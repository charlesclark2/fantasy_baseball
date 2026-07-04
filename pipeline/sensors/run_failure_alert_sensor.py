"""INC-16-P6 — Dagster OSS run-failure → email alert.

Replaces Dagster+ Cloud's built-in run-failure alerting (gone with the P4 cutover
to the self-hosted box). Fires on ANY job-run FAILURE and publishes to the shared
SNS topic (→ operator email) via pipeline.utils.alerting.send_alert.

Severity is set by the CLAUDE.md E11.7 op→tier map: serving-critical (HALT-tier)
jobs page LOUD ([CRITICAL]); everything else still emails ([ERROR]) — job-run
failures are rare enough that emailing all of them beats silently dropping a
WARN-tier break. (Sensor-TICK failures are NOT runs and are not caught here — the
freshness sensors call send_alert directly; see their modules.)

OPERATOR: as of E11.23 this sensor SELF-STARTS (default_status=RUNNING) so it can't
silently boot STOPPED after a Dagster-DB reset / re-host (INC-16 class) and miss the very
run-failures it exists to page on. Still confirm the SNS email subscription is active.
"""

from __future__ import annotations

from dagster import DefaultSensorStatus, RunFailureSensorContext, run_failure_sensor

from pipeline.utils.alerting import send_alert

# HALT-tier serving-critical jobs (CLAUDE.md E11.7 op→tier map). A failure here
# means today's picks / served prices / core pitch data are at risk → page LOUD.
_HALT_TIER_JOBS = {
    "daily_ingestion_job",      # predict_today, dbt run, write_serving_store, signal_freshness, ingest_statcast, W1 ops
    "odds_current_rebuild_job", # served-price freshness (displayed odds)
    "statcast_catchup_job",     # core pitch data; predictions depend
    "w1_parity_job",            # lakehouse parity gates the S3-served marts
}


@run_failure_sensor(
    name="run_failure_alert_sensor",
    description="Email on any job-run failure; LOUD for HALT-tier serving jobs (INC-16-P6).",
    default_status=DefaultSensorStatus.RUNNING,  # E11.23: self-start; a stopped alarm is silent
)
def run_failure_alert_sensor(context: RunFailureSensorContext) -> None:
    run = context.dagster_run
    job_name = run.job_name
    run_id = run.run_id
    severity = "CRITICAL" if job_name in _HALT_TIER_JOBS else "ERROR"

    error = ""
    try:
        error = context.failure_event.message or ""
    except Exception:  # noqa: BLE001 — never let alert construction crash the sensor
        error = "(failure message unavailable)"

    subject = f"{job_name} run FAILED"
    body = (
        f"Dagster job-run FAILED on the AWS box.\n\n"
        f"  job:      {job_name}\n"
        f"  run_id:   {run_id}\n"
        f"  tier:     {'HALT (serving-critical)' if severity == 'CRITICAL' else 'WARN/peripheral'}\n\n"
        f"error:\n{error}\n\n"
        f"First action: open Dagit (https://dagster.credencesports.com) → Runs → {run_id} "
        f"for the full stack trace and step logs."
    )
    # dedup per (job, severity) so a tight retry loop can't flood the inbox.
    send_alert(subject, body, severity=severity, dedup_key=f"runfail:{job_name}")
