"""
odds_api_ingestion.py
---------------------
Ingests MLB data from The Odds API into Snowflake. Four ingestion modes are
supported and can be run independently via CLI subcommands:

  events            — Calls /v4/sports/baseball_mlb/events and inserts the full
                      response array as a single row in the events target table.

  historical-events — Calls /v4/historical/sports/baseball_mlb/events once per
                      regular-season game date in a configurable range. The API
                      snapshot timestamp is set to 1 hour before the earliest
                      first pitch on each date. Results land in the same events
                      target table as the live events subcommand so all
                      downstream dbt models consume them without schema changes.

  odds              — Calls /v4/sports/baseball_mlb/odds for one or more
                      market/region combinations and inserts each event's odds
                      as its own row in the configured odds target table.

  historical-odds   — Fetches historical odds for each regular-season game date
                      via /v4/historical/sports/baseball_mlb/odds using the same
                      snapshot strategy as historical-events (1 hour before first
                      pitch UTC). commenceTimeFrom/commenceTimeTo scope the
                      response to that calendar date. Idempotent: (game_date,
                      market) pairs already in target are skipped. Results land
                      in mlb_odds_raw — the same target as live odds — so
                      stg_oddsapi_odds and all downstream models consume them
                      without schema changes.

Loading is append-only. No rows are updated or deleted. Every run produces a
new set of rows tagged with a shared load_id so a full run can be isolated in
queries.

Target tables are resolved at startup from environment variables, falling back
to the production defaults. Override any of the four variables to redirect
writes without editing code (useful for testing against a staging schema):

    ODDS_TARGET_DATABASE   (default: baseball_data)
    ODDS_TARGET_SCHEMA     (default: oddsapi)
    ODDS_EVENTS_TABLE      (default: mlb_events_raw)
    ODDS_ODDS_TABLE        (default: mlb_odds_raw)

Snowflake authentication — private key (preferred) or password fallback:
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

    Odds API:
        ODDS_API_KEY

Usage:
    uv run odds_api_ingestion.py events
    uv run odds_api_ingestion.py events --commence-time-from 2026-04-22T00:00:00Z --commence-time-to 2026-04-29T00:00:00Z

    # Full historical events backfill (2021 season opener through day before live ingestion)
    uv run odds_api_ingestion.py historical-events

    # Incremental / partial events backfill
    uv run odds_api_ingestion.py historical-events --start-date 2023-04-01 --end-date 2023-10-01

    uv run odds_api_ingestion.py odds
    uv run odds_api_ingestion.py odds --markets h2h totals --regions us us2
    uv run odds_api_ingestion.py odds --odds-format american --date-format iso

    # Full historical odds backfill (requires historical-events to have run first)
    uv run odds_api_ingestion.py historical-odds

    # Incremental / partial historical odds backfill
    uv run odds_api_ingestion.py historical-odds --start-date 2024-04-01 --end-date 2024-10-01
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

ODDS_API_BASE_URL    = "https://api.the-odds-api.com/v4"
EVENTS_ENDPOINT      = "/sports/baseball_mlb/events"
ODDS_ENDPOINT        = "/sports/baseball_mlb/odds"
HIST_EVENTS_ENDPOINT = "/historical/sports/baseball_mlb/events"
HIST_ODDS_ENDPOINT   = "/historical/sports/baseball_mlb/odds"

# First day of the 2021 regular season — default historical events backfill start
HIST_DEFAULT_START = date(2021, 4, 1)
# Day before live ingestion began — default historical backfill end (shared)
HIST_DEFAULT_END   = date(2026, 4, 22)
# Default start for historical odds backfill (card 3 scope: 2023–present)
HIST_ODDS_DEFAULT_START = date(2023, 1, 1)

SOURCE_SYSTEM = "the_odds_api"
PROCESS_NAME  = "odds_api_ingestion.py"


# ── E11.1-W3pre: S3 lakehouse mirror ────────────────────────────────────────────
# This writer is being migrated to write the S3 lakehouse_raw/ tier (which the dual-branch
# stg_oddsapi_* models flatten in DuckDB) instead of Snowflake. The switch is driven by the
# shared keystone (scripts/utils/lakehouse_raw_writer) and gated by env so the cutover is
# safe and reversible:
#   LAKEHOUSE_RAW_WRITE_MODE = snowflake (DEFAULT) → unchanged: Snowflake only, no S3
#                            = both                → dual-write (validate parity, then…)
#                            = s3                  → S3 only (Snowflake leg retired)
# Default 'snowflake' means importing/running this file is a no-op change until the operator
# opts in — the mirror code below stays dead. ⚠️ mlb_odds_raw feeds the SERVING-critical
# mart_odds_outcomes, so flip to 's3' only AFTER parity_check_w3pre is GREEN.

def _lakehouse_write_mode() -> str:
    return os.environ.get("LAKEHOUSE_RAW_WRITE_MODE", "snowflake").lower()


def _mirror_raw_to_lakehouse(source: str, rows: list[dict]) -> None:
    """Mirror raw rows to S3 lakehouse_raw/<source>/ via the shared keystone. Rows carry
    NATIVE types (int credits, dict raw_json/request_params, datetime ingestion_ts) so the
    parquet schema matches scripts/export_odds_raw_to_s3.py exactly (no union_by_name drift).
    Local import keeps boto3/pyarrow off the default Snowflake-only path."""
    if not rows:
        return
    from utils.lakehouse_raw_writer import write_raw_rows_s3
    n = write_raw_rows_s3(source, rows, mode="append")
    log.info("  mirrored %d raw row(s) → S3 lakehouse_raw/%s/", n, source)

# Production defaults — all four are overridable via env vars at startup.
_DEFAULT_DATABASE     = "baseball_data"
_DEFAULT_SCHEMA       = "oddsapi"
_DEFAULT_EVENTS_TABLE = "mlb_events_raw"
_DEFAULT_ODDS_TABLE   = "mlb_odds_raw"

# Defaults for the odds endpoint
DEFAULT_MARKETS     = ["h2h", "totals"]
DEFAULT_REGIONS     = ["us", "us2"]
DEFAULT_ODDS_FORMAT = "american"
DEFAULT_DATE_FORMAT = "iso"

# Default look-ahead window for the events endpoint (days)
DEFAULT_EVENTS_WINDOW_DAYS = 7

# Polite delay between API calls (seconds)
REQUEST_DELAY = 0.5


# ── Target resolution ─────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class SnowflakeTarget:
    """Fully-qualified Snowflake write destination for one table."""
    database: str
    schema: str
    table: str

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"


def resolve_targets() -> tuple[SnowflakeTarget, SnowflakeTarget]:
    """
    Read target location from env vars, falling back to production defaults.
    Returns (events_target, odds_target).
    """
    database = os.environ.get("ODDS_TARGET_DATABASE", _DEFAULT_DATABASE)
    schema   = os.environ.get("ODDS_TARGET_SCHEMA",   _DEFAULT_SCHEMA)

    events_target = SnowflakeTarget(
        database = database,
        schema   = schema,
        table    = os.environ.get("ODDS_EVENTS_TABLE", _DEFAULT_EVENTS_TABLE),
    )
    odds_target = SnowflakeTarget(
        database = database,
        schema   = schema,
        table    = os.environ.get("ODDS_ODDS_TABLE", _DEFAULT_ODDS_TABLE),
    )
    return events_target, odds_target


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
    """
    Build a Snowflake connection scoped to the given database and schema.
    Uses private key auth when SNOWFLAKE_PRIVATE_KEY_PATH is set, otherwise
    falls back to password auth.
    """
    required_base = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required_base if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

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

    kwargs: dict = {
        "account":   account,
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


# ── Odds API request layer ─────────────────────────────────────────────────────

class OddsApiResponse:
    """Wraps a raw requests.Response to expose the JSON body and credit headers."""

    def __init__(self, response: requests.Response) -> None:
        self._response = response
        self.status_code: int = response.status_code
        self.url: str = response.url
        self.payload: Any = response.json()
        self.requests_used: int | None = _parse_int_header(
            response.headers.get("x-requests-used")
        )
        self.requests_remaining: int | None = _parse_int_header(
            response.headers.get("x-requests-remaining")
        )

    def log_credits(self) -> None:
        log.info(
            "  API credits — used: %s  remaining: %s",
            self.requests_used,
            self.requests_remaining,
        )


def _parse_int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _get_ordered_keys(historical: bool, prefer_main: bool = False) -> list[tuple[str, str]]:
    """
    Return (label, api_key) pairs to try in priority order.

    For live endpoints the DEFAULT is starter key first (if set), then main key —
    this conserves the more expensive main-key credits for endpoints where it
    matters.

    For historical endpoints: main key only — the starter tier does not support
    the /historical/ path.

    prefer_main=True flips the live order to MAIN first, then starter as a quota
    fallback. Use this for COVERAGE-CRITICAL pulls (the /odds endpoint): The Odds
    API's starter tier returns a NARROWER bookmaker roster — it omits Fanatics,
    Caesars (williamhill_us) and rebet (confirmed 2026-06-17) — so a starter-first
    odds pull silently drops those books. The events endpoint carries no bookmaker
    data, so it keeps the credit-conserving starter-first default.
    """
    main_key = os.environ.get("ODDS_API_KEY")
    if not main_key:
        raise EnvironmentError("ODDS_API_KEY is not set in the environment or .env file.")
    starter = None if historical else os.environ.get("ODDS_API_STARTER_KEY")

    keys: list[tuple[str, str]] = []
    if prefer_main:
        keys.append(("main key", main_key))
        if starter:
            keys.append(("starter key", starter))
    else:
        if starter:
            keys.append(("starter key", starter))
        keys.append(("main key", main_key))
    return keys


def call_odds_api(endpoint: str, params: dict, prefer_main: bool = False) -> OddsApiResponse:
    """
    Make a GET request to the given Odds API endpoint path (e.g.
    '/sports/baseball_mlb/events') with the provided query parameters.

    For live endpoints, the starter key (ODDS_API_STARTER_KEY) is tried first by
    default. If a key returns HTTP 401 or 422 (invalid or quota exhausted) the
    next key in priority order is used as a fallback. Historical endpoints always
    use the main key directly — the starter tier does not support /historical/.

    prefer_main=True tries the MAIN key first (full bookmaker coverage); pass it
    for the /odds endpoint, whose starter-tier roster omits Fanatics, Caesars
    (williamhill_us) and rebet (see _get_ordered_keys).

    Raises requests.HTTPError when all available keys are exhausted.
    """
    url        = f"{ODDS_API_BASE_URL}{endpoint}"
    historical = "historical" in endpoint
    keys       = _get_ordered_keys(historical, prefer_main=prefer_main)

    log.info("GET %s  params=%s", url, {k: v for k, v in params.items()})

    for i, (key_label, key) in enumerate(keys):
        response = requests.get(url, params={"apiKey": key, **params}, timeout=30)

        if response.status_code in (401, 422) and i < len(keys) - 1:
            log.warning(
                "  %s returned HTTP %d — falling back to %s",
                key_label, response.status_code, keys[i + 1][0],
            )
            continue

        response.raise_for_status()
        result = OddsApiResponse(response)
        if len(keys) > 1:
            log.info("  Using %s", key_label)
        result.log_credits()
        return result

    raise RuntimeError("All API keys exhausted without a successful response")


# ── Snowflake write helpers ────────────────────────────────────────────────────

def insert_event_row(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    ingestion_ts: datetime,
    load_id: str,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    x_requests_used: int | None,
    x_requests_remaining: int | None,
    raw_json: Any,
    event_id: str | None,
    sport_key: str | None,
    sport_title: str | None,
    commence_time: str | None,
    home_team: str | None,
    away_team: str | None,
) -> None:
    sql = f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code, x_requests_used, x_requests_remaining,
            raw_json,
            event_id, sport_key, sport_title, commence_time, home_team, away_team
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
            %(x_requests_used)s,
            %(x_requests_remaining)s,
            PARSE_JSON(%(raw_json)s),
            %(event_id)s,
            %(sport_key)s,
            %(sport_title)s,
            %(commence_time)s::timestamp_ntz,
            %(home_team)s,
            %(away_team)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "ingestion_ts":          ingestion_ts.isoformat(),
            "load_id":               load_id,
            "source_system":         SOURCE_SYSTEM,
            "process_name":          PROCESS_NAME,
            "source_endpoint":       source_endpoint,
            "request_url":           request_url,
            "request_params":        json.dumps(request_params),
            "http_status_code":      http_status_code,
            "x_requests_used":       x_requests_used,
            "x_requests_remaining":  x_requests_remaining,
            "raw_json":              json.dumps(raw_json),
            "event_id":              event_id,
            "sport_key":             sport_key,
            "sport_title":           sport_title,
            "commence_time":         commence_time,
            "home_team":             home_team,
            "away_team":             away_team,
        })


# ── Bulk odds write ───────────────────────────────────────────────────────────
# The odds endpoints return one event object per game; the old path inserted each
# event with its own `INSERT … SELECT …, PARSE_JSON(raw_json)` statement, so a single
# live fire (~28 events × regions × markets ≈ 168 events) kept COMPUTE_WH hot for the
# whole script and re-parsed JSON per row (Story 12.3.8 / A2.15 anti-pattern).
#
# Instead, buffer all events for a fire (live) or game-date (historical) into Python,
# load them into a session-scoped TEMPORARY table whose JSON columns are VARCHAR, then
# run ONE set-based `INSERT INTO target SELECT …, PARSE_JSON(raw_json), …`. The warehouse
# is touched once at the end instead of per row. This is the established VARIANT-insert
# rule (feedback_snowflake_variant_insert): never PARSE_JSON inside an executemany VALUES
# — stage as VARCHAR, then PARSE_JSON in the set-based write.

_BULK_TMP_TABLE = "tmp_odds_ingest"

_CREATE_BULK_TMP_SQL = f"""
    CREATE OR REPLACE TEMPORARY TABLE {_BULK_TMP_TABLE} (
        ingestion_ts         VARCHAR,
        load_id              VARCHAR,
        source_system        VARCHAR,
        process_name         VARCHAR,
        source_endpoint      VARCHAR,
        request_url          VARCHAR,
        request_params       VARCHAR,
        http_status_code     VARCHAR,
        x_requests_used      VARCHAR,
        x_requests_remaining VARCHAR,
        raw_json             VARCHAR,
        event_id             VARCHAR,
        sport_key            VARCHAR,
        sport_title          VARCHAR,
        commence_time        VARCHAR,
        home_team            VARCHAR,
        away_team            VARCHAR,
        bookmakers_count     VARCHAR
    )
