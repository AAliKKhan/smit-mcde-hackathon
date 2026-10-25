-- Q5 Overtime by department and month - three measures, never conflated
--   (FR-038; spec edge case "approved != computed != paid").
--   computed : SUM(ot_hours) from attendance (Rules 14/15 applied at build:
--              minutes after shift end on working days; Sunday/holiday work
--              is all overtime, both rounded down to half hours)
--   approved : SUM(approved_hours) from Approved requests only (Rule 19)
--   paid     : SUM(units) of OVERTIME payroll lines; units = hours paid
--              (Rule 20), pivoted with SUM(CASE WHEN component = ...).
-- Department attribution: computed/approved use the department at the day,
--   paid uses the month-end department (Rule 3). Output: every department
--   x month grid (25 x 6) so zero rows are explicit, not missing.
WITH months AS (
  SELECT DISTINCT month FROM warehouse.dim_date
  WHERE month BETWEEN '2026-04' AND '2026-09'
),
grid AS (
  SELECT d.dept_id, m.month
  FROM warehouse.dim_department d CROSS JOIN months m
),
comp AS (
  SELECT dept_id, substr(work_date, 1, 7) AS month, SUM(ot_hours) AS h
  FROM warehouse.fact_attendance_daily
  GROUP BY dept_id, substr(work_date, 1, 7)
),
appr AS (
  SELECT dept_id, substr(ot_date, 1, 7) AS month, SUM(approved_hours) AS h
  FROM warehouse.fact_overtime_approved
  GROUP BY dept_id, substr(ot_date, 1, 7)
),
paid AS (
  SELECT dept_id_month_end AS dept_id, payroll_month AS month,
         SUM(CASE WHEN component = 'OVERTIME' THEN units END) AS h
  FROM warehouse.fact_payroll_line
  GROUP BY dept_id_month_end, payroll_month
)
SELECT g.month,
       d.plant,
       g.dept_id,
       d.dept_name,
       ROUND(COALESCE(c.h, 0), 2) AS computed_ot_hours,
       ROUND(COALESCE(a.h, 0), 2) AS approved_ot_hours,
       ROUND(COALESCE(p.h, 0), 2) AS paid_ot_hours
FROM grid g
JOIN warehouse.dim_department d ON d.dept_id = g.dept_id
LEFT JOIN comp c ON c.dept_id = g.dept_id AND c.month = g.month
LEFT JOIN appr a ON a.dept_id = g.dept_id AND a.month = g.month
LEFT JOIN paid p ON p.dept_id = g.dept_id AND p.month = g.month
ORDER BY g.month, d.plant, g.dept_id
