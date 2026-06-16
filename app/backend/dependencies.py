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
