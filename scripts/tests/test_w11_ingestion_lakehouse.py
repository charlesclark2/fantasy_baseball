"""E11.1-W11 (ingestion FINISH wave) — unit tests for the Tier-A raw-feed Snowflake→S3 flip.

Offline (no S3/Snowflake). Verifies:
  • the 7 Tier-A sources are registered in the shared dispatcher's RAW_SOURCES;
  • the bridge (export_w11_raw_to_s3) and parity (parity_check_w11) source sets agree with the
    registry — so a typo in one can't silently drift from the writers;
  • a TYPED row (no raw_json) round-trips through write_raw_rows_s3 with its scalar columns intact
    (the typed Tier-A feeds — sprint_speed/oaa/park_factors — carry no _JSON_COLS member);
  • the flipped FanGraphs writers import the dispatcher and target a registered source.
"""
import importlib

import duckdb
import pyarrow.parquet as pq

from utils.lakehouse_raw_writer import (
    RAW_SOURCES,
    lakehouse_write_legs,
    w11_write_mode,
    write_raw_rows_s3,
)

# The Tier-A sources this wave flips (writers + bridge + parity must all agree on this set).
W11_TIER_A_SOURCES = {
    "fg_stuff_plus_raw",
    "fg_hitting_leaderboard_raw",
    "catcher_framing_raw",
    "player_transactions",
    "sprint_speed_raw",
    "oaa_team_season_raw",
    "savant_park_factors_raw",
}


def test_w11_write_mode_independent_of_shared_odds_env(monkeypatch):
    """CRITICAL no-op guard: the W11 flips must default to 'snowflake' REGARDLESS of the shared
    LAKEHOUSE_RAW_WRITE_MODE (already 's3'/'both' in prod for odds). Reusing the shared env would
    flip the W11 writers to S3-only on deploy, before any parity/cutover — silent SF starvation."""
    monkeypatch.setenv("LAKEHOUSE_RAW_WRITE_MODE", "s3")        # odds is cut over…
    monkeypatch.delenv("W11_RAW_WRITE_MODE", raising=False)     # …but W11 hasn't opted in
    assert w11_write_mode() == "snowflake"
    assert lakehouse_write_legs(w11_write_mode()) == (True, False)  # SF only — unchanged
    # The W11 wave opts in via its OWN env, leaving odds untouched.
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "both")
    assert lakehouse_write_legs(w11_write_mode()) == (True, True)   # dual-write
    monkeypatch.setenv("W11_RAW_WRITE_MODE", "s3")
    assert lakehouse_write_legs(w11_write_mode()) == (False, True)  # SF leg retired


def test_w11_sources_registered_in_dispatcher():
    missing = W11_TIER_A_SOURCES - set(RAW_SOURCES)
    assert not missing, f"W11 sources missing from RAW_SOURCES (write_raw_rows_s3 would reject): {missing}"


def test_bridge_and_parity_source_sets_agree_with_registry():
    bridge = importlib.import_module("export_w11_raw_to_s3")
    parity = importlib.import_module("parity_check_w11")
    # The bridge + parity must agree with EACH OTHER (a typo in one can't silently drift) and cover
    # at least Tier-A. Later tiers (B umpire, …) append to the same bridge/parity sets.
    assert set(bridge.SOURCES) == set(parity.SOURCES), "bridge/parity source sets drifted apart"
    assert W11_TIER_A_SOURCES <= set(bridge.SOURCES), "a Tier-A source dropped out of the bridge"
    # Every bridged/parity source must be a valid dispatcher source (else write/read would reject).
    assert set(bridge.SOURCES) <= set(RAW_SOURCES)
    assert W11_TIER_A_SOURCES <= set(RAW_SOURCES)


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


def test_typed_row_roundtrips_with_scalar_columns_intact(tmp_path):
    """A typed Tier-A feed (sprint_speed_raw) has NO raw_json — its scalar columns must survive the
    dispatcher as native parquet columns (only _JSON_COLS members get JSON-stringified)."""
    rows = [
        {"ingestion_ts": "2026-06-28T10:00:00", "player_mlbam_id": 660271, "season": 2026,
         "snapshot_date": "2026-06-28", "sprint_speed_fts": 28.7, "competitive_runs": 41},
    ]
    fake = _FakeS3()
    n = write_raw_rows_s3("sprint_speed_raw", rows, mode="append", s3_client=fake)
    assert n == 1 and len(fake.puts) == 1

    # The written bytes are a real parquet with the scalar columns preserved + readable by DuckDB.
    key, body = fake.puts[0]
    assert "lakehouse_raw/sprint_speed_raw/dt=2026-06-28/" in key
    out = tmp_path / "part.parquet"
    out.write_bytes(body)
    d = pq.read_table(str(out)).to_pydict()
    assert d["player_mlbam_id"][0] == 660271
    assert d["sprint_speed_fts"][0] == 28.7
    assert "raw_json" not in d  # typed feed — no JSON blob column invented
    # DuckDB can read it back (the read-side the cutover repoint will use).
    con = duckdb.connect()
    (cnt,) = con.execute(f"SELECT count(*) FROM read_parquet('{out}')").fetchone()
    assert cnt == 1


def test_nan_in_string_column_does_not_crash_arrow_build():
    """Regression (the sprint_speed crash): a pandas-derived row with a NaN float in an otherwise-
    STRING column (player_name) must normalize to None, not raise 'Expected bytes, got a float'."""
    from utils.lakehouse_raw_writer import rows_to_arrow_table
    rows = [
        {"ingestion_ts": "2026-06-30T18:00:00", "player_mlbam_id": 1, "player_name": "Mike Trout",
         "sprint_speed_fts": 28.7},
        {"ingestion_ts": "2026-06-30T18:00:00", "player_mlbam_id": 2, "player_name": float("nan"),
         "sprint_speed_fts": float("nan")},
    ]
    d = rows_to_arrow_table(rows).to_pydict()        # must not raise
    assert d["player_name"] == ["Mike Trout", None]  # NaN string → None
    assert d["sprint_speed_fts"][1] is None          # NaN numeric → None too


def test_all_seven_flipped_writers_target_registered_sources():
    """Every Tier-A writer imports cleanly (catches an import-time bug — e.g. a missing datetime
    import in a flipped writer) and tags a registered _LAKEHOUSE_SOURCE."""
    expected = {
        "ingest_fangraphs_stuff_plus": "fg_stuff_plus_raw",
        "ingest_fangraphs_hitting_leaderboard": "fg_hitting_leaderboard_raw",
        "ingest_transactions": "player_transactions",
        "ingest_savant_park_factors": "savant_park_factors_raw",
        "ingest_oaa": "oaa_team_season_raw",
        "ingest_sprint_speed": "sprint_speed_raw",
        "ingest_catcher_framing": "catcher_framing_raw",
    }
    assert set(expected.values()) == W11_TIER_A_SOURCES
    for mod_name, source in expected.items():
        mod = importlib.import_module(mod_name)
        assert getattr(mod, "_LAKEHOUSE_SOURCE") == source, f"{mod_name} _LAKEHOUSE_SOURCE drift"
        assert mod._LAKEHOUSE_SOURCE in RAW_SOURCES
        # The flip target is imported — either the dispatcher (FanGraphs) or the leg-gate primitive.
        assert hasattr(mod, "append_raw_rows_lakehouse") or hasattr(mod, "lakehouse_write_legs")
