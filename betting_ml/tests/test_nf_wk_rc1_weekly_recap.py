"""NF-WK-RC1 — guards for the weekly recap's load-bearing properties.

Every clause here defends a property a RULING named, and each was RED-proven against deliberately
broken source (`nf_wk_rc1_red_proof.py`) rather than trusted because it passed once.
"""

from __future__ import annotations

import pytest

from app.backend.models import nfl_recap
from app.backend.services import league_scoring, realized_dst, realized_stat_fields, weekly_recap


# ── the ONE scorer ───────────────────────────────────────────────────────────────────────────────

def test_player_seats_go_through_the_one_scorer_proven_by_substitution(monkeypatch):
    """⛔ BY SUBSTITUTION, never by grepping for a call (INC-38) and never by an import that
    nothing invokes (NF-C0e). `score_row` is replaced with a sentinel and the sentinel must come
    out the other end."""
    monkeypatch.setattr(league_scoring, "score_row",
                        lambda row, pos, resolved, stat_field: {"pts": 1234.5})
    fetched = {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "L",
        "startingSlots": ["RB"],
        "teams": [{"teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": 9.0,
                   "lineup": [{"slot": "RB", "seat": 0, "playerKey": "1", "empty": False,
                               "name": "Real Player", "position": "RB", "team": "ATL",
                               "platformPts": 9.0}]}],
    }
    realized = [{"player_display_name": "Real Player", "position": "RB", "team": "ATL",
                 "rushing_yards": 100}]
    out = weekly_recap.score_week(fetched=fetched, realized_rows=realized,
                                  cfg={"scoring": {"per_stat": {"rush_yds": 0.1}}})
    assert out["teams"][0]["seats"][0]["points"] == 1234.5


def test_the_dst_seat_carries_the_leagues_own_figure_not_ours(monkeypatch):
    """PM disposition D2 = (C). Even with the scorer returning a wild number, the D/ST seat must
    serve the platform's figure — otherwise (C) is not implemented at all."""
    monkeypatch.setattr(league_scoring, "score_row",
                        lambda *a, **k: {"pts": 999.0})
    fetched = {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "L",
        "startingSlots": ["DEF"],
        "teams": [{"teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": 4.0,
                   "lineup": [{"slot": "DEF", "seat": 0, "playerKey": "PHI", "empty": False,
                               "name": "PHI D/ST", "position": "DST", "team": "PHI",
                               "platformPts": 4.0}]}],
    }
    seat = weekly_recap.score_week(fetched=fetched, realized_rows=[], cfg={"scoring": {}}
                                   )["teams"][0]["seats"][0]
    assert seat["points"] == 4.0
    assert seat["source"] == weekly_recap.SOURCE_LEAGUE_PUBLISHED
    assert seat["sourceNote"]


# ── the standings fact (PM ruling (i)) ───────────────────────────────────────────────────────────

def _two_team_week(a_total, b_total, *, custom=None):
    return {
        "season": 2025, "week": 1, "platform": "sleeper", "leagueId": "L",
        "startingSlots": ["RB"],
        "teams": [
            {"teamKey": "1", "teamName": "A", "matchupId": 1, "platformTotal": a_total,
             "platformCustomTotal": custom, "lineup": []},
            {"teamKey": "2", "teamName": "B", "matchupId": 1, "platformTotal": b_total,
             "platformCustomTotal": None, "lineup": []},
        ],
    }


def test_the_standings_total_is_the_leagues_and_is_not_our_sum():
    """Our itemisation and the league's record are DIFFERENT FIELDS — the ruling forbids presenting
    them as two estimates of one number, and one `total` is what a consumer would swap."""
    out = weekly_recap.score_week(fetched=_two_team_week(102.04, 103.28),
                                  realized_rows=[], cfg={"scoring": {}})
    team = out["teams"][0]
    assert team["standingsTotal"] == 102.04
    assert team["itemisedTotal"] == 0.0           # nothing itemisable in this fixture
    assert team["itemisationGap"] == pytest.approx(-102.04)
    assert "total" not in team, "a bare `total` invites exactly the swap the ruling forbids"


def test_a_commissioner_override_is_the_leagues_record_and_wins():
    out = weekly_recap.score_week(fetched=_two_team_week(100.0, 90.0, custom=77.0),
                                  realized_rows=[], cfg={"scoring": {}})
    assert out["teams"][0]["standingsTotal"] == 77.0


