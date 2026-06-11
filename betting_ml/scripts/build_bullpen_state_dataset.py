"""
build_bullpen_state_dataset.py — Epic 6.1 / 16B.2

Assembles the training dataset for the Epic 6 bullpen state model.

Grain: pitching_team × game_pk (pre-game features + post-game target).

Features (all pre-game, no leakage):
  Workload  — mart_bullpen_workload:
    bullpen_ip_prev_{1,2,3}d
    bullpen_pitches_prev_{3,7}d
    pitchers_used_prev_{2,3,7}d
    reliever_appearances_prev_{3,7}d
    high_leverage_used_prev_2d
    closer_used_prev_{1,2}d

  Quality rolling — mart_bullpen_effectiveness:
    xwoba_against_{14,30}d, k_pct_{14,30}d, bb_pct_{14,30}d,
    hard_hit_pct_{14,30}d, whiff_rate_{14,30}d, innings_pitched_{14,30}d

  EB posteriors — mart_bullpen_effectiveness (via Epic 6A.3):
    eb_bullpen_xwoba, eb_bullpen_uncertainty, eb_bullpen_coverage_pct

  Sequential posterior (Epic 16B.2) — team_sequential_posteriors:
    team_sequential_bullpen_xwoba  (as-of-date: latest game_date < scoring_date)
    posterior_source               (1 if sequential posterior available, else 0)

  Top-3 leverage arm availability (Story 6.6) — mart_reliever_top3_availability:
    closer_available   (1 = closer not used yesterday; NULL → imputed 1)
    closer_rest_days   (days since last outing; NULL when no prior 30-day data)
    setup1_available   (same for rank-2 arm)
    setup1_rest_days
    setup2_available   (same for rank-3 arm)
    setup2_rest_days

Target (post-game, computed from pitch data):
  actual_bullpen_xwoba — game-level xwOBA against for the team's relievers
  in the current game. Used as the training target for Story 6.3 (bullpen
  quality model). High per-game variance (~0.05–0.50); shrinkage models
  expected to show substantial improvement over naive rolling averages.

Note: the bullpen availability index (Story 6.2) will be computed from
workload columns and merged into this dataset before 6.3 training.

Training window: 2016+ (EB posterior coverage starts 2016).
  Epic 16B.2 sequential retrain: use --min-year 2021 (sequential posteriors
  only backfilled to 2021+; pre-2021 rows will have NULL team_sequential_bullpen_xwoba).

Requires: dbtf build --select mart_bullpen_workload --full-refresh
          (to pick up the new bullpen_ip_prev_3d column from 6.1)
          dbtf build --select feature_pregame_team_features
          (EB columns already backfilled in mart_bullpen_effectiveness)

Output: betting_ml/data/bullpen_state_train.parquet

Usage:
    uv run python betting_ml/scripts/build_bullpen_state_dataset.py
    uv run python betting_ml/scripts/build_bullpen_state_dataset.py --dry-run
    uv run python betting_ml/scripts/build_bullpen_state_dataset.py --min-year 2021
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

_OUTPUT_PATH = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"

# ── Main query ─────────────────────────────────────────────────────────────────
# Joins workload + effectiveness marts and computes actual_bullpen_xwoba from
# pitch-level data as the training target. Relievers are identified as any
# pitcher NOT in mart_starting_pitcher_game_log — identical to the mart logic.
_QUERY = """
WITH

-- ── Actual game-level bullpen xwOBA (post-game target) ─────────────────────
-- Uses same reliever definition as mart_bullpen_effectiveness:
-- any pitcher who is NOT the qualifying starter.
reliever_pitches AS (
    SELECT
        p.game_pk,
        p.game_date,
        p.game_year,
        CASE WHEN p.inning_half = 'Top' THEN p.home_team ELSE p.away_team END
            AS pitching_team,
        CASE WHEN p.woba_denom = 1
            THEN COALESCE(p.xwoba, p.woba_value) ELSE 0 END   AS xwoba_num,
        COALESCE(p.woba_denom, 0)                              AS xwoba_den
    FROM baseball_data.betting.stg_batter_pitches p
    LEFT JOIN baseball_data.betting.mart_starting_pitcher_game_log s
        ON  p.game_pk       = s.game_pk
        AND p.pitcher_id    = s.pitcher_id
        AND CASE WHEN p.inning_half = 'Top' THEN p.home_team ELSE p.away_team END
            = s.pitching_team
    WHERE s.pitcher_id IS NULL
      AND p.game_type   = 'R'
      AND p.game_year   >= {min_year}
),

