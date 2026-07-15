"""cfbd_client.py  (NCAAF-P0.2 lean lakehouse scaffold)
=========================================================
A thin, landmine-hardened HTTP client for the CollegeFootballData (CFBD) v2 API.

⚠️ THE P0.1 LANDMINE THIS FILE EXISTS TO PREVENT (ncaaf_data_inventory.md §1):
  A WRONG CFBD PATH RETURNS **HTTP 200 with the Swagger HTML page**, not a 404. The
  v1-style singular paths (`/play/stats`, `/play/types`) silently serve an API-docs
  bundle. A naive ingest that only checks `status_code == 200` would WRITE AN HTML PAGE
  AS DATA. ⇒ every fetch here asserts BOTH `Content-Type: application/json` AND that the
  body parses to a list/dict — a 200 alone is NOT a success signal. `get()` raises
  `CFBDContentError` on an HTML/non-JSON body so a bad path fails LOUD at ingest, never
  silently downstream. v2 paths are PLURAL (`/plays/stats`, `/plays/types`).

Other P0.1 facts baked in as guardrails (so P0.2+ can't rediscover them):
  • `/plays/stats` is hard-capped at 2,000 rows/response ⇒ MUST be pulled per `gameId`
    (`iter_play_stats_by_game`). `/plays` REQUIRES `week` (`get_plays` enforces it).
  • `/roster`, `/player/usage`, `/stats/player/season`, `/ppa/players/season`,
    `/recruiting/players`, `/player/returning` all accept YEAR-ONLY — do NOT loop 136
    teams (a 136× budget trap). These are 1 call/season.
  • `/game/box/advanced` takes `id=`, NOT `gameId=`.
  • Tier gating is server-side: `/live/plays` → 401 "requires Patreon Tier 2+". The
    backfill (`/plays/stats` per game, ~15.8k calls) needs the Tier-3 key (§6) — the
    free tier is 1,000 calls/mo. `X-Calllimit-Remaining` is surfaced on every response
    (`last_calls_remaining`) so a run can watch the budget.

Auth: `CFBD_API_KEY` (Bearer). Operator provisions the key — never entered in code. No
secrets are logged. Uses `requests` (already a transitive dep; listed in requirements).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

CFBD_BASE = "https://api.collegefootballdata.com"

# The 2,000-row hard cap on /plays/stats (observed live 2026-07-13, P0.1 §1). If a single
# response comes back at exactly this many rows the pull was truncated → we pull per gameId,
# never per week, so this is a tripwire assertion, not a paging cursor.
PLAY_STATS_ROW_CAP = 2000


class CFBDError(RuntimeError):
    """Base for CFBD client failures (auth, tier-gate, transport)."""


class CFBDContentError(CFBDError):
    """A 200 response whose body is NOT parseable JSON — the Swagger-HTML landmine.

    This is the single most important failure mode: a wrong (v1/singular) path returns
    200 text/html, so we raise HERE rather than let an HTML string be written as data.
    """


class CFBDAuthError(CFBDError):
    """401/403 — bad key or a Patreon-tier-gated endpoint (e.g. /live/plays needs Tier 2+)."""


def _api_key(explicit: str | None = None) -> str:
    key = explicit or os.environ.get("CFBD_API_KEY")
    if not key:
        raise CFBDAuthError(
            "CFBD_API_KEY is not set (operator provisions it; free tier = 1,000 calls/mo, "
            "buy Patreon Tier 3 for the backfill — see ncaaf_data_inventory.md §6)."
        )
    return key


class CFBDClient:
    """A landmine-hardened CFBD v2 client.

    Every path goes through `get()`, which enforces the JSON-content-type guard. The
    typed helpers below encode the P0.1 per-endpoint call-shape rules (which params are
    required, which accept year-only, which must loop per game) so callers can't get them
    wrong.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = CFBD_BASE,
        timeout: float = 30.0,
        max_retries: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = session or requests.Session()
        self._session.headers.update(
            {"Authorization": f"Bearer {_api_key(api_key)}", "Accept": "application/json"}
        )
        # Surfaced from X-Calllimit-Remaining on the latest response (None until first call).
        self.last_calls_remaining: int | None = None

    # ── the ONE choke point every fetch flows through ──────────────────────────────────
    def get(self, path: str, params: dict[str, Any] | None = None) -> list | dict:
        """GET a CFBD path, returning parsed JSON. Raises on the HTML-page landmine.

        A 200 is NOT trusted on its own: the response Content-Type must be JSON AND the
        body must parse. A wrong/singular path (the Swagger-HTML bundle) or an HTML error
        page therefore raises CFBDContentError instead of returning an HTML string.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:  # transport error → backoff+retry
                last_exc = exc
                time.sleep(min(2 ** attempt, 8))
                continue

            # Surface the free-tier budget meter (case-insensitive; header is X-Calllimit-Remaining).
            rem = resp.headers.get("X-Calllimit-Remaining") or resp.headers.get("x-calllimit-remaining")
            if rem is not None:
                try:
                    self.last_calls_remaining = int(rem)
                except ValueError:
                    pass

            if resp.status_code in (401, 403):
                raise CFBDAuthError(
                    f"CFBD {resp.status_code} on {path} — bad key or a Patreon-tier-gated "
                    f"endpoint (e.g. /live/plays needs Tier 2+). Body: {resp.text[:200]!r}"
                )
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                # rate-limited / server error → exponential backoff and retry
                last_exc = CFBDError(f"CFBD {resp.status_code} on {path}")
                time.sleep(min(2 ** attempt, 8))
                continue
            if resp.status_code == 400:
                # a validation error (e.g. /plays without week) — do NOT retry, surface it
                raise CFBDError(f"CFBD 400 Validation on {path} params={params}: {resp.text[:200]!r}")
            resp.raise_for_status()

            # 🧨 THE LANDMINE GUARD: a 200 is not enough — the body must be JSON.
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" not in ctype.lower():
                raise CFBDContentError(
                    f"CFBD {path} returned 200 but Content-Type={ctype!r} (not JSON) — this is "
                    f"the wrong-path Swagger-HTML landmine (P0.1 §1). Use the PLURAL v2 path "
                    f"(e.g. /plays/stats, not /play/stats). Body starts: {resp.text[:120]!r}"
                )
            try:
                data = resp.json()
            except ValueError as exc:
                raise CFBDContentError(
                    f"CFBD {path} returned 200 with an unparseable body (the HTML landmine): "
                    f"{resp.text[:120]!r}"
                ) from exc
            if not isinstance(data, (list, dict)):
                raise CFBDContentError(
                    f"CFBD {path} parsed to {type(data).__name__}, expected list/dict"
                )
            return data

        raise CFBDError(f"CFBD {path} failed after {self.max_retries} attempts: {last_exc}")

    # ── week-grained endpoints (a per-week loop is natural) ─────────────────────────────
    def get_games(self, year: int, week: int | None = None, *, season_type: str = "both") -> list[dict]:
        params: dict[str, Any] = {"year": year, "seasonType": season_type}
        if week is not None:
            params["week"] = week
        return self.get("/games", params)  # type: ignore[return-value]

    def get_plays(self, year: int, week: int, *, season_type: str = "regular") -> list[dict]:
        """/plays REQUIRES `week` (400 Validation Failed: week otherwise — P0.1 §1)."""
        if week is None:
            raise ValueError("/plays requires a week (CFBD 400 Validation Failed: week)")
        return self.get("/plays", {"year": year, "week": week, "seasonType": season_type})  # type: ignore[return-value]

    def get_game_team_stats(self, year: int, week: int | None = None) -> list[dict]:
        params: dict[str, Any] = {"year": year}
        if week is not None:
            params["week"] = week
        return self.get("/games/teams", params)  # type: ignore[return-value]

    def get_game_player_stats(self, year: int, week: int | None = None) -> list[dict]:
        params: dict[str, Any] = {"year": year}
        if week is not None:
            params["week"] = week
        return self.get("/games/players", params)  # type: ignore[return-value]

    def get_drives(self, year: int, week: int | None = None, *, season_type: str = "regular") -> list[dict]:
        params: dict[str, Any] = {"year": year, "seasonType": season_type}
        if week is not None:
            params["week"] = week
        return self.get("/drives", params)  # type: ignore[return-value]

    def get_box_advanced(self, game_id: int) -> dict:
        """/game/box/advanced takes `id=`, NOT `gameId=` (P0.1 §1, 400 Validation: id)."""
        return self.get("/game/box/advanced", {"id": game_id})  # type: ignore[return-value]

    # ── /plays/stats: the 2,000-row-capped, per-gameId endpoint (the dominant cost) ─────
    def get_play_stats_by_game(self, game_id: int) -> list[dict]:
        """One /plays/stats pull for a single game (the ONLY safe grain — 2,000-row cap).

        Asserts the response did NOT hit the cap (a game is ~218 rows; hitting 2,000 would
        mean the grain silently truncated — the P0.1 landmine that forces per-game pulls).
        """
        rows = self.get("/plays/stats", {"gameId": game_id})
        if isinstance(rows, list) and len(rows) >= PLAY_STATS_ROW_CAP:
            raise CFBDError(
                f"/plays/stats gameId={game_id} returned {len(rows)} rows (≥ the {PLAY_STATS_ROW_CAP} "
                f"cap) — pull is truncated. This endpoint MUST be pulled per game (it is)."
            )
        return rows  # type: ignore[return-value]

    def iter_play_stats_by_game(self, game_ids) -> Iterator[dict]:
        """Yield every /plays/stats row across a list of gameIds (~1 call/game). This is the
        target-share source (statType='Target') and the single biggest driver of the call
        budget (~960 calls/season — ncaaf_data_inventory.md §6)."""
        for gid in game_ids:
            for row in self.get_play_stats_by_game(gid):
                yield row

    # ── year-only endpoints (1 call/season — do NOT loop teams; the 136× trap) ──────────
    def get_year_only(self, path: str, year: int, **extra: Any) -> list[dict]:
        """Fetch a YEAR-ONLY endpoint (/roster, /player/usage, /stats/player/season,
        /ppa/players/season, /recruiting/players, /player/returning, /talent, …).
        These take year with NO team param — one call covers the whole season (P0.1 §1)."""
        return self.get(path, {"year": year, **extra})  # type: ignore[return-value]
