"""
generate_starter_signals.py — Epic 5, Story 5.3

Loads the starter_v1 champion artifact (LightGBM + Normal sigma, or NGBoost Normal),
scores every regular-season game-side in feature_pregame_starter_features (2020+),
and writes four distributional signals to
baseball_data.betting_features.starter_suppression_signals via a
VARCHAR temp table + MERGE (idempotent; safe to re-run).

Output signals (one row per game × side):
    starter_suppression_mu      — Predicted mean xwOBA-against for this starter
    starter_suppression_sigma   — Predicted std of the Normal distribution
    starter_suppression_signal  — Z-score of mu relative to season mean (negative = better suppression)
    uncertainty                 — Width of the 80% Normal PI: 2 × 1.28 × sigma

Usage:
    # Backfill all 2020+ regular-season games
    uv run python betting_ml/scripts/starter_v1/generate_starter_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/starter_v1/generate_starter_signals.py --date 2026-05-29

    # Dry-run: compute without writing to Snowflake
    uv run python betting_ml/scripts/starter_v1/generate_starter_signals.py --backfill --dry-run

    # Target the dev schema (dev_betting_features) instead of prod
    uv run python betting_ml/scripts/starter_v1/generate_starter_signals.py --date 2026-06-01 --env dev
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact

_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/starter_v1.pkl"
_ARTIFACT_LOCAL  = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "starter_v1" / "starter_v1.pkl"
_MODEL_VERSION   = "starter_v1"
_TRAINING_START  = "2020-01-01"

_DB           = "baseball_data"
_WRITE_SCHEMA = {"prod": "betting_features", "dev": "dev_betting_features"}
_TABLE_NAME   = "starter_suppression_signals"
_TEMP_TABLE   = "tmp_starter_suppression_signals_incoming"


def _resolve_target(env: str) -> str:
    """Fully-qualified write target for the chosen environment.

    prod → baseball_data.betting_features.starter_suppression_signals
    dev  → baseball_data.dev_betting_features.starter_suppression_signals
    """
    return f"{_DB}.{_WRITE_SCHEMA[env]}.{_TABLE_NAME}"


def _ddl(target_table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_table} (
    game_pk                    VARCHAR(20)   NOT NULL,
    side                       VARCHAR(4)    NOT NULL,
    game_date                  DATE          NOT NULL,
    game_year                  INTEGER       NOT NULL,
    starter_suppression_mu     FLOAT         NOT NULL,
    starter_suppression_sigma  FLOAT         NOT NULL,
    starter_suppression_signal FLOAT         NOT NULL,
    uncertainty                FLOAT         NOT NULL,
    model_version              VARCHAR(20)   NOT NULL,
    ingestion_ts               TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
)
"""

_NUMERIC_FEATURES: list[str] = [
    # A: EB posteriors
    "eb_xwoba_against", "eb_k_pct", "eb_bb_pct", "eb_xwoba_uncertainty",
    # B: rolling 7d
    "xwoba_against_7d", "k_pct_7d", "bb_pct_7d", "hard_hit_pct_7d",
    "barrel_pct_7d", "whiff_rate_7d", "batter_chase_rate_7d", "avg_fastball_velo_7d",
    # C: rolling 14d
    "xwoba_against_14d", "k_pct_14d", "bb_pct_14d", "hard_hit_pct_14d",
    "barrel_pct_14d", "whiff_rate_14d", "batter_chase_rate_14d", "avg_fastball_velo_14d",
    # D: rolling 30d
    "xwoba_against_30d", "k_pct_30d", "bb_pct_30d", "hard_hit_pct_30d",
    "barrel_pct_30d", "whiff_rate_30d", "batter_chase_rate_30d", "avg_fastball_velo_30d",
    # E: rolling season-to-date
    "xwoba_against_std", "k_pct_std", "bb_pct_std", "hard_hit_pct_std",
    "barrel_pct_std", "whiff_rate_std", "batter_chase_rate_std", "avg_fastball_velo_std",
    # F: velocity & form
    "fastball_velo_trend", "avg_fastball_velo_3start", "velo_delta_3start",
    "k_pct_7d_minus_std", "xwoba_7d_minus_std",
    # G: activity
    "appearances_30d", "appearances_std",
    # H: platoon splits
    "k_pct_vs_lhb", "bb_pct_vs_lhb", "xwoba_vs_lhb", "whiff_rate_vs_lhb",
    "k_pct_vs_rhb", "bb_pct_vs_rhb", "xwoba_vs_rhb", "whiff_rate_vs_rhb",
    # I: workload / rest
    "avg_ip_last_3", "avg_ip_season", "cumulative_season_ip", "cumulative_season_pitches", "days_rest",
    # J: Stuff+ and arsenal
    "starter_stuff_plus", "starter_fastball_pct", "starter_breaking_pct",
    "starter_offspeed_pct", "starter_avg_fastball_velo",
    "starter_fastball_stuff_plus", "starter_slider_stuff_plus",
    "starter_curveball_stuff_plus", "starter_changeup_stuff_plus",
    # K: ZiPS + trailing FIP
    "starter_proj_fip", "starter_trailing_fip_30g", "starter_trailing_ra9_30g", "starter_fip_ra9_gap",
    # L: CSW & pitch mix drift
    "csw_pct_3start", "csw_pct_season",
    "fastball_pct_drift_5start", "breaking_pct_drift_5start", "offspeed_pct_drift_5start",
]

