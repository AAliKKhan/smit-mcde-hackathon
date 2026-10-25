-- Q1 Month-end headcount by plant x department for all six months (FR-034).
-- Rule 4: in headcount at month end when hire_date <= month end AND
--   (no separation_date OR separation_date after month end).
-- Rule 3: department/plant = the SCD2 version containing the month end
--   (employees counted here are employed at month end, so the attribution
--   date IS the month end).
-- Grain: month x plant x dept_id; only combinations with headcount > 0.
WITH months AS (
  SELECT month_end AS d, month
  FROM warehouse.dim_date
  WHERE date_key = month_end
    AND month BETWEEN '2026-04' AND '2026-09'
)
SELECT m.month,
       de.plant,
       de.dept_id,
       de.dept_name,
       COUNT(*) AS headcount
FROM months m
JOIN warehouse.dim_employee de
  ON de.valid_from <= m.d
 AND (de.valid_to IS NULL OR de.valid_to >= m.d)
 AND de.hire_date <= m.d
 AND (de.separation_date IS NULL OR de.separation_date > m.d)
GROUP BY m.month, de.plant, de.dept_id, de.dept_name
ORDER BY m.month, de.plant, de.dept_id
