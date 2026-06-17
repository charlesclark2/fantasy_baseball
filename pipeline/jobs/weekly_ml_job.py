from dagster import in_process_executor, job

from pipeline.ops.weekly_ml_ops import (
    compute_stacking_weights_op,
    train_bayesian_meta_model_op,
)


@job(executor_def=in_process_executor)
def weekly_ml_job():
    """Weekly Layer 3 stacking-weight recomputation (Epic 9 Story 9.6 / Epic O.3)."""
    compute_stacking_weights_op()


@job(executor_def=in_process_executor)
def weekly_meta_model_job():
    """Weekly Bayesian CLV meta-model retrain (Story 12.4 / Epic O.5).

    Separate job (not folded into weekly_ml_job) on a different day so the slow MCMC
    is an independent failure domain from the stacking-weights recompute and the
    Snowflake compute load is spread across the week (Wednesday vs. Monday).
    """
    train_bayesian_meta_model_op()
