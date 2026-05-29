"""
train_offense_v1.py — Epic 4, Story 4.2

Train Ridge and LightGBM on the offense_v1 feature set (Groups A–G, 55 numeric
+ one-hot encoded starter_pitch_archetype). Walk-forward CV on folds 1–8
(eval years 2018–2025; fold 9/2026 excluded — partial season).

Champion selection: lower mean CV MAE wins. --force-winner overrides.

Outputs:
    betting_ml/models/sub_models/offense_v1/{model_name}_offense_v1.pkl
    betting_ml/models/sub_models/offense_v1/lgbm_best_params.json
    s3://baseball-betting-ml-artifacts/sub_models/offense_v1.pkl
    betting_ml/sub_model_registry.yaml  (offense_v1 entry updated)

Usage:
    uv run python betting_ml/scripts/offense_v1/train_offense_v1.py
    uv run python betting_ml/scripts/offense_v1/train_offense_v1.py --no-promote
    uv run python betting_ml/scripts/offense_v1/train_offense_v1.py --optuna-trials 10
    uv run python betting_ml/scripts/offense_v1/train_offense_v1.py --force-winner lgbm
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd

# LightGBM's sklearn wrapper stores feature names even when fit on numpy arrays.
# Sklearn then warns on every numpy predict call. Results are correct; suppress the noise.
warnings.filterwarnings(
    "ignore",
    message="X does not have valid feature names",
    category=UserWarning,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import upload_artifact
from betting_ml.utils.mlflow_utils import get_or_create_experiment, log_cv_fold

_OUTPUT_DIR       = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v1"
_REGISTRY_PATH    = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_ARTIFACT_S3_URI  = "s3://baseball-betting-ml-artifacts/sub_models/offense_v1.pkl"
_FEAT_COLS_PATH   = _OUTPUT_DIR / "feature_columns.json"
_PARAMS_PATH      = _OUTPUT_DIR / "lgbm_best_params.json"

_OPTUNA_TRIALS    = 50
_EXCLUDE_EVAL_YEAR = 2026   # fold 9 — partial season

# ---------------------------------------------------------------------------
# Feature column inventory (mirrors feature_columns.json)
# ---------------------------------------------------------------------------

NUMERIC_FEATURES: list[str] = [
    # A: EB rates
    "avg_eb_woba", "avg_eb_k_pct", "avg_eb_bb_pct", "avg_eb_iso", "avg_eb_woba_uncertainty",
    # B: raw rolling rates
    "avg_woba_30d", "avg_k_pct_30d", "avg_bb_pct_30d",
    "avg_woba_std", "avg_k_pct_std", "avg_bb_pct_std",
    # C: Statcast / bat tracking
    "avg_xwoba_30d", "avg_hard_hit_pct_30d", "avg_barrel_pct_30d",
    "avg_whiff_rate_30d", "avg_chase_rate_30d",
    "avg_xwoba_std", "avg_hard_hit_pct_std", "avg_barrel_pct_std",
    "lineup_avg_bat_speed", "lineup_bat_speed_std", "lineup_avg_swing_length",
    "lineup_avg_attack_angle", "lineup_bat_speed_vs_starter_velo",
    # D: ZiPS projections
    "avg_zips_wrc_plus", "avg_zips_woba_proxy", "avg_zips_k_pct", "avg_zips_iso",
    "zips_coverage_pct",
    # E: structural / lineup composition
    "lhb_count", "rhb_count", "has_full_lineup", "lineup_depth_score", "lineup_entropy",
    "lineup_rookie_count", "lineup_rookie_pa_share", "injured_player_count",
    "injury_adj_avg_woba_30d", "injury_adj_avg_xwoba_30d",
    "eb_coverage_pct", "catcher_framing_runs", "catcher_defensive_runs",
    # F: platoon splits
    "avg_woba_vs_lhp", "avg_xwoba_vs_lhp", "avg_k_pct_vs_lhp",
    "avg_bb_pct_vs_lhp", "avg_hard_hit_pct_vs_lhp",
    "avg_woba_vs_rhp", "avg_xwoba_vs_rhp", "avg_k_pct_vs_rhp",
    "avg_bb_pct_vs_rhp", "avg_hard_hit_pct_vs_rhp",
    # G: archetype matchup (numeric portion)
    "lineup_woba_vs_starter_archetype", "lineup_xwoba_vs_starter_archetype",
    "lineup_k_pct_vs_starter_archetype", "lineup_iso_vs_starter_archetype",
    "lineup_archetype_pa_coverage",
]

_CAT_FEATURE = "starter_pitch_archetype"
_TARGET      = "runs_scored"

_QUERY = """
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


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    for col in df.select_dtypes(include=["object"]).columns:
        if col == _CAT_FEATURE:
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    df["has_full_lineup"] = df["has_full_lineup"].astype(float)
    df = df.sort_values("game_date").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# CV fold selection (folds 1–8, exclude eval year 2026)
