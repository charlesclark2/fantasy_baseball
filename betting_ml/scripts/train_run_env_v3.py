"""
train_run_env_v3.py — Run Environment Sub-Model v3 (Epic 3, Story 3.5)

Retrains the run environment model with two structural changes:

  1. Drops dead features confirmed by both Ridge v1 and XGBoost v2:
       ump_k_pct_zscore    (SHAP = 0.000 in v2; shrunk to ~0 under Ridge v1)
       ump_bb_pct_zscore   (same)

  2. Adds MLB rules-change era features (derived from game_date and training
     data — no new Snowflake tables or query changes required):
       is_universal_dh              (1 from 2022-04-07, else 0)
       is_pitch_clock_era           (1 from 2023-03-30, else 0)
       is_shift_ban_era             (1 from 2023-03-30, else 0)
       prior_season_lg_runs_per_game (prior season league avg; no leakage)

  Both Ridge and XGBoost are evaluated on identical CV folds with the same
  19-feature set. The better-performing variant is promoted as v3.

Motivation: The 2023 walk-forward fold in v1/v2 produced a -1.229 run/game bias
because the pitch clock and shift ban structurally shifted offensive environment
in a way the model had no features to represent. A persistent -0.556 run/game
bias across all seasons confirms systematic under-prediction.

Net feature count: 19 (was 17 — drop 2, add 4).
Promotion gate: CV MAE < 3.4604 (v1 baseline 3.5104, minus 0.05).

Usage:
    uv run python betting_ml/scripts/train_run_env_v3.py
    uv run python betting_ml/scripts/train_run_env_v3.py --no-promote
"""

from __future__ import annotations

import argparse
import itertools
import json
import pickle
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.train_run_env import (
    load_training_data,
    validate_no_leakage,
    _print_calibration,
    _VENUE_ELEVATION_FT,
    _TRAINING_START,
)
from betting_ml.utils.training_cache import get_cached_df

_V1_CV_MAE        = 3.5104
_PROMOTION_GATE   = 0.05
_PROMOTE_THRESHOLD = 3.4604

_REGISTRY_PATH    = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
_ARTIFACT_PATH    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v3.pkl"
_FEATURE_COLS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v3_features.json"

# ---------------------------------------------------------------------------
# Feature specification (v3)
# ---------------------------------------------------------------------------

_PARK_FEATURES = [
    "eb_park_run_factor",
    "elevation_ft",
    "center_ft",
    "is_dome",
]

_WEATHER_FEATURES = [
    "temp_f",
    "wind_component_mph",
    "humidity_pct",
]

# ump_k_pct_zscore and ump_bb_pct_zscore dropped — SHAP=0 in both Ridge v1 and XGBoost v2.
_UMPIRE_FEATURES = [
    "ump_runs_per_game_zscore",
    "ump_run_impact_zscore",
]

_ERA_FEATURES = [
    "is_universal_dh",               # NL adopted DH permanently; 1 from 2022 Opening Day
    "is_pitch_clock_era",            # pitch clock introduced; 1 from 2023 Opening Day
    "is_shift_ban_era",              # defensive shift banned; 1 from 2023 Opening Day
    "prior_season_lg_runs_per_game", # prior season league avg runs/game
]

_CONTROL_FEATURES = [
    "home_off_woba_30d",
    "away_off_woba_30d",
    "home_starter_proj_fip",
    "away_starter_proj_fip",
    "home_starter_xwoba_30d",
    "away_starter_xwoba_30d",
]

FEATURE_COLS_V3 = (
    _PARK_FEATURES + _WEATHER_FEATURES + _UMPIRE_FEATURES + _ERA_FEATURES + _CONTROL_FEATURES
)

_ALPHA_GRID = [0.01, 0.1, 1.0, 10.0, 100.0, 1000.0]

_XGB_PARAM_GRID = {
    "n_estimators":     [200, 500],
    "max_depth":        [3, 5],
    "learning_rate":    [0.05, 0.1],
    "subsample":        [0.8],
    "colsample_bytree": [0.8],
    "min_child_weight": [3],
}

