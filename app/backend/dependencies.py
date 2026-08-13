"""Shared FastAPI dependencies.

get_user_id — resolve the caller's identity (Cognito `sub`) from the API Gateway
JWT authorizer context. The authorizer validates the token before the Lambda is
invoked, so the `sub` claim here is trusted. In local dev (uvicorn, no authorizer)
falls back to X-User-Id header, then to the Bearer JWT sub claim (unverified decode).

get_admin_user — same as get_user_id, but additionally checks that the caller
belongs to the Cognito "admin" group (preferred) or appears in the ADMIN_EMAILS
env var (legacy fallback). Raises 403 otherwise.
"""

from __future__ import annotations

import base64
import json
import logging
import os

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)

# Comma-separated list of Cognito usernames (emails) allowed to call admin endpoints.
# Legacy fallback — prefer assigning users to the Cognito "admin" group instead.
_ADMIN_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
)


def _decode_jwt_payload(authorization: str | None) -> dict:
    """Decode the payload of a Bearer JWT without signature verification.

    Safe in prod because API Gateway's JWT authorizer has already validated the
    token before Lambda is invoked. Used as a fallback when the authorizer context
    doesn't surface a specific claim (e.g. cognito:groups array flattening).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return {}
    token = authorization.removeprefix("Bearer ")
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def _sub_from_bearer(authorization: str | None) -> str | None:
    return _decode_jwt_payload(authorization).get("sub")


def _groups_from_bearer(authorization: str | None) -> list[str]:
    """Extract cognito:groups from the raw Bearer token payload."""
    groups = _decode_jwt_payload(authorization).get("cognito:groups") or []
    if isinstance(groups, list):
        return groups
    if isinstance(groups, str):
        return [g.strip() for g in groups.split(",") if g.strip()]
    return []


def parse_groups_claim(raw) -> set[str]:
    """Parse a `cognito:groups` claim value in EVERY delivery shape we have seen.

    ⚠️ THE DELIMITER IS THE BUG. The API Gateway HTTP API (v2) JWT authorizer flattens a
    multi-valued claim into a BRACKETED, SPACE-separated string (`[fantasy_comp subscriber]`)
    — not the comma-separated form the shape suggests — while a raw token payload carries a
    clean JSON array. A comma-only split therefore yields `["[subscriber]"]`, which matches
    NOTHING, and every caller of it silently behaves as though the user were in no groups at
    all. That is invisible in tests written with the comma form, because such a test restates
    the parser's own assumption instead of testing it (NF-C0e).

    Central so a fix lands once rather than in each of the four places that read this claim.
    """
    if isinstance(raw, (list, tuple, set)):
        return {str(g).strip() for g in raw if str(g).strip()}
    if isinstance(raw, str) and raw.strip():
        return {
            part.strip()
            for part in raw.strip().strip("[]").replace(",", " ").split()
            if part.strip()
        }
    return set()


def _claims_from_event(request: Request) -> dict:
    """Return the JWT claims dict from the API Gateway authorizer context, or {}."""
    event = request.scope.get("aws.event", {})
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return {}


def get_user_id(request: Request) -> str:
    """Cognito `sub` from the API Gateway HTTP API (v2) JWT authorizer context."""
    claims = _claims_from_event(request)
    if claims.get("sub"):
        return claims["sub"]
    # Local dev fallback 1: explicit header
    dev_user = request.headers.get("X-User-Id")
    if dev_user:
        return dev_user
    # Local dev fallback 2: decode Bearer token (no sig verification)
    sub = _sub_from_bearer(request.headers.get("Authorization"))
    if sub:
        return sub
    raise HTTPException(status_code=401, detail="Unable to determine user identity")


def get_optional_user_id(request: Request) -> str | None:
    """Like get_user_id, but returns None instead of raising 401 when unauthenticated.

    Used by endpoints that support optional per-user behavior (e.g. portfolio filtering
    on GET /picks/today?apply_portfolio=true).
    """
    try:
        return get_user_id(request)
    except Exception:
        return None


def _groups_from_request(request: Request) -> list[str]:
    """Cognito groups for the caller — the UNION of the authorizer-context claim and the
    raw Bearer-token payload.

    Both sources are merged because the API Gateway HTTP API (v2) JWT authorizer delivers
    a multi-valued claim like `cognito:groups` as a bracketed, space-separated STRING
    (`[fantasy_comp subscriber]`), NOT comma-separated — so parsing the context alone is
    unreliable (this is exactly why get_admin_user keeps a bearer-decode fallback). The
    Bearer payload carries the claim as a clean JSON array. Unioning both, and parsing the
    context for either bracket/space or comma delimiters, is robust to both formats. The
    token is already signature-validated by the authorizer before Lambda invokes.

    🔒 E9.56 — THE UNION IS CONDITIONAL ON THE AUTHORIZER HAVING RUN. The sentence above ("already
    signature-validated by the authorizer") is the ENTIRE basis for trusting an unverified bearer
    decode, and it is true only while this route carries the API Gateway JWT authorizer. On a route
    whose authorization-type is `NONE` there is no upstream validation, and a forged
    `{"cognito:groups":["subscriber","admin"]}` reaches the Lambda intact (measured — see
    `services/jwt_verify.py`). So when the authorizer context is ABSENT, groups come only from a
    SIGNATURE-VERIFIED token. That keeps this helper safe for any future public route rather than
    relying on nobody ever mounting a gated dependency on one, and it is also correct in local
    uvicorn dev, where a real Cognito token verifies normally."""
    claims = _claims_from_event(request)
    if not claims:
        from app.backend.services import jwt_verify

        return jwt_verify.verified_groups(request.headers.get("Authorization"))

    groups: set[str] = set(_groups_from_bearer(request.headers.get("Authorization")))
    # Handles both "[a b]" (HTTP API v2) and "a,b" delimiter styles.
    groups |= parse_groups_claim(claims.get("cognito:groups"))
    return list(groups)


def require_fantasy_access(request: Request, user_id: str = Depends(get_user_id)) -> str:
    """Gate the fantasy surface (E9.45) — defense-in-depth for the client-side nav gate.

    Grants callers in `subscriber`, `admin`, or the `fantasy_comp` allow-list, read
    from the `cognito:groups` claim. Raises 403 otherwise (a `beta_tester` who lacks
    fantasy is blocked here even though they keep full betting access — the deliberate
    E9.8 divergence). A client-only gate on a paid feature is bypassable, so the
    fantasy DATA endpoints depend on this.
    """
    # Import here to avoid a circular import at module load (services import lightly).
    from app.backend.services import cognito

    if cognito.has_fantasy_access(_groups_from_request(request)):
        return user_id
    raise HTTPException(status_code=403, detail="Fantasy access required")


def require_fantasy_beta_access(request: Request, user_id: str = Depends(get_user_id)) -> str:
    """Gate the manual league-settings editor (NF-C0b) — `admin` + `fantasy_comp` ONLY.

    NARROWER than `require_fantasy_access` on purpose: a paying `subscriber` has the
    fantasy surface but NOT this editor yet. The settings a user saves here drive the
    board, VOR and the draft optimizer, so the surface goes to operator + comp accounts
    first (the staged shape MVP-3 used when the draft tool was admin-only).

    Server-side enforcement matters more than usual here because these are WRITE
    endpoints: hiding the nav item is not a gate, and an unentitled caller could
    otherwise POST a league config straight to the API.
    """
    from app.backend.services import cognito

    if cognito.has_fantasy_beta_access(_groups_from_request(request)):
        return user_id
    raise HTTPException(status_code=403, detail="Fantasy league settings access required")


def require_personalized_league_access(
    request: Request, user_id: str = Depends(get_user_id)
) -> str:
    """G100-C1 — gate the SAVED-LEAGUE surface on the caller's personalization QUOTA.

    ⭐ REPLACES `require_fantasy_beta_access` on the league editor + platform import. Until G100-C1
    those were `admin` + `fantasy_comp` only; a free account now gets ONE personalized league, so the
    question the gate asks changed from "which group are you in?" to "do you have a quota to spend?"
    — and the answer comes from ONE place, `entitlement.personalized_league_quota`, rather than being
    re-derived here. That is what makes the free tier a number an operator can move (including back
    to 0) instead of a predicate someone has to rewrite.

    ⚠️ IDENTITY FIRST, ENTITLEMENT SECOND, and the order is load-bearing. `get_user_id` resolves as a
    dependency, so an anonymous caller gets 401 before the quota is consulted. That is the honest
    status: every league record is keyed on a Cognito `sub`, so an anonymous caller has nowhere to
    save one — this is "sign in", not "pay". Returning 403 there would send the client to the upgrade
    CTA when the real next step is the signup one.

    ⛔ A quota of 0 (the operator setting `FREE_PERSONALIZED_LEAGUE_QUOTA=0` to withdraw the free
    tier) refuses a non-entitled caller with 403 — the paid message — while a subscriber is unaffected
    because their quota comes from the storage cap, not from that env var.
    """
    from app.backend.services import entitlement

    if entitlement.allows_personalization(entitlement.resolve_entitlement(request)):
        return user_id
    raise HTTPException(
        status_code=403, detail="A Credence membership is required to save a league."
    )


def get_admin_user(request: Request, user_id: str = Depends(get_user_id)) -> str:
    """Like get_user_id, but raises 403 if the caller is not an admin.

    Preferred path: checks the caller belongs to the Cognito "admin" group via
    the `cognito:groups` claim in the access token (set when the user is added to
    the Cognito User Pool "admin" group).

    Legacy fallback: ADMIN_EMAILS env var (comma-separated emails). Kept for
    backwards compatibility during deployments that haven't set up Cognito groups.

    Local dev fallback: X-Admin-Email request header.
    """
    claims = _claims_from_event(request)

    # Primary: cognito:groups from API Gateway authorizer context.
    # API Gateway HTTP API delivers JWT array claims as comma-separated strings,
    # so split on comma rather than JSON-parse.
    raw = claims.get("cognito:groups") or ""
    if raw:
        ctx_groups = [g.strip() for g in raw.split(",") if g.strip()]
        if "admin" in ctx_groups:
            return user_id

    # Fallback: decode the Bearer token directly.
    # Needed when API Gateway doesn't surface cognito:groups in the claims context
    # (e.g. single-group users or authorizer config differences). Safe because the
    # JWT has already been signature-validated by API Gateway before Lambda invokes.
    if "admin" in _groups_from_bearer(request.headers.get("Authorization")):
        return user_id

    # Legacy: ADMIN_EMAILS env var
    if _ADMIN_EMAILS:
        username = claims.get("username") or claims.get("cognito:username", "")
        if username.lower() in _ADMIN_EMAILS:
            return user_id
        dev_email = request.headers.get("X-Admin-Email", "")
        if dev_email.lower() in _ADMIN_EMAILS:
            return user_id

    raise HTTPException(status_code=403, detail="Admin access required")
