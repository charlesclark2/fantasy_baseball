"""
ingest_actionnetwork_betting.py
-------------------------------
Ingest public betting percentages (money% and ticket%) from the Action Network
public-betting endpoint into baseball_data.actionnetwork.public_betting_raw.

Modes:
    uv run ingest_actionnetwork_betting.py                              # today
    uv run ingest_actionnetwork_betting.py --date 2025-09-01
    uv run ingest_actionnetwork_betting.py --backfill --start-date 2021-04-01
    uv run ingest_actionnetwork_betting.py --date 2025-09-01 --dry-run

The --dry-run flag prints the raw JSON for the first game and skips the DB
write — useful for inspecting nesting before relying on the parse logic.

NOTES on API behavior (verified 2026-05-07):
    - Endpoint requires a browser-like User-Agent or returns 403.
    - The bookIds query param accepts up to ~11 books, but in practice only
      book 15 (FanDuel — also the public-facing book on actionnetwork.com)
      returns non-zero `bet_info.money.percent` / `bet_info.tickets.percent`
      values. Other books carry odds + lines but their bet_info percentages
      are zeros or nulls. We therefore prefer book 15 and fall back to any
      other book that happens to carry a non-zero percent for a given game.
    - Date format required by the API: YYYYMMDD (no dashes).
    - Empty / no-games responses (e.g. early-season days the API never
      tracked) are logged and skipped without raising.

Snowflake auth env vars match the rest of the project:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE,
    SNOWFLAKE_PRIVATE_KEY_PATH (preferred) / SNOWFLAKE_PASSWORD (fallback),
    SNOWFLAKE_ROLE (optional).
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
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

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────────────

AN_BASE_URL  = "https://api.actionnetwork.com/web/v2/scoreboard/publicbetting/mlb"
AN_BOOK_IDS  = "15,30,4727,4795,79,2988,69,68,75,123,71"
# Book 15 (FanDuel) is the only book that consistently carries non-zero
# bet_info percentages; we prefer it and fall back to other books only if
# its outcomes are missing or all zero.
PREFERRED_BOOK_ID = "15"

# The endpoint blocks default User-Agents (HTTP 403). Use a browser UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.actionnetwork.com/",
}

REQUEST_TIMEOUT_S = 30
BACKFILL_DELAY_S  = 0.7

TARGET_DATABASE = "baseball_data"
TARGET_SCHEMA   = "actionnetwork"
TARGET_TABLE    = "public_betting_raw"
TARGET_FQN      = f"{TARGET_DATABASE}.{TARGET_SCHEMA}.{TARGET_TABLE}"


# ── Snowflake connection ──────────────────────────────────────────────────────

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
        "database":  TARGET_DATABASE,
        "schema":    TARGET_SCHEMA,
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


# ── API fetch / parse ─────────────────────────────────────────────────────────

def fetch_public_betting(game_date: date) -> dict | None:
    """
    Call the Action Network public-betting endpoint for a single date.

    Returns the parsed JSON dict on success, None on a 4xx that indicates
    "no data for this date" so the backfill can keep going.
    """
    date_str = game_date.strftime("%Y%m%d")  # YYYYMMDD format required by API
    url = f"{AN_BASE_URL}?bookIds={AN_BOOK_IDS}&date={date_str}&periods=event"
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_S)

    if resp.status_code == 404:
        log.info("[SKIP] No games returned for %s (HTTP 404)", game_date)
        return None
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as exc:
        log.warning("[SKIP] Non-JSON response for %s: %s", game_date, exc)
        return None


def _pick_outcome(outcomes: list[dict], side: str) -> dict | None:
    for o in outcomes or []:
        if o.get("side") == side:
            return o
    return None


def _pct(outcome: dict | None, kind: str) -> float | None:
    """kind is 'money' or 'tickets'; returns percent or None."""
    if not outcome:
        return None
    bi = outcome.get("bet_info") or {}
    section = bi.get(kind) or {}
    return section.get("percent")


def _market_with_data(
    markets_by_book: dict, market_type: str, sides: tuple[str, str]
) -> tuple[list[dict] | None, str | None]:
    """
    Pick a (market outcomes, book_id) tuple for `market_type` ('moneyline' or
    'total') where BOTH sides carry non-null, non-zero bet_info percentages.

    Some books carry the line + odds but report 0 on one side of the
    bet_info percentages — that is "no public-betting data for this book"
    rather than "0% public lean", and accepting it produces rows where
    home + away percentages no longer sum to ~100. We therefore require
    both sides to have a populated percent before a book qualifies.

    Prefers book 15 (FanDuel — the only book that consistently carries
    public-betting data) and falls back to any other book where both sides
    are populated.
    """
    book_order = [PREFERRED_BOOK_ID] + [
        b for b in markets_by_book.keys() if b != PREFERRED_BOOK_ID
    ]
    for book_id in book_order:
        book = markets_by_book.get(book_id) or {}
        event = book.get("event") or {}
        outcomes = event.get(market_type)
        if not outcomes:
            continue
        all_have_data = True
        for s in sides:
            o = _pick_outcome(outcomes, s)
            mp = _pct(o, "money")
            tp = _pct(o, "tickets")
            if not ((mp is not None and mp > 0) or (tp is not None and tp > 0)):
                all_have_data = False
                break
        if all_have_data:
            return outcomes, book_id
    return None, None


def parse_game(game: dict) -> dict | None:
    """
    Return a flat row dict for a single game. Any required field missing →
    None and the row is skipped.
    """
    teams = game.get("teams") or []
    home_team_id = game.get("home_team_id")
    away_team_id = game.get("away_team_id")
    home_abbr = away_abbr = None
    for t in teams:
        if t.get("id") == home_team_id:
            home_abbr = t.get("abbr")
        elif t.get("id") == away_team_id:
            away_abbr = t.get("abbr")
    if not home_abbr or not away_abbr:
        return None

    markets = game.get("markets") or {}
    if not isinstance(markets, dict) or not markets:
        return None

    ml_outcomes, ml_book   = _market_with_data(markets, "moneyline", ("home", "away"))
    tot_outcomes, tot_book = _market_with_data(markets, "total",     ("over", "under"))

    home_ml_money = home_ml_ticket = None
    away_ml_money = away_ml_ticket = None
    if ml_outcomes:
        home_o = _pick_outcome(ml_outcomes, "home")
        away_o = _pick_outcome(ml_outcomes, "away")
        home_ml_money  = _pct(home_o, "money")
        home_ml_ticket = _pct(home_o, "tickets")
        away_ml_money  = _pct(away_o, "money")
        away_ml_ticket = _pct(away_o, "tickets")

    over_money = over_ticket = under_money = under_ticket = None
    if tot_outcomes:
        over_o  = _pick_outcome(tot_outcomes, "over")
        under_o = _pick_outcome(tot_outcomes, "under")
        over_money   = _pct(over_o,  "money")
        over_ticket  = _pct(over_o,  "tickets")
        under_money  = _pct(under_o, "money")
        under_ticket = _pct(under_o, "tickets")

    # Skip games where neither market has data — nothing useful to store.
    if (
        home_ml_money is None and home_ml_ticket is None
        and over_money is None and over_ticket is None
    ):
        return None

    books_used = ",".join([b for b in (ml_book, tot_book) if b])

    return {
        "an_game_id":         str(game.get("id")) if game.get("id") is not None else None,
        "home_team_abbr":     (home_abbr or "").upper() or None,
        "away_team_abbr":     (away_abbr or "").upper() or None,
        "home_ml_money_pct":  home_ml_money,
        "away_ml_money_pct":  away_ml_money,
        "home_ml_ticket_pct": home_ml_ticket,
        "away_ml_ticket_pct": away_ml_ticket,
        "over_money_pct":     over_money,
        "under_money_pct":    under_money,
        "over_ticket_pct":    over_ticket,
        "under_ticket_pct":   under_ticket,
        "book_ids_used":      books_used or None,
    }


# ── Snowflake write ───────────────────────────────────────────────────────────

INSERT_SQL = f"""
INSERT INTO {TARGET_FQN} (
    game_date, an_game_id, home_team_abbr, away_team_abbr,
    home_ml_money_pct, away_ml_money_pct,
    home_ml_ticket_pct, away_ml_ticket_pct,
    over_money_pct, under_money_pct,
    over_ticket_pct, under_ticket_pct,
    book_ids_used, ingestion_timestamp
)
SELECT
    %(game_date)s::date,
    %(an_game_id)s::varchar,
    %(home_team_abbr)s::varchar,
    %(away_team_abbr)s::varchar,
    %(home_ml_money_pct)s::float,
    %(away_ml_money_pct)s::float,
    %(home_ml_ticket_pct)s::float,
    %(away_ml_ticket_pct)s::float,
    %(over_money_pct)s::float,
    %(under_money_pct)s::float,
    %(over_ticket_pct)s::float,
    %(under_ticket_pct)s::float,
    %(book_ids_used)s::varchar,
    CURRENT_TIMESTAMP
