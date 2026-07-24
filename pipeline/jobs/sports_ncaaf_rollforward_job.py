"""NCAAF-P0.7 — the box Dagster job for the annual PRE-SEASON season roll-forward.

Stands the UPCOMING season's pre-season data up in the lake so the P1.5 futures board + the live
P1.4 game-model board can RUN before kickoff. Two ops, chained:

  1. ncaaf_roll_forward_ingest_op  — refresh the SCHEDULE + pre-season COVARIATES for
     `current_season()` (clock-derived; `ROLL_FORWARD_SOURCES`). Peripheral-ingestion tier:
     per-source failures are ALERT-loud-but-continue (a covariate CFBD hasn't published yet must
     not sink the batch); the op raises ONLY on a TOTAL failure (every source errored — e.g. a
     missing/expired CFBD key), which is a real outage worth failing the run on.
  2. ncaaf_roll_forward_rebuild_op — rebuild the NCAAF sports_dbt marts so `dim_ncaaf_game` +
     the roster/coaching marts carry the fresh upcoming-season rows. HALT tier (a failed rebuild
     fails this job's own run). ⭐ WHY THIS OP EXISTS: the game-day `sports_ncaaf_dbt_schedule`
     SKIPs pre-season (no game was played yesterday), so nothing else rebuilds the marts before
     kickoff — without this step the fresh 2026 schedule would sit in raw Delta, unread.

ISOLATION (sport_data_platform.md §16.3): a standalone sports job in its own namespace — it fails
ITS OWN run on error and blocks nothing MLB-serving. INC-32 discipline (the subprocess timeout) is
inherited from the shared `_run_sports_dbt` helper.

After this job lands + rebuilds, P1.2 must be re-fit for the season and the board rendered — those
are the OPERATOR steps (`run_team_strength` is the multi-minute >1-min job; see the P0.7 handoff),
not wired here, because P1.2 is a once-per-season refit, not a weekly one.

⚠️ DEPLOY PREREQUISITE (operator): the box container needs `CFBD_API_KEY` in its env (the same
free-tier key the backfill used) — the roll-forward ingest calls CFBD `/games` + the covariate
endpoints. dbt-duckdb + the us-east-2 S3 region are the same prereqs the sports dbt job documents.
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

from pipeline.jobs.sports_dbt_job import _run_sports_dbt

# The roll-forward source set is trivially cheap (~8 CFBD calls), but keep the finite-timeout
# discipline: an ingest op on a Dagster worker must never hang forever (INC-32).
ROLL_FORWARD_TIMEOUT_SECONDS = int(os.environ.get("NCAAF_ROLL_FORWARD_TIMEOUT_SECONDS", "600"))


@op(out=Out(Nothing))
def ncaaf_roll_forward_ingest_op(context):
    """Refresh the upcoming season's schedule + pre-season covariates (WARN-continue tier)."""
    from quant_sports_intel_models.football.ncaaf.ingest.roll_forward import run_roll_forward
    from quant_sports_intel_models.football.ncaaf.ingest.sources import (
        ROLL_FORWARD_SOURCES,
        current_season,
    )

    season = current_season()
    context.log.info(
        "NCAAF roll-forward ingest: season=%s (clock-derived) sources=%s",
        season, ROLL_FORWARD_SOURCES,
    )
    manifest = run_roll_forward(season)

    keyed = {k: v for k, v in manifest.items() if not k.startswith("_")}
    errored = [k for k, v in keyed.items() if isinstance(v, str) and str(v).startswith("ERROR")]
    landed = [k for k, v in keyed.items() if isinstance(v, int) and v > 0]
    empty = [k for k, v in keyed.items() if isinstance(v, int) and v == 0]

    # A not-yet-published covariate (0 rows) is EXPECTED pre-season — log loud, do not fail.
    if empty:
        context.log.warning(
            "⚠️ NCAAF roll-forward: %d feed(s) returned 0 rows for %s (not yet published by CFBD; "
            "re-run closer to kickoff): %s", len(empty), season, ", ".join(sorted(empty)))
    # A TOTAL failure (every source errored) is a real outage — fail the run so the operator sees it.
    if errored and not landed:
        raise Exception(
            f"🚨 NCAAF roll-forward ingest TOTALLY FAILED for {season} — every source errored "
            f"(likely a missing/expired CFBD_API_KEY on the box). Errors: {errored}"
        )
    if errored:
        context.log.warning(
            "⚠️ NCAAF roll-forward: %d feed(s) errored for %s (build kept — landed feeds refreshed): %s",
            len(errored), season, ", ".join(sorted(errored)))
    context.log.info(
        "NCAAF roll-forward ingest done: %d landed, %d not-yet-published, %d errored.",
        len(landed), len(empty), len(errored))


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def ncaaf_roll_forward_rebuild_op(context):
    """HALT tier — rebuild the NCAAF marts so the fresh upcoming-season rows are readable.

    Mirrors `sports_ncaaf_dbt_run_op` (staging serially, then all marts — the serial-staging
    rationale in that op applies identically here). Pre-season there are no completed games, so
    this materializes an upcoming-season `dim_ncaaf_game` (schedule) + the covariate marts.
    """
    staging = _run_sports_dbt(
        context, ["run", "--select", "ncaaf.staging", "--threads", "1"], "ncaaf.staging (serial)")
    if staging.returncode != 0:
        raise Exception(
            f"NCAAF roll-forward STAGING rebuild FAILED (exit {staging.returncode}). See logs above.")
    marts = _run_sports_dbt(
        context, ["run", "--select", "ncaaf.marts", "--threads", "1"], "ncaaf.marts")
    if marts.returncode != 0:
        raise Exception(
            f"NCAAF roll-forward MARTS rebuild FAILED (exit {marts.returncode}). See logs above.")
    context.log.info(
        "NCAAF roll-forward rebuild PASSED — upcoming-season schedule + covariate marts materialized. "
        "Next: re-fit P1.2 (run_team_strength) for the season, then render the board "
        "(run_season_simulation --season <YYYY>). See the P0.7 handoff.")


@job(executor_def=in_process_executor)
def sports_ncaaf_roll_forward_job():
    """Pre-season roll-forward: refresh schedule + covariates → rebuild the NCAAF marts."""
    ncaaf_roll_forward_rebuild_op(start=ncaaf_roll_forward_ingest_op())
