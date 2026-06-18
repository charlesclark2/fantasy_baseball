"""test_bullpen_v3.py — Story E2.1b: bullpen_v3 aggregation, weighting, EB-k, guard.

All synthetic — no Snowflake. Covers the pure-Python core that the CV k-sweep relies on:
the expected-leverage×availability weighting (the leak fix), the shrinkage-k EB posterior,
availability down-weighting, the platoon channel carry-through, and the market-blind guard.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.eb_priors.compute_bullpen_v3 import (
    _availability_factor,
    _eb_posterior_k,
    aggregate_team_v3,
    _V3_VALUE_COLS,
)
from betting_ml.scripts.eb_priors.compute_bullpen_posteriors import _normal_posterior
from betting_ml.utils.market_blind import find_market_columns


def _reliever(game_pk="1", team="NYY", pid="100", *, prior_mu=0.320, prior_sigma=0.030,
              bf=200, xwoba_obs=0.300, leverage=10.0, rest_days=3, ap3=0,
              lhb=0.310, rhb=0.330):
    return {
        "game_pk": game_pk, "game_date": "2024-06-01", "season": 2024, "team": team,
        "pitcher_id": pid, "prior_mu_xwoba": prior_mu, "prior_sigma_xwoba": prior_sigma,
        "bf": bf, "xwoba_obs": xwoba_obs, "expected_leverage": leverage,
        "rest_days": rest_days, "appearances_prev_3d": ap3,
        "bp_xwoba_vs_lhb_30d": lhb, "bp_xwoba_vs_rhb_30d": rhb,
    }


# ── EB posterior at shrinkage k ────────────────────────────────────────────────

def test_eb_k1_matches_static_normal_posterior():
    """k=1 reproduces compute_bullpen_posteriors._normal_posterior (parity)."""
    mu0, sig0, bf, obs = 0.320, 0.030, 150.0, 0.290
    mean_k, std_k = _eb_posterior_k(np.array([mu0]), np.array([sig0]),
                                    np.array([bf]), np.array([obs]), k=1.0)
    exp_mean, exp_std = _normal_posterior(mu0, sig0, bf, obs)
    assert mean_k[0] == pytest.approx(exp_mean, rel=1e-9)
    assert std_k[0] == pytest.approx(exp_std, rel=1e-9)


def test_eb_zero_bf_returns_prior():
    mean, std = _eb_posterior_k(np.array([0.32]), np.array([0.03]),
                                np.array([0.0]), np.array([0.0]), k=1.0)
    assert mean[0] == pytest.approx(0.32)
    assert std[0] == pytest.approx(0.03)


def test_eb_higher_k_shrinks_toward_prior():
    """Larger k ⇒ posterior closer to the prior mean (stronger prior precision)."""
    mu0, obs = 0.320, 0.250
    m1, _ = _eb_posterior_k(np.array([mu0]), np.array([0.03]), np.array([100.0]), np.array([obs]), k=1.0)
    m4, _ = _eb_posterior_k(np.array([mu0]), np.array([0.03]), np.array([100.0]), np.array([obs]), k=4.0)
    assert abs(m4[0] - mu0) < abs(m1[0] - mu0)


# ── Availability factor ────────────────────────────────────────────────────────

def test_availability_rested_and_unknown_are_full():
    assert _availability_factor(3, 0) == 1.0
    assert _availability_factor(None, None) == 1.0       # no 30d appearance ⇒ fresh


def test_availability_back_to_back_downweighted():
    assert _availability_factor(1, 0) == pytest.approx(0.45)    # pitched yesterday
    assert _availability_factor(2, 0) == pytest.approx(0.90)


def test_availability_heavy_recent_use_penalised():
    # rest_days=2 base 0.90, ×0.70 heavy-use penalty when ≥2 of prior 3 days worked.
    assert _availability_factor(2, 2) == pytest.approx(0.90 * 0.70)


# ── Team aggregation ───────────────────────────────────────────────────────────

def test_aggregate_empty_returns_schema():
    out = aggregate_team_v3(pd.DataFrame())
    assert list(out.columns)[:4] == ["game_pk", "game_date", "season", "team"]
    for c in _V3_VALUE_COLS:
        assert c in out.columns
    assert len(out) == 0


def test_leverage_weighting_pulls_toward_high_leverage_arm():
    """The expected-leverage weight (NOT tonight's actual usage) drives the team value.
    Swapping which arm carries the leverage flips the weighted xwOBA — the leak-fix core."""
    lo = _reliever(pid="A", xwoba_obs=0.250, prior_mu=0.250, leverage=20.0, bf=300)   # elite, high-lev
    hi = _reliever(pid="B", xwoba_obs=0.360, prior_mu=0.360, leverage=2.0, bf=300)    # poor, low-lev
    weighted_elite = aggregate_team_v3(pd.DataFrame([lo, hi]))["team_eb_bullpen_xwoba_v3"].iloc[0]

    # Now give the leverage to the poor arm instead.
    lo2 = {**lo, "expected_leverage": 2.0}
    hi2 = {**hi, "expected_leverage": 20.0}
    weighted_poor = aggregate_team_v3(pd.DataFrame([lo2, hi2]))["team_eb_bullpen_xwoba_v3"].iloc[0]

    assert weighted_elite < weighted_poor          # leverage shifts the team posterior
    assert weighted_elite < 0.305 and weighted_poor > 0.305


def test_unavailable_arm_is_downweighted_not_dropped():
    """A back-to-back elite arm contributes less than when rested, but still counts."""
    elite_rested = _reliever(pid="A", xwoba_obs=0.250, prior_mu=0.250, leverage=20.0, rest_days=3)
    filler = _reliever(pid="B", xwoba_obs=0.360, prior_mu=0.360, leverage=10.0, rest_days=3)
    rested = aggregate_team_v3(pd.DataFrame([elite_rested, filler]))["team_eb_bullpen_xwoba_v3"].iloc[0]

    elite_tired = {**elite_rested, "rest_days": 1}     # availability 0.45
    tired = aggregate_team_v3(pd.DataFrame([elite_tired, filler]))["team_eb_bullpen_xwoba_v3"].iloc[0]

    assert tired > rested                               # less elite weight ⇒ worse (higher) team xwOBA
    out = aggregate_team_v3(pd.DataFrame([elite_tired, filler]))
    assert out["pen_projected_unavailable_arms"].iloc[0] == 1
    assert out["pen_available_arms"].iloc[0] == 1
    assert out["n_relievers"].iloc[0] == 2              # not dropped


def test_platoon_channel_carried_through():
    out = aggregate_team_v3(pd.DataFrame([_reliever(lhb=0.290, rhb=0.345)]))
    assert out["team_eb_bullpen_xwoba_vs_lhb_v3"].iloc[0] == pytest.approx(0.290)
    assert out["team_eb_bullpen_xwoba_vs_rhb_v3"].iloc[0] == pytest.approx(0.345)


def test_zero_total_weight_falls_back_to_equal_weight():
    """If every arm has zero expected leverage, fall back to equal weight (no div-by-zero)."""
    a = _reliever(pid="A", xwoba_obs=0.250, prior_mu=0.250, leverage=0.0)
    b = _reliever(pid="B", xwoba_obs=0.350, prior_mu=0.350, leverage=0.0)
    out = aggregate_team_v3(pd.DataFrame([a, b]))
    assert out["team_eb_bullpen_xwoba_v3"].iloc[0] == pytest.approx(0.30, abs=0.02)


def test_effective_size_between_one_and_n():
    rs = [_reliever(pid=str(i), leverage=lev) for i, lev in enumerate([20.0, 5.0, 5.0, 1.0])]
    eff = aggregate_team_v3(pd.DataFrame(rs))["pen_effective_size"].iloc[0]
    assert 1.0 <= eff <= 4.0


def test_two_teams_aggregate_independently():
    nyy = _reliever(game_pk="1", team="NYY", pid="A", xwoba_obs=0.250, prior_mu=0.250)
    bos = _reliever(game_pk="1", team="BOS", pid="B", xwoba_obs=0.360, prior_mu=0.360)
    out = aggregate_team_v3(pd.DataFrame([nyy, bos])).set_index("team")
    assert out.loc["NYY", "team_eb_bullpen_xwoba_v3"] < out.loc["BOS", "team_eb_bullpen_xwoba_v3"]


# ── De-leaked control (equal-weight) ───────────────────────────────────────────

def test_equal_weight_mode_ignores_leverage():
    """weight_mode='equal' must NOT depend on expected_leverage (the de-leaked control)."""
    a = _reliever(pid="A", xwoba_obs=0.250, prior_mu=0.250, leverage=20.0)
    b = _reliever(pid="B", xwoba_obs=0.360, prior_mu=0.360, leverage=2.0)
    hi_lev = aggregate_team_v3(pd.DataFrame([a, b]), weight_mode="equal")["team_eb_bullpen_xwoba_v3"].iloc[0]
    a2, b2 = {**a, "expected_leverage": 1.0}, {**b, "expected_leverage": 99.0}
    swapped = aggregate_team_v3(pd.DataFrame([a2, b2]), weight_mode="equal")["team_eb_bullpen_xwoba_v3"].iloc[0]
    assert hi_lev == pytest.approx(swapped)          # leverage irrelevant under equal weight
    assert hi_lev == pytest.approx(0.305, abs=0.02)  # ~plain average of the two arms


def test_unknown_weight_mode_raises():
    with pytest.raises(ValueError):
        aggregate_team_v3(pd.DataFrame([_reliever()]), weight_mode="bogus")


# ── CONTRACT-GUARD ─────────────────────────────────────────────────────────────

def test_output_columns_are_market_blind():
    out = aggregate_team_v3(pd.DataFrame([_reliever()]))
    assert find_market_columns(out.columns) == []
