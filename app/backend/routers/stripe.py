"""Stripe subscription billing (E9.8 / master Story A0.7).

Endpoints
  POST /stripe/create-checkout-session — auth. Server-side founding-price gate
      selects the $10 (first 100 conversions) or $20 Price, then opens a Stripe
      Checkout Session. Beta/subscriber/admin callers are refused (they already
      have access — beta users must never see checkout).
  POST /stripe/create-portal-session — auth. Stripe billing portal for the caller
      to manage / cancel their subscription (cancel → webhook → access revoked).
  POST /stripe/webhook — Stripe-signed. Verifies the signature, is idempotent on
      the event id, and moves the user between Cognito groups:
        customer.subscription.created  → add `subscriber`, drop `beta_tester`/`churned`
                                         (+ count the conversion, exactly once)
        customer.subscription.deleted  → drop `subscriber`, add `churned`
        invoice.payment_failed         → drop `subscriber`, add `churned`
  GET  /subscription/status — auth. The caller's tier / access, from Cognito.
  GET  /subscription/pricing — auth. The Price a NEW checkout would use right now.
  GET  /subscription/public-pricing — PUBLIC (E9.59). The same price, minimised, for the
      logged-out pricing page. On `public_router`, which carries no auth dependency.

Two-phase rollout: everything runs in Stripe TEST mode until the operator flips
the live keys + live webhook secret and gives the go (Phase 2). No changelog entry
until that flip. See story_prompts.md → E9.8.

⚠️ The /stripe/webhook route MUST be exposed WITHOUT the API Gateway Cognito JWT
authorizer (Stripe presents no Cognito token) — signature verification is its auth.
The same is true of /subscription/public-pricing, for the ordinary NF3.2 reason: the
authorizer sits per-route in front of the Lambda, so a router with no `Depends()` still
401s until an explicit `--authorization-type NONE` route exists. See
infrastructure/aws_resources.md.
"""

from __future__ import annotations

import json
import logging
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.backend.dependencies import get_user_id
from app.backend.services import cognito, dynamo, stripe_pricing

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscription"])

# E9.59 — the ONE public route in this module, kept on its own router object rather than
# as an exemption flag inside the gated one (the fantasy_import / fantasy_public pattern).
public_router = APIRouter(tags=["subscription-public"])

# ── Config (all operator-provisioned; secrets never live in the repo) ────────
_FOUNDING_CAP = int(os.getenv("FOUNDING_MEMBER_CAP", "100"))
_APP_BASE_URL = os.getenv("APP_BASE_URL", "https://credencesports.com").rstrip("/")
# ⛔ There is deliberately NO `FOUNDING_PRICE_CENTS` display constant any more (E9.59).
# It was a SECOND source of truth for the number a customer sees, maintained by hand and
# with nothing tying it to the Stripe Price they are actually charged. Both pricing reads
# below now go through `stripe_pricing.resolve()` on the SAME Price id checkout uses.

# Groups that already have full access → must never be sent to checkout.
_ACCESS_GROUPS = {cognito.GROUP_BETA, cognito.GROUP_SUBSCRIBER, "admin"}


def _secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Billing is not configured")
    return key


def _configure_stripe() -> None:
    stripe.api_key = _secret_key()


def _pricing_decision() -> tuple[str, str, int]:
    """(price_id, tier, founding_slots_used) — the ONE place the offered Price is chosen.

    Decided from the authoritative founding counter: under the cap → the founding Price
    (grandfathered for life); at/over → the standard Price. The #100 boundary race is
    accepted (no lock).

    ⭐ E9.59: checkout AND both pricing reads call this, so the Price the page DISPLAYS is
    by construction the Price checkout CHARGES. A separate display path is precisely how
    the two drift. The `STRIPE_PRICE_*` env vars are also the TEST→LIVE seam (E9.8-P2):
    Stripe Price ids differ by mode, and pointing this one function at the live ids moves
    display and charge together."""
    founding = os.getenv("STRIPE_PRICE_FOUNDING")
    standard = os.getenv("STRIPE_PRICE_STANDARD")
    if not founding or not standard:
        raise HTTPException(status_code=503, detail="Billing prices are not configured")
    used = dynamo.founding_slots_used()
    if used < _FOUNDING_CAP:
        return founding, "founding", used
    return standard, "standard", used


