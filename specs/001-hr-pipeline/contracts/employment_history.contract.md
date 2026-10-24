# Contract: `employment_history.csv` — Core HR: Employment

**Rows**: 3,686
**Rules**: 2 (effective dating — `effective_to` unreliable), 3 (month-end department), 4

| Column | Raw type | Notes |
|---|---|---|
| `emp_id` | text | FK → employees |
| `effective_from` | text | ISO in file; re-verify in staging |
| `effective_to` | text | **unreliable**: overlaps or gaps for 37 employees — do NOT trust; recompute as day-before-next-record (Rule 2), keep raw as `_raw_effective_to` |
| `dept_id` | text | FK → departments |
| `designation`, `grade` | text | snapshot attributes |
| `basic_salary` | text | monthly PKR → numeric in staging |
| `change_reason` | text | Hire / Salary Revision / Promotion / Transfer |

**Validation (raw)**: row count 3,686.
**Validation (staging)**: per-employee `effective_from` strictly increasing after rebuild;
`valid_to_calc >= valid_from` for closed periods; **exactly 37 employees** show the raw
overlap/gap pattern (log each in docs/profile_notes.md as planted-issue evidence);
latest record has NULL end; every `dept_id` resolves.
