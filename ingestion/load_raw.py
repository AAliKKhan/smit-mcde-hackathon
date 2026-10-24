"""Stage 1: load raw HCM exports into schema `raw` exactly as delivered (T010-T012).

Rules enforced here:
  - FR-001: every column stored as TEXT, values untouched (no trimming/case/date fixes)
  - FR-002: `_source_file`, `_loaded_at`, `_row_hash` (sha256 over ordered field values)
  - FR-003: idempotent - deterministic rebuild (DROP + CREATE via if_exists='replace')
  - FR-004: row counts logged per file/table; verified by ingestion.counts
  - Raw is Immutable: this module never writes to data/, only reads it

JSON handling: one row per top-level document (shifts: 4 rows; leave: 5,372 rows);
nested objects/arrays are stored as JSON text columns - semantic flattening is Stage 2.

Usage: python -m ingestion.load_raw
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import DATA_DIR, EXPECTED_COUNTS, RAW_FILES
from common import db

META_COLS = ["_source_file", "_loaded_at", "_row_hash"]


def _hash_row(values: tuple) -> str:
    """sha256 over '|'.join(field values) - stable identity of a raw row (FR-002)."""
    payload = "|".join("" if v is None else str(v) for v in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_csv_raw(path: Path) -> pd.DataFrame:
    """All columns as TEXT; empty strings preserved (no NA coercion)."""
    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        encoding="utf-8-sig",
    )


def read_json_raw(path: Path) -> pd.DataFrame:
    """One row per top-level document; nested values kept as JSON text (no flattening)."""
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        # shifts.json -> {"shifts": [ ... ]}
        payload = next(v for v in payload.values() if isinstance(v, list))
    rows = []
    for doc in payload:
        row = {}
        for key, value in doc.items():
            if value is None:
                row[key] = ""
            elif isinstance(value, str):
                row[key] = value
            elif isinstance(value, (dict, list)):
                row[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            else:
                row[key] = json.dumps(value)  # numbers/bools keep JSON spelling
        rows.append(row)
    return pd.DataFrame(rows)


def _with_metadata(df: pd.DataFrame, source_file: str, loaded_at: str) -> pd.DataFrame:
    out = df.copy()
    out["_source_file"] = source_file
    out["_loaded_at"] = loaded_at
    out["_row_hash"] = [_hash_row(v) for v in out.itertuples(index=False, name=None)]
    return out[[*df.columns, *META_COLS]]


def load_all(verbose: bool = True) -> dict[str, int]:
    """Load every registered file into raw.<table>. Returns {table: rows}."""
    db.ensure_db_files()
    loaded_at = datetime.now().isoformat(timespec="seconds")
    counts: dict[str, int] = {}
    log_rows: list[dict] = []

    # load_log survives rebuilds of the data tables
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS raw.load_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_file TEXT NOT NULL,
          target_table TEXT NOT NULL,
          rows_read INTEGER NOT NULL,
          rows_written INTEGER NOT NULL,
          status TEXT NOT NULL,
          started_at TEXT NOT NULL,
          finished_at TEXT NOT NULL
        );
        """
    )

    for fname, (table, kind) in RAW_FILES.items():
        path = DATA_DIR / fname
        if not path.exists():
            raise FileNotFoundError(f"missing raw file: {path} (Principle II: never regenerate data/)")
        started = datetime.now().isoformat(timespec="seconds")

        df = read_json_raw(path) if kind == "json" else read_csv_raw(path)
        rows_read = len(df)
        df = _with_metadata(df, fname, loaded_at)

        # deterministic rebuild -> idempotent (FR-003)
        db.write_df(df, table, schema="raw", if_exists="replace")

        rows_written = db.table_count(f"raw.{table}")
        counts[table] = rows_written
        status = "OK" if rows_written == rows_read else "MISMATCH"
        finished = datetime.now().isoformat(timespec="seconds")

        log_rows.append(
            {
                "source_file": fname,
                "target_table": table,
                "rows_read": rows_read,
                "rows_written": rows_written,
                "status": status,
                "started_at": started,
                "finished_at": finished,
            }
        )
        if verbose:
            exp = EXPECTED_COUNTS.get(table, "?")
            mark = "=" if rows_written == exp else "!="
            print(f"  raw.{table:<22} {rows_read:>7} rows (expected {exp}) {mark}")

    # raw indexes (raw tables are rebuilt each run, so create them post-load).
    # SQLite rule: CREATE INDEX <schema>.<ix> ON <table> - qualified index,
    # unqualified table (verified during implementation).
    db.executescript(
        """
        CREATE INDEX IF NOT EXISTS raw.ix_emp_updated
          ON employees(emp_id, updated_at);
        CREATE INDEX IF NOT EXISTS raw.ix_punch_device
          ON biometric_punches(device_id, device_user_id);
        CREATE INDEX IF NOT EXISTS raw.ix_punch_time
          ON biometric_punches(punch_time);
        CREATE INDEX IF NOT EXISTS raw.ix_payroll_emp
          ON payroll_lines(emp_id, payroll_month);
        CREATE INDEX IF NOT EXISTS raw.ix_ot_emp
          ON overtime_requests(emp_id, ot_date);
        """
    )

    # write load log
    log = pd.DataFrame(log_rows)
    db.write_df(log, "load_log", schema="raw", if_exists="append")
    bad = log[log["status"] != "OK"]
    if len(bad):
        raise RuntimeError(f"row-count mismatches inside load: {bad.to_dict('records')}")
    return counts


def main() -> int:
    print(f"[stage 1] loading raw exports from {DATA_DIR}")
    counts = load_all()
    total = sum(counts.values())
    print(f"[stage 1] done: {len(counts)} tables, {total:,} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
