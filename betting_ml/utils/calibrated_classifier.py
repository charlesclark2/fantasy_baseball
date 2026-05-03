from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier


class PlattCalibratedXGBClassifier:
    """XGBClassifier with a fitted Platt (sigmoid) calibrator."""

    def __init__(self, xgb_classifier: XGBClassifier, calibrator: LogisticRegression) -> None:
        self.xgb_classifier = xgb_classifier
        self.calibrator = calibrator

    def predict_proba(self, X) -> np.ndarray:
        raw = self.xgb_classifier.predict_proba(X)[:, 1]
        return self.calibrator.predict_proba(raw.reshape(-1, 1))
