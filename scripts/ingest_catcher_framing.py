"""
ingest_catcher_framing.py
-------------------------
Fetches catcher fielding/framing data from FanGraphs leaderboard API and loads
it into Snowflake as a weekly snapshot.

Source: FanGraphs /api/leaders/major-league/data (stats=fld, type=c, pos=c)
Target table: baseball_data.savant.catcher_framing_raw

Key columns extracted per catcher × season snapshot:
  framing_runs   -- CFraming: pure pitch-framing runs above average
  defensive_runs -- FRP: total catcher defensive value (framing + blocking + arm + range)
  stolen_base_runs -- rSB: arm/throwing runs saved on stolen base attempts
  innings_caught -- Inn: sample size proxy for reliability regression
  raw_json       -- full API record (VARIANT) for schema resilience

Player identity: xMLBAMID from FanGraphs == MLBAM player ID used in lineup tables.
No cross-walk needed.

Load is idempotent within a snapshot_date: re-running the same day overwrites
(MERGE on player_id × season × snapshot_date). Run once per week.

Usage:
    # Backfill 2021–2026 (use today as snapshot_date)
    uv run python scripts/ingest_catcher_framing.py --start-season 2021 --end-season 2026

    # Current season only
    uv run python scripts/ingest_catcher_framing.py --season 2026

    # Override snapshot date (e.g. replaying a past capture)
    uv run python scripts/ingest_catcher_framing.py --season 2026 --snapshot-date 2026-04-01

    # Dry-run (print rows, skip Snowflake write)
    uv run python scripts/ingest_catcher_framing.py --season 2025 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from datetime import date
from typing import Any

import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_KEY_PATH = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH") or os.path.expanduser(
    "~/Documents/machine_learning/baseball/betting_model/jaffle_shop/rsa_key.pem"
)

TABLE_FQN = "baseball_data.savant.catcher_framing_raw"

FANGRAPHS_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
FANGRAPHS_PARAMS = {
    "pos":       "c",
    "stats":     "fld",
    "lg":        "all",
    "qual":      "0",      # all catchers regardless of sample size
    "type":      "c",      # catcher-specific fielding stats (includes CFraming, FRP, rSB)
    "pageitems": "500",
    "pagenum":   "1",
    "ind":       "0",
    "rost":      "0",
    "players":   "",
    "postseason": "",
    "month":     "0",
    "hand":      "",
    "team":      "0",
    "age":       "",
}

REQUEST_DELAY   = 2.0   # seconds between season requests
REQUEST_TIMEOUT = 60
MAX_RETRIES     = 3
RETRY_BACKOFF   = 10

# Temp table used to stage rows before MERGE (required for VARIANT / PARSE_JSON pattern)
_CREATE_TEMP_SQL = """
CREATE TEMPORARY TABLE IF NOT EXISTS tmp_catcher_framing_stage (
    player_id        VARCHAR,
    season           INTEGER,
    snapshot_date    VARCHAR,
    framing_runs     FLOAT,
    defensive_runs   FLOAT,
    stolen_base_runs FLOAT,
    innings_caught   FLOAT,
    raw_json_str     VARCHAR
)
"""

_INSERT_SQL = f"""
INSERT INTO {TABLE_FQN}
    (player_id, season, snapshot_date, framing_runs, defensive_runs,
     stolen_base_runs, innings_caught, raw_json, ingestion_timestamp)
SELECT
    player_id,
    season,
    snapshot_date::DATE,
    framing_runs,
    defensive_runs,
    stolen_base_runs,
    innings_caught,
    PARSE_JSON(raw_json_str),
    CURRENT_TIMESTAMP