# ---------------------------------------------------------------------------

def get_cv_folds(df: pd.DataFrame) -> list[tuple]:
    all_folds = list(all_season_splits(df, min_train_seasons=3))
    folds_1_8 = [
        (tr, ev) for tr, ev in all_folds
        if int(df.loc[ev, "game_year"].mode()[0]) != _EXCLUDE_EVAL_YEAR
    ]
    return folds_1_8


# ---------------------------------------------------------------------------
# Per-fold data preparation (impute + OHE)
# ---------------------------------------------------------------------------

def _compute_impute_means(train: pd.DataFrame) -> dict[str, float]:
    means: dict[str, float] = {}
    for col in NUMERIC_FEATURES:
        m = train[col].mean()
        means[col] = float(m) if not np.isnan(m) else 0.0
    return means


def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _ohe_archetype(
    train: pd.DataFrame,
    eval_: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """One-hot encode starter_pitch_archetype. Align eval columns to training."""
    train_dummies = pd.get_dummies(train[_CAT_FEATURE], prefix="archetype", dtype=float)
    ohe_cols = sorted(train_dummies.columns.tolist())
    train_dummies = train_dummies[ohe_cols]

    eval_dummies = pd.get_dummies(eval_[_CAT_FEATURE], prefix="archetype", dtype=float)
    for col in ohe_cols:
        if col not in eval_dummies.columns:
            eval_dummies[col] = 0.0
    eval_dummies = eval_dummies[ohe_cols]

    train_out = pd.concat([train.reset_index(drop=True), train_dummies.reset_index(drop=True)], axis=1)
    eval_out  = pd.concat([eval_.reset_index(drop=True),  eval_dummies.reset_index(drop=True)],  axis=1)
    return train_out, eval_out, ohe_cols


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

    train, eval_, ohe_cols = _ohe_archetype(train, eval_)

    all_feat_cols = NUMERIC_FEATURES + ohe_cols
    X_train = train[all_feat_cols].to_numpy(dtype=float)
    y_train = train[_TARGET].to_numpy(dtype=float)
    X_eval  = eval_[all_feat_cols].to_numpy(dtype=float)
    y_eval  = eval_[_TARGET].to_numpy(dtype=float)

    return X_train, y_train, X_eval, y_eval, impute_means, ohe_cols, all_feat_cols


def _april_mask(df: pd.DataFrame, eval_idx) -> np.ndarray:
    """Boolean mask over eval rows where game is in April."""
    dates = pd.to_datetime(df.loc[eval_idx, "game_date"]).dt.month
    return (dates == 4).to_numpy()


# ---------------------------------------------------------------------------
# Ridge CV
# ---------------------------------------------------------------------------

def cv_ridge(df: pd.DataFrame, folds: list[tuple]) -> tuple[float, list[dict]]:
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    alphas = np.logspace(-1, 5, 30)
    fold_records: list[dict] = []

    print(f"\n── Ridge walk-forward CV ({len(folds)} folds) ─────────────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'N_train':>8}  {'N_eval':>7}  "
          f"{'MAE':>6}  {'Bias':>7}  {'April_MAE':>10}  {'Alpha':>10}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        pipe = Pipeline([
            ("scaler", StandardScaler()),
            ("ridge",  RidgeCV(alphas=alphas, cv=5)),
        ])
        pipe.fit(X_tr, y_tr)
        y_pred = pipe.predict(X_ev)

        mae  = float(np.mean(np.abs(y_pred - y_ev)))
        bias = float(np.mean(y_pred - y_ev))
        alpha = float(pipe.named_steps["ridge"].alpha_)

        april = _april_mask(df, eval_idx)
        april_mae = float(np.mean(np.abs(y_pred[april] - y_ev[april]))) if april.any() else float("nan")

        print(f"  {i:>4}  {eval_year:>6}  {len(y_tr):>8,}  {len(y_ev):>7,}  "
              f"{mae:>6.3f}  {bias:>+7.3f}  {april_mae:>10.3f}  {alpha:>10.1f}")

        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "mae": round(mae, 4), "bias": round(bias, 4),
            "april_mae": round(april_mae, 4) if not np.isnan(april_mae) else None,
            "best_alpha": alpha,
        })

    mean_mae = float(np.mean([r["mae"] for r in fold_records]))
    april_maes = [r["april_mae"] for r in fold_records if r["april_mae"] is not None]
    mean_april = float(np.mean(april_maes)) if april_maes else float("nan")
    print(f"\n  Mean CV MAE:    {mean_mae:.4f}")
    print(f"  Mean April MAE: {mean_april:.4f}")
    return mean_mae, fold_records


