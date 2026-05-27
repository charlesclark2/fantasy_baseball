"""
backfill_eb_posteriors.py — Backfill EB posteriors for historical game dates.

Queries all distinct game dates from stg_statsapi_lineups for the specified
season range and runs compute_lineup_posteriors.py for each date.

Usage:
    uv run python betting_ml/scripts/backfill_eb_posteriors.py
    uv run python betting_ml/scripts/backfill_eb_posteriors.py --from-season 2024
    uv run python betting_ml/scripts/backfill_eb_posteriors.py --from-season 2021 --to-season 2023
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection


def _load_game_dates(from_season: int, to_season: int) -> list[date]:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT official_date
            FROM baseball_data.betting.stg_statsapi_lineups
            WHERE year(official_date) BETWEEN %(from_season)s AND %(to_season)s
              AND batting_order = 1
            ORDER BY official_date
            """,
            {"from_season": from_season, "to_season": to_season},
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill EB posteriors for historical game dates")
    parser.add_argument("--from-season", type=int, default=2021)
    parser.add_argument("--to-season", type=int, default=date.today().year)
    args = parser.parse_args()

    print(f"Loading game dates {args.from_season}–{args.to_season}...")
    dates = _load_game_dates(args.from_season, args.to_season)
    print(f"  {len(dates)} game dates to process\n")

    script = _PROJECT_ROOT / "betting_ml" / "scripts" / "eb_priors" / "compute_lineup_posteriors.py"
    python = sys.executable

    errors = []
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
        print(f"[{i:4d}/{len(dates)}] {date_str}", end="  ", flush=True)
        result = subprocess.run(
            [python, str(script), "--game-date", date_str],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR")
            errors.append((date_str, result.stderr[-200:]))
        else:
            # Extract summary line from stdout
            lines = [l for l in result.stdout.splitlines() if "rows" in l.lower() or "done" in l.lower()]
            print(" | ".join(lines[-2:]) if lines else "done")

    print(f"\n{'─'*60}")
    print(f"Completed: {len(dates) - len(errors)}/{len(dates)} dates")
    if errors:
        print(f"Errors ({len(errors)}):")
        for date_str, msg in errors[:10]:
            print(f"  {date_str}: {msg}")


if __name__ == "__main__":
    main()
