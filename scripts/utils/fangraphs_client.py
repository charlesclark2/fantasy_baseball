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
# MINOR-league statistical leaderboard (E7.7) — same param shape as the major board, different
# path segment. Enumerates EVERY minor leaguer (ranked or not) → the `fg_minor_id` population
# feed THE BOARD can't give (it only covers graded prospects). Rows carry `playerid` (the
# `sa`-prefixed minor id) + `xMLBAMID`. Endpoint verified via fungo::fetch_leaders(league='minor').
MINOR_LEADERBOARD_URL = "https://www.fangraphs.com/api/leaders/minor-league/data"
# THE BOARD — prospect rankings + scouting grades (E7.7). ONE JSON call returns the whole
# board (~1,300 prospects/season): future value (cFV), risk, ETA, org/overall rank, level,
# and — critically for the E8.0 join — both the FanGraphs id (`playerid` → fg_minor_id) AND
# the MLBAM id (`xMLBAMID`). Endpoint + param shape verified against the FanGraphs mobile-app
# path (github.com/hedgertronic/fungo::get_prospect_board, 2026-07) — do NOT re-derive.
PROSPECT_BOARD_URL = "https://www.fangraphs.com/api/prospects/board/data"

# FlareSolverr endpoint that solves the Cloudflare challenge (Epic FG).
FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "")
_CHALLENGE_MAX_TIMEOUT_MS = 60000
# FlareSolverr POST timeout must comfortably exceed maxTimeout (solve + fetch).
_FLARESOLVERR_POST_TIMEOUT_S = 180

_MAX_RETRIES = 3
_RETRY_DELAYS = [2, 4, 8]

# INC-26 (2026-07-02): the leaderboard endpoint 500s at FanGraphs' *origin* (not a
# Cloudflare/FlareSolverr clearance failure) when asked for one absurd page —
# `pageitems=2000000&qual=0`. A 500 means the request reached the origin, so the cure
# is to cap the page and paginate, not to re-solve the challenge. We request modest
# pages and walk `pagenum` until a short/empty/all-seen page, and — belt-and-braces —
# halve the page on any upstream 5xx and retry the same page (the "retry path").
_LEADERBOARD_PAGE_SIZE = 1000       # replaces pageitems=2000000; well above a season's pitcher count per page
_LEADERBOARD_MIN_PAGE_SIZE = 250    # 5xx-retry floor before we give up
_LEADERBOARD_MAX_PAGES = 60         # safety cap (60 * 250 = 15k rows) so a paginate-ignoring API can't loop forever


def _leaderboard_max_timeout_ms() -> int:
    """FlareSolverr maxTimeout for a leaderboard fetch. INC-26 follow-up: the qual=0 Stuff+
    leaderboard over a date range takes >60s to compute at FanGraphs' origin, so the default 60s
    solve window times out → FlareSolverr returns HTTP 500 (~61s elapsed). We give it more time.
    Env-tunable (FANGRAPHS_LEADERBOARD_MAX_TIMEOUT_MS) so the box can adjust without a redeploy."""
    try:
        return int(os.environ.get("FANGRAPHS_LEADERBOARD_MAX_TIMEOUT_MS", "120000"))
    except ValueError:
        return 120000

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


