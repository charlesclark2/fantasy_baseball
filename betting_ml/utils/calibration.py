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
