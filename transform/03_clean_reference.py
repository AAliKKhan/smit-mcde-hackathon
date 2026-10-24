"""T017 - Stage 2.3: reference data (Rules 5, 6; FR-015).

- departments  : canonical list incl. the 2 renames (`previous_name`).
- shifts       : shifts.json -> typed table (`crosses_midnight` -> 0/1).
- device_mapping / holidays: typed copies (holidays keep scope codes).
- shift_roster : full employee x week grid over the export span.
  * observed week            -> as exported (is_gap_filled = 0)
  * missing week after first -> previous week's shift (Rule 6, forward-fill)
  * missing week before first-> Rule 5 default (Head Office/manager -> GEN,
    plant worker -> DAY) - deterministic fallback, see docs/profile_notes.md
"""

from __future__ import annotations

import pandas as pd

from common import db
from transform.util import iso_series, print_counts, replace_rows, to_int

ROSTER_COLS = ["emp_id", "week_start", "shift_code", "is_gap_filled"]


def _to_bool01(v) -> int:
    return 1 if str(v).strip().lower() in {"true", "1", "yes"} else 0


def default_shift(plant: str, designation: str) -> str:
    """Rule 5: Head Office and managers work GEN; plant workers start on DAY."""
    if str(plant).strip() == "Head Office":
        return "GEN"
    if "manager" in str(designation).strip().lower():
        return "GEN"
    return "DAY"


def build_roster() -> tuple[pd.DataFrame, dict]:
    ros = db.read_sql(
        "SELECT emp_id, week_start, shift_code FROM raw.shift_roster"
    )
    emps = db.read_sql(
        "SELECT emp_id, plant, designation FROM staging.employees"
    )
    assert len(emps) > 0, "staging.employees empty - run transform/01_clean_employees.py first"
    all_weeks = sorted(ros["week_start"].unique())
    grid = pd.date_range(all_weeks[0], all_weeks[-1], freq="7D")
    grid = [ts.strftime("%Y-%m-%d") for ts in grid]

    observed: dict[str, dict[str, str]] = {}
    for e, w, s in zip(ros["emp_id"], ros["week_start"], ros["shift_code"]):
        observed.setdefault(e, {})[w] = s

    rows = []
    filled = 0
    defaults = 0
    for r in emps.itertuples():
        obs = observed.get(r.emp_id, {})
        last: str | None = None
        for w in grid:
            if w in obs:
                code, flag = obs[w], 0
                last = code
            elif last is not None:
                code, flag = last, 1        # Rule 6 forward-fill
                filled += 1
            else:
                code = default_shift(r.plant, r.designation)  # Rule 5
                flag = 1
                filled += 1
                defaults += 1
            rows.append({"emp_id": r.emp_id, "week_start": w,
                         "shift_code": code, "is_gap_filled": flag})

    df = pd.DataFrame(rows, columns=ROSTER_COLS)
    return df, {"grid_weeks": len(grid), "gap_filled": filled, "rule5_defaults": defaults}


def main() -> dict:
    # ---- prepare every frame first ------------------------------------------
    roster, rstats = build_roster()

    dep = db.read_sql(
        "SELECT dept_id, dept_name, plant, cost_center, previous_name, "
        "renamed_on FROM raw.departments"
    )
    for col in ("previous_name", "renamed_on"):
        dep[col] = dep[col].map(lambda v: str(v).strip() or None)

    shifts = db.read_sql(
        "SELECT shift_code, name, start_time, end_time, crosses_midnight, "
        "grace_minutes, applies_to FROM raw.shifts"
    )
    shifts["crosses_midnight"] = shifts["crosses_midnight"].map(_to_bool01)
    shifts["grace_minutes"] = shifts["grace_minutes"].map(to_int)

    dev = db.read_sql(
        "SELECT device_id, device_user_id, emp_id, enrolled_on FROM raw.device_mapping"
    )

    hol = db.read_sql(
        "SELECT holiday_date, scope, holiday_name FROM raw.holidays"
    )
    hol["holiday_date"], bad = iso_series(hol["holiday_date"])
    assert bad == 0, "unparseable holiday_date"

    # ---- FK-safe write order: staging.shift_roster REFERENCES shifts, so the
    # child rows must be cleared before shifts can be rebuilt, and only then
    # re-inserted (SQLite enforces FKs on both DELETE and INSERT).
    db.execute("DELETE FROM staging.shift_roster")
    n_shifts = replace_rows(shifts, "staging.shifts")
    n_ros = replace_rows(roster, "staging.shift_roster")

    n_dep = replace_rows(dep, "staging.departments")
    n_dev = replace_rows(dev, "staging.device_mapping")
    n_hol = replace_rows(hol, "staging.holidays")

    stats = {
        "roster_rows": n_ros, "departments": n_dep, "shifts": n_shifts,
        "device_mapping": n_dev, "holidays": n_hol, **rstats,
    }
    print_counts("03_clean_reference", stats)
    return stats


if __name__ == "__main__":
    main()
