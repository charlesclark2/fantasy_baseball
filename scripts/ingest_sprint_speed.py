"""
ingest_sprint_speed.py
----------------------
Fetches the Baseball Savant sprint speed leaderboard and loads it to Snowflake.

Sprint speed (ft/s) is Statcast's actual measured sprint speed — distinct from
the FanGraphs 'Spd' speed score (a 1-10 derived value). This leaderboard is
updated throughout the season as more HP-to-2B sprint attempts are recorded.

Target table: baseball_data.savant.sprint_speed_raw
  - Grain: one row per player × season × snapshot_date
  - snapshot_date is today's date (the day this script runs)
  - Existing rows for the same (player_mlbam_id, season, snapshot_date) are
    deleted and replaced, so reruns are fully idempotent.

Snowflake authentication (same pattern as other ingestion scripts):
    SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER / SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH          path to RSA PEM key (preferred)
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE    (optional, omit if key is unencrypted)
    SNOWFLAKE_ROLE                      (optional)
    SNOWFLAKE_PASSWORD                  fallback when no private key is set

Usage:
    # Current season
    uv run python scripts/ingest_sprint_speed.py --season 2026

    # Backfill a prior season
    uv run python scripts/ingest_sprint_speed.py --season 2024

    # Dry-run (print row count, do not write)
    uv run python scripts/ingest_sprint_speed.py --season 2026 --dry-run
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import time
from datetime import date

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

SAVANT_SPRINT_SPEED_URL = "https://baseballsavant.mlb.com/leaderboard/sprint_speed"
REQUEST_TIMEOUT = 60
MAX_RETRIES = 3
RETRY_BACKOFF = 10

TABLE_FQN = "baseball_data.savant.sprint_speed_raw"
TABLE_NAME = "SPRINT_SPEED_RAW"
DB = "BASEBALL_DATA"
SCHEMA = "SAVANT"

# Savant CSV column names → our Snowflake column names (all uppercase)
COLUMN_MAP = {
    "player_id":        "PLAYER_MLBAM_ID",
    "last_name, first_name": None,  # we'll derive PLAYER_NAME below
    "last_name":        None,
    "first_name":       None,
    "team":             "TEAM_ABBREV",
    "age":              "AGE",
    "sprint_speed":     "SPRINT_SPEED_FTS",
    "competitive_runs": "COMPETITIVE_RUNS",
    "hp_to_1b":         "HP_TO_1B",
    "hp_to_2b":         "HP_TO_2B",
    "pos":              "POSITION",
}


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
        "database":  DB,
        "schema":    SCHEMA,
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(private_key_path, passphrase)
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


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_sprint_speed(season: int) -> pd.DataFrame:
    """Fetch the sprint speed leaderboard CSV from Baseball Savant."""
    params = {
        "min_competitive": "0",
        "year": str(season),
        "team": "",
        "position": "",
        "display": "n",
        "csv": "true",
    }
    session = requests.Session()
    session.headers.update({"User-Agent": "baseball-ingest/1.0 (research)"})

    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(SAVANT_SPRINT_SPEED_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            text = resp.text.strip()
            if not text or text.lower() == "null":
                log.warning("Savant returned empty response for season %d", season)
                return pd.DataFrame()
            df = pd.read_csv(io.StringIO(text), dtype=str, encoding_errors="replace")
            df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]
            log.info("Fetched %d rows for season %d", len(df), season)
            return df
        except requests.Timeout:
            log.warning("[%d/%d] Request timed out", attempt, MAX_RETRIES)
        except requests.HTTPError as exc:
            log.warning("[%d/%d] HTTP %s", attempt, MAX_RETRIES, exc.response.status_code)
        except Exception as exc:
            log.warning("[%d/%d] Unexpected error: %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            log.info("Retrying in %ds…", backoff)
            time.sleep(backoff)
            backoff *= 2

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed fetching sprint speed for {season}")


# ── Transform ──────────────────────────────────────────────────────────────────

def transform(df: pd.DataFrame, season: int, snapshot_date: date) -> pd.DataFrame:
    """Normalize column names, add season and snapshot_date, attach raw_json."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # Build player name from last_name / first_name if the combined column isn't present
    if "last_name, first_name" in df.columns:
        df["PLAYER_NAME"] = df["last_name, first_name"]
    elif "last_name" in df.columns and "first_name" in df.columns:
        df["PLAYER_NAME"] = df["first_name"].str.strip() + " " + df["last_name"].str.strip()
    else:
        df["PLAYER_NAME"] = None

    # Attach raw_json before renaming so every source column is captured
    df["RAW_JSON"] = df.apply(lambda row: json.dumps(row.to_dict()), axis=1)

    # Map known columns
    rename: dict[str, str] = {}
    for src, dst in COLUMN_MAP.items():
        if dst and src in df.columns:
            rename[src] = dst
    df = df.rename(columns=rename)

    df["SEASON"] = season
    df["SNAPSHOT_DATE"] = snapshot_date.isoformat()

    keep = [
        "PLAYER_MLBAM_ID", "PLAYER_NAME", "TEAM_ABBREV", "AGE", "POSITION",
        "SPRINT_SPEED_FTS", "COMPETITIVE_RUNS", "HP_TO_1B", "HP_TO_2B",
        "SEASON", "SNAPSHOT_DATE", "RAW_JSON",
    ]
    existing = [c for c in keep if c in df.columns]
    return df[existing]


