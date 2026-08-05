"""E9.56 — REAL Cognito JWT signature verification, for routes the API Gateway does NOT validate.

🚨 WHY THIS EXISTS (the finding that gates the whole story). Everywhere else in this backend,
`dependencies._decode_jwt_payload` reads a Bearer token WITHOUT verifying its signature, and that is
correct *because* the API Gateway JWT authorizer already validated it before Lambda was invoked. That
assumption holds for exactly as long as the route carries the authorizer.

It does NOT hold on a route whose API Gateway `--authorization-type` is `NONE` — the public/free-tier
routes this story creates. Measured against the live API on 2026-08-04:

    forged unsigned JWT ({"cognito:groups":["subscriber","admin"]}) →
        GET /fantasy/nfl/track-record/manifest   (authorizer NONE)   → 200   ← reaches the Lambda
        GET /fantasy/nfl/projections             (authorizer JWT)    → 401
        GET /picks/today                         (authorizer JWT)    → 401

So on a public route the caller controls the entire token. An entitlement-aware public endpoint that
resolved `cognito:groups` through the usual unverified decode would hand the paid 2026 projections to
anyone who base64-encodes `{"cognito:groups":["subscriber"]}` — a WORSE leak than the static-blob one
this story was written to close, and one that looks perfectly correct in the FastAPI source.

⇒ any route that is public at the gateway AND varies its response by entitlement MUST verify the
signature here. `entitlement.resolve_entitlement` is the only sanctioned way to read groups on such a
route; it calls this module and treats an unverifiable token as ANONYMOUS.

Uses `python-jose[cryptography]`, already in the Lambda bundle (`infrastructure/lambda/deploy.sh`) —
no new dependency, nothing hand-rolled.

TOKEN SHAPE. The frontend sends the Cognito **ACCESS** token (`auth-context.tsx` puts
`session.getAccessToken()` on every `apiFetch`). Access tokens carry `token_use:"access"` and
`client_id` — they have NO `aud` claim (only ID tokens do), which is why the audience is checked
manually rather than through jose's `verify_aud`. ID tokens are accepted too so a future caller that
sends one is not silently treated as anonymous.

FAIL CLOSED. Every failure path — bad signature, expired, wrong issuer/audience, unknown `kid`,
unreachable JWKS — returns None, i.e. "not entitled". A verification outage degrades a paying
subscriber to the free view (visible, recoverable, and the CTA still renders); it can never promote
an anonymous caller. An unevaluable check is never scored as a pass (NF1.7 (a)).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request

from jose import jwt
from jose.utils import base64url_decode  # noqa: F401  (import proves the crypto backend is present)

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "us-east-1_gG9zMbwQt")
_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "1qh95e78bd7g6ipqcvdcpf7ou6")

ISSUER = f"https://cognito-idp.{_AWS_REGION}.amazonaws.com/{_USER_POOL_ID}"
_JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# JWKS cache. Cognito signing keys are effectively static (rotation is rare and additive), so a warm
# Lambda holds them for the container's life; the TTL bounds staleness after a rotation. A `kid` miss
# forces one immediate refetch (see `_jwks_for_kid`) so a rotation self-heals without waiting out the
# TTL — the cache can delay a NEW key by one request, never reject a valid one for an hour.
_JWKS_TTL_SECONDS = 3600
_JWKS_FETCH_TIMEOUT = 3.0
_jwks_lock = threading.Lock()
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0


def _fetch_jwks() -> dict | None:
    try:
        with urllib.request.urlopen(_JWKS_URL, timeout=_JWKS_FETCH_TIMEOUT) as resp:  # noqa: S310
            import json

            return json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — network/parse; fail closed, never raise into a request
        logger.warning("JWKS fetch failed from %s", _JWKS_URL, exc_info=True)
        return None


def _jwks_for_kid(kid: str, *, allow_refetch: bool = True) -> dict | None:
    """Return the JWK matching `kid`, refetching once on a miss (key rotation) or expiry."""
    global _jwks_cache, _jwks_fetched_at

    with _jwks_lock:
        expired = (time.monotonic() - _jwks_fetched_at) > _JWKS_TTL_SECONDS
        if _jwks_cache is None or expired:
            fresh = _fetch_jwks()
            if fresh is not None:
                _jwks_cache = fresh
                _jwks_fetched_at = time.monotonic()
        cache = _jwks_cache

    for key in (cache or {}).get("keys", []):
        if key.get("kid") == kid:
            return key

    if allow_refetch:
        # Unknown kid against a cache we did not just refresh → a rotation may have landed.
        with _jwks_lock:
            fresh = _fetch_jwks()
            if fresh is not None:
                _jwks_cache = fresh
                _jwks_fetched_at = time.monotonic()
        return _jwks_for_kid(kid, allow_refetch=False)
    return None


def reset_jwks_cache() -> None:
    """Drop the cached JWKS. Tests only — production relies on the TTL + kid-miss refetch."""
    global _jwks_cache, _jwks_fetched_at
    with _jwks_lock:
        _jwks_cache = None
        _jwks_fetched_at = 0.0


def verify_cognito_token(token: str | None) -> dict | None:
    """Return the token's VERIFIED claims, or None if it cannot be trusted.

    Checks, in order: a well-formed header with a `kid` and RS256; a JWKS key for that `kid`;
    the RSA signature; `exp`/`iat`; `iss` == this user pool; and the audience — `aud` for an ID
    token, `client_id` for an access token (Cognito access tokens have no `aud`).

    None means "treat as anonymous". It never raises: a verification failure inside a request must
    degrade the response, not 500 it.
    """
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    if token.count(".") != 2:
        return None

    try:
        header = jwt.get_unverified_header(token)
    except Exception:  # noqa: BLE001
        return None

    # Pin the algorithm from OUR side. Never take the token's word for it — an attacker-supplied
    # `alg` is the classic JWT confusion attack ("alg":"none" / HS256-signed-with-the-public-key).
    if header.get("alg") != "RS256":
        logger.warning("rejecting token with non-RS256 alg=%s", header.get("alg"))
        return None
    kid = header.get("kid")
    if not kid:
        return None

    key = _jwks_for_kid(kid)
    if key is None:
        logger.warning("no JWKS key for kid=%s", kid)
        return None

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=ISSUER,
            # Access tokens carry no `aud`; jose would reject them outright. The audience is
            # checked explicitly below against whichever claim this token type uses.
            options={"verify_aud": False},
        )
    except Exception:  # noqa: BLE001 — signature/exp/iss failures all mean "not trusted"
        logger.info("JWT verification failed", exc_info=True)
        return None

    token_use = claims.get("token_use")
    if token_use == "access":
        audience_ok = claims.get("client_id") == _APP_CLIENT_ID
    elif token_use == "id":
        aud = claims.get("aud")
        audience_ok = aud == _APP_CLIENT_ID or (
            isinstance(aud, list) and _APP_CLIENT_ID in aud
        )
    else:
        # Neither an access nor an ID token from this pool — refuse rather than guess.
        logger.warning("rejecting token with unexpected token_use=%r", token_use)
        return None

    if not audience_ok:
        logger.warning("rejecting token for a different app client")
        return None

    return claims


def verified_groups(token: str | None) -> list[str]:
    """The caller's Cognito groups from a SIGNATURE-VERIFIED token; [] if unverifiable.

    `cognito:groups` is a JSON array in the token payload itself (the bracketed-string mangling
    `dependencies._groups_from_request` works around is an API-Gateway *authorizer-context*
    artifact, not a property of the token), so no delimiter guessing is needed here.
    """
    claims = verify_cognito_token(token)
    if not claims:
        return []
    groups = claims.get("cognito:groups") or []
    if isinstance(groups, str):
        return [g.strip() for g in groups.replace(",", " ").split() if g.strip()]
    if isinstance(groups, list):
        return [str(g).strip() for g in groups if str(g).strip()]
    return []
