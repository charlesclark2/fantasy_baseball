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
import pathlib
import sys
import tempfile
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
# INC-13: re-fetch the trailing window on every incremental run so late-arriving
# games are absorbed.  Two failure modes this guards against:
#   (a) UTC-boundary: a game starts before midnight ET but Savant hasn't published
#       its data yet when the ingest runs; the lookback re-checks that date next day.
#   (b) Postponed/makeup games: Savant files them under the ORIGINAL official_date,
#       which the ingest already passed by the time the game is actually played.
# Matches the LOOKBACK_DAYS in ingest_statcast_to_s3.py (the S3 path).
LOOKBACK_DAYS   = 14


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

    # All retries exhausted on a TRANSPORT failure (timeout / HTTP / unexpected).
    # Do NOT return an empty frame here: a fetch error and a legitimately empty day
    # (handled above via the "null"/empty-body check, which is the only path that
    # may return an empty frame) must be distinguishable. Collapsing both to "no
    # data — skipping" is exactly what let a broken ingest exit green for days.
    # Raising propagates to run_endpoint → the op fails and the Dagster run goes red.
    raise RuntimeError(
        f"Savant fetch failed for {_date_str(day)} after {MAX_RETRIES} attempts "
        f"(transport error, not an empty day)"
    )


# ── Column normalization ───────────────────────────────────────────────────────

def _normalize_df(df: pd.DataFrame, table_columns: set[str]) -> pd.DataFrame:
    """Uppercase columns; emit loud warning + drop any CSV columns not in the table."""
    df = df.copy()
    df.columns = [c.upper() for c in df.columns]
    extra = [c for c in df.columns if c not in table_columns]
    if extra:
        # ALERT-loud-but-continue: print to stderr so this surfaces in Dagster logs and
        # operator terminals even when log level is above WARNING. Silently dropping a new
        # Savant field is how useful data (e.g. miss_distance) disappears for a full season.
        banner = (
            "\n" + "=" * 72 + "\n"
            "ACTION NEEDED — NEW SAVANT COLUMN(S) NOT IN TARGET TABLE:\n"
            f"  {extra}\n"
            "  ALTER TABLE savant.batter_pitches ADD COLUMN <name> TEXT\n"
            "  then add to stg_batter_pitches.sql before these can be captured.\n"
            + "=" * 72 + "\n"
        )
        print(banner, file=sys.stderr)
        log.warning("Dropping %d CSV column(s) not in target table: %s", len(extra), extra)
        df = df.drop(columns=extra)
    return df


# ── Snowflake write ────────────────────────────────────────────────────────────

def load_day(
    conn: snowflake.connector.SnowflakeConnection,
    endpoint: StatcastEndpoint,
    day: date,
    df: pd.DataFrame,
    table_columns: set[str],
) -> int:
    """Delete the day's existing rows, then bulk-insert df. Returns row count inserted.

    Single-day path — used by tests and explicit single-date CLI runs. Production
    multi-day runs go through run_endpoint which batches all days into one write.
    """
    date_str = _date_str(day)
    df = _normalize_df(df, table_columns)

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


def batch_write(
    conn: snowflake.connector.SnowflakeConnection,
    endpoint: StatcastEndpoint,
    loaded_dates: list[date],
    combined_df: pd.DataFrame,
) -> int:
    """Delete all loaded_dates with one IN clause, then insert combined_df in a single
    write_pandas call. combined_df must already be normalized (uppercase, extras dropped).
    Returns total rows inserted.
    """
    placeholders = ", ".join(["%s"] * len(loaded_dates))
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {endpoint.target.qualified_name} "
            f"WHERE {endpoint.date_column.upper()}::date IN ({placeholders})",
            [_date_str(d) for d in loaded_dates],
        )
        deleted = cur.rowcount
    if deleted:
        log.info("Batch deleted %d existing row(s) across %d date(s)", deleted, len(loaded_dates))

    success, _, nrows, _ = write_pandas(
        conn,
        combined_df,
        table_name        = endpoint.target.table.upper(),
        database          = endpoint.target.database.upper(),
        schema            = endpoint.target.schema.upper(),
        quote_identifiers = False,
    )
    if not success:
        raise RuntimeError("write_pandas failed for batch")

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
    skipped_days = 0

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

    # ── Phase 1: fetch all days from Baseball Savant (no warehouse activity) ───
    # All HTTP work happens here so the warehouse is idle during the slow fetch loop.
    frames: list[pd.DataFrame] = []
    loaded_dates: list[date]   = []

    for day in date_range(start_date, end_date):
        log.info("[%s] Fetching…", _date_str(day))
        df = fetch_day(session, endpoint, day)

        if df.empty:
            log.info("[%s] No data — skipping", _date_str(day))
            skipped_days += 1
            time.sleep(REQUEST_DELAY)
            continue

        frames.append(_normalize_df(df, table_columns))
        loaded_dates.append(day)
        log.info("[%s] Fetched %d row(s)", _date_str(day), len(frames[-1]))
        time.sleep(REQUEST_DELAY)

    if not frames:
        log.info(
            "Ingest complete — 0 day(s) loaded | %d skipped (no data) | 0 total rows",
            skipped_days,
        )
        return

    # ── Phase 2: batch write to Snowflake via a temp Parquet staging file ──────
    # One DELETE IN (...) + one write_pandas instead of N per-day round-trips.
    combined = pd.concat(frames, ignore_index=True)
    del frames  # free memory before writing to disk

    fd, tmp_name = tempfile.mkstemp(suffix=".parquet", prefix="savant_ingest_")
    os.close(fd)  # mkstemp holds an open fd; close it so pandas can write the file
    tmp_path = pathlib.Path(tmp_name)

    try:
        log.info(
            "Staging %d row(s) across %d date(s) to temp Parquet: %s",
            len(combined), len(loaded_dates), tmp_path,
        )
        combined.to_parquet(tmp_path, index=False)
        del combined  # free memory; read back cleanly from Parquet

        batch_df   = pd.read_parquet(tmp_path)
        log.info("Batch writing to Snowflake…")
        total_rows = batch_write(conn, endpoint, loaded_dates, batch_df)
    finally:
        tmp_path.unlink(missing_ok=True)
        log.info("Removed temp Parquet: %s", tmp_path)

    log.info(
        "Ingest complete — %d day(s) loaded | %d skipped (no data) | %d total rows",
        len(loaded_dates), skipped_days, total_rows,
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
            start_date = last_loaded - timedelta(days=LOOKBACK_DAYS)
            log.info(
                "Auto-detected last loaded date: %s → starting from %s (%d-day lookback)",
                last_loaded, start_date, LOOKBACK_DAYS,
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
