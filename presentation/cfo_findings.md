# CFO Findings — Indus Weave Textiles (Apr–Sep 2026)

Exactly three findings, each stated as a **number**, the **evidence query** that
produces it, and a **recommended action** (FR-055). Every figure below comes from
`analytics/results/*.csv`, regenerated on each rebuild by
`python run_pipeline.py` (stage 5). Query definitions and edge decisions are
documented in the header comments of the SQL files.

---

## Finding 1 — Stitching pays overtime it cannot see: 2,758 unpaid-for punch hours (≈ PKR 1.36 m)

**Number.**
Stitching (D20, Faisalabad) is the **only** department where paid overtime
exceeds punch-computed overtime by more than 15%:

| measure (Apr–Sep 2026) | hours |
|---|---:|
| Computed from punches (Rules 14/15) | **4,901.0** |
| Approved in OT requests (Rule 20) | 7,656.0 |
| Paid in payroll (Rule 19) | **7,659.0** |
| **Overage (paid − computed)** | **+2,758.0 h (+56%, ratio 1.56)** |

- **PKR 3,771,337** of OT was paid to Stitching; roughly **PKR 1.36 m** of it
  has no punch support (2,758 h × the department's ~PKR 492/h OT rate).
- The gap is **0 in April** (761.5 paid vs 779.5 computed) and widens every
  month to **September: 1,778.5 paid vs 772.5 computed (+130%)** — an
  escalating pattern, not a rounding dispute.
- Approved hours track *paid* hours month-for-month (7,656 vs 7,659) instead of
  *computed* hours: the approval layer is ratifying the payment, not the punches.
- Stitching alone is **20% of all OT paid** in the window (PKR 19,003,890).

**Evidence query** — `analytics/q06_dept_paid_over_computed_15pct.sql` (full
text; result: `analytics/results/q06_dept_paid_over_computed_15pct.csv`, 1 row):

```sql
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
SELECT d.plant, d.dept_id, d.dept_name,
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
ORDER BY overage_hours DESC;
```

Monthly drill-down for D20 (computed vs approved vs paid, hours):

| month | computed | approved | paid |
|---|---:|---:|---:|
| 2026-04 | 779.5 | 761.5 | 761.5 |
| 2026-05 | 852.5 | 1008.0 | 1008.0 |
| 2026-06 | 764.0 | 1122.0 | 1122.0 |
| 2026-07 | 805.0 | 1428.0 | 1440.5 |
| 2026-08 | 927.5 | 1558.0 | 1548.5 |
| 2026-09 | 772.5 | 1778.5 | 1778.5 |

**Recommended action.**
Make OT payroll posting conditional on punch evidence: an OT row may post only
if its hours fall inside a punch-derived OT window for the same employee-day
(strictest: approved ⊆ computed, not approved ≈ paid). Open a review of D20's
May→Sep approvals — identify which supervisor approved the escalation — and
hold Stitching's next OT run until the +2,758 h is explained or clawed back.
Standing control: the same query becomes a monthly DQ check
(`paid > computed × 1.15` = FAIL) so the gap cannot re-open silently.

---

## Finding 2 — PKR 2,879,197 paid to 7 employees for 37 months in which they were never once present

**Number.**
Employees with a **positive EARNING month but zero worked hours** that month
(Q7) total **PKR 4,827,197 across 58 employee-months / 12 employees**. Excluding
the post-separation months (Finding 3) leaves the core problem:

| zero-attendance pay that is NOT post-separation | |
|---|---:|
| Employees | **7** (E10397, E10399, E10491, E10564, E10907, E11064, E11089) |
| Employee-months with pay and zero worked hours | **37** |
| Amount paid | **PKR 2,879,197** |
| Present days across all 37 months | **0** |

Six of the seven were **never Present in any of the six months** (6 months each:
E10399 PKR 541,125; E10491 PKR 487,650; E11064 PKR 510,900; E11089 PKR 471,375;
E10907 PKR 462,075; E10564 PKR 403,950) while payroll kept paying full
earnings; E10397 was paid PKR 2,122 for its single month. The remaining
PKR 1,948,000 of the Q7 total is the Finding 3 set.

**Evidence query** — `analytics/q07_paid_zero_attendance.sql` (full text;
result: `analytics/results/q07_paid_zero_attendance.csv`, 58 rows):

```sql
WITH pay AS (
  SELECT emp_id, payroll_month AS month, SUM(amount) AS paid_amount
  FROM warehouse.fact_payroll_line
  WHERE component_type = 'EARNING'
  GROUP BY emp_id, payroll_month
  HAVING SUM(amount) > 0
),
att AS (
  SELECT emp_id, substr(work_date, 1, 7) AS month,
         COUNT(*) AS attendance_days,
         SUM(CASE WHEN status = 'Present'    THEN 1 ELSE 0 END) AS present_days,
         SUM(CASE WHEN status = 'Absent'     THEN 1 ELSE 0 END) AS absent_days,
         SUM(CASE WHEN status = 'On Leave'   THEN 1 ELSE 0 END) AS leave_days,
         SUM(CASE WHEN status = 'Weekly Off' THEN 1 ELSE 0 END) AS weekly_off_days,
         SUM(worked_hours) AS worked_hours
  FROM warehouse.fact_attendance_daily
  GROUP BY emp_id, substr(work_date, 1, 7)
)
SELECT p.emp_id, de.full_name, de.plant, de.dept_name, p.month,
       ROUND(p.paid_amount, 2) AS paid_amount,
       COALESCE(a.attendance_days, 0) AS attendance_days,
       COALESCE(a.present_days, 0)    AS present_days,
       COALESCE(a.absent_days, 0)     AS absent_days,
       COALESCE(a.leave_days, 0)      AS leave_days,
       ROUND(COALESCE(a.worked_hours, 0), 2) AS worked_hours
FROM pay p
LEFT JOIN att a ON a.emp_id = p.emp_id AND a.month = p.month
JOIN warehouse.dim_employee de
  ON de.emp_id = p.emp_id AND de.is_current = 1
WHERE COALESCE(a.worked_hours, 0) = 0
ORDER BY p.emp_id, p.month;
```

**Recommended action.**
Institute a hard attendance-to-payroll gate: payroll cannot release a month
while `paid employee-months with worked_hours = 0` is non-zero — the manager of
each affected department must certify or reverse the pay. The six chronic cases
need same-week HR investigation (salary still flowing, workforce spine still
lists them). Add this query as a standing DQ check in `quality.run_dq` so any
future zero-attendance pay month fails the pipeline before it reaches payroll.

---

## Finding 3 — PKR 1,948,000 paid to 5 ex-employees for 21 full months after they left

**Number.**
EARNING payroll in months that **start entirely after the separation date**
(Q8; the final settlement month that *contains* the exit is excluded, so this is
pure overrun):

| emp_id | name | dept | separated | months paid after exit | total |
|---|---|---|---|---:|---:|
| E10471 | Umair Baloch | Human Resources | 2026-04-23 | 5 (May–Sep) | **PKR 660,000** |
| E11222 | Naveed Ansari | Dyeing | 2026-05-16 | 4 (Jun–Sep) | PKR 418,100 |
| E10332 | Amna Awan | Warehouse | 2026-05-14 | 4 (Jun–Sep) | PKR 322,000 |
| E10295 | Sohail Hussain | Finishing | 2026-05-11 | 4 (Jun–Sep) | PKR 253,800 |
| E10989 | Tariq Jatoi | Packing | 2026-05-18 | 4 (Jun–Sep) | PKR 294,100 |
| **total** | | | | **21 employee-months** | **PKR 1,948,000** |

E10471 kept drawing a full PKR 132,000/month for **131 days** after their last
day worked — every one of these months also has zero attendance (they appear in
Q7 as well).

**Evidence query** — `analytics/q08_pay_after_separation.sql` (full text;
result: `analytics/results/q08_pay_after_separation.csv`, 21 rows):

```sql
WITH pay AS (
  SELECT emp_id, payroll_month AS month, SUM(amount) AS paid_amount
  FROM warehouse.fact_payroll_line
  WHERE component_type = 'EARNING'
  GROUP BY emp_id, payroll_month
  HAVING SUM(amount) > 0
)
SELECT p.emp_id, de.full_name, de.plant, de.dept_name,
       de.separation_date, p.month AS payroll_month,
       ROUND(p.paid_amount, 2) AS paid_amount,
       CAST(julianday(date(p.month || '-01')) -
            julianday(de.separation_date) AS INT) AS days_after_separation
FROM pay p
JOIN warehouse.dim_employee de
  ON de.emp_id = p.emp_id AND de.is_current = 1
WHERE de.separation_date IS NOT NULL
  AND date(p.month || '-01') > de.separation_date
ORDER BY de.separation_date, p.emp_id, p.month;
```

**Recommended action.**
Payroll must be driven off the separation feed: an automated block that stops
any earnings line for an employee whose `separation_date < month start` (the
query above is the block's exact predicate, already running as a DQ check).
Recover the PKR 1,948,000 through the exit checklist, and reconcile the four
separations from mid-May that continued into the June run — they indicate the
offboarding trigger failed twice, not once.

---

## Reproduce everything

```bash
pip install -r requirements.txt
python run_pipeline.py          # stages 1-6; writes all CSVs + dq_results
```

All three findings regenerate from stage 5 output; stage 6 (`dq_results`)
proves the underlying tables passed 58 integrity checks before these numbers
were trusted.
