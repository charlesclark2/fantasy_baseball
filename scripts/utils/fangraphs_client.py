"""
fangraphs_client.py
-------------------
Shared HTTP client for FanGraphs API endpoints used by all ingestion scripts.

FanGraphs sits behind a Cloudflare **managed JavaScript challenge**
(`cf-mitigated: challenge`). curl_cffi can match Chrome's TLS fingerprint but
cannot execute the challenge JS, so every direct request returns HTTP 403.
To get through, we use FlareSolverr (a headless-browser challenge solver, run as
a separate service) to solve the challenge once, harvest its `cf_clearance`
cookie + user-agent, and replay BOTH on fast curl_cffi requests for the actual
JSON API calls. See Epic FG in the implementation guide.

Configuration:
  FLARESOLVERR_URL  -- FlareSolverr /v1 endpoint. Required for FanGraphs calls.
                       prod:  http://flaresolverr.railway.internal:8191/v1
                       local: http://localhost:8191/v1

IMPORTANT (IP binding): cf_clearance is bound to the egress IP of the host that
solved it AND to the returned user-agent. The process replaying the cookie must
share FlareSolverr's egress IP (on Railway: same project/region). On a 403 the
client re-solves once automatically; a persistent 403 after re-solve almost
always means an IP mismatch between the agent and FlareSolverr.

Two public functions:
  fetch_projections(proj_type, stats, season) -- ZiPS / Steamer projections
  fetch_leaderboard(stats, type_id, season, startdate, enddate) -- any leaderboard

Both return a standardised dict:
  {
    "data":             list[dict],   # one dict per player row
    "source_endpoint":  str,
    "request_params":   dict,
    "http_status_code": int,
    "load_id":          str,          # UUID shared across all rows in one fetch
  }

Historical ZiPS type conventions (pass as proj_type):
  "rzips"        -- current-season rolling ZiPS
  "zips_2025"    -- historical season-specific ZiPS (any year 2015–present)
  "steamer"      -- current-season Steamer
  "steamer_2025" -- historical Steamer

Leaderboard type_id values used in this project:
  36  -- Stuff+ / Location+ / Pitching+ (pitching, stats='pit')
  8   -- Dashboard batting (wRC+, OBP, SLG, K%, BB%, WAR)
"""

import logging
import os
import time
import uuid
from typing import Optional

from curl_cffi import requests

log = logging.getLogger(__name__)

PROJECTIONS_URL = "https://www.fangraphs.com/api/projections/member"
LEADERBOARD_URL = "https://www.fangraphs.com/api/leaders/major-league/data"

# FlareSolverr endpoint that solves the Cloudflare challenge (Epic FG).
FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "")
# Any fangraphs.com page works to mint clearance — cf_clearance is set zone-wide.
_CHALLENGE_WARMUP_URL = "https://www.fangraphs.com/leaders/major-league"
_CHALLENGE_MAX_TIMEOUT_MS = 60000

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]

# Shared session so cookies/connection pooling persist across calls in one run.
_session: requests.Session | None = None
# Harvested Cloudflare clearance: {"cookies": {name: value}, "user_agent": str}
_clearance: dict | None = None


class FangraphsClientError(Exception):
    pass


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        # impersonate="chrome124" makes curl_cffi use a recent Chrome TLS
        # fingerprint (JA3/JA4), aligned with the user-agent FlareSolverr returns.
        _session = requests.Session(impersonate="chrome124")
    return _session


