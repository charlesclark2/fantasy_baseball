"""NF-WK-ACC1 part 2 — the FROZEN play-derived D/ST rules, and the two-construction wiring.

The rules themselves are frozen as of 2026-09-18 (PM ruling ③) so that three completed 2026 weeks
can test them OUT OF SAMPLE. These guards therefore pin two different things:

  1. WHAT EACH RULE COUNTS, on plays built to make one rule the only thing that could move. A rule
     that quietly changed would otherwise be invisible until the 2026 tally, which is exactly the
     measurement the freeze exists to protect.
  2. THAT A DEGRADED CONSTRUCTION ANNOUNCES ITSELF. A week with no published plays still produces a
     line — from summed player rows, which reproduced 35 of 48 — and the artifact must say so.

Measured figures the rules reproduce (the record they are frozen at): every field 544/544 over 2025's
544 team-weeks except fumble recoveries 543 and forced fumbles 539; scored against the league's own
started defences, 48/48 on weeks 1-4 and 154/155 on weeks 5-17, the one miss being a forced-fumble
count. A defence on BYE counts as 0 on both sides.
"""

from __future__ import annotations

import pytest

from app.backend.services import realized_dst as D
from quant_sports_intel_models.football.nfl.fantasy import realized_dst_pbp as DP
from quant_sports_intel_models.football.nfl.fantasy import realized_week as RW

_BLANK = {c: None for c in DP.PBP_COLUMNS}


def _play(**over):
    """One play with every contract column present and nothing set — so a test's own play cannot
    accidentally count for a rule it is not about."""
    return {**_BLANK, "game_id": "g1", "week": 1, "posteam": "DAL", "defteam": "PHI",
            "play_type": "pass", **over}


def _counters(*plays):
    return DP.team_game_counters(list(plays))


# ── what each rule counts ─────────────────────────────────────────────────────────────────────────

def test_the_defensive_counting_terms_each_credit_the_defence():
    out = _counters(
        _play(sack=1.0),
        _play(interception=1.0),
        _play(play_type="field_goal", field_goal_result="blocked"),
        _play(play_type="punt", punt_blocked=1.0),
    )
    assert out["PHI"]["def_sacks"] == 1
    assert out["PHI"]["def_int"] == 1
    assert out["PHI"]["def_blocked_kick"] == 2, "a blocked FG and a blocked punt both count"
    assert out["DAL"]["def_sacks"] == 0, "the offence is credited with nothing"


def test_a_safety_credits_the_team_not_in_possession_and_charges_the_other():
    out = _counters(_play(safety=1.0))
    assert out["PHI"]["def_safety"] == 1 and out["PHI"]["safeties_scored"] == 1
    assert out["DAL"]["def_safety"] == 0


def test_a_touchdown_is_defensive_or_special_teams_by_the_PLAY_TYPE():
    """⭐ The classification is the rule (`SPECIAL_TEAMS_PLAY_TYPES`), and it decides both the term
    the defence is paid under AND whether the score is charged to points allowed."""
    out = _counters(
        _play(touchdown=1.0, td_team="PHI"),                        # pick-six on a pass play
        _play(play_type="punt", touchdown=1.0, td_team="PHI"),      # punt return TD
        _play(touchdown=1.0, td_team="DAL"),                        # ordinary offensive TD
    )
    assert out["PHI"]["def_td"] == 1 and out["PHI"]["st_td"] == 1
    assert out["PHI"]["defensive_tds_scored"] == 1, "only the DEFENSIVE one is charged (measured)"
    assert out["DAL"]["def_td"] == 0 and out["DAL"]["defensive_tds_scored"] == 0


def test_a_recovery_keys_on_who_FUMBLED_and_a_forced_fumble_on_who_had_POSSESSION():
    """The measured asymmetry (543/544 vs 539/544 for the other keying). They come apart on a fumble
    by a player whose side does not have the ball — here DAL has possession and a PHI player fumbles
    (after an interception), so DAL recovering its opponent's fumble counts for DAL."""
    out = _counters(_play(fumble=1.0, fumbled_1_team="PHI", fumble_recovery_1_team="DAL",
                          forced_fumble_player_1_team="DAL"))
    assert out["DAL"]["def_fumble_rec"] == 1, "keyed on the fumbling team, not on possession"
    assert out["DAL"]["def_forced_fumble"] == 0, "possession-keyed: DAL had the ball, so no credit"
    assert out["PHI"]["def_fumble_rec"] == 0


