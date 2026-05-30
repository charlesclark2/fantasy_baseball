"""
train_starter_v1.py — Epic 5, Story 5.2

Three-candidate Normal distributional comparison for starter xwOBA-against:

  Candidate A — NGBoost Normal       (end-to-end distributional; native Normal NLL)
  Candidate B — LightGBM + sigma     (LGBM predicts mean; sigma from training residuals)
  Candidate C — OLS GLM baseline     (statsmodels OLS; sigma = training RMSE; NLL floor only)

Gates (all must pass to promote):
  NLL      < Candidate C NLL + 0.015 slack     (primary gate)
  calib_80 ≥ 0.75 (≥ 75% of actuals within ±1.28σ of mu)
  std(pred) ≥ 0.010 (degeneracy guard; xwOBA range 0.28–0.38)
  MAE      in 0.030–0.055 (expected range for xwOBA-against)

Winner is Optuna-tuned on mean CV NLL (objective).
Champion becomes starter_v1.

Usage:
    uv run python betting_ml/scripts/starter_v1/train_starter_v1.py
    uv run python betting_ml/scripts/starter_v1/train_starter_v1.py --no-promote
    uv run python betting_ml/scripts/starter_v1/train_starter_v1.py --skip-ngboost
    uv run python betting_ml/scripts/starter_v1/train_starter_v1.py --optuna-probe 5 --optuna-full 20
    uv run python betting_ml/scripts/starter_v1/train_starter_v1.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import date
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)
warnings.filterwarnings("ignore", message=".*`force_all_finite`.*", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_OUTPUT_DIR     = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "starter_v1"
_REGISTRY_PATH  = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_ARTIFACT_S3    = "s3://baseball-betting-ml-artifacts/sub_models/starter_v1.pkl"
_FEAT_COLS_PATH = _OUTPUT_DIR / "feature_columns.json"
_PARAMS_PATH    = _OUTPUT_DIR / "best_params.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_YEAR         = 2016   # EB xwOBA available; Stuff+ null 2016–2019 (imputed to mean)
_EXCLUDE_EVAL_YEAR = 2026   # partial season — exclude from Optuna objective
_MIN_TRAIN_SEASONS = 7      # keeps eval window at 2023–2026 (same folds, richer training)

_STD_PRED_GATE  = 0.010    # degeneracy guard (xwOBA range is 0.28–0.38)
_CALIB_80_GATE  = 0.75     # fraction of actuals within ±1.28σ
_NLL_GATE_SLACK = 0.015    # GLM may degenerate to intercept-only
_MIN_SIGMA      = 0.005    # floor to prevent NLL explosion on near-zero sigma
_OPTUNA_SEED    = 42

# ---------------------------------------------------------------------------
# Feature inventory (mirrors feature_columns.json)
# ---------------------------------------------------------------------------

NUMERIC_FEATURES: list[str] = [
    # A: EB posteriors
    "eb_xwoba_against", "eb_k_pct", "eb_bb_pct", "eb_xwoba_uncertainty",
    # B: rolling 7d
    "xwoba_against_7d", "k_pct_7d", "bb_pct_7d", "hard_hit_pct_7d",
    "barrel_pct_7d", "whiff_rate_7d", "batter_chase_rate_7d", "avg_fastball_velo_7d",
    # C: rolling 14d
    "xwoba_against_14d", "k_pct_14d", "bb_pct_14d", "hard_hit_pct_14d",
    "barrel_pct_14d", "whiff_rate_14d", "batter_chase_rate_14d", "avg_fastball_velo_14d",
    # D: rolling 30d
    "xwoba_against_30d", "k_pct_30d", "bb_pct_30d", "hard_hit_pct_30d",
    "barrel_pct_30d", "whiff_rate_30d", "batter_chase_rate_30d", "avg_fastball_velo_30d",
    # E: rolling season-to-date
    "xwoba_against_std", "k_pct_std", "bb_pct_std", "hard_hit_pct_std",
    "barrel_pct_std", "whiff_rate_std", "batter_chase_rate_std", "avg_fastball_velo_std",
    # F: velocity & form
    "fastball_velo_trend", "avg_fastball_velo_3start", "velo_delta_3start",
    "k_pct_7d_minus_std", "xwoba_7d_minus_std",
    # G: activity
    "appearances_30d", "appearances_std",
    # H: platoon splits
    "k_pct_vs_lhb", "bb_pct_vs_lhb", "xwoba_vs_lhb", "whiff_rate_vs_lhb",
    "k_pct_vs_rhb", "bb_pct_vs_rhb", "xwoba_vs_rhb", "whiff_rate_vs_rhb",
    # I: workload / rest
    "avg_ip_last_3", "avg_ip_season", "cumulative_season_ip", "cumulative_season_pitches", "days_rest",
    # J: Stuff+ and arsenal
    "starter_stuff_plus", "starter_fastball_pct", "starter_breaking_pct",
    "starter_offspeed_pct", "starter_avg_fastball_velo",
    "starter_fastball_stuff_plus", "starter_slider_stuff_plus",
    "starter_curveball_stuff_plus", "starter_changeup_stuff_plus",
    # K: ZiPS + trailing FIP (starter_proj_xfip excluded: 100% NULL)
    "starter_proj_fip", "starter_trailing_fip_30g", "starter_trailing_ra9_30g", "starter_fip_ra9_gap",
    # L: CSW & pitch mix drift
    "csw_pct_3start", "csw_pct_season",
    "fastball_pct_drift_5start", "breaking_pct_drift_5start", "offspeed_pct_drift_5start",
]

CAT_FEATURES: list[str] = ["pitcher_hand", "starter_primary_pitch_type", "eb_data_source"]
TARGET = "xwoba_against"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_QUERY = """
SELECT
    f.game_pk,
    f.game_date,
    f.game_year,
    f.side,
    f.pitcher_id,
    f.pitcher_hand,
    f.starter_primary_pitch_type,
    f.eb_data_source,
    f.eb_xwoba_against, f.eb_k_pct, f.eb_bb_pct, f.eb_xwoba_uncertainty,
    f.xwoba_against_7d, f.k_pct_7d, f.bb_pct_7d, f.hard_hit_pct_7d,
    f.barrel_pct_7d, f.whiff_rate_7d, f.batter_chase_rate_7d, f.avg_fastball_velo_7d,
    f.xwoba_against_14d, f.k_pct_14d, f.bb_pct_14d, f.hard_hit_pct_14d,
    f.barrel_pct_14d, f.whiff_rate_14d, f.batter_chase_rate_14d, f.avg_fastball_velo_14d,
    f.xwoba_against_30d, f.k_pct_30d, f.bb_pct_30d, f.hard_hit_pct_30d,
    f.barrel_pct_30d, f.whiff_rate_30d, f.batter_chase_rate_30d, f.avg_fastball_velo_30d,
    f.xwoba_against_std, f.k_pct_std, f.bb_pct_std, f.hard_hit_pct_std,
    f.barrel_pct_std, f.whiff_rate_std, f.batter_chase_rate_std, f.avg_fastball_velo_std,
    f.fastball_velo_trend, f.avg_fastball_velo_3start, f.velo_delta_3start,
    f.k_pct_7d_minus_std, f.xwoba_7d_minus_std,
    f.appearances_30d, f.appearances_std,
    f.k_pct_vs_lhb, f.bb_pct_vs_lhb, f.xwoba_vs_lhb, f.whiff_rate_vs_lhb,
    f.k_pct_vs_rhb, f.bb_pct_vs_rhb, f.xwoba_vs_rhb, f.whiff_rate_vs_rhb,
    f.avg_ip_last_3, f.avg_ip_season, f.cumulative_season_ip, f.cumulative_season_pitches, f.days_rest,
    f.starter_stuff_plus, f.starter_fastball_pct,
    f.starter_breaking_pct, f.starter_offspeed_pct, f.starter_avg_fastball_velo,
    f.starter_fastball_stuff_plus, f.starter_slider_stuff_plus,
    f.starter_curveball_stuff_plus, f.starter_changeup_stuff_plus,
    f.starter_proj_fip, f.starter_trailing_fip_30g, f.starter_trailing_ra9_30g, f.starter_fip_ra9_gap,
    f.csw_pct_3start, f.csw_pct_season,
    f.fastball_pct_drift_5start, f.breaking_pct_drift_5start, f.offspeed_pct_drift_5start,
    m.xwoba_against
