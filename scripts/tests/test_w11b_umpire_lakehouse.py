"""E11.1-W11 Tier-B (umpire ingestion → S3) — unit tests for the shared-umpire-feed flip.

Offline (no S3/Snowflake). Verifies:
  • umpire_game_log is registered in RAW_SOURCES and in the bridge + parity source sets;
  • umpire_mirror_rows() normalizes any partial writer row to the full column set + stamps
    loaded_at / data_source (the stg dedup tiebreaker + source tag the record dict lacks);
  • a normalized umpire row round-trips through write_raw_rows_s3 with scalar columns intact;
  • the 4 umpire writers import cleanly and target the shared _LAKEHOUSE_SOURCE;
  • the 4 umpire dbt models render a clean DuckDB branch (no unresolved Jinja, no lakehouse_ext
    leak) and the build/refresh/generator model lists agree.
"""
import importlib

import duckdb
import pyarrow.parquet as pq

from utils.lakehouse_raw_writer import (
    RAW_SOURCES,
    UMPIRE_GAME_LOG_COLS,
    umpire_mirror_rows,
    write_raw_rows_s3,
)

_SOURCE = "umpire_game_log"


def test_umpire_source_registered_everywhere():
    assert _SOURCE in RAW_SOURCES
    bridge = importlib.import_module("export_w11_raw_to_s3")
    parity = importlib.import_module("parity_check_w11")
    assert _SOURCE in bridge.SOURCES, "export_w11_raw_to_s3 missing umpire_game_log"
    assert _SOURCE in parity.SOURCES, "parity_check_w11 missing umpire_game_log"


def test_umpire_mirror_rows_normalizes_partial_rows():
    """A daily-assignment row (5 cols) and a scorecards row (data_source present) both expand to the
    full column set; loaded_at is stamped, data_source defaulted, game_date coerced to a string."""
    # ingest_umpires-shape row: only assignment columns, no data_source / loaded_at / tendency cols.
    partial = [{"game_pk": 777001, "game_date": "2026-06-30", "season": 2026,
                "umpire_name": "Angel Hernandez", "umpire_id": "12345"}]
    out = umpire_mirror_rows(partial, data_source="statsapi")
    row = out[0]
    assert set(row.keys()) == set(UMPIRE_GAME_LOG_COLS), "mirror row missing/extra columns"
    assert row["data_source"] == "statsapi"
    assert row["loaded_at"] is not None and isinstance(row["loaded_at"], str)
    assert row["k_pct"] is None and row["total_run_impact"] is None  # NULL tendency for assignments
    assert row["game_pk"] == 777001

    # A row that ALREADY carries data_source (scorecards/historical) keeps it (not overwritten).
    already = [{"game_pk": 1, "game_date": "2026-06-01", "season": 2026, "umpire_name": "X",
                "data_source": "umpscorecards", "total_run_impact": 1.23}]
    out2 = umpire_mirror_rows(already, data_source="statsapi")  # default must NOT clobber
    assert out2[0]["data_source"] == "umpscorecards"
    assert out2[0]["total_run_impact"] == 1.23


def test_explicit_loaded_at_is_shared_across_a_batch():
    rows = [{"game_pk": i, "game_date": "2026-06-30", "season": 2026, "umpire_name": "U"} for i in range(3)]
    out = umpire_mirror_rows(rows, data_source="statsapi_backfill", loaded_at="2026-06-30T00:00:00+00:00")
    assert {r["loaded_at"] for r in out} == {"2026-06-30T00:00:00+00:00"}
    assert {r["data_source"] for r in out} == {"statsapi_backfill"}


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


def test_umpire_row_roundtrips_through_write_raw_rows_s3(tmp_path):
    rows = umpire_mirror_rows(
        [{"game_pk": 999, "game_date": "2026-06-30", "season": 2026, "umpire_name": "Joe West",
          "total_runs": 9, "total_run_impact": 0.42, "accuracy_above_expected": 0.91}],
        data_source="umpscorecards", loaded_at="2026-06-30T12:00:00+00:00",
    )
    fake = _FakeS3()
    n = write_raw_rows_s3(_SOURCE, rows, mode="append", s3_client=fake)
    assert n == 1 and len(fake.puts) == 1
    key, body = fake.puts[0]
    # The dt= partition is derived from the auto-stamped ingestion_ts (layout only — the stg dedup
    # keys on loaded_at, not the partition), so assert the source prefix, not a specific date.
    assert "lakehouse_raw/umpire_game_log/dt=" in key and key.endswith(".parquet")
    out = tmp_path / "part.parquet"
    out.write_bytes(body)
    d = pq.read_table(str(out)).to_pydict()
    assert d["game_pk"][0] == 999
    assert d["data_source"][0] == "umpscorecards"
    assert d["loaded_at"][0] == "2026-06-30T12:00:00+00:00"  # ISO VARCHAR (INC-23 cure)
    # DuckDB reads it + casts loaded_at to a timestamp (the stg duckdb branch's use-site cast).
    con = duckdb.connect()
    ts = con.execute(f"SELECT try_cast(loaded_at AS timestamp) FROM read_parquet('{out}')").fetchone()[0]
    assert ts is not None


def test_four_umpire_writers_target_shared_source():
    for mod_name in ("ingest_umpires", "ingest_umpire_scorecards",
                     "ingest_umpires_historical", "backfill_umpire_assignments"):
        mod = importlib.import_module(mod_name)
        assert getattr(mod, "_LAKEHOUSE_SOURCE") == _SOURCE, f"{mod_name} _LAKEHOUSE_SOURCE drift"
        assert mod._LAKEHOUSE_SOURCE in RAW_SOURCES
        assert hasattr(mod, "lakehouse_write_legs") and hasattr(mod, "umpire_mirror_rows")


def test_umpire_models_render_clean_duckdb_branch():
    """extract_duckdb_sql must pull a clean DuckDB branch for all 4 models — no unresolved Jinja and
    no Snowflake lakehouse_ext reference leaking from the else branch (that would query the ext table
    inside the DuckDB build)."""
    run_w1 = importlib.import_module("run_w1_lakehouse")
    for m in run_w1.W11B_MODELS:
        sql = run_w1.extract_duckdb_sql(m)
        assert "{{" not in sql and "{%" not in sql, f"{m}: unresolved Jinja"
        assert "lakehouse_ext" not in sql.lower(), f"{m}: else-branch ext ref leaked into DuckDB SQL"
        assert "read_parquet" in sql or "from stg_statsapi_umpire" in sql.lower(), f"{m}: no source read"


def test_build_refresh_generator_model_lists_agree():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    refresh = importlib.import_module("refresh_w1_external_tables")
    gen = importlib.import_module("ddl.generate_w11b_external_tables")
    expected = {"stg_statsapi_umpire_game_log", "stg_statsapi_umpire_snapshots",
                "feature_pregame_umpire_features", "feature_pregame_umpire_status"}
    assert set(run_w1.W11B_MODELS) == expected
    assert set(refresh.W11B_TABLES) == expected
    assert set(gen.W11B_MODELS) == expected
