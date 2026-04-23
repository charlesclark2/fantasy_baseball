"""
ingest_statsapi.py
------------------
Ingests MLB Stats API data into Snowflake. Two ingestion modes are supported
and can be run independently via CLI subcommands:

  schedule  — Iterates month-by-month over a configurable date range and
              upserts each month's schedule+lineup response into
              baseball_data.statsapi.monthly_schedule. Defaults to the
              current calendar month only — pass --start-date to widen the
              window for backfills or to pick up retroactive lineup updates.

  venues    — Accepts a list of venue IDs (from a file or stdin) and upserts
              each venue's full API response (with fieldInfo, location,
              timezone, xrefId hydration) into
              baseball_data.statsapi.venues_raw.

Authentication — private key (preferred) or password fallback:
    Private key (set SNOWFLAKE_PRIVATE_KEY_PATH; passphrase optional):
        SNOWFLAKE_ACCOUNT
        SNOWFLAKE_USER
        SNOWFLAKE_WAREHOUSE
        SNOWFLAKE_PRIVATE_KEY_PATH      path to .p8 / PEM private key file
        SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  (optional, omit if key is unencrypted)
        SNOWFLAKE_ROLE                  (optional)

    Password fallback (used when SNOWFLAKE_PRIVATE_KEY_PATH is not set):
        SNOWFLAKE_ACCOUNT
        SNOWFLAKE_USER
        SNOWFLAKE_PASSWORD
        SNOWFLAKE_WAREHOUSE
        SNOWFLAKE_ROLE                  (optional)

DDL for target tables:
    create or replace table baseball_data.statsapi.monthly_schedule (
        month_start_date date,
        month_end_date   date,
        games_cnt        int,
        json_field       variant
    );

    create or replace table baseball_data.statsapi.venues_raw (
        venue_id    number,
        json_field  variant,
        ingest_date date
    );

Usage:
    # Daily update — current month only (default)
    uv run ingest_statsapi.py schedule

    # Refresh current + prior month to pick up retroactive lineup updates
    uv run ingest_statsapi.py schedule --start-date 2026-04-01

    # Full historical backfill from the beginning of Statcast data
    uv run ingest_statsapi.py schedule --start-date 2015-04-01

    uv run ingest_statsapi.py venues --venue-ids-file /path/to/venue_ids.csv
    uv run ingest_statsapi.py venues --venue-ids 1 2 3 31
"""

import argparse
import calendar
import csv
import json
import logging
import os
import sys
import time
from datetime import date, timedelta

import requests
import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from dotenv import load_dotenv

# Search from the script's location upward so the project-root .env is found
# regardless of which directory the script is invoked from.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

INGEST_START = date(2015, 4, 1)

STATSAPI_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
STATSAPI_SCHEDULE_PARAMS = {
    "sportId": 1,
    "gameType": "R",
    "hydrate": "lineups",
}

STATSAPI_VENUE_URL = "https://statsapi.mlb.com/api/v1/venues/{venue_id}"
STATSAPI_VENUE_PARAMS = {
    "hydrate": "fieldInfo,location,timezone,xrefId",
}

TARGET_DATABASE = "baseball_data"
TARGET_SCHEMA   = "statsapi"
SCHEDULE_TABLE  = "monthly_schedule"
VENUES_TABLE    = "venues_raw"

# Polite delay between API calls (seconds)
REQUEST_DELAY = 0.5


# ── Snowflake ─────────────────────────────────────────────────────────────────

def _load_private_key(path: str, passphrase: str | None) -> bytes:
    """Read a PEM private key file and return DER bytes for the Snowflake connector."""
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    """
    Build a Snowflake connection using private key auth when
    SNOWFLAKE_PRIVATE_KEY_PATH is set, otherwise fall back to password auth.
    """
    required_base = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required_base if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  TARGET_DATABASE,
        "schema":    TARGET_SCHEMA,
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        log.info("Authenticating with private key: %s", private_key_path)
        kwargs["private_key"] = _load_private_key(private_key_path, passphrase=None)
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        log.info("Authenticating with password")
        kwargs["password"] = password

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


# ── Snowflake writes ──────────────────────────────────────────────────────────

