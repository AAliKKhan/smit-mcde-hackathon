-- 30_indexes.sql — staging/warehouse query-performance gaps (T009)
-- Applied AFTER loads (idempotent). Most indexes are declared with their tables
-- in 10_staging.sql / 20_warehouse.sql; raw.* indexes are created by
-- ingestion/load_raw.py because raw tables are rebuilt (DROP+CREATE) each run.
-- SQLite syntax rule (verified): CREATE INDEX <schema>.<ix> ON <table>  - the
-- index name carries the schema, the table name must be unqualified.

CREATE INDEX IF NOT EXISTS staging.ix_ot_emp_status    ON overtime_requests(status, ot_date);
CREATE INDEX IF NOT EXISTS staging.ix_pay_comp_month   ON payroll_lines(component, payroll_month);
CREATE INDEX IF NOT EXISTS staging.ix_leave_days_date  ON leave_days(day_date);
CREATE INDEX IF NOT EXISTS staging.ix_appl_dept        ON applications(dept_id, stage);
CREATE INDEX IF NOT EXISTS staging.ix_dedupe_emp       ON employees_dedupe_log(emp_id);
CREATE INDEX IF NOT EXISTS staging.ix_rej_reason       ON rejected_punches(reason);
