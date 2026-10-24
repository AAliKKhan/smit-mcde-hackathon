# Contract: `overtime_requests.csv` — Workforce: Overtime

**Rows**: 22,098
**Rules**: 19 (only `status = Approved` counts), 20 (payroll pays from approved requests),
14/15 (computed OT is separate — never conflate)

| Column | Raw type | Notes |
|---|---|---|
| `request_id` | text | `OT000001…`, PK |
| `emp_id` | text | FK → employees |
| `ot_date` | text | ISO — **the shift date** (already night-attributed) |
| `requested_hours` | text | numeric like `2.0` |
| `approved_hours` | text | numeric; may differ from requested |
| `status` | text | Approved / Rejected / Pending (profile exact domain) |
| `approver_id` | text | employee id or desk id |
| `requested_at` | text | ISO timestamp (T-separated) |

**Planted mess**: some approvals exist for days with **no overtime worked** (Q5/Q6 divergence —
the CFO story); pending/rejected rows must not count (Rule 19).

**Validation**: 22,098 rows; `ot_date` within window; status domain profiled; after staging:
approved-only subset feeds `fact_overtime_approved`; `approved_hours >= 0`.
