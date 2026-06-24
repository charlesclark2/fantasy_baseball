from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier


class PlattCalibratedXGBClassifier:
    """XGBClassifier with a fitted Platt (sigmoid) calibrator."""

    def __init__(self, xgb_classifier: XGBClassifier, calibrator: LogisticRegression) -> None:
        self.xgb_classifier = xgb_classifier
        self.calibrator = calibrator

    @property
    def n_features_in_(self) -> int:
        return self.xgb_classifier.n_features_in_

    def predict_proba(self, X) -> np.ndarray:
        raw = self.xgb_classifier.predict_proba(X)[:, 1]
        return self.calibrator.predict_proba(raw.reshape(-1, 1))


class PlattCalibratedLinearClassifier:
    """Linear (glm_elasticnet) pipeline with a fitted Platt (sigmoid) calibrator.

    The Edge Program E1.9 de-leaked v6 home_win champion is a
    ``Pipeline(StandardScaler, LogisticRegression(penalty="elasticnet"))`` — the
    bake-off winner (tree/HPO overfits the thin home_win signal on lean
    contracts). This mirrors PlattCalibratedXGBClassifier so predict_today's
    serving path is class-agnostic: it loads the artifact, calls
    ``predict_proba(X)[:, 1]``, and the CONTRACT-GUARD reads ``n_features_in_``.

    `linear_pipeline` is exposed so the per-pick explainer (Story 30.15) can run
    EXACT linear SHAP on the underlying coefficients instead of TreeSHAP — the
    Platt calibrator (and the served TemperatureCalibrator) are both monotonic,
    so a feature's signed contribution to the logit preserves its sign/ranking
    through calibration, exactly as the TreeSHAP path relies on for XGBoost.

    Lives in this stable importable module (not a script's __main__) so the
    promoted pickle resolves at load time in predict_today / backfill — same
    constraint as IdentityCalibrator / TemperatureCalibrator.
    """

    def __init__(self, pipeline, calibrator: LogisticRegression) -> None:
        self.pipeline = pipeline
        self.calibrator = calibrator

    @property
    def n_features_in_(self) -> int:
        return int(self.pipeline.n_features_in_)

    @property
    def linear_pipeline(self):
        """The fitted StandardScaler + LogisticRegression pipeline (for linear SHAP)."""
        return self.pipeline

    def predict_proba(self, X) -> np.ndarray:
        raw = self.pipeline.predict_proba(X)[:, 1]
        return self.calibrator.predict_proba(raw.reshape(-1, 1))
