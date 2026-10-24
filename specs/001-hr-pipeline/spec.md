# Feature Specification: Indus Weave HR Data Warehouse Pipeline

**Feature Branch**: `001-hr-pipeline`  
**Created**: 2026-10-25  
**Status**: Draft  
**Input**: User description: "Build a Python + SQL pipeline that turns six months of messy HR exports from Indus Weave Textiles into a trusted data warehouse and explains why overtime cost keeps rising (PeopleOps Data Hackathon case study)."

**Sources of truth**: `PeopleOps Data Hackathon HR Pipeline Case Study.pdf` (stages, deliverables, rubric), `data/data_dictionary.md` (21 business rules), `data/` (12 synthetic export files, 1 Apr – 30 Sep 2026).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trusted raw landing zone (Priority: P1)

As a data engineer, I load all 12 HCM export files into a `raw` schema exactly as delivered —
every column as TEXT, nothing flattened, renamed, or corrected — so that every later stage can be
traced back to the untouched source and re-loaded safely.

**Why this priority**: Nothing else can start without raw data; Checkpoint 1 (end of Day 1)
requires raw loaded with row counts shown to a mentor. This is the foundation of the rubric's
"Code quality and reproducibility" (10 pts) and "Cleaning" evidence (20 pts).

**Independent Test**: Run the load twice against an empty database and against a populated one;
verify every table's row count equals the case-study counts, `_row_hash` prevents duplicates, and
a per-file/per-table row-count log matches source counts.

**Acceptance Scenarios**:

1. **Given** an empty database, **When** the raw loader runs, **Then** `raw.*` tables exist with
   all columns typed TEXT and counts: employees 1316, employment_history 3686, departments 25,
   shifts 4, shift_roster 36402, device_mapping 1260, biometric_punches 345280, holidays 12,
   leave_requests 5372, overtime_requests 22098, payroll_lines 53617, applications 3835.
2. **Given** raw tables already populated, **When** the raw loader runs again, **Then** row counts
   are unchanged (idempotent via `_row_hash`) and the log records both runs.
3. **Given** any raw row, **When** I inspect its metadata, **Then** `_source_file`, `_loaded_at`
   and `_row_hash` are present and non-null.

---

### User Story 2 - Clean, standardized staging layer (Priority: P2)

As a data engineer, I convert raw text into typed, cleaned `staging` tables: trimmed and
consistent text, ISO dates, deduplicated employees with an audit log, device-to-employee punch
mapping with a rejected-punch quarantine, the clock-drifted device detected and corrected,
duplicate punches collapsed by the 2-minute rule, and leave requests flattened to request rows,
approval-step rows and per-day rows — so that downstream logic can trust every value.

**Why this priority**: The rubric awards 20 points for "every planted data issue found, fixed in
code and documented"; Checkpoint 1 also requires staging loaded. All later stages depend on it.

**Independent Test**: For every table run `raw count = staging count + rejected count`;
verify dedupe-log entries exist for the ~50 duplicate employees; verify unmapped punches land in
`staging.rejected_punches` with reasons; verify the drifted device's corrected times change
check-in patterns; verify no residual non-ISO dates or untrimmed strings.

**Acceptance Scenarios**:

1. **Given** raw employees with duplicate `emp_id` rows, **When** staging builds,
   **Then** one row per `emp_id` remains (latest `updated_at`) and a log row records which
   rows were merged and why (Rule 1).
2. **Given** punches with unmapped `device_id`+`device_user_id`, **When** staging maps punches,
   **Then** they are excluded from mapped punches and inserted into
   `staging.rejected_punches` with a reason (Rule 8).
3. **Given** punches from every device, **When** drift detection runs, **Then** the device whose
   average check-in time is systematically offset from shift start is identified, corrected, and
   the detection method is written up (Rule 11).
4. **Given** any employee's punch series, **When** the 2-minute rule runs, **Then** punches less
   than 2 minutes apart count as one, implemented with a window function over punch time (Rule 9).
