"""T035 / FR-030 - render warehouse/erd.png from the star-schema layout.

The DBML source (warehouse/erd.dbml) is the human-editable description; this
script draws the same tables/FKs with Pillow so the committed PNG is
reproducible from the repo (Principle IV - no hand-edited binaries).

Run: python -m warehouse.make_erd   -> warehouse/erd.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent / "erd.png"
FONT_DIR = Path("C:/Windows/Fonts")

DIMS = {
    "dim_date": [
        ("date_key", "TEXT", "pk"),
        ("day", "INTEGER", ""),
        ("month", "TEXT", ""),
        ("month_start", "TEXT", ""),
        ("month_end", "TEXT", ""),
        ("week_start", "TEXT", ""),
        ("weekday_no", "INTEGER", ""),
        ("weekday_name", "TEXT", ""),
        ("is_weekend", "INTEGER", ""),
        ("is_holiday_all", "INTEGER", ""),
        ("holiday_name", "TEXT", ""),
    ],
    "dim_employee": [
        ("employee_key", "INTEGER", "pk"),
        ("emp_id", "TEXT", "biz"),
        ("full_name", "TEXT", ""),
        ("gender", "TEXT", ""),
        ("date_of_birth", "TEXT", ""),
        ("plant", "TEXT", ""),
        ("dept_id", "TEXT", "fk"),
        ("dept_name", "TEXT", ""),
        ("designation", "TEXT", ""),
        ("grade", "TEXT", ""),
        ("employment_type", "TEXT", ""),
        ("status", "TEXT", ""),
        ("hire_date", "TEXT", ""),
        ("separation_date", "TEXT", ""),
        ("annual_leave_entitlement", "INTEGER", ""),
        ("basic_salary", "REAL", ""),
        ("change_reason", "TEXT", ""),
        ("valid_from", "TEXT", "scd"),
        ("valid_to", "TEXT", "scd"),
        ("is_current", "INTEGER", "scd"),
    ],
    "dim_department": [
        ("dept_id", "TEXT", "pk"),
        ("dept_name", "TEXT", ""),
        ("plant", "TEXT", ""),
        ("cost_center", "TEXT", ""),
        ("previous_name", "TEXT", ""),
        ("renamed_on", "TEXT", ""),
    ],
    "dim_shift": [
        ("shift_code", "TEXT", "pk"),
        ("name", "TEXT", ""),
        ("start_time", "TEXT", ""),
        ("end_time", "TEXT", ""),
        ("crosses_midnight", "INTEGER", ""),
        ("grace_minutes", "INTEGER", ""),
        ("applies_to", "TEXT", ""),
    ],
}

FACTS = {
    "fact_attendance_daily": [
        ("employee_key", "INTEGER", "fk"),
        ("date_key", "TEXT", "fk"),
        ("shift_code", "TEXT", "fk"),
        ("emp_id", "TEXT", ""),
        ("work_date", "TEXT", ""),
        ("plant", "TEXT", ""),
        ("dept_id", "TEXT", "fk"),
        ("status", "TEXT", ""),
        ("punches_count", "INTEGER", ""),
        ("worked_hours", "REAL", ""),
        ("late_minutes", "INTEGER", ""),
        ("early_leave_minutes", "INTEGER", ""),
        ("ot_hours", "REAL", ""),
        ("is_working_day", "INTEGER", ""),
    ],
    "fact_leave_day": [
        ("employee_key", "INTEGER", "fk"),
        ("date_key", "TEXT", "fk"),
        ("request_id", "TEXT", "pk"),
        ("emp_id", "TEXT", ""),
        ("leave_type", "TEXT", ""),
        ("plant", "TEXT", ""),
        ("dept_id", "TEXT", "fk"),
    ],
    "fact_overtime_approved": [
        ("request_id", "TEXT", "pk"),
        ("employee_key", "INTEGER", "fk"),
        ("date_key", "TEXT", "fk"),
        ("emp_id", "TEXT", ""),
        ("ot_date", "TEXT", ""),
        ("approved_hours", "REAL", ""),
        ("requested_hours", "REAL", ""),
        ("plant", "TEXT", ""),
        ("dept_id", "TEXT", "fk"),
    ],
    "fact_payroll_line": [
        ("line_id", "TEXT", "pk"),
        ("employee_key", "INTEGER", "fk"),
        ("payroll_month", "TEXT", "fk-month"),
        ("emp_id", "TEXT", ""),
        ("component", "TEXT", ""),
        ("component_type", "TEXT", ""),
        ("units", "REAL", ""),
        ("amount", "REAL", ""),
        ("plant", "TEXT", ""),
        ("dept_id_month_end", "TEXT", "fk"),
    ],
}

# (fact, fk column, dim, dim pk column, dashed?)
EDGES = [
    ("fact_attendance_daily", "employee_key", "dim_employee", "employee_key", False),
    ("fact_attendance_daily", "date_key", "dim_date", "date_key", False),
    ("fact_attendance_daily", "shift_code", "dim_shift", "shift_code", False),
    ("fact_attendance_daily", "dept_id", "dim_department", "dept_id", False),
    ("fact_leave_day", "employee_key", "dim_employee", "employee_key", False),
    ("fact_leave_day", "date_key", "dim_date", "date_key", False),
    ("fact_leave_day", "dept_id", "dim_department", "dept_id", False),
    ("fact_overtime_approved", "employee_key", "dim_employee", "employee_key", False),
    ("fact_overtime_approved", "date_key", "dim_date", "date_key", False),
    ("fact_overtime_approved", "dept_id", "dim_department", "dept_id", False),
    ("fact_payroll_line", "employee_key", "dim_employee", "employee_key", False),
    ("fact_payroll_line", "payroll_month", "dim_date", "month", True),
    ("fact_payroll_line", "dept_id_month_end", "dim_department", "dept_id", False),
]

DIM_COLOR = {
    "dim_employee": (44, 110, 145),
    "dim_date": (123, 94, 167),
    "dim_department": (46, 139, 87),
    "dim_shift": (192, 57, 43),
}
FACT_COLOR = (184, 92, 56)
HDR_H, ROW_H, PAD = 28, 20, 14
MARGIN, GAP_X, GAP_Y = 40, 46, 170


def _font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    names = (["consola.ttf"] if mono else
             (["segoeuib.ttf", "segoeui.ttf"] if bold else ["segoeui.ttf"]))
    for name in names:
        p = FONT_DIR / name
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()  # type: ignore[return-value]


def _measure(name: str, cols: list[tuple[str, str, str]],
             f_name, f_type) -> tuple[int, int]:
    w_name = max(f_name.getlength(c[0]) for c in cols)
    w_type = max(f_type.getlength(c[1]) for c in cols)
    w_title = f_name.getlength(name) + 16
    return int(max(w_name + w_type + 40, w_title)) + PAD * 2, HDR_H + ROW_H * len(cols) + 6


def _box(draw: ImageDraw.ImageDraw, x: int, y: int, name: str,
         cols: list[tuple[str, str, str]], color: tuple, w: int, h: int,
         f_name, f_type, f_hdr) -> dict[str, int]:
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(255, 255, 255),
                           outline=color, width=2)
    draw.rounded_rectangle([x, y, x + w, y + HDR_H], radius=8, fill=color)
    draw.rectangle([x, y + HDR_H - 8, x + w, y + HDR_H], fill=color)
    draw.text((x + 10, y + 5), name, font=f_hdr, fill=(255, 255, 255))
    anchors: dict[str, int] = {}
    for i, (cname, ctype, flag) in enumerate(cols):
        cy = y + HDR_H + 4 + i * ROW_H
        if i % 2 == 1:
            draw.rectangle([x + 2, cy, x + w - 2, cy + ROW_H], fill=(244, 246, 248))
        fill = (30, 30, 30)
        prefix = ""
        if flag == "pk":
            prefix, fill = "* ", (176, 128, 0)
        elif flag == "fk":
            prefix, fill = "→ ", color
        elif flag == "scd":
            prefix, fill = "~ ", (100, 100, 100)
        elif flag == "biz":
            prefix, fill = "# ", (100, 100, 100)
        draw.text((x + 10, cy + 3), prefix + cname, font=f_name, fill=fill)
        tw = f_type.getlength(ctype)
        draw.text((x + w - 10 - tw, cy + 3), ctype, font=f_type, fill=(130, 130, 130))
        anchors[cname] = cy + ROW_H // 2
    return anchors


def _dashed(draw, p1, p2, fill, width=2, dash=7):
    import math
    dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if dist == 0:
        return
    steps = int(dist / dash)
    for i in range(steps + 1):
        if i % 2:
            continue
        a = i / steps
        b = min((i + 1) / steps, 1.0)
        draw.line([p1[0] + (p2[0] - p1[0]) * a, p1[1] + (p2[1] - p1[1]) * a,
                   p1[0] + (p2[0] - p1[0]) * b, p1[1] + (p2[1] - p1[1]) * b],
                  fill=fill, width=width)


def main() -> None:
    f_title = _font(22, bold=True)
    f_hdr = _font(15, bold=True)
    f_name = _font(13, mono=True)
    f_type = _font(12, mono=True)
    f_note = _font(13)

    dim_order = ["dim_date", "dim_employee", "dim_department", "dim_shift"]
    fact_order = ["fact_attendance_daily", "fact_leave_day",
                  "fact_overtime_approved", "fact_payroll_line"]

    col_w, dim_h = {}, 0
    for n in dim_order:
        w, h = _measure(n, DIMS[n], f_name, f_type)
        col_w[n] = w
        dim_h = max(dim_h, h)
    fact_w, fact_h = {}, {}
    for n in fact_order:
        w, h = _measure(n, FACTS[n], f_name, f_type)
        fact_w[n], fact_h[n] = w, h

    grid_w = [max(col_w[dim_order[i]], fact_w[fact_order[i]]) for i in range(4)]
    xs = []
    x = MARGIN
    for w in grid_w:
        xs.append(x)
        x += w + GAP_X
    canvas_w = x - GAP_X + MARGIN
    y_dim = 70
    y_fact = y_dim + dim_h + GAP_Y

    # facts may be taller than dims; canvas must fit both + notes
    canvas_h = max(y_fact + max(fact_h.values()), y_dim + dim_h) + 120
    img = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((MARGIN, 24),
              "Indus Weave Textiles - PeopleOps warehouse star schema "
              "(2026-04 .. 2026-09)", font=f_title, fill=(25, 25, 25))
    draw.text((MARGIN, 52),
              "* primary key    → foreign key    ~ SCD2 validity (Rule 2)    "
              "# business key    - - month-level ref    dim_employee: 3,686 "
              "versions / 1,266 employees", font=f_note, fill=(70, 70, 70))

    anchors: dict[str, dict[str, int]] = {}
    boxes: dict[str, tuple[int, int, int, int]] = {}
    for i, n in enumerate(dim_order):
        x0, y0 = xs[i], y_dim
        w = grid_w[i]
        anchors[n] = _box(draw, x0, y0, n, DIMS[n], DIM_COLOR[n], w, dim_h,
                          f_name, f_type, f_hdr)
        boxes[n] = (x0, y0, w, dim_h)
    for i, n in enumerate(fact_order):
        x0, y0 = xs[i], y_fact
        w, h = grid_w[i], fact_h[n]
        anchors[n] = _box(draw, x0, y0, n, FACTS[n], FACT_COLOR, w, h,
                          f_name, f_type, f_hdr)
        boxes[n] = (x0, y0, w, h)

    # edges: fact top edge -> horizontal channel between rows -> dim bottom edge
    fact_counts = {n: sum(1 for e in EDGES if e[0] == n) for n in fact_order}
    dim_counts = {n: sum(1 for e in EDGES if e[2] == n) for n in dim_order}
    fact_seen: dict[str, int] = {}
    dim_seen: dict[str, int] = {}
    channel = y_dim + dim_h + GAP_Y // 2
    for fact, fcol, dim, dcol, dashed in EDGES:
        fx, fy, fw, fh = boxes[fact]
        dx, dy, dw, dh = boxes[dim]
        i = fact_seen.get(fact, 0)
        fact_seen[fact] = i + 1
        j = dim_seen.get(dim, 0)
        dim_seen[dim] = j + 1
        p1 = (fx + fw * (i + 1) / (fact_counts[fact] + 1), fy)
        p2 = (dx + dw * (j + 1) / (dim_counts[dim] + 1), dy + dh)
        pts = [(p1[0], p1[1]), (p1[0], channel), (p2[0], channel), (p2[0], p2[1])]
        color = DIM_COLOR[dim]
        for a, b in zip(pts, pts[1:]):
            if dashed:
                _dashed(draw, a, b, color)
            else:
                draw.line([a, b], fill=color, width=2)
        # arrow head at the dim end (pointing up into the dim)
        draw.polygon([p2, (p2[0] - 6, p2[1] + 12), (p2[0] + 6, p2[1] + 12)],
                     fill=color)

    draw.text((MARGIN, canvas_h - 60),
              "Fact grain: attendance = employee x day | leave = countable "
              "leave day | overtime = approved request | payroll = payslip line",
              font=f_note, fill=(70, 70, 70))
    draw.text((MARGIN, canvas_h - 38),
              "fact_payroll_line.dept_id_month_end = department at month end "
              "/ last working day (Rule 3, dashed month join to dim_date)",
              font=f_note, fill=(70, 70, 70))
    img.save(OUT)
    print(f"  erd: {OUT} written ({canvas_w}x{canvas_h})")


if __name__ == "__main__":
    main()
