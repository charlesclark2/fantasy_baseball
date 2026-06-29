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
    list_partition_dts,
    prune_partitions,
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


def test_explicit_null_ingestion_ts_is_preserved_not_stamped():
    """Historical-backfill rows carry an EXPLICIT NULL ingestion_ts (key present, value None).
    It must survive as NULL (matches Snowflake) — NOT be stamped now() like a key-ABSENT live
    row — else the value mismatches and the staging 'order by ingestion_ts desc nulls last'
    dedup picks the wrong row (silent data loss)."""
    rows = [{"ingestion_ts": None, "json_field": {"dates": []}}]
    d = rows_to_arrow_table(rows).to_pydict()
    assert d["ingestion_ts"][0] is None
    # key ABSENT still stamps (live-writer DEFAULT CURRENT_TIMESTAMP semantics).
    d2 = rows_to_arrow_table([{"json_field": {"dates": []}}]).to_pydict()
    assert d2["ingestion_ts"][0]


def test_all_null_ingestion_ts_batch_stays_utf8_typed():
    """An all-NULL batch (a __nullts__ partition) must NOT infer arrow 'null' type, or its
    parquet drifts from the utf8 ingestion_ts of dated partitions under the union_by_name glob."""
    import pyarrow as pa
    rows = [{"ingestion_ts": None, "json_field": {"a": 1}},
            {"ingestion_ts": None, "json_field": {"a": 2}}]
    assert rows_to_arrow_table(rows).schema.field("ingestion_ts").type == pa.string()


def test_null_ingestion_ts_routes_to_sentinel_partition():
    puts = []

    class FakeS3:
        def put_object(self, Bucket, Key, Body):
            puts.append(Key)

        def get_paginator(self, _):
            class P:
                def paginate(self, **kw):
                    return iter([{}])
            return P()

    rows = [{"ingestion_ts": None, "json_field": {"dates": []}}]
    n = write_raw_rows_s3("monthly_schedule", rows, mode="overwrite_partition", s3_client=FakeS3())
    assert n == 1
    assert any("dt=__nullts__/" in k for k in puts)


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


# ── E11.1-W6 / INC-20: monthly_schedule retention ──────────────────────────────
def test_latest_dt_per_month_keeps_one_latest_per_calendar_month():
    """The retention rule: collapse accumulating daily snapshots to the latest ingestion per
    (year, month) — value-identical under the flatten's latest-ingestion-per-game_pk dedup."""
    from datetime import date

    from export_odds_raw_to_s3 import latest_dt_per_month

    dates = [
        date(2026, 5, 12), date(2026, 5, 20), date(2026, 5, 31),   # May → keep 05-31
        date(2026, 6, 1), date(2026, 6, 15), date(2026, 6, 28),    # Jun → keep 06-28
        date(2026, 4, 30),                                          # Apr → keep 04-30 (only one)
    ]
    assert latest_dt_per_month(dates) == [date(2026, 4, 30), date(2026, 5, 31), date(2026, 6, 28)]
    assert latest_dt_per_month([]) == []


class _FakeS3Partitions:
    """Fake S3 supporting list_objects_v2 pagination + delete_object, for prune tests."""

    def __init__(self, keys):
        self._keys = list(keys)
        self.deleted = []

    def get_paginator(self, _op):
        outer = self

        class P:
            def paginate(self, Bucket, Prefix):
                contents = [{"Key": k} for k in outer._keys if k.startswith(Prefix)]
                return iter([{"Contents": contents}])

        return P()

    def delete_object(self, Bucket, Key):
        self.deleted.append(Key)
        self._keys.remove(Key)


def test_list_partition_dts_parses_dt_keys():
    keys = [
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-05-31/part-a.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-06-28/part-b.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=__nullts__/part-c.parquet",
    ]
    assert list_partition_dts(_FakeS3Partitions(keys), "monthly_schedule") == [
        "2026-05-31", "2026-06-28", "__nullts__",
    ]


def test_prune_partitions_keeps_keepset_and_nullts_deletes_rest():
    keys = [
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-05-12/part-a.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-05-31/part-b.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-06-15/part-c.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=2026-06-28/part-d.parquet",
        "baseball/lakehouse_raw/monthly_schedule/dt=__nullts__/part-e.parquet",
    ]
    fake = _FakeS3Partitions(keys)
    deleted = prune_partitions("monthly_schedule", ["2026-05-31", "2026-06-28"], s3_client=fake)
    # redundant same-month snapshots gone; latest-per-month + __nullts__ retained.
    assert deleted == ["2026-05-12", "2026-06-15"]
    assert "baseball/lakehouse_raw/monthly_schedule/dt=__nullts__/part-e.parquet" in fake._keys
    assert "baseball/lakehouse_raw/monthly_schedule/dt=2026-05-31/part-b.parquet" in fake._keys


def test_prune_partitions_rejects_unknown_source():
    with pytest.raises(ValueError, match="Unknown raw source"):
        prune_partitions("not_a_source", ["2026-06-28"], s3_client=_FakeS3Partitions([]))
