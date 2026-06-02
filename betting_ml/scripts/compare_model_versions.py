"""Card 7.M — Offline champion vs. 7.M EB-enriched market-blind challenger comparison.

Loads the 2024+ feature window from Snowflake, scores both the current market-blind
champion and the 7.M EB-enriched challenger for each target, and prints side-by-side
metrics. No writes to Snowflake or daily_model_predictions.

Champion (current production):
  home_win       ElasticNet  elasticnet_market_blind_2026.pkl  feature_columns_market_blind.json
  total_runs     NGBoost     ngboost_market_blind_2026.pkl     feature_columns_market_blind.json
  run_diff       NGBoost     ngboost_market_blind_2026.pkl     feature_columns_market_blind.json

Challenger (7.M EB-enriched):
  home_win       XGBoost     xgb_classifier_tuned_2026.pkl     feature_selection.md (367 cols)
  total_runs     NGBoost     ngboost_tuned_2026.pkl            feature_selection.md (367 cols)
  run_diff       NGBoost     ngboost_tuned_2026.pkl            feature_selection.md (367 cols)

Key metrics
-----------
  home_win      Brier score, AVG(pred_prob) vs AVG(actual_win_rate)
  total_runs    MAE, AVG(pred) vs AVG(actual), Pct_Pred_Over_Line (directional bias)
  run_diff      MAE, AVG(pred) vs AVG(actual)

Usage
-----
    uv run python betting_ml/scripts/compare_model_versions.py
    uv run python betting_ml/scripts/compare_model_versions.py --start-year 2025
    uv run python betting_ml/scripts/compare_model_versions.py --target total_runs
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

from betting_ml.scripts.train_elasticnet_prod import _MARKET_COLS_TO_EXCLUDE
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

_MODELS = PROJECT_ROOT / "betting_ml" / "models"

# Directional bias thresholds for total_runs
_BIAS_LOW  = 25.0
_BIAS_HIGH = 75.0


def _load_md_feature_cols() -> list[str]:
    retained = load_retained_features()
    return [f for f in retained if f not in _MARKET_COLS_TO_EXCLUDE]


def _load_json_feature_cols(path: Path) -> list[str]:
    return json.loads(path.read_text())


def _build_challenger_transform(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Replicate the exact training preprocessing for 7.M challengers.

    Training scripts call:
        X_raw = df.loc[idx, feature_cols]
        pipe = build_imputation_pipeline()
        X_imp = pipe.fit_transform(X_raw)
        X_imp = X_imp.select_dtypes(include=[np.number])

    _AddIndicators inside the pipeline appends has_starter_platoon_data and
    is_new_venue, so the output has len(feature_cols) + 2 columns. Column
    order is preserved (indicators appended last), which matters for NGBoost
    since it was trained with .values (no named feature lookup).
    """
    available = [c for c in feature_cols if c in df.columns]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        print(f"  WARNING: {len(missing)} challenger feature cols absent from DataFrame "
              f"(will be zero-filled at inference): {missing[:10]}"
              + (" ..." if len(missing) > 10 else ""))
    pipe = build_imputation_pipeline()
    transformed = pipe.fit_transform(df[available])
    return transformed.select_dtypes(include=[np.number])


def _predict_elasticnet(model, feature_cols: list[str], df: pd.DataFrame) -> np.ndarray:
    X = df.reindex(columns=feature_cols, fill_value=0.0).values.astype(np.float32)
    return model.predict_proba(X)[:, 1]


def _predict_xgboost(model, df_chall_transformed: pd.DataFrame) -> np.ndarray:
    feature_cols = [str(f) for f in model.xgb_classifier.feature_names_in_]
    X = df_chall_transformed.reindex(columns=feature_cols, fill_value=0.0).values.astype(np.float32)
    return model.predict_proba(X)[:, 1]


def _predict_ngboost_champ(model, feature_cols: list[str], df_transformed: pd.DataFrame) -> np.ndarray:
    X = df_transformed.reindex(columns=feature_cols, fill_value=0.0).values
    return model.predict(X)


def _predict_ngboost_chall(model, df_chall_transformed: pd.DataFrame) -> np.ndarray:
    return model.predict(df_chall_transformed.values)


def _fmt(v: float | None, d: int = 4) -> str:
    return f"{v:.{d}f}" if v is not None else "—"


