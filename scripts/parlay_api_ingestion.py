"""
parlay_api_ingestion.py
-----------------------
Ingests MLB data from the Parlay API into Snowflake. Six subcommands:

  events              — Calls /v1/sports/baseball_mlb/events and inserts the
                        full response array as a single row in the events table.

  odds                — Calls /v1/sports/baseball_mlb/odds for each market/region
                        combination and inserts each event's odds as its own row.

  historical-odds     — Fetches historical odds for each calendar day in a date
                        range via /v1/historical/sports/baseball_mlb/odds. One
                        call per (date, market); one row per event per call.
                        Idempotent: (game_date, market) pairs already in target
                        are skipped unless --force is passed.

  historical-matches  — Fetches historical match results + ML odds via
                        /v1/historical/sports/baseball_mlb/matches. One call per
                        calendar date; stores the full response array as a single
                        row in mlb_matches_raw. Useful for game results backfill
                        and has_odds auditing.

  line-movement       — Fetches intraday price history for a set of event IDs via
                        /v1/sports/baseball_mlb/line-movement. One call per
                        event_id; stores the full (event × source × market)
                        snapshots array as VARIANT in mlb_line_movement_raw.
                        Event IDs are auto-resolved from mlb_events_raw
                        (today + tomorrow) or accepted explicitly via --event-ids.

  events-canonical    — Calls /v1/sports/baseball_mlb/events/canonical and inserts
                        the full response array as a single row in
                        mlb_canonical_events_raw. This is the ONLY endpoint that
                        returns real per-game start times; all other live endpoints
                        return 19:00:00Z as a placeholder. Used by
                        stg_parlayapi_canonical_events to supply accurate
                        commence_time for leakage guards in mart models.
                        Auth note: uses apiKey query param — X-API-Key header is
                        rejected on this endpoint.

Key differences from odds_api_ingestion.py:
  • Single key only — PARLAY_API_KEY; no starter-key fallback.
  • Header auth — X-API-Key header (not ?apiKey= query param).
  • No credit counter headers — Parlay API does not return x-requests-used/
    remaining. Call sequence is tracked via an in-script counter instead.
  • Historical endpoint uses date=YYYY-MM-DD (single date) — not commenceTimeFrom/
    commenceTimeTo. Iterates calendar days; no game-start-time query needed.
  • Four target tables instead of two (adds mlb_matches_raw, mlb_line_movement_raw).
  • canonical_event_id extracted from events and odds responses (new field).

Loading is append-only. No rows are updated or deleted. Every run produces a
new set of rows tagged with a shared load_id.

Target tables are resolved from env vars, falling back to production defaults:

    PARLAY_TARGET_DATABASE         (default: baseball_data)
    PARLAY_TARGET_SCHEMA           (default: parlayapi)
    PARLAY_EVENTS_TABLE            (default: mlb_events_raw)
    PARLAY_ODDS_TABLE              (default: mlb_odds_raw)
    PARLAY_MATCHES_TABLE           (default: mlb_matches_raw)
    PARLAY_LINE_MOVEMENT_TABLE     (default: mlb_line_movement_raw)
    PARLAY_CANONICAL_EVENTS_TABLE  (default: mlb_canonical_events_raw)

Snowflake authentication — private key (preferred) or password fallback:
    SNOWFLAKE_ACCOUNT
    SNOWFLAKE_USER
    SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH      path to .p8 / PEM private key file
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  (optional)
    SNOWFLAKE_ROLE                  (optional)

    Parlay API:
    PARLAY_API_KEY

Usage:
    uv run parlay_api_ingestion.py events
    uv run parlay_api_ingestion.py odds
    uv run parlay_api_ingestion.py odds --markets h2h totals --regions us us2

    # Historical odds backfill — defaults to 90 days prior to run date
    uv run parlay_api_ingestion.py historical-odds
    uv run parlay_api_ingestion.py historical-odds --start-date 2026-02-08 --end-date 2026-05-08

    # Historical matches backfill (game results + ML odds + has_odds)
    uv run parlay_api_ingestion.py historical-matches
    uv run parlay_api_ingestion.py historical-matches --start-date 2026-02-08 --end-date 2026-05-08

    # Line-movement — auto-resolves today's event IDs from mlb_events_raw
    uv run parlay_api_ingestion.py line-movement
    # Or pass specific event IDs
    uv run parlay_api_ingestion.py line-movement --event-ids id1 id2 id3

    # Canonical events — real per-game start times (apiKey query param auth)
    uv run parlay_api_ingestion.py events-canonical
"""

import argparse
import dataclasses
import json
import logging
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from date_utils import default_window, format_iso_utc

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

# ── Constants ──────────────────────────────────────────────────────────────────

PARLAY_BASE_URL              = "https://parlay-api.com/v1"
EVENTS_ENDPOINT              = "/sports/baseball_mlb/events"
CANONICAL_EVENTS_ENDPOINT    = "/sports/baseball_mlb/events/canonical"
ODDS_ENDPOINT                = "/sports/baseball_mlb/odds"
HIST_ODDS_ENDPOINT           = "/historical/sports/baseball_mlb/odds"
HIST_MATCHES_ENDPOINT        = "/historical/sports/baseball_mlb/matches"
LINE_MOVEMENT_ENDPOINT       = "/sports/baseball_mlb/line-movement"

SOURCE_SYSTEM = "parlay_api"
PROCESS_NAME  = "parlay_api_ingestion.py"

_DEFAULT_DATABASE                   = "baseball_data"
_DEFAULT_SCHEMA                     = "parlayapi"
_DEFAULT_EVENTS_TABLE               = "mlb_events_raw"
_DEFAULT_ODDS_TABLE                 = "mlb_odds_raw"
_DEFAULT_MATCHES_TABLE              = "mlb_matches_raw"
_DEFAULT_LINE_MOVEMENT_TABLE        = "mlb_line_movement_raw"
_DEFAULT_CANONICAL_EVENTS_TABLE     = "mlb_canonical_events_raw"

