from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import monitor_magnitude_h2h_op


@job(executor_def=in_process_executor)
def magnitude_monitor_job():
    """Weekly Story 28.3 kill-criterion monitor for magnitude H2H bets."""
    monitor_magnitude_h2h_op()
