"""G100-C0 — canonical identity resolution for the email-OTP sign-in path.

THE INVARIANT THIS SERVICE EXISTS TO HOLD
─────────────────────────────────────────
One human ⇒ exactly one Credence `user_id`, no matter which auth method they use.

The `user_id` is the NATIVE Cognito user's `sub` — that is not a new decision here,
it is the architecture E9.7 already established and every store already keys on
(`credence-prod-dynamo-user-bets`, `…-dynamo-users`, leagues, portfolio, alerts, and
the Cognito groups that carry entitlement). Federated identities are LINKED INTO that
native user by the PreSignUp trigger, so Google sign-in resolves to the same `sub`.

So the canonical-identity work for a SECOND auth method is not to invent a mapping
layer beside Cognito — it is to make sure the second method lands on the SAME native
user rather than minting a new one. Concretely, an email arriving at OTP is in exactly
one of three states, and only one of them may create anything:

    NEW             nobody has this address           → create the native user, send OTP
    NATIVE          a native user exists (incl. one   → send OTP to THAT user
                    that Google is linked into)
    FEDERATED_ONLY  only a bare federated profile     → ⛔ REFUSE. Send them to Google.

⭐ WHY `FEDERATED_ONLY` IS A REFUSAL AND NOT A MERGE. That profile's `sub` owns the
person's data. A native user we created for them would necessarily carry a DIFFERENT
sub, and the identity cannot be moved across: linking a provider identity that is
already an independent profile is precisely the case this repo's own PreSignUp README
resolves by DELETING that profile — which would take their bets and leagues with it.
So the only two options are "refuse" and "silently split the account", and a refusal
that says *use Google, you already have an account* costs one click while a split
account is invisible, permanent, and exactly what this story forbids.

⭐ AND THE SET IS CLOSED, NOT GROWING. `FEDERATED_ONLY` can only contain people who
signed in with Google BEFORE G100-C0's pre-provisioning shipped. From that deploy
onward every federated sign-in gets a native user created for it first
(`infrastructure/cognito/presignup_link/handler.py`), so new Google users are `NATIVE`
and OTP works for them on day one. This branch is a shrinking legacy tail, not a
permanent hole in the product.

DELIBERATE DISCLOSURE, STATED RATHER THAN HIDDEN
────────────────────────────────────────────────
Answering "this address uses Google" tells the caller an account exists. That is real
account enumeration and it is a considered trade: the alternative is telling someone
who HAS an account to check an inbox that will never receive anything, which strands
the exact person the story is trying to let in. Google, Slack and Notion all make the
same call. Everything else about the endpoint is non-enumerable — `NEW` and `NATIVE`
are byte-identical from outside, which is the case that actually matters, since it
covers every address that is not already a Google customer.
"""

from __future__ import annotations

import logging
import os
import secrets
import string
from dataclasses import dataclass
from enum import Enum

import boto3
from botocore.exceptions import ClientError

from app.backend.services import cognito as cognito_svc

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "us-east-1_gG9zMbwQt")

# Username prefixes Cognito gives a federated profile (`<provider>_<providerUserId>`).
# Kept in step with the PreSignUp trigger's `_FEDERATED_PREFIXES`; the agreement is
# pinned by `test_g100_c0_email_otp.py::test_the_two_implementations_agree_on_federated_prefixes`.
_FEDERATED_PREFIXES = ("google", "facebook", "signinwithapple", "loginwithamazon")

# Prefix → the name to show a human ("Continue with Google").
_PROVIDER_LABELS = {
    "google": "Google",
    "facebook": "Facebook",
    "signinwithapple": "Apple",
    "loginwithamazon": "Amazon",
}


class IdentityState(str, Enum):
    NEW = "new"
    NATIVE = "native"
    FEDERATED_ONLY = "federated_only"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Identity:
    """What we found for an email address, and what the caller may do about it."""

    state: IdentityState
    #: Cognito Username of the native user, when there is one. ⚠️ This is the pool's
    #: generated UUID, NOT the email — this pool uses email as a username ATTRIBUTE.
    username: str | None = None
    #: Display name of the federated provider, when `state is FEDERATED_ONLY`.
    provider: str | None = None

    @property
    def may_send_otp(self) -> bool:
        return self.state in (IdentityState.NEW, IdentityState.NATIVE)


def _client():
    return boto3.client("cognito-idp", region_name=_AWS_REGION)


