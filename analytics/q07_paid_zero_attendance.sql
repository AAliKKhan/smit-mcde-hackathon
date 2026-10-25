-- Q7 Employees paid in a month with zero attendance that month (FR-040).
-- Definition (documented per task): a payroll month whose EARNING total
--   (Rule 21) is positive while the employee's attendance rows for that
--   same month sum to ZERO worked hours. This covers both shapes found in
--   the data: months with no attendance rows at all (employee absent from
--   the workforce spine) and months where every day is non-Present
--   (all Absent / Weekly Off / Holiday). Approved-leave-only months would
--   also read as zero attendance; none occur in Apr-Sep 2026.
-- Attendance composition columns are returned so the case can be defended.
WITH pay AS (
  SELECT emp_id, payroll_month AS month, SUM(amount) AS paid_amount
  FROM warehouse.fact_payroll_line
  WHERE component_type = 'EARNING'
  GROUP BY emp_id, payroll_month
  HAVING SUM(amount) > 0
),
att AS (
  SELECT emp_id, substr(work_date, 1, 7) AS month,
         COUNT(*) AS attendance_days,
         SUM(CASE WHEN status = 'Present'    THEN 1 ELSE 0 END) AS present_days,
         SUM(CASE WHEN status = 'Absent'     THEN 1 ELSE 0 END) AS absent_days,
         SUM(CASE WHEN status = 'On Leave'   THEN 1 ELSE 0 END) AS leave_days,
         SUM(CASE WHEN status = 'Weekly Off' THEN 1 ELSE 0 END) AS weekly_off_days,
         SUM(worked_hours) AS worked_hours
  FROM warehouse.fact_attendance_daily
  GROUP BY emp_id, substr(work_date, 1, 7)
)
SELECT p.emp_id,
       de.full_name,
       de.plant,
       de.dept_name,
       p.month,
       ROUND(p.paid_amount, 2) AS paid_amount,
       COALESCE(a.attendance_days, 0) AS attendance_days,
       COALESCE(a.present_days, 0)    AS present_days,
       COALESCE(a.absent_days, 0)     AS absent_days,
       COALESCE(a.leave_days, 0)      AS leave_days,
       ROUND(COALESCE(a.worked_hours, 0), 2) AS worked_hours
FROM pay p
LEFT JOIN att a ON a.emp_id = p.emp_id AND a.month = p.month
JOIN warehouse.dim_employee de
  ON de.emp_id = p.emp_id AND de.is_current = 1
WHERE COALESCE(a.worked_hours, 0) = 0
ORDER BY p.emp_id, p.month
