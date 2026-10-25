-- B01 (BONUS) Recruitment funnel: conversion % and median days at each
--   stage, from applications.csv (guide bonus task: "Recruitment funnel
--   from applications.csv: conversion and median days at each stage").
-- Funnel = the five main-path stages Applied -> Screened -> Interviewed ->
--   Offered -> Hired. Terminal outcomes (Rejected 1,310; Offer Declined 16)
--   are not funnel steps; they are the reason each stage's count shrinks.
-- Grain: one row per funnel stage. median_days = median calendar days spent
--   in the PREVIOUS stage before reaching this one (SQLite median via
--   ROW_NUMBER: average of the two middle values for even counts).
WITH per_app AS (
  SELECT application_id,
         MAX(CASE WHEN stage = 'Applied'     THEN stage_date END) AS d0,
         MAX(CASE WHEN stage = 'Screened'    THEN stage_date END) AS d1,
         MAX(CASE WHEN stage = 'Interviewed' THEN stage_date END) AS d2,
         MAX(CASE WHEN stage = 'Offered'     THEN stage_date END) AS d3,
         MAX(CASE WHEN stage = 'Hired'       THEN stage_date END) AS d4
  FROM raw.applications
  GROUP BY application_id
),
reach AS (
  SELECT 1 AS step, 'Applied' AS stage, COUNT(d0) AS reached FROM per_app
  UNION ALL
  SELECT 2, 'Screened', COUNT(d1) FROM per_app
  UNION ALL
  SELECT 3, 'Interviewed', COUNT(d2) FROM per_app
  UNION ALL
  SELECT 4, 'Offered', COUNT(d3) FROM per_app
  UNION ALL
  SELECT 5, 'Hired', COUNT(d4) FROM per_app
),
gaps AS (
  SELECT 2 AS step, julianday(d1) - julianday(d0) AS days
  FROM per_app WHERE d0 IS NOT NULL AND d1 IS NOT NULL
  UNION ALL
  SELECT 3, julianday(d2) - julianday(d1)
  FROM per_app WHERE d1 IS NOT NULL AND d2 IS NOT NULL
  UNION ALL
  SELECT 4, julianday(d3) - julianday(d2)
  FROM per_app WHERE d2 IS NOT NULL AND d3 IS NOT NULL
  UNION ALL
  SELECT 5, julianday(d4) - julianday(d3)
  FROM per_app WHERE d3 IS NOT NULL AND d4 IS NOT NULL
),
gaps_ranked AS (
  SELECT step, days,
         ROW_NUMBER() OVER (PARTITION BY step ORDER BY days) AS rn,
         COUNT(*)     OVER (PARTITION BY step)               AS n
  FROM gaps
),
med AS (
  SELECT step, ROUND(AVG(days), 1) AS median_days
  FROM gaps_ranked
  WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
  GROUP BY step
)
SELECT r.step,
       r.stage,
       r.reached,
       ROUND(100.0 * r.reached / NULLIF(p.reached, 0), 1)
         AS conversion_from_prev_pct,
       ROUND(100.0 * r.reached /
             NULLIF((SELECT reached FROM reach WHERE step = 1), 0), 1)
         AS pct_of_applied,
       p.stage AS previous_stage,
       m.median_days AS median_days_in_previous_stage
FROM reach r
LEFT JOIN reach p ON p.step = r.step - 1
LEFT JOIN med  m ON m.step = r.step
ORDER BY r.step
