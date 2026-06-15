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


def _sub_from_bearer(authorization: str | None) -> str | None:
    """Extract sub claim from a Cognito JWT without signature verification.

    Safe for local dev only — prod uses the API Gateway authorizer.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # JWT payload is base64url encoded; pad to multiple of 4
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload.get("sub")
    except Exception:
        return None


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

    # Primary: Cognito group membership ("admin" group)
    groups = claims.get("cognito:groups") or []
    if isinstance(groups, str):
        # API Gateway may deliver a JSON array as a string
        try:
            groups = json.loads(groups)
        except Exception:
            groups = [groups]
    if "admin" in groups:
        return user_id

    # Legacy: ADMIN_EMAILS env var
    if _ADMIN_EMAILS:
        username = claims.get("username") or claims.get("cognito:username", "")
        if username.lower() in _ADMIN_EMAILS:
            return user_id
        # Local dev fallback: explicit header
        dev_email = request.headers.get("X-Admin-Email", "")
        if dev_email.lower() in _ADMIN_EMAILS:
            return user_id

    raise HTTPException(status_code=403, detail="Admin access required")
