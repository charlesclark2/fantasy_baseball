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
from dotenv import load_dotenv

# E11.1-W11 Tier-B: leg-gated dual-write (W11_RAW_WRITE_MODE). SF INSERT on 'snowflake'/'both';
# an S3 mirror to lakehouse_raw/umpire_game_log/ on 's3'/'both'. Default 'snowflake' → unchanged.
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


def get_snowflake_conn():
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="statsapi")


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
    # Idempotent: replace any existing statsapi assignment rows for these game_pks
    # before inserting. The append-only INSERT used to bloat the table when the
    # daily early+late ops AND the afternoon lineup_monitor ticks (Story 30.5) each
    # re-ran for the same day. Scoped to data_source='statsapi' so it never touches
    # the umpscorecards tendency rows for the same game_pk (settled games carry
    # both; the dbt staging model prefers umpscorecards).
    game_pks = [int(r["game_pk"]) for r in rows if r.get("game_pk") is not None]
    with conn.cursor() as cur:
        if game_pks:
            pk_list = ", ".join(str(pk) for pk in game_pks)
            cur.execute(
                f"DELETE FROM {TABLE_FQN} "
                f"WHERE data_source = 'statsapi' AND game_pk IN ({pk_list})"
            )
        for row in rows:
            cur.execute(INSERT_SQL, row)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Ingest daily HP umpire assignments from MLB Stats API")
    parser.add_argument("--date", required=True,
                        help="Game date in YYYY-MM-DD format")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print extracted assignments without writing to Snowflake")
    parser.add_argument("--skip-if-exists", action="store_true",
                        help=(
                            "E11.11: skip ingest if today's statsapi umpire assignments "
                            "are already in the table. MLB posts assignments once (afternoon); "
                            "subsequent lineup_monitor fires are no-ops."
                        ))
    args = parser.parse_args()

    # E11.1-W11 Tier-B: which legs run (SF INSERT and/or S3 mirror) per W11_RAW_WRITE_MODE.
    do_sf, do_s3 = lakehouse_write_legs(w11_write_mode())

    # E11.11 — once-captured guard: skip the MLB API call if today's data is already present.
    # The delete-then-insert is idempotent, but hitting the API and re-writing on every
    # lineup_monitor fire (~every 10 min) is wasteful after the first successful ingest.
    # SF-leg-only optimization (there's no Snowflake to check in s3-only mode).
    if args.skip_if_exists and not args.dry_run and do_sf:
        conn = get_snowflake_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {TABLE_FQN} "
                    f"WHERE game_date = %(d)s AND data_source = 'statsapi'",
                    {"d": args.date},
                )
                existing = cur.fetchone()[0]
        finally:
            conn.close()
        if existing > 0:
            log.info("[E11.11] %d umpire assignment(s) already ingested for %s, skipping.",
                     existing, args.date)
            return

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

    if do_sf:
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

    if do_s3:
        # data_source='statsapi' (today's HP-name assignment); tendency cols NULL.
        mirror_rows = umpire_mirror_rows(assignments, data_source="statsapi")
        n_s3 = write_raw_rows_s3(_LAKEHOUSE_SOURCE, mirror_rows, mode="append")
        log.info("mirrored %d row(s) → S3 lakehouse_raw/%s/", n_s3, _LAKEHOUSE_SOURCE)


if __name__ == "__main__":
    main()
