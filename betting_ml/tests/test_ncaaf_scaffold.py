"""Fast-gate unit tests for the NCAAF-P0.2 lakehouse scaffold.

Pure logic only — no network, no S3 (all external IO is mocked / local FS), so this stays
in the fast gate. Guards the P0.1 landmines encoded in the scaffold (the CFBD JSON-content
guard, the year-only vs per-game call shapes, the Delta unsigned-int rejection) + the
registry completeness + a real local Delta round-trip (write → delta_scan read-back).
"""
from __future__ import annotations

import json

import pyarrow as pa
import pytest

from quant_sports_intel_models.football.ncaaf.ingest import s3io
from quant_sports_intel_models.football.ncaaf.ingest.cfbd_client import (
    CFBDAuthError,
    CFBDClient,
    CFBDContentError,
)
from quant_sports_intel_models.football.ncaaf.ingest import sources as src
from quant_sports_intel_models.football.ncaaf.ingest.handler import (
    _parse_seasons,
    _resolve_sources,
)


# ── fake requests plumbing (no network) ─────────────────────────────────────────────────
class _FakeResp:
    def __init__(self, status=200, ctype="application/json", body=None, text=""):
        self.status_code = status
        self.headers = {"Content-Type": ctype, "X-Calllimit-Remaining": "876"}
        self._body = body
        self.text = text or (json.dumps(body) if body is not None else "")

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return self._resp


def _client(resp):
    return CFBDClient(api_key="x", session=_FakeSession(resp))


# ── the landmine guard: a 200 text/html Swagger page must RAISE, not return HTML ─────────
def test_cfbd_html_page_raises_content_error():
    resp = _FakeResp(status=200, ctype="text/html; charset=utf-8", text="<!doctype html><html>swagger")
    with pytest.raises(CFBDContentError):
        _client(resp).get("/play/stats")  # the wrong singular path → HTML bundle


def test_cfbd_200_unparseable_body_raises():
    resp = _FakeResp(status=200, ctype="application/json", body=None, text="not json")
    with pytest.raises(CFBDContentError):
        _client(resp).get("/games")


def test_cfbd_valid_json_returns_and_tracks_budget():
    resp = _FakeResp(status=200, body=[{"id": 1}, {"id": 2}])
    c = _client(resp)
    out = c.get("/games", {"year": 2024})
    assert out == [{"id": 1}, {"id": 2}]
    assert c.last_calls_remaining == 876  # X-Calllimit-Remaining surfaced


def test_cfbd_tier_gate_401_raises_auth():
    resp = _FakeResp(status=401, text="requires a Patreon subscription at Tier 2")
    with pytest.raises(CFBDAuthError):
        _client(resp).get("/live/plays")


def test_cfbd_missing_key_raises():
    import os

    saved = os.environ.pop("CFBD_API_KEY", None)
    try:
        with pytest.raises(CFBDAuthError):
            CFBDClient(api_key=None)
    finally:
        if saved is not None:
            os.environ["CFBD_API_KEY"] = saved


def test_plays_requires_week():
    c = _client(_FakeResp(body=[]))
    with pytest.raises(ValueError):
        c.get_plays(2024, week=None)


def test_play_stats_cap_tripwire():
    # A response at/over the 2,000 cap means the pull truncated → must raise (forces per-game).
    resp = _FakeResp(body=[{"x": i} for i in range(2000)])
    with pytest.raises(Exception):
        _client(resp).get_play_stats_by_game(123)


# ── s3io pure logic ─────────────────────────────────────────────────────────────────────
def test_records_to_arrow_schema_and_rawjson():
    recs = [{"id": 1, "homeTeam": "A"}, {"id": 2, "homeTeam": "B"}]
    tbl = s3io.records_to_arrow(recs, source="games", season=2024, week=1)
    assert tbl.column_names == ["season", "week", "source", "ingested_at", "raw_json"]
    assert tbl.num_rows == 2
    assert tbl.column("season").to_pylist() == [2024, 2024]
    assert tbl.column("week").to_pylist() == [1, 1]
    # raw_json is a JSON string that round-trips
    assert json.loads(tbl.column("raw_json")[0].as_py())["homeTeam"] == "A"


def test_reject_unsigned_delta():
    tbl = pa.table({"season": pa.array([2024], pa.int64()), "u": pa.array([1], pa.uint64())})
    with pytest.raises(ValueError):
        s3io._reject_unsigned(tbl, "ctx")


