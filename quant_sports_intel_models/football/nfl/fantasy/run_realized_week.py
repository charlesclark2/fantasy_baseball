"""run_realized_week.py — publish ONE week's realized stat lines for the NF-WK-RC1 recap.

⭐ SHIPS WITH AN EXECUTING SMOKE FROM DAY ONE (the entrypoint sibling sweep, GyD9hoeD): `--smoke`
builds the week and prints what WOULD publish without writing, so this entrypoint can never join
the zero-callers list — a publish script nothing has ever run is one nobody can trust on the day it
matters.

RUN (BOX — reads the S3 NFL lake, writes the api-cache; ~15s):

    docker compose -f services/dagster/aws/docker-compose.yml exec -T \
      -e AWS_DEFAULT_REGION=us-east-2 dagster-codeloc \
      python -m quant_sports_intel_models.football.nfl.fantasy.run_realized_week \
        --season 2026 --week 1 --publish

⛔ IT REFUSES TO PUBLISH A WEEK THAT HAS NOT STARTED. A `not_started` week carries zero rows, and a
zero-row artifact would make every recap render an empty lineup that looks exactly like a bye. A
PARTIAL week DOES publish — labelled — because a reader watching Sunday evening is entitled to see
what has happened; what they are not entitled to is a partial total presented as final.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

log = logging.getLogger("nfl.fantasy.realized_week")


def main() -> int:
    p = argparse.ArgumentParser(description="Publish one week's realized NFL stat lines.")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--publish", action="store_true", help="write to S3 (else a dry build)")
    p.add_argument("--smoke", action="store_true",
                   help="build and report WITHOUT writing — the executing smoke")
    p.add_argument("--s3-bucket", default=os.environ.get("CACHE_BUCKET",
                                                         "credence-prod-s3-api-cache"))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    from quant_sports_intel_models.football.nfl.fantasy import realized_week
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    built = realized_week.build(args.season, args.week, q=q, delta=delta)
    man = built["manifest"]
    print(json.dumps({k: v for k, v in man.items() if k != "columns"}, indent=2))

    if args.smoke or not args.publish:
        print(f"\n[dry] would publish {len(built['players'])} rows to "
              f"s3://{args.s3_bucket}/fantasy/nfl/"
              f"{realized_week.realized_players_key(args.season, args.week)}")
        return 0

    if man["completeness"] == "not_started":
        # ⛔ A hard refusal, not a warning: see the module header. A zero-row artifact is
        # indistinguishable from a whole league on a bye.
        print(f"REFUSING to publish {args.season} wk{args.week}: the week has not started "
              f"({man['realized_games']}/{man['scheduled_games']} games). Nothing was written.",
              file=sys.stderr)
        return 2

    import boto3

    out = realized_week.publish(built, s3=boto3.client("s3", region_name="us-east-1"),
                                bucket=args.s3_bucket)
    print(f"\npublished {out['completeness']}: {', '.join(out['published'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
