---

description: "Task list for Indus Weave HR data warehouse pipeline (001-hr-pipeline)"
---

# Tasks: Indus Weave HR Data Warehouse Pipeline

**Input**: Design documents from `/specs/001-hr-pipeline/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: DQ checks (Stage 6) and pytest probes are *required by spec* (FR-045…050, SC-007);
test-writing tasks are included per story where they mirror graded checks. Pure unit-test
scaffolding is included only where it protects graded behavior.

**Organization**: grouped by user story so each stage is independently implementable/testable.
Rule citations from `data/data_dictionary.md` are embedded in task text — cite them in code too.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallel-safe (different files, no dependencies)
- **[Story]**: US1…US7 (user stories in spec.md)

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repository skeleton required by the deliverable layout

- [ ] T001 [P] [Setup] Create dirs `ingestion/ transform/ warehouse/ddl/ analytics/results/ quality/ presentation/ tests/ docs/ db/` + `__init__.py` files
- [ ] T002 [P] [Setup] `requirements.txt` (pandas, sqlalchemy, pytest — pinned) + `.gitignore` (`db/`, `__pycache__/`, `.venv/`, `.pytest_cache/`)
- [ ] T003 [Setup] `common/db.py`: SQLite connect helper, `PRAGMA foreign_keys = ON`, `DB_PATH` from `config.py` (single source of truth for paths: `data/`, `db/indus_weave.db`)
- [ ] T004 [Setup] `config.py` at repo root: paths, expected row counts registry (contracts/README table), date window 2026-04-01…2026-09-30, dim_date end 2026-10-31

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: schemas + skeleton everything depends on

- [ ] T005 [Setup] `warehouse/ddl/00_schemas.sql` — `raw`, `staging`, `warehouse` schemas (IF NOT EXISTS) + `dq_results` table DDL
- [ ] T006 [Setup] `warehouse/ddl/apply.py` — executes all `warehouse/ddl/*.sql` in order (idempotent), usable as `python -m warehouse.ddl.apply`
- [ ] T007 [P] [Setup] `warehouse/ddl/10_staging.sql` — staging DDL per data-model.md (all tables incl. `employees_dedupe_log`, `rejected_punches`, `drift_corrections`, `attendance_daily`, CHECK constraints on status domains)
- [ ] T008 [P] [Setup] `warehouse/ddl/20_warehouse.sql` — dims + facts with PK/FK per data-model.md
- [ ] T009 [P] [Setup] `warehouse/ddl/30_indexes.sql` — join indexes (facts by keys, punches by emp/time, history by emp/from)

**Checkpoint**: foundation ready — US1 can begin

---

## Phase 3: User Story 1 - Trusted raw landing zone (Priority: P1) 🎯 MVP

**Goal**: 12 files → `raw.*` as TEXT with metadata, idempotent, counts verified
**Independent Test**: double-run produces unchanged counts; `ingestion/counts.py` exits 0

- [ ] T010 [P] [US1] `ingestion/load_raw.py`: file→table registry (CSV via pandas `dtype=str`+`keep_default_na=False`, JSON via flattening to 1 row/request + `approvals` stored as JSON text column — **nothing flattened semantically**), DROP+CREATE per table, insert with `_source_file`, `_loaded_at`, `_row_hash` (sha256 of ordered field values) (FR-001/002/003/005)
- [ ] T011 [US1] `ingestion/counts.py`: compare actual vs `config.EXPECTED_COUNTS`; print table; exit non-zero on mismatch (FR-004)
- [ ] T012 [US1] Load log: `raw.load_log` table (file, rows_read, rows_written, started_at, finished_at, status)
- [ ] T013 [US1] Verify idempotency: run loader twice in test, assert counts identical (SC-001) → **Gate R**
- [ ] T014 [US1] `tests/test_raw_counts.py` — asserts FR-004 counts + metadata non-null

**Checkpoint**: Gate R passed — Checkpoint 1 raw portion done

---

## Phase 4: User Story 2 - Clean, standardized staging (Priority: P2)

**Goal**: typed staging + quarantines + logs (Rules 1–2, 5–11, 16–18)
**Independent Test**: `raw = staging + rejected` per table; dedupe log populated; drift doc written

- [ ] T015 [P] [US2] `transform/01_clean_employees.py`: mixed date formats → ISO (3 formats), trim/normalize department strings to `dept_id` (casing, spaces, old names via `previous_name`), dedupe on latest `updated_at` → `staging.employees` + `staging.employees_dedupe_log` (Rules 1, 3) (FR-006/007)
- [ ] T016 [US2] `transform/02_clean_history.py`: recompute `valid_to_calc = next.effective_from − 1 day`, latest NULL; keep `_raw_effective_to`; flag/log the 37 overlap-or-gap employees (Rule 2) (FR-008)
- [ ] T017 [P] [US2] `transform/03_clean_reference.py`: departments (canonical + 2 renames), shifts JSON → table, holidays with scope codes, roster **gap-fill forward-fill** (Rules 5, 6) (FR-015)
- [ ] T018 [US2] `transform/04_punches.py` **part A — mapping**: composite-key join, unmapped → `staging.rejected_punches` with reason (Rule 8) (FR-010)
- [ ] T019 [US2] `transform/04_punches.py` **part B — drift**: per-device avg first-punch time vs roster shift start → identify offset device; apply offset; write `staging.drift_corrections` with method + before/after evidence (Rule 11) (FR-011) + docs paragraph for README
- [ ] T020 [US2] `transform/04_punches.py` **part C — 2-min dedupe**: SQL LAG window over `(emp_id, punch_time)`; collapse pairs < 2 min; count collapsed (Rule 9) (FR-012)
- [ ] T021 [US2] `transform/05_leave.py`: flatten JSON → `leave_requests` (with `is_counted`: both steps Approved + not cancelled), `leave_approval_steps`, `leave_days` (range − Sundays − plant holidays) (Rules 16, 17) (FR-013/014)
- [ ] T022 [P] [US2] `transform/06_overtime_payroll.py`: OT requests typed + approved-only view; payroll lines typed (Rule 19/20/21) (FR-019-adjacent prep)
- [ ] T023 [US2] Reconciliation helper in `quality/checks.py` skeleton: `raw = staging + rejected` per table (reused in Stage 6)
- [ ] T024 [US2] `tests/test_staging_invariants.py`: ISO dates only, dept resolution 100%, dedupe log non-empty, rejects have reasons, no leave_day on Sunday/holiday (SC-003) → **Gate S**

**Checkpoint**: Gate S — staging trusted; Checkpoint 1 staging portion done

---

## Phase 5: User Story 3 - Daily attendance (Priority: P3)

**Goal**: `staging.attendance_daily` with statuses + measures (Rules 4, 7, 10, 12–15)
**Independent Test**: invariants in SC-004 all pass

- [ ] T025 [US3] `transform/07_attendance_daily.py` **part A — day spine**: employee × day rows from hire→min(sep, 2026-09-30), clamped to window (Rule 4)
- [ ] T026 [US3] **part B — night attribution**: `shift_date` = punch date shifted for NIGHT (−6h rule) (Rule 7); pair first-in/last-out per `(emp_id, shift_date)`; single punch → flag (Rule 10) (FR-019)
- [ ] T027 [US3] **part C — status CASE chain** in exact Rule-12 priority: Weekly Off → Holiday → On Leave → Present → Missing Punch → Absent (FR-020)
- [ ] T028 [US3] **part D — measures**: worked hours, late minutes (>10 after start), early-departure (>10 before end) only on Present; OT half-hour flooring; Sunday/holiday work = all OT (Rules 13, 14, 15) (FR-021/022/023)
- [ ] T029 [US3] Extend `quality/checks.py`: status domain, non-negative hours, OT multiples of 0.5, one row per employee-day → **Gate A**

---

## Phase 6: User Story 4 - Star warehouse + ERD (Priority: P4)

**Goal**: `warehouse.*` dims/facts with enforced keys + SCD2 + ER diagram (Rules 2, 3)
**Independent Test**: RI query 0 orphans; SCD2 no overlaps; ERD committed

- [ ] T030 [US4] `warehouse/build_warehouse.py` **part A — `dim_date`**: pandas `date_range` 2026-04-01→2026-10-31 with day/month/week/weekday/is_weekend/is_holiday_all flags (research R1/R8)
- [ ] T031 [US4] **part B — `dim_employee` SCD2**: `LEAD(effective_from)−1d` build, surrogate keys, `is_current`, contiguous/non-overlapping (Rule 2, FR-026)
- [ ] T032 [P] [US4] **part C — `dim_department`, `dim_shift`** from staging
- [ ] T033 [US4] **part D — facts**: `fact_attendance_daily`, `fact_leave_day`, `fact_overtime_approved` (approved only), `fact_payroll_line` with `dept_id_month_end` via SCD2 at month end / last working day (Rule 3, FR-028/029)
- [ ] T034 [US4] Enforce FKs: load order dims→facts; `PRAGMA foreign_key_check` after load = 0 rows
- [ ] T035 [P] [US4] ER diagram: `warehouse/erd.dbml` source + dbdiagram.io/draw.io export → `warehouse/erd.png` (FR-030)
- [ ] T036 [US4] DQ: RI checks all facts, SCD2 overlap check → **Gate W**

**Checkpoint**: Checkpoint 2 prerequisite — warehouse built

---

## Phase 7: User Story 5 - Ten business answers (Priority: P5)

**Goal**: q01–q10 SQL + CSVs (Q5–Q8 first — CFO story, per PDF hint)
**Independent Test**: each runs standalone; CSVs non-empty

- [ ] T037 [P] [US5] `analytics/run_all.py`: discover `analytics/q*.sql`, execute, write `analytics/results/<stem>.csv`, print row counts
- [ ] T038 [US5] **Q5** `q05_overtime_computed_vs_approved_vs_paid.sql` — dept × month, 3 measures (Rules 14, 15, 19, 20) (FR-038)
- [ ] T039 [US5] **Q6** `q06_dept_paid_over_computed_15pct.sql` — paid > computed × 1.15 (FR-039)
- [ ] T040 [P] [US5] **Q7** `q07_paid_zero_attendance.sql` — payroll months with zero attendance (FR-040)
- [ ] T041 [P] [US5] **Q8** `q08_pay_after_separation.sql` — pay after `separation_date` (FR-041)
- [ ] T042 [P] [US5] **Q1** `q01_month_end_headcount.sql` — plant × dept × month (Rules 3, 4) (FR-034)
- [ ] T043 [P] [US5] **Q2** `q02_monthly_attrition.sql` — separations ÷ avg headcount (FR-035); definition documented in query header
- [ ] T044 [P] [US5] **Q3** `q03_absenteeism.sql` — excl. approved leave (FR-036); eligibility definition in header
- [ ] T045 [P] [US5] **Q4** `q04_top_late_arrivals.sql` — top 10 + dept (FR-037)
- [ ] T046 [P] [US5] **Q9** `q09_payroll_cost_mom.sql` — cost/employee by dept + MoM window fn (Rule 21, FR-042)
- [ ] T047 [P] [US5] **Q10** `q10_leave_overuse.sql` — approved Annual days > entitlement (Rules 18, FR-043)
- [ ] T048 [US5] Run all → CSVs committed; spot-reconcile Q5 paid OT vs payroll pivot sum → **Gate Q**

**Checkpoint**: Checkpoint 2 — ≥5 questions answered (then remaining 5)

---

## Phase 8: User Story 6 - Automated DQ proof (Priority: P6)

**Goal**: `dq_results` complete & automated post-load (FR-045…050)
**Independent Test**: clean run all PASS; seeded violation flips FAIL

- [ ] T049 [US6] `quality/checks.py` families: PK uniqueness/not-null (all tables), RI fact→dim, reconciliation `raw = staging + rejected`, accepted values (attendance status, leave type, pay component), sanity (negative hours, >16h shifts, SCD2 overlap)
- [ ] T050 [US6] `quality/run_dq.py` entry point + wire into `run_pipeline.py` after every stage load
- [ ] T051 [US6] `tests/test_dq.py`: seed an invalid status row → expect FAIL → cleanup → PASS (SC-007) → **Gate D**

---

## Phase 9: User Story 7 - CFO story & reproducible delivery (Priority: P7)

**Goal**: one-command rebuild + findings + deck + README
**Independent Test**: clean-clone rebuild per quickstart.md; evidence queries reproduce numbers

- [ ] T052 [US7] `run_pipeline.py`: stages in plan.md order, `--stage` flag for partial runs, timing summary, exits non-zero on any gate failure (FR-051)
- [ ] T053 [US7] `README.md`: mentor rebuild (quickstart.md content), design decisions, **drift-correction write-up**, rule-citation map, team members, rubric artifact map (FR-052)
- [ ] T054 [US7] Analyze q05–q08 outputs → write `presentation/cfo_findings.md`: exactly 3 findings, each = number + evidence query + recommended action (FR-055)
- [ ] T055 [P] [US7] `presentation/slides.pdf` ≤ 6 slides (problem, pipeline, finding 1–3, ask)
- [ ] T056 [US7] Demo rehearsal: 5-min script, every team member can explain any line (FR-057)

**Checkpoint**: **Gate P** — ready for demo

---

## Phase 10: Polish & Cross-Cutting

- [ ] T057 [P] `docs/profile_notes.md` finalized: profiling outputs + planted-issues inventory (SC-003 evidence)
- [ ] T058 [P] PHRs for each major prompt in `history/prompts/001-hr-pipeline/` (opencode.md compliance)
- [ ] T059 Final green run: `python run_pipeline.py` from clean `db/` → all gates PASS, 10 CSVs, dq_results green; commit
- [ ] T060 Create public GitHub repo, push before code freeze; verify README renders

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** → **US1** (blocks everything) → **US2** → **US3**
- **US4** depends on US2/US3 outputs (facts need attendance + staging) — DDL portion (T005–T009) already done in P2
- **US5** depends on US4 (facts) — Q-file skeletons + `run_all.py` (T037) can start after P2 [P]
- **US6** builds incrementally from US2 onward (checks added per stage), completes after US5
- **US7** depends on US5+US6 (findings need numbers; README needs everything)
- **Parallel after Foundational**: teammate A = US1→US2 (T010–T024), teammate B = T037 + DDL review + ERD (T035) + profiling (T057); US3/US4/US5 sequential-ish but Q-files can be drafted against data-model.md contract before warehouse lands (verify after)

## Implementation Strategy

1. Phases 1–3 first (**Checkpoint 1**: raw + staging loaded, counts shown to mentor)
2. Phases 4–5 (staging trusted, attendance green)
3. Phases 6–7 (**Checkpoint 2**: warehouse + ≥5 questions — do Q5–Q8 first)
4. Phases 8–9 (DQ proof + CFO package) → **code freeze**
5. Phase 10 only while time remains; bonus tasks (incremental load, funnel, dashboard)
   NOT scheduled — pull in only if Gate P is green early

## Notes

- Never edit `data/` (Principle II); every fix in code with rule citation (Principle I/V).
- Commit after each task or logical group; message references task IDs (e.g., `T010 raw loader`).
- Stop at each Gate checkpoint and validate before proceeding.
