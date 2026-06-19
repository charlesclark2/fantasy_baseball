from dagster import ScheduleDefinition

from pipeline.jobs.intraday_jobs import (
    intraday_schedule_job,
    intraday_weather_job,
    odds_clv_rebuild_job,
    odds_snapshot_job,
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

# ── Odds Snapshot (Parlay) — DECOMMISSIONED 2026-06-16 (Story 12.3.7 / A2.18) ──
# These 17 Parlay `odds_snapshot_job` schedules were the live odds source AND the #1
# Dagster+ run-minute driver (~1,044 min/mo, ~42%). Retired in favour of The Odds API
# (Railway cron capture → mlb_odds_raw → odds_current_rebuild_sensor / odds_clv_rebuild_daily),
# which validated healthier coverage on 2026-06-16 (28 games / 37 books incl Bovada + Pinnacle,
# vs Parlay 18 / 15). Removing them from `all_intraday_schedules` (below) stops the auto-fires
# and the Dagster+ cost BEFORE billing starts 6/18.
#
# The defs are RETAINED (not deleted) so Parlay stays a dormant manual failover: `odds_snapshot_job`
# is still registered and launchable from the Dagster UI, and re-adding `odds_snapshot_schedules`
# to the tuple below revives the schedule in one line. Historical Parlay data is preserved; the
# stg_parlayapi_* → mart_odds_outcomes union rows simply stop updating (dedup prefers odds_api).
#
# Mirrors the 17 cron entries in odds_snapshot.yml (all times UTC). Dagster does not support
# multiple cron strings per ScheduleDefinition, so each is its own ScheduleDefinition.

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

# NOTE: `odds_snapshot_schedules` (Parlay) is intentionally OMITTED — decommissioned
# 2026-06-16 (see header). Re-add it to this tuple to revive the Parlay capture cadence.
#
# E11.4 (2026-06-19) — intraday_weather_* and intraday_schedule_capture_* are OMITTED:
# their jobs are now run by Railway cron services (services/schedule_capture/ and
# services/weather_capture/) off Dagster's metered compute. The ScheduleDefinition
# objects above are kept for manual fallback via the Dagster UI.
all_intraday_schedules = [
    odds_clv_rebuild_schedule,
]
