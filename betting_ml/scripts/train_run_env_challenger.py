"""
train_run_env_challenger.py — Run Environment Challenger (Epic 3, Story 3.4)

Trains run_env_v2: an XGBoost model on the identical 17-feature matrix and
walk-forward CV folds used by run_env_v1 (Ridge, CV MAE = 3.5104).

Goals:
  1. Determine whether a tree model recovers non-linear interactions
     (elevation × temperature, dome × park factor) that Ridge cannot express.
  2. Audit umpire K/BB features (shrunk to ~0 under Ridge) for non-linear signal.
  3. Promote v2 to champion only if CV MAE improves by > 0.05 runs over v1.

Artifacts:
  run_env_v2.pkl              — XGBoost model + metadata
  run_env_v2_features.json    — feature column list (identical to v1)

Registry:
  run_env_v2 added as challenger (or champion if gate passes).
  run_env_v1 updated: promotion_gate.threshold set; deprecated if v2 wins.

Usage:
    uv run python betting_ml/scripts/train_run_env_challenger.py
    uv run python betting_ml/scripts/train_run_env_challenger.py --no-promote
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.train_run_env import (
    FEATURE_COLS,
    _TRAINING_START,
    _apply_imputation,
    _compute_impute_values,
    _build_Xy,
    load_training_data,
    validate_no_leakage,
    _print_calibration,
)

_V1_CV_MAE     = 3.5104
_PROMOTION_GATE = 0.05          # must beat v1 by > this many runs to promote
_PROMOTE_THRESHOLD = _V1_CV_MAE - _PROMOTION_GATE   # 3.4604

_REGISTRY_NAME_V1 = "run_env_v1"
_REGISTRY_NAME_V2 = "run_env_v2"
_ARTIFACT_PATH    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v2.pkl"
_FEATURE_COLS_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v2_features.json"

# ---------------------------------------------------------------------------
# Hyperparameter grid
# ---------------------------------------------------------------------------

_PARAM_GRID = {
    "n_estimators":     [200, 500],
    "max_depth":        [3, 5],
    "learning_rate":    [0.05, 0.1],
    "subsample":        [0.8],
    "colsample_bytree": [0.8],
    "min_child_weight": [3],
}


def _grid_combinations(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, vals)) for vals in product(*grid.values())]


# ---------------------------------------------------------------------------
# Walk-forward CV
# ---------------------------------------------------------------------------

def _walk_forward_cv(df: pd.DataFrame) -> tuple[dict, float, list[dict]]:
    """Walk-forward season CV with XGBoost hyperparameter grid search.

    For each season s: train on all prior seasons, test on s.
    Returns (best_params, best_mean_mae, fold_records_with_best_params).
    """
    import xgboost as xgb

    seasons = sorted(df["game_year"].unique())
    if len(seasons) < 2:
        raise ValueError(f"Need at least 2 seasons; got {seasons}")

    folds = [(seasons[:i], seasons[i]) for i in range(1, len(seasons))]
    combos = _grid_combinations(_PARAM_GRID)

    print(f"  Grid: {len(combos)} param combos × {len(folds)} folds = {len(combos)*len(folds)} fits")

    best_params: dict = {}
    best_mean_mae = float("inf")

    for params in combos:
        fold_maes = []
        for train_seasons, test_season in folds:
            train_df = df[df["game_year"].isin(train_seasons)]
            test_df  = df[df["game_year"] == test_season]

            impute_vals = _compute_impute_values(train_df)
            X_train, y_train = _build_Xy(train_df, impute_vals)
            X_test,  y_test  = _build_Xy(test_df,  impute_vals)

            model = xgb.XGBRegressor(
                **params,
                objective="reg:absoluteerror",
                tree_method="hist",
                random_state=42,
                verbosity=0,
            )
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            fold_maes.append(float(np.mean(np.abs(y_pred - y_test))))

        mean_mae = float(np.mean(fold_maes))
        if mean_mae < best_mean_mae:
            best_mean_mae = mean_mae
            best_params = params

    # Collect per-fold records with best params
    fold_records = []
    for train_seasons, test_season in folds:
        train_df = df[df["game_year"].isin(train_seasons)]
        test_df  = df[df["game_year"] == test_season]

        impute_vals = _compute_impute_values(train_df)
        X_train, y_train = _build_Xy(train_df, impute_vals)
        X_test,  y_test  = _build_Xy(test_df,  impute_vals)

        model = xgb.XGBRegressor(
            **best_params,
            objective="reg:absoluteerror",
            tree_method="hist",
            random_state=42,
            verbosity=0,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        mae  = float(np.mean(np.abs(y_pred - y_test)))
        bias = float(np.mean(y_pred - y_test))
        fold_records.append({
            "fold":          len(fold_records) + 1,
            "train_seasons": list(map(int, train_seasons)),
            "test_season":   int(test_season),
            "n_train":       int(len(y_train)),
            "n_test":        int(len(y_test)),
            "mae":           round(mae, 4),
            "bias":          round(bias, 4),
        })

    return best_params, round(best_mean_mae, 4), fold_records


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _print_cv_results(best_params: dict, fold_records: list[dict]) -> None:
    mean_mae  = float(np.mean([r["mae"]  for r in fold_records]))
    mean_bias = float(np.mean([r["bias"] for r in fold_records]))
    print("\n── Walk-forward CV results (XGBoost v2) ───────────────────")
    print(f"  Best params: {best_params}")
    print(f"  {'Fold':>4}  {'Train':>16}  {'Test':>6}  {'N_train':>7}  {'N_test':>6}  {'MAE':>6}  {'Bias':>7}")
    for r in fold_records:
        train_str = f"{r['train_seasons'][0]}–{r['train_seasons'][-1]}"
        print(
            f"  {r['fold']:>4}  {train_str:>16}  {r['test_season']:>6}  "
            f"{r['n_train']:>7}  {r['n_test']:>6}  {r['mae']:>6.3f}  {r['bias']:>+7.3f}"
        )
    print(f"  {'Mean':>4}  {'':>16}  {'':>6}  {'':>7}  {'':>6}  {mean_mae:>6.3f}  {mean_bias:>+7.3f}")


def _print_shap_importance(model, X_all: np.ndarray) -> dict[str, float]:
    """Compute and print mean |SHAP| importance; return as dict for artifact."""
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X_all)
        mean_abs = np.abs(shap_vals).mean(axis=0)
        importance = dict(zip(FEATURE_COLS, mean_abs.tolist()))

        print("\n── SHAP feature importance (mean |SHAP|) ───────────────────")
        for feat, imp in sorted(importance.items(), key=lambda x: -x[1]):
            bar = "█" * int(imp / max(importance.values()) * 20)
            print(f"  {feat:<35s}  {imp:.4f}  {bar}")
        return importance
    except Exception as exc:
        print(f"\n[WARN] SHAP computation failed: {exc}. Falling back to gain importance.")
        gain = model.get_booster().get_score(importance_type="gain")
        total = sum(gain.values()) or 1.0
        importance = {FEATURE_COLS[int(k[1:])]: v / total for k, v in gain.items()}
        return importance


def _print_comparison(v2_mae: float, fold_records: list[dict]) -> bool:
    """Print v1 vs v2 head-to-head table. Returns True if promotion gate passed."""
    delta    = v2_mae - _V1_CV_MAE
    gate_ok  = v2_mae < _PROMOTE_THRESHOLD

    print("\n" + "=" * 65)
    print("run_env v1 (Ridge) vs v2 (XGBoost) — head-to-head")
    print("=" * 65)
    print(f"  {'Metric':<30s}  {'v1 (Ridge)':>10}  {'v2 (XGB)':>10}  {'Delta':>8}")
    print(f"  {'-'*30}  {'-'*10}  {'-'*10}  {'-'*8}")
    print(f"  {'Walk-forward CV MAE':<30s}  {_V1_CV_MAE:>10.4f}  {v2_mae:>10.4f}  {delta:>+8.4f}")
    print(f"  {'Promotion threshold':<30s}  {'—':>10}  {_PROMOTE_THRESHOLD:>10.4f}  {'':>8}")
    print(f"  {'Gate (>0.05 improvement)':<30s}  {'—':>10}  {'PASS ✓' if gate_ok else 'FAIL ✗':>10}  {'':>8}")
    print("=" * 65)

    per_fold_delta = []
    v1_fold_maes = []
    print(f"\n  Per-fold breakdown (v2 only; v1 folds not stored individually):")
    for r in fold_records:
        print(f"    {r['test_season']}  MAE={r['mae']:.4f}  bias={r['bias']:+.4f}")
        per_fold_delta.append(r["mae"])

    return gate_ok


# ---------------------------------------------------------------------------
# Registry update
# ---------------------------------------------------------------------------

def _update_registry(cv_mae: float, gate_passed: bool) -> None:
    import re

    registry_path = _PROJECT_ROOT / "betting_ml" / "sub_model_registry.yaml"
    text = registry_path.read_text()

    # ── v1: set promotion_gate.threshold and optionally deprecate ──────────
    text = re.sub(
        r"(run_env_v1:.*?promotion_gate:.*?threshold:)\s*null",
        rf"\1 {_PROMOTE_THRESHOLD:.4f}",
        text, count=1, flags=re.DOTALL,
    )
    if gate_passed:
        text = re.sub(
            r"(run_env_v1:.*?promotion_status:)\s*\S+",
            r"\1 deprecated",
            text, count=1, flags=re.DOTALL,
        )

    # ── v2: append block if not already present ────────────────────────────
    if "run_env_v2:" not in text:
        v2_status = "champion" if gate_passed else "deprecated"
        v2_block = f"""
