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

def test_minor_leaderboard_uses_minor_param_set(monkeypatch):
    """The minor board takes a DIFFERENT contract than the major one (a major-style request 404s):
    `seasonEnd` not `season1`, `type=0` not 8, plus `level`/`org`/`splitTeam`."""
    captured = {}

    def fake_get(url, params, max_timeout_ms=None):
        captured["url"] = url
        captured["params"] = params
        return ({"data": [{"playerid": "sa1", "xMLBAMID": "10"}]}, 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_minor_leaderboard(stats="bat", season=2026)

    assert captured["url"] == fc.MINOR_LEADERBOARD_URL and "minor-league" in captured["url"]
    p = captured["params"]
    assert p["season"] == 2026 and p["seasonEnd"] == 2026 and "season1" not in p
    assert p["type"] == 0 and "month" not in p            # minor set, not the major type=8/month
    assert p["level"] == "0" and p["splitTeam"] == "false"
    assert p["qual"] == "0"                                # everyone (coverage default)
    assert out["data"] == [{"playerid": "sa1", "xMLBAMID": "10"}]


def test_minor_leaderboard_endpoint_and_extra_params_override(monkeypatch):
    """Probe-driven overrides finalize the fragile contract without a code change."""
    captured = {}
    monkeypatch.setattr(fc, "_flaresolverr_get",
                        lambda url, params, max_timeout_ms=None: (captured.update(url=url, params=params) or ({"data": []}, 200)))
    fc.fetch_minor_leaderboard(stats="bat", season=2026,
                               url="https://x/api/other", extra_params={"lg": "2,4,5", "type": 3})
    assert captured["url"] == "https://x/api/other"
    assert captured["params"]["lg"] == "2,4,5" and captured["params"]["type"] == 3


def test_dedup_id_case_insensitive_and_idless_kept(monkeypatch):
    """Cross-page de-dup resolves the id case-insensitively over candidates (playerid /
    minorMasterId); a row with NO id key is kept (never collapse an id-less page to one row)."""
    assert fc._row_dedup_id({"PlayerId": "35376"}) == "35376"
    assert fc._row_dedup_id({"minorMasterId": "sa1"}) == "sa1"
    assert fc._row_dedup_id({"WAR": 2.0}) is None
    # A single page of id-less rows must all survive.
    monkeypatch.setattr(fc, "_flaresolverr_get",
                        lambda url, params, max_timeout_ms=None: ({"data": [{"WAR": 1}, {"WAR": 2}]}, 200))
    out = fc.fetch_minor_leaderboard(stats="bat", season=2026, page_size=500)
    assert len(out["data"]) == 2


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
                        lambda season, stats, **kw: seen.append(stats) or [{"playerid": "sa1"}])
    monkeypatch.setattr(il, "write_partition",
                        lambda *a, **k: pytest.fail("dry-run must not write"))
    il.run(season=2026, stats_groups=["bat", "pit"], as_of_date="2026-07-27",
           mode="dry-run", csv_path=None)
    assert seen == ["bat", "pit"]


def test_write_mode_calls_partition_per_stat(monkeypatch):
    monkeypatch.setattr(il, "fetch_board", lambda season, stats, **kw: [{"playerid": "sa1"}])
    calls = []
    monkeypatch.setattr(il, "write_partition",
                        lambda df, season, stats, as_of_date: calls.append((stats, len(df))) or len(df))
    il.run(season=2026, stats_groups=["bat", "pit"], as_of_date="2026-07-27",
           mode="write", csv_path=None)
    assert calls == [("bat", 1), ("pit", 1)]
