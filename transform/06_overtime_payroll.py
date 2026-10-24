"""T022 - Stage 2.6: overtime + payroll typing (Rules 19-21) + applications.

- `overtime_requests` -> typed hours (Rule 19: only status='Approved' counts;
  the approved-only view is a query concern, staging keeps every status).
- `payroll_lines`     -> typed `units`/`amount` (Rule 20: OVERTIME units =
  paid hours; Rule 21: cost = sum of EARNING amounts). Deductions are positive
  numbers typed DEDUCTION - sign flipping is never done at staging.
- `applications`      -> flat copy (bonus metric completeness).
"""

from __future__ import annotations

from common import db
from config import COMPONENT_TYPES, PAY_COMPONENTS
from transform.util import iso_series, print_counts, replace_rows, to_float


def main() -> dict:
    # ---- overtime (Rule 19) ---------------------------------------------------
    ot = db.read_sql(
        "SELECT request_id, emp_id, ot_date, requested_hours, approved_hours, "
        "status, approver_id, requested_at FROM raw.overtime_requests"
    )
    ot["ot_date"], bad_ot = iso_series(ot["ot_date"])
    assert bad_ot == 0, f"{bad_ot} unparseable ot_date"
    ot["requested_hours"] = ot["requested_hours"].map(to_float)
    ot["approved_hours"] = ot["approved_hours"].map(to_float)
    ot["status"] = ot["status"].map(lambda v: str(v).strip())
    assert set(ot["status"]) <= {"Approved", "Rejected", "Pending"}, (
        f"unexpected OT status: {sorted(set(ot['status']))}"
    )
    n_ot = replace_rows(ot, "staging.overtime_requests")

    # ---- payroll (Rules 20, 21) ----------------------------------------------
    pay = db.read_sql(
        "SELECT line_id, payroll_month, emp_id, component, component_type, "
        "units, amount FROM raw.payroll_lines"
    )
    bad_month = int((~pay["payroll_month"].str.match(r"^\d{4}-\d{2}$")).sum())
    assert bad_month == 0, f"{bad_month} payroll_month not YYYY-MM"
    pay["component"] = pay["component"].map(lambda v: str(v).strip())
    pay["component_type"] = pay["component_type"].map(lambda v: str(v).strip())
    assert set(pay["component_type"]) <= set(COMPONENT_TYPES)
    assert set(pay["component"]) <= set(PAY_COMPONENTS), (
        f"unexpected components: {sorted(set(pay['component']) - set(PAY_COMPONENTS))}"
    )
    pay["units"] = pay["units"].map(to_float)
    pay["amount"] = pay["amount"].map(to_float)
    n_pay = replace_rows(pay, "staging.payroll_lines")

    # ---- applications (bonus) -------------------------------------------------
    app = db.read_sql(
        "SELECT application_id, candidate_id, job_req_id, dept_id, stage, "
        "stage_date FROM raw.applications"
    )
    app["stage_date"], bad_app = iso_series(app["stage_date"])
    assert bad_app == 0, f"{bad_app} unparseable stage_date"
    n_app = replace_rows(app, "staging.applications")

    approved_ot = db.scalar(
        "SELECT COUNT(*) FROM staging.overtime_requests WHERE status = 'Approved'"
    )
    ot_hours_paid = db.scalar(
        "SELECT COALESCE(SUM(units), 0) FROM staging.payroll_lines "
        "WHERE component = 'OVERTIME'"
    )
    stats = {
        "overtime_requests": n_ot,
        "approved_requests": int(approved_ot),
        "payroll_lines": n_pay,
        "paid_ot_hours": float(ot_hours_paid),
        "applications": n_app,
    }
    print_counts("06_overtime_payroll", stats)
    return stats


if __name__ == "__main__":
    main()
