# Quickstart: 001-hr-pipeline (Phase 1)

One-page rebuild + verification guide. Mirrors `README.md` (which is written last for mentors).

## Prerequisites

- Python 3.10+ (3.13 verified), ~500 MB free disk, no database server required (SQLite file).
- Network needed **once** for `pip install` only; runtime is fully offline.

## Rebuild from raw files (clean machine)

```powershell
git clone <our-public-repo> indus-weave-hr-pipeline
cd indus-weave-hr-pipeline
python -m venv .venv; .\.venv\Scripts\Activate.ps1     # or python3 -m venv .venv (mac/linux)
pip install -r requirements.txt
python run_pipeline.py                                  # Stages 1→6, one command
```

Expected: console prints per-file raw row counts (all green), staging build messages, warehouse
load counts, 10 query results, and a final `DQ: all checks PASS`.

## Stage-by-stage (for debugging / parallel teammate work)

```powershell
python -m warehouse.ddl.apply          # schemas + DDL          (or run warehouse/ddl/*.sql)
python -m ingestion.load_raw           # Stage 1 → raw.*        Gate R
python -m ingestion.counts             # expected vs actual row counts (exit ≠ 0 on mismatch)
python -m ingestion.profile            # docs/profile_notes.md  (profiling evidence)
python -m transform.build              # Stage 2+3 → staging.*  Gate S + A
python -m warehouse.build_warehouse    # Stage 4 → warehouse.*  Gate W
python -m analytics.run_all            # Stage 5 → analytics/results/qNN_*.csv   Gate Q
python -m quality.run_dq               # Stage 6 → dq_results   Gate D
```

Every step is idempotent (rebuild semantics) — rerun any step safely.

## Verify success in 60 seconds

```sql
-- 1) row counts matched (Gate R evidence)
SELECT * FROM dq_results WHERE check_id LIKE 'RAW_COUNT%';

-- 2) every raw row accounted for (SC-002)
SELECT check_id, status, failure_count FROM dq_results
 WHERE layer = 'reconciliation' ORDER BY check_id;

-- 3) all checks green
SELECT status, COUNT(*) FROM dq_results GROUP BY status;   -- expect PASS only

-- 4) CFO numbers present
SELECT COUNT(*) FROM analytics CSVs ...  -- 10 files in analytics/results/
```

Python one-liner (no sqlite3 CLI needed):

```powershell
python -c "import sqlite3;c=sqlite3.connect('db/indus_weave.db');print(c.execute(\"SELECT status,COUNT(*) FROM dq_results GROUP BY status\").fetchall())"
```

## Deliverable map → rubric

| Artifact | Rubric criterion |
|---|---|
| `ingestion/`, `requirements.txt`, README | Code quality & reproducibility (10) |
| `transform/` + logs/quarantines | Cleaning & business logic (20) |
| `warehouse/ddl/`, `warehouse/erd.png` | Data model (15) |
| `dq_results` via `quality/` | Data quality & reconciliation (15) |
| `analytics/q01…q10` + `results/*.csv` | Correct answers (25) |
| `presentation/cfo_findings.md`, `slides.pdf` | CFO findings & demo (15) |

## Troubleshooting

- **FK errors in SQLite** → connections must run `PRAGMA foreign_keys = ON` (handled in
  `warehouse/ddl/apply.py`; if testing manually, set it per connection).
- **Counts mismatch after data change** → do NOT edit `data/`; investigate in
  `docs/profile_notes.md`, ask a mentor.
- **Stale DB** → `db/indus_weave.db` can be deleted any time; `run_pipeline.py` recreates it.
- **Windows console Unicode** → scripts write UTF-8 files explicitly; console output is ASCII.
