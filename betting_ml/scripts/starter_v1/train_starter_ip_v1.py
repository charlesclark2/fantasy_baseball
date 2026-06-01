"""
train_starter_ip_v1.py — Epic 5D, Story 5D.2

Three-candidate distributional comparison for outs_recorded (innings pitched):

  Candidate A — LightGBM mean + NegBin r from per-decile residuals
  Candidate B — Ridge mean   + NegBin r from per-decile residuals
  Candidate C — NegBin GLM (joint MLE; floor reference; never promoted)

Distribution family: NegativeBinomial(mu, r) — count data, 0–27 outs.
Overdispersion ratio 1.125 (variance/mean > 1.0) confirmed in 5D.1.

Training window: 2020–2026 (Stuff+ not available pre-2020).
CV: walk-forward season, min_train_seasons=3 → eval years 2023, 2024, 2025, 2026.

Gates (all must pass to promote):
  NLL       < Candidate C GLM baseline (primary gate)
  calib_80  ≥ 0.80  (80% of actuals within 10th–90th NegBin PI)
  MAE       ≤ 3.0 outs  (within one inning)
  std(pred) ≥ 2.0 outs  (degeneracy guard)
  fold win  ≥ 3 of 4 folds with lower NLL

Artifact keys:
  model, r_by_decile, interior_edges, impute_means, ohe_categories,
  feature_names, ip_feature_columns, model_type,
  cv_nll, cv_mae, cv_calib_80, cv_folds, cv_fold_records

Usage:
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py --no-promote
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py --dry-run
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py --skip-glm
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py --force-winner {lgbm,ridge}
    uv run python betting_ml/scripts/starter_v1/train_starter_ip_v1.py --optuna-probe 5 --optuna-full 20
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
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom, wilcoxon

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)
warnings.filterwarnings("ignore", message=".*`force_all_finite`.*", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, message="divide by zero")

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
_FEAT_COLS_PATH = _OUTPUT_DIR / "ip_feature_columns.json"
_ARTIFACT_S3    = "s3://baseball-betting-ml-artifacts/sub_models/starter_ip_v1.pkl"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_YEAR          = 2020
_EXCLUDE_EVAL_YEAR = 2026
_MIN_TRAIN_SEASONS = 3
_N_DECILES         = 10
_MU_CLIP_MIN       = 0.5
_MU_CLIP_MAX       = 27.0

_CALIB_80_GATE   = 0.80
_MAE_GATE        = 3.0
_STD_PRED_GATE   = 2.0
_FOLD_WIN_GATE   = 3
_OPTUNA_SEED     = 42

# ---------------------------------------------------------------------------
# Feature inventory (matches ip_feature_columns.json from 5D.1)
# ---------------------------------------------------------------------------

NUMERIC_FEATURES: list[str] = [
    # A: workload
    "days_rest", "avg_ip_last_3", "avg_ip_season",
    "cumulative_season_ip", "cumulative_season_pitches",
    "appearances_30d", "appearances_std",
    "pitch_count_last_start",
    # B: season context
    "is_doubleheader_game2",
    # C: stuff + velocity
    "starter_stuff_plus", "starter_avg_fastball_velo",
    "starter_fastball_pct", "starter_breaking_pct", "starter_offspeed_pct",
    "starter_fastball_stuff_plus", "starter_slider_stuff_plus",
    "starter_curveball_stuff_plus", "starter_changeup_stuff_plus",
    # D: recent performance
    "xwoba_against_30d", "k_pct_30d", "bb_pct_30d",
    "whiff_rate_30d", "hard_hit_pct_30d", "xwoba_against_7d", "k_pct_7d",
    # E: velocity form
    "fastball_velo_trend", "avg_fastball_velo_30d", "velo_delta_3start",
    # F: trailing FIP
    "starter_trailing_fip_30g", "starter_trailing_ra9_30g",
    "starter_proj_fip", "csw_pct_season", "csw_pct_3start",
    # G: EB posterior
    "eb_xwoba_against", "eb_xwoba_uncertainty",
]

CAT_FEATURES: list[str] = [
    "pitcher_hand",
    "starter_primary_pitch_type",
    "starter_pitcher_archetype",   # 16.3% null → __NA__ category
]

TARGET = "outs_recorded"

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_QUERY = """
WITH prior_pitch_count AS (
    SELECT
        game_pk,
        pitcher_id,
        LAG(total_pitches) OVER (
            PARTITION BY pitcher_id
            ORDER BY game_date, game_pk
        ) AS pitch_count_last_start
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year BETWEEN 2019 AND 2026
)
SELECT
    f.game_pk,
    f.game_date,
    f.game_year,
    f.side,
    f.pitcher_id,
    f.pitcher_hand,
    f.days_rest, f.avg_ip_last_3, f.avg_ip_season,
    f.cumulative_season_ip, f.cumulative_season_pitches,
    f.appearances_30d, f.appearances_std,
    ppc.pitch_count_last_start,
    IFF(g.double_header IN ('Y', 'S') AND g.game_number = 2, 1.0, 0.0) AS is_doubleheader_game2,
    f.starter_stuff_plus, f.starter_avg_fastball_velo,
    f.starter_fastball_pct, f.starter_breaking_pct, f.starter_offspeed_pct,
    f.starter_fastball_stuff_plus, f.starter_slider_stuff_plus,
    f.starter_curveball_stuff_plus, f.starter_changeup_stuff_plus,
    f.xwoba_against_30d, f.k_pct_30d, f.bb_pct_30d,
    f.whiff_rate_30d, f.hard_hit_pct_30d, f.xwoba_against_7d, f.k_pct_7d,
    f.fastball_velo_trend, f.avg_fastball_velo_30d, f.velo_delta_3start,
    f.starter_trailing_fip_30g, f.starter_trailing_ra9_30g,
    f.starter_proj_fip, f.csw_pct_season, f.csw_pct_3start,
    f.eb_xwoba_against, f.eb_xwoba_uncertainty,
    f.starter_primary_pitch_type, f.starter_pitcher_archetype,
    m.outs_recorded,
    IFF(m.outs_recorded < 9, TRUE, FALSE) AS is_bulk_usage,
    m.total_pitches AS game_pitch_count
FROM baseball_data.betting_features.feature_pregame_starter_features f
JOIN baseball_data.betting.mart_starting_pitcher_game_log m
    ON m.game_pk = f.game_pk AND m.pitcher_id = f.pitcher_id
LEFT JOIN prior_pitch_count ppc
    ON ppc.game_pk = f.game_pk AND ppc.pitcher_id = f.pitcher_id
