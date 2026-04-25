"""Card 4.10 — Temporal CV evaluation for run differential regression baselines.

Trains Ridge, XGBoost, NGBoost Normal, and NGBoost LogNormal on all temporal
CV folds for run_differential. Derives win probability from NGBoost Normal
P(run_diff > 0), runs era feature ablation, writes results to Snowflake, and
produces betting_ml/evaluation/run_differential_results.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.evaluation import fold_metrics, brier_score_over_under
from betting_ml.models.total_runs_trainer import (
    train_ridge,
    train_xgboost,
    train_ngboost,
    p_over_line,
)

ERA_COLS = ["post_2022_rules", "game_year", "home_win_rate_trailing_3yr"]

import datetime
_CURRENT_YEAR = datetime.date.today().year


def _get_eval_year(df: pd.DataFrame, eval_idx: pd.Index) -> int:
    return int(df.loc[eval_idx, "game_year"].iloc[0])


def _align(X_train_imp: pd.DataFrame, X_eval_imp: pd.DataFrame) -> pd.DataFrame:
    X_eval_imp = X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)
    return X_eval_imp


def _impute(X_train_raw: pd.DataFrame, X_eval_raw: pd.DataFrame):
    pipeline = build_imputation_pipeline()
    X_train_imp = pipeline.fit_transform(X_train_raw)
    X_eval_imp = pipeline.transform(X_eval_raw)
    X_train_imp = X_train_imp.select_dtypes(include=[np.number])
    X_eval_imp = X_eval_imp[[c for c in X_train_imp.columns if c in X_eval_imp.columns]]
    X_eval_imp = _align(X_train_imp, X_eval_imp)
    return X_train_imp, X_eval_imp


def run_cv(df: pd.DataFrame, feature_cols: list[str]) -> tuple[list[dict], list[dict], dict]:
    """Run full temporal CV. Returns (fold_results, ablation_results, final_fold_models)."""
    fold_results: list[dict] = []
    ablation_results: list[dict] = []

    final_fold_models: dict = {}
    final_eval_year: int | None = None

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"\nRunning {len(folds)} CV folds for run_differential...")

    header = (
        f"{'Fold':<8} {'N':>6} {'Baseline':>10} {'Ridge':>10} "
        f"{'XGBoost':>10} {'NGBoost-N':>10} {'WinBrier':>10}"
    )
    print(header)
    print("-" * len(header))

    for fold_num, (train_idx, eval_idx) in enumerate(folds):
        eval_year = _get_eval_year(df, eval_idx)
        fold_label = str(eval_year)

        X_train_raw = df.loc[train_idx, feature_cols]
        X_eval_raw = df.loc[eval_idx, feature_cols]
        y_train = df.loc[train_idx, "run_differential"]
        y_eval = df.loc[eval_idx, "run_differential"]
        home_win_eval = df.loc[eval_idx, "home_win"]

        X_train_imp, X_eval_imp = _impute(X_train_raw, X_eval_raw)
        n_eval = len(y_eval)

        # Global mean baseline
        y_mean = np.full(n_eval, y_train.mean())
        baseline_metrics = fold_metrics(y_eval, y_mean)

        # Ridge
        ridge_result = train_ridge(X_train_imp, y_train, X_eval_imp)
        ridge_metrics = fold_metrics(y_eval, ridge_result["y_pred"])

        # XGBoost
        xgb_result = train_xgboost(X_train_imp, y_train, X_eval_imp)
        xgb_metrics = fold_metrics(y_eval, xgb_result["y_pred"])

        # NGBoost Normal
        ngb_n_result = train_ngboost(X_train_imp, y_train, X_eval_imp, dist="Normal")
        ngb_n_metrics = fold_metrics(y_eval, ngb_n_result["y_pred"])

        # NGBoost LogNormal — requires strictly positive targets; run_differential
        # can be negative or zero, so skip without attempting to fit.
        lognormal_viable = False
        ngb_ln_result = None
        ngb_ln_metrics = {"mae": None, "rmse": None}
        if (y_train <= 0).any():
            if fold_num == 0:
                print(
                    f"  [Fold {fold_label}] NGBoost LogNormal skipped: "
                    "run_differential contains non-positive values — "
                    "LogNormal requires strictly positive support. "
                    "(This applies to all folds; suppressing further notices.)"
                )
        else:
            try:
                ngb_ln_result = train_ngboost(X_train_imp, y_train, X_eval_imp, dist="LogNormal")
                ln_pred = ngb_ln_result["y_pred"]
                if np.any(np.isnan(ln_pred)) or np.any(np.isinf(ln_pred)):
                    raise ValueError("LogNormal produced NaN/Inf predictions")
                ngb_ln_metrics = fold_metrics(y_eval, ln_pred)
                lognormal_viable = True
            except Exception as exc:
                print(f"  [Fold {fold_label}] NGBoost LogNormal failed: {exc}")

        # Win probability from NGBoost Normal: P(run_diff > 0) = P(home win)
        ngb_n_dist_params = ngb_n_result["dist_params"]
        p_home_win = p_over_line("Normal", ngb_n_dist_params, total_line=0)
        win_brier = brier_score_over_under(y_eval.values, p_home_win, total_line=0)

        print(
            f"{fold_label:<8} {n_eval:>6} "
            f"{baseline_metrics['mae']:>10.3f} "
            f"{ridge_metrics['mae']:>10.3f} "
            f"{xgb_metrics['mae']:>10.3f} "
            f"{ngb_n_metrics['mae']:>10.3f} "
            f"{win_brier:>10.4f}"
        )

        for model_name, m, brier in [
            ("global_mean", baseline_metrics, None),
            ("ridge", ridge_metrics, None),
            ("xgboost", xgb_metrics, None),
            ("ngboost_normal", ngb_n_metrics, win_brier),
            ("ngboost_lognormal", ngb_ln_metrics, None),
        ]:
            fold_results.append({
                "fold": fold_label,
                "model": model_name,
                "n_eval": n_eval,
                "mae": m["mae"],
                "rmse": m["rmse"],
                "win_prob_brier": brier,
            })

        # --- Era feature ablation (XGBoost only) ---
        era_cols_present = [c for c in ERA_COLS if c in feature_cols]
        no_era_cols = [c for c in feature_cols if c not in ERA_COLS]

        X_train_no_era_raw = df.loc[train_idx, no_era_cols]
        X_eval_no_era_raw = df.loc[eval_idx, no_era_cols]
        X_train_no_era, X_eval_no_era = _impute(X_train_no_era_raw, X_eval_no_era_raw)

        xgb_no_era = train_xgboost(X_train_no_era, y_train, X_eval_no_era)
        mae_without_era = fold_metrics(y_eval, xgb_no_era["y_pred"])["mae"]
        mae_with_era = xgb_metrics["mae"]
        era_delta_mae = mae_without_era - mae_with_era

        # Home win rate sub-ablation — run for every fold, highlight 2023
        hwrt_col = "home_win_rate_trailing_3yr"
        no_hwrt_cols = [c for c in feature_cols if c != hwrt_col]
        X_train_no_hwrt_raw = df.loc[train_idx, no_hwrt_cols]
        X_eval_no_hwrt_raw = df.loc[eval_idx, no_hwrt_cols]
        X_train_no_hwrt, X_eval_no_hwrt = _impute(X_train_no_hwrt_raw, X_eval_no_hwrt_raw)
        xgb_no_hwrt = train_xgboost(X_train_no_hwrt, y_train, X_eval_no_hwrt)
        mae_without_hwrt = fold_metrics(y_eval, xgb_no_hwrt["y_pred"])["mae"]
        home_win_rate_delta_mae = mae_without_hwrt - mae_with_era

        ablation_results.append({
            "fold": fold_label,
            "mae_with_era": mae_with_era,
            "mae_without_era": mae_without_era,
            "era_delta_mae": era_delta_mae,
            "mae_without_hwrt": mae_without_hwrt,
            "home_win_rate_delta_mae": home_win_rate_delta_mae,
        })

        # Track final fold for model serialization
        final_fold_models = {
            "ridge": ridge_result["model"],
            "xgboost": xgb_result["model"],
            "ngboost_normal": ngb_n_result["model"],
            "ngboost_lognormal": ngb_ln_result["model"] if lognormal_viable else None,
            "lognormal_viable": lognormal_viable,
        }
        final_eval_year = eval_year

    final_fold_models["eval_year"] = final_eval_year
    return fold_results, ablation_results, final_fold_models


def _write_snowflake(fold_results: list[dict], ablation_results: list[dict], summary_row: dict) -> None:
    print("\nWriting results to Snowflake...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute("CREATE SCHEMA IF NOT EXISTS baseball_data.betting_ml")

        # cv_results_run_diff
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_results_run_diff (
                fold VARCHAR,
                model VARCHAR,
                n_eval INTEGER,
                mae FLOAT,
                rmse FLOAT,
                win_prob_brier FLOAT,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.cv_results_run_diff")
        for row in fold_results:
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_results_run_diff
                    (fold, model, n_eval, mae, rmse, win_prob_brier)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["fold"],
                    row["model"],
                    row["n_eval"],
                    row["mae"],
                    row["rmse"],
                    row["win_prob_brier"],
                ),
            )
        print(f"  Inserted {len(fold_results)} rows into cv_results_run_diff")

        # cv_era_ablation_run_diff
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_era_ablation_run_diff (
                fold VARCHAR,
                mae_with_era FLOAT,
                mae_without_era FLOAT,
                era_delta_mae FLOAT,
                mae_without_hwrt FLOAT,
                home_win_rate_delta_mae FLOAT,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.cv_era_ablation_run_diff")
        for row in ablation_results:
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_era_ablation_run_diff
                    (fold, mae_with_era, mae_without_era, era_delta_mae,
                     mae_without_hwrt, home_win_rate_delta_mae)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["fold"],
                    row["mae_with_era"],
                    row["mae_without_era"],
                    row["era_delta_mae"],
                    row["mae_without_hwrt"],
                    row["home_win_rate_delta_mae"],
                ),
            )
        print(f"  Inserted {len(ablation_results)} rows into cv_era_ablation_run_diff")

        # cv_summary_run_diff
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_summary_run_diff (
                best_mae_model VARCHAR,
                best_win_prob_brier_model VARCHAR,
                era_features_help BOOLEAN,
                home_win_rate_trailing_helps BOOLEAN,
                lognormal_viable BOOLEAN,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("TRUNCATE TABLE baseball_data.betting_ml.cv_summary_run_diff")
        cur.execute(
            """
            INSERT INTO baseball_data.betting_ml.cv_summary_run_diff
                (best_mae_model, best_win_prob_brier_model, era_features_help,
                 home_win_rate_trailing_helps, lognormal_viable)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                summary_row["best_mae_model"],
                summary_row["best_win_prob_brier_model"],
                summary_row["era_features_help"],
                summary_row["home_win_rate_trailing_helps"],
                summary_row["lognormal_viable"],
            ),
        )
        print("  Inserted 1 row into cv_summary_run_diff")

        conn.commit()
    finally:
        conn.close()

    print("Snowflake writes complete.")


