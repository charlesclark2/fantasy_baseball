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
_FEDERATED_PREFIXES = ("Google", "Facebook", "SignInWithApple", "LoginWithAmazon")


def handler(event, context):  # noqa: ANN001, ARG001 (Lambda signature)
    # Only external-provider (Google) sign-ups. Native sign-ups
    # (PreSignUp_SignUp) and admin-created users pass straight through.
    if event.get("triggerSource") != "PreSignUp_ExternalProvider":
        return event

    user_pool_id = event["userPoolId"]
    attrs = event.get("request", {}).get("userAttributes", {})
    email = attrs.get("email")
    # NEVER merge on an unverified email — that would be an account-takeover vector.
    email_verified = str(attrs.get("email_verified", "")).lower() == "true"
    if not email or not email_verified:
        return event

    # For an external provider the incoming userName is "<Provider>_<providerUserId>",
    # e.g. "Google_1234567890". Split into the provider name + the provider's subject.
    incoming_username = event.get("userName", "")
    if "_" not in incoming_username:
        return event
    provider_name, provider_uid = incoming_username.split("_", 1)

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
        return event

    try:
        cognito.admin_link_provider_for_user(
            UserPoolId=user_pool_id,
            DestinationUser={
                "ProviderName": "Cognito",
                "ProviderAttributeValue": target,
            },
            SourceUser={
                "ProviderName": provider_name,          # "Google"
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": provider_uid,  # the Google sub
            },
        )
        logger.info("presignup-link: linked %s → native user %s", incoming_username, target)
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
        prefix = username.split("_", 1)[0] if "_" in username else ""
        if prefix in _FEDERATED_PREFIXES:
            continue
        return username
    return None
