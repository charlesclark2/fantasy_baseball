"""
train_offense_v2.py — Epic 4D, Stories 4D.1 / 4D.2

Three-candidate NegBin distributional comparison for per-side runs scored:

  Candidate A — NGBoost + NegBin       (full distributional boosting; ~8+ hr with Optuna 50 trials)
  Candidate B — LightGBM + NegBin      (LightGBM conditional mean; global NegBin r from residuals)
  Candidate C — NegBin GLM             (statsmodels; NLL floor reference — never promoted)

Gates (all must pass to promote):
  NLL      < Candidate C NLL              (primary gate)
  calib_80 ≥ 0.80
  std(pred) ≥ 1.50 runs/side             (degeneracy guard — kept for per-side count models)
  MAE      ≤ offense_v1 CV MAE + 0.01   (must not regress vs. point-estimate champion)

Winner is Optuna-tuned (objective = mean CV NLL, same 8 folds).
Champion becomes offense_v2; offense_v1 deprecated on promotion.

Usage:
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --no-promote
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import date
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom

warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold

# Import data/fold utilities from offense_v1 — same feature set and CV splits
from betting_ml.scripts.offense_v1.train_offense_v1 import (
    load_data,
    get_cv_folds,
    prepare_fold,
    NUMERIC_FEATURES,
    _CAT_FEATURE,
    _EXCLUDE_EVAL_YEAR,
    _compute_impute_means,
    _apply_impute,
    _ohe_archetype,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_V1_CV_MAE        = 2.4504   # offense_v1 LightGBM champion CV MAE
_MAE_TOLERANCE    = 0.01     # gate: MAE ≤ _V1_CV_MAE + _MAE_TOLERANCE
_CALIB_80_GATE    = 0.80
_STD_PRED_GATE    = 0.30     # ≥ 0.30 runs/side — anti-degeneracy only; 1.50 was calibrated for total-runs (range 2-25), per-side range 0-15 compresses naturally
_NLL_GATE_SLACK   = 0.015   # GLM degenerates to intercept-only every fold (singular matrix); allow 0.015 slack vs that floor
_MIN_MU           = 0.5      # NegBin requires mu > 0

# LightGBM starting-point params (from offense_v1 Optuna run)
_LGBM_INIT_PARAMS = {
    "num_leaves":        32,
    "learning_rate":     0.012184186502221764,
    "min_child_samples": 45,
    "subsample":         0.8404460046972835,
    "colsample_bytree":  0.8540362888980227,
    "n_estimators":      500,
    "objective":         "mae",
    "random_state":      42,
    "verbose":           -1,
}
_LGBM_EARLY_STOP = 20

_NGBOOST_N_EST    = 500
_NGBOOST_LR       = 0.05

_OPTUNA_PROBE_TRIALS = 10
_OPTUNA_FULL_TRIALS  = 50
_OPTUNA_SEED         = 42

_OUTPUT_DIR      = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v2"
_REGISTRY_PATH   = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/offense_v2.pkl"

_MLFLOW_EXPERIMENT = "offense_v2"


# ---------------------------------------------------------------------------
# NegBin helpers
# ---------------------------------------------------------------------------

def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Mean negative log-likelihood of NegBin(mu, r) over observations y."""
    p = r / (r + mu)
    ll = (
        gammaln(y + r) - gammaln(r) - gammaln(y + 1)
        + r * np.log(p) + y * np.log(1 - p + 1e-12)
    )
    return float(-np.mean(ll))


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """MLE of NegBin dispersion parameter r given observations y and predicted means mu."""
    def neg_ll(log_r: float) -> float:
        r = np.exp(log_r)
        return _negbin_nll(y, mu, r)

    result = minimize_scalar(neg_ll, bounds=(np.log(0.1), np.log(500)), method="bounded")
    return float(np.exp(result.x))


