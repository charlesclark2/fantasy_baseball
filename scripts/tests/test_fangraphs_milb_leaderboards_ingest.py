"""E7.7 — unit tests for the FanGraphs MiLB-leaderboard ingest (offline; FlareSolverr + S3 mocked).

The MiLB leaderboards are the `fg_minor_id` POPULATION feed (every minor leaguer, not just the
graded ones THE BOARD covers). Tests cover: the minor-league endpoint + inverted-season params,
pagination reuse, and the tolerant extraction (fg_minor_id/xMLBAMID + alt casing, HTML strip).
"""
import json

import pytest

import ingest_fangraphs_milb_leaderboards_to_s3 as il
from utils import fangraphs_client as fc


# ── fetch_minor_leaderboard (client) ─────────────────────────────────────────────

def test_minor_leaderboard_hits_minor_endpoint_and_inverts_season(monkeypatch):
    captured = {}

    def fake_get(url, params, max_timeout_ms=None):
        captured["url"] = url
        captured["params"] = params
        return ({"data": [{"playerid": "sa1", "xMLBAMID": "10"}]}, 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_minor_leaderboard(stats="bat", season=2026)

    assert captured["url"] == fc.MINOR_LEADERBOARD_URL
    assert "minor-league" in captured["url"]
    assert captured["params"]["season"] == 2026 and captured["params"]["season1"] == 2026
    assert captured["params"]["qual"] == "0"      # everyone (coverage default)
    assert captured["params"]["ind"] == "1"       # per player-season grain
    assert out["data"] == [{"playerid": "sa1", "xMLBAMID": "10"}]


def test_minor_leaderboard_paginates(monkeypatch):
    def fake_get(url, params, max_timeout_ms=None):
        pagenum = int(params["pagenum"])
        rows = [{"playerid": f"sa{i}"} for i in ([1, 2] if pagenum == 1 else [3])]
        return ({"data": rows}, 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_minor_leaderboard(stats="pit", season=2025, page_size=2)
    assert [r["playerid"] for r in out["data"]] == ["sa1", "sa2", "sa3"]


# ── extraction ───────────────────────────────────────────────────────────────────

def _extract(raw, stats="bat"):
    return il.extract_row(raw, season=2026, stats=stats, as_of_date="2026-07-27",
                          ingested_at="2026-07-27T12:00:00+00:00")


def test_extract_minor_row_real_casing():
    raw = {
        "playerid": "sa3012345", "xMLBAMID": 700123,
        "Name": '<a href="/players/x">Prospect Guy</a>',
        "Team": '<a href="/teams/y">BAL (AA)</a>', "aLevel": "AA",
        "Age": 21.3, "PA": 300, "K%": 0.22, "BB%": 0.10, "wRC+": 130,
    }
    r = _extract(raw)
    assert r["fg_minor_id"] == "sa3012345"
    assert r["mlbam_id"] == "700123"
    assert r["player_name"] == "Prospect Guy"          # HTML stripped
    assert r["team"] == "BAL (AA)"                       # HTML stripped
    assert r["level"] == "AA"
    assert r["age"] == 21.3
    assert r["pa"] == 300.0 and r["k_pct"] == 0.22 and r["wrc_plus"] == 130.0
    assert r["stats"] == "bat" and r["season"] == 2026
    assert json.loads(r["raw_json"])["playerid"] == "sa3012345"


def test_extract_pitcher_row_and_missing_stats_none():
    r = _extract({"playerid": "sa9", "ERA": 3.21, "IP": 55.2}, stats="pit")
    assert r["fg_minor_id"] == "sa9"
    assert r["era"] == 3.21 and r["ip"] == 55.2
    assert r["wrc_plus"] is None          # batter stat absent on a pitcher row → None, no crash
    assert r["mlbam_id"] is None


def test_extract_alt_casing_resolves():
    r = _extract({"minorMasterId": "m1", "mlbamid": "5", "PlayerName": "Foo", "Level": "A+"})
    assert r["fg_minor_id"] == "m1" and r["mlbam_id"] == "5"
    assert r["player_name"] == "Foo" and r["level"] == "A+"


# ── run() wiring: dry-run / probe make NO write; both stat groups iterate ────────

def test_dry_run_iterates_both_stats_without_write(monkeypatch):
    seen = []
    monkeypatch.setattr(il, "fetch_board",
                        lambda season, stats: seen.append(stats) or [{"playerid": "sa1"}])
    monkeypatch.setattr(il, "write_partition",
                        lambda *a, **k: pytest.fail("dry-run must not write"))
    il.run(season=2026, stats_groups=["bat", "pit"], as_of_date="2026-07-27",
           mode="dry-run", csv_path=None)
    assert seen == ["bat", "pit"]


def test_write_mode_calls_partition_per_stat(monkeypatch):
    monkeypatch.setattr(il, "fetch_board", lambda season, stats: [{"playerid": "sa1"}])
    calls = []
    monkeypatch.setattr(il, "write_partition",
                        lambda df, season, stats, as_of_date: calls.append((stats, len(df))) or len(df))
    il.run(season=2026, stats_groups=["bat", "pit"], as_of_date="2026-07-27",
           mode="write", csv_path=None)
    assert calls == [("bat", 1), ("pit", 1)]
