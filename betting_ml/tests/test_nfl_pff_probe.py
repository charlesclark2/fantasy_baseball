"""NF-W9-0 — guards for the PFF feasibility probe.

FAST-GATE SAFE BY CONSTRUCTION: no `pipeline` import, no network, no real lake. Every fixture
is a synthetic frame — a fast-gate test that calls the real `duck()`/lake passes on a
credentialed laptop and fails in CI (the E11.24 lesson), so the lake is never touched here.

The properties under test are the ones whose failure would be SILENT: a grade column that
slips through, an auth failure that looks like an empty day, and an ambiguous vendor id that
gets arbitrated into a wrong merge.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from quant_sports_intel_models.football.pff import facets as fx
from quant_sports_intel_models.football.pff import guards as g
from quant_sports_intel_models.football.pff.client import (
    PFFAuthError, PFFChallengeError, PFFClient, PFFClientError, _parse_response, sample_filename,
)
from quant_sports_intel_models.football.pff.probe import normalise_rows, run_league
from quant_sports_intel_models.football.pff.resolve import (
    build_pff_crosswalk, id_space_agreement, match_report, resolve_games, resolve_nfl_players,
)


# ── the RAW-STATS-ONLY boundary ────────────────────────────────────────────────────────────
class TestRawStatsOnlyGuard:
    @pytest.mark.parametrize("col", [
        "grades_offense", "pass_grades_rate", "player_rank", "pff_projection",
        "projected_points", "wins_above_replacement", "predicted_yards",
    ])
    def test_model_output_columns_are_dropped(self, col):
        assert g.is_model_output_column(col), f"{col} is PFF model output and must be stripped"

    @pytest.mark.parametrize("col", [
        # The token-boundary cases. A raw substring scan for "grade"/"rank"/"war" would
        # false-fire on every one of these — the NF-W7 `'temp' ⊂ 'attempt'` trap.
        "downgrade", "franchise_id", "yards_after_contact", "targets", "routes",
        "forward_progress", "warmup_snaps",
    ])
    def test_legitimate_raw_columns_survive(self, col):
        assert not g.is_model_output_column(col), f"{col} is a RAW stat and must survive"

    def test_forbidden_endpoint_is_refused(self):
        with pytest.raises(g.ForbiddenEndpointError):
            g.assert_endpoint_allowed("/api/v1/facet/receiving/projections")
        with pytest.raises(g.ForbiddenEndpointError):
            g.assert_endpoint_allowed("/api/v1/rankings/big-board")

    def test_raw_facet_is_allowed_even_with_a_grade_query_param(self):
        # Only the PATH is scanned: refusing on `sort=grade` would block raw data for a
        # display parameter.
        g.assert_endpoint_allowed("/api/v1/facet/rushing/summary?sort=grade")

    def test_strip_reports_what_it_dropped_not_just_what_it_kept(self):
        kept, dropped = g.strip_model_output_columns(["carries", "grades_offense", "targets"])
        assert kept == ["carries", "targets"]
        # The dropped list is the point: a silent strip is indistinguishable from "PFF sent
        # no grades", and those are different facts.
        assert dropped == ["grades_offense"]

    def test_fetch_facet_strips_grades_from_real_rows(self, monkeypatch):
        client = _StubClient({"players": [
            {"player_id": 1, "targets": 5, "grades_pass_route": 88.1, "routes": 20}
        ]})
        rows = fx.fetch_facet(client, fx.Facet("receiving", "summary"), 1)
        assert "grades_pass_route" not in rows[0]
        assert rows[0]["targets"] == 5 and rows[0]["routes"] == 20


# ── auth is verified by DATA, never by reachability ─────────────────────────────────────────
class TestAuthFailsLoudly:
    def test_expired_session_returning_html_login_with_http_200_is_an_auth_error(self):
        # The dangerous shape: PFF answers 200 with the login page. A status-code check calls
        # this healthy; only inspecting the body distinguishes it.
        body = "<html><body><form>Sign in<input type=password></form></body></html>"
        with pytest.raises(PFFAuthError):
            _parse_response("u", 200, body)

    def test_cloudflare_challenge_is_named_as_a_challenge_not_an_auth_failure(self):
        with pytest.raises(PFFChallengeError):
            _parse_response("u", 200, "<html><title>Just a moment...</title>cf_chl</html>")

    def test_rejected_credential_is_an_auth_error(self):
        with pytest.raises(PFFAuthError):
            _parse_response("u", 401, '{"error":"unauthorized"}')

    def test_no_failure_path_returns_an_empty_list(self):
        # E5.10: a swallowed failure that becomes `[]` makes an outage indistinguishable from a
        # quiet day. Every failure here must RAISE.
        for status, body in ((500, "boom"), (200, "<html>Sign in <input type=password>"),
                             (403, "nope"), (200, "not json at all")):
            with pytest.raises(PFFClientError):
                _parse_response("u", status, body)

    def test_missing_credential_raises_rather_than_attempting_a_bypass(self):
        c = PFFClient(token="", cookie="", transport="direct")
        with pytest.raises(PFFAuthError, match="No PFF credential"):
            c.get("/api/v1/games", {"league": "nfl"})

    def test_flaresolverr_without_a_cookie_says_why_instead_of_serving_a_logged_out_200(self):
        c = PFFClient(token="tok", cookie="", transport="flaresolverr",
                      flaresolverr_url="http://x/v1")
        with pytest.raises(PFFAuthError, match="COOKIE"):
            c.get("/api/v1/games", {"league": "nfl"})

    def test_guard_runs_before_the_credential_check(self):
        # The refusal must be unconditional, not an accident of being logged out.
        c = PFFClient(token="", cookie="", transport="direct")
        with pytest.raises(g.ForbiddenEndpointError):
            c.get("/api/v1/facet/receiving/projections")


class TestPayloadShapes:
    def test_unrecognised_payload_raises_rather_than_parsing_to_empty(self):
        with pytest.raises(PFFClientError, match="Unrecognised"):
            fx._rows({"meta": {"a": 1}, "paging": {"b": 2}})

    @pytest.mark.parametrize("payload", [
        [{"a": 1}], {"data": [{"a": 1}]}, {"players": [{"a": 1}]}, {"anything": [{"a": 1}]},
    ])
    def test_common_envelopes_parse(self, payload):
        assert fx._rows(payload, prefer=("players", "data")) == [{"a": 1}]


# ── entity resolution ──────────────────────────────────────────────────────────────────────
def _rosters() -> pd.DataFrame:
    """A synthetic `weekly_rosters` reproducing the LIVE ambiguity measured on the lake:
    pff_id 47327 is attached to BOTH Ryan Izzo and Tyler Conklin, and Conklin also has 47124."""
    return pd.DataFrame([
        # historical rows carry NO pff_id — the real 2024 pattern the cross-season carry fixes
        {"season": 2024, "gsis_id": "00-0000001", "pff_id": None, "full_name": "Alpha Back",
         "team": "KC", "position": "RB"},
        {"season": 2025, "gsis_id": "00-0000001", "pff_id": "1001", "full_name": "Alpha Back",
         "team": "KC", "position": "RB"},
        {"season": 2024, "gsis_id": "00-0034270", "pff_id": "47124", "full_name": "Tyler Conklin",
         "team": "NYJ", "position": "TE"},
        {"season": 2024, "gsis_id": "00-0034270", "pff_id": "47327", "full_name": "Tyler Conklin",
         "team": "NYJ", "position": "TE"},
        {"season": 2024, "gsis_id": "00-0033900", "pff_id": "47327", "full_name": "Ryan Izzo",
         "team": "NE", "position": "TE"},
    ])


class TestCrosswalk:
    def test_cross_season_carry_recovers_a_player_whose_season_row_has_no_pff_id(self):
        # Measured on the live lake: this carry is worth ~44 points of 2024 opportunity
        # coverage (56.16% same-season → 99.89% player-level).
        xw = build_pff_crosswalk(_rosters())
        got = resolve_nfl_players(pd.DataFrame({"pff_player_id": ["1001"]}), xw)
        assert got.loc[0, "canonical_player_id"] == "00-0000001"

    def test_an_ambiguous_vendor_id_is_refused_not_arbitrated(self):
        # ⭐ The wrong-merge guard. `max(pff_id)` — the obvious implementation — would hand
        # 47327 to Conklin, an id that is also Izzo's. A miss is visible; a wrong merge is not.
        xw = build_pff_crosswalk(_rosters())
        got = resolve_nfl_players(pd.DataFrame({"pff_player_id": ["47327"]}), xw)
        assert pd.isna(got.loc[0, "canonical_player_id"])
        assert got.loc[0, "match_method"] == "manual_review"

    def test_the_unambiguous_id_of_the_same_player_still_resolves(self):
        # The ambiguity must cost only the ambiguous id, not the player.
        xw = build_pff_crosswalk(_rosters())
        got = resolve_nfl_players(pd.DataFrame({"pff_player_id": ["47124"]}), xw)
        assert got.loc[0, "canonical_player_id"] == "00-0034270"

    def test_resolution_is_row_preserving(self):
        xw = build_pff_crosswalk(_rosters())
        src = pd.DataFrame({"pff_player_id": ["1001", "47327", "nope", "47124"]})
        assert len(resolve_nfl_players(src, xw)) == 4


class TestIdSpaceAssumption:
    """The single highest-risk assumption in the story: nflverse `pff_id` == PFF `player_id`."""

    def test_disjoint_id_spaces_are_named_as_such(self):
        xw = build_pff_crosswalk(_rosters())
        out = id_space_agreement(pd.DataFrame({"pff_player_id": ["A1", "A2", "A3"]}), xw)
        assert out["verdict"].startswith("DISJOINT_ID_SPACE")

    def test_matching_id_spaces_are_named_as_such(self):
        xw = build_pff_crosswalk(_rosters())
        out = id_space_agreement(pd.DataFrame({"pff_player_id": ["1001", "47124"]}), xw)
        assert out["verdict"] == "SAME_ID_SPACE"

    def test_no_ids_is_UNTESTED_not_a_pass(self):
        # NF1.7(a): a check that could not run is never scored healthy.
        xw = build_pff_crosswalk(_rosters())
        assert id_space_agreement(pd.DataFrame({"pff_player_id": []}), xw)["verdict"].startswith(
            "UNTESTED"
        )


class TestGameResolution:
    def _ours(self):
        return pd.DataFrame([{"game_id": "2024_01_BAL_KC", "season": 2024, "week": 1,
                              "home_team": "KC", "away_team": "BAL"}])

    def test_exact_orientation_matches(self):
        pff = pd.DataFrame([{"season": 2024, "week": 1, "home_team": "KC", "away_team": "BAL"}])
        out = resolve_games(pff, self._ours())
        assert out.loc[0, "our_game_id"] == "2024_01_BAL_KC"
        assert out.loc[0, "game_match_method"] == "exact"

    def test_a_swapped_home_away_feed_still_matches_instead_of_scoring_zero(self):
        # A feed that labels home/away the other way round would otherwise give a clean,
        # total and completely mysterious 0% — the class this story exists to catch.
        pff = pd.DataFrame([{"season": 2024, "week": 1, "home_team": "BAL", "away_team": "KC"}])
        out = resolve_games(pff, self._ours())
        assert out.loc[0, "our_game_id"] == "2024_01_BAL_KC"
        assert out.loc[0, "game_match_method"] == "swapped"

    def test_a_genuinely_absent_game_stays_unmatched(self):
        pff = pd.DataFrame([{"season": 2024, "week": 9, "home_team": "SF", "away_team": "SEA"}])
        assert pd.isna(resolve_games(pff, self._ours()).loc[0, "our_game_id"])


class TestMatchReport:
    def test_opportunity_weighted_rate_differs_from_the_row_rate(self):
        # The NF1.8 rule: NFL 2024 is 56% of roster ROWS and >99% of targets-and-carries.
        # Reporting only the row rate would condemn a feed that is fine for the population
        # every downstream story actually uses.
        res = pd.DataFrame({
            "canonical_player_id": ["a", None, None],
            "match_method": ["stable_vendor_id", "manual_review", "manual_review"],
            "opp": [900.0, 1.0, 1.0],
            "pff_player_name": ["Star", "Scrub", "Scrub2"],
        })
        rep = match_report(res, id_column="canonical_player_id", label="t",
                           opportunity_column="opp", name_column="pff_player_name")
        assert rep["match_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert rep["opportunity_matched_rate"] > 0.99
        assert rep["unmatched_count"] == 2

    def test_the_unmatched_are_enumerated_not_merely_counted(self):
        res = pd.DataFrame({"canonical_player_id": [None], "match_method": ["manual_review"],
                            "pff_player_name": ["Ghost Player"]})
        rep = match_report(res, id_column="canonical_player_id", label="t",
                           name_column="pff_player_name")
        assert rep["unmatched_sample"] == [{"pff_player_name": "Ghost Player"}]


# ── the probe refuses to call a zero-row pull a success ────────────────────────────────────
class _StubClient:
    """A PFFClient stand-in returning canned payloads (no network, no credential)."""

    def __init__(self, payload, games=None):
        self.payload, self.games = payload, games
        self.transport, self.sample_dir = "sample", None

    def get(self, path, params=None):
        from quant_sports_intel_models.football.pff.guards import assert_endpoint_allowed
        assert_endpoint_allowed(path)
        if path.endswith("/games"):
            return self.games if self.games is not None else {"games": []}
        return self.payload


class TestProbeFailsLoud:
    def test_zero_games_raises_in_strict_mode(self):
        with pytest.raises(PFFClientError, match="NO games"):
            run_league(_StubClient({}, games={"games": []}), league="nfl", season=2024,
                       weeks=[1], discover=False, strict=True)

    def test_zero_facet_rows_raises_in_strict_mode(self):
        games = {"games": [{"id": 1, "season": 2024, "week": 1,
                            "home_team": "KC", "away_team": "BAL"}]}
        with pytest.raises(PFFClientError, match="ZERO facet rows"):
            run_league(_StubClient({"players": []}, games=games), league="nfl", season=2024,
                       weeks=[1], discover=False, strict=True)

    def test_no_strict_reports_the_zero_instead_of_raising(self):
        out = run_league(_StubClient({}, games={"games": []}), league="nfl", season=2024,
                         weeks=[1], discover=False, strict=False)
        assert out["games_pulled"] == 0


class TestFieldDiscovery:
    def test_field_names_are_discovered_and_recorded_not_assumed(self):
        # We have not seen PFF's real field names; the probe records which candidate hit so the
        # artifact says what PFF actually sends rather than what we guessed.
        df = normalise_rows(
            [{"player_id": 7, "player": "X", "team_name": "KC", "position": "WR",
              "routes": 30, "targets": 5, "avg_depth_of_target": 9.1}],
            facet_key="receiving/summary", game_id=1,
        )
        assert df.attrs["field_hits"]["adot"] == "avg_depth_of_target"
        assert df.loc[0, "routes"] == 30
        # Originals are kept so nothing PFF sent is lost to our renaming.
        assert "raw_avg_depth_of_target" in df.columns

    def test_a_missing_concept_is_NA_not_a_crash(self):
        df = normalise_rows([{"player_id": 1}], facet_key="rushing/summary", game_id=1)
        assert pd.isna(df.loc[0, "routes"])


def test_sample_filename_is_deterministic_and_operator_reproducible():
    assert sample_filename("/api/v1/games", {"league": "nfl", "season": 2024, "week": 1}) == \
        "api_v1_games__league-nfl__season-2024__week-1.json"


# ── NCAAF: the school key IS the join ──────────────────────────────────────────────────────
from quant_sports_intel_models.football.pff.resolve import resolve_ncaaf_players  # noqa: E402
from quant_sports_intel_models.football.pff.schools import school_key  # noqa: E402


class TestSchoolKey:
    @pytest.mark.parametrize("a,b", [
        ("San José State", "San Jose St"),   # accent + the trailing-St convention
        ("Miami (OH)", "Miami OH"),          # parenthetical disambiguator
        ("Texas A&M", "Texas A&M University"),
        ("Ole Miss", "Mississippi"),         # genuinely different names (alias map)
        ("Pitt", "Pittsburgh"),
        ("Ohio State", "Ohio St"),
    ])
    def test_vendor_spellings_of_one_school_fold_together(self, a, b):
        assert school_key(a) == school_key(b) != ""

    def test_a_leading_St_is_Saint_not_State(self):
        # `\bst$` is anchored at the END on purpose: an unanchored expansion turns
        # `st francis` into `state francis`.
        assert school_key("St. Francis (PA)") == "st francis pa"

    def test_genuinely_different_schools_do_not_collide(self):
        assert school_key("Miami (OH)") != school_key("Miami")
        assert school_key("Texas") != school_key("Texas A&M")

    def test_the_nfl_team_folder_would_NOT_do_this_job(self):
        # The reason schools.py exists. If this ever starts passing, normalize_team has been
        # widened to college names and this module should be reconsidered — deliberately.
        from quant_sports_intel_models.football.nfl.entity.names import normalize_team
        assert normalize_team("Ole Miss") != normalize_team("Mississippi")


class TestNcaafResolution:
    def _roster(self):
        return pd.DataFrame([
            {"id": "111", "firstName": "Caleb", "lastName": "Williams",
             "team": "Southern California", "position": "QB"},
            {"id": "222", "firstName": "Luther", "lastName": "Burden",
             "team": "Missouri", "position": "WR"},
        ])

    def test_a_school_alias_resolves_the_player(self):
        out = resolve_ncaaf_players(
            pd.DataFrame([{"pff_player_name": "Caleb Williams", "pff_team": "USC",
                           "pff_position": "QB"}]), self._roster())
        assert out.loc[0, "cfbd_athlete_id"] == "111"

    def test_an_unreconciled_school_is_NAMED_not_silently_unmatched(self):
        # A school we cannot key takes its whole roster down with it; naming it converts a
        # depressed match rate into an alias-map entry.
        out = resolve_ncaaf_players(
            pd.DataFrame([{"pff_player_name": "Someone Else", "pff_team": "Fake Tech",
                           "pff_position": "RB"}]), self._roster())
        assert pd.isna(out.loc[0, "cfbd_athlete_id"])
        assert bool(out.loc[0, "unknown_school"]) is True

    def test_a_known_school_with_an_unknown_player_is_not_flagged_as_a_school_problem(self):
        # The two causes of "unmatched" must stay distinguishable (the NF-C6b lesson).
        out = resolve_ncaaf_players(
            pd.DataFrame([{"pff_player_name": "Nobody Here", "pff_team": "Missouri",
                           "pff_position": "WR"}]), self._roster())
        assert pd.isna(out.loc[0, "cfbd_athlete_id"])
        assert bool(out.loc[0, "unknown_school"]) is False

    def test_ambiguous_name_within_a_school_abstains_rather_than_guessing(self):
        roster = pd.DataFrame([
            {"id": "1", "firstName": "John", "lastName": "Smith", "team": "Ohio State",
             "position": "WR"},
            {"id": "2", "firstName": "John", "lastName": "Smith", "team": "Ohio State",
             "position": "WR"},
        ])
        out = resolve_ncaaf_players(
            pd.DataFrame([{"pff_player_name": "John Smith", "pff_team": "Ohio St",
                           "pff_position": "WR"}]), roster)
        assert pd.isna(out.loc[0, "cfbd_athlete_id"])

    def test_resolution_is_row_preserving(self):
        src = pd.DataFrame([
            {"pff_player_name": n, "pff_team": "USC", "pff_position": "QB"}
            for n in ("Caleb Williams", "X Y", "Z W")
        ])
        assert len(resolve_ncaaf_players(src, self._roster())) == 3


class TestGameJoinUsesTheLeagueCorrectTeamKey:
    """Regression pin for a bug found by RUNNING the probe, not by a unit test.

    The player join was moved onto `school_key` and `resolve_games` was left on the NFL
    `normalize_team`, so an NCAAF probe scored a 100% PLAYER match and a 0% GAME match —
    `Ohio St` vs `Ohio State`. Two renderers of one field running two rule sets (E9.61).
    """

    def _ours(self):
        return pd.DataFrame([{"game_id": "401628319", "season": 2024, "week": 1,
                              "home_team": "Ohio State", "away_team": "Akron"}])

    def test_the_nfl_key_FAILS_on_college_names(self):
        # The pre-fix behaviour, pinned so the fix is demonstrably load-bearing rather than
        # decorative — if this ever passes, `normalize_team` has changed under us.
        pff = pd.DataFrame([{"season": 2024, "week": 1, "home_team": "Ohio St",
                             "away_team": "Akron"}])
        out = resolve_games(pff, self._ours())          # default team_key=normalize_team
        assert pd.isna(out.loc[0, "our_game_id"])

    def test_the_school_key_matches_the_same_game(self):
        pff = pd.DataFrame([{"season": 2024, "week": 1, "home_team": "Ohio St",
                             "away_team": "Akron"}])
        out = resolve_games(pff, self._ours(), team_key=school_key)
        assert out.loc[0, "our_game_id"] == "401628319"

    def test_run_league_selects_the_key_from_the_league(self):
        # The property that actually prevents the recurrence: the CALLER must not be free to
        # forget. Asserted on the source of `run_league` so a future edit that hardcodes one
        # key trips this.
        import inspect
        from quant_sports_intel_models.football.pff import probe as probe_mod
        src = inspect.getsource(probe_mod.run_league)
        assert "team_key=" in src, "run_league must pass an explicit team_key to resolve_games"
        assert "school_key" in src and "normalize_team" in src, (
            "run_league must choose BOTH keys by league — a single hardcoded key is the bug"
        )


# ── what the LIVE API taught us (all of these were real failures, in this order) ────────────
from quant_sports_intel_models.football.pff.client import PFFNotFoundError  # noqa: E402
from quant_sports_intel_models.football.pff.facets import fetch_facet_with_entitlement  # noqa: E402
from quant_sports_intel_models.football.pff.probe import (  # noqa: E402
    TEAM_LABEL_KEYS, _team_label, build_franchise_map,
)


class TestClerkAuthMechanics:
    """PFF uses Clerk: the `__session` cookie IS the JWT and it lives 60 SECONDS."""

    def test_a_stateless_cookie_header_gets_the_handshake_and_is_named_as_such(self):
        # The API 307s to clerk.pff.com to refresh the expired session. A client that does not
        # persist cookies across that redirect loops until curl aborts — which reads as a
        # network fault. The error must name the auth flow instead.
        body = '<a href="https://clerk.pff.com/v1/client/handshake?__clerk_hs_reason=se">Redirect</a>'
        with pytest.raises(PFFAuthError, match="handshake"):
            _parse_response("u", 200, body)

    def test_the_direct_session_does_NOT_also_set_a_cookie_header(self):
        # PFF's jar is ~7 KB. Seeding the session jar AND setting an explicit Cookie header
        # sends it twice → HTTP 431 with an EMPTY body → "unparseable JSON". Measured live.
        #
        # ⭐ Asserted on the REAL SESSION, not on `_headers()`. The first cut checked the helper
        # and stayed green when the call site was broken back to `include_cookie=True` — the
        # defect lives at the CALL SITE, so that is what the guard must read.
        c = PFFClient(cookie="a=1; b=2", token="", transport="direct")
        sess = c._session()
        hdr = {k.lower(): v for k, v in dict(sess.headers).items()}
        assert "cookie" not in hdr, (
            "the session must not ALSO carry an explicit Cookie header — the jar already has it"
        )
        assert len(list(sess.cookies)) == 2, "the jar is what carries the credential"

    def test_431_is_named_as_the_duplicate_cookie_it_almost_always_is(self):
        with pytest.raises(PFFClientError, match="431"):
            _parse_response("u", 431, "")

    def test_cookie_values_containing_equals_are_not_truncated(self):
        # JWT/base64 cookie values carry `=` padding; splitting on every `=` would silently
        # truncate exactly the session token.
        from quant_sports_intel_models.football.pff.client import _parse_cookie_header
        assert _parse_cookie_header("__session=aa.bb==; x=1") == [("__session", "aa.bb=="), ("x", "1")]

    def test_datadome_is_recognised_as_a_challenge_not_a_parse_failure(self):
        # premium.pff.com is behind DataDome, not Cloudflare. Matching only CF markers would
        # misfile the block and send the operator after the wrong problem.
        with pytest.raises(PFFChallengeError):
            _parse_response("u", 200, "<html>geo.captcha-delivery.com datadome</html>")


class TestEntitlementIsAFirstClassFinding:
    """PFF returns, beside the data, the list of fields THIS TIER WITHHOLDS."""

    def test_restricted_is_never_mistaken_for_the_row_list(self):
        # `restricted` is a list of FIELD NAMES sitting next to the data list. Treating it as
        # rows would yield strings-not-dicts and normalise to an all-NA frame — data-shaped
        # nonsense rather than an error.
        #
        # ⭐ NO `prefer` hit on purpose. With one, the lookup short-circuits before the
        # "single list in the envelope" fallback and the guard passes without ever exercising
        # the branch that can confuse the two lists — which is where the bug would live.
        payload = {"restricted": ["routes", "yprr"],
                   "some_unforeseen_facet_key": [{"player": "X", "attempts": 3}]}
        assert fx._rows(payload) == [{"player": "X", "attempts": 3}]

    def test_it_still_resolves_when_the_facet_key_IS_known(self):
        payload = {"restricted": ["routes"], "rushing_summary": [{"player": "X"}]}
        assert fx._rows(payload, prefer=("rushing_summary",)) == [{"player": "X"}]

    def test_the_withheld_fields_are_returned_to_the_caller(self):
        client = _StubClient({"restricted": ["routes", "avg_depth_of_target"],
                              "receiving_summary": [{"player": "X", "targets": 4}]})
        rows, restricted = fetch_facet_with_entitlement(
            client, fx.Facet("receiving", "summary"), 1)
        assert rows == [{"player": "X", "targets": 4}]
        # Without this the probe reports "1 row pulled" for a payload missing everything we
        # came for — a feed that is present but empty of the point.
        assert restricted == ["routes", "avg_depth_of_target"]

    def test_a_404_is_not_retried_and_is_distinguished_from_a_fetch_failure(self):
        # PFF answers 404 with the body `"Internal server error"`. Retrying a discovery miss
        # 3x triples our request count against a paid API for no information.
        with pytest.raises(PFFNotFoundError):
            _parse_response("u", 404, '"Internal server error"')


class TestTeamComesFromTheGameNotTheFacetRow:
    """PFF's facet rows carry NO team name — only `franchise_id` (measured live)."""

    GAMES = [{
        "id": 1, "season": 2024, "week": 1,
        "home_team": {"franchise_id": 28, "abbreviation": "SF", "city": "San Francisco"},
        "away_team": {"franchise_id": 22, "abbreviation": "NYJ", "city": "New York"},
    }]

    def test_the_franchise_map_supplies_the_team_the_rows_lack(self):
        # Without this the NCAAF school block is empty and the join scores a clean 0% — which
        # is exactly what the first live NCAAF run did.
        assert build_franchise_map(self.GAMES, "nfl") == {"28": "SF", "22": "NYJ"}

    def test_the_label_key_is_league_specific(self):
        # NFL `abbreviation` matches nflverse codes; NCAA `abbreviation` is "NOTRED", which
        # matches nothing on our side — CFBD wants `city` ("Notre Dame").
        ncaa = [{"id": 1, "home_team": {"franchise_id": 258, "abbreviation": "NOTRED",
                                        "city": "Notre Dame"}}]
        assert build_franchise_map(ncaa, "ncaa") == {"258": "Notre Dame"}
        assert build_franchise_map(ncaa, "nfl") == {"258": "NOTRED"}

    def test_a_nested_team_object_is_never_stringified_into_the_join_key(self):
        team = {"franchise_id": 28, "abbreviation": "SF", "city": "San Francisco"}
        assert _team_label(team, "nfl") == "SF"
        assert _team_label(team, "ncaa") == "San Francisco"

    def test_both_leagues_are_registered(self):
        assert set(TEAM_LABEL_KEYS) == {"nfl", "ncaa"}


