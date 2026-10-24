"""T025-T028 - Stage 3: staging.attendance_daily (Rules 4, 7, 10, 12-15).

Pipeline (research R9, R10):

1. **day spine** (Rule 4)  : one row per (employee, day) from
   max(hire_date, 2026-04-01) to min(separation_date, 2026-09-30);
   separation_date is the last day worked (inclusive).
2. **pair punches** (Rule 10): staging.punches is already night-attributed
   (Rule 7, shift_date), so first-in/last-out = MIN/MAX per (emp_id, shift_date).
3. **status CASE chain** (Rule 12, exact priority, FR-020):
   Weekly Off -> Holiday -> On Leave -> Present -> Missing Punch -> Absent.
   Literal dictionary text: "Covered by an approved leave -> On Leave" carries
   NO "with no punches" qualifier (unlike Sunday/holiday lines), so leave
   wins even when a stray badge tap exists (753 such days - see
   docs/profile_notes.md); those must not become Missing Punch.
4. **measures** (Rules 13-15):
   - late/early only on Present, only when > 10 min past start / before end;
   - OT on working days = minutes after shift end, floored to half-hours;
   - Sunday/holiday work = (check_out - check_in), floored to half-hours;
   - status CASE + measures are executed as SQL over a temp table so the
     rule text and the code read the same (research R9 "CASE WHEN chain").
"""

from __future__ import annotations

import pandas as pd

from common import db
from config import PLANT_CODE, WINDOW_END, WINDOW_START
from transform.util import bindable, print_counts


def build_spine() -> pd.DataFrame:
    """Employee x day rows clamped to the analysis window (Rule 4)."""
    emp = db.read_sql(
        "SELECT emp_id, plant, dept_id, hire_date, separation_date "
        "FROM staging.employees"
    )
    rows = []
    for r in emp.itertuples():
        start = max(str(r.hire_date), WINDOW_START.isoformat())
        sep = r.separation_date
        sep_s = "" if pd.isna(sep) else str(sep)
        end = min(sep_s or WINDOW_END.isoformat(), WINDOW_END.isoformat())
        if start > end:
            continue
        for d in pd.date_range(start, end):
            rows.append((r.emp_id, d.strftime("%Y-%m-%d"), r.plant, r.dept_id))
    spine = pd.DataFrame(rows, columns=["emp_id", "work_date", "plant", "dept_id"])
    return spine


