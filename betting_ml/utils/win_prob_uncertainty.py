"""win_prob_uncertainty.py — Story 19.7: Beta(α,β) credible interval on P(home win).

Implements the Approach-A Beta representation from the h2h-v2 spec (impl-guide 11.2):
express the served home-win probability as a Beta(α,β) whose mean is the point estimate
and whose concentration κ=α+β encodes confidence, then report the 80% credible interval
[Beta.ppf(0.10), Beta.ppf(0.90)].

The spec's `win_prob_to_beta(p, combined_sigma)` needs a per-game σ. The champion serve
path (scripts/predict_today.py) does not compute the Epic-9 stacking `combined_sigma`, but
it DOES carry two independent home-win estimators per game — NGBoost run-diff P(home win)
and the XGBoost classifier. Their dispersion is an honest across-model σ; we add a small
irreducible base so the interval never collapses to zero width when the two happen to agree.

This is the documented serve-time σ source. If/when the Epic-9 `combined_sigma` is available
in the serve path, pass it directly to `win_prob_to_beta` for the principled stacking-based
concentration instead.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np

# Irreducible model uncertainty on the win probability (probability units). Floors σ so a
# game where the two estimators agree exactly still gets a finite-width CI.
_BASE_SIGMA = 0.03
# Concentration guards: never tighter than this (avoid a degenerate spike) / never flatter
# than ~uniform (the spec's 2.0 floor).
_MIN_CONCENTRATION = 2.0
_MAX_CONCENTRATION = 1000.0


def win_prob_to_beta(p_home_win: float, combined_sigma: float) -> tuple[float, float]:
    """Fit Beta(α, β) with mean = p_home_win and variance implied by combined_sigma.

    Beta variance = p(1-p)/(κ+1) ⇒ κ = p(1-p)/σ² − 1. Mirrors impl-guide 11.2 exactly,
    with an added upper clamp on κ so a tiny σ cannot manufacture an absurdly tight CI.
    """
    p = float(min(max(p_home_win, 1e-6), 1 - 1e-6))
    variance = float(combined_sigma) ** 2
    if variance <= 0:
        concentration = _MAX_CONCENTRATION
    else:
        concentration = p * (1 - p) / variance - 1.0
    concentration = float(min(max(concentration, _MIN_CONCENTRATION), _MAX_CONCENTRATION))
    return p * concentration, (1 - p) * concentration


def ensemble_sigma(estimator_probs: Iterable[float], base_sigma: float = _BASE_SIGMA) -> float:
    """Across-model σ on the win prob: dispersion of the independent estimators, combined
    in quadrature with an irreducible base. Estimators that are None/NaN are dropped."""
    vals = [float(v) for v in estimator_probs if v is not None and np.isfinite(v)]
    disagreement = float(np.std(vals)) if len(vals) >= 2 else 0.0
    return float(np.sqrt(disagreement ** 2 + base_sigma ** 2))


def compute_win_prob_beta(
    p_point: float,
    estimator_probs: Iterable[float],
    base_sigma: float = _BASE_SIGMA,
) -> dict[str, float] | None:
    """Per-game Beta(α,β) + 80% credible interval on P(home win).

    p_point        — the served point estimate (calibrated_win_prob) → Beta mean.
    estimator_probs— independent home-win estimates (ngboost run-diff, classifier) → σ.
    Returns win_prob_alpha/beta, win_prob_ci_low/high (80% CI), win_prob_ci_width, and the
    σ used. Returns None when p_point is missing (e.g. no model output for the game).
    """
    if p_point is None or not np.isfinite(p_point):
        return None
    from scipy.stats import beta as _beta

    sigma = ensemble_sigma(estimator_probs, base_sigma=base_sigma)
    alpha, beta_param = win_prob_to_beta(float(p_point), sigma)
    ci_low = float(_beta.ppf(0.10, alpha, beta_param))
    ci_high = float(_beta.ppf(0.90, alpha, beta_param))
    return {
        "win_prob_alpha": round(alpha, 4),
        "win_prob_beta": round(beta_param, 4),
        "win_prob_ci_low": round(ci_low, 4),
        "win_prob_ci_high": round(ci_high, 4),
        "win_prob_ci_width": round(ci_high - ci_low, 4),
        "win_prob_sigma": round(sigma, 4),
    }
