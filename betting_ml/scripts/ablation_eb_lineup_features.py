"""
ablation_eb_lineup_features.py — Epic 4A.4

Walk-forward CV ablation: do EB lineup posteriors improve runs-scored prediction
compared to raw rolling-rate features?

Compares two feature sets on per-side (home/away) runs-scored prediction
using 4 season-forward folds (min_train_seasons=1, 2021+ data):

    raw   — {avg_woba_30d, avg_k_pct_30d, avg_bb_pct_30d,
              avg_woba_std, avg_k_pct_std, avg_bb_pct_std}
              + non-rate columns (handedness, injury, ZiPS, etc.)

    eb    — {avg_eb_woba, avg_eb_k_pct, avg_eb_bb_pct,
              avg_eb_iso, avg_eb_woba_uncertainty}
              + same non-rate columns

Uses Ridge regression (alpha=1000) so each fold completes in seconds.
This measures incremental signal value, not final model architecture.

Gate: proceed with EB features if mean CV MAE improves OR EB reduces
      MAE in ≥ 2 of 4 folds vs. raw.

Coverage note: eb_coverage_pct is reported per fold. Run
compute_lineup_posteriors.py for historical dates before interpreting results.

Results written to:
    betting_ml/models/sub_models/offense_v1/ablation_eb_lineup_{ts}.json

Usage:
    uv run python betting_ml/scripts/ablation_eb_lineup_features.py
    uv run python betting_ml/scripts/ablation_eb_lineup_features.py --dry-run
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
from betting_ml.utils.data_loader import get_snowflake_connection

_RIDGE_ALPHA = 1000
_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v1"

# ── Feature sets ──────────────────────────────────────────────────────────────

_RAW_RATE_COLS = [
    "avg_woba_30d",
    "avg_k_pct_30d",
    "avg_bb_pct_30d",
    "avg_woba_std",
    "avg_k_pct_std",
    "avg_bb_pct_std",
]

_EB_RATE_COLS = [
    "avg_eb_woba",
    "avg_eb_k_pct",
    "avg_eb_bb_pct",
    "avg_eb_iso",
    "avg_eb_woba_uncertainty",
]

# Columns to exclude from features (identifiers, targets, metadata)
_NON_FEATURE_COLS = {
    "game_pk", "game_date", "game_year", "side", "home_away",
    "runs_scored",                    # target
    "valid_from", "valid_to", "is_current", "computed_at", "record_hash",
    "ingestion_ts",
    "eb_coverage_pct",                # diagnostic, not a feature
    # Exclude both raw and EB rate sets — we add back the right set per run
    *_RAW_RATE_COLS,
    *_EB_RATE_COLS,
}

# ── Data loading ──────────────────────────────────────────────────────────────

_LINEUP_FEATURES_QUERY = """
SELECT
    lf.game_pk,
    lf.game_date,
    lf.game_year,
    lf.side,
    -- Raw rate columns
    lf.avg_woba_30d,
    lf.avg_k_pct_30d,
    lf.avg_bb_pct_30d,
    lf.avg_woba_std,
    lf.avg_k_pct_std,
    lf.avg_bb_pct_std,
    -- EB rate columns
    lf.avg_eb_woba,
    lf.avg_eb_k_pct,
    lf.avg_eb_bb_pct,
    lf.avg_eb_iso,
    lf.avg_eb_woba_uncertainty,
    lf.eb_coverage_pct,
    -- Non-rate lineup features (unchanged between runs)
    lf.lhb_count,
    lf.rhb_count,
    lf.avg_xwoba_30d,
    lf.avg_hard_hit_pct_30d,
    lf.avg_barrel_pct_30d,
    lf.avg_whiff_rate_30d,
    lf.avg_chase_rate_30d,
    lf.avg_xwoba_std,
    lf.avg_hard_hit_pct_std,
    lf.avg_barrel_pct_std,
    lf.avg_zips_wrc_plus,
    lf.avg_zips_woba_proxy,
    lf.avg_zips_k_pct,
    lf.avg_zips_iso,
    lf.zips_coverage_pct,
    lf.lineup_depth_score,
    lf.lineup_entropy,
    lf.lineup_rookie_count,
    lf.injured_player_count,
    lf.injury_adj_avg_woba_30d,
    -- Actual runs scored by this side (target)
    CASE
        WHEN lf.side = 'home' THEN gr.home_final_score
        ELSE gr.away_final_score
    END AS runs_scored
FROM baseball_data.betting_features.feature_pregame_lineup_features lf
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = lf.game_pk
WHERE lf.game_year >= 2021
  AND gr.game_type = 'R'
  AND gr.home_final_score IS NOT NULL
