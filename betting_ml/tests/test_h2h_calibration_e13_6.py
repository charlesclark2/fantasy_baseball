"""Story E13.6 — unit tests for the H2H calibration audit metric/calibrator primitives.

Pure functions only (no Snowflake): proper-score behavior, ECE detection of
overconfidence, temperature-scaling direction, and the candidate selection contract.
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.scripts.h2h_calibration_audit_e13_6 import (
    TemperatureCalibrator,
    brier,
    ece,
    fit_candidates,
    fit_temperature,
    log_loss,
)


def test_brier_and_logloss_perfect_vs_worst():
    y = np.array([1.0, 0.0, 1.0, 0.0])
    assert brier(y, y) == pytest.approx(0.0)
    # A confidently-wrong forecast scores worse than a coin flip on both scores.
    wrong = 1 - y
    assert brier(wrong, y) > brier(np.full_like(y, 0.5), y)
    assert log_loss(wrong, y) > log_loss(np.full_like(y, 0.5), y)


def test_ece_zero_when_calibrated_high_when_overconfident():
    rng = np.random.default_rng(0)
    # Calibrated: outcomes drawn at the stated probability → near-zero ECE.
    p = rng.uniform(0.1, 0.9, size=4000)
    y = (rng.uniform(size=4000) < p).astype(float)
    assert ece(p, y) < 0.03
    # Overconfident: stated probs pushed to the tails but truth is a coin flip → high ECE.
    p_over = np.where(p > 0.5, 0.9, 0.1)
    y_flat = (rng.uniform(size=4000) < 0.5).astype(float)
    assert ece(p_over, y_flat) > 0.3


def test_fit_temperature_shrinks_overconfident_probs():
    # Probs at the tails but coin-flip truth → T should be >1 (shrink toward 0.5).
    rng = np.random.default_rng(1)
    p = np.where(rng.uniform(size=3000) > 0.5, 0.9, 0.1)
    y = (rng.uniform(size=3000) < 0.5).astype(float)
    T = fit_temperature(p, y)
    assert T > 1.0
    out = TemperatureCalibrator(T).predict(p)
    # Shrinking pulls every prediction toward the base rate → smaller spread, no flip.
    assert out.std() < p.std()
    assert np.all((out > 0.0) & (out < 1.0))


def test_temperature_one_is_identity():
    p = np.array([0.2, 0.4, 0.5, 0.7, 0.85])
    out = TemperatureCalibrator(1.0).predict(p)
    np.testing.assert_allclose(out, p, atol=1e-6)


def test_fit_candidates_recovers_calibration_on_overconfident_input():
    # Overconfident, no-discrimination input (the E13.6 served regime): every recalibrator
    # must lower ECE vs identity, and the ECE-pick must not be identity.
    rng = np.random.default_rng(2)
    n = 1200
    p = np.where(rng.uniform(size=n) > 0.5, 0.85, 0.15)
    y = (rng.uniform(size=n) < 0.5).astype(float)
    rep = fit_candidates(p, y, eval_frac=0.25)
    s = rep["eval_stats"]
    assert s["platt"]["ece"] < s["identity"]["ece"]
    assert rep["ece_pick"] != "identity"
    assert "T" in s["temperature"]