5. **Given** nested `leave_requests.json`, **When** staging flattens it, **Then** there is one row
   per request, one row per approval step, and one row per leave day, with only fully approved,
   non-cancelled requests counting (Rule 16) and Sundays/plant holidays inside ranges excluded
   (Rule 17).

---

### User Story 3 - Daily attendance with statuses, lateness and overtime (Priority: P3)

As an analyst, I get `staging.attendance_daily`: one row per employee per scheduled day, pairing
first check-in with last check-out, assigning night-shift punches to the shift's start date,
computing worked hours, late minutes, early-departure minutes and overtime hours, and giving each
row exactly one status from {Present, Absent, On Leave, Holiday, Weekly Off, Missing Punch} —
so attendance questions can be answered from a single trusted table.

**Why this priority**: Attendance is the bridge between raw punches and every business question;
questions 3, 4, 5, 6, 7, 8 all read from it. Wrong statuses silently corrupt the answer key.

**Independent Test**: Query invariants — every employee-day has exactly one status; status is in
the accepted domain; no negative worked hours; no shift > 16 hours; Sundays without punches are
Weekly Off; plant holidays without punches are Holiday; late/early counted only on Present
working days; overtime is a whole multiple of 0.5.

**Acceptance Scenarios**:

1. **Given** an employee with two punches spanning 06:12–14:05 on DAY shift, **When**
   attendance builds, **Then** status = Present, late = 12 minutes (06:12 vs 06:00 + 10 grace),
   early departure = 0, overtime = 0.
2. **Given** a NIGHT shift (22:00–06:00) with punches 21:55 on 1 May and 06:10 on 2 May,
   **When** attendance builds, **Then** the row belongs to 1 May and overtime = 0.5 h
   (10 minutes past 06:00, rounded down to half-hours).
3. **Given** an employee with one punch only, **When** attendance builds,
   **Then** status = Missing Punch (Rule 10).
4. **Given** an approved leave covering a plant holiday, **When** attendance builds,
   **Then** the holiday row is Holiday, not On Leave (Rules 12, 17).

---

### User Story 4 - Star-schema warehouse with enforced keys (Priority: P4)

As a data architect, I model a `warehouse` schema with `dim_employee` (SCD Type 2 sourced from
employment history), `dim_department`, `dim_shift`, `dim_date`, and facts
`fact_attendance_daily`, `fact_leave_day`, `fact_overtime_approved`, `fact_payroll_line` —
primary/foreign keys enforced — plus an ER diagram — so analysts can join reliably and month-based
facts attach to the department in effect at month end.

**Why this priority**: The data model is 15 rubric points and the questions (US5) run on top of
it; Checkpoint 2 requires the warehouse built.

**Independent Test**: Every fact row resolves to a dimension row (RI query returns 0 orphans);
SCD2 ranges for each employee never overlap; keys are NOT NULL and unique; `dim_date` covers
2026-04-01 → 2026-10-31; ERD file committed.

**Acceptance Scenarios**:

1. **Given** an employee transferred from Korangi to SITE on 15 Jun, **When** the SCD2 dimension
   loads, **Then** two rows exist with contiguous `valid_from`/`valid_to` and a fact row for
   10 Jun joins to the Korangi row while 20 Jun joins to the SITE row.
2. **Given** any fact table, **When** the FK check runs, **Then** zero unmatched dimension
   references are found.

---

### User Story 5 - The ten business answers (Priority: P5)

As the CFO-facing analyst, I produce one `.sql` file per question (q01–q10) using CTEs and window
functions where they fit, each result saved as a CSV in `analytics/results/`, covering headcount,
attrition, absenteeism, lateness, overtime computed vs approved vs paid, >15% overpaid
departments, zero-attendance pay, post-separation pay, payroll cost per employee with MoM change,
and annual-leave over-entitlement — so the team can defend the numbers against the hidden answer
key.

**Why this priority**: Correct answers are 25 rubric points — the single largest — and
questions 5–8 contain the CFO's story.

**Independent Test**: Each query runs cleanly against the warehouse in one statement; every
query has a non-empty CSV; totals reconcile with staging (e.g., OT paid = sum of OVERTIME lines).

**Acceptance Scenarios**:

