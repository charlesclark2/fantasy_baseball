"""
generate_offense_signals.py — Epic 4D, Story 4D.3

Loads the offense_v2 champion artifact (LightGBM + NegBin), scores every
regular-season game-side in feature_pregame_lineup_features, and writes four
distributional signals to baseball_data.betting_features.offense_v2_signals via a
VARCHAR temp table + MERGE (idempotent; safe to re-run).

Output signals (one row per game × side):
    pred_runs_mu         — NegBin conditional mean (LightGBM prediction, clipped ≥ 0.5)
    pred_runs_dispersion — Fitted NegBin r (constant per model artifact; 3.4777 for v2)
    pred_runs_raw        — Alias for pred_runs_mu (backward-compat name for downstream)
    uncertainty          — Width of the 80% NegBin predictive interval [p10, p90]

No bias correction is applied. The v1 scalar bias correction was specific to the
point-estimate model; the NegBin distributional output is used directly here.

Usage:
    # Backfill all 2015+ regular-season games
    uv run python betting_ml/scripts/offense_v2/generate_offense_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/offense_v2/generate_offense_signals.py --date 2026-05-29

    # Dry-run: compute without writing to Snowflake
    uv run python betting_ml/scripts/offense_v2/generate_offense_signals.py --backfill --dry-run

    # Target the dev schema (dev_betting_features) instead of prod
    uv run python betting_ml/scripts/offense_v2/generate_offense_signals.py --date 2026-06-01 --env dev
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

_ARTIFACT_S3_URI = "s3://baseball-betting-ml-artifacts/sub_models/offense_v2.pkl"
_ARTIFACT_LOCAL  = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "offense_v2" / "offense_v2.pkl"
_MODEL_VERSION   = "offense_v2"
_TRAINING_START  = "2015-01-01"

_DB           = "baseball_data"
_WRITE_SCHEMA = {"prod": "betting_features", "dev": "dev_betting_features"}
_TABLE_NAME   = "offense_v2_signals"
_TEMP_TABLE   = "tmp_offense_v2_signals_incoming"


def _resolve_target(env: str) -> str:
    """Fully-qualified write target for the chosen environment.

    prod → baseball_data.betting_features.offense_v2_signals
    dev  → baseball_data.dev_betting_features.offense_v2_signals
    """
    return f"{_DB}.{_WRITE_SCHEMA[env]}.{_TABLE_NAME}"


def _ddl(target_table: str) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS {target_table} (
    game_pk              VARCHAR(20)   NOT NULL,
    side                 VARCHAR(4)    NOT NULL,
    game_date            DATE          NOT NULL,
    game_year            INTEGER       NOT NULL,
    pred_runs_mu         FLOAT         NOT NULL,
    pred_runs_dispersion FLOAT         NOT NULL,
    pred_runs_raw        FLOAT         NOT NULL,
    uncertainty          FLOAT         NOT NULL,
    model_version        VARCHAR(20)   NOT NULL,
    ingestion_ts         TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP,
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

    for col in df.select_dtypes(include=["object"]).columns:
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
# Feature preparation (mirrors train_offense_v1.py / train_offense_v2.py logic)
# ---------------------------------------------------------------------------

def _apply_impute(df: pd.DataFrame, means: dict[str, float]) -> pd.DataFrame:
    df = df.copy()
    for col, val in means.items():
        if col in df.columns:
            df[col] = df[col].fillna(val)
    return df


def _apply_ohe(df: pd.DataFrame, ohe_categories: list[str]) -> pd.DataFrame:
    dummies = pd.get_dummies(df[_CAT_FEATURE], prefix="archetype", dtype=float)
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
    """Return df with four NegBin distributional signal columns added."""
    X   = prepare_features(df, artifact)
    min_mu = artifact.get("min_mu", 0.5)
    mu  = np.clip(artifact["model"].predict(X), min_mu, None)
    r   = float(artifact["negbin_r"])

    p   = r / (r + mu)
    lo  = nbinom.ppf(0.10, n=r, p=p).astype(float)
    hi  = nbinom.ppf(0.90, n=r, p=p).astype(float)

    df = df.copy()
    df["pred_runs_mu"]         = mu
    df["pred_runs_dispersion"] = r
    df["pred_runs_raw"]        = mu   # alias; used by downstream models expecting v1 column name
    df["uncertainty"]          = hi - lo

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
            str(round(float(row["pred_runs_mu"]), 6)),
            str(round(float(row["pred_runs_dispersion"]), 6)),
            str(round(float(row["pred_runs_raw"]), 6)),
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
            game_pk              VARCHAR,
            side                 VARCHAR,
            game_date            VARCHAR,
            game_year            VARCHAR,
            pred_runs_mu         VARCHAR,
            pred_runs_dispersion VARCHAR,
            pred_runs_raw        VARCHAR,
            uncertainty          VARCHAR,
            model_version        VARCHAR
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
                game_pk::VARCHAR(20)   AS game_pk,
                side::VARCHAR(4)       AS side,
                game_date::DATE        AS game_date,
                game_year::INTEGER     AS game_year,
                pred_runs_mu::FLOAT    AS pred_runs_mu,
                pred_runs_dispersion::FLOAT AS pred_runs_dispersion,
                pred_runs_raw::FLOAT   AS pred_runs_raw,
                uncertainty::FLOAT     AS uncertainty,
                model_version::VARCHAR(20) AS model_version
            FROM {_TEMP_TABLE}
        ) AS src
        ON  tgt.game_pk       = src.game_pk
        AND tgt.side          = src.side
        AND tgt.model_version = src.model_version
        WHEN MATCHED THEN UPDATE SET
            game_date            = src.game_date,
            game_year            = src.game_year,
            pred_runs_mu         = src.pred_runs_mu,
            pred_runs_dispersion = src.pred_runs_dispersion,
            pred_runs_raw        = src.pred_runs_raw,
            uncertainty          = src.uncertainty,
            ingestion_ts         = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (game_pk, side, game_date, game_year,
             pred_runs_mu, pred_runs_dispersion, pred_runs_raw, uncertainty, model_version)
        VALUES
            (src.game_pk, src.side, src.game_date, src.game_year,
             src.pred_runs_mu, src.pred_runs_dispersion, src.pred_runs_raw,
             src.uncertainty, src.model_version)
    """
    cur.execute(merge_sql)
    row = cur.fetchone()

    inserted = int(row[0]) if row and row[0] is not None else 0
    updated  = int(row[1]) if row and len(row) > 1 and row[1] is not None else 0
    return {"inserted": inserted, "updated": updated}


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------

