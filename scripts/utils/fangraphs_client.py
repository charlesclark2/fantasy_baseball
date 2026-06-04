"""
fangraphs_client.py
-------------------
Shared HTTP client for FanGraphs API endpoints used by all ingestion scripts.

FanGraphs sits behind a Cloudflare **managed JavaScript challenge**
(`cf-mitigated: challenge`). A TLS-fingerprint match (curl_cffi) is not enough —
the challenge JS must be executed — so every direct request returns HTTP 403.
We use FlareSolverr (a headless-browser challenge solver, run as a separate
service) to perform the request.

DESIGN — fetch THROUGH FlareSolverr (not cookie-replay):
We send the actual API GET to FlareSolverr (`cmd: request.get` with the full URL
+ query string) and parse the JSON back out of its rendered-HTML response.
FlareSolverr's browser performs the request from ITS OWN egress IP, with a TLS
fingerprint that matches its own Chrome, holding live Cloudflare clearance. This
process never touches fangraphs.com directly.

Why not harvest `cf_clearance` and replay it from here? Because cf_clearance is
bound to BOTH the egress IP and the user-agent/TLS fingerprint of the host that
solved it. When FlareSolverr and the agent run as **separate Railway services**
they have different egress IPs, so a replayed cookie is rejected (persistent 403
even though the solve succeeds); and a hardcoded curl_cffi `impersonate=` version
drifts from FlareSolverr's auto-updating Chrome, producing the same 403. Routing
the fetch through FlareSolverr makes both failure modes structurally impossible.
See Epic FG in the implementation guide.

Configuration:
  FLARESOLVERR_URL  -- FlareSolverr /v1 endpoint. Required for FanGraphs calls.
                       prod:  http://flaresolverr.railway.internal:8191/v1
                       local: http://localhost:8191/v1

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

import html
import json
import logging
import os
import re
import time
import uuid
from typing import Optional
from urllib.parse import urlencode

from curl_cffi import requests

log = logging.getLogger(__name__)

PROJECTIONS_URL = "https://www.fangraphs.com/api/projections/member"
LEADERBOARD_URL = "https://www.fangraphs.com/api/leaders/major-league/data"

# FlareSolverr endpoint that solves the Cloudflare challenge (Epic FG).
FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "")
_CHALLENGE_MAX_TIMEOUT_MS = 60000
# FlareSolverr POST timeout must comfortably exceed maxTimeout (solve + fetch).
_FLARESOLVERR_POST_TIMEOUT_S = 180

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]

# Retained for non-FanGraphs callers (e.g. ingest_savant_park_factors.py): Baseball
# Savant is NOT behind the Cloudflare JS challenge, so a plain Chrome-impersonating
# curl_cffi session suffices there. The FanGraphs path no longer uses this.
_session: requests.Session | None = None


class FangraphsClientError(Exception):
    pass


def _get_session() -> requests.Session:
    """A curl_cffi session with a current Chrome TLS fingerprint.

    NOT used by the FanGraphs fetch path (that goes through FlareSolverr). Kept
    for callers that hit non-challenged hosts (Baseball Savant park factors).
    """
    global _session
    if _session is None:
        _session = requests.Session(impersonate="chrome")
    return _session


def _extract_json(response_html: str):
    """Pull the JSON payload out of FlareSolverr's rendered-HTML response.

    Headless Chrome renders an ``application/json`` response as raw text inside a
    ``<pre>`` element, so the common case is ``<body><pre>{...}</pre></body>``.
    We try, in order: (1) the whole response as raw JSON, (2) the ``<pre>``
    contents (HTML-unescaped), (3) the outermost ``{...}`` / ``[...]`` substring.
    """
    text = response_html or ""
    stripped = text.strip()

    # (1) Already raw JSON.
    if stripped[:1] in "{[":
        try:
            return json.loads(stripped)
        except ValueError:
            pass

    # (2) JSON inside <pre>...</pre> (headless-Chrome JSON rendering).
    m = re.search(r"<pre[^>]*>(.*?)</pre>", text, re.DOTALL | re.IGNORECASE)
    if m:
        candidate = html.unescape(m.group(1)).strip()
        try:
            return json.loads(candidate)
        except ValueError:
            pass

    # (3) Outermost JSON container anywhere in the body.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        i, j = text.find(open_ch), text.rfind(close_ch)
        if 0 <= i < j:
            try:
                return json.loads(html.unescape(text[i:j + 1]))
            except ValueError:
                continue

    raise FangraphsClientError(
        "Could not extract JSON from FlareSolverr response "
        f"(status looked OK; first 200 chars: {text[:200]!r})"
    )


def _flaresolverr_get(url: str, params: dict) -> tuple:
    """Fetch ``url?params`` THROUGH FlareSolverr; return ``(parsed_json, http_status)``.

    FlareSolverr's headless browser issues the request from its own egress IP with
    a matching fingerprint and live Cloudflare clearance, so there is nothing to
    replay from this process — which is what makes the split-service deployment
    (FlareSolverr + agent on separate Railway services) work reliably.
    """
    if not FLARESOLVERR_URL:
        raise FangraphsClientError(
            "FanGraphs is behind a Cloudflare JS challenge and FLARESOLVERR_URL is "
            "not configured. Point it at a FlareSolverr instance "
            "(e.g. http://flaresolverr.railway.internal:8191/v1). See Epic FG."
        )

    full_url = f"{url}?{urlencode(params)}"
    payload = {"cmd": "request.get", "url": full_url, "maxTimeout": _CHALLENGE_MAX_TIMEOUT_MS}
    log.info("Fetching via FlareSolverr: %s", url)
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.post(FLARESOLVERR_URL, json=payload, timeout=_FLARESOLVERR_POST_TIMEOUT_S)
            r.raise_for_status()
            data = r.json()

            if data.get("status") != "ok":
                raise FangraphsClientError(
                    f"FlareSolverr did not solve the request: {data.get('message')}"
                )

            sol = data.get("solution", {}) or {}
            http_status = int(sol.get("status") or 0)
            if http_status != 200:
                # Cloudflare/FanGraphs returned non-200 to FlareSolverr's browser
                # itself — re-solve on the next attempt (fresh browser nav).
                raise FangraphsClientError(
                    f"FlareSolverr fetched {full_url} but upstream returned HTTP {http_status}"
                )

            parsed = _extract_json(sol.get("response", ""))
            return parsed, http_status
        except Exception as exc:  # noqa: BLE001
            log.warning("Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, full_url, exc)
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])

    raise FangraphsClientError(f"All {_MAX_RETRIES} attempts failed for {full_url}") from last_exc


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
    payload, status = _flaresolverr_get(PROJECTIONS_URL, params)
    rows = payload if isinstance(payload, list) else payload.get("data", [payload])
    log.info(
        "fetch_projections: type=%s stats=%s season=%d → %d rows",
        proj_type, stats, season, len(rows),
    )
    return {
        "data": rows,
        "source_endpoint": PROJECTIONS_URL,
        "request_params": params,
        "http_status_code": status,
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
    payload, status = _flaresolverr_get(LEADERBOARD_URL, params)
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
        "http_status_code": status,
        "load_id": str(uuid.uuid4()),
    }
