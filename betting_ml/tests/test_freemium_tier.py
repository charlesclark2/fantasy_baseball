"""FREEMIUM BUILD — the free/paid boundary as executable clauses.

THE STORY'S ACCEPTANCE CRITERION IS "the split is pinned in a test, not vibes" (the E9.56b
discipline), and this file is that pin. It asserts the boundary from BOTH sides, because each
direction fails in a different way and neither failure raises:

  • A GATED SURFACE THAT QUIETLY BECOMES FREE gives away the paid product. Nothing errors — it
    renders perfectly, for everyone.
  • A FREE SURFACE THAT QUIETLY BECOMES GATED breaks the funnel. Also nothing errors: the visitor
    is redirected or shown an empty state, which reads as "we haven't published this" rather than
    as a gate, and it is invisible to anyone already logged in as a subscriber (i.e. to us).

⭐ THE NO-REGRESSION HALF IS NOT OPTIONAL. Without `test_the_personalization_endpoints_still_403_*`
and `test_personalization_and_decision_pages_stay_gated`, a change that made EVERYTHING free would
satisfy every "the free board is visible" assertion here and the suite would be green with the
business given away. The same shape E9.56's own suite guarded against, pointing the other way.

⚠️ AND-COMPOSED CLAUSES GET ONE ISOLATING FIXTURE EACH (NF-D17 §7, which shipped broken in that
story's first cut). Where a rule is a conjunction, the fixture satisfies every OTHER clause so only
the named one can flip the result — a fixture that trips two clauses tests neither, because the
first refusal hides the second.

⚠️ EVERY SOURCE ASSERTION STRIPS COMMENTS FIRST. Without it, the explanatory comment written above
each change would satisfy the guard with the change DELETED — the INC-38 "prose cannot satisfy a
source guard" landmine, which this repo has already shipped once. ⭐ And `//` line comments are
stripped BEFORE `/* */` blocks: doing it the other way lets a path glob inside a line comment eat
everything to the next `*/` and silently blank whole regions of scanned source.

RED-PROVEN against deliberately-broken source:
`uv run python betting_ml/tests/freemium_tier_red_proof.py`.

Pure/offline (fast gate): source inspection plus the real ASGI app with only its two IO boundaries
(the S3 read, the JWKS fetch) stubbed. No DuckDB, no S3, no network.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from app.backend.services import entitlement
from app.backend.services.entitlement import Capability

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


def _code(rel: str) -> str:
    """Frontend source with comments stripped — see the module docstring for why, and for why the
    line-comment pass runs FIRST."""
    text = (_FRONTEND / rel).read_text()
    text = "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The capability map — the boundary itself
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_every_capability_is_placed_on_exactly_one_side():
    """⭐ THE CLAUSE THAT MAKES A NEW CAPABILITY A DECISION RATHER THAN A DEFAULT.

    The sets are written out longhand rather than derived from each other, so a capability added to
    the enum belongs to NEITHER until someone places it — and this goes red. Spelled the obvious way
    (`PAID = all - FREE`) a forgotten capability silently becomes paid; spelled the other way it
    silently becomes free. Neither default is acceptable, and being forced to choose is the point.
    """
    placed = entitlement.FREE_CAPABILITIES | entitlement.PAID_CAPABILITIES
    assert placed == set(Capability), (
        f"unplaced capabilities: {set(Capability) - placed} — add each to FREE_CAPABILITIES or "
        f"PAID_CAPABILITIES; leaving one out makes its gate whichever the code happens to default to"
    )
    assert not (entitlement.FREE_CAPABILITIES & entitlement.PAID_CAPABILITIES), (
        "a capability is in BOTH sets — `allows` short-circuits on FREE, so it is silently free"
    )


def test_the_generic_board_is_free_and_the_other_two_are_paid():
    """The boundary, stated as the operator stated it: 'free tells you what Credence thinks; a
    membership helps you decide.'"""
    assert entitlement.FREE_CAPABILITIES == {Capability.GENERIC_BOARD}
    assert entitlement.PAID_CAPABILITIES == {
        Capability.PERSONALIZATION,
        Capability.DECISION_SUPPORT,
    }


def test_an_anonymous_caller_gets_the_generic_board_and_nothing_else():
    assert entitlement.allows(Capability.GENERIC_BOARD, None) is True
    assert entitlement.allows(Capability.PERSONALIZATION, None) is False
    assert entitlement.allows(Capability.DECISION_SUPPORT, None) is False


def test_a_subscriber_gets_both_halves():
    """The no-regression direction on the capability map itself: a rule that refused EVERYONE would
    pass the clause above."""
    sub = entitlement.Entitlement(fantasy=True, source="gateway")
    for cap in Capability:
        assert entitlement.allows(cap, sub) is True, f"a subscriber lost {cap}"


def test_a_signed_in_caller_without_fantasy_is_treated_as_free_not_as_entitled():
    """A `beta_tester` has betting access and no fantasy — the tier must key on the fantasy
    entitlement, not on 'is logged in'. Getting this wrong hands the paid half to every account."""
    logged_in = entitlement.Entitlement(user_id="u1", groups=("beta_tester",), fantasy=False,
                                        source="gateway")
    assert entitlement.allows(Capability.GENERIC_BOARD, logged_in) is True
    assert entitlement.allows(Capability.PERSONALIZATION, logged_in) is False


