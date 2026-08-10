"""Cognito CUSTOM_AUTH triggers — passwordless email OTP sign-in (G100-C0).

ONE Lambda serving all three custom-auth triggers, switched on `triggerSource`
(the shape AWS's own passwordless sample uses):

    DefineAuthChallenge          — how many challenges, and when to issue tokens
    CreateAuthChallenge          — mint the 6-digit code and email it via SES
    VerifyAuthChallengeResponse  — compare what the user typed

WHY OTP AND NOT EMAIL/PASSWORD. Native self-signup is disabled on this pool
permanently: it has no email auto-verification, so a self-registered password
account can never confirm itself or reset its password (verified live, E9.57 —
see `infrastructure/aws_resources.md`). OTP sidesteps that dead end entirely
because the code IS the proof of email ownership; there is no separate
verification step to be missing.

WHY NOT A MAGIC LINK. A link authenticates whatever device OPENS it, which on
mobile is routinely a webview inside the mail client rather than the browser the
person started in — so the session lands somewhere they cannot see. A typed code
authenticates the tab that asked for it, works cross-device, and is a shape
people already recognise. `input-otp` was already a dependency.

─────────────────────────────────────────────────────────────────────────────────
THREE THINGS THAT MAKE THIS SAFE (each is a way an OTP flow looks fine and isn't)
─────────────────────────────────────────────────────────────────────────────────

1. ⭐ A RETRY MUST NOT MINT — OR EMAIL — A NEW CODE. Cognito re-invokes
   CreateAuthChallenge for EVERY wrong answer. The obvious implementation
   generates a fresh code each time, which (a) mails the user once per typo and
   (b) makes the code they are looking at permanently stale, so a correct reading
   of a real email fails forever. The code is minted once and carried across
   retries in `challengeMetadata` — Cognito's own encrypted session, never
   exposed to the client. `_recover_code` is that carry.

2. ⭐ AN UNKNOWN ADDRESS MUST BEHAVE EXACTLY LIKE A KNOWN ONE. Cognito sets
   `userNotFound: true` rather than erroring, precisely so the flow can be made
   non-enumerable. We still issue a challenge and still return the same shape —
   we simply mint a code nobody holds and send no email. Short-circuiting on
   `userNotFound` would turn this endpoint into an "is this person a customer?"
   oracle for anyone who can type an email address.

3. ⭐ ATTEMPTS ARE COUNTED FROM COGNITO'S SESSION, NOT FROM ANYTHING WE STORE.
   The session is server-side and tamper-evident; a client-side or best-effort
   attempt counter is one the attacker controls. Three tries against a 6-digit
   code is a 3-in-a-million ceiling, and the session's own validity window
   (`AuthSessionValidity` on the app client) is the expiry.

IAM (execution role):
    ses:SendEmail  on the `credencesports.com` identity
    (no cognito-idp permissions — the triggers are invoked BY Cognito and mutate
     nothing; they only read the event and return it)
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ses = boto3.client("sesv2")

# ── Tunables ────────────────────────────────────────────────────────────────────
# 6 digits is the shape autofill recognises on iOS/Android ("from Messages/Mail"),
# which matters more for completion rate than the extra entropy of 8 would.
CODE_LENGTH = 6
# Three tries. Enough for a genuine misread, far too few to search 10^6.
MAX_ATTEMPTS = 3

# Prefix on `challengeMetadata` — see hazard 1. Cognito uses this field to let a
# custom flow distinguish challenge TYPES; we additionally use it as the carrier
# for the issued code across retries. It is server-side session state and is not
# returned to the client.
_METADATA_PREFIX = "CODE-"

_FROM_ADDRESS = os.getenv("OTP_FROM_ADDRESS", "noreply@credencesports.com")
_CONFIG_SET = os.getenv("SES_CONFIGURATION_SET", "credence-prod-ses-config")
# Display only. The real expiry is the Cognito app client's `AuthSessionValidity`;
# this string must be kept in step with it or the email tells the user something
# the system will not honour.
_TTL_MINUTES = os.getenv("OTP_TTL_MINUTES", "15")

_SUBJECT = "Your Credence sign-in code"


def generate_code() -> str:
    """A cryptographically random zero-padded code.

    `secrets.randbelow`, not `random` — this is a credential. Zero-padded so every
    code is exactly CODE_LENGTH digits: a variable-length code breaks fixed-length
    input UIs and leaks a sliver of entropy through its length.
    """
    return str(secrets.randbelow(10**CODE_LENGTH)).zfill(CODE_LENGTH)


def mask_email(email: str) -> str:
    """`charlie@example.com` → `ch•••@example.com`, for the "we sent a code to…" line.

    Shown so someone who typo'd their address can SEE that they did, without the
    page re-displaying an address an attacker may have typed into a shared screen.
    """
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    head = local[:2] if len(local) > 2 else local[:1]
    return f"{head}•••@{domain}"


def _custom_challenges(session: list) -> list:
    """Only the CUSTOM_CHALLENGE entries of the auth session.

    Filtered rather than taken wholesale: Cognito can prepend entries for other
    challenge names, and counting those as attempts would lock a user out after
    fewer real tries than the policy states.
    """
    return [s for s in session if (s or {}).get("challengeName") == "CUSTOM_CHALLENGE"]


def _recover_code(session: list) -> str | None:
    """The code issued by the FIRST challenge of this session, if there was one.

    See hazard 1 — this is what makes a retry re-use the code already in the
    user's inbox instead of superseding it.
    """
    for entry in reversed(_custom_challenges(session)):
        metadata = (entry or {}).get("challengeMetadata") or ""
        if metadata.startswith(_METADATA_PREFIX):
            return metadata[len(_METADATA_PREFIX):]
    return None


# ── DefineAuthChallenge ─────────────────────────────────────────────────────────

def define_auth_challenge(event: dict) -> dict:
    request = event.get("request", {}) or {}
    response = event.setdefault("response", {})
    attempts = _custom_challenges(request.get("session") or [])

    if attempts and attempts[-1].get("challengeResult") is True:
        # Correct code → Cognito mints the id/access/refresh tokens.
        response["issueTokens"] = True
        response["failAuthentication"] = False
        return event

    if len(attempts) >= MAX_ATTEMPTS:
        response["issueTokens"] = False
        response["failAuthentication"] = True
        return event

    response["issueTokens"] = False
    response["failAuthentication"] = False
    response["challengeName"] = "CUSTOM_CHALLENGE"
    return event


# ── CreateAuthChallenge ─────────────────────────────────────────────────────────

def create_auth_challenge(event: dict) -> dict:
    request = event.get("request", {}) or {}
    response = event.setdefault("response", {})
    session = request.get("session") or []
    user_not_found = bool(request.get("userNotFound"))
    email = (request.get("userAttributes") or {}).get("email") or ""

    code = _recover_code(session)
    is_first_issue = code is None
    if is_first_issue:
        code = generate_code()

    # Send ONLY on the first issue, and never for an address with no account — see
    # hazards 1 and 2. An unknown address still gets a challenge and a code; the
    # code simply belongs to nobody, so the flow is shaped identically from outside.
    if is_first_issue and not user_not_found and email:
        _send_code_email(email, code)

    response["privateChallengeParameters"] = {"code": code}
    # Returned to the client. The masked address only — never the code, and never
    # the full address the caller supplied.
    response["publicChallengeParameters"] = {"email": mask_email(email)}
    response["challengeMetadata"] = f"{_METADATA_PREFIX}{code}"
    return event


def _send_code_email(email: str, code: str) -> None:
    """Deliver the code. Never raises: a send failure must fail the SIGN-IN, not the
    trigger — a raised exception here surfaces to the user as an opaque Cognito
    error, whereas returning normally lets them hit "resend" and try again."""
    try:
        ses.send_email(
            FromEmailAddress=_FROM_ADDRESS,
            Destination={"ToAddresses": [email]},
            ConfigurationSetName=_CONFIG_SET,
            Content={
                "Simple": {
                    "Subject": {"Data": _SUBJECT},
                    "Body": {
                        "Text": {"Data": _text_body(code)},
                        "Html": {"Data": _html_body(code)},
                    },
                }
            },
        )
        logger.info("email-otp: sent code to %s", mask_email(email))
    except Exception:
        # Log the MASKED address — a CloudWatch log group is a wider audience than
        # the mailbox, and this line would otherwise be a plaintext address dump.
        logger.warning("email-otp: SES send failed for %s", mask_email(email), exc_info=True)


def _text_body(code: str) -> str:
    return (
        f"Your Credence sign-in code is {code}\n\n"
        f"It expires in {_TTL_MINUTES} minutes and can be used once.\n\n"
        "If you didn't try to sign in, you can ignore this email — "
        "nobody can get in without this code.\n"
    )


def _html_body(code: str) -> str:
    # Deliberately minimal, table-free, inline-styled: this is a transactional code
    # people read in a notification preview, and heavy markup is what gets such mail
    # filtered. The brand green matches the app's primary.
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:420px;margin:0 auto;padding:24px;color:#0a0a0a">'
        '<p style="font-size:15px;margin:0 0 20px">Your Credence sign-in code:</p>'
        f'<p style="font-size:34px;font-weight:700;letter-spacing:.32em;margin:0 0 20px;'
        f'color:#059669">{code}</p>'
        f'<p style="font-size:13px;color:#525252;margin:0 0 8px">Expires in {_TTL_MINUTES} '
        "minutes and can be used once.</p>"
        '<p style="font-size:13px;color:#525252;margin:0">If you didn\'t try to sign in, '
        "ignore this email — nobody can get in without this code.</p>"
        "</div>"
    )


# ── VerifyAuthChallengeResponse ─────────────────────────────────────────────────

def verify_auth_challenge(event: dict) -> dict:
    request = event.get("request", {}) or {}
    response = event.setdefault("response", {})

    expected = (request.get("privateChallengeParameters") or {}).get("code") or ""
    # Normalise what a human actually types: autofill and paste routinely carry
    # surrounding whitespace, and rejecting "123456 " as a wrong code is a defect the
    # user cannot see the cause of.
    supplied = str(request.get("challengeAnswer") or "").strip()

    # `compare_digest`, not `==` — a short-circuiting comparison on a live credential
    # is a timing oracle. Also refuse an EMPTY expected value outright: without this,
    # any path that failed to set a code (a bug, or the userNotFound branch had it
    # cleared) would authenticate anyone who submits an empty answer.
    response["answerCorrect"] = bool(expected) and hmac.compare_digest(supplied, expected)
    return event


# ── Entry point ────────────────────────────────────────────────────────────────

_ROUTES = {
    "DefineAuthChallenge_Authentication": define_auth_challenge,
    "CreateAuthChallenge_Authentication": create_auth_challenge,
    "VerifyAuthChallengeResponse_Authentication": verify_auth_challenge,
}


def handler(event, context):  # noqa: ANN001, ARG001 (Lambda signature)
    trigger = (event or {}).get("triggerSource", "")
    route = _ROUTES.get(trigger)
    if route is None:
        # An unrecognised trigger is returned untouched. Cognito invokes one Lambda per
        # trigger TYPE, so this only fires if the function is wired somewhere it was not
        # designed for — in which case passing the event through unchanged is the
        # neutral act, not a good moment to raise.
        logger.info("email-otp: ignoring unexpected triggerSource %r", trigger)
        return event
    return route(event)