def _flaresolverr_get(url: str, params: dict, max_timeout_ms: int | None = None) -> tuple:
    """Fetch ``url?params`` THROUGH FlareSolverr; return ``(parsed_json, http_status)``.

    ``max_timeout_ms`` is FlareSolverr's browser solve+fetch budget (default 60s). A slow
    origin (the qual=0 leaderboard) needs a longer window — see ``_leaderboard_max_timeout_ms``.

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

    timeout_ms = int(max_timeout_ms or _CHALLENGE_MAX_TIMEOUT_MS)
    # The POST must outlast FlareSolverr's own solve+fetch budget (+30s slack).
    post_timeout_s = max(_FLARESOLVERR_POST_TIMEOUT_S, timeout_ms / 1000 + 30)
    full_url = f"{url}?{urlencode(params)}"
    payload = {"cmd": "request.get", "url": full_url, "maxTimeout": timeout_ms}
    log.info("Fetching via FlareSolverr (maxTimeout=%ds): %s", timeout_ms // 1000, url)
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = requests.post(FLARESOLVERR_URL, json=payload, timeout=post_timeout_s)
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


def _is_upstream_5xx(exc: Exception) -> bool:
    """True if an origin 5xx is anywhere in the exception chain (INC-26 retry trigger).

    ``_flaresolverr_get`` wraps the upstream-status error as the ``__cause__`` of its
    "All N attempts failed" error, so we walk the chain and match ``HTTP 5xx``.
    """
    seen = exc
    for _ in range(6):
        if seen is None:
            return False
        if re.search(r"HTTP 5\d\d", str(seen)):
            return True
        seen = seen.__cause__
    return False


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


def _board_max_timeout_ms() -> int:
    """FlareSolverr solve+fetch budget for a Board pull. One request returns the full
    ~1,300-prospect board, so a generous window (default 120s, env-tunable) keeps a slow
    origin from timing out — same lever as the leaderboard fetch."""
    try:
        return int(os.environ.get("FANGRAPHS_BOARD_MAX_TIMEOUT_MS", "120000"))
    except ValueError:
        return 120000


def fetch_prospects_board(
    season: int,
    draft: Optional[str] = None,
    board_type: Optional[str] = None,
    pos: Optional[str] = None,
    players: Optional[str] = None,
) -> dict:
    """Fetch THE BOARD (prospect rankings + scouting grades) for one season (E7.7).

    Routes THROUGH FlareSolverr like every other FanGraphs fetch — FanGraphs fronts the whole
    site with a Cloudflare JS challenge (`cf-mitigated: challenge`, HTTP 403 to any direct
    client), verified live 2026-07-27. One call returns the whole board.

    Args:
        season: board season year (e.g. 2026).
        draft: board slug; defaults to ``"<season>prospect"`` (the main prospect board).
            Other slugs select the draft / international boards (e.g. ``"2026mlb"``).
        board_type: optional board `type` filter (FanGraphs default when None).
        pos: optional position filter.
        players: optional comma-joined player-id filter.

    Returns the standardised dict shape used across this module: ``data`` is the list of
    per-prospect row dicts EXACTLY as FanGraphs produced them (raw casing preserved — the
    caller does tolerant, case-insensitive key extraction so a FanGraphs rename can never
    silently zero a column, per the column-name-reality discipline).
    """
    params = {
        "draft": draft or f"{season}prospect",
        "season": season,
        "type": board_type,
        "pos": pos,
        "players": players,
    }
    # Drop None-valued params — urlencode would otherwise send the literal string "None".
    params = {k: v for k, v in params.items() if v is not None}

    payload, status = _flaresolverr_get(
        PROSPECT_BOARD_URL, params, max_timeout_ms=_board_max_timeout_ms()
    )
    # The Board endpoint returns a bare JSON list; tolerate a {"data": [...]} wrapper too.
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data", payload.get("prospects", [payload]))
    else:
        rows = []
    log.info(
        "fetch_prospects_board: season=%d draft=%s → %d prospect row(s)",
        season, params["draft"], len(rows),
    )
    return {
        "data": rows,
        "source_endpoint": PROSPECT_BOARD_URL,
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
    qual: str | int = "0",
    page_size: Optional[int] = None,
) -> dict:
    """Fetch a FanGraphs major-league leaderboard snapshot (INC-26 paginated).

    Walks ``pagenum`` at a capped ``pageitems`` (default 1000) and concatenates the
    pages — the old single ``pageitems=2000000`` request 500s at FanGraphs' origin.
    Rows are de-duplicated by ``playerid`` so a pagination-ignoring API (returns the
    full set every page) terminates on the first all-seen page instead of looping.

    Args:
        stats: 'pit' for pitching, 'bat' for hitting
        type_id: FanGraphs column-set ID (36=Stuff+, 8=batting dashboard)
        season: calendar year
        startdate: ISO date string e.g. '2026-04-01'; defaults to March 1 of season
        enddate: ISO date string e.g. '2026-04-07'; defaults to November 1 of season
        qual: minimum PA/IP qualifier ('0' = every player; a small floor is another
            lever against a borderline origin 500, but changes which rows return —
            keep '0' for parity with the historical raws).
        page_size: rows per page (default 1000). Halved automatically on an upstream 5xx.
    """
    base_params = {
        "pos": "all",
        "stats": stats,
        "lg": "all",
        "qual": str(qual),
        "season": season,
        "season1": season,
        "startdate": startdate or f"{season}-03-01",
        "enddate": enddate or f"{season}-11-01",
        "month": "1000",
        "hand": "",
        "team": "0",
        "ind": "0",
        "rost": "0",
        "players": "",
        "type": type_id,
        "postseason": "",
        "sortdir": "default",
        "sortstat": "WAR",
    }
    out = _paginate_leaderboard(
        LEADERBOARD_URL, base_params,
        page_size=int(page_size or _LEADERBOARD_PAGE_SIZE),
        max_timeout_ms=_leaderboard_max_timeout_ms(),
        label=f"stats={stats} type={type_id} season={season}",
    )
    return out


_DEDUP_ID_KEYS = ("playerid", "minormasterid", "playerId".lower(), "upid")


def _row_dedup_id(row: dict) -> str | None:
    """Case-insensitive player id for cross-page de-dup, over a candidate key list. None when a
    row carries no id key (so the caller keeps it rather than collapsing an id-less page)."""
    lc = {str(k).lower(): v for k, v in row.items()}
    for k in _DEDUP_ID_KEYS:
        v = lc.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _paginate_leaderboard(
    url: str,
    base_params: dict,
    page_size: int,
    max_timeout_ms: int,
    label: str = "",
) -> dict:
    """Walk ``pagenum`` at a capped ``pageitems`` and concatenate the de-duplicated pages
    (shared by the major + minor leaderboard fetchers). The single ``pageitems=2000000``
    request 500s at FanGraphs' origin (INC-26); rows are de-duped by ``playerid`` so a
    pagination-ignoring API terminates on the first all-seen page, and an upstream 5xx halves
    the page and retries the SAME page. Returns the standardised ``{data, source_endpoint,
    request_params, http_status_code, load_id}`` dict."""
    all_rows: list = []
    seen_ids: set = set()
    load_id = str(uuid.uuid4())
    first_params: dict | None = None
    last_status = 0
    pagenum = 1
    pages_fetched = 0

    while pages_fetched < _LEADERBOARD_MAX_PAGES:
        params = dict(base_params, pageitems=str(page_size), pagenum=str(pagenum))
        if first_params is None:
            first_params = params
        try:
            payload, status = _flaresolverr_get(url, params, max_timeout_ms=max_timeout_ms)
        except FangraphsClientError as exc:
            # INC-26 retry path: a borderline page can still 500 at the origin → halve
            # the page and retry the SAME pagenum before giving up.
            if _is_upstream_5xx(exc) and page_size > _LEADERBOARD_MIN_PAGE_SIZE:
                page_size = max(_LEADERBOARD_MIN_PAGE_SIZE, page_size // 2)
                log.warning(
                    "Leaderboard page %d returned upstream 5xx; retrying at smaller page_size=%d",
                    pagenum, page_size,
                )
                continue
            raise

        last_status = status
        page_rows = payload.get("data", []) if isinstance(payload, dict) else (payload or [])
        pages_fetched += 1
        if not page_rows:
            break

        # De-dup across pages by player id. The id key varies by board (major: `playerid`;
        # minor/prospect: `minorMasterId`/`PlayerId`) — resolve case-insensitively over a
        # candidate list; a row with NO id key can't be de-duped, so keep it (never collapse
        # an id-less page to one row).
        new_rows = []
        for r in page_rows:
            rid = _row_dedup_id(r)
            if rid is not None and rid in seen_ids:
                continue
            if rid is not None:
                seen_ids.add(rid)
            new_rows.append(r)
        all_rows.extend(new_rows)

        # Last page (short) or the API ignored pagination (nothing new) → stop.
        if len(page_rows) < page_size or not new_rows:
            break
        pagenum += 1
    else:
        log.warning(
            "_paginate_leaderboard hit the %d-page cap (%s @ %s) — possible truncation",
            _LEADERBOARD_MAX_PAGES, label, url,
        )

    log.info(
        "_paginate_leaderboard: %s → %d rows (%d page(s), page_size=%d) @ %s",
        label, len(all_rows), pages_fetched, page_size, url,
    )
    return {
        "data": all_rows,
        "source_endpoint": url,
        "request_params": first_params,
        "http_status_code": last_status or 200,
        "load_id": load_id,
    }


def fetch_minor_leaderboard(
    stats: str,
    season: int,
    qual: str | int = "0",
    ind: str | int = "0",
    stat_type: int | str = 0,
    level: str | int = 0,
    lg: str = "",
    page_size: Optional[int] = None,
    url: Optional[str] = None,
    extra_params: Optional[dict] = None,
) -> dict:
    """Fetch the FanGraphs MINOR-league statistical leaderboard for a season (E7.7).

    THE reason this exists: THE BOARD only covers RANKED/graded prospects, but a deep dynasty
    roster is full of UNRANKED minor leaguers. This leaderboard enumerates EVERY minor leaguer
    with a stat line — so it is the population feed for `fg_minor_id` (rows carry the `sa`-prefixed
    minor id + xMLBAMID), the id coverage E7.4's xref + a deep-league draft board need. Routes
    through FlareSolverr like every FanGraphs fetch.

    ⚠️ The minor board takes a DIFFERENT param set than the major one (a major-style request with
    `season1`/`month`/`type=8` 404s at the origin — probed live 2026-07-27): it uses `seasonEnd`
    (not `season1`), `type=0`, and `level`/`org`/`splitTeam`. Because the exact contract is
    fragile, `url` + `extra_params` let a caller override any of it from a probe WITHOUT a code
    change (the ingest exposes `--endpoint`/`--extra-param`).

    Args:
        stats: 'bat' for hitting, 'pit' for pitching.
        season: calendar year (start == end for a single season).
        qual: PA/IP minimum ('0' = EVERYONE — the coverage default; 'y' = qualified only).
        ind: '0' = aggregate the season into one row per player; '1' = one row per split.
        stat_type: minor column-set id (0 = default minor set — NOT the major '8').
        level: minor level filter (0 = all levels).
        lg: league filter ('' = all).
        page_size: rows per page (default 1000); halved automatically on an upstream 5xx.
        url: override the endpoint (defaults to MINOR_LEADERBOARD_URL).
        extra_params: merged over the built params (probe-driven overrides).
    """
    base_params = {
        "age": "",
        "pos": "all",
        "stats": stats,
        "lg": lg,
        "qual": str(qual),
        "season": season,
        "seasonEnd": season,   # the minor board uses seasonEnd, NOT season1
        "level": str(level),
        "team": "",
        "org": "",
        "ind": str(ind),
        "splitTeam": "false",
        "players": "",
        "type": stat_type,
        "sortdir": "default",
        "sortstat": "",
    }
    if extra_params:
        base_params.update(extra_params)
    return _paginate_leaderboard(
        url or MINOR_LEADERBOARD_URL, base_params,
        page_size=int(page_size or _LEADERBOARD_PAGE_SIZE),
        max_timeout_ms=_leaderboard_max_timeout_ms(),
        label=f"MINOR stats={stats} season={season} qual={qual} ind={ind} type={stat_type}",
    )
