-- Q4 Top 10 employees by late arrivals (FR-037).
-- Rule 13: late = check-in more than 10 minutes after shift start, counted
--   only on Present working days (already computed in late_minutes).
-- Ranking: number of late days, ties broken by total late minutes.
-- Department = employee's current (is_current) SCD2 version.
-- Uses ROW_NUMBER() window function (FR-032).
WITH late AS (
  SELECT emp_id,
         COUNT(*) AS late_days,
         SUM(late_minutes) AS late_minutes_total
  FROM warehouse.fact_attendance_daily
  WHERE late_minutes > 0
  GROUP BY emp_id
)
SELECT ROW_NUMBER() OVER (ORDER BY l.late_days DESC,
                                      l.late_minutes_total DESC) AS rank_no,
       l.emp_id,
       de.full_name,
       de.dept_name,
       de.plant,
       l.late_days,
       l.late_minutes_total
FROM late l
JOIN warehouse.dim_employee de
  ON de.emp_id = l.emp_id AND de.is_current = 1
ORDER BY rank_no
LIMIT 10
