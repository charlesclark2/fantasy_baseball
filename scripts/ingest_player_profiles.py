"""
ingest_player_profiles.py
--------------------------
Ingests MLB Stats API player profile data (height, weight, birth_date,
primary_position) into baseball_data.statsapi.player_profiles.

Two modes:

  backfill  — Collects all unique batter and pitcher IDs from
              mart_pitch_play_event (2020+) and batch-fetches profiles from
              /api/v1/people?personIds=.... Appends rows to player_profiles_raw;
              stg_statsapi_player_profiles deduplicates downstream.

  update    — Calls /api/v1/people/changes to fetch recently updated profiles
              (weight corrections, name changes) and also detects new player IDs
              from the last 14 days of game data absent from player_profiles_raw
              (call-ups, international signings). Designed for weekly Dagster
              invocation.

Authentication — same environment variables as ingest_statsapi.py:
    Private key (preferred):
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
        SNOWFLAKE_PRIVATE_KEY_PATH  (passphrase optional via SNOWFLAKE_PRIVATE_KEY_PASSPHRASE)
        SNOWFLAKE_ROLE              (optional)
    Password fallback:
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, SNOWFLAKE_WAREHOUSE
        SNOWFLAKE_ROLE              (optional)

DDL (created inline at startup if not exists):
    CREATE TABLE IF NOT EXISTS baseball_data.statsapi.player_profiles_raw (
        player_id              NUMBER        NOT NULL,
        full_name              TEXT,
        birth_date             DATE,
        height_inches          NUMBER,
        weight_lbs             NUMBER,
        primary_position_code  TEXT,
        active                 BOOLEAN,
        last_fetched_at        TIMESTAMP_NTZ
    );
    Deduplication (latest row per player_id) is handled by the dbt model
    stg_statsapi_player_profiles via ROW_NUMBER() OVER (PARTITION BY player_id
    ORDER BY last_fetched_at DESC).

Usage:
    # One-time backfill for all historical player IDs (2020+)
    uv run scripts/ingest_player_profiles.py backfill

    # Weekly update — changed profiles + new call-ups
    uv run scripts/ingest_player_profiles.py update
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

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

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

STATSAPI_BASE = "https://statsapi.mlb.com/api/v1"
BATCH_SIZE    = 200   # max personIds per bulk /people request
REQUEST_DELAY = 0.3   # seconds between API calls (polite crawl rate)

TARGET_DB     = "baseball_data"
TARGET_SCHEMA = "statsapi"
TARGET_TABLE  = "player_profiles_raw"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE} (
    player_id              NUMBER        NOT NULL,
    full_name              TEXT,
    birth_date             DATE,
    height_inches          NUMBER,
    weight_lbs             NUMBER,
    primary_position_code  TEXT,
    active                 BOOLEAN,
    last_fetched_at        TIMESTAMP_NTZ
)
"""

# ── Snowflake connection ───────────────────────────────────────────────────────

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


def get_snowflake_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  TARGET_DB,
        "schema":    TARGET_SCHEMA,
    }
    if pk_path := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(pk_path, passphrase)
    else:
        pw = os.environ.get("SNOWFLAKE_PASSWORD")
        if not pw:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        kwargs["password"] = pw
    if role := os.environ.get("SNOWFLAKE_ROLE"):
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


# ── Height parsing ─────────────────────────────────────────────────────────────

_HEIGHT_RE = re.compile(r"(\d+)'\s*(\d+)\"?")


def parse_height_inches(s: str | None) -> int | None:
    if not s:
        return None
    m = _HEIGHT_RE.match(s.strip())
    if not m:
        log.warning("Unparseable height string: %r", s)
        return None
    return int(m.group(1)) * 12 + int(m.group(2))


# ── API fetchers ───────────────────────────────────────────────────────────────

