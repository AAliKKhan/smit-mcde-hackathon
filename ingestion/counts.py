"""Gate R: verify raw row counts against the case-study contract (T011, FR-004).

Compares actual raw.<table> counts with config.EXPECTED_COUNTS and checks the
load metadata columns are present and non-null (SC-001).

Usage: python -m ingestion.counts   (exit 0 = Gate R counts green, 1 = failure)
"""

from __future__ import annotations

import sys

from config import EXPECTED_COUNTS
from common import db


def check(expected: dict[str, int] | None = None) -> list[dict]:
    exp = expected or EXPECTED_COUNTS
    rows: list[dict] = []
    with db.conn() as conn:
        for table, want in sorted(exp.items()):
            got = conn.execute(f"SELECT COUNT(*) FROM raw.{table}").fetchone()[0]
            meta_bad = conn.execute(
                f"""SELECT COUNT(*) FROM raw.{table}
                    WHERE _source_file IS NULL OR _loaded_at IS NULL
                       OR _row_hash IS NULL OR _row_hash = ''"""
            ).fetchone()[0]
            rows.append(
                {
                    "table": table,
                    "expected": want,
                    "actual": got,
                    "count_ok": got == want,
                    "meta_null_rows": meta_bad,
                    "meta_ok": meta_bad == 0,
                }
            )
    return rows


def main() -> int:
    rows = check()
    failures = 0
    print(f"{'table':<24}{'expected':>10}{'actual':>10}  status")
    for r in rows:
        ok = r["count_ok"] and r["meta_ok"]
        if not ok:
            failures += 1
        flag = "OK" if ok else "FAIL"
        extra = "" if r["meta_ok"] else f"  (null metadata rows: {r['meta_null_rows']})"
        print(f"{r['table']:<24}{r['expected']:>10}{r['actual']:>10}  {flag}{extra}")

    total_exp = sum(x["expected"] for x in rows)
    total_ok = sum(x["actual"] for x in rows)
    print(f"{'TOTAL':<24}{total_exp:>10}{total_ok:>10}")
    if failures:
        print(f"GATE R: FAIL ({failures} table(s))")
        return 1
    print("GATE R: PASS (all raw counts + load metadata verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
