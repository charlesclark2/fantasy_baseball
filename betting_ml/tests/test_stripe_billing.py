"""E9.8 — Stripe subscription billing (router + server-side MFA guard).

No network / no real Stripe / no boto3: the Stripe SDK's signature verification is
monkeypatched to return a fabricated event, and the Cognito/Dynamo service calls are
replaced with in-memory fakes. Router functions are called directly (no TestClient —
httpx isn't a test dep, matching test_alerts_router.py).

Covers:
  • founding-price gate — $10 for sub #1–100, $20 at/over the cap, at the boundary
  • webhook idempotency — a replayed subscription.created promotes again (idempotent)
    but counts the conversion exactly ONCE
  • promote / churn transitions on the mapped events
  • the server-side subscriber-MFA guard, incl. the federated-exemption trap (never
    key off the id-token identities claim; fail closed on ambiguity)
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from app.backend.routers import auth as auth_router
from app.backend.routers import stripe as billing


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakeCognito:
    def __init__(self):
        self.groups: dict[str, set[str]] = {}
        self.promoted: list[str] = []
        self.churned: list[str] = []

    def groups_for_user(self, sub):
        return sorted(self.groups.get(sub, set()))

    def promote_to_subscriber(self, sub):
        self.promoted.append(sub)
        self.groups.setdefault(sub, set()).update({"subscriber"})
        self.groups[sub].discard("beta_tester")
        self.groups[sub].discard("churned")

    def demote_to_churned(self, sub):
        self.churned.append(sub)
        self.groups.setdefault(sub, set()).discard("subscriber")
        self.groups[sub].add("churned")


class _FakeStore:
    """In-memory stand-in for the dynamo billing helpers."""

    def __init__(self):
        self.processed: set[str] = set()
        self.slots = 0
        self.customers: dict[str, str] = {}       # sub -> customer
        self.reverse: dict[str, str] = {}          # customer -> sub

    def stripe_event_already_processed(self, event_id):
        if event_id in self.processed:
            return True
        self.processed.add(event_id)
        return False

    def founding_slots_used(self):
        return self.slots

    def increment_founding_slots(self):
        self.slots += 1
        return self.slots

    def link_stripe_customer(self, sub, customer):
        self.customers[sub] = customer
        self.reverse[customer] = sub

    def user_id_for_stripe_customer(self, customer):
        return self.reverse.get(customer)

    def stripe_customer_for_user(self, sub):
        return self.customers.get(sub)


@pytest.fixture
def store(monkeypatch):
    s = _FakeStore()
    for name in (
        "stripe_event_already_processed",
        "founding_slots_used",
        "increment_founding_slots",
        "link_stripe_customer",
        "user_id_for_stripe_customer",
        "stripe_customer_for_user",
    ):
        monkeypatch.setattr(billing.dynamo, name, getattr(s, name))
    return s


@pytest.fixture
def cog(monkeypatch):
    c = _FakeCognito()
    monkeypatch.setattr(billing.cognito, "groups_for_user", c.groups_for_user)
    monkeypatch.setattr(billing.cognito, "promote_to_subscriber", c.promote_to_subscriber)
    monkeypatch.setattr(billing.cognito, "demote_to_churned", c.demote_to_churned)
    return c


class _FakeRequest:
    def __init__(self, body=b"{}", headers=None):
        self._body = body
        self.headers = headers or {"stripe-signature": "sig"}

    async def body(self):
        return self._body


def _run_webhook(monkeypatch, event, store):
    """Drive the async webhook with a fabricated event.

    The event is passed as the RAW request body (as Stripe delivers it); the handler
    parses it via json.loads(payload) after signature verification, so this exercises
    the real plain-dict path (construct_event returns a non-dict StripeObject in prod)."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    # Verify step is stubbed to succeed; its return value is intentionally NOT used.
    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", lambda *a, **k: object())
    body = json.dumps(event).encode()
    return asyncio.run(billing.stripe_webhook(_FakeRequest(body=body)))


# ── Founding-price gate ──────────────────────────────────────────────────────


def test_founding_price_below_cap(monkeypatch, store):
    monkeypatch.setenv("STRIPE_PRICE_FOUNDING", "price_founding")
    monkeypatch.setenv("STRIPE_PRICE_STANDARD", "price_standard")
    store.slots = 50
    price, tier = billing._price_for_new_checkout()
    assert (price, tier) == ("price_founding", "founding")