1. **Given** the loaded warehouse, **When** `q05_overtime_comparison.sql` runs, **Then** it
   returns overtime hours by department and month in three measures: computed from punches,
   approved from requests, paid from payroll (Rule 20).
2. **Given** `q10_leave_overuse.sql`, **When** it runs, **Then** employees whose approved Annual
   leave days Apr–Sep exceed `annual_leave_entitlement` (Rule 18) are returned.

---

### User Story 6 - Automated data-quality proof (Priority: P6)

As a mentor-facing engineer, I run automated checks after every load that write to
`dq_results`: PK uniqueness/not-null on every key, fact-to-dimension referential integrity,
reconciliation `raw = staging + rejected` per table, accepted-value domains (attendance status,
leave type, pay component), and business sanity (no negative worked hours, no shift > 16 h,
no overlapping SCD2 ranges) — so the team can prove every raw row is accounted for.

**Why this priority**: 15 rubric points, but it validates everything above it — it must exist
before the demo.

**Independent Test**: Run the full pipeline; `dq_results` contains a row per check with
pass/fail and detail; intentionally breaking a rule (e.g., inserting an invalid status) flips
the check to fail.

**Acceptance Scenarios**:

1. **Given** a freshly built warehouse, **When** DQ runs, **Then** every check row shows PASS
   with zero failures, and `raw = staging + rejected` holds for all 12 tables.
2. **Given** a fact row with a nonexistent `dim_employee_key`, **When** RI checks run,
   **Then** that check FAILs with the offending key listed.

---

### User Story 7 - CFO story and reproducible delivery (Priority: P7)

As the presenting team, I ship a public GitHub repo a mentor can rebuild from a clean machine
(`README.md`, `requirements.txt`, one-command `run_pipeline.py`), plus
`presentation/cfo_findings.md` with three findings — each with the number, its evidence query and
a recommended action — and a ≤6-slide deck for a 5-minute demo where any team member can explain
any line of code.

**Why this priority**: 15 rubric points (findings/demo) + 10 (reproducibility); last because it
depends on all other stories, but must land before code freeze.

**Independent Test**: On a clean clone: `pip install -r requirements.txt && python
run_pipeline.py` completes and regenerates every CSV and `dq_results`; each finding's evidence
SQL re-executes and returns the quoted number.

**Acceptance Scenarios**:

1. **Given** a clean checkout with only the repo, **When** `python run_pipeline.py` runs,
   **Then** the database, all 10 result CSVs and all DQ rows are produced without manual steps.
2. **Given** `cfo_findings.md`, **When** each evidence query runs, **Then** the number quoted in
   the finding appears in the result.

### Edge Cases

- Night-shift punches at 00:01–06:00 on the following calendar day (incl. 1 Oct check-outs of
  30 Sep shifts) attribute to the shift start date.
- A device clock running one hour off creates phantom early/late and wrong-date punches until
  corrected.
- Missing roster weeks inherit the previous week's shift (Rule 6); employees with no earlier
  week need a deterministic fallback (head-office/manager GEN default per Rule 5).
- Employee with `hire_date` or `separation_date` mid-month: month-end headcount and department
  attribution use last working day (Rules 3, 4).
- Leave ranges spanning Sundays and plant holidays: those days must not become leave days.
- OT approved for a day with no overtime worked: approved ≠ computed ≠ paid — all three must be
  reported separately, never conflated.
- Duplicate punches seconds apart, punch pairs missing check-out, punches from unmapped
  contractor IDs, and departments renamed mid-period (Supply Chain ← Procurement,
  Finishing ← Processing) all need code-handled resolution.
- Payroll in long format: earnings vs deductions (deductions stored as positive with
  `component_type = DEDUCTION`); OVERTIME `units` = hours paid.
- Re-running any stage must not double data (idempotency across all stages, not only raw).

## Requirements *(mandatory)*

### Functional Requirements

**Ingestion (Stage 1) — US1**

- **FR-001**: System MUST load all 12 files from `data/` into schema `raw` with every column
  stored as TEXT, preserving original values byte-for-byte apart from transport encoding.
