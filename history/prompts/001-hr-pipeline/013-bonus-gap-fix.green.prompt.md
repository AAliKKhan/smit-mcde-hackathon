---
id: 013
title: Guide gap fix: Q9 per-employee grain + three bonus tasks
stage: green
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: main
user: hackathon-participant
command: "go"
labels: [bonus, q9, incremental-load, funnel, dashboard]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: specs/001-hr-pipeline/tasks.md#T061-T064
  adr: null
  pr: null
files:
 - analytics/q09_payroll_cost_mom.sql
 - analytics/b01_recruitment_funnel.sql
 - analytics/run_all.py
 - ingestion/load_incremental.py
 - tests/test_incremental.py
 - dashboard/__init__.py
 - dashboard/build_dashboard.py
 - dashboard/index.html
 - README.md
 - specs/001-hr-pipeline/tasks.md
---

## Prompt

"go" (twice) - approve the gap-fix plan from the guide-PDF audit: rewrite Q9 to
match the guide wording ("Payroll cost per employee by department, with
month-over-month change") and implement the three remaining guide bonus tasks
(7th-month incremental load, recruitment funnel from applications.csv, HTML
dashboard over warehouse.*).

## Outcome

- Q9 rewritten to employee x month grain (dept as column, LAG partition by emp_id):
  7,233 rows, mom_change_abs/mom_change_pct.
- b01_recruitment_funnel.sql: 1400 -> 682 -> 263 -> 90 -> 74; conversion
  48.7/38.6/34.2/82.2%; median days in stage 9/8/9/8 (ROW_NUMBER median, SQLite).
- run_all.py discovery q*.sql -> *.sql (now 11/11 queries OK).
- load_incremental.py: append-only delta on a key, idempotent (345,280 read /
  0 appended on the real punches file), in-file dedupe, _source_file/_row_hash.
- test_incremental.py: seed -> re-run idempotent -> +2 delta -> dedupe; 33/33 tests.
- dashboard/build_dashboard.py -> index.html: KPIs (1,176 / 90 / PKR 695.0M /
  PKR 19.0M / 58 DQ), headcount/payroll/absenteeism bars, OT overage table,
  three finding numbers (2,758 h / 2,879,197 / 1,948,000).
- Two SQL bugs found by the dashboard's own numbers and fixed: att CTE
  GROUP BY emp_id,1 collapsed months (ordinal 1 = emp_id, not m); SCD2
  valid_to is NULL for separated employees so headcount switched to Rule 4
  (hire_date/separation_date on is_current rows) = 1,176.
- tasks.md Phase 11 (T061-T064) all [x]; README run-block, repo map,
  rubric bonus row and test counts updated.
