"""
ablation_eb_bullpen_features.py — Epic 6A.4

Walk-forward CV ablation: do EB bullpen posteriors improve total-runs prediction
compared to raw rolling bullpen effectiveness features?

Compares two feature sets on game-level total-runs prediction
using season-forward folds (min_train_seasons=1, 2021+ data):

    raw — {home/away}_bp_xwoba_against_{14d,30d},
           {home/away}_bp_k_pct_{14d,30d},
           {home/away}_bp_bb_pct_{14d,30d},
           {home/away}_bp_hard_hit_pct_{14d,30d},
           {home/away}_bp_whiff_rate_{14d,30d}

    eb  — {home/away}_bp_eb_xwoba,
           {home/away}_bp_eb_uncertainty,
           {home/away}_bp_eb_coverage_pct

Uses Ridge regression (alpha=1000) so each fold completes in seconds.
This measures incremental signal value, not final model architecture.

Gate: proceed with EB features if mean CV MAE improves OR EB reduces
      MAE in >= 2 of N folds vs. raw.

Prerequisite: run `dbtf build --select feature_pregame_team_features`
after adding the bp_eb_* columns (Epic 6A.3).

Results written to:
    betting_ml/models/ablation/ablation_eb_bullpen_{ts}.json

Usage:
    uv run python betting_ml/scripts/ablation_eb_bullpen_features.py
    uv run python betting_ml/scripts/ablation_eb_bullpen_features.py --dry-run
    uv run python betting_ml/scripts/ablation_eb_bullpen_features.py --min-year 2022
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
_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "ablation"

# ── Feature column definitions ─────────────────────────────────────────────────

_WINDOWS = ["14d", "30d"]
_SIDES = ["home", "away"]

_RAW_RATE_COLS = [
    f"{side}_bp_xwoba_against_{w}"
    for side in _SIDES for w in _WINDOWS
] + [
    f"{side}_bp_k_pct_{w}"
    for side in _SIDES for w in _WINDOWS
] + [
    f"{side}_bp_bb_pct_{w}"
    for side in _SIDES for w in _WINDOWS
] + [
    f"{side}_bp_hard_hit_pct_{w}"
    for side in _SIDES for w in _WINDOWS
] + [
    f"{side}_bp_whiff_rate_{w}"
    for side in _SIDES for w in _WINDOWS
]

_EB_RATE_COLS = [
    f"{side}_bp_eb_xwoba"
    for side in _SIDES
] + [
    f"{side}_bp_eb_uncertainty"
    for side in _SIDES
] + [
    f"{side}_bp_eb_coverage_pct"
    for side in _SIDES
]

_NON_FEATURE_COLS = {
    "game_pk", "game_date", "game_year",
    "total_runs",           # target
    *_RAW_RATE_COLS,
    *_EB_RATE_COLS,
}

# ── Data loading ───────────────────────────────────────────────────────────────

_QUERY = """
WITH home_features AS (
    SELECT
        ft.game_pk,
        ft.game_date,
        ft.game_year,
        ft.bp_xwoba_against_14d        AS home_bp_xwoba_against_14d,
        ft.bp_xwoba_against_30d        AS home_bp_xwoba_against_30d,
        ft.bp_k_pct_14d                AS home_bp_k_pct_14d,
        ft.bp_k_pct_30d                AS home_bp_k_pct_30d,
        ft.bp_bb_pct_14d               AS home_bp_bb_pct_14d,
        ft.bp_bb_pct_30d               AS home_bp_bb_pct_30d,
        ft.bp_hard_hit_pct_14d         AS home_bp_hard_hit_pct_14d,
        ft.bp_hard_hit_pct_30d         AS home_bp_hard_hit_pct_30d,
        ft.bp_whiff_rate_14d           AS home_bp_whiff_rate_14d,
        ft.bp_whiff_rate_30d           AS home_bp_whiff_rate_30d,
        ft.bp_innings_pitched_14d      AS home_bp_innings_pitched_14d,
        ft.bp_innings_pitched_30d      AS home_bp_innings_pitched_30d,
        ft.bp_eb_xwoba                 AS home_bp_eb_xwoba,
        ft.bp_eb_uncertainty           AS home_bp_eb_uncertainty,
        ft.bp_eb_coverage_pct          AS home_bp_eb_coverage_pct
    FROM baseball_data.betting_features.feature_pregame_team_features ft
    WHERE ft.side = 'home'
      AND ft.game_year >= {min_year}
),
away_features AS (
    SELECT
        ft.game_pk,
        ft.bp_xwoba_against_14d        AS away_bp_xwoba_against_14d,
        ft.bp_xwoba_against_30d        AS away_bp_xwoba_against_30d,
        ft.bp_k_pct_14d                AS away_bp_k_pct_14d,
        ft.bp_k_pct_30d                AS away_bp_k_pct_30d,
        ft.bp_bb_pct_14d               AS away_bp_bb_pct_14d,
        ft.bp_bb_pct_30d               AS away_bp_bb_pct_30d,
        ft.bp_hard_hit_pct_14d         AS away_bp_hard_hit_pct_14d,
        ft.bp_hard_hit_pct_30d         AS away_bp_hard_hit_pct_30d,
        ft.bp_whiff_rate_14d           AS away_bp_whiff_rate_14d,
        ft.bp_whiff_rate_30d           AS away_bp_whiff_rate_30d,
        ft.bp_innings_pitched_14d      AS away_bp_innings_pitched_14d,
        ft.bp_innings_pitched_30d      AS away_bp_innings_pitched_30d,
        ft.bp_eb_xwoba                 AS away_bp_eb_xwoba,
        ft.bp_eb_uncertainty           AS away_bp_eb_uncertainty,
        ft.bp_eb_coverage_pct          AS away_bp_eb_coverage_pct
    FROM baseball_data.betting_features.feature_pregame_team_features ft
    WHERE ft.side = 'away'
      AND ft.game_year >= {min_year}
)
SELECT
    h.game_pk,
    h.game_date,
    h.game_year,
    -- Raw rolling features (home + away)
    h.home_bp_xwoba_against_14d,
    h.home_bp_xwoba_against_30d,
    h.home_bp_k_pct_14d,
    h.home_bp_k_pct_30d,
    h.home_bp_bb_pct_14d,
    h.home_bp_bb_pct_30d,
    h.home_bp_hard_hit_pct_14d,
    h.home_bp_hard_hit_pct_30d,
    h.home_bp_whiff_rate_14d,
    h.home_bp_whiff_rate_30d,
    h.home_bp_innings_pitched_14d,
    h.home_bp_innings_pitched_30d,
    a.away_bp_xwoba_against_14d,
    a.away_bp_xwoba_against_30d,
    a.away_bp_k_pct_14d,
    a.away_bp_k_pct_30d,
    a.away_bp_bb_pct_14d,
    a.away_bp_bb_pct_30d,
    a.away_bp_hard_hit_pct_14d,
    a.away_bp_hard_hit_pct_30d,
    a.away_bp_whiff_rate_14d,
    a.away_bp_whiff_rate_30d,
    a.away_bp_innings_pitched_14d,
    a.away_bp_innings_pitched_30d,
    -- EB features (home + away)
    h.home_bp_eb_xwoba,
    h.home_bp_eb_uncertainty,
    h.home_bp_eb_coverage_pct,
    a.away_bp_eb_xwoba,
    a.away_bp_eb_uncertainty,
    a.away_bp_eb_coverage_pct,
    -- Target
    gr.home_final_score + gr.away_final_score AS total_runs