def test_an_unplaced_capability_fails_closed():
    """`allows` must refuse something it does not recognise. Fails CLOSED because a refused paid
    surface is visible and reversible, and a leaked one is not."""
    assert entitlement.allows("some_future_capability", None) is False  # type: ignore[arg-type]
    assert (
        entitlement.allows(
            "some_future_capability",  # type: ignore[arg-type]
            entitlement.Entitlement(fantasy=True),
        )
        is False
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The G100-C1 seam — "1 free personalized league", now FLIPPED ON
# ══════════════════════════════════════════════════════════════════════════════════════════════
# 🗄️ THIS SECTION USED TO ASSERT THE QUOTA WAS ZERO. That pin existed so raising it would be a
# deliberate, reviewed edit rather than a default drifting in — and it did its job: G100-C1
# (2026-08-08) is the reviewed edit, and this is what it looks like on the other side. The behaviour
# of the free tier is exercised in `test_g100_c1_free_league.py`; what stays HERE is the boundary
# this story drew, which G100-C1 built inside rather than replaced.


def test_the_free_personalized_league_quota_is_one():
    """⭐ G100-C1 raised this 0 → 1, and it is still pinned — in the other direction now.

    The number is the whole free tier, so it must not drift again. If this goes red, someone has
    changed how many leagues a free account gets, which is a pricing decision.
    """
    assert entitlement.FREE_PERSONALIZED_LEAGUE_QUOTA == 1
    assert entitlement.personalized_league_quota(None) == 1


def test_the_quota_is_a_count_so_one_free_league_was_expressible():
    """⭐ WHY A COUNT AND NOT A BOOLEAN — vindicated. A `free_personalization: bool` could not have
    expressed 'one league but not five', so G100-C1 would have had to REPLACE the predicate, and
    replacing an entitlement predicate is exactly when a surface quietly falls out of its gate.
    Because it was a count, the whole flip was ONE literal and no gate was rewritten."""
    assert isinstance(entitlement.FREE_PERSONALIZED_LEAGUE_QUOTA, int)
    sub_quota = entitlement.personalized_league_quota(entitlement.Entitlement(fantasy=True))
    assert sub_quota > entitlement.FREE_PERSONALIZED_LEAGUE_QUOTA, (
        "a subscriber's quota must exceed the free tier's"
    )


def test_personalization_is_still_a_paid_capability_after_the_free_grant():
    """⛔ THE DISTINCTION THE WHOLE STORY RESTS ON. A free account may KEEP one personalized league;
    `Capability.PERSONALIZATION` is still what a membership sells and must stay in PAID_CAPABILITIES.

    The tempting shortcut was to move the capability into `FREE_CAPABILITIES` — one line, and every
    gate would have opened. It would also have freed every OTHER surface that reads the same
    capability, silently, which is why the grant is a quota beside the capability rather than a
    reclassification of it.
    """
    assert entitlement.Capability.PERSONALIZATION in entitlement.PAID_CAPABILITIES
    assert entitlement.Capability.PERSONALIZATION not in entitlement.FREE_CAPABILITIES
    free_caller = entitlement.Entitlement(user_id="u1", fantasy=False, source="gateway")
    assert entitlement.allows(entitlement.Capability.PERSONALIZATION, free_caller) is False
    # …and yet they hold a quota. The two answers differ ON PURPOSE — see `allows_personalization`.
    assert entitlement.allows_personalization(free_caller) is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. End to end through the real ASGI app
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Raw ASGI rather than starlette's TestClient, for the two reasons E9.56's suite documents:
# TestClient needs `httpx` (absent here), and it cannot set the `aws.event` scope key that Mangum
# uses to carry the API Gateway authorizer context — the one thing separating a real subscriber
# from a forged token.

_PLAYERS = [
    {"id": "p1", "name": "Alpha Back", "pos": "RB", "team": "BUF", "bye": 7, "rookie": False,
     "g": 15.5, "fpPpr": 325.7, "fpHalf": 290.1, "fpStd": 255.0, "fpP10": 225.7, "fpP90": 425.7,
     "conf": "high", "uncType": "empirical", "adp": 14.2},
    {"id": "p2", "name": "Beta Wideout", "pos": "WR", "team": "KC", "bye": 10, "rookie": False,
     "g": 16.8, "fpPpr": 281.4, "fpHalf": 250.0, "fpStd": 219.0, "fpP10": 181.4, "fpP90": 381.4,
     "conf": "high", "uncType": "empirical", "adp": 8.1},
]
_PROJECTIONS = {"season": 2026, "generated_at": "2026-08-08T00:00:00Z", "players": _PLAYERS,
                "adp_format": "ppr", "adp_teams": 12}
#: ⚠️ CARRIES A PAID PRESET AND A PAID SIZE ON PURPOSE. A fixture holding only `full_ppr`/12 would
#: make every free-tier assertion below pass vacuously — there would be no paid board to refuse, so
#: deleting the gate entirely would not fail a single test.
_MANIFEST = {"season": 2026, "generated_at": "2026-08-08T00:00:00Z",
             "configs": [{"name": "full_ppr", "label": "Full PPR"},
                         {"name": "half_ppr", "label": "Half PPR"}], "sizes": [10, 12],
             "positions": ["QB", "RB", "WR", "TE"],
             "featureLegend": {"pergame_fp": "Points per game"},
             "projections": {"players": 2, "model_version": "nf1.5b"}}

#: The one free (config, size), and a paid one of each kind — a different FORMAT at the free size,
#: and the free FORMAT at a different size. The second is the one a format-only gate would miss.
_FREE_BOARD_QUERY = "season=2026&config=full_ppr&size=12"
_PAID_FORMAT_QUERY = "season=2026&config=half_ppr&size=12"
_PAID_SIZE_QUERY = "season=2026&config=full_ppr&size=10"
_BOARD = [
    {"id": "p1", "name": "Alpha Back", "pos": "RB", "pts": 325.7, "vor": 88.2, "ovrRank": 1,
     "posRank": 1, "adp": 14.2, "g": 15.5},
    {"id": "p2", "name": "Beta Wideout", "pos": "WR", "pts": 281.4, "vor": 61.0, "ovrRank": 2,
     "posRank": 1, "adp": 8.1, "g": 16.8},
]

#: Values that exist ONLY in the model output, PER ENDPOINT — the projections payload carries no
#: VOR and the board carries no p10/p90, so one shared set would assert a number the endpoint never
#: had and fail for the wrong reason.
_MODEL_NUMBERS = {
    "/fantasy/nfl/projections": {325.7, 281.4, 425.7},
    "/fantasy/nfl/board": {325.7, 281.4, 88.2, 61.0},
}


@pytest.fixture()
def app_env(monkeypatch):
    """Stub ONLY the two IO boundaries. Routing, router dependencies, the entitlement resolver and
    JSON serialization are all the real thing."""
    from app.backend.routers import fantasy
    from app.backend.services import cost_guardrails, jwt_verify

    # ⭐ THE PER-IP RATE LIMITER IS PROCESS-GLOBAL AND STATEFUL, so it carries token depletion ACROSS
    # tests and across FILES. Every `_call` below arrives from the same fake client, so a suite that
    # makes enough requests exhausts the bucket and the NEXT file starts receiving 429s — which
    # surface as `KeyError: 'configs'` and similar, i.e. as assertion failures about payload shape
    # rather than as anything resembling throttling. (Measured: adding `test_g100_c1_free_league.py`
    # ahead of this file turned 17 of its tests red until this reset was added.)
    #
    # The limiter's own behaviour has its own suite; here it must simply not be a hidden dependency
    # between unrelated tests.
    cost_guardrails.get_limiter().reset()


    def fake_load(rel_key: str, sport: str = "nfl"):
        if rel_key.endswith("projections.json"):
            return _PROJECTIONS
        if rel_key.endswith("manifest.json"):
            return _MANIFEST
        if "board_" in rel_key:
            return _BOARD
        return None

    monkeypatch.setattr(fantasy, "_load_json", fake_load)
    # No network. An unreachable JWKS makes every presented token unverifiable, which is both the
    # anonymous path asserted on below and a proof the verifier fails CLOSED when it is unavailable.
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return True


def _call(path: str, query: str = "", *, headers: dict | None = None, aws_event: dict | None = None):
    """Drive the real ASGI app. Returns (status, raw_body_bytes)."""
    import anyio

    from app.backend.main import app

    out: dict = {}
    body_parts: list[bytes] = []

    async def run():
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")]
            + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("test", 1),
            "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    return out["status"], b"".join(body_parts)


def _entitled_event(groups: str = "[subscriber]"):
    """The API Gateway authorizer context as Mangum delivers it — the ONE shape that legitimately
    grants entitlement."""
    return {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": "sub-1",
                                                                "cognito:groups": groups}}}}}


def _unsigned_token(groups: list[str]) -> str:
    """A hand-written JWT with no valid signature. On a gateway-`NONE` route this is exactly what an
    attacker can present."""
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'sub': 'x', 'cognito:groups': groups})}.x"