def test_storage_options_never_empty_akid(monkeypatch):
    # An empty-string env key must NOT be forwarded (the object_store empty-AKID → 400 bug).
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    opts = s3io.storage_options()
    assert opts.get("AWS_ACCESS_KEY_ID", None) != ""  # either resolved-from-chain or absent


def test_table_uri_layout():
    uri = s3io.table_uri("ncaaf", "games", bucket="b")
    assert uri == "s3://b/ncaaf/raw/games"


# ── registry completeness ───────────────────────────────────────────────────────────────
def test_registry_has_24_locked_tables():
    assert len(src.SOURCES) == 24
    # spot-check the load-bearing ones from ncaaf_data_inventory.md §8
    for name in ["games", "play_stats", "cfbd_draft_picks", "odds_ncaaf",
                 "nflverse_draft_picks", "nflverse_players"]:
        assert name in src.SOURCES


def test_registry_groupings():
    assert "games" in src.CFBD_WEEKLY
    assert "odds_ncaaf" in src.ODDS_SOURCES
    assert set(src.NFLVERSE_SOURCES) == {
        "nflverse_draft_picks", "nflverse_combine", "nflverse_players"}
    # nflverse_players is not season-grained
    assert src.SOURCES["nflverse_players"].season_scoped is False


class _FakeCFBD:
    """Records calls; mimics CFBD requiring `week` for the week-grained endpoints (a
    year-only call raises, like the live 400 'either week, team, or conference are required')."""

    def __init__(self):
        self.calls = []

    def get_game_team_stats(self, year, week=None):
        if week is None:
            raise RuntimeError("400: week required")
        self.calls.append(("teams", week))
        return [{"team": "A", "week": week}]

    def get_game_player_stats(self, year, week=None):
        if week is None:
            raise RuntimeError("400: week required")
        self.calls.append(("players", week))
        return [{"player": "x", "week": week}]

    def get(self, path, params):
        if "week" not in params:
            raise RuntimeError("400: week required")
        self.calls.append((path, params["week"]))
        return [{"ppa": 1.0}]


def test_week_grained_fetchers_never_call_year_only():
    # game_team_stats / game_player_stats / ppa_players_games must loop weeks, never year-only
    # (the 2026-07-15 backfill 400). Scope to a couple weeks so the test is cheap.
    ctx = src.Ctx(cfbd=_FakeCFBD())
    for name in ["game_team_stats", "game_player_stats", "ppa_players_games"]:
        rows = src.SOURCES[name].fetch(ctx, 2024, weeks=[1, 2])
        assert len(rows) == 2, name
        assert all("_week" in r for r in rows), name
    # and with weeks=None the fetchers still loop the default weeks (no year-only fallback)
    ctx2 = src.Ctx(cfbd=_FakeCFBD())
    rows = src.SOURCES["game_team_stats"].fetch(ctx2, 2024)
    assert len(rows) == len(src._default_weeks())


def test_handler_parse_seasons():
    assert _parse_seasons("2024") == [2024]
    assert _parse_seasons("2014-2016") == [2014, 2015, 2016]
    assert _parse_seasons("2020,2022") == [2020, 2022]


def test_handler_resolve_sources_rejects_unknown():
    assert _resolve_sources(["games"]) == ["games"]
    with pytest.raises(ValueError):
        _resolve_sources(["not_a_source"])


# ── a real local Delta round-trip (write → delta_scan read-back), tiny & fast ────────────
def test_local_delta_roundtrip(tmp_path):
    recs = [{"id": 401, "homeTeam": "A"}, {"id": 402, "homeTeam": "B"}]
    n = s3io.write_records(
        recs, sport="ncaaf", source="games", season=2024, week=1,
        local_root=str(tmp_path),
    )
    assert n == 2
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL delta; LOAD delta")
    uri = s3io.local_table_uri(str(tmp_path), "ncaaf", "games")
    rows = con.execute(f"SELECT season, raw_json FROM delta_scan('{uri}') ORDER BY raw_json").fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 2024
    assert json.loads(rows[0][1])["homeTeam"] == "A"

    # idempotent re-write of the same season = value-identical (still 2 rows, not 4)
    s3io.write_records(recs, sport="ncaaf", source="games", season=2024, week=1,
                       local_root=str(tmp_path))
    cnt = con.execute(f"SELECT count(*) FROM delta_scan('{uri}')").fetchone()[0]
    assert cnt == 2
