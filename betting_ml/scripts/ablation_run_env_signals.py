"""
ablation_run_env_signals.py — Story 3.Z

Incremental ablation test: does adding run_env_v3 signals improve totals CV MAE?

Compares walk-forward temporal CV (2021+ data, season-forward folds) using:
  - Baseline:     feature_pregame_game_features columns only (same as train_total_runs_prod)
  - With signals: + run_env_signal_v3 (z-scored predicted total runs)
                  + environment_volatility_v3 (per-venue run std dev)

Uses Ridge regression (alpha=1000) rather than NGBoost so each fold runs in
seconds rather than hours. The ablation measures incremental signal value, not
final model architecture.

Gate: proceed to Layer 3 integration if signals reduce mean CV MAE vs. baseline
      OR show directional improvement in majority of folds.

Usage:
    uv run python betting_ml/scripts/ablation_run_env_signals.py
    uv run python betting_ml/scripts/ablation_run_env_signals.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_RIDGE_ALPHA = 1000

_SIGNAL_COLS = ["run_env_signal_v3", "environment_volatility_v3"]

# Imputation defaults for when signal is unavailable (neutral / league-mean)
_SIGNAL_DEFAULTS = {
    "run_env_signal_v3": 0.0,       # z=0 → league-average run environment
    "environment_volatility_v3": None,  # filled with training-window mean
}

_SIGNAL_QUERY = """
select
    game_pk,
    max(case when signal_name = 'run_env_signal'         and sub_model_version = 'v3' then signal_value end) as run_env_signal_v3,
    max(case when signal_name = 'environment_volatility' and sub_model_version = 'v3' then signal_value end) as environment_volatility_v3
from baseball_data.betting.mart_sub_model_signals
where sub_model_version = 'v3'
  and is_current = true
  and side = 'home'
group by game_pk
"""


def _load_signals() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNAL_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    return pd.DataFrame(rows, columns=cols)


def _run_fold_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    tag: str,
) -> list[dict]:
    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=3))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        # Fill any remaining nulls in signal cols with column training mean
        for col in _SIGNAL_COLS:
            if col in Xtr.columns and Xtr[col].isna().any():
                fill = Xtr[col].mean()
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)
        mae = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))

        fold_results.append({
            "tag": tag,
            "eval_year": eval_year,
            "n_eval": len(yev),
            "mae": mae,
            "bias": bias,
        })
    return fold_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 3.Z ablation: run_env_v3 signals")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print feature counts and signal coverage then exit.",
    )
    args = parser.parse_args()

    print("=== STORY 3.Z — RUN ENV V3 ABLATION TEST ===\n")

    print("Loading base features from Snowflake...")
    df_base = load_features(min_games_played=15)
    df_base = df_base[df_base["game_year"] >= 2021].reset_index(drop=True)
    if "game_date" in df_base.columns:
        df_base = df_base.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df_base):,} rows, seasons {sorted(df_base['game_year'].unique())}")

    print("\nLoading run_env_v3 signals from mart_sub_model_signals...")
    df_signals = _load_signals()
    df_signals["game_pk"] = df_signals["game_pk"].astype(int)
    print(f"  {len(df_signals):,} signal rows (one per game_pk)")
    for col in _SIGNAL_COLS:
        n_pop = df_signals[col].notna().sum()
        print(f"  {col}: {n_pop:,} / {len(df_signals):,} populated ({100*n_pop/max(len(df_signals),1):.1f}%)")

    # Merge signals → base
    df_base["game_pk"] = df_base["game_pk"].astype(int)
    df_merged = df_base.merge(df_signals, on="game_pk", how="left")
    n_joined = df_merged[_SIGNAL_COLS[0]].notna().sum()
    print(f"\n  Joined: {n_joined:,} / {len(df_merged):,} base rows have signals ({100*n_joined/max(len(df_merged),1):.1f}%)")

    # Impute environment_volatility_v3 with training-window mean before fold CV
    # (fold-level imputation inside _run_fold_cv handles any remaining NULLs)
    global_vol_mean = float(df_merged["environment_volatility_v3"].mean()) if df_merged["environment_volatility_v3"].notna().any() else 3.0
    df_merged["environment_volatility_v3"] = df_merged["environment_volatility_v3"].fillna(global_vol_mean)
    df_merged["run_env_signal_v3"] = df_merged["run_env_signal_v3"].fillna(0.0)

    _NON_FEAT = _NON_FEATURE_COLS | {"split", "game_type"} | set(_SIGNAL_COLS)

    numeric_cols = df_merged.select_dtypes(include=[np.number]).columns.tolist()
    base_feature_cols = [c for c in numeric_cols if c not in _NON_FEAT]
    signal_feature_cols = base_feature_cols + _SIGNAL_COLS

    print(f"\n  Baseline feature cols:     {len(base_feature_cols)}")
    print(f"  With-signals feature cols: {len(signal_feature_cols)}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV. Feature columns look correct.")
        return

    print("\n--- BASELINE (no sub-model signals) ---")
    baseline_results = _run_fold_cv(df_merged, base_feature_cols, tag="baseline")
    for r in baseline_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    baseline_mean = float(np.mean([r["mae"] for r in baseline_results]))
    print(f"  Mean MAE: {baseline_mean:.4f}")

    print("\n--- WITH SIGNALS (run_env_signal_v3, environment_volatility_v3) ---")
    signal_results = _run_fold_cv(df_merged, signal_feature_cols, tag="with_signals")
    for r in signal_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    signal_mean = float(np.mean([r["mae"] for r in signal_results]))
    print(f"  Mean MAE: {signal_mean:.4f}")

    delta = signal_mean - baseline_mean
    n_folds_improved = sum(
        1 for b, s in zip(baseline_results, signal_results) if s["mae"] < b["mae"]
    )
    n_folds = len(baseline_results)

    print(f"""
=== ABLATION SUMMARY ===
  Baseline mean MAE:     {baseline_mean:.4f}
  With-signals mean MAE: {signal_mean:.4f}
  Delta:                 {delta:+.4f} ({'improvement' if delta < 0 else 'degradation'})
  Folds improved:        {n_folds_improved} / {n_folds}

Gate: signals show positive incremental value
  → {'PASS' if delta < 0 or n_folds_improved > n_folds / 2 else 'FAIL'}
  (criterion: MAE reduction OR majority-of-folds improvement)
""")

    if delta < 0 or n_folds_improved > n_folds / 2:
        print("Signals show positive incremental value.")
        print("Next: add run_env_signal_v3 + environment_volatility_v3 to load_features()")
        print("      query and rebuild feature_pregame_sub_model_signals (v3 columns).")
    else:
        print("Signals do NOT show clear incremental value over existing feature set.")
        print("This is expected if base features already contain park/weather/umpire inputs.")
        print("Consider: document findings in sub_model_registry.yaml notes; defer integration.")


if __name__ == "__main__":
    main()