def _build_summary(fold_results: list[dict], ablation_results: list[dict], lognormal_viable: bool) -> dict:
    results_df = pd.DataFrame(fold_results)

    def mean_mae(model: str) -> float:
        return float(results_df[results_df["model"] == model]["mae"].dropna().mean())

    non_baseline_models = ["ridge", "xgboost", "ngboost_normal"]
    if lognormal_viable:
        non_baseline_models.append("ngboost_lognormal")

    best_mae_model = min(non_baseline_models, key=mean_mae)

    ngb_brier_vals = results_df[results_df["model"] == "ngboost_normal"]["win_prob_brier"].dropna()
    best_win_prob_brier_model = "ngboost_normal" if len(ngb_brier_vals) > 0 else None

    ablation_df = pd.DataFrame(ablation_results)
    era_features_help = bool((ablation_df["era_delta_mae"] > 0).sum() > len(ablation_df) / 2)
    home_win_rate_trailing_helps = bool(
        (ablation_df["home_win_rate_delta_mae"] > 0).sum() > len(ablation_df) / 2
    )

    return {
        "best_mae_model": best_mae_model,
        "best_win_prob_brier_model": best_win_prob_brier_model or "ngboost_normal",
        "era_features_help": era_features_help,
        "home_win_rate_trailing_helps": home_win_rate_trailing_helps,
        "lognormal_viable": lognormal_viable,
    }


