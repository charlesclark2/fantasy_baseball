from dagster import in_process_executor, job
from dagster._core.storage.tags import MAX_RUNTIME_SECONDS_TAG

from betting_ml.monitoring.intraday_tick_budget import (  # E11.26 — cadence-derived tick budget
    MAX_RUNTIME_SECONDS as _TICK_MAX_RUNTIME,
)
from pipeline.ops.intraday_ops import (
    intraday_lineup_rebuild,
    intraday_public_betting_capture,
    intraday_schedule_capture,
    intraday_weather_capture,
    odds_clv_dbt_rebuild,
    odds_current_dbt_rebuild,
    write_book_odds_op,
)


# Story 12.3.7 / A2.18 — dbt rebuild for the ODDS API live path. The capture itself runs
# every 30 min on a Railway cron container (off the Dagster+ bill); Dagster only pays for
# the warehouse rebuild, decoupled from capture cadence. Split into two by freshness need:
#
#   odds_current_rebuild_job  — LIGHT (stg + mart_odds_outcomes). Fired by
#     odds_current_rebuild_sensor on a dynamic game-hours window (hourly from first-pitch
#     -3h to last first pitch + a near-close tick). ~12-14 game-day rebuilds, 0 on dark days.
#   odds_clv_rebuild_job      — FULL post-hoc CLV/line-movement marts. Run ONCE/day post-game
#     by odds_clv_rebuild_schedule (the closing line doesn't exist until first pitch).
@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_oddsapi_rebuild"})
def odds_current_rebuild_job():
    dbt_done = odds_current_dbt_rebuild()
    write_book_odds_op(start=dbt_done)


@job(executor_def=in_process_executor, tags={"concurrency_group": "odds_oddsapi_rebuild"})
def odds_clv_rebuild_job():
    odds_clv_dbt_rebuild()


@job(executor_def=in_process_executor)
def intraday_weather_job():
    intraday_weather_capture()


# E11.26 — THE TICK MUST NOT OUTLIVE ITS OWN CADENCE.
#
# On 2026-07-29 this job ran >1h and parked `deploy.sh`'s drain loop for its full DRAIN_TIMEOUT,
# which pushed the deploy past the CD poll budget and let a second deploy race it (INC-36). INC-36
# hardened the DEPLOY against that; the run itself was still unbounded in any useful sense.
#
# It was NOT an INC-32 missing timeout — every subprocess on this chain already had one. It was
# that each leg's timeout was the module default of 1800s, i.e. EXACTLY the tick's own 30-minute
# cadence, so three live legs were granted 90 minutes and the only ceiling above them was the
# global 4h run_monitoring cap sized for the Sunday full-refresh build. See
# betting_ml/monitoring/intraday_tick_budget for the arithmetic and the pinned invariants.
#
# Two tags, doing two different jobs — neither is a substitute for the other:
#   dagster/max_runtime  the authoritative wall-clock ceiling. run-monitoring terminates the run,
#                        whatever it is waiting on — a subprocess, a `requests` poll, the
#                        dbt-runner 409 `RetryRequested` backoff (40x30s = 20 min), or pure
#                        in-process work. It does not require me to have enumerated every wait,
#                        which is exactly why the per-leg timeouts alone were not enough.
#   concurrency_group    activates the `tag_concurrency_limits` rule already in
#                        services/dagster/dagster.yaml (limit 1 per unique value). Every other
#                        recurring job here carries one; this one never did, so a slow tick could
#                        STACK with its successor — and concurrent ticks write the same S3
#                        partitions and both run DuckDB with threads=2 on a 2-vCPU box, which is
#                        how a slow tick compounds into the CPU saturation that starves the
#                        Dagster daemon (INC-32). With the ceiling below the cadence this can
#                        never actually queue anything; it is the guard for the day someone
#                        raises the ceiling or shortens the cron.
@job(
    executor_def=in_process_executor,
    tags={
        "concurrency_group": "intraday_schedule",
        MAX_RUNTIME_SECONDS_TAG: str(_TICK_MAX_RUNTIME),
    },
)
def intraday_schedule_job():
    done = intraday_schedule_capture()
    intraday_lineup_rebuild(start=done)


# E11.1-W11-D addendum — hourly ActionNetwork public-betting capture (the E13.16 public-%→line-movement
# precursor). One op, its own job so it can be scheduled independently (hourly, pre-game window). Boots
# STOPPED per repo convention — a merge is a no-op until the operator toggles it on.
@job(executor_def=in_process_executor)
def intraday_public_betting_job():
    intraday_public_betting_capture()
