# Contract: `departments.csv` — Foundation: Organization

**Rows**: 25 (7 Head Office, 8 Korangi, 5 SITE, 5 Faisalabad)
**Rules**: 3 (monthly attribution joins through dept), rename handling

| Column | Raw type | Notes |
|---|---|---|
| `dept_id` | text | `D01…D25`, PK |
| `dept_name` | text | canonical name — **names repeat across plants** (Maintenance ×3, QC ×4): never join by name alone |
| `plant` | text | Head Office / Korangi Plant / SITE Plant / Faisalabad Plant |
| `cost_center` | text | `CC-…` |
| `previous_name` | text | **2 renames mid-period**: D04 Supply Chain ← Procurement (2026-07-01), D15 Finishing ← Processing (2026-06-01); empty otherwise |
| `renamed_on` | text | ISO date of rename, empty otherwise |

**Validation**: row count 25; unique `dept_id`; exactly 2 non-empty `previous_name`;
employees' messy department strings normalize to either `dept_name` or `previous_name`
(both map to the same `dept_id`).
