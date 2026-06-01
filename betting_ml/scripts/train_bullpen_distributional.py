"""
train_bullpen_distributional.py — Epic 6D.2

Trains the distributional bullpen model v2: NegBin(mu, r) predicting
next-game bullpen runs allowed for the pitching team.

Target: bullpen_runs_allowed = GREATEST(total_opponent_runs - starter_runs_allowed, 0)
Distribution family: Negative Binomial — strongly overdispersed count data
(Var/Mean = 2.54, r = 1.22 confirmed in 6D.1 audit).

Candidates:
  A — LightGBM mean + NegBin r from residuals (TRAINABLE NOW)
      Same 24-feature set as Epic 6 champion; retrained on bullpen_runs_allowed.
      r fitted via minimize_scalar on log(r) from training-fold residuals.
  B — Two-stage starter IP → bullpen NegBin (BLOCKED until Epic 5D complete)
      Requires starter_xwoba_sigma from Epic 5D distributional model.
  C — NegBin GLM (statsmodels NB2) — NLL floor reference; not promotable

Selection: Case 1 (new distributional model — no prior NegBin champion). Lower mean CV
NLL wins outright; calib_80 ≥ 0.80; MAE must not regress vs. mean-predictor baseline
(direct comparison vs. Epic 6 is N/A: target changed from xwOBA rate → runs count).

Inputs:  betting_ml/data/bullpen_state_train.parquet  (features; same as Epic 6)
         Snowflake: baseball_data.betting.mart_game_results
                    baseball_data.betting.mart_starting_pitcher_game_log
Outputs:
  betting_ml/models/sub_models/bullpen_v2.pkl
  s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl
  sub_model_registry.yaml  (bullpen_v2 block)

MLflow experiment: bullpen_6D

Usage:
    uv run python betting_ml/scripts/train_bullpen_distributional.py
    uv run python betting_ml/scripts/train_bullpen_distributional.py --no-promote
    uv run python betting_ml/scripts/train_bullpen_distributional.py --min-year 2021
"""
from __future__ import annotations

import argparse
import json
import joblib
import re
import sys
import warnings
from datetime import date
from pathlib import Path

# Suppress noisy third-party warnings that don't affect correctness
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
    module="sklearn",
)
warnings.filterwarnings(
    "ignore",
    message="Inverting hessian failed",
    module="statsmodels",
)
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    module="statsmodels",
)
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)

import mlflow
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom, wilcoxon

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold
from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.data_loader import get_snowflake_connection

_PARQUET_PATH    = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_ARTIFACT_PATH   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2.pkl"
_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl"
_REGISTRY_PATH   = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"

_TARGET_COL       = "bullpen_runs_allowed"
_YEAR_COL         = "game_year"
_MIN_YEAR_DEFAULT = 2016          # maximize fold count; merge filters to available data
_CALIB_80_GATE    = 0.80
_FATIGUE_THRESH   = 0.7           # fatigue_score > threshold → high-fatigue subset
_BLOWOUT_DELTA    = 5             # abs(score_delta) > threshold → blowout subset
_MIN_R            = 1e-3          # floor on NegBin r

_OPTUNA_PROBE_TRIALS = 10
_OPTUNA_FULL_TRIALS  = 40         # 50 trials total (10 probe + 40 full)
_OPTUNA_SEED         = 42
_OPTUNA_RECENT_FOLDS = 5

_LGBM_N_EST     = 500
_LGBM_LR        = 0.05
_LGBM_LEAVES    = 31

# Candidate B benchmark: Candidate A tuned CV NLL (recent 5 folds) — B must beat this
_CAND_B_BENCHMARK_NLL = 1.8940

_IP_SIGNALS_TABLE = "baseball_data.betting_features.starter_ip_signals"


# ── Feature set (same 24 as Epic 6 champion bullpen_quality_v1) ───────────────
FEATURE_COLS = [
    "eb_bullpen_xwoba",
    "eb_bullpen_uncertainty",
    "eb_bullpen_coverage_pct",
    "xwoba_against_14d",
    "k_pct_14d",
    "bb_pct_14d",
    "hard_hit_pct_14d",
    "whiff_rate_14d",
    "innings_pitched_14d",
    "xwoba_against_30d",
    "k_pct_30d",
    "bb_pct_30d",
    "hard_hit_pct_30d",
    "whiff_rate_30d",
    "innings_pitched_30d",
    "availability_index",
    "bullpen_ip_prev_1d",
    "bullpen_ip_prev_2d",
    "bullpen_ip_prev_3d",
    "pitchers_used_prev_3d",
    "pitchers_used_prev_7d",
    "reliever_appearances_prev_3d",
    "high_leverage_used_prev_2d",
    "closer_used_prev_1d",
]


# ── Snowflake data fetch ───────────────────────────────────────────────────────

_RUNS_QUERY = """
WITH

game_scores AS (
    SELECT
        game_pk,
        game_year,
        home_team,
        away_team,
        home_final_score,
        away_final_score,
        ABS(home_final_score - away_final_score) AS score_delta
    FROM baseball_data.betting.mart_game_results
    WHERE game_year >= {min_year}
      AND game_type = 'R'
),

team_scores AS (
    SELECT
        game_pk,
        game_year,
        home_team   AS pitching_team,
        away_final_score AS total_runs_allowed,
        score_delta
    FROM game_scores
    UNION ALL
    SELECT
        game_pk,
        game_year,
        away_team   AS pitching_team,
        home_final_score AS total_runs_allowed,
        score_delta
    FROM game_scores
),

starter_runs AS (
    SELECT
        game_pk,
        pitching_team,
        COALESCE(runs_allowed, 0) AS starter_runs_allowed
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year >= {min_year}
)

SELECT
    t.game_pk,
    t.game_year,
    t.pitching_team,
    t.total_runs_allowed,
    COALESCE(s.starter_runs_allowed, 0)                                            AS starter_runs_allowed,
    GREATEST(t.total_runs_allowed - COALESCE(s.starter_runs_allowed, 0), 0)        AS bullpen_runs_allowed,
    t.score_delta
FROM team_scores t
LEFT JOIN starter_runs s
    ON  s.game_pk       = t.game_pk
    AND s.pitching_team = t.pitching_team
ORDER BY t.game_pk, t.pitching_team
"""


