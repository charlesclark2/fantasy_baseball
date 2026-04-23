"""
savant_ingestion.py
-------------------
Ingests MLB Statcast data from Baseball Savant into Snowflake.

Queries are chunked by single calendar day to stay under Baseball Savant's
25,000-row per-request limit. Each day is deleted from the target table before
re-insertion, so reruns are fully idempotent.

Extensibility: new Baseball Savant endpoints (sprint speed, expected stats,
batting stats, etc.) can be added by defining a new StatcastEndpoint instance
in the ENDPOINTS registry — no other code changes are required.

Subcommands:
    batter_pitches   Pitch-level data → baseball_data.savant.batter_pitches

Target table overrides (env vars):
    SAVANT_TARGET_DATABASE          (default: baseball_data)
    SAVANT_TARGET_SCHEMA            (default: savant)
    SAVANT_BATTER_PITCHES_TABLE     (default: batter_pitches)

Snowflake authentication (same pattern as odds_api_ingestion.py):
    SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH          path to RSA PEM key (preferred)
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE    (optional, omit if key is unencrypted)
    SNOWFLAKE_ROLE                      (optional)
    SNOWFLAKE_PASSWORD                  fallback when no private key is set

Usage:
    # Auto-detect last loaded date; ingest everything up through yesterday
    uv run savant_ingestion.py batter_pitches

    # Explicit date range (use for initial backfill)
    uv run savant_ingestion.py batter_pitches --start-date 2026-03-20 --end-date 2026-04-21
"""

import argparse
import dataclasses
import io
import logging
import os
import time
from datetime import date, timedelta
from typing import Iterator

import pandas as pd
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
from snowflake.connector.pandas_tools import write_pandas

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SAVANT_CSV_URL  = "https://baseballsavant.mlb.com/statcast_search/csv"
REQUEST_TIMEOUT = 90       # seconds; Baseball Savant can be slow
REQUEST_DELAY   = 2.0      # seconds between requests
MAX_RETRIES     = 3
RETRY_BACKOFF   = 10       # seconds; doubles on each retry


# ── Data structures ────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class SnowflakeTarget:
    database: str
    schema: str
    table: str

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table}"


@dataclasses.dataclass(frozen=True)
class StatcastEndpoint:
    """One Baseball Savant endpoint plus its Snowflake write target.

    base_params:  query parameters sent on every request for this endpoint.
                  game_date_gt, game_date_lt, and hfSea are injected per-day
                  by the runner — do not include them here.
    date_column:  CSV column holding the game date; used for idempotency deletes
                  and auto-detection of the last loaded date.
    """
    name: str
    base_params: dict
    target: SnowflakeTarget
    date_column: str = "game_date"


# ── Endpoint registry ──────────────────────────────────────────────────────────
# To add a new endpoint:
#   1. Define a SnowflakeTarget pointing at the destination table.
#   2. Define a StatcastEndpoint with the appropriate base_params.
#   3. Add it to ENDPOINTS.

BATTER_PITCHES = StatcastEndpoint(
    name        = "batter_pitches",
    base_params = {
        "all":         "true",
        "hfGT":        "R|",       # regular season only
        "player_type": "pitcher",  # pitcher view returns every pitch thrown
        "type":        "details",  # trigger CSV download (not HTML)
        "min_pitches": "0",
        "min_results": "0",
        "min_pas":     "0",
        "sort_col":    "pitches",
        "sort_order":  "desc",
    },
    target = SnowflakeTarget(
        database = os.environ.get("SAVANT_TARGET_DATABASE", "baseball_data"),
        schema   = os.environ.get("SAVANT_TARGET_SCHEMA",   "savant"),
        table    = os.environ.get("SAVANT_BATTER_PITCHES_TABLE", "batter_pitches"),
    ),
    date_column = "game_date",
)

ENDPOINTS: dict[str, StatcastEndpoint] = {
    BATTER_PITCHES.name: BATTER_PITCHES,
}


# ── Snowflake connection ───────────────────────────────────────────────────────

def _load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding           = Encoding.DER,
        format             = PrivateFormat.PKCS8,
        encryption_algorithm = NoEncryption(),
    )


def get_snowflake_connection(target: SnowflakeTarget) -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  target.database,
        "schema":    target.schema,
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        log.info("Authenticating with private key: %s", private_key_path)
        passphrase      = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
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


# ── Auto-detect last loaded date ───────────────────────────────────────────────

