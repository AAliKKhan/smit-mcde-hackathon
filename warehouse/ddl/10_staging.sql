-- 10_staging.sql â€” typed, cleaned layer (Stage 2/3 outputs). Requires common/db.py attaches.
-- Conventions: dates TEXT 'YYYY-MM-DD', timestamps TEXT ISO-8601, hours REAL,
-- all tables idempotent (CREATE IF NOT EXISTS) - transforms rebuild via DELETE/CREATE.

-- ---------------------------------------------------------------- employees (Rule 1)
CREATE TABLE IF NOT EXISTS staging.employees (
  emp_id                   TEXT    PRIMARY KEY,
  full_name                TEXT,
  gender                   TEXT,
  date_of_birth            TEXT,           -- ISO after cleaning
  email                    TEXT,
  phone                    TEXT,
  plant                    TEXT,
  dept_id                  TEXT,           -- resolved via departments (incl. previous_name)
  department               TEXT,           -- canonical dept_name
  designation              TEXT,
  grade                    TEXT,
  employment_type          TEXT,
  hire_date                TEXT NOT NULL,  -- ISO
  separation_date          TEXT,           -- NULL = active
  status                   TEXT CHECK (status IN ('Active','Separated')),
  annual_leave_entitlement INTEGER,
  updated_at               TEXT
);

CREATE TABLE IF NOT EXISTS staging.employees_dedupe_log (
  emp_id         TEXT NOT NULL,
  kept_updated_at TEXT,
  dropped_updated_at TEXT,
  dropped_hash   TEXT,
  reason         TEXT NOT NULL,
  logged_at      TEXT NOT NULL,
  PRIMARY KEY (emp_id, dropped_hash)
);

-- ------------------------------------------------- employment history (Rule 2)
CREATE TABLE IF NOT EXISTS staging.employment_history (
  record_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  emp_id            TEXT NOT NULL,
  effective_from    TEXT NOT NULL,
  effective_to      TEXT,                 -- recomputed: day before next record (NULL = latest)
  raw_effective_to  TEXT,                 -- original unreliable value (forensics)
  dept_id           TEXT NOT NULL,
  designation       TEXT,
  grade             TEXT,
  basic_salary      REAL,
  change_reason     TEXT,
  is_latest         INTEGER NOT NULL DEFAULT 0 CHECK (is_latest IN (0,1))
);
CREATE INDEX IF NOT EXISTS staging.ix_hist_emp_from ON employment_history(emp_id, effective_from);

-- ------------------------------------------------------------------ reference
CREATE TABLE IF NOT EXISTS staging.departments (
  dept_id       TEXT PRIMARY KEY,
  dept_name     TEXT NOT NULL,
  plant         TEXT NOT NULL,
  cost_center   TEXT,
  previous_name TEXT,
  renamed_on    TEXT
);

CREATE TABLE IF NOT EXISTS staging.shifts (
  shift_code       TEXT PRIMARY KEY,
  name             TEXT,
  start_time       TEXT NOT NULL,   -- HH:MM
  end_time         TEXT NOT NULL,   -- HH:MM
  crosses_midnight INTEGER NOT NULL CHECK (crosses_midnight IN (0,1)),
  grace_minutes    INTEGER NOT NULL,
  applies_to       TEXT
);

CREATE TABLE IF NOT EXISTS staging.shift_roster (
  emp_id     TEXT NOT NULL,
  week_start TEXT NOT NULL,         -- Monday
  shift_code TEXT NOT NULL REFERENCES shifts(shift_code),  -- unqualified: same attached DB (SQLite rejects qualified REFERENCES)
  is_gap_filled INTEGER NOT NULL DEFAULT 0 CHECK (is_gap_filled IN (0,1)),
  PRIMARY KEY (emp_id, week_start)
);
CREATE INDEX IF NOT EXISTS staging.ix_roster_emp ON shift_roster(emp_id, week_start);

CREATE TABLE IF NOT EXISTS staging.device_mapping (
  device_id      TEXT NOT NULL,
  device_user_id TEXT NOT NULL,
  emp_id         TEXT NOT NULL,
  enrolled_on    TEXT,
  PRIMARY KEY (device_id, device_user_id)
);

CREATE TABLE IF NOT EXISTS staging.holidays (
  holiday_date TEXT NOT NULL,
  scope        TEXT NOT NULL CHECK (scope IN ('ALL','HO','KOR','SITE','FSD')),
  holiday_name TEXT,
  PRIMARY KEY (holiday_date, scope)
);

-- ------------------------------------------------------------------ punches
-- Processing order (research R3): map (Rule 8) -> drift-correct (Rule 11)
-- -> 2-min dedupe (Rule 9) -> night shift_date attribution (Rule 7).
CREATE TABLE IF NOT EXISTS staging.punches (
  emp_id       TEXT NOT NULL,
  punch_time   TEXT NOT NULL,          -- drift-corrected, ISO timestamp
  device_id    TEXT,
  device_user_id TEXT,
  src_punch_id TEXT,
  shift_date   TEXT,                   -- attributed work date (Rule 7)
  PRIMARY KEY (emp_id, punch_time)
);
CREATE INDEX IF NOT EXISTS staging.ix_punches_emp_date ON punches(emp_id, shift_date);
CREATE INDEX IF NOT EXISTS staging.ix_punches_time     ON punches(punch_time);

