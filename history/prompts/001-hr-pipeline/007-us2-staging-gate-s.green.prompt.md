---
id: 007
title: US2 staging transforms, Gate S
stage: green
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: main
user: hackathon-participant
command: "continue"
labels: [implementation, stage2, cleaning, rules-1-21, gate-s]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: specs/001-hr-pipeline/tasks.md#T015-T024
  adr: null
  pr: null
files:
 - transform/build.py
 - transform/util.py
 - transform/01_clean_employees.py
 - transform/02_clean_history.py
 - transform/03_clean_reference.py
 - transform/04_punches.py
 - transform/05_leave.py
 - transform/06_overtime_payroll.py
 - docs/drift_analysis.md
 - docs/history_repairs.md
 - tests/test_staging_invariants.py
 - specs/001-hr-pipeline/tasks.md
tests:
 - pytest tests/test_staging_invariants.py (21 passed)
 - python -m quality.checks (reconciliation + step checks PASS)
---

## Prompt

> continue

(continuation; constraint: "really less time left" — T057 profiling folded
into this phase)

## Response snapshot

T015–T024: rules 1–3, 5–6, 8–11, 16–21 implemented as stages 01–06 —
dedupe by updated_at (50 ids), mixed-date parsing (0 failures), department
canonicalisation, SCD2 effective_to recompute (25 overlap + 12 gap rows,
37 employees, docs/history_repairs.md), roster gap-fill (2,844 weeks +
769 Rule-5 defaults), punch mapping with rejected quarantine (6,962 unmapped +
16,175 collapsed), device-drift correction (DEV-SITE-01 −30 min,
docs/drift_analysis.md), leave Rule 16/17 (4,282 counted, 1,616
sundays/holidays skipped), OT/payroll Rules 19–21 (19,666 approved,
36,401.5 paid hours). Gate S PASS: reconciliation raw = staging + rejected
for all 13 tables, 21/21 tests.

## Outcome

- ✅ Impact: staging layer trusted; Checkpoint 1 complete and signed off
- 🧪 Tests: test_staging_invariants 21 passed; quality.checks green
- 📁 Files: 13 written/edited (listed above)
- 🔁 Next prompts: US3 attendance engine (T025–T029 → Gate A)
- 🧠 Reflection: computing drift per-device from first-punch deltas vs roster
  start (mean, not median) made the +30 min outlier unmistakable; correction
  recomputed each run instead of hard-coded

## Evaluation notes (flywheel)

- Failure modes observed: none in gates; drift detection deliberately
  conservative (samples outside [−120, +240] min excluded)
- Graders run and results (PASS/FAIL): Gate S PASS
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): build attendance and compare
  Missing Punch counts before/after sessionisation
