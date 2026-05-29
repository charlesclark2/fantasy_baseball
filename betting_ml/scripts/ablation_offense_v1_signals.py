"""
ablation_offense_v1_signals.py — Story 4.4

Incremental ablation test: does adding offense_v1 signals improve totals and
run-differential CV MAE?

Compares walk-forward temporal CV (2015+ data, 8 folds, eval years 2018–2025):
  - Baseline:     feature_pregame_game_features columns only
  - With signals: + home_pred_runs_v1, away_pred_runs_v1,
                    home_runs_index_v1, away_runs_index_v1

Uses Ridge regression (alpha=1000) so each fold runs in seconds. The ablation
measures incremental signal value, not final model architecture.

Gate: document and proceed regardless of delta.  A near-zero delta is expected
(signal is a linear compression of features already in the matrix).  A regression
> +0.05 MAE on either target would indicate a data integrity problem and blocks
integration.

Usage:
    uv run python betting_ml/scripts/ablation_offense_v1_signals.py
    uv run python betting_ml/scripts/ablation_offense_v1_signals.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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
_REGRESSION_GATE = 0.05  # MAE increase above this on either target blocks integration

_SIGNAL_COLS = [
    "home_pred_runs_v1",
    "away_pred_runs_v1",
    "home_runs_index_v1",
    "away_runs_index_v1",
]

_SIGNAL_QUERY = """
select
    game_pk,
    max(case when side = 'home' then pred_runs_raw end) as home_pred_runs_v1,
    max(case when side = 'away' then pred_runs_raw end) as away_pred_runs_v1,
    max(case when side = 'home' then runs_index    end) as home_runs_index_v1,
    max(case when side = 'away' then runs_index    end) as away_runs_index_v1
from baseball_data.betting_features.offense_v1_signals
where model_version = 'offense_v1'
group by game_pk
"""

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v1"


def _load_signals() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNAL_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    for col in _SIGNAL_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _run_fold_cv(
    df: pd.DataFrame,
    feature_cols: list[str],
    target: str,
    tag: str,
) -> list[dict]:
    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=3))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        is_april = df.loc[eval_idx, "game_date"].astype(str).str[5:7] == "04"

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, target].values
        yev = df.loc[eval_idx, target].values
        yev_apr = yev[is_april.values]

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        for col in _SIGNAL_COLS:
            if col in Xtr.columns and Xtr[col].isna().any():
                fill = float(Xtr[col].mean())
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)
        y_pred_apr = y_pred[is_april.values]

        mae = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))
        mae_april = float(np.mean(np.abs(yev_apr - y_pred_apr))) if len(yev_apr) > 0 else None

        fold_results.append({
            "tag": tag,
            "target": target,
            "eval_year": eval_year,
            "n_eval": len(yev),
            "n_eval_april": int(is_april.sum()),
            "mae": mae,
            "bias": bias,
            "mae_april": mae_april,
        })
    return fold_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 4.4 ablation: offense_v1 signals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print feature counts and signal coverage then exit.")
    args = parser.parse_args()

    print("=== STORY 4.4 — OFFENSE V1 SIGNALS ABLATION TEST ===\n")

    print("Loading base features from Snowflake...")
    df_base = load_features(min_games_played=15)
    df_base = df_base[df_base["game_year"] >= 2015].reset_index(drop=True)
    if "game_date" in df_base.columns:
        df_base = df_base.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df_base):,} rows, seasons {sorted(df_base['game_year'].unique())}")

    print("\nLoading offense_v1 signals from offense_v1_signals...")
    df_signals = _load_signals()
    df_signals["game_pk"] = df_signals["game_pk"].astype(str)
    print(f"  {len(df_signals):,} signal rows (one per game_pk)")
    for col in _SIGNAL_COLS:
        n_pop = df_signals[col].notna().sum()
        print(f"  {col}: {n_pop:,} / {len(df_signals):,} ({100*n_pop/max(len(df_signals),1):.1f}%)")

    df_base["game_pk"] = df_base["game_pk"].astype(str)
    df_merged = df_base.merge(df_signals, on="game_pk", how="left")
    n_joined = df_merged[_SIGNAL_COLS[0]].notna().sum()
    print(f"\n  Joined: {n_joined:,} / {len(df_merged):,} base rows have signals "
          f"({100*n_joined/max(len(df_merged),1):.1f}%)")

    # Fill missing signals with neutral values (league-mean runs_index = 100, pred = col mean)
    for col in ["home_pred_runs_v1", "away_pred_runs_v1"]:
        fill = float(df_merged[col].mean()) if df_merged[col].notna().any() else 4.5
        df_merged[col] = df_merged[col].fillna(fill)
    for col in ["home_runs_index_v1", "away_runs_index_v1"]:
        df_merged[col] = df_merged[col].fillna(100.0)

    _NON_FEAT = _NON_FEATURE_COLS | {"split", "game_type"} | set(_SIGNAL_COLS)
    numeric_cols = df_merged.select_dtypes(include=[np.number]).columns.tolist()
    base_feature_cols = [c for c in numeric_cols if c not in _NON_FEAT]
    signal_feature_cols = base_feature_cols + _SIGNAL_COLS

    print(f"\n  Baseline feature cols:     {len(base_feature_cols)}")
    print(f"  With-signals feature cols: {len(signal_feature_cols)}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV. Feature columns look correct.")
        return

    results: dict = {
        "meta": {
            "story": "4.4",
            "script": "ablation_offense_v1_signals.py",
            "run_ts": datetime.now(timezone.utc).isoformat(),
            "base_feature_count": len(base_feature_cols),
            "signal_feature_count": len(signal_feature_cols),
            "signal_cols": _SIGNAL_COLS,
            "regression_gate": _REGRESSION_GATE,
        },
        "targets": {},
    }

    for target in ["total_runs", "run_differential"]:
        print(f"\n{'='*60}")
        print(f"TARGET: {target}")
        print(f"{'='*60}")

        print("\n--- BASELINE (no offense signals) ---")
        baseline_results = _run_fold_cv(df_merged, base_feature_cols, target, "baseline")
        for r in baseline_results:
            apr = f"  apr={r['mae_april']:.4f}" if r["mae_april"] is not None else ""
            print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}{apr}")
        baseline_mean = float(np.mean([r["mae"] for r in baseline_results]))
        print(f"  Mean MAE: {baseline_mean:.4f}")

        print("\n--- WITH SIGNALS (home/away pred_runs_v1 + runs_index_v1) ---")
        signal_results = _run_fold_cv(df_merged, signal_feature_cols, target, "with_signals")
        for r in signal_results:
            apr = f"  apr={r['mae_april']:.4f}" if r["mae_april"] is not None else ""
            print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}{apr}")
        signal_mean = float(np.mean([r["mae"] for r in signal_results]))
        print(f"  Mean MAE: {signal_mean:.4f}")

        delta = signal_mean - baseline_mean
        n_folds_improved = sum(
            1 for b, s in zip(baseline_results, signal_results) if s["mae"] < b["mae"]
        )
        n_folds = len(baseline_results)

        # April-only delta (where EB features carry most new info)
        baseline_apr = [r["mae_april"] for r in baseline_results if r["mae_april"] is not None]
        signal_apr   = [r["mae_april"] for r in signal_results   if r["mae_april"] is not None]
        april_delta = (float(np.mean(signal_apr)) - float(np.mean(baseline_apr))) if baseline_apr else None

        regression_triggered = delta > _REGRESSION_GATE

        print(f"""
