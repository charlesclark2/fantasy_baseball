"""E11.0 — dbt-runner HTTP service.

FastAPI server that accepts dbt run requests, executes dbtf in a background
thread, and exposes a polling endpoint for status. Deployed on Railway as
an always-on web service; Dagster ops POST /run instead of running dbtf
in-process, removing dbt execution from Dagster+ run-minutes.

Environment variables (set in Railway):
    DBT_RUNNER_AUTH_TOKEN  Shared secret; sent as "Authorization: Bearer <token>".
                           Leave unset to disable auth (dev/local only).
    DBT_PROJECT_DIR        Path to the dbt project (default /dbt).
    SNOWFLAKE_PRIVATE_KEY  PEM key string — written to a temp file by entrypoint.sh.
    SNOWFLAKE_PRIVATE_KEY_PATH  Set by entrypoint.sh after writing the PEM.
    TARGET_ENV             prod | dev (forwarded to dbt via DBT_JOB_NAME tag).
    DBT_STATE_BUCKET       S3 bucket for state files (default baseball-betting-ml-artifacts).
    DBT_STATE_PREFIX       S3 key prefix for state files (default dbt_state).

Concurrency: one dbt run at a time — the Snowflake COMPUTE_WH is the bottleneck,
and concurrent dbtf processes would compete for the same warehouse slots anyway.
Callers that arrive during an active run receive HTTP 409; they should back off and
retry (the Dagster op already polls for up to 45 minutes).
"""
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

_AUTH_TOKEN: str = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
_DBT_PROJECT_DIR: str = os.environ.get("DBT_PROJECT_DIR", "/dbt")

# E11.2 Task 2 — S3 state persistence for source_status:fresher+ daily builds.
# State files: manifest.json (dbt graph) + sources.json (freshness timestamps).
# Keyed by TARGET_ENV so prod and dev never clobber each other.
_STATE_BUCKET: str = os.environ.get("DBT_STATE_BUCKET", "baseball-betting-ml-artifacts")
_STATE_PREFIX: str = os.environ.get("DBT_STATE_PREFIX", "dbt_state")
_TARGET_ENV: str = os.environ.get("TARGET_ENV", "dev")
_STATE_LOCAL_DIR: str = "/tmp/dbt-state"
_STATE_FILES: tuple[str, ...] = ("manifest.json", "sources.json")

# In-memory run registry — sufficient for a single-instance service where
# Dagster polls until completion within the same process lifetime.
_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

app = FastAPI(title="dbt-runner", version="1.0.0")


def _check_auth(authorization: str | None) -> None:
    if _AUTH_TOKEN and authorization != f"Bearer {_AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _s3_state_key(filename: str) -> str:
    return f"{_STATE_PREFIX}/{_TARGET_ENV}/{filename}"


def _download_state() -> bool:
    """Pull prior manifest.json + sources.json from S3 into _STATE_LOCAL_DIR.

    Returns True only when BOTH files are successfully retrieved; we need
    both for --state to be meaningful. A missing-bucket or missing-key error
    is expected on first run and treated as a normal full-build trigger.
    """
    try:
        import boto3
        s3 = boto3.client("s3")
        Path(_STATE_LOCAL_DIR).mkdir(parents=True, exist_ok=True)
        for fname in _STATE_FILES:
            s3.download_file(_STATE_BUCKET, _s3_state_key(fname),
                             f"{_STATE_LOCAL_DIR}/{fname}")
        return True
    except Exception as exc:
        print(f"[dbt-runner] state download miss ({exc}) — will full-build", flush=True)
        return False


def _upload_state() -> None:
    """Push target/manifest.json + target/sources.json to S3 after a successful run.

    Non-fatal on error: the worst outcome is the next run falls back to a full
    build rather than the cheaper source_status:fresher+ path.
    """
    try:
        import boto3
        s3 = boto3.client("s3")
        target_dir = Path(_DBT_PROJECT_DIR) / "target"
        for fname in _STATE_FILES:
            local = target_dir / fname
            if local.exists():
                s3.upload_file(str(local), _STATE_BUCKET, _s3_state_key(fname))
                print(f"[dbt-runner] state uploaded: {_s3_state_key(fname)}", flush=True)
            else:
                print(f"[dbt-runner] WARNING: {fname} not found in target/ — not uploaded",
                      flush=True)
    except Exception as exc:
        print(f"[dbt-runner] WARNING: state upload failed — next run will full-build. ({exc})",
              flush=True)