def _price_for_new_checkout() -> tuple[str, str]:
    """(price_id, tier) for a new checkout."""
    price_id, tier, _used = _pricing_decision()
    return price_id, tier


def _displayed_price(price_id: str) -> stripe_pricing.PriceSnapshot:
    """The Stripe Price to show, or a 503. See `services/stripe_pricing.py` for the cache
    + last-known-good chain — reaching the 503 means Stripe is unreachable AND this Price
    has never once been read successfully, which is the only state where showing nothing
    beats showing something."""
    _configure_stripe()
    snapshot = stripe_pricing.resolve(price_id)
    if snapshot is None:
        raise HTTPException(status_code=503, detail="Pricing is temporarily unavailable")
    return snapshot


# ── Response models ──────────────────────────────────────────────────────────


class CheckoutSession(BaseModel):
    url: str


class PortalSession(BaseModel):
    url: str


class SubscriptionStatus(BaseModel):
    tier: str          # admin | subscriber | beta_tester | churned | free
    has_access: bool   # admin | subscriber | beta_tester
    is_beta: bool
    has_billing: bool  # a Stripe customer exists → can open the billing portal
    # Cancel-at-period-end visibility (E9.57 finding): Stripe's Customer Portal default
    # cancel action does NOT delete the subscription immediately — it schedules a future
    # cancellation (via `cancel_at_period_end` OR the separate `cancel_at` timestamp field,
    # depending on billing mode — see `_active_subscription_period`) and only fires
    # `customer.subscription.deleted` (our demote trigger) once that date actually arrives.
    # So a canceled `subscriber` correctly keeps `tier="subscriber"`/`has_access=True` for the
    # rest of what they paid for; these two fields are what let the UI say so honestly instead
    # of looking unchanged. `cancel_at_period_end` here means "is a cancellation scheduled" (by
    # either mechanism); `current_period_end` here means "access ends at" (may be `cancel_at`,
    # not necessarily the literal period boundary). Best-effort (False/None if there's no
    # billing, nothing scheduled, or the read fails) — never blocks subscription/status.
    cancel_at_period_end: bool = False
    current_period_end: int | None = None  # unix seconds, when set


class SubscriptionPricing(BaseModel):
    """The AUTHENTICATED pricing read. Shape unchanged (E9.41/NF-C0 — a deployed client
    reads these keys); only the SOURCE of `unit_amount`/`currency` moved to Stripe."""

    tier: str             # founding | standard
    unit_amount: int      # cents, from the Stripe Price
    currency: str         # from the Stripe Price
    founding_slots_used: int
    founding_cap: int
    founding_available: bool


class PublicPricing(BaseModel):
    """The PUBLIC pricing read — what a logged-out stranger is shown.

    Deliberately MINIMISED. It carries the Stripe Price fields a page must render, plus
    ONE number of ours, and nothing else.

    ⛔ `founding_slots_used` and `founding_cap` are BOTH absent, and that is not an
    oversight: shipping the cap alongside `remaining` would make `used` a subtraction
    away, i.e. it would leak the internal conversion count through the back door. The
    marketing claim a page can make from `founding_slots_remaining` alone ("N founding
    seats left at this price") is the one worth making anyway."""

    unit_amount: int          # cents, from the Stripe Price
    currency: str             # from the Stripe Price
    interval: str             # from the Stripe Price ("month")
    interval_count: int       # from the Stripe Price
    product_name: str         # from the Stripe Product
    tier: str                 # founding | standard — which offer is live right now
    founding_slots_remaining: int  # OURS (a Credence count), never a Stripe capped price