DEFAULT_MARKETS     = ["h2h", "totals"]
DEFAULT_REGIONS     = ["us", "us2"]
DEFAULT_ODDS_FORMAT = "american"
DEFAULT_DATE_FORMAT = "iso"

# Default look-ahead window for the events endpoint (days)
DEFAULT_EVENTS_WINDOW_DAYS = 7

# Historical backfill default: 90 days prior to run date (Business plan limit)
HIST_BACKFILL_DAYS = 90

# Line-movement: look-ahead window for auto event ID resolution
LINE_MOVEMENT_LOOKAHEAD_DAYS = 2

# Polite delay between API calls (seconds)
REQUEST_DELAY = 0.5


# ── Target resolution ─────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class SnowflakeTarget:
    database: str
    schema: str
    table: str

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"


@dataclasses.dataclass(frozen=True)
class Targets:
    events: SnowflakeTarget
    odds: SnowflakeTarget
    matches: SnowflakeTarget
    line_movement: SnowflakeTarget
    canonical_events: SnowflakeTarget


def resolve_targets() -> Targets:
    database = os.environ.get("PARLAY_TARGET_DATABASE", _DEFAULT_DATABASE)
    schema   = os.environ.get("PARLAY_TARGET_SCHEMA",   _DEFAULT_SCHEMA)
    return Targets(
        events = SnowflakeTarget(
            database, schema,
            os.environ.get("PARLAY_EVENTS_TABLE", _DEFAULT_EVENTS_TABLE),
        ),
        odds = SnowflakeTarget(
            database, schema,
            os.environ.get("PARLAY_ODDS_TABLE", _DEFAULT_ODDS_TABLE),
        ),
        matches = SnowflakeTarget(
            database, schema,
            os.environ.get("PARLAY_MATCHES_TABLE", _DEFAULT_MATCHES_TABLE),
        ),
        line_movement = SnowflakeTarget(
            database, schema,
            os.environ.get("PARLAY_LINE_MOVEMENT_TABLE", _DEFAULT_LINE_MOVEMENT_TABLE),
        ),
        canonical_events = SnowflakeTarget(
            database, schema,
            os.environ.get("PARLAY_CANONICAL_EVENTS_TABLE", _DEFAULT_CANONICAL_EVENTS_TABLE),
        ),
    )


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


def get_snowflake_connection(
    database: str, schema: str
) -> snowflake.connector.SnowflakeConnection:
    required_base = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required_base if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  database,
        "schema":    schema,
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        log.info("Authenticating with private key: %s", private_key_path)
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(private_key_path, passphrase)
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


# ── Parlay API request layer ───────────────────────────────────────────────────

class ParlayApiResponse:
    """Wraps a raw requests.Response for a Parlay API call."""

    def __init__(self, response: requests.Response) -> None:
        self._response      = response
        self.status_code: int = response.status_code
        self.url: str         = response.url
        self.payload: Any     = response.json()
        # Parlay API does not return x-requests-used/remaining headers.
        # x-request-id is available for tracing.
        self.request_id: str | None = response.headers.get("x-request-id")

    def log_request_id(self) -> None:
        if self.request_id:
            log.debug("  x-request-id: %s", self.request_id)


def _get_api_key() -> str:
    key = os.environ.get("PARLAY_API_KEY")
    if not key:
        raise EnvironmentError("PARLAY_API_KEY is not set in the environment or .env file.")
    return key


def call_parlay_api(endpoint: str, params: dict) -> ParlayApiResponse:
    """
    Make a GET request to the given Parlay API endpoint path with the provided
    query parameters. Auth is via the X-API-Key header (single key only).
    """
    url     = f"{PARLAY_BASE_URL}{endpoint}"
    api_key = _get_api_key()

    log.info("GET %s  params=%s", url, params)

    response = requests.get(
        url,
        headers={"X-API-Key": api_key},
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    result = ParlayApiResponse(response)
    result.log_request_id()
    return result


def call_parlay_api_query_auth(endpoint: str, params: dict) -> ParlayApiResponse:
    """
    Make a GET request using apiKey as a query parameter instead of the X-API-Key
    header. Required for /events/canonical, which rejects the header auth method.
    The API key is NOT logged.
    """
    url     = f"{PARLAY_BASE_URL}{endpoint}"
    api_key = _get_api_key()

    log.info("GET %s  params=%s  (apiKey query auth)", url, params)

    response = requests.get(
        url,
        params={**params, "apiKey": api_key},
        timeout=30,
    )
    response.raise_for_status()

    result = ParlayApiResponse(response)
    result.log_request_id()
    return result


# ── Snowflake write helpers ────────────────────────────────────────────────────

def insert_event_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    call_sequence: int,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    raw_json: Any,
    event_id: str | None,
    canonical_event_id: str | None,
    sport_key: str | None,
    sport_title: str | None,
    commence_time: str | None,
    home_team: str | None,
    away_team: str | None,
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id, call_sequence,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code, x_requests_used, x_requests_remaining,
            raw_json,
            event_id, canonical_event_id,
            sport_key, sport_title, commence_time, home_team, away_team
        )
        SELECT
            %(ingestion_ts)s::timestamp_ntz,
            %(load_id)s,
            %(call_sequence)s,
            %(source_system)s,
            %(process_name)s,
            %(source_endpoint)s,
            %(request_url)s,
            PARSE_JSON(%(request_params)s),
            %(http_status_code)s,
            NULL,
            NULL,
            PARSE_JSON(%(raw_json)s),
            %(event_id)s,
            %(canonical_event_id)s,
            %(sport_key)s,
            %(sport_title)s,
            %(commence_time)s::timestamp_ntz,
            %(home_team)s,
            %(away_team)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":        ingestion_ts.isoformat(),
            "load_id":             load_id,
            "call_sequence":       call_sequence,
            "source_system":       SOURCE_SYSTEM,
            "process_name":        PROCESS_NAME,
            "source_endpoint":     source_endpoint,
            "request_url":         request_url,
            "request_params":      json.dumps(request_params),
            "http_status_code":    http_status_code,
            "raw_json":            json.dumps(raw_json),
            "event_id":            event_id,
            "canonical_event_id":  canonical_event_id,
            "sport_key":           sport_key,
            "sport_title":         sport_title,
            "commence_time":       commence_time,
            "home_team":           home_team,
            "away_team":           away_team,
        })


