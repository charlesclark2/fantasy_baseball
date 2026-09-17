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
`RESULT {json}` line the op reads. Every fire also rebuilds the CUMULATIVE SEASON-TO-DATE artifact
(`realized/<season>/season/`, PM ruling 2026-09-17) from the served weeks.

⭐ `--check-published` is READ-ONLY and runs the publish-time contract against what is serving now —
the stored week-1 artifact is the anchor the contract was measured against (~5s, LAPTOP or BOX):

    AWS_DEFAULT_REGION=us-east-2 uv run python -m \
      quant_sports_intel_models.football.nfl.fantasy.run_realized_week --season 2026 --check-published

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

    # ⭐ THE SEASON-TO-DATE ARTIFACT IS REBUILT EVERY FIRE, not only when a week was written this
    # run — it is a pure function of the served weeks, so an unchanged season is a cheap no-op and a
    # season artifact that fell behind (a prior fire that failed half-way) heals on the next one.
    summary["season_to_date"] = _season(args, s3, dry, summary)
    summary["dst_inputs"], summary["dst_inputs_errors"] = _dst_inputs(
        args, s3, dry, sorted(w for w, s in states.items() if s == "final"), q, delta)

    # ⭐ THE OP READS THIS LINE, not a regex over prose. A machine-readable result at a fixed
    # sentinel is what stops a log-format change from silently blinding the caller.
    print("RESULT " + json.dumps(summary, default=str))
    return 1 if summary["errors"] else 0


def _dst_inputs(args, s3, dry: bool, final_weeks: list[int], q, delta) -> tuple[list, list]:
    """NF-WK-ACC1 ⑥ — (re)publish every FINAL week's D/ST recorder inputs. Never raises.

    ⭐ ITS FAILURES ARE RETURNED SEPARATELY FROM `summary["errors"]` ON PURPOSE. Those page CRITICAL
    and fail the run, because the recap RENDERS from them; these feed a record-only recorder (D2
    disposition (C)), so a failure here must not withhold or fail anything a reader sees. The op
    reports them at WARN under their own dedup key.

    ⭐ EVERY FINAL WEEK, EVERY FIRE — not only the weeks published this run — because the input
    legitimately changes after a week is final (the Monday-night result lands late) and an
    unchanged week costs one GET.
    """
    from quant_sports_intel_models.football.nfl.fantasy import realized_week

    results, errors = [], []
    for week in final_weeks:
        try:
            built = realized_week.build_dst_inputs(args.season, week, q=q, delta=delta)
            results.append(realized_week.publish_dst_inputs(
                built, s3=s3, bucket=args.s3_bucket, dry=dry))
        except Exception as exc:  # noqa: BLE001 — record-only; see the docstring
            log.warning("dst inputs wk%s FAILED: %s: %s", week, type(exc).__name__, exc)
            errors.append({"week": week, "error": f"{type(exc).__name__}: {exc}"})
    for r in results:
        print(f"  dst inputs wk{r['week']}: {r['action']} ({r['teams']} defences, "
              f"result pending: {r['resultPending'] or 'none'})")
    return results, errors


def _season(args, s3, dry: bool, summary: dict) -> dict:
    """Build (and unless `dry`, publish) the cumulative season-to-date artifact. Never raises —
    a failure lands in `summary["errors"]` under `week: "season"`, which the op pages on.

    ⚠️ ON A DRY RUN a week the real run would `backfill_hash` still reads as `unverifiable` here,
    because the dry run does not install the hash. That exclusion is reported, not paged.
    """
    from quant_sports_intel_models.football.nfl.fantasy import realized_week

    season = args.season
    try:
        served = {}
        for week in sorted(_published_weeks(s3, args.s3_bucket, season)):
            got = realized_week.load_served_week(season, week, s3=s3, bucket=args.s3_bucket)
            if got is not None:
                served[week] = got
        built = realized_week.build_season(season, served)
        man = built["manifest"]
        if dry:
            out = realized_week.season_publish_decision(
                man, realized_week.published_season_manifest(season, s3=s3,
                                                             bucket=args.s3_bucket))
            out = {**out, "published": []}
        else:
            out = realized_week.publish_season(built, s3=s3, bucket=args.s3_bucket)
            _verify_season(s3, args.s3_bucket, season, built, out)
    except Exception as exc:  # noqa: BLE001 — recorded; the op pages on it
        log.warning("season-to-date FAILED: %s: %s", type(exc).__name__, exc)
        summary["errors"].append({"week": "season", "error": f"{type(exc).__name__}: {exc}"})
        return {"action": "error", "error": f"{type(exc).__name__}: {exc}"}

    report = {"action": out["action"], "reason": out["reason"],
              "through_week": man["through_week"], "weeks": man["weeks"],
              "excluded": man["excluded"], "n_rows": man["n_rows"]}
    # ⛔ A SERVED FINAL WEEK THAT CANNOT ENTER THE SEASON TOTAL IS A DEFECT, NOT A NOTE. The
    # artifact names it in `excluded` so a consumer can say so — but the cadence must page, or a
    # season total stuck at week 3 reads as three quiet weeks for every player.
    defects = realized_week.season_defects(built)
    if defects and not dry:
        summary["errors"].append({"week": "season",
                                  "error": "served weeks excluded from the season-to-date artifact: "
                                           + json.dumps(defects)})
    if out.get("event"):
        summary["events"].append({"week": "season", **report})
    print(f"  season: {out['action']} — {out['reason']}")
    return report


