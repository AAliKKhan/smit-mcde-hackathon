# Indus Weave HR Pipeline Constitution

Governing principles for the PeopleOps Data Hackathon project `indus-weave-hr-pipeline`.
This constitution supersedes personal preference whenever a trade-off arises during implementation.

## Core Principles

### I. Rule Wins
The 21 business rules in `data/data_dictionary.md` are the law of this project. Where the raw data
disagrees with a rule, the rule wins — every time, no exceptions. Every transformation must be
traceable to a numbered rule (cite the rule number in code comments and docs where non-obvious).
Ambiguity in rules is resolved by asking mentors, never by guessing silently.

### II. Raw is Immutable
Files under `data/` are never edited, renamed, or moved — not even to fix a typo, a date format,
or a casing issue. All fixes happen in code, downstream of the `raw` schema. The `raw` schema is a
faithful copy of the delivery: every column as TEXT, every row as delivered, with load metadata
(`_source_file`, `_loaded_at`, `_row_hash`). Raw data is always reproducible from `data/`.

### III. Correctness First
Grading weights matching the hidden answer key highest (25 points). When forced to choose between
correct numbers and cosmetic polish, choose correct numbers. Every stage must reconcile: raw row
counts = staged + rejected, for every table, verified by automated checks — not by eyeballing.
No result ships without its reconciliation evidence.

### IV. Idempotent and Rebuildable
Every script must be safe to run twice: loads deduplicate via `_row_hash`, transforms rebuild their
outputs from their inputs (create-or-replace, not blind append), and the whole pipeline rebuilds
from raw files to answers with one command (`python run_pipeline.py`). A mentor on a clean machine
must succeed by following only `README.md`.

### V. Code Only
No manual edits to any dataset file, no hand-crafted result CSVs, no numbers typed from memory into
deliverables. If a result appears anywhere, a committed script produced it. Every fix, every
correction (including the device clock drift) is an explicit, reviewable code change.

### VI. Explainable Code
AI assistance is allowed, but every line must be defensible in Q&A: a team member can say what it
does and why. Prefer small, readable functions, explicit rule references, and CTE-named SQL over
clever compression. If a construct cannot be explained, rewrite it.

## Constraints

- **Stack**: Python 3 (pandas, SQLAlchemy/psycopg2, stdlib) + SQL only. No Spark, no Airflow,
  no BI tools for Stages 1–6. Any PyPI library otherwise permitted.
- **Database**: SQLite (explicitly allowed by the case study) unless requirements change;
  foreign keys enforced via `PRAGMA foreign_keys = ON`.
- **Scope**: Stages 1–6 + deliverables are in scope; bonus tasks (incremental 7th-month load,
  recruitment funnel, dashboard) only after all in-scope items are green.
- **Timebox**: 8-hour hackathon. Effort is allocated by rubric weight:
  answers 25 > cleaning 20 > model 15 = DQ 15 = CFO story 15 > code 10.
- **Data coverage**: 1 Apr – 30 Sep 2026, 12 files + dictionary, all synthetic.

## Quality Gates

A phase is not "done" until its gate passes; gates are checked before moving on:

1. **Gate R (Raw)**: all 12 files loaded; row counts match the case study exactly;
   `_row_hash` idempotency proven by a double-run producing identical counts.
2. **Gate S (Staging)**: every staging table equals raw + rejected reconciliation;
   dedupe log written; drifted device detected and corrected with explanation;
   typed ISO dates everywhere; no NULLs in required keys.
3. **Gate A (Attendance)**: every employee-day has exactly one row and one valid status;
   no negative worked hours; no shift > 16 hours; night shifts attributed to start date.
4. **Gate W (Warehouse)**: all PK/FK enforced and verified; SCD2 ranges non-overlapping;
   ERD committed.
5. **Gate Q (Questions)**: all 10 queries run green; each has a CSV in `analytics/results/`.
6. **Gate D (DQ)**: `dq_results` fully populated after a run; every raw row accounted for.
7. **Gate P (Presentation)**: 3 findings each with number + evidence query + action;
   README rebuild instructions verified end-to-end; demo fits 5 minutes.

## Development Workflow

- Work through Spec Kit artifacts in order: constitution → spec → plan → tasks → implementation.
  A requirement not in `spec.md` does not get built; a build not in `tasks.md` gets added there first.
- Record a Prompt History Record (PHR) under `history/prompts/<feature>/` for every user prompt
  per `opencode.md`.
- Suggest an ADR whenever a decision passes the significance test (long-term impact +
  multiple viable alternatives + cross-cutting scope); never auto-create one.
- Commit after each completed task group with a message referencing the task IDs.
- Checkpoint 1 (end Day 1): Gate R + staging underway. Checkpoint 2 (Day 2 midday):
  Gate W + ≥5 questions answered. Code freeze: repo link submitted.

## Governance

- This constitution governs all project artifacts and code; conflicts are resolved in favor of
  this file and then the data dictionary.
- Amendments require a PHR documenting the change, the reason, and the rubric/timebox impact —
  approved by the team before adoption.
- Any deliverable that violates Raw is Immutable or Code Only is rejected regardless of quality.
- Runtime development guidance lives in `opencode.md`; templates live in `.specify/templates/`.

**Version**: 1.0.0 | **Ratified**: 2026-10-25 | **Last Amended**: 2026-10-25
