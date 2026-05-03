"""
ingest_umpires_historical.py
-----------------------------
Bulk-load UmpScorecards historical by-game data into
baseball_data.statsapi.umpire_game_log.

AUTOMATION NOTE:
  This script is intended for:
    1. One-time backfill (2015-present) from the locally-downloaded CSV
    2. Annual refresh at the start of each off-season
  Daily going-forward data comes from the MLB Stats API via ingest_umpires.py.
  UmpScorecards does not provide a daily push mechanism; bulk exports are
  downloaded manually from: https://umpscorecards.com/data/games

DATA NOTE:
  The by-game export from UmpScorecards does not include k_pct or bb_pct.
  Those columns are retained in umpire_game_log for potential future
  population from Statcast pitch data but will be NULL for these rows.
  Available metrics: total_runs, called_strikes_above_avg (Correct Calls
  Above Expected), run_expectancy_delta (Favor Home), total_run_impact,
  accuracy_above_expected.

Usage:
    # Dry-run: inspect data without writing
    uv run python scripts/ingest_umpires_historical.py --dry-run

    # Load all seasons from default CSV path
    uv run python scripts/ingest_umpires_historical.py

    # Load specific season
    uv run python scripts/ingest_umpires_historical.py --season 2025

    # Load from explicit file path
    uv run python scripts/ingest_umpires_historical.py --file path/to/file.csv
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# UmpScorecards bulk export URL (for documentation; bulk download only, not a live API)
UMPSCORECARDS_GAMES_URL = "https://umpscorecards.com/data/games"

DEFAULT_CSV_PATH = Path(__file__).parent / "raw_files" / "umpscorecards" / "umpscorecards_historical.csv"

TABLE_FQN = "baseball_data.statsapi.umpire_game_log"

MERGE_SQL = f"""
MERGE INTO {TABLE_FQN} AS tgt
USING (
    SELECT
        %(game_pk)s::INTEGER              AS game_pk,
        %(game_date)s::DATE               AS game_date,
        %(season)s::INTEGER               AS season,
        %(umpire_name)s::VARCHAR           AS umpire_name,
        NULL::VARCHAR                     AS umpire_id,
        NULL::FLOAT                       AS k_pct,
        NULL::FLOAT                       AS bb_pct,
        %(total_runs)s::INTEGER           AS total_runs,
        %(called_strikes_above_avg)s::FLOAT AS called_strikes_above_avg,
        %(run_expectancy_delta)s::FLOAT   AS run_expectancy_delta,
        %(total_run_impact)s::FLOAT       AS total_run_impact,
        %(accuracy_above_expected)s::FLOAT AS accuracy_above_expected,
        'umpscorecards'::VARCHAR          AS data_source,
        CURRENT_TIMESTAMP()               AS loaded_at
) AS src
ON tgt.game_pk = src.game_pk
WHEN MATCHED THEN UPDATE SET
    game_date                = src.game_date,
    season                   = src.season,
    umpire_name              = src.umpire_name,
    total_runs               = src.total_runs,
    called_strikes_above_avg = src.called_strikes_above_avg,
    run_expectancy_delta     = src.run_expectancy_delta,
    total_run_impact         = src.total_run_impact,
    accuracy_above_expected  = src.accuracy_above_expected,
    data_source              = src.data_source,
    loaded_at                = src.loaded_at
