"""E9.59 — the PUBLIC pricing read: price from Stripe, slots from us.

No network / no real Stripe / no boto3: `stripe.Price.retrieve` is monkeypatched and the
Dynamo helpers are in-memory fakes. Router functions are called directly (no TestClient),
matching `test_stripe_billing.py`.

The decision under test: the number the marketing page DISPLAYS is read from the SAME
Stripe Price object Checkout CHARGES against, so the two cannot drift and a price change is
one Stripe-dashboard edit with no redeploy.

What is actually load-bearing here, in rough order:

  1. THE DISPLAYED PRICE AND THE CHARGED PRICE COME FROM ONE DECISION. Not "both look
     right on today's config" — the test drives them apart (flips the founding counter past
     the cap) and demands they move together. A test that only asserted "$10 is returned"
     would pass just as happily against two independent constants, which is the state E9.59
     removed.
  2. NOTHING IS HARDCODED. Change what Stripe returns; the response must change. This is
     the same property the E2E `transform` test asserts at the DOM, held here at the API.
  3. THE PAYLOAD IS MINIMISED. `founding_slots_used` and `founding_cap` must BOTH be absent
     — shipping the cap beside `remaining` leaks `used` as a subtraction.
  4. THE CACHE CANNOT BLANK THE PAGE, AND CANNOT SERVE A FICTION. Stale-then-durable
     fallbacks, and a 503 (never a made-up number) when no layer can answer.
  5. THE ROUTE IS GENUINELY PUBLIC AT THE APP LAYER. Which is necessary and NOT sufficient
     — the API-Gateway authorizer is what actually gates it (NF3.2), and no test can see it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.backend.routers import stripe as billing
from app.backend.services import stripe_pricing


# ── Fakes ────────────────────────────────────────────────────────────────────


class _StripeObject:
    """Fidelity fake for a `StripeObject`: supports `in` and `[...]`, and NOT `.get()`.

    The gap is the point. `.get()` on a real Stripe SDK object raises `AttributeError`, and
    that has reached production twice (E9.8 webhook, E9.57 `Subscription.list`), both times
    swallowed by a broad `except` into a plausible wrong answer. A plain-dict fixture would
    pass even after that regression was re-introduced."""

    def __init__(self, data: dict):
        self._data = data

    def __contains__(self, key):
        return key in self._data

    def __getitem__(self, key):
        value = self._data[key]
        return _StripeObject(value) if isinstance(value, dict) else value


def _price(unit_amount=1000, currency="usd", interval="month", interval_count=1, product="Credence Sports Membership"):
    return _StripeObject(
        {
            "unit_amount": unit_amount,
            "currency": currency,
            "recurring": {"interval": interval, "interval_count": interval_count},
            "product": {"name": product},
        }
    )


class _FakeDynamo:
    def __init__(self):
        self.slots = 0
        self.snapshots: dict[str, dict] = {}
        self.writes = 0
        self.read_fails = False

    def founding_slots_used(self):
        return self.slots

    def read_price_snapshot(self, price_id):
        if self.read_fails:
            return None
        return dict(self.snapshots[price_id]) if price_id in self.snapshots else None

    def write_price_snapshot(self, price_id, snapshot):
        self.writes += 1
        self.snapshots[price_id] = dict(snapshot)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_PRICE_FOUNDING", "price_founding_test")
    monkeypatch.setenv("STRIPE_PRICE_STANDARD", "price_standard_test")
    monkeypatch.setattr(billing, "_FOUNDING_CAP", 100)


@pytest.fixture
def store(monkeypatch, env):
    fake = _FakeDynamo()
    monkeypatch.setattr(billing.dynamo, "founding_slots_used", fake.founding_slots_used)
    monkeypatch.setattr(stripe_pricing.dynamo, "read_price_snapshot", fake.read_price_snapshot)
    monkeypatch.setattr(stripe_pricing.dynamo, "write_price_snapshot", fake.write_price_snapshot)
    return fake


@pytest.fixture(autouse=True)
def clean_cache():
    """The pricing cache is module-level (it must survive across warm-Lambda invocations),
    so it also survives across tests. Clear both layers around every test — a leaked entry
    would let a test pass on a neighbour's Stripe response."""
    stripe_pricing._memory.clear()
    stripe_pricing._persisted.clear()
    yield
    stripe_pricing._memory.clear()
    stripe_pricing._persisted.clear()


