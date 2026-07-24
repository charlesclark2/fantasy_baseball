"""
generate_run_env_signals.py — Run environment signal generation (Epic 3D, Story 3D.3)

Loads the trained run_env_v4 artifact (Ridge + Negative Binomial) and writes
three distributional signals per game into mart_sub_model_signals via the
SCD-2 writer:

  run_env_mu           — NegBin predicted mean total runs (μ); primary signal.
                         Positive values indicate a high-scoring environment.

  run_env_dispersion   — NegBin dispersion parameter r fitted on training data.
                         Constant across all games for a given model version;
                         stored per row for downstream join convenience.

  run_env_signal       — z-scored μ: (mu - target_mean) / target_std
                         Retained for backwards-compatible downstream joins
                         (matches the signal_name used by run_env_v3).

All three signals carry an `uncertainty` value — the game-level 80% predictive
interval width from NegBin(mu_i, r): ppf(0.90) - ppf(0.10).

Signals are written as separate rows for side='home' and side='away' so the
feature mart can join on (game_pk, side).

Usage:
    # Backfill all 2021+ completed regular-season games
    uv run python betting_ml/scripts/generate_run_env_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/generate_run_env_signals.py --date 2026-05-19

    # Dry-run: compute without writing
    uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV
from betting_ml.scripts.train_run_env_v3 import (
    _add_era_features,
    _apply_imputation_v3,
)

_TRAINING_START   = "2021-01-01"
_ARTIFACT_S3_URI  = "s3://baseball-betting-ml-artifacts/sub_models/run_env_v4.pkl"
_ARTIFACT_LOCAL   = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v4.pkl"
_SUB_MODEL_NAME   = "run_env_v4"
_SUB_MODEL_VERSION = "v4"
_SIDES = ("home", "away")


def _resolve_tables(env: str) -> tuple[str, str]:
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    return f"{schema}.mart_sub_model_signals", f"{schema}.tmp_scd2_incoming"


# ---------------------------------------------------------------------------
# Feature query (no outcome filter — includes upcoming games)
# ---------------------------------------------------------------------------

_SIGNAL_QUERY_TEMPLATE = """
select
    g.game_pk,
    g.game_date,
    p.venue_id,
    p.venue_name,
    g.home_final_score + g.away_final_score      as total_runs,

    p.eb_park_run_factor,
    p.elevation_ft,
    p.center_ft,
    iff(p.roof_type = 'Dome', 1, 0)              as is_dome,

    coalesce(w.temp_f,             70)           as temp_f,
    coalesce(w.wind_component_mph,  0)           as wind_component_mph,
    coalesce(w.humidity_pct,       50)           as humidity_pct,

    u.ump_runs_per_game_zscore,
    u.ump_run_impact_zscore,

    th.off_woba_30d                              as home_off_woba_30d,
    ta.off_woba_30d                              as away_off_woba_30d,
    sh.starter_proj_fip                          as home_starter_proj_fip,
    sh.xwoba_against_30d                         as home_starter_xwoba_30d,
    sa.starter_proj_fip                          as away_starter_proj_fip,
    sa.xwoba_against_30d                         as away_starter_xwoba_30d

-- Game universe + realized total_runs sourced from mart_game_results — the SAME table the
-- signal_freshness gate anchors on (scripts/check_signal_freshness.py: reference slate =
-- `max(game_date) from mart_game_results where game_type='R' and home_final_score is not null`;
-- coverage denominator = games in mart_game_results on that date). The generator MUST read the
-- gate's exact source, or a false HALT is possible in either lag direction.
--
-- HISTORY: INC-34 (2026-07-21) moved this universe to stg_statsapi_games to dodge a re-execute
-- race where mart_game_results (rebuilt by the heavy --w5-group-a) lagged the generator. But that
-- de-SYNCED run_env from the gate, which still reads mart_game_results — so on 2026-07-24 the
-- INVERSE bit: mart_game_results (scores derived from Statcast stg_batter_pitches, rebuilt in-job
-- by --w1/--w5-group-a) had the 7/23 finals, while stg_statsapi_games.home_score (a SEPARATE
-- StatsAPI monthly_schedule capture/flatten pipeline) still lagged them at generator time → run_env
-- emitted 0/10 → BLOCKING HALT. INC-34 verified VALUE parity between the two score sources but not
-- TIMING parity — they are independent pipelines and can disagree on "is this game Final yet" at the
-- moment the generators run. Re-unifying onto mart_game_results makes the desync structurally
-- impossible: the gate can only demand games that are in mart_game_results, which run_env now reads.
-- The daily job already rebuilds mart_game_results (lakehouse_w8a --w5-group-a) BEFORE the generators;
-- on a re-execute-from-the-generator soak where the mart is stale, the gate (also on mart_game_results)
-- regresses WITH it, so still no false HALT. mart_game_results.game_date is a real DATE (cast ::date
-- in the model) — NOT the INC-23 VARCHAR game_date; `home_final_score is not null` = completed-only.
from baseball_data.betting.mart_game_results g
left join baseball_data.betting_features.feature_pregame_park_features p
    on p.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_weather_features w
    on w.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_umpire_features u
    on u.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_team_features th
    on th.game_pk = g.game_pk and th.side = 'home'
