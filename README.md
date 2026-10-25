# Indus Weave HR Data Pipeline — Hackathon Deliverable

Six months of HR exports (Apr–Sep 2026) for Indus Weave Textiles, rebuilt into
a trustworthy, queryable answer: **raw ingest → cleaned staging → attendance
logic → star warehouse → 10 business questions → automated data-quality proof →
three CFO findings**. Python 3 + SQLite, no server, one command end-to-end.

---

## 1. Rebuild from a clean machine (mentor quickstart)

**Prerequisites:** Python 3.10+ (verified on 3.13), ~500 MB disk, no database
server. Network only for `pip install`; runtime is fully offline.

```bash
git clone https://github.com/AAliKKhan/smit-mcde-hackathon.git
cd smit-mcde-hackathon
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\Activate
pip install -r requirements.txt
python run_pipeline.py                                # Stages 1→6, one command
```

Expected: per-file raw row counts (green), staging build messages, warehouse
load counts, 10 query results written to `analytics/results/`, and a final
`dq_results: 58 checks, 58 PASS, 0 FAIL` (exit code 0). Runtime ≈ 2 minutes.

**Stage-by-stage** (debugging / parallel work; every step is idempotent):

```bash
python -m ingestion.load_raw          # Stage 1 → raw.*            Gate R
python -m ingestion.counts            # expected vs actual counts (exit ≠ 0 on mismatch)
python -m transform.build             # Stage 2+3 → staging.*      Gates S + A
python -m warehouse.build_warehouse   # Stage 4 → warehouse.*      Gate W
python -m analytics.run_all           # Stage 5 → results/*.csv    Gate Q
python -m quality.run_dq              # Stage 6 → dq_results       Gate D
python -m ingestion.load_incremental  # bonus: append only new rows (delta load)
python -m dashboard.build_dashboard   # bonus: rebuild dashboard/index.html
python run_pipeline.py --stage 4      # or any single stage
python -m pytest tests/ -q            # 33 tests
```

**60-second verification**

```sql
SELECT status, COUNT(*) FROM dq_results GROUP BY status;   -- PASS only
```

`db/indus_weave.db` can be deleted at any time — `run_pipeline.py` recreates
everything from `data/`. Nothing in `data/` is ever written (raw is immutable).

---

## 2. Design decisions

| Decision | Why |
|---|---|
| **SQLite, 3 attached DB files** (ADR-001, `history/adr/`) | The case study mandates Python 3 + SQL and allows SQLite when a team cannot run PostgreSQL. `raw.db`/`staging.db`/`warehouse.db` attach into one connection so a mentor can inspect a layer in isolation or join across them. |
| **Rule wins over data** (Constitution I) | Every disagreement (mixed date formats, 50 duplicate `emp_id`s, 25 overlap + 12 gap history rows, device drift) is repaired in code with the rule number cited — never by editing `data/`. |
| **Attendance day model** (ADR-002) | A punch pair within 12.5 h = one session; >16 h treated as data error and flagged. Night punches attach to the shift's start date (Rule 7). OT rounds *down* to half-hours (Rules 14/15) so computed OT is conservative. |
| **SCD2 employment dimensions** | `dim_employee` versions track department/grade/salary by day via recomputed history (Rule 2), so fact tables attribute cost to the department on the **last day of the month** (Rule 3) with no lookups at query time. |
| **Definitions documented where they're decided** | Q2 = separations ÷ average of start/end headcount; Q3 = Absent ÷ (Present+Absent+MissingPunch); Q7 = positive earning month with zero worked hours; Q8 = payroll month *starting* after separation (final settlement month excluded). Each SQL file's header states its definition and why. |
| **`dq_results` as a table, not console noise** | All 58 checks (reconciliation, keys, referential integrity, SCD2, accepted domains, sanity) land in `main.dq_results` with `run_id` so a grader can query evidence instead of trusting a screenshot. |
| **Idempotent everywhere** | `DELETE` + reload or create-or-replace per stage; rerunning any stage — or the whole pipeline — converges to the same state. |

---

## 3. Drift-correction write-up (Rule 11)

Generated evidence: `docs/drift_analysis.md` (produced by `transform/04_punches.py`).

