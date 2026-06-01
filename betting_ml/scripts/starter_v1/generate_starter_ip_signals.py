"""
generate_starter_ip_signals.py — Story 5D.3

Loads starter_ip_v1.pkl from S3, scores every game-side in
feature_pregame_starter_features (2020+), and writes 6 distributional signals
plus is_bulk_usage to baseball_data.betting_features.starter_ip_signals
via VARCHAR temp table + MERGE (idempotent; safe to re-run).

Output signals (one row per game × side):
    starter_ip_mu         — Predicted mean outs (divide by 3.0 for innings pitched)
    starter_ip_dispersion — NegBin r parameter (fitted per predicted-mean decile)
    starter_ip_signal     — z-score of mu vs. season mean outs (negative = shorter outing)
    starter_ip_p80_outs   — 80th percentile of outs distribution
    starter_ip_p20_outs   — 20th percentile of outs distribution
    uncertainty           — PI width: p80 - p20 outs
    is_bulk_usage         — True if starter_ip_mu < 9 (matches training threshold)

Usage:
    uv run python betting_ml/scripts/starter_v1/generate_starter_ip_signals.py --backfill
    uv run python betting_ml/scripts/starter_v1/generate_starter_ip_signals.py --date 2026-06-01
    uv run python betting_ml/scripts/starter_v1/generate_starter_ip_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact

_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/starter_ip_v1.pkl"
_ARTIFACT_LOCAL  = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "starter_v1" / "starter_ip_v1.pkl"
_MODEL_VERSION   = "starter_ip_v1"
_TRAINING_START  = "2020-01-01"
_MU_CLIP_MIN     = 0.5
_MU_CLIP_MAX     = 27.0
_BULK_THRESHOLD  = 9.0   # matches training: is_bulk_usage = outs_recorded < 9

_TARGET_TABLE = "baseball_data.betting_features.starter_ip_signals"
_TEMP_TABLE   = "tmp_starter_ip_signals_incoming"

_CAT_FEATURES = ["pitcher_hand", "starter_primary_pitch_type", "starter_pitcher_archetype"]

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET_TABLE} (
    game_pk               VARCHAR(20)   NOT NULL,
    side                  VARCHAR(4)    NOT NULL,
    game_date             DATE          NOT NULL,
    game_year             INTEGER       NOT NULL,
    starter_ip_mu         FLOAT         NOT NULL,
    starter_ip_dispersion FLOAT         NOT NULL,
    starter_ip_signal     FLOAT         NOT NULL,
    starter_ip_p80_outs   FLOAT         NOT NULL,
    starter_ip_p20_outs   FLOAT         NOT NULL,
    uncertainty           FLOAT         NOT NULL,
    is_bulk_usage         BOOLEAN       NOT NULL,
    model_version         VARCHAR(20)   NOT NULL,
    ingestion_ts          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
)
"""

