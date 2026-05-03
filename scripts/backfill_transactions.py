"""
backfill_transactions.py
------------------------
Historical backfill of MLB player roster transactions from the Stats API.
Iterates over a range of seasons and loads all transactions into
baseball_data.statsapi.player_transactions.

The Stats API transactions endpoint returns data from at least 2015 onward.
Our training window starts at 2021 (Stuff+ coverage begins 2020, training
cutoff set to game_year >= 2021 in Card 7.F). Run this script once before
Card 7.MA retraining to populate training-time IL signal.

The script calls ingest_transactions.py month-by-month (or season-by-season
for speed) and logs progress to avoid re-fetching already-loaded ranges.

Usage:
    # Backfill 2021 through 2025 (recommended before Card 7.MA retraining)
    uv run python scripts/backfill_transactions.py --start-season 2021 --end-season 2025

    # Dry-run — print record counts without writing
    uv run python scripts/backfill_transactions.py --start-season 2021 --end-season 2025 --dry-run

    # Single season
    uv run python scripts/backfill_transactions.py --start-season 2024 --end-season 2024
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

INGEST_SCRIPT = Path(__file__).parent / "ingest_transactions.py"

# Season boundaries (approximate — March through October)
SEASON_START_MONTH = 3   # March (spring training/Opening Day)
SEASON_END_MONTH   = 10  # October (end of regular season + playoffs)


def _season_date_range(season: int) -> tuple[str, str]:
    start = date(season, SEASON_START_MONTH, 1).isoformat()
    end = date(season, SEASON_END_MONTH, 31 if SEASON_END_MONTH == 10 else 30).isoformat()
    # Cap end at today so we don't request future dates
    today = date.today().isoformat()
    end = min(end, today)
    return start, end


def _run_ingest(start_date: str, end_date: str, dry_run: bool) -> bool:
    cmd = [
        sys.executable, str(INGEST_SCRIPT),
        "--start-date", start_date,
        "--end-date",   end_date,
    ]
    if dry_run:
        cmd.append("--dry-run")

    env = os.environ.copy()
    result = subprocess.run(cmd, env=env, capture_output=False)
    if result.returncode != 0:
        log.error("ingest_transactions.py failed for %s → %s (exit %d)", start_date, end_date, result.returncode)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill MLB player transactions for one or more historical seasons."
    )
    parser.add_argument("--start-season", required=True, type=int, help="First season year (e.g. 2021)")
    parser.add_argument("--end-season",   required=True, type=int, help="Last season year (inclusive, e.g. 2025)")
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run to ingest_transactions.py")
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Seconds to sleep between season requests (default: 2.0)",
    )
    args = parser.parse_args()

    if args.start_season > args.end_season:
        parser.error("--start-season must be <= --end-season")

    seasons = range(args.start_season, args.end_season + 1)
    log.info(
        "Backfilling %d season(s): %d–%d  [dry_run=%s]",
        len(seasons), args.start_season, args.end_season, args.dry_run,
    )

    failed = []
    for season in seasons:
        start, end = _season_date_range(season)
        log.info("Season %d: %s → %s", season, start, end)
        ok = _run_ingest(start, end, args.dry_run)
        if not ok:
            failed.append(season)
        if args.delay > 0 and season != args.end_season:
            time.sleep(args.delay)

    if failed:
        log.error("Failed seasons: %s", failed)
        sys.exit(1)

    log.info(
        "Backfill complete. %d/%d seasons succeeded.",
        len(seasons) - len(failed),
        len(seasons),
    )


if __name__ == "__main__":
    main()
