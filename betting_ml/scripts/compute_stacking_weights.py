"""
compute_stacking_weights.py — Epic 9, Story 9.3

Turns the 9.2 signal evaluation into explicit pseudo-BMA stacking weights and a
law-of-total-variance combiner that produces a combined (mu, sigma) from the
PROMOTED sub-model signals. Weights are persisted (version-controlled) for the
Layer 3 combiner that Epics 10/11 consume.

Pseudo-BMA: w_i ∝ exp(−NLL_i) over promoted signals (Yao et al., 2018), where
NLL_i is each signal's *standalone* held-out NLL — a single-feature walk-forward
model (signal mu → target). 9.2 produced *incremental* deltas, which aren't
comparable in a softmax; the single-feature model also maps each heterogeneous
signal onto the target scale. Only signals that PROMOTED in 9.2 are weighted
(deferred/rejected → 0): the incremental gate already removed the redundant
signals that standalone-NLL pseudo-BMA would otherwise over-weight.

Combiner (law of total variance):
    combined_mu    = Σ w_i μ_i
    combined_sigma = sqrt( Σ w_i σ_i²  +  Σ w_i (μ_i − combined_mu)² )
                          [within-model]   [across-model disagreement]
Exercised/validated on total_runs. (For home_win the weights still produce a
weighted-probability combine; the LTV "sigma" is reported as informational
across-model probability spread.)

Outputs: betting_ml/models/layer3/stacking_weights.json; MLflow 'layer3_evaluation'.
No Snowflake writes. Full run is >1 min (single-feature GLMs × signals × folds).

Usage:
    uv run python betting_ml/scripts/compute_stacking_weights.py --env prod
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    load_layer3_features, _SIGNAL_GROUPS,
)
from betting_ml.scripts.evaluate_layer3_signals import (  # noqa: E402
    _design, _fit_poisson_mu, _fit_negbin_r, _negbin_nll, _fit_logit_p, _logloss,
    _group_mu_cols,
)
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_ABLATION_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_WEIGHTS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "stacking_weights.json"
_MLFLOW_EXPERIMENT = "layer3_evaluation"
_FOLD_STABILITY_FLAG = 0.15

_CHAMPION_VERSION = {
    "run_env": "run_env_v4", "offense": "offense_v2", "starter": "starter_v1",
    "starter_ip": "starter_ip_v1", "bullpen": "bullpen_v2", "matchup": "matchup_v1",
}
_GROUP_BY_LABEL = {g[0]: g for g in _SIGNAL_GROUPS}


# --------------------------------------------------------------------------- #
# Pure functions (spec signatures)
# --------------------------------------------------------------------------- #
def compute_pseudo_bma_weights(nll_scores: dict[str, float]) -> dict[str, float]:
    """Pseudo-BMA weights: w_i ∝ exp(−NLL_i), normalized. Deterministic.

    nll_scores should contain only the signals to be weighted (promoted set);
    an empty dict returns {}.
    """
    if not nll_scores:
        return {}
    groups = sorted(nll_scores)
    s = -np.array([nll_scores[g] for g in groups], dtype=float)
    e = np.exp(s - s.max())                      # stabilized softmax
    w = e / e.sum()
    return {g: float(wi) for g, wi in zip(groups, w)}


def combine_distributional_signals(signal_mus: dict, signal_sigmas: dict,
                                    weights: dict) -> tuple[float, float]:
    """Law-of-total-variance combine over the weighted signals (weights>0).

    Accepts scalars or aligned numpy arrays per signal (broadcasts elementwise).
    Weights are renormalized over the provided signals.
    """
    groups = [g for g in sorted(weights) if weights[g] > 0
              and g in signal_mus and g in signal_sigmas]
    w = np.array([weights[g] for g in groups], dtype=float)
    w = w / w.sum()
    mu = np.array([np.asarray(signal_mus[g], dtype=float) for g in groups])
    sig = np.array([np.asarray(signal_sigmas[g], dtype=float) for g in groups])
    combined_mu = np.tensordot(w, mu, axes=1)
    within = np.tensordot(w, sig ** 2, axes=1)
    across = np.tensordot(w, (mu - combined_mu) ** 2, axes=1)
    combined_sigma = np.sqrt(within + across)
    if np.ndim(combined_mu) == 0:
        return float(combined_mu), float(combined_sigma)
    return combined_mu, combined_sigma


def weight_stability_check(per_signal_fold_nlls: dict[str, list]) -> dict[str, float]:
    """Std of per-fold pseudo-BMA weights for each signal (high std = unstable)."""
    groups = list(per_signal_fold_nlls)
    n_folds = len(next(iter(per_signal_fold_nlls.values()))) if groups else 0
    fold_w = {g: [] for g in groups}
    for k in range(n_folds):
        w_k = compute_pseudo_bma_weights({g: per_signal_fold_nlls[g][k] for g in groups})
        for g in groups:
            fold_w[g].append(w_k[g])
    return {g: float(np.std(fold_w[g])) for g in groups}


# --------------------------------------------------------------------------- #
# Per-signal standalone NLL + per-game target-scale (mu, sigma)
# --------------------------------------------------------------------------- #
def _standalone_signal_nll(label: str, df: pd.DataFrame, target: str, folds: list) -> tuple[float, list]:
    """Single-feature walk-forward held-out NLL for one signal (mu → target)."""
    _, mu, *_ = _GROUP_BY_LABEL[label]
    cols = _group_mu_cols(label, mu)
    y_all = pd.to_numeric(df[target]).to_numpy(dtype=float)
    fold_nlls = []
    for tr_idx, ev_idx in folds:
        y_tr = y_all[df.index.get_indexer(tr_idx)]
        y_ev = y_all[df.index.get_indexer(ev_idx)]
        X_tr, means = _design(df, tr_idx, cols)
        X_ev, _ = _design(df, ev_idx, cols, means)
        if target == "total_runs":
            mu_tr, mu_ev = _fit_poisson_mu(X_tr, y_tr, X_ev)
            r = _fit_negbin_r(y_tr, mu_tr)
            fold_nlls.append(_negbin_nll(y_ev, mu_ev, r))
        else:
            fold_nlls.append(_logloss(_fit_logit_p(X_tr, y_tr, X_ev), y_ev))
    return float(np.mean(fold_nlls)), [float(x) for x in fold_nlls]


def _per_game_signal_dist(label: str, df: pd.DataFrame, target: str) -> tuple[np.ndarray, np.ndarray]:
    """Refit single-feature model on all rows; return per-game (mu, sigma) on target scale.

    In-sample (combiner demonstration / validation only); Epic 10 trains properly.
    """
    _, mu, *_ = _GROUP_BY_LABEL[label]
    cols = _group_mu_cols(label, mu)
    y = pd.to_numeric(df[target]).to_numpy(dtype=float)
    X, _ = _design(df, df.index, cols)
    if target == "total_runs":
        mu_tr, mu_all = _fit_poisson_mu(X, y, X)
        r = _fit_negbin_r(y, mu_tr)
        sigma = np.sqrt(mu_all + mu_all ** 2 / r)        # NB2 variance
        return mu_all, sigma
    p = _fit_logit_p(X, y, X)
    return p, np.sqrt(p * (1 - p))                        # Bernoulli


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _load_promoted(eval_json: Path) -> dict[str, list[str]]:
    """Read 9.2 results JSON → {target: [promoted signal labels]}."""
    data = json.loads(eval_json.read_text())
    out = {}
    for target, blk in data.get("targets", {}).items():
        out[target] = [g["signal_group"] for g in blk["groups"]
                       if g["signal_verdict"] == "promote"]
    return out


def _resolve_eval_json(arg: str) -> Path:
    if arg != "latest":
        return Path(arg)
    matches = sorted(glob.glob(str(_ABLATION_DIR / "layer3_signal_evaluation_*.json")))
    if not matches:
        raise FileNotFoundError("No layer3_signal_evaluation_*.json found — run 9.2 first.")
    return Path(matches[-1])


def run(env: str = "prod", eval_json: str = "latest", min_train_seasons: int = 2,
        start_date: str = "2021-01-01") -> dict:
    ev_path = _resolve_eval_json(eval_json)
    promoted_by_target = _load_promoted(ev_path)
    log.info("Promoted signals from %s: %s", ev_path.name, promoted_by_target)

    df = load_layer3_features(start_date=start_date, env=env)
    folds = list(all_season_splits(df, min_train_seasons=min_train_seasons))

    result = {"meta": {"env": env, "eval_json": ev_path.name, "n_games": len(df),
                       "min_train_seasons": min_train_seasons,
                       "generated_at": datetime.now().isoformat(timespec="seconds")},
              "targets": {}, "validation": {}}

    for target, promoted in promoted_by_target.items():
        if not promoted:
            result["targets"][target] = {}
            continue
        mean_nll, fold_nlls = {}, {}
        for label in promoted:
            m, fl = _standalone_signal_nll(label, df, target, folds)
            mean_nll[label], fold_nlls[label] = m, fl
        weights = compute_pseudo_bma_weights(mean_nll)
        fold_std = weight_stability_check(fold_nlls)

        result["targets"][target] = {
            label: {
                "weight": round(weights[label], 6),
                "nll_score": round(mean_nll[label], 6),
                "n_folds": len(fold_nlls[label]),
                "fold_weight_std": round(fold_std[label], 6),
                "fold_weight_unstable": fold_std[label] > _FOLD_STABILITY_FLAG,
                "verdict": "promote",
                "champion_version": _CHAMPION_VERSION.get(label, label),
            } for label in sorted(promoted)
        }
        log.info("[%s] weights: %s", target,
                 {l: round(weights[l], 3) for l in sorted(promoted)})

        if target == "total_runs":
            result["validation"]["total_runs"] = _validate_totals(df, promoted, weights)

    return result


def _validate_totals(df: pd.DataFrame, promoted: list[str], weights: dict) -> dict:
    """ACs: weight sum, fewer-vs-all sigma (reported), high-disagreement sigma (holds by construction)."""
    dist = {label: _per_game_signal_dist(label, df, "total_runs") for label in promoted}
    mus = {label: dist[label][0] for label in promoted}
    sigmas = {label: dist[label][1] for label in promoted}

    all_mu, all_sigma = combine_distributional_signals(mus, sigmas, weights)
    across = all_sigma ** 2 - np.tensordot(  # across-model variance per game
        np.array([weights[l] for l in sorted(promoted)]) /
        sum(weights[l] for l in promoted),
        np.array([sigmas[l] for l in sorted(promoted)]) ** 2, axes=1)

    out = {
        "weights_sum": round(float(sum(weights.values())), 8),
        "mean_combined_sigma_all": round(float(all_sigma.mean()), 4),
    }

    # Fewer-signals scenario: run_env + offense only (renormalized) — REPORTED, not asserted.
    sub = [l for l in ("run_env", "offense") if l in promoted]
    if len(sub) >= 1:
        sub_w = {l: weights[l] for l in sub}
        _, sub_sigma = combine_distributional_signals(
            {l: mus[l] for l in sub}, {l: sigmas[l] for l in sub}, sub_w)
        out["mean_combined_sigma_run_env_offense_only"] = round(float(np.mean(sub_sigma)), 4)
        out["fewer_signals_larger_sigma"] = bool(np.mean(sub_sigma) > all_sigma.mean())

    # High-disagreement (holds by construction): top-3 across-model-variance games in 2025.
    yr = df["game_year"].to_numpy()
    mask2025 = yr == 2025
    if mask2025.any():
        idx2025 = np.where(mask2025)[0]
        top3 = idx2025[np.argsort(across[idx2025])[-3:]][::-1]
        median_sigma = float(np.median(all_sigma[idx2025]))
        out["high_disagreement_games"] = [
            {"game_pk": int(df.iloc[i]["game_pk"]),
             "across_model_var": round(float(across[i]), 4),
             "combined_sigma": round(float(all_sigma[i]), 4),
             "per_signal_mu": {l: round(float(mus[l][i]), 3) for l in promoted}}
            for i in top3
        ]
        out["median_combined_sigma_2025"] = round(median_sigma, 4)
        out["high_disagreement_larger_sigma"] = bool(
            all(all_sigma[i] > median_sigma for i in top3))
    return out


def _persist_weights(result: dict) -> Path:
    _WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"meta": result["meta"], "targets": result["targets"]}
    _WEIGHTS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True))
    log.info("Wrote %s", _WEIGHTS_PATH)
    return _WEIGHTS_PATH


def _log_mlflow(result: dict) -> None:
    import mlflow
    from betting_ml.utils.mlflow_utils import get_or_create_experiment
    exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
    with mlflow.start_run(experiment_id=exp_id, run_name="layer3_stacking_weights"):
        mlflow.log_params({k: result["meta"][k] for k in ("env", "eval_json", "n_games", "min_train_seasons")})
        for target, groups in result["targets"].items():
            for label, info in groups.items():
                mlflow.log_metric(f"{target}__{label}__weight", info["weight"])
                mlflow.log_metric(f"{target}__{label}__fold_weight_std", info["fold_weight_std"])
                mlflow.set_tag(f"{target}__{label}__champion", info["champion_version"])
    log.info("Logged MLflow run under '%s'", _MLFLOW_EXPERIMENT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Layer 3 pseudo-BMA stacking weights (Epic 9.3)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod")
    parser.add_argument("--eval-json", default="latest", help="9.2 results JSON path, or 'latest'")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    result = run(env=args.env, eval_json=args.eval_json,
                 min_train_seasons=args.min_train_seasons, start_date=args.start_date)
    _persist_weights(result)
    if not args.no_mlflow:
        try:
            _log_mlflow(result)
        except Exception as exc:  # noqa: BLE001
            log.warning("MLflow logging skipped: %s", exc)

    v = result.get("validation", {}).get("total_runs", {})
    log.info("Validation (total_runs): weights_sum=%s, σ(all)=%s, σ(run_env+offense)=%s, "
             "fewer→larger=%s, high-disagreement→larger=%s",
             v.get("weights_sum"), v.get("mean_combined_sigma_all"),
             v.get("mean_combined_sigma_run_env_offense_only"),
             v.get("fewer_signals_larger_sigma"), v.get("high_disagreement_larger_sigma"))
    unstable = [f"{t}/{l}" for t, g in result["targets"].items()
                for l, info in g.items() if info["fold_weight_unstable"]]
    if unstable:
        log.warning("Fold-weight-unstable signals (std>%.2f): %s", _FOLD_STABILITY_FLAG, unstable)


if __name__ == "__main__":
    main()
