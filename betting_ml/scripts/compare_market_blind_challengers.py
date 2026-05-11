"""Epic 1 — Offline champion-vs-challenger comparison for market-blind retrains.

Loads the 2024+ feature window from Snowflake, runs both the production champion
and the Epic 1 market-blind challenger for each target, and prints side-by-side
metrics.  No writes to Snowflake or daily_model_predictions.

Key metrics
-----------
  home_win      Brier score, AVG(pred_prob) vs AVG(actual_win_rate)
  total_runs    MAE, AVG(pred) vs AVG(actual), Pct_Pred_Over_Line (directional bias)
  run_diff      MAE, AVG(pred) vs AVG(actual)

The directional bias check for total_runs is the most important gate here.
A healthy model should predict over the consensus line on 25–75% of games.
Values near 0% or 100% indicate systematic bias regardless of MAE.

Usage
-----
    uv run python betting_ml/scripts/compare_market_blind_challengers.py
    uv run python betting_ml/scripts/compare_market_blind_challengers.py --start-year 2025
    uv run python betting_ml/scripts/compare_market_blind_challengers.py --target total_runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from betting_ml.utils.data_loader import load_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

# ---------------------------------------------------------------------------
# Artifact + feature-column paths
# ---------------------------------------------------------------------------

_MODELS = PROJECT_ROOT / "betting_ml" / "models"

_CONFIGS: dict[str, dict] = {
    "home_win": {
        "champion_artifact":   _MODELS / "home_win" / "elasticnet_2026.pkl",
        "challenger_artifact": _MODELS / "home_win" / "elasticnet_market_blind_2026.pkl",
        "champion_cols":       _MODELS / "home_win" / "elasticnet_feature_columns.json",
        "challenger_cols":     _MODELS / "home_win" / "feature_columns_market_blind.json",
        "model_type":          "elasticnet",
        "target_col":          "home_win",
        "champ_label":         "v1",
        "chall_label":         "v2 (market-blind)",
    },
    "total_runs": {
        "champion_artifact":   _MODELS / "total_runs" / "ngboost_decay_weighted.pkl",
        "challenger_artifact": _MODELS / "total_runs" / "ngboost_market_blind_2026.pkl",
        "champion_cols":       _MODELS / "total_runs" / "feature_columns_v2.json",
        "challenger_cols":     _MODELS / "total_runs" / "feature_columns_market_blind.json",
        "model_type":          "ngboost",
        "target_col":          "total_runs",
        "champ_label":         "v2",
        "chall_label":         "v3 (market-blind)",
    },
    "run_differential": {
        "champion_artifact":   _MODELS / "run_differential" / "ngboost_tuned_2026.pkl",
        "challenger_artifact": _MODELS / "run_differential" / "ngboost_market_blind_2026.pkl",
        "champion_cols":       _MODELS / "feature_columns.json",
        "challenger_cols":     _MODELS / "run_differential" / "feature_columns_market_blind.json",
        "model_type":          "ngboost",
        "target_col":          "run_differential",
        "champ_label":         "v1",
        "chall_label":         "v2 (market-blind)",
    },
}

# Directional bias thresholds for total_runs pct_pred_over_line
_BIAS_LOW  = 25.0
_BIAS_HIGH = 75.0


# ---------------------------------------------------------------------------
# Prediction helpers
# ---------------------------------------------------------------------------

def _predict_elasticnet(
    model,
    feature_cols: list[str],
    df: pd.DataFrame,
) -> np.ndarray:
    """Run inference through a sklearn Pipeline (impute + scale + LR)."""
    X = df.reindex(columns=feature_cols, fill_value=0.0).values.astype(np.float32)
    return model.predict_proba(X)[:, 1]


def _predict_ngboost(
    model,
    df_transformed: pd.DataFrame,
    feature_cols: list[str],
) -> np.ndarray:
    """Run inference on a pre-transformed DataFrame using saved feature column list."""
    X = df_transformed.reindex(columns=feature_cols, fill_value=0.0).values
    return model.predict(X)


# ---------------------------------------------------------------------------
# Per-target comparison
# ---------------------------------------------------------------------------

def _fmt(v: float | None, d: int = 4) -> str:
    return f"{v:.{d}f}" if v is not None else "—"


def _print_row(label: str, v0: float | None, v1: float | None, d: int = 4) -> None:
    delta = (v1 - v0) if (v0 is not None and v1 is not None) else None
    delta_s = f"{delta:+.{d}f}" if delta is not None else "—"
    print(f"  {label:<28} {_fmt(v0, d):>12} {_fmt(v1, d):>16} {delta_s:>10}")


def _compare_home_win(
    df: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
    chall_cols: list[str],
    champ_label: str,
    chall_label: str,
) -> str:
    mask = df["home_win"].notna()
    sub = df[mask].copy()

    p_champ = _predict_elasticnet(champ_model, champ_cols, sub)
    p_chall = _predict_elasticnet(chall_model, chall_cols, sub)
    actual  = sub["home_win"].values.astype(float)

    brier_champ  = float(np.mean((actual - p_champ) ** 2))
    brier_chall  = float(np.mean((actual - p_chall) ** 2))
    delta_brier  = brier_chall - brier_champ

    hdr = f"  {'Metric':<28} {champ_label:>12} {chall_label:>16} {'Delta':>10}"
    print(f"\n{'='*68}")
    print(f"  home_win  (elasticnet)   n={len(sub):,}")
    print(hdr)
    print(f"  {'-'*68}")
    _print_row("Brier",         brier_champ, brier_chall)
    _print_row("AVG(pred_prob)",float(p_champ.mean()), float(p_chall.mean()))
    _print_row("AVG(actual)",   float(actual.mean()), None)

    if delta_brier <= 0:
        verdict = "PROMOTE — challenger Brier improves."
    elif delta_brier <= 0.002:
        verdict = f"PROMOTE WITH MONITORING — Brier +{delta_brier:.4f}, within 0.002 tolerance."
    else:
        verdict = f"DO NOT PROMOTE — Brier regresses {delta_brier:+.4f} (limit: +0.002)."
    print(f"\n  Verdict: {verdict}")
    return verdict


def _compare_total_runs(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
    chall_cols: list[str],
    champ_label: str,
    chall_label: str,
) -> str:
    mask = df["total_runs"].notna()
    sub = df[mask].copy()
    sub_t = df_transformed.loc[mask].copy()

    p_champ = _predict_ngboost(champ_model, sub_t, champ_cols)
    p_chall = _predict_ngboost(chall_model, sub_t, chall_cols)
    actual  = sub["total_runs"].values.astype(float)

    mae_champ = float(np.mean(np.abs(actual - p_champ)))
    mae_chall = float(np.mean(np.abs(actual - p_chall)))
    delta_mae = mae_chall - mae_champ

    # Directional bias — use total_line_consensus if available, else vs actual
    if "total_line_consensus" in df.columns and df.loc[mask, "total_line_consensus"].notna().mean() > 0.5:
        line = df.loc[mask, "total_line_consensus"].fillna(float(actual.mean())).values
        pct_over_champ = float((p_champ > line).mean() * 100)
        pct_over_chall = float((p_chall > line).mean() * 100)
        bias_label = "Pct_Pred_Over_Line"
    else:
        pct_over_champ = float((p_champ > actual).mean() * 100)
        pct_over_chall = float((p_chall > actual).mean() * 100)
        bias_label = "Pct_Pred_Over_Actual (no line data)"

    hdr = f"  {'Metric':<28} {champ_label:>12} {chall_label:>16} {'Delta':>10}"
    print(f"\n{'='*68}")
    print(f"  total_runs  (NGBoost)    n={len(sub):,}")
    print(hdr)
    print(f"  {'-'*68}")
    _print_row("MAE",              mae_champ, mae_chall, 3)
    _print_row("AVG(pred)",        float(p_champ.mean()), float(p_chall.mean()), 3)
    _print_row("AVG(actual)",      float(actual.mean()), None, 3)
    _print_row(bias_label,         pct_over_champ, pct_over_chall, 1)

    bias_flag_chall = pct_over_chall < _BIAS_LOW or pct_over_chall > _BIAS_HIGH
    bias_flag_champ = pct_over_champ < _BIAS_LOW or pct_over_champ > _BIAS_HIGH

    if bias_flag_champ and not bias_flag_chall:
        print(f"\n  NOTE: Champion shows directional bias ({pct_over_champ:.1f}%); "
              f"challenger ({pct_over_chall:.1f}%) is healthier.")
    elif bias_flag_chall:
        direction = "under" if pct_over_chall < 50 else "over"
        print(f"\n  *** DIRECTIONAL BIAS: challenger predicts {direction} on "
              f"{max(pct_over_chall, 100-pct_over_chall):.1f}% of games "
              f"(healthy range: {_BIAS_LOW}%–{_BIAS_HIGH}%) ***")

    if delta_mae <= 0 and not bias_flag_chall:
        verdict = "PROMOTE — MAE improves, no directional bias."
    elif delta_mae <= 0 and bias_flag_chall:
        verdict = "PROMOTE WITH MONITORING — MAE improves but directional bias detected. Investigate before relying on totals signal."
    elif delta_mae <= 0.05 and not bias_flag_chall:
        verdict = f"PROMOTE WITH MONITORING — MAE +{delta_mae:.3f} (within noise), no bias."
    elif delta_mae <= 0.05 and bias_flag_chall:
        verdict = f"DO NOT PROMOTE — MAE slightly worse and directional bias detected."
    else:
        verdict = f"DO NOT PROMOTE — MAE regresses {delta_mae:+.3f}."
        if bias_flag_chall:
            verdict += " Directional bias also present."
    print(f"\n  Verdict: {verdict}")
    return verdict


def _compare_run_diff(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
    chall_cols: list[str],
    champ_label: str,
    chall_label: str,
) -> str:
    mask = df["run_differential"].notna()
    sub = df[mask].copy()
    sub_t = df_transformed.loc[mask].copy()

    p_champ = _predict_ngboost(champ_model, sub_t, champ_cols)
    p_chall = _predict_ngboost(chall_model, sub_t, chall_cols)
    actual  = sub["run_differential"].values.astype(float)

    mae_champ = float(np.mean(np.abs(actual - p_champ)))
    mae_chall = float(np.mean(np.abs(actual - p_chall)))
    delta_mae = mae_chall - mae_champ

    hdr = f"  {'Metric':<28} {champ_label:>12} {chall_label:>16} {'Delta':>10}"
    print(f"\n{'='*68}")
    print(f"  run_differential  (NGBoost)   n={len(sub):,}")
    print(hdr)
    print(f"  {'-'*68}")
    _print_row("MAE",          mae_champ, mae_chall, 3)
    _print_row("AVG(pred)",    float(p_champ.mean()), float(p_chall.mean()), 3)
    _print_row("AVG(actual)",  float(actual.mean()), None, 3)

    if delta_mae <= 0:
        verdict = "PROMOTE — challenger MAE improves or matches."
    elif delta_mae <= 0.05:
        verdict = f"PROMOTE WITH MONITORING — MAE +{delta_mae:.3f} (within noise)."
    else:
        verdict = f"DO NOT PROMOTE — challenger MAE worse by {delta_mae:.3f}."
    print(f"\n  Verdict: {verdict}")
    return verdict


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Offline Epic 1 champion-vs-challenger comparison."
    )
    parser.add_argument(
        "--start-year", type=int, default=2024,
        help="First season to include (default: 2024)",
    )
    parser.add_argument(
        "--target",
        choices=["home_win", "total_runs", "run_differential", "all"],
        default="all",
        help="Target to compare (default: all)",
    )
    args = parser.parse_args()

    print("=== EPIC 1 — OFFLINE CHAMPION VS CHALLENGER COMPARISON ===\n")
    print("Loading feature store from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= args.start_year].reset_index(drop=True)
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")

    # Fit + apply imputation pipeline once on all numeric cols so that the
    # Bayesian shrinkage step has its games_played counterparts available.
    print("\nFitting and applying imputation pipeline...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    pipe = build_imputation_pipeline()
    pipe.fit(df[numeric_cols])
    df_transformed = pd.DataFrame(
        pipe.transform(df[numeric_cols]),
        columns=numeric_cols,
        index=df.index,
    )
    print(f"  Done. Transformed shape: {df_transformed.shape}")

    targets = (
        ["home_win", "total_runs", "run_differential"]
        if args.target == "all"
        else [args.target]
    )

    verdicts: dict[str, str] = {}

    for target in targets:
        cfg = _CONFIGS[target]

        # Load feature column lists
        champ_cols: list[str] = json.loads(cfg["champion_cols"].read_text())
        chall_cols: list[str] = json.loads(cfg["challenger_cols"].read_text())

        # Load model artifacts
        champ_model = joblib.load(cfg["champion_artifact"])
        chall_model = joblib.load(cfg["challenger_artifact"])

        if target == "home_win":
            verdicts[target] = _compare_home_win(
                df, champ_model, chall_model,
                champ_cols, chall_cols,
                cfg["champ_label"], cfg["chall_label"],
            )
        elif target == "total_runs":
            verdicts[target] = _compare_total_runs(
                df, df_transformed, champ_model, chall_model,
                champ_cols, chall_cols,
                cfg["champ_label"], cfg["chall_label"],
            )
        else:
            verdicts[target] = _compare_run_diff(
                df, df_transformed, champ_model, chall_model,
                champ_cols, chall_cols,
                cfg["champ_label"], cfg["chall_label"],
            )

    print(f"\n{'='*68}")
    print("  SUMMARY")
    print(f"  {'-'*68}")
    for t, v in verdicts.items():
        short = v.split("—")[0].strip()
        print(f"  {t:<20} {short}")

    print(f"\n  total_runs directional bias thresholds:")
    print(f"    Healthy:  {_BIAS_LOW}%–{_BIAS_HIGH}% of games predicted over the line")
    print(f"    Flagged:  < {_BIAS_LOW}% or > {_BIAS_HIGH}% indicates systematic bias")


if __name__ == "__main__":
    main()
