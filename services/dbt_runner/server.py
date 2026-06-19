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

Concurrency: one dbt run at a time — the Snowflake COMPUTE_WH is the bottleneck,
and concurrent dbtf processes would compete for the same warehouse slots anyway.
Callers that arrive during an active run receive HTTP 409; they should back off and
retry (the Dagster op already polls for up to 45 minutes).
"""
import os
import subprocess
import threading
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

_AUTH_TOKEN: str = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
_DBT_PROJECT_DIR: str = os.environ.get("DBT_PROJECT_DIR", "/dbt")

# In-memory run registry — sufficient for a single-instance service where
# Dagster polls until completion within the same process lifetime.
_runs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

app = FastAPI(title="dbt-runner", version="1.0.0")


def _check_auth(authorization: str | None) -> None:
    if _AUTH_TOKEN and authorization != f"Bearer {_AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


class RunRequest(BaseModel):
    args: list[str]
    env: dict[str, str] = {}


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

    threading.Thread(target=_execute, args=(run_id, body.args, body.env), daemon=True).start()
    return {"run_id": run_id}


@app.get("/status/{run_id}")
def get_status(run_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _check_auth(authorization)
    entry = _runs.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return entry


def _execute(run_id: str, args: list[str], extra_env: dict[str, str]) -> None:
    env = {
        **os.environ,
        **extra_env,
        "DBT_JOB_NAME": extra_env.get("DBT_JOB_NAME", f"dbt_runner|{run_id}"),
    }
    cmd = ["dbtf"] + args + ["--project-dir", _DBT_PROJECT_DIR, "--profiles-dir", _DBT_PROJECT_DIR]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=_DBT_PROJECT_DIR)
    _runs[run_id] = {
        "status": "success" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