"""


def insert_rows(
    conn: snowflake.connector.SnowflakeConnection,
    game_date: date,
    rows: list[dict],
) -> int:
    if not rows:
        return 0
    payload = [{"game_date": game_date.isoformat(), **r} for r in rows]
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, payload)
    return len(payload)


# ── Per-date orchestration ────────────────────────────────────────────────────

def ingest_date(
    conn: snowflake.connector.SnowflakeConnection | None,
    game_date: date,
    *,
    dry_run: bool = False,
) -> int:
    """Returns number of rows written (or that would be written in dry-run)."""
    log.info("Fetching Action Network public betting for %s", game_date)
    try:
        data = fetch_public_betting(game_date)
    except requests.HTTPError as exc:
        log.warning("HTTP error fetching %s: %s", game_date, exc)
        return 0
    except requests.RequestException as exc:
        log.warning("Request failed for %s: %s", game_date, exc)
        return 0

    if not data:
        return 0

    games = data.get("games") or []
    if not games:
        log.info("[SKIP] No games returned for %s", game_date)
        return 0

    if dry_run:
        log.info("=== DRY RUN: raw JSON for first game on %s ===", game_date)
        print(json.dumps(games[0], indent=2)[:6000])
        log.info("=== END DRY RUN raw JSON ===")

    rows: list[dict] = []
    for g in games:
        row = parse_game(g)
        if row is not None:
            rows.append(row)

    if not rows:
        log.info("[SKIP] %s — no parseable rows (no book had populated percentages)", game_date)
        return 0

    log.info("  Parsed %d/%d game(s) with public-betting data", len(rows), len(games))

    if dry_run:
        log.info("Dry run — skipping Snowflake write. Sample row: %s", rows[0])
        return len(rows)

    assert conn is not None
    n = insert_rows(conn, game_date, rows)
    log.info("  Inserted %d row(s) into %s", n, TARGET_FQN)
    return n


# ── Backfill orchestration ────────────────────────────────────────────────────

def fetch_already_loaded_dates(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
) -> set[date]:
    sql = f"""
        SELECT DISTINCT game_date
        FROM {TARGET_FQN}
        WHERE game_date BETWEEN %(s)s::date AND %(e)s::date
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"s": start_date.isoformat(), "e": end_date.isoformat()})
        return {row[0] for row in cur.fetchall() if row[0]}


