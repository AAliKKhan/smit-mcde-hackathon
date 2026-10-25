---
id: 010
title: US5 ten business queries, Gate Q
stage: green
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: main
user: hackathon-participant
command: "continue"
labels: [implementation, analytics, sql, cfo, gate-q]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: specs/001-hr-pipeline/tasks.md#T037-T048
  adr: null
  pr: null
files:
 - analytics/run_all.py
 - analytics/q01_month_end_headcount.sql
 - analytics/q02_monthly_attrition.sql
 - analytics/q03_absenteeism.sql
 - analytics/q04_top_late_arrivals.sql
 - analytics/q05_overtime_computed_vs_approved_vs_paid.sql
 - analytics/q06_dept_paid_over_computed_15pct.sql
 - analytics/q07_paid_zero_attendance.sql
 - analytics/q08_pay_after_separation.sql
 - analytics/q09_payroll_cost_mom.sql
 - analytics/q10_leave_overuse.sql
 - analytics/results/ (10 CSVs)
 - specs/001-hr-pipeline/tasks.md
tests:
 - python -m analytics.run_all (10/10 non-empty)
 - spot reconciliation: q05 paid 36,401.5 == payroll OVERTIME units
---

## Prompt

> continue

(continuation; definition decisions documented in each query header per FR-045)

## Response snapshot

T037–T048: run_all discovers q*.sql, executes, exports results/*.csv, exit 1
on failure/empty. Q1 headcount 1199→1176 (Rule 4 literal), Q2 separations ÷
avg(start,end), Q3 Absent ÷ (Present+Absent+MissingPunch), Q4 late arrivals
(RN window), Q5 per emp-month computed/approved/paid, Q6 departments paid >
computed × 1.15 (**D20 Stitching only**: 7,659 paid vs 4,901 computed, ratio
1.5627), Q7 zero-worked-hour paid months (**58 / 12 emps / PKR 4,827,197**),
Q8 post-separation pay (**5 emps / 21 months / PKR 1,948,000**; settlement
month excluded), Q9 payroll cost MoM, Q10 leave overuse (20 employees, top
E10770 28 vs 14). Row counts 150/150/24/10/150/1/58/21/150/20. Gate Q PASS.

## Outcome

- ✅ Impact: Checkpoint 2 delivered — all 10 graded answers produced and
  reconciled; CFO story (Q5–Q8) numbers now fixed
- 🧪 Tests: run_all exit 0; Q5↔payroll reconciliation exact
- 📁 Files: 22 written/edited (11 SQL + runner + 10 CSVs)
- 🔁 Next prompts: US6 DQ proof (T049–T051 → Gate D)
- 🧠 Reflection: FULL-OUTER emulation via dim×months grid + LEFT JOIN kept
  month-coverage complete (150 rows) instead of INNER JOIN dropping
  zero-payroll combinations

## Evaluation notes (flywheel)

- Failure modes observed: pandas sqlite paramstyle (`:name` with dict, not
  `$name`) cost one debug cycle
- Graders run and results (PASS/FAIL): Gate Q PASS
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): wire all check families into one
  dq_results run and prove a seeded failure flips FAIL
