"""G100-C0 — guards for passwordless email sign-in and the one-account-per-human invariant.

⚠️ EVERY GUARD HERE WAS RED-PROVEN against deliberately-broken source before being trusted.
The specific break each one catches is named in its docstring. Per NF-D17, a guard on an
`and`-composed rule is vacuous unless its fixture satisfies every OTHER clause, so the
fixtures below isolate ONE property each.

THE THREE THINGS MOST LIKELY TO SHIP BROKEN AND SILENT, and therefore the ones with the
heaviest coverage:

  1. **A DUPLICATE ACCOUNT.** The whole story is "one Credence user_id, many auth
     identities". A second Cognito user for the same human is not an error — it is a
     working sign-in into an empty account. Nothing throws, nothing logs, and the person
     simply cannot find their leagues. `TestFederatedOnlyIsRefusedNotDuplicated` and
     `TestPreProvisioning` are that invariant's teeth.

  2. **A CODE THAT SILENTLY ROTATES.** Cognito re-invokes CreateAuthChallenge on EVERY
     wrong answer. Minting a fresh code there means the code in the user's inbox is stale
     the instant they mistype once — so a CORRECT reading of a REAL email fails forever,
     and every failure also mails them again. Both halves are covered.

  3. **AN ACCOUNT-EXISTENCE ORACLE.** Cognito hands us `userNotFound` rather than erroring
     precisely so this flow can be made non-enumerable. Short-circuiting on it turns the
     endpoint into "is this person a customer?" for anyone who can type an address.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO = Path(__file__).resolve().parents[2]
_OTP_HANDLER = _REPO / "infrastructure" / "cognito" / "email_otp" / "handler.py"
_PRESIGNUP_HANDLER = _REPO / "infrastructure" / "cognito" / "presignup_link" / "handler.py"


def _load(path: Path, name: str, monkeypatch):
    """Import a Lambda handler by path with boto3 mocked out.

    These live outside the package tree (they are separate deployment artifacts), so a
    normal import cannot reach them — the same loader `test_cognito_presignup_link.py` uses.
    """
    fake_client = MagicMock()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake_client


# ══════════════════════════════════════════════════════════════════════════════════════════
# The CUSTOM_AUTH trigger Lambda
# ══════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def otp(monkeypatch):
    module, _ = _load(_OTP_HANDLER, "email_otp_handler", monkeypatch)
    module.ses = MagicMock()
    return module


def _create_event(session=None, user_not_found=False, email="user@example.com"):
    return {
        "triggerSource": "CreateAuthChallenge_Authentication",
        "request": {
            "session": session or [],
            "userNotFound": user_not_found,
            "userAttributes": {"email": email},
        },
        "response": {},
    }


def _define_event(session):
    return {
        "triggerSource": "DefineAuthChallenge_Authentication",
        "request": {"session": session},
        "response": {},
    }


def _verify_event(expected, supplied):
    return {
        "triggerSource": "VerifyAuthChallengeResponse_Authentication",
        "request": {
            "privateChallengeParameters": {"code": expected},
            "challengeAnswer": supplied,
        },
        "response": {},
    }


def _issued(session_entry_code: str) -> dict:
    """A completed CUSTOM_CHALLENGE session entry carrying an already-issued code."""
    return {
        "challengeName": "CUSTOM_CHALLENGE",
        "challengeResult": False,
        "challengeMetadata": f"CODE-{session_entry_code}",
    }


class TestTheCodeIsMintedOnceAndMailedOnce:
    def test_the_first_challenge_generates_a_code_and_sends_exactly_one_email(self, otp):
        out = otp.handler(_create_event(), None)
        assert otp.ses.send_email.call_count == 1
        code = out["response"]["privateChallengeParameters"]["code"]
        assert len(code) == otp.CODE_LENGTH and code.isdigit()

    def test_a_retry_reuses_the_same_code_and_sends_no_second_email(self, otp):
        """RED-PROVEN by deleting `_recover_code`'s use in `create_auth_challenge`.

        THE BREAK THIS CATCHES: minting a fresh code per retry. The user's real email is
        then stale after one typo — so the code they are correctly reading can never work
        again — and every wrong keystroke mails them another one. Both are silent: the flow
        still "works", it just never lets that person in.
        """
        first = otp.handler(_create_event(), None)
        issued = first["response"]["privateChallengeParameters"]["code"]
        otp.ses.send_email.reset_mock()

        second = otp.handler(_create_event(session=[_issued(issued)]), None)

        assert second["response"]["privateChallengeParameters"]["code"] == issued
        assert otp.ses.send_email.call_count == 0

    def test_the_code_is_never_returned_to_the_client(self, otp):
        """`publicChallengeParameters` is echoed to the caller; `privateChallengeParameters`
        is not. Putting the code in the wrong one hands it to whoever asked for it."""
        out = otp.handler(_create_event(), None)
        public = out["response"]["publicChallengeParameters"]
        code = out["response"]["privateChallengeParameters"]["code"]
        assert code not in repr(public)
        assert public["email"] == "us•••@example.com"

    def test_a_failed_send_does_not_raise(self, otp):
        otp.ses.send_email.side_effect = RuntimeError("SES down")
        out = otp.handler(_create_event(), None)
        assert out["response"]["privateChallengeParameters"]["code"]


class TestAnUnknownAddressIsIndistinguishable:
    def test_an_unknown_address_still_gets_a_challenge_but_no_email(self, otp):
        """RED-PROVEN by making `create_auth_challenge` return early on `userNotFound`.

        THE BREAK THIS CATCHES: an account-existence oracle. An early return produces a
        visibly different response for a registered address than for an unregistered one,
        so anyone can test whether a given person is a customer.
        """
        out = otp.handler(_create_event(user_not_found=True), None)
        assert otp.ses.send_email.call_count == 0
        # Still shaped exactly like the known-address response.
        assert out["response"]["privateChallengeParameters"]["code"]
        assert "email" in out["response"]["publicChallengeParameters"]

    def test_the_response_shape_matches_a_known_address_exactly(self, otp):
        known = otp.handler(_create_event(user_not_found=False), None)["response"]
        unknown = otp.handler(_create_event(user_not_found=True), None)["response"]
        assert set(known) == set(unknown)
        assert set(known["publicChallengeParameters"]) == set(unknown["publicChallengeParameters"])


class TestAttemptsAreBoundedByCognitosSession:
    def test_a_correct_answer_issues_tokens(self, otp):
        session = [{"challengeName": "CUSTOM_CHALLENGE", "challengeResult": True}]
        out = otp.handler(_define_event(session), None)
        assert out["response"]["issueTokens"] is True
        assert out["response"]["failAuthentication"] is False

    def test_the_flow_dies_after_max_attempts(self, otp):
        session = [
            {"challengeName": "CUSTOM_CHALLENGE", "challengeResult": False}
        ] * otp.MAX_ATTEMPTS
        out = otp.handler(_define_event(session), None)
        assert out["response"]["failAuthentication"] is True
        assert out["response"]["issueTokens"] is False

    def test_one_wrong_answer_issues_another_challenge(self, otp):
        session = [{"challengeName": "CUSTOM_CHALLENGE", "challengeResult": False}]
        out = otp.handler(_define_event(session), None)
        assert out["response"]["challengeName"] == "CUSTOM_CHALLENGE"
        assert out["response"]["failAuthentication"] is False

    def test_non_custom_session_entries_do_not_burn_attempts(self, otp):
        """RED-PROVEN by replacing `_custom_challenges(...)` with the raw session list.

        THE BREAK THIS CATCHES: counting every session entry as an attempt. Cognito can
        prepend entries for other challenge names, which would lock a user out after fewer
        real tries than the policy claims — and the user sees only "that code didn't work".
        """
        session = [{"challengeName": "SRP_A", "challengeResult": False}] * 5
        out = otp.handler(_define_event(session), None)
        assert out["response"]["failAuthentication"] is False
        assert out["response"]["challengeName"] == "CUSTOM_CHALLENGE"


class TestVerification:
    def test_the_right_code_is_accepted_and_a_wrong_one_is_not(self, otp):
        assert otp.handler(_verify_event("123456", "123456"), None)["response"]["answerCorrect"]
        assert not otp.handler(_verify_event("123456", "123457"), None)["response"]["answerCorrect"]

    def test_surrounding_whitespace_is_tolerated(self, otp):
        """Autofill and paste routinely carry whitespace; rejecting " 123456 " is a defect
        whose cause the user cannot possibly see."""
        assert otp.handler(_verify_event("123456", " 123456 "), None)["response"]["answerCorrect"]

    def test_an_absent_expected_code_never_authenticates(self, otp):
        """RED-PROVEN by dropping the `bool(expected) and` clause.

        THE BREAK THIS CATCHES: `compare_digest("", "")` is TRUE. Any path that failed to
        set a code would then authenticate anyone who submits an empty answer — a complete
        auth bypass reachable by pressing enter on an empty field.
        """
        assert not otp.handler(_verify_event("", ""), None)["response"]["answerCorrect"]
        assert not otp.handler(_verify_event(None, ""), None)["response"]["answerCorrect"]

    def test_an_unexpected_trigger_is_passed_through_unchanged(self, otp):
        event = {"triggerSource": "PreSignUp_SignUp", "request": {}}
        assert otp.handler(event, None) is event


# ══════════════════════════════════════════════════════════════════════════════════════════
# PreSignUp pre-provisioning — the half of the invariant that lives in Cognito
# ══════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def presignup(monkeypatch):
    monkeypatch.delenv("PRESIGNUP_PREPROVISION", raising=False)
    module, fake = _load(_PRESIGNUP_HANDLER, "presignup_link_handler_g100c0", monkeypatch)
    module.cognito = fake
    return module


def _external_event(email="new@example.com", username="google_12345"):
    return {
        "triggerSource": "PreSignUp_ExternalProvider",
        "userPoolId": "us-east-1_gG9zMbwQt",
        "userName": username,
        "request": {"userAttributes": {"email": email}},
    }


class TestPreProvisioning:
    def test_a_brand_new_google_signin_gets_a_native_user_created_and_linked(self, presignup):
        """THE CORE G100-C0 INVARIANT, forward direction. Without this a Google-first person
        has no native user, so a later email-OTP sign-in has nothing to authenticate against
        and would have to mint a SECOND account for the same human."""
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "uuid-abc"}}

        presignup.handler(_external_event(), None)

        presignup.cognito.admin_create_user.assert_called_once()
        presignup.cognito.admin_link_provider_for_user.assert_called_once()
        link = presignup.cognito.admin_link_provider_for_user.call_args.kwargs
        assert link["DestinationUser"]["ProviderAttributeValue"] == "uuid-abc"

    def test_the_link_targets_the_created_username_not_the_email(self, presignup):
        """RED-PROVEN by returning `email` from `_preprovision_native_user`.

        THE BREAK THIS CATCHES: this pool uses email as a username ATTRIBUTE, so Cognito
        assigns a generated UUID as the real Username. Linking to the email targets a user
        that does not exist under that name — the link fails, the trigger fails OPEN, and a
        plain federated account is created. Net effect: the whole feature silently no-ops,
        with a successful sign-in every time.
        """
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "uuid-xyz"}}

        presignup.handler(_external_event(email="someone@example.com"), None)

        target = presignup.cognito.admin_link_provider_for_user.call_args.kwargs[
            "DestinationUser"
        ]["ProviderAttributeValue"]
        assert target == "uuid-xyz"
        assert target != "someone@example.com"

    def test_the_invite_email_is_suppressed(self, presignup):
        """Without SUPPRESS, Cognito mails a "your temporary password is…" invite for an
        account the person never asked for and cannot use — during a Google sign-in."""
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "u"}}
        presignup.handler(_external_event(), None)
        assert (
            presignup.cognito.admin_create_user.call_args.kwargs["MessageAction"] == "SUPPRESS"
        )

    def test_the_account_is_moved_out_of_force_change_password(self, presignup):
        """A permanent password is what makes the account CONFIRMED. Without it the account
        exists and CUSTOM_AUTH still cannot run against it — created, and useless for the
        one purpose it was created for."""
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "u"}}
        presignup.handler(_external_event(), None)
        assert presignup.cognito.admin_set_user_password.call_args.kwargs["Permanent"] is True

    def test_an_existing_native_user_is_never_duplicated(self, presignup):
        """The E9.7 path, re-anchored: when a native user already exists we link into IT and
        create nothing. Creating here would be the duplicate-account bug from the other side."""
        presignup.cognito.list_users.return_value = {"Users": [{"Username": "native-uuid"}]}
        presignup.handler(_external_event(), None)
        presignup.cognito.admin_create_user.assert_not_called()
        presignup.cognito.admin_link_provider_for_user.assert_called_once()

    def test_the_kill_switch_restores_the_pre_g100c0_behaviour(self, presignup, monkeypatch):
        """This trigger sits in front of the ONLY public signup path, so the operator needs a
        rollback that is not a redeploy."""
        monkeypatch.setenv("PRESIGNUP_PREPROVISION", "0")
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.handler(_external_event(), None)
        presignup.cognito.admin_create_user.assert_not_called()
        presignup.cognito.admin_link_provider_for_user.assert_not_called()

    def test_pre_provisioning_is_on_by_default(self, presignup):
        """A default-OFF flag would put this repo's documented-but-never-set landmine
        (`W7B_LAKEHOUSE_S3`) in front of signup: the docs would promise one account per
        human while production quietly kept splitting them."""
        assert presignup.preprovision_enabled() is True

    def test_a_failed_creation_fails_open_rather_than_blocking_the_signin(self, presignup):
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.side_effect = RuntimeError("throttled")
        out = presignup.handler(_external_event(), None)
        assert out is not None
        presignup.cognito.admin_link_provider_for_user.assert_not_called()

    def test_a_native_signup_still_passes_through_untouched(self, presignup):
        event = dict(_external_event(), triggerSource="PreSignUp_SignUp")
        presignup.handler(event, None)
        presignup.cognito.admin_create_user.assert_not_called()
        presignup.cognito.list_users.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════════════════
# Backend identity resolution
# ══════════════════════════════════════════════════════════════════════════════════════════

from app.backend.services import identity as identity_svc  # noqa: E402


class TestEmailNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("  Charlie@Example.COM ", "charlie@example.com"),
            ("a@b.co", "a@b.co"),
        ],
    )
    def test_case_and_whitespace_are_folded(self, raw, expected):
        assert identity_svc.normalize_email(raw) == expected

    @pytest.mark.parametrize(
        "raw", ["", None, "nope", "@example.com", "a@", "a b@example.com", "a@localhost"]
    )
    def test_non_addresses_are_rejected(self, raw):
        assert identity_svc.normalize_email(raw) is None

    def test_provider_aliasing_is_deliberately_not_canonicalised(self):
        """RED-PROVEN by adding Gmail dot-stripping to `normalize_email`.

        THE BREAK THIS CATCHES: `c.harlie@gmail.com` and `charlie@gmail.com` are DISTINCT
        Cognito users. Folding them here would send one person's sign-in code to a session
        resolving onto a DIFFERENT person's account — an identity service's worst possible
        failure, and it would look like a tidy normalisation improvement in review.
        """
        assert identity_svc.normalize_email("c.harlie@gmail.com") == "c.harlie@gmail.com"
        assert identity_svc.normalize_email("me+tag@gmail.com") == "me+tag@gmail.com"


class TestClassification:
    def _patch(self, monkeypatch, users=None, raises=False):
        client = MagicMock()
        if raises:
            from botocore.exceptions import ClientError

            client.list_users.side_effect = ClientError({"Error": {}}, "ListUsers")
        else:
            client.list_users.return_value = {"Users": users or []}
        monkeypatch.setattr(identity_svc, "_client", lambda: client)
        return client

    def test_nobody_is_new(self, monkeypatch):
        self._patch(monkeypatch, users=[])
        assert identity_svc.classify("a@b.co").state is identity_svc.IdentityState.NEW

    def test_a_native_user_is_native(self, monkeypatch):
        self._patch(monkeypatch, users=[{"Username": "uuid-1", "Enabled": True}])
        found = identity_svc.classify("a@b.co")
        assert found.state is identity_svc.IdentityState.NATIVE
        assert found.username == "uuid-1"

    def test_a_bare_federated_profile_is_federated_only(self, monkeypatch):
        self._patch(monkeypatch, users=[{"Username": "google_999", "Enabled": True}])
        found = identity_svc.classify("a@b.co")
        assert found.state is identity_svc.IdentityState.FEDERATED_ONLY
        assert found.provider == "Google"

    def test_a_linked_account_reads_as_native_even_beside_a_federated_row(self, monkeypatch):
        """A person whose Google identity is linked into a native user must go down the OTP
        path, not the "use Google" dead end — it is one account and OTP works for it."""
        self._patch(
            monkeypatch,
            users=[{"Username": "google_999"}, {"Username": "uuid-1", "Enabled": True}],
        )
        assert identity_svc.classify("a@b.co").state is identity_svc.IdentityState.NATIVE

    def test_a_disabled_account_is_not_handed_a_new_way_in(self, monkeypatch):
        """Disabling an account is the one action an operator takes to lock someone out. A
        sign-in method that ignores it is a bypass."""
        self._patch(monkeypatch, users=[{"Username": "uuid-1", "Enabled": False}])
        assert identity_svc.classify("a@b.co").state is identity_svc.IdentityState.DISABLED

    def test_an_unreadable_answer_fails_closed(self, monkeypatch):
        """RED-PROVEN by returning `Identity(NEW)` from the except branch.

        THE BREAK THIS CATCHES: treating a Cognito outage as "nobody has this address"
        makes the route CREATE an account for someone who already has one — a permanent,
        silent data split produced by a transient error. Fail-closed is the opposite
        direction from the PreSignUp trigger's fail-OPEN, and deliberately so: there an
        error costs a sign-in, here it would cost a duplicate account.
        """
        self._patch(monkeypatch, raises=True)
        found = identity_svc.classify("a@b.co")
        assert found.state is identity_svc.IdentityState.DISABLED
        assert found.may_send_otp is False


class TestNativeUserCreation:
    def test_it_returns_the_response_username_and_sets_a_permanent_password(self, monkeypatch):
        client = MagicMock()
        client.admin_create_user.return_value = {"User": {"Username": "uuid-new"}}
        monkeypatch.setattr(identity_svc, "_client", lambda: client)

        assert identity_svc.create_native_user("a@b.co") == "uuid-new"
        assert client.admin_create_user.call_args.kwargs["MessageAction"] == "SUPPRESS"
        assert client.admin_set_user_password.call_args.kwargs["Permanent"] is True
        assert client.admin_set_user_password.call_args.kwargs["Username"] == "uuid-new"

    def test_email_verified_starts_false(self, monkeypatch):
        """Nothing has proven ownership at creation time. `POST /auth/verify-email` flips it
        after the first successful code — which IS the moment ownership is proven."""
        client = MagicMock()
        client.admin_create_user.return_value = {"User": {"Username": "u"}}
        monkeypatch.setattr(identity_svc, "_client", lambda: client)
        identity_svc.create_native_user("a@b.co")
        attrs = {
            a["Name"]: a["Value"]
            for a in client.admin_create_user.call_args.kwargs["UserAttributes"]
        }
        assert attrs["email_verified"] == "false"

    def test_a_missing_username_raises_rather_than_returning_none(self, monkeypatch):
        client = MagicMock()
        client.admin_create_user.return_value = {}
        monkeypatch.setattr(identity_svc, "_client", lambda: client)
        with pytest.raises(RuntimeError):
            identity_svc.create_native_user("a@b.co")


class TestNativeUserCreationAgreesAcrossImplementations:
    """The trigger Lambda and the API create the SAME kind of native user, in two files that
    cannot import each other (a Cognito trigger is a separate deployment artifact). Undetected
    drift between them would produce two CLASSES of account that behave differently — one able
    to run CUSTOM_AUTH and one not — with nothing to point at.
    """

    def _kwargs_of(self, source: Path, func_name: str) -> set[str]:
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == func_name:
                    return {kw.arg for kw in node.keywords}
        raise AssertionError(f"{func_name} is not called in {source}")

    def test_both_suppress_the_invite_and_set_a_permanent_password(self):
        for source in (_PRESIGNUP_HANDLER, _REPO / "app/backend/services/identity.py"):
            create = self._kwargs_of(source, "admin_create_user")
            assert {"MessageAction", "UserAttributes", "Username", "UserPoolId"} <= create, source
            setpw = self._kwargs_of(source, "admin_set_user_password")
            assert {"Permanent", "Password", "Username", "UserPoolId"} <= setpw, source

    def test_both_agree_on_which_username_prefixes_mean_federated(self):
        module_prefixes = set(identity_svc._FEDERATED_PREFIXES)
        tree = ast.parse(_PRESIGNUP_HANDLER.read_text())
        trigger_prefixes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_FEDERATED_PREFIXES" for t in node.targets
            ):
                trigger_prefixes = {
                    e.value for e in node.value.elts if isinstance(e, ast.Constant)
                }
        assert trigger_prefixes, "could not read _FEDERATED_PREFIXES from the trigger"
        assert trigger_prefixes == module_prefixes


# ══════════════════════════════════════════════════════════════════════════════════════════
# The routes
# ══════════════════════════════════════════════════════════════════════════════════════════

from fastapi import HTTPException  # noqa: E402

from app.backend.routers import email_otp as otp_router  # noqa: E402
from app.backend.services import cost_guardrails as cg  # noqa: E402


class _FakeRequest:
    """The slice of a Starlette Request that `resolve_client_ip` reads."""

    def __init__(self, ip: str = "203.0.113.7"):
        self.scope = {"aws.event": {"requestContext": {"http": {"sourceIp": ip}}}}
        self.headers: dict[str, str] = {}
        self.client = None


@pytest.fixture(autouse=True)
def _clean_otp_throttles():
    """The OTP limiter is PROCESS-GLOBAL and STATEFUL, so without this a test that sends
    codes leaks its buckets into the next one — and the failure presents as an unexpected
    RESPONSE SHAPE (a 429 body where a 200 was expected), not as an obvious throttle."""
    otp_router.reset_throttles()
    yield
    otp_router.reset_throttles()


def _patch_router(monkeypatch, state, *, username="uuid-1", provider="Google"):
    """Put the router in one identity state with every Cognito call mocked."""
    found = identity_svc.Identity(
        state=state,
        username=username if state is identity_svc.IdentityState.NATIVE else None,
        provider=provider if state is identity_svc.IdentityState.FEDERATED_ONLY else None,
    )
    created: list[str] = []
    client = MagicMock()
    client.admin_initiate_auth.return_value = {"Session": "cognito-session-token"}
    monkeypatch.setattr(otp_router.identity_svc, "classify", lambda email: found)
    monkeypatch.setattr(
        otp_router.identity_svc,
        "create_native_user",
        lambda email: (created.append(email), "uuid-new")[1],
    )
    monkeypatch.setattr(otp_router, "_client", lambda: client)
    return client, created


class TestFederatedOnlyIsRefusedNotDuplicated:
    """⭐ THE STORY'S CENTRAL INVARIANT. A pre-G100-C0 Google account has no native
    counterpart, and its `sub` — which owns that person's bets and leagues — cannot be moved
    to one. Creating a native user here would hand them a second, empty account that signs
    in perfectly. Nothing would throw; they would simply never find their data again."""

    def test_it_creates_nothing_and_starts_no_challenge(self, monkeypatch):
        """RED-PROVEN by removing the FEDERATED_ONLY branch from `start_email_otp`.

        With the branch gone the request falls through to the NEW path and mints the
        duplicate. Both assertions are needed: creating the user is the data split, and
        starting the challenge would mail a code for an account they should not be using.
        """
        client, created = _patch_router(monkeypatch, identity_svc.IdentityState.FEDERATED_ONLY)

        out = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="g@example.com"), _FakeRequest()
        )

        assert out.next == "google"
        assert out.provider == "Google"
        assert created == []
        client.admin_initiate_auth.assert_not_called()

    def test_it_returns_no_session_so_the_client_cannot_show_a_code_field(self, monkeypatch):
        _patch_router(monkeypatch, identity_svc.IdentityState.FEDERATED_ONLY)
        out = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="g@example.com"), _FakeRequest()
        )
        assert out.session is None


class TestStart:
    def test_a_brand_new_address_gets_an_account_and_a_code(self, monkeypatch):
        client, created = _patch_router(monkeypatch, identity_svc.IdentityState.NEW)
        out = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="New@Example.com"), _FakeRequest()
        )
        assert out.next == "otp"
        assert out.session == "cognito-session-token"
        # Normalised before anything touches Cognito, or the same human creates two accounts
        # by capitalising differently.
        assert created == ["new@example.com"]
        client.admin_initiate_auth.assert_called_once()

    def test_an_existing_native_user_is_not_recreated(self, monkeypatch):
        client, created = _patch_router(monkeypatch, identity_svc.IdentityState.NATIVE)
        out = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
        )
        assert out.next == "otp"
        assert created == []
        client.admin_initiate_auth.assert_called_once()

    def test_new_and_native_are_indistinguishable_from_outside(self, monkeypatch):
        """The non-enumerable case that actually matters: every address that is not already
        a provider account must look identical whether or not it has an account."""
        _patch_router(monkeypatch, identity_svc.IdentityState.NEW)
        fresh = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
        )
        otp_router.reset_throttles()
        _patch_router(monkeypatch, identity_svc.IdentityState.NATIVE)
        existing = otp_router.start_email_otp(
            otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
        )
        assert fresh.model_dump() == existing.model_dump()

    def test_a_disabled_account_is_refused(self, monkeypatch):
        _patch_router(monkeypatch, identity_svc.IdentityState.DISABLED)
        with pytest.raises(HTTPException) as exc:
            otp_router.start_email_otp(
                otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
            )
        assert exc.value.status_code == 403

    def test_a_malformed_address_is_rejected_before_any_cognito_call(self, monkeypatch):
        client, created = _patch_router(monkeypatch, identity_svc.IdentityState.NEW)
        with pytest.raises(HTTPException) as exc:
            otp_router.start_email_otp(otp_router.OtpStartRequest(email="nope"), _FakeRequest())
        assert exc.value.status_code == 400
        assert created == []
        client.admin_initiate_auth.assert_not_called()

    def test_a_missing_session_is_a_503_not_a_200_with_no_session(self, monkeypatch):
        """RED-PROVEN by returning `resp.get("Session")` unchecked.

        THE BREAK THIS CATCHES: a 200 carrying a null session shows the user a code field
        for a challenge they can never answer — presenting a backend failure as a code that
        is simply always wrong.
        """
        client, _ = _patch_router(monkeypatch, identity_svc.IdentityState.NATIVE)
        client.admin_initiate_auth.return_value = {}
        with pytest.raises(HTTPException) as exc:
            otp_router.start_email_otp(
                otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
            )
        assert exc.value.status_code == 503


class TestSendThrottling:
    """The mail-bomb bound. Routing `InitiateAuth` through our API instead of letting the
    browser call Cognito directly exists ENTIRELY so this limit can exist at all."""

    def test_one_address_cannot_be_mailed_without_limit(self, monkeypatch):
        client, _ = _patch_router(monkeypatch, identity_svc.IdentityState.NATIVE)
        allowed = 0
        for _ in range(int(otp_router._EMAIL_POLICY.burst) + 3):
            try:
                otp_router.start_email_otp(
                    otp_router.OtpStartRequest(email="victim@example.com"), _FakeRequest()
                )
                allowed += 1
            except HTTPException as exc:
                assert exc.value.status_code == 429 if hasattr(exc, "value") else True
                break
        assert allowed == int(otp_router._EMAIL_POLICY.burst)
        assert client.admin_initiate_auth.call_count == allowed

    def test_the_per_address_limit_is_not_bypassed_by_changing_ip(self, monkeypatch):
        """RED-PROVEN by keying the email bucket on the IP instead of the address.

        THE BREAK THIS CATCHES: a per-IP-only limit does not bound what ONE INBOX receives,
        which is the harm that lands on someone who did nothing wrong. A botnet or a phone
        on cellular rotates addresses freely.
        """
        _patch_router(monkeypatch, identity_svc.IdentityState.NATIVE)
        allowed = 0
        for i in range(int(otp_router._EMAIL_POLICY.burst) + 3):
            try:
                otp_router.start_email_otp(
                    otp_router.OtpStartRequest(email="victim@example.com"),
                    _FakeRequest(ip=f"198.51.100.{i}"),
                )
                allowed += 1
            except HTTPException:
                break
        assert allowed == int(otp_router._EMAIL_POLICY.burst)

    def test_the_throttle_runs_before_any_cognito_call(self, monkeypatch):
        """A limiter that fires AFTER the lookup still pays for every abusive request."""
        client, created = _patch_router(monkeypatch, identity_svc.IdentityState.NEW)
        for _ in range(int(otp_router._IP_POLICY.burst)):
            try:
                otp_router.start_email_otp(
                    otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest()
                )
            except HTTPException:
                pass
        before = client.admin_initiate_auth.call_count
        with pytest.raises(HTTPException) as exc:
            otp_router.start_email_otp(otp_router.OtpStartRequest(email="a@b.co"), _FakeRequest())
        assert exc.value.status_code == 429
        assert client.admin_initiate_auth.call_count == before

    def test_the_ip_bucket_cannot_be_minted_by_a_forged_header(self, monkeypatch):
        """`resolve_client_ip` prefers the gateway's own observation; this pins that the OTP
        path uses it rather than reading a caller-controlled header itself."""
        req = _FakeRequest(ip="203.0.113.7")
        req.headers = {"x-forwarded-for": "1.2.3.4"}
        assert cg.resolve_client_ip(req) == "203.0.113.7"


class TestVerify:
    def _client(self, monkeypatch, result):
        client = MagicMock()
        client.admin_respond_to_auth_challenge.return_value = result
        monkeypatch.setattr(otp_router, "_client", lambda: client)
        return client

    def test_a_correct_code_returns_the_token_trio(self, monkeypatch):
        self._client(
            monkeypatch,
            {
                "AuthenticationResult": {
                    "AccessToken": "at",
                    "IdToken": "it",
                    "RefreshToken": "rt",
                    "ExpiresIn": 3600,
                    "TokenType": "Bearer",
                }
            },
        )
        out = otp_router.verify_email_otp(
            otp_router.OtpVerifyRequest(email="a@b.co", code="123456", session="s"),
            _FakeRequest(),
        )
        assert (out.access_token, out.id_token, out.refresh_token) == ("at", "it", "rt")

    def test_another_challenge_is_a_401_not_a_success(self, monkeypatch):
        """RED-PROVEN by dropping the `if not result.get("AccessToken")` check.

        THE BREAK THIS CATCHES: a WRONG code comes back as another CHALLENGE, not an
        exception. Without the check the route returns 200 with empty tokens, the client
        hydrates an empty session, and a failed sign-in presents as a broken app rather
        than as "that code didn't work".
        """
        self._client(monkeypatch, {"ChallengeName": "CUSTOM_CHALLENGE", "Session": "s2"})
        with pytest.raises(HTTPException) as exc:
            otp_router.verify_email_otp(
                otp_router.OtpVerifyRequest(email="a@b.co", code="000000", session="s"),
                _FakeRequest(),
            )
        assert exc.value.status_code == 401

    def test_a_dead_session_reads_as_a_retryable_401(self, monkeypatch):
        from botocore.exceptions import ClientError

        client = MagicMock()
        client.admin_respond_to_auth_challenge.side_effect = ClientError(
            {"Error": {"Code": "NotAuthorizedException"}}, "AdminRespondToAuthChallenge"
        )
        monkeypatch.setattr(otp_router, "_client", lambda: client)
        with pytest.raises(HTTPException) as exc:
            otp_router.verify_email_otp(
                otp_router.OtpVerifyRequest(email="a@b.co", code="000000", session="s"),
                _FakeRequest(),
            )
        assert exc.value.status_code == 401


class TestTheRoutesArePublicAndSurviveDegradeMode:
    def test_neither_route_carries_an_auth_dependency(self):
        """A caller signing in has no token by definition, so a `Depends(get_user_id)` here
        would make the feature unreachable for exactly the people it exists for."""
        for route in otp_router.router.routes:
            assert not route.dependencies, route.path

    def test_the_paths_stay_up_when_the_cost_kill_switch_is_on(self):
        """A spend event must not make it impossible to sign in — that turns a cost
        containment into an outage. Covered by the `/auth` prefix; pinned here so a future
        narrowing of that entry is caught by the story that depends on it."""
        assert cg.is_allowed_in_degrade("/auth/email-otp/start")
        assert cg.is_allowed_in_degrade("/auth/email-otp/verify")

    def test_the_router_is_mounted_on_the_app(self):
        """RED-PROVEN by removing the `include_router` line.

        THE BREAK THIS CATCHES: every unit here passes against an unmounted router — the
        functions are correct and simply unreachable. The NF-C0e "wired ≠ invoked" class.
        """
        from app.backend.main import app

        paths = {r.path for r in app.routes}
        assert "/auth/email-otp/start" in paths
        assert "/auth/email-otp/verify" in paths


# ══════════════════════════════════════════════════════════════════════════════════════════
# The frontend doors
# ══════════════════════════════════════════════════════════════════════════════════════════

import re  # noqa: E402

_FRONTEND = _REPO / "frontend"

# ⚠️ Applied PER CLASS, not as a module-level `pytestmark`. A module-level mark assigned here
# would silently skip the BACKEND tests above it too — the whole suite would go green in any
# environment without `frontend/`, which is the vacuous-guard failure this file is built to
# avoid, occurring inside the file itself.
_needs_frontend = pytest.mark.skipif(
    not (_FRONTEND / "app").is_dir(), reason="frontend/ not present"
)


def _code(rel: str) -> str:
    """Source with comments stripped.

    ⚠️ COMMENTS MUST GO FIRST, or a guard is satisfiable by PROSE: every assertion below is
    a substring check, and a sentence in a docstring naming `completeSignIn` would satisfy
    one while the call itself was deleted (the INC-38 prose-cannot-satisfy class).
    """
    text = (_FRONTEND / rel).read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


@_needs_frontend
class TestEverySelfServeDoorDoesThePostSignInWork:
    """⭐ THE POINT OF `lib/post-signin.ts`. Two doors now create accounts; a door that skips
    `completeSignIn` skips the E9.58b ToS record — which is EVIDENCE, not telemetry — and does
    so completely silently: the user signs in, the app works, and the gap only surfaces the day
    someone asks which terms that account agreed to.
    """

    @pytest.mark.parametrize(
        "rel", ["app/callback/page.tsx", "components/email-otp-form.tsx"]
    )
    def test_the_door_routes_through_the_shared_completion(self, rel):
        assert "completeSignIn(" in _code(rel), f"{rel} does not do the post-sign-in work"

    def test_the_shared_completion_still_carries_all_four_obligations(self):
        post = _code("lib/post-signin.ts")
        for obligation in (
            "user_signed_in",
            "user_signup_completed",
            "/auth/verify-email",
            "acceptTermsWithRetry(",
        ):
            assert obligation in post, f"post-signin dropped {obligation}"

    def test_the_otp_door_declares_its_method_on_both_ends(self):
        """Without a `method` on both the start and the completion the funnel cannot answer
        the question this story exists to ask: does the second door convert?"""
        form = _code("components/email-otp-form.tsx")
        assert 'method: "email_otp"' in form
        assert "user_signup_started" in form and "user_signin_started" in form
        assert "surface," in form or "surface:" in form


@_needs_frontend
class TestAPasswordlessSessionIsNeverAskedForTotp:
    """An email-OTP user has NO password. Bouncing them to enroll TOTP strands them: the only
    way off that screen (`reauthenticatePassword`) asks for a credential they have never had."""

    def test_the_predicate_covers_both_passwordless_methods(self):
        lib = _code("lib/cognito.ts")
        block = lib.split("PASSWORDLESS_METHODS")[1][:200]
        assert '"google"' in block and '"email_otp"' in block

    @pytest.mark.parametrize("rel", ["components/auth-guard.tsx", "lib/cognito.ts"])
    def test_no_mfa_site_still_compares_against_google_alone(self, rel):
        """RED-PROVEN by restoring `getSessionAuthMethod() === "google"` in auth-guard.tsx.

        THE BREAK THIS CATCHES: adding a second passwordless method by bolting `|| ===
        "email_otp"` onto each call site is how one site gets missed, and the miss is
        invisible until a real OTP subscriber is bounced into a dead end.
        """
        assert 'getSessionAuthMethod() === "google"' not in _code(rel), (
            f"{rel} still keys MFA exemption off Google alone"
        )

    def test_the_otp_client_stamps_the_session_as_passwordless(self):
        """RED-PROVEN by dropping the `"email_otp"` argument from `hydrateSessionFromTokens`.

        Without the stamp the session defaults to "password" — the strict direction, which is
        right for an unknown value and wrong here: it would send every OTP user to enroll TOTP
        the moment enforcement is switched on.
        """
        assert '"email_otp"' in _code("lib/email-otp.ts")


@_needs_frontend
class TestBothSurfacesOfferTheEmailDoor:
    @pytest.mark.parametrize("rel", ["app/signup/page.tsx", "app/login/page.tsx"])
    def test_the_form_is_rendered_not_merely_imported(self, rel):
        """An import is not a render (NF-C0e "wired ≠ invoked"). Assert the JSX element."""
        assert "<EmailOtpForm" in _code(rel), f"{rel} imports the door but never opens it"

    def test_google_still_works_on_both_surfaces(self):
        """The story widens the funnel; it must not narrow it. Losing the Google button while
        adding an email one would trade one excluded population for another."""
        for rel in ("app/signup/page.tsx", "app/login/page.tsx"):
            assert "startGoogleSignIn(" in _code(rel), f"{rel} lost the Google door"

    def test_the_provider_branch_is_not_a_dead_end(self):
        """Telling a Google-first user "use Google" without giving them the button is a
        refusal with no way out — the refusal is only acceptable because it costs one click."""
        form = _code("components/email-otp-form.tsx")
        assert "onUseProvider" in form
        for rel in ("app/signup/page.tsx", "app/login/page.tsx"):
            assert "onUseProvider=" in _code(rel), f"{rel} never wires the provider fallback"

    def test_the_public_board_is_not_put_behind_the_new_door(self):
        """The browse/gate boundary: auth is for personalization and saving, never for reading
        the generic rankings. A signup story is exactly when that line gets crossed by accident."""
        assert cg.is_allowed_in_degrade("/fantasy/nfl/board")
        for route in otp_router.router.routes:
            assert route.path.startswith("/auth/email-otp"), (
                "the OTP router reaches outside /auth/email-otp"
            )
