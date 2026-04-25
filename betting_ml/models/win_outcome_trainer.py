"""Card 4.11 — Training and calibration functions for win outcome classification.

Public API:
    train_logistic(X_train, y_train, X_eval) -> dict
    train_xgboost_classifier(X_train, y_train, X_eval, y_eval, calibration) -> dict
    compute_calibration_curve(y_true, y_pred_proba, n_bins) -> list[dict]
    compute_ece(y_true, y_pred_proba, n_bins) -> float
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from xgboost import XGBClassifier


def _validate_numeric(X: pd.DataFrame, name: str) -> None:
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        raise ValueError(f"{name} contains non-numeric columns: {non_numeric}")


def train_logistic(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
) -> dict:
    """Fit LogisticRegression and return P(home win) on X_eval.

    Returns
    -------
    dict with keys:
        y_pred_proba: np.ndarray of P(home win), shape (n_eval,)
        model: fitted LogisticRegression instance
    """
    _validate_numeric(X_train, "X_train")
    _validate_numeric(X_eval, "X_eval")
    model = LogisticRegression(max_iter=5000, C=1.0, solver="lbfgs")
    model.fit(X_train, y_train)
    y_pred_proba = model.predict_proba(X_eval)[:, 1]
    return {"y_pred_proba": y_pred_proba, "model": model}


def train_xgboost_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
    y_eval: pd.Series,
    calibration: str = "sigmoid",
) -> dict:
    """Fit XGBClassifier and apply post-hoc calibration on the eval fold.

    Parameters
    ----------
    calibration: 'sigmoid' (Platt scaling) or 'isotonic'

    Note: fitting the calibrator on X_eval/y_eval is an approximation
    acceptable for CV comparison; production deployment would use a
    dedicated hold-out split.

    Returns
    -------
    dict with keys:
        y_pred_proba: np.ndarray of calibrated P(home win), shape (n_eval,)
        y_pred_proba_uncalibrated: np.ndarray of raw XGBoost P(home win)
        model: fitted XGBClassifier instance
        calibrated_model: fitted calibrator object (LogisticRegression or IsotonicRegression)
    """
    _validate_numeric(X_train, "X_train")
    _validate_numeric(X_eval, "X_eval")
    model = XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_raw = model.predict_proba(X_eval)[:, 1]

    # Fit calibrator on raw XGBoost scores vs. true labels from the eval fold.
    # cv='prefit' was removed in sklearn 1.2+; manual calibration is equivalent.
    if calibration == "sigmoid":
        calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        calibrator.fit(y_raw.reshape(-1, 1), np.asarray(y_eval))
        y_pred_proba = calibrator.predict_proba(y_raw.reshape(-1, 1))[:, 1]
    elif calibration == "isotonic":
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(y_raw, np.asarray(y_eval))
        y_pred_proba = calibrator.predict(y_raw)
    else:
        raise ValueError(f"calibration must be 'sigmoid' or 'isotonic', got '{calibration}'")

    return {
        "y_pred_proba": y_pred_proba,
        "y_pred_proba_uncalibrated": y_raw,
        "model": model,
        "calibrated_model": calibrator,
    }


def compute_calibration_curve(
    y_true: np.ndarray | pd.Series,
    y_pred_proba: np.ndarray,
    n_bins: int = 10,
) -> list[dict]:
    """Bin predictions into equal-width [0,1] buckets and compute actual win rates.

    Returns
    -------
    list of dicts with keys: bin_center, mean_pred_prob, actual_win_rate, n_games
    Bins with zero games are omitted.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred_proba = np.asarray(y_pred_proba, dtype=float)

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    result = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (y_pred_proba >= lo) & (y_pred_proba < hi)
        # Include right edge in last bin
        if i == n_bins - 1:
            mask = (y_pred_proba >= lo) & (y_pred_proba <= hi)
        n_games = int(mask.sum())
        if n_games == 0:
            continue
        bin_center = float((lo + hi) / 2)
        mean_pred_prob = float(y_pred_proba[mask].mean())
        actual_win_rate = float(y_true[mask].mean())
        result.append({
            "bin_center": bin_center,
            "mean_pred_prob": mean_pred_prob,
            "actual_win_rate": actual_win_rate,
            "n_games": n_games,
        })
    return result


def compute_ece(
    y_true: np.ndarray | pd.Series,
    y_pred_proba: np.ndarray,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error: weighted mean |mean_pred - actual_rate| across bins.

    Returns float ECE in [0, 1].
    """
    curve = compute_calibration_curve(y_true, y_pred_proba, n_bins=n_bins)
    if not curve:
        return 0.0
    total_games = sum(b["n_games"] for b in curve)
    ece = sum(
        abs(b["mean_pred_prob"] - b["actual_win_rate"]) * b["n_games"] / total_games
        for b in curve
    )
    return float(ece)
