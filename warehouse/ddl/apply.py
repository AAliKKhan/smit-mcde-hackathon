"""Apply all DDL files in order (T006). Idempotent: every statement is
CREATE ... IF NOT EXISTS. Requires common/db.py attaches (raw/staging/warehouse).

Usage: python -m warehouse.ddl.apply [--after-load]
  (no flag)  -> 00_schemas, 10_staging, 20_warehouse
  --after-load -> adds 30_indexes (staging/warehouse gaps; raw indexes come
                  from ingestion/load_raw.py which rebuilds raw tables)
"""

from __future__ import annotations

import sys
from pathlib import Path

from common import db

DDL_DIR = Path(__file__).resolve().parent
BASE_FILES = ["00_schemas.sql", "10_staging.sql", "20_warehouse.sql"]
AFTER_LOAD_FILES = ["30_indexes.sql"]


def apply(files: list[str] | None = None) -> None:
    targets = files or BASE_FILES
    conn = db.conn()
    try:
        for name in targets:
            script = (DDL_DIR / name).read_text(encoding="utf-8")
            conn.executescript(script)
            print(f"  ddl: {name} applied")
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    if "--after-load" in sys.argv:
        apply(AFTER_LOAD_FILES)
    else:
        apply()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
