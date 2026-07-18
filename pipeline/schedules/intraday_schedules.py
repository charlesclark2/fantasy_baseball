from dagster import DefaultScheduleStatus, ScheduleDefinition

from pipeline.jobs.intraday_jobs import (
    intraday_public_betting_job,
    intraday_schedule_job,
    intraday_weather_job,
    odds_clv_rebuild_job,
)
# lineup_monitor_schedule_* — a 30-min cron alternate driver for the lineup re-score, added
# 2026-07-07 when the sensor was unreliable. INC-32 (2026-07-18) DEMOTED them to default_status=
# STOPPED (manual fallback): the lineup_monitor_sensor is now the sole driver (un-wedgeable +
# staleness-heartbeat-checked), and running both double-fired lineup_monitor_job. Still registered
# here (join all_intraday_schedules) so an operator can toggle one on if ever needed.
from pipeline.sensors.lineup_monitor_sensor import (
    lineup_monitor_schedule_daytime,
    lineup_monitor_schedule_overnight,
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
    # E11.23: default_status=RUNNING — the daily CLV / line-movement rebuild is serving-adjacent
    # (the pick-detail line-movement chart + CLV monitoring read it); self-start on the box / after
    # a DB reset instead of silently booting STOPPED. NOTE: the intraday_schedule_capture_* and
    # intraday_public_betting_* schedules below stay default-STOPPED ON PURPOSE — they need an
    # explicit operator opt-in (disable the lean host-cron / set W11_RAW_WRITE_MODE) to avoid
    # double-ingest, so they are NOT in the self-start / silently-not-running critical set.
    default_status=DefaultScheduleStatus.RUNNING,
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

# E11.4 (2026-06-19) — intraday_weather_* WAS offloaded to a Railway/EC2 cron service
# (services/weather_capture/) and stays omitted here.
#
# INC-22 (2026-06-29) — intraday_schedule_capture_* are RE-ADDED to Dagster (operator's
# Option-2 decision). The lean services/schedule_capture/ cron could ONLY refresh native
# Snowflake + the lineup VIEWS — but post-W6 those are views over the S3 lakehouse_ext
# external tables, so the lean cron's rebuild was a NO-OP for served data: intraday lineup/
# game-state captures never reached the S3 parquet prod actually serves (the 6/29 evening-
# slate miss). The Dagster job has DuckDB + boto3 + run_w1_lakehouse on the box, so its
# intraday_schedule_capture op runs the full parquet/DuckDB propagation chain
# (_schedule_lakehouse_intraday: export today's raw → S3 → run_w1_lakehouse --w3pre-only →
# refresh external tables) and then intraday_lineup_rebuild re-materializes the downstream
# lineup/pitcher TABLES off the now-fresh views. Gated by SCHEDULE_LAKEHOUSE_INTRADAY=1.
#
# OPERATOR (enabling Option 2):
#   1. set SCHEDULE_LAKEHOUSE_INTRADAY=1 on the Dagster box (else the S3 chain no-ops),
#   2. START intraday_schedule_capture_daytime + _overnight in the Dagster UI (repo
#      convention: schedules boot STOPPED — they will NOT auto-fire until toggled),
#   3. DISABLE the lean services/schedule_capture/ EC2 cron so the two don't double-ingest.
# The ScheduleDefinitions fire on UTC cron, but every op resolves the baseball-day via
# current_game_date_iso() (LA), so the captured/served date is correct (INC-22).
# ── Intraday Public Betting (E11.1-W11-D addendum) ────────────────────────────
# Hourly ActionNetwork public-betting capture across the pre-game window, building the public-%
# time-series (the E13.16 public-%→line-movement / reverse-line-movement precursor). Two cron
# expressions cover ~10:00 AM–01:59 AM ET (14:00–05:59 UTC) — pre-game through the late-slate first
# pitches — since cron can't wrap midnight in one expr. Boots STOPPED (repo convention: schedules do
# NOT auto-fire until toggled in the Dagster UI), so merging this is a no-op. Every op resolves the
# baseball-day via current_game_date_iso() (LA), so the captured date is correct off UTC cron (INC-22).
#
# OPERATOR (enabling the hourly capture):
#   1. set W11_RAW_WRITE_MODE=s3 (or both) on the Dagster box so the S3 raw mirror + the dedicated
#      public_betting_intraday_series are actually written (default 'snowflake' → SF-only, series skipped),
#   2. START intraday_public_betting_daytime + _overnight in the Dagster UI.
intraday_public_betting_daytime = ScheduleDefinition(
    job=intraday_public_betting_job,
    cron_schedule="0 14-23 * * *",
    name="intraday_public_betting_daytime",
)

intraday_public_betting_overnight = ScheduleDefinition(
    job=intraday_public_betting_job,
    cron_schedule="0 0-5 * * *",
    name="intraday_public_betting_overnight",
)

all_intraday_schedules = [
    odds_clv_rebuild_schedule,
    intraday_schedule_capture_daytime,
    intraday_schedule_capture_overnight,
    intraday_public_betting_daytime,
    intraday_public_betting_overnight,
    lineup_monitor_schedule_daytime,
    lineup_monitor_schedule_overnight,
]
