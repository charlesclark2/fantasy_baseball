"""G100-C0-MFA — a passwordless subscriber must not be locked out, and a password
subscriber must still be challenged.

⚠️ THIS FILE GUARDS AN MFA EXEMPTION, so it has to be read in BOTH directions. Every test
below is one half of a pair:

  • the LOCKOUT half — a passwordless `subscriber` reaches the API. Failing this ships a
    403 at a paying customer, pointing them at an enrollment screen whose only exit
    (`reauthenticatePassword`) asks for a password they have never had. No self-service
    recovery exists for that.
  • the BYPASS half — a genuine PASSWORD `subscriber` without TOTP is still refused.
    Failing this turns the whole guard off for whoever the exemption over-reaches, which
    is the exact failure the guard was written to prevent.

A test that only ever asserts "the call succeeded" satisfies the first and says nothing
about the second, so each exemption clause is fixture-isolated per NF-D17: the fixture
satisfies every OTHER clause, so only the clause under test can change the verdict.

⛔ NOTHING HERE PROVES THE FIX WORKS IN PRODUCTION. CI mocks all IO and cannot see Cognito,
so the claim shapes below are the shapes we HANDLE, not shapes anyone measured. What a real
CUSTOM_AUTH session carries is answered by `GET /auth/session-diagnostics` against the live
pool — see `infrastructure/cognito/email_otp/README.md`. That live run is the acceptance
test; this file is only the invariant that survives it.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.backend.dependencies import parse_groups_claim
from app.backend.routers import auth as auth_router
from app.backend.services import cognito as cognito_svc
from app.backend.services import identity as identity_svc

_REPO = Path(__file__).resolve().parents[2]
_PRESIGNUP_HANDLER = _REPO / "infrastructure" / "cognito" / "presignup_link" / "handler.py"

# A pre-provisioned / linked account's username. NOT `google_…` — that is the entire defect:
# since G100-C0 pre-provisioning shipped, the federated-username signal misses exactly the
# people who signed in with Google most recently.
_UUID_USERNAME = "14187448-c091-705c-1199-63858b12c986"


class _Req:
    """The slice of a Starlette Request the guard reads."""

    def __init__(self, claims: dict | None, headers: dict | None = None):
        event = (
            {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
            if claims is not None
            else {}
        )
        self.scope = {"aws.event": event}
        self.headers = headers or {}


@pytest.fixture(autouse=True)
def _enforced(monkeypatch):
    """Every test here runs with enforcement ON — the state the whole story is about."""
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    auth_router._MFA_CACHE.clear()
    yield
    auth_router._MFA_CACHE.clear()


@pytest.fixture
def no_totp(monkeypatch):
    """Nobody has TOTP. Isolates the exemption: any success is the exemption's doing."""
    calls: list[str] = []

    def _read(sub):
        calls.append(sub)
        return False

    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", _read)
    return calls


# ══════════════════════════════════════════════════════════════════════════════════════════
# The delimiter — why the guard was enforcing nothing
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestTheGroupsClaimIsParsedInEveryShapeItArrivesIn:
    """RED-PROVEN by restoring `raw.split(",")` in `require_subscriber_mfa`.

    THE BREAK THIS CATCHES, and it is not the one the story went looking for: the API Gateway
    HTTP API (v2) JWT authorizer flattens a multi-valued claim to a BRACKETED, SPACE-separated
    string (`[fantasy_comp subscriber]` — this repo's own measured finding, recorded in
    `dependencies._groups_from_request`). The guard split on ',' only, so `"[subscriber]"`
    parsed to `["[subscriber]"]`, matched no group, and every subscriber returned early —
    enforcement that reads as ON in the config and enforces NOTHING. The pre-existing tests
    all passed because they were written with the comma form, i.e. they restated the parser's
    own assumption rather than testing it (NF-C0e).
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "[subscriber]",  # HTTP API v2, single group
            "[fantasy_comp subscriber]",  # HTTP API v2, multiple
            "subscriber",  # bare
            "beta_tester,subscriber",  # comma style
            ["subscriber"],  # raw token payload (a real JSON array)
        ],
    )
    def test_subscriber_is_recognised(self, raw):
        assert "subscriber" in parse_groups_claim(raw)

    @pytest.mark.parametrize("raw", [None, "", "   ", [], "[]"])
    def test_absent_is_empty_not_noise(self, raw):
        assert parse_groups_claim(raw) == set()

    def test_a_bracketed_subscriber_is_actually_gated(self, no_totp):
        """The delimiter bug's real-world consequence, at the guard rather than the parser."""
        req = _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"})
        with pytest.raises(HTTPException) as ei:
            auth_router.require_subscriber_mfa(req, user_id="pw-sub")
        assert ei.value.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════════════════