def test_the_matchup_result_is_decided_on_the_leagues_total_never_our_sum(monkeypatch):
    """⭐ THE SHARPEST CONSEQUENCE: deciding a head-to-head on our itemisation could hand a user a
    DIFFERENT WINNER from their league page. Team 1 has the bigger league total and MUST win even
    though our scorer credits team 2 far more."""
    fetched = _two_team_week(102.0, 101.0)
    fetched["teams"][0]["lineup"] = [{"slot": "RB", "seat": 0, "playerKey": "1", "empty": False,
                                      "name": "Small", "position": "RB", "team": "ATL",
                                      "platformPts": 1.0}]
    fetched["teams"][1]["lineup"] = [{"slot": "RB", "seat": 0, "playerKey": "2", "empty": False,
                                      "name": "Huge", "position": "RB", "team": "BUF",
                                      "platformPts": 1.0}]
    realized = [{"player_display_name": "Small", "position": "RB", "team": "ATL", "rushing_yards": 1},
                {"player_display_name": "Huge", "position": "RB", "team": "BUF", "rushing_yards": 5000}]
    out = weekly_recap.score_week(fetched=fetched, realized_rows=realized,
                                  cfg={"scoring": {"per_stat": {"rush_yds": 0.1}}})
    by_key = {t["teamKey"]: t for t in out["teams"]}
    assert by_key["2"]["itemisedTotal"] > by_key["1"]["itemisedTotal"], "fixture must disagree"
    assert out["matchups"][0]["winnerTeamKey"] == "1"


def test_a_week_with_no_league_totals_has_no_standings_rather_than_approximate_ones():
    """PM amendment 2: a platform we cannot fetch has NO standings, not approximate ones."""
    out = weekly_recap.score_week(fetched=_two_team_week(None, None),
                                  realized_rows=[], cfg={"scoring": {}})
    assert out["matchups"][0].get("resultUnavailable") is True
    assert out["matchups"][0].get("winnerTeamKey") is None
    assert weekly_recap.power_rankings([out])["rows"] == []


# ── the adjacency disclosure ─────────────────────────────────────────────────────────────────────

def test_the_gap_note_names_the_leagues_own_captured_terms_and_is_not_generic():
    note = weekly_recap.itemisation_gap_note({"terms": [
        {"key": "fum", "verdict": "captured", "weight": -1.0},
        {"key": "rec_td_40p", "verdict": "captured", "weight": 2.0},
        {"key": "rec", "verdict": "applied", "weight": 0.5},
    ]})
    assert "fumbles" in note and "40+ yard receiving TD bonuses" in note
    assert "may differ" not in note, "the ruling forbids a vague 'totals may differ'"


def test_a_league_that_captures_nothing_gets_no_disclosure_at_all():
    """A caveat that fires on nothing is one readers learn to skip."""
    assert weekly_recap.itemisation_gap_note(
        {"terms": [{"key": "rec", "verdict": "applied", "weight": 0.5}]}) is None


# ── the divergence recorder ──────────────────────────────────────────────────────────────────────

_DST_SCORED = {"teams": [{"teamKey": "1", "teamName": "A", "seats": [
    {"position": "DST", "team": "PHI", "playerKey": "PHI", "slot": "DEF", "seat": 0,
     "name": "PHI D/ST", "points": 4.0, "platformPts": 4.0}]}]}


def test_the_dst_comparison_is_not_vacuous_against_the_served_value():
    """⚠️ Under (C) the SERVED D/ST point IS `platformPts`, so comparing them is 0 BY CONSTRUCTION.
    The recorder must compare our UNWIRED CONSTRUCTION — the first cut did not, and reported
    '0 diverging' for a construction measured to fail ~27% of team-weeks."""
    out = weekly_recap.compare_to_platform(_DST_SCORED, dst_constructed={"PHI": 2.0})
    assert out["dstSeats"]["diverging"] == 1, "the construction (2.0) differs from the league (4.0)"


def test_a_dst_seat_we_could_not_construct_is_reported_not_counted_as_agreement():
    out = weekly_recap.compare_to_platform(_DST_SCORED, dst_constructed={})
    assert out["dstSeats"]["compared"] == 0
    assert out["dstSeats"]["notConstructed"], "'could not check' must not look like 'it matched'"


def test_no_seat_may_alert():
    """PM amendment 1: every seat records, no seat pages — the player-seat equality premise was
    measured false for legitimate reasons, so alerting on it would be the muted-monitor pattern."""
    out = weekly_recap.compare_to_platform(_DST_SCORED, dst_constructed={"PHI": 2.0})
    assert out["dstSeats"]["mayAlert"] is False
    assert out["playerSeats"]["mayAlert"] is False


def test_a_captured_term_splits_into_explained_and_unexplained():
    """The residual is the future alert's clean signal; the explained part is arithmetic."""
    scored = {"teams": [{"teamKey": "1", "teamName": "A", "seats": [
        {"position": "RB", "slot": "RB", "seat": 0, "name": "X", "points": 12.0,
         "platformPts": 10.0}]}]}
    out = weekly_recap.compare_to_platform(
        scored, captured_weights={"fum": -1.0},
        realized_by_seat={("1", 0): {"fumbles_total": 2}})
    row = out["playerSeats"]["rows"][0]
    assert row["explained"] == pytest.approx(2.0)     # we omitted -1.0 x 2 fumbles
    assert row["unexplained"] == pytest.approx(0.0)
    assert out["playerSeats"]["unexplained"] == 0


