#!/usr/bin/env python3
"""Pull recent Dagster+ runs of a job; print per-run status + failed steps.

Reads DAGSTER_CLOUD_API_TOKEN from .env (repo root) or the environment; the
token is never printed. Deployment: penumbra-partners.dagster.plus, prod.

Usage:
    python3 scripts/ops/dagster_runs.py [job] [limit]
    # e.g. python3 scripts/ops/dagster_runs.py lineup_monitor_job 12
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.request

JOB = sys.argv[1] if len(sys.argv) > 1 else "daily_ingestion_job"
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 10
ENDPOINT = "https://penumbra-partners.dagster.plus/prod/graphql"


def _load_token() -> str:
    tok = os.environ.get("DAGSTER_CLOUD_API_TOKEN")
    if tok:
        return tok.strip()
    # Walk up from this file to find a .env (repo root), independent of CWD.
    here = pathlib.Path(__file__).resolve()
    for parent in [pathlib.Path.cwd(), *here.parents]:
        env = parent / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.startswith("DAGSTER_CLOUD_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("DAGSTER_CLOUD_API_TOKEN not found in env or .env")


def main() -> None:
    token = _load_token()
    query = (
        "query($f: RunsFilter, $n: Int){ runsOrError(filter:$f, limit:$n){ __typename "
        "... on Runs { results { runId status startTime endTime "
        "stepStats { stepKey status } tags { key value } } } "
        "... on PythonError { message } } }"
    )
    body = json.dumps({"query": query, "variables": {"f": {"pipelineName": JOB}, "n": LIMIT}}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Dagster-Cloud-Api-Token": token, "Content-Type": "application/json"},
    )
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
