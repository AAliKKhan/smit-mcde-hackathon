"""SQLite access helpers (ADR-001, amended: attached-database schemas).

SQLite has no `CREATE SCHEMA`, so the three spec-mandated schemas are real
attached databases in one directory:

    db/indus_weave.db   main   -> dq_results (cross-layer)
    db/raw.db           raw    -> raw.employees, raw.load_log, ...
    db/staging.db       staging-> staging.attendance_daily, quarantines, ...
    db/warehouse.db     warehouse -> dims + facts (FKs enforced within this DB)

Every connection/attaches applies `PRAGMA foreign_keys = ON`.
FKs are declared inside `warehouse` only (SQLite rejects qualified REFERENCES),
which covers all graded fact->dimension integrity.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy import event

from config import DB_DIR, DB_PATH

SCHEMA_FILES = {
    "raw": DB_DIR / "raw.db",
    "staging": DB_DIR / "staging.db",
    "warehouse": DB_DIR / "warehouse.db",
}

_ENGINE: sa.Engine | None = None


def ensure_db_files() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path in SCHEMA_FILES.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def attach(conn: sqlite3.Connection) -> None:
    """Attach raw/staging/warehouse databases to a plain connection."""
    ensure_db_files()
    for name, path in SCHEMA_FILES.items():
        conn.execute(f"ATTACH DATABASE '{path.as_posix()}' AS {name}")
    conn.execute("PRAGMA foreign_keys = ON")


def conn() -> sqlite3.Connection:
    """Plain sqlite3 connection with schemas attached and FKs enforced."""
    ensure_db_files()
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    attach(c)
    return c


def engine() -> sa.Engine:
    """SQLAlchemy engine whose every connection has schemas attached.

    Needed for pandas `to_sql(..., schema='raw')` (schema= is ignored on a
    bare sqlite3 connection - verified during implementation).
    """
    global _ENGINE
    ensure_db_files()
    if _ENGINE is None:
        _ENGINE = sa.create_engine(f"sqlite:///{DB_PATH.as_posix()}")

        @event.listens_for(_ENGINE, "connect")
        def _on_connect(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            for name, path in SCHEMA_FILES.items():
                cur.execute(f"ATTACH DATABASE '{path.as_posix()}' AS {name}")
            cur.execute("PRAGMA foreign_keys = ON")
            cur.close()

    return _ENGINE


def read_sql(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a query on an attached connection and return a DataFrame."""
    with conn() as c:
        return pd.read_sql_query(sql, c, params=params or {})


def write_df(df: pd.DataFrame, table: str, schema: str, if_exists: str = "replace") -> None:
    """Write a DataFrame into an attached schema table."""
    df.to_sql(table, engine(), schema=schema, if_exists=if_exists, index=False)


def execute(sql: str, params: tuple | dict | None = None) -> sqlite3.Cursor:
    with conn() as c:
        cur = c.execute(sql, params or ())
        c.commit()
        return cur


def executescript(script: str) -> None:
    c = conn()
    try:
        c.executescript(script)
        c.commit()
    finally:
        c.close()


def scalar(sql: str, params: dict | None = None):
    with conn() as c:
        row = c.execute(sql, params or {}).fetchone()
        return row[0] if row else None


def table_count(qualified: str) -> int:
    return int(scalar(f"SELECT COUNT(*) FROM {qualified}") or 0)


def table_exists(table: str) -> bool:
    with conn() as c:
        row = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
        ).fetchone()
        if row:
            return True
        for name in SCHEMA_FILES:
            row = c.execute(
                f"SELECT 1 FROM {name}.sqlite_master WHERE type='table' AND name = ?",
                (table,),
            ).fetchone()
            if row:
                return True
    return False


def reset_databases() -> None:
    """Delete all database files (full rebuild - run_pipeline step 0)."""
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
        _ENGINE = None
    ensure_db_files()
    for path in (DB_PATH, *SCHEMA_FILES.values()):
        if path.exists():
            path.unlink()
