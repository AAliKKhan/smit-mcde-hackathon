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
2. **Session attribution before pairing** (amended 2026-10-25, second revision): group each
   employee's kept punches into shift **sessions**; a new session opens when the punch falls
   in its rostered shift's check-IN window `[start−2h, start+3h)`, when the inter-punch gap
   exceeds 12.5 h, when the span from the session start exceeds `MAX_SHIFT_HOURS` (16 h,
   FR-024), or at the employee boundary. Each session is dated by its **first** punch — the
   date the shift started (Rules 7, 10). Exception: an all-pre-noon session on a NIGHT
   roster is a check-out whose check-in is missing (e.g. a lone 05:18 OUT) and steps back
   one day. This replaced two earlier heuristics: the literal −6h shift (fails for 06:00–06:30
   check-outs: 06:10 − 6h = 00:10 the same day, stranding them and mis-pairing ~15 h spans)
   and a pure gap threshold (an 11.68 h overnight break after a 12.21 h GEN overtime day
   chained two shifts into one 35 h row; a lone NIGHT OUT collided with the same day's real
   night session into a 27 h row). The session model delivers: 01-Oct 06:10 check-outs
   attribute to 30-Sep shifts (contract), EVE check-outs after midnight (00:04–00:20) stay
   with their shift, and **0 attendance rows exceed 16 h**. First/last punch pair per
   `(emp_id, work_date)` after attribution.
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

- Session boundaries are heuristics: the check-IN window `[start−2h, start+3h)`, the 12.5 h
  gap and the 16 h span cap are calibrated to this extract's punch profile (bimodal gap
  histogram, observed IN windows per shift); a rule amendment changing shift hours must
  revisit them (guarded by drift/night regression fixtures and the FR-024 >16 h check).
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
