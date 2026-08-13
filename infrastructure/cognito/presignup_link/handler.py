"""Cognito PreSignUp trigger — make every human resolve to exactly ONE native Cognito
user, whichever auth method they arrive with.

Why this exists (E9.7):
    The app keys ALL per-user data (bets, portfolio, alerts) by the Cognito `sub`
    claim (see app/backend/dependencies.py::get_user_id). But a Google sign-in
    creates a SEPARATE user (username "Google_<sub>") with a DIFFERENT `sub` than
    the person's native username/password account — so the federated user sees an
    empty account (the "my bets don't show under Google login" bug). Linking the
    Google identity into the existing native user makes Google sign-in resolve to
    that native user's `sub`, so both login methods reach the same account.

How it works:
    On the FIRST Google sign-in for an email, Cognito fires PreSignUp with
    triggerSource == "PreSignUp_ExternalProvider" BEFORE creating the federated
    user. We look up any existing native user with the same (verified) email and
    call admin_link_provider_for_user to link Google → that native user. Cognito
    then authenticates the sign-in AS the native user (same sub) and does NOT
    create a duplicate. Native username/password sign-ups pass through untouched.

─────────────────────────────────────────────────────────────────────────────────
G100-C0 — PRE-PROVISION, so the invariant holds in BOTH arrival orders
─────────────────────────────────────────────────────────────────────────────────
E9.7 linked Google into a native user only WHEN ONE ALREADY EXISTED. That covers
"native account first, Google second" and silently does nothing the other way
round: a Google-FIRST person ends up as a bare federated profile with no native
counterpart. That was invisible while Google was the only self-serve method — and
it becomes the duplicate-account bug the moment a second method (G100-C0's email
OTP) can also create an account, because OTP needs a NATIVE user to authenticate
and would have to mint a second one for the same human.

⭐ THE ORDER OF ARRIVAL MUST NOT DECIDE THE ARCHITECTURE. So on a brand-new
federated sign-in with no native counterpart we CREATE the native user first
(suppressed invite, permanent random password so the account lands CONFIRMED
rather than FORCE_CHANGE_PASSWORD) and link Google into that. From here on:

    Google first, OTP later  →  OTP finds the native user      →  one sub ✅
    OTP first, Google later  →  this trigger links into it     →  one sub ✅

so "one Credence user_id ↔ many auth identities" is enforced by Cognito itself,
with no app-level alias map and no change to any storage key (every user's
canonical id is still their own `sub`).

⚠️ THIS DOES NOT RETROACTIVELY FIX ANYONE. A federated profile that already exists
has no native counterpart and cannot grow one: its `sub` — which owns that
person's data — belongs to the federated profile, and linking a provider identity
that is ALREADY an independent profile is exactly the case this repo's own README
resolves by DELETING that profile. So pre-existing Google-only accounts are
handled by refusing OTP for them with an honest "continue with Google" (see
`app/backend/services/identity.py`), never by minting a duplicate.

⚠️ FAIL-OPEN IS LOAD-BEARING HERE, more than anywhere else in the repo: this
trigger sits in front of the ONLY public signup path. Every new failure mode below
returns the event unchanged, which degrades to exactly the pre-G100-C0 behaviour
(a plain federated account) rather than to a broken signup. `PRESIGNUP_PREPROVISION=0`
is the operator's instant kill switch — no redeploy, no code change.

Deploy: see README.md in this directory (function + role + trigger + IAM + the
    one-time cleanup for accounts that already have a duplicate Google user).

IAM (execution role) — on the pool ARN:
    cognito-idp:ListUsers
    cognito-idp:AdminLinkProviderForUser
    cognito-idp:AdminCreateUser        (G100-C0 pre-provision)
    cognito-idp:AdminSetUserPassword   (G100-C0 pre-provision)
    cognito-idp:AdminAddUserToGroup    (G100-C0-MFA passwordless marking)
"""

from __future__ import annotations

import logging
import os
import secrets
import string

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client("cognito-idp")

# Provider-name prefixes that indicate a federated (not native) Cognito user. We
# only ever link INTO a native user, never chain one federated identity to another.
# Matched case-insensitively (Cognito stores the prefix in the IdP's configured case,
# e.g. "google_<sub>" here — see the E9.7 CloudWatch finding).
_FEDERATED_PREFIXES = ("google", "facebook", "signinwithapple", "loginwithamazon")

# Providers whose email claim we trust as verified even when the IdP attribute mapping
# doesn't pass `email_verified` through to the PreSignUp event (the common case — that
# attribute was ABSENT, so a strict `== "true"` check silently skipped every link).
# Google verifies email ownership before ever releasing the email claim, so this is safe
# for our only configured IdP. An explicit `email_verified=false` is still honored below.
_TRUSTED_VERIFIED_PROVIDERS = ("google", "facebook", "signinwithapple", "loginwithamazon")

