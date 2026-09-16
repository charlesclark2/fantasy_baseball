"""NF-C6-PH2 — the SERVING-BOUNDARY invariants between NF-W1's certified champion and a payload.

Everything here is driven on SYNTHETIC frames: no lake, no S3, no fit. That is deliberate — CI
mocks all IO, so an invariant that could only be exercised against the real lake would be checked
nowhere (the E11.30 "validated nowhere" class), and these are precisely the checks that must hold on
every build.

The four invariants, and the specific bad outcome each one exists to prevent:

  1. `resolve_target_week`   — projecting a slate that has already started.
  2. `assert_no_target_week_outcome` — the frame's placeholder zero for an unplayed week reaching
     that week's own features, i.e. a lost `shift(1)`.
  3. `assert_frozen_form`    — the horizon re-engineering its lags over weeks with no realized
     outcome, which compounds that placeholder forward and collapses every remaining week toward
     the nihilist while reading like a projection.
  4. `opponent_grid_stub`    — a feature that training always has and serving never does (E7.9).

RED-proven by `betting_ml/tests/nf_c6_ph2_red_proof.py`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

_REPO = Path(__file__).resolve().parents[2]

TEAMS = ("AAA", "BBB", "CCC", "DDD")
SEASONS = (2024, 2025)
WEEKS = tuple(range(1, 7))


def _gameday(season: int, week: int, *, slot: int = 0) -> str:
    """Weeks a REAL week apart.

    ⚠️ NOT cosmetic. `assert_point_in_time`'s clause 9 requires every rolling window to end STRICTLY
    before the target kickoff, and the window's as-of instant is the day AFTER the previous week's
    last game. Weeks one calendar day apart therefore make window-end == target kickoff and the
    guard fail-closes on EVERY week but the first — which is the guard working correctly on an
    impossible schedule. A fixture that cannot pass the real gate tests nothing.

    ⭐ AND `slot` SPREADS A WEEK'S GAMES ACROSS DAYS, which is equally load-bearing and was missing
    on the first cut. With every game in a week sharing one gameday, `min` and `max` over that week
    are the SAME NUMBER — so `resolve_target_week` choosing the LAST kickoff instead of the first
    would have been completely invisible to this fixture, and the guard on it passed on nothing. The
    RED proof is what surfaced that. A real week has a Thursday game and a Sunday game, and the
    whole point of picking the FIRST kickoff is what happens between them.
    """
    return str((date(season, 9, 1) + timedelta(days=7 * (week - 1) + slot)))


def _schedule() -> pd.DataFrame:
    """A tiny two-season schedule: 4 teams, 6 weeks, rotating pairings.

    ⭐ IN WEEK 5 ONLY ONE PAIR PLAYS, so CCC and DDD are on a real PER-TEAM bye — which is what an
    NFL bye actually is. A league-wide empty week would be a different (and impossible) shape: the
    week would vanish from the global week index entirely, so this fixture would be exercising a
    pathology rather than the bye path it exists to cover.
    """
    rows = []
    for s in SEASONS:
        for w in WEEKS:
            a, b, c, d = TEAMS
            pairs = [(a, b)] if w == 5 else ([(a, b), (c, d)] if w % 2 else [(a, c), (b, d)])
            for slot, (home, away) in enumerate(pairs):
                rows.append({"season": s, "week": w, "home_team": home, "away_team": away,
                             # slot 0 = the early game, slot 3 = three days later — a real week
                             # spans days, and that is what makes first-vs-last kickoff a choice.
                             "gameday": _gameday(s, w, slot=3 * slot), "div_game": 1})
    return pd.DataFrame(rows)


def _rosters(n_per_pos: int = 2) -> pd.DataFrame:
    rows = []
    for s in SEASONS:
        for w in WEEKS:
            for t in TEAMS:
                for pos in WP.POSITIONS:
                    for i in range(n_per_pos):
                        rows.append({"season": s, "week": w, "team": t, "position": pos,
                                     "status": "ACT", "gsis_id": f"{t}-{pos}-{i}"})
    return pd.DataFrame(rows)


def _stats(schedule: pd.DataFrame, rosters: pd.DataFrame, *, drop=None) -> pd.DataFrame:
    """A realized stat line for every rostered player in every week that has a game.

    `drop` removes (season, week) pairs entirely — that is how a week is made "not yet played".
    """
    tw = WS._team_week_context(schedule)[["season", "week", "team", "opponent"]]
    r = rosters.merge(tw, on=["season", "week", "team"], how="inner")
    if drop:
        r = r[~r.set_index(["season", "week"]).index.isin(drop)]
    rng = np.random.default_rng(7)
    n = len(r)
    return pd.DataFrame({
        "season": r["season"].to_numpy(), "week": r["week"].to_numpy(),
        "player_id": r["gsis_id"].to_numpy(), "position": r["position"].to_numpy(),
        "team": r["team"].to_numpy(), "opponent_team": r["opponent"].to_numpy(),
        "fantasy_points_ppr": rng.gamma(3.0, 3.0, n).round(2),
        "carries": rng.integers(0, 20, n).astype(float),
        "targets": rng.integers(0, 12, n).astype(float),
        "attempts": rng.integers(0, 40, n).astype(float),
        "receptions": rng.integers(0, 9, n).astype(float),
        "passing_yards": rng.integers(0, 350, n).astype(float),
        "passing_tds": rng.integers(0, 4, n).astype(float),
        "passing_interceptions": rng.integers(0, 3, n).astype(float),
        "rushing_yards": rng.integers(0, 120, n).astype(float),
        "rushing_tds": rng.integers(0, 3, n).astype(float),
        "receiving_yards": rng.integers(0, 140, n).astype(float),
        "receiving_tds": rng.integers(0, 3, n).astype(float),
    })


@pytest.fixture()
def world():
    sch = _schedule()
    ros = _rosters()
    return {"schedule": sch, "rosters": ros, "stats": _stats(sch, ros),
            "snaps": pd.DataFrame(columns=["season", "week", "gsis_id", "offense_pct",
                                           "offense_snaps"])}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Which week gets projected
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_target_is_the_first_week_whose_slate_has_not_started(world):
    """⭐ FIRST kickoff, not last. Using the LAST would keep a Thursday-night slate 'current' until
    Monday and serve a projection for six games already in progress."""
    sch = world["schedule"]
    now = datetime(2025, 9, 10, 12, tzinfo=timezone.utc)  # after wk1 (9/1) and wk2 (9/8)
    t = WS.resolve_target_week(sch, now=now)
    assert (t.season, t.week) == (2025, 3)
    assert t.last_reg_week == 6


def test_a_slate_that_has_already_started_is_not_the_target(world):
    """One second after the first kickoff, the week is no longer projectable."""
    sch = world["schedule"]
    first = pd.Timestamp(_gameday(2025, 3, slot=0), tz="UTC").to_pydatetime()
    last = pd.Timestamp(_gameday(2025, 3, slot=3), tz="UTC").to_pydatetime()
    assert last > first, "the fixture must span days, or first-vs-last kickoff is unobservable"
    assert WS.resolve_target_week(sch, now=first - timedelta(seconds=1)).week == 3
    # ⭐ THE DISCRIMINATING INSTANT: between week 3's first and last kickoff. Week 3 is under way,
    # so the projectable week is 4 — and a `max`-based resolver would still answer 3 here, which is
    # exactly the "serve a projection for games in progress" outcome this rules out.
    assert WS.resolve_target_week(sch, now=first + timedelta(seconds=1)).week == 4
    assert WS.resolve_target_week(sch, now=last + timedelta(seconds=1)).week == 4


def test_no_upcoming_week_refuses_rather_than_projecting_a_played_slate(world):
    with pytest.raises(WS.WeeklyServingError, match="kicks off after"):
        WS.resolve_target_week(world["schedule"],
                               now=datetime(2030, 1, 1, tzinfo=timezone.utc))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The target week's own outcome cannot reach its own features
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _unplayed(world, season=2025, week=6):
    """The world with `week` not yet played — the real serving shape."""
    src = dict(world)
    src["stats"] = _stats(world["schedule"], world["rosters"], drop={(season, week)})
    return src, WS.TargetWeek(season=season, week=week,
                              first_kickoff=pd.Timestamp(_gameday(season, week), tz="UTC"),
                              last_reg_week=6)


def test_the_outcome_independence_proof_passes_on_an_honest_build(world):
    src, target = _unplayed(world)
    audit = WS.assert_no_target_week_outcome(src, target=target)
    # ⛔ NON-VACUOUS: a proof over zero rows or zero features would pass on nothing (NF1.7(a)).
    assert audit["n_target_rows"] > 0
    assert audit["n_features_compared"] == len(WP.FEATURES)
    assert audit["n_injected_stat_rows"] > 0


def test_the_independence_tolerance_is_load_bearing_not_decorative(world):
    """⭐ THE TOLERANCE MUST BE DOING WORK, AND IT MUST NOT BE DOING TOO MUCH.

    `prior_week_box__ppr_sum_s2d` is computed as `cumsum() − own`, so the target week's own value is
    added and then subtracted rather than excluded — exact in real arithmetic, not quite in floating
    point. On a MID-SEASON target that leaves a real, non-zero cancellation residue; in WEEK 1 the
    season-to-date group holds only the target row, so it cancels bit-exactly and a bit-exact bar
    passes by luck of the week number. This asserts both halves: the residue exists (so the
    tolerance is load-bearing rather than decorative) and it is orders below the injected outcome
    (so the tolerance cannot hide a leak).
    """
    src, target = _unplayed(world, season=2025, week=6)   # mid-season: five prior weeks
    audit = WS.assert_no_target_week_outcome(src, target=target)
    drift = audit["max_abs_drift"]
    assert drift > 0.0, ("no residue at all — either the fixture no longer reaches a mid-season "
                         "week or the cancellation was removed, and the tolerance now hides nothing")
    assert drift < WS.INDEPENDENCE_ATOL, "the residue exceeds the tolerance it is meant to sit under"
    # …and it is far below the injected outcome a real leak would move the feature by.
    assert drift < audit["injected_points"] * 1e-9

    # The week-1 shape, by contrast, cancels exactly — which is why the first real build passed a
    # bit-exact bar and every week after it would not have.
    src1, target1 = _unplayed(world, season=2025, week=1)
    assert WS.assert_no_target_week_outcome(src1, target=target1)["max_abs_drift"] == 0.0


def test_the_proof_refuses_when_the_target_week_has_no_rows(world):
    src, _ = _unplayed(world)
    ghost = WS.TargetWeek(season=2025, week=99,
                          first_kickoff=pd.Timestamp("2025-12-01", tz="UTC"), last_reg_week=6)
    with pytest.raises(WS.WeeklyServingError, match="no target-week rows"):
        WS.assert_no_target_week_outcome(src, target=ghost)


def test_the_proof_CATCHES_a_lost_lag(world, monkeypatch):
    """⛔ THE GUARD MUST BE ABLE TO FAIL. Simulate a lost `shift(1)` by making one feature read the
    row's OWN week — which is exactly the defect the injection is designed to surface."""
    src, target = _unplayed(world)
    real = WP.engineer_features

    def leaky(frame, stats, snaps, schedule):
        f = real(frame, stats, snaps, schedule)
        f["prior_week_box__ppr_l1"] = f["fantasy_points"]  # the lag, deleted
        return f

    monkeypatch.setattr(WP, "engineer_features", leaky)
    with pytest.raises(WS.WeeklyServingError, match="REACHES its own features"):
        WS.assert_no_target_week_outcome(src, target=target)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The frozen-form horizon
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _basis_and_horizon(world, season=2025, week=3):
    src, target = _unplayed(world, season, week)
    modeled, _, frame = WS.build_serving_matrix(src, target=target)
    universe = (frame[(frame.season == season) & (frame.week == week)]
                [["gsis_id", "position", "team"]].drop_duplicates())
    basis = WS.form_basis(modeled, target=target, universe=universe)
    return basis, WS.frozen_form_horizon(basis, src["schedule"], target=target), target