actual_xwoba AS (
    SELECT
        game_pk,
        game_date,
        game_year,
        pitching_team,
        ROUND(SUM(xwoba_num) / NULLIF(SUM(xwoba_den), 0), 4) AS actual_bullpen_xwoba,
        SUM(xwoba_den)                                         AS actual_bullpen_pa
    FROM reliever_pitches
    GROUP BY game_pk, game_date, game_year, pitching_team
),

-- ── Pre-game workload features ──────────────────────────────────────────────
workload AS (
    SELECT
        game_pk,
        pitching_team,
        bullpen_ip_prev_1d,
        bullpen_ip_prev_2d,
        bullpen_ip_prev_3d,
        bullpen_pitches_prev_3d,
        bullpen_pitches_prev_7d,
        pitchers_used_prev_2d,
        pitchers_used_prev_3d,
        pitchers_used_prev_7d,
        reliever_appearances_prev_3d,
        reliever_appearances_prev_7d,
        high_leverage_used_prev_2d,
        closer_used_prev_1d,
        closer_used_prev_2d
    FROM baseball_data.betting.mart_bullpen_workload
    WHERE game_year >= {min_year}
),

-- ── Pre-game quality + EB features ─────────────────────────────────────────
effectiveness AS (
    SELECT
        game_pk,
        team_abbrev                AS pitching_team,
        xwoba_against_14d,
        k_pct_14d,
        bb_pct_14d,
        hard_hit_pct_14d,
        whiff_rate_14d,
        innings_pitched_14d,
        xwoba_against_30d,
        k_pct_30d,
        bb_pct_30d,
        hard_hit_pct_30d,
        whiff_rate_30d,
        innings_pitched_30d,
        eb_bullpen_xwoba,
        eb_bullpen_uncertainty,
        eb_bullpen_coverage_pct
    FROM baseball_data.betting.mart_bullpen_effectiveness
    WHERE game_year >= {min_year}
),

-- ── Sequential bullpen posterior — as-of-date via interval join ─────────────
-- Snowflake does not support LEFT JOIN LATERAL with this correlated subquery
-- type. Window-function workaround: for each (team, game_date) posterior row
-- compute the validity interval [valid_from, valid_until]. A game on date G
-- uses the posterior where valid_from < G <= valid_until (valid_from is
-- post-game so strictly-before is leakage-safe; valid_until is also post-game,
-- so the game played on that date may still use the prior-period posterior).
seq_intervals AS (
    SELECT
        team,
        game_date                                                              AS valid_from,
        LEAD(game_date) OVER (PARTITION BY team ORDER BY game_date)           AS valid_until,
        posterior_mu
    FROM baseball_data.betting.team_sequential_posteriors
    WHERE metric = 'bullpen_xwoba'
),

-- ── Top-3 leverage arm availability (Story 6.6) ──────────────────────────────
top3_avail AS (
    SELECT
        game_pk,
        team_abbrev,
        closer_available,
        closer_rest_days,
        setup1_available,
        setup1_rest_days,
        setup2_available,
        setup2_rest_days
    FROM baseball_data.betting.mart_reliever_top3_availability
    WHERE game_pk IN (SELECT DISTINCT game_pk FROM actual_xwoba)
)

SELECT
    ax.game_pk,
    ax.game_date,
    ax.game_year,
    ax.pitching_team,

    -- ── Target ──────────────────────────────────────────────────────────────
    ax.actual_bullpen_xwoba,
    ax.actual_bullpen_pa,

    -- ── Workload (fatigue / availability) ───────────────────────────────────
    w.bullpen_ip_prev_1d,
    w.bullpen_ip_prev_2d,
    w.bullpen_ip_prev_3d,
    w.bullpen_pitches_prev_3d,
    w.bullpen_pitches_prev_7d,
    w.pitchers_used_prev_2d,
    w.pitchers_used_prev_3d,
    w.pitchers_used_prev_7d,
    w.reliever_appearances_prev_3d,
    w.reliever_appearances_prev_7d,
    w.high_leverage_used_prev_2d,
    w.closer_used_prev_1d,
    w.closer_used_prev_2d,

    -- ── Rolling quality ──────────────────────────────────────────────────────
    e.xwoba_against_14d,
    e.k_pct_14d,
    e.bb_pct_14d,
    e.hard_hit_pct_14d,
    e.whiff_rate_14d,
    e.innings_pitched_14d,
    e.xwoba_against_30d,
    e.k_pct_30d,
    e.bb_pct_30d,
    e.hard_hit_pct_30d,
    e.whiff_rate_30d,
    e.innings_pitched_30d,

    -- ── Empirical Bayes (Epic 6A.3) ──────────────────────────────────────────
    e.eb_bullpen_xwoba,
    e.eb_bullpen_uncertainty,
    e.eb_bullpen_coverage_pct,

    -- ── Sequential bullpen posterior (Epic 16B.2) ───────────────────────────
    -- As-of-date: latest posterior updated BEFORE this game (leakage-safe).
    -- NULL for pre-2021 games and season openers before first observation.
    si.posterior_mu                                           AS team_sequential_bullpen_xwoba,
    CASE WHEN si.posterior_mu IS NOT NULL THEN 1 ELSE 0 END  AS posterior_source,

    -- ── Top-3 leverage arm availability (Story 6.6) ──────────────────────────
    -- NULL when no prior 30-day appearances (season openers); impute to 1 in
    -- preprocessing. Leakage-free: mart uses strictly-prior appearances.
    ta.closer_available,
    ta.closer_rest_days,
    ta.setup1_available,
    ta.setup1_rest_days,
    ta.setup2_available,
    ta.setup2_rest_days