# ── Load ───────────────────────────────────────────────────────────────────────

def load(
    conn: snowflake.connector.SnowflakeConnection,
    df: pd.DataFrame,
    season: int,
    snapshot_date: date,
) -> int:
    """Delete existing snapshot rows then bulk-insert. Returns row count inserted."""
    with conn.cursor() as cur:
        cur.execute(
            f"DELETE FROM {TABLE_FQN} WHERE SEASON = %s AND SNAPSHOT_DATE = %s",
            (season, snapshot_date.isoformat()),
        )
        deleted = cur.rowcount

    if deleted:
        log.info("Deleted %d existing rows for season=%d snapshot=%s", deleted, season, snapshot_date)

    # RAW_JSON must go in as a VARIANT — use a VARCHAR temp table then PARSE_JSON
    # to avoid PARSE_JSON in VALUES, which fails with executemany.
    tmp = f"sprint_speed_tmp_{snapshot_date.strftime('%Y%m%d')}"

    # Build tmp table matching df columns, with RAW_JSON as VARCHAR
    col_defs = ", ".join(
        f"{c} VARCHAR" if c != "RAW_JSON" else f"{c} VARCHAR"
        for c in df.columns
    )
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMPORARY TABLE {tmp} ({col_defs})")

    success, _, _, _ = write_pandas(
        conn,
        df,
        table_name=tmp,
        database=DB,
        schema=SCHEMA,
        quote_identifiers=False,
    )
    if not success:
        raise RuntimeError("write_pandas to temp table failed")

    non_json_cols = [c for c in df.columns if c != "RAW_JSON"]
    col_list = ", ".join(non_json_cols)
    src_list = ", ".join(f"src.{c}" for c in non_json_cols)

    insert_sql = f"""
        INSERT INTO {TABLE_FQN} ({col_list}, RAW_JSON)
        SELECT {src_list}, PARSE_JSON(src.RAW_JSON)
        FROM {tmp} src
    """
    with conn.cursor() as cur:
        cur.execute(insert_sql)
        inserted = cur.rowcount

    log.info("Inserted %d rows for season=%d snapshot=%s", inserted, season, snapshot_date)
    return inserted


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest Baseball Savant sprint speed leaderboard into Snowflake."
    )
    parser.add_argument(
        "--season",
        type=int,
        default=date.today().year,
        help="Season year to fetch (default: current year)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform but do not write to Snowflake",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    snapshot_date = date.today()

    raw_df = fetch_sprint_speed(args.season)
    if raw_df.empty:
        log.info("No data returned — nothing to load")
        return

    df = transform(raw_df, args.season, snapshot_date)
    log.info("Transformed to %d rows, %d columns", len(df), len(df.columns))

    if args.dry_run:
        log.info("Dry-run mode — skipping Snowflake write")
        print(df.head())
        return

    conn = get_snowflake_connection()
    try:
        load(conn, df, args.season, snapshot_date)
    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
