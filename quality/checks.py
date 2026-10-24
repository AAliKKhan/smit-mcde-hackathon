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
    bad = [r for r in rows if not r["ok"]]
    if bad or not steps["ok"]:
        print(f"\nRECONCILIATION FAILED: {len(bad)} table(s)")
        return 1
    print("\nreconciliation OK: raw = staging + rejected for every table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
