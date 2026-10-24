---
id: 003
title: Download dataset pack locally
stage: misc
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: 001-hr-pipeline
user: hackathon-participant
command: (download request + several "go" retries)
labels: [data, download, tooling]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - data/ (13 files)
tests: none
---

## Prompt

> first i want all required file from the github repo locally here in this directory so we can start builiding when i say  … [plan-mode pause] … go … (aborted run) … i have added them manually from repo , now tell me whats next

## Response snapshot

Attempted clone → failed; API-loop → user aborted during slow base64 writes; DNS intermittently
failed then recovered; curl from `raw.githubusercontent.com` downloaded 8/13 files before abort.
**User added the remaining files manually.** Final state verified: all 13 files in `data/`
(~25 MB) with plausible sizes; next-step plan presented (scaffold + Stage 1).

## Outcome

- ✅ Impact: dataset pack complete locally — unblocks implementation
- 🧪 Tests: n/a (size sanity check + later Gate R row counts)
- 📁 Files: `data/*` (user-completed)
- 🔁 Next prompts: 004 spec-driven method
- 🧠 Reflection: flaky campus network makes single-request-per-file with retries essential;
  manual user fallback was fastest resolution — confirm data presence before assuming success

## Evaluation notes (flywheel)

- Failure modes observed: `git clone` RPC failure; DNS `could not be resolved` intermittents;
  long silent loops look like hangs (no incremental output) → print per-file progress
- Graders run and results: n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): write progress to log file during long downloads
