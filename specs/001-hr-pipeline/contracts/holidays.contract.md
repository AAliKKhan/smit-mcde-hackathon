# Contract: `holidays.csv` — Workforce: Holidays

**Rows**: 12
**Rules**: 12 (Holiday status priority), 15 (holiday work = all OT), 17 (no leave on holidays)

| Column | Raw type | Notes |
|---|---|---|
| `holiday_date` | text | ISO dates Apr–Sep 2026 |
| `holiday_name` | text | e.g. "Eid ul Adha", "Annual plant shutdown" |
| `scope` | text | `ALL` (5 rows) or plant codes `HO/KOR/SITE/FSD` (7 rows: FSD×2, SITE×1, KOR×1, …) |

**Validation**: 12 rows; `scope` ∈ {ALL, HO, KOR, SITE, FSD}; dates within window;
no duplicate (date, scope).
**Semantics**: scope code maps to plant — `ALL` applies to every plant incl. Head Office;
plant-specific rows apply only to that plant's employees (e.g. `2026-09-12` shutdown = KOR only).
