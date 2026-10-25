"""Gate S tests (T015-T024): staging invariants (SC-003 planted issues fixed,
Rules 1-21 evidence, raw = staging + rejected).

Run: python -m pytest tests/test_staging_invariants.py -v
"""

from __future__ import annotations

import re

import pytest

from common import db
from config import PLANT_CODE, SHIFT_CODES
from quality import checks as qc
from transform import build as build_mod

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="module")
def staging_built() -> None:
    if db.table_count("staging.employees") == 0 or db.table_count("staging.punches") == 0:
        build_mod.run(build_mod.STAGE2)


def _scalar(sql: str) -> int:
    return int(db.scalar(sql) or 0)


# ----------------------------------------------------------------- employees
def test_iso_dates_only(staging_built) -> None:
    bad = _scalar(
        "SELECT COUNT(*) FROM staging.employees WHERE "
        "(hire_date IS NOT NULL AND hire_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]') "
        "OR (date_of_birth IS NOT NULL AND date_of_birth NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]') "
        "OR (separation_date IS NOT NULL AND separation_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')"
    )
    assert bad == 0, f"{bad} non-ISO dates in staging.employees"


def test_dept_resolution_100pct(staging_built) -> None:
    unresolved = _scalar(
        "SELECT COUNT(*) FROM staging.employees e "
        "LEFT JOIN staging.departments d USING (dept_id) "
        "WHERE e.dept_id IS NULL OR d.dept_id IS NULL "
        "OR e.department != d.dept_name"
    )
    assert unresolved == 0, f"{unresolved} employees with unresolved/mismatched department"


def test_dedupe_keeps_latest_updated_at(staging_built) -> None:
    assert db.table_count("staging.employees") == 1266
    log = _scalar("SELECT COUNT(*) FROM staging.employees_dedupe_log")
    assert log == 50, f"expected 50 dropped duplicates, got {log}"
    stale_kept = _scalar(
        """
        SELECT COUNT(*) FROM staging.employees_dedupe_log l
        WHERE EXISTS (
          SELECT 1 FROM raw.employees r
          WHERE r.emp_id = l.emp_id AND r.updated_at > l.kept_updated_at
        )
        """
    )
    assert stale_kept == 0, "a kept row is older than a dropped duplicate (Rule 1)"


def test_status_domain(staging_built) -> None:
    bad = _scalar(
        "SELECT COUNT(*) FROM staging.employees "
        "WHERE status IS NOT NULL AND status NOT IN ('Active', 'Separated')"
    )
    assert bad == 0, f"{bad} employees outside status domain"


# ------------------------------------------------------------------- history
def test_history_valid_to_recomputed(staging_built) -> None:
    bad = _scalar(
        """
        WITH s AS (
          SELECT effective_from, effective_to,
                 LEAD(effective_from) OVER (PARTITION BY emp_id
                     ORDER BY effective_from) AS nx
          FROM staging.employment_history
        )
        SELECT COUNT(*) FROM s
        WHERE (nx IS NOT NULL AND effective_to != date(nx, '-1 day'))
           OR (nx IS NULL AND effective_to IS NOT NULL)
        """
    )
    assert bad == 0, f"{bad} rows with wrong recomputed effective_to (Rule 2)"


def test_history_overlaps_gone_and_raw_preserved(staging_built) -> None:
    overlaps = _scalar(
        """
        WITH s AS (
          SELECT effective_to, LEAD(effective_from) OVER (PARTITION BY emp_id
                     ORDER BY effective_from) AS nx
          FROM staging.employment_history
        )
        SELECT COUNT(*) FROM s WHERE nx IS NOT NULL AND effective_to >= nx
        """
    )
    assert overlaps == 0, f"{overlaps} overlapping SCD2 rows remain"
    flagged = _scalar(
        "SELECT COUNT(DISTINCT emp_id) FROM staging.employment_history "
        "WHERE raw_effective_to IS NOT NULL AND raw_effective_to != effective_to"
    )
    assert flagged > 0, "raw_effective_to forensics column lost"