def _active_subscription_period(customer_id: str) -> tuple[bool, int | None]:
    """(is_scheduled_to_cancel, access_ends_at) for the customer's subscription.

    ⚠️ `stripe.Subscription.list(...)` returns real `StripeObject` instances, NOT plain
    dicts — they support `in` / `[...]` (via `__contains__`/`__getitem__`) but do NOT
    define a `.get()` method, so `sub.get(...)` raises `AttributeError: get` (confirmed
    live in prod, 2026-08-05 — the exact class of bug already documented for the
    webhook's `construct_event` result, hitting a different Stripe SDK call this time).
    The broad except below SWALLOWED that error and silently returned the "nothing
    scheduled" defaults, which is indistinguishable from a genuinely uncanceled
    subscription. Use `in`/`[...]`, never `.get()`, on a Stripe SDK object.

    ⚠️ A SECOND live-prod trap, found the same day right after the first fix shipped:
    `cancel_at_period_end` (bool) is NOT the only way Stripe represents "will cancel at
    the end of this paid period" — `cancel_at` (nullable int, "a date in the future at
    which the subscription will automatically get canceled") is a genuinely separate
    field, and a subscription on **Flexible billing mode** (Stripe's 2025-03-31 API
    migration) canceled via the Customer Portal came back with `cancel_at_period_end=
    False` while `cancel_at` held the real scheduled-cancellation timestamp — confirmed
    against the Stripe dashboard showing "Active — Cancels <date>" for a subscription
    our fixed code STILL reported as not-scheduled-to-cancel. So both fields must be
    checked; `cancel_at`, when present, is also the more precise "access ends at" value
    to show (it need not coincide with `current_period_end` in general — Stripe allows
    scheduling a cancellation for any future date, not only the period boundary).
    `current_period_end` also moved OFF the top-level Subscription object onto each
    subscription item as of API version 2025-03-31 — read the first item's value as a
    fallback so this works regardless of which API version this Stripe account defaults
    to, used only when neither `cancel_at` nor a scheduled `cancel_at_period_end` cancel
    date is what's needed (i.e. never reached once `cancel_at` is present).

    Best-effort — a Stripe hiccup or a customer with no subscription object (e.g. a
    pre-conversion row) must never break GET /subscription/status, so any failure
    still just returns the "nothing scheduled" defaults."""
    try:
        _configure_stripe()
        subs = stripe.Subscription.list(customer=customer_id, status="all", limit=1)
        if not subs.data:
            return False, None
        sub = subs.data[0]
        cancel_at_period_end_flag = bool(sub["cancel_at_period_end"]) if "cancel_at_period_end" in sub else False
        cancel_at = sub["cancel_at"] if ("cancel_at" in sub and sub["cancel_at"] is not None) else None
        if not (cancel_at_period_end_flag or cancel_at is not None):
            return False, None
        if cancel_at is not None:
            return True, cancel_at
        if "current_period_end" in sub:
            return True, sub["current_period_end"]
        items = sub["items"]["data"] if "items" in sub and sub["items"] else []
        current_period_end = (
            items[0]["current_period_end"]
            if items and "current_period_end" in items[0]
            else None
        )
        return True, current_period_end
    except Exception:  # noqa: BLE001
        logger.exception("Could not read subscription period for customer=%s", customer_id)
        return False, None


def _tier(groups: list[str]) -> str:
    if "admin" in groups:
        return "admin"
    if cognito.GROUP_SUBSCRIBER in groups:
        return "subscriber"
    if cognito.GROUP_BETA in groups:
        return "beta_tester"
    if cognito.GROUP_CHURNED in groups:
        return "churned"
    return "free"


# ── Checkout + portal (authenticated) ────────────────────────────────────────


@router.post("/stripe/create-checkout-session", response_model=CheckoutSession)
def create_checkout_session(request: Request, user_id: str = Depends(get_user_id)) -> CheckoutSession:
    """Open a Stripe Checkout Session for the caller, at the server-decided price.

    Refuses callers who already have access (beta_tester / subscriber / admin) so a
    beta user can never be charged. The Cognito `sub` is stamped on both the session
    (client_reference_id) and the subscription metadata so the webhook can map the
    conversion back to the user."""
    groups = cognito.groups_for_user(user_id)
    if _ACCESS_GROUPS.intersection(groups):
        raise HTTPException(status_code=409, detail="You already have full access.")

    _configure_stripe()
    price_id, _tier_name = _price_for_new_checkout()

    kwargs = dict(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=user_id,
        subscription_data={"metadata": {"cognito_sub": user_id}},
        metadata={"cognito_sub": user_id},
        success_url=f"{_APP_BASE_URL}/subscribe/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{_APP_BASE_URL}/subscribe",
        allow_promotion_codes=True,
    )
    # Reuse an existing Stripe customer if this user has churned-and-returned.
    existing_customer = dynamo.stripe_customer_for_user(user_id)
    if existing_customer:
        kwargs["customer"] = existing_customer

    try:
        session = stripe.checkout.Session.create(**kwargs)
    except Exception as exc:  # noqa: BLE001 — surface any Stripe error as a 502
        logger.exception("stripe checkout.Session.create failed (sub=%s)", user_id)
        raise HTTPException(status_code=502, detail="Could not start checkout") from exc

    if not session.url:
        raise HTTPException(status_code=502, detail="Checkout session had no URL")
    return CheckoutSession(url=session.url)


