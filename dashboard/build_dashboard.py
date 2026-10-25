"""Bonus: static HTML dashboard built on the warehouse tables.

Guide bonus task: "A simple dashboard in any tool, built on the warehouse
tables."  Pure Python + SQL -> one self-contained `dashboard/index.html`
(no JS libraries, no server): KPI cards, monthly bar charts, a department
overtime table and the three CFO finding numbers, all queried live from
warehouse.* (findings aggregates mirror q06/q07/q08 definitions).

Run:  python -m dashboard.build_dashboard   ->  dashboard/index.html
"""

from __future__ import annotations

from pathlib import Path

from common import db

HERE = Path(__file__).resolve().parent
OUT = HERE / "index.html"

MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
MONTH_END = {"2026-04": "2026-04-30", "2026-05": "2026-05-30",
             "2026-06": "2026-06-30", "2026-07": "2026-07-30",
             "2026-08": "2026-08-31", "2026-09": "2026-09-30"}


def _headcount_series() -> list[tuple[str, int]]:
    rows = ", ".join(f"('{m}', '{e}')" for m, e in MONTH_END.items())
    return [
        (r["month"], int(r["n"]))
        for r in db.read_sql(
            f"""
            WITH months(month, mend) AS (VALUES {rows})
            SELECT m.month, COUNT(DISTINCT de.emp_id) AS n
            FROM months m
            CROSS JOIN warehouse.dim_employee de
            WHERE de.is_current = 1
              AND de.hire_date <= m.mend
              AND (de.separation_date IS NULL OR de.separation_date > m.mend)
            GROUP BY m.month ORDER BY m.month
            """
        ).to_dict("records")
    ]


def _payroll_series() -> list[tuple[str, float]]:
    return [
        (r["m"], float(r["amt"]))
        for r in db.read_sql(
            """
            SELECT substr(payroll_month, 1, 7) AS m,
                   SUM(CASE WHEN component_type = 'EARNING' THEN amount END) AS amt
            FROM warehouse.fact_payroll_line
            GROUP BY 1 ORDER BY 1
            """
        ).to_dict("records")
    ]


def _absenteeism_series() -> list[tuple[str, float]]:
    return [
        (r["m"], float(r["rate"]))
        for r in db.read_sql(
            """
            SELECT substr(work_date, 1, 7) AS m,
                   ROUND(100.0 * SUM(CASE WHEN status = 'Absent' THEN 1 ELSE 0 END) /
                         NULLIF(SUM(CASE WHEN status IN
                               ('Present', 'Absent', 'Missing Punch')
                               THEN 1 ELSE 0 END), 0), 2) AS rate
            FROM warehouse.fact_attendance_daily
            GROUP BY 1 ORDER BY 1
            """
        ).to_dict("records")
    ]


def _ot_by_dept() -> list[dict]:
    return db.read_sql(
        """
        WITH comp AS (
          SELECT dept_id, SUM(ot_hours) AS h
          FROM warehouse.fact_attendance_daily GROUP BY dept_id
        ), paid AS (
          SELECT dept_id_month_end AS dept_id,
                 SUM(CASE WHEN component = 'OVERTIME' THEN units END) AS h,
                 SUM(CASE WHEN component = 'OVERTIME' THEN amount END) AS amt
          FROM warehouse.fact_payroll_line GROUP BY dept_id_month_end
        )
        SELECT d.dept_name, d.plant,
               ROUND(COALESCE(c.h, 0), 1) AS computed_h,
               ROUND(COALESCE(p.h, 0), 1) AS paid_h,
               ROUND(COALESCE(p.amt, 0), 0) AS paid_amt,
               ROUND(COALESCE(p.h, 0) - COALESCE(c.h, 0), 1) AS overage_h
        FROM warehouse.dim_department d
        LEFT JOIN comp  c ON c.dept_id = d.dept_id
        LEFT JOIN paid  p ON p.dept_id = d.dept_id
        ORDER BY overage_h DESC LIMIT 8
        """
    ).to_dict("records")