ORDER BY lf.game_date, lf.game_pk, lf.side
"""


def _load_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_LINEUP_FEATURES_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    # Convert Decimal → float
    for col in df.select_dtypes(include=["object", "str"]).columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


# ── CV logic ──────────────────────────────────────────────────────────────────

def _impute_train_mean(Xtr: pd.DataFrame, Xev: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Impute each column with its training-window mean."""
    for col in Xtr.columns:
        fill = Xtr[col].mean()
        if pd.isna(fill):
            fill = 0.0
        Xtr[col] = Xtr[col].fillna(fill)
        Xev[col] = Xev[col].fillna(fill)
    return Xtr, Xev


def _run_fold_cv(
    df: pd.DataFrame,
    rate_cols: list[str],
    tag: str,
) -> list[dict]:
    shared_cols = [
        c for c in df.columns
        if c not in _NON_FEATURE_COLS
        and c in df.select_dtypes(include=[np.number]).columns
    ]
    feature_cols = shared_cols + rate_cols

    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=1))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols].copy()
        Xev_raw = df.loc[eval_idx, feature_cols].copy()
        ytr = df.loc[train_idx, "runs_scored"].values.astype(float)
        yev = df.loc[eval_idx, "runs_scored"].values.astype(float)

        Xtr, Xev = _impute_train_mean(Xtr_raw, Xev_raw)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)

        mae = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))
        eb_cov = float(df.loc[eval_idx, "eb_coverage_pct"].mean())

        fold_results.append({
            "tag": tag,
            "eval_year": eval_year,
            "n_eval": len(yev),
            "mae": round(mae, 4),
            "bias": round(bias, 4),
            "eb_coverage_pct": round(eb_cov, 3),
            "n_features": len(feature_cols),
        })
    return fold_results


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Epic 4A.4 ablation: EB vs raw lineup rate features")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print data shape and coverage then exit without running CV")
    args = parser.parse_args()

    print("=== EPIC 4A.4 — EB LINEUP FEATURES ABLATION ===\n")

    print("Loading lineup features and game results from Snowflake...")
    df = _load_data()
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df):,} rows, seasons {sorted(df['game_year'].unique())}")
    print(f"  EB coverage by year:")
    for yr, grp in df.groupby("game_year"):
        cov = grp["eb_coverage_pct"].mean()
        eb_n = (grp["avg_eb_woba"].notna()).sum()
        print(f"    {yr}: mean_eb_coverage={cov:.3f}  eb_woba_populated={eb_n:,}/{len(grp):,}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV.")
        return

    print("\n--- RAW RATES (avg_woba_30d, avg_k_pct_30d, avg_bb_pct_30d, _std variants) ---")
    raw_results = _run_fold_cv(df, _RAW_RATE_COLS, tag="raw")
    for r in raw_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  "
              f"n={r['n_eval']}  eb_cov={r['eb_coverage_pct']:.3f}")
    raw_mean_mae = float(np.mean([r["mae"] for r in raw_results]))
    print(f"  Mean MAE: {raw_mean_mae:.4f}")

    print("\n--- EB RATES (avg_eb_woba, avg_eb_k_pct, avg_eb_bb_pct, avg_eb_iso, avg_eb_woba_uncertainty) ---")
    eb_results = _run_fold_cv(df, _EB_RATE_COLS, tag="eb")
    for r in eb_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  "
              f"n={r['n_eval']}  eb_cov={r['eb_coverage_pct']:.3f}")
    eb_mean_mae = float(np.mean([r["mae"] for r in eb_results]))
    print(f"  Mean MAE: {eb_mean_mae:.4f}")

    # Decision gate
    delta = eb_mean_mae - raw_mean_mae
    folds_improved = sum(
        1 for r, b in zip(eb_results, raw_results) if r["mae"] < b["mae"]
    )
    print("\n=== SUMMARY ===")
    print(f"  Raw mean MAE:  {raw_mean_mae:.4f}")
    print(f"  EB  mean MAE:  {eb_mean_mae:.4f}")
    print(f"  Delta (EB-raw): {delta:+.4f}  ({'IMPROVEMENT' if delta < 0 else 'REGRESSION'})")
    print(f"  Folds where EB < raw: {folds_improved} / {len(raw_results)}")

    gate_pass = delta < 0 or folds_improved >= 2
    print(f"\n  Gate: {'PASS ✓' if gate_pass else 'FAIL ✗'}  "
          f"(threshold: mean improvement OR ≥2/4 folds improved)")

    # Save results
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = _OUTPUT_DIR / f"ablation_eb_lineup_{ts}.json"
    payload = {
        "run_ts": ts,
        "gate_pass": gate_pass,
        "raw_mean_mae": round(raw_mean_mae, 4),
        "eb_mean_mae": round(eb_mean_mae, 4),
        "delta_mae": round(delta, 4),
        "folds_improved": folds_improved,
        "total_folds": len(raw_results),
        "raw_folds": raw_results,
        "eb_folds": eb_results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\n  Written → {out_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
