"""NF-C6-PH2 — the NFL WEEKLY SERVING build-and-publish job.

NF-W1's certified weekly champion (`lgbm_hurdle`, SHIP × 4 positions, 8/8 folds, PBO 0.0, coverage
≥ 0.817 against a 0.80 FLOOR) was certified 2026-08-07 and has served nothing since: there was no
weekly endpoint for it to land on. This job is that path — a daily in-season rebuild of the target
week's player payloads plus the rest-of-season roll-up, published to the api-cache the
`/fantasy/nfl/weekly/*` routes read.

⚖️ TIER — the same two-sided shape `sports_nfl_board_publish_job` documents, and for the same
reasons:
  * It can never HALT anything else. A standalone sports job in its own namespace: a failure fails
    ITS OWN run, blocks nothing MLB-serving, and leaves the PREVIOUS week's artifacts serving from
    S3 untouched. A missed rebuild costs freshness, never availability.
  * ⛔ It must NEVER report SUCCESS while publishing nothing. That is how
    `sports_nfl_sleeper_injuries_job` produced 19 consecutive green runs against one 19-day-old
    Delta commit (NF-FRESH1): a WARN-tier op opened a gitignored file, died in 114 ms, and its bare
    `except` returned SUCCESS. So this op PAGES AND RAISES: a red run that leaves last week's
    projection serving is strictly better than a green run that shipped nothing.

⭐ THE BUILDER REFUSES BEFORE IT WRITES, which is what makes "green" mean something here. Four
fail-closed invariants run inside `run_weekly_serving.build` ahead of any byte: the point-in-time
gate must be NON-VACUOUS (weeks AND records checked > 0 — NF1.7(a)), the target week's own outcome
must be provably unable to reach its own features, the rest-of-season horizon must be frozen-form
(no lag recomputed over a week with no realized outcome), and every blob must validate against
`app/backend/models/nfl_weekly.py`. This op then VERIFIES the artifact that was actually published
rather than trusting three exit codes.

🚦 PRECONDITION, and it is the likely first failure on the box: the build reads the S3 NFL lake
through DuckDB. Unlike the board job it needs NO sports DuckDB file — the whole chain is lake reads
plus an in-process fit — so its precondition is credentials and the delta extension, not a
gitignored artifact. What it DOES need is `lightgbm`, which the codeloc image carries.

⏱️ RUNTIME. The fit is the long pole: one classifier plus nine quantile regressors for the points
mixture, plus eleven means for the advisory component head, over ~85k training rows. Measured on a
laptop at ~9 minutes end to end; the box is a 2-vCPU r6g.large, so the timeout is generous and the
job is deliberately OFF the daily critical path.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dagster import In, Nothing, Out, in_process_executor, job, op

_APP_DIR = Path(os.environ.get("APP_DIR", "/app"))
_FANTASY = "quant_sports_intel_models.football.nfl.fantasy"
_STAGING = "quant_sports_intel_models/football/nfl/fantasy/artifacts/weekly_serving"

# INC-32 — every subprocess on a Dagster path carries a finite timeout, and this one is sized from
# the measured build rather than from a round number: ~9 min on a laptop, so 45 min leaves room for
# a 2-vCPU box under load without letting a wedged fit sit forever.
NFL_WEEKLY_BUILD_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_WEEKLY_BUILD_TIMEOUT_SECONDS", "2700"))

# ⚠️ NOT defaulted to empty. `--publish` with no bucket is a HARD ERROR in the runner by design
# (the NF1.7 silent-no-publish lesson), and we want that error rather than a green run that
# shipped nothing.
NFL_WEEKLY_CACHE_BUCKET = os.environ.get("CACHE_BUCKET", "credence-prod-s3-api-cache")

#: Mirrors `run_weekly_serving.EXIT_AWAITING_ROSTERS`. Pinned equal by
#: `test_nf_c6_ph2_weekly_serving.py` so the two owners of this code cannot drift.
EXIT_AWAITING_ROSTERS = 3

# NF-INC-0916 node 1 — the training-feed ingest that runs immediately before the build.
# Two unauthenticated nflverse release reads plus two Delta partition writes; measured in seconds,
# so this ceiling is orders of magnitude of headroom rather than a snug fit. INC-32: a finite
# timeout on every subprocess on a Dagster path, and `run_bounded` kills the whole process group
# on expiry rather than orphaning a grandchild.
NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS", "900"))

# NF-WK-RC1 ① — the realized-week publish. Two grouped lake counts plus, at most,
# `RESTATEMENT_WINDOW_WEEKS` single-week builds and their S3 writes; measured at ~15 s for one week,
# so this is orders of magnitude of headroom rather than a snug fit. INC-32: finite, and
# `run_bounded` kills the process group on expiry rather than orphaning a grandchild.
NFL_REALIZED_PUBLISH_TIMEOUT_SECONDS = int(
    os.environ.get("NFL_REALIZED_PUBLISH_TIMEOUT_SECONDS", "900"))


# NF-ROS1b node 4 — the certified rest-of-season publish. Measured at ~5 s on a laptop (lake reads
# plus a closed-form update over ~870 rows); this is headroom, not a fit. INC-32: finite.
NFL_ROS_PUBLISH_TIMEOUT_SECONDS = int(os.environ.get("NFL_ROS_PUBLISH_TIMEOUT_SECONDS", "900"))

#: Mirrors `run_nf_ros1_publish.EXIT_NO_FINAL_WEEK` (pinned equal by the NF-ROS1b guards).
EXIT_ROS_NO_FINAL_WEEK = 3


def _page(context, title: str, body: str, *, severity: str, dedup_key: str) -> None:
    """Page, and mirror it into the step log. Distinct `dedup_key` per failure mode so one noisy
    leg cannot occupy another's 1-hour rate-limit slot (INC-39)."""
    from pipeline.utils.alerting import send_alert

    send_alert(title, body, severity=severity, dedup_key=dedup_key)
    context.log.warning("ALERT [nfl weekly] %s — %s", title, body)


