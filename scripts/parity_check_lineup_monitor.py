#!/usr/bin/env python3
"""
scripts/parity_check_lineup_monitor.py  (E11.20 phase-2a — the LINEUP_MONITOR_S3 flip gate)

Compares the lineup monitor's DETECTION reads between the two backends for a given date:
  Snowflake (default path)  vs  DuckDB-over-S3 (LINEUP_MONITOR_S3=1)

Checked, per date:
  1. candidate game set          (stg_statsapi_lineups_wide, both sides posted)
  2. per-game min_slots_filled   (the INC-32 readiness signal — a drift here would change
                                  WHICH games are held vs scored, so it must match exactly)
  3. probable starter IDs        (home/away — drives the pitcher-change re-trigger)
  4. games with a post_lineup    (daily_model_predictions — the Step-2b retry set)

Exit 0 = PARITY PASSED (safe to flip). Exit 1 = a mismatch is printed per game_pk.

⚠️ This is the ONLY sanctioned Snowflake read in phase-2a — it opens exactly one session.
Run it OUTSIDE the AC-C measurement window (or accept the one wake), and prefer the BOX so
the instance role + the same lakehouse the monitor will read are in play:

  docker compose -f services/dagster/aws/docker-compose.yml exec -T \\
      -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \\
      python scripts/parity_check_lineup_monitor.py --date 2026-07-21

State parity (lineup_monitor_state → DynamoDB) is NOT compared here: the Dynamo store starts
empty by design, so the first flipped day re-triggers nothing historical — it simply records
that day's confirmations. Verify it by running the monitor once with the flag on and
confirming a `lineup_monitor#<date>#<game_pk>` item appears per triggered game.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_MONITOR = Path(__file__).resolve().parent / "lineup_monitor.py"


def _load_monitor(s3_mode: bool):
    """Import lineup_monitor.py fresh with the flag set (module-level _S3_MODE is read at
    import time, so each backend needs its own module instance)."""
    os.environ["LINEUP_MONITOR_S3"] = "1" if s3_mode else "0"
    spec = importlib.util.spec_from_file_location(
        f"lineup_monitor_{'s3' if s3_mode else 'sf'}", _MONITOR
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", default=None,
                    help="slate date (America/New_York), default today")
    args = ap.parse_args()
    day = args.date or datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    s3 = _load_monitor(True)
    sf = _load_monitor(False)

    print(f"Lineup-monitor detection parity for {day}\n{'=' * 60}")
    s3_cand = s3._candidates_s3(day)
    s3_post = s3._games_with_post_lineup_s3(day)

    conn = sf.get_connection()
    cur = conn.cursor()
    try:
        sf_cand = sf._candidates_sf(cur, day)
        sf_post = sf._games_with_post_lineup_sf(cur, day)
    finally:
        cur.close()
        conn.close()

    failures: list[str] = []

    only_sf = sorted(set(sf_cand) - set(s3_cand))
    only_s3 = sorted(set(s3_cand) - set(sf_cand))
    if only_sf:
        failures.append(f"candidates only in Snowflake: {only_sf}")
    if only_s3:
        failures.append(f"candidates only in S3: {only_s3}")

    for pk in sorted(set(sf_cand) & set(s3_cand)):
        a, b = sf_cand[pk], s3_cand[pk]
        if int(a["min_slots_filled"] or 0) != int(b["min_slots_filled"] or 0):
            failures.append(
                f"game {pk}: min_slots_filled SF={a['min_slots_filled']} S3={b['min_slots_filled']}"
            )
        for side in ("home", "away"):
            x = None if a[side] is None else int(a[side])
            y = None if b[side] is None else int(b[side])
            if x != y:
                failures.append(f"game {pk}: {side} starter SF={x} S3={y}")

    if sf_post != s3_post:
        failures.append(
            f"post_lineup set differs: only-SF={sorted(sf_post - s3_post)} "
            f"only-S3={sorted(s3_post - sf_post)}"
        )

    print(f"candidates      : SF={len(sf_cand)}  S3={len(s3_cand)}")
    print(f"post_lineup set : SF={len(sf_post)}  S3={len(s3_post)}")
    if failures:
        print(f"\n❌ PARITY FAILED ({len(failures)} mismatch(es)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n✅ PARITY PASSED — detection is identical on both backends; safe to set "
          "LINEUP_MONITOR_S3=1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