def insert_odds_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    call_sequence: int,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    raw_json: Any,
    event_id: str | None,
    canonical_event_id: str | None,
    sport_key: str | None,
    sport_title: str | None,
    commence_time: str | None,
    home_team: str | None,
    away_team: str | None,
    bookmakers_count: int | None,
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id, call_sequence,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code, x_requests_used, x_requests_remaining,
            raw_json,
            event_id, canonical_event_id,
            sport_key, sport_title, commence_time, home_team, away_team,
            bookmakers_count
        )
        SELECT
            %(ingestion_ts)s::timestamp_ntz,
            %(load_id)s,
            %(call_sequence)s,
            %(source_system)s,
            %(process_name)s,
            %(source_endpoint)s,
            %(request_url)s,
            PARSE_JSON(%(request_params)s),
            %(http_status_code)s,
            NULL,
            NULL,
            PARSE_JSON(%(raw_json)s),
            %(event_id)s,
            %(canonical_event_id)s,
            %(sport_key)s,
            %(sport_title)s,
            %(commence_time)s::timestamp_ntz,
            %(home_team)s,
            %(away_team)s,
            %(bookmakers_count)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":        ingestion_ts.isoformat(),
            "load_id":             load_id,
            "call_sequence":       call_sequence,
            "source_system":       SOURCE_SYSTEM,
            "process_name":        PROCESS_NAME,
            "source_endpoint":     source_endpoint,
            "request_url":         request_url,
            "request_params":      json.dumps(request_params),
            "http_status_code":    http_status_code,
            "raw_json":            json.dumps(raw_json),
            "event_id":            event_id,
            "canonical_event_id":  canonical_event_id,
            "sport_key":           sport_key,
            "sport_title":         sport_title,
            "commence_time":       commence_time,
            "home_team":           home_team,
            "away_team":           away_team,
            "bookmakers_count":    bookmakers_count,
        })


def insert_matches_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    call_sequence: int,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    raw_json: Any,
    game_date: date | None,
    sport_key: str | None,
    season: str | None,
    record_count: int,
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id, call_sequence,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code,
            raw_json,
            game_date, sport_key, season, record_count
        )
        SELECT
            %(ingestion_ts)s::timestamp_ntz,
            %(load_id)s,
            %(call_sequence)s,
            %(source_system)s,
            %(process_name)s,
            %(source_endpoint)s,
            %(request_url)s,
            PARSE_JSON(%(request_params)s),
            %(http_status_code)s,
            PARSE_JSON(%(raw_json)s),
            %(game_date)s::date,
            %(sport_key)s,
            %(season)s,
            %(record_count)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":     ingestion_ts.isoformat(),
            "load_id":          load_id,
            "call_sequence":    call_sequence,
            "source_system":    SOURCE_SYSTEM,
            "process_name":     PROCESS_NAME,
            "source_endpoint":  source_endpoint,
            "request_url":      request_url,
            "request_params":   json.dumps(request_params),
            "http_status_code": http_status_code,
            "raw_json":         json.dumps(raw_json),
            "game_date":        game_date.isoformat() if game_date else None,
            "sport_key":        sport_key,
            "season":           season,
            "record_count":     record_count,
        })


def insert_line_movement_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    call_sequence: int,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    raw_json: Any,
    event_id: str | None,
    home_team: str | None,
    away_team: str | None,
    record_count: int,
    markets_captured: list[str],
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id, call_sequence,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code,
            raw_json,
            event_id, home_team, away_team,
            record_count, markets_captured
        )
        SELECT
            %(ingestion_ts)s::timestamp_ntz,
            %(load_id)s,
            %(call_sequence)s,
            %(source_system)s,
            %(process_name)s,
            %(source_endpoint)s,
            %(request_url)s,
            PARSE_JSON(%(request_params)s),
            %(http_status_code)s,
            PARSE_JSON(%(raw_json)s),
            %(event_id)s,
            %(home_team)s,
            %(away_team)s,
            %(record_count)s,
            PARSE_JSON(%(markets_captured)s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":     ingestion_ts.isoformat(),
            "load_id":          load_id,
            "call_sequence":    call_sequence,
            "source_system":    SOURCE_SYSTEM,
            "process_name":     PROCESS_NAME,
            "source_endpoint":  source_endpoint,
            "request_url":      request_url,
            "request_params":   json.dumps(request_params),
            "http_status_code": http_status_code,
            "raw_json":         json.dumps(raw_json),
            "event_id":         event_id,
            "home_team":        home_team,
            "away_team":        away_team,
            "record_count":     record_count,
            "markets_captured": json.dumps(sorted(set(markets_captured))),
        })


def insert_canonical_events_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    call_sequence: int,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    raw_json: Any,
    sport_key: str | None,
    event_count: int,
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code, call_sequence,
            raw_json,
            sport_key, event_count
        )
        SELECT
            %(ingestion_ts)s::timestamp_ntz,
            %(load_id)s,
            %(source_system)s,
            %(process_name)s,
            %(source_endpoint)s,
            %(request_url)s,
            PARSE_JSON(%(request_params)s),
            %(http_status_code)s,
            %(call_sequence)s,
            PARSE_JSON(%(raw_json)s),
            %(sport_key)s,
            %(event_count)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":     ingestion_ts.isoformat(),
            "load_id":          load_id,
            "source_system":    SOURCE_SYSTEM,
            "process_name":     PROCESS_NAME,
            "source_endpoint":  source_endpoint,
            "request_url":      request_url,
            "request_params":   json.dumps(request_params),
            "http_status_code": http_status_code,
            "call_sequence":    call_sequence,
            "raw_json":         json.dumps(raw_json),
            "sport_key":        sport_key,
            "event_count":      event_count,
        })


