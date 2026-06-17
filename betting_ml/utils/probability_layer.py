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

# ---------------------------------------------------------------------------
# VAE OOD gate — Story 19.6
# ---------------------------------------------------------------------------
# Lazy-loaded; None until the artifact is present on disk.
_vae_model: "Any" = None  # betting_ml.models.vae_ood.signal_vae.SignalVAE | None


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
    """Raw model-vs-market diagnostic: positive means the model disagrees upward
    with the market. NOTE: this ignores alpha, so it is NOT safe to size bets off
    directly — use compute_actionable_edge for anything that drives a pick. Kept as
    a calibration/CLV diagnostic and for Layer-4 selective-strategy magnitudes."""
    return model_prob - market_prob


def compute_actionable_edge(model_prob: float, market_prob: float, alpha: float) -> float:
    """Alpha-aware betting edge: posterior(model, market, alpha) − market.

    A2.5 edge-artifact guard. Unlike compute_edge (raw model-vs-market gap), this
    inherits the alpha blend, so the alpha tuner's skill judgment flows straight
    through to the displayed/stored edge and any Kelly sized off it:

        alpha=1.0 → posterior=model      → edge = model − market (full conviction)
        alpha=0.0 → posterior=market     → edge ≈ 0              (no skill → no edge)

    This is the correct quantity to bet on: a non-zero (calibrated − market) gap on
    a model the tuner has set alpha=0 for is the calibrated flat-probability artifact,
    not real value. Sizing bets off this prevents surfacing phantom edges (e.g. the
    "bet every home underdog" pattern when the model collapses to a near-constant)."""
    return compute_posterior(model_prob, market_prob, alpha) - market_prob


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
_VAE_ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "betting_ml" / "models" / "vae_ood" / "signal_vae.joblib"

# Bullpen OOD gate — training distribution parameters fitted on 2022-2025 data.
# Source: betting_ml/models/bayesian/signal_scalers.joblib → 'opp_bullpen_mu' scaler.
# These are fixed and must not be recomputed from live data.
# Updated 2026-06-05 (Story 17.0-retune): bullpen_v2 retrained on 2021-2026 window;
# scaler refit on new 2022-2025 signal rows. 2026 mean z=+0.30 (was +0.34).
_BULLPEN_OOD_TRAINING_MEAN  = 2.145507   # mean(bullpen_mu across 2022-2025 opp sides)
_BULLPEN_OOD_TRAINING_STD   = 0.684726   # std(bullpen_mu across 2022-2025 opp sides)
_BULLPEN_OOD_THRESHOLD_SIGMA = 1.5       # |z| > 1.5 → OOD flag; blocks totals bets

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


def _eval_uncertainty_below_threshold(row: dict, threshold: float = 0.25) -> float:
    """Criterion 3: edge_to_sigma above threshold (Story 22.4).

    Returns a continuous strength in [0, 1]:
        0.0 if edge_to_sigma < threshold  (wide posterior → abstain)
        scales linearly from 0.01 → 1.0 over [threshold, 2*threshold]

    Requires prediction_row to contain 'totals_ci_width'/'h2h_ci_width' plus the
    corresponding edge key (populated by predict_today.py via sigma_gate.evaluate_sigma_gate).
    Falls back to 0.0 if CI widths are absent — the gate does not fire on missing data.

    threshold: minimum edge_to_sigma to qualify. Set via the registry's
        uncertainty_below_threshold.threshold field; use the value from
        sigma_gate_backtest_22_4.py results. Default 0.25 is preliminary.
    """
    try:
        from betting_ml.utils.sigma_gate import compute_edge_to_sigma
    except ImportError:
        return 0.0

    if threshold is None or threshold <= 0:
        threshold = 0.25

    # Use the higher edge_to_sigma across totals and H2H (best available signal)
    candidates: list[float] = []
    for ci_key, edge_key in (("totals_ci_width", "totals_edge"),
                              ("h2h_ci_width",    "h2h_edge")):
        ci   = row.get(ci_key)
        edge = row.get(edge_key)
        if ci is not None and edge is not None and float(ci) > 0:
            candidates.append(compute_edge_to_sigma(float(edge), float(ci)))

    if not candidates:
        return 0.0

    ets = max(candidates)

    if ets < threshold:
        return 0.0
    # Scale linearly 0.01 at threshold → 1.0 at 2*threshold
    return min(1.0, 0.01 + (ets - threshold) / max(threshold, 1e-6) * 0.99)


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


