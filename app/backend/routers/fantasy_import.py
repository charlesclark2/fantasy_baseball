"""fantasy_import.py — platform league import (NF-C0).

The CONVENIENCE layer over NF-C0b's manual editor. An import lands in the SAME `fantasy_leagues`
store, as the SAME `LeagueConfig` object, read by the SAME `/fantasy/leagues` endpoints — so every
downstream surface is unable to tell an imported league from a typed-in one, and a user is never
blocked when a platform cannot be reached (they fall back to the floor, which already ships).

🚨 THE HARD RED LINE. No endpoint here accepts, stores, or replays a platform PASSWORD. Sleeper
needs no credential at all (public read API); Yahoo goes through Yahoo's own OAuth consent screen
and we keep only an encrypted, revocable, read-scoped grant. ESPN is USER-MEDIATED: the user makes
the request in their own signed-in browser and pastes the RESPONSE BODY — the server never calls
ESPN and never sees a cookie (a body structurally cannot carry `espn_s2`, which is an HTTP cookie).
We still refuse a paste that contains credential material, because a user can paste the wrong
artifact — DevTools' "Copy as cURL" embeds the whole `Cookie:` header. ESPN's automated
private-league path remains refused: it is the same line CBS was declined on at E8.2a. Full
reasoning, including why the paste flow is categorically different: `docs/nf_c0_espn_access_probe.md`.

🔒 ENTITLEMENT (⭐ WIDENED AT G100-C1, 2026-08-08). Every route requires
`require_personalized_league_access` — the caller's personalization QUOTA
(`entitlement.personalized_league_quota(...) > 0`), which is one for any signed-in free account and
the storage cap for a subscriber. It was `require_fantasy_beta_access` (`admin` + `fantasy_comp`),
matching NF-C0b's editor; G100-C1 grants a free account ONE personalized league, and import is one
of the two ways to configure it, so gating it on a group list would have left the free tier with
only the manual editor. The COUNT is enforced where a league is SAVED (`POST /fantasy/leagues`),
not here — import produces a config to save, and a preview writes nothing.

These WRITE a user's league configuration, so the server-side gate is the real one; hiding the nav
item stops nobody from POSTing a config straight to the API.

⚠️ THE ONE UNAUTHENTICATED ROUTE, AND WHY IT IS SAFE. `GET /fantasy/import/yahoo/callback` is
entered by the USER'S BROWSER being redirected back from Yahoo, so it carries no Authorization
header and CANNOT sit behind the bearer-token gate. Its authentication is the signed `state`
parameter: HMAC-SHA256 under a server-side key, carrying the user id and an issue time, verified in
`yahoo_oauth.verify_state`. That is what binds the returning grant to the account that started the
flow — without it, anyone could complete a consent round-trip and graft their Yahoo account onto
another user's Credence account. It is mounted on a separate router precisely so the exemption is
one visible, single-purpose route rather than a hole in the gate.
"""

from __future__ import annotations

import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.backend.dependencies import require_personalized_league_access
from app.backend.services import dynamo, fantasy_import_telemetry
from app.backend.services.platform_import import PLATFORMS, espn, sleeper, yahoo, yahoo_oauth
from app.backend.services.platform_import.http import RATE_LIMIT_STATUSES, PlatformHTTPError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fantasy/import", tags=["fantasy"])
# See the module docstring: the OAuth callback cannot carry a bearer token.
public_router = APIRouter(prefix="/fantasy/import", tags=["fantasy"])

# Where the callback sends the browser once the grant is stored. The frontend route reads the
# `yahoo` query flag and either continues the import or shows the failure.
FRONTEND_RETURN_URL = os.getenv(
    "FANTASY_IMPORT_RETURN_URL", "https://www.credencesports.com/fantasy/import"
)

_DEFAULT_SEASON = os.getenv("NFL_FANTASY_SEASON", "2026")


class SleeperUserRequest(BaseModel):
    # Named `username` for backwards compatibility, but it accepts a username, a league ID or a
    # user ID — see `sleeper.resolve_target`. The league ID is the one people actually have to
    # hand (it is in the league's URL), so requiring a username was a self-inflicted dead end.
    username: str = Field(min_length=1, max_length=64)
    season: str = Field(default=_DEFAULT_SEASON, min_length=4, max_length=4)


