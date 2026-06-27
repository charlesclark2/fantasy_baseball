#!/usr/bin/env python3
"""Fetch captured stdout/stderr (MessageEvents) for one step of a Dagster run.

Targets the self-hosted OSS Dagster on the AWS box (INC-16). Endpoint + auth are
env-configurable (see dagster_runs.py):
    DAGSTER_GRAPHQL_URL   default https://dagster.credencesports.com/graphql
                          (on the box, set http://localhost:3000/graphql — no auth)
    DAGIT_BASIC_AUTH_USER + DAGIT_BASIC_AUTH_PASSWORD  → HTTP Basic (through Caddy)
    DAGSTER_CLOUD_API_TOKEN (only if URL is *.dagster.plus)  → legacy token header
Secrets are never printed.

Usage:
    python3 scripts/ops/dagster_steplog.py <runId> <stepKey>
    # runId must be the FULL id (the 8-char prefix from dagster_runs.py won't work);
    # dagster_runs.py prints the full id in parentheses.
"""
import base64
import json
import os
import sys
import urllib.request

ENDPOINT = os.environ.get("DAGSTER_GRAPHQL_URL", "https://dagster.credencesports.com/graphql")


def _headers() -> dict:
    """Build request headers for the configured Dagster GraphQL endpoint."""
    h = {"Content-Type": "application/json"}
    tok = os.environ.get("DAGSTER_CLOUD_API_TOKEN")
    if tok and "dagster.plus" in ENDPOINT:          # legacy Dagster+ Cloud
        h["Dagster-Cloud-Api-Token"] = tok.strip()
        return h
    user = os.environ.get("DAGIT_BASIC_AUTH_USER")
    pw = os.environ.get("DAGIT_BASIC_AUTH_PASSWORD")
    if user and pw:                                  # self-hosted behind Caddy basic-auth
        h["Authorization"] = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    return h                                         # else: no auth (localhost on the box)


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Usage: dagster_steplog.py <runId> <stepKey>")
    run, step = sys.argv[1], sys.argv[2]

    # logsForRun limit max is 1000.
    q = (
        "query($r: ID!){ logsForRun(runId:$r, limit:1000){ __typename "
        "... on EventConnection { events { __typename ... on MessageEvent "
        "{ message level stepKey } } } "
        "... on PythonError { message } } }"
    )
    body = json.dumps({"query": q, "variables": {"r": run}}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers=_headers())
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