def test_the_horizon_freezes_every_feature_except_the_game_context(world):
    basis, horizon, _ = _basis_and_horizon(world)
    audit = WS.assert_frozen_form(basis, horizon)
    assert audit["checked"] is True
    assert audit["n_horizon_rows"] > 0
    # ⛔ NON-VACUOUS on BOTH sides: zero rows, or zero frozen columns, would pass on nothing.
    assert audit["n_frozen_columns"] == len(WP.FEATURES) - len(WS.GAME_CONTEXT_COLUMNS) > 0


def test_the_frozen_form_check_CATCHES_a_recomputed_lag(world):
    """A horizon whose lag columns move is the fabricated-zero compounding hazard at its only entry
    point — a placeholder zero read as a realized outcome, week after week."""
    basis, horizon, _ = _basis_and_horizon(world)
    broken = horizon.copy()
    broken["prior_week_box__ppr_l1"] = broken["prior_week_box__ppr_l1"].astype(float) + 1.0
    with pytest.raises(WS.WeeklyServingError, match="NOT frozen form"):
        WS.assert_frozen_form(basis, broken)


def test_the_game_context_IS_allowed_to_move_and_actually_does(world):
    """⭐ If the four game-context columns never varied the check would be trivially satisfiable by a
    horizon that is a pure copy — which would silently drop the real remaining schedule."""
    basis, horizon, target = _basis_and_horizon(world)
    assert horizon["game_context__week_index"].nunique() > 1
    for col in WS.GAME_CONTEXT_COLUMNS:
        assert col in WP.FEATURES
    assert set(horizon["week"]) == set(range(target.week + 1, target.last_reg_week + 1))


