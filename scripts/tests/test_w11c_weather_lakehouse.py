"""E11.1-W11 Tier-C (weather ingestion → S3) — unit tests for the weather-feed flip + retention.

Offline (no S3/Snowflake). Verifies:
  • weather_raw is registered in RAW_SOURCES + the bridge/parity source sets; weather_intraday_series
    is S3-ONLY (in RAW_SOURCES but NOT in the bridge/parity, which mirror Snowflake tables);
  • weather_mirror_rows() / weather_series_rows() normalize + stamp loaded_at / captured_at;
  • dedupe_latest_per_key() keeps the latest row per key across MIXED ISO timestamp formats (the
    INC-23 bridge-vs-live union) — the retention primitive;
  • write_raw_rows_s3_retained() merges the incoming rows with the existing dt= partition, keeps the
    latest per key, and overwrites — a re-fetch never inflates the mirror;
  • both weather writers import cleanly and target the shared _LAKEHOUSE_SOURCE;
  • the 4 weather dbt models render a clean DuckDB branch (no unresolved Jinja, no lakehouse_ext leak)
    and the build/refresh/generator model lists agree.
"""
import importlib
import io

import duckdb
import pyarrow.parquet as pq

from utils.lakehouse_raw_writer import (
    RAW_SOURCES,
    WEATHER_RAW_COLS,
    WEATHER_RAW_RETENTION_KEY,
    WEATHER_SERIES_RETENTION_KEY,
    dedupe_latest_per_key,
    weather_mirror_rows,
    weather_series_rows,
    write_raw_rows_s3,
    write_raw_rows_s3_retained,
)

_SOURCE = "weather_raw"
_SERIES = "weather_intraday_series"


def test_weather_sources_registered():
    assert _SOURCE in RAW_SOURCES
    assert _SERIES in RAW_SOURCES
    bridge = importlib.import_module("export_w11_raw_to_s3")
    parity = importlib.import_module("parity_check_w11")
    assert _SOURCE in bridge.SOURCES, "export_w11_raw_to_s3 missing weather_raw"
    assert _SOURCE in parity.SOURCES, "parity_check_w11 missing weather_raw"
    # The hourly series is a brand-new S3-only source — it has NO Snowflake table to bridge / parity.
    assert _SERIES not in bridge.SOURCES
    assert _SERIES not in parity.SOURCES


def test_weather_mirror_rows_normalizes_and_stamps():
    partial = [{"game_pk": 777001, "venue_id": 3, "game_datetime_utc": "2026-06-30 23:05:00",
                "temp_f": 72.0, "wind_speed_mph": 8.0, "wind_direction_deg": 180,
                "humidity_pct": 55, "condition_text": None, "api_source": "open-meteo",
                "weather_observation_type": "forecast_pregame", "hours_to_first_pitch": None}]
    out = weather_mirror_rows(partial)
    row = out[0]
    assert set(row.keys()) == set(WEATHER_RAW_COLS), "mirror row missing/extra columns"
    assert isinstance(row["loaded_at"], str) and row["loaded_at"]  # stamped
    assert row["game_datetime_utc"] == "2026-06-30 23:05:00"
    assert row["game_pk"] == 777001

    # An explicit loaded_at is shared + coerced to ISO string.
    out2 = weather_mirror_rows(partial, loaded_at="2026-06-30T12:00:00+00:00")
    assert out2[0]["loaded_at"] == "2026-06-30T12:00:00+00:00"


def test_weather_series_rows_stamp_captured_hour():
    rows = [{"game_pk": 1, "venue_id": 2, "temp_f": 70.0, "wind_speed_mph": 5.0,
             "wind_direction_deg": 90, "humidity_pct": 40, "condition_text": "Clear",
             "api_source": "open-meteo"}]
    out = weather_series_rows(rows, captured_at="2026-07-01T18:42:11+00:00")
    r = out[0]
    assert r["captured_at"] == "2026-07-01T18:42:11+00:00"
    assert r["captured_hour"] == "2026-07-01T18"  # hour bucket = retention key
    assert r["weather_observation_type"] == "forecast_intraday_series"  # defaulted


