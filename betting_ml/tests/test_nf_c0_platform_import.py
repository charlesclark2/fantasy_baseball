"""Fast-gate tests for NF-C0 — PLATFORM LEAGUE IMPORT (Sleeper + Yahoo).

Five things have to hold for this story, and each is a section below.

1. **THERE IS ONE CONFIG SCHEMA, NOT TWO.** The whole story rests on an imported league and a
   hand-entered (NF-C0b) league being the IDENTICAL object. The backend cannot import
   `fantasy_engine` (the Lambda bundles neither it nor pandas/numpy), so `platform_import.canonical`
   restates the shape — and a silent drift between the two would defeat the story while every test
   still passed. So every adapter's output is fed through the REAL `LeagueConfig.from_dict()`, must
   round-trip BYTE-IDENTICAL through `to_dict()`, and must also satisfy the backend's own
   `LeagueSave` pydantic model. Three independent restatements, pinned to each other.

2. **AN UNMAPPED SCORING TERM IS CARRIED, NOT DROPPED.** A platform scores things we do not project.
   Dropping those keys would make the config look clean and make the board silently ignore a rule
   the league really has — precisely the failure NF-C0b's coverage machinery exists to prevent. They
   must survive to `resolve_scoring` and land as CAPTURED.

3. **THE COARSE→FINE FAN-OUT IS EXACT, AND THE FINE→COARSE FOLD IS DECLARED.** A platform's 7-tier
   points-allowed table restates exactly on our nine buckets (both halves take the same weight);
   a 6-bucket FG table folds onto our three and `resolve_scoring` reports whether that was lossless.
   Getting either backwards silently changes a user's scoring.

4. **THE RED LINE IS STRUCTURAL, NOT ASPIRATIONAL.** No import path may accept, store or replay a
   platform password. That is asserted against the SOURCE, so a future adapter cannot quietly add a
   password field and still ship green.

5. **EVERY ROUTE IS ENTITLEMENT-GATED, EXCEPT THE ONE THAT PROVABLY CANNOT BE.** The Yahoo OAuth
   callback is entered by a browser redirect with no bearer token; its authentication is the signed
   `state`. That exemption must stay exactly one route, and the signature must actually reject a
   tampered/expired/foreign state.

Fast-gate discipline: pure imports, no `pipeline`, no network. Every platform payload here is a
FIXTURE captured from the real APIs (Sleeper's shapes were taken from a live 2026-08-01 read of
league 1182033380414181376; Yahoo's from its published resource documentation).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest

lc = pytest.importorskip("quant_sports_intel_models.fantasy_engine.league_config")
presets = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.league_presets")
settings_mod = pytest.importorskip("quant_sports_intel_models.fantasy_engine.settings")

from app.backend.models.fantasy import LeagueSave  # noqa: E402
from app.backend.services.platform_import import canonical as C  # noqa: E402
from app.backend.services.platform_import import sleeper, yahoo, yahoo_oauth  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
IMPORT_PKG = REPO / "app" / "backend" / "services" / "platform_import"
ROUTER = REPO / "app" / "backend" / "routers" / "fantasy_import.py"

APPLIED, DERIVED, CAPTURED = settings_mod.APPLIED, settings_mod.DERIVED, settings_mod.CAPTURED


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Fixtures — real payload SHAPES, not invented ones
# ══════════════════════════════════════════════════════════════════════════════════════════════════

# Captured from Sleeper league 1182033380414181376 on 2026-08-01 (a live 12-team superflex dynasty),
# trimmed to the fields the adapter reads. `roster_positions` is one entry PER SEAT — the shape that
# makes `collapse_slots` necessary — and `settings` carries IR/taxi counts that `roster_positions`
# does NOT list, which is the omission a naive importer loses.
SLEEPER_LEAGUE = {
    "league_id": "1182033380414181376",
    "name": "Sunday Funday",
    "season": "2025",
    "sport": "nfl",
    "status": "complete",
    "total_rosters": 12,
    "draft_id": "1182033380414181377",
    "roster_positions": [
        "QB", "RB", "RB", "WR", "WR", "WR", "TE", "TE",
        "FLEX", "FLEX", "FLEX", "SUPER_FLEX",
        *["BN"] * 15,
    ],
    "settings": {
        "num_teams": 12,
        "type": 2,             # dynasty
        "best_ball": 0,
        "league_average_match": 0,
        "playoff_week_start": 15,
        "max_keepers": 1,
        "reserve_slots": 3,    # IR — absent from roster_positions
        "taxi_slots": 5,       # taxi — absent from roster_positions
    },
    "scoring_settings": {
        "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0,
        "rush_yd": 0.1, "rush_td": 6.0,
        "rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0,
        "fum_lost": -2.0, "fum_rec_td": 6.0,
        "pass_2pt": 2.0, "rush_2pt": 2.0, "rec_2pt": 2.0,
        "fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0,
        "fgm_40_49": 4.0, "fgm_50p": 5.0, "fgmiss": -1.0,
        "xpm": 1.0, "xpmiss": -1.0,
        "sack": 1.0, "int": 2.0, "fum_rec": 2.0, "ff": 1.0,
        "safe": 2.0, "blk_kick": 2.0, "def_td": 6.0, "def_st_td": 6.0, "st_td": 6.0,
        "pts_allow_0": 10.0, "pts_allow_1_6": 7.0, "pts_allow_7_13": 4.0,
        "pts_allow_14_20": 1.0, "pts_allow_21_27": 0.0,
        "pts_allow_28_34": -1.0, "pts_allow_35p": -4.0,
        # genuinely unmapped (we do not project these) — must survive as CAPTURED
        "st_ff": 1.0, "st_fum_rec": 1.0, "def_st_ff": 1.0,
        # a zeroed term is a non-statement and must NOT be reported as captured
        "fum": 0.0,
    },
}

# Yahoo's settings resource, in its real nested/fragmented idiom: `fantasy_content.league` is an
# ARRAY whose members are partial objects, and collections are numeric-keyed dicts with a sibling
# `count`. Parsing this positionally is what breaks on first contact; the adapter walks it instead.
YAHOO_SETTINGS = {
    "fantasy_content": {
        "league": [
            {
                "league_key": "461.l.1000",
                "name": "Test Yahoo League",
                "season": "2025",
                "num_teams": "10",
                "scoring_type": "head",
            },
            {
                "settings": [
                    {
                        "uses_playoff": "1",
                        "playoff_start_week": "15",
                        "uses_fractional_points": "1",
                        "roster_positions": [
                            {"roster_position": {"position": "QB", "count": 1}},
                            {"roster_position": {"position": "RB", "count": 2}},
                            {"roster_position": {"position": "WR", "count": 3}},
                            {"roster_position": {"position": "TE", "count": 1}},
                            {"roster_position": {"position": "W/R/T", "count": 1}},
                            {"roster_position": {"position": "K", "count": 1}},
                            {"roster_position": {"position": "DEF", "count": 1}},
                            {"roster_position": {"position": "BN", "count": 6}},
                            {"roster_position": {"position": "IR", "count": 2}},
                        ],
                        "stat_modifiers": {
                            "stats": [
                                {"stat": {"stat_id": "4", "value": "0.04"}},
                                {"stat": {"stat_id": "5", "value": "4"}},
                                {"stat": {"stat_id": "6", "value": "-1"}},    # INT thrown
                                {"stat": {"stat_id": "9", "value": "0.1"}},
                                {"stat": {"stat_id": "10", "value": "6"}},
                                {"stat": {"stat_id": "11", "value": "0.5"}},  # half PPR
                                {"stat": {"stat_id": "12", "value": "0.1"}},
                                {"stat": {"stat_id": "13", "value": "6"}},
                                {"stat": {"stat_id": "18", "value": "-2"}},
                                {"stat": {"stat_id": "19", "value": "3"}},
                                {"stat": {"stat_id": "22", "value": "4"}},
                                {"stat": {"stat_id": "23", "value": "5"}},    # FG 50+ → two buckets
                                {"stat": {"stat_id": "29", "value": "1"}},
                                {"stat": {"stat_id": "32", "value": "1"}},
                                {"stat": {"stat_id": "33", "value": "2"}},    # INT by a DEFENSE
                                {"stat": {"stat_id": "53", "value": "1"}},    # PA 14-20 → two buckets
                                {"stat": {"stat_id": "56", "value": "-4"}},   # PA 35+ → two buckets
                                {"stat": {"stat_id": "9999", "value": "3"}},  # unknown → captured
                            ]
                        },
                    }
                ]
            },
        ]
    }
}


def _import_sleeper(monkeypatch, league=None, *, with_state=False):
    """Run the Sleeper adapter against fixtures with every HTTP call stubbed."""
    league = league or SLEEPER_LEAGUE

    def fake_get_json(url, **_):
        if url.endswith("/rosters"):
            return [{"roster_id": 1, "owner_id": "u1", "players": ["100", "200"], "starters": ["100"]}]
        if url.endswith("/users"):
            return [{"user_id": "u1", "display_name": "Owner", "metadata": {"team_name": "The Team"}}]
        if url.endswith("/drafts"):
            return [{"draft_id": "d1", "start_time": 1749736837326, "status": "complete",
                     "type": "linear", "settings": {"rounds": 3}}]
        if "/draft/" in url and url.endswith("/picks"):
            return [{"pick_no": 1, "round": 1, "roster_id": 6, "player_id": "12527",
                     "metadata": {"first_name": "Ashton", "last_name": "Jeanty",
                                  "position": "RB", "team": "LV"}}]
        return league

    monkeypatch.setattr(sleeper, "get_json", fake_get_json)
    return sleeper.import_league(league["league_id"], include_draft=with_state)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. ONE SCHEMA — the imported config IS the engine's LeagueConfig
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestSharedConfigContract:
    """The story's central claim, pinned three ways.

    This is the test that would catch the story quietly failing: an import that produces a config
    the engine cannot read, or that the engine reads DIFFERENTLY from how it was written, breaks
    "an imported league and a typed-in league are the identical object" while every adapter unit
    test still passes.
    """

    def test_sleeper_config_is_accepted_by_the_real_engine(self, monkeypatch):
        result = _import_sleeper(monkeypatch)
        cfg = lc.LeagueConfig.from_dict(result.config)  # raises if the engine rejects it
        assert cfg.name == "Sunday Funday"
        assert cfg.n_teams == 12

    def test_sleeper_config_round_trips_byte_identical(self, monkeypatch):
        result = _import_sleeper(monkeypatch)
        assert lc.LeagueConfig.from_dict(result.config).to_dict() == result.config

    def test_sleeper_config_satisfies_the_backend_save_model(self, monkeypatch):
        # The API's own pydantic restatement is a THIRD independent copy of the shape; an import
        # the engine accepts but the API rejects could never actually be saved.
        result = _import_sleeper(monkeypatch)
        assert LeagueSave(**result.config).n_teams == 12

    def test_provenance_survives_the_save_model_and_stays_out_of_the_config(self, monkeypatch):
        """Provenance rides the STORAGE envelope, never `LeagueConfig` itself.

        That separation is what keeps the "identical object" claim literally true: strip the
        envelope and an imported league is byte-identical to a hand-entered one.
        """
        result = _import_sleeper(monkeypatch)
        saved = LeagueSave(
            **result.config,
            source_platform="sleeper",
            source_league_id="1182033380414181376",
            imported_at="2026-08-01T00:00:00Z",
        )
        assert saved.source_platform == "sleeper"
        assert "source_platform" not in lc.LeagueConfig.from_dict(result.config).to_dict()

    def test_canonical_format_version_matches_the_engine(self):
        # A drifted version string would make round-tripped configs disagree about their own schema.
        assert C.CONFIG_FORMAT_VERSION == lc.CONFIG_FORMAT_VERSION

    def test_yahoo_config_is_accepted_by_the_real_engine(self, monkeypatch):
        monkeypatch.setattr(yahoo, "_get", lambda path, token: YAHOO_SETTINGS)
        monkeypatch.setattr(yahoo, "_fetch_teams", lambda *_a, **_k: ())
        monkeypatch.setattr(yahoo, "_stat_names", lambda *_a, **_k: {})
        result = yahoo.import_league("461.l.1000", "tok", include_draft=False)
        cfg = lc.LeagueConfig.from_dict(result.config)
        assert lc.LeagueConfig.from_dict(result.config).to_dict() == result.config
        assert cfg.n_teams == 10
        assert LeagueSave(**result.config).name == "Test Yahoo League"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2 + 3. HONEST TRANSLATION — nothing dropped, nothing silently reinterpreted
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestSleeperTranslation:
    def test_roster_seats_collapse_with_counts(self, monkeypatch):
        roster = {s["name"]: s for s in _import_sleeper(monkeypatch).config["roster"]}
        assert (roster["RB"]["count"], roster["WR"]["count"]) == (2, 3)
        assert roster["FLEX"]["count"] == 3
        assert roster["SUPERFLEX"]["eligible"] == list(C.SUPERFLEX_ELIG)

    def test_ir_and_taxi_slots_absent_from_roster_positions_are_still_imported(self, monkeypatch):
        """Verified on the live league: `roster_positions` omitted its 3 IR and 5 taxi spots.

        Importing only `roster_positions` silently shrinks the roster. They must arrive as BENCH
        slots — a bench slot creates no starter demand, so it cannot move replacement level.
        """
        roster = {s["name"]: s for s in _import_sleeper(monkeypatch).config["roster"]}
        assert roster["IR"]["count"] == 3 and roster["IR"]["bench"] is True
        assert roster["TAXI"]["count"] == 5 and roster["TAXI"]["bench"] is True

    def test_superflex_is_detected_from_eligibility_not_the_slot_name(self, monkeypatch):
        assert _import_sleeper(monkeypatch).config["superflex"] is True
        # A league that spells its QB-eligible slot anything at all is still superflex.
        assert C.detect_superflex([{"name": "OP", "count": 1, "eligible": ["QB", "RB"], "bench": False}])
        # …and a QB-ONLY slot is not (len == 1), nor is a bench slot that happens to allow QBs.
        assert not C.detect_superflex([{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}])
        assert not C.detect_superflex(
            [{"name": "BN", "count": 6, "eligible": ["QB", "RB"], "bench": True}]
        )

    def test_unknown_roster_slot_becomes_a_bench_slot_and_is_disclosed(self, monkeypatch):
        league = {**SLEEPER_LEAGUE, "roster_positions": ["QB", "RB", "WEIRD", "BN"]}
        result = _import_sleeper(monkeypatch, league)
        weird = next(s for s in result.config["roster"] if s["name"] == "WEIRD")
        assert weird["bench"] is True  # cannot inflate starter demand
        assert any("WEIRD" in w for w in result.warnings)  # and the user is told

    def test_points_allowed_fans_out_exactly_across_both_fine_buckets(self, monkeypatch):
        per_stat = _import_sleeper(monkeypatch).config["scoring"]["per_stat"]
        # Sleeper's single 14-20 tier == our 14_17 + 18_20; 35+ == our 35_45 + 46p.
        assert per_stat["dst_pa_g_14_17"] == per_stat["dst_pa_g_18_20"] == 1.0
        assert per_stat["dst_pa_g_35_45"] == per_stat["dst_pa_g_46p"] == -4.0

    def test_fg_50_plus_fans_out_and_then_folds_back_losslessly(self, monkeypatch):
        """The round trip that has to be exact in BOTH directions.

        Sleeper is coarser than our catalog (one 50+ bucket → our 50-59 and 60+), and our catalog is
        finer than the PROJECTION (which resolves 50+ as one bucket). So the weight fans out on
        import and folds back on scoring — and because both halves carry the same value, the fold is
        reported EXACT rather than approximated.
        """
        result = _import_sleeper(monkeypatch)
        per_stat = result.config["scoring"]["per_stat"]
        assert per_stat["fg_made_50_59"] == per_stat["fg_made_60p"] == 5.0
        _, report = presets.resolve_config(lc.LeagueConfig.from_dict(result.config))
        folded = [t for t in report.terms if t.projected_key == "fg_made_50_plus"]
        assert folded and all(t.verdict == DERIVED and t.exact for t in folded)
        assert not report.has_approximation

    def test_the_fine_fg_buckets_map_one_to_one_and_beat_the_coarse_key(self, monkeypatch):
        """Sleeper offers a coarse `fgm_50p` AND a fine `fgm_50_59`/`fgm_60p` pair; leagues use both.

        Regression: the first cut mapped only the coarse key, so a real league paying 5 for 50-59
        and 6 for 60+ had BOTH rules silently dropped to "captured" — despite the catalog having an
        exact column for each. Values here are that league's actual settings.
        """
        league = {
            **SLEEPER_LEAGUE,
            "scoring_settings": {
                **{k: v for k, v in SLEEPER_LEAGUE["scoring_settings"].items() if k != "fgm_50p"},
                "fgm_50_59": 5.0,
                "fgm_60p": 6.0,
            },
        }
        result = _import_sleeper(monkeypatch, league)
        per_stat = result.config["scoring"]["per_stat"]
        assert per_stat["fg_made_50_59"] == 5.0
        assert per_stat["fg_made_60p"] == 6.0
        assert "fgm_60p" not in result.unmapped_scoring_keys

    def test_a_league_setting_both_fg_schemes_lets_the_FINER_one_win(self, monkeypatch):
        """The fine buckets are the more specific statement of the same rule, so the coarse key is
        redundant — and which one lands must not be decided by alphabetical dict ordering."""
        league = {
            **SLEEPER_LEAGUE,
            "scoring_settings": {
                **SLEEPER_LEAGUE["scoring_settings"],  # carries fgm_50p = 5.0
                "fgm_50_59": 5.0,
                "fgm_60p": 6.0,
            },
        }
        per_stat = _import_sleeper(monkeypatch, league).config["scoring"]["per_stat"]
        assert per_stat["fg_made_60p"] == 6.0  # NOT 5.0 from the coarse key

    def test_genuinely_differing_fine_buckets_are_reported_as_an_APPROXIMATION(self, monkeypatch):
        """The other half of the fold. When the fine values AGREE the fold is exact; when they
        genuinely differ our projection cannot express it, and `resolve_scoring` must say
        `exact=False` rather than quietly averaging behind an 'applied' label."""
        league = {
            **SLEEPER_LEAGUE,
            "scoring_settings": {
                **{k: v for k, v in SLEEPER_LEAGUE["scoring_settings"].items() if k != "fgm_50p"},
                "fgm_50_59": 5.0,
                "fgm_60p": 6.0,
            },
        }
        result = _import_sleeper(monkeypatch, league)
        _, report = presets.resolve_config(lc.LeagueConfig.from_dict(result.config))
        folded = [t for t in report.terms if t.projected_key == "fg_made_50_plus"]
        assert folded and all(not t.exact for t in folded)
        assert report.has_approximation
        assert all(t.note for t in folded)  # and it explains itself

    def test_offensive_and_defensive_stats_are_not_conflated(self, monkeypatch):
        """The pair a careless map merges: a player's return TD vs the DEF/ST unit's.

        Sleeper's `st_td` is credited to the returning PLAYER and `def_st_td` to the DEF unit;
        mapping both to one canonical key would double-count a single return touchdown.
        """
        per_stat = _import_sleeper(monkeypatch).config["scoring"]["per_stat"]
        assert per_stat["st_player_td"] == 6.0  # from Sleeper's `st_td`
        assert per_stat["st_td"] == 6.0         # from Sleeper's `def_st_td`
        assert sleeper.SCORING_KEY_MAP["st_td"] != sleeper.SCORING_KEY_MAP["def_st_td"]

    def test_te_premium_lands_in_position_bonuses_not_the_flat_rec_weight(self, monkeypatch):
        """Folding `bonus_rec_te` into `rec` would pay every RB and WR the TE premium."""
        league = {
            **SLEEPER_LEAGUE,
            "scoring_settings": {**SLEEPER_LEAGUE["scoring_settings"], "bonus_rec_te": 0.5},
        }
        cfg = _import_sleeper(monkeypatch, league).config
        assert cfg["scoring"]["position_bonuses"] == {"TE": {"rec": 0.5}}
        assert cfg["scoring"]["per_stat"]["rec"] == 1.0  # unchanged
        # …and the engine reads it back as a TE-only premium.
        scoring = lc.LeagueConfig.from_dict(cfg).scoring
        assert scoring.points_for("rec", "TE") == 1.5
        assert scoring.points_for("rec", "WR") == 1.0

    def test_agreeing_two_point_keys_collapse_silently_and_disagreeing_ones_are_disclosed(
        self, monkeypatch
    ):
        # All three agree → an exact restatement, nothing to warn about.
        assert not [w for w in _import_sleeper(monkeypatch).warnings if "2-point" in w]
        # They disagree → our single `two_pt` column cannot express it, so SAY so rather than
        # letting dict ordering decide which value survives.
        league = {
            **SLEEPER_LEAGUE,
            "scoring_settings": {
                **SLEEPER_LEAGUE["scoring_settings"],
                "pass_2pt": 2.0, "rush_2pt": 3.0, "rec_2pt": 2.0,
            },
        }
        result = _import_sleeper(monkeypatch, league)
        assert result.config["scoring"]["per_stat"]["two_pt"] == 3.0
        assert any("2-point" in w for w in result.warnings)

    def test_unmapped_terms_are_carried_verbatim_and_reported_captured(self, monkeypatch):
        """The honesty rule: a rule we cannot project is STORED and DISCLOSED, never dropped."""
        result = _import_sleeper(monkeypatch)
        per_stat = result.config["scoring"]["per_stat"]
        assert per_stat["st_ff"] == 1.0  # carried under Sleeper's own key
        assert "st_ff" in result.unmapped_scoring_keys

        _, report = presets.resolve_config(lc.LeagueConfig.from_dict(result.config))
        captured = {t.key for t in report.by_verdict(CAPTURED)}
        assert {"st_ff", "st_fum_rec", "def_st_ff"} <= captured
        # and every captured term says WHY
        assert all(t.note for t in report.by_verdict(CAPTURED))

    def test_a_zeroed_term_is_not_reported_as_captured(self, monkeypatch):
        """A platform ships its whole table with unused rules at 0. Reporting those would bury the
        handful that genuinely matter under dozens of non-statements."""
        result = _import_sleeper(monkeypatch)
        assert "fum" not in result.unmapped_scoring_keys

    def test_captured_rules_are_recorded_but_never_scored(self, monkeypatch):
        result = _import_sleeper(monkeypatch)
        assert result.config["captured_rules"]["league_type"] == "dynasty"
        assert result.config["captured_rules"]["playoff_weeks"] == 15
        # None of them leaked into scoring, which is the whole point of the field.
        assert not set(result.config["captured_rules"]) & set(result.config["scoring"]["per_stat"])

    def test_median_scoring_is_captured_when_the_league_uses_it(self, monkeypatch):
        league = {**SLEEPER_LEAGUE, "settings": {**SLEEPER_LEAGUE["settings"], "league_average_match": 1}}
        assert _import_sleeper(monkeypatch, league).config["captured_rules"]["median_scoring"] is True

    def test_draft_state_is_named_and_epoch_millis_are_converted(self, monkeypatch):
        """Sleeper stamps epoch MILLISECONDS; passing it through raw renders as year ~57000."""
        draft = _import_sleeper(monkeypatch, with_state=True).draft
        assert draft.picks[0].player.name == "Ashton Jeanty"
        assert draft.start_time.startswith("2025-")

    def test_a_league_with_no_starting_slots_is_refused_at_import(self, monkeypatch):
        """Rankable-or-refuse. Storing it would produce an empty board later with no explanation."""
        league = {**SLEEPER_LEAGUE, "roster_positions": ["BN", "BN"]}
        with pytest.raises(sleeper.SleeperInputError, match="starting lineup"):
            _import_sleeper(monkeypatch, league)


class TestYahooTranslation:
    def _import(self, monkeypatch, payload=None):
        monkeypatch.setattr(yahoo, "_get", lambda path, token: payload or YAHOO_SETTINGS)
        monkeypatch.setattr(yahoo, "_fetch_teams", lambda *_a, **_k: ())
        monkeypatch.setattr(yahoo, "_stat_names", lambda *_a, **_k: {"9999": "Some Bonus"})
        return yahoo.import_league("461.l.1000", "tok", include_draft=False)

    def test_the_two_interception_stats_are_kept_apart(self, monkeypatch):
        """⭐ The bug a name-matching importer ships: Yahoo has id 6 "Interceptions" (thrown by a
        QB, negative) and id 33 "Interception" (made by a defense, positive). Conflating them pays
        quarterbacks for defensive picks — which is why this adapter maps by ID."""
        per_stat = self._import(monkeypatch).config["scoring"]["per_stat"]
        assert per_stat["pass_int"] == -1.0
        assert per_stat["def_int"] == 2.0
        assert yahoo.STAT_ID_MAP["6"] != yahoo.STAT_ID_MAP["33"]

    def test_coarse_buckets_fan_out_exactly(self, monkeypatch):
        per_stat = self._import(monkeypatch).config["scoring"]["per_stat"]
        assert per_stat["fg_made_50_59"] == per_stat["fg_made_60p"] == 5.0
        assert per_stat["dst_pa_g_14_17"] == per_stat["dst_pa_g_18_20"] == 1.0
        assert per_stat["dst_pa_g_35_45"] == per_stat["dst_pa_g_46p"] == -4.0

    def test_count_based_roster_positions_expand_then_collapse(self, monkeypatch):
        roster = {s["name"]: s for s in self._import(monkeypatch).config["roster"]}
        assert roster["WR"]["count"] == 3
        assert roster["FLEX"]["eligible"] == list(C.FLEX_ELIG)  # from Yahoo's "W/R/T"
        assert roster["DST"]["eligible"] == ["DST"]             # from Yahoo's "DEF"
        assert roster["IR"]["bench"] is True

    def test_an_unknown_stat_id_is_carried_under_a_readable_key(self, monkeypatch):
        result = self._import(monkeypatch)
        assert result.config["scoring"]["per_stat"]["yahoo_9999_some_bonus"] == 3.0
        assert "yahoo_9999_some_bonus" in result.unmapped_scoring_keys

    def test_ppr_label_is_derived_from_the_actual_reception_weight(self, monkeypatch):
        assert self._import(monkeypatch).config["ppr"] == "half"  # stat 11 = 0.5

    def test_the_tree_walk_survives_yahoos_numeric_keyed_collections(self, monkeypatch):
        """Yahoo returns collections as `{"0": …, "1": …, "count": n}` in some resources and as
        plain arrays in others. Positional parsing breaks on the difference; the walk must not."""
        payload = {
            "fantasy_content": {
                "league": [
                    {"league_key": "461.l.1000", "name": "Numeric", "season": "2025", "num_teams": "8"},
                    {
                        "settings": [
                            {
                                "roster_positions": {
                                    "0": {"roster_position": {"position": "QB", "count": 1}},
                                    "1": {"roster_position": {"position": "RB", "count": 2}},
                                    "2": {"roster_position": {"position": "BN", "count": 5}},
                                    "count": 3,
                                },
                                "stat_modifiers": {
                                    "stats": {
                                        "0": {"stat": {"stat_id": "4", "value": "0.04"}},
                                        "1": {"stat": {"stat_id": "11", "value": "1"}},
                                        "count": 2,
                                    }
                                },
                            }
                        ]
                    },
                ]
            }
        }
        result = self._import(monkeypatch, payload)
        roster = {s["name"]: s["count"] for s in result.config["roster"]}
        assert roster == {"QB": 1, "RB": 2, "BN": 5}
        assert result.config["scoring"]["per_stat"]["rec"] == 1.0
        assert result.config["ppr"] == "ppr"


class TestIdentifierResolution:
    """The identifier a user HAS is the league ID, not their username.

    The first cut asked for a username, and the very first real attempt pasted a league ID and got a
    422 — a dead end created entirely by demanding the one identifier Sleeper's UI never shows you.
    A bare number is genuinely ambiguous (league ids and user ids are both snowflakes), so these pin
    the disambiguation ORDER and, more importantly, that a total miss names BOTH possibilities
    instead of blaming whichever we happened to try first.
    """

    def _resolve(self, monkeypatch, *, league=None, user=None, leagues=()):
        def fake_get_json(url, **_):
            if "/league/" in url and url.endswith(tuple("0123456789")):
                return league
            if "/user/" in url and "/leagues/" not in url:
                return user
            if "/leagues/" in url:
                return list(leagues)
            return None

        monkeypatch.setattr(sleeper, "get_json", fake_get_json)
        return sleeper.resolve_target("1268257036043292672", "2026")

    def test_a_numeric_id_is_tried_as_a_league_first(self, monkeypatch):
        """League-first because that is where a user gets a number from — the league's own URL."""
        out = self._resolve(monkeypatch, league={"league_id": "1268257036043292672", "name": "The Megalabowl", "total_rosters": 12})
        assert out["kind"] == "league"
        assert out["league"]["name"] == "The Megalabowl"

    def test_every_branch_carries_leagues_so_an_older_client_still_renders(self, monkeypatch):
        """🚨 The API Lambda and the frontend deploy INDEPENDENTLY (the Lambda has no CI/CD), so a
        response-shape change must be ADDITIVE. The first cut returned the league branch WITHOUT a
        `leagues` key; a frontend one deploy behind read `res.leagues`, got undefined, and rendered
        a blank screen on a 200 — no error anywhere. Pin the key in BOTH branches."""
        as_league = self._resolve(monkeypatch, league={"league_id": "1268257036043292672", "name": "L", "total_rosters": 12})
        assert as_league["leagues"] == [as_league["league"]]

        as_user = self._resolve(
            monkeypatch,
            league=None,
            user={"user_id": "1268257036043292672", "display_name": "Someone"},
            leagues=[{"league_id": "9", "name": "L", "season": "2026"}],
        )
        assert isinstance(as_user["leagues"], list)

    def test_a_numeric_id_falls_back_to_a_user_lookup(self, monkeypatch):
        out = self._resolve(
            monkeypatch,
            league=None,
            user={"user_id": "1268257036043292672", "display_name": "Someone"},
            leagues=[{"league_id": "9", "name": "L", "season": "2026"}],
        )
        assert out["kind"] == "user"
        assert out["leagues"][0]["league_id"] == "9"

    def test_a_number_that_is_neither_names_both_possibilities(self, monkeypatch):
        """The failure mode this replaced said 'Sleeper has no user called X' for what was, in fact,
        a perfectly valid league ID — blaming the branch we guessed rather than the ambiguity."""
        with pytest.raises(sleeper.SleeperInputError) as exc:
            self._resolve(monkeypatch, league=None, user=None)
        assert "league ID" in str(exc.value) and "username" in str(exc.value)

    def test_a_username_miss_points_at_the_league_id_escape_hatch(self, monkeypatch):
        monkeypatch.setattr(sleeper, "get_json", lambda url, **_: None)
        with pytest.raises(sleeper.SleeperInputError, match="league ID"):
            sleeper.resolve_user("nosuchuser")

    def test_an_empty_identifier_is_refused_before_any_request(self, monkeypatch):
        called = []
        monkeypatch.setattr(sleeper, "get_json", lambda url, **_: called.append(url))
        with pytest.raises(sleeper.SleeperInputError):
            sleeper.resolve_target("   ", "2026")
        assert not called


