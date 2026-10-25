"""Gate D tests (T049-T051): automated DQ proof - every family PASSes on a
clean build (FR-045..FR-050) and a seeded violation flips its dq_results row
to FAIL before cleanup restores PASS (SC-007).

Run: python -m pytest tests/test_dq.py -v
"""

from __future__ import annotations

import pytest

from common import db
from quality import run_dq
from transform import build as build_mod
from warehouse import build_warehouse as wh_build


@pytest.fixture(scope="module")
def built() -> None:
    if db.table_count("staging.attendance_daily") == 0:
        build_mod.run(build_mod.STAGE2 + build_mod.STAGE3)
    if db.table_count("warehouse.fact_attendance_daily") == 0:
        wh_build.main()


def _row(check_id: str) -> dict:
    df = db.read_sql(
        "SELECT status, failure_count, layer, target FROM dq_results "
        "WHERE check_id = :c", {"c": check_id}
    )
    assert len(df) == 1, f"expected exactly one dq_results row for {check_id}"
    return df.iloc[0].to_dict()


def test_all_checks_pass(built) -> None:
    res = run_dq.run()
    assert res["failed"] == 0, [
        r for r in res["rows"] if r["status"] == "FAIL"
    ]
    n = int(db.scalar("SELECT COUNT(*) FROM dq_results") or 0)
    assert n == res["total"] and n >= 50, f"only {n} dq rows written"
    layers = {r["layer"] for r in res["rows"]}
    assert {"reconciliation", "staging", "warehouse", "sanity"} <= layers


def test_seeded_invalid_status_fails_then_passes(built) -> None:
    # baseline: everything green
    assert run_dq.run()["failed"] == 0

    pick = db.read_sql(
        "SELECT emp_id, work_date FROM staging.attendance_daily "
        "WHERE status = 'Absent' LIMIT 1"
    )
    emp_id, work_date = pick.iloc[0]["emp_id"], pick.iloc[0]["work_date"]

    # seed: one invalid status. The DDL CHECK would reject the write, so the
    # seeding connection opts out of CHECK enforcement (the DQ code paths do
    # not - they read whatever is stored).
    c = db.conn()
    try:
        c.execute("PRAGMA ignore_check_constraints = 1")
        c.execute(
            "UPDATE staging.attendance_daily SET status = 'OnVacation' "
            "WHERE emp_id = ? AND work_date = ?",
            (emp_id, work_date),
        )
        c.commit()
    finally:
        c.close()

    res = run_dq.run()
    assert res["failed"] >= 1
    bad = _row("status_in_domain")
    assert bad["status"] == "FAIL" and bad["failure_count"] >= 1

    # cleanup: restore the real status, re-run, everything passes again
    c = db.conn()
    try:
        c.execute(
            "UPDATE staging.attendance_daily SET status = 'Absent' "
            "WHERE emp_id = ? AND work_date = ?",
            (emp_id, work_date),
        )
        c.commit()
    finally:
        c.close()

    res = run_dq.run()
    assert res["failed"] == 0, [
        r for r in res["rows"] if r["status"] == "FAIL"
    ]
    assert _row("status_in_domain")["status"] == "PASS"
