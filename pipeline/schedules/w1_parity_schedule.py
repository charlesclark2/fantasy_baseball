"""
One-shot schedule: run the W1 parity gate on 2026-06-25 after 3 days of
concurrent Snowflake + S3 lakehouse runs.  Cron fires daily at 20:00 UTC
(4 PM EDT) but the function skips every day except 2026-06-25, giving the
daily_ingestion_job (08:00 EDT) time to complete first.

After the parity check passes you can turn this schedule off in the Dagster UI.
"""

from datetime import date

from dagster import RunRequest, SkipReason, schedule

from pipeline.jobs.w1_parity_job import w1_parity_job

_PARITY_DATE = date(2026, 6, 25)


@schedule(cron_schedule="0 20 * * *", job=w1_parity_job)
def w1_parity_schedule(context):
    if context.scheduled_execution_time.date() != _PARITY_DATE:
        return SkipReason(f"One-shot schedule — only runs on {_PARITY_DATE}")
    return RunRequest(run_key=str(_PARITY_DATE))