# ── Subcommand runners ─────────────────────────────────────────────────────────

def run_events(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    commence_time_from: str,
    commence_time_to: str,
    dry_run: bool = False,
) -> None:
    """
    Fetch MLB events within the given UTC time window and store the complete
    response array as a single row. One API call → one row; dbt staging layer
    flattens raw_json into individual event rows.
    """
    load_id      = str(uuid.uuid4())
    ingestion_ts = datetime.now(tz=timezone.utc)
    params: dict = {
        "commenceTimeFrom": commence_time_from,
        "commenceTimeTo":   commence_time_to,
    }

    log.info(
        "Events ingest → %s  window=[%s, %s]  load_id=%s",
        target.qualified_name, commence_time_from, commence_time_to, load_id,
    )

    try:
        result = call_parlay_api(EVENTS_ENDPOINT, params)
    except requests.HTTPError as exc:
        log.error("HTTP error fetching events: %s", exc)
        return
    except requests.RequestException as exc:
        log.error("Request failed fetching events: %s", exc)
        return

    event_count = len(result.payload) if isinstance(result.payload, list) else 0
    log.info("  %d event(s) in response", event_count)

    if dry_run:
        log.info(
            "[DRY RUN] Would insert 1 row to %s (%d event(s) in payload)",
            target.qualified_name, event_count,
        )
        return

    try:
        insert_event_row(
            conn,
            target             = target,
            ingestion_ts       = ingestion_ts,
            load_id            = load_id,
            call_sequence      = 1,
            source_endpoint    = EVENTS_ENDPOINT,
            request_url        = result.url,
            request_params     = params,
            http_status_code   = result.status_code,
            raw_json           = result.payload,
            event_id           = None,
            canonical_event_id = None,
            sport_key          = None,
            sport_title        = None,
            commence_time      = None,
            home_team          = None,
            away_team          = None,
        )
        log.info(
            "Events ingest complete — 1 row inserted, %d event(s) in payload (load_id=%s)",
            event_count, load_id,
        )
    except Exception as exc:
        log.error("Snowflake write failed: %s", exc)


def run_odds(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    markets: list[str],
    regions: list[str],
    odds_format: str,
    date_format: str,
    dry_run: bool = False,
) -> None:
    """
    Fetch MLB odds for each (market, region) combination and insert each
    event's odds as its own row into target.
    """
    load_id      = str(uuid.uuid4())
    ingestion_ts = datetime.now(tz=timezone.utc)
    total_calls  = len(markets) * len(regions)
    call_sequence = 0

    log.info(
        "Odds ingest → %s  %d market(s) × %d region(s) = %d call(s)  load_id=%s",
        target.qualified_name, len(markets), len(regions), total_calls, load_id,
    )

    for market in markets:
        for region in regions:
            call_sequence += 1
            params = {
                "markets":    market,
                "regions":    region,
                "oddsFormat": odds_format,
                "dateFormat": date_format,
            }
            log.info(
                "[%d/%d] market=%s  region=%s",
                call_sequence, total_calls, market, region,
            )

            try:
                result = call_parlay_api(ODDS_ENDPOINT, params)
            except requests.HTTPError as exc:
                log.warning(
                    "  HTTP error for market=%s region=%s: %s — skipping",
                    market, region, exc,
                )
                time.sleep(REQUEST_DELAY)
                continue
            except requests.RequestException as exc:
                log.warning(
                    "  Request failed for market=%s region=%s: %s — skipping",
                    market, region, exc,
                )
                time.sleep(REQUEST_DELAY)
                continue

            events: list[dict] = result.payload if isinstance(result.payload, list) else []
            log.info("  %d event(s) with odds returned", len(events))

            if dry_run:
                log.info(
                    "  [DRY RUN] Would insert %d row(s) to %s",
                    len(events), target.qualified_name,
                )
                time.sleep(REQUEST_DELAY)
                continue

            inserted = 0
            for event in events:
                bookmakers = event.get("bookmakers")
                try:
                    insert_odds_row(
                        conn,
                        target             = target,
                        ingestion_ts       = ingestion_ts,
                        load_id            = load_id,
                        call_sequence      = call_sequence,
                        source_endpoint    = ODDS_ENDPOINT,
                        request_url        = result.url,
                        request_params     = params,
                        http_status_code   = result.status_code,
                        raw_json           = event,
                        event_id           = event.get("id"),
                        canonical_event_id = event.get("canonical_event_id"),
                        sport_key          = event.get("sport_key"),
                        sport_title        = event.get("sport_title"),
                        commence_time      = event.get("commence_time"),
                        home_team          = event.get("home_team"),
                        away_team          = event.get("away_team"),
                        bookmakers_count   = len(bookmakers) if isinstance(bookmakers, list) else None,
                    )
                    inserted += 1
                except Exception as exc:
                    log.error(
                        "  Snowflake write failed for event %s (market=%s region=%s): %s",
                        event.get("id"), market, region, exc,
                    )

            log.info("  %d/%d row(s) inserted", inserted, len(events))
            time.sleep(REQUEST_DELAY)

    log.info("Odds ingest complete — load_id=%s", load_id)


# ── Historical odds ───────────────────────────────────────────────────────────

def _hist_default_start() -> date:
    """90 days prior to today — Business plan historical data limit."""
    return date.today() - timedelta(days=HIST_BACKFILL_DAYS)


def _hist_default_end() -> date:
    """Yesterday — today's games may not yet be finalized."""
    return date.today() - timedelta(days=1)


