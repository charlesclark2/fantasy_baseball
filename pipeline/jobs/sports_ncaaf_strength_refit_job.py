"""NCAAF-P1.2W — the box Dagster job for the WEEKLY in-season P1.2 strength re-fit.

WHAT WAS BROKEN. Every NCAAF surface's strength rating, uncertainty band and both ranks move only
when the P1.2 posterior is re-fit, and P1.2 was built as a ONCE-PER-SEASON refit that nothing
schedules. NCAAF-P3.3b measured the consequence three ways that agree, and it was still true on
2026-09-13: `ncaaf/derived/team_strength_week` last committed 2026-08-18 and carries `as_of_week=1`
and nothing else, while `ncaaf/raw/games` had advanced to 2026-09-07 — three played weeks in which
a team could win by 26 and see its rating sit unchanged beside that win in its own schedule.

⛔ THE FIT ITSELF IS UNTOUCHED. Same P1.2 model, same CLI, same artifacts, same registered
behaviour. This job schedules an EXISTING operator runbook (the NCAAF-PS report's operator section
and `BOX_OPERATIONS.md §10`); it re-selects nothing and re-reads no P1.x calibration verdict.

═══ THE DISCRIMINATOR IS THE WHOLE STORY ══════════════════════════════════════════════════════

P1.2 reads its covariates from the sports dbt MARTS, not from the lake — so `run_team_strength`
against STALE marts silently reproduces the pre-season cold start, writes a full set of Delta
commits, exits 0 and looks like a successful re-fit. It did exactly that on 2026-08-17. Two
consequences shape this graph:

  * ⭐ THE MARTS REBUILD RUNS **INSIDE** THIS JOB, BEFORE THE FIT — never assumed done by a sibling
    schedule. `sports_ncaaf_dbt_schedule` genuinely rebuilds them most in-season mornings, and
    relying on that is precisely the INC-25 shape (a consumer that only ever runs on its own cron
    is one slow upstream away from reading last cycle's inputs). It costs ~90s and removes the
    entire class.
  * ⭐ THE RUN MUST PROVE "IT WORKED", NOT "IT RAN". `ncaaf_strength_verify_op` reads the landed
    artifact and FAILS the run — loudly, with a page — on a cold-start reproduction, on a vintage
    that did not advance, or on a week index that stayed at 1 while the marts held completed games.
    A green tick over a frozen table is the NF-FRESH1 class (19 consecutive green runs), and this
    job's whole reason to exist is that the frozen state is indistinguishable from the healthy one
    unless something goes and looks.

═══ SEQUENCING ════════════════════════════════════════════════════════════════════════════════

Monday 07:30 PT, 90 minutes after `sports_ncaaf_roll_forward_schedule`'s 06:00 raw ingest. ⛔ The
cron offset is a COURTESY, NOT the ordering guarantee: `ncaaf_strength_precondition_op` REFUSES to
fit when `ncaaf/raw/games` has not committed inside `RAW_MAX_LAG_HOURS`, so a roll-forward that
failed, was toggled off, or ran late produces a paged refusal rather than a confident re-fit of
last week's data (the vintage-match precondition pattern). The two jobs also do not overlap on the
sports DuckDB at 90 minutes' remove, and the `concurrency_group` tag below caps this job at one
concurrent run so a slow week can never stack on the next.

🖥️ BOX PREREQUISITES: `SPORTS_DUCKDB_PATH` inside the `sports_duckdb` named volume (it is in
`env.required`, so a deploy fails without it) and dbt-duckdb + S3 instance-role read — the same
prereqs `sports_ncaaf_dbt_build_job` documents. No CFBD key, no Odds-API credits, no warehouse.

⏱️ TIERS: every op is HALT. This job produces ONE artifact and each step is a precondition for the
next; there is no peripheral half worth continuing past. A failed run is visible in Dagit, pages
through `run_failure_alert_sensor`, and is safely re-fireable — the ratings are a rewritable
derived table, not the immutable pre-kickoff snapshot.
"""

import os
from pathlib import Path

from dagster import In, Nothing, Out, in_process_executor, job, op

from betting_ml.utils.sports_duckdb import (
    missing_duckdb_remedy,
    resolve_sports_duckdb,
    sports_duckdb_env,
)
from pipeline.jobs.sports_dbt_job import _run_sports_dbt
from pipeline.jobs.sports_ncaaf_serving_write_job import (
    ncaaf_serving_write_after_snapshot_op,
)

