"""Card 4.12d — NGBoost grid search hyperparameter optimization for total_runs.

Runs a grid search (2 n_estimators × 2 distributions = 4 combinations) using
temporal CV splits, persists the best NGBoost model, and writes:
  betting_ml/evaluation/tuning_results_ngboost_total_runs.json
  betting_ml/evaluation/hyperparameter_tuning_ngboost_total_runs.md

Usage:
    uv run python betting_ml/scripts/run_ngboost_total_runs_search.py
    uv run python betting_ml/scripts/run_ngboost_total_runs_search.py --report-only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "tuning_results_ngboost_total_runs.json"
_REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "hyperparameter_tuning_ngboost_total_runs.md"
_CONTEXT_PATH = PROJECT_ROOT / "project_context.md"

_N_ESTIMATORS_GRID = [200, 500]
_DIST_GRID = ["Normal", "LogNormal"]


def _get_dist_class(dist_name: str):
    from ngboost.distns import Normal, LogNormal
    return {"Normal": Normal, "LogNormal": LogNormal}[dist_name]


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


def run_search() -> None:
    from ngboost import NGBRegressor

    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

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

    grid_results = []
    best_viable = None

    print("\nRunning NGBoost grid search — total_runs (4 combinations)...")
    print(f"{'n_estimators':>12}  {'dist':>10}  {'CV MAE':>10}  {'viable':>6}")
    print("-" * 48)

    for n_est in _N_ESTIMATORS_GRID:
        for dist_name in _DIST_GRID:
            dist_cls = _get_dist_class(dist_name)
            fold_maes = []
            viable = True
            lognormal_note = None

            try:
                for fold in folds:
                    y_train = df.loc[fold["train_idx"], "total_runs"].values
                    y_eval = df.loc[fold["eval_idx"], "total_runs"].values

                    ngb = NGBRegressor(n_estimators=n_est, Dist=dist_cls, verbose=False)
                    ngb.fit(fold["X_train"].values, y_train)
                    y_pred = ngb.predict(fold["X_eval"].values)

                    if np.any(np.isnan(y_pred)) or np.any(np.isinf(y_pred)):
                        raise ValueError(f"NaN/Inf predictions from {dist_name} dist")

                    fold_maes.append(float(np.mean(np.abs(y_eval - y_pred))))

                cv_mae = float(np.mean(fold_maes))

            except Exception as exc:
                viable = False
                cv_mae = None
                lognormal_note = str(exc) if dist_name == "LogNormal" else None
                fold_maes = []

            result = {
                "n_estimators": n_est,
                "dist": dist_name,
                "cv_mae": cv_mae,
                "viable": viable,
                "lognormal_note": lognormal_note,
            }
            grid_results.append(result)

            mae_str = f"{cv_mae:.4f}" if cv_mae is not None else "null"
            viable_str = "true" if viable else "false"
            print(f"{n_est:>12}  {dist_name:>10}  {mae_str:>10}  {viable_str:>6}")

            if viable and (best_viable is None or cv_mae < best_viable["cv_mae"]):
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
        df.loc[last_fold["train_idx"], "total_runs"].values,
    )
    model_path = save_model(
        ngb_best,
        target="total_runs",
        model_name="ngboost_tuned",
        eval_year=last_eval_year,
    )
    print(f"  total_runs/ngboost_tuned → {model_path}")

    results = {
        "target": "total_runs",
        "model": "ngboost",
        "grid_results": grid_results,
        "best_n_estimators": best_n_est,
        "best_dist": best_dist_name,
        "best_cv_mae": best_cv_mae,
        "persisted_models": [
            {
                "target": "total_runs",
                "model_name": "ngboost_tuned",
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
        "# NGBoost total_runs Hyperparameter Tuning (Card 4.12d)",
        "",
        "## NGBoost total_runs Grid Search Results",
        "",
        "Grid search over n_estimators ∈ {200, 500} and dist ∈ {Normal, LogNormal}.",
        "Evaluation metric: mean absolute error (MAE) across temporal CV splits (min_train_seasons=3).",
        "",
        "| n_estimators | Dist | CV MAE | Viable |",
        "|-------------|------|--------|--------|",
    ]

    for r in grid:
        mae_str = f"{r['cv_mae']:.4f}" if r["cv_mae"] is not None else "null"
        viable_str = "Yes" if r["viable"] else "No"
        note = f" *(note: {r['lognormal_note']})*" if r.get("lognormal_note") else ""
        lines.append(f"| {r['n_estimators']} | {r['dist']} | {mae_str}{note} | {viable_str} |")

    lines += [
        "",
        f"**Best viable configuration:** n_estimators={best_n_est}, dist={best_dist}, CV MAE={best_cv_mae:.4f}",
        "",
        "## Best NGBoost Configuration",
        "",
        f"- **best_n_estimators:** {best_n_est}",
        f"- **best_dist:** {best_dist}",
        f"- **CV MAE:** {best_cv_mae:.4f}",
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

    # Check if LogNormal was viable
    lognormal_results = [r for r in grid if r["dist"] == "LogNormal"]
    lognormal_viable = any(r["viable"] for r in lognormal_results)
    lognormal_maes = [r["cv_mae"] for r in lognormal_results if r["viable"] and r["cv_mae"] is not None]
    normal_results = [r for r in grid if r["dist"] == "Normal" and r["viable"]]
    normal_maes = [r["cv_mae"] for r in normal_results if r["cv_mae"] is not None]

    if lognormal_viable and normal_maes and lognormal_maes:
        best_normal = min(normal_maes)
        best_lognormal = min(lognormal_maes)
        if best_lognormal < best_normal:
            dist_comment = (
                f"LogNormal outperformed Normal (best MAE: {best_lognormal:.4f} vs {best_normal:.4f}). "
                "This is expected since total_runs is a non-negative count — LogNormal's support "
                "over (0, ∞) is a natural fit for run totals and avoids predicting negative values."
            )
        else:
            dist_comment = (
                f"Normal slightly outperformed LogNormal (best MAE: {best_normal:.4f} vs {best_lognormal:.4f}). "
                "Despite total_runs being non-negative (a natural fit for LogNormal), the Normal "
                "distribution performed comparably, suggesting the target distribution is well-approximated "
                "by a Gaussian in this feature space."
            )
    elif lognormal_viable:
        dist_comment = (
            "Both Normal and LogNormal were viable for total_runs. "
            "LogNormal is a theoretically motivated choice since total_runs is non-negative "
            "and right-skewed — it ensures predictions remain positive by construction."
        )
    else:
        dist_comment = (
            "LogNormal encountered numerical issues during optimization. "
            "Unlike run_differential (which can be negative and is unsuitable for LogNormal), "
            "total_runs is non-negative so LogNormal is theoretically appropriate, "
            "but may require gradient clipping or constrained inputs for stable training."
        )

    lines += [
        "",
        "Model saved successfully. ✓ (persisted)",
        "",
        "## Notes on Distribution Choice",
        "",
        dist_comment,
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
#### Card 4.12d Results — NGBoost total_runs Hyperparameter Tuning (Grid Search)

- **best_ngboost_config_total_runs:** {{n_estimators: {best_n_est}, dist: {best_dist}}}
- **Best CV MAE:** {best_cv_mae:.4f}
- **Summary:** NGBoost grid search (4 combos: 2 n_estimators × 2 distributions) identified best config as n_estimators={best_n_est}, dist={best_dist} with CV MAE={best_cv_mae:.4f}; model persisted via model_io.py as `ngboost_tuned`.
"""

    with open(_CONTEXT_PATH) as f:
        content = f.read()

    header = "#### Card 4.12d Results"
    if header in content:
        import re
        content = re.sub(
            r"#### Card 4\.12d Results.*?(?=####|\Z)",
            section.lstrip("\n") + "\n",
            content,
            flags=re.DOTALL,
        )
    elif "#### Card 4.12c" in content:
        content = content.replace(
            "#### Card 4.12c",
            section + "\n#### Card 4.12c",
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
    print(f"Updated {_CONTEXT_PATH} with Card 4.12d results.")


if __name__ == "__main__":
    if "--report-only" in sys.argv:
        generate_report()
    else:
        run_search()
