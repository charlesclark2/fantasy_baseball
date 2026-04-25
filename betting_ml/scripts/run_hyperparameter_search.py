"""Card 4.12 — Hyperparameter optimization for XGBoost and NGBoost models.

Runs Optuna TPE search (50 trials each) for XGBoost on three targets and an
NGBoost grid search on regression targets, then persists five tuned models and
writes betting_ml/evaluation/tuning_results.json.

Usage:
    uv run python betting_ml/scripts/run_hyperparameter_search.py

Exits non-zero if any tuned XGBoost score regresses more than 1% vs. baseline.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import optuna
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier, XGBRegressor
from ngboost import NGBRegressor
from ngboost.distns import LogNormal, Normal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection, load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

optuna.logging.set_verbosity(optuna.logging.WARNING)


def _load_baseline_scores() -> dict:
    """Query Snowflake for baseline XGBoost CV scores from Cards 4.9–4.11."""
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT AVG(mae) FROM baseball_data.betting_ml.cv_results_tot_runs"
            " WHERE model = 'xgboost'"
        )
        total_runs = float(cur.fetchone()[0])

        cur.execute(
            "SELECT AVG(mae) FROM baseball_data.betting_ml.cv_results_run_diff"
            " WHERE model = 'xgboost'"
        )
        run_diff = float(cur.fetchone()[0])

        cur.execute(
            "SELECT AVG(brier_score) FROM baseball_data.betting_ml.cv_results_win_outcome"
            " WHERE model = 'xgb_platt'"
        )
        win_outcome = float(cur.fetchone()[0])

        return {
            "total_runs": total_runs,
            "run_differential": run_diff,
            "win_outcome": win_outcome,
        }
    finally:
        conn.close()


def _prepare_folds(df: pd.DataFrame, feature_cols: list[str]) -> list[dict]:
    """Build imputed CV folds once and cache them for reuse across Optuna trials."""
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


def _xgb_search_space(trial: optuna.Trial) -> dict:
    return {
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.5, 2.0),
    }


def _regression_objective(folds: list[dict], df: pd.DataFrame, target: str):
    def objective(trial: optuna.Trial) -> float:
        params = {**_xgb_search_space(trial), "random_state": 42, "n_jobs": -1}
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


def _classification_objective(folds: list[dict], df: pd.DataFrame):
    def objective(trial: optuna.Trial) -> float:
        params = {
            **_xgb_search_space(trial),
            "eval_metric": "logloss",
            "random_state": 42,
            "n_jobs": -1,
        }
        brier_scores = []
        for fold in folds:
            y_train = df.loc[fold["train_idx"], "home_win"].astype(int)
            y_eval = df.loc[fold["eval_idx"], "home_win"].astype(int)

            clf = XGBClassifier(**params)
            clf.fit(fold["X_train"], y_train)
            y_raw = clf.predict_proba(fold["X_eval"])[:, 1]

            # Platt calibration: fit logistic on raw scores vs. eval labels.
            # Equivalent to CalibratedClassifierCV(cv='prefit', method='sigmoid')
            # but compatible with sklearn 1.2+.
            calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
            calibrator.fit(y_raw.reshape(-1, 1), y_eval.values)
            y_cal = calibrator.predict_proba(y_raw.reshape(-1, 1))[:, 1]

            brier_scores.append(brier_score_loss(y_eval, y_cal))
        return float(np.mean(brier_scores))

    return objective


def _run_optuna_study(
    objective,
    study_name: str,
    n_trials: int = 50,
) -> optuna.Study:
    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=42),
        study_name=study_name,
    )
    study.optimize(objective, n_trials=n_trials)
    return study


def _study_to_result(study: optuna.Study, baseline: float, metric: str) -> dict:
    return {
        "n_trials": len(study.trials),
        "best_params": study.best_params,
        "best_cv_score": study.best_value,
        "baseline_cv_score": baseline,
        "metric": metric,
        "improved": study.best_value <= baseline,
        "all_trials": [
            {"trial_number": t.number, "params": t.params, "value": t.value}
            for t in study.trials
            if t.value is not None
        ],
    }


def _ngboost_grid(folds: list[dict], df: pd.DataFrame, target: str) -> list[dict]:
    """Run NGBoost grid search across n_estimators × dist combinations."""
    n_estimators_grid = [200, 500, 1000]
    dist_grid = ["Normal", "LogNormal"]
    results = []

    for n_est in n_estimators_grid:
        for dist_name in dist_grid:
            dist_class = Normal if dist_name == "Normal" else LogNormal
            maes: list[float] = []
            viable = True
            lognormal_note: str | None = None

            try:
                for fold in folds:
                    y_train = df.loc[fold["train_idx"], target]
                    y_eval = df.loc[fold["eval_idx"], target]

                    if dist_name == "LogNormal" and (y_train <= 0).any():
                        raise ValueError(
                            f"LogNormal requires strictly positive target values; "
                            f"'{target}' contains non-positive values "
                            f"(min={float(y_train.min()):.2f}). "
                            "run_differential can be negative — LogNormal not viable."
                        )

                    model = NGBRegressor(
                        Dist=dist_class,
                        n_estimators=n_est,
                        random_state=42,
                        verbose=False,
                    )
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        model.fit(fold["X_train"].values, y_train.values)

                    y_pred = model.predict(fold["X_eval"].values)

                    if np.any(np.isnan(y_pred)):
                        raise ValueError("NGBoost produced NaN predictions")

                    maes.append(float(np.mean(np.abs(y_eval.values - y_pred))))

            except Exception as exc:
                viable = False
                lognormal_note = str(exc)
                maes = []

            cv_mae = float(np.mean(maes)) if maes else None
            status = f"cv_mae={cv_mae:.4f}" if cv_mae is not None else f"FAILED: {lognormal_note}"
            print(f"    NGBoost {target} n_est={n_est} dist={dist_name}: {status}")

            results.append({
                "n_estimators": n_est,
                "dist": dist_name,
                "cv_mae": cv_mae,
                "viable": viable,
                "lognormal_note": lognormal_note,
            })

    return results


def _best_ngboost(grid_results: list[dict]) -> dict:
    viable = [r for r in grid_results if r["viable"] and r["cv_mae"] is not None]
    if not viable:
        raise RuntimeError("No viable NGBoost configuration found")
    return min(viable, key=lambda r: r["cv_mae"])


def main() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    print("Loading baseline CV scores from Snowflake...")
    baselines = _load_baseline_scores()
    print(
        f"Baselines — total_runs MAE={baselines['total_runs']:.4f}, "
        f"run_diff MAE={baselines['run_differential']:.4f}, "
        f"win_outcome Brier={baselines['win_outcome']:.4f}"
    )

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    missing = [f for f in retained if f not in df.columns]
    if missing:
        print(f"WARNING: {len(missing)} retained features absent from DataFrame (skipped): {missing[:5]}")
    print(f"Using {len(feature_cols)} features")

    print("Preparing imputed CV folds (this may take a few minutes)...")
    folds = _prepare_folds(df, feature_cols)
    print(f"Prepared {len(folds)} CV folds")

    last_fold = folds[-1]
    last_eval_year = last_fold["eval_year"]

    # ── XGBoost Optuna studies ────────────────────────────────────────────────

    print("\n[1/5] Optuna XGBoost study — total_runs (50 trials)...")
    study_tr = _run_optuna_study(
        _regression_objective(folds, df, "total_runs"),
        study_name="xgb_total_runs",
    )
    print(f"  Best MAE: {study_tr.best_value:.4f}  (baseline: {baselines['total_runs']:.4f})")
    xgb_total_runs = _study_to_result(study_tr, baselines["total_runs"], "mae")

    print("\n[2/5] Optuna XGBoost study — run_differential (50 trials)...")
    study_rd = _run_optuna_study(
        _regression_objective(folds, df, "run_differential"),
        study_name="xgb_run_differential",
    )
    print(f"  Best MAE: {study_rd.best_value:.4f}  (baseline: {baselines['run_differential']:.4f})")
    xgb_run_diff = _study_to_result(study_rd, baselines["run_differential"], "mae")

    print("\n[3/5] Optuna XGBoost study — win_outcome (50 trials)...")
    study_wo = _run_optuna_study(
        _classification_objective(folds, df),
        study_name="xgb_win_outcome",
    )
    print(f"  Best Brier: {study_wo.best_value:.4f}  (baseline: {baselines['win_outcome']:.4f})")
    xgb_win_outcome = _study_to_result(study_wo, baselines["win_outcome"], "brier_score")

    xgboost_tuning = {
        "total_runs": xgb_total_runs,
        "run_differential": xgb_run_diff,
        "win_outcome": xgb_win_outcome,
    }

    # ── NGBoost grid search ───────────────────────────────────────────────────

    print("\n[4/5] NGBoost grid search — total_runs...")
    tr_grid = _ngboost_grid(folds, df, "total_runs")
    best_tr_ngb = _best_ngboost(tr_grid)
    ngb_total_runs = {
        "grid_results": tr_grid,
        "best_n_estimators": best_tr_ngb["n_estimators"],
        "best_dist": best_tr_ngb["dist"],
        "best_cv_mae": best_tr_ngb["cv_mae"],
    }

    print("\n[5/5] NGBoost grid search — run_differential...")
    rd_grid = _ngboost_grid(folds, df, "run_differential")
    best_rd_ngb = _best_ngboost(rd_grid)
    ln_note_rd = next(
        (r["lognormal_note"] for r in rd_grid if r["dist"] == "LogNormal" and not r["viable"]),
        None,
    )
    ngb_run_diff = {
        "grid_results": rd_grid,
        "best_n_estimators": best_rd_ngb["n_estimators"],
        "best_dist": best_rd_ngb["dist"],
        "best_cv_mae": best_rd_ngb["cv_mae"],
        "lognormal_viable": any(r["dist"] == "LogNormal" and r["viable"] for r in rd_grid),
        "lognormal_note": ln_note_rd,
    }

    ngboost_tuning = {
        "total_runs": ngb_total_runs,
        "run_differential": ngb_run_diff,
    }

    # ── Persist tuned models ─────────────────────────────────────────────────

    print("\nPersisting tuned models (retraining on last-fold training split)...")
    persisted: list[dict] = []

    # XGBoost tuned — total_runs
    xgb_params_tr = {**study_tr.best_params, "random_state": 42, "n_jobs": -1}
    xgb_reg_tr = XGBRegressor(**xgb_params_tr)
    xgb_reg_tr.fit(last_fold["X_train"], df.loc[last_fold["train_idx"], "total_runs"])
    p = save_model(xgb_reg_tr, target="total_runs", model_name="xgb_tuned", eval_year=last_eval_year)
    persisted.append({"target": "total_runs", "model_name": "xgb_tuned", "eval_year": last_eval_year, "path": p})
    print(f"  total_runs/xgb_tuned → {p}")

    # XGBoost tuned — run_differential
    xgb_params_rd = {**study_rd.best_params, "random_state": 42, "n_jobs": -1}
    xgb_reg_rd = XGBRegressor(**xgb_params_rd)
    xgb_reg_rd.fit(last_fold["X_train"], df.loc[last_fold["train_idx"], "run_differential"])
    p = save_model(xgb_reg_rd, target="run_differential", model_name="xgb_tuned", eval_year=last_eval_year)
    persisted.append({"target": "run_differential", "model_name": "xgb_tuned", "eval_year": last_eval_year, "path": p})
    print(f"  run_differential/xgb_tuned → {p}")

    # XGBoost tuned — home_win (with Platt calibration)
    xgb_params_wo = {**study_wo.best_params, "eval_metric": "logloss", "random_state": 42, "n_jobs": -1}
    xgb_clf = XGBClassifier(**xgb_params_wo)
    y_train_wo = df.loc[last_fold["train_idx"], "home_win"].astype(int)
    y_eval_wo = df.loc[last_fold["eval_idx"], "home_win"].astype(int)
    xgb_clf.fit(last_fold["X_train"], y_train_wo)
    y_raw_wo = xgb_clf.predict_proba(last_fold["X_eval"])[:, 1]
    platt_wo = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    platt_wo.fit(y_raw_wo.reshape(-1, 1), y_eval_wo.values)
    # Bundle classifier + calibrator as a tuple for downstream scoring
    p = save_model(
        {"classifier": xgb_clf, "calibrator": platt_wo},
        target="home_win",
        model_name="xgb_classifier_tuned",
        eval_year=last_eval_year,
    )
    persisted.append({"target": "home_win", "model_name": "xgb_classifier_tuned", "eval_year": last_eval_year, "path": p})
    print(f"  home_win/xgb_classifier_tuned → {p}")

    # NGBoost tuned — total_runs
    ngb_dist_tr = Normal if best_tr_ngb["dist"] == "Normal" else LogNormal
    ngb_tr = NGBRegressor(
        Dist=ngb_dist_tr,
        n_estimators=best_tr_ngb["n_estimators"],
        random_state=42,
        verbose=False,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ngb_tr.fit(
            last_fold["X_train"].values,
            df.loc[last_fold["train_idx"], "total_runs"].values,
        )
    p = save_model(ngb_tr, target="total_runs", model_name="ngboost_tuned", eval_year=last_eval_year)
    persisted.append({"target": "total_runs", "model_name": "ngboost_tuned", "eval_year": last_eval_year, "path": p})
    print(f"  total_runs/ngboost_tuned → {p}")

    # NGBoost tuned — run_differential
    ngb_dist_rd = Normal if best_rd_ngb["dist"] == "Normal" else LogNormal
    ngb_rd = NGBRegressor(
        Dist=ngb_dist_rd,
        n_estimators=best_rd_ngb["n_estimators"],
        random_state=42,
        verbose=False,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ngb_rd.fit(
            last_fold["X_train"].values,
            df.loc[last_fold["train_idx"], "run_differential"].values,
        )
    p = save_model(ngb_rd, target="run_differential", model_name="ngboost_tuned", eval_year=last_eval_year)
    persisted.append({"target": "run_differential", "model_name": "ngboost_tuned", "eval_year": last_eval_year, "path": p})
    print(f"  run_differential/ngboost_tuned → {p}")

    # ── Summary table ─────────────────────────────────────────────────────────

    print("\n=== Tuning Summary ===")
    print(f"{'Target':<22} {'Metric':<12} {'Baseline':>10} {'Tuned':>10} {'Improved'}")
    print("-" * 62)
    for target, key, metric_label in [
        ("total_runs", "total_runs", "MAE"),
        ("run_differential", "run_differential", "MAE"),
        ("win_outcome", "win_outcome", "Brier"),
    ]:
        r = xgboost_tuning[key]
        flag = "YES ✓" if r["improved"] else "NO ✗"
        print(
            f"{target:<22} {metric_label:<12} "
            f"{r['baseline_cv_score']:>10.4f} {r['best_cv_score']:>10.4f} {flag}"
        )

    # ── Write tuning_results.json ─────────────────────────────────────────────

    summary = {
        "xgb_total_runs_improved": xgb_total_runs["improved"],
        "xgb_run_diff_improved": xgb_run_diff["improved"],
        "xgb_win_outcome_improved": xgb_win_outcome["improved"],
        "best_ngboost_config_total_runs": {
            "n_estimators": best_tr_ngb["n_estimators"],
            "dist": best_tr_ngb["dist"],
        },
        "best_ngboost_config_run_diff": {
            "n_estimators": best_rd_ngb["n_estimators"],
            "dist": best_rd_ngb["dist"],
        },
    }

    tuning_results = {
        "xgboost_tuning": xgboost_tuning,
        "ngboost_tuning": ngboost_tuning,
        "persisted_models": persisted,
        "summary": summary,
    }

    eval_dir = PROJECT_ROOT / "betting_ml" / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    results_path = eval_dir / "tuning_results.json"
    with open(results_path, "w") as f:
        json.dump(tuning_results, f, indent=2, default=lambda x: None if x != x else x)
    print(f"\nWrote {results_path}")

    # ── Regression guard ──────────────────────────────────────────────────────

    failures: list[str] = []
    tr_base, tr_tuned = baselines["total_runs"], xgb_total_runs["best_cv_score"]
    if tr_tuned > tr_base * 1.01:
        failures.append(
            f"XGBoost total_runs MAE regressed: tuned={tr_tuned:.4f} > 1.01 × baseline={tr_base:.4f}"
        )
    rd_base, rd_tuned = baselines["run_differential"], xgb_run_diff["best_cv_score"]
    if rd_tuned > rd_base * 1.01:
        failures.append(
            f"XGBoost run_differential MAE regressed: tuned={rd_tuned:.4f} > 1.01 × baseline={rd_base:.4f}"
        )
    wo_base, wo_tuned = baselines["win_outcome"], xgb_win_outcome["best_cv_score"]
    if wo_tuned > wo_base * 1.01:
        failures.append(
            f"XGBoost win_outcome Brier regressed: tuned={wo_tuned:.4f} > 1.01 × baseline={wo_base:.4f}"
        )

    if failures:
        print("\nFAILURE: Tuned model(s) regressed beyond 1% tolerance:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)

    print("\nCard 4.12 hyperparameter search complete. Run generate_tuning_report.py to produce the markdown report.")


if __name__ == "__main__":
    main()