FROM baseball_data.betting_features.feature_pregame_starter_features f
JOIN baseball_data.betting.mart_starting_pitcher_game_log m
    ON m.game_pk = f.game_pk AND m.pitcher_id = f.pitcher_id
WHERE f.game_year BETWEEN {min_year} AND 2026
  AND f.has_starter_data = TRUE
  AND m.xwoba_against IS NOT NULL
ORDER BY f.game_date, f.game_pk, f.side
"""


def load_data(min_year: int = _MIN_YEAR) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY.format(min_year=min_year))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    df = df.sort_values("game_date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CV fold selection
# ---------------------------------------------------------------------------

def get_cv_folds(df: pd.DataFrame, exclude_eval_year: int = _EXCLUDE_EVAL_YEAR) -> list[tuple]:
    all_folds = list(all_season_splits(df, min_train_seasons=_MIN_TRAIN_SEASONS))
    return [
        (tr, ev) for tr, ev in all_folds
        if int(df.loc[ev, "game_year"].mode()[0]) != exclude_eval_year
    ]


def get_all_folds(df: pd.DataFrame) -> list[tuple]:
    """All folds including 2026 — for final CV reporting."""
    return list(all_season_splits(df, min_train_seasons=_MIN_TRAIN_SEASONS))


# ---------------------------------------------------------------------------
# Per-fold data preparation
# ---------------------------------------------------------------------------

def _compute_impute_means(train: pd.DataFrame) -> dict[str, float]:
    means: dict[str, float] = {}
    for col in NUMERIC_FEATURES:
        if col in train.columns:
            m = train[col].mean()
            means[col] = float(m) if not np.isnan(m) else 0.0
    return means


def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _ohe_cats(
    train: pd.DataFrame,
    eval_: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """One-hot encode all CAT_FEATURES. Align eval columns to training set."""
    train_dummies_list = []
    eval_dummies_list  = []
    all_ohe_cols: list[str] = []

    for cat in CAT_FEATURES:
        if cat not in train.columns:
            continue
        t_d = pd.get_dummies(train[cat].fillna("__NA__"), prefix=cat, dtype=float)
        e_d = pd.get_dummies(eval_[cat].fillna("__NA__"), prefix=cat, dtype=float)
        ohe_cols = sorted(t_d.columns.tolist())
        t_d = t_d.reindex(columns=ohe_cols, fill_value=0.0)
        e_d = e_d.reindex(columns=ohe_cols, fill_value=0.0)
        train_dummies_list.append(t_d)
        eval_dummies_list.append(e_d)
        all_ohe_cols.extend(ohe_cols)

    train_out = pd.concat(
        [train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in train_dummies_list],
        axis=1,
    )
    eval_out = pd.concat(
        [eval_.reset_index(drop=True)] + [d.reset_index(drop=True) for d in eval_dummies_list],
        axis=1,
    )
    return train_out, eval_out, all_ohe_cols


def prepare_fold(
    df: pd.DataFrame,
    train_idx,
    eval_idx,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict, list[str], list[str]]:
    train = df.loc[train_idx].copy()
    eval_ = df.loc[eval_idx].copy()

    impute_means = _compute_impute_means(train)
    train = _apply_impute(train, impute_means)
    eval_ = _apply_impute(eval_,  impute_means)

    train, eval_, ohe_cols = _ohe_cats(train, eval_)

    all_feat_cols = NUMERIC_FEATURES + ohe_cols
    X_train = train[all_feat_cols].to_numpy(dtype=float)
    y_train = train[TARGET].to_numpy(dtype=float)
    X_eval  = eval_[all_feat_cols].to_numpy(dtype=float)
    y_eval  = eval_[TARGET].to_numpy(dtype=float)

    return X_train, y_train, X_eval, y_eval, impute_means, ohe_cols, all_feat_cols


# ---------------------------------------------------------------------------
# Normal distribution helpers
# ---------------------------------------------------------------------------

_LOG_SQRT_2PI = 0.5 * np.log(2 * np.pi)


def normal_nll(y: np.ndarray, mu: np.ndarray, sigma: float) -> float:
    """Mean Normal negative log-likelihood per sample."""
    sigma = max(sigma, _MIN_SIGMA)
    return float(np.mean(_LOG_SQRT_2PI + np.log(sigma) + 0.5 * ((y - mu) / sigma) ** 2))


def fit_sigma(y_train: np.ndarray, mu_train: np.ndarray) -> float:
    """Sigma = training RMSE (fit on train; apply to eval for NLL computation)."""
    residuals = y_train - mu_train
    return max(float(np.sqrt(np.mean(residuals ** 2))), _MIN_SIGMA)


def calib_80(y: np.ndarray, mu: np.ndarray, sigma: float) -> float:
    """Fraction of eval actuals within ±1.28σ of predicted mean (80% PI coverage)."""
    sigma = max(sigma, _MIN_SIGMA)
    width = 1.28 * sigma
    return float(np.mean(np.abs(y - mu) <= width))


# ---------------------------------------------------------------------------
# Candidate C — OLS GLM baseline (NLL floor; never promoted)
# ---------------------------------------------------------------------------

def cv_glm(df: pd.DataFrame, folds: list[tuple]) -> tuple[float, float, float, float, list[dict]]:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    fold_records: list[dict] = []
    print(f"\n── C-GLM walk-forward CV ({len(folds)} folds) ──────────────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'sigma':>7}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        pipe = Pipeline([("scaler", StandardScaler()), ("lr", LinearRegression())])
        pipe.fit(X_tr, y_tr)
        mu_tr = pipe.predict(X_tr)
        mu_ev = pipe.predict(X_ev)

        sigma = fit_sigma(y_tr, mu_tr)
        nll   = normal_nll(y_ev, mu_ev, sigma)
        mae   = float(np.mean(np.abs(y_ev - mu_ev)))
        c80   = calib_80(y_ev, mu_ev, sigma)
        std_p = float(np.std(mu_ev))

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.4f}  {c80:>8.3f}  {sigma:>7.4f}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "sigma": round(sigma, 4), "std_pred": round(std_p, 4),
        })

    mean_nll  = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae  = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80  = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std  = float(np.mean([r["std_pred"] for r in fold_records]))
    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  calib_80: {mean_c80:.3f}  std(pred): {mean_std:.4f}")
    return mean_nll, mean_mae, mean_std, mean_c80, fold_records


# ---------------------------------------------------------------------------
# Candidate A — NGBoost Normal
# ---------------------------------------------------------------------------

def cv_ngboost(
    df: pd.DataFrame,
    folds: list[tuple],
    params: dict | None = None,
) -> tuple[float, float, float, float, list[dict]]:
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    default_params = dict(n_estimators=500, learning_rate=0.01, minibatch_frac=1.0,
                          random_state=42, verbose=False)
    p = {**default_params, **(params or {})}

    fold_records: list[dict] = []
    print(f"\n── A-NGBoost Normal walk-forward CV ({len(folds)} folds) ────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'sigma':>7}  {'std_pred':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        ngb = NGBRegressor(Dist=Normal, **p)
        ngb.fit(X_tr, y_tr)

        dist_ev = ngb.pred_dist(X_ev)
        mu_ev   = dist_ev.loc
        sig_ev  = np.clip(dist_ev.scale, _MIN_SIGMA, None)

        nll   = float(np.mean(normal_nll(y_ev, mu_ev, sig) for sig, mu in zip(sig_ev, mu_ev)
                               )) if False else float(np.mean(
                                   _LOG_SQRT_2PI + np.log(sig_ev) + 0.5 * ((y_ev - mu_ev) / sig_ev) ** 2
                               ))
        mae   = float(np.mean(np.abs(y_ev - mu_ev)))
        mean_sigma = float(np.mean(sig_ev))
        c80   = float(np.mean(np.abs(y_ev - mu_ev) <= 1.28 * sig_ev))
        std_p = float(np.std(mu_ev))

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.4f}  {c80:>8.3f}  {mean_sigma:>7.4f}  {std_p:>9.4f}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "mean_sigma": round(mean_sigma, 4), "std_pred": round(std_p, 4),
        })

    mean_nll = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80 = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std = float(np.mean([r["std_pred"] for r in fold_records]))
    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  calib_80: {mean_c80:.3f}  std(pred): {mean_std:.4f}")
    return mean_nll, mean_mae, mean_std, mean_c80, fold_records


# ---------------------------------------------------------------------------
# Candidate B — LightGBM + Normal sigma
# ---------------------------------------------------------------------------

def cv_lgbm(
    df: pd.DataFrame,
    folds: list[tuple],
    params: dict | None = None,
) -> tuple[float, float, float, float, list[dict], list[str], int]:
    import lightgbm as lgb

    default_params = dict(
        num_leaves=63, learning_rate=0.05, min_child_samples=20,
        subsample=0.8, colsample_bytree=0.7, n_estimators=500,
        objective="mae", metric="mae", random_state=42, verbose=-1,
    )
    p = {**default_params, **(params or {})}

    fold_records: list[dict] = []
    all_feat_names: list[str] = []
    best_iters: list[int] = []

    print(f"\n── B-LightGBM + sigma walk-forward CV ({len(folds)} folds) ─────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'sigma':>7}  {'std_pred':>9}  {'BestIter':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, feat_cols = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        if not all_feat_names:
            all_feat_names = feat_cols

        model = lgb.LGBMRegressor(**p)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=30, verbose=False),
                lgb.log_evaluation(-1),
            ],
        )
        best_iters.append(int(model.best_iteration_))

        mu_tr = model.predict(X_tr)
        mu_ev = model.predict(X_ev)
        sigma = fit_sigma(y_tr, mu_tr)
        nll   = normal_nll(y_ev, mu_ev, sigma)
        mae   = float(np.mean(np.abs(y_ev - mu_ev)))
        c80   = calib_80(y_ev, mu_ev, sigma)
        std_p = float(np.std(mu_ev))

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.4f}  {c80:>8.3f}  {sigma:>7.4f}  {std_p:>9.4f}  {model.best_iteration_:>9}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll": round(nll, 4), "mae": round(mae, 4),
            "calib_80": round(c80, 3), "sigma": round(sigma, 4),
            "std_pred": round(std_p, 4), "best_iteration": int(model.best_iteration_),
        })

    mean_nll  = float(np.mean([r["nll"]  for r in fold_records]))
    mean_mae  = float(np.mean([r["mae"]  for r in fold_records]))
    mean_c80  = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std  = float(np.mean([r["std_pred"] for r in fold_records]))
    mean_iter = int(round(float(np.mean(best_iters))))
    print(f"\n  Mean NLL: {mean_nll:.4f}  Mean MAE: {mean_mae:.4f}  calib_80: {mean_c80:.3f}  std(pred): {mean_std:.4f}  mean_iter: {mean_iter}")
    return mean_nll, mean_mae, mean_std, mean_c80, fold_records, all_feat_names, mean_iter


# ---------------------------------------------------------------------------
# Gate summary and winner selection
# ---------------------------------------------------------------------------

def print_gate_summary(
    a_nll: float | None, a_mae: float | None, a_std: float | None, a_calib: float | None,
    b_nll: float, b_mae: float, b_std: float, b_calib: float,
    c_nll: float,
    skip_ngboost: bool = False,
) -> tuple[str, float]:
    """Print gate table and return (winner_type, winner_nll)."""
    glm_threshold = c_nll + _NLL_GATE_SLACK

    def gate(val: float | None, thresh: float, direction: str = "ge") -> str:
        if val is None:
            return "—"
        passes = (val >= thresh) if direction == "ge" else (val <= thresh)
        return "OK" if passes else "NO"

    print("\n" + "=" * 76)
    print("Gate summary")
    print("=" * 76)
    cols = f"  {'Gate':<28} {'Threshold':>12}"
    if not skip_ngboost:
        cols += f"  {'A-NGBoost':>12}"
    cols += f"  {'B-LGBM':>10}"
    print(cols)
    print("  " + "-" * (72 if not skip_ngboost else 56))

    def row(label, thresh_str, a_val, b_val, direction="ge"):
        s = f"  {label:<28} {thresh_str:>12}"
        if not skip_ngboost:
            av = f"{a_val:.4f} {gate(a_val, float(thresh_str.lstrip('<≥≤ ')), direction)}" if a_val is not None else "—"
            s += f"  {av:>12}"
        bv = f"{b_val:.4f} {gate(b_val, float(thresh_str.lstrip('<≥≤ ')), direction)}"
        s += f"  {bv:>10}"
        return s

    nll_thr = glm_threshold
    print(f"  {'NLL < GLM+slack':<28} {'< ' + f'{nll_thr:.4f}':>12}"
          + (f"  {a_nll:.4f} {gate(a_nll, nll_thr, 'le') if a_nll else '—':>12}" if not skip_ngboost else "")
          + f"  {b_nll:.4f} {gate(b_nll, nll_thr, 'le'):>10}")
    print(f"  {'calib_80':<28} {'≥ ' + f'{_CALIB_80_GATE:.2f}':>12}"
          + (f"  {a_calib:.3f} {gate(a_calib, _CALIB_80_GATE):>12}" if (not skip_ngboost and a_calib is not None) else ("  —" if not skip_ngboost else ""))
          + f"  {b_calib:.3f} {gate(b_calib, _CALIB_80_GATE):>10}")
    print(f"  {'std(pred)':<28} {'≥ ' + f'{_STD_PRED_GATE:.3f}':>12}"
          + (f"  {a_std:.4f} {gate(a_std, _STD_PRED_GATE):>12}" if (not skip_ngboost and a_std is not None) else ("  —" if not skip_ngboost else ""))
          + f"  {b_std:.4f} {gate(b_std, _STD_PRED_GATE):>10}")
    print()

    def _passes(nll, std, calib, is_le_nll=True):
        if nll is None:
            return False
        nll_ok = (nll <= glm_threshold)
        return nll_ok and (std >= _STD_PRED_GATE) and (calib >= _CALIB_80_GATE)

    a_passes = (not skip_ngboost) and _passes(a_nll, a_std, a_calib)
    b_passes = _passes(b_nll, b_std, b_calib)

    if not skip_ngboost:
        print(f"  A-NGBoost passes all gates: {'YES' if a_passes else 'NO'}")
    print(f"  B-LightGBM passes all gates: {'YES' if b_passes else 'NO'}")

    # Selection
    if not a_passes and not b_passes:
        print("\n  [WARN] Neither candidate passes all gates. Selecting lower-NLL candidate.")
        if skip_ngboost or a_nll is None:
            return "lgbm", b_nll
        winner = "ngboost" if a_nll <= b_nll else "lgbm"
        return winner, (a_nll if winner == "ngboost" else b_nll)

    if a_passes and b_passes:
        if skip_ngboost or a_nll is None or b_nll <= a_nll:
            print("\n  Both pass (or NGBoost skipped). Winner: B-LightGBM")
            return "lgbm", b_nll
        print("\n  Both pass. Winner by lower NLL: A-NGBoost")
        return "ngboost", a_nll
    if a_passes:
        print("\n  Winner: A-NGBoost")
        return "ngboost", a_nll
    print("\n  Winner: B-LightGBM")
    return "lgbm", b_nll


# ---------------------------------------------------------------------------
# Optuna tuning
# ---------------------------------------------------------------------------

def _tune_winner(
    winner_type: str,
    df: pd.DataFrame,
    folds: list[tuple],  # Optuna folds (exclude partial year)
    n_probe: int,
    n_full: int,
) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial) -> float:
        if winner_type == "lgbm":
            import lightgbm as lgb
            params = {
                "num_leaves":        trial.suggest_int("num_leaves", 15, 127),
                "learning_rate":     trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 80),
                "reg_alpha":         trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
                "reg_lambda":        trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
                "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "n_estimators":      trial.suggest_int("n_estimators", 100, 800, step=50),
                "objective": "mae", "random_state": _OPTUNA_SEED, "verbose": -1,
            }
            fold_nlls: list[float] = []
            for tr_idx, ev_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, tr_idx, ev_idx)
                model = lgb.LGBMRegressor(**params)
                model.fit(X_tr, y_tr)
                mu_tr = model.predict(X_tr)
                mu_ev = model.predict(X_ev)
                sigma = fit_sigma(y_tr, mu_tr)
                fold_nlls.append(normal_nll(y_ev, mu_ev, sigma))
            return float(np.mean(fold_nlls))

        else:  # ngboost
            from ngboost import NGBRegressor
            from ngboost.distns import Normal
            params = {
                "n_estimators":   trial.suggest_int("n_estimators", 200, 1000, step=100),
                "learning_rate":  trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "minibatch_frac": trial.suggest_float("minibatch_frac", 0.5, 1.0),
            }
            fold_nlls = []
            for tr_idx, ev_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, tr_idx, ev_idx)
                ngb = NGBRegressor(Dist=Normal, random_state=_OPTUNA_SEED, verbose=False, **params)
                ngb.fit(X_tr, y_tr)
                dist = ngb.pred_dist(X_ev)
                mu_ev = dist.loc
                sig_ev = np.clip(dist.scale, _MIN_SIGMA, None)
                fold_nlls.append(float(np.mean(
                    _LOG_SQRT_2PI + np.log(sig_ev) + 0.5 * ((y_ev - mu_ev) / sig_ev) ** 2
                )))
            return float(np.mean(fold_nlls))

    # Probe then full
    print(f"\n── Optuna: {winner_type} ({n_probe}-trial probe) ─────────────────────────")
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED))
    study.optimize(objective, n_trials=n_probe, show_progress_bar=True)
    probe_nll = study.best_value
    print(f"  Probe best NLL: {probe_nll:.4f}  params: {study.best_params}")

    print(f"\n── Optuna: {winner_type} ({n_full}-trial full search) ────────────────────")
    study.optimize(objective, n_trials=n_full, show_progress_bar=True)
    best_nll = study.best_value
    best_params = study.best_params
    print(f"  Full best NLL:  {best_nll:.4f}  params: {best_params}")

    return best_params, best_nll


# ---------------------------------------------------------------------------
# Final model training
# ---------------------------------------------------------------------------

def _prepare_final_train(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict, list[str], list[str]]:
    """Train on all available seasons (2016–2026 including partial)."""
    impute_means = _compute_impute_means(df)
    train = _apply_impute(df.copy(), impute_means)

    dummies_list = []
    all_ohe_cols: list[str] = []
    for cat in CAT_FEATURES:
        if cat not in train.columns:
            continue
        d = pd.get_dummies(train[cat], prefix=cat, dtype=float)
        ohe_cols = sorted(d.columns.tolist())
        d = d.reindex(columns=ohe_cols, fill_value=0.0)
        dummies_list.append(d)
        all_ohe_cols.extend(ohe_cols)

    train = pd.concat([train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in dummies_list], axis=1)
    all_feat_cols = NUMERIC_FEATURES + all_ohe_cols
    X = train[all_feat_cols].to_numpy(dtype=float)
    y = train[TARGET].to_numpy(dtype=float)
    return X, y, impute_means, all_ohe_cols, all_feat_cols


def train_final_lgbm(df: pd.DataFrame, best_params: dict, mean_iter: int, fold_records: list[dict]) -> dict:
    import lightgbm as lgb

    X, y, impute_means, ohe_cols, feat_cols = _prepare_final_train(df)
    final_params = {
        **best_params,
        "n_estimators": mean_iter,
        "objective": "mae", "random_state": 42, "verbose": -1,
    }
    model = lgb.LGBMRegressor(**final_params)
    model.fit(X, y)
    mu = model.predict(X)
    sigma = fit_sigma(y, mu)
    print(f"\n  Final LightGBM trained on {len(y):,} rows; sigma={sigma:.4f}")
    _print_feature_importance(model, feat_cols)

    return {
        "model_type": "lgbm",
        "model": model,
        "sigma": sigma,
        "impute_means": impute_means,
        "ohe_categories": ohe_cols,
        "feature_names": feat_cols,
        "feature_columns": NUMERIC_FEATURES + ohe_cols,
        "cv_nll":  round(float(np.mean([r["nll"] for r in fold_records])), 4),
        "cv_mae":  round(float(np.mean([r["mae"] for r in fold_records])), 4),
        "cv_folds": len(fold_records),
        "cv_fold_records": fold_records,
    }


def train_final_ngboost(df: pd.DataFrame, best_params: dict, fold_records: list[dict]) -> dict:
    from ngboost import NGBRegressor
    from ngboost.distns import Normal

    X, y, impute_means, ohe_cols, feat_cols = _prepare_final_train(df)
    ngb = NGBRegressor(Dist=Normal, random_state=42, verbose=False, **best_params)
    ngb.fit(X, y)
    dist = ngb.pred_dist(X)
    sigma = float(np.mean(np.clip(dist.scale, _MIN_SIGMA, None)))
    print(f"\n  Final NGBoost trained on {len(y):,} rows; mean_sigma={sigma:.4f}")

    return {
        "model_type": "ngboost",
        "model": ngb,
        "sigma": sigma,
        "impute_means": impute_means,
        "ohe_categories": ohe_cols,
        "feature_names": feat_cols,
        "feature_columns": NUMERIC_FEATURES + ohe_cols,
        "cv_nll":  round(float(np.mean([r["nll"] for r in fold_records])), 4),
        "cv_mae":  round(float(np.mean([r["mae"] for r in fold_records])), 4),
        "cv_folds": len(fold_records),
        "cv_fold_records": fold_records,
    }


def _print_feature_importance(model, feat_names: list[str]) -> None:
    importances = model.feature_importances_
    ranked = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
    max_val = ranked[0][1] if ranked else 1
    print("\n── LightGBM feature importance (top 20) ────────────────────────────")
    for rank, (feat, val) in enumerate(ranked[:20], 1):
        bar = "█" * int(val / max_val * 25)
        print(f"  {rank:>3}. {feat:<50s} {val:>6}  {bar}")


# ---------------------------------------------------------------------------
# Artifact save and registry update
# ---------------------------------------------------------------------------

def save_artifact(artifact: dict, promote: bool) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / "starter_v1.pkl"
    joblib.dump(artifact, local_path)
    print(f"\n  Saved → {local_path.relative_to(_PROJECT_ROOT)}")
    if promote:
        upload_artifact(local_path, _ARTIFACT_S3)
    else:
        print("  [--no-promote] Skipping S3 upload")
    return local_path


def update_registry(
    artifact: dict,
    local_path: Path,
    best_params: dict,
    promote: bool,
    a_nll: float | None,
    b_nll: float,
    c_nll: float,
    mlflow_run_id: str | None,
) -> None:
    model_type = artifact["model_type"]
    cv_nll  = artifact["cv_nll"]
    cv_mae  = artifact["cv_mae"]
    cv_folds = artifact["cv_folds"]
    sigma   = artifact["sigma"]
    s3_path = _ARTIFACT_S3 if promote else str(local_path)
    today   = date.today().isoformat()
    run_id_line = mlflow_run_id if mlflow_run_id else "null  # set on next retrain"

    winner_note = f"A-NGBoost NLL={a_nll:.4f}" if model_type == "ngboost" and a_nll else "B-LightGBM"
    glm_note = f"C-GLM NLL={c_nll:.4f} (floor); winner NLL={cv_nll:.4f} (< GLM+{_NLL_GATE_SLACK})"

    new_block = f"""starter_v1:
  artifact_path: {s3_path}
  feature_columns_path: models/sub_models/starter_v1/feature_columns.json
  mlflow_run_id: {run_id_line}
  target:
    source_table: baseball_data.betting.mart_starting_pitcher_game_log
    primary_column: xwoba_against
    auxiliary_columns: []
    grain: game_pk_side
  training_window:
    start: '{_MIN_YEAR}-01-01'
    end: null
  cv_strategy: walk_forward_season
  cv_folds: {cv_folds}   # eval years 2023-2025 (2026 partial excluded from Optuna)
  cv_metric: normal_nll
  cv_score: {cv_nll}
  cv_mae: {cv_mae}
  normal_sigma: {round(sigma, 4)}
  promotion_gate:
    metric: normal_nll
    direction: lower_is_better
    must_beat: candidate_c_glm_nll
    secondary:
      - calib_80_ge: {_CALIB_80_GATE}
      - std_pred_ge: {_STD_PRED_GATE}
  output_signals:
    - starter_suppression_mu
    - starter_suppression_sigma
    - starter_suppression_signal
    - uncertainty
  promotion_status: champion
  promoted_at: '{today}'
  notes: |
    Story 5.2 ({today}). Training window {_MIN_YEAR}+; target = xwoba_against.
    Distribution: Normal. Model: {model_type.upper()}.
    Features: 74 numeric + OHE pitcher_hand/starter_primary_pitch_type/eb_data_source.
    {glm_note}. Winner: {winner_note}.
    sigma={round(sigma, 4)} (fit from full-dataset training residuals).
    Best params: {json.dumps(best_params)}.
