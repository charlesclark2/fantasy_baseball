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

    def test_canonical_auction_budget_matches_the_engine(self):
        # NF-C5. `canonical.py` MIRRORS engine constants rather than importing them (the Lambda
        # cold-start rule), so each mirrored constant needs its own pin or it drifts silently — an
        # imported league would then round-trip to a different budget than the engine's default.
        from quant_sports_intel_models.fantasy_engine import auction as auc

        assert C.DEFAULT_AUCTION_BUDGET == auc.DEFAULT_AUCTION_BUDGET

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

    def test_espn_is_offered_ONLY_as_a_paste_never_as_a_credential_flow(self):
        """ESPN was originally refused outright. NF-C0f re-opened it via user-mediated paste, which
        is categorically different: the user makes the request in their own browser and hands us the
        RESPONSE BODY, which structurally cannot carry `espn_s2` (an HTTP cookie is never echoed
        into a body). What must never come back is a credential-accepting ESPN path — so this pins
        the auth KIND rather than merely the platform's presence."""
        from app.backend.services.platform_import import PLATFORMS

        assert PLATFORMS["espn"]["auth"] == "paste"
        assert PLATFORMS["espn"]["auth"] not in ("password", "cookie", "session")

    def test_the_espn_memo_records_BOTH_the_refusal_and_the_reopening(self):
        """The refusal has to stay an EARNED, written finding — and the correction that re-opened a
        narrower path has to sit beside it, or a later session re-litigates one or the other from
        scratch."""
        memo = (REPO / "docs" / "nf_c0_espn_access_probe.md").read_text()
        assert "NO-GO" in memo
        assert "espn_s2" in memo          # names the specific mechanism it refuses
        assert "NF-C0f" in memo           # names the path that WAS opened
        assert "USER-MEDIATED PASTE" in memo

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

    def test_gated_routes_all_depend_on_the_personalization_gate(self):
        """One `Depends(require_personalized_league_access)` per gated route — importing WRITES a
        user's league config, so the server-side gate is the real one.

        🗄️ THE GATE WIDENED AT G100-C1 (2026-08-08): `require_fantasy_beta_access` (`admin` +
        `fantasy_comp`) → the caller's personalization QUOTA. Import is one of the two ways a free
        account configures the ONE league it is now entitled to, so gating it on a group list would
        have left the free tier with only the manual editor. The COUNT is enforced where a league is
        SAVED (`POST /fantasy/leagues`); a preview writes nothing.

        ⭐ The clause itself is unchanged and is the load-bearing part: EVERY route on the gated
        router carries the dependency, so a new import endpoint cannot ship ungated.
        """
        assert self.SOURCE.count("Depends(require_personalized_league_access)") == len(
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
            "SWID={ABC-123}; espn_s2=zzz",
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
        """🚨 THIS TEST IS WHY THE BUG IT NOW GUARDS SURVIVED TO PRODUCTION (NF-C0e).

        It is named `..._is_applied` but for its whole life it only asserted that a WEIGHT could be
        read back under WHATEVER KEY THE ADAPTER HAPPENED TO WRITE — `per_stat["pass_yd"]`. That is
        a restatement of the code, not a test of it: a mapping table pointing at a key that does not
        exist anywhere in the catalog satisfies it just as happily as a correct one.

        And it was pointing at a key that does not exist. ESPN's ids 3/24/42/72 mapped to `pass_yd`
        / `rush_yd` / `rec_yd` / `fum_lost` — SLEEPER's platform keys — instead of the canonical
        `pass_yds` / `rush_yds` / `rec_yds` / `fumbles_lost` that Sleeper's and Yahoo's adapters both
        map to. Nothing errored, because NF-C0's contract is that an unrecognised key passes through
        verbatim and is reported CAPTURED. So every ESPN-imported league scored ZERO for passing,
        rushing and receiving YARDAGE — the bulk of fantasy points — behind a coverage panel that
        said so and that nobody read.

        The test now asserts the property its NAME claims: the canonical key, and the APPLIED
        VERDICT from the real engine. A wrong key cannot satisfy that, because a key with no
        projection column behind it resolves CAPTURED by construction.
        """
        from app.backend.services.platform_import import espn
        from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

        per_stat = espn.parse_settings_payload(espn_payload).config["scoring"]["per_stat"]
        assert per_stat["pass_yds"] == 0.04
        assert per_stat["pass_td"] == 4.0
        assert per_stat["pass_int"] == -1.0
        assert per_stat["rush_yds"] == 0.1
        assert per_stat["rush_td"] == 6.0
        assert per_stat["rec"] == 1.0          # the league's own playerRankType reads "PPR"
        assert per_stat["rec_yds"] == 0.1
        assert per_stat["rec_td"] == 6.0
        assert per_stat["fumbles_lost"] == -1.0
        # …and none of them are the near-miss spellings that produced the outage.
        for wrong in ("pass_yd", "rush_yd", "rec_yd", "fum_lost"):
            assert wrong not in per_stat, (
                f"{wrong!r} is a PLATFORM key, not a canonical one — it has no projection column, "
                f"so this league's yardage would score ZERO and be reported CAPTURED")

        cfg = LeagueConfig.from_dict(espn.parse_settings_payload(espn_payload).config)
        _, report = presets.resolve_config(cfg)
        verdicts = {t.key: t.verdict for t in report.terms}
        for key in ("pass_yds", "rush_yds", "rec_yds", "rec", "fumbles_lost"):
            assert verdicts[key] == "applied", (
                f"{key} resolved {verdicts[key]!r}; an ESPN league's core yardage must move the "
                f"board, not be stored and ignored")

    def test_unmapped_ids_are_CAPTURED_not_dropped(self, espn_payload):
        """ESPN publishes no stat-id dictionary, so the map is deliberately partial. The contract is
        that everything unmapped is stored faithfully and reported, never silently discarded —
        an unmapped id tells the truth; a guessed id silently misprices the league."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert league.unmapped_scoring_keys, "expected captured terms from a 43-rule league"
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

    def test_the_read_url_asks_for_settings_teams_and_rosters_in_ONE_link(self):
        """ESPN takes repeated `view=` params, so importing rosters costs the user no extra step.
        One link, one paste — the copy burden is what the whole flow is designed around."""
        from app.backend.services.platform_import import espn

        url = espn.build_read_url("998005", 2026)
        assert "leagues/998005?" in url
        for view in ("mSettings", "mTeam", "mRoster"):
            assert f"view={view}" in url

    def test_the_read_url_rejects_a_non_numeric_league_id(self):
        from app.backend.services.platform_import import espn

        for bad in ("../../etc", "998005; rm -rf /", "http://evil", ""):
            with pytest.raises(espn.EspnInputError):
                espn.build_read_url(bad, 2026)

    def test_an_oversized_paste_is_refused_before_parsing(self):
        from app.backend.services.platform_import import espn

        with pytest.raises(espn.EspnInputError):
            espn.parse_settings_payload("x" * (espn.MAX_PASTE_BYTES + 1))


class TestEspnStatIdMapIsVerifiedNotTrusted:
    """The stat-ID map was established by IDENTITIES a wrong map fails, not by a published table
    (ESPN has none). These pin the identities so a future edit can't quietly re-guess an id.

    Values are from a real `kona_player_info` season-projection export (2026, league 998005).
    """

    # Denver D/ST, 2026 season projection: the nine claimed points-allowed buckets in ESPN's order.
    BRONCOS_PA = (0.310716074, 1.40460691, 4.596895343, 3.745618428, 2.468703055,
                  2.851777666, 1.40460691, 0.212819229, 0.004256385)
    BRONCOS_YDS = (0.809320972, 6.304184415, 4.557754949, 3.492858933,
                   1.490854422, 0.255575044, 0.085191681, 0.004259584)

    def test_points_allowed_buckets_partition_the_season(self):
        """THE decisive check: nine buckets that partition 17 games fixes both their IDENTITY and
        their ORDER. A map that mislabels or reorders them cannot sum to 17."""
        assert abs(sum(self.BRONCOS_PA) - 17.0) < 1e-6

    def test_yards_allowed_buckets_partition_the_season(self):
        assert abs(sum(self.BRONCOS_YDS) - 17.0) < 1e-6

    def test_per_game_stats_are_the_season_totals_over_seventeen(self):
        assert abs(317.7855711 / 17 - 18.69326889) < 1e-6   # stat 126 = points allowed per game
        assert abs(5447.733929 / 17 - 320.454937) < 1e-6    # stat 137 = yards allowed per game

    def test_field_goal_buckets_partition_total_made(self):
        """80 (<40) + 77 (40-49) + 74 (50+) == 83 (total FGM), for Brandon Aubrey."""
        assert abs((19.2313044 + 9.2261031 + 7.02552502) - 35.48293252) < 1e-6

    def test_stat_53_is_receptions_despite_its_common_label(self):
        """`receiving_yards / stat_53 == stat_60` (yards per reception) ⇒ 53 IS receptions. It is
        widely labelled "receptions_alternate", and ESPN emits no stat 41 at all — so trusting that
        label would drop PPR scoring, which is exactly what this league sets on 53."""
        assert abs(1589.937424 / 122.9659744 - 12.92989733) < 1e-6
        assert espn_mod().SCORING_KEY_MAP["53"] == ("rec",)

    def test_completions_plus_incompletions_equals_attempts(self):
        assert abs((340.1123125 + 168.7780519) - 508.8903644) < 1e-6


class TestEspnLossyEdgesAreDisclosed:
    """Both edges below change a user's scoring. Neither may be silent."""

    def test_the_points_allowed_boundary_mismatch_is_disclosed(self, espn_payload):
        """🚨 ESPN splits points-allowed at 18-21 / 22-27; our canonical buckets split at
        18-20 / 21-27. (The comment in `sleeper.py` calling these "the common refinement of the
        ESPN and Yahoo schemes" is wrong — they are the YAHOO refinement; a true common refinement
        needs 21 as its own bucket.) Exactly one point value is misplaced, and the user is told."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert any("exactly 21 points" in w for w in league.warnings)

    def test_the_boundary_note_is_SILENT_when_the_two_tiers_pay_the_same(self):
        """A warning that cannot affect the board is noise. If 18-21 and 22-27 carry equal weight
        the misplacement is a no-op and must not be reported."""
        from app.backend.services.platform_import import espn

        translation, warnings = espn.translate_scoring({"121@dst": 2.0, "122@dst": 2.0})
        assert not any("exactly 21 points" in w for w in warnings)
        translation, warnings = espn.translate_scoring({"121@dst": 3.0, "122@dst": 1.0})
        assert any("exactly 21 points" in w for w in warnings)

    def test_disagreeing_two_point_values_are_collapsed_AND_disclosed(self, espn_payload):
        """This real league pays 1.0 for a passing 2-pt but 2.0 for rushing/receiving."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert league.config["scoring"]["per_stat"]["two_pt"] == 2.0
        assert any("two-point conversions" in w for w in league.warnings)

    def test_a_player_return_td_is_never_conflated_with_the_defence_unit(self):
        """Mapping both onto one canonical key double-counts a single return touchdown."""
        from app.backend.services.platform_import import espn

        assert espn.SCORING_KEY_MAP["101"] == ("st_player_td",)
        assert espn.SCORING_KEY_MAP["101@dst"] == ("st_td",)

    def test_the_fine_field_goal_keys_beat_the_coarse_one(self):
        """74 is the coarse 50+ bucket; 198/201 are the fine 50-59 / 60+ pair. A league setting the
        fine keys means them — and which won must not depend on dict ordering."""
        from app.backend.services.platform_import import espn

        flat = {"74": 5.0, "198": 4.0, "201": 6.0}
        translation, _ = espn.translate_scoring(flat)
        assert translation.per_stat["fg_made_50_59"] == 4.0
        assert translation.per_stat["fg_made_60p"] == 6.0

    def test_every_collapse_group_member_is_actually_mapped(self):
        """A group member missing from SCORING_KEY_MAP collapses to an agreed value and is then
        reported CAPTURED anyway — silently inert. The map derives them, so this pins the wiring."""
        from app.backend.services.platform_import import espn

        for target, keys, _label in espn._COLLAPSE_GROUPS:
            for key in keys:
                assert espn.SCORING_KEY_MAP.get(key) == (target,), f"{key} not mapped to {target}"

    def test_a_real_league_applies_most_of_its_rules(self, espn_payload):
        """Regression floor: the first cut applied 12 of 43 rules. Long-TD bonuses stay CAPTURED
        because no projection column exists for them — that is honest, not a gap to paper over."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        per_stat = league.config["scoring"]["per_stat"]
        applied = [k for k in per_stat if not k.split("@")[0].isdigit()]
        assert len(applied) >= 34
        assert set(league.unmapped_scoring_keys) == {"15", "16", "35", "36", "45", "46"}


def espn_mod():
    from app.backend.services.platform_import import espn

    return espn


class TestEspnRouteAndUi:
    """The serving surface for the paste flow (NF-C0f)."""

    ROUTER_SRC = ROUTER.read_text()
    UI = REPO / "frontend" / "components" / "fantasy" / "league-import.tsx"
    CLIENT = REPO / "frontend" / "lib" / "fantasy-import.ts"

    def test_both_espn_routes_exist_and_are_gated(self):
        from app.backend.routers import fantasy_import as fi

        paths = {r.path for r in fi.router.routes}
        assert "/fantasy/import/espn/read-url" in paths
        assert "/fantasy/import/espn/preview" in paths
        # The callback stays the ONLY ungated route — ESPN adds no exemption.
        public = {r.path for r in fi.public_router.routes}
        assert public == {"/fantasy/import/yahoo/callback"}

    def test_a_credential_paste_is_a_422_and_never_reaches_the_logging_fallback(self):
        """🔒 THE ONE THAT MATTERS. `_handle_platform_error`'s fallback calls `logger.exception`,
        which would write the offending paste into CloudWatch — the single place a stray cookie must
        never land. `EspnCredentialPasteError` must be matched BEFORE that fallback."""
        from app.backend.routers import fantasy_import as fi
        from app.backend.services.platform_import import espn

        err = espn.EspnCredentialPasteError("that paste includes your ESPN sign-in cookie")
        mapped = fi._handle_platform_error(err)
        assert mapped.status_code == 422
        assert "sign-in" in str(mapped.detail)

    def test_the_router_never_interpolates_the_pasted_body(self):
        """Source check: no log line or error message may carry the paste."""
        src = self.ROUTER_SRC
        for forbidden in ("payload.payload}", "{payload.payload", "logger.info(payload"):
            assert forbidden not in src

    def test_the_paste_field_has_no_pydantic_max_length(self):
        """A pydantic length rejection produces a `detail` that is a LIST of objects, which
        `apiFetch` deliberately will not surface (see frontend/lib/api.ts) — the user would get a
        bare "API error 422". The adapter's own size check returns an actionable string instead."""
        from app.backend.routers.fantasy_import import EspnPasteRequest

        field = EspnPasteRequest.model_fields["payload"]
        assert all(getattr(m, "max_length", None) is None for m in field.metadata)

    def test_the_ui_no_longer_says_espn_is_unavailable(self):
        """The old copy told users ESPN can't be imported. Leaving it beside a working ESPN option
        would be worse than either state alone."""
        ui = self.UI.read_text()
        assert "ESPN is not listed" not in ui
        assert "espn" in ui.lower()

    def test_the_ui_explains_WHY_the_paste_is_needed(self):
        """Users will ask why ESPN is harder than Sleeper. Saying it plainly is what stops the
        obvious 'just ask for my ESPN login' suggestion — which is the red line."""
        ui = self.UI.read_text()
        assert "Why the copy-paste?" in ui
        assert "read-only" in ui

    def test_the_paste_textarea_is_16px_on_phones(self):
        """iOS auto-zooms any focused input under 16px — the repo's mobile-form guard rule."""
        ui = self.UI.read_text()
        assert "text-base sm:text-xs" in ui or "text-base sm:text-sm" in ui

    def test_the_client_sends_the_season_with_the_paste(self):
        client = self.CLIENT.read_text()
        assert "espn/preview" in client and "espn/read-url" in client


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 7. ESPN — the SECOND real league (NF-C0f follow-up).
#
# The NF-C0 rule that earned this section: "for any third-party-payload adapter, validate against
# ≥2 INDEPENDENTLY-SOURCED real payloads before trusting the field map — a fixture derived from the
# first payload cannot disconfirm it." Sleeper proved that once (the coarse `fgm_50p` vs fine
# `fgm_50_59`/`fgm_60p` bug survived 56 tests and a live-verified league). ESPN proved it again:
# league 642070 scores a whole family — the nine-rung yards-allowed ladder — that league 998005 does
# not contain at all, so no amount of testing against the first payload could have surfaced it.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

ESPN_FIXTURE_2 = Path(__file__).parent / "fixtures" / "espn_league_642070_mSettings_real.json"


@pytest.fixture
def espn_payload_2() -> str:
    """A SECOND real `?view=mSettings` response, from a different 10-team league on a different
    account (financeSettings removed)."""
    return ESPN_FIXTURE_2.read_text()


class TestEspnSecondRealLeague:
    """What the second payload found that the first structurally could not."""

    def test_the_two_real_leagues_exercise_disjoint_scoring_families(
        self, espn_payload, espn_payload_2
    ):
        """The justification for keeping BOTH fixtures, asserted rather than claimed.

        If this ever fails because the two payloads have converged, the second fixture has stopped
        buying coverage and a genuinely different third league should replace it.
        """
        def ids(raw: str) -> set[int]:
            items = json.loads(raw)["settings"]["scoringSettings"]["scoringItems"]
            return {int(i["statId"]) for i in items}

        one, two = ids(espn_payload), ids(espn_payload_2)
        # Each league scores rules the other does not have at all.
        assert one - two, "league 1 no longer contributes any unique scoring rule"
        assert two - one, "league 2 no longer contributes any unique scoring rule"
        # Specifically: the yards-allowed ladder exists ONLY in league 2, and the points-allowed
        # 18-21 / 22-27 tiers ONLY in league 1. Those are the two findings this section pins.
        assert {128, 129, 130, 132, 133, 134, 135, 136} <= two - one
        assert {121, 122} <= one - two

    def test_the_second_league_imports(self, espn_payload_2):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_2)
        assert league.platform == "espn"
        assert league.source_league_id == "642070"
        assert league.season == "2026"
        assert league.config["n_teams"] == 10
        starters = {s["name"]: s["count"] for s in league.config["roster"] if not s["bench"]}
        assert starters == {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "K": 1, "DST": 1}
        # Half-PPR — a different setting from league 1, so the reception weight is read and not
        # defaulted.
        assert league.config["scoring"]["per_stat"]["rec"] == 0.5

    def test_the_position_override_trap_is_avoided_on_a_second_league(self, espn_payload_2):
        """The single highest-consequence behaviour, re-proven on an independent payload.

        Seven points-allowed rules in this league carry `points: 0.0` with their real value only in
        `pointsOverrides["16"]`. A parser reading `points` scores the whole tier table as zero while
        reporting it APPLIED — indistinguishable from working.
        """
        from app.backend.services.platform_import import espn

        per_stat = espn.parse_settings_payload(espn_payload_2).config["scoring"]["per_stat"]
        assert per_stat["dst_pa_g_0"] == 5.0
        assert per_stat["dst_pa_g_1_6"] == 4.0
        assert per_stat["dst_pa_g_7_13"] == 3.0
        assert per_stat["dst_pa_g_14_17"] == 1.0
        assert per_stat["dst_pa_g_28_34"] == -1.0
        assert per_stat["dst_pa_g_35_45"] == -3.0
        assert per_stat["dst_pa_g_46p"] == -5.0
        # …and the sacks/int/safety block, likewise override-only.
        assert per_stat["def_sacks"] == 1.0
        assert per_stat["def_int"] == 2.0
        assert per_stat["def_safety"] == 2.0

    def test_the_fine_field_goal_pair_is_read_without_the_coarse_bucket(self, espn_payload_2):
        """This league sets 198/201 and no 74 — the mirror of the case `_drop_coarse_when_fine_
        present` exists for, so it proves the fine keys stand on their own."""
        from app.backend.services.platform_import import espn

        per_stat = espn.parse_settings_payload(espn_payload_2).config["scoring"]["per_stat"]
        assert per_stat["fg_made_50_59"] == 5.0
        assert per_stat["fg_made_60p"] == 5.0
        assert per_stat["fg_made_40_49"] == 4.0
        # The coarse sub-40 bucket fans out across all three of ours — an exact restatement.
        assert per_stat["fg_made_0_19"] == per_stat["fg_made_20_29"] == 3.0
        assert per_stat["fg_made_30_39"] == 3.0

    def test_yards_allowed_is_now_APPLIED_on_the_right_rungs(self, espn_payload_2):
        """⭐ NF-C0e INVERTED THIS TEST ON PURPOSE — it used to assert the ladder was CAPTURED.

        That was the honest verdict while no yards-allowed column existed. NF-C0e projects the nine
        `proj_dst_ya_g_*` expected-games columns, so the same nine ids now resolve to real canonical
        keys and the league's own tier table is applied exactly.

        The failure being guarded is unchanged in SPIRIT and is now the more dangerous direction: a
        mapped ladder must land on the CORRECT RUNG. Reporting APPLIED while paying the "under 100
        yards" bonus for a 550-yard game would be far worse than the old honest CAPTURED, so this
        pins the two ENDPOINTS (which fix the ladder's direction) rather than merely its membership.
        """
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_2)
        per_stat = league.config["scoring"]["per_stat"]
        # the nine rungs are gone from the raw-key namespace…
        assert not any(k.endswith("@dst") and k[:3].isdigit() and 128 <= int(k[:3]) <= 136
                       for k in per_stat)
        assert not any(f"{i}@dst" in league.unmapped_scoring_keys for i in range(128, 137))
        # …and land on the canonical keys, with the ladder the RIGHT WAY UP.
        assert per_stat["dst_ya_g_0_99"] == 5.0        # ESPN 128, the BEST rung
        assert per_stat["dst_ya_g_550p"] == -7.0       # ESPN 136, the WORST rung
        assert per_stat["dst_ya_g_100_199"] == 3.0
        assert per_stat["dst_ya_g_450_499"] == -5.0
        # The ladder is monotone non-increasing, which a shuffled map could not satisfy. Read only
        # the rungs the league actually SETS: 642070 omits the 300-349 rung entirely (it scores 0
        # there), and demanding every rung be present would fail on a real league's real settings.
        order = ("0_99", "100_199", "200_299", "300_349", "350_399",
                 "400_449", "450_499", "500_549", "550p")
        rungs = [per_stat[f"dst_ya_g_{b}"] for b in order if f"dst_ya_g_{b}" in per_stat]
        assert len(rungs) >= 8, f"expected ESPN's nine-rung ladder, got {len(rungs)}"
        assert rungs == sorted(rungs, reverse=True), rungs

    def test_the_stale_yards_allowed_caveat_is_GONE_not_reworded(self, espn_payload_2):
        """The old warning told the user "We don't project yards allowed … a defence that wins by
        suppressing yardage will be under-rated on your board." That is now FALSE.

        A caveat that has stopped being true is not harmlessly stale — it tells the user their board
        ignores a rule it actually applies, which is the same class of wrong as claiming to apply
        one we ignore. So it must be DELETED, and this asserts its absence rather than its wording.
        """
        from app.backend.services.platform_import import espn

        warnings = espn.parse_settings_payload(espn_payload_2).warnings
        assert not [w for w in warnings if "yards allowed" in w.lower()], warnings
        assert not [w for w in warnings if "under-rated" in w.lower()], warnings

    def test_the_points_allowed_boundary_note_is_likewise_conditional(self, espn_payload_2):
        """League 2 scores neither the 18-21 nor the 22-27 tier, so the 21-point misplacement
        cannot affect it and is not raised."""
        from app.backend.services.platform_import import espn

        warnings = espn.parse_settings_payload(espn_payload_2).warnings
        assert not [w for w in warnings if "exactly 21 points" in w]


