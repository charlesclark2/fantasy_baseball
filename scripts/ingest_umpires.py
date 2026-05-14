"""
ingest_umpires.py
-----------------
Fetch today's HP umpire assignments from the MLB Stats API and upsert rows
into baseball_data.statsapi.umpire_game_log.

Endpoint: https://statsapi.mlb.com/api/v1/schedule
  ?sportId=1&date=YYYY-MM-DD&hydrate=officials

The officials array in each game contains entries with officialType.
Filter for officialType == "Home Plate" to get the HP umpire.

HP umpire assignments are announced morning of the game — run after 08:00 ET
before predict_today.py. Only umpire_name and umpire_id are written; tendency
metrics (k_pct, bb_pct, etc.) remain NULL. The dbt feature model computes
trailing z-scores from UmpScorecards historical rows; this script just stamps
the umpire_name so today's game_pk can join via umpire_name.

Usage:
    # Dry-run: print extracted assignments without writing
    uv run python scripts/ingest_umpires.py --date 2026-05-01 --dry-run

    # Live upsert for today
    uv run python scripts/ingest_umpires.py --date $(date +%Y-%m-%d)
"""

import argparse
import logging
import os
import sys
from datetime import date as date_type

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

STATSAPI_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"
TABLE_FQN = "baseball_data.statsapi.umpire_game_log"

INSERT_SQL = f"""
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
    'statsapi'::VARCHAR,
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


def fetch_hp_umpires(game_date: str) -> list[dict]:
    """Fetch HP umpire assignments for all games on game_date from MLB Stats API."""
    params = {
        "sportId": 1,
        "date": game_date,
        "hydrate": "officials",
    }
    try:
        resp = requests.get(STATSAPI_SCHEDULE_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("MLB Stats API request failed: %s", exc)
        sys.exit(1)

    data = resp.json()
    season = int(game_date[:4])
    results = []

    total_games = 0
    assigned = 0

    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            game_pk = game.get("gamePk")
            total_games += 1
            officials = game.get("officials", [])

            hp_official = None
            for official in officials:
                if official.get("officialType") == "Home Plate":
                    hp_official = official.get("official", {})
                    break

            if not hp_official:
                log.warning("[WARN] No HP umpire listed for game_pk=%s on %s — skipping.", game_pk, game_date)
                continue

            results.append({
                "game_pk": game_pk,
                "game_date": game_date,
                "season": season,
                "umpire_name": hp_official.get("fullName", "Unknown"),
                "umpire_id": str(hp_official.get("id", "")) or None,
            })
            assigned += 1

    log.info("Loaded HP umpire for %d of %d games on %s", assigned, total_games, game_date)
    return results


def insert_rows(conn, rows: list[dict]) -> int:
    with conn.cursor() as cur:
        for row in rows:
            cur.execute(INSERT_SQL, row)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Ingest daily HP umpire assignments from MLB Stats API")
    parser.add_argument("--date", required=True,
                        help="Game date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print extracted assignments without writing to Snowflake")
    args = parser.parse_args()

    assignments = fetch_hp_umpires(args.date)

    if args.dry_run:
        print(f"\n--- DRY RUN: HP umpire assignments for {args.date} ---")
        for a in assignments:
            print(f"  game_pk={a['game_pk']}  umpire={a['umpire_name']}  id={a['umpire_id']}")
        print(f"Total: {len(assignments)} assignments")
        return

    if not assignments:
        log.warning("No HP umpire assignments found for %s — nothing to write.", args.date)
        return

    log.info("Connecting to Snowflake...")
    conn = get_snowflake_conn()
    try:
        loaded = insert_rows(conn, assignments)
        log.info("Inserted %d HP umpire assignments for %s", loaded, args.date)
    except Exception as exc:
        log.error("Snowflake write failed: %s", exc)
        conn.close()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