@pytest.fixture
def stripe_returns(monkeypatch):
    """Install a `stripe.Price.retrieve` and record what Price id it was asked for."""
    calls: list[str] = []

    def install(price_obj=None, raises=None):
        def retrieve(price_id, **_kwargs):
            calls.append(price_id)
            if raises is not None:
                raise raises
            return price_obj

        monkeypatch.setattr(stripe_pricing.stripe.Price, "retrieve", retrieve)
        return calls

    install.calls = calls
    return install


# ── 1. Display and charge are ONE decision ───────────────────────────────────


def test_the_displayed_price_id_is_the_one_checkout_would_charge(store, stripe_returns):
    """⭐ The story's core claim, asserted as an identity rather than as two coincidences.

    The public read must ask Stripe for exactly the Price id `_price_for_new_checkout()`
    hands to `checkout.Session.create`. Comparing rendered NUMBERS would not do it — two
    independent sources agreeing on today's value is precisely the pre-E9.59 state."""
    calls = stripe_returns(_price())
    billing.public_pricing()
    charged_price_id, _tier = billing._price_for_new_checkout()
    assert calls == [charged_price_id]


def test_display_and_charge_move_together_across_the_founding_boundary(store, stripe_returns):
    """Drive them apart and require them to stay together.

    Below the cap both must be the founding Price; at the cap both must flip to standard in
    the same step. This is the test a second display constant fails: a hardcoded $10 would
    keep displaying $10 while checkout silently moved to the standard Price."""
    calls = stripe_returns(_price())

    store.slots = 99
    billing.public_pricing()
    assert calls[-1] == "price_founding_test"
    assert billing._price_for_new_checkout()[0] == "price_founding_test"

    stripe_pricing._memory.clear()  # the flip is a different Price id, not a cache question
    store.slots = 100
    billing.public_pricing()
    assert calls[-1] == "price_standard_test"
    assert billing._price_for_new_checkout()[0] == "price_standard_test"


def test_the_authenticated_read_uses_the_same_stripe_price(store, stripe_returns):
    """`/subscribe` renders a logged-out branch and a signed-in branch. If only the public
    one were moved to Stripe, ONE page would show two different prices to two visitors."""
    stripe_returns(_price(unit_amount=1799))
    assert billing.public_pricing().unit_amount == 1799
    assert billing.subscription_pricing(_="anyone").unit_amount == 1799


# ── 2. Nothing is hardcoded ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "amount,currency,interval,product",
    [
        (1000, "usd", "month", "Credence Sports Membership"),
        (4700, "eur", "year", "Credence Pro"),
        (999, "gbp", "week", "Anything At All"),
    ],
)
def test_every_displayed_field_comes_from_stripe(store, stripe_returns, amount, currency, interval, product):
    """The response must be a function of Stripe's answer, not of anything in this repo.
    Parametrised across values no constant in the codebase could coincidentally match."""
    stripe_returns(_price(unit_amount=amount, currency=currency, interval=interval, product=product))
    out = billing.public_pricing()
    assert (out.unit_amount, out.currency, out.interval, out.product_name) == (
        amount,
        currency,
        interval,
        product,
    )


def test_a_stripe_object_is_read_without_dot_get(store, stripe_returns):
    """Regression guard for the twice-shipped `.get()` bug. The fake refuses `.get()` exactly
    as the SDK object does, so a reader that reaches for it raises here instead of in prod."""
    stripe_returns(_price())
    assert billing.public_pricing().unit_amount == 1000


def test_the_fake_stripe_object_does_not_support_dot_get():
    """Fidelity check on the fake itself — a plain dict would make the test above vacuous."""
    obj = _price()
    with pytest.raises(AttributeError):
        obj.get("unit_amount")
    assert obj["unit_amount"] == 1000
    assert "unit_amount" in obj


# ── 3. The payload is minimised ──────────────────────────────────────────────


def test_the_public_payload_carries_no_internal_counts(store, stripe_returns):
    """`used` and `cap` must BOTH be absent. Shipping the cap beside `remaining` would leak
    the conversion count as a one-line subtraction — the leak this endpoint exists to avoid,
    arriving through the back door."""
    stripe_returns(_price())
    store.slots = 63
    payload = billing.public_pricing().model_dump()
    assert "founding_slots_used" not in payload
    assert "founding_cap" not in payload
    assert payload["founding_slots_remaining"] == 37


def test_remaining_is_clamped_at_zero_past_the_cap(store, stripe_returns):
    """The #100 boundary race is accepted (no lock), so `used` can exceed the cap. A negative
    'seats left' would be rendered verbatim by the page."""
    stripe_returns(_price())
    store.slots = 104
    assert billing.public_pricing().founding_slots_remaining == 0


