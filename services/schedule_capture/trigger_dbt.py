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
    print("[trigger_dbt] DBT_RUNNER_URL not set — skipping remote dbt trigger", flush=True)
    sys.exit(0)

if not dbt_args:
    print("[trigger_dbt] no dbt args provided", file=sys.stderr, flush=True)
    sys.exit(1)

headers = {"Authorization": f"Bearer {token}"} if token else {}
payload = {"args": dbt_args, "env": {"DBT_JOB_NAME": job_name, "DAGSTER_JOB_NAME": job_name}}

print(f"[trigger_dbt] POST {url}/run  args={dbt_args[:3]}…", flush=True)
try:
    resp = requests.post(f"{url}/run", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
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