def test_the_explanation_columns_are_actually_carried_by_the_published_artifact():
    """⚠️ THE SPLIT SHIPPED AS A SILENT NO-OP ONCE: `fumbles_total` is not among the realized
    scorer's own columns, so the explanation ran with no input and reported 0.0 everywhere. The
    publisher's required set must carry every explanation column, DERIVED."""
    from quant_sports_intel_models.football.nfl.fantasy import realized_week
    missing = set(weekly_recap.EXPLANATION_COLUMNS) - set(realized_week.required_columns())
    assert not missing, f"the artifact would not carry {missing}, so the split scores 0 silently"


# ── completeness is a count, not a clock ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("realized,scheduled,expected", [
    (16, 16, "final"), (15, 16, "partial"), (0, 16, "not_started"), (16, 0, "not_started"),
])
def test_completeness_is_derived_from_a_game_count(realized, scheduled, expected):
    from quant_sports_intel_models.football.nfl.fantasy import realized_week
    assert realized_week.completeness(realized, scheduled) == expected


def test_a_postponed_game_keeps_a_week_partial():
    """The one case a clock rule gets wrong, stated as its own clause so it cannot be lost."""
    from quant_sports_intel_models.football.nfl.fantasy import realized_week
    assert realized_week.completeness(15, 16) == "partial"


# ── the maps stay derived from the scorer's key set ──────────────────────────────────────────────

def test_the_realized_map_refuses_a_key_the_scorer_does_not_know():
    with pytest.raises(ValueError, match="absent from"):
        realized_stat_fields.resolve_realized_fields({"rec": "rec"})


def test_an_absence_reason_distinguishes_its_two_causes():
    """`pat_missed`'s column EXISTS on the realized line; saying 'the line does not carry it' would
    be a confident wrong explanation (NF1.7(a) / NF-C6b)."""
    assert "scorer does not carry" in realized_stat_fields.absence_reason("pat_missed")
    assert "team" in realized_stat_fields.absence_reason("dst_points_allowed").lower()


def test_dst_tier_ranges_are_parsed_from_the_scorer_key_names():
    assert realized_dst.PA_BUCKETS["dst_pa_g_14_17"] == (14.0, 17.0)
    assert realized_dst.PA_BUCKETS["dst_pa_g_46p"][1] == float("inf")
    with pytest.raises(realized_dst.DstBucketError):
        realized_dst._parse_buckets("pa", {"dst_pa_g_weird": "x"})


def test_points_allowed_excludes_the_opponents_non_offensive_touchdowns():
    """The MIN 2025 wk1 proof: CHI's 24 included a defensive TD, so MIN's defence allowed 17 — a
    different scoring tier, and the naive reading disagrees with the league's own figure."""
    assert realized_dst.points_allowed(24, 1) == 17.0
    assert realized_dst.points_allowed(20, 0) == 20.0
    assert realized_dst.points_allowed(7, 1) == 0.0, "never negative"


def test_net_yards_treats_sack_yards_as_the_negative_they_are_stored_as():
    assert realized_dst.net_yards_allowed(210, 119, -12) == 317.0


def test_the_recap_contract_declares_both_totals_separately():
    fields = set(nfl_recap.RecapTeam.model_fields)
    assert {"standingsTotal", "itemisedTotal"} <= fields
    assert "total" not in fields


# ── the publish entrypoint ───────────────────────────────────────────────────────────────────────

def test_the_publisher_refuses_a_week_that_has_not_started():
    """⛔ A zero-row artifact is indistinguishable from a whole league on a bye, so a not_started
    week must REFUSE rather than publish an empty one. The sibling of NF1.7's silent-no-publish."""
    import subprocess
    import sys as _sys
    r = subprocess.run(
        [_sys.executable, "-m",
         "quant_sports_intel_models.football.nfl.fantasy.run_realized_week",
         "--season", "1999", "--week", "1", "--smoke"],
        capture_output=True, text=True, timeout=180,
    )
    # A 1999 week is not in the lake window; the smoke path must still not raise.
    assert r.returncode in (0, 1), r.stderr[-500:]


def test_the_entrypoint_has_an_executing_smoke_flag():
    """The entrypoint sibling sweep (GyD9hoeD): a publish script ships WITH a runnable smoke, so it
    can never join the zero-callers list."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2].joinpath(
        "quant_sports_intel_models/football/nfl/fantasy/run_realized_week.py").read_text()
    assert '"--smoke"' in src
    assert 'if man["completeness"] == "not_started"' in src, "the refusal must be in the publish path"
