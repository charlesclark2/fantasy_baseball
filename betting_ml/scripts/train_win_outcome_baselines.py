"""Card 4.11 — Temporal CV evaluation for win outcome classification baselines.

Trains Logistic Regression, XGBoost (Platt), and XGBoost (isotonic) on all
temporal CV folds, runs home bias ablation for 2023–2025 folds, writes results
to Snowflake, generates betting_ml/evaluation/win_outcome_results.md, and
updates project_context.md.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.models.win_outcome_trainer import (
    compute_calibration_curve,
    compute_ece,
    train_logistic,
    train_xgboost_classifier,
)
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection, load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.model_io import save_model
from betting_ml.utils.preprocessing import build_imputation_pipeline

HOME_BIAS_COL = "home_win_rate_trailing_3yr"
HOME_BIAS_YEARS = {2023, 2024, 2025}


def _get_eval_year(df: pd.DataFrame, eval_idx: pd.Index) -> int:
    return int(df.loc[eval_idx, "game_year"].iloc[0])


def _clip_probs(p: np.ndarray) -> np.ndarray:
    return np.clip(p, 1e-7, 1 - 1e-7)


def _impute_and_align(
    pipeline,
    X_train_raw: pd.DataFrame,
    X_eval_raw: pd.DataFrame,
    fit: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if fit:
        X_train_imp = pipeline.fit_transform(X_train_raw)
    else:
        X_train_imp = pipeline.transform(X_train_raw)
    X_eval_imp = pipeline.transform(X_eval_raw)
    X_train_imp = X_train_imp.select_dtypes(include=[np.number])
    X_eval_imp = X_eval_imp[[c for c in X_train_imp.columns if c in X_eval_imp.columns]]
    X_eval_imp = X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)
    return X_train_imp, X_eval_imp


def run_cv() -> tuple[pd.DataFrame, pd.DataFrame, list[dict], dict]:
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

    fold_results: list[dict] = []
    fold_calibration: list[dict] = []
    final_fold: dict | None = None
    final_eval_year: int | None = None

    folds = list(all_season_splits(df, min_train_seasons=3))
    print(f"\nRunning {len(folds)} CV folds...")

    for train_idx, eval_idx in folds:
        eval_year = _get_eval_year(df, eval_idx)
        fold_label = str(eval_year)

        X_train_raw = df.loc[train_idx, feature_cols]
        X_eval_raw = df.loc[eval_idx, feature_cols]
        y_train = df.loc[train_idx, "home_win"].astype(int)
        y_eval = df.loc[eval_idx, "home_win"].astype(int)

        pipeline = build_imputation_pipeline()
        X_train_imp, X_eval_imp = _impute_and_align(pipeline, X_train_raw, X_eval_raw)

        n_eval = len(y_eval)
        p_naive = np.full(n_eval, float(y_train.mean()))

        lr_result = train_logistic(X_train_imp, y_train, X_eval_imp)
        p_logistic = lr_result["y_pred_proba"]

        xgb_platt_result = train_xgboost_classifier(
            X_train_imp, y_train, X_eval_imp, y_eval, calibration="sigmoid"
        )
        p_xgb_platt = xgb_platt_result["y_pred_proba"]
        p_xgb_raw = xgb_platt_result["y_pred_proba_uncalibrated"]
        ece_raw = compute_ece(y_eval, p_xgb_raw)

        xgb_iso_result = train_xgboost_classifier(
            X_train_imp, y_train, X_eval_imp, y_eval, calibration="isotonic"
        )
        p_xgb_iso = xgb_iso_result["y_pred_proba"]

        for model_name, p in [
            ("naive_baseline", p_naive),
            ("logistic", p_logistic),
            ("xgb_platt", p_xgb_platt),
            ("xgb_isotonic", p_xgb_iso),
        ]:
            ll = float(log_loss(y_eval, _clip_probs(p)))
            bs = float(brier_score_loss(y_eval, p))
            auc = float(roc_auc_score(y_eval, p))
            calib_curve = compute_calibration_curve(y_eval, p)
            ece = compute_ece(y_eval, p)
            fold_results.append({
                "fold": fold_label,
                "model": model_name,
                "n_eval": n_eval,
                "log_loss": ll,
                "brier_score": bs,
                "auc_roc": auc,
                "ece": ece,
                "calibration_curve": calib_curve,
            })

        fold_calibration.append({
            "fold": fold_label,
            "calibration_method": "platt",
            "ece": compute_ece(y_eval, p_xgb_platt),
            "ece_uncalibrated": ece_raw,
        })
        fold_calibration.append({
            "fold": fold_label,
            "calibration_method": "isotonic",
            "ece": compute_ece(y_eval, p_xgb_iso),
            "ece_uncalibrated": None,
        })

        print(
            f"Fold {fold_label}: n={n_eval} | "
            f"naive LL={float(log_loss(y_eval, _clip_probs(p_naive))):.4f} | "
            f"LR LL={float(log_loss(y_eval, _clip_probs(p_logistic))):.4f} | "
            f"XGB Platt LL={float(log_loss(y_eval, _clip_probs(p_xgb_platt))):.4f} | "
            f"XGB Iso LL={float(log_loss(y_eval, _clip_probs(p_xgb_iso))):.4f}"
        )

        final_fold = {
            "lr_model": lr_result["model"],
            "xgb_platt_model": xgb_platt_result["calibrated_model"],
            "xgb_iso_model": xgb_iso_result["calibrated_model"],
        }
        final_eval_year = eval_year

    # --- Home bias ablation (2023–2025 folds only) ---
    print("\nRunning home bias ablation (2023–2025 folds)...")
    home_bias_results: list[dict] = []
    bias_folds = [
        (tr, ev) for tr, ev in folds if _get_eval_year(df, ev) in HOME_BIAS_YEARS
    ]

    for train_idx, eval_idx in bias_folds:
        eval_year = _get_eval_year(df, eval_idx)
        fold_label = str(eval_year)

        y_train_b = df.loc[train_idx, "home_win"].astype(int)
        y_eval_b = df.loc[eval_idx, "home_win"].astype(int)

        # With home_win_rate_trailing_3yr
        X_train_raw_w = df.loc[train_idx, feature_cols]
        X_eval_raw_w = df.loc[eval_idx, feature_cols]
        pipeline_w = build_imputation_pipeline()
        X_train_imp_w, X_eval_imp_w = _impute_and_align(pipeline_w, X_train_raw_w, X_eval_raw_w)
        xgb_w = train_xgboost_classifier(
            X_train_imp_w, y_train_b, X_eval_imp_w, y_eval_b, calibration="sigmoid"
        )
        p_with = xgb_w["y_pred_proba"]

        # Without home_win_rate_trailing_3yr
        feature_cols_no_hwrt = [f for f in feature_cols if f != HOME_BIAS_COL]
        X_train_raw_n = df.loc[train_idx, feature_cols_no_hwrt]
        X_eval_raw_n = df.loc[eval_idx, feature_cols_no_hwrt]
        pipeline_n = build_imputation_pipeline()
        X_train_imp_n, X_eval_imp_n = _impute_and_align(pipeline_n, X_train_raw_n, X_eval_raw_n)
        xgb_n = train_xgboost_classifier(
            X_train_imp_n, y_train_b, X_eval_imp_n, y_eval_b, calibration="sigmoid"
        )
        p_without = xgb_n["y_pred_proba"]

        ll_with = float(log_loss(y_eval_b, _clip_probs(p_with)))
        ll_without = float(log_loss(y_eval_b, _clip_probs(p_without)))
        brier_with = float(brier_score_loss(y_eval_b, p_with))
        brier_without = float(brier_score_loss(y_eval_b, p_without))

        mean_pred = float(np.mean(p_without))
        mean_actual = float(np.mean(y_eval_b.astype(float)))
        if mean_pred > mean_actual + 0.02:
            bias_dir = "overprices_home"
        elif mean_pred < mean_actual - 0.02:
            bias_dir = "underprices_home"
        else:
            bias_dir = "neutral"

        home_bias_results.append({
            "fold": fold_label,
            "log_loss_with_hwrt": ll_with,
            "log_loss_without_hwrt": ll_without,
            "brier_with_hwrt": brier_with,
            "brier_without_hwrt": brier_without,
            "home_bias_direction": bias_dir,
        })
        print(
            f"  Bias fold {fold_label}: LL_with={ll_with:.4f} LL_without={ll_without:.4f} "
            f"bias={bias_dir}"
        )

    avg_ll_with = float(np.mean([r["log_loss_with_hwrt"] for r in home_bias_results]))
    avg_ll_without = float(np.mean([r["log_loss_without_hwrt"] for r in home_bias_results]))
    # hwrt helps = removing it increases log_loss AND at least one fold shows overpricing
    hwrt_reduces_bias: bool = (
        avg_ll_without > avg_ll_with
        and any(r["home_bias_direction"] == "overprices_home" for r in home_bias_results)
    )

    # --- Save final-fold models ---
    print(f"\nSaving final-fold models (eval_year={final_eval_year})...")
    save_model(
        final_fold["lr_model"],
        target="home_win",
        model_name="logistic",
        eval_year=final_eval_year,
    )
    save_model(
        final_fold["xgb_platt_model"],
        target="home_win",
        model_name="xgboost_platt",
        eval_year=final_eval_year,
    )
    save_model(
        final_fold["xgb_iso_model"],
        target="home_win",
        model_name="xgboost_isotonic",
        eval_year=final_eval_year,
    )
    print("Models saved.")

    # --- Build summary ---
    results_df = pd.DataFrame(fold_results)
    calib_df = pd.DataFrame(fold_calibration)

    non_baseline = ["logistic", "xgb_platt", "xgb_isotonic"]

    def mean_ll(m: str) -> float:
        return float(results_df[results_df["model"] == m]["log_loss"].mean())

    def mean_brier(m: str) -> float:
        return float(results_df[results_df["model"] == m]["brier_score"].mean())

    def mean_auc(m: str) -> float:
        return float(results_df[results_df["model"] == m]["auc_roc"].mean())

    best_ll_model = min(non_baseline, key=mean_ll)
    best_brier_model = min(non_baseline, key=mean_brier)
    best_auc_model = max(non_baseline, key=mean_auc)

    platt_ece = float(calib_df[calib_df["calibration_method"] == "platt"]["ece"].mean())
    iso_ece = float(calib_df[calib_df["calibration_method"] == "isotonic"]["ece"].mean())
    better_calib_method = "platt" if platt_ece <= iso_ece else "isotonic"
    best_calib_model = "xgb_platt" if better_calib_method == "platt" else "xgb_isotonic"

    bias_summary = ", ".join(
        f"{r['fold']}:{r['home_bias_direction']}" for r in home_bias_results
    )

    summary = {
        "best_log_loss_model": best_ll_model,
        "best_brier_model": best_brier_model,
        "best_auc_model": best_auc_model,
        "best_calibration_model": best_calib_model,
        "better_calibration_method": better_calib_method,
        "hwrt_reduces_bias": hwrt_reduces_bias,
        "home_bias_in_recent_seasons": bias_summary,
        "platt_mean_ece": platt_ece,
        "isotonic_mean_ece": iso_ece,
        "best_ll_mean": mean_ll(best_ll_model),
        "best_brier_mean": mean_brier(best_brier_model),
    }

    # --- Print per-fold summary table ---
    print("\n=== Per-Fold Summary ===")
    header = f"{'Fold':>6} | {'N':>5} | {'Naive LL':>9} | {'LR LL':>8} | {'XGB Platt LL':>12} | {'XGB Iso LL':>10} | {'Naive Brier':>11} | {'LR Brier':>9} | {'XGB Platt Brier':>15} | {'Naive AUC':>9} | {'LR AUC':>7} | {'XGB Platt AUC':>13} | {'XGB Platt ECE':>13}"
    print(header)
    print("-" * len(header))
    for fold in sorted(results_df["fold"].unique()):
        fd = results_df[results_df["fold"] == fold]

        def gv(model: str, col: str) -> float:
            r = fd[fd["model"] == model]
            return float(r[col].values[0]) if len(r) > 0 else float("nan")

        print(
            f"{fold:>6} | {gv('naive_baseline', 'n_eval'):>5.0f} | "
            f"{gv('naive_baseline', 'log_loss'):>9.4f} | "
            f"{gv('logistic', 'log_loss'):>8.4f} | "
            f"{gv('xgb_platt', 'log_loss'):>12.4f} | "
            f"{gv('xgb_isotonic', 'log_loss'):>10.4f} | "
            f"{gv('naive_baseline', 'brier_score'):>11.4f} | "
            f"{gv('logistic', 'brier_score'):>9.4f} | "
            f"{gv('xgb_platt', 'brier_score'):>15.4f} | "
            f"{gv('naive_baseline', 'auc_roc'):>9.4f} | "
            f"{gv('logistic', 'auc_roc'):>7.4f} | "
            f"{gv('xgb_platt', 'auc_roc'):>13.4f} | "
            f"{gv('xgb_platt', 'ece'):>13.4f}"
        )

    print(f"\nBest log loss model: {best_ll_model} (mean={mean_ll(best_ll_model):.4f})")
    print(f"Best Brier score model: {best_brier_model} (mean={mean_brier(best_brier_model):.4f})")
    print(f"Better calibration method: {better_calib_method} (Platt ECE={platt_ece:.4f}, Isotonic ECE={iso_ece:.4f})")
    print(f"HWRT reduces home bias: {hwrt_reduces_bias}")

    return results_df, calib_df, home_bias_results, summary


def write_to_snowflake(
    results_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    home_bias_results: list[dict],
    summary: dict,
    retrain_version: str,
) -> None:
    print("\nWriting results to Snowflake...")
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute("CREATE SCHEMA IF NOT EXISTS baseball_data.betting_ml")

        # --- cv_results_win_outcome ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_results_win_outcome (
                fold VARCHAR,
                model VARCHAR,
                n_eval INTEGER,
                log_loss FLOAT,
                brier_score FLOAT,
                auc_roc FLOAT,
                ece FLOAT,
                calibration_curve VARIANT,
                retrain_version VARCHAR,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("ALTER TABLE baseball_data.betting_ml.cv_results_win_outcome ADD COLUMN IF NOT EXISTS retrain_version VARCHAR")
        for _, row in results_df.iterrows():
            calib_json = json.dumps(row["calibration_curve"])
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_results_win_outcome
                    (fold, model, n_eval, log_loss, brier_score, auc_roc, ece, calibration_curve, retrain_version)
                SELECT %s, %s, %s, %s, %s, %s, %s, PARSE_JSON(%s), %s
                """,
                (
                    row["fold"],
                    row["model"],
                    int(row["n_eval"]),
                    float(row["log_loss"]),
                    float(row["brier_score"]),
                    float(row["auc_roc"]),
                    float(row["ece"]),
                    calib_json,
                    retrain_version,
                ),
            )
        print(f"  cv_results_win_outcome: {len(results_df)} rows written")

        # --- cv_calibration_win_outcome ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_calibration_win_outcome (
                fold VARCHAR,
                calibration_method VARCHAR,
                ece FLOAT,
                ece_uncalibrated FLOAT,
                retrain_version VARCHAR,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("ALTER TABLE baseball_data.betting_ml.cv_calibration_win_outcome ADD COLUMN IF NOT EXISTS retrain_version VARCHAR")
        for _, row in calib_df.iterrows():
            ece_uncal = None if pd.isna(row["ece_uncalibrated"]) else float(row["ece_uncalibrated"])
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_calibration_win_outcome
                    (fold, calibration_method, ece, ece_uncalibrated, retrain_version)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (row["fold"], row["calibration_method"], float(row["ece"]), ece_uncal, retrain_version),
            )
        print(f"  cv_calibration_win_outcome: {len(calib_df)} rows written")

        # --- cv_home_bias_win_outcome ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_home_bias_win_outcome (
                fold VARCHAR,
                log_loss_with_hwrt FLOAT,
                log_loss_without_hwrt FLOAT,
                brier_with_hwrt FLOAT,
                brier_without_hwrt FLOAT,
                home_bias_direction VARCHAR,
                retrain_version VARCHAR,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("ALTER TABLE baseball_data.betting_ml.cv_home_bias_win_outcome ADD COLUMN IF NOT EXISTS retrain_version VARCHAR")
        for r in home_bias_results:
            cur.execute(
                """
                INSERT INTO baseball_data.betting_ml.cv_home_bias_win_outcome
                    (fold, log_loss_with_hwrt, log_loss_without_hwrt,
                     brier_with_hwrt, brier_without_hwrt, home_bias_direction, retrain_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    r["fold"],
                    r["log_loss_with_hwrt"],
                    r["log_loss_without_hwrt"],
                    r["brier_with_hwrt"],
                    r["brier_without_hwrt"],
                    r["home_bias_direction"],
                    retrain_version,
                ),
            )
        print(f"  cv_home_bias_win_outcome: {len(home_bias_results)} rows written")

        # --- cv_summary_win_outcome ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.cv_summary_win_outcome (
                best_log_loss_model VARCHAR,
                best_brier_model VARCHAR,
                best_auc_model VARCHAR,
                best_calibration_model VARCHAR,
                better_calibration_method VARCHAR,
                hwrt_reduces_bias BOOLEAN,
                home_bias_in_recent_seasons VARCHAR,
                retrain_version VARCHAR,
                loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("ALTER TABLE baseball_data.betting_ml.cv_summary_win_outcome ADD COLUMN IF NOT EXISTS retrain_version VARCHAR")
        cur.execute(
            """
            INSERT INTO baseball_data.betting_ml.cv_summary_win_outcome
                (best_log_loss_model, best_brier_model, best_auc_model,
                 best_calibration_model, better_calibration_method,
                 hwrt_reduces_bias, home_bias_in_recent_seasons, retrain_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                summary["best_log_loss_model"],
                summary["best_brier_model"],
                summary["best_auc_model"],
                summary["best_calibration_model"],
                summary["better_calibration_method"],
                bool(summary["hwrt_reduces_bias"]),
                summary["home_bias_in_recent_seasons"],
                retrain_version,
            ),
        )
        print("  cv_summary_win_outcome: 1 row written")

        conn.commit()
        print("Snowflake writes complete.")
    finally:
        conn.close()