- **FR-002**: System MUST add `_source_file`, `_loaded_at`, `_row_hash` columns to every raw
  table; `_row_hash` = stable SHA-256 of the row's concatenated field values.
- **FR-003**: Loads MUST be idempotent: a second run must not increase any table's row count.
- **FR-004**: System MUST log row counts per source file and per target table and verify they
  match the expected counts (employees 1316, employment_history 3686, departments 25, shifts 4,
  shift_roster 36402, device_mapping 1260, biometric_punches 345280, holidays 12,
  leave_requests 5372, overtime_requests 22098, payroll_lines 53617, applications 3835).
- **FR-005**: Raw files MUST NOT be edited, moved or renamed; all fixes occur in code (Rule:
  Raw is Immutable).

**Cleaning (Stage 2) — US2**

- **FR-006**: System MUST create typed `staging` tables: trimmed text, consistent department
  casing/spaces, all dates normalized to ISO `YYYY-MM-DD`.
- **FR-007**: Employees MUST be deduplicated on `emp_id` keeping latest `updated_at`, with a log
  of merged records and reasons (Rule 1).
- **FR-008**: `employment_history.valid_to` MUST be recomputed as "day before the next record's
  `effective_from`"; latest records have no end (Rule 2).
- **FR-009**: Monthly attribution MUST use the department held on the last day of the month, or
  the last working day if separated during the month (Rule 3).
- **FR-010**: Punches MUST be mapped by the composite key `device_id` + `device_user_id`;
  unmapped punches MUST be parked in `staging.rejected_punches` with a reason and excluded from
  mapped results (Rule 8).
- **FR-011**: The system MUST detect any device with a systematically offset clock, correct its
  punch times, and document the detection method (Rule 11) — detection hint: average check-in
  time per device versus shift start.
- **FR-012**: Duplicate punches within 2 minutes for the same employee MUST count as one,
  implemented with a window function (LAG) over punch time (Rule 9).
- **FR-013**: `leave_requests.json` MUST be flattened into one row per request, one row per
  approval step, and one row per leave day expanded across the `from`–`to` range (Rules 16, 17).
- **FR-014**: Leave days MUST count only when both approval steps (Manager then HR) are
  `Approved` and `cancelled_at` is empty (Rule 16); `days_requested` MUST NOT be used for counts.
- **FR-015**: Missing roster weeks MUST inherit the previous week's shift (Rule 6).
- **FR-016**: The dedupe/merge log, rejected punches, and drift-correction write-up MUST be
  persisted as queryable artifacts (tables or docs).
- **FR-017**: Every transformation MUST cite the data-dictionary rule number it implements where
  the mapping is non-obvious.

**Business logic (Stage 3) — US3**

- **FR-018**: System MUST build `staging.attendance_daily` with exactly one row per employee per
  scheduled day of employment.
- **FR-019**: Check-in = first punch and check-out = last punch per employee per shift date;
  night-shift punches MUST be assigned to the date the shift started (Rules 7, 10).
- **FR-020**: Status MUST be one of {Present, Absent, On Leave, Holiday, Weekly Off,
  Missing Punch} applying the priority order in Rule 12 (Sunday → Weekly Off, plant holiday →
  Holiday, approved leave → On Leave, ≥2 punches → Present, 1 punch → Missing Punch, 0 → Absent).
- **FR-021**: Late arrival = check-in > 10 minutes after shift start; early departure = check-out
  > 10 minutes before shift end; both counted ONLY on Present working days (Rule 13).
- **FR-022**: Overtime on working days = minutes after shift end rounded DOWN to whole
  half-hours (29 min → 0, 45 min → 0.5, 75 min → 1.0) (Rule 14).
- **FR-023**: Sunday/holiday work is ALL overtime = check-out − check-in, rounded down to whole
  half-hours (Rule 15).
- **FR-024**: Worked hours MUST never be negative; no shift MAY exceed 16 hours.

**Warehouse (Stage 4) — US4**

- **FR-025**: System MUST define a `warehouse` schema with enforced primary and foreign keys
  (SQLite: `PRAGMA foreign_keys = ON` plus explicit constraints).
