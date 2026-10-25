-- Q3 Absenteeism rate by plant and month, excluding approved leave (FR-036).
-- Eligibility definition (research R12, documented per task):
--   numerator   = Absent days (Rule 12)
--   denominator = eligible attendance days MINUS approved leave MINUS
--                 plant holidays MINUS weekly offs, i.e. exactly the
--                 Present + Absent + Missing Punch days (days expected to
--                 be worked, with Rule 12 special statuses removed).
--   Rate is a decimal (0.03 = 3%). Plant comes from the attendance row.
-- Only the six export months are in scope.
SELECT a.plant,
       substr(a.work_date, 1, 7) AS month,
       SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
       SUM(CASE WHEN a.status IN ('Present', 'Absent', 'Missing Punch')
                THEN 1 ELSE 0 END) AS eligible_days,
       SUM(CASE WHEN a.status = 'On Leave' THEN 1 ELSE 0 END) AS approved_leave_days,
       SUM(CASE WHEN a.status = 'Holiday' THEN 1 ELSE 0 END) AS holiday_days,
       SUM(CASE WHEN a.status = 'Weekly Off' THEN 1 ELSE 0 END) AS weekly_off_days,
       ROUND(1.0 *
             SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) /
             NULLIF(SUM(CASE WHEN a.status IN ('Present', 'Absent', 'Missing Punch')
                             THEN 1 ELSE 0 END), 0), 4) AS absenteeism_rate
FROM warehouse.fact_attendance_daily a
WHERE a.work_date BETWEEN '2026-04-01' AND '2026-09-30'
GROUP BY a.plant, substr(a.work_date, 1, 7)
ORDER BY a.plant, month
