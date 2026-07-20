"""Fast-gate tests for the E2.1-r per-side bake-off harness.

Covers the pure logic only (no Snowflake, no S3, no long fits — every heavy path is the
operator's job): the pre-registered candidate/contract/dispersion registries, the native
(μ, σ) → NegBin r moment-match, in-fold contract derivation, and the downstream selection
metric. The point of these is that the *selection rule* can't silently drift.
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.scripts.totals_generative import bakeoff_perside as bo


# ---------------------------------------------------------------------------
# Pre-registration: the candidate set is what the story committed to
# ---------------------------------------------------------------------------

def test_candidate_set_is_at_least_three_classes_plus_incumbent():
    assert bo._INCUMBENT in bo.MODEL_CLASSES
    assert len(bo.MODEL_CLASSES) >= 4, "§0.5 requires ≥3 candidate classes + the incumbent foil"


def test_every_model_class_builds():
    for mc in bo.MODEL_CLASSES:
        cand = bo.build_candidate(mc)
        assert cand.name == mc
        assert callable(cand.fit_predict)


def test_exactly_one_native_distributional_foil():
    natives = [mc for mc in bo.MODEL_CLASSES if bo.build_candidate(mc).native]
    assert natives, "the bake-off must carry a native-joint foil to test retiring the 2-step r"
    for mc in natives:
        assert bo.default_dispersion(mc) == "native"
    for mc in set(bo.MODEL_CLASSES) - set(natives):
        assert bo.default_dispersion(mc) == "heldout"


def test_unknown_model_class_raises():
    with pytest.raises(KeyError):
        bo.build_candidate("not_a_model")


def test_incumbent_config_reproduces_e2_1_exactly():
    """The foil must be E2.1 AS SHIPPED — full contract, train-fit r — not a modernised one."""
    assert bo._INCUMBENT_CONTRACT == "full"
    assert bo._INCUMBENT_DISPERSION == "train"
    assert bo._INCUMBENT_DISPERSION in bo.DISPERSION_MODES


# ---------------------------------------------------------------------------
# Native (μ, σ) → NegBin r moment-match
# ---------------------------------------------------------------------------

def test_sigma_to_r_moment_matches_negbin_variance():
    mu = np.array([4.0, 5.0, 6.0])
    r_true = np.array([3.0, 8.0, 2.5])
    sigma = np.sqrt(mu + mu**2 / r_true)          # exact NegBin sd for (mu, r_true)
    assert np.allclose(bo.sigma_to_negbin_r(mu, sigma), r_true, rtol=1e-6)


def test_sigma_to_r_underdispersed_falls_back_to_poisson_limit():
    """σ² ≤ μ is not overdispersed — r must go to the upper bound (the Poisson limit), not blow up."""
    mu = np.array([4.0, 4.0])
    sigma = np.array([1.0, 2.0])                  # var 1 and 4, both ≤ mu
    r = bo.sigma_to_negbin_r(mu, sigma)
    assert np.all(r == bo._R_BOUNDS[1])


def test_sigma_to_r_always_within_optimiser_bounds():
    rng = np.random.default_rng(0)
    mu = rng.uniform(0.3, 12.0, size=500)
    sigma = rng.uniform(0.01, 20.0, size=500)
    r = bo.sigma_to_negbin_r(mu, sigma)
    assert np.all(r >= bo._R_BOUNDS[0]) and np.all(r <= bo._R_BOUNDS[1])
    assert np.all(np.isfinite(r))


# ---------------------------------------------------------------------------
# In-fold feature contracts
# ---------------------------------------------------------------------------

def _toy_matrix():
    rng = np.random.default_rng(7)
    a = rng.normal(size=400)
    X = np.column_stack([a, a + 1e-9 * rng.normal(size=400), rng.normal(size=400), np.ones(400)])
    return X, ["a", "a_dup", "b", "const"]


def test_clustered_contract_drops_the_redundant_twin_and_keeps_the_ranked_one():
    X, cols = _toy_matrix()
    kept = bo.clustered_contract(X, cols, ranking=["a", "a_dup", "b", "const"])
    assert "a" in kept and "a_dup" not in kept   # keeps the higher-ranked cluster member
    assert "b" in kept
    assert "const" not in kept                    # zero-variance in-fold carries no information


def test_top_k_contract_respects_the_ranking_and_size():
    X, cols = _toy_matrix()
    ranking = ["b", "a", "const", "a_dup"]
    kept = bo.resolve_contract("top_k", X, cols, ranking, top_k=2)
    assert kept == ["b", "a"]


def test_full_contract_is_the_untouched_column_list():
    X, cols = _toy_matrix()
    assert bo.resolve_contract("full", X, cols, ranking=list(cols)) == cols


def test_unknown_contract_raises():
    X, cols = _toy_matrix()
    with pytest.raises(KeyError):
        bo.resolve_contract("kitchen_sink", X, cols, ranking=list(cols))


# ---------------------------------------------------------------------------
# The downstream selection metric
# ---------------------------------------------------------------------------

def _metrics(calib: float, dev: float) -> dict:
    m = {"calib_80": calib, "pit_max_decile_dev": dev, "pit_mean_dev": 0.0, "pit_is_flat": True}
    return {k: dict(m) for k in ("total", "run_diff", "home_total", "away_total")}


def test_perfect_calibration_scores_zero():
    assert bo.downstream_score(_metrics(0.80, 0.0)) == pytest.approx(0.0)


def test_score_is_lower_is_better_and_symmetric_around_the_target():
    over = bo.downstream_score(_metrics(0.85, 0.0))
    under = bo.downstream_score(_metrics(0.75, 0.0))
    assert over == pytest.approx(under)          # both are miscalibration, neither is "safe"
    assert over > bo.downstream_score(_metrics(0.80, 0.0))


def test_run_diff_is_measured_but_excluded_from_selection():
    """E2.2/E2.3 attributed the run-diff miss to dropped dependence — scoring it would select
    on a defect the per-side marginal cannot fix."""
    assert "run_diff" not in bo.SCORED_DISTS
    base = _metrics(0.80, 0.0)
    poisoned = {**base, "run_diff": {"calib_80": 0.10, "pit_max_decile_dev": 0.9,
                                     "pit_mean_dev": 0.4, "pit_is_flat": False}}
    assert bo.downstream_score(poisoned) == pytest.approx(bo.downstream_score(base))


def test_pit_deviation_contributes_to_the_score():
    assert bo.downstream_score(_metrics(0.80, 0.05)) > bo.downstream_score(_metrics(0.80, 0.0))


def test_scored_dists_are_the_three_the_marginal_owns():
    assert set(bo.SCORED_DISTS) == {"total", "home_total", "away_total"}


# ---------------------------------------------------------------------------
# Convolution wiring (small, fast — guards the game-frame contract)
# ---------------------------------------------------------------------------

def test_convolved_metrics_returns_all_four_distributions():
    import pandas as pd

    rng = np.random.default_rng(1)
    n = 300
    g = pd.DataFrame({
        "mu_home": np.full(n, 4.6), "mu_away": np.full(n, 4.3),
        "r_home": np.full(n, 3.7), "r_away": np.full(n, 3.7),
        "y_home": rng.poisson(4.6, n).astype(float), "y_away": rng.poisson(4.3, n).astype(float),
    })
    m = bo.convolved_metrics(g, rng, n_draws=500)
    assert set(m) == {"total", "run_diff", "home_total", "away_total"}
    assert 0.0 <= m["total"]["calib_80"] <= 1.0
    assert np.isfinite(bo.downstream_score(m))
