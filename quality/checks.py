"""T023/T029/T036 - Reconciliation + integrity checks.

Raw = staging + rejected per table (Gate S), attendance_daily invariants
(SC-004), and warehouse RI/SCD2/parity checks (Gate W). Every check counts
VIOLATIONS (0 = pass); CLI exits 1 on any failure.

Run: python -m quality.checks
"""

from __future__ import annotations

from common import db


def _n(sql: str) -> int:
    return int(db.scalar(sql) or 0)


def reconciliation_report() -> list[dict]:
    raw = {t: _n(f"SELECT COUNT(*) FROM raw.{t}") for t in (
        "employees", "employment_history", "departments", "shifts",
        "shift_roster", "device_mapping", "biometric_punches", "holidays",
        "leave_requests", "overtime_requests", "payroll_lines", "applications",
    )}
    rows: list[dict] = []

    def add(table: str, staged: int, rejected: int = 0, extra: int = 0,
            note: str = "", extra_inside: bool = False) -> None:
        # extra_inside: `extra` rows are PART of `staged` (gap-filled weeks);
        # otherwise `extra` rows live outside staging (dedupe log).
        if extra_inside:
            accounted = staged - extra + rejected
        else:
            accounted = staged + rejected + extra
        rows.append({
            "table": table,
            "raw": raw[table],
            "staged": staged,
            "rejected": rejected,
            "extra": extra,
            "accounted": accounted,
            "ok": accounted == raw[table],
            "note": note,
        })

    deduped = _n("SELECT COUNT(*) FROM staging.employees_dedupe_log")
    add("employees", _n("SELECT COUNT(*) FROM staging.employees"),
        extra=deduped, note="extra = dedupe log rows (Rule 1)")
    add("employment_history", _n("SELECT COUNT(*) FROM staging.employment_history"),
        note="row count preserved; only effective_to recomputed (Rule 2)")
    add("departments", _n("SELECT COUNT(*) FROM staging.departments"))
    add("shifts", _n("SELECT COUNT(*) FROM staging.shifts"))
    gap_filled = _n("SELECT COUNT(*) FROM staging.shift_roster WHERE is_gap_filled = 1")
    add("shift_roster", _n("SELECT COUNT(*) FROM staging.shift_roster"),
        extra=gap_filled, extra_inside=True,
        note="extra = Rule 5/6 gap-filled weeks (inside staging)")
    add("device_mapping", _n("SELECT COUNT(*) FROM staging.device_mapping"))

    punch_kept = _n("SELECT COUNT(*) FROM staging.punches")
    rej_unmapped = _n(
        "SELECT COUNT(*) FROM staging.rejected_punches "
        "WHERE reason = 'unmapped_device_user'"
    )
    rej_collapsed = _n(
        "SELECT COUNT(*) FROM staging.rejected_punches "
        "WHERE reason = 'duplicate_within_2min'"
    )
    rows.append({
        "table": "biometric_punches",
        "raw": raw["biometric_punches"],
        "staged": punch_kept,
        "rejected": rej_unmapped + rej_collapsed,
        "extra": 0,
        "accounted": punch_kept + rej_unmapped + rej_collapsed,
        "ok": punch_kept + rej_unmapped + rej_collapsed == raw["biometric_punches"],
        "note": f"rejected = {rej_unmapped:,} unmapped + {rej_collapsed:,} <2min",
    })

    add("holidays", _n("SELECT COUNT(*) FROM staging.holidays"))
    add("leave_requests", _n("SELECT COUNT(*) FROM staging.leave_requests"))
    add("overtime_requests", _n("SELECT COUNT(*) FROM staging.overtime_requests"))
    add("payroll_lines", _n("SELECT COUNT(*) FROM staging.payroll_lines"))
    add("applications", _n("SELECT COUNT(*) FROM staging.applications"))
    return rows


def steps_reconciliation() -> dict:
    """Leave approval steps: raw JSON array length == staged step rows."""
    raw_steps = _n(
        "SELECT COALESCE(SUM(json_array_length(approvals)), 0) "
        "FROM raw.leave_requests"
    )
    staged_steps = _n("SELECT COUNT(*) FROM staging.leave_approval_steps")
    return {"raw_steps": raw_steps, "staged_steps": staged_steps,
            "ok": raw_steps == staged_steps}


STATUS_DOMAIN = ("Absent", "Holiday", "Missing Punch", "On Leave",
                 "Present", "Weekly Off")


