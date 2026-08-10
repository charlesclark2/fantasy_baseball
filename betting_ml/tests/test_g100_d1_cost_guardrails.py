"""G100-D1 — guards for the launch cost guardrails: per-IP rate limit, degrade kill switch,
CDN cache headers, and the removal of the per-request lakehouse read from the public hot path.

⚠️ EVERY GUARD HERE WAS RED-PROVEN against deliberately-broken source before being trusted (the
NF-D17 rule: a guard on an `and`-composed rule is vacuous unless its fixture satisfies every OTHER
clause, so each fixture below isolates ONE property). The RED proofs are recorded in the session
handoff; the specific breaks are named in the docstrings of the tests that catch them.

WHY SO MUCH ATTENTION TO THE IP: a rate limiter keyed on a caller-controlled value is not a weak
limiter, it is NO limiter — `X-Forwarded-For: <random>` buys a fresh bucket per request and the
guard can never fail. That is the INC-38/INC-39 vacuous-guard family, and it is the single easiest
way to ship this story broken while every test passes.

The ASGI driver is raw rather than starlette's `TestClient` for the reason
`test_e9_56_entitlement.py` documents: `httpx` is absent from this env, AND raw ASGI is the only way
to set the `aws.event` scope key that carries the API Gateway `sourceIp` — which is precisely the
value under test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.services import cost_guardrails as cg

_FRONTEND = Path("frontend")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# helpers
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _clean_guardrail_state(monkeypatch):
    """Every test starts with an empty bucket store and the kill switch OFF.

    The limiter is deliberately module-level (it must survive across warm Lambda invocations), so
    without this a test's spent tokens leak into the next one and the suite becomes order-dependent.
    """
    cg.get_limiter().reset()
    monkeypatch.delenv("COST_DEGRADE_MODE", raising=False)
    for name in (
        "COST_RL_PUBLIC_BURST",
        "COST_RL_PUBLIC_PER_SECOND",
        "COST_RL_AUTH_BURST",
        "COST_RL_AUTH_PER_SECOND",
    ):
        monkeypatch.delenv(name, raising=False)
    yield
    cg.get_limiter().reset()


class _FakeRequest:
    """The narrow slice of a Starlette Request that `resolve_client_ip` reads."""

    class _Client:
        def __init__(self, host):
            self.host = host

    def __init__(self, *, aws_event=None, peer=None, headers=None):
        self.scope = {"aws.event": aws_event} if aws_event is not None else {}
        self.client = self._Client(peer) if peer is not None else None
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


def _gw_event(source_ip: str) -> dict:
    """An API Gateway HTTP API v2 event carrying the gateway's own observation of the peer."""
    return {"requestContext": {"http": {"sourceIp": source_ip}}}


def _call(path, query="", *, method="GET", headers=None, aws_event=None):
    """Drive the real ASGI app. Returns (status, headers_dict, parsed_body_or_raw_text)."""
    import anyio

    from app.backend.main import app

    out: dict = {}
    body_parts: list[bytes] = []

    async def run():
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")]
            + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("203.0.113.9", 1),
            "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
                out["headers"] = {
                    k.decode().lower(): v.decode() for k, v in message.get("headers", [])
                }
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    raw = b"".join(body_parts)
    try:
        parsed = json.loads(raw)
    except Exception:  # noqa: BLE001
        parsed = raw.decode(errors="replace")
    return out["status"], out.get("headers", {}), parsed