@op(out=Out(Nothing))
def nfl_weekly_stats_ingest_op(context):
    """NF-INC-0916 node 1 — refresh the weekly model's TRAINING FEEDS, immediately before the
    build that learns from them.

    ⭐ WHY THIS OP IS HERE AND NOT ON ITS OWN SCHEDULE. `stats_player_week` and `snap_counts` are
    what `run_weekly_serving` trains on, and until this op existed NOTHING ingested either of them
    on any cadence — which is the incident: the 2026 week-1 training rows carried no stat line,
    `attach_labels` filled them with zeros under the retained-zero convention, and the hurdle
    learned a `P(zero)` from a week nobody had played. Population-matched against realized scoring
    the served point ran at roughly a third of reality.

    Sitting it in THIS job, upstream of the build, is the INC-25 rule in its strongest form: the
    consumer is refreshed downstream of its feed IN THE SAME RUN, so there is no cron window in
    which the build reads a lake the ingest has not touched — and no second schedule that can
    silently revert to STOPPED while everything stays green (NF-INFRA1).

    ⛔ NOT `ROLL_FORWARD_SOURCES`, and that is measured rather than stylistic: the roll-forward
    fires Monday 06:15 PT, an NFL week closes Monday NIGHT, and the vendor publishes it the next
    morning — so on a weekly cadence the just-completed week is missing for a full seven days, and
    under the retained-zero convention a missing line is a zero. See
    `ingest/in_season_stats.py`, which holds the measurement and asserts the exclusivity.

    ⚖️ ALERT-LOUD-BUT-CONTINUE. A failed ingest pages and does NOT sink the run: the build can
    still produce a correct projection from the weeks that DID land, and this job's own doctrine is
    that a missed rebuild costs freshness rather than availability. The protection against training
    on what did not land is the target week's COVERAGE REFUSAL inside the builder, not this op's
    exit code — a gate belongs at the instrument, not at the feed.
    """
    from betting_ml.utils.bounded_subprocess import run_bounded

    cmd = [sys.executable, "-m",
           "quant_sports_intel_models.football.nfl.ingest.in_season_stats"]
    context.log.info("[nfl weekly stats] %s", " ".join(cmd))
    env = {**os.environ, "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2")}
    try:
        proc = run_bounded(cmd, cwd=str(_APP_DIR), env=env,
                           timeout=NFL_WEEKLY_STATS_INGEST_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(
            cmd, returncode=124, stdout=(exc.stdout or ""), stderr="timeout")

    for line in (proc.stdout or "").splitlines()[-40:]:
        context.log.info("[stats] %s", line)
    context.log.info("[METRIC] nfl_weekly_stats_ingest_exit=%d", proc.returncode)

    if proc.returncode != 0:
        for line in (proc.stderr or "").splitlines()[-40:]:
            context.log.warning("[stats:stderr] %s", line)
        _page(context, "NFL weekly training-feed ingest FAILED",
              "`in_season_stats` exited "
              f"{proc.returncode}. The build below still runs — it can project from the weeks that "
              "already landed — but it is now training on a feed that did not advance this cycle, "
              "which is the NF-INC-0916 mechanism. The freshness leg reports which week each feed "
              "is actually at.\n\n"
              f"stderr tail:\n{(proc.stderr or '')[-1500:]}",
              severity="CRITICAL", dedup_key="nfl_weekly_stats:ingest")


def _slate_end_utc(sched, week):
    """When the given week's slate actually FINISHED, in UTC.

    ⚠️ `gameday` is a DATE, not a kickoff instant, and the last game of an NFL week is the Monday
    night one — it ends around 23:30 PT, i.e. ~06:30 UTC the FOLLOWING day. Taking the bare date
    would start the publication-grace window ~6-7 hours early and let the monitor call STALE while
    the vendor was still inside its normal, measured lag.

    Returns `None` when it cannot be resolved; `classify` then judges the week mismatch with no
    grace window at all, which can only ever cost a FALSE ALARM rather than a missed finding.
    """
    if week is None:
        return None
    try:
        import pandas as pd

        last_day = pd.Timestamp(sched.loc[sched["week"] == week, "gameday"].max())
        if pd.isna(last_day):
            return None
        end = (last_day.to_pydatetime().replace(tzinfo=timezone.utc)
               if last_day.tzinfo is None else last_day.to_pydatetime())
        # +30.5 h from midnight of the last gameday ≈ 06:30 UTC next day ≈ 23:30 PT.
        return end + timedelta(hours=30.5)
    except Exception:  # noqa: BLE001 — a grace window we cannot compute is simply absent
        return None


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_weekly_stats_freshness_op(context):
    """Is each training feed actually carrying the last week that was played?

    ⛔ DOWNSTREAM OF THE INGEST, deliberately. A guard positioned UPSTREAM of the op that writes
    what it checks reads a store one cycle behind and pages on a date the same run heals moments
    later — INC-40, where the tell was that the date named read healthy by the time a human looked.

    ⭐ AND IT IS A CONTENT CHECK, NOT A COMMIT-TIME CHECK (INC-41). A Delta commit timestamp says
    when we last WROTE; a daily ingest re-landing the same stale vendor file would refresh it every
    day while the content stood still. The question is which WEEK the feed carries, judged against
    the SCHEDULE — never against the feed itself, which would be circular.

    ALERT-tier, never HALT: it judges, it does not gate, and it never raises.
    """
    from betting_ml.monitoring import nfl_weekly_stats_freshness as SF
    from quant_sports_intel_models.football.nfl.ingest.in_season_stats import WEEKLY_STAT_SOURCES

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    try:
        from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

        sched = q(f"select week, gameday, home_score from {delta('schedules')} "
                  f"where season = {season} and game_type = 'REG'")
        played = sched[sched["home_score"].notna()]
        last_completed_week = int(played["week"].max()) if len(played) else None
        slate_ended = _slate_end_utc(sched, last_completed_week)
    except Exception as exc:  # noqa: BLE001
        # ⚠️ UNEVALUABLE IS WARN, NEVER HEALTHY (NF1.7(a)). This module exists because a year of
        # green runs examined nothing.
        _page(context, "NFL training-feed freshness: could not resolve the completed week",
              f"{type(exc).__name__}: {exc}. The feeds were NOT judged — reported UNVERIFIED "
              "rather than healthy.",
              severity="WARN", dedup_key="nfl_weekly_stats_freshness:unresolvable")
        return

    verdicts = []
    for src in WEEKLY_STAT_SOURCES:
        try:
            from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

            df = q(f"select max(week) lw, count(*) n from {delta(src)} where season = {season}")
            lw = df["lw"].iloc[0]
            reading = SF.FeedReading(src, None if lw is None or lw != lw else int(lw),
                                     int(df["n"].iloc[0]))
        except Exception as exc:  # noqa: BLE001
            reading = SF.FeedReading(src, None, 0, error=f"{type(exc).__name__}: {exc}")
        v = SF.classify(reading, season=season, last_completed_week=last_completed_week,
                        slate_ended=slate_ended)
        verdicts.append(v)
        context.log.info("[METRIC] nfl_weekly_stats_feed=%s verdict=%s last_week=%s",
                         src, v["verdict"], v["last_week"])
        context.log.info("[nfl weekly stats] %s", v["detail"])

    severity = SF.worst(verdicts)
    if severity:
        bad = [v for v in verdicts if v.get("severity")]
        _page(context, "NFL weekly training feed is not advancing",
              "\n\n".join(f"- {v['verdict']}: {v['detail']}" for v in bad),
              severity=severity, dedup_key="nfl_weekly_stats_freshness:stale")


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_realized_week_publish_op(context):
    """NF-WK-RC1 ① — publish every COMPLETED week's realized stat lines.

    ⭐ WHY IT IS IN THIS JOB AND NOT ON ITS OWN SCHEDULE. It reads `stats_player_week`, which is
    exactly what `nfl_weekly_stats_ingest_op` above writes — so this is the INC-25 rule in its
    strongest form, the consumer refreshed downstream of its feed IN THE SAME RUN. A separate
    schedule would be a bare clock racing that ingest, plus a second instigator that can silently
    revert to STOPPED while everything stays green (NF-INFRA1/E11.23). Riding a job that already
    self-starts (`default_status=RUNNING`) and is in `check_monitors_healthy_op`'s required set
    means this cadence inherits a heartbeat rather than adding one more thing to watch.

    ⛔ AND IT IS DELIBERATELY NOT DOWNSTREAM OF THE BUILD. `nfl_weekly_serving_op` RAISES on a
    refusal — often correctly, when the builder fails closed — and hanging the realized publish off
    it would mean a refused PROJECTION withholds the REALIZED facts, which are a different product
    on a different input. Two unrelated failures must not share a fate. As an independent branch off
    the ingest, each still runs when the other fails.

    ⚖️ TIER — pages and RAISES on a failed publish, exactly as the sibling build does. The realized
    artifact is what Phase B's recap renders from; "we published nothing and said nothing" is the
    NF-FRESH1 shape this job's own header exists to refuse. A red run that leaves last week's
    artifact serving beats a green one that shipped nothing.

    ⭐ A RESTATEMENT PAGES *WARN*, NOT CRITICAL. The vendor restating a played week is a named
    event, not an outage — the published week keeps serving and the new build is parked. Paging
    CRITICAL on a thing that is working as designed is how a monitor gets muted before it ever
    catches something (the D2 divergence-recorder constraint, one surface over).
    """
    from betting_ml.utils.bounded_subprocess import run_bounded

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    cmd = [sys.executable, "-m", f"{_FANTASY}.run_realized_week",
           "--season", str(season), "--auto",
           "--s3-bucket", NFL_WEEKLY_CACHE_BUCKET, "--publish"]
    context.log.info("[nfl realized] %s", " ".join(cmd))
    env = {**os.environ, "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2")}
    try:
        proc = run_bounded(cmd, cwd=str(_APP_DIR), env=env,
                           timeout=NFL_REALIZED_PUBLISH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(
            cmd, returncode=124, stdout=(exc.stdout or ""), stderr="timeout")

    for line in (proc.stdout or "").splitlines()[-60:]:
        context.log.info("[realized] %s", line)

    summary = _parse_result_line(proc.stdout or "")
    context.log.info("[METRIC] nfl_realized_publish_exit=%d", proc.returncode)

    # ⛔ AN UNPARSEABLE RESULT IS A FAILURE, NEVER A PASS. Exit 0 with no summary means the run
    # cannot say what it did, and "we could not tell" must not read as "nothing needed doing"
    # (NF1.7(a)) — that is precisely how a cadence publishes nothing for a month while green.
    if summary is None:
        for line in (proc.stderr or "").splitlines()[-40:]:
            context.log.warning("[realized:stderr] %s", line)
        _page(context, "NFL realized week: the publish reported nothing readable",
              f"`run_realized_week --auto` exited {proc.returncode} and printed no RESULT line, so "
              "this run cannot say which weeks it published. Reported as a failure rather than a "
              f"pass.\n\nstderr tail:\n{(proc.stderr or '')[-1500:]}",
              severity="CRITICAL", dedup_key="nfl_realized_publish:unreadable")
        raise Exception("NFL realized publish produced no readable RESULT")

    planned = summary.get("planned") or []
    results = summary.get("results") or []
    events = summary.get("events") or []
    errors = summary.get("errors") or []
    context.log.info("[METRIC] nfl_realized_final_weeks=%s", summary.get("final_weeks"))
    context.log.info("[METRIC] nfl_realized_planned=%d", len(planned))
    context.log.info("[METRIC] nfl_realized_published=%d",
                     sum(1 for r in results if r.get("action") in ("create", "upgrade",
                                                                   "backfill_hash")))
    context.log.info("[METRIC] nfl_realized_events=%d", len(events))
    context.log.info("[METRIC] nfl_realized_errors=%d", len(errors))
    season_to_date = summary.get("season_to_date") or {}
    context.log.info("[METRIC] nfl_realized_season_through_week=%s action=%s",
                     season_to_date.get("through_week"), season_to_date.get("action"))

    # NF-WK-ACC1 ⑥ — the D/ST recorder's inputs. RECORD-ONLY (D2 disposition (C)): a failure is a
    # WARN under its own dedup key and never fails the run — the recap does not render from these.
    dst_results = summary.get("dst_inputs") or []
    dst_errors = summary.get("dst_inputs_errors") or []
    context.log.info("[METRIC] nfl_realized_dst_inputs_written=%d",
                     sum(1 for r in dst_results if r.get("action") in ("create", "update")))
    context.log.info("[METRIC] nfl_realized_dst_inputs_errors=%d", len(dst_errors))
    if dst_errors:
        _page(context, "NFL realized: D/ST recorder inputs were not published",
              "The divergence recorder's team-grain inputs did not publish for these weeks. The "
              "recap is unaffected (its D/ST seat is the league's own figure); the recorder will "
              "report those weeks as `constructionSupplied: False` until this heals.\n\n"
              + "\n".join(f"- {_realized_label(e)}: {e['error']}" for e in dst_errors),
              severity="WARN", dedup_key="nfl_realized_publish:dst_inputs")

    if errors:
        _page(context, "NFL realized week publish FAILED",
              "The realized stat lines Phase B's recap renders from did not advance this cycle.\n\n"
              + "\n".join(f"- {_realized_label(e)}: {e['error']}" for e in errors),
              severity="CRITICAL", dedup_key="nfl_realized_publish:failed")
        raise Exception(f"NFL realized publish failed for week(s) "
                        f"{[e['week'] for e in errors]}")

    if events:
        _page(context, "NFL realized: a published artifact was deliberately NOT replaced",
              "Either the vendor RESTATED a published week (the published week KEEPS SERVING and "
              "the new build is parked at a revision key) or a build was refused because it would "
              "have replaced a served artifact with a less complete one. Nothing changed underneath "
              "a reader. This is a named event for a human to look at, not an outage.\n\n"
              + "\n".join(f"- {_realized_label(e)}: {e['action']} — {e['reason']}"
                          for e in events),
              severity="WARN", dedup_key="nfl_realized_publish:restated")

    # ⭐ A CADENCE FIRE WITH NOTHING TO DO IS THE COMMON CASE AND MUST STAY LEGIBLE. Most fires land
    # mid-week, when the newest week is still partial and every final week is already published.
    # That is a clean skip, said out loud — never a silent success (the ALERT-loud tier).
    if not planned:
        context.log.info(
            "⏸️ [nfl realized] nothing to publish: %s FINAL week(s), all already served",
            len(summary.get("final_weeks") or []))
    else:
        context.log.info("[nfl realized] %s", "; ".join(
            f"wk{r['week']}={r['action']}" for r in results))


def _realized_label(entry: dict) -> str:
    """`wk3`, or `season-to-date` for the cumulative artifact's entries (`week: "season"`)."""
    return "season-to-date" if entry.get("week") == "season" else f"wk{entry.get('week')}"


def _parse_result_line(stdout: str) -> dict | None:
    """The `RESULT {json}` line the runner prints. `None` when it is absent or unparseable.

    ⛔ THE *LAST* MATCHING LINE, and parsed as JSON rather than regexed out of prose: a log format
    that drifts must break loudly here rather than silently matching something adjacent.
    """
    for line in reversed((stdout or "").splitlines()):
        if line.startswith("RESULT "):
            try:
                return json.loads(line[len("RESULT "):])
            except json.JSONDecodeError:
                return None
    return None


@op(ins={"start": In(Nothing)}, out=Out(None))
def nfl_weekly_serving_op(context):
    """Build the target week's projection, publish it, then verify what was published.

    Subprocess rather than an in-process import on purpose: the build pulls the whole modelling
    stack (pandas / sklearn / lightgbm), and importing that into the Dagster code-location process
    would put it on every op's import path in this container.
    """
    started = datetime.now(timezone.utc)
    cmd = [sys.executable, "-m", f"{_FANTASY}.run_weekly_serving",
           "--s3-bucket", NFL_WEEKLY_CACHE_BUCKET, "--publish"]
    context.log.info("[nfl weekly] %s", " ".join(cmd))
    env = {**os.environ, "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2")}
    try:
        proc = subprocess.run(cmd, cwd=str(_APP_DIR), env=env,
                              timeout=NFL_WEEKLY_BUILD_TIMEOUT_SECONDS,
                              capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        # ⛔ Never `|| echo 0`-style swallowing: an unreachable step must stay distinguishable from
        # a clean one (INC-32/INC-36). A timeout is a real non-zero result.
        proc = subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr="timeout")

    for line in (proc.stdout or "").splitlines()[-80:]:
        context.log.info("[weekly] %s", line)

    # ⭐ THE CADENCE SKIP IS NOT A FAILURE. The target week advances at the previous slate's first
    # kickoff while its game-day rosters publish days later, so for most of every week the next week
    # is the right target and has no roster rows. Paging on that would fire CRITICAL on most days —
    # the muted-monitor pattern (INC-37: judging a feed before it lands pages every morning).
    #
    # ⛔ NOT A SILENT SUCCESS EITHER. The run said so with a distinct exit code, this logs it, and
    # the thing that escalates if it persists is the DAILY freshness monitor on the PUBLISHED
    # artifact — which goes WRONG_WEEK once the served week falls behind. A build that declines to
    # run is structurally invisible to itself, which is why that monitor is a different job.
    if proc.returncode == EXIT_AWAITING_ROSTERS:
        context.log.warning(
            "⏸️ [nfl weekly] the target week's rosters have not published yet — nothing built, "
            "nothing published; the previously published week keeps serving")
        context.log.info("[METRIC] nfl_weekly_skipped_awaiting_rosters=1")
        return

    if proc.returncode != 0:
        for line in (proc.stderr or "").splitlines()[-80:]:
            context.log.warning("[weekly:stderr] %s", line)
        body = (f"`run_weekly_serving --publish` exited {proc.returncode}.\n\n"
                "NOTHING WAS PUBLISHED THIS CYCLE — the previously published week is still being "
                "served, so the product is not down; it is just not advancing.\n\n"
                "⭐ A REFUSAL HERE IS OFTEN THE BUILDER WORKING. It fails closed on four "
                "invariants before it writes anything: a vacuous point-in-time gate, a target week "
                "whose own outcome reaches its own features, a horizon that is not frozen-form, or "
                "a blob that does not validate against the served contract. Read the stderr tail "
                "before assuming an outage.\n\n"
                f"stderr tail:\n{(proc.stderr or '')[-1800:]}")
        _page(context, "NFL weekly serving FAILED", body,
              severity="CRITICAL", dedup_key="nfl_weekly_serving:build")
        raise Exception(f"NFL weekly serving failed (exit {proc.returncode})")

    _verify_published(context, started)


