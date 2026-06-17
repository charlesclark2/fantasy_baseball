"""
backfill_historical_odds_snapshots.py
--------------------------------------
Backfills historical intraday odds snapshots for MLB regular-season game dates
into `baseball_data.oddsapi.odds_snapshots_historical` (Card 7.P2).

For each game date × timestamp combination the script calls:
    GET /v4/historical/sports/baseball_mlb/odds
        ?apiKey=<ODDS_API_KEY>
        &date=<YYYY-MM-DDThh:mm:ssZ>
        &regions=us
        &markets=h2h,totals
        &oddsFormat=american
        &bookmakers=<bookmaker>

The historical endpoint returns odds as they existed at the given UTC timestamp.
Snapshots through the day capture the open, mid-day, and pre-game lines. Both h2h
and totals markets are requested in a single call.

Credit cost (verified live 2026-06-16): historical = 10 × [#markets] × [#regions].
We always request 2 markets (h2h,totals), so a call costs 20 credits for one region
(us), 40 for two (us,us2), etc. The #books does NOT affect cost — `--bookmaker all`
captures every book in the region for the same credits (see ALL_BOOKS below).

Usage:
    uv run backfill_historical_odds_snapshots.py \\
        --start-date 2025-03-01 \\
        --end-date   2025-10-31 \\
        --timestamps 12:00,17:00,23:00 \\
        [--bookmaker draftkings] \\
        [--region us] \\
        [--sleep-seconds 1.5] \\
        [--dry-run]

    # Pinnacle closing lines (EU region):
    uv run backfill_historical_odds_snapshots.py \\
        --start-date 2021-04-01 \\
        --end-date   2025-10-01 \\
        --timestamps 17:00,23:00 \\
        --bookmaker  pinnacle \\
        --region     eu \\
        [--sleep-seconds 1.5] \\
        [--dry-run]

    --dry-run   Prints the date range, estimated API call count, and expected
                credit cost then exits without touching the API or Snowflake.

Environment variables (from ../.env):
    ODDS_API_KEY                    Required.
    SNOWFLAKE_ACCOUNT               Required.
    SNOWFLAKE_USER                  Required.
    SNOWFLAKE_WAREHOUSE             Required.
    SNOWFLAKE_PRIVATE_KEY_PATH      Required (or SNOWFLAKE_PASSWORD).
    SNOWFLAKE_PRIVATE_KEY_PASSPHRASE  Optional.
    SNOWFLAKE_ROLE                  Optional.
"""

import argparse
import logging
import os
import sys
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

ODDS_API_BASE_URL  = "https://api.the-odds-api.com/v4"
HIST_ENDPOINT      = "/historical/sports/baseball_mlb/odds"
TARGET_DB          = "baseball_data"
TARGET_SCHEMA      = "oddsapi"
TARGET_TABLE       = "odds_snapshots_historical"
TARGET_FQN         = f"{TARGET_DB}.{TARGET_SCHEMA}.{TARGET_TABLE}"

GAMES_FQN          = "baseball_data.betting.stg_statsapi_games"

DEFAULT_BOOKMAKER  = "draftkings"
DEFAULT_SLEEP      = 1.5
BATCH_SIZE         = 500     # rows per Snowflake write batch

# --parquet-out mode staging objects. Fetch writes per-date parquet locally (warehouse
# stays SUSPENDED through the whole API-bound loop), then a single PUT → COPY INTO →
# MERGE loads everything at the end (warehouse hot only for that final step).
STAGING_TBL_NAME   = "stg_odds_backfill_parquet"
STAGING_FQN        = f"{TARGET_DB}.{TARGET_SCHEMA}.{STAGING_TBL_NAME}"
STAGING_STAGE      = f"@{TARGET_DB}.{TARGET_SCHEMA}.%{STAGING_TBL_NAME}"   # the table's internal stage
PARQUET_COLS       = [
    "game_pk", "game_date", "snapshot_ts", "home_team", "away_team",
    "home_price", "away_price", "over_price", "under_price", "total_line",
    "bookmaker", "home_win_prob", "away_win_prob", "load_id",
]

# Sentinel for --bookmaker: capture EVERY book present in the requested region(s).
# The Odds API historical cost is 10 × markets × regions — it does NOT depend on the
# number of books, so one call captures ~15 us books for the same credits as one book.
# The target table's MERGE key already includes `bookmaker`, so multi-book rows coexist.
ALL_BOOKS          = "all"
# When in all-books mode, use this book to decide whether a date/snapshot is already
# covered enough to skip (it's our model target and present on most games).
COVERAGE_ANCHOR    = "bovada"

# Date-sensitive team name normalization: (oddsapi_name, effective_from_year) → statsapi_name.
# statsapi renames teams when franchises relocate; OddsAPI may lag behind.
_TEAM_RENAMES: list[tuple[str, int, str]] = [
    # (oddsapi_name,        from_season, statsapi_name)
    ("Oakland Athletics",   2025,        "Athletics"),
    ("Las Vegas Athletics", 2025,        "Athletics"),
]


