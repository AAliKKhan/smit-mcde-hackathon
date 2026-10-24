"""T016 - Stage 2.2: employment history SCD2 recompute (Rule 2; FR-008).

`effective_to` in the export is unreliable. A record is valid from its
`effective_from` until the day BEFORE the employee's next record starts;
the latest record never ends.

- recomputed `effective_to` written to staging, original kept in `raw_effective_to`
  (forensics, Principle III: raw is immutable anyway).
- every employee whose raw `effective_to` overlaps or gaps against the next
  record is listed in docs/history_repairs.md (the case-study "37 employees").
"""

from __future__ import annotations

import pandas as pd

from config import DOCS_DIR
from common import db
from transform.util import iso_series, print_counts, replace_rows, to_float

STAGING_COLS = [
    "record_id", "emp_id", "effective_from", "effective_to", "raw_effective_to",
    "dept_id", "designation", "grade", "basic_salary", "change_reason",
    "is_latest",
]


def main() -> dict:
    raw = db.read_sql(
        "SELECT emp_id, effective_from, effective_to, dept_id, designation, "
        "       grade, basic_salary, change_reason, _row_hash "
        "FROM raw.employment_history"
    )

    raw["effective_from"], bad_from = iso_series(raw["effective_from"])
    assert bad_from == 0, f"{bad_from} unparseable effective_from"
    raw["raw_effective_to"] = raw["effective_to"].map(
        lambda v: str(v).strip() or None
    )
    # deterministic order inside employee (ties resolved by content hash)
    raw = raw.sort_values(
        ["emp_id", "effective_from", "change_reason", "_row_hash"],
        kind="mergesort",
    ).reset_index(drop=True)

    # ---- Rule 2: valid_to = next.effective_from - 1 day (latest -> NULL) -----
    nxt = raw.groupby("emp_id")["effective_from"].shift(-1)
    nxt_dt = pd.to_datetime(nxt, errors="coerce")
    valid_to = nxt_dt - pd.Timedelta(days=1)
    raw["effective_to"] = valid_to.dt.strftime("%Y-%m-%d").where(valid_to.notna(), None)
    raw["is_latest"] = nxt.isna().astype(int)

    # ---- overlap/gap forensics on the RAW values (the 37 employees) ---------
    raw_dt_to = pd.to_datetime(raw["raw_effective_to"], errors="coerce")
    overlap = raw_dt_to.notna() & nxt_dt.notna() & (raw_dt_to >= nxt_dt)
    gap = raw_dt_to.notna() & nxt_dt.notna() & (raw_dt_to < nxt_dt - pd.Timedelta(days=1))
    flagged = raw[overlap | gap].copy()
    flagged["issue"] = "gap before next record"
    flagged.loc[overlap[overlap | gap].index, "issue"] = "overlap with next record"

    emps = sorted(flagged["emp_id"].unique())
    lines = [
        "# History repair log (Rule 2)",
        "",
        f"Raw `effective_to` disagrees with the recomputed "
        f"next.effective_from - 1 day for **{len(emps)} employees** "
        f"({int(overlap.sum())} overlap rows, {int(gap.sum())} gap rows).",
        "",
        "| emp_id | issue | raw effective_to | next effective_from | recomputed valid_to |",
        "|---|---|---|---|---|",
    ]
    for i in flagged.sort_values(["emp_id", "effective_from"]).index:
        r = flagged.loc[i]
        lines.append(
            f"| {r['emp_id']} | {r['issue']} | {r['raw_effective_to']} "
            f"| {nxt.loc[i]} | {r['effective_to'] or '(latest)'} |"
        )
    out_path = DOCS_DIR / "history_repairs.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- assemble staging ----------------------------------------------------
    raw["basic_salary"] = raw["basic_salary"].map(to_float)
    raw["record_id"] = range(1, len(raw) + 1)
    out = raw[STAGING_COLS]
    n = replace_rows(out, "staging.employment_history")

    stats = {
        "raw_rows": len(raw),
        "staging_rows": n,
        "flagged_emps": len(emps),
        "overlap_rows": int(overlap.sum()),
        "gap_rows": int(gap.sum()),
        "latest_rows": int(raw["is_latest"].sum()),
    }
    print_counts("02_clean_history", stats)
    print(f"  history repairs written: {out_path}")
    return stats


if __name__ == "__main__":
    main()