@router.post("/stripe/create-portal-session", response_model=PortalSession)
def create_portal_session(user_id: str = Depends(get_user_id)) -> PortalSession:
    """Open the Stripe billing portal so the caller can manage / cancel billing."""
    customer_id = dynamo.stripe_customer_for_user(user_id)
    if not customer_id:
        raise HTTPException(status_code=404, detail="No billing account found")

    _configure_stripe()
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{_APP_BASE_URL}/settings",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("stripe billing_portal.Session.create failed (sub=%s)", user_id)
        raise HTTPException(status_code=502, detail="Could not open billing portal") from exc

    return PortalSession(url=session.url)


# ── Status + pricing (authenticated) ─────────────────────────────────────────


@router.get("/subscription/status", response_model=SubscriptionStatus)
def subscription_status(user_id: str = Depends(get_user_id)) -> SubscriptionStatus:
    """The caller's access tier — read authoritatively from Cognito groups so a
    just-converted user sees `subscriber` immediately (before their next token
    refresh reflects the group change in the JWT claims)."""
    groups = cognito.groups_for_user(user_id)
    tier = _tier(groups)
    customer_id = dynamo.stripe_customer_for_user(user_id)
    cancel_at_period_end, current_period_end = (
        _active_subscription_period(customer_id) if (tier == "subscriber" and customer_id) else (False, None)
    )
    return SubscriptionStatus(
        tier=tier,
        has_access=tier in {"admin", "subscriber", "beta_tester"},
        is_beta=tier == "beta_tester",
        has_billing=customer_id is not None,
        cancel_at_period_end=cancel_at_period_end,
        current_period_end=current_period_end,
    )


@router.get("/subscription/pricing", response_model=SubscriptionPricing)
def subscription_pricing(_: str = Depends(get_user_id)) -> SubscriptionPricing:
    """The price a NEW checkout would use right now (founding vs standard).

    E9.59 — the amount now comes from the Stripe Price rather than an env constant. That
    matters here and not only on the public read: `/subscribe` renders BOTH branches, so
    leaving this one on a hardcoded constant would have made one page show two different
    prices to a logged-out and a signed-in visitor."""
    price_id, tier, used = _pricing_decision()
    snapshot = _displayed_price(price_id)
    return SubscriptionPricing(
        tier=tier,
        unit_amount=snapshot.unit_amount,
        currency=snapshot.currency,
        founding_slots_used=used,
        founding_cap=_FOUNDING_CAP,
        founding_available=tier == "founding",
    )


# ── Public pricing (E9.59 — NO auth; see the API-Gateway note in the module docstring) ──


@public_router.get("/subscription/public-pricing", response_model=PublicPricing)
def public_pricing() -> PublicPricing:
    """The price a logged-out stranger is shown, read from Stripe.

    Takes NO credentials and returns nothing caller-specific — which is what makes it safe
    on an `--authorization-type NONE` route. ⚠️ Such a route gets no upstream token
    validation, so any Bearer token on it is attacker-controlled (measured, 2026-08-04); a
    public read must therefore never branch on one, and this one has no `Depends()` and
    reads no header at all.

    "Price from Stripe, slots from us": the amount/currency/interval/product come from the
    Stripe Price object that Checkout charges against; `founding_slots_remaining` is OUR
    durable conversion counter. The founding tier is deliberately NOT modelled as a Stripe
    metered/capped price — the cap is a Credence marketing promise, and expressing it in
    Stripe would put a business rule in a place we cannot count or grandfather from."""
    price_id, tier, used = _pricing_decision()
    snapshot = _displayed_price(price_id)
    return PublicPricing(
        unit_amount=snapshot.unit_amount,
        currency=snapshot.currency,
        interval=snapshot.interval,
        interval_count=snapshot.interval_count,
        product_name=snapshot.product_name,
        tier=tier,
        # Clamped: the #100 boundary race is accepted, so `used` can exceed the cap and a
        # negative "seats left" would be a nonsense the page would render verbatim.
        founding_slots_remaining=max(0, _FOUNDING_CAP - used),
    )


