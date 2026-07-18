"""Fast-gate unit tests for the NFL-N0.2 lakehouse scaffold.

Pure logic only — no network, no S3 (all external IO is mocked / local FS), so this stays in
the fast gate. Guards the N0.1/N0.2 landmines encoded in the scaffold: the wide-`pbp` null-column
→ Delta `void` cure (`_sanitize_null_columns` + a real typed round-trip), the typed-vs-JSON write
routing (`write_dataframe` vs `write_records`), the below-floor 404 → empty-slice skip, the
`pbp_participation` no-season-col stamp, the Delta unsigned-int rejection, registry completeness,
and the AKID-safe storage_options.
"""
from __future__ import annotations

import json

import pandas as pd
import pyarrow as pa
import pytest

from quant_sports_intel_models.football.nfl.ingest import s3io
from quant_sports_intel_models.football.nfl.ingest import sources as src
from quant_sports_intel_models.football.nfl.ingest.handler import (
    _land,
    _parse_seasons,
    _resolve_sources,
    run_ingest,
)


# ── s3io pure logic ─────────────────────────────────────────────────────────────────────
def test_records_to_arrow_schema_and_rawjson():
    recs = [{"id": "e1", "home_team": "A"}, {"id": "e2", "home_team": "B"}]
    tbl = s3io.records_to_arrow(recs, source="odds_nfl", season=2024, week=None)
    assert tbl.column_names == ["season", "week", "source", "ingested_at", "raw_json"]
    assert tbl.num_rows == 2
    assert tbl.column("season").to_pylist() == [2024, 2024]
    assert json.loads(tbl.column("raw_json")[0].as_py())["home_team"] == "A"


def test_reject_unsigned_delta():
    tbl = pa.table({"season": pa.array([2024], pa.int64()), "u": pa.array([1], pa.uint64())})
    with pytest.raises(ValueError):
        s3io._reject_unsigned(tbl, "ctx")


def test_sanitize_null_columns_casts_void_to_string():
    # The wide-pbp landmine: an all-null column arrives as pyarrow `null` type → Delta `void`
    # (unreadable). _sanitize_null_columns recasts it to string (value-preserving, all null).
    tbl = pa.table({
        "season": pa.array([2024, 2024], pa.int64()),
        "end_yard_line": pa.array([None, None], pa.null()),  # the void-prone column
        "yards": pa.array([3, 7], pa.int64()),
    })
    assert pa.types.is_null(tbl.schema.field("end_yard_line").type)
    out = s3io._sanitize_null_columns(tbl)
    assert pa.types.is_string(out.schema.field("end_yard_line").type)
    assert out.column("end_yard_line").to_pylist() == [None, None]  # still all-null
    assert out.column("yards").to_pylist() == [3, 7]  # untouched
    # no-op when there are no null-typed columns (identity)
    clean = pa.table({"season": pa.array([2024], pa.int64())})
    assert s3io._sanitize_null_columns(clean) is clean


def test_storage_options_never_empty_akid(monkeypatch):
    # An empty-string env key must NOT be forwarded (the object_store empty-AKID → 400 bug).
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    opts = s3io.storage_options()
    assert opts.get("AWS_ACCESS_KEY_ID", None) != ""  # either resolved-from-chain or absent
    assert opts["AWS_REGION"] == s3io.DEFAULT_REGION


def test_table_uri_layout():
    assert s3io.table_uri("nfl", "schedules", bucket="b") == "s3://b/nfl/raw/schedules"


def test_write_dataframe_empty_slice_skips(tmp_path):
    # A below-floor season yields an empty DataFrame → skip (0 rows), no empty partition.
    assert s3io.write_dataframe(pd.DataFrame(), sport="nfl", source="ftn_charting",
                                season=2019, local_root=str(tmp_path)) == 0
    assert s3io.write_dataframe(None, sport="nfl", source="ftn_charting",
                                season=2019, local_root=str(tmp_path)) == 0


# ── registry completeness ───────────────────────────────────────────────────────────────
def test_registry_size_and_split():
    # 32 = 30 nflverse + 2 Odds API (nfl_data_inventory.md §7; the ×3 NGS/×4 PFR expansions).
    assert len(src.SOURCES) == 32
    assert len(src.NFLVERSE_SOURCES) == 30
    assert len(src.ODDS_SOURCES) == 2
    for name in ["stats_player_week", "schedules", "ngs_receiving", "pbp",
                 "pfr_advstats_week_def", "nflverse_players", "odds_nfl"]:
        assert name in src.SOURCES


def test_stats_player_week_not_legacy():
    # Must be the 145-col stats_player release, NOT legacy player_stats (N0.1 §1). The URL the
    # fetcher builds points at the stats_player tag.
    fetch = src.SOURCES["stats_player_week"].fetch
    assert "stats_player" in fetch.__name__ and "player_stats" not in fetch.__name__


