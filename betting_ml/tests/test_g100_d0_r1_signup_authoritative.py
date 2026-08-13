"""G100-D0-R1 — `user_signup_completed` must count ACCOUNTS, not button clicks.

WHY THIS FILE EXISTS. The event keyed on which affordance the visitor pressed: `/signup` stashed
`intent: "signup"` across the Cognito redirect and the callback fired the event only on that
branch. Google federation auto-provisions an account at EITHER door, so that rule was wrong in
both directions at once:

  · a first-time visitor who clicked SIGN IN got a real, new account and emitted no signup event
    at all — and because R1's funnel is ORDERED, those people were discarded from it outright,
    appearing neither as signups nor as drop-offs. Measured, not hypothetical: all 16 auth events
    in production's first 48h used the /login door.
  · a RETURNING user who clicked SIGN UP emitted a signup that never happened.

⭐ FIXING ONE DIRECTION AND NOT THE OTHER LEAVES THE FUNNEL WRONG, so both are pinned here, and
each has its own case rather than sharing one — a guard whose fixture trips a different clause
proves nothing about the clause it names (NF-D17).

The signal is the server's: `/auth/accept-terms` already wrote with `if_not_exists`, so it alone
knows whether a given call was the first. The three properties that make that trustworthy —
atomicity, ABSENT-is-not-FALSE across the deploy skew, and the under-count-never-over-count
failure direction — are each pinned below, because losing any one of them silently returns a
number that reads fine and is not.

⚠️ THE BEHAVIOURAL HALF OF THIS STORY IS THE E2E SPEC, not this file:
`frontend/e2e/specs/signup-attribution.spec.ts` drives the REAL callback page against an
intercepted ingest endpoint, because a source-inspection guard cannot tell a `capture()` that
fires from one that is unreachable. The tests here pin the server contract (executed, with a fake
table) and the client's structure (inspected).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.backend.routers import auth as auth_router
from app.backend.services import dynamo

_FRONTEND = Path("frontend")
_BACKEND = Path("app/backend")

_UID = "sub-g100-d0-r1"


def _code(rel: str) -> str:
    """Frontend source with comments stripped FIRST.

    ⚠️ Comments must go before any substring assertion or a guard is satisfiable by PROSE — this
    file's own explanatory comments name every symbol it asserts on (INC-38).
    """
    text = (_FRONTEND / rel).read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


def _py(path: Path) -> str:
    """Python source with comments and docstrings stripped, for the same reason."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body.pop(0)
    return ast.unparse(tree)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The server signal — executed, not inspected
# ══════════════════════════════════════════════════════════════════════════════════════════════


class _FakeTable:
    """A DynamoDB Table stand-in that models the ONE behaviour under test.

    `update_item(ReturnValues="ALL_OLD")` returns the item as it was BEFORE the update, and omits
    `Attributes` entirely when there was no item. Both shapes are real and they mean different
    things to a naive reader, which is why both are exercised.
    """

    def __init__(self, item: dict | None = None):
        self.item = dict(item) if item is not None else None
        self.calls: list[dict] = []
        self.reads = 0

    def update_item(self, **kwargs):
        self.calls.append(kwargs)
        before = self.item
        self.item = {**(before or {}), "tos_accepted_at": "2026-08-13T00:00:00Z"}
        if kwargs.get("ReturnValues") != "ALL_OLD":
            return {}
        return {"Attributes": dict(before)} if before is not None else {}

    def get_item(self, **kwargs):
        self.reads += 1
        return {"Item": dict(self.item)} if self.item else {}


@pytest.fixture
def table(monkeypatch):
    t = _FakeTable()
    monkeypatch.setattr(dynamo, "_users_table", lambda: t)
    return t


def test_a_brand_new_account_reports_created(table):
    """The whole point: no prior item ⇒ this sign-in created the account."""
    assert dynamo.record_tos_acceptance(_UID, "2026-06-14") is True


def test_an_account_that_already_accepted_reports_not_created(table, monkeypatch):
    """The other direction, and the one that kills the pre-R1 false positive: a RETURNING user
    who clicks Sign Up must not be counted."""
    t = _FakeTable({"user_id": _UID, "tos_accepted_at": "2026-08-01T00:00:00Z"})
    monkeypatch.setattr(dynamo, "_users_table", lambda: t)
    assert dynamo.record_tos_acceptance(_UID, "2026-06-14") is False


