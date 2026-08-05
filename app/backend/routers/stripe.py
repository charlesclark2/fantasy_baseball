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

Two-phase rollout: everything runs in Stripe TEST mode until the operator flips
the live keys + live webhook secret and gives the go (Phase 2). No changelog entry
until that flip. See story_prompts.md → E9.8.

⚠️ The /stripe/webhook route MUST be exposed WITHOUT the API Gateway Cognito JWT
authorizer (Stripe presents no Cognito token) — signature verification is its auth.
"""

from __future__ import annotations

import json
import logging
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.backend.dependencies import get_user_id
from app.backend.services import cognito, dynamo

logger = logging.getLogger(__name__)
router = APIRouter(tags=["subscription"])

# ── Config (all operator-provisioned; secrets never live in the repo) ────────
_FOUNDING_CAP = int(os.getenv("FOUNDING_MEMBER_CAP", "100"))
# Display amounts (cents) for the /subscribe page — cosmetic; the Stripe Price ids
# are the billing source of truth. Defaults match the decided v1 pricing.
_FOUNDING_CENTS = int(os.getenv("FOUNDING_PRICE_CENTS", "1000"))   # $10/mo
_STANDARD_CENTS = int(os.getenv("STANDARD_PRICE_CENTS", "2000"))   # $20/mo
_APP_BASE_URL = os.getenv("APP_BASE_URL", "https://credencesports.com").rstrip("/")

# Groups that already have full access → must never be sent to checkout.
_ACCESS_GROUPS = {cognito.GROUP_BETA, cognito.GROUP_SUBSCRIBER, "admin"}


def _secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Billing is not configured")
    return key


def _configure_stripe() -> None:
    stripe.api_key = _secret_key()


def _price_for_new_checkout() -> tuple[str, str]:
    """(price_id, tier) for a new checkout, decided from the authoritative founding
    counter. Under the cap → founding ($10, grandfathered); at/over → standard ($20).
    The #100 boundary race is accepted (no lock)."""
    founding = os.getenv("STRIPE_PRICE_FOUNDING")
    standard = os.getenv("STRIPE_PRICE_STANDARD")
    if not founding or not standard:
        raise HTTPException(status_code=503, detail="Billing prices are not configured")
    if dynamo.founding_slots_used() < _FOUNDING_CAP:
        return founding, "founding"
    return standard, "standard"


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
    # cancel action does NOT delete the subscription immediately — it flips
    # `cancel_at_period_end` and only fires `customer.subscription.deleted` (our demote
    # trigger) once the paid period actually ends. So a canceled `subscriber` correctly
    # keeps `tier="subscriber"`/`has_access=True` for the rest of what they paid for; these
    # two fields are what let the UI say so honestly instead of looking unchanged. Best-effort
    # (None if there's no billing, or if the read fails) — never blocks subscription/status.
    cancel_at_period_end: bool = False
    current_period_end: int | None = None  # unix seconds, when set


class SubscriptionPricing(BaseModel):
    tier: str             # founding | standard
    unit_amount: int      # cents
    currency: str
    founding_slots_used: int
    founding_cap: int
    founding_available: bool


def _active_subscription_period(customer_id: str) -> tuple[bool, int | None]:
    """(cancel_at_period_end, current_period_end) for the customer's subscription.

    ⚠️ `stripe.Subscription.list(...)` returns real `StripeObject` instances, NOT plain
    dicts — they support `in` / `[...]` (via `__contains__`/`__getitem__`) but do NOT
    define a `.get()` method, so `sub.get(...)` raises `AttributeError: get` (confirmed
    live in prod, 2026-08-05 — the exact class of bug already documented for the
    webhook's `construct_event` result, hitting a different Stripe SDK call this time).
    The broad except below SWALLOWED that error and silently returned the "nothing
    scheduled" defaults, which is indistinguishable from a genuinely uncanceled
    subscription — caught only by checking the Stripe dashboard directly against a
    subscription confirmed scheduled to cancel. Use `in`/`[...]`, never `.get()`, on a
    Stripe SDK object. `current_period_end` also moved OFF the top-level Subscription
    object onto each subscription item as of Stripe API version 2025-03-31 (Stripe's
    multi-item-billing migration) — read the first item's value as a fallback so this
    works regardless of which API version this Stripe account defaults to.

    Best-effort — a Stripe hiccup or a customer with no subscription object (e.g. a
    pre-conversion row) must never break GET /subscription/status, so any failure
    still just returns the "nothing scheduled" defaults."""
    try:
        _configure_stripe()
        subs = stripe.Subscription.list(customer=customer_id, status="all", limit=1)
        if not subs.data:
            return False, None
        sub = subs.data[0]
        cancel_at_period_end = bool(sub["cancel_at_period_end"]) if "cancel_at_period_end" in sub else False
        if "current_period_end" in sub:
            current_period_end = sub["current_period_end"]
        else:
            items = sub["items"]["data"] if "items" in sub and sub["items"] else []
            current_period_end = (
                items[0]["current_period_end"]
                if items and "current_period_end" in items[0]
                else None
            )
        return cancel_at_period_end, current_period_end
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
    """The price a NEW checkout would use right now (founding vs standard)."""
    used = dynamo.founding_slots_used()
    available = used < _FOUNDING_CAP
    return SubscriptionPricing(
        tier="founding" if available else "standard",
        unit_amount=_FOUNDING_CENTS if available else _STANDARD_CENTS,
        currency="usd",
        founding_slots_used=used,
        founding_cap=_FOUNDING_CAP,
        founding_available=available,
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
