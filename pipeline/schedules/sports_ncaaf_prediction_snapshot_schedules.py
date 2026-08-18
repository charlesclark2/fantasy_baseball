"""NCAAF-PS — the weekly PRE-KICKOFF prediction-snapshot schedule.

Fires `sports_ncaaf_prediction_snapshot_job` once a week, IN SEASON, comfortably ahead of the
week's first kickoff: the job writes what the served P1.4 model says about each upcoming
FBS-vs-FBS game BEFORE it starts, which is the only way a forward track record can exist (a
backtest can always be re-derived, so it proves nothing about what we would have said in advance).

⏰ WINDOW + TIMING: **Tuesday 09:00 America/Los_Angeles, August-January.**
  * TUESDAY, not Monday-of-the-slate-just-played and not Thursday. NCAAF weeks run Thu-Sat with
    occasional Tue/Wed weeknight games, so a Tuesday-morning fire sits AHEAD of essentially every
    kickoff in its 7-day window while still being late enough to see the previous weekend's
    results (which is what moves the strength mart, once the in-season dbt cadence is running).
  * The 7-day horizon and the weekly cadence are the same number ON PURPOSE: every kickoff falls
    inside exactly one fire's window. A game still ahead on the following fire is snapshotted
    AGAIN under a fresh `snapshot_ts` — that is an additional vintage, not a duplicate, and the
    append-only (game_id, snapshot_ts) key keeps both.
  * AUGUST-JANUARY matches the season, bowls and the CFP included. ⚠️ A month-scoped cron has a
    BOUNDARY HOLE by construction (E9.48 (c) / INC-37): the 7-day horizon is what covers it here —
    the last January fire still reaches games in the first days of February, and the season is over
    well before then. It is stated rather than assumed because a month-range cron is exactly the
    kind of thing that silently stops covering a season (NF-FRESH1's `3-8` NFL window).

⛔ SHIPS `default_status=STOPPED` — the same operator-gated exception the NCAAF roll-forward and
odds-capture schedules take (the E11.23 carve-out). Two reasons, and the second is the important
one: there is nothing to snapshot until the 2026 season opens (8/29), AND the first real snapshot
should run only AFTER the operator's close-to-kickoff P1.2 RE-FIT (✅ done 2026-08-18). Firing
before that re-fit would have frozen the pre-season COLD START — a board built with the fall-camp
covariates missing, which COMPRESSES every margin toward the mean — into a track record that, by
design, can never be rewritten. The intended state lives in `BOX_OPERATIONS.md §10`.

💸 COST: zero. No CFBD key, no Odds-API key, no credits, no warehouse — the job reads two Delta
tables over S3 and the two committed served JSON artifacts, and writes two small Delta partitions.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_ncaaf_prediction_snapshot_job import sports_ncaaf_prediction_snapshot_job

# Tuesday 09:00 PT, months August-December + January (the in-season pre-kickoff window).
NCAAF_PREDICTION_SNAPSHOT_CRON = "0 9 * 8-12,1 2"


@schedule(
    job=sports_ncaaf_prediction_snapshot_job,
    cron_schedule=NCAAF_PREDICTION_SNAPSHOT_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_prediction_snapshot_schedule(context: ScheduleEvaluationContext):
    """Weekly pre-kickoff per-game predictions + the P1.5 futures board, snapshotted to the lake."""
    context.log.info(
        "[ncaaf prediction snapshot] firing the weekly PRE-KICKOFF snapshot for the clock-derived "
        "current_season() — market-blind probabilities + intervals, best_alpha=0"
    )
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "prediction_snapshot"})
