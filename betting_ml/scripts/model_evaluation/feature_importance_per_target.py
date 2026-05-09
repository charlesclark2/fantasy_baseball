"""8.W per-target feature importance analysis on production artifacts.

home_win:        Extract top-20 elasticnet coefficient magnitudes (standardized
                 space) from the production Pipeline artifact.
total_runs:      Permutation importance on production NGBoost artifact using
                 2025 held-out games as the test set.
run_differential: Same as total_runs.

Outputs (betting_ml/evaluation/feature_selection/):
    home_win_top20_importances.txt
    total_runs_feature_importance.txt
    run_diff_feature_importance.txt

Usage:
    uv run python betting_ml/scripts/model_evaluation/feature_importance_per_target.py
    uv run python betting_ml/scripts/model_evaluation/feature_importance_per_target.py --target home_win
    uv run python betting_ml/scripts/model_evaluation/feature_importance_per_target.py --target total_runs
    uv run python betting_ml/scripts/model_evaluation/feature_importance_per_target.py --target run_diff
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features

# ---------------------------------------------------------------------------
# Phase 8 feature origin patterns
# ---------------------------------------------------------------------------
_PHASE8_PATTERNS: dict[str, list[str]] = {
    "8.A": ["_pct_diff"],
    "8.B": ["proj_fip", "trailing_fip_30g", "fip_ra9_gap"],
    "8.C": ["oaa_blended"],
    "8.D": ["_elo", "elo_diff"],
    "8.E": ["bat_speed", "swing_length", "attack_angle", "bat_tracking"],
    "8.J": ["h2h_woba", "h2h_xwoba", "h2h_pa_coverage"],
    "8.K": ["catcher_framing", "catcher_defensive"],
    "8.L": ["bp_matchup_xwoba"],
    "8.M": ["arsenal_drift"],
    "8.Q": ["csw_pct"],
    "8.R": ["pct_home_ml", "pct_away_ml", "ml_sharp_signal", "total_sharp_signal",
            "has_public_betting"],
    "8.T": ["ml_implied_prob_std", "ml_implied_prob_range", "sharp_soft_ml_spread",
            "n_books_available", "stale_book_flag", "totals_line_std", "totals_line_range"],
    "8.U": ["bp_leverage_sum", "bp_high_lev_appearances"],
    "8.X": ["pythagorean_residual", "pyth_residual"],
    "8.Y": ["base_state", "woba_splits", "xwoba_splits", "sequencing"],
}


def _phase8_origin(col: str) -> str:
    for card, patterns in _PHASE8_PATTERNS.items():
        if any(p in col for p in patterns):
            return card
    return "legacy"


# ---------------------------------------------------------------------------
# home_win: elasticnet coefficients
# ---------------------------------------------------------------------------

def analyze_home_win(out_dir: Path) -> None:
    print("\n=== home_win: elasticnet coefficient magnitudes ===")

    model_path = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_2026.pkl"
    feat_path  = PROJECT_ROOT / "betting_ml" / "models" / "home_win" / "elasticnet_feature_columns.json"

    pipeline  = joblib.load(model_path)
    feat_cols = json.loads(feat_path.read_text())
    coef      = pipeline.named_steps["clf"].coef_[0]

    # SimpleImputer silently drops all-NaN columns; resolve to the kept subset.
    if len(coef) != len(feat_cols):
        imputer = pipeline.named_steps.get("impute") or pipeline.named_steps.get("imputer")
        if imputer is not None and hasattr(imputer, "get_feature_names_out"):
            kept = list(imputer.get_feature_names_out(feat_cols))
            dropped = [c for c in feat_cols if c not in set(kept)]
            print(f"  NOTE: imputer dropped {len(dropped)} all-NaN columns: {dropped}")
            feat_cols = kept
        if len(coef) != len(feat_cols):
            raise ValueError(f"Coefficient length {len(coef)} != feature list length {len(feat_cols)}")

    df = pd.DataFrame({
        "feature":       feat_cols,
        "coefficient":   coef,
        "abs_coef":      np.abs(coef),
        "phase8_origin": [_phase8_origin(c) for c in feat_cols],
    }).sort_values("abs_coef", ascending=False).reset_index(drop=True)

    top20      = df.head(20)
    n_nonzero  = (df["abs_coef"] > 0).sum()
    n_phase8   = (df["phase8_origin"] != "legacy").sum()
    top20_p8   = top20[top20["phase8_origin"] != "legacy"]

    print(f"Total features: {len(df)} | Non-zero coef: {n_nonzero} | Phase 8 features: {n_phase8}")
    print(f"Phase 8 features in top-20: {len(top20_p8)}")
    print(f"\n{'Rank':<5} {'Feature':<55} {'Coefficient':>12} {'Origin'}")
    print("-" * 85)
    for i, row in top20.iterrows():
        marker = " *" if row["phase8_origin"] != "legacy" else ""
        print(f"{i+1:<5} {row['feature']:<55} {row['coefficient']:>+12.4f}  {row['phase8_origin']}{marker}")

    # Write report
    lines = [
        "home_win — elasticnet top-20 feature coefficients (standardized space)",
        f"Model: {model_path.name}  |  Features: {len(df)}  |  Non-zero: {n_nonzero}  |  Phase 8: {n_phase8}",
        f"Phase 8 features in top-20: {len(top20_p8)}",
        "",
        "TOP 20 (largest |coefficient| — most influential):",
        f"{'Rank':<5} {'Feature':<55} {'Coefficient':>12} {'Origin'}",
        "-" * 85,
    ]
    for i, row in top20.iterrows():
        marker = " *" if row["phase8_origin"] != "legacy" else ""
        lines.append(f"{i+1:<5} {row['feature']:<55} {row['coefficient']:>+12.4f}  {row['phase8_origin']}{marker}")

    bottom20 = df.tail(20).reset_index(drop=True)
    lines += [
        "",
        "BOTTOM 20 (smallest |coefficient| — exclusion candidates for next retrain):",
        f"{'Rank':<5} {'Feature':<55} {'Coefficient':>12} {'Origin'}",
        "-" * 85,
    ]
    for i, row in bottom20.iterrows():
        rank = len(df) - 19 + i
        lines.append(f"{rank:<5} {row['feature']:<55} {row['coefficient']:>+12.4f}  {row['phase8_origin']}")

    zero_coef = df[df["abs_coef"] == 0.0]
    if len(zero_coef):
        lines += [
            "",
            f"ZERO-COEFFICIENT FEATURES ({len(zero_coef)} — l1 penalty pruned entirely):",
        ]
        for _, row in zero_coef.iterrows():
            lines.append(f"  {row['feature']}  ({row['phase8_origin']})")

    out_path = out_dir / "home_win_top20_importances.txt"
    out_path.write_text("\n".join(lines))
    print(f"\nSaved → {out_path}")


# ---------------------------------------------------------------------------
# NGBoost permutation importance
# ---------------------------------------------------------------------------

def _load_2025_test_data(feat_cols: list[str], target_col: str) -> tuple[np.ndarray, np.ndarray]:
    print("  Loading 2025 held-out test data from Snowflake…")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] == 2025].reset_index(drop=True)
    print(f"  2025 rows: {len(df)}")

    missing = [c for c in feat_cols if c not in df.columns]
    if missing:
        print(f"  WARNING: {len(missing)} feature columns missing from loaded data — imputing 0.0")
        for c in missing:
            df[c] = 0.0

    valid_mask = df[target_col].notna()
    X = df.loc[valid_mask, feat_cols].fillna(0.0).values.astype(np.float32)
    y = df.loc[valid_mask, target_col].values.astype(np.float32)
    print(f"  Valid rows for '{target_col}': {len(X)}")
    return X, y


def _run_perm_importance(
    model_path: Path,
    feat_path:  Path,
    target_col: str,
    out_path:   Path,
    label:      str,
    n_repeats:  int = 10,
) -> None:
    print(f"\n=== {label}: permutation importance (n_repeats={n_repeats}) ===")

    model     = joblib.load(model_path)
    feat_cols = json.loads(feat_path.read_text())
    X, y      = _load_2025_test_data(feat_cols, target_col)

    # Baseline MAE before any permutation
    y_pred_base = model.predict(X)
    baseline_mae = float(np.mean(np.abs(y_pred_base - y)))
    print(f"  Baseline MAE on 2025 test set: {baseline_mae:.4f}")

    def neg_mae_scorer(est, X_, y_):
        return -float(np.mean(np.abs(est.predict(X_) - y_)))

    print(f"  Running permutation importance ({len(feat_cols)} features × {n_repeats} repeats)…")
    result = permutation_importance(
        model, X, y,
        scoring=neg_mae_scorer,
        n_repeats=n_repeats,
        random_state=42,
        n_jobs=-1,
    )

    imp_mean = result.importances_mean   # positive = hurts MAE when shuffled = important
    imp_std  = result.importances_std
    ci_lower = imp_mean - imp_std

    df_imp = pd.DataFrame({
        "feature":        feat_cols,
        "mean_imp":       imp_mean,
        "std_imp":        imp_std,
        "ci_lower":       ci_lower,
        "phase8_origin":  [_phase8_origin(c) for c in feat_cols],
    }).sort_values("mean_imp", ascending=False).reset_index(drop=True)

    # Exclusion candidate: shuffling doesn't hurt (or helps) model — feature is noise
    df_imp["exclude_candidate"] = (df_imp["mean_imp"] <= 0) | (df_imp["ci_lower"] < -0.001)

    n_exclude  = int(df_imp["exclude_candidate"].sum())
    n_phase8   = int((df_imp["phase8_origin"] != "legacy").sum())
    p8_exclude = df_imp[(df_imp["phase8_origin"] != "legacy") & df_imp["exclude_candidate"]]

    print(f"\n  Total features: {len(df_imp)} | Exclusion candidates: {n_exclude} | Phase 8 features: {n_phase8}")
    print(f"  Phase 8 exclusion candidates: {len(p8_exclude)}")

    print(f"\n{'Rank':<5} {'Feature':<52} {'Mean':>9} {'Std':>8} {'CI Lo':>9} {'Origin':<10} {'Excl?'}")
    print("-" * 105)
    for i, row in df_imp.head(20).iterrows():
        flag   = "X" if row["exclude_candidate"] else ""
        marker = " *" if row["phase8_origin"] != "legacy" else ""
        print(f"{i+1:<5} {row['feature']:<52} {row['mean_imp']:>9.5f} {row['std_imp']:>8.5f} "
              f"{row['ci_lower']:>9.5f}  {row['phase8_origin']:<10}{marker} {flag}")

    if len(p8_exclude):
        print(f"\n  Phase 8 features flagged for exclusion:")
        for _, row in p8_exclude.iterrows():
            print(f"    {row['feature']}  ({row['phase8_origin']})  mean={row['mean_imp']:.5f}")
    else:
        print("\n  No Phase 8 features flagged as exclusion candidates.")

    # Write report
    lines = [
        f"{label} — permutation importance on 2025 held-out test set",
        f"Model: {model_path.name}  |  Test rows: {len(X)}  |  n_repeats={n_repeats}",
        f"Baseline MAE: {baseline_mae:.4f}",
        f"Total features: {len(df_imp)} | Exclusion candidates: {n_exclude} | Phase 8 features: {n_phase8}",
        "",
        "TOP 20 features by mean permutation importance (larger = shuffling hurts more = important):",
        f"{'Rank':<5} {'Feature':<52} {'Mean Imp':>10} {'Std':>8} {'CI Lower':>10} {'Origin':<10} {'Excl?'}",
        "-" * 105,
    ]
    for i, row in df_imp.head(20).iterrows():
        flag   = "EXCLUDE" if row["exclude_candidate"] else ""
        marker = " *" if row["phase8_origin"] != "legacy" else ""
        lines.append(
            f"{i+1:<5} {row['feature']:<52} {row['mean_imp']:>10.5f} {row['std_imp']:>8.5f} "
            f"{row['ci_lower']:>10.5f}  {row['phase8_origin']:<10}{marker} {flag}"
        )

    lines += [
        "",
        f"EXCLUSION CANDIDATES (mean_imp ≤ 0 or ci_lower < −0.001)  — {n_exclude} total:",
        f"{'Feature':<52} {'Mean Imp':>10} {'Std':>8} {'Origin'}",
        "-" * 80,
    ]
    for _, row in df_imp[df_imp["exclude_candidate"]].iterrows():
        lines.append(
            f"{row['feature']:<52} {row['mean_imp']:>10.5f} {row['std_imp']:>8.5f}  {row['phase8_origin']}"
        )

    if len(p8_exclude):
        lines += [
            "",
            f"PHASE 8 EXCLUSION CANDIDATES ({len(p8_exclude)}) — consider dropping from next retrain:",
        ]
        for _, row in p8_exclude.iterrows():
            lines.append(f"  {row['feature']}  ({row['phase8_origin']})  mean={row['mean_imp']:.5f}")

    out_path.write_text("\n".join(lines))
    print(f"\n  Saved → {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["home_win", "total_runs", "run_diff", "all"],
        default="all",
        help="Which target to analyze (default: all)",
    )
    parser.add_argument(
        "--n-repeats", type=int, default=10,
        help="Permutation importance repeats for NGBoost targets (default: 10)",
    )
    args = parser.parse_args()

    out_dir = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.target in ("home_win", "all"):
        analyze_home_win(out_dir)

    if args.target in ("total_runs", "all"):
        _run_perm_importance(
            model_path = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "ngboost_decay_weighted.pkl",
            feat_path  = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "feature_columns_v2.json",
            target_col = "total_runs",
            out_path   = out_dir / "total_runs_feature_importance.txt",
            label      = "total_runs",
            n_repeats  = args.n_repeats,
        )

    if args.target in ("run_diff", "all"):
        _run_perm_importance(
            model_path = PROJECT_ROOT / "betting_ml" / "models" / "run_differential" / "ngboost_tuned_2026.pkl",
            feat_path  = PROJECT_ROOT / "betting_ml" / "models" / "feature_columns.json",
            target_col = "run_differential",
            out_path   = out_dir / "run_diff_feature_importance.txt",
            label      = "run_differential",
            n_repeats  = args.n_repeats,
        )

    print("\n=== Per-target feature importance analysis complete ===")


if __name__ == "__main__":
    main()