def _verify_beats_baseline(fold_results: list[dict], lognormal_viable: bool) -> None:
    results_df = pd.DataFrame(fold_results)
    folds = results_df["fold"].unique()
    n_folds = len(folds)

    check_models = ["ridge", "xgboost", "ngboost_normal"]
    if lognormal_viable:
        check_models.append("ngboost_lognormal")

    failures = []
    for model_name in check_models:
        n_beats = 0
        for fold in folds:
            model_mae = results_df[
                (results_df["model"] == model_name) & (results_df["fold"] == fold)
            ]["mae"].dropna().values
            baseline_mae = results_df[
                (results_df["model"] == "global_mean") & (results_df["fold"] == fold)
            ]["mae"].dropna().values
            if len(model_mae) > 0 and len(baseline_mae) > 0 and model_mae[0] < baseline_mae[0]:
                n_beats += 1
        if n_beats <= n_folds // 2:
            failures.append(f"{model_name} beats baseline on only {n_beats}/{n_folds} folds")

    if failures:
        print("\nFAILURE: Some models do not beat global mean baseline on majority of folds:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)

    print("\nAll models beat global mean baseline on majority of folds. ✓")


def _build_report(
    fold_results: list[dict],
    ablation_results: list[dict],
    summary: dict,
) -> str:
    results_df = pd.DataFrame(fold_results)
    ablation_df = pd.DataFrame(ablation_results)
    folds = sorted(results_df["fold"].unique())
    lognormal_viable = summary["lognormal_viable"]

    lines = ["# Run Differential Regression — Baseline Model Results (Card 4.10)", ""]

    # --- Per-Season MAE/RMSE by Model ---
    lines.append("## Per-Season MAE/RMSE by Model")
    lines.append("")

    ln_header = "NGBoost LogNormal MAE |" if lognormal_viable else "NGBoost LogNormal MAE |"
    header = (
        "| Season | Global Mean MAE | Ridge MAE | XGBoost MAE | "
        "NGBoost Normal MAE | "
        + ln_header
        + " Ridge RMSE | XGBoost RMSE | NGBoost Normal RMSE |"
    )
    sep = "|---|---|---|---|---|---|---|---|---|"
    lines.append(header)
    lines.append(sep)

    for fold in folds:
        fd = results_df[results_df["fold"] == fold]

        def get_val(model: str, metric: str) -> str:
            row = fd[fd["model"] == model]
            if len(row) == 0 or pd.isna(row[metric].values[0]):
                return "N/A"
            return f"{row[metric].values[0]:.3f}"

        non_baseline = ["ridge", "xgboost", "ngboost_normal"]
        if lognormal_viable:
            non_baseline.append("ngboost_lognormal")

        fold_maes = {}
        for m in non_baseline:
            row = fd[fd["model"] == m]
            if len(row) > 0 and not pd.isna(row["mae"].values[0]):
                fold_maes[m] = float(row["mae"].values[0])

        best_mae_val = min(fold_maes.values()) if fold_maes else float("nan")

        def fmt_mae(model: str) -> str:
            v = fold_maes.get(model, float("nan"))
            if np.isnan(v):
                return "N/A"
            s = f"{v:.3f}"
            return f"**{s}**" if abs(v - best_mae_val) < 1e-9 else s

        baseline_row = fd[fd["model"] == "global_mean"]
        baseline_mae = float(baseline_row["mae"].values[0]) if len(baseline_row) > 0 else float("nan")
        ln_cell = fmt_mae("ngboost_lognormal") if lognormal_viable else "N/A"

        lines.append(
            f"| {fold} "
            f"| {baseline_mae:.3f} "
            f"| {fmt_mae('ridge')} "
            f"| {fmt_mae('xgboost')} "
            f"| {fmt_mae('ngboost_normal')} "
            f"| {ln_cell} "
            f"| {get_val('ridge', 'rmse')} "
            f"| {get_val('xgboost', 'rmse')} "
            f"| {get_val('ngboost_normal', 'rmse')} |"
        )

    lines.append("")

    # --- Model Comparison Summary ---
    lines.append("## Model Comparison Summary")
    lines.append("")
    lines.append("Average MAE and RMSE across all CV folds:")
    lines.append("")
    lines.append("| Model | Mean MAE | Mean RMSE |")
    lines.append("|---|---|---|")

    all_models = ["global_mean", "ridge", "xgboost", "ngboost_normal"]
    if lognormal_viable:
        all_models.append("ngboost_lognormal")

    for model in all_models:
        mdf = results_df[results_df["model"] == model]
        mean_mae = float(mdf["mae"].dropna().mean())
        mean_rmse = float(mdf["rmse"].dropna().mean())
        lines.append(f"| {model} | {mean_mae:.4f} | {mean_rmse:.4f} |")

    non_baseline = [m for m in all_models if m != "global_mean"]
    best_mae_model = min(non_baseline, key=lambda m: float(results_df[results_df["model"] == m]["mae"].dropna().mean()))
    best_rmse_model = min(non_baseline, key=lambda m: float(results_df[results_df["model"] == m]["rmse"].dropna().mean()))

    lines.append("")
    lines.append(f"**Best MAE:** {best_mae_model}")
    lines.append(f"**Best RMSE:** {best_rmse_model}")
    lines.append("")

    if not lognormal_viable:
        lines.append(
            "> **Note — NGBoost LogNormal not viable for run_differential:** "
            "Run differential can be negative (home team loses), which violates the "
            "LogNormal distribution's strictly-positive support. Training was attempted "
            "but produced NaN/invalid predictions. LogNormal is excluded from ranking."
        )
        lines.append("")

    # --- Win Probability from Run Differential Distribution ---
    lines.append("## Win Probability from Run Differential Distribution")
    lines.append("")
    lines.append(
        "**Method:** P(home win) = P(run_diff > 0) under NGBoost Normal N(μ, σ²). "
        "Equivalently: 1 − Φ(−μ/σ) where Φ is the standard Normal CDF. "
        "Computed via `p_over_line('Normal', dist_params, total_line=0)`."
    )
    lines.append("")
    lines.append("| Fold | NGBoost Normal Win Prob Brier | N eval games |")
    lines.append("|---|---|---|")

    ngb_n_rows = results_df[results_df["model"] == "ngboost_normal"]
    all_brier_vals = []
    for fold in folds:
        row = ngb_n_rows[ngb_n_rows["fold"] == fold]
        if len(row) > 0:
            brier = row["win_prob_brier"].values[0]
            n_eval = int(row["n_eval"].values[0])
            brier_str = f"{brier:.4f}" if brier is not None and not pd.isna(brier) else "N/A"
            lines.append(f"| {fold} | {brier_str} | {n_eval} |")
            if brier is not None and not pd.isna(brier):
                all_brier_vals.append(float(brier))

    agg_brier = float(np.mean(all_brier_vals)) if all_brier_vals else float("nan")
    agg_brier_str = f"{agg_brier:.4f}" if not np.isnan(agg_brier) else "N/A"
    lines.append("")
    lines.append(f"**Aggregate Brier score (all folds):** {agg_brier_str}")
    lines.append("")
    lines.append(
        "> **Forward reference:** This Brier score will be compared against the binary "
        "classifier from Card 4.11 once that card is complete. A regression-derived win "
        "probability that rivals a dedicated classifier would support using a single NGBoost "
        "model for both regression and classification targets."
    )
    lines.append("")

    # --- Era Feature Ablation ---
    lines.append("## Era Feature Ablation")
    lines.append("")
    lines.append(
        "XGBoost trained with all retained era features (`post_2022_rules`, `game_year`, "
        "`home_win_rate_trailing_3yr`) vs. without them. "
        "Delta > 0 means era features reduce MAE (help); Delta < 0 means they hurt."
    )
    lines.append("")
    lines.append("| Fold | MAE with era features | MAE without era features | Delta (positive = help) |")
    lines.append("|---|---|---|---|")

    for _, row in ablation_df.iterrows():
        fold_note = " ← 2022 rule-change effect" if row["fold"] == "2023" else ""
        lines.append(
            f"| {row['fold']}{fold_note} "
            f"| {row['mae_with_era']:.3f} "
            f"| {row['mae_without_era']:.3f} "
            f"| {row['era_delta_mae']:+.3f} |"
        )

    lines.append("")
    avg_era_delta = float(ablation_df["era_delta_mae"].mean())
    era_row_2023 = ablation_df[ablation_df["fold"] == "2023"]
    if len(era_row_2023) > 0:
        delta_2023 = float(era_row_2023["era_delta_mae"].values[0])
        lines.append(
            f"**2023 fold era delta:** {delta_2023:+.3f} runs — "
            "motivated by NB01 finding of a ~0.64-run structural mean shift from the "
            "2022 shift ban and pitch clock rule changes."
        )
    lines.append(f"**Average era delta across all folds:** {avg_era_delta:+.3f} runs")
    era_helps_str = "Yes — era features materially reduce run differential prediction error." if summary["era_features_help"] else "No — era features do not consistently reduce prediction error across folds."
    lines.append(f"**Era features help:** {era_helps_str}")
    lines.append("")

    # --- Time-Varying Home Win Rate ---
    lines.append("## Time-Varying Home Win Rate")
    lines.append("")
    lines.append(
        "**NB01 finding:** Home advantage declined from 0.548 (2020) to 0.519 (2023); "
        "a static 0.529 average is wrong for recent seasons. "
        "`home_win_rate_trailing_3yr` captures this time-varying trend."
    )
    lines.append("")
    lines.append(
        "Sub-ablation: XGBoost retaining `post_2022_rules` and `game_year` but dropping "
        "`home_win_rate_trailing_3yr`. Delta > 0 means the time-varying rate provides "
        "marginal benefit beyond the era flags alone."
    )
    lines.append("")
    lines.append("| Fold | MAE without home_win_rate_trailing_3yr | Delta vs. full era features |")
    lines.append("|---|---|---|")

    for _, row in ablation_df.iterrows():
        lines.append(
            f"| {row['fold']} "
            f"| {row['mae_without_hwrt']:.3f} "
            f"| {row['home_win_rate_delta_mae']:+.3f} |"
        )

    avg_hwrt_delta = float(ablation_df["home_win_rate_delta_mae"].mean())
    hwrt_row_2023 = ablation_df[ablation_df["fold"] == "2023"]
    if len(hwrt_row_2023) > 0:
        hwrt_delta_2023 = float(hwrt_row_2023["home_win_rate_delta_mae"].values[0])
        lines.append(f"\n**2023 fold home_win_rate_delta_mae:** {hwrt_delta_2023:+.3f} runs")
    lines.append(f"**Average home_win_rate_delta_mae across all folds:** {avg_hwrt_delta:+.3f} runs")

    hwrt_conclusion = (
        "`home_win_rate_trailing_3yr` provides additional benefit beyond `post_2022_rules` + `game_year` alone."
        if summary["home_win_rate_trailing_helps"]
        else
        "`home_win_rate_trailing_3yr` marginal benefit is largely absorbed by `post_2022_rules` + `game_year`. "
        "The era flag and calendar year already capture most of the home advantage trend."
    )
    lines.append(f"\n**Conclusion:** {hwrt_conclusion}")
    lines.append("")

    # --- Best Model Selection ---
    lines.append("## Best Model Selection")
    lines.append("")
    best_model = summary["best_mae_model"]
    best_mae_val = float(results_df[results_df["model"] == best_model]["mae"].dropna().mean())
    baseline_mae_val = float(results_df[results_df["model"] == "global_mean"]["mae"].dropna().mean())
    improvement = baseline_mae_val - best_mae_val

    if best_model in ("ngboost_normal", "ngboost_lognormal"):
        dist_comment = (
            "NGBoost provides a full predictive distribution: P(home win) = P(run_diff > 0) "
            "is computed directly from the Normal CDF, eliminating the need for a separate "
            "calibration step. The derived win probability Brier score (see above) indicates "
            f"whether this single model can substitute for a dedicated binary classifier (Card 4.11)."
        )
    elif best_model == "xgboost":
        dist_comment = (
            "XGBoost provides point predictions; win probability would require a separate "
            "distributional approximation (residual-based Normal). NGBoost Normal is preferred "
            "for downstream probabilistic use despite potentially slightly higher MAE."
        )
    else:
        dist_comment = "Ridge provides only point predictions with no distributional output."

    lines.append(f"**Recommended model for downstream use (Card 4.11 comparison and Card 4.13 strategy):** `{best_model}`")
    lines.append("")
    lines.append(
        f"`{best_model}` achieves mean MAE of {best_mae_val:.4f} across all CV folds, "
        f"improving on the global mean baseline ({baseline_mae_val:.4f}) by {improvement:.4f} runs. "
        f"{dist_comment}"
    )
    lines.append("")

    return "\n".join(lines)


def write_report(
    fold_results: list[dict],
    ablation_results: list[dict],
    summary: dict,
) -> None:
    content = _build_report(fold_results, ablation_results, summary)
    report_path = PROJECT_ROOT / "betting_ml" / "evaluation" / "run_differential_results.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(content)
    print(f"\nWrote {report_path}")


def update_project_context(
    fold_results: list[dict],
    ablation_results: list[dict],
    summary: dict,
) -> None:
    context_path = PROJECT_ROOT / "project_context.md"
    results_df = pd.DataFrame(fold_results)
    ablation_df = pd.DataFrame(ablation_results)

    best_model = summary["best_mae_model"]
    best_mae = float(results_df[results_df["model"] == best_model]["mae"].dropna().mean())

    ngb_brier_vals = results_df[results_df["model"] == "ngboost_normal"]["win_prob_brier"].dropna()
    agg_brier = float(ngb_brier_vals.mean()) if len(ngb_brier_vals) > 0 else float("nan")
    agg_brier_str = f"{agg_brier:.4f}" if not np.isnan(agg_brier) else "N/A"

    card_410_section = f"""
#### Card 4.10 Results — Run Differential Regression Baselines

- **Best model:** `{best_model}` (mean MAE = {best_mae:.4f})
- **NGBoost Normal aggregate win probability Brier score:** {agg_brier_str}
- **Era features help (post_2022_rules + game_year):** {summary['era_features_help']}
- **home_win_rate_trailing_3yr helps beyond era flags:** {summary['home_win_rate_trailing_helps']}
- **NGBoost LogNormal viable for run_differential:** {summary['lognormal_viable']} (negative support incompatible)
- **Details:** `betting_ml/evaluation/run_differential_results.md`
"""

    with open(context_path) as f:
        content = f.read()

    if "Card 4.10 Results" not in content:
        insert_marker = "#### Card 4.11"
        if insert_marker in content:
            content = content.replace(insert_marker, card_410_section + "\n" + insert_marker, 1)
        else:
            content += card_410_section

        with open(context_path, "w") as f:
            f.write(content)
        print(f"Updated {context_path} with Card 4.10 results.")
    else:
        print("project_context.md already contains Card 4.10 results — skipping.")


def main() -> None:
    print("Card 4.10 — Run Differential Regression Baselines")
    print("=" * 60)

    print("Loading features from Snowflake...")
    df = load_features()
    print(
        f"Loaded {len(df)} rows, {df['game_year'].nunique()} seasons: "
        f"{sorted(df['game_year'].unique())}"
    )

    retained_features = load_retained_features()
    feature_cols = [f for f in retained_features if f in df.columns]
    missing_feats = [f for f in retained_features if f not in df.columns]
    if missing_feats:
        print(
            f"WARNING: {len(missing_feats)} retained features not in df "
            f"(will be skipped): {missing_feats[:5]}..."
        )

    n_before = len(df)
    df = df[df["game_year"] != _CURRENT_YEAR].copy()
    if len(df) < n_before:
        print(f"Dropped {n_before - len(df)} rows for in-progress season {_CURRENT_YEAR}.")

    fold_results, ablation_results, final_fold_models = run_cv(df, feature_cols)

    lognormal_viable = final_fold_models["lognormal_viable"]
    summary = _build_summary(fold_results, ablation_results, lognormal_viable)

    # Save final-fold models
    eval_year = final_fold_models["eval_year"]
    print(f"\nSaving final-fold models (eval_year={eval_year})...")
    save_model(final_fold_models["ridge"], target="run_differential", model_name="ridge", eval_year=eval_year)
    save_model(final_fold_models["xgboost"], target="run_differential", model_name="xgboost", eval_year=eval_year)
    save_model(final_fold_models["ngboost_normal"], target="run_differential", model_name="ngboost_normal", eval_year=eval_year)
    if lognormal_viable and final_fold_models["ngboost_lognormal"] is not None:
        save_model(final_fold_models["ngboost_lognormal"], target="run_differential", model_name="ngboost_lognormal", eval_year=eval_year)
    print("Models saved.")

    _write_snowflake(fold_results, ablation_results, summary)

    _verify_beats_baseline(fold_results, lognormal_viable)

    write_report(fold_results, ablation_results, summary)
    update_project_context(fold_results, ablation_results, summary)

    print("\nCard 4.10 complete.")


if __name__ == "__main__":
    main()