# The lockout half
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestAPasswordlessSubscriberIsNotLockedOut:
    def test_the_passwordless_group_exempts(self, no_totp):
        """RED-PROVEN by deleting the `GROUP_PASSWORDLESS` clause from `_totp_exemption`.

        The fixture satisfies every OTHER clause so only this one can decide it (NF-D17):
        the username is a plain UUID (federated-username clause CANNOT fire), there is no
        `amr` (federated-amr clause CANNOT fire), and TOTP is absent (the enrolment path
        CANNOT fire). So a pass here is the group's doing and nothing else's.
        """
        req = _Req(
            {"cognito:groups": "[passwordless subscriber]", "username": _UUID_USERNAME}
        )
        assert auth_router.require_subscriber_mfa(req, user_id="otp-sub") == "otp-sub"

    def test_it_works_in_the_comma_shape_too(self, no_totp):
        req = _Req({"cognito:groups": "subscriber,passwordless", "username": _UUID_USERNAME})
        assert auth_router.require_subscriber_mfa(req, user_id="otp-sub") == "otp-sub"

    def test_a_linked_google_account_with_a_uuid_username_is_exempt(self, no_totp):
        """The other population the story names: pre-provisioning links Google INTO a native
        user, so this person's username is a UUID and `google_…` never matches. They have no
        password either — the pre-provisioned one is a random string nobody was ever told."""
        req = _Req(
            {
                "cognito:groups": "[passwordless subscriber]",
                "username": _UUID_USERNAME,
                "identities": '[{"providerName":"Google"}]',
            }
        )
        assert auth_router.require_subscriber_mfa(req, user_id="linked") == "linked"

    def test_the_exemption_is_recorded_in_the_logs(self, no_totp, caplog):
        """At flip time the operator must be able to see WHICH signal exempted someone. An
        exemption firing for an unexpected reason is how this guard becomes a bypass, and a
        silent exemption is indistinguishable from a guard that never ran."""
        req = _Req(
            {"cognito:groups": "[passwordless subscriber]", "username": _UUID_USERNAME}
        )
        with caplog.at_level("INFO", logger=auth_router.logger.name):
            auth_router.require_subscriber_mfa(req, user_id="otp-sub")
        assert any("passwordless_group" in r.getMessage() for r in caplog.records)


# ══════════════════════════════════════════════════════════════════════════════════════════
# The bypass half — the exemption must not punch a hole in MFA
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestAPasswordSubscriberIsStillChallenged:
    def test_a_plain_password_subscriber_without_totp_is_refused(self, no_totp):
        req = _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"})
        with pytest.raises(HTTPException) as ei:
            auth_router.require_subscriber_mfa(req, user_id="pw-sub")
        assert ei.value.status_code == 403

    def test_the_identities_claim_still_does_not_exempt(self, no_totp):
        """The E9.19 trap, re-anchored on the new code path: post-E9.7 linking, `identities`
        rides on a linked account's PASSWORD logins too. Exempting on it would skip MFA on
        exactly the session this guard protects. Fixture isolation: no passwordless group,
        no amr, an email username — `identities` is the only thing that could exempt."""
        req = _Req(
            {
                "cognito:groups": "[subscriber]",
                "username": "linked@example.com",
                "identities": '[{"providerName":"Google"}]',
            }
        )
        with pytest.raises(HTTPException) as ei:
            auth_router.require_subscriber_mfa(req, user_id="linked")
        assert ei.value.status_code == 403

    def test_a_passwordless_claim_in_an_unverified_bearer_does_not_exempt(self, no_totp):
        """RED-PROVEN by switching `_groups_from_claims` to `_groups_from_request`.

        THE BREAK THIS CATCHES: `dependencies._groups_from_request` unions in an UNVERIFIED
        bearer decode. That is right for an entitlement read and wrong for an MFA exemption —
        E9.56 measured that a forged payload reaches the Lambda intact on an
        `--authorization-type NONE` route. Groups that grant an exemption may come only from
        the API-Gateway-validated claims, so a caller can never assert their own way out.
        """
        forged = (
            "Bearer eyJhbGciOiJub25lIn0."
            # {"cognito:groups":["subscriber","passwordless"]}
            "eyJjb2duaXRvOmdyb3VwcyI6WyJzdWJzY3JpYmVyIiwicGFzc3dvcmRsZXNzIl19."
            "sig"
        )
        req = _Req(
            {"cognito:groups": "[subscriber]", "username": "pw@example.com"},
            headers={"Authorization": forged},
        )
        with pytest.raises(HTTPException) as ei:
            auth_router.require_subscriber_mfa(req, user_id="pw-sub")
        assert ei.value.status_code == 403

    def test_an_unreadable_mfa_status_still_fails_closed(self, monkeypatch):
        def _boom(sub):
            raise RuntimeError("cognito down")

        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", _boom)
        req = _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"})
        with pytest.raises(HTTPException) as ei:
            auth_router.require_subscriber_mfa(req, user_id="pw-sub")
        assert ei.value.status_code == 403

    def test_an_enrolled_password_subscriber_passes(self, monkeypatch):
        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda s: True)
        req = _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"})
        assert auth_router.require_subscriber_mfa(req, user_id="pw-sub") == "pw-sub"


