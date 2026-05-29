"""
build_training_dataset.py — Epic 4, Story 4.1

Verifies the offense_v1 training dataset is ready and writes the canonical
feature column inventory to feature_columns.json.

Loads from feature_pregame_lineup_features (2015–present) joined to
mart_game_results. One row per game-side (home/away). Target: runs_scored.

Training window: 2015+ (EB columns are NULL for 2015–2020; imputed to
training-window mean at fit time in train_offense_v1.py).

Walk-forward CV: all_season_splits(df, min_train_seasons=3)
  → eval years 2018–2025 (8 folds on 2015+ data)

Outputs:
    betting_ml/models/sub_models/offense_v1/feature_columns.json

Usage:
    uv run python betting_ml/scripts/offense_v1/build_training_dataset.py
    uv run python betting_ml/scripts/offense_v1/build_training_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import get_snowflake_connection

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v1"
_FEATURE_COLS_PATH = _OUTPUT_DIR / "feature_columns.json"

# ---------------------------------------------------------------------------
# Feature column inventory (Groups A–G)
# All columns are lowercased; STARTER_PITCH_ARCHETYPE encoded as one-hot in 4.2.
# ---------------------------------------------------------------------------

FEATURE_GROUPS: dict[str, list[str]] = {
    "A_eb_rates": [
        "avg_eb_woba",
        "avg_eb_k_pct",
        "avg_eb_bb_pct",
        "avg_eb_iso",
        "avg_eb_woba_uncertainty",
    ],
    "B_raw_rates": [
        "avg_woba_30d",
        "avg_k_pct_30d",
        "avg_bb_pct_30d",
        "avg_woba_std",
        "avg_k_pct_std",
        "avg_bb_pct_std",
    ],
    "C_statcast": [
        "avg_xwoba_30d",
        "avg_hard_hit_pct_30d",
        "avg_barrel_pct_30d",
        "avg_whiff_rate_30d",
        "avg_chase_rate_30d",
        "avg_xwoba_std",
        "avg_hard_hit_pct_std",
        "avg_barrel_pct_std",
        "lineup_avg_bat_speed",
        "lineup_bat_speed_std",
        "lineup_avg_swing_length",
        "lineup_avg_attack_angle",
        "lineup_bat_speed_vs_starter_velo",
    ],
    "D_zips": [
        "avg_zips_wrc_plus",
        "avg_zips_woba_proxy",
        "avg_zips_k_pct",
        "avg_zips_iso",
        "zips_coverage_pct",
    ],
    "E_structural": [
        "lhb_count",
        "rhb_count",
        "has_full_lineup",
        "lineup_depth_score",
        "lineup_entropy",
        "lineup_rookie_count",
        "lineup_rookie_pa_share",
        "injured_player_count",
        "injury_adj_avg_woba_30d",
        "injury_adj_avg_xwoba_30d",
        "eb_coverage_pct",
        "catcher_framing_runs",
        "catcher_defensive_runs",
    ],
    "F_platoon": [
        "avg_woba_vs_lhp",
        "avg_xwoba_vs_lhp",
        "avg_k_pct_vs_lhp",
        "avg_bb_pct_vs_lhp",
        "avg_hard_hit_pct_vs_lhp",
        "avg_woba_vs_rhp",
        "avg_xwoba_vs_rhp",
        "avg_k_pct_vs_rhp",
        "avg_bb_pct_vs_rhp",
        "avg_hard_hit_pct_vs_rhp",
    ],
    "G_archetype_matchup": [
        "lineup_woba_vs_starter_archetype",
        "lineup_xwoba_vs_starter_archetype",
        "lineup_k_pct_vs_starter_archetype",
        "lineup_iso_vs_starter_archetype",
        "lineup_archetype_pa_coverage",
        # starter_pitch_archetype is TEXT; one-hot encoded at training time in 4.2
        # encoded columns are added to this group as: archetype_<value> (0/1)
    ],
}

# Columns pulled from Snowflake but excluded from features (identifiers, target, SCD metadata)
_NON_FEATURE_COLS = {
    "game_pk", "game_date", "game_year", "side",
    "runs_scored",
    "starter_pitch_archetype",   # TEXT — one-hot encoded separately
    "valid_from", "valid_to", "is_current", "computed_at", "record_hash",
}

_QUERY = """
SELECT
    lf.game_pk,
    lf.game_date,
    lf.game_year,
    lf.side,
    -- Group A: EB rates
    lf.avg_eb_woba,
    lf.avg_eb_k_pct,
    lf.avg_eb_bb_pct,
    lf.avg_eb_iso,
    lf.avg_eb_woba_uncertainty,
    lf.eb_coverage_pct,
    -- Group B: raw rolling rates
    lf.avg_woba_30d,
    lf.avg_k_pct_30d,
    lf.avg_bb_pct_30d,
    lf.avg_woba_std,
    lf.avg_k_pct_std,
    lf.avg_bb_pct_std,
    -- Group C: Statcast / bat tracking
    lf.avg_xwoba_30d,
    lf.avg_hard_hit_pct_30d,
    lf.avg_barrel_pct_30d,
    lf.avg_whiff_rate_30d,
    lf.avg_chase_rate_30d,
    lf.avg_xwoba_std,
    lf.avg_hard_hit_pct_std,
    lf.avg_barrel_pct_std,
    lf.lineup_avg_bat_speed,
    lf.lineup_bat_speed_std,
    lf.lineup_avg_swing_length,
    lf.lineup_avg_attack_angle,
    lf.lineup_bat_speed_vs_starter_velo,
    -- Group D: ZiPS projections
    lf.avg_zips_wrc_plus,
    lf.avg_zips_woba_proxy,
    lf.avg_zips_k_pct,
    lf.avg_zips_iso,
    lf.zips_coverage_pct,
    -- Group E: structural / lineup composition
    lf.lhb_count,
    lf.rhb_count,
    lf.has_full_lineup,
    lf.lineup_depth_score,
    lf.lineup_entropy,
    lf.lineup_rookie_count,
    lf.lineup_rookie_pa_share,
    lf.injured_player_count,
    lf.injury_adj_avg_woba_30d,
    lf.injury_adj_avg_xwoba_30d,
    lf.catcher_framing_runs,
    lf.catcher_defensive_runs,
    -- Group F: platoon splits
    lf.avg_woba_vs_lhp,
    lf.avg_xwoba_vs_lhp,
    lf.avg_k_pct_vs_lhp,
    lf.avg_bb_pct_vs_lhp,
    lf.avg_hard_hit_pct_vs_lhp,
    lf.avg_woba_vs_rhp,
    lf.avg_xwoba_vs_rhp,
    lf.avg_k_pct_vs_rhp,
    lf.avg_bb_pct_vs_rhp,
    lf.avg_hard_hit_pct_vs_rhp,
    -- Group G: archetype matchup
    lf.lineup_woba_vs_starter_archetype,
    lf.lineup_xwoba_vs_starter_archetype,
    lf.lineup_k_pct_vs_starter_archetype,
    lf.lineup_iso_vs_starter_archetype,
    lf.lineup_archetype_pa_coverage,
    lf.starter_pitch_archetype,
    -- Target
    CASE
        WHEN lf.side = 'home' THEN gr.home_final_score
        ELSE gr.away_final_score
    END AS runs_scored
