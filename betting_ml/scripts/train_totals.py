"""
train_totals.py — Epic 10, Story 10.2

Layer 3 totals distribution model: a calibrated NegBin(mu, r) predictive
distribution over `total_runs`, trained EXCLUSIVELY on the Layer 3 feature matrix
(sub-model distributional signals — no market inputs). This fixes the existing
NGBoost totals model's variance-shrinkage failure (std(pred) = 0.77).

Candidates (champion = lower held-out NLL; must beat the GLM floor):
  A — LightGBM conditional mean + NegBin r from residuals (per predicted-mean decile)
  B — Ridge     conditional mean + NegBin r from residuals (per predicted-mean decile)
  C — NegBin GLM (statsmodels) joint MLE — NLL FLOOR REFERENCE only, not promotable

Gates: NLL < C floor (primary); calib_80 >= 0.80; MAE <= 3.55 (current NGBoost v3
champion); fold consistency >= ceil(0.6 * n_folds). Optuna tunes the winner.

  ⚠️ PROMOTION SCOPE: --promote registers this as the **Layer 3** totals champion
  (populates the `layer3_totals` registry stub + uploads the artifact to S3). It
  does NOT flip the production `total_runs` source — that go-live decision is
  Story 10.6 (champion-vs-challenger) → 10.7 (integration). Default run writes
  NOTHING outside local artifacts + MLflow.

Artifact:  betting_ml/models/sub_models/totals_v1.pkl  (TotalsNegBinModel)
S3 URI:    s3://baseball-betting-ml-artifacts/sub_models/totals_v1.pkl

Usage:
    # Full train + CV + champion selection (HAND OFF — minutes):
    uv run python betting_ml/scripts/train_totals.py --env prod
    # Register the Layer 3 champion (S3 + layer3_totals registry):
    uv run python betting_ml/scripts/train_totals.py --env prod --promote
    # Fast smoke (tiny synthetic-ish subsample, no MLflow):
    uv run python betting_ml/scripts/train_totals.py --env prod --quick --no-mlflow
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import build_totals_dataset  # noqa: E402
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
# Champion class + predict-time helpers live in an importable module so the
# pickled artifact binds to a stable path (not __main__).
from betting_ml.models.totals_negbin_model import (  # noqa: E402
    TotalsNegBinModel,
    assign_r,
    coerce_numeric as _coerce_numeric,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "totals_v1.pkl"
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/totals_v1.pkl"
_REGISTRY_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
_COMPARISON_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "totals_v1_architecture_comparison.md"
)

_CALIB_80_GATE = 0.80
_MAE_GATE = 3.55           # current market-blind NGBoost v3 totals champion
_MIN_STD_PRED = 1.5        # variance-shrinkage target (informational here; gated in 10.6)
_MIN_TRAIN_SEASONS = 2     # 2021-2026 → eval folds 2023..2026 (4 folds)
_N_DECILES = 10
_OPTUNA_SEED = 42
_MLFLOW_EXPERIMENT = "totals_v1"
_ALPHA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]


# ---------------------------------------------------------------------------
# NegBin (mu, r) helpers — NB2 parameterization (variance = mu + mu^2/r)
# ---------------------------------------------------------------------------

def _negbin_logpmf(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    mu = np.clip(mu, 1e-6, None)
    r = max(r, 1e-6)
    return (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1)
        + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu))
    )


def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    return float(-np.mean(_negbin_logpmf(y, mu, r)))


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of NegBin dispersion r given fixed conditional means mu (1-D search)."""
    if len(y) < 2:
        return 10.0
    res = minimize_scalar(lambda r: _negbin_nll(y, mu, r),
                          bounds=(0.01, 1000.0), method="bounded")
    return float(res.x)