_IMPUTE_COLS = {
    # eb_park_run_factor is always non-null (EB prior covers all venues); no park imputation.
    "fip":   ["home_starter_proj_fip", "away_starter_proj_fip"],
    "woba":  ["home_off_woba_30d", "away_off_woba_30d"],
    "xwoba": ["home_starter_xwoba_30d", "away_starter_xwoba_30d"],
}

_UNIVERSAL_DH_DATE = pd.Timestamp("2022-04-07")
_PITCH_CLOCK_DATE  = pd.Timestamp("2023-03-30")
_SHIFT_BAN_DATE    = pd.Timestamp("2023-03-30")

# ---------------------------------------------------------------------------
# Era feature engineering
# ---------------------------------------------------------------------------

def _compute_prior_season_runs(df: pd.DataFrame) -> dict[int, float]:
    """Per-season league avg runs/game. Called on train split only — no leakage."""
    return df.groupby("game_year")["total_runs"].mean().to_dict()


def _add_era_features(df: pd.DataFrame, prior_season_runs: dict[int, float]) -> pd.DataFrame:
    """Derive era columns from game_date and prior_season_runs dict.

    prior_season_lg_runs_per_game maps game_year-1 to the dict. For rows where
    the prior year predates the training window (2021 rows → 2020), falls back
    to the mean of available seasons.
    """
    df = df.copy()
    dates = pd.to_datetime(df["game_date"])

    df["is_universal_dh"]            = (dates >= _UNIVERSAL_DH_DATE).astype(float)
    df["is_pitch_clock_era"]         = (dates >= _PITCH_CLOCK_DATE).astype(float)
    df["is_shift_ban_era"]           = (dates >= _SHIFT_BAN_DATE).astype(float)

    fallback = float(np.mean(list(prior_season_runs.values()))) if prior_season_runs else 8.77
    df["prior_season_lg_runs_per_game"] = df["game_year"].map(
        lambda y: prior_season_runs.get(y - 1, fallback)
    )
    return df


# ---------------------------------------------------------------------------
# Imputation
# ---------------------------------------------------------------------------

def _compute_impute_values_v3(train_df: pd.DataFrame) -> dict:
    vals: dict = {}
    for col in FEATURE_COLS_V3:
        if col in train_df.columns:
            col_mean = train_df[col].mean()
            vals[f"_col_{col}"] = float(col_mean) if not np.isnan(col_mean) else 0.0

    # No park imputation: eb_park_run_factor is always non-null (prior covers all venues).

    fip_vals = []
    for col in _IMPUTE_COLS["fip"]:
        if col in train_df:
            fip_vals.extend(train_df[col].dropna().tolist())
    vals["_fip_mean"] = float(np.mean(fip_vals)) if fip_vals else 4.30

    woba_vals = []
    for col in _IMPUTE_COLS["woba"]:
        if col in train_df:
            woba_vals.extend(train_df[col].dropna().tolist())
    vals["_woba_mean"] = float(np.mean(woba_vals)) if woba_vals else 0.315

    xwoba_vals = []
    for col in _IMPUTE_COLS["xwoba"]:
        if col in train_df:
            xwoba_vals.extend(train_df[col].dropna().tolist())
    vals["_xwoba_mean"] = float(np.mean(xwoba_vals)) if xwoba_vals else 0.315

    return vals


