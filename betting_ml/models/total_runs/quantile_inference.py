"""Card 8.P — Quantile interpolation inference for total_runs.

Converts five LightGBM quantile predictions (q=0.10, 0.25, 0.50, 0.75, 0.90)
into P(total_runs > market_line) via linear interpolation between the two
bracketing quantiles. Clamps output to [0.05, 0.95].
"""
from __future__ import annotations

import numpy as np

ALPHAS = [0.10, 0.25, 0.50, 0.75, 0.90]


def _interpolate_one(quantile_preds: list[float], alphas: list[float], line: float) -> float:
    pairs = sorted(zip(quantile_preds, alphas))
    preds = [p for p, _ in pairs]
    alp   = [a for _, a in pairs]

    if line <= preds[0]:
        return 0.95
    if line >= preds[-1]:
        return 0.05

    for i in range(len(preds) - 1):
        if preds[i] <= line <= preds[i + 1]:
            frac = (line - preds[i]) / (preds[i + 1] - preds[i])
            prob_under = alp[i] + frac * (alp[i + 1] - alp[i])
            return float(max(0.05, min(0.95, 1.0 - prob_under)))

    return 0.50


def predict_prob_over_line(
    models: dict[float, object],
    X: np.ndarray,
    market_line: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray]:
    """P(total_runs > market_line) for each game using quantile interpolation.

    Parameters
    ----------
    models:
        Dict mapping alpha (float) to a fitted LGBMRegressor.
    X:
        Feature matrix of shape (n_games, n_features).
    market_line:
        Scalar or array of shape (n_games,).

    Returns
    -------
    prob_over, prob_under: arrays of shape (n_games,), clamped to [0.05, 0.95],
        summing to exactly 1.0 per game.
    """
    n = X.shape[0]
    alphas = sorted(models.keys())
    quantile_preds = {a: models[a].predict(X) for a in alphas}

    line_arr = np.broadcast_to(np.asarray(market_line, dtype=float), (n,)).copy()

    prob_over = np.empty(n, dtype=float)
    for i in range(n):
        preds_i = [quantile_preds[a][i] for a in alphas]
        prob_over[i] = _interpolate_one(preds_i, alphas, float(line_arr[i]))

    prob_under = 1.0 - prob_over
    return prob_over, prob_under
