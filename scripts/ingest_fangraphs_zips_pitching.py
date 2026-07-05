"""
ingest_fangraphs_zips_pitching.py
----------------------------------
Fetches FanGraphs ZiPS / Steamer pitching projections and appends rows to
baseball_data.fangraphs.fg_zips_pitching_raw.

Historical ZiPS type conventions:
  Current season (2026): type=rzips  (rolling / restated ZiPS)
  Past seasons:          type=zips_YYYY  (e.g. zips_2022)
  Steamer current:       type=steamer
  Steamer historical:    type=steamer_YYYY (e.g. steamer_2022)

Usage:
    # Dry-run — current season
    uv run python scripts/ingest_fangraphs_zips_pitching.py --season 2026 --dry-run

    # Load current season
    uv run python scripts/ingest_fangraphs_zips_pitching.py --season 2026

    # Historical backfill 2020–2025
    uv run python scripts/ingest_fangraphs_zips_pitching.py --start-season 2020 --end-season 2025

    # Steamer projections
    uv run python scripts/ingest_fangraphs_zips_pitching.py --season 2026 --projection-type steamer
"""

import argparse
import logging
import os
import sys
from datetime import date

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from fangraphs_client import fetch_projections, FangraphsClientError  # noqa: E402
from snowflake_loader import get_snowflake_connection, append_raw_rows  # noqa: E402

# E11.1-W11-FG: this writer stays SNOWFLAKE-ONLY, matching the zips_hitting sibling. ZiPS pitching is
# pre-season-static; the stg_fangraphs__zips_pitching duckdb branch reads the export-bridge SNAPSHOT
# (export_w4_raw_to_s3.py → lakehouse/fg_zips_pitching_raw/), NOT a live-writer lakehouse_raw/ mirror,
# so there is nothing for a dual-write to feed. Re-run the bridge after an annual CSV load to refresh S3.

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_FQN = "baseball_data.fangraphs.fg_zips_pitching_raw"
CURRENT_YEAR = date.today().year


def _api_type(season: int, projection_family: str) -> str:
    """Return the FanGraphs API type string for the given season and projection family."""
    if projection_family == "steamer":
        return "steamer" if season == CURRENT_YEAR else f"steamer_{season}"
    return "rzips" if season == CURRENT_YEAR else f"zips_{season}"


def ingest_season(
    season: int,
    projection_type: str,
    dry_run: bool,
    conn,
) -> int:
    api_type = _api_type(season, projection_type)
    log.info(
        "Fetching %s pitching projections: season=%d api_type=%s",
        projection_type, season, api_type,
    )

    result = fetch_projections(proj_type=api_type, stats="pit", season=season)
    data = result["data"]

    if dry_run:
        log.info("[DRY RUN] %d pitchers returned. Sample: %s", len(data), data[0] if data else "N/A")
        return len(data)

    rows = [
        {
            "season":           season,
            "pitcher_name":     player.get("PlayerName") or player.get("Name"),
            "fg_pitcher_id":    str(player.get("playerid", "")),
            "projection_type":  projection_type,
            "load_id":          result["load_id"],
            "source_endpoint":  result["source_endpoint"],
            "request_params":   result["request_params"],
            "http_status_code": result["http_status_code"],
            "raw_json":         player,
        }
        for player in data
    ]

    inserted = append_raw_rows(TABLE_FQN, rows, conn)
    log.info(
        "Loaded %d ZiPS pitching rows for season=%d, projection_type=%s",
        inserted, season, projection_type,
    )
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest FanGraphs ZiPS/Steamer pitching projections into Snowflake"
    )
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--start-season", type=int, default=None)
    parser.add_argument("--end-season", type=int, default=None)
    parser.add_argument(
        "--projection-type",
        default="rzips",
        choices=["rzips", "steamer"],
        help="Projection family (default: rzips)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.season and (args.start_season or args.end_season):
        parser.error("Use --season OR --start-season/--end-season, not both")

    if args.start_season:
        seasons = list(range(args.start_season, (args.end_season or CURRENT_YEAR) + 1))
    else:
        seasons = [args.season or CURRENT_YEAR]

    conn = None if args.dry_run else get_snowflake_connection()
    try:
        total = 0
        for season in seasons:
            total += ingest_season(season, args.projection_type, args.dry_run, conn)
        log.info("Done. %d rows across %d season(s).", total, len(seasons))
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Ingestion failed")
        sys.exit(1)
