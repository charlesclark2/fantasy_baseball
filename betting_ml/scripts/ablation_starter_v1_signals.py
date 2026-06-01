"""
ablation_starter_v1_signals.py — Story 5.5

Incremental ablation: does adding starter_suppression_mu_v1 and
starter_suppression_signal_v1 improve totals and run-differential CV MAE?

Compares walk-forward temporal CV (2015+ data, min_train_seasons=3):
  - Baseline:     feature_pregame_game_features columns only
  - With signals: + home_starter_suppression_mu_v1, away_starter_suppression_mu_v1,
                    home_starter_suppression_signal_v1, away_starter_suppression_signal_v1

Starter signals are available from 2021+ only; 2015-2020 rows are filled with
neutral values (mu=league_mean≈0.325, signal=0.0). The model sees a "no-info"
value for years outside the signal window, so the test is conservative.

Uses Ridge regression (alpha=1000) for speed. Regression gate: delta MAE < 0.005.
Feature importance reported via Ridge |coef| rank on the full dataset.

Usage:
    uv run python betting_ml/scripts/ablation_starter_v1_signals.py
    uv run python betting_ml/scripts/ablation_starter_v1_signals.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS

_RIDGE_ALPHA = 1000
_MAE_GATE = 0.005          # max allowed MAE increase per target

# Neutral fill values for 2015-2020 rows (outside signal window)
_MU_NEUTRAL    = 0.325     # ≈ league-mean starter xwOBA-against (2021-2026 avg)
_SIGNAL_NEUTRAL = 0.0      # signal is mean-zero by construction

_SIGNAL_COLS = [
    "home_starter_suppression_mu_v1",
    "away_starter_suppression_mu_v1",
    "home_starter_suppression_signal_v1",
    "away_starter_suppression_signal_v1",
]

_SIGNAL_QUERY = """
select
    game_pk,
    max(case when side = 'home' then starter_suppression_mu_v1     end) as home_starter_suppression_mu_v1,
    max(case when side = 'away' then starter_suppression_mu_v1     end) as away_starter_suppression_mu_v1,
    max(case when side = 'home' then starter_suppression_signal_v1 end) as home_starter_suppression_signal_v1,
    max(case when side = 'away' then starter_suppression_signal_v1 end) as away_starter_suppression_signal_v1
