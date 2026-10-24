# ADR-001: Storage & Pipeline Stack (SQLite + pandas + SQLAlchemy)

- **Status:** Accepted
- **Date:** 2026-10-25
- **Feature:** 001-hr-pipeline
- **Context:** The case study mandates Python 3 + SQL and allows SQLite when a team cannot run
  PostgreSQL. We have 8 hours, mixed-skill teams, and a rubric whose largest weight is correct
  answers, not infrastructure. Rebuild-on-clean-machine is graded (10 pts).

## Decision

- **Database**: SQLite single file `db/indus_weave.db`, schemas `raw`/`staging`/`warehouse` +
  `dq_results` table; `PRAGMA foreign_keys = ON` on every connection.
- **Language layer**: Python 3 with pandas for file handling and orchestration; all set-based
  transformations (dedupe, statuses, SCD2, pivots, the 10 questions) written as SQL executed via
  sqlite3/SQLAlchemy.
- **Dependency surface**: `pandas`, `sqlalchemy`, `pytest` — pinned in `requirements.txt`.
- **Date spine**: pandas `date_range` → rows inserted (SQLite has no `generate_series()`).

## Consequences

### Positive

- Zero-install database: any mentor laptop runs the demo; clean-machine rebuild is a venv + two
  commands (directly serves SC-008).
- No Docker/network dependence — resilient given flaky network observed during setup.
- SQLite enforces the graded integrity model (PK/FK/`CHECK` + `foreign_key_check`), which is
  what Stage 4 judging inspects.
- pandas handles the awkward file shapes (nested JSON, mixed date formats) quickly.

### Negative

- No `generate_series()`/`INTERVAL` → date arithmetic lives partly in Python.
- Single-connection writer: no parallel loads (irrelevant at 345k rows / <10 min budget).
- `PRAGMA foreign_keys` is per-connection — must be centralized in `common/db.py` or FKs
  silently don't apply (known SQLite footgun, mitigated by DQ RI checks).

## Alternatives Considered

- **PostgreSQL (local/Docker)**: closer to a real warehouse, `generate_series()`; rejected —
  install/setup cost on unknown mentor machines + Docker availability risk eats the timebox.
- **DuckDB**: excellent analytics speed; rejected — less familiar to mentors/judges, weaker
  "warehouse with enforced PK/FK" story for Stage 4.
- **Pure pandas, no SQL**: fastest to write; rejected — Stage 5 explicitly requires SQL files
  with CTEs/window functions and Stage 4 requires enforced keys.

## References

- Feature Spec: specs/001-hr-pipeline/spec.md (FR-025, FR-059)
- Implementation Plan: specs/001-hr-pipeline/plan.md (Constitution Check, Technical Context)
- Research: specs/001-hr-pipeline/research.md (R1, R13)
- Related ADRs: ADR-002 (attendance-day model)
