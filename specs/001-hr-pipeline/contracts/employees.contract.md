# Contract: `employees.csv` — Core HR: People

**Rows**: 1,316 expected (includes ~50 duplicate `emp_id` records)
**Rules**: 1 (dedupe by latest `updated_at`), 3, 4 (month-end attribution), 18 (entitlement)

| Column | Raw type | Notes / planted mess |
|---|---|---|
| `emp_id` | text | `E10001…` — **not unique in file**; dedupe key |
| `full_name` | text | synthetic |
| `gender` | text | M/F |
| `date_of_birth` | text | **3 formats**: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-Mon-YYYY` → ISO in staging |
| `email`, `phone` | text | synthetic, pass through |
| `plant` | text | Head Office / Korangi Plant / SITE Plant / Faisalabad Plant — verify casing/trim |
| `department` | text | **messy**: mixed case, stray spaces (`"dyeing  "`), old names pre-dating renames → normalize to `departments.dept_name` |
| `designation`, `grade` | text | grade G1–G9 |
| `employment_type` | text | Permanent / Contract |
| `hire_date` | text | mixed formats (see sample: `17-Nov-2022`, `2016-06-18`) → ISO |
| `separation_date` | text | empty = active (Rules 3, 4) |
| `status` | text | Active / Separated |
| `annual_leave_entitlement` | text | integer days/year (Rule 18) |
| `updated_at` | text/timestamp | tie-breaker for duplicates (Rule 1) |

**Validation (raw)**: row count 1,316; all columns TEXT; `_row_hash` non-null.
**Validation (staging)**: exactly N unique `emp_id` after dedupe; every `department` resolves to
`departments.dept_name` or `previous_name`; all dates ISO; dedupe log non-empty (~50 rows).