def test_the_authenticated_payload_keeps_its_existing_keys(store, stripe_returns):
    """E9.41 / NF-C0 — the deployed client reads these. Only the SOURCE of the amount moved;
    removing or renaming a key here is a silent blank screen on the un-redeployed frontend."""
    stripe_returns(_price())
    payload = billing.subscription_pricing(_="anyone").model_dump()
    assert set(payload) == {
        "tier",
        "unit_amount",
        "currency",
        "founding_slots_used",
        "founding_cap",
        "founding_available",
    }


# ── 4. The cache cannot blank the page, and cannot serve a fiction ───────────


def test_the_price_is_cached_rather_than_fetched_per_pageview(store, stripe_returns):
    """This endpoint is the top of the funnel — every anonymous visitor and crawler hits it.
    A Stripe call per pageview is a latency tax on the page that has to convert."""
    calls = stripe_returns(_price())
    for _ in range(5):
        billing.public_pricing()
    assert len(calls) == 1


def test_a_stripe_outage_serves_the_last_price_from_memory(store, stripe_returns, monkeypatch):
    """A blip must not blank the price. Warm container: the in-memory entry answers."""
    stripe_returns(_price(unit_amount=1000))
    assert billing.public_pricing().unit_amount == 1000

    monkeypatch.setattr(stripe_pricing, "_TTL_SECONDS", 0)  # force a refresh attempt
    stripe_returns(raises=RuntimeError("stripe down"))
    assert billing.public_pricing().unit_amount == 1000


def test_a_cold_container_during_a_stripe_outage_serves_the_durable_snapshot(store, stripe_returns):
    """⭐ The layer an in-memory cache alone cannot provide, and the reason the Dynamo row
    exists. A Lambda cold start during a Stripe outage has NO memory — which is exactly when
    the fallback matters, and exactly what a same-process test would miss if the memory
    cache were not cleared to simulate it."""
    stripe_returns(_price(unit_amount=1000))
    billing.public_pricing()
    assert store.snapshots  # the successful read persisted a last-known-good

    stripe_pricing._memory.clear()  # cold container
    stripe_returns(raises=RuntimeError("stripe down"))
    assert billing.public_pricing().unit_amount == 1000


def test_no_cache_and_no_stripe_is_a_503_not_a_made_up_price(store, stripe_returns):
    """⛔ It must NOT fall back to a constant. A wrong price is worse than a missing one, and
    a hardcoded fallback would re-create the second source of truth E9.59 deleted. The page
    degrades to perks + CTA (asserted in the E2E suite); it never invents a number."""
    stripe_returns(raises=RuntimeError("stripe down"))
    store.read_fails = True
    with pytest.raises(HTTPException) as exc:
        billing.public_pricing()
    assert exc.value.status_code == 503


def test_a_tiered_price_is_refused_rather_than_rendered_as_null(store, stripe_returns):
    """A metered/tiered Stripe Price has `unit_amount=None`. Rendering that as a number would
    be a fabrication, so it is treated as a failed read (→ fallback, or 503)."""
    stripe_returns(_StripeObject({"unit_amount": None, "currency": "usd", "recurring": {"interval": "month"}}))
    store.read_fails = True
    with pytest.raises(HTTPException) as exc:
        billing.public_pricing()
    assert exc.value.status_code == 503


def test_an_unchanged_price_is_not_rewritten_to_dynamo_every_refresh(store, stripe_returns, monkeypatch):
    """The durable snapshot is a fallback, not a log."""
    monkeypatch.setattr(stripe_pricing, "_TTL_SECONDS", 0)
    stripe_returns(_price())
    for _ in range(4):
        billing.public_pricing()
    assert store.writes == 1


def test_a_failed_snapshot_write_does_not_fail_the_request(store, stripe_returns, monkeypatch):
    """Caching is best-effort. Failing to CACHE a price must never fail the request that
    successfully READ it."""
    def boom(*_a, **_k):
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(stripe_pricing.dynamo, "write_price_snapshot", boom)
    stripe_returns(_price(unit_amount=1500))
    assert billing.public_pricing().unit_amount == 1500


def test_invalidate_sends_the_next_read_back_to_stripe(store, stripe_returns):
    """The webhook hook: a dashboard price edit shows up on the next pageview rather than up
    to one TTL later."""
    calls = stripe_returns(_price())
    billing.public_pricing()
    assert len(calls) == 1

    stripe_pricing.invalidate()
    billing.public_pricing()
    assert len(calls) == 2


