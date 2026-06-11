"""
backfill_eb_posteriors.py — Backfill lineup EB posteriors over a season range.

A2.8 spend fix: this used to spawn a FRESH OS subprocess per game date
(`compute_lineup_posteriors.py --game-date <d>`) — hundreds of Python
cold-starts + Snowflake auth handshakes, each then doing its own per-date
CREATE-TEMP + INSERT + MERGE round-trip. That pattern was the warehouse-uptime
burn flagged in the dbt/Snowflake spend audit.

It now calls the in-process, batched `main_backfill_season(season)` directly:
one connection per season, all dates computed in-process, then a SINGLE
temp-table + INSERT + MERGE for the whole season.

NOTE: this wrapper covers the LINEUP posteriors only. The starter and bullpen
posteriors have their own batched backfill entry points:
    uv run python betting_ml/scripts/eb_priors/compute_starter_posteriors.py --backfill-season <YEAR>
    uv run python betting_ml/scripts/eb_priors/compute_bullpen_posteriors.py --backfill-season <YEAR>
and archetype:
    uv run python betting_ml/scripts/eb_priors/compute_archetype_posteriors.py --mode backfill --season <YEAR>

Usage:
    uv run python betting_ml/scripts/backfill_eb_posteriors.py
    uv run python betting_ml/scripts/backfill_eb_posteriors.py --from-season 2024
    uv run python betting_ml/scripts/backfill_eb_posteriors.py --from-season 2021 --to-season 2023
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.eb_priors.compute_lineup_posteriors import (
    main_backfill_season as backfill_lineup_season,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill lineup EB posteriors over a season range (batched, in-process)"
    )
    parser.add_argument("--from-season", type=int, default=2021)
    parser.add_argument("--to-season", type=int, default=date.today().year)
    args = parser.parse_args()

    seasons = list(range(args.from_season, args.to_season + 1))
    print(f"Backfilling lineup EB posteriors for seasons {seasons} (batched per season)\n")

    errors: list[tuple[int, str]] = []
    for season in seasons:
        try:
            backfill_lineup_season(season)
        except FileNotFoundError as e:
            # Missing prior JSON for that season — skip, don't abort the range.
            print(f"  SKIP season {season}: {e}")
            errors.append((season, str(e)))

    print(f"\n{'─'*60}")
    print(f"Completed: {len(seasons) - len(errors)}/{len(seasons)} seasons")
    if errors:
        print(f"Skipped ({len(errors)}):")
        for season, msg in errors:
            print(f"  {season}: {msg[:160]}")


if __name__ == "__main__":
    main()
