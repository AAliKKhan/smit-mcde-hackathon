---
id: 008
title: US3 attendance engine, Gate A
stage: green
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: main
user: hackathon-participant
command: "continue"
labels: [implementation, stage3, attendance, adr-002, gate-a]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: specs/001-hr-pipeline/tasks.md#T025-T029
  adr: history/adr/ADR-002-attendance-day-model.md
  pr: null
files:
 - transform/07_attendance_daily.py
 - history/adr/ADR-002-attendance-day-model.md
 - quality/checks.py
 - tests/test_staging_invariants.py
 - specs/001-hr-pipeline/tasks.md
tests:
 - pytest (21 passed after stage-3 fixes)
 - python -m quality.checks (attendance_checks 7 PASS)
---

## Prompt

> continue

(continuation of the same implementation push)

## Response snapshot

T025–T029: one attendance row per employee-day (217,584 = spine), status
CASE chain per Rule 12 priority, late/early per Rule 13, OT Rules 14/15
(floor to half-hours), night punches attributed to shift start (Rule 7).
Two rounds: WIP commit fixed FK-safe stage-3 rebuild and night attribution
(Missing Punch 23,052 → 2,841); ADR-002 written (12.5 h session window,
16 h cap). Second commit added session-based shift attribution and Gate A
attendance checks (7 checks PASS). Final status totals: Present 159,825 /
Weekly Off 30,321 / Holiday 10,759 / On Leave 8,604 / Absent 5,582 /
Missing Punch 2,493.

## Outcome

- ✅ Impact: attendance model finished — Gate A green, data ready for facts
- 🧪 Tests: 21 passed + 7 attendance checks PASS
- 📁 Files: 5 written/edited (listed above)
- 🔁 Next prompts: US4 star warehouse (T030–T036 → Gate W)
- 🧠 Reflection: the first night-attribution fix (pre-noon heuristic) was
  still wrong for late-evening EVE punches — ADR-002 records why session
  attribution, not clock-time heuristics, is the defensible rule

## Evaluation notes (flywheel)

- Failure modes observed: rule-7 attribution initially under-counted Missing
  Punch by 20k rows; caught by comparing status totals against expectations
- Graders run and results (PASS/FAIL): Gate A PASS
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): load facts and prove parity
  between staging status totals and fact_attendance_daily
