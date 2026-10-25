-- Q6 Departments where paid overtime exceeds computed overtime by more
--   than 15% over the whole window (FR-039): paid > computed x 1.15.
-- Measures come from the same three sources as Q5 (Rules 14/15/19/20);
--   a department with zero computed hours but positive paid hours
--   qualifies (0 x 1.15 = 0). Rates are Apr-Sep 2026 totals.
WITH comp AS (
  SELECT dept_id, SUM(ot_hours) AS h
  FROM warehouse.fact_attendance_daily
  GROUP BY dept_id
),
appr AS (
  SELECT dept_id, SUM(approved_hours) AS h
  FROM warehouse.fact_overtime_approved
  GROUP BY dept_id
),
paid AS (
  SELECT dept_id_month_end AS dept_id,
         SUM(CASE WHEN component = 'OVERTIME' THEN units END) AS h
  FROM warehouse.fact_payroll_line
  GROUP BY dept_id_month_end
)
SELECT d.plant,
       d.dept_id,
       d.dept_name,
       ROUND(COALESCE(c.h, 0), 2) AS computed_ot_hours,
       ROUND(COALESCE(a.h, 0), 2) AS approved_ot_hours,
       ROUND(COALESCE(p.h, 0), 2) AS paid_ot_hours,
       ROUND(COALESCE(p.h, 0) - COALESCE(c.h, 0), 2) AS overage_hours,
       ROUND(COALESCE(p.h, 0) / NULLIF(c.h, 0), 4) AS paid_over_computed_ratio
FROM warehouse.dim_department d
LEFT JOIN comp c ON c.dept_id = d.dept_id
LEFT JOIN appr a ON a.dept_id = d.dept_id
LEFT JOIN paid p ON p.dept_id = d.dept_id
WHERE COALESCE(p.h, 0) > COALESCE(c.h, 0) * 1.15
ORDER BY overage_hours DESC
