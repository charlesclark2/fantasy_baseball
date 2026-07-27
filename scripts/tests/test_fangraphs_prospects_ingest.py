"""E7.7 — unit tests for the FanGraphs THE BOARD ingest (offline; FlareSolverr + S3 mocked).

Covers the two risk surfaces:
  • fetch_prospects_board builds the right params (draft default, None dropped) and normalises
    both the bare-list and {"data": [...]} payload shapes;
  • the tolerant, case-insensitive extraction survives whatever casing FanGraphs returns
    (playerid/xMLBAMID and alt casings), strips embedded HTML, parses FV grades, and NEVER
    silently zeroes the join keys (the column-name-reality discipline).
"""
import json

import pytest

import ingest_fangraphs_prospects_to_s3 as ip
from utils import fangraphs_client as fc


# ── fetch_prospects_board (client) ───────────────────────────────────────────────

def test_fetch_board_params_and_default_draft(monkeypatch):
    captured = {}

    def fake_get(url, params, max_timeout_ms=None):
        captured["url"] = url
        captured["params"] = params
        return ([{"playerid": "1"}], 200)

    monkeypatch.setattr(fc, "_flaresolverr_get", fake_get)
    out = fc.fetch_prospects_board(season=2026)

    assert captured["url"] == fc.PROSPECT_BOARD_URL
    assert captured["params"]["draft"] == "2026prospect"      # default slug
    assert captured["params"]["season"] == 2026
    assert "type" not in captured["params"] and "pos" not in captured["params"]  # None dropped
    assert out["data"] == [{"playerid": "1"}]
    assert out["http_status_code"] == 200


def test_fetch_board_normalises_dict_wrapper(monkeypatch):
    monkeypatch.setattr(fc, "_flaresolverr_get",
                        lambda url, params, max_timeout_ms=None: ({"data": [{"playerid": "9"}]}, 200))
    out = fc.fetch_prospects_board(season=2025, draft="2025mlb")
    assert out["data"] == [{"playerid": "9"}]
    assert out["request_params"]["draft"] == "2025mlb"


# ── extraction (the column-name-reality core) ────────────────────────────────────

def _extract(raw):
    return ip.extract_row(raw, season=2026, as_of_date="2026-07-27",
                          board_slug="2026prospect", ingested_at="2026-07-27T12:00:00+00:00")


def test_extract_real_board_row_casing():
    """The VERIFIED live board casing (2026-07-27 box probe, Konnor Griffin row): the stable id is
    `minorMasterId` (sa-prefixed) — it must WIN over `PlayerId` (the numeric MLB id for a
    graduate); `cRisk`/`cETA`/`cFV`; and there is NO MLBAM id on the board (→ None by design)."""
    raw = {
        "minorMasterId": "sa3065496",
        "PlayerId": "35376", "UPID": "35376",   # numeric FG/MLB id — NOT the stable minor id
        "playerName": "Konnor Griffin",
        "Team": "PIT", "Position": "SS", "mlevel": "MLB",
        "cFV": "70", "FV_Current": 70, "cRisk": "High", "cETA": "2026", "ETA_Current": 2026,
        "Ovr_Rank": 1, "Org_Rank": 1, "Age": "18.9361111",
        "Fantasy_Dynasty": 3, "Fantasy_Redraft": 120, "TLDR": "Best prospect in baseball.",
    }
    r = _extract(raw)
    assert r["fg_minor_id"] == "sa3065496"        # minorMasterId WINS over PlayerId
    assert r["fg_player_id"] == "35376"           # the FG unified id kept separately
    assert r["mlbam_id"] is None                   # board exposes none — bridge via leaderboard/xref
    assert r["player_name"] == "Konnor Griffin"
    assert r["org"] == "PIT" and r["position"] == "SS" and r["level"] == "MLB"
    assert r["fv"] == 70.0 and r["risk"] == "High" and r["eta"] == 2026
    assert r["overall_rank"] == 1 and r["org_rank"] == 1
    assert round(r["age"], 2) == 18.94
    assert r["fantasy_dynasty_rank"] == 3 and r["fantasy_redraft_rank"] == 120
    assert r["tldr"] == "Best prospect in baseball."
    assert json.loads(r["raw_json"])["minorMasterId"] == "sa3065496"