def test_dedupe_latest_per_key_mixed_ts_formats():
    # Same key, two loaded_at values in DIFFERENT ISO formats (space vs 'T'+offset — the bridge/live
    # union). Lexicographic order would be wrong; the parsed sort must pick the later wall-clock.
    rows = [
        {"game_pk": 5, "venue_id": 1, "weather_observation_type": "forecast_pregame",
         "hours_to_first_pitch": None, "temp_f": 60.0, "loaded_at": "2026-06-30 09:00:00"},
        {"game_pk": 5, "venue_id": 1, "weather_observation_type": "forecast_pregame",
         "hours_to_first_pitch": None, "temp_f": 71.0, "loaded_at": "2026-06-30T15:30:00+00:00"},
        {"game_pk": 6, "venue_id": 1, "weather_observation_type": "forecast_pregame",
         "hours_to_first_pitch": None, "temp_f": 55.0, "loaded_at": "2026-06-30 12:00:00"},
    ]
    out = dedupe_latest_per_key(rows, WEATHER_RAW_RETENTION_KEY, "loaded_at")
    by_pk = {r["game_pk"]: r for r in out}
    assert len(out) == 2
    assert by_pk[5]["temp_f"] == 71.0, "latest loaded_at (later wall-clock) must win across formats"
    assert by_pk[6]["temp_f"] == 55.0


def test_series_dedupe_keeps_every_hour():
    # Two hours for the same game → both kept (the trajectory is the signal). A re-capture in the same
    # hour collapses to the latest.
    rows = weather_series_rows([
        {"game_pk": 9, "venue_id": 1, "temp_f": 70.0},
        {"game_pk": 9, "venue_id": 1, "temp_f": 71.0},
    ], captured_at="2026-07-01T18:00:00+00:00") + weather_series_rows([
        {"game_pk": 9, "venue_id": 1, "temp_f": 80.0},
    ], captured_at="2026-07-01T19:00:00+00:00")
    out = dedupe_latest_per_key(rows, WEATHER_SERIES_RETENTION_KEY, "captured_at")
    temps = sorted(r["temp_f"] for r in out)
    assert temps == [71.0, 80.0], "one row per hour: latest in 18h (71) + the 19h row (80)"


class _FakeS3:
    """In-memory S3 stub: stores puts, lists + returns them so the retention read-back round-trips."""
    def __init__(self):
        self.store: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body):
        self.store[Key] = Body

    def delete_object(self, Bucket, Key):
        self.store.pop(Key, None)

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.store[Key])}

    def get_paginator(self, _):
        store = self.store

        class P:
            def paginate(self, **kw):
                prefix = kw.get("Prefix", "")
                yield {"Contents": [{"Key": k} for k in store if k.startswith(prefix)]}
        return P()


def test_write_raw_rows_s3_retained_merges_and_dedups():
    fake = _FakeS3()
    key = WEATHER_RAW_RETENTION_KEY
    r1 = weather_mirror_rows([{"game_pk": 5, "venue_id": 1, "temp_f": 60.0,
                               "weather_observation_type": "forecast_pregame",
                               "hours_to_first_pitch": None}],
                             loaded_at="2026-06-30T09:00:00+00:00")
    n1 = write_raw_rows_s3_retained(_SOURCE, r1, key_cols=key, ts_col="loaded_at", s3_client=fake)
    assert n1 == 1

    # A SECOND fetch of the SAME (game, obs, checkpoint) with a later loaded_at must COLLAPSE to 1 row,
    # not append a duplicate (INC-20 retention).
    r2 = weather_mirror_rows([{"game_pk": 5, "venue_id": 1, "temp_f": 75.0,
                               "weather_observation_type": "forecast_pregame",
                               "hours_to_first_pitch": None}],
                             loaded_at="2026-06-30T15:00:00+00:00")
    n2 = write_raw_rows_s3_retained(_SOURCE, r2, key_cols=key, ts_col="loaded_at", s3_client=fake)
    assert n2 == 1, "retained mirror stays at 1 row for the key"

    # Read back everything in the partition → exactly one row, the LATEST temp.
    all_rows = []
    for k, body in fake.store.items():
        all_rows.extend(pq.read_table(io.BytesIO(body)).to_pylist())
    assert len(all_rows) == 1
    assert all_rows[0]["temp_f"] == 75.0


