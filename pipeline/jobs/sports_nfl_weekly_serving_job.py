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
from datetime import datetime, timezone
from pathlib import Path

from dagster import Out, in_process_executor, job, op

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


def _page(context, title: str, body: str, *, severity: str, dedup_key: str) -> None:
    """Page, and mirror it into the step log. Distinct `dedup_key` per failure mode so one noisy
    leg cannot occupy another's 1-hour rate-limit slot (INC-39)."""
    from pipeline.utils.alerting import send_alert

    send_alert(title, body, severity=severity, dedup_key=dedup_key)
    context.log.warning("ALERT [nfl weekly] %s — %s", title, body)


@op(out=Out(None))
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


@job(executor_def=in_process_executor)
def sports_nfl_weekly_serving_job():
    """Rebuild + publish the NFL weekly projection for the next unplayed week, then verify it."""
    nfl_weekly_serving_op()