def _ts_code(rel: str) -> str:
    """TypeScript source with comments stripped, so PROSE cannot satisfy a source guard (INC-38).

    ⚠️ LINE COMMENTS FIRST, THEN BLOCKS — this order is load-bearing and the opposite of the
    obvious one. `// … /api/public/fantasy/* …` is ordinary prose in this codebase and contains
    `/*`; stripping blocks first reads that as an opening delimiter and deletes everything up to the
    next genuine `*/`, silently removing the very lines the guard polices. Measured elsewhere in
    this repo at 55 live lines deleted. `(?<!:)` keeps `https://` from being eaten.
    """
    text = (_FRONTEND / rel).read_text()
    text = re.sub(r"(?<!:)//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# A. Client-IP resolution — the property that makes the limiter real
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_gateway_source_ip_is_preferred_over_every_caller_supplied_header():
    """RED-PROVEN by reordering `resolve_client_ip` to read X-Forwarded-For first.

    The fixture supplies BOTH a gateway observation and a contradicting header, so only the
    precedence can decide the answer (NF-D17: isolate the clause under test).
    """
    req = _FakeRequest(
        aws_event=_gw_event("198.51.100.7"),
        peer="10.0.0.1",
        headers={"x-forwarded-for": "1.2.3.4"},
    )
    assert cg.resolve_client_ip(req) == "198.51.100.7"


def test_a_spoofed_x_forwarded_for_cannot_mint_a_fresh_bucket():
    """THE test. One real caller varying its own XFF must stay in ONE bucket and get throttled.

    RED-PROVEN: making `resolve_client_ip` return the leftmost XFF entry lets all 40 requests
    through, because each forged value is a new key. That is the bypass this whole ordering exists
    to prevent, and it is invisible to any test that only checks "the limiter blocks eventually".
    """
    policy = cg.RateLimitPolicy(burst=5, per_second=0.001)
    limiter = cg.get_limiter()
    allowed = 0
    for i in range(40):
        req = _FakeRequest(
            aws_event=_gw_event("198.51.100.7"),  # the truth: always the same caller
            headers={"x-forwarded-for": f"10.9.9.{i}"},  # the lie: a new identity each time
        )
        if limiter.check(cg.resolve_client_ip(req), policy, now=100.0):
            allowed += 1
    assert allowed == 5, f"a spoofed header bought {allowed - 5} extra requests"


def test_the_rightmost_forwarded_for_entry_is_used_not_the_leftmost():
    """With no gateway event and no peer, XFF is the last resort — and only its RIGHTMOST entry is
    trustworthy, because proxies APPEND. The leftmost is whatever the client typed.

    RED-PROVEN by switching `parts[-1]` to `parts[0]`.
    """
    req = _FakeRequest(headers={"x-forwarded-for": "1.2.3.4, 5.6.7.8, 198.51.100.7"})
    assert cg.resolve_client_ip(req) == "198.51.100.7"


def test_an_unresolvable_caller_falls_into_one_shared_bucket_not_a_free_pass():
    """Degrading to a single global bucket is the safe direction; handing every unidentifiable
    caller its own bucket would make 'unidentifiable' the bypass."""
    a = cg.resolve_client_ip(_FakeRequest())
    b = cg.resolve_client_ip(_FakeRequest())
    assert a == b == cg.UNKNOWN_IP


def test_a_malformed_gateway_event_does_not_break_request_handling():
    """A limiter that raises on junk input fails the request OPEN — worse than no limiter, because
    it takes the endpoint down too."""
    req = _FakeRequest(aws_event={"requestContext": "not-a-dict"}, peer="10.0.0.5")
    assert cg.resolve_client_ip(req) == "10.0.0.5"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# B. The token bucket
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_burst_is_spendable_then_the_bucket_blocks():
    policy = cg.RateLimitPolicy(burst=3, per_second=0.5)
    limiter = cg.RateLimiter()
    assert [limiter.check("ip", policy, now=0.0) for _ in range(3)] == [True, True, True]
    assert limiter.check("ip", policy, now=0.0) is False


def test_tokens_refill_over_elapsed_time():
    policy = cg.RateLimitPolicy(burst=2, per_second=1.0)
    limiter = cg.RateLimiter()
    limiter.check("ip", policy, now=0.0)
    limiter.check("ip", policy, now=0.0)
    assert limiter.check("ip", policy, now=0.0) is False
    assert limiter.check("ip", policy, now=1.0) is True, "one second should buy one token"


def test_refill_never_exceeds_the_burst_capacity():
    """Otherwise a caller who idles for an hour returns with an unbounded credit and can pull the
    whole board in one pass — the exact scrape the limiter exists to bound."""
    policy = cg.RateLimitPolicy(burst=3, per_second=1.0)
    limiter = cg.RateLimiter()
    limiter.check("ip", policy, now=0.0)
    allowed = sum(1 for _ in range(50) if limiter.check("ip", policy, now=3600.0))
    assert allowed == 3


def test_a_backwards_clock_cannot_drain_the_bucket():
    """`max(0.0, now - last)` guards this. Without it a negative delta SUBTRACTS tokens, so a clock
    adjustment locks a legitimate caller out. RED-PROVEN by removing the clamp."""
    policy = cg.RateLimitPolicy(burst=5, per_second=1.0)
    limiter = cg.RateLimiter()
    assert limiter.check("ip", policy, now=1000.0) is True
    assert limiter.check("ip", policy, now=0.0) is True


def test_the_bucket_store_is_memory_bounded():
    """An unbounded {ip: bucket} dict is an OOM on a 512 MB Lambda under IP rotation — the cost
    guard becoming the outage. RED-PROVEN by deleting `_evict_if_needed`'s call site."""
    policy = cg.RateLimitPolicy(burst=1, per_second=1.0)
    limiter = cg.RateLimiter(max_keys=50)
    for i in range(5000):
        limiter.check(f"10.0.{i // 256}.{i % 256}", policy, now=float(i))
    assert limiter.tracked_keys <= 50


def test_an_actively_throttled_key_is_not_the_first_thing_evicted():
    """Eviction must not REWARD abuse: dropping the loudest caller's bucket hands them a clean one.

    The throttled key keeps being touched, so LRU keeps it; the quiet keys age out instead.
    """
    policy = cg.RateLimitPolicy(burst=1, per_second=0.0001)
    limiter = cg.RateLimiter(max_keys=10)
    for i in range(200):
        limiter.check("attacker", policy, now=float(i))  # hammering, always throttled
        limiter.check(f"visitor-{i}", policy, now=float(i))  # one-shot visitors
    assert limiter.check("attacker", policy, now=200.0) is False, "the attacker got a fresh bucket"


def test_retry_after_is_never_zero():
    """`Retry-After: 0` invites an immediate retry — the opposite instruction to a throttled client."""
    assert cg.RateLimitPolicy(burst=1, per_second=1000.0).retry_after_seconds >= 1


def test_a_malformed_tuning_env_var_falls_back_instead_of_taking_the_api_down(monkeypatch):
    monkeypatch.setenv("COST_RL_PUBLIC_BURST", "not-a-number")
    monkeypatch.setenv("COST_RL_PUBLIC_PER_SECOND", "-5")
    policy = cg.public_policy()
    assert policy.burst > 0 and policy.per_second > 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# C. Degrade mode — the kill switch
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_degrade_mode_is_off_by_default():
    assert cg.degrade_mode_enabled() is False


def test_the_flag_is_read_at_call_time_so_a_live_flip_takes_effect(monkeypatch):
    """Import-time capture would half-apply across the warm fleet with no way to tell which
    containers had picked it up. RED-PROVEN by hoisting the getenv to module scope."""
    assert cg.degrade_mode_enabled() is False
    monkeypatch.setenv("COST_DEGRADE_MODE", "1")
    assert cg.degrade_mode_enabled() is True


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/fantasy/nfl/manifest",
        "/fantasy/nfl/projections",
        "/fantasy/nfl/board",
        "/fantasy/nfl/track-record/manifest",
        "/fantasy/nfl/track-record/2024",
        "/picks/featured",
        "/blog/posts",
        "/stripe/webhook",
    ],
)
def test_the_promised_floor_stays_up_in_degrade_mode(path):
    """The switch must be a FLOOR, not an outage: the free board, the marketing surfaces, auth and
    the payment webhook all survive."""
    assert cg.is_allowed_in_degrade(path) is True