- **FR-026**: `dim_employee` MUST be SCD Type 2 built from `employment_history`, with
  `valid_from`/`valid_to` bounds contiguous and non-overlapping (Rule 2), keyed so facts join by
  `work_date BETWEEN valid_from AND valid_to`.
- **FR-027**: Dimensions MUST include `dim_department`, `dim_shift`, `dim_date` (covering
  2026-04-01 → 2026-10-31 with day, month, week, weekday, is_weekend, holiday flags).
- **FR-028**: Facts MUST include `fact_attendance_daily`, `fact_leave_day`,
  `fact_overtime_approved`, `fact_payroll_line`, each referencing the correct dimension keys.
- **FR-029**: Monthly facts MUST resolve the employee's department as of month end / last working
  day (Rule 3) via the SCD2 dimension.
- **FR-030**: An ER diagram MUST be produced (dbdiagram.io, draw.io or hand-drawn photo) and
  committed as `warehouse/erd.png` (or `.md`/`.drawio` source plus exported image).

**Analysis (Stage 5) — US5**

- **FR-031**: There MUST be exactly one `.sql` file per question, `q01…q10`, in `analytics/`,
  each executable standalone against the warehouse.
- **FR-032**: Queries MUST use CTEs and window functions where they naturally fit (e.g., MoM
  change, ranking).
- **FR-033**: Each query's result MUST be exported to `analytics/results/` as a CSV.
- **FR-034**: Q1 Month-end headcount by plant and department for all six months (Rules 3, 4).
- **FR-035**: Q2 Monthly attrition rate by department = separations ÷ average headcount.
- **FR-036**: Q3 Absenteeism rate by plant and month, excluding approved leave.
- **FR-037**: Q4 Top 10 employees by late arrivals, with department.
- **FR-038**: Q5 Overtime by department and month, three measures: computed from punches,
  approved from requests, paid from payroll (Rules 14, 15, 19, 20).
- **FR-039**: Q6 Departments where paid OT exceeds computed OT by more than 15%.
- **FR-040**: Q7 Employees paid in a month with zero attendance that month.
- **FR-041**: Q8 Employees still receiving pay after their separation date.
- **FR-042**: Q9 Payroll cost per employee by department with month-over-month change
  (Rule 21: cost = sum of EARNING lines).
- **FR-043**: Q10 Employees whose approved Annual leave days in the six months exceed
  `annual_leave_entitlement` (Rule 18).
- **FR-044**: Payroll long format MUST be pivoted in SQL using
  `SUM(CASE WHEN component = '…' THEN … END)` patterns.

**Data quality (Stage 6) — US6**

- **FR-045**: Automated checks MUST run after every load and write results to a `dq_results`
  table (check name, target, status, failures, detail, run timestamp).
- **FR-046**: Uniqueness and not-null checks MUST cover every primary key.
- **FR-047**: Referential-integrity checks MUST verify every fact row has matching dimension rows.
- **FR-048**: Reconciliation MUST verify `raw row count = staging rows + rejected rows` for
  every table.
- **FR-049**: Accepted-value checks MUST cover attendance status, leave type and pay component.
- **FR-050**: Business-sanity checks MUST verify no negative worked hours, no shift > 16 hours,
  and no overlapping SCD2 ranges.

**Delivery & presentation — US7**

- **FR-051**: `run_pipeline.py` MUST rebuild everything from raw files with one command
  (Stage order 1→6), and the pipeline MUST be safe to re-run.
- **FR-052**: `README.md` MUST let a mentor rebuild the database from raw files on a clean
  machine: setup, commands, design decisions, team members.
- **FR-053**: `requirements.txt` MUST pin every third-party dependency used.
- **FR-054**: The repo MUST follow the prescribed layout: `ingestion/`, `transform/`,
  `warehouse/ddl/`, `warehouse/erd.*`, `analytics/qNN_*.sql`, `analytics/results/`, `quality/`,
  `presentation/`.
- **FR-055**: `presentation/cfo_findings.md` MUST contain exactly three findings, each with the
  number, the evidence query and a recommended action.
