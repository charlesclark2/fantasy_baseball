"""
ingest_fangraphs_stuff_plus.py
--------------------------------
Fetches the FanGraphs Stuff+ pitching leaderboard (type=36) and appends rows
to baseball_data.fangraphs.fg_stuff_plus_raw.

Each row captures one pitcher's Stuff+, Location+, and Pitching+ for the
requested season window across rolling windows, allowing us to track how
stuff grades change over the course of a season.

Stuff+ stabilises after ~3 outings (per Eno Sarris), so 14d and 30d windows
are the primary units. 7d is intentionally excluded as too noisy for pitchers.

Window types:
  14d    -- non-overlapping 14-day windows from season start to season end
  30d    -- non-overlapping 30-day windows
  season -- one request covering the full season

Stuff+ data is available from the 2020 season onward.
Season boundaries come from the MLB Stats API (regularSeasonStartDate /
regularSeasonEndDate). Falls back to April 1 / October 1 if unavailable.

Key metrics captured in raw_json (type=36 leaderboard):
  sp_stuff, sp_location, sp_pitching,
  plus per-pitch variants: sp_s_FF, sp_l_FF, sp_p_FF, sp_s_SL, etc.

Usage:
    # Dry-run current season
    uv run python scripts/ingest_fangraphs_stuff_plus.py --season 2026 --dry-run

    # Load current season (14d + 30d + season windows)
    uv run python scripts/ingest_fangraphs_stuff_plus.py --season 2026

    # Historical backfill (Stuff+ starts 2020)
    uv run python scripts/ingest_fangraphs_stuff_plus.py --start-season 2020 --end-season 2025

    # Specific window types only
    uv run python scripts/ingest_fangraphs_stuff_plus.py --season 2026 --window-types 30d,season
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "utils"))
from fangraphs_client import fetch_leaderboard, FangraphsClientError  # noqa: E402
from snowflake_loader import get_snowflake_connection, append_raw_rows  # noqa: E402

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

TABLE_FQN = "baseball_data.fangraphs.fg_stuff_plus_raw"
STUFF_PLUS_TYPE_ID = 36
STUFF_PLUS_FIRST_SEASON = 2020
CURRENT_YEAR = date.today().year

WINDOW_DAYS = {"14d": 14, "30d": 30}
VALID_WINDOW_TYPES = {"14d", "30d", "season"}

REQUEST_DELAY_SECONDS = 1.0

_season_dates_cache: dict[int, tuple[date, date]] = {}


def _season_dates(season: int) -> tuple[date, date]:
    if season in _season_dates_cache:
        return _season_dates_cache[season]

    try:
        resp = requests.get(
            "https://statsapi.mlb.com/api/v1/seasons",
            params={"sportId": 1, "season": season},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        info = data["seasons"][0]
        start = date.fromisoformat(info["regularSeasonStartDate"])
        end = date.fromisoformat(info["regularSeasonEndDate"])
        log.info("MLB season %d: %s → %s", season, start, end)
    except Exception as exc:
        log.warning("MLB Stats API season lookup failed for %d (%s); using defaults", season, exc)
        start = date(season, 4, 1)
        end = date(season, 10, 1)

    if season == CURRENT_YEAR:
        end = min(end, date.today())

    _season_dates_cache[season] = (start, end)
    return start, end


def _windows_for_type(window_type: str, season: int) -> list[tuple[date, date]]:
    season_start, season_end = _season_dates(season)

    if window_type == "season":
        return [(season_start, season_end)]

    step = timedelta(days=WINDOW_DAYS[window_type])
    windows = []
    cursor = season_start
    while cursor < season_end:
        w_end = min(cursor + step - timedelta(days=1), season_end)
        windows.append((cursor, w_end))
        cursor += step
    return windows


def ingest_window(
    season: int,
    window_type: str,
    window_start: date,
    window_end: date,
    dry_run: bool,
    conn,
    errors: list,
) -> int:
    startdate_str = window_start.isoformat()
    enddate_str = window_end.isoformat()

    try:
        result = fetch_leaderboard(
            stats="pit",
            type_id=STUFF_PLUS_TYPE_ID,
            season=season,
            startdate=startdate_str,
            enddate=enddate_str,
        )
    except FangraphsClientError as exc:
        log.warning(
            "Window %s %s→%s FAILED: %s", window_type, startdate_str, enddate_str, exc
        )
        errors.append({
            "season": season,
            "window_type": window_type,
            "window_start": startdate_str,
            "window_end": enddate_str,
            "error": str(exc),
        })
        return 0

    data = result["data"]
    log.info(
        "Window %s %s→%s: %d pitchers", window_type, startdate_str, enddate_str, len(data)
    )

    if dry_run:
        return len(data)

    rows = [
        {
            "season":           season,
            "pitcher_name":     player.get("Name") or player.get("PlayerName"),
            "fg_pitcher_id":    str(player.get("playerid", "")),
            "load_id":          result["load_id"],
            "source_endpoint":  result["source_endpoint"],
            "request_params":   result["request_params"],
            "http_status_code": result["http_status_code"],
            "raw_json":         player,
        }
        for player in data
    ]

    return append_raw_rows(TABLE_FQN, rows, conn)


def ingest_season(
    season: int,
    window_types: list[str],
    dry_run: bool,
    conn,
    errors: list,
) -> int:
    if season < STUFF_PLUS_FIRST_SEASON:
        log.warning("Stuff+ data not available before %d; skipping season=%d", STUFF_PLUS_FIRST_SEASON, season)
        return 0

    total = 0
    for window_type in window_types:
        windows = _windows_for_type(window_type, season)
        log.info(
            "Season %d / %s: %d window(s) to ingest", season, window_type, len(windows)
        )
        for window_start, window_end in windows:
            total += ingest_window(
                season, window_type, window_start, window_end, dry_run, conn, errors
            )
            time.sleep(REQUEST_DELAY_SECONDS)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest FanGraphs Stuff+ pitching leaderboard rolling windows into Snowflake"
    )
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--start-season", type=int, default=None)
    parser.add_argument("--end-season", type=int, default=None)
    parser.add_argument(
        "--window-types",
        default="14d,30d,season",
        help="Comma-separated list of window types: 14d, 30d, season (default: all three)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.season and (args.start_season or args.end_season):
        parser.error("Use --season OR --start-season/--end-season, not both")

    window_types = [w.strip() for w in args.window_types.split(",")]
    invalid = set(window_types) - VALID_WINDOW_TYPES
    if invalid:
        parser.error(f"Invalid window types: {invalid}. Valid: {VALID_WINDOW_TYPES}")

    if args.start_season:
        seasons = list(range(args.start_season, (args.end_season or CURRENT_YEAR) + 1))
    else:
        seasons = [args.season or CURRENT_YEAR]

    if args.dry_run:
        all_windows = sum(
            len(_windows_for_type(wt, s))
            for s in seasons
            for wt in window_types
        )
        first_season = seasons[0]
        first_wt = window_types[0]
        first_window = _windows_for_type(first_wt, first_season)[0]
        log.info(
            "[DRY RUN] %d season(s), window types=%s, total API calls=%d",
            len(seasons), window_types, all_windows,
        )
        log.info(
            "[DRY RUN] First window: season=%d type=%s %s→%s",
            first_season, first_wt,
            first_window[0].isoformat(), first_window[1].isoformat(),
        )
        return

    errors: list[dict] = []
    conn = get_snowflake_connection()
    try:
        total = 0
        for season in seasons:
            total += ingest_season(season, window_types, False, conn, errors)
        log.info("Done. %d rows across %d season(s).", total, len(seasons))
    finally:
        conn.close()

    if errors:
        error_path = Path(__file__).parent / "ingest_errors.json"
        existing = json.loads(error_path.read_text()) if error_path.exists() else []
        error_path.write_text(json.dumps(existing + errors, indent=2))
        log.warning("%d window(s) failed — see %s", len(errors), error_path)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Ingestion failed")
        sys.exit(1)
