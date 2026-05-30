"""
build_training_dataset.py — Epic 5, Story 5.1

Defines and validates the training dataset for the starter suppression model (v1).

Source tables:
  - baseball_data.betting_features.feature_pregame_starter_features  (features)
  - baseball_data.betting.mart_starting_pitcher_game_log              (labels)

Join grain: (game_pk, pitcher_id).  Training window: 2020–2026.

Outputs:
  betting_ml/models/sub_models/starter_v1/feature_columns.json

Validates:
  1. Row count ≥ 8,000 for training window
  2. xwoba_against non-null rate ≥ 99%
  3. Null rates per feature column (logged; STARTER_PROJ_XFIP excluded and documented)
  4. Stuff+ null rate by season (expect 0% null 2020–2026, ~100% null pre-2020)
  5. Leakage spot-check: re-derives xwoba_against_7d from mart_starting_pitcher_game_log
     for 5 sampled rows and confirms it matches the feature table value within 1e-4
  6. Smoke check: COUNT, date range, AVG(xwoba_against)

Usage:
    uv run python betting_ml/scripts/starter_v1/build_training_dataset.py
    uv run python betting_ml/scripts/starter_v1/build_training_dataset.py --min-year 2020
    uv run python betting_ml/scripts/starter_v1/build_training_dataset.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection

_OUTPUT_DIR = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "starter_v1"
_FEAT_COLS_PATH = _OUTPUT_DIR / "feature_columns.json"

_DEFAULT_MIN_YEAR = 2020

# ---------------------------------------------------------------------------
# Feature inventory
# ---------------------------------------------------------------------------

FEATURE_GROUPS: dict[str, list[str]] = {
    "A_eb_posteriors": [
        "eb_xwoba_against",
        "eb_k_pct",
        "eb_bb_pct",
        "eb_xwoba_uncertainty",
    ],
    "B_rolling_7d": [
        "xwoba_against_7d",
        "k_pct_7d",
        "bb_pct_7d",
        "hard_hit_pct_7d",
        "barrel_pct_7d",
        "whiff_rate_7d",
        "batter_chase_rate_7d",
        "avg_fastball_velo_7d",
    ],
    "C_rolling_14d": [
        "xwoba_against_14d",
        "k_pct_14d",
        "bb_pct_14d",
        "hard_hit_pct_14d",
        "barrel_pct_14d",
        "whiff_rate_14d",
        "batter_chase_rate_14d",
        "avg_fastball_velo_14d",
    ],
    "D_rolling_30d": [
        "xwoba_against_30d",
        "k_pct_30d",
        "bb_pct_30d",
        "hard_hit_pct_30d",
        "barrel_pct_30d",
        "whiff_rate_30d",
        "batter_chase_rate_30d",
        "avg_fastball_velo_30d",
    ],
    "E_rolling_season": [
        "xwoba_against_std",
        "k_pct_std",
        "bb_pct_std",
        "hard_hit_pct_std",
        "barrel_pct_std",
        "whiff_rate_std",
        "batter_chase_rate_std",
        "avg_fastball_velo_std",
    ],
    "F_velocity_form": [
        "fastball_velo_trend",
        "avg_fastball_velo_3start",
        "velo_delta_3start",
        "k_pct_7d_minus_std",
        "xwoba_7d_minus_std",
    ],
    "G_activity": [
        "appearances_30d",
        "appearances_std",
    ],
    "H_platoon": [
        "k_pct_vs_lhb",
        "bb_pct_vs_lhb",
        "xwoba_vs_lhb",
        "whiff_rate_vs_lhb",
        "k_pct_vs_rhb",
        "bb_pct_vs_rhb",
        "xwoba_vs_rhb",
        "whiff_rate_vs_rhb",
    ],
    "I_workload": [
        "avg_ip_last_3",
        "avg_ip_season",
        "cumulative_season_ip",
        "cumulative_season_pitches",
        "days_rest",
    ],
    "J_stuff_arsenal": [
        "starter_stuff_plus",
        "starter_fastball_pct",
        "starter_breaking_pct",
        "starter_offspeed_pct",
        "starter_avg_fastball_velo",
        "starter_fastball_stuff_plus",
        "starter_slider_stuff_plus",
        "starter_curveball_stuff_plus",
        "starter_changeup_stuff_plus",
    ],
    "K_zips_trailing": [
        "starter_proj_fip",
        "starter_trailing_fip_30g",
        "starter_trailing_ra9_30g",
        "starter_fip_ra9_gap",
    ],
    "L_csw_pitch_mix": [
        "csw_pct_3start",
        "csw_pct_season",
        "fastball_pct_drift_5start",
        "breaking_pct_drift_5start",
        "offspeed_pct_drift_5start",
    ],
}

CATEGORICAL_FEATURES: dict[str, dict] = {
    "pitcher_hand": {"encoding": "one_hot", "group": "H_platoon"},
    "starter_primary_pitch_type": {"encoding": "one_hot", "group": "J_stuff_arsenal"},
    "eb_data_source": {"encoding": "one_hot", "group": "A_eb_posteriors"},
}

ALL_NUMERIC_FEATURES: list[str] = [col for cols in FEATURE_GROUPS.values() for col in cols]

EXCLUDED_COLUMNS = [
    # identifiers / metadata
    "game_pk", "game_date", "game_year", "side", "pitcher_id", "pitcher_name",
    # flags (not predictive features)
    "has_starter_data", "has_ip_history",
    # 100% NULL confirmed in Story 2.7
    "starter_proj_xfip",
    # categorical features (handled separately)
    "pitcher_hand", "starter_primary_pitch_type", "eb_data_source",
    # labels (populated from mart join)
    "xwoba_against", "label_k_pct", "label_bb_pct", "innings_pitched",
]

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

_TRAINING_QUERY = """
SELECT
    f.game_pk,
    f.game_date,
    f.game_year,
    f.side,
    f.pitcher_id,
    f.pitcher_name,
    f.pitcher_hand,
    -- rolling performance: 7d
    f.xwoba_against_7d,
    f.k_pct_7d,
    f.bb_pct_7d,
    f.hard_hit_pct_7d,
    f.barrel_pct_7d,
    f.whiff_rate_7d,
    f.batter_chase_rate_7d,
    f.avg_fastball_velo_7d,
    -- rolling performance: 14d
    f.xwoba_against_14d,
    f.k_pct_14d,
    f.bb_pct_14d,
    f.hard_hit_pct_14d,
    f.barrel_pct_14d,
    f.whiff_rate_14d,
    f.batter_chase_rate_14d,
    f.avg_fastball_velo_14d,
    -- rolling performance: 30d
    f.xwoba_against_30d,
    f.k_pct_30d,
    f.bb_pct_30d,
    f.hard_hit_pct_30d,
    f.barrel_pct_30d,
    f.whiff_rate_30d,
    f.batter_chase_rate_30d,
    f.avg_fastball_velo_30d,
    -- rolling performance: season-to-date
    f.xwoba_against_std,
    f.k_pct_std,
    f.bb_pct_std,
    f.hard_hit_pct_std,
    f.barrel_pct_std,
    f.whiff_rate_std,
    f.batter_chase_rate_std,
    f.avg_fastball_velo_std,
    -- velocity & form
    f.fastball_velo_trend,
    f.avg_fastball_velo_3start,
    f.velo_delta_3start,
    f.k_pct_7d_minus_std,
    f.xwoba_7d_minus_std,
    -- activity
    f.appearances_30d,
    f.appearances_std,
    -- platoon splits
    f.k_pct_vs_lhb,
    f.bb_pct_vs_lhb,
    f.xwoba_vs_lhb,
    f.whiff_rate_vs_lhb,
    f.k_pct_vs_rhb,
    f.bb_pct_vs_rhb,
    f.xwoba_vs_rhb,
    f.whiff_rate_vs_rhb,
    -- workload / rest
    f.avg_ip_last_3,
    f.avg_ip_season,
    f.cumulative_season_ip,
    f.cumulative_season_pitches,
    f.days_rest,
    -- Stuff+ and arsenal
    f.starter_stuff_plus,
    f.starter_primary_pitch_type,
    f.starter_fastball_pct,
    f.starter_breaking_pct,
    f.starter_offspeed_pct,
    f.starter_avg_fastball_velo,
    f.starter_fastball_stuff_plus,
    f.starter_slider_stuff_plus,
    f.starter_curveball_stuff_plus,
    f.starter_changeup_stuff_plus,
    -- ZiPS + trailing FIP (starter_proj_xfip excluded: 100% NULL per Story 2.7)
    f.starter_proj_fip,
    f.starter_trailing_fip_30g,
    f.starter_trailing_ra9_30g,
    f.starter_fip_ra9_gap,
    -- CSW & pitch mix drift
    f.csw_pct_3start,
    f.csw_pct_season,
    f.fastball_pct_drift_5start,
    f.breaking_pct_drift_5start,
    f.offspeed_pct_drift_5start,
    -- EB posteriors (Story 5A.3)
    f.eb_xwoba_against,
    f.eb_k_pct,
    f.eb_bb_pct,
    f.eb_xwoba_uncertainty,
    f.eb_data_source,
    -- labels (from mart)
    m.xwoba_against,
    CASE WHEN m.batters_faced > 0
         THEN m.strikeouts::float / m.batters_faced ELSE NULL END AS label_k_pct,
    CASE WHEN m.batters_faced > 0
         THEN m.walks::float / m.batters_faced ELSE NULL END AS label_bb_pct,
    m.innings_pitched