_SCORE_QUERY = """
WITH prior_pitch_count AS (
    SELECT
        game_pk,
        pitcher_id,
        LAG(total_pitches) OVER (
            PARTITION BY pitcher_id
            ORDER BY game_date, game_pk
        ) AS pitch_count_last_start
    FROM baseball_data.betting.mart_starting_pitcher_game_log
    WHERE game_year BETWEEN 2019 AND 2026
)
SELECT
    f.game_pk,
    f.game_date,
    f.game_year,
    f.side,
    f.pitcher_id,
    f.pitcher_hand,
    f.days_rest,
    f.avg_ip_last_3,
    f.avg_ip_season,
    f.cumulative_season_ip,
    f.cumulative_season_pitches,
    f.appearances_30d,
    f.appearances_std,
    ppc.pitch_count_last_start,
    IFF(g.double_header IN ('Y', 'S') AND g.game_number = 2, 1.0, 0.0) AS is_doubleheader_game2,
    f.starter_stuff_plus,
    f.starter_avg_fastball_velo,
    f.starter_fastball_pct,
    f.starter_breaking_pct,
    f.starter_offspeed_pct,
    f.starter_fastball_stuff_plus,
    f.starter_slider_stuff_plus,
    f.starter_curveball_stuff_plus,
    f.starter_changeup_stuff_plus,
    f.xwoba_against_30d,
    f.k_pct_30d,
    f.bb_pct_30d,
    f.whiff_rate_30d,
    f.hard_hit_pct_30d,
    f.xwoba_against_7d,
    f.k_pct_7d,
    f.fastball_velo_trend,
    f.avg_fastball_velo_30d,
    f.velo_delta_3start,
    f.starter_trailing_fip_30g,
    f.starter_trailing_ra9_30g,
    f.starter_proj_fip,
    f.csw_pct_season,
    f.csw_pct_3start,
    f.eb_xwoba_against,
    f.eb_xwoba_uncertainty,
    f.starter_primary_pitch_type,
    f.starter_pitcher_archetype
FROM baseball_data.betting_features.feature_pregame_starter_features f
LEFT JOIN prior_pitch_count ppc
    ON ppc.game_pk = f.game_pk AND ppc.pitcher_id = f.pitcher_id
LEFT JOIN baseball_data.betting.stg_statsapi_games g
    ON g.game_pk = f.game_pk
WHERE f.game_year >= 2020
  AND f.has_starter_data = TRUE
  AND f.game_date >= '{start_date}'
  AND f.game_date <= '{end_date}'
ORDER BY f.game_date, f.game_pk, f.side
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(start_date: str, end_date: str) -> pd.DataFrame:
    conn = get_snowflake_connection(schema="betting_features")
    try:
        cur = conn.cursor()
        cur.execute(_SCORE_QUERY.format(start_date=start_date, end_date=end_date))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    skip = set(_CAT_FEATURES) | {"game_pk", "side", "pitcher_id"}
    for col in df.select_dtypes(include=["object"]).columns:
        if col in skip:
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    return df.sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Feature preparation (mirrors train_starter_ip_v1.py logic)
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
# NegBin r assignment (mirrors training decile lookup)
# ---------------------------------------------------------------------------

def _assign_r(
    mu: np.ndarray,
    interior_edges: np.ndarray,
    r_by_decile: dict,
) -> np.ndarray:
    n_bins = len(interior_edges) + 1
    idx = np.clip(np.digitize(mu, interior_edges), 0, n_bins - 1)
    return np.array([r_by_decile.get(int(i), 5.0) for i in idx])


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    X = prepare_features(df, artifact)

    mu_arr = np.clip(
        artifact["model"].predict(X).astype(float),
        _MU_CLIP_MIN,
        _MU_CLIP_MAX,
    )

    r_arr = _assign_r(
        mu_arr,
        np.array(artifact["interior_edges"]),
        artifact["r_by_decile"],
    )

    p_arr   = r_arr / (r_arr + mu_arr)
    p80_arr = nbinom.ppf(0.80, r_arr, p_arr).astype(float)
    p20_arr = nbinom.ppf(0.20, r_arr, p_arr).astype(float)

    df = df.copy()
    df["_mu"] = mu_arr
    season_mean = df.groupby("game_year")["_mu"].transform("mean")
    season_std  = df.groupby("game_year")["_mu"].transform("std").clip(lower=1e-6)

    df["starter_ip_mu"]         = mu_arr
    df["starter_ip_dispersion"] = r_arr
    df["starter_ip_signal"]     = (mu_arr - season_mean.values) / season_std.values
    df["starter_ip_p80_outs"]   = p80_arr
    df["starter_ip_p20_outs"]   = p20_arr
    df["uncertainty"]           = p80_arr - p20_arr
    df["is_bulk_usage"]         = mu_arr < _BULK_THRESHOLD

    return df.drop(columns=["_mu"])


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_sanity_checks(df: pd.DataFrame) -> None:
    mu_p5      = float(np.percentile(df["starter_ip_mu"], 5))
    mu_p95     = float(np.percentile(df["starter_ip_mu"], 95))
    unc_median = float(np.median(df["uncertainty"]))
    bulk_mask  = df["is_bulk_usage"]
    bulk_mean_mu = float(df.loc[bulk_mask, "starter_ip_mu"].mean()) if bulk_mask.any() else float("nan")

    print(f"\n  starter_ip_mu   — p5={mu_p5:.2f}  p95={mu_p95:.2f}  "
          f"(expect: p5 ≥ 6.0, p95 ≤ 24.0 outs)")
    print(f"  uncertainty     — median={unc_median:.2f}  (expect > 3.0 outs)")
    print(f"  is_bulk_usage   — {bulk_mask.sum():,} rows  avg ip_mu={bulk_mean_mu:.2f}  "
          f"(expect < 12.0)")

    if mu_p5 < 6.0:
        print(f"  [WARN] ip_mu p5={mu_p5:.2f} below 6.0 floor — check imputation or artifact")
    if mu_p95 > 24.0:
        print(f"  [WARN] ip_mu p95={mu_p95:.2f} above 24.0 ceiling — check for outliers")
    if unc_median <= 3.0:
        print(f"  [WARN] uncertainty median={unc_median:.2f} ≤ 3.0 — distribution may be too narrow")
    if not np.isnan(bulk_mean_mu) and bulk_mean_mu >= 12.0:
        print(f"  [WARN] bulk rows avg ip_mu={bulk_mean_mu:.2f} ≥ 12.0 — bulk flag may be mis-assigned")

    season_stats = (
        df.groupby("game_year")["starter_ip_mu"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "mu_mean", "std": "mu_std"})
    )
    print("\n  ip_mu by season (expect mean ≈14–16 outs; std ≥ 1.0):")
    for yr, row in season_stats.iterrows():
        flag = ""
        if not (6.0 <= row["mu_mean"] <= 24.0):
            flag = " ← WARN: mean outside [6, 24]"
        print(f"    {yr}  mean={row['mu_mean']:.2f}  std={row['mu_std']:.2f}{flag}")

    bad_order = (
        (df["starter_ip_p80_outs"] <= df["starter_ip_mu"]) |
        (df["starter_ip_mu"] <= df["starter_ip_p20_outs"])
    ).sum()
    print(f"\n  Percentile ordering (p80 > mu > p20): "
          f"{len(df) - bad_order:,} / {len(df):,} rows correct")
    if bad_order > 0:
        print(f"  [WARN] {bad_order:,} rows violate p80 > mu > p20")


# ---------------------------------------------------------------------------
# Snowflake write (VARCHAR temp table + MERGE)
# ---------------------------------------------------------------------------

def ensure_table(conn) -> None:
    conn.cursor().execute(_DDL)


def write_signals(conn, df: pd.DataFrame, dry_run: bool = False) -> dict[str, int]:
    rows = [
        (
            str(row["game_pk"]),
            str(row["side"]),
            str(row["game_date"]),
            str(int(row["game_year"])),
            str(round(float(row["starter_ip_mu"]),         6)),
            str(round(float(row["starter_ip_dispersion"]), 6)),
            str(round(float(row["starter_ip_signal"]),     6)),
            str(round(float(row["starter_ip_p80_outs"]),   6)),
            str(round(float(row["starter_ip_p20_outs"]),   6)),
            str(round(float(row["uncertainty"]),           6)),
            "TRUE" if bool(row["is_bulk_usage"]) else "FALSE",
            _MODEL_VERSION,
        )
        for _, row in df.iterrows()
    ]

    if dry_run:
        print(f"\n[DRY RUN] Would write {len(rows):,} rows to {_TARGET_TABLE}.")
        print("  Sample (first 4):")
        for r in rows[:4]:
            print(f"    {r}")
        return {"inserted": 0, "updated": 0}

    cur = conn.cursor()
    cur.execute(f"""
        CREATE OR REPLACE TEMPORARY TABLE {_TEMP_TABLE} (
            game_pk               VARCHAR,
            side                  VARCHAR,
            game_date             VARCHAR,
            game_year             VARCHAR,
            starter_ip_mu         VARCHAR,
            starter_ip_dispersion VARCHAR,
            starter_ip_signal     VARCHAR,
            starter_ip_p80_outs   VARCHAR,
            starter_ip_p20_outs   VARCHAR,
            uncertainty           VARCHAR,
            is_bulk_usage         VARCHAR,
            model_version         VARCHAR
        )
    """)

    cur.executemany(
        f"INSERT INTO {_TEMP_TABLE} VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    print(f"  Staged {len(rows):,} rows in temp table.")

    merge_sql = f"""
        MERGE INTO {_TARGET_TABLE} AS tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)         AS game_pk,
                side::VARCHAR(4)             AS side,
                game_date::DATE              AS game_date,
                game_year::INTEGER           AS game_year,
                starter_ip_mu::FLOAT         AS starter_ip_mu,
                starter_ip_dispersion::FLOAT AS starter_ip_dispersion,
                starter_ip_signal::FLOAT     AS starter_ip_signal,
                starter_ip_p80_outs::FLOAT   AS starter_ip_p80_outs,
                starter_ip_p20_outs::FLOAT   AS starter_ip_p20_outs,
                uncertainty::FLOAT           AS uncertainty,
                is_bulk_usage::BOOLEAN       AS is_bulk_usage,
                model_version::VARCHAR(20)   AS model_version
            FROM {_TEMP_TABLE}
        ) AS src
        ON  tgt.game_pk       = src.game_pk
        AND tgt.side          = src.side
        AND tgt.model_version = src.model_version
        WHEN MATCHED THEN UPDATE SET
            game_date             = src.game_date,
            game_year             = src.game_year,
            starter_ip_mu         = src.starter_ip_mu,
            starter_ip_dispersion = src.starter_ip_dispersion,
            starter_ip_signal     = src.starter_ip_signal,
            starter_ip_p80_outs   = src.starter_ip_p80_outs,
            starter_ip_p20_outs   = src.starter_ip_p20_outs,
            uncertainty           = src.uncertainty,
            is_bulk_usage         = src.is_bulk_usage,
            ingestion_ts          = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (game_pk, side, game_date, game_year,
             starter_ip_mu, starter_ip_dispersion, starter_ip_signal,
             starter_ip_p80_outs, starter_ip_p20_outs, uncertainty,
             is_bulk_usage, model_version)
        VALUES
            (src.game_pk, src.side, src.game_date, src.game_year,
             src.starter_ip_mu, src.starter_ip_dispersion, src.starter_ip_signal,
             src.starter_ip_p80_outs, src.starter_ip_p20_outs, src.uncertainty,
             src.is_bulk_usage, src.model_version)
    """
    cur.execute(merge_sql)
    row = cur.fetchone()

    inserted = int(row[0]) if row and row[0] is not None else 0
    updated  = int(row[1]) if row and len(row) > 1 and row[1] is not None else 0
    return {"inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate starter_ip_v1 distributional signals (Story 5D.3)"
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
        "--dry-run",
        action="store_true",
        help="Compute signals and run sanity checks but skip the Snowflake write.",
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    # Load artifact — prefer S3 when AWS credentials present
    artifact_path = _ARTIFACT_S3_URI if os.environ.get("AWS_ACCESS_KEY_ID") else str(_ARTIFACT_LOCAL)
    print(f"Loading artifact from {artifact_path} ...")
    artifact = load_artifact(artifact_path)
    print(f"  model_type={artifact['model_type']}  cv_nll={artifact['cv_nll']:.4f}  "
          f"cv_mae={artifact['cv_mae']:.4f}  cv_calib_80={artifact['cv_calib_80']:.4f}")
    print(f"  feature_count={len(artifact['feature_names'])}  "
          f"ohe_categories={len(artifact['ohe_categories'])}")

    # Load games
    print(f"\nLoading games {start_date} → {end_date} ...")
    df = load_games(start_date, end_date)
    print(f"  Loaded {len(df):,} rows ({df['game_pk'].nunique():,} games, "
          f"{df['game_year'].nunique()} seasons).")

    if df.empty:
        print("No games found for date range. Exiting.")
        return

    # Compute signals
    print("\nComputing NegBin IP signals ...")
    df_out = compute_signals(df, artifact)
    print(f"  Generated {len(df_out):,} signal rows.")

    run_sanity_checks(df_out)

    if args.dry_run:
        write_signals(None, df_out, dry_run=True)
        print("\n[DRY RUN] Complete. No rows written.")
        return

    # Ensure table exists + write
    conn = get_snowflake_connection(schema="betting_features")
    try:
        print(f"\nEnsuring table {_TARGET_TABLE} exists ...")
        ensure_table(conn)

        print(f"Writing to {_TARGET_TABLE} ...")
        result = write_signals(conn, df_out, dry_run=False)
    finally:
        conn.close()

    print(f"\n  Done. inserted={result['inserted']:,}  updated={result['updated']:,}")
    print("\nStory 5D.3 complete. Next steps:")
    print("  1. dbtf build --select feature_pregame_sub_model_signals (Story 5D.4)")
    print("  2. Update sub_model_registry.yaml starter_ip_v1 entry (Story 5D.5)")


if __name__ == "__main__":
    main()