def _apply_imputation_v3(df: pd.DataFrame, impute_vals: dict) -> pd.DataFrame:
    df = df.copy()

    # No park imputation: eb_park_run_factor is always non-null.
    for col in _UMPIRE_FEATURES:
        if col in df.columns:
            df[col] = df[col].fillna(0.0)
    for col in _IMPUTE_COLS["fip"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_fip_mean"])
    for col in _IMPUTE_COLS["woba"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_woba_mean"])
    for col in _IMPUTE_COLS["xwoba"]:
        if col in df.columns:
            df[col] = df[col].fillna(impute_vals["_xwoba_mean"])

    if "elevation_ft" in df.columns and "venue_id" in df.columns:
        null_elev = df["elevation_ft"].isna()
        if null_elev.any():
            df.loc[null_elev, "elevation_ft"] = df.loc[null_elev, "venue_id"].map(
                _VENUE_ELEVATION_FT
            )

    for col in FEATURE_COLS_V3:
        if col in df.columns and df[col].isna().any():
            df[col] = df[col].fillna(impute_vals.get(f"_col_{col}", 0.0))

    return df


def _prepare_fold(
    df: pd.DataFrame, train_seasons: list, test_season: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """Slice, add era features (train-split-only), impute, and return X/y arrays."""
    train_df = df[df["game_year"].isin(train_seasons)].copy()
    test_df  = df[df["game_year"] == test_season].copy()

    prior_season_runs = _compute_prior_season_runs(train_df)
    train_df = _add_era_features(train_df, prior_season_runs)
    test_df  = _add_era_features(test_df,  prior_season_runs)

    impute_vals = _compute_impute_values_v3(train_df)
    train_imp   = _apply_imputation_v3(train_df, impute_vals)
    test_imp    = _apply_imputation_v3(test_df,  impute_vals)

    X_train = train_imp[FEATURE_COLS_V3].to_numpy(dtype=float)
    y_train = train_imp["total_runs"].to_numpy(dtype=float)
    X_test  = test_imp[FEATURE_COLS_V3].to_numpy(dtype=float)
    y_test  = test_imp["total_runs"].to_numpy(dtype=float)

    return X_train, y_train, X_test, y_test, impute_vals


# ---------------------------------------------------------------------------
# Ridge CV
# ---------------------------------------------------------------------------

def _walk_forward_cv_ridge(df: pd.DataFrame) -> tuple[float, float, list[dict]]:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    seasons = sorted(df["game_year"].unique())
    folds   = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]

    best_alpha   = 1.0
    best_mean_mae = float("inf")

    for alpha in _ALPHA_GRID:
        fold_maes = []
        for train_seasons, test_season in folds:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, train_seasons, test_season)
            pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
            pipe.fit(X_tr, y_tr)
            fold_maes.append(float(np.mean(np.abs(pipe.predict(X_te) - y_te))))

        mean_mae = float(np.mean(fold_maes))
        if mean_mae < best_mean_mae:
            best_mean_mae = mean_mae
            best_alpha    = alpha

    fold_records = []
    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, train_seasons, test_season)
        pipe = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=best_alpha))])
        pipe.fit(X_tr, y_tr)
        y_pred = pipe.predict(X_te)
        fold_records.append({
            "fold": len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train": int(len(y_tr)),
            "n_test":  int(len(y_te)),
            "mae":  round(float(np.mean(np.abs(y_pred - y_te))), 4),
            "bias": round(float(np.mean(y_pred - y_te)),         4),
        })

    return best_alpha, round(best_mean_mae, 4), fold_records


# ---------------------------------------------------------------------------
# XGBoost CV
# ---------------------------------------------------------------------------

def _expand_grid(grid: dict) -> list[dict]:
    keys   = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    return [dict(zip(keys, combo)) for combo in combos]


def _walk_forward_cv_xgb(df: pd.DataFrame) -> tuple[dict, float, list[dict]]:
    from xgboost import XGBRegressor

    seasons      = sorted(df["game_year"].unique())
    folds        = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    param_combos = _expand_grid(_XGB_PARAM_GRID)
    print(f"  Grid: {len(param_combos)} param combos × {len(folds)} folds = {len(param_combos)*len(folds)} fits")

    best_params   = param_combos[0]
    best_mean_mae = float("inf")

    for params in param_combos:
        fold_maes = []
        for train_seasons, test_season in folds:
            X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, train_seasons, test_season)
            model = XGBRegressor(
                objective="reg:absoluteerror",
                tree_method="hist",
                random_state=42,
                verbosity=0,
                **params,
            )
            model.fit(X_tr, y_tr)
            fold_maes.append(float(np.mean(np.abs(model.predict(X_te) - y_te))))

        mean_mae = float(np.mean(fold_maes))
        if mean_mae < best_mean_mae:
            best_mean_mae = mean_mae
            best_params   = params

    fold_records = []
    for train_seasons, test_season in folds:
        X_tr, y_tr, X_te, y_te, _ = _prepare_fold(df, train_seasons, test_season)
        model = XGBRegressor(
            objective="reg:absoluteerror",
            tree_method="hist",
            random_state=42,
            verbosity=0,
            **best_params,
        )
        model.fit(X_tr, y_tr)
        y_pred = model.predict(X_te)
        fold_records.append({
            "fold": len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train": int(len(y_tr)),
            "n_test":  int(len(y_te)),
            "mae":  round(float(np.mean(np.abs(y_pred - y_te))), 4),
            "bias": round(float(np.mean(y_pred - y_te)),         4),
        })

    return best_params, round(best_mean_mae, 4), fold_records


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_cv_table(label: str, fold_records: list[dict], best_param_str: str) -> None:
    mean_mae  = float(np.mean([r["mae"]  for r in fold_records]))
    mean_bias = float(np.mean([r["bias"] for r in fold_records]))
    print(f"\n── {label} walk-forward CV ──────────────────────────────────")
    print(f"  Best params: {best_param_str}")
    print(f"  {'Fold':>4}  {'Train':>16}  {'Test':>6}  {'N_train':>7}  {'N_test':>6}  {'MAE':>6}  {'Bias':>7}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>16}  {r['test_season']:>6}  "
            f"{r['n_train']:>7}  {r['n_test']:>6}  {r['mae']:>6.3f}  {r['bias']:>+7.3f}"
        )
    print(f"  {'Mean':>4}  {'':>48}  {mean_mae:>6.3f}  {mean_bias:>+7.3f}")