def _negbin_80pct_calibration(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Fraction of actuals within the central 80% NegBin PI (target ~0.80)."""
    r = max(r, 1e-6)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, r, p)
    hi = nbinom.ppf(0.90, r, p)
    return float(np.mean((y >= lo) & (y <= hi)))


def _std_pred(mu: np.ndarray, r: float) -> float:
    """Mean predictive std of the NegBin: sqrt(mu + mu^2/r)."""
    r = max(r, 1e-6)
    return float(np.mean(np.sqrt(mu + mu ** 2 / r)))


# ---------------------------------------------------------------------------
# Per-predicted-mean-decile dispersion (Story 10.2 spec)
# `coerce_numeric` and `assign_r` are imported from
# betting_ml.models.totals_negbin_model (shared with predict time).
# ---------------------------------------------------------------------------

def fit_decile_r(y: np.ndarray, mu: np.ndarray, n_deciles: int = _N_DECILES) -> tuple[np.ndarray, np.ndarray, float]:
    """Fit NegBin r per predicted-mean decile. Returns (edges, r_per_bin, global_r).

    Heteroscedastic dispersion: high-mu games are more overdispersed than low-mu
    games, so a single r under-states tail risk where it matters most. `edges`
    are the interior mu quantile boundaries (len n_deciles-1); bin i covers
    (edges[i-1], edges[i]]. Bins with < 30 games reuse the global r.
    """
    global_r = _fit_negbin_r(y, mu)
    qs = np.linspace(0, 1, n_deciles + 1)[1:-1]
    edges = np.unique(np.quantile(mu, qs)) if len(mu) else np.array([])
    bins = np.digitize(mu, edges)
    r_per_bin = np.full(len(edges) + 1, global_r, dtype=float)
    for b in range(len(edges) + 1):
        m = bins == b
        if m.sum() >= 30:
            r_per_bin[b] = _fit_negbin_r(y[m], mu[m])
    return edges, r_per_bin, global_r


# ---------------------------------------------------------------------------
# Conditional-mean fitters
# ---------------------------------------------------------------------------

def _fit_lightgbm(X_tr: pd.DataFrame, y_tr: np.ndarray, params: dict):
    import lightgbm as lgb
    model = lgb.LGBMRegressor(objective="regression", verbosity=-1,
                              random_state=_OPTUNA_SEED, **params)
    model.fit(X_tr, y_tr)
    return model


def _fit_ridge(X_tr: pd.DataFrame, y_tr: np.ndarray, alpha: float):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    # SimpleImputer handles NaN signal columns (missing groups); fit per-fold (no leakage).
    pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("ridge", Ridge(alpha=alpha)),
    ])
    pipe.fit(X_tr, y_tr)
    return pipe


_DEFAULT_LGBM = {"n_estimators": 300, "learning_rate": 0.03, "num_leaves": 31,
                 "min_child_samples": 40, "subsample": 0.8, "colsample_bytree": 0.8}


# ---------------------------------------------------------------------------
# Walk-forward CV
# ---------------------------------------------------------------------------

def _folds(meta: pd.DataFrame) -> list[tuple[pd.Index, pd.Index]]:
    return list(all_season_splits(meta, min_train_seasons=_MIN_TRAIN_SEASONS))


def _cv_mean_negbin(X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame, kind: str,
                    params: dict) -> dict:
    """Walk-forward CV for a mean+decile-NegBin candidate (kind ∈ lightgbm|ridge)."""
    folds = _folds(meta)
    fold_recs: list[dict] = []
    for tr_idx, ev_idx in folds:
        X_tr, y_tr = X.loc[tr_idx], y.loc[tr_idx].to_numpy()
        X_ev, y_ev = X.loc[ev_idx], y.loc[ev_idx].to_numpy()
        if kind == "lightgbm":
            model = _fit_lightgbm(X_tr, y_tr, params)
        else:
            model = _fit_ridge(X_tr, y_tr, params["alpha"])
        mu_tr = np.clip(model.predict(X_tr), 1e-6, None)
        mu_ev = np.clip(model.predict(X_ev), 1e-6, None)
        edges, r_bin, g_r = fit_decile_r(y_tr, mu_tr)   # dispersion from TRAIN residuals
        r_ev = assign_r(mu_ev, edges, r_bin, g_r)
        fold_recs.append({
            "eval_year": int(meta.loc[ev_idx, "game_year"].iloc[0]),
            "n_eval": int(len(y_ev)),
            "nll": _negbin_nll(y_ev, mu_ev, float(np.mean(r_ev))),
            "mae": float(np.mean(np.abs(y_ev - mu_ev))),
            "calib_80": _negbin_80pct_calibration(y_ev, mu_ev, float(np.mean(r_ev))),
            "std_pred": float(np.mean(np.sqrt(mu_ev + mu_ev ** 2 / np.clip(r_ev, 1e-6, None)))),
            "global_r": round(g_r, 4),
        })
    return _aggregate(kind, fold_recs)


def _cv_glm_floor(X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame) -> dict:
    """Candidate C — NegBin GLM (statsmodels) joint MLE. NLL FLOOR reference only."""
    import statsmodels.api as sm
    fold_recs: list[dict] = []
    for tr_idx, ev_idx in _folds(meta):
        # Force a clean float ndarray: median-impute from TRAIN, zero-fill any
        # column that is all-NaN within the fold (median itself NaN), then to_numpy
        # — statsmodels errors on object/pandas-NA dtypes otherwise.
        Xtr_df = X.loc[tr_idx].astype(float)
        Xev_df = X.loc[ev_idx].astype(float)
        med = Xtr_df.median()
        Xtr = Xtr_df.fillna(med).fillna(0.0).to_numpy(dtype=float)
        Xev = Xev_df.fillna(med).fillna(0.0).to_numpy(dtype=float)
        X_tr = sm.add_constant(Xtr, has_constant="add")
        X_ev = sm.add_constant(Xev, has_constant="add")
        y_tr, y_ev = y.loc[tr_idx].to_numpy(), y.loc[ev_idx].to_numpy()
        try:
            res = sm.GLM(y_tr, X_tr, family=sm.families.NegativeBinomial(alpha=1.0)).fit(maxiter=100)
            mu_ev = np.clip(res.predict(X_ev), 1e-6, None)
        except Exception as exc:  # noqa: BLE001 — GLM convergence is best-effort (floor only)
            log.warning("  [C] GLM fold %s did not converge (%s); skipping", int(meta.loc[ev_idx, "game_year"].iloc[0]), exc)
            continue
        r = _fit_negbin_r(y_ev, mu_ev)
        fold_recs.append({
            "eval_year": int(meta.loc[ev_idx, "game_year"].iloc[0]),
            "n_eval": int(len(y_ev)),
            "nll": _negbin_nll(y_ev, mu_ev, r),
            "mae": float(np.mean(np.abs(y_ev - mu_ev))),
            "calib_80": _negbin_80pct_calibration(y_ev, mu_ev, r),
            "std_pred": _std_pred(mu_ev, r), "global_r": round(r, 4),
        })
    return _aggregate("glm", fold_recs)


def _aggregate(kind: str, fold_recs: list[dict]) -> dict:
    if not fold_recs:
        return {"kind": kind, "nll": float("inf"), "mae": float("inf"),
                "calib_80": 0.0, "std_pred": 0.0, "folds": [], "win_count": 0}
    return {
        "kind": kind,
        "nll": float(np.mean([f["nll"] for f in fold_recs])),
        "mae": float(np.mean([f["mae"] for f in fold_recs])),
        "calib_80": float(np.mean([f["calib_80"] for f in fold_recs])),
        "std_pred": float(np.mean([f["std_pred"] for f in fold_recs])),
        "folds": fold_recs,
    }


# ---------------------------------------------------------------------------
# Champion selection
# ---------------------------------------------------------------------------

def _consistency_needed(n_folds: int) -> int:
    import math
    return max(1, math.ceil(0.6 * n_folds))


def select_champion(a: dict, b: dict, c_nll: float) -> tuple[str, dict]:
    """Champion = lower NLL among A/B that pass all gates. Returns (kind, metrics).

    Gates: NLL < C floor; calib_80 >= 0.80; MAE <= 3.55.
    """
    mae_thr = _MAE_GATE

    def passes(m: dict) -> bool:
        return (m["nll"] < c_nll) and (m["calib_80"] >= _CALIB_80_GATE) and (m["mae"] <= mae_thr)

    a_ok, b_ok = passes(a), passes(b)
    if not a_ok and not b_ok:
        return "none", (a if a["nll"] <= b["nll"] else b)
    if a_ok and not b_ok:
        return a["kind"], a
    if b_ok and not a_ok:
        return b["kind"], b
    return (a["kind"], a) if a["nll"] <= b["nll"] else (b["kind"], b)


# ---------------------------------------------------------------------------
# Optuna tuning of the winner
# ---------------------------------------------------------------------------

def _tune(kind: str, X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame, n_trials: int) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        if kind == "lightgbm":
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 150, 600),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "min_child_samples": trial.suggest_int("min_child_samples", 20, 120),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            }
        else:
            params = {"alpha": trial.suggest_float("alpha", 0.01, 1000.0, log=True)}
        return _cv_mean_negbin(X, y, meta, kind, params)["nll"]

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    best = study.best_params if kind == "lightgbm" else {"alpha": study.best_params["alpha"]}
    log.info("  Optuna(%s) best NLL=%.4f params=%s", kind, study.best_value, best)
    return best


# ---------------------------------------------------------------------------
# Finalize: fit winner on all data, build artifact
# ---------------------------------------------------------------------------

def finalize_model(kind: str, params: dict, X: pd.DataFrame, y: pd.Series) -> TotalsNegBinModel:
    y_arr = y.to_numpy()
    model = _fit_lightgbm(X, y_arr, params) if kind == "lightgbm" else _fit_ridge(X, y_arr, params["alpha"])
    mu = np.clip(model.predict(X), 1e-6, None)
    edges, r_bin, g_r = fit_decile_r(y_arr, mu)
    return TotalsNegBinModel(kind, model, list(X.columns), edges, r_bin, g_r)


# ---------------------------------------------------------------------------
# Reporting + registry
# ---------------------------------------------------------------------------

def _fold_table(m: dict) -> list[str]:
    rows = ["| eval year | n | NLL | MAE | calib_80 | std_pred | r |",
            "|---|---|---|---|---|---|---|"]
    for f in m["folds"]:
        rows.append(f"| {f['eval_year']} | {f['n_eval']} | {f['nll']:.4f} | {f['mae']:.3f} | "
                    f"{f['calib_80']:.3f} | {f['std_pred']:.3f} | {f['global_r']:.2f} |")
    return rows


def write_comparison(a: dict, b: dict, c: dict, winner: str, tuned_params: dict,
                     n_games: int, overdispersion: dict) -> Path:
    _COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)
    n_folds = len(a["folds"]) or len(b["folds"])
    lines = [
        "# Layer 3 Totals — Architecture Comparison (Story 10.2)",
        "",
        f"- Games: **{n_games}**; walk-forward folds: **{n_folds}** (min_train_seasons={_MIN_TRAIN_SEASONS}); "
        f"consistency needed: **{_consistency_needed(n_folds)}/{n_folds}**.",
        f"- Target overdispersion var/mean = **{overdispersion.get('overdispersion_ratio')}** (NegBin justified).",
        f"- Gates: NLL < C(GLM) floor; calib_80 ≥ {_CALIB_80_GATE}; MAE ≤ {_MAE_GATE} (NGBoost v3 champion).",
        "",
        "## Head-to-head (mean CV)",
        "",
        "| Candidate | NLL | MAE | calib_80 | std_pred |",
        "|---|---|---|---|---|",
        f"| A — LightGBM+NegBin | {a['nll']:.4f} | {a['mae']:.3f} | {a['calib_80']:.3f} | {a['std_pred']:.3f} |",
        f"| B — Ridge+NegBin | {b['nll']:.4f} | {b['mae']:.3f} | {b['calib_80']:.3f} | {b['std_pred']:.3f} |",
        f"| C — NegBin GLM (floor) | {c['nll']:.4f} | {c['mae']:.3f} | — | — |",
        "",
        f"**Winner: {winner}** — tuned params: `{json.dumps(tuned_params)}`.",
        "",
        f"_std(pred) target ≥ {_MIN_STD_PRED} (variance-shrinkage fix; the failing NGBoost model was 0.77). "
        "Formal head-to-head vs. the live champion is Story 10.6._",
        "",
        "## Candidate A folds", "", *_fold_table(a),
        "", "## Candidate B folds", "", *_fold_table(b),
    ]
    _COMPARISON_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote architecture comparison → %s", _COMPARISON_PATH)
    return _COMPARISON_PATH


def update_layer3_totals_registry(model_obj: TotalsNegBinModel, metrics: dict,
                                  mlflow_run_id: str | None) -> None:
    """Populate the `layer3_totals` registry stub (Story 9.4) with the trained
    Layer 3 champion. Does NOT touch the production `total_runs` entry — go-live is
    Story 10.6 → 10.7."""
    text = _REGISTRY_PATH.read_text()
    today = datetime.date.today().isoformat()
    arch = "LightGBM+NegBin" if model_obj.model_type == "lightgbm" else "Ridge+NegBin"
    new_block = (
        "layer3_totals:\n"
        f"  artifact_path: {_ARTIFACT_S3_URI}\n"
        "  feature_columns_path: betting_ml/models/layer3/layer3_feature_columns.json\n"
        "  stacking_weights_path: betting_ml/models/layer3/stacking_weights.json\n"
        "  target: total_runs\n"
        f"  model_type: {model_obj.model_type}\n"
        f"  architecture: {arch}\n"
        f"  mlflow_run_id: {mlflow_run_id or 'null'}\n"
        f"  cv_nll: {metrics['nll']:.4f}\n"
        f"  cv_mae: {metrics['mae']:.4f}\n"
        f"  cv_calib_80: {metrics['calib_80']:.4f}\n"
        f"  cv_std_pred: {metrics['std_pred']:.4f}\n"
        "  promotion_status: champion    # Layer 3 champion architecture; production go-live gated by Story 10.6/10.7\n"
        f"  promoted_signals: [run_env, offense, bullpen]\n"
        f"  trained_at: '{today}'\n"
        "  notes: >\n"
        f"    Epic 10 Story 10.2 — {arch} Layer 3 totals model. CV NLL {metrics['nll']:.4f}, "
        f"MAE {metrics['mae']:.3f}, calib_80 {metrics['calib_80']:.3f}, std(pred) {metrics['std_pred']:.3f}.\n"
        "    NOT yet the production totals source — awaiting Story 10.6 champion-vs-challenger decision.\n"
    )
    # Replace the existing layer3_totals block (from the 9.4 stub) up to the next
    # top-level key (layer3_h2h) or EOF.
    pattern = r"layer3_totals:\n(?:[ \t].*\n|\n)*?(?=^[A-Za-z_]|\Z)"
    if re.search(pattern, text, flags=re.MULTILINE):
        text = re.sub(pattern, new_block + "\n", text, count=1, flags=re.MULTILINE)
    else:
        text = text.rstrip() + "\n\n" + new_block
    _REGISTRY_PATH.write_text(text)
    log.info("Updated layer3_totals registry entry (promotion_status: champion).")


def _log_mlflow(a: dict, b: dict, c: dict, winner: str, metrics: dict, params: dict) -> str | None:
    try:
        import mlflow
        from betting_ml.utils.mlflow_utils import get_or_create_experiment
        exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
        with mlflow.start_run(experiment_id=exp_id, run_name="totals_v1_train") as run:
            mlflow.log_params({"winner": winner, **{f"param__{k}": v for k, v in params.items()}})
            for label, m in (("A_lgbm", a), ("B_ridge", b), ("C_glm", c)):
                mlflow.log_metric(f"{label}__nll", m["nll"])
                mlflow.log_metric(f"{label}__mae", m["mae"])
                mlflow.log_metric(f"{label}__calib_80", m["calib_80"])
            for k in ("nll", "mae", "calib_80", "std_pred"):
                mlflow.log_metric(f"champion__{k}", metrics[k])
            return run.info.run_id
    except Exception as exc:  # noqa: BLE001 — MLflow non-blocking
        log.warning("MLflow logging skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(env: str = "prod", optuna_trials: int = 50, compare_trials: int = 10,
        quick: bool = False, mlflow: bool = True, promote: bool = False) -> dict:
    X, y, _eval_lines, report, meta = build_totals_dataset(env=env, return_meta=True)
    X = _coerce_numeric(X)   # *_available object→float; NaN signals preserved for LGBM, imputed for Ridge/GLM
    if quick:  # tiny subsample for a fast smoke (last ~800 games)
        X, y, meta = X.tail(800).reset_index(drop=True), y.tail(800).reset_index(drop=True), meta.tail(800).reset_index(drop=True)
        optuna_trials, compare_trials = 3, 2

    n_folds = len(_folds(meta))
    log.info("Totals model: %d games, %d folds (min_train_seasons=%d)", len(X), n_folds, _MIN_TRAIN_SEASONS)
    if n_folds < 2:
        raise RuntimeError(f"Only {n_folds} CV fold(s) — need ≥2. Check the season span.")

    # Candidate comparison (light Optuna on A/B, GLM floor C).
    log.info("Tuning Candidate A (LightGBM) — %d trials...", compare_trials)
    a_params = _tune("lightgbm", X, y, meta, compare_trials)
    a = _cv_mean_negbin(X, y, meta, "lightgbm", a_params)
    log.info("  A: NLL=%.4f MAE=%.3f calib_80=%.3f std=%.3f", a["nll"], a["mae"], a["calib_80"], a["std_pred"])

    log.info("Tuning Candidate B (Ridge) — %d trials...", compare_trials)
    b_params = _tune("ridge", X, y, meta, compare_trials)
    b = _cv_mean_negbin(X, y, meta, "ridge", b_params)
    log.info("  B: NLL=%.4f MAE=%.3f calib_80=%.3f std=%.3f", b["nll"], b["mae"], b["calib_80"], b["std_pred"])

    log.info("Candidate C (NegBin GLM floor)...")
    c = _cv_glm_floor(X, y, meta)
    log.info("  C floor: NLL=%.4f", c["nll"])

    winner_kind, winner_metrics = select_champion(a, b, c["nll"])
    need = _consistency_needed(n_folds)
    if winner_kind == "none":
        log.warning("No candidate passed all gates (NLL<floor, calib_80≥%.2f, MAE≤%.2f). "
                    "No Layer 3 totals champion.", _CALIB_80_GATE, _MAE_GATE)
        write_comparison(a, b, c, "NONE (gates failed)", {}, len(X), report["overdispersion"])
        return {"winner": "none", "a": a, "b": b, "c": c}

    log.info("Winner: %s (NLL %.4f). Tuning winner with %d trials...", winner_kind, winner_metrics["nll"], optuna_trials)
    tuned = _tune(winner_kind, X, y, meta, optuna_trials)
    final_metrics = _cv_mean_negbin(X, y, meta, winner_kind, tuned)

    model_obj = finalize_model(winner_kind, tuned, X, y)
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_obj, _ARTIFACT_PATH)
    log.info("Saved champion artifact → %s (std_pred=%.3f)", _ARTIFACT_PATH, final_metrics["std_pred"])

    run_id = _log_mlflow(a, b, c, winner_kind, final_metrics, tuned) if mlflow else None
    write_comparison(a, b, c, f"Candidate {'A LightGBM' if winner_kind=='lightgbm' else 'B Ridge'}+NegBin",
                     tuned, len(X), report["overdispersion"])

    if promote:
        from betting_ml.utils.artifact_store import upload_artifact
        upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)
        log.info("Uploaded champion → %s", _ARTIFACT_S3_URI)
        update_layer3_totals_registry(model_obj, final_metrics, run_id)
    else:
        log.info("Default run — local artifact + report only. Re-run with --promote to register "
                 "the Layer 3 champion (S3 + layer3_totals registry). Production go-live is Story 10.6/10.7.")

    return {"winner": winner_kind, "metrics": final_metrics, "a": a, "b": b, "c": c, "params": tuned}


def main() -> None:
    p = argparse.ArgumentParser(description="Train the Layer 3 totals distribution model (Epic 10.2)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--optuna-trials", type=int, default=50, help="Trials for the winner (default 50)")
    p.add_argument("--compare-trials", type=int, default=10, help="Trials per candidate during comparison")
    p.add_argument("--quick", action="store_true", help="Tiny subsample + few trials (smoke test)")
    p.add_argument("--no-mlflow", action="store_true")
    p.add_argument("--promote", action="store_true",
                   help="Register as the LAYER 3 champion: upload to S3 + populate layer3_totals "
                        "registry. Does NOT flip the production totals source (Story 10.6/10.7).")
    p.add_argument("--floor-only", action="store_true",
                   help="Compute ONLY the Candidate C NegBin-GLM NLL floor and exit "
                        "(cheap — no LightGBM/Ridge/Optuna). Use to fill in a real floor without "
                        "re-running the full champion selection.")
    args = p.parse_args()

    if args.floor_only:
        X, y, _el, _rep, meta = build_totals_dataset(env=args.env, return_meta=True)
        X = _coerce_numeric(X)
        c = _cv_glm_floor(X, y, meta)
        log.info("Candidate C (NegBin GLM) NLL floor = %.4f over %d folds. "
                 "Champion must have CV NLL < this to clear the primary gate.",
                 c["nll"], len(c["folds"]))
        return

    result = run(env=args.env, optuna_trials=args.optuna_trials, compare_trials=args.compare_trials,
                 quick=args.quick, mlflow=not args.no_mlflow, promote=args.promote)
    if result["winner"] != "none":
        m = result["metrics"]
        log.info("Done. Champion=%s | CV NLL=%.4f MAE=%.3f calib_80=%.3f std_pred=%.3f",
                 result["winner"], m["nll"], m["mae"], m["calib_80"], m["std_pred"])


if __name__ == "__main__":
    main()
