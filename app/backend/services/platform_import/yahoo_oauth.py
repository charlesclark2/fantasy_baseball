"""yahoo_oauth.py — the 3-legged Yahoo OAuth2 flow + the encrypted per-user token store (NF-C0).

🚨 THE RED LINE THIS EXISTS TO HONOUR. We NEVER capture, store, or replay a user's Yahoo password.
The user authorizes on YAHOO'S OWN consent screen; we receive an authorization code on our callback
and exchange it for a per-user token. What we hold is a revocable, read-scoped grant the user can
withdraw at any time from their Yahoo account settings — not a credential that could be used to log
in as them. (This is precisely the line E8.2a's CBS NO-GO was earned on.)

🔎 PROBED LIVE 2026-08-01 — every endpoint below was verified, not copied from a cached page. The
old `developer.yahoo.com/fantasysports/guide/` now 308-redirects to `sports.yahoo.com/developer`,
so a session coding from the historical docs URL would have been writing against a moved target:
  * `POST/GET https://api.login.yahoo.com/oauth2/request_auth` → live; a call without `redirect_uri`
    returns `error=invalid_request&error_description=missing required parameter redirect_uri`,
    which is how the endpoint was confirmed rather than assumed.
  * `https://api.login.yahoo.com/oauth2/get_token` → the documented token + refresh endpoint,
    Basic-authenticated with `client_id:client_secret`.
  * `https://fantasysports.yahooapis.com/fantasy/v2/game/nfl` → 401 unauthenticated (live, gated).

⚠️ NOTE ON `scope`. Yahoo's authorization-code flow does NOT take a per-request `scope` parameter for
Fantasy Sports — the permission is a property of the REGISTERED APP ("select Read access for Fantasy
Sports" in the YDN console). Sending a `scope=fspt-r` query parameter is a widely-copied piece of
folklore that does not appear in the current flow documentation, so it is deliberately not sent
here: the app's declared permission is what grants access.

🔑 SECRETS. The client id/secret are OUR application credential (not user data) and live in SSM
Parameter Store as SecureStrings; the backend reads them at runtime and they are never committed.
See `docs/nf_c0_yahoo_oauth_setup.md` for the operator's click-by-click registration guide and the
exact parameter names.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
import time
from hashlib import sha256

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.backend.services.platform_import.http import PlatformHTTPError, post_form

logger = logging.getLogger(__name__)

AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"

# SSM parameter names. `SSM_PREFIX` lets a non-prod stack point at its own copies without a code
# change; the defaults are the prod names quoted in the operator guide.
SSM_PREFIX = os.getenv("YAHOO_SSM_PREFIX", "/credence/prod")
PARAM_CLIENT_ID = f"{SSM_PREFIX}/yahoo_oauth_client_id"
PARAM_CLIENT_SECRET = f"{SSM_PREFIX}/yahoo_oauth_client_secret"
PARAM_TOKEN_KEY = f"{SSM_PREFIX}/yahoo_token_encryption_key"

# ⚠️ Yahoo requires an HTTPS callback (a known gotcha — an http:// redirect URI is rejected at app
# registration). It must match the registered value BYTE-FOR-BYTE, including the trailing path, or
# the token exchange fails with an opaque `invalid_request`.
DEFAULT_REDIRECT_URI = "https://api.credencesports.com/fantasy/import/yahoo/callback"
REDIRECT_URI = os.getenv("YAHOO_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI)

# How long a signed `state` value stays valid. Long enough for a user to actually read Yahoo's
# consent screen, short enough that a leaked callback URL is not replayable tomorrow.
STATE_TTL_SECONDS = 900

# Warm-container cache for the SSM reads. A Lambda that re-read three SSM parameters on every
# request would add latency and burn the (throttled) GetParameter quota for values that change
# approximately never; a short TTL still lets a rotated secret take effect without a redeploy.
_SSM_CACHE_TTL = 300.0
_ssm_cache: dict[str, tuple[float, str | None]] = {}

_ssm_client = None


class YahooNotConfigured(RuntimeError):
    """Yahoo import is not provisioned yet (no client id/secret in SSM).

    A DISTINCT type on purpose: "the operator has not finished the Yahoo developer registration"
    must reach the user as an honest "not available yet", never as a generic 500 that looks like a
    bug. The story ships this adapter code-complete ahead of that registration, so this is an
    EXPECTED state, not an error condition.
    """


class YahooAuthError(RuntimeError):
    """The user's Yahoo grant is missing, expired or was revoked → they must reconnect."""


