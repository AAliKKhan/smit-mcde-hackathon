---
id: 004
title: Adopt spec-driven development method
stage: spec
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: 001-hr-pipeline
user: hackathon-participant
command: (SSD request; plan-mode Q&A)
labels: [spec-kit, sdd, planning]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - .specify/ (templates + scripts inspected)
 - .specify/memory/constitution.md (drafted in plan)
tests: none
---

## Prompt

> follow SSD method first write specs , constitution , then follow whole spec kit plus spec driven method to fully achieve what is asked

## Response snapshot

Inspected `.specify/` (templates: spec/plan/tasks/adr/checklist/phr; scripts:
`create-new-feature.ps1` etc.; `commands/` absent → `/sp.*` not wired, workflows run manually per
`opencode.md`). Confirmed requirements understood + readiness gaps (code 0%). Presented a
7-phase SSD plan (constitution → feature branch → spec → plan+artifacts → tasks → ADRs →
execute). Asked 2 decisions: **feature granularity → one feature `001-hr-pipeline`**;
**database → SQLite**.

## Outcome

- ✅ Impact: method + scope decisions locked; plan approved by user ("go")
- 🧪 Tests: n/a
- 📁 Files: none yet (read-only planning)
- 🔁 Next prompts: 005 artifact build
- 🧠 Reflection: confirming template inventory + missing commands dir up front prevented
  promising `/sp.*` commands that don't exist

## Evaluation notes (flywheel)

- Failure modes observed: n/a
- Graders run and results: n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