def test_the_horizon_carries_the_bye_week_as_a_bye(world):
    """Week 5 is a league-wide bye in the fixture. ⭐ THE REAL 2026 WEEK-1 BUILD CANNOT EXERCISE
    THIS — NFL byes start around week 5 — so a fixture is the only thing standing between the bye
    path and shipping untested."""
    _, horizon, _ = _basis_and_horizon(world, week=3)
    byes = horizon[horizon["is_bye"]]
    assert len(byes) > 0, "the bye path is not exercised — this fixture would prove nothing"
    assert set(byes["week"]) == {5}
    assert byes["opponent"].isna().all()
    assert set(byes["team"]) == {"CCC", "DDD"}, "only the two teams without a week-5 game are byes"
    assert not horizon[horizon["week"] != 5]["is_bye"].any()


def test_a_final_week_target_has_an_empty_horizon(world):
    basis, horizon, _ = _basis_and_horizon(world, week=6)
    assert len(horizon) == 0
    audit = WS.assert_frozen_form(basis, horizon)
    assert audit["checked"] is False  # honestly reported as not-run, never as a pass


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The opponent-grid stub — the E7.9 train/serve gap
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _opponent_block(world, stats_feat, stats_lab, season, week):
    spine = WF.build_spine(world["rosters"], world["schedule"])
    frame = WF.attach_labels(spine, stats_lab, label_version=WP.LABEL_VERSION,
                             label_as_of_timestamp="x", scoring_system_id=WP.SCORING_SYSTEM_ID,
                             snaps=world["snaps"])
    f = WP.engineer_features(frame, stats_feat, world["snaps"], world["schedule"])
    m = (f.season == season) & (f.week == week) & (f.label != WF.LABEL_BYE)
    return f.loc[m, ["gsis_id", *WS.OPPONENT_BLOCK_COLUMNS]].sort_values("gsis_id").reset_index(drop=True)


def test_without_the_stub_the_opponent_block_is_entirely_absent_at_serve(world):
    """⭐ THE CONTROL, and the reason the stub exists. Measured on the real 2026 week-1 frame the
    same way: training coverage 0.9580 / 0.9847 (1.000 on the analogous week-1 rows), serving
    0.0000 / 0.0000 — a model fitted on a feature that is always present, served one that is always
    absent."""
    season, week = 2025, 6
    wo = _stats(world["schedule"], world["rosters"], drop={(season, week)})
    served = _opponent_block(world, wo, wo, season, week)
    for col in WS.OPPONENT_BLOCK_COLUMNS:
        assert served[col].notna().mean() == 0.0, f"{col} is not the gap this test describes"
    trained = _opponent_block(world, world["stats"], world["stats"], season, week)
    assert all(trained[c].notna().mean() > 0.0 for c in WS.OPPONENT_BLOCK_COLUMNS)


def test_the_stub_reproduces_the_training_block_to_1e_9(world):
    """⭐ THE REPRODUCTION PIN. The stub supplies the missing GROUP KEYS and lets
    `engineer_features` compute its own block — so where training's grid is COMPLETE (every
    defence × position cell produced a stat row), the two must agree bit-for-bit.

    Measured the same way against the real lake: bit-identical (0.00e+00) on 5 of 6 sampled
    held-out weeks."""
    season, week = 2025, 6
    trained = _opponent_block(world, world["stats"], world["stats"], season, week)
    wo = _stats(world["schedule"], world["rosters"], drop={(season, week)})
    target = WS.TargetWeek(season=season, week=week,
                           first_kickoff=pd.Timestamp(_gameday(2025, 6), tz="UTC"), last_reg_week=6)
    stub = WS.opponent_grid_stub(world["schedule"], wo, target=target)
    served = _opponent_block(world, pd.concat([wo, stub], ignore_index=True), wo, season, week)

    assert len(stub) > 0, "the stub generated no rows — the pin would be vacuous"
    for col in WS.OPPONENT_BLOCK_COLUMNS:
        a, b = trained[col].to_numpy(float), served[col].to_numpy(float)
        assert (np.isnan(a) == np.isnan(b)).all(), f"{col}: null pattern differs"
        both = ~np.isnan(a)
        assert both.sum() > 0, f"{col}: nothing to compare — the pin would be vacuous"
        assert np.max(np.abs(a[both] - b[both])) < 1e-9, f"{col}: does not reproduce"


def test_the_stub_never_reaches_the_labeller(world):
    """⛔ A zero stat line reaching `attach_labels` would be a FABRICATED OUTCOME. The stub carries
    no `player_id`, so it cannot join a spine row even if it were passed there by mistake."""
    season, week = 2025, 6
    wo = _stats(world["schedule"], world["rosters"], drop={(season, week)})
    target = WS.TargetWeek(season=season, week=week,
                           first_kickoff=pd.Timestamp(_gameday(2025, 6), tz="UTC"), last_reg_week=6)
    stub = WS.opponent_grid_stub(world["schedule"], wo, target=target)
    assert stub["player_id"].isna().all()
    assert set(stub.columns) == set(wo.columns)
    src = {**world, "stats": wo}
    _, _, frame = WS.build_serving_matrix(src, target=target)
    tgt = frame[(frame.season == season) & (frame.week == week)]
    assert (tgt["fantasy_points"] == 0.0).all()
    assert not tgt["_has_stat_row"].any(), "a stub row was joined as a realized outcome"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The coverage instrument that tells a real gap from a benign one
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_coverage_report_separates_a_serve_only_null_from_a_structural_one():
    """⭐ COMPARED AGAINST TRAINING'S ROWS FOR THE SAME WEEK NUMBER, not against pooled training.

    Both measured on the real 2026 week-1 build: `prior_week_box__ppr_s2d_mean` is 0.0000 at serve
    AND 0.0000 in training's week-1 rows (benign — season-to-date has no value in week 1), while the
    opponent block was 0.0000 at serve and 1.0000 in training's week-1 rows (the real gap). Pooled
    training coverage for the season-to-date feature is 0.9184, which would have flagged the benign
    case exactly as loudly as the real one."""
    feats = ("a__x", "b__y", "c__z")
    target = WS.TargetWeek(season=2026, week=1, first_kickoff=pd.Timestamp("2026-09-09", tz="UTC"),
                           last_reg_week=18)
    served = pd.DataFrame({"week": [1, 1], "a__x": [np.nan, np.nan],
                           "b__y": [np.nan, np.nan], "c__z": [1.0, 2.0]})
    train = pd.DataFrame({"week": [1, 1, 2], "a__x": [1.0, 2.0, 3.0],       # training HAS it at wk1
                          "b__y": [np.nan, np.nan, 9.0],                     # training lacks it too
                          "c__z": [1.0, 1.0, 1.0]})
    out = WS.train_serve_coverage(served, train, target=target, features=feats)
    assert out["serve_only_null"] == ["a__x"]
    assert out["null_in_both"] == ["b__y"]
    assert out["train_same_week_rows"] == 2


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. ROS: the levels, the byes, the horizon
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_quantile_at_interpolates_the_vector_and_is_monotone():
    q = np.array([np.linspace(0.0, 38.0, 39)])
    assert WS.quantile_at(q, 0.5)[0] == pytest.approx(np.interp(0.5, WP.Q_LEVELS, q[0]))
    assert WS.quantile_at(q, 0.16)[0] < WS.quantile_at(q, 0.84)[0]