def _ssm():
    global _ssm_client
    if _ssm_client is None:
        # ⚠️ NO region override here. `AWS_DEFAULT_REGION=us-east-2` is the S3 LAKEHOUSE bucket's
        # region only; SSM (like SNS) lives with the rest of the app stack in us-east-1, and
        # passing the lakehouse region produces a misleading ParameterNotFound.
        _ssm_client = boto3.client("ssm", region_name=os.getenv("APP_AWS_REGION", "us-east-1"))
    return _ssm_client


def _get_parameter(name: str) -> str | None:
    """Read one SecureString parameter, cached. Returns None when absent or unreadable.

    Never raises: an unprovisioned or IAM-blocked parameter must surface as "Yahoo import isn't set
    up yet" (a 503 the UI explains), not as an unhandled exception on a page that also serves
    Sleeper import — one platform's missing config must not take the other down.
    """
    now = time.time()
    cached = _ssm_cache.get(name)
    if cached and now - cached[0] < _SSM_CACHE_TTL:
        return cached[1]
    value: str | None = None
    try:
        resp = _ssm().get_parameter(Name=name, WithDecryption=True)
        value = str(resp["Parameter"]["Value"]).strip() or None
    except (ClientError, BotoCoreError, KeyError) as e:
        logger.info("yahoo oauth: parameter %s unavailable (%s)", name, type(e).__name__)
    _ssm_cache[name] = (now, value)
    return value


def client_credentials() -> tuple[str, str]:
    cid = _get_parameter(PARAM_CLIENT_ID)
    secret = _get_parameter(PARAM_CLIENT_SECRET)
    if not cid or not secret:
        raise YahooNotConfigured(
            "Yahoo import is not configured yet. The Yahoo developer application has not been "
            "registered, so Yahoo leagues cannot be connected."
        )
    return cid, secret


def is_configured() -> bool:
    """Are OUR Yahoo app credentials readable from SSM? (Provisioning, not permission.)"""
    try:
        client_credentials()
        return True
    except YahooNotConfigured:
        return False


def is_enabled() -> bool:
    """Should Yahoo import be OFFERED to users right now?

    ⚠️ CREDENTIALS PRESENT ≠ FEATURE USABLE, and conflating the two ships a button that fails.
    Creating the YDN app yields a client id/secret immediately, but Yahoo grants FANTASY DATA access
    separately, on approval of a reviewed application (1–2 weeks). In between, the OAuth handshake
    itself would succeed — the user would clear Yahoo's consent screen — and then every Fantasy
    endpoint would 401. That is strictly worse than an honest "Coming soon": the user has now
    granted a permission that buys them nothing, and the failure looks like our bug.

    So provisioning (SSM) and availability (this flag) are deliberately separate. It lets the
    operator write the parameters and prove the SSM/IAM path works — the part that is OURS and can
    genuinely be misconfigured — while the surface keeps telling the truth. On approval it is one
    env var, no redeploy and no code change.
    """
    return is_configured() and os.getenv("YAHOO_IMPORT_ENABLED", "").strip() == "1"


# ── token encryption ──────────────────────────────────────────────────────────────────────────────
# A user's refresh token is a long-lived grant on their Yahoo account. It is encrypted at rest with
# Fernet (AES-128-CBC + HMAC-SHA256, from `cryptography`, which the Lambda bundle already carries)
# under a key held in SSM as a SecureString. That keeps the ciphertext useless to anyone who can
# read the DynamoDB item but cannot also read the KMS-encrypted parameter — two separate grants.


def _fernet():
    key = _get_parameter(PARAM_TOKEN_KEY)
    if not key:
        raise YahooNotConfigured(
            "Yahoo import is not configured yet (the token encryption key is not provisioned)."
        )
    from cryptography.fernet import Fernet

    return Fernet(key.encode("utf-8"))


