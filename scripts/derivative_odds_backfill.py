"""
derivative_odds_backfill.py
---------------------------
E2.0 — Backfills derivative-market historical CLOSING odds (team totals,
alternate totals, first-5-innings / first-half totals and moneyline) for MLB
games via The Odds API per-event historical event-odds endpoint.

  ⚠️ EVAL/CLV-ONLY — this data is for validation of E2 derivative gates only.
     It must NEVER be joined into model training feature matrices (market-blind
     constraint, Edge Program §0.1 Principle 3).

Shared plumbing with E5.1 (player-prop historical backfill): same endpoint
pattern, cost model, and idempotency logic are reusable for props.

TWO-PHASE DESIGN (keeps Snowflake warehouse off during the ~hour-long API loop):

  Phase 1 — fetch:
    Opens Snowflake once (brief query to get event list), then closes the
    connection. Fetches all derivative odds from the Odds API and writes the
    raw rows to a local Parquet file. No Snowflake warehouse running during
    the API loop.

  Phase 2 — ingest:
    Opens Snowflake, PUT the Parquet file to the target table's internal stage,
    COPY INTO a transient staging table, INSERT INTO the real target (with
    PARSE_JSON), DROP the staging table. One warehouse wake-up, one bulk write.

Endpoint:
    GET /v4/historical/sports/baseball_mlb/events/{eventId}/odds
    params: date (snapshot), markets, regions, oddsFormat, dateFormat
    Response envelope: {timestamp, previous_timestamp, next_timestamp, data:{event+bookmakers}}
    Cost: 10 × len(markets) × len(regions) credits per call (additional markets)

Coverage: additional-market history only available from 2023-05-03 onward.
Passing date=commence_time gives the last pre-game (closing) snapshot.

Target table DDL (run once as operator before first ingest):
    CREATE TABLE IF NOT EXISTS baseball_data.oddsapi.derivative_odds_raw (
        ingestion_ts          TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        load_id               VARCHAR,
        event_id              VARCHAR,
        requested_snapshot_ts TIMESTAMP_NTZ,
        actual_snapshot_ts    TIMESTAMP_NTZ,
        previous_snapshot_ts  TIMESTAMP_NTZ,
        next_snapshot_ts      TIMESTAMP_NTZ,
        markets_requested     VARCHAR,
        regions_requested     VARCHAR,
        x_requests_remaining  INTEGER,
        x_requests_last       INTEGER,
        raw_json              VARIANT,
        fetch_status          VARCHAR   -- 'success' | 'not_found' | 'no_data' | 'error'
    );

    -- If the table already exists without fetch_status, add the column:
    ALTER TABLE baseball_data.oddsapi.derivative_odds_raw ADD COLUMN IF NOT EXISTS fetch_status VARCHAR;

Usage:
    # Phase 1: fetch from API → local Parquet (Snowflake disconnected during loop)
    uv run python scripts/derivative_odds_backfill.py fetch
    uv run python scripts/derivative_odds_backfill.py fetch --start-date 2024-04-01 --end-date 2024-10-31
    uv run python scripts/derivative_odds_backfill.py fetch --output /tmp/deriv_2024.parquet
    uv run python scripts/derivative_odds_backfill.py fetch --dry-run   # list events, no API calls

    # Phase 2: ingest the Parquet into Snowflake (one bulk write)
    uv run python scripts/derivative_odds_backfill.py ingest --file /tmp/deriv_2024.parquet

Environment:
    ODDS_API_KEY           — MAIN-tier Odds API key (starter key excludes additional markets)
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH [+ SNOWFLAKE_PRIVATE_KEY_PASSPHRASE]
      OR SNOWFLAKE_PASSWORD (fallback)
    SNOWFLAKE_ROLE         (optional)
    ODDS_TARGET_DATABASE   (default: baseball_data)
    ODDS_TARGET_SCHEMA     (default: oddsapi)
    DERIVATIVE_ODDS_TABLE  (default: derivative_odds_raw)
"""

import argparse
import json
import logging
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# E11.1-W11-E: gated Snowflake→S3 dual-write for the LIVE derivative capture (cmd_capture).
# Flipping the writer S3-native lets the daily W11_W3PRE_DAILY export bridge be retired — the
# live rows land directly in lakehouse_raw/derivative_odds_raw/, which stg_derivative_odds already
# reads (duckdb branch). Uses the SHARED W11 wave switch W11_RAW_WRITE_MODE (default 'snowflake' =
# unchanged), NOT the odds family's LAKEHOUSE_RAW_WRITE_MODE — that shared env is already 's3'/'both'
# in prod, which would flip this writer the instant it deploys, before the operator validates. The
# lean derivative-capture image (services/derivative_capture/Dockerfile) now COPYs scripts/utils/ +
# installs boto3 so write_raw_rows_s3 resolves; the script runs from /app OR scripts/, so make the
# utils package importable from either cwd.
import sys as _sys  # noqa: E402

_sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.lakehouse_raw_writer import (  # noqa: E402
    lakehouse_write_legs,
    w11_write_mode,
    write_raw_rows_s3,
)

_LAKEHOUSE_SOURCE = "derivative_odds_raw"

# The exact column set stg_derivative_odds reads + the §3 export bridge emits (NO fetch_status —
# the bridge does not export it and the stg filters on raw_json). Project the live rows to this set
# so the writer-written S3 parts are schema-identical to the bridge-written parts (union_by_name).
_DERIVATIVE_S3_COLS = (
    "ingestion_ts", "load_id", "event_id",
    "requested_snapshot_ts", "actual_snapshot_ts", "previous_snapshot_ts", "next_snapshot_ts",
    "markets_requested", "regions_requested", "x_requests_remaining", "x_requests_last",
    "raw_json",
)