class TestCanonicalHelpers:
    def test_collapse_preserves_first_seen_order_and_merges_interleaved_seats(self):
        slots = C.collapse_slots(
            [("RB", ("RB",), False), ("WR", ("WR",), False), ("RB", ("RB",), False)]
        )
        assert [(s["name"], s["count"]) for s in slots] == [("RB", 2), ("WR", 1)]

    @pytest.mark.parametrize(
        "rec,label", [(0.0, "standard"), (0.5, "half"), (1.0, "ppr"), (0.75, "custom")]
    )
    def test_ppr_label(self, rec, label):
        assert C.derive_ppr_label({"rec": rec}) == label

    def test_a_coarse_platform_bucket_writes_every_fine_bucket(self):
        out = C.apply_scoring_map({"pa_14_20": 1.0}, {"pa_14_20": ("a", "b")})
        assert out.per_stat == {"a": 1.0, "b": 1.0}

    def test_config_is_rankable_requires_a_real_starting_slot(self):
        base = {"n_teams": 12, "scoring": {"per_stat": {"rec": 1.0}}}
        assert not C.config_is_rankable({**base, "roster": [{"name": "BN", "count": 6, "bench": True}]})
        assert C.config_is_rankable({**base, "roster": [{"name": "QB", "count": 1, "bench": False}]})


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. THE RED LINE — structural, not aspirational
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestNoCredentialHandling:
    """🚨 The story's hard red line, enforced against the SOURCE.

    A future adapter (CBS, MFL, Fantrax) could otherwise add a password field, pass every unit
    test, and ship. Reading the source is the only check that binds code nobody has written yet.
    """

    def test_no_import_module_handles_a_password_or_a_session_cookie(self):
        """Scans CODE, not prose.

        Comments and docstrings are stripped first: these modules DISCUSS the red line at length,
        and a lint that fired on the documentation would push authors to delete the explanation —
        the opposite of what is wanted. Ordinary string literals are deliberately KEPT in scope, so
        a `{"password": ...}` payload or an `os.environ["ESPN_S2"]` read still trips it.
        """
        import ast
        import io
        import tokenize

        offenders = []
        for path in sorted(IMPORT_PKG.glob("*.py")) + [ROUTER]:
            source = path.read_text()
            skip: set[int] = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc is not None:
                        expr = node.body[0]
                        skip.update(range(expr.lineno, (expr.end_lineno or expr.lineno) + 1))
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.COMMENT:
                    skip.update(range(tok.start[0], tok.end[0] + 1))
            # ⭐ THE ONE EXEMPTION, AND WHY IT IS NARROW.
            # `espn.py` must NAME these tokens in order to REFUSE them: its scrubber rejects a
            # paste containing a session cookie. Naming a credential to reject it is the opposite
            # of handling one, but a blanket file-level exemption would gut the lint for the whole
            # ESPN adapter. So the exemption is scoped to the `_CREDENTIAL_SIGNATURES` assignment
            # ONLY, and `TestEspnCredentialScrubber` below pins that the tokens appear nowhere else
            # in that module and that the scrubber genuinely fires.
            exempt: set[int] = set()
            if path.name == "espn.py":
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.AnnAssign | ast.Assign):
                        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                        names = {t.id for t in targets if isinstance(t, ast.Name)}
                        if "_CREDENTIAL_SIGNATURES" in names:
                            exempt.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

            for lineno, line in enumerate(source.splitlines(), 1):
                if lineno in skip or lineno in exempt:
                    continue
                if re.search(r"\bpassword\b|\bespn_s2\b|\bSWID\b", line, re.IGNORECASE):
                    offenders.append(f"{path.name}:{lineno}")
        assert not offenders, f"platform import must never handle credentials: {offenders}"

    def test_that_credential_lint_actually_fires(self, tmp_path):
        """A lint nobody has seen FAIL is not a lint (NF1.7 (a): a check that cannot fail passes on
        nothing). Prove it catches a real breach and ignores prose about one."""
        import ast
        import io
        import tokenize

        def scan(source: str) -> bool:
            skip: set[int] = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    doc = ast.get_docstring(node, clean=False)
                    if doc is not None:
                        expr = node.body[0]
                        skip.update(range(expr.lineno, (expr.end_lineno or expr.lineno) + 1))
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.COMMENT:
                    skip.update(range(tok.start[0], tok.end[0] + 1))
            return any(
                re.search(r"\bpassword\b|\bespn_s2\b|\bSWID\b", line, re.IGNORECASE)
                for lineno, line in enumerate(source.splitlines(), 1)
                if lineno not in skip
            )

        assert scan('def login(password):\n    return password\n')
        assert scan('COOKIES = {"espn_s2": token}\n')
        assert not scan('"""We never store a password."""\n# nor an espn_s2 cookie\nX = 1\n')

    def test_espn_is_not_an_offered_platform(self):
        from app.backend.services.platform_import import PLATFORMS

        assert "espn" not in PLATFORMS

    def test_the_espn_probe_memo_exists_and_records_a_no_go(self):
        """The NO-GO has to be an EARNED, written finding — not an undocumented omission a later
        session re-litigates from scratch."""
        memo = (REPO / "docs" / "nf_c0_espn_access_probe.md").read_text()
        assert "NO-GO" in memo
        assert "espn_s2" in memo  # names the specific mechanism it refuses

    def test_user_supplied_ids_are_validated_before_a_url_is_built(self):
        """SSRF guard: these values come from a form field and are interpolated into a URL."""
        for bad in ("../../etc/passwd", "1;rm -rf /", "http://evil.test", "1 2", ""):
            with pytest.raises(sleeper.SleeperInputError):
                sleeper.import_league(bad)
            with pytest.raises(yahoo.YahooInputError):
                yahoo.import_league(bad, "tok")

    def test_every_outbound_call_carries_a_finite_timeout(self):
        """INC-32, one layer over: an un-timed-out call on a request path hangs the invocation."""
        from app.backend.services.platform_import import http

        assert http.DEFAULT_TIMEOUT and http.DEFAULT_TIMEOUT < 29  # API Gateway's hard cap
        source = (IMPORT_PKG / "http.py").read_text()
        assert "timeout=timeout" in source


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. OAUTH + ROUTE GATING
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestYahooOAuth:
    @pytest.fixture
    def keyed(self, monkeypatch):
        """Pin a deterministic SSM key so the signing tests need no AWS."""
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            yahoo_oauth,
            "_get_parameter",
            lambda name: {
                yahoo_oauth.PARAM_CLIENT_ID: "cid",
                yahoo_oauth.PARAM_CLIENT_SECRET: "secret",
                yahoo_oauth.PARAM_TOKEN_KEY: key,
            }.get(name),
        )
        return key

    def test_state_round_trips_and_binds_the_user(self, keyed):
        assert yahoo_oauth.verify_state(yahoo_oauth.issue_state("user-123")) == "user-123"

    def test_a_tampered_state_is_rejected(self, keyed):
        """Without this, anyone could complete their OWN consent round-trip and graft their Yahoo
        account onto another user's Credence account."""
        body, sig = yahoo_oauth.issue_state("user-123").split(".", 1)
        forged_body, _ = yahoo_oauth.issue_state("victim-456").split(".", 1)
        for bad in (f"{forged_body}.{sig}", f"{body}.AAAA", body, "garbage"):
            with pytest.raises(yahoo_oauth.YahooAuthError):
                yahoo_oauth.verify_state(bad)

    def test_an_expired_state_is_rejected(self, keyed, monkeypatch):
        state = yahoo_oauth.issue_state("user-123")
        # Capture the REAL clock before patching — `yahoo_oauth.time` is the shared stdlib module,
        # so a lambda that calls `time.time()` would recurse into its own patch.
        later = time.time() + 3600
        monkeypatch.setattr(yahoo_oauth.time, "time", lambda: later)
        with pytest.raises(yahoo_oauth.YahooAuthError):
            yahoo_oauth.verify_state(state)

    def test_tokens_encrypt_and_decrypt(self, keyed):
        blob = yahoo_oauth.encrypt_token("refresh-abc")
        assert blob != "refresh-abc"
        assert yahoo_oauth.decrypt_token(blob) == "refresh-abc"

    def test_a_token_encrypted_under_a_rotated_key_asks_for_a_reconnect(self, keyed, monkeypatch):
        """A rotated key must read as 'reconnect', not as a 500 that strands the user."""
        blob = yahoo_oauth.encrypt_token("refresh-abc")
        from cryptography.fernet import Fernet

        monkeypatch.setattr(yahoo_oauth, "_get_parameter", lambda name: Fernet.generate_key().decode())
        with pytest.raises(yahoo_oauth.YahooAuthError):
            yahoo_oauth.decrypt_token(blob)

    def test_credentials_present_does_not_mean_the_feature_is_available(self, keyed, monkeypatch):
        """⚠️ Creating the Yahoo app yields a client id/secret IMMEDIATELY, but fantasy DATA access
        is granted separately on approval (1–2 weeks). In between, the OAuth handshake would
        succeed and every Fantasy endpoint would 401 — the user grants a permission that buys them
        nothing and the failure looks like our bug. So provisioning and availability are separate,
        and the flag must default CLOSED (an unset env var means not available)."""
        monkeypatch.delenv("YAHOO_IMPORT_ENABLED", raising=False)
        assert yahoo_oauth.is_configured() is True  # credentials ARE in SSM
        assert yahoo_oauth.is_enabled() is False  # …and the feature is still not offered

        monkeypatch.setenv("YAHOO_IMPORT_ENABLED", "1")
        assert yahoo_oauth.is_enabled() is True

    def test_the_availability_flag_only_opens_on_an_exact_1(self, keyed, monkeypatch):
        """A flag that opens on any truthy-looking string opens by accident."""
        for value in ("0", "", "true", "yes", "enabled", " "):
            monkeypatch.setenv("YAHOO_IMPORT_ENABLED", value)
            assert yahoo_oauth.is_enabled() is False, value

    def test_the_flag_cannot_open_without_credentials(self, monkeypatch):
        """Setting the flag must not make an unprovisioned platform look available."""
        monkeypatch.setattr(yahoo_oauth, "_get_parameter", lambda name: None)
        monkeypatch.setenv("YAHOO_IMPORT_ENABLED", "1")
        assert yahoo_oauth.is_enabled() is False

    def test_missing_ssm_config_degrades_honestly(self, monkeypatch):
        """Unprovisioned is an EXPECTED state (the operator's Yahoo approval is pending), so it must
        raise a distinct type the router turns into a 503 with an explanation — never a 500."""
        monkeypatch.setattr(yahoo_oauth, "_get_parameter", lambda name: None)
        assert yahoo_oauth.is_configured() is False
        with pytest.raises(yahoo_oauth.YahooNotConfigured):
            yahoo_oauth.authorize_url("user-1")

    def test_authorize_url_targets_the_probed_endpoint_over_https(self, keyed):
        url = yahoo_oauth.authorize_url("user-1")
        assert url.startswith("https://api.login.yahoo.com/oauth2/request_auth?")
        assert "response_type=code" in url and "state=" in url
        # ⚠️ Yahoo rejects a non-HTTPS callback at registration; a drift here fails the exchange
        # with an opaque `invalid_request` that never mentions the URI.
        assert yahoo_oauth.REDIRECT_URI.startswith("https://")

    def test_a_refresh_that_omits_a_new_token_keeps_the_old_one(self, keyed, monkeypatch):
        """Yahoo MAY rotate the refresh token and revokes the old one when it does. Dropping the
        carried-forward value on a non-rotating refresh would silently disconnect the user."""
        monkeypatch.setattr(
            yahoo_oauth, "_token_call", lambda form: {"access_token": "a", "expires_in": 3600}
        )
        assert yahoo_oauth.refresh_access_token("old-refresh")["refresh_token"] == "old-refresh"

    def test_a_rotated_refresh_token_replaces_the_old_one(self, keyed, monkeypatch):
        monkeypatch.setattr(
            yahoo_oauth,
            "_token_call",
            lambda form: {"access_token": "a", "refresh_token": "new", "expires_in": 3600},
        )
        assert yahoo_oauth.refresh_access_token("old")["refresh_token"] == "new"

    def test_expiry_carries_a_safety_margin(self, keyed, monkeypatch):
        """A token that expires mid-request must be refreshed BEFORE the call, not produce a 401
        the user sees."""
        monkeypatch.setattr(
            yahoo_oauth, "_token_call", lambda form: {"access_token": "a", "expires_in": 3600}
        )
        assert yahoo_oauth.refresh_access_token("r")["expires_at"] < time.time() + 3600