def _print_shap_importance(model, X: np.ndarray) -> None:
    try:
        import shap
        explainer  = shap.TreeExplainer(model)
        shap_vals  = explainer.shap_values(X)
        mean_shap  = np.abs(shap_vals).mean(axis=0)
        max_val    = mean_shap.max() if mean_shap.max() > 0 else 1.0
        print("\n── SHAP feature importance (mean |SHAP|) ───────────────────")
        for feat, val in sorted(zip(FEATURE_COLS_V3, mean_shap), key=lambda x: x[1], reverse=True):
            bar = "█" * int(val / max_val * 20)
            print(f"  {feat:<40s} {val:.4f}  {bar}")
    except Exception as exc:
        print(f"  [SHAP unavailable: {exc}] Using gain importance.")
        scores = model.get_booster().get_score(importance_type="gain")
        imp = {feat: scores.get(f"f{i}", 0.0) for i, feat in enumerate(FEATURE_COLS_V3)}
        for feat, val in sorted(imp.items(), key=lambda x: x[1], reverse=True):
            print(f"  {feat:<40s} {val:.4f}")


def _print_comparison(
    ridge_mae: float, xgb_mae: float,
    ridge_folds: list[dict], xgb_folds: list[dict],
) -> tuple[str, float]:
    """Print 3-way comparison table. Returns (winner_type, winner_mae).

    winner_type is 'ridge', 'xgb', or 'none'.
    """
    ridge_delta = ridge_mae - _V1_CV_MAE
    xgb_delta   = xgb_mae   - _V1_CV_MAE
    ridge_gate  = "PASS ✓" if ridge_mae < _PROMOTE_THRESHOLD else "FAIL ✗"
    xgb_gate    = "PASS ✓" if xgb_mae   < _PROMOTE_THRESHOLD else "FAIL ✗"

    print("\n" + "=" * 72)
    print("run_env head-to-head: v1 Ridge | v3 Ridge | v3 XGBoost")
    print("=" * 72)
    print(f"  {'Metric':<30}  {'v1 Ridge':>10}  {'v3 Ridge':>10}  {'v3 XGBoost':>12}")
    print(f"  {'-'*30}  {'-'*10}  {'-'*10}  {'-'*12}")
    print(f"  {'CV MAE':<30}  {_V1_CV_MAE:>10.4f}  {ridge_mae:>10.4f}  {xgb_mae:>12.4f}")
    print(f"  {'Delta vs v1':<30}  {'—':>10}  {ridge_delta:>+10.4f}  {xgb_delta:>+12.4f}")
    gate_label = f"Gate (< {_PROMOTE_THRESHOLD})"
    print(f"  {gate_label:<30}  {'—':>10}  {ridge_gate:>10}  {xgb_gate:>12}")
    print("=" * 72)

    print("\n  Per-fold comparison (test year | Ridge MAE | XGB MAE | Ridge bias | XGB bias):")
    for rr, xr in zip(ridge_folds, xgb_folds):
        print(
            f"    {rr['test_season']}  Ridge={rr['mae']:.4f} ({rr['bias']:+.4f})  "
            f"XGB={xr['mae']:.4f} ({xr['bias']:+.4f})"
        )

    ridge_passes = ridge_mae < _PROMOTE_THRESHOLD
    xgb_passes   = xgb_mae   < _PROMOTE_THRESHOLD

    if not ridge_passes and not xgb_passes:
        print("\n  Neither variant beats the promotion gate. v1 Ridge stays champion.")
        return "none", min(ridge_mae, xgb_mae)
    elif ridge_passes and not xgb_passes:
        print(f"\n  Winner: v3 Ridge (MAE {ridge_mae:.4f})")
        return "ridge", ridge_mae
    elif xgb_passes and not ridge_passes:
        print(f"\n  Winner: v3 XGBoost (MAE {xgb_mae:.4f})")
        return "xgb", xgb_mae
    else:
        if ridge_mae <= xgb_mae:
            print(f"\n  Both pass gate — Winner: v3 Ridge (MAE {ridge_mae:.4f} ≤ XGB {xgb_mae:.4f})")
            return "ridge", ridge_mae
        else:
            print(f"\n  Both pass gate — Winner: v3 XGBoost (MAE {xgb_mae:.4f} < Ridge {ridge_mae:.4f})")
            return "xgb", xgb_mae


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def _update_registry(cv_mae: float, model_type: str, gate_passed: bool) -> None:
    text = _REGISTRY_PATH.read_text()

    # Set v1 promotion gate threshold if still null
    text = re.sub(
        r"(run_env_v1:.*?promotion_gate:.*?threshold:)\s*null",
        rf"\1 {_PROMOTE_THRESHOLD}",
        text, count=1, flags=re.DOTALL,
    )

    if gate_passed:
        # Deprecate v1 — v3 is the new champion
        text = re.sub(
            r"(run_env_v1:.*?promotion_status:)\s*\S+",
            r"\1 deprecated",
            text, count=1, flags=re.DOTALL,
        )

    v3_status    = "champion" if gate_passed else "deprecated"
    arch_label   = "Ridge" if model_type == "ridge" else "XGBoost"
    gate_note    = (
        f"Promoted to champion — {arch_label} CV MAE {cv_mae:.4f} < threshold {_PROMOTE_THRESHOLD}."
        if gate_passed
        else f"Deprecated — best CV MAE {cv_mae:.4f} did not beat threshold {_PROMOTE_THRESHOLD}."
    )

    if "run_env_v3:" not in text:
        v3_block = f"""
run_env_v3:
  artifact_path: models/sub_models/run_env_v3.pkl
  feature_columns_path: models/sub_models/run_env_v3_features.json
  target:
    source_table: baseball_data.betting.mart_game_results
    primary_column: home_final_score + away_final_score
    auxiliary_columns: []
    grain: game_pk
  training_window:
    start: '{_TRAINING_START}'
    end: null
  cv_strategy: walk_forward
  cv_metric: mae
  cv_score: {cv_mae}
  promotion_gate:
    metric: mae
    threshold: {_PROMOTE_THRESHOLD}
    direction: lower_is_better
  parent_features:
    - feature_pregame_park_features
    - feature_pregame_weather_features
    - feature_pregame_umpire_features
  output_signals:
    - run_env_signal
    - environment_volatility
  downstream_consumers: []
  promotion_status: {v3_status}
  promoted_at: null
  notes: |
    Story 3.5 (2026-05-19). Era features added to address systematic -0.556 run/game
    under-prediction bias confirmed in v1 and v2 (Story 3.4). Winning architecture: {arch_label}.
    Changes from v1: dropped ump_k_pct_zscore, ump_bb_pct_zscore (SHAP=0 in prior models).
    Added: is_universal_dh (2022+), is_pitch_clock_era (2023+), is_shift_ban_era (2023+),
    prior_season_lg_runs_per_game (prior season league avg, computed from training split,
    no leakage; fallback=mean of available seasons for rows mapping to pre-training years).
    Both Ridge and XGBoost evaluated on identical CV folds; {arch_label} selected as winner.
    {gate_note}
    Net features: 19 (was 17). Prior_season_runs dict stored in artifact for inference.
"""
        text = text.rstrip() + "\n" + v3_block

    _REGISTRY_PATH.write_text(text)
    v1_outcome = "deprecated" if gate_passed else "unchanged"
    print(f"\nRegistry updated: run_env_v3={v3_status}, run_env_v1={v1_outcome}")


