"""Game-day-gated schedules for the sports (NCAAF / NFL) dbt builds — NCAAF-P1.1.

⛔ BOTH SHIP **STOPPED** (`DefaultScheduleStatus.STOPPED`) — operator-gated, by request.
There are no live NCAAF or NFL games right now (the 2026 seasons open in Aug/Sep 2026), so
neither should fire yet. The wiring exists so that turning them on before kickoff is a one-click
Dagit action rather than a code change during the season.

⚠️ THIS IS A DELIBERATE EXCEPTION TO THE E11.23 `default_status=RUNNING` RULE, and the exception
is the SAME one that rule already carves out: serving-critical sensors self-start, while
operator-gated schedules stay STOPPED on purpose. The cost of that choice is real — a STOPPED
schedule silently never fires, which is the "silently never runs" outage class — so the intended
state MUST be recorded in `BOX_OPERATIONS.md §10` and flipped deliberately before the season.
⏰ TO ENABLE (operator, before the 2026 openers): Dagit → Automation → toggle the schedule ON.

⭐ WHY GATED AND NOT JUST DAILY: football has no game most days. NCAAF plays mainly Saturdays
(plus scattered Thu/Fri/Tue/Wed), NFL mainly Sun/Mon/Thu. The cron fires daily inside the season
months and `sports_game_day_gate` decides whether the run is warranted, so the box does ~2–3
rebuilds a week instead of 7. The gate FAILS OPEN — see its module docstring; a missed rebuild
leaves marts silently stale, a redundant one costs ~2 min of free DuckDB compute.

Cron is 11:00 America/Los_Angeles: late enough that the prior day's games are final and CFBD /
nflverse have published, early enough that the marts are fresh for any daytime work.
"""

from dagster import DefaultScheduleStatus, RunRequest, ScheduleEvaluationContext, SkipReason, schedule

from betting_ml.monitoring.sports_game_day_gate import evaluate_gate
from pipeline.jobs.sports_dbt_job import (
    sports_ncaaf_dbt_build_job,
    sports_nfl_dbt_build_job,
)

# The local DuckDB each job materializes into — the same defaults the ops use. The gate reads
# these files (never S3) to answer "was a game played yesterday".
NCAAF_DUCKDB = "/tmp/sports_ncaaf.duckdb"
NFL_DUCKDB = "/tmp/sports_nfl.duckdb"

# NCAAF: Aug–Dec plus January (CFP / bowls run into mid-January).
NCAAF_CRON = "0 11 * 8-12,1 *"
# NFL: Sep–Dec plus January and February (playoffs; the Super Bowl is early Feb).
NFL_CRON = "0 11 * 9-12,1-2 *"


@schedule(
    job=sports_ncaaf_dbt_build_job,
    cron_schedule=NCAAF_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_ncaaf_dbt_schedule(context: ScheduleEvaluationContext):
    """Rebuild the NCAAF marts the morning after an NCAAF game day."""
    decision = evaluate_gate(
        duckdb_path=NCAAF_DUCKDB,
        # dim_ncaaf_game carries a real DATE column and every FBS game in the universe.
        relation="main_ncaaf_marts.dim_ncaaf_game",
        date_column="game_date",
    )
    context.log.info(f"[ncaaf game-day gate] {decision.reason}")
    if not decision.should_run:
        return SkipReason(decision.reason)
    return RunRequest(run_key=None, tags={"sport": "ncaaf", "gate": "game_day"})


@schedule(
    job=sports_nfl_dbt_build_job,
    cron_schedule=NFL_CRON,
    execution_timezone="America/Los_Angeles",
    default_status=DefaultScheduleStatus.STOPPED,  # ⛔ operator-gated — see module docstring
)
def sports_nfl_dbt_schedule(context: ScheduleEvaluationContext):
    """Rebuild the NFL marts the morning after an NFL game day."""
    decision = evaluate_gate(
        duckdb_path=NFL_DUCKDB,
        relation="main_nfl_staging.stg_nfl_schedules",
        # ⚠️ VARCHAR ISO date in the nflverse parquet (INC-23) — the gate casts ::date.
        date_column="game_date",
    )
    context.log.info(f"[nfl game-day gate] {decision.reason}")
    if not decision.should_run:
        return SkipReason(decision.reason)
    return RunRequest(run_key=None, tags={"sport": "nfl", "gate": "game_day"})