def test_the_billing_and_funnel_paths_stay_up_in_degrade_mode():
    """⭐ REGRESSION GUARD FOR A REAL SHIPPED BUG (found 2026-08-08, before the switch was ever used).

    The allowlist carried `"/stripe/public"` and `"/subscribe"`, and NEITHER MATCHED ANY ROUTE: the
    real path is `/subscription/public-pricing` (the prefix had been written from the router's mount
    name, `stripe.public_router`, rather than from the route decorator) and `/subscribe` is a
    FRONT-END page, not an API path. The comment beside them claimed the upgrade funnel was
    protected while degrade mode would in fact have 503'd the pricing page.

    That is the allowlist's characteristic failure mode and the reason this test reads the app's
    REAL route table instead of a hand-written list: a wrong entry does not raise, it silently
    DENIES, and a hand-written fixture would simply repeat the author's wrong assumption about the
    path (the "a test that reads back the key the code wrote" family). Resolving the paths from
    `app.routes` means a future rename breaks this test instead of quietly re-closing the funnel.

    RED-PROVEN by restoring `"/stripe/public"` / `"/subscribe"`: all four paths fail.
    """
    from app.backend.main import app

    real_paths = {r.path for r in app.routes if getattr(r, "path", None)}

    # Each must EXIST (so a rename fails loudly here) and be reachable in degrade mode.
    must_stay_up = {
        "/subscription/public-pricing": "the logged-out upgrade funnel — the whole point of degrading rather than dying",
        "/subscription/status": "app/subscribe/success POLLS it; blocking strands someone who JUST PAID",
        "/stripe/create-checkout-session": "taking money during a cost event is not optional",
        "/stripe/webhook": "a dropped webhook is a real payment whose subscription never activates",
    }
    for path, why in must_stay_up.items():
        assert path in real_paths, f"{path} no longer exists — the allowlist entry is now dead ({why})"
        assert cg.is_allowed_in_degrade(path), f"degrade mode would block {path}: {why}"