def test_founding_price_at_boundary(monkeypatch, store):
    """Slot #99 used (99 conversions) → the 100th checkout is still founding; at 100 → standard."""
    monkeypatch.setenv("STRIPE_PRICE_FOUNDING", "price_founding")
    monkeypatch.setenv("STRIPE_PRICE_STANDARD", "price_standard")
    store.slots = 99
    assert billing._price_for_new_checkout() == ("price_founding", "founding")
    store.slots = 100
    assert billing._price_for_new_checkout() == ("price_standard", "standard")


def test_pricing_endpoint_reports_tier(monkeypatch, store):
    store.slots = 100
    out = billing.subscription_pricing(_="sub-x")
    assert out.tier == "standard"
    assert out.founding_available is False
    assert out.unit_amount == 2000
    store.slots = 3
    out2 = billing.subscription_pricing(_="sub-x")
    assert out2.tier == "founding" and out2.founding_available is True and out2.unit_amount == 1000


# ── Webhook: promote + idempotent counting ───────────────────────────────────


def _sub_created_event(event_id, sub="sub-1", customer="cus_1"):
    return {
        "id": event_id,
        "type": "customer.subscription.created",
        "data": {"object": {"metadata": {"cognito_sub": sub}, "customer": customer}},
    }


def test_subscription_created_promotes_and_counts_once(monkeypatch, store, cog):
    event = _sub_created_event("evt_1")
    _run_webhook(monkeypatch, event, store)
    # Replay the SAME event id (Stripe duplicate/retry).
    _run_webhook(monkeypatch, event, store)

    assert cog.promoted == ["sub-1", "sub-1"]   # promote is idempotent → safe to redo
    assert store.slots == 1                       # …but the conversion counts exactly once
    assert store.reverse["cus_1"] == "sub-1"      # customer↔sub reverse map recorded


def test_two_distinct_conversions_count_twice(monkeypatch, store, cog):
    _run_webhook(monkeypatch, _sub_created_event("evt_a", sub="a", customer="cus_a"), store)
    _run_webhook(monkeypatch, _sub_created_event("evt_b", sub="b", customer="cus_b"), store)
    assert store.slots == 2


def test_subscription_deleted_churns(monkeypatch, store, cog):
    event = {
        "id": "evt_del",
        "type": "customer.subscription.deleted",
        "data": {"object": {"metadata": {"cognito_sub": "sub-9"}, "customer": "cus_9"}},
    }
    _run_webhook(monkeypatch, event, store)
    assert cog.churned == ["sub-9"]
    assert store.slots == 0  # churn never touches the founding counter (permanent grandfather)


def test_payment_failed_churns_via_reverse_lookup(monkeypatch, store, cog):
    # invoice.payment_failed carries only a customer id → resolve via the reverse map.
    store.link_stripe_customer("sub-7", "cus_7")
    event = {
        "id": "evt_pf",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_7"}},
    }
    _run_webhook(monkeypatch, event, store)
    assert cog.churned == ["sub-7"]


def test_bad_signature_is_400(monkeypatch, store):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    def _boom(*a, **k):
        raise billing.stripe.SignatureVerificationError("bad", "sig")

    monkeypatch.setattr(billing.stripe.Webhook, "construct_event", _boom)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(billing.stripe_webhook(_FakeRequest()))
    assert ei.value.status_code == 400


def test_missing_webhook_secret_is_503(monkeypatch, store):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    with pytest.raises(HTTPException) as ei:
        asyncio.run(billing.stripe_webhook(_FakeRequest()))
    assert ei.value.status_code == 503


# ── Checkout guard: beta/subscriber/admin never see checkout ─────────────────


def test_checkout_refused_for_beta_tester(monkeypatch, store, cog):
    cog.groups["beta-guy"] = {"beta_tester"}
    with pytest.raises(HTTPException) as ei:
        billing.create_checkout_session(request=None, user_id="beta-guy")
    assert ei.value.status_code == 409


