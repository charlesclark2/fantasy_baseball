"""Unit tests for the E13.4 incremental-lift harness pure-logic primitives.

These exercise the harness MATH without Snowflake or a model fit (the numeric lift run is an
operator job). They are the "validate the harness before trusting it" guard at the code level:
a sanity candidate that is pure noise must read ~0 lift / high PBO, an in-contract duplicate
must read ~0 incremental lift, and the scoring/shrinkage helpers must be correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.scripts.incremental_lift_eval import (
    candidate_dsr, candidate_is_degenerate, eb_shrink_toward_mean, max_abs_corr, negbin_crps,
    negbin_nll, stratified_lift, time_sliced_perf,
)


def test_eb_shrink_toward_mean_endpoints():
    raw = np.array([1.0, 1.0, 1.0])
    n = np.array([0.0, 1.0, 1e9])
    prior = 0.0
    out = eb_shrink_toward_mean(raw, n, prior=prior, k=1.0)
    assert out[0] == 0.0                      # n=0 → collapses to prior
    assert abs(out[1] - 0.5) < 1e-9           # n=k=1 → midpoint
    assert abs(out[2] - 1.0) < 1e-6           # huge n → ≈ raw


def test_eb_shrink_nan_raw_collapses_to_prior():
    out = eb_shrink_toward_mean(np.array([np.nan]), np.array([0.0]), prior=2.0, k=4.0)
    assert abs(out[0] - 2.0) < 1e-9


def test_negbin_nll_matches_reference_mean():
    # cross-check the vectorized NLL against train_perside_negbin's mean implementation
    from betting_ml.scripts.totals_generative.train_perside_negbin import (
        negbin_nll as ref_mean_nll,
    )
    rng = np.random.default_rng(0)
    y = rng.poisson(4.5, size=200).astype(float)
    mu = np.full_like(y, 4.5)
    r = 5.0
    assert abs(negbin_nll(y, mu, r).mean() - ref_mean_nll(y, mu, r)) < 1e-9


def test_negbin_crps_nonnegative_and_better_mean_scores_lower():
    y = np.array([4.0, 4.0, 4.0])
    good = negbin_crps(y, np.array([4.0, 4.0, 4.0]), r=5.0)
    bad = negbin_crps(y, np.array([9.0, 9.0, 9.0]), r=5.0)
    assert np.all(good >= 0)
    assert good.mean() < bad.mean()           # a mean near truth scores lower CRPS


def test_stratified_lift_signs_and_strata():
    base = np.array([1.0, 1.0, 1.0, 1.0])
    cand = np.array([0.5, 0.5, 1.5, 1.5])     # better on first two, worse on last two
    non_cold = np.array([True, True, False, False])
    out = {s.stratum: s for s in stratified_lift(base, cand, non_cold)}
    assert out["all"].lift == 0.0             # net zero across all (cand mean 1.0)
    assert out["non_cold_start"].lift == 0.5  # candidate better on non-cold
    assert out["cold_start"].lift == -0.5     # candidate worse on cold
    assert out["non_cold_start"].n == 2


def test_stratified_lift_duplicate_is_zero_lift():
    base = np.array([0.3, 0.7, 0.5, 0.9])
    out = {s.stratum: s for s in stratified_lift(base, base.copy(), None)}
    assert out["all"].lift == 0.0             # an in-contract duplicate ⇒ exactly 0 incremental


def test_time_sliced_perf_shape_and_order():
    dates = pd.to_datetime(["2026-01-03", "2026-01-01", "2026-01-02", "2026-01-04"]).values
    scores = {"base": np.array([4.0, 1.0, 2.0, 3.0]), "cand": np.array([4.0, 1.0, 2.0, 3.0])}
    M, names = time_sliced_perf(dates, scores, n_slices=2)
    assert M.shape == (2, 2)
    assert names == ["base", "cand"]
    # sorted by date the base scores are [1,2,3,4] → slice means [1.5, 3.5]
    assert abs(M[0, 0] - 1.5) < 1e-9 and abs(M[1, 0] - 3.5) < 1e-9


def test_candidate_dsr_noise_is_not_significant():
    rng = np.random.default_rng(1)
    base = rng.normal(1.0, 0.2, size=500)
    cand = base + rng.normal(0.0, 0.2, size=500)   # no systematic improvement
    dsr = candidate_dsr(base, cand, n_trials=3)
    assert dsr is not None
    assert not dsr.passes_live                      # pure noise must NOT clear DSR≥0.95


def test_candidate_dsr_real_improvement_is_significant():
    rng = np.random.default_rng(2)
    base = rng.normal(1.0, 0.2, size=800)
    cand = base - 0.10                              # consistent per-game improvement
    dsr = candidate_dsr(base, cand, n_trials=1)
    assert dsr is not None and dsr.passes_live      # a real, consistent gain clears DSR


def test_degenerate_flags_constant_candidate():
    # a ~constant candidate column (corrupt/collapsed feature) is INVALID, not a null
    deg, reason = candidate_is_degenerate(0.0, all_lift=0.0031, dsr=None)
    assert deg and "constant" in reason


def test_degenerate_flags_zero_effect_candidate():
    # byte-identical scores to base (lift≡0, DSR n/a) = feature had no effect = INVALID
    deg, reason = candidate_is_degenerate(0.05, all_lift=0.0, dsr=None)
    assert deg and "NO effect" in reason


def test_degenerate_passes_a_real_candidate():
    class _DSR:  # a real candidate has variance + a computable DSR → not degenerate
        pass
    deg, reason = candidate_is_degenerate(0.02, all_lift=0.0015, dsr=_DSR())
    assert not deg and reason is None


def test_max_abs_corr_detects_redundancy():
    rng = np.random.default_rng(3)
    x = rng.normal(size=200)
    df = pd.DataFrame({"base_a": x, "base_b": rng.normal(size=200),
                       "cand_redundant": x + rng.normal(0, 1e-3, size=200),
                       "cand_orthogonal": rng.normal(size=200)})
    out = max_abs_corr(df, ["cand_redundant", "cand_orthogonal"], ["base_a", "base_b"])
    assert out["cand_redundant"]["max_abs_corr"] > 0.9    # ~ copy of base_a
    assert out["cand_redundant"]["vs"] == "base_a"
    assert out["cand_orthogonal"]["max_abs_corr"] < 0.4
