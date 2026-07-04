"""
diagnose_fangraphs_500.py  (INC-26 root-cause probe — RUN ON THE BOX)
---------------------------------------------------------------------
The leaderboard 500s even at pageitems=1000, and each attempt runs ~61s — right at
FlareSolverr's 60s maxTimeout. That points at a SERVER-SIDE TIMEOUT (FanGraphs takes
>60s to compute the qual=0 Stuff+ leaderboard over a date range), not a payload-size
problem. This probe hits FlareSolverr DIRECTLY with a matrix of {maxTimeout, qual,
date-range vs full-season, endpoint} and reports (status, elapsed) for each so we can
see EXACTLY which lever returns 200 — then finalize fangraphs_client.py accordingly.

Run on the EC2 box (FlareSolverr is box-co-located):
  docker compose -f services/dagster/aws/docker-compose.yml exec -T dagster-codeloc \
    python scripts/spikes/diagnose_fangraphs_500.py

Reads FLARESOLVERR_URL from the env (already set on the box).
"""
import os
import time
from urllib.parse import urlencode

from curl_cffi import requests

FLARE = os.environ.get("FLARESOLVERR_URL", "")
LEADERBOARD = "https://www.fangraphs.com/api/leaders/major-league/data"


def _base(stats="pit", type_id=36, season=2026, qual="0", pageitems="1000",
          startdate=None, enddate=None, month="1000"):
    p = {
        "pos": "all", "stats": stats, "lg": "all", "qual": str(qual),
        "season": season, "season1": season,
        "startdate": startdate or "", "enddate": enddate or "",
        "month": month, "hand": "", "team": "0", "ind": "0", "rost": "0",
        "players": "", "type": type_id, "postseason": "",
        "sortdir": "default", "sortstat": "WAR", "pageitems": pageitems, "pagenum": "1",
    }
    return p


def probe(label, params, max_timeout_ms):
    url = f"{LEADERBOARD}?{urlencode(params)}"
    payload = {"cmd": "request.get", "url": url, "maxTimeout": max_timeout_ms}
    t0 = time.time()
    try:
        # POST timeout must exceed maxTimeout (solve + fetch).
        r = requests.post(FLARE, json=payload, timeout=max_timeout_ms / 1000 + 30)
        r.raise_for_status()
        data = r.json()
        sol = data.get("solution", {}) or {}
        upstream = sol.get("status")
        resp = sol.get("response", "") or ""
        # crude row count: count '"playerid"' occurrences in the rendered JSON
        rows = resp.count('"playerid"')
        elapsed = time.time() - t0
        print(f"[{label:38}] flare={data.get('status'):5} upstream={upstream} "
              f"rows≈{rows:5} elapsed={elapsed:5.1f}s maxTimeout={max_timeout_ms/1000:.0f}s")
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"[{label:38}] ERROR after {elapsed:5.1f}s (maxTimeout={max_timeout_ms/1000:.0f}s): "
              f"{type(exc).__name__}: {str(exc)[:120]}")


def main():
    if not FLARE:
        raise SystemExit("FLARESOLVERR_URL not set — run on the box.")
    print(f"FlareSolverr: {FLARE}\n")

    SD, ED = "2026-03-25", "2026-04-23"  # the failing 30d window

    # 1) SANITY — is FlareSolverr/FanGraphs up at all? (small, cheap batting dashboard, full season)
    probe("sanity: batting type=8 full-season", _base(stats="bat", type_id=8, month="0", pageitems="30"), 60000)

    # 2) Reproduce the failure (qual=0, date range, 60s)
    probe("repro: pit stuff+ daterange qual=0 60s", _base(startdate=SD, enddate=ED), 60000)

    # 3) Timeout lever — same query, 120s / 180s
    probe("timeout: daterange qual=0 120s", _base(startdate=SD, enddate=ED), 120000)
    probe("timeout: daterange qual=0 180s", _base(startdate=SD, enddate=ED), 180000)

    # 4) qual lever — same query, qual floor (fewer pitchers → less compute)
    probe("qual: daterange qual=20 60s", _base(startdate=SD, enddate=ED, qual="20"), 60000)
    probe("qual: daterange qual=50 60s", _base(startdate=SD, enddate=ED, qual="50"), 60000)

    # 5) date-range shape — full-season (no dates, month=0) qual=0; and month=0 WITH dates
    probe("shape: full-season month=0 qual=0 60s", _base(month="0"), 60000)
    probe("shape: daterange month=0 (not 1000) 60s", _base(startdate=SD, enddate=ED, month="0"), 60000)

    # 6) combined best-guess: qual floor + longer timeout
    probe("combo: daterange qual=20 120s", _base(startdate=SD, enddate=ED, qual="20"), 120000)

    print("\nRead the 200s: the cheapest variant that returns upstream=200 with rows>0 is the fix.")


if __name__ == "__main__":
    main()
