#!/usr/bin/env python3
"""Fetch captured stdout/stderr (MessageEvents) for one step of a Dagster+ run.

Reads DAGSTER_CLOUD_API_TOKEN from .env (repo root) or the environment; never
printed. Deployment: penumbra-partners.dagster.plus, prod.

Usage:
    python3 scripts/ops/dagster_steplog.py <runId> <stepKey>
    # runId must be the FULL id (the 8-char prefix from dagster_runs.py won't work);
    # dagster_runs.py prints the full id in parentheses.
"""
import json
import os
import pathlib
import sys
import urllib.request

ENDPOINT = "https://penumbra-partners.dagster.plus/prod/graphql"


def _load_token() -> str:
    tok = os.environ.get("DAGSTER_CLOUD_API_TOKEN")
    if tok:
        return tok.strip()
    here = pathlib.Path(__file__).resolve()
    for parent in [pathlib.Path.cwd(), *here.parents]:
        env = parent / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.startswith("DAGSTER_CLOUD_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("DAGSTER_CLOUD_API_TOKEN not found in env or .env")


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Usage: dagster_steplog.py <runId> <stepKey>")
    run, step = sys.argv[1], sys.argv[2]
    token = _load_token()

    # logsForRun limit max is 1000.
    q = (
        "query($r: ID!){ logsForRun(runId:$r, limit:1000){ __typename "
        "... on EventConnection { events { __typename ... on MessageEvent "
        "{ message level stepKey } } } "
        "... on PythonError { message } } }"
    )
    body = json.dumps({"query": q, "variables": {"r": run}}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Dagster-Cloud-Api-Token": token, "Content-Type": "application/json"},
    )
    d = json.loads(urllib.request.urlopen(req, timeout=40).read())

    node = d.get("data", {}).get("logsForRun", {})
    if node.get("__typename") != "EventConnection":
        print("err:", json.dumps(d)[:800])
        sys.exit(1)
    hits = [e for e in node["events"] if (e.get("stepKey") or "").startswith(step) and e.get("message")]
    print(f"== {len(hits)} log lines for step '{step}' in run {run[:8]} ==")
    for e in hits[-80:]:
        print(f"[{(e.get('level') or '')[:5]:5}] {e['message'][:300]}")


if __name__ == "__main__":
    main()
