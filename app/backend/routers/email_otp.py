"""G100-C0 — passwordless email sign-in (one-time code).

Two PUBLIC routes. They are the only way into the product that does not require a
Google account, and they are what widens the top of the funnel G100-D0 measures.

    POST /auth/email-otp/start   {email}                → send a code (or say "use Google")
    POST /auth/email-otp/verify  {email, code, session} → Cognito tokens

🔒 BOTH LEGS GO THROUGH THIS BACKEND RATHER THAN BROWSER-DIRECT, AND THAT IS THE
POINT. `amazon-cognito-identity-js` can drive CUSTOM_AUTH from the browser with no
server at all — which would also mean ANY caller could make Cognito email a code to
any address we have a user for, at whatever rate Cognito's generic per-user throttle
allows. Mail-bombing a customer, and burning our SES reputation doing it, would be a
few lines of console script. Routing `InitiateAuth` through here puts the send behind
a throttle we own (`_EMAIL_POLICY` / `_IP_POLICY`) and behind identity resolution, so
the only way to make us send mail is to ask us to.

🚦 THE GATEWAY IS NOT OPTIONAL (NF3.2). A router with no `Depends()` is NOT a public
route: the API Gateway JWT authorizer sits in FRONT of the Lambda and answers 401
before FastAPI is ever reached. Both routes below need an explicit
`--authorization-type NONE` route at the gateway or the entire feature 401s while
looking correct in every test. See the operator steps in `infrastructure/aws_resources.md`.

📭 ADDITIVE SHAPES ONLY (NF-C0). The API Lambda has no CD — it ships only via
`infrastructure/lambda/deploy.sh` — so the frontend and backend halves of this feature
deploy independently and there is always a skew window. These are brand-new routes, so
nothing older reads them; keep it that way by only ever ADDING response keys.
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.backend.services import identity as identity_svc
from app.backend.services.cost_guardrails import (
    RateLimiter,
    RateLimitPolicy,
    resolve_client_ip,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/email-otp", tags=["auth"])

_COGNITO_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "1qh95e78bd7g6ipqcvdcpf7ou6")
_COGNITO_USER_POOL = os.environ.get("COGNITO_USER_POOL_ID", "us-east-1_gG9zMbwQt")
_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


# ══════════════════════════════════════════════════════════════════════════════════
# Throttling
# ══════════════════════════════════════════════════════════════════════════════════
# Reuses G100-D1's token bucket rather than growing a second limiter: it is already
# memory-bounded for a 512 MB Lambda and already tested. A SEPARATE instance, though —
# sharing the global one would let ordinary browsing drain the OTP allowance and vice
# versa, so a single page load could stop someone signing in.
_OTP_LIMITER = RateLimiter(max_keys=20_000)

# Per ADDRESS: 3 sends, refilling one per 5 minutes. This is the mail-bomb bound — it
# is what one address can be made to receive, and it is deliberately the tighter of the
# two, because the harm of a flooded inbox lands on a person who did nothing wrong.
_EMAIL_POLICY = RateLimitPolicy(burst=3.0, per_second=1.0 / 300.0)

# Per SOURCE IP: 10 sends, refilling one per 3 minutes. Bounds a single script farming
# many addresses. Looser than the per-address bound on purpose — a shared NAT (an
# office, a campus, a phone carrier) is a legitimate many-users-one-IP case, and this
# must not become the reason a real person cannot sign in.
_IP_POLICY = RateLimitPolicy(burst=10.0, per_second=1.0 / 180.0)


def reset_throttles() -> None:
    """Drop all OTP buckets. For tests and a deliberate operator flush.

    ⚠️ The limiter is PROCESS-GLOBAL and STATEFUL, so a test file that sends OTPs
    leaks its bucket state into the next one and the failure presents as a wrong
    RESPONSE SHAPE (a 429 body where a 200 was expected), not as an obvious throttle.
    Call this in a fixture.
    """
    _OTP_LIMITER.reset()


def _client():
    return boto3.client("cognito-idp", region_name=_AWS_REGION)


# ══════════════════════════════════════════════════════════════════════════════════
# Wire shapes
# ══════════════════════════════════════════════════════════════════════════════════

class OtpStartRequest(BaseModel):
    email: str = Field(..., max_length=254)


class OtpStartResponse(BaseModel):
    """`next` is the whole point of the response: it tells the client which of the two
    doors this address goes through, so the UI never asks someone to watch an inbox
    that will stay empty."""

    #: "otp" → a code is on its way, show the code field.
    #: "google" → this address already signs in with a provider; show that button.
    next: str
    #: Masked ("ch•••@example.com") so a typo is visible without re-displaying a
    #: full address that someone else may have typed on a shared screen.
    masked_email: str
    #: Opaque Cognito auth session; hand it straight back to /verify. Absent for "google".
    session: str | None = None
    #: Human-readable provider name when `next == "google"`.
    provider: str | None = None


class OtpVerifyRequest(BaseModel):
    email: str = Field(..., max_length=254)
    code: str = Field(..., max_length=16)
    session: str = Field(..., max_length=4096)


class OtpVerifyResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str


# ══════════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════════

@router.post("/start", response_model=OtpStartResponse)
def start_email_otp(body: OtpStartRequest, request: Request) -> OtpStartResponse:
    """Resolve the address to ONE canonical account and begin a custom-auth challenge."""
    email = identity_svc.normalize_email(body.email)
    if not email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    # Throttle BEFORE any Cognito call, and IP first: an attacker enumerating many
    # addresses should exhaust their own bucket without ever costing us a lookup.
    client_ip = resolve_client_ip(request)
    if not _OTP_LIMITER.check(f"ip:{client_ip}", _IP_POLICY):
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts from this network. Please wait a few minutes.",
        )
    if not _OTP_LIMITER.check(f"email:{email}", _EMAIL_POLICY):
        raise HTTPException(
            status_code=429,
            detail="We've already sent a few codes to that address. Check your inbox, "
                   "including spam, and try again in a few minutes.",
        )

    found = identity_svc.classify(email)

    if found.state is identity_svc.IdentityState.FEDERATED_ONLY:
        # A pre-G100-C0 Google account with no native counterpart. Minting a native
        # user here would split them in two — see `identity.py` for why that cannot be
        # merged back. Send them to the door that already works.
        return OtpStartResponse(
            next="google",
            masked_email=_mask(email),
            provider=found.provider or "Google",
        )

    if found.state is identity_svc.IdentityState.DISABLED:
        # Covers both a deliberately disabled account and an unreadable Cognito answer
        # (`classify` fails CLOSED). Deliberately vague: naming which one would leak
        # whether the address is a locked-out customer.
        raise HTTPException(
            status_code=403,
            detail="This account can't sign in right now. Contact support@credencesports.com.",
        )

    if found.state is identity_svc.IdentityState.NEW:
        try:
            identity_svc.create_native_user(email)
        except Exception as exc:  # noqa: BLE001 — surfaces as an honest 503 below
            logger.exception("email-otp: could not create native user for %s", email)
            raise HTTPException(
                status_code=503,
                detail="We couldn't start sign-in just now. Please try again.",
            ) from exc

    session = _initiate_custom_auth(email)
    return OtpStartResponse(next="otp", masked_email=_mask(email), session=session)


@router.post("/verify", response_model=OtpVerifyResponse)
def verify_email_otp(body: OtpVerifyRequest, request: Request) -> OtpVerifyResponse:
    """Answer the challenge. On success Cognito mints the same token trio a Google
    sign-in produces, for the same `sub` — which is what makes the two methods one
    account rather than two."""
    email = identity_svc.normalize_email(body.email)
    if not email:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")

    code = body.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Enter the code from your email.")

    # A verify attempt is cheap and mails nothing, so it does NOT spend the send
    # budget — burning it here would let a wrong guess block the resend that fixes it.
    # The guess ceiling is enforced by Cognito's session (3 challenges, then the
    # session dies), which the client cannot tamper with.
    client_ip = resolve_client_ip(request)
    if not _OTP_LIMITER.check(f"verify:{client_ip}", _IP_POLICY):
        raise HTTPException(
            status_code=429,
            detail="Too many attempts from this network. Please wait a few minutes.",
        )

    try:
        resp = _client().admin_respond_to_auth_challenge(
            UserPoolId=_COGNITO_USER_POOL,
            ClientId=_COGNITO_CLIENT_ID,
            ChallengeName="CUSTOM_CHALLENGE",
            Session=body.session,
            ChallengeResponses={"USERNAME": email, "ANSWER": code},
        )
    except ClientError as exc:
        code_name = exc.response.get("Error", {}).get("Code", "")
        if code_name in ("NotAuthorizedException", "CodeMismatchException"):
            # Cognito kills the session after MAX_ATTEMPTS, which arrives here as
            # NotAuthorizedException. Both mean "start again" to the user.
            raise HTTPException(
                status_code=401,
                detail="That code didn't work. Request a new one and try again.",
            ) from exc
        if code_name == "UserNotFoundException":
            raise HTTPException(
                status_code=401, detail="That code didn't work. Request a new one."
            ) from exc
        logger.exception("email-otp: admin_respond_to_auth_challenge failed")
        raise HTTPException(status_code=503, detail="Auth service unavailable.") from exc

    result = resp.get("AuthenticationResult") or {}
    if not result.get("AccessToken"):
        # A wrong code comes back as another CHALLENGE, not an exception. Treating that
        # as success would hand the client an empty token set and present a failed
        # sign-in as a broken app.
        raise HTTPException(
            status_code=401,
            detail="That code didn't work. Check the code and try again.",
        )

    return OtpVerifyResponse(
        access_token=result["AccessToken"],
        id_token=result["IdToken"],
        refresh_token=result.get("RefreshToken", ""),
        expires_in=result.get("ExpiresIn", 3600),
        token_type=result.get("TokenType", "Bearer"),
    )


# ══════════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════════

def _initiate_custom_auth(email: str) -> str:
    """Open a CUSTOM_AUTH session. The CreateAuthChallenge trigger does the emailing;
    all we get back — and all the browser ever needs — is the opaque session handle."""
    try:
        resp = _client().admin_initiate_auth(
            UserPoolId=_COGNITO_USER_POOL,
            ClientId=_COGNITO_CLIENT_ID,
            AuthFlow="CUSTOM_AUTH",
            AuthParameters={"USERNAME": email},
        )
    except ClientError as exc:
        logger.exception("email-otp: admin_initiate_auth failed for %s", email)
        raise HTTPException(
            status_code=503,
            detail="We couldn't send a code just now. Please try again.",
        ) from exc

    session = resp.get("Session")
    if not session:
        # No session ⇒ no way to answer the challenge. Failing here is much better than
        # returning 200 with a null session and letting the user wait for a code they
        # could not have used anyway.
        logger.error("email-otp: admin_initiate_auth returned no Session for %s", email)
        raise HTTPException(
            status_code=503,
            detail="We couldn't send a code just now. Please try again.",
        )
    return session


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}•••@{domain}"