def _solve_challenge(url: str = _CHALLENGE_WARMUP_URL) -> dict:
    """Solve the Cloudflare challenge via FlareSolverr; return a clearance dict.

    Returns {"cookies": {name: value}, "user_agent": str}.
    """
    if not FLARESOLVERR_URL:
        raise FangraphsClientError(
            "FanGraphs is behind a Cloudflare JS challenge and FLARESOLVERR_URL is "
            "not configured. Point it at a FlareSolverr instance "
            "(e.g. http://flaresolverr.railway.internal:8191/v1). See Epic FG."
        )
    payload = {"cmd": "request.get", "url": url, "maxTimeout": _CHALLENGE_MAX_TIMEOUT_MS}
    log.info("Solving Cloudflare challenge via FlareSolverr (%s)", url)
    try:
        r = requests.post(FLARESOLVERR_URL, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        raise FangraphsClientError(f"FlareSolverr request failed: {exc}") from exc

    if data.get("status") != "ok":
        raise FangraphsClientError(
            f"FlareSolverr could not solve the challenge: {data.get('message')}"
        )
    sol = data.get("solution", {})
    cookies = {c["name"]: c["value"] for c in sol.get("cookies", [])}
    if "cf_clearance" not in cookies:
        log.warning("FlareSolverr solution did not include a cf_clearance cookie "
                    "(challenge may not have been required, or solve incomplete)")
    log.info("Cloudflare clearance obtained (%d cookies)", len(cookies))
    return {"cookies": cookies, "user_agent": sol.get("userAgent", "")}


def _ensure_clearance(force: bool = False) -> dict:
    global _clearance
    if force or _clearance is None:
        _clearance = _solve_challenge()
    return _clearance


def _get_with_retry(url: str, params: dict, extra_headers: dict | None = None) -> requests.Response:
    sess = _get_session()
    clearance = _ensure_clearance()
    last_exc: Exception | None = None

    def _do_get(clr: dict) -> requests.Response:
        headers = dict(extra_headers or {})
        headers["User-Agent"] = clr["user_agent"]
        return sess.get(url, params=params, headers=headers,
                        cookies=clr["cookies"], timeout=60)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = _do_get(clearance)
            if resp.status_code == 403:
                # Clearance expired (or IP mismatch). Re-solve once, then retry.
                log.warning("403 from %s — re-solving Cloudflare challenge", url)
                clearance = _ensure_clearance(force=True)
                resp = _do_get(clearance)
            resp.raise_for_status()
            return resp
        except Exception as exc:  # noqa: BLE001
            log.warning("Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, url, exc)
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])
    raise FangraphsClientError(f"All {_MAX_RETRIES} attempts failed for {url}") from last_exc


def fetch_projections(proj_type: str, stats: str, season: int) -> dict:
    """Fetch ZiPS / Steamer projections from the FanGraphs projections endpoint.

    Args:
        proj_type: FanGraphs type string e.g. 'rzips', 'steamer', 'zips_2024'
        stats: 'pit' for pitching, 'bat' for hitting
        season: calendar year of the projection
    """
    params = {
        "type": proj_type,
        "stats": stats,
        "pos": "all",
        "team": "0",
        "players": "0",
        "lg": "all",
        "z": int(time.time()),
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.fangraphs.com/projections",
    }
    resp = _get_with_retry(PROJECTIONS_URL, params, extra_headers=headers)
    payload = resp.json()
    rows = payload if isinstance(payload, list) else payload.get("data", [payload])
    log.info(
        "fetch_projections: type=%s stats=%s season=%d → %d rows",
        proj_type, stats, season, len(rows),
    )
    return {
        "data": rows,
        "source_endpoint": PROJECTIONS_URL,
        "request_params": params,
        "http_status_code": resp.status_code,
        "load_id": str(uuid.uuid4()),
    }


def fetch_leaderboard(
    stats: str,
    type_id: int,
    season: int,
    startdate: Optional[str] = None,
    enddate: Optional[str] = None,
) -> dict:
    """Fetch a FanGraphs major-league leaderboard snapshot.

    Args:
        stats: 'pit' for pitching, 'bat' for hitting
        type_id: FanGraphs column-set ID (36=Stuff+, 8=batting dashboard)
        season: calendar year
        startdate: ISO date string e.g. '2026-04-01'; defaults to March 1 of season
        enddate: ISO date string e.g. '2026-04-07'; defaults to November 1 of season
    """
    params = {
        "pos": "all",
        "stats": stats,
        "lg": "all",
        "qual": "0",
        "season": season,
        "season1": season,
        "startdate": startdate or f"{season}-03-01",
        "enddate": enddate or f"{season}-11-01",
        "month": "1000",
        "hand": "",
        "team": "0",
        "pageitems": "2000000",
        "pagenum": "1",
        "ind": "0",
        "rost": "0",
        "players": "",
        "type": type_id,
        "postseason": "",
        "sortdir": "default",
        "sortstat": "WAR",
    }
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.fangraphs.com/leaders/major-league",
    }
    resp = _get_with_retry(LEADERBOARD_URL, params, extra_headers=headers)
    payload = resp.json()
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    log.info(
        "fetch_leaderboard: stats=%s type=%d season=%d %s→%s → %d rows",
        stats, type_id, season,
        startdate or "(full)", enddate or "(full)",
        len(rows),
    )
    return {
        "data": rows,
        "source_endpoint": LEADERBOARD_URL,
        "request_params": params,
        "http_status_code": resp.status_code,
        "load_id": str(uuid.uuid4()),
    }