# ------------------------------------------------------------------ reference
def test_roster_full_grid(staging_built) -> None:
    emps = db.table_count("staging.employees")
    weeks = _scalar("SELECT COUNT(DISTINCT week_start) FROM staging.shift_roster")
    total = db.table_count("staging.shift_roster")
    assert total == emps * weeks, f"roster grid incomplete: {total} != {emps}x{weeks}"
    bad_shift = _scalar(
        "SELECT COUNT(*) FROM staging.shift_roster WHERE shift_code NOT IN ("
        + ",".join(f"'{c}'" for c in SHIFT_CODES) + ")"
    )
    assert bad_shift == 0, "roster with unknown shift_code"
    filled = _scalar("SELECT COUNT(*) FROM staging.shift_roster WHERE is_gap_filled = 1")
    assert filled == 2844, f"expected 2844 gap-filled weeks, got {filled}"


# -------------------------------------------------------------------- punches
def test_punch_accounting_exact(staging_built) -> None:
    rows = {r["table"]: r for r in qc.reconciliation_report()}
    p = rows["biometric_punches"]
    assert p["ok"], f"punch reconciliation failed: {p}"
    assert p["rejected"] == 6962 + 16175


def test_rejects_have_reasons(staging_built) -> None:
    bad = _scalar(
        "SELECT COUNT(*) FROM staging.rejected_punches "
        "WHERE reason IS NULL OR reason NOT IN "
        "('unmapped_device_user', 'duplicate_within_2min')"
    )
    assert bad == 0, f"{bad} rejected punches without a valid reason"


def test_no_punches_within_2min(staging_built) -> None:
    pairs = _scalar(
        """
        WITH s AS (
          SELECT emp_id, punch_time,
                 LAG(punch_time) OVER (PARTITION BY emp_id
                     ORDER BY punch_time) AS prev
          FROM staging.punches
        )
        SELECT COUNT(*) FROM s
        WHERE prev IS NOT NULL
          AND (julianday(punch_time) - julianday(prev)) * 1440.0 < 2.0
        """
    )
    assert pairs == 0, f"{pairs} punch pairs closer than 2 minutes (Rule 9)"


def test_drift_detected_and_corrected(staging_built) -> None:
    rows = db.read_sql("SELECT * FROM staging.drift_corrections")
    assert len(rows) >= 1, "no drift correction recorded (Rule 11)"
    time_re = re.compile(r"^\d{2}:\d{2}:\d{2}$")
    for r in rows.itertuples():
        assert r.offset_minutes != 0
        assert r.detection_method and r.evidence_note
        assert time_re.match(r.avg_first_punch_before or ""), "before evidence not HH:MM:SS"
        assert time_re.match(r.avg_first_punch_after or ""), "after evidence not HH:MM:SS"


def test_night_spillover_attributed(staging_built) -> None:
    spillover = _scalar(
        "SELECT COUNT(*) FROM staging.punches "
        "WHERE date(punch_time) = '2026-10-01' AND shift_date = '2026-09-30'"
    )
    assert spillover > 0, "1 Oct check-outs not attributed to 30 Sep (Rule 7)"
    null_attr = _scalar(
        "SELECT COUNT(*) FROM staging.punches WHERE shift_date IS NULL"
    )
    assert null_attr == 0, "punches without shift_date"


# ---------------------------------------------------------------------- leave
def test_rule16_counted_flags(staging_built) -> None:
    counted = _scalar("SELECT COUNT(*) FROM staging.leave_requests WHERE is_counted = 1")
    assert counted == 4282, f"expected 4282 counted requests, got {counted}"
    bad = _scalar(
        """
        SELECT COUNT(*) FROM staging.leave_requests r
        WHERE r.is_counted = 1 AND r.cancelled_at IS NOT NULL
        """
    )
    assert bad == 0, "cancelled request flagged as counted"
    bad2 = _scalar(
        """
        SELECT COUNT(*) FROM staging.leave_requests r
        WHERE r.is_counted = 1 AND (
          (SELECT COUNT(*) FROM staging.leave_approval_steps s
             WHERE s.request_id = r.request_id AND s.action = 'Approved') != 2
          OR (SELECT COUNT(*) FROM staging.leave_approval_steps s
             WHERE s.request_id = r.request_id) != 2
        )
        """
    )
    assert bad2 == 0, "counted request without exactly 2 Approved steps"
    missing_reason = _scalar(
        "SELECT COUNT(*) FROM staging.leave_requests "
        "WHERE is_counted = 0 AND (reject_reason IS NULL OR reject_reason = '')"
    )
    assert missing_reason == 0, "uncounted request without reject_reason"