class TestEspnCapturedKeysAreLegible:
    """A captured rule is only honest if the user can tell WHAT was captured.

    Sleeper and Yahoo name their rules in words; ESPN numbers them, so an unlabelled panel reports
    "129@dst · 3.00" — which discloses nothing and reads as noise rather than as the disclosure it
    is meant to be.
    """

    @pytest.mark.parametrize("fixture_name", ["espn_payload", "espn_payload_2"])
    def test_every_captured_key_in_a_real_league_has_a_label(self, fixture_name, request):
        """The invariant that keeps the panel legible as the map grows: if a future ESPN id starts
        appearing as CAPTURED, it must arrive with a human label in the same change."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(request.getfixturevalue(fixture_name))
        labels = league.to_dict()["unmapped_labels"]
        missing = [k for k in league.unmapped_scoring_keys if not labels.get(k)]
        assert not missing, f"captured ESPN keys with no human label: {missing}"

    def test_labels_are_sent_only_for_keys_this_league_actually_captured(self, espn_payload_2):
        """Never explain a rule the user does not have."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_2)
        assert set(league.to_dict()["unmapped_labels"]) == set(league.unmapped_scoring_keys)

    def test_labels_do_not_invent_a_boundary_we_never_verified(self):
        """⭐ The display-layer form of this map's "verified, not trusted" rule.

        NF-C0e moved which keys this applies to, and the move is the interesting part. The
        YARDS-ALLOWED ladder used to be the motivating case: its order was verified and its cut
        points were not, so its labels named no numbers. Sleeper's self-describing keys then
        supplied the missing half from a second independent payload, the nine ids became APPLIED,
        and they left `CAPTURED_LABELS` entirely.

        The LONG-TD pairs did NOT get that second source: 15/16 (and 35/36, 45/46) are a 40+ and a
        50+ bonus and no payload we hold distinguishes them. So the rule now guards them instead —
        and it must, because the 40+ column exists now, which makes guessing tempting in a way it
        was not before. A label reading "50+ yard TD bonus" would be a guess shown to a user as
        fact; a digit in one of these labels is the smell.
        """
        from app.backend.services.platform_import import espn

        long_td_keys = ("15", "16", "35", "36", "45", "46")
        for key in long_td_keys:
            label = espn.CAPTURED_LABELS[key]
            assert not re.search(r"\d", label), f"{key} label asserts a boundary: {label!r}"
        # The yards ids must have LEFT the captured-label table — a label for an APPLIED term is a
        # stale claim that the term is not applied.
        for key in espn._YARDS_ALLOWED_KEYS:
            assert key not in espn.CAPTURED_LABELS, (
                f"{key} is APPLIED now; a 'captured' label for it tells the user the opposite")

    def test_the_label_field_is_additive_so_an_older_client_still_renders(self):
        """NF-C0's deploy-skew rule: the API and the frontend ship independently. A client that
        has never heard of `unmapped_labels` must fall back to the raw key, not a blank row."""
        ui = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "components"
            / "fantasy"
            / "league-import.tsx"
        ).read_text()
        assert "preview.unmapped_labels?.[t.key] ?? t.key" in ui

    def test_the_other_adapters_are_unaffected(self):
        """Sleeper and Yahoo keys are already words, so they send no labels — and the field must
        default rather than force every adapter to opt in."""
        league = C.ImportedLeague(
            platform="sleeper", source_league_id="1", season="2026", config={}
        )
        assert league.to_dict()["unmapped_labels"] == {}


