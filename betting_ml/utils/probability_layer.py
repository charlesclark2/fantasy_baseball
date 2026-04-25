"""Card 4.13 — Bayesian probability layer utilities.

Public API:
    vig_adjust(home_price, away_price, odds_format) -> tuple[float, float]
    log_odds(p) -> float
    sigmoid(x) -> float
    compute_posterior(model_prob, market_prob, alpha) -> float
    compute_edge(model_prob, market_prob) -> float
    compute_kelly(edge, market_implied_prob) -> float
    tune_alpha(model_probs, market_probs, outcomes, alpha_grid) -> tuple[float, list[dict]]
"""

from __future__ import annotations

import logging
import math

import numpy as np
from sklearn.metrics import log_loss as sklearn_log_loss

logger = logging.getLogger(__name__)


def vig_adjust(
    home_price: float,
    away_price: float,
    odds_format: str = "american",
) -> tuple[float, float]:
    """Remove bookmaker vig and return fair-value (home_prob, away_prob).

    For American odds:
        Positive (e.g. +150): decimal = odds/100 + 1; implied = 1/decimal
        Negative (e.g. -120): decimal = 100/abs(odds) + 1; implied = 1/decimal
    For decimal odds:
        implied = 1/price directly

    Vig removal: total = home_implied + away_implied
        home_prob = home_implied / total
        away_prob = away_implied / total
    """
    if odds_format == "american":
        home_decimal = (home_price / 100 + 1) if home_price > 0 else (100 / abs(home_price) + 1)
        away_decimal = (away_price / 100 + 1) if away_price > 0 else (100 / abs(away_price) + 1)
        home_implied = 1.0 / home_decimal
        away_implied = 1.0 / away_decimal
    elif odds_format == "decimal":
        home_implied = 1.0 / home_price
        away_implied = 1.0 / away_price
    else:
        raise ValueError(f"Unknown odds_format '{odds_format}'. Expected 'american' or 'decimal'.")

    total = home_implied + away_implied
    if total <= 0:
        raise ValueError(f"Implied probability total must be > 0, got {total}")

    return home_implied / total, away_implied / total


def log_odds(p: float) -> float:
    """Compute log-odds of probability p, clipped to avoid infinities."""
    p_clipped = float(np.clip(p, 1e-9, 1 - 1e-9))
    return math.log(p_clipped / (1 - p_clipped))


def sigmoid(x: float) -> float:
    """Logistic sigmoid function."""
    return 1.0 / (1.0 + math.exp(-x))


def compute_posterior(model_prob: float, market_prob: float, alpha: float) -> float:
    """Bayesian log-odds blend of model and market probability.

    log_odds_post = alpha * log_odds(model_prob) + (1 - alpha) * log_odds(market_prob)
    posterior = sigmoid(log_odds_post)

    alpha=1.0 → posterior equals model_prob
    alpha=0.0 → posterior equals market_prob
    """
    if not (0.0 <= alpha <= 1.0):
        raise ValueError(f"alpha must be in [0, 1], got {alpha}")
    log_odds_post = alpha * log_odds(model_prob) + (1 - alpha) * log_odds(market_prob)
    return sigmoid(log_odds_post)


def compute_edge(model_prob: float, market_prob: float) -> float:
    """Edge signal: positive means model sees value over market."""
    return model_prob - market_prob


def compute_kelly(edge: float, market_implied_prob: float) -> float:
    """Simplified Kelly fraction: edge * market_implied_prob.

    Derived from: edge / decimal_odds where decimal_odds = 1 / market_implied_prob.
    """
    if market_implied_prob <= 0:
        raise ValueError(f"market_implied_prob must be > 0, got {market_implied_prob}")
    return edge * market_implied_prob


def tune_alpha(
    model_probs: np.ndarray,
    market_probs: np.ndarray,
    outcomes: np.ndarray,
    alpha_grid: np.ndarray | None = None,
) -> tuple[float, list[dict]]:
    """Grid-search α that minimizes log-loss of posterior vs. actual outcome.

    Returns (best_alpha, [{'alpha': float, 'log_loss': float}, ...]).
    Falls back to alpha=0.5 with a warning if fewer than 100 games are available.
    """
    if alpha_grid is None:
        alpha_grid = np.round(np.arange(0.0, 1.01, 0.1), 2)

    model_probs = np.asarray(model_probs, dtype=float)
    market_probs = np.asarray(market_probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)

    results: list[dict] = []

    if len(model_probs) < 100:
        logger.warning(
            "Only %d games available for α tuning (expected several thousand with "
            "historical odds backfill). Defaulting to α=0.5.",
            len(model_probs),
        )
        for a in alpha_grid:
            posteriors = np.array([compute_posterior(mp, mk, float(a)) for mp, mk in zip(model_probs, market_probs)])
            posteriors_clipped = np.clip(posteriors, 1e-7, 1 - 1e-7)
            ll = sklearn_log_loss(outcomes, posteriors_clipped)
            results.append({"alpha": float(a), "log_loss": ll})
        return 0.5, results

    for a in alpha_grid:
        posteriors = np.array([
            compute_posterior(float(mp), float(mk), float(a))
            for mp, mk in zip(model_probs, market_probs)
        ])
        posteriors_clipped = np.clip(posteriors, 1e-7, 1 - 1e-7)
        ll = sklearn_log_loss(outcomes, posteriors_clipped)
        results.append({"alpha": float(a), "log_loss": ll})

    best = min(results, key=lambda r: r["log_loss"])
    return best["alpha"], results
