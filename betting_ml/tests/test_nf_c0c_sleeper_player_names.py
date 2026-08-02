"""Fast-gate tests for NF-C0c — SLEEPER PLAYER-FILE INGEST + roster/draft NAME RESOLUTION.

Three layers, one per section:

1. `sleeper_players_source` — the offline fetch/crosswalk/slim/coverage pipeline
   (`run_sleeper_player_ingest.py`'s engine). Mirrors the existing `sleeper_injuries_source` test
   pattern (same repo, same shape: native gsis_id preferred, name+position crosswalk fallback only
   for skill positions, played_flag never a filter).
2. `app.backend.services.platform_import.sleeper_players` — the READ side: a memoized load that
   must fetch AT MOST ONCE, and must tell "no name cache available" apart from "checked, no match"
   (an empty/failed read must never look like "these ids genuinely have no names").
3. `sleeper._fetch_teams` — the wiring: names/positions/teams populate when resolved, the "IDs
   only" warning is removed only when every rostered player actually resolved, a PARTIAL match gets
   a scoped honest warning naming the count, and a totally unavailable name cache keeps the original
   warning text unchanged (back-compat with NF-C0's existing behavior).

Fast-gate discipline: pure imports, no `pipeline`, no real network/S3 (boto3 calls are never reached
because tests never set CACHE_BUCKET — `sleeper_players._fetch()` short-circuits to None).
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

sp = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.sleeper_players_source")

from app.backend.services.platform_import import canonical as C  # noqa: E402
from app.backend.services.platform_import import sleeper, sleeper_players  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. sleeper_players_source — offline fetch / crosswalk / slim / coverage
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestFetchAllSleeperPlayers:
    def test_fetch_is_unfiltered_by_position_unlike_the_skill_only_siblings(self, tmp_path):
        """Unlike adp_source/sleeper_injuries_source (QB/RB/WR/TE only), this module must keep K/DEF/
        IDP rows too — an imported roster can carry any of them (sleeper.ROSTER_SLOT_MAP) and every
        slot needs a readable name, even though only skill positions get a gsis crosswalk attempt."""
        payload = {
            "1": {"first_name": "Cam", "last_name": "Akers", "position": "RB", "team": "MIN",
                  "gsis_id": "00-0036223", "years_exp": 5},
            "2": {"first_name": "Justin", "last_name": "Tucker", "position": "K", "team": "BAL",
                  "gsis_id": "00-0030001", "years_exp": 13},
            "SEA": {"full_name": None, "first_name": "Seattle", "last_name": "Seahawks",
                    "position": "DEF", "team": "SEA", "gsis_id": None, "years_exp": None},
        }
        (tmp_path / "sleeper_players_full_2026-08-01.json").write_text(json.dumps(payload))
        df = sp.fetch_all_sleeper_players(cache_dir=tmp_path, as_of="2026-08-01")
        assert sorted(df["position"].unique()) == ["DEF", "K", "RB"]
        seahawks = df[df["sleeper_player_id"] == "SEA"].iloc[0]
        assert seahawks["player_name"] == "Seattle Seahawks"  # first+last fallback, no full_name

    def test_a_player_with_no_derivable_name_is_dropped(self, tmp_path):
        payload = {"1": {"position": "RB", "team": None}}  # no full_name, no first/last, no team
        (tmp_path / "sleeper_players_full_2026-08-01.json").write_text(json.dumps(payload))
        df = sp.fetch_all_sleeper_players(cache_dir=tmp_path, as_of="2026-08-01")
        assert df.empty

    def test_cache_is_reused_within_the_same_day(self, tmp_path):
        cache = tmp_path / "sleeper_players_full_2026-08-01.json"
        cache.write_text(json.dumps({"1": {"full_name": "Cached Guy", "position": "RB"}}))
        df = sp.fetch_all_sleeper_players(cache_dir=tmp_path, as_of="2026-08-01")
        assert df.iloc[0]["player_name"] == "Cached Guy"


class TestAttachGsis:
    def test_native_gsis_wins_and_the_crosswalk_is_never_called_for_it(self, monkeypatch):
        df = pd.DataFrame({
            "sleeper_player_id": ["1", "2"], "player_name": ["Native Guy", "Fallback Guy"],
            "position": ["RB", "WR"], "team": ["MIN", "KC"], "gsis_id": ["00-0036223", None],
            "years_exp": [5, 0],
        })
        calls = []

        def _fake_crosswalk(con, sub, season, schema="main_nfl_marts"):
            calls.append(list(sub["player_name"]))
            out = sub.copy()
            out["player_id"] = ["00-0099999" for _ in range(len(out))]
            return out

        monkeypatch.setattr(sp.A, "attach_gsis", _fake_crosswalk)
        out = sp.attach_gsis(None, df, 2026)
        assert out.loc[out["player_name"] == "Native Guy", "gsis_id"].iloc[0] == "00-0036223"
        assert out.loc[out["player_name"] == "Fallback Guy", "gsis_id"].iloc[0] == "00-0099999"
        assert calls == [["Fallback Guy"]]  # crosswalk called ONLY on the missing-gsis skill subset

    def test_non_skill_positions_are_never_crosswalked(self, monkeypatch):
        """K/DST/IDP rows keep whatever Sleeper gave them (usually null) — fct_player_week has
        nothing to crosswalk them against, and calling the crosswalk on them would be a no-op at
        best and a wrong-population match at worst."""
        df = pd.DataFrame({
            "sleeper_player_id": ["1"], "player_name": ["Some Kicker"], "position": ["K"],
            "team": ["SF"], "gsis_id": [None], "years_exp": [3],
        })
        called = []
        monkeypatch.setattr(sp.A, "attach_gsis", lambda *a, **k: called.append(1))
        out = sp.attach_gsis(None, df, 2026)
        assert not called
        assert pd.isna(out.iloc[0]["gsis_id"])

    def test_empty_frame_is_handled(self):
        df = pd.DataFrame(columns=sp._FETCH_COLS)
        out = sp.attach_gsis(None, df, 2026)
        assert out.empty and "gsis_id" in out.columns


class TestSlimArtifact:
    def test_slim_artifact_keys_by_sleeper_id_and_drops_years_exp(self):
        df = pd.DataFrame({
            "sleeper_player_id": ["1", "2"], "player_name": ["Cam Akers", "No Gsis Guy"],
            "position": ["RB", "WR"], "team": ["MIN", "KC"], "gsis_id": ["00-0036223", None],
            "years_exp": [5, 0],
        })
        out = sp.slim_artifact(df)
        assert out["1"] == {"name": "Cam Akers", "position": "RB", "team": "MIN", "gsis_id": "00-0036223"}
        assert "gsis_id" not in out["2"]  # never emit a null/blank gsis_id key
        assert "years_exp" not in out["1"]

    def test_rows_missing_id_or_name_are_skipped(self):
        df = pd.DataFrame({
            "sleeper_player_id": ["", "2"], "player_name": ["Nameless", ""],
            "position": ["RB", "WR"], "team": ["MIN", "KC"], "gsis_id": [None, None],
            "years_exp": [0, 0],
        })
        assert sp.slim_artifact(df) == {}


class TestCoverage:
    def test_coverage_reports_skill_overall_and_rookies_separately(self):
        df = pd.DataFrame({
            "sleeper_player_id": ["1", "2", "3", "4"],
            "player_name": ["Vet Matched", "Vet Unmatched", "Rookie Matched", "Rookie Unmatched"],
            "position": ["RB", "WR", "RB", "WR"], "team": ["MIN", "KC", "SF", "DAL"],
            "gsis_id": ["00-1", None, "00-2", None],
            "years_exp": [5, 4, 0, 0],
        })
        cov = sp.coverage(df)
        assert cov["skill_overall"] == {"n": 4, "n_matched": 2, "pct_matched": 50.0}
        assert cov["skill_rookies"] == {"n": 2, "n_matched": 1, "pct_matched": 50.0}

    def test_non_skill_rows_are_excluded_from_both_rates(self):
        df = pd.DataFrame({
            "sleeper_player_id": ["1"], "player_name": ["A Kicker"], "position": ["K"],
            "team": ["SF"], "gsis_id": [None], "years_exp": [3],
        })
        cov = sp.coverage(df)
        assert cov["n_rows"] == 1
        assert cov["skill_overall"] == {"n": 0, "n_matched": 0, "pct_matched": 0.0}


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. app.backend.services.platform_import.sleeper_players — the memoized read
# ══════════════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_sleeper_players_cache():
    sleeper_players.reset_cache()
    yield
    sleeper_players.reset_cache()


class TestSleeperPlayersRead:
    def test_unconfigured_environment_reports_not_loaded_not_empty_dict(self, monkeypatch):
        """No CACHE_BUCKET and no FANTASY_BOARD_DIR — the default test environment. Must return
        artifact_loaded=False, never a silently-empty {} that would look like 'checked, no names'."""
        monkeypatch.setattr(sleeper_players, "_CACHE_BUCKET", None)
        monkeypatch.setattr(sleeper_players, "_LOCAL_BOARD_DIR", None)
        matches, loaded = sleeper_players.resolve(["1", "2"])
        assert matches == {} and loaded is False

    def test_local_dir_load_resolves_known_ids_and_ignores_unknown_ones(self, tmp_path, monkeypatch):
        sleeper_dir = tmp_path / "sleeper"
        sleeper_dir.mkdir()
        (sleeper_dir / "players.json").write_text(json.dumps({
            "100": {"name": "Ashton Jeanty", "position": "RB", "team": "LV", "gsis_id": "00-9"},
        }))
        monkeypatch.setattr(sleeper_players, "_LOCAL_BOARD_DIR", str(tmp_path))
        matches, loaded = sleeper_players.resolve(["100", "200"])
        assert loaded is True
        assert matches == {"100": {"name": "Ashton Jeanty", "position": "RB", "team": "LV", "gsis_id": "00-9"}}
        assert "200" not in matches  # unknown id: simply absent, not an error

    def test_an_empty_but_successfully_loaded_artifact_still_reports_not_loaded(self, tmp_path, monkeypatch):
        """A `{}` artifact is indistinguishable from a bad read at the call site — resolve() must
        treat it the same as 'unavailable' so a caller never renders a whole roster unmatched off
        what looks like a completed-but-empty read."""
        sleeper_dir = tmp_path / "sleeper"
        sleeper_dir.mkdir()
        (sleeper_dir / "players.json").write_text(json.dumps({}))
        monkeypatch.setattr(sleeper_players, "_LOCAL_BOARD_DIR", str(tmp_path))
        matches, loaded = sleeper_players.resolve(["1"])
        assert matches == {} and loaded is False

    def test_load_is_memoized_across_multiple_resolve_calls(self, tmp_path, monkeypatch):
        sleeper_dir = tmp_path / "sleeper"
        sleeper_dir.mkdir()
        (sleeper_dir / "players.json").write_text(json.dumps({
            "1": {"name": "A", "position": "RB", "team": "MIN"},
        }))
        monkeypatch.setattr(sleeper_players, "_LOCAL_BOARD_DIR", str(tmp_path))

        calls = []
        real_fetch = sleeper_players._fetch

        def _counted_fetch():
            calls.append(1)
            return real_fetch()

        monkeypatch.setattr(sleeper_players, "_fetch", _counted_fetch)
        sleeper_players.resolve(["1"])
        sleeper_players.resolve(["1"])
        sleeper_players.resolve(["1"])
        assert len(calls) == 1  # ONE fetch, not one per resolve() call (E9.26b narrow-read discipline)

    def test_a_corrupt_local_file_is_treated_as_unavailable_not_a_crash(self, tmp_path, monkeypatch):
        sleeper_dir = tmp_path / "sleeper"
        sleeper_dir.mkdir()
        (sleeper_dir / "players.json").write_text("{not valid json")
        monkeypatch.setattr(sleeper_players, "_LOCAL_BOARD_DIR", str(tmp_path))
        matches, loaded = sleeper_players.resolve(["1"])
        assert matches == {} and loaded is False


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. sleeper._fetch_teams — the wiring: names fill in, warnings stay honest
# ══════════════════════════════════════════════════════════════════════════════════════════════════

SLEEPER_LEAGUE = {
    "league_id": "1182033380414181376", "name": "Sunday Funday", "season": "2025", "sport": "nfl",
    "status": "complete", "total_rosters": 12,
    "roster_positions": ["QB", "RB", "WR", "TE", "BN"],
    "settings": {"num_teams": 12, "type": 2},
    "scoring_settings": {"pass_yd": 0.04, "rec": 1.0},
}


def _import_sleeper(monkeypatch, *, rosters):
    def fake_get_json(url, **_):
        if url.endswith("/rosters"):
            return rosters
        if url.endswith("/users"):
            return [{"user_id": "u1", "display_name": "Owner", "metadata": {}}]
        if url.endswith("/drafts"):
            return []
        return SLEEPER_LEAGUE

    monkeypatch.setattr(sleeper, "get_json", fake_get_json)
    return sleeper.import_league(SLEEPER_LEAGUE["league_id"], include_draft=False)


class TestFetchTeamsWiring:
    ROSTERS = [{"roster_id": 1, "owner_id": "u1", "players": ["100", "200"], "starters": ["100"]}]

    def test_all_matched_removes_the_ids_only_warning_entirely(self, monkeypatch):
        monkeypatch.setattr(
            sleeper_players, "resolve",
            lambda ids: (
                {
                    "100": {"name": "Ashton Jeanty", "position": "RB", "team": "LV"},
                    "200": {"name": "Some Other Guy", "position": "WR", "team": "KC"},
                },
                True,
            ),
        )
        result = _import_sleeper(monkeypatch, rosters=self.ROSTERS)
        players = {p.player_key: p for p in result.teams[0].players}
        assert players["100"].name == "Ashton Jeanty" and players["100"].position == "RB"
        assert players["100"].starter is True and players["200"].starter is False
        assert not any("player IDs" in w or "rostered players" in w for w in result.warnings)

    def test_partial_match_names_what_it_can_and_discloses_a_count(self, monkeypatch):
        monkeypatch.setattr(
            sleeper_players, "resolve",
            lambda ids: ({"100": {"name": "Ashton Jeanty", "position": "RB", "team": "LV"}}, True),
        )
        result = _import_sleeper(monkeypatch, rosters=self.ROSTERS)
        players = {p.player_key: p for p in result.teams[0].players}
        assert players["100"].name == "Ashton Jeanty"
        assert players["200"].name == ""  # unresolved: honestly empty, not fabricated
        assert any("1 of 2 rostered players" in w for w in result.warnings)

    def test_unavailable_name_cache_keeps_the_original_ids_only_warning(self, monkeypatch):
        monkeypatch.setattr(sleeper_players, "resolve", lambda ids: ({}, False))
        result = _import_sleeper(monkeypatch, rosters=self.ROSTERS)
        players = {p.player_key: p for p in result.teams[0].players}
        assert players["100"].name == "" and players["200"].name == ""
        assert any("player IDs without names" in w for w in result.warnings)

    def test_a_league_with_no_rostered_players_gets_no_roster_warning(self, monkeypatch):
        monkeypatch.setattr(sleeper_players, "resolve", lambda ids: ({}, False))
        result = _import_sleeper(
            monkeypatch, rosters=[{"roster_id": 1, "owner_id": "u1", "players": [], "starters": []}]
        )
        assert not any(
            "player IDs" in w or "rostered players" in w for w in result.warnings
        )

    def test_resolve_is_called_once_with_the_union_of_every_teams_player_ids(self, monkeypatch):
        seen = {}

        def _fake_resolve(ids):
            seen["ids"] = set(ids)
            return {}, True

        monkeypatch.setattr(sleeper_players, "resolve", _fake_resolve)
        rosters = [
            {"roster_id": 1, "owner_id": "u1", "players": ["100", "200"], "starters": []},
            {"roster_id": 2, "owner_id": "u2", "players": ["200", "300"], "starters": []},
        ]
        _import_sleeper(monkeypatch, rosters=rosters)
        assert seen["ids"] == {"100", "200", "300"}  # de-duplicated across teams, one call