WHEN NOT MATCHED THEN INSERT (
    game_pk, game_date, season, umpire_name, umpire_id,
    k_pct, bb_pct, total_runs, called_strikes_above_avg,
    run_expectancy_delta, total_run_impact, accuracy_above_expected,
    data_source, loaded_at
) VALUES (
    src.game_pk, src.game_date, src.season, src.umpire_name, src.umpire_id,
    src.k_pct, src.bb_pct, src.total_runs, src.called_strikes_above_avg,
    src.run_expectancy_delta, src.total_run_impact, src.accuracy_above_expected,
    src.data_source, src.loaded_at
)
"""


def _load_private_key() -> bytes | None:
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw,
        password=passphrase.encode() if passphrase else None,
        backend=default_backend(),
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="statsapi",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def load_csv(csv_path: Path, season: int | None) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    df["game_date"] = pd.to_datetime(df["Date"]).dt.date
    df["season"] = pd.to_datetime(df["Date"]).dt.year
    df["total_runs"] = df["Runs (Home)"].fillna(0).astype(int) + df["Runs (Away)"].fillna(0).astype(int)
    df["called_strikes_above_avg"] = pd.to_numeric(df["Correct Calls Above Exp."], errors="coerce")
    df["run_expectancy_delta"] = pd.to_numeric(df["Favor (Home)"], errors="coerce")
    df["total_run_impact"] = pd.to_numeric(df["Total Run Impact"], errors="coerce")
    df["accuracy_above_expected"] = pd.to_numeric(df["Accuracy Above Expected"], errors="coerce")
    df["umpire_name"] = df["Umpire"].str.strip()
    df["game_pk"] = pd.to_numeric(df["game_pk"], errors="coerce").dropna().astype(int)

    df = df.dropna(subset=["game_pk", "umpire_name"])
    df["game_pk"] = df["game_pk"].astype(int)

    if season is not None:
        df = df[df["season"] == season]

    return df[["game_pk", "game_date", "season", "umpire_name",
               "total_runs", "called_strikes_above_avg", "run_expectancy_delta",
               "total_run_impact", "accuracy_above_expected"]]


def bulk_load(conn, df: pd.DataFrame) -> int:
    """Fast bulk load via write_pandas (PUT + COPY INTO).

    For initial/full backfill: truncates the table, then bulk-inserts all rows.
    Much faster than row-by-row MERGE for large datasets.
    For incremental season updates use --merge flag (row-by-row MERGE, idempotent).
    """
    from snowflake.connector.pandas_tools import write_pandas

    # Prepare the DataFrame with proper column names and types for Snowflake
    load_df = df.copy()
    load_df["game_date"] = load_df["game_date"].astype(str)
    load_df["k_pct"] = None
    load_df["bb_pct"] = None
    load_df["umpire_id"] = None
    load_df["data_source"] = "umpscorecards"

    # Rename to exact Snowflake column names (uppercase for write_pandas)
    col_map = {
        "game_pk": "GAME_PK",
        "game_date": "GAME_DATE",
        "season": "SEASON",
        "umpire_name": "UMPIRE_NAME",
        "umpire_id": "UMPIRE_ID",
        "k_pct": "K_PCT",
        "bb_pct": "BB_PCT",
        "total_runs": "TOTAL_RUNS",
        "called_strikes_above_avg": "CALLED_STRIKES_ABOVE_AVG",
        "run_expectancy_delta": "RUN_EXPECTANCY_DELTA",
        "total_run_impact": "TOTAL_RUN_IMPACT",
        "accuracy_above_expected": "ACCURACY_ABOVE_EXPECTED",
        "data_source": "DATA_SOURCE",
    }
    load_df = load_df[list(col_map.keys())].rename(columns=col_map)

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE baseball_data.statsapi.umpire_game_log")
        log.info("Truncated umpire_game_log for full reload.")

    success, nchunks, nrows, _ = write_pandas(
        conn,
        load_df,
        "UMPIRE_GAME_LOG",
        database="BASEBALL_DATA",
        schema="STATSAPI",
        overwrite=False,
        quote_identifiers=False,
    )
    if not success:
        raise RuntimeError("write_pandas reported failure")
    log.info("Bulk loaded %d rows in %d chunk(s).", nrows, nchunks)
    return nrows


def merge_rows(conn, rows: list[dict]) -> int:
    """Idempotent row-by-row MERGE for incremental season updates."""
    loaded = 0
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(MERGE_SQL, row)
            loaded += 1
    return loaded


def main():
    parser = argparse.ArgumentParser(description="Load UmpScorecards historical game data into Snowflake")
    parser.add_argument("--file", type=Path, default=DEFAULT_CSV_PATH,
                        help="Path to UmpScorecards CSV (default: scripts/raw_files/umpscorecards/umpscorecards_historical.csv)")
    parser.add_argument("--season", type=int, default=None,
                        help="Filter to a specific season year (e.g. 2024)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print record count and sample row; no Snowflake write")
    parser.add_argument("--merge", action="store_true",
                        help="Use row-by-row MERGE instead of bulk truncate+load (use for incremental season refresh)")
    args = parser.parse_args()

    csv_path = args.file
    if not csv_path.exists():
        log.error("CSV not found: %s", csv_path)
        log.error("Download from %s and save to %s", UMPSCORECARDS_GAMES_URL, DEFAULT_CSV_PATH)
        sys.exit(1)

    log.info("Loading CSV: %s", csv_path)
    df = load_csv(csv_path, args.season)
    log.info("Parsed %d rows (season filter=%s)", len(df), args.season)

    if df.empty:
        log.warning("No rows after filtering — nothing to load.")
        sys.exit(0)

    season_range = f"{df['season'].min()}–{df['season'].max()}"

    if args.dry_run:
        print(f"\n--- DRY RUN ---")
        print(f"Record count: {len(df)}")
        print(f"Season range: {season_range}")
        print(f"Sample row:\n{df.iloc[0].to_dict()}")
        print(f"Source URL (for future reference): {UMPSCORECARDS_GAMES_URL}")
        return

    log.info("Connecting to Snowflake...")
    conn = get_snowflake_conn()
    try:
        if args.merge:
            rows = df.to_dict(orient="records")
            for r in rows:
                r["game_date"] = str(r["game_date"])
            log.info("Merging %d rows (incremental)...", len(rows))
            loaded = merge_rows(conn, rows)
        else:
            log.info("Bulk loading %d rows (truncate + write_pandas)...", len(df))
            loaded = bulk_load(conn, df)
        log.info("Loaded %d UmpScorecards rows (%s)", loaded, season_range)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
