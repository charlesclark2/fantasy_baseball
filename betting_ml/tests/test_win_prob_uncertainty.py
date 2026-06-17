"""Unit tests for win_prob_uncertainty (Story 19.7).

Covers the Beta(α,β) win-probability credible interval: the concentration math
(win_prob_to_beta), the across-estimator σ source (ensemble_sigma), and the
end-to-end per-game output (compute_win_prob_beta) — including the invariants the
serve path and the app rely on (CI brackets the point estimate; width grows with
estimator disagreement; never collapses to zero; None-safe).
"""
from __future__ import annotations

import math

import pytest

from betting_ml.utils.win_prob_uncertainty import (
    _BASE_SIGMA,
    _MAX_CONCENTRATION,
    _MIN_CONCENTRATION,
    compute_win_prob_beta,
    ensemble_sigma,
    win_prob_to_beta,
)


# ── win_prob_to_beta ────────────────────────────────────────────────────────────

def test_beta_mean_equals_point_estimate():
    p = 0.62
    a, b = win_prob_to_beta(p, 0.05)
    assert a / (a + b) == pytest.approx(p, abs=1e-9)


def test_small_sigma_gives_high_concentration_capped():
    # σ→0 ⇒ concentration clamps at the max (no infinite spike).
    a, b = win_prob_to_beta(0.5, 1e-9)
    assert a + b == pytest.approx(_MAX_CONCENTRATION, rel=1e-6)


def test_large_sigma_floors_at_min_concentration():
    # σ ≥ sqrt(p(1-p)) ⇒ variance ≥ p(1-p) ⇒ concentration floored at 2.0.
    a, b = win_prob_to_beta(0.5, 0.9)
    assert a + b == pytest.approx(_MIN_CONCENTRATION, rel=1e-6)


def test_zero_or_negative_sigma_does_not_blow_up():
    a, b = win_prob_to_beta(0.55, 0.0)
    assert a + b == pytest.approx(_MAX_CONCENTRATION, rel=1e-6)
    assert math.isfinite(a) and math.isfinite(b)


# ── ensemble_sigma ──────────────────────────────────────────────────────────────

def test_ensemble_sigma_floors_at_base_on_agreement():
    assert ensemble_sigma([0.6, 0.6]) == pytest.approx(_BASE_SIGMA, abs=1e-9)


def test_ensemble_sigma_grows_with_disagreement():
    assert ensemble_sigma([0.45, 0.75]) > ensemble_sigma([0.58, 0.62]) > _BASE_SIGMA


def test_ensemble_sigma_ignores_none_and_nan():
    assert ensemble_sigma([0.6, None, float("nan")]) == pytest.approx(_BASE_SIGMA, abs=1e-9)


# ── compute_win_prob_beta (end-to-end) ──────────────────────────────────────────

def test_output_keys_present():
    out = compute_win_prob_beta(0.6, [0.58, 0.62])
    assert set(out) == {
        "win_prob_alpha", "win_prob_beta",
        "win_prob_ci_low", "win_prob_ci_high", "win_prob_ci_width", "win_prob_sigma",
    }


@pytest.mark.parametrize("p,est", [
    (0.60, [0.60, 0.60]),
    (0.52, [0.50, 0.54]),
    (0.85, [0.82, 0.88]),
    (0.30, [0.45, 0.15]),  # away-favored game, wide disagreement
])
def test_ci_brackets_point_estimate(p, est):
    out = compute_win_prob_beta(p, est)
    assert out["win_prob_ci_low"] < p < out["win_prob_ci_high"]


def test_width_monotone_in_disagreement():
    agree = compute_win_prob_beta(0.6, [0.60, 0.60])["win_prob_ci_width"]
    mild = compute_win_prob_beta(0.6, [0.55, 0.65])["win_prob_ci_width"]
    wide = compute_win_prob_beta(0.6, [0.45, 0.75])["win_prob_ci_width"]
    assert agree < mild < wide


def test_width_never_zero_even_on_perfect_agreement():
    assert compute_win_prob_beta(0.6, [0.60, 0.60])["win_prob_ci_width"] > 0.0


def test_symmetric_in_side_magnitude():
    # |edge| drives uncertainty, not the side: a home-lean and the mirrored away-lean
    # with the same estimator spread get the same CI width.
    home = compute_win_prob_beta(0.70, [0.66, 0.74])["win_prob_ci_width"]
    away = compute_win_prob_beta(0.30, [0.34, 0.26])["win_prob_ci_width"]
    assert home == pytest.approx(away, abs=1e-9)


def test_none_point_returns_none():
    assert compute_win_prob_beta(None, [0.5, 0.6]) is None
    assert compute_win_prob_beta(float("nan"), [0.5, 0.6]) is None
