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

⭐⭐ SHIPS `default_status=RUNNING` AND FIRES NOTHING UNTIL AN OPERATOR SETS ONE FLAG — and the two
halves of that are a deliberate reconciliation, not a hedge.

The deploy-held requirement is real: **the FIRST real in-season fit will move ranks materially.** It
replaces a pre-season prior (`strength_margin_sd ≈ 7.3`) with a posterior that has absorbed several
played weeks, so teams move a long way on the board the morning it lands. That is the product
working rather than a defect, and it is a thing an operator should WATCH happen once rather than
discover. So merged must not mean running.

The obvious way to express that is the `default_status=STOPPED` carve-out every other NCAAF
schedule takes — and it is the WRONG tool here, because this schedule also has to be
heartbeat-checked, and the two are incompatible in a way that is easy to miss:

  * `monitor_health.stopped_critical_instigators` flags an instigator only when Dagster holds a
    PERSISTED STOPPED row (someone toggled it off). A schedule at its STOPPED DEFAULT has no row,
    so the revert that matters most — a Dagster-volume reset or a box re-host wiping the operator's
    toggle — leaves it silently off and UNFLAGGED. That is the NF-CAP1 reading, recorded there as
    the reason `sports_nfl_pit_market_schedule` is deliberately NOT in the set: the entry would
    have read as coverage while detecting nothing.
  * and `test_monitor_health_wiring.py::test_critical_instigators_self_start` pins exactly that:
    every member of `CRITICAL_SCHEDULES` declares `default_status=RUNNING`. It is E11.23's
    "permanently on" acceptance criterion, and it is not a thing to weaken for one story.

⇒ the schedule SELF-STARTS (so a re-host cannot silently un-arm it, and the heartbeat entry is
non-vacuous in both directions), and the deploy-held boundary moves to a single declared env flag,
`NCAAF_STRENGTH_REFIT_ENABLED`. Unset or not "1", every tick returns a LOUD `SkipReason` naming the
action; nothing runs. "Merged never means running" holds literally.

⚠️ AND THE FLAG IS NOT THE `W7B_LAKEHOUSE_S3` CLASS (a documented state nobody ever set, unnoticed
for weeks), because the thing it gates is WATCHED FROM THE ARTIFACT SIDE: if the flag is never set —
or is set and later lapses — `ncaaf/derived/team_strength_week` stops advancing and the
`ncaaf_team_strength_week` freshness contract goes STALE within ~8 active days regardless of what
any surface signal says. That is INC-41's thesis doing exactly the job it exists for, and it is why
the flag is deliberately NOT in `env.required`: adding it there would FAIL the next deploy until
the operator added the key by hand, to enforce a default whose correct value at deploy time is OFF.

💸 COST: no CFBD key, no Odds-API credits, no warehouse. A dbt-duckdb rebuild over the S3 lake, a
multi-minute CPU-bound fit, two Delta writes and a few hundred small serving-store keys.
"""

from dagster import (
    DefaultScheduleStatus,
    RunRequest,
    ScheduleEvaluationContext,
    SkipReason,
    schedule,
)

from betting_ml.monitoring.ncaaf_strength_refit import (
    REFIT_ENABLED_FLAG,
    SEASON_MONTHS,
    refit_enabled,
)
from pipeline.jobs.sports_ncaaf_strength_refit_job import sports_ncaaf_strength_refit_job

#: Monday 07:30 PT, August → January. The month field is BUILT from `SEASON_MONTHS` rather than
#: typed, so the cron and the freshness contract's active window cannot drift apart — one logical
#: thing, one owner (INC-30 / INC-36 / INC-38). Rendered `8,9,10,11,12,1`, which cron accepts as a
#: plain list and which is the same set the sibling `8-12,1` schedules express as a range.
NCAAF_STRENGTH_REFIT_CRON = "30 7 * " + ",".join(str(m) for m in SEASON_MONTHS) + " 1"

#: The deploy-held boundary — see the module docstring for why it is a flag and not a STOPPED
#: default. ⭐ OWNED BY `betting_ml.monitoring.ncaaf_strength_refit`, not declared here: the fast
#: test gate must be able to exercise the predicate, and importing anything under `pipeline`
#: triggers the dbt-manifest read that is absent on a CI runner (E11.23). The schedule READS it, at
#: TICK time — never at import, because the schedule module is loaded once when the code server
#: boots and reading it then would freeze a value the operator can still change with a redeploy.


@schedule(
    job=sports_ncaaf_strength_refit_job,
    cron_schedule=NCAAF_STRENGTH_REFIT_CRON,
    execution_timezone="America/Los_Angeles",
    # ⭐ SELF-STARTS so a Dagster-volume reset cannot silently un-arm it and the heartbeat entry is
    # not vacuous; the deploy-held gate is REFIT_ENABLED_FLAG below. See the module docstring.
    default_status=DefaultScheduleStatus.RUNNING,
)
def sports_ncaaf_strength_refit_schedule(context: ScheduleEvaluationContext):
    """Weekly in-season P1.2 re-fit: fresh marts → the strength posterior → the serving store."""
    if not refit_enabled():
        return SkipReason(
            f"{REFIT_ENABLED_FLAG} is not '1' on the box, so the weekly P1.2 re-fit is ARMED BUT "
            f"NOT FIRING — the deliberate deploy-held state (NCAAF-P1.2W): the first real in-season "
            f"fit moves ranks materially and is a supervised operator step. TO ENABLE: set "
            f"{REFIT_ENABLED_FLAG}=1 in services/dagster/aws/.env on the box and redeploy, then "
            f"launch sports_ncaaf_strength_refit_job once by hand and watch it. ⚠️ While this skip "
            f"is firing the served ratings do NOT advance, and the ncaaf_team_strength_week "
            f"freshness contract will say so within ~8 active days — this skip is visible from the "
            f"artifact side, not silent.")
    context.log.info(
        "[ncaaf strength refit] firing the weekly P1.2 re-fit for the clock-derived "
        "current_season(). The job REFUSES to fit on stale raw games and FAILS on a cold-start "
        "reproduction — a green run here means the ratings actually moved. best_alpha=0: a "
        "strength rating is context, never a pick.")
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "cadence": "strength_refit"})
