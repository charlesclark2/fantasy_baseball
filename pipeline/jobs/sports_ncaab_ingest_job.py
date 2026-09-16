"""NCAAB-P0 — the box Dagster job for the FREE NCAAB lake ingest.

Lands the hoopR feeds (schedule, team box, team crosswalk) as content-timestamped Delta season
partitions. Free in every sense: hoopR is CC BY 4.0 published parquet, the compute is DuckDB,
and nothing here touches a paid endpoint. **The Odds API captures are deliberately NOT in this
job** — they are a spend decision the operator makes on `docs/ncaab_p0_credit_arithmetic.md`,
and wiring them here would turn that decision into a default nobody chose.

⭐ DEFAULT_STATUS=RUNNING, deliberately, and the reason is the rule rather than the exception.
The NCAAF/NFL dbt schedules ship STOPPED because they are operator-gated on cost or on a season
that has not started. Neither applies to a free ingest, so E11.23's rule governs: a STOPPED
schedule silently never fires and is invisible to the revert heartbeat, which is the outage
class NF-CAP1 and NCAAF-P1.2W both paid for. It is also registered in
`monitor_health.CRITICAL_SCHEDULES`, so a manual STOP is visible rather than silent.

⭐ THE CRON RUNS ALL YEAR (`0 14 * * *`), and that is a decision, not laziness. Every
month-scoped cron in this repo's history has turned out to be a SEASONAL BOUNDARY HOLE
(E9.48(c) / INC-37 / NCAAF-RF1 / NF-FRESH2) — and NCAAB has an especially sharp one, because
hoopR publishes the NEXT season's schedule file in late summer (measured: the 2027 file existed
on 2026-08-19 with 1,629 games) while the season itself runs November to April. A `11-4` window
would therefore miss the entire schedule-publication period and the vertical would have no
upcoming season loaded until the night before it started. Running daily, all year, removes the
class outright: the ingest is idempotent (a value-identical `replaceWhere season = YYYY`
overwrite), a source the upstream has not published lands 0 rows and is SKIPPED rather than
overwriting a good partition, and the whole run costs seconds of free compute.

✅ RUNTIME GATE PASSED 2026-09-15. Both things CI structurally could not verify were verified
by real runs on the box:
  1. The instance role CAN write the `ncaab/` prefix of `credence-sports-lakehouse` — it did so
     on the first attempt (`Found credentials from IAM Role: credence-dagster-ec2-role` ->
     1,629 rows), so the E8.5 first-write-to-a-new-prefix risk did not materialise and no IAM
     grant was needed.
  2. The box's DuckDB reaches hoopR over HTTPS.
⭐ And the SCHEDULE itself was verified separately, which is the check that is easy to skip:
`2026-09-15 14:00 SUCCESS` was its first AUTONOMOUS fire. Every earlier run was invoked by hand,
which proves the JOB works and says exactly nothing about whether the SCHEDULE ticks — the
E11.23 "silently never fires" class is ruled out by evidence, not by `default_status` reading
correctly in source.

TIER: the ingest op RAISES on an escalation or an error, so the run fails and pages through the
existing `run_failure_alert_sensor`. That is the correct tier for a spine feed — but note the
op is careful about WHICH silences are escalations: a pre-season 404 on the box-score file is
the normal state of the world from July to November and is logged, not raised.
"""

import os

from dagster import DefaultScheduleStatus, Nothing, Out, ScheduleDefinition, in_process_executor, job, op

#: INC-32 — even a cheap op on a Dagster worker gets a finite budget. The measured full run
#: (3 feeds, one season) is ~8s; 600s is four orders of margin and still bounded.
NCAAB_INGEST_TIMEOUT_SECONDS = int(os.environ.get("NCAAB_INGEST_TIMEOUT_SECONDS", "600"))

#: Daily 14:00 UTC (07:00 PT) — comfortably after hoopR's own automated update commits, which
#: were measured landing around 06:00 UTC.
NCAAB_INGEST_CRON = "0 14 * * *"


@op(out=Out(Nothing))
def ncaab_ingest_op(context) -> None:
    """Land the free hoopR feeds for the current season."""
    from quant_sports_intel_models.basketball.ncaab.ingest.handler import (
        receipt_to_dict,
        run_ingest,
    )
    from quant_sports_intel_models.basketball.ncaab.ingest.sources import season_for

    season = season_for()
    context.log.info("NCAAB ingest: season=%s (hoopR labels a season by the year it ENDS)", season)

    receipt = run_ingest(seasons=[season])
    payload = receipt_to_dict(receipt)

    for r in receipt.results:
        # ⭐ Log every attempt, including the ones that wrote nothing. A run that skipped a feed
        # and a run that never reached it are different facts, and a log that only records
        # successes renders them identically (the execution-witness discipline).
        context.log.info(
            "  %-16s season=%s rows=%s wrote=%s %s",
            r.source, r.season, r.rows, r.wrote,
            r.error or r.skipped_reason or "",
        )

    context.log.info("NCAAB ingest receipt: %s", payload["errors"] or "no errors")

    if receipt.errors or receipt.escalations:
        # Loud. A spine feed that failed or landed empty in-season must fail the run so the
        # existing failure sensor pages, rather than leaving a green tick over a frozen lake.
        raise Exception(
            "NCAAB ingest failed or escalated — "
            f"errors={receipt.errors} escalations={receipt.escalations}"
        )


@job(
    executor_def=in_process_executor,
    name="sports_ncaab_ingest_job",
    # ⭐ THE CONSTANT ABOVE WAS DECLARED AND NEVER APPLIED (NCAAB-P0 close-out). It appeared
    # exactly once in the repo — at its own definition — so this op ran UNBOUNDED on a Dagster
    # worker, which is the INC-32 class: an un-timed-out wait on a daemon path wedges the worker
    # and, at worst, the sensor daemon behind it. A `dagster/max_runtime` RUN TAG is the right
    # instrument rather than a per-call timeout, because it bounds EVERY wait — the HTTPS read of
    # hoopR, the Delta commit, retry backoff, and plain in-process work — without anyone having
    # to enumerate them (E11.26's lesson, where per-leg timeouts alone were insufficient).
    tags={"dagster/max_runtime": NCAAB_INGEST_TIMEOUT_SECONDS,
          "concurrency_group": "sports_ncaab_ingest"},
)
def sports_ncaab_ingest_job():
    ncaab_ingest_op()


sports_ncaab_ingest_schedule = ScheduleDefinition(
    name="sports_ncaab_ingest_schedule",
    job=sports_ncaab_ingest_job,
    cron_schedule=NCAAB_INGEST_CRON,
    execution_timezone="UTC",
    # ⭐ RUNNING — see the module docstring. A free ingest has neither of the two reasons the
    # NCAAF/NFL schedules ship STOPPED, so E11.23's rule applies unmodified.
    default_status=DefaultScheduleStatus.RUNNING,
)