class TestNothingElseChanged:
    def test_a_non_subscriber_passes_without_a_cognito_read(self, no_totp):
        req = _Req({"cognito:groups": "[beta_tester passwordless]", "username": "b@x.com"})
        assert auth_router.require_subscriber_mfa(req, user_id="b") == "b"
        assert no_totp == [], "a non-subscriber must not cost an AdminGetUser"

    def test_the_flag_off_path_is_still_a_no_op(self, monkeypatch, no_totp):
        monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "0")
        req = _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"})
        assert auth_router.require_subscriber_mfa(req, user_id="pw") == "pw"

    def test_an_anonymous_caller_on_a_public_route_passes_through(self, no_totp):
        assert auth_router.require_subscriber_mfa(_Req(None), user_id=None) is None


# ══════════════════════════════════════════════════════════════════════════════════════════
# Which signal fired — each clause isolated (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestTheExemptionReasonNamesTheSignalThatFired:
    def test_amr_only(self):
        claims = {"username": "pw@example.com", "amr": '["Google"]'}
        assert auth_router._totp_exemption(claims, set()) == "amr_federated"

    def test_username_shape_only(self):
        claims = {"username": "Google_10979331"}
        assert auth_router._totp_exemption(claims, set()) == "federated_username"

    def test_group_only(self):
        claims = {"username": _UUID_USERNAME}
        groups = {"subscriber", cognito_svc.GROUP_PASSWORDLESS}
        assert auth_router._totp_exemption(claims, groups) == "passwordless_group"

    def test_a_password_session_has_no_exemption(self):
        claims = {"username": "pw@example.com", "identities": '[{"providerName":"Google"}]'}
        assert auth_router._totp_exemption(claims, {"subscriber"}) is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            (["Google"], ["Google"]),
            ('["Google"]', ["Google"]),
            ("pwd", ["pwd"]),
            (None, []),
        ],
    )
    def test_amr_is_parsed_in_every_delivery_shape(self, raw, expected):
        """`amr` arrives as a list, a JSON string, or a bare string depending on the path.
        Reported verbatim by the diagnostics endpoint because what a CUSTOM_AUTH session
        carries here is an open measurement, not something to reason about."""
        assert auth_router.parse_amr({"amr": raw} if raw is not None else {}) == expected