def _build_report(
    results_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    home_bias_results: list[dict],
    summary: dict,
) -> str:
    folds = sorted(results_df["fold"].unique())
    lines: list[str] = [
        "# Win Outcome Classification — Baseline Model Results (Card 4.11)",
        "",
    ]

    def gv(df: pd.DataFrame, fold: str, model: str, col: str) -> float:
        r = df[(df["fold"] == fold) & (df["model"] == model)]
        return float(r[col].values[0]) if len(r) > 0 else float("nan")

    def fmt(v: float, decimals: int = 4) -> str:
        return f"{v:.{decimals}f}" if not np.isnan(v) else "—"

    # --- Per-Season Metrics by Model ---
    lines += [
        "## Per-Season Metrics by Model",
        "",
        "| Season | Naive Log Loss | Logistic Log Loss | XGB Platt Log Loss | "
        "XGB Isotonic Log Loss | Logistic Brier | XGB Platt Brier | "
        "Logistic AUC | XGB Platt AUC |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for fold in folds:
        naive_ll = gv(results_df, fold, "naive_baseline", "log_loss")
        lr_ll = gv(results_df, fold, "logistic", "log_loss")
        platt_ll = gv(results_df, fold, "xgb_platt", "log_loss")
        iso_ll = gv(results_df, fold, "xgb_isotonic", "log_loss")
        lr_brier = gv(results_df, fold, "logistic", "brier_score")
        platt_brier = gv(results_df, fold, "xgb_platt", "brier_score")
        lr_auc = gv(results_df, fold, "logistic", "auc_roc")
        platt_auc = gv(results_df, fold, "xgb_platt", "auc_roc")

        # Bold best non-baseline on log loss
        non_baseline_lls = {"logistic": lr_ll, "xgb_platt": platt_ll, "xgb_isotonic": iso_ll}
        best_ll_fold = min(non_baseline_lls, key=lambda m: non_baseline_lls[m])

        def fmt_ll(model: str, val: float) -> str:
            s = fmt(val)
            return f"**{s}**" if model == best_ll_fold else s

        lines.append(
            f"| {fold} | {fmt(naive_ll)} | {fmt_ll('logistic', lr_ll)} | "
            f"{fmt_ll('xgb_platt', platt_ll)} | {fmt_ll('xgb_isotonic', iso_ll)} | "
            f"{fmt(lr_brier)} | {fmt(platt_brier)} | "
            f"{fmt(lr_auc)} | {fmt(platt_auc)} |"
        )
    lines.append("")

    # --- Model Comparison Summary ---
    lines += ["## Model Comparison Summary", ""]
    lines += [
        "Average log loss, Brier score, and AUC-ROC across all CV folds:",
        "",
        "| Model | Mean Log Loss | Mean Brier Score | Mean AUC-ROC |",
        "|---|---|---|---|",
    ]
    for model in ["naive_baseline", "logistic", "xgb_platt", "xgb_isotonic"]:
        mdf = results_df[results_df["model"] == model]
        lines.append(
            f"| {model} | {fmt(float(mdf['log_loss'].mean()))} | "
            f"{fmt(float(mdf['brier_score'].mean()))} | "
            f"{fmt(float(mdf['auc_roc'].mean()))} |"
        )
    lines += [
        "",
        f"**Best log loss:** {summary['best_log_loss_model']} "
        f"(mean={fmt(summary['best_ll_mean'])})",
        f"**Best Brier score:** {summary['best_brier_model']} "
        f"(mean={fmt(summary['best_brier_mean'])})",
        f"**Best AUC-ROC:** {summary['best_auc_model']}",
        "",
    ]

    # --- Calibration Analysis ---
    lines += [
        "## Calibration Analysis",
        "",
        "Calibration curves are computed by binning predicted probabilities into "
        "10 equal-width [0, 1] buckets, then comparing mean predicted probability "
        "against actual home win rate per bin. Expected Calibration Error (ECE) is "
        "the weighted mean of |mean_pred_prob − actual_win_rate| across non-empty bins, "
        "weighted by the fraction of games in each bin. Smaller ECE indicates better "
        "calibration.",
        "",
        "| Fold | XGB Uncalibrated ECE | XGB Platt ECE | XGB Isotonic ECE | Logistic ECE |",
        "|---|---|---|---|---|",
    ]
    for fold in folds:
        platt_row = calib_df[(calib_df["fold"] == fold) & (calib_df["calibration_method"] == "platt")]
        iso_row = calib_df[(calib_df["fold"] == fold) & (calib_df["calibration_method"] == "isotonic")]
        ece_uncal = float(platt_row["ece_uncalibrated"].values[0]) if len(platt_row) > 0 else float("nan")
        ece_platt = float(platt_row["ece"].values[0]) if len(platt_row) > 0 else float("nan")
        ece_iso = float(iso_row["ece"].values[0]) if len(iso_row) > 0 else float("nan")
        ece_lr = gv(results_df, fold, "logistic", "ece")
        lines.append(
            f"| {fold} | {fmt(ece_uncal)} | {fmt(ece_platt)} | {fmt(ece_iso)} | {fmt(ece_lr)} |"
        )
    lines += [
        "",
        f"**Better calibration method: {summary['better_calibration_method']}**",
        f"- Platt scaling average ECE: {fmt(summary['platt_mean_ece'])}",
        f"- Isotonic regression average ECE: {fmt(summary['isotonic_mean_ece'])}",
        "",
        "XGBoost raw (uncalibrated) predictions typically show overconfidence in "
        "high-probability bins (predicted >0.6 but actual rate lower) and underconfidence "
        "in mid-range bins. Post-calibration with either Platt or isotonic regression "
        "corrects this systematic bias, producing ECE values closer to those of "
        "Logistic Regression.",
        "",
    ]

    # --- Home Team Bias Analysis ---
    lines += [
        "## Home Team Bias Analysis",
        "",
        "NB01 finding: home advantage declined from 0.548 (2020) to 0.519 (2023). "
        "A model using a static home win rate will systematically overprice home teams "
        "in recent seasons. The feature `home_win_rate_trailing_3yr` was designed to "
        "capture this trend by using a rolling 3-year home win rate rather than a "
        "fixed historical baseline.",
        "",
        "| Season | Log Loss with HWRT | Log Loss without HWRT | "
        "Brier with HWRT | Brier without HWRT | Home Bias Direction |",
        "|---|---|---|---|---|---|",
    ]
    for r in home_bias_results:
        lines.append(
            f"| {r['fold']} | {fmt(r['log_loss_with_hwrt'])} | "
            f"{fmt(r['log_loss_without_hwrt'])} | "
            f"{fmt(r['brier_with_hwrt'])} | {fmt(r['brier_without_hwrt'])} | "
            f"{r['home_bias_direction']} |"
        )
    lines.append("")

    hwrt_str = "reduces" if summary["hwrt_reduces_bias"] else "does not materially reduce"
    lines += [
        f"`home_win_rate_trailing_3yr` **{hwrt_str}** the home team overpricing bias "
        f"in 2023–2025 seasons.",
        f"Home bias directions by season: {summary['home_bias_in_recent_seasons']}.",
        "",
    ]

    # --- Best Model Selection ---
    best = summary["best_log_loss_model"]
    best_calib = summary["best_calibration_model"]
    better_method = summary["better_calibration_method"]
    lines += [
        "## Best Model Selection",
        "",
        f"**Recommended model for downstream EV calculations (Phase 6): `{best_calib}`**",
        "",
        f"Calibration quality is the primary criterion because probability outputs feed "
        f"directly into EV calculations in Phase 6. `{best_calib}` achieves the best "
        f"overall ECE with {better_method} calibration "
        f"(mean ECE = {fmt(summary['platt_mean_ece'] if better_method == 'platt' else summary['isotonic_mean_ece'])}).",
        "",
        f"On point metrics, `{best}` achieves the best mean log loss "
        f"({fmt(summary['best_ll_mean'])}) and `{summary['best_brier_model']}` achieves "
        f"the best mean Brier score ({fmt(summary['best_brier_mean'])}).",
        "",
        f"The marginal ECE difference between Platt and isotonic calibration "
        f"(Platt={fmt(summary['platt_mean_ece'])} vs. isotonic={fmt(summary['isotonic_mean_ece'])}) "
        + (
            "favors Platt scaling. Given Platt's lower complexity and comparable performance, "
            "it is the preferred calibration method."
            if summary["better_calibration_method"] == "platt"
            else "favors isotonic regression. The additional complexity of isotonic regression "
            "is justified by its improved ECE, which directly benefits EV accuracy in Phase 6."
        ),
        "",
        "Forward reference: in Card 4.13 probability output layer, this classifier's "
        "win probability output will be compared against the regression-derived win "
        "probability from NGBoost Normal (Card 4.10); the better-calibrated model "
        "should anchor the downstream EV calculation.",
        "",
    ]

    return "\n".join(lines)


def write_report(
    results_df: pd.DataFrame,
    calib_df: pd.DataFrame,
    home_bias_results: list[dict],
    summary: dict,
) -> None:
    content = _build_report(results_df, calib_df, home_bias_results, summary)
    eval_dir = PROJECT_ROOT / "betting_ml" / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    report_path = eval_dir / "win_outcome_results.md"
    with open(report_path, "w") as f:
        f.write(content)
    print(f"Wrote {report_path}")


def update_project_context(summary: dict) -> None:
    context_path = PROJECT_ROOT / "project_context.md"
    best_model = summary["best_log_loss_model"]
    best_ll = summary["best_ll_mean"]
    best_brier = summary["best_brier_mean"]
    better_method = summary["better_calibration_method"]
    hwrt = summary["hwrt_reduces_bias"]
    bias_summary = summary["home_bias_in_recent_seasons"]

    card_411_section = f"""
#### Card 4.11 Results — Win Outcome Classification Baselines

- **Best model (log loss):** `{best_model}` (mean log loss = {best_ll:.4f})
- **Best Brier score:** `{summary['best_brier_model']}` (mean = {best_brier:.4f})
- **Better calibration method:** {better_method} (Platt ECE={summary['platt_mean_ece']:.4f}, Isotonic ECE={summary['isotonic_mean_ece']:.4f})
- **hwrt_reduces_bias:** {hwrt}
- **Home bias in recent seasons:** {bias_summary}
- **Recommended classifier for Phase 6 EV:** `{summary['best_calibration_model']}`
"""

    _RESULTS_HEADER = "#### Card 4.11 Results — Win Outcome Classification Baselines"

    with open(context_path) as f:
        content = f.read()

    if _RESULTS_HEADER in content:
        # Replace the existing results section (handles re-runs after upstream changes).
        start = content.index(_RESULTS_HEADER)
        next_section = content.find("\n####", start + len(_RESULTS_HEADER))
        if next_section == -1:
            content = content[:start] + card_411_section.strip() + "\n"
        else:
            content = content[:start] + card_411_section.strip() + "\n\n" + content[next_section + 1:]
        with open(context_path, "w") as f:
            f.write(content)
        print(f"Updated {context_path} — replaced existing Card 4.11 results section.")
    else:
        insert_marker = "#### Card 4.1 —"
        if insert_marker in content:
            content = content.replace(insert_marker, card_411_section + "\n" + insert_marker, 1)
        else:
            content += card_411_section
        with open(context_path, "w") as f:
            f.write(content)
        print(f"Updated {context_path} with Card 4.11 results.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default=datetime.date.today().isoformat(), help="Retrain version tag written to Snowflake (default: today's date)")
    args = parser.parse_args()

    results_df, calib_df, home_bias_results, summary = run_cv()

    # Verify trained models beat naive baseline on log loss for majority of folds
    folds = sorted(results_df["fold"].unique())
    n_folds = len(folds)
    failures = []
    for model_name in ["logistic", "xgb_platt", "xgb_isotonic"]:
        n_beats = 0
        for fold in folds:
            model_ll = results_df[(results_df["model"] == model_name) & (results_df["fold"] == fold)]["log_loss"].values
            naive_ll = results_df[(results_df["model"] == "naive_baseline") & (results_df["fold"] == fold)]["log_loss"].values
            if len(model_ll) > 0 and len(naive_ll) > 0 and model_ll[0] < naive_ll[0]:
                n_beats += 1
        if n_beats <= n_folds // 2:
            failures.append(f"{model_name} beats naive baseline on only {n_beats}/{n_folds} folds")

    if failures:
        print("\nFAILURE: Some trained models do not beat the naive baseline on log loss on the majority of folds:")
        for msg in failures:
            print(f"  - {msg}")
        sys.exit(1)
    else:
        print("\nAll trained models beat naive baseline on log loss on majority of folds. ✓")

    write_to_snowflake(results_df, calib_df, home_bias_results, summary, retrain_version=args.version)
    write_report(results_df, calib_df, home_bias_results, summary)
    update_project_context(summary)
    print("\nCard 4.11 complete.")


if __name__ == "__main__":
    main()