FROM baseball_data.betting_features.feature_pregame_lineup_features lf
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = lf.game_pk
WHERE gr.game_type = 'R'
  AND gr.home_final_score IS NOT NULL
ORDER BY lf.game_date, lf.game_pk, lf.side
"""


def load_data() -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    for col in df.select_dtypes(include=["object", "str"]).columns:
        if col == "starter_pitch_archetype":
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass
    df["has_full_lineup"] = df["has_full_lineup"].astype(float)
    return df


def _all_feature_cols() -> list[str]:
    cols = []
    for group_cols in FEATURE_GROUPS.values():
        cols.extend(group_cols)
    return cols


def _print_coverage_report(df: pd.DataFrame) -> None:
    print("\nYear coverage:")
    print(f"  {'Year':<6} {'Rows':>6} {'EB_woba_pct':>12} {'raw_woba_pct':>13} {'target_mean':>12}")
    for yr, grp in df.groupby("game_year"):
        eb_pct = grp["avg_eb_woba"].notna().mean()
        raw_pct = grp["avg_woba_30d"].notna().mean()
        target_mean = grp["runs_scored"].mean()
        print(f"  {yr:<6} {len(grp):>6} {eb_pct:>12.1%} {raw_pct:>13.1%} {target_mean:>12.3f}")
    print(f"\n  Total rows: {len(df):,}")
    print(f"  Target mean: {df['runs_scored'].mean():.3f}  std: {df['runs_scored'].std():.3f}")


def _print_fold_inventory(df: pd.DataFrame) -> None:
    print("\nWalk-forward fold inventory (min_train_seasons=3):")
    print(f"  {'Fold':<5} {'Train years':<30} {'Eval year':<10} {'Train rows':>10} {'Eval rows':>10}")
    folds = list(all_season_splits(df, min_train_seasons=3))
    for i, (train_idx, eval_idx) in enumerate(folds, 1):
        train_years = sorted(df.loc[train_idx, "game_year"].unique())
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        yr_str = f"{train_years[0]}–{train_years[-1]}"
        print(f"  {i:<5} {yr_str:<30} {eval_year:<10} {len(train_idx):>10,} {len(eval_idx):>10,}")
    print(f"\n  Total folds: {len(folds)}")


def _check_2018_gap(df: pd.DataFrame) -> None:
    rows_2018 = (df["game_year"] == 2018).sum()
    if rows_2018 < 4500:
        print(f"\n  NOTE: 2018 has {rows_2018:,} rows (expected ~4,860). Known mart_game_results gap.")


def _write_feature_columns_json() -> None:
    all_numeric_cols = _all_feature_cols()
    payload = {
        "version": "offense_v1",
        "target": "runs_scored",
        "training_window": "2015+",
        "notes": (
            "Group A (EB rates) is NULL for 2015-2020; imputed to training-window mean at fit time. "
            "Group C bat-tracking cols (lineup_avg_bat_speed etc.) available from ~2023-07-14 only; "
            "~50% null in 2021+ training set. "
            "starter_pitch_archetype is TEXT; one-hot encoded at training time and added to Group G."
        ),
        "groups": FEATURE_GROUPS,
        "all_numeric_features": all_numeric_cols,
        "categorical_features": {
            "starter_pitch_archetype": {
                "encoding": "one_hot",
                "group": "G_archetype_matchup",
            }
        },
        "excluded": sorted(_NON_FEATURE_COLS),
    }
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _FEATURE_COLS_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\n  Written → {_FEATURE_COLS_PATH.relative_to(_PROJECT_ROOT)}")


def _run_acceptance_checks(df: pd.DataFrame) -> bool:
    passed = True

    # Check year range
    years = sorted(df["game_year"].unique())
    if min(years) > 2015:
        print(f"  FAIL: earliest year is {min(years)}, expected 2015")
        passed = False
    else:
        print(f"  PASS: year range {min(years)}–{max(years)}")

    # Check EB NULL for 2015-2020
    pre_2020 = df[df["game_year"] < 2021]
    if pre_2020["avg_eb_woba"].notna().any():
        print(f"  WARN: avg_eb_woba non-NULL for {pre_2020['avg_eb_woba'].notna().sum()} pre-2021 rows")
    else:
        print(f"  PASS: avg_eb_woba NULL for all {len(pre_2020):,} pre-2021 rows")

    # Check EB populated for 2021+
    post_2020 = df[df["game_year"].between(2021, 2025)]
    eb_pct = post_2020["avg_eb_woba"].notna().mean()
    if eb_pct < 0.95:
        print(f"  WARN: avg_eb_woba only {eb_pct:.1%} populated for 2021–2025 (expected ~100%)")
    else:
        print(f"  PASS: avg_eb_woba {eb_pct:.1%} populated for 2021–2025")

    # Check raw rates populated
    raw_pct = df["avg_woba_30d"].notna().mean()
    if raw_pct < 0.95:
        print(f"  WARN: avg_woba_30d only {raw_pct:.1%} populated (expected ~99%)")
    else:
        print(f"  PASS: avg_woba_30d {raw_pct:.1%} populated")

    # Check fold count — expect ≥ 8 (8 on 2015–2025 data; +1 per additional live season)
    folds = list(all_season_splits(df, min_train_seasons=3))
    if len(folds) < 8:
        print(f"  FAIL: expected ≥ 8 folds, got {len(folds)}")
        passed = False
    else:
        eval_years = [int(df.loc[ev, "game_year"].mode()[0]) for _, ev in folds]
        print(f"  PASS: {len(folds)} walk-forward folds (eval years {eval_years[0]}–{eval_years[-1]})")

    # Check final fold train size
    if folds:
        final_train_idx, _ = folds[-1]
        n_final_train = len(final_train_idx)
        if n_final_train < 40_000:
            print(f"  WARN: final fold train rows = {n_final_train:,} (expected ~44k)")
        else:
            print(f"  PASS: final fold train rows = {n_final_train:,}")

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="Epic 4.1 — offense_v1 training dataset verification")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Snowflake; write feature_columns.json only")
    args = parser.parse_args()

    print("=== EPIC 4.1 — OFFENSE_V1 TRAINING DATASET ===\n")

    _write_feature_columns_json()

    if args.dry_run:
        print("\n[DRY RUN] Snowflake query skipped.")
        return

    print("\nLoading data from Snowflake...")
    df = load_data()
    df = df.sort_values("game_date").reset_index(drop=True)

    _print_coverage_report(df)
    _check_2018_gap(df)
    _print_fold_inventory(df)

    print("\n=== ACCEPTANCE CHECKS ===")
    ok = _run_acceptance_checks(df)
    print(f"\n  Overall: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