def _iter_calendar_days(start_date: date, end_date: date):
    """Yield each calendar date in [start_date, end_date] inclusive."""
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def fetch_already_loaded_odds_combos(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
) -> set[tuple[date, str]]:
    """
    Return (game_date, market) pairs already present in target for the given
    range. Used to skip (date, market) combos completed in a prior run.
    """
    sql = f"""
        SELECT DISTINCT
            commence_time::date              AS game_date,
            request_params:markets::varchar  AS market
        FROM {target.qualified_name}
        WHERE source_endpoint = %(endpoint)s
          AND commence_time IS NOT NULL
          AND commence_time::date >= %(start_date)s::date
          AND commence_time::date <= %(end_date)s::date
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "endpoint":   HIST_ODDS_ENDPOINT,
            "start_date": start_date.isoformat(),
            "end_date":   end_date.isoformat(),
        })
        return {(row[0], row[1]) for row in cur.fetchall() if row[0] and row[1]}


def run_historical_odds(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Fetch historical odds for every calendar day in [start_date, end_date].

    Parlay API uses a single date=YYYY-MM-DD param (not commenceTimeFrom/To),
    so one call is made per (date, market). Each event in the response is
    stored as its own row. Idempotent by (game_date, market).
    """
    if dry_run:
        log.info("[DRY RUN] Skipping idempotency check.")
        already_loaded: set[tuple[date, str]] = set()
    elif force:
        log.info("--force: skipping already-loaded check")
        already_loaded = set()
    else:
        log.info("Checking for already-loaded (game_date, market) pairs ...")
        already_loaded = fetch_already_loaded_odds_combos(conn, target, start_date, end_date)
        if already_loaded:
            log.info(
                "  %d pair(s) already loaded — will skip", len(already_loaded)
            )

    calendar_days = list(_iter_calendar_days(start_date, end_date))
    total_calls   = len(calendar_days) * len(DEFAULT_MARKETS)
    load_id       = str(uuid.uuid4())
    call_sequence = 0
    rows_inserted = 0

    log.info(
        "Historical odds ingest: %d day(s) × %d market(s) = %d call(s) → %s  load_id=%s",
        len(calendar_days), len(DEFAULT_MARKETS), total_calls,
        target.qualified_name, load_id,
    )

    for game_date in calendar_days:
        ingestion_ts = datetime.now(tz=timezone.utc)
        date_inserted = 0

        for market in DEFAULT_MARKETS:
            call_sequence += 1

            if (game_date, market) in already_loaded:
                log.info(
                    "[%d/%d] %s  market=%s — already loaded, skipping",
                    call_sequence, total_calls, game_date, market,
                )
                continue

            if force and not dry_run:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        DELETE FROM {target.qualified_name}
                        WHERE source_endpoint = %(endpoint)s
                          AND commence_time::date = %(game_date)s::date
                          AND request_params:markets::varchar = %(market)s
                        """,
                        {
                            "endpoint":  HIST_ODDS_ENDPOINT,
                            "game_date": game_date.isoformat(),
                            "market":    market,
                        },
                    )
                    deleted = cur.rowcount
                if deleted:
                    log.info(
                        "  --force: deleted %d existing row(s) for %s market=%s",
                        deleted, game_date, market,
                    )

            params: dict = {
                "date":       game_date.isoformat(),
                "markets":    market,
                "regions":    ",".join(DEFAULT_REGIONS),
                "oddsFormat": DEFAULT_ODDS_FORMAT,
                "dateFormat": DEFAULT_DATE_FORMAT,
            }

            log.info(
                "[%d/%d] %s  market=%s",
                call_sequence, total_calls, game_date, market,
            )

            try:
                result = call_parlay_api(HIST_ODDS_ENDPOINT, params)
            except requests.HTTPError as exc:
                log.warning(
                    "  HTTP error for %s market=%s: %s — skipping",
                    game_date, market, exc,
                )
                time.sleep(REQUEST_DELAY)
                continue
            except requests.RequestException as exc:
                log.warning(
                    "  Request failed for %s market=%s: %s — skipping",
                    game_date, market, exc,
                )
                time.sleep(REQUEST_DELAY)
                continue

            events: list[dict] = result.payload if isinstance(result.payload, list) else []

            if not events:
                log.info("  No data in response — skipping insert")
                time.sleep(REQUEST_DELAY)
                continue

            log.info("  %d event(s) in response", len(events))

            if dry_run:
                log.info(
                    "  [DRY RUN] Would insert %d row(s) to %s",
                    len(events), target.qualified_name,
                )
                date_inserted += len(events)
                rows_inserted += len(events)
                time.sleep(REQUEST_DELAY)
                continue

            for event in events:
                bookmakers = event.get("bookmakers")
                try:
                    insert_odds_row(
                        conn,
                        target             = target,
                        ingestion_ts       = ingestion_ts,
                        load_id            = load_id,
                        call_sequence      = call_sequence,
                        source_endpoint    = HIST_ODDS_ENDPOINT,
                        request_url        = result.url,
                        request_params     = params,
                        http_status_code   = result.status_code,
                        raw_json           = event,
                        event_id           = event.get("id"),
                        canonical_event_id = event.get("canonical_event_id"),
                        sport_key          = event.get("sport_key"),
                        sport_title        = event.get("sport_title"),
                        commence_time      = event.get("commence_time"),
                        home_team          = event.get("home_team"),
                        away_team          = event.get("away_team"),
                        bookmakers_count   = len(bookmakers) if isinstance(bookmakers, list) else None,
                    )
                    date_inserted += 1
                    rows_inserted += 1
                except Exception as exc:
                    log.error(
                        "  Snowflake write failed for event=%s market=%s: %s",
                        event.get("id"), market, exc,
                    )

            log.info("  %d/%d row(s) inserted", date_inserted, len(events))
            time.sleep(REQUEST_DELAY)

    log.info(
        "Historical odds ingest complete — %d call(s), %d row(s)  load_id=%s",
        call_sequence, rows_inserted, load_id,
    )
    print(f"rows_inserted={rows_inserted}", flush=True)


# ── Historical matches ────────────────────────────────────────────────────────

def fetch_already_loaded_match_dates(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
) -> set[date]:
    """Return game_dates already present in the matches table for the given range."""
    sql = f"""
        SELECT DISTINCT game_date
        FROM {target.qualified_name}
        WHERE source_endpoint = %(endpoint)s
          AND game_date IS NOT NULL
          AND game_date >= %(start_date)s::date
          AND game_date <= %(end_date)s::date
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "endpoint":   HIST_MATCHES_ENDPOINT,
            "start_date": start_date.isoformat(),
            "end_date":   end_date.isoformat(),
        })
        return {row[0] for row in cur.fetchall() if row[0]}