def _eval_bullpen_ood_gate(
    row: dict,
) -> tuple[float | None, float | None, bool]:
    """Compute bullpen OOD z-scores and flag for home and away teams.

    Returns (z_home, z_away, is_ood) where is_ood=True when either team's
    bullpen_mu deviates > _BULLPEN_OOD_THRESHOLD_SIGMA from the 2022-2025
    training distribution. Returns (None, None, False) when signals are absent.

    Args:
        row: prediction_row with optional keys bullpen_mu_home, bullpen_mu_away.

    Returns:
        (bullpen_z_score_home, bullpen_z_score_away, bullpen_signal_ood)
    """
    mu_home = row.get("bullpen_mu_home")
    mu_away = row.get("bullpen_mu_away")

    if mu_home is None and mu_away is None:
        return None, None, False

    def _z(mu: float | None) -> float | None:
        if mu is None:
            return None
        return (float(mu) - _BULLPEN_OOD_TRAINING_MEAN) / _BULLPEN_OOD_TRAINING_STD

    z_home = _z(mu_home)
    z_away = _z(mu_away)

    is_ood = (z_home is not None and abs(z_home) > _BULLPEN_OOD_THRESHOLD_SIGMA) or \
             (z_away is not None and abs(z_away) > _BULLPEN_OOD_THRESHOLD_SIGMA)

    return z_home, z_away, is_ood


def _eval_signal_combination_ood(row: dict) -> bool:
    """VAE joint OOD gate (Story 19.6).

    Loads the fitted SignalVAE from disk (lazy, cached), builds the 13-column
    mu vector from prediction_row, and returns True when the reconstruction
    error exceeds the training-era 95th-percentile threshold.

    Graceful degradation:
      - Artifact missing → False (no OOD signal; gate does not block)
      - All 13 columns absent from row → False (cannot evaluate)
      - VAE not enabled in bet_gate config → caller skips this function

    Args:
        row: prediction_row dict (same object passed to compute_bet_permission).

    Returns:
        True if the game is jointly OOD (bets should be blocked).
    """
    global _vae_model

    if not _VAE_ARTIFACT_PATH.exists():
        return False

    # Lazy load
    if _vae_model is None:
        try:
            from betting_ml.models.vae_ood.signal_vae import SIGNAL_MU_COLUMNS, SignalVAE
            _vae_model = SignalVAE.load(_VAE_ARTIFACT_PATH)
            logger.debug("SignalVAE artifact loaded from %s", _VAE_ARTIFACT_PATH)
        except Exception as exc:
            logger.warning("Failed to load SignalVAE artifact: %s — OOD gate skipped.", exc)
            return False

    try:
        from betting_ml.models.vae_ood.signal_vae import SIGNAL_MU_COLUMNS
        import numpy as np

        vec = np.array(
            [float(row[c]) if row.get(c) is not None else float("nan")
             for c in SIGNAL_MU_COLUMNS],
            dtype=np.float64,
        ).reshape(1, -1)

        # NaN columns are imputed inside SignalVAE.predict_ood with training means.
        # All-NaN rows reconstruct near the training mean → low recon error → not OOD.
        # This is the correct graceful degradation: absent signals ≠ OOD.
        _, is_ood = _vae_model.predict_ood(vec)
        return bool(is_ood[0])
    except Exception as exc:
        logger.warning("SignalVAE OOD evaluation failed (%s) — gate skipped.", exc)
        return False


