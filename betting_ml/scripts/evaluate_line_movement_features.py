"""Card 7.P3 — Line movement feature CV impact evaluation.

Compares XGBoost home_win Brier score with and without the four line movement
features added in Card 7.P3. Writes betting_ml/evaluation/line_movement_feature_impact.md.

Does NOT replace the production model. Full retrain is deferred to Card 7.MA.

Usage:
    uv run python betting_ml/scripts/evaluate_line_movement_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

_REPORT_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "line_movement_feature_impact.md"

LINE_MOVEMENT_FEATURES = [
    "home_h2h_line_movement",
    "home_open_win_prob",
    "total_line_movement",
    "open_total_line",
]

TARGET = "home_win"

XGB_PARAMS = {
    "max_depth": 5,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "eval_metric": "logloss",
    "tree_method": "hist",
    "random_state": 42,
    "n_jobs": -1,
}


def _run_cv(df: pd.DataFrame, feature_cols: list[str]) -> tuple[float, float]:
    """Return (mean_brier, mean_h2h_edge) across all season-forward folds."""
    briers = []
    edges = []

    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        y_train = df.loc[train_idx, TARGET].astype(int)
        y_eval = df.loc[eval_idx, TARGET].astype(int)

        pipeline = build_imputation_pipeline()
        X_train_raw = df.loc[train_idx, feature_cols]
        X_eval_raw = df.loc[eval_idx, feature_cols]

        X_train_imp = pipeline.fit_transform(X_train_raw)
        X_eval_imp = pipeline.transform(X_eval_raw)

        X_train_num = X_train_imp.select_dtypes(include=[np.number])
        X_eval_num = X_eval_imp.reindex(columns=X_train_num.columns, fill_value=0.0)

        clf = XGBClassifier(**XGB_PARAMS)
        clf.fit(X_train_num, y_train)

        y_raw = clf.predict_proba(X_eval_num)[:, 1]
        cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        cal.fit(y_raw.reshape(-1, 1), np.asarray(y_eval))
        y_cal = cal.predict_proba(y_raw.reshape(-1, 1))[:, 1]

        briers.append(float(brier_score_loss(y_eval, y_cal)))

        # h2h edge: only on rows that have odds (home_implied_prob non-null)
        eval_df = df.loc[eval_idx].copy()
        eval_df["pred_prob"] = y_cal
        has_odds = eval_df["home_implied_prob"].notna()
        if has_odds.sum() > 0:
            edges.append(
                float((eval_df.loc[has_odds, "pred_prob"] - eval_df.loc[has_odds, "home_implied_prob"]).mean())
            )

    return float(np.mean(briers)), float(np.mean(edges)) if edges else float("nan")


def _compute_shap_importance(df: pd.DataFrame, feature_cols: list[str]) -> pd.Series:
    """Train on all data and compute mean |SHAP| per feature."""
    try:
        import shap
    except ImportError:
        return pd.Series(dtype=float)

    pipeline = build_imputation_pipeline()
    X_raw = df[feature_cols]
    X_imp = pipeline.fit_transform(X_raw)
    X_num = X_imp.select_dtypes(include=[np.number])
    y = df[TARGET].astype(int)

    clf = XGBClassifier(**XGB_PARAMS)
    clf.fit(X_num, y)

    explainer = shap.TreeExplainer(clf)
    shap_values = explainer.shap_values(X_num)

    return pd.Series(
        np.abs(shap_values).mean(axis=0),
        index=X_num.columns,
    ).sort_values(ascending=False)


def _check_correlations(df: pd.DataFrame, candidates: list[str]) -> dict[str, float]:
    """Return Pearson |r| with home_win for each candidate column."""
    result = {}
    for col in candidates:
        if col in df.columns:
            r = df[col].corr(df[TARGET])
            result[col] = round(float(r) if not np.isnan(r) else 0.0, 4)
    return result


def main() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].unique())}")

    retained = load_retained_features()
    base_features = [f for f in retained if f in df.columns]
    missing_retained = [f for f in retained if f not in df.columns]
    if missing_retained:
        print(f"  WARNING: {len(missing_retained)} retained features absent: {missing_retained[:5]}")
    print(f"  Baseline feature count: {len(base_features)}")

    # Check which line movement features are present in the loaded data
    present_lm = [f for f in LINE_MOVEMENT_FEATURES if f in df.columns]
    absent_lm = [f for f in LINE_MOVEMENT_FEATURES if f not in df.columns]
    if absent_lm:
        print(f"  WARNING: line movement features not in DataFrame: {absent_lm}")
    print(f"  Line movement features present: {present_lm}")

    # Correlation filter check (r >= 0.02 threshold)
    print("\nChecking correlations with home_win...")
    corrs = _check_correlations(df, LINE_MOVEMENT_FEATURES)
    survived_corr = {k: v for k, v in corrs.items() if abs(v) >= 0.02}
    dropped_corr = {k: v for k, v in corrs.items() if abs(v) < 0.02}
    print(f"  Survived (|r| >= 0.02): {list(survived_corr.keys())}")
    print(f"  Dropped  (|r| <  0.02): {list(dropped_corr.keys())}")

    # CV: baseline (retained features only)
    print("\nRunning baseline CV (retained features, no line movement)...")
    base_brier, base_edge = _run_cv(df, base_features)
    print(f"  Baseline Brier: {base_brier:.4f}  Mean h2h edge: {base_edge:.4f}")

    # CV: with line movement features appended
    lm_features = base_features + [f for f in present_lm if f not in base_features]
    print(f"\nRunning CV with {len(present_lm)} line movement features added...")
    lm_brier, lm_edge = _run_cv(df, lm_features)
    print(f"  With lm  Brier: {lm_brier:.4f}  Mean h2h edge: {lm_edge:.4f}")

    brier_delta = lm_brier - base_brier
    edge_delta = lm_edge - base_edge
    print(f"\n  Brier delta: {brier_delta:+.4f}  ({'improved' if brier_delta < 0 else 'regressed'})")
    print(f"  Edge delta:  {edge_delta:+.4f}")

    # SHAP importance on model with line movement
    print("\nComputing SHAP feature importance (top 20)...")
    shap_importance = _compute_shap_importance(df, lm_features)
    top20 = shap_importance.head(20)
    if shap_importance.empty:
        print("  shap not installed — skipping SHAP analysis")

    # Recommendation
    lm_h2h_shap = shap_importance.get("home_h2h_line_movement", 0.0)
    recommendation = (
        "INCLUDE in production model"
        if (brier_delta <= 0.001 and abs(corrs.get("home_h2h_line_movement", 0)) >= 0.02)
        else "EXCLUDE pending Card 7.MA full retrain"
    )

    # Write report
    lines = [
        "# Line Movement Feature Impact Report",
        "",
        "**Card:** 7.P3 — Line Movement Feature Engineering",
        f"**Date:** 2026-05-03",
        "",
        "---",
        "",
        "## Feature Selection: Correlation with home_win",
        "",
        "Threshold: |r| ≥ 0.02",
        "",
        "| Feature | Pearson r | Survived? |",
        "|---|---|---|",
    ]
    for feat in LINE_MOVEMENT_FEATURES:
        r = corrs.get(feat, float("nan"))
        survived = "✓" if abs(r) >= 0.02 else "✗"
        lines.append(f"| `{feat}` | {r:.4f} | {survived} |")

    lines += [
        "",
        "---",
        "",
        "## CV Brier Score: Baseline vs. With Line Movement",
        "",
        "Method: XGBoost + Platt calibration, season-forward CV (min 3 train seasons).",
        "Hyperparameters: fixed at representative values (not tuned — full grid search at Card 7.MA).",
        "",
        "| Model | Mean Brier | Mean h2h edge (has_odds rows) |",
        "|---|---|---|",
        f"| Baseline (retained features) | {base_brier:.4f} | {base_edge:.4f} |",
        f"| +line movement features      | {lm_brier:.4f} | {lm_edge:.4f} |",
        f"| Delta                        | {brier_delta:+.4f} | {edge_delta:+.4f} |",
        "",
    ]

    if brier_delta < 0:
        lines.append(f"Brier improved by {abs(brier_delta):.4f} with line movement features.")
    elif brier_delta <= 0.001:
        lines.append(f"Brier essentially unchanged (+{brier_delta:.4f}) — line movement features add no harm.")
    else:
        lines.append(f"Brier regressed by {brier_delta:.4f} — line movement features may add noise.")

    lines += ["", "---", "", "## SHAP Top-20 Feature Importance", ""]

    if not shap_importance.empty:
        lines += [
            "| Rank | Feature | Mean |SHAP| |",
            "|---|---|---|",
        ]
        for rank, (feat, val) in enumerate(top20.items(), 1):
            marker = " ← **line movement**" if feat in LINE_MOVEMENT_FEATURES else ""
            lines.append(f"| {rank} | `{feat}` | {val:.4f} |{marker}")
        lines.append("")
        lines.append(f"`home_h2h_line_movement` mean |SHAP|: {lm_h2h_shap:.4f}")
    else:
        lines += [
            "_SHAP analysis skipped (shap package not installed)._",
            "",
            "Install with: `uv add shap` then rerun this script.",
        ]

    lines += [
        "",
        "---",
        "",
        "## Recommendation",
        "",
        f"**{recommendation}**",
        "",
        "Rationale:",
    ]

    for feat, r in corrs.items():
        if abs(r) >= 0.02:
            lines.append(f"- `{feat}` passed correlation filter (r = {r:.4f})")
        else:
            lines.append(f"- `{feat}` did NOT pass correlation filter (r = {r:.4f})")

    lines += [
        "",
        "Note: Full model retrain with all Phase 7 features is deferred to Card 7.MA.",
        "This evaluation uses fixed hyperparameters and should be interpreted as directional only.",
    ]

    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nReport written to {_REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
