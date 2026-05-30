"""
ablation_bullpen_signals.py — Epic 6, Story 6.5

Incremental ablation test: do bullpen sub-model signals improve totals CV MAE?

Compares walk-forward temporal CV (2021+ data, season-forward folds) using:
  - Baseline:     feature_pregame_game_features columns only
  - With signals: + bullpen_quality_signal_v1_home
                  + bullpen_quality_signal_v1_away
                  + bullpen_fatigue_signal_v1_home
                  + bullpen_fatigue_signal_v1_away
                  + high_leverage_availability_proxy_v1_home
                  + high_leverage_availability_proxy_v1_away
                  + late_game_volatility_signal_v1_home
                  + late_game_volatility_signal_v1_away

Uses Ridge regression (alpha=1000) for fast fold-level CV — same approach as
ablation_run_env_signals.py. The ablation measures incremental signal value,
not final model architecture.

Gate: proceed to Layer 3 integration if signals reduce mean CV MAE vs. baseline
      OR show directional improvement in majority of folds.

Requires mart_sub_model_signals to have bullpen_v1 rows (run Story 6.4 first).

Usage:
    uv run python betting_ml/scripts/ablation_bullpen_signals.py
    uv run python betting_ml/scripts/ablation_bullpen_signals.py --dry-run
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

# Signals to pull: one row per game_pk with home + away values pivoted wide
_SIGNAL_COLS = [
    "bullpen_quality_signal_home",
    "bullpen_quality_signal_away",
    "bullpen_fatigue_signal_home",
    "bullpen_fatigue_signal_away",
    "high_leverage_availability_proxy_home",
    "high_leverage_availability_proxy_away",
    "late_game_volatility_signal_home",
    "late_game_volatility_signal_away",
]

# Neutral fill values when signal is unavailable (league-average)
_SIGNAL_DEFAULTS = {
    "bullpen_quality_signal_home":            0.0,    # z=0 → average quality
    "bullpen_quality_signal_away":            0.0,
    "bullpen_fatigue_signal_home":            None,   # filled with training mean
    "bullpen_fatigue_signal_away":            None,
    "high_leverage_availability_proxy_home":  None,
    "high_leverage_availability_proxy_away":  None,
    "late_game_volatility_signal_home":       None,
    "late_game_volatility_signal_away":       None,
}

# Pivot from long mart into one row per game_pk
_SIGNAL_QUERY = """
SELECT
    game_pk,
    MAX(CASE WHEN signal_name = 'bullpen_quality_signal'           AND side = 'home' THEN signal_value END) AS bullpen_quality_signal_home,
    MAX(CASE WHEN signal_name = 'bullpen_quality_signal'           AND side = 'away' THEN signal_value END) AS bullpen_quality_signal_away,
    MAX(CASE WHEN signal_name = 'bullpen_fatigue_signal'           AND side = 'home' THEN signal_value END) AS bullpen_fatigue_signal_home,
    MAX(CASE WHEN signal_name = 'bullpen_fatigue_signal'           AND side = 'away' THEN signal_value END) AS bullpen_fatigue_signal_away,
    MAX(CASE WHEN signal_name = 'high_leverage_availability_proxy' AND side = 'home' THEN signal_value END) AS high_leverage_availability_proxy_home,
    MAX(CASE WHEN signal_name = 'high_leverage_availability_proxy' AND side = 'away' THEN signal_value END) AS high_leverage_availability_proxy_away,
    MAX(CASE WHEN signal_name = 'late_game_volatility_signal'      AND side = 'home' THEN signal_value END) AS late_game_volatility_signal_home,
    MAX(CASE WHEN signal_name = 'late_game_volatility_signal'      AND side = 'away' THEN signal_value END) AS late_game_volatility_signal_away
FROM baseball_data.betting.mart_sub_model_signals
WHERE sub_model_name    = 'bullpen_v1'
  AND sub_model_version = 'v1'
  AND is_current        = TRUE
  AND signal_name IN (
      'bullpen_quality_signal',
      'bullpen_fatigue_signal',
      'high_leverage_availability_proxy',
      'late_game_volatility_signal'
  )