Method: map punches via Rule 8 → for each employee-day take the **first punch**
as check-in proxy → subtract the roster shift start for that day → average the
delta per device. A clock that is off shifts *every* employee on that device
identically, while ordinary lateness averages out.

| device | samples | mean delta vs shift start |
|---|---:|---:|
| DEV-FSD-01 | 37,502 | −4.2 min |
| DEV-HO-01 | 16,641 | −4.7 min |
| DEV-KOR-01 | 39,472 | −4.5 min |
| **DEV-SITE-01** | 33,203 | **+25.7 min** |

**Correction:** DEV-SITE-01's mean sits +30.2 min above the peer median
(−4.5 min), i.e. its clock runs 30 minutes slow. We apply a **−30 min offset**
to every punch from that device before sessionisation; post-correction its mean
delta is −4.3 min, in line with the other three devices. Evidence table and
before/after means are in `docs/drift_analysis.md`; the correction is
recomputed on every run (not hard-coded).

---

## 4. Rule-citation map (all 21 rules → code)

| Rule | Statement (short) | Implemented in |
|---:|---|---|
| 1 | Dedupe `emp_id` by latest `updated_at` | `transform/01_clean_employees.py` (50 ids / 100 rows resolved) |
| 2 | History is source of truth; recompute `effective_to` = day before next record | `transform/02_clean_history.py` (25 overlaps, 12 gaps repaired) |
| 3 | Month figures use department on last day of month | `warehouse/build_warehouse.py` (`fact_payroll_line.dept_id_month_end`, SCD2 join) |
| 4 | Headcount at month end: hired ≤ month end, not separated before | `analytics/q01_month_end_headcount.sql`, `q02_monthly_attrition.sql` |
| 5 | Plant rotation DAY/EVE/NIGHT; HO & managers GEN | `transform/03_clean_reference.py`, `warehouse.dim_shift` |
| 6 | Missing roster week → previous week's shift | `transform/04_punches.py` |
| 7 | Night punch belongs to the shift's start date | `transform/07_attendance_daily.py` (sessionisation) |
| 8 | Punch mapping = `device_id` + `device_user_id`; unmapped → rejected | `transform/04_punches.py` (rejected table kept) |
| 9 | Punches ≤2 min apart count as one | `transform/04_punches.py` |
| 10 | Check-in = first punch, checkout = last; one punch = Missing Punch | `transform/04_punches.py` + `07_attendance_daily.py` |
| 11 | Detect & correct device clock drift, explain how | `transform/04_punches.py` → `docs/drift_analysis.md` (§3 above) |
| 12 | Attendance status priority (Weekly Off → Holiday → On Leave → Present → Missing Punch → Absent) | `transform/07_attendance_daily.py` (CASE chain) |
| 13 | Late/early = >10 min outside shift, Present days only | `transform/07_attendance_daily.py` |
| 14 | Weekday OT = minutes after shift end, floor to half-hour | `transform/07_attendance_daily.py` (`floor(min/30)*0.5`) |
| 15 | Sunday/holiday work = all OT | `transform/07_attendance_daily.py` |
| 16 | Leave counts only if Manager **and** HR approved, not cancelled | `transform/05_leave.py` |
| 17 | Leave days = from–to minus Sundays/plant holidays | `transform/05_leave.py` |
| 18 | `annual_leave_entitlement` = full-year Annual entitlement | `transform/05_leave.py`, `warehouse.dim_employee` (14/20-day types) |
| 19 | Approved OT = `status = 'Approved'` only | `transform/06_overtime_payroll.py` → `warehouse.fact_overtime_approved` |
| 20 | Payroll `OVERTIME.units` = hours paid (from approved requests) | `transform/06_overtime_payroll.py` → `fact_payroll_line` |
| 21 | Cost = sum of `EARNING` lines; deductions positive with `component_type='DEDUCTION'` | `transform/06_overtime_payroll.py` → all cost queries |

Rule text: `data/data_dictionary.md`. Profiling evidence of every planted
issue: `docs/profile_notes.md` (SC-003).

---

## 5. Data-quality proof (Gate D)

`python -m quality.run_dq` writes **58 checks** into `main.dq_results`
(`run_id, check_id, layer, target, status, failure_count, detail, checked_at`):

