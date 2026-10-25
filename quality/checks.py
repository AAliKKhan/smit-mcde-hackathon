"""T023 - Reconciliation: raw = staging + rejected, per table.

Used by Gate S tests (tests/test_staging_invariants.py) and by Stage 6 DQ
(FR-045+): every raw row must be accounted for - kept in staging, rejected
with a reason, or (for employees) logged in the dedupe log. shift_roster is
the one table allowed to GAIN rows (Rule 6 gap-fill).

Run: python -m quality.checks   (exit 1 on any imbalance)
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

    bad = [r for r in rows if not r["ok"]]
    if bad or not steps["ok"] or bad_att:
        print(f"\nRECONCILIATION FAILED: {len(bad)} table(s), "
              f"{len(bad_att)} attendance check(s)")
        return 1
    print("\nreconciliation OK: raw = staging + rejected for every table")
    print("attendance invariants OK: SC-004 satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
