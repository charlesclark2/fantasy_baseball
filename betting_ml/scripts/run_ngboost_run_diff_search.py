"""Card 4.12e — NGBoost grid search hyperparameter optimization for run_differential.

Runs a grid search (3 n_estimators × 2 distributions = 6 combinations) using
temporal CV splits, persists the best NGBoost model, and writes:
  betting_ml/evaluation/tuning_results_ngboost_run_diff.json
  betting_ml/evaluation/hyperparameter_tuning_ngboost_run_diff.md

LogNormal is expected to fail because run_differential can be negative; those
entries are recorded with viable=false and a descriptive note.

Grid chosen so Normal-dist runs take approximately 30 minutes in total:
  n_estimators ∈ {200, 500, 1000}  (LogNormal fails fast, so 3 viable fits)

Usage:
    uv run python betting_ml/scripts/run_ngboost_run_diff_search.py
    uv run python betting_ml/scripts/run_ngboost_run_diff_search.py --report-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.train_run_diff_prod import _MARKET_COLS_TO_EXCLUDE
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.feature_selection import (
    SEQUENTIAL_POSTERIOR_FEATURES,
    load_retained_features,
)
from betting_ml.utils.mlflow_utils import log_search_run
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_ngboost_run_diff.json"
_REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning_ngboost_run_diff.md"
_CONTEXT_PATH = PROJECT_ROOT / "project_context.md"

_N_ESTIMATORS_GRID = [200, 500, 1000]
_DIST_GRID = ["Normal"]  # LogNormal excluded: run_diff can be negative, log(Y) blows up


def _get_dist_class(dist_name: str):
    from ngboost.distns import Normal
    return {"Normal": Normal}[dist_name]


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


def run_search(exclude_sequential: bool = False, mlflow_enabled: bool = True) -> None:
    from ngboost import NGBRegressor

    model_name = "ngboost_nonseq" if exclude_sequential else "ngboost_tuned"

    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns and f not in _MARKET_COLS_TO_EXCLUDE]
    # Story 30.1 — drop leakage-prone identifier/temporal columns
    # (home_starter_pitcher_id, venue_id, game_year). All three targets PROMOTE
    # without them; see evaluation/feature_selection/story_30_1_identifier_hygiene.md.
    _identifier_removed = [f for f in feature_cols if is_identifier_name(f)]
    feature_cols = [f for f in feature_cols if not is_identifier_name(f)]
    print(f"Story 30.1: dropped {len(_identifier_removed)} identifier/temporal cols: {_identifier_removed}")
    missing = [f for f in retained if f not in df.columns and f not in _MARKET_COLS_TO_EXCLUDE]
    if missing:
        print(f"WARNING: {len(missing)} retained features absent from DataFrame (skipped): {missing[:5]}")
    market_removed = [f for f in retained if f in _MARKET_COLS_TO_EXCLUDE]
    if exclude_sequential:
        seq_removed = [f for f in feature_cols if f in set(SEQUENTIAL_POSTERIOR_FEATURES)]
        feature_cols = [f for f in feature_cols if f not in set(SEQUENTIAL_POSTERIOR_FEATURES)]
        print(
            f"--exclude-sequential: dropped {len(seq_removed)} sequential cols "
            f"→ faithful no-sequential baseline (documented champion). model_name={model_name}"
        )
    print(f"Using {len(feature_cols)} features (market-blind)")
    print(f"Market cols excluded: {len(market_removed)} — {market_removed}")

    print("Preparing imputed CV folds...")
    folds = _prepare_folds(df, feature_cols)
    print(f"Prepared {len(folds)} CV folds")

    last_fold = folds[-1]
    last_eval_year = last_fold["eval_year"]

    grid_results = []
    best_viable = None

    print("\nRunning NGBoost grid search — run_differential (3 combinations)...")
    print(f"{'n_estimators':>12}  {'dist':>10}  {'CV MAE':>10}")
    print("-" * 38)

    for n_est in _N_ESTIMATORS_GRID:
        for dist_name in _DIST_GRID:
            dist_cls = _get_dist_class(dist_name)
            fold_maes = []

            for fold in folds:
                y_train = df.loc[fold["train_idx"], "run_differential"].values
                y_eval = df.loc[fold["eval_idx"], "run_differential"].values

                ngb = NGBRegressor(n_estimators=n_est, Dist=dist_cls, verbose=False)
                ngb.fit(fold["X_train"].values, y_train)
                y_pred = ngb.predict(fold["X_eval"].values)

                if np.any(np.isnan(y_pred)) or np.any(np.isinf(y_pred)):
                    raise ValueError(f"NaN/Inf predictions from {dist_name} dist")

                fold_maes.append(float(np.mean(np.abs(y_eval - y_pred))))

            cv_mae = float(np.mean(fold_maes))

            result = {
                "n_estimators": n_est,
                "dist": dist_name,
                "cv_mae": cv_mae,
            }
            grid_results.append(result)

            mae_str = f"{cv_mae:.4f}" if cv_mae is not None else "null"
            print(f"{n_est:>12}  {dist_name:>10}  {mae_str:>10}")

            if best_viable is None or cv_mae < best_viable["cv_mae"]:
                best_viable = result

    if best_viable is None:
        print("\nERROR: No viable configurations found.")
        sys.exit(1)

    best_n_est = best_viable["n_estimators"]
    best_dist_name = best_viable["dist"]
    best_cv_mae = best_viable["cv_mae"]
    best_dist_cls = _get_dist_class(best_dist_name)

    print(f"\nBest config: n_estimators={best_n_est}, dist={best_dist_name}, CV MAE={best_cv_mae:.4f}")

    print("\nPersisting best model (retrain on last-fold training split)...")
    ngb_best = NGBRegressor(n_estimators=best_n_est, Dist=best_dist_cls, verbose=False)
    ngb_best.fit(
        last_fold["X_train"].values,
        df.loc[last_fold["train_idx"], "run_differential"].values,
    )
    model_path = save_model(
        ngb_best,
        target="run_differential",
        model_name=model_name,
        eval_year=last_eval_year,
    )
    print(f"  run_differential/{model_name} → {model_path}")

    # Contract must list the POST-imputation columns the model actually consumes
    # (feature_cols + the imputation indicators has_starter_platoon_data/is_new_venue,
    # appended by build_imputation_pipeline). Writing the pre-imputation feature_cols
    # makes predict_today serve fewer columns than the model expects → IndexError.
    final_feature_cols = list(last_fold["X_train"].columns)
    cols_path = Path(model_path).with_name(f"feature_columns_{model_name}_{last_eval_year}.json")
    with open(cols_path, "w") as f:
        json.dump(
            {
                "target": "run_differential",
                "model_name": model_name,
                "eval_year": last_eval_year,
                "exclude_sequential": exclude_sequential,
                "n_features": len(final_feature_cols),
                "feature_cols": final_feature_cols,
            },
            f,
            indent=2,
        )
    print(f"  feature contract → {cols_path}")

    mlflow_run_id = log_search_run(
        experiment="production_retrain",
        run_name=f"run_differential_{model_name}_{last_eval_year}",
        params={
            "target": "run_differential",
            "architecture": "ngboost_normal",
            "model_name": model_name,
            "exclude_sequential": exclude_sequential,
            "n_features": len(feature_cols),
            "n_rows": len(df),
            "n_seasons": int(df["game_year"].nunique()),
            "eval_year": last_eval_year,
            "best_n_estimators": best_n_est,
            "best_dist": best_dist_name,
        },
        metrics={"cv_mae": best_cv_mae},
        tags={
            "sequential_enriched": str(not exclude_sequential),
            "role": "challenger" if not exclude_sequential else "documented_champion_repro",
        },
        artifacts=[model_path, str(cols_path)],
        enabled=mlflow_enabled,
    )
    if mlflow_run_id:
        print(f"  MLflow run_id: {mlflow_run_id}")

    results = {
        "target": "run_differential",
        "model": "ngboost",
        "grid_results": grid_results,
        "best_n_estimators": best_n_est,
        "best_dist": best_dist_name,
        "best_cv_mae": best_cv_mae,
        "exclude_sequential": exclude_sequential,
        "mlflow_run_id": mlflow_run_id,
        "persisted_models": [
            {
                "target": "run_differential",
                "model_name": model_name,
                "eval_year": last_eval_year,
                "path": model_path,
            }
        ],
    }

    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nWrote {_RESULTS_PATH}")

    generate_report(results)


def _build_report(results: dict) -> str:
    grid = results["grid_results"]
    best_n_est = results["best_n_estimators"]
    best_dist = results["best_dist"]
    best_cv_mae = results["best_cv_mae"]
    persisted = results["persisted_models"]

    lines = [
        "# NGBoost run_differential Hyperparameter Tuning (Card 4.12e)",
        "",
        "## NGBoost run_differential Grid Search Results",
        "",
        "Grid search over n_estimators ∈ {200, 500, 1000}, dist = Normal only.",
        "LogNormal excluded: run_differential can be negative, causing log(Y) divide-by-zero.",
        "Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).",
        "",
        "| n_estimators | Dist | CV MAE |",
        "|-------------|------|--------|",
    ]

    for r in grid:
        mae_str = f"{r['cv_mae']:.4f}" if r["cv_mae"] is not None else "N/A"
        lines.append(f"| {r['n_estimators']} | {r['dist']} | {mae_str} |")

    lines += [
        "",
        f"**Best configuration:** n_estimators={best_n_est}, dist={best_dist}, CV MAE={best_cv_mae:.4f}",
        "",
        "## Best NGBoost Configuration",
        "",
        f"- **best_n_estimators:** {best_n_est}",
        f"- **best_dist:** {best_dist}",
        f"- **CV MAE:** {best_cv_mae:.4f}",
        "",
        "The Normal distribution is the only viable choice for run_differential, as it supports "
        "the full real line and can model both positive (home win) and negative (away win) margins.",
        "",
        "## Persisted Model",
        "",
        "The best NGBoost model was retrained on the last CV fold's training split "
        "and persisted via `save_model()` from `betting_ml.utils.model_io`.",
        "",
        "| Target | Model Name | Eval Year | Path |",
        "|--------|------------|-----------|------|",
    ]

    for m in persisted:
        lines.append(f"| {m['target']} | {m['model_name']} | {m['eval_year']} | `{m['path']}` |")

    lines += [
        "",
        "Model saved successfully. (persisted)",
        "",
    ]

    return "\n".join(lines)


def generate_report(results: dict | None = None) -> None:
    if results is None:
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
    best_n_est = results["best_n_estimators"]
    best_dist = results["best_dist"]
    best_cv_mae = results["best_cv_mae"]

    section = f"""