# ---------------------------------------------------------------------------
# LightGBM — Optuna tuning then final CV
# ---------------------------------------------------------------------------

def _lgbm_trial_objective(
    trial,
    df: pd.DataFrame,
    folds: list[tuple],
):
    import lightgbm as lgb

    params = {
        "num_leaves":        trial.suggest_int("num_leaves", 15, 127),
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
        "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "n_estimators":      500,
        "objective":         "mae",
        "metric":            "mae",   # explicit so early_stopping uses the right eval metric
        "random_state":      42,
        "verbose":           -1,
    }

    fold_maes: list[float] = []
    for train_idx, eval_idx in folds:
        X_tr, y_tr, X_ev, y_ev, _, _, _ = prepare_fold(df, train_idx, eval_idx)
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=20, verbose=False),
                lgb.log_evaluation(-1),
            ],
        )
        y_pred = model.predict(X_ev)
        fold_maes.append(float(np.mean(np.abs(y_pred - y_ev))))

    return float(np.mean(fold_maes))


def tune_lgbm(
    df: pd.DataFrame,
    folds: list[tuple],
    n_trials: int = _OPTUNA_TRIALS,
) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    print(f"\n── LightGBM Optuna tuning ({n_trials} trials × {len(folds)} folds) ──────")
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(
        lambda trial: _lgbm_trial_objective(trial, df, folds),
        n_trials=n_trials,
        show_progress_bar=True,
    )
    best_params = study.best_params
    print(f"\n  Best trial MAE: {study.best_value:.4f}")
    print(f"  Best params:    {best_params}")
    return best_params


def cv_lgbm(
    df: pd.DataFrame,
    folds: list[tuple],
    best_params: dict,
) -> tuple[float, list[dict], list[str], int]:
    import lightgbm as lgb

    lgbm_params = {
        **best_params,
        "n_estimators":  500,
        "objective":     "mae",
        "metric":        "mae",   # explicit so early_stopping uses the right eval metric
        "random_state":  42,
        "verbose":       -1,
    }

    fold_records: list[dict] = []
    all_feat_names: list[str] = []
    best_iters: list[int] = []

    print(f"\n── LightGBM walk-forward CV ({len(folds)} folds) ──────────────────────")
    print(f"  {'Fold':>4}  {'Eval':>6}  {'N_train':>8}  {'N_eval':>7}  "
          f"{'MAE':>6}  {'Bias':>7}  {'April_MAE':>10}  {'BestIter':>9}")

    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        X_tr, y_tr, X_ev, y_ev, _, _, feat_cols = prepare_fold(df, train_idx, eval_idx)
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        if not all_feat_names:
            all_feat_names = feat_cols

        model = lgb.LGBMRegressor(**lgbm_params)
        model.fit(
            X_tr, y_tr,
            eval_set=[(X_ev, y_ev)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=20, verbose=False),
                lgb.log_evaluation(-1),
            ],
        )
        best_iters.append(int(model.best_iteration_))
        y_pred = model.predict(X_ev)

        mae  = float(np.mean(np.abs(y_pred - y_ev)))
        bias = float(np.mean(y_pred - y_ev))

        april = _april_mask(df, eval_idx)
        april_mae = float(np.mean(np.abs(y_pred[april] - y_ev[april]))) if april.any() else float("nan")

        print(f"  {i:>4}  {eval_year:>6}  {len(y_tr):>8,}  {len(y_ev):>7,}  "
              f"{mae:>6.3f}  {bias:>+7.3f}  {april_mae:>10.3f}  {model.best_iteration_:>9}")

        fold_records.append({
            "fold": i, "eval_year": eval_year,
            "n_train": int(len(y_tr)), "n_eval": int(len(y_ev)),
            "mae": round(mae, 4), "bias": round(bias, 4),
            "april_mae": round(april_mae, 4) if not np.isnan(april_mae) else None,
            "best_iteration": int(model.best_iteration_),
        })

    mean_mae = float(np.mean([r["mae"] for r in fold_records]))
    april_maes = [r["april_mae"] for r in fold_records if r["april_mae"] is not None]
    mean_april = float(np.mean(april_maes)) if april_maes else float("nan")
    mean_best_iter = int(round(float(np.mean(best_iters))))

    print(f"\n  Mean CV MAE:    {mean_mae:.4f}")
    print(f"  Mean April MAE: {mean_april:.4f}")
    print(f"  Mean best iter: {mean_best_iter}")
    return mean_mae, fold_records, all_feat_names, mean_best_iter


