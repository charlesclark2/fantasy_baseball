"""
fangraphs_client.py
-------------------
Shared HTTP client for FanGraphs API endpoints used by all ingestion scripts.

Uses curl_cffi to impersonate a Chrome TLS fingerprint, which is required to
pass Cloudflare's bot detection on fangraphs.com.

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
import time
import uuid
from typing import Optional

from curl_cffi import requests

log = logging.getLogger(__name__)

PROJECTIONS_URL = "https://www.fangraphs.com/api/projections/member"
LEADERBOARD_URL = "https://www.fangraphs.com/api/leaders/major-league/data"

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]

# Shared session so cookies obtained during warmup persist across all calls
# in the same process run.
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        # impersonate="chrome" makes curl_cffi use Chrome's TLS fingerprint
        # (JA3/JA4 hash), which is what Cloudflare actually checks.
        _session = requests.Session(impersonate="chrome")
    return _session


class FangraphsClientError(Exception):
    pass


def _get_with_retry(url: str, params: dict, extra_headers: dict | None = None) -> requests.Response:
    sess = _get_session()
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = sess.get(url, params=params, headers=extra_headers or {}, timeout=60)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            log.warning(
                "Attempt %d/%d failed for %s: %s", attempt, _MAX_RETRIES, url, exc
            )
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAYS[attempt - 1])
    raise FangraphsClientError(
        f"All {_MAX_RETRIES} attempts failed for {url}"
    ) from last_exc


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
