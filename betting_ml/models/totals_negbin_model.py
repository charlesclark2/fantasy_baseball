"""
totals_negbin_model.py — Epic 10 (Stories 10.2/10.3)

The Layer 3 totals champion's picklable model object and the predict-time helpers
it depends on. This lives in an importable module (NOT in the `train_totals.py`
entrypoint) so the pickled artifact binds to a stable class path
(`betting_ml.models.totals_negbin_model.TotalsNegBinModel`) and unpickles cleanly
from any caller — score_totals_layer3, predict_today, Dagster.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def coerce_numeric(X: pd.DataFrame) -> pd.DataFrame:
    """Make the Layer 3 matrix model-ready: `*_available` flags arrive as object
    (Snowflake booleans) → float 0/1 (missing → 0 = not available); any other
    object column → numeric. mu/spread/uncertainty NaN (missing signal groups) is
    preserved — LightGBM handles it natively; Ridge/GLM median-impute it. Applied
    identically at train and inference so the representation matches.
    """
    X = X.copy()
    for c in X.columns:
        if X[c].dtype == object:
            X[c] = pd.to_numeric(X[c], errors="coerce")
    avail = [c for c in X.columns if c.endswith("_available")]
    if avail:
        X[avail] = X[avail].fillna(0.0)
    return X


def assign_r(mu: np.ndarray, edges: np.ndarray, r_per_bin: np.ndarray, global_r: float) -> np.ndarray:
    """Map each predicted mu to its predicted-mean-decile NegBin r (global fallback)."""
    if len(edges) == 0 or len(r_per_bin) == 0:
        return np.full(len(mu), global_r, dtype=float)
    bins = np.clip(np.digitize(mu, edges), 0, len(r_per_bin) - 1)
    return r_per_bin[bins]


class TotalsNegBinModel:
    """Layer 3 totals champion: conditional-mean model + decile NegBin dispersion.

    `predict_mu_r(X)` returns the NegBin (mu, r) per game for Stories 10.3 / 10.6.
    """

    def __init__(self, model_type: str, mean_model, feature_cols: list[str],
                 decile_edges: np.ndarray, decile_r: np.ndarray, global_r: float):
        self.model_type = model_type          # "lightgbm" | "ridge"
        self.mean_model = mean_model
        self.feature_cols = list(feature_cols)
        self.decile_edges = np.asarray(decile_edges, dtype=float)
        self.decile_r = np.asarray(decile_r, dtype=float)
        self.global_r = float(global_r)
        self.version = "totals_v1"

    def predict_mu(self, X: pd.DataFrame) -> np.ndarray:
        mu = self.mean_model.predict(coerce_numeric(X[self.feature_cols]))
        return np.clip(np.asarray(mu, dtype=float), 1e-6, None)

    def predict_mu_r(self, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        mu = self.predict_mu(X)
        r = assign_r(mu, self.decile_edges, self.decile_r, self.global_r)
        return mu, r