class TestEspnRosterImport:
    """Rosters from the `mTeam` + `mRoster` views.

    ⏳ **The PRE-DRAFT case is the normal case.** People import BEFORE their draft — that is when a
    draft tool earns its keep — and an undrafted ESPN league returns teams with EMPTY rosters. Both
    current-season fixtures are undrafted, so that is what this class covers. The POPULATED path is
    validated separately in `TestEspnDraftedRealLeague` against a real prior-season payload; the
    hand-built entries below deliberately remain, because they cover malformed and edge-shaped rows
    that a well-formed real payload does not contain.
    """

    def test_a_settings_only_payload_still_imports_cleanly(self, espn_payload):
        """An older single-view link, or any response without `teams`, must remain a COMPLETE
        settings import — rosters are additive, never a new precondition."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload)
        assert league.teams == ()
        assert league.config["scoring"]["per_stat"]  # the real import is untouched
        assert not [w for w in league.warnings if "hasn't drafted" in w]

    def test_an_undrafted_league_reports_it_as_expected_not_as_a_failure(self):
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [
            {"id": 1, "name": "Team One", "owners": ["{GUID-1}"], "roster": {"entries": []}},
            {"id": 2, "location": "Team", "nickname": "Two", "owners": ["{GUID-2}"]},
        ]
        payload["members"] = [
            {"id": "{GUID-1}", "displayName": "alice"},
            {"id": "{GUID-2}", "displayName": "bob"},
        ]
        league = espn.parse_settings_payload(json.dumps(payload))

        assert [t.name for t in league.teams] == ["Team One", "Team Two"]
        assert [t.owner for t in league.teams] == ["alice", "bob"]
        assert all(t.players == () for t in league.teams)
        note = [w for w in league.warnings if "hasn't drafted" in w]
        assert len(note) == 1
        # It must tell the user what to DO, not merely that something is missing.
        assert "Import again after your draft" in note[0]

    def test_a_member_guid_is_used_as_a_label_and_then_dropped(self):
        """A SWID GUID identifies a real ESPN account. It is not a credential — but "not a
        credential" is not a reason to keep it."""
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [{"id": 1, "name": "T", "owners": ["{SECRET-GUID}"]}]
        payload["members"] = [{"id": "{SECRET-GUID}", "displayName": "alice"}]
        league = espn.parse_settings_payload(json.dumps(payload))

        assert league.teams[0].owner == "alice"
        assert "SECRET-GUID" not in json.dumps(league.to_dict())

    def test_nobody_is_marked_as_the_importing_user(self):
        """ESPN's response never says which team belongs to the requesting account, and we
        deliberately do not hold the credential that would tell us. Guessing would be worse."""
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [
            {"id": i, "name": f"T{i}", "roster": {"entries": [_espn_entry(i)]}} for i in (1, 2)
        ]
        league = espn.parse_settings_payload(json.dumps(payload))
        assert not any(t.is_owner for t in league.teams)
        assert [w for w in league.warnings if "which of these teams is yours" in w]

    # ── the POPULATED path — shape-plausible, NOT yet real-payload validated ────────────────────

    def test_a_rostered_player_is_read_with_position_and_starter_flag(self):
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [
            {
                "id": 7,
                "name": "Roster Test",
                "roster": {
                    "entries": [
                        _espn_entry(3139477, "Patrick Mahomes", slots=[0, 20, 21], lineup=0, pro=12),
                        _espn_entry(4262921, "Bench Back", slots=[2, 3, 23, 20, 21], lineup=20, pro=9),
                    ]
                },
            }
        ]
        league = espn.parse_settings_payload(json.dumps(payload))
        players = {p.name: p for p in league.teams[0].players}

        assert players["Patrick Mahomes"].position == "QB"
        assert players["Patrick Mahomes"].starter is True
        assert players["Bench Back"].position == "RB"
        assert players["Bench Back"].starter is False
        assert not [w for w in league.warnings if "hasn't drafted" in w]

    def test_position_comes_from_the_ALREADY_VERIFIED_slot_map(self):
        """⭐ Derived from `eligibleSlots` against `ROSTER_SLOT_MAP`, which the settings work already
        established — NOT from ESPN's separate `defaultPositionId` table, which is a second
        numbering with no identity to check it against. Reusing verified evidence beats importing a
        new guess."""
        from app.backend.services.platform_import import espn

        for slot, expected in ((0, "QB"), (2, "RB"), (4, "WR"), (6, "TE"), (16, "DST"), (17, "K")):
            assert espn._player_position({"eligibleSlots": [slot, 20, 21]}) == expected
        # A bench-only or unrecognised player yields None rather than a fabricated position.
        assert espn._player_position({"eligibleSlots": [20, 21]}) is None
        assert espn._player_position({}) is None
        # Slot 1 is TQB — a whole-team QB slot, not an individual's position.
        assert 1 not in espn._POSITION_BY_SLOT

    def test_an_unknown_pro_team_id_yields_none_rather_than_a_guess(self):
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [
            {"id": 1, "name": "T", "roster": {"entries": [_espn_entry(1, "Nobody", pro=999)]}}
        ]
        league = espn.parse_settings_payload(json.dumps(payload))
        assert league.teams[0].players[0].team is None

    def test_a_malformed_roster_entry_costs_only_itself(self):
        """The E9.49 row-by-row rule: one bad entry must never blank a whole roster."""
        from app.backend.services.platform_import import espn

        payload = json.loads(ESPN_FIXTURE_2.read_text())
        payload["teams"] = [
            {
                "id": 1,
                "name": "T",
                "roster": {
                    "entries": [
                        "not-a-dict",
                        {"playerPoolEntry": None},
                        {"playerPoolEntry": {"player": {"fullName": ""}}},
                        _espn_entry(5, "Good Player", slots=[4, 20], lineup=4, pro=21),
                    ]
                },
            }
        ]
        league = espn.parse_settings_payload(json.dumps(payload))
        assert [p.name for p in league.teams[0].players] == ["Good Player"]


