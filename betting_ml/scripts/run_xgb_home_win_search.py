"""XGBoost home_win — Optuna TPE hyperparameter search (Platt calibration).

Runs 50 Optuna trials with the TPE sampler, persists the best Platt-calibrated
XGBoost classifier, and writes:
  betting_ml/evaluation/tuning_results_xgb_home_win.json

Pass --report-only to skip the search and regenerate the markdown report +
project_context.md update from an existing tuning_results_xgb_home_win.json.

Usage:
    uv run python betting_ml/scripts/run_xgb_home_win_search.py
    uv run python betting_ml/scripts/run_xgb_home_win_search.py --report-only

Exits non-zero if the tuned Brier score regresses more than 1% vs. the baseline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import optuna
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection, load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

optuna.logging.set_verbosity(optuna.logging.WARNING)

TARGET = "home_win"
N_TRIALS = 50
_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_xgb_home_win.json"
_REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning_xgb_home_win.md"
_CONTEXT_PATH = PROJECT_ROOT / "project_context.md"


class PlattCalibratedXGBClassifier:
    """XGBClassifier with a fitted Platt (sigmoid) calibrator.

    Wraps the base classifier and calibrator so downstream code can call
    predict_proba() to obtain calibrated win probabilities.
    """

    def __init__(self, xgb_classifier: XGBClassifier, calibrator: LogisticRegression) -> None:
        self.xgb_classifier = xgb_classifier
        self.calibrator = calibrator

    def predict_proba(self, X) -> np.ndarray:
        raw = self.xgb_classifier.predict_proba(X)[:, 1]
        return self.calibrator.predict_proba(raw.reshape(-1, 1))


def _load_baseline_brier() -> float:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT AVG(brier_score) FROM baseball_data.betting_ml.cv_results_win_outcome"
            " WHERE model = 'xgb_platt'"
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


def _make_objective(folds: list[dict], df):
    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 400),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 2.0),
            "eval_metric": "logloss",
            "tree_method": "hist",
            "random_state": 42,
            "n_jobs": -1,
        }
        briers = []
        for fold in folds:
            y_train = df.loc[fold["train_idx"], TARGET].astype(int)
            y_eval = df.loc[fold["eval_idx"], TARGET].astype(int)

            xgb_clf = XGBClassifier(**params)
            xgb_clf.fit(fold["X_train"], y_train)

            y_raw = xgb_clf.predict_proba(fold["X_eval"])[:, 1]
            calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
            calibrator.fit(y_raw.reshape(-1, 1), np.asarray(y_eval))
            y_cal = calibrator.predict_proba(y_raw.reshape(-1, 1))[:, 1]

            briers.append(float(brier_score_loss(y_eval, y_cal)))
        return float(np.mean(briers))

    return objective


def run_search() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    print("Loading baseline XGBoost Platt Brier score for home_win from Snowflake...")
    baseline_brier = _load_baseline_brier()
    print(f"Baseline XGBoost Platt Brier (home_win): {baseline_brier:.4f}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    missing = [f for f in retained if f not in df.columns]
    if missing:
        print(
            f"WARNING: {len(missing)} retained features absent from DataFrame "
            f"(skipped): {missing[:5]}"
        )
    print(f"Using {len(feature_cols)} features")

    print("Preparing imputed CV folds...")
    folds = _prepare_folds(df, feature_cols)
    print(f"Prepared {len(folds)} CV folds")

    last_fold = folds[-1]
    last_eval_year = last_fold["eval_year"]

    print(f"\nRunning Optuna TPE study — {TARGET} ({N_TRIALS} trials)...")
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name=f"xgb_{TARGET}",
    )
    study.optimize(_make_objective(folds, df), n_trials=N_TRIALS)
    tuned_brier = study.best_value
    print(f"Study complete. Best Brier: {tuned_brier:.4f}  (baseline: {baseline_brier:.4f})")

    improved = tuned_brier <= baseline_brier

    # Persist best model — retrain on last-fold training split, calibrate on last-fold eval split
    print("\nPersisting tuned model (retraining on last-fold split)...")
    best_params = {
        **study.best_params,
        "eval_metric": "logloss",
        "tree_method": "hist",
        "random_state": 42,
        "n_jobs": -1,
    }
    y_train_last = df.loc[last_fold["train_idx"], TARGET].astype(int)
    y_eval_last = df.loc[last_fold["eval_idx"], TARGET].astype(int)

    xgb_clf = XGBClassifier(**best_params)
    xgb_clf.fit(last_fold["X_train"], y_train_last)

    y_raw_last = xgb_clf.predict_proba(last_fold["X_eval"])[:, 1]
    calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    calibrator.fit(y_raw_last.reshape(-1, 1), np.asarray(y_eval_last))

    xgb_clf_calibrated = PlattCalibratedXGBClassifier(xgb_clf, calibrator)
    model_path = save_model(
        xgb_clf_calibrated,
        target=TARGET,
        model_name="xgb_classifier_tuned",
        eval_year=last_eval_year,
    )
    print(f"  home_win/xgb_classifier_tuned → {model_path}")

    all_trials = [
        {"trial_number": t.number, "params": t.params, "value": t.value}
        for t in study.trials
        if t.value is not None
    ]

    results = {
        "target": TARGET,
        "model": "xgboost",
        "n_trials": len(study.trials),
        "best_params": study.best_params,
        "best_cv_score": tuned_brier,
        "baseline_cv_score": baseline_brier,
        "metric": "brier_score",
        "improved": improved,
        "all_trials": all_trials,
        "persisted_models": [
            {
                "target": TARGET,
                "model_name": "xgb_classifier_tuned",
                "eval_year": last_eval_year,
                "path": model_path,
            }
        ],
    }

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {_RESULTS_PATH}")

    improvement_pct = (baseline_brier - tuned_brier) / baseline_brier * 100
    flag = "IMPROVED ✓" if improved else "REGRESSED ✗"
    print(f"\n=== Tuning Summary ===")
    print(f"  Baseline Brier: {baseline_brier:.4f}")
    print(f"  Tuned Brier:    {tuned_brier:.4f}")
    print(f"  Change:         {improvement_pct:+.2f}%  {flag}")

    if tuned_brier > baseline_brier * 1.01:
        print(
            f"\nFAILURE: Tuned XGBoost home_win Brier regressed beyond 1% tolerance: "
            f"tuned={tuned_brier:.4f} > 1.01 × baseline={baseline_brier:.4f}"
        )
        sys.exit(1)

    print(
        "\nXGBoost home_win search complete. "
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

    best_val = results["best_cv_score"]
    best_trial_num = next(
        (t["trial_number"] for t in trials if t["value"] is not None and abs(t["value"] - best_val) < 1e-9),
        "N/A",
    )
    if isinstance(best_trial_num, int) and best_trial_num < 10:
        convergence_comment = (
            "Convergence was early (within first 10 trials), suggesting the TPE sampler "
            "quickly identified a promising region of the search space."
        )
    else:
        convergence_comment = (
            "Convergence required extended search beyond the first 10 trials, indicating "
            "a more complex hyperparameter landscape for this target."
        )

    improved_marker = " ✓" if results["improved"] else " ✗"

    lines = [
        "# XGBoost home_win Hyperparameter Tuning (Optuna TPE)",
        "",
        "Optuna TPE sampler (seed=42), direction=minimize, n_trials=50.",
        "Platt calibration (sigmoid) applied within each CV fold via LogisticRegression.",
        "",
        "## XGBoost home_win Hyperparameter Search Results",
        "",
        "Note that scores are Brier scores (lower is better).",
        "",
        "| Metric | Baseline CV Score | Tuned CV Score | Improvement (%) | Trials |",
        "|--------|-------------------|----------------|-----------------|--------|",
        f"| Brier Score | {baseline:.4f} | {tuned:.4f} | {improvement_pct:+.2f}%{improved_marker} | {n_trials} |",
        "",
        "Baseline sourced from Snowflake table "
        "`baseball_data.betting_ml.cv_results_win_outcome` (model='xgb_platt').",
        "",
        "**Best hyperparameter values:**",
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
        f"The best Brier score of {best_val:.4f} was first achieved at trial number "
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
        "The tuned Platt-calibrated XGBoost classifier was retrained on the last CV "
        "fold's training split (Platt calibrator fitted on eval split) and persisted "
        "via `save_model()` from `betting_ml.utils.model_io`. The persisted object is "
        "a `PlattCalibratedXGBClassifier` wrapper containing the XGBClassifier and "
        "the fitted Platt (sigmoid) calibrator (LogisticRegression).",
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
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
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
    improved_str = "improved ✓" if improved else "did not improve ✗"

    section = f"""
