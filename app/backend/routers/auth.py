"""Auth endpoints + the server-side subscriber-MFA guard (E9.8).

POST /auth/refresh — exchange a Cognito refresh token for a new access token.

`require_subscriber_mfa` is a FastAPI dependency wired onto the paid content routers
(see main.py). It is the defense-in-depth backstop for E9.19's MFA enforcement, which
is otherwise frontend-only (a client redirect, trivially bypassed by hitting the API
directly). It rejects `subscriber`-group API calls whose Cognito account lacks a TOTP
(SOFTWARE_TOKEN_MFA) factor, EXEMPTING sessions that authenticated via a federated IdP
(Google) — those inherit MFA from the IdP and never enroll TOTP.

G100-C0-MFA extends that exemption to `passwordless`-group accounts and adds
`GET /auth/session-diagnostics`, the live instrument that makes the exemption verifiable
against the real pool rather than assumed. Read `_totp_exemption` first — it is the only
place in this file where getting a claim shape wrong is an MFA BYPASS rather than a bug.
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

from app.backend.dependencies import (
    _claims_from_event,
    get_optional_user_id,
    get_user_id,
    parse_groups_claim,
)
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


class TermsAcceptanceResult(BaseModel):
    """⭐ G100-D0-R1 — the authoritative answer to "did this sign-in create an account?".

    ⚠️ NF-C0 ADDITIVITY. This endpoint used to return 204 with NO body, so there is no key to
    remove or rename and an older deployed client — which discards the response entirely — is
    unaffected (`apiFetch` returns `null` for a 204 and the parsed object for a 200; neither
    caller inspected it before). The frontend reads this as ABSENT-vs-PRESENT rather than
    truthy-vs-falsy, exactly as `lib/terms.ts` already does for `tos_accepted_at`: the API
    Lambda ships only via `infrastructure/lambda/deploy.sh` while the frontend auto-deploys on
    merge to main, so there is always a window where a new client talks to a backend that has
    never heard of this field, and ABSENT must not be read as `created: false`.
    """

    #: True iff THIS call recorded the account's first acceptance — see record_tos_acceptance
    #: for why that is exactly-once even under a concurrent double-call.
    created: bool


@router.post("/accept-terms", response_model=TermsAcceptanceResult)
def accept_terms(user_id: str = Depends(get_user_id)) -> TermsAcceptanceResult:
    """Record ToS acceptance for the calling user, and report whether it was the first.

    Writes tos_accepted_at (if_not_exists, so the ORIGINAL timestamp is never overwritten)
    and tos_version to credence-prod-dynamo-users. Idempotent — safe to call repeatedly.

    ⭐ G100-D0-R1 — `created` IS THE SIGNUP SIGNAL, AND THE SERVER IS THE ONLY THING THAT CAN
    KNOW IT. `user_signup_completed` used to key on which BUTTON the visitor clicked, which the
    client stashes across the Cognito redirect. But Google federation auto-provisions an account
    at either door, so a first-time visitor who clicks *Sign In* got a real new account and
    emitted no signup event at all — and R1's ordered funnel discarded them outright (in the
    first 48h of production data, all 16 auth events used the /login door). This makes the
    signal a property of the ACCOUNT rather than of the affordance.

    ⚠️ "FIRST ACCEPTANCE" ≠ "ACCOUNT CREATED" — the residual, stated so nobody re-derives it:
    an account created BEFORE E9.58b started writing acceptance on every sign-in has no record,
    so its next acceptance reports `created: true` late. That population is bounded (operator-
    invited accounts predating 2026-08-06), one-time, and shrinking. The direction is the safe
    one for everything except that historical set, and Cognito creation dates remain the count
    of truth for new accounts (docs/g100_d0_funnel.md §3).

    🚨 E9.58b — THIS MUST NOT SWALLOW ITS FAILURE, and used to.
    It was written as a fire-and-forget call on the first-login set-password path, where a
    lost write was a small blemish on an account a human had personally created. E9.58 made
    Google self-serve signup public, so this is now the ONLY record that a given account
    agreed to anything — it is evidence, not telemetry. A caught-and-logged exception here
    returned 204 to the client, which reported success, so an account could be created and
    used with no acceptance on file and nothing anywhere would say so.
    The caller is expected to retry and, failing that, to block the user until it lands.
    """
    try:
        created = record_tos_acceptance(user_id, _TOS_VERSION)
    except Exception as exc:
        logger.exception("accept_terms: failed to record acceptance for %s", user_id)
        raise HTTPException(
            status_code=503, detail="Could not record your acceptance. Please try again."
        ) from exc
    return TermsAcceptanceResult(created=created)


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


def _groups_from_claims(claims: dict) -> set[str]:
    """The caller's Cognito groups, from the API-Gateway-VALIDATED claims only.

    ⛔ Deliberately NOT `dependencies._groups_from_request`, which unions in an UNVERIFIED
    bearer decode. That union is right for an entitlement read (it only ever grants access to
    someone who already holds a signed token) and wrong here, because these groups now drive
    an MFA EXEMPTION: on an `--authorization-type NONE` route there is no upstream validation,
    so a forged `{"cognito:groups":["subscriber","passwordless"]}` reaches the Lambda intact
    (measured — `services/jwt_verify.py`). Reading only the authorizer context means an
    exemption can never be self-asserted; the worst a forged token achieves is being gated.
    """
    return parse_groups_claim(claims.get("cognito:groups"))


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
    return _amr_names_a_federated_idp(claims) or _username_is_federated(claims)


def parse_amr(claims: dict) -> list[str]:
    """`amr` as a list, in every shape it arrives in (native list, JSON-string, bare string).

    ⭐ MEASURED 2026-08-13 AGAINST THE LIVE POOL, AND THE ANSWER IS "THERE IS NO `amr`."
    All three doors — password, Google, and a freshly-minted email-OTP (CUSTOM_AUTH) token
    straight out of `/verify` — deliver an ACCESS token whose claims are exactly:

        auth_time, client_id, cognito:groups, event_id, exp, iat, iss, jti,
        origin_jti, scope, sub, token_use, username

    No `amr`. No `identities`. The frontend sends the ACCESS token (`auth-context.tsx`
    resolves `at`), so that list is everything this guard will ever see.

    ⇒ `_amr_names_a_federated_idp` CANNOT FIRE IN PRODUCTION. It is kept because it costs
    nothing and an ID-token path would carry `amr`, but do not read it as a live signal, and
    ⛔ do not build a new rule on `amr` without re-measuring — on this token there is nothing
    to key on. This is also why the passwordless exemption had to be a GROUP: it was not the
    cheapest available signal, it was the ONLY one.
    """
    raw = claims.get("amr")
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return [str(x) for x in parsed] if isinstance(parsed, list) else [raw]
        except Exception:
            return [raw]
    return []


def _amr_names_a_federated_idp(claims: dict) -> bool:
    return any(
        re.search(r"google|federated|signinwithapple|facebook", a, re.IGNORECASE)
        for a in parse_amr(claims)
    )


def _username_is_federated(claims: dict) -> bool:
    """A bare federated profile's username is `<Provider>_<id>` with no '@'.

    ⚠️ This signal covers FEWER accounts than it looks like it does, and that gap is the whole
    of G100-C0-MFA: since pre-provisioning shipped, a Google-first user is linked into a NATIVE
    user whose username is a plain UUID, so this returns False for exactly the people who
    signed in with Google most recently.
    """
    username = str(claims.get("username") or claims.get("cognito:username") or "")
    return "@" not in username and bool(_FEDERATED_USERNAME_RE.match(username))


def _totp_exemption(claims: dict, groups: set[str]) -> str | None:
    """Why TOTP does not apply to THIS session, or None if it does.

    Returns a short reason string rather than a bool so the decision is legible in the logs
    and in `GET /auth/session-diagnostics` — at flip time the operator needs to know not just
    that someone was exempted but WHICH signal did it, because an exemption firing for an
    unexpected reason is precisely how this guard turns into an MFA bypass.

    ⭐ G100-C0-MFA adds the third reason, and it is the one that makes the flip safe. The two
    federated signals both fail for a passwordless account: a pre-provisioned or linked user's
    username is a plain UUID (not `google_…`), and `amr` is not something we may assume the
    shape of. Failing closed there was correct while the only alternative to a federated
    session was a PASSWORD session — an annoying re-verification. It stopped being correct
    when G100-C0 created a population with NO password: for them a 403 points at an enrollment
    screen whose only exit (`reauthenticatePassword`) asks for a credential they have never
    had, i.e. a locked-out paying customer with no self-service recovery.

    The `passwordless` group is the signal because it is written by US at account creation,
    travels inside the API-Gateway-validated token, and needs no pool schema change — unlike
    the client's `credence_auth_method` marker, which is client-controlled and must never gate
    a security decision.

    ⚠️ KNOWN AND DELIBERATE: the group describes the ACCOUNT, not the session. A person who
    later gives themselves a password through forgot-password keeps the exemption until the
    group is removed. That is bounded — the reset itself proves control of the same mailbox
    the exemption is predicated on.

    ⛔ AND THE OBVIOUS TIGHTENING IS NOT AVAILABLE. The plan was "exempt on the group AND on
    `amr` not indicating a password", pending a live reading. That reading came back on
    2026-08-13: the access token carries NO `amr` on ANY door (see `parse_amr`), so there is
    no per-session signal to add. The only real ways to close it are to REMOVE the group when
    someone sets a password, or to mint a claim from a PreTokenGeneration trigger. Neither is
    needed to ship; both are the honest candidates. Do not re-propose the `amr` version.
    """
    if _amr_names_a_federated_idp(claims):
        return "amr_federated"
    if _username_is_federated(claims):
        return "federated_username"
    if cognito_svc.GROUP_PASSWORDLESS in groups:
        return "passwordless_group"
    return None


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
    # Groups from the authorizer context — cheap, no Cognito call. ⚠️ Parsed by the shared
    # helper: this used to split on ',' ONLY, but the HTTP API v2 authorizer flattens the
    # claim to `[subscriber]` / `[fantasy_comp subscriber]`, so the comma split matched
    # nothing and the guard would have passed EVERY subscriber straight through the day it
    # was switched on — enforcement that reads as enabled and enforces nothing.
    groups = _groups_from_claims(claims)
    if cognito_svc.GROUP_SUBSCRIBER not in groups:
        return user_id  # only paying subscribers are gated
    if not user_id:
        return user_id  # can't identify the caller → not a resolvable subscriber call

    # Exempt sessions TOTP cannot apply to: a federated (Google) session inherits IdP MFA,
    # and a `passwordless` account has no password to re-authenticate with, so the enrollment
    # flow it would be sent to is a dead end (G100-C0-MFA).
    exemption = _totp_exemption(claims, groups)
    if exemption:
        logger.info("require_subscriber_mfa: exempt sub=%s reason=%s", user_id, exemption)
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


# ── The live instrument (G100-C0-MFA) ────────────────────────────────────────
# ⭐ THIS ENDPOINT EXISTS BECAUSE THE FIX IT SUPPORTS MUST NOT BE MADE BLIND. The
# passwordless exemption above is an MFA exemption on a paying account: get the claim shape
# wrong and it is a BYPASS, and CI — which mocks all IO and cannot see Cognito — passes just
# as happily either way. G100-C0 shipped without this fix precisely because nobody could see
# what a CUSTOM_AUTH session's token actually carries.
#
# So this reports, for the CALLER'S OWN session and nobody else's, exactly what the Lambda
# sees after the API Gateway authorizer has validated the token, plus the verdict the guard
# WOULD reach. That makes the acceptance test a measurement instead of an assumption, and it
# makes it runnable BEFORE `ENFORCE_SUBSCRIBER_MFA` is flipped and WITHOUT a real subscriber
# (`would_be_blocked_if_subscriber` answers the question hypothetically).
#
# Disclosure: everything here is derived from the token the caller already holds and could
# decode themselves, plus two booleans about their own account. The one genuinely new fact is
# `mfa_enforced`, and that is deliberate — it is how the operator confirms the flag is live on
# the Lambda they are actually hitting rather than inferring it from a status code, which is
# the failure this repo has already paid for once (G100-D1: "read the flag, don't infer it").

_GUARD_VERSION = "g100-c0-mfa/1"


class SessionDiagnostics(BaseModel):
    #: Bumped whenever this guard's logic changes ⇒ proves `deploy.sh` actually shipped the
    #: build being tested. A green CI and a merged PR do not put code on the Lambda.
    guard_version: str
    #: False ⇒ the API Gateway authorizer did not run for this route, so the claims below came
    #: from nothing trustworthy and no exemption may be read from them.
    authorizer_context_present: bool
    sub: str
    username: str | None = None
    #: Parsed groups, as the guard sees them.
    groups: list[str]
    #: The claim VERBATIM, so the delimiter style ("[a b]" vs "a,b") is visible rather than
    #: inferred — the exact detail that made the previous parse a no-op.
    groups_claim_raw: str | None = None
    groups_claim_type: str
    #: ⭐ The open empirical question this endpoint was built to answer: what `amr` a
    #: CUSTOM_AUTH (email-OTP) session and a linked-Google session actually carry.
    amr: list[str]
    amr_claim_raw: str | None = None
    amr_claim_type: str
    #: Present on any LINKED account, including on its password logins — which is why it is
    #: reported and never acted on (the E9.19 trap).
    identities_present: bool
    #: Claim NAMES only, never their values.
    claim_keys: list[str]
    mfa_enforced: bool
    is_subscriber: bool
    is_passwordless: bool
    totp_exempt: bool
    totp_exempt_reason: str | None = None
    #: None ⇒ the Cognito read failed; the guard treats that as not-enrolled (fails closed).
    totp_enrolled: bool | None = None
    would_be_blocked_if_subscriber: bool


@router.get("/session-diagnostics", response_model=SessionDiagnostics)
def session_diagnostics(
    request: Request, user_id: str = Depends(get_user_id)
) -> SessionDiagnostics:
    """What this session looks like to the server-side MFA guard. Self-only."""
    claims = _claims_from_event(request)
    groups = _groups_from_claims(claims)
    exemption = _totp_exemption(claims, groups)

    raw_groups = claims.get("cognito:groups")
    raw_amr = claims.get("amr")

    enrolled: bool | None
    try:
        enrolled = _has_totp(user_id)
    except Exception:
        logger.warning("session_diagnostics: MFA read failed for %s", user_id)
        enrolled = None

    return SessionDiagnostics(
        guard_version=_GUARD_VERSION,
        authorizer_context_present=bool(claims),
        sub=user_id,
        username=str(claims.get("username") or claims.get("cognito:username") or "") or None,
        groups=sorted(groups),
        groups_claim_raw=None if raw_groups is None else str(raw_groups),
        groups_claim_type=type(raw_groups).__name__,
        amr=parse_amr(claims),
        amr_claim_raw=None if raw_amr is None else str(raw_amr),
        amr_claim_type=type(raw_amr).__name__,
        identities_present=bool(claims.get("identities")),
        claim_keys=sorted(str(k) for k in claims),
        mfa_enforced=_mfa_enforced(),
        is_subscriber=cognito_svc.GROUP_SUBSCRIBER in groups,
        is_passwordless=cognito_svc.GROUP_PASSWORDLESS in groups,
        totp_exempt=exemption is not None,
        totp_exempt_reason=exemption,
        totp_enrolled=enrolled,
        # The two-sided answer, without needing a real subscription or the flag flipped:
        # exempt ⇒ never blocked; not exempt and not enrolled (incl. an unreadable read,
        # which fails closed) ⇒ blocked.
        would_be_blocked_if_subscriber=exemption is None and enrolled is not True,
    )
