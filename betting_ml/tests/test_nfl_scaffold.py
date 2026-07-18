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
    # 35 = 30 nflverse + 5 Odds API (N0.2's 2 live + N0.4's 3 net-new: props + 2 historical).
    assert len(src.SOURCES) == 35
    assert len(src.NFLVERSE_SOURCES) == 30
    assert len(src.ODDS_SOURCES) == 5
    for name in ["stats_player_week", "schedules", "ngs_receiving", "pbp",
                 "pfr_advstats_week_def", "nflverse_players", "odds_nfl",
                 "odds_nfl_props", "odds_nfl_historical", "odds_nfl_props_historical"]:
        assert name in src.SOURCES


def test_odds_on_demand_gating():
    # N0.4: the paid/per-event odds sources are on_demand → EXCLUDED from a default (unnamed)
    # run so a plain nflverse backfill never burns Odds-API credits; named explicitly they run.
    assert src.ODDS_LIVE == ["odds_nfl", "odds_nfl_scores"]           # cheap recurring feeds (default-in)
    assert set(src.ODDS_ON_DEMAND) == {"odds_nfl_props", "odds_nfl_historical",
                                       "odds_nfl_props_historical"}
    assert set(src.ODDS_HISTORICAL) == {"odds_nfl_historical", "odds_nfl_props_historical"}
    assert len(src.DEFAULT_SOURCES) == 32                             # the pre-N0.4 default set
    for name in src.ODDS_ON_DEMAND:
        assert name not in src.DEFAULT_SOURCES
        assert src.SOURCES[name].on_demand is True
    # handler: unnamed run drops on_demand; explicit names bypass the gate
    default = set(_resolve_sources(None))
    assert default.isdisjoint(src.ODDS_ON_DEMAND)
    assert _resolve_sources(["odds_nfl_historical"]) == ["odds_nfl_historical"]


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
    for name in ("odds_nfl_props", "odds_nfl_historical", "odds_nfl_props_historical"):
        assert src.SOURCES[name].typed is False            # raw_json (event arrays flatten in dbt)


# ── N0.4 odds fetchers (props + historical closing lines) — no network (fake requests) ────
class _FakeResp:
    """A stand-in requests.Response: canned JSON + credit headers, raises on 4xx/5xx."""

    def __init__(self, payload, *, used="100", remaining="9900", status=200,
                 content_type="application/json"):
        self._payload = payload
        self.headers = {"x-requests-used": used, "x-requests-remaining": remaining,
                        "Content-Type": content_type}
        self.status_code = status
        self.text = "err"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _patch_requests(monkeypatch, capture, responder):
    """Patch requests.get so the odds fetchers hit `responder(path, params)` instead of the net.
    Records every (url, params) into `capture` for call-shape assertions."""
    import requests

    def fake_get(url, params=None, timeout=None):
        capture.append((url, params or {}))
        return responder(url, params or {})

    monkeypatch.setattr(requests, "get", fake_get)


def test_odds_request_captures_credits_and_unwraps_historical(monkeypatch):
    # The /historical envelope {timestamp, data:[...]} unwraps to a flat list + the served
    # snapshot ts; credit headers land on ctx.
    calls: list = []
    envelope = {"timestamp": "2024-09-08T16:55:00Z", "previous_timestamp": "2024-09-08T16:50:00Z",
                "data": [{"id": "e1", "commence_time": "2024-09-08T17:00:00Z"}]}
    _patch_requests(monkeypatch, calls, lambda u, p: _FakeResp(envelope, used="250", remaining="9750"))
    ctx = src.build_ctx(odds_key="k", sleep_seconds=0)
    data, snap = src._odds_request(ctx, "historical/sports/x/odds", {"date": "z"})
    assert data == envelope["data"] and snap == "2024-09-08T16:55:00Z"
    assert ctx.credits_used == 250 and ctx.credits_remaining == 9750
    # a bare live list is passed through with snapshot None
    _patch_requests(monkeypatch, calls, lambda u, p: _FakeResp([{"id": "e2"}]))
    data2, snap2 = src._odds_request(ctx, "sports/x/odds", {})
    assert data2 == [{"id": "e2"}] and snap2 is None