# Cognito LOWERCASES the provider name in the federated username (e.g. "google_<sub>"),
# but admin_link_provider_for_user's SourceProviderName must match the IdP's CONFIGURED
# name EXACTLY, which for the managed social providers is title-cased. Map the lowercase
# username prefix back to the canonical configured name. (Confirmed by the E9.7
# "SourceProviderName must match a Provider…" failure.)
_PROVIDER_CANONICAL = {
    "google": "Google",
    "facebook": "Facebook",
    "signinwithapple": "SignInWithApple",
    "loginwithamazon": "LoginWithAmazon",
}


def handler(event, context):  # noqa: ANN001, ARG001 (Lambda signature)
    # Only external-provider (Google) sign-ups. Native sign-ups
    # (PreSignUp_SignUp) and admin-created users pass straight through.
    trigger = event.get("triggerSource")
    incoming_username = event.get("userName", "")
    if trigger != "PreSignUp_ExternalProvider":
        return event

    user_pool_id = event["userPoolId"]
    attrs = event.get("request", {}).get("userAttributes", {})
    email = attrs.get("email")
    if not email:
        logger.info("presignup-link: no email attribute on %s — skipping", incoming_username)
        return event

    # For an external provider the incoming userName is "<Provider>_<providerUserId>",
    # e.g. "google_100868166396155863973". Split into the provider name + subject.
    if "_" not in incoming_username:
        logger.info("presignup-link: unexpected username format %r — skipping", incoming_username)
        return event
    provider_name, provider_uid = incoming_username.split("_", 1)

    # Verification gate. Cognito reports email_verified=false (or omits it) for a Google
    # federation whenever the IdP attribute mapping doesn't pass Google's own
    # `email_verified` through — the DEFAULT, and the confirmed cause here. That `false`
    # is a Cognito artifact, NOT Google saying the email is unverified: Google verifies
    # email ownership before it ever releases the email claim. So for a TRUSTED provider
    # (the IdPs we deliberately configured) we link regardless of the reported value;
    # any future UNTRUSTED provider must still assert email_verified=true.
    ev = str(attrs.get("email_verified", "")).lower()
    provider_trusted = provider_name.lower() in _TRUSTED_VERIFIED_PROVIDERS
    if not provider_trusted and ev != "true":
        logger.info(
            "presignup-link: %s from untrusted provider without verified email — skipping",
            incoming_username,
        )
        return event

    # Find an EXISTING user with this email that isn't the incoming federated identity
    # and isn't itself federated → the native account to link into.
    try:
        resp = cognito.list_users(
            UserPoolId=user_pool_id,
            Filter=f'email = "{email}"',
            Limit=10,
        )
    except Exception:
        # Fail OPEN: never block a sign-in because the lookup failed. Worst case the
        # user gets an unlinked federated account (recoverable), not a locked-out one.
        logger.warning("presignup-link: list_users failed for email=%s", email, exc_info=True)
        return event

    target = _pick_link_target(resp.get("Users", []), incoming_username)
    if not target:
        # G100-C0 — no native counterpart yet. PRE-PROVISION one so this person has a
        # native `sub` that a later email-OTP sign-in can authenticate against, instead
        # of the OTP path being forced to mint a second account for the same human.
        if not preprovision_enabled():
            logger.info(
                "presignup-link: no native user for %s and pre-provisioning is OFF "
                "— plain federated account (pre-G100-C0 behaviour)", email,
            )
            return event
        target = _preprovision_native_user(user_pool_id, email)
        if not target:
            # Fail OPEN: creation failed → let Cognito make the ordinary federated user.
            # Strictly no worse than the pre-G100-C0 behaviour.
            return event

    # Resolve the username prefix ("google") to the IdP's configured name ("Google").
    source_provider = _PROVIDER_CANONICAL.get(provider_name.lower(), provider_name)
    try:
        cognito.admin_link_provider_for_user(
            UserPoolId=user_pool_id,
            DestinationUser={
                "ProviderName": "Cognito",
                "ProviderAttributeValue": target,
            },
            SourceUser={
                "ProviderName": source_provider,         # canonical, e.g. "Google"
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": provider_uid,  # the Google sub
            },
        )
        logger.info(
            "presignup-link: linked %s (provider %s) → native user %s",
            incoming_username, source_provider, target,
        )
    except Exception:
        # Fail OPEN again: a link error must not hard-block the person from signing in.
        logger.warning(
            "presignup-link: admin_link_provider_for_user failed (%s → %s)",
            incoming_username, target, exc_info=True,
        )

    return event


def preprovision_enabled() -> bool:
    """Whether to create a native user for a brand-new federated sign-in (G100-C0).

    Read at CALL time, not import time, so `aws lambda update-function-configuration`
    takes effect on the warm fleet immediately — the same reasoning as
    `cost_guardrails.degrade_mode_enabled`.

    ⭐ DEFAULT ON, and the env var is a KILL SWITCH rather than an enabler. A
    default-OFF flag would put this repo's documented-but-never-set landmine
    (`W7B_LAKEHOUSE_S3`) in front of the only public signup path: the docs would
    describe one-account-per-human while production quietly kept minting split
    accounts, and nothing would say so. Default-on means the deployed behaviour and
    the documented behaviour agree unless someone deliberately disagrees with them,
    and the operator still gets a no-redeploy rollback.
    """
    return os.getenv("PRESIGNUP_PREPROVISION", "1").strip().lower() not in ("0", "false", "no")


