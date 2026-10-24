# Contract: `shift_roster.csv` — Workforce: Rosters

**Rows**: 36,402
**Rules**: 5 (plant rotate DAY/EVE/NIGHT weekly; HO & managers GEN), 6 (Monday-start weeks,
missing week ⇒ same as previous week), 7

| Column | Raw type | Notes |
|---|---|---|
| `emp_id` | text | FK → employees |
| `week_start` | text | ISO **Monday** dates; extends into early October (planned weeks) |
| `shift_code` | text | DAY/EVE/NIGHT/GEN |

**Planted mess**: some weeks missing per employee (histogram in profiling) — gap-fill by
forward-fill (Rule 6); employees with no earlier week get the Rule-5 default (HO/manager → GEN,
plant worker → DAY — confirm counts during profiling).

**Validation**: row count 36,402; `week_start` all Mondays (`weekday()==0`); shift codes ∈
domain; after staging: zero gaps per employee inside Apr–Sep window (or documented fallbacks).
