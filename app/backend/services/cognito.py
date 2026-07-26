"""Cognito user-pool group + MFA operations for the E9.8 subscription billing flow.

The Stripe webhook promotes/demotes paying users between Cognito groups
(beta_tester → subscriber on conversion; subscriber → churned on cancel/payment
failure), and the server-side subscriber-MFA guard reads a user's enrolled MFA
factors. Both go through the boto3 cognito-idp admin APIs here.

The Lambda execution role needs, on the user pool:
  cognito-idp:AdminAddUserToGroup, AdminRemoveUserFromGroup,
  cognito-idp:AdminGetUser, cognito-idp:ListUsersInGroup

`Username` is the Cognito `sub` throughout — the pool accepts the sub as the
Username for admin APIs (matches routers/auth.py's verify_email pattern).
"""

from __future__ import annotations

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "us-east-1_gG9zMbwQt")

# Cognito group names — the tier model (E9.4). A user in ANY of {beta_tester,
# subscriber, admin} has full access; churned/free do not.
GROUP_BETA = "beta_tester"
GROUP_SUBSCRIBER = "subscriber"
GROUP_CHURNED = "churned"
GROUP_ADMIN = "admin"

# Fantasy comp allow-list (E9.45) — a group DISTINCT from `subscriber` that grants
# fantasy access to operator/comp accounts WITHOUT counting them as paid subscribers.
# Keeping it separate from `subscriber` is deliberate: it keeps E9.8's founding-100
# count-based $10→$20 flip accurate and keeps comps out of paid analytics.
GROUP_FANTASY_COMP = "fantasy_comp"

# Per-SURFACE entitlement (E9.45). Betting is grandfathered — open to every current
# access tier; fantasy is a paid feature: `subscriber` or `admin` or the comp
# allow-list ONLY (beta_tester is deliberately NOT granted fantasy).
FANTASY_ACCESS_GROUPS = frozenset({GROUP_SUBSCRIBER, GROUP_ADMIN, GROUP_FANTASY_COMP})


def has_fantasy_access(groups: list[str] | frozenset[str]) -> bool:
    """True iff the caller's Cognito groups grant the fantasy surface (E9.45)."""
    return bool(FANTASY_ACCESS_GROUPS.intersection(groups))


def _client():
    return boto3.client("cognito-idp", region_name=_AWS_REGION)


def add_user_to_group(sub: str, group: str) -> None:
    """Add the user to a Cognito group. Idempotent — re-adding is a no-op in Cognito."""
    try:
        _client().admin_add_user_to_group(
            UserPoolId=_USER_POOL_ID, Username=sub, GroupName=group
        )
    except ClientError:
        logger.exception("admin_add_user_to_group failed (sub=%s group=%s)", sub, group)
        raise


def remove_user_from_group(sub: str, group: str) -> None:
    """Remove the user from a Cognito group. A user not in the group is a no-op
    (Cognito raises no error), so this is safe to call unconditionally."""
    try:
        _client().admin_remove_user_from_group(
            UserPoolId=_USER_POOL_ID, Username=sub, GroupName=group
        )
    except ClientError:
        logger.exception(
            "admin_remove_user_from_group failed (sub=%s group=%s)", sub, group
        )
        raise


def promote_to_subscriber(sub: str) -> None:
    """Convert a user to a paying subscriber: add `subscriber`, drop `beta_tester`
    and `churned`. Called from the Stripe webhook on a confirmed conversion."""
    add_user_to_group(sub, GROUP_SUBSCRIBER)
    remove_user_from_group(sub, GROUP_BETA)
    remove_user_from_group(sub, GROUP_CHURNED)


def demote_to_churned(sub: str) -> None:
    """Revoke paid access: drop `subscriber`, add `churned`. Called from the Stripe
    webhook on subscription.deleted / invoice.payment_failed."""
    remove_user_from_group(sub, GROUP_SUBSCRIBER)
    add_user_to_group(sub, GROUP_CHURNED)


def groups_for_user(sub: str) -> list[str]:
    """Authoritative current group membership for a user, read from Cognito."""
    try:
        resp = _client().admin_list_groups_for_user(
            UserPoolId=_USER_POOL_ID, Username=sub
        )
    except ClientError:
        logger.exception("admin_list_groups_for_user failed (sub=%s)", sub)
        return []
    return [g.get("GroupName", "") for g in resp.get("Groups", []) if g.get("GroupName")]


def mfa_factors_for_user(sub: str) -> list[str]:
    """The user's enabled MFA factors (e.g. ['SOFTWARE_TOKEN_MFA']).

    Read from AdminGetUser's UserMFASettingList — the authoritative record of what
    the account has enrolled. Returns [] if unreadable (the caller decides how to
    treat that; the subscriber-MFA guard fails CLOSED)."""
    try:
        resp = _client().admin_get_user(UserPoolId=_USER_POOL_ID, Username=sub)
    except ClientError:
        logger.exception("admin_get_user failed (sub=%s)", sub)
        raise
    return list(resp.get("UserMFASettingList", []) or [])


def has_software_token_mfa(sub: str) -> bool:
    """True iff the user has an authenticator-app (TOTP) factor enrolled."""
    return "SOFTWARE_TOKEN_MFA" in mfa_factors_for_user(sub)