def test_odds_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    ctx = src.Ctx(odds_api_key=None)
    with pytest.raises(RuntimeError, match="ODDS_API_KEY"):
        src._odds_request(ctx, "historical/sports/x/odds", {})


def test_current_props_event_endpoint_shape(monkeypatch):
    # odds_nfl_props: one /events call → one /events/{id}/odds per event, carrying the prop
    # markets. max_events caps the fan-out (the cheap verification pull).
    calls: list = []

    def responder(url, params):
        if url.endswith("/events"):
            return _FakeResp([{"id": "evA"}, {"id": "evB"}, {"id": "evC"}])
        return _FakeResp([{"id": params.get("_eid", "ev"), "bookmakers": []}])

    _patch_requests(monkeypatch, calls, responder)
    ctx = src.build_ctx(odds_key="k", sleep_seconds=0, max_events=2)
    out = src._odds_nfl_props(ctx, 2024)
    event_calls = [u for u, _ in calls if "/events/" in u and u.endswith("/odds")]
    assert len(event_calls) == 2                      # capped to 2 of 3 events
    assert all(f"sports/{src.ODDS_SPORT_KEY}/events/" in u for u in event_calls)
    prop_params = [p for u, p in calls if "/events/" in u][0]
    assert prop_params["markets"] == ",".join(src.NFL_PROP_MARKETS)  # DEEP prop set
    assert prop_params["regions"] == "us"
    assert len(out) == 2


def test_historical_closing_line_is_leakage_safe(monkeypatch):
    # odds_nfl_historical: for each kickoff K the snapshot `date` is K − buffer (strictly before
    # kickoff) and commenceTimeFrom/To bracket K → leakage-safe close; rows carry _snapshot_ts.
    calls: list = []
    kickoff = "2024-09-08T17:00:00Z"
    envelope = {"timestamp": "2024-09-08T16:55:00Z",
                "data": [{"id": "e1", "commence_time": kickoff, "bookmakers": []}]}
    _patch_requests(monkeypatch, calls, lambda u, p: _FakeResp(envelope))

    # one distinct kickoff at 17:00Z
    from datetime import datetime, timezone
    monkeypatch.setattr(src, "_season_kickoffs",
                        lambda ctx, year, weeks=None: [datetime(2024, 9, 8, 17, 0, tzinfo=timezone.utc)])
    ctx = src.build_ctx(odds_key="k", sleep_seconds=0, snapshot_buffer_min=5)
    out = src._odds_nfl_historical(ctx, 2024)
    assert len(calls) == 1
    url, params = calls[0]
    assert f"historical/sports/{src.ODDS_SPORT_KEY}/odds" in url
    assert params["date"] == "2024-09-08T16:55:00Z"           # K − 5min (pre-kickoff)
    assert params["markets"] == src.NFL_GAME_LINE_MARKETS
    assert params["commenceTimeFrom"] < kickoff < params["commenceTimeTo"]  # window brackets K
    # the served snapshot is recorded AND is < the event commence_time (the hard leakage guard)
    assert out[0]["_snapshot_ts"] == "2024-09-08T16:55:00Z"
    assert out[0]["_requested_snapshot"] == "2024-09-08T16:55:00Z"
    assert out[0]["_snapshot_ts"] < out[0]["commence_time"]


