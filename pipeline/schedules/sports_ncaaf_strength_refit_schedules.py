"""NCAAF-P1.2W — the WEEKLY in-season P1.2 strength re-fit schedule.

Fires `sports_ncaaf_strength_refit_job` (preconditions → marts rebuild → the P1.2 fit → VERIFY →
serving publish) once a week in season, so the strength rating, band and both ranks every NCAAF
surface prints actually move when games are played. Until this existed, nothing scheduled touched
`ncaaf/derived/team_strength_week` at all: P1.2 was built as a once-per-season refit and the
re-fit was an operator laptop step, which is why the served ratings sat at the pre-season prior
(`as_of_week = 1`, commit 2026-08-18) three played weeks into the 2026 season.

⏰ WINDOW + TIMING: **Monday 07:30 America/Los_Angeles, August → January.**

  * MONDAY, because an NCAAF week runs Thursday–Saturday: Monday morning is the first moment the
    weekend's results are all in and still three days ahead of the next Thursday kickoff — and it
    is the cadence NCAAF-P3.3 asked the product for.
  * **07:30, ninety minutes after `sports_ncaaf_roll_forward_schedule`'s 06:00 raw ingest.** ⛔ That
    offset is a COURTESY AND NOT THE ORDERING GUARANTEE. The guarantee is inside the job:
    `ncaaf_strength_precondition_op` reads `ncaaf/raw/games`' own Delta commit and REFUSES to fit
    when it has not landed this cycle. INC-25 was learned the hard way — an ordering that lives
    only in two crons is one slow ingest away from a consumer reading last cycle's inputs — and
    here the failure would be worse than usual, because a re-fit over stale raw succeeds, writes,
    and stamps the served "ratings as of" line with today's date.
  * The 90 minutes also keep the two jobs off the box's two vCPUs at once. The roll-forward's own
    mart rebuild takes ~90s; this job's takes about the same before the multi-minute fit starts.
  * **AUGUST → JANUARY** matches the season, bowls and the CFP — the same `8-12,1` window every
    other in-season NCAAF cron carries. ⚠️ A month-scoped cron is a SEASONAL BOUNDARY HOLE by
    construction (E9.48(c) / INC-37 / NCAAF-RF1, which had to widen exactly this kind of window
    after it would have frozen every roll-forward feed on 09-01). It is stated rather than assumed
    here, and the off-season half is not silence: `betting_ml/monitoring/sports_delta_freshness`'s
    `ncaaf_team_strength_week` contract declares the SAME months as its active window, so a
    January-final rating is legitimately fresh all spring and starts ageing again on August 1 —
    **idle by declaration, not by a silently suppressed check.** The two must move together; the
    schedule reads the month list from that contract's owner rather than re-typing it.

⛔ SHIPS `default_status=STOPPED` — the operator-gated carve-out every NCAAF schedule takes (the
E11.23 exception for a schedule that needs a prereq or a supervised first run), and here the second
reason is the load-bearing one: **the FIRST real in-season fit will move ranks materially.** It
replaces a pre-season prior (`strength_margin_sd ≈ 7.3`) with a posterior that has absorbed several
played weeks, so teams will move a long way on the board the morning it lands. That is the product
working rather than a defect, and it is a thing an operator should watch happen once rather than
discover. The intended state belongs in `BOX_OPERATIONS.md §10`.

⚠️ THE HEARTBEAT ENTRY IS NOT COMPLETE COVERAGE, AND SAYING SO IS THE POINT (the NF-CAP1 reading of
`stopped_critical_instigators`). This schedule is in `monitor_health.CRITICAL_SCHEDULES`, which
flags an instigator only when Dagster holds a PERSISTED STOPPED row — i.e. it catches someone
TOGGLING IT OFF, which is real coverage and the commonest way a weekly job dies. It cannot catch a
Dagster-volume reset or a box re-host, which wipes the row and drops the schedule back to its
STOPPED default with no row to flag. The detector for THAT is the artifact contract above, which
goes STALE within ~8 active days of a missed Monday regardless of what any surface signal says
(INC-41's whole thesis). Listing it here without that second half would have read as coverage while
detecting only one of the two ways this can stop.

💸 COST: no CFBD key, no Odds-API credits, no warehouse. A dbt-duckdb rebuild over the S3 lake, a
multi-minute CPU-bound fit, two Delta writes and a few hundred small serving-store keys.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, schedule

from betting_ml.monitoring.ncaaf_strength_refit import SEASON_MONTHS
from pipeline.jobs.sports_ncaaf_strength_refit_job import sports_ncaaf_strength_refit_job

#: Monday 07:30 PT, August → January. The month field is BUILT from `SEASON_MONTHS` rather than
#: typed, so the cron and the freshness contract's active window cannot drift apart — one logical
#: thing, one owner (INC-30 / INC-36 / INC-38). Rendered `8,9,10,11,12,1`, which cron accepts as a
#: plain list and which is the same set the sibling `8-12,1` schedules express as a range.
NCAAF_STRENGTH_REFIT_CRON = "30 7 * " + ",".join(str(m) for m in SEASON_MONTHS) + " 1"


@schedule(
    job=sports_ncaaf_strength_refit_job,
    cron_schedule=NCAAF_STRENGTH_REFIT_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_strength_refit_schedule(context: ScheduleEvaluationContext):
    """Weekly in-season P1.2 re-fit: fresh marts → the strength posterior → the serving store."""
    context.log.info(
        "[ncaaf strength refit] firing the weekly P1.2 re-fit for the clock-derived "
        "current_season(). The job REFUSES to fit on stale raw games and FAILS on a cold-start "
        "reproduction — a green run here means the ratings actually moved. best_alpha=0: a "
        "strength rating is context, never a pick.")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "strength_refit"})
