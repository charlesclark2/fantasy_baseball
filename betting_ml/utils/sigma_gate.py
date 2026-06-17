"""sigma_gate.py — Story 22.4: uncertainty-aware bet selection & σ-scaled sizing.

Utilities for computing per-game predictive-interval widths, the edge_to_sigma ratio,
sigma tier assignment, and sigma-scaled Kelly fractions. All logic is pure Python /
NumPy (no Snowflake, no model loading) so it runs in the serve path and in backtests.

Public API:
    compute_totals_ci_width(pred_total_runs, pred_total_runs_scale, total_line) -> float
    compute_h2h_ci_width(calibrated_win_prob, p_ngboost, p_clf) -> float
    compute_edge_to_sigma(edge, ci_width) -> float
    classify_sigma_tier(edge_to_sigma) -> str
    compute_sigma_scaled_kelly(base_kelly, ci_width, sigma_budget) -> float
    evaluate_sigma_gate(prediction_row) -> dict

CALIBRATION PREREQUISITE (Story 9.8, 2026-06-16):
    total_runs champion: cov80 0.808, calibrated ✓
    run_diff champion:   cov80 0.776, calibrated ✓
    home_win:            ECE 0.040, served path is identity (A2.9), calibrated ✓
    → All three targets are cleared to use as decision inputs.

TIERS (preliminary; update after sigma_gate_backtest_22_4.py reports optimal threshold):
    high_confidence  edge_to_sigma > HIGH_THRESHOLD   (1.50)
    medium           MED_THRESHOLD < ets ≤ HIGH_THRESHOLD (0.75–1.50)
    low              ABSTAIN_THRESHOLD < ets ≤ MED_THRESHOLD (0.25–0.75)
    abstain          ets ≤ ABSTAIN_THRESHOLD (0.25)

SIZING:
    sigma_scaled_kelly = base_kelly / (1 + SIGMA_PENALTY_K * ci_width)
    SIGMA_PENALTY_K default = 3.0 — a CI width of ~0.33 halves Kelly.
    Folds into 22.2 portfolio Kelly once that story ships.
"""
from __future__ import annotations

import math
import logging

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier thresholds (preliminary pre-backtest values; update after 22.4 backtest)
# ---------------------------------------------------------------------------
ABSTAIN_THRESHOLD: float = 0.25   # edge_to_sigma < this → abstain
MED_THRESHOLD:     float = 0.75
HIGH_THRESHOLD:    float = 1.50

# Default σ-Kelly penalty: halves Kelly at CI width = 1/SIGMA_PENALTY_K
SIGMA_PENALTY_K: float = 3.0

# Base σ floor for H2H: see win_prob_uncertainty.ensemble_sigma
_H2H_BASE_SIGMA: float = 0.03


# ---------------------------------------------------------------------------
# CI width computation
# ---------------------------------------------------------------------------

def compute_totals_ci_width(
    pred_total_runs: float,
    pred_total_runs_scale: float,
    total_line: float,
) -> float:
    """Probability-space 80% CI width for P(total > line).

    Treats pred_total_runs_scale as the predictive σ (Normal model). Propagates
    a ±1.28σ shift in the mean to probability space — i.e. the range of P(over)
    if the true mean were anywhere in the model's 80% PI:

        P_over(mu_shift) = 1 − Φ((line − mu_shift) / sigma)
        ci_width         = P_over(mu + 1.28σ) − P_over(mu − 1.28σ)

    This is the delta-method approximation: a narrow σ near the line → wide ci_width
    → low edge_to_sigma → abstain (the correct behaviour when the model is uncertain
    whether total lands above or below the line).

    Returns a value in (0, 1]; clamped to [1e-6, 1] for numerical safety.
    """
    from scipy.stats import norm as _norm

    mu    = float(pred_total_runs)
    sigma = float(pred_total_runs_scale)
    line  = float(total_line)

    if sigma <= 0 or not all(math.isfinite(x) for x in (mu, sigma, line)):
        return 1.0  # treat as maximally uncertain when inputs invalid

    p_hi = 1.0 - _norm.cdf((line - (mu + 1.28 * sigma)) / sigma)
    p_lo = 1.0 - _norm.cdf((line - (mu - 1.28 * sigma)) / sigma)
    return float(np.clip(p_hi - p_lo, 1e-6, 1.0))