def encrypt_token(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as e:
        # A rotated key makes every stored token undecryptable. Surfacing that as "reconnect your
        # Yahoo account" is both true and actionable; surfacing it as a 500 would strand the user.
        raise YahooAuthError("Your Yahoo connection could not be read. Please reconnect.") from e


# ── CSRF state ────────────────────────────────────────────────────────────────────────────────────
# The `state` round-trips through Yahoo and comes back on our callback, so it must prove BOTH that
# we issued it and WHICH user it belongs to. It is signed (HMAC-SHA256 under the same SSM key)
# rather than stored, so the callback needs no session lookup and there is no server-side state to
# expire or leak. Binding the user id into the signature is what stops an attacker from replaying
# their own consent callback to graft their Yahoo account onto someone else's Credence account.


def _state_key() -> bytes:
    key = _get_parameter(PARAM_TOKEN_KEY)
    if not key:
        raise YahooNotConfigured("Yahoo import is not configured yet.")
    return sha256(("state:" + key).encode("utf-8")).digest()


def issue_state(user_id: str) -> str:
    payload = {"u": user_id, "n": secrets.token_urlsafe(12), "t": int(time.time())}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    body = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(_state_key(), body.encode("ascii"), sha256).digest()
    return f"{body}.{base64.urlsafe_b64encode(sig).decode('ascii').rstrip('=')}"


def verify_state(state: str) -> str:
    """Return the user id a state was issued for, or raise YahooAuthError."""

    def _bad() -> YahooAuthError:
        return YahooAuthError("That Yahoo sign-in link is invalid or has expired. Please try again.")

    try:
        body, sig = str(state).split(".", 1)
    except ValueError as e:
        raise _bad() from e
    expected = hmac.new(_state_key(), body.encode("ascii"), sha256).digest()
    try:
        given = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
    except Exception as e:  # noqa: BLE001 - any decode failure is the same rejection
        raise _bad() from e
    if not hmac.compare_digest(expected, given):
        raise _bad()
    try:
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        user_id = str(payload["u"])
        issued = int(payload["t"])
    except Exception as e:  # noqa: BLE001
        raise _bad() from e
    if time.time() - issued > STATE_TTL_SECONDS:
        raise _bad()
    return user_id


# ── the flow ──────────────────────────────────────────────────────────────────────────────────────


def authorize_url(user_id: str) -> str:
    """Step 2 of the authorization-code flow: where we send the user to grant access."""
    import urllib.parse

    client_id, _ = client_credentials()
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": issue_state(user_id),
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _basic_auth_header() -> dict[str, str]:
    client_id, secret = client_credentials()
    blob = base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {blob}"}


def _token_call(form: dict[str, str]) -> dict:
    status, payload = post_form(TOKEN_URL, form, headers=_basic_auth_header())
    if not isinstance(payload, dict):
        raise PlatformHTTPError("Yahoo returned an unreadable token response", status=status)
    if status >= 400 or "access_token" not in payload:
        detail = str(payload.get("error_description") or payload.get("error") or f"HTTP {status}")
        # `invalid_grant` specifically means the user's grant is gone (revoked, or the code was
        # already spent) — a reconnect fixes it, so it is an auth error rather than a platform fault.
        if str(payload.get("error") or "") in ("invalid_grant", "INVALID_REFRESH_TOKEN"):
            raise YahooAuthError("Your Yahoo connection has expired. Please reconnect.")
        raise PlatformHTTPError(f"Yahoo rejected the token request: {detail}", status=status)
    return payload


def exchange_code(code: str) -> dict:
    """Step 4: authorization code → `{access_token, refresh_token, expires_at, guid}`."""
    payload = _token_call(
        {
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        }
    )
    return _normalize_token(payload)


def refresh_access_token(refresh_token: str) -> dict:
    payload = _token_call(
        {
            "grant_type": "refresh_token",
            "redirect_uri": REDIRECT_URI,
            "refresh_token": refresh_token,
        }
    )
    normalized = _normalize_token(payload)
    # Yahoo MAY rotate the refresh token; the docs are explicit that the old one is revoked once a
    # new one is issued, so carrying the previous value forward when the response omits it (and
    # replacing it when present) is required — not an optimisation.
    if not normalized.get("refresh_token"):
        normalized["refresh_token"] = refresh_token
    return normalized


def _normalize_token(payload: dict) -> dict:
    expires_in = payload.get("expires_in")
    try:
        expires_in = int(expires_in)
    except (TypeError, ValueError):
        expires_in = 3600
    return {
        "access_token": str(payload.get("access_token") or ""),
        "refresh_token": str(payload.get("refresh_token") or ""),
        # A 60s safety margin so a token that expires mid-request is refreshed before the call
        # rather than producing a 401 the user sees.
        "expires_at": int(time.time()) + max(0, expires_in - 60),
        "guid": str(payload.get("xoauth_yahoo_guid") or "") or None,
    }


__all__ = [
    "AUTHORIZE_URL",
    "PARAM_CLIENT_ID",
    "PARAM_CLIENT_SECRET",
    "PARAM_TOKEN_KEY",
    "REDIRECT_URI",
    "TOKEN_URL",
    "YahooAuthError",
    "YahooNotConfigured",
    "authorize_url",
    "client_credentials",
    "is_enabled",
    "decrypt_token",
    "encrypt_token",
    "exchange_code",
    "is_configured",
    "issue_state",
    "refresh_access_token",
    "verify_state",
]
