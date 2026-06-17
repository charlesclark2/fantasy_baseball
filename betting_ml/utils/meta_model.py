"""meta_model.py — Story 12.4 Bayesian CLV meta-model inference.

Serve-side helper that turns a morning game's raw signals into a calibrated P(CLV > 0)
with an 80% credible interval, using the posterior trace + scaler produced by
`betting_ml/scripts/train_bayesian_meta_model.py`.

Feature set (must match the trainer exactly):
    edge_mag       = |(model_home_prob − open_home_win_prob) − edge_median|
    pub_align      = (home_ml_money_pct − home_ml_ticket_pct) × sign(centered edge)
    open_extremity = |open_home_win_prob − 0.5|
`edge_median` and the per-feature standardization (mean/std) are training statistics read
from the scaler sidecar so serve-time transforms match training.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

FEATURES = ["edge_mag", "pub_align", "open_extremity"]


def load_scaler(path: str | Path) -> dict:
    """Load the scaler/feature-spec sidecar written next to the trace."""
    return json.loads(Path(path).read_text())


_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[1] / "models" / "meta_model"


def load_latest_meta_model(models_dir: str | Path | None = None):
    """Load the most-recent (trace, scaler) pair from the meta_model dir.

    Picks the highest `bayesian_meta_trace_{n:04d}.nc` (zero-padded n → lexical sort =
    numeric sort) with a matching `meta_model_scaler_{n}.json`. Returns (None, None) when
    no trained artifact is present or the load fails — callers must serve-skip meta columns
    rather than crash (the meta-model is an optional serve enrichment, not core scoring).
    """
    d = Path(models_dir) if models_dir else _DEFAULT_MODELS_DIR
    try:
        traces = sorted(d.glob("bayesian_meta_trace_*.nc"))
        if not traces:
            return None, None
        trace_path = traces[-1]
        n = trace_path.stem.rsplit("_", 1)[-1]
        scaler_path = d / f"meta_model_scaler_{n}.json"
        if not scaler_path.exists():
            return None, None
        import arviz as az
        return az.from_netcdf(str(trace_path)), load_scaler(scaler_path)
    except Exception:
        return None, None


def build_meta_features(game: dict, scaler: dict) -> dict:
    """
    Derive the three meta-model features from a game's raw morning signals.

    `game` keys: model_home_prob, open_home_win_prob, and optionally
    handle_ticket_div (AN money% − ticket%; missing → 0, i.e. neutral public money).
    """
    edge_c = (float(game["model_home_prob"]) - float(game["open_home_win_prob"])
              - float(scaler["edge_median"]))
    side = float(np.sign(edge_c))
    div = game.get("handle_ticket_div")
    div = 0.0 if div is None else float(div)
    return {
        "edge_mag": abs(edge_c),
        "pub_align": div * side,
        "open_extremity": abs(float(game["open_home_win_prob"]) - 0.5),
    }


def _standardize(feats: dict, scaler: dict) -> np.ndarray:
    return np.array([
        (feats[f] - scaler["mean"][f]) / (scaler["std"][f] or 1.0) for f in FEATURES
    ], dtype=float)


def _posterior_betas(trace) -> tuple[np.ndarray, np.ndarray]:
    """Flatten (chain, draw) → (b0 samples, beta samples [S, F])."""
    post = trace.posterior
    b0 = post["b0"].values.reshape(-1)
    betas = np.stack([post[f"b_{f}"].values.reshape(-1) for f in FEATURES], axis=1)
    return b0, betas


def compute_meta_model_prediction(game_features: dict, trace, scaler: dict) -> dict[str, Any]:
    """
    Posterior predictive P(CLV > 0) with an 80% credible interval for one game.

    `game_features` may be either raw morning signals (model_home_prob,
    open_home_win_prob, handle_ticket_div) or already-derived FEATURES; raw signals are
    detected by the presence of `model_home_prob` and converted via build_meta_features.
    Returns the column dict written to daily_model_predictions.
    """
    if "model_home_prob" in game_features:
        feats = build_meta_features(game_features, scaler)
    else:
        feats = {f: float(game_features[f]) for f in FEATURES}

    z = _standardize(feats, scaler)
    b0, betas = _posterior_betas(trace)
    logits = b0 + betas @ z                      # (S,)
    p = 1.0 / (1.0 + np.exp(-logits))
    lo, hi = np.percentile(p, 10), np.percentile(p, 90)
    return {
        "meta_p_clv_positive": float(p.mean()),
        "meta_ci_low": float(lo),
        "meta_ci_high": float(hi),
        "meta_ci_width": float(hi - lo),
        "meta_n_games_trained": int(scaler.get("n_games", 0)),
        "meta_model_type": "bayesian_sequential",
    }
