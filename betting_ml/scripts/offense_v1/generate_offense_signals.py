"""
generate_offense_signals.py — Epic 4, Story 4.3

Loads the offense_v1 champion artifact (LightGBM), scores every regular-season
game-side in feature_pregame_lineup_features, applies a scalar bias correction
derived from CV fold records, computes a per-season runs_index (100 = league avg),
and writes results to baseball_data.betting_features.offense_v1_signals via a
VARCHAR temp table + MERGE (idempotent; safe to re-run).

Bias correction:
    LightGBM CV mean bias = mean(pred − actual) ≈ −0.530 runs/game-side (retrain 2026-05-28).
    Corrected: pred_runs_raw = raw_pred − mean_cv_bias  (adds ~+0.530).
    The correction is derived from artifact["cv_fold_records"] at runtime so
    it stays in sync if the model is retrained without editing this script.

runs_index:
    For each season, season_avg = mean(pred_runs_raw) across all game-sides
    in that season. runs_index = 100 × pred_runs_raw / season_avg.
    A value > 100 means above-average run-creation environment for that side.

Usage:
    # Backfill all 2015+ regular-season games
    uv run python betting_ml/scripts/offense_v1/generate_offense_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/offense_v1/generate_offense_signals.py --date 2026-05-28

    # Dry-run: compute without writing to Snowflake
    uv run python betting_ml/scripts/offense_v1/generate_offense_signals.py --backfill --dry-run
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

_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/offense_v1.pkl"
_ARTIFACT_LOCAL  = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v1" / "lgbm_offense_v1.pkl"
_MODEL_VERSION   = "offense_v1"
_TRAINING_START  = "2015-01-01"

_TARGET_TABLE = "baseball_data.betting_features.offense_v1_signals"
_TEMP_TABLE   = "tmp_offense_v1_signals_incoming"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TARGET_TABLE} (
    game_pk          VARCHAR(20)       NOT NULL,
    side             VARCHAR(4)        NOT NULL,
    game_date        DATE              NOT NULL,
    game_year        INTEGER           NOT NULL,
    pred_runs_raw    FLOAT             NOT NULL,
    runs_index       FLOAT             NOT NULL,
    model_version    VARCHAR(20)       NOT NULL,
    ingestion_ts     TIMESTAMP_NTZ     DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_pk, side, model_version)
)
"""

_SCORE_QUERY = """
SELECT
    lf.game_pk,
    lf.game_date,
    lf.game_year,
    lf.side,
    lf.avg_eb_woba,
    lf.avg_eb_k_pct,
    lf.avg_eb_bb_pct,
    lf.avg_eb_iso,
    lf.avg_eb_woba_uncertainty,
    lf.eb_coverage_pct,
    lf.avg_woba_30d,
    lf.avg_k_pct_30d,
    lf.avg_bb_pct_30d,
    lf.avg_woba_std,
    lf.avg_k_pct_std,
    lf.avg_bb_pct_std,
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
    lf.avg_zips_wrc_plus,
    lf.avg_zips_woba_proxy,
    lf.avg_zips_k_pct,
    lf.avg_zips_iso,
    lf.zips_coverage_pct,
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
    lf.lineup_woba_vs_starter_archetype,
    lf.lineup_xwoba_vs_starter_archetype,
    lf.lineup_k_pct_vs_starter_archetype,
    lf.lineup_iso_vs_starter_archetype,
    lf.lineup_archetype_pa_coverage,
    lf.starter_pitch_archetype
FROM baseball_data.betting_features.feature_pregame_lineup_features lf
JOIN baseball_data.betting.mart_game_results gr
    ON gr.game_pk = lf.game_pk
WHERE gr.game_type = 'R'
  AND lf.game_date >= '{start_date}'
  AND lf.game_date <= '{end_date}'
ORDER BY lf.game_date, lf.game_pk, lf.side
"""