"""

    text = _REGISTRY_PATH.read_text()
    pattern = r"^starter_v1:.*?(?=^\S|\Z)"
    replacement = new_block + "\n"
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if new_text == text:
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [INFO] starter_v1 not found in registry; appended")
    else:
        print(f"  Updated starter_v1 in {_REGISTRY_PATH.relative_to(_PROJECT_ROOT)}")
    _REGISTRY_PATH.write_text(new_text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train(
    promote: bool = True,
    skip_ngboost: bool = False,
    optuna_probe: int = 10,
    optuna_full: int = 50,
    dry_run: bool = False,
    min_year: int = _MIN_YEAR,
) -> str:
    print("=== EPIC 5.2 — STARTER_V1 TRAINING ===\n")
    print("Loading data from Snowflake...")
    df = load_data(min_year=min_year)
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({int(df['game_year'].min())}–{int(df['game_year'].max())})")

    optuna_folds = get_cv_folds(df, exclude_eval_year=_EXCLUDE_EVAL_YEAR)
    all_folds    = get_all_folds(df)
    eval_years_optuna = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in optuna_folds]
    eval_years_all    = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in all_folds]
    print(f"  Optuna folds: {len(optuna_folds)} (eval years {eval_years_optuna})")
    print(f"  Full CV folds: {len(all_folds)} (eval years {eval_years_all})")

    if len(optuna_folds) < 3:
        raise RuntimeError(f"Expected ≥ 3 Optuna folds, got {len(optuna_folds)}")

    if dry_run:
        print("\n  [--dry-run] Loaded data and validated folds. Exiting before training.")
        return "dry_run"

    mlflow.set_experiment("starter_suppression_v1")
    get_or_create_experiment("starter_suppression_v1")

    with mlflow.start_run(run_name=f"train_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id
        mlflow.log_params({
            "train_start": f"{min_year}-01-01",
            "n_rows": len(df),
            "n_seasons": int(df["game_year"].nunique()),
            "n_folds_optuna": len(optuna_folds),
            "n_folds_all": len(all_folds),
            "eval_years": str(eval_years_all),
            "exclude_eval_year": _EXCLUDE_EVAL_YEAR,
            "optuna_probe": optuna_probe,
            "optuna_full": optuna_full,
            "skip_ngboost": skip_ngboost,
        })

        # ── C: GLM baseline (NLL floor) ────────────────────────────────────
        c_nll, c_mae, c_std, c_calib, c_folds = cv_glm(df, all_folds)
        mlflow.log_metric("glm_cv_nll", c_nll)
        mlflow.log_metric("glm_cv_mae", c_mae)

        # ── A: NGBoost Normal ──────────────────────────────────────────────
        a_nll, a_mae, a_std, a_calib, a_folds = None, None, None, None, []
        if not skip_ngboost:
            a_nll, a_mae, a_std, a_calib, a_folds = cv_ngboost(df, all_folds)
            mlflow.log_metric("ngboost_cv_nll", a_nll)
            mlflow.log_metric("ngboost_cv_mae", a_mae)
            mlflow.log_metric("ngboost_cv_calib80", a_calib)
            mlflow.log_metric("ngboost_cv_std_pred", a_std)
            for rec in a_folds:
                log_cv_fold(rec["fold"], rec["eval_year"], {
                    "ngboost_nll": rec["nll"], "ngboost_mae": rec["mae"],
                    "ngboost_calib80": rec["calib_80"],
                })
        else:
            print("\n  [--skip-ngboost] Skipping Candidate A")

        # ── B: LightGBM + sigma ────────────────────────────────────────────
        b_nll, b_mae, b_std, b_calib, b_folds, b_feat_names, b_mean_iter = cv_lgbm(df, all_folds)
        mlflow.log_metric("lgbm_cv_nll", b_nll)
        mlflow.log_metric("lgbm_cv_mae", b_mae)
        mlflow.log_metric("lgbm_cv_calib80", b_calib)
        mlflow.log_metric("lgbm_cv_std_pred", b_std)
        for rec in b_folds:
            log_cv_fold(rec["fold"], rec["eval_year"], {
                "lgbm_nll": rec["nll"], "lgbm_mae": rec["mae"],
                "lgbm_calib80": rec["calib_80"],
                "lgbm_best_iter": rec.get("best_iteration"),
            })

        # ── Gate summary ───────────────────────────────────────────────────
        winner_type, winner_nll = print_gate_summary(
            a_nll, a_mae, a_std, a_calib,
            b_nll, b_mae, b_std, b_calib,
            c_nll, skip_ngboost=skip_ngboost,
        )
        mlflow.log_params({"winner_type": winner_type, "winner_nll": winner_nll})

        # ── Optuna tuning on winner ────────────────────────────────────────
        print(f"\n── Optuna tuning: {winner_type} ───────────────────────────────────────")
        best_params, tuned_nll = _tune_winner(
            winner_type, df, optuna_folds, n_probe=optuna_probe, n_full=optuna_full
        )
        mlflow.log_params({f"best_{k}": v for k, v in best_params.items()})
        mlflow.log_metric("tuned_cv_nll", tuned_nll)

        # ── Re-run CV with tuned params for final fold table ──────────────
        print(f"\n── Final CV with tuned params ──────────────────────────────────────")
        if winner_type == "lgbm":
            final_nll, final_mae, final_std, final_calib, final_folds, _, final_iter = cv_lgbm(
                df, all_folds, params=best_params
            )
            # Override n_estimators with tuned value if present
            if "n_estimators" in best_params:
                final_iter = best_params["n_estimators"]
        else:
            final_nll, final_mae, final_std, final_calib, final_folds = cv_ngboost(
                df, all_folds, params=best_params
            )
            final_iter = best_params.get("n_estimators", 500)

        mlflow.log_metric("final_cv_nll", final_nll)
        mlflow.log_metric("final_cv_mae", final_mae)
        mlflow.log_metric("final_cv_calib80", final_calib)

        # Save best params
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        _PARAMS_PATH.write_text(json.dumps({
            "winner_type": winner_type,
            "best_params": best_params,
            "mean_best_iteration": final_iter,
            "tuned_cv_nll": round(tuned_nll, 4),
            "final_cv_nll": round(final_nll, 4),
        }, indent=2))
        print(f"  Saved → {_PARAMS_PATH.relative_to(_PROJECT_ROOT)}")

        # ── Train final model on all data ─────────────────────────────────
        print(f"\n── Training final {winner_type} model on {_MIN_YEAR}–2026 ──────────────")
        if winner_type == "lgbm":
            artifact = train_final_lgbm(df, best_params, final_iter, final_folds)
        else:
            artifact = train_final_ngboost(df, best_params, final_folds)

        local_path = save_artifact(artifact, promote=promote)
        mlflow.log_artifact(str(local_path))
        mlflow.log_metric("final_sigma", artifact["sigma"])

        # ── Registry update ────────────────────────────────────────────────
        update_registry(
            artifact, local_path, best_params, promote,
            a_nll=a_nll, b_nll=b_nll, c_nll=c_nll,
            mlflow_run_id=mlflow_run_id,
        )

        # ── AC summary ────────────────────────────────────────────────────
        print("\n" + "=" * 64)
        print("Acceptance criteria")
        print("=" * 64)
        print(f"  CV folds completed:  {len(all_folds)} (≥ 3 required)  {'OK' if len(all_folds) >= 3 else 'FAIL'}")
        print(f"  Winner NLL:          {final_nll:.4f} vs GLM {c_nll:.4f}+{_NLL_GATE_SLACK}={c_nll+_NLL_GATE_SLACK:.4f}  "
              f"{'OK' if final_nll <= c_nll + _NLL_GATE_SLACK else 'FAIL'}")
        print(f"  std(pred):           {final_std:.4f} (≥ {_STD_PRED_GATE})  {'OK' if final_std >= _STD_PRED_GATE else 'FAIL'}")
        print(f"  calib_80:            {final_calib:.3f} (≥ {_CALIB_80_GATE})  {'OK' if final_calib >= _CALIB_80_GATE else 'FAIL'}")
        print(f"  MAE:                 {final_mae:.4f} (expect 0.030–0.055)")
        print(f"  sigma:               {artifact['sigma']:.4f}")
        print(f"  MLflow run_id:       {mlflow_run_id}")
        print(f"  S3 artifact:         {'uploaded' if promote else 'skipped (--no-promote)'}")

    return mlflow_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 5.2 — train starter_v1 Normal distributional model")
    parser.add_argument("--no-promote",    action="store_true", help="Skip S3 upload")
    parser.add_argument("--skip-ngboost",  action="store_true", help="Skip Candidate A (NGBoost) for faster run")
    parser.add_argument("--optuna-probe",  type=int, default=10,  help="Optuna probe trials (default: 10)")
    parser.add_argument("--optuna-full",   type=int, default=50,  help="Optuna full trials (default: 50)")
    parser.add_argument("--dry-run",       action="store_true",   help="Load data and validate folds only")
    parser.add_argument("--min-year",      type=int, default=_MIN_YEAR, help=f"Training start year (default: {_MIN_YEAR})")
    args = parser.parse_args()

    train(
        promote=not args.no_promote,
        skip_ngboost=args.skip_ngboost,
        optuna_probe=args.optuna_probe,
        optuna_full=args.optuna_full,
        dry_run=args.dry_run,
        min_year=args.min_year,
    )


if __name__ == "__main__":
    main()