def test_weather_row_roundtrips_and_casts(tmp_path):
    rows = weather_mirror_rows([{"game_pk": 999, "venue_id": 2,
                                 "game_datetime_utc": "2026-06-30 23:05:00", "temp_f": 68.5,
                                 "wind_speed_mph": 10.0, "wind_direction_deg": 200, "humidity_pct": 60,
                                 "condition_text": None, "api_source": "open-meteo",
                                 "weather_observation_type": "forecast_pregame",
                                 "hours_to_first_pitch": None}],
                               loaded_at="2026-06-30T12:00:00+00:00")

    class _Put:
        def __init__(self): self.puts = []
        def put_object(self, Bucket, Key, Body): self.puts.append((Key, Body))
        def get_paginator(self, _):
            class P:
                def paginate(self, **kw): return iter([{}])
            return P()
    fake = _Put()
    n = write_raw_rows_s3(_SOURCE, rows, mode="append", s3_client=fake)
    assert n == 1 and len(fake.puts) == 1
    key, body = fake.puts[0]
    assert "lakehouse_raw/weather_raw/dt=" in key and key.endswith(".parquet")
    out = tmp_path / "part.parquet"
    out.write_bytes(body)
    d = pq.read_table(str(out)).to_pydict()
    assert d["game_pk"][0] == 999 and d["loaded_at"][0] == "2026-06-30T12:00:00+00:00"
    con = duckdb.connect()
    ts = con.execute(
        f"SELECT try_cast(loaded_at AS timestamp), try_cast(game_datetime_utc AS timestamp) "
        f"FROM read_parquet('{out}')"
    ).fetchone()
    assert ts[0] is not None and ts[1] is not None  # the stg duckdb-branch use-site cast


def test_both_weather_writers_target_shared_source():
    for mod_name in ("ingest_weather", "backfill_observed_weather"):
        mod = importlib.import_module(mod_name)
        assert getattr(mod, "_LAKEHOUSE_SOURCE") == _SOURCE, f"{mod_name} _LAKEHOUSE_SOURCE drift"
        assert mod._LAKEHOUSE_SOURCE in RAW_SOURCES
        assert hasattr(mod, "lakehouse_write_legs") and hasattr(mod, "weather_mirror_rows")


def test_weather_models_render_clean_duckdb_branch():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    for m in run_w1.W11C_MODELS:
        sql = run_w1.extract_duckdb_sql(m)
        assert "{{" not in sql and "{%" not in sql, f"{m}: unresolved Jinja"
        assert "lakehouse_ext" not in sql.lower(), f"{m}: else-branch ext ref leaked into DuckDB SQL"
        assert ("read_parquet" in sql or "from feature_pregame_weather_status" in sql.lower()
                or "from stg_weather_raw_snapshots" in sql.lower()), f"{m}: no source read"


def test_build_refresh_generator_model_lists_agree():
    run_w1 = importlib.import_module("run_w1_lakehouse")
    refresh = importlib.import_module("refresh_w1_external_tables")
    gen = importlib.import_module("ddl.generate_w11c_external_tables")
    expected = {"stg_weather_raw", "stg_weather_raw_snapshots",
                "feature_pregame_weather_status", "feature_pregame_weather_features"}
    assert set(run_w1.W11C_MODELS) == expected
    assert set(refresh.W11C_TABLES) == expected
    assert set(gen.W11C_MODELS) == expected