def _verify_season(s3, bucket: str, season: int, built: dict, out: dict) -> None:
    """Read back the served season manifest and prove it is THIS build (the `_verify_week` rule)."""
    from quant_sports_intel_models.football.nfl.fantasy import realized_week

    if not out.get("published"):
        return
    back = realized_week.published_season_manifest(season, s3=s3, bucket=bucket)
    want = built["manifest"]["content_sha256"]
    if back is None or back.get("content_sha256") != want:
        raise RuntimeError(f"{season} season: published, but the served manifest reads back as "
                           f"{(back or {}).get('content_sha256')!r}, not {want!r}")


def _check_published(args) -> int:
    """READ-ONLY. Run the publish-time contract against what is SERVING right now.

    ⭐ THE STORED ARTIFACT IS THE ANCHOR (PM 2026-09-17). Week 1 was published by hand before this
    contract existed, and the vendor's week-1 window is partly closed, so the served file is the one
    copy of week 1 anybody can check the contract against. Exit 5 if anything served fails.
    """
    import boto3

    from quant_sports_intel_models.football.nfl.fantasy import realized_week

    s3 = boto3.client("s3", region_name="us-east-1")
    season, bad = args.season, False
    out = {"season": season, "weeks": [], "season_to_date": None}
    for week in sorted(_published_weeks(s3, args.s3_bucket, season)):
        man, players = realized_week.load_served_week(season, week, s3=s3, bucket=args.s3_bucket)
        rep = realized_week.contract_report(man, players)
        prior = man.get("content_sha256")
        hash_ok = None if not prior else prior == realized_week.content_hash(players)
        bad |= (not rep["ok"]) or hash_ok is False
        out["weeks"].append({"week": week, "completeness": man.get("completeness"),
                             "n_players": man.get("n_players"), "n_teams": man.get("n_teams"),
                             "realized_games": man.get("realized_games"),
                             "hashMatches": hash_ok, **rep})
    smeta = realized_week.published_season_manifest(season, s3=s3, bucket=args.s3_bucket)
    if smeta is not None:
        body = json.loads(s3.get_object(
            Bucket=args.s3_bucket,
            Key=f"fantasy/nfl/{realized_week.realized_season_players_key(season)}")["Body"].read())
        rep = realized_week.season_contract_report(
            {"manifest": smeta, "columns": body["columns"], "rows": body["rows"]})
        bad |= not rep["ok"]
        out["season_to_date"] = {"through_week": smeta.get("through_week"),
                                 "excluded": smeta.get("excluded"), **rep}
    print(json.dumps(out, indent=2, default=str))
    return 5 if bad else 0


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
    p.add_argument("--check-published", action="store_true",
                   help="READ-ONLY: run the publish-time contract against the served artifacts")
    p.add_argument("--publish", action="store_true", help="write to S3 (else a dry build)")
    p.add_argument("--smoke", action="store_true",
                   help="build and report WITHOUT writing — the executing smoke")
    p.add_argument("--s3-bucket", default=os.environ.get("CACHE_BUCKET",
                                                         "credence-prod-s3-api-cache"))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.check_published:
        return _check_published(args)
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
        rep = realized_week.contract_report(man, built["players"])
        print("\n[dry] contract: " + json.dumps({k: v for k, v in rep.items()}))
        print(f"[dry] would publish {len(built['players'])} rows to "
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
