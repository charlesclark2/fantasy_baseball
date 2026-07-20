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

    # INC-32 run-stall diagnosis — per-OP durations of the most recent run, slowest first
    # (finds which op ate the predict→serve tail):
    python3 scripts/ops/dagster_runs.py daily_ingestion_job --steps
    # a specific run:
    python3 scripts/ops/dagster_runs.py daily_ingestion_job --steps <runId>
"""
import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

_ARGV = [a for a in sys.argv[1:] if a != "--steps"]
STEPS_MODE = "--steps" in sys.argv
JOB = _ARGV[0] if len(_ARGV) > 0 else "daily_ingestion_job"
# In --steps mode the 2nd positional is an optional runId; otherwise it's the run LIMIT.
STEP_RUN_ID = _ARGV[1] if (STEPS_MODE and len(_ARGV) > 1) else None
LIMIT = int(_ARGV[1]) if (not STEPS_MODE and len(_ARGV) > 1) else 10
ENDPOINT = os.environ.get("DAGSTER_GRAPHQL_URL", "https://dagster.credencesports.com/graphql")
# ON THE BOX the webserver is published at 127.0.0.1:3000 with NO auth (Caddy terminates
# basic-auth only for the public host). So the public default 401s when you run this on the box
# without exporting DAGIT_BASIC_AUTH_*; we fall back to this on a 401-with-no-auth (see main()).
_LOCAL_FALLBACK = "http://localhost:3000/graphql"


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
    # stepStats carries per-op start/end so --steps can attribute wall-clock (INC-32 run-stall).
    query = (
        "query($f: RunsFilter, $n: Int){ runsOrError(filter:$f, limit:$n){ __typename "
        "... on Runs { results { runId status startTime endTime "
        "stepStats { stepKey status startTime endTime } tags { key value } } } "
        "... on PythonError { message } } }"
    )
    body = json.dumps({"query": query, "variables": {"f": {"pipelineName": JOB}, "n": LIMIT}}).encode()

    def _post(url: str) -> dict:
        req = urllib.request.Request(url, data=body, headers=_headers())
        return json.loads(urllib.request.urlopen(req, timeout=30).read())

    try:
        d = _post(ENDPOINT)
    except urllib.error.HTTPError as e:
        # 401 with no basic-auth configured + still on the public default = you're on the box.
        # Retry the local webserver (127.0.0.1:3000, no auth) instead of dumping a traceback.
        no_auth = not (os.environ.get("DAGIT_BASIC_AUTH_USER") and os.environ.get("DAGIT_BASIC_AUTH_PASSWORD"))
        if e.code == 401 and no_auth and "DAGSTER_GRAPHQL_URL" not in os.environ:
            print(f"[dagster_runs] {ENDPOINT} → 401 (no auth); retrying {_LOCAL_FALLBACK} "
                  f"(set DAGSTER_GRAPHQL_URL to silence this).", file=sys.stderr)
            d = _post(_LOCAL_FALLBACK)
        else:
            raise

    node = d.get("data", {}).get("runsOrError", {})
    if node.get("__typename") != "Runs":
        sys.exit("Query error: " + json.dumps(d)[:800])

    def ts(x):
        return datetime.datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M") if x else "—"

    def tsp(x):
        return datetime.datetime.fromtimestamp(x).strftime("%H:%M:%S") if x else "—"

    res = node["results"]

    if STEPS_MODE:
        run = None
        if STEP_RUN_ID:
            run = next((r for r in res if r["runId"].startswith(STEP_RUN_ID)), None)
        elif res:
            run = res[0]  # most recent
        if run is None:
            sys.exit(f"No matching run for {JOB} (runId={STEP_RUN_ID}).")
        print(f"== per-op durations: {JOB}  [{run['runId']}]  {run['status']}  "
              f"start {ts(run.get('startTime'))} ==")
        rows = []
        for s in run.get("stepStats") or []:
            st, en = s.get("startTime"), s.get("endTime")
            dur = (en - st) if (st and en) else None
            rows.append((dur, s["stepKey"], s.get("status"), st, en))
        # Slowest first; unfinished (dur=None) last.
        rows.sort(key=lambda x: (x[0] is None, -(x[0] or 0)))
        for dur, key, status, st, en in rows:
            dstr = f"{dur/60:6.1f} min" if dur is not None else "   —    "
            print(f"  {dstr}  {status:<11}  {tsp(st)}→{tsp(en)}  {key}")
        return
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