class TestSchoolAliasesAreMeasuredNotGuessed:
    def test_the_state_suffix_aliases_that_were_verified_against_cfbd(self):
        for pff_name, cfbd_key in [("Grambling State", "grambling"), ("McNeese State", "mcneese"),
                                   ("Sam Houston State", "sam houston"),
                                   ("Central Connecticut State", "central connecticut")]:
            assert school_key(pff_name) == cfbd_key

    def test_state_is_NOT_stripped_wholesale_because_real_rivals_would_merge(self):
        # Measured: CFBD carries BOTH forms for these — a blanket rule would merge them.
        for base in ("Ohio", "Michigan", "Florida"):
            assert school_key(base) != school_key(f"{base} State")

    def test_the_measured_long_short_form_aliases(self):
        for pff_name, cfbd_key in [("Albany", "ualbany"), ("Appalachian State", "app state"),
                                   ("Tennessee-Martin", "ut martin"), ("LIU", "long island"),
                                   ("Virginia Military Institute", "vmi")]:
            assert school_key(pff_name) == cfbd_key

    def test_a_known_upstream_typo_is_pinned_rather_than_fuzzy_matched(self):
        # PFF ships "Rio Grand" for "Rio Grande". A typo is a fact about the feed; pinning it
        # keeps the join exact instead of loosening the threshold for everyone.
        assert school_key("UT Rio Grand Valley") == school_key("UT Rio Grande Valley")