def daterange(start: date, end_inclusive: date):
    d = start
    while d <= end_inclusive:
        yield d
        d += timedelta(days=1)


def run_backfill(
    conn: snowflake.connector.SnowflakeConnection,
    start_date: date,
    end_date: date,
    *,
    skip_existing: bool = True,
) -> None:
    log.info("Backfill range: %s → %s", start_date, end_date)
    already_loaded: set[date] = (
        fetch_already_loaded_dates(conn, start_date, end_date)
        if skip_existing
        else set()
    )
    if already_loaded:
        log.info("  %d date(s) already loaded — will skip", len(already_loaded))

    total_rows = 0
    total_dates = 0
    skipped_empty = 0
    for d in daterange(start_date, end_date):
        if d in already_loaded:
            log.info("[SKIP] %s — already loaded", d)
            continue
        total_dates += 1
        n = ingest_date(conn, d)
        total_rows += n
        if n == 0:
            skipped_empty += 1
        time.sleep(BACKFILL_DELAY_S)
    log.info(
        "Backfill complete — %d date(s) attempted, %d empty/skipped, %d row(s) total",
        total_dates, skipped_empty, total_rows,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Ingest Action Network public-betting percentages into "
            f"{TARGET_FQN}."
        ),
    )
    p.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Single date to fetch. Defaults to today (UTC).",
    )
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Backfill mode — iterate over [start-date, end-date].",
    )
    p.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default="2021-04-01",
        help="Backfill start date inclusive (default: 2021-04-01).",
    )
    p.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Backfill end date inclusive (default: today).",
    )
    p.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="In backfill mode, do not skip dates already present in the target table.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse but do not write to Snowflake. Prints raw JSON for first game.",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    today = date.today()

    if args.dry_run and not args.backfill:
        target_date = (
            date.fromisoformat(args.date) if args.date else today
        )
        log.info("DRY RUN: %s → %s (no DB write)", target_date, TARGET_FQN)
        ingest_date(None, target_date, dry_run=True)
        return

    log.info("Connecting to Snowflake → %s", TARGET_FQN)
    conn = get_snowflake_connection()
    try:
        if args.backfill:
            start = date.fromisoformat(args.start_date)
            end   = date.fromisoformat(args.end_date) if args.end_date else today
            run_backfill(
                conn,
                start,
                end,
                skip_existing=not args.no_skip_existing,
            )
        else:
            target_date = (
                date.fromisoformat(args.date) if args.date else today
            )
            ingest_date(conn, target_date)
    finally:
        conn.close()
        log.info("Snowflake connection closed")


if __name__ == "__main__":
    main()