def run_sanity_checks(df: pd.DataFrame, r: float) -> None:
    mu_p5  = float(np.percentile(df["pred_runs_mu"], 5))
    mu_p95 = float(np.percentile(df["pred_runs_mu"], 95))
    unc_p50 = float(np.percentile(df["uncertainty"], 50))
    print(f"\n  pred_runs_mu  — p5={mu_p5:.3f}  p95={mu_p95:.3f}  (expect: p5 ≥ 1.5, p95 ≤ 10.0)")
    print(f"  uncertainty   — median={unc_p50:.1f} runs  (80% PI width; expect 8–14 for r={r:.2f})")

    if mu_p5 < 1.5:
        print(f"  [WARN] pred_runs_mu p5={mu_p5:.3f} below 1.5 floor — check imputation.")
    if mu_p95 > 10.0:
        print(f"  [WARN] pred_runs_mu p95={mu_p95:.3f} above 10.0 ceiling — check outliers.")

    season_stats = (
        df.groupby("game_year")["pred_runs_mu"]
        .agg(["mean", "std", "count"])
        .rename(columns={"mean": "mu_mean", "std": "mu_std", "count": "n"})
    )
    print("\n  pred_runs_mu by season (expect mean 4.0–5.5; std 0.2–0.8 for regularized LGBM):")
    for yr, row in season_stats.iterrows():
        flag = ""
        if not (3.0 <= row["mu_mean"] <= 7.0):
            flag = " ← WARN: mean outside expected range"
        # The std-degeneracy check is only meaningful over a full-season sample.
        # Single-date / small-window scoring (e.g. the daily Dagster op) naturally
        # has a tight spread across one slate, so only flag it at full-season scale.
        if row["mu_std"] < 0.10 and row["n"] >= 100:
            flag = flag or " ← WARN: std near zero — model may be degenerate"
        elif row["mu_std"] < 0.10:
            flag = flag or f" (low std expected for small sample n={int(row['n'])})"
        print(f"    {yr}  mean={row['mu_mean']:.3f}  std={row['mu_std']:.3f}{flag}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate offense_v2 signals (Story 4D.3)"
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
    r = float(artifact["negbin_r"])
    print(f"  model_type={artifact['model_type']}  cv_mae={artifact['cv_mae']:.4f}  "
          f"cv_nll={artifact['cv_nll']:.4f}  negbin_r={r:.4f}")
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
    print(f"  Generated {len(df_out):,} signal rows with 4 signals per row.")
    print(f"  NegBin r (dispersion): {r:.4f} — constant across all game predictions.")

    run_sanity_checks(df_out, r)

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
    print("\nStory 4D.3 complete. Next steps:")
    print("  1. Update dbt/models/feature/feature_pregame_sub_model_signals.sql to")
    print("     join offense_v2_signals and expose pred_runs_mu, pred_runs_dispersion,")
    print("     pred_runs_raw, uncertainty.")
    print("  2. dbtf build --select feature_pregame_sub_model_signals")


if __name__ == "__main__":
    main()
