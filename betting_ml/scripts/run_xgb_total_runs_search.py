"""Card 4.12a — Optuna TPE hyperparameter search for XGBoost on total_runs.

Runs 50 Optuna trials with the TPE sampler, persists the best XGBoost model,
and writes betting_ml/evaluation/tuning_results_xgb_total_runs.json.

Pass --report-only to skip the search and regenerate the markdown report +
project_context.md update from an existing tuning_results_xgb_total_runs.json.

Usage:
    uv run python betting_ml/scripts/run_xgb_total_runs_search.py
    uv run python betting_ml/scripts/run_xgb_total_runs_search.py --report-only

Exits non-zero if the tuned MAE regresses more than 1% vs. the baseline.
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

_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_xgb_total_runs.json"
_REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning_xgb_total_runs.md"
_CONTEXT_PATH = PROJECT_ROOT / "project_context.md"


def _load_baseline_mae() -> float:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT AVG(mae) FROM baseball_data.betting_ml.cv_results_tot_runs"
            " WHERE model = 'xgboost'"
        )
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


def _make_objective(folds: list[dict], df, target: str = "total_runs"):
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
            y_train = df.loc[fold["train_idx"], target]
            y_eval = df.loc[fold["eval_idx"], target]
            model = XGBRegressor(**params)
            model.fit(fold["X_train"], y_train)
            y_pred = model.predict(fold["X_eval"])
            maes.append(float(np.mean(np.abs(y_eval.values - y_pred))))
        return float(np.mean(maes))

    return objective


def run_search() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    print("Loading baseline XGBoost MAE for total_runs from Snowflake...")
    baseline_mae = _load_baseline_mae()
    print(f"Baseline XGBoost MAE (total_runs): {baseline_mae:.4f}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    missing = [f for f in retained if f not in df.columns]
    if missing:
        print(f"WARNING: {len(missing)} retained features absent from DataFrame (skipped): {missing[:5]}")
    print(f"Using {len(feature_cols)} features")

    print("Preparing imputed CV folds...")
    folds = _prepare_folds(df, feature_cols)
    print(f"Prepared {len(folds)} CV folds")

    last_fold = folds[-1]
    last_eval_year = last_fold["eval_year"]

    print("\nRunning Optuna TPE study — total_runs (50 trials)...")
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name="xgb_total_runs",
    )
    study.optimize(_make_objective(folds, df, "total_runs"), n_trials=50)
    print(f"Study complete. Best MAE: {study.best_value:.4f}  (baseline: {baseline_mae:.4f})")

    tuned_mae = study.best_value
    improved = tuned_mae <= baseline_mae

    # Persist best model — retrain on last-fold training split
    print("\nPersisting tuned model (retraining on last-fold training split)...")
    best_params = {**study.best_params, "random_state": 42, "n_jobs": -1}
    xgb_reg = XGBRegressor(**best_params)
    xgb_reg.fit(last_fold["X_train"], df.loc[last_fold["train_idx"], "total_runs"])
    model_path = save_model(
        xgb_reg,
        target="total_runs",
        model_name="xgb_tuned",
        eval_year=last_eval_year,
    )
    print(f"  total_runs/xgb_tuned → {model_path}")

    # Build results dict
    all_trials = [
        {"trial_number": t.number, "params": t.params, "value": t.value}
        for t in study.trials
        if t.value is not None
    ]

    results = {
        "target": "total_runs",
        "model": "xgboost",
        "n_trials": len(study.trials),
        "best_params": study.best_params,
        "best_cv_score": tuned_mae,
        "baseline_cv_score": baseline_mae,
        "metric": "mae",
        "improved": improved,
        "all_trials": all_trials,
        "persisted_models": [
            {
                "target": "total_runs",
                "model_name": "xgb_tuned",
                "eval_year": last_eval_year,
                "path": model_path,
            }
        ],
    }

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {_RESULTS_PATH}")

    print(f"\n=== Tuning Summary ===")
    improvement_pct = (baseline_mae - tuned_mae) / baseline_mae * 100
    flag = "IMPROVED ✓" if improved else "REGRESSED ✗"
    print(f"  Baseline MAE: {baseline_mae:.4f}")
    print(f"  Tuned MAE:    {tuned_mae:.4f}")
    print(f"  Change:       {improvement_pct:+.2f}%  {flag}")

    # Regression guard — exit non-zero if tuned MAE regresses > 1%
    if tuned_mae > baseline_mae * 1.01:
        print(
            f"\nFAILURE: Tuned XGBoost total_runs MAE regressed beyond 1% tolerance: "
            f"tuned={tuned_mae:.4f} > 1.01 × baseline={baseline_mae:.4f}"
        )
        sys.exit(1)

    print(
        "\nCard 4.12a search complete. "
        "Run with --report-only to generate the markdown report."
    )


def _build_report(results: dict) -> str:
    bp = results["best_params"]
    baseline = results["baseline_cv_score"]
    tuned = results["best_cv_score"]
    improvement_pct = (baseline - tuned) / baseline * 100
    n_trials = results["n_trials"]
    trials = results["all_trials"]
    persisted = results["persisted_models"]

    # Find trial where best value was first achieved
    best_val = results["best_cv_score"]
    best_trial_num = next(
        (t["trial_number"] for t in trials if t["value"] is not None and abs(t["value"] - best_val) < 1e-9),
        "N/A",
    )
    convergence_comment = (
        "Convergence was early (within first 10 trials), suggesting the TPE sampler "
        "quickly identified a promising region of the search space."
        if isinstance(best_trial_num, int) and best_trial_num < 10
        else "Convergence required extended search beyond the first 10 trials, indicating "
        "a more complex hyperparameter landscape for this target."
    )

    lines = [
        "# XGBoost total_runs Hyperparameter Tuning (Card 4.12a)",
        "",
        "## XGBoost total_runs Hyperparameter Search Results",
        "",
        "Optuna TPE sampler with 50 trials; baseline MAE sourced from Snowflake "
        "table `baseball_data.betting_ml.cv_results_tot_runs` (model='xgboost').",
        "",
        "| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |",
        "|--------|-------------------|----------------|-----------------|--------|",
        f"| MAE | {baseline:.4f} | {tuned:.4f} | {improvement_pct:+.2f}% | {n_trials} |",
        "",
        "**Best hyperparameters:**",
        "",
        f"- `max_depth`: {bp['max_depth']}",
        f"- `learning_rate`: {bp['learning_rate']:.6f}",
        f"- `n_estimators`: {bp['n_estimators']}",
        f"- `subsample`: {bp['subsample']:.4f}",
        f"- `colsample_bytree`: {bp['colsample_bytree']:.4f}",
        f"- `reg_alpha`: {bp['reg_alpha']:.4f}",
        f"- `reg_lambda`: {bp['reg_lambda']:.4f}",
        "",
        "## Optuna Trial Convergence",
        "",
        f"The best MAE of {best_val:.4f} was first achieved at trial number "
        f"{best_trial_num} (out of {n_trials} total trials).",
        "",
        convergence_comment,
        "",
        "## Best Hyperparameter Configuration",
        "",
        "```python",
        "best_params = {",
        f'    "max_depth": {bp["max_depth"]},',
        f'    "learning_rate": {bp["learning_rate"]:.6f},',
        f'    "n_estimators": {bp["n_estimators"]},',
        f'    "subsample": {bp["subsample"]:.4f},',
        f'    "colsample_bytree": {bp["colsample_bytree"]:.4f},',
        f'    "reg_alpha": {bp["reg_alpha"]:.4f},',
        f'    "reg_lambda": {bp["reg_lambda"]:.4f},',
        "}",
        "```",
        "",
        "## Persisted Model",
        "",
        "The tuned XGBoost model was retrained on the last CV fold's training split "
        "and persisted via `save_model()` from `betting_ml.utils.model_io`.",
        "",
        "| Target | Model Name | Eval Year | Path |",
        "|--------|------------|-----------|------|",
    ]

    for m in persisted:
        lines.append(f"| {m['target']} | {m['model_name']} | {m['eval_year']} | `{m['path']}` |")

    lines += [
        "",
        "Model saved successfully. ✓ (persisted)",
        "",
    ]

    return "\n".join(lines)


def generate_report() -> None:
    if not _RESULTS_PATH.exists():
        print(f"ERROR: {_RESULTS_PATH} not found. Run the search first.")
        sys.exit(1)

    with open(_RESULTS_PATH) as f:
        results = json.load(f)

    content = _build_report(results)
    with open(_REPORT_PATH, "w") as f:
        f.write(content)
    print(f"Wrote {_REPORT_PATH}")

    _update_project_context(results)


def _update_project_context(results: dict) -> None:
    improved = results["improved"]
    baseline = results["baseline_cv_score"]
    tuned = results["best_cv_score"]
    improvement_pct = (baseline - tuned) / baseline * 100
    bp = results["best_params"]

    section = f"""