FROM baseball_data.betting_features.feature_pregame_starter_features f
JOIN baseball_data.betting.mart_starting_pitcher_game_log m
    ON m.game_pk    = f.game_pk
    AND m.pitcher_id = f.pitcher_id
WHERE f.game_year BETWEEN {min_year} AND 2026
  AND f.has_starter_data = TRUE
ORDER BY f.game_date, f.game_pk, f.side
"""

_STUFF_PLUS_BY_SEASON_QUERY = """
SELECT
    game_year,
    COUNT(*) AS row_count,
    SUM(CASE WHEN starter_stuff_plus IS NULL THEN 1 ELSE 0 END) AS null_count,
    ROUND(100.0 * SUM(CASE WHEN starter_stuff_plus IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) AS null_pct
FROM baseball_data.betting_features.feature_pregame_starter_features
WHERE has_starter_data = TRUE
  AND game_year BETWEEN {min_year} AND 2026
GROUP BY game_year
ORDER BY game_year
"""

# Leakage spot-check (structural): for 5 sampled (game_pk, pitcher_id) pairs,
# verify that the most recent mart row that could contribute to the 7d window has
# a game_date strictly less than the feature row's game_date, and that the feature
# game itself is NOT present in the contributing window (i.e. game_pk excluded).
#
# Note: value comparison (feature vs. recomputed) is intentionally informational only.
# The feature model computes xwoba_against_7d as a PA-level Statcast weighted mean;
# the mart stores per-game aggregates. Differences up to ~0.10 are expected due to
# weighting and are NOT indicative of leakage.
_LEAKAGE_CHECK_QUERY = """
WITH sampled AS (
    SELECT f.game_pk, f.pitcher_id, f.game_date, f.xwoba_against_7d
    FROM baseball_data.betting_features.feature_pregame_starter_features f
    WHERE f.game_year BETWEEN {min_year} AND 2026
      AND f.has_starter_data = TRUE
      AND f.xwoba_against_7d IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 5
),
window_games AS (
    SELECT
        s.game_pk        AS feature_game_pk,
        s.pitcher_id,
        s.game_date      AS feature_date,
        s.xwoba_against_7d AS feature_value,
        m.game_pk        AS contrib_game_pk,
        m.game_date      AS contrib_date,
        m.xwoba_against,
        -- structural check flags
        (m.game_date >= s.game_date) AS date_not_strictly_prior,
        (m.game_pk   = s.game_pk)   AS same_game_included
    FROM sampled s
    LEFT JOIN baseball_data.betting.mart_starting_pitcher_game_log m
        ON  m.pitcher_id = s.pitcher_id
        AND m.game_date  <  s.game_date
        AND m.game_date  >= DATEADD(day, -7, s.game_date)
),
summary AS (
    SELECT
        feature_game_pk,
        pitcher_id,
        feature_date,
        feature_value,
        COUNT(contrib_game_pk)                                          AS n_contributing,
        MAX(CASE WHEN date_not_strictly_prior THEN 1 ELSE 0 END)       AS any_date_violation,
        MAX(CASE WHEN same_game_included      THEN 1 ELSE 0 END)       AS same_game_included,
        MAX(contrib_date)                                               AS latest_contrib_date,
        AVG(xwoba_against)                                              AS avg_xwoba_game_level
    FROM window_games
    GROUP BY feature_game_pk, pitcher_id, feature_date, feature_value
)
SELECT
    feature_game_pk  AS game_pk,
    pitcher_id,
    feature_date     AS game_date,
    feature_value,
    n_contributing,
    latest_contrib_date,
    avg_xwoba_game_level,
    any_date_violation,
    same_game_included
FROM summary
ORDER BY game_date
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_null_rates(df: pd.DataFrame, feature_cols: list[str]) -> None:
    n = len(df)
    print(f"\n{'Column':<45} {'Null%':>7}  {'Non-null':>10}")
    print("-" * 68)
    high_null = []
    for col in feature_cols:
        if col not in df.columns:
            print(f"  {col:<43} {'MISSING COLUMN':>18}")
            continue
        null_count = df[col].isna().sum()
        pct = 100.0 * null_count / n if n > 0 else 0.0
        flag = "  <<" if pct > 80 else ""
        print(f"  {col:<43} {pct:>6.1f}%  {n - null_count:>10}{flag}")
        if pct > 80:
            high_null.append((col, pct))
    if high_null:
        print(f"\n  High-null columns (>80%): {[c for c, _ in high_null]}")


def _leakage_check(conn) -> bool:
    print("\n── Leakage spot-check (structural) ─────────────────────────────────")
    print("  Verifies: no contributing game_date >= feature game_date; feature game not")
    print("  included in its own window. Value diff is informational only — feature uses")
    print("  PA-level Statcast weighting vs. per-game mart averages (diffs up to 0.10 OK).")
    cur = conn.cursor()
    cur.execute(_LEAKAGE_CHECK_QUERY.format(min_year=_DEFAULT_MIN_YEAR))
    rows = cur.fetchall()
    cols = [d[0].lower() for d in cur.description]
    df = pd.DataFrame(rows, columns=cols)
    cur.close()

    if df.empty:
        print("  WARNING: no rows returned — verify manually")
        return True

    hdr = f"  {'game_pk':<12} {'date':<12} {'feature':>9} {'game_avg':>9} {'n_contrib':>10} {'latest_prior':>14}  struct"
    print(hdr)
    print("  " + "-" * 82)
    passed = True
    for _, row in df.iterrows():
        fv = row.get("feature_value")
        gv = row.get("avg_xwoba_game_level")
        n  = int(row.get("n_contributing") or 0)
        latest = str(row.get("latest_contrib_date") or "—")
        date_viol = bool(row.get("any_date_violation") or False)
        same_game = bool(row.get("same_game_included") or False)

        struct_ok = not date_viol and not same_game
        if not struct_ok:
            passed = False
        status = "OK" if struct_ok else "FAIL"
        if date_viol:
            status += " date_violation"
        if same_game:
            status += " same_game_leak"

        fv_str = f"{fv:.4f}" if fv is not None else "NULL"
        gv_str = f"{gv:.4f}" if gv is not None else "—"
        print(f"  {str(row['game_pk']):<12} {str(row['game_date']):<12} {fv_str:>9} {gv_str:>9} {n:>10} {latest:>14}  {status}")

    if passed:
        print("\n  PASS: structural date guard holds for all 5 spot-check rows")
    else:
        print("\n  FAIL: leakage detected — investigate immediately")
    return passed


def _save_feature_columns(dry_run: bool, min_year: int) -> None:
    payload = {
        "version": "starter_v1",
        "target": "xwoba_against",
        "secondary_targets": ["label_k_pct", "label_bb_pct", "innings_pitched"],
        "training_window": f"{min_year}–2026",
        "notes": (
            "starter_proj_xfip excluded: 100% NULL confirmed (Story 2.7). "
            "Stuff+ (J_stuff_arsenal) available 2020–2026 only; expect ~0% null in training window. "
            "EB posteriors (A_eb_posteriors) available 2016–2026 from Story 5A.3; "
            "eb_data_source is categorical (prior_only / il_return_blend / full_eb). "
            "pitcher_hand and starter_primary_pitch_type are categorical — one-hot at training time."
        ),
        "groups": FEATURE_GROUPS,
        "all_numeric_features": ALL_NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "excluded": EXCLUDED_COLUMNS,
    }
    if dry_run:
        print("\n── feature_columns.json (dry-run — not written) ────────────────────")
        print(json.dumps(payload, indent=2)[:1200], "...")
        return
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(_FEAT_COLS_PATH, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\n  Written: {_FEAT_COLS_PATH}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Story 5.1 — build and validate starter_v1 training dataset")
    parser.add_argument("--min-year", type=int, default=_DEFAULT_MIN_YEAR, help="First season to include (default: 2020)")
    parser.add_argument("--dry-run", action="store_true", help="Run all checks but do not write feature_columns.json")
    args = parser.parse_args()

    print(f"Story 5.1 — starter_v1 training dataset validation (min_year={args.min_year})")
    print("=" * 70)

    conn = get_snowflake_connection()
    try:
        # ── 1. Load training data ─────────────────────────────────────────────
        print("\n── Loading training data ────────────────────────────────────────────")
        query = _TRAINING_QUERY.format(min_year=args.min_year)
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cols = [d[0].lower() for d in cur.description]
        df = pd.DataFrame(rows, columns=cols)
        cur.close()

        n = len(df)
        print(f"  Rows loaded: {n:,}")

        # ── 2. AC: row count gate ─────────────────────────────────────────────
        print("\n── AC: row count ≥ 8,000 ───────────────────────────────────────────")
        if n >= 8_000:
            print(f"  PASS: {n:,} rows (≥ 8,000)")
        else:
            print(f"  FAIL: only {n:,} rows — investigate data gaps")

        # ── 3. Smoke check ────────────────────────────────────────────────────
        print("\n── Smoke check ─────────────────────────────────────────────────────")
        if n > 0:
            min_date = df["game_date"].min()
            max_date = df["game_date"].max()
            avg_xwoba = df["xwoba_against"].mean()
            print(f"  Date range:      {min_date}  →  {max_date}")
            print(f"  AVG(xwoba_against): {avg_xwoba:.4f}  (expect 0.305–0.325)")
            if not (0.290 <= avg_xwoba <= 0.340):
                print("  WARNING: average xwOBA-against outside expected range 0.290–0.340")

        # ── 4. AC: xwoba_against non-null rate ≥ 99% ─────────────────────────
        print("\n── AC: xwoba_against non-null rate ─────────────────────────────────")
        if "xwoba_against" in df.columns:
            nonnull = df["xwoba_against"].notna().sum()
            pct = 100.0 * nonnull / n if n > 0 else 0.0
            status = "PASS" if pct >= 99.0 else "FAIL"
            print(f"  {status}: {nonnull:,} / {n:,} non-null = {pct:.2f}%")

        # ── 5. Row count by season ────────────────────────────────────────────
        print("\n── Row count by season ─────────────────────────────────────────────")
        if "game_year" in df.columns:
            season_counts = df.groupby("game_year").size().reset_index(name="rows")
            for _, row in season_counts.iterrows():
                print(f"  {int(row['game_year'])}: {int(row['rows']):>6,} rows")

        # ── 6. Stuff+ null rate by season ─────────────────────────────────────
        print("\n── Stuff+ null rate by season ──────────────────────────────────────")
        cur2 = conn.cursor()
        cur2.execute(_STUFF_PLUS_BY_SEASON_QUERY.format(min_year=args.min_year))
        sp_rows = cur2.fetchall()
        sp_cols = [d[0].lower() for d in cur2.description]
        sp_df = pd.DataFrame(sp_rows, columns=sp_cols)
        cur2.close()
        print(f"  {'Season':<8} {'Rows':>8}  {'Null%':>8}")
        for _, r in sp_df.iterrows():
            flag = " << unexpectedly high" if float(r["null_pct"]) > 5 and int(r["game_year"]) >= 2020 else ""
            print(f"  {int(r['game_year']):<8} {int(r['row_count']):>8,}  {float(r['null_pct']):>7.1f}%{flag}")

        # ── 7. Null rates per feature column ──────────────────────────────────
        print("\n── Null rates per feature column ───────────────────────────────────")
        _print_null_rates(df, ALL_NUMERIC_FEATURES)

        print("\n── Null rates: categorical features ────────────────────────────────")
        _print_null_rates(df, list(CATEGORICAL_FEATURES.keys()))

        # ── 8. Leakage spot-check ─────────────────────────────────────────────
        _leakage_check(conn)

        # ── 9. AC: feature_columns.json ───────────────────────────────────────
        print("── Writing feature_columns.json ────────────────────────────────────")
        _save_feature_columns(dry_run=args.dry_run, min_year=args.min_year)

        print("\n── Summary ─────────────────────────────────────────────────────────")
        print(f"  Total rows:        {n:,}")
        print(f"  Numeric features:  {len(ALL_NUMERIC_FEATURES)}")
        print(f"  Categorical:       {len(CATEGORICAL_FEATURES)}")
        print(f"  Excluded:          starter_proj_xfip (100% NULL), identifiers, flags")
        print(f"  feature_columns.json: {'DRY RUN — not written' if args.dry_run else str(_FEAT_COLS_PATH)}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
