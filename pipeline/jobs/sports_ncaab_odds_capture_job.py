"""NCAAB-P0 — the PAID NCAAB market capture. Ships STOPPED; the operator enables it.

⛔ `default_status=STOPPED`, and this is the SAME deliberate E11.23 exception the NCAAF odds
schedules take: an operator-gated PAID capture. Enabling it starts spending Odds-API credits,
which is a decision to make on `docs/ncaab_p0_credit_arithmetic.md` — where the measured unit
prices, the priced cadence menu and a recommendation live. Wiring it now means enabling is a
one-click Dagit action rather than a code change during the season.

⏰ TO ENABLE (operator): Dagit → Automation → toggle `sports_ncaab_odds_capture_schedule` ON.
Safe to enable EARLY: measured 2026-09-14, an empty board bills **0 credits**, so every tick
before the season posts lines is free and the job simply reports an empty board.

💳 MEASURED cost per tick: **3 credits** for the whole game-line board (any size — one call
returns up to 105 events), plus **1** on the single daily futures tick. At the proposed
30-minute cadence across the 16h US window that is ≈ **14,938 credits/season, 0.31%** of the
balance measured at 4,812,933.

⭐ ONE CRON, and the op decides what this tick is. `should_capture_futures()` is a pure
function of the tick instant, so the daily futures capture needs no second schedule and no
stored state. Two crons for one logical job is the INC-30 / INC-36 / INC-38 class.

⚠️ THE CAPTURE DOES A READ-MERGE-WRITE, not a write. Odds accumulate all season and the lake's
ordinary path is a season-grained `replaceWhere` OVERWRITE, so a plain write would delete every
prior snapshot on the first fire. See `odds_capture` — including the shape bug a real run
caught, where the merge key went missing on read-back and collapsed a season into one row.

TIER: WARN-with-escalation. A missed tick loses that tick and the next one catches up (the
merge is idempotent), so a transient failure must not fail the job. But a capture that lands
ZERO events while the season is running is escalated rather than passing silently — "0 rows,
no error" is this repo's signature failure and a market capture is exactly where it hides.
"""

import os

from dagster import DefaultScheduleStatus, Nothing, Out, ScheduleDefinition, in_process_executor, job, op

#: Every 30 minutes across the 16h window that carries a US slate (12:00–04:00 UTC). No month
#: range: an out-of-season tick is measured FREE, so gating by month would buy nothing and
#: would reintroduce the seasonal-boundary-hole class for no benefit.
NCAAB_ODDS_CAPTURE_CRON = "0,30 12-23,0-3 * * *"

NCAAB_ODDS_TIMEOUT_SECONDS = int(os.environ.get("NCAAB_ODDS_TIMEOUT_SECONDS", "300"))


@op(out=Out(Nothing))
def ncaab_odds_capture_op(context) -> None:
    """One capture tick: the whole game-line board, plus futures once a day."""
    from quant_sports_intel_models.basketball.ncaab.ingest.odds_capture import run_capture

    receipt = run_capture()
    for r in receipt.results:
        # Log every leg including the ones that did nothing — a skipped futures tick and a
        # failed one must not read alike.
        context.log.info(
            "  %-18s attempted=%s events=%s merged_rows=%s remaining=%s %s",
            r.table, r.attempted, r.events, r.rows_total_after_merge,
            r.credits_remaining, r.error or r.skipped_reason or "",
        )

    if receipt.errors:
        # WARN tier: a transient capture failure must not fail the job — the merge is
        # idempotent and the next tick catches up. Loud, not fatal.
        context.log.warning("NCAAB odds capture had errors: %s", receipt.errors)
    for esc in receipt.escalations:
        context.log.warning(esc)


@job(executor_def=in_process_executor, name="sports_ncaab_odds_capture_job")
def sports_ncaab_odds_capture_job():
    ncaab_odds_capture_op()


sports_ncaab_odds_capture_schedule = ScheduleDefinition(
    name="sports_ncaab_odds_capture_schedule",
    job=sports_ncaab_odds_capture_job,
    cron_schedule=NCAAB_ODDS_CAPTURE_CRON,
    execution_timezone="UTC",
    # ⛔ STOPPED — operator-gated on SPEND. See the module docstring; this is the documented
    # E11.23 exception, not an oversight, and the intended state is recorded in
    # BOX_OPERATIONS.md §10 so it cannot quietly stay off by accident.
    default_status=DefaultScheduleStatus.STOPPED,
)