class TestRouteGating:
    """Source-inspected rather than TestClient-driven: the fast gate must not import `pipeline`
    or construct the whole app, and the invariant here is structural anyway."""

    SOURCE = ROUTER.read_text()

    def test_every_route_is_entitlement_gated_except_the_oauth_callback(self):
        # Each decorated route must either sit on the gated `router` or be the ONE documented
        # exemption on `public_router`.
        gated = re.findall(r"@router\.(get|post|put|delete)\(", self.SOURCE)
        public = re.findall(r"@public_router\.(get|post|put|delete)\(", self.SOURCE)
        assert len(gated) >= 8, "expected the full import surface on the gated router"
        assert len(public) == 1, "exactly one unauthenticated route (the OAuth callback) is allowed"
        assert "@public_router.get(\"/yahoo/callback\")" in self.SOURCE

    def test_gated_routes_all_depend_on_the_beta_entitlement(self):
        # One `Depends(require_fantasy_beta_access)` per gated route — importing WRITES a user's
        # league config, so the server-side gate is the real one.
        assert self.SOURCE.count("Depends(require_fantasy_beta_access)") == len(
            re.findall(r"@router\.(get|post|put|delete)\(", self.SOURCE)
        )

    def test_every_yahoo_route_enforces_the_availability_gate_server_side(self):
        """Hiding the button is not a gate — an entitled caller can POST straight to the API."""
        assert "_require_yahoo_enabled()" in self.SOURCE
        # authorize + the shared token path (which every league/preview route goes through)
        assert self.SOURCE.count("_require_yahoo_enabled()") >= 3  # def + authorize + _access_token

    def test_the_callback_verifies_the_signed_state(self):
        assert "verify_state(state)" in self.SOURCE

    def test_the_callback_redirects_rather_than_returning_an_api_error(self):
        """The user is mid-flow in a browser; a JSON error body strands them on a blank page."""
        assert self.SOURCE.count("RedirectResponse") >= 3

    def test_the_refresh_token_is_encrypted_before_it_reaches_dynamo(self):
        for call in re.findall(r"put_platform_token\((.{0,400}?)\)\n", self.SOURCE, re.S):
            if "refresh_token" in call:
                assert "encrypt_token" in call

    def test_live_draft_state_is_never_persisted(self):
        """A stored 'who is already drafted' snapshot is wrong the moment the next pick lands, and
        it looks identical to a correct one — so state is always re-read, never saved."""
        assert "fetch_draft_state" in self.SOURCE
        assert "put_fantasy_league" not in self.SOURCE  # the import router never writes a config


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 6. ESPN — user-mediated paste (NF-C0f). No network client exists in that module BY DESIGN.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

