"""Render presentation/slides.pdf (<=6 slides) from plain text (T055).

Usage:  python -m presentation.make_slides

Design kept deliberately simple: a PIL canvas, one template (title, optional
callout, wrapped bullets), saved twice - as PNGs under presentation/slides/
for review/commit and as a single multi-page PDF at presentation/slides.pdf.
Runs offline; only Pillow is required (pinned in requirements.txt).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
W, H = 1280, 720
MARGIN = 72

INK = (23, 33, 43)
ACCENT = (0, 108, 99)
MUTED = (90, 104, 118)
LIGHT = (236, 240, 243)
WARN = (176, 58, 46)


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


F_SUB = _font("segoeui.ttf", 26)
F_FOOT = _font("segoeui.ttf", 20)


def _fit_font(name: str, text: str, max_w: int, start: int, floor: int) -> ImageFont.FreeTypeFont:
    """Largest font <= start pt whose single line fits max_w."""
    size = start
    while size > floor:
        f = _font(name, size)
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        if probe.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return _font(name, floor)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def slide(title: str, callout: tuple[str, str] | None,
          bullets: list[str], footer: str) -> Image.Image:
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)

    # title auto-shrinks so it never clips or wraps into the callout
    f_title = _fit_font("segoeuib.ttf", title, W - 2 * MARGIN, 52, 32)
    d.text((MARGIN, 52), title, font=f_title, fill=INK)

    # body auto-shrinks until all bullets fit above the footer
    for size in (30, 28, 26, 24):
        f_body = _font("segoeui.ttf", size)
        lh = size + 12
        y, ok = 150 + (150 if callout else 0), True
        for b in bullets:
            y += len(_wrap(d, b, f_body, W - 2 * MARGIN - 44)) * lh + 14
            if y > H - 64:
                ok = False
                break
        if ok:
            break

    y = 150
    if callout:
        big, small = callout
        d.rectangle([MARGIN, y, W - MARGIN, y + 118], fill=LIGHT)
        d.text((MARGIN + 28, y + 14), big, font=_fit_font("segoeuib.ttf", big, W - 2 * MARGIN - 56, 64, 40), fill=WARN)
        d.text((MARGIN + 28, y + 84), small, font=_fit_font("segoeui.ttf", small, W - 2 * MARGIN - 56, 26, 18), fill=MUTED)
        y += 150

    for b in bullets:
        d.ellipse([MARGIN + 6, y + 13, MARGIN + 18, y + 25], fill=ACCENT)
        for ln in _wrap(d, b, f_body, W - 2 * MARGIN - 44):
            d.text((MARGIN + 44, y), ln, font=f_body, fill=INK)
            y += lh
        y += 14

    d.rectangle([0, H - 54, W, H], fill=INK)
    d.text((MARGIN, H - 40), footer, font=F_FOOT, fill=(255, 255, 255))
    return img


def main() -> int:
    slides = [
        slide(
            "The problem: 6 months of HR exports, no trusted answers",
            None,
            [
                "Indus Weave Textiles: 1,266 employees, 4 plants, 12 HCM files (Apr-Sep 2026) "
                "under 21 contradictory business rules.",
                "The export is deliberately messy: mixed date formats, 50 duplicate employees, "
                "37 broken history rows, a biometric clock running 30 minutes slow.",
                "The CFO needs answers it can defend: headcount trend, attrition, overtime "
                "authenticity, and who is being paid for what.",
                "Our job: one pipeline that turns these files into evidence - and proves "
                "the evidence is clean.",
            ],
            "Indus Weave Textiles | Multi-Cloud Data Engineering Hackathon | Apr-Sep 2026",
        ),
        slide(
            "The pipeline: one command, six gated stages",
            ("python run_pipeline.py", "raw -> staging -> attendance -> warehouse -> 10 queries -> 58 DQ checks (~2 min)"),
            [
                "Raw is immutable: files load verbatim (TEXT + hash), then Rules 1-21 repair "
                "them in code - data/ is never edited.",
                "Attendance engine: sessionised punches, device-drift corrected, night shifts "
                "attributed to their start date; OT rounded down to half-hours.",
                "Star schema: 4 slowly-changing dimensions + 4 fact tables, all foreign keys "
                "verified (0 orphans), ERD included.",
                "Quality gate: 58 automated checks (reconciliation, keys, SCD2, domains) written "
                "to dq_results - currently 58 PASS / 0 FAIL, proven to FAIL when seeded bad data.",
            ],
            "Gates R -> S/A -> W -> Q -> D all PASS | 32/32 tests green | SQLite, no server",
        ),
        slide(
            "Finding 1: Stitching pays overtime it cannot see",
            ("+2,758 h", "paid vs punch-computed OT in Stitching = +56% (approx. PKR 1.36 m unsupported)"),
            [
                "Only department over the 15% threshold: paid 7,659 h / PKR 3,771,337 vs "
                "4,901 h justified by punches.",
                "The gap is zero in April and grows every month to +130% in September - "
                "an escalation, not rounding.",
                "Approved hours track PAID hours (7,656), not punch hours: approvals ratify "
                "the payment instead of the work.",
                "Action: block OT posting unless approved hours sit inside punch-derived OT "
                "windows; review May-Sep D20 approvals.",
            ],
            "Evidence: analytics/q06_dept_paid_over_computed_15pct.sql | 1 row out of 25 departments",
        ),
        slide(
            "Finding 2: Pay for people who are never at work",
            ("PKR 2,879,197", "7 employees, 37 employee-months paid with ZERO present days"),
            [
                "Q7 finds 58 employee-months (PKR 4.83 m) paid with zero worked hours; 37 of "
                "them (PKR 2.88 m) are people still on the payroll, not leavers.",
                "Six of the seven were never Present in any of the six months while salary "
                "kept flowing - e.g. E10399: 6 months, PKR 541,125, 0 present days.",
                "Zero Present + zero Absent rows means these employees sit outside the "
                "workforce spine entirely: invisible to HR, visible to payroll.",
                "Action: attendance-to-payroll release gate - no month pays while "
                "worked_hours = 0 exists uncertified.",
            ],
            "Evidence: analytics/q07_paid_zero_attendance.sql | 58 rows | overlaps Finding 3 by 21 months",
        ),
        slide(
            "Finding 3: Payroll keeps paying people who left",
            ("PKR 1,948,000", "5 ex-employees, 21 FULL months paid after their separation date"),
            [
                "Every payroll month that starts after separation_date still pays earnings - "
                "final settlement months excluded, so this is pure overrun.",
                "Worst case: E10471 left 23 Apr, collected PKR 132,000/month for May-Sep "
                "(131 days, PKR 660,000) with zero attendance.",
                "Four of the five left in mid-May yet were paid in the June run too - the "
                "offboarding trigger failed twice, not once.",
                "Action: automatic payroll block where separation_date < month start (the "
                "query IS the predicate) + recoveries through the exit checklist.",
            ],
            "Evidence: analytics/q08_pay_after_separation.sql | 21 rows | months starting after last day worked",
        ),
        slide(
            "The ask",
            None,
            [
                "Approve three automated controls, all already written as queries: "
                "OT-must-match-punches, zero-attendance pay block, post-separation payroll block.",
                "Total exposure identified in ONE six-month window: approx. PKR 6.2 m "
                "(1.36 + 2.88 + 1.95) - findings overlap only where noted.",
                "Run python run_pipeline.py monthly: every number regenerates, every DQ check "
                "re-runs, dq_results is the audit trail.",
                "Deliverables: this deck, cfo_findings.md (3 findings with evidence SQL), "
                "README, ERD, 10 questions, 58 DQ checks, 32 tests.",
            ],
            "Ask: sign off the three controls + a monthly run of this pipeline | Thank you",
        ),
    ]

    png_dir = OUT / "slides"
    png_dir.mkdir(exist_ok=True)
    for i, img in enumerate(slides, 1):
        img.save(png_dir / f"slide-{i:02d}.png")
    pdf = OUT / "slides.pdf"
    slides[0].save(pdf, save_all=True, append_images=slides[1:])
    print(f"wrote {pdf} ({len(slides)} slides) + {png_dir}\\slide-NN.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
