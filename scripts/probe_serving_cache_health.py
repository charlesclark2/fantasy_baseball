"""probe_serving_cache_health.py — READ-ONLY health probe of the DynamoDB serving cache.

Answers the two questions behind the 2026-07-13 serving-data incident:

  1. Does each date's `picks/ev` blob actually PARSE as EVPicksResponse?
     A blob that fails validation makes /picks/ev silently fall through to an (empty) last-resort
     read → the EV Tracker renders BLANK for that whole date. (Root cause was an INC-23-class loose
     timestamp '2026-07-12 17:35:00+00' from the --s3/DuckDB read path; fixed in
     write_serving_store._ts + the LooseDatetime coercion in app/backend/models/picks.py.)

  2. How many of each date's games have a SCORECARD-READY game-detail blob?
     The model-vs-market "who called it" scorecards require the cached game-detail blob to be
     status='Final' with both scores. Games without a scorecard are classified into two buckets so
     an expected gap isn't mistaken for a failure:
       • NEEDS BACKFILL (actionable) — a blob frozen mid-game at 'Live'/'Preview', or missing. Root
         cause is a game-detail refresh that stopped before the game went Final; healed by
         finalize_prior_slate_game_detail_op (daily) or a manual `--game-detail --date D` re-run.
         If it persists, the game is stuck Live/Preview in the SOURCE schedule feed itself and that
         date's statsapi schedule needs re-ingesting (a game-detail write only mirrors the source).
       • postponed (expected) — the game is Final-in-the-feed with NULL scores because it was
         POSTPONED/cancelled and moved to a future date. It was never played on this date, so it
         has no result and no backfill can produce one. These do NOT count against date health.

Use it to (a) find dates needing a `write_serving_store.py --picks --game-detail --s3 --date D`
re-run, and (b) verify a backfill afterwards.

Writes NOTHING. Needs AWS creds only (the serving-cache table is in AWS_REGION, default us-east-1).

Usage
-----
  uv run python scripts/probe_serving_cache_health.py                      # whole season
  uv run python scripts/probe_serving_cache_health.py --start 2026-07-01
  uv run python scripts/probe_serving_cache_health.py --backfill-cmd      # emit the re-run commands
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.models.picks import EVPicksResponse  # noqa: E402
from app.backend.services.scorecard import build_scorecard_from_detail  # noqa: E402

TABLE = os.getenv("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
REGION = os.getenv("AWS_REGION", "us-east-1")


def _all_picks_items(tbl) -> dict[str, dict]:
    items, kw = [], {"KeyConditionExpression": Key("pk").eq("picks")}
    while True:
        r = tbl.query(**kw)
        items.extend(r.get("Items", []))
        if not r.get("LastEvaluatedKey"):
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    return {it["sk"]: it for it in items}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--backfill-cmd", action="store_true",
                    help="Print the write_serving_store re-run commands for the unhealthy dates.")
    args = ap.parse_args()

    tbl = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    by_sk = _all_picks_items(tbl)

    dates = sorted(sk.split("#", 1)[1] for sk in by_sk if sk.startswith("ev#"))
    if args.start:
        dates = [d for d in dates if d >= args.start]
    if args.end:
        dates = [d for d in dates if d <= args.end]

    print(f"{'date':<12} {'ev blob':<9} {'games':<7} {'final':<7} {'status'}")
    print("-" * 56)
    unhealthy: list[str] = []
    for d in dates:
        blob = json.loads(by_sk[f"ev#{d}"]["value"])
        try:
            EVPicksResponse(**blob)
            ev_ok, ev_txt = True, "OK"
        except Exception:
            ev_ok, ev_txt = False, "FAIL"

        gps = sorted({p.get("game_pk") for p in (blob.get("picks") or [])
                      if p.get("game_pk") is not None})
        final = 0        # scorecard-ready (Final + both scores)
        no_result = 0    # postponed/cancelled — Final in the feed but NULL scores (never played this date)
        stale = 0        # genuinely actionable: no blob, or still Live/Preview on a past date
        for gp in gps:
            it = by_sk.get(f"game/{gp}#PERMANENT") or by_sk.get(f"game/{gp}#{d}")
            if not it:
                stale += 1
                continue
            try:
                detail = json.loads(it["value"])
                if build_scorecard_from_detail(detail, gp) is not None:
                    final += 1
                    continue
            except Exception:
                pass
            # No scorecard produced — classify WHY, so a postponed game isn't a false alarm.
            # A postponed/cancelled game is Final-in-the-feed with NULL scores: it was moved to a
            # future date and never played on THIS one, so it legitimately has no result here and
            # no backfill can ever produce one. Anything else (stuck Live/Preview) IS actionable.
            gs = (detail.get("game_score") or {}) if isinstance(detail, dict) else {}
            if gs.get("status") == "Final" and gs.get("home_score") is None and gs.get("away_score") is None:
                no_result += 1
            else:
                stale += 1

        # A date is healthy when its EV blob parses AND every PLAYED game has a scorecard. Postponed
        # (no_result) games are expected gaps, not failures — they don't count against health.
        sc_ok = stale == 0
        if not (ev_ok and sc_ok):
            unhealthy.append(d)
        note = ""
        if not ev_ok or stale:
            note = "NEEDS BACKFILL"
        elif no_result:
            note = f"({no_result} postponed)"
        print(f"{d:<12} {ev_txt:<9} {len(gps):<7} {final:<7} {note}")

    print(f"\n{len(dates) - len(unhealthy)}/{len(dates)} dates healthy; "
          f"{len(unhealthy)} genuinely need attention "
          f"(postponed/no-result games are expected gaps, not failures).")
    if unhealthy:
        print("Unhealthy dates:", " ".join(unhealthy))
    if args.backfill_cmd and unhealthy:
        print("\n# Re-run write_serving_store for each (regenerates the ev blob + Final game-detail blobs):")
        print("for D in " + " ".join(unhealthy) + "; do")
        print("  docker compose -f services/dagster/aws/docker-compose.yml exec -T \\")
        print("    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \\")
        print('    python scripts/write_serving_store.py --game-detail --s3 --date "$D"')
        print("done")
        print("# NOTE: if a date stays unhealthy after this, its games are stuck Live/Preview in the")
        print("#       SOURCE schedule feed (stg_statsapi_games) — re-ingest that date's statsapi")
        print("#       schedule first (a game-detail re-run only mirrors whatever the source says).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
