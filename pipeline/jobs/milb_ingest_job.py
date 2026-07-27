"""E7.1/E7.2 — the isolated daily MiLB incremental-ingest job.

A standalone job (like settle_user_bets_job / the sports jobs) so MiLB ingestion runs on its own
daily cadence and, crucially, in its OWN run — a MiLB Stats-API/Savant/S3 failure fails only this
job and can never touch the MLB serving-critical daily_ingestion_job. Two independent ops
(game-log boxscores + AAA Statcast leaderboards) run here rather than two separate jobs — both
are WARN-tier and catch their own exceptions internally, so one failing never blocks the other;
splitting them into separate jobs would just double the Dagster scaffolding for what is
operationally one "keep MiLB data topped up" duty. MiLB data feeds E7.3 (MLE) + E8 (Dynasty),
never the MLB predict path.
"""
from dagster import in_process_executor, job

from pipeline.ops.milb_ops import (
    fangraphs_prospects_ingest_op,
    milb_incremental_ingest_op,
    statcast_aaa_incremental_ingest_op,
)


@job(executor_def=in_process_executor)
def milb_ingest_job():
    # Three independent WARN-tier ops in one isolated run (E7.1/E7.2/E7.7). Each catches its own
    # exceptions internally, so one failing never blocks the others or fails the run — one
    # operational duty ("keep the MiLB + prospect research data topped up"), no extra scaffolding.
    milb_incremental_ingest_op()
    statcast_aaa_incremental_ingest_op()
    fangraphs_prospects_ingest_op()