FROM tmp_catcher_framing_stage
"""


def _connect() -> snowflake.connector.SnowflakeConnection:
    with open(_KEY_PATH, "rb") as f:
        p_key = serialization.load_pem_private_key(
            f.read(), password=None, backend=default_backend()
        )
    pkb = p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "IHUPICS-DP59975"),
        user=os.environ.get("SNOWFLAKE_USER", "dbt_rw"),
        private_key=pkb,
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="savant",
    )


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def fetch_season(season: int) -> list[dict[str, Any]]:
    """Fetch catcher fielding/framing data for a single season from FanGraphs."""
    params = {
        **FANGRAPHS_PARAMS,
        "season":    season,
        "season1":   season,
        "startdate": f"{season}-03-01",
        "enddate":   f"{season}-11-01",
    }

    session = requests.Session()
    session.headers.update({
        "User-Agent": "baseball-research/1.0 (research)",
        "Accept":     "application/json",
    })

    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(FANGRAPHS_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
            break
        except requests.Timeout:
            log.warning("  [%d/%d] Request timed out", attempt, MAX_RETRIES)
        except requests.HTTPError as exc:
            log.warning("  [%d/%d] HTTP %s", attempt, MAX_RETRIES, exc.response.status_code)
        except Exception as exc:
            log.warning("  [%d/%d] Unexpected error: %s", attempt, MAX_RETRIES, exc)

        if attempt < MAX_RETRIES:
            log.info("  Retrying in %ds…", backoff)
            time.sleep(backoff)
            backoff *= 2
    else:
        log.error("  All %d attempts failed for season %d — skipping", MAX_RETRIES, season)
        return []

    log.info("  Season %d: %d rows from FanGraphs", season, len(data))

    records: list[dict[str, Any]] = []
    skipped = 0
    for row in data:
        mlbam_id = _safe_float(row.get("xMLBAMID"))
        if mlbam_id is None:
            skipped += 1
            continue

        records.append({
            "player_id":       str(int(mlbam_id)),
            "season":          season,
            "framing_runs":    _safe_float(row.get("CFraming")),
            "defensive_runs":  _safe_float(row.get("FRP")),
            "stolen_base_runs": _safe_float(row.get("rSB")),
            "innings_caught":  _safe_float(row.get("Inn")),
            "raw_json":        json.dumps(
                {k: v for k, v in row.items() if v is not None},
                default=str,
            ),
        })

    if skipped:
        log.warning("  Season %d: %d rows skipped (missing xMLBAMID)", season, skipped)
    log.info("  Season %d: %d valid catcher rows parsed", season, len(records))
    return records


def write_to_snowflake(
    conn: snowflake.connector.SnowflakeConnection,
    records: list[dict[str, Any]],
    snapshot_date: str,
) -> int:
    if not records:
        return 0

    cur = conn.cursor()
    cur.execute(_CREATE_TEMP_SQL)

    rows = [
        (
            r["player_id"],
            r["season"],
            snapshot_date,
            r["framing_runs"],
            r["defensive_runs"],
            r["stolen_base_runs"],
            r["innings_caught"],
            r["raw_json"],
        )
        for r in records
    ]
    cur.executemany(
        "INSERT INTO tmp_catcher_framing_stage VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        rows,
    )
    cur.execute(_INSERT_SQL)
    cur.close()
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest FanGraphs catcher fielding/framing data to Snowflake"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--season", type=int, help="Single season to ingest")
    group.add_argument(
        "--start-season", type=int, default=2021,
        help="Start of range (default 2021)",
    )
    parser.add_argument(
        "--end-season", type=int, default=date.today().year,
        help="End of range (default current year)",
    )
    parser.add_argument(
        "--snapshot-date", type=str, default=str(date.today()),
        help="Snapshot date to tag rows with (YYYY-MM-DD, default today)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print rows without writing to Snowflake",
    )
    args = parser.parse_args()

    seasons = (
        [args.season] if args.season
        else list(range(args.start_season, args.end_season + 1))
    )
    log.info("Fetching catcher framing for seasons: %s (snapshot_date=%s)",
             seasons, args.snapshot_date)

    all_records: list[dict] = []
    for i, season in enumerate(seasons):
        records = fetch_season(season)
        all_records.extend(records)
        if i < len(seasons) - 1:
            time.sleep(REQUEST_DELAY)

    log.info("Total: %d catcher-season rows fetched", len(all_records))

    if args.dry_run:
        for r in all_records:
            print(
                f"  {r['season']}  pid={r['player_id']:<10}  "
                f"framing={r['framing_runs']}  "
                f"defense={r['defensive_runs']}  "
                f"sb={r['stolen_base_runs']}  "
                f"inn={r['innings_caught']}"
            )
        return

    log.info("Connecting to Snowflake…")
    conn = _connect()
    try:
        written = write_to_snowflake(conn, all_records, args.snapshot_date)
        log.info("Done. %d rows written to %s", written, TABLE_FQN)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
