"""
ingest_savant_park_factors.py
------------------------------
Scrapes Baseball Savant statcast-park-factors page for per-park granular
park factors (HR, 1B, 2B, 3B, BB, SO, wOBA) and upserts into
baseball_data.fangraphs.savant_park_factors_raw.

Source: https://baseballsavant.mlb.com/leaderboard/statcast-park-factors?year=<YEAR>
The page embeds a JS variable `var data = [...]` containing all park factor
rows. Each row has both single-season and rolling views; we keep only the
3-year rolling / All bat-side rows (key_bat_side='All', key_num_years_rolling='3').

Venue IDs in Savant match MLB Stats API venue IDs (both use '19' for Coors).

Usage:
    # Current season
    uv run python scripts/ingest_savant_park_factors.py --season 2026 --dry-run
    uv run python scripts/ingest_savant_park_factors.py --season 2026

    # Backfill
    uv run python scripts/ingest_savant_park_factors.py --start-season 2016 --end-season 2025
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from fangraphs_client import _get_session           # noqa: E402
from snowflake_loader import get_snowflake_connection  # noqa: E402

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_TABLE = "baseball_data.fangraphs.savant_park_factors_raw"
_SAVANT_URL = "https://baseballsavant.mlb.com/leaderboard/statcast-park-factors"
_REQUEST_DELAY = 1.5


def _fetch_year(season: int) -> list[dict]:
    """Fetch all park factor rows for a season from Savant's embedded JS var."""
    sess = _get_session()
    resp = sess.get(
        _SAVANT_URL,
        params={"year": season},
        timeout=30,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://baseballsavant.mlb.com/",
        },
    )
    resp.raise_for_status()

    # Data is server-rendered as: var data = [...];
    matches = re.findall(r"var\s+data\s*=\s*(\[.*?\]);", resp.text, re.DOTALL)
    if not matches:
        raise ValueError(f"No 'var data = [...]' block found on page for season={season}")

    return json.loads(matches[0])


def _to_int_safe(val) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_rows(raw_rows: list[dict], season: int, run_id: str) -> list[dict]:
    """Filter to 3yr-rolling / All bat-side rows and normalise field names."""
    out = []
    for row in raw_rows:
        if row.get("key_bat_side") != "All":
            continue
        if row.get("key_num_years_rolling") != "3":
            continue
        # key_year from Savant matches the season we fetched — sanity check
        row_season = _to_int_safe(row.get("key_year"))
        if row_season is not None and row_season != season:
            log.warning(
                "key_year mismatch: expected %d, got %d for venue %s",
                season, row_season, row.get("venue_name"),
            )

        out.append({
            "venue_id":             _to_int_safe(row.get("venue_id")),
            "venue_name":           str(row.get("venue_name", "")),
            "season":               season,
            "bat_side":             str(row.get("key_bat_side", "All")),
            "num_years_rolling":    3,
            "n_pa":                 _to_int_safe(row.get("n_pa")),
            "index_runs":           _to_int_safe(row.get("index_runs")),
            "index_hr":             _to_int_safe(row.get("index_hr")),
            "index_1b":             _to_int_safe(row.get("index_1b")),
            "index_2b":             _to_int_safe(row.get("index_2b")),
            "index_3b":             _to_int_safe(row.get("index_3b")),
            "index_bb":             _to_int_safe(row.get("index_bb")),
            "index_so":             _to_int_safe(row.get("index_so")),
            "index_woba":           _to_int_safe(row.get("index_woba")),
            "index_hardhit":        _to_int_safe(row.get("index_hardhit")),
            "index_wobacon":        _to_int_safe(row.get("index_wobacon")),
            "index_xwobacon":       _to_int_safe(row.get("index_xwobacon")),
            "run_id":               run_id,
        })
    return out


