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

⭐ `--auto` IS THE SCHEDULED PATH (NF-WK-RC1 ①, 2026-09-16). `nfl_realized_week_publish_op` runs
exactly this, sequenced behind `nfl_weekly_stats_ingest_op` in `sports_nfl_weekly_serving_job` so
the consumer is refreshed downstream of its own feed IN THE SAME RUN (the INC-25 rule). It resolves
every REG week from the lake, publishes each one that is FINAL and needs a write, and prints a
`RESULT {json}` line the op reads.

  ⛔ AND IT PUBLISHES A FINAL WEEK OR NOTHING. A daily fire lands on Monday morning too, when the
  week is 15/16 games — `plan_auto` never plans a partial, so a pre-MNF fire writes nothing rather
  than shipping a week whose Monday-night players would render as absences that look exactly like
  "did not play". Publishing a partial deliberately is a human judgement and stays on the
  single-week path below.

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


def _auto(args) -> int:
    """Publish every FINAL week that needs a write. The scheduled path — see the module header."""
    import boto3

    from quant_sports_intel_models.football.nfl.fantasy import realized_week
    from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

    season = args.season
    sched = q(f"select week, count(*) n from {delta('schedules')} "
              f"where season = {season} and game_type = 'REG' group by week")
    real = q(f"select week, count(distinct game_id) n from {delta('stats_player_week')} "
             f"where season = {season} and season_type = 'REG' group by week")
    scheduled_by_week = {int(r.week): int(r.n) for r in sched.itertuples()}
    realized_by_week = {int(r.week): int(r.n) for r in real.itertuples()}
    states = realized_week.week_completeness_map(realized_by_week, scheduled_by_week)

    s3 = boto3.client("s3", region_name="us-east-1")
    published = _published_weeks(s3, args.s3_bucket, season)
    plan = realized_week.plan_auto(states, published)
    dry = args.smoke or not args.publish

    summary = {
        "season": season,
        "scheduled_weeks": len(scheduled_by_week),
        "final_weeks": sorted(w for w, s in states.items() if s == "final"),
        "published_before": sorted(published),
        "planned": plan,
        "results": [],
        "events": [],
        "errors": [],
    }
    summary["dryRun"] = dry
    for item in plan:
        week = item["week"]
        try:
            built = realized_week.build(season, week, q=q, delta=delta)
            if dry:
                decision = realized_week.publish_decision(
                    built["manifest"],
                    realized_week.published_manifest(season, week, s3=s3, bucket=args.s3_bucket))
                out = {**decision, "published": [], "revision": [],
                       "completeness": built["manifest"]["completeness"]}
            else:
                out = realized_week.publish(built, s3=s3, bucket=args.s3_bucket)
                _verify_week(s3, args.s3_bucket, season, week, built, out)
        except Exception as exc:  # noqa: BLE001 — recorded per week; the caller decides the tier
            log.warning("week %s FAILED: %s: %s", week, type(exc).__name__, exc)
            summary["errors"].append({"week": week, "error": f"{type(exc).__name__}: {exc}"})
            continue
        row = {"week": week, "planReason": item["reason"], "action": out["action"],
               "completeness": out["completeness"], "reason": out["reason"]}
        summary["results"].append(row)
        if out["event"]:
            summary["events"].append(row)
        print(f"  wk{week}: {out['action']} — {out['reason']}")

    # ⭐ THE OP READS THIS LINE, not a regex over prose. A machine-readable result at a fixed
    # sentinel is what stops a log-format change from silently blinding the caller.
    print("RESULT " + json.dumps(summary, default=str))
    return 1 if summary["errors"] else 0


def _verify_week(s3, bucket: str, season: int, week: int, built: dict, out: dict) -> None:
    """Read back what was just written and prove it is THIS build. RAISES if it is not.

    ⭐ VERIFY THE ARTIFACT, NOT THE CALL. A `put_object` that returned is not a week that advanced —
    the sibling weekly build learned this the hard way, and the cheap proof here is the content hash
    we already compute: if the served manifest does not carry this build's hash, something else is
    on that key.

    ⛔ ONLY FOR ACTIONS THAT CLAIMED A SERVING WRITE. Verifying after `unchanged` or `restate` would
    assert the served manifest matches a build we deliberately did NOT serve, which would fail on
    correct behaviour — the inverse vacuity, a guard that fires on the healthy path.
    """
    from quant_sports_intel_models.football.nfl.fantasy import realized_week

    if not out.get("published"):
        return
    back = realized_week.published_manifest(season, week, s3=s3, bucket=bucket)
    if back is None:
        raise RuntimeError(f"wk{week}: published, but the manifest reads back as ABSENT")
    if back.get("content_sha256") != built["manifest"]["content_sha256"]:
        raise RuntimeError(
            f"wk{week}: the served manifest carries content_sha256="
            f"{back.get('content_sha256')!r} but this build wrote "
            f"{built['manifest']['content_sha256']!r} — the publish did not land on the served key")


def _published_weeks(s3, bucket: str, season: int) -> set[int]:
    """Which weeks already have a SERVED manifest. One LIST, not 18 HEADs.

    ⛔ A failure RAISES rather than returning an empty set: an empty set means "nothing is
    published", which would plan a `create` for every week and overwrite the lot.
    """
    weeks: set[int] = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=f"fantasy/nfl/realized/{int(season)}/"):
        for obj in page.get("Contents") or []:
            parts = obj["Key"].split("/")
            # ⛔ `manifest.json` EXACTLY — a `manifest.revision-*.json` is a parked restatement and
            # must not read as a served week, or a restated week would look published and a genuine
            # gap could hide behind its own revision.
            if parts[-1] == "manifest.json" and len(parts) >= 2 and parts[-2].isdigit():
                weeks.add(int(parts[-2]))
    return weeks


def main() -> int:
    p = argparse.ArgumentParser(description="Publish one week's realized NFL stat lines.")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, help="one week (omit with --auto)")
    p.add_argument("--auto", action="store_true",
                   help="publish every FINAL week that needs a write (the scheduled path)")
    p.add_argument("--publish", action="store_true", help="write to S3 (else a dry build)")
    p.add_argument("--smoke", action="store_true",
                   help="build and report WITHOUT writing — the executing smoke")
    p.add_argument("--s3-bucket", default=os.environ.get("CACHE_BUCKET",
                                                         "credence-prod-s3-api-cache"))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.auto:
        if args.week is not None:
            raise SystemExit("--auto resolves its own weeks; do not also pass --week")
        return _auto(args)
    if args.week is None:
        raise SystemExit("--week is required without --auto")

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
    print(f"\n{out['action']}: {out['reason']}")
    if out["published"]:
        print("  published: " + ", ".join(out["published"]))
    if out["revision"]:
        print("  parked at a revision key (the published week keeps serving): "
              + ", ".join(out["revision"]))
    # ⛔ A REFUSED DOWNGRADE IS NOT A SUCCESS. "published" and "correctly declined to publish" must
    # stay distinguishable at the process boundary (the run_weekly_serving EXIT_AWAITING_ROSTERS
    # reasoning) — a human who asked for a publish and got none needs a non-zero answer.
    return 4 if out["action"] == "refuse_downgrade" else 0


if __name__ == "__main__":
    raise SystemExit(main())