GROUP BY game_pk
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CV harness (mirrors ablation_run_env_signals.py)
# ---------------------------------------------------------------------------

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
                fill = Xtr[col].mean() if Xtr[col].notna().any() else 0.0
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)
        mae    = float(np.mean(np.abs(yev - y_pred)))
        bias   = float(np.mean(y_pred - yev))

        fold_results.append({
            "tag":      tag,
            "eval_year": eval_year,
            "n_eval":   len(yev),
            "mae":      mae,
            "bias":     bias,
        })
    return fold_results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Story 6.5 ablation: bullpen_v1 signals vs. totals baseline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print feature counts and signal coverage then exit without running CV.",
    )
    args = parser.parse_args()

    print("=== STORY 6.5 — BULLPEN SIGNAL ABLATION TEST ===\n")

    print("Loading base features from Snowflake...")
    df_base = load_features(min_games_played=15)
    df_base = df_base[df_base["game_year"] >= 2021].reset_index(drop=True)
    if "game_date" in df_base.columns:
        df_base = df_base.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df_base):,} rows, seasons {sorted(df_base['game_year'].unique())}")

    print("\nLoading bullpen_v1 signals from mart_sub_model_signals...")
    df_signals = _load_signals()
    df_signals["game_pk"] = df_signals["game_pk"].astype(int)
    print(f"  {len(df_signals):,} game_pk rows")
    for col in _SIGNAL_COLS:
        if col in df_signals.columns:
            n_pop = df_signals[col].notna().sum()
            print(
                f"  {col}: {n_pop:,} / {len(df_signals):,} populated "
                f"({100 * n_pop / max(len(df_signals), 1):.1f}%)"
            )

    if df_signals.empty:
        print("\nERROR: no bullpen signals found. Run generate_bullpen_signals.py --backfill first.")
        sys.exit(1)

    # Merge signals → base
    df_base["game_pk"] = df_base["game_pk"].astype(int)
    df_merged = df_base.merge(df_signals, on="game_pk", how="left")
    n_joined = df_merged[_SIGNAL_COLS[0]].notna().sum()
    print(
        f"\n  Joined: {n_joined:,} / {len(df_merged):,} base rows have bullpen signals "
        f"({100 * n_joined / max(len(df_merged), 1):.1f}%)"
    )

    # Pre-fill z-score signals with 0 (league-average); fill others with training global mean
    df_merged["bullpen_quality_signal_home"] = df_merged["bullpen_quality_signal_home"].fillna(0.0)
    df_merged["bullpen_quality_signal_away"] = df_merged["bullpen_quality_signal_away"].fillna(0.0)
    for col in _SIGNAL_COLS:
        if _SIGNAL_DEFAULTS.get(col) is None and col in df_merged.columns:
            global_mean = float(df_merged[col].mean()) if df_merged[col].notna().any() else 0.0
            df_merged[col] = df_merged[col].fillna(global_mean)

    _NON_FEAT = _NON_FEATURE_COLS | {"split", "game_type"} | set(_SIGNAL_COLS)

    numeric_cols       = df_merged.select_dtypes(include=[np.number]).columns.tolist()
    base_feature_cols  = [c for c in numeric_cols if c not in _NON_FEAT]
    signal_feature_cols = base_feature_cols + [c for c in _SIGNAL_COLS if c in df_merged.columns]

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

    print("\n--- WITH BULLPEN SIGNALS (quality, fatigue, hi-lev proxy, volatility) ---")
    signal_results = _run_fold_cv(df_merged, signal_feature_cols, tag="with_bullpen_signals")
    for r in signal_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
    signal_mean = float(np.mean([r["mae"] for r in signal_results]))
    print(f"  Mean MAE: {signal_mean:.4f}")

    delta = signal_mean - baseline_mean
    n_folds_improved = sum(
        1 for b, s in zip(baseline_results, signal_results) if s["mae"] < b["mae"]
    )
    n_folds = len(baseline_results)

    gate_pass = delta < 0 or n_folds_improved > n_folds / 2

    print(f"""
=== ABLATION SUMMARY ===
  Signals tested:        {', '.join(_SIGNAL_COLS)}
  Baseline mean MAE:     {baseline_mean:.4f}
  With-signals mean MAE: {signal_mean:.4f}
  Delta:                 {delta:+.4f} ({'improvement' if delta < 0 else 'degradation'})
  Folds improved:        {n_folds_improved} / {n_folds}

Gate: signals show positive incremental value
  Criterion: MAE reduction OR majority-of-folds improvement
  Result: {'PASS' if gate_pass else 'FAIL'}
""")

    if gate_pass:
        print("Signals show positive incremental value.")
        print("Next steps:")
        print("  1. Add bullpen signal columns to feature_pregame_sub_model_signals dbt model.")
        print("  2. dbtf build --select feature_pregame_sub_model_signals")
        print("  3. Update sub_model_registry.yaml bullpen_v1 with ablation results.")
    else:
        print("Signals do not clear the gate.")
        print("Options:")
        print("  - Investigate per-fold signal coverage (pre-2021 may be sparse).")
        print("  - Consider a 2022+ restricted window for the ablation.")
        print("  - Signals still carry value at Layer 3 (Epic 17) even if Ridge ablation is flat.")


if __name__ == "__main__":
    main()