def test_invalidate_keeps_the_durable_fallback(store, stripe_returns):
    """`invalidate()` must drop the MEMORY cache and KEEP the durable snapshot. A "clear
    everything" implementation converts a routine price edit into a blank pricing page.

    ⚠️ THE ORDERING HERE IS THE TEST, and getting it wrong made an earlier version of this
    guard unfalsifiable. Damaging the durable row is invisible if any SUCCESSFUL read happens
    afterwards, because that read re-persists it — the defect self-heals before you look. The
    harmful sequence is the one below and only this one: invalidate → Stripe unreachable →
    cold container, with no successful read in between. That is also the realistic one: a
    price edit is exactly when a webhook fires, so an outage in that window is the case the
    durable layer exists for. (An earlier form asserted `store.snapshots` was non-empty; a
    deliberately-broken `invalidate()` left it non-empty and CORRUPT, and the guard stayed
    green.)"""
    stripe_returns(_price(unit_amount=1000))
    billing.public_pricing()

    stripe_pricing.invalidate()
    stripe_pricing._memory.clear()  # cold container
    stripe_returns(raises=RuntimeError("stripe down"))
    assert billing.public_pricing().unit_amount == 1000, "invalidate() destroyed the fallback"


# ── 5. Public at the app layer (necessary, NOT sufficient) ───────────────────


def test_the_public_route_takes_no_credentials(store, stripe_returns):
    """Callable with no arguments and no request — it cannot branch on a caller.

    ⚠️ This matters more than "it has no auth dependency". An `--authorization-type NONE`
    gateway route gets NO upstream token validation, so a Bearer token on it is
    attacker-controlled (measured 2026-08-04: a forged unsigned JWT claiming admin returns
    200 on the existing NONE route). A public read must therefore never look at one."""
    stripe_returns(_price())
    assert billing.public_pricing().unit_amount == 1000


def test_the_public_router_carries_exactly_one_route_and_no_auth():
    """The exemption is structural — a separate router object, not a flag inside the gated
    one (the fantasy_import / fantasy_public pattern). One route, so the surface a gateway
    exemption opens is the surface that was reviewed."""
    routes = [r for r in billing.public_router.routes]
    assert len(routes) == 1
    assert routes[0].path == "/subscription/public-pricing"
    assert billing.public_router.dependencies == []


def test_the_public_router_is_mounted():
    """A router that is never included is a 404 that looks like an authorizer problem."""
    from app.backend.main import app

    assert any(getattr(r, "path", None) == "/subscription/public-pricing" for r in app.routes)


def test_no_display_price_constant_survives_in_the_router():
    """⛔ The hardcoded-display source is GONE, not merely unused. A leftover
    `FOUNDING_PRICE_CENTS` is an invitation for the next reader to wire it back in, and it
    would drift from Stripe silently the moment anyone did."""
    source = Path(billing.__file__).read_text()
    body = "\n".join(l for l in source.splitlines() if not l.strip().startswith("#"))
    for banned in ("FOUNDING_PRICE_CENTS", "STANDARD_PRICE_CENTS", "_FOUNDING_CENTS", "_STANDARD_CENTS"):
        assert banned not in body, f"{banned} is still a display-price source in stripe.py"


# ── The E2E fixture's shape is pinned to the model, not hand-maintained ──────


def test_the_e2e_fixture_matches_the_response_model_exactly():
    """⭐ `frontend/e2e/README.md` forbids hand-written fixtures, because one encodes the
    assumption under test. E9.59's public-pricing fixture has to be synthetic (the route is
    not live in prod, so it cannot be captured) — so the rule is enforced from this side
    instead: the fixture's key set must EQUAL `PublicPricing`'s fields. A backend that adds,
    removes or renames a field fails here, which is what stops the fixture from quietly
    describing a payload the server no longer sends.

    Note `==`, not `<=`: a MISSING key matters as much as an extra one. A fixture short a
    field lets the E2E suite pass against a payload the real page would render incomplete."""
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "frontend/e2e/fixtures/api/subscription-public-pricing.synthetic.json"
    )
    fixture = json.loads(fixture_path.read_text())
    keys = {k for k in fixture if not k.startswith("__")}
    assert keys == set(billing.PublicPricing.model_fields), (
        "the E2E public-pricing fixture has drifted from PublicPricing — update "
        f"{fixture_path.name} (or capture it for real, now that the route is live)"
    )


def test_the_e2e_fixture_amount_is_not_a_real_price():
    """The fixture's $12.34 is load-bearing: a page that hardcodes $10 or $20 would still
    render a plausible number against a realistic fixture, and the E2E `transform` test that
    exists to catch exactly that would pass."""
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "frontend/e2e/fixtures/api/subscription-public-pricing.synthetic.json"
    )
    assert json.loads(fixture_path.read_text())["unit_amount"] not in (1000, 2000)