"""

_INSERT_BULK_TMP_SQL = f"""
    INSERT INTO {_BULK_TMP_TABLE} VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
"""


def _bulk_odds_insert_select_sql(target: SnowflakeTarget) -> str:
    return f"""
        INSERT INTO {target.qualified_name} (
            ingestion_ts, load_id,
            source_system, process_name,
            source_endpoint, request_url, request_params,
            http_status_code, x_requests_used, x_requests_remaining,
            raw_json,
            event_id, sport_key, sport_title, commence_time, home_team, away_team,
            bookmakers_count
        )
        SELECT
            ingestion_ts::timestamp_ntz,
            load_id,
            source_system,
            process_name,
            source_endpoint,
            request_url,
            PARSE_JSON(request_params),
            http_status_code::integer,
            x_requests_used::integer,
            x_requests_remaining::integer,
            PARSE_JSON(raw_json),
            event_id,
            sport_key,
            sport_title,
            commence_time::timestamp_ntz,
            home_team,
            away_team,
            bookmakers_count::integer
        FROM {_BULK_TMP_TABLE}
    """


def _opt_str(value: Any) -> str | None:
    """Render a value as VARCHAR for the staging table; None stays NULL."""
    return str(value) if value is not None else None


def build_odds_row(
    *,
    ingestion_ts: datetime,
    load_id: str,
    source_endpoint: str,
    request_url: str,
    request_params: dict,
    http_status_code: int,
    x_requests_used: int | None,
    x_requests_remaining: int | None,
    event: dict,
    bookmakers_count: int | None,
) -> tuple:
    """
    Build one staging-table row tuple (all VARCHAR-or-NULL) for a single odds event.
    Column order matches _INSERT_BULK_TMP_SQL / _CREATE_BULK_TMP_SQL.
    """
    return (
        ingestion_ts.isoformat(),
        load_id,
        SOURCE_SYSTEM,
        PROCESS_NAME,
        source_endpoint,
        request_url,
        json.dumps(request_params),
        _opt_str(http_status_code),
        _opt_str(x_requests_used),
        _opt_str(x_requests_remaining),
        json.dumps(event),
        event.get("id"),
        event.get("sport_key"),
        event.get("sport_title"),
        event.get("commence_time"),
        event.get("home_team"),
        event.get("away_team"),
        _opt_str(bookmakers_count),
    )


def bulk_insert_odds_rows(
    conn: snowflake.connector.SnowflakeConnection,
    *,
    target: SnowflakeTarget,
    rows: list[tuple],
) -> int:
    """
    Append many odds events to `target` with a single set-based write.

    Loads all `rows` (VARCHAR-staged tuples from build_odds_row) into a TEMPORARY
    table via one batched executemany, then runs ONE INSERT…SELECT with PARSE_JSON.
    Collapses N per-event warehouse-active INSERTs into a single temp load + one
    set-based INSERT. Append-only — no MERGE/dedup (matches the script's load model).
    Returns the number of rows written.
    """
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.execute(_CREATE_BULK_TMP_SQL)
        cur.executemany(_INSERT_BULK_TMP_SQL, rows)
        cur.execute(_bulk_odds_insert_select_sql(target))
        cur.execute(f"DROP TABLE IF EXISTS {_BULK_TMP_TABLE}")
    return len(rows)


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
    response array as a single row in target. One API call produces one row;
    the dbt staging layer is responsible for flattening the raw_json array
    into individual event rows.
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
        result = call_odds_api(EVENTS_ENDPOINT, params)
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

    write_mode = _lakehouse_write_mode()             # E11.1-W3pre
    if write_mode in ("snowflake", "both"):
        try:
            insert_event_row(
                conn,
                target               = target,
                ingestion_ts         = ingestion_ts,
                load_id              = load_id,
                source_endpoint      = EVENTS_ENDPOINT,
                request_url          = result.url,
                request_params       = params,
                http_status_code     = result.status_code,
                x_requests_used      = result.requests_used,
                x_requests_remaining = result.requests_remaining,
                raw_json             = result.payload,
                event_id             = None,
                sport_key            = None,
                sport_title          = None,
                commence_time        = None,
                home_team            = None,
                away_team            = None,
            )
            log.info("Events ingest (Snowflake) — 1 row, %d event(s) in payload (load_id=%s)",
                     event_count, load_id)
        except Exception as exc:
            log.error("Snowflake write failed: %s", exc)
    if write_mode in ("s3", "both"):
        # The events stg reads only ingestion_ts, load_id, x_requests_*, raw_json (the array).
        try:
            _mirror_raw_to_lakehouse("mlb_events_raw", [{
                "ingestion_ts":         ingestion_ts,
                "load_id":              load_id,
                "x_requests_used":      result.requests_used,
                "x_requests_remaining": result.requests_remaining,
                "raw_json":             result.payload,
            }])
            log.info("Events ingest (S3 lakehouse) — 1 row mirrored (load_id=%s)", load_id)
        except Exception as exc:
            log.error("S3 lakehouse mirror failed (load_id=%s): %s", load_id, exc)


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
    event's odds as its own row into target. Separating by market keeps each
    raw_json payload focused and makes downstream parsing straightforward.
    """
    load_id      = str(uuid.uuid4())
    ingestion_ts = datetime.now(tz=timezone.utc)
    total_calls  = len(markets) * len(regions)
    call_num     = 0
    # Buffer every event across all (market, region) calls, then write ONCE at the end
    # of the fire (one temp load + one PARSE_JSON INSERT-SELECT) so COMPUTE_WH is touched
    # once briefly instead of staying hot for the whole fetch loop. Each row carries its
    # own call's url/params/credits, so a single bulk write preserves per-call metadata.
    buffer: list[tuple] = []
    write_mode   = _lakehouse_write_mode()           # E11.1-W3pre
    mirror_buffer: list[dict] = []                   # stg-shaped dicts for the S3 mirror

    log.info(
        "Odds ingest → %s  %d market(s) × %d region(s) = %d call(s)  load_id=%s  write_mode=%s",
        target.qualified_name, len(markets), len(regions), total_calls, load_id, write_mode,
    )

    for market in markets:
        for region in regions:
            call_num += 1
            params = {
                "markets":    market,
                "regions":    region,
                "oddsFormat": odds_format,
                "dateFormat": date_format,
            }
            log.info("[%d/%d] market=%s  region=%s", call_num, total_calls, market, region)

            try:
                # prefer_main: the /odds pull is coverage-critical — the starter
                # tier drops Fanatics, Caesars (williamhill_us) and rebet, so use
                # the full-coverage main key first (starter stays as quota fallback).
                result = call_odds_api(ODDS_ENDPOINT, params, prefer_main=True)
            except requests.HTTPError as exc:
                log.warning("  HTTP error for market=%s region=%s: %s — skipping", market, region, exc)
                time.sleep(REQUEST_DELAY)
                continue
            except requests.RequestException as exc:
                log.warning("  Request failed for market=%s region=%s: %s — skipping", market, region, exc)
                time.sleep(REQUEST_DELAY)
                continue

            events: list[dict] = result.payload if isinstance(result.payload, list) else []
            log.info("  %d event(s) with odds returned", len(events))

            if dry_run:
                log.info(
                    "  [DRY RUN] Would buffer %d row(s) for %s",
                    len(events), target.qualified_name,
                )
                time.sleep(REQUEST_DELAY)
                continue

            for event in events:
                bookmakers = event.get("bookmakers")
                buffer.append(build_odds_row(
                    ingestion_ts         = ingestion_ts,
                    load_id              = load_id,
                    source_endpoint      = ODDS_ENDPOINT,
                    request_url          = result.url,
                    request_params       = params,
                    http_status_code     = result.status_code,
                    x_requests_used      = result.requests_used,
                    x_requests_remaining = result.requests_remaining,
                    event                = event,
                    bookmakers_count     = len(bookmakers) if isinstance(bookmakers, list) else None,
                ))
                if write_mode in ("s3", "both"):       # E11.1-W3pre: only the cols stg reads
                    mirror_buffer.append({
                        "ingestion_ts":         ingestion_ts,
                        "load_id":              load_id,
                        "request_params":       params,
                        "x_requests_used":      result.requests_used,
                        "x_requests_remaining": result.requests_remaining,
                        "raw_json":             event,
                    })

            log.info("  %d event(s) buffered (%d total)", len(events), len(buffer))
            time.sleep(REQUEST_DELAY)

    if dry_run:
        log.info("[DRY RUN] Odds ingest complete — no writes performed (load_id=%s)", load_id)
        return

    # E11.1-W3pre: Snowflake leg (skipped when write_mode='s3') + S3 lakehouse leg.
    if write_mode in ("snowflake", "both"):
        try:
            written = bulk_insert_odds_rows(conn, target=target, rows=buffer)
            log.info("Odds ingest (Snowflake) — %d row(s) in 1 bulk insert (load_id=%s)",
                     written, load_id)
        except Exception as exc:
            log.error("Snowflake bulk write failed (%d buffered row(s), load_id=%s): %s",
                      len(buffer), load_id, exc)
    if write_mode in ("s3", "both"):
        try:
            _mirror_raw_to_lakehouse("mlb_odds_raw", mirror_buffer)
            log.info("Odds ingest (S3 lakehouse) — %d row(s) mirrored (load_id=%s)",
                     len(mirror_buffer), load_id)
        except Exception as exc:
            log.error("S3 lakehouse mirror failed (%d row(s), load_id=%s): %s",
                      len(mirror_buffer), load_id, exc)


# ── Historical events helpers ─────────────────────────────────────────────────

def fetch_game_dates_with_start_times(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
) -> list[tuple[date, datetime]]:
    """
    Return (official_date, first_game_utc) for every regular-season game date
    in [start_date, end_date], ordered by date.

    Queries stg_statsapi_games, which stores game_date as timestamp_tz from the
    Stats API — the only source in this project with actual game start times.
    """
    sql = """
        SELECT
            official_date,
            MIN(CONVERT_TIMEZONE('UTC', game_date)) AS first_game_utc
        FROM baseball_data.betting.stg_statsapi_games
        WHERE official_date >= %(start_date)s::date
          AND official_date <= %(end_date)s::date
          AND game_type = 'R'
        GROUP BY official_date
        ORDER BY official_date
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "start_date": start_date.isoformat(),
            "end_date":   end_date.isoformat(),
        })
        return [(row[0], row[1]) for row in cur.fetchall()]


def run_historical_events(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
    dry_run: bool = False,
) -> None:
    """
    Fetch historical MLB events for every regular-season game date in
    [start_date, end_date] and insert them into target.

    For each game date the API snapshot timestamp (``date`` param) is set to
    1 hour before the earliest scheduled first pitch UTC. commenceTimeFrom /
    commenceTimeTo are scoped to the full calendar date so only that day's
    games are returned.

    The historical endpoint wraps its event array in {"data": [...]}. Only
    the inner array is stored as raw_json so stg_oddsapi_events (which does
    lateral flatten expecting an array) works without any schema changes.
    """
    log.info(
        "Querying game dates with start times: %s → %s", start_date, end_date
    )
    game_dates = fetch_game_dates_with_start_times(conn, start_date, end_date)

    if not game_dates:
        log.warning(
            "No regular-season game dates found in %s – %s — nothing to ingest",
            start_date, end_date,
        )
        return

    total = len(game_dates)
    log.info(
        "Historical events ingest: %d game date(s) → %s",
        total, target.qualified_name,
    )

    for idx, (game_date, first_game_utc) in enumerate(game_dates, start=1):
        load_id      = str(uuid.uuid4())
        ingestion_ts = datetime.now(tz=timezone.utc)

        # Ensure first_game_utc is timezone-aware (Snowflake connector may
        # return a naive datetime for timestamp_tz depending on driver version).
        if first_game_utc.tzinfo is None:
            first_game_utc = first_game_utc.replace(tzinfo=timezone.utc)

        snapshot_dt  = first_game_utc - timedelta(hours=1)
        snapshot_str = format_iso_utc(snapshot_dt)

        # Scope response to this calendar date in ET.
        # MLB games can start as late as ~10 pm ET (03:00 UTC next day).
        # Using UTC midnight-to-midnight would silently drop any game that
        # starts after 00:00 UTC (i.e. after 8 pm ET in summer / 7 pm ET in
        # winter). Extending day_end to 05:00 UTC the following day covers the
        # full ET calendar day including the latest possible West Coast starts.
        day_start = datetime(
            game_date.year, game_date.month, game_date.day,
            0, 0, 0, tzinfo=timezone.utc,
        )
        next_day = game_date + timedelta(days=1)
        day_end = datetime(
            next_day.year, next_day.month, next_day.day,
            4, 59, 59, tzinfo=timezone.utc,
        )

        params: dict = {
            "date":             snapshot_str,
            "commenceTimeFrom": format_iso_utc(day_start),
            "commenceTimeTo":   format_iso_utc(day_end),
            "dateFormat":       "iso",
        }

        log.info(
            "[%d/%d] %s  snapshot=%s  first_pitch=%s",
            idx, total, game_date, snapshot_str, format_iso_utc(first_game_utc),
        )

        try:
            result = call_odds_api(HIST_EVENTS_ENDPOINT, params)
        except requests.HTTPError as exc:
            log.warning("  HTTP error for %s: %s — skipping", game_date, exc)
            time.sleep(REQUEST_DELAY)
            continue
        except requests.RequestException as exc:
            log.warning("  Request failed for %s: %s — skipping", game_date, exc)
            time.sleep(REQUEST_DELAY)
            continue

        # Historical endpoint returns {"timestamp":..., "data":[...]}; extract
        # just the array so the staging model's lateral flatten works unchanged.
        payload = result.payload
        if isinstance(payload, dict):
            events_array = payload.get("data", [])
        elif isinstance(payload, list):
            events_array = payload  # defensive: live-style response
        else:
            events_array = []

        event_count = len(events_array)
        log.info("  %d event(s) in response", event_count)

        if dry_run:
            log.info(
                "  [DRY RUN] Would insert 1 row to %s (%d event(s) in payload)",
                target.qualified_name, event_count,
            )
            time.sleep(REQUEST_DELAY)
            continue

        try:
            insert_event_row(
                conn,
                target               = target,
                ingestion_ts         = ingestion_ts,
                load_id              = load_id,
                source_endpoint      = HIST_EVENTS_ENDPOINT,
                request_url          = result.url,
                request_params       = params,
                http_status_code     = result.status_code,
                x_requests_used      = result.requests_used,
                x_requests_remaining = result.requests_remaining,
                raw_json             = events_array,
                event_id             = None,
                sport_key            = None,
                sport_title          = None,
                commence_time        = None,
                home_team            = None,
                away_team            = None,
            )
            log.info(
                "  Inserted — %d event(s), load_id=%s", event_count, load_id,
            )
        except Exception as exc:
            log.error("  Snowflake write failed for %s: %s", game_date, exc)

        time.sleep(REQUEST_DELAY)

    log.info(
        "Historical events ingest complete — %d date(s) processed", total,
    )


# ── Historical odds helpers ───────────────────────────────────────────────────

def fetch_already_loaded_odds_combos(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
    start_date: date,
    end_date: date,
) -> set[tuple[date, str]]:
    """
    Return set of (game_date, market) pairs already present in target for this
    range. Used to skip (date, market) combos that completed in a prior run.
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
    Fetch historical odds for every regular-season game date in [start_date,
    end_date] and insert them into target.

    Uses the same snapshot strategy as run_historical_events: the ``date``
    parameter is set to 1 hour before the earliest first pitch UTC on each
    game date. This ensures the event IDs exist at the snapshot time.

    commenceTimeFrom / commenceTimeTo scope each response to that calendar
    date only. No eventIds filter is used — the time window is sufficient to
    isolate each day's games and avoids ID-stability issues across snapshots.

    One API call per (game_date, market). The historical odds endpoint returns
    {"timestamp":..., "data":[...]}; each event object in data is stored as
    its own row in target so stg_oddsapi_odds can flatten raw_json:bookmakers
    without schema changes.

    Idempotent: (game_date, market) pairs already present in target are skipped.
    """
    log.info("Querying game dates with start times: %s → %s", start_date, end_date)
    game_dates = fetch_game_dates_with_start_times(conn, start_date, end_date)

    if not game_dates:
        log.warning(
            "No regular-season game dates found in %s – %s — nothing to ingest",
            start_date, end_date,
        )
        return

    if dry_run:
        log.info("[DRY RUN] Skipping idempotency check.")
        already_loaded: set[tuple[date, str]] = set()
    elif force:
        log.info("--force: skipping already-loaded check, all dates will be re-fetched")
        already_loaded = set()
    else:
        log.info("Checking for already-loaded (game_date, market) pairs ...")
        already_loaded = fetch_already_loaded_odds_combos(conn, target, start_date, end_date)
        if already_loaded:
            log.info("  %d (game_date, market) pair(s) already loaded — will skip", len(already_loaded))

    markets       = DEFAULT_MARKETS
    total_dates   = len(game_dates)
    total_calls   = total_dates * len(markets)
    load_id       = str(uuid.uuid4())
    call_num      = 0
    rows_inserted = 0

    log.info(
        "Historical odds ingest: %d game date(s) × %d market(s) = %d call(s) → %s  load_id=%s",
        total_dates, len(markets), total_calls, target.qualified_name, load_id,
    )

    for game_date, first_game_utc in game_dates:
        if first_game_utc.tzinfo is None:
            first_game_utc = first_game_utc.replace(tzinfo=timezone.utc)

        # Same snapshot as historical-events: 1 hour before first pitch.
        # Ensures the events exist in the API at the snapshot time.
        snapshot_dt  = first_game_utc - timedelta(hours=1)
        snapshot_str = format_iso_utc(snapshot_dt)

        day_start = datetime(
            game_date.year, game_date.month, game_date.day,
            0, 0, 0, tzinfo=timezone.utc,
        )
        next_day = game_date + timedelta(days=1)
        day_end = datetime(
            next_day.year, next_day.month, next_day.day,
            4, 59, 59, tzinfo=timezone.utc,
        )

        ingestion_ts = datetime.now(tz=timezone.utc)
        # Buffer every event across this date's markets, then write ONCE per date
        # (one temp load + one PARSE_JSON INSERT-SELECT). The date is a natural resume
        # checkpoint: a crash only loses the in-progress date, and the (date, market)
        # idempotency skip re-fetches it on the next run since nothing was written.
        date_buffer: list[tuple] = []

        for market in markets:
            call_num += 1

            if (game_date, market) in already_loaded:
                log.info(
                    "[%d/%d] %s  market=%s — already loaded, skipping",
                    call_num, total_calls, game_date, market,
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
                    log.info("  --force: deleted %d existing row(s) for %s market=%s", deleted, game_date, market)

            params: dict = {
                "date":             snapshot_str,
                "markets":          market,
                "regions":          ",".join(DEFAULT_REGIONS),
                "oddsFormat":       DEFAULT_ODDS_FORMAT,
                "dateFormat":       DEFAULT_DATE_FORMAT,
                "commenceTimeFrom": format_iso_utc(day_start),
                "commenceTimeTo":   format_iso_utc(day_end),
            }

            log.info(
                "[%d/%d] %s  market=%s  snapshot=%s",
                call_num, total_calls, game_date, market, snapshot_str,
            )

            try:
                result = call_odds_api(HIST_ODDS_ENDPOINT, params)
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

            payload = result.payload
            if isinstance(payload, dict):
                data_array = payload.get("data", [])
            elif isinstance(payload, list):
                data_array = payload
            else:
                data_array = []

            if not data_array:
                log.info("  No data in response — skipping insert")
                time.sleep(REQUEST_DELAY)
                continue

            log.info("  %d event(s) in response", len(data_array))

            if dry_run:
                log.info(
                    "  [DRY RUN] Would insert %d row(s) to %s",
                    len(data_array), target.qualified_name,
                )
                rows_inserted += len(data_array)
                time.sleep(REQUEST_DELAY)
                continue

            for event_obj in data_array:
                bookmakers = event_obj.get("bookmakers")
                date_buffer.append(build_odds_row(
                    ingestion_ts         = ingestion_ts,
                    load_id              = load_id,
                    source_endpoint      = HIST_ODDS_ENDPOINT,
                    request_url          = result.url,
                    request_params       = params,
                    http_status_code     = result.status_code,
                    x_requests_used      = result.requests_used,
                    x_requests_remaining = result.requests_remaining,
                    event                = event_obj,
                    bookmakers_count     = len(bookmakers) if isinstance(bookmakers, list) else None,
                ))

            log.info("  %d event(s) buffered for %s", len(data_array), game_date)
            time.sleep(REQUEST_DELAY)

        # Single bulk write per game-date (skipped when dry-run buffered nothing).
        if date_buffer:
            try:
                written = bulk_insert_odds_rows(conn, target=target, rows=date_buffer)
                rows_inserted += written
                log.info("  %s — flushed %d row(s) in 1 bulk insert", game_date, written)
            except Exception as exc:
                log.error("  Snowflake bulk write failed for %s (%d buffered row(s)): %s",
                          game_date, len(date_buffer), exc)

    log.info(
        "Historical odds ingest complete — %d date(s), %d call(s), %d row(s)  load_id=%s",
        total_dates, call_num, rows_inserted, load_id,
    )
    print(f"rows_inserted={rows_inserted}", flush=True)


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest MLB odds data from The Odds API into Snowflake.",
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
            "Write target: 'prod' uses oddsapi schema (default); "
            "'dev' redirects all writes to oddsapi_dev. "
            "Must be placed before the subcommand name."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    events_parser = sub.add_parser(
        "events",
        help="Fetch upcoming MLB events and ingest into the configured events table.",
    )
    events_parser.add_argument(
        "--commence-time-from",
        default=None,
        metavar="ISO8601",
        help=(
            "Lower bound for event commence time in ISO 8601 UTC format "
            "(e.g. 2026-04-22T00:00:00Z). Defaults to today at 00:00:00Z."
        ),
    )
    events_parser.add_argument(
        "--commence-time-to",
        default=None,
        metavar="ISO8601",
        help=(
            f"Upper bound for event commence time in ISO 8601 UTC format. "
            f"Defaults to {DEFAULT_EVENTS_WINDOW_DAYS} days from today at 00:00:00Z."
        ),
    )

    hist_events_parser = sub.add_parser(
        "historical-events",
        help=(
            "Fetch historical MLB events for each regular-season game date "
            "and ingest into the configured events table."
        ),
    )
    hist_events_parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=HIST_DEFAULT_START.isoformat(),
        help=(
            f"First game date to fetch, inclusive (default: {HIST_DEFAULT_START}). "
            "Pass a later date to resume an interrupted backfill."
        ),
    )
    hist_events_parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=HIST_DEFAULT_END.isoformat(),
        help=(
            f"Last game date to fetch, inclusive (default: {HIST_DEFAULT_END} — "
            "the day before live odds ingestion began)."
        ),
    )

    hist_odds_parser = sub.add_parser(
        "historical-odds",
        help=(
            "Fetch historical MLB odds for events from mlb_events_raw and "
            "ingest into the configured odds table. Requires historical-events "
            "to have been run first for the target date range."
        ),
    )
    hist_odds_parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=HIST_ODDS_DEFAULT_START.isoformat(),
        help=(
            f"First event commence date to include, inclusive "
            f"(default: {HIST_ODDS_DEFAULT_START}). "
            "Pass a later date to resume an interrupted backfill."
        ),
    )
    hist_odds_parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=HIST_DEFAULT_END.isoformat(),
        help=(
            f"Last event commence date to include, inclusive "
            f"(default: {HIST_DEFAULT_END})."
        ),
    )
    hist_odds_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch dates that are already present in the odds table (bypasses idempotency check).",
    )

    odds_parser = sub.add_parser(
        "odds",
        help="Fetch MLB odds and ingest into the configured odds table.",
    )
    odds_parser.add_argument(
        "--markets",
        nargs="+",
        default=DEFAULT_MARKETS,
        metavar="MARKET",
        help=f"Odds market keys to fetch (default: {' '.join(DEFAULT_MARKETS)}).",
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

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.target == "dev":
        os.environ["ODDS_TARGET_SCHEMA"] = "oddsapi_dev"

    dry_run = args.dry_run
    if dry_run:
        log.info("[DRY RUN] No Snowflake writes will be performed.")

    events_target, odds_target = resolve_targets()
    log.info(
        "Connecting to Snowflake  events→%s  odds→%s",
        events_target.qualified_name,
        odds_target.qualified_name,
    )
    conn = get_snowflake_connection(events_target.database, events_target.schema)

    try:
        if args.command == "events":
            window_from, window_to = default_window(days=DEFAULT_EVENTS_WINDOW_DAYS)
            run_events(
                conn,
                events_target,
                commence_time_from = args.commence_time_from or window_from,
                commence_time_to   = args.commence_time_to   or window_to,
                dry_run            = dry_run,
            )

        elif args.command == "historical-events":
            run_historical_events(
                conn,
                events_target,
                start_date = date.fromisoformat(args.start_date),
                end_date   = date.fromisoformat(args.end_date),
                dry_run    = dry_run,
            )

        elif args.command == "historical-odds":
            run_historical_odds(
                conn,
                odds_target,
                start_date = date.fromisoformat(args.start_date),
                end_date   = date.fromisoformat(args.end_date),
                force      = args.force,
                dry_run    = dry_run,
            )

        elif args.command == "odds":
            run_odds(
                conn,
                odds_target,
                markets     = args.markets,
                regions     = args.regions,
                odds_format = args.odds_format,
                date_format = args.date_format,
                dry_run     = dry_run,
            )

    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
