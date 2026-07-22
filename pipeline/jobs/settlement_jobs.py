from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import settle_user_bets_scheduled_op


# E11.20 phase-2a — evening user-bet settlement pass.
#
# The ONLY automated settlement used to be settle_user_bets_op inside daily_ingestion_job
# (12:00 UTC / 05:00 PDT — morning). A whole slate plays out over the afternoon/evening, so
# its finals sat unsettled 12-24h until the NEXT morning's run (the app showed "open" bets;
# an operator manually re-ran the script to catch up). This job runs the same settlement on
# an evening/overnight cadence (settlement_schedule) so same-night finals settle same-night.
#
# It is cheap and safe to run frequently: idempotent (only touches bets still in the sparse
# gsi-pending-by-game index), and Snowflake-FREE (settle_user_bets.py reads scores/K totals
# from the S3 lakehouse via DuckDB), so an extra pass never wakes the warehouse (E11.20-COST).
@job(executor_def=in_process_executor)
def settle_user_bets_job():
    settle_user_bets_scheduled_op()