def _derivative_mirror_rows(rows: list[dict]) -> list[dict]:
    """Project live-capture rows to the S3 raw schema (drop fetch_status; keep only successful,
    bookmaker-bearing rows — mirrors the stg's `where raw_json is not null` filter so failed/no-data
    rows never bloat the mirror). raw_json is already a JSON STRING (json.dumps'd in cmd_capture) →
    write_raw_rows_s3 passes it through unchanged."""
    return [
        {c: r.get(c) for c in _DERIVATIVE_S3_COLS}
        for r in rows
        if r.get("raw_json") is not None
    ]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
HIST_EVENT_ODDS_ENDPOINT = "/historical/sports/baseball_mlb/events/{event_id}/odds"

DERIVATIVE_HISTORY_START = date(2023, 5, 3)

# Correct baseball F5 keys (confirmed live 2026-06-24: 16 books offered on the live endpoint).
# h2h_h1/totals_h1 are the WRONG "generic 1st Half" family — baseball books don't populate them.
DEFAULT_DERIVATIVE_MARKETS = [
    "team_totals",
    "alternate_totals",
    "h2h_1st_5_innings",
    "totals_1st_5_innings",
    "totals_1st_1_innings",   # NRFI
]
DEFAULT_REGIONS = ["us", "us2", "eu"]
DEFAULT_ODDS_FORMAT = "american"
DEFAULT_DATE_FORMAT = "iso"

REQUEST_DELAY_SECONDS = 0.3
REQUEST_TIMEOUT_SECONDS = 45
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [5, 15, 30]

_DEFAULT_DATABASE = "baseball_data"
_DEFAULT_SCHEMA = "oddsapi"
_DEFAULT_TABLE = "derivative_odds_raw"
_EVENTS_SOURCE_TABLE = "mlb_events_raw"

# Parquet column names (all stored as VARCHAR strings)
PARQUET_COLS = [
    "ingestion_ts",
    "load_id",
    "event_id",
    "requested_snapshot_ts",
    "actual_snapshot_ts",
    "previous_snapshot_ts",
    "next_snapshot_ts",
    "markets_requested",
    "regions_requested",
    "x_requests_remaining",
    "x_requests_last",
    "raw_json",
    "fetch_status",   # 'success' | 'not_found' | 'no_data' | 'error'
]

# Staging table for the Parquet → Snowflake ingest step
_STAGING_TABLE = "stg_derivative_odds_parquet"

# ── E2.0b live capture / probe endpoints ──────────────────────────────────────

LIVE_EVENTS_ENDPOINT = "/sports/baseball_mlb/events"
EVENT_MARKETS_ENDPOINT = "/sports/baseball_mlb/events/{event_id}/markets"
LIVE_EVENT_ODDS_ENDPOINT = "/sports/baseball_mlb/events/{event_id}/odds"

# Default curated bookmakers for the E2.0b probe
PROBE_BOOKMAKERS = ["bovada", "pinnacle", "fanduel", "draftkings", "betmgm", "caesars"]


# ── Target resolution ──────────────────────────────────────────────────────────

def _target_fqn() -> str:
    db = os.environ.get("ODDS_TARGET_DATABASE", _DEFAULT_DATABASE)
    schema = os.environ.get("ODDS_TARGET_SCHEMA", _DEFAULT_SCHEMA)
    table = os.environ.get("DERIVATIVE_ODDS_TABLE", _DEFAULT_TABLE)
    return f"{db}.{schema}.{table}"


def _staging_fqn() -> str:
    db = os.environ.get("ODDS_TARGET_DATABASE", _DEFAULT_DATABASE)
    schema = os.environ.get("ODDS_TARGET_SCHEMA", _DEFAULT_SCHEMA)
    return f"{db}.{schema}.{_STAGING_TABLE}"


def _staging_stage() -> str:
    return f"@{_staging_fqn().rsplit('.', 1)[0]}.%{_STAGING_TABLE}"


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