# ══════════════════════════════════════════════════════════════════════════════════════════
# The group has to actually get applied — at BOTH creation points, and NOWHERE else
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestBothCreationPathsMarkTheAccountPasswordless:
    """Two files that cannot import each other create the passwordless population: the API's
    OTP path and the PreSignUp trigger (a separate deployment artifact). A miss in either is
    invisible until the flip, and then it is a lockout for whoever was created by that path.
    """

    def test_the_otp_path_marks_the_created_user(self, monkeypatch):
        client = MagicMock()
        client.admin_create_user.return_value = {"User": {"Username": "uuid-new"}}
        monkeypatch.setattr(identity_svc, "_client", lambda: client)
        # ⚠️ Deliberately NOT patching `cognito_svc._client`: the group write must go through
        # the client this function already built. A second client here would be invisible to
        # this fixture and would reach for the real network inside a suite that mocks all IO.
        monkeypatch.setattr(
            cognito_svc, "_client", lambda: pytest.fail("built a second boto3 client")
        )

        assert identity_svc.create_native_user("a@b.co") == "uuid-new"

        kwargs = client.admin_add_user_to_group.call_args.kwargs
        assert kwargs["GroupName"] == cognito_svc.GROUP_PASSWORDLESS
        # The pool's generated UUID, never the email — the same trap the link target hit.
        assert kwargs["Username"] == "uuid-new"

    def test_a_failed_marking_does_not_cost_the_person_their_signin(self, monkeypatch):
        """Best-effort by design: this runs inside the only public signup paths, where the
        repo's discipline is to fail OPEN. The failure is loud instead (see the next test)."""
        client = MagicMock()
        client.admin_create_user.return_value = {"User": {"Username": "uuid-new"}}
        client.admin_add_user_to_group.side_effect = RuntimeError("throttled")
        monkeypatch.setattr(identity_svc, "_client", lambda: client)

        assert identity_svc.create_native_user("a@b.co") == "uuid-new"

    def test_a_failed_marking_names_the_repair_command(self, monkeypatch, caplog):
        """A silently missing group is a future lockout with nothing to point at. The log line
        has to be greppable AND actionable — whoever finds it is looking at a 403 they cannot
        explain, months later."""
        group_client = MagicMock()
        group_client.admin_add_user_to_group.side_effect = RuntimeError("nope")
        monkeypatch.setattr(cognito_svc, "_client", lambda: group_client)

        with caplog.at_level("ERROR", logger=cognito_svc.logger.name):
            assert cognito_svc.mark_passwordless("uuid-new") is False
        message = " ".join(r.getMessage() for r in caplog.records)
        assert "[ALERT]" in message
        assert "admin-add-user-to-group" in message

    def test_the_trigger_marks_the_pre_provisioned_user(self, presignup):
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "uuid-abc"}}

        presignup.handler(_external_event(), None)

        kwargs = presignup.cognito.admin_add_user_to_group.call_args.kwargs
        assert kwargs["GroupName"] == "passwordless"
        assert kwargs["Username"] == "uuid-abc"

    def test_the_trigger_does_NOT_mark_an_existing_native_user(self, presignup):
        """⭐ THE BYPASS HALF OF THE CREATION RULE, and the easiest thing to get wrong here.
        When a native user already exists we link Google INTO it — and that account may well
        have a real, user-chosen password (every beta account does). Marking it passwordless
        would hand a permanent MFA exemption to a password account, which is the bypass this
        whole story is trying not to create.

        RED-PROVEN by moving `_mark_passwordless` out of `_preprovision_native_user` and into
        `handler` after the link.
        """
        presignup.cognito.list_users.return_value = {"Users": [{"Username": "native-uuid"}]}
        presignup.handler(_external_event(), None)
        presignup.cognito.admin_add_user_to_group.assert_not_called()

    def test_a_failed_marking_still_fails_open_in_the_trigger(self, presignup):
        presignup.cognito.list_users.return_value = {"Users": []}
        presignup.cognito.admin_create_user.return_value = {"User": {"Username": "uuid-abc"}}
        presignup.cognito.admin_add_user_to_group.side_effect = RuntimeError("denied")

        out = presignup.handler(_external_event(), None)

        assert out is not None
        presignup.cognito.admin_link_provider_for_user.assert_called_once()

    def test_the_two_implementations_agree_on_the_group_name(self):
        """The trigger cannot import the constant, so the agreement is pinned here. A drifted
        name is a lockout for one of the two populations and nothing else would say so."""
        tree = ast.parse(_PRESIGNUP_HANDLER.read_text())
        literal = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "_PASSWORDLESS_GROUP" for t in node.targets
            ):
                literal = node.value.value
        assert literal, "the trigger no longer defines _PASSWORDLESS_GROUP"
        assert literal == cognito_svc.GROUP_PASSWORDLESS


def _external_event(email="new@example.com", username="google_12345"):
    return {
        "triggerSource": "PreSignUp_ExternalProvider",
        "userPoolId": "us-east-1_gG9zMbwQt",
        "userName": username,
        "request": {"userAttributes": {"email": email}},
    }


