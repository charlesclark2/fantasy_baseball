"""Card 4.9 — Training functions for total runs regression baselines.

Public API:
    train_ridge(X_train, y_train, X_eval) -> dict
    train_xgboost(X_train, y_train, X_eval) -> dict
    train_ngboost(X_train, y_train, X_eval, dist) -> dict
    p_over_line(dist_name, dist_params, total_line) -> np.ndarray
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor
from ngboost import NGBRegressor
from ngboost.distns import Normal, LogNormal


def _validate_numeric(X: pd.DataFrame, name: str) -> None:
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        raise ValueError(f"{name} contains non-numeric columns: {non_numeric}")


def train_ridge(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
) -> dict:
    """Fit Ridge regression and return point predictions on X_eval.

    Returns
    -------
    dict with keys:
        y_pred: np.ndarray, shape (n_eval,)
        model: fitted Ridge instance
    """
    _validate_numeric(X_train, "X_train")
    _validate_numeric(X_eval, "X_eval")
    model = Ridge(alpha=1.0)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_eval)
    return {"y_pred": y_pred, "model": model}


def train_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
) -> dict:
    """Fit XGBRegressor and return point predictions on X_eval.

    Returns
    -------
    dict with keys:
        y_pred: np.ndarray, shape (n_eval,)
        model: fitted XGBRegressor instance
    """
    _validate_numeric(X_train, "X_train")
    _validate_numeric(X_eval, "X_eval")
    model = XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        tree_method="hist",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_eval)
    return {"y_pred": y_pred, "model": model}


def train_ngboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_eval: pd.DataFrame,
    dist: str = "Normal",
) -> dict:
    """Fit NGBRegressor with Normal or LogNormal distribution.

    Parameters
    ----------
    dist: "Normal" or "LogNormal"

    Returns
    -------
    dict with keys:
        y_pred: np.ndarray, shape (n_eval,) — predicted mean
        dist_params: dict with 'loc' and 'scale' arrays (n_eval,)
            Normal: loc=predicted mean, scale=predicted std
            LogNormal: loc=log-mean (mu), scale=log-std (sigma)
        model: fitted NGBRegressor instance
    """
    _validate_numeric(X_train, "X_train")
    _validate_numeric(X_eval, "X_eval")

    dist_class = Normal if dist == "Normal" else LogNormal
    model = NGBRegressor(
        Dist=dist_class,
        n_estimators=300,
        learning_rate=0.1,
        random_state=42,
        verbose=False,
    )
    model.fit(X_train.values, y_train.values)

    pred_dist = model.pred_dist(X_eval.values)

    if dist == "Normal":
        loc = pred_dist.params["loc"]
        scale = pred_dist.params["scale"]
        y_pred = loc.copy()
    else:
        # scipy lognorm convention: s=sigma (log-std), scale=exp(mu)
        # Map to our convention: loc=log-mean, scale=log-std
        if "s" in pred_dist.params:
            sigma = pred_dist.params["s"]
            mu = np.log(pred_dist.params["scale"])
        else:
            # Fallback for alternative parameter naming
            mu = pred_dist.params.get("mu", pred_dist.params.get("loc", np.zeros(len(X_eval))))
            sigma = pred_dist.params.get("sigma", pred_dist.params.get("scale", np.ones(len(X_eval))))
        loc = mu
        scale = sigma
        y_pred = np.exp(mu + 0.5 * sigma ** 2)

    return {
        "y_pred": y_pred,
        "dist_params": {"loc": np.asarray(loc), "scale": np.asarray(scale)},
        "model": model,
    }


def p_over_line(
    dist_name: str,
    dist_params: dict,
    total_line: float | np.ndarray,
) -> np.ndarray:
    """P(total_runs > total_line) for each game under the given distribution.

    Parameters
    ----------
    dist_name: "Normal" or "LogNormal"
    dist_params: dict with 'loc' and 'scale' arrays
        Normal: loc=mean, scale=std
        LogNormal: loc=log-mean, scale=log-std
    total_line: scalar or per-game array

    Returns
    -------
    np.ndarray of probabilities in [0, 1], shape (n,)
    """
    loc = dist_params["loc"]
    scale = dist_params["scale"]

    if dist_name == "Normal":
        return stats.norm.sf(total_line, loc=loc, scale=scale)
    elif dist_name == "LogNormal":
        # scipy lognorm: sf(x, s=sigma, scale=exp(mu))
        return stats.lognorm.sf(total_line, s=scale, scale=np.exp(loc))
    else:
        raise ValueError(f"Unknown dist_name '{dist_name}'. Expected 'Normal' or 'LogNormal'.")