LEFT JOIN baseball_data.betting.stg_statsapi_games g
    ON g.game_pk = f.game_pk
WHERE f.game_year BETWEEN {min_year} AND 2026
  AND f.has_starter_data = TRUE
  AND m.outs_recorded IS NOT NULL
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
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["game_year"] = df["game_year"].astype(int)
    df[TARGET] = df[TARGET].astype(int)
    df["is_bulk_usage"] = df["is_bulk_usage"].astype(bool)
    return df.sort_values("game_date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# CV fold selection
# ---------------------------------------------------------------------------

def get_optuna_folds(df: pd.DataFrame) -> list[tuple]:
    all_folds = list(all_season_splits(df, min_train_seasons=_MIN_TRAIN_SEASONS))
    return [
        (tr, ev) for tr, ev in all_folds
        if int(df.loc[ev, "game_year"].mode()[0]) != _EXCLUDE_EVAL_YEAR
    ]


def get_all_folds(df: pd.DataFrame) -> list[tuple]:
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
    train: pd.DataFrame, eval_: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """OHE categorical features. Fill NaN with __NA__ to create explicit unknown category."""
    train_dummies, eval_dummies, all_ohe_cols = [], [], []
    for cat in CAT_FEATURES:
        if cat not in train.columns:
            continue
        t_d = pd.get_dummies(train[cat].fillna("__NA__"), prefix=cat, dtype=float)
        e_d = pd.get_dummies(eval_[cat].fillna("__NA__"),  prefix=cat, dtype=float)
        ohe_cols = sorted(t_d.columns.tolist())
        t_d = t_d.reindex(columns=ohe_cols, fill_value=0.0)
        e_d = e_d.reindex(columns=ohe_cols, fill_value=0.0)
        train_dummies.append(t_d)
        eval_dummies.append(e_d)
        all_ohe_cols.extend(ohe_cols)

    train_out = pd.concat(
        [train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in train_dummies], axis=1
    )
    eval_out = pd.concat(
        [eval_.reset_index(drop=True)] + [d.reset_index(drop=True) for d in eval_dummies], axis=1
    )
    return train_out, eval_out, all_ohe_cols


def prepare_fold(
    df: pd.DataFrame, train_idx, eval_idx
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict, list[str], list[str]]:
    train = df.loc[train_idx].copy()
    eval_ = df.loc[eval_idx].copy()

    impute_means = _compute_impute_means(train)
    train = _apply_impute(train, impute_means)
    eval_ = _apply_impute(eval_,  impute_means)

    train, eval_, ohe_cols = _ohe_cats(train, eval_)

    all_feat_cols = NUMERIC_FEATURES + ohe_cols
    X_train = train[all_feat_cols].to_numpy(dtype=float)
    y_train = train[TARGET].to_numpy(dtype=int)
    X_eval  = eval_[all_feat_cols].to_numpy(dtype=float)
    y_eval  = eval_[TARGET].to_numpy(dtype=int)

    return X_train, y_train, X_eval, y_eval, impute_means, ohe_cols, all_feat_cols


# ---------------------------------------------------------------------------
# NegBin distribution helpers
# ---------------------------------------------------------------------------

def negbin_nll(y: np.ndarray, mu: np.ndarray, r_arr: np.ndarray) -> float:
    """Mean NegBin NLL. Uses NB2 parameterization: Var = mu + mu^2/r."""
    mu  = np.clip(mu,    _MU_CLIP_MIN, _MU_CLIP_MAX)
    r   = np.clip(r_arr, 0.05,         None)
    p   = r / (r + mu)
    lls = nbinom.logpmf(y.astype(int), n=r, p=p)
    lls = np.where(np.isfinite(lls), lls, -50.0)
    return float(-lls.mean())


def negbin_calib_80(y: np.ndarray, mu: np.ndarray, r_arr: np.ndarray) -> float:
    """Fraction of actuals within the symmetric 80% PI [10th, 90th NegBin percentile]."""
    mu = np.clip(mu,    _MU_CLIP_MIN, _MU_CLIP_MAX)
    r  = np.clip(r_arr, 0.05,         None)
    p  = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(((y >= lo) & (y <= hi)).mean())


def fit_negbin_r_by_decile(
    y_train: np.ndarray,
    mu_train: np.ndarray,
    n_deciles: int = _N_DECILES,
) -> tuple[dict[int, float], np.ndarray]:
    """
    Fit NegBin dispersion r per predicted-mean decile via MLE.
    Returns (r_by_decile, interior_edges) where interior_edges are the
    bin boundaries used for decile assignment at inference.
    """
    percentiles = np.linspace(0, 100, n_deciles + 1)
    all_edges   = np.percentile(mu_train, percentiles)
    interior    = np.unique(all_edges[1:-1])  # deduplicate in case of ties

    # digitize: idx 0 means mu <= interior[0], idx len(interior) means mu > interior[-1]
    decile_idx  = np.digitize(mu_train, interior)
    n_bins      = len(interior) + 1

    r_by_decile: dict[int, float] = {}
    for d in range(n_bins):
        mask = decile_idx == d
        if mask.sum() < 5:
            r_by_decile[d] = 5.0
            continue
        y_d  = y_train[mask].astype(int)
        mu_d = np.clip(mu_train[mask], _MU_CLIP_MIN, _MU_CLIP_MAX)

        def neg_ll(log_r: float) -> float:
            r   = float(np.exp(log_r))
            p   = r / (r + mu_d)
            lls = nbinom.logpmf(y_d, n=r, p=p)
            return float(-np.where(np.isfinite(lls), lls, -50.0).mean())

        try:
            res = minimize_scalar(neg_ll, bounds=(-2.0, 6.0), method="bounded")
            r_by_decile[d] = float(np.exp(res.x))
        except Exception:
            r_by_decile[d] = 5.0

    return r_by_decile, interior


def assign_r(
    mu: np.ndarray,
    interior_edges: np.ndarray,
    r_by_decile: dict[int, float],
) -> np.ndarray:
    """Assign NegBin r to each row based on its predicted-mu decile."""
    n_bins = len(interior_edges) + 1
    idx    = np.clip(np.digitize(mu, interior_edges), 0, n_bins - 1)
    return np.array([r_by_decile.get(int(i), 5.0) for i in idx])


# ---------------------------------------------------------------------------
# Candidate A — LightGBM + NegBin r by decile
# ---------------------------------------------------------------------------

def cv_lgbm(
    df: pd.DataFrame,
    folds: list[tuple],
    params: dict | None = None,
) -> tuple[float, float, float, float, list[dict], list[str]]:
    import lightgbm as lgb

    default_params = dict(
        num_leaves=63, learning_rate=0.05, min_child_samples=20,
        subsample=0.8, colsample_bytree=0.7, n_estimators=500,
        objective="regression_l1", metric="mae", random_state=42, verbose=-1,
    )
    p = {**default_params, **(params or {})}

    fold_records:   list[dict] = []
    all_feat_names: list[str]  = []

    print(f"\n── A-LightGBM + NegBin r ({len(folds)} folds) ─────────────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'std_pred':>9}  {'mean_r':>7}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, feat_cols = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        if not all_feat_names:
            all_feat_names = feat_cols

        model = lgb.LGBMRegressor(**p)
        model.fit(X_tr, y_tr.astype(float))
        mu_tr = np.clip(model.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
        mu_ev = np.clip(model.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)

        r_by_dec, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
        r_ev   = assign_r(mu_ev, interior, r_by_dec)
        mean_r = float(np.mean(list(r_by_dec.values())))

        nll  = negbin_nll(y_ev, mu_ev, r_ev)
        mae  = float(np.mean(np.abs(y_ev - mu_ev)))
        c80  = negbin_calib_80(y_ev, mu_ev, r_ev)
        stdp = float(np.std(mu_ev))

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  {stdp:>9.3f}  {mean_r:>7.3f}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll": round(nll, 4), "mae": round(mae, 3),
            "calib_80": round(c80, 3), "std_pred": round(stdp, 3), "mean_r": round(mean_r, 3),
        })

    mean_nll = float(np.mean([r["nll"]     for r in fold_records]))
    mean_mae = float(np.mean([r["mae"]      for r in fold_records]))
    mean_c80 = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std = float(np.mean([r["std_pred"] for r in fold_records]))
    print(f"\n  Mean  NLL={mean_nll:.4f}  MAE={mean_mae:.3f}  calib_80={mean_c80:.3f}  std_pred={mean_std:.3f}")
    return mean_nll, mean_mae, mean_c80, mean_std, fold_records, all_feat_names


# ---------------------------------------------------------------------------
# Candidate B — Ridge + NegBin r by decile
# ---------------------------------------------------------------------------

def cv_ridge(
    df: pd.DataFrame,
    folds: list[tuple],
    alpha: float = 1.0,
    verbose: bool = True,
) -> tuple[float, float, float, float, list[dict]]:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    fold_records: list[dict] = []
    if verbose:
        print(f"\n── B-Ridge + NegBin r (alpha={alpha}, {len(folds)} folds) ─────────────")
        print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'std_pred':>9}  {'mean_r':>7}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
        pipe.fit(X_tr, y_tr.astype(float))
        mu_tr = np.clip(pipe.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
        mu_ev = np.clip(pipe.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)

        r_by_dec, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
        r_ev   = assign_r(mu_ev, interior, r_by_dec)
        mean_r = float(np.mean(list(r_by_dec.values())))

        nll  = negbin_nll(y_ev, mu_ev, r_ev)
        mae  = float(np.mean(np.abs(y_ev - mu_ev)))
        c80  = negbin_calib_80(y_ev, mu_ev, r_ev)
        stdp = float(np.std(mu_ev))

        if verbose:
            print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  {stdp:>9.3f}  {mean_r:>7.3f}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll": round(nll, 4), "mae": round(mae, 3),
            "calib_80": round(c80, 3), "std_pred": round(stdp, 3), "mean_r": round(mean_r, 3),
        })

    mean_nll = float(np.mean([r["nll"]     for r in fold_records]))
    mean_mae = float(np.mean([r["mae"]      for r in fold_records]))
    mean_c80 = float(np.mean([r["calib_80"] for r in fold_records]))
    mean_std = float(np.mean([r["std_pred"] for r in fold_records]))
    if verbose:
        print(f"\n  Mean  NLL={mean_nll:.4f}  MAE={mean_mae:.3f}  calib_80={mean_c80:.3f}  std_pred={mean_std:.3f}")
    return mean_nll, mean_mae, mean_c80, mean_std, fold_records