def test_registry_typing_and_scoping():
    assert src.SOURCES["odds_nfl"].typed is False          # JSON → write_records
    assert src.SOURCES["odds_nfl_scores"].typed is False
    assert src.SOURCES["stats_player_week"].typed is True   # DataFrame → write_dataframe
    assert src.SOURCES["nflverse_players"].season_scoped is False  # not season-grained (season=0)
    assert src.SOURCES["schedules"].season_scoped is True


# ── nflverse fetcher logic (no network — fake DuckDB conn) ───────────────────────────────
class _FakeDuck:
    """A stand-in DuckDB connection: records the URL+params, returns a canned df, or raises a
    404-shaped error for the below-floor test."""

    def __init__(self, df=None, raise_404=False):
        self._df = df if df is not None else pd.DataFrame({"season": [2024], "x": [1]})
        self._raise_404 = raise_404
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if self._raise_404:
            raise RuntimeError("HTTP Error: HTTP GET error on '...': 404 Not Found")
        return self

    def df(self):
        return self._df


def test_nflverse_seasonal_below_floor_404_returns_empty():
    # A per-year read below an asset's coverage floor 404s → empty df (clean skip, not error).
    ctx = src.Ctx(_duck=_FakeDuck(raise_404=True))
    fetch = src.SOURCES["ftn_charting"].fetch
    out = fetch(ctx, 2019)
    assert isinstance(out, pd.DataFrame) and out.empty


def test_nflverse_seasonal_non404_error_propagates():
    class _Boom(_FakeDuck):
        def execute(self, sql, params=None):
            raise RuntimeError("Binder Error: something real")

    ctx = src.Ctx(_duck=_Boom())
    with pytest.raises(RuntimeError):
        src.SOURCES["pbp"].fetch(ctx, 2024)


def test_participation_stamps_season_when_absent():
    # pbp_participation has NO season column → the fetcher stamps the URL year.
    duck = _FakeDuck(df=pd.DataFrame({"nflverse_game_id": ["2023_01_KC_DET"], "play_id": [1]}))
    ctx = src.Ctx(_duck=duck)
    out = src.SOURCES["pbp_participation"].fetch(ctx, 2023)
    assert "season" in out.columns and out["season"].tolist() == [2023]


def test_single_file_fetcher_filters_by_season():
    duck = _FakeDuck()
    ctx = src.Ctx(_duck=duck)
    src.SOURCES["ngs_passing"].fetch(ctx, 2024)
    sql, params = duck.calls[-1]
    assert "WHERE season = ?" in sql and params[1] == 2024
    assert "nextgen_stats/ngs_passing.parquet" in params[0]


def test_roster_str_cols_cast_to_varchar():
    # The cross-season type-drift cure: jersey_number/draft_number are VARCHAR ≤2015 but INTEGER
    # 2016+ → the fetcher must force them to VARCHAR so the Delta column type is stable across
    # season partitions (else the merge write fails `Cannot cast string '79D' to Int32`).
    duck = _FakeDuck(df=pd.DataFrame({"season": [2013], "jersey_number": ["79D"],
                                      "draft_number": ["1A"]}))
    ctx = src.Ctx(_duck=duck)
    src.SOURCES["weekly_rosters"].fetch(ctx, 2013)
    sql, _ = duck.calls[-1]  # the main SELECT (a LIMIT 0 schema-probe precedes it)
    assert "jersey_number::VARCHAR AS jersey_number" in sql
    assert "draft_number::VARCHAR AS draft_number" in sql
    assert "EXCLUDE (jersey_number, draft_number)" in sql
    # the registry advertises the pin (metadata for introspection)
    assert set(src.SOURCES["weekly_rosters"].str_cols) == {"jersey_number", "draft_number"}
    assert set(src.SOURCES["rosters"].str_cols) == {"jersey_number", "draft_number"}


def test_projection_noop_without_or_absent_str_cols():
    duck = _FakeDuck()  # canned df has columns season,x — not the drift cols
    assert src._projection(duck, "u", ()) == "*"           # no str_cols → plain select, no probe
    assert src._projection(duck, "u", ("nonexistent",)) == "*"  # absent col → still "*", no crash


def test_players_single_file_not_season_filtered():
    duck = _FakeDuck(df=pd.DataFrame({"gsis_id": ["00-1"], "x": [1]}))
    ctx = src.Ctx(_duck=duck)
    src.SOURCES["nflverse_players"].fetch(ctx, 2024)
    sql, params = duck.calls[-1]
    assert "WHERE" not in sql  # no season filter (not season-grained)
    assert "players/players.parquet" in params[0]