# ── Webhook (Stripe-signed, unauthenticated) ─────────────────────────────────


def _resolve_sub(obj: dict) -> str | None:
    """Map a Stripe event object back to a Cognito sub.

    Priority: subscription/session metadata → session client_reference_id →
    the customer→sub reverse-lookup row (used by invoice.payment_failed, whose
    object carries only a customer id)."""
    meta = obj.get("metadata") or {}
    if meta.get("cognito_sub"):
        return meta["cognito_sub"]
    if obj.get("client_reference_id"):
        return obj["client_reference_id"]
    customer = obj.get("customer")
    if customer:
        return dynamo.user_id_for_stripe_customer(str(customer))
    return None


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> dict:
    """Verify the Stripe signature, then apply the group change idempotently.

    Group add/remove is naturally idempotent, so it runs on every delivery
    (including Stripe retries + duplicates) — that guarantees a promote/demote
    eventually lands. The one non-idempotent side effect, the founding-counter
    increment, is gated exactly-once on the event id."""
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET unset — cannot verify webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.SignatureVerificationError) as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid signature") from exc

    # Handle off the raw JSON (plain dicts) — construct_event returns a StripeObject
    # whose fields are NOT plain-dict, so `.get()` raises AttributeError on it. The
    # signature is already verified above, so json.loads(payload) is authentic.
    event = json.loads(payload)
    event_id = event["id"]
    event_type = event["type"]
    obj = event["data"]["object"]

    try:
        if event_type == "checkout.session.completed":
            sub = _resolve_sub(obj)
            customer = obj.get("customer")
            if sub and customer:
                dynamo.link_stripe_customer(sub, str(customer))
            if sub:
                cognito.promote_to_subscriber(sub)

        elif event_type == "customer.subscription.created":
            sub = _resolve_sub(obj)
            customer = obj.get("customer")
            if sub and customer:
                dynamo.link_stripe_customer(sub, str(customer))
            if sub:
                cognito.promote_to_subscriber(sub)
                # Count the conversion exactly once (idempotent on the event id).
                if not dynamo.stripe_event_already_processed(event_id):
                    total = dynamo.increment_founding_slots()
                    logger.info("Founding conversion #%s (sub=%s)", total, sub)
            else:
                logger.warning(
                    "subscription.created could not resolve a Cognito sub (event=%s)", event_id
                )

        elif event_type in ("price.updated", "price.created", "product.updated"):
            # E9.59 — an operator edited the price in the Stripe dashboard. Dropping the
            # in-memory cache makes the change visible on the NEXT pageview instead of up
            # to one TTL later. Optional: these event types only arrive if they are
            # subscribed on the endpoint in the Stripe dashboard, and the TTL bounds
            # staleness either way, so this is a nicety and never load-bearing.
            stripe_pricing.invalidate()
            logger.info("Pricing cache invalidated by %s (event=%s)", event_type, event_id)

        elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
            sub = _resolve_sub(obj)
            if sub:
                cognito.demote_to_churned(sub)
                logger.info("Revoked access for sub=%s (%s)", sub, event_type)
            else:
                logger.warning(
                    "%s could not resolve a Cognito sub (event=%s)", event_type, event_id
                )
    except Exception:  # noqa: BLE001
        # Ack with 200 so Stripe doesn't hammer retries on a transient Cognito/Dynamo
        # blip; group ops are idempotent so the next delivery reconciles. Log LOUD.
        logger.exception("Stripe webhook handler failed (event=%s type=%s)", event_id, event_type)

    return {"status": "ok"}