#### Card 4.12a Results — XGBoost total_runs Hyperparameter Tuning (Optuna TPE)

- **xgb_total_runs_improved:** {improved}
- **Baseline MAE:** {baseline:.4f} | **Tuned MAE:** {tuned:.4f} | **Change:** {improvement_pct:+.2f}%
- **Best params:** max_depth={bp['max_depth']}, learning_rate={bp['learning_rate']:.4f}, n_estimators={bp['n_estimators']}, subsample={bp['subsample']:.3f}, colsample_bytree={bp['colsample_bytree']:.3f}, reg_alpha={bp['reg_alpha']:.3f}, reg_lambda={bp['reg_lambda']:.3f}
- **Summary:** Optuna tuned XGBoost for total_runs achieved MAE={tuned:.4f} vs. baseline={baseline:.4f}; tuned model persisted via model_io.py as `xgb_tuned`.
"""

    with open(_CONTEXT_PATH) as f:
        content = f.read()

    header = "#### Card 4.12a Results"
    if header in content:
        import re
        content = re.sub(
            r"#### Card 4\.12a Results.*?(?=####|\Z)",
            section.lstrip("\n") + "\n",
            content,
            flags=re.DOTALL,
        )
    elif "#### Card 4.12" in content:
        content = content.replace("#### Card 4.12", section + "\n#### Card 4.12", 1)
    elif "#### Card 4.9" in content:
        content = content.replace("#### Card 4.9", section + "\n#### Card 4.9", 1)
    else:
        content += section

    with open(_CONTEXT_PATH, "w") as f:
        f.write(content)
    print(f"Updated {_CONTEXT_PATH} with Card 4.12a results.")


if __name__ == "__main__":
    if "--report-only" in sys.argv:
        generate_report()
    else:
        run_search()
        generate_report()
