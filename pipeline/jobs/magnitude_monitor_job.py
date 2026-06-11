from dagster import in_process_executor, job

from pipeline.ops.daily_ingestion_ops import (
    monitor_conviction_h2h_op,
    monitor_magnitude_h2h_op,
)


@job(executor_def=in_process_executor)
def magnitude_monitor_job():
    """Weekly H2H kill-criterion monitors: Story 28.3 (magnitude) + 28.6b (conviction).

    Both read-only; they log real-book ROI / Brier / accrual so the CONFIRM/KILL
    gates are auditable without manual runs. Neither fires automated bets."""
    monitor_magnitude_h2h_op()
    monitor_conviction_h2h_op()