- **FR-056**: `presentation/slides.pdf` MUST be ≤ 6 slides.
- **FR-057**: The demo MUST fit 5 minutes plus 3 minutes Q&A; every line of code must be
  explainable by a team member.
- **FR-058**: Work MUST be committed to one public GitHub repo with commits before code freeze.

**Constraints & governance**

- **FR-059**: Python 3 + SQL only for Stages 1–6; no Spark, no cloud services, no BI tools;
  SQLite is the target database (PostgreSQL permitted only if setup cost is proven negligible).
- **FR-060**: No result values may be hard-coded; every published number MUST be produced by a
  committed script or query (Code Only).
- **FR-061**: Business-rule ambiguities MUST be resolved with mentors, never by silent guessing;
  the data dictionary wins over data in all conflicts (Rule Wins).

*Open items*: none blocking; bonus tasks (incremental 7th-month load, recruitment funnel from
`applications.csv`, dashboard) are explicitly out of scope until US1–US7 are green.

### Key Entities *(include if feature involves data)*

- **Employee**: identity (`emp_id`, name, plant, grade, employment type), lifecycle
  (`hire_date`, `separation_date`), leave entitlement; versioned over time by employment history.
- **EmploymentHistoryRecord**: effective-dated department/grade/salary change; drives SCD2 and
  month-end attribution.
- **Department**: `dept_id`, name, plant, cost center, previous name (2 renames mid-period).
- **Shift**: code (DAY/EVE/NIGHT/GEN), start/end time, crosses-midnight flag, grace minutes.
- **RosterWeek**: employee × Monday-start week × shift code; missing weeks inherit prior week.
- **Punch**: device event (`device_id`, `device_user_id`, `punch_time`); mapped to an employee,
  deduplicated, drift-corrected; rejections quarantined with reasons.
- **AttendanceDay**: employee × date grain with status, worked/late/early/OT measures — the
  central derived table.
- **LeaveRequest / LeaveApprovalStep / LeaveDay**: flattened request, its approval workflow, and
  its countable days (excluding Sundays/holidays).
- **OvertimeRequest**: requested/approved hours per shift date with status.
- **PayrollLine**: employee × month × component in long format; earnings vs deductions; OVERTIME
  units = paid hours.
- **Holiday**: date × name × scope (ALL/HO/KOR/SITE/FSD).
- **DateDimension**: calendar spine for all six months (+ October for spillover).
- **DQResult**: one check execution record feeding the mentor demo.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 12 raw tables load with counts exactly matching FR-004, and a double-run
  changes no count (idempotency proven).
- **SC-002**: For every table, `raw = staging + rejected` holds at DQ time; 100% of raw rows are
  accounted for.
- **SC-003**: All planted data issues (duplicate employees, mixed date formats, messy department
  text, history overlap/gap cases, unmapped punches, drifted device, duplicate punches, nested
  leave, missing roster weeks, approvals without work) are detected, fixed in code, and
  documented.
- **SC-004**: `staging.attendance_daily` satisfies 100% of invariants (single status per day,
  accepted domain, non-negative hours, OT multiples of 0.5, no >16 h shifts).
- **SC-005**: Warehouse passes all PK/FK/SCD2 checks; zero orphan fact rows; ERD committed.
- **SC-006**: All 10 queries execute successfully and produce CSVs; answers match the hidden
  answer key within rounding.
- **SC-007**: Every check in `dq_results` is automated, runs post-load, and PASSes on a clean
  full build; any seeded violation flips it to FAIL.
- **SC-008**: A mentor can rebuild everything on a clean machine using only `README.md`
  (`pip install -r requirements.txt` + `python run_pipeline.py`) in under 15 minutes.
- **SC-009**: Three CFO findings each quantify impact, link an evidence query that reproduces
  the number, and propose an action; demo completes in ≤ 5 minutes.
- **SC-010**: Checkpoint 1 met (raw + staging loaded with row counts) and Checkpoint 2 met
  (warehouse built, ≥5 questions answered) per the hackathon timeline.