class PreviewRequest(BaseModel):
    league_id: str = Field(min_length=1, max_length=64)
    include_draft: bool = True


class CapturedTermTelemetry(BaseModel):
    """One scoring term the league scores that our board could not apply.

    Deliberately narrow: a key + its point value + its verdict. There is no field here for a user
    id, a team name, or anything roster-shaped — see the module docstring on
    `fantasy_import_telemetry` for why that is a property of the SCHEMA, not just of intent.
    """

    key: str = Field(min_length=1, max_length=120)
    weight: float = 0.0
    verdict: str = "captured"


class ImportTelemetryRequest(BaseModel):
    platform: str = Field(min_length=1, max_length=32)
    season: str | None = None
    terms: list[CapturedTermTelemetry] = Field(default_factory=list, max_length=200)


def _handle_platform_error(e: Exception) -> HTTPException:
    """Map an adapter failure onto an HONEST status code.

    The distinction that matters: a user's typo (422) must never be reported as a platform outage
    (502), and vice versa. Getting this wrong sends a user to check Sleeper's status page when they
    actually mistyped their username — the E9.26b "a swallowed error reads as an outage" lesson,
    facing outward.
    """
    if isinstance(e, (sleeper.SleeperInputError, yahoo.YahooInputError, espn.EspnInputError)):
        # `EspnCredentialPasteError` is a subclass and lands here too: a 422 with an actionable
        # message. It must NOT reach the `logger.exception` fallback below — that would write the
        # offending paste into CloudWatch, which is the one place a stray cookie must never go.
        return HTTPException(status_code=422, detail=str(e))
    if isinstance(e, yahoo_oauth.YahooNotConfigured):
        return HTTPException(status_code=503, detail=str(e))
    if isinstance(e, yahoo_oauth.YahooAuthError):
        return HTTPException(status_code=401, detail=str(e))
    if isinstance(e, PlatformHTTPError):
        if e.status == 404:
            return HTTPException(status_code=404, detail="That league could not be found.")
        if e.status == 401:
            return HTTPException(
                status_code=401, detail="Your connection to that platform is no longer authorized."
            )
        if e.status in RATE_LIMIT_STATUSES:
            # ⚠️ `in`, not `== 429`: Yahoo throttles with HTTP **999** (measured live 2026-08-19),
            # which used to fall through to the 502 below and told the user the platform was
            # unreachable when it was simply asking us to slow down.
            return HTTPException(
                status_code=429, detail="That platform is rate-limiting us. Try again shortly."
            )
        return HTTPException(status_code=502, detail=f"The platform could not be reached: {e}")
    logger.exception("unexpected fantasy import failure")
    return HTTPException(status_code=500, detail="The import failed unexpectedly.")


# ── platform catalog ──────────────────────────────────────────────────────────────────────────────


@router.get("/platforms")
def list_platforms(user_id: str = Depends(require_personalized_league_access)):
    """Which platforms can be imported RIGHT NOW, and whether the user is already connected.

    `available` is the static capability; `configured` is the runtime truth for an OAuth platform
    whose developer app may not be provisioned yet. Reporting them separately is what lets the UI
    say "Yahoo import is coming, the app registration is pending" instead of hiding the option or
    offering a button that 500s.
    """
    out = []
    for platform in PLATFORMS.values():
        entry = dict(platform)
        if platform["auth"] == "oauth":
            # `configured` is the gate the UI reads: OFFER this platform or say "coming soon".
            # `credentials_present` is a DIAGNOSTIC — it distinguishes "the operator hasn't written
            # the SSM parameters" from "the parameters are there but the platform hasn't approved
            # us yet", which otherwise look identical from outside and would send someone
            # re-running a provisioning step that already succeeded. Boolean only, no secret.
            enabled = yahoo_oauth.is_enabled()
            entry["configured"] = enabled
            entry["credentials_present"] = yahoo_oauth.is_configured()
            entry["connected"] = bool(
                enabled and dynamo.get_platform_token(user_id, platform["id"])
            )
            entry["attribution"] = yahoo.ATTRIBUTION
            entry["attribution_url"] = yahoo.ATTRIBUTION_URL
        else:
            entry["configured"] = True
            entry["connected"] = False
        out.append(entry)
    return out