def upsert_month(
    conn: snowflake.connector.SnowflakeConnection,
    month_start: date,
    month_end: date,
    games_cnt: int,
    payload: dict,
) -> None:
    """Merge one month's schedule data into the target table."""
    json_str = json.dumps(payload)

    sql = f"""
        MERGE INTO {TARGET_DATABASE}.{TARGET_SCHEMA}.{SCHEDULE_TABLE} AS tgt
        USING (
            SELECT
                %(month_start)s::date    AS month_start_date,
                %(month_end)s::date      AS month_end_date,
                %(games_cnt)s::int       AS games_cnt,
                PARSE_JSON(%(json_str)s) AS json_field
        ) AS src
        ON tgt.month_start_date = src.month_start_date
        WHEN MATCHED THEN UPDATE SET
            month_end_date = src.month_end_date,
            games_cnt      = src.games_cnt,
            json_field     = src.json_field
        WHEN NOT MATCHED THEN INSERT (month_start_date, month_end_date, games_cnt, json_field)
            VALUES (src.month_start_date, src.month_end_date, src.games_cnt, src.json_field)
    """

    with conn.cursor() as cur:
        cur.execute(sql, {
            "month_start": month_start.isoformat(),
            "month_end":   month_end.isoformat(),
            "games_cnt":   games_cnt,
            "json_str":    json_str,
        })


def upsert_venue(
    conn: snowflake.connector.SnowflakeConnection,
    venue_id: int,
    payload: dict,
    ingest_date: date,
) -> None:
    """Merge one venue's API response into venues_raw, keyed on venue_id."""
    json_str = json.dumps(payload)

    sql = f"""
        MERGE INTO {TARGET_DATABASE}.{TARGET_SCHEMA}.{VENUES_TABLE} AS tgt
        USING (
            SELECT
                %(venue_id)s::number     AS venue_id,
                PARSE_JSON(%(json_str)s) AS json_field,
                %(ingest_date)s::date    AS ingest_date
        ) AS src
        ON tgt.venue_id = src.venue_id
        WHEN MATCHED THEN UPDATE SET
            json_field  = src.json_field,
            ingest_date = src.ingest_date
        WHEN NOT MATCHED THEN INSERT (venue_id, json_field, ingest_date)
            VALUES (src.venue_id, src.json_field, src.ingest_date)
    """

    with conn.cursor() as cur:
        cur.execute(sql, {
            "venue_id":    venue_id,
            "json_str":    json_str,
            "ingest_date": ingest_date.isoformat(),
        })


# ── Stats API fetchers ────────────────────────────────────────────────────────

