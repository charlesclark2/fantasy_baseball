"""E11.1-W11-E (serving-coupled ingestion FINISH) — unit tests for the derivative/venues writer
flips + the parlay_api decommission. Offline (no S3/Snowflake — the shared _FakeS3 pattern).

Covers:
  • derivative_odds_backfill._derivative_mirror_rows projects live-capture rows to the exact S3 raw
    schema stg_derivative_odds reads (drops fetch_status, filters null raw_json, passes JSON through);
  • the derivative + venues sources are registered so write_raw_rows_s3 accepts them;
  • a venues-shaped mirror row round-trips through write_raw_rows_s3 (json_field → JSON string,
    ingestion_ts drives a stable dt= partition);
  • the parlay_api decommission is complete: the ingestion script + cold-archive stg models are gone
    and no dbt model/test carries a live parlay ref (a regression here = a broken dbt build).
"""
import importlib
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from utils.lakehouse_raw_writer import RAW_SOURCES, write_raw_rows_s3

_REPO = Path(__file__).resolve().parents[2]


class _FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, Bucket, Key, Body):
        self.puts.append((Key, Body))

    def get_paginator(self, _):
        class P:
            def paginate(self, **kw):
                return iter([{}])
        return P()


# ── derivative live-writer flip ──────────────────────────────────────────────

def test_derivative_and_venues_sources_registered():
    for src in ("derivative_odds_raw", "venues_raw"):
        assert src in RAW_SOURCES, f"{src} missing from RAW_SOURCES → write_raw_rows_s3 would reject it"


def test_derivative_mirror_rows_projects_to_stg_schema():
    """_derivative_mirror_rows must (1) keep exactly the columns stg_derivative_odds reads, (2) DROP
    fetch_status (the bridge doesn't emit it), (3) filter rows with null raw_json (failed captures)."""
    mod = importlib.import_module("derivative_odds_backfill")
    rows = [
        {  # a successful capture row (raw_json present)
            "ingestion_ts": "2026-07-03T18:00:00Z", "load_id": "L1", "event_id": "E1",
            "requested_snapshot_ts": "2026-07-03T18:00:00Z", "actual_snapshot_ts": "2026-07-03T18:00:00Z",
            "previous_snapshot_ts": None, "next_snapshot_ts": None,
            "markets_requested": "team_totals", "regions_requested": "us",
            "x_requests_remaining": "500", "x_requests_last": "10",
            "raw_json": '{"id": "E1", "bookmakers": []}', "fetch_status": "success",
        },
        {  # a FAILED capture (raw_json None) — must be filtered out of the S3 mirror
            "ingestion_ts": "2026-07-03T18:00:00Z", "load_id": "L1", "event_id": "E2",
            "requested_snapshot_ts": "2026-07-03T18:00:00Z", "actual_snapshot_ts": "2026-07-03T18:00:00Z",
            "previous_snapshot_ts": None, "next_snapshot_ts": None,
            "markets_requested": "team_totals", "regions_requested": "us",
            "x_requests_remaining": "499", "x_requests_last": "0",
            "raw_json": None, "fetch_status": "not_found",
        },
    ]
    out = mod._derivative_mirror_rows(rows)
    assert len(out) == 1, "failed (null raw_json) rows must be filtered from the mirror"
    assert set(out[0].keys()) == set(mod._DERIVATIVE_S3_COLS)
    assert "fetch_status" not in out[0], "fetch_status must be dropped (bridge parity)"
    assert out[0]["event_id"] == "E1"
    assert out[0]["raw_json"] == '{"id": "E1", "bookmakers": []}'  # JSON string passthrough


