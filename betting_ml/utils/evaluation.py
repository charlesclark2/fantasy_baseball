"""Card 4.9 — Evaluation utilities for regression and probabilistic predictions.

Public API:
    fold_metrics(y_true, y_pred) -> dict
    brier_score_over_under(y_true_runs, p_over, total_line) -> float
    calibration_table(y_true_runs, p_over, total_line, n_bins) -> pd.DataFrame
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def fold_metrics(
    y_true: np.ndarray | pd.Series,
    y_pred: np.ndarray | pd.Series,
) -> dict:
    """Compute MAE and RMSE for a single fold.

    Returns {'mae': float, 'rmse': float}. Returns NaN values for empty inputs.
    Raises ValueError for mismatched lengths.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"y_true and y_pred must have the same shape, "
            f"got {y_true.shape} and {y_pred.shape}"
        )

    if len(y_true) == 0:
        return {"mae": float("nan"), "rmse": float("nan")}

    errors = y_true - y_pred
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors ** 2)))
    return {"mae": mae, "rmse": rmse}


def brier_score_over_under(
    y_true_runs: np.ndarray | pd.Series,
    p_over: np.ndarray | pd.Series,
    total_line: float | np.ndarray,
) -> float:
    """Binary Brier score for the over/under bet.

    outcome = 1 if actual runs > total_line, else 0.
    Brier = mean((p_over - outcome)^2).

    Returns NaN for empty inputs. Raises ValueError for mismatched lengths.
    """
    y_true_runs = np.asarray(y_true_runs, dtype=float)
    p_over = np.asarray(p_over, dtype=float)

    if y_true_runs.shape != p_over.shape:
        raise ValueError(
            f"y_true_runs and p_over must have the same shape, "
            f"got {y_true_runs.shape} and {p_over.shape}"
        )

    if len(y_true_runs) == 0:
        return float("nan")

    outcome = (y_true_runs > total_line).astype(float)
    return float(np.mean((p_over - outcome) ** 2))


def calibration_table(
    y_true_runs: np.ndarray | pd.Series,
    p_over: np.ndarray | pd.Series,
    total_line: float | np.ndarray,
    n_bins: int = 10,
) -> pd.DataFrame:
    """Bin games by predicted P(over) and compute calibration statistics.

    Parameters
    ----------
    n_bins: number of equal-width bins across [0, 1]

    Returns
    -------
    DataFrame with columns: bin_center, mean_p_over, actual_over_rate, n_games.
    Bins with zero games are excluded.
    """
    y_true_runs = np.asarray(y_true_runs, dtype=float)
    p_over = np.asarray(p_over, dtype=float)
    outcome = (y_true_runs > total_line).astype(float)

    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    rows = []
    for i, center in enumerate(bin_centers):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        # Include right edge in the last bin
        if i < n_bins - 1:
            mask = (p_over >= lo) & (p_over < hi)
        else:
            mask = (p_over >= lo) & (p_over <= hi)
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append(
            {
                "bin_center": float(center),
                "mean_p_over": float(p_over[mask].mean()),
                "actual_over_rate": float(outcome[mask].mean()),
                "n_games": n,
            }
        )

    return pd.DataFrame(rows, columns=["bin_center", "mean_p_over", "actual_over_rate", "n_games"])
