"""E11.1-W3pre — unit tests for the shared S3 raw-writer keystone.

Verifies (offline, no S3/Snowflake) that rows_to_arrow_table produces a parquet whose
raw_json VARCHAR column the dbt staging duckdb branches can flatten with the locked
DuckDB JSON idiom — i.e. the writer output and the stg read are byte-compatible.
"""
import json

import duckdb
import pyarrow.parquet as pq
import pytest

from utils.lakehouse_raw_writer import (
    RAW_SOURCES,
    append_raw_rows_lakehouse,
    raw_lakehouse_loc,
    rows_to_arrow_table,
    write_raw_rows_s3,
)

_ODDS_JSON = {
    "id": "evt1", "home_team": "Los Angeles Angels", "away_team": "Athletics",
    "commence_time": "2026-06-27T01:39:00Z",
    "bookmakers": [
        {"key": "fanduel", "title": "FanDuel", "last_update": "2026-06-25T23:02:19Z",
         "markets": [{"key": "h2h", "last_update": "2026-06-25T23:02:19Z",
                      "outcomes": [{"name": "Athletics", "price": -118},
                                   {"name": "Los Angeles Angels", "price": 100}]}]},
    ],
}


def test_raw_lakehouse_loc():
    assert raw_lakehouse_loc("mlb_odds_raw") == (
        "s3://baseball-betting-ml-artifacts/baseball/lakehouse_raw/mlb_odds_raw/"
    )


def test_rows_to_arrow_table_serialises_json_and_stamps_ts():
    rows = [{"load_id": "L1", "x_requests_used": 5, "raw_json": _ODDS_JSON}]
    tbl = rows_to_arrow_table(rows)
    d = tbl.to_pydict()
    # raw_json is a JSON STRING (not a struct), x_requests_used stays numeric, ts stamped.
    assert isinstance(d["raw_json"][0], str)
    assert json.loads(d["raw_json"][0])["id"] == "evt1"
    assert d["x_requests_used"][0] == 5
    assert "ingestion_ts" in d and d["ingestion_ts"][0]


def test_ingestion_ts_preserved_when_present():
    rows = [{"ingestion_ts": "2026-05-11T16:31:37", "load_id": "L1", "raw_json": _ODDS_JSON}]
    d = rows_to_arrow_table(rows).to_pydict()
    assert d["ingestion_ts"][0] == "2026-05-11T16:31:37"


def test_parquet_roundtrips_through_duckdb_triple_flatten(tmp_path):
    """The end-to-end contract: writer parquet → DuckDB flatten → correct outcome rows."""
    rows = [{"ingestion_ts": "2026-06-25T23:02:00", "load_id": "L1", "raw_json": _ODDS_JSON}]
    pq.write_table(rows_to_arrow_table(rows), str(tmp_path / "part-0.parquet"))

    con = duckdb.connect()
    out = con.execute(f"""
        with src as (select raw_json from read_parquet('{tmp_path}/*.parquet')),
        bk as (
            select json_extract_string(raw_json, '$.id') as event_id,
                   unnest(from_json(json_extract(raw_json, '$.bookmakers'), '["JSON"]')) as bookmaker
            from src
        ),
        mk as (
            select event_id, json_extract_string(bookmaker, '$.key') as bookmaker_key,
                   unnest(from_json(json_extract(bookmaker, '$.markets'), '["JSON"]')) as market
            from bk
        ),
        oc as (
            select event_id, bookmaker_key, json_extract_string(market, '$.key') as market_key,
                   unnest(from_json(json_extract(market, '$.outcomes'), '["JSON"]')) as outcome
            from mk
        )
        select event_id, bookmaker_key, market_key,
               json_extract_string(outcome, '$.name') as outcome_name,
               json_extract(outcome, '$.price')::integer as price
        from oc order by price
    """).fetchall()
    assert out == [
        ("evt1", "fanduel", "h2h", "Athletics", -118),
        ("evt1", "fanduel", "h2h", "Los Angeles Angels", 100),
    ]


def test_write_raw_rows_s3_rejects_unknown_source():
    with pytest.raises(ValueError, match="Unknown raw source"):
        write_raw_rows_s3("not_a_source", [{"raw_json": {}}])


def test_write_raw_rows_s3_partitions_by_date_and_appends(monkeypatch):
    """mode='append' writes one part per dt= partition with a unique key; no overwrite."""
    puts, deletes = [], []

    class FakeS3:
        def put_object(self, Bucket, Key, Body):
            puts.append(Key)

        def get_paginator(self, _):
            class P:
                def paginate(self, **kw):
                    deletes.append(kw.get("Prefix"))
                    return iter([{}])
            return P()

    rows = [
        {"ingestion_ts": "2026-06-25T10:00:00", "load_id": "A", "raw_json": _ODDS_JSON},
        {"ingestion_ts": "2026-06-26T10:00:00", "load_id": "B", "raw_json": _ODDS_JSON},
    ]
    n = write_raw_rows_s3("mlb_odds_raw", rows, mode="append", s3_client=FakeS3())
    assert n == 2
    assert len(puts) == 2  # one part per distinct dt= partition
    assert any("dt=2026-06-25/" in k for k in puts)
    assert any("dt=2026-06-26/" in k for k in puts)
    assert deletes == []  # append mode never deletes


def test_dispatcher_default_mode_is_non_breaking(monkeypatch):
    """Default (no env, no conn) resolves to 'snowflake' and refuses without a conn —
    i.e. importing the module changes nothing until a writer opts in."""
    monkeypatch.delenv("LAKEHOUSE_RAW_WRITE_MODE", raising=False)
    with pytest.raises(ValueError, match="needs a Snowflake conn"):
        append_raw_rows_lakehouse("db.sc.t", "mlb_odds_raw", [{"raw_json": {}}], conn=None)


def test_dispatcher_s3_mode_skips_snowflake(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "utils.lakehouse_raw_writer.write_raw_rows_s3",
        lambda source, rows, mode="append": captured.update(source=source, n=len(rows)) or len(rows),
    )
    n = append_raw_rows_lakehouse("db.sc.t", "mlb_odds_raw", [{"raw_json": {}}], conn=None, mode="s3")
    assert n == 1 and captured["source"] == "mlb_odds_raw"


def test_all_raw_sources_have_valid_locs():
    for s in RAW_SOURCES:
        assert raw_lakehouse_loc(s).startswith("s3://")
