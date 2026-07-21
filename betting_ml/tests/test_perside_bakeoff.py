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


def test_score_ignores_calib_80_because_discreteness_inflates_it():
    """🩹 2026-07-20 correction. calib_80 uses INCLUSIVE integer bounds, so a perfectly
    specified count model covers ~0.82-0.86, not 0.80 (see test_oracle_is_the_scoring_floor).
    Scoring |calib_80 - 0.80| therefore REWARDED under-dispersion and inverted the stage-1
    ranking. The score is PIT-only; calib_80 survives as a FLOOR, not a target."""
    base = bo.downstream_score(_metrics(0.80, 0.01))
    for calib in (0.75, 0.80, 0.85, 0.90):
        assert bo.downstream_score(_metrics(calib, 0.01)) == pytest.approx(base)


def test_calibration_floor_rejects_undercoverage_and_allows_overcoverage():
    assert bo.passes_calibration_floor(_metrics(0.85, 0.0))    # too wide = conservative, OK
    assert bo.passes_calibration_floor(_metrics(0.80, 0.0))    # exactly at the floor
    assert not bo.passes_calibration_floor(_metrics(0.79, 0.0))  # under-covers = rejected


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


# ---------------------------------------------------------------------------
# Draw-once-then-slice (the PBO-bucket optimisation)
# ---------------------------------------------------------------------------

def _game_frame(n=400, seed=3):
    import pandas as pd

    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "mu_home": np.full(n, 4.6), "mu_away": np.full(n, 4.3),
        "r_home": np.full(n, 3.7), "r_away": np.full(n, 3.7),
        "y_home": rng.poisson(4.6, n).astype(float), "y_away": rng.poisson(4.3, n).astype(float),
    })


def test_slicing_the_draws_matches_scoring_that_subset_directly():
    """A row-subset of a fold's draws must BE the sub-population's predictive — that identity is
    what makes re-drawing per PBO bucket unnecessary."""
    g = _game_frame()
    dists, obs = bo.draw_predictive(g, np.random.default_rng(0), n_draws=800)
    rows = np.arange(100, 250)
    sliced = bo.score_predictive(dists, obs, np.random.default_rng(5), rows=rows)

    sub_dists = {k: v[rows] for k, v in dists.items()}
    sub_obs = {k: v[rows] for k, v in obs.items()}
    direct = bo.score_predictive(sub_dists, sub_obs, np.random.default_rng(5))
    for k in sliced:
        assert sliced[k]["calib_80"] == pytest.approx(direct[k]["calib_80"])


def test_convolved_metrics_still_matches_draw_then_score():
    """The one-call convenience form must stay equivalent to the split form."""
    g = _game_frame()
    combined = bo.convolved_metrics(g, np.random.default_rng(11), n_draws=600)
    dists, obs = bo.draw_predictive(g, np.random.default_rng(11), n_draws=600)
    split = bo.score_predictive(dists, obs, np.random.default_rng(11))
    for k in combined:
        assert combined[k]["calib_80"] == pytest.approx(split[k]["calib_80"])


def test_draw_predictive_shapes_are_games_by_draws():
    g = _game_frame(n=120)
    dists, obs = bo.draw_predictive(g, np.random.default_rng(2), n_draws=300)
    for k in ("total", "run_diff", "home_total", "away_total"):
        assert dists[k].shape == (120, 300)
        assert obs[k].shape == (120,)


# ---------------------------------------------------------------------------
# The oracle guard — the regression test for the 2026-07-20 metric inversion
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_oracle_is_the_scoring_floor():
    """No model may score BETTER than a perfectly-specified one.

    This is the check that caught the metric bug: E2.1-r's stage-1 "winner" scored 0.1426 while
    an oracle — truth drawn from exactly the NegBin being scored, zero misspecification —
    scored 0.1624. Beating the oracle is impossible for an honestly-calibrated model, so the
    metric had to be wrong (|calib_80 - 0.80| was rewarding under-dispersion, because inclusive
    integer interval bounds inflate a CORRECT model's coverage well above the nominal 0.80).
    """
    import pandas as pd

    rng = np.random.default_rng(0)
    n, mu_h, mu_a, r = 2500, 4.6, 4.3, 3.7

    def draw_nb(mu, size):
        return rng.negative_binomial(r, r / (r + mu), size=size).astype(float)

    g = pd.DataFrame({
        "mu_home": np.full(n, mu_h), "mu_away": np.full(n, mu_a),
        "r_home": np.full(n, r), "r_away": np.full(n, r),
        "y_home": draw_nb(mu_h, n), "y_away": draw_nb(mu_a, n),
    })
    m = bo.convolved_metrics(g, rng, n_draws=2000)

    # The oracle passes the floor and is PIT-flat — both by construction.
    assert bo.passes_calibration_floor(m)
    for j in bo.SCORED_DISTS:
        assert m[j]["pit_max_decile_dev"] < 0.025, f"{j} oracle PIT should be flat"

    # And the artefact that caused the inversion is REAL and must stay documented: a perfect
    # discrete model does NOT cover the nominal 0.80 — it over-covers.
    assert m["total"]["calib_80"] > 0.81
    assert m["home_total"]["calib_80"] > 0.84


# ---------------------------------------------------------------------------
# Verdict logic — the two-axis decision (2026-07-20 rewrite)
# ---------------------------------------------------------------------------

