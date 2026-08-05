"""NF-W0a — schedules for the NFL point-in-time forward capture.

⏰ WHY THE `default_status` CHOICES ARE SPLIT, and why the split is deliberate rather than
inconsistent. E11.23 established the repo's rule: serving-critical instigators ship
`default_status=RUNNING` (a schedule that boots STOPPED silently never runs — an outage class
this repo has hit repeatedly), while PAID / operator-gated captures ship STOPPED. These three
schedules sit on both sides of that line:

  • WEATHER + METADATA ship **RUNNING**. They are FREE (Open-Meteo needs no key; nflverse is
    public), and their failure mode is the worst one available here: a checkpoint not captured is
    gone forever — the archive returns observations, not the forecast that stood at the time. A
    STOPPED weather schedule would be discovered in January, when the season's Tuesday-build
    weather feature is already unrecoverable. Between "it quietly costs a few free API calls" and
    "it quietly costs the season", RUNNING is the only defensible default.

  • MARKET ships **STOPPED** — it spends PAID Odds-API credits, and the repo's standing rule is
    that a paid capture is an explicit operator decision (the same carve-out
    `sports_ncaaf_odds_capture_schedule` takes). ⚠️ BUT THE DEADLINE IS REAL: it must be turned
    ON before the **2026-09-09** opener, or every Tuesday/Friday market feature is permanently
    un-backtestable (only closing lines exist historically). This is recorded in the story
    handoff and belongs in `BOX_OPERATIONS.md §10` as an intended-state row.

MONTH GATE: all three crons are scoped to September–February (the NFL season, which crosses the
calendar boundary). Outside those months the job never fires, so a RUNNING schedule costs
nothing off-season — no season pin, no code change next year (the NCAAF-P0.6 landmine).
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_nfl_pit_capture_job import (
    sports_nfl_pit_market_job,
    sports_nfl_pit_metadata_job,
    sports_nfl_pit_weather_job,
)

#: HOURLY, Sep–Feb. Hourly is the minimum cadence the ladder needs: the tightest rung gap is
#: 3h→1h and the match window is ±0.75h, so a fire every hour lands every rung exactly once
#: (pinned by `test_nfl_pit_capture.py::test_an_hourly_cron_cannot_miss_a_rung`).
NFL_PIT_WEATHER_CRON = "5 * * 9-12,1-2 *"

#: Tue + Fri 09:00 PT, Sep–Feb — the two early-week builds the story names. Injuries + schema
#: ride the same cadence so a build's injury view and its schema snapshot are contemporaneous.
NFL_PIT_METADATA_CRON = "0 9 * 9-12,1-2 2,5"

#: Tue + Fri 09:15 PT, Sep–Feb — 15 minutes after metadata so a schema break is visible in the
#: log before the PAID call fires.
NFL_PIT_MARKET_CRON = "15 9 * 9-12,1-2 2,5"


@schedule(
    job=sports_nfl_pit_weather_job,
    cron_schedule=NFL_PIT_WEATHER_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.RUNNING,  # free + irreplaceable — see module docstring
)
def sports_nfl_pit_weather_schedule(context: ScheduleEvaluationContext):
    """Hourly ladder capture; a fire with no game at a rung is a cheap no-op."""
    context.log.info("[nfl pit] hourly weather-forecast ladder capture")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "pit_weather_capture"})


@schedule(
    job=sports_nfl_pit_metadata_job,
    cron_schedule=NFL_PIT_METADATA_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.RUNNING,  # free; the only as-of stamp we will ever have
)
def sports_nfl_pit_metadata_schedule(context: ScheduleEvaluationContext):
    """Tue/Fri injury capture (our own as-of stamp) + nflverse schema snapshot."""
    context.log.info("[nfl pit] Tue/Fri injury + schema snapshot capture")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "pit_metadata_capture"})


@schedule(
    job=sports_nfl_pit_market_job,
    cron_schedule=NFL_PIT_MARKET_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ PAID — operator-gated; TURN ON BEFORE 2026-09-09
)
def sports_nfl_pit_market_schedule(context: ScheduleEvaluationContext):
    """Tue/Fri point-in-time market board (PAID: ~30 credits/snapshot, props opt-in and far
    dearer). ⚠️ Must be enabled before the opener or no early-build market feature is ever
    backtestable."""
    context.log.info("[nfl pit] Tue/Fri point-in-time market snapshot")
    return RunRequest(run_key=None, tags={"sport": "nfl", "cadence": "pit_market_capture"})