def enrich(spine: pd.DataFrame) -> pd.DataFrame:
    # ---- shift + shift-window timestamps ------------------------------------
    mon = pd.to_datetime(spine["work_date"]) - pd.to_timedelta(
        pd.to_datetime(spine["work_date"]).dt.weekday, unit="D"
    )
    spine["_week"] = mon.dt.strftime("%Y-%m-%d")

    roster = db.read_sql(
        "SELECT emp_id, week_start, shift_code FROM staging.shift_roster"
    ).rename(columns={"week_start": "_week"})
    spine = spine.merge(roster, on=["emp_id", "_week"], how="left")
    assert spine["shift_code"].notna().all(), "spine day without roster shift"

    shifts = db.read_sql(
        "SELECT shift_code, start_time, end_time, crosses_midnight FROM staging.shifts"
    )
    spine = spine.merge(shifts, on="shift_code", how="left")
    wd = pd.to_datetime(spine["work_date"])
    spine["start_ts"] = (
        wd + pd.to_timedelta(spine["start_time"].str.slice(0, 5) + ":00")
    ).dt.strftime("%Y-%m-%d %H:%M:%S")
    end_day = wd + pd.to_timedelta(spine["crosses_midnight"].astype(int), unit="D")
    spine["end_ts"] = (
        end_day + pd.to_timedelta(spine["end_time"].str.slice(0, 5) + ":00")
    ).dt.strftime("%Y-%m-%d %H:%M:%S")
    spine["is_sunday"] = (pd.to_datetime(spine["work_date"]).dt.weekday == 6).astype(int)

    # ---- plant holidays (scope ALL + plant code) ----------------------------
    hol = db.read_sql("SELECT holiday_date, scope FROM staging.holidays")
    all_dates = set(hol.loc[hol["scope"] == "ALL", "holiday_date"])
    scoped = {
        (scope, day)
        for scope, day in zip(hol["scope"], hol["holiday_date"])
        if scope != "ALL"
    }
    codes = spine["plant"].map(PLANT_CODE)
    spine["is_holiday"] = [
        int(d in all_dates or (c, d) in scoped)
        for c, d in zip(codes, spine["work_date"])
    ]

    # ---- approved leave coverage (counted requests only, Rule 16) -----------
    leave = db.read_sql("SELECT emp_id, day_date FROM staging.leave_days")
    leave_keys = set(zip(leave["emp_id"], leave["day_date"]))
    spine["on_leave"] = [
        int((e, d) in leave_keys)
        for e, d in zip(spine["emp_id"], spine["work_date"])
    ]

    # ---- punch pairing (Rule 10: first in / last out per shift date) ---------
    punches = db.read_sql(
        "SELECT emp_id, shift_date, COUNT(*) AS punches, "
        "MIN(punch_time) AS check_in, MAX(punch_time) AS check_out "
        "FROM staging.punches GROUP BY emp_id, shift_date"
    ).rename(columns={"shift_date": "work_date"})
    spine = spine.merge(punches, on=["emp_id", "work_date"], how="left")
    spine["punches"] = spine["punches"].fillna(0).astype(int)
    spine["check_in"] = spine["check_in"].where(spine["check_in"].notna(), None)
    spine["check_out"] = spine["check_out"].where(spine["check_out"].notna(), None)

    # ---- department as-of day (SCD2 join, Rule 2/3) -------------------------
    hist = db.read_sql(
        "SELECT emp_id, effective_from, dept_id FROM staging.employment_history "
        "ORDER BY emp_id, effective_from"
    )
    spine["_wd"] = pd.to_datetime(spine["work_date"])
    hist["_ef"] = pd.to_datetime(hist["effective_from"])
    # merge_asof (pandas 3.x) requires a globally monotonic on-key even with by=;
    # matches stay inside the by-group, so sort on key first, emp second.
    spine = spine.sort_values(["_wd", "emp_id"]).reset_index(drop=True)
    hist = hist.sort_values(["_ef", "emp_id"]).reset_index(drop=True)
    spine = pd.merge_asof(
        spine, hist,
        left_on="_wd", right_on="_ef",
        by="emp_id", direction="backward",
    )
    spine["dept_id"] = spine["dept_id_y"].fillna(spine["dept_id_x"])
    spine = spine.drop(
        columns=["dept_id_x", "dept_id_y", "effective_from", "_week", "_wd", "_ef"]
    )

    spine["is_working_day"] = (
        (spine["is_sunday"] == 0) & (spine["is_holiday"] == 0)
    ).astype(int)
    return spine


