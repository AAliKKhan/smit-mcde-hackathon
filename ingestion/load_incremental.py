"""Bonus: incremental raw load - append only rows not yet present.

Guide bonus task: "Incremental load: a seventh month of punches arrives
mid-hackathon; load only the new data."

The Stage-1 full load (`ingestion.load_raw`) rebuilds every table from
scratch; this module is the delta path. Given a newer export of one table
it:

  1. reads the file exactly as delivered - all columns TEXT, meta columns
     `_source_file` / `_loaded_at` / `_row_hash` added the same way as the
     full load (FR-001/002, Raw is Immutable: reads only),
  2. skips every row whose key already exists in `raw.<table>` (so a
     re-run of the same file appends 0 rows - FR-003 idempotent),
  3. de-duplicates inside the file itself on the key,
  4. appends the rest and logs the counts.

Usage:
  python -m ingestion.load_incremental                 # default: re-check
      # data/biometric_punches.csv against raw.biometric_punches (0 new)
  python -m ingestion.load_incremental --file oct.csv \\
      --table biometric_punches --key punch_id
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from common import db
from config import DATA_DIR
from ingestion.load_raw import _with_metadata, read_csv_raw, read_json_raw

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def incremental_load(file: str | Path, table: str, key: str) -> dict:
    """Append rows from `file` to `raw.<table>` that are not in it yet."""
    if not (_IDENT.match(table) and _IDENT.match(key)):
        raise ValueError(f"unsafe identifier: {table!r}/{key!r}")
    path = Path(file)
    if not path.exists():
        raise FileNotFoundError(f"missing incremental file: {path}")

    df = read_json_raw(path) if path.suffix.lower() == ".json" else read_csv_raw(path)
    if key not in df.columns:
        raise KeyError(f"key {key!r} not in {path.name}: {list(df.columns)}")
    rows_read = len(df)

    loaded_at = datetime.now().isoformat(timespec="seconds")
    df = _with_metadata(df, path.name, loaded_at)

    # keys already in raw (table may not exist yet -> append creates it)
    existing: set[str] = set()
    if db.table_exists(table):
        have = db.read_sql(f'SELECT "{key}" AS k FROM raw."{table}"')
        existing = set(have["k"].astype(str))

    before = len(df)
    df = df.drop_duplicates(subset=[key], keep="first")
    dupes_in_file = before - len(df)
    new = df[~df[key].astype(str).isin(existing)]
    rows_new = len(new)

    if rows_new:
        db.write_df(new, table, schema="raw", if_exists="append")

    rows_total = db.table_count(f"raw.{table}") if db.table_exists(table) else rows_new
    result = {
        "table": table,
        "rows_read": rows_read,
        "rows_new": rows_new,
        "rows_total": rows_total,
        "dupes_in_file": dupes_in_file,
        "already_present": rows_read - rows_new - dupes_in_file,
    }
    print(
        f"[incremental] raw.{table}: read {rows_read:,} | already present "
        f"{result['already_present']:,} | in-file dupes {dupes_in_file} | "
        f"appended {rows_new:,} -> total {rows_total:,}"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--file", default=str(DATA_DIR / "biometric_punches.csv"),
                    help="new export file (default: data/biometric_punches.csv)")
    ap.add_argument("--table", default="biometric_punches", help="raw target table")
    ap.add_argument("--key", default="punch_id", help="dedup key column")
    args = ap.parse_args()
    incremental_load(args.file, args.table, args.key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