def _verify_published(context, started: datetime) -> None:
    """Read back the manifest this run staged and assert it is THIS run's.

    ⭐ VERIFY THE ARTIFACT, NOT THE EXIT CODE. An exit-0 proves the script ran; it does not prove a
    week advanced. An exporter that silently reused a staged directory, or a publish that ran
    against yesterday's build, cannot pass `generated_at >= this run's start`.

    ⛔ AN UNREADABLE ARTIFACT IS A FAILURE, NEVER A PASS (NF1.7(a) — a check that could not run is
    not a check that succeeded).
    """
    pointer = _APP_DIR / _STAGING
    seasons = sorted(p for p in pointer.glob("*/current.json")) if pointer.exists() else []
    if not seasons:
        _page(context, "NFL weekly serving: cannot verify what was published",
              f"no staged current.json under {pointer}. The build exited 0, so something may well "
              "have shipped — but this run cannot prove it, and an unverifiable publish is "
              "reported as a failure, never as a pass.",
              severity="CRITICAL", dedup_key="nfl_weekly_serving:verify_unreadable")
        raise Exception(f"NFL weekly serving verification found no artifact under {pointer}")

    cur_path = seasons[-1]
    try:
        cur = json.loads(cur_path.read_text())
        man = json.loads((cur_path.parent / str(cur["week"]) / "manifest.json").read_text())
    except Exception as exc:  # noqa: BLE001
        _page(context, "NFL weekly serving: cannot verify what was published",
              f"could not read the staged artifacts beside {cur_path} "
              f"({type(exc).__name__}: {exc}).",
              severity="CRITICAL", dedup_key="nfl_weekly_serving:verify_unreadable")
        raise Exception(f"NFL weekly serving verification could not read {cur_path}: {exc}") from exc

    from betting_ml.monitoring import nfl_weekly_freshness as WF

    gen = WF._parse(man.get("generated_at"))
    fatal = []
    if gen is None or gen < started:
        fatal.append(f"manifest generated_at={man.get('generated_at')} is not from this run "
                     f"(started {started.isoformat()}) — the publish may have shipped a stale build")
    if not man.get("n_players"):
        fatal.append("the published week carries ZERO players")
    for pos, n in (man.get("n_by_position") or {}).items():
        if not n:
            fatal.append(f"position {pos} has ZERO projected players (the NF-K1 class)")
    if not man.get("pit_weeks_checked") or not man.get("pit_records_checked"):
        fatal.append("the point-in-time gate reports zero weeks/records checked — it examined "
                     "nothing, which is not a pass (NF1.7(a))")

    context.log.info("[METRIC] nfl_weekly_players=%s", man.get("n_players"))
    context.log.info("[METRIC] nfl_weekly_week=%s", man.get("week"))
    context.log.info("[METRIC] nfl_weekly_verify_fatal_count=%d", len(fatal))
    if fatal:
        _page(context, "NFL weekly serving: the published artifact failed verification",
              "\n".join(f"- {p}" for p in fatal),
              severity="CRITICAL", dedup_key="nfl_weekly_serving:verify_failed")
        raise Exception("NFL weekly serving verification failed: " + "; ".join(fatal))
    context.log.info("[nfl weekly] verified: %s wk %s, %s players, generated_at=%s",
                     man.get("season"), man.get("week"), man.get("n_players"),
                     man.get("generated_at"))


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_ros_value_publish_op(context):
    """NF-ROS1b node 4 — publish the CERTIFIED rest-of-season value (RB only today).

    ⭐ WHY THIS JOB, NOT A SCHEDULE OF ITS OWN (the NF-WK-RC1 reasoning). It reads the
    `stats_player_week` that `nfl_weekly_stats_ingest_op` refreshes, so it runs downstream of that
    ingest IN THE SAME RUN (INC-25) rather than on a clock racing it, and it inherits this job's
    self-starting, heartbeat-checked schedule instead of adding an instigator that could silently
    revert to STOPPED.

    ⭐ DEPLOY-HELD BY A FLAG, READ HERE AT RUN TIME. `NF_ROS_PUBLISH_ENABLED` unset ⇒ a loud skip and
    nothing written; `nfl_ros_freshness_op` reports that state daily (WARN) from the artifact side.

    ⚖️ TIER — pages and RAISES on a failed publish (never a green run that shipped nothing,
    NF-FRESH1), and VERIFIES what it served by reading the manifest back. Exit 3 is the builder's
    clean "no REG week is final yet" skip, which writes nothing and is not a failure.
    """
    from betting_ml.monitoring import nfl_ros_freshness as RF
    from betting_ml.utils.bounded_subprocess import run_bounded

    if not RF.publish_enabled():
        context.log.warning(
            "[nfl ros] %s is not '1' — the certified ROS publish is ARMED BUT NOT FIRING "
            "(NF-ROS1b deploy-held state). Nothing was built or written. To enable: set it in "
            "services/dagster/aws/.env and redeploy after the post-merge box run.",
            RF.PUBLISH_ENABLED_FLAG)
        return

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    started = datetime.now(timezone.utc)
    cmd = [sys.executable, "-m", f"{_FANTASY}.run_nf_ros1_publish", "--season", str(season),
           "--s3-bucket", NFL_WEEKLY_CACHE_BUCKET, "--board-bucket", NFL_WEEKLY_CACHE_BUCKET,
           "--publish"]
    context.log.info("[nfl ros] %s", " ".join(cmd))
    try:
        proc = run_bounded(cmd, cwd=str(_APP_DIR), env={**os.environ},
                           timeout=NFL_ROS_PUBLISH_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(cmd, returncode=124, stdout=(exc.stdout or ""),
                                           stderr="timeout")
    for line in ((proc.stdout or "") + (proc.stderr or "")).splitlines()[-40:]:
        context.log.info("[ros] %s", line)
    context.log.info("[METRIC] nfl_ros_publish_exit=%d", proc.returncode)

    if proc.returncode == EXIT_ROS_NO_FINAL_WEEK:
        context.log.info("[nfl ros] no REG week of %s is final yet — nothing to update", season)
        return
    if proc.returncode != 0:
        _page(context, "NFL ROS value: the publish failed",
              f"`run_nf_ros1_publish` exited {proc.returncode}. The previously served ROS value "
              f"(if any) keeps serving; consumers keep their stated absences.\n\n"
              f"tail:\n{((proc.stdout or '') + (proc.stderr or ''))[-1500:]}",
              severity="CRITICAL", dedup_key="nfl_ros_publish:failed")
        raise Exception(f"NFL ROS publish failed (exit {proc.returncode})")

    import hashlib

    import boto3

    from app.backend.models import nfl_ros as RC

    fatal = []
    try:
        s3 = boto3.client("s3", region_name="us-east-1")
        cur = json.loads(s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                       Key=f"fantasy/nfl/{RC.ros_current_key(season)}")["Body"].read())
        man = json.loads(s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                       Key=f"fantasy/nfl/{cur['manifest_key']}")["Body"].read())
        body = s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                             Key=f"fantasy/nfl/{cur['players_key']}")["Body"].read()
        gen = RF._parse(man.get("generated_at"))
        if gen is None or gen < started - timedelta(seconds=1):
            fatal.append(f"manifest generated_at={man.get('generated_at')} predates this run")
        if hashlib.sha256(body).hexdigest() != man.get("players_sha256"):
            fatal.append("served players bytes do not match manifest.players_sha256")
        certified = sum(1 for p in json.loads(body)["players"] if p.get("certified"))
        if man.get("certified_for_this_week") and not certified:
            fatal.append("a certified week was published with ZERO certified rows (the NF-K1 class)")
        missing = RC.missing_declared_fields(man, RC.NflRosManifest, where="manifest")
        if missing:
            fatal.append(f"served manifest is short of its contract: {missing[:8]}")
        context.log.info("[METRIC] nfl_ros_through_week=%s certified_rows=%d",
                         man.get("throughWeek"), certified)
    except Exception as exc:  # noqa: BLE001
        fatal.append(f"could not read back the served artifact ({type(exc).__name__}: {exc})")
    context.log.info("[METRIC] nfl_ros_verify_fatal_count=%d", len(fatal))
    if fatal:
        _page(context, "NFL ROS value: the served artifact failed verification",
              "\n".join(f"- {f}" for f in fatal),
              severity="CRITICAL", dedup_key="nfl_ros_publish:verify_failed")
        raise Exception("NFL ROS verification failed: " + "; ".join(fatal))