def test_an_existing_profile_with_no_acceptance_still_reports_created(monkeypatch):
    """A user row can exist without ever having accepted (some other write created it).

    The test must therefore be on the ATTRIBUTE, never on the item — keying on "was there an
    Item" would report a returning user as new the moment anything else wrote their profile
    first.
    """
    t = _FakeTable({"user_id": _UID, "email": "someone@example.com"})
    monkeypatch.setattr(dynamo, "_users_table", lambda: t)
    assert dynamo.record_tos_acceptance(_UID, "2026-06-14") is True


def test_the_answer_comes_from_the_write_itself_not_a_second_read(table):
    """⭐ ATOMICITY IS THE PROPERTY, AND IT IS WHAT STOPS A DOUBLE-COUNT.

    A read-then-write (or a follow-up `get_item`) lets two concurrent calls — a retry racing its
    own first attempt, a double-invoked effect — BOTH observe "no acceptance yet" and both report
    a signup. `ReturnValues="ALL_OLD"` is answered by the same atomic update, so exactly one
    caller can ever see the absence. Over-counting is strictly worse than the under-count this
    story replaces, because nothing downstream questions a number that is too high.
    """
    dynamo.record_tos_acceptance(_UID, "2026-06-14")
    assert table.calls, "record_tos_acceptance did not write at all"
    assert table.calls[0].get("ReturnValues") == "ALL_OLD", (
        "the created-flag is no longer derived from the write's own ALL_OLD response — a separate "
        "read would let two concurrent callers both report the same signup"
    )
    assert table.reads == 0, "a separate read snuck back in; see above"