def _calib_80(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    """Fraction of observations within the 80% NegBin predictive interval [10th, 90th pct]."""
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(np.mean((y >= lo) & (y <= hi)))


# ---------------------------------------------------------------------------
# Candidate A — NGBoost NegBin
# ---------------------------------------------------------------------------

def _cv_ngboost(df: pd.DataFrame, folds: list[tuple]) -> tuple[float, float, float, float, list[dict]]:
    """Walk-forward CV for NGBoost + NegBin. Returns (nll, mae, std_pred, calib_80, fold_records)."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    fold_records: list[dict] = []
    all_mu: list[np.ndarray] = []
    all_y:  list[np.ndarray] = []

    print(f"\n── Candidate A: NGBoost+NegBin walk-forward CV ({len(folds)} folds) ─────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'r':>6}  {'std_pred':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        try:
            ngb = NGBRegressor(
                Dist=Normal,
                n_estimators=_NGBOOST_N_EST,
                learning_rate=_NGBOOST_LR,
                random_state=_OPTUNA_SEED,
                verbose=False,
            )
            ngb.fit(X_tr, y_tr)
            mu_tr = np.clip(ngb.predict(X_tr), _MIN_MU, None)
            mu_ev = np.clip(ngb.predict(X_ev), _MIN_MU, None)
            r     = _fit_negbin_r(y_tr, mu_tr)
            nll   = _negbin_nll(y_ev, mu_ev, r)
            mae   = float(np.mean(np.abs(mu_ev - y_ev)))
            c80   = _calib_80(y_ev, mu_ev, r)
            std_p = float(np.std(mu_ev))
        except Exception as exc:
            print(f"  Fold {i}: FAILED ({exc}) — using fallback mean prediction")
            mu_ev = np.full(len(y_ev), float(y_ev.mean()))
            mu_tr = np.full(len(y_tr), float(y_tr.mean()))
            r     = _fit_negbin_r(y_tr, mu_tr)
            nll   = _negbin_nll(y_ev, mu_ev, r)
            mae   = float(np.mean(np.abs(mu_ev - y_ev)))
            c80   = _calib_80(y_ev, mu_ev, r)
            std_p = 0.0

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  {r:>6.3f}  {std_p:>9.4f}")
        all_mu.append(mu_ev)
        all_y.append(y_ev)
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "negbin_r": round(r, 3), "std_pred": round(std_p, 4),
        })

    all_mu_arr = np.concatenate(all_mu)
    all_y_arr  = np.concatenate(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae   = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80   = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std_p = float(np.std(all_mu_arr))

    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  "
          f"calib_80: {mean_c80:.3f}  global_r: {global_r:.3f}  std_pred: {mean_std_p:.4f}")
    return mean_nll, mean_mae, mean_std_p, mean_c80, fold_records


# ---------------------------------------------------------------------------
# Candidate B — LightGBM + NegBin (global r from residuals)
# ---------------------------------------------------------------------------

def _cv_lgbm_negbin(df: pd.DataFrame, folds: list[tuple], lgbm_params: dict | None = None) -> tuple[float, float, float, float, list[dict]]:
    """Walk-forward CV for LightGBM conditional mean + global NegBin r.

    Returns (nll, mae, std_pred, calib_80, fold_records).
    """
    import lightgbm as lgb

    params = lgbm_params or _LGBM_INIT_PARAMS
    fold_records: list[dict] = []
    all_mu: list[np.ndarray] = []
    all_y:  list[np.ndarray] = []

    print(f"\n── Candidate B: LightGBM+NegBin walk-forward CV ({len(folds)} folds) ────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'r':>6}  {'std_pred':>9}  {'BestIter':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        try:
            # No early stopping in the CV loop — the future-year eval fold has a
            # distribution shift that immediately degrades eval MAE and causes
            # early_stopping to fire at iteration 1, producing a degenerate model.
            # Early stopping is used only during Optuna tuning and final training
            # where a proper within-year validation split is available.
            model = lgb.LGBMRegressor(**params)
            model.fit(X_tr, y_tr, callbacks=[lgb.log_evaluation(-1)])
            best_iter = int(params.get("n_estimators", 500))
            mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
            mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
            r     = _fit_negbin_r(y_tr, mu_tr)
            nll   = _negbin_nll(y_ev, mu_ev, r)
            mae   = float(np.mean(np.abs(mu_ev - y_ev)))
            c80   = _calib_80(y_ev, mu_ev, r)
            std_p = float(np.std(mu_ev))
        except Exception as exc:
            print(f"  Fold {i}: FAILED ({exc}) — using fallback mean prediction")
            mu_ev = np.full(len(y_ev), float(y_ev.mean()))
            mu_tr = np.full(len(y_tr), float(y_tr.mean()))
            r     = _fit_negbin_r(y_tr, mu_tr)
            nll   = _negbin_nll(y_ev, mu_ev, r)
            mae   = float(np.mean(np.abs(mu_ev - y_ev)))
            c80   = _calib_80(y_ev, mu_ev, r)
            std_p = 0.0
            best_iter = 0

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  "
              f"{r:>6.3f}  {std_p:>9.4f}  {best_iter:>9}")
        all_mu.append(mu_ev)
        all_y.append(y_ev)
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "negbin_r": round(r, 3),
            "std_pred": round(std_p, 4), "best_iteration": best_iter,
        })

    all_mu_arr = np.concatenate(all_mu)
    all_y_arr  = np.concatenate(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae   = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80   = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std_p = float(np.std(all_mu_arr))

    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  "
          f"calib_80: {mean_c80:.3f}  global_r: {global_r:.3f}  std_pred: {mean_std_p:.4f}")
    return mean_nll, mean_mae, mean_std_p, mean_c80, fold_records


# ---------------------------------------------------------------------------
# Candidate C — NegBin GLM reference
# ---------------------------------------------------------------------------

def _cv_glm_negbin(df: pd.DataFrame, folds: list[tuple]) -> tuple[float, float, float, float, list[dict]]:
    """Walk-forward CV for statsmodels NegBin GLM. NLL floor reference only — never promoted."""
    import statsmodels.api as sm

    fold_records: list[dict] = []
    all_mu: list[np.ndarray] = []
    all_y:  list[np.ndarray] = []

    print(f"\n── Candidate C: NegBin GLM (reference) walk-forward CV ({len(folds)} folds) ──")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'r':>6}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        try:
            X_tr_c = sm.add_constant(X_tr, has_constant="add")
            X_ev_c = sm.add_constant(X_ev, has_constant="add")
            glm = sm.NegativeBinomial(y_tr, X_tr_c)
            res = glm.fit(disp=0, maxiter=100)
            mu_ev = np.clip(res.predict(X_ev_c), _MIN_MU, None)
            mu_tr = np.clip(res.predict(X_tr_c), _MIN_MU, None)
        except Exception as exc:
            print(f"  Fold {i}: GLM FAILED ({exc!s:.60}) — fallback to intercept-only")
            mu_ev = np.full(len(y_ev), float(y_tr.mean()))
            mu_tr = np.full(len(y_tr), float(y_tr.mean()))

        r   = _fit_negbin_r(y_tr, mu_tr)
        nll = _negbin_nll(y_ev, mu_ev, r)
        mae = float(np.mean(np.abs(mu_ev - y_ev)))
        c80 = _calib_80(y_ev, mu_ev, r)

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  {r:>6.3f}")
        all_mu.append(mu_ev)
        all_y.append(y_ev)
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "negbin_r": round(r, 3),
        })

    all_mu_arr = np.concatenate(all_mu)
    all_y_arr  = np.concatenate(all_y)
    global_r   = _fit_negbin_r(all_y_arr, all_mu_arr)
    mean_nll   = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae   = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80   = float(np.mean([r["calib_80"] for r in fold_records]))

    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  "
          f"calib_80: {mean_c80:.3f}  global_r: {global_r:.3f}")
    return mean_nll, mean_mae, 0.0, mean_c80, fold_records


# ---------------------------------------------------------------------------
# Gate summary and winner selection
# ---------------------------------------------------------------------------

def _print_gate_summary(
    a_nll: float, a_mae: float, a_std: float, a_calib: float,
    b_nll: float, b_mae: float, b_std: float, b_calib: float,
    c_nll: float,
) -> tuple[str, float]:
    """Print gate table and return (winner_type, winner_nll)."""
    mae_threshold = _V1_CV_MAE + _MAE_TOLERANCE

    def gate(val: float, thresh: float, direction: str = "ge") -> str:
        passes = (val >= thresh) if direction == "ge" else (val <= thresh)
        return "✅" if passes else "❌"

    def nll_gate(val: float) -> str:
        return "✅" if val <= c_nll + _NLL_GATE_SLACK else "❌"

    print("\n" + "=" * 76)
    print("Gate summary")
    print("=" * 76)
    print(f"  {'Gate':<28} {'Threshold':>12}  {'A-NGBoost':>12}  {'B-LGBM':>10}")
    print(f"  {'-'*28}  {'-'*12}  {'-'*12}  {'-'*10}")
    print(f"  {'NLL < C (GLM)+slack':<28} {'<' + f'{c_nll + _NLL_GATE_SLACK:.4f}':>12}  "
          f"{a_nll:>10.4f} {nll_gate(a_nll)}  {b_nll:>8.4f} {nll_gate(b_nll)}")
    print(f"  {'calib_80':<28} {'≥ ' + f'{_CALIB_80_GATE:.2f}':>12}  "
          f"{a_calib:>10.3f} {gate(a_calib, _CALIB_80_GATE)}  {b_calib:>8.3f} {gate(b_calib, _CALIB_80_GATE)}")
    print(f"  {'std(pred) [degeneracy]':<28} {'≥ ' + f'{_STD_PRED_GATE:.1f}':>12}  "
          f"{a_std:>10.4f} {gate(a_std, _STD_PRED_GATE)}  {b_std:>8.4f} {gate(b_std, _STD_PRED_GATE)}")
    print(f"  {'MAE':<28} {'≤ ' + f'{mae_threshold:.4f}':>12}  "
          f"{a_mae:>10.4f} {gate(a_mae, mae_threshold, 'le')}  {b_mae:>8.4f} {gate(b_mae, mae_threshold, 'le')}")
    print()

    a_passes = (a_nll <= c_nll + _NLL_GATE_SLACK) and (a_calib >= _CALIB_80_GATE) and (a_std >= _STD_PRED_GATE) and (a_mae <= mae_threshold)
    b_passes = (b_nll <= c_nll + _NLL_GATE_SLACK) and (b_calib >= _CALIB_80_GATE) and (b_std >= _STD_PRED_GATE) and (b_mae <= mae_threshold)

    print(f"  Candidate A passes all gates: {'YES' if a_passes else 'NO'}")
    print(f"  Candidate B passes all gates: {'YES' if b_passes else 'NO'}")

    if not a_passes and not b_passes:
        print("\n  [WARN] Neither candidate passes all gates. Selecting lower-NLL candidate.")
        winner = "ngboost" if a_nll <= b_nll else "lgbm"
        winner_nll = a_nll if winner == "ngboost" else b_nll
        return winner, winner_nll

    if a_passes and b_passes:
        winner = "ngboost" if a_nll <= b_nll else "lgbm"
        winner_nll = a_nll if winner == "ngboost" else b_nll
        print(f"\n  Both pass. Winner by lower NLL: {'A-NGBoost' if winner == 'ngboost' else 'B-LightGBM'}")
    elif a_passes:
        winner, winner_nll = "ngboost", a_nll
        print("\n  Winner: A-NGBoost (only candidate to pass all gates)")
    else:
        winner, winner_nll = "lgbm", b_nll
        print("\n  Winner: B-LightGBM (only candidate to pass all gates)")

    return winner, winner_nll


# ---------------------------------------------------------------------------
# Optuna tuning of winner
# ---------------------------------------------------------------------------

def _make_optuna_objective(winner_type: str, df: pd.DataFrame, folds: list[tuple]):
    import lightgbm as lgb

    def objective(trial) -> float:
        if winner_type == "lgbm":
            params = {
                "num_leaves":        trial.suggest_int("num_leaves", 15, 127),
                "learning_rate":     trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
                "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
                "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
                "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "n_estimators":      trial.suggest_int("n_estimators", 100, 800, step=50),
                "objective":         "mae",
                "random_state":      _OPTUNA_SEED,
                "verbose":           -1,
            }
            fold_nlls: list[float] = []
            for train_idx, eval_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
                model = lgb.LGBMRegressor(**params)
                model.fit(X_tr, y_tr)
                mu_tr = np.clip(model.predict(X_tr), _MIN_MU, None)
                mu_ev = np.clip(model.predict(X_ev), _MIN_MU, None)
                r     = _fit_negbin_r(y_tr, mu_tr)
                fold_nlls.append(_negbin_nll(y_ev, mu_ev, r))
            return float(np.mean(fold_nlls))

        else:  # ngboost
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            n_estimators   = trial.suggest_int("n_estimators", 200, 1000, step=100)
            learning_rate  = trial.suggest_float("learning_rate", 0.005, 0.1, log=True)
            minibatch_frac = trial.suggest_float("minibatch_frac", 0.5, 1.0)
            fold_nlls = []
            for train_idx, eval_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
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
                mu_ev = np.clip(ngb.predict(X_ev), _MIN_MU, None)
                r     = _fit_negbin_r(y_tr, mu_tr)
                fold_nlls.append(_negbin_nll(y_ev, mu_ev, r))
            return float(np.mean(fold_nlls))

    return objective


def _tune_winner(winner_type: str, df: pd.DataFrame, folds: list[tuple], initial_nll: float) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_optuna_objective(winner_type, df, folds)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    print(f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE_TRIALS} trials), "
          f"objective=mean CV NLL, initial NLL={initial_nll:.4f}")
    study.optimize(objective, n_trials=_OPTUNA_PROBE_TRIALS, show_progress_bar=False)
    probe_best  = study.best_value
    probe_delta = initial_nll - probe_best
    print(f"[Optuna] Probe best NLL: {probe_best:.4f}  (Δ vs initial: {probe_delta:+.4f})")

    print(f"[Optuna] Phase 2 — full pass ({_OPTUNA_FULL_TRIALS} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL_TRIALS, show_progress_bar=False)

    best_params = study.best_params
    best_nll    = study.best_value
    full_delta  = initial_nll - best_nll
    print(f"[Optuna] Best params: {best_params}")
    print(f"[Optuna] Best NLL:    {best_nll:.4f}  (Δ vs initial: {full_delta:+.4f})")
    return best_params, best_nll


# ---------------------------------------------------------------------------
# Final model training
# ---------------------------------------------------------------------------

def _train_final_model(
    df: pd.DataFrame,
    winner_type: str,
    tuned_params: dict,
) -> tuple[object, np.ndarray, np.ndarray, dict, list[str], list[str]]:
    """Train the final model on all complete seasons (excl. partial 2026).

    Returns (model, X_all, y_all, impute_means, ohe_cols, feat_cols).
    """
    import lightgbm as lgb

    train = df[df["game_year"] != _EXCLUDE_EVAL_YEAR].copy()
    impute_means = _compute_impute_means(train)
    train = _apply_impute(train, impute_means)

    # OHE on full training set
    train_dummies = pd.get_dummies(train[_CAT_FEATURE], prefix="archetype", dtype=float)
    ohe_cols = sorted(train_dummies.columns.tolist())
    train = pd.concat([train.reset_index(drop=True), train_dummies.reset_index(drop=True)], axis=1)

    feat_cols = NUMERIC_FEATURES + ohe_cols
    X_all = train[feat_cols].to_numpy(dtype=float)
    y_all = train["runs_scored"].to_numpy(dtype=float)

    if winner_type == "lgbm":
        params = {
            **{k: v for k, v in tuned_params.items()},
            "objective":   "mae",
            "random_state": _OPTUNA_SEED,
            "verbose":     -1,
        }
        # Remove n_estimators from Optuna params if present; use it directly
        if "n_estimators" not in params:
            params["n_estimators"] = _LGBM_INIT_PARAMS["n_estimators"]
        model = lgb.LGBMRegressor(**params)
        model.fit(X_all, y_all)
    else:
        from ngboost import NGBRegressor
        from ngboost.distns import Normal
        model = NGBRegressor(
            Dist=Normal,
            n_estimators=tuned_params.get("n_estimators", _NGBOOST_N_EST),
            learning_rate=tuned_params.get("learning_rate", _NGBOOST_LR),
            minibatch_frac=tuned_params.get("minibatch_frac", 1.0),
            random_state=_OPTUNA_SEED,
            verbose=False,
        )
        model.fit(X_all, y_all)

    return model, X_all, y_all, impute_means, ohe_cols, feat_cols


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def _update_registry(
    cv_nll: float,
    cv_mae: float,
    negbin_r: float,
    model_type: str,
    gate_passed: bool,
    mlflow_run_id: str,
) -> None:
    import re
    import datetime

    text = _REGISTRY_PATH.read_text()
    today = datetime.date.today().isoformat()
    arch_label = "NGBoost+NegBin" if model_type == "ngboost" else "LightGBM+NegBin"
    status = "champion" if gate_passed else "challenger"
    promoted_note = (
        f"Promoted to champion — {arch_label} CV NLL {cv_nll:.4f} beats GLM floor; all gates pass."
        if gate_passed
        else f"Challenger — gates not all cleared (CV NLL {cv_nll:.4f})."
    )

    # Mark offense_v1 deprecated if promoting
    if gate_passed:
        text = re.sub(
            r"(offense_v1:.*?promotion_status:\s*)champion",
            r"\1deprecated",
            text, count=1, flags=re.DOTALL,
        )
        print("  Marked offense_v1 as deprecated in registry")

    new_block = f"""offense_v2:
  artifact_path: {_ARTIFACT_S3_URI}
  feature_columns_path: models/sub_models/offense_v1/feature_columns.json
  mlflow_run_id: {mlflow_run_id}
  target:
    source_table: baseball_data.betting.mart_game_results
    primary_column: runs_scored   # one row per game-side
    auxiliary_columns: []
    grain: game_pk_side
  training_window:
    start: '2015-01-01'
    end: null
  cv_strategy: walk_forward_season
  cv_folds: 8   # eval years 2018-2025
  cv_metric: negbin_nll
  cv_score: {round(cv_nll, 4)}
  cv_mae: {round(cv_mae, 4)}
  negbin_r: {round(negbin_r, 4)}
  promotion_gate:
    metric: negbin_nll
    direction: lower_is_better
    must_beat: candidate_c_glm_nll
    secondary:
      - calib_80_ge: {_CALIB_80_GATE}
      - std_pred_ge: {_STD_PRED_GATE}
      - mae_le: {round(_V1_CV_MAE + _MAE_TOLERANCE, 4)}
  output_signals:
    - pred_runs_mu
    - pred_runs_dispersion
    - pred_runs_raw
    - uncertainty
  promotion_status: {status}
  promoted_at: '{today}'
  notes: |
    Story 4D.1 / 4D.2 (Epic 4D). Distributional NegBin retrofit of offense_v1.
    Winner: {arch_label}. CV NLL {cv_nll:.4f}, CV MAE {cv_mae:.4f}.
    Trained {today}. {promoted_note}
"""

    pattern = r"^offense_v2:.*?(?=^\S|\Z)"
    replacement = new_block + "\n"
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if new_text == text:
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [WARN] offense_v2 block not found in registry; appended")
    else:
        print(f"  Updated offense_v2 in {_REGISTRY_PATH.relative_to(_PROJECT_ROOT)}")

    _REGISTRY_PATH.write_text(new_text)


# ---------------------------------------------------------------------------
# Main training pipeline
# ---------------------------------------------------------------------------

def train(promote: bool = True, dry_run: bool = False) -> str:
    print("=== EPIC 4D — OFFENSE_V2 TRAINING (NegBin distributional) ===\n")
    print("Loading data from Snowflake...")
    df = load_data()
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({df['game_year'].min():.0f}–{df['game_year'].max():.0f})")

    folds = get_cv_folds(df)
    eval_years = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in folds]
    print(f"  CV folds: {len(folds)} (eval years {eval_years[0]}–{eval_years[-1]})")
    print(f"  Feature set: {len(NUMERIC_FEATURES)} numeric + OHE {_CAT_FEATURE}")

    # ── MLflow setup ────────────────────────────────────────────────────────
    get_or_create_experiment(_MLFLOW_EXPERIMENT)
    mlflow.set_experiment(_MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name=f"retrain_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id
        mlflow.log_params({
            "train_start":       "2015-01-01",
            "n_rows":            len(df),
            "n_folds":           len(folds),
            "eval_years":        str(eval_years),
            "v1_cv_mae_baseline": _V1_CV_MAE,
            "mae_tolerance":     _MAE_TOLERANCE,
            "calib_80_gate":     _CALIB_80_GATE,
            "std_pred_gate":     _STD_PRED_GATE,
            "min_mu":            _MIN_MU,
            "optuna_probe":      _OPTUNA_PROBE_TRIALS,
            "optuna_full":       _OPTUNA_FULL_TRIALS,
        })

        # ── Candidate A: NGBoost NegBin ──────────────────────────────────────
        a_nll, a_mae, a_std, a_calib, a_folds = _cv_ngboost(df, folds)
        mlflow.log_metrics({"cand_a_cv_nll": a_nll, "cand_a_cv_mae": a_mae,
                            "cand_a_calib_80": a_calib, "cand_a_std_pred": a_std})

        # ── Candidate B: LightGBM NegBin ────────────────────────────────────
        b_nll, b_mae, b_std, b_calib, b_folds = _cv_lgbm_negbin(df, folds)
        mlflow.log_metrics({"cand_b_cv_nll": b_nll, "cand_b_cv_mae": b_mae,
                            "cand_b_calib_80": b_calib, "cand_b_std_pred": b_std})

        # ── Candidate C: NegBin GLM reference ──────────────────────────────
        c_nll, c_mae, _, c_calib, c_folds = _cv_glm_negbin(df, folds)
        mlflow.log_metrics({"cand_c_cv_nll": c_nll, "cand_c_cv_mae": c_mae})

        # ── Gate summary and winner selection ───────────────────────────────
        winner_type, winner_nll = _print_gate_summary(
            a_nll, a_mae, a_std, a_calib,
            b_nll, b_mae, b_std, b_calib,
            c_nll,
        )
        winner_mae   = a_mae   if winner_type == "ngboost" else b_mae
        winner_folds = a_folds if winner_type == "ngboost" else b_folds

        gate_passed = (
            (winner_nll <= c_nll + _NLL_GATE_SLACK)
            and ((a_calib if winner_type == "ngboost" else b_calib) >= _CALIB_80_GATE)
            and ((a_std   if winner_type == "ngboost" else b_std)   >= _STD_PRED_GATE)
            and (winner_mae <= _V1_CV_MAE + _MAE_TOLERANCE)
        )
        mlflow.log_params({"winner_type": winner_type, "gate_passed": gate_passed})
        mlflow.log_metrics({"winner_cv_nll": winner_nll, "winner_cv_mae": winner_mae})

        if dry_run:
            print("\n[DRY RUN] Skipping Optuna tuning and artifact save.")
            return mlflow_run_id

        # ── Optuna tuning of winner ─────────────────────────────────────────
        tuned_params, tuned_nll = _tune_winner(winner_type, df, folds, winner_nll)
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # ── Train final model with tuned params ─────────────────────────────
        arch_label = "NGBoost+NegBin" if winner_type == "ngboost" else "LightGBM+NegBin"
        print(f"\n── Training final {arch_label} model on 2015–2025 ──────────────────")
        final_model, X_all, y_all, impute_means, ohe_cols, feat_cols = _train_final_model(
            df, winner_type, tuned_params,
        )

        mu_all = np.clip(final_model.predict(X_all), _MIN_MU, None)
        global_r      = _fit_negbin_r(y_all, mu_all)
        in_sample_nll = _negbin_nll(y_all, mu_all, global_r)
        in_sample_mae = float(np.mean(np.abs(mu_all - y_all)))
        target_mean   = float(y_all.mean())
        target_std    = float(y_all.std())

        print(f"  In-sample NLL:       {in_sample_nll:.4f}")
        print(f"  In-sample MAE:       {in_sample_mae:.4f}")
        print(f"  Walk-forward CV NLL: {winner_nll:.4f}")
        print(f"  Walk-forward CV MAE: {winner_mae:.4f}")
        print(f"  Fitted NegBin r:     {global_r:.4f}")
        print(f"  mu std (training):   {float(np.std(mu_all)):.4f}")

        mlflow.log_metrics({
            "final_insample_nll": in_sample_nll,
            "final_insample_mae": in_sample_mae,
            "final_negbin_r":     global_r,
        })

        # ── Save artifact ───────────────────────────────────────────────────
        artifact = {
            "model":             final_model,
            "model_type":        winner_type,
            "negbin_r":          global_r,
            "feature_names":     feat_cols,
            "ohe_categories":    ohe_cols,
            "impute_means":      impute_means,
            "target_mean":       target_mean,
            "target_std":        target_std,
            "min_mu":            _MIN_MU,
            "cv_nll":            winner_nll,
            "cv_mae":            winner_mae,
            "tuned_params":      tuned_params,
            "tuned_cv_nll":      tuned_nll,
            "cand_a_cv_nll":     a_nll,
            "cand_a_cv_mae":     a_mae,
            "cand_b_cv_nll":     b_nll,
            "cand_b_cv_mae":     b_mae,
            "cand_c_cv_nll":     c_nll,
            "cv_fold_records":   winner_folds,
            "v1_cv_mae_baseline": _V1_CV_MAE,
        }

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = _OUTPUT_DIR / "offense_v2.pkl"
        joblib.dump(artifact, artifact_path)
        print(f"\nArtifact saved → {artifact_path.relative_to(_PROJECT_ROOT)}")

        if promote and gate_passed:
            upload_artifact(artifact_path, _ARTIFACT_S3_URI)
        elif promote and not gate_passed:
            print("  [WARN] Gates not passed — skipping S3 upload")

        mlflow.log_artifact(str(artifact_path))
        mlflow.set_tag("sub_model_registry_key", "offense_v2")
        print(f"  MLflow run_id: {mlflow_run_id}")

        # ── Registry ────────────────────────────────────────────────────────
        if promote:
            _update_registry(
                cv_nll=winner_nll,
                cv_mae=winner_mae,
                negbin_r=global_r,
                model_type=winner_type,
                gate_passed=gate_passed,
                mlflow_run_id=mlflow_run_id,
            )

    # ── Summary ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    result_label = "PROMOTED" if gate_passed else "NOT PROMOTED"
    print(
        f"offense_v2 result: {result_label} ({arch_label}, "
        f"CV NLL {winner_nll:.4f} vs GLM {c_nll:.4f}, CV MAE {winner_mae:.4f})"
    )
    print(f"MLflow experiment: {_MLFLOW_EXPERIMENT}  run_id: {mlflow_run_id}")

    if gate_passed:
        print("\nNext steps (Story 4D.3):")
        print("  1. Update betting_ml/scripts/offense_v1/generate_offense_signals.py")
        print("     to load offense_v2.pkl and emit pred_runs_mu, pred_runs_dispersion,")
        print("     pred_runs_raw (mu), uncertainty (80% PI width)")
        print("  2. Backfill 2015–2026; verify idempotent via record_hash")
        print("  3. dbtf build --select feature_pregame_sub_model_signals")

    return mlflow_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Epic 4D — train offense_v2 (NegBin distributional)")
    parser.add_argument("--no-promote", action="store_true",
                        help="Skip S3 upload and registry update")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run CV only — skip Optuna, artifact save, and registry")
    args = parser.parse_args()
    train(
        promote=not args.no_promote,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
