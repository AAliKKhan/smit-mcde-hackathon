"""T050 - run every DQ family and write results to main.dq_results (FR-045).

Families and their FR mapping:
  PK uniqueness / NOT NULL ......... FR-046  (checks.pk_checks)
  Referential integrity fact->dim .. FR-047  (checks.warehouse_checks: fk)
  Reconciliation raw = staging ..... FR-048  (checks.reconciliation_report +
                                    steps_reconciliation + fact/staging parity)
  Accepted values .................. FR-049  (attendance status Rule 12 +
                                    checks.accepted_value_checks)
  Business sanity .................. FR-050  (negative hours, >16h shifts,
                                    SCD2 overlap/contiguity)

The table always holds the LATEST run (previous rows are replaced). Columns
follow warehouse/ddl/00_schemas.sql: run_id, check_id, layer, target,
status, failure_count, detail, checked_at.

Run:  python -m quality.run_dq      (exit 1 if any check FAILs)
Wire: run_pipeline.py calls run_dq.run() after every stage load (T052).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from common import db
from quality import checks as qc
from warehouse.ddl.apply import apply as apply_ddl

# dq_results.layer CHECK allows: raw, staging, warehouse, reconciliation, sanity
_WAREHOUSE_LAYER = {
    "foreign_key_integrity": "warehouse",
    "scd2_no_overlap": "sanity",
    "scd2_contiguous": "sanity",
    "scd2_one_current_per_emp": "warehouse",
    "dim_date_covers_window": "warehouse",
    "fact_row_parity": "reconciliation",
    "status_distribution_parity": "reconciliation",
    "payroll_month_end_dept_present": "warehouse",
}
_SANITY_ATTENDANCE = {
    "non_negative_measures", "ot_half_hour_multiples", "no_shift_over_16h",
    "status_punches_consistent", "ot_and_lateness_only_on_present",
}


def collect() -> list[dict]:
    """Run every family -> [{check_id, layer, target, status,
    failure_count, detail}]."""
    rows: list[dict] = []

    def add(check_id: str, layer: str, target: str, ok: bool,
            failures: int, detail: str) -> None:
        rows.append({
            "check_id": check_id,
            "layer": layer,
            "target": target,
            "status": "PASS" if ok else "FAIL",
            "failure_count": int(failures),
            "detail": detail,
        })

    # FR-048: raw = staging + rejected (+ leave approval steps)
    for r in qc.reconciliation_report():
        gap = abs(r["raw"] - r["accounted"])
        add(f"recon_{r['table']}", "reconciliation", f"raw.{r['table']}",
            r["ok"], 0 if r["ok"] else gap,
            f"raw={r['raw']}, staged={r['staged']}, rejected={r['rejected']}, "
            f"extra={r['extra']}; {r['note']}".strip("; "))
    steps = qc.steps_reconciliation()
    add("recon_leave_approval_steps", "reconciliation",
        "staging.leave_approval_steps", steps["ok"],
        abs(steps["raw_steps"] - steps["staged_steps"]),
        f"raw={steps['raw_steps']}, staged={steps['staged_steps']}")

    # FR-049 (status) + FR-045 sanity from the attendance family
    for c in qc.attendance_checks():
        # 5 of the 7 are business-sanity; grain + status domain are staging
        layer = "sanity" if c["check"] in _SANITY_ATTENDANCE else "staging"
        add(c["check"], layer, "staging.attendance_daily",
            c["ok"], c["violations"], c["note"])

    # FR-047 RI + FR-050 SCD2 + staging<->warehouse parity
    for c in qc.warehouse_checks():
        layer = _WAREHOUSE_LAYER.get(c["check"], "warehouse")
        add(c["check"], layer, "db/warehouse.db", c["ok"], c["violations"],
            c["note"])

    # FR-046 keys
    for c in qc.pk_checks():
        schema = c["target"].split(".")[0]
        add(c["check"], schema, c["target"], c["ok"], c["violations"],
            c["note"])

    # FR-049 domains (leave type, pay components)
    for c in qc.accepted_value_checks():
        add(c["check"], "staging", c["target"], c["ok"], c["violations"],
            c["note"])
    return rows


def run() -> dict:
    """Collect all checks, replace dq_results, print a summary."""
    apply_ddl()  # ensures main.dq_results exists (00_schemas.sql)
    rows = collect()
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    now = datetime.now().isoformat(timespec="seconds")

    c = db.conn()
    try:
        c.execute("DELETE FROM dq_results")
        c.executemany(
            "INSERT INTO dq_results (run_id, check_id, layer, target, status, "
            "failure_count, detail, checked_at) VALUES (?,?,?,?,?,?,?,?)",
            [(run_id, r["check_id"], r["layer"], r["target"], r["status"],
              r["failure_count"], r["detail"], now) for r in rows],
        )
        c.commit()
    finally:
        c.close()

    failed = [r for r in rows if r["status"] == "FAIL"]
    for r in rows:
        if r["status"] == "FAIL":
            print(f"  FAIL  [{r['layer']:<15}] {r['check_id']:<32} "
                  f"failures={r['failure_count']:<7,} {r['detail']}")
    print(f"\ndq_results: run {run_id} - {len(rows)} checks, "
          f"{len(rows) - len(failed)} PASS, {len(failed)} FAIL")
    return {"run_id": run_id, "total": len(rows), "failed": len(failed),
            "rows": rows}


def main() -> int:
    res = run()
    return 1 if res["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
