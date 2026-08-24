"""NCAAF-P3.1 — the in-season schedule that keeps the NCAAF serving store fresh.

⏰ WINDOW + TIMING: **daily 06:00 America/Los_Angeles, August-January.**
  * DAILY rather than weekly, even though the underlying predictions are snapshotted weekly. Two
    things change between snapshot fires and both are user-visible: the manifest's
    `current_game_day` (which slate the app opens on) rolls every day, and a market line can land
    for a kickoff that has since passed its capture instant. A re-serve is a lake read plus a few
    dozen small key writes — no credits, no warehouse — so a daily refresh is the cheap way to keep
    "today" honest.
  * 06:00 PT sits after the overnight and comfortably before any kickoff (the earliest NCAAF
    windows are ~09:00 PT), so the day's slate is on the store before anyone opens the page.
  * AUGUST-JANUARY matches the season, bowls and the CFP included. ⚠️ A month-scoped cron has a
    BOUNDARY HOLE by construction (E9.48 (c) / INC-37) — here the hole is benign because the store
    is idempotent and re-derived from the lake each fire, and the season is over well before
    February. It is stated rather than assumed.

🔗 ORDERING (INC-25): the serving store is a CONSUMER of the NCAAF-PS snapshot tables, so a
re-serve that ran BEFORE the week's snapshot would publish last week's vintage. That is why the
authoritative write is chained INSIDE `sports_ncaaf_prediction_snapshot_job` (the same run that
produces the snapshots), and this daily schedule is the top-up: it can only ever re-publish the
newest vintage the lake holds, never an older one.

⛔ SHIPS `default_status=STOPPED` — the operator-gated carve-out every NCAAF schedule takes (the
E11.23 exception). There is nothing to serve until the season opens and the operator's P1.2 re-fit
+ first snapshot have landed; the intended state lives in `BOX_OPERATIONS.md §10`.

💸 COST: zero. No CFBD key, no Odds-API credits, no warehouse — two Delta reads over S3 and a few
dozen DynamoDB/S3 puts.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_ncaaf_serving_write_job import sports_ncaaf_serving_write_job

# Daily 06:00 PT, August-December + January (the in-season serving window).
NCAAF_SERVING_WRITE_CRON = "0 6 * 8-12,1 *"


@schedule(
    job=sports_ncaaf_serving_write_job,
    cron_schedule=NCAAF_SERVING_WRITE_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_serving_write_schedule(context: ScheduleEvaluationContext):
    """Re-publish the NCAAF serving store from the newest lake vintage."""
    context.log.info(
        "[ncaaf serving write] refreshing the NCAAF serving store for the clock-derived "
        "current_season() — market-blind probabilities + intervals, best_alpha=0")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "serving_write"})