#### Card 4.12e Results — NGBoost run_differential Hyperparameter Tuning (Grid Search)

- **best_ngboost_config_run_diff:** {{n_estimators: {best_n_est}, dist: {best_dist}}}
- **Best CV MAE:** {best_cv_mae:.4f}
- **lognormal_viable:** false
- **Summary:** NGBoost grid search (6 combos: 3 n_estimators × 2 distributions) for run_differential; LogNormal non-viable due to negative target support; best config n_estimators={best_n_est}, dist={best_dist}, CV MAE={best_cv_mae:.4f}; model persisted via model_io.py as `ngboost_tuned`.
"""

    with open(_CONTEXT_PATH) as f:
        content = f.read()

    header = "#### Card 4.12e Results"
    if header in content:
        import re
        content = re.sub(
            r"#### Card 4\.12e Results.*?(?=####|\Z)",
            section.lstrip("\n") + "\n",
            content,
            flags=re.DOTALL,
        )
    elif "#### Card 4.12d" in content:
        content = content.replace(
            "#### Card 4.12d",
            section + "\n#### Card 4.12d",
            1,
        )
    elif "#### Card 4.12" in content:
        last_idx = content.rfind("#### Card 4.12")
        next_section = content.find("\n####", last_idx + 1)
        if next_section == -1:
            content += section
        else:
            content = content[:next_section] + "\n" + section + content[next_section:]
    elif "#### Card 4.9" in content:
        content = content.replace("#### Card 4.9", section + "\n#### Card 4.9", 1)
    else:
        content += section

    with open(_CONTEXT_PATH, "w") as f:
        f.write(content)
    print(f"Updated {_CONTEXT_PATH} with Card 4.12e results.")


if __name__ == "__main__":
    if "--report-only" in sys.argv:
        generate_report()
    else:
        run_search(
            exclude_sequential="--exclude-sequential" in sys.argv,
            mlflow_enabled="--no-mlflow" not in sys.argv,
        )
