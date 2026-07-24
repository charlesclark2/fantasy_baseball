"""NCAAF-P0.7 — the PRE-SEASON season-roll-forward schedule.

A weekly PRE-SEASON refresh of the upcoming season's schedule + covariates so the P1.5 futures
board + the live P1.4 board can RUN before kickoff. Fires the `sports_ncaaf_roll_forward_job`
(ingest → mart rebuild) on a clock-derived `current_season()` — the exact same schedule lands 2027
next August with no code change (the annual cadence; NEVER pin the season — the P0.6 landmine).

⏰ WINDOW: weekly Mondays, FEBRUARY–AUGUST. That is the pre-season churn window — CFBD publishes /
moves games and fills covariates (returning production, talent, coaches, roster) on a rolling basis
from late winter through fall camp (verified 2026-07-24: half the covariates were still unpublished
in July). Once the season opens (Sep+), the game-day `sports_ncaaf_dbt_schedule` takes over the
mart rebuilds off real game data, so the roll-forward pull stops for the season and resumes the next
February for the following season.

⛔ SHIPS `default_status=STOPPED` — the SAME operator-gated exception the sports dbt schedules take
(E11.23 carves out operator-gated schedules that need a prereq / can spend an external budget): this
job calls CFBD (needs `CFBD_API_KEY` on the box) and there is nothing to roll forward until an
operator has verified the upcoming season's CFBD availability + provisioned the key. The cost of
STOPPED is the "silently never runs" class, so the intended state is recorded in
`BOX_OPERATIONS.md §10` and the P0.7 handoff makes ENABLING THIS the launch-critical action —
turn it ON in Dagit well before the Aug-29 opener.

Cron 06:00 America/Los_Angeles Monday, Feb–Aug: a quiet-hours weekly pull; ~8 cheap CFBD calls.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_ncaaf_rollforward_job import sports_ncaaf_roll_forward_job

# Weekly Monday 06:00 PT, months February–August (the pre-season roll-forward window).
NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"


@schedule(
    job=sports_ncaaf_roll_forward_job,
    cron_schedule=NCAAF_ROLL_FORWARD_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_roll_forward_schedule(context: ScheduleEvaluationContext):
    """Weekly pre-season refresh of the upcoming season's schedule + covariates."""
    context.log.info(
        "[ncaaf roll-forward] firing pre-season schedule + covariate refresh for the "
        "clock-derived current_season()")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "roll_forward"})
