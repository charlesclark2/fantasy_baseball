"""
check_data_freshness.py
-----------------------
Verify that all ingestion source tables have been updated within their expected
freshness windows. Exits non-zero if any threshold is breached.

Usage:
    uv run python scripts/check_data_freshness.py
    uv run python scripts/check_data_freshness.py --date 2026-05-01
    uv run python scripts/check_data_freshness.py --dry-run

Snowflake auth env vars (same pattern as other scripts):
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE              (optional)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Freshness thresholds
# ---------------------------------------------------------------------------

FRESHNESS_THRESHOLDS: dict[str, dict] = {
    "baseball_data.savant.batter_pitches": {
        "ts_col": "game_date",       # DATE; cast to TIMESTAMP_NTZ in query
        "max_stale_hours": 36,
        "game_day_only": False,
    },
    "baseball_data.oddsapi.mlb_odds_raw": {
        "ts_col": "ingestion_ts",
        "max_stale_hours": 6,
        "game_day_only": True,
    },
    "baseball_data.fangraphs.fg_stuff_plus_raw": {
        "ts_col": "ingestion_ts",
        "max_stale_hours": 192,  # 8 days — weekly Sunday ingest
        "game_day_only": False,
    },
    "baseball_data.statsapi.umpire_game_log": {
        "ts_col": "loaded_at",
        "max_stale_hours": 36,
        "game_day_only": False,
    },
    "baseball_data.statsapi.player_transactions": {
        "ts_col": "effective_date",  # DATE; no ingestion_ts column exists
        "max_stale_hours": 168,      # 7 days — ingest backfills a 7-day window
        "game_day_only": False,
    },
    "baseball_data.statsapi.monthly_schedule": {
        "ts_col": "ingest_date",     # DATE; cast to TIMESTAMP_NTZ in query
        "max_stale_hours": 2,
        "game_day_only": True,
    },
}

# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------


def _load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  "baseball_data",
    }

    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(pk_path, passphrase)
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        kwargs["password"] = password

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_game_day(check_date: date, con: snowflake.connector.SnowflakeConnection) -> bool:
    """Return True if there are scheduled games on check_date."""
    cur = con.cursor()
    cur.execute(
        """
        SELECT COUNT(*) FROM baseball_data.betting_features.feature_pregame_game_features
        WHERE game_date = %s
        """,
        (check_date.isoformat(),),
    )
    row = cur.fetchone()
    return bool(row and row[0] > 0)


def _max_ingestion_timestamp(
    table: str,
    ts_col: str,
    con: snowflake.connector.SnowflakeConnection,
) -> datetime | None:
    """Query MAX of the table's freshness column. DATE columns are cast to TIMESTAMP_NTZ."""
    cur = con.cursor()
    cur.execute(f"SELECT MAX({ts_col}::TIMESTAMP_NTZ) FROM {table}")
    row = cur.fetchone()
    if row and row[0] is not None:
        ts = row[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(check_date: date, dry_run: bool = False) -> None:
    now_utc = datetime.now(timezone.utc)

    if dry_run:
        log.info("[DRY RUN] Would check freshness thresholds for date=%s", check_date)
        for table, cfg in FRESHNESS_THRESHOLDS.items():
            log.info("  %s — max_stale_hours=%s game_day_only=%s",
                     table, cfg["max_stale_hours"], cfg["game_day_only"])
        return

    con = _get_connection()
    try:
        game_day = _is_game_day(check_date, con)
        log.info("Check date: %s — game day: %s", check_date, game_day)

        results: list[dict] = []
        breaches: list[str] = []

        for table, cfg in FRESHNESS_THRESHOLDS.items():
            max_stale_hours: int = cfg["max_stale_hours"]
            game_day_only: bool = cfg["game_day_only"]
            ts_col: str = cfg["ts_col"]

            if game_day_only and not game_day:
                log.info("  %-55s SKIP (off day)", table)
                results.append({"table": table, "status": "SKIP (off day)", "hours_stale": None})
                continue

            max_ts = _max_ingestion_timestamp(table, ts_col, con)
            if max_ts is None:
                log.warning("  %-55s NO DATA", table)
                results.append({"table": table, "status": "NO DATA", "hours_stale": None})
                breaches.append(table)
                continue

            hours_stale = (now_utc - max_ts).total_seconds() / 3600
            threshold_exceeded = hours_stale > max_stale_hours
            status = f"STALE ({hours_stale:.1f}h > {max_stale_hours}h)" if threshold_exceeded else f"OK ({hours_stale:.1f}h)"

            log.info("  %-55s %s", table, status)
            results.append({"table": table, "status": status, "hours_stale": hours_stale})

            if threshold_exceeded:
                breaches.append(table)
    finally:
        con.close()

    print("\n--- Data Freshness Summary ---")
    col_w = 55
    print(f"{'Table':<{col_w}}  {'Status'}")
    print("-" * (col_w + 30))
    for r in results:
        print(f"{r['table']:<{col_w}}  {r['status']}")

    if breaches:
        print(f"\nFRESHNESS ALERT: {len(breaches)} table(s) exceeded threshold:")
        for t in breaches:
            print(f"  - {t}")
        sys.exit(1)
    else:
        print("\nAll freshness checks passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check ingestion source table freshness against expected thresholds."
    )
    parser.add_argument("--date", default=None,
                        help="Check date in YYYY-MM-DD format (default: today ET)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print thresholds without querying Snowflake")
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        check_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(check_date=check_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
