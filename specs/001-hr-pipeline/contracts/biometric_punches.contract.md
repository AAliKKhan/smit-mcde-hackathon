# Contract: `biometric_punches.csv` — Workforce: Biometric Gateway

**Rows**: 345,280
**Rules**: 7 (night attribution), 8 (mapping/rejects), 9 (2-minute dedupe), 10 (first=in, last=out,
single=Missing Punch), 11 (device drift)

| Column | Raw type | Notes |
|---|---|---|
| `punch_id` | text | `P00000001…`, PK in raw |
| `device_id` | text | part of mapping key |
| `device_user_id` | text | part of mapping key |
| `punch_time` | text | `YYYY-MM-DD HH:MM:SS` — raw device local time, **no direction flag** |

**Planted mess** (all must be found & fixed in code):
1. duplicate punches seconds apart (Rule 9 — collapse within 2 min, LAG over `emp_id`)
2. missing check-outs (one punch only → `Missing Punch`)
3. unmapped contractor/visitor IDs → `staging.rejected_punches` with reason (Rule 8)
4. **one device clock running ~1 hour off** → detect via avg first-punch time per device vs
   shift start; correct + document (Rule 11)
5. early-morning **1 Oct check-outs belonging to 30 Sep night shifts** (Rule 7)

**Processing order (must not be reordered)**: map → drift-correct → 2-minute dedupe →
night-date attribution → first/last pairing.
**Validation**: raw count 345,280; staged punches + rejected + 2-min-collapsed = mapped punches;
every staged punch maps to an employee; `shift_date` within 2026-04-01…2026-10-01.
