"""E9.59 — the DISPLAYED price, read from Stripe, cached, with a last-known-good fallback.

⭐ THE DECISION THIS MODULE EXISTS TO ENFORCE. Stripe is the single billing control
plane: the number the marketing page shows must be read from the SAME Stripe Price
object Checkout charges against, so display and charge cannot drift and a price change
is one Stripe-dashboard edit with no redeploy. Before this, `/subscription/pricing`
rendered `FOUNDING_PRICE_CENTS` — an env constant maintained by hand, in a second place,
with nothing keeping it equal to the Price the customer is actually billed at.

It also de-risks the TEST→LIVE flip (E9.8-P2): Stripe Price IDs differ by mode, so
sourcing display AND charge from the same mode-scoped `STRIPE_PRICE_*` env var keeps the
two in step by construction. There is no separate "display price" seam to forget.

══ WHY A CACHE, AND WHY TWO LAYERS ═════════════════════════════════════════════════════

The public pricing page is the top of the funnel: it is hit by every anonymous visitor,
crawler and preview-link expander. A Stripe API call per pageview is both a latency tax
on the page that has to convert and an external dependency on the page least able to
afford one — a Stripe blip would blank the price.

Resolution order, and each layer answers a failure the layer above cannot:

  1. IN-MEMORY, fresh (< TTL)  — the common case; zero external calls.
  2. STRIPE                    — the source of truth; refreshes both caches.
  3. IN-MEMORY, STALE          — Stripe is unreachable and this container has seen a
                                 price before. Showing the last real price beats
                                 blanking the page.
  4. DYNAMO last-known-good    — Stripe is unreachable AND this is a COLD container.
                                 An in-memory cache alone is per-container, so without
                                 this layer a Lambda cold start during a Stripe outage
                                 has nothing, which is exactly when it matters.
  5. None                      — never fetched successfully since this Price was
                                 configured. The caller 503s. ⛔ It deliberately does
                                 NOT fall back to a hardcoded constant: a wrong price is
                                 worse than a missing one, and re-introducing a second
                                 source of truth is the exact defect this module removes.

⚠️ NEVER call `.get()` on a Stripe SDK object. `StripeObject` supports `in` and `[...]`
but does not define `.get()`, so `price.get("unit_amount")` raises `AttributeError` —
confirmed live in prod twice (E9.8 webhook `construct_event`, E9.57 `Subscription.list`),
both times swallowed by a broad `except` into a plausible-looking wrong answer. `_field`
below is the one accessor, and it works on a StripeObject and a plain dict alike.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass

import stripe

from app.backend.services import dynamo

logger = logging.getLogger(__name__)

# Short by design. This is the window between an operator editing the price in the Stripe
# dashboard and the site showing it — the "one dashboard edit, no redeploy" promise. It is
# NOT a correctness knob: every layer below it serves a price Stripe really returned.
_TTL_SECONDS = int(os.getenv("STRIPE_PRICE_CACHE_TTL_SECONDS", "300"))


@dataclass(frozen=True)
class PriceSnapshot:
    """Exactly the fields a pricing page needs, and nothing else."""

    price_id: str
    unit_amount: int   # cents (Stripe's minor unit)
    currency: str
    interval: str      # "month" | "year" | …
    interval_count: int
    product_name: str


# price_id -> (fetched_at_epoch, snapshot). Module-level, so it survives across
# invocations of a warm Lambda container and is empty on a cold one.
_memory: dict[str, tuple[float, PriceSnapshot]] = {}
# What we last wrote to Dynamo, so an unchanged price is not re-written every TTL.
_persisted: dict[str, PriceSnapshot] = {}


def _field(obj, key):
    """Read `key` off a Stripe SDK object OR a plain dict. See the `.get()` note above."""
    if obj is None:
        return None
    try:
        return obj[key] if key in obj else None
    except TypeError:  # not subscriptable — treat as absent rather than exploding
        return None


def _from_stripe(price_id: str) -> PriceSnapshot:
    """Retrieve the Price (with its Product expanded) and narrow it to a snapshot.

    Raises if the Price cannot answer the question a pricing page asks — a metered or
    tiered Price has `unit_amount=None`, and rendering that as a number would be a
    fabrication. Raising here means the caller falls through to a cached snapshot or a
    503, both of which are honest."""
    price = stripe.Price.retrieve(price_id, expand=["product"])
    recurring = _field(price, "recurring") or {}
    unit_amount = _field(price, "unit_amount")
    currency = _field(price, "currency")
    interval = _field(recurring, "interval")
    product_name = _field(_field(price, "product"), "name")

    if unit_amount is None or not currency or not interval:
        raise ValueError(
            f"Stripe Price {price_id} is not a simple recurring unit price "
            f"(unit_amount={unit_amount!r} currency={currency!r} interval={interval!r})"
        )

    return PriceSnapshot(
        price_id=price_id,
        unit_amount=int(unit_amount),
        currency=str(currency),
        interval=str(interval),
        interval_count=int(_field(recurring, "interval_count") or 1),
        # A Product with no name is odd but not a reason to withhold the price.
        product_name=str(product_name or "Membership"),
    )


def _persist(snapshot: PriceSnapshot) -> None:
    if _persisted.get(snapshot.price_id) == snapshot:
        return
    dynamo.write_price_snapshot(snapshot.price_id, asdict(snapshot))
    _persisted[snapshot.price_id] = snapshot


def _last_known_good(price_id: str) -> PriceSnapshot | None:
    raw = dynamo.read_price_snapshot(price_id)
    if not raw:
        return None
    try:
        return PriceSnapshot(
            price_id=price_id,
            unit_amount=int(raw["unit_amount"]),
            currency=str(raw["currency"]),
            interval=str(raw["interval"]),
            interval_count=int(raw.get("interval_count") or 1),
            product_name=str(raw.get("product_name") or "Membership"),
        )
    except (KeyError, TypeError, ValueError):
        logger.exception("Malformed last-known-good price snapshot (price=%s)", price_id)
        return None


def resolve(price_id: str) -> PriceSnapshot | None:
    """The price to DISPLAY for `price_id`, or None if no layer can answer.

    See the resolution order in the module docstring. Never raises: a pricing page that
    500s is strictly worse than one that degrades."""
    now = time.time()
    cached = _memory.get(price_id)
    if cached and (now - cached[0]) < _TTL_SECONDS:
        return cached[1]

    try:
        snapshot = _from_stripe(price_id)
    except Exception:  # noqa: BLE001 — any Stripe/network/shape failure falls through
        logger.exception("Could not read Stripe Price %s — falling back", price_id)
    else:
        _memory[price_id] = (now, snapshot)
        try:
            _persist(snapshot)
        except Exception:  # noqa: BLE001 — caching is best-effort, the read succeeded
            logger.exception("Could not persist the price snapshot (price=%s)", price_id)
        return snapshot

    if cached:
        logger.warning("Serving a STALE cached price for %s (Stripe unreachable)", price_id)
        return cached[1]

    lkg = _last_known_good(price_id)
    if lkg:
        logger.warning("Serving the last-known-good price for %s (Stripe unreachable, cold)", price_id)
        # Seed the memory cache so a Stripe outage is not one Dynamo read per pageview.
        _memory[price_id] = (now, lkg)
        return lkg

    logger.error("No price available for %s — no cache, no last-known-good, Stripe failed", price_id)
    return None


def invalidate(price_id: str | None = None) -> None:
    """Drop the in-memory cache so the next read goes back to Stripe.

    Called from the webhook on `price.*` / `product.*` events, which turns the TTL into a
    ceiling rather than the mechanism: with those events subscribed in the Stripe
    dashboard, a dashboard price edit shows up on the next pageview. Without them the TTL
    still bounds it, so this is an optimisation and never a correctness requirement.

    The DURABLE last-known-good is deliberately NOT cleared — it is the outage fallback,
    and dropping it would leave a cold container with nothing during the very window a
    price change is propagating."""
    if price_id is None:
        _memory.clear()
    else:
        _memory.pop(price_id, None)
