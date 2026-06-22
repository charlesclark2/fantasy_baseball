"""E1.9 — fast unit guards for the v6 bake-off / HPO / gate harness.

These exercise the harness *logic* on tiny synthetic data (no NGBoost/CatBoost fits, no
Snowflake) — the real multi-minute runs are operator-side. They lock in:
  - the market-blind CONTRACT-GUARD (the leak that would invalidate a non-market model),
  - the adapters emit the correct PredictiveOutput kind (binary / normal),
  - every tunable class CONSTRUCTS a spec for both kinds,
  - ECE is sane, and the NGBoostSpec tunable knobs are wired.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.model_bakeoff import (
    CalibratedProbaSpec, PointNormalSpec, _assert_market_blind, _binary_ece,
)
from betting_ml.scripts.optuna_hpo import _TUNABLE, _make_spec
from betting_ml.scripts.promotion_gate_eval import NGBoostSpec


def _toy(n=120, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n), "c": rng.normal(size=n)})
    score = 0.8 * X["a"] - 0.5 * X["b"]
    yb = (score + rng.normal(scale=0.5, size=n) > 0).astype(int).values
    yr = (score + rng.normal(scale=0.5, size=n)).values
    return X, yb, yr


def test_contract_guard_blocks_market_columns():
    with pytest.raises(SystemExit, match="CONTRACT-GUARD"):
        _assert_market_blind(["home_elo_diff", "over_prob_consensus"])
    with pytest.raises(SystemExit, match="CONTRACT-GUARD"):
        _assert_market_blind(["away_implied_prob"])
    # a clean leak-free slim contract passes
    _assert_market_blind(["home_bp_eb_coverage_pct", "park_run_factor_3yr", "away_wins"])


def test_calibrated_proba_spec_returns_binary():
    from sklearn.linear_model import LogisticRegression
    X, yb, _ = _toy()
    spec = CalibratedProbaSpec(lambda: LogisticRegression(max_iter=500), name="lr")
    out = spec.fit_predict(X.iloc[:80], yb[:80], X.iloc[80:], yb[80:])
    assert out.kind == "binary_prob"
    assert out.prob.shape == (40,)
    assert np.all((out.prob >= 0) & (out.prob <= 1))


def test_point_normal_spec_returns_normal_with_positive_sigma():
    from sklearn.linear_model import LinearRegression
    X, _, yr = _toy()
    spec = PointNormalSpec(lambda: LinearRegression(), name="ols")
    out = spec.fit_predict(X.iloc[:80], yr[:80], X.iloc[80:], yr[80:])
    assert out.kind == "normal"
    assert out.scale is not None and np.all(out.scale > 0)
    # a homoscedastic Normal supports crps + nll (the totals gate metrics)
    assert np.isfinite(out.score_to_truth(yr[80:], "crps")).all()
    assert np.isfinite(out.score_to_truth(yr[80:], "nll")).all()


@pytest.mark.parametrize("model_class", sorted(_TUNABLE))
@pytest.mark.parametrize("kind", ["clf", "reg"])
def test_make_spec_constructs_every_tunable_class(model_class, kind):
    if model_class == "ngboost_lognormal" and kind == "clf":
        pytest.skip("lognormal is regression-only")
    params = {"n_estimators": 50, "iterations": 50, "max_depth": 3, "depth": 3,
              "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
              "num_leaves": 31, "min_child_weight": 1, "min_child_samples": 5,
              "reg_lambda": 1.0, "l2_leaf_reg": 3.0, "minibatch_frac": 1.0,
              "alpha": 0.1, "l1_ratio": 0.5, "C": 0.5}
    spec = _make_spec(model_class, kind, params, seed=0)
    assert hasattr(spec, "fit_predict") and spec.name


def test_binary_ece_perfect_is_low_and_nan_safe():
    y = np.array([0, 0, 1, 1] * 10)
    p = y.astype(float) * 0.999 + 0.0005  # near-perfect calibration
    assert _binary_ece(y, p) < 0.05
    assert np.isnan(_binary_ece(np.array([0, 1]), np.array([np.nan, np.nan])))


def test_ngboost_spec_tunable_knobs_wired():
    spec = NGBoostSpec(120, "Normal", name="x", seed=1, learning_rate=0.03, minibatch_frac=0.7)
    assert spec.learning_rate == 0.03 and spec.minibatch_frac == 0.7
    # defaults preserve prior behavior for existing callers
    assert NGBoostSpec(500, "Normal").learning_rate == 0.01