def test_no_leave_day_on_sunday_or_holiday(staging_built) -> None:
    sundays = _scalar(
        "SELECT COUNT(*) FROM staging.leave_days "
        "WHERE CAST(strftime('%w', day_date) AS INT) = 0"
    )
    assert sundays == 0, f"{sundays} leave days on a Sunday (Rule 17)"
    holidays = _scalar(
        """
        SELECT COUNT(*) FROM staging.leave_days d
        JOIN staging.leave_requests r USING (request_id)
        JOIN staging.holidays h
          ON h.holiday_date = d.day_date
         AND (h.scope = 'ALL' OR h.scope = CASE r.plant
                WHEN 'Head Office' THEN 'HO'
                WHEN 'Korangi Plant' THEN 'KOR'
                WHEN 'SITE Plant' THEN 'SITE'
                WHEN 'Faisalabad Plant' THEN 'FSD' END)
        """
    )
    assert holidays == 0, f"{holidays} leave days on a plant holiday (Rule 17)"


def test_leave_days_recompute_matches_ranges(staging_built) -> None:
    """Rule 17 re-implemented independently: ranges minus Sundays minus plant
    holidays must equal staging.leave_days exactly (days_requested is never
    trusted - FR-014)."""
    import pandas as pd

    req = db.read_sql(
        "SELECT request_id, date_from, date_to, plant "
        "FROM staging.leave_requests WHERE is_counted = 1"
    )
    hol = db.read_sql("SELECT holiday_date, scope FROM staging.holidays")
    days = db.read_sql("SELECT request_id, day_date FROM staging.leave_days")
    h_by_scope = hol.groupby("scope")["holiday_date"].apply(set).to_dict()

    expected: set[tuple[str, str]] = set()
    for r in req.itertuples():
        code = PLANT_CODE.get(str(r.plant).strip())
        plant_hol = h_by_scope.get("ALL", set()) | h_by_scope.get(code, set())
        for d in pd.date_range(r.date_from, r.date_to):
            if d.weekday() == 6:
                continue
            ds = d.strftime("%Y-%m-%d")
            if ds in plant_hol:
                continue
            expected.add((r.request_id, ds))

    actual = set(zip(days["request_id"], days["day_date"]))
    assert expected == actual, (
        f"leave_days mismatch: missing={len(expected - actual)}, "
        f"extra={len(actual - expected)}"
    )


# ----------------------------------------------------------- overtime/payroll
def test_overtime_payroll_typing(staging_built) -> None:
    bad = _scalar(
        "SELECT COUNT(*) FROM staging.overtime_requests "
        "WHERE status NOT IN ('Approved', 'Rejected', 'Pending') "
        "OR ot_date NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'"
    )
    assert bad == 0, f"{bad} badly typed overtime rows"
    bad_pay = _scalar(
        "SELECT COUNT(*) FROM staging.payroll_lines "
        "WHERE component_type NOT IN ('EARNING', 'DEDUCTION') "
        "OR payroll_month NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]'"
    )
    assert bad_pay == 0, f"{bad_pay} badly typed payroll lines"
    units_wrong = _scalar(
        "SELECT COUNT(*) FROM staging.payroll_lines "
        "WHERE units IS NOT NULL AND component NOT IN "
        "('OVERTIME', 'ABSENCE_DEDUCTION')"
    )
    assert units_wrong == 0, "units present on a component that has none"


# -------------------------------------------------------------- reconciliation
def test_full_reconciliation(staging_built) -> None:
    rows = qc.reconciliation_report()
    bad = [r for r in rows if not r["ok"]]
    assert not bad, f"raw != staging + rejected for: {bad}"
    steps = qc.steps_reconciliation()
    assert steps["ok"], f"leave approval steps mismatch: {steps}"


# ------------------------------------------------------- attendance (T029, SC-004)
def _att_failed(*names: str) -> list[dict]:
    checks = {c["check"]: c for c in qc.attendance_checks()}
    return [checks[n] for n in names if not checks[n]["ok"]]


def test_attendance_grain_and_status_domain(staging_built) -> None:
    failed = _att_failed("one_row_per_emp_day", "status_in_domain")
    assert not failed, failed


def test_attendance_measures_valid(staging_built) -> None:
    failed = _att_failed("non_negative_measures", "ot_half_hour_multiples",
                         "no_shift_over_16h")
    assert not failed, failed


def test_attendance_status_punch_consistency(staging_built) -> None:
    failed = _att_failed("status_punches_consistent",
                         "ot_and_lateness_only_on_present")
    assert not failed, failed