def normalize_team_name(name: str, game_date_str: str) -> str:
    """Map OddsAPI team name to the name stored in statsapi for the given date."""
    try:
        season = int(game_date_str[:4])
    except (ValueError, TypeError):
        return name
    for oddsapi_name, from_season, statsapi_name in _TEAM_RENAMES:
        if name == oddsapi_name and season >= from_season:
            return statsapi_name
    return name

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TARGET_FQN} (
    game_pk          INTEGER,
    game_date        DATE          NOT NULL,
    snapshot_ts      TIMESTAMP_TZ  NOT NULL,
    home_team        VARCHAR(120)  NOT NULL,
    away_team        VARCHAR(120)  NOT NULL,
    home_price       INTEGER,
    away_price       INTEGER,
    over_price       INTEGER,
    under_price      INTEGER,
    total_line       FLOAT,
    bookmaker        VARCHAR(60)   NOT NULL,
    home_win_prob    FLOAT,
    away_win_prob    FLOAT,
    load_id          VARCHAR(100)  NOT NULL,
    loaded_at        TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP()
)
"""

# ── Implied-probability conversion ────────────────────────────────────────────

def american_to_implied_prob(odds: int | float) -> float | None:
    """Convert American moneyline odds to implied win probability (0–1)."""
    if odds is None:
        return None
    if odds == 0:
        return 0.5
    if odds < 0:
        abs_odds = abs(odds)
        return abs_odds / (abs_odds + 100)
    return 100 / (odds + 100)


# ── Snowflake helpers ─────────────────────────────────────────────────────────

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
    missing  = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing Snowflake env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  TARGET_DB,
        "schema":    TARGET_SCHEMA,
    }

    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(pk_path, passphrase)
    else:
        pw = os.environ.get("SNOWFLAKE_PASSWORD")
        if not pw:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        kwargs["password"] = pw

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


def ensure_table(conn: snowflake.connector.SnowflakeConnection) -> None:
    with conn.cursor() as cur:
        cur.execute(_CREATE_TABLE_SQL)
    log.info("Table %s ready", TARGET_FQN)


def fetch_game_dates(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return sorted list of regular-season game dates in [start_date, end_date]."""
    sql = """
        SELECT DISTINCT official_date
        FROM baseball_data.betting.stg_statsapi_games
        WHERE game_type = 'R'
          AND official_date >= %(start)s
          AND official_date <= %(end)s
        ORDER BY official_date
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"start": start_date.isoformat(), "end": end_date.isoformat()})
        return [row[0] for row in cur.fetchall()]


def fetch_already_loaded(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
    bookmaker: str,
) -> set[tuple[str, str]]:
    """
    Return set of (game_date_iso, snapshot_ts_label) pairs already present.
    snapshot_ts_label format: 'YYYY-MM-DDTHH:MM:00Z'
    """
    sql = f"""
        SELECT DISTINCT
            TO_VARCHAR(game_date, 'YYYY-MM-DD')                                       AS gd,
            TO_VARCHAR(snapshot_ts, 'YYYY-MM-DD') || 'T'
                || LPAD(EXTRACT(HOUR   FROM snapshot_ts)::INTEGER::VARCHAR, 2, '0')
                || ':'
                || LPAD(EXTRACT(MINUTE FROM snapshot_ts)::INTEGER::VARCHAR, 2, '0')
                || ':00Z'                                                              AS ts_label
        FROM {TARGET_FQN}
        WHERE bookmaker = %(bk)s
          AND game_date >= %(start)s
          AND game_date <= %(end)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "bk":    bookmaker,
            "start": start_date.isoformat(),
            "end":   end_date.isoformat(),
        })
        return {(row[0], row[1]) for row in cur.fetchall()}


def fetch_dates_with_sufficient_coverage(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
    bookmaker: str,
    min_snapshots: int = 2,
) -> set[str]:
    """
    Return set of game_date ISO strings where EVERY game on that date already has
    >= min_snapshots distinct snapshot timestamps loaded.

    A date is only skipped when all its games are fully covered — if even one game
    has fewer than min_snapshots snapshots the date is re-processed so the missing
    timestamp can be added for the under-covered game(s).
    """
    sql = f"""
        WITH game_snap_counts AS (
            SELECT
                TO_VARCHAR(game_date, 'YYYY-MM-DD')   AS gd,
                home_team,
                away_team,
                COUNT(DISTINCT snapshot_ts)            AS snap_count
            FROM {TARGET_FQN}
            WHERE bookmaker = %(bk)s
              AND game_date >= %(start)s
              AND game_date <= %(end)s
            GROUP BY game_date, home_team, away_team
        )
        SELECT gd
        FROM game_snap_counts
        GROUP BY gd
        HAVING MIN(snap_count) >= %(min_snaps)s
    """
    with conn.cursor() as cur:
        cur.execute(sql, {
            "bk":        bookmaker,
            "start":     start_date.isoformat(),
            "end":       end_date.isoformat(),
            "min_snaps": min_snapshots,
        })
        return {row[0] for row in cur.fetchall()}


def build_game_pk_lookup(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
) -> dict[tuple[str, str, str], list[tuple[int, datetime | None]]]:
    """
    Build a dict mapping (home_team_name, away_team_name, official_date_iso) →
    list of (game_pk, game_start_utc) sorted by game_number.

    A list is used so doubleheaders (two games, same teams, same date) are
    preserved. Disambiguation by commence_time is handled in resolve_game_pk().

    The query window is widened by ±2 days so that the date±1 fallbacks in
    resolve_game_pk() can find games that cross UTC midnight or were postponed.
    """
    padded_start = (start_date - timedelta(days=2)).isoformat()
    padded_end   = (end_date   + timedelta(days=2)).isoformat()
    sql = """
        SELECT
            home_team_name,
            away_team_name,
            TO_VARCHAR(official_date, 'YYYY-MM-DD') AS date_str,
            game_pk,
            CONVERT_TIMEZONE('UTC', game_date)      AS game_start_utc
        FROM baseball_data.betting.stg_statsapi_games
        WHERE game_type = 'R'
          AND official_date >= %(start)s
          AND official_date <= %(end)s
        ORDER BY official_date, game_number
    """
    lookup: dict[tuple[str, str, str], list[tuple[int, datetime | None]]] = {}
    with conn.cursor() as cur:
        cur.execute(sql, {"start": padded_start, "end": padded_end})
        for row in cur.fetchall():
            home_team, away_team, date_str, game_pk, game_start = row
            key = (home_team, away_team, date_str)
            if key not in lookup:
                lookup[key] = []
            lookup[key].append((game_pk, game_start))
    return lookup


