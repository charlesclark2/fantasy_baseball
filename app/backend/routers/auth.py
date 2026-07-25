"""Auth endpoints + the server-side subscriber-MFA guard (E9.8).

POST /auth/refresh — exchange a Cognito refresh token for a new access token.

`require_subscriber_mfa` is a FastAPI dependency wired onto the paid content routers
(see main.py). It is the defense-in-depth backstop for E9.19's MFA enforcement, which
is otherwise frontend-only (a client redirect, trivially bypassed by hitting the API
directly). It rejects `subscriber`-group API calls whose Cognito account lacks a TOTP
(SOFTWARE_TOKEN_MFA) factor, EXEMPTING sessions that authenticated via a federated IdP
(Google) — those inherit MFA from the IdP and never enroll TOTP.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.backend.dependencies import _claims_from_event, get_optional_user_id, get_user_id
from app.backend.services import cognito as cognito_svc
from app.backend.services.dynamo import record_tos_acceptance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

_COGNITO_CLIENT_ID  = os.environ.get("COGNITO_APP_CLIENT_ID",  "1qh95e78bd7g6ipqcvdcpf7ou6")
_COGNITO_USER_POOL  = os.environ.get("COGNITO_USER_POOL_ID",   "us-east-1_gG9zMbwQt")
_AWS_REGION         = os.environ.get("AWS_REGION",              "us-east-1")


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    id_token: str
    expires_in: int
    token_type: str


@router.post("/refresh", response_model=RefreshResponse)
def refresh_token(body: RefreshRequest) -> RefreshResponse:
    client = boto3.client("cognito-idp", region_name=_AWS_REGION)
    try:
        resp = client.initiate_auth(
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": body.refresh_token},
            ClientId=_COGNITO_CLIENT_ID,
        )
    except client.exceptions.NotAuthorizedException as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from exc
    except ClientError as exc:
        logger.exception("Cognito initiate_auth failed")
        raise HTTPException(status_code=503, detail="Auth service unavailable") from exc

    result = resp.get("AuthenticationResult", {})
    return RefreshResponse(
        access_token=result["AccessToken"],
        id_token=result["IdToken"],
        expires_in=result.get("ExpiresIn", 3600),
        token_type=result.get("TokenType", "Bearer"),
    )


@router.post("/verify-email", status_code=204)
def verify_email(user_id: str = Depends(get_user_id)) -> None:
    """Mark the caller's Cognito email as verified.

    Admin-created accounts have email_verified=false by default, which blocks
    the forgotPassword() flow. The frontend calls this fire-and-forget on every
    successful login; it's a no-op once the attribute is already true.

    Requires cognito-idp:AdminUpdateUserAttributes on the Lambda execution role.
    """
    client = boto3.client("cognito-idp", region_name=_AWS_REGION)
    try:
        client.admin_update_user_attributes(
            UserPoolId=_COGNITO_USER_POOL,
            Username=user_id,
            UserAttributes=[{"Name": "email_verified", "Value": "true"}],
        )
    except ClientError:
        # Best-effort — don't fail the login flow if this call errors
        logger.warning("verify_email: admin_update_user_attributes failed for %s", user_id)


_TOS_VERSION = "2026-06-14"


@router.post("/accept-terms", status_code=204)
def accept_terms(user_id: str = Depends(get_user_id)) -> None:
    """Record ToS acceptance for the calling user.

    Called fire-and-forget from the frontend on completion of the first-login
    new-password flow. Writes tos_accepted_at (if_not_exists) and tos_version
    to credence-prod-dynamo-users. Safe to call multiple times.
    """
    try:
        record_tos_acceptance(user_id, _TOS_VERSION)
    except Exception:
        logger.warning("accept_terms: failed to record acceptance for %s", user_id)


# ── Server-side subscriber-MFA enforcement (E9.8) ────────────────────────────
# Flag-gated OFF by default so it's a no-op through Phase 1 (test mode) and only
# ever bites once real `subscriber` accounts exist. The operator flips it to "1"
# at go-live, in lockstep with NEXT_PUBLIC_ENFORCE_SUBSCRIBER_MFA (frontend).
def _mfa_enforced() -> bool:
    return os.getenv("ENFORCE_SUBSCRIBER_MFA", "0") == "1"

# Known Cognito federated-username prefixes (`<Provider>_<providerUserId>`). A native
# (username/password) account's username is its email — which contains an '@' — so the
# "no '@' + provider prefix" shape is a trustworthy, server-verifiable signal that THIS
# token was minted for a federated (Google) sign-in.
_FEDERATED_USERNAME_RE = re.compile(
    r"^(google|signinwithapple|facebook|loginwithamazon)_", re.IGNORECASE
)

# Small in-warm-Lambda cache of MFA-factor reads so a burst of paid API calls from one
# subscriber isn't one AdminGetUser each. Keyed by sub; short TTL.
_MFA_CACHE: dict[str, tuple[float, bool]] = {}
_MFA_CACHE_TTL_S = 120.0


def _session_is_federated(claims: dict, authorization: str | None) -> bool:
    """Trustworthy, server-side determination that this token's session authenticated
    via a federated IdP (Google).

    We deliberately do NOT key off the id-token `identities` claim: after E9.7 account
    linking one Cognito sub carries BOTH a password credential and a linked Google
    identity, so `identities` is present even on that user's PASSWORD login — exempting
    on it would skip MFA on exactly the session this guard exists to protect. We also
    don't trust the client's localStorage auth-method marker (client-controlled).

    Signals used, both derived from the API-Gateway-validated token:
      • `amr` (Authentication Methods References) naming a federated provider, and
      • the federated username shape (`Google_<id>`, no '@').
    On ANY ambiguity we return False → the caller FAILS CLOSED (requires TOTP). A
    Google-linked user re-verifying TOTP is a minor annoyance; a bypass on a paying
    account is not.
    """
    # amr — a list (sometimes delivered as a JSON string by API Gateway).
    amr_raw = claims.get("amr")
    amr: list[str] = []
    if isinstance(amr_raw, list):
        amr = [str(x) for x in amr_raw]
    elif isinstance(amr_raw, str):
        try:
            parsed = json.loads(amr_raw)
            amr = [str(x) for x in parsed] if isinstance(parsed, list) else [amr_raw]
        except Exception:
            amr = [amr_raw]
    if any(re.search(r"google|federated|signinwithapple|facebook", a, re.IGNORECASE) for a in amr):
        return True

    # Federated username shape.
    username = str(claims.get("username") or claims.get("cognito:username") or "")
    if "@" not in username and _FEDERATED_USERNAME_RE.match(username):
        return True

    return False


def _has_totp(sub: str) -> bool:
    now = time.monotonic()
    cached = _MFA_CACHE.get(sub)
    if cached and (now - cached[0]) < _MFA_CACHE_TTL_S:
        return cached[1]
    ok = cognito_svc.has_software_token_mfa(sub)  # raises on Cognito error
    _MFA_CACHE[sub] = (now, ok)
    return ok


def require_subscriber_mfa(
    request: Request, user_id: str | None = Depends(get_optional_user_id)
) -> str | None:
    """Reject a `subscriber` API call that lacks TOTP MFA (federated sessions exempt).

    Wired as a router-level dependency on the paid content routers. Uses the OPTIONAL
    identity resolver so it never forces auth on the anonymous-capable endpoints those
    routers also serve (e.g. the public landing-page picks) — an unauthenticated caller
    simply isn't a subscriber and passes through.

    No-op unless ENFORCE_SUBSCRIBER_MFA=1. Only `subscriber`-group callers are gated,
    so non-subscribers (free/beta/anon) pass through untouched and incur no Cognito
    read. Fails CLOSED: an unreadable MFA status is treated as not-enrolled.
    """
    if not _mfa_enforced():
        return user_id

    claims = _claims_from_event(request)
    # Groups from the authorizer context (comma-joined) — cheap, no Cognito call.
    raw_groups = claims.get("cognito:groups") or ""
    groups = [g.strip() for g in raw_groups.split(",") if g.strip()] if isinstance(raw_groups, str) else list(raw_groups)
    if cognito_svc.GROUP_SUBSCRIBER not in groups:
        return user_id  # only paying subscribers are gated
    if not user_id:
        return user_id  # can't identify the caller → not a resolvable subscriber call

    # Exempt genuine federated (Google) sessions — they inherit IdP MFA.
    if _session_is_federated(claims, request.headers.get("Authorization")):
        return user_id

    try:
        if _has_totp(user_id):
            return user_id
    except Exception:
        logger.warning("require_subscriber_mfa: MFA read failed for %s — failing closed", user_id)

    raise HTTPException(
        status_code=403,
        detail="Two-factor authentication is required for your account. Enable it in Settings.",
    )
