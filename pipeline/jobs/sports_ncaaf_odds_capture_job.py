"""NCAAF-P0.6b — the box Dagster job for the recurring IN-SEASON closing-line catch-up.

Bridges P0.6's one-time 2020-2025 historical closing-line backfill into an ONGOING feed: a
weekly catch-up that lands each newly-kicked-off, not-yet-covered week's leakage-safe CLOSING
game lines into `odds_ncaaf_historical` for the clock-derived `current_season()`. One op —
`odds_recurring_capture.py` does its own read-merge-write against the Delta partition (see that
module's docstring for why a plain overwrite would be a landmine), so there is nothing else for
this job to chain; there is no dbt mart yet reading `odds_ncaaf_historical` (that's P1.4), so
unlike the P0.7 roll-forward job there is no mart-rebuild op here.

TIER: WARN (peripheral, non-serving — mirrors `ingest_player_props_op`, the other paid/gated
odds-adjacent ingest in the CLAUDE.md op→tier map). A failed/missed week is NOT an outage: the
merge-safe design means the NEXT scheduled fire just catches up whatever weeks piled up, with no
data loss and no duplicate rows (dedup on (event id, requested snapshot)). So a per-run failure
logs loud and returns cleanly rather than failing the job.

⚠️ DEPLOY PREREQUISITE (operator): the box container needs `ODDS_API_KEY` (the PAID **main**
key — `/historical` is not available on the starter tier) AND `CFBD_API_KEY` (kickoff times +
the per-week coverage check) in its env.

🆕 NCAAF-P0.6c — day-prior (T-1) line-movement capture: gated behind `NCAAF_ODDS_CAPTURE_T1`
(default unset = OFF), a SEPARATE opt-in from this job's own `default_status=STOPPED` schedule
gate (`sports_odds_capture_schedules.py`) — both must be turned on. Enabling it roughly DOUBLES
this op's paid Odds-API credit spend (a second `/historical` snapshot per kickoff, ~24h
pre-kickoff); confirm against the remaining balance first (`odds_recurring_capture.py --dry-run
--capture-t1`) before setting the flag on the box.
"""

import os

from dagster import Nothing, Out, in_process_executor, job, op


@op(out=Out(Nothing))
def ncaaf_odds_recurring_capture_op(context):
    """Weekly in-season closing-line catch-up (WARN tier — see module docstring); optionally
    also captures the P0.6c T-1 day-prior snapshot when `NCAAF_ODDS_CAPTURE_T1=1`."""
    from quant_sports_intel_models.football.ncaaf.ingest.odds_recurring_capture import (
        run_recurring_capture,
    )
    from quant_sports_intel_models.football.ncaaf.ingest.sources import current_season

    season = current_season()
    capture_t1 = os.environ.get("NCAAF_ODDS_CAPTURE_T1") == "1"
    context.log.info(
        "NCAAF odds recurring capture: season=%s (clock-derived) capture_t1=%s",
        season, capture_t1,
    )
    try:
        manifest = run_recurring_capture(season, capture_t1=capture_t1)
    except Exception as exc:  # noqa: BLE001 — ALERT-loud-but-continue (peripheral; merge-safe catch-up next fire)
        context.log.warning(
            "ALERT NCAAF odds recurring capture FAILED for season=%s: %s — will retry on the "
            "next scheduled fire (merge-safe design, no data lost).", season, exc,
        )
        return
    rows = manifest.get("rows_written") or 0
    if rows:
        context.log.info(
            "NCAAF odds recurring capture: captured %s new close kickoff(s)%s (%d rows) for "
            "season=%s. credits used=%s remaining=%s",
            manifest.get("new_kickoffs"),
            f", {manifest.get('new_kickoffs_t1')} new T-1 kickoff(s)" if capture_t1 else "",
            rows, season, manifest.get("credits_used"), manifest.get("credits_remaining"),
        )
    else:
        context.log.info(
            "NCAAF odds recurring capture: nothing newly kicked-off/uncovered for season=%s — "
            "no-op this run (0 credits).", season,
        )


@job(executor_def=in_process_executor)
def sports_ncaaf_odds_capture_job():
    """Weekly in-season closing-line catch-up → the odds_ncaaf_historical Delta partition."""
    ncaaf_odds_recurring_capture_op()
