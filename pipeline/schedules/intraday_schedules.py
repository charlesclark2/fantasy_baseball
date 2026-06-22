from dagster import ScheduleDefinition

from pipeline.jobs.intraday_jobs import (
    intraday_schedule_job,
    intraday_weather_job,
    odds_clv_rebuild_job,
)

# E11.4 (2026-06-19) — intraday_schedule_job and intraday_weather_job have been
# decomposed onto Railway cron services:
#   • schedule capture + dbt staging rebuild → services/schedule_capture/ (*/30 * * * *)
#   • weather capture                        → services/weather_capture/  (0 * * * *)
# Their Dagster schedule definitions below are RETAINED (not deleted) so both jobs
# remain available for manual re-runs in the Dagster UI, but their schedules are
# REMOVED from all_intraday_schedules so they no longer auto-fire on Dagster+ metered
# compute. Removing ~48 + ~19 = ~67 daily Dagster fires eliminates the bulk of the
# ~27% run-minute share these two jobs held.

# ── Odds-API CLV / line-movement rebuild (Story 12.3.7 / A2.18) ───────────────
# The full-CTAS post-hoc marts (closing_line_value, prediction_clv, line_movement)
# can't compute anything until the closing line locks at first pitch, so they're
# split off the intraday current-odds path and rebuilt ONCE/day after the last game.
# 08:00 UTC = 04:00 EDT, comfortably after west-coast late games + extra innings.
# The live current-odds path is handled separately by odds_current_rebuild_sensor.
odds_clv_rebuild_schedule = ScheduleDefinition(
    job=odds_clv_rebuild_job,
    cron_schedule="0 8 * * *",
    name="odds_clv_rebuild_daily",
)

# ── Intraday Weather ──────────────────────────────────────────────────────────
# Fires hourly 06:00–22:00 ET (10:00–02:00 UTC). Two cron expressions mirror
# intraday_weather.yml since cron doesn't support wrapping midnight in one expr.

intraday_weather_schedule_daytime = ScheduleDefinition(
    job=intraday_weather_job,
    cron_schedule="0 10-23 * * *",
    name="intraday_weather_daytime",
)

intraday_weather_schedule_overnight = ScheduleDefinition(
    job=intraday_weather_job,
    cron_schedule="0 0-2 * * *",
    name="intraday_weather_overnight",
)

# ── Intraday Schedule Capture ─────────────────────────────────────────────────
# Fires every 30 minutes 10:00 AM – 11:59 PM ET (14:00–03:30 UTC).

intraday_schedule_capture_daytime = ScheduleDefinition(
    job=intraday_schedule_job,
    cron_schedule="*/30 14-23 * * *",
    name="intraday_schedule_capture_daytime",
)

intraday_schedule_capture_overnight = ScheduleDefinition(
    job=intraday_schedule_job,
    cron_schedule="0,30 0-3 * * *",
    name="intraday_schedule_capture_overnight",
)

# E11.4 (2026-06-19) — intraday_weather_* and intraday_schedule_capture_* are OMITTED:
# their jobs are now run by Railway cron services (services/schedule_capture/ and
# services/weather_capture/) off Dagster's metered compute. The ScheduleDefinition
# objects above are kept for manual fallback via the Dagster UI.
all_intraday_schedules = [
    odds_clv_rebuild_schedule,
]
