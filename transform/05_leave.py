"""T021 - Stage 2.5: leave (Rules 16, 17; FR-013/014).

- header flattening: nested `employee` / `leave` JSON objects -> columns.
- approval steps: the `approvals` array -> one row per (request, step).
- `is_counted` (Rule 16): exactly two approval steps, both `Approved`
  (Manager then HR), and `cancelled_at` empty. `days_requested` is recorded
  but NEVER used for counting (employee-typed calendar days).
- `leave_days` (Rule 17): every day of a counted request's from-to range,
  minus Sundays and minus holidays applying to the employee's plant
  (scope ALL or the plant's scope code).
"""

from __future__ import annotations

import json

import pandas as pd

from common import db
from config import PLANT_CODE
from transform.util import iso_series, print_counts, replace_rows, to_int

REQ_COLS = ["request_id", "emp_id", "plant", "leave_type", "date_from",
            "date_to", "days_requested_raw", "submitted_at", "cancelled_at",
            "is_counted", "reject_reason"]
STEP_COLS = ["request_id", "step", "approver_role", "approver_id", "action",
             "acted_at"]
DAY_COLS = ["request_id", "emp_id", "day_date", "leave_type"]


def main() -> dict:
    raw = db.read_sql(
        "SELECT request_id, employee, leave, submitted_at, approvals, "
        "cancelled_at FROM raw.leave_requests"
    )

    # ---- header + steps flattening -------------------------------------------
    req_rows, step_rows = [], []
    for r in raw.itertuples(index=False, name=None):
        request_id, employee, leave, submitted_at, approvals, cancelled_at = r
        emp = json.loads(employee)
        lv = json.loads(leave)
        steps = json.loads(approvals)
        for s in steps:
            step_rows.append({
                "request_id": request_id,
                "step": int(s["step"]),
                "approver_role": s.get("approver_role"),
                "approver_id": s.get("approver_id"),
                "action": s.get("action"),
                "acted_at": s.get("acted_at"),
            })
        n_steps = len(steps)
        approved = sum(1 for s in steps if s.get("action") == "Approved")
        cancelled = str(cancelled_at or "").strip()
        counted = (n_steps == 2 and approved == 2 and not cancelled)
        if counted:
            reason = None
        elif cancelled:
            reason = "cancelled"
        elif n_steps != 2:
            reason = "incomplete_approval_chain"
        else:
            reason = "approval_rejected"
        req_rows.append({
            "request_id": request_id,
            "emp_id": emp.get("emp_id"),
            "plant": emp.get("plant"),
            "leave_type": lv.get("type"),
            "date_from": lv.get("from"),
            "date_to": lv.get("to"),
            "days_requested_raw": to_int(lv.get("days_requested")),
            "submitted_at": submitted_at or None,
            "cancelled_at": cancelled or None,
            "is_counted": int(counted),
            "reject_reason": reason,
        })

    req = pd.DataFrame(req_rows, columns=REQ_COLS)
    steps = pd.DataFrame(step_rows, columns=STEP_COLS)

    for col in ("date_from", "date_to"):
        req[col], bad = iso_series(req[col])
        assert bad == 0, f"{bad} unparseable {col} in leave_requests"

    # ---- Rule 17: expand counted ranges, drop Sundays + plant holidays -------
    hol = db.read_sql("SELECT holiday_date, scope FROM staging.holidays")
    holidays_by_scope: dict[str, set[str]] = hol.groupby("scope")["holiday_date"].apply(set).to_dict()

    day_rows = []
    for r in req[req["is_counted"] == 1].itertuples():
        plant_code = PLANT_CODE.get(str(r.plant).strip(), None)
        skipped_hol = holidays_by_scope.get("ALL", set()) | (
            holidays_by_scope.get(plant_code, set()) if plant_code else set()
        )
        for d in pd.date_range(r.date_from, r.date_to):
            ds = d.strftime("%Y-%m-%d")
            if d.weekday() == 6:      # Sunday has its own Rule-12 status
                continue
            if ds in skipped_hol:     # plant holiday has its own status
                continue
            day_rows.append({
                "request_id": r.request_id, "emp_id": r.emp_id,
                "day_date": ds, "leave_type": r.leave_type,
            })

    leave_days = pd.DataFrame(day_rows, columns=DAY_COLS)

    n_req = replace_rows(req, "staging.leave_requests")
    n_steps = replace_rows(steps, "staging.leave_approval_steps")
    n_days = replace_rows(leave_days, "staging.leave_days")

    stats = {
        "requests": n_req,
        "counted": int(req["is_counted"].sum()),
        "steps": n_steps,
        "leave_days": n_days,
        "sundays_or_holidays_skipped": int(
            sum(
                (pd.date_range(r.date_from, r.date_to).size)
                for r in req[req["is_counted"] == 1].itertuples()
            )
            - n_days
        ),
    }
    print_counts("05_leave", stats)
    return stats


if __name__ == "__main__":
    main()