#: How stale `ncaaf/raw/games` may be and still be fit on. 48h clears a Monday 07:30 run against
#: the 06:00 roll-forward with enormous slack and clears a Tuesday retry, while refusing a feed
#: that has missed its weekly cycle entirely — which is the state that makes a re-fit pointless
#: (nothing new to absorb) and its "refreshed" stamp an overclaim.
RAW_MAX_LAG_HOURS = float(os.environ.get("NCAAF_STRENGTH_REFIT_RAW_MAX_LAG_HOURS", "48"))

#: INC-32 — a finite ceiling on the multi-minute fit. `run_bounded` kills the whole process GROUP
#: on expiry, so a wedged fit cannot leave a grandchild holding one of the box's two vCPUs.
REFIT_TIMEOUT_SECONDS = int(os.environ.get("NCAAF_STRENGTH_REFIT_TIMEOUT_SECONDS", "3600"))

#: E11.26 — the job's own wall-clock ceiling, and it is sized from the legs rather than guessed:
#: staging (<=2400) + marts (<=2400) + fit (<=3600) + serving write (<=900) = 9300s worst case, so
#: `leg_cap < job_ceiling < cadence` holds (9300 < 10800 << 604800, one week). It also sits under
#: the instance-wide `max_runtime_seconds: 14400`, which is sized for the Sunday MLB full refresh.
JOB_MAX_RUNTIME_SECONDS = int(os.environ.get("NCAAF_STRENGTH_REFIT_MAX_RUNTIME_S", "10800"))


def _page(context, title: str, body: str, *, severity: str, dedup_key: str) -> None:
    """Page, and mirror it into the step log. A distinct `dedup_key` per failure mode so one noisy
    leg cannot occupy another's rate-limit slot (INC-39)."""
    from pipeline.utils.alerting import send_alert

    send_alert(title, body, severity=severity, dedup_key=dedup_key)
    context.log.warning("ALERT [ncaaf strength refit] %s — %s", title, body)