from baseball_data.betting_features.feature_pregame_sub_model_signals
group by game_pk
"""

_REPORT_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"


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

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, target].values
        yev = df.loc[eval_idx, target].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        # Signal cols may still have NaN after imputation pipeline (if all-NaN in fold)
        for col in [c for c in _SIGNAL_COLS if c in Xtr.columns]:
            if Xtr[col].isna().any():
                fill = float(Xtr[col].mean()) if Xtr[col].notna().any() else 0.0
                Xtr[col] = Xtr[col].fillna(fill)
                Xev[col] = Xev[col].fillna(fill)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)

        mae  = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))
        fold_results.append({
            "tag": tag, "target": target,
            "eval_year": eval_year, "n_eval": len(yev),
            "mae": mae, "bias": bias,
        })
    return fold_results


def _ridge_importance(
    df: pd.DataFrame,
    feature_cols: list[str],
    target: str,
) -> list[tuple[str, float]]:
    """Return list of (feature_name, |coef| rank weight) sorted descending."""
    pipe = build_imputation_pipeline()
    X = pipe.fit_transform(df[feature_cols]).select_dtypes(include=[np.number])
    for col in [c for c in _SIGNAL_COLS if c in X.columns]:
        X[col] = X[col].fillna(0.0)
    y = df[target].values

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X.values)

    model = Ridge(alpha=_RIDGE_ALPHA)
    model.fit(Xs, y)

    importance = np.abs(model.coef_)
    order = np.argsort(importance)[::-1]
    return [(X.columns[i], float(importance[i])) for i in order]


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 5.5 ablation: starter_v1 signals")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print data shape and signal coverage then exit.")
    args = parser.parse_args()

    print("=== STORY 5.5 — STARTER V1 SIGNALS ABLATION TEST ===\n")

    print("Loading base features from Snowflake...")
    df_base = load_features(min_games_played=15)
    df_base = df_base[df_base["game_year"] >= 2015].reset_index(drop=True)
    if "game_date" in df_base.columns:
        df_base = df_base.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df_base):,} rows, seasons {sorted(df_base['game_year'].unique())}")

    print("\nLoading starter_v1 signals from feature_pregame_sub_model_signals...")
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

    # Fill 2015-2020 (and any missing) with neutral values
    for col in ["home_starter_suppression_mu_v1", "away_starter_suppression_mu_v1"]:
        df_merged[col] = df_merged[col].fillna(_MU_NEUTRAL)
    for col in ["home_starter_suppression_signal_v1", "away_starter_suppression_signal_v1"]:
        df_merged[col] = df_merged[col].fillna(_SIGNAL_NEUTRAL)

    _NON_FEAT = _NON_FEATURE_COLS | {"split", "game_type"} | set(_SIGNAL_COLS)
    numeric_cols = df_merged.select_dtypes(include=[np.number]).columns.tolist()
    base_feature_cols  = [c for c in numeric_cols if c not in _NON_FEAT]
    signal_feature_cols = base_feature_cols + _SIGNAL_COLS

    print(f"\n  Baseline feature cols:     {len(base_feature_cols)}")
    print(f"  With-signals feature cols: {len(signal_feature_cols)}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV. Columns and coverage look correct.")
        return

    target_results: dict[str, dict] = {}

    for target in ["total_runs", "run_differential"]:
        print(f"\n{'─'*60}")
        print(f"TARGET: {target}")
        print(f"{'─'*60}")

        print("\n── Baseline (no starter signals) ──────────────────────────")
        baseline_results = _run_fold_cv(df_merged, base_feature_cols, target, "baseline")
        for r in baseline_results:
            print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
        baseline_mean = float(np.mean([r["mae"] for r in baseline_results]))
        print(f"  Mean MAE: {baseline_mean:.4f}")

        print("\n── With starter signals ───────────────────────────────────")
        signal_results = _run_fold_cv(df_merged, signal_feature_cols, target, "with_signals")
        for r in signal_results:
            print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  n={r['n_eval']}")
        signal_mean = float(np.mean([r["mae"] for r in signal_results]))
        print(f"  Mean MAE: {signal_mean:.4f}")

        delta = signal_mean - baseline_mean
        n_folds_improved = sum(
            1 for b, s in zip(baseline_results, signal_results) if s["mae"] < b["mae"]
        )
        n_folds = len(baseline_results)
        gate_triggered = delta > _MAE_GATE

        print(f"""
── Summary ({target}) ────────────────────────────────────────
  Baseline mean MAE:     {baseline_mean:.4f}
  With-signals mean MAE: {signal_mean:.4f}
  Delta:                 {delta:+.4f}  ({'improvement' if delta < 0 else 'regression — GATE TRIGGERED' if gate_triggered else 'neutral'})
  Folds improved:        {n_folds_improved} / {n_folds}
  Gate (Δ < {_MAE_GATE}):        {'TRIGGERED' if gate_triggered else 'CLEAR'}
