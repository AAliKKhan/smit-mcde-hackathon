"""T037 - run every analytics/q*.sql against the warehouse, export CSVs.

Discovers `analytics/q*.sql` (sorted), executes each file as one standalone
statement (FR-031), writes `analytics/results/<stem>.csv` (FR-033) and prints
row counts. Exits non-zero if a query fails or returns no rows, so Gate Q
can rely on the exit code.

Run:  python -m analytics.run_all             # all queries
      python -m analytics.run_all q05 q07     # only the given stems
"""

from __future__ import annotations

import sys
from pathlib import Path

from common import db

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"


def run(stems: list[str] | None = None) -> int:
    files = sorted(HERE.glob("q*.sql"))
    if stems:
        wanted = set(stems)
        files = [f for f in files if f.stem in wanted]
    if not files:
        print("no analytics/q*.sql files found")
        return 1
    RESULTS.mkdir(exist_ok=True)

    failed: list[str] = []
    for f in files:
        sql = f.read_text(encoding="utf-8")
        try:
            df = db.read_sql(sql)
        except Exception as exc:  # pragma: no cover - surfaced as exit code
            print(f"  FAIL {f.name}: {exc}")
            failed.append(f.stem)
            continue
        out = RESULTS / f"{f.stem}.csv"
        df.to_csv(out, index=False, encoding="utf-8")
        note = "" if len(df) else "  [EMPTY]"
        print(f"  {f.name:<48} rows={len(df):>6,} -> results/{f.stem}.csv{note}")
        if not len(df):
            failed.append(f.stem)

    print(f"\n{len(files) - len(failed)}/{len(files)} queries OK")
    if failed:
        print(f"failed: {', '.join(failed)}")
    return 1 if failed else 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    return run(args or None)


if __name__ == "__main__":
    raise SystemExit(main())
