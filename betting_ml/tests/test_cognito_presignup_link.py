"""E9.7 — Cognito PreSignUp auto-link trigger handler.

Loads infrastructure/cognito/presignup_link/handler.py by path (it lives outside the
package tree) with a mocked boto3 client, and pins the linking logic: only external
providers, only verified emails, link into the native user (never chain federated),
and fail-open so a sign-in is never hard-blocked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_HANDLER_PATH = (
    Path(__file__).resolve().parents[2]
    / "infrastructure" / "cognito" / "presignup_link" / "handler.py"
)


@pytest.fixture()
def mod(monkeypatch):
    """Import the handler module fresh with a mocked cognito client."""
    fake_cognito = MagicMock()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_cognito
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    spec = importlib.util.spec_from_file_location("presignup_link_handler", _HANDLER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.cognito = fake_cognito  # ensure the handler uses our mock
    return module


def _event(trigger="PreSignUp_ExternalProvider", username="google_100868166396155863973",
           email="user@example.com", verified="true"):
    attrs = {"email": email}
    # verified=None models Cognito NOT mapping email_verified into the event (the real
    # E9.7 case); otherwise set it explicitly.
    if verified is not None:
        attrs["email_verified"] = verified
    return {
        "triggerSource": trigger,
        "userPoolId": "us-east-1_gG9zMbwQt",
        "userName": username,
        "request": {"userAttributes": attrs},
    }


def test_links_google_into_existing_native_user(mod):
    # Native user has a UUID username (as in prod: 14187448-c091-…), email as attribute.
    mod.cognito.list_users.return_value = {
        "Users": [{"Username": "14187448-c091-705c-1199-63858b12c986"}]
    }
    out = mod.handler(_event(), None)

    assert out["triggerSource"] == "PreSignUp_ExternalProvider"  # event returned unchanged
    mod.cognito.admin_link_provider_for_user.assert_called_once()
    kwargs = mod.cognito.admin_link_provider_for_user.call_args.kwargs
    assert kwargs["DestinationUser"] == {
        "ProviderName": "Cognito",
        "ProviderAttributeValue": "14187448-c091-705c-1199-63858b12c986",
    }
    assert kwargs["SourceUser"] == {
        # Canonical IdP name — Cognito lowercases it in the username ("google_…") but
        # admin_link_provider_for_user requires the configured "Google".
        "ProviderName": "Google",
        "ProviderAttributeName": "Cognito_Subject",
        "ProviderAttributeValue": "100868166396155863973",
    }


def test_links_when_email_verified_attribute_is_absent(mod):
    # The real E9.7 bug: Google mapping omits email_verified → attribute absent. A
    # trusted provider must still link (this is the regression the fix targets).
    mod.cognito.list_users.return_value = {
        "Users": [{"Username": "14187448-c091-705c-1199-63858b12c986"}]
    }
    mod.handler(_event(verified=None), None)
    mod.cognito.admin_link_provider_for_user.assert_called_once()


def test_native_signup_passes_through_untouched(mod):
    mod.handler(_event(trigger="PreSignUp_SignUp"), None)
    mod.cognito.list_users.assert_not_called()
    mod.cognito.admin_link_provider_for_user.assert_not_called()


def test_trusted_provider_links_even_when_email_verified_false(mod):
    # Cognito reports email_verified="false" for a Google federation when the IdP mapping
    # doesn't pass it through (the confirmed prod case). That `false` is an artifact, not a
    # real unverified signal, so a trusted provider must STILL link.
    mod.cognito.list_users.return_value = {
        "Users": [{"Username": "14187448-c091-705c-1199-63858b12c986"}]
    }
    mod.handler(_event(verified="false"), None)
    mod.cognito.admin_link_provider_for_user.assert_called_once()


def test_untrusted_provider_without_verified_email_never_links(mod):
    # A hypothetical future non-trusted IdP must assert email_verified=true to link.
    mod.cognito.list_users.return_value = {
        "Users": [{"Username": "14187448-c091-705c-1199-63858b12c986"}]
    }
    mod.handler(_event(username="myoidc_abc", verified="false"), None)
    mod.cognito.admin_link_provider_for_user.assert_not_called()


def test_no_pre_existing_user_is_ever_adopted_as_the_link_target(mod):
    # Only the incoming federated identity exists → there is no account to link INTO.
    #
    # ⚠️ RE-ANCHORED BY G100-C0, deliberately. E9.7's assertion here was
    # `admin_link_provider_for_user.assert_not_called()`, which asserted the IMPLEMENTATION
    # of the day ("do nothing") rather than the property it was defending ("never attach this
    # identity to somebody else's account"). G100-C0 pre-provisions a native user for exactly
    # this case, so "do nothing" is no longer true — but the PROPERTY is unchanged, and it is
    # what is asserted now: the link target is the account created for THIS person, and no
    # pre-existing row was adopted. (The "pre-provisioning is off ⇒ no link at all" behaviour
    # is covered by the kill-switch test in `test_g100_c0_email_otp.py`.)
    mod.cognito.list_users.return_value = {
        "Users": [{"Username": "google_100868166396155863973"}]
    }
    mod.cognito.admin_create_user.return_value = {"User": {"Username": "freshly-made-uuid"}}

    mod.handler(_event(), None)

    target = mod.cognito.admin_link_provider_for_user.call_args.kwargs["DestinationUser"][
        "ProviderAttributeValue"
    ]
    assert target == "freshly-made-uuid"
    assert target != "google_100868166396155863973"


def test_never_chains_into_another_federated_user(mod):
    # A different federated user shares the email — must NOT be a link target. This is
    # E9.7's property verbatim and it is untouched by G100-C0: linking one federated
    # identity onto another would make a Facebook sign-in resolve to a Google profile.
    # Only the assertion moved from "nothing happened" to "the target is not that user",
    # because a native account is now created to link into instead.
    mod.cognito.list_users.return_value = {"Users": [{"Username": "Facebook_999"}]}
    mod.cognito.admin_create_user.return_value = {"User": {"Username": "freshly-made-uuid"}}

    mod.handler(_event(), None)

    target = mod.cognito.admin_link_provider_for_user.call_args.kwargs["DestinationUser"][
        "ProviderAttributeValue"
    ]
    assert target == "freshly-made-uuid"
    assert target != "Facebook_999"


def test_fails_open_when_link_raises(mod):
    mod.cognito.list_users.return_value = {"Users": [{"Username": "user@example.com"}]}
    mod.cognito.admin_link_provider_for_user.side_effect = RuntimeError("boom")
    # Must not raise — a link failure cannot hard-block the sign-in.
    out = mod.handler(_event(), None)
    assert out is not None


def test_fails_open_when_list_users_raises(mod):
    mod.cognito.list_users.side_effect = RuntimeError("throttled")
    out = mod.handler(_event(), None)
    assert out is not None
    mod.cognito.admin_link_provider_for_user.assert_not_called()