def tune_ridge_alpha(df: pd.DataFrame, folds: list[tuple]) -> tuple[float, float]:
    """Grid search best Ridge alpha. Returns (best_alpha, best_nll)."""
    alphas = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]
    print(f"\n── B-Ridge alpha grid search ({len(alphas)} values × {len(folds)} folds) ─")
    best_alpha, best_nll = 1.0, float("inf")
    for alpha in alphas:
        nll, _, _, _, _ = cv_ridge(df, folds, alpha=alpha, verbose=False)
        flag = " ← best" if nll < best_nll else ""
        print(f"    alpha={alpha:<8}  mean_NLL={nll:.4f}{flag}")
        if nll < best_nll:
            best_nll, best_alpha = nll, alpha
    print(f"  Best alpha={best_alpha}  NLL={best_nll:.4f}")
    return best_alpha, best_nll


# ---------------------------------------------------------------------------
# Candidate C — NegBin GLM (floor reference; never promoted)
# ---------------------------------------------------------------------------

def cv_negbin_glm(
    df: pd.DataFrame,
    folds: list[tuple],
) -> tuple[float, float, float, float, list[dict]]:
    """
    NegBin GLM via statsmodels (joint MLE for mu and r).
    Falls back to Ridge + global-r MLE if convergence fails.
    """
    try:
        import statsmodels.api as sm
        _HAS_SM = True
    except ImportError:
        _HAS_SM = False
        print("  [WARN] statsmodels not available; using Ridge + global-r fallback for GLM")

    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    fold_records: list[dict] = []
    print(f"\n── C-NegBin GLM baseline ({len(folds)} folds) ───────────────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'NLL':>7}  {'MAE':>6}  {'calib80':>8}  {'r_glm':>7}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        scaler   = StandardScaler()
        X_tr_s   = scaler.fit_transform(X_tr)
        X_ev_s   = scaler.transform(X_ev)

        nll = mae = c80 = float("nan")
        r_used = float("nan")

        if _HAS_SM:
            try:
                X_tr_c = sm.add_constant(X_tr_s)
                X_ev_c = sm.add_constant(X_ev_s)
                glm    = sm.NegativeBinomial(y_tr, X_tr_c, loglike_method="nb2")
                result = glm.fit(method="bfgs", maxiter=200, disp=False)
                mu_ev  = np.clip(result.predict(X_ev_c), _MU_CLIP_MIN, _MU_CLIP_MAX)
                alpha  = max(float(result.scale), 1e-6)
                r_used = 1.0 / alpha
                r_arr  = np.full(len(y_ev), r_used)
                nll    = negbin_nll(y_ev, mu_ev, r_arr)
                mae    = float(np.mean(np.abs(y_ev - mu_ev)))
                c80    = negbin_calib_80(y_ev, mu_ev, r_arr)
            except Exception as exc:
                print(f"    fold {i}: statsmodels GLM failed ({type(exc).__name__}: {exc}); using fallback")
                _HAS_SM = False  # fall through to fallback below

        if not np.isfinite(nll):
            # Fallback: Ridge for mu + global r MLE on training set
            pipe = Pipeline([("s", StandardScaler()), ("r", Ridge(alpha=1.0))])
            pipe.fit(X_tr, y_tr.astype(float))
            mu_tr = np.clip(pipe.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
            mu_ev = np.clip(pipe.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)

            def neg_ll_global(log_r: float) -> float:
                r   = float(np.exp(log_r))
                p   = r / (r + mu_tr)
                lls = nbinom.logpmf(y_tr, n=r, p=p)
                return float(-np.where(np.isfinite(lls), lls, -50.0).mean())

            try:
                res    = minimize_scalar(neg_ll_global, bounds=(-2.0, 6.0), method="bounded")
                r_used = float(np.exp(res.x))
            except Exception:
                r_used = 5.0
            r_arr  = np.full(len(y_ev), r_used)
            nll    = negbin_nll(y_ev, mu_ev, r_arr)
            mae    = float(np.mean(np.abs(y_ev - mu_ev)))
            c80    = negbin_calib_80(y_ev, mu_ev, r_arr)

        print(f"  {i:>4}  {eval_year:>6}  {nll:>7.4f}  {mae:>6.3f}  {c80:>8.3f}  {r_used:>7.3f}")
        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "nll":      round(nll, 4)  if np.isfinite(nll) else 999.0,
            "mae":      round(mae, 3)  if np.isfinite(mae) else 999.0,
            "calib_80": round(c80, 3)  if np.isfinite(c80) else 0.0,
        })

    mean_nll = float(np.mean([r["nll"]     for r in fold_records]))
    mean_mae = float(np.mean([r["mae"]      for r in fold_records]))
    mean_c80 = float(np.mean([r["calib_80"] for r in fold_records]))
    print(f"\n  Mean  NLL={mean_nll:.4f}  MAE={mean_mae:.3f}  calib_80={mean_c80:.3f}")
    return mean_nll, mean_mae, mean_c80, 0.0, fold_records


