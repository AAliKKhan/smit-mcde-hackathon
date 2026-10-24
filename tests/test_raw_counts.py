"""Gate R tests (T014): raw counts match contract, load metadata present,
and a second load is idempotent (SC-001 / FR-002..004).

Run: python -m pytest tests/test_raw_counts.py -v
"""

from __future__ import annotations

import pytest

from common import db
from config import EXPECTED_COUNTS
from ingestion import counts as counts_mod
from ingestion import load_raw


@pytest.fixture(scope="module")
def raw_loaded() -> None:
    """Ensure raw is loaded exactly once for this module."""
    existing = {t for t in EXPECTED_COUNTS if db.table_count(f"raw.{t}") > 0}
    if existing != set(EXPECTED_COUNTS):
        load_raw.load_all(verbose=False)


def test_all_expected_counts(raw_loaded) -> None:
    rows = counts_mod.check()
    bad = [r for r in rows if not r["count_ok"]]
    assert not bad, f"raw count mismatches: {bad}"


def test_load_metadata_present(raw_loaded) -> None:
    rows = counts_mod.check()
    bad = [r for r in rows if not r["meta_ok"]]
    assert not bad, f"null _source_file/_loaded_at/_row_hash rows: {bad}"


def test_idempotent_reload(raw_loaded) -> None:
    before = {t: db.table_count(f"raw.{t}") for t in EXPECTED_COUNTS}
    load_raw.load_all(verbose=False)
    after = {t: db.table_count(f"raw.{t}") for t in EXPECTED_COUNTS}
    assert before == after, f"reload changed counts: {before} -> {after}"


def test_all_columns_are_text(raw_loaded) -> None:
    """FR-001: raw columns are TEXT (SQLite affinity check on every raw table)."""
    offenders: list[str] = []
    with db.conn() as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM raw.sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'load_log'"
            )
        ]
        assert len(tables) == len(EXPECTED_COUNTS), f"raw tables found: {tables}"
        for table in tables:
            for col in conn.execute(f"PRAGMA raw.table_info({table})"):
                if col["type"].upper() != "TEXT":
                    offenders.append(f"{table}.{col['name']}:{col['type']}")
    assert not offenders, f"non-TEXT raw columns: {offenders}"