def fetch_schedule(start: date, end: date) -> dict:
    """Call the Stats API schedule endpoint for the given date range."""
    params = {
        **STATSAPI_SCHEDULE_PARAMS,
        "startDate": start.isoformat(),
        "endDate":   end.isoformat(),
    }
    resp = requests.get(STATSAPI_SCHEDULE_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_venue(venue_id: int) -> dict:
    """Call the Stats API venue endpoint with full hydration for one venue."""
    url = STATSAPI_VENUE_URL.format(venue_id=venue_id)
    resp = requests.get(url, params=STATSAPI_VENUE_PARAMS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def extract_games_count(payload: dict) -> int:
    """Return the number of games in the schedule payload, defaulting to 0."""
    return int(payload.get("totalGames", 0))


# ── Month iteration ───────────────────────────────────────────────────────────

def iter_months(start: date, end: date):
    """Yield (month_start, month_end) pairs from start through end, inclusive."""
    current = start.replace(day=1)
    end_month = end.replace(day=1)

    while current <= end_month:
        last_day = calendar.monthrange(current.year, current.month)[1]
        yield current, current.replace(day=last_day)
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


# ── Venue ID loading ──────────────────────────────────────────────────────────

def load_venue_ids_from_file(path: str) -> list[int]:
    """
    Read venue IDs from a file. Accepts either a plain list of integers
    (one per line) or a CSV with a header row containing a VENUE_ID column.
    """
    venue_ids: list[int] = []
    with open(path, newline="") as fh:
        sample = fh.read(1024)
        fh.seek(0)
        # Sniff for CSV with header
        if "," in sample or sample.strip().upper().startswith("VENUE_ID"):
            reader = csv.DictReader(fh)
            col = next(
                (c for c in (reader.fieldnames or []) if c.strip().upper() == "VENUE_ID"),
                None,
            )
            if col is None:
                raise ValueError(f"No VENUE_ID column found in {path}. Columns: {reader.fieldnames}")
            for row in reader:
                raw = row[col].strip()
                if raw:
                    venue_ids.append(int(raw))
        else:
            for line in fh:
                raw = line.strip()
                if raw:
                    venue_ids.append(int(raw))
    return venue_ids


# ── Subcommand runners ────────────────────────────────────────────────────────

def run_schedule(
    conn: snowflake.connector.SnowflakeConnection,
    start: date,
    end: date,
) -> None:
    months = list(iter_months(start, end))
    total  = len(months)

    log.info(
        "Schedule ingest: %d month(s) from %s to %s",
        total, start.strftime("%Y-%m"), end.strftime("%Y-%m"),
    )

    for idx, (month_start, month_end) in enumerate(months, start=1):
        label = month_start.strftime("%Y-%m")
        log.info("[%d/%d] Fetching schedule %s", idx, total, label)

        try:
            payload = fetch_schedule(month_start, month_end)
        except requests.HTTPError as exc:
            log.warning("  HTTP error for %s: %s — skipping", label, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request failed for %s: %s — skipping", label, exc)
            time.sleep(REQUEST_DELAY)
            continue

        games_cnt = extract_games_count(payload)
        log.info("  %d game(s) found", games_cnt)

        try:
            upsert_month(conn, month_start, month_end, games_cnt, payload)
            log.info("  Upserted to Snowflake")
        except Exception as exc:
            log.error("  Snowflake write failed for %s: %s — skipping", label, exc)

        time.sleep(REQUEST_DELAY)

    log.info("Schedule ingest complete — processed %d month(s)", total)


def run_venues(conn: snowflake.connector.SnowflakeConnection, venue_ids: list[int]) -> None:
    today = date.today()
    total = len(venue_ids)

    log.info("Venue ingest: %d venue(s)", total)

    for idx, venue_id in enumerate(venue_ids, start=1):
        log.info("[%d/%d] Fetching venue %d", idx, total, venue_id)

        try:
            payload = fetch_venue(venue_id)
        except requests.HTTPError as exc:
            log.warning("  HTTP error for venue %d: %s — skipping", venue_id, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request failed for venue %d: %s — skipping", venue_id, exc)
            time.sleep(REQUEST_DELAY)
            continue

        try:
            upsert_venue(conn, venue_id, payload, today)
            log.info("  Upserted venue %d to Snowflake", venue_id)
        except Exception as exc:
            log.error("  Snowflake write failed for venue %d: %s — skipping", venue_id, exc)

        time.sleep(REQUEST_DELAY)

    log.info("Venue ingest complete — processed %d venue(s)", total)


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest MLB Stats API data into Snowflake.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    schedule_parser = sub.add_parser(
        "schedule",
        help="Ingest monthly schedule + lineup data for a configurable date range.",
    )
    schedule_parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "First date to ingest, inclusive. Defaults to the first day of the "
            "current calendar month. Pass 2015-04-01 for a full historical backfill."
        ),
    )
    schedule_parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "Last date to ingest, inclusive. Defaults to the last day of the "
            "current calendar month."
        ),
    )

    venues_parser = sub.add_parser(
        "venues",
        help="Ingest venue metadata for a list of venue IDs.",
    )
    id_group = venues_parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument(
        "--venue-ids-file",
        metavar="FILE",
        help="Path to a file containing venue IDs (one per line or CSV with VENUE_ID column).",
    )
    id_group.add_argument(
        "--venue-ids",
        nargs="+",
        type=int,
        metavar="ID",
        help="Space-separated list of venue IDs.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    log.info("Connecting to Snowflake (%s.%s)", TARGET_DATABASE, TARGET_SCHEMA)
    conn = get_snowflake_connection()

    try:
        if args.command == "schedule":
            today = date.today()
            if args.start_date:
                schedule_start = date.fromisoformat(args.start_date)
            else:
                schedule_start = today.replace(day=1)
            if args.end_date:
                schedule_end = date.fromisoformat(args.end_date)
            else:
                last_day = calendar.monthrange(today.year, today.month)[1]
                schedule_end = today.replace(day=last_day)
            run_schedule(conn, schedule_start, schedule_end)

        elif args.command == "venues":
            if args.venue_ids_file:
                venue_ids = load_venue_ids_from_file(args.venue_ids_file)
            else:
                venue_ids = args.venue_ids
            log.info("Loaded %d venue ID(s)", len(venue_ids))
            run_venues(conn, venue_ids)

    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