# Numeric features in the order the model expects (must match NUMERIC_FEATURES
# in train_offense_v1.py and the feature_names stored in the artifact).
_NUMERIC_FEATURES = [
    "avg_eb_woba", "avg_eb_k_pct", "avg_eb_bb_pct", "avg_eb_iso", "avg_eb_woba_uncertainty",
    "avg_woba_30d", "avg_k_pct_30d", "avg_bb_pct_30d",
    "avg_woba_std", "avg_k_pct_std", "avg_bb_pct_std",
    "avg_xwoba_30d", "avg_hard_hit_pct_30d", "avg_barrel_pct_30d",
    "avg_whiff_rate_30d", "avg_chase_rate_30d",
    "avg_xwoba_std", "avg_hard_hit_pct_std", "avg_barrel_pct_std",
    "lineup_avg_bat_speed", "lineup_bat_speed_std", "lineup_avg_swing_length",
    "lineup_avg_attack_angle", "lineup_bat_speed_vs_starter_velo",
    "avg_zips_wrc_plus", "avg_zips_woba_proxy", "avg_zips_k_pct", "avg_zips_iso",
    "zips_coverage_pct",
    "lhb_count", "rhb_count", "has_full_lineup", "lineup_depth_score", "lineup_entropy",
    "lineup_rookie_count", "lineup_rookie_pa_share", "injured_player_count",
    "injury_adj_avg_woba_30d", "injury_adj_avg_xwoba_30d",
    "eb_coverage_pct", "catcher_framing_runs", "catcher_defensive_runs",
    "avg_woba_vs_lhp", "avg_xwoba_vs_lhp", "avg_k_pct_vs_lhp",
    "avg_bb_pct_vs_lhp", "avg_hard_hit_pct_vs_lhp",
    "avg_woba_vs_rhp", "avg_xwoba_vs_rhp", "avg_k_pct_vs_rhp",
    "avg_bb_pct_vs_rhp", "avg_hard_hit_pct_vs_rhp",
    "lineup_woba_vs_starter_archetype", "lineup_xwoba_vs_starter_archetype",
    "lineup_k_pct_vs_starter_archetype", "lineup_iso_vs_starter_archetype",
    "lineup_archetype_pa_coverage",
]
_CAT_FEATURE = "starter_pitch_archetype"


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

    for col in df.select_dtypes(include=["object", "str"]).columns:
        if col == _CAT_FEATURE:
            continue
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    df["has_full_lineup"] = df["has_full_lineup"].astype(float)
    df = df.sort_values(["game_date", "game_pk", "side"]).reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Feature preparation (mirrors train_offense_v1.py logic)
# ---------------------------------------------------------------------------