# ── Sleeper (public read API — no credential of any kind) ────────────────────────────────────────


@router.post("/sleeper/leagues")
def sleeper_leagues(payload: SleeperUserRequest, user_id: str = Depends(require_personalized_league_access)):
    """Resolve whatever identifier the user has — username, league ID or user ID.

    Returns `{"kind": "league", "league": {...}}` when the value WAS a league (the caller skips the
    picker and previews it directly), or `{"kind": "user", "user": ..., "leagues": [...]}`.
    """
    try:
        resolved = sleeper.resolve_target(payload.username, payload.season)
    except Exception as e:  # noqa: BLE001 - mapped to an honest status below
        raise _handle_platform_error(e) from e
    return {"season": payload.season, **resolved}


@router.post("/sleeper/preview")
def sleeper_preview(payload: PreviewRequest, user_id: str = Depends(require_personalized_league_access)):
    """Read a Sleeper league WITHOUT saving it.

    Preview-then-save is deliberate: the response carries the coverage-relevant facts (which of the
    league's scoring terms we could not map, what was collapsed, which roster slots we do not rank)
    so the user AGREES to an honest translation before it becomes their league — rather than
    discovering after the fact that a rule silently did nothing.
    """
    try:
        return sleeper.import_league(payload.league_id, include_draft=payload.include_draft).to_dict()
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e


# ── ESPN (user-mediated paste — this server never calls ESPN) ────────────────────────────────────


class EspnReadUrlRequest(BaseModel):
    league_id: str = Field(min_length=1, max_length=24)
    season: str = Field(default=_DEFAULT_SEASON, min_length=4, max_length=4)


class EspnPasteRequest(BaseModel):
    # ⚠️ Deliberately NOT `Field(max_length=...)`: pydantic would reject an oversized paste with its
    # own validation error, whose `detail` is a LIST of objects that `apiFetch` cannot surface (see
    # frontend/lib/api.ts). The adapter's own size check returns a plain, actionable string instead.
    payload: str = Field(min_length=1)
    season: str | None = None


@router.post("/espn/read-url")
def espn_read_url(payload: EspnReadUrlRequest, user_id: str = Depends(require_personalized_league_access)):
    """Build the link the USER opens themselves. Nothing here fetches it.

    We construct it server-side so the user never has to assemble a URL by hand, and so the league
    id is format-checked before it is rendered into a link.
    """
    try:
        return {"url": espn.build_read_url(payload.league_id, int(payload.season))}
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e


@router.post("/espn/preview")
def espn_preview(payload: EspnPasteRequest, user_id: str = Depends(require_personalized_league_access)):
    """Parse a pasted ESPN settings response WITHOUT saving it.

    🔒 The pasted body is treated as hostile input and is NEVER logged — not on the happy path and
    not on failure. `_handle_platform_error` maps the adapter's own errors before the
    `logger.exception` fallback can see them, and nothing here interpolates `payload.payload` into
    a log line or an error message.
    """
    try:
        league = espn.parse_settings_payload(
            payload.payload, season=int(payload.season) if payload.season else None
        )
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e
    return league.to_dict()


# ── Yahoo (official OAuth2, read scope) ──────────────────────────────────────────────────────────


def _require_yahoo_enabled() -> None:
    """Server-side enforcement of the availability gate.

    Hiding the button is not a gate — an entitled caller can POST straight to the API, complete a
    consent round-trip, and be left holding a Yahoo grant that buys them nothing until approval
    lands. Every Yahoo route calls this so "coming soon" is true of the API, not just of the UI.
    """
    if not yahoo_oauth.is_enabled():
        raise yahoo_oauth.YahooNotConfigured(
            "Yahoo import is not available yet — we are waiting on Yahoo to approve our "
            "application for access to their fantasy data."
        )


