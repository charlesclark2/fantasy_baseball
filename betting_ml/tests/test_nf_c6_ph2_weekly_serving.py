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

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

TEAMS = ("AAA", "BBB", "CCC", "DDD")
SEASONS = (2024, 2025)
WEEKS = tuple(range(1, 7))


def _gameday(season: int, week: int) -> str:
    """Weeks a REAL week apart.

    ⚠️ NOT cosmetic. `assert_point_in_time`'s clause 9 requires every rolling window to end STRICTLY
    before the target kickoff, and the window's as-of instant is the day AFTER the previous week's
    last game. Weeks one calendar day apart therefore make window-end == target kickoff and the
    guard fail-closes on EVERY week but the first — which is the guard working correctly on an
    impossible schedule. A fixture that cannot pass the real gate tests nothing.
    """
    return str((date(season, 9, 1) + timedelta(days=7 * (week - 1))))


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
            for home, away in pairs:
                rows.append({"season": s, "week": w, "home_team": home, "away_team": away,
                             "gameday": _gameday(s, w), "div_game": 1})
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
    kickoff = pd.Timestamp(_gameday(2025, 3), tz="UTC").to_pydatetime()
    assert WS.resolve_target_week(sch, now=kickoff - timedelta(seconds=1)).week == 3
    just_after = kickoff + timedelta(seconds=1)
    assert WS.resolve_target_week(sch, now=just_after).week == 4


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