def attendance_checks() -> list[dict]:
    """T029 / SC-004: attendance_daily invariants -> [{check, violations, ok}].

    Every check counts VIOLATIONS (0 = pass): grain, status domain, non-negative
    measures, half-hour OT quantization (Rule 14), no shift > 16h (FR-024),
    status<->punches consistency with the Rule-12 CASE chain, and
    Present-only OT/lateness (Rules 13/14).
    """
    att = "staging.attendance_daily"
    checks: list[dict] = []

    def add(name: str, violations_sql: str, note: str = "") -> None:
        n = _n(violations_sql)
        checks.append({"check": name, "violations": n, "ok": n == 0,
                       "note": note})

    add("one_row_per_emp_day",
        f"SELECT COUNT(*) FROM (SELECT emp_id, work_date FROM {att} "
        "GROUP BY emp_id, work_date HAVING COUNT(*) > 1)")
    domain = ", ".join(f"'{s}'" for s in STATUS_DOMAIN)
    add("status_in_domain",
        f"SELECT COUNT(*) FROM {att} "
        f"WHERE status IS NULL OR status NOT IN ({domain})",
        "one status per day, accepted domain only (Rule 12)")
    add("non_negative_measures",
        f"SELECT COUNT(*) FROM {att} WHERE worked_hours < 0 OR ot_hours < 0 "
        "OR late_minutes < 0 OR early_leave_minutes < 0")
    add("ot_half_hour_multiples",
        f"SELECT COUNT(*) FROM {att} "
        "WHERE ABS(ot_hours * 2.0 - ROUND(ot_hours * 2.0)) > 1e-9",
        "Rule 14: floored to whole half-hours")
    add("no_shift_over_16h",
        f"SELECT COUNT(*) FROM {att} WHERE worked_hours > 16.0",
        "FR-024 / SC-004")
    add("status_punches_consistent",
        f"SELECT COUNT(*) FROM {att} WHERE "
        "(status = 'Present'      AND punches_count < 2) OR "
        "(status = 'Missing Punch' AND punches_count <> 1) OR "
        "(status = 'Absent'        AND punches_count <> 0) OR "
        "(status = 'Weekly Off'    AND punches_count <> 0) OR "
        "(status = 'Holiday'       AND punches_count <> 0)",
        "stored punches_count must agree with the Rule-12 CASE chain "
        "(On Leave may keep punches)")
    add("ot_and_lateness_only_on_present",
        f"SELECT COUNT(*) FROM {att} WHERE status <> 'Present' AND "
        "(ot_hours <> 0 OR late_minutes <> 0 OR early_leave_minutes <> 0)",
        "Rules 13/14 measures are Present-only")
    return checks