def _kpis() -> dict:
    hc = db.scalar(
        """
        SELECT COUNT(DISTINCT emp_id) FROM warehouse.dim_employee
        WHERE is_current = 1 AND hire_date <= '2026-09-30'
          AND (separation_date IS NULL OR separation_date > '2026-09-30')
        """
    )
    sep = db.scalar(
        """SELECT COUNT(DISTINCT emp_id) FROM warehouse.dim_employee
           WHERE separation_date BETWEEN '2026-04-01' AND '2026-09-30'"""
    )
    cost = db.scalar(
        """SELECT SUM(amount) FROM warehouse.fact_payroll_line
           WHERE component_type = 'EARNING'"""
    )
    ot = db.scalar(
        """SELECT SUM(amount) FROM warehouse.fact_payroll_line
           WHERE component = 'OVERTIME'"""
    )
    dq = db.read_sql(
        """SELECT status, COUNT(*) AS n FROM dq_results GROUP BY status"""
    ).to_dict("records")
    dq_txt = ", ".join(f"{int(r['n'])} {r['status']}" for r in dq)
    return {"headcount": int(hc), "separations": int(sep),
            "cost": float(cost), "ot": float(ot), "dq": dq_txt}


def _findings() -> dict:
    f1 = db.scalar(
        """
        WITH comp AS (
          SELECT dept_id, SUM(ot_hours) AS h FROM warehouse.fact_attendance_daily
          GROUP BY dept_id),
        paid AS (
          SELECT dept_id_month_end AS dept_id,
                 SUM(CASE WHEN component = 'OVERTIME' THEN units END) AS h
          FROM warehouse.fact_payroll_line GROUP BY dept_id_month_end)
        SELECT COALESCE(p.h, 0) - COALESCE(c.h, 0)
        FROM paid p JOIN comp c ON c.dept_id = p.dept_id
        WHERE p.h > c.h * 1.15 ORDER BY 1 DESC LIMIT 1
        """
    )
    f2 = db.scalar(
        """
        WITH pay AS (
          SELECT emp_id, substr(payroll_month, 1, 7) AS m,
                 SUM(CASE WHEN component_type = 'EARNING' THEN amount END) AS amt
          FROM warehouse.fact_payroll_line GROUP BY 1, 2),
        att AS (
          SELECT emp_id, substr(work_date, 1, 7) AS m, SUM(worked_hours) AS wh
          FROM warehouse.fact_attendance_daily GROUP BY 1, 2)
        SELECT COALESCE(SUM(pay.amt), 0) FROM pay
        LEFT JOIN att ON att.emp_id = pay.emp_id AND att.m = pay.m
        JOIN warehouse.dim_employee de ON de.emp_id = pay.emp_id AND de.is_current = 1
        WHERE pay.amt > 0 AND COALESCE(att.wh, 0) = 0
          AND (de.separation_date IS NULL
               OR date(pay.m || '-01') <= de.separation_date)
        """
    )
    f3 = db.scalar(
        """
        WITH pay AS (
          SELECT emp_id, substr(payroll_month, 1, 7) AS m,
                 SUM(CASE WHEN component_type = 'EARNING' THEN amount END) AS amt
          FROM warehouse.fact_payroll_line GROUP BY 1, 2)
        SELECT COALESCE(SUM(pay.amt), 0) FROM pay
        JOIN warehouse.dim_employee de ON de.emp_id = pay.emp_id AND de.is_current = 1
        WHERE de.separation_date IS NOT NULL
          AND date(pay.m || '-01') > de.separation_date AND pay.amt > 0
        """
    )
    return {"f1": float(f1 or 0), "f2": float(f2 or 0), "f3": float(f3 or 0)}


def _bars(rows: list[tuple[str, float]], fmt: str = "{:,.0f}") -> str:
    peak = max((v for _, v in rows), default=1) or 1
    out = []
    for label, v in rows:
        w = max(2.0, 100.0 * v / peak)
        out.append(
            f'<div class="bar-row"><span class="bar-lbl">{label}</span>'
            f'<div class="bar" style="width:{w:.1f}%"></div>'
            f'<span class="bar-val">{fmt.format(v)}</span></div>'
        )
    return "\n".join(out)


def _table(rows: list[dict]) -> str:
    out = ["<table><tr><th>department</th><th>plant</th><th>computed h</th>"
           "<th>paid h</th><th>paid PKR</th><th>overage h</th></tr>"]
    for r in rows:
        cls = ' class="hot"' if r["overage_h"] > 0 else ""
        out.append(
            f"<tr{cls}><td>{r['dept_name']}</td><td>{r['plant']}</td>"
            f"<td>{r['computed_h']:,.1f}</td><td>{r['paid_h']:,.1f}</td>"
            f"<td>{r['paid_amt']:,.0f}</td><td>{r['overage_h']:+,.1f}</td></tr>"
        )
    return "\n".join(out) + "</table>"


