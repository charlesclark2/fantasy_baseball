"""NCAAF-ODDS-LIVE — the box Dagster job for the AHEAD-OF-KICKOFF live odds board.

Football is bet days ahead, and the P0.6b `/historical` catch-up structurally cannot serve that:
it only ever asks for a kickoff once `K − buffer` has already passed. This job fires the live bulk
`/odds` feed on a tiered in-season cadence so a market line stands beside the model DAYS before
kickoff, and so the lake accumulates the line MOVEMENT between those observations.

Rows land in `odds_ncaaf_live` — ⛔ NEVER `odds_ncaaf_historical`, which is the leakage-safe CLV
benchmark P1.4's model selection and VAL1's null were both decided on. See
`odds_live_capture.py`'s docstring for that separation, the read-merge-write that keeps an hourly
cadence from `replaceWhere`-deleting the season, and the two leakage defences.

⏱️ THE TIER LIVES IN THE OP, NOT IN A SECOND CRON. One hourly schedule fires; the op asks
`odds_live_capture.should_capture` whether THIS tick captures (hourly inside 24h of the next
kickoff, otherwise only a 6-hourly tick) and loud-skips at ZERO credits otherwise. Two crons for
one logical job is this repo's most-repeated operational defect (INC-30's double-installed
crontab, INC-36's raced deploy, INC-38's per-caller flag), so there is exactly one owner.

TIER: WARN — peripheral and non-serving-critical. A market line is transparency beside the model
(`best_alpha = 0`), never an input to it, so a failed capture must never fail a job. The next tick
catches up on its own: the merge is idempotent per `(event id, snapshot instant)` and a missed
observation costs a gap in the movement series, not a data loss.

⚠️ DEPLOY PREREQUISITES (operator): `ODDS_API_KEY` (the paid main key) + `CFBD_API_KEY` (kickoff
times, for the tier decision) in the box container's env — the SAME two the P0.6b capture already
needs, so a box that runs that job needs nothing new.

💳 COST, measured 2026-08-27 against the live API: 3 credits per capture (1 x 3 markets x 1
region) returning the WHOLE upcoming board — 109 events, 1.6-92.6 days out, Bovada on 51. The
tiered cadence is roughly 4,900 credits/season against a ~4.49M balance (0.11%). That is a TENTH
of what the existing per-kickoff `/historical` loop costs for far less coverage.
"""

from dagster import Nothing, Out, in_process_executor, job, op


@op(out=Out(Nothing))
def ncaaf_odds_live_capture_op(context):
    """One tiered live-board tick (WARN tier — see the module docstring)."""
    from quant_sports_intel_models.football.ncaaf.ingest.odds_live_capture import run_live_capture

    try:
        manifest = run_live_capture()
    except Exception as exc:  # noqa: BLE001 — WARN tier: a market line never costs a job
        context.log.warning(
            "ALERT NCAAF live odds capture FAILED: %s — the next tick retries (the merge is "
            "idempotent per (event, snapshot instant), so nothing is lost but this observation).",
            exc)
        return

    # ⭐ BOTH branches log. A skipped tick that said nothing would be indistinguishable from a
    # schedule that quietly stopped firing — the NF-FRESH1 "19 green runs over a frozen artifact"
    # class, which is exactly the shape a cheap, always-succeeding op invites.
    if not manifest.get("captured"):
        context.log.info("NCAAF live odds capture: no capture this tick — %s",
                         manifest.get("reason"))
        return
    dropped = manifest.get("dropped_not_pre_kickoff") or 0
    context.log.info(
        "NCAAF live odds capture: %s — %s event(s) stored across season(s) %s (%s row(s) in the "
        "partition after merge). credits used=%s remaining=%s",
        manifest.get("reason"), manifest.get("events"), sorted(manifest.get("seasons") or {}),
        manifest.get("rows_written"), manifest.get("credits_used"),
        manifest.get("credits_remaining"))
    if dropped:
        context.log.warning(
            "ALERT NCAAF live odds capture dropped %d record(s) that were NOT strictly "
            "pre-kickoff at the snapshot instant (an in-play price must never enter the store a "
            "pre-game line is served from).", dropped)
    if not manifest.get("events"):
        context.log.warning(
            "ALERT NCAAF live odds capture fired and stored ZERO events — the board should not be "
            "empty during the in-season window. Check the Odds-API key/balance and the "
            "commenceTimeFrom bound before trusting the next quiet tick.")


@job(executor_def=in_process_executor)
def sports_ncaaf_odds_live_job():
    """One tiered tick of the ahead-of-kickoff live odds board → `odds_ncaaf_live`."""
    ncaaf_odds_live_capture_op()