#### XGBoost home_win — Hyperparameter Tuning Results (Optuna TPE)

- **xgb_win_outcome_improved:** {improved} — XGBoost home_win Brier {improved_str} (tuned={tuned:.4f} vs baseline={baseline:.4f})
- **Baseline Brier:** {baseline:.4f} | **Tuned Brier:** {tuned:.4f} | **Change:** {improvement_pct:+.2f}%
- **Best params:** max_depth={bp['max_depth']}, learning_rate={bp['learning_rate']:.4f}, n_estimators={bp['n_estimators']}, subsample={bp['subsample']:.3f}, colsample_bytree={bp['colsample_bytree']:.3f}, reg_alpha={bp['reg_alpha']:.3f}, reg_lambda={bp['reg_lambda']:.3f}
- **Summary:** Optuna TPE (50 trials) tuned XGBoost (Platt) for home_win; tuned Brier={tuned:.4f} vs baseline={baseline:.4f} — {improved_str}; tuned model persisted via model_io.py as `xgb_classifier_tuned`.
- **Full results:** `betting_ml/evaluation/hyperparameter_tuning_xgb_home_win.md`, `betting_ml/evaluation/tuning_results_xgb_home_win.json`
"""

    with open(_CONTEXT_PATH) as f:
        content = f.read()

    import re
    if re.search(r"#### XGBoost home_win — Hyperparameter Tuning Results", content):
        content = re.sub(
            r"#### XGBoost home_win — Hyperparameter Tuning Results.*?(?=\n####|\Z)",
            section.lstrip("\n"),
            content,
            flags=re.DOTALL,
        )
    else:
        content += section

    with open(_CONTEXT_PATH, "w") as f:
        f.write(content)
    print(f"Updated {_CONTEXT_PATH} with XGBoost home_win tuning results.")


if __name__ == "__main__":
    if "--report-only" in sys.argv:
        generate_report()
    else:
        run_search()
        generate_report()
