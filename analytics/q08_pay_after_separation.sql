-- Q8 Employees still receiving pay after their separation date (FR-041).
-- Definition (documented per task): EARNING payroll (Rule 21) for a
--   payroll month that BEGINS entirely after separation_date, where
--   separation_date is the last day worked (Rule 4). Final-month
--   settlements - the month that CONTAINS the separation date - are
--   excluded on purpose: paying through the last day worked is correct.
-- Department = employee's current version (they left the company).
-- days_after_separation = calendar days from separation to month start.
WITH pay AS (
  SELECT emp_id, payroll_month AS month, SUM(amount) AS paid_amount
  FROM warehouse.fact_payroll_line
  WHERE component_type = 'EARNING'
  GROUP BY emp_id, payroll_month
  HAVING SUM(amount) > 0
)
SELECT p.emp_id,
       de.full_name,
       de.plant,
       de.dept_name,
       de.separation_date,
       p.month AS payroll_month,
       ROUND(p.paid_amount, 2) AS paid_amount,
       CAST(julianday(date(p.month || '-01')) -
            julianday(de.separation_date) AS INT) AS days_after_separation
FROM pay p
JOIN warehouse.dim_employee de
  ON de.emp_id = p.emp_id AND de.is_current = 1
WHERE de.separation_date IS NOT NULL
  AND date(p.month || '-01') > de.separation_date
ORDER BY de.separation_date, p.emp_id, p.month