def _print_row(label: str, v0: float | None, v1: float | None, d: int = 4) -> None:
    delta = (v1 - v0) if (v0 is not None and v1 is not None) else None
    delta_s = f"{delta:+.{d}f}" if delta is not None else "—"
    print(f"  {label:<30} {_fmt(v0, d):>12} {_fmt(v1, d):>16} {delta_s:>10}")


def _compare_home_win(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    df_chall_transformed: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
) -> str:
    mask = df["home_win"].notna()
    sub = df[mask].copy()
    sub_chall = df_chall_transformed.loc[mask]
    actual = sub["home_win"].values.astype(float)

    p_champ = _predict_elasticnet(champ_model, champ_cols, sub)
    p_chall = _predict_xgboost(chall_model, sub_chall)
    chall_n_features = len(chall_model.xgb_classifier.feature_names_in_)

    brier_champ = float(np.mean((actual - p_champ) ** 2))
    brier_chall = float(np.mean((actual - p_chall) ** 2))
    delta_brier = brier_chall - brier_champ

    actual_mean = float(actual.mean())
    champ_cal_bias = float(p_champ.mean()) - actual_mean
    chall_cal_bias = float(p_chall.mean()) - actual_mean
    _CAL_BIAS_LIMIT = 0.05  # flag if avg_pred deviates from avg_actual by >5 pp

    hdr = f"  {'Metric':<30} {'Champion (v2)':>12} {'Challenger (7.M)':>16} {'Delta':>10}"
    print(f"\n{'='*70}")
    print(f"  home_win  (ElasticNet vs XGBoost EB)   n={len(sub):,}   chall_features={chall_n_features}")
    print(hdr)
    print(f"  {'-'*70}")
    _print_row("Brier",          brier_champ,          brier_chall)
    _print_row("AVG(pred_prob)", float(p_champ.mean()), float(p_chall.mean()))
    _print_row("AVG(actual)",    actual_mean,           None)
    _print_row("Cal bias (pred−actual)", champ_cal_bias, chall_cal_bias)

    bias_flag_chall = abs(chall_cal_bias) > _CAL_BIAS_LIMIT
    bias_flag_champ = abs(champ_cal_bias) > _CAL_BIAS_LIMIT

    if bias_flag_chall:
        direction = "over" if chall_cal_bias > 0 else "under"
        print(f"\n  *** CALIBRATION BIAS: challenger systematically calls {direction} "
              f"({chall_cal_bias:+.4f} avg pred vs actual; limit: ±{_CAL_BIAS_LIMIT}) ***")

    if delta_brier <= 0 and not bias_flag_chall:
        verdict = "PROMOTE — challenger Brier improves, calibration healthy."
    elif delta_brier <= 0 and bias_flag_chall:
        verdict = f"DO NOT PROMOTE — Brier improves but calibration bias {chall_cal_bias:+.4f} exceeds ±{_CAL_BIAS_LIMIT}."
    elif delta_brier <= 0.002 and not bias_flag_chall:
        verdict = f"PROMOTE WITH MONITORING — Brier +{delta_brier:.4f}, within 0.002 tolerance."
    elif delta_brier <= 0.002 and bias_flag_chall:
        verdict = f"DO NOT PROMOTE — Brier +{delta_brier:.4f} and calibration bias {chall_cal_bias:+.4f} exceeds ±{_CAL_BIAS_LIMIT}."
    else:
        verdict = f"DO NOT PROMOTE — Brier regresses {delta_brier:+.4f} (limit: +0.002)."
        if bias_flag_chall:
            verdict += f" Calibration bias {chall_cal_bias:+.4f} also flagged."
    print(f"\n  Verdict: {verdict}")
    return verdict