CREATE TABLE IF NOT EXISTS staging.rejected_punches (
  punch_id       TEXT PRIMARY KEY,
  device_id      TEXT,
  device_user_id TEXT,
  punch_time     TEXT,
  reason         TEXT NOT NULL         -- unmapped_device_user | ...
);

CREATE TABLE IF NOT EXISTS staging.drift_corrections (
  device_id        TEXT PRIMARY KEY,
  offset_minutes   INTEGER NOT NULL,
  detection_method TEXT NOT NULL,
  avg_first_punch_before TEXT,
  avg_first_punch_after  TEXT,
  evidence_note    TEXT,
  corrected_at     TEXT NOT NULL
);

-- -------------------------------------------------------------------- leave
CREATE TABLE IF NOT EXISTS staging.leave_requests (
  request_id  TEXT PRIMARY KEY,
  emp_id      TEXT NOT NULL,
  plant       TEXT,
  leave_type  TEXT NOT NULL,
  date_from   TEXT NOT NULL,
  date_to     TEXT NOT NULL,
  days_requested_raw INTEGER,          -- employee-typed, never used for counting (Rule 16)
  submitted_at TEXT,
  cancelled_at TEXT,
  is_counted  INTEGER NOT NULL DEFAULT 0 CHECK (is_counted IN (0,1)),  -- Rule 16
  reject_reason TEXT                   -- NULL if countable
);

CREATE TABLE IF NOT EXISTS staging.leave_approval_steps (
  request_id    TEXT NOT NULL,
  step          INTEGER NOT NULL,
  approver_role TEXT,
  approver_id   TEXT,
  action        TEXT,
  acted_at      TEXT,
  PRIMARY KEY (request_id, step)
);

CREATE TABLE IF NOT EXISTS staging.leave_days (
  request_id TEXT NOT NULL,
  emp_id     TEXT NOT NULL,
  day_date   TEXT NOT NULL,            -- Rule 17: range minus Sundays & plant holidays
  leave_type TEXT,
  PRIMARY KEY (request_id, day_date)
);
CREATE INDEX IF NOT EXISTS staging.ix_leave_days_emp ON leave_days(emp_id, day_date);

-- --------------------------------------------------------- overtime / payroll
CREATE TABLE IF NOT EXISTS staging.overtime_requests (
  request_id      TEXT PRIMARY KEY,
  emp_id          TEXT NOT NULL,
  ot_date         TEXT NOT NULL,
  requested_hours REAL,
  approved_hours  REAL,
  status          TEXT NOT NULL,
  approver_id     TEXT,
  requested_at    TEXT
);
CREATE INDEX IF NOT EXISTS staging.ix_ot_emp_date ON overtime_requests(emp_id, ot_date);

CREATE TABLE IF NOT EXISTS staging.payroll_lines (
  line_id        TEXT PRIMARY KEY,
  payroll_month  TEXT NOT NULL,        -- YYYY-MM
  emp_id         TEXT NOT NULL,
  component      TEXT NOT NULL,
  component_type TEXT NOT NULL CHECK (component_type IN ('EARNING','DEDUCTION')),
  units          REAL,
  amount         REAL
);
CREATE INDEX IF NOT EXISTS staging.ix_payroll_emp_month ON payroll_lines(emp_id, payroll_month);

-- ------------------------------------------------------- applications (bonus)
CREATE TABLE IF NOT EXISTS staging.applications (
  application_id TEXT NOT NULL,
  candidate_id   TEXT,
  job_req_id     TEXT,
  dept_id        TEXT,
  stage          TEXT,
  stage_date     TEXT,
  PRIMARY KEY (application_id, stage, stage_date)
);

-- -------------------------------------------- attendance daily (Stage 3, Rule 12)
CREATE TABLE IF NOT EXISTS staging.attendance_daily (
  emp_id              TEXT NOT NULL,
  work_date           TEXT NOT NULL,
  plant               TEXT,
  dept_id             TEXT,
  shift_code          TEXT,
  check_in            TEXT,
  check_out           TEXT,
  status              TEXT NOT NULL CHECK (status IN
                        ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),
  punches_count       INTEGER NOT NULL DEFAULT 0,
  worked_hours        REAL    NOT NULL DEFAULT 0,
  late_minutes        INTEGER NOT NULL DEFAULT 0,
  early_leave_minutes INTEGER NOT NULL DEFAULT 0,
  ot_hours            REAL    NOT NULL DEFAULT 0,
  is_working_day      INTEGER NOT NULL DEFAULT 1 CHECK (is_working_day IN (0,1)),
  PRIMARY KEY (emp_id, work_date)
);
CREATE INDEX IF NOT EXISTS staging.ix_att_date   ON attendance_daily(work_date);
CREATE INDEX IF NOT EXISTS staging.ix_att_status ON attendance_daily(status);