class TestEspnScrubberStillRefusesEveryRealCredentialPaste:
    """The SWID pattern was narrowed to the cookie-assignment form when `mTeam` was added. That is a
    security-guard change, so the guard's real job is re-proven here rather than assumed."""

    @pytest.mark.parametrize(
        "curl",
        [
            "curl 'https://lm-api-reads.fantasy.espn.com/x' -H 'Cookie: SWID={A}; espn_s2=AEBdead'",
            "curl 'https://x' -H 'cookie: espn_s2=AEBdead; SWID={A}'",
            "GET /x\nCookie: SWID={A}; espn_s2=AEBdead",
        ],
    )
    def test_a_real_devtools_copy_is_still_refused(self, curl):
        from app.backend.services.platform_import import espn

        with pytest.raises(espn.EspnCredentialPasteError):
            espn.assert_no_credentials(curl)

    def test_the_narrowing_cannot_let_the_actual_credential_through(self):
        """`espn_s2` is the session credential and is matched ANYWHERE, in any syntax — the
        narrowing applies only to SWID, which is an identifier."""
        from app.backend.services.platform_import import espn

        for text in ('{"espn_s2": "AEBdead"}', "espn_s2=AEBdead", "ESPN_S2 AEBdead"):
            with pytest.raises(espn.EspnCredentialPasteError):
                espn.assert_no_credentials(text)

    def test_a_bare_swid_identifier_no_longer_false_refuses_an_honest_paste(self):
        """⚠️ THE REASON FOR THE NARROWING. `mTeam` returns `members[].id` as a SWID GUID, so a
        pattern matching the bare word would reject every honest ESPN import — with a message
        accusing the user of pasting credentials. A GUID cannot authenticate without `espn_s2`."""
        from app.backend.services.platform_import import espn

        espn.assert_no_credentials('{"members": [{"id": "{7B2A-SWID-LOOKING-GUID}"}]}')

    def test_the_real_payloads_pass_the_scrubber(self, espn_payload, espn_payload_2):
        from app.backend.services.platform_import import espn

        espn.assert_no_credentials(espn_payload)
        espn.assert_no_credentials(espn_payload_2)