def warehouse_checks() -> list[dict]:
    """T036 / Gate W: warehouse integrity -> [{check, violations, ok, note}].

    Referential integrity over every fact (PRAGMA foreign_key_check), SCD2
    validity (no overlap, no gap, exactly one current row per employee),
    dim_date window coverage, fact<->staging row parity, and status
    distribution parity for the attendance fact.
    """
    from config import DIM_DATE_END, WINDOW_START

    checks: list[dict] = []

    def add(name: str, violations: int, note: str = "") -> None:
        checks.append({"check": name, "violations": int(violations),
                       "ok": int(violations) == 0, "note": note})

    c = db.conn()
    try:
        fk = len(c.execute("PRAGMA warehouse.foreign_key_check").fetchall())
    finally:
        c.close()
    add("foreign_key_integrity", fk,
        "all fact FKs resolve inside db/warehouse.db")

    add("scd2_no_overlap",
        _n("SELECT COUNT(*) FROM warehouse.dim_employee a "
           "JOIN warehouse.dim_employee b ON a.emp_id = b.emp_id "
           " AND a.employee_key <> b.employee_key "
           " AND a.valid_from <= COALESCE(b.valid_to, '9999-12-31') "
           " AND COALESCE(a.valid_to, '9999-12-31') >= b.valid_from "
           " AND a.valid_from < b.valid_from"),
        "no two versions of an employee overlap (Rule 2)")

    add("scd2_contiguous",
        _n("SELECT COUNT(*) FROM ("
           "  SELECT valid_to, LEAD(valid_from) OVER "
           "    (PARTITION BY emp_id ORDER BY valid_from) nxt "
           "  FROM warehouse.dim_employee) "
           "WHERE nxt IS NOT NULL AND valid_to <> date(nxt, '-1 day')"),
        "valid_to = next valid_from - 1 day; no gaps between versions")

    add("scd2_one_current_per_emp",
        _n("SELECT COUNT(*) FROM (SELECT emp_id FROM warehouse.dim_employee "
           "GROUP BY emp_id HAVING SUM(is_current) <> 1)"),
        "exactly one open (is_current) version per employee")

    expected_days = (DIM_DATE_END - WINDOW_START).days + 1
    add("dim_date_covers_window",
        abs(expected_days - _n("SELECT COUNT(*) FROM warehouse.dim_date"))
        + _n("SELECT COUNT(*) FROM warehouse.dim_date WHERE date_key < "
             f"'{WINDOW_START.isoformat()}' OR date_key > "
             f"'{DIM_DATE_END.isoformat()}'"),
        f"exactly {expected_days} days {WINDOW_START}..{DIM_DATE_END}")

    add("fact_row_parity",
        _n("SELECT ABS((SELECT COUNT(*) FROM warehouse.fact_attendance_daily)"
           " - (SELECT COUNT(*) FROM staging.attendance_daily))"
           " + ABS((SELECT COUNT(*) FROM warehouse.fact_leave_day)"
           " - (SELECT COUNT(*) FROM staging.leave_days))"
           " + ABS((SELECT COUNT(*) FROM warehouse.fact_overtime_approved)"
           " - (SELECT COUNT(*) FROM staging.overtime_requests "
           "     WHERE status = 'Approved'))"
           " + ABS((SELECT COUNT(*) FROM warehouse.fact_payroll_line)"
           " - (SELECT COUNT(*) FROM staging.payroll_lines))"),
        "every eligible staging row landed in its fact")

    add("status_distribution_parity",
        _n("SELECT "
           " (SELECT COUNT(*) FROM ("
           "    SELECT status, COUNT(*) n FROM warehouse.fact_attendance_daily"
           "    GROUP BY status"
           "    EXCEPT SELECT status, COUNT(*) n"
           "           FROM staging.attendance_daily GROUP BY status))"
           " + (SELECT COUNT(*) FROM ("
           "    SELECT status, COUNT(*) n FROM staging.attendance_daily"
           "    GROUP BY status"
           "    EXCEPT SELECT status, COUNT(*) n"
           "           FROM warehouse.fact_attendance_daily GROUP BY status))"),
        "per-status totals identical fact vs staging")

    add("payroll_month_end_dept_present",
        _n("SELECT COUNT(*) FROM warehouse.fact_payroll_line "
           "WHERE dept_id_month_end IS NULL"),
        "Rule 3: every payslip line resolves a month-end department")
    return checks


PK_TABLES: dict[str, dict[str, list[str]]] = {
    "staging": {
        "employees": ["emp_id"],
        "employees_dedupe_log": ["emp_id", "dropped_hash"],
        "employment_history": ["record_id"],
        "departments": ["dept_id"],
        "shifts": ["shift_code"],
        "shift_roster": ["emp_id", "week_start"],
        "device_mapping": ["device_id", "device_user_id"],
        "holidays": ["holiday_date", "scope"],
        "punches": ["emp_id", "punch_time"],
        "rejected_punches": ["punch_id"],
        "drift_corrections": ["device_id"],
        "leave_requests": ["request_id"],
        "leave_approval_steps": ["request_id", "step"],
        "leave_days": ["request_id", "day_date"],
        "overtime_requests": ["request_id"],
        "payroll_lines": ["line_id"],
        "applications": ["application_id", "stage", "stage_date"],
        "attendance_daily": ["emp_id", "work_date"],
    },
    "warehouse": {
        "dim_employee": ["employee_key"],
        "dim_department": ["dept_id"],
        "dim_shift": ["shift_code"],
        "dim_date": ["date_key"],
        "fact_attendance_daily": ["employee_key", "date_key"],
        "fact_leave_day": ["request_id", "date_key"],
        "fact_overtime_approved": ["request_id"],
        "fact_payroll_line": ["line_id"],
    },
}