def test_the_ros_band_is_read_at_the_levels_that_make_sigma_sigma():
    """`ros_projection` computes σ = (q84 − q16)/2, which is σ ONLY at those levels. For a Normal
    predictive the recovered σ must therefore come back correct — the nearest grid points
    (0.15/0.85) would return 1.036σ, a 3.6% over-estimate in every ROS interval."""
    from scipy.stats import norm

    mu, sigma = 10.0, 4.0
    q = norm.ppf(WP.Q_LEVELS, loc=mu, scale=sigma)[None, :]
    lo = WS.quantile_at(q, WS.C.ROS_SIGMA_LO_LEVEL)[0]
    hi = WS.quantile_at(q, WS.C.ROS_SIGMA_HI_LEVEL)[0]
    assert (hi - lo) / 2.0 == pytest.approx(sigma, rel=0.01)
    naive_lo, naive_hi = WS.quantile_at(q, 0.15)[0], WS.quantile_at(q, 0.85)[0]
    assert (naive_hi - naive_lo) / 2.0 > sigma * 1.02  # the error the level choice avoids


def test_ros_counts_a_bye_as_a_remaining_week_worth_zero():
    """⚠️ ONE MEANING FOR `rosWeeks`. Dropping byes would make it 'weeks with a game' for some
    players and 'weeks remaining' for others — the same column meaning two things."""
    tgt = pd.DataFrame({"gsis_id": ["a"], "position": ["RB"], "week": [1]})
    tq = np.tile(np.linspace(0.0, 20.0, 39), (1, 1))
    hz = pd.DataFrame({"gsis_id": ["a", "a"], "position": ["RB", "RB"], "week": [2, 3],
                       "is_bye": [False, True]})
    hq = np.tile(np.linspace(0.0, 20.0, 39), (2, 1))
    ros = WS.build_ros(tgt, tq, hz, hq)
    assert int(ros.loc["a", "n_weeks"]) == 3
    # weeks 1 and 2 contribute the same mean; the bye contributes exactly zero.
    assert float(ros.loc["a", "ros_mean"]) == pytest.approx(2 * tq[0].mean(), rel=1e-9)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The point-in-time gate must have examined something
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_pit_gate_must_have_examined_something():
    """⛔ BOTH counters. `weeks_checked > 0` alone is satisfied by a week that carried zero records,
    so a gate that looked at one empty week would report itself as having run."""
    assert WS.assert_pit_gate_non_vacuous(
        {"weeks_checked": 3, "records_checked": 90, "rows_dropped": 0})["records_checked"] == 90
    for bad in ({"weeks_checked": 0, "records_checked": 90},
                {"weeks_checked": 3, "records_checked": 0},
                {}):
        with pytest.raises(WS.WeeklyServingError, match="VACUOUS"):
            WS.assert_pit_gate_non_vacuous(bad)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The freshness SLA — the WRONG-WEEK check is the one no staleness bar can make
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _manifest(**over):
    base = {"season": 2026, "week": 3, "generated_at": "2026-09-22T12:00:00+00:00",
            "projection_day": "2026-09-27T17:00:00+00:00", "n_players": 503}
    return {**base, **over}


def _now(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def test_a_healthy_weekly_artifact_reads_ok():
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _manifest()), expected_week=3,
                   now=_now("2026-09-22T18:00:00+00:00"))
    assert v["verdict"] == "OK" and v["severity"] is None


def test_a_build_running_fine_on_LAST_weeks_slate_is_CRITICAL():
    """⭐ THE CHECK NO STALENESS BAR CAN MAKE. The build ran an hour ago, every timestamp is healthy,
    and the number on the page is for a slate that has already been played — the INC-37 shape."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _manifest(week=2)), expected_week=3,
                   now=_now("2026-09-22T13:00:00+00:00"))
    assert v["verdict"] == "WRONG_WEEK" and v["severity"] == "CRITICAL"
    assert "already been played" in v["detail"]


def test_a_stale_build_escalates_only_past_twice_the_sla():
    """≤2× the SLA is a missed cycle; beyond it the build is dead. Conflating the two makes the
    monitor either noisy or blind."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    r = F.reading_from_manifest(2026, _manifest())
    # ⚠️ Both readings are taken MORE than STALE_BEFORE_KICKOFF_HOURS out from the 09-27 kickoff,
    # so the earlier `STALE_INTO_KICKOFF` branch cannot fire and this test measures the escalation
    # it names rather than a different branch that happens to be red.
    missed = F.classify(r, expected_week=3, now=_now("2026-09-23T20:00:00+00:00"))   # 32h
    dead = F.classify(r, expected_week=3, now=_now("2026-09-25T12:00:00+00:00"))     # 72h
    assert missed["verdict"] == "STALE" and missed["severity"] == "WARN"
    assert dead["verdict"] == "STALE" and dead["severity"] == "CRITICAL"


def test_the_off_season_deactivates_the_sla_rather_than_paging_for_seven_months():
    """INC-45: never put a freshness SLA on an artifact that SHOULD be static — it pages daily on a
    healthy file and gets muted."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _manifest()), expected_week=None,
                   now=_now("2027-04-01T12:00:00+00:00"))
    assert v["verdict"] == "OFF_SEASON" and v["severity"] is None
    assert not F.is_problem(v)


def test_an_unreadable_manifest_is_WARN_never_healthy():
    """NF1.7(a): a check that could not run is not a check that passed."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    for blob in ({}, {"week": 3}, {"generated_at": "not-a-date", "week": 3}, [], "x"):
        v = F.classify(F.reading_from_manifest(2026, blob), expected_week=3,
                       now=_now("2026-09-22T18:00:00+00:00"))
        assert v["verdict"] == "UNKNOWN" and v["severity"] == "WARN", blob