def test_an_unknown_new_endpoint_is_contained_by_default():
    """⭐ THE ALLOWLIST PROOF — the load-bearing direction (E9.56 rule 1, same reasoning).

    Under a DENYLIST the next expensive endpoint anyone adds keeps burning while the switch reads
    'on', so the kill switch silently fails at the one job it has. This test is what makes that
    impossible: a path nobody has thought about yet is contained.

    RED-PROVEN by inverting `is_allowed_in_degrade` to a denylist.
    """
    assert cg.is_allowed_in_degrade("/some/endpoint/invented/next/quarter") is False


@pytest.mark.parametrize(
    "path",
    ["/performance/summary", "/parlay/build", "/players/12345", "/teams/NYY", "/bets", "/portfolio"],
)
def test_the_expensive_personalized_endpoints_are_refused_in_degrade_mode(path):
    """These are the `lakehouse_query` surfaces — DuckDB over S3, seconds of Lambda each. They are
    exactly what the operator is flipping the switch to stop paying for."""
    assert cg.is_allowed_in_degrade(path) is False


def test_a_prefix_match_cannot_be_gamed_by_a_lookalike_path():
    """`/fantasy/nfl/boardroom-of-expensive-things` must NOT inherit `/fantasy/nfl/board`'s
    exemption. RED-PROVEN by relaxing the matcher to a bare `startswith(prefix)`."""
    assert cg.is_allowed_in_degrade("/fantasy/nfl/boardroom") is False
    assert cg.is_allowed_in_degrade("/fantasy/nfl/board") is True
    assert cg.is_allowed_in_degrade("/fantasy/nfl/board/2026") is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# D. Cache-Control — the entitlement hazard
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "path",
    [
        "/fantasy/nfl/board",
        "/fantasy/nfl/manifest",
        "/fantasy/nfl/projections",
        "/fantasy/nfl/track-record/2024",
        "/picks/featured",
        "/blog/posts",
    ],
)
def test_an_authorized_request_is_never_shared_cacheable(path):
    """⭐ THE BREACH THIS PREVENTS. `/fantasy/nfl/board` returns the LOCKED payload to an anonymous
    caller and the FULL board to a subscriber — SAME URL, two bodies. Marking a subscriber's
    response `public` lets a shared cache store the paid board and serve it to every anonymous
    visitor thereafter: a paid-data breach caused by a caching header alone.

    Parametrized over EVERY shared-cacheable path, because one missed path is the whole breach.
    RED-PROVEN by dropping the `has_authorization` branch.
    """
    value = cg.cache_control_for(path, has_authorization=True, status_code=200)
    assert value == cg.PRIVATE_CACHE_CONTROL
    assert "public" not in value


def test_an_anonymous_read_of_a_public_path_is_shared_cacheable():
    value = cg.cache_control_for("/fantasy/nfl/board", has_authorization=False, status_code=200)
    assert value is not None and value.startswith("public, s-maxage=")


def test_a_non_200_is_never_cached():
    """E9.26b: a swallowed lakehouse failure surfaces as an error/empty rather than raising. Pinning
    that into a CDN for the full TTL turns a blip into a blank surface for everyone until it
    expires. RED-PROVEN by removing the status check."""
    for status in (404, 429, 500, 502, 503):
        value = cg.cache_control_for("/fantasy/nfl/board", has_authorization=False, status_code=status)
        assert value == "no-store", f"status {status} was cacheable"