# ── handler routing + parsing ────────────────────────────────────────────────────────────
def test_land_routes_typed_vs_records(tmp_path):
    # typed=True → write_dataframe (typed columns); typed=False → write_records (raw_json).
    df = pd.DataFrame({"season": [2024], "player_id": ["00-1"], "passing_yards": [321]})
    _land(src.SOURCES["stats_player_week"], df, season=2024, bucket="b", local_root=str(tmp_path))
    _land(src.SOURCES["odds_nfl"], [{"id": "e1", "home_team": "A"}], season=2024,
          bucket="b", local_root=str(tmp_path))
    import duckdb

    con = duckdb.connect(); con.execute("INSTALL delta; LOAD delta")
    typed_uri = s3io.local_table_uri(str(tmp_path), "nfl", "stats_player_week")
    cols = con.execute(f"SELECT * FROM delta_scan('{typed_uri}') LIMIT 0").df().columns.tolist()
    assert "passing_yards" in cols and "raw_json" not in cols  # typed, not JSON-wrapped
    json_uri = s3io.local_table_uri(str(tmp_path), "nfl", "odds_nfl")
    jcols = con.execute(f"SELECT * FROM delta_scan('{json_uri}') LIMIT 0").df().columns.tolist()
    assert "raw_json" in jcols  # JSON path


def test_handler_parse_seasons():
    assert _parse_seasons("2025") == [2025]
    assert _parse_seasons("2016-2018") == [2016, 2017, 2018]
    assert _parse_seasons("2020,2022") == [2020, 2022]


def test_handler_resolve_sources_rejects_unknown():
    assert _resolve_sources(["schedules"]) == ["schedules"]
    with pytest.raises(ValueError):
        _resolve_sources(["not_a_source"])


def test_existing_seasons_and_skip(tmp_path):
    # Land two typed seasons locally, then existing_seasons reports them (pure FS listing).
    for yr in (2016, 2017):
        s3io.write_dataframe(pd.DataFrame({"season": [yr], "x": [1]}),
                             sport="nfl", source="schedules", season=yr, local_root=str(tmp_path))
    assert s3io.existing_seasons("nfl", "schedules", local_root=str(tmp_path)) == {2016, 2017}
    assert s3io.existing_seasons("nfl", "pbp", local_root=str(tmp_path)) == set()

    # skip_existing must NOT re-fetch a present season (fetch would raise here).
    def _boom(*a, **k):
        raise AssertionError("fetch must not be called for an already-ingested season")

    orig = src.SOURCES["schedules"].fetch
    src.SOURCES["schedules"].fetch = _boom
    try:
        m = run_ingest([2016], sources=["schedules"], local_root=str(tmp_path),
                       skip_existing=True, ctx=src.Ctx())
        assert m["schedules/2016"] == "skipped (already ingested)"
    finally:
        src.SOURCES["schedules"].fetch = orig


# ── a real local Delta round-trip proving the void cure end-to-end ───────────────────────
def test_typed_delta_roundtrip_with_null_column(tmp_path):
    # A typed nflverse-shaped slice with an ALL-NULL column (the pbp `void` landmine) must
    # write AND read back through delta_scan (pre-cure this raised 'Unsupported Delta type void').
    df = pd.DataFrame({
        "season": [2024, 2024],
        "play_id": [1, 2],
        "yards_gained": [3, 7],
        "end_yard_line": [None, None],  # all-null → void without the cure
    })
    n = s3io.write_dataframe(df, sport="nfl", source="pbp", season=2024, local_root=str(tmp_path))
    assert n == 2
    import duckdb

    con = duckdb.connect(); con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "nfl", "pbp")
    rows = con.execute(f"SELECT count(*) c, count(end_yard_line) nn "
                       f"FROM delta_scan('{uri}')").fetchone()
    assert rows[0] == 2 and rows[1] == 0  # 2 rows, end_yard_line all-null but READABLE

    # idempotent re-write of the same season = value-identical (still 2 rows, not 4)
    s3io.write_dataframe(df, sport="nfl", source="pbp", season=2024, local_root=str(tmp_path))
    assert con.execute(f"SELECT count(*) FROM delta_scan('{uri}')").fetchone()[0] == 2


def test_records_delta_roundtrip(tmp_path):
    # The JSON path (odds) round-trips too.
    n = s3io.write_records([{"id": "e1", "home_team": "A"}], sport="nfl", source="odds_nfl",
                           season=2024, local_root=str(tmp_path))
    assert n == 1
    import duckdb

    con = duckdb.connect(); con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "nfl", "odds_nfl")
    got = con.execute(f"SELECT json_extract_string(raw_json,'$.home_team') FROM "
                      f"delta_scan('{uri}')").fetchone()[0]
    assert got == "A"
