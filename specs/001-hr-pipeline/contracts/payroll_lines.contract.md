# Contract: `payroll_lines.csv` — Payroll: Payslips (long format)

**Rows**: 53,617
**Rules**: 20 (OVERTIME `units` = hours paid), 21 (cost = sum of EARNING lines; deductions are
positive amounts typed `DEDUCTION`)

| Column | Raw type | Notes |
|---|---|---|
| `line_id` | text | `PL0000001…`, PK |
| `payroll_month` | text | `YYYY-MM`, 2026-04…2026-09 |
| `emp_id` | text | FK → employees |
| `component` | text | BASIC, HOUSE_RENT, MEDICAL, CONVEYANCE, **OVERTIME**, INCOME_TAX, EOBI, ABSENCE_DEDUCTION, LOAN_INSTALLMENT |
| `component_type` | text | EARNING / DEDUCTION |
| `units` | text | populated for OVERTIME (= paid OT hours) and ABSENCE_DEDUCTION (= days); else empty |
| `amount` | text | numeric; **deductions stored as positive numbers** |

**Validation**: 53,617 rows; `component_type` ∈ {EARNING, DEDUCTION}; components ⊆ domain above;
every (month, emp) with OVERTIME has `units` numeric ≥ 0; no earnings rows negative.
**Pivot contract (SQL)**: `SUM(CASE WHEN component='OVERTIME' THEN units END)` → paid OT hours;
`SUM(CASE WHEN component_type='EARNING' THEN amount END)` → payroll cost (Rule 21).