def _scalars(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _scalars(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _scalars(v)
    else:
        yield obj


@pytest.mark.parametrize(
    "path,query",
    [
        ("/fantasy/nfl/projections", "season=2026"),
        ("/fantasy/nfl/board", "season=2026&config=full_ppr&size=12"),
    ],
)
def test_an_anonymous_caller_gets_the_real_generic_board(app_env, path, query):
    """⭐ THE UN-GATE ITSELF. Pre-freemium these answered an anonymous caller with E9.56's locked
    payload — every model value removed, `locked: true` in its place. The free board IS the wedge,
    so the numbers have to be there."""
    status, raw = _call(path, query)
    assert status == 200
    numbers = {v for v in _scalars(json.loads(raw)) if isinstance(v, float)}
    assert _MODEL_NUMBERS[path] <= numbers, (
        "the anonymous generic board is missing model values — it is still being redacted"
    )


def test_an_anonymous_board_is_still_a_bare_list(app_env):
    """NF-C0: the deployed client indexes `/board` directly, so wrapping it in an envelope is the
    blank-screen break. Free or locked, the container type never changes."""
    status, raw = _call("/fantasy/nfl/board", "season=2026&config=full_ppr&size=12")
    assert status == 200 and isinstance(json.loads(raw), list)


def test_the_anonymous_projections_payload_declares_itself_unlocked(app_env):
    """The deployed frontend branches on `locked`/`entitled`, and the API Lambda ships only via a
    manual `deploy.sh` — so these keys must keep arriving (additive, NF-C0/E9.41), now saying
    `false`/`true` rather than disappearing."""
    _, raw = _call("/fantasy/nfl/projections", "season=2026")
    body = json.loads(raw)
    assert body["locked"] is False and body["entitled"] is True


def test_no_row_carries_a_lock_marker_on_the_free_board(app_env):
    """A stray `locked: true` would make the UI render a subscribe chip over a value it HAS —
    a paywall on free content, which converts nobody and looks broken."""
    _, raw = _call("/fantasy/nfl/projections", "season=2026")
    assert not any(p.get("locked") for p in json.loads(raw)["players"])


@pytest.mark.parametrize(
    "path,query",
    [
        ("/fantasy/nfl/projections", "season=2026"),
        ("/fantasy/nfl/manifest", "season=2026"),
        ("/fantasy/nfl/board", "season=2026&config=full_ppr&size=12"),
    ],
)
def test_the_free_generic_board_is_byte_identical_for_every_caller(app_env, path, query):
    """⭐⭐ THE INVARIANT THREE OTHER SYSTEMS REST ON, asserted as literal byte equality rather than
    as 'both look right'.

    ⚠️ SCOPED TO THE *FREE* URLS since the tier narrowed to one preset (2026-08-08). A PAID board URL
    is deliberately caller-dependent (200 or 403), which is why the CDN allowlist cannot reach one —
    see `test_the_cdn_route_can_only_ask_for_the_free_board`.

    Because these responses cannot vary by caller: G100-D1's CDN route may cache ONE copy for
    everybody; `cost_guardrails.cache_control_for`'s 'same URL, two bodies' hazard cannot arise
    here; and the frontend's `entitled`-keyed query cache can never strand a new subscriber on a
    stale view. Re-introducing any per-caller variation invalidates all three AT ONCE and would need
    the CDN allowlist, the backend cache rules and the query keys revisited together — so the
    cheapest place to notice is here.

    A forged `subscriber` token is included deliberately: with the gateway authorizer off these
    routes are anonymously reachable, so an attacker-controlled token must buy exactly nothing.
    """
    _, anon = _call(path, query)
    _, forged = _call(path, query,
                      headers={"Authorization": "Bearer " + _unsigned_token(["subscriber", "admin"])})
    _, subscriber = _call(path, query, aws_event=_entitled_event())

    assert anon == subscriber, "a subscriber's generic payload differs from an anonymous one"
    assert anon == forged, "a forged token changed the generic payload"


def test_the_free_board_is_free_for_a_past_season_too(app_env):
    """The NF3.2 receipts rule survives: nothing about the freemium build re-gates history."""
    status, raw = _call("/fantasy/nfl/projections", "season=2025")
    assert status == 200 and json.loads(raw)["locked"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3b. ONE preset is free — the other thirteen are the membership (operator decision 2026-08-08)
# ══════════════════════════════════════════════════════════════════════════════════════════════
# `Capability.GENERIC_BOARD` says a caller may read the generic board; `FREE_BOARD_CONFIG`/
# `FREE_BOARD_SIZE` say WHICH one. Both halves need pinning, and the size half is the one an
# implementation naturally forgets: locking the format alone still offers `full_ppr`/10, a board the
# API refuses, so the picker would present a combination that cannot load.


def test_the_free_preset_is_full_ppr_at_twelve_teams():
    """The paywall itself, as a literal. ⭐ The reason it is THIS preset is a data fact, not a taste:
    the ADP column shown beside our number is an FFC 12-team PPR sample, so at any other preset the
    two columns describe different leagues. Moving this constant means moving that sample."""
    assert entitlement.FREE_BOARD_CONFIG == "full_ppr"
    assert entitlement.FREE_BOARD_SIZE == 12


@pytest.mark.parametrize(
    "config,size,expected",
    [
        ("full_ppr", 12, True),
        ("half_ppr", 12, False),  # a paid FORMAT at the free size
        ("full_ppr", 10, False),  # the free format at a paid SIZE — the easy one to miss
        ("superflex", 10, False),
    ],
)
def test_only_the_one_preset_is_free(config, size, expected):
    """⚠️ BOTH coordinates matter. League size sets the replacement level, so `full_ppr`/10 is a
    different set of numbers rather than a relabelling of the free board."""
    assert entitlement.is_free_board(config, size) is expected


def test_an_unparseable_size_is_not_the_free_board():
    """Fail closed on junk: an unparseable size must not fall through to 'free'."""
    assert entitlement.is_free_board("full_ppr", None) is False
    assert entitlement.is_free_board("full_ppr", "twelve") is False


def test_a_paid_preset_needs_entitlement_and_the_free_one_never_does():
    ent = entitlement.Entitlement(fantasy=True, source="gateway")
    assert entitlement.allows_board("half_ppr", 12, None) is False
    assert entitlement.allows_board("half_ppr", 12, ent) is True
    assert entitlement.allows_board("full_ppr", 12, None) is True


@pytest.mark.parametrize("query", [_PAID_FORMAT_QUERY, _PAID_SIZE_QUERY])
def test_an_anonymous_caller_is_refused_a_paid_preset(app_env, query):
    """⭐ THE CLAUSE THAT STOPS 'MAKE EVERYTHING FREE' FROM SATISFYING THIS FILE, at the format
    grain. 403 rather than a redacted 200: the E9.56 lock existed to draw a per-cell CTA on a board
    the visitor was looking at, and here the client keeps them on the free board instead."""
    status, _ = _call("/fantasy/nfl/board", query)
    assert status == 403, "a paid preset is reachable anonymously"


@pytest.mark.parametrize("query", [_PAID_FORMAT_QUERY, _PAID_SIZE_QUERY])
def test_a_subscriber_gets_a_paid_preset(app_env, query):
    """The other side — a gate that refused EVERYONE would pass the test above."""
    status, _ = _call("/fantasy/nfl/board", query, aws_event=_entitled_event())
    assert status == 200, "a subscriber lost a preset they pay for"


@pytest.mark.parametrize("query", [_PAID_FORMAT_QUERY, _PAID_SIZE_QUERY])
def test_a_forged_token_does_not_unlock_a_paid_preset(app_env, query):
    """With the gateway authorizer set to NONE on these routes the Bearer token is
    attacker-controlled, so `jwt_verify` — not the presence of a token — is what grants a preset."""
    status, _ = _call(
        "/fantasy/nfl/board",
        query,
        headers={"Authorization": "Bearer " + _unsigned_token(["subscriber", "admin"])},
    )
    assert status == 403, "a forged token bought a paid preset"


def test_a_signed_in_non_subscriber_is_refused_a_paid_preset(app_env):
    """A real, gateway-validated account with no fantasy entitlement is on the FREE tier — the
    third caller class, and the one a naive `has a token ⇒ entitled` check would let through."""
    status, _ = _call(
        "/fantasy/nfl/board", _PAID_FORMAT_QUERY, aws_event=_entitled_event(groups="[beta_tester]")
    )
    assert status == 403


def test_a_junk_config_reads_the_same_to_everyone(app_env):
    """A malformed `config` must be rejected on its syntax BEFORE entitlement is consulted, or the
    status code leaks the caller's tier on a request that was never valid for anybody."""
    bad = "season=2026&config=NOT-A-CONFIG&size=12"
    anon, _ = _call("/fantasy/nfl/board", bad)
    sub, _ = _call("/fantasy/nfl/board", bad, aws_event=_entitled_event())
    assert anon == sub == 422


def test_neither_answer_to_a_paid_board_is_shared_cacheable():
    """⭐ THE COST-GUARDRAIL CONSEQUENCE OF MAKING A ROUTE CALLER-DEPENDENT, checked rather than
    assumed. `cost_guardrails.cache_control_for` is keyed on the PATH — it cannot see `config` — so
    `/fantasy/nfl/board` has one caching rule covering both the free preset and the paid ones, and
    the paid ones now answer 200-or-403 depending on who asks. That is precisely the 'same URL, two
    bodies' shape G100-D1 exists to prevent.

    It is safe, but for two SEPARATE pre-existing reasons, and the point of this clause is that
    losing either one is a paid-data breach rather than a caching regression:
      · a subscriber's request carries `Authorization` ⇒ `private`, so their 200 is never shared;
      · an anonymous request gets 403 ⇒ non-200 ⇒ `no-store`, so the refusal is never pinned into
        the edge and served to subscribers.
    Remove the status check and every subscriber gets a cached 403; remove the authorization check
    and every anonymous visitor gets a cached paid board.
    """
    from app.backend.services import cost_guardrails as cg

    assert cg.cache_control_for(
        "/fantasy/nfl/board", has_authorization=True, status_code=200
    ) == cg.PRIVATE_CACHE_CONTROL
    assert cg.cache_control_for(
        "/fantasy/nfl/board", has_authorization=False, status_code=403
    ) == "no-store"


def test_the_manifest_marks_exactly_the_free_preset(app_env):
    """The client cannot draw the boundary it cannot see. The manifest is where the paywall is
    stated to the frontend — deriving it there from a hardcoded format name would put the same fact
    in two places, and only one of them deploys with `deploy.sh`."""
    _, raw = _call("/fantasy/nfl/manifest", "season=2026")
    body = json.loads(raw)
    free = {c["name"] for c in body["configs"] if c.get("free")}
    assert free == {entitlement.FREE_BOARD_CONFIG}
    assert body["freeBoard"] == {
        "config": entitlement.FREE_BOARD_CONFIG,
        "size": entitlement.FREE_BOARD_SIZE,
    }


def test_the_manifest_marking_is_purely_additive(app_env):
    """NF-C0: the deployed client knows neither key. Adding them must not rename, drop or reorder
    anything it does read — a response-shape break here is a 200 with a blank screen."""
    _, raw = _call("/fantasy/nfl/manifest", "season=2026")
    body = json.loads(raw)
    for key, value in _MANIFEST.items():
        if key == "configs":
            continue
        assert body[key] == value, f"the manifest lost or changed {key!r}"
    assert [c["name"] for c in body["configs"]] == [c["name"] for c in _MANIFEST["configs"]]
    for served, original in zip(body["configs"], _MANIFEST["configs"]):
        assert served["label"] == original["label"]


# ── the no-regression half: what must STAY paid ───────────────────────────────────────────────


#: The personalization reads. ⚠️ G100-C1 changed WHO may reach these — see below.
_PERSONALIZATION_PATHS = [("/fantasy/nfl/my-teams", "season=2026"), ("/fantasy/leagues", "")]


@pytest.mark.parametrize("path,query", _PERSONALIZATION_PATHS)
def test_a_signed_in_free_account_reaches_personalization_with_a_quota_of_one(app_env, path, query):
    """🗄️ THIS CLAUSE USED TO ASSERT 403, AND G100-C1 (2026-08-08) IS WHY IT NO LONGER DOES.

    When the freemium boundary was drawn, `Capability.PERSONALIZATION` had no free form at all and
    these endpoints refused every non-entitled caller outright. G100-C1 grants a free account ONE
    personalized league, so a validated-but-unentitled caller now reaches them and is served their
    own single league.

    ⛔ THE CAPABILITY IS STILL PAID. What changed is a QUOTA, not the tier — see
    `test_personalization_is_still_a_paid_capability_after_the_free_grant` above, and
    `test_g100_c1_free_league.py` for the cap that keeps it at one. The no-regression half this
    clause carries moved to the two tests below, which is where it still has teeth.
    """
    status, _ = _call(path, query, aws_event=_entitled_event(groups="[beta_tester]"))
    assert status == 200, f"{path} refuses a signed-in free account its one league"


@pytest.mark.parametrize("path,query", _PERSONALIZATION_PATHS)
def test_personalization_is_still_refused_when_the_free_quota_is_withdrawn(
    app_env, path, query, monkeypatch
):
    """⭐ WITHOUT THIS THE WHOLE FILE IS SATISFIED BY MAKING EVERYTHING FREE.

    The clause above no longer discriminates on its own — after G100-C1 it passes just as well
    against a server with no gate at all. What still discriminates is the quota: set it to 0 (the
    operator's one-flip withdrawal of the free tier) and an unentitled caller must be refused
    again, which proves the gate is READING the quota rather than waving everyone through.
    """
    monkeypatch.setattr(entitlement, "FREE_PERSONALIZED_LEAGUE_QUOTA", 0)
    status, _ = _call(path, query, aws_event=_entitled_event(groups="[beta_tester]"))
    assert status == 403, f"{path} served personalization with the free quota withdrawn"


def test_the_personalization_endpoints_still_serve_an_entitled_caller(app_env):
    """The other side of the clause above — a gate that refused EVERYONE would satisfy it."""
    status, _ = _call("/fantasy/nfl/my-teams", "season=2026", aws_event=_entitled_event())
    assert status != 403, "a subscriber lost access to their own leagues"


def test_an_anonymous_caller_cannot_reach_personalization_at_all(app_env):
    status, _ = _call("/fantasy/nfl/my-teams", "season=2026")
    assert status in (401, 403), "anonymous reached a personalization endpoint"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The frontend mirrors the same split
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: The free surfaces, as page files. ⭐ A NAMED GUARD makes this set enumerable in one grep; guard
#: OMISSION is not greppable (you would have to search for the ABSENCE of a wrapper), and the entire
#: risk on this story is a gated page quietly becoming public.
_PUBLIC_PAGES = {
    "app/fantasy/projections/page.tsx",
    "app/fantasy/rankings/page.tsx",
    "app/fantasy/players/page.tsx",
}

#: PERSONALIZATION + DECISION SUPPORT. Listed per page so a failure names the surface that leaked.
_GATED_PAGES = [
    "app/fantasy/my-teams/page.tsx",
    "app/fantasy/league-settings/page.tsx",
    "app/fantasy/import/page.tsx",
    "app/fantasy/draft/page.tsx",
    # NF-C2.1 — the mock draft reads the SAME 403-ing gated board endpoints as the live tool,
    # so a public wrapper here would render a permanently broken page, not a free one.
    "app/fantasy/mock-draft/page.tsx",
    # NF-C5 — the auction optimizer reads the SAME gated board endpoints as the snake tool and is
    # the same paid decision-support half by product decision.
    "app/fantasy/auction/page.tsx",
    "app/fantasy/league-board/page.tsx",
    "app/fantasy/mlb/prospects/page.tsx",
]


def _pages_using(guard: str) -> set[str]:
    return {
        str(p.relative_to(_FRONTEND)).replace("\\", "/")
        for p in (_FRONTEND / "app").rglob("page.tsx")
        if re.search(rf"<{guard}\b", _code(str(p.relative_to(_FRONTEND))))
    }


def test_exactly_the_generic_board_pages_are_public():
    assert _pages_using("FantasyPublicGuard") == _PUBLIC_PAGES


@pytest.mark.parametrize("page", _GATED_PAGES)
def test_personalization_and_decision_pages_stay_gated(page):
    """These have no free form — their endpoints 403 a free caller, or (the draft optimizer) they
    are the paid half by product decision. Making one public renders a permanently broken page at
    best, and exposes a user's own league data at worst."""
    code = _code(page)
    assert "FantasyPublicGuard" not in code, f"{page} became PUBLIC"
    # `FantasyLeagueGuard` (G100-C1) joins the list: signed in + a personalization quota above
    # zero. It is a GATE, not an exemption — an anonymous visitor is still bounced — and the pages
    # behind it are still refused server-side when the quota is withdrawn. What it is NOT is
    # `FantasyPublicGuard`, which is the assertion above and the one that matters here.
    assert re.search(r"<(FantasyGuard|FantasyBetaGuard|FantasyLeagueGuard|AdminGuard)\b", code), (
        f"{page} lost its guard entirely"
    )


def test_the_nav_marks_exactly_the_public_surfaces_public():
    """A public page the nav still hides is reachable only by typing the URL; a gated page the nav
    advertises is a click straight into a redirect."""
    code = _code("lib/nav-model.ts")
    for key in ("fantasy-rankings", "fantasy-projections", "fantasy-players"):
        line = next(ln for ln in code.splitlines() if f'key: "{key}"' in ln)
        assert "public: true" in line, f"{key} is a free surface but the nav still gates it"
    for key in ("fantasy-league-board", "fantasy-draft", "fantasy-mock-draft", "fantasy-auction",
                "fantasy-my-teams", "fantasy-import", "fantasy-league-settings"):
        lines = [ln for ln in code.splitlines() if f'key: "{key}"' in ln]
        if lines:
            assert "public: true" not in lines[0], f"{key} is paid but the nav marks it public"


def test_the_frontend_capability_sets_mirror_the_backend():
    """⚠️ ONE LOGICAL THING, TWO OWNERS (the INC-38 shape). A UI that believes a surface is free
    while the API 403s it renders a permanently broken page with no error anywhere — and the reverse
    hides a surface the caller is paying for. Set equality, both directions."""
    code = _code("lib/entitlements.ts")
    for const, expected in (
        ("FREE_CAPABILITIES", entitlement.FREE_CAPABILITIES),
        ("PAID_CAPABILITIES", entitlement.PAID_CAPABILITIES),
    ):
        m = re.search(rf"{const}:[^=]*=\s*\[(.*?)\]", code, re.S)
        assert m, f"{const} not found in lib/entitlements.ts"
        assert set(re.findall(r'"([a-z_]+)"', m.group(1))) == {c.value for c in expected}, (
            f"{const} has drifted from the backend's set"
        )


def test_the_cdn_route_can_only_ask_for_the_free_board():
    """⭐ THE EDGE MUST NOT BE ABLE TO ASK A CALLER-DEPENDENT QUESTION.

    The public CDN handler strips `Authorization` unconditionally (its property 1), so any board it
    fetches is fetched ANONYMOUSLY — and since the tier narrowed, a paid preset answers 403 to an
    anonymous caller. Left proxyable, a subscriber's request for `half_ppr` would mint a public CDN
    entry containing a 403 and serve it to every subscriber for the rest of the window. Pinning the
    `config`/`size` patterns to the free selection removes the possibility rather than relying on
    the client never to ask.

    Read from the route source and compared against the BACKEND constants, so a one-sided edit to
    either owner goes red (INC-38: one logical thing, two owners)."""
    code = _code("app/api/public/[...path]/route.ts")
    m = re.search(r"board:\s*\{(.*?)\n  \}", code, re.S)
    assert m, "the board entry is no longer recognisable in the CDN allowlist"
    entry = m.group(1)
    assert f"/^{entitlement.FREE_BOARD_CONFIG}$/" in entry, (
        "the CDN board route accepts a config other than the free preset"
    )
    assert f"/^{entitlement.FREE_BOARD_SIZE}$/" in entry, (
        "the CDN board route accepts a size other than the free one"
    )


def test_the_picker_disables_every_paid_preset_for_an_unentitled_caller():
    """Asserted on the RENDER, not on the import: a file that still imports the lock copy while
    handing `Picker` an unconditional option list passes any name-in-file grep. The claim here is
    that `disabled` is wired to the lock state on BOTH controls."""
    code = _code("components/fantasy/shared.tsx")
    start = code.index("export function FormatSelector")
    end = code.index("export function PositionTabs")
    body = code[start:end]
    assert "lockFormats = !entitled" in body, "the picker no longer derives a lock state"
    # Two controls, two independent locks — the size lock is the one an implementation forgets.
    assert body.count("disabled: locked") == 2, (
        "a format/size control stopped disabling its paid options"
    )
    assert re.search(r"locked\s*=\s*lockFormats\s*&&\s*!isFreeConfig\(c\)", body), (
        "the format options are no longer locked by the manifest's own `free` marking"
    )
    assert re.search(r"locked\s*=\s*lockFormats\s*&&\s*n\s*!==\s*free!\.size", body), (
        "the size options are no longer locked against the free size"
    )


def test_a_locked_preset_is_listed_rather_than_removed():
    """⚠️ THE OPPOSITE FAILURE, and the more tempting fix. Dropping the paid presets from the picker
    would satisfy 'an unentitled caller cannot select one' completely — and would make the free
    board look like the only board we publish, which is both untrue and the reverse of what an
    upgrade prompt is for. The list stays whole; the options go disabled."""
    code = _code("components/fantasy/shared.tsx")
    start = code.index("export function FormatSelector")
    end = code.index("export function PositionTabs")
    body = code[start:end]
    assert "manifest.configs.map(" in body, "the picker no longer offers every exported preset"
    assert not re.search(r"manifest\.configs\s*\.\s*filter", body), (
        "paid presets are being filtered out of the picker instead of disabled"
    )
    assert not re.search(r"manifest\.sizes\s*\.\s*filter", body), (
        "paid sizes are being filtered out of the picker instead of disabled"
    )


def _guarded_block(text: str, header: str) -> str:
    """`header` plus its `{…}` body, brace-matched, or "" if the header is absent.

    Brace-matched rather than regex-sliced because the alternative is a marker-based cut, and a
    break that DELETES the marker then silently changes what is being asserted (see the note in the
    caller — that is how the first narrowing went vacuous).
    """
    at = text.find(header)
    if at < 0:
        return ""
    open_at = text.index("{", at)
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[at : i + 1]
    return ""


def _block_after(body: str, header: str) -> str:
    """The `if (...) { … }` block introduced by `header`."""
    block = _guarded_block(body, header)
    assert block, f"the {header!r} branch is gone"
    return block


def test_an_unentitled_visitor_is_defaulted_onto_a_board_they_can_read():
    """A first visit that opens on `half_ppr` would fire a request the API refuses, and the surface
    would render its refusal state before the visitor had done anything — a paywall presented as a
    broken page. The default has to come from the manifest's own `freeBoard`, not from the entitled
    default constant."""
    code = _code("lib/fantasy-queries.ts")
    start = code.index("export function useFormatSelection")
    end = code.index("const persist =")
    body = code[start:end]
    assert "freeSelection(manifest)" in body, "the selection hook never reads the free board"
    assert re.search(r"if\s*\(!entitled\s*&&\s*free\)", body), (
        "the unentitled branch is gone — an unentitled visitor can be defaulted onto a paid preset"
    )
    # ⛔ THE BRANCH MUST NOT HONOUR A STORED *PRESET*. A paid selection written while subscribed
    # survives the lapse in localStorage, and reopening on it lands the caller on a board the API
    # now refuses.
    #
    # ⚠️ TWO EARLIER SPELLINGS OF THIS CLAUSE WERE VACUOUS AND THE RED PROOF CAUGHT BOTH. First
    # `assert "storedIsFree" in body`, which a break replacing the whole expression with `= true`
    # satisfied because the NAME survived (the import-vs-render shape). Then asserting the
    # comparison itself — which was still vacuous, for a better reason: the ternary it guarded had
    # IDENTICAL ARMS, so the check genuinely did nothing and no break of it could fail.
    #
    # 🩹 NARROWED AT E9.61, from "`stored` must not appear at all" to what that was standing in for.
    # The absence form was the right SPELLING while the branch had nothing legitimate to restore,
    # and it stopped being right when G100-C1's quota made one thing legitimate: a free account owns
    # ONE PERSONALIZED LEAGUE, `/fantasy/leagues` serves it, and `FormatSelector` offers it ungated.
    # `entitled` here is `canUse("personalization", …)` — false for a free account BY DESIGN, since
    # it states the PRICING rather than the quota — so a blanket discard swept up the one selection
    # they are allowed to have, and their league silently reverted to the generic preset on every
    # reload (measured; fixed in E9.61).
    #
    # ⚠️ SO THIS IS A NARROWING TO THE ORIGINAL INTENT, NOT A RELAXATION, and the distinction is the
    # whole reason it is edited here rather than deleted: the paid-preset protection is unchanged
    # and still RED-proven. `stored` may be consulted ONLY behind a membership test against the
    # caller's OWN leagues. E9.61's positive requirement — that the custom selection IS restored —
    # lives in `test_e9_61_generic_delta.py`, under its own story's name.
    branch = _block_after(body, "if (!entitled && free)")

    # ⭐ THE ABSENCE ASSERTION IS KEPT AT FULL STRENGTH — it is simply evaluated on the branch with
    # the ONE permitted read excised. Anything else touching `stored` still fails, exactly as before.
    #
    # ⚠️ THIS SPELLING IS THE SECOND ATTEMPT, AND THE RED PROOF IS WHY. The first narrowing sliced
    # the branch at the free-board fall-through and asked only that a `customIds` test appeared
    # somewhere. That satisfied itself: `restore ANY stored selection` went red, but the ORIGINAL
    # case — `honour a stored paid selection`, which rewrites the FALL-THROUGH to read `stored` —
    # went GREEN. Narrowing a clause is exactly where its old breaks have to be re-run, because the
    # failure mode is a guard that still catches the new regression and has quietly stopped catching
    # the old one.
    permitted = _guarded_block(branch, "if (stored.configName && customIds.has(stored.configName))")
    rest = branch.replace(permitted, "", 1) if permitted else branch

    assert "stored" not in rest, (
        "the unentitled branch consults the stored selection outside the one permitted read — a "
        "paid preset written while subscribed will survive a lapse and reopen on a board the API "
        "now refuses"
    )


def test_a_refused_board_does_not_render_as_an_empty_search():
    """A 403 arriving as zero rows previously rendered 'No players match — try clearing the search
    box': a paywall described as a typo. Reachable through a stale stored selection or the NF-C0
    skew window, i.e. exactly when a misleading message costs most."""
    code = _code("components/fantasy/rankings-board.tsx")
    assert "error: boardError" in code, "the board's error is no longer surfaced"
    assert re.search(r"!boardLoading\s*&&\s*boardError\s*&&", code), (
        "there is no distinct branch for a refused board"
    )
    assert re.search(r"!boardLoading\s*&&\s*!boardError\s*&&\s*rows\.length === 0", code), (
        "the empty-search branch still swallows a refusal"
    )


def test_the_three_board_hooks_never_gate_their_fetch_on_entitlement():
    """With `enabled: canAccess(...)` present the fetch never fires for a free user, `data` is
    undefined, and the surface renders its 'not available yet' EMPTY STATE — which reads as
    unpublished content rather than as a paywall. Silent, and the exact failure the un-gate exists
    to prevent."""
    code = _code("lib/fantasy-queries.ts")
    start = code.index("export function useFantasyManifest")
    end = code.index("useSavedLeagues")
    assert 'enabled: canAccess("fantasy"' not in code[start:end], (
        "a generic-board hook gates its fetch on entitlement"
    )


def test_the_entitlement_is_still_part_of_every_dual_mode_query_key():
    """Kept from E9.56b, deliberately, even though the payloads no longer differ.

    ⭐ It costs one cache miss on login and it is the ONLY thing standing between a future
    re-introduction of per-caller variation and a paying subscriber stranded on a cached free view
    — these queries are `staleTime: Infinity` and `queryClient.clear()` runs on SIGN-OUT ONLY.
    Removing it would be safe TODAY and silently wrong the day the payloads diverge again."""
    code = _code("lib/fantasy-queries.ts")
    for key in ("nfl-fantasy-manifest", "nfl-fantasy-projections", "nfl-fantasy-board"):
        m = re.search(rf'queryKey:\s*\[[^\]]*"{re.escape(key)}"[^\]]*\]', code)
        assert m and "entitled" in m.group(0), f"{key} queryKey omits `entitled`"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4b. The paid formats must not be READABLE — or DERIVABLE — on a free surface
# ══════════════════════════════════════════════════════════════════════════════════════════════
# The board's format picker was only the first of three places the paid scorings surface. The other
# two are client-side renders of a payload that is (correctly) identical for every caller, so the
# API cannot help here — `projections.json` carries `fpStd`/`fpHalf` for everybody by design, and
# the whole gate is which of them a component chooses to print.
#
# ⭐⭐ AND THE THIRD LEAK IS ARITHMETIC, NOT A COLUMN. The three reference totals differ ONLY in how
# a reception scores, so a visible reception count makes the two withheld numbers exact:
#     half = full − 0.5 × rec        standard = full − 1.0 × rec
# Measured on a real served player — full 178.4, half 147.5, standard 116.5, rec 61.9 — both hold to
# a tenth. Locking the totals while printing the stat line underneath is a paywall the reader can do
# in their head, on the one page that shows both. Hence the stat line is gated too, and hence this
# section exists rather than the checks being scattered next to their components.


def test_the_derivation_the_stat_line_gate_exists_to_prevent():
    """⭐ THE ARITHMETIC ITSELF, executable, so the REASON for the gate cannot rot into folklore.

    A future reader deciding whether the stat-line lock is worth its cost needs the identity in
    front of them, not a claim about it. These are the served figures from a real player page.
    If this ever stops holding — a scoring change, a different reception weight — the gate's
    justification has changed and the comment above it needs rewriting, not just its threshold.
    """
    full, half, standard, receptions = 178.4, 147.5, 116.5, 61.9
    assert abs((full - 0.5 * receptions) - half) < 0.15, "half-PPR is no longer full − 0.5·rec"
    assert abs((full - 1.0 * receptions) - standard) < 0.15, "standard is no longer full − 1.0·rec"


def test_the_projections_page_offers_only_the_free_reference_scoring():
    """Season Projections lays a reference TOTAL over a scoring-independent table. That control is
    not the board's format picker and does not share its code, which is exactly how one of the two
    ends up gated and the other does not."""
    code = _code("components/fantasy/projections-table.tsx")
    assert re.search(r'const FREE_SCORING: Scoring = "fpPpr"', code), (
        "the projections page no longer names a single free reference scoring"
    )
    assert re.search(r"const lockedOption = !entitled && s !== FREE_SCORING", code), (
        "the reference-scoring picker no longer locks the paid options"
    )
    assert "disabled: lockedOption" in code, "the locked reference scorings are still selectable"


def test_the_projections_page_reads_the_derived_scoring_not_the_raw_state():
    """⭐ A DISABLED OPTION IS PRESENTATION; A STATE VARIABLE IS NOT A GATE.

    Every read has to go through `effScoring` (which collapses to the free scoring for an
    unentitled caller), so the `scoring` state cannot reach a number even if something else sets
    it. The NF-C0e 'wired ≠ invoked' shape pointed the other way: here the state IS wired and must
    not be invoked.

    Asserted as an ABSENCE of raw `[scoring]` reads, because the presence of `effScoring` somewhere
    in the file says nothing about whether the one read that matters uses it."""
    code = _code("components/fantasy/projections-table.tsx")
    body = code[code.index("export function ProjectionsTable") :]
    assert "effScoring: Scoring = entitled ? scoring : FREE_SCORING" in body, (
        "the derived scoring is gone — the picker state now reaches the table directly"
    )
    raw = re.findall(r"(?<!eff)\[scoring\]|p\[scoring\]|value=\{scoring\}", body)
    assert not raw, f"a value is still read off the raw picker state rather than `effScoring`: {raw}"


def test_the_player_page_locks_the_two_paid_reference_totals():
    """Standard and half-PPR render a lock rather than a number for an unentitled caller — and the
    PERCENTILE goes with them, because it is a position rank computed from the withheld scoring and
    would otherwise describe the number it replaces."""
    code = _code("components/fantasy/player-page.tsx")
    for field, label in (("fpStd", "Standard"), ("fpHalf", "Half PPR")):
        assert re.search(
            rf"value=\{{entitled \? num\(proj\.{field}\) : <LockChip", code
        ), f"the {label} tile still prints its number to an unentitled caller"
    assert code.count("FORMAT_TILE_LOCK_SUB") >= 2, (
        "a locked format tile keeps a sub-line describing the number it is withholding"
    )


def test_the_player_page_gates_the_raw_stat_line():
    """⭐ THE GATE THAT MAKES THE TWO ABOVE MEAN ANYTHING — see the section header for the identity.

    Asserted on the RENDER (`entitled ? <grid of tiles> : <lock>`), not on the presence of the copy
    constants: a component can import every string in this module and still map `statCols` to tiles
    unconditionally."""
    code = _code("components/fantasy/player-page.tsx")
    assert re.search(r"\{entitled \? \(\s*<div className=\"grid grid-cols-3", code), (
        "the raw stat line is no longer gated on entitlement"
    )
    assert 'data-testid="stat-line-lock"' in code, "there is no locked state for the stat line"


def test_the_free_player_page_makes_no_claim_about_the_readers_league():
    """"(your league)" is a claim ABOUT THE READER, and it is false for a free visitor: they have no
    saved league, and the format selector above the tile is pinned to the free preset, so that card
    is the generic board rather than theirs. It is also the phrase the paid tier is sold on, so
    spending it over a preset costs the boundary its own vocabulary."""
    code = _code("components/fantasy/player-page.tsx")
    m = re.search(r"label=\{\s*entitled\s*\?(.*?)\n\s*\}", code, re.S)
    assert m, "the league tile's label no longer branches on entitlement"
    assert "your league" not in m.group(1).split(":")[-1].lower(), (
        "the unentitled branch still labels a preset as the reader's own league"
    )


def test_the_locked_format_copy_lives_in_the_governed_module():
    """Every string these three gates render is claim-adjacent — it says what a membership buys —
    so it goes through the same denylist screening as the rest, and none of it is typed inline."""
    copy_src = (_FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    for const in (
        "REFERENCE_SCORING_LOCK_NOTE",
        "FORMAT_TILE_LOCK_SUB",
        "STAT_LINE_LOCK_TITLE",
        "STAT_LINE_LOCK_DETAIL",
    ):
        assert f"export const {const}" in copy_src, f"{const} is not in the governed copy module"


def test_the_stat_line_lock_does_not_claim_to_stop_scraping():
    """⛔ AN HONESTY CLAUSE, not a copy-style one. The free board is scrapeable BY DESIGN and that
    was accepted when this tier was drawn (it is the marketing wedge). A lock that presented itself
    as protection against copying would be claiming a property the product does not have, on a
    surface whose whole argument is that we say what is true. It withholds a figure; it does not
    defend one."""
    # ⚠️ SCOPED TO THE STRING LITERALS, not to a slice of the file.
    #
    # This used to read from `STAT_LINE_LOCK_TITLE` to the next blank-line run, which made it
    # depend on the FORMATTING of whatever happened to be written below it: G100-C1 appended a
    # section whose explanatory comment legitimately contains "scrapeable" (the free board IS
    # scrapeable by design — saying so in a comment is the opposite of the defect this guards),
    # and the slice swallowed it. A comment cannot mislead a reader of the product; only the copy
    # can, so only the copy is screened.
    copy_src = (_FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    block = " ".join(
        re.findall(rf'{name}\s*=\s*\n?\s*"([^"]*)"', copy_src)[0]
        for name in ("STAT_LINE_LOCK_TITLE", "STAT_LINE_LOCK_DETAIL")
    )
    for word in ("scrap", "steal", "copy-protect", "piracy", "unauthorized"):
        assert word not in block.lower(), (
            f"the stat-line lock copy claims anti-{word} protection the product does not provide"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The paywall boundary is EXPLICIT in the UX
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "component",
    [
        "components/fantasy/rankings-board.tsx",
        "components/fantasy/projections-table.tsx",
        "components/fantasy/player-page.tsx",
    ],
)
def test_every_free_surface_states_the_boundary(component):
    """AC: 'the paywall is on personalization + decision, explicit in the UX.' A complete-looking
    free board with no boundary stated reads as the whole product — there is nothing to buy, and the
    paid aha ('what changed because it is MY league') never gets posed."""
    assert "<FreemiumBoundary" in _code(component), f"{component} states no free/paid boundary"


def test_the_boundary_is_not_shown_to_someone_who_already_pays():
    """An upsell for something the caller already pays for reads as a billing bug."""
    code = _code("components/fantasy/shared.tsx")
    body = code[code.index("export function FreemiumBoundary"):]
    assert re.search(r"if\s*\(\s*entitled\s*\)\s*return null", body), (
        "FreemiumBoundary does not return null for an entitled caller"
    )


def test_the_boundary_copy_lives_in_the_governed_copy_module():
    """Every claim-bearing string on this surface must pass the denylist screening, which runs over
    `fantasy-claim-copy.ts`. A literal typed into the component is outside every copy check there
    is — which is exactly where a well-meaning edit would put a performance promise.

    ⚠️ ASSERTS THE ABSENCE OF INLINE PROSE, not merely the PRESENCE of the constants. The obvious
    spelling ("both constants are referenced") is satisfied by a component that references them AND
    adds a sentence of its own — which is the actual failure mode, since nobody deletes the imports
    when they paste in a better headline. Proven vacuous by the red-proof harness before being
    rewritten this way.

    Short strings (class names, `href`s, single words) are allowed; the rule is that no SENTENCE
    lives here. 40 characters is comfortably above any Tailwind class list and below any real claim.
    """
    code = _code("components/fantasy/shared.tsx")
    body = code[code.index("export function FreemiumBoundary"):]
    body = body[: body.index("export function PosBadge")]
    assert "FREE_TIER_SUMMARY" in body and "PAID_TIER_SUMMARY" in body

    # ⚠️ ATTRIBUTES ARE STRIPPED FIRST, and skipping this is a real bug rather than tidiness: a
    # naive `"([^"]{40,})"` sweep pairs the CLOSING quote of one `className` with the OPENING quote
    # of the next, so it "finds" the markup between two attributes and reports it as prose. The
    # first cut of this clause did exactly that and failed on correct source.
    markup_free = re.sub(r'\w+(?:-\w+)*=(?:"[^"]*"|\{[^{}]*\})', "", body)

    # What remains that could carry a claim: a JSX TEXT NODE (`>Some sentence<`) or a long quoted
    # literal. Braced expressions are references to the governed module and are fine by definition.
    prose = [t.strip() for t in re.findall(r">\s*([A-Za-z][^<>{}]{15,})\s*<", markup_free)]
    quoted = [s for s in re.findall(r'"([^"]{25,})"', markup_free) if " " in s]
    assert not prose and not quoted, (
        f"inline copy in FreemiumBoundary — move it to fantasy-claim-copy.ts so the denylist "
        f"screening covers it: {prose + quoted}"
    )


def test_the_boundary_copy_makes_no_forbidden_claim():
    """The freemium pitch is a division of LABOUR — it does more of the work — never an outcome
    promise. `best_alpha = 0`."""
    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

    src = _code("lib/fantasy-claim-copy.ts")
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', src)
    hits = [(t, lit) for lit in literals for t in ex._CLAIM_DENYLIST if t in lit.lower()]
    assert not hits, f"forbidden claim in the fantasy copy module: {hits}"


def test_the_paid_summary_names_both_halves_of_the_boundary():
    """⭐ ISOLATING FIXTURE FOR AN AND-COMPOSED RULE: the two halves are asserted SEPARATELY, so a
    block that named only personalization (the easy one to write) cannot pass on the strength of the
    other. The entitlement splits on two capabilities and the copy has to describe both, or the
    pricing page promises less than the product delivers."""
    src = (_FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    # ⚠️ Slice from the `= [` that OPENS the array, not from the name — the TypeScript annotation
    # (`readonly {...}[]`) contains a `]` of its own, so slicing to the first one after the name cut
    # the block to the type and the clause passed on nothing.
    block = src[src.index("PAID_TIER_SUMMARY"):]
    block = block[block.index("= ["):]
    block = block[: block.index("\n]")].lower()
    assert "scoring" in block and "roster" in block, "the personalization half is not described"
    assert "draft" in block, "the decision-support half is not described"
    # The third half, added when the tier narrowed to one preset: the formats are now a membership
    # feature and the paid summary is what states that in the user's words.
    assert "format" in block, "the scoring-format half is not described"


def test_the_free_tier_summary_names_no_league_format():
    """⚠️ THE COPY THAT WENT STALE ONCE, AND WOULD AGAIN.

    Two independent reasons this sentence must not name a format. (1) CORRECTNESS TODAY: the block
    renders on Projections, which is format-INDEPENDENT — one projection with no scoring applied —
    so 'scored for full-PPR, twelve teams' would be false on one of the two pages that shows it.
    (2) STALENESS: until 2026-08-08 it read 'scored for the common league presets', true while all
    14 boards were free and false the instant the tier narrowed. Nothing renders differently when
    copy stops being accurate, so nothing catches it. The format scope belongs to the controls it
    constrains (`FORMAT_LOCK_EXPLANATION`) and to the paid summary, both of which are asserted
    separately above."""
    src = (_FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    block = src[src.index("FREE_TIER_SUMMARY"):]
    block = block[: block.index("} as const")].lower()
    for token in ("ppr", "superflex", "twelve team", "12-team", "preset"):
        assert token not in block, (
            f"FREE_TIER_SUMMARY names a league format ({token!r}) — it renders on the "
            f"format-independent Projections surface too, and it goes stale when the tier moves"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The full-season rate — a DISPLAY transform, and it must stay one
# ══════════════════════════════════════════════════════════════════════════════════════════════

#: Everything that decides a player's POSITION on a board. If the full-season rate reaches any of
#: these it has stopped being a display transform.
_ORDERING_MODULES = [
    "lib/league-scoring.ts",
    "lib/draft-optimizer.ts",
    "components/fantasy/league-board.tsx",
    "components/fantasy/draft-optimizer.tsx",
    # NF-C2.1 — the mock draft orders twice over: the CPU shortlist decides who the room takes,
    # and the grade orders the room itself. Both are ordering, so both inherit the boundary.
    "lib/mock-draft.ts",
    "components/fantasy/mock-draft.tsx",
    # NF-C5 — the auction optimizer orders twice over: the candidate list decides what to bid on,
    # and the nomination panel orders who to put up. Both are ordering, so both inherit the
    # boundary — and an auction VALUE derived from a full-slate rate would be worse than a
    # mis-ordered board, because a user bids real money against it.
    "lib/auction-optimizer.ts",
    "components/fantasy/auction-optimizer.tsx",
]


@pytest.mark.parametrize("module", _ORDERING_MODULES)
def test_the_full_season_rate_never_reaches_a_scoring_or_ordering_module(module):
    """⛔⛔ THE HARD BOUNDARY ON THIS FEATURE.

    Ranking on a full-slate rate ranks players as if availability did not exist — it systematically
    promotes exactly the players our projection discounts on purpose. And because it REORDERS the
    board it stops being a UI change and becomes a model decision subject to the whole-board
    placement gate (the NF-D18/NF-D20 `CONSTRAINT_REFUSED` class), which has its own
    pre-registration. A display column can ship in an app story; a re-ordering cannot."""
    assert "fullSeasonRate" not in _code(module), (
        f"{module} uses fullSeasonRate — a display transform has leaked into ordering"
    )


def test_the_full_season_rate_guards_a_zero_or_absent_games_figure():
    """⚠️ `games === 0` (a player projected to miss the whole season) yields `Infinity`, which is a
    `number` in JS — so it passes every `!= null` guard a caller might write and renders as '∞'
    beside a points column. The helper must return null, which callers render as an em-dash."""
    code = _code("lib/fantasy.ts")
    body = code[code.index("export function fullSeasonRate"):]
    body = body[: body.index("\n}")]
    assert "games <= 0" in body, "no zero/negative-games guard"
    assert body.count("Number.isFinite") >= 2, "both inputs must be finiteness-checked"
    assert body.count("return null") >= 3, "a rejected input must yield null, not a number"


def test_the_full_season_rate_is_the_expected_arithmetic():
    """Pins the transform itself: expected points × a full slate ÷ expected games. A drifted
    constant (16, or a per-game figure) would produce a plausible-looking wrong number that nothing
    else in the product would contradict."""
    code = _code("lib/fantasy.ts")
    assert "export const FULL_SEASON_GAMES = 17" in code
    body = code[code.index("export function fullSeasonRate"):]
    assert "(pts * FULL_SEASON_GAMES) / games" in body


@pytest.mark.parametrize(
    "component",
    ["components/fantasy/rankings-board.tsx", "components/fantasy/projections-table.tsx"],
)
def test_the_rate_renders_beside_the_expected_total(component):
    """AC: 'the if-healthy figure renders beside expected pts'. The PAIR is the disclosure — each
    number alone answers only half the drafter's question.

    ⚠️ ASSERTS THE RENDER, NOT THE IMPORT. The obvious spelling (`"FULL_SEASON_RATE_LABEL" in code`)
    is satisfied by a file that merely still IMPORTS the constant while heading the column something
    else — proven vacuous by the red-proof harness, which swapped the header for a bare `"Rate"` and
    watched this clause stay green. So it matches the label INSIDE the `InfoTip` that heads the
    column, and requires the two headers to be adjacent in that order.
    """
    code = _code(component)
    assert re.search(r"<InfoTip\s+label=\{FULL_SEASON_RATE_LABEL\}", code), (
        "no column is headed with the canonical full-season-rate label"
    )
    assert "fullSeasonRate(" in code, "the column is headed but never populated"

    # Adjacency: no other InfoTip-headed column may sit between the two.
    headers = re.findall(r"<InfoTip\s+label=\{(\w+)\}", code)
    assert "EXPECTED_POINTS_LABEL" in headers and "FULL_SEASON_RATE_LABEL" in headers
    assert headers.index("FULL_SEASON_RATE_LABEL") == headers.index("EXPECTED_POINTS_LABEL") + 1, (
        f"the full-season rate is not immediately beside the expected total: {headers}"
    )


def test_the_rate_label_does_not_imply_a_consensus_calibrated_number():
    """⛔ It is our own projection divided by our own expected games — NOT reconciled against
    anyone else's published 'if he plays every week' figure. The definition has to say so, because a
    bare full-slate number invites exactly that comparison. (The former "still conservative at running
    back" clause was RETIRED 2026-08-15 with NF-TR2b's served level recalibration — the RB residual is
    now inside the noise, and a claim about it would be a claim about noise; the per-position table on
    the Track Record page is where any residual is disclosed, derived.)
    """
    src = (_FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    block = src[src.index("FULL_SEASON_RATE_DEFINITION"):]
    block = block[: block.index("\n\n")].lower()
    assert "not a prediction that he plays all seventeen" in block, "the label reads as a forecast"
    assert "conservative at running back" not in block, (
        "the retired pre-NF-TR2b RB-conservatism claim is back in the served copy"
    )
    assert "not a figure reconciled against" in block, (
        "the definition does not disclaim consensus calibration"
    )
