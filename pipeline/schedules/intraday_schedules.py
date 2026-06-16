from dagster import ScheduleDefinition

from pipeline.jobs.intraday_jobs import (
    intraday_schedule_job,
    intraday_weather_job,
    odds_clv_rebuild_job,
    odds_snapshot_job,
)

# ── Odds Snapshot ─────────────────────────────────────────────────────────────
# Mirrors the 17 cron entries in odds_snapshot.yml (all times UTC):
#
# CLV architecture timeline (EDT = UTC-4):
#   Step 1 — Opening baseline: captured by daily_ingestion_job at 12:00 UTC
#   Step 2 — Hourly line-movement path (14:00–23:00 UTC = 10:00–19:00 EDT)
#   Step 3 — Near-close snapshots covering each start-time band
#
# Dagster does not support multiple cron strings per ScheduleDefinition, so
# each cron entry is its own ScheduleDefinition pointing at the same job.

_ODDS_SNAPSHOT_CRONS = [
    # ── Hourly morning / midday coverage (10:00–17:00 EDT) ─────────────────
    ("0 14 * * *",   "odds_snapshot_1000_edt"),   # 10:00 EDT
    ("0 15 * * *",   "odds_snapshot_1100_edt"),   # 11:00 EDT
    ("0 16 * * *",   "odds_snapshot_1200_edt"),   # 12:00 EDT
    ("0 17 * * *",   "odds_snapshot_1300_edt"),   # 13:00 EDT (~5 min before 1:05 PM starts)
    ("0 18 * * *",   "odds_snapshot_1400_edt"),   # 14:00 EDT
    ("30 18 * * *",  "odds_snapshot_1430_edt"),   # 14:30 EDT — T-1h pre-afternoon
    ("0 19 * * *",   "odds_snapshot_1500_edt"),   # 15:00 EDT
    ("0 20 * * *",   "odds_snapshot_1600_edt"),   # 16:00 EDT
    ("0 21 * * *",   "odds_snapshot_1700_edt"),   # 17:00 EDT
    # ── Pre-evening coverage (18:00–19:00 EDT) ──────────────────────────────
    ("0 22 * * *",   "odds_snapshot_1800_edt"),   # 18:00 EDT — pre-evening games
    ("0 23 * * *",   "odds_snapshot_1900_edt"),   # 19:00 EDT — ~5 min before 7:05 PM ET starts
    ("30 23 * * *",  "odds_snapshot_1930_edt"),   # 19:30 EDT — T-30min for 8:00 PM ET starts
    # ── Near-close snapshots ─────────────────────────────────────────────────
    ("55 23 * * *",  "odds_snapshot_1955_edt"),   # 19:55 EDT — closing line for 8:00 PM ET
    ("5 0 * * *",    "odds_snapshot_2005_edt"),   # 20:05 EDT — closing line for 8:10 PM ET
    ("30 1 * * *",   "odds_snapshot_2130_edt"),   # 21:30 EDT — west coast early (9:05 PM ET)
    ("0 2 * * *",    "odds_snapshot_2200_edt"),   # 22:00 EDT — west coast late (10:05 PM ET)
    ("0 3 * * *",    "odds_snapshot_2300_edt"),   # 23:00 EDT — safety net / extra innings
]

odds_snapshot_schedules = [
    ScheduleDefinition(job=odds_snapshot_job, cron_schedule=cron, name=name)
    for cron, name in _ODDS_SNAPSHOT_CRONS
]

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

all_intraday_schedules = (
    odds_snapshot_schedules
    + [
        odds_clv_rebuild_schedule,
        intraday_weather_schedule_daytime,
        intraday_weather_schedule_overnight,
        intraday_schedule_capture_daytime,
        intraday_schedule_capture_overnight,
    ]
)