def test_status_tier_mapping(store, cog):
    cog.groups["s"] = {"subscriber"}
    st = billing.subscription_status(user_id="s")
    assert st.tier == "subscriber" and st.has_access is True and st.is_beta is False
    # No Stripe customer linked → the period fields default off, never break the call.
    assert st.cancel_at_period_end is False and st.current_period_end is None

    cog.groups["b"] = {"beta_tester"}
    assert billing.subscription_status(user_id="b").is_beta is True

    cog.groups["f"] = set()
    assert billing.subscription_status(user_id="f").has_access is False


# ── E9.57 finding: Stripe's Customer Portal cancels at period end, not immediately ──
# The webhook only demotes on `customer.subscription.deleted`, which Stripe fires once the
# paid period actually ends — so a canceled subscriber correctly stays `tier=subscriber`
# until then. These fields let Settings say so honestly instead of looking unchanged.
#
# ⚠️ CONFIRMED LIVE IN PROD (2026-08-05): the first cut of these fakes was plain dicts,
# which support `.get()` — so they passed even though the real handler code called
# `sub.get(...)` on a genuine Stripe SDK `StripeObject`, which does NOT define `.get()`
# and raised `AttributeError: get` in prod, silently swallowed by the handler's broad
# except into the exact same "nothing scheduled" default a real uncanceled subscription
# would produce. `_FakeStripeSub` below mimics the REAL SDK object's interface (`in` /
# `[...]` via `__contains__`/`__getitem__`, no `.get()`) so a regression back to `.get()`
# fails these tests with the same AttributeError it produced live, instead of silently
# passing. Sibling of the already-documented `construct_event()` StripeObject trap.


class _FakeStripeSub:
    def __init__(self, data):
        self._data = data

    def __contains__(self, k):
        return k in self._data

    def __getitem__(self, k):
        return self._data[k]

    def __getattr__(self, k):
        if k in self._data:
            return self._data[k]
        raise AttributeError(k)  # real StripeObject behavior for e.g. `.get`


class _FakeSubList:
    def __init__(self, data):
        self.data = [_FakeStripeSub(d) for d in data]


def test_fake_stripe_sub_does_not_support_dict_get():
    """Fidelity check: prove the fake matches the real SDK object's `.get()` gap —
    a fixture that instead used a plain dict would pass even after a regression."""
    sub = _FakeStripeSub({"cancel_at_period_end": True})
    with pytest.raises(AttributeError):
        sub.get("cancel_at_period_end")
    assert sub["cancel_at_period_end"] is True
    assert "cancel_at_period_end" in sub


def test_status_reports_scheduled_cancellation(monkeypatch, store, cog):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    cog.groups["s"] = {"subscriber"}
    store.link_stripe_customer("s", "cus_s")
    monkeypatch.setattr(
        billing.stripe.Subscription,
        "list",
        lambda **kw: _FakeSubList([{"cancel_at_period_end": True, "current_period_end": 1999999999}]),
    )
    st = billing.subscription_status(user_id="s")
    assert st.tier == "subscriber" and st.has_access is True  # access continues
    assert st.cancel_at_period_end is True
    assert st.current_period_end == 1999999999


def test_status_active_subscription_has_no_scheduled_cancellation(monkeypatch, store, cog):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    cog.groups["s"] = {"subscriber"}
    store.link_stripe_customer("s", "cus_s")
    monkeypatch.setattr(
        billing.stripe.Subscription,
        "list",
        lambda **kw: _FakeSubList([{"cancel_at_period_end": False, "current_period_end": 1999999999}]),
    )
    st = billing.subscription_status(user_id="s")
    assert st.cancel_at_period_end is False


