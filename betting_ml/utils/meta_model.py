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
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

FEATURES = ["edge_mag", "pub_align", "open_extremity"]


def load_scaler(path: str | Path) -> dict:
    """Load the scaler/feature-spec sidecar written next to the trace."""
    return json.loads(Path(path).read_text())


_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[1] / "models" / "meta_model"
_S3_BUCKET = "baseball-betting-ml-artifacts"
_S3_PREFIX = "meta_model"


def _load_from_dir(d: Path):
    """Load the highest-n (trace, scaler) pair from a directory, or (None, None)."""
    traces = sorted(d.glob("bayesian_meta_trace_*.nc"))  # zero-padded n → lexical == numeric
    if not traces:
        return None, None
    trace_path = traces[-1]
    n = trace_path.stem.rsplit("_", 1)[-1]
    scaler_path = d / f"meta_model_scaler_{n}.json"
    if not scaler_path.exists():
        return None, None
    import arviz as az
    return az.from_netcdf(str(trace_path)), load_scaler(scaler_path)


def _pull_latest_from_s3(cache_dir: Path) -> bool:
    """Download the trace+scaler named in `meta_model_latest.json` into `cache_dir`.

    The Story O.5 weekly retrain uploads the newest trace/scaler plus a stable
    `meta_model_latest.json` pointer to S3. This pulls that pointer's pair so serve
    picks up the weekly update without a redeploy. Fail-open: any error (no creds,
    missing object, network) returns False → caller falls back to the local trace.
    """
    import io

    import boto3

    s3 = boto3.client("s3")
    buf = io.BytesIO()
    s3.download_fileobj(_S3_BUCKET, f"{_S3_PREFIX}/meta_model_latest.json", buf)
    summary = json.loads(buf.getvalue().decode())
    trace_file, scaler_file = summary["trace_file"], summary["scaler_file"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name in (trace_file, scaler_file):
        dest = cache_dir / name
        if not dest.exists():  # immutable per-n names → cache once
            s3.download_file(_S3_BUCKET, f"{_S3_PREFIX}/{name}", str(dest))
    return (cache_dir / trace_file).exists() and (cache_dir / scaler_file).exists()


def load_latest_meta_model(models_dir: str | Path | None = None):
    """Load the most-recent (trace, scaler) pair for serving.

    Prod serve prefers the newest trace from S3 (the Story O.5 weekly-retrain target)
    so a Wednesday retrain reaches serve without a redeploy, then falls back to the
    baked-in local `betting_ml/models/meta_model/` trace on any S3 failure. An explicit
    `models_dir` (tests / offline) loads from that dir only and skips S3. Set
    `META_MODEL_S3_DISABLE=1` to force local-only. Returns (None, None) when no artifact
    is available or the load fails — callers serve-skip the meta columns rather than
    crash (the meta-model is an optional serve enrichment, not core scoring).
    """
    if models_dir is not None:
        try:
            return _load_from_dir(Path(models_dir))
        except Exception:
            return None, None

    if os.environ.get("META_MODEL_S3_DISABLE") != "1":
        try:
            cache = Path(tempfile.gettempdir()) / "meta_model_cache"
            if _pull_latest_from_s3(cache):
                got = _load_from_dir(cache)
                if got != (None, None):
                    return got
        except Exception:
            pass  # fall through to local baked-in trace

    try:
        return _load_from_dir(_DEFAULT_MODELS_DIR)
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
