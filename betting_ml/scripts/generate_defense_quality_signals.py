"""
generate_defense_quality_signals.py — Story 27.4: Defensive quality signal generation

Reads the dbt-built mart_team_defense_quality_rolling table (which contains OAA
z-scores + sprint speed z-scores pre-computed with leakage guard and EB smoothing)
and emits three signal_names per (game_pk, side) into mart_sub_model_signals via
the SCD-2 writer:

  defense_quality_mu     — composite z-score: (oaa_z + sprint_z)/sqrt(2) or
                           whichever component is available; higher = better defense
  defense_quality_oaa_z  — OAA z-score component (OAA outs above average, prior season)
  defense_quality_sprint_z — team mean sprint speed z-score (EB-smoothed, prior season)

Sub-model registration: sub_model_name="defense_quality_v1", sub_model_version="v1"

Signal design (R33 shared signal):
  This signal is consumed by both Epic 27 (totals) and Epic 28 (H2H).  It is
  orthogonal to all existing sub-model signals by construction: OAA measures
  fielder-driven outs (excluded from FIP/xwOBA-against) and sprint speed measures
  range (independent of batting outcomes).

Usage:
    # Score a single date (daily Dagster op)
    uv run python betting_ml/scripts/generate_defense_quality_signals.py --date 2026-06-09

    # Backfill all 2021+ regular-season games (hand off to user — >1 min)
    uv run python betting_ml/scripts/generate_defense_quality_signals.py --backfill

    # Dry-run: compute without writing
    uv run python betting_ml/scripts/generate_defense_quality_signals.py --date 2026-06-09 --dry-run
    uv run python betting_ml/scripts/generate_defense_quality_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV

_TRAINING_START    = "2021-01-01"
_SUB_MODEL_NAME    = "defense_quality_v1"
_SUB_MODEL_VERSION = "v1"
_SIGNAL_NAMES      = (
    "defense_quality_mu",
    "defense_quality_oaa_z",
    "defense_quality_sprint_z",
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _resolve_tables(env: str) -> tuple[str, str, str]:
    """Return (signal_table, temp_table, mart_table) for the given env."""
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    mart_schema = "baseball_data.betting" if env == "prod" else "baseball_data.dev_betting"
    return (
        f"{schema}.mart_sub_model_signals",
        f"{schema}.tmp_scd2_incoming",
        f"{mart_schema}.mart_team_defense_quality_rolling",
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_MART_QUERY = """
SELECT
    game_pk,
    side,
    defense_quality_mu,
    oaa_z                 AS defense_quality_oaa_z,
    sprint_z              AS defense_quality_sprint_z,
    oaa_available,
    sprint_available
FROM {mart_table}
WHERE game_date >= '{start_date}'
  AND game_date <= '{end_date}'
