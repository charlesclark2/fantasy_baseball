"""
h2h_classifier_model.py — Epic 11 Approach B (Story 11.3) artifact wrapper

Stable-path wrapper for the H2H direct-classifier champion so the pickled artifact
binds to an importable module (not __main__). Holds the fitted estimator (an
elasticnet logistic Pipeline, or a Platt-calibrated LightGBM via
CalibratedClassifierCV) plus the feature-column contract, and exposes a single
`predict_proba_home(X) -> p(home_win)` used at inference time.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class H2HClassifierModel:
    model_type: str            # 'elasticnet' | 'lightgbm'
    model: object              # sklearn Pipeline (elasticnet) or CalibratedClassifierCV / LGBMClassifier
    feature_columns: list      # contract column order
    calibrated: bool = False   # True when `model` already wraps Platt (sigmoid) calibration

    def predict_proba_home(self, X: pd.DataFrame) -> np.ndarray:
        """P(home win) for each row of X (columns coerced to the contract order)."""
        Xc = X[self.feature_columns].apply(pd.to_numeric, errors="coerce")
        return np.asarray(self.model.predict_proba(Xc)[:, 1], dtype=float)