def pk_checks() -> list[dict]:
    """T049 / FR-046: every declared PK - duplicate-free and NOT NULL.

    Returns [{check, target, violations, ok, note}]; raw tables are the
    immutable landing zone (no PKs declared) and are covered by the
    reconciliation family instead.
    """
    checks: list[dict] = []
    for schema, tables in PK_TABLES.items():
        for table, cols in tables.items():
            key = ", ".join(cols)
            dup = _n(
                f"SELECT COUNT(*) FROM (SELECT {key} FROM {schema}.{table} "
                f"GROUP BY {key} HAVING COUNT(*) > 1)"
            )
            null_sql = " OR ".join(f"{c} IS NULL" for c in cols)
            nulls = _n(
                f"SELECT COUNT(*) FROM {schema}.{table} WHERE {null_sql}"
            )
            checks.append({
                "check": f"pk_{table}",
                "target": f"{schema}.{table}",
                "violations": dup + nulls,
                "ok": dup + nulls == 0,
                "note": f"key ({key}): {dup} duplicate, {nulls} null",
            })
    return checks


ACCEPTED_VALUES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "leave_type": ("staging.leave_requests", "leave_type",
                   ("Annual", "Casual", "Sick")),
    "leave_type_day": ("staging.leave_days", "leave_type",
                       ("Annual", "Casual", "Sick")),
    "pay_component": ("staging.payroll_lines", "component",
                      ("ABSENCE_DEDUCTION", "BASIC", "CONVEYANCE", "EOBI",
                       "HOUSE_RENT", "INCOME_TAX", "LOAN_INSTALLMENT",
                       "MEDICAL", "OVERTIME")),
    "pay_component_type": ("staging.payroll_lines", "component_type",
                           ("EARNING", "DEDUCTION")),
}


def accepted_value_checks() -> list[dict]:
    """T049 / FR-049: accepted-value domains beyond attendance status
    (which attendance_checks already covers: Rule 12 status domain)."""
    checks: list[dict] = []
    for name, (target, col, domain) in ACCEPTED_VALUES.items():
        allowed = ", ".join(f"'{v}'" for v in domain)
        n = _n(
            f"SELECT COUNT(*) FROM {target} "
            f"WHERE {col} IS NULL OR {col} NOT IN ({allowed})"
        )
        checks.append({"check": f"domain_{name}", "target": target,
                       "violations": n, "ok": n == 0,
                       "note": f"{col} in {{{', '.join(domain)}}}"})
    return checks


def main() -> int:
    rows = reconciliation_report()
    print(f"{'table':<24}{'raw':>9}{'staged':>9}{'rejected':>9}{'extra':>7}  ok  note")
    print("-" * 100)
    for r in rows:
        print(f"{r['table']:<24}{r['raw']:>9,}{r['staged']:>9,}"
              f"{r['rejected']:>9,}{r['extra']:>7,}  {'Y' if r['ok'] else 'N'}   {r['note']}")
    steps = steps_reconciliation()
    print(f"\nleave approval steps: raw={steps['raw_steps']:,} "
          f"staged={steps['staged_steps']:,} ok={steps['ok']}")

    att = attendance_checks()
    print("\nattendance invariants (T029 / SC-004):")
    for c in att:
        flag = "PASS" if c["ok"] else "FAIL"
        print(f"  {flag}  {c['check']:<32} violations={c['violations']:<7,} {c['note']}")
    bad_att = [c for c in att if not c["ok"]]

    wh = warehouse_checks()
    print("\nwarehouse integrity (T036 / Gate W):")
    for c in wh:
        flag = "PASS" if c["ok"] else "FAIL"
        print(f"  {flag}  {c['check']:<32} violations={c['violations']:<7,} {c['note']}")
    bad_wh = [c for c in wh if not c["ok"]]

    pks = pk_checks()
    doms = accepted_value_checks()
    print("\nkeys + accepted values (T049 / FR-046, FR-049):")
    for c in pks + doms:
        flag = "PASS" if c["ok"] else "FAIL"
        print(f"  {flag}  {c['check']:<32} violations={c['violations']:<7,} {c['note']}")
    bad_keys = [c for c in pks + doms if not c["ok"]]

    bad = [r for r in rows if not r["ok"]]
    if bad or not steps["ok"] or bad_att or bad_wh or bad_keys:
        print(f"\nRECONCILIATION FAILED: {len(bad)} table(s), "
              f"{len(bad_att)} attendance check(s), {len(bad_wh)} warehouse "
              f"check(s), {len(bad_keys)} key/domain check(s)")
        return 1
    print("\nreconciliation OK: raw = staging + rejected for every table")
    print("attendance invariants OK: SC-004 satisfied")
    print("warehouse integrity OK: RI + SCD2 + parity satisfied")
    print("keys + accepted values OK: FR-046 / FR-049 satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