@pytest.fixture
def presignup(monkeypatch):
    """Import the trigger Lambda by path with boto3 mocked — it lives outside the package
    tree (a separate deployment artifact), so a normal import cannot reach it."""
    monkeypatch.delenv("PRESIGNUP_PREPROVISION", raising=False)
    fake_client = MagicMock()
    fake_boto3 = MagicMock()
    fake_boto3.client.return_value = fake_client
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    spec = importlib.util.spec_from_file_location(
        "presignup_link_handler_g100c0_mfa", _PRESIGNUP_HANDLER
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.cognito = fake_client
    return module


# ══════════════════════════════════════════════════════════════════════════════════════════
# The live instrument
# ══════════════════════════════════════════════════════════════════════════════════════════


class TestSessionDiagnosticsAnswersTheQuestionTheFixDependsOn:
    """This endpoint is what turns "we think a CUSTOM_AUTH token carries X" into a
    measurement. Its own tests can only check that it reports faithfully — the answer it
    returns against the real pool is the acceptance test, not this."""

    def test_it_is_self_only(self):
        """It reports one session's claims: the CALLER'S. `get_user_id` (not the optional
        resolver) means an anonymous request is 401'd rather than served an empty shell, and
        there is no user parameter anyone could point at somebody else."""
        params = inspect.signature(auth_router.session_diagnostics).parameters
        assert params["user_id"].default.dependency is auth_router.get_user_id
        assert set(params) == {"request", "user_id"}

    def test_it_reports_the_raw_claim_shape_not_just_the_parse(self, monkeypatch):
        """The delimiter style is the detail that made the old parse a no-op, so it has to be
        visible verbatim — an operator reading a parsed list cannot tell which shape arrived."""
        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda s: False)
        req = _Req(
            {
                "cognito:groups": "[passwordless subscriber]",
                "username": _UUID_USERNAME,
                "amr": '["custom_auth"]',
            }
        )
        out = auth_router.session_diagnostics(req, user_id="otp-sub")
        assert out.groups_claim_raw == "[passwordless subscriber]"
        assert out.groups == ["passwordless", "subscriber"]
        assert out.amr == ["custom_auth"]
        assert out.amr_claim_raw == '["custom_auth"]'
        assert out.is_passwordless is True and out.is_subscriber is True

    def test_the_dry_run_is_two_sided(self, monkeypatch):
        """The whole point: it answers BOTH acceptance questions without a real subscription
        and without flipping the flag in production."""
        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda s: False)

        passwordless = auth_router.session_diagnostics(
            _Req({"cognito:groups": "[passwordless subscriber]", "username": _UUID_USERNAME}),
            user_id="otp-sub",
        )
        assert passwordless.totp_exempt is True
        assert passwordless.totp_exempt_reason == "passwordless_group"
        assert passwordless.would_be_blocked_if_subscriber is False

        auth_router._MFA_CACHE.clear()
        password = auth_router.session_diagnostics(
            _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"}),
            user_id="pw-sub",
        )
        assert password.totp_exempt is False
        assert password.would_be_blocked_if_subscriber is True

    def test_an_unreadable_totp_read_reports_unknown_and_blocks(self, monkeypatch):
        """NF1.7(a): a check that did not run is never scored as a pass. `None` says the read
        failed; the verdict still fails closed, matching the guard."""

        def _boom(sub):
            raise RuntimeError("cognito down")

        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", _boom)
        out = auth_router.session_diagnostics(
            _Req({"cognito:groups": "[subscriber]", "username": "pw@example.com"}),
            user_id="pw-sub",
        )
        assert out.totp_enrolled is None
        assert out.would_be_blocked_if_subscriber is True

    def test_it_reports_claim_names_but_not_their_values(self, monkeypatch):
        """A diagnostics endpoint is a disclosure surface. Only the claims the guard actually
        uses are echoed; everything else is named, never dumped."""
        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda s: False)
        req = _Req(
            {
                "cognito:groups": "[subscriber]",
                "username": "pw@example.com",
                "email": "someone@example.com",
                "origin_jti": "a-secret-looking-value",
            }
        )
        out = auth_router.session_diagnostics(req, user_id="pw-sub")
        body = out.model_dump_json()
        assert "origin_jti" in out.claim_keys and "email" in out.claim_keys
        assert "a-secret-looking-value" not in body
        assert "someone@example.com" not in body

    def test_it_reports_whether_the_authorizer_actually_ran(self, monkeypatch):
        """An exemption read from claims the gateway never validated would be self-asserted.
        The flag makes that visible instead of implied."""
        monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda s: False)
        assert (
            auth_router.session_diagnostics(_Req(None), user_id="u").authorizer_context_present
            is False
        )

    def test_it_carries_a_version_marker(self):
        """`deploy.sh` is a manual step with no CD; a merged PR is not a deployed Lambda. The
        marker is how the operator confirms they are testing the build they think they are."""
        assert auth_router._GUARD_VERSION

    def test_its_response_can_never_be_publicly_cached(self):
        """⚠️ A new route under an existing prefix silently inherits that prefix's cache rule
        and degrade entry — this repo has already paid for that once (NF-EPIC 1: a gated route
        placed under a public path inherited its public cache). `/auth` IS degrade-allowlisted,
        which is correct (nobody can sign in otherwise) and says nothing about caching. This
        response is per-caller, so a shared cache entry would hand one person's session facts to
        the next caller. It is authenticated, and `cache_control_for` forces `private, no-store`
        on anything carrying a token — assert that rather than assume it.
        """
        from app.backend.services.cost_guardrails import cache_control_for

        header = cache_control_for(
            "/auth/session-diagnostics", has_authorization=True, status_code=200
        )
        assert "no-store" in header and "private" in header
