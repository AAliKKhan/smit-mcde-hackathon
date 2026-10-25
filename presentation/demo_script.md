# Demo script — 5 minutes (T056, FR-057)

Rehearse until every team member can narrate any line without notes. Timings
are cumulative from "0:00". Terminal is pre-warmed in the repo root; DB already
built (or run the live segment shown — it only takes ~2 minutes).

---

## 0:00–0:30 — Problem (slide 1)

> "Indus Weave Textiles gave us six months of HR exports — 12 files, 1,266
> employees, four plants — plus 21 business rules that the export itself
> violates: mixed date formats, 50 duplicate employees, 37 broken history
> rows, and a biometric clock running 30 minutes slow. The CFO wants answers
> she can defend. We built one pipeline that produces those answers **and**
> proves the data underneath them is clean."

**If asked why this matters:** every figure in payroll is potentially wrong
until reconciliation passes; we are the control layer between raw exports and
the CFO's decisions.

## 0:30–1:30 — Pipeline live (slide 2)

Run (or narrate if pre-run):

```bash
python run_pipeline.py
```

> "One command, six gated stages. Stage 1 loads the files verbatim — raw is
> immutable, hashes on every row. Stages 2–3 apply the 21 rules in code:
> dedupe, recompute history, correct the drifting device, sessionise punches,
> build one attendance row per employee-day. Stage 4 loads a star schema —
> four SCD2 dimensions, four fact tables, zero orphan keys. Stage 5 runs ten
> questions to CSV. Stage 6 runs 58 data-quality checks into `dq_results`."

Point at the timing table + final line `58 checks, 58 PASS, 0 FAIL`.

**If asked about idempotency:** "Every stage is delete-and-reload; rerun any
stage — or the whole pipeline — and you converge to the same state. We delete
`db/` any time and rebuild from `data/`."

## 1:30–2:15 — Model + trust (ERD, DQ)

Show `warehouse/erd.png` for 15 seconds, then:

```sql
SELECT status, COUNT(*) FROM dq_results GROUP BY status;
```

> "Four dimensions — date, employee (versioned by day so department
> attribution follows Rule 3), department, shift — and four facts: attendance
> days, leave days, approved overtime, payroll lines. All 58 checks are in
> `dq_results` with a run id: reconciliation (raw = staging + rejected),
> primary keys, referential integrity, SCD2 overlap/gap, accepted domains."

**Live DQ proof** (30 s, optional but recommended):

```bash
python -m pytest tests/test_dq.py -q
```

> "This test corrupts one attendance status on purpose, shows the domain check
> flip to FAIL, restores it, and shows all 58 PASS again. Green means green
> because we've seen it red."

## 2:15–4:15 — The three findings (slides 3–5)

**Finding 1 — 0:40**

> "Question 6 asks which departments are paid more overtime than their punches
> justify. Exactly one breaches the 15% threshold: Stitching. They paid 7,659
> hours — 4,901 of which the biometric data supports. That's a 2,758-hour
> overage, about PKR 1.36 million. And it's not a constant gap: zero in April,
> growing every month to +130% in September. Approved hours track *paid*
> hours, not punch hours — the approval layer is ratifying the payment.
> Action: block OT posting unless approved hours sit inside punch-derived
> windows."

**Finding 2 — 0:40**

> "Question 7: who was paid in a month with zero worked hours? 58
> employee-months, PKR 4.83 million. Subtract the ex-employees — that's
> Finding 3 — and you still have PKR 2,879,197: seven employees, 37 months,
> zero present days. Six of them were never present in any of the six months
> while salary kept flowing. Action: attendance-to-payroll release gate —
> nothing pays while uncertified zero-attendance months exist."

**Finding 3 — 0:40**

> "Question 8: payroll months that start entirely after someone's separation
> date. Five employees, 21 full months, PKR 1,948,000. Worst case: E10471 left
> April 23rd and collected PKR 132,000 a month through September — 131 days
> after their last day. Action: the query itself is the payroll block —
> `separation_date < month start` refuses the line."

**Transition:** "Together — about PKR 6.2 million of exposure in one
six-month window, each number backed by a query you can rerun."

## 4:15–5:00 — The ask (slide 6)

> "Three controls, all already written: OT must match punches, zero-attendance
> pay blocks, post-separation pay blocks. Run this pipeline monthly — every
> number regenerates, every check re-runs, `dq_results` is the audit trail.
> Deliverables: deck, findings with evidence SQL, README, ERD, ten answers,
> 58 checks, 32 tests — all from `python run_pipeline.py`."

Q&A parking lot (don't narrate unless asked):
- **Why SQLite?** ADR-001: case study allows it, zero setup, mentors can open
  the file directly; the SQL is portable to Postgres unchanged.
- **Night shifts?** Rule 7 — punch attaches to the shift's *start* date;
  12.5-hour session window, capped at 16.
- **Why is Q8's settlement month excluded?** Paying through your last day is
  correct; we only flag months that *start* after the exit.
- **Where's the fraud proven?** We don't claim fraud — we claim *evidence
  gaps* and hand the controller three reproducible queries.

---

## Rehearsal checklist

- [ ] Full run-through ≤ 5:00 (phone timer)
- [ ] Each member narrates at least one finding cold
- [ ] `run_pipeline.py`, `pytest tests/test_dq.py -q`, and the `dq_results`
      query each rehearsed at least once (including failure modes)
- [ ] Backup: screenshots in `presentation/slides/` if live terminal fails