def _espn_entry(
    player_id: int,
    name: str = "Player",
    *,
    slots: list[int] | None = None,
    lineup: int = 20,
    pro: int = 12,
) -> dict:
    """A hand-built ESPN roster entry. Its field names ARE now confirmed (see
    `TestEspnDraftedRealLeague`, built from a real prior-season payload); this helper exists to
    construct the MALFORMED and edge-shaped rows a well-formed real payload cannot supply."""
    return {
        "lineupSlotId": lineup,
        "playerPoolEntry": {
            "player": {
                "id": player_id,
                "fullName": name,
                "eligibleSlots": slots if slots is not None else [0, 20, 21],
                "proTeamId": pro,
            }
        },
    }


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 8. ESPN — the DRAFTED league (a PRIOR SEASON, which is how a rostered payload was obtainable at
#    all: both current-season leagues are undrafted). Real structure and real players; the members
#    block is anonymised because the real one carries the operator's leaguemates' names and ESPN
#    account GUIDs, which are not ours to commit. The GUID SHAPE is preserved, since that is what
#    the parser and the credential scrubber actually have to handle.
# ══════════════════════════════════════════════════════════════════════════════════════════════════

ESPN_FIXTURE_DRAFTED = Path(__file__).parent / "fixtures" / "espn_league_642070_2025_drafted.json"


@pytest.fixture
def espn_payload_drafted() -> str:
    return ESPN_FIXTURE_DRAFTED.read_text()


class TestEspnDraftedRealLeague:
    """The populated-roster path, against a real payload rather than the author's guess."""

    # The seven real entries, with the position and pro team each ACTUALLY had in 2025.
    REAL = [
        ("Josh Jacobs", "RB", "GB", True),
        ("Davante Adams", "WR", "LAR", False),
        ("George Kittle", "TE", "SF", True),
        ("Kenneth Walker III", "RB", "SEA", True),
        ("Tetairoa McMillan", "WR", "CAR", True),
        ("Patrick Mahomes", "QB", "KC", False),   # on IR (lineupSlotId 21)
        ("Mark Andrews", "TE", "BAL", False),
    ]

    def test_every_real_player_reads_correctly(self, espn_payload_drafted):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_drafted)
        got = {p.name: p for p in (pl for t in league.teams for pl in t.players)}
        assert len(got) >= 160, "the full 10-team roster set should be present"
        for name, position, team, starter in self.REAL:
            assert got[name].position == position, name
            assert got[name].team == team, name
            assert got[name].starter is starter, name

    def test_pro_team_ids_are_pinned_against_a_real_payload(self, espn_payload_drafted):
        """⭐ The promised upgrade from "plausible" to "identity-checked".

        `_PRO_TEAM_BY_ID` shipped at a deliberately lower evidence bar than the scoring map, on the
        argument that a wrong abbreviation is cosmetic where a wrong stat id misprices a league.
        Seven real players now confirm seven of its rows by identity — the same discipline the
        scoring map was held to, applied as soon as the evidence existed.
        """
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_drafted)
        by_name = {p.name: p.team for t in league.teams for p in t.players}
        assert {n: by_name[n] for n, _p, _t, _s in self.REAL} == {
            n: t for n, _p, t, _s in self.REAL
        }
        # An id outside the table must stay None rather than become a neighbouring team.
        assert espn._PRO_TEAM_BY_ID.get(999) is None

    def test_espn_position_ids_are_a_DIFFERENT_numbering_from_lineup_slots(self):
        """🪤 THE NEAR-MISS THIS FIXTURE CAUGHT — do not "simplify" position derivation to use
        `defaultPositionId`.

        The two numberings overlap enough to look interchangeable and are not: `defaultPositionId`
        4 means TE, while lineup SLOT 4 means WR. Reading ESPN's position id against the slot map
        would have labelled George Kittle and Mark Andrews **WR**, and left Mahomes, Adams and
        McMillan with **no position at all** — silently, on a roster we display. Deriving from
        `eligibleSlots` against the map the settings work already verified is what avoids it.
        """
        from app.backend.services.platform_import import espn

        # The collision, stated as an assertion so it cannot be re-argued from memory.
        assert espn._POSITION_BY_SLOT[4] == "WR"      # lineup slot 4
        assert espn._POSITION_BY_SLOT[6] == "TE"      # lineup slot 6
        # ESPN's defaultPositionId 4 is a TIGHT END. Kittle carries it and must still read as TE.
        kittle = {"defaultPositionId": 4, "eligibleSlots": [5, 6, 23, 7, 20, 21]}
        assert espn._player_position(kittle) == "TE"
        # defaultPositionId 3 (WR) is not even a single-position lineup slot — slot 3 is RB/WR.
        assert 3 not in espn._POSITION_BY_SLOT

    def test_an_unknown_eligible_slot_does_not_break_derivation(self, espn_payload_drafted):
        """The real payload carries slot 25 (McMillan) — an id absent from `ROSTER_SLOT_MAP`. An
        unrecognised eligibility must be ignored, never allowed to blank a known position."""
        from app.backend.services.platform_import import espn

        assert 25 not in espn._POSITION_BY_SLOT
        league = espn.parse_settings_payload(espn_payload_drafted)
        mcmillan = next(p for p in league.teams[0].players if p.name == "Tetairoa McMillan")
        assert mcmillan.position == "WR"

    def test_a_drafted_league_does_not_get_the_pre_draft_note(self, espn_payload_drafted):
        from app.backend.services.platform_import import espn

        warnings = espn.parse_settings_payload(espn_payload_drafted).warnings
        assert not [w for w in warnings if "hasn't drafted" in w]
        assert [w for w in warnings if "which of these teams is yours" in w]

    def test_a_real_guid_bearing_payload_passes_the_credential_scrubber(self, espn_payload_drafted):
        """The concrete reason the bare-`SWID` pattern had to be narrowed: `mTeam` really does
        return member ids in SWID GUID form, on every ESPN league."""
        from app.backend.services.platform_import import espn

        assert '"id": "{' in espn_payload_drafted  # the GUID shape is genuinely present
        espn.assert_no_credentials(espn_payload_drafted)

    def test_member_identity_never_reaches_the_response(self, espn_payload_drafted):
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_drafted)
        out = json.dumps(league.to_dict())
        assert "manager1" in out                     # the display name labels the team…
        assert "-4000-8000-" not in out              # …and the account GUID is dropped
        assert "Last1" not in out                    # as is the member's surname

    def test_the_whole_league_parses_with_no_gaps(self, espn_payload_drafted):
        """172 real roster entries across 10 teams. A player who reads with no position or no pro
        team is a silent hole on a roster we display, so the bar is zero of either."""
        from app.backend.services.platform_import import espn

        league = espn.parse_settings_payload(espn_payload_drafted)
        players = [p for t in league.teams for p in t.players]
        assert len(league.teams) == 10
        assert len(players) == 172
        assert [p.name for p in players if not p.position] == []
        assert [p.name for p in players if not p.team] == []
        assert all(t.name for t in league.teams)

    def test_kickers_and_team_defenses_read_correctly(self, espn_payload_drafted):
        """⭐ The two shapes the FIRST look at this payload could not reach — the visible portion
        contained only QB/RB/WR/TE. A D/ST is not a person but a TEAM (`fullName` "Packers D/ST",
        a NEGATIVE player id), so it is the entry most likely to fall through name/position
        handling written for skill players."""
        from app.backend.services.platform_import import espn

        players = [p for t in espn.parse_settings_payload(espn_payload_drafted).teams
                   for p in t.players]
        by_pos = {}
        for p in players:
            by_pos.setdefault(p.position, []).append(p)

        assert len(by_pos["K"]) == 13
        assert len(by_pos["DST"]) == 15
        # Every D/ST names its own club and carries that club's proTeamId — so each is a free
        # identity check on `_PRO_TEAM_BY_ID`, and all 15 must agree.
        for dst in by_pos["DST"]:
            assert dst.name.endswith("D/ST"), dst.name
            assert dst.team, dst.name
        packers = next(p for p in by_pos["DST"] if p.name.startswith("Packers"))
        assert packers.team == "GB"
        # A D/ST id is NEGATIVE in ESPN's namespace; it must survive as an opaque key.
        assert packers.player_key.startswith("-")

    def test_every_pro_team_id_in_a_real_league_is_mapped(self, espn_payload_drafted):
        """A 10-team drafted league touches all 32 clubs, so this exercises the whole table."""
        from app.backend.services.platform_import import espn

        doc = json.loads(espn_payload_drafted)
        ids = {int(e["playerPoolEntry"]["player"]["proTeamId"])
               for t in doc["teams"] for e in (t.get("roster") or {}).get("entries", [])}
        assert len(ids) == 32
        assert not [i for i in ids if i not in espn._PRO_TEAM_BY_ID]


