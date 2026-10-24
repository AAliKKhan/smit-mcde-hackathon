# Research: 001-hr-pipeline (Phase 0)

Date: 2026-10-25 | Branch: `001-hr-pipeline` | Inputs: case study PDF, `data/data_dictionary.md`, `data/*`

Findings are decisions unless marked OPEN (mentor questions — asked per rule "ask mentors about
business rules, never about solutions").

## R1. Database engine: SQLite ✅ DECIDED (ADR-001)

- Case study explicitly allows SQLite when a team can't run PostgreSQL.
- Trade-off: PostgreSQL gives `generate_series()`, `INTERVAL`, real schemas and typed constraints;
  SQLite gives zero setup on every mentor laptop and trivially clean-machine rebuild (SC-008).
- SQLite mitigations: `PRAGMA foreign_keys=ON` per connection (not persistent), types enforced via
  `CHECK (col IN (…))` + `typeof()` discipline (load TEXT, cast at staging), `NOT NULL`/`PRIMARY KEY`
  honored, date spine generated in pandas (`pd.date_range`) instead of `generate_series()`.
- Schemas `raw`, `staging`, `warehouse` + `dq_results` table live in one file `db/indus_weave.db`.

## R2. Raw idempotency strategy ✅ DECIDED

Options: (a) `_row_hash` as PK with `INSERT OR IGNORE`; (b) upsert on `_row_hash`;
(c) deterministic rebuild (drop + recreate raw tables from `data/` every run).
**Chosen: (c) deterministic rebuild with `_row_hash` retained for audit and reconciliation.**
Rationale: files are immutable (Principle II) so rebuild == same rows; satisfies "running twice
must not create duplicate rows" trivially and makes full `run_pipeline.py` deterministic.
`counts.py` asserts expected counts post-load → Gate R evidence.

## R3. Punch dedup (2-minute rule) ✅ DECIDED — Rule 9

`LAG(punch_time) OVER (PARTITION BY emp_id ORDER BY punch_time)`; a punch is dropped when
`julianday(punch) - julianday(prev) < 2/1440`. Implemented in SQL (window functions required by
spec FR-032 culture) inside `transform/04_punches.py` via `pandas.read_sql`/`to_sql` or pure
`executescript` — final call at implementation; SQL preferred for mentor explainability.
Order matters: **map first (Rule 8), then drift-correct (Rule 11), then dedupe (Rule 9)** —
dedupe on uncorrected times would merge wrong pairs across the drift boundary.

## R4. Device clock drift detection & correction ✅ DECIDED — Rule 11

- Detection: group mapped punches by `device_id`, compute average **check-in proxy** = for each
  employee-day, first punch of the day; compare that per-device mean first-punch time against the
  expected shift start (from roster) → the faulty device shows a constant offset (~1 hour).
  Equivalent cross-check (case-study hint): `AVG(strftime('%H:%M', punch_time)) BY device` vs
  shift start; also compare pairwise: same employee working same shift rarely punches elsewhere.
- Correction: apply the discovered constant offset (e.g., −60 min or +60 min) to that device's
  punches in staging; log device, offset, method, before/after evidence in
  `staging.drift_corrections` → written up in README ("explain how you found it").

## R5. Night-shift date attribution ✅ DECIDED — Rules 7, 10

- Build `shift_date`: for NIGHT, if clock time < 12:00 attribute to the previous calendar
  day (the shift started the previous 22:00), else keep the same date. This is the R5 −6h
  intent exact: −6h alone covers only [00:00, 06:00) — 06:10 − 6h = 00:10 the same day —
  so the 06:00–06:30 check-out stragglers in the data need the full previous-day step
  (implemented in `transform/04_punches.py` part D). Pairing (first/last) runs per
  `(emp_id, shift_date)` after attribution.
- Spillover verified: 1 Oct early check-outs must land on 30 Sep (data contract note in
  `biometric_punches.contract.md`).

## R6. Missing roster weeks (gap-fill) ✅ DECIDED — Rule 6

`shift_code` forward-filled per employee ordered by `week_start` (window `LAST_VALUE(… IGNORE
NULLS)` or pandas `groupby.ffill`). Fallback for employees whose first week is missing: Rule 5
default — Head Office/managers → `GEN`; plant workers → `DAY` pending profiling. Profile first
(docs/profile_notes.md) to confirm how many such cases exist (OPEN only if data contradicts).

## R7. SCD2 dimension build & join ✅ DECIDED — Rule 2

- Sort history by `(emp_id, effective_from)`; `valid_from = effective_from`;
  `valid_to = LEAD(effective_from) - 1 day` (null for latest) — implements "valid until day
  before next record starts", ignoring unreliable `effective_to`.
- Join facts: `work_date >= valid_from AND work_date <= COALESCE(valid_to, '9999-12-31')`.
- Overlap detection is a DQ check (FR-050): count rows where `valid_to >= next valid_from`.
- Month-end attribution (Rule 3): for each employee-month pick SCD2 row containing
  `last_day(month)` or last working day if separated.

## R8. Leave JSON flattening ✅ DECIDED — Rules 16, 17

- `pd.json_normalize(requests, record_path='approvals', meta=[…])` for steps; separate requests
  frame for header fields; `cancelled_at` empty + both steps `Approved` (Manager → HR order)
  ⇒ `is_counted`.
- Day expansion: `pd.date_range(from, to)` per approved request, then anti-join
  `holidays` (plant scope + ALL) and drop Sundays → `staging.leave_days`.
- Never use `days_requested` for counting (contract note).

## R9. Attendance day spine ✅ DECIDED — Rules 4, 12

Grain: every `(emp_id, day)` from `hire_date` (clamped to 2026-04-01) through
`min(separation_date, 2026-09-30)`. Build via SQL `WITH RECURSIVE` or pandas cross-join filtered
— pandas chosen (date spine already in memory for dim_date). Status priority implemented as
CASE WHEN chain in exact Rule-12 order.

## R10. Overtime & half-hour rounding ✅ DECIDED — Rules 14, 15

- Working day: `ot_min = max(0, checkout − shift_end)`; `ot_hours = floor(ot_min / 30) * 0.5`.
- Sunday/holiday worked: `ot_hours = floor((checkout − checkin) / 30) * 0.5` (all OT).
- Guard: reject rows with `checkout < checkin` unless night-shift-normalized (16h cap, DQ check).

## R11. Payroll pivot & cost ✅ DECIDED — Rules 20, 21

- `SUM(CASE WHEN component='OVERTIME' THEN units END)` → paid OT hours;
  `SUM(CASE WHEN component_type='EARNING' THEN amount END)` → payroll cost (deductions are
  positive numbers typed DEDUCTION — subtract only if explicitly modeling net; Q9 uses earnings
  per Rule 21).

## R12. Attrition denominator, absenteeism exclusions (Q2/Q3) — OPEN? NO, resolved by rules

- Q2: separations in month ÷ average of (month-start headcount, month-end headcount)
  [standard HR definition; document choice in q02 header comment].
- Q3: `Absent / (eligible working days − approved leave days − holidays − weekly offs)` per
  plant-month from `attendance_daily`. Documented in query header so Q&A can defend it.
- If answer-key mismatch suspected → mentor clarifies definition (Rule: ask mentors about rules).

## R13. Timeboxing & build order (rubric-weighted) ✅ DECIDED

1. Scaffold + DDL + Stage 1 (Checkpoint 1) → 2. cleaning + attendance → 3. warehouse + Q5–Q8
   (CFO story core, per PDF hint) → 4. Q1–4, Q9–10 (Checkpoint 2) → 5. DQ → 6. README/CFO/deck.
Bonus tasks only after Gate P prerequisites are green.

## Profiling checklist (before any cleaning — PDF hint)

Per file: `df.info()`, `df.dtypes`, null counts, `value_counts()` on categorical/status/plant/
department/shift/leave type/component, distinct date-format regex per date column, duplicate-key
counts (`emp_id`, `punch_id`, `line_id`), min/max dates, roster week gap histogram, punch gap
histogram per device, device→employee map orphans. Output → `docs/profile_notes.md`, which feeds
the planted-issues inventory (SC-003 evidence).

## Environment facts (verified this session)

- Python 3.13.7 installed; `pypdf` present; pandas/SQLAlchemy to be pinned in requirements.
- Repo `D:\Ali\Smit Hackathon` on branch `001-hr-pipeline`; data in `data/` (13 files, ~25 MB).
- Network to GitHub flaky (raw/API worked, clone failed) — no runtime dependency on network.