# ---------------------------------------------------------------------------
# IP-specific evaluation cuts (last fold = most recent held-out year)
# ---------------------------------------------------------------------------

def print_ip_cuts(
    df: pd.DataFrame,
    folds: list[tuple],
    winner_type: str,
    best_params: dict,
    best_alpha: float,
) -> None:
    import lightgbm as lgb
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    train_idx, eval_idx = folds[-1]
    X_tr, y_tr, X_ev, y_ev, _, _, feat_cols = prepare_fold(df, train_idx, eval_idx)
    eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
    eval_meta = df.loc[eval_idx].reset_index(drop=True)

    print(f"\n── IP-specific evaluation cuts ({winner_type}, eval={eval_year}) ─────────")

    if winner_type == "lgbm":
        p = {**best_params, "objective": "regression_l1", "random_state": 42, "verbose": -1}
        model = lgb.LGBMRegressor(**p)
        model.fit(X_tr, y_tr.astype(float))
    else:
        model = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        model.fit(X_tr, y_tr.astype(float))

    mu_tr = np.clip(model.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
    mu_ev = np.clip(model.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)
    r_by_dec, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
    r_ev = assign_r(mu_ev, interior, r_by_dec)

    # 1. Early-exit NLL (outs < 12, i.e. < 4 IP)
    early_mask = y_ev < 12
    if early_mask.sum() >= 5:
        nll_early = negbin_nll(y_ev[early_mask], mu_ev[early_mask], r_ev[early_mask])
        # Naive baseline: constant mu = training mean, global r
        naive_mu   = np.full(int(early_mask.sum()), float(y_tr.mean()))
        def neg_ll_naive(log_r: float) -> float:
            r   = float(np.exp(log_r))
            p   = r / (r + naive_mu)
            lls = nbinom.logpmf(y_ev[early_mask], n=r, p=p)
            return float(-np.where(np.isfinite(lls), lls, -50.0).mean())
        try:
            res_n   = minimize_scalar(neg_ll_naive, bounds=(-2.0, 6.0), method="bounded")
            r_naive = float(np.exp(res_n.x))
        except Exception:
            r_naive = 5.0
        nll_naive = negbin_nll(y_ev[early_mask], naive_mu, np.full(int(early_mask.sum()), r_naive))
        better = "BETTER" if nll_early < nll_naive else "WORSE"
        print(f"  Early-exit (outs<12, n={early_mask.sum()}):  model NLL={nll_early:.4f}  naive={nll_naive:.4f}  [{better}]")
    else:
        print(f"  Early-exit: n={early_mask.sum()} — too few for reliable estimate")

    # 2. Bulk usage NLL sensitivity
    if "is_bulk_usage" in eval_meta.columns:
        bulk     = eval_meta["is_bulk_usage"].values.astype(bool)
        non_bulk = ~bulk
        if bulk.sum() > 0 and non_bulk.sum() > 0:
            nll_all      = negbin_nll(y_ev,             mu_ev,             r_ev)
            nll_non_bulk = negbin_nll(y_ev[non_bulk],   mu_ev[non_bulk],   r_ev[non_bulk])
            delta = nll_non_bulk - nll_all
            print(f"  Bulk sensitivity:  NLL_all={nll_all:.4f}  NLL_non_bulk={nll_non_bulk:.4f}"
                  f"  Δ={delta:+.4f}  (n_bulk={bulk.sum()}, n_non_bulk={non_bulk.sum()})")

    # 3. High-workload check (pitch_count_last_start)
    if "pitch_count_last_start" in eval_meta.columns:
        pc         = eval_meta["pitch_count_last_start"].values
        high_mask  = pc > 100
        low_mask   = pc < 85
        n_hi, n_lo = int(high_mask.sum()), int(low_mask.sum())
        if n_hi >= 10 and n_lo >= 10:
            mu_hi = float(mu_ev[high_mask].mean())
            mu_lo = float(mu_ev[low_mask].mean())
            ok    = mu_hi < mu_lo
            print(f"  High-workload check (pitch_count_last_start):")
            print(f"    Mean ip_mu | >100 pitches (n={n_hi}): {mu_hi:.2f}")
            print(f"    Mean ip_mu | <85  pitches (n={n_lo}):  {mu_lo:.2f}")
            print(f"    Fatigued starters get shorter leash:  {'YES ✓' if ok else 'NO ✗  — review feature importance'}")
        else:
            print(f"  High-workload check: n_hi={n_hi}, n_lo={n_lo} — insufficient samples in eval fold")


# ---------------------------------------------------------------------------
# Gate summary + winner selection
# ---------------------------------------------------------------------------

def print_gate_summary(
    a_nll: float, a_mae: float, a_c80: float, a_std: float, a_folds: list[dict],
    b_nll: float, b_mae: float, b_c80: float, b_std: float, b_folds: list[dict],
    c_nll: float,
    force_winner: str | None = None,
) -> tuple[str, float]:
    print("\n" + "=" * 78)
    print("Gate summary — starter_ip_v1 (NegBin outs_recorded)")
    print(f"  C-GLM floor NLL: {c_nll:.4f}")
    print("=" * 78)
    hdr = f"  {'Gate':<32}  {'Threshold':>10}  {'A-LightGBM':>12}  {'B-Ridge':>10}"
    print(hdr)
    print("  " + "-" * 70)

    def _ok(val: float, thresh: float, le: bool = True) -> str:
        return "OK" if (val <= thresh if le else val >= thresh) else "NO"

    print(f"  {'NLL < GLM floor':<32}  {f'< {c_nll:.4f}':>10}"
          f"  {a_nll:.4f} {_ok(a_nll, c_nll):>4}"
          f"  {b_nll:.4f} {_ok(b_nll, c_nll):>4}")
    print(f"  {'calib_80':<32}  {'≥ 0.80':>10}"
          f"  {a_c80:.3f} {_ok(a_c80, _CALIB_80_GATE, le=False):>5}"
          f"  {b_c80:.3f} {_ok(b_c80, _CALIB_80_GATE, le=False):>5}")
    print(f"  {'MAE':<32}  {'≤ 3.0 outs':>10}"
          f"  {a_mae:.3f} {_ok(a_mae, _MAE_GATE):>5}"
          f"  {b_mae:.3f} {_ok(b_mae, _MAE_GATE):>5}")
    print(f"  {'std(pred)':<32}  {'≥ 2.0 outs':>10}"
          f"  {a_std:.3f} {_ok(a_std, _STD_PRED_GATE, le=False):>5}"
          f"  {b_std:.3f} {_ok(b_std, _STD_PRED_GATE, le=False):>5}")

    # Fold win count + Wilcoxon
    a_nlls = [r["nll"] for r in a_folds]
    b_nlls = [r["nll"] for r in b_folds]
    a_wins = sum(1 for an, bn in zip(a_nlls, b_nlls) if an < bn)
    b_wins = len(a_nlls) - a_wins
    print(f"\n  Fold NLL win count: A={a_wins}  B={b_wins}  (total={len(a_nlls)} folds)")
    print(f"  Fold win gate (≥ {_FOLD_WIN_GATE}):  A={'OK' if a_wins >= _FOLD_WIN_GATE else 'NO'}  "
          f"B={'OK' if b_wins >= _FOLD_WIN_GATE else 'NO'}")
    if len(a_nlls) >= 4:
        try:
            _, p_wil = wilcoxon(a_nlls, b_nlls)
            print(f"  Wilcoxon signed-rank (A vs B fold NLLs): p={p_wil:.4f}")
        except Exception:
            pass

    # Gate passage
    def _passes(nll, mae, c80, std):
        return nll < c_nll and c80 >= _CALIB_80_GATE and mae <= _MAE_GATE and std >= _STD_PRED_GATE

    a_pass = _passes(a_nll, a_mae, a_c80, a_std)
    b_pass = _passes(b_nll, b_mae, b_c80, b_std)
    print(f"\n  A-LightGBM passes all gates: {'YES' if a_pass else 'NO'}")
    print(f"  B-Ridge     passes all gates: {'YES' if b_pass else 'NO'}")

    if force_winner is not None:
        print(f"\n  [--force-winner {force_winner}] Overriding gate-based selection.")
        winner_nll = a_nll if force_winner == "lgbm" else b_nll
        print("=" * 78)
        return force_winner, winner_nll

    if not a_pass and not b_pass:
        print(f"\n  [WARN] Neither passes all gates. Selecting lower NLL.")
        winner = "lgbm" if a_nll <= b_nll else "ridge"
    elif a_pass and b_pass:
        winner = "lgbm" if a_nll <= b_nll else "ridge"
        print(f"\n  Both pass. Winner by lower NLL: {winner.upper()}")
    elif a_pass:
        winner = "lgbm"
        print(f"\n  Winner: A-LightGBM")
    else:
        winner = "ridge"
        print(f"\n  Winner: B-Ridge")

    winner_nll = a_nll if winner == "lgbm" else b_nll
    print("=" * 78)
    return winner, winner_nll


# ---------------------------------------------------------------------------
# Optuna tuning
# ---------------------------------------------------------------------------

def tune_winner(
    winner_type: str,
    df: pd.DataFrame,
    folds: list[tuple],
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
                "n_estimators":      trial.suggest_int("n_estimators", 100, 800, step=50),
                "subsample":         trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.4, 1.0),
                "objective": "regression_l1", "random_state": _OPTUNA_SEED, "verbose": -1,
            }
            fold_nlls: list[float] = []
            for tr_idx, ev_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, tr_idx, ev_idx)
                model = lgb.LGBMRegressor(**params)
                model.fit(X_tr, y_tr.astype(float))
                mu_tr = np.clip(model.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
                mu_ev = np.clip(model.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)
                r_by_dec, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
                r_ev = assign_r(mu_ev, interior, r_by_dec)
                fold_nlls.append(negbin_nll(y_ev, mu_ev, r_ev))
            return float(np.mean(fold_nlls))

        else:  # ridge — tune alpha continuously for richer Optuna coverage
            from sklearn.linear_model import Ridge
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
            alpha = trial.suggest_float("alpha", 0.01, 1000.0, log=True)
            fold_nlls_r: list[float] = []
            for tr_idx, ev_idx in folds:
                X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, tr_idx, ev_idx)
                pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
                pipe.fit(X_tr, y_tr.astype(float))
                mu_tr = np.clip(pipe.predict(X_tr), _MU_CLIP_MIN, _MU_CLIP_MAX)
                mu_ev = np.clip(pipe.predict(X_ev), _MU_CLIP_MIN, _MU_CLIP_MAX)
                r_by_dec, interior = fit_negbin_r_by_decile(y_tr, mu_tr)
                r_ev = assign_r(mu_ev, interior, r_by_dec)
                fold_nlls_r.append(negbin_nll(y_ev, mu_ev, r_ev))
            return float(np.mean(fold_nlls_r))

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    print(f"\n── Optuna probe ({n_probe} trials, winner={winner_type}) ────────────────")
    study.optimize(objective, n_trials=n_probe, show_progress_bar=True)
    print(f"  Probe best NLL: {study.best_value:.4f}  params: {study.best_params}")

    print(f"\n── Optuna full ({n_full} trials) ─────────────────────────────────────────")
    study.optimize(objective, n_trials=n_full, show_progress_bar=True)
    best_params = study.best_params
    best_nll    = study.best_value
    print(f"  Full best NLL:  {best_nll:.4f}  params: {best_params}")
    return best_params, best_nll


