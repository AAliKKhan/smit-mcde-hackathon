---
id: 002
title: Recon dataset repo and plan next steps
stage: plan
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: 001-hr-pipeline
user: hackathon-participant
command: (repo recon request)
labels: [recon, github, planning]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: null
  adr: null
  pr: null
files:
 - specs/001-hr-pipeline/research.md (later)
tests: none
---

## Prompt

> https://github.com/aiwithqasim/data-hackathon.git this is the github repo provided for data we have to use in hackathon , check all files and tell me what next we should do

## Response snapshot

`git clone` hung/failed (network resets); pivoted to GitHub API (`git/trees`, `contents`)
endpoints — listed all 13 files (12 datasets + `data_dictionary.md`, ~25 MB), fetched and read
the full 21-rule data dictionary, sampled `departments.csv`/`shifts.json`/`holidays.csv`, and
delivered an 8-hour execution plan (scaffold → profile → stages 1–6, Q5–Q8 first, time-boxed by
rubric weight).

## Outcome

- ✅ Impact: dataset + rules understood; rubric-weighted build order agreed
- 🧪 Tests: row-count expectations captured for later Gate R
- 📁 Files: read-only API fetches (temp)
- 🔁 Next prompts: 003 local download
- 🧠 Reflection: API fallback beats retrying clone on flaky networks; keep raw/API/codeload as
  ordered fallbacks

## Evaluation notes (flywheel)

- Failure modes observed: `git clone` RPC reset twice; `Invoke-WebRequest` requires
  `-UseBasicParsing` in PS 5.1 non-interactive; PS 5.1 lacks ternary and multi-arg `Join-Path`
- Graders run and results: n/a
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): n/a
