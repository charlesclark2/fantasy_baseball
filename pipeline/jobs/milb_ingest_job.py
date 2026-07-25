"""E7.1 — the isolated daily MiLB incremental-ingest job.

A standalone single-op job (like settle_user_bets_job / the sports jobs) so MiLB ingestion runs
on its own daily cadence and, crucially, in its OWN run — a MiLB Stats-API/S3 failure fails only
this job and can never touch the MLB serving-critical daily_ingestion_job. MiLB data feeds E7.3
(MLE) + E8 (Dynasty), never the MLB predict path.
"""
from dagster import in_process_executor, job

from pipeline.ops.milb_ops import milb_incremental_ingest_op


@job(executor_def=in_process_executor)
def milb_ingest_job():
    milb_incremental_ingest_op()