def _compare_total_runs(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    df_chall_transformed: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
) -> str:
    mask = df["total_runs"].notna()
    sub = df[mask].copy()
    actual = sub["total_runs"].values.astype(float)

    p_champ = _predict_ngboost_champ(champ_model, champ_cols, df_transformed.loc[mask])
    p_chall = _predict_ngboost_chall(chall_model, df_chall_transformed.loc[mask])

    mae_champ = float(np.mean(np.abs(actual - p_champ)))
    mae_chall = float(np.mean(np.abs(actual - p_chall)))
    delta_mae = mae_chall - mae_champ

    if "total_line_consensus" in df.columns and df.loc[mask, "total_line_consensus"].notna().mean() > 0.5:
        line = df.loc[mask, "total_line_consensus"].fillna(float(actual.mean())).values
        pct_over_champ = float((p_champ > line).mean() * 100)
        pct_over_chall = float((p_chall > line).mean() * 100)
        bias_label = "Pct_Pred_Over_Line"
    else:
        pct_over_champ = float((p_champ > actual).mean() * 100)
        pct_over_chall = float((p_chall > actual).mean() * 100)
        bias_label = "Pct_Pred_Over_Actual (no line data)"

    hdr = f"  {'Metric':<30} {'Champion (v3)':>12} {'Challenger (7.M)':>16} {'Delta':>10}"
    print(f"\n{'='*70}")
    print(f"  total_runs  (NGBoost champion vs NGBoost EB)   n={len(sub):,}")
    print(hdr)
    print(f"  {'-'*70}")
    _print_row("MAE",           mae_champ,            mae_chall,            3)
    _print_row("AVG(pred)",     float(p_champ.mean()), float(p_chall.mean()), 3)
    _print_row("AVG(actual)",   float(actual.mean()),  None,                 3)
    _print_row(bias_label,      pct_over_champ,        pct_over_chall,       1)

    bias_flag_chall = pct_over_chall < _BIAS_LOW or pct_over_chall > _BIAS_HIGH
    bias_flag_champ = pct_over_champ < _BIAS_LOW or pct_over_champ > _BIAS_HIGH

    if bias_flag_champ and not bias_flag_chall:
        print(f"\n  NOTE: Champion shows directional bias ({pct_over_champ:.1f}%); "
              f"challenger ({pct_over_chall:.1f}%) is healthier.")
    elif bias_flag_chall:
        direction = "under" if pct_over_chall < 50 else "over"
        print(f"\n  *** DIRECTIONAL BIAS: challenger predicts {direction} on "
              f"{max(pct_over_chall, 100 - pct_over_chall):.1f}% of games "
              f"(healthy range: {_BIAS_LOW}%–{_BIAS_HIGH}%) ***")

    if delta_mae <= 0 and not bias_flag_chall:
        verdict = "PROMOTE — MAE improves, no directional bias."
    elif delta_mae <= 0 and bias_flag_chall:
        verdict = "PROMOTE WITH MONITORING — MAE improves but directional bias detected."
    elif delta_mae <= 0.05 and not bias_flag_chall:
        verdict = f"PROMOTE WITH MONITORING — MAE +{delta_mae:.3f} (within noise), no bias."
    elif delta_mae <= 0.05 and bias_flag_chall:
        verdict = "DO NOT PROMOTE — MAE slightly worse and directional bias detected."
    else:
        verdict = f"DO NOT PROMOTE — MAE regresses {delta_mae:+.3f}."
        if bias_flag_chall:
            verdict += " Directional bias also present."
    print(f"\n  Verdict: {verdict}")
    return verdict