_CAT_FEATURES: list[str] = ["pitcher_hand", "starter_primary_pitch_type", "eb_data_source"]

_SCORE_QUERY = """
SELECT
    sf.game_pk,
    sf.game_date,
    sf.game_year,
    sf.side,
    sf.eb_xwoba_against,
    sf.eb_k_pct,
    sf.eb_bb_pct,
    sf.eb_xwoba_uncertainty,
    sf.xwoba_against_7d,
    sf.k_pct_7d,
    sf.bb_pct_7d,
    sf.hard_hit_pct_7d,
    sf.barrel_pct_7d,
    sf.whiff_rate_7d,
    sf.batter_chase_rate_7d,
    sf.avg_fastball_velo_7d,
    sf.xwoba_against_14d,
    sf.k_pct_14d,
    sf.bb_pct_14d,
    sf.hard_hit_pct_14d,
    sf.barrel_pct_14d,
    sf.whiff_rate_14d,
    sf.batter_chase_rate_14d,
    sf.avg_fastball_velo_14d,
    sf.xwoba_against_30d,
    sf.k_pct_30d,
    sf.bb_pct_30d,
    sf.hard_hit_pct_30d,
    sf.barrel_pct_30d,
    sf.whiff_rate_30d,
    sf.batter_chase_rate_30d,
    sf.avg_fastball_velo_30d,
    sf.xwoba_against_std,
    sf.k_pct_std,
    sf.bb_pct_std,
    sf.hard_hit_pct_std,
    sf.barrel_pct_std,
    sf.whiff_rate_std,
    sf.batter_chase_rate_std,
    sf.avg_fastball_velo_std,
    sf.fastball_velo_trend,
    sf.avg_fastball_velo_3start,
    sf.velo_delta_3start,
    sf.k_pct_7d_minus_std,
    sf.xwoba_7d_minus_std,
    sf.appearances_30d,
    sf.appearances_std,
    sf.k_pct_vs_lhb,
    sf.bb_pct_vs_lhb,
    sf.xwoba_vs_lhb,
    sf.whiff_rate_vs_lhb,
    sf.k_pct_vs_rhb,
    sf.bb_pct_vs_rhb,
    sf.xwoba_vs_rhb,
    sf.whiff_rate_vs_rhb,
    sf.avg_ip_last_3,
    sf.avg_ip_season,
    sf.cumulative_season_ip,
    sf.cumulative_season_pitches,
    sf.days_rest,
    sf.starter_stuff_plus,
    sf.starter_fastball_pct,
    sf.starter_breaking_pct,
    sf.starter_offspeed_pct,
    sf.starter_avg_fastball_velo,
    sf.starter_fastball_stuff_plus,
    sf.starter_slider_stuff_plus,
    sf.starter_curveball_stuff_plus,
    sf.starter_changeup_stuff_plus,
    sf.starter_proj_fip,
    sf.starter_trailing_fip_30g,
    sf.starter_trailing_ra9_30g,
    sf.starter_fip_ra9_gap,
    sf.csw_pct_3start,
    sf.csw_pct_season,
    sf.fastball_pct_drift_5start,
    sf.breaking_pct_drift_5start,
    sf.offspeed_pct_drift_5start,
    sf.pitcher_hand,
    sf.starter_primary_pitch_type,
    sf.eb_data_source
FROM baseball_data.betting_features.feature_pregame_starter_features sf
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = sf.game_pk
WHERE gr.game_type = 'R'
  AND sf.game_date >= '{start_date}'
  AND sf.game_date <= '{end_date}'
ORDER BY sf.game_date, sf.game_pk, sf.side
"""