def run_historical_matches(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Fetch historical match results (scores, ML odds, has_odds flag) for each
    calendar day via /historical/matches. One call per date; stores records
    for that date as a single row in mlb_matches_raw. Idempotent by game_date.

    Correct params (confirmed 2026-05-10): use dateFrom=YYYY-MM-DD and
    dateTo=YYYY-MM-DD. The `date` param is silently ignored by the API.
    Max lookback is 90 days (Business plan). Max limit per call is 5000;
    a single-day call returns ~91 records (15 games × ~6 bookmakers) so the
    default 1000 limit is always sufficient.
    """
    if dry_run:
        log.info("[DRY RUN] Skipping idempotency check.")
        already_loaded: set[date] = set()
    elif force:
        log.info("--force: skipping already-loaded check")
        already_loaded = set()
    else:
        log.info("Checking for already-loaded game_dates ...")
        already_loaded = fetch_already_loaded_match_dates(conn, target, start_date, end_date)
        if already_loaded:
            log.info("  %d date(s) already loaded — will skip", len(already_loaded))

    calendar_days = list(_iter_calendar_days(start_date, end_date))
    load_id       = str(uuid.uuid4())
    call_sequence = 0
    rows_inserted = 0
    total         = len(calendar_days)

    log.info(
        "Historical matches ingest: %d day(s) → %s  load_id=%s",
        total, target.qualified_name, load_id,
    )

    for game_date in calendar_days:
        call_sequence += 1

        if game_date in already_loaded:
            log.info(
                "[%d/%d] %s — already loaded, skipping",
                call_sequence, total, game_date,
            )
            continue

        if force and not dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {target.qualified_name}
                    WHERE source_endpoint = %(endpoint)s
                      AND game_date = %(game_date)s::date
                    """,
                    {"endpoint": HIST_MATCHES_ENDPOINT, "game_date": game_date.isoformat()},
                )
                deleted = cur.rowcount
            if deleted:
                log.info("  --force: deleted %d existing row(s) for %s", deleted, game_date)

        ingestion_ts = datetime.now(tz=timezone.utc)
        params       = {
            "dateFrom": game_date.isoformat(),
            "dateTo":   game_date.isoformat(),
        }

        log.info("[%d/%d] %s", call_sequence, total, game_date)

        try:
            result = call_parlay_api(HIST_MATCHES_ENDPOINT, params)
        except requests.HTTPError as exc:
            log.warning("  HTTP error for %s: %s — skipping", game_date, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request failed for %s: %s — skipping", game_date, exc)
            time.sleep(REQUEST_DELAY)
            continue

        payload      = result.payload if isinstance(result.payload, list) else []
        record_count = len(payload)

        if not payload:
            log.info("  No data — skipping insert")
            time.sleep(REQUEST_DELAY)
            continue

        log.info("  %d record(s) in response", record_count)

        if dry_run:
            log.info(
                "  [DRY RUN] Would insert 1 row to %s (%d record(s) in payload)",
                target.qualified_name, record_count,
            )
            rows_inserted += 1
            time.sleep(REQUEST_DELAY)
            continue

        first     = payload[0]
        sport_key = first.get("sport_key", "baseball_mlb")
        season    = str(first.get("season")) if first.get("season") else None

        try:
            insert_matches_row(
                conn,
                target           = target,
                ingestion_ts     = ingestion_ts,
                load_id          = load_id,
                call_sequence    = call_sequence,
                source_endpoint  = HIST_MATCHES_ENDPOINT,
                request_url      = result.url,
                request_params   = params,
                http_status_code = result.status_code,
                raw_json         = payload,
                game_date        = game_date,
                sport_key        = sport_key,
                season           = season,
                record_count     = record_count,
            )
            log.info("  Inserted — %d record(s)", record_count)
            rows_inserted += 1
        except Exception as exc:
            log.error("  Snowflake write failed for %s: %s", game_date, exc)

        time.sleep(REQUEST_DELAY)

    log.info(
        "Historical matches ingest complete — %d call(s), %d date(s) inserted  load_id=%s",
        call_sequence, rows_inserted, load_id,
    )


# ── Line movement ─────────────────────────────────────────────────────────────

def fetch_event_ids_from_snowflake(
    conn: snowflake.connector.SnowflakeConnection,
    events_target: SnowflakeTarget,
    lookahead_days: int,
) -> list[str]:
    """
    Resolve event IDs from the most recent events ingestion run in mlb_events_raw.
    Returns all distinct Parlay event IDs found in any run within the last 26 hours.

    Note: commence_time filtering is intentionally omitted. The Parlay API events
    endpoint returns a uniform commence_time for all games in a daily slate (not
    actual per-game start times), making it unreliable for filtering. All events
    from the latest run are returned and line-movement is fetched for each.
    """
    sql = f"""
        SELECT DISTINCT
            e.value:id::varchar AS event_id
        FROM {events_target.qualified_name},
        LATERAL FLATTEN(input => raw_json) e
        WHERE source_endpoint = %(endpoint)s
          AND ingestion_ts >= DATEADD('hour', -26, CURRENT_TIMESTAMP())
          AND e.value:id IS NOT NULL
        ORDER BY event_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"endpoint": EVENTS_ENDPOINT})
        return [row[0] for row in cur.fetchall() if row[0]]


def run_line_movement(
    conn: snowflake.connector.SnowflakeConnection,
    events_target: SnowflakeTarget,
    target: SnowflakeTarget,
    event_ids: list[str] | None,
    dry_run: bool = False,
) -> None:
    """
    Fetch line-movement history for each event_id and insert the full
    (event × source × market) snapshots array into mlb_line_movement_raw.

    If event_ids is None or empty, auto-resolves from the most recent events
    run in mlb_events_raw (games commencing within the next 2 days).
    """
    if not event_ids:
        log.info("No --event-ids provided — resolving from mlb_events_raw ...")
        event_ids = fetch_event_ids_from_snowflake(
            conn, events_target, LINE_MOVEMENT_LOOKAHEAD_DAYS
        )
        if not event_ids:
            log.warning("No upcoming event IDs found in mlb_events_raw — nothing to ingest")
            return
        log.info("  Resolved %d event ID(s) from Snowflake", len(event_ids))

    load_id       = str(uuid.uuid4())
    total         = len(event_ids)
    call_sequence = 0

    log.info(
        "Line-movement ingest: %d event(s) → %s  load_id=%s",
        total, target.qualified_name, load_id,
    )

    for event_id in event_ids:
        call_sequence += 1
        ingestion_ts = datetime.now(tz=timezone.utc)
        params       = {"eventId": event_id}

        log.info("[%d/%d] event_id=%s", call_sequence, total, event_id)

        try:
            result = call_parlay_api(LINE_MOVEMENT_ENDPOINT, params)
        except requests.HTTPError as exc:
            log.warning("  HTTP error for event_id=%s: %s — skipping", event_id, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request failed for event_id=%s: %s — skipping", event_id, exc)
            time.sleep(REQUEST_DELAY)
            continue

        payload      = result.payload if isinstance(result.payload, list) else []
        record_count = len(payload)

        first      = payload[0] if payload else {}
        home_team  = first.get("home_team")
        away_team  = first.get("away_team")
        markets    = [r.get("market_key") for r in payload if r.get("market_key")]

        log.info(
            "  %s vs %s — %d record(s), markets: %s",
            home_team, away_team, record_count,
            sorted(set(markets)) if markets else "none",
        )

        if not payload:
            log.info("  No data — skipping insert")
            time.sleep(REQUEST_DELAY)
            continue

        if dry_run:
            log.info(
                "  [DRY RUN] Would insert 1 row to %s (%d record(s) in payload)",
                target.qualified_name, record_count,
            )
            time.sleep(REQUEST_DELAY)
            continue

        try:
            insert_line_movement_row(
                conn,
                target            = target,
                ingestion_ts      = ingestion_ts,
                load_id           = load_id,
                call_sequence     = call_sequence,
                source_endpoint   = LINE_MOVEMENT_ENDPOINT,
                request_url       = result.url,
                request_params    = params,
                http_status_code  = result.status_code,
                raw_json          = payload,
                event_id          = event_id,
                home_team         = home_team,
                away_team         = away_team,
                record_count      = record_count,
                markets_captured  = markets,
            )
            log.info("  Inserted — %d record(s)", record_count)
        except Exception as exc:
            log.error("  Snowflake write failed for event_id=%s: %s", event_id, exc)

        time.sleep(REQUEST_DELAY)

    log.info(
        "Line-movement ingest complete — %d event(s)  load_id=%s",
        total, load_id,
    )


# ── Canonical events ─────────────────────────────────────────────────────────

def run_canonical_events(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    dry_run: bool = False,
) -> None:
    """
    Fetch canonical events (real per-game start times) for the MLB and store
    the full response as one row per ingestion run.

    Auth: apiKey query parameter — X-API-Key header is rejected on this endpoint.
    The endpoint returns upcoming events with their actual scheduled start times,
    unlike /events which returns 19:00:00Z for all games in a daily slate.
    """
    load_id      = str(uuid.uuid4())
    ingestion_ts = datetime.now(tz=timezone.utc)
    params: dict = {}   # no filter params; endpoint returns all upcoming MLB events

    log.info(
        "Canonical events ingest → %s  load_id=%s",
        target.qualified_name, load_id,
    )

    try:
        result = call_parlay_api_query_auth(CANONICAL_EVENTS_ENDPOINT, params)
    except requests.HTTPError as exc:
        log.error("HTTP error fetching canonical events: %s", exc)
        return
    except requests.RequestException as exc:
        log.error("Request failed fetching canonical events: %s", exc)
        return

    payload     = result.payload
    event_count = len(payload) if isinstance(payload, list) else 0
    log.info("  %d canonical event(s) in response", event_count)

    if dry_run:
        log.info(
            "[DRY RUN] Would insert 1 row to %s (%d event(s) in payload)",
            target.qualified_name, event_count,
        )
        return

    first_event = payload[0] if isinstance(payload, list) and payload else {}
    sport_key   = first_event.get("sport_key")

    try:
        insert_canonical_events_row(
            conn,
            target            = target,
            ingestion_ts      = ingestion_ts,
            load_id           = load_id,
            call_sequence     = 1,
            source_endpoint   = CANONICAL_EVENTS_ENDPOINT,
            request_url       = result.url,
            request_params    = params,
            http_status_code  = result.status_code,
            raw_json          = payload,
            sport_key         = sport_key,
            event_count       = event_count,
        )
        log.info(
            "Canonical events ingest complete — 1 row inserted, %d event(s) in payload (load_id=%s)",
            event_count, load_id,
        )
    except Exception as exc:
        log.error("Snowflake write failed: %s", exc)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest MLB data from the Parlay API into Snowflake.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Make API calls but skip all Snowflake writes. "
            "Logs the endpoint, row count, and target that would be written. "
            "Must be placed before the subcommand name."
        ),
    )
    parser.add_argument(
        "--target",
        choices=["prod", "dev"],
        default="prod",
        help=(
            "Write target: 'prod' uses parlayapi schema (default); "
            "'dev' redirects all writes to parlayapi_dev. "
            "Must be placed before the subcommand name."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # events
    events_parser = sub.add_parser(
        "events",
        help="Fetch upcoming MLB events and ingest into the events table.",
    )
    events_parser.add_argument(
        "--commence-time-from",
        default=None,
        metavar="ISO8601",
        help="Lower bound for event commence time (ISO 8601 UTC). Defaults to today 00:00:00Z.",
    )
    events_parser.add_argument(
        "--commence-time-to",
        default=None,
        metavar="ISO8601",
        help=f"Upper bound for event commence time. Defaults to today + {DEFAULT_EVENTS_WINDOW_DAYS}d.",
    )

    # odds
    odds_parser = sub.add_parser(
        "odds",
        help="Fetch current MLB odds and ingest into the odds table.",
    )
    odds_parser.add_argument(
        "--markets",
        nargs="+",
        default=DEFAULT_MARKETS,
        metavar="MARKET",
        help=f"Market keys to fetch (default: {' '.join(DEFAULT_MARKETS)}).",
    )
    odds_parser.add_argument(
        "--regions",
        nargs="+",
        default=DEFAULT_REGIONS,
        metavar="REGION",
        help=f"Regions for bookmaker filtering (default: {' '.join(DEFAULT_REGIONS)}).",
    )
    odds_parser.add_argument(
        "--odds-format",
        default=DEFAULT_ODDS_FORMAT,
        choices=["american", "decimal", "hongkong", "indonesian", "malay"],
        help=f"Odds format returned by the API (default: {DEFAULT_ODDS_FORMAT}).",
    )
    odds_parser.add_argument(
        "--date-format",
        default=DEFAULT_DATE_FORMAT,
        choices=["iso", "unix"],
        help=f"Date format for commence_time fields (default: {DEFAULT_DATE_FORMAT}).",
    )

    # historical-odds
    hist_odds_parser = sub.add_parser(
        "historical-odds",
        help=(
            "Fetch historical MLB odds (one call per date per market). "
            f"Defaults to the last {HIST_BACKFILL_DAYS} days."
        ),
    )
    hist_odds_parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            f"First date to fetch, inclusive. "
            f"Defaults to {HIST_BACKFILL_DAYS} days before today."
        ),
    )
    hist_odds_parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Last date to fetch, inclusive. Defaults to yesterday.",
    )
    hist_odds_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch dates already present in target (bypasses idempotency check).",
    )

    # historical-matches
    hist_matches_parser = sub.add_parser(
        "historical-matches",
        help=(
            "Fetch historical match results + ML odds via /historical/matches. "
            f"Defaults to the last {HIST_BACKFILL_DAYS} days."
        ),
    )
    hist_matches_parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=f"First date to fetch, inclusive. Defaults to {HIST_BACKFILL_DAYS} days before today.",
    )
    hist_matches_parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Last date to fetch, inclusive. Defaults to yesterday.",
    )
    hist_matches_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch dates already present in target (bypasses idempotency check).",
    )

    # line-movement
    line_mov_parser = sub.add_parser(
        "line-movement",
        help=(
            "Fetch intraday price history for upcoming game event IDs. "
            "Auto-resolves event IDs from mlb_events_raw if --event-ids is omitted."
        ),
    )
    line_mov_parser.add_argument(
        "--event-ids",
        nargs="+",
        default=None,
        metavar="EVENT_ID",
        help=(
            "Explicit Parlay event IDs to fetch. If omitted, auto-resolved from "
            "the most recent events run in mlb_events_raw."
        ),
    )

    # events-canonical
    sub.add_parser(
        "events-canonical",
        help=(
            "Fetch canonical MLB events with real per-game start times. "
            "Auth via apiKey query param (X-API-Key header rejected on this endpoint). "
            "Stores one row per run in mlb_canonical_events_raw."
        ),
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.target == "dev":
        os.environ["PARLAY_TARGET_SCHEMA"] = "parlayapi_dev"

    dry_run = args.dry_run
    if dry_run:
        log.info("[DRY RUN] No Snowflake writes will be performed.")

    targets = resolve_targets()

    log.info(
        "Connecting to Snowflake  database=%s  schema=%s",
        targets.events.database, targets.events.schema,
    )
    conn = get_snowflake_connection(targets.events.database, targets.events.schema)

    try:
        if args.command == "events":
            window_from, window_to = default_window(days=DEFAULT_EVENTS_WINDOW_DAYS)
            run_events(
                conn,
                targets.events,
                commence_time_from = args.commence_time_from or window_from,
                commence_time_to   = args.commence_time_to   or window_to,
                dry_run            = dry_run,
            )

        elif args.command == "odds":
            run_odds(
                conn,
                targets.odds,
                markets     = args.markets,
                regions     = args.regions,
                odds_format = args.odds_format,
                date_format = args.date_format,
                dry_run     = dry_run,
            )

        elif args.command == "historical-odds":
            start = date.fromisoformat(args.start_date) if args.start_date else _hist_default_start()
            end   = date.fromisoformat(args.end_date)   if args.end_date   else _hist_default_end()
            log.info("Historical odds range: %s → %s", start, end)
            run_historical_odds(conn, targets.odds, start, end, force=args.force, dry_run=dry_run)

        elif args.command == "historical-matches":
            start = date.fromisoformat(args.start_date) if args.start_date else _hist_default_start()
            end   = date.fromisoformat(args.end_date)   if args.end_date   else _hist_default_end()
            log.info("Historical matches range: %s → %s", start, end)
            run_historical_matches(conn, targets.matches, start, end, force=args.force, dry_run=dry_run)

        elif args.command == "line-movement":
            run_line_movement(
                conn,
                targets.events,
                targets.line_movement,
                event_ids = args.event_ids,
                dry_run   = dry_run,
            )

        elif args.command == "events-canonical":
            run_canonical_events(conn, targets.canonical_events, dry_run=dry_run)

    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