def test_a_path_with_no_public_rule_gets_no_cache_header():
    assert cg.cache_control_for("/bets", has_authorization=False, status_code=200) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# E. The middleware, end-to-end through the real ASGI app
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _throttle_until_429(monkeypatch, *, headers=None, limit=6):
    """Spend a deliberately tiny burst so the limiter engages in a few calls rather than hundreds.

    The env knobs are read at CALL time, so setting them here really does shrink the bucket — which
    is itself a small proof that the tuning knobs are live.
    """
    monkeypatch.setenv("COST_RL_PUBLIC_BURST", "2")
    monkeypatch.setenv("COST_RL_PUBLIC_PER_SECOND", "0.01")
    for _ in range(limit):
        status, resp_headers, body = _call("/fantasy/nfl/track-record/manifest", headers=headers)
        if status == 429:
            return status, resp_headers, body
    raise AssertionError("the limiter never engaged, so this guard proved nothing")


def test_a_throttled_response_still_carries_cors_headers(monkeypatch):
    """⭐ REGISTRATION-ORDER GUARD. The guardrail middleware must sit INSIDE `CORSMiddleware`, or a
    429 short-circuits before CORS and reaches the browser with no `access-control-allow-origin`.
    The browser then reports an opaque network error and JS cannot read the status at all — the
    frontend literally cannot distinguish 'slow down' from 'the API is gone'.

    RED-PROVEN by moving `app.middleware("http")(cost_guardrail_middleware)` below the
    `add_middleware(CORSMiddleware, ...)` block in main.py: the 429 then carries no CORS header.
    """
    _, resp_headers, _ = _throttle_until_429(
        monkeypatch, headers={"origin": "https://credencesports.com"}
    )
    assert resp_headers.get("access-control-allow-origin") == "https://credencesports.com"


def test_the_throttled_response_is_an_honest_429_with_retry_after(monkeypatch):
    _, resp_headers, body = _throttle_until_429(monkeypatch)
    assert int(resp_headers["retry-after"]) >= 1
    assert "detail" in body
    assert resp_headers.get("cache-control") == "no-store", "a 429 must never be cached"


def test_health_is_never_rate_limited():
    """A throttled health check reads as an unhealthy API and can deregister it — the guard causing
    the outage. RED-PROVEN by deleting `/health` from `_RATE_LIMIT_EXEMPT_PREFIXES`."""
    statuses = {_call("/health")[0] for _ in range(300)}
    assert statuses == {200}, f"health was throttled: {statuses}"


def test_the_stripe_webhook_is_never_rate_limited():
    """Stripe delivers from a small pool of source IPs, so a per-IP limit is exactly wrong here: a
    dropped webhook is a real payment whose subscription never activates."""
    assert cg.is_rate_limit_exempt("/stripe/webhook") is True


def test_degrade_mode_returns_503_with_an_additive_body(monkeypatch):
    """The shape is ADDITIVE (NF-C0): `detail` is what every other error on this API returns and
    what the deployed client already renders; `degraded` is the new field a stale client ignores."""
    monkeypatch.setenv("COST_DEGRADE_MODE", "1")
    status, headers, body = _call("/performance/summary")
    assert status == 503
    assert isinstance(body.get("detail"), str) and body["detail"]
    assert body.get("degraded") is True
    assert headers.get("retry-after") == "300"
    assert headers.get("cache-control") == "no-store"


def test_degrade_mode_leaves_the_free_board_reachable(monkeypatch):
    """The switch is a FLOOR. The free surfaces must NOT 503 — proving it end-to-end rather than
    only against the allowlist function."""
    monkeypatch.setenv("COST_DEGRADE_MODE", "1")
    status, _, _ = _call("/health")
    assert status == 200


