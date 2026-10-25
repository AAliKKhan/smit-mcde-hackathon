"""Gate W tests (T030-T036): warehouse star-schema integrity - RI, SCD2
validity (Rule 2), month-end attribution (Rule 3), dim_date coverage,
fact<->staging parity (FR-025..FR-029, SC-005).

Run: python -m pytest tests/test_warehouse_integrity.py -v
"""

from __future__ import annotations

import pytest

from common import db
from config import DIM_DATE_END, WINDOW_START
from quality import checks as qc
from transform import build as build_mod
from warehouse import build_warehouse as wh_build


@pytest.fixture(scope="module")
def warehouse_built() -> None:
    if db.table_count("staging.attendance_daily") == 0:
        build_mod.run(build_mod.STAGE2 + build_mod.STAGE3)
    if db.table_count("warehouse.fact_attendance_daily") == 0:
        wh_build.main()


def _scalar(sql: str) -> int:
    return int(db.scalar(sql) or 0)


def test_warehouse_checks_all_pass(warehouse_built) -> None:
    failed = [c for c in qc.warehouse_checks() if not c["ok"]]
    assert not failed, f"warehouse checks failed: {failed}"


def test_dim_counts(warehouse_built) -> None:
    expected_days = (DIM_DATE_END - WINDOW_START).days + 1
    assert db.table_count("warehouse.dim_date") == expected_days
    assert db.table_count("warehouse.dim_department") == 25
    assert db.table_count("warehouse.dim_shift") == 4
    assert db.table_count("warehouse.dim_employee") == 3686


def test_attendance_fk_row_is_valid_version(warehouse_built) -> None:
    # stronger than PRAGMA FK: the employee_key must resolve to the SCD2
    # version that actually contains the work_date (correct join, not just
    # an existing key)
    bad = _scalar(
        "SELECT COUNT(*) FROM warehouse.fact_attendance_daily f "
        "JOIN warehouse.dim_employee de ON de.employee_key = f.employee_key "
        "WHERE de.emp_id <> f.emp_id OR f.work_date < de.valid_from "
        "OR (de.valid_to IS NOT NULL AND f.work_date > de.valid_to)"
    )
    assert bad == 0, f"{bad} attendance rows keyed to wrong SCD2 version"


def test_payroll_month_end_dept_matches_version(warehouse_built) -> None:
    bad = _scalar(
        "SELECT COUNT(*) FROM warehouse.fact_payroll_line f "
        "JOIN warehouse.dim_employee de ON de.employee_key = f.employee_key "
        "WHERE f.dept_id_month_end <> de.dept_id"
    )
    assert bad == 0, f"{bad} payroll lines disagree with their keyed version"
    null_dept = _scalar(
        "SELECT COUNT(*) FROM warehouse.fact_payroll_line "
        "WHERE dept_id_month_end IS NULL"
    )
    assert null_dept == 0, f"{null_dept} payroll lines without month-end dept"


def test_measures_match_staging(warehouse_built) -> None:
    fact = db.read_sql(
        "SELECT COUNT(*) n, SUM(worked_hours) wh, SUM(ot_hours) ot, "
        "SUM(late_minutes) lm FROM warehouse.fact_attendance_daily"
    ).iloc[0]
    stg = db.read_sql(
        "SELECT COUNT(*) n, SUM(worked_hours) wh, SUM(ot_hours) ot, "
        "SUM(late_minutes) lm FROM staging.attendance_daily"
    ).iloc[0]
    assert fact.n == stg.n
    for col in ("wh", "ot", "lm"):
        assert abs(float(fact[col]) - float(stg[col])) < 1e-6, col


def test_overtime_fact_approved_only(warehouse_built) -> None:
    non_approved = _scalar(
        "SELECT COUNT(*) FROM warehouse.fact_overtime_approved f "
        "JOIN staging.overtime_requests o USING (request_id) "
        "WHERE o.status <> 'Approved'"
    )
    assert non_approved == 0, f"{non_approved} non-approved OT rows in fact"
    assert db.table_count("warehouse.fact_overtime_approved") == _scalar(
        "SELECT COUNT(*) FROM staging.overtime_requests WHERE status = 'Approved'"
    )
