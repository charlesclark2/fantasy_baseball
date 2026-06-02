from dagster import in_process_executor, job

from pipeline.ops.weekly_ml_ops import compute_stacking_weights_op


@job(executor_def=in_process_executor)
def weekly_ml_job():
    """Weekly Layer 3 stacking-weight recomputation (Epic 9 Story 9.6 / Epic O.3)."""
    compute_stacking_weights_op()