# ---------------------------------------------------------------------------
# Feature importance (LightGBM)
# ---------------------------------------------------------------------------

def _print_feature_importance(model, feat_names: list[str]) -> int:
    """Print ranked feature importances. Returns rank of avg_eb_woba_uncertainty."""
    importances = model.feature_importances_
    ranked = sorted(zip(feat_names, importances), key=lambda x: x[1], reverse=True)
    max_val = ranked[0][1] if ranked else 1

    print("\n── LightGBM feature importance (split count, top 30) ────────────")
    eb_uncertainty_rank = -1
    for rank, (feat, val) in enumerate(ranked, 1):
        if feat == "avg_eb_woba_uncertainty":
            eb_uncertainty_rank = rank
        if rank <= 30:
            bar = "█" * int(val / max_val * 25)
            marker = " ◄ avg_eb_woba_uncertainty" if feat == "avg_eb_woba_uncertainty" else ""
            print(f"  {rank:>3}. {feat:<50s} {val:>6}  {bar}{marker}")

    if eb_uncertainty_rank > 30:
        print(f"\n  avg_eb_woba_uncertainty rank: {eb_uncertainty_rank} (outside top 30)")
    print(f"\n  avg_eb_woba_uncertainty rank: {eb_uncertainty_rank} / {len(ranked)}")
    if eb_uncertainty_rank <= 20:
        print("  FLAG: avg_eb_woba_uncertainty rank ≤ 20 — candidate standalone feature (see 4.3 spec)")
    return eb_uncertainty_rank


# ---------------------------------------------------------------------------
# Champion selection
# ---------------------------------------------------------------------------

def select_champion(
    ridge_mae: float,
    lgbm_mae: float,
    ridge_fold_maes: list[float],
    lgbm_fold_maes: list[float],
    force_winner: str | None = None,
) -> tuple[str, float | None]:
    """Select champion between Ridge and LightGBM.

    Returns (champion_type, wilcoxon_pval).

    New-model case (no prior champion):
        Lower mean CV MAE wins.  --force-winner overrides.

    Future challenger case (prior champion exists) — three gates, all must pass:
        1. Paired Wilcoxon signed-rank test on fold MAEs (p < 0.05)
        2. Minimum absolute improvement vs. prior champion CV MAE
        3. Challenger wins on ≥ 5/8 folds (fold consistency)
    This function implements the new-model case only; the challenger gate should
    be added in the training script of whatever version supersedes offense_v1.
    """
    from scipy.stats import wilcoxon

    delta = ridge_mae - lgbm_mae  # positive = LightGBM is better

    print("\n" + "=" * 64)
    print("Champion selection")
    print("=" * 64)
    print(f"  Ridge CV MAE:    {ridge_mae:.4f}  (fold MAEs: {[round(x,4) for x in ridge_fold_maes]})")
    print(f"  LightGBM CV MAE: {lgbm_mae:.4f}  (fold MAEs: {[round(x,4) for x in lgbm_fold_maes]})")
    print(f"  Delta (Ridge − LGBM): {delta:+.4f}")

    # Fold-level win count
    lgbm_fold_wins = sum(l < r for l, r in zip(lgbm_fold_maes, ridge_fold_maes))
    print(f"  LightGBM wins {lgbm_fold_wins}/{len(lgbm_fold_maes)} folds")

    # Paired Wilcoxon on fold differences (informational for new-model run)
    diffs = [r - l for r, l in zip(ridge_fold_maes, lgbm_fold_maes)]
    try:
        _, pval = wilcoxon(diffs)
        print(f"  Wilcoxon signed-rank p={pval:.4f} (informational; gate applies to challenger runs)")
    except Exception:
        pval = None
        print("  Wilcoxon: insufficient data for test")

    if force_winner is not None:
        force_winner = force_winner.lower()
        assert force_winner in ("ridge", "lgbm"), "--force-winner must be 'ridge' or 'lgbm'"
        print(f"\n  --force-winner override → {force_winner}")
        return force_winner, pval

    # New-model case: lower mean CV MAE wins outright
    if lgbm_mae < ridge_mae:
        print(f"  Winner: LightGBM (lower CV MAE by {delta:.4f} runs)")
        return "lgbm", pval
    else:
        print(f"  Winner: Ridge (LightGBM did not improve on Ridge)")
        return "ridge", pval


