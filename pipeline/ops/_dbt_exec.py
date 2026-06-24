"""pipeline/ops/_dbt_exec.py — shared dbt execution helper (E11.0c).

Single source of truth replacing the three diverged private copies in
sensor_ops, intraday_ops, and daily_ingestion_ops.  Import via:
    from pipeline.ops._dbt_exec import _run_dbt, _failure_detail
"""
import os
import subprocess
import time

import requests
from dagster import RetryRequested

APP_DIR = "/app"
DBT_DIR = "/app/dbt"
_SUBPROCESS_TIMEOUT = 1800  # seconds (30 min) — hard ceiling per subprocess op


def _failure_detail(result) -> str:
    """Diagnostic tail for a failed subprocess.

    dbt-fusion writes everything to STDOUT and leaves stderr empty, so a bare
    {stderr} loses the real error to Dagster's 50k log truncation (incident
    2026-06-11). Prefer stderr; fall back to the stdout tail (dbt's end-of-run
    failure summary lives there).
    """
    err = (result.stderr or "").strip()
    if err:
        return err[-4000:]
    out_tail = (result.stdout or "")[-4000:]
    return f"(stderr empty — stdout tail)\n{out_tail}"


def _run_dbt_remote(
    context,
    args: list[str],
    runner_url: str,
    timeout_seconds: int = _SUBPROCESS_TIMEOUT,
    use_state: bool = False,
) -> None:
    """Delegate a dbt run to the E11.0 dbt-runner Railway service (services/dbt_runner/).

    Called when DBT_RUNNER_URL is set — dbt execution runs in the Railway container,
    not on Dagster+ metered compute. Falls back to in-process dbtf when absent.
    use_state=True (E11.2): the runner downloads prior manifest/sources.json from S3
    and selects source_status:fresher+ instead of the full DAG.
    """
    auth_token = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    extra_env = {"DBT_JOB_NAME": context.job_name, "DAGSTER_JOB_NAME": context.job_name}

    url = runner_url.rstrip("/")
    deadline = time.monotonic() + timeout_seconds

    # 409 = runner busy (single-tenant). Raise RetryRequested so Dagster releases the
    # compute slot during the wait — sleeping in the op holds run-minutes open for nothing.
    resp = requests.post(
        f"{url}/run",
        json={"args": args, "env": extra_env, "use_state": use_state},
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 409:
        context.log.info("[dbt-runner] runner busy (409) — releasing compute slot, retry in 30s")
        raise RetryRequested(max_retries=40, seconds_to_wait=30)
    resp.raise_for_status()

    run_id = resp.json()["run_id"]
    context.log.info(f"[dbt-runner] started run {run_id} — dbtf {' '.join(args[:3])} …")
    while time.monotonic() < deadline:
        time.sleep(15)
        status_resp = requests.get(f"{url}/status/{run_id}", headers=headers, timeout=15)
        status_resp.raise_for_status()
        data = status_resp.json()
        if data["status"] == "running":
            context.log.debug(f"[dbt-runner] {run_id} still running …")
            continue
        if data.get("stdout"):
            context.log.info(data["stdout"])
        if data.get("stderr"):
            context.log.warning(data["stderr"])
        if data["status"] == "failed":
            raise Exception(
                f"[dbt-runner] run {run_id} failed (exit {data.get('returncode')})\n"
                f"{data.get('stderr', '')}"
            )
        context.log.info(f"[dbt-runner] run {run_id} succeeded")
        return
    raise TimeoutError(f"[dbt-runner] run {run_id} timed out after {timeout_seconds}s")


def _run_dbt(
    context,
    args: list[str],
    timeout: int = _SUBPROCESS_TIMEOUT,
    use_state: bool = False,
) -> None:
    """Run a dbt command, delegating to the E11.0 runner when DBT_RUNNER_URL is set.

    Falls back to a local dbtf subprocess for dev/CI (DBT_RUNNER_URL unset).
    A hard timeout kills the subprocess if it wedges (incidents 2026-06-15/19).
    """
    runner_url = os.environ.get("DBT_RUNNER_URL")
    if runner_url:
        _run_dbt_remote(context, args, runner_url, timeout_seconds=timeout, use_state=use_state)
        return

    env = {**os.environ, "DBT_JOB_NAME": context.job_name, "DAGSTER_JOB_NAME": context.job_name}
    if use_state:
        effective_args = _local_state_aware_args(context, args, env)
    else:
        effective_args = args
    cmd = ["dbtf"] + effective_args + ["--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
    context.log.info(f"Running: {' '.join(cmd)} (timeout {timeout}s)")
    try:
        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, cwd=APP_DIR, timeout=timeout
        )
    except subprocess.TimeoutExpired as e:
        stdout_tail = ""
        if isinstance(e.stdout, bytes):
            stdout_tail = e.stdout[-2000:].decode(errors="replace")
        elif isinstance(e.stdout, str):
            stdout_tail = e.stdout[-2000:]
        raise Exception(
            f"dbtf {args[0]} exceeded {timeout}s hard timeout and was killed\n"
            f"(stdout tail)\n{stdout_tail}"
        ) from e
    if result.stdout:
        context.log.info(result.stdout)
    if result.stderr:
        context.log.warning(result.stderr)
    if result.returncode != 0:
        detail = _failure_detail(result)
        context.log.error(f"dbtf {args[0]} failed (exit {result.returncode}) — failure tail:\n{detail}")
        raise Exception(f"dbtf {args[0]} failed (exit {result.returncode})\n{detail}")
    if use_state:
        _local_state_upload(context, args, env)


def _local_state_aware_args(context, args: list[str], env: dict) -> list[str]:
    """Download S3 state and return source_status:fresher+ args (or full-build fallback)."""
    state_dir = "/tmp/dbt-state"
    try:
        import pathlib

        import boto3
        bucket = os.environ.get("DBT_STATE_BUCKET", "baseball-betting-ml-artifacts")
        prefix = os.environ.get("DBT_STATE_PREFIX", "dbt_state")
        target_env = os.environ.get("TARGET_ENV", "dev")
        s3 = boto3.client("s3")
        pathlib.Path(state_dir).mkdir(parents=True, exist_ok=True)
        for fname in ("manifest.json", "sources.json"):
            s3.download_file(bucket, f"{prefix}/{target_env}/{fname}", f"{state_dir}/{fname}")
        target_args: list[str] = []
        try:
            idx = args.index("--target")
            target_args = ["--target", args[idx + 1]]
        except (ValueError, IndexError):
            pass
        context.log.info("[dbt-runner] local state: source_status:fresher+ + views mode")
        # INC-13: union config.materialized:view so views are always rebuilt
        # (pure DDL, cheap) — skipping them causes cryptic "object does not
        # exist" errors when a fresh consumer references an unbuilt view.
        return ["build", "--select", "source_status:fresher+ config.materialized:view",
                "--state", state_dir] + target_args
    except Exception as exc:
        context.log.warning(f"[dbt-runner] local state download failed ({exc}) — full build")
        return args


def _local_state_upload(context, args: list[str], env: dict) -> None:
    """After a successful build, run source freshness and upload state to S3."""
    try:
        target_args: list[str] = []
        try:
            idx = args.index("--target")
            target_args = ["--target", args[idx + 1]]
        except (ValueError, IndexError):
            pass
        freshness_cmd = (
            ["dbtf", "source", "freshness", "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR]
            + target_args
        )
        freshness = subprocess.run(
            freshness_cmd, env=env, capture_output=True, text=True, cwd=APP_DIR
        )
        if freshness.returncode != 0:
            context.log.warning(
                f"[dbt-runner] source freshness failed (rc={freshness.returncode}) — state NOT uploaded"
            )
            return
        import pathlib

        import boto3
        bucket = os.environ.get("DBT_STATE_BUCKET", "baseball-betting-ml-artifacts")
        prefix = os.environ.get("DBT_STATE_PREFIX", "dbt_state")
        target_env = os.environ.get("TARGET_ENV", "dev")
        s3 = boto3.client("s3")
        target_dir = pathlib.Path(DBT_DIR) / "target"
        for fname in ("manifest.json", "sources.json"):
            local = target_dir / fname
            if local.exists():
                s3.upload_file(str(local), bucket, f"{prefix}/{target_env}/{fname}")
    except Exception as exc:
        context.log.warning(
            f"[dbt-runner] local state upload failed — next run will full-build. ({exc})"
        )