ORDER BY game_pk, side
"""


def _load_mart_rows(conn, mart_table: str, start_date: str, end_date: str,
                    use_s3: bool = False) -> pd.DataFrame:
    """Load pre-computed defense quality rows from the dbt mart.

    E11.1-W9-tail: when use_s3, read mart_team_defense_quality_rolling from the S3
    lakehouse via DuckDB instead of Snowflake. The SCD-2 WRITE stays on Snowflake (the
    W9 export-mirror copies the OUTPUT to S3; a DuckDB SCD-2 rewrite is the W7a-wipe
    class W9 forbids). game_date is TIMESTAMP in the parquet (NOT DATE like the other
    marts) → cast ::date so a single-date `--date` run isn't dropped by the midnight
    boundary. Reuses scripts.utils.lakehouse_read (no forked connection helper)."""
    if use_s3:
        from scripts.utils.lakehouse_read import duck_connect, register_views

        _MART_S3 = "mart_team_defense_quality_rolling"
        sql = _MART_QUERY.format(mart_table=_MART_S3, start_date=start_date, end_date=end_date)
        sql = (sql.replace("WHERE game_date >=", "WHERE game_date::date >=")
                  .replace("AND game_date <=", "AND game_date::date <="))
        duck = duck_connect()
        try:
            register_views(duck, [_MART_S3])
            cur = duck.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            rows = cur.fetchall()
        finally:
            duck.close()
        return pd.DataFrame(rows, columns=cols)

    cur = conn.cursor()
    try:
        cur.execute(_MART_QUERY.format(
            mart_table=mart_table,
            start_date=start_date,
            end_date=end_date,
        ))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        cur.close()
    df = pd.DataFrame(rows, columns=cols)
    return df


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def _feature_hash(game_pk: int, side: str) -> str:
    """Stable hash encoding the mart source for this signal."""
    key = f"{game_pk}|{side}|defense_quality_v1"
    return hashlib.md5(key.encode()).hexdigest()


def generate_signals(mart_df: pd.DataFrame) -> list[dict]:
    """Convert mart rows to mart_sub_model_signals long-format rows.

    Emits three signal_names per (game_pk, side):
      defense_quality_mu       — composite z-score
      defense_quality_oaa_z    — OAA component z-score
      defense_quality_sprint_z — sprint speed component z-score
    """
    rows = []
    for _, r in mart_df.iterrows():
        gp            = int(r["game_pk"])
        side          = str(r["side"])
        feat_hash     = _feature_hash(gp, side)
        oaa_avail     = bool(r["oaa_available"])
        sprint_avail  = bool(r["sprint_available"])
        composite_mu  = float(r["defense_quality_mu"]) if r["defense_quality_mu"] is not None else 0.0
        oaa_z         = float(r["defense_quality_oaa_z"]) if r["defense_quality_oaa_z"] is not None else 0.0
        sprint_z      = float(r["defense_quality_sprint_z"]) if r["defense_quality_sprint_z"] is not None else 0.0

        base = {
            "game_pk":           gp,
            "side":              side,
            "sub_model_name":    _SUB_MODEL_NAME,
            "sub_model_version": _SUB_MODEL_VERSION,
            "input_feature_hash": feat_hash,
        }

        # Primary composite signal
        rows.append({**base,
            "signal_name":     "defense_quality_mu",
            "signal_value":    composite_mu,
            "uncertainty":     None,
            "signal_available": oaa_avail or sprint_avail,
        })
        # OAA component
        rows.append({**base,
            "signal_name":     "defense_quality_oaa_z",
            "signal_value":    oaa_z,
            "uncertainty":     None,
            "signal_available": oaa_avail,
        })
        # Sprint speed component
        rows.append({**base,
            "signal_name":     "defense_quality_sprint_z",
            "signal_value":    sprint_z,
            "uncertainty":     None,
            "signal_available": sprint_avail,
        })

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate defense_quality_v1 signals (Story 27.4)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help=f"Generate signals for all regular-season games from {_TRAINING_START} through today.",
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
        help="Target environment: prod or dev. Default: prod.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute signals but skip the Snowflake write.",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="E11.1-W9-tail: read mart_team_defense_quality_rolling from the S3 lakehouse "
             "via DuckDB instead of Snowflake. The SCD-2 write stays on Snowflake.",
    )
    args = parser.parse_args()

    target_table, temp_table, mart_table = _resolve_tables(args.env)
    today = date.today().isoformat()

    if args.backfill:
        game_start, game_end = _TRAINING_START, today
    else:
        game_start = game_end = args.date

    env_label = f"[{args.env.upper()}]"
    print(f"{env_label} target={target_table}")
    print(f"{env_label} source mart={mart_table}")
    print(f"Mode: {'backfill' if args.backfill else 'date=' + args.date}")

    # ---- Load mart rows ----
    print(f"\nLoading mart_team_defense_quality_rolling from {'S3 (DuckDB)' if args.s3 else 'Snowflake'}...")
    if args.s3:
        mart_df = _load_mart_rows(None, mart_table, game_start, game_end, use_s3=True)
    else:
        conn = get_snowflake_connection()
        try:
            mart_df = _load_mart_rows(conn, mart_table, game_start, game_end)
        finally:
            conn.close()

    print(f"  {len(mart_df):,} mart rows ({len(mart_df) // 2:,} games) for {game_start} → {game_end}")

    if mart_df.empty:
        print("No rows found in the mart for the given date range. Exiting.")
        print("  Ensure dbtf build --select mart_team_defense_quality_rolling has been run first.")
        return

    # ---- Generate signals ----
    print("\nGenerating signals...")
    signal_rows = generate_signals(mart_df)
    n_per_game_side = len(_SIGNAL_NAMES)
    print(
        f"  {len(signal_rows):,} signal rows "
        f"({len(mart_df):,} game-sides × {n_per_game_side} signals)"
    )

    # Coverage summary
    mu_rows = [r for r in signal_rows if r["signal_name"] == "defense_quality_mu"]
    available = sum(1 for r in mu_rows if r["signal_available"])
    pct = 100.0 * available / len(mu_rows) if mu_rows else 0.0
    print(f"  Coverage: {available}/{len(mu_rows)} game-sides have defense_quality_mu ({pct:.1f}%)")
    if pct < 95.0 and len(mu_rows) > 100:
        print(f"  WARNING: coverage {pct:.1f}% is below the 95% acceptance criterion (AC1)")

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 6):")
        for r in signal_rows[:6]:
            print(f"  {r}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    # ---- Write via SCD-2 ----
    print(f"\nWriting {len(signal_rows):,} rows to {target_table}...")
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

    if pct < 95.0 and len(mu_rows) > 100:
        print(f"  WARNING: coverage {pct:.1f}% is below the 95% AC1 gate — investigate missing OAA/sprint data")

    print("\nStory 27.4 signal generation complete.")
    print("Next step: dbtf build --select feature_pregame_sub_model_signals --target baseball_betting_and_fantasy")


if __name__ == "__main__":
    main()
