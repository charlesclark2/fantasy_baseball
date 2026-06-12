"""Shared FastAPI dependencies.

get_user_id — resolve the caller's identity (Cognito `sub`) from the API Gateway
JWT authorizer context. The authorizer validates the token before the Lambda is
invoked, so the `sub` claim here is trusted. In local dev (uvicorn, no authorizer)
falls back to X-User-Id header, then to the Bearer JWT sub claim (unverified decode).
"""

from __future__ import annotations

import base64
import json
import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


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


def get_user_id(request: Request) -> str:
    """Cognito `sub` from the API Gateway HTTP API (v2) JWT authorizer context."""
    event = request.scope.get("aws.event", {})
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
    except (KeyError, TypeError):
        pass
    # Local dev fallback 1: explicit header
    dev_user = request.headers.get("X-User-Id")
    if dev_user:
        return dev_user
    # Local dev fallback 2: decode Bearer token (no sig verification)
    sub = _sub_from_bearer(request.headers.get("Authorization"))
    if sub:
        return sub
    raise HTTPException(status_code=401, detail="Unable to determine user identity")
