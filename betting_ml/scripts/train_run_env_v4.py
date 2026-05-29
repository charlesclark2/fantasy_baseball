"""
train_run_env_v4.py — Run Environment Sub-Model v4 (Epic 3D, Stories 3D.1 + 3D.2)

Distributional Negative Binomial retrofit of run_env_v3.

Three candidates are evaluated on identical 19-feature walk-forward CV folds
(same feature set, imputation, and era engineering as v3):

  Candidate A — NGBoost (conditional mean, Normal GBM) + NegBin r from residuals
  Candidate B — Ridge v3 (conditional mean) + NegBin r from residuals  [speed baseline]
  Candidate C — NegBin GLM (statsmodels, joint MLE)  [NLL floor reference only — not promotable]

All three output NegBin (mu, r) parameters so NLL is apples-to-apples.
Candidate A uses NGBoost's Normal-optimal mean; NegBin r is then MLE-fit from
training residuals, making the final model a NegBin distribution over total runs.

Evaluation gates (Sub-model output standard):
  NLL        primary gate — winner must beat Candidate C NLL (GLM floor)
  calib_80   ≥ 80 % of observed totals fall within the model's 80% NegBin PI
  MAE        predicted-mu MAE must not regress vs. run_env_v3 (3.5127 ± _MAE_TOLERANCE)

  Note: std(pred) is NOT a gate for distributional models. calib_80 supersedes it —
  a Ridge with low mu variance can still be well-calibrated via NegBin (mu, r) spread.

Selection: lower mean CV NLL wins (A vs B); MAE is tiebreaker if NLL tied.
After winner selection, Optuna tunes the winner's hyperparameters (objective = mean
CV NLL on same folds). Final artifact is trained with tuned params.
Candidate C is printed for reference; it cannot be promoted.

Artifact:  betting_ml/models/sub_models/run_env_v4.pkl
S3 URI:    s3://baseball-betting-ml-artifacts/sub_models/run_env_v4.pkl
MLflow:    experiment run_env_v4

Usage:
    uv run python betting_ml/scripts/train_run_env_v4.py
    uv run python betting_ml/scripts/train_run_env_v4.py --no-promote
    uv run python betting_ml/scripts/train_run_env_v4.py --force-winner {ngboost,ridge}
    uv run python betting_ml/scripts/train_run_env_v4.py --refresh-cache
"""
from __future__ import annotations

import argparse
import json
import joblib
import re
import sys
from datetime import date
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.train_run_env import load_training_data, validate_no_leakage
from betting_ml.scripts.train_run_env_v3 import (
    FEATURE_COLS_V3,
    _prepare_fold,
    _compute_prior_season_runs,
    _add_era_features,
    _compute_impute_values_v3,
    _apply_imputation_v3,
)
from betting_ml.utils.training_cache import get_cached_df
from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold

_V3_CV_MAE       = 3.5127
_MAE_TOLERANCE   = 0.01   # gate: MAE ≤ _V3_CV_MAE + _MAE_TOLERANCE (noise margin)
_CALIB_80_GATE   = 0.80
_MIN_MU          = 0.5    # NegBin requires mu > 0; clip all predictions here

_REGISTRY_PATH   = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_ARTIFACT_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v4.pkl"
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/run_env_v4.pkl"

# NGBoost default params (used for candidate comparison; tuned by Optuna if winner)
_NGBOOST_N_EST = 500
_NGBOOST_LR    = 0.05

# Ridge alpha candidates (same grid as v3, now selected on NLL not MAE)
_ALPHA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

# Optuna tuning protocol (Sub-model output standard)
_OPTUNA_PROBE_TRIALS = 10   # feasibility probe
_OPTUNA_FULL_TRIALS  = 50   # full pass — always runs after probe
_OPTUNA_SEED         = 42


# ---------------------------------------------------------------------------
# NegBin utilities
# ---------------------------------------------------------------------------

def _negbin_logpmf(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    """Vectorized NegBin log PMF with NB2 parameterization (r = number of successes)."""
    y = np.round(y).clip(0).astype(int)
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    return (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1)
        + r * np.log(p + 1e-12)
        + y * np.log(1.0 - p + 1e-12)
    )


def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    return float(-_negbin_logpmf(y, mu, r).mean())


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of NegBin dispersion r given fixed conditional means mu (1-D optimization)."""
    def neg_loglik(log_r: float) -> float:
        return -_negbin_logpmf(y, mu, np.exp(log_r)).sum()
    result = minimize_scalar(neg_loglik, bounds=(np.log(0.1), np.log(500)), method="bounded")
    return float(np.exp(result.x))


def _negbin_80pct_calibration(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Fraction of observations within the model's 80% NegBin PI [10th, 90th pctile]."""
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(((y >= lo) & (y <= hi)).mean())


