-- Q10 Employees whose approved Annual leave days (Apr-Sep 2026) exceed
--   their annual_leave_entitlement (FR-043; Rule 18: entitlement is the
--   full-year Annual leave allowance - the six-month window is compared
--   against it as the spec requires).
-- Only fully approved, countable, non-Sunday/non-holiday leave days reach
--   fact_leave_day (Rules 16/17), so COUNT(*) is the approved taken count.
-- Entitlement from the employee's current SCD2 version (is_current = 1).
SELECT f.emp_id,
       de.full_name,
       de.plant,
       de.dept_name,
       de.annual_leave_entitlement,
       COUNT(*) AS annual_days_taken,
       COUNT(*) - de.annual_leave_entitlement AS days_over_entitlement,
       MIN(f.date_key) AS first_annual_leave,
       MAX(f.date_key) AS last_annual_leave
FROM warehouse.fact_leave_day f
JOIN warehouse.dim_employee de
  ON de.emp_id = f.emp_id AND de.is_current = 1
WHERE f.leave_type = 'Annual'
GROUP BY f.emp_id, de.full_name, de.plant, de.dept_name,
         de.annual_leave_entitlement
HAVING COUNT(*) > de.annual_leave_entitlement
ORDER BY days_over_entitlement DESC, f.emp_id
