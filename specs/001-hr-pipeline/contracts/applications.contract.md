# Contract: `applications.csv` — Talent Acquisition (BONUS ONLY)

**Rows**: 3,835
**Rules**: none required — used only for the recruitment-funnel bonus task (out of scope until
US1–US7 are green)

| Column | Raw type | Notes |
|---|---|---|
| `application_id` | text | **repeats** — one row per stage change |
| `candidate_id` | text | `C00001…` |
| `job_req_id` | text | `JR…` |
| `dept_id` | text | FK → departments |
| `stage` | text | Applied / Screened / … (profile domain) |
| `stage_date` | text | ISO |

**Validation**: 3,835 rows; loaded to raw for completeness (FR-001) even though analytics for
this file are bonus. Funnel design (if reached): conversion % and median days between stages
per `job_req_id`/`dept_id`.