# ---------------------------------------------------------------------------
# Shared CV fold result builder
# ---------------------------------------------------------------------------

def _fold_record(
    fold_idx: int,
    train_seasons: list[int],
    test_season: int,
    y_tr: np.ndarray,
    y_te: np.ndarray,
    mu_te: np.ndarray,
    r: float,
) -> dict:
    nll   = _negbin_nll(y_te, mu_te, r)
    mae   = float(np.mean(np.abs(mu_te - y_te)))
    calib = _negbin_80pct_calibration(y_te, mu_te, r)
    return {
        "fold": fold_idx,
        "train_seasons": list(map(int, train_seasons)),
        "test_season": int(test_season),
        "n_train": int(len(y_tr)),
        "n_test": int(len(y_te)),
        "nll": round(nll, 4),
        "mae": round(mae, 4),
        "calib_80": round(calib, 4),
        "negbin_r": round(r, 4),
        "std_pred": round(float(np.std(mu_te)), 4),
    }


# ---------------------------------------------------------------------------
# Candidate A — NGBoost mean + NegBin r from residuals
# ---------------------------------------------------------------------------

def _walk_forward_cv_ngboost(df: pd.DataFrame) -> tuple[float, float, float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, std_pred_all_folds, calib_80, fold_records)."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    seasons = sorted(df["game_year"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [A] NGBoost: n_estimators={_NGBOOST_N_EST}, lr={_NGBOOST_LR}, {len(folds)} folds")

    all_mu: list[float] = []
    all_y:  list[float] = []
    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
        ngb = NGBRegressor(
            Dist=Normal,
            n_estimators=_NGBOOST_N_EST,
            learning_rate=_NGBOOST_LR,
            random_state=42,
            verbose=False,
        )
        ngb.fit(X_tr, y_tr)

        mu_tr = np.clip(ngb.predict(X_tr), _MIN_MU, None)
        mu_te = np.clip(ngb.predict(X_te), _MIN_MU, None)
        r     = _fit_negbin_r(y_tr, mu_tr)

        rec = _fold_record(
            len(fold_records) + 1, list(train_seasons), test_season, y_tr, y_te, mu_te, r
        )
        fold_records.append(rec)
        all_mu.extend(mu_te.tolist())
        all_y.extend(y_te.tolist())
        print(
            f"    fold {rec['fold']} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  r={rec['negbin_r']:.3f}  std_pred={rec['std_pred']:.3f}"
        )

    all_mu_arr = np.array(all_mu)
    all_y_arr  = np.array(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"] for f in fold_records]))
    std_pred   = float(np.std(all_mu_arr))
    calib_80   = _negbin_80pct_calibration(all_y_arr, all_mu_arr, global_r)

    return mean_nll, mean_mae, std_pred, calib_80, fold_records


# ---------------------------------------------------------------------------
# Candidate B — Ridge v3 conditional mean + NegBin r from residuals
# ---------------------------------------------------------------------------

def _walk_forward_cv_ridge_negbin(df: pd.DataFrame) -> tuple[float, float, float, float, list[dict], float]:
    """Returns (mean_nll, mean_mae, std_pred_all_folds, calib_80, fold_records, best_alpha)."""
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seasons = sorted(df["game_year"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    # Alpha selection on NLL (not MAE — this is the v3→v4 change)
    best_alpha    = 1.0
    best_mean_nll = float("inf")

    print(f"\n  [B] Ridge alpha search ({len(_ALPHA_GRID)} alphas × {len(folds)} folds)...")
    for alpha in _ALPHA_GRID:
        fold_nlls = []
        for train_seasons, test_season in folds:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
            pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
            pipe.fit(X_tr, y_tr)
            mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
            mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
            r     = _fit_negbin_r(y_tr, mu_tr)
            fold_nlls.append(_negbin_nll(y_te, mu_te, r))
        mean_nll = float(np.mean(fold_nlls))
        marker = " ←" if mean_nll < best_mean_nll else ""
        print(f"    alpha={alpha:>8}  mean_nll={mean_nll:.4f}{marker}")
        if mean_nll < best_mean_nll:
            best_mean_nll = mean_nll
            best_alpha    = alpha

    print(f"  [B] Best alpha: {best_alpha}")

    all_mu: list[float] = []
    all_y:  list[float] = []
    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
        pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        pipe.fit(X_tr, y_tr)
        mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
        mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
        r     = _fit_negbin_r(y_tr, mu_tr)

        rec = _fold_record(
            len(fold_records) + 1, list(train_seasons), test_season, y_tr, y_te, mu_te, r
        )
        fold_records.append(rec)
        all_mu.extend(mu_te.tolist())
        all_y.extend(y_te.tolist())
        print(
            f"    fold {rec['fold']} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  r={rec['negbin_r']:.3f}  std_pred={rec['std_pred']:.3f}"
        )

    all_mu_arr = np.array(all_mu)
    all_y_arr  = np.array(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"] for f in fold_records]))
    std_pred   = float(np.std(all_mu_arr))
    calib_80   = _negbin_80pct_calibration(all_y_arr, all_mu_arr, global_r)

    return mean_nll, mean_mae, std_pred, calib_80, fold_records, best_alpha


# ---------------------------------------------------------------------------
# Candidate C — NegBin GLM (NLL floor reference, not promotable)
# ---------------------------------------------------------------------------

def _walk_forward_cv_glm(df: pd.DataFrame) -> tuple[float, float, float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, std_pred_all_folds, calib_80, fold_records).
    Candidate C is reference-only; used only to establish the NLL floor."""
    import statsmodels.api as sm

    seasons = sorted(df["game_year"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [C] NegBin GLM: {len(folds)} folds (NLL floor reference)")

    all_mu: list[float] = []
    all_y:  list[float] = []
    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
        X_tr_sm = sm.add_constant(X_tr)
        X_te_sm = sm.add_constant(X_te)

        try:
            glm    = sm.NegativeBinomial(y_tr, X_tr_sm)
            result = glm.fit(disp=False, maxiter=200, method="nm")
            mu_te  = np.clip(result.predict(X_te_sm), _MIN_MU, None)
            # statsmodels NegBin: last param is alpha (overdispersion); r = 1/alpha
            alpha_val = float(result.params.iloc[-1])
            r = 1.0 / max(alpha_val, 1e-6)
        except Exception as exc:
            print(f"    [C] GLM fit failed (test={test_season}): {exc} — using mean fallback")
            mu_te = np.full(len(y_te), float(np.clip(y_tr.mean(), _MIN_MU, None)))
            r = _fit_negbin_r(y_te, mu_te)

        rec = _fold_record(
            len(fold_records) + 1, list(train_seasons), test_season, y_tr, y_te, mu_te, r
        )
        fold_records.append(rec)
        all_mu.extend(mu_te.tolist())
        all_y.extend(y_te.tolist())
        print(
            f"    fold {rec['fold']} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  r={rec['negbin_r']:.3f}  std_pred={rec['std_pred']:.3f}"
        )

    all_mu_arr = np.array(all_mu)
    all_y_arr  = np.array(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([f["nll"] for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"] for f in fold_records]))
    std_pred   = float(np.std(all_mu_arr))
    calib_80   = _negbin_80pct_calibration(all_y_arr, all_mu_arr, global_r)

    return mean_nll, mean_mae, std_pred, calib_80, fold_records


# ---------------------------------------------------------------------------
# Optuna hyperparameter tuning
# ---------------------------------------------------------------------------

def _make_optuna_objective(winner_type: str, df: pd.DataFrame):
    """Return an Optuna objective function for the given winner architecture."""
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seasons = sorted(df["game_year"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    def objective(trial) -> float:
        if winner_type == "ridge":
            alpha = trial.suggest_float("alpha", 1e-3, 1e4, log=True)
            fold_nlls = []
            for train_seasons, test_season in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
                pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
                pipe.fit(X_tr, y_tr)
                mu_tr = np.clip(pipe.predict(X_tr), _MIN_MU, None)
                mu_te = np.clip(pipe.predict(X_te), _MIN_MU, None)
                r = _fit_negbin_r(y_tr, mu_tr)
                fold_nlls.append(_negbin_nll(y_te, mu_te, r))
            return float(np.mean(fold_nlls))
        else:  # ngboost
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            n_estimators   = trial.suggest_int("n_estimators", 200, 1000, step=100)
            learning_rate  = trial.suggest_float("learning_rate", 0.005, 0.1, log=True)
            minibatch_frac = trial.suggest_float("minibatch_frac", 0.5, 1.0)
            fold_nlls = []
            for train_seasons, test_season in folds:
                X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
                ngb = NGBRegressor(
                    Dist=Normal,
                    n_estimators=n_estimators,
                    learning_rate=learning_rate,
                    minibatch_frac=minibatch_frac,
                    random_state=_OPTUNA_SEED,
                    verbose=False,
                )
                ngb.fit(X_tr, y_tr)
                mu_tr = np.clip(ngb.predict(X_tr), _MIN_MU, None)
                mu_te = np.clip(ngb.predict(X_te), _MIN_MU, None)
                r = _fit_negbin_r(y_tr, mu_tr)
                fold_nlls.append(_negbin_nll(y_te, mu_te, r))
            return float(np.mean(fold_nlls))

    return objective


def _tune_winner(
    winner_type: str,
    df: pd.DataFrame,
    initial_nll: float,
) -> tuple[dict, float]:
    """Tune the winning architecture with Optuna. Returns (best_params, best_nll).

    Protocol (Sub-model output standard):
      Phase 1: n_trials=_OPTUNA_PROBE_TRIALS — feasibility check
      Phase 2: n_trials=_OPTUNA_FULL_TRIALS  — always runs (rigorous pass)
    """
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_optuna_objective(winner_type, df)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    # Seed study with the known-good params from comparison phase
    if winner_type == "ridge":
        pass  # best alpha from grid will be found by TPE naturally
    # (NGBoost defaults are included via normal trial space sampling)

    print(
        f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE_TRIALS} trials), "
        f"objective=mean CV NLL, initial NLL={initial_nll:.4f}"
    )
    study.optimize(objective, n_trials=_OPTUNA_PROBE_TRIALS, show_progress_bar=False)
    probe_best = study.best_value
    probe_delta = initial_nll - probe_best
    print(
        f"[Optuna] Probe best NLL: {probe_best:.4f}  "
        f"(Δ vs initial: {probe_delta:+.4f})"
    )

    print(f"[Optuna] Phase 2 — full pass ({_OPTUNA_FULL_TRIALS} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL_TRIALS, show_progress_bar=False)

    best_params = study.best_params
    best_nll    = study.best_value
    full_delta  = initial_nll - best_nll
    print(f"[Optuna] Best params: {best_params}")
    print(f"[Optuna] Best NLL:    {best_nll:.4f}  (Δ vs initial: {full_delta:+.4f})")
    return best_params, best_nll


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _print_fold_table(label: str, fold_records: list[dict]) -> None:
    print(f"\n── {label} walk-forward CV ──────────────────────────────────────────────")
    print(f"  {'Fold':>4}  {'Train':>12}  {'Test':>6}  {'NLL':>7}  {'MAE':>6}  "
          f"{'Calib80':>8}  {'r':>6}  {'std_pred':>9}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>12}  {r['test_season']:>6}  "
            f"{r['nll']:>7.4f}  {r['mae']:>6.3f}  {r['calib_80']:>8.4f}  "
            f"{r['negbin_r']:>6.3f}  {r['std_pred']:>9.4f}"
        )
    print(
        f"  {'Mean':>4}  {'':>12}  {'':>6}  "
        f"{np.mean([f['nll'] for f in fold_records]):>7.4f}  "
        f"{np.mean([f['mae'] for f in fold_records]):>6.3f}  "
        f"{np.mean([f['calib_80'] for f in fold_records]):>8.4f}  "
        f"{np.mean([f['negbin_r'] for f in fold_records]):>6.3f}  "
        f"{np.mean([f['std_pred'] for f in fold_records]):>9.4f}"
    )


def _print_gate_summary(
    a_nll: float, a_mae: float, a_std: float, a_calib: float,
    b_nll: float, b_mae: float, b_std: float, b_calib: float,
    c_nll: float,
) -> tuple[str, float]:
    """Print gate evaluation table. Returns (winner_type, winner_nll).

    winner_type is 'ngboost', 'ridge', or 'none'.
    Gates: NLL < GLM floor, calib_80 ≥ _CALIB_80_GATE, MAE ≤ _V3_CV_MAE + _MAE_TOLERANCE.
    std(pred) is intentionally excluded — calib_80 supersedes it for distributional models.
    """
    mae_threshold = _V3_CV_MAE + _MAE_TOLERANCE
    mae_label = f"MAE (≤ {mae_threshold:.4f})"
    cal_label = f"calib_80 (≥ {_CALIB_80_GATE})"
    nll_label = "NLL (< GLM floor)"

    def gate(val: float, threshold: float, lower_is_better: bool = True) -> str:
        passes = (val < threshold) if lower_is_better else (val >= threshold)
        return "PASS" if passes else "FAIL"

    w = 26
    print("\n" + "=" * 82)
    print("run_env_v4 head-to-head: Cand A (NGBoost) | Cand B (Ridge) | Ref C (GLM floor)")
    print(f"  [std(pred) not a gate for distributional models — calib_80 supersedes it]")
    print("=" * 82)
    print(f"  {'Gate':<{w}}  {'Cand A (NGBoost)':>20}  {'Cand B (Ridge)':>16}  {'Ref C (GLM)':>12}")
    print(f"  {'-'*w}  {'-'*20}  {'-'*16}  {'-'*12}")
    print(
        f"  {nll_label:<{w}}  "
        f"{a_nll:>14.4f} {gate(a_nll, c_nll):>5}  "
        f"{b_nll:>10.4f} {gate(b_nll, c_nll):>5}  "
        f"{c_nll:>12.4f}"
    )
    print(
        f"  {cal_label:<{w}}  "
        f"{a_calib:>14.4f} {gate(a_calib, _CALIB_80_GATE, lower_is_better=False):>5}  "
        f"{b_calib:>10.4f} {gate(b_calib, _CALIB_80_GATE, lower_is_better=False):>5}  "
        f"{'N/A':>12}"
    )
    print(
        f"  {mae_label:<{w}}  "
        f"{a_mae:>14.4f} {gate(a_mae, mae_threshold):>5}  "
        f"{b_mae:>10.4f} {gate(b_mae, mae_threshold):>5}  "
        f"{'N/A':>12}"
    )
    print(f"  {'std(pred) [info only]':<{w}}  {a_std:>20.4f}  {b_std:>16.4f}  {'N/A':>12}")
    print("=" * 82)

    a_passes = (a_nll < c_nll) and (a_calib >= _CALIB_80_GATE) and (a_mae <= mae_threshold)
    b_passes = (b_nll < c_nll) and (b_calib >= _CALIB_80_GATE) and (b_mae <= mae_threshold)

    if not a_passes and not b_passes:
        print("\n  Neither candidate passes all gates. run_env_v3 remains champion.")
        return "none", min(a_nll, b_nll)
    elif a_passes and not b_passes:
        print(f"\n  Winner: Candidate A — NGBoost+NegBin (NLL {a_nll:.4f})")
        return "ngboost", a_nll
    elif b_passes and not a_passes:
        print(f"\n  Winner: Candidate B — Ridge+NegBin (NLL {b_nll:.4f})")
        return "ridge", b_nll
    else:
        if a_nll <= b_nll:
            print(f"\n  Both pass — Winner: Candidate A NGBoost (NLL {a_nll:.4f} ≤ Ridge {b_nll:.4f})")
            return "ngboost", a_nll
        else:
            print(f"\n  Both pass — Winner: Candidate B Ridge+NegBin (NLL {b_nll:.4f} < NGBoost {a_nll:.4f})")
            return "ridge", b_nll


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def _update_registry(
    cv_nll: float,
    cv_mae: float,
    negbin_r: float,
    model_type: str,
    gate_passed: bool,
    mlflow_run_id: str | None = None,
) -> None:
    import datetime
    text = _REGISTRY_PATH.read_text()

    if gate_passed:
        # Deprecate v3 on promotion
        text = re.sub(
            r"(run_env_v3:.*?promotion_status:)\s*\S+",
            r"\1 deprecated",
            text, count=1, flags=re.DOTALL,
        )

    arch_label = "NGBoost+NegBin" if model_type == "ngboost" else "Ridge+NegBin"
    today = datetime.date.today().isoformat()
    v4_status = "champion" if gate_passed else "challenger"
    promoted_at_str = f"'{today}'" if gate_passed else "null"
    mlflow_line = mlflow_run_id or "null"
    gate_note = (
        f"Promoted to champion — {arch_label} CV NLL {cv_nll:.4f} beats GLM floor; "
        f"all gates pass."
        if gate_passed
        else f"Challenger — gates not all cleared (CV NLL {cv_nll:.4f})."
    )

    new_block = f"""run_env_v4:
  artifact_path: {_ARTIFACT_S3_URI}
  feature_columns_path: models/sub_models/run_env_v3_features.json
  mlflow_run_id: {mlflow_line}
  target:
    source_table: baseball_data.betting.mart_game_results
    primary_column: home_final_score + away_final_score
    auxiliary_columns: []
    grain: game_pk
  training_window:
    start: '2021-01-01'
    end: null
  cv_strategy: walk_forward
  cv_metric: negbin_nll
  cv_score: {cv_nll}
  cv_mae: {cv_mae}
  negbin_r: {negbin_r}
  promotion_gate:
    metric: negbin_nll
    direction: lower_is_better
    must_beat: candidate_c_glm_nll
    secondary:
      - calib_80_ge: {_CALIB_80_GATE}
      - mae_le: {round(_V3_CV_MAE + _MAE_TOLERANCE, 4)}
  parent_features:
    - feature_pregame_park_features
    - feature_pregame_weather_features
    - feature_pregame_umpire_features
  output_signals:
    - run_env_mu
    - run_env_dispersion
    - run_env_signal
    - uncertainty
  downstream_consumers: []
  promotion_status: {v4_status}
  promoted_at: {promoted_at_str}
  notes: |
    Story 3D.1 / 3D.2 (Epic 3D). Distributional NegBin retrofit of run_env_v3.
    Same 19-feature matrix and walk-forward CV folds as v3. Three candidates:
      A — NGBoost Normal mean + NegBin r from residuals
      B — Ridge+NegBin (v3 architecture, alpha re-selected on NLL)
      C — NegBin GLM (statsmodels NB2) — NLL floor reference only
    Winner: {arch_label}. CV NLL {cv_nll:.4f}, CV MAE {cv_mae:.4f}.
    Trained {today}. {gate_note}
"""

    pattern = r"^run_env_v4:.*?(?=^\S|\Z)"
    replacement = new_block + "\n"
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if new_text == text:
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [WARN] run_env_v4 block not found in registry; appended.")

    _REGISTRY_PATH.write_text(new_text)
    v3_outcome = "deprecated" if gate_passed else "unchanged"
    print(f"\nRegistry updated: run_env_v4={v4_status}, run_env_v3={v3_outcome}")


# ---------------------------------------------------------------------------
# Training orchestration
# ---------------------------------------------------------------------------

def train(
    promote: bool = True,
    force_winner: str | None = None,
    refresh_cache: bool = False,
) -> str:
    """Run full run_env_v4 training pipeline. Returns the MLflow run ID."""
    from betting_ml.utils.artifact_store import upload_artifact

    print(f"\nLoading training data (2021-01-01 → latest)...")
    df = get_cached_df(
        cache_key="run_env_training",
        pull_fn=load_training_data,
        max_age_hours=24,
        refresh=refresh_cache,
    )
    print(f"Loaded {len(df):,} rows across {df['game_year'].nunique()} seasons.")
    validate_no_leakage(df)

    print("\n" + "=" * 72)
    print("TRAINING run_env_v4 — Distributional NegBin (Epic 3D)")
    print(f"Baseline MAE to preserve:  run_env_v3 MAE = {_V3_CV_MAE}")
    print(f"Feature set: {len(FEATURE_COLS_V3)} features (identical to v3)")
    print(f"Gates: NLL < GLM floor | calib_80 ≥ {_CALIB_80_GATE} | MAE ≤ {_V3_CV_MAE + _MAE_TOLERANCE:.4f}  [std(pred) informational only]")
    print("=" * 72)

    mlflow.set_experiment("run_env_v4")
    get_or_create_experiment("run_env_v4")

    with mlflow.start_run(run_name=f"3D_comparison_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id

        mlflow.log_params({
            "train_start": "2021-01-01",
            "n_rows": len(df),
            "n_seasons": int(df["game_year"].nunique()),
            "n_features": len(FEATURE_COLS_V3),
            "ngboost_n_est_default": _NGBOOST_N_EST,
            "ngboost_lr_default": _NGBOOST_LR,
            "v3_cv_mae_baseline": _V3_CV_MAE,
            "mae_tolerance": _MAE_TOLERANCE,
            "calib_80_gate": _CALIB_80_GATE,
            "optuna_probe_trials": _OPTUNA_PROBE_TRIALS,
            "optuna_full_trials": _OPTUNA_FULL_TRIALS,
            "force_winner": str(force_winner),
            "promote": promote,
        })

        # ── Candidate A: NGBoost ───────────────────────────────────────────
        print("\n[1/3] Candidate A — NGBoost mean + NegBin r from residuals")
        a_nll, a_mae, a_std, a_calib, a_folds = _walk_forward_cv_ngboost(df)
        _print_fold_table("Candidate A (NGBoost+NegBin)", a_folds)

        mlflow.log_metrics({
            "cand_a_cv_nll": a_nll,
            "cand_a_cv_mae": a_mae,
            "cand_a_std_pred": a_std,
            "cand_a_calib_80": a_calib,
        })
        for rec in a_folds:
            log_cv_fold(rec["fold"], rec["test_season"], {
                "a_nll": rec["nll"],
                "a_mae": rec["mae"],
                "a_calib_80": rec["calib_80"],
                "a_negbin_r": rec["negbin_r"],
                "a_std_pred": rec["std_pred"],
            })

        # ── Candidate B: Ridge + NegBin ────────────────────────────────────
        print("\n[2/3] Candidate B — Ridge v3 mean + NegBin r from residuals")
        b_nll, b_mae, b_std, b_calib, b_folds, ridge_best_alpha = _walk_forward_cv_ridge_negbin(df)
        _print_fold_table("Candidate B (Ridge+NegBin)", b_folds)

        mlflow.log_metrics({
            "cand_b_cv_nll": b_nll,
            "cand_b_cv_mae": b_mae,
            "cand_b_std_pred": b_std,
            "cand_b_calib_80": b_calib,
            "cand_b_ridge_alpha": ridge_best_alpha,
        })
        for rec in b_folds:
            log_cv_fold(rec["fold"], rec["test_season"], {
                "b_nll": rec["nll"],
                "b_mae": rec["mae"],
                "b_calib_80": rec["calib_80"],
                "b_negbin_r": rec["negbin_r"],
                "b_std_pred": rec["std_pred"],
            })

        # ── Candidate C: NegBin GLM (floor reference) ──────────────────────
        print("\n[3/3] Candidate C — NegBin GLM (NLL floor reference, not promotable)")
        c_nll, c_mae, c_std, c_calib, c_folds = _walk_forward_cv_glm(df)
        _print_fold_table("Candidate C (NegBin GLM — reference)", c_folds)

        mlflow.log_metrics({
            "cand_c_cv_nll": c_nll,
            "cand_c_cv_mae": c_mae,
            "cand_c_std_pred": c_std,
            "cand_c_calib_80": c_calib,
        })

        # ── Selection ──────────────────────────────────────────────────────
        winner_type, winner_nll = _print_gate_summary(
            a_nll, a_mae, a_std, a_calib,
            b_nll, b_mae, b_std, b_calib,
            c_nll,
        )
        gate_passed = winner_type != "none"

        if force_winner is not None:
            winner_type = force_winner
            winner_nll  = a_nll if force_winner == "ngboost" else b_nll
            winner_mae  = a_mae if force_winner == "ngboost" else b_mae
            gate_passed = True
            print(f"\n[--force-winner {force_winner}] Overriding gate-based selection.")
        else:
            winner_mae = a_mae if winner_type == "ngboost" else b_mae

        if not promote:
            gate_passed = False
            if force_winner is None and winner_type == "none":
                winner_type = "ngboost" if a_nll <= b_nll else "ridge"
                winner_mae  = a_mae if winner_type == "ngboost" else b_mae
                winner_nll  = a_nll if winner_type == "ngboost" else b_nll
            print("\n[--no-promote] Registry update and S3 upload suppressed.")

        mlflow.log_params({"winner_type": winner_type, "gate_passed": gate_passed})
        mlflow.log_metrics({"winner_cv_nll": winner_nll, "winner_cv_mae": winner_mae})

        # ── Optuna tuning of winner ────────────────────────────────────────
        print(f"\n{'='*72}")
        print(f"Optuna hyperparameter tuning — winner: {winner_type.upper()}")
        print(f"{'='*72}")
        tuned_params, tuned_nll = _tune_winner(winner_type, df, winner_nll)
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # Extract tuned values (fall back to comparison-phase defaults if key absent)
        if winner_type == "ngboost":
            final_n_est        = tuned_params.get("n_estimators", _NGBOOST_N_EST)
            final_lr           = tuned_params.get("learning_rate", _NGBOOST_LR)
            final_mbfrac       = tuned_params.get("minibatch_frac", 1.0)
        else:
            final_ridge_alpha  = tuned_params.get("alpha", ridge_best_alpha)

        # ── Final model: train on all data with tuned params ───────────────
        print(f"\nTraining final {winner_type.upper()} model on all {len(df):,} rows...")
        seasons_all       = sorted(df["game_year"].unique())
        prior_season_runs = _compute_prior_season_runs(df)
        df_era            = _add_era_features(df, prior_season_runs)
        impute_vals       = _compute_impute_values_v3(df_era)
        df_imp            = _apply_imputation_v3(df_era, impute_vals)
        X_all = df_imp[FEATURE_COLS_V3].to_numpy(dtype=float)
        y_all = df_imp["total_runs"].to_numpy(dtype=float)

        if winner_type == "ngboost":
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            print(f"  Tuned params: n_estimators={final_n_est}, lr={final_lr:.5f}, minibatch_frac={final_mbfrac:.3f}")
            final_model = NGBRegressor(
                Dist=Normal,
                n_estimators=final_n_est,
                learning_rate=final_lr,
                minibatch_frac=final_mbfrac,
                random_state=_OPTUNA_SEED,
                verbose=False,
            )
            final_model.fit(X_all, y_all)
            mu_all  = np.clip(final_model.predict(X_all), _MIN_MU, None)
            winner_folds = a_folds
        else:
            from sklearn.linear_model import Ridge
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import StandardScaler
            print(f"  Tuned params: alpha={final_ridge_alpha:.4f}")
            final_model = Pipeline([
                ("scaler", StandardScaler()),
                ("ridge", Ridge(alpha=final_ridge_alpha)),
            ])
            final_model.fit(X_all, y_all)
            mu_all  = np.clip(final_model.predict(X_all), _MIN_MU, None)
            winner_folds = b_folds

        global_r = _fit_negbin_r(y_all, mu_all)
        in_sample_nll = _negbin_nll(y_all, mu_all, global_r)
        in_sample_mae = float(np.mean(np.abs(mu_all - y_all)))

        print(f"  In-sample NLL:         {in_sample_nll:.4f}")
        print(f"  In-sample MAE:         {in_sample_mae:.4f}")
        print(f"  Walk-forward CV NLL:   {winner_nll:.4f}")
        print(f"  Walk-forward CV MAE:   {winner_mae:.4f}")
        print(f"  Fitted NegBin r:       {global_r:.4f}  (dispersion; larger = less overdispersion)")
        print(f"  mu std (training):     {float(np.std(mu_all)):.4f}")

        mlflow.log_metrics({
            "final_insample_nll": in_sample_nll,
            "final_insample_mae": in_sample_mae,
            "final_negbin_r": global_r,
        })

        # ── Save artifact ──────────────────────────────────────────────────
        artifact = {
            "model":             final_model,
            "model_type":        winner_type,
            "negbin_r":          global_r,
            "feature_cols":      FEATURE_COLS_V3,
            "impute_values":     impute_vals,
            "prior_season_runs": prior_season_runs,
            "target_mean":       float(y_all.mean()),
            "target_std":        float(y_all.std()),
            "min_mu":            _MIN_MU,
            # CV metrics (comparison phase, pre-tuning)
            "cv_nll":            winner_nll,
            "cv_mae":            winner_mae,
            # Optuna tuning results
            "tuned_params":      tuned_params,
            "tuned_cv_nll":      tuned_nll,
            # All candidate results
            "cand_a_cv_nll":     a_nll,
            "cand_a_cv_mae":     a_mae,
            "cand_a_std_pred":   a_std,
            "cand_a_calib_80":   a_calib,
            "cand_b_cv_nll":     b_nll,
            "cand_b_cv_mae":     b_mae,
            "cand_b_std_pred":   b_std,
            "cand_b_calib_80":   b_calib,
            "cand_b_ridge_alpha": ridge_best_alpha,
            "cand_c_cv_nll":     c_nll,
            "cv_fold_records":   winner_folds,
        }

        _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, _ARTIFACT_PATH)
        print(f"\nArtifact saved → {_ARTIFACT_PATH}")

        if promote:
            upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)

        mlflow.log_artifact(str(_ARTIFACT_PATH))
        mlflow.set_tag("sub_model_registry_key", "run_env_v4")
        print(f"  MLflow run_id: {mlflow_run_id}")

        # ── Registry ───────────────────────────────────────────────────────
        if promote:
            _update_registry(
                cv_nll=winner_nll,
                cv_mae=winner_mae,
                negbin_r=global_r,
                model_type=winner_type,
                gate_passed=gate_passed,
                mlflow_run_id=mlflow_run_id,
            )

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    arch_label = "NGBoost+NegBin" if winner_type == "ngboost" else "Ridge+NegBin"
    if gate_passed:
        print(
            f"run_env_v4 result: PROMOTED ({arch_label}, "
            f"CV NLL {winner_nll:.4f} < GLM {c_nll:.4f}, "
            f"CV MAE {winner_mae:.4f})"
        )
        print("\nNext steps (Story 3D.3):")
        print("  1. Update generate_run_env_signals.py to load run_env_v4.pkl")
        print("     and emit run_env_mu, run_env_dispersion, run_env_signal (z-score), uncertainty")
        print("  2. Backfill 2021–2026, verify idempotent via record_hash")
        print("  3. dbtf build --select feature_pregame_sub_model_signals")
    else:
        print(f"run_env_v4 result: NOT PROMOTED (run_env_v3 remains champion)")
        print(f"  Best candidate: {arch_label}, CV NLL {winner_nll:.4f}, MAE {winner_mae:.4f}")
        print(f"  GLM floor NLL:  {c_nll:.4f}")
    print(f"\n=== DONE — MLflow run: {mlflow_run_id} (run `mlflow ui` to browse) ===")
    print("=" * 72)
    return mlflow_run_id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train run_env_v4 — distributional NegBin run environment model (Epic 3D)"
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Run CV and save artifact locally but skip S3 upload and registry update.",
    )
    parser.add_argument(
        "--force-winner",
        choices=["ngboost", "ridge"],
        default=None,
        metavar="{ngboost,ridge}",
        help=(
            "Override gate-based selection. Trains the specified architecture "
            "and promotes it regardless of gate outcomes. Implies gate_passed=True."
        ),
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Bypass local Parquet cache and re-pull training data from Snowflake.",
    )
    args = parser.parse_args()
    train(
        promote=not args.no_promote,
        force_winner=args.force_winner,
        refresh_cache=args.refresh_cache,
    )


if __name__ == "__main__":
    main()