def fetch_people_bulk(player_ids: list[int]) -> list[dict]:
    """Fetch up to BATCH_SIZE player profiles in one /people?personIds=... call."""
    ids_str = ",".join(str(i) for i in player_ids)
    resp = requests.get(f"{STATSAPI_BASE}/people", params={"personIds": ids_str}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("people", [])


def fetch_people_changes(updated_since: datetime) -> list[dict]:
    """Fetch profiles updated since the given UTC datetime via /people/changes."""
    since_str = updated_since.strftime("%Y-%m-%dT%H:%M:%S")
    resp = requests.get(
        f"{STATSAPI_BASE}/people/changes",
        params={"updatedSince": since_str},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("people", [])


def parse_person(p: dict) -> dict | None:
    """Extract structured fields from a StatsAPI person object. Returns None if no player_id."""
    pid = p.get("id")
    if not pid:
        return None
    height_raw = p.get("height")
    return {
        "player_id":             str(pid),
        "full_name":             p.get("fullName") or "",
        "birth_date":            p.get("birthDate") or "",
        "height_inches":         str(parse_height_inches(height_raw)) if height_raw else "",
        "weight_lbs":            str(p.get("weight") or ""),
        "primary_position_code": (p.get("primaryPosition") or {}).get("code") or "",
        "active":                str(bool(p.get("active", False))),
        "last_fetched_at":       datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Snowflake write ───────────────────────────────────────────────────────────

def insert_profiles(conn: snowflake.connector.SnowflakeConnection, profiles: list[dict]) -> int:
    """Append profiles into player_profiles_raw via VARCHAR temp table. Returns rows inserted."""
    if not profiles:
        return 0

    tmp = f"tmp_player_profiles_{uuid.uuid4().hex[:8]}"

    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TEMPORARY TABLE {tmp} (
                player_id              VARCHAR,
                full_name              VARCHAR,
                birth_date             VARCHAR,
                height_inches          VARCHAR,
                weight_lbs             VARCHAR,
                primary_position_code  VARCHAR,
                active                 VARCHAR,
                last_fetched_at        VARCHAR
            )
        """)

        cur.executemany(
            f"""INSERT INTO {tmp} VALUES (
                %(player_id)s, %(full_name)s, %(birth_date)s,
                %(height_inches)s, %(weight_lbs)s, %(primary_position_code)s,
                %(active)s, %(last_fetched_at)s
            )""",
            profiles,
        )

        cur.execute(f"""
            INSERT INTO {TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE} (
                player_id, full_name, birth_date, height_inches, weight_lbs,
                primary_position_code, active, last_fetched_at
            )
            SELECT
                TRY_TO_NUMBER(player_id),
                full_name::TEXT,
                TRY_TO_DATE(birth_date),
                TRY_TO_NUMBER(height_inches),
                TRY_TO_NUMBER(weight_lbs),
                primary_position_code::TEXT,
                (active = 'True')::BOOLEAN,
                TRY_TO_TIMESTAMP_NTZ(last_fetched_at)
            FROM {tmp}
            WHERE TRY_TO_NUMBER(player_id) IS NOT NULL
        """)

        return cur.rowcount


# ── Snowflake queries ─────────────────────────────────────────────────────────

def query_all_historical_player_ids(conn: snowflake.connector.SnowflakeConnection) -> set[int]:
    """Union all batter and pitcher IDs from mart_pitch_play_event (2020+)."""
    sql = """
        SELECT DISTINCT batter_id AS player_id
        FROM baseball_data.betting.mart_pitch_play_event
        WHERE game_year >= 2020
        UNION
        SELECT DISTINCT pitcher_id AS player_id
        FROM baseball_data.betting.mart_pitch_play_event
        WHERE game_year >= 2020
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {int(row[0]) for row in cur.fetchall() if row[0] is not None}


def query_missing_cluster_player_ids(conn: snowflake.connector.SnowflakeConnection) -> set[int]:
    """
    Return player IDs that appear in batter_clusters or pitcher_clusters but have
    no row in player_profiles_raw. These are pre-2020 retired players that the
    original backfill (2020+ only) never fetched.
    """
    sql = f"""
        WITH cluster_ids AS (
            SELECT DISTINCT batter_id AS player_id
            FROM baseball_data.statsapi.batter_clusters
            UNION
            SELECT DISTINCT pitcher_id AS player_id
            FROM baseball_data.statsapi.pitcher_clusters
        )
        SELECT c.player_id
        FROM cluster_ids c
        LEFT JOIN {TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE} p
            ON c.player_id = p.player_id
        WHERE p.player_id IS NULL
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {int(row[0]) for row in cur.fetchall() if row[0] is not None}


def query_missing_recent_player_ids(conn: snowflake.connector.SnowflakeConnection) -> set[int]:
    """Return player IDs in the last 14 days of game data not yet in player_profiles."""
    sql = f"""
        WITH recent_ids AS (
            SELECT DISTINCT batter_id AS player_id
            FROM baseball_data.betting.mart_pitch_play_event
            WHERE game_date >= CURRENT_DATE - 14
            UNION
            SELECT DISTINCT pitcher_id AS player_id
            FROM baseball_data.betting.mart_pitch_play_event
            WHERE game_date >= CURRENT_DATE - 14
        )
        SELECT r.player_id
        FROM recent_ids r
        LEFT JOIN {TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE} p
            ON r.player_id = p.player_id
        WHERE p.player_id IS NULL
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {int(row[0]) for row in cur.fetchall() if row[0] is not None}


def query_last_fetch_time(conn: snowflake.connector.SnowflakeConnection) -> datetime:
    """Return MAX(last_fetched_at); defaults to 7 days ago if table is empty."""
    sql = f"SELECT MAX(last_fetched_at) FROM {TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE}"
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        if row and row[0]:
            ts = row[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return ts
    return datetime.now(tz=timezone.utc) - timedelta(days=7)


# ── Batch fetch + merge ───────────────────────────────────────────────────────

def fetch_and_insert_ids(
    conn: snowflake.connector.SnowflakeConnection,
    player_ids: list[int],
) -> int:
    """Batch-fetch profiles for player_ids in BATCH_SIZE chunks and INSERT."""
    total_merged = 0
    batches = [player_ids[i:i + BATCH_SIZE] for i in range(0, len(player_ids), BATCH_SIZE)]

    for batch_idx, batch in enumerate(batches, start=1):
        log.info("[%d/%d] Fetching %d player profiles", batch_idx, len(batches), len(batch))
        try:
            people = fetch_people_bulk(batch)
        except requests.HTTPError as exc:
            log.warning("  HTTP error on batch %d: %s — skipping", batch_idx, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request error on batch %d: %s — skipping", batch_idx, exc)
            time.sleep(REQUEST_DELAY)
            continue

        profiles = [p for raw in people if (p := parse_person(raw)) is not None]
        n = insert_profiles(conn, profiles)
        log.info("  Inserted %d row(s)", n)
        total_merged += n
        time.sleep(REQUEST_DELAY)

    return total_merged


# ── Subcommand runners ────────────────────────────────────────────────────────

def run_cluster_backfill(conn: snowflake.connector.SnowflakeConnection) -> None:
    """
    Fetch profiles for player IDs in batter_clusters / pitcher_clusters that are
    absent from player_profiles_raw. Fills the pre-2020 retired-player gap left by
    the original backfill mode (which only sourced IDs from mart_pitch_play_event
    where game_year >= 2020).

    After this completes, run:
        dbtf run --select stg_statsapi_player_profiles
    to refresh the deduped downstream table.
    """
    log.info("Cluster backfill: finding player IDs in cluster tables missing from player_profiles_raw")
    missing_ids = query_missing_cluster_player_ids(conn)
    log.info("Found %d player ID(s) to backfill", len(missing_ids))

    if not missing_ids:
        log.info("No missing IDs — player_profiles_raw already has full cluster coverage")
        return

    total = fetch_and_insert_ids(conn, sorted(missing_ids))
    log.info("Cluster backfill complete — %d total rows inserted into player_profiles_raw", total)
    log.info("Next step: run `dbtf run --select stg_statsapi_player_profiles` to refresh downstream")


def run_backfill(conn: snowflake.connector.SnowflakeConnection) -> None:
    log.info("Backfill: collecting all historical player IDs from Snowflake (2020+)")
    all_ids = query_all_historical_player_ids(conn)
    log.info("Found %d unique player IDs", len(all_ids))

    if not all_ids:
        log.warning("No player IDs found — aborting backfill")
        return

    total = fetch_and_insert_ids(conn, sorted(all_ids))
    log.info("Backfill complete — %d total rows inserted", total)


def run_update(conn: snowflake.connector.SnowflakeConnection) -> None:
    log.info("Update: fetching changed profiles and new player IDs")

    # 1. Changed profiles via people/changes with 1-day overlap guard
    last_fetch = query_last_fetch_time(conn)
    updated_since = last_fetch - timedelta(days=1)
    log.info("Fetching changes since %s", updated_since.isoformat())

    try:
        changed_people = fetch_people_changes(updated_since)
        log.info("  %d changed profile(s) from people/changes", len(changed_people))
    except requests.RequestException as exc:
        log.warning("people/changes request failed: %s — skipping change fetch", exc)
        changed_people = []

    if changed_people:
        changed_profiles = [p for raw in changed_people if (p := parse_person(raw)) is not None]
        n = insert_profiles(conn, changed_profiles)
        log.info("  Inserted %d changed profile(s)", n)

    # 2. New player IDs from recent game data not yet in player_profiles
    new_ids = query_missing_recent_player_ids(conn)
    if new_ids:
        log.info("Found %d new player ID(s) not in player_profiles (call-ups/signings)", len(new_ids))
        fetch_and_insert_ids(conn, sorted(new_ids))
    else:
        log.info("No new player IDs found in last 14 days")

    log.info("Update complete")


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest StatsAPI player profiles (height, weight, birth_date) into Snowflake.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backfill", help="Fetch all historical player profiles (2020+). Idempotent.")
    sub.add_parser(
        "cluster-backfill",
        help=(
            "Fetch profiles for player IDs in batter_clusters/pitcher_clusters that are "
            "absent from player_profiles_raw (pre-2020 retired players). One-time run. "
            "Follow up with: dbtf run --select stg_statsapi_player_profiles"
        ),
    )
    sub.add_parser("update", help="Fetch recently changed profiles and new call-ups. Run weekly.")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    log.info("Connecting to Snowflake (%s.%s)", TARGET_DB, TARGET_SCHEMA)
    conn = get_snowflake_connection()

    try:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        log.info("player_profiles table ready")

        if args.command == "backfill":
            run_backfill(conn)
        elif args.command == "cluster-backfill":
            run_cluster_backfill(conn)
        elif args.command == "update":
            run_update(conn)
    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