def _cfg(config_id, score, calib, *, incumbent=False, n_buckets=20, seed=0):
    """A synthetic config result. bucket_scores centre on `score` with small noise so PBO/DSR
    have something to chew on; calib sets the floor pass/fail."""
    rng = np.random.default_rng(seed)
    buckets = list(np.round(score + rng.normal(0, score * 0.05 + 1e-4, n_buckets), 6))
    m = {"calib_80": calib, "pit_max_decile_dev": score, "pit_mean_dev": 0.0,
         "pit_is_flat": True}
    return {
        "config_id": config_id,
        "is_incumbent": incumbent,
        "bucket_scores": buckets,
        "pooled_downstream_score": score,
        "pooled_metrics": {k: dict(m) for k in ("total", "run_diff", "home_total", "away_total")},
        "passes_calibration_floor": calib >= bo._CALIB_TARGET,
        "mean_per_side_negbin_nll": 2.45,
    }


def test_verdict_never_says_incumbent_stands_when_incumbent_fails_floor():
    """The bug this rewrite fixes: a floor-failing incumbent was reported as 'proven best'."""
    results = [
        _cfg("lgbm_poisson__full__train", 0.135, 0.778, incumbent=True, seed=1),
        _cfg("lgbm_poisson__full__heldout", 0.026, 0.835, seed=2),
        _cfg("catboost_poisson__top_k__heldout", 0.025, 0.833, seed=3),
    ]
    d = bo.decide_verdict(results)
    assert d["verdict"] != "INCUMBENT_STANDS"
    assert d["incumbent_passes_floor"] is False


def _cfg_buckets(config_id, buckets, calib, *, incumbent=False):
    """A config with EXPLICIT bucket_scores (so PBO's rank behaviour is controllable)."""
    m = {"calib_80": calib, "pit_max_decile_dev": float(np.mean(buckets)),
         "pit_mean_dev": 0.0, "pit_is_flat": True}
    return {
        "config_id": config_id, "is_incumbent": incumbent,
        "bucket_scores": [float(b) for b in buckets],
        "pooled_downstream_score": float(np.mean(buckets)),
        "pooled_metrics": {k: dict(m) for k in ("total", "run_diff", "home_total", "away_total")},
        "passes_calibration_floor": calib >= bo._CALIB_TARGET,
        "mean_per_side_negbin_nll": 2.45,
    }


def test_verdict_promotes_minimal_fix_when_learner_cluster_is_tied():
    """The E2.1-r shape: incumbent broken; a tied learner cluster whose members all beat the
    incumbent every bucket but ROTATE ranks among themselves (→ high full-search PBO = a learner
    NULL); the same-learner dispersion switch is robust → PROMOTE_MINIMAL_FIX keeping the learner.
    """
    nb = 24
    cluster = [
        "glm_poisson__top_k__heldout", "catboost_poisson__top_k__heldout",
        "xgb_poisson__full__heldout", "lgbm_poisson__full__heldout",
        "lgbm_poisson__top_k__heldout", "xgb_poisson__top_k__heldout",
    ]
    results = [_cfg_buckets("lgbm_poisson__full__train", [0.135] * nb, 0.778, incumbent=True)]
    # each cluster member is best (0.024) in the buckets it "owns" and 0.026 elsewhere — all
    # well below the incumbent's 0.135 every bucket, but the in-sample champion rotates → the
    # cross-learner winner is not identifiable (high PBO), while every member beats the incumbent.
    for i, lc in enumerate(cluster):
        buckets = [0.024 if (b % len(cluster)) == i else 0.026 for b in range(nb)]
        results.append(_cfg_buckets(lc, buckets, 0.834))
    d = bo.decide_verdict(results)
    assert d["full_pbo"] >= bo._PBO_GATE, "the rotating cluster should NOT be deflation-clean"
    assert d["verdict"] == "PROMOTE_MINIMAL_FIX"
    # the winner keeps the incumbent's learner + contract; only dispersion changed
    assert bo._learner_of(d["winner"]["config_id"]) == "lgbm_poisson"
    assert d["winner"]["config_id"] == "lgbm_poisson__full__heldout"
    assert d["requires_downstream_rerun"] is True


def test_verdict_promotes_outright_when_search_is_deflation_clean():
    """A single clearly-separated winner (not a tied cluster) → PROMOTE."""
    results = [_cfg("lgbm_poisson__full__train", 0.20, 0.83, incumbent=True, seed=1)]
    results.append(_cfg("ngboost_normal__full__native", 0.05, 0.82, seed=2))
    # filler configs all clearly worse than the winner, so the winner is identifiable
    for i in range(6):
        results.append(_cfg(f"filler_{i}__full__heldout", 0.15 + 0.01 * i, 0.83, seed=20 + i))
    d = bo.decide_verdict(results)
    assert d["verdict"] == "PROMOTE"
    assert d["winner"]["config_id"] == "ngboost_normal__full__native"


def test_verdict_incumbent_stands_when_it_passes_floor_and_nothing_beats_it():
    results = [
        _cfg("lgbm_poisson__full__train", 0.025, 0.83, incumbent=True, seed=1),
        _cfg("xgb_poisson__full__heldout", 0.026, 0.834, seed=2),
        _cfg("glm_poisson__full__heldout", 0.027, 0.836, seed=3),
    ]
    d = bo.decide_verdict(results)
    assert d["verdict"] == "INCUMBENT_STANDS"
    assert d["winner"] is None
    assert d["requires_downstream_rerun"] is False
