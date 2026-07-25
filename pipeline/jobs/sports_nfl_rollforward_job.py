"""NF-D1 — the box Dagster job for the annual NFL season roll-forward.

Stands the UPCOMING season's rosters/schedule/depth-charts/injuries/rookie-class data up in the
lake so MVP-1's fantasy board (`mart_nfl_fantasy_season_projection`) can sharpen off REAL
current-season data instead of falling back to the prior season's carryover. Two ops, chained —
mirrors `sports_ncaaf_rollforward_job.py` (NCAAF-P0.7) exactly:

  1. nfl_roll_forward_ingest_op  — refresh rosters/weekly_rosters/schedules/depth_charts/
     injuries/nflverse_draft_picks/nflverse_combine for `current_season()` (clock-derived;
     `ROLL_FORWARD_SOURCES`). Peripheral-ingestion tier: per-source failures are ALERT-loud-but-
     continue (a feed nflverse hasn't published yet — e.g. `injuries` pre-camp — must not sink
     the batch); the op raises ONLY on a TOTAL failure (every source errored), which is a real
     outage worth failing the run on. UNLIKE NCAAF's P0.7, every source here is a FREE
     unauthenticated nflverse release read — no API key is required for this ingest step.
  2. nfl_roll_forward_rebuild_op — rebuild the NFL sports_dbt staging + marts so
     `stg_nfl_schedules` / `stg_nfl_depth_charts` (whose 2025+ branch ASOF-maps each daily ESPN
     snapshot to an NFL week using the schedule) / `stg_nfl_weekly_rosters` / … carry the fresh
     upcoming-season rows. HALT tier (a failed rebuild fails this job's own run). ⭐ WHY THIS OP
     EXISTS: the game-day `sports_nfl_dbt_schedule` is itself operator-gated/STOPPED until
     kickoff (no game played yesterday pre-season anyway), so nothing else rebuilds the marts
     before the season starts — without this step the fresh 2026 rows would sit in raw Delta,
     unread, and the `depth_charts` week-map would stay 0-mapped even after the schedule lands.

ISOLATION (sport_data_platform.md §16.3): a standalone sports job in its own namespace — it fails
ITS OWN run on error and blocks nothing MLB-serving. INC-32 discipline (the subprocess timeout) is
inherited from the shared `_run_sports_dbt` helper.

⚠️ DEPLOY PREREQUISITE (operator): same as `sports_nfl_dbt_build_job` — the box container needs
dbt-duckdb + S3 read on `credence-sports-lakehouse` via the instance role (region us-east-2). The
ingest step itself needs NO credential (nflverse is public).
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

from pipeline.jobs.sports_dbt_job import _run_sports_dbt

# The roll-forward source set is trivially cheap (7 unauthenticated nflverse release reads), but
# keep the finite-timeout discipline: an ingest op on a Dagster worker must never hang forever
# (INC-32). depth_charts is the largest single file (hundreds of thousands of raw daily-snapshot
# rows across 32 teams), so the ceiling is generous.
NFL_ROLL_FORWARD_TIMEOUT_SECONDS = int(os.environ.get("NFL_ROLL_FORWARD_TIMEOUT_SECONDS", "600"))


@op(out=Out(Nothing))
def nfl_roll_forward_ingest_op(context):
    """Refresh the upcoming season's rosters/schedule/depth_charts/injuries/rookie-class
    (WARN-continue tier)."""
    from quant_sports_intel_models.football.nfl.ingest.roll_forward import run_roll_forward
    from quant_sports_intel_models.football.nfl.ingest.sources import (
        ROLL_FORWARD_SOURCES,
        current_season,
    )

    season = current_season()
    context.log.info(
        "NFL roll-forward ingest: season=%s (clock-derived) sources=%s",
        season, ROLL_FORWARD_SOURCES,
    )
    manifest = run_roll_forward(season)

    keyed = {k: v for k, v in manifest.items() if not k.startswith("_")}
    errored = [k for k, v in keyed.items() if isinstance(v, str) and str(v).startswith("ERROR")]
    landed = [k for k, v in keyed.items() if isinstance(v, int) and v > 0]
    empty = [k for k, v in keyed.items() if isinstance(v, int) and v == 0]

    # A not-yet-published feed (0 rows) is EXPECTED pre-camp (e.g. injuries) — log loud, don't fail.
    if empty:
        context.log.warning(
            "⚠️ NFL roll-forward: %d feed(s) returned 0 rows for %s (not yet published by "
            "nflverse; re-run closer to kickoff): %s", len(empty), season, ", ".join(sorted(empty)))
    # A TOTAL failure (every source errored) is a real outage — fail the run so the operator sees it.
    if errored and not landed:
        raise Exception(
            f"🚨 NFL roll-forward ingest TOTALLY FAILED for {season} — every source errored "
            f"(likely a network/S3 outage; nflverse itself needs no key). Errors: {errored}"
        )
    if errored:
        context.log.warning(
            "⚠️ NFL roll-forward: %d feed(s) errored for %s (build kept — landed feeds refreshed): %s",
            len(errored), season, ", ".join(sorted(errored)))
    context.log.info(
        "NFL roll-forward ingest done: %d landed, %d not-yet-published, %d errored.",
        len(landed), len(empty), len(errored))


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_roll_forward_rebuild_op(context):
    """HALT tier — rebuild the NFL marts so the fresh upcoming-season rows are readable.

    Mirrors `sports_nfl_dbt_run_op` (staging serially, then all marts — the serial-staging
    rationale in that op applies identically here). Pre-season there is no play-by-play yet, so
    this materializes an upcoming-season roster/schedule/depth-chart-week-map (and whatever else
    the raw feeds carry), not the realized-game marts.
    """
    staging = _run_sports_dbt(
        context, ["run", "--select", "nfl.staging", "--threads", "1"], "nfl.staging (serial)")
    if staging.returncode != 0:
        raise Exception(
            f"NFL roll-forward STAGING rebuild FAILED (exit {staging.returncode}). See logs above.")
    marts = _run_sports_dbt(
        context, ["run", "--select", "nfl.marts", "--threads", "1"], "nfl.marts")
    if marts.returncode != 0:
        raise Exception(
            f"NFL roll-forward MARTS rebuild FAILED (exit {marts.returncode}). See logs above.")
    context.log.info(
        "NFL roll-forward rebuild PASSED — upcoming-season roster/schedule/depth-chart marts "
        "materialized. Next: re-run MVP-1 (`run_season_projection.py --season <YYYY>`) to pick "
        "up the sharper 2026 role. See the NF-D1 handoff.")


@job(executor_def=in_process_executor)
def sports_nfl_roll_forward_job():
    """Season roll-forward: refresh rosters/schedule/depth_charts/injuries/draft/combine →
    rebuild the NFL marts."""
    nfl_roll_forward_rebuild_op(start=nfl_roll_forward_ingest_op())