def build() -> Path:
    k = _kpis()
    f = _findings()
    hc = _headcount_series()
    pay = _payroll_series()
    abs_ = _absenteeism_series()

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Indus Weave HR Control Tower</title>
<style>
 body {{ font-family: 'Segoe UI', sans-serif; margin: 0; background:#f4f6f8; color:#17212b; }}
 header {{ background:#006c63; color:#fff; padding:22px 32px; }}
 header h1 {{ margin:0; font-size:26px; }} header p {{ margin:6px 0 0; opacity:.9; }}
 main {{ padding:24px 32px; max-width:1200px; margin:0 auto; }}
 .kpis {{ display:grid; grid-template-columns:repeat(5,1fr); gap:14px; margin-bottom:24px; }}
 .kpi {{ background:#fff; border-radius:10px; padding:16px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
 .kpi .v {{ font-size:26px; font-weight:700; color:#006c63; }}
 .kpi .l {{ font-size:12px; color:#5a6876; margin-top:4px; text-transform:uppercase; }}
 .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
 .card {{ background:#fff; border-radius:10px; padding:18px 20px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
 .card h2 {{ margin:0 0 14px; font-size:16px; color:#006c63; }}
 .bar-row {{ display:flex; align-items:center; gap:8px; margin:6px 0; font-size:13px; }}
 .bar-lbl {{ width:64px; color:#5a6876; }}
 .bar {{ height:16px; background:linear-gradient(90deg,#006c63,#3fae9f); border-radius:3px; min-width:2px; }}
 .bar-val {{ margin-left:6px; font-variant-numeric:tabular-nums; }}
 table {{ width:100%; border-collapse:collapse; font-size:13px; }}
 th, td {{ text-align:right; padding:7px 8px; border-bottom:1px solid #e6eaee; }}
 th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align:left; }}
 th {{ color:#5a6876; font-weight:600; }}
 tr.hot td {{ background:#fff3f1; color:#b03a2e; font-weight:600; }}
 .findings {{ grid-column:1 / -1; display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
 .find {{ background:#fff; border-left:5px solid #b03a2e; padding:14px 16px; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
 .find .n {{ font-size:22px; font-weight:700; color:#b03a2e; }}
 .find .t {{ font-size:13px; color:#5a6876; margin-top:6px; }}
 footer {{ text-align:center; color:#5a6876; font-size:12px; padding:18px; }}
</style></head><body>
<header>
 <h1>Indus Weave Textiles &mdash; HR Control Tower</h1>
 <p>Apr&ndash;Sep 2026 &middot; built on warehouse.* by dashboard/build_dashboard.py
 &middot; DQ {k['dq']}</p>
</header>
<main>
 <div class="kpis">
  <div class="kpi"><div class="v">{k['headcount']:,}</div><div class="l">Headcount (Sep 30)</div></div>
  <div class="kpi"><div class="v">{k['separations']:,}</div><div class="l">Separations (6 mo)</div></div>
  <div class="kpi"><div class="v">PKR {k['cost']/1e6:,.1f} M</div><div class="l">Payroll cost</div></div>
  <div class="kpi"><div class="v">PKR {k['ot']/1e6:,.1f} M</div><div class="l">Overtime paid</div></div>
  <div class="kpi"><div class="v">{k['dq'].split()[0]}</div><div class="l">DQ checks passing</div></div>
 </div>
 <div class="grid">
  <div class="card"><h2>Month-end headcount</h2>{_bars(hc)}</div>
  <div class="card"><h2>Payroll cost by month (PKR)</h2>{_bars(pay)}</div>
  <div class="card"><h2>Absenteeism rate by month (%)</h2>{_bars(abs_, "{:.2f}")}</div>
  <div class="card"><h2>Overtime: computed vs paid (top overage depts)</h2>{_table(_ot_by_dept())}</div>
  <div class="findings">
   <div class="find"><div class="n">+{f['f1']:,.0f} h</div>
     <div class="t">Finding 1 &mdash; Stitching paid overtime beyond punch-computed hours
     (q06)</div></div>
   <div class="find"><div class="n">PKR {f['f2']:,.0f}</div>
     <div class="t">Finding 2 &mdash; pay for zero-attendance months, excluding
     post-separation (q07/q08 split)</div></div>
   <div class="find"><div class="n">PKR {f['f3']:,.0f}</div>
     <div class="t">Finding 3 &mdash; pay after separation date (q08)</div></div>
  </div>
 </div>
</main>
<footer>Regenerate: <code>python -m dashboard.build_dashboard</code>
 &middot; numbers query warehouse tables live &middot; Indus Weave is fictional, data is synthetic</footer>
</body></html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html):,} bytes)")
    return OUT


def main() -> int:
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
