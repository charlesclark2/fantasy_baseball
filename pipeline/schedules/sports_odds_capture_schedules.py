"""NCAAF-P0.6b — the IN-SEASON weekly closing-line catch-up schedule.

A weekly IN-SEASON catch-up of the just-completed slate's leakage-safe CLOSING game lines, so
the CLV benchmark (P1.4's vs-market eval + Phase 2) keeps extending season-over-season instead of
freezing at the P0.6 2020-2025 backfill. Fires `sports_ncaaf_odds_capture_job`
(`odds_recurring_capture.run_recurring_capture`) on a clock-derived `current_season()` — the same
job re-runnable next season with no code change (never pin the season — the P0.6 landmine).

⏰ WINDOW: weekly Mondays, AUGUST-JANUARY — the in-season closing-line window. NCAAF games kick
off Thu/Fri/Sat with occasional weeknight games; a Monday-morning fire safely catches an entire
week's slate after every one of its games has already kicked off (the module's own
`weeks_needing_capture` additionally waits for a week to be FULLY kicked-off before touching it,
so an early/late fire is harmless either way). Complements the pre-season
`sports_ncaaf_roll_forward_schedule` (Feb-Aug) — together the two schedules cover the full
calendar with no gap (P0.7 pre-season -> P0.6b in-season -> repeat next year).

⛔ SHIPS `default_status=STOPPED` — the SAME operator-gated exception the roll-forward schedule
takes (E11.23 carve-out): this job calls the PAID Odds-API `/historical` endpoint (needs
`ODDS_API_KEY`, the main tier) + CFBD (`CFBD_API_KEY`), and there is nothing to capture until the
2026 season actually kicks off (8/29). The intended state is recorded in `BOX_OPERATIONS.md §10`;
turn this ON alongside `sports_ncaaf_roll_forward_schedule`, well before the opener.

Cron 08:00 America/Los_Angeles Monday, Aug-Dec + Jan (bowls/CFP still land in January): a
quiet-hours weekly catch-up; credit cost bounded to whichever week(s) newly crossed into
"kicked off, not yet covered" since the last fire (module docstring: ~1,800-2,100 credits/week).

🆕 NCAAF-P0.6c (day-prior T-1 line-movement capture) is a SEPARATE opt-in on top of this
schedule, `NCAAF_ODDS_CAPTURE_T1` (default unset = OFF, read by
`ncaaf_odds_recurring_capture_op`) — turning this schedule ON does NOT by itself enable T-1
capture. It roughly DOUBLES the per-run credit cost above, so confirm the remaining Odds-API
balance (`odds_recurring_capture.py --dry-run --capture-t1`) before setting the flag; the weekly
cadence still works for a ~24h-pre-kickoff snapshot because `/historical` snapshots a PAST
instant regardless of when the fetch runs (see that module's docstring).
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from pipeline.jobs.sports_ncaaf_odds_capture_job import sports_ncaaf_odds_capture_job
from pipeline.jobs.sports_ncaaf_odds_live_job import sports_ncaaf_odds_live_job

# Monday 08:00 PT, months August-December + January (the in-season closing-line window).
NCAAF_ODDS_CAPTURE_CRON = "0 8 * 8-12,1 1"


@schedule(
    job=sports_ncaaf_odds_capture_job,
    cron_schedule=NCAAF_ODDS_CAPTURE_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_odds_capture_schedule(context: ScheduleEvaluationContext):
    """Weekly in-season catch-up of the just-completed slate's closing lines."""
    context.log.info(
        "[ncaaf odds capture] firing weekly in-season closing-line catch-up for the "
        "clock-derived current_season()"
    )
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "odds_recurring_capture"})


# ── NCAAF-ODDS-LIVE — the ahead-of-kickoff board ─────────────────────────────────────────────
#
# Football is bet days ahead, and the weekly `/historical` catch-up above structurally cannot
# serve that (it only asks for a kickoff once K−buffer has passed). This fires the live bulk
# `/odds` feed so a market line stands beside the model DAYS before kickoff.
#
# ⏱️ ONE HOURLY CRON, AND THE OP DECIDES. The operator-chosen cadence is tiered — hourly inside
# 24h of the next kickoff, 6-hourly otherwise — and that decision lives in
# `odds_live_capture.should_capture`, a pure function of the clock and the schedule, NOT in a
# second cron. Two crons for one logical job is this repo's most-repeated operational defect
# (INC-30's double-installed crontab, INC-36's raced deploy, INC-38's per-caller flag).
# A non-capturing tick spends ZERO credits and logs why.
#
# ⛔ The schedule eval itself does NO IO: the tier decision needs the season's kickoff times, and
# a CFBD call inside a schedule evaluation would put network in the Dagster DAEMON — the INC-32
# wedge class. The op does the read, in its own process, with the client's own timeout.
#
# ⛔ SHIPS `default_status=STOPPED`, the same operator-gated carve-out (E11.23) the paid
# `/historical` capture takes: this spends real Odds-API credits on every capturing tick. Turning
# it on is a deliberate act; the intended state belongs in `BOX_OPERATIONS.md §10`.
NCAAF_ODDS_LIVE_CRON = "0 * * 8-12,1 *"   # hourly, in-season (Aug-Dec + Jan bowls/CFP)


@schedule(
    job=sports_ncaaf_odds_live_job,
    cron_schedule=NCAAF_ODDS_LIVE_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — paid feed
)
def sports_ncaaf_odds_live_schedule(context: ScheduleEvaluationContext):
    """Hourly in-season tick; the op applies the 6h-baseline / hourly-near-kickoff tier."""
    context.log.info(
        "[ncaaf odds live] hourly tick — the op decides whether this one captures "
        "(hourly within 24h of the next kickoff, otherwise a 6-hourly baseline tick)"
    )
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "odds_live_capture"})