def test_an_ordinary_offensive_fumble_credits_the_defence_on_both_terms():
    out = _counters(_play(fumble=1.0, fumbled_1_team="DAL", fumble_recovery_1_team="PHI",
                          forced_fumble_player_1_team="PHI"))
    assert out["PHI"]["def_fumble_rec"] == 1 and out["PHI"]["def_forced_fumble"] == 1


def test_a_special_teams_fumble_lands_on_the_ST_terms_and_not_the_defensive_ones():
    out = _counters(_play(play_type="punt", fumble=1.0, fumbled_1_team="DAL",
                          fumble_recovery_1_team="PHI", forced_fumble_player_1_team="PHI"))
    assert out["PHI"]["def_st_ff"] == 1 and out["PHI"]["def_st_fum_rec"] == 1
    assert out["PHI"]["def_fumble_rec"] == 0 and out["PHI"]["def_forced_fumble"] == 0


def test_recovering_your_own_special_teams_fumble_is_not_a_recovery():
    out = _counters(_play(play_type="kickoff", fumble=1.0, fumbled_1_team="PHI",
                          fumble_recovery_1_team="PHI"))
    assert out["PHI"]["def_st_fum_rec"] == 0


def test_a_nan_flag_is_not_set_so_a_missing_value_cannot_inflate_every_counter():
    """⚠️ `bool(float("nan"))` is TRUE. nflverse serves these flags as NaN on most plays, so a bare
    truth test would count EVERY play — inflating the counters rather than failing, i.e. it would
    look like data."""
    nan = float("nan")
    out = _counters(_play(sack=nan, interception=nan, touchdown=nan, safety=nan, fumble=nan))
    assert all(v == 0 for v in out["PHI"].values()), out["PHI"]


def test_a_narrower_select_is_refused_rather_than_counting_zero():
    """The read contract. A term whose column the caller forgot to select would count zero with no
    error — the NF-C0e wired-≠-invoked shape, in its silent-empty costume."""
    thin = {k: v for k, v in _play().items() if k != "punt_blocked"}
    with pytest.raises(ValueError, match="punt_blocked"):
        DP.team_game_counters([thin])


def test_every_team_on_the_field_gets_a_row_even_with_nothing_to_its_name():
    out = _counters(_play())
    assert set(out) == {"DAL", "PHI"}
    assert set(out["DAL"]) == {*DP.COUNTER_KEYS, *DP.ADJUSTMENT_KEYS}


# ── points allowed ────────────────────────────────────────────────────────────────────────────────

def test_points_allowed_removes_six_per_defensive_td_and_two_per_safety():
    opp = {"defensive_tds_scored": 2.0, "safeties_scored": 1.0}
    assert DP.points_allowed(33.0, opp) == pytest.approx(19.0)


def test_points_allowed_keeps_charging_the_opponents_special_teams_touchdowns():
    """MEASURED, and the opposite convention is what RC1 used: excluding ST touchdowns too
    reproduces 518 of 544 team-weeks instead of 544."""
    out = _counters(_play(play_type="kickoff", touchdown=1.0, td_team="DAL"))
    assert out["DAL"]["defensive_tds_scored"] == 0
    assert DP.points_allowed(27.0, out["DAL"]) == pytest.approx(27.0)


def test_points_allowed_is_unknown_not_zero_while_the_result_is_pending():
    assert DP.points_allowed(None, {}) is None
    assert DP.points_allowed(float("nan"), {}) is None


def test_points_allowed_is_floored_at_zero():
    assert DP.points_allowed(6.0, {"defensive_tds_scored": 1.0}) == 0.0


# ── the frozen constants themselves ───────────────────────────────────────────────────────────────

def test_the_special_teams_play_types_are_exactly_the_frozen_set():
    """A silent change here would move the touchdown terms AND points allowed, and would only
    surface in the 2026 tally the freeze exists to keep clean."""
    assert DP.SPECIAL_TEAMS_PLAY_TYPES == {"field_goal", "extra_point", "punt", "kickoff"}


