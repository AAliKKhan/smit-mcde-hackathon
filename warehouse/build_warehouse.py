"""T030-T034 - Stage 4: star-schema loads (Rules 2, 3; FR-025..FR-029, Gate W).

Part A  dim_date         pandas date_range 2026-04-01..2026-10-31 (SQLite has no
                         generate_series - research R1) with day/month/week/weekday/
                         is_weekend flags and is_holiday_all from scope-ALL holidays.
Part B  dim_employee     SCD2 from staging.employment_history: valid_from =
                         effective_from, valid_to = effective_to already recomputed
                         as LEAD(effective_from)-1d by 02 (NULL = open/current),
                         attributes joined from staging.employees + departments
                         (Rule 2, FR-026).
Part C  dim_department, dim_shift - direct copies of the staging reference tables.
Part D  facts            attendance (SCD2 join on work_date), leave days
                         (is_counted only), APPROVED overtime only, payroll lines
                         with dept_id_month_end resolved at min(month end,
                         separation date) - Rule 3 month-end attribution (FR-029).

Idempotent: applies DDL (all IF NOT EXISTS), deletes facts then dims, reloads.
Ends with PRAGMA warehouse.foreign_key_check - 0 rows required (T034).
dims load before facts so every FK resolves on insert.

Run: python -m warehouse.build_warehouse
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from common import db
from config import DIM_DATE_END, WINDOW_START
from transform.util import print_counts
from warehouse.ddl.apply import apply as apply_ddl

# Rule 2 / R7: a business date resolves to the SCD2 row containing it.
_SCD2 = """
JOIN warehouse.dim_employee de
  ON de.emp_id = {emp}
 AND de.valid_from <= {dt}
 AND (de.valid_to IS NULL OR de.valid_to >= {dt})