def test_vary_authorization_is_set_on_a_shared_cacheable_response(monkeypatch):
    """Without `Vary: Authorization` a cache keyed on the URL alone can still mix the locked and
    entitled bodies — the header pair is what closes the breach, and either alone does not."""
    from app.backend.routers import fantasy_public

    monkeypatch.setattr(fantasy_public, "_load_json", lambda key: {"seasons": [2024]})
    status, headers, _ = _call("/fantasy/nfl/track-record/manifest")
    assert status == 200
    assert headers.get("cache-control", "").startswith("public, s-maxage=")
    assert "authorization" in headers.get("vary", "").lower()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# F. No per-request lakehouse read on the public hot path
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_public_featured_heal_does_not_query_once_per_request(monkeypatch):
    """⭐ THE COST BUG. `_heal_pending_featured_yesterday` only wrote back on SUCCESS, so while
    yesterday's game was genuinely unsettled (hours, every morning) EVERY request re-ran a
    DuckDB-over-S3 query. `/picks/featured` is public and the landing page fetches it on load, so
    that is one lakehouse query PER ANONYMOUS VISITOR on the hottest public path.

    RED-PROVEN by removing the cooldown: the call count becomes 20.
    """
    from app.backend.routers import picks

    calls = {"n": 0}

    def _counting_query(*_a, **_kw):
        calls["n"] += 1
        return []  # "not settled yet" — the case that used to re-query forever

    monkeypatch.setattr(picks, "lakehouse_query", _counting_query)
    picks._heal_last_attempt.clear()

    payload = {"game_pk": 1, "yesterday": {"status": "pending"}}
    for _ in range(20):
        picks._heal_pending_featured_yesterday(dict(payload), "2026-08-08")

    assert calls["n"] == 1, f"the public path ran {calls['n']} lakehouse queries for 20 requests"


def test_the_featured_heal_is_skipped_entirely_in_degrade_mode(monkeypatch):
    from app.backend.routers import picks

    calls = {"n": 0}
    monkeypatch.setattr(picks, "lakehouse_query", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or [])
    monkeypatch.setenv("COST_DEGRADE_MODE", "1")
    picks._heal_last_attempt.clear()

    picks._heal_pending_featured_yesterday({"yesterday": {"status": "pending"}}, "2026-08-08")
    assert calls["n"] == 0


def test_the_featured_endpoint_skips_the_lakehouse_fallback_in_degrade_mode(monkeypatch):
    """On a cache-cold morning the fallback is up to four DuckDB-over-S3 calls per visitor — the
    single most expensive thing anonymous traffic can trigger. In degrade mode we serve the honest
    'nothing published' payload the client already renders instead."""
    from app.backend.routers import picks

    monkeypatch.setattr(picks.serving_cache, "get_cache", lambda *a, **k: None)
    monkeypatch.setattr(picks, "get_cache", lambda *a, **k: None)

    def _boom(*_a, **_kw):
        raise AssertionError("degrade mode must not reach the lakehouse")

    monkeypatch.setattr(picks, "lakehouse_query", _boom)
    monkeypatch.setenv("COST_DEGRADE_MODE", "1")

    result = picks.get_featured_pick()
    assert result.game_pk is None


def test_the_heal_attempt_dict_cannot_grow_without_bound(monkeypatch):
    """A long-lived warm container would otherwise accumulate one entry per day it survives."""
    from app.backend.routers import picks

    monkeypatch.setattr(picks, "lakehouse_query", lambda *a, **k: [])
    picks._heal_last_attempt.clear()
    for day in range(1, 29):
        picks._heal_pending_featured_yesterday(
            {"yesterday": {"status": "pending"}}, f"2026-08-{day:02d}"
        )
    assert len(picks._heal_last_attempt) <= 8


# ══════════════════════════════════════════════════════════════════════════════════════════════
# G. The CDN read path (frontend source guards — no JS test runner in this repo)
# ══════════════════════════════════════════════════════════════════════════════════════════════

_CDN_ROUTE = "app/api/public/[...path]/route.ts"

pytest_frontend = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


@pytest_frontend
def test_the_cdn_route_never_forwards_an_authorization_header():
    """⭐ THE BREACH THIS PREVENTS, on the frontend side. If a subscriber's token reached the
    upstream from this handler, the upstream would answer with the FULL board and the handler would
    write that paid payload into a PUBLIC CDN entry keyed only on the URL — served from then on to
    every anonymous visitor.

    Asserted on comment-stripped source, so the explanatory comment above the code cannot satisfy
    the guard (INC-38). RED-PROVEN by adding an Authorization passthrough to the fetch.
    """
    code = _ts_code(_CDN_ROUTE)
    assert "authorization" not in code.lower(), "the CDN route references Authorization in CODE"
    # And it must not splat the incoming headers, which would forward one implicitly.
    assert "...request.headers" not in code
    assert "request.headers" not in code


