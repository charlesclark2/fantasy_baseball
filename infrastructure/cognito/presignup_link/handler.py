"""Cognito PreSignUp trigger — auto-link a federated (Google) sign-in to an existing
native account with the SAME verified email, so one person = one Cognito identity.

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

Deploy: see README.md in this directory (function + role + trigger + IAM + the
    one-time cleanup for accounts that already have a duplicate Google user).

IAM (execution role) — on the pool ARN:
    cognito-idp:ListUsers
    cognito-idp:AdminLinkProviderForUser
"""

from __future__ import annotations

import logging

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
        # No native account with this email → a genuinely new Google user. Let Cognito
        # create the federated account normally (E9.8 promotes it from the default group).
        logger.info("presignup-link: no native user for %s — new federated account", email)
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