"""

_FACT_TABLES = ("fact_attendance_daily", "fact_leave_day",
                "fact_overtime_approved", "fact_payroll_line")
_DIM_TABLES = ("dim_employee", "dim_department", "dim_shift", "dim_date")


def build_dim_date(c: sqlite3.Connection) -> int:
    idx = pd.date_range(WINDOW_START, DIM_DATE_END, freq="D")
    hol = db.read_sql(
        "SELECT holiday_date, holiday_name FROM staging.holidays WHERE scope = 'ALL'"
    )
    hol_map = dict(zip(hol["holiday_date"], hol["holiday_name"]))
    rows = []
    for d in idx:
        ds = d.strftime("%Y-%m-%d")
        rows.append((
            ds,
            d.day,
            d.strftime("%Y-%m"),
            d.replace(day=1).strftime("%Y-%m-%d"),
            (d + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d"),
            (d - pd.Timedelta(days=int(d.weekday()))).strftime("%Y-%m-%d"),
            int(d.isoweekday()),
            d.strftime("%a"),
            1 if d.weekday() == 6 else 0,          # Sunday = weekend (Rule 4)
            1 if ds in hol_map else 0,
            hol_map.get(ds),
        ))
    c.executemany(
        "INSERT INTO warehouse.dim_date (date_key, day, month, month_start, "
        "month_end, week_start, weekday_no, weekday_name, is_weekend, "
        "is_holiday_all, holiday_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def build_dim_employee(c: sqlite3.Connection) -> int:
    cur = c.execute(
        """
        INSERT INTO warehouse.dim_employee (
          emp_id, full_name, gender, date_of_birth, plant, dept_id, dept_name,
          designation, grade, employment_type, status, hire_date,
          separation_date, annual_leave_entitlement, basic_salary,
          change_reason, valid_from, valid_to, is_current)
        SELECT h.emp_id, e.full_name, e.gender, e.date_of_birth,
               COALESCE(d.plant, e.plant), h.dept_id, d.dept_name,
               h.designation, h.grade, e.employment_type, e.status,
               e.hire_date, e.separation_date, e.annual_leave_entitlement,
               h.basic_salary, h.change_reason,
               h.effective_from, h.effective_to,
               CASE WHEN h.effective_to IS NULL THEN 1 ELSE 0 END
        FROM staging.employment_history h
        JOIN staging.employees e ON e.emp_id = h.emp_id
        LEFT JOIN staging.departments d ON d.dept_id = h.dept_id
        """
    )
    return cur.rowcount


def build_ref_dims(c: sqlite3.Connection) -> tuple[int, int]:
    dep = c.execute(
        "INSERT INTO warehouse.dim_department "
        "(dept_id, dept_name, plant, cost_center, previous_name, renamed_on) "
        "SELECT dept_id, dept_name, plant, cost_center, previous_name, renamed_on "
        "FROM staging.departments"
    ).rowcount
    sh = c.execute(
        "INSERT INTO warehouse.dim_shift "
        "(shift_code, name, start_time, end_time, crosses_midnight, "
        "grace_minutes, applies_to) "
        "SELECT shift_code, name, start_time, end_time, crosses_midnight, "
        "grace_minutes, applies_to FROM staging.shifts"
    ).rowcount
    return dep, sh


def build_facts(c: sqlite3.Connection) -> dict[str, int]:
    # attendance: grain (emp_id, work_date) -> SCD2 row containing work_date
    att = c.execute(
        """
        INSERT INTO warehouse.fact_attendance_daily (
          employee_key, date_key, shift_code, emp_id, work_date, plant, dept_id,
          status, punches_count, worked_hours, late_minutes,
          early_leave_minutes, ot_hours, is_working_day)
        SELECT de.employee_key, a.work_date, a.shift_code, a.emp_id, a.work_date,
               a.plant, a.dept_id, a.status, a.punches_count, a.worked_hours,
               a.late_minutes, a.early_leave_minutes, a.ot_hours,
               a.is_working_day
        FROM staging.attendance_daily a
        """ + _SCD2.format(emp="a.emp_id", dt="a.work_date")
    ).rowcount

    # leave: countable days only (staging.leave_days is built from is_counted
    # requests; the join re-asserts it); dept snapshot via SCD2 at the day
    leave = c.execute(
        """
        INSERT INTO warehouse.fact_leave_day (
          employee_key, date_key, request_id, emp_id, leave_type, plant, dept_id)
        SELECT de.employee_key, ld.day_date, ld.request_id, ld.emp_id,
               ld.leave_type, r.plant, de.dept_id
        FROM staging.leave_days ld
        JOIN staging.leave_requests r ON r.request_id = ld.request_id
        """ + _SCD2.format(emp="ld.emp_id", dt="ld.day_date") + """
        WHERE r.is_counted = 1
        """
    ).rowcount

    # overtime: APPROVED requests only (Rule 19); rejected/pending stay in staging
    ot = c.execute(
        """
        INSERT INTO warehouse.fact_overtime_approved (
          request_id, employee_key, date_key, emp_id, ot_date,
          approved_hours, requested_hours, plant, dept_id)
        SELECT o.request_id, de.employee_key, o.ot_date, o.emp_id, o.ot_date,
               o.approved_hours, o.requested_hours, de.plant, de.dept_id
        FROM staging.overtime_requests o
        """ + _SCD2.format(emp="o.emp_id", dt="o.ot_date") + """
        WHERE o.status = 'Approved'
        """
    ).rowcount

    # payroll: Rule 3 - department as of month end, or the separation date when
    # that falls earlier (last working day of the month for a separated employee)
    pay = c.execute(
        """
        INSERT INTO warehouse.fact_payroll_line (
          line_id, employee_key, payroll_month, emp_id, component,
          component_type, units, amount, plant, dept_id_month_end)
        SELECT p.line_id, de.employee_key, p.payroll_month, p.emp_id,
               p.component, p.component_type, p.units, p.amount,
               de.plant, de.dept_id
        FROM staging.payroll_lines p
        JOIN staging.employees e ON e.emp_id = p.emp_id
        JOIN warehouse.dim_employee de
          ON de.emp_id = p.emp_id
         AND de.valid_from <= min(
               date(p.payroll_month || '-01', '+1 month', '-1 day'),
               COALESCE(NULLIF(e.separation_date, ''),
                        date(p.payroll_month || '-01', '+1 month', '-1 day')))
         AND (de.valid_to IS NULL OR de.valid_to >= min(
               date(p.payroll_month || '-01', '+1 month', '-1 day'),
               COALESCE(NULLIF(e.separation_date, ''),
                        date(p.payroll_month || '-01', '+1 month', '-1 day'))))
        """
    ).rowcount

    return {"fact_attendance_daily": att, "fact_leave_day": leave,
            "fact_overtime_approved": ot, "fact_payroll_line": pay}


def main() -> dict:
    apply_ddl()  # idempotent CREATE IF NOT EXISTS - tables must exist for DELETEs
    c = db.conn()
    try:
        # idempotent reload: children before parents (FKs enforced on delete)
        for t in _FACT_TABLES + _DIM_TABLES:
            c.execute(f"DELETE FROM warehouse.{t}")

        n_date = build_dim_date(c)
        n_emp = build_dim_employee(c)
        n_dep, n_shift = build_ref_dims(c)
        facts = build_facts(c)

        # T034: every FK resolves (facts -> dims), 0 orphans allowed
        violations = c.execute("PRAGMA warehouse.foreign_key_check").fetchall()
        c.commit()
    finally:
        c.close()

    stats = {
        "dim_date": n_date,
        "dim_employee": n_emp,
        "dim_department": n_dep,
        "dim_shift": n_shift,
        **facts,
        "fk_violations": len(violations),
    }
    print_counts("build_warehouse", stats)
    if violations:
        raise SystemExit(
            f"FK violations after warehouse load: {len(violations)} row(s): "
            f"{violations[:5]}"
        )
    return stats


if __name__ == "__main__":
    main()