def test_props_historical_dedups_and_pins_own_commence(monkeypatch):
    # The credit bug guard: overlapping ±30-min kickoff windows must NOT re-fetch an event's
    # props. Two distinct kickoffs 20 min apart (20:05 / 20:25); each events-list returns BOTH
    # games → props must fire ONCE per unique event, each at ITS OWN commence − buffer.
    from datetime import datetime, timezone
    calls: list = []
    g1 = {"id": "g1", "commence_time": "2024-09-08T20:05:00Z"}
    g2 = {"id": "g2", "commence_time": "2024-09-08T20:25:00Z"}

    def responder(url, params):
        if url.endswith("/events"):                 # both windows list BOTH games (the overlap)
            return _FakeResp({"timestamp": params["date"], "data": [g1, g2]})
        # event-odds: echo which event + snapshot was requested
        eid = url.rstrip("/odds").rsplit("/", 1)[-1]
        return _FakeResp({"timestamp": params["date"],
                          "data": [{"id": eid, "_req_date": params["date"], "bookmakers": []}]})

    _patch_requests(monkeypatch, calls, responder)
    monkeypatch.setattr(src, "_season_kickoffs", lambda ctx, year, weeks=None: [
        datetime(2024, 9, 8, 20, 5, tzinfo=timezone.utc),
        datetime(2024, 9, 8, 20, 25, tzinfo=timezone.utc),
    ])
    ctx = src.build_ctx(odds_key="k", sleep_seconds=0, snapshot_buffer_min=5)
    out = src._odds_nfl_props_historical(ctx, 2024)
    prop_calls = [(u, p) for u, p in calls if "/events/" in u and u.endswith("/odds")]
    # exactly 2 per-event props calls (NOT 4) — each unique event fetched ONCE despite the overlap
    assert len(prop_calls) == 2
    fetched = {u.rstrip("/odds").rsplit("/", 1)[-1]: p["date"] for u, p in prop_calls}
    assert fetched == {"g1": "2024-09-08T20:00:00Z",   # g1 commence 20:05 − 5min
                       "g2": "2024-09-08T20:20:00Z"}   # g2 commence 20:25 − 5min (its OWN, not g1's)
    assert len(out) == 2


def test_props_historical_below_floor_skips_without_calls(monkeypatch):
    # Player-prop historical coverage starts season 2023 (Odds-API additional markets ~2023-05);
    # a pre-floor season must skip WHOLE (no events-list / no per-event 422 grinding, 0 credits).
    calls: list = []
    _patch_requests(monkeypatch, calls, lambda u, p: _FakeResp([]))
    # guard even if _season_kickoffs would return something — the floor check precedes it
    monkeypatch.setattr(src, "_season_kickoffs",
                        lambda ctx, year, weeks=None: (_ for _ in ()).throw(
                            AssertionError("must not enumerate kickoffs below the props floor")))
    ctx = src.build_ctx(odds_key="k", sleep_seconds=0)
    assert src.NFL_PROPS_HISTORICAL_FLOOR == 2023
    assert src._odds_nfl_props_historical(ctx, 2022) == []   # below floor → empty, no calls
    assert calls == []


def test_season_kickoffs_et_to_utc_distinct(monkeypatch):
    # gameday(ET date) + gametime(ET HH:MM) → distinct UTC kickoff datetimes (DST-correct).
    # Two 13:00 ET games collapse to ONE distinct kickoff; a null gametime is skipped.
    rows = [("2024-09-08", "13:00"), ("2024-09-08", "13:00"),  # dup window → 1 kickoff
            ("2024-09-08", "16:25"), ("2024-09-05", "20:20"),  # opener (Thu)
            ("2024-09-08", None)]                               # not scheduled → skipped

    class _SchedDuck:
        def execute(self, sql, params=None):
            self._rows = rows
            return self

        def fetchall(self):
            return [r for r in self._rows]

    ctx = src.Ctx(_duck=_SchedDuck())
    kicks = src._season_kickoffs(ctx, 2024)
    iso = sorted(k.strftime("%Y-%m-%dT%H:%M:%SZ") for k in kicks)
    # Sep 2024 is EDT (UTC−4): 13:00→17:00Z, 16:25→20:25Z, 20:20(Sep5)→00:20Z(Sep6)
    assert iso == ["2024-09-06T00:20:00Z", "2024-09-08T17:00:00Z", "2024-09-08T20:25:00Z"]


def test_build_ctx_odds_knobs():
    ctx = src.build_ctx(odds_key="k", regions="us,us2", snapshot_buffer_min=3,
                        sleep_seconds=0.0, max_events=5, prop_markets=("player_pass_yds",))
    assert ctx.odds_regions == "us,us2" and ctx.odds_snapshot_buffer_min == 3
    assert ctx.odds_max_events == 5 and ctx.odds_prop_markets == ("player_pass_yds",)
    # default prop set when not overridden
    assert src.build_ctx().odds_prop_markets == src.NFL_PROP_MARKETS


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
