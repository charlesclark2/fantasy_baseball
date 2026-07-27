from dagster import DefaultScheduleStatus, ScheduleDefinition

from pipeline.jobs.milb_ingest_job import milb_ingest_job

# E7.1/E7.2/E7.7 — daily MiLB + FanGraphs-prospect incremental ingest.
#
# Fires at 13:00 UTC (08:00 ET). MiLB games — including the latest West-coast starts — are Final
# by ~06:00 UTC, so by 13:00 UTC yesterday's whole slate has settled; the --incremental re-pull of
# the current month then captures those finals + any late box revisions. A little after the MLB
# daily_ingestion_job (12:00 UTC), but they run as SEPARATE isolated runs so cadence contention is
# a non-issue.
#
# default_status=RUNNING (E11.23 self-start class): the operator's goal is CONTINUOUS capture — the
# freshly-backfilled 2026 season goes stale without this — so it must self-start on deploy and
# survive a Dagster-DB reset / re-host (never boot STOPPED and silently never fire). Safe to
# auto-run: the Stats API is FREE and FanGraphs THE BOARD is free too (no paid-endpoint /
# double-ingest concern that keeps the intraday CAPTURE schedules STOPPED-on-purpose; the FanGraphs
# fetch routes through our own box FlareSolverr), the writes are idempotent per (season, sport_id,
# month) / (season, as_of_date), all three are Snowflake-FREE (never wakes the warehouse —
# E11.20-COST), and every op is WARN-tier so a failure degrades quietly and touches nothing
# MLB-serving.
milb_ingest_schedule = ScheduleDefinition(
    job=milb_ingest_job,
    cron_schedule="0 13 * * *",
    default_status=DefaultScheduleStatus.RUNNING,
)