def test_extract_xmlbamid_resolves_when_present():
    """If a feed DOES carry an MLBAM id (e.g. the leaderboards), the alias picks it up."""
    r = _extract({"minorMasterId": "sa1", "xMLBAMID": 691718})
    assert r["fg_minor_id"] == "sa1" and r["mlbam_id"] == "691718"


def test_extract_alt_casing_still_resolves():
    """A drifted casing (minorMasterId / mlbamid / futureValue) still resolves via aliases."""
    raw = {"minorMasterId": "m42", "mlbamid": "111", "PlayerName": "Foo Bar",
           "Team": "NYY", "Position": "RHP", "FV": "55+", "eta": "2027"}
    r = _extract(raw)
    assert r["fg_minor_id"] == "m42"
    assert r["mlbam_id"] == "111"
    assert r["player_name"] == "Foo Bar"
    assert r["org"] == "NYY"
    assert r["fv"] == 55.0          # trailing '+' stripped
    assert r["fv_raw"] == "55+"     # raw grade preserved
    assert r["eta"] == 2027


def test_extract_missing_fields_are_none_not_crash():
    r = _extract({"playerid": "z1"})
    assert r["fg_minor_id"] == "z1"
    assert r["mlbam_id"] is None
    assert r["fv"] is None
    assert r["overall_rank"] is None
    assert r["season"] == 2026 and r["as_of_date"] == "2026-07-27"


def test_resolve_as_of_date_historical_safeguard():
    """A historical --season pull with no --as-of must NOT stamp TODAY (would poison E7.8's
    time-series) — it stamps a mid-season approx and flags is_historical_guess."""
    # explicit --as-of wins verbatim
    assert ip.resolve_as_of_date("2020-04-01", 2020, 2026, "2026-07-27") == ("2020-04-01", False)
    # current season → today's game day
    assert ip.resolve_as_of_date(None, 2026, 2026, "2026-07-27") == ("2026-07-27", False)
    # past season, no --as-of → mid-season approx + historical flag (main() warns)
    assert ip.resolve_as_of_date(None, 2020, 2026, "2026-07-27") == ("2020-07-01", True)


def test_numeric_parsers():
    assert ip._to_float("50+") == 50.0
    assert ip._to_float(60) == 60.0
    assert ip._to_float("") is None
    assert ip._to_float(None) is None
    assert ip._to_int("2026") == 2026
    assert ip._clean_str("<a>X</a>") == "X"
    assert ip._clean_str("  ") is None


# ── run() wiring: dry-run makes NO S3 write; probe writes nothing ────────────────

def test_dry_run_builds_rows_without_write(monkeypatch):
    monkeypatch.setattr(ip, "fetch_board", lambda season, draft: [
        {"playerid": "1", "xMLBAMID": "10", "Name": "A", "cFV": 50},
        {"playerid": "2", "xMLBAMID": "20", "Name": "B", "cFV": 55},
    ])
    called = {"write": False}
    monkeypatch.setattr(ip, "write_partition", lambda *a, **k: called.__setitem__("write", True))

    ip.run(season=2026, draft=None, as_of_date="2026-07-27", mode="dry-run", csv_path=None)
    assert called["write"] is False


def test_probe_writes_nothing(monkeypatch):
    monkeypatch.setattr(ip, "fetch_board", lambda season, draft: [{"playerid": "1", "cFV": 50}])
    monkeypatch.setattr(ip, "write_partition",
                        lambda *a, **k: pytest.fail("probe must not write"))
    ip.run(season=2026, draft=None, as_of_date="2026-07-27", mode="probe", csv_path=None)


def test_write_mode_calls_partition_write(monkeypatch):
    monkeypatch.setattr(ip, "fetch_board", lambda season, draft: [{"playerid": "1", "cFV": 50}])
    captured = {}

    def fake_write(df, season, as_of_date):
        captured["rows"] = len(df)
        captured["season"] = season
        captured["as_of_date"] = as_of_date
        return len(df)

    monkeypatch.setattr(ip, "write_partition", fake_write)
    ip.run(season=2026, draft=None, as_of_date="2026-07-27", mode="write", csv_path=None)
    assert captured == {"rows": 1, "season": 2026, "as_of_date": "2026-07-27"}