@job(executor_def=in_process_executor)
def sports_nfl_weekly_serving_job():
    """Refresh the training feeds, judge them, then rebuild + publish + verify the weekly
    projection.

    ⭐ THE ORDER IS THE POINT (NF-INC-0916 node 1). `in_process_executor` runs ops one at a time in
    topological order, so chaining the ingest ahead of the build is what makes "the consumer reads
    a feed this run refreshed" true BY CONSTRUCTION rather than by two crons happening to fire in
    the right order — the INC-25 rule, whose violation is how a serving consumer ends up a full
    cycle behind its own inputs.

    The freshness leg sits between them so its verdict is in the log BEFORE the build's outcome,
    which is the order a reader wants; it never raises and never gates.

    ⭐ AND THE REALIZED-WEEK PUBLISH (NF-WK-RC1 ①) HANGS OFF THE SAME INGEST, in parallel rather
    than in series. It reads `stats_player_week` too, so it needs the same INC-25 ordering — but it
    serves a DIFFERENT product (what happened) from the build (what we expect), and chaining them
    would let a refused projection withhold the realized facts, or a lake hiccup in the realized
    read sink a perfectly good projection. Independent branches: each still runs when the other
    fails.
    """
    landed = nfl_weekly_stats_ingest_op()
    nfl_weekly_serving_op(start=nfl_weekly_stats_freshness_op(start=landed))
    # NF-ROS1b node 4 — a third INDEPENDENT branch off the same ingest (the RC1 reasoning): it reads
    # the `stats_player_week` this run just refreshed, and neither it nor the build can withhold the
    # other. Deploy-held by NF_ROS_PUBLISH_ENABLED, checked inside the op at run time.
    nfl_ros_value_publish_op(start=landed)
    # NF-WK-RC1 ① — an INDEPENDENT branch off the same ingest: it must not be withheld by a
    # refused projection build, and must not withhold one. See the op's own docstring.
    nfl_realized_week_publish_op(start=landed)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The OFF-CYCLE freshness reader — INC-41's shape, and it must not live inside the build job
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⛔ WHY THIS IS A SEPARATE JOB. The failure INC-41 exists to catch is a producer that SUCCEEDS
# while writing nothing — `sports_nfl_sleeper_injuries_job`'s 19 consecutive green runs against one
# 19-day-old commit. A freshness check that runs inside the build it judges is structurally
# incapable of seeing that: it reads an artifact the same run just wrote, so it can only ever agree
# with itself. The check has to run on a DIFFERENT cadence from the writer or it is decoration.
#
# ⭐ AND IT READS THE PUBLISHED BLOB, NOT THE STAGED ONE. What matters is what the routes serve;
# a staged file the publish never uploaded is exactly the gap this is looking for. ⛔ Never an S3
# `LastModified` (INC-41): an mtime is refreshed by a server-side rewrite that changes no data, and
# `aws s3 ls` prints SHELL-LOCAL time. The timestamps come from INSIDE the manifest.
#
# ALERT-tier, never HALT: it judges, it does not gate. A stale weekly projection is a real finding
# and never a reason to withhold anything else.
@op(out=Out(None))
def nfl_weekly_freshness_op(context):
    """Classify the PUBLISHED weekly artifact and page on a real finding."""
    import boto3
    from botocore.exceptions import ClientError

    from app.backend.models import nfl_weekly as C
    from betting_ml.monitoring import nfl_weekly_freshness as WF
    from quant_sports_intel_models.football.nfl.fantasy import weekly_serving as WS

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    s3 = boto3.client("s3", region_name="us-east-1")

    def read(rel: str):
        try:
            return json.loads(s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                            Key=f"fantasy/nfl/{rel}")["Body"].read())
        except ClientError as exc:
            context.log.warning("[nfl weekly freshness] could not read %s: %s", rel, exc)
            return None

    # ⭐ THE EXPECTED WEEK COMES FROM THE SCHEDULE, NOT FROM THE ARTIFACT. Reading it off the thing
    # being judged would make the wrong-week check circular — and wrong-week is the one finding no
    # staleness bar can make, because a build that runs fine on last week's slate has every
    # timestamp healthy while serving a played game.
    expected_week = None
    expected_kickoff = None
    sched = None
    try:
        from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

        sched = q(f"select season, week, gameday from {delta('schedules')} "
                  f"where season = {season} and game_type = 'REG'")
        target = WS.resolve_target_week(sched)
        expected_week = target.week
        # ⭐ THE KICKOFF IS CARRIED, NOT DISCARDED — it is what lets `classify` escalate the
        # NOTHING-PUBLISHED case. Before a season's first successful publish, every other finding
        # the monitor can make reads a field off an artifact that does not exist yet, so without
        # this the verdict is pinned at UNKNOWN/WARN no matter how close the slate is. That is how
        # 2026 week 1 was lost quietly. `resolve_target_week` already computed it; only the `.week`
        # was being kept.
        expected_kickoff = getattr(target.first_kickoff, "to_pydatetime",
                                   lambda: target.first_kickoff)()
    except WS.WeeklyServingError:
        # No upcoming REG week: the artifact is correctly static and no SLA applies.
        expected_week = None
    except Exception as exc:  # noqa: BLE001
        # ⚠️ UNEVALUABLE IS WARN, NEVER HEALTHY (NF1.7(a)) — and it must be distinguishable from the
        # off-season, which is why this branch pages while the one above does not.
        _page(context, "NFL weekly freshness: could not resolve the expected week",
              f"{type(exc).__name__}: {exc}. The published artifact was NOT judged — reported "
              "UNVERIFIED rather than healthy.",
              severity="WARN", dedup_key="nfl_weekly_freshness:unresolvable")
        return

    cur = read(C.weekly_current_key(season))
    week = (cur or {}).get("week", expected_week)
    blob = read(C.weekly_manifest_key(season, week)) if week is not None else None
    reading = WF.reading_from_manifest(season, blob)

    # ⭐ THE SERVED WEEK'S OWN SLATE END — what separates the roster feed's cadence from the INC-37
    # shape. Read from the SCHEDULE (never the artifact being judged, which would make the check
    # circular) and for `reading.week`, NOT the expected week. Absent ⇒ classify judges the mismatch
    # exactly as it did before, so a failure here can only ever cost a FALSE ALARM, never a miss.
    served_slate_ends = None
    if sched is not None and reading.week is not None:
        try:
            served_slate_ends = WS.slate_end(sched, season=season, week=reading.week)
        except Exception as exc:  # noqa: BLE001
            context.log.warning("[nfl weekly freshness] could not resolve the slate end for "
                                "wk %s (%s) — judging the mismatch without it", reading.week, exc)

    verdict = WF.classify(reading, expected_week=expected_week,
                          served_slate_ends=served_slate_ends,
                          expected_kickoff=expected_kickoff)

    context.log.info("[METRIC] nfl_weekly_freshness=%s lag_hours=%s",
                     verdict["verdict"], verdict["lag_hours"])
    context.log.info("[nfl weekly freshness] %s", verdict["detail"])
    if WF.is_problem(verdict):
        _page(context, f"NFL weekly projection is {verdict['verdict']}", verdict["detail"],
              severity=verdict["severity"],
              dedup_key=f"nfl_weekly_freshness:{verdict['verdict']}")


