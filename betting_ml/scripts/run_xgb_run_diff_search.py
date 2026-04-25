"""Card 4.12b — XGBoost hyperparameter optimization for run_differential.

Runs an Optuna TPE search (50 trials) for XGBoost on the run_differential
target, persists the best model, and writes:
  betting_ml/evaluation/tuning_results_xgb_run_diff.json

Exits non-zero if tuned MAE regresses more than 1% vs. the Card 4.10 baseline.

Usage:
    uv run python betting_ml/scripts/run_xgb_run_diff_search.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import optuna
from xgboost import XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection, load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

optuna.logging.set_verbosity(optuna.logging.WARNING)

TARGET = "run_differential"
SNOWFLAKE_TABLE = "baseball_data.betting_ml.cv_results_run_diff"
N_TRIALS = 20
RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_xgb_run_diff.json"


def _load_baseline() -> float:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT AVG(mae) FROM {SNOWFLAKE_TABLE} WHERE model = 'xgboost'")
        return float(cur.fetchone()[0])
    finally:
        conn.close()


def _prepare_folds(df, feature_cols: list[str]) -> list[dict]:
    folds = []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        X_train_raw = df.loc[train_idx, feature_cols]
        X_eval_raw = df.loc[eval_idx, feature_cols]

        pipeline = build_imputation_pipeline()
        X_train_imp = pipeline.fit_transform(X_train_raw)
        X_eval_imp = pipeline.transform(X_eval_raw)

        X_train_imp = X_train_imp.select_dtypes(include=[np.number])
        X_eval_imp = X_eval_imp[[c for c in X_train_imp.columns if c in X_eval_imp.columns]]
        X_eval_imp = X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)

        folds.append({
            "train_idx": train_idx,
            "eval_idx": eval_idx,
            "eval_year": eval_year,
            "X_train": X_train_imp,
            "X_eval": X_eval_imp,
        })
    return folds


def _make_objective(folds: list[dict], df):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 2.0),
            "random_state": 42,
            "n_jobs": -1,
        }
        maes = []
        for fold in folds:
            y_train = df.loc[fold["train_idx"], TARGET]
            y_eval = df.loc[fold["eval_idx"], TARGET]
            model = XGBRegressor(**params)
            model.fit(fold["X_train"], y_train)
            y_pred = model.predict(fold["X_eval"])
            maes.append(float(np.mean(np.abs(y_eval.values - y_pred))))
        return float(np.mean(maes))

    return objective


def main() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    print(f"Loading baseline XGBoost CV score from {SNOWFLAKE_TABLE}...")
    baseline_mae = _load_baseline()
    print(f"Baseline XGBoost {TARGET} MAE: {baseline_mae:.4f}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    missing = [f for f in retained if f not in df.columns]
    if missing:
        print(f"WARNING: {len(missing)} retained features absent from DataFrame (skipped): {missing[:5]}")
    print(f"Using {len(feature_cols)} features")

    print("Preparing imputed CV folds...")
    folds = _prepare_folds(df, feature_cols)
    print(f"Prepared {len(folds)} CV folds")

    print(f"\nRunning Optuna TPE study — {TARGET} ({N_TRIALS} trials)...")
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name=f"xgb_{TARGET}",
    )
    study.optimize(_make_objective(folds, df), n_trials=N_TRIALS)
    tuned_mae = study.best_value
    print(f"  Best MAE: {tuned_mae:.4f}  (baseline: {baseline_mae:.4f})")

    last_fold = folds[-1]
    last_eval_year = last_fold["eval_year"]

    print(f"\nRetraining best model on last-fold training split (eval_year={last_eval_year})...")
    best_params = {**study.best_params, "random_state": 42, "n_jobs": -1}
    xgb_reg = XGBRegressor(**best_params)
    xgb_reg.fit(last_fold["X_train"], df.loc[last_fold["train_idx"], TARGET])
    model_path = save_model(
        xgb_reg,
        target=TARGET,
        model_name="xgb_tuned",
        eval_year=last_eval_year,
    )
    print(f"  Persisted → {model_path}")

    all_trials = [
        {"trial_number": t.number, "params": t.params, "value": t.value}
        for t in study.trials
        if t.value is not None
    ]

    result = {
        "target": TARGET,
        "model": "xgboost",
        "n_trials": len(study.trials),
        "best_params": study.best_params,
        "best_cv_score": tuned_mae,
        "baseline_cv_score": baseline_mae,
        "metric": "mae",
        "improved": tuned_mae <= baseline_mae,
        "all_trials": all_trials,
        "persisted_models": [
            {
                "target": TARGET,
                "model_name": "xgb_tuned",
                "eval_year": last_eval_year,
                "path": model_path,
            }
        ],
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nWrote {RESULTS_PATH}")

    improved_str = "IMPROVED ✓" if result["improved"] else "NO IMPROVEMENT ✗"
    print(f"\nSummary: tuned MAE={tuned_mae:.4f}  baseline MAE={baseline_mae:.4f}  → {improved_str}")

    if tuned_mae > baseline_mae * 1.01:
        print(
            f"\nFAILURE: XGBoost {TARGET} MAE regressed beyond 1% tolerance: "
            f"tuned={tuned_mae:.4f} > 1.01 × baseline={baseline_mae:.4f}"
        )
        sys.exit(1)

    print("\nCard 4.12b search complete. Run generate_xgb_run_diff_report.py to produce the markdown report.")


if __name__ == "__main__":
    main()
