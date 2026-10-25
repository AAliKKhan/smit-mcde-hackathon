---
id: 012
title: US7 deliverables and demo pack, Gate P
stage: explainer
date: 2026-10-25
surface: agent
model: opencode/mimo-v2.6-flash-free
feature: 001-hr-pipeline
branch: main
user: hackathon-participant
command: "continue"
labels: [deliverables, readme, cfo-findings, slides, demo, gate-p]
links:
  spec: specs/001-hr-pipeline/spec.md
  ticket: specs/001-hr-pipeline/tasks.md#T052-T056
  adr: null
  pr: null
files:
 - run_pipeline.py
 - README.md
 - presentation/cfo_findings.md
 - presentation/make_slides.py
 - presentation/slides.pdf
 - presentation/slides/slide-01.png
 - presentation/slides/slide-02.png
 - presentation/slides/slide-03.png
 - presentation/slides/slide-04.png
 - presentation/slides/slide-05.png
 - presentation/slides/slide-06.png
 - presentation/demo_script.md
 - requirements.txt
 - specs/001-hr-pipeline/tasks.md
tests:
 - python run_pipeline.py from clean db/ (6/6 stages, exit 0, 155.8 s)
 - python -m quality.run_dq (58/58 PASS final)
 - pytest tests/ (32/32)
---

## Prompt

> What did we do so far?

> Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.

## Response snapshot

T052–T056 + T059: `run_pipeline.py` (six stages, `--stage N`, per-stage
timing, advisory DQ after every load / strict at stage 6, exit ≠ 0 on any
gate failure); `README.md` (mentor rebuild, design decisions, drift
write-up, 21-rule citation map, rubric map, team); `presentation/cfo_findings.md`
(exactly 3 findings: Stitching +2,758 h / ≈PKR 1.36 m, zero-attendance
PKR 2,879,197, post-separation PKR 1,948,000 — each with number, full
evidence SQL, action); `slides.pdf` 6 slides via PIL renderer (auto-fit
titles/bullets; PNGs committed); `demo_script.md` 5-minute rehearsed script
with Q&A parking lot. T059 green run from deleted `db/`: 6/6 OK, 155.8 s,
10 CSVs, 58/58 PASS, exit 0. requirements.txt pins pillow==11.3.0.

## Outcome

- ✅ Impact: Gate P candidate — full demo pack regenerable by one command
- 🧪 Tests: 32/32 + clean-run exit 0
- 📁 Files: 14 written/edited (listed above)
- 🔁 Next prompts: T058 PHRs (this file), T060 README render check, push
- 🧠 Reflection: advisory-vs-strict DQ split avoids false aborts mid-pipeline
  (stage-1 recon correctly "fails" because staging is not loaded yet) while
  keeping the final gate honest

## Evaluation notes (flywheel)

- Failure modes observed: PIL slide layout — long titles clipped and last
  bullet collided with footer; fixed with measure-and-shrink fonts
- Graders run and results (PASS/FAIL): all gates PASS (R, S, A, W, Q, D)
- Prompt variant (if applicable): n/a
- Next experiment (smallest change to try): push and verify README rendering
  on GitHub
