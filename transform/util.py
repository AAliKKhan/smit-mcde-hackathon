"""Shared helpers for Stage 2/3 transforms (T015-T024).

Design notes:
- `replace_rows` = DELETE + parameterized INSERT (idempotent rebuild, Principle IV).
  pandas `to_sql(if_exists='replace')` would DROP and recreate the table from
  DataFrame dtypes, losing DDL CHECK constraints - so we never use it for staging.
- `iso_series` normalizes the three contract date formats (FR-007):
  YYYY-MM-DD, DD/MM/YYYY, DD-Mon-YYYY -> ISO 8601 date text.
"""

from __future__ import annotations

import re
from datetime import datetime

import numpy as np
import pandas as pd

from common import db

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SLASH_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
DMY_RE = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{4})$")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def to_iso_date(value) -> str | None:
    """Normalize one date cell to 'YYYY-MM-DD'; None when empty/unparseable."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "nat", "none"}:
        return None
    if ISO_RE.match(s):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    m = SLASH_RE.match(s)
    if m:
        d, mo, y = m.groups()
        try:
            return datetime(int(y), int(mo), int(d)).date().isoformat()
        except ValueError:
            return None
    m = DMY_RE.match(s)
    if m:
        d, mon, y = m.groups()
        mo = _MONTHS.get(mon.lower())
        if mo:
            try:
                return datetime(int(y), mo, int(d)).date().isoformat()
            except ValueError:
                return None
    return None


def iso_series(values) -> tuple[pd.Series, int]:
    """Vectorize to_iso_date; returns (ISO strings as object Series, failure count)."""
    out = [to_iso_date(v) for v in values]
    failures = sum(
        1
        for v, o in zip(values, out)
        if str(v).strip()
        and str(v).strip().lower() not in {"nan", "nat", "none"}
        and o is None
    )
    return pd.Series(out, dtype=object), failures


def to_float(value) -> float | None:
    """Numeric cell -> float; empty/NaN -> None (payroll units, OT hours...)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    return float(s)


def to_int(value) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    return int(float(s))


def _bindable(df: pd.DataFrame) -> list[tuple]:
    """DataFrame rows as Python scalars sqlite3 can bind (numpy types rejected)."""
    obj = df.astype(object).where(pd.notna(df), None)
    rows = []
    for row in obj.itertuples(index=False, name=None):
        rows.append(tuple(v.item() if isinstance(v, np.generic) else v for v in row))
    return rows


def replace_rows(df: pd.DataFrame, qualified: str) -> int:
    """Idempotent rebuild of `qualified` (e.g. 'staging.employees') from `df`."""
    cols = list(df.columns)
    col_sql = ", ".join(cols)
    ph = ", ".join("?" for _ in cols)
    rows = _bindable(df)
    c = db.conn()
    try:
        c.execute(f"DELETE FROM {qualified}")
        if rows:
            c.executemany(f"INSERT INTO {qualified} ({col_sql}) VALUES ({ph})", rows)
        c.commit()
    finally:
        c.close()
    return len(rows)


def frame(columns: list[str], rows: list[dict]) -> pd.DataFrame:
    """Empty-or-populated DataFrame with fixed column order (stable INSERTs)."""
    return pd.DataFrame(rows, columns=columns)


def print_counts(title: str, counts: dict) -> None:
    print(f"[{title}] " + ", ".join(f"{k}={v:,}" for k, v in counts.items()))
