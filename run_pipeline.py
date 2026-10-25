"""One-command rebuild: Stages 1 -> 6 (T052, FR-051). Safe to re-run -
every stage is idempotent (Principle IV), so a stale or partial `db/`
always converges to the same result.

    python run_pipeline.py              # full rebuild
    python run_pipeline.py --stage 4    # run only stage 4

Stages (plan.md / quickstart.md order):
  1  ingestion.load_raw         raw files -> raw.* + counts gate (Gate R)
  2  transform STAGE2           clean + reference + punches + leave + OT/pay
  3  transform STAGE3           attendance_daily (Gates S + A)
  4  warehouse.build_warehouse  star schema + FK check (Gate W)
  5  analytics.run_all          q01..q10 -> analytics/results/*.csv (Gate Q)
  6  quality.run_dq             every DQ family -> dq_results (Gate D)

quality.run_dq runs after EVERY stage (T050): intermediate runs are
advisory (layers not built yet trivially pass; stage 1 flags
staging-not-yet-loaded as a warning), while the stage-6 run is strict and
its failure count decides the exit code. A raised exception or a failed
analytics run also exits non-zero. Timing summary printed at the end.

Run: python run_pipeline.py [--stage N]
"""

from __future__ import annotations

import argparse
import time

from quality import run_dq as dq


def stage_1() -> int:
    from ingestion import counts, load_raw
    rc = load_raw.main()
    return rc or counts.main()  # Gate R: expected row counts per file


def stage_2() -> int:
    from transform import build
    build.run(build.STAGE2)
    return 0


def stage_3() -> int:
    from transform import build
    build.run(build.STAGE3)
    return 0


def stage_4() -> int:
    from warehouse import build_warehouse
    build_warehouse.main()
    return 0


def stage_5() -> int:
    from analytics import run_all
    return run_all.run()


def stage_6() -> int:
    res = dq.run()
    return 1 if res["failed"] else 0


STAGES: dict[int, tuple[str, callable]] = {
    1: ("raw ingest + counts (Gate R)", stage_1),
    2: ("cleaning transforms", stage_2),
    3: ("attendance daily (Gates S+A)", stage_3),
    4: ("warehouse star schema (Gate W)", stage_4),
    5: ("analytics q01-q10 (Gate Q)", stage_5),
    6: ("data quality -> dq_results (Gate D)", stage_6),
}


def _dq_advisory() -> None:
    """DQ after every stage load (T050) - recorded, not gate-strict."""
    res = dq.run()
    if res["failed"]:
        print(f"  (advisory DQ: {res['failed']} check(s) FAIL - expected "
              "until all stages are loaded)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--stage", type=int, choices=range(1, 7),
                    help="run only this stage (default: all six)")
    args = ap.parse_args()

    order = [args.stage] if args.stage else [1, 2, 3, 4, 5, 6]
    rows: list[tuple[int, str, float, str]] = []
    failed = False
    t_all = time.perf_counter()

    for n in order:
        name, fn = STAGES[n]
        print(f"\n=== Stage {n}: {name} ===")
        t0 = time.perf_counter()
        try:
            rc = fn()
        except Exception as exc:  # noqa: BLE001 - surface and stop the chain
            print(f"Stage {n} FAILED: {exc}")
            rc = 1
        dt = time.perf_counter() - t0
        state = "OK" if rc == 0 else "FAIL"
        rows.append((n, name, dt, state))
        if rc != 0:
            failed = True
            break  # downstream stages depend on this one
        if n != 6:
            _dq_advisory()

    total = time.perf_counter() - t_all
    print("\n" + "=" * 72)
    print(f"{'stage':<6}{'name':<38}{'seconds':>9}  status")
    print("-" * 72)
    for n, name, dt, state in rows:
        print(f"{n:<6}{name:<38}{dt:>9.1f}  {state}")
    print("-" * 72)
    print(f"{'total':<44}{total:>9.1f}  {'FAILED' if failed else 'ALL OK'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