# ---------------------------------------------------------------------------
# Final model training and artifact persistence
# ---------------------------------------------------------------------------

def _prepare_final_train(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, dict, list[str], list[str]]:
    """Train on 2015–2025 (all complete seasons; exclude 2026 partial)."""
    train = df[df["game_year"] != _EXCLUDE_EVAL_YEAR].copy()

    impute_means = _compute_impute_means(train)
    train = _apply_impute(train, impute_means)

    train_dummies = pd.get_dummies(train[_CAT_FEATURE], prefix="archetype", dtype=float)
    ohe_cols = sorted(train_dummies.columns.tolist())
    train_dummies = train_dummies[ohe_cols]
    train = pd.concat([train.reset_index(drop=True), train_dummies.reset_index(drop=True)], axis=1)

    all_feat_cols = NUMERIC_FEATURES + ohe_cols
    X = train[all_feat_cols].to_numpy(dtype=float)
    y = train[_TARGET].to_numpy(dtype=float)
    return X, y, impute_means, ohe_cols, all_feat_cols


def train_final_ridge(
    df: pd.DataFrame,
    fold_records: list[dict],
) -> dict:
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    X, y, impute_means, ohe_cols, feat_cols = _prepare_final_train(df)
    alphas = np.logspace(-1, 5, 30)
    pipe = Pipeline([("scaler", StandardScaler()), ("ridge", RidgeCV(alphas=alphas, cv=5))])
    pipe.fit(X, y)
    print(f"\n  Final Ridge alpha: {pipe.named_steps['ridge'].alpha_:.2f}  "
          f"(trained on {len(y):,} rows)")

    return {
        "model_type": "ridge",
        "model":         pipe,
        "impute_means":  impute_means,
        "ohe_categories": ohe_cols,
        "feature_names": feat_cols,
        "cv_mae":        round(float(np.mean([r["mae"] for r in fold_records])), 4),
        "cv_fold_records": fold_records,
    }


def train_final_lgbm(
    df: pd.DataFrame,
    best_params: dict,
    mean_best_iter: int,
    fold_records: list[dict],
) -> dict:
    import lightgbm as lgb

    X, y, impute_means, ohe_cols, feat_cols = _prepare_final_train(df)

    final_params = {
        **best_params,
        "n_estimators":  mean_best_iter,
        "objective":     "mae",
        "random_state":  42,
        "verbose":       -1,
    }
    model = lgb.LGBMRegressor(**final_params)
    model.fit(X, y)
    print(f"\n  Final LightGBM n_estimators: {mean_best_iter}  "
          f"(trained on {len(y):,} rows)")

    eb_rank = _print_feature_importance(model, feat_cols)

    return {
        "model_type":      "lgbm",
        "model":           model,
        "impute_means":    impute_means,
        "ohe_categories":  ohe_cols,
        "feature_names":   feat_cols,
        "cv_mae":          round(float(np.mean([r["mae"] for r in fold_records])), 4),
        "cv_fold_records": fold_records,
        "eb_uncertainty_rank": eb_rank,
    }


def save_artifact(artifact: dict, promote: bool) -> Path:
    model_name = artifact["model_type"]
    local_path = _OUTPUT_DIR / f"{model_name}_offense_v1.pkl"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, local_path)
    print(f"\n  Saved → {local_path.relative_to(_PROJECT_ROOT)}")

    if promote:
        upload_artifact(local_path, _ARTIFACT_S3_URI)
    else:
        print(f"  [--no-promote] Skipping S3 upload")
    return local_path


