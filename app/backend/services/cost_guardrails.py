"""G100-D1 — cost guardrails for the public launch: a per-IP rate limiter and a spend kill switch.

WHY THIS EXISTS. E9.46 + the freemium flip open the generic rankings board to anonymous traffic. The
platform is self-funded on Vercel Pro + AWS with no per-caller quota anywhere in front of it: API
Gateway HTTP API throttling is **per-API, not per-caller** (usage plans are a REST-API feature, and
AWS WAF does not support HTTP APIs — see `infrastructure/aws_resources.md`). So the stage throttle
can only bound the TOTAL blast radius; it cannot tell one scraper from the whole user base, and a
limit low enough to stop the scraper also throttles everyone else. The per-caller dimension has to
live here, in the application, or it does not exist.

Two independent levers, deliberately separate:

  1. **RATE LIMIT** (always on) — a per-IP token bucket. Bounds what any single caller can extract
     and therefore what any single caller can cost us.
  2. **DEGRADE MODE** (`COST_DEGRADE_MODE=1`, off by default) — the one-flip floor. If spend spikes,
     the operator flips it and the API serves ONLY the cheap cached/static reads; the expensive
     personalized + decision-support endpoints answer 503 with an honest payload. A runaway bill
     lands on a floor instead of an outage.

───────────────────────────────────────────────────────────────────────────────────────────────────
FOUR THINGS THAT MAKE THIS ACTUALLY WORK (each is a way a limiter looks present and does nothing)
───────────────────────────────────────────────────────────────────────────────────────────────────

1. ⭐ **THE CLIENT IP MUST NOT BE CALLER-CONTROLLED.** The obvious implementation reads the FIRST
   entry of `X-Forwarded-For`, which is exactly the value an attacker sets. `X-Forwarded-For:
   1.2.3.4` then buys a fresh bucket on every request and the limiter is bypassed with one header —
   a guard that cannot fail. The trustworthy value is the gateway's OWN observation
   (`requestContext.http.sourceIp`), which no client can forge; XFF's **RIGHTMOST** entry is the
   fallback, because each proxy APPENDS, so the rightmost is the one written by the hop nearest us.
   `resolve_client_ip` implements that order and `test_g100_d1_cost_guardrails.py` proves a spoofed
   header cannot mint a new bucket.

2. ⭐ **DEGRADE MODE IS AN ALLOWLIST, NEVER A DENYLIST** — the same load-bearing direction as
   E9.56's entitlement redaction, for the same reason. Under a denylist the next expensive endpoint
   someone adds keeps burning while the switch reads "on": the kill switch silently fails to contain
   the bill, which is the one thing it exists to do. Under an allowlist a new endpoint is contained
   by default and the worst case is over-blocking during an emergency the operator declared — that
   is visible, reversible, and exactly what was asked for. Guarded by
   `test_a_new_endpoint_is_contained_by_default`.

3. ⭐ **THE BUCKET STORE MUST BE MEMORY-BOUNDED.** The Lambda is 512 MB. An unbounded `{ip: bucket}`
   dict is a memory leak that a scraper rotating source IPs turns into an OOM — i.e. the cost guard
   becomes the outage. The store is a bounded LRU (`_MAX_TRACKED_IPS`). The honest limitation of
   evicting under IP rotation is documented on `RateLimiter` rather than papered over.

4. ⭐ **A 429 MUST CARRY CORS HEADERS.** This middleware is registered INSIDE `CORSMiddleware` (see
   `main.py`) so a throttled response still passes back out through it. A 429 without CORS headers
   does not present to the user as "slow down" — it presents as an opaque browser network error with
   no status visible to JS, which is indistinguishable from the API being down.

HONEST LIMITATION, STATED UP FRONT: the bucket store is per-Lambda-CONTAINER, not global. Concurrent
containers each hold their own view, so the effective ceiling is `limit × live containers` and a
low-volume attacker spread thinly across cold starts is under-counted. This is deliberate — an exact
limiter needs a DynamoDB read+write on EVERY request, which is itself a per-request cost on the hot
path this story exists to protect, and it would put a network round-trip in front of a cached read.
The bucket catches what actually matters: SUSTAINED extraction from one source, which necessarily
lands on warm containers. The stage-wide API Gateway throttle is the true hard ceiling underneath;
these two compose (per-caller shaping here, total blast radius there).
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════════════════════
# Client IP resolution
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Returned when no trustworthy IP can be resolved. A single shared bucket is the SAFE direction: it
# degrades to a global limit rather than to no limit at all. Handing every unidentifiable caller its
# own bucket would mean "unidentifiable" is the bypass.
UNKNOWN_IP = "_unknown"


def resolve_client_ip(request) -> str:
    """The most trustworthy client IP available, in descending order of forgeability.

    1. `requestContext.http.sourceIp` from the API Gateway HTTP API v2 event — the gateway's own
       observation of the TCP peer. A client cannot influence it. Mangum stashes the raw event on
       the ASGI scope as `aws.event`, which is how we reach it.
    2. `request.client.host` — what Mangum derives from that same field locally, and the real peer
       under uvicorn in local dev.
    3. The **RIGHTMOST** `X-Forwarded-For` entry. Proxies APPEND, so the rightmost hop is the one
       written by the infrastructure closest to us; every entry to its left is either an upstream
       proxy or a value the caller made up. Taking the leftmost — the common implementation — is the
       bug this ordering exists to avoid.

    Never raises: a limiter that throws on a malformed header fails the request open.
    """
    # 1. The gateway's own observation.
    try:
        event = request.scope.get("aws.event") or {}
        source_ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
        if source_ip:
            return str(source_ip)
    except Exception:  # noqa: BLE001 — a malformed event must never break request handling
        logger.debug("cost_guardrails: could not read sourceIp from the gateway event", exc_info=True)

    # 2. The ASGI peer.
    try:
        client = request.client
        if client is not None and client.host:
            return str(client.host)
    except Exception:  # noqa: BLE001
        logger.debug("cost_guardrails: could not read request.client", exc_info=True)

    # 3. Rightmost X-Forwarded-For entry — see the docstring for why rightmost and not leftmost.
    try:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                return parts[-1]
    except Exception:  # noqa: BLE001
        logger.debug("cost_guardrails: could not read X-Forwarded-For", exc_info=True)

    return UNKNOWN_IP


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Token-bucket rate limiter
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Bounded so a source-IP-rotating scraper cannot grow this dict into an OOM on a 512 MB Lambda.
# ~10k entries × (an IPv6 string + two floats) is well under a megabyte.
_MAX_TRACKED_IPS = 10_000


def _env_float(name: str, default: float) -> float:
    """Read a tuning knob from the environment, falling back on any malformed value.

    Deliberately tolerant: a typo'd env var must not take the API down at import. A bad value is
    logged and the default stands.
    """
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning("cost_guardrails: %s=%r is not a number; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning("cost_guardrails: %s=%r must be > 0; using default %s", name, raw, default)
        return default
    return value


@dataclass
class RateLimitPolicy:
    """A token bucket: `burst` tokens of capacity, refilled at `per_second`.

    `burst` is what a normal page load spends at once (a board page fires several parallel calls);
    `per_second` is the sustained ceiling that actually bounds bulk extraction.
    """

    burst: float
    per_second: float

    @property
    def retry_after_seconds(self) -> int:
        """Seconds until one whole token exists again — what to put in `Retry-After`.

        At least 1: a `Retry-After: 0` invites an immediate retry, which is the opposite of what a
        throttled client should do.
        """
        return max(1, int(round(1.0 / self.per_second)))


def public_policy() -> RateLimitPolicy:
    """Anonymous / unauthenticated reads.

    Sized for a human browsing the board, not for a crawler. A rankings page load fires a handful of
    calls at once (manifest + board + projections), hence the burst headroom; 30/min sustained is far
    above any human's reading pace and far below a useful scrape rate.
    """
    return RateLimitPolicy(
        burst=_env_float("COST_RL_PUBLIC_BURST", 30.0),
        per_second=_env_float("COST_RL_PUBLIC_PER_SECOND", 0.5),
    )


def authenticated_policy() -> RateLimitPolicy:
    """Signed-in callers. Looser — these are paying users on personalized surfaces that legitimately
    fan out into several calls (performance, bet log, parlay builder), and they are already bounded
    by having had to authenticate."""
    return RateLimitPolicy(
        burst=_env_float("COST_RL_AUTH_BURST", 60.0),
        per_second=_env_float("COST_RL_AUTH_PER_SECOND", 2.0),
    )


class RateLimiter:
    """An in-process, memory-bounded per-key token bucket.

    ⚠️ PER-CONTAINER, NOT GLOBAL — see the module docstring. This shapes sustained single-source
    extraction; it is not an exact quota and is not represented as one.

    ⚠️ UNDER IP ROTATION the LRU evicts, so an attacker cycling through more than `max_keys`
    addresses can keep finding fresh buckets. That is inherent to any bounded in-memory store; the
    stage-wide API Gateway throttle is the backstop for that case, and it is the reason both layers
    are applied rather than either alone.
    """

    def __init__(self, max_keys: int = _MAX_TRACKED_IPS) -> None:
        # key -> (tokens_remaining, last_refill_monotonic)
        self._buckets: OrderedDict[str, tuple[float, float]] = OrderedDict()
        self._max_keys = max_keys

    def check(self, key: str, policy: RateLimitPolicy, now: float | None = None) -> bool:
        """Consume one token for `key`. True if the request is allowed, False if it is throttled.

        `now` is injectable so the tests can drive refill deterministically rather than sleeping —
        a limiter tested with real sleeps is a slow test that still cannot prove the refill maths.
        """
        now = time.monotonic() if now is None else now

        tokens, last = self._buckets.get(key, (policy.burst, now))
        # Refill for elapsed time, capped at capacity. `max(0.0, ...)` guards a non-monotonic clock:
        # a negative delta must never DRAIN the bucket.
        elapsed = max(0.0, now - last)
        tokens = min(policy.burst, tokens + elapsed * policy.per_second)

        if tokens < 1.0:
            # Still record the refill so the caller is not permanently pinned at zero, and refresh
            # LRU position so an actively-throttled key is not the first thing evicted (evicting it
            # would hand the attacker a clean bucket — the eviction policy must not reward abuse).
            self._buckets[key] = (tokens, now)
            self._buckets.move_to_end(key)
            return False

        self._buckets[key] = (tokens - 1.0, now)
        self._buckets.move_to_end(key)
        self._evict_if_needed()
        return True

    def _evict_if_needed(self) -> None:
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)  # drop the least-recently-seen key

    def reset(self) -> None:
        """Drop all state. For tests and for a deliberate operator flush; never called on the hot path."""
        self._buckets.clear()

    @property
    def tracked_keys(self) -> int:
        return len(self._buckets)


# The process-wide limiter. Module-level so it survives across warm invocations of the same
# container — a per-request instance would reset every bucket on every call and limit nothing.
_LIMITER = RateLimiter()


def get_limiter() -> RateLimiter:
    return _LIMITER


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Degrade mode — the spend kill switch
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Paths that stay UP when degrade mode is on. ALLOWLIST — see docstring point 2.
#
# The rule for membership: it is cheap AND it is the floor we promise. Cheap means a DynamoDB point
# read or a single S3 GetObject of a pre-built artifact — never a `lakehouse_query` (DuckDB-over-S3,
# seconds of compute and the E9.26b silent-empty hazard), never a fan-out.
#
# Matching is by PREFIX, so `/fantasy/nfl/track-record` covers `/manifest` and `/{season}` alike.
_DEGRADE_ALLOWED_PREFIXES: tuple[str, ...] = (
    # Liveness + platform plumbing. Blocking these turns a cost event into a real outage:
    # a failing /health can deregister the API, and a blocked Stripe webhook silently drops
    # subscription state changes we can never replay.
    "/health",
    "/stripe/webhook",
    # Auth must keep working or nobody can sign in to see even the free board.
    "/auth",
    # The free/generic board — the floor the product promises anonymous visitors. Every one of
    # these is a single S3 GetObject of a pre-built JSON blob.
    "/fantasy/nfl/manifest",
    "/fantasy/nfl/projections",
    "/fantasy/nfl/board",
    "/fantasy/nfl/track-record",
    # The public marketing surfaces. `/picks/featured` is a DynamoDB point read on the cache-hit
    # path (G100-D1 removed its per-request lakehouse fallback, so it is genuinely cheap now).
    "/picks/featured",
    "/blog/posts",
    # Pricing must stay readable or the upgrade funnel dies exactly when we most want revenue.
    "/stripe/public",
    "/subscribe",
)

# Human-readable reason, returned in the 503 body so the client can render an honest state rather
# than a generic failure. Additive: a client that does not know the field ignores it (NF-C0).
DEGRADE_MESSAGE = (
    "This view is temporarily unavailable while we manage service capacity. "
    "The free rankings board and your account are unaffected."
)


def degrade_mode_enabled() -> bool:
    """Read the flag at CALL time, not import time.

    Import-time capture would mean the flag only takes effect on containers started after the flip,
    so an operator watching spend would see it half-apply across the warm fleet with no way to tell
    which. Reading per call makes `aws lambda update-function-configuration` fully effective the
    moment the new env reaches a container.
    """
    return os.getenv("COST_DEGRADE_MODE", "").strip() in ("1", "true", "True", "TRUE", "yes")


def is_allowed_in_degrade(path: str) -> bool:
    """Whether `path` stays up while degrade mode is on. ALLOWLIST — unknown paths are contained."""
    if not path:
        return False
    # Normalise a trailing slash so `/health/` and `/health` classify identically.
    normalised = path.rstrip("/") or "/"
    for prefix in _DEGRADE_ALLOWED_PREFIXES:
        if normalised == prefix or normalised.startswith(prefix + "/") or normalised.startswith(prefix + "?"):
            return True
    # CORS preflight is never the expensive thing and blocking it breaks every cross-origin call
    # with an opaque error rather than an honest 503.
    return False


def degrade_exempt_methods() -> frozenset[str]:
    """Methods that bypass the degrade check entirely. OPTIONS is preflight — a blocked preflight
    presents as a CORS failure, not as a service message, so it must always pass."""
    return frozenset({"OPTIONS"})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Cache-Control — make the anonymous read path CDN-cacheable
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Public, anonymous GET reads that are safe for a SHARED cache, and how long for.
#   (path prefix, s-maxage seconds, stale-while-revalidate seconds)
#
# `s-maxage` targets shared caches (Vercel's CDN, and CloudFront if it is ever put in front of the
# API) rather than the browser, which is the copy that actually saves us a Lambda invocation.
# `stale-while-revalidate` means an expiring entry is served immediately while it refreshes behind
# the scenes, so a TTL rollover never costs a visitor a cold read.
_PUBLIC_CACHE_RULES: tuple[tuple[str, int, int], ...] = (
    # The board blobs change only when the operator re-runs an exporter — not intraday. A long TTL
    # is honest here, and it is the single biggest lever on anonymous cost.
    ("/fantasy/nfl/manifest", 900, 3600),
    ("/fantasy/nfl/projections", 900, 3600),
    ("/fantasy/nfl/board", 900, 3600),
    # Past seasons. Immutable in practice — a past season's track record does not change.
    ("/fantasy/nfl/track-record", 3600, 86400),
    # Re-written intraday by each re-score, so a much shorter window. Still collapses a burst of
    # landing-page views onto one origin read.
    ("/picks/featured", 300, 900),
    ("/blog/posts", 600, 3600),
)

# What a personalized or authenticated response must carry. `no-store` is deliberate over
# `private, max-age=0`: it forbids writing the payload to disk at all, which is the right handling
# for someone's bet log and bankroll.
PRIVATE_CACHE_CONTROL = "private, no-store"


def public_cache_control(path: str) -> str | None:
    """The `Cache-Control` value for an ANONYMOUS GET of `path`, or None if it is not shared-cacheable.

    Callers must only apply this when the request carried NO `Authorization` header — see
    `cache_control_for` for why that condition is load-bearing rather than a detail.
    """
    if not path:
        return None
    normalised = path.rstrip("/") or "/"
    for prefix, s_maxage, swr in _PUBLIC_CACHE_RULES:
        if normalised == prefix or normalised.startswith(prefix + "/"):
            return f"public, s-maxage={s_maxage}, stale-while-revalidate={swr}"
    return None


def cache_control_for(path: str, *, has_authorization: bool, status_code: int) -> str | None:
    """The `Cache-Control` header to apply, or None to leave the response's own header alone.

    🔒 THE ENTITLEMENT HAZARD THIS EXISTS TO CLOSE. `/fantasy/nfl/board` answers with the LOCKED
    payload for an anonymous caller and the FULL payload for a subscriber — the SAME URL, two
    different bodies. Marking that `public` without discriminating would let a shared cache store one
    subscriber's full board and hand it to every anonymous visitor: a paid-data breach caused
    entirely by a caching header. So:
      • an `Authorization` header present ⇒ `private, no-store`, unconditionally, on every path;
      • absent ⇒ shared-cacheable, but only for the paths in `_PUBLIC_CACHE_RULES`.
    The caller must ALSO emit `Vary: Authorization` so a cache keyed on the URL alone cannot mix the
    two. Both halves are required; either one alone still allows the breach.

    ⭐ NON-200s ARE NEVER CACHED (E9.26b). A `lakehouse_query` failure surfaces as an empty or error
    payload rather than an exception, and pinning that into a CDN for the full TTL turns a transient
    blip into a blank surface for everyone until it expires. An empty read is SUSPECT; it does not
    get to be a cache entry.
    """
    if has_authorization:
        return PRIVATE_CACHE_CONTROL
    if status_code != 200:
        return "no-store"
    return public_cache_control(path)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The middleware
# ══════════════════════════════════════════════════════════════════════════════════════════════

# Paths the RATE LIMITER must never touch. Each one is a case where throttling causes a worse
# failure than the traffic it would shed:
#   • /health   — a throttled health check reads as an unhealthy API and can deregister it.
#   • /stripe/webhook — Stripe delivers from a small pool of source IPs, so a per-IP limit is
#     exactly wrong here: a dropped webhook means a real payment whose subscription never
#     activates, and the customer sees a charge with no access. Signature-verified and low volume.
_RATE_LIMIT_EXEMPT_PREFIXES: tuple[str, ...] = ("/health", "/stripe/webhook")


def is_rate_limit_exempt(path: str) -> bool:
    if not path:
        return False
    normalised = path.rstrip("/") or "/"
    return any(
        normalised == p or normalised.startswith(p + "/") for p in _RATE_LIMIT_EXEMPT_PREFIXES
    )


def _add_vary_authorization(response) -> None:
    """Append `Authorization` to `Vary` without clobbering what is already there (CORSMiddleware
    adds `Origin`). A cache keyed on URL alone would otherwise be free to serve a subscriber's
    payload to an anonymous caller — see `cache_control_for`."""
    existing = response.headers.get("vary")
    if not existing:
        response.headers["Vary"] = "Authorization"
        return
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    if not any(p.lower() == "authorization" for p in parts):
        response.headers["Vary"] = ", ".join([*parts, "Authorization"])


async def cost_guardrail_middleware(request, call_next):
    """Degrade check → per-IP rate limit → response cache headers.

    ⚠️ REGISTRATION ORDER IS LOAD-BEARING: this must sit INSIDE `CORSMiddleware` (registered
    BEFORE it in `main.py`, since Starlette makes the last-added middleware outermost). A 429 or 503
    returned from here has to travel back out through CORS to pick up its headers — without them the
    browser reports an opaque network error and JS cannot see the status at all, so the frontend
    cannot tell "slow down" from "the API is gone". Pinned by
    `test_g100_d1_cost_guardrails.py::test_a_throttled_response_still_carries_cors_headers`.
    """
    # Local import: keeps this module importable without FastAPI installed (the pure policy
    # functions above are exercised by tests that never construct a request).
    from fastapi.responses import JSONResponse

    path = request.url.path
    method = request.method
    has_auth = bool(request.headers.get("authorization"))

    # ── 1. Degrade mode — the spend kill switch. Checked first: when it is on we want to spend as
    #      little as possible on a request we are about to refuse anyway.
    if (
        method not in degrade_exempt_methods()
        and degrade_mode_enabled()
        and not is_allowed_in_degrade(path)
    ):
        logger.info("cost_guardrails: degrade mode refused %s %s", method, path)
        return JSONResponse(
            status_code=503,
            # ADDITIVE shape (NF-C0): `detail` is what every other error on this API returns and
            # what the deployed client already renders. `degraded` is the new field — a client that
            # does not know it simply ignores it.
            content={"detail": DEGRADE_MESSAGE, "degraded": True},
            headers={"Retry-After": "300", "Cache-Control": "no-store"},
        )

    # ── 2. Per-IP rate limit.
    if method not in degrade_exempt_methods() and not is_rate_limit_exempt(path):
        policy = authenticated_policy() if has_auth else public_policy()
        client_ip = resolve_client_ip(request)
        if not get_limiter().check(client_ip, policy):
            logger.warning("cost_guardrails: rate-limited %s %s for %s", method, path, client_ip)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again shortly."},
                headers={
                    "Retry-After": str(policy.retry_after_seconds),
                    "Cache-Control": "no-store",
                },
            )

    response = await call_next(request)

    # ── 3. Cache headers. Do not overwrite a handler that has deliberately set its own.
    if "cache-control" not in response.headers:
        value = cache_control_for(path, has_authorization=has_auth, status_code=response.status_code)
        if value:
            response.headers["Cache-Control"] = value
            _add_vary_authorization(response)
    return response
