"""Bonus test: incremental load appends only new rows, and is idempotent.

Uses a scratch table in schema `raw` so the real raw tables (and Gate R
counts) are untouched: create -> re-run (0 new) -> bigger file (delta only)
-> cleanup.
"""

from __future__ import annotations

import pandas as pd
import pytest

from common import db
from ingestion.load_incremental import incremental_load

TABLE = "incr_demo"


def _csv(tmp_path, name: str, rows: list[tuple[str, str]]) -> str:
    p = tmp_path / name
    pd.DataFrame(rows, columns=["id", "value"]).to_csv(p, index=False)
    return str(p)


@pytest.fixture()
def scratch_table():
    yield
    db.executescript(f'DROP TABLE IF EXISTS raw."{TABLE}"')


def test_incremental_appends_only_new_rows(tmp_path, scratch_table):
    db.executescript(f'DROP TABLE IF EXISTS raw."{TABLE}"')

    f1 = _csv(tmp_path, "batch1.csv", [("R1", "a"), ("R2", "b"), ("R3", "c")])

    # first load: table created, all rows appended
    r = incremental_load(f1, TABLE, "id")
    assert r["rows_read"] == 3 and r["rows_new"] == 3 and r["rows_total"] == 3

    # same file again: nothing new (FR-003 idempotent)
    r = incremental_load(f1, TABLE, "id")
    assert r["rows_new"] == 0 and r["rows_total"] == 3

    # "seventh month arrives": file with old rows + two new ones
    f2 = _csv(tmp_path, "batch2.csv",
              [("R1", "a"), ("R2", "b"), ("R3", "c"), ("R4", "d"), ("R5", "e")])
    r = incremental_load(f2, TABLE, "id")
    assert r["rows_read"] == 5 and r["rows_new"] == 2 and r["rows_total"] == 5

    # keys unique and metadata present (FR-002); each row keeps the file it
    # arrived in - earlier rows are never rewritten
    df = db.read_sql(f'SELECT "id", _source_file, _row_hash FROM raw."{TABLE}" ORDER BY "id"')
    assert df["id"].is_unique
    assert (df["_source_file"] == "batch1.csv").sum() == 3
    assert (df["_source_file"] == "batch2.csv").sum() == 2
    assert df["_row_hash"].str.len().eq(64).all()

    # duplicates inside one file are collapsed before append
    f3 = _csv(tmp_path, "batch3.csv", [("R6", "f"), ("R6", "f"), ("R7", "g")])
    r = incremental_load(f3, TABLE, "id")
    assert r["rows_new"] == 2 and r["dupes_in_file"] == 1 and r["rows_total"] == 7
