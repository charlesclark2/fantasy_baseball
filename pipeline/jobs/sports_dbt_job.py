"""
NFL-N0.3 — the box Dagster job that builds the `sports_dbt` NFL DAG (dbt-duckdb over the
S3/Delta lake).

This is the FIRST sports-dbt (DuckDB-native) build wired into Dagster — the MLB dbt path
(`_dbt_exec` → the remote dbt-fusion/Snowflake runner) does NOT apply here. `sports_dbt` is a
disjoint DuckDB project (NCAAF + NFL): it reads the raw Delta lake via DuckDB and materializes
tables into a LOCAL DuckDB file (no warehouse, no remote runner). So this job just invokes
dbt-duckdb in-process on the box.

Tier: standalone job, NOT in the MLB daily serving DAG → it fails ITS OWN run on a build error
(so the operator is alerted) and blocks nothing MLB-serving. INC-32 discipline: the subprocess
carries a finite `timeout=` so a wedged dbt can never hang the Dagster worker forever.

⚠️ DEPLOY PREREQUISITES (operator — dbt-duckdb is not on the box image yet, per the NCAAF-P0.2
flag): the box image must install `dbt-core` + `dbt-duckdb` (already in this repo's uv lock), and
the container needs S3 read on `credence-sports-lakehouse` via the instance role (the same chain
the MLB writers use — no inline keys). Region is pinned to us-east-2 for the DuckDB S3 secret.
"""

import os
import subprocess
import sys

from dagster import In, Nothing, Out, in_process_executor, job, op

# The repo is copied to /app on the box; the shared sports project lives here.
SPORTS_DBT_DIR = os.environ.get(
    "SPORTS_DBT_DIR", "/app/quant_sports_intel_models/sports_dbt"
)
# 40 min ceiling — the full NFL build is ~1–2 min over the lake; this is a generous wedge-guard.
DBT_TIMEOUT_SECONDS = int(os.environ.get("SPORTS_DBT_TIMEOUT_SECONDS", "2400"))


@op(out=Out(Nothing))
def sports_nfl_dbt_build_op(context):
    """Build the NFL staging + refined marts in sports_dbt over the S3/Delta lake."""
    cmd = [
        sys.executable,
        "-m",
        "dbt.cli.main",
        "build",  # run models + run their data tests in one pass
        "--select",
        "nfl.staging",
        "nfl.marts+",
        "--project-dir",
        SPORTS_DBT_DIR,
        "--profiles-dir",
        SPORTS_DBT_DIR,
    ]
    env = {
        **os.environ,
        "DAGSTER_JOB_NAME": context.job_name,
        # DuckDB needs an explicit region for the S3 lake bucket (boto3 is region-less).
        "SPORTS_LAKE_REGION": os.environ.get("SPORTS_LAKE_REGION", "us-east-2"),
        "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-2"),
        # Materialize into a writable local DuckDB file (rebuilt each run).
        "SPORTS_DUCKDB_PATH": os.environ.get("SPORTS_DUCKDB_PATH", "/tmp/sports_nfl.duckdb"),
    }
    context.log.info(f"Building sports_dbt NFL DAG: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            cwd=SPORTS_DBT_DIR,
            timeout=DBT_TIMEOUT_SECONDS,  # INC-32: never an un-timed-out subprocess on a worker
        )
    except subprocess.TimeoutExpired as exc:
        raise Exception(
            f"sports_dbt NFL build TIMED OUT after {DBT_TIMEOUT_SECONDS}s — dbt wedged."
        ) from exc

    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        raise Exception(
            f"sports_dbt NFL build FAILED (exit {result.returncode}). See logs above."
        )
    context.log.info("sports_dbt NFL build PASSED — staging + refined marts materialized.")


@job(executor_def=in_process_executor)
def sports_nfl_dbt_build_job():
    sports_nfl_dbt_build_op()