def _upsert_rows(rows: list[dict], conn) -> int:
    """MERGE rows into savant_park_factors_raw via a VARCHAR temp table."""
    if not rows:
        return 0

    cur = conn.cursor()

    # Step 1: VARCHAR temp table
    cur.execute("""
        CREATE TEMPORARY TABLE IF NOT EXISTS _tmp_savant_pf (
            venue_id            VARCHAR,
            venue_name          VARCHAR,
            season              VARCHAR,
            bat_side            VARCHAR,
            num_years_rolling   VARCHAR,
            n_pa                VARCHAR,
            index_runs          VARCHAR,
            index_hr            VARCHAR,
            index_1b            VARCHAR,
            index_2b            VARCHAR,
            index_3b            VARCHAR,
            index_bb            VARCHAR,
            index_so            VARCHAR,
            index_woba          VARCHAR,
            index_hardhit       VARCHAR,
            index_wobacon       VARCHAR,
            index_xwobacon      VARCHAR,
            run_id              VARCHAR
        )
    """)
    cur.execute("TRUNCATE TABLE _tmp_savant_pf")

    cur.executemany(
        """
        INSERT INTO _tmp_savant_pf VALUES (
            %(venue_id)s, %(venue_name)s, %(season)s, %(bat_side)s,
            %(num_years_rolling)s, %(n_pa)s, %(index_runs)s, %(index_hr)s,
            %(index_1b)s, %(index_2b)s, %(index_3b)s, %(index_bb)s,
            %(index_so)s, %(index_woba)s, %(index_hardhit)s, %(index_wobacon)s,
            %(index_xwobacon)s, %(run_id)s
        )
        """,
        [
            {k: (str(v) if v is not None else None) for k, v in r.items()}
            for r in rows
        ],
    )

    # Step 2: MERGE into target
    cur.execute(f"""
        MERGE INTO {_TABLE} AS tgt
        USING (
            SELECT
                TRY_CAST(venue_id AS INTEGER)           AS venue_id,
                venue_name,
                TRY_CAST(season AS INTEGER)             AS season,
                bat_side,
                TRY_CAST(num_years_rolling AS INTEGER)  AS num_years_rolling,
                TRY_CAST(n_pa AS INTEGER)               AS n_pa,
                TRY_CAST(index_runs AS INTEGER)         AS index_runs,
                TRY_CAST(index_hr AS INTEGER)           AS index_hr,
                TRY_CAST(index_1b AS INTEGER)           AS index_1b,
                TRY_CAST(index_2b AS INTEGER)           AS index_2b,
                TRY_CAST(index_3b AS INTEGER)           AS index_3b,
                TRY_CAST(index_bb AS INTEGER)           AS index_bb,
                TRY_CAST(index_so AS INTEGER)           AS index_so,
                TRY_CAST(index_woba AS INTEGER)         AS index_woba,
                TRY_CAST(index_hardhit AS INTEGER)      AS index_hardhit,
                TRY_CAST(index_wobacon AS INTEGER)      AS index_wobacon,
                TRY_CAST(index_xwobacon AS INTEGER)     AS index_xwobacon,
                run_id
            FROM _tmp_savant_pf
        ) AS src
        ON  tgt.venue_id          = src.venue_id
        AND tgt.season            = src.season
        AND tgt.bat_side          = src.bat_side
        AND tgt.num_years_rolling = src.num_years_rolling
        WHEN MATCHED THEN UPDATE SET
            venue_name      = src.venue_name,
            n_pa            = src.n_pa,
            index_runs      = src.index_runs,
            index_hr        = src.index_hr,
            index_1b        = src.index_1b,
            index_2b        = src.index_2b,
            index_3b        = src.index_3b,
            index_bb        = src.index_bb,
            index_so        = src.index_so,
            index_woba      = src.index_woba,
            index_hardhit   = src.index_hardhit,
            index_wobacon   = src.index_wobacon,
            index_xwobacon  = src.index_xwobacon,
            run_id          = src.run_id,
            ingestion_ts    = CURRENT_TIMESTAMP
        WHEN NOT MATCHED THEN INSERT (
            venue_id, venue_name, season, bat_side, num_years_rolling,
            n_pa, index_runs, index_hr, index_1b, index_2b, index_3b,
            index_bb, index_so, index_woba, index_hardhit, index_wobacon,
            index_xwobacon, run_id
        ) VALUES (
            src.venue_id, src.venue_name, src.season, src.bat_side,
            src.num_years_rolling, src.n_pa, src.index_runs, src.index_hr,
            src.index_1b, src.index_2b, src.index_3b, src.index_bb,
            src.index_so, src.index_woba, src.index_hardhit, src.index_wobacon,
            src.index_xwobacon, src.run_id
        )
    """)
    return cur.rowcount


def ingest_season(season: int, dry_run: bool, conn) -> int:
    log.info("Fetching park factors for season=%d", season)
    raw_rows = _fetch_year(season)
    run_id = str(uuid.uuid4())
    rows = _parse_rows(raw_rows, season, run_id)
    log.info("  Parsed %d venues (3yr-rolling, All bat-side)", len(rows))

    if dry_run:
        for r in rows[:3]:
            log.info("  [DRY RUN] %s (venue_id=%s): hr=%s runs=%s bb=%s so=%s",
                     r["venue_name"], r["venue_id"],
                     r["index_hr"], r["index_runs"], r["index_bb"], r["index_so"])
        return len(rows)

    inserted = _upsert_rows(rows, conn)
    log.info("  Upserted %d rows for season=%d", inserted, season)
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Baseball Savant granular park factors into Snowflake"
    )
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--start-season", type=int, default=None)
    parser.add_argument("--end-season", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.season and (args.start_season or args.end_season):
        parser.error("Use --season OR --start-season/--end-season, not both")

    current_year = date.today().year
    if args.start_season:
        seasons = list(range(args.start_season, (args.end_season or current_year) + 1))
    else:
        seasons = [args.season or current_year]

    log.info("Ingesting park factors for %d season(s): %s", len(seasons), seasons)

    if args.dry_run:
        conn = None
    else:
        conn = get_snowflake_connection()

    try:
        total = 0
        for season in seasons:
            total += ingest_season(season, args.dry_run, conn)
            if len(seasons) > 1:
                time.sleep(_REQUEST_DELAY)
        log.info("Done. %d rows across %d season(s).", total, len(seasons))
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Ingestion failed")
        sys.exit(1)
