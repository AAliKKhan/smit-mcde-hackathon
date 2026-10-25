-- Q9 Payroll cost per employee by department, with month-over-month change
--   (FR-042; guide wording: "Payroll cost per employee by department, with
--   month-over-month change" - grain is EMPLOYEE x MONTH, department is the
--   grouping label carried on each row).
-- Rule 21: cost = sum of EARNING lines (deductions stored positive with
--   component_type = 'DEDUCTION' are excluded).
-- Rule 3: department = the employee's month-end department
--   (fact_payroll_line.dept_id_month_end).
-- MoM: LAG within each employee (PARTITION BY emp_id ORDER BY month);
--   an employee's first paid month has no prior value (NULL). PKR.
WITH cost AS (
  SELECT emp_id,
         payroll_month AS month,
         dept_id_month_end AS dept_id,
         SUM(CASE WHEN component_type = 'EARNING' THEN amount END) AS cost
  FROM warehouse.fact_payroll_line
  GROUP BY emp_id, payroll_month, dept_id_month_end
)
SELECT c.emp_id,
       de.full_name,
       dd.plant,
       c.dept_id,
       dd.dept_name,
       c.month,
       ROUND(c.cost, 2) AS payroll_cost,
       ROUND(c.cost -
             LAG(c.cost) OVER (PARTITION BY c.emp_id ORDER BY c.month), 2)
         AS mom_change_abs,
       ROUND((c.cost -
              LAG(c.cost) OVER (PARTITION BY c.emp_id ORDER BY c.month)) /
             NULLIF(LAG(c.cost) OVER (PARTITION BY c.emp_id ORDER BY c.month), 0),
             4)
         AS mom_change_pct
FROM cost c
JOIN warehouse.dim_employee de
  ON de.emp_id = c.emp_id AND de.is_current = 1
JOIN warehouse.dim_department dd
  ON dd.dept_id = c.dept_id
ORDER BY c.emp_id, c.month
