#!/usr/bin/env python3
"""
trigger_dbt.py — Call the E11.0 dbt-runner HTTP API and wait for the run.

Usage (argv[1..] = dbt args):
    python trigger_dbt.py run --select stg_statsapi_lineups --target baseball_betting_and_fantasy

Required env vars:
    DBT_RUNNER_URL          — E11.0 service base URL
    DBT_RUNNER_AUTH_TOKEN   — bearer token (optional; if set, included in Authorization header)
    DBT_JOB_NAME            — tag injected into dbt QUERY_TAG for cost attribution

Exits 0 on success, 1 on failure/timeout. If DBT_RUNNER_URL is unset, exits 0
with a warning so the caller can deploy without the runner wired up.
"""
import os
import sys
import time

import requests

url = os.environ.get("DBT_RUNNER_URL", "").rstrip("/")
token = os.environ.get("DBT_RUNNER_AUTH_TOKEN", "")
job_name = os.environ.get("DBT_JOB_NAME", "schedule_capture_cron")
dbt_args = sys.argv[1:]

if not url:
    print(
        "[trigger_dbt] WARNING: DBT_RUNNER_URL not set — dbt staging rebuild SKIPPED. "
        "Raw schedule data landed in Snowflake but stg_statsapi_lineups* will NOT be "
        "refreshed until the next daily build. Set DBT_RUNNER_URL on this service to fix.",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(0)

if not dbt_args:
    print("[trigger_dbt] no dbt args provided", file=sys.stderr, flush=True)
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"} if token else {}
payload = {"args": dbt_args, "env": {"DBT_JOB_NAME": job_name, "DAGSTER_JOB_NAME": job_name}}

print(f"[trigger_dbt] POST {url}/run  args={dbt_args[:3]}…", flush=True)
# The dbt-runner serializes to ONE run at a time and returns 409 Conflict when busy
# (daily build, an odds/intraday rebuild, or a duplicate schedule-capture tick). A bare
# raise_for_status() here made a contended tick DROP the lineup-staging rebuild entirely
# (non-fatal in the entrypoint) → the lineup feed silently lagged → lineup_monitor_sensor
# saw no fresh lineups until a manual kick. So treat 409 as "runner busy → back off and
# retry" (bounded); every other error still fails fast.
_RETRY_409_MAX = 6          # ~6 attempts
_RETRY_409_BACKOFF = 20     # seconds between attempts (runner runs are short)
resp = None
for _attempt in range(1, _RETRY_409_MAX + 1):
    try:
        resp = requests.post(f"{url}/run", json=payload, headers=headers, timeout=30)
        if resp.status_code == 409:
            if _attempt < _RETRY_409_MAX:
                print(
                    f"[trigger_dbt] runner busy (409) — attempt {_attempt}/{_RETRY_409_MAX}; "
                    f"retrying in {_RETRY_409_BACKOFF}s",
                    flush=True,
                )
                time.sleep(_RETRY_409_BACKOFF)
                continue
            print(
                f"[trigger_dbt] runner still busy (409) after {_RETRY_409_MAX} attempts — "
                "giving up this tick (next 30-min tick retries)",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)
        resp.raise_for_status()
        break
    except Exception as exc:
        print(f"[trigger_dbt] failed to start run: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)

run_id = resp.json()["run_id"]
print(f"[trigger_dbt] run {run_id} started", flush=True)

deadline = time.monotonic() + 900  # 15-min hard ceiling
while time.monotonic() < deadline:
    time.sleep(15)
    try:
        sr = requests.get(f"{url}/status/{run_id}", headers=headers, timeout=15)
        sr.raise_for_status()
    except Exception as exc:
        print(f"[trigger_dbt] status poll error (non-fatal): {exc}", flush=True)
        continue
    data = sr.json()
    if data["status"] == "running":
        continue
    if data.get("stdout"):
        print(data["stdout"], flush=True)
    if data["status"] == "failed":
        print(
            f"[trigger_dbt] run {run_id} FAILED (exit {data.get('returncode')})\n"
            f"{data.get('stderr', '')}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    print(f"[trigger_dbt] run {run_id} succeeded", flush=True)
    sys.exit(0)

print(f"[trigger_dbt] run {run_id} timed out after 15 min", file=sys.stderr, flush=True)
sys.exit(1)