def compute_h2h_ci_width(
    calibrated_win_prob: float,
    p_ngboost: float,
    p_clf: float,
) -> float:
    """Probability-space 80% CI width for P(home win).

    Uses the Beta(α,β) credible interval from win_prob_uncertainty:
    the across-model σ (disagreement between NGBoost run-diff and XGB classifier,
    combined in quadrature with a 0.03 irreducible floor) drives the Beta concentration.
    Mirrors exactly what predict_today.py computes via compute_win_prob_beta.

    Returns ci_high − ci_low in probability units; clamped to [1e-6, 1].
    """
    try:
        from betting_ml.utils.win_prob_uncertainty import compute_win_prob_beta
        result = compute_win_prob_beta(calibrated_win_prob, [p_ngboost, p_clf])
        if result is None:
            return 1.0  # treat as maximally uncertain when inputs invalid
        return float(np.clip(result["win_prob_ci_width"], 1e-6, 1.0))
    except Exception as exc:
        logger.debug("compute_h2h_ci_width fallback (%s)", exc)
        # Fallback: simple symmetric CI from across-model disagreement + base floor
        sigma = math.sqrt(((p_ngboost - p_clf) ** 2) / 2.0 + _H2H_BASE_SIGMA ** 2)
        p = float(calibrated_win_prob)
        p = min(max(p, 1e-6), 1 - 1e-6)
        if sigma <= 0:
            return 1.0
        from scipy.stats import beta as _beta
        concentration = p * (1 - p) / sigma ** 2 - 1.0
        concentration = min(max(concentration, 2.0), 1000.0)
        alpha_p, beta_p = p * concentration, (1 - p) * concentration
        return float(np.clip(
            _beta.ppf(0.90, alpha_p, beta_p) - _beta.ppf(0.10, alpha_p, beta_p), 1e-6, 1.0
        ))


# ---------------------------------------------------------------------------
# Edge-to-sigma ratio
# ---------------------------------------------------------------------------

def compute_edge_to_sigma(edge: float, ci_width: float) -> float:
    """edge_to_sigma = |edge| / ci_width.

    Both edge and ci_width are in probability units.
    High ratio → tight posterior relative to edge → high confidence → act.
    Low ratio  → wide posterior relative to edge → uncertain → abstain.

    Returns 0.0 when ci_width ≤ 0 (maximally uncertain).
    """
    if ci_width <= 0:
        return 0.0
    return float(abs(edge)) / float(ci_width)


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------

def classify_sigma_tier(edge_to_sigma: float) -> str:
    """Classify a game into a σ confidence tier.

    Preliminary thresholds (pre-backtest). Update ABSTAIN_THRESHOLD, MED_THRESHOLD,
    HIGH_THRESHOLD after running sigma_gate_backtest_22_4.py.

    Returns one of: 'high_confidence', 'medium', 'low', 'abstain'.
    """
    if edge_to_sigma > HIGH_THRESHOLD:
        return "high_confidence"
    if edge_to_sigma > MED_THRESHOLD:
        return "medium"
    if edge_to_sigma > ABSTAIN_THRESHOLD:
        return "low"
    return "abstain"


# ---------------------------------------------------------------------------
# σ-scaled Kelly
# ---------------------------------------------------------------------------

def compute_sigma_scaled_kelly(
    base_kelly: float,
    ci_width: float,
    sigma_penalty_k: float = SIGMA_PENALTY_K,
) -> float:
    """Down-weight Kelly fraction for high-uncertainty (wide-CI) legs.

    Formula: sigma_scaled_kelly = base_kelly / (1 + k * ci_width)

    At ci_width = 0   → full Kelly (no penalty).
    At ci_width = 1/k → half Kelly.
    At ci_width = 1.0 → Kelly / (1 + k).

    The penalty is applied before portfolio-level correlation scaling (22.2).
    When 22.2 ships, pass sigma_scaled_kelly as the input fraction to
    compute_portfolio_kelly instead of the raw Kelly.

    Args:
        base_kelly:      per-bet Kelly fraction (from probability_layer.compute_kelly).
        ci_width:        predictive-interval width in probability units (0–1).
        sigma_penalty_k: penalty steepness; default 3.0 (halves Kelly at ci_width≈0.33).

    Returns:
        Scaled Kelly fraction ≥ 0. Floored at 0 (never negative).
    """
    if base_kelly <= 0:
        return 0.0
    if ci_width <= 0:
        return float(base_kelly)
    scaled = float(base_kelly) / (1.0 + sigma_penalty_k * float(ci_width))
    return max(scaled, 0.0)


# ---------------------------------------------------------------------------
# Convenience: full gate evaluation from a prediction_row dict
# ---------------------------------------------------------------------------

