"""
E11.1-W1 parity check job.

Runs scripts/parity_check_w1.py to validate that the S3 Parquet lakehouse
outputs match Snowflake mart_pitch_* on row count and PK uniqueness.
Hard-fails the job on any discrepancy so the operator is notified via Dagster+.
Scheduled to run automatically on 2026-06-25 (after 3 days of parallel runs).
Can also be triggered manually from the Dagster UI at any time.
"""

import os
import subprocess
import sys

from dagster import In, Nothing, Out, in_process_executor, job, op

SCRIPTS_DIR = "/app/scripts"
APP_DIR = "/app"


@op(out=Out(Nothing))
def w1_parity_op(context):
    path = f"{SCRIPTS_DIR}/parity_check_w1.py"
    cmd = [sys.executable, path]
    env = {**os.environ, "DAGSTER_JOB_NAME": context.job_name}
    context.log.info(f"Running W1 parity gate: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=APP_DIR)
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(
            f"W1 parity gate FAILED — S3 lakehouse does not match Snowflake.\n{result.stderr}"
        )
    context.log.info("W1 parity gate PASSED — safe to decommission Snowflake mart_pitch_* schedules.")


@job(executor_def=in_process_executor)
def w1_parity_job():
    w1_parity_op()