ESPN_FIXTURE = Path(__file__).parent / "fixtures" / "espn_league_mSettings_real.json"


@pytest.fixture
def espn_payload() -> str:
    """A REAL `?view=mSettings` response from a live 12-team private league (financeSettings
    removed). Real, because a hand-written fixture inherits the author's assumptions about the
    shape — the NF-C0 lesson that cost a mapping bug."""
    return ESPN_FIXTURE.read_text()


class TestEspnCredentialScrubber:
    """The guard that keeps the paste flow from decaying into the cookie flow it replaced."""

    def test_a_copy_as_curl_paste_is_refused(self):
        from app.backend.services.platform_import import espn

        curl = (
            "curl 'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/"
            "segments/0/leagues/998005?view=mSettings' "
            "-H 'Cookie: SWID={ABC-123}; espn_s2=AEBxyz%2Fdeadbeef'"
        )
        with pytest.raises(espn.EspnCredentialPasteError) as exc:
            espn.parse_settings_payload(curl)
        # THE invariant: the refusal must never echo the pasted VALUE back. An error string is a
        # log line waiting to happen, and the cookie's value is the actual secret (its NAME is not).
        msg = str(exc.value)
        assert "AEBxyz" not in msg and "deadbeef" not in msg and "ABC-123" not in msg
        # ...and it must still tell the user what to do instead of just refusing.
        assert "JSON" in msg

    @pytest.mark.parametrize(
        "bad",
        [
            "Cookie: espn_s2=abc",
            "-H 'cookie: SWID={x}'",
            "authorization: Bearer abc",
            '{"SWID": "{ABC}"}',
            "set-cookie: espn_s2=zzz",
        ],
    )
    def test_every_credential_shape_is_refused(self, bad):
        from app.backend.services.platform_import import espn

        with pytest.raises(espn.EspnCredentialPasteError):
            espn.parse_settings_payload(bad)

    def test_the_scrubber_runs_before_the_parser(self):
        """Order matters: a cURL paste is not valid JSON, so if parsing ran first the user would get
        a confusing 'not JSON' message and we'd have no idea a credential had been pasted."""
        from app.backend.services.platform_import import espn

        with pytest.raises(espn.EspnCredentialPasteError):
            espn.parse_settings_payload("not json at all, but has espn_s2=abc in it")

    def test_espn_module_names_credentials_ONLY_in_the_refusal_constant(self):
        """Compensating control for the narrow lint exemption above."""
        import ast
        import io
        import tokenize

        source = (IMPORT_PKG / "espn.py").read_text()
        tree = ast.parse(source)
        allowed: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign | ast.Assign):
                targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
                if any(isinstance(t, ast.Name) and t.id == "_CREDENTIAL_SIGNATURES" for t in targets):
                    allowed.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        assert allowed, "_CREDENTIAL_SIGNATURES not found — the exemption is pointing at nothing"

        skip: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                doc = ast.get_docstring(node, clean=False)
                if doc is not None:
                    expr = node.body[0]
                    skip.update(range(expr.lineno, (expr.end_lineno or expr.lineno) + 1))
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                skip.update(range(tok.start[0], tok.end[0] + 1))

        strays = [
            n for n, line in enumerate(source.splitlines(), 1)
            if n not in skip and n not in allowed
            and re.search(r"\bespn_s2\b|\bSWID\b|\bpassword\b", line, re.IGNORECASE)
        ]
        assert not strays, f"credential tokens outside the refusal constant: {strays}"

    def test_the_espn_module_makes_no_network_call_at_all(self):
        """§3(d) rests on us never REQUESTING anything from ESPN. Enforce it structurally: if a
        future edit imports an HTTP client here, the paste flow has quietly become the cookie flow."""
        source = (IMPORT_PKG / "espn.py").read_text()
        for banned in ("import requests", "import httpx", "urllib.request", "from .http", "http.client"):
            assert banned not in source, f"espn.py must make no network call, found: {banned}"


