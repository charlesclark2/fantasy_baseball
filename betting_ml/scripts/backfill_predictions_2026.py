"""Card 6.G — Backfill 2026 predictions.

Runs predict_today.py for every 2026 regular-season date that has finalized
game results in mart_game_results but no existing rows in daily_model_predictions.
Produces parquet + CSV outputs and Snowflake rows for each date, enabling the
Card 6.E Performance Tracker to analyse model vs. market performance.

Run from project root:
    uv run python betting_ml/scripts/backfill_predictions_2026.py
    uv run python betting_ml/scripts/backfill_predictions_2026.py --force
    uv run python betting_ml/scripts/backfill_predictions_2026.py --start-date 2026-03-27
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection


_GAME_DATES_QUERY = """
SELECT DISTINCT game_date::DATE AS game_date
FROM baseball_data.betting.mart_game_results
WHERE game_date >= '{start_date}'
  AND game_date < CURRENT_DATE()
  AND game_type = 'R'
ORDER BY game_date
"""

_ALREADY_SCORED_QUERY = """
SELECT DISTINCT score_date::DATE AS score_date
FROM baseball_data.betting_ml.daily_model_predictions
WHERE score_date >= '{start_date}'
  AND score_date < CURRENT_DATE()
"""


def _get_game_dates(start_date: str) -> list[str]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_GAME_DATES_QUERY.format(start_date=start_date))
        return [str(row[0]) for row in cur.fetchall()]
    finally:
        conn.close()


def _get_already_scored(start_date: str) -> set[str]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(_ALREADY_SCORED_QUERY.format(start_date=start_date))
            return {str(row[0]) for row in cur.fetchall()}
        except Exception:
            # Table may not exist yet if no successful writes have occurred.
            return set()
    finally:
        conn.close()


def _run_date(date_str: str) -> bool:
    result = subprocess.run(
        ["uv", "run", "python", "betting_ml/scripts/predict_today.py", "--date", date_str],
        cwd=str(PROJECT_ROOT),
        capture_output=False,
    )
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill predict_today.py for all 2026 regular-season dates."
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default="2026-03-27",
        help="Earliest game date to process (default: 2026-03-27, Opening Day)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run dates that already have rows in daily_model_predictions",
    )
    args = parser.parse_args()

    print(f"Fetching 2026 regular-season game dates from {args.start_date}...")
    game_dates = _get_game_dates(args.start_date)
    print(f"  Found {len(game_dates)} date(s) with finalized results")

    if not game_dates:
        print("Nothing to backfill.")
        return

    if args.force:
        dates_to_run = game_dates
    else:
        already_scored = _get_already_scored(args.start_date)
        dates_to_run = [d for d in game_dates if d not in already_scored]
        skipped = len(game_dates) - len(dates_to_run)
        if skipped:
            print(f"  Skipping {skipped} date(s) already in daily_model_predictions "
                  f"(use --force to reprocess)")

    if not dates_to_run:
        print("All dates already scored. Use --force to reprocess.")
        return

    print(f"  Processing {len(dates_to_run)} date(s): "
          f"{dates_to_run[0]} → {dates_to_run[-1]}\n")

    succeeded: list[str] = []
    failed: list[str] = []

    for i, d in enumerate(dates_to_run, 1):
        print(f"[{i}/{len(dates_to_run)}] {d}")
        print("-" * 60)
        ok = _run_date(d)
        (succeeded if ok else failed).append(d)
        print()

    print("=" * 60)
    print(f"Backfill complete: {len(succeeded)} succeeded, {len(failed)} failed")
    if failed:
        print(f"Failed dates: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
