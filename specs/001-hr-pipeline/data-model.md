# Data Model: 001-hr-pipeline (Phase 1)

Branch: `001-hr-pipeline` | Date: 2026-10-25 | Engine: SQLite (`db/indus_weave.db`)
Full DDL lives in `warehouse/ddl/*.sql`; this document defines grains, keys and rules mapping.

## Layer overview

```text
data/* (immutable)  →  raw.* (TEXT, 12 tables + load metadata)
                    →  staging.* (typed, cleaned, quarantines + logs)   [stages 2–3]
                    →  warehouse.* (star schema, PK/FK enforced)       [stage 4]
dq_results  ←──────────────── quality checks over all layers           [stage 6]
```

## STAGING (Stage 2–3 outputs)

Every staging table: ISO dates, trimmed/normalized text, `_source_file` lineage retained where
useful. Rebuild = create-or-replace (idempotent).

| Table | Grain | Key | Source & rules |
|---|---|---|---|
| `staging.employees` | 1 row / `emp_id` | PK `emp_id` | raw.employees, Rule 1 (latest `updated_at`), mixed date formats → ISO, dept casing/spaces → `departments` canonical names |
| `staging.employees_dedupe_log` | 1 row / dropped duplicate row | PK `emp_id` + `_row_hash` | which rows merged, `updated_at` values, reason |
| `staging.employment_history` | 1 row / record | PK auto | Rule 2: `valid_to_calc = next.effective_from - 1 day` (latest → NULL); original `effective_to` kept as `_raw_effective_to` for forensics |
| `staging.departments` | 1 row / `dept_id` | PK `dept_id` | canonical `dept_name`, `previous_name`, `renamed_on` preserved (2 renames) |
| `staging.shifts` | 1 row / `shift_code` | PK `shift_code` | DAY 06:00–14:00, EVE 14:00–22:00, NIGHT 22:00–06:00 (crosses_midnight), GEN 09:00–17:30; `grace_minutes = 10` |
| `staging.shift_roster` | 1 row / (`emp_id`, `week_start`) | PK (`emp_id`,`week_start`) | Rule 6: gaps forward-filled from previous week; `week_start` is Monday |
| `staging.device_mapping` | 1 row / (`device_id`,`device_user_id`) | PK (composite) | → `emp_id` |
| `staging.punches` | 1 row / deduplicated, mapped, drift-corrected punch | PK (`emp_id`,`punch_time`) | Rules 8→11→9 order; columns: `punch_time`, `device_id`, `shift_date` (Rule 7 attribution), `_src_punch_id` |
| `staging.rejected_punches` | 1 row / unusable punch | PK `punch_id` | `reason` ∈ {unmapped_device_user, …}; contractors/visitors excluded but retained (Rule 8) |
| `staging.drift_corrections` | 1 row / corrected device | PK `device_id` | `offset_minutes`, `detection_method`, `avg_first_punch_before/after`, `evidence_note` |
| `staging.holidays` | 1 row / (`holiday_date`,`scope`) | PK (composite) | scope ALL/HO/KOR/SITE/FSD |
| `staging.leave_requests` | 1 row / request | PK `request_id` | flattened header: `emp_id`, `plant`, `leave_type`, `from`, `to`, `submitted_at`, `cancelled_at`, `is_counted` (Rule 16) |
| `staging.leave_approval_steps` | 1 row / request × step | PK (`request_id`,`step`) | `step`, `approver_role`, `approver_id`, `action`, `acted_at` |
| `staging.leave_days` | 1 row / countable leave day | PK (`request_id`,`day_date`) | date range expansion minus Sundays & plant holidays (Rule 17), only `is_counted` requests |
| `staging.overtime_requests` | 1 row / request | PK `request_id` | `ot_date`, `requested_hours`, `approved_hours`, `status`; Rule 19 |
| `staging.payroll_lines` | 1 row / line | PK `line_id` | typed `payroll_month` (YYYY-MM), numeric `units`/`amount`, `component_type` EARNING/DEDUCTION |
| `staging.applications` | 1 row / stage change | PK `application_id`+`stage`+`stage_date` | bonus only; loaded for completeness |
| **`staging.attendance_daily`** | **1 row / (`emp_id`,`work_date`)** | PK (composite) | Rules 4, 7, 10, 12–15: `shift_code`, `check_in`, `check_out`, `status`, `worked_hours`, `late_minutes`, `early_leave_minutes`, `ot_hours`, `plant`, `dept_id` (as-of day), `is_working_day` |

**`staging.attendance_daily.status` domain (Rule 12 priority):**
`Weekly Off` > `Holiday` > `On Leave` > `Present` (≥2 punches) > `Missing Punch` (1 punch) > `Absent` (0).

## WAREHOUSE (Stage 4 star schema)

### Dimensions

**`warehouse.dim_employee` — SCD Type 2 (Rule 2)**