def _compare_run_diff(
    df: pd.DataFrame,
    df_transformed: pd.DataFrame,
    df_chall_transformed: pd.DataFrame,
    champ_model,
    chall_model,
    champ_cols: list[str],
) -> str:
    mask = df["run_differential"].notna()
    sub = df[mask].copy()
    actual = sub["run_differential"].values.astype(float)

    p_champ = _predict_ngboost_champ(champ_model, champ_cols, df_transformed.loc[mask])
    p_chall = _predict_ngboost_chall(chall_model, df_chall_transformed.loc[mask])

    mae_champ = float(np.mean(np.abs(actual - p_champ)))
    mae_chall = float(np.mean(np.abs(actual - p_chall)))
    delta_mae = mae_chall - mae_champ

    hdr = f"  {'Metric':<30} {'Champion (v2)':>12} {'Challenger (7.M)':>16} {'Delta':>10}"
    print(f"\n{'='*70}")
    print(f"  run_differential  (NGBoost champion vs NGBoost EB)   n={len(sub):,}")
    print(hdr)
    print(f"  {'-'*70}")
    _print_row("MAE",          mae_champ,            mae_chall,            3)
    _print_row("AVG(pred)",    float(p_champ.mean()), float(p_chall.mean()), 3)
    _print_row("AVG(actual)",  float(actual.mean()),  None,                 3)

    if delta_mae <= 0:
        verdict = "PROMOTE — challenger MAE improves or matches."
    elif delta_mae <= 0.05:
        verdict = f"PROMOTE WITH MONITORING — MAE +{delta_mae:.3f} (within noise)."
    else:
        verdict = f"DO NOT PROMOTE — challenger MAE worse by {delta_mae:.3f}."
    print(f"\n  Verdict: {verdict}")
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Card 7.M offline champion vs. EB-enriched challenger comparison."
    )
    parser.add_argument(
        "--start-year", type=int, default=2024,
        help="First season to include in held-out evaluation (default: 2024)",
    )
    parser.add_argument(
        "--target",
        choices=["home_win", "total_runs", "run_differential", "all"],
        default="all",
        help="Target to compare (default: all)",
    )
    args = parser.parse_args()

    print("=== CARD 7.M — CHAMPION vs. EB-ENRICHED CHALLENGER COMPARISON ===\n")
    print("Champions: market-blind ElasticNet/NGBoost (Epic 1, v2/v3)")
    print("Challengers: EB-enriched market-blind XGBoost/NGBoost (7.M, 367 features)\n")

    print("Loading feature store from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= args.start_year].reset_index(drop=True)
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")

    print("\nFitting and applying imputation pipeline (champions)...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    pipe_champ = build_imputation_pipeline()
    pipe_champ.fit(df[numeric_cols])
    champ_out = pipe_champ.transform(df[numeric_cols])
    df_transformed = champ_out.reindex(columns=numeric_cols).fillna(0.0)
    df_transformed.index = df.index
    print(f"  Done. Champion transformed shape: {df_transformed.shape}")

    chall_base_cols = _load_md_feature_cols()
    print(f"\nBuilding challenger transform (feature_selection.md − market: {len(chall_base_cols)} cols)...")
    df_chall_transformed = _build_challenger_transform(df, chall_base_cols)
    df_chall_transformed.index = df.index
    print(f"  Done. Challenger transformed shape: {df_chall_transformed.shape}")

    targets = (
        ["home_win", "total_runs", "run_differential"]
        if args.target == "all"
        else [args.target]
    )

    verdicts: dict[str, str] = {}

    if "home_win" in targets:
        champ_cols = _load_json_feature_cols(
            _MODELS / "home_win" / "feature_columns_market_blind.json"
        )
        champ_model = joblib.load(_MODELS / "home_win" / "elasticnet_market_blind_2026.pkl")
        chall_model = joblib.load(_MODELS / "home_win" / "xgb_classifier_tuned_2026.pkl")
        verdicts["home_win"] = _compare_home_win(
            df, df_transformed, df_chall_transformed, champ_model, chall_model, champ_cols
        )

    if "total_runs" in targets:
        champ_cols = _load_json_feature_cols(
            _MODELS / "total_runs" / "feature_columns_market_blind.json"
        )
        champ_model = joblib.load(_MODELS / "total_runs" / "ngboost_market_blind_2026.pkl")
        chall_model = joblib.load(_MODELS / "total_runs" / "ngboost_tuned_2026.pkl")
        verdicts["total_runs"] = _compare_total_runs(
            df, df_transformed, df_chall_transformed, champ_model, chall_model, champ_cols
        )

    if "run_differential" in targets:
        champ_cols = _load_json_feature_cols(
            _MODELS / "run_differential" / "feature_columns_market_blind.json"
        )
        champ_model = joblib.load(_MODELS / "run_differential" / "ngboost_market_blind_2026.pkl")
        chall_model = joblib.load(_MODELS / "run_differential" / "ngboost_tuned_2026.pkl")
        verdicts["run_differential"] = _compare_run_diff(
            df, df_transformed, df_chall_transformed, champ_model, chall_model, champ_cols
        )

    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"  {'-'*70}")
    for t, v in verdicts.items():
        short = v.split("—")[0].strip()
        print(f"  {t:<22} {short}")

    print(f"\n  total_runs directional bias thresholds:")
    print(f"    Healthy:  {_BIAS_LOW}%–{_BIAS_HIGH}% of games predicted over the line")
    print(f"    Flagged:  < {_BIAS_LOW}% or > {_BIAS_HIGH}% indicates systematic bias")


if __name__ == "__main__":
    main()
