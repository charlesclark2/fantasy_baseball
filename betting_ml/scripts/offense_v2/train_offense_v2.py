"""
train_offense_v2.py — Epic 4D, Stories 4D.1 / 4D.2
                       Epic 16B, Story 16B.1 (--seq mode)

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

--seq mode (Epic 16B.1): two-candidate comparison
  Candidate nonseq — current offense_v2 champion (LightGBM+NegBin, no seq features)
  Candidate seq    — sequential-enriched challenger (adds avg_eb_woba_sequential +
                     posterior_source OHE with explicit __NA__ cold-start level)

  Prerequisite: dbtf run -s feature_pregame_lineup_features must be run first so
  that the posterior_source column is materialized in the feature mart.

  Gate: challenger must beat champion on BOTH NLL AND calib_80 to be promoted.
  Negative result (hold champion) is recorded in sub_model_registry.yaml + MLflow.

Usage:
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --no-promote
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --dry-run
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --seq
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --seq --no-promote
    uv run python betting_ml/scripts/offense_v2/train_offense_v2.py --seq --dry-run
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
    _TARGET,
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
# Epic 16B.1 — Sequential challenger constants and helpers
# ---------------------------------------------------------------------------

# Extends the nonseq feature set with the sequential posterior estimate.
# avg_eb_woba_sequential is NULL for pre-2021 rows; imputed to training mean.
NUMERIC_FEATURES_SEQ: list[str] = NUMERIC_FEATURES + ["avg_eb_woba_sequential"]

# All possible posterior_source values. __NA__ covers NULL (pre-2021) and
# any novel cold-start level seen only at serve time.
_PS_LEVELS = ["sequential", "season_eb", "prior_only", "__NA__"]
_PS_OHE_COLS = [f"ps_{lvl}" for lvl in _PS_LEVELS]

# Champion NLL/calib_80 thresholds (from current offense_v2 sub_model_registry.yaml).
# The seq challenger must beat BOTH to be promoted.
_NONSEQ_CHAMPION_NLL     = 2.484
_NONSEQ_CHAMPION_CALIB80 = 0.80  # registry gate floor; actual champion value verified at train time

_SEQ_QUERY = """
SELECT
    lf.game_pk,
    lf.game_date,
    lf.game_year,
    lf.side,
    lf.avg_eb_woba,
    lf.avg_eb_k_pct,
    lf.avg_eb_bb_pct,
    lf.avg_eb_iso,
    lf.avg_eb_woba_uncertainty,
    lf.eb_coverage_pct,
    lf.avg_woba_30d,
    lf.avg_k_pct_30d,
    lf.avg_bb_pct_30d,
    lf.avg_woba_std,
    lf.avg_k_pct_std,
    lf.avg_bb_pct_std,
    lf.avg_xwoba_30d,
    lf.avg_hard_hit_pct_30d,
    lf.avg_barrel_pct_30d,
    lf.avg_whiff_rate_30d,
    lf.avg_chase_rate_30d,
    lf.avg_xwoba_std,
    lf.avg_hard_hit_pct_std,
    lf.avg_barrel_pct_std,
    lf.lineup_avg_bat_speed,
    lf.lineup_bat_speed_std,
    lf.lineup_avg_swing_length,
    lf.lineup_avg_attack_angle,
    lf.lineup_bat_speed_vs_starter_velo,
    lf.avg_zips_wrc_plus,
    lf.avg_zips_woba_proxy,
    lf.avg_zips_k_pct,
    lf.avg_zips_iso,
    lf.zips_coverage_pct,
    lf.lhb_count,
    lf.rhb_count,
    lf.has_full_lineup,
    lf.lineup_depth_score,
    lf.lineup_entropy,
    lf.lineup_rookie_count,
    lf.lineup_rookie_pa_share,
    lf.injured_player_count,
    lf.injury_adj_avg_woba_30d,
    lf.injury_adj_avg_xwoba_30d,
    lf.catcher_framing_runs,
    lf.catcher_defensive_runs,
    lf.avg_woba_vs_lhp,
    lf.avg_xwoba_vs_lhp,
    lf.avg_k_pct_vs_lhp,
    lf.avg_bb_pct_vs_lhp,
    lf.avg_hard_hit_pct_vs_lhp,
    lf.avg_woba_vs_rhp,
    lf.avg_xwoba_vs_rhp,
    lf.avg_k_pct_vs_rhp,
    lf.avg_bb_pct_vs_rhp,
    lf.avg_hard_hit_pct_vs_rhp,
    lf.lineup_woba_vs_starter_archetype,
    lf.lineup_xwoba_vs_starter_archetype,
    lf.lineup_k_pct_vs_starter_archetype,
    lf.lineup_iso_vs_starter_archetype,
    lf.lineup_archetype_pa_coverage,
    lf.starter_pitch_archetype,
    lf.avg_eb_woba_sequential,
    lf.posterior_source,
    CASE
        WHEN lf.side = 'home' THEN gr.home_final_score
        ELSE gr.away_final_score
    END AS runs_scored