# ---------------------------------------------------------------------------
# E11.1-W9-tail: read the starter feature sources (feature_pregame_starter_features +
# mart_game_results, both in S3 post-W8b) from the S3 lakehouse via DuckDB. The MERGE
# WRITE to starter_suppression_signals stays on Snowflake (the W9 export-mirror copies
# that OUTPUT to S3; re-implementing MERGE accumulate in DuckDB is the W7a-wipe class
# W9 forbids). Reuses scripts.utils.lakehouse_read. No SF dialect tokens; game_date is
# DATE in the parquet → no ::date cast needed.
# ---------------------------------------------------------------------------

def _load_games_s3(start_date: str, end_date: str):
    """Run _SCORE_QUERY against the S3 lakehouse. Returns (rows, lowercase-cols)."""
    from scripts.utils.lakehouse_read import duck_connect, register_views, strip_fqn, referenced_tables

    duck_sql = strip_fqn(_SCORE_QUERY.format(start_date=start_date, end_date=end_date))
    duck = duck_connect()
    try:
        register_views(duck, referenced_tables(_SCORE_QUERY))
        cur = duck.execute(duck_sql)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        duck.close()
    return rows, cols


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(start_date: str, end_date: str, use_s3: bool = False) -> pd.DataFrame:
    if use_s3:
        rows, cols = _load_games_s3(start_date, end_date)
    else:
        conn = get_snowflake_connection(schema="betting_features")
        try:
            cur = conn.cursor()
            cur.execute(_SCORE_QUERY.format(start_date=start_date, end_date=end_date))
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
        finally:
            conn.close()

    df = pd.DataFrame(rows, columns=cols)

    for col in df.select_dtypes(include=["object"]).columns:
        if col in _CAT_FEATURES:
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    df = df.sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Feature preparation (mirrors train_starter_v1.py logic)
# ---------------------------------------------------------------------------

