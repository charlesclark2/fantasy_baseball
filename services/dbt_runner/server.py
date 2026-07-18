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
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

_AUTH_TOKEN: str = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
_DBT_PROJECT_DIR: str = os.environ.get("DBT_PROJECT_DIR", "/dbt")

# INC-32 (2026-07-18) — SERVER-SIDE hard ceiling on a single dbtf run. The single-tenant lock
# below (start_run 409s while any run is "running") had no server-side timeout: a wedged dbtf
# process (documented 2026-06-15 — "the dbt-fusion CLI process simply stopped exiting") hung the
# worker thread FOREVER, so the dead-but-"running" entry held the lock permanently → EVERY
# subsequent /run 409'd until an operator manually restarted the container. Downstream that
# stalled the daily build's dbt op (daily fired ~1.2h late), dropped schedule_capture's staging
# rebuild (stale lineups), and blocked the lineup_monitor rebuild ops (the manual run's 5h stall).
# A finite timeout + a stale-run reaper guarantee the lock ALWAYS frees on its own. Default 60 min
# bounds a true wedge while still accommodating a Sunday --full-refresh build (a healthy run that
# finishes normally releases the lock the moment it returns, well before this ceiling).
_MAX_RUN_SECONDS: int = int(os.environ.get("DBT_RUNNER_MAX_RUN_SECONDS", "3600"))
_REAP_GRACE_SECONDS: int = 120  # extra slack before start_run treats a "running" entry as dead

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
    # INC-32: hard timeout so a wedged dbtf is KILLED (child + its process group) and surfaced as
    # a non-zero result instead of hanging the worker thread forever. subprocess.run() kills the
    # child on timeout; the caller (_execute) then marks the run "failed", which FREES the
    # single-tenant lock so the next /run is served instead of 409-ing indefinitely.
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, env=env, cwd=_DBT_PROJECT_DIR,
            timeout=_MAX_RUN_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode(errors="replace")
        err = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,  # conventional timeout exit code
            stdout=out,
            stderr=(err + f"\n[dbt-runner] KILLED: exceeded {_MAX_RUN_SECONDS}s hard timeout "
                    "(INC-32 wedge guard — the single-tenant lock is now freed).").strip(),
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


def _reap_stale_runs(now: float) -> None:
    """INC-32: mark any 'running' entry whose worker thread has clearly died (started longer ago
    than the hard timeout + grace, yet never transitioned to success/failed) as failed, so a dead
    thread can NEVER hold the single-tenant lock forever. Belt-and-suspenders behind the _run_cmd
    timeout: covers the case where the worker thread dies before it can set the terminal status.
    Called under _lock."""
    ceiling = _MAX_RUN_SECONDS + _REAP_GRACE_SECONDS
    for rid, entry in _runs.items():
        if entry.get("status") != "running":
            continue
        started = entry.get("started_monotonic")
        if started is not None and (now - started) > ceiling:
            entry["status"] = "failed"
            entry["returncode"] = 124
            entry["stderr"] = (entry.get("stderr", "") +
                               f"\n[dbt-runner] REAPED: run stuck 'running' > {ceiling}s with no "
                               "terminal status — worker thread presumed dead; lock freed "
                               "(INC-32).").strip()


@app.post("/run")
def start_run(body: RunRequest, authorization: str | None = Header(None)) -> dict[str, str]:
    _check_auth(authorization)
    with _lock:
        now = time.monotonic()
        _reap_stale_runs(now)  # free the lock if a prior run's worker thread died
        in_flight = [r for r in _runs.values() if r["status"] == "running"]
        if in_flight:
            raise HTTPException(
                status_code=409,
                detail="A dbt run is already in progress — retry after it completes",
            )
        run_id = uuid.uuid4().hex[:8]
        _runs[run_id] = {
            "status": "running", "stdout": "", "stderr": "", "returncode": None,
            "started_monotonic": now,
        }

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


def _execute(run_id: str, args: list[str], extra_env: dict[str, str], use_state: bool = False) -> None:
    # INC-32: any unexpected exception in the body (state download, boto3, subprocess spawn) must
    # still transition the run to a TERMINAL status — otherwise the entry stays "running" and holds
    # the single-tenant lock forever (the exact wedge this story fixes). The reaper is the last
    # resort; this makes the common failure paths self-clear immediately.
    try:
        _execute_impl(run_id, args, extra_env, use_state)
    except Exception as exc:  # noqa: BLE001 — must never leave the run "running"
        _runs[run_id] = {
            "status": "failed",
            "returncode": 1,
            "stdout": "",
            "stderr": f"[dbt-runner] _execute crashed ({type(exc).__name__}): {exc} — lock freed (INC-32)",
        }


def _execute_impl(run_id: str, args: list[str], extra_env: dict[str, str], use_state: bool = False) -> None:
    env = {
        **os.environ,
        **extra_env,
        "DBT_JOB_NAME": extra_env.get("DBT_JOB_NAME", f"dbt_runner|{run_id}"),
    }
    log: list[str] = []

    effective_args = args
    if use_state:
        state_ready = _download_state()
        if state_ready:
            # E11.2: run source freshness first (non-fatal; exit 1 from stale-data warnings
            # is expected when ingest is paused). This writes target/sources.json so the
            # source_status:fresher+ selector has a freshness baseline to compare against.
            target_args = _extract_target_args(args)
            freshness_cmd = ["dbtf", "source", "freshness",
                             "--project-dir", _DBT_PROJECT_DIR,
                             "--profiles-dir", _DBT_PROJECT_DIR] + target_args
            freshness_result = _run_cmd(freshness_cmd, env)
            log.append(f"[dbt-runner] source freshness exit={freshness_result.returncode} "
                       f"(non-fatal; stale-warn is expected when ingest is paused)\n")
            # Switch to source_status:fresher+ selector with state from S3.
            # INC-13: union config.materialized:view so views are always rebuilt
            # (pure DDL, cheap) — skipping them causes cryptic "object does not
            # exist" errors when a fresh consumer references an unbuilt view.
            effective_args = ["build", "--select",
                              "source_status:fresher+ config.materialized:view",
                              "--state", _STATE_LOCAL_DIR] + target_args
        else:
            log.append("[dbt-runner] no prior state in S3 — full build\n")

    cmd = ["dbtf"] + effective_args + [
        "--project-dir", _DBT_PROJECT_DIR, "--profiles-dir", _DBT_PROJECT_DIR
    ]
    result = _run_cmd(cmd, env)

    stderr_extra = ""
    if use_state and result.returncode == 0:
        _upload_state()

    _runs[run_id] = {
        "status": "success" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": "".join(log) + result.stdout,
        "stderr": result.stderr + stderr_extra,
    }