def test_the_write_still_never_overwrites_the_original_timestamp(table):
    """E9.58b's property, re-asserted because this story rewrote the function around it."""
    dynamo.record_tos_acceptance(_UID, "2026-06-14")
    assert "if_not_exists" in table.calls[0]["UpdateExpression"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The router contract — additive, and still loud on failure
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("created", [True, False])
def test_the_endpoint_reports_what_the_store_said(monkeypatch, created: bool):
    monkeypatch.setattr(auth_router, "record_tos_acceptance", lambda *a, **k: created)
    assert auth_router.accept_terms(user_id=_UID).created is created


def test_the_endpoint_still_raises_rather_than_reporting_success_for_a_failed_write(monkeypatch):
    """E9.58b's guarantee. Adding a response body must not turn a 503 into a cheerful
    `{"created": false}` — which would be a lost ToS record reported as a returning user."""

    def boom(*a, **k):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(auth_router, "record_tos_acceptance", boom)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        auth_router.accept_terms(user_id=_UID)
    assert exc.value.status_code == 503


def test_the_response_shape_change_is_additive():
    """⚠️ NF-C0. The API Lambda ships only via deploy.sh while the frontend auto-deploys, so an
    OLDER client will read this response for as long as the skew lasts.

    Additivity is trivially satisfied HERE — the endpoint returned 204 with no body at all, so
    there is no key to remove — but it is pinned anyway because the next change to this model is
    the one that can break it, and the 204 that made it free is now gone.
    """
    src = _py(_BACKEND / "routers/auth.py")
    model = src.split("class TermsAcceptanceResult(")[1].split("\n@")[0]
    assert "created: bool" in model
    assert "status_code=204" not in src.split("def accept_terms(")[0].split("@router.post")[-1], (
        "a 204 cannot carry a body — the field would be silently dropped"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The client — both directions of the fix, one case each
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _report_body() -> str:
    """The function that decides whether to emit, with nothing else in scope."""
    post = _code("lib/post-signin.ts")
    assert "function reportSignupCompletion(" in post, (
        "the signup decision is no longer a named function — the guards below would be reading "
        "whatever happened to be nearby"
    )
    return post.split("function reportSignupCompletion(")[1]


def test_a_new_account_at_the_signin_door_is_counted():
    """DIRECTION 1 — the under-count this story exists to fix.

    The emit must sit under the server's `created`, with no `intent` condition gating it, or a
    first-timer entering through /login is discarded from the funnel exactly as before.
    """
    body = _report_body()
    emit = body.split("user_signup_completed")[0]
    assert "acceptance.created" in emit, (
        "the signup event is not conditioned on the server's created flag — it is back to keying "
        "on which button was pressed, and /login-door signups are invisible again"
    )


def test_a_returning_user_who_clicks_sign_up_is_not_counted():
    """DIRECTION 2 — the pre-existing FALSE POSITIVE, which is just as wrong.

    ⭐ The fixture for this clause deliberately satisfies the other one: the source under test
    already emits on `created`, so the only thing this can fail on is the server's answer being
    overridden by intent. `known` must short-circuit before the intent fallback is reachable.
    """
    body = _report_body()
    known_branch = body.split("if (acceptance.known)")
    assert len(known_branch) == 2, (
        "reportSignupCompletion no longer branches on whether the server ANSWERED — an "
        "authoritative `created: false` can now be overridden by the client's intent, restoring "
        "the false positive for a returning user who clicks Sign Up"
    )
    assert "return" in known_branch[1].split('if (intent === "signup")')[0], (
        "the known branch does not return before the intent fallback, so a server answer of "
        "created:false falls through to the button rule"
    )


def test_an_absent_field_is_a_deploy_skew_not_a_negative_answer():
    """⭐ THE PROPERTY MOST LIKELY TO BE 'SIMPLIFIED' AWAY, and the one that would hurt most.

    `created` ABSENT means an old Lambda answered (frontend auto-deploys; the API does not).
    Collapsing that into `created: false` takes step 2 of the funnel to a flat ZERO for the whole
    skew window — and a zero on a conversion chart reads as a conversion collapse, not as a
    missing deploy. Same distinction `lib/terms.ts` already draws for `tos_accepted_at`.
    """
    lib = _code("lib/terms.ts")
    accept = lib.split("export async function acceptTerms(")[1].split("\n}")[0]
    assert 'typeof res.created !== "boolean"' in accept, (
        "acceptTerms no longer checks that `created` is genuinely a boolean, so an absent field "
        "from an un-deployed Lambda reads as `created: false`"
    )
    assert "known: false" in accept


def test_the_skew_fallback_exists_and_is_labelled_on_the_wire():
    """A window with NO signal is the one place the old button rule is still the best available
    answer. It must be distinguishable in the DATA, or a funnel read during a deploy looks
    identical to one taken after it."""
    body = _report_body()
    assert 'signal: "server"' in body and 'signal: "intent_fallback"' in body, (
        "the two provenances are indistinguishable in the event stream"
    )


def test_the_terms_gate_deliberately_counts_nothing():
    """`created` is a FIRST-ACCEPTANCE signal, exact only for accounts made since E9.58b started
    writing acceptance on every sign-in. The gate's population is precisely where that is
    weakest — accounts predating that record — so emitting there would report a years-old
    account as a fresh signup. Silence is the safe direction (docs/g100_d0_funnel.md §3)."""
    assert "user_signup_completed" not in _code("components/terms-gate.tsx")


def test_both_self_serve_doors_still_route_through_the_one_place_that_emits():
    """The server answer is only useful if every account-creating door observes it. Both doors
    delegate to `completeSignIn`, and `completeSignIn` is where the answer is read."""
    for rel in ("app/callback/page.tsx", "components/email-otp-form.tsx"):
        assert "completeSignIn(" in _code(rel), f"{rel} bypasses the shared completion"
    post = _code("lib/post-signin.ts")
    assert "acceptTermsWithRetry(accessToken)" in post
    assert "reportSignupCompletion(" in post


def test_the_guards_can_actually_fail():
    """Anti-vacuity: every reader above must be reading real source, and `_code`/`_py` must
    really strip comments — otherwise the prose in this very file would satisfy them."""
    post = _code("lib/post-signin.ts")
    assert len(post) > 500 and "posthog.capture" in post
    assert "THE SIGNUP EVENT NOW RIDES" not in post, "_code did not strip line comments"
    assert "WHY THE RETURN VALUE EXISTS" not in _py(_BACKEND / "services/dynamo.py"), (
        "_py did not strip docstrings"
    )