# Long enough that it is unguessable, and deliberately spanning every character class so
# it satisfies any Cognito password policy the pool might have. NOBODY EVER LEARNS THIS
# VALUE — not the user, not us. It exists only to move the account out of
# FORCE_CHANGE_PASSWORD (where CUSTOM_AUTH cannot run) into CONFIRMED. The person's real
# credential is their Google identity or an emailed OTP; if they ever want a password they
# get one through the ordinary forgot-password flow, which proves email ownership first.
_GENERATED_PASSWORD_LENGTH = 32


def _random_password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    # Guarantee one of each required class up front, then fill and shuffle, so this can
    # never fail the policy by chance (a pure random draw can legitimately omit a class,
    # and that failure would surface as a broken signup for one unlucky user).
    required = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*()-_=+"),
    ]
    rest = [secrets.choice(alphabet) for _ in range(_GENERATED_PASSWORD_LENGTH - len(required))]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def _preprovision_native_user(user_pool_id: str, email: str) -> str | None:
    """Create the native Cognito user that a federated identity will be linked into.

    Returns the created user's Username, or None on any failure (caller fails open).

    ⚠️ RETURN THE RESPONSE'S Username, NEVER THE EMAIL WE PASSED IN. This pool uses
    email as a username ATTRIBUTE, so Cognito assigns a generated UUID as the actual
    Username (prod native users look like "14187448-c091-705c-1199-63858b12c986").
    admin_link_provider_for_user's DestinationUser must be that UUID; passing the email
    would target a user that does not exist under that name.

    `email_verified=true` is correct here for the same reason the link gate above trusts
    these providers: Google verifies ownership of the address before it will release the
    email claim at all. An untrusted IdP never reaches this line — the verification gate
    returns earlier.
    """
    try:
        resp = cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            # SUPPRESS or Cognito emails this person a "your temporary password is…"
            # invite for an account they never asked for and can never use.
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
        )
        username = (resp.get("User") or {}).get("Username")
        if not username:
            logger.warning("presignup-link: admin_create_user returned no Username for %s", email)
            return None

        # Permanent password ⇒ status CONFIRMED. Without this the account sits in
        # FORCE_CHANGE_PASSWORD, where the email-OTP CUSTOM_AUTH flow cannot run — the
        # account would exist and still not be usable by the method it was created for.
        cognito.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=username,
            Password=_random_password(),
            Permanent=True,
        )
        _mark_passwordless(user_pool_id, username)
        logger.info("presignup-link: pre-provisioned native user %s for %s", username, email)
        return username
    except Exception:
        # Includes the benign race where a concurrent sign-in created it first
        # (UsernameExistsException). Failing open costs that person a split account —
        # bad — but raising costs them their sign-in entirely, which is worse, and the
        # split case is recoverable by hand while a signup outage is not.
        logger.warning("presignup-link: pre-provision failed for %s", email, exc_info=True)
        return None


# ⭐ G100-C0-MFA — the group that means "this account has never had a user-chosen password".
# MUST stay byte-identical to `app.backend.services.cognito.GROUP_PASSWORDLESS`; a trigger
# Lambda is a separate deployment artifact and cannot import it, so the agreement is pinned by
# `test_g100_c0_mfa_passwordless.py::TestBothCreationPathsMarkTheAccountPasswordless`.
# The pre-provisioned user below is created with a random password nobody is ever told, so the
# person's only credentials are Google and an emailed code — neither of which can satisfy the
# TOTP-enrollment flow. Without this group, `ENFORCE_SUBSCRIBER_MFA=1` 403s them with no way out.
_PASSWORDLESS_GROUP = "passwordless"


def _mark_passwordless(user_pool_id: str, username: str) -> None:
    """Best-effort, LOUD group assignment. Same fail-open discipline as everything else on
    this trigger — a group-write error must not cost the person their sign-in — but a silent
    miss is a future lockout, so it logs the exact repair command."""
    try:
        cognito.admin_add_user_to_group(
            UserPoolId=user_pool_id, Username=username, GroupName=_PASSWORDLESS_GROUP
        )
    except Exception:
        logger.warning(
            "[ALERT] presignup-link: passwordless-group assignment FAILED for %s — this "
            "account cannot enroll TOTP and will be 403'd if it subscribes while "
            "ENFORCE_SUBSCRIBER_MFA=1. Repair: aws cognito-idp admin-add-user-to-group "
            "--user-pool-id %s --username %s --group-name %s --region us-east-1",
            username, user_pool_id, username, _PASSWORDLESS_GROUP,
            exc_info=True,
        )


def _pick_link_target(users: list[dict], incoming_username: str) -> str | None:
    """Return the native username to link the incoming federated identity into.

    Skips the incoming federated user itself and any other federated user (we only
    link into a native Cognito account, never chain federated→federated).
    """
    for user in users:
        username = user.get("Username", "")
        if not username or username == incoming_username:
            continue
        prefix = username.split("_", 1)[0].lower() if "_" in username else ""
        if prefix in _FEDERATED_PREFIXES:
            continue
        return username
    return None