def test_status_falls_back_to_the_subscription_item_when_top_level_period_end_is_absent(
    monkeypatch, store, cog
):
    """Stripe moved `current_period_end` off the top-level Subscription object onto each
    subscription item as of API version 2025-03-31 — confirm the fallback read works when
    the top-level field is genuinely absent (not just falsy)."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    cog.groups["s"] = {"subscriber"}
    store.link_stripe_customer("s", "cus_s")
    monkeypatch.setattr(
        billing.stripe.Subscription,
        "list",
        lambda **kw: _FakeSubList(
            [
                {
                    "cancel_at_period_end": True,
                    "items": _FakeStripeSub({"data": [_FakeStripeSub({"current_period_end": 1999999999})]}),
                }
            ]
        ),
    )
    st = billing.subscription_status(user_id="s")
    assert st.cancel_at_period_end is True
    assert st.current_period_end == 1999999999


def test_status_period_read_failure_is_best_effort(monkeypatch, store, cog):
    cog.groups["s"] = {"subscriber"}
    store.link_stripe_customer("s", "cus_s")

    def _boom(**kw):
        raise RuntimeError("Stripe is down")

    monkeypatch.setattr(billing.stripe.Subscription, "list", _boom)
    st = billing.subscription_status(user_id="s")
    assert st.tier == "subscriber" and st.has_access is True
    assert st.cancel_at_period_end is False and st.current_period_end is None


# ── Server-side subscriber-MFA guard ─────────────────────────────────────────


def _req(claims):
    class _R:
        def __init__(self):
            self.scope = {
                "aws.event": {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}}
            }
            self.headers = {}

    return _R()


def test_mfa_guard_noop_when_flag_off(monkeypatch):
    monkeypatch.delenv("ENFORCE_SUBSCRIBER_MFA", raising=False)
    # Even a subscriber with no MFA passes when enforcement is off.
    req = _req({"cognito:groups": "subscriber", "username": "u@x.com"})
    assert auth_router.require_subscriber_mfa(req, user_id="u") == "u"


def test_mfa_guard_passes_non_subscriber(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    req = _req({"cognito:groups": "beta_tester", "username": "u@x.com"})
    assert auth_router.require_subscriber_mfa(req, user_id="u") == "u"


def test_mfa_guard_blocks_subscriber_without_totp(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda sub: False)
    auth_router._MFA_CACHE.clear()
    req = _req({"cognito:groups": "subscriber", "username": "u@x.com"})
    with pytest.raises(HTTPException) as ei:
        auth_router.require_subscriber_mfa(req, user_id="u")
    assert ei.value.status_code == 403


def test_mfa_guard_allows_subscriber_with_totp(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda sub: True)
    auth_router._MFA_CACHE.clear()
    req = _req({"cognito:groups": "subscriber", "username": "u@x.com"})
    assert auth_router.require_subscriber_mfa(req, user_id="u") == "u"


def test_mfa_guard_fails_closed_when_cognito_errors(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")

    def _boom(sub):
        raise RuntimeError("cognito down")

    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", _boom)
    auth_router._MFA_CACHE.clear()
    req = _req({"cognito:groups": "subscriber", "username": "u@x.com"})
    with pytest.raises(HTTPException) as ei:
        auth_router.require_subscriber_mfa(req, user_id="u")
    assert ei.value.status_code == 403  # unreadable MFA status → fail closed


def test_federated_exemption_by_username_shape(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    # A pure-Google session: username is `Google_<id>` (no '@'), no TOTP → still allowed.
    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda sub: False)
    auth_router._MFA_CACHE.clear()
    req = _req({"cognito:groups": "subscriber", "username": "Google_10979331"})
    assert auth_router.require_subscriber_mfa(req, user_id="g") == "g"


def test_federated_exemption_by_amr(monkeypatch):
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda sub: False)
    auth_router._MFA_CACHE.clear()
    req = _req({"cognito:groups": "subscriber", "username": "u@x.com", "amr": '["Google"]'})
    assert auth_router.require_subscriber_mfa(req, user_id="u") == "u"


def test_identities_claim_does_NOT_exempt_password_session(monkeypatch):
    """The trap: a linked account (E9.7) carries `identities` even on its PASSWORD login.
    The guard must NOT exempt on it — a password session without TOTP must be blocked."""
    monkeypatch.setenv("ENFORCE_SUBSCRIBER_MFA", "1")
    monkeypatch.setattr(auth_router.cognito_svc, "has_software_token_mfa", lambda sub: False)
    auth_router._MFA_CACHE.clear()
    claims = {
        "cognito:groups": "subscriber",
        "username": "linked@x.com",  # native email username → password session
        "identities": '[{"providerName":"Google"}]',  # present due to linking
    }
    with pytest.raises(HTTPException) as ei:
        auth_router.require_subscriber_mfa(_req(claims), user_id="linked")
    assert ei.value.status_code == 403
