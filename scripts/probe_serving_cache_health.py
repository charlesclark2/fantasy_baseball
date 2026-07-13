"""probe_serving_cache_health.py — READ-ONLY health probe of the DynamoDB serving cache.

Answers the two questions behind the 2026-07-13 serving-data incident:

  1. Does each date's `picks/ev` blob actually PARSE as EVPicksResponse?
     A blob that fails validation makes /picks/ev silently fall through to an (empty) last-resort
     read → the EV Tracker renders BLANK for that whole date. (Root cause was an INC-23-class loose
     timestamp '2026-07-12 17:35:00+00' from the --s3/DuckDB read path; fixed in
     write_serving_store._ts + the LooseDatetime coercion in app/backend/models/picks.py.)

  2. How many of each date's games have a SCORECARD-READY game-detail blob?
     The model-vs-market "who called it" scorecards require the cached game-detail blob to be
     status='Final' with both scores. A blob frozen mid-game at status='Live' produces NO scorecard,
     so the date shows no model-vs-market data. Game-detail blobs are refreshed intraday by
     write_book_odds_op (--book-odds --game-detail); if that stops running, games that finish after
     the last refresh freeze at 'Live' forever.

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
        final = 0
        for gp in gps:
            it = by_sk.get(f"game/{gp}#PERMANENT") or by_sk.get(f"game/{gp}#{d}")
            if not it:
                continue
            try:
                if build_scorecard_from_detail(json.loads(it["value"]), gp) is not None:
                    final += 1
            except Exception:
                pass

        sc_ok = not gps or final == len(gps)
        if not (ev_ok and sc_ok):
            unhealthy.append(d)
        note = "" if (ev_ok and sc_ok) else "NEEDS BACKFILL"
        print(f"{d:<12} {ev_txt:<9} {len(gps):<7} {final:<7} {note}")

    print(f"\n{len(dates) - len(unhealthy)}/{len(dates)} dates healthy; "
          f"{len(unhealthy)} need a re-run.")
    if unhealthy:
        print("Unhealthy dates:", " ".join(unhealthy))
    if args.backfill_cmd and unhealthy:
        print("\n# Re-run write_serving_store for each (regenerates the ev blob + Final game-detail blobs):")
        print("for D in " + " ".join(unhealthy) + "; do")
        print("  docker compose -f services/dagster/aws/docker-compose.yml exec -T \\")
        print("    -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \\")
        print('    python scripts/write_serving_store.py --picks --game-detail --s3 --date "$D"')
        print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