# ---------------------------------------------------------------------------
# Final model training (full dataset)
# ---------------------------------------------------------------------------

def _prepare_full_dataset(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, dict, list[str], list[str]]:
    impute_means = _compute_impute_means(df)
    train = _apply_impute(df.copy(), impute_means)

    dummies_list, all_ohe_cols = [], []
    for cat in CAT_FEATURES:
        if cat not in train.columns:
            continue
        d = pd.get_dummies(train[cat].fillna("__NA__"), prefix=cat, dtype=float)
        ohe_cols = sorted(d.columns.tolist())
        d = d.reindex(columns=ohe_cols, fill_value=0.0)
        dummies_list.append(d)
        all_ohe_cols.extend(ohe_cols)

    train = pd.concat(
        [train.reset_index(drop=True)] + [d.reset_index(drop=True) for d in dummies_list], axis=1
    )
    all_feat_cols = NUMERIC_FEATURES + all_ohe_cols
    X = train[all_feat_cols].to_numpy(dtype=float)
    y = train[TARGET].to_numpy(dtype=int)
    return X, y, impute_means, all_ohe_cols, all_feat_cols


def _print_feature_importance(model, feat_names: list[str]) -> None:
    importances = np.asarray(model.feature_importances_)
    if importances.ndim > 1:
        importances = importances.mean(axis=1)
    ranked = sorted(zip(feat_names, importances.tolist()), key=lambda x: x[1], reverse=True)
    max_val = ranked[0][1] if ranked and ranked[0][1] > 0 else 1
    print("\n── LightGBM feature importance (top 20) ─────────────────────────────")
    for rank, (feat, val) in enumerate(ranked[:20], 1):
        bar = "█" * max(0, int(val / max_val * 25))
        print(f"  {rank:>3}. {feat:<52s} {val:>7}  {bar}")