| Column | Notes |
|---|---|
| `employee_key` | PK, surrogate (INTEGER) |
| `emp_id` | business key, indexed (non-unique by design) |
| `full_name`, `gender`, `email`, `phone`, `date_of_birth` | from deduped employees |
| `plant`, `grade`, `designation`, `employment_type`, `status` | snapshot attributes |
| `dept_id`, `dept_name` | from history row (attribute snapshot) |
| `basic_salary` | monthly PKR from history |
| `change_reason` | Hire / Salary Revision / Promotion / Transfer |
| `hire_date`, `separation_date` | lifecycle |
| `annual_leave_entitlement` | Rule 18 |
| `valid_from`, `valid_to` | date; `valid_to` inclusive, NULL→9999-12-31; contiguous, non-overlapping |
| `is_current` | 1 for latest row |

Grain: one row per employee per effective period. Build: sort history, `valid_to =
LEAD(effective_from)-1d`. DQ: no overlap, every fact date resolves.

**`warehouse.dim_department`** — PK `dept_id`; `dept_name`, `plant`, `cost_center`,
`previous_name`, `renamed_on`. (Names unique per plant: "Maintenance" ×3, "Quality Control" ×4 —
composite natural key is (`dept_id`), joins never by name.)

**`warehouse.dim_shift`** — PK `shift_code`; `name`, `start_time`, `end_time`,
`crosses_midnight`, `grace_minutes`, `applies_to`.

**`warehouse.dim_date`** — PK `date_key` (ISO date); `day`, `month` (YYYY-MM), `week_start`,
`weekday_no`, `weekday_name`, `is_weekend`, `is_holiday_all`, `plant` variant flags left to
queries (scope handled via holidays join). Range **2026-04-01 → 2026-10-31** (1 Oct check-outs +
October roster planning). Generated via pandas `date_range` (SQLite has no `generate_series`,
R1).

### Facts

| Fact | Grain | Measures | FKs |
|---|---|---|---|
| `warehouse.fact_attendance_daily` | (`employee_key`, `date_key`) — 1 row per employee-day built in Stage 3 | `worked_hours`, `late_minutes`, `early_leave_minutes`, `ot_hours`, `status`, `shift_code`, `emp_id`, `dept_id_at_day`, `plant` | `employee_key`→dim_employee (SCD2 join by `work_date`), `date_key`→dim_date, `shift_code`→dim_shift |
| `warehouse.fact_leave_day` | (`employee_key`, `date_key`, `request_id`) | `leave_type`, `is_paid` | + dim_date; `dept_id` snapshot at day for Q10 grouping |
| `warehouse.fact_overtime_approved` | (`employee_key`, `date_key`, `request_id`) | `requested_hours`, `approved_hours`, `status` (Approved only in fact; rejected kept in staging) | dim_employee, dim_date |
| `warehouse.fact_payroll_line` | (`employee_key`, `payroll_month_key`→date_key of month-end? **No** — see note) | `component`, `component_type`, `units`, `amount` | `employee_key`, `payroll_month` TEXT (YYYY-MM), `dept_id_month_end` |

**Q9/Q1 department attribution note**: `fact_payroll_line` and `fact_attendance_daily` carry
`dept_id` resolved for the reporting month/day via SCD2 (Rule 3: last day of month / last working
day). Payroll fact stores `dept_id_month_end` so Q6/Q9 need no extra join gymnastics.
Month grain kept as `payroll_month` TEXT because dim_date month-end is derivable anyway.

**Missing-punch & rejected data**: never enter facts as measures; `rejected_punches` and
`drift_corrections` remain in staging (audit artifacts), exposed in DQ evidence.

## dq_results (Stage 6 output table)

```sql
CREATE TABLE dq_results (
  run_id       TEXT,      -- pipeline run timestamp id
  check_id     TEXT,      -- e.g. PK_UNIQ_STAGING_EMPLOYEES, RI_FACT_ATTENDANCE_DIM_EMP
  layer        TEXT,      -- raw | staging | warehouse | reconciliation | sanity
  target       TEXT,      -- table or rule checked
  status       TEXT CHECK (status IN ('PASS','FAIL')),
  failure_count INTEGER,
  detail       TEXT,      -- offending keys / values (truncated)
  checked_at   TEXT
);
```

Check families (FR-045…050): PK uniqueness/not-null for every table key; RI fact→dim for all
four facts; reconciliation `raw = staging + rejected` per table; accepted values (attendance
status, leave type, pay component); sanity (no negative `worked_hours`, no shift > 16h, no
overlapping SCD2 ranges).

## ER relationships (for `warehouse/erd.png`)

```text
dim_employee (SCD2) ──< fact_attendance_daily >── dim_date
        │                      └──> dim_shift
        ├──< fact_leave_day >── dim_date
        ├──< fact_overtime_approved >── dim_date
        └──< fact_payroll_line        (dept_id_month_end → dim_department)
dim_department ──< (dept_id carried on facts as degenerate/FK snapshot)
```

Draw in dbdiagram.io using the `warehouse/erd.dbml` source (export PNG → `warehouse/erd.png`).
