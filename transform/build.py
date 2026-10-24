"""Stage 2/3 orchestrator: runs the transform modules in dependency order.

    python -m transform.build          # staging up to Stage 2 (01..06)
    python -m transform.build --stage3 # + attendance_daily (07)

Each module exposes main() -> stats dict; modules are idempotent (DELETE +
INSERT), so re-running rebuilds staging from immutable raw (Principle IV).
Modules are loaded via importlib because their filenames start with digits.
"""

from __future__ import annotations

import argparse
import importlib
import time

STAGE2 = [
    "transform.01_clean_employees",
    "transform.02_clean_history",
    "transform.03_clean_reference",
    "transform.04_punches",
    "transform.05_leave",
    "transform.06_overtime_payroll",
]
STAGE3 = [
    "transform.07_attendance_daily",
]


def run(modules: list[str]) -> dict:
    all_stats: dict = {}
    for name in modules:
        t0 = time.perf_counter()
        mod = importlib.import_module(name)
        stats = mod.main()
        all_stats[name] = stats
        print(f"  {name} done in {time.perf_counter() - t0:.1f}s")
    return all_stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage3", action="store_true",
                    help="also build attendance_daily (Stage 3)")
    args = ap.parse_args()

    modules = STAGE2 + (STAGE3 if args.stage3 else [])
    run(modules)
    print(f"\ntransform.build OK ({len(modules)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