left join baseball_data.betting_features.feature_pregame_team_features ta
    on ta.game_pk = g.game_pk and ta.side = 'away'
left join baseball_data.betting_features.feature_pregame_starter_features sh
    on sh.game_pk = g.game_pk and sh.side = 'home'
left join baseball_data.betting_features.feature_pregame_starter_features sa
    on sa.game_pk = g.game_pk and sa.side = 'away'

where g.game_date >= '{start_date}'
  and g.game_date <= '{end_date}'
  and g.game_type = 'R'
  and g.home_final_score is not null   -- completed games only (matches the gate's reference slate)

order by g.game_date, g.game_pk
"""


# ---------------------------------------------------------------------------
# E11.1-W9-tail: read the run_env feature sources (mart_game_results + 5
# feature_pregame_* tables, all in S3 post-W8b) from the S3 lakehouse via DuckDB.
# The SCD-2 WRITE to mart_sub_model_signals stays on Snowflake (the W9 export-mirror
# copies that OUTPUT to S3; re-implementing SCD-2 accumulate in DuckDB is the W7a-wipe
# class the W9 design forbids). Reuses the shared scripts.utils.lakehouse_read helper
# (NOT a forked `_get_duckdb`). The only SF dialect token here is iff() → IF() (DuckDB
# has IF, not IFF); every game_date is DATE in the parquet → no ::date cast needed.
# ---------------------------------------------------------------------------

def _load_games_s3(start_date: str, end_date: str):
    """Run _SIGNAL_QUERY_TEMPLATE against the S3 lakehouse. Returns (rows, lowercase-cols)."""
    import re

    from scripts.utils.lakehouse_read import duck_connect, register_views, strip_fqn, referenced_tables

    sql = _SIGNAL_QUERY_TEMPLATE.format(start_date=start_date, end_date=end_date)
    duck_sql = re.sub(r"\biff\s*\(", "IF(", strip_fqn(sql), flags=re.IGNORECASE)
    duck = duck_connect()
    try:
        register_views(duck, referenced_tables(_SIGNAL_QUERY_TEMPLATE))
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
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_SIGNAL_QUERY_TEMPLATE.format(start_date=start_date, end_date=end_date))
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
        finally:
            conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= df[col].notna().sum() * 0.9:
                df[col] = converted

    df["game_year"] = pd.to_datetime(df["game_date"]).dt.year
    return df


# ---------------------------------------------------------------------------
# 80% PI width from NegBin(mu, r) — vectorized over a 1-D array of mu values
# ---------------------------------------------------------------------------

def _negbin_pi_width(mu: np.ndarray, r: float) -> np.ndarray:
    """Return the 80% predictive interval width for each game's NegBin(mu_i, r)."""
    p = r / (r + mu)  # nbinom parameterizes as (n=r, p=r/(r+mu))
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return hi - lo


# ---------------------------------------------------------------------------
# Feature hashing (idempotency key for SCD-2)
# ---------------------------------------------------------------------------

def _feature_hash(row: pd.Series, feature_cols: list[str]) -> str:
    parts = "|".join(
        "" if pd.isna(row[c]) else f"{row[c]:.6g}" for c in feature_cols
    )
    return hashlib.md5(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def generate_signals(df: pd.DataFrame, artifact: dict) -> list[dict]:
    """Return signal rows ready for scd2_upsert.

    Emits three signal_names per (game_pk, side):
      run_env_mu          — NegBin μ (predicted mean total runs)
      run_env_dispersion  — NegBin r (dispersion; constant per model version)
      run_env_signal      — z-score of μ (backwards-compatible)

    All three carry uncertainty = game-level 80% PI width from NegBin(mu_i, r).
    """
    model            = artifact["model"]
    impute_vals      = artifact["impute_values"]
    prior_season_runs = artifact["prior_season_runs"]
    feature_cols     = artifact["feature_cols"]
    target_mean      = artifact["target_mean"]
    target_std       = artifact["target_std"]
    min_mu           = artifact["min_mu"]
    negbin_r         = artifact["negbin_r"]

    df_era = _add_era_features(df, prior_season_runs)
    df_imp = _apply_imputation_v3(df_era, impute_vals)

    X = df_imp[feature_cols].to_numpy(dtype=float)
    mu_pred = np.clip(model.predict(X), min_mu, None)
    run_env_z = (mu_pred - target_mean) / target_std
    pi_widths = _negbin_pi_width(mu_pred, negbin_r)

    rows = []
    for i, (_, game_row) in enumerate(df.iterrows()):
        game_pk  = int(game_row["game_pk"])
        feat_hash = _feature_hash(df_imp.iloc[i], feature_cols)
        mu_i     = float(mu_pred[i])
        z_i      = float(run_env_z[i])
        pi_i     = float(pi_widths[i])

        for side in _SIDES:
            base = {
                "game_pk":            game_pk,
                "side":               side,
                "sub_model_name":     _SUB_MODEL_NAME,
                "sub_model_version":  _SUB_MODEL_VERSION,
                "signal_available":   True,
                "input_feature_hash": feat_hash,
            }
            rows.append({**base,
                "signal_name":  "run_env_mu",
                "signal_value": mu_i,
                "uncertainty":  pi_i,
            })
            rows.append({**base,
                "signal_name":  "run_env_dispersion",
                "signal_value": float(negbin_r),
                "uncertainty":  None,
            })
            rows.append({**base,
                "signal_name":  "run_env_signal",
                "signal_value": z_i,
                "uncertainty":  pi_i,
            })

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate run_env_v4 signals (Story 3D.3)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help=f"Generate signals for all games from {_TRAINING_START} through today.",
    )
    mode.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Generate signals for a single game date.",
    )
    parser.add_argument(
        "--env",
        choices=["prod", "dev"],
        default="prod",
        help="Target environment: prod (baseball_data.betting) or dev (baseball_data.dev_betting). Default: prod.",
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
             "instead of Snowflake. The SCD-2 write stays on Snowflake.",
    )
    args = parser.parse_args()

    target_table, temp_table = _resolve_tables(args.env)

    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    env_label = f"[{args.env.upper()}]"
    print(f"{env_label} target={target_table}")

    artifact_path = _ARTIFACT_S3_URI if (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("ARTIFACTS_FROM_S3")) else _ARTIFACT_LOCAL
    print(f"\nLoading artifact from {artifact_path}...")
    artifact = load_artifact(artifact_path)
    print(
        f"  model_type={artifact['model_type']}, "
        f"NegBin r={artifact['negbin_r']:.4f}, "
        f"CV NLL={artifact['cv_nll']:.4f}, "
        f"CV MAE={artifact['cv_mae']:.4f}"
    )

    print(f"\nLoading games {start_date} → {end_date} from {'S3 (DuckDB)' if args.s3 else 'Snowflake'}...")
    df = load_games(start_date, end_date, use_s3=args.s3)
    print(f"  Loaded {len(df):,} games.")

    if df.empty:
        print("No games found for the given date range. Exiting.")
        return

    print("\nGenerating signals...")
    signal_rows = generate_signals(df, artifact)
    n_games = len(df)
    print(f"  {len(signal_rows):,} signal rows ({n_games:,} games × 3 signals × 2 sides).")

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 6):")
        for r in signal_rows[:6]:
            print(f"  {r}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    print(f"\nWriting to {target_table}...")
    conn = get_snowflake_connection()
    try:
        computed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = scd2_upsert(
            conn, signal_rows,
            target_table=target_table,
            temp_table=temp_table,
            computed_at=computed_at,
        )
    finally:
        conn.close()

    print(
        f"  Done. inserted={result['inserted']}, "
        f"skipped={result['skipped']}, closed={result['closed']}"
    )
    print("\nStory 3D.3 complete.")
    print("Next steps (Story 3D.4):")
    print("  1. Add run_env_mu and run_env_dispersion columns to mart_sub_model_signals DDL")
    print("  2. Update dbt/models/feature/feature_pregame_sub_model_signals.sql")
    print("  3. dbtf build --select feature_pregame_sub_model_signals")


if __name__ == "__main__":
    main()