def get_last_loaded_date(
    conn: snowflake.connector.SnowflakeConnection,
    endpoint: StatcastEndpoint,
) -> date | None:
    """Return the most recent game date already in the target table, or None."""
    sql = (
        f"SELECT MAX({endpoint.date_column}::date) "
        f"FROM {endpoint.target.qualified_name}"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return row[0] if (row and row[0]) else None


# ── Table column inspection ────────────────────────────────────────────────────

def get_table_columns(
    conn: snowflake.connector.SnowflakeConnection,
    target: SnowflakeTarget,
) -> set[str]:
    """Return the set of uppercase column names for the target table."""
    sql = """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (target.schema.upper(), target.table.upper()))
        return {row[0].upper() for row in cur.fetchall()}


# ── CSV fetch ──────────────────────────────────────────────────────────────────

def _date_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def fetch_day(
    session: requests.Session,
    endpoint: StatcastEndpoint,
    day: date,
) -> pd.DataFrame:
    """Fetch one calendar day from Baseball Savant; return a DataFrame.

    Returns an empty DataFrame when the day has no game data.
    Retries up to MAX_RETRIES times with exponential backoff on failure.
    """
    params = {
        **endpoint.base_params,
        "hfSea":        f"{day.year}|",
        "game_date_gt": _date_str(day),
        "game_date_lt": _date_str(day),
    }

    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SAVANT_CSV_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            # Baseball Savant returns the literal string "null" when no data exists.
            text = resp.text.strip()
            if not text or text.lower() == "null":
                return pd.DataFrame()

            # utf-8-sig transparently strips the UTF-8 BOM present in some responses.
            df = pd.read_csv(
                io.StringIO(text),
                dtype            = str,
                encoding_errors  = "replace",
                encoding         = "utf-8-sig",
            )
            # Drop the trailing unnamed column Baseball Savant occasionally emits.
            df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
            return df

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

    log.error("  All %d attempts failed for %s — skipping", MAX_RETRIES, _date_str(day))
    return pd.DataFrame()


# ── Snowflake write ────────────────────────────────────────────────────────────

def load_day(
    conn: snowflake.connector.SnowflakeConnection,
    endpoint: StatcastEndpoint,
    day: date,
    df: pd.DataFrame,
    table_columns: set[str],
) -> int:
    """Delete the day's existing rows, then bulk-insert df. Returns row count inserted."""
    date_str = _date_str(day)

    # Uppercase to match Snowflake column names; drop any CSV columns not in the table.
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    extra = [c for c in df.columns if c not in table_columns]
    if extra:
        log.warning("  Dropping %d CSV column(s) not in target table: %s", len(extra), extra)
        df = df.drop(columns=extra)

    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {endpoint.target.qualified_name} "
            f"WHERE {endpoint.date_column.upper()}::date = %s",
            (date_str,),
        )
        deleted = cur.rowcount
    if deleted:
        log.info("  Deleted %d existing row(s) for %s", deleted, date_str)

    success, _, nrows, _ = write_pandas(
        conn,
        df,
        table_name        = endpoint.target.table.upper(),
        database          = endpoint.target.database.upper(),
        schema            = endpoint.target.schema.upper(),
        quote_identifiers = False,
    )
    if not success:
        raise RuntimeError(f"write_pandas failed for {date_str}")

    return nrows


# ── Date iteration ─────────────────────────────────────────────────────────────

def date_range(start: date, end: date) -> Iterator[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


# ── Main runner ────────────────────────────────────────────────────────────────

def run_endpoint(
    conn: snowflake.connector.SnowflakeConnection,
    endpoint: StatcastEndpoint,
    start_date: date,
    end_date: date,
) -> None:
    total_days   = (end_date - start_date).days + 1
    loaded_days  = 0
    skipped_days = 0
    total_rows   = 0

    log.info(
        "Savant ingest → %s  [%s → %s]  %d day(s) to process",
        endpoint.target.qualified_name,
        _date_str(start_date),
        _date_str(end_date),
        total_days,
    )

    table_columns = get_table_columns(conn, endpoint.target)
    session       = requests.Session()
    session.headers.update({"User-Agent": "baseball-ingest/1.0 (research)"})

    for day in date_range(start_date, end_date):
        log.info("[%s] Fetching…", _date_str(day))
        df = fetch_day(session, endpoint, day)

        if df.empty:
            log.info("[%s] No data — skipping", _date_str(day))
            skipped_days += 1
            time.sleep(REQUEST_DELAY)
            continue

        nrows = load_day(conn, endpoint, day, df, table_columns)
        log.info("[%s] Loaded %d row(s)", _date_str(day), nrows)
        loaded_days += 1
        total_rows  += nrows
        time.sleep(REQUEST_DELAY)

    log.info(
        "Ingest complete — %d day(s) loaded | %d skipped (no data) | %d total rows",
        loaded_days, skipped_days, total_rows,
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest MLB Statcast data from Baseball Savant into Snowflake.",
    )
    sub = parser.add_subparsers(dest="endpoint", required=True)

    for ep_name in ENDPOINTS:
        ep_parser = sub.add_parser(ep_name, help=f"Ingest {ep_name} data.")
        ep_parser.add_argument(
            "--start-date",
            metavar="YYYY-MM-DD",
            default=None,
            help=(
                "First date to ingest, inclusive. "
                "Defaults to the day after the latest date already in the target table."
            ),
        )
        ep_parser.add_argument(
            "--end-date",
            metavar="YYYY-MM-DD",
            default=None,
            help="Last date to ingest, inclusive. Defaults to yesterday.",
        )

    return parser


def main() -> None:
    args      = build_parser().parse_args()
    endpoint  = ENDPOINTS[args.endpoint]
    conn      = get_snowflake_connection(endpoint.target)
    yesterday = date.today() - timedelta(days=1)

    end_date = date.fromisoformat(args.end_date) if args.end_date else yesterday

    if args.start_date:
        start_date = date.fromisoformat(args.start_date)
    else:
        last_loaded = get_last_loaded_date(conn, endpoint)
        if last_loaded:
            start_date = last_loaded + timedelta(days=1)
            log.info(
                "Auto-detected last loaded date: %s → starting from %s",
                last_loaded, start_date,
            )
        else:
            raise SystemExit(
                "Target table appears empty and --start-date was not provided. "
                "Pass --start-date YYYY-MM-DD to specify where to begin."
            )

    if start_date > end_date:
        log.info(
            "Nothing to ingest: start %s is after end %s",
            _date_str(start_date), _date_str(end_date),
        )
        conn.close()
        return

    try:
        run_endpoint(conn, endpoint, start_date, end_date)
    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
