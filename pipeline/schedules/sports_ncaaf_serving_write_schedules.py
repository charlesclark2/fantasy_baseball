"""NCAAF-P3.1 — the in-season schedule that keeps the NCAAF serving store fresh.

⏰ WINDOW + TIMING: **hourly, August-January, with the TIER DECIDED IN THE OP.**
  * ⭐ HOURLY since NCAAF-ODDS-LIVE followUp ⑦ (operator chose option (b), 2026-08-29). It was
    daily 06:00 PT, which was right until the ahead-of-kickoff live odds feed made the PRODUCER
    hourly inside 24h of kickoff. A daily re-serve behind an hourly capture means a line that moves
    on a Saturday morning reaches the reader only AFTER the games — the INC-25 consumer/producer
    ordering mismatch, on the REFRESH axis rather than the build axis.
  * The op asks `write_ncaaf_serving_store.should_reserve`: re-serve every hour inside the
    capture's dense window, otherwise take the daily baseline write, otherwise loud-skip. That
    window is SHARED with the capture by import (`odds_live_capture.in_dense_window`), not copied,
    so tuning one cadence moves both (E9.61).
  * ⭐ THE CHANGE IS MONOTONE: the 06:00 PT baseline is preserved exactly, so every write that
    happened before still happens and the dense tier only ADDS refreshes. The worst case of this
    cadence change is "no better than the old one" — which is what makes it safe to land in-season.
  * ⏱️ MINUTE :20, NOT :00. The live capture fires at :00 (`NCAAF_ODDS_LIVE_CRON`), and a consumer
    that ticks at the same instant as its producer races it — it would read the lake before the
    capture landed and publish the previous hour's line. A 20-minute offset is a WEAKER guarantee
    than a graph edge (a capture that ran long would still be missed), and deliberately so: the two
    are separate jobs with different tiers, the write is idempotent, and the next hour heals it.
  * ⛔ ONE SCHEDULE, ONE OWNER. A second "dense" schedule beside the daily one was the obvious
    build and was NOT done: two crons for one logical job is this repo's most-repeated operational
    defect (INC-30's double-installed crontab, INC-36's raced deploy, INC-38's per-caller flag).
  * AUGUST-JANUARY matches the season, bowls and the CFP included. ⚠️ A month-scoped cron has a
    BOUNDARY HOLE by construction (E9.48 (c) / INC-37) — here the hole is benign because the store
    is idempotent and re-derived from the lake each fire, and the season is over well before
    February. It is stated rather than assumed.

🔗 ORDERING (INC-25): the serving store is a CONSUMER of the NCAAF-PS snapshot tables, so a
re-serve that ran BEFORE the week's snapshot would publish last week's vintage. That is why the
authoritative write is chained INSIDE `sports_ncaaf_prediction_snapshot_job` (the same run that
produces the snapshots), and this schedule is the top-up: it can only ever re-publish the newest
vintage the lake holds, never an older one. ⛔ That chained op is deliberately NOT tier-gated — it
must run whenever the snapshot run does, whatever the clock says.

⛔ SHIPS `default_status=STOPPED` — the operator-gated carve-out every NCAAF schedule takes (the
E11.23 exception). There is nothing to serve until the season opens and the operator's P1.2 re-fit
+ first snapshot have landed; the intended state lives in `BOX_OPERATIONS.md §10`.

💸 COST: zero. No CFBD key, no Odds-API credits, no warehouse — two Delta reads over S3 and a few
dozen DynamoDB/S3 puts. The tier is nonetheless real: outside the dense window the capture is only
6-hourly, so an ungated hourly write would be a 24/7 evenly-spread poller against a 2-vCPU box for
five months, which is the E11.24 "poller shows up in ACTIVE-MINUTES" shape rather than a free lunch.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_ncaaf_serving_write_job import sports_ncaaf_serving_write_job

# Hourly at :20 PT, August-December + January. The OP applies the tier; :20 sits after the
# live odds capture's :00 so a re-serve reads a lake the capture has already written.
NCAAF_SERVING_WRITE_CRON = "20 * * 8-12,1 *"


@schedule(
    job=sports_ncaaf_serving_write_job,
    cron_schedule=NCAAF_SERVING_WRITE_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_serving_write_schedule(context: ScheduleEvaluationContext):
    """Hourly in-season tick; the op applies the dense/baseline re-serve tier."""
    context.log.info(
        "[ncaaf serving write] hourly tick — the op decides whether this one publishes "
        "(every hour within 24h of the next kickoff, otherwise the daily 06:00 PT baseline). "
        "Market-blind probabilities + intervals, best_alpha=0")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "serving_write"})