def normalize_email(raw: str | None) -> str | None:
    """Lower-case and trim, or None if this cannot be an email address.

    ⛔ DELIBERATELY DOES NOT canonicalise provider-specific aliasing (stripping Gmail
    dots, cutting `+tags`). Those addresses are DISTINCT Cognito users, so folding
    them here would resolve one person's OTP onto a different person's account —
    an identity service's worst possible failure. Case folding is safe because
    Cognito already treats the email attribute case-insensitively for sign-in.
    """
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        return None
    if " " in cleaned or len(cleaned) > 254:  # RFC 5321 maximum
        return None
    local, _, domain = cleaned.partition("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return None
    return cleaned


def _is_federated(username: str) -> bool:
    if "_" not in username:
        return False
    return username.split("_", 1)[0].lower() in _FEDERATED_PREFIXES


def _provider_label(username: str) -> str:
    prefix = username.split("_", 1)[0].lower()
    return _PROVIDER_LABELS.get(prefix, prefix.title() or "your original provider")


def classify(email: str, *, user_pool_id: str | None = None) -> Identity:
    """Which of the three states `email` is in. Never raises — a lookup failure is
    reported as NEW's opposite, `DISABLED`, so a Cognito outage cannot cause us to
    create a duplicate account for someone who already has one.

    ⭐ FAILING CLOSED IS THE RIGHT DIRECTION HERE and it is the reverse of the
    PreSignUp trigger's fail-OPEN. There, an error costs a sign-in that would
    otherwise work; here, an error would cost a DUPLICATE ACCOUNT — a permanent,
    silent data split. Refusing to act on an unreadable answer is recoverable; acting
    on one is not.
    """
    pool = user_pool_id or _USER_POOL_ID
    try:
        resp = _client().list_users(
            UserPoolId=pool, Filter=f'email = "{email}"', Limit=10
        )
    except ClientError:
        logger.exception("identity.classify: list_users failed for %s", email)
        return Identity(state=IdentityState.DISABLED)

    users = resp.get("Users", []) or []
    federated: list[str] = []
    for user in users:
        username = user.get("Username") or ""
        if not username:
            continue
        if _is_federated(username):
            federated.append(username)
            continue
        # A native match. A DISABLED account must not be handed a fresh way in — that
        # would make OTP a bypass for the one action an operator takes to lock someone
        # out. Reported distinctly so the route can say something true.
        if user.get("Enabled") is False:
            return Identity(state=IdentityState.DISABLED, username=username)
        return Identity(state=IdentityState.NATIVE, username=username)

    if federated:
        return Identity(
            state=IdentityState.FEDERATED_ONLY, provider=_provider_label(federated[0])
        )
    return Identity(state=IdentityState.NEW)


# ── Native-user creation ───────────────────────────────────────────────────────
# ⚠️ THIS MIRRORS `infrastructure/cognito/presignup_link/handler.py::_preprovision_native_user`.
# The duplication is forced — a Cognito trigger Lambda is a separate deployment artifact
# and cannot import from `app.backend`. What it must NOT be is undetected drift, so the
# load-bearing properties (suppressed invite, email_verified, permanent password, and
# using the RESPONSE's Username) are pinned across BOTH files by
# `test_g100_c0_email_otp.py::TestNativeUserCreationAgreesAcrossImplementations`.

_GENERATED_PASSWORD_LENGTH = 32
_SYMBOLS = "!@#$%^&*()-_=+"


def _random_password() -> str:
    """An unguessable password nobody is ever told, spanning every character class so it
    cannot fail the pool's policy by chance. See the trigger's twin for why it exists at
    all: it moves the account out of FORCE_CHANGE_PASSWORD, where CUSTOM_AUTH cannot run."""
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice(_SYMBOLS),
    ]
    alphabet = string.ascii_letters + string.digits + _SYMBOLS
    rest = [secrets.choice(alphabet) for _ in range(_GENERATED_PASSWORD_LENGTH - len(required))]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def create_native_user(email: str, *, user_pool_id: str | None = None) -> str:
    """Create the native Cognito user that will own this person's `user_id`.

    Returns the Cognito Username (the pool's generated UUID — NOT the email). Raises
    on failure; the caller turns that into a 503 rather than pretending a code was sent.

    `email_verified` is set to **false**: nothing has proven ownership at this point,
    and the whole reason native self-signup is closed on this pool is that an unverified
    account is a dead end. The existing `POST /auth/verify-email` flips it to true after
    the first successful sign-in — which for OTP is precisely the moment ownership IS
    proven, since the code only reaches the real mailbox.
    """
    pool = user_pool_id or _USER_POOL_ID
    client = _client()
    resp = client.admin_create_user(
        UserPoolId=pool,
        Username=email,
        # SUPPRESS or Cognito mails a "your temporary password is…" invite for an
        # account the person never asked for and could not use if they wanted to.
        MessageAction="SUPPRESS",
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "false"},
        ],
    )
    username = (resp.get("User") or {}).get("Username")
    if not username:
        raise RuntimeError("admin_create_user returned no Username")

    client.admin_set_user_password(
        UserPoolId=pool, Username=username, Password=_random_password(), Permanent=True
    )

    # G100-C0-MFA — record, in the one place a later API call can actually SEE it, that this
    # account has no user-chosen password. Cognito groups ride inside the API-Gateway-validated
    # token, so `require_subscriber_mfa` can exempt this person from TOTP without trusting
    # anything the client says. Without it, the day `ENFORCE_SUBSCRIBER_MFA=1` flips, an OTP
    # subscriber is 403'd into an enrollment screen whose only exit asks for the password this
    # function deliberately never gave them.
    cognito_svc.mark_passwordless(username, client=client, user_pool_id=pool)

    logger.info("identity: created native user %s", username)
    return username