--- SUMMARY ({target}) ---
  Baseline mean MAE:     {baseline_mean:.4f}
  With-signals mean MAE: {signal_mean:.4f}
  Delta:                 {delta:+.4f} ({'improvement' if delta < 0 else 'regression' if regression_triggered else 'neutral'})
  April delta:           {f'{april_delta:+.4f}' if april_delta is not None else 'n/a'}
  Folds improved:        {n_folds_improved} / {n_folds}
  Regression gate (>{_REGRESSION_GATE}): {'TRIGGERED — investigate before integration' if regression_triggered else 'clear'}
""")

        results["targets"][target] = {
            "baseline_mean_mae": baseline_mean,
            "signal_mean_mae": signal_mean,
            "delta": delta,
            "april_delta": april_delta,
            "folds_improved": n_folds_improved,
            "n_folds": n_folds,
            "regression_gate_triggered": regression_triggered,
            "baseline_folds": baseline_results,
            "signal_folds": signal_results,
        }

    # Overall gate check
    any_regression = any(
        v["regression_gate_triggered"] for v in results["targets"].values()
    )

    print("=" * 60)
    print("OVERALL GATE")
    print("=" * 60)
    if any_regression:
        print(f"  BLOCKED — regression > {_REGRESSION_GATE} MAE detected on at least one target.")
        print("  Investigate data integrity before integrating signals into Layer 3.")
    else:
        print("  CLEAR — no regression detected. Near-zero delta is expected at this stage.")
        print("  True integration point is the Layer 3 stacked model (Epic 9) where")
        print("  sub-model outputs replace raw features rather than augmenting them.")

    # Write JSON output
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = _OUTPUT_DIR / f"ablation_game_signals_{ts}.json"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print(f"\nResults written to {out_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
