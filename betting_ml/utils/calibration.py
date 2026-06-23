"""Calibration helpers for the win-probability layer.

IdentityCalibrator is a picklable pass-through used when the raw consensus is already
the best-calibrated option (Story A2.9): the 2026-06-10 audit showed the live Platt
calibrator — fit on feature-degraded data and selected by ECE — flattened the recovered
signal and worsened Brier. When the re-fit selects "identity", we persist this object as
calibrator.joblib so the deployed scorers (predict_today, backfill) load it via the SAME
joblib path and `predict_proba(x)[:, 1] == x` (calibrated == consensus), with no special-
casing. It MUST live in a stable importable module (not a script's __main__) or the
pickle will not resolve at load time.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-6


class TemperatureCalibrator:
    """Single-parameter temperature scaling on the logit: p' = sigmoid(logit(p)/T).

    Story E13.6 (2026-06-21): the SERVED home_win prob (identity-calibrated consensus of the
    de-leaked v5 champion) was OVERCONFIDENT — spread 0.20 but corr ~0.07, ECE 0.154, a worse
    proper-score forecast than the base rate. T>1 shrinks toward the base rate to remove that
    false precision (T<1 would sharpen an underconfident prob). Monotone + spread-honest: it
    rescales confidence without flattening to a constant. This REVERSES the A2.9 identity choice
    for the SERVED surface (A2.9 was validated on the now-removed-leak 376-dim model where the
    prob genuinely discriminated). INTERIM — re-fit after any 30.3/Epic-33 serving fix or the
    E1.9 v6 rebuild (see calibrator_meta.json REFIT_GUARD). Lives here, not in the audit script,
    so the promoted pickle resolves in predict_today/backfill (same reason as IdentityCalibrator).
    """

    def __init__(self, temperature: float):
        self.temperature = float(temperature)

    def _apply(self, x: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(x, dtype=float).reshape(-1), _EPS, 1 - _EPS)
        z = np.log(p / (1 - p)) / self.temperature
        return 1.0 / (1.0 + np.exp(-z))

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        p = self._apply(x)
        return np.column_stack([1.0 - p, p])

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self._apply(x)


class IdentityCalibrator:
    """Pass-through calibrator: calibrated probability == consensus probability.

    Mirrors the sklearn calibrator interface predict_today expects:
    `predict_proba(x)[:, 1]` returns x unchanged.
    """

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        p = np.asarray(x, dtype=float).reshape(-1)
        return np.column_stack([1.0 - p, p])

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=float).reshape(-1)
