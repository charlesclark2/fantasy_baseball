from dagster import DefaultScheduleStatus, ScheduleDefinition

from pipeline.jobs.settlement_jobs import settle_user_bets_job

# E11.20 phase-2a — evening/overnight settlement passes.
#
# Cron fires at 20:00, 22:00, 00:00, 02:00, 04:00, 06:00 UTC — every 2h across the window
# MLB finals actually land (East day games wrap ~20:00 UTC; late West games ~05:30 UTC). The
# daily_ingestion_job's 12:00 UTC pass covers the morning; together a game finals same-day and
# is settled within ~2h, instead of waiting for the next morning (the 12-24h gap this fixes).
#
# default_status=RUNNING (E11.23 self-start class): this is the mechanism that CLOSES the gap,
# so it must not boot STOPPED and silently never fire (nor revert to STOPPED after a Dagster-DB
# reset / re-host). It is safe to auto-run — idempotent + Snowflake-free + a cheap sparse-GSI
# scan when nothing is pending. (Unlike the intraday CAPTURE schedules, which stay STOPPED on
# purpose: those double-ingest / hit paid endpoints. Settlement does neither.)
settlement_schedule = ScheduleDefinition(
    job=settle_user_bets_job,
    cron_schedule="0 0,2,4,6,20,22 * * *",
    default_status=DefaultScheduleStatus.RUNNING,
)
