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

⚠️⚠️ RUNTIME GATE — THIS HAS NOT RUN ON THE BOX. CI mocks all IO, so neither this op nor its S3
write is exercised by any gate that runs before merge. Two things must be verified by an actual
run (they are in the P0 handoff):
  1. The instance role can WRITE the `ncaab/` prefix of `credence-sports-lakehouse`. Prior
     grants may cover only `ncaaf/`/`nfl/`, and a first-write-to-a-new-prefix needing a new IAM
     grant is this repo's E8.5 class — invisible until a live run.
  2. The box's DuckDB can read hoopR over HTTPS (httpfs), which the ingest needs for every feed.

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


@job(executor_def=in_process_executor, name="sports_ncaab_ingest_job")
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