def test_a_projection_not_refreshed_into_its_own_kickoff_is_flagged():
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _manifest(generated_at="2026-09-20T12:00:00+00:00")),
                   expected_week=3, now=_now("2026-09-26T12:00:00+00:00"))
    assert v["verdict"] == "STALE_INTO_KICKOFF" and v["severity"] == "ERROR"


# ── 8b. …and the cadence that is NOT a wrong week (the false-CRITICAL this monitor first shipped)

#: Week 2's last GAMEDAY, date-granular exactly as `schedules.gameday` carries it.
_WK2_SLATE_END = datetime.fromisoformat("2026-09-21T00:00:00+00:00")


def _serving_wk2():
    """Serving week 2 healthily while the schedule's next week is 3 — the in-season steady state."""
    return _manifest(week=2, generated_at="2026-09-17T22:00:00+00:00",
                     projection_day="2026-09-17T20:15:00+00:00")


def test_the_roster_feeds_cadence_is_not_a_wrong_week():
    """⭐ THE REGRESSION THIS EXISTS FOR. The target week advances at the previous slate's FIRST
    kickoff, but the roster feed publishes the new week's rows days later — so from Thursday night
    until ~Tuesday the served week is legitimately one behind while ITS OWN games are still being
    played. The first cut keyed the wrong-week check on `week != expected_week` alone and therefore
    paged CRITICAL for ~5 of every 7 days, with a detail line ("a slate that has already been
    played") that was false on its face. That is the muted-monitor pattern, not a finding.
    """
    from betting_ml.monitoring import nfl_weekly_freshness as F

    for label, now in (("Fri, two days into the slate", "2026-09-18T18:00:00+00:00"),
                       ("Sun, main slate in progress", "2026-09-20T18:00:00+00:00"),
                       ("Mon night, MNF in play", "2026-09-21T22:00:00+00:00")):
        v = F.classify(F.reading_from_manifest(2026, _serving_wk2()), expected_week=3,
                       served_slate_ends=_WK2_SLATE_END, now=_now(now))
        assert v["verdict"] == "AWAITING_NEXT_WEEK", (label, v)
        assert v["severity"] is None, (label, v)
        assert not F.is_problem(v), label


def test_the_cadence_window_turns_CRITICAL_the_moment_the_served_slate_completes():
    """The two-sided half: the benign state must not be a blind spot. The SAME reading, judged
    either side of the served slate's completion, must flip — otherwise this change would have
    traded a false alarm for a missed one."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    r = F.reading_from_manifest(2026, _serving_wk2())
    during = F.classify(r, expected_week=3, served_slate_ends=_WK2_SLATE_END,
                        now=_now("2026-09-21T22:00:00+00:00"))
    after = F.classify(r, expected_week=3, served_slate_ends=_WK2_SLATE_END,
                       now=_now("2026-09-22T12:00:00+00:00"))
    assert during["verdict"] == "AWAITING_NEXT_WEEK" and during["severity"] is None
    assert after["verdict"] == "WRONG_WEEK" and after["severity"] == "CRITICAL"


def test_a_monday_night_kickoff_does_not_page_because_gameday_is_date_granular():
    """`gameday` is a DATE, so the served slate's end is MIDNIGHT UTC on the Monday — while a
    20:15 ET kickoff is already 00:15 UTC on TUESDAY. A grace sized for a kickoff TIME rather than
    a DATE would page CRITICAL with the last game of the week still in play."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _serving_wk2()), expected_week=3,
                   served_slate_ends=_WK2_SLATE_END,
                   now=_now("2026-09-22T02:00:00+00:00"))   # MNF kicked off 00:15Z, still running
    assert v["verdict"] == "AWAITING_NEXT_WEEK", v


def test_an_unknown_slate_end_is_judged_EXACTLY_as_before():
    """NF1.7(a), fail-closed: a check that cannot establish the benign case must not assume it. With
    no slate end the mismatch keeps its original CRITICAL verdict, so a failed schedule read can
    only ever cost a false alarm — never a miss."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _serving_wk2()), expected_week=3,
                   served_slate_ends=None, now=_now("2026-09-18T18:00:00+00:00"))
    assert v["verdict"] == "WRONG_WEEK" and v["severity"] == "CRITICAL"


def test_more_than_one_week_behind_is_never_the_feeds_cadence():
    """The feed is at most one week out. Two behind means the build stopped publishing, whatever the
    served slate is doing."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(F.reading_from_manifest(2026, _serving_wk2()), expected_week=4,
                   served_slate_ends=_WK2_SLATE_END, now=_now("2026-09-18T18:00:00+00:00"))
    assert v["verdict"] == "WRONG_WEEK" and v["severity"] == "CRITICAL"


def test_slate_end_reads_the_last_gameday_of_the_SERVED_week():
    """`slate_end` answers "has the week we are SERVING finished", which is a different question
    from `resolve_target_week`'s "which week is next" — and it must read the served week, not the
    expected one."""
    import pandas as pd

    from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

    sched = pd.DataFrame({
        "season": [2026] * 5,
        "week": [2, 2, 2, 3, 3],
        "gameday": ["2026-09-17", "2026-09-20", "2026-09-21", "2026-09-24", "2026-09-28"],
    })
    assert WS.slate_end(sched, season=2026, week=2) == _WK2_SLATE_END
    assert WS.slate_end(sched, season=2026, week=3) == datetime.fromisoformat(
        "2026-09-28T00:00:00+00:00")
    # A week the schedule does not carry is None, never a silent default.
    assert WS.slate_end(sched, season=2026, week=9) is None
    assert WS.slate_end(sched, season=2025, week=2) is None


# ── 8c. The monitor must actually RUN, and the schedule must not be silently revertible ────────
#
# ⛔ E11.23 forbids importing `pipeline` in the fast gate (it reads the dbt manifest at import and
# dies at COLLECTION when absent), so these read SOURCE. That is the technique the repo's other
# wiring guards use — and it is why each one matches a real CALL form rather than a bare name: an
# identifier is satisfied by an import line or a docstring (the NF-C0e wired-not-invoked shape and
# the INC-38 prose-satisfies-a-scan shape, both of which have shipped green in this repo before).

_REPO_ROOT = Path(__file__).resolve().parents[2]

_TRIPLE_DQ = chr(34) * 3
_TRIPLE_SQ = chr(39) * 3