FROM actual_xwoba ax
LEFT JOIN workload w
    ON  ax.game_pk       = w.game_pk
    AND ax.pitching_team = w.pitching_team
LEFT JOIN effectiveness e
    ON  ax.game_pk       = e.game_pk
    AND ax.pitching_team = e.pitching_team
LEFT JOIN seq_intervals si
    ON  si.team      = ax.pitching_team
    AND ax.game_date > si.valid_from
    AND (si.valid_until IS NULL OR ax.game_date <= si.valid_until)
LEFT JOIN top3_avail ta
    ON  ta.game_pk     = ax.game_pk
    AND ta.team_abbrev = ax.pitching_team

ORDER BY ax.game_date, ax.game_pk, ax.pitching_team
"""


def _print_coverage(df: pd.DataFrame) -> None:
    print(f"\n  {len(df):,} rows | {df['game_year'].nunique()} seasons "
          f"[{int(df['game_year'].min())}–{int(df['game_year'].max())}]")
    print(f"  target actual_bullpen_xwoba: mean={df['actual_bullpen_xwoba'].mean():.3f}, "
          f"std={df['actual_bullpen_xwoba'].std():.3f}")

    has_seq = "team_sequential_bullpen_xwoba" in df.columns
    print("\n  Coverage by year:")
    for yr, grp in df.groupby("game_year"):
        n = len(grp)
        eb_fill = grp["eb_bullpen_xwoba"].notna().mean()
        ip3d_fill = grp["bullpen_ip_prev_3d"].notna().mean()
        xwoba30_fill = grp["xwoba_against_30d"].notna().mean()
        target_fill = grp["actual_bullpen_xwoba"].notna().mean()
        seq_fill = grp["team_sequential_bullpen_xwoba"].notna().mean() if has_seq else float("nan")
        seq_str = f"  seq={seq_fill:.3f}" if has_seq else ""
        print(f"    {int(yr)}: n={n:4d}  eb={eb_fill:.3f}  "
              f"ip_3d={ip3d_fill:.3f}  xwoba_30d={xwoba30_fill:.3f}  "
              f"target={target_fill:.3f}{seq_str}")

    print("\n  Null rates for key columns:")
    key_cols = [
        "actual_bullpen_xwoba",
        "eb_bullpen_xwoba", "eb_bullpen_uncertainty", "eb_bullpen_coverage_pct",
        "bullpen_ip_prev_1d", "bullpen_ip_prev_2d", "bullpen_ip_prev_3d",
        "xwoba_against_14d", "xwoba_against_30d",
        "team_sequential_bullpen_xwoba",
        "closer_available", "setup1_available", "setup2_available",
    ]
    for col in key_cols:
        if col not in df.columns:
            continue
        null_pct = df[col].isna().mean() * 100
        print(f"    {col:<35s} {null_pct:5.1f}% null")


def _load(min_year: int) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY.format(min_year=min_year))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Epic 6.1 — assemble bullpen state model training dataset"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print coverage stats but do not write parquet")
    parser.add_argument("--min-year", type=int, default=2016,
                        help="Earliest season to include (default: 2016)")
    args = parser.parse_args()

    print(f"=== EPIC 6.1 — BULLPEN STATE TRAINING DATASET ===\n")
    print(f"Loading from Snowflake (>= {args.min_year})...")

    df = _load(args.min_year)
    _print_coverage(df)

    if args.dry_run:
        print("\n[dry-run] Skipping parquet write.")
        return

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUTPUT_PATH, index=False)
    print(f"\nWritten -> {_OUTPUT_PATH}")
    print(f"  Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")


if __name__ == "__main__":
    main()
