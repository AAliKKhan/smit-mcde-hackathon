"""Project-wide paths, windows and contracts (single source of truth).

Rule references: data/data_dictionary.md. Nothing here mutates data/ (Principle II).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_DIR = ROOT / "db"
DB_PATH = DB_DIR / "indus_weave.db"
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

DDL_DIR = ROOT / "warehouse" / "ddl"
ANALYTICS_DIR = ROOT / "analytics"
RESULTS_DIR = ANALYTICS_DIR / "results"
DOCS_DIR = ROOT / "docs"

# ---------------------------------------------------------------- time window
# Dataset pack covers 1 April - 30 September 2026 (case study).
WINDOW_START = date(2026, 4, 1)
WINDOW_END = date(2026, 9, 30)
# dim_date extends into October: 1 Oct holds check-outs of 30 Sep night shifts,
# and shift_roster contains planned October weeks.
DIM_DATE_END = date(2026, 10, 31)

# ---------------------------------------------------------------- raw file registry
# name -> (raw table, format). Row counts = case study delivery numbers (Gate R).
RAW_FILES: dict[str, tuple[str, str]] = {
    "employees.csv": ("employees", "csv"),
    "employment_history.csv": ("employment_history", "csv"),
    "departments.csv": ("departments", "csv"),
    "shifts.json": ("shifts", "json"),
    "shift_roster.csv": ("shift_roster", "csv"),
    "device_mapping.csv": ("device_mapping", "csv"),
    "biometric_punches.csv": ("biometric_punches", "csv"),
    "holidays.csv": ("holidays", "csv"),
    "leave_requests.json": ("leave_requests", "json"),
    "overtime_requests.csv": ("overtime_requests", "csv"),
    "payroll_lines.csv": ("payroll_lines", "csv"),
    "applications.csv": ("applications", "csv"),
}

EXPECTED_COUNTS: dict[str, int] = {
    "employees": 1316,
    "employment_history": 3686,
    "departments": 25,
    "shifts": 4,
    "shift_roster": 36402,
    "device_mapping": 1260,
    "biometric_punches": 345280,
    "holidays": 12,
    "leave_requests": 5372,
    "overtime_requests": 22098,
    "payroll_lines": 53617,
    "applications": 3835,
}

# Raw tables that hold an approvals array inside a nested JSON document.
# They are stored as-is (one row per top-level record, JSON text column) in Stage 1;
# semantic flattening happens in Stage 2 (contracts/leave_requests.contract.md).
JSON_AS_TEXT_TABLES = {"shifts", "leave_requests"}

# ---------------------------------------------------------------- value domains (Rule 12 / contracts)
ATTENDANCE_STATUSES = (
    "Present",
    "Absent",
    "On Leave",
    "Holiday",
    "Weekly Off",
    "Missing Punch",
)
LEAVE_TYPES: tuple[str, ...] = ()  # populated from profiling (see docs/profile_notes.md)
PAY_COMPONENTS = (
    "BASIC",
    "HOUSE_RENT",
    "MEDICAL",
    "CONVEYANCE",
    "OVERTIME",
    "INCOME_TAX",
    "EOBI",
    "ABSENCE_DEDUCTION",
    "LOAN_INSTALLMENT",
)
COMPONENT_TYPES = ("EARNING", "DEDUCTION")
PLANTS = ("Head Office", "Korangi Plant", "SITE Plant", "Faisalabad Plant")
HOLIDAY_SCOPES = ("ALL", "HO", "KOR", "SITE", "FSD")
SHIFT_CODES = ("DAY", "EVE", "NIGHT", "GEN")

# Plant code used by holidays.scope / device_id prefixes.
PLANT_CODE = {
    "Head Office": "HO",
    "Korangi Plant": "KOR",
    "SITE Plant": "SITE",
    "Faisalabad Plant": "FSD",
}

# Night shift starts 22:00; attribution is session-based (ADR-002 step 2), not a
# fixed clock offset - a session dated by its first punch covers the crossing.
# Used for shift-date attribution (Rule 7, research R5).
NIGHT_SHIFT = {"code": "NIGHT", "start": "22:00", "end": "06:00", "crosses_midnight": True}

# ---------------------------------------------------------------- runtime knobs
MIN_GAP_MINUTES = 2          # Rule 9: two punches within 2 minutes count as one
SESSION_GAP_HOURS = 12.5     # Rule 7: max gap inside one shift session
                             # (within-shift max observed 12.21h = GEN 08:46-20:58
                             #  OT day; between-shift breaks are >= 11.68h but are
                             #  caught by the MAX_SHIFT_HOURS session-span cap)
GRACE_MINUTES = 10           # Rule 13: lateness / early-departure threshold
OT_ROUND_MINUTES = 30        # Rule 14/15: floor to whole half-hours
MAX_SHIFT_HOURS = 16         # sanity check (FR-024 / FR-050)


def ensure_dirs() -> None:
    """Create runtime directories (idempotent)."""
    for path in (DB_DIR, RESULTS_DIR, DOCS_DIR):
        path.mkdir(parents=True, exist_ok=True)