STATUS_AND_MEASURES_SQL = """
INSERT INTO staging.attendance_daily (
  emp_id, work_date, plant, dept_id, shift_code, check_in, check_out,
  status, punches_count, worked_hours, late_minutes, early_leave_minutes,
  ot_hours, is_working_day
)
SELECT emp_id, work_date, plant, dept_id, shift_code, check_in, check_out,
  status,
  punches,
  -- worked hours (Rule 10 span; 0 when one side missing)
  CASE WHEN check_in IS NOT NULL AND check_out IS NOT NULL
       THEN ROUND((julianday(check_out) - julianday(check_in)) * 24.0, 2)
       ELSE 0 END,
  -- late arrival: > 10 min after shift start (Rule 13), Present only
  CASE WHEN status = 'Present'
         AND (julianday(check_in) - julianday(start_ts)) * 1440.0 > 10
       THEN CAST(ROUND((julianday(check_in) - julianday(start_ts)) * 1440.0, 0) AS INTEGER)
       ELSE 0 END,
  -- early departure: > 10 min before shift end (Rule 13), Present only
  CASE WHEN status = 'Present'
         AND (julianday(end_ts) - julianday(check_out)) * 1440.0 > 10
       THEN CAST(ROUND((julianday(end_ts) - julianday(check_out)) * 1440.0, 0) AS INTEGER)
       ELSE 0 END,
  -- overtime (Rules 14/15): working day = minutes after shift end;
  -- Sunday/holiday worked = the whole span; floored to whole half-hours
  CASE
    WHEN status = 'Present' AND is_working_day = 0
      THEN CAST(ROUND(MAX(0.0, (julianday(check_out) - julianday(check_in)) * 1440.0), 6)
                / 30 AS INTEGER) * 0.5
    WHEN status = 'Present' AND is_working_day = 1
      THEN CAST(ROUND(MAX(0.0, (julianday(check_out) - julianday(end_ts)) * 1440.0), 6)
                / 30 AS INTEGER) * 0.5
    ELSE 0
  END,
  CASE WHEN is_sunday = 1 OR is_holiday = 1 THEN 0 ELSE 1 END
FROM att_stat
"""

STATUS_SQL = """
CREATE TEMP TABLE att_stat AS
SELECT *,
  CASE
    WHEN is_sunday = 1 AND punches = 0 THEN 'Weekly Off'   -- Rule 12 (1)
    WHEN is_holiday = 1 AND punches = 0 THEN 'Holiday'     -- Rule 12 (2)
    WHEN on_leave = 1                   THEN 'On Leave'    -- Rule 12 (3)
    WHEN punches >= 2                   THEN 'Present'     -- Rule 12 (4)
    WHEN punches = 1                    THEN 'Missing Punch' -- Rule 12 (5)
    ELSE 'Absent'                                           -- Rule 12 (6)
  END AS status
FROM att_stg
"""

STG_COLS = [
    "emp_id", "work_date", "plant", "dept_id", "shift_code",
    "start_ts", "end_ts", "is_sunday", "is_holiday", "on_leave",
    "punches", "check_in", "check_out", "is_working_day",
]


def main() -> dict:
    spine = enrich(build_spine())
    obj = spine[STG_COLS].astype(object).where(pd.notna(spine[STG_COLS]), None)
    rows = bindable(obj)

    c = db.conn()
    try:
        c.execute("DELETE FROM staging.attendance_daily")
        c.execute("DROP TABLE IF EXISTS temp.att_stat")
        c.execute("DROP TABLE IF EXISTS temp.att_stg")
        c.execute(
            "CREATE TEMP TABLE att_stg ("
            "emp_id TEXT, work_date TEXT, plant TEXT, dept_id TEXT, "
            "shift_code TEXT, start_ts TEXT, end_ts TEXT, is_sunday INTEGER, "
            "is_holiday INTEGER, on_leave INTEGER, punches INTEGER, "
            "check_in TEXT, check_out TEXT, is_working_day INTEGER)"
        )
        c.executemany(
            "INSERT INTO att_stg VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        c.execute(STATUS_SQL)
        c.execute(STATUS_AND_MEASURES_SQL)
        n = c.execute("SELECT COUNT(*) FROM staging.attendance_daily").fetchone()[0]
        c.commit()
    finally:
        c.execute("DROP TABLE IF EXISTS temp.att_stat")
        c.execute("DROP TABLE IF EXISTS temp.att_stg")
        c.close()

    dist = db.read_sql(
        "SELECT status, COUNT(*) AS n FROM staging.attendance_daily "
        "GROUP BY status ORDER BY 2 DESC"
    )
    stats = {"rows": n, "spine_days": len(spine)}
    stats.update({r.status: int(r.n) for r in dist.itertuples()})
    print_counts("07_attendance_daily", stats)
    return stats


if __name__ == "__main__":
    main()