class TestEspnPositionOverrides:
    """🚨 The trap: 16 of 43 real rules have `points: 0.0` with their true value ONLY in
    `pointsOverrides['16']` (slot 16 = D/ST). Reading `points` alone silently zeroes the entire
    team-defense sheet AND reports it APPLIED — indistinguishable from working."""

    def test_the_real_payload_actually_contains_the_trap(self, espn_payload):
        """Guard the guard: if ESPN ever stops using overrides this test tells us the fixture no
        longer exercises the thing the parser exists to handle."""
        items = json.loads(espn_payload)["settings"]["scoringSettings"]["scoringItems"]
        zero_base_with_override = [
            i for i in items if i.get("pointsOverrides", {}).get("16") and i["points"] == 0.0
        ]
        assert len(zero_base_with_override) >= 10, "fixture no longer exercises the override trap"

    def test_dst_values_survive_flattening(self, espn_payload):
        from app.backend.services.platform_import import espn

        items = json.loads(espn_payload)["settings"]["scoringSettings"]["scoringItems"]
        flat, _ = espn.flatten_scoring_items(items)
        # statId 89 is points=0.0 / D/ST=12.0 in the real payload.
        assert flat.get("89@dst") == 12.0
        assert "89" not in flat, "a 0.0 base must not be emitted as a real rule"
        # statId 102 scores 6.0 for a player and 0.0 for a D/ST — both facts must be preserved
        # distinctly, the same player-vs-unit split Sleeper draws between st_td and def_st_td.
        assert flat.get("102") == 6.0
        assert "102@dst" not in flat

    def test_a_naive_points_only_parser_would_lose_these(self, espn_payload):
        """Quantifies the bug this module exists to prevent, so the cost is on record."""
        from app.backend.services.platform_import import espn

        items = json.loads(espn_payload)["settings"]["scoringSettings"]["scoringItems"]
        naive = {str(i["statId"]): i["points"] for i in items if i["points"]}
        flat, _ = espn.flatten_scoring_items(items)
        recovered = [k for k in flat if k.endswith("@dst")]
        assert len(recovered) >= 15
        assert not any(k in naive for k in recovered)