run_env_v2:
  artifact_path: models/sub_models/run_env_v2.pkl
  feature_columns_path: models/sub_models/run_env_v2_features.json
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
    threshold: {_PROMOTE_THRESHOLD:.4f}
    direction: lower_is_better
  parent_features:
    - feature_pregame_park_features
    - feature_pregame_weather_features
    - feature_pregame_umpire_features
  output_signals:
    - run_env_signal
    - environment_volatility
  downstream_consumers: []
  promotion_status: {v2_status}
  promoted_at: null
  notes: |
    XGBoost challenger to run_env_v1 (Ridge, CV MAE={_V1_CV_MAE}). Story 3.4.
    Same 17-feature matrix and walk-forward CV folds as v1.
    objective=reg:absoluteerror (directly optimizes MAE).
    Gate: CV MAE < {_PROMOTE_THRESHOLD:.4f} (v1 − 0.05 runs).
    {"Gate PASSED — promoted to champion; v1 deprecated." if gate_passed else f"Gate FAILED — v1 remains champion (Ridge CV MAE={_V1_CV_MAE})."}
"""
        text = text.rstrip() + "\n" + v2_block
    else:
        # Update existing v2 block
        text = re.sub(
            r"(run_env_v2:.*?cv_score:)\s*\S+",
            rf"\1 {cv_mae}",
            text, count=1, flags=re.DOTALL,
        )
        new_status = "champion" if gate_passed else "deprecated"
        text = re.sub(
            r"(run_env_v2:.*?promotion_status:)\s*\S+",
            rf"\1 {new_status}",
            text, count=1, flags=re.DOTALL,
        )

    registry_path.write_text(text)
    status_v2 = "champion" if gate_passed else "deprecated"
    status_v1 = "deprecated" if gate_passed else "challenger (champion)"
    print(f"\nRegistry updated: run_env_v2={status_v2}, run_env_v1={status_v1}")


# ---------------------------------------------------------------------------
# Main training routine
# ---------------------------------------------------------------------------

def train(df: pd.DataFrame, *, no_promote: bool = False) -> None:
    import pickle
    import xgboost as xgb

    print("\n" + "=" * 65)
    print("TRAINING run_env_v2 — XGBoost challenger")
    print(f"Baseline to beat: run_env_v1 Ridge CV MAE = {_V1_CV_MAE}")
    print(f"Promotion gate:   CV MAE < {_PROMOTE_THRESHOLD:.4f} (delta > 0.05)")
    print("=" * 65)

    # 1. Walk-forward CV with grid search
    print(f"\nRunning walk-forward CV...")
    best_params, mean_mae, fold_records = _walk_forward_cv(df)
    _print_cv_results(best_params, fold_records)

    # 2. Train final model on all data
    print(f"\nTraining final model on all {len(df):,} rows...")
    impute_vals = _compute_impute_values(df)
    X_all, y_all = _build_Xy(df, impute_vals)

    final_model = xgb.XGBRegressor(
        **best_params,
        objective="reg:absoluteerror",
        tree_method="hist",
        random_state=42,
        verbosity=0,
    )
    final_model.fit(X_all, y_all)
    y_pred_all = final_model.predict(X_all)
    train_mae  = float(np.mean(np.abs(y_pred_all - y_all)))
    print(f"  Training MAE (in-sample): {train_mae:.4f}")
    print(f"  Walk-forward CV MAE:      {mean_mae:.4f}")

    # 3. Calibration
    df_imp = _apply_imputation(df, impute_vals)
    _print_calibration(df_imp, y_pred_all)

    # 4. SHAP importance
    shap_importance = _print_shap_importance(final_model, X_all)

    # 5. Head-to-head comparison and gate decision
    gate_passed = _print_comparison(mean_mae, fold_records)
    if no_promote:
        print("\n[--no-promote] Skipping registry update and promotion logic.")
        gate_passed = False

    # 6. Save artifact
    artifact = {
        "model":           final_model,
        "feature_cols":    FEATURE_COLS,
        "impute_values":   impute_vals,
        "target_mean":     float(y_all.mean()),
        "target_std":      float(y_all.std()),
        "cv_mae":          mean_mae,
        "best_params":     best_params,
        "cv_fold_records": fold_records,
        "shap_importance": shap_importance,
    }
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_ARTIFACT_PATH, "wb") as fh:
        pickle.dump(artifact, fh)
    print(f"\nArtifact saved → {_ARTIFACT_PATH}")

    with open(_FEATURE_COLS_PATH, "w") as fh:
        json.dump(FEATURE_COLS, fh, indent=2)
    print(f"Feature columns saved → {_FEATURE_COLS_PATH}")

    # 7. Registry update (unless suppressed)
    if not no_promote:
        _update_registry(mean_mae, gate_passed)

    # 8. Summary
    print("\n" + "=" * 65)
    verdict = "CHAMPION (v1 deprecated)" if gate_passed else f"DEPRECATED (v1 Ridge remains champion at {_V1_CV_MAE})"
    print(f"run_env_v2 result: {verdict}")
    if gate_passed:
        print("Next (REQUIRED ORDER):")
        print("  1. Test signals in dev first:")
        print("       uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --env dev")
        print("  2. Verify dev row counts look right, then promote to prod:")
        print("       uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --env prod")
        print("  3. dbtf build --select feature_pregame_sub_model_signals")
    else:
        print("Next: Story 3.Z ablation test (Ridge v1 is champion).")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Train run_env_v2 XGBoost challenger (Story 3.4)")
    parser.add_argument(
        "--no-promote",
        action="store_true",
        help="Skip registry update and promotion logic (dry-run of training only).",
    )
    args = parser.parse_args()

    print(f"Loading training data from Snowflake ({_TRAINING_START} → latest)...")
    df = load_training_data()
    print(f"Loaded {len(df):,} rows across {df['game_year'].nunique()} seasons.")

    validate_no_leakage(df)
    train(df, no_promote=args.no_promote)


if __name__ == "__main__":
    main()