def test_derivative_mirror_round_trips_through_write_raw_rows_s3(tmp_path):
    """The projected rows must write a real parquet DuckDB can read, partitioned by ingestion_ts date
    — the exact read-path stg_derivative_odds' duckdb branch globs."""
    mod = importlib.import_module("derivative_odds_backfill")
    rows = mod._derivative_mirror_rows([{
        "ingestion_ts": "2026-07-03T18:00:00Z", "load_id": "L1", "event_id": "E1",
        "requested_snapshot_ts": "2026-07-03T18:00:00Z", "actual_snapshot_ts": "2026-07-03T18:00:00Z",
        "previous_snapshot_ts": None, "next_snapshot_ts": None,
        "markets_requested": "team_totals", "regions_requested": "us",
        "x_requests_remaining": "500", "x_requests_last": "10",
        "raw_json": '{"id": "E1", "bookmakers": [{"key": "bovada"}]}', "fetch_status": "success",
    }])
    fake = _FakeS3()
    n = write_raw_rows_s3("derivative_odds_raw", rows, mode="append", s3_client=fake)
    assert n == 1 and len(fake.puts) == 1
    key, body = fake.puts[0]
    assert "lakehouse_raw/derivative_odds_raw/dt=2026-07-03/" in key
    out = tmp_path / "part.parquet"
    out.write_bytes(body)
    con = duckdb.connect()
    row = con.execute(
        f"select event_id, json_extract_string(raw_json, '$.id') as id "
        f"from read_parquet('{out}')"
    ).fetchone()
    assert row == ("E1", "E1")


# ── venues writer flip ───────────────────────────────────────────────────────

def test_venues_mirror_row_round_trips(tmp_path):
    """The venues mirror row (venue_id / ingest_date / ingestion_ts / json_field dict) must write a
    parquet whose json_field is a JSON string (dict serialized) and partition on the stable ingest_date."""
    rows = [{
        "venue_id": 15, "ingest_date": "2026-07-03", "ingestion_ts": "2026-07-03",
        "json_field": {"id": 15, "name": "Dodger Stadium"},
    }]
    fake = _FakeS3()
    n = write_raw_rows_s3("venues_raw", rows, mode="append", s3_client=fake)
    assert n == 1
    key, body = fake.puts[0]
    assert "lakehouse_raw/venues_raw/dt=2026-07-03/" in key
    out = tmp_path / "v.parquet"
    out.write_bytes(body)
    con = duckdb.connect()
    row = con.execute(
        f"select venue_id, json_extract_string(json_field, '$.name') as name "
        f"from read_parquet('{out}')"
    ).fetchone()
    assert row == (15, "Dodger Stadium")


# ── parlay_api decommission invariants ───────────────────────────────────────

def test_parlay_ingestion_and_stg_models_removed():
    assert not (_REPO / "scripts" / "parlay_api_ingestion.py").exists(), \
        "parlay_api_ingestion.py must be deleted (Parlay platform decommissioned)"
    for m in ("stg_parlayapi_odds", "stg_parlayapi_line_movement", "stg_parlayapi_canonical_events"):
        assert not (_REPO / "dbt" / "models" / "staging" / f"{m}.sql").exists(), \
            f"cold-archive {m}.sql must be removed"


def test_no_live_parlay_ref_in_dbt():
    """A live {{ ref('stg_parlayapi_*') }} or {{ source('parlayapi', ...) }} anywhere would break the
    dbt build once the operator DROPs baseball_data.parlayapi.* — guard against reintroduction."""
    offenders = []
    for sql in (_REPO / "dbt" / "models").rglob("*.sql"):
        text = sql.read_text()
        if "ref('stg_parlayapi" in text or 'ref("stg_parlayapi' in text \
                or "source('parlayapi'" in text or 'source("parlayapi"' in text:
            offenders.append(sql.relative_to(_REPO).as_posix())
    # dbt tests dir too
    for sql in (_REPO / "dbt" / "tests").rglob("*.sql"):
        text = sql.read_text()
        if "ref('stg_parlayapi" in text or "source('parlayapi'" in text:
            offenders.append(sql.relative_to(_REPO).as_posix())
    assert not offenders, f"live parlay refs remain (will break dbt build after SF DROP): {offenders}"