def _src(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text()


def _strip_comments_and_docstrings(src: str) -> str:
    """Remove `#` comments and triple-quoted blocks so PROSE cannot satisfy a wiring assertion."""
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith(_TRIPLE_DQ, i) or src.startswith(_TRIPLE_SQ, i):
            quote = src[i:i + 3]
            close = src.find(quote, i + 3)
            i = n if close == -1 else close + 3
            continue
        if src[i] == "#":
            nl = src.find("\n", i)
            i = n if nl == -1 else nl
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def test_the_stripper_actually_removes_prose_or_these_guards_are_vacuous():
    """The guards below are only as good as this helper — if it stopped stripping, a COMMENT naming
    the op would satisfy them (INC-38). Prove it removes both comment and docstring forms."""
    sample = "x = 1  # nfl_weekly_freshness_op()\n" + _TRIPLE_DQ + "nfl_weekly_freshness_op()" \
        + _TRIPLE_DQ + "\ny = 2\n"
    stripped = _strip_comments_and_docstrings(sample)
    assert "nfl_weekly_freshness_op()" not in stripped
    assert "x = 1" in stripped and "y = 2" in stripped


def test_the_weekly_freshness_monitor_is_actually_INVOKED_by_a_scheduled_job():
    """⭐ THE GAP THIS CLOSES. The op was defined, exported and tested — and wired into a job that
    nothing scheduled, so it NEVER RAN, while the builder's own skip message named it as the thing
    that escalates. A named escalation path that does not exist is worse than an absent one.

    It must be CALLED, not merely imported — an import line alone is the wired-not-invoked shape."""
    host = _strip_comments_and_docstrings(
        _src("pipeline/jobs/sports_nfl_sleeper_injuries_job.py"))
    assert "nfl_weekly_freshness_op()" in host, (
        "the weekly freshness monitor is not CALLED by sports_nfl_sleeper_injuries_job — if it has "
        "moved to another scheduled host, re-anchor this guard onto that host rather than deleting "
        "it; a monitor nothing invokes is not a monitor")


def test_the_weekly_freshness_monitor_does_NOT_live_in_the_job_it_watches():
    """A monitor hosted inside its own subject cannot see its subject STOP — when the schedule is
    off there is no run, no verification and nothing red. The op is DEFINED with its subject (it
    shares that module's S3 keys and paging helper); what must not happen is its being INVOKED by
    `sports_nfl_weekly_serving_job`, whose failure mode it exists to detect."""
    subject = _strip_comments_and_docstrings(
        _src("pipeline/jobs/sports_nfl_weekly_serving_job.py"))
    # ⚠️ SCOPE TO THIS JOB'S BODY ONLY. `sports_nfl_weekly_freshness_job` is defined LATER in the
    # same module and calls the op legitimately (an on-demand operator handle), so reading to
    # end-of-file makes this guard fail for the wrong reason — which is exactly what it did on its
    # first cut. Cut at the next top-level definition.
    body = subject.split("def sports_nfl_weekly_serving_job(")[-1]
    for terminator in ("\n@", "\ndef "):
        body = body.split(terminator)[0]
    assert "nfl_weekly_freshness_op()" not in body, (
        "the weekly freshness monitor is invoked by the very job it watches — it cannot observe "
        "that job failing to run at all")


def test_the_weekly_serving_schedule_self_starts_and_is_heartbeat_checked():
    """NF-INFRA1, twice-bitten: a schedule toggled ON in Dagit holds that state ONLY in the Dagster
    Postgres, so a volume reset or box re-host silently reverts it to STOPPED with nothing paging.

    ⚠️ It needs BOTH halves and this asserts both. `default_status=RUNNING` makes the intended state
    a property of the CODE; `CRITICAL_SCHEDULES` makes a revert PAGE. Either alone leaves a hole —
    and here the artifact cannot substitute for the heartbeat, because a clean `awaiting_rosters`
    skip is the healthy answer most days, so a stopped schedule looks exactly like the cadence."""
    sched = _src("pipeline/schedules/sports_rollforward_schedules.py")
    block = sched.split("def sports_nfl_weekly_serving_schedule(")[0]
    decorator = block.rsplit("@schedule(", 1)[-1]
    assert "default_status=DefaultScheduleStatus.RUNNING" in decorator, (
        "sports_nfl_weekly_serving_schedule does not self-start — its ON state would live only in "
        "the Dagster Postgres")

    from betting_ml.monitoring import monitor_health as MH

    assert "sports_nfl_weekly_serving_schedule" in set(MH.CRITICAL_SCHEDULES), (
        "sports_nfl_weekly_serving_schedule is not heartbeat-checked, so a revert to STOPPED would "
        "freeze the weekly artifact silently")


def test_the_builder_does_not_promise_an_escalation_path_that_does_not_exist():
    """The skip message is operator-facing and makes a CLAIM about what escalates. It named an
    'OFF-CYCLE freshness monitor' that was on no schedule. Whatever it names must be real."""
    src = _src("quant_sports_intel_models/football/nfl/fantasy/weekly_serving.py")
    assert "OFF-CYCLE freshness monitor" not in src, (
        "the skip path still points at the retired 'OFF-CYCLE' monitor wording — the monitor now "
        "runs DAILY as a leaf on sports_nfl_sleeper_injuries_job")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The builder must populate every field the contract declares
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_builder_emits_every_field_the_contract_declares():
    """⭐ ONE LOGICAL THING, TWO OWNERS — and the deploy trigger cannot referee them.

    The box builder imports `app/backend/models/nfl_weekly.py`, but `app/**` deliberately does NOT
    trigger the box CD: it ships via `deploy.sh`, and listing it there would read as though merging
    deployed the API (the NF-C0 skew misconception, pinned by
    `test_orchestration_cd_paths.py::test_the_lambda_and_frontend_are_not_wired_to_the_box_deploy`).
    So a contract-only change can merge without the box image moving.

    A REQUIRED field added that way fails loudly — the builder validates every blob before writing.
    An OPTIONAL one does not: `q` and the component fields all default to `None`, so a builder that
    stopped populating them would keep validating while the paid route served nulls. That is the
    E9.41 silently-dropped-field class arriving from the WRITER side instead of the serializer side.

    This closes it in CI rather than in the deploy trigger: set equality, both directions, so a
    field added to either owner and not the other goes red before merge.
    """
    universe = pd.DataFrame([{"gsis_id": "a", "position": "RB", "team": "AAA",
                              "is_bye": False, "opponent": "BBB", "is_home": 1.0}])
    qmap = {"a": np.linspace(0.0, 20.0, len(WP.Q_LEVELS))}
    comps = pd.DataFrame([{"gsis_id": "a", **{f"proj_{c}": 1.0
                                              for c in WS.C.WEEKLY_COMPONENT_STAT_KEY}}])
    ros = pd.DataFrame([{"gsis_id": "a", "ros_mean": 100.0, "ros_q10": 80.0, "ros_q90": 120.0,
                         "n_weeks": 17}]).set_index("gsis_id")
    rows = WS.build_players(universe, qmap, comps, ros, names={"a": "A Back"},
                            hist_weeks={"a": 40})
    assert len(rows) == 1
    declared = set(WS.C.declared_field_names(WS.C.NflWeeklyPlayer))
    assert set(rows[0]) == declared, (
        "the builder and the contract disagree about the served player row: "
        f"builder-only={sorted(set(rows[0]) - declared)} "
        f"contract-only={sorted(declared - set(rows[0]))}"
    )
    # …and every PAID field is actually populated, not merely present as a declared null.
    assert all(rows[0][f] is not None for f in WS.C.PAID_WEEKLY_PLAYER_FIELDS)
    WS.C.NflWeeklyPlayer.model_validate(rows[0])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. A publish must name its own destination
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_publish_refuses_to_inherit_the_bucket_from_the_environment(monkeypatch):
    """⭐ AN OUTWARD-FACING ACTION MUST NAME ITS TARGET IN THE COMMAND THAT PERFORMS IT.

    NF1.7's lesson is that `--publish` with no bucket resolved must be a hard error rather than a
    silent no-op. This is the same hazard facing the other way, and it is the one that actually bit
    while this story was being built: `$CACHE_BUCKET` is set in a normal working shell, so a
    `--publish` intended to exercise the REFUSAL path resolved a bucket from the environment and
    reached the LIVE prod api-cache. A destination chosen by an invisible environment variable is
    the documented-but-never-set class pointed at a publish.

    ⚠️ Two-sided: the env var is still honoured for STAGING, which is the safe direction — only a
    real write has to be spelled out.
    """
    from quant_sports_intel_models.football.nfl.fantasy import run_weekly_serving as R

    monkeypatch.setenv("CACHE_BUCKET", "credence-prod-s3-api-cache")

    def _explode(*a, **k):  # a refusal must happen BEFORE any build work
        raise AssertionError("build() ran — the refusal came too late to prevent a publish")

    monkeypatch.setattr(R, "build", _explode)
    with pytest.raises(SystemExit, match="does not inherit"):
        R.main(["--publish"])
    # …and the error names the value that would have been used, so the reader sees what they nearly
    # published to rather than being told only that something was missing.
    monkeypatch.delenv("CACHE_BUCKET")
    with pytest.raises(SystemExit, match="unset"):
        R.main(["--publish"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. "The rosters have not published yet" is a STATE, not a failure
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_awaiting_rosters_is_its_own_state_not_a_generic_failure():
    """⭐ MEASURED ON A LIVE FEED (2026-09-13). The target week advances at the PREVIOUS slate's
    first kickoff, but `weekly_rosters` publishes the next week's game-day rows days later — that
    day `resolve_target_week` returned 2026 wk 2 while the roster feed held week 1 only.

    Treating that as a failure would CRITICAL-page on most days of every week, which is the
    muted-monitor pattern (INC-37: judging a feed before it lands pages every morning). Treating it
    as a success would be the NF-FRESH1 19-green-runs class. So it is its own state, with its own
    exit code, and the message names the FEED rather than the guard that noticed — the first cut
    said "the proof has no rows to compare", which reads like a malfunction (INC-40 anchoring).
    """
    from quant_sports_intel_models.football.nfl.fantasy import run_weekly_serving as R

    assert issubclass(WS.WeeklyRostersNotPublished, WS.WeeklyServingError)
    # …but distinguishable from the generic failure, or the op could not map it.
    assert WS.WeeklyRostersNotPublished is not WS.WeeklyServingError


def test_the_skip_exit_code_has_exactly_one_value_across_both_owners():
    """⚠️ ONE LOGICAL THING, TWO OWNERS (INC-30/36/38). The runner returns the code and the Dagster
    op maps it to a clean skip; if they drift, a routine cadence skip becomes a CRITICAL page or —
    worse — a real failure becomes a silent skip.

    ⛔ The op is read from SOURCE rather than imported: nothing in the fast gate may import
    `pipeline`, whose `__init__` reads the dbt manifest and crashes at COLLECTION when it is absent
    (E11.23)."""
    import re

    from quant_sports_intel_models.football.nfl.fantasy import run_weekly_serving as R

    op_src = (_REPO / "pipeline/jobs/sports_nfl_weekly_serving_job.py").read_text()
    m = re.search(r"^EXIT_AWAITING_ROSTERS = (\d+)$", op_src, flags=re.M)
    assert m, "the op no longer declares EXIT_AWAITING_ROSTERS"
    assert int(m.group(1)) == R.EXIT_AWAITING_ROSTERS == 3
    # …and the op actually BRANCHES on it, rather than merely declaring it (wired ≠ invoked).
    assert "proc.returncode == EXIT_AWAITING_ROSTERS" in op_src
    # ⛔ NOT zero: "published" and "correctly declined to publish" must stay distinguishable at the
    # process boundary.
    assert R.EXIT_AWAITING_ROSTERS != 0


def test_the_cadence_check_fires_on_an_unpublished_week_and_passes_on_a_published_one(world):
    """Two-sided, and driven on the pure function so it does no IO.

    Measured on the live feed 2026-09-13: `resolve_target_week` returned 2026 wk 2 while
    `weekly_rosters` held week 1 only — the routine state this distinguishes from a defect.
    """
    ros = world["rosters"]
    published = WS.TargetWeek(season=2025, week=3,
                              first_kickoff=pd.Timestamp(_gameday(2025, 3), tz="UTC"),
                              last_reg_week=6)
    assert WS.assert_target_week_rosters_published(ros, target=published) > 0

    unpublished = WS.TargetWeek(season=2025, week=9,
                                first_kickoff=pd.Timestamp("2025-11-01", tz="UTC"),
                                last_reg_week=9)
    with pytest.raises(WS.WeeklyRostersNotPublished, match="NO game-day rows"):
        WS.assert_target_week_rosters_published(ros, target=unpublished)
    # The message names the FEED and its newest week, not the guard that noticed — the first cut
    # said "the proof has no rows to compare", which reads like a malfunction (INC-40 anchoring).
    try:
        WS.assert_target_week_rosters_published(ros, target=unpublished)
    except WS.WeeklyRostersNotPublished as exc:
        assert "weekly_rosters" in str(exc) and "newest week present: 6" in str(exc)
        assert "cadence, not a defect" in str(exc)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8b. NOTHING EVER PUBLISHED — the one state in which every other check is unreachable
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐ WHY THIS SECTION EXISTS. 2026 lost week 1 quietly: the schedule was wired STOPPED on 09-05 and
# only flipped RUNNING on 09-13, by which time `resolve_target_week` had advanced past week 1's
# kickoff. Nothing was ever published, and the daily monitor's answer — UNKNOWN/WARN — was byte
# identical on the benign morning and on the morning the slate was being played, because
# WRONG_WEEK, STALE and STALE_INTO_KICKOFF all read a field off an artifact that did not exist.

_WK2_KICKOFF = datetime.fromisoformat("2026-09-17T00:00:00+00:00")


def _nothing_published():
    """The reading the op actually produces when the manifest 404s: `read()` returns None."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    return F.reading_from_manifest(2026, None)


def test_nothing_published_escalates_as_the_expected_kickoff_approaches():
    """The verdict must CHANGE as the deadline closes — that is the whole defect being fixed."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    r = _nothing_published()

    # Far out: benign and expected. Still never healthy (NF1.7(a)), but not a page-at-3am.
    early = F.classify(r, expected_week=2, expected_kickoff=_WK2_KICKOFF,
                       now=_now("2026-09-13T15:00:00+00:00"))
    assert early["verdict"] == "UNKNOWN" and early["severity"] == "WARN"

    # Inside the window: CRITICAL, and under a DIFFERENT verdict so the page's dedup key differs
    # from the benign one an operator has already learned to scroll past.
    late = F.classify(r, expected_week=2, expected_kickoff=_WK2_KICKOFF,
                      now=_now("2026-09-16T12:00:00+00:00"))
    assert late["verdict"] == "NOTHING_PUBLISHED" and late["severity"] == "CRITICAL"
    assert late["verdict"] != early["verdict"]

    # And it does not quietly lapse once the slate starts — that is when it matters most.
    missed = F.classify(r, expected_week=2, expected_kickoff=_WK2_KICKOFF,
                        now=_now("2026-09-20T17:00:00+00:00"))
    assert missed["verdict"] == "NOTHING_PUBLISHED" and missed["severity"] == "CRITICAL"
    assert "kicked off" in missed["detail"]


def test_the_escalation_names_the_actionable_half_of_the_diagnosis():
    """A page that cannot be acted on gets muted. Upstream rosters being late is NOT actionable;
    our own ingest not advancing is — so the detail must name both and say which."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(_nothing_published(), expected_week=2, expected_kickoff=_WK2_KICKOFF,
                   now=_now("2026-09-16T12:00:00+00:00"))
    assert "weekly_rosters" in v["detail"]
    assert "sports_nfl_weekly_serving_schedule" in v["detail"]


def test_nothing_published_stays_warn_when_no_kickoff_can_be_established():
    """NF1.7(a) in BOTH directions: an unestablished deadline must not clear the finding, and must
    not manufacture a CRITICAL either."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(_nothing_published(), expected_week=2, expected_kickoff=None,
                   now=_now("2026-09-20T17:00:00+00:00"))
    assert v["verdict"] == "UNKNOWN" and v["severity"] == "WARN"
    assert F.is_problem(v)


def test_the_kickoff_escalation_cannot_fire_once_something_is_published():
    """No regression on the steady state: a readable artifact is judged by the existing checks, and
    a healthy one sitting right on top of its kickoff is still OK, not NOTHING_PUBLISHED."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    healthy = F.classify(F.reading_from_manifest(2026, _manifest()), expected_week=3,
                         expected_kickoff=_now("2026-09-27T17:00:00+00:00"),
                         now=_now("2026-09-22T18:00:00+00:00"))
    assert healthy["verdict"] == "OK" and healthy["severity"] is None

    # And the benign one-week-behind cadence keeps its own verdict rather than being escalated.
    cadence = F.classify(F.reading_from_manifest(2026, _serving_wk2()), expected_week=3,
                         served_slate_ends=_WK2_SLATE_END,
                         expected_kickoff=_now("2026-09-24T00:00:00+00:00"),
                         now=_now("2026-09-19T18:00:00+00:00"))
    assert cadence["verdict"] == "AWAITING_NEXT_WEEK" and cadence["severity"] is None


def test_the_off_season_is_still_silent_even_with_nothing_published():
    """INC-45: no SLA on a deliberately-static artifact. The escalation must not reintroduce one."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    v = F.classify(_nothing_published(), expected_week=None, expected_kickoff=_WK2_KICKOFF,
                   now=_now("2026-09-20T17:00:00+00:00"))
    assert v["verdict"] == "OFF_SEASON" and v["severity"] is None
    assert not F.is_problem(v)


def test_the_escalation_threshold_is_derived_from_the_existing_kickoff_bar():
    """A second hand-picked number is a second thing to keep true — they must not drift apart."""
    from betting_ml.monitoring import nfl_weekly_freshness as F

    assert F.NOTHING_PUBLISHED_CRITICAL_HOURS == F.STALE_BEFORE_KICKOFF_HOURS


def test_the_freshness_op_actually_supplies_the_expected_kickoff():
    """⭐ THE WIRED-≠-INVOKED HALF, and the one that matters most: a classifier that CAN escalate
    is worth nothing if its only caller never passes the input that lets it.

    AST, not a grep — this module's own explanatory comments name `expected_kickoff` several times,
    so a substring scan would stay green with the argument deleted (the INC-38 prose-satisfies-the-
    guard class)."""
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "pipeline/jobs/sports_nfl_weekly_serving_job.py"
    tree = ast.parse(src.read_text())

    # ⚠️ SCOPED TO `nfl_weekly_freshness_op`, NOT THE WHOLE MODULE (NF-INC-0916). A module-wide
    # scan for `.classify(` was correct while this file held exactly one classifier call; node 1
    # added a SECOND op with its own `SF.classify(...)` over a different classifier with a
    # different signature, and the unscoped form then failed on code that has nothing to do with
    # the property under test. Re-anchored onto the op it always meant — the argument is unchanged.
    op = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "nfl_weekly_freshness_op"), None)
    assert op is not None, (
        "`nfl_weekly_freshness_op` is gone from the job module — this guard would scan nothing")

    calls = [n for n in ast.walk(op)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "classify"]
    assert calls, "no WF.classify(...) call found in the freshness op — the guard would pass on nothing"

    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "expected_kickoff" in kw, (
            "the freshness op calls classify() without expected_kickoff — the NOTHING_PUBLISHED "
            "escalation is then unreachable in production, which is exactly how 2026 week 1 was lost")
        # It must be a real value, not a placeholder that can never escalate.
        assert not (isinstance(kw["expected_kickoff"], ast.Constant)
                    and kw["expected_kickoff"].value is None), \
            "expected_kickoff is hard-coded None — the escalation can never fire"

    # …and the value must come from the SCHEDULE's resolved target, never off the artifact.
    assigned = [n for n in ast.walk(op)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "expected_kickoff" for t in n.targets)]
    assert any("first_kickoff" in ast.dump(n.value) for n in assigned), \
        "expected_kickoff is not derived from the resolved target week's first_kickoff"
