"""E11.1-W11 Tier-D (ActionNetwork public-betting ingestion → S3) — unit tests for the writer flip +
the dedicated hourly time-series + the dual-branched dbt models.

Offline (no S3/Snowflake). Verifies:
  • public_betting_raw + public_betting_intraday_series are registered in RAW_SOURCES and in the
    bridge + parity source sets (the raw mirror; the series is S3-only new data);
  • public_betting_mirror_rows() normalizes a parsed row to the full raw column set + stamps
    ingestion_timestamp (the stg dedup key + SCD-2 loaded_at the record dict lacks);
  • public_betting_series_rows() carries an explicit captured_at (the reconstructable trajectory);
  • a normalized row round-trips through write_raw_rows_s3 with scalar columns intact;
  • the writer imports cleanly and targets the shared _LAKEHOUSE_SOURCE / _LAKEHOUSE_SERIES;
  • the 4 public-betting dbt models render a clean DuckDB branch (no unresolved Jinja, no lakehouse_ext
    leak) and the build/refresh/generator model lists agree.
"""
import importlib

import duckdb
import pyarrow.parquet as pq

from utils.lakehouse_raw_writer import (
    PUBLIC_BETTING_RAW_COLS,
    PUBLIC_BETTING_SERIES_COLS,
    RAW_SOURCES,
    public_betting_mirror_rows,
    public_betting_series_rows,
    write_raw_rows_s3,
)

_SOURCE = "public_betting_raw"
_SERIES = "public_betting_intraday_series"

_PARSED = {
    "game_date": "2026-07-01", "an_game_id": "AN1",
    "home_team_abbr": "NYY", "away_team_abbr": "BOS",
    "home_ml_money_pct": 55.0, "away_ml_money_pct": 45.0,
    "home_ml_ticket_pct": 60.0, "away_ml_ticket_pct": 40.0,
    "over_money_pct": 52.0, "under_money_pct": 48.0,
    "over_ticket_pct": 51.0, "under_ticket_pct": 49.0,
    "book_ids_used": "15",
}


def test_public_betting_sources_registered_everywhere():
    assert _SOURCE in RAW_SOURCES and _SERIES in RAW_SOURCES
    bridge = importlib.import_module("export_w11_raw_to_s3")
    parity = importlib.import_module("parity_check_w11")
    # The raw mirror bridges/parities against Snowflake; the series is S3-only new data (no SF table).
    assert _SOURCE in bridge.SOURCES, "export_w11_raw_to_s3 missing public_betting_raw"
    assert _SOURCE in parity.SOURCES, "parity_check_w11 missing public_betting_raw"
    assert _SERIES not in bridge.SOURCES, "series is S3-only — must NOT have a Snowflake export bridge"


def test_mirror_rows_normalize_and_stamp_ingestion_timestamp():
    out = public_betting_mirror_rows([_PARSED], ingestion_timestamp="2026-07-01T18:00:00+00:00")
    row = out[0]
    assert set(row.keys()) == set(PUBLIC_BETTING_RAW_COLS), "mirror row missing/extra columns"
    assert row["ingestion_timestamp"] == "2026-07-01T18:00:00+00:00"
    assert row["an_game_id"] == "AN1" and row["home_ml_money_pct"] == 55.0
    assert isinstance(row["game_date"], str)

    # Absent stamp → one is generated (a whole capture shares it).
    auto = public_betting_mirror_rows([_PARSED, {**_PARSED, "an_game_id": "AN2"}])
    assert auto[0]["ingestion_timestamp"] and auto[0]["ingestion_timestamp"] == auto[1]["ingestion_timestamp"]


def test_series_rows_carry_explicit_captured_at():
    out = public_betting_series_rows([_PARSED], captured_at="2026-07-01T18:00:00+00:00")
    row = out[0]
    assert set(row.keys()) == set(PUBLIC_BETTING_SERIES_COLS)
    assert row["captured_at"] == "2026-07-01T18:00:00+00:00"
    assert "ingestion_timestamp" not in row  # the series uses captured_at, not the raw-mirror name


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


def test_series_row_roundtrips_through_write_raw_rows_s3(tmp_path):
    rows = public_betting_series_rows([_PARSED], captured_at="2026-07-01T18:00:00+00:00")
    fake = _FakeS3()
    n = write_raw_rows_s3(_SERIES, rows, mode="append", s3_client=fake)
    assert n == 1 and len(fake.puts) == 1
    key, body = fake.puts[0]
    assert f"lakehouse_raw/{_SERIES}/dt=" in key and key.endswith(".parquet")
    out = tmp_path / "part.parquet"
    out.write_bytes(body)
    d = pq.read_table(str(out)).to_pydict()
    assert d["an_game_id"][0] == "AN1"
    assert d["captured_at"][0] == "2026-07-01T18:00:00+00:00"  # ISO VARCHAR (the reconstructable stamp)
    assert d["home_ml_money_pct"][0] == 55.0
    con = duckdb.connect()
    ts = con.execute(f"SELECT try_cast(captured_at AS timestamp) FROM read_parquet('{out}')").fetchone()[0]
    assert ts is not None


def test_writer_targets_shared_sources():
    mod = importlib.import_module("ingest_actionnetwork_betting")
    assert mod._LAKEHOUSE_SOURCE == _SOURCE and mod._LAKEHOUSE_SERIES == _SERIES
    assert mod._LAKEHOUSE_SOURCE in RAW_SOURCES and mod._LAKEHOUSE_SERIES in RAW_SOURCES
    assert hasattr(mod, "lakehouse_write_legs") and hasattr(mod, "public_betting_mirror_rows")


def test_public_betting_models_render_clean_duckdb_branch():
    """extract_duckdb_sql must pull a clean DuckDB branch for all 4 models — no unresolved Jinja and no
    Snowflake lakehouse_ext reference leaking from the else branch (that would query the ext table inside
    the DuckDB build)."""
    run_w1 = importlib.import_module("run_w1_lakehouse")
    for m in run_w1.W11D_MODELS:
        sql = run_w1.extract_duckdb_sql(m)
        assert "{{" not in sql and "{%" not in sql, f"{m}: unresolved Jinja"
        assert "lakehouse_ext" not in sql.lower(), f"{m}: else-branch ext ref leaked into DuckDB SQL"
        assert ("public_betting_raw" in sql
                or "public_betting_status" in sql
                or "public_betting_snapshots" in sql), f"{m}: no source read"
    # The snapshots stg joins the pregame spine by BARE name (a registered view), not a Jinja ref.
    snap = run_w1.extract_duckdb_sql("stg_actionnetwork_public_betting_snapshots")
    assert "feature_pregame_game_features" in snap


def test_build_refresh_generator_model_lists_agree():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    refresh = importlib.import_module("refresh_w1_external_tables")
    gen = importlib.import_module("ddl.generate_w11d_external_tables")
    expected = {"stg_actionnetwork_public_betting", "stg_actionnetwork_public_betting_snapshots",
                "feature_pregame_public_betting_status", "feature_pregame_public_betting_features"}
    assert set(run_w1.W11D_MODELS) == expected
    assert set(refresh.W11D_TABLES) == expected
    assert set(gen.W11D_MODELS) == expected