class TestEspnPayloadIsPrunedBeforeUpload:
    """The client drops per-player bulk the import never reads before uploading a paste.

    ⚠️ THE SIZE FIGURES PREVIOUSLY QUOTED HERE ARE NOT REPRODUCED. This said "3.3 MB, 82% of the cap
    at 10 teams, ~99% at 12, OVER THE CAP at 14". ESPN-PRUNER captured a real un-pruned drafted
    10-team response and measured **834 KB (20.9% of the cap) → 131 KB pruned**, i.e. a 6.4×
    reduction, with 12- and 14-team scalings at 24.1% and 28.1% — nowhere near the cap. So pruning
    is NOT today load-bearing for import to work; it is a 6.4× reduction worth keeping on its own
    terms. The capture is a COMPLETED season (5 stat splits per player, zero `outlooks`); an
    in-season response may be far larger, which is unmeasured. See `fantasy-import.ts`.
    """

    CLIENT = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "fantasy-import.ts"

    def test_the_client_prunes_before_posting(self):
        src = self.CLIENT.read_text()
        assert "export function pruneEspnPayload" in src
        assert "payload: pruneEspnPayload(payload)" in src, "prune is defined but not applied"

    def test_only_verified_unread_fields_are_dropped(self):
        """Each name here must be a field the PARSER never touches. If the adapter ever starts
        reading one, it has to come off this list in the same change."""
        from app.backend.services.platform_import import espn

        src = self.CLIENT.read_text()
        adapter = Path(espn.__file__).read_text()
        for field in ("stats", "draftRanksByRankType", "ownership", "outlooks",
                      "ratings", "notificationSettings"):
            assert field in src, f"{field} no longer pruned"
            assert f'"{field}"' not in adapter and f"'{field}'" not in adapter, (
                f"the adapter now reads {field!r} — it must not be pruned client-side"
            )

    def test_it_is_a_denylist_not_an_allowlist(self):
        """The API and the frontend deploy independently, so a client that kept ONLY today's known
        fields would silently starve a newer server of one it had begun to read. Removing just the
        verified-unread fields is safe in both skew directions."""
        src = self.CLIENT.read_text()
        assert "DENYLIST, NOT AN ALLOWLIST" in src

    def test_a_non_json_paste_is_passed_through_untouched(self):
        """A pruning bug must never turn a good paste into a rejected one, and a cURL paste must
        still reach the server's credential scrubber rather than dying in the client."""
        src = self.CLIENT.read_text()
        assert "return text" in src and "catch" in src

    def test_pruning_does_not_change_what_gets_imported(self, espn_payload_drafted):
        """⭐ THE INVARIANT THAT MATTERS. The committed fixture IS the pruned shape; parsing it must
        produce the same league the untrimmed response would. Proven here by re-pruning an already
        pruned payload — IDEMPOTENCE, which is a proxy: a pruner deleting the WRONG subtree is
        perfectly idempotent while destroying the league.

        ⭐ The real claim is now tested directly against a committed un-pruned capture (834 KB, not
        the 3.3 MB this docstring used to cite as too large to commit) — see
        `test_espn_pruner_raw_capture.py::TestPruningDoesNotChangeWhatGetsImported`. This stays as
        the idempotence half."""
        from app.backend.services.platform_import import espn

        doc = json.loads(espn_payload_drafted)
        for m in doc.get("members") or []:
            m.pop("notificationSettings", None)
        for t in doc.get("teams") or []:
            for e in ((t.get("roster") or {}).get("entries") or []):
                pool = e.get("playerPoolEntry") or {}
                pool.pop("ratings", None)
                for f in ("stats", "draftRanksByRankType", "ownership", "outlooks"):
                    (pool.get("player") or {}).pop(f, None)

        again = espn.parse_settings_payload(json.dumps(doc))
        assert again.to_dict() == espn.parse_settings_payload(espn_payload_drafted).to_dict()

    def test_the_pruned_fixture_is_small_enough_for_a_big_league(self, espn_payload_drafted):
        """A 10-team league pruned, scaled to 16 teams, must sit far under the cap — the headroom
        this whole class exists to create."""
        from app.backend.services.platform_import import espn

        pruned = len(espn_payload_drafted.encode())
        assert pruned < 400_000, f"pruned fixture unexpectedly large: {pruned:,}"
        assert pruned / 10 * 16 < espn.MAX_PASTE_BYTES / 4