@op(out=Out(None))
def nfl_ros_freshness_op(context):
    """NF-ROS1b — is the PUBLISHED ROS value advancing (and is the deploy-held flag still off)?

    DEFINED HERE, INVOKED from `sports_nfl_sleeper_injuries_job` (a monitor hosted inside its own
    subject cannot see its subject stop). ALERT-tier, never HALT. The policy is
    `betting_ml.monitoring.nfl_ros_freshness`; this op only reads and pages."""
    import boto3
    from botocore.exceptions import ClientError

    from app.backend.models import nfl_ros as RC
    from betting_ml.monitoring import nfl_ros_freshness as RF

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    expected, commit, lake_error = None, None, None
    try:
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_ros1_publish as PUB

        real, sched, _, _ = PUB.lake_reads(season)
        expected = PUB.final_through_week(real, sched)
        from deltalake import DeltaTable

        from quant_sports_intel_models.football.nfl.ingest import s3io
        hist = DeltaTable(s3io.table_uri("nfl", "stats_player_week"),
                          storage_options=s3io.storage_options()).history(1)
        if hist and hist[0].get("timestamp") is not None:
            commit = datetime.fromtimestamp(hist[0]["timestamp"] / 1000, tz=timezone.utc)
    except Exception as exc:  # noqa: BLE001
        lake_error = f"{type(exc).__name__}: {exc}"

    blob = None
    read_error = None
    s3 = boto3.client("s3", region_name="us-east-1")
    try:
        cur = json.loads(s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                       Key=f"fantasy/nfl/{RC.ros_current_key(season)}")["Body"].read())
        blob = json.loads(s3.get_object(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                        Key=f"fantasy/nfl/{cur['manifest_key']}")["Body"].read())
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404"):
            read_error = f"{code}: {exc}"
    except Exception as exc:  # noqa: BLE001
        read_error = f"{type(exc).__name__}: {exc}"

    reading = (RF.RosReading(season=season, error=read_error) if read_error
               else RF.reading_from_manifest(season, blob))
    verdict = RF.classify(reading, enabled=RF.publish_enabled(), expected_through_week=expected,
                          lake_commit=commit, lake_error=lake_error)
    context.log.info("[METRIC] nfl_ros_freshness=%s lag_hours=%s", verdict["verdict"],
                     verdict["lag_hours"])
    context.log.info("[nfl ros freshness] %s", verdict["detail"])
    if RF.is_problem(verdict):
        _page(context, f"NFL ROS value is {verdict['verdict']}", verdict["detail"],
              severity=verdict["severity"], dedup_key=f"nfl_ros_freshness:{verdict['verdict']}")