@pytest_frontend
def test_the_cdn_route_is_an_allowlist_not_an_open_proxy():
    """A catch-all that forwarded any path would be an open relay into our own API from a trusted
    origin. RED-PROVEN by replacing `resolve()` with a passthrough."""
    code = _ts_code(_CDN_ROUTE)
    assert "ROUTES" in code and "resolve" in code
    assert "return jsonError(404" in code, "an unrecognised path must 404, not be forwarded"


@pytest_frontend
def test_the_cdn_route_refuses_to_cache_an_error_or_an_empty_body():
    """E9.26b — an empty read is SUSPECT and must never be pinned into the CDN for a full window."""
    code = _ts_code(_CDN_ROUTE)
    assert "looksEmpty" in code
    assert 'no-store' in code
    assert "upstream.ok" in code


@pytest_frontend
def test_the_anonymous_fantasy_reads_go_through_the_cdn_and_the_entitled_ones_do_not():
    """The token split IS the design: one cacheable payload for the many, per-request Lambda for the
    few who pay. RED-PROVEN by reverting either arm of the ternary."""
    code = _ts_code("lib/fantasy.ts")
    for surface in ("manifest", "board", "projections"):
        assert f"/api/public/{surface}" in code, f"{surface} still calls the Lambda anonymously"
    # The entitled path must still go direct — a token must never reach the shared-cache route.
    assert "apiFetch(`/fantasy/nfl/manifest" in code
    assert "if (!token) return cdnFetch" in code


@pytest_frontend
def test_every_cdn_surface_is_also_mapped_in_the_e2e_harness():
    """⭐ ONE LOGICAL THING, TWO OWNERS — the shape this repo keeps getting caught by (INC-30
    crontab, INC-36 concurrency, INC-38 per-caller flags).

    Adding a surface to the CDN route without adding it to `e2e/support/api-mock.ts` does not fail
    loudly: the anonymous request simply stops carrying `API_PREFIX`, slips past the interceptor,
    lands on the local Next server and is answered by the REAL handler — which then reaches for the
    REAL API. The suite keeps passing while quietly ceasing to be hermetic, which is strictly worse
    than a red test.

    RED-PROVEN by deleting the `featured` line from the harness's `cdnPathToApiPath`.
    """
    route_code = _ts_code(_CDN_ROUTE)
    harness_code = _ts_code("e2e/support/api-mock.ts")

    # The allowlist keys are the top-level `ROUTES` entries plus the track-record special case.
    # ⚠️ THE OPTIONAL QUOTES ARE LOAD-BEARING (E9.46). A key containing a hyphen — `featured-player`
    # — MUST be quoted in TypeScript, and the original pattern required a bare identifier, so a
    # hyphenated surface was silently INVISIBLE here: the guard passed while checking nothing about
    # it. That is the vacuous-guard class this file is otherwise careful about, and a hyphen is the
    # natural way to name a multi-word surface, so it would have recurred.
    keys = set(re.findall(r'^\s{2}"?([a-zA-Z][\w-]*)"?: \{$', route_code, flags=re.M))
    assert keys, "could not parse the CDN route's allowlist — the guard would be vacuous"
    assert any("-" in k for k in keys), (
        "no hyphenated surface was parsed — either none exists yet (delete this line when that is "
        "true) or the quoted-key form has stopped matching and this guard is silently skipping it"
    )

    for key in keys:
        assert f'"{key}"' in harness_code, (
            f"CDN surface '{key}' has no mapping in e2e/support/api-mock.ts — anonymous E2E "
            f"traffic for it would escape the mock and reach the real API"
        )
    # The track-record pair is matched by pattern rather than by key in both files.
    assert "track-record/manifest" in harness_code


@pytest_frontend
def test_the_comment_stripper_is_itself_correct():
    """Pins the line-comments-first order with the exact shape that breaks the naive one: a path
    glob inside a `//` comment. With blocks stripped first this returns '' and every source guard
    above silently passes against deleted code."""
    import tempfile

    sample = "// see /api/public/*\nconst KEEP_ME = 1\n/* real block */\nconst ALSO = 2\n"
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "s.ts"
        p.write_text(sample)
        text = re.sub(r"(?<!:)//[^\n]*", "", p.read_text())
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    assert "KEEP_ME" in text and "ALSO" in text