def _access_token(user_id: str) -> str:
    """A usable Yahoo access token for this user, refreshing it when it has aged out.

    The refresh token is decrypted here and NOWHERE else in the request path; the refreshed pair is
    written straight back so the next request does not repeat the round-trip. Yahoo may ROTATE the
    refresh token and revokes the previous one when it does, so the write-back is required for
    correctness, not just for speed.
    """
    _require_yahoo_enabled()
    record = dynamo.get_platform_token(user_id, yahoo.PLATFORM)
    if not record or not record.get("refresh_token"):
        raise yahoo_oauth.YahooAuthError("Connect your Yahoo account to import a Yahoo league.")

    expires_at = int(record.get("expires_at") or 0)
    access = str(record.get("access_token") or "")
    if access and expires_at > int(time.time()):
        return access

    refreshed = yahoo_oauth.refresh_access_token(
        yahoo_oauth.decrypt_token(str(record["refresh_token"]))
    )
    dynamo.put_platform_token(
        user_id,
        yahoo.PLATFORM,
        {
            "refresh_token": yahoo_oauth.encrypt_token(refreshed["refresh_token"]),
            "access_token": refreshed["access_token"],
            "expires_at": refreshed["expires_at"],
            "connected_at": record.get("connected_at"),
        },
    )
    return refreshed["access_token"]


@router.get("/yahoo/authorize")
def yahoo_authorize(user_id: str = Depends(require_personalized_league_access)):
    """Where to send the user to grant read access (Yahoo's OWN consent screen)."""
    try:
        _require_yahoo_enabled()
        return {"authorize_url": yahoo_oauth.authorize_url(user_id)}
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e


@public_router.get("/yahoo/callback")
def yahoo_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """Yahoo redirects the user's BROWSER here after the consent screen (see the module docstring
    for why this route is unauthenticated and how the signed `state` authenticates it instead).

    Always returns a REDIRECT back to the app, never a JSON error: the user is sitting in a browser
    mid-flow, and an API error body would strand them on a blank page with no way back.
    """
    if error or not code or not state:
        reason = "denied" if error == "access_denied" else "failed"
        return RedirectResponse(f"{FRONTEND_RETURN_URL}?yahoo={reason}", status_code=302)
    try:
        user_id = yahoo_oauth.verify_state(state)
        tokens = yahoo_oauth.exchange_code(code)
        dynamo.put_platform_token(
            user_id,
            yahoo.PLATFORM,
            {
                "refresh_token": yahoo_oauth.encrypt_token(tokens["refresh_token"]),
                "access_token": tokens["access_token"],
                "expires_at": tokens["expires_at"],
                "connected_at": int(time.time()),
            },
        )
    except Exception:  # noqa: BLE001
        # Deliberately no detail in the URL: the failure reasons here (bad state, spent code,
        # rejected secret) are diagnostics for us, not for whoever might be reading the address bar.
        logger.exception("yahoo oauth callback failed")
        return RedirectResponse(f"{FRONTEND_RETURN_URL}?yahoo=failed", status_code=302)
    return RedirectResponse(f"{FRONTEND_RETURN_URL}?yahoo=connected", status_code=302)


@router.get("/yahoo/leagues")
def yahoo_leagues(user_id: str = Depends(require_personalized_league_access)):
    try:
        return {"leagues": yahoo.list_leagues(_access_token(user_id))}
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e


@router.post("/yahoo/preview")
def yahoo_preview(payload: PreviewRequest, user_id: str = Depends(require_personalized_league_access)):
    try:
        return yahoo.import_league(
            payload.league_id, _access_token(user_id), include_draft=payload.include_draft
        ).to_dict()
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e