@job(executor_def=in_process_executor)
def sports_nfl_weekly_freshness_job():
    """On-demand: is the PUBLISHED weekly projection advancing, and is it for the right week?

    ⚠️ THIS JOB IS NOT THE CADENCE, AND SAYING SO MATTERS. `nfl_weekly_freshness_op`'s daily run is
    an independent leaf on `sports_nfl_sleeper_injuries_job` (NF-C6-PH2, 2026-09-13), because a
    monitor hosted inside its own subject cannot see its subject stop — the same argument
    `nfl_published_board_freshness_op` makes, and it applies with extra force here: the weekly build
    SKIPS CLEANLY and reports SUCCESS while the next week's rosters are unpublished, so a schedule
    that silently reverted to STOPPED looks identical to the routine cadence from the artifact side.

    ⛔ This job carries NO schedule ON PURPOSE. It shipped that way and the op consequently NEVER
    RAN — while the builder's own skip message named "the OFF-CYCLE freshness monitor" as the thing
    that escalates. A named escalation path that does not exist is worse than an absent one: it is
    the E11.30 "detected, nobody notified" shape one step earlier, at INVOCATION rather than paging.
    Adding a schedule here would have been the wrong repair (one more instigator that can itself be
    silently STOPPED); riding a job that already self-starts and is heartbeat-checked is the fix.
    What remains is a convenience handle for an operator who wants the verdict on demand."""
    nfl_weekly_freshness_op()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-WK-RC1 ① — the realized-week freshness BACKSTOP
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# ⛔ DEFINED HERE, INVOKED ELSEWHERE — exactly as `nfl_weekly_freshness_op` above. It shares this
# module's bucket and paging helper, so defining it here keeps ONE owner; but it is INVOKED from
# `sports_nfl_sleeper_injuries_job`, because the failure it exists to catch is THIS job not running
# at all, and a monitor hosted inside its own subject cannot see its subject stop.
@op(out=Out(Nothing))
def nfl_realized_freshness_op(context):
    """ALERT (never HALT) — does every week the lake calls FINAL have a published artifact?

    ⭐ A COUNT COMPARISON, NOT AN AGE CHECK. A published week is CORRECT to never change again, so
    an mtime SLA on it would page daily on a healthy file (INC-45) while being blind to the producer
    that succeeds writing nothing (NF-FRESH1). Both sides of this comparison come from outside the
    artifact: the expectation from the lake, the actual from S3.

    ⏳ ACTIVE-SEASON SEMANTICS: out of season no week is FINAL, so there is nothing to publish and
    the verdict is INACTIVE — reported as its own state rather than as OK, because "nothing to
    check" is not "checked and healthy" (NF1.7(a)).
    """
    import boto3

    from betting_ml.monitoring import nfl_realized_freshness as RF

    season = int(os.environ.get("NFL_FANTASY_SEASON", "2026"))
    reading = RF.RealizedReading(season=season)
    try:
        from quant_sports_intel_models.football.nfl.fantasy import realized_week
        from quant_sports_intel_models.football.nfl.ingest.query_lake import delta, q

        sched = q(f"select week, gameday, count(*) n from {delta('schedules')} "
                  f"where season = {season} and game_type = 'REG' group by week, gameday")
        real = q(f"select week, count(distinct game_id) n from {delta('stats_player_week')} "
                 f"where season = {season} and season_type = 'REG' group by week")
        scheduled_by_week: dict[int, int] = {}
        for r in sched.itertuples():
            scheduled_by_week[int(r.week)] = scheduled_by_week.get(int(r.week), 0) + int(r.n)
        realized_by_week = {int(r.week): int(r.n) for r in real.itertuples()}
        states = realized_week.week_completeness_map(realized_by_week, scheduled_by_week)
        reading.lake_final_weeks = {w for w, s in states.items() if s == "final"}
        reading.slate_end_by_week = {
            w: e for w in reading.lake_final_weeks
            if (e := _slate_end_utc(sched, w)) is not None
        }

        s3 = boto3.client("s3", region_name="us-east-1")
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=NFL_WEEKLY_CACHE_BUCKET,
                                       Prefix=f"fantasy/nfl/realized/{season}/"):
            for obj in page.get("Contents") or []:
                parts = obj["Key"].split("/")
                # ⛔ `manifest.json` EXACTLY: a parked `manifest.revision-*.json` is NOT a served
                # week, and counting one would let a restated week hide a genuine publishing gap.
                if parts[-1] == "manifest.json" and parts[-2].isdigit():
                    reading.published_weeks.add(int(parts[-2]))
    except Exception as exc:  # noqa: BLE001
        reading.error = f"{type(exc).__name__}: {exc}"

    verdict = RF.classify(reading)
    context.log.info("[METRIC] nfl_realized_freshness=%s missing=%s",
                     verdict["verdict"], verdict.get("missing"))
    context.log.info("[METRIC] nfl_realized_published_weeks=%s",
                     sorted(reading.published_weeks))
    context.log.info("[nfl realized freshness] %s", verdict["detail"])
    if RF.is_problem(verdict):
        _page(context, f"NFL realized week artifact {verdict['verdict']}", verdict["detail"],
              severity=verdict["severity"],
              dedup_key=f"nfl_realized_freshness:{verdict['verdict']}")