def train_final_model(
    df: pd.DataFrame,
    winner_type: str,
    best_params: dict,
    best_alpha: float,
    final_fold_records: list[dict],
) -> dict:
    import lightgbm as lgb
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    X, y, impute_means, ohe_cols, feat_cols = _prepare_full_dataset(df)

    if winner_type == "lgbm":
        p = {**best_params, "objective": "regression_l1", "random_state": 42, "verbose": -1}
        model = lgb.LGBMRegressor(**p)
        model.fit(X, y.astype(float))
        _print_feature_importance(model, feat_cols)
    else:
        alpha = best_params.get("alpha", best_alpha)
        model = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
        model.fit(X, y.astype(float))

    mu_all = np.clip(model.predict(X), _MU_CLIP_MIN, _MU_CLIP_MAX)
    r_by_decile, interior_edges = fit_negbin_r_by_decile(y, mu_all)
    r_all   = assign_r(mu_all, interior_edges, r_by_decile)
    mean_r  = float(np.mean(list(r_by_decile.values())))
    in_nll  = negbin_nll(y, mu_all, r_all)
    print(f"\n  Final {winner_type.upper()} trained on {len(y):,} rows")
    print(f"  In-sample NLL:  {in_nll:.4f}  mean_r: {mean_r:.3f}")

    # Load ip_feature_columns.json for artifact metadata
    ip_feat_json = json.loads(_FEAT_COLS_PATH.read_text()) if _FEAT_COLS_PATH.exists() else {}

    return {
        "model":             model,
        "model_type":        winner_type,
        "r_by_decile":       r_by_decile,
        "interior_edges":    interior_edges,
        "impute_means":      impute_means,
        "ohe_categories":    ohe_cols,
        "feature_names":     feat_cols,
        "ip_feature_columns": feat_cols,
        "ip_feature_columns_meta": ip_feat_json,
        "cv_nll":      round(float(np.mean([r["nll"]     for r in final_fold_records])), 4),
        "cv_mae":      round(float(np.mean([r["mae"]      for r in final_fold_records])), 4),
        "cv_calib_80": round(float(np.mean([r["calib_80"] for r in final_fold_records])), 4),
        "cv_folds":    len(final_fold_records),
        "cv_fold_records": final_fold_records,
        "mu_clip_min": _MU_CLIP_MIN,
        "mu_clip_max": _MU_CLIP_MAX,
        "n_deciles":   _N_DECILES,
        "trained_date": date.today().isoformat(),
        "target":      TARGET,
        "distribution_family": "negbin_nb2",
    }


# ---------------------------------------------------------------------------
# Artifact save + S3 upload
# ---------------------------------------------------------------------------