# ── PERF (2026-08-11): the import page's projections fetch ───────────────────────────────────────
class TestTheProjectionsFetchIsDeferredAndNeverGuessed:
    """The ~647 KB projections payload must not be fetched at mount, and its ABSENCE must never be
    resolved into an optimistic coverage report.

    WHY BOTH CLAUSES LIVE TOGETHER. Deferring the fetch is a performance change; on its own it would
    have introduced a correctness bug, because `resolveScoring` reads a missing `availableFields` as
    "every field exists" (`availableFields ? has(field) : true`). A preview arriving before the
    payload would then print every scoring term as "applied" — including terms we do not project —
    which is the exact claim `league-import.tsx`'s own docstring says this surface may never make
    ("this surface cannot promote a term by asserting it").

    ⭐ The second clause is NOT merely protecting the first: the pre-deferral code passed `undefined`
    on the FAILURE path too, so a 404 or an errored projections fetch already produced a silent
    all-"applied" report. Deferring made a latent bug reachable, and fixing it closed both.
    """

    UI = Path(__file__).resolve().parents[2] / "frontend" / "components" / "fantasy" / "league-import.tsx"
    QUERIES = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "fantasy-queries.ts"

    def test_the_import_page_does_not_fetch_projections_at_mount(self):
        """`useFantasyProjections` must be called with an explicit gate, not bare.

        A bare `useFantasyProjections()` fires on mount, racing `/fantasy/leagues` and
        `/fantasy/import/platforms` into a Lambda whose cold init measured ~4 s — and on an idle
        function each parallel request pays that cost on its OWN container.
        """
        ui = self.UI.read_text()
        assert "useFantasyProjections(" in ui, "wrong file, or the hook was renamed"
        # The gate is the second argument. A bare call — `useFantasyProjections()` — is the
        # regression: it restores the mount-time fetch.
        assert not re.search(r"useFantasyProjections\(\s*\)", ui), (
            "league-import.tsx calls useFantasyProjections() with no `enabled` gate, so the ~647 KB "
            "payload is fetched at mount again. Pass the flow-started flag as the second argument."
        )
        assert re.search(r"useFantasyProjections\(\s*undefined\s*,\s*flowStarted\s*\)", ui), (
            "the projections gate is no longer `flowStarted` — if the trigger moved, re-check that "
            "it still fires before a preview can exist, or the coverage panel will block on a "
            "647 KB download at the moment the user is waiting to read it"
        )
        assert "setFlowStarted(true)" in ui, "nothing ever starts the deferred fetch"

    def test_coverage_is_not_computed_without_the_projection_columns(self):
        """The resolver must not run until `projections.players` is really present.

        This is the clause that keeps the verdict honest; `availableFields` defaulting to "has
        everything" is what makes an early or failed fetch produce a wrong, confident answer.
        """
        ui = self.UI.read_text()
        memo = ui.split("const coverage = useMemo(")[1].split("}, [")[0]
        assert "if (!projections?.players) return null" in memo, (
            "the coverage useMemo resolves scoring without proving the projection columns loaded. "
            "resolveScoring treats a missing availableFields as 'every field exists', so this "
            "prints every term as 'applied' — including ones we do not project."
        )
        # The optimistic call shape must be gone, not merely guarded above.
        assert "availableFields: projections?.players ?" not in memo, (
            "the conditional/undefined availableFields form is back; pass the real Set only"
        )
        # Non-vacuity: we really parsed the memo body, not an empty string.
        assert "resolveScoring(" in memo, "coverage useMemo body not parsed — guard is vacuous"

    def test_the_shared_hook_keeps_fetching_on_mount_by_default(self):
        """`enabled` is ADDITIVE. Six other surfaces render this payload as their primary content
        and must be unaffected — a default of `false` would blank all of them."""
        src = self.QUERIES.read_text()
        assert re.search(
            r"export function useFantasyProjections\(\s*season[^,]*,\s*enabled:\s*boolean\s*=\s*true\s*\)",
            src,
        ), "useFantasyProjections' `enabled` parameter must default to true"
