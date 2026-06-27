#!/usr/bin/env python3
"""Pull recent Dagster runs of a job; print per-run status + failed steps.

Targets the self-hosted OSS Dagster on the AWS box (INC-16). Endpoint + auth are
env-configurable:
    DAGSTER_GRAPHQL_URL   default https://dagster.credencesports.com/graphql
                          (on the box, set http://localhost:3000/graphql — no auth)
    Auth, in priority order:
      • *.dagster.plus URL + DAGSTER_CLOUD_API_TOKEN → Dagster-Cloud-Api-Token (legacy)
      • DAGIT_BASIC_AUTH_USER + DAGIT_BASIC_AUTH_PASSWORD → HTTP Basic (through Caddy)
      • neither → no auth (localhost on the box)
Secrets are never printed.

Usage:
    python3 scripts/ops/dagster_runs.py [job] [limit]
    # e.g. python3 scripts/ops/dagster_runs.py lineup_monitor_job 12
"""
import base64
import datetime
import json
import os
import sys
import urllib.request

JOB = sys.argv[1] if len(sys.argv) > 1 else "daily_ingestion_job"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 10
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
    query = (
        "query($f: RunsFilter, $n: Int){ runsOrError(filter:$f, limit:$n){ __typename "
        "... on Runs { results { runId status startTime endTime "
        "stepStats { stepKey status } tags { key value } } } "
        "... on PythonError { message } } }"
    )
    body = json.dumps({"query": query, "variables": {"f": {"pipelineName": JOB}, "n": LIMIT}}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers=_headers())
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())

    node = d.get("data", {}).get("runsOrError", {})
    if node.get("__typename") != "Runs":
        sys.exit("Query error: " + json.dumps(d)[:800])

    def ts(x):
        return datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M") if x else "—"

    res = node["results"]
    print(f"== last {len(res)} runs of {JOB} ==")
    for r in res:
        steps = r.get("stepStats") or []
        failed = [s["stepKey"] for s in steps if s["status"] == "FAILURE"]
        nok = sum(1 for s in steps if s["status"] == "SUCCESS")
        nskip = sum(1 for s in steps if s["status"] == "SKIPPED")
        nrun = sum(1 for s in steps if s["status"] in ("IN_PROGRESS", "STARTED"))
        gp = [t["value"] for t in (r.get("tags") or []) if t["key"] == "game_pks"]
        line = f"{ts(r.get('startTime')):16}  {r['status']:<9}  {nok} ok / {nskip} skip / {len(failed)} fail"
        if nrun:
            line += f" / {nrun} running"
        if failed:
            line += "   FAILED AT: " + ", ".join(failed)
        if gp:
            line += f"   game_pks={gp[0]}"
        print(line + f"   [{r['runId'][:8]}]  (full: {r['runId']})")


if __name__ == "__main__":
    main()
