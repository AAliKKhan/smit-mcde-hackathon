"""T015 - Stage 2.1: employees cleaning (Rules 1, 3; FR-006/007).

1. Date normalization: `date_of_birth`, `hire_date`, `separation_date` from the
   three contract formats (YYYY-MM-DD, DD/MM/YYYY, DD-Mon-YYYY) to ISO.
2. Dedupe: same `emp_id` more than once -> keep the row with the latest
   `updated_at` (Rule 1); every dropped row is logged with its `_row_hash`.
3. Department resolution: messy `department` text (casing, spaces, old names)
   -> `dept_id` + canonical `dept_name` via `departments` incl. `previous_name`.

Rebuild is idempotent: staging tables are DELETE + INSERT (Principle IV).
"""

from __future__ import annotations

import pandas as pd

from common import db
from transform.util import iso_series, now_iso, print_counts, replace_rows, to_int

STAGING_COLS = [
    "emp_id", "full_name", "gender", "date_of_birth", "email", "phone",
    "plant", "dept_id", "department", "designation", "grade",
    "employment_type", "hire_date", "separation_date", "status",
    "annual_leave_entitlement", "updated_at",
]
LOG_COLS = ["emp_id", "kept_updated_at", "dropped_updated_at", "dropped_hash",
            "reason", "logged_at"]


def dept_lookup() -> dict[str, tuple[str, str]]:
    """normalized (lower/trimmed) name -> (dept_id, canonical dept_name)."""
    dep = db.read_sql("SELECT dept_id, dept_name, previous_name FROM raw.departments")
    lookup: dict[str, tuple[str, str]] = {}
    for r in dep.itertuples():
        lookup[str(r.dept_name).strip().lower()] = (r.dept_id, r.dept_name)
        prev = str(r.previous_name or "").strip()
        if prev:
            lookup[prev.lower()] = (r.dept_id, r.dept_name)
    return lookup


def normalize_status(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for canonical in ("Active", "Separated"):
        if s.lower() == canonical.lower():
            return canonical
    return s  # surfaced by Gate S status-domain test


def main() -> dict:
    raw = db.read_sql(
        "SELECT emp_id, full_name, gender, date_of_birth, email, phone, plant, "
        "       department, designation, grade, employment_type, hire_date, "
        "       separation_date, status, annual_leave_entitlement, updated_at, "
        "       _row_hash FROM raw.employees"
    )

    # ---- dates (3 mixed formats -> ISO; failures counted, never guessed) ----
    failures = 0
    for col in ("date_of_birth", "hire_date", "separation_date"):
        raw[col], n_bad = iso_series(raw[col])
        failures += n_bad
    assert raw["hire_date"].notna().all(), "unparseable hire_date present"

    # ---- department resolution (Rule 3 + contract: casing/spaces/old names) ----
    lookup = dept_lookup()
    resolved = raw["department"].map(lambda d: lookup.get(str(d).strip().lower()))
    unresolved = int(resolved.isna().sum())
    assert unresolved == 0, (
        f"{unresolved} department strings not resolvable: "
        f"{sorted({d for d, r in zip(raw['department'], resolved) if r is None})[:10]}"
    )
    raw["dept_id"] = resolved.map(lambda x: x[0])
    raw["department"] = resolved.map(lambda x: x[1])

    # ---- Rule 1: keep latest updated_at per emp_id ----------------------------
    raw["_upd"] = pd.to_datetime(raw["updated_at"], errors="coerce")
    raw = raw.sort_values(["emp_id", "_upd", "_row_hash"], kind="mergesort")
    dup_mask = raw.duplicated("emp_id", keep="last")
    kept = raw[~dup_mask].copy()

    now = now_iso()
    log_rows = []
    for r in raw[dup_mask][["emp_id", "updated_at", "_row_hash"]].to_dict("records"):
        keeper = kept.loc[kept.emp_id == r["emp_id"]].iloc[0]
        log_rows.append({
            "emp_id": r["emp_id"],
            "kept_updated_at": keeper["updated_at"],
            "dropped_updated_at": r["updated_at"],
            "dropped_hash": r["_row_hash"],
            "reason": "duplicate emp_id: kept row with latest updated_at (Rule 1)",
            "logged_at": now,
        })

    # ---- assemble staging frame ---------------------------------------------
    kept["status"] = kept["status"].map(normalize_status)
    kept["annual_leave_entitlement"] = kept["annual_leave_entitlement"].map(to_int)
    kept["separation_date"] = kept["separation_date"].map(
        lambda v: v if v else None
    )
    out = kept[STAGING_COLS].copy()

    n_emp = replace_rows(out, "staging.employees")
    n_log = replace_rows(
        pd.DataFrame(log_rows, columns=LOG_COLS), "staging.employees_dedupe_log"
    )
    stats = {
        "raw_rows": len(raw),
        "staging_rows": n_emp,
        "dedupe_logged": n_log,
        "date_failures": failures,
        "dept_resolved": n_emp,
    }
    print_counts("01_clean_employees", stats)
    return stats


if __name__ == "__main__":
    main()