def compute_bet_permission(
    game_pk: str,
    prediction_row: dict[str, Any],
    gate_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate whether a game qualifies as an approved bet.

    Each criterion returns a continuous strength in [0, 1]. A criterion is
    considered "fired" (counts toward gate_signals_met) when its strength > 0.
    game_conviction_score is the equal-weighted mean across all five criteria.

    Bullpen OOD gate (Epic 19 / Story 17.1b): if either team's bullpen_mu deviates
    > 1.5σ from the 2022-2025 training distribution, qualified_bet is forced False
    regardless of criterion votes. This is a hard veto, not a criterion vote — it
    fires when the bullpen signal is outside the model's reliable operating range.
    Requires prediction_row to contain bullpen_mu_home and bullpen_mu_away.

    VAE holistic OOD gate (Story 19.6): if the joint 13-column signal vector has a
    VAE reconstruction error above the training-era 95th-percentile threshold,
    qualified_bet is also forced False.  Activates only when the SignalVAE artifact
    is present on disk AND signal_combination_ood is enabled in the registry config.
    Catches combination drift invisible to the per-signal marginal z gate.

    Args:
        game_pk: Game identifier (used for logging only).
        prediction_row: Dict of scored fields from predict_today.py (pred_total_runs,
            total_line_consensus, bullpen_mu_home, bullpen_mu_away, and the 13 VAE
            mu columns, etc.). Missing fields are treated as criterion=False / OOD
            gate absent.
        gate_config: Optional override for gate thresholds and min_criteria_met.
            If None, loaded from sub_model_registry.yaml bet_gate block.

    Returns:
        {
            "qualified_bet": bool,          # gate_signals_met >= min_criteria_met AND NOT any OOD veto
            "gate_signals_met": int,        # 0–5
            "game_conviction_score": float, # 0.0–1.0 (equal-weighted mean strength)
            "gate_detail": {
                "offensive_signal_qualifies": bool,
                "run_env_supports": bool,
                "uncertainty_below_threshold": bool,
                "market_disagreement_visible": bool,
                "prior_fresh": bool,
            },
            "bullpen_z_score_home": float | None,
            "bullpen_z_score_away": float | None,
            "bullpen_signal_ood": bool,
            "signal_combination_ood": bool,  # VAE holistic OOD veto (Story 19.6)
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
    if _cfg("uncertainty_below_threshold", "enabled", False):
        unc_threshold = _cfg("uncertainty_below_threshold", "threshold", 0.25)
        unc_threshold = float(unc_threshold) if unc_threshold is not None else 0.25
        strengths["uncertainty_below_threshold"] = _eval_uncertainty_below_threshold(
            prediction_row, threshold=unc_threshold
        )
    else:
        strengths["uncertainty_below_threshold"] = 0.0
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

    # Bullpen OOD gate — hard veto regardless of criterion votes (Story 17.1b / Epic 19)
    bullpen_z_home, bullpen_z_away, bullpen_ood = _eval_bullpen_ood_gate(prediction_row)
    if bullpen_ood:
        qualified_bet = False

    # VAE holistic OOD gate — hard veto (Story 19.6)
    # Fires only when the artifact is on disk AND enabled in the registry.
    vae_ood_enabled = _cfg("signal_combination_ood", "enabled", False)
    signal_combination_ood = (
        _eval_signal_combination_ood(prediction_row) if vae_ood_enabled else False
    )
    if signal_combination_ood:
        qualified_bet = False

    logger.debug(
        "game_pk=%s gate_signals_met=%d/%d conviction=%.4f "
        "bullpen_ood=%s vae_ood=%s qualified=%s",
        game_pk, gate_signals_met, min_met, game_conviction_score,
        bullpen_ood, signal_combination_ood, qualified_bet,
    )

    return {
        "qualified_bet": qualified_bet,
        "gate_signals_met": gate_signals_met,
        "game_conviction_score": game_conviction_score,
        "gate_detail": gate_detail,
        "bullpen_z_score_home": round(bullpen_z_home, 4) if bullpen_z_home is not None else None,
        "bullpen_z_score_away": round(bullpen_z_away, 4) if bullpen_z_away is not None else None,
        "bullpen_signal_ood": bullpen_ood,
        "signal_combination_ood": signal_combination_ood,
    }