- **reconciliation** — raw = staging + rejected for every table (SC-002)
- **keys** — duplicates/nulls on all 26 primary keys
- **referential integrity** — every fact key resolves; `PRAGMA foreign_key_check` = 0
- **SCD2** — no overlap, no gap, exactly one current version per employee
- **sanity/domains** — status in accepted set, dates inside Apr–Sep window, parity between staging and warehouse status totals
- **raw counts** — every file's row count matches `config.EXPECTED_COUNTS` (Gate R)

Proof under failure: `tests/test_dq.py` seeds an invalid attendance status,
observes `status_in_domain` flip to FAIL, restores the row and observes all
58 PASS again (SC-007).

---

## 6. CFO findings (exact three)

`presentation/cfo_findings.md` — each finding = number + evidence query + action:

1. **Stitching (D20) paid 7,659 OT hours vs 4,901 computed** (+56%, ≈ PKR 1.36 m
   unsupported; gap 0 in April → +130% by September; approvals track payments,
   not punches).
2. **PKR 2,879,197 paid to 7 employees for 37 employee-months with zero
   Present days** (six never present all six months).
3. **PKR 1,948,000 paid to 5 ex-employees for 21 full months after their
   separation date** (up to 5 months / 131 days past exit).

Deck: `presentation/slides.pdf` (6 slides). Demo script:
`presentation/demo_script.md`.

---

## 7. Repository map

```
run_pipeline.py            one-command rebuild (stages 1→6, --stage N)
config.py                  paths, expected counts, file→table map
common/db.py               connection factory, PRAGMAs, attach helper
ingestion/                 load_raw (raw immutable), load_incremental (delta), counts gate, profiler
transform/                 01..07 clean → attendance (Gates S + A)
warehouse/                 ddl/ (schemas+indexes), build_warehouse, ERD (erd.png/dbml)
analytics/                 q01..q10.sql + b01 funnel + run_all.py + results/*.csv
quality/                   checks.py (families) + run_dq.py (orchestrator → dq_results)
dashboard/                 bonus: build_dashboard.py → index.html (warehouse.* charts)
presentation/              cfo_findings.md, slides.pdf, demo_script.md, make_slides.py
docs/                      profile_notes, drift_analysis, history_repairs
history/adr/               ADR-001 (SQLite), ADR-002 (attendance model)
specs/001-hr-pipeline/     spec, plan, tasks (all gates), contracts, data-model
tests/                     33 tests: raw counts, staging invariants, warehouse, DQ
```

---

## 8. Rubric → artifact map

| Rubric criterion (weight) | Where |
|---|---|
| Correct answers (25) | `analytics/q01..q10.sql`, `analytics/results/*.csv` |
| Cleaning & business logic (20) | `transform/01..07`, `docs/` quarantine/repair notes, rule map §4 |
| Data model (15) | `warehouse/ddl/`, `warehouse/erd.png`, SCD2 dimensions + 4 facts |
| Data quality & reconciliation (15) | `quality/`, `main.dq_results` (58 checks), `tests/test_dq.py` |
| CFO findings & demo (15) | `presentation/cfo_findings.md`, `slides.pdf`, `demo_script.md` |
| Code quality & reproducibility (10) | `run_pipeline.py`, `requirements.txt`, README, 33 tests, idempotent stages |
| **Bonus (+10)** | `run_pipeline.py` one-command rebuild; `ingestion/load_incremental.py` (delta load); `analytics/b01_recruitment_funnel.sql`; `dashboard/index.html` (all four guide bonus tasks) |

---

## 9. Team

- **Ali Khan** ([@AAliKKhan](https://github.com/AAliKKhan)) — pipeline, warehouse, analytics, DQ
- **Sana Yousuf** ([@sanayousuf](https://github.com/sanayousuf)) — ingestion & cleaning, data profiling, tests
- **Bilal Ahmed** ([@bilalahmed-dev](https://github.com/bilalahmed-dev)) — DQ checks, dashboard, demo pack
- **Hina Raza** ([@hinaraza](https://github.com/hinaraza)) — specs, README, CFO findings, slides

---

*Everything in this repository regenerates from `data/` via
`python run_pipeline.py`. If a number here ever disagrees with a fresh run,
the fresh run wins — and please open an issue.*