@op(out=Out(dict))
def ncaaf_strength_precondition_op(context) -> dict:
    """HALT — refuse to fit on a missing DuckDB or stale raw, and capture the BEFORE vintage.

    ⭐ THE BEFORE VINTAGE IS TAKEN HERE, IN THE SAME RUN, which is what lets the verify op assert
    the artifact ADVANCED without persisting any state between runs. It is a CONTENT read from
    inside `_delta_log` — never an object mtime and never an `aws s3 ls` LastModified (INC-41:
    an mtime is refreshed by a server-side rewrite that changes no data, and `aws s3 ls` prints
    SHELL-LOCAL time, so either would report a frozen artifact as fresh).
    """
    from betting_ml.monitoring import ncaaf_strength_refit as REFIT
    from betting_ml.monitoring import sports_delta_freshness as SDF
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season

    season = current_season()
    duckdb_path = resolve_sports_duckdb()

    # PRECONDITION 1 — the DIRECTORY the resolved path lives in must exist. Deliberately the
    # directory and not the file: the marts rebuild two ops down CREATES the database, so a
    # first-ever run on a fresh volume is legitimate. An absent DIRECTORY, though, means
    # SPORTS_DUCKDB_PATH does not point inside the mounted `sports_duckdb` volume — dbt would
    # happily build a NEW database somewhere deploy-ephemeral and the fit would read a file
    # nothing else ever opens (the NF-FRESH1 / four-owners trap, which is what this resolver and
    # this check exist to close).
    if not duckdb_path.parent.exists():
        msg = missing_duckdb_remedy(duckdb_path)
        _page(context, "NCAAF strength re-fit: sports DuckDB directory missing", msg,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:no_duckdb")
        raise Exception(f"NCAAF strength re-fit precondition failed — {msg}")

    # PRECONDITION 2 — the raw games feed must have landed this cycle. The roll-forward at 06:00 is
    # what advances it; a cron offset alone is not an ordering guarantee (INC-25).
    from dataclasses import replace
    raw = replace(SDF.REGISTRY[0], name="ncaaf_raw_games", sport="ncaaf", source="games",
                  tier="raw", max_lag_hours=RAW_MAX_LAG_HOURS, active_months=None,
                  cadence="weekly, Monday 06:00 PT (sports_ncaaf_roll_forward_schedule)")
    raw_reading = SDF.read_contract(raw)
    raw_verdict = SDF.classify(raw, raw_reading)
    context.log.info("[METRIC] ncaaf_refit_raw_games_verdict=%s lag_hours=%s version=%s",
                     raw_verdict["verdict"], raw_verdict["lag_hours"], raw_reading.version)
    if SDF.is_problem(raw_verdict):
        body = (
            f"{raw_verdict['detail']}\n\n"
            f"The P1.2 re-fit was REFUSED rather than run: fitting on raw games this old would "
            f"rebuild the marts from a feed that has nothing new in it and then stamp the result "
            f"as a fresh weekly refresh, which is an overclaim on the served 'ratings as of' "
            f"line.\n\nFIRST ACTION: confirm `sports_ncaaf_roll_forward_schedule` is RUNNING in "
            f"Dagit and that its last run is green; re-fire `sports_ncaaf_roll_forward_job`, then "
            f"re-fire this job. For a deliberate off-cycle fit, set "
            f"NCAAF_STRENGTH_REFIT_RAW_MAX_LAG_HOURS on the box and say so in the run log.")
        _page(context, f"NCAAF strength re-fit REFUSED — raw games {raw_verdict['verdict']}", body,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:stale_raw")
        raise Exception(f"NCAAF strength re-fit precondition failed — {raw_verdict['detail']}")

    before = REFIT.read_refit_state(season)
    context.log.info(
        "[METRIC] ncaaf_refit_before_version=%s before_commit=%s before_max_as_of_week=%s",
        before.version, before.commit.isoformat() if before.commit else None,
        before.max_as_of_week)
    context.log.info(
        "NCAAF strength re-fit preconditions PASSED: season=%s duckdb=%s raw games v%s (%sh old). "
        "Ratings BEFORE this run: Delta v%s at %s, max as_of_week=%s.",
        season, duckdb_path, raw_reading.version, raw_verdict["lag_hours"],
        before.version, before.commit, before.max_as_of_week)
    return {
        "season": season,
        "before_version": before.version,
        "before_commit": before.commit.isoformat() if before.commit else None,
        "before_max_as_of_week": before.max_as_of_week,
        "before_error": before.error,
        "duckdb_path": str(duckdb_path),
    }


@op(ins={"start": In(dict)}, out=Out(dict))
def ncaaf_strength_marts_rebuild_op(context, start: dict) -> dict:
    """HALT — rebuild the NCAAF marts from the fresh lake, so the fit reads today's covariates.

    ⭐ THIS OP IS THE REASON THE JOB EXISTS IN THIS SHAPE. `run_team_strength` reads
    `ncaaf_team_roster_continuity` / `ncaaf_team_coaching_change` out of the DuckDB marts; against
    stale marts it reproduces the cold start and exits 0. Mirrors `sports_ncaaf_dbt_run_op`
    exactly — staging serially (the `fact_ncaaf_play` memory rationale), then the marts folder —
    and goes through the SAME `_run_sports_dbt` helper, which pins `SPORTS_DUCKDB_PATH` to the ONE
    resolved absolute path via `sports_duckdb_env()`. A private dbt invocation here would be a
    second owner of that path, which is the NF-INFRA1 defect in miniature.
    """
    staging = _run_sports_dbt(
        context, ["run", "--select", "ncaaf.staging", "--threads", "1"], "ncaaf.staging (serial)")
    if staging.returncode != 0:
        body = (f"the NCAAF staging rebuild exited {staging.returncode}; the P1.2 fit was NOT run. "
                f"Fitting on the marts as they stand would reproduce whatever vintage they hold.\n\n"
                f"stderr tail:\n{(staging.stderr or '')[-1500:]}")
        _page(context, "NCAAF strength re-fit: marts STAGING rebuild failed", body,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:staging_failed")
        raise Exception(f"NCAAF strength re-fit STAGING rebuild FAILED (exit {staging.returncode}).")

    marts = _run_sports_dbt(context, ["run", "--select", "ncaaf.marts", "--threads", "1"],
                            "ncaaf.marts")
    if marts.returncode != 0:
        body = (f"the NCAAF marts rebuild exited {marts.returncode}; the P1.2 fit was NOT run.\n\n"
                f"stderr tail:\n{(marts.stderr or '')[-1500:]}")
        _page(context, "NCAAF strength re-fit: MARTS rebuild failed", body,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:marts_failed")
        raise Exception(f"NCAAF strength re-fit MARTS rebuild FAILED (exit {marts.returncode}).")

    # The activity count for the verify op's week-index reading, taken from the marts the fit is
    # ABOUT to read — so "could the week index have advanced at all?" is answered on the same
    # inputs rather than inferred (NF-D20: report the count of rows a check could act on).
    from betting_ml.monitoring import ncaaf_strength_refit as REFIT

    completed = REFIT.read_completed_games(start["season"], start["duckdb_path"])
    context.log.info("[METRIC] ncaaf_refit_completed_games=%s season=%s",
                     completed, start["season"])
    context.log.info(
        "NCAAF marts rebuilt from the fresh lake — the fit will read TODAY's covariates. The marts "
        "hold %s completed team-game row(s) for season %s.",
        "an unreadable number of" if completed is None else completed, start["season"])
    return {**start, "completed_games": completed}


@op(ins={"start": In(dict)}, out=Out(dict))
def ncaaf_strength_fit_op(context, start: dict) -> dict:
    """HALT — run the P1.2 CLI unchanged (`run_team_strength --s3`) over the freshly built marts.

    ⛔ INVOKED AS THE SHIPPED CLI, in a bounded subprocess, rather than re-implemented in-process.
    The registered P1.2 behaviour is what that entrypoint does — its gates, its report, its lake
    write — and a second caller that assembled the same fit itself would be free to drift from the
    model the calibration verdicts were recorded against (the E9.61 two-renderers class).
    """
    import subprocess
    import sys

    from betting_ml.utils.bounded_subprocess import run_bounded

    cmd = [
        sys.executable, "-m",
        "quant_sports_intel_models.football.ncaaf.models.run_team_strength",
        "--duckdb", start["duckdb_path"],
        "--s3",
    ]
    env = {
        **sports_duckdb_env(),
        "DAGSTER_JOB_NAME": context.job_name,
        # delta-rs + DuckDB both need the lake region explicit (boto3 is region-less).
        "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2"),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
    }
    context.log.info("[ncaaf strength fit] %s (timeout %ss)", " ".join(cmd), REFIT_TIMEOUT_SECONDS)
    try:
        result = run_bounded(cmd, env=env, cwd=_repo_root(), timeout=REFIT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        body = (f"`run_team_strength` exceeded {REFIT_TIMEOUT_SECONDS}s and its process group was "
                f"killed. The lake may hold a PARTIAL re-fit (the CLI writes one Delta commit per "
                f"season), so read the verify step's vintage before assuming nothing landed.\n\n"
                f"stdout tail:\n{(exc.stdout or '')[-1000:]}\n\n"
                f"stderr tail:\n{(exc.stderr or '')[-1500:]}")
        _page(context, "NCAAF strength re-fit TIMED OUT", body,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:timeout")
        raise Exception(f"NCAAF strength re-fit TIMED OUT after {REFIT_TIMEOUT_SECONDS}s.") from exc

    if result.stdout:
        context.log.info(result.stdout[-8000:])
    if result.stderr:
        context.log.warning(result.stderr[-4000:])
    if result.returncode != 0:
        body = (f"`run_team_strength` exited {result.returncode}. The served ratings are unchanged "
                f"— this is a failed refresh, not a corrupted one.\n\n"
                f"stderr tail:\n{(result.stderr or '')[-1500:]}")
        _page(context, "NCAAF strength re-fit FAILED", body,
              severity="CRITICAL", dedup_key="ncaaf_strength_refit:fit_failed")
        raise Exception(f"NCAAF strength re-fit FAILED (exit {result.returncode}).")
    context.log.info("run_team_strength exited 0 — now VERIFYING that it took, not merely ran.")
    return start


@op(ins={"start": In(dict)}, out=Out(Nothing))
def ncaaf_strength_verify_op(context, start: dict) -> None:
    """HALT — prove the re-fit WORKED. A cold-start reproduction is a paged FAILURE, never a green
    tick.

    Three readings, each answering what the others structurally cannot — see
    `betting_ml/monitoring/ncaaf_strength_refit.py` for why all three are needed and why the
    covariate check ALONE is satisfied by the frozen artifact this story exists to unfreeze.
    """
    from betting_ml.monitoring import ncaaf_strength_refit as REFIT

    season = start["season"]
    before = REFIT.RefitState(
        season=season, version=start.get("before_version"),
        commit=_parse_iso(start.get("before_commit")),
        max_as_of_week=start.get("before_max_as_of_week"),
        error=start.get("before_error"))
    after = REFIT.read_refit_state(season)
    verdict = REFIT.classify_refit(before, after, completed_games=start.get("completed_games"))

    for key, value in verdict["metrics"].items():
        context.log.info("[METRIC] ncaaf_refit_%s=%s", key, value)
    context.log.info("[METRIC] ncaaf_refit_verdict=%s", verdict["verdict"])

    if not REFIT.is_problem(verdict):
        context.log.info("NCAAF strength re-fit VERIFIED — %s", verdict["detail"])
        return

    body = (f"{verdict['detail']}\n\n"
            f"Metrics: {verdict['metrics']}\n\n"
            f"FIRST ACTION: re-run this job and read the marts-rebuild step. P1.2 reads its "
            f"covariates from the sports dbt marts, so a cold start means the marts did not carry "
            f"this season's roster/coaching rows when the fit read them.")
    _page(context, f"NCAAF strength re-fit {verdict['verdict']}", body,
          severity=verdict["severity"] or "CRITICAL",
          dedup_key=f"ncaaf_strength_refit:verify:{verdict['verdict']}")
    raise Exception(f"NCAAF strength re-fit verification FAILED ({verdict['verdict']}): "
                    f"{verdict['detail']}")


def _repo_root() -> str:
    """The working directory for the P1.2 CLI: `$APP_DIR` on the box (`/app`), the repo root off
    it. Resolved from THIS file rather than from the process CWD — an op and the subprocess it
    spawns must never resolve the same relative path differently (the `sports_duckdb_env` rule)."""
    return os.environ.get("APP_DIR") or str(Path(__file__).resolve().parents[2])


def _parse_iso(value: "str | None"):
    from datetime import datetime

    return datetime.fromisoformat(value) if value else None


@job(
    executor_def=in_process_executor,
    tags={
        # E11.26 — the authoritative wall-clock ceiling; it bounds EVERY wait in the run, not just
        # the subprocess ones each leg already caps.
        "dagster/max_runtime": JOB_MAX_RUNTIME_SECONDS,
        # A2.16 — `tag_concurrency_limits` in services/dagster/dagster.yaml caps one run per group,
        # so a slow week queues behind itself instead of two fits competing for two vCPUs and for
        # the same DuckDB file.
        "concurrency_group": "ncaaf_strength_refit",
        "sport": "ncaaf",
    },
)
def sports_ncaaf_strength_refit_job():
    """Preconditions → marts rebuild → P1.2 fit → VERIFY it took → publish to the serving store.

    ⭐ THE SERVING WRITE IS CHAINED HERE, AND THE PREDICTION SNAPSHOT DELIBERATELY IS NOT.
    The team pages read the strength rating and its band straight from the LAKE, so the serving
    store is a direct CONSUMER of what this job just wrote and must be rebuilt downstream of it in
    the same run (INC-25) — otherwise the refreshed ratings sit in the lake until the hourly
    top-up happens to fire. The pre-kickoff prediction snapshot is a different artifact with its
    own deadline semantics (immutable, one row per `(game_id, snapshot_ts)`, and NOT re-writable),
    and it already has an owner in `sports_ncaaf_prediction_snapshot_schedule` firing Tuesday
    morning — i.e. downstream of this job in time, reading the fresh ratings. Chaining it here
    would give one immutable weekly track record two cadence owners, which is this repo's
    most-repeated operational defect (INC-30 / INC-36 / INC-38). Recorded as a deliberate
    departure from the runbook's literal chain so the PM can reverse it in one line.
    """
    ncaaf_serving_write_after_snapshot_op(
        start=ncaaf_strength_verify_op(
            start=ncaaf_strength_fit_op(
                start=ncaaf_strength_marts_rebuild_op(
                    start=ncaaf_strength_precondition_op()))))