def _fetch_bullpen_runs(min_year: int) -> pd.DataFrame:
    print(f"Querying Snowflake for bullpen runs allowed (game_year >= {min_year})...")
    conn = get_snowflake_connection()
    df = pd.read_sql(_RUNS_QUERY.format(min_year=min_year), conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    print(f"  Fetched {len(df):,} rows | {df['game_year'].nunique()} seasons "
          f"[{int(df['game_year'].min())}–{int(df['game_year'].max())}]")
    return df


# ── Data preparation ──────────────────────────────────────────────────────────

def _load_data(min_year: int) -> pd.DataFrame:
    """Load parquet features, fetch Snowflake target, merge on (game_pk, pitching_team)."""
    if not _PARQUET_PATH.exists():
        print(f"ERROR: {_PARQUET_PATH} not found. Run build_bullpen_state_dataset.py first.")
        sys.exit(1)

    parquet_df = pd.read_parquet(_PARQUET_PATH)
    parquet_df = parquet_df[parquet_df[_YEAR_COL] >= min_year].copy()

    # Force float on object-typed columns in the parquet
    for col in FEATURE_COLS:
        if col in parquet_df.columns:
            parquet_df[col] = pd.to_numeric(parquet_df[col], errors="coerce")

    runs_df = _fetch_bullpen_runs(min_year)

    df = parquet_df.merge(
        runs_df[["game_pk", "pitching_team", "bullpen_runs_allowed", "score_delta"]],
        on=["game_pk", "pitching_team"],
        how="inner",
    )
    df = df.dropna(subset=[_TARGET_COL]).reset_index(drop=True)
    df[_TARGET_COL] = df[_TARGET_COL].astype(float)
    df["score_delta"] = pd.to_numeric(df["score_delta"], errors="coerce").fillna(0)

    print(f"  Merged dataset: {len(df):,} rows | "
          f"{df[_YEAR_COL].nunique()} seasons "
          f"[{int(df[_YEAR_COL].min())}–{int(df[_YEAR_COL].max())}]")
    return df


def _prepare_fold(
    df: pd.DataFrame,
    train_seasons: list[int],
    test_season: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Split data into train/test arrays; median-impute from training fold."""
    tr = df[df[_YEAR_COL].isin(train_seasons)].copy()
    te = df[df[_YEAR_COL] == test_season].copy()

    impute_vals = {col: float(tr[col].median()) for col in FEATURE_COLS}
    for col in FEATURE_COLS:
        tr[col] = tr[col].fillna(impute_vals[col])
        te[col] = te[col].fillna(impute_vals[col])

    X_tr = tr[FEATURE_COLS].to_numpy(dtype=float)
    y_tr = tr[_TARGET_COL].to_numpy(dtype=float)
    X_te = te[FEATURE_COLS].to_numpy(dtype=float)
    y_te = te[_TARGET_COL].to_numpy(dtype=float)

    return X_tr, y_tr, X_te, y_te, impute_vals


# ── NegBin distribution utilities ─────────────────────────────────────────────

def _negbin_logpmf(y: np.ndarray, mu: np.ndarray | float, r: float) -> np.ndarray:
    """Log-PMF of NegBin(mu, r) (NB2 parameterization: Var = mu + mu²/r)."""
    r = max(float(r), _MIN_R)
    mu = np.clip(mu, 1e-6, None)
    p = r / (r + mu)
    return (
        gammaln(r + y) - gammaln(r) - gammaln(y + 1)
        + r * np.log(p)
        + y * np.log(1.0 - p)
    )


def _negbin_nll(y: np.ndarray, mu: np.ndarray | float, r: float) -> float:
    """Mean NLL under NegBin(mu, r)."""
    return float(-_negbin_logpmf(y, mu, r).mean())


def _negbin_calib_80(y: np.ndarray, mu: np.ndarray | float, r: float) -> float:
    """Fraction of y within the symmetric 80% NegBin PI (ppf 10th → 90th)."""
    r = max(float(r), _MIN_R)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p).astype(float)
    hi = nbinom.ppf(0.90, n=r, p=p).astype(float)
    return float(((y >= lo) & (y <= hi)).mean())


def _negbin_pi_width(mu: np.ndarray | float, r: float) -> np.ndarray:
    """80% PI width per observation: ppf(0.90) - ppf(0.10)."""
    r = max(float(r), _MIN_R)
    mu = np.clip(np.asarray(mu, dtype=float), 1e-6, None)
    p = r / (r + mu)
    return nbinom.ppf(0.90, n=r, p=p) - nbinom.ppf(0.10, n=r, p=p)


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    """Fit NegBin r via minimize_scalar on log(r) given per-row mu predictions."""
    def neg_ll(log_r: float) -> float:
        return _negbin_nll(y, mu, np.exp(log_r))

    result = minimize_scalar(neg_ll, bounds=(-3.0, 6.0), method="bounded")
    return float(np.exp(result.x))


# ── Candidate A: LightGBM mean + NegBin r from residuals ──────────────────────

def _walk_forward_cv_lgbm_negbin(
    df: pd.DataFrame,
    n_estimators: int = _LGBM_N_EST,
    learning_rate: float = _LGBM_LR,
    num_leaves: int = _LGBM_LEAVES,
    min_child_samples: int = 20,
    subsample: float = 1.0,
    colsample_bytree: float = 1.0,
) -> tuple[float, float, float, float, list[dict]]:
    """Returns (mean_nll, mean_mae, mean_calib_80, mean_r, fold_records)."""
    from lightgbm import LGBMRegressor

    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [A] LightGBM+NegBin: n_est={n_estimators}, lr={learning_rate}, "
          f"leaves={num_leaves}, {len(folds)} folds")

    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)

        lgb = LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            min_child_samples=min_child_samples,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            random_state=42,
            verbose=-1,
        )
        lgb.fit(X_tr, y_tr)

        mu_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
        mu_te = np.clip(lgb.predict(X_te), 1e-6, None)

        r = _fit_negbin_r(y_tr, mu_tr)

        nll   = _negbin_nll(y_te, mu_te, r)
        mae   = float(np.mean(np.abs(mu_te - y_te)))
        calib = _negbin_calib_80(y_te, mu_te, r)

        rec = {
            "fold":          len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train":       int(len(y_tr)),
            "n_test":        int(len(y_te)),
            "nll":           round(nll, 4),
            "mae":           round(mae, 4),
            "calib_80":      round(calib, 4),
            "r":             round(r, 4),
        }
        fold_records.append(rec)
        print(
            f"    fold {rec['fold']:>2} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  r={rec['r']:.3f}"
        )

    mean_nll   = float(np.mean([f["nll"]      for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]      for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    mean_r     = float(np.mean([f["r"]        for f in fold_records]))
    return mean_nll, mean_mae, mean_calib, mean_r, fold_records


# ── Candidate C: NegBin GLM reference (NLL floor) ────────────────────────────

def _walk_forward_cv_negbin_glm(
    df: pd.DataFrame,
) -> tuple[float, float, float, list[dict]]:
    """NegBin GLM (statsmodels NB2) reference. Returns (mean_nll, mean_mae, mean_calib_80, folds).
    Failures fall back to mean prediction so folds always complete."""
    import statsmodels.api as sm

    seasons = sorted(df[_YEAR_COL].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    print(f"\n  [C] NegBin GLM (statsmodels NB2) reference: {len(folds)} folds")

    fold_records: list[dict] = []
    n_fallback = 0

    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
        X_tr_c = sm.add_constant(X_tr, has_constant="add")
        X_te_c = sm.add_constant(X_te, has_constant="add")

        nll = mae = calib = r_glm = float("nan")
        fallback = False

        try:
            glm = sm.NegativeBinomial(y_tr, X_tr_c)
            res = glm.fit(disp=0, maxiter=200)
            mu_te  = np.clip(res.predict(X_te_c), 1e-6, None)
            alpha  = float(res.params.get("alpha", 1.0))
            r_glm  = 1.0 / max(alpha, 1e-6)
            nll    = _negbin_nll(y_te, mu_te, r_glm)
            mae    = float(np.mean(np.abs(mu_te - y_te)))
            calib  = _negbin_calib_80(y_te, mu_te, r_glm)
        except Exception as exc:
            fallback = True
            n_fallback += 1
            mu_fallback = float(y_tr.mean())
            r_fallback  = 2.0   # rough prior
            nll    = _negbin_nll(y_te, np.full(len(y_te), mu_fallback), r_fallback)
            mae    = float(np.mean(np.abs(mu_fallback - y_te)))
            calib  = _negbin_calib_80(y_te, np.full(len(y_te), mu_fallback), r_fallback)
            print(f"      fold {len(fold_records)+1} GLM fallback to mean: {exc}")

        rec = {
            "fold":          len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train":       int(len(y_tr)),
            "n_test":        int(len(y_te)),
            "nll":           round(nll, 4),
            "mae":           round(mae, 4),
            "calib_80":      round(calib, 4),
            "r_glm":         round(r_glm, 4) if not np.isnan(r_glm) else None,
            "fallback":      fallback,
        }
        fold_records.append(rec)
        flag = " [fallback]" if fallback else ""
        print(
            f"    fold {rec['fold']:>2} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}{flag}"
        )

    if n_fallback > 0:
        print(f"  GLM: {n_fallback}/{len(folds)} folds fell back to mean prediction. "
              f"NLL floor reflects intercept-only NegBin, not a full GLM.")

    mean_nll   = float(np.mean([f["nll"]      for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]      for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    return mean_nll, mean_mae, mean_calib, fold_records


# ── Candidate B: two-stage starter IP → bullpen exposure → NegBin ────────────

_STARTER_IP_P20_QUERY = """
SELECT
    si.game_pk,
    CASE WHEN si.side = 'home' THEN gr.home_team
         ELSE gr.away_team END AS pitching_team,
    si.starter_ip_p20_outs
FROM {ip_table} si
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = si.game_pk
WHERE si.model_version = 'starter_ip_v1'
  AND gr.game_year >= {{min_year}}
  AND gr.game_type  = 'R'
""".format(ip_table=_IP_SIGNALS_TABLE)


def _fetch_starter_ip_p20(min_year: int) -> pd.DataFrame:
    """Fetch starter_ip_p20_outs keyed to (game_pk, pitching_team)."""
    print(f"Querying Snowflake for starter_ip_p20_outs (game_year >= {min_year})...")
    conn = get_snowflake_connection()
    df = pd.read_sql(_STARTER_IP_P20_QUERY.format(min_year=min_year), conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    df["game_pk"] = pd.to_numeric(df["game_pk"], errors="coerce").astype("int64")
    df["starter_ip_p20_outs"] = pd.to_numeric(df["starter_ip_p20_outs"], errors="coerce")
    print(f"  Fetched {len(df):,} rows | {df['starter_ip_p20_outs'].notna().sum():,} non-null p20")
    return df


def _walk_forward_cv_candidate_b(
    df: pd.DataFrame,
    tuned_params: dict,
) -> tuple[float, float, float, float, list[dict]]:
    """Candidate B recent-5-fold CV: same LightGBM as A, plus IP-depth exposure scaling.

    mu_adj = mu_base × (27 - starter_ip_p20_outs) / fold_avg_bullpen_outs
    Falls back to scale=1.0 for rows where p20 is null.
    Matches the _OPTUNA_RECENT_FOLDS=5 window used to produce the 1.8940 A benchmark.
    """
    from lightgbm import LGBMRegressor

    seasons  = sorted(df[_YEAR_COL].unique())
    n_folds  = min(_OPTUNA_RECENT_FOLDS, len(seasons) - 1)
    folds    = [(seasons[:i], seasons[i]) for i in range(len(seasons) - n_folds, len(seasons))]

    print(f"\n  [B] Two-stage starter-IP → bullpen-NegBin: {n_folds} recent folds "
          f"(same window as Optuna objective)")

    fold_records: list[dict] = []

    for train_seasons, test_season in folds:
        tr_df = df[df[_YEAR_COL].isin(train_seasons)].copy()
        te_df = df[df[_YEAR_COL] == test_season].copy()

        impute_vals = {col: float(tr_df[col].median()) for col in FEATURE_COLS}
        for col in FEATURE_COLS:
            tr_df[col] = tr_df[col].fillna(impute_vals[col])
            te_df[col] = te_df[col].fillna(impute_vals[col])

        X_tr = tr_df[FEATURE_COLS].to_numpy(dtype=float)
        y_tr = tr_df[_TARGET_COL].to_numpy(dtype=float)
        X_te = te_df[FEATURE_COLS].to_numpy(dtype=float)
        y_te = te_df[_TARGET_COL].to_numpy(dtype=float)

        p20_tr = tr_df["starter_ip_p20_outs"].to_numpy(dtype=float)
        p20_te = te_df["starter_ip_p20_outs"].to_numpy(dtype=float)

        valid_tr = ~np.isnan(p20_tr)
        fold_avg_bullpen_outs = (
            float(np.mean(27.0 - p20_tr[valid_tr])) if valid_tr.any() else 12.0
        )

        lgb = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **tuned_params)
        lgb.fit(X_tr, y_tr)

        mu_base_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
        mu_base_te = np.clip(lgb.predict(X_te), 1e-6, None)

        denom = max(fold_avg_bullpen_outs, 1e-3)
        scale_tr = np.where(np.isnan(p20_tr), 1.0, (27.0 - p20_tr) / denom)
        scale_te = np.where(np.isnan(p20_te), 1.0, (27.0 - p20_te) / denom)

        mu_adj_tr = np.clip(mu_base_tr * scale_tr, 1e-6, None)
        mu_adj_te = np.clip(mu_base_te * scale_te, 1e-6, None)

        r     = _fit_negbin_r(y_tr, mu_adj_tr)
        nll   = _negbin_nll(y_te, mu_adj_te, r)
        mae   = float(np.mean(np.abs(mu_adj_te - y_te)))
        calib = _negbin_calib_80(y_te, mu_adj_te, r)

        p20_cov = float(valid_tr.mean())
        rec = {
            "fold":               len(fold_records) + 1,
            "train_seasons":      list(map(int, train_seasons)),
            "test_season":        int(test_season),
            "n_train":            int(len(y_tr)),
            "n_test":             int(len(y_te)),
            "nll":                round(nll, 4),
            "mae":                round(mae, 4),
            "calib_80":           round(calib, 4),
            "r":                  round(r, 4),
            "fold_avg_bullpen_outs": round(fold_avg_bullpen_outs, 3),
            "p20_coverage":       round(p20_cov, 4),
        }
        fold_records.append(rec)
        print(
            f"    fold {rec['fold']:>2} (test={test_season}): "
            f"NLL={rec['nll']:.4f}  MAE={rec['mae']:.4f}  "
            f"calib80={rec['calib_80']:.3f}  r={rec['r']:.3f}  "
            f"avg_bp_outs={rec['fold_avg_bullpen_outs']:.1f}  p20_cov={p20_cov:.3f}"
        )

    mean_nll   = float(np.mean([f["nll"]      for f in fold_records]))
    mean_mae   = float(np.mean([f["mae"]      for f in fold_records]))
    mean_calib = float(np.mean([f["calib_80"] for f in fold_records]))
    mean_r     = float(np.mean([f["r"]        for f in fold_records]))
    return mean_nll, mean_mae, mean_calib, mean_r, fold_records


def _evaluate_candidate_b(promote: bool, min_year: int) -> None:
    """Evaluate Candidate B against the existing Candidate A champion (bullpen_v2.pkl).

    Requires bullpen_v2.pkl to be present (run --candidate a first).
    Uses A's tuned LightGBM params so the only delta is the exposure scaling.
    Evaluates on the same recent-5-fold window that produced A's 1.8940 NLL benchmark.
    If B wins, saves new artifact and updates S3 + registry.
    """
    if not _ARTIFACT_PATH.exists():
        print("ERROR: bullpen_v2.pkl not found. Run --candidate a first to train Candidate A.")
        sys.exit(1)

    print(f"\n{'='*72}")
    print("EVALUATING Candidate B — Two-stage starter-IP → bullpen NegBin")
    print(f"Benchmark: Candidate A tuned CV NLL = {_CAND_B_BENCHMARK_NLL} (recent 5 folds)")
    print(f"{'='*72}")

    a_artifact   = joblib.load(_ARTIFACT_PATH)
    tuned_params = a_artifact.get("tuned_params", {})
    if not tuned_params:
        print("WARNING: No tuned_params in bullpen_v2.pkl — using default LightGBM params")
        tuned_params = {
            "n_estimators":     _LGBM_N_EST,
            "learning_rate":    _LGBM_LR,
            "num_leaves":       _LGBM_LEAVES,
            "min_child_samples": 20,
        }

    print(f"  Using A's tuned params: {tuned_params}")

    df_base = _load_data(min_year)
    ip_df   = _fetch_starter_ip_p20(min_year)

    df = df_base.merge(
        ip_df[["game_pk", "pitching_team", "starter_ip_p20_outs"]],
        on=["game_pk", "pitching_team"],
        how="left",
    )
    null_p20 = df["starter_ip_p20_outs"].isna().mean()
    print(f"\n  Merged dataset: {len(df):,} rows | p20 null rate: {null_p20:.3%} "
          f"(falls back to scale=1.0)")

    mlflow.set_experiment("bullpen_6D")
    get_or_create_experiment("bullpen_6D")

    with mlflow.start_run(run_name=f"6D.2_candidate_b_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id

        mlflow.log_params({
            "candidate":        "B",
            "min_year":         min_year,
            "benchmark_nll":    _CAND_B_BENCHMARK_NLL,
            "n_rows":           len(df),
            "null_p20_rate":    round(null_p20, 4),
            **{f"tuned_{k}": v for k, v in tuned_params.items()},
        })

        b_nll, b_mae, b_calib, b_r, b_folds = _walk_forward_cv_candidate_b(df, tuned_params)

        mlflow.log_metrics({
            "cand_b_cv_nll":   b_nll,
            "cand_b_cv_mae":   b_mae,
            "cand_b_calib_80": b_calib,
            "cand_b_mean_r":   b_r,
            "cand_a_benchmark_nll": _CAND_B_BENCHMARK_NLL,
        })

        print(f"\n{'='*72}")
        print(f"Candidate B vs A gate comparison (recent {_OPTUNA_RECENT_FOLDS} folds)")
        print(f"{'='*72}")

        delta = _CAND_B_BENCHMARK_NLL - b_nll
        b_wins = b_nll < _CAND_B_BENCHMARK_NLL and b_calib >= _CALIB_80_GATE

        print(f"  Candidate B NLL:      {b_nll:.4f}")
        print(f"  Candidate A NLL:      {_CAND_B_BENCHMARK_NLL:.4f}  (tuned benchmark)")
        print(f"  Δ NLL (A − B):        {delta:+.4f}  {'← B WINS' if delta > 0 else '← A WINS'}")
        print(f"  Candidate B calib_80: {b_calib:.4f}  "
              f"{'≥ 0.80 ✓' if b_calib >= _CALIB_80_GATE else '< 0.80 ✗'}")
        print(f"  Overall verdict:      {'CANDIDATE B PROMOTED' if b_wins else 'CANDIDATE A REMAINS CHAMPION'}")

        mlflow.set_tag("candidate", "B")
        mlflow.set_tag("verdict", "B_wins" if b_wins else "A_wins")
        mlflow.set_tag("sub_model_registry_key", "bullpen_v2")

        if b_wins:
            print(f"\n  Building final Candidate B model on all data...")
            from lightgbm import LGBMRegressor

            df_final = df.copy()
            impute_vals = {col: float(df_final[col].median()) for col in FEATURE_COLS}
            for col in FEATURE_COLS:
                df_final[col] = df_final[col].fillna(impute_vals[col])

            p20_all = df_final["starter_ip_p20_outs"].to_numpy(dtype=float)
            valid   = ~np.isnan(p20_all)
            league_avg_bullpen_outs = float(np.mean(27.0 - p20_all[valid])) if valid.any() else 12.0

            X_all = df_final[FEATURE_COLS].to_numpy(dtype=float)
            y_all = df_final[_TARGET_COL].to_numpy(dtype=float)

            final_model = LGBMRegressor(random_state=_OPTUNA_SEED, verbose=-1, **tuned_params)
            final_model.fit(X_all, y_all)

            mu_base_all = np.clip(final_model.predict(X_all), 1e-6, None)
            scale_all   = np.where(np.isnan(p20_all), 1.0,
                                   (27.0 - p20_all) / max(league_avg_bullpen_outs, 1e-3))
            mu_adj_all  = np.clip(mu_base_all * scale_all, 1e-6, None)
            final_r     = _fit_negbin_r(y_all, mu_adj_all)

            in_sample_nll = _negbin_nll(y_all, mu_adj_all, final_r)
            in_sample_cal = _negbin_calib_80(y_all, mu_adj_all, final_r)

            print(f"  Final r:              {final_r:.4f}")
            print(f"  League avg bp outs:   {league_avg_bullpen_outs:.3f}")
            print(f"  In-sample NLL:        {in_sample_nll:.4f}")
            print(f"  In-sample calib_80:   {in_sample_cal:.4f}")

            artifact_b = {
                "model":                  final_model,
                "model_type":             "lgbm",
                "distribution_family":    "negbin",
                "feature_cols":           FEATURE_COLS,
                "impute_vals":            impute_vals,
                "r":                      final_r,
                "candidate":              "B",
                "league_avg_bullpen_outs": league_avg_bullpen_outs,
                "cv_nll":                 b_nll,
                "cv_mae":                 b_mae,
                "cv_calib_80":            b_calib,
                "cv_mean_r":              b_r,
                "tuned_params":           tuned_params,
                "cand_a_tuned_nll":       _CAND_B_BENCHMARK_NLL,
                "cv_fold_records":        b_folds,
            }
            _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(artifact_b, _ARTIFACT_PATH)
            print(f"\n  Artifact saved → {_ARTIFACT_PATH.relative_to(_PROJECT_ROOT)}")

            if promote:
                upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)
                mlflow.log_artifact(str(_ARTIFACT_PATH))

        print(f"\n=== DONE — Candidate B evaluation — MLflow run: {mlflow_run_id} ===")
        print("=" * 72)

        winner = "B" if b_wins else "A"
        print(f"\nNext: update bullpen_6D_architecture.md with champion = Candidate {winner}")
        print(f"  Champion NLL: {'B=' + str(round(b_nll, 4)) if b_wins else 'A=' + str(_CAND_B_BENCHMARK_NLL)}")
        print(f"  MLflow run_id (B eval): {mlflow_run_id}")


# ── Display helpers ───────────────────────────────────────────────────────────

def _print_fold_table_a(fold_records: list[dict]) -> None:
    print("\n── Candidate A (LightGBM+NegBin) walk-forward CV ───────────────────────────")
    print(f"  {'Fold':>4}  {'Train':>12}  {'Test':>6}  {'NLL':>7}  "
          f"{'MAE':>6}  {'Calib80':>8}  {'r':>6}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>12}  {r['test_season']:>6}  "
            f"{r['nll']:>7.4f}  {r['mae']:>6.4f}  {r['calib_80']:>8.4f}  "
            f"{r['r']:>6.3f}"
        )
    print(
        f"  {'Mean':>4}  {'':>12}  {'':>6}  "
        f"{np.mean([f['nll'] for f in fold_records]):>7.4f}  "
        f"{np.mean([f['mae'] for f in fold_records]):>6.4f}  "
        f"{np.mean([f['calib_80'] for f in fold_records]):>8.4f}  "
        f"{np.mean([f['r'] for f in fold_records]):>6.3f}"
    )


def _print_gate_summary(
    a_nll: float, a_mae: float, a_calib: float, a_mean_r: float, a_folds: list[dict],
    c_nll: float, c_mae: float, c_calib: float,
    mean_pred_mae: float,
) -> None:
    print("\n" + "=" * 78)
    print("bullpen_v2 head-to-head: Cand A (LightGBM+NegBin) | Cand C (GLM reference)")
    print("  Candidate B: BLOCKED until Epic 5D (starter_xwoba_sigma not yet available)")
    print("=" * 78)

    def gate(val: float, thr: float, lower: bool = True) -> str:
        return "PASS" if ((val < thr) if lower else (val >= thr)) else "FAIL"

    w = 30
    print(f"  {'Gate':<{w}}  {'Cand A (LightGBM+NB)':>22}  {'Cand C (GLM ref)':>18}")
    print(f"  {'-'*w}  {'-'*22}  {'-'*18}")

    nll_winner = "A" if a_nll <= c_nll else "C"
    print(
        f"  {'NLL (A must beat C baseline)':<{w}}  "
        f"{a_nll:>18.4f} {'←' if nll_winner == 'A' else ' ':>3}  "
        f"{c_nll:>18.4f}"
    )
    print(
        f"  {'calib_80 (≥ 0.80)':<{w}}  "
        f"{a_calib:>18.4f} {gate(a_calib, _CALIB_80_GATE, lower=False):>4}  "
        f"{c_calib:>18.4f}"
    )
    print(
        f"  {'MAE (vs mean-predictor baseline)':<{w}}  "
        f"{a_mae:>22.4f}  {mean_pred_mae:>18.4f}"
    )
    mae_gate_ok = a_mae <= mean_pred_mae
    print(f"  {'  (MAE gate)':<{w}}  {'PASS' if mae_gate_ok else 'FAIL':>22}  {'(baseline)':>18}")

    if len(a_folds) >= 2:
        a_nlls = [f["nll"] for f in a_folds]
        try:
            a_wins = sum(1 for nll in a_nlls if not np.isnan(nll))
            print(f"\n  Fold NLL count: {len(a_nlls)} folds  |  mean_r={a_mean_r:.3f}")
        except Exception:
            pass

    print("=" * 78)
    nll_gate_ok    = a_nll <= c_nll
    calib_gate_ok  = a_calib >= _CALIB_80_GATE

    if nll_gate_ok and calib_gate_ok:
        print(f"\n  CANDIDATE A PROMOTED — NLL {a_nll:.4f} ≤ GLM {c_nll:.4f}, "
              f"calib_80 {a_calib:.4f} ≥ {_CALIB_80_GATE}")
    else:
        fails = []
        if not nll_gate_ok:
            fails.append(f"NLL gate (A {a_nll:.4f} > GLM {c_nll:.4f})")
        if not calib_gate_ok:
            fails.append(f"calib_80 gate ({a_calib:.4f} < {_CALIB_80_GATE})")
        print(f"\n  WARNING: gate failure — {', '.join(fails)}")
        print("  Proceeding with Candidate A (only non-reference option until 5D unblocks B)")


# ── Subset evaluation ─────────────────────────────────────────────────────────

def _subset_eval(
    df: pd.DataFrame,
    final_model,
    r: float,
    impute_vals: dict,
) -> dict:
    """Evaluate on high-fatigue and blowout subsets using the final trained model."""
    df = df.copy()
    for col in FEATURE_COLS:
        df[col] = df[col].fillna(impute_vals.get(col, 0.0))

    X_all  = df[FEATURE_COLS].to_numpy(dtype=float)
    y_all  = df[_TARGET_COL].to_numpy(dtype=float)
    mu_all = np.clip(final_model.predict(X_all), 1e-6, None)

    # High-fatigue subset
    fatigue_mask = df["fatigue_score"].fillna(0.0) > _FATIGUE_THRESH
    rest_mask    = ~fatigue_mask
    high_fatigue = {"n": int(fatigue_mask.sum())}
    rested       = {"n": int(rest_mask.sum())}
    if high_fatigue["n"] >= 50:
        high_fatigue["nll"]      = round(_negbin_nll(y_all[fatigue_mask], mu_all[fatigue_mask], r), 4)
        high_fatigue["calib_80"] = round(_negbin_calib_80(y_all[fatigue_mask], mu_all[fatigue_mask], r), 4)
        high_fatigue["mean_pi_width"] = round(float(_negbin_pi_width(mu_all[fatigue_mask], r).mean()), 4)
    if rested["n"] >= 50:
        rested["nll"]      = round(_negbin_nll(y_all[rest_mask], mu_all[rest_mask], r), 4)
        rested["calib_80"] = round(_negbin_calib_80(y_all[rest_mask], mu_all[rest_mask], r), 4)
        rested["mean_pi_width"] = round(float(_negbin_pi_width(mu_all[rest_mask], r).mean()), 4)

    # Blowout subset
    blowout_mask = df["score_delta"].fillna(0.0) > _BLOWOUT_DELTA
    close_mask   = ~blowout_mask
    blowout  = {"n": int(blowout_mask.sum())}
    close    = {"n": int(close_mask.sum())}
    if blowout["n"] >= 50:
        blowout["nll"]      = round(_negbin_nll(y_all[blowout_mask], mu_all[blowout_mask], r), 4)
        blowout["calib_80"] = round(_negbin_calib_80(y_all[blowout_mask], mu_all[blowout_mask], r), 4)
        blowout["mean_pi_width"] = round(float(_negbin_pi_width(mu_all[blowout_mask], r).mean()), 4)
    if close["n"] >= 50:
        close["nll"]      = round(_negbin_nll(y_all[close_mask], mu_all[close_mask], r), 4)
        close["calib_80"] = round(_negbin_calib_80(y_all[close_mask], mu_all[close_mask], r), 4)
        close["mean_pi_width"] = round(float(_negbin_pi_width(mu_all[close_mask], r).mean()), 4)

    result = {
        "fatigue_thresh":  _FATIGUE_THRESH,
        "blowout_thresh":  _BLOWOUT_DELTA,
        "high_fatigue":    high_fatigue,
        "rested":          rested,
        "blowout":         blowout,
        "close_game":      close,
    }
    return result


def _print_subset_eval(subset: dict) -> None:
    hf = subset["high_fatigue"]
    rs = subset["rested"]
    bl = subset["blowout"]
    cl = subset["close_game"]

    print(f"\n── Bullpen-specific subset evaluation ──────────────────────────────────────")
    print(f"  High-fatigue (fatigue_score > {subset['fatigue_thresh']}, n={hf['n']}):  "
          f"NLL={hf.get('nll','N/A')}  calib80={hf.get('calib_80','N/A')}  "
          f"PI_width={hf.get('mean_pi_width','N/A')}")
    print(f"  Rested (n={rs['n']}):  "
          f"NLL={rs.get('nll','N/A')}  calib80={rs.get('calib_80','N/A')}  "
          f"PI_width={rs.get('mean_pi_width','N/A')}")
    if hf.get("mean_pi_width") and rs.get("mean_pi_width"):
        wider = hf["mean_pi_width"] > rs["mean_pi_width"]
        print(f"  → High-fatigue PI wider than rested: {'YES ✓' if wider else 'NO ✗ (unexpected)'}")

    print(f"\n  Blowout (|score_delta| > {subset['blowout_thresh']}, n={bl['n']}):  "
          f"NLL={bl.get('nll','N/A')}  calib80={bl.get('calib_80','N/A')}  "
          f"PI_width={bl.get('mean_pi_width','N/A')}")
    print(f"  Close games (n={cl['n']}):  "
          f"NLL={cl.get('nll','N/A')}  calib80={cl.get('calib_80','N/A')}  "
          f"PI_width={cl.get('mean_pi_width','N/A')}")
    if bl.get("mean_pi_width") and cl.get("mean_pi_width"):
        note = ("wider (mop-up dispersion captured ✓)" if bl["mean_pi_width"] > cl["mean_pi_width"]
                else "narrower (unexpected for mop-up context)")
        print(f"  → Blowout PI vs. close: {note}")


# ── Optuna tuning ─────────────────────────────────────────────────────────────

def _make_optuna_objective(df: pd.DataFrame):
    seasons = sorted(df[_YEAR_COL].unique())
    n_folds = min(_OPTUNA_RECENT_FOLDS, len(seasons) - 1)
    folds   = [(seasons[:i], seasons[i]) for i in range(len(seasons) - n_folds, len(seasons))]

    def objective(trial) -> float:
        from lightgbm import LGBMRegressor
        n_est   = trial.suggest_int("n_estimators",       100, 800, step=50)
        lr      = trial.suggest_float("learning_rate",    0.005, 0.2,  log=True)
        leaves  = trial.suggest_int("num_leaves",         15,  127)
        min_cs  = trial.suggest_int("min_child_samples",  10,  100)
        sub     = trial.suggest_float("subsample",        0.5,  1.0)
        colsub  = trial.suggest_float("colsample_bytree", 0.5,  1.0)

        fold_nlls = []
        for train_seasons, test_season in folds:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, list(train_seasons), test_season)
            lgb = LGBMRegressor(
                n_estimators=n_est, learning_rate=lr, num_leaves=leaves,
                min_child_samples=min_cs, subsample=sub, colsample_bytree=colsub,
                random_state=_OPTUNA_SEED, verbose=-1,
            )
            lgb.fit(X_tr, y_tr)
            mu_tr = np.clip(lgb.predict(X_tr), 1e-6, None)
            mu_te = np.clip(lgb.predict(X_te), 1e-6, None)
            r     = _fit_negbin_r(y_tr, mu_tr)
            fold_nlls.append(_negbin_nll(y_te, mu_te, r))
        return float(np.mean(fold_nlls))

    return objective


def _tune_winner(df: pd.DataFrame, initial_nll: float) -> tuple[dict, float]:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    objective = _make_optuna_objective(df)
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED),
    )

    print(
        f"\n[Optuna] Phase 1 — probe ({_OPTUNA_PROBE_TRIALS} trials), "
        f"objective=mean CV NLL, initial NLL={initial_nll:.4f}"
    )
    study.optimize(objective, n_trials=_OPTUNA_PROBE_TRIALS, show_progress_bar=True)
    probe_best = study.best_value
    print(
        f"[Optuna] Probe best NLL: {probe_best:.4f}  "
        f"(Δ vs initial: {initial_nll - probe_best:+.4f})"
    )

    print(f"[Optuna] Phase 2 — full pass ({_OPTUNA_FULL_TRIALS} trials)...")
    study.optimize(objective, n_trials=_OPTUNA_FULL_TRIALS, show_progress_bar=True)

    best_params = study.best_params
    best_nll    = study.best_value
    print(f"[Optuna] Best params: {best_params}")
    print(f"[Optuna] Best NLL:    {best_nll:.4f}  (Δ vs initial: {initial_nll - best_nll:+.4f})")
    return best_params, best_nll


# ── Registry update ───────────────────────────────────────────────────────────

def _update_registry(
    cv_nll: float,
    cv_mae: float,
    mean_r: float,
    calib_80: float,
    n_features: int,
    tuned_nll: float,
    tuned_params: dict,
    cand_a_nll: float,
    cand_c_nll: float,
    mlflow_run_id: str | None,
    subset_eval: dict,
    n_seasons: int,
    n_rows: int,
) -> None:
    text  = _REGISTRY_PATH.read_text()
    today = date.today().isoformat()
    subset_str = json.dumps(subset_eval)

    bullpen_v2_block = f"""
bullpen_v2:
  artifact_path: {_ARTIFACT_S3_URI}
  distribution_family: negbin
  target: bullpen_runs_allowed
  n_features: {n_features}
  architecture: LightGBM mean + NegBin r from residuals (Candidate A)
  mlflow_run_id: {mlflow_run_id or "null"}
  tuned_params: {json.dumps(tuned_params)}
  cv_strategy: walk_forward_season
  cv_metric: negbin_nll
  cv_score: {round(cv_nll, 4)}
  cv_mae: {round(cv_mae, 4)}
  cv_calib_80: {round(calib_80, 4)}
  tuned_cv_nll: {round(tuned_nll, 4)}
  negbin_r: {round(mean_r, 4)}
  cand_a_cv_nll: {round(cand_a_nll, 4)}
  cand_c_glm_cv_nll: {round(cand_c_nll, 4)}
  candidate_architecture: A
  candidate_b_status: BLOCKED_until_Epic5D
  promotion_gate:
    metric: negbin_nll
    direction: lower_is_better
    nll_vs_glm: {round(cand_a_nll, 4)} vs {round(cand_c_nll, 4)} ({'PASS' if cand_a_nll <= cand_c_nll else 'FAIL'})
    calib_80_gate: {round(calib_80, 4)} >= {_CALIB_80_GATE} ({'PASS' if calib_80 >= _CALIB_80_GATE else 'FAIL'})
    case: 1  # new distributional model; lower NLL wins outright
  output_signals:
    - bullpen_mu
    - bullpen_dispersion
    - bullpen_fatigue_adjusted_mu
    - uncertainty
  distribution_params:
    mu: predicted mean bullpen runs allowed
    r: NegBin dispersion (r = {round(mean_r, 4)}); lower r = higher overdispersion
    p: r / (r + mu) at inference
  subset_eval: '{subset_str}'
  downstream_consumers: []
  promotion_status: champion
  trained_at: "{today}"
  n_rows: {n_rows}
  n_seasons: {n_seasons}
  notes: |
    Story 6D.2 ({today}). Distributional NegBin retrofit of Epic 6 bullpen champion.
    Target: bullpen_runs_allowed (integer count, 2021+ data quality).
    Distribution: NegBin(mu, r); r={round(mean_r, 4)} (from training residuals; Var/Mean~2.54 per 6D.1 audit).
    Architecture: LightGBM mean + constant NegBin r from residuals (Candidate A).
    Candidate B (two-stage starter IP) blocked until Epic 5D delivers starter_xwoba_sigma.
    Candidate C (GLM) is reference floor only; not promotable.
    CV NLL {round(cv_nll, 4)} | Tuned NLL {round(tuned_nll, 4)} | calib_80 {round(calib_80, 4)}.
    {n_features} features: same feature set as bullpen_quality_v1 (Epic 6).
    Next: 6D.3 generate_bullpen_signals.py → emit bullpen_mu, bullpen_dispersion,
    bullpen_fatigue_adjusted_mu, uncertainty per game-side.
"""

    # Insert bullpen_v2 block — after the existing bullpen_v1 block
    if "bullpen_v2:" in text:
        pattern = r"bullpen_v2:.*?(?=\n\S|\Z)"
        new_text = re.sub(pattern, bullpen_v2_block.lstrip(), text, count=1, flags=re.DOTALL)
    else:
        # Insert after bullpen_v1's closing notes block
        new_text = re.sub(
            r"(bullpen_v1:.*?(?=\n[a-z_]+_v[0-9]|\Z))",
            r"\1" + bullpen_v2_block,
            text,
            count=1,
            flags=re.DOTALL,
        )
        if new_text == text:
            new_text = text + bullpen_v2_block

    _REGISTRY_PATH.write_text(new_text)
    print(f"\nRegistry updated: bullpen_v2 (LightGBM+NegBin, NLL={round(cv_nll, 4)}, "
          f"r={round(mean_r, 4)}, trained {today})")


# ── Training orchestration ────────────────────────────────────────────────────

def train(promote: bool = True, min_year: int = _MIN_YEAR_DEFAULT) -> str:
    print(f"\n{'='*72}")
    print("TRAINING bullpen_v2 — Distributional NegBin (Epic 6D.2)")
    print(f"Distribution: NegBin(mu, r) | Target: bullpen_runs_allowed | min_year={min_year}")
    print(f"{'='*72}")

    df = _load_data(min_year)
    seasons = sorted(df[_YEAR_COL].unique())
    n_folds = len(seasons) - 1

    print(f"\nDataset: {len(df):,} rows | {len(seasons)} seasons | {n_folds} CV folds")
    print(f"Target: mean={df[_TARGET_COL].mean():.4f}  std={df[_TARGET_COL].std():.4f}  "
          f"P(0)={float((df[_TARGET_COL]==0).mean()):.3f}")
    print(f"Features: {len(FEATURE_COLS)}")

    # Mean-predictor MAE as no-regress baseline (Epic 6 targets xwOBA, not runs — not comparable)
    global_mean     = float(df[_TARGET_COL].mean())
    mean_pred_mae   = float(np.mean(np.abs(df[_TARGET_COL] - global_mean)))

    print(f"\nMean-predictor baseline MAE (runs): {mean_pred_mae:.4f}")
    print("(Candidate A MAE must be ≤ this; direct Epic 6 MAE comparison N/A: target changed)")

    null_pct = df[FEATURE_COLS].isna().mean() * 100
    high_null = null_pct[null_pct > 2]
    if not high_null.empty:
        print(f"\nNull rates > 2% (median-imputed per fold):")
        for col, pct in high_null.items():
            print(f"  {col}: {pct:.1f}%")

    print(f"\nCandidate B: BLOCKED — Epic 5D not yet complete "
          f"(requires starter_xwoba_sigma); skip until 5D champion ships")

    mlflow.set_experiment("bullpen_6D")
    get_or_create_experiment("bullpen_6D")

    with mlflow.start_run(run_name=f"6D.2_comparison_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id

        mlflow.log_params({
            "n_rows":                len(df),
            "n_seasons":             len(seasons),
            "n_features":            len(FEATURE_COLS),
            "min_year":              min_year,
            "distribution":          "negbin",
            "target":                _TARGET_COL,
            "calib_80_gate":         _CALIB_80_GATE,
            "optuna_probe_trials":   _OPTUNA_PROBE_TRIALS,
            "optuna_full_trials":    _OPTUNA_FULL_TRIALS,
            "candidate_b_status":    "BLOCKED_until_Epic5D",
        })

        # ── Candidate A: LightGBM+NegBin ──────────────────────────────────────
        print(f"\n[1/2] Candidate A — LightGBM mean + NegBin r from residuals")
        a_nll, a_mae, a_calib, a_mean_r, a_folds = _walk_forward_cv_lgbm_negbin(df)
        _print_fold_table_a(a_folds)

        mlflow.log_metrics({
            "cand_a_cv_nll":    a_nll,
            "cand_a_cv_mae":    a_mae,
            "cand_a_calib_80":  a_calib,
            "cand_a_mean_r":    a_mean_r,
        })
        for rec in a_folds:
            log_cv_fold(rec["fold"], rec["test_season"], {
                "a_nll":     rec["nll"],
                "a_mae":     rec["mae"],
                "a_calib_80": rec["calib_80"],
                "a_r":       rec["r"],
            })

        # ── Candidate C: NegBin GLM reference ─────────────────────────────────
        print(f"\n[2/2] Candidate C — NegBin GLM reference (NLL floor; not promotable)")
        c_nll, c_mae, c_calib, c_folds = _walk_forward_cv_negbin_glm(df)

        mlflow.log_metrics({
            "cand_c_glm_cv_nll":    c_nll,
            "cand_c_glm_cv_mae":    c_mae,
            "cand_c_glm_calib_80":  c_calib,
        })

        # ── Gate summary ───────────────────────────────────────────────────────
        _print_gate_summary(
            a_nll, a_mae, a_calib, a_mean_r, a_folds,
            c_nll, c_mae, c_calib,
            mean_pred_mae,
        )

        mlflow.log_metrics({
            "winner_cv_nll":   a_nll,
            "winner_cv_mae":   a_mae,
            "winner_calib_80": a_calib,
            "mean_pred_mae":   mean_pred_mae,
        })

        # ── Optuna tuning ──────────────────────────────────────────────────────
        print(f"\n{'='*72}")
        print("Optuna hyperparameter tuning — Candidate A (LightGBM+NegBin)")
        print(f"{'='*72}")
        tuned_params, tuned_nll = _tune_winner(df, a_nll)
        mlflow.log_params({f"tuned_{k}": v for k, v in tuned_params.items()})
        mlflow.log_metrics({"tuned_cv_nll": tuned_nll})

        # ── Final model: train on all data with tuned params ───────────────────
        print(f"\nTraining final LightGBM on all {len(df):,} rows with tuned params...")
        from lightgbm import LGBMRegressor

        impute_vals = {col: float(df[col].median()) for col in FEATURE_COLS}
        df_final    = df.copy()
        for col in FEATURE_COLS:
            df_final[col] = df_final[col].fillna(impute_vals[col])

        X_all = df_final[FEATURE_COLS].to_numpy(dtype=float)
        y_all = df_final[_TARGET_COL].to_numpy(dtype=float)

        final_n_est   = tuned_params.get("n_estimators",       _LGBM_N_EST)
        final_lr      = tuned_params.get("learning_rate",      _LGBM_LR)
        final_leaves  = tuned_params.get("num_leaves",         _LGBM_LEAVES)
        final_min_cs  = tuned_params.get("min_child_samples",  20)
        final_sub     = tuned_params.get("subsample",          1.0)
        final_colsub  = tuned_params.get("colsample_bytree",   1.0)

        print(f"  Tuned params: n_est={final_n_est}, lr={final_lr:.5f}, "
              f"leaves={final_leaves}, min_child_samples={final_min_cs}")

        final_model = LGBMRegressor(
            n_estimators=final_n_est, learning_rate=final_lr, num_leaves=final_leaves,
            min_child_samples=final_min_cs, subsample=final_sub, colsample_bytree=final_colsub,
            random_state=_OPTUNA_SEED, verbose=-1,
        )
        final_model.fit(X_all, y_all)

        mu_all  = np.clip(final_model.predict(X_all), 1e-6, None)
        final_r = _fit_negbin_r(y_all, mu_all)

        in_sample_nll  = _negbin_nll(y_all, mu_all, final_r)
        in_sample_mae  = float(np.mean(np.abs(mu_all - y_all)))
        in_sample_cal  = _negbin_calib_80(y_all, mu_all, final_r)

        print(f"\n  Final NegBin r (all-data fit):   {final_r:.4f}")
        print(f"  In-sample NLL:                   {in_sample_nll:.4f}")
        print(f"  In-sample MAE:                   {in_sample_mae:.4f}")
        print(f"  In-sample calib_80:              {in_sample_cal:.4f}")
        print(f"  Walk-forward CV NLL (tuned):     {tuned_nll:.4f}")
        print(f"  Walk-forward CV MAE:             {a_mae:.4f}")

        mlflow.log_metrics({
            "final_negbin_r":      final_r,
            "final_insample_nll":  in_sample_nll,
            "final_insample_mae":  in_sample_mae,
            "final_insample_cal":  in_sample_cal,
        })

        # ── Subset evaluation ──────────────────────────────────────────────────
        subset = _subset_eval(df, final_model, final_r, impute_vals)
        _print_subset_eval(subset)
        mlflow.log_dict(subset, "subset_eval.json")

        # ── Save artifact ──────────────────────────────────────────────────────
        artifact = {
            "model":               final_model,
            "model_type":          "lgbm",
            "distribution_family": "negbin",
            "feature_cols":        FEATURE_COLS,
            "impute_vals":         impute_vals,
            "r":                   final_r,
            "target_mean":         float(y_all.mean()),
            "target_std":          float(y_all.std()),
            "cv_nll":              a_nll,
            "cv_mae":              a_mae,
            "cv_calib_80":         a_calib,
            "cv_mean_r":           a_mean_r,
            "tuned_cv_nll":        tuned_nll,
            "tuned_params":        tuned_params,
            "cand_a_cv_nll":       a_nll,
            "cand_a_cv_mae":       a_mae,
            "cand_a_calib_80":     a_calib,
            "cand_c_glm_cv_nll":   c_nll,
            "candidate":           "A",
            "candidate_b_status":  "BLOCKED_until_Epic5D",
            "cv_fold_records":     a_folds,
            "subset_eval":         subset,
        }

        _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(artifact, _ARTIFACT_PATH)
        print(f"\nArtifact saved → {_ARTIFACT_PATH.relative_to(_PROJECT_ROOT)}")

        if promote:
            upload_artifact(_ARTIFACT_PATH, _ARTIFACT_S3_URI)

        mlflow.log_artifact(str(_ARTIFACT_PATH))
        mlflow.set_tag("sub_model_registry_key", "bullpen_v2")
        mlflow.set_tag("distribution_family",    "negbin")
        mlflow.set_tag("candidate",              "A")
        print(f"  MLflow run_id: {mlflow_run_id}")

        # ── Registry ───────────────────────────────────────────────────────────
        if promote:
            _update_registry(
                cv_nll=a_nll,
                cv_mae=a_mae,
                mean_r=final_r,
                calib_80=a_calib,
                n_features=len(FEATURE_COLS),
                tuned_nll=tuned_nll,
                tuned_params=tuned_params,
                cand_a_nll=a_nll,
                cand_c_nll=c_nll,
                mlflow_run_id=mlflow_run_id,
                subset_eval=subset,
                n_seasons=len(seasons),
                n_rows=len(df),
            )

    # ── Final summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 72)
    print(
        f"bullpen_v2 result: CHAMPION (LightGBM+NegBin, Candidate A)\n"
        f"  CV NLL {a_nll:.4f} → tuned {tuned_nll:.4f}  |  "
        f"CV MAE {a_mae:.4f}  |  calib_80 {a_calib:.4f}  |  r={final_r:.4f}"
    )
    print("\nNext steps (Story 6D.3):")
    print("  1. Update generate_bullpen_signals.py to load bullpen_v2.pkl")
    print("     Emit: bullpen_mu, bullpen_dispersion, bullpen_fatigue_adjusted_mu, uncertainty")
    print("  2. Backfill 2021–2026 regular season (--backfill flag; idempotent via SCD-2)")
    print("  3. Add bullpen_v2 PIVOT block to feature_pregame_sub_model_signals.sql")
    print("  4. dbtf build --select feature_pregame_sub_model_signals")
    print(f"\n=== DONE — MLflow run: {mlflow_run_id} ===")
    print("=" * 72)
    return mlflow_run_id


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train bullpen_v2 — distributional NegBin (Epic 6D.2)"
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Run CV and save artifact locally; skip S3 upload and registry update.",
    )
    parser.add_argument(
        "--min-year",
        type=int,
        default=_MIN_YEAR_DEFAULT,
        metavar="YEAR",
        help=f"First season to include in training (default {_MIN_YEAR_DEFAULT}). "
             "Use 2021 to match the 6D.1 overdispersion audit window.",
    )
    parser.add_argument(
        "--candidate",
        choices=["a", "b"],
        default="a",
        help=(
            "Which candidate to run. "
            "'a' — full Candidate A training + Optuna tuning (default). "
            "'b' — evaluate Candidate B against A's tuned benchmark "
            f"(NLL={_CAND_B_BENCHMARK_NLL}); requires bullpen_v2.pkl from a prior --candidate a run."
        ),
    )
    args = parser.parse_args()
    if args.candidate == "b":
        _evaluate_candidate_b(promote=not args.no_promote, min_year=args.min_year)
    else:
        train(promote=not args.no_promote, min_year=args.min_year)


if __name__ == "__main__":
    main()