def resolve_game_pk(
    pk_lookup: dict[tuple[str, str, str], list[tuple[int, datetime | None]]],
    home_team: str,
    away_team: str,
    date_str: str,
    commence_time_str: str,
) -> tuple[int, str] | None:
    """
    Return (game_pk, official_date_iso) for the best-matching StatsAPI game, or
    None if no game matches.

    The matched ``try_date`` IS the game's StatsAPI official_date — the lookup is
    keyed on official_date — so the caller stamps the row's game_date from it
    rather than from the loop date. This is what keeps a single game_pk from being
    written under two adjacent game_dates: a late-night ET game whose UTC date is
    the next day resolves via the date−1 fallback to its true official_date, and
    that official_date (not the loop's UTC date) is what gets stored.

    Resolution order:
      1. Exact date match
      2. date − 1 (late-night ET games whose UTC date is one day after official_date)
      3. date + 1 (postponed games; OddsAPI keeps original scheduled date)

    For each candidate date, if only one game is found (most cases) it is
    returned immediately.  For doubleheaders (two games, same teams, same date)
    the candidate whose statsapi game_start_utc is closest to the OddsAPI
    commence_time is chosen.  If commence_time parsing fails or all game_start_utc
    values are None, the first candidate (game 1) is returned with a warning.
    """
    try:
        oddsapi_ct: datetime | None = datetime.fromisoformat(
            commence_time_str.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        oddsapi_ct = None

    for try_date in [
        date_str,
        (date.fromisoformat(date_str) - timedelta(days=1)).isoformat(),
        (date.fromisoformat(date_str) + timedelta(days=1)).isoformat(),
    ]:
        candidates = pk_lookup.get((home_team, away_team, try_date))
        if not candidates:
            continue

        if len(candidates) == 1:
            return candidates[0][0], try_date

        # Doubleheader: try to match by commence_time proximity.
        if oddsapi_ct is not None:
            timed = [
                (game_pk, gs)
                for game_pk, gs in candidates
                if gs is not None
            ]
            if timed:
                best_pk = min(
                    timed,
                    key=lambda pair: abs((pair[1] - oddsapi_ct).total_seconds()),
                )[0]
                return best_pk, try_date

        # Fallback: game 1 (first in list, ordered by game_number).
        log.warning(
            "  Doubleheader ambiguity for %s vs %s on %s — no start time available, "
            "defaulting to game 1 (game_pk=%s)",
            home_team, away_team, try_date, candidates[0][0],
        )
        return candidates[0][0], try_date

    return None


# ── OddsAPI helpers ───────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        raise EnvironmentError("ODDS_API_KEY is not set.")
    return key


def _parse_int_header(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def fetch_snapshot(
    snapshot_ts: str,
    bookmaker: str,
    sleep_seconds: float,
    region: str = "us",
) -> tuple[list[dict], int | None, int | None]:
    """
    Fetch h2h + totals odds from the OddsAPI historical endpoint at a single UTC
    snapshot timestamp. Returns (events, credits_used, credits_remaining).
    Empty list on 404 or missing data. Exits on 401/403/429.
    """
    url    = ODDS_API_BASE_URL + HIST_ENDPOINT
    params = {
        "apiKey":     _get_api_key(),
        "date":       snapshot_ts,
        "regions":    region,
        "markets":    "h2h,totals",
        "oddsFormat": "american",
    }
    # all-books mode: omit the bookmakers filter so the response carries every book
    # in the region (same credit cost). Single-book mode keeps the narrow filter.
    if bookmaker != ALL_BOOKS:
        params["bookmakers"] = bookmaker

    log.info("GET %s  date=%s  bookmaker=%s", url, snapshot_ts, bookmaker)

    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        log.warning("  Request error: %s — treating as missing", exc)
        time.sleep(sleep_seconds)
        return [], None, None

    used      = _parse_int_header(resp.headers.get("x-requests-used"))
    remaining = _parse_int_header(resp.headers.get("x-requests-remaining"))
    log.info("  HTTP %d  credits used=%s  remaining=%s", resp.status_code, used, remaining)

    if resp.status_code in (401, 403):
        print(
            f"\nERROR: HTTP {resp.status_code} — OddsAPI historical endpoint requires "
            "a paid plan. Please upgrade your plan and retry.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 429:
        print(
            "\nERROR: HTTP 429 — rate limit reached. "
            "Re-run with --sleep-seconds 2 or split into smaller date ranges.\n",
            file=sys.stderr,
        )
        sys.exit(1)

    if resp.status_code == 404:
        log.info("  404 — no data at this snapshot")
        time.sleep(sleep_seconds)
        return [], used, remaining

    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.warning("  HTTP error: %s — treating as missing", exc)
        time.sleep(sleep_seconds)
        return [], used, remaining

    payload = resp.json()
    if isinstance(payload, dict):
        events = payload.get("data", [])
    elif isinstance(payload, list):
        events = payload
    else:
        events = []

    log.info("  %d event(s) in response", len(events))
    time.sleep(sleep_seconds)
    return events, used, remaining


def _extract_h2h(event: dict, bookmaker_key: str) -> tuple[int | None, int | None]:
    """Return (home_price, away_price) American odds from the h2h market."""
    # Use raw OddsAPI name for outcome matching (outcomes use the same names as the event)
    home_team  = event.get("home_team")
    home_price = None
    away_price = None

    for bk in event.get("bookmakers", []):
        if bk.get("key") != bookmaker_key:
            continue
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                price = outcome.get("price")
                if outcome.get("name") == home_team:
                    home_price = price
                else:
                    away_price = price
        break  # only one bookmaker entry needed

    return home_price, away_price


def _extract_totals(event: dict, bookmaker_key: str) -> tuple[int | None, int | None, float | None]:
    """Return (over_price, under_price, total_line) from the totals market."""
    over_price  = None
    under_price = None
    total_line  = None

    for bk in event.get("bookmakers", []):
        if bk.get("key") != bookmaker_key:
            continue
        for market in bk.get("markets", []):
            if market.get("key") != "totals":
                continue
            for outcome in market.get("outcomes", []):
                name  = outcome.get("name", "").lower()
                price = outcome.get("price")
                point = outcome.get("point")
                if name == "over":
                    over_price = price
                    if point is not None:
                        total_line = float(point)
                elif name == "under":
                    under_price = price
                    if point is not None and total_line is None:
                        total_line = float(point)
        break

    return over_price, under_price, total_line


# ── Snowflake write ────────────────────────────────────────────────────────────
# Pattern: VARCHAR temp table + executemany → MERGE INTO target on natural key.
# The natural key is (home_team, away_team, game_date, snapshot_ts, bookmaker)
# because game_pk may be NULL for unmatched events.

_CREATE_TEMP_SQL = """
    CREATE OR REPLACE TEMPORARY TABLE tmp_odds_snaps (
        game_pk_str    VARCHAR,
        game_date_str  VARCHAR,
        snapshot_ts_str VARCHAR,
        home_team      VARCHAR,
        away_team      VARCHAR,
        home_price_str VARCHAR,
        away_price_str VARCHAR,
        over_price_str VARCHAR,
        under_price_str VARCHAR,
        total_line_str VARCHAR,
        bookmaker      VARCHAR,
        home_win_prob_str VARCHAR,
        away_win_prob_str VARCHAR,
        load_id        VARCHAR
    )
"""

_INSERT_TEMP_SQL = """
    INSERT INTO tmp_odds_snaps VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
"""

_MERGE_SQL = f"""
    MERGE INTO {TARGET_FQN} AS tgt
    USING (
        SELECT
            TRY_CAST(game_pk_str    AS INTEGER)      AS game_pk,
            TRY_CAST(game_date_str  AS DATE)         AS game_date,
            TRY_CAST(snapshot_ts_str AS TIMESTAMP_TZ) AS snapshot_ts,
            home_team,
            away_team,
            TRY_CAST(home_price_str AS INTEGER)      AS home_price,
            TRY_CAST(away_price_str AS INTEGER)      AS away_price,
            TRY_CAST(over_price_str AS INTEGER)      AS over_price,
            TRY_CAST(under_price_str AS INTEGER)     AS under_price,
            TRY_CAST(total_line_str AS FLOAT)        AS total_line,
            bookmaker,
            TRY_CAST(home_win_prob_str AS FLOAT)     AS home_win_prob,
            TRY_CAST(away_win_prob_str AS FLOAT)     AS away_win_prob,
            load_id
        FROM tmp_odds_snaps
    ) AS src
    ON  tgt.home_team   = src.home_team
    AND tgt.away_team   = src.away_team
    AND tgt.game_date   = src.game_date
    AND tgt.snapshot_ts = src.snapshot_ts
    AND tgt.bookmaker   = src.bookmaker
    WHEN MATCHED THEN UPDATE SET
        game_pk       = src.game_pk,
        home_price    = src.home_price,
        away_price    = src.away_price,
        over_price    = src.over_price,
        under_price   = src.under_price,
        total_line    = src.total_line,
        home_win_prob = src.home_win_prob,
        away_win_prob = src.away_win_prob,
        load_id       = src.load_id,
        loaded_at     = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        game_pk, game_date, snapshot_ts, home_team, away_team,
        home_price, away_price, over_price, under_price, total_line,
        bookmaker, home_win_prob, away_win_prob, load_id
    ) VALUES (
        src.game_pk, src.game_date, src.snapshot_ts, src.home_team, src.away_team,
        src.home_price, src.away_price, src.over_price, src.under_price, src.total_line,
        src.bookmaker, src.home_win_prob, src.away_win_prob, src.load_id
    )
"""


def _str(v: Any) -> str | None:
    return str(v) if v is not None else None


def upsert_rows(
    conn: snowflake.connector.SnowflakeConnection,
    rows: list[dict],
) -> tuple[int, int]:
    """
    Write rows to odds_snapshots_historical via temp table + MERGE.
    Returns (rows_inserted, rows_updated).
    """
    if not rows:
        return 0, 0

    with conn.cursor() as cur:
        cur.execute(_CREATE_TEMP_SQL)

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            cur.executemany(
                _INSERT_TEMP_SQL,
                [
                    (
                        _str(r["game_pk"]),
                        r["game_date"],
                        r["snapshot_ts"],
                        r["home_team"],
                        r["away_team"],
                        _str(r["home_price"]),
                        _str(r["away_price"]),
                        _str(r["over_price"]),
                        _str(r["under_price"]),
                        _str(r["total_line"]),
                        r["bookmaker"],
                        _str(r["home_win_prob"]),
                        _str(r["away_win_prob"]),
                        r["load_id"],
                    )
                    for r in batch
                ],
            )

        cur.execute(_MERGE_SQL)
        # Snowflake returns (rows_inserted, rows_updated) for MERGE
        result = cur.fetchone()
        ins = result[0] if result else 0
        upd = result[1] if result else 0

    return ins, upd


# ── Parquet → COPY INTO → MERGE (deferred-load mode) ──────────────────────────
# Fetch writes one parquet per date locally (no warehouse), then a single bulk load
# at the end. Everything is stored as VARCHAR in parquet so the load is unambiguous
# (avoids the write_pandas DATE/TIMESTAMP serialization corruption) and cast in MERGE.

def write_date_parquet(date_rows: list[dict], parquet_dir: Path,
                       date_str: str, bookmaker: str, region: str) -> Path:
    import pandas as pd

    df = pd.DataFrame(date_rows, columns=PARQUET_COLS).astype("string")  # nullable str
    safe = f"{date_str}_{bookmaker}_{region.replace(',', '-')}"
    path = parquet_dir / f"snap_{safe}.parquet"
    df.to_parquet(path, index=False)
    return path


_CREATE_STAGING_SQL = f"""
    CREATE OR REPLACE TRANSIENT TABLE {STAGING_FQN} (
        game_pk VARCHAR, game_date VARCHAR, snapshot_ts VARCHAR,
        home_team VARCHAR, away_team VARCHAR,
        home_price VARCHAR, away_price VARCHAR, over_price VARCHAR,
        under_price VARCHAR, total_line VARCHAR, bookmaker VARCHAR,
        home_win_prob VARCHAR, away_win_prob VARCHAR, load_id VARCHAR
    )
"""

_MERGE_FROM_STAGING_SQL = f"""
    MERGE INTO {TARGET_FQN} AS tgt
    USING (
        -- Outer SELECT keeps one row per MERGE key. The source MUST be unique on the ON
        -- key or Snowflake raises 100090 "Duplicate row detected during DML action".
        -- Two ways the staging set produces duplicates, both handled here:
        --   1. DOUBLEHEADERS — same (home_team, away_team, game_date) but distinct game_pk;
        --      game_pk is therefore part of BOTH the dedup partition AND the ON clause so the
        --      two games map to two target rows instead of colliding.
        --   2. A snapshot re-fetched under two requested timestamps that resolve to the same
        --      stored snapshot_ts — collapsed by ROW_NUMBER()=1.
        SELECT
            game_pk, game_date, snapshot_ts, home_team, away_team,
            home_price, away_price, over_price, under_price, total_line,
            bookmaker, home_win_prob, away_win_prob, load_id
        FROM (
            SELECT
                TRY_CAST(game_pk       AS INTEGER)       AS game_pk,
                TRY_CAST(game_date     AS DATE)          AS game_date,
                TRY_CAST(snapshot_ts   AS TIMESTAMP_TZ)  AS snapshot_ts,
                home_team,
                away_team,
                TRY_CAST(home_price    AS INTEGER)       AS home_price,
                TRY_CAST(away_price    AS INTEGER)       AS away_price,
                TRY_CAST(over_price    AS INTEGER)       AS over_price,
                TRY_CAST(under_price   AS INTEGER)       AS under_price,
                TRY_CAST(total_line    AS FLOAT)         AS total_line,
                bookmaker,
                TRY_CAST(home_win_prob AS FLOAT)         AS home_win_prob,
                TRY_CAST(away_win_prob AS FLOAT)         AS away_win_prob,
                load_id,
                ROW_NUMBER() OVER (
                    PARTITION BY TRY_CAST(game_pk AS INTEGER), home_team, away_team,
                                 TRY_CAST(game_date AS DATE),
                                 TRY_CAST(snapshot_ts AS TIMESTAMP_TZ), bookmaker
                    ORDER BY TRY_CAST(snapshot_ts AS TIMESTAMP_TZ)
                ) AS _rn
            FROM {STAGING_FQN}
        )
        WHERE _rn = 1
    ) AS src
    ON  EQUAL_NULL(tgt.game_pk, src.game_pk)
    AND tgt.home_team   = src.home_team
    AND tgt.away_team   = src.away_team
    AND tgt.game_date   = src.game_date
    AND tgt.snapshot_ts = src.snapshot_ts
    AND tgt.bookmaker   = src.bookmaker
    WHEN MATCHED THEN UPDATE SET
        game_pk       = src.game_pk,
        home_price    = src.home_price,
        away_price    = src.away_price,
        over_price    = src.over_price,
        under_price   = src.under_price,
        total_line    = src.total_line,
        home_win_prob = src.home_win_prob,
        away_win_prob = src.away_win_prob,
        load_id       = src.load_id,
        loaded_at     = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN INSERT (
        game_pk, game_date, snapshot_ts, home_team, away_team,
        home_price, away_price, over_price, under_price, total_line,
        bookmaker, home_win_prob, away_win_prob, load_id
    ) VALUES (
        src.game_pk, src.game_date, src.snapshot_ts, src.home_team, src.away_team,
        src.home_price, src.away_price, src.over_price, src.under_price, src.total_line,
        src.bookmaker, src.home_win_prob, src.away_win_prob, src.load_id
    )
"""


def bulk_load_parquet(conn: snowflake.connector.SnowflakeConnection,
                      parquet_dir: Path) -> tuple[int, int]:
    """PUT every parquet in parquet_dir → the staging table's internal stage, COPY INTO
    a transient staging table (MATCH_BY_COLUMN_NAME), then MERGE into the target in one
    shot. The warehouse is used ONLY here (PUT is a client-side upload, no warehouse)."""
    files = sorted(parquet_dir.glob("*.parquet"))
    if not files:
        log.warning("No parquet files in %s — nothing to load.", parquet_dir)
        return 0, 0

    put_glob = str((parquet_dir / "*.parquet").resolve()).replace("\\", "/")
    log.info("Bulk-loading %d parquet file(s) from %s ...", len(files), parquet_dir)
    with conn.cursor() as cur:
        cur.execute(_CREATE_STAGING_SQL)
        # PUT runs client-side; parquet is already compressed.
        cur.execute(
            f"PUT 'file://{put_glob}' {STAGING_STAGE} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
        cur.execute(
            f"COPY INTO {STAGING_FQN} FROM {STAGING_STAGE} "
            "FILE_FORMAT=(TYPE=PARQUET) MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE PURGE=TRUE"
        )
        cur.execute(f"SELECT COUNT(*) FROM {STAGING_FQN}")
        staged = cur.fetchone()[0]
        log.info("  staged %d row(s) → MERGE into %s", staged, TARGET_FQN)
        cur.execute(_MERGE_FROM_STAGING_SQL)
        result = cur.fetchone()
        ins = result[0] if result else 0
        upd = result[1] if result else 0
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_FQN}")

    return ins, upd


# ── Main backfill loop ────────────────────────────────────────────────────────

def run_backfill(
    start_date: date,
    end_date: date,
    timestamps: list[str],
    bookmaker: str,
    sleep_seconds: float,
    min_snapshots: int = 2,
    region: str = "us",
    parquet_out: Path | None = None,
    force: bool = False,
    load_only: bool = False,
) -> None:
    if parquet_out is not None:
        parquet_out.mkdir(parents=True, exist_ok=True)
        log.info("Deferred-load mode: per-date parquet → %s, single COPY+MERGE at the end "
                 "(warehouse stays suspended through the fetch loop).", parquet_out)

    log.info("Connecting to Snowflake ...")
    conn = get_snowflake_connection()

    ensure_table(conn)

    # RECOVERY PATH: load already-staged parquet WITHOUT re-fetching from the API. Use this
    # when the fetch succeeded but the final MERGE failed (the parquet on disk holds every
    # row, so no API credits are re-spent). Requires --parquet-out pointing at that dir.
    if load_only:
        if parquet_out is None:
            log.error("--load-only requires --parquet-out pointing at the staged parquet dir.")
            conn.close()
            return
        log.info("--load-only: skipping fetch; loading existing parquet from %s ...", parquet_out)
        ins, upd = bulk_load_parquet(conn, parquet_out)
        conn.close()
        print(f"\nLoad-only complete: {ins} inserted, {upd} updated from {parquet_out}")
        return

    log.info("Fetching regular-season game dates %s → %s ...", start_date, end_date)
    game_dates = fetch_game_dates(conn, start_date, end_date)
    if not game_dates:
        log.warning("No regular-season game dates found in range — nothing to do.")
        conn.close()
        return
    log.info("  %d game date(s) found", len(game_dates))

    log.info("Building game_pk lookup table ...")
    pk_lookup = build_game_pk_lookup(conn, start_date, end_date)
    n_games = sum(len(v) for v in pk_lookup.values())
    n_dh    = sum(1 for v in pk_lookup.values() if len(v) > 1)
    log.info("  %d game(s) cached across %d matchup-dates (%d doubleheader date(s))",
             n_games, len(pk_lookup), n_dh)

    # In all-books mode, decide skip/coverage against the anchor book (it's present on
    # most games); a date/snapshot already covered for the anchor means we'd re-pull the
    # whole region for no new anchor data, so skipping it saves credits.
    #
    # --force bypasses BOTH skips: the anchor-book coverage check is wrong for a
    # RE-DENSIFICATION pass (adding new regions/books/timestamps on top of an existing
    # sparse backfill) — bovada already being dense made every date skip and starved the
    # new us2 + full-eu/Pinnacle pulls. With --force every (date × timestamp) call fires;
    # the MERGE is idempotent on the natural key, so re-pulled rows update in place and the
    # genuinely-new books/timestamps insert.
    if force:
        log.info("--force: bypassing coverage/already-loaded skips — every (date × timestamp) "
                 "call will fire (re-pulls are idempotent MERGEs).")
        dates_sufficient: set = set()
        already_loaded: set = set()
    else:
        coverage_book = COVERAGE_ANCHOR if bookmaker == ALL_BOOKS else bookmaker
        log.info("Checking coverage of already-loaded snapshots (min_snapshots=%d, anchor=%s) ...",
                 min_snapshots, coverage_book)
        dates_sufficient = fetch_dates_with_sufficient_coverage(
            conn, start_date, end_date, coverage_book, min_snapshots=min_snapshots
        )
        log.info("  %d date(s) already have ≥%d snapshots — will skip entirely",
                 len(dates_sufficient), min_snapshots)
        already_loaded = fetch_already_loaded(conn, start_date, end_date, coverage_book)
        log.info("  %d (game_date, snapshot_ts) pair(s) already loaded — will skip individual calls", len(already_loaded))

    total_calls        = len(game_dates) * len(timestamps)
    call_num           = 0
    calls_skipped      = 0
    total_inserted     = 0
    total_updated      = 0
    total_rows_written = 0     # parquet mode: rows staged to disk during fetch
    last_remaining: int | None = None
    load_id            = str(uuid.uuid4())

    log.info(
        "Backfill start: %d date(s) × %d timestamp(s) = %d call(s)  load_id=%s",
        len(game_dates), len(timestamps), total_calls, load_id,
    )

    for game_date in game_dates:
        date_str = game_date.isoformat() if isinstance(game_date, date) else str(game_date)

        if date_str in dates_sufficient:
            log.info("  %s — already has ≥%d snapshots, skipping date", date_str, min_snapshots)
            calls_skipped += len(timestamps)
            call_num      += len(timestamps)
            continue

        # Accumulate every timestamp's rows for this date, then write ONCE per date
        # (one temp-table build + one MERGE instead of one per timestamp → ~Nx fewer
        # Snowflake round-trips/warehouse ops). The date is a natural resume checkpoint:
        # a crash only loses the in-progress date, which re-fetches on the next run.
        date_rows: list[dict] = []

        for ts_str in timestamps:
            call_num   += 1
            ts_label    = f"{date_str}T{ts_str}:00Z"

            if (date_str, ts_label) in already_loaded:
                log.info("[%d/%d] %s — already loaded, skipping", call_num, total_calls, ts_label)
                calls_skipped += 1
                continue

            events, used, remaining = fetch_snapshot(ts_label, bookmaker, sleep_seconds, region)
            if remaining is not None:
                last_remaining = remaining

            if not events:
                log.info("  No events returned for %s", ts_label)
                continue

            ts_start  = len(date_rows)
            unmatched = 0

            for event in events:
                ct         = event.get("commence_time", "")
                event_date = ct[:10] if ct else ""
                if event_date != date_str:
                    continue  # skip games not on this date

                home_team = normalize_team_name(event.get("home_team", ""), date_str)
                away_team = normalize_team_name(event.get("away_team", ""), date_str)

                resolved = resolve_game_pk(
                    pk_lookup, home_team, away_team, date_str, ct
                )
                if resolved is None:
                    # Unmatched: keep NULL game_pk and fall back to the loop date for
                    # game_date (no StatsAPI official_date is available to stamp from).
                    game_pk = None
                    resolved_game_date = date_str
                    log.warning(
                        "  No game_pk found for %s vs %s on %s — storing with NULL game_pk",
                        home_team, away_team, date_str,
                    )
                    unmatched += 1
                else:
                    # Stamp game_date from the resolved StatsAPI official_date, NOT the
                    # loop date_str — this is what prevents the same game_pk from being
                    # written under two adjacent game_dates (UTC-midnight straddle).
                    game_pk, resolved_game_date = resolved

                # In all-books mode emit one row per book present in the event;
                # otherwise just the single requested book.
                if bookmaker == ALL_BOOKS:
                    book_keys = [b.get("key") for b in event.get("bookmakers", []) if b.get("key")]
                else:
                    book_keys = [bookmaker]

                for bk in book_keys:
                    home_price, away_price      = _extract_h2h(event, bk)
                    over_price, under_price, total_line = _extract_totals(event, bk)
                    # skip a book that carried neither market at this snapshot
                    if home_price is None and away_price is None and total_line is None:
                        continue

                    date_rows.append({
                        "game_pk":       game_pk,
                        "game_date":     resolved_game_date,
                        "snapshot_ts":   ts_label,
                        "home_team":     home_team,
                        "away_team":     away_team,
                        "home_price":    home_price,
                        "away_price":    away_price,
                        "over_price":    over_price,
                        "under_price":   under_price,
                        "total_line":    total_line,
                        "bookmaker":     bk,
                        "home_win_prob": american_to_implied_prob(home_price),
                        "away_win_prob": american_to_implied_prob(away_price),
                        "load_id":       load_id,
                    })

            if unmatched:
                log.warning("  %d event(s) had no matching game_pk on %s", unmatched, date_str)
            log.info("[%d/%d] %s — %d row(s) buffered  credits_remaining=%s",
                     call_num, total_calls, ts_label, len(date_rows) - ts_start, remaining)

        # Single write per date. Parquet mode defers ALL Snowflake work to the end so the
        # warehouse stays suspended during fetch; direct mode MERGEs per date.
        if date_rows:
            if parquet_out is not None:
                path = write_date_parquet(date_rows, parquet_out, date_str, bookmaker, region)
                total_rows_written += len(date_rows)
                log.info("  %s — wrote %d row(s) → %s", date_str, len(date_rows), path.name)
            else:
                ins, upd = upsert_rows(conn, date_rows)
                total_inserted += ins
                total_updated  += upd
                log.info("  %s — flushed %d row(s) in 1 MERGE: %d inserted, %d updated",
                         date_str, len(date_rows), ins, upd)

    # Deferred load: one PUT → COPY INTO → MERGE for the whole run.
    if parquet_out is not None:
        log.info("Fetch complete (%d row(s) staged to parquet). Loading to Snowflake ...",
                 total_rows_written)
        total_inserted, total_updated = bulk_load_parquet(conn, parquet_out)

    conn.close()

    print("\n" + "=" * 60)
    print("Backfill complete")
    print("=" * 60)
    print(f"  Date range         : {start_date} → {end_date}")
    print(f"  Bookmaker          : {bookmaker}")
    print(f"  Region             : {region}")
    print(f"  Total calls        : {call_num}")
    print(f"  Calls skipped      : {calls_skipped}")
    print(f"  Rows inserted      : {total_inserted}")
    print(f"  Rows updated       : {total_updated}")
    if last_remaining is not None:
        print(f"  Credits remaining  : {last_remaining}")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill OddsAPI historical intraday odds snapshots into "
            "baseball_data.oddsapi.odds_snapshots_historical (Card 7.P2)."
        )
    )
    parser.add_argument(
        "--start-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="First game date to backfill, inclusive.",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Last game date to backfill, inclusive.",
    )
    parser.add_argument(
        "--timestamps",
        required=True,
        metavar="HH:MM,...",
        help="Comma-separated UTC timestamps to snapshot per date (e.g. 12:00,17:00,23:00).",
    )
    parser.add_argument(
        "--bookmaker",
        default=DEFAULT_BOOKMAKER,
        metavar="KEY",
        help=(
            f"OddsAPI bookmaker key (default: {DEFAULT_BOOKMAKER}). Use '{ALL_BOOKS}' to "
            "capture EVERY book in the requested region(s) in one call — same credit cost "
            "(cost is per region, not per book), ~15+ books/call. Skip/coverage is anchored "
            f"on '{COVERAGE_ANCHOR}' in this mode."
        ),
    )
    parser.add_argument(
        "--region",
        default="us",
        metavar="REGION",
        help=(
            "OddsAPI region key (default: us). Use 'eu' to access European bookmakers "
            "such as Pinnacle, which are not available in the us/us2 markets."
        ),
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_SLEEP,
        metavar="N",
        help=f"Seconds to sleep between API calls (default: {DEFAULT_SLEEP}).",
    )
    parser.add_argument(
        "--min-snapshots",
        type=int,
        default=2,
        metavar="N",
        help=(
            "Skip a date only when it already has >= N distinct snapshot timestamps loaded "
            "(default: 2). Use --min-snapshots 3 when adding a third timestamp to dates "
            "that already have 2."
        ),
    )
    parser.add_argument(
        "--parquet-out",
        default=None,
        metavar="DIR",
        help=(
            "DEFERRED-LOAD mode: write one parquet file per game-date to DIR during fetch "
            "(Snowflake/warehouse stays SUSPENDED through the API loop), then a single "
            "PUT → COPY INTO → MERGE at the end. Also banks fetched data to disk so a "
            "Snowflake failure never re-burns API credits. Recommended for large backfills."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help=(
            "Bypass the anchor-book coverage/already-loaded skips and fire EVERY "
            "(date × timestamp) call. Use this for a RE-DENSIFICATION pass (adding new "
            "regions/books/timestamps on top of an existing backfill) — otherwise an "
            "already-dense anchor book (e.g. bovada) makes every date skip. Re-pulls are "
            "idempotent MERGEs, so existing rows update and new books/timestamps insert."
        ),
    )
    parser.add_argument(
        "--load-only",
        action="store_true",
        default=False,
        help=(
            "RECOVERY: skip the API fetch and load the parquet already in --parquet-out into "
            "Snowflake (re-runs the PUT → COPY → MERGE). Use when the fetch succeeded but the "
            "MERGE failed — no API credits are re-spent."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print expected call count and exit without making API or Snowflake calls.",
    )
    return parser


def main() -> None:
    args       = build_parser().parse_args()
    timestamps = [t.strip() for t in args.timestamps.split(",") if t.strip()]

    try:
        start_date = date.fromisoformat(args.start_date)
        end_date   = date.fromisoformat(args.end_date)
    except ValueError as exc:
        print(f"ERROR: Invalid date format — {exc}", file=sys.stderr)
        sys.exit(1)

    if not timestamps:
        print("ERROR: --timestamps is empty.", file=sys.stderr)
        sys.exit(1)

    if start_date > end_date:
        print("ERROR: --start-date must be <= --end-date.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        print("DRY-RUN mode — no API calls or Snowflake writes will be made.\n")
        print(f"Date range     : {start_date} → {end_date}")
        print(f"Timestamps     : {', '.join(timestamps)}")
        print(f"Bookmaker      : {args.bookmaker}")
        print(f"Region         : {args.region}")
        print(f"Sleep (seconds): {args.sleep_seconds}")
        span_days      = (end_date - start_date).days + 1
        approx_dates   = round(span_days * 0.6)  # rough: ~60% of days are game days
        approx_calls   = approx_dates * len(timestamps)
        # The Odds API HISTORICAL cost = 10 × [#markets] × [#regions]. We always request
        # 2 markets (h2h,totals); regions = comma-count of --region. (Verified live
        # 2026-06-16: regions=us, markets=h2h,totals → x-requests-last: 20.) The number of
        # bookmakers does NOT change cost, so --bookmaker all is free upside.
        n_regions        = len([r for r in args.region.split(",") if r.strip()])
        credits_per_call = 10 * 2 * n_regions
        approx_credits   = approx_calls * credits_per_call
        print(f"\nEstimated game dates in range : ~{approx_dates} (exact count from Snowflake at runtime)")
        print(f"Estimated API calls           : ~{approx_calls}")
        print(f"Credits per call              : {credits_per_call}  (10 × 2 markets × {n_regions} region(s))")
        print(f"Estimated credits consumed    : ~{approx_credits}")
        if args.bookmaker == ALL_BOOKS:
            print(f"Bookmaker mode                : ALL books in region(s)={args.region} (same cost, ~15+ books/call)")
        if args.force:
            print("Skip mode                     : --force (no coverage/already-loaded skips — "
                  "every call fires; the credit estimate above is the full spend)")
        else:
            print("Skip mode                     : default (skips dates/timestamps the anchor "
                  "book already covers; actual spend will be LOWER — use --force to re-densify)")
        if args.parquet_out:
            print(f"Load mode                     : DEFERRED (parquet → {args.parquet_out} → one COPY+MERGE; warehouse cold during fetch)")
        print("\nDry-run complete.")
        return

    run_backfill(
        start_date    = start_date,
        end_date      = end_date,
        timestamps    = timestamps,
        bookmaker     = args.bookmaker,
        sleep_seconds = args.sleep_seconds,
        min_snapshots = args.min_snapshots,
        region        = args.region,
        parquet_out   = Path(args.parquet_out) if args.parquet_out else None,
        force         = args.force,
        load_only     = args.load_only,
    )


if __name__ == "__main__":
    main()
