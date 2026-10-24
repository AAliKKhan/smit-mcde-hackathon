-- 20_warehouse.sql â€” star schema with enforced PK/FK (Stage 4, T008)
-- Lives entirely in attached db/warehouse.db: SQLite rejects qualified REFERENCES,
-- and all FKs here are intra-warehouse (facts -> dims), which is what we need.
-- SCD2 join contract: fact.work_date BETWEEN dim.valid_from AND dim.valid_to (Rule 2).

-- ================================================================= dimensions
CREATE TABLE IF NOT EXISTS warehouse.dim_employee (
  employee_key           INTEGER PRIMARY KEY AUTOINCREMENT,
  emp_id                 TEXT NOT NULL,          -- business key (non-unique: SCD2)
  full_name              TEXT,
  gender                 TEXT,
  date_of_birth          TEXT,
  plant                  TEXT,
  dept_id                TEXT,
  dept_name              TEXT,
  designation            TEXT,
  grade                  TEXT,
  employment_type        TEXT,
  status                 TEXT,
  hire_date              TEXT,
  separation_date        TEXT,
  annual_leave_entitlement INTEGER,
  basic_salary           REAL,
  change_reason          TEXT,
  valid_from             TEXT NOT NULL,
  valid_to               TEXT,                   -- inclusive; NULL = open (treated 9999-12-31)
  is_current             INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0,1))
);
CREATE INDEX IF NOT EXISTS warehouse.ix_dim_emp_biz   ON dim_employee(emp_id, valid_from);
CREATE INDEX IF NOT EXISTS warehouse.ix_dim_emp_valid ON dim_employee(valid_from, valid_to);

CREATE TABLE IF NOT EXISTS warehouse.dim_department (
  dept_id      TEXT PRIMARY KEY,
  dept_name    TEXT NOT NULL,
  plant        TEXT NOT NULL,
  cost_center  TEXT,
  previous_name TEXT,
  renamed_on   TEXT
);

CREATE TABLE IF NOT EXISTS warehouse.dim_shift (
  shift_code       TEXT PRIMARY KEY,
  name             TEXT,
  start_time       TEXT NOT NULL,
  end_time         TEXT NOT NULL,
  crosses_midnight INTEGER NOT NULL CHECK (crosses_midnight IN (0,1)),
  grace_minutes    INTEGER NOT NULL,
  applies_to       TEXT
);

-- date spine: 2026-04-01 .. 2026-10-31 (SQLite has no generate_series - pandas date_range,
-- research R1). holiday flags for scope ALL; plant-scoped holidays resolved in queries.
CREATE TABLE IF NOT EXISTS warehouse.dim_date (
  date_key      TEXT PRIMARY KEY,          -- YYYY-MM-DD
  day           INTEGER NOT NULL,
  month         TEXT    NOT NULL,          -- YYYY-MM
  month_start   TEXT    NOT NULL,
  month_end     TEXT    NOT NULL,
  week_start    TEXT    NOT NULL,          -- Monday of that week
  weekday_no    INTEGER NOT NULL,          -- 1=Mon .. 7=Sun
  weekday_name  TEXT    NOT NULL,
  is_weekend    INTEGER NOT NULL CHECK (is_weekend IN (0,1)),
  is_holiday_all INTEGER NOT NULL DEFAULT 0 CHECK (is_holiday_all IN (0,1)),
  holiday_name  TEXT
);

-- ===================================================================== facts
-- Grain: one row per employee per day (from staging.attendance_daily).
-- dept_at_day = department held that day (SCD2 lookup; Rule 3 uses month-end variant).
CREATE TABLE IF NOT EXISTS warehouse.fact_attendance_daily (
  employee_key      INTEGER NOT NULL REFERENCES dim_employee(employee_key),
  date_key          TEXT    NOT NULL REFERENCES dim_date(date_key),
  shift_code        TEXT             REFERENCES dim_shift(shift_code),
  emp_id            TEXT    NOT NULL,
  work_date         TEXT    NOT NULL,
  plant             TEXT,
  dept_id           TEXT             REFERENCES dim_department(dept_id),
  status            TEXT    NOT NULL,
  punches_count     INTEGER NOT NULL DEFAULT 0,
  worked_hours      REAL    NOT NULL DEFAULT 0,
  late_minutes      INTEGER NOT NULL DEFAULT 0,
  early_leave_minutes INTEGER NOT NULL DEFAULT 0,
  ot_hours          REAL    NOT NULL DEFAULT 0,
  is_working_day    INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (employee_key, date_key)
);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_att_emp   ON fact_attendance_daily(emp_id, work_date);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_att_dept  ON fact_attendance_daily(dept_id, date_key);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_att_stat  ON fact_attendance_daily(status, date_key);

-- Grain: one row per countable leave day (Rule 17), only is_counted requests (Rule 16).
CREATE TABLE IF NOT EXISTS warehouse.fact_leave_day (
  employee_key  INTEGER NOT NULL REFERENCES dim_employee(employee_key),
  date_key      TEXT    NOT NULL REFERENCES dim_date(date_key),
  request_id    TEXT    NOT NULL,
  emp_id        TEXT    NOT NULL,
  leave_type    TEXT,
  plant         TEXT,
  dept_id       TEXT             REFERENCES dim_department(dept_id),
  PRIMARY KEY (request_id, date_key)
);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_leave_emp ON fact_leave_day(emp_id, date_key);

-- Grain: one row per APPROVED overtime request (Rule 19). Rejected/pending stay in staging.
CREATE TABLE IF NOT EXISTS warehouse.fact_overtime_approved (
  request_id      TEXT    PRIMARY KEY,
  employee_key    INTEGER NOT NULL REFERENCES dim_employee(employee_key),
  date_key        TEXT    NOT NULL REFERENCES dim_date(date_key),
  emp_id          TEXT    NOT NULL,
  ot_date         TEXT    NOT NULL,
  approved_hours  REAL,
  requested_hours REAL,
  plant           TEXT,
  dept_id         TEXT             REFERENCES dim_department(dept_id)
);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_ot_dept ON fact_overtime_approved(dept_id, ot_date);

-- Grain: one row per payslip line (long format). Rule 21: cost = sum of EARNING lines.
-- dept_id_month_end: department at month end / last working day (Rule 3, FR-029).
CREATE TABLE IF NOT EXISTS warehouse.fact_payroll_line (
  line_id          TEXT    PRIMARY KEY,
  employee_key     INTEGER NOT NULL REFERENCES dim_employee(employee_key),
  payroll_month    TEXT    NOT NULL,                -- YYYY-MM
  emp_id           TEXT    NOT NULL,
  component        TEXT    NOT NULL,
  component_type   TEXT    NOT NULL,
  units            REAL,
  amount           REAL,
  plant            TEXT,
  dept_id_month_end TEXT            REFERENCES dim_department(dept_id)
);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_pay_month ON fact_payroll_line(payroll_month);
CREATE INDEX IF NOT EXISTS warehouse.ix_fact_pay_comp  ON fact_payroll_line(component, payroll_month);
