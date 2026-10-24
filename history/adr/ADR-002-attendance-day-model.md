# ADR-002: Attendance Day Model (night attribution, status priority, OT rounding)

- **Status:** Accepted
- **Date:** 2026-10-25
- **Feature:** 001-hr-pipeline
- **Context:** Attendance is the pivot between 345k raw punches and every graded answer.
  The data dictionary fixes the semantics (Rules 7, 10, 12–15) but leaves the implementation
  shape open: how night punches become a date, how one status is chosen, and how overtime is
  quantized. Getting this wrong silently corrupts Q3–Q8 and the CFO story.

## Decision

Single derived table **`staging.attendance_daily`**, grain `(emp_id, work_date)`, built in a
fixed four-step order:

1. **Day spine**: one row per employee per day from `hire_date` (clamped to 2026-04-01) through
   `min(separation_date, 2026-09-30)` — absentees exist because the spine exists, not because
   punches were missing (Rule 4).
2. **Night attribution before pairing**: for NIGHT-shift days, a punch whose clock time is
   before 12:00 belongs to the shift that started the PREVIOUS evening (22:00), so its date
   steps back one day; all other punches keep their own date (Rules 7, 10). First/last punch
   pair per `(emp_id, work_date)` after attribution. This is R5's −6h intent made exact: a
   fixed −6h covers only [00:00, 06:00), while 06:10 − 6h = 00:10 the same day would strand
   the data's 06:00–06:30 check-out stragglers on the wrong date (and mis-pair them with the
   next shift's check-in, producing ~15 h "worked" spans). With the pre-noon rule, 01-Oct
   06:10 check-outs attribute to 30-Sep shifts as the data contract requires.
3. **Status as a single CASE chain in exact Rule-12 priority**: `Weekly Off` > `Holiday` >
   `On Leave` > `Present` (≥2 punches) > `Missing Punch` (1) > `Absent` (0) — evaluated top-down
   so the first match wins; no status can be double-assigned.
4. **Measures computed from the paired row**: `late_minutes`/`early_leave_minutes` only when
   `status='Present'` (>10 min beyond grace), `ot_hours = floor(minutes/30) × 0.5` for work
   after shift end (Rule 14), and for Sunday/holiday worked time `floor((out−in)/30) × 0.5`
   (Rule 15, all OT). Quantization is **floor to half-hours — never rounding**.

Supporting rules baked into the same build: punches processed **map → drift-correct → 2-min
dedupe → attribute** (order is load-bearing; deduping before drift correction merges wrong
pairs), roster gaps forward-filled before shift lookup (Rule 6), leave days must already exclude
Sundays/holidays (Rule 17) so `On Leave` never shadows `Weekly Off`/`Holiday`.

## Consequences

### Positive

- One table answers absenteeism, lateness, computed OT and present-days — one place to debug,
  one grain to reconcile, one target for DQ (SC-004 invariants are a checklist against one
  relation).
- Priority chain mirrors the dictionary verbatim → explainable in Q&A line-by-line (Principle VI).
- Half-hour flooring matches the graded examples (29→0, 45→0.5, 75→1.0) exactly.

### Negative

- Pre-noon cutoff is a heuristic tied to NIGHT's fixed 22:00–06:00 window (morning punches
  before noon = previous shift's check-out); if a rule amendment changes night hours, step 2
  must change (guarded by drift/night regression fixtures).
- Day spine expands rows to employee-days (~1,300 × 183 ≈ 240k) — negligible for SQLite but
  means absence is *materialized*, costing rebuild time.

## Alternatives Considered

- **Attribute by punch-clock date only**: simpler; rejected — breaks Rule 7 and the 1-Oct
  spillover cases.
- **Statuses as flags (multiple true)**: flexible; rejected — spec demands ONE status per row;
  flags would let Q3 double-count.
- **OT as continuous minutes rounded at query time**: rejected — quantization must happen once
  (Rule 14 "rounded down to whole half-hours") or Q5/Q6 diverge per consumer.
- **Compute statuses in Python, store punches only**: rejected — SQL invariants and mentor
  explainability are stronger when the CASE chain is visible in DDL/SQL text.

## References

- Feature Spec: specs/001-hr-pipeline/spec.md (FR-018…FR-024, US3)
- Data Model: specs/001-hr-pipeline/data-model.md (`staging.attendance_daily`)
- Research: specs/001-hr-pipeline/research.md (R5, R9, R10)
- Rules: data_dictionary.md Rules 4, 6, 7, 10, 12, 13, 14, 15, 17
- Related ADRs: ADR-001 (stack)