def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _apply_ohe(df: pd.DataFrame, ohe_categories: list[str]) -> pd.DataFrame:
    """One-hot encode starter_pitch_archetype using the training categories."""
    dummies = pd.get_dummies(df[_CAT_FEATURE], prefix="archetype", dtype=float)
    for col in ohe_categories:
        if col not in dummies.columns:
            dummies[col] = 0.0
    dummies = dummies[ohe_categories]
    return pd.concat([df.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)


def prepare_features(df: pd.DataFrame, artifact: dict) -> np.ndarray:
    """Impute nulls, one-hot encode, and return the feature matrix."""
    df = _apply_impute(df, artifact["impute_means"])
    df = _apply_ohe(df, artifact["ohe_categories"])
    feature_names = artifact["feature_names"]
    return df[feature_names].to_numpy(dtype=float)


# ---------------------------------------------------------------------------
# Bias correction
# ---------------------------------------------------------------------------

def compute_mean_cv_bias(artifact: dict) -> float:
    """Compute mean CV bias from fold records stored in the artifact.

    bias = mean(pred − actual) per fold. A negative value means the model
    systematically under-predicts. Corrected prediction = raw − mean_bias.
    """
    fold_records = artifact.get("cv_fold_records", [])
    biases = [r["bias"] for r in fold_records if r.get("bias") is not None]
    if not biases:
        print("  [WARN] No cv_fold_records bias data found — no correction applied.")
        return 0.0
    mean_bias = float(np.mean(biases))
    print(f"  Bias correction: mean CV bias = {mean_bias:+.4f} runs/game-side "
          f"(from {len(biases)} folds; adding {-mean_bias:+.4f} to raw predictions)")
    return mean_bias


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signals(df: pd.DataFrame, artifact: dict) -> pd.DataFrame:
    """Return df with pred_runs_raw and runs_index columns added."""
    X = prepare_features(df, artifact)
    raw_preds = artifact["model"].predict(X)

    mean_bias = compute_mean_cv_bias(artifact)
    pred_corrected = raw_preds - mean_bias  # subtract negative bias → add positive offset

    df = df.copy()
    df["pred_runs_raw"] = pred_corrected

    # Per-season runs_index: 100 = league avg prediction for that season
    season_means = df.groupby("game_year")["pred_runs_raw"].transform("mean")
    df["runs_index"] = 100.0 * df["pred_runs_raw"] / season_means

    return df


# ---------------------------------------------------------------------------
# Snowflake write (VARCHAR temp table + MERGE)
# ---------------------------------------------------------------------------

def ensure_table(conn) -> None:
    conn.cursor().execute(_DDL)


def write_signals(conn, df: pd.DataFrame, dry_run: bool = False) -> dict[str, int]:
    """Write signal rows to offense_v1_signals via VARCHAR temp + MERGE.

    Returns dict with inserted and updated counts.
    """
    rows = [
        (
            str(row["game_pk"]),
            str(row["side"]),
            str(row["game_date"]),
            str(int(row["game_year"])),
            str(round(float(row["pred_runs_raw"]), 6)),
            str(round(float(row["runs_index"]), 6)),
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
            game_pk       VARCHAR,
            side          VARCHAR,
            game_date     VARCHAR,
            game_year     VARCHAR,
            pred_runs_raw VARCHAR,
            runs_index    VARCHAR,
            model_version VARCHAR
        )
    """)

    cur.executemany(
        f"INSERT INTO {_TEMP_TABLE} VALUES (%s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    print(f"  Staged {len(rows):,} rows in temp table.")

    merge_sql = f"""
        MERGE INTO {_TARGET_TABLE} AS tgt
        USING (
            SELECT
                game_pk::VARCHAR(20)   AS game_pk,
                side::VARCHAR(4)       AS side,
                game_date::DATE        AS game_date,
                game_year::INTEGER     AS game_year,
                pred_runs_raw::FLOAT   AS pred_runs_raw,
                runs_index::FLOAT      AS runs_index,
                model_version::VARCHAR(20) AS model_version
            FROM {_TEMP_TABLE}
        ) AS src
        ON  tgt.game_pk      = src.game_pk
        AND tgt.side         = src.side
        AND tgt.model_version = src.model_version
        WHEN MATCHED THEN UPDATE SET
            game_date     = src.game_date,
            game_year     = src.game_year,
            pred_runs_raw = src.pred_runs_raw,
            runs_index    = src.runs_index,
            ingestion_ts  = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (game_pk, side, game_date, game_year, pred_runs_raw, runs_index, model_version)
        VALUES
            (src.game_pk, src.side, src.game_date, src.game_year,
             src.pred_runs_raw, src.runs_index, src.model_version)
    """
    cur.execute(merge_sql)
    row = cur.fetchone()

    # Snowflake MERGE returns (rows_inserted, rows_updated) as a single result row
    inserted = int(row[0]) if row and row[0] is not None else 0
    updated  = int(row[1]) if row and len(row) > 1 and row[1] is not None else 0
    return {"inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_sanity_checks(df: pd.DataFrame) -> None:
    p5  = float(np.percentile(df["pred_runs_raw"], 5))
    p95 = float(np.percentile(df["pred_runs_raw"], 95))
    print(f"\n  pred_runs_raw  —  p5={p5:.3f}  p95={p95:.3f}  "
          f"(AC: p5 ≥ 1.5, p95 ≤ 10.0)")
    if p5 < 1.5:
        print(f"  [WARN] p5 {p5:.3f} below 1.5 sanity floor — check imputation.")
    if p95 > 10.0:
        print(f"  [WARN] p95 {p95:.3f} above 10.0 sanity ceiling — check outliers.")

    season_stats = (
        df.groupby("game_year")["runs_index"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "idx_mean", "std": "idx_std"})
    )
    # Per-game-side MAE model predicts near the conditional mean; std 1–4 is realistic
    # for per-game predictions. Higher std (8–15) is only expected once EB features
    # are fully populated (2021+) and Epic 4A stabilization has been applied.
    print("\n  runs_index by season (mean ≈ 100 by construction; std 1–4 expected for per-game model):")
    for yr, row in season_stats.iterrows():
        flag = ""
        if not (90 <= row["idx_mean"] <= 110):
            flag = " ← WARN: mean far from 100"
        if row["idx_std"] < 0.5:
            flag = flag or " ← WARN: std near zero — check features"
        print(f"    {yr}  mean={row['idx_mean']:.2f}  std={row['idx_std']:.2f}{flag}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate offense_v1 signals (Story 4.3)"
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
        help="Compute signals but skip the Snowflake write.",
    )
    args = parser.parse_args()

    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    # Load artifact
    artifact_path = _ARTIFACT_S3_URI if os.environ.get("AWS_ACCESS_KEY_ID") else _ARTIFACT_LOCAL
    print(f"Loading artifact from {artifact_path} ...")
    artifact = load_artifact(artifact_path)
    print(f"  model_type={artifact['model_type']}  cv_mae={artifact['cv_mae']}")
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
    print("\nComputing signals ...")
    df_out = compute_signals(df, artifact)
    print(f"  Generated {len(df_out):,} signal rows.")

    run_sanity_checks(df_out)

    if args.dry_run:
        write_signals(None, df_out, dry_run=True)
        print("\n[DRY RUN] Complete. No rows written.")
        return

    # Ensure table + write
    conn = get_snowflake_connection(schema="betting_features")
    try:
        print(f"\nEnsuring table {_TARGET_TABLE} exists ...")
        ensure_table(conn)

        print(f"Writing to {_TARGET_TABLE} ...")
        result = write_signals(conn, df_out, dry_run=False)
    finally:
        conn.close()

    print(f"  Done. inserted={result['inserted']:,}  updated={result['updated']:,}")
    print("\nStory 4.3 complete. Next: run `dbtf build --select feature_pregame_sub_model_signals`.")


if __name__ == "__main__":
    main()