def evaluate_sigma_gate(prediction_row: dict) -> dict:
    """Compute sigma gate fields from a prediction_row dict.

    Expects keys used by predict_today.py:
        pred_total_runs, pred_total_runs_scale, total_line_consensus (totals)
        calibrated_win_prob, p_home_win_ngboost, p_home_win_classifier (H2H)
        totals_edge, h2h_edge, totals_kelly_fraction, h2h_kelly_fraction

    Returns:
        {
          "totals_ci_width":          float | None,
          "h2h_ci_width":             float | None,
          "totals_edge_to_sigma":     float | None,
          "h2h_edge_to_sigma":        float | None,
          "sigma_tier":               str,   # joint tier from best available target
          "abstain_reason":           str,   # '' when not abstaining
          "totals_sigma_kelly":       float | None,
          "h2h_sigma_kelly":          float | None,
          "totals_p_over_ci_low":     float | None,
          "totals_p_over_ci_high":    float | None,
        }
    """
    # --- totals ---
    totals_ci_width = None
    totals_ets      = None
    tot_ci_lo       = None
    tot_ci_hi       = None

    pred_mu   = prediction_row.get("pred_total_runs")
    pred_sig  = prediction_row.get("pred_total_runs_scale")
    line      = prediction_row.get("total_line_consensus")
    tot_edge  = prediction_row.get("totals_edge")

    if all(v is not None for v in (pred_mu, pred_sig, line)):
        try:
            totals_ci_width = compute_totals_ci_width(
                float(pred_mu), float(pred_sig), float(line)
            )
            # CI bounds in probability space (for persist to daily_model_predictions)
            from scipy.stats import norm as _norm
            mu, sigma = float(pred_mu), float(pred_sig)
            ln = float(line)
            if sigma > 0:
                tot_ci_lo = float(1.0 - _norm.cdf((ln - (mu - 1.28 * sigma)) / sigma))
                tot_ci_hi = float(1.0 - _norm.cdf((ln - (mu + 1.28 * sigma)) / sigma))
            if tot_edge is not None:
                totals_ets = compute_edge_to_sigma(float(tot_edge), totals_ci_width)
        except Exception as exc:
            logger.debug("totals sigma gate error: %s", exc)

    # --- h2h ---
    h2h_ci_width = None
    h2h_ets      = None

    cal_p   = prediction_row.get("calibrated_win_prob")
    ngb_p   = prediction_row.get("p_home_win_ngboost")
    clf_p   = prediction_row.get("p_home_win_classifier")
    h2h_edge = prediction_row.get("h2h_edge")

    if all(v is not None for v in (cal_p, ngb_p, clf_p)):
        try:
            h2h_ci_width = compute_h2h_ci_width(
                float(cal_p), float(ngb_p), float(clf_p)
            )
            if h2h_edge is not None:
                h2h_ets = compute_edge_to_sigma(float(h2h_edge), h2h_ci_width)
        except Exception as exc:
            logger.debug("h2h sigma gate error: %s", exc)

    # --- tier: use whichever target the prediction is about; fall back to worst ---
    # Use the best available ets (highest signal quality for selection)
    available_ets = [v for v in (totals_ets, h2h_ets) if v is not None]
    best_ets = max(available_ets) if available_ets else 0.0

    tier = classify_sigma_tier(best_ets)
    abstain_reason = ""
    if tier == "abstain":
        if not available_ets:
            abstain_reason = "ci_width_unavailable"
        else:
            abstain_reason = f"edge_to_sigma={best_ets:.3f}<threshold={ABSTAIN_THRESHOLD}"

    # --- sigma-scaled Kelly ---
    tot_skel = None
    h2h_skel = None
    tot_kelly = prediction_row.get("totals_kelly_fraction")
    h2h_kelly = prediction_row.get("h2h_kelly_fraction")
    if tot_kelly is not None and totals_ci_width is not None:
        tot_skel = compute_sigma_scaled_kelly(float(tot_kelly), totals_ci_width)
    if h2h_kelly is not None and h2h_ci_width is not None:
        h2h_skel = compute_sigma_scaled_kelly(float(h2h_kelly), h2h_ci_width)

    return {
        "totals_ci_width":       totals_ci_width,
        "h2h_ci_width":          h2h_ci_width,
        "totals_edge_to_sigma":  totals_ets,
        "h2h_edge_to_sigma":     h2h_ets,
        "sigma_tier":            tier,
        "abstain_reason":        abstain_reason,
        "totals_sigma_kelly":    tot_skel,
        "h2h_sigma_kelly":       h2h_skel,
        "totals_p_over_ci_low":  tot_ci_lo,
        "totals_p_over_ci_high": tot_ci_hi,
    }