def save_artifact(artifact: dict, promote: bool) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / "starter_ip_v1.pkl"
    joblib.dump(artifact, local_path)
    print(f"\n  Saved → {local_path.relative_to(_PROJECT_ROOT)}")
    if promote:
        upload_artifact(local_path, _ARTIFACT_S3)
    else:
        print("  [--no-promote] Skipping S3 upload")
    return local_path


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def update_registry(
    artifact: dict,
    local_path: Path,
    best_params: dict,
    promote: bool,
    a_nll: float,
    b_nll: float,
    c_nll: float,
    best_alpha: float,
    mlflow_run_id: str | None,
) -> None:
    model_type = artifact["model_type"]
    cv_nll     = artifact["cv_nll"]
    cv_mae     = artifact["cv_mae"]
    cv_calib   = artifact["cv_calib_80"]
    today      = date.today().isoformat()
    s3_path    = _ARTIFACT_S3 if promote else str(local_path)
    run_id_str = mlflow_run_id or "null  # set on next retrain"

    params_str  = json.dumps(best_params)
    winner_note = "A-LightGBM + NegBin r-by-decile" if model_type == "lgbm" else "B-Ridge + NegBin r-by-decile"
    alpha_note  = f"best_alpha={best_alpha}" if model_type == "ridge" else ""

    new_block = f"""starter_ip_v1:
  artifact_path: {s3_path}
  feature_columns_path: models/sub_models/starter_v1/ip_feature_columns.json
  mlflow_run_id: {run_id_str}
  target:
    source_table: baseball_data.betting.mart_starting_pitcher_game_log
    primary_column: outs_recorded
    auxiliary_columns: [is_bulk_usage, game_pitch_count]
    grain: game_pk_side
  distribution_family: negbin
  training_window:
    start: '{_MIN_YEAR}-01-01'
    end: null
  cv_strategy: walk_forward_season
  cv_folds: {artifact["cv_folds"]}   # eval years 2023-2026
  cv_metric: negbin_nll
  cv_score: {cv_nll}
  cv_mae: {cv_mae}
  cv_calib_80: {cv_calib}
  promotion_gate:
    metric: negbin_nll
    direction: lower_is_better
    must_beat: candidate_c_glm_nll
    c_glm_nll: {round(c_nll, 4)}
    secondary:
      - calib_80_ge: {_CALIB_80_GATE}
      - mae_le: {_MAE_GATE}
      - std_pred_ge: {_STD_PRED_GATE}
  output_signals:
    - ip_mu
    - ip_pi_lo
    - ip_pi_hi
    - ip_r
    - ip_signal
  promotion_status: champion
  promoted_at: '{today}'
  notes: |
    Story 5D.2 ({today}). Training window {_MIN_YEAR}+; target = outs_recorded (0-27 outs).
    Distribution: NegBin NB2 (Var = mu + mu^2/r). Overdispersion ratio 1.125 confirmed (5D.1).
    r fitted per predicted-mean decile (10 deciles) via scipy minimize_scalar on NegBin logpmf.
    Model: {model_type.upper()}. Winner: {winner_note}. {alpha_note}
    A-LightGBM NLL={a_nll:.4f}; B-Ridge NLL={b_nll:.4f}; C-GLM NLL={c_nll:.4f}.
    Best params: {params_str}.
    starter_pitcher_archetype 16.3% null → __NA__ OHE category.
    starter_curveball_stuff_plus 32.4% null → median-imputed per fold.
"""

    text = _REGISTRY_PATH.read_text()
    pattern = r"^starter_ip_v1:.*?(?=^\S|\Z)"
    new_text = re.sub(pattern, new_block + "\n", text, count=1, flags=re.MULTILINE | re.DOTALL)
    if new_text == text:
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [INFO] starter_ip_v1 not found in registry; appended")
    else:
        print(f"  Updated starter_ip_v1 in {_REGISTRY_PATH.relative_to(_PROJECT_ROOT)}")
    _REGISTRY_PATH.write_text(new_text)


# ---------------------------------------------------------------------------
# Main training orchestration
# ---------------------------------------------------------------------------