FROM home_features h
JOIN away_features a ON a.game_pk = h.game_pk
JOIN baseball_data.betting.mart_game_results gr ON gr.game_pk = h.game_pk
WHERE gr.game_type = 'R'
  AND gr.home_final_score IS NOT NULL
ORDER BY h.game_date, h.game_pk
"""


def _load_data(min_year: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY.format(min_year=min_year))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    for col in df.select_dtypes(include=["object"]).columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    return df


# ── CV logic ───────────────────────────────────────────────────────────────────

def _impute_train_mean(
    Xtr: pd.DataFrame, Xev: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
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
    min_train_seasons: int = 1,
) -> list[dict]:
    shared_cols = [
        c for c in df.columns
        if c not in _NON_FEATURE_COLS
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    feature_cols = shared_cols + [c for c in rate_cols if c in df.columns]

    fold_results = []
    folds = list(all_season_splits(df, min_train_seasons=min_train_seasons))
    for train_idx, eval_idx in folds:
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols].copy()
        Xev_raw = df.loc[eval_idx, feature_cols].copy()
        ytr = df.loc[train_idx, "total_runs"].values.astype(float)
        yev = df.loc[eval_idx, "total_runs"].values.astype(float)

        Xtr, Xev = _impute_train_mean(Xtr_raw, Xev_raw)

        model = Ridge(alpha=_RIDGE_ALPHA)
        model.fit(Xtr.values, ytr)
        y_pred = model.predict(Xev.values)

        mae = float(np.mean(np.abs(yev - y_pred)))
        bias = float(np.mean(y_pred - yev))

        # EB coverage diagnostic: fraction of games where EB estimate is populated
        eb_home_cov = float(df.loc[eval_idx, "home_bp_eb_xwoba"].notna().mean())
        eb_away_cov = float(df.loc[eval_idx, "away_bp_eb_xwoba"].notna().mean())

        fold_results.append({
            "tag": tag,
            "eval_year": eval_year,
            "n_eval": len(yev),
            "mae": round(mae, 4),
            "bias": round(bias, 4),
            "eb_home_coverage": round(eb_home_cov, 3),
            "eb_away_coverage": round(eb_away_cov, 3),
            "n_features": len(feature_cols),
        })
    return fold_results


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Epic 6A.4 ablation: EB vs raw bullpen rate features for total-runs prediction"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print data shape and coverage then exit without running CV")
    parser.add_argument("--min-year", type=int, default=2021,
                        help="Earliest season to include (default: 2021)")
    args = parser.parse_args()

    print("=== EPIC 6A.4 — EB BULLPEN FEATURES ABLATION ===\n")
    print(f"Loading pregame team features + game results from Snowflake (>= {args.min_year})...")

    df = _load_data(args.min_year)
    df = df.sort_values("game_date").reset_index(drop=True)
    print(f"  {len(df):,} games, seasons {sorted(df['game_year'].unique())}")
    print(f"  target total_runs: mean={df['total_runs'].mean():.3f}, "
          f"std={df['total_runs'].std():.3f}")

    print(f"\n  EB coverage by year:")
    for yr, grp in df.groupby("game_year"):
        eb_h = grp["home_bp_eb_xwoba"].notna().mean()
        eb_a = grp["away_bp_eb_xwoba"].notna().mean()
        raw_h = grp["home_bp_xwoba_against_30d"].notna().mean()
        print(f"    {yr}: home_eb={eb_h:.3f}  away_eb={eb_a:.3f}  "
              f"raw_30d_fill={raw_h:.3f}  n={len(grp)}")

    if args.dry_run:
        print("\n[DRY RUN] Exiting before CV.")
        return

    print("\n--- RAW RATES (xwoba_against/k_pct/bb_pct/hard_hit_pct/whiff_rate, 14d+30d, home+away) ---")
    raw_results = _run_fold_cv(df, _RAW_RATE_COLS, tag="raw")
    for r in raw_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  "
              f"n={r['n_eval']}  eb_cov_home={r['eb_home_coverage']:.3f}")
    raw_mean_mae = float(np.mean([r["mae"] for r in raw_results]))
    print(f"  Mean MAE: {raw_mean_mae:.4f}")

    print("\n--- EB RATES (eb_xwoba + eb_uncertainty + eb_coverage_pct, home+away) ---")
    eb_results = _run_fold_cv(df, _EB_RATE_COLS, tag="eb")
    for r in eb_results:
        print(f"  {r['eval_year']}: MAE={r['mae']:.4f}  bias={r['bias']:+.4f}  "
              f"n={r['n_eval']}  eb_cov_home={r['eb_home_coverage']:.3f}")
    eb_mean_mae = float(np.mean([r["mae"] for r in eb_results]))
    print(f"  Mean MAE: {eb_mean_mae:.4f}")

    delta = eb_mean_mae - raw_mean_mae
    folds_improved = sum(
        1 for r, b in zip(eb_results, raw_results) if r["mae"] < b["mae"]
    )

    print("\n=== SUMMARY ===")
    print(f"  Raw mean MAE:    {raw_mean_mae:.4f}")
    print(f"  EB  mean MAE:    {eb_mean_mae:.4f}")
    print(f"  Delta (EB-raw):  {delta:+.4f}  ({'IMPROVEMENT' if delta < 0 else 'REGRESSION'})")
    print(f"  Folds EB < raw:  {folds_improved} / {len(raw_results)}")

    gate_pass = delta < 0 or folds_improved >= 2
    print(f"\n  Gate: {'PASS' if gate_pass else 'FAIL'}  "
          f"(threshold: mean improvement OR >=2 folds improved)")
    if gate_pass:
        print("  -> EB bullpen features recommended for inclusion in next model version.")
    else:
        print("  -> EB bullpen features do not improve total-runs prediction; keep raw rolling.")

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = _OUTPUT_DIR / f"ablation_eb_bullpen_{ts}.json"
    payload = {
        "run_ts": ts,
        "gate_pass": gate_pass,
        "min_year": args.min_year,
        "raw_mean_mae": round(raw_mean_mae, 4),
        "eb_mean_mae": round(eb_mean_mae, 4),
        "delta_mae": round(delta, 4),
        "folds_improved": folds_improved,
        "total_folds": len(raw_results),
        "raw_folds": raw_results,
        "eb_folds": eb_results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\n  Written -> {out_path.relative_to(_PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
