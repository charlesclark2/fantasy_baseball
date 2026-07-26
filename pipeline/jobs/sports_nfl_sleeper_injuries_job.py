"""NF-D5 — the box Dagster job for the Sleeper forward-availability feed (daily through camp).

Continues NF-D2 slice 5 (the roster-status unavailability flag): nflverse's roster `status` lags to
camp, but Sleeper's free `v1/players/nfl` snapshot surfaces offseason PUP/IR/surgery designations as
they're reported. Two ops, chained — mirrors `sports_nfl_rollforward_job.py`'s shape, but BOTH ops
are WARN-tier here (unlike the roll-forward job's HALT rebuild step): this whole feed is advisory —
`load_forward_roster_status` (run_season_projection.py) falls back cleanly to nflverse-only when it's
stale/missing, so nothing on this job's critical path may fail the projection.

  1. nfl_sleeper_injuries_ingest_op — fetch Sleeper's player feed, resolve `player_id` (native
     gsis_id + the deterministic name/position crosswalk fallback), land to
     `nfl/raw/sleeper_injuries` (season-partitioned Delta overwrite). WARN-continue: a fetch/network
     failure logs loud and the op still succeeds — never fails the run.
  2. nfl_sleeper_injuries_rebuild_op — refresh JUST the `stg_nfl_sleeper_injuries` staging model
     (not a full `nfl.staging`/`nfl.marts` pass — this one model is cheap) so
     `load_forward_roster_status` sees today's snapshot. WARN-continue too: a failed rebuild just
     means yesterday's (still-served) snapshot stays live one more cycle.

ISOLATION (sport_data_platform.md §16.3): a standalone sports job in its own namespace — it fails
ITS OWN run on error (which it structurally can't, both ops WARN) and blocks nothing MLB-serving.

⚠️ DEPLOY PREREQUISITE (operator): same box-readiness gate as `sports_nfl_dbt_build_job` /
`sports_nfl_roll_forward_job` — dbt-duckdb + S3 read/write on `credence-sports-lakehouse` via the
instance role (region us-east-2). The Sleeper fetch itself needs no credential (public, unauthenticated).
"""

import os

from dagster import In, Nothing, Out, in_process_executor, job, op

from pipeline.jobs.sports_dbt_job import _run_sports_dbt

# Cheap (one unauthenticated HTTP GET + a single-model dbt rebuild), but keep the finite-timeout
# discipline (INC-32): a Dagster op must never hang forever.
NFL_SLEEPER_INJURIES_TIMEOUT_SECONDS = int(os.environ.get("NFL_SLEEPER_INJURIES_TIMEOUT_SECONDS", "120"))


@op(out=Out(Nothing))
def nfl_sleeper_injuries_ingest_op(context):
    """WARN-tier — land Sleeper's `v1/players/nfl` forward-availability snapshot. Advisory/
    non-serving: `load_forward_roster_status` falls back to nflverse-only when this lags or fails,
    so a fetch/landing error here is logged loud but must never fail the run."""
    try:
        import duckdb

        from quant_sports_intel_models.football.nfl.fantasy import sleeper_injuries_source as SI
        from quant_sports_intel_models.football.nfl.ingest import s3io
        from quant_sports_intel_models.football.nfl.ingest.sources import current_season

        duckdb_path = os.environ.get(
            "SPORTS_DUCKDB_PATH", "quant_sports_intel_models/sports_dbt/sports.duckdb")
        season = current_season()
        con = duckdb.connect(duckdb_path, read_only=True)
        try:
            df = SI.load_sleeper_injuries(con, season)
        finally:
            con.close()
        n = s3io.write_dataframe(df, sport="nfl", source="sleeper_injuries", season=int(season), tier="raw")
        cov = SI.coverage(df)
        context.log.info(
            "NFL Sleeper injuries: landed %d rows for season=%s (%d gsis-matched, %d flagged: %s)",
            n, season, cov["n_matched"], cov["n_flagged"], cov.get("by_injury_status"))
    except Exception as exc:  # noqa: BLE001 — WARN-tier: advisory, non-serving (see module docstring)
        context.log.warning(
            "⚠️ ALERT NFL Sleeper injuries ingest failed (%s) — projections fall back to "
            "nflverse-only forward roster status; will retry next cadence.", exc)


@op(ins={"start": In(Nothing)}, out=Out(Nothing))
def nfl_sleeper_injuries_rebuild_op(context):
    """WARN-tier — refresh just `stg_nfl_sleeper_injuries` (a single cheap model, not a full
    nfl.staging pass) so `load_forward_roster_status` sees today's snapshot. A failed rebuild just
    means the previously-served snapshot stays live one more cycle — never fails the run."""
    result = _run_sports_dbt(
        context, ["run", "--select", "stg_nfl_sleeper_injuries", "--threads", "1"],
        "stg_nfl_sleeper_injuries")
    if result.returncode != 0:
        context.log.warning(
            "⚠️ stg_nfl_sleeper_injuries rebuild FAILED (exit %s) — yesterday's snapshot stays "
            "served; investigate above.", result.returncode)
    else:
        context.log.info("stg_nfl_sleeper_injuries rebuilt — today's Sleeper snapshot is live.")


@job(executor_def=in_process_executor)
def sports_nfl_sleeper_injuries_job():
    """Daily (through camp) Sleeper forward-availability capture → refresh the staging model.
    WARN-tier throughout — advisory, never blocks the projection or any other job."""
    nfl_sleeper_injuries_rebuild_op(start=nfl_sleeper_injuries_ingest_op())
