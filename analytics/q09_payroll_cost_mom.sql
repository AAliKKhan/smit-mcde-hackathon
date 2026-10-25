-- Q9 Payroll cost per employee by department with month-over-month change
--   (FR-042; Rule 21: cost = sum of EARNING lines - deductions are stored
--   positive but typed DEDUCTION and excluded here).
-- FR-044: the long-format payroll is pivoted in SQL with
--   SUM(CASE WHEN component = '...' THEN amount END) per component.
-- Department = month-end department (Rule 3). Employees counted per
--   dept-month; cost_per_employee = total earning cost / employees.
-- MoM: LAG window over cost_per_employee within each department (FR-032);
--   first month has no prior value (NULL).
WITH comp_pivot AS (
  SELECT payroll_month AS month,
         dept_id_month_end AS dept_id,
         SUM(CASE WHEN component = 'BASIC'      THEN amount END) AS basic,
         SUM(CASE WHEN component = 'HOUSE_RENT' THEN amount END) AS house_rent,
         SUM(CASE WHEN component = 'CONVEYANCE' THEN amount END) AS conveyance,
         SUM(CASE WHEN component = 'MEDICAL'    THEN amount END) AS medical,
         SUM(CASE WHEN component = 'OVERTIME'   THEN amount END) AS overtime
  FROM warehouse.fact_payroll_line
  GROUP BY payroll_month, dept_id_month_end
),
per_emp AS (
  SELECT payroll_month AS month,
         dept_id_month_end AS dept_id,
         emp_id,
         SUM(CASE WHEN component_type = 'EARNING' THEN amount END) AS cost
  FROM warehouse.fact_payroll_line
  GROUP BY payroll_month, dept_id_month_end, emp_id
),
dept AS (
  SELECT month, dept_id,
         SUM(cost) AS total_cost,
         COUNT(DISTINCT emp_id) AS employees
  FROM per_emp
  GROUP BY month, dept_id
)
SELECT d.month,
       dd.plant,
       d.dept_id,
       dd.dept_name,
       d.employees,
       ROUND(d.total_cost, 2) AS total_cost,
       ROUND(d.total_cost * 1.0 / d.employees, 2) AS cost_per_employee,
       ROUND(COALESCE(cp.basic, 0), 2)      AS basic_amount,
       ROUND(COALESCE(cp.house_rent, 0), 2) AS house_rent_amount,
       ROUND(COALESCE(cp.conveyance, 0), 2) AS conveyance_amount,
       ROUND(COALESCE(cp.medical, 0), 2)    AS medical_amount,
       ROUND(COALESCE(cp.overtime, 0), 2)   AS overtime_amount,
       ROUND(d.total_cost * 1.0 / d.employees -
             LAG(d.total_cost * 1.0 / d.employees)
               OVER (PARTITION BY d.dept_id ORDER BY d.month), 2)
         AS mom_change_abs,
       ROUND(1.0 * (d.total_cost * 1.0 / d.employees -
             LAG(d.total_cost * 1.0 / d.employees)
               OVER (PARTITION BY d.dept_id ORDER BY d.month)) /
             NULLIF(LAG(d.total_cost * 1.0 / d.employees)
               OVER (PARTITION BY d.dept_id ORDER BY d.month), 0), 4)
         AS mom_change_pct
FROM dept d
JOIN warehouse.dim_department dd ON dd.dept_id = d.dept_id
LEFT JOIN comp_pivot cp ON cp.month = d.month AND cp.dept_id = d.dept_id
ORDER BY d.dept_id, d.month