def connect_snowflake() -> snowflake.connector.SnowflakeConnection:
    _raw_account = os.environ["SNOWFLAKE_ACCOUNT"]
    account = _raw_account.strip()
    if "://" in account:
        account = account.split("://", 1)[1]
    account = account.split("/", 1)[0]
    account = account.split(".snowflakecomputing.com", 1)[0]
    if account != _raw_account:
        log.warning("SNOWFLAKE_ACCOUNT normalized: raw=%r -> used=%r", _raw_account, account)
    if any(c in account for c in "./"):
        log.warning(
            "SNOWFLAKE_ACCOUNT still contains a dot/slash after normalization: %r "
            "— the connector will reject this; fix the env var to the bare "
            "org-account identifier (e.g. IHUPICS-DP59975).", account)
    params: dict[str, Any] = {
        "account":   account,
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
    }
    if role := os.environ.get("SNOWFLAKE_ROLE"):
        params["role"] = role
    key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if key_path:
        params["private_key"] = _load_private_key(
            key_path, os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        )
    else:
        params["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**params)


# ── Event discovery ────────────────────────────────────────────────────────────

def fetch_events_to_backfill(
    conn: snowflake.connector.SnowflakeConnection,
    target_fqn: str,
    start_date: date,
    end_date: date,
    limit: int | None = None,
) -> list[dict]:
    """Return [{event_id, commence_time, home_team, away_team}] not yet in target."""
    db = os.environ.get("ODDS_TARGET_DATABASE", _DEFAULT_DATABASE)
    schema = os.environ.get("ODDS_TARGET_SCHEMA", _DEFAULT_SCHEMA)
    events_fqn = f"{db}.{schema}.{_EVENTS_SOURCE_TABLE}"
    limit_clause = f"LIMIT {limit}" if limit else ""
    sql = f"""
        WITH events_flat AS (
            SELECT
                evt.value:id::VARCHAR                    AS event_id,
                evt.value:commence_time::TIMESTAMP_NTZ   AS commence_time,
                evt.value:home_team::VARCHAR              AS home_team,
                evt.value:away_team::VARCHAR              AS away_team
            FROM {events_fqn},
            LATERAL FLATTEN(input => raw_json) evt
            WHERE raw_json IS NOT NULL
              AND TYPEOF(raw_json) = 'ARRAY'
              AND ARRAY_SIZE(raw_json) > 0
              AND evt.value:id IS NOT NULL
              AND evt.value:commence_time IS NOT NULL
        ),
        deduped AS (
            SELECT event_id, commence_time, home_team, away_team,
                   ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY commence_time) AS rn
            FROM events_flat
        ),
        already_fetched AS (
            SELECT DISTINCT event_id FROM {target_fqn} WHERE event_id IS NOT NULL
        )
        SELECT d.event_id, d.commence_time, d.home_team, d.away_team
        FROM deduped d
        WHERE d.rn = 1
          AND d.commence_time >= '{start_date.isoformat()}T00:00:00'::TIMESTAMP_NTZ
          AND d.commence_time <  '{(end_date + timedelta(days=1)).isoformat()}T00:00:00'::TIMESTAMP_NTZ
          AND d.event_id NOT IN (SELECT event_id FROM already_fetched)
        ORDER BY d.commence_time ASC
        {limit_clause}
    """
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    return [
        {"event_id": r[0], "commence_time": r[1], "home_team": r[2], "away_team": r[3]}
        for r in rows
    ]


# ── API fetch ──────────────────────────────────────────────────────────────────

def fetch_event_derivative_odds(
    event_id: str,
    snapshot_ts: datetime,
    markets: list[str],
    regions: list[str],
    api_key: str,
) -> tuple[dict | None, str]:
    """Return (payload, status) where status ∈ {'success','not_found','no_data','error'}.

    'not_found' — API 404 EVENT_NOT_FOUND; event will be written as a sentinel row so
                  future runs skip it without spending API credits.
    'no_data'   — 200 OK or 422 but no bookmaker data at this snapshot.
    'error'     — network/timeout after all retries, or 429 rate-limit.
    """
    url = ODDS_API_BASE_URL + HIST_EVENT_ODDS_ENDPOINT.format(event_id=event_id)
    params = {
        "apiKey":     api_key,
        "date":       snapshot_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "markets":    ",".join(markets),
        "regions":    ",".join(regions),
        "oddsFormat": DEFAULT_ODDS_FORMAT,
        "dateFormat": DEFAULT_DATE_FORMAT,
    }

    resp = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            break
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS[attempt - 1]
                log.warning(
                    "request error event=%s (attempt %d/%d), retrying in %ds: %s",
                    event_id, attempt, MAX_RETRIES, wait, exc,
                )
                time.sleep(wait)
            else:
                log.warning(
                    "request error event=%s: giving up after %d attempts: %s",
                    event_id, MAX_RETRIES, exc,
                )
                return None, "error"

    remaining = resp.headers.get("x-requests-remaining")
    last = resp.headers.get("x-requests-last")

    if resp.status_code == 404:
        log.warning("unexpected status 404 for event=%s: %s", event_id, resp.text[:200])
        return None, "not_found"
    if resp.status_code == 422:
        log.info("no derivative data: event=%s snapshot=%s (422)", event_id, params["date"])
        return None, "no_data"
    if resp.status_code == 429:
        log.warning("rate limited on event=%s, sleeping 60s", event_id)
        time.sleep(60)
        return None, "error"
    if resp.status_code != 200:
        log.warning("unexpected status %s for event=%s: %s", resp.status_code, event_id, resp.text[:200])
        return None, "error"

    try:
        payload = resp.json()
    except ValueError as exc:
        log.warning("JSON parse error for event=%s: %s", event_id, exc)
        return None, "error"

    payload["_x_requests_remaining"] = int(remaining) if remaining else None
    payload["_x_requests_last"] = int(last) if last else None
    return payload, "success"


# ── Parquet helpers ────────────────────────────────────────────────────────────

def write_parquet(rows: list[dict], output_path: Path) -> None:
    import pandas as pd

    df = pd.DataFrame(rows, columns=PARQUET_COLS).astype("string")  # all VARCHAR, no datetime objects
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    log.info("wrote %d rows → %s", len(df), output_path)


# ── Snowflake ingest ───────────────────────────────────────────────────────────

def bulk_load_parquet(
    conn: snowflake.connector.SnowflakeConnection,
    parquet_path: Path,
    target_fqn: str,
    staging_fqn: str,
    staging_stage: str,
) -> int:
    """PUT parquet → internal stage → COPY INTO staging → INSERT SELECT PARSE_JSON → DROP staging.

    Warehouse is used only for COPY INTO + INSERT — PUT is client-side (no compute).
    Returns the number of rows inserted.
    """
    put_path = str(parquet_path.resolve()).replace("\\", "/")
    log.info("bulk load: %s → %s", parquet_path.name, target_fqn)

    create_staging_sql = f"""
        CREATE OR REPLACE TRANSIENT TABLE {staging_fqn} (
            ingestion_ts          VARCHAR,
            load_id               VARCHAR,
            event_id              VARCHAR,
            requested_snapshot_ts VARCHAR,
            actual_snapshot_ts    VARCHAR,
            previous_snapshot_ts  VARCHAR,
            next_snapshot_ts      VARCHAR,
            markets_requested     VARCHAR,
            regions_requested     VARCHAR,
            x_requests_remaining  VARCHAR,
            x_requests_last       VARCHAR,
            raw_json              VARCHAR,
            fetch_status          VARCHAR
        )
    """

    insert_sql = f"""
        INSERT INTO {target_fqn} (
            ingestion_ts, load_id, event_id,
            requested_snapshot_ts, actual_snapshot_ts,
            previous_snapshot_ts, next_snapshot_ts,
            markets_requested, regions_requested,
            x_requests_remaining, x_requests_last,
            raw_json, fetch_status
        )
        SELECT
            TRY_CAST(ingestion_ts          AS TIMESTAMP_NTZ),
            load_id,
            event_id,
            TRY_CAST(requested_snapshot_ts AS TIMESTAMP_NTZ),
            TRY_CAST(actual_snapshot_ts    AS TIMESTAMP_NTZ),
            TRY_CAST(previous_snapshot_ts  AS TIMESTAMP_NTZ),
            TRY_CAST(next_snapshot_ts      AS TIMESTAMP_NTZ),
            markets_requested,
            regions_requested,
            TRY_CAST(x_requests_remaining  AS INTEGER),
            TRY_CAST(x_requests_last       AS INTEGER),
            PARSE_JSON(raw_json),
            -- backward-compat: Parquets written before fetch_status was added have NULL here;
            -- those files only ever contained successful rows (404s were silently dropped)
            COALESCE(fetch_status, 'success')
        FROM {staging_fqn}
    """

    with conn.cursor() as cur:
        cur.execute(create_staging_sql)

        # PUT is client-side — no warehouse compute
        cur.execute(
            f"PUT 'file://{put_path}' {staging_stage} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )

        # COPY INTO reads the Parquet; warehouse wakes here
        cur.execute(
            f"COPY INTO {staging_fqn} FROM {staging_stage} "
            "FILE_FORMAT=(TYPE=PARQUET) MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE PURGE=TRUE"
        )

        cur.execute(f"SELECT COUNT(*) FROM {staging_fqn}")
        staged = cur.fetchone()[0]
        log.info("  staged %d row(s), inserting with PARSE_JSON ...", staged)

        cur.execute(insert_sql)
        conn.commit()

        cur.execute(f"DROP TABLE IF EXISTS {staging_fqn}")

    log.info("  inserted %d rows into %s", staged, target_fqn)
    return staged


# ── Live events discovery (E2.0b) ────────────────────────────────────────────

def fetch_upcoming_events(api_key: str, lookahead_hours: int = 24) -> list[dict]:
    """Return upcoming MLB events from the live events endpoint (1 credit).

    Each item: {id, commence_time (ISO str), home_team, away_team, ...}.
    """
    now = datetime.now(timezone.utc)
    url = ODDS_API_BASE_URL + LIVE_EVENTS_ENDPOINT
    params = {
        "apiKey":            api_key,
        "dateFormat":        DEFAULT_DATE_FORMAT,
        "commenceTimeFrom":  now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo":    (now + timedelta(hours=lookahead_hours)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        log.warning("fetch_upcoming_events: request error: %s", exc)
        return []
    remaining = resp.headers.get("x-requests-remaining", "?")
    if resp.status_code != 200:
        log.warning("fetch_upcoming_events: status %s: %s", resp.status_code, resp.text[:200])
        return []
    events = resp.json() or []
    log.info(
        "live events: %d upcoming in next %dh  credits_remaining=%s",
        len(events), lookahead_hours, remaining,
    )
    return events


def probe_event_markets(event_id: str, api_key: str, bookmakers: list[str]) -> list[dict]:
    """Call the Event Markets endpoint for one event (Schema 6 — no odds payload).

    Returns list of bookmaker objects: [{key, title, last_update, markets:[{key,last_update}]}].
    Cheap: no odds payload, ~1 credit per call.
    """
    url = ODDS_API_BASE_URL + EVENT_MARKETS_ENDPOINT.format(event_id=event_id)
    params = {
        "apiKey":     api_key,
        "bookmakers": ",".join(bookmakers),
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        log.warning("probe_event_markets event=%s: request error: %s", event_id, exc)
        return []
    if resp.status_code != 200:
        log.warning(
            "probe_event_markets event=%s: status %s: %s",
            event_id, resp.status_code, resp.text[:200],
        )
        return []
    result = resp.json() or []
    bookmakers_data = result if isinstance(result, list) else result.get("bookmakers", [])
    log.debug(
        "  event=%s  %d bookmakers  credits_remaining=%s",
        event_id, len(bookmakers_data), resp.headers.get("x-requests-remaining", "?"),
    )
    return bookmakers_data


# ── Live per-event odds fetch (E2.0b) ─────────────────────────────────────────

def fetch_live_event_derivative_odds(
    event_id: str,
    markets: list[str],
    regions: list[str],
    api_key: str,
) -> tuple[dict | None, str]:
    """Fetch live (non-historical) derivative odds for a single upcoming event.

    Unlike fetch_event_derivative_odds(), hits the live per-event endpoint without a
    date param and returns the event object directly (no timestamp wrapper).

    Returns (payload, status) where status ∈ {'success','not_found','no_data','error'}.
    Cost: unique markets returned × regions.
    """
    url = ODDS_API_BASE_URL + LIVE_EVENT_ODDS_ENDPOINT.format(event_id=event_id)
    params = {
        "apiKey":     api_key,
        "markets":    ",".join(markets),
        "regions":    ",".join(regions),
        "oddsFormat": DEFAULT_ODDS_FORMAT,
        "dateFormat": DEFAULT_DATE_FORMAT,
    }

    resp = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            break
        except requests.RequestException as exc:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS[attempt - 1]
                log.warning(
                    "live odds request error event=%s (attempt %d/%d), retry in %ds: %s",
                    event_id, attempt, MAX_RETRIES, wait, exc,
                )
                time.sleep(wait)
            else:
                log.warning(
                    "live odds request error event=%s: giving up after %d attempts: %s",
                    event_id, MAX_RETRIES, exc,
                )
                return None, "error"

    remaining = resp.headers.get("x-requests-remaining")
    last = resp.headers.get("x-requests-last")

    if resp.status_code == 404:
        log.warning("404 for live event=%s", event_id)
        return None, "not_found"
    if resp.status_code == 422:
        log.info("no derivative data (422): live event=%s", event_id)
        return None, "no_data"
    if resp.status_code == 429:
        log.warning("rate limited on live event=%s, sleeping 60s", event_id)
        time.sleep(60)
        return None, "error"
    if resp.status_code != 200:
        log.warning(
            "unexpected status %s for live event=%s: %s",
            resp.status_code, event_id, resp.text[:200],
        )
        return None, "error"

    try:
        payload = resp.json()
    except ValueError as exc:
        log.warning("JSON parse error for live event=%s: %s", event_id, exc)
        return None, "error"

    payload["_x_requests_remaining"] = int(remaining) if remaining else None
    payload["_x_requests_last"] = int(last) if last else None
    return payload, "success"


# ── Subcommand: fetch ─────────────────────────────────────────────────────────

def cmd_fetch(args: argparse.Namespace) -> None:
    api_key = os.environ["ODDS_API_KEY"]
    markets = args.markets
    regions = args.regions
    start_date = args.start_date
    end_date = args.end_date
    target_fqn = _target_fqn()

    log.info(
        "E2.0 fetch  start=%s  end=%s  markets=%s  regions=%s  dry_run=%s",
        start_date, end_date, markets, regions, args.dry_run,
    )

    # ── Step 1: brief Snowflake query to discover events ──────────────────────
    log.info("connecting to Snowflake for event discovery ...")
    conn = connect_snowflake()
    events = fetch_events_to_backfill(conn, target_fqn, start_date, end_date, args.limit)
    conn.close()
    log.info("Snowflake connection closed — %d events to fetch", len(events))

    if args.dry_run:
        for ev in events[:20]:
            log.info("  dry-run: event_id=%s  %s vs %s  %s",
                     ev["event_id"], ev["away_team"], ev["home_team"], ev["commence_time"])
        if len(events) > 20:
            log.info("  ... and %d more", len(events) - 20)
        return

    if not events:
        log.info("no new events to fetch — nothing to do")
        return

    cost_per_event = 10 * len(markets) * len(regions)
    log.info("estimated credits: %d × %d = ~%d", len(events), cost_per_event, len(events) * cost_per_event)

    # ── Step 2: API fetch loop (Snowflake disconnected) ───────────────────────
    load_id = str(uuid.uuid4())
    ingestion_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []      # all rows including sentinels
    success_count = 0
    total_credits_used = 0

    for i, event in enumerate(events, 1):
        event_id = event["event_id"]
        commence_ts = event["commence_time"]
        snapshot_ts = commence_ts.replace(tzinfo=timezone.utc) if commence_ts.tzinfo is None else commence_ts
        requested_ts_str = snapshot_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        payload, status = fetch_event_derivative_odds(event_id, snapshot_ts, markets, regions, api_key)
        time.sleep(REQUEST_DELAY_SECONDS)

        if status != "success":
            # Write a sentinel row so future runs skip this event (idempotency)
            # and we have an audit trail of the attempt.
            rows.append({
                "ingestion_ts":              ingestion_ts,
                "load_id":                   load_id,
                "event_id":                  event_id,
                "requested_snapshot_ts":     requested_ts_str,
                "actual_snapshot_ts":        None,
                "previous_snapshot_ts":      None,
                "next_snapshot_ts":          None,
                "markets_requested":         ",".join(markets),
                "regions_requested":         ",".join(regions),
                "x_requests_remaining":      None,
                "x_requests_last":           None,
                "raw_json":                  None,
                "fetch_status":              status,
            })
            continue

        actual_ts   = payload.get("timestamp", "")
        previous_ts = payload.get("previous_timestamp", "")
        next_ts     = payload.get("next_timestamp", "")
        data_obj    = payload.get("data")
        x_remaining = payload.get("_x_requests_remaining")
        x_last      = payload.get("_x_requests_last")

        if not data_obj or not data_obj.get("bookmakers"):
            log.debug("no bookmaker data for event=%s at %s", event_id, actual_ts)
            rows.append({
                "ingestion_ts":              ingestion_ts,
                "load_id":                   load_id,
                "event_id":                  event_id,
                "requested_snapshot_ts":     requested_ts_str,
                "actual_snapshot_ts":        actual_ts,
                "previous_snapshot_ts":      previous_ts,
                "next_snapshot_ts":          next_ts,
                "markets_requested":         ",".join(markets),
                "regions_requested":         ",".join(regions),
                "x_requests_remaining":      str(x_remaining) if x_remaining is not None else None,
                "x_requests_last":           str(x_last) if x_last is not None else None,
                "raw_json":                  None,
                "fetch_status":              "no_data",
            })
            continue

        if x_last:
            total_credits_used += x_last

        rows.append({
            "ingestion_ts":              ingestion_ts,
            "load_id":                   load_id,
            "event_id":                  event_id,
            "requested_snapshot_ts":     requested_ts_str,
            "actual_snapshot_ts":        actual_ts,
            "previous_snapshot_ts":      previous_ts,
            "next_snapshot_ts":          next_ts,
            "markets_requested":         ",".join(markets),
            "regions_requested":         ",".join(regions),
            "x_requests_remaining":      str(x_remaining) if x_remaining is not None else None,
            "x_requests_last":           str(x_last) if x_last is not None else None,
            "raw_json":                  json.dumps(data_obj),
            "fetch_status":              "success",
        })
        success_count += 1

        if i % 100 == 0:
            log.info(
                "progress: %d/%d events  rows_collected=%d  credits_used=%d  x_remaining=%s",
                i, len(events), success_count, total_credits_used, x_remaining,
            )

    not_found = sum(1 for r in rows if r.get("fetch_status") == "not_found")
    no_data   = sum(1 for r in rows if r.get("fetch_status") == "no_data")
    errors    = sum(1 for r in rows if r.get("fetch_status") == "error")
    log.info(
        "fetch complete: %d/%d success  not_found=%d  no_data=%d  errors=%d  total_credits=%d",
        success_count, len(events), not_found, no_data, errors, total_credits_used,
    )

    if success_count == 0 and not rows:
        log.warning("no rows to write — check API key tier or date range")
        return

    # ── Step 3: write Parquet ─────────────────────────────────────────────────
    write_parquet(rows, args.output)
    log.info("DONE — run ingest next:  uv run python scripts/derivative_odds_backfill.py ingest --file %s", args.output)


# ── Subcommand: ingest ────────────────────────────────────────────────────────

def cmd_ingest(args: argparse.Namespace) -> None:
    parquet_path = Path(args.file)
    if not parquet_path.exists():
        log.error("parquet file not found: %s", parquet_path)
        raise SystemExit(1)

    target_fqn = _target_fqn()
    staging_fqn = _staging_fqn()
    staging_stage = _staging_stage()

    log.info("E2.0 ingest  file=%s → %s", parquet_path, target_fqn)

    conn = connect_snowflake()
    try:
        inserted = bulk_load_parquet(conn, parquet_path, target_fqn, staging_fqn, staging_stage)
        log.info("DONE — %d rows inserted into %s", inserted, target_fqn)
        log.info("next step: dbtf build --select stg_derivative_odds mart_derivative_closes")
    finally:
        conn.close()


# ── Subcommand: probe ─────────────────────────────────────────────────────────

def cmd_probe(args: argparse.Namespace) -> None:
    """E2.0b Step 0: probe the Event Markets endpoint for derivative market availability.

    Queries a sample of upcoming events to answer:
      (a) Are derivative markets (esp. F5 h2h_1st_5_innings/totals_1st_5_innings) offered live right now?
      (b) What is the per-market last_update cadence → what cron schedule to use?

    No writes. Run this before deploying the capture cron to size the cadence correctly.
    """
    api_key = os.environ["ODDS_API_KEY"]
    log.info("=== E2.0b PROBE: checking derivative market availability ===")

    events = fetch_upcoming_events(api_key, lookahead_hours=args.lookahead_hours)
    if not events:
        log.warning(
            "No upcoming MLB events in next %dh — probe can't run on a non-game window",
            args.lookahead_hours,
        )
        log.warning("Try again closer to a game day, or increase --lookahead-hours")
        return

    sample = events[:args.sample]
    log.info(
        "Found %d upcoming events (lookahead=%dh); sampling %d",
        len(events), args.lookahead_hours, len(sample),
    )

    # {bm_key -> set of market_keys offered across sampled events}
    market_coverage: dict[str, set[str]] = {}
    # {bm_key -> {mkt_key -> most-recent last_update str}}
    last_updates: dict[str, dict[str, str]] = {}

    for ev in sample:
        event_id = ev["id"]
        label = (
            f"{ev.get('away_team','?')} @ {ev.get('home_team','?')} "
            f"({ev.get('commence_time','')})"
        )
        log.info("  probing markets: %s", label)
        bookmakers_data = probe_event_markets(event_id, api_key, args.bookmakers)
        time.sleep(0.3)

        for bm in bookmakers_data:
            bm_key = bm.get("key", "unknown")
            for mkt in bm.get("markets", []):
                mkt_key = mkt.get("key", "")
                if not mkt_key:
                    continue
                market_coverage.setdefault(bm_key, set()).add(mkt_key)
                lu = mkt.get("last_update", "")
                if lu:
                    existing = last_updates.get(bm_key, {}).get(mkt_key, "")
                    if lu > existing:
                        last_updates.setdefault(bm_key, {})[mkt_key] = lu

    if not market_coverage:
        log.warning("No market data returned — check ODDS_API_KEY or bookmakers list")
        return

    target = DEFAULT_DERIVATIVE_MARKETS
    now_utc = datetime.now(timezone.utc)

    log.info("")
    log.info("=== E2.0b PROBE REPORT ===")
    log.info(
        "Sample: %d of %d upcoming events | Lookahead: %dh",
        len(sample), len(events), args.lookahead_hours,
    )
    log.info("")
    log.info("Market availability by bookmaker (mark = offered in >=1 sampled game):")
    for bm_key in sorted(market_coverage):
        offered = market_coverage[bm_key]
        flags = "  ".join(f"{m} {'YES' if m in offered else 'NO'}" for m in target)
        log.info("  %-16s %s", bm_key + ":", flags)

    log.info("")

    # Correct baseball F5 keys (NOT h2h_h1/totals_h1 which are the generic 1st-Half family).
    f5_markets = ("h2h_1st_5_innings", "totals_1st_5_innings", "totals_1st_1_innings")
    f5_books = sorted(
        bm for bm, mkts in market_coverage.items() if any(m in mkts for m in f5_markets)
    )
    if f5_books:
        log.info(
            "F5 (h2h_1st_5_innings / totals_1st_5_innings / totals_1st_1_innings): OFFERED by %s",
            ", ".join(f5_books),
        )
        log.info(
            "  ACTION: keep correct keys in DERIVATIVE_CAPTURE_MARKETS "
            "(team_totals,alternate_totals,h2h_1st_5_innings,totals_1st_5_innings,totals_1st_1_innings)"
        )
    else:
        log.info(
            "F5 (h2h_1st_5_innings / totals_1st_5_innings / totals_1st_1_innings): "
            "NOT OFFERED by any sampled bookmaker"
        )
        log.info(
            "  ACTION: set DERIVATIVE_CAPTURE_MARKETS=team_totals,alternate_totals in Railway env"
        )
        log.info(
            "  NOTE: correct keys are *_1st_5_innings — not offered LIVE at this source as of today"
        )

    log.info("")
    log.info("Last-update cadence (most recent last_update across sampled events):")
    cadence_ages: list[float] = []
    for bm_key in sorted(last_updates):
        for mkt_key in target:
            lu_str = last_updates.get(bm_key, {}).get(mkt_key)
            if lu_str:
                try:
                    lu_dt = datetime.fromisoformat(lu_str.replace("Z", "+00:00"))
                    age_h = (now_utc - lu_dt).total_seconds() / 3600
                    cadence_ages.append(age_h)
                    log.info(
                        "  %-16s %-22s last_update=%s (%.1fh ago)",
                        bm_key, mkt_key, lu_str, age_h,
                    )
                except Exception:
                    log.info("  %-16s %-22s last_update=%s", bm_key, mkt_key, lu_str)

    log.info("")
    if cadence_ages:
        median_age = sorted(cadence_ages)[len(cadence_ages) // 2]
        if median_age < 1:
            cron_rec = "*/30 * * * *  (every 30 min)"
        elif median_age < 3:
            cron_rec = "0 * * * *    (every 1h)"
        else:
            cron_rec = "0 */4 * * *  (every 4h)"
        log.info(
            "Observed median cadence: ~%.1fh -> recommended cronSchedule: %s",
            median_age, cron_rec,
        )

    log.info("")
    log.info("NEXT STEPS:")
    log.info("  1. Set DERIVATIVE_CAPTURE_MARKETS in Railway service env (see F5 verdict above)")
    log.info("  2. Update cronSchedule in services/derivative_capture/railway.toml")
    log.info("  3. Deploy: services/derivative_capture/ Railway cron service")
    log.info("  4. After first captures land: dbtf build --select stg_derivative_odds mart_derivative_closes")


# ── Subcommand: capture ───────────────────────────────────────────────────────

def cmd_capture(args: argparse.Namespace) -> None:
    """E2.0b live forward capture — fetch derivative odds for upcoming MLB games.

    Called by the Railway derivative_capture cron (services/derivative_capture/).
    Each invocation:
      1. Gets upcoming events from the live Odds API events endpoint.
      2. Fetches derivative odds for games starting within --lookahead-hours.
      3. Writes rows to derivative_odds_raw (same schema as historical backfill).
      4. mart_derivative_closes picks up the last pre-game snapshot on next dbtf build.

    Multiple snapshots per game are intentional — the cron fires repeatedly during the
    day; mart_derivative_closes's ROW_NUMBER keeps only the last pre-game snapshot.

    EVAL/CLV-ONLY — derivative odds must NEVER be model training features.
    """
    api_key = os.environ["ODDS_API_KEY"]

    # Support DERIVATIVE_CAPTURE_MARKETS env var for Railway configuration (set after probe)
    env_markets = [
        m.strip()
        for m in os.environ.get("DERIVATIVE_CAPTURE_MARKETS", "").split(",")
        if m.strip()
    ]
    markets = env_markets if env_markets else args.markets
    regions = args.regions

    log.info(
        "E2.0b capture  markets=%s  regions=%s  lookahead=%dh  dry_run=%s",
        markets, regions, args.lookahead_hours, args.dry_run,
    )

    # 1. Get upcoming events from live API (1 credit)
    now = datetime.now(timezone.utc)
    events = fetch_upcoming_events(api_key, lookahead_hours=args.lookahead_hours)

    if not events:
        log.info("No upcoming MLB events in next %dh — nothing to capture", args.lookahead_hours)
        return

    # Skip games already started (10-min grace window)
    upcoming = []
    for ev in events:
        try:
            ct = datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            if ct > now - timedelta(minutes=10):
                upcoming.append(ev)
        except Exception as exc:
            log.warning("skipping event %s — bad commence_time: %s", ev.get("id"), exc)

    if not upcoming:
        log.info("No pre-start games in the capture window — nothing to capture")
        return

    log.info(
        "Capturing %d of %d events (pre-start, within next %dh)",
        len(upcoming), len(events), args.lookahead_hours,
    )

    if args.dry_run:
        for ev in upcoming:
            log.info(
                "  dry-run: event_id=%s  %s @ %s  %s",
                ev["id"], ev.get("away_team", "?"), ev.get("home_team", "?"), ev["commence_time"],
            )
        return

    cost_per_event = len(markets) * len(regions)
    log.info(
        "estimated credits: %d events x %d markets x %d regions = ~%d",
        len(upcoming), len(markets), len(regions), len(upcoming) * cost_per_event,
    )

    # 2. Fetch live derivative odds
    load_id = str(uuid.uuid4())
    ingestion_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict] = []
    success_count = 0
    total_credits = 0
    x_remaining = None

    for ev in upcoming:
        event_id = ev["id"]
        payload, status = fetch_live_event_derivative_odds(event_id, markets, regions, api_key)
        time.sleep(REQUEST_DELAY_SECONDS)

        x_remaining = (payload or {}).get("_x_requests_remaining")
        x_last = (payload or {}).get("_x_requests_last")

        base_row: dict = {
            "ingestion_ts":          ingestion_ts,
            "load_id":               load_id,
            "event_id":              event_id,
            "requested_snapshot_ts": ingestion_ts,
            "actual_snapshot_ts":    ingestion_ts,  # live snapshot timestamp = request time
            "previous_snapshot_ts":  None,
            "next_snapshot_ts":      None,
            "markets_requested":     ",".join(markets),
            "regions_requested":     ",".join(regions),
            "x_requests_remaining":  str(x_remaining) if x_remaining is not None else None,
            "x_requests_last":       str(x_last) if x_last is not None else None,
            "raw_json":              None,
            "fetch_status":          status,
        }

        if status != "success" or not payload:
            rows.append(base_row)
            continue

        # Live endpoint returns the event object directly (no timestamp wrapper);
        # strip internal bookkeeping keys before storing.
        data_obj = {k: v for k, v in payload.items() if not k.startswith("_")}

        if not data_obj.get("bookmakers"):
            rows.append({**base_row, "fetch_status": "no_data"})
            continue

        if x_last:
            total_credits += x_last

        rows.append({**base_row, "raw_json": json.dumps(data_obj)})
        success_count += 1

    non_success = sum(1 for r in rows if r.get("fetch_status") != "success")
    log.info(
        "capture complete: %d/%d success  non_success=%d  credits_used=%d  x_remaining=%s",
        success_count, len(upcoming), non_success, total_credits, x_remaining,
    )

    if not rows:
        log.info("no rows to write")
        return

    # 3. Write — E11.1-W11-E gated dual-write (W11_RAW_WRITE_MODE, default 'snowflake' = unchanged).
    #    SF leg = the two-phase Parquet→Snowflake bulk load; S3 leg = append the same rows to
    #    lakehouse_raw/derivative_odds_raw/ (retires the daily export bridge once mode='s3').
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

    if do_sf:
        ts_str = now.strftime("%Y%m%d_%H%M%S")
        output_path = args.output or Path(f"/tmp/deriv_live_{ts_str}.parquet")
        write_parquet(rows, output_path)

        conn = connect_snowflake()
        try:
            inserted = bulk_load_parquet(
                conn, output_path, _target_fqn(), _staging_fqn(), _staging_stage(),
            )
            log.info("DONE — %d rows inserted into %s", inserted, _target_fqn())
            if args.output is None:
                try:
                    output_path.unlink()
                    log.debug("cleaned up %s", output_path)
                except Exception:
                    pass
        finally:
            conn.close()

    if do_s3:
        mirror_rows = _derivative_mirror_rows(rows)
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append") if mirror_rows else 0
        log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)


# ── CLI ────────────────────────────────────────────────────────────────────────

def _default_output(start: date, end: date) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"data/derivative_odds_{start.isoformat()}_{end.isoformat()}_{ts}.parquet")


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2.0 derivative odds historical backfill — two-phase fetch+ingest (EVAL/CLV only)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── fetch ──────────────────────────────────────────────────────────────────
    fetch_p = sub.add_parser("fetch", help="Fetch derivative odds from API → local Parquet")
    fetch_p.add_argument("--start-date", type=parse_date, default=DERIVATIVE_HISTORY_START,
                         help=f"First game date (default: {DERIVATIVE_HISTORY_START})")
    fetch_p.add_argument("--end-date", type=parse_date, default=date.today(),
                         help="Last game date inclusive (default: today)")
    fetch_p.add_argument("--markets", nargs="+", default=DEFAULT_DERIVATIVE_MARKETS,
                         help=f"Odds API market keys (default: {DEFAULT_DERIVATIVE_MARKETS})")
    fetch_p.add_argument("--regions", nargs="+", default=DEFAULT_REGIONS,
                         help=f"Odds API regions (default: {DEFAULT_REGIONS})")
    fetch_p.add_argument("--limit", type=int, default=None,
                         help="Cap events processed (for testing)")
    fetch_p.add_argument("--output", type=Path, default=None,
                         help="Parquet output path (default: data/derivative_odds_<dates>_<ts>.parquet)")
    fetch_p.add_argument("--dry-run", action="store_true",
                         help="List events without calling API or writing files")

    # ── ingest ─────────────────────────────────────────────────────────────────
    ingest_p = sub.add_parser("ingest", help="Load a Parquet file into Snowflake (one bulk write)")
    ingest_p.add_argument("--file", required=True, help="Path to the Parquet file from 'fetch'")

    # ── probe (E2.0b) ──────────────────────────────────────────────────────────
    probe_p = sub.add_parser(
        "probe",
        help="E2.0b: probe Event Markets endpoint for derivative market availability (no writes)",
    )
    probe_p.add_argument(
        "--bookmakers", nargs="+", default=PROBE_BOOKMAKERS,
        help=f"Bookmakers to probe (default: {PROBE_BOOKMAKERS})",
    )
    probe_p.add_argument(
        "--sample", type=int, default=5,
        help="Number of upcoming events to probe (default: 5)",
    )
    probe_p.add_argument(
        "--lookahead-hours", type=int, default=24,
        help="Hours ahead to search for upcoming events (default: 24)",
    )

    # ── capture (E2.0b) ────────────────────────────────────────────────────────
    capture_p = sub.add_parser(
        "capture",
        help="E2.0b: live forward capture for upcoming games (Railway cron subcommand)",
    )
    capture_p.add_argument(
        "--markets", nargs="+", default=DEFAULT_DERIVATIVE_MARKETS,
        help=(
            f"Derivative markets to capture (default: {DEFAULT_DERIVATIVE_MARKETS}); "
            "override at runtime via DERIVATIVE_CAPTURE_MARKETS env var"
        ),
    )
    capture_p.add_argument(
        "--regions", nargs="+", default=DEFAULT_REGIONS,
        help=f"Odds API regions (default: {DEFAULT_REGIONS})",
    )
    capture_p.add_argument(
        "--lookahead-hours", type=int, default=12,
        help="Capture games starting within the next N hours (default: 12)",
    )
    capture_p.add_argument(
        "--output", type=Path, default=None,
        help="Parquet path for testing (default: auto /tmp/deriv_live_<ts>.parquet, deleted after ingest)",
    )
    capture_p.add_argument(
        "--dry-run", action="store_true",
        help="List upcoming games without calling the odds endpoint",
    )

    args = parser.parse_args()

    if args.command == "fetch":
        if args.start_date < DERIVATIVE_HISTORY_START:
            log.warning("start-date %s before API limit %s; clamping", args.start_date, DERIVATIVE_HISTORY_START)
            args.start_date = DERIVATIVE_HISTORY_START
        if args.output is None:
            args.output = _default_output(args.start_date, args.end_date)
        cmd_fetch(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "probe":
        cmd_probe(args)
    elif args.command == "capture":
        cmd_capture(args)


if __name__ == "__main__":
    main()