@router.delete("/yahoo/connection", status_code=204)
def yahoo_disconnect(user_id: str = Depends(require_personalized_league_access)):
    """Forget the user's Yahoo grant on our side, AND delete the Yahoo data we copied.

    ⚠️ Says exactly what it does: this deletes OUR copy. The authoritative revocation is the user's
    own Yahoo account settings, which the UI links to — claiming to have revoked a grant we cannot
    revoke would be the kind of quiet overstatement this product does not make.

    ⭐ NF-C0-Yahoo-ENABLE (Half A) — DELETION ON DISCONNECT IS MANDATORY, NOT A COURTESY (§6). Until
    this story, disconnecting dropped the OAuth token and nothing else, so a user who disconnected
    kept every roster we had copied from Yahoo, indefinitely and with no way to remove it. The
    spike memo carried that as gap B2. Two halves, and the split is deliberate:
      · THE ROSTERS GO. `imported_roster` and `league_rosters` are a copy of Yahoo's league state.
      · THE LEAGUE STAYS. Its scoring rules, roster slots, team count and depth targets are the
        user's own configuration — the same artefact a hand-entered league is — and destroying it
        would punish someone for exercising the control this endpoint exists to give them.

    ⚠️ THE PURGE RUNS FIRST AND IS ALLOWED TO FAIL THE REQUEST. Dropping the token first would
    leave the rosters behind with the connection already gone, and this endpoint is the user's only
    handle on them. A purge that cannot complete therefore surfaces as a failed disconnect the user
    can retry, rather than as a silent partial one — the compliance red line is deletion, so the
    fail-closed direction is to not report success we did not achieve.
    """
    dynamo.purge_platform_league_data(user_id, yahoo.PLATFORM)
    dynamo.delete_platform_token(user_id, yahoo.PLATFORM)
    return None


# ── coverage-gap telemetry (NF-C0d) ─────────────────────────────────────────────────────────────


@router.post("/telemetry", status_code=202)
def record_import_telemetry(
    payload: ImportTelemetryRequest, user_id: str = Depends(require_personalized_league_access)
) -> dict:
    """Record which of this JUST-SAVED league's scoring terms we could not apply.

    Called by the import UI right after a successful save, carrying exactly the CAPTURED rows the
    coverage panel already showed the user (see `resolveScoring`/`TermCoverage` on the frontend —
    this endpoint does not and cannot recompute that classification; the Lambda has no
    `fantasy_engine`/pandas, per `canonical.py`'s docstring). The write is AGGREGATE ONLY — see
    `fantasy_import_telemetry`'s module docstring — and BEST-EFFORT: `record_captured_terms` never
    raises, so this endpoint cannot turn a telemetry hiccup into a user-visible failure, and it
    always returns 202 whether or not the write actually landed.
    """
    if payload.platform not in PLATFORMS:
        raise HTTPException(status_code=422, detail="Unknown platform")
    fantasy_import_telemetry.record_captured_terms(
        payload.platform,
        payload.season,
        [t.model_dump() for t in payload.terms],
    )
    return {"status": "recorded"}


# ── live state for an ALREADY-SAVED imported league ──────────────────────────────────────────────


@router.get("/live/{league_id}")
def live_state(league_id: str, user_id: str = Depends(require_personalized_league_access)):
    """Re-read LIVE rosters + draft state for a saved league that was imported.

    ⭐ WHY THIS IS A SEPARATE READ AND NOT A STORED FIELD. Draft state is the one part of an import
    that is worthless the moment it is stale — a board showing a player as available when they went
    three picks ago is actively harmful, and it looks identical to a correct board. So the SETTINGS
    are durable and the STATE is always fetched fresh. A league saved by hand (no provenance) gets
    an explicit "not an imported league" 400 rather than an empty payload that would read as "your
    draft has not started".
    """
    league = dynamo.get_fantasy_league(user_id, league_id)
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    platform = str(league.get("source_platform") or "")
    source_id = str(league.get("source_league_id") or "")
    if not platform or not source_id:
        raise HTTPException(
            status_code=400,
            detail="This league was entered by hand, so there is no platform to read live state from.",
        )
    try:
        if platform == sleeper.PLATFORM:
            draft = sleeper.fetch_draft_state(source_id)
        elif platform == yahoo.PLATFORM:
            draft = yahoo.fetch_draft_state(source_id, _access_token(user_id))
        else:
            raise HTTPException(status_code=400, detail=f"Unknown platform {platform!r}")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise _handle_platform_error(e) from e
    return {"platform": platform, "source_league_id": source_id, "draft": draft.to_dict()}