def test_the_play_derived_terms_are_scorable_and_not_claimed_as_player_columns():
    """They live in the D/ST half of the map: the player table has no column for any of them, so
    naming them in the player-grain map would claim a column that does not exist."""
    from app.backend.services import realized_stat_fields

    for key in D.REALIZED_PBP_DST_FIELD:
        assert key in D.dst_stat_field(), f"{key} would score zero with no error"
        assert key not in realized_stat_fields.REALIZED_STAT_SOURCE


# ── the two constructions, and the degraded one announcing itself ─────────────────────────────────

def _games():
    return [{"game_id": "g1", "home_team": "PHI", "away_team": "DAL",
             "home_score": 24, "away_score": 27}]


def _team_stats():
    base = {c: 0 for c in D.DST_TEAM_COLUMNS}
    return {"PHI": {**base, "def_sacks": 1, "passing_yards": 0, "rushing_yards": 0},
            "DAL": {**base, "passing_yards": 200, "rushing_yards": 100, "def_tds": 1}}


def test_with_plays_the_line_carries_the_frozen_terms_and_the_frozen_points_allowed():
    counters = _counters(
        _play(posteam="PHI", defteam="DAL", touchdown=1.0, td_team="DAL"),     # DAL defensive TD
        _play(posteam="DAL", defteam="PHI", play_type="field_goal", field_goal_result="blocked"),
    )
    out = RW.team_week_inputs(_team_stats(), _games(), counters)
    line = out["PHI"]["line"]
    assert line["def_blocked_kick"] == 1, "a term only the plays can supply"
    # DAL scored 27 including one DEFENSIVE touchdown → PHI allowed 27 − 6 = 21.
    assert line["dst_points_allowed"] == pytest.approx(21.0)


def test_without_plays_the_line_falls_back_to_the_summed_player_construction():
    out = RW.team_week_inputs(_team_stats(), _games())
    line = out["PHI"]["line"]
    assert "def_blocked_kick" not in line, "the fallback cannot supply a play-only term"
    # RC1's rule: 27 − 7 × (DAL's one defensive TD) = 20.
    assert line["dst_points_allowed"] == pytest.approx(20.0)


class _FakeQ:
    """A `q` that answers the three reads `build_dst_inputs` makes, with plays optional."""

    def __init__(self, plays):
        self.plays = plays

    def __call__(self, sql):
        import pandas as pd

        if "stats_player_week" in sql:
            return pd.DataFrame([{"team": t, **{c: v.get(c, 0) for c in D.DST_TEAM_COLUMNS}}
                                 for t, v in _team_stats().items()])
        if "schedules" in sql:
            return pd.DataFrame(_games())
        return pd.DataFrame(self.plays, columns=list(DP.PBP_COLUMNS))


def test_the_artifact_says_which_construction_produced_it():
    built = RW.build_dst_inputs(2025, 1, q=_FakeQ([_play(sack=1.0)]), delta=lambda t: t)
    assert built["construction"] == "pbp_frozen"
    assert "pbp" in built["source"] and "frozen" in built["source"]
    assert "play-by-play" in built["pointsAllowedAssumption"]
    assert "constructionFallbackReason" not in built


def test_a_week_with_no_published_plays_is_labelled_a_fallback_with_its_reason():
    """⛔ "We fell back" and "this is the frozen construction" must never be the same artifact."""
    built = RW.build_dst_inputs(2025, 1, q=_FakeQ([]), delta=lambda t: t)
    assert built["construction"] == "player_sums"
    assert "no REG plays published" in built["constructionFallbackReason"]
    assert "assumed extra point" in built["pointsAllowedAssumption"], (
        "the fallback must disclose the 7-point assumption it actually used")
    assert built["teams"], "a fallback still produces lines — it is degraded, not absent"


def test_a_failed_play_read_falls_back_and_names_the_failure_rather_than_pretending():
    def boom(sql):
        import pandas as pd

        if "pbp" in sql:
            raise RuntimeError("lake unreachable")
        return _FakeQ([])(sql)

    built = RW.build_dst_inputs(2025, 1, q=boom, delta=lambda t: t)
    assert built["construction"] == "player_sums"
    assert "RuntimeError: lake unreachable" in built["constructionFallbackReason"]