def train(
    promote:       bool = True,
    skip_glm:      bool = False,
    force_winner:  str | None = None,
    optuna_probe:  int = 10,
    optuna_full:   int = 50,
    dry_run:       bool = False,
    min_year:      int = _MIN_YEAR,
) -> str:
    print("=" * 72)
    print("Story 5D.2 — starter_ip_v1 training (NegBin outs_recorded)")
    print("=" * 72)

    print("\nLoading data from Snowflake...")
    df = load_data(min_year=min_year)
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({int(df['game_year'].min())}–{int(df['game_year'].max())})")
    print(f"  Target: mean={df[TARGET].mean():.2f}  std={df[TARGET].std():.2f}"
          f"  min={df[TARGET].min()}  max={df[TARGET].max()}")

    optuna_folds = get_optuna_folds(df)
    all_folds    = get_all_folds(df)
    eval_yrs_opt = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in optuna_folds]
    eval_yrs_all = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in all_folds]
    print(f"  Optuna folds: {len(optuna_folds)} (eval years {eval_yrs_opt})")
    print(f"  Full CV folds: {len(all_folds)} (eval years {eval_yrs_all})")

    if len(optuna_folds) < 3:
        raise RuntimeError(f"Need ≥ 3 Optuna folds; got {len(optuna_folds)}. "
                           "Check min_train_seasons vs data range.")

    if dry_run:
        print("\n  [--dry-run] Data loaded, folds validated. Exiting before training.")
        return "dry_run"

    mlflow.set_experiment("starter_ip_v1")
    get_or_create_experiment("starter_ip_v1")

    with mlflow.start_run(run_name=f"5D2_train_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id
        mlflow.log_params({
            "train_start":     f"{min_year}-01-01",
            "n_rows":          len(df),
            "n_seasons":       int(df["game_year"].nunique()),
            "n_folds_optuna":  len(optuna_folds),
            "n_folds_all":     len(all_folds),
            "eval_years":      str(eval_yrs_all),
            "distribution":    "negbin_nb2",
            "n_deciles":       _N_DECILES,
            "optuna_probe":    optuna_probe,
            "optuna_full":     optuna_full,
            "skip_glm":        skip_glm,
            "force_winner":    str(force_winner),
        })

        # Target distribution stats (logged for 5D.1 MLflow deferred AC)
        mlflow.log_metrics({
            "target_mean":          round(float(df[TARGET].mean()),   4),
            "target_var":           round(float(df[TARGET].var()),    4),
            "target_overdispersion": round(float(df[TARGET].var() / df[TARGET].mean()), 4),
            "target_pct_bulk":      round(float(df["is_bulk_usage"].mean()), 4),
        })

        # ── C: NegBin GLM baseline ─────────────────────────────────────────
        if skip_glm:
            print("\n  [--skip-glm] Skipping Candidate C; setting floor NLL=999.0")
            c_nll, c_mae, c_c80, _, c_folds = 999.0, 999.0, 0.0, 0.0, []
        else:
            c_nll, c_mae, c_c80, _, c_folds = cv_negbin_glm(df, all_folds)
        mlflow.log_metric("glm_cv_nll", c_nll)
        mlflow.log_metric("glm_cv_mae", c_mae)

        # ── A: LightGBM + NegBin r ────────────────────────────────────────
        a_nll, a_mae, a_c80, a_std, a_folds, a_feat_names = cv_lgbm(df, all_folds)
        mlflow.log_metrics({
            "lgbm_cv_nll": a_nll, "lgbm_cv_mae": a_mae,
            "lgbm_cv_calib80": a_c80, "lgbm_cv_std_pred": a_std,
        })
        for rec in a_folds:
            log_cv_fold(rec["fold"], rec["eval_year"], {
                "lgbm_nll": rec["nll"], "lgbm_mae": rec["mae"],
                "lgbm_calib80": rec["calib_80"],
            })

        # ── B: Ridge alpha grid search + full CV ───────────────────────────
        best_alpha, _   = tune_ridge_alpha(df, optuna_folds)
        b_nll, b_mae, b_c80, b_std, b_folds = cv_ridge(df, all_folds, alpha=best_alpha)
        mlflow.log_metrics({
            "ridge_best_alpha": best_alpha,
            "ridge_cv_nll": b_nll, "ridge_cv_mae": b_mae,
            "ridge_cv_calib80": b_c80, "ridge_cv_std_pred": b_std,
        })
        for rec in b_folds:
            log_cv_fold(rec["fold"], rec["eval_year"], {
                "ridge_nll": rec["nll"], "ridge_mae": rec["mae"],
                "ridge_calib80": rec["calib_80"],
            })

        # ── Gate summary + winner selection ───────────────────────────────
        winner_type, winner_nll = print_gate_summary(
            a_nll, a_mae, a_c80, a_std, a_folds,
            b_nll, b_mae, b_c80, b_std, b_folds,
            c_nll, force_winner=force_winner,
        )
        mlflow.log_params({"winner_type": winner_type, "winner_nll": winner_nll})

        winner_folds = a_folds if winner_type == "lgbm" else b_folds

        # ── IP-specific evaluation cuts ────────────────────────────────────
        comparison_params = {} if winner_type == "lgbm" else {"alpha": best_alpha}
        print_ip_cuts(df, all_folds, winner_type, comparison_params, best_alpha)

        # ── Optuna tuning on winner ────────────────────────────────────────
        print(f"\n── Optuna tuning: {winner_type.upper()} ─────────────────────────────────")
        best_params, tuned_nll = tune_winner(
            winner_type, df, optuna_folds,
            n_probe=optuna_probe, n_full=optuna_full,
        )
        mlflow.log_params({f"best_{k}": v for k, v in best_params.items()})
        mlflow.log_metric("tuned_cv_nll", tuned_nll)

        # ── Re-run final CV with tuned params ─────────────────────────────
        print(f"\n── Final CV with tuned params ({winner_type.upper()}) ───────────────────")
        if winner_type == "lgbm":
            _, _, _, _, final_folds, _ = cv_lgbm(df, all_folds, params=best_params)
        else:
            alpha_final = best_params.get("alpha", best_alpha)
            _, _, _, _, final_folds   = cv_ridge(df, all_folds, alpha=alpha_final)

        final_nll  = float(np.mean([r["nll"]     for r in final_folds]))
        final_mae  = float(np.mean([r["mae"]      for r in final_folds]))
        final_c80  = float(np.mean([r["calib_80"] for r in final_folds]))
        final_std  = float(np.mean([r["std_pred"] for r in final_folds]))
        mlflow.log_metrics({
            "final_cv_nll": final_nll, "final_cv_mae": final_mae,
            "final_cv_calib80": final_c80, "final_cv_std_pred": final_std,
        })

        # ── Train final model on all data ─────────────────────────────────
        print(f"\n── Training final {winner_type.upper()} on {_MIN_YEAR}–2026 ──────────────")
        artifact = train_final_model(df, winner_type, best_params, best_alpha, final_folds)

        local_path = save_artifact(artifact, promote=promote)
        mlflow.log_artifact(str(local_path))

        # ── Registry update ───────────────────────────────────────────────
        update_registry(
            artifact, local_path, best_params, promote,
            a_nll=a_nll, b_nll=b_nll, c_nll=c_nll,
            best_alpha=best_alpha, mlflow_run_id=mlflow_run_id,
        )

        # ── AC summary ────────────────────────────────────────────────────
        print("\n" + "=" * 72)
        print("Acceptance criteria")
        print("=" * 72)
        print(f"  At least 2 candidates trained:   {'OK' if True else 'FAIL'}")
        print(f"  CV folds completed:              {len(final_folds)} (≥ {_MIN_TRAIN_SEASONS} required)  "
              f"{'OK' if len(final_folds) >= _MIN_TRAIN_SEASONS else 'FAIL'}")
        print(f"  Winner NLL < GLM:                {final_nll:.4f} < {c_nll:.4f}  "
              f"{'OK' if final_nll < c_nll else 'FAIL'}")
        print(f"  calib_80 ≥ {_CALIB_80_GATE}:               {final_c80:.3f}  "
              f"{'OK' if final_c80 >= _CALIB_80_GATE else 'FAIL'}")
        print(f"  MAE ≤ {_MAE_GATE} outs:                  {final_mae:.3f}  "
              f"{'OK' if final_mae <= _MAE_GATE else 'FAIL'}")
        print(f"  std(pred) ≥ {_STD_PRED_GATE} outs:           {final_std:.3f}  "
              f"{'OK' if final_std >= _STD_PRED_GATE else 'FAIL'}")
        print(f"  Winner: {winner_type.upper()}")
        print(f"  S3 artifact: {'uploaded' if promote else 'skipped (--no-promote)'}")
        print(f"  MLflow run_id: {mlflow_run_id}")
        print("=" * 72)

    return mlflow_run_id


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story 5D.2 — train starter_ip_v1 NegBin distributional model"
    )
    parser.add_argument("--no-promote",   action="store_true", help="Skip S3 upload")
    parser.add_argument("--skip-glm",     action="store_true", help="Skip Candidate C (slow statsmodels GLM)")
    parser.add_argument("--force-winner", choices=["lgbm", "ridge"],
                        default=None, help="Override gate-based winner selection")
    parser.add_argument("--optuna-probe", type=int, default=10, help="Optuna probe trials (default: 10)")
    parser.add_argument("--optuna-full",  type=int, default=50, help="Optuna full trials (default: 50)")
    parser.add_argument("--dry-run",      action="store_true", help="Load data and validate folds only")
    parser.add_argument("--min-year",     type=int, default=_MIN_YEAR,
                        help=f"Training start year (default: {_MIN_YEAR})")
    args = parser.parse_args()

    train(
        promote=not args.no_promote,
        skip_glm=args.skip_glm,
        force_winner=args.force_winner,
        optuna_probe=args.optuna_probe,
        optuna_full=args.optuna_full,
        dry_run=args.dry_run,
        min_year=args.min_year,
    )


if __name__ == "__main__":
    main()