# ---------------------------------------------------------------------------
# Training orchestration
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame, *, no_promote: bool = False, force_winner: str | None = None) -> None:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor

    print("\n" + "=" * 65)
    print("TRAINING run_env_v3 — Ridge vs XGBoost (era features)")
    print(f"Baseline to beat: run_env_v1 Ridge CV MAE = {_V1_CV_MAE}")
    print(f"Promotion gate:   CV MAE < {_PROMOTE_THRESHOLD} (delta > {_PROMOTION_GATE})")
    print("=" * 65)

    print(f"\nFeature set ({len(FEATURE_COLS_V3)} features):")
    for group, cols in [
        ("Park", _PARK_FEATURES),
        ("Weather", _WEATHER_FEATURES),
        ("Umpire (trimmed)", _UMPIRE_FEATURES),
        ("Era (new)", _ERA_FEATURES),
        ("Controls", _CONTROL_FEATURES),
    ]:
        print(f"  {group}: {cols}")

    # ------------------------------------------------------------------
    # 1. Ridge CV
    # ------------------------------------------------------------------
    print("\n[1/2] Running Ridge walk-forward CV...")
    ridge_alpha, ridge_mae, ridge_folds = _walk_forward_cv_ridge(df)
    _print_cv_table("Ridge v3", ridge_folds, f"alpha={ridge_alpha}")

    # ------------------------------------------------------------------
    # 2. XGBoost CV
    # ------------------------------------------------------------------
    print("\n[2/2] Running XGBoost walk-forward CV...")
    xgb_params, xgb_mae, xgb_folds = _walk_forward_cv_xgb(df)
    _print_cv_table("XGBoost v3", xgb_folds, str(xgb_params))

    # ------------------------------------------------------------------
    # 3. Comparison — determine winner
    # ------------------------------------------------------------------
    winner_type, winner_mae = _print_comparison(ridge_mae, xgb_mae, ridge_folds, xgb_folds)
    gate_passed = winner_type != "none"

    if force_winner is not None:
        winner_type = force_winner
        winner_mae  = ridge_mae if force_winner == "ridge" else xgb_mae
        gate_passed = True
        print(f"\n[--force-winner {force_winner}] Overriding MAE-based selection. gate_passed=True.")

    if no_promote:
        gate_passed = False
        if force_winner is None:
            winner_type = "ridge" if ridge_mae <= xgb_mae else "xgb"
            winner_mae  = min(ridge_mae, xgb_mae)
        print("\n[--no-promote] Registry update suppressed.")

    # ------------------------------------------------------------------
    # 4. Train final model (winning architecture) on all data
    # ------------------------------------------------------------------
    print(f"\nTraining final {winner_type.upper()} model on all {len(df):,} rows...")
    prior_season_runs_all = _compute_prior_season_runs(df)
    df_era   = _add_era_features(df, prior_season_runs_all)
    impute_vals = _compute_impute_values_v3(df_era)
    df_imp   = _apply_imputation_v3(df_era, impute_vals)
    X_all    = df_imp[FEATURE_COLS_V3].to_numpy(dtype=float)
    y_all    = df_imp["total_runs"].to_numpy(dtype=float)

    if winner_type == "ridge":
        pipeline = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=ridge_alpha))])
        pipeline.fit(X_all, y_all)
        y_pred_all = pipeline.predict(X_all)
        final_model = pipeline

        coef = pipeline.named_steps["ridge"].coef_
        print("\n── Ridge feature coefficients (sorted by |coef|) ───────────")
        for feat, c in sorted(zip(FEATURE_COLS_V3, coef), key=lambda x: abs(x[1]), reverse=True):
            print(f"  {feat:<40s}  {c:+.4f}")
    else:
        final_model = XGBRegressor(
            objective="reg:absoluteerror",
            tree_method="hist",
            random_state=42,
            verbosity=0,
            **xgb_params,
        )
        final_model.fit(X_all, y_all)
        y_pred_all = final_model.predict(X_all)
        _print_shap_importance(final_model, X_all)

    train_mae = float(np.mean(np.abs(y_pred_all - y_all)))
    print(f"\n  Training MAE (in-sample): {train_mae:.4f}")
    print(f"  Walk-forward CV MAE:      {winner_mae:.4f}")

    # ------------------------------------------------------------------
    # 5. Calibration
    # ------------------------------------------------------------------
    _print_calibration(df_imp, y_pred_all)

    # ------------------------------------------------------------------
    # 6. Save artifact
    # ------------------------------------------------------------------
    artifact = {
        "model":              final_model,
        "model_type":         winner_type,
        "feature_cols":       FEATURE_COLS_V3,
        "impute_values":      impute_vals,
        "prior_season_runs":  prior_season_runs_all,
        "target_mean":        float(y_all.mean()),
        "target_std":         float(y_all.std()),
        "cv_mae":             winner_mae,
        "ridge_cv_mae":       ridge_mae,
        "xgb_cv_mae":         xgb_mae,
        "ridge_best_alpha":   ridge_alpha,
        "xgb_best_params":    xgb_params,
        "cv_fold_records":    ridge_folds if winner_type == "ridge" else xgb_folds,
    }
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ARTIFACT_PATH, "wb") as fh:
        pickle.dump(artifact, fh)
    print(f"\nArtifact saved → {_ARTIFACT_PATH}")

    with open(_FEATURE_COLS_PATH, "w") as fh:
        json.dump(FEATURE_COLS_V3, fh, indent=2)
    print(f"Feature columns saved → {_FEATURE_COLS_PATH}")

    # ------------------------------------------------------------------
    # 7. Registry
    # ------------------------------------------------------------------
    if not no_promote:
        _update_registry(winner_mae, winner_type, gate_passed)

    # ------------------------------------------------------------------
    # 8. Next steps
    # ------------------------------------------------------------------
    print("\n" + "=" * 65)
    arch_label = "Ridge" if winner_type == "ridge" else "XGBoost"
    if gate_passed:
        if force_winner is not None:
            print(
                f"run_env_v3 result: PROMOTED via --force-winner {force_winner} "
                f"({arch_label}, CV MAE {winner_mae:.4f}; promoted on bias-correction grounds)"
            )
        else:
            print(f"run_env_v3 result: PROMOTED ({arch_label}, CV MAE {winner_mae:.4f} < {_PROMOTE_THRESHOLD})")
        print("\nNext (REQUIRED ORDER):")
        print("  1. Update generate_run_env_signals.py to load run_env_v3.pkl")
        print("     and compute era features from game_date + artifact prior_season_runs.")
        print("  2. Test in dev first:")
        print("       uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --env dev")
        print("  3. Verify dev row counts, then prod:")
        print("       uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --env prod")
        print("  4. dbtf build --select feature_pregame_sub_model_signals")
    else:
        print(f"run_env_v3 result: DEPRECATED (best CV MAE {winner_mae:.4f} ≥ {_PROMOTE_THRESHOLD})")
        print("v1 Ridge remains champion. Proceed to Story 3.Z ablation.")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train run_env_v3 sub-model — Ridge vs XGBoost with era features (Story 3.5)"
    )
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Compute and save artifact but skip registry update.",
    )
    parser.add_argument(
        "--force-winner",
        choices=["ridge", "xgb"],
        default=None,
        metavar="{ridge,xgb}",
        help=(
            "Override MAE-based winner selection and train the specified architecture. "
            "Use when promoting on a criterion other than CV MAE (e.g., bias correction). "
            "Implies gate_passed=True and triggers registry promotion."
        ),
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Bypass local Parquet cache and re-pull training data from Snowflake.",
    )
    args = parser.parse_args()

    print(f"Loading training data ({_TRAINING_START} → latest)...")
    df = get_cached_df(
        cache_key="run_env_training",
        pull_fn=load_training_data,
        max_age_hours=24,
        refresh=args.refresh_cache,
    )
    print(f"Loaded {len(df):,} rows across {df['game_year'].nunique()} seasons.")

    validate_no_leakage(df)
    train(df, no_promote=args.no_promote, force_winner=args.force_winner)


if __name__ == "__main__":
    main()
