-- 00_schemas.sql — cross-layer objects in `main` (Stage 1 prerequisite, T005)
--
-- SQLite has no CREATE SCHEMA: raw/staging/warehouse are ATTACHed databases
-- (db/raw.db, db/staging.db, db/warehouse.db) wired up by common/db.py.
-- This file only creates objects that live in main: the DQ results table (Stage 6).

CREATE TABLE IF NOT EXISTS dq_results (
  run_id        TEXT    NOT NULL,
  check_id      TEXT    NOT NULL,
  layer         TEXT    NOT NULL CHECK (layer IN
                    ('raw','staging','warehouse','reconciliation','sanity')),
  target        TEXT    NOT NULL,
  status        TEXT    NOT NULL CHECK (status IN ('PASS','FAIL')),
  failure_count INTEGER NOT NULL DEFAULT 0,
  detail        TEXT,
  checked_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dq_results_run  ON dq_results(run_id);
CREATE INDEX IF NOT EXISTS idx_dq_results_chk  ON dq_results(check_id, status);
