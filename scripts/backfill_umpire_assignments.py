"""
backfill_umpire_assignments.py
------------------------------
Backfill historical HP umpire assignments for completed MLB games (2021–2026)
into baseball_data.statsapi.umpire_game_log.

Source: MLB Stats API live feed endpoint
  GET https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live
  → gameData.officials[].officialType == "Home Plate"

Strategy:
  1. Query mart_game_results for all completed regular-season game_pks.
  2. Skip game_pks that already have a row in umpire_game_log with
     data_source IN ('statsapi', 'statsapi_backfill') (any source is valid).
  3. For each remaining game_pk, hit the live feed, extract the HP umpire,
     and INSERT with data_source='statsapi_backfill'.
  4. Throttle to ~1 req/s to stay within Stats API limits.

Usage:
    # Full backfill 2021–2026
    uv run python scripts/backfill_umpire_assignments.py

    # Single season
    uv run python scripts/backfill_umpire_assignments.py --start-year 2025 --end-year 2025

    # Dry-run (list game_pks without writing)
    uv run python scripts/backfill_umpire_assignments.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import date

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

# E11.1-W11 Tier-B: leg-gated dual-write (W11_RAW_WRITE_MODE) to lakehouse_raw/umpire_game_log/.
from utils.lakehouse_raw_writer import (  # noqa: E402
    lakehouse_write_legs,
    umpire_mirror_rows,
    w11_write_mode,
    write_raw_rows_s3,
)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

_LAKEHOUSE_SOURCE = "umpire_game_log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_FQN        = "baseball_data.statsapi.umpire_game_log"
LIVE_FEED_URL    = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
REQUEST_DELAY    = 1.0   # seconds between API calls
REQUEST_TIMEOUT  = 30
MAX_RETRIES      = 3
RETRY_BACKOFF    = 10

_PENDING_GAMES_SQL = """
    SELECT DISTINCT game_pk, game_date, game_year
    FROM baseball_data.betting.mart_game_results
    WHERE game_type = 'R'
      AND game_year BETWEEN %(start_year)s AND %(end_year)s
      AND game_pk NOT IN (
          SELECT DISTINCT game_pk
          FROM baseball_data.statsapi.umpire_game_log
          WHERE data_source IN ('statsapi', 'statsapi_backfill', 'umpscorecards')
      )
    ORDER BY game_date
"""

_INSERT_SQL = f"""
INSERT INTO {TABLE_FQN} (
    game_pk, game_date, season, umpire_name, umpire_id,
    k_pct, bb_pct, total_runs, called_strikes_above_avg,
    run_expectancy_delta, total_run_impact, accuracy_above_expected,
    data_source, loaded_at
)
SELECT
    %(game_pk)s::INTEGER,
    %(game_date)s::DATE,
    %(season)s::INTEGER,
    %(umpire_name)s::VARCHAR,
    %(umpire_id)s::VARCHAR,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::INTEGER,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::FLOAT,
    NULL::FLOAT,
    'statsapi_backfill'::VARCHAR,
    CURRENT_TIMESTAMP()
"""


def _load_private_key() -> bytes | None:
    key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
    if not key_path:
        return None
    with open(key_path, "rb") as fh:
        raw = fh.read()
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    key = load_pem_private_key(
        raw,
        password=passphrase.encode() if passphrase else None,
        backend=default_backend(),
    )
    return key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())


def get_snowflake_conn():
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
        role=os.environ.get("SNOWFLAKE_ROLE"),
        database="baseball_data",
        schema="statsapi",
    )
    pk = _load_private_key()
    if pk:
        kwargs["private_key"] = pk
    else:
        kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**kwargs)


def fetch_hp_umpire(game_pk: int) -> dict | None:
    """Fetch HP umpire from the live feed endpoint. Returns {name, id} or None."""
    url = LIVE_FEED_URL.format(game_pk=game_pk)
    backoff = RETRY_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            officials = data.get("gameData", {}).get("officials", [])
            for official in officials:
                if official.get("officialType") == "Home Plate":
                    o = official.get("official", {})
                    return {
                        "umpire_name": o.get("fullName", "Unknown"),
                        "umpire_id":   str(o.get("id", "")) or None,
                    }
            log.warning("  game_pk=%d: no HP official found in live feed", game_pk)
            return None
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                log.warning("  game_pk=%d: 404 — game not found, skipping", game_pk)
                return None
            log.warning("  [%d/%d] HTTP %s for game_pk=%d",
                        attempt, MAX_RETRIES, exc.response.status_code, game_pk)
        except requests.RequestException as exc:
            log.warning("  [%d/%d] Request error for game_pk=%d: %s", attempt, MAX_RETRIES, game_pk, exc)

        if attempt < MAX_RETRIES:
            log.info("  Retrying in %ds…", backoff)
            time.sleep(backoff)
            backoff *= 2

    log.error("  game_pk=%d: all %d attempts failed", game_pk, MAX_RETRIES)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill historical HP umpire assignments from MLB Stats API"
    )
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year",   type=int, default=date.today().year)
    parser.add_argument("--dry-run", action="store_true",
                        help="List pending game_pks without writing to Snowflake")
    args = parser.parse_args()

    log.info("Connecting to Snowflake…")
    conn = get_snowflake_conn()

    try:
        with conn.cursor() as cur:
            cur.execute(_PENDING_GAMES_SQL, {
                "start_year": args.start_year,
                "end_year":   args.end_year,
            })
            rows = cur.fetchall()

        games = [{"game_pk": r[0], "game_date": r[1], "season": r[2]} for r in rows]  # r[2] = game_year
        log.info("Found %d game_pks needing umpire backfill (%d–%d)",
                 len(games), args.start_year, args.end_year)

        if args.dry_run:
            for g in games[:20]:
                print(f"  game_pk={g['game_pk']}  date={g['game_date']}  season={g['season']}")
            if len(games) > 20:
                print(f"  … and {len(games) - 20} more")
            return

        # E11.1-W11 Tier-B: which legs run. The pending-games query above always reads Snowflake
        # (mart_game_results — still live during migration); only the WRITE legs are gated.
        do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

        inserted = 0
        skipped  = 0
        mirror_src: list[dict] = []   # rows to mirror to S3 at the end (data_source='statsapi_backfill')
        for i, g in enumerate(games, start=1):
            game_pk  = g["game_pk"]
            log.info("[%d/%d] game_pk=%d  date=%s", i, len(games), game_pk, g["game_date"])

            umpire = fetch_hp_umpire(game_pk)
            if umpire is None:
                skipped += 1
            else:
                row = {
                    "game_pk":     game_pk,
                    "game_date":   str(g["game_date"]),
                    "season":      g["season"],
                    "umpire_name": umpire["umpire_name"],
                    "umpire_id":   umpire["umpire_id"],
                }
                if do_sf:
                    with conn.cursor() as cur:
                        cur.execute(_INSERT_SQL, row)
                if do_s3:
                    mirror_src.append(row)
                log.info("  Inserted: %s (id=%s)", umpire["umpire_name"], umpire["umpire_id"])
                inserted += 1

            time.sleep(REQUEST_DELAY)

        if do_s3 and mirror_src:
            mirror_rows = umpire_mirror_rows(mirror_src, data_source="statsapi_backfill")
            n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append")
            log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)

        log.info("Backfill complete — %d inserted, %d skipped (no HP official found).",
                 inserted, skipped)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
