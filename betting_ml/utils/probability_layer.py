"""Card 4.13 — Bayesian probability layer utilities.

Public API:
    vig_adjust(home_price, away_price, odds_format) -> tuple[float, float]
    log_odds(p) -> float
    sigmoid(x) -> float
    compute_posterior(model_prob, market_prob, alpha) -> float
    compute_edge(model_prob, market_prob) -> float
    compute_kelly(edge, market_implied_prob) -> float
    tune_alpha(model_probs, market_probs, outcomes, alpha_grid) -> tuple[float, list[dict]]
    compute_bet_permission(game_pk, prediction_row, gate_config) -> dict
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml
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


# ---------------------------------------------------------------------------
# Bet Permission Gate — Story 19.2
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "betting_ml" / "sub_model_registry.yaml"

_DEFAULT_GATE_CONFIG: dict[str, Any] = {
    "min_criteria_met": 3,
    "criteria": {
        "offensive_signal_qualifies": {"threshold": 0.5, "enabled": True},
        "run_env_supports":           {"threshold": None, "enabled": False},
        "uncertainty_below_threshold": {"threshold": None, "enabled": False},
        "market_disagreement_visible": {"threshold": None, "enabled": False},
        "prior_fresh":                {"threshold": 7,    "enabled": False},
    },
}

_CRITERIA_ORDER = [
    "offensive_signal_qualifies",
    "run_env_supports",
    "uncertainty_below_threshold",
    "market_disagreement_visible",
    "prior_fresh",
]


def _load_gate_config() -> dict[str, Any]:
    try:
        registry = yaml.safe_load(_REGISTRY_PATH.read_text()) or {}
        gate = registry.get("bet_gate")
        if gate:
            return gate
    except Exception as exc:
        logger.warning("Could not load bet_gate config from registry (%s); using defaults.", exc)
    return _DEFAULT_GATE_CONFIG


def _eval_offensive_signal(row: dict, threshold: float) -> float:
    """Criterion 1: |pred_total_runs − total_line_consensus| ≥ threshold.

    Returns a continuous strength value in [0, 1]:
        0.0 if disagreement < threshold
        scales linearly from 0→1 over [threshold, threshold + 1.5 runs]
    """
    pred = row.get("pred_total_runs")
    line = row.get("total_line_consensus")
    if pred is None or line is None:
        return 0.0
    try:
        disagreement = abs(float(pred) - float(line))
    except (TypeError, ValueError):
        return 0.0
    if disagreement < threshold:
        return 0.0
    # Linearly scale from 0.01 (at threshold) to 1.0 (at threshold + 1.5 runs).
    # Floor of 0.01 ensures strength > 0 when disagreement == threshold, so the
    # criterion fires at the boundary (gate_detail = True).
    return min(1.0, 0.01 + (disagreement - threshold) / 1.5 * 0.99)


def _eval_run_env_supports(row: dict) -> float:
    """Criterion 2: run_env_v4 directionally supports the offensive call.

    Not yet wired — depends on Epic 9 integrating run_env sub-model signal
    into inference output. Returns 0.0 until enabled.
    """
    # Future: check row.get("run_env_signal") vs. direction of pred_total_runs vs. line
    return 0.0


def _eval_uncertainty_below_threshold(row: dict) -> float:
    """Criterion 3: game_uncertainty_score below threshold (Epic 9.F1).

    Not yet wired — returns 0.0 until game_uncertainty_score is in prediction_row.
    """
    # Future: score = 1.0 - clip(game_uncertainty_score / threshold, 0, 1)
    return 0.0


def _eval_market_disagreement(row: dict) -> float:
    """Criterion 4: sharp-money alignment visible in mart_game_odds_bridge (Epic 12).

    Not yet wired — returns 0.0 until market disagreement signal is available.
    """
    return 0.0


def _eval_prior_fresh(row: dict, threshold_days: int) -> float:
    """Criterion 5: prior_age_days ≤ threshold for key players (post-10M EB tracking).

    Returns 0.0 if prior_age_days is absent (field not yet in prediction_row).
    Returns 1.0 if prior_age_days ≤ threshold; 0.0 if > threshold (hard gate).
    """
    age = row.get("prior_age_days")
    if age is None:
        return 0.0
    try:
        return 1.0 if float(age) <= threshold_days else 0.0
    except (TypeError, ValueError):
        return 0.0


def compute_bet_permission(
    game_pk: str,
    prediction_row: dict[str, Any],
    gate_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate whether a game qualifies as an approved bet.

    Each criterion returns a continuous strength in [0, 1]. A criterion is
    considered "fired" (counts toward gate_signals_met) when its strength > 0.
    game_conviction_score is the equal-weighted mean across all five criteria.

    Args:
        game_pk: Game identifier (used for logging only).
        prediction_row: Dict of scored fields from predict_today.py (pred_total_runs,
            total_line_consensus, etc.). Missing fields are treated as criterion=False.
        gate_config: Optional override for gate thresholds and min_criteria_met.
            If None, loaded from sub_model_registry.yaml bet_gate block.

    Returns:
        {
            "qualified_bet": bool,          # gate_signals_met >= min_criteria_met
            "gate_signals_met": int,        # 0–5
            "game_conviction_score": float, # 0.0–1.0 (equal-weighted mean strength)
            "gate_detail": {
                "offensive_signal_qualifies": bool,
                "run_env_supports": bool,
                "uncertainty_below_threshold": bool,
                "market_disagreement_visible": bool,
                "prior_fresh": bool,
            },
        }
    """
    if gate_config is None:
        gate_config = _load_gate_config()

    criteria_cfg = gate_config.get("criteria", _DEFAULT_GATE_CONFIG["criteria"])
    min_met = int(gate_config.get("min_criteria_met", 3))

    def _cfg(name: str, key: str, default: Any) -> Any:
        return criteria_cfg.get(name, {}).get(key, default)

    strengths: dict[str, float] = {}

    # Criterion 1 — always evaluated; enabled flag respected
    if _cfg("offensive_signal_qualifies", "enabled", True):
        threshold = float(_cfg("offensive_signal_qualifies", "threshold", 0.5))
        strengths["offensive_signal_qualifies"] = _eval_offensive_signal(prediction_row, threshold)
    else:
        strengths["offensive_signal_qualifies"] = 0.0

    # Criteria 2–5 — disabled until upstream signals ship
    strengths["run_env_supports"] = (
        _eval_run_env_supports(prediction_row)
        if _cfg("run_env_supports", "enabled", False) else 0.0
    )
    strengths["uncertainty_below_threshold"] = (
        _eval_uncertainty_below_threshold(prediction_row)
        if _cfg("uncertainty_below_threshold", "enabled", False) else 0.0
    )
    strengths["market_disagreement_visible"] = (
        _eval_market_disagreement(prediction_row)
        if _cfg("market_disagreement_visible", "enabled", False) else 0.0
    )
    threshold_days = int(_cfg("prior_fresh", "threshold", 7) or 7)
    strengths["prior_fresh"] = (
        _eval_prior_fresh(prediction_row, threshold_days)
        if _cfg("prior_fresh", "enabled", False) else 0.0
    )

    gate_detail = {k: strengths[k] > 0.0 for k in _CRITERIA_ORDER}
    gate_signals_met = sum(1 for v in gate_detail.values() if v)
    game_conviction_score = round(sum(strengths[k] for k in _CRITERIA_ORDER) / len(_CRITERIA_ORDER), 4)
    qualified_bet = gate_signals_met >= min_met

    logger.debug(
        "game_pk=%s gate_signals_met=%d/%d conviction=%.4f qualified=%s",
        game_pk, gate_signals_met, min_met, game_conviction_score, qualified_bet,
    )

    return {
        "qualified_bet": qualified_bet,
        "gate_signals_met": gate_signals_met,
        "game_conviction_score": game_conviction_score,
        "gate_detail": gate_detail,
    }