def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _apply_ohe(df: pd.DataFrame, ohe_categories: list[str]) -> pd.DataFrame:
    dummies_list = []
    for cat in _CAT_FEATURES:
        d = pd.get_dummies(df[cat], prefix=cat, dtype=float)
        dummies_list.append(d)
    dummies = pd.concat(dummies_list, axis=1)
    for col in ohe_categories:
        if col not in dummies.columns:
            dummies[col] = 0.0
    dummies = dummies[ohe_categories]
    return pd.concat([df.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)


def prepare_features(df: pd.DataFrame, artifact: dict) -> np.ndarray:
    df = _apply_impute(df, artifact["impute_means"])
    df = _apply_ohe(df, artifact["ohe_categories"])
    return df[artifact["feature_names"]].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    """Return df with four Normal distributional signal columns added."""
    X = prepare_features(df, artifact)

    model_type = artifact.get("model_type", "lgbm")
    if model_type == "ngboost":
        dist = artifact["model"].pred_dist(X)
        mu    = dist.loc.astype(float)
        sigma_arr = np.clip(dist.scale.astype(float), 0.005, None)
    else:
        mu = artifact["model"].predict(X).astype(float)
        sigma_arr = np.full(len(mu), float(artifact["sigma"]))

    # Z-score relative to season mean (negative = better suppression)
    df = df.copy()
    df["_mu"] = mu
    df["_sigma_arr"] = sigma_arr
    season_mu   = df.groupby("game_year")["_mu"].transform("mean")
    season_std  = df.groupby("game_year")["_mu"].transform("std").clip(lower=1e-6)

    df["starter_suppression_mu"]     = mu
    df["starter_suppression_sigma"]  = sigma_arr
    df["starter_suppression_signal"] = (mu - season_mu) / season_std
    df["uncertainty"]                = 2.0 * 1.28 * sigma_arr

    df = df.drop(columns=["_mu", "_sigma_arr"])
    return df


# ---------------------------------------------------------------------------
# Snowflake write (VARCHAR temp table + MERGE)
# ---------------------------------------------------------------------------

def ensure_table(conn, target_table: str) -> None:
    conn.cursor().execute(_ddl(target_table))


def write_signals(conn, df: pd.DataFrame, target_table: str, dry_run: bool = False) -> dict[str, int]:
    rows = [
        (
            str(row["game_pk"]),
            str(row["side"]),
            str(row["game_date"]),
            str(int(row["game_year"])),
            str(round(float(row["starter_suppression_mu"]), 6)),
            str(round(float(row["starter_suppression_sigma"]), 6)),
            str(round(float(row["starter_suppression_signal"]), 6)),
            str(round(float(row["uncertainty"]), 6)),
            _MODEL_VERSION,
        )
        for _, row in df.iterrows()
    ]

    if dry_run:
        print(f"\n[DRY RUN] Would write {len(rows):,} rows to {target_table}.")
        print("  Sample (first 4):")
        for r in rows[:4]:
            print(f"    {r}")
        return {"inserted": 0, "updated": 0}

    cur = conn.cursor()

    cur.execute(f"""
        CREATE OR REPLACE TEMPORARY TABLE {_TEMP_TABLE} (
            game_pk                    VARCHAR,
            side                       VARCHAR,
            game_date                  VARCHAR,
            game_year                  VARCHAR,
            starter_suppression_mu     VARCHAR,
            starter_suppression_sigma  VARCHAR,
            starter_suppression_signal VARCHAR,
            uncertainty                VARCHAR,
            model_version              VARCHAR
        )
    """)

    cur.executemany(
        f"INSERT INTO {_TEMP_TABLE} VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    print(f"  Staged {len(rows):,} rows in temp table.")

    merge_sql = f"""
        MERGE INTO {target_table} AS tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)               AS game_pk,
                side::VARCHAR(4)                   AS side,
                game_date::DATE                    AS game_date,
                game_year::INTEGER                 AS game_year,
                starter_suppression_mu::FLOAT      AS starter_suppression_mu,
                starter_suppression_sigma::FLOAT   AS starter_suppression_sigma,
                starter_suppression_signal::FLOAT  AS starter_suppression_signal,
                uncertainty::FLOAT                 AS uncertainty,
                model_version::VARCHAR(20)         AS model_version
            FROM {_TEMP_TABLE}
        ) AS src
        ON  tgt.game_pk       = src.game_pk
        AND tgt.side          = src.side
        AND tgt.model_version = src.model_version
        WHEN MATCHED THEN UPDATE SET
            game_date                  = src.game_date,
            game_year                  = src.game_year,
            starter_suppression_mu     = src.starter_suppression_mu,
            starter_suppression_sigma  = src.starter_suppression_sigma,
            starter_suppression_signal = src.starter_suppression_signal,
            uncertainty                = src.uncertainty,
            ingestion_ts               = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (game_pk, side, game_date, game_year,
             starter_suppression_mu, starter_suppression_sigma,
             starter_suppression_signal, uncertainty, model_version)
        VALUES
            (src.game_pk, src.side, src.game_date, src.game_year,
             src.starter_suppression_mu, src.starter_suppression_sigma,
             src.starter_suppression_signal, src.uncertainty, src.model_version)
    """
    cur.execute(merge_sql)
    row = cur.fetchone()

    inserted = int(row[0]) if row and row[0] is not None else 0
    updated  = int(row[1]) if row and len(row) > 1 and row[1] is not None else 0
    return {"inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_sanity_checks(df: pd.DataFrame) -> None:
    mu_p5  = float(np.percentile(df["starter_suppression_mu"], 5))
    mu_p95 = float(np.percentile(df["starter_suppression_mu"], 95))
    sig_median = float(np.median(df["starter_suppression_sigma"]))
    unc_median = float(np.median(df["uncertainty"]))

    print(f"\n  starter_suppression_mu    — p5={mu_p5:.4f}  p95={mu_p95:.4f}  (expect: p5 ≥ 0.250, p95 ≤ 0.400)")
    print(f"  starter_suppression_sigma — median={sig_median:.4f}  (expect > 0)")
    print(f"  uncertainty               — median={unc_median:.4f}  (80% PI width = 2×1.28×sigma)")

    if mu_p5 < 0.250:
        print(f"  [WARN] mu p5={mu_p5:.4f} below 0.250 floor — check imputation or artifact.")
    if mu_p95 > 0.400:
        print(f"  [WARN] mu p95={mu_p95:.4f} above 0.400 ceiling — check for outliers.")
    if sig_median <= 0:
        print(f"  [WARN] sigma median ≤ 0 — model may be degenerate.")

    season_stats = (
        df.groupby("game_year")["starter_suppression_mu"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "mu_mean", "std": "mu_std"})
    )
    print("\n  mu by season (expect mean 0.290–0.330; std ≥ 0.010 to confirm spread):")
    for yr, row in season_stats.iterrows():
        flag = ""
        if not (0.250 <= row["mu_mean"] <= 0.400):
            flag = " ← WARN: mean outside expected range"
        if row["mu_std"] < 0.010:
            flag = flag or " ← WARN: std near zero — model may be degenerate"
        print(f"    {yr}  mean={row['mu_mean']:.4f}  std={row['mu_std']:.4f}{flag}")

    # Spot-check: signal should be negative for elite suppressors (low mu)
    elite = df.nsmallest(5, "starter_suppression_mu")[["game_pk", "side", "game_year",
                                                         "starter_suppression_mu",
                                                         "starter_suppression_signal"]]
    print("\n  Top 5 suppression rows (lowest mu — signal should be negative):")
    for _, r in elite.iterrows():
        flag = " ✓" if r["starter_suppression_signal"] < 0 else " ← WARN: signal not negative"
        print(f"    game_pk={r['game_pk']} side={r['side']} yr={r['game_year']} "
              f"mu={r['starter_suppression_mu']:.4f} signal={r['starter_suppression_signal']:.3f}{flag}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate starter_v1 signals (Story 5.3)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help=f"Score all games from {_TRAINING_START} through today.",
    )
    mode.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Score games for a single date.",
    )
    parser.add_argument(
        "--env",
        choices=["prod", "dev"],
        default="prod",
        help="Target environment: prod (betting_features) or dev (dev_betting_features). "
             "Default: prod. Reads always come from prod feature tables.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute signals but skip the Snowflake write.",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="E11.1-W9-tail: read feature sources from the S3 lakehouse via DuckDB "
             "instead of Snowflake. The MERGE write stays on Snowflake.",
    )
    args = parser.parse_args()

    target_table = _resolve_target(args.env)
    print(f"[{args.env.upper()}] target={target_table}")

    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    # Load artifact
    artifact_path = _ARTIFACT_S3_URI if (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("ARTIFACTS_FROM_S3")) else str(_ARTIFACT_LOCAL)
    print(f"Loading artifact from {artifact_path} ...")
    artifact = load_artifact(artifact_path)
    model_type = artifact.get("model_type", "lgbm")
    sigma = float(artifact["sigma"])
    print(f"  model_type={model_type}  cv_mae={artifact['cv_mae']:.4f}  "
          f"cv_nll={artifact['cv_nll']:.4f}  sigma={sigma:.4f}")
    print(f"  feature_count={len(artifact['feature_names'])}  "
          f"ohe_categories={len(artifact['ohe_categories'])}")

    # Load games
    print(f"\nLoading games {start_date} → {end_date} from {'S3 (DuckDB)' if args.s3 else 'Snowflake'} ...")
    df = load_games(start_date, end_date, use_s3=args.s3)
    print(f"  Loaded {len(df):,} rows ({df['game_pk'].nunique():,} games, "
          f"{df['game_year'].nunique()} seasons).")

    if df.empty:
        print("No games found for date range. Exiting.")
        return

    # Compute signals
    print("\nComputing signals ...")
    df_out = compute_signals(df, artifact)
    print(f"  Generated {len(df_out):,} signal rows with 4 signals per row.")

    run_sanity_checks(df_out)

    if args.dry_run:
        write_signals(None, df_out, target_table, dry_run=True)
        print("\n[DRY RUN] Complete. No rows written.")
        return

    # Ensure table + write
    conn = get_snowflake_connection(schema=_WRITE_SCHEMA[args.env])
    try:
        print(f"\nEnsuring table {target_table} exists ...")
        ensure_table(conn, target_table)

        print(f"Writing to {target_table} ...")
        result = write_signals(conn, df_out, target_table, dry_run=False)
    finally:
        conn.close()

    print(f"  Done. inserted={result['inserted']:,}  updated={result['updated']:,}")
    print("\nStory 5.3 complete. Next steps:")
    print("  1. Add source entry for starter_suppression_signals in dbt/models/sources.yml")
    print("  2. Update feature_pregame_sub_model_signals.sql to join on (game_pk, side, model_version='starter_v1')")
    print("  3. dbtf build --select feature_pregame_sub_model_signals")


if __name__ == "__main__":
    main()