def save_lgbm_params(best_params: dict, mean_best_iter: int, cv_mae: float) -> None:
    payload = {
        "best_params": best_params,
        "mean_best_iteration": mean_best_iter,
        "optuna_cv_mae": round(cv_mae, 4),
    }
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _PARAMS_PATH.write_text(json.dumps(payload, indent=2))
    print(f"  Saved → {_PARAMS_PATH.relative_to(_PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def update_registry(
    artifact: dict,
    local_path: Path,
    lgbm_params: dict | None,
    promote: bool,
    ridge_mae: float | None = None,
    lgbm_mae: float | None = None,
    ridge_fold_maes: list[float] | None = None,
    lgbm_fold_maes: list[float] | None = None,
    wilcoxon_p: float | None = None,
    mlflow_run_id: str | None = None,
) -> None:
    import datetime
    import re
    text = _REGISTRY_PATH.read_text()

    model_type    = artifact["model_type"]
    cv_mae        = artifact["cv_mae"]
    feat_count    = len(artifact["feature_names"])
    s3_path       = _ARTIFACT_S3_URI if promote else str(local_path)
    today         = datetime.date.today().isoformat()

    eb_rank_note = (
        f"avg_eb_woba_uncertainty rank {artifact.get('eb_uncertainty_rank', 'N/A')} / {feat_count}"
        if model_type == "lgbm" else "N/A (Ridge model)"
    )
    arch_note = "RidgeCV(alphas=logspace(-1,5,30), cv=5) + StandardScaler" if model_type == "ridge" \
                else f"LightGBM; Optuna 50 trials; best_iter={lgbm_params.get('mean_best_iteration', 'N/A') if lgbm_params else 'N/A'}"

    # Champion selection summary for notes
    if ridge_mae is not None and lgbm_mae is not None:
        delta = ridge_mae - lgbm_mae
        lgbm_wins = sum(l < r for l, r in zip(lgbm_fold_maes or [], ridge_fold_maes or []))
        total_folds = len(lgbm_fold_maes or [])
        p_str = f"{wilcoxon_p:.4f}" if wilcoxon_p is not None else "N/A"
        selection_note = (
            f"Champion selection (Case 1 — new model): Ridge MAE {ridge_mae:.4f} vs LightGBM {lgbm_mae:.4f}; "
            f"delta {delta:+.4f}; LGBM wins {lgbm_wins}/{total_folds} folds; Wilcoxon p={p_str}. "
            f"Winner: {model_type.upper()}."
        )
        # Bias summary
        if model_type == "lgbm" and lgbm_fold_maes is not None:
            bias_values = [r.get("bias") for r in (artifact.get("cv_fold_records") or []) if r.get("bias") is not None]
            if bias_values:
                mean_bias = sum(bias_values) / len(bias_values)
                bias_note = (
                    f"LightGBM mean CV bias: {mean_bias:+.3f} runs/game-side (systematic under-prediction; "
                    f"apply scalar bias correction in generate_offense_signals.py)."
                )
            else:
                bias_note = ""
        else:
            bias_values = [r.get("bias") for r in (artifact.get("cv_fold_records") or []) if r.get("bias") is not None]
            mean_bias = sum(bias_values) / len(bias_values) if bias_values else 0.0
            bias_note = f"Ridge mean CV bias: {mean_bias:+.3f} runs/game-side."
    else:
        selection_note = ""
        bias_note = ""

    mlflow_run_id_line = mlflow_run_id if mlflow_run_id is not None else "null  # set on next retrain"

    new_block = f"""offense_v1:
  artifact_path: {s3_path}
  feature_columns_path: models/sub_models/offense_v1/feature_columns.json
  mlflow_run_id: {mlflow_run_id_line}
  target:
    source_table: baseball_data.betting.mart_game_results
    primary_column: runs_scored   # one row per game-side (home or away)
    auxiliary_columns: []
    grain: game_pk_side
  training_window:
    start: '2015-01-01'
    end: null
  cv_strategy: walk_forward_season
  cv_folds: 8   # eval years 2018-2025; fold 9 (2026 partial) excluded from CV
  cv_metric: mae
  cv_score: {cv_mae}
  promotion_gate:
    metric: mae
    threshold: null   # new model; no prior baseline
    direction: lower_is_better
  parent_features:
    - feature_pregame_lineup_features
  output_signals:
    - pred_runs_raw
    - runs_index
  downstream_consumers: []
  promotion_status: champion
  promoted_at: '{today}'
  notes: |
    Story 4.2 ({today}). Training window 2015+; target = runs_scored (one row per game-side).
    Features: Groups A-G (55 numeric + one-hot starter_pitch_archetype = {feat_count} total).
    Group A (EB rates) fully populated 2015+; backfilled via mart_batter_rolling_stats fallback for 2015-2019.
    Group C bat-tracking ~50% null (data available from ~2023-07-14).
    Architecture: {arch_note}.
    CV: walk-forward, folds 1-8 (eval years 2018-2025); fold 9 (2026 partial) excluded.
    {selection_note}
    {bias_note}
    eb_uncertainty_rank: {eb_rank_note}.
"""

    # Replace the stale offense_v1 block — find it and replace through to next top-level key
    import re
    pattern = r"^offense_v1:.*?(?=^\S)"
    replacement = new_block + "\n"
    new_text = re.sub(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)

    if new_text == text:
        # Pattern didn't match — append
        new_text = text.rstrip() + "\n\n" + new_block
        print("  [WARN] Could not locate offense_v1 block; appended to registry")
    else:
        print(f"  Updated offense_v1 in {_REGISTRY_PATH.relative_to(_PROJECT_ROOT)}")

    _REGISTRY_PATH.write_text(new_text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def train(
    promote: bool = True,
    optuna_trials: int = _OPTUNA_TRIALS,
    force_winner: str | None = None,
) -> str:
    """Run the full offense_v1 training pipeline. Returns the MLflow run ID."""
    print("=== EPIC 4.2 — OFFENSE_V1 TRAINING ===\n")
    print("Loading data from Snowflake...")
    df = load_data()
    print(f"  Loaded {len(df):,} rows × {df.shape[1]} cols "
          f"({df['game_year'].min():.0f}–{df['game_year'].max():.0f})")

    folds = get_cv_folds(df)
    eval_years = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in folds]
    print(f"  CV folds: {len(folds)} (eval years {eval_years[0]}–{eval_years[-1]})")

    # ── MLflow experiment setup ───────────────────────────────────────────────
    mlflow.set_experiment("offense_v1")
    get_or_create_experiment("offense_v1")

    with mlflow.start_run(run_name=f"retrain_{date.today()}") as mlflow_run:
        mlflow_run_id = mlflow_run.info.run_id

        # Log data and CV config params
        mlflow.log_params({
            "train_start": "2015-01-01",
            "n_rows": len(df),
            "n_seasons": int(df["game_year"].nunique()),
            "n_folds": len(folds),
            "eval_years": str(eval_years),
            "exclude_eval_year": _EXCLUDE_EVAL_YEAR,
            "min_train_seasons": 3,
            "optuna_trials": optuna_trials,
            "force_winner": str(force_winner),
        })

        # ── Ridge ────────────────────────────────────────────────────────────
        ridge_mae, ridge_folds = cv_ridge(df, folds)
        mlflow.log_metric("ridge_cv_mae", ridge_mae)
        for rec in ridge_folds:
            log_cv_fold(rec["fold"], rec["eval_year"], {
                "ridge_mae": rec["mae"],
                "ridge_bias": rec["bias"],
                "ridge_april_mae": rec["april_mae"],
            })

        # ── LightGBM ─────────────────────────────────────────────────────────
        best_lgbm_params = tune_lgbm(df, folds, n_trials=optuna_trials)
        lgbm_mae, lgbm_folds, feat_names, mean_best_iter = cv_lgbm(df, folds, best_lgbm_params)
        mlflow.log_metric("lgbm_cv_mae", lgbm_mae)
        mlflow.log_metric("mean_cv_mae", lgbm_mae)
        for key, val in best_lgbm_params.items():
            mlflow.log_param(f"best_{key}", val)
        mlflow.log_param("best_mean_iteration", mean_best_iter)
        for rec in lgbm_folds:
            log_cv_fold(rec["fold"], rec["eval_year"], {
                "lgbm_mae": rec["mae"],
                "lgbm_bias": rec["bias"],
                "lgbm_april_mae": rec["april_mae"],
                "best_iteration": rec.get("best_iteration"),
            })

        # ── April-only comparison ─────────────────────────────────────────────
        print("\n── April-only MAE comparison ──────────────────────────────────────")
        print(f"  {'Year':>6}  {'Ridge_April':>12}  {'LGBM_April':>11}")
        for rr, lr in zip(ridge_folds, lgbm_folds):
            r_a = f"{rr['april_mae']:.3f}" if rr['april_mae'] is not None else "  —  "
            l_a = f"{lr['april_mae']:.3f}" if lr['april_mae'] is not None else "  —  "
            print(f"  {rr['eval_year']:>6}  {r_a:>12}  {l_a:>11}")
        ridge_april_maes = [r["april_mae"] for r in ridge_folds if r["april_mae"] is not None]
        lgbm_april_maes  = [r["april_mae"] for r in lgbm_folds  if r["april_mae"] is not None]
        if ridge_april_maes and lgbm_april_maes:
            print(f"  {'Mean':>6}  {np.mean(ridge_april_maes):>12.3f}  {np.mean(lgbm_april_maes):>11.3f}")
            mlflow.log_metric("ridge_mean_april_mae", float(np.mean(ridge_april_maes)))
            mlflow.log_metric("lgbm_mean_april_mae", float(np.mean(lgbm_april_maes)))

        # ── Champion ──────────────────────────────────────────────────────────
        ridge_fold_maes = [r["mae"] for r in ridge_folds]
        lgbm_fold_maes  = [r["mae"] for r in lgbm_folds]
        champion_type, wilcoxon_p = select_champion(
            ridge_mae, lgbm_mae,
            ridge_fold_maes, lgbm_fold_maes,
            force_winner=force_winner,
        )
        lgbm_fold_wins = sum(l < r for l, r in zip(lgbm_fold_maes, ridge_fold_maes))
        mlflow.log_params({
            "champion_type": champion_type,
            "lgbm_fold_wins": lgbm_fold_wins,
            "wilcoxon_p": round(wilcoxon_p, 4) if wilcoxon_p is not None else "N/A",
        })

        # ── Save LightGBM params ──────────────────────────────────────────────
        save_lgbm_params(best_lgbm_params, mean_best_iter, lgbm_mae)

        # ── Train final model and save ────────────────────────────────────────
        print(f"\n── Training final {champion_type} model on 2015–2025 ─────────────")
        if champion_type == "ridge":
            artifact = train_final_ridge(df, ridge_folds)
        else:
            artifact = train_final_lgbm(df, best_lgbm_params, mean_best_iter, lgbm_folds)

        local_path = save_artifact(artifact, promote=promote)

        # Log feature importance params if LightGBM won
        if champion_type == "lgbm":
            eb_rank = artifact.get("eb_uncertainty_rank", -1)
            mlflow.log_params({
                "eb_woba_uncertainty_rank": eb_rank,
                "n_features": len(artifact.get("feature_names", [])),
            })

        # Log artifacts to MLflow
        mlflow.log_artifact(str(local_path))
        mlflow.log_artifact(str(_FEAT_COLS_PATH))
        if _PARAMS_PATH.exists():
            mlflow.log_artifact(str(_PARAMS_PATH))

        mlflow.set_tag("sub_model_registry_key", "offense_v1")
        print(f"\n  MLflow run_id: {mlflow_run_id}")

        # ── Registry ──────────────────────────────────────────────────────────
        if promote:
            lgbm_meta = {"mean_best_iteration": mean_best_iter} if champion_type == "lgbm" else None
            update_registry(
                artifact, local_path, lgbm_meta, promote=True,
                ridge_mae=ridge_mae, lgbm_mae=lgbm_mae,
                ridge_fold_maes=ridge_fold_maes, lgbm_fold_maes=lgbm_fold_maes,
                wilcoxon_p=wilcoxon_p,
                mlflow_run_id=mlflow_run_id,
            )

    print("\n=== DONE ===")
    print(f"  Champion: {champion_type}  |  CV MAE: {artifact['cv_mae']:.4f}")
    print(f"  Artifact: {local_path.relative_to(_PROJECT_ROOT)}")
    if promote:
        print(f"  S3:       {_ARTIFACT_S3_URI}")
    print(f"  MLflow run: {mlflow_run_id}  (mlflow ui to browse)")
    return mlflow_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Epic 4.2 — train offense_v1")
    parser.add_argument("--no-promote", action="store_true",
                        help="Skip S3 upload and registry update")
    parser.add_argument("--optuna-trials", type=int, default=_OPTUNA_TRIALS,
                        help=f"Number of Optuna trials (default {_OPTUNA_TRIALS})")
    parser.add_argument("--force-winner", choices=["ridge", "lgbm"], default=None,
                        help="Override champion selection (document reason in registry notes)")
    args = parser.parse_args()
    train(
        promote=not args.no_promote,
        optuna_trials=args.optuna_trials,
        force_winner=args.force_winner,
    )


if __name__ == "__main__":
    main()