class TestEspnImport:
    def test_a_real_private_league_imports(self, espn_payload):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert league.platform == "espn"
        assert league.config["name"] == "Sundays Best"
        assert league.config["n_teams"] == 12
        assert league.season == "2026"

    def test_the_paste_reaches_a_PRIVATE_league(self, espn_payload):
        """The whole reason §3(d) beats the public-visibility toggle: it works on a league that is
        NOT public, which is the population the feature exists to serve."""
        assert json.loads(espn_payload)["settings"]["isPublic"] is False

    def test_roster_matches_the_real_league(self, espn_payload):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        counts = {s["name"]: s["count"] for s in league.config["roster"]}
        assert counts == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "DST": 1, "K": 1,
                          "BN": 6, "IR": 3}
        starters = sum(s["count"] for s in league.config["roster"] if not s["bench"])
        assert starters == 9

    def test_superflex_is_false_for_this_league(self, espn_payload):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert C.detect_superflex(league.config["roster"]) is False

    def test_core_scoring_is_applied(self, espn_payload):
        from app.backend.services.platform_import import espn

        per_stat = espn.parse_settings_payload(espn_payload).config["scoring"]["per_stat"]
        assert per_stat["pass_yd"] == 0.04
        assert per_stat["pass_td"] == 4.0
        assert per_stat["pass_int"] == -1.0
        assert per_stat["rush_yd"] == 0.1
        assert per_stat["rush_td"] == 6.0
        assert per_stat["rec"] == 1.0          # the league's own playerRankType reads "PPR"
        assert per_stat["rec_yd"] == 0.1
        assert per_stat["rec_td"] == 6.0
        assert per_stat["fum_lost"] == -1.0

    def test_unmapped_ids_are_CAPTURED_not_dropped(self, espn_payload):
        """ESPN publishes no stat-id dictionary, so the map is deliberately partial. The contract is
        that everything unmapped is stored faithfully and reported, never silently discarded —
        an unmapped id tells the truth; a guessed id silently misprices the league."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert league.unmapped_scoring_keys, "expected captured terms from a 43-rule league"
        # Every D/ST rule is currently unmapped and must be visible as such.
        assert any(k.endswith("@dst") for k in league.unmapped_scoring_keys)
        stored = league.config["scoring"]["per_stat"]
        for key in league.unmapped_scoring_keys:
            assert key in stored, f"{key} reported unmapped but not stored"

    def test_config_round_trips_through_the_real_engine(self, espn_payload):
        """Same shared-contract proof the Sleeper and Yahoo adapters carry — no forked schema."""
        from app.backend.services.platform_import import espn

        config = espn.parse_settings_payload(espn_payload).config
        assert lc.LeagueConfig.from_dict(config).to_dict() == config

    def test_an_unauthorized_espn_response_gets_an_actionable_message(self):
        from app.backend.services.platform_import import espn

        body = json.dumps({"messages": ["You are not authorized to view this League."]})
        with pytest.raises(espn.EspnInputError) as exc:
            espn.parse_settings_payload(body)
        assert "signed in" in str(exc.value).lower()

    def test_the_read_url_rejects_a_non_numeric_league_id(self):
        from app.backend.services.platform_import import espn

        assert espn.build_read_url("998005", 2026).endswith("leagues/998005?view=mSettings")
        for bad in ("../../etc", "998005; rm -rf /", "http://evil", ""):
            with pytest.raises(espn.EspnInputError):
                espn.build_read_url(bad, 2026)

    def test_an_oversized_paste_is_refused_before_parsing(self):
        from app.backend.services.platform_import import espn

        with pytest.raises(espn.EspnInputError):
            espn.parse_settings_payload("x" * (espn.MAX_PASTE_BYTES + 1))