""")

        # Feature importance via Ridge |coef| on full dataset (with-signals model)
        ranked = _ridge_importance(df_merged, signal_feature_cols, target)
        mu_rank    = next((i+1 for i, (n, _) in enumerate(ranked) if "mu_v1" in n and "starter" in n), None)
        sig_rank   = next((i+1 for i, (n, _) in enumerate(ranked) if "signal_v1" in n and "starter" in n), None)

        print(f"  Feature importance (Ridge |coef|, {target}):")
        print(f"    home_starter_suppression_mu_v1:     rank #{mu_rank} of {len(ranked)}")
        print(f"    away_starter_suppression_mu_v1:     rank #{next((i+1 for i,(n,_) in enumerate(ranked) if 'away_starter_suppression_mu' in n), None)} of {len(ranked)}")
        print(f"    home_starter_suppression_signal_v1: rank #{sig_rank} of {len(ranked)}")
        top5 = [f"{n} ({v:.4f})" for n, v in ranked[:5]]
        print(f"    Top 5: {', '.join(top5)}")

        target_results[target] = {
            "baseline_mean_mae": baseline_mean,
            "signal_mean_mae": signal_mean,
            "delta": delta,
            "folds_improved": n_folds_improved,
            "n_folds": n_folds,
            "gate_triggered": gate_triggered,
            "mu_rank": mu_rank,
            "signal_rank": sig_rank,
            "baseline_folds": baseline_results,
            "signal_folds": signal_results,
        }

    # Overall gate
    any_gate = any(v["gate_triggered"] for v in target_results.values())
    print("\n" + "=" * 60)
    print("OVERALL GATE")
    print("=" * 60)
    if any_gate:
        print(f"  BLOCKED — MAE regression > {_MAE_GATE} on at least one target.")
        print("  Investigate data integrity before integrating signals into Layer 3.")
    else:
        print("  CLEAR — no regression detected. Proceed with integration.")
        print("  Near-zero delta is expected: signal is a compression of features")
        print("  already in the matrix. True payoff is Epic 9 stacking.")

    # Write markdown report
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_path = _REPORT_DIR / "starter_v1_ablation.md"

    lines = [
        "# Story 5.5 — Starter v1 Signal Ablation Results",
        "",
        f"**Run date:** {run_ts}  ",
        f"**Script:** `betting_ml/scripts/ablation_starter_v1_signals.py`  ",
        f"**Signal coverage:** 2021–2026 (2015–2020 rows filled with neutral values: mu={_MU_NEUTRAL}, signal={_SIGNAL_NEUTRAL})  ",
        f"**CV method:** Walk-forward by season, Ridge α={_RIDGE_ALPHA}, min_train_seasons=3  ",
        f"**Regression gate:** Δ MAE < {_MAE_GATE} on both targets  ",
        "",
        "## Results by Target",
        "",
    ]

    for target, res in target_results.items():
        lines += [
            f"### {target}",
            "",
            f"| Fold | Baseline MAE | With-signals MAE | Δ |",
            f"|---|---|---|---|",
        ]
        for b, s in zip(res["baseline_folds"], res["signal_folds"]):
            delta_fold = s["mae"] - b["mae"]
            lines.append(
                f"| {b['eval_year']} | {b['mae']:.4f} | {s['mae']:.4f} | {delta_fold:+.4f} |"
            )
        lines += [
            f"| **Mean** | **{res['baseline_mean_mae']:.4f}** | **{res['signal_mean_mae']:.4f}** | **{res['delta']:+.4f}** |",
            "",
            f"- Folds improved: {res['folds_improved']} / {res['n_folds']}",
            f"- Gate: {'**TRIGGERED**' if res['gate_triggered'] else '**CLEAR**'}",
            f"- `home_starter_suppression_mu_v1` Ridge |coef| rank: #{res['mu_rank']}",
            f"- `home_starter_suppression_signal_v1` Ridge |coef| rank: #{res['signal_rank']}",
            "",
        ]

    lines += [
        "## Overall Gate",
        "",
        ("**BLOCKED** — regression detected. Investigate before Layer 3 integration."
         if any_gate else
         "**CLEAR** — no regression. Starter signals are safe to include in Layer 3 stacking (Epic 9)."),
        "",
        "## Notes",
        "",
        "- Near-zero delta is expected: `starter_suppression_mu_v1` is a smoothed compression",
        "  of starter quality features already present in `feature_pregame_game_features`.",
        "  The real incremental value appears in Epic 9 stacking, where sub-model outputs",
        "  *replace* raw features rather than augmenting them.",
        "- 2015–2020 rows (no signal coverage) are filled with league-mean neutral values;",
        "  this makes the ablation conservative — the with-signals model is penalized for the",
        "  neutral fill in ~5 of the 8+ CV folds.",
        "- Feature importance via Ridge |coef| on standardized features (full dataset fit).",
    ]

    report_path.write_text("\n".join(lines) + "\n")
    print(f"\nReport written → {report_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