def _extract_target_args(args: list[str]) -> list[str]:
    """Extract ['--target', '<value>'] from an args list, or return []."""
    try:
        idx = args.index("--target")
        return ["--target", args[idx + 1]]
    except (ValueError, IndexError):
        return []


def _run_cmd(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, env=env, cwd=_DBT_PROJECT_DIR
    )


class RunRequest(BaseModel):
    args: list[str]
    env: dict[str, str] = {}
    # E11.2 Task 2: when True, download prior state from S3 and run
    # source_status:fresher+ instead of the full DAG; upload new state on success.
    use_state: bool = False


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/run")
def start_run(body: RunRequest, authorization: str | None = Header(None)) -> dict[str, str]:
    _check_auth(authorization)
    with _lock:
        in_flight = [r for r in _runs.values() if r["status"] == "running"]
        if in_flight:
            raise HTTPException(
                status_code=409,
                detail="A dbt run is already in progress — retry after it completes",
            )
        run_id = uuid.uuid4().hex[:8]
        _runs[run_id] = {"status": "running", "stdout": "", "stderr": "", "returncode": None}

    threading.Thread(
        target=_execute, args=(run_id, body.args, body.env, body.use_state), daemon=True
    ).start()
    return {"run_id": run_id}


@app.get("/status/{run_id}")
def get_status(run_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(authorization)
    entry = _runs.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return entry


def _execute(run_id: str, args: list[str], extra_env: dict[str, str], use_state: bool) -> None:
    env = {
        **os.environ,
        **extra_env,
        "DBT_JOB_NAME": extra_env.get("DBT_JOB_NAME", f"dbt_runner|{run_id}"),
    }
    log: list[str] = []

    effective_args = args
    if use_state:
        has_state = _download_state()
        if has_state:
            # Override the default args with source_status:fresher+ selection so
            # only models downstream of sources that have new data since the prior
            # run are rebuilt. --state points at the downloaded prior sources.json +
            # manifest.json; dbt compares current freshness against sources.json to
            # determine which sources are "fresher" and selects their descendants.
            target_args = _extract_target_args(args)
            effective_args = (
                ["build", "--select", "source_status:fresher+",
                 "--state", _STATE_LOCAL_DIR]
                + target_args
            )
            log.append(
                "[dbt-runner] mode=source_status:fresher+ (prior state found in S3)\n"
            )
        else:
            log.append(
                "[dbt-runner] mode=full-build (no prior state in S3 — first run or upload failed)\n"
            )

    cmd = ["dbtf"] + effective_args + [
        "--project-dir", _DBT_PROJECT_DIR, "--profiles-dir", _DBT_PROJECT_DIR
    ]
    result = _run_cmd(cmd, env)

    stderr_extra = ""
    if use_state and result.returncode == 0:
        # Produce target/sources.json for the next run's freshness comparison.
        # `dbtf build --select source_status:fresher+` runs freshness internally
        # for selection but does not persist sources.json; run it explicitly so
        # the artifact is always fresh and ready to upload.
        freshness_cmd = (
            ["dbtf", "source", "freshness",
             "--project-dir", _DBT_PROJECT_DIR, "--profiles-dir", _DBT_PROJECT_DIR]
            + _extract_target_args(args)
        )
        freshness = _run_cmd(freshness_cmd, env)
        log.append(freshness.stdout)
        if freshness.returncode != 0:
            stderr_extra = (
                f"[dbt-runner] WARNING: source freshness failed (rc={freshness.returncode})"
                " — state NOT uploaded; next run will full-build.\n"
                + freshness.stderr
            )
        else:
            _upload_state()

    _runs[run_id] = {
        "status": "success" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": "".join(log) + result.stdout,
        "stderr": result.stderr + stderr_extra,
    }
