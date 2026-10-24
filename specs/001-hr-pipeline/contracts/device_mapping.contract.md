# Contract: `device_mapping.csv` — Workforce: Biometric Gateway

**Rows**: 1,260
**Rules**: 8 (map by `device_id` + `device_user_id`; unmapped = contractors/visitors → rejected)

| Column | Raw type | Notes |
|---|---|---|
| `device_id` | text | e.g. `DEV-SITE-01` |
| `device_user_id` | text | device-local user number |
| `emp_id` | text | FK → employees |
| `enrolled_on` | text | ISO |

**Validation**: row count 1,260; composite key (`device_id`,`device_user_id`) unique;
all `emp_id` resolve to employees (profiling flags orphans if any).
**Join contract**: punches join on **both** `device_id` AND `device_user_id` — never
`device_user_id` alone (composite uniqueness is what makes mapping unambiguous).