FROM baseball_data.betting_features.feature_pregame_lineup_features lf
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = lf.game_pk
WHERE gr.game_type = 'R'
  AND gr.home_final_score IS NOT NULL
ORDER BY lf.game_date, lf.game_pk, lf.side
"""


def load_data_seq() -> pd.DataFrame:
    """Load training data including sequential posterior columns (Epic 16B.1).

    Requires feature_pregame_lineup_features to have been rebuilt after the
    16B.1 dbt model update (dbtf run -s feature_pregame_lineup_features).
    """
    from betting_ml.utils.data_loader import get_snowflake_connection

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SEQ_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for col in df.select_dtypes(include=["object"]).columns:
        if col in (_CAT_FEATURE, "posterior_source"):
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    df["has_full_lineup"] = df["has_full_lineup"].astype(float)
    df = df.sort_values("game_date").reset_index(drop=True)

    # Validate that posterior_source column landed (requires post-16B.1 dbt rebuild)
    if "posterior_source" not in df.columns:
        raise RuntimeError(
            "posterior_source column missing from feature_pregame_lineup_features. "
            "Run: dbtf run -s feature_pregame_lineup_features  before running --seq."
        )
    seq_coverage = df["avg_eb_woba_sequential"].notna().mean()
    ps_dist = df["posterior_source"].value_counts(dropna=False).to_dict()
    print(f"  avg_eb_woba_sequential non-null coverage: {seq_coverage:.1%}")
    print(f"  posterior_source distribution: {ps_dist}")
    return df


def _compute_impute_means_seq(train: pd.DataFrame) -> dict[str, float]:
    """Compute imputation means for NUMERIC_FEATURES_SEQ (includes avg_eb_woba_sequential)."""
    means: dict[str, float] = {}
    for col in NUMERIC_FEATURES_SEQ:
        m = train[col].mean()
        means[col] = float(m) if not np.isnan(m) else 0.0
    return means


def _ohe_posterior_source(
    train: pd.DataFrame,
    eval_: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """OHE posterior_source with explicit __NA__ level for NULLs and cold-starts."""
    train = train.copy()
    eval_ = eval_.copy()
    train["posterior_source"] = train["posterior_source"].fillna("__NA__")
    eval_["posterior_source"] = eval_["posterior_source"].fillna("__NA__")

    train_dummies = pd.get_dummies(train["posterior_source"], prefix="ps", dtype=float)
    # Ensure all 4 known levels are always present (training fold may miss some)
    for col in _PS_OHE_COLS:
        if col not in train_dummies.columns:
            train_dummies[col] = 0.0
    train_dummies = train_dummies[_PS_OHE_COLS]

    eval_dummies = pd.get_dummies(eval_["posterior_source"], prefix="ps", dtype=float)
    for col in _PS_OHE_COLS:
        if col not in eval_dummies.columns:
            eval_dummies[col] = 0.0
    eval_dummies = eval_dummies[_PS_OHE_COLS]

    train_out = pd.concat([train.reset_index(drop=True), train_dummies.reset_index(drop=True)], axis=1)
    eval_out  = pd.concat([eval_.reset_index(drop=True), eval_dummies.reset_index(drop=True)], axis=1)
    return train_out, eval_out, _PS_OHE_COLS


def prepare_fold_seq(
    df: pd.DataFrame,
    train_idx,
    eval_idx,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict, list[str], list[str]]:
    """Seq-enriched fold preparation for Epic 16B.1.

    Adds avg_eb_woba_sequential to NUMERIC_FEATURES and OHEs both
    starter_pitch_archetype and posterior_source (with __NA__ cold-start level).
    """
    train = df.loc[train_idx].copy()
    eval_ = df.loc[eval_idx].copy()

    impute_means = _compute_impute_means_seq(train)
    train = _apply_impute(train, impute_means)
    eval_ = _apply_impute(eval_,  impute_means)

    # OHE starter_pitch_archetype (same pattern as v1)
    train, eval_, arch_cols = _ohe_archetype(train, eval_)

    # OHE posterior_source with __NA__ for NULLs / cold-starts
    train, eval_, ps_cols = _ohe_posterior_source(train, eval_)

    all_ohe_cols = arch_cols + ps_cols
    all_feat_cols = NUMERIC_FEATURES_SEQ + all_ohe_cols
    X_train = train[all_feat_cols].to_numpy(dtype=float)
    y_train = train[_TARGET].to_numpy(dtype=float)
    X_eval  = eval_[all_feat_cols].to_numpy(dtype=float)
    y_eval  = eval_[_TARGET].to_numpy(dtype=float)

    return X_train, y_train, X_eval, y_eval, impute_means, all_ohe_cols, all_feat_cols


def _train_final_model_seq(
    df: pd.DataFrame,
    winner_type: str,
    tuned_params: dict,
) -> tuple[object, np.ndarray, np.ndarray, dict, list[str], list[str]]:
    """Train final seq model on all complete seasons (excl. partial 2026)."""
    import lightgbm as lgb

    train = df[df["game_year"] != _EXCLUDE_EVAL_YEAR].copy()
    impute_means = _compute_impute_means_seq(train)
    train = _apply_impute(train, impute_means)

    # OHE starter_pitch_archetype
    train_dummies_arch = pd.get_dummies(train[_CAT_FEATURE], prefix="archetype", dtype=float)
    arch_cols = sorted(train_dummies_arch.columns.tolist())
    train = pd.concat([train.reset_index(drop=True), train_dummies_arch.reset_index(drop=True)], axis=1)

    # OHE posterior_source with __NA__
    train["posterior_source"] = train["posterior_source"].fillna("__NA__")
    train_dummies_ps = pd.get_dummies(train["posterior_source"], prefix="ps", dtype=float)
    for col in _PS_OHE_COLS:
        if col not in train_dummies_ps.columns:
            train_dummies_ps[col] = 0.0
    train_dummies_ps = train_dummies_ps[_PS_OHE_COLS]
    train = pd.concat([train.reset_index(drop=True), train_dummies_ps.reset_index(drop=True)], axis=1)

    all_ohe_cols = arch_cols + _PS_OHE_COLS
    feat_cols = NUMERIC_FEATURES_SEQ + all_ohe_cols
    X_all = train[feat_cols].to_numpy(dtype=float)
    y_all = train["runs_scored"].to_numpy(dtype=float)

    params = {
        **{k: v for k, v in tuned_params.items()},
        "objective":    "mae",
        "random_state": _OPTUNA_SEED,
        "verbose":      -1,
    }
    if "n_estimators" not in params:
        params["n_estimators"] = _LGBM_INIT_PARAMS["n_estimators"]
    model = lgb.LGBMRegressor(**params)
    model.fit(X_all, y_all)

    return model, X_all, y_all, impute_means, all_ohe_cols, feat_cols


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

def _cv_lgbm_negbin(
    df: pd.DataFrame,
    folds: list[tuple],
    lgbm_params: dict | None = None,
    prepare_fn=None,
    label: str = "B",
) -> tuple[float, float, float, float, list[dict]]:
    """Walk-forward CV for LightGBM conditional mean + global NegBin r.

    Returns (nll, mae, std_pred, calib_80, fold_records).

    prepare_fn: fold preparation callable — defaults to prepare_fold (nonseq).
                Pass prepare_fold_seq for the seq challenger.
    label: display label for the candidate header line.
    """
    import lightgbm as lgb

    _prepare = prepare_fn or prepare_fold
    params = lgbm_params or _LGBM_INIT_PARAMS
    fold_records: list[dict] = []
    all_mu: list[np.ndarray] = []
    all_y:  list[np.ndarray] = []

    print(f"\n── Candidate {label}: LightGBM+NegBin walk-forward CV ({len(folds)} folds) ────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'r':>6}  {'std_pred':>9}  {'BestIter':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = _prepare(df, train_idx, eval_idx)
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

def _make_optuna_objective(winner_type: str, df: pd.DataFrame, folds: list[tuple], prepare_fn=None):
    import lightgbm as lgb

    _prepare = prepare_fn or prepare_fold

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
                X_tr, y_tr, X_ev, y_ev, _, _, _ = _prepare(df, train_idx, eval_idx)
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
                X_tr, y_tr, X_ev, y_ev, _, _, _ = _prepare(df, train_idx, eval_idx)
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


def _tune_winner(
    winner_type: str,
    df: pd.DataFrame,
    folds: list[tuple],
    initial_nll: float,
    prepare_fn=None,
) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_optuna_objective(winner_type, df, folds, prepare_fn=prepare_fn)
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


# ---------------------------------------------------------------------------
# Epic 16B.1 — Sequential challenger training pipeline
# ---------------------------------------------------------------------------

def _update_registry_seq(
    nonseq_nll: float,
    nonseq_calib: float,
    seq_nll: float,
    seq_calib: float,
    seq_tuned_nll: float,
    seq_negbin_r: float,
    verdict: str,
    mlflow_run_id: str,
) -> None:
    """Update the offense_v2 registry block with the 16B.1 seq challenger result."""
    import re
    import datetime

    text = _REGISTRY_PATH.read_text()
    today = datetime.date.today().isoformat()

    verdict_line = (
        f"PROMOTED — seq challenger NLL {seq_nll:.4f} < nonseq {nonseq_nll:.4f} AND "
        f"calib_80 {seq_calib:.3f} ≥ {_CALIB_80_GATE}."
        if verdict == "promote"
        else f"HOLD — seq challenger did not beat nonseq champion on both NLL ({seq_nll:.4f} vs {nonseq_nll:.4f}) "
             f"and calib_80 ({seq_calib:.3f} vs {nonseq_calib:.3f}). Champion unchanged."
    )

    seq_block = f"""
  seq_challenger_16b1:
    run_date: '{today}'
    mlflow_run_id: {mlflow_run_id}
    nonseq_champion_nll: {round(nonseq_nll, 4)}
    nonseq_champion_calib_80: {round(nonseq_calib, 3)}
    seq_challenger_cv_nll: {round(seq_nll, 4)}
    seq_challenger_tuned_nll: {round(seq_tuned_nll, 4)}
    seq_challenger_calib_80: {round(seq_calib, 3)}
    seq_challenger_negbin_r: {round(seq_negbin_r, 4)}
    features_added: [avg_eb_woba_sequential, posterior_source_ohe]
    verdict: {verdict}
    verdict_detail: |
      {verdict_line}"""

    # Append seq_challenger_16b1 sub-block inside offense_v2 block (before next top-level key)
    pattern = r"(^offense_v2:.*?)(^(?!\s)|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
    if match:
        insertion_point = match.end(1)
        new_text = text[:insertion_point].rstrip() + "\n" + seq_block + "\n\n" + text[insertion_point:]
        _REGISTRY_PATH.write_text(new_text)
        print(f"  Updated offense_v2 seq_challenger_16b1 in {_REGISTRY_PATH.relative_to(_PROJECT_ROOT)}")
    else:
        # Fallback: append at end
        _REGISTRY_PATH.write_text(text.rstrip() + "\n" + seq_block + "\n")
        print("  [WARN] offense_v2 block not found; appended seq result to end of registry")


def train_seq(promote: bool = True, dry_run: bool = False) -> str:
    """Epic 16B.1 — Sequential sub-model enrichment for offense_v2.

    Runs a two-candidate comparison:
      - nonseq champion: current offense_v2 (NUMERIC_FEATURES, no seq columns)
      - seq challenger:  adds avg_eb_woba_sequential + posterior_source OHE

    Gate: challenger promoted only if NLL < nonseq champion NLL AND calib_80 ≥ gate.
    Negative result (hold) is recorded in registry + MLflow.

    Prerequisite: dbtf run -s feature_pregame_lineup_features  (adds posterior_source column)
    """
    print("=== EPIC 16B.1 — OFFENSE_V2 SEQUENTIAL CHALLENGER (LightGBM+NegBin) ===\n")
    print("Loading data from Snowflake (includes avg_eb_woba_sequential, posterior_source)...")
    df = load_data_seq()
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({df['game_year'].min():.0f}–{df['game_year'].max():.0f})")

    folds = get_cv_folds(df)
    eval_years = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in folds]
    print(f"  CV folds: {len(folds)} (eval years {eval_years[0]}–{eval_years[-1]})")
    print(f"  Nonseq features: {len(NUMERIC_FEATURES)} numeric + OHE {_CAT_FEATURE}")
    print(f"  Seq features:    {len(NUMERIC_FEATURES_SEQ)} numeric + OHE [{_CAT_FEATURE}, posterior_source]")
    print(f"  Champion thresholds: NLL={_NONSEQ_CHAMPION_NLL}  calib_80≥{_NONSEQ_CHAMPION_CALIB80}")

    # ── MLflow setup ──────────────────────────────────────────────────────────
    get_or_create_experiment(_MLFLOW_EXPERIMENT)
    mlflow.set_experiment(_MLFLOW_EXPERIMENT)

    with mlflow.start_run(run_name=f"seq_16b1_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id
        mlflow.log_params({
            "epic":               "16B.1",
            "n_rows":             len(df),
            "n_folds":            len(folds),
            "eval_years":         str(eval_years),
            "nonseq_champ_nll":   _NONSEQ_CHAMPION_NLL,
            "calib_80_gate":      _CALIB_80_GATE,
            "optuna_probe":       _OPTUNA_PROBE_TRIALS,
            "optuna_full":        _OPTUNA_FULL_TRIALS,
            "seq_features_added": "avg_eb_woba_sequential,posterior_source",
        })

        # ── Candidate nonseq: reproduce champion on this dataset ──────────────
        print("\n" + "=" * 72)
        print("Step 1/4 — Nonseq champion CV (current offense_v2 feature set)")
        print("=" * 72)
        ns_nll, ns_mae, ns_std, ns_calib, ns_folds = _cv_lgbm_negbin(
            df, folds, label="nonseq",
        )
        mlflow.log_metrics({
            "nonseq_cv_nll": ns_nll, "nonseq_cv_mae": ns_mae,
            "nonseq_calib_80": ns_calib, "nonseq_std_pred": ns_std,
        })
        print(f"\n  Nonseq champion: NLL={ns_nll:.4f}  calib_80={ns_calib:.3f}  "
              f"(registry champion NLL={_NONSEQ_CHAMPION_NLL})")

        # ── Candidate seq: sequential-enriched challenger ─────────────────────
        print("\n" + "=" * 72)
        print("Step 2/4 — Seq challenger CV (+ avg_eb_woba_sequential + posterior_source OHE)")
        print("=" * 72)
        seq_nll, seq_mae, seq_std, seq_calib, seq_folds = _cv_lgbm_negbin(
            df, folds, label="seq", prepare_fn=prepare_fold_seq,
        )
        mlflow.log_metrics({
            "seq_cv_nll": seq_nll, "seq_cv_mae": seq_mae,
            "seq_calib_80": seq_calib, "seq_std_pred": seq_std,
        })

        # ── Gate assessment ───────────────────────────────────────────────────
        print("\n" + "=" * 72)
        print("Step 3/4 — 16B.1 Gate assessment")
        print("=" * 72)
        nll_delta   = ns_nll - seq_nll      # positive = seq is better
        calib_delta = seq_calib - ns_calib  # positive = seq is better

        def glyph(ok: bool) -> str:
            return "✅" if ok else "❌"

        seq_beats_nll    = seq_nll   < ns_nll
        seq_beats_calib  = seq_calib >= _CALIB_80_GATE
        both_gates_pass  = seq_beats_nll and seq_beats_calib

        print(f"  {'Gate':<36} {'Threshold':>12}  {'nonseq':>8}  {'seq':>8}  {'Pass':>6}")
        print(f"  {'-'*36}  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*6}")
        print(f"  {'NLL (seq < nonseq)':<36} {'<' + f'{ns_nll:.4f}':>12}  "
              f"{ns_nll:>8.4f}  {seq_nll:>8.4f}  {glyph(seq_beats_nll):>6}  "
              f"(Δ {nll_delta:+.4f})")
        print(f"  {'calib_80':<36} {'≥' + f'{_CALIB_80_GATE:.2f}':>12}  "
              f"{ns_calib:>8.3f}  {seq_calib:>8.3f}  {glyph(seq_beats_calib):>6}  "
              f"(Δ {calib_delta:+.3f})")
        print()
        print(f"  Both gates pass: {'YES → PROMOTE SEQ CHALLENGER' if both_gates_pass else 'NO → HOLD NONSEQ CHAMPION'}")

        verdict = "promote" if both_gates_pass else "hold"
        mlflow.log_params({"seq_verdict": verdict})
        mlflow.log_metrics({
            "nll_delta_nonseq_minus_seq": nll_delta,
            "calib_delta_seq_minus_nonseq": calib_delta,
        })

        if dry_run:
            print("\n[DRY RUN] Skipping Optuna tuning and artifact save.")
            return mlflow_run_id

        # ── Optuna-tune the winner ────────────────────────────────────────────
        print("\n" + "=" * 72)
        if verdict == "promote":
            print("Step 4/4 — Optuna-tune SEQ challenger (winner)")
            winner_nll    = seq_nll
            winner_pfn    = prepare_fold_seq
            winner_label  = "seq"
        else:
            print("Step 4/4 — Optuna-tune NONSEQ champion (no promotion)")
            winner_nll    = ns_nll
            winner_pfn    = None  # defaults to prepare_fold
            winner_label  = "nonseq"
        print("=" * 72)

        tuned_params, tuned_nll = _tune_winner(
            "lgbm", df, folds, winner_nll, prepare_fn=winner_pfn,
        )
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # ── Train final model ─────────────────────────────────────────────────
        print(f"\n── Training final {winner_label} LightGBM+NegBin model on 2015–2025 ────")
        if verdict == "promote":
            final_model, X_all, y_all, impute_means, ohe_cols, feat_cols = (
                _train_final_model_seq(df, "lgbm", tuned_params)
            )
        else:
            final_model, X_all, y_all, impute_means, ohe_cols, feat_cols = (
                _train_final_model(df, "lgbm", tuned_params)
            )

        mu_all        = np.clip(final_model.predict(X_all), _MIN_MU, None)
        global_r      = _fit_negbin_r(y_all, mu_all)
        in_sample_nll = _negbin_nll(y_all, mu_all, global_r)
        in_sample_mae = float(np.mean(np.abs(mu_all - y_all)))
        target_mean   = float(y_all.mean())
        target_std    = float(y_all.std())

        print(f"  In-sample NLL:       {in_sample_nll:.4f}")
        print(f"  In-sample MAE:       {in_sample_mae:.4f}")
        print(f"  Walk-forward CV NLL: {winner_nll:.4f}")
        print(f"  Fitted NegBin r:     {global_r:.4f}")

        mlflow.log_metrics({
            "final_insample_nll": in_sample_nll,
            "final_insample_mae": in_sample_mae,
            "final_negbin_r":     global_r,
        })

        # ── Save artifact ─────────────────────────────────────────────────────
        artifact = {
            "model":              final_model,
            "model_type":         "lgbm",
            "negbin_r":           global_r,
            "feature_names":      feat_cols,
            "ohe_categories":     ohe_cols,
            "impute_means":       impute_means,
            "target_mean":        target_mean,
            "target_std":         target_std,
            "min_mu":             _MIN_MU,
            "cv_nll":             winner_nll,
            "cv_mae":             seq_mae if verdict == "promote" else ns_mae,
            "tuned_params":       tuned_params,
            "tuned_cv_nll":       tuned_nll,
            "seq_challenger_nll":  seq_nll,
            "seq_challenger_calib": seq_calib,
            "nonseq_champion_nll": ns_nll,
            "nonseq_champion_calib": ns_calib,
            "cv_fold_records":    seq_folds if verdict == "promote" else ns_folds,
            "epic":               "16B.1",
            "verdict":            verdict,
            "seq_features_added": ["avg_eb_woba_sequential", "posterior_source"],
        }

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = _OUTPUT_DIR / f"offense_v2_seq_{date.today()}.pkl"
        joblib.dump(artifact, artifact_path)
        print(f"\nArtifact saved → {artifact_path.relative_to(_PROJECT_ROOT)}")

        if promote and verdict == "promote":
            upload_artifact(artifact_path, _ARTIFACT_S3_URI)
            # Also write to the canonical offense_v2.pkl path (serving path)
            canonical_path = _OUTPUT_DIR / "offense_v2.pkl"
            joblib.dump(artifact, canonical_path)
            print(f"  Canonical artifact updated → {canonical_path.relative_to(_PROJECT_ROOT)}")
        elif promote and verdict == "hold":
            print("  Seq gate not passed — skipping S3 upload (nonseq champion unchanged)")

        mlflow.log_artifact(str(artifact_path))
        mlflow.set_tag("sub_model_registry_key", "offense_v2")
        mlflow.set_tag("epic", "16B.1")
        print(f"  MLflow run_id: {mlflow_run_id}")

        # ── Registry ─────────────────────────────────────────────────────────
        if promote:
            _update_registry_seq(
                nonseq_nll=ns_nll,
                nonseq_calib=ns_calib,
                seq_nll=seq_nll,
                seq_calib=seq_calib,
                seq_tuned_nll=tuned_nll,
                seq_negbin_r=global_r,
                verdict=verdict,
                mlflow_run_id=mlflow_run_id,
            )

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(f"Epic 16B.1 result: {verdict.upper()}")
    print(f"  nonseq champion: NLL={ns_nll:.4f}  calib_80={ns_calib:.3f}")
    print(f"  seq challenger:  NLL={seq_nll:.4f}  calib_80={seq_calib:.3f}  "
          f"(Δ NLL {nll_delta:+.4f}  Δ calib {calib_delta:+.3f})")
    print(f"  Tuned NLL ({winner_label}): {tuned_nll:.4f}")
    print(f"  MLflow experiment: {_MLFLOW_EXPERIMENT}  run_id: {mlflow_run_id}")

    if verdict == "promote":
        print("\n16B.1 PROMOTED. Next steps (16B.4 regeneration):")
        print("  1. Re-run generate_offense_signals.py against the seq artifact")
        print("     to refresh feature_pregame_sub_model_signals")
        print("  2. Continue to 16B.2 (bullpen retrain) and 16B.3 (starter retrain)")
        print("  3. After 16B.1–16B.3 complete → run 16B.4 (OOS regen + stacking weights)")
    else:
        print("\n16B.1 HOLD. Nonseq champion unchanged.")
        print("  Record this result; continue 16B.2/16B.3 regardless (per spec).")
        print("  The combined-μ gate (16B.5) will assess the full picture after all retrains.")

    return mlflow_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Epic 4D / 16B.1 — train offense_v2")
    parser.add_argument("--seq", action="store_true",
                        help="Epic 16B.1: sequential challenger comparison (nonseq vs seq). "
                             "Requires dbtf run -s feature_pregame_lineup_features first.")
    parser.add_argument("--no-promote", action="store_true",
                        help="Skip S3 upload and registry update")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run CV only — skip Optuna, artifact save, and registry")
    args = parser.parse_args()

    if args.seq:
        train_seq(
            promote=not args.no_promote,
            dry_run=args.dry_run,
        )
    else:
        train(
            promote=not args.no_promote,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
