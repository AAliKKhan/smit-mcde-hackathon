-- Q2 Monthly attrition rate by department (FR-035).
-- Definition (research R12, documented per task): attrition_rate =
--   separations in the month / average of (headcount at month start,
--   headcount at month end). The rate is a decimal (0.05 = 5%).
-- Separations = employees whose separation_date falls in the month,
--   attributed to the department of their last working day (Rule 3:
--   the SCD2 version containing separation_date). Headcount uses Rule 4
--   at each reference date; department = SCD2 version at that date.
-- Output: every department x month (zero separations included).
WITH months AS (
  SELECT DISTINCT month FROM warehouse.dim_date
  WHERE month BETWEEN '2026-04' AND '2026-09'
),
refs AS (
  SELECT month, date_key AS d, 'start' AS pos
  FROM warehouse.dim_date
  WHERE date_key = month_start AND month BETWEEN '2026-04' AND '2026-09'
  UNION ALL
  SELECT month, date_key, 'end'
  FROM warehouse.dim_date
  WHERE date_key = month_end AND month BETWEEN '2026-04' AND '2026-09'
),
hc AS (
  SELECT r.month, r.pos, de.dept_id, COUNT(*) AS n
  FROM refs r
  JOIN warehouse.dim_employee de
    ON de.valid_from <= r.d
   AND (de.valid_to IS NULL OR de.valid_to >= r.d)
   AND de.hire_date <= r.d
   AND (de.separation_date IS NULL OR de.separation_date > r.d)
  GROUP BY r.month, r.pos, de.dept_id
),
seps AS (
  SELECT substr(de.separation_date, 1, 7) AS month, de.dept_id,
         COUNT(*) AS n
  FROM warehouse.dim_employee de
  WHERE de.separation_date IS NOT NULL
    AND de.separation_date BETWEEN '2026-04-01' AND '2026-09-30'
    AND de.valid_from <= de.separation_date
    AND (de.valid_to IS NULL OR de.valid_to >= de.separation_date)
  GROUP BY substr(de.separation_date, 1, 7), de.dept_id
)
SELECT m.month,
       d.plant,
       d.dept_id,
       d.dept_name,
       COALESCE(s.n, 0) AS separations,
       COALESCE(hs.n, 0) AS headcount_month_start,
       COALESCE(he.n, 0) AS headcount_month_end,
       ROUND((COALESCE(hs.n, 0) + COALESCE(he.n, 0)) / 2.0, 1) AS avg_headcount,
       ROUND(1.0 * COALESCE(s.n, 0) /
             NULLIF((COALESCE(hs.n, 0) + COALESCE(he.n, 0)) / 2.0, 0), 4)
         AS attrition_rate
FROM months m
CROSS JOIN warehouse.dim_department d
LEFT JOIN seps s   ON s.month = m.month   AND s.dept_id = d.dept_id
LEFT JOIN hc hs    ON hs.month = m.month  AND hs.pos = 'start' AND hs.dept_id = d.dept_id
LEFT JOIN hc he    ON he.month = m.month  AND he.pos = 'end'   AND he.dept_id = d.dept_id
ORDER BY m.month, d.plant, d.dept_id
