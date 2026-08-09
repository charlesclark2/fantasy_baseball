"""G100-C1 — ONE free personalized league, and the cap that keeps it one.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT THIS GUARDS, AND WHY EACH CLAUSE NEEDS ITS OWN FIXTURE
═══════════════════════════════════════════════════════════════════════════════════════════════════

The freemium build (2026-08-08) drew a capability boundary and left a SEAM — a real, read
`FREE_PERSONALIZED_LEAGUE_QUOTA` with a default of 0 and nothing calling it. G100-C1 is the flip.
Three things had to be true at once, and each fails silently on its own:

  1. A signed-in FREE account can save and read ONE league.
  2. Their SECOND league is refused — server-side, whether the request comes from our UI or curl.
  3. Nothing about the FREE GENERIC BOARD changed. Personalization is per-caller by construction,
     so if any of it reached the CDN allowlist or the public cache rules, one user's league would be
     served to another. `test_freemium_tier.py` owns the byte-identity invariant; this file owns the
     statement that the new surface stayed OUT of the caches that invariant licenses.

⭐ EVERY GATE HERE IS `and`-COMPOSED SOMEWHERE, so each clause gets a fixture that SATISFIES the
others (NF-D17). A test whose fixture trips two clauses proves neither: deleting the clause it names
leaves it green because the other one is still refusing. The quota tests below therefore drive a
caller who is otherwise fully admissible, and the identity tests drive one whose quota is fine.

⛔ WHAT THIS FILE DOES NOT PROVE. The API Gateway authorizer (a route that is correct in code still
401s until its per-route console config is right — NF3.2) and the live `deploy.sh`. The saved-league
routes are AUTHENTICATED, so they inherit the default Cognito authorizer and need no gateway change —
which is itself asserted below, because "needs no change" is the kind of claim that rots.
"""

from __future__ import annotations

import base64
import json

import pytest

from app.backend.services import entitlement


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The quota, as a pure function — no request, no IO
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_a_free_signed_in_account_gets_exactly_one_league():
    free = entitlement.Entitlement(user_id="u1", groups=(), fantasy=False, source="gateway")
    assert entitlement.personalized_league_quota(free) == 1
    assert entitlement.allows_personalization(free) is True


def test_a_subscriber_keeps_the_storage_cap():
    from app.backend.services import dynamo

    sub = entitlement.Entitlement(user_id="u2", fantasy=True, source="gateway")
    assert entitlement.personalized_league_quota(sub) == dynamo.MAX_LEAGUES_PER_USER
    assert entitlement.personalized_league_quota(sub) > 1


def test_setting_the_quota_to_zero_withdraws_the_free_tier_cleanly(monkeypatch):
    """⭐ ZERO IS A LIVE SETTING, NOT DEAD CODE — the operator's one-flip withdrawal.

    A gate that has only ever been exercised at its OPEN setting is not a tested gate. If the free
    tier has to be pulled (cost, abuse, a pricing change), `FREE_PERSONALIZED_LEAGUE_QUOTA=0` must
    refuse a free caller outright rather than leave them a half-working page — and must NOT touch a
    subscriber, whose quota comes from the storage cap and not from that env var.
    """
    monkeypatch.setattr(entitlement, "FREE_PERSONALIZED_LEAGUE_QUOTA", 0)
    free = entitlement.Entitlement(user_id="u1", fantasy=False, source="gateway")
    sub = entitlement.Entitlement(user_id="u2", fantasy=True, source="gateway")

    assert entitlement.allows_personalization(free) is False
    assert entitlement.allows_personalization(sub) is True, "withdrawing the free tier hit a payer"


def test_the_serve_cap_keeps_the_oldest_league_deterministically():
    """A lapsed subscriber's five leagues must resolve to ONE, and always the SAME one.

    ⚠️ Ordered by `created_at`, not `updated_at`. `list_fantasy_leagues` sorts on `updated_at`, which
    moves every time the user edits something — so a cap built on it would silently swap WHICH league
    a lapsed user keeps as soon as they opened a different one. The kept league has to be stable
    against browsing, which means the one they have had longest.
    """
    # ⚠️ THE TIMESTAMPS ARE CHOSEN SO THE TWO ORDERINGS DISAGREE, and that is the whole fixture.
    # The first cut used records whose `created_at` and `updated_at` happened to sort identically —
    # so swapping the clause to `updated_at` produced the SAME answer and the guard stayed green
    # with the thing it names broken (caught by `g100_c1_red_proof.py`, the NF-D17 shape).
    #
    # Here the league created FIRST ("a") was edited MOST RECENTLY, so:
    #   by created_at (correct) → "a"      by updated_at (the defect) → "b"
    records = [
        {"league_id": "c", "created_at": "2026-03-01", "updated_at": "2026-03-02"},
        {"league_id": "a", "created_at": "2026-01-01", "updated_at": "2026-09-01"},
        {"league_id": "b", "created_at": "2026-02-01", "updated_at": "2026-02-02"},
    ]
    kept = entitlement.leagues_within_quota(records, 1)
    assert [r["league_id"] for r in kept] == ["a"]
    # Stable under a different input ORDER — the cap must not inherit DynamoDB's iteration order.
    assert entitlement.leagues_within_quota(list(reversed(records)), 1) == kept
    # And it is a cap, not a filter: a subscriber-sized quota returns everything.
    assert len(entitlement.leagues_within_quota(records, 25)) == 3


def test_a_malformed_created_at_cannot_reorder_the_healthy_leagues():
    """One bad field must cost only itself (E9.49's row-by-row principle, applied to ordering).

    A record with no `created_at` sorts LAST rather than first — otherwise a single missing
    timestamp would silently become the league a lapsed user keeps.
    """
    records = [
        {"league_id": "broken"},
        {"league_id": "good", "created_at": "2026-05-05"},
    ]
    assert [r["league_id"] for r in entitlement.leagues_within_quota(records, 1)] == ["good"]


def test_zero_quota_serves_no_personalized_league():
    assert entitlement.leagues_within_quota([{"league_id": "a", "created_at": "x"}], 0) == []


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The storage writer honours the CALLER's quota, not its own ceiling
# ══════════════════════════════════════════════════════════════════════════════════════════════


class _FakeTable:
    """The narrowest possible stand-in for the users table: a dict of stored leagues."""

    def __init__(self, leagues: dict | None = None):
        self.leagues = dict(leagues or {})

    def get_item(self, Key):  # noqa: N803 — boto3's casing
        return {"Item": {"fantasy_leagues": self.leagues}}

    def update_item(self, Key, UpdateExpression, **kw):  # noqa: N803
        names = kw.get("ExpressionAttributeNames", {})
        values = kw.get("ExpressionAttributeValues", {})
        if "ConditionExpression" in kw:
            return {}
        if UpdateExpression.startswith("REMOVE"):
            self.leagues.pop(names["#id"], None)
            return {}
        self.leagues[names["#id"]] = values[":cfg"]
        return {}


@pytest.fixture()
def fake_users_table(monkeypatch):
    from app.backend.services import dynamo

    table = _FakeTable()
    monkeypatch.setattr(dynamo, "_users_table", lambda: table)
    return table


def test_a_free_caller_may_save_their_first_league(fake_users_table):
    from app.backend.services import dynamo

    record = dynamo.put_fantasy_league("u1", None, {"name": "Home league"}, max_leagues=1)
    assert record["league_id"]
    assert len(fake_users_table.leagues) == 1


def test_a_free_callers_second_league_is_refused_by_the_writer(fake_users_table):
    """The cap lives in the WRITER, so it holds for any caller — router, script or future job."""
    from app.backend.services import dynamo

    dynamo.put_fantasy_league("u1", None, {"name": "First"}, max_leagues=1)
    with pytest.raises(ValueError, match="too_many_leagues"):
        dynamo.put_fantasy_league("u1", None, {"name": "Second"}, max_leagues=1)


def test_a_caller_at_their_quota_can_still_EDIT_the_league_they_have(fake_users_table):
    """⭐ THE CLAUSE MOST LIKELY TO BE WRITTEN WRONG. Applying the cap to updates as well as creates
    reads as symmetric and is a real defect: a free user's one league would freeze at whatever they
    first typed, and the failure would present as "saving is broken" with a 409 nobody expects
    (E8.6's silent/blocked-save class). The cap counts leagues; an update creates none.
    """
    from app.backend.services import dynamo

    created = dynamo.put_fantasy_league("u1", None, {"name": "First"}, max_leagues=1)
    updated = dynamo.put_fantasy_league(
        "u1", created["league_id"], {"name": "Renamed"}, max_leagues=1
    )
    assert updated["name"] == "Renamed"
    assert len(fake_users_table.leagues) == 1


def test_the_quota_can_only_ever_tighten_the_storage_ceiling(fake_users_table):
    """An entitlement bug must not be able to authorise a DynamoDB item overflow.

    `max_leagues` is an ENTITLEMENT number and `MAX_LEAGUES_PER_USER` is a STORAGE fact; the writer
    clamps to the smaller of the two, so a hypothetical quota of 10_000 still cannot blow the 400 KB
    item limit. The two constants answer different questions and only one of them is negotiable.
    """
    from app.backend.services import dynamo

    for i in range(dynamo.MAX_LEAGUES_PER_USER):
        dynamo.put_fantasy_league("u1", None, {"name": f"L{i}"}, max_leagues=10_000)
    with pytest.raises(ValueError, match="too_many_leagues"):
        dynamo.put_fantasy_league("u1", None, {"name": "overflow"}, max_leagues=10_000)


def test_the_writers_default_is_unchanged_for_existing_callers(fake_users_table):
    """NF-C0 additivity: `max_leagues` is optional and defaults to the old behaviour, so no existing
    caller changed meaning when the parameter was added."""
    from app.backend.services import dynamo

    for i in range(3):
        dynamo.put_fantasy_league("u1", None, {"name": f"L{i}"})
    assert len(fake_users_table.leagues) == 3


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. End to end through the real ASGI app
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Raw ASGI rather than starlette's TestClient, for the reasons E9.56's suite documents: TestClient
# needs `httpx` (absent here), and it cannot set the `aws.event` scope key that Mangum uses to carry
# the API Gateway authorizer context — the one thing separating a real account from a forged token.


def _call(
    path: str,
    query: str = "",
    *,
    method: str = "GET",
    body: dict | None = None,
    headers: dict | None = None,
    aws_event: dict | None = None,
):
    """Drive the real ASGI app. Returns (status, parsed_body_or_raw_bytes)."""
    import anyio

    from app.backend.main import app

    out: dict = {}
    parts: list[bytes] = []
    raw = json.dumps(body).encode() if body is not None else b""

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
            "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")]
            + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("test", 1),
            "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": raw, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]
            elif message["type"] == "http.response.body":
                parts.append(message.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    payload = b"".join(parts)
    try:
        return out["status"], json.loads(payload)
    except Exception:  # noqa: BLE001 — a 204 has no body, and that is a valid outcome here
        return out["status"], payload


def _event(groups: str = "[]", sub: str = "free-user-1"):
    """The API Gateway authorizer context as Mangum delivers it. `groups="[]"` is a real,
    gateway-validated account with NO entitlement — the free tier."""
    return {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": sub, "cognito:groups": groups}}}
        }
    }


def _unsigned_token(groups: list[str]) -> str:
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'sub': 'x', 'cognito:groups': groups})}.x"


#: A REAL `LeagueSave` payload — the exact shape the editor and the importer both produce. Written
#: out rather than minimised because `LeagueSave` validates that a config has at least one STARTING
#: slot (nothing to rank against otherwise), and a fixture trimmed past that would fail these tests
#: at the validator instead of at the gate they are actually about.
_LEAGUE_BODY = {
    "name": "Sunday Money",
    "n_teams": 10,
    "scoring": {"per_stat": {"rec": 0.5, "pass_yds": 0.04, "rush_yds": 0.1}},
    "roster": [
        {"name": "QB", "count": 1, "eligible": ["QB"]},
        {"name": "RB", "count": 2, "eligible": ["RB"]},
        {"name": "WR", "count": 3, "eligible": ["WR"]},
        {"name": "TE", "count": 1, "eligible": ["TE"]},
        {"name": "BENCH", "count": 6, "eligible": [], "bench": True},
    ],
}


@pytest.fixture()
def api(monkeypatch):
    """Stub ONLY the storage boundary. Routing, both router dependencies, the entitlement resolver
    and the Pydantic response models are all the real thing."""
    from app.backend.services import dynamo, jwt_verify

    tables: dict[str, _FakeTable] = {}

    def table_for(user_id):
        return tables.setdefault(user_id, _FakeTable())

    # `_users_table()` takes no user, so route the fake through the call that DOES: every dynamo
    # league helper keys on user_id, and the stub keeps one table per user so a cross-user read
    # would fail loudly rather than silently succeed.
    holder = {"user": None}
    real_list = dynamo.list_fantasy_leagues

    def list_leagues(user_id):
        holder["user"] = user_id
        monkeypatch.setattr(dynamo, "_users_table", lambda: table_for(user_id), raising=False)
        return real_list(user_id)

    monkeypatch.setattr(dynamo, "list_fantasy_leagues", list_leagues)
    monkeypatch.setattr(dynamo, "_users_table", lambda: table_for(holder["user"] or "anon"))
    # No network: an unreachable JWKS makes every presented token unverifiable, which is both the
    # anonymous path asserted on below and a proof the verifier fails CLOSED when it is unavailable.
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return tables


# ── identity before entitlement ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/fantasy/leagues"),
        ("GET", "/fantasy/nfl/my-teams"),
        ("POST", "/fantasy/leagues"),
    ],
)
def test_an_anonymous_caller_is_told_to_sign_in_not_to_pay(api, method, path):
    """⭐ 401, NOT 403, and the distinction is a product decision rather than a nicety.

    Every league record is keyed on a Cognito `sub`, so an anonymous caller has nowhere to SAVE a
    league — the next step is signup, not checkout. A 403 here would send the client to the upgrade
    CTA and ask someone to pay for something they can have for free.
    """
    status, _ = _call(path, method=method, body=_LEAGUE_BODY if method == "POST" else None)
    assert status == 401, f"{method} {path} did not ask an anonymous caller to sign in"


def test_a_forged_token_buys_no_ENTITLEMENT_even_though_it_resolves_an_identity(api):
    """⚠️ THE HONEST STATEMENT OF WHAT PROTECTS THIS SURFACE — recorded because G100-C1 WIDENED it.

    Before this story the saved-league routes required `require_fantasy_beta_access`, which reads
    groups from a SIGNATURE-VERIFIED token when no authorizer context is present — so a forged token
    was refused by the app itself. The gate is now the personalization QUOTA, and a free account's
    quota is 1, so the app-layer question a forged caller has to pass is only "who are you?".

    `get_user_id` answers that from the authorizer context, then falls back to an UNVERIFIED bearer
    decode (a documented local-dev fallback shared by `/bets`, `/bankroll`, `/portfolio` and every
    other authenticated route). So in this harness — which deliberately has no authorizer context —
    a forged token does resolve to an identity and reads that identity's own empty league list.

    ⭐ WHAT ACTUALLY KEEPS IT SAFE IN PRODUCTION is the API Gateway Cognito authorizer, which rejects
    an unsigned token before Mangum is invoked. That protection is real ONLY while these routes stay
    off the `--authorization-type NONE` list — which is asserted separately below, and is the clause
    that would actually break if someone "made My League public".

    What is asserted here is the part that IS the app's job: a forged token confers no ENTITLEMENT.
    It cannot read another user's leagues, and it cannot buy the subscriber quota — `resolve_entitlement`
    ignores unverified groups, so the forged `subscriber`/`admin` claim leaves the caller on the free
    quota of one.
    """
    forged = {"Authorization": "Bearer " + _unsigned_token(["subscriber", "admin"])}
    status, listed = _call("/fantasy/leagues", headers=forged)
    # It reaches the route (see above) — but as a nobody, with nobody's data.
    assert status == 200
    assert listed == [], "a forged token read another account's leagues"

    # And it is still on the FREE quota: the second save is refused exactly as for any free caller.
    assert _call("/fantasy/leagues", method="POST", body=_LEAGUE_BODY, headers=forged)[0] == 201
    status, _ = _call(
        "/fantasy/leagues",
        method="POST",
        body={**_LEAGUE_BODY, "name": "Second"},
        headers=forged,
    )
    assert status == 409, "a forged `subscriber` claim bought the paid quota"


def test_the_saved_league_routes_are_not_declared_public_at_the_api_gateway():
    """⭐ THE CLAUSE THE TEST ABOVE DEFERS TO, and the one with real teeth.

    A route reachable anonymously needs an explicit `--authorization-type NONE` at the API Gateway —
    per-route console config, outside this repo's IaC (NF3.2), inventoried in
    `infrastructure/aws_resources.md`. Every authenticated route inherits the Cognito authorizer,
    which is what rejects a forged token before the Lambda runs.

    So "My League is public" would be a ONE-LINE infra change with no code diff, and it would turn
    the unverified-bearer fallback above into a live hole. Reading the inventory means a session that
    adds such a route has to come past this test.
    """
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "infrastructure/aws_resources.md").read_text()
    for route_key in (
        "GET /fantasy/leagues",
        "POST /fantasy/leagues",
        "GET /fantasy/nfl/my-teams",
    ):
        assert f'--route-key "{route_key}"' not in doc, (
            f"{route_key} was given an anonymous API-Gateway route; the saved-league surface must "
            "stay behind the Cognito authorizer"
        )


# ── the free tier, end to end ─────────────────────────────────────────────────────────────────


def test_a_free_account_can_save_and_read_its_one_league(api):
    """The whole story, in one pass: a signed-in account with NO fantasy groups configures a league
    and gets it back on the personalization surface."""
    status, created = _call(
        "/fantasy/leagues", method="POST", body=_LEAGUE_BODY, aws_event=_event()
    )
    assert status == 201, f"a free account could not save its first league ({created})"

    status, listed = _call("/fantasy/leagues", aws_event=_event())
    assert status == 200 and len(listed) == 1

    status, teams = _call("/fantasy/nfl/my-teams", "season=2026", aws_event=_event())
    assert status == 200
    assert len(teams["leagues"]) == 1
    assert teams["quota"] == 1


def test_a_free_accounts_second_league_is_refused_by_the_api(api):
    """⭐ THE CAP IS SERVER-ENFORCED. Hiding the button is not a gate — this is the same POST the UI
    makes, and it must be refused on its own."""
    status, _ = _call("/fantasy/leagues", method="POST", body=_LEAGUE_BODY, aws_event=_event())
    assert status == 201
    status, detail = _call(
        "/fantasy/leagues",
        method="POST",
        body={**_LEAGUE_BODY, "name": "Second league"},
        aws_event=_event(),
    )
    assert status == 409, "a free account saved a SECOND personalized league"
    assert "1 league" in json.dumps(detail), (
        "the refusal must quote the CALLER's quota; a free user told '25' reads a paywall as a bug"
    )


def test_a_subscriber_may_save_more_than_one(api):
    """The same POST, by an entitled caller. Without this the cap test above would pass just as well
    on a gate that refused EVERYONE's second league — i.e. it would not be testing the quota."""
    ev = _event(groups="[subscriber]", sub="paid-user-1")
    assert _call("/fantasy/leagues", method="POST", body=_LEAGUE_BODY, aws_event=ev)[0] == 201
    status, _ = _call(
        "/fantasy/leagues",
        method="POST",
        body={**_LEAGUE_BODY, "name": "Second league"},
        aws_event=ev,
    )
    assert status == 201, "a subscriber was capped at the free quota"


def test_the_management_list_is_not_capped_but_the_personalized_serve_is(api, monkeypatch):
    """⭐ THE LAPSED-SUBSCRIBER CASE, which the create check structurally cannot see.

    Someone saves several leagues as a subscriber and then lapses. No create happens afterwards, so
    a create-only cap would keep serving them every personalized board forever — the paid tier,
    retained by having once paid for it.

    The two surfaces then have to disagree ON PURPOSE: `/fantasy/leagues` still returns ALL of them
    (they are the user's own configs, and they must be able to see and DELETE their way back under
    quota — capping it would strand them above a limit they can never get under), while
    `/fantasy/nfl/my-teams` serves at most `quota`.
    """
    paid = _event(groups="[subscriber]", sub="lapsing-user")
    for i in range(3):
        assert (
            _call(
                "/fantasy/leagues",
                method="POST",
                body={**_LEAGUE_BODY, "name": f"League {i}"},
                aws_event=paid,
            )[0]
            == 201
        )

    # …the subscription lapses. Same account, same stored data, no groups.
    free = _event(groups="[]", sub="lapsing-user")

    status, listed = _call("/fantasy/leagues", aws_event=free)
    assert status == 200
    assert len(listed) == 3, "a lapsed user lost sight of their own saved leagues"

    status, teams = _call("/fantasy/nfl/my-teams", "season=2026", aws_event=free)
    assert status == 200
    assert len(teams["leagues"]) == 1, "a lapsed subscriber kept the paid tier's personalization"
    assert teams["withheld_by_quota"] == 2
    assert teams["saved_total"] == 3


def test_my_teams_keeps_every_key_the_deployed_client_already_reads(api):
    """NF-C0 additivity. The new keys are ADDED; `season` and `leagues` are untouched, so the
    already-deployed frontend — which knows none of them — renders exactly what it renders today
    rather than going blank on a missing key during the deploy-skew window."""
    status, teams = _call("/fantasy/nfl/my-teams", "season=2026", aws_event=_event())
    assert status == 200
    assert teams["season"] == 2026
    assert isinstance(teams["leagues"], list)
    for added in ("quota", "saved_total", "withheld_by_quota"):
        assert added in teams, f"the client's `?? default` read of {added} has nothing to find"


def test_the_management_list_is_still_a_bare_array(api):
    """`/fantasy/leagues` has always returned a bare JSON array and the deployed client indexes it
    directly. Wrapping it in an envelope to carry the quota would be the NF-C0 break in its exact
    original form — a 200 with a blank screen and no error anywhere. The quota travels on
    `/nfl/my-teams`, which was already an object."""
    _call("/fantasy/leagues", method="POST", body=_LEAGUE_BODY, aws_event=_event())
    status, listed = _call("/fantasy/leagues", aws_event=_event())
    assert status == 200
    assert isinstance(listed, list), "the management list changed container type"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The personalized surface stayed OUT of every shared cache
# ══════════════════════════════════════════════════════════════════════════════════════════════
# Personalization is per-caller by construction — the exact opposite of the free board's
# byte-identity invariant. A shared cache entry here hands one user's league to another.

_PERSONAL_PATHS = ("/fantasy/leagues", "/fantasy/nfl/my-teams")


@pytest.mark.parametrize("path", _PERSONAL_PATHS)
def test_a_personalized_path_is_never_shared_cacheable(path):
    from app.backend.services import cost_guardrails

    assert cost_guardrails.public_cache_control(path) is None, (
        f"{path} was added to the public cache rules; it is per-caller"
    )


@pytest.mark.parametrize("path", _PERSONAL_PATHS)
def test_a_personalized_response_is_private_no_store(path):
    """The structural reason it is safe, rather than the remembered one: every request to these
    paths carries `Authorization`, and `cache_control_for` answers `private, no-store` on any such
    request regardless of path. So this holds even if someone later adds a rule above."""
    from app.backend.services import cost_guardrails

    assert (
        cost_guardrails.cache_control_for(path, has_authorization=True, status_code=200)
        == cost_guardrails.PRIVATE_CACHE_CONTROL
    )


@pytest.mark.parametrize("path", _PERSONAL_PATHS)
def test_the_cdn_route_cannot_reach_a_personalized_path(path):
    """The edge strips `Authorization` unconditionally, so anything it proxied would be fetched
    ANONYMOUSLY — for these paths that is a 401 written into a public CDN entry. The allowlist is
    what keeps the edge from being able to ask the question at all.

    Read from the route file rather than restated here: a copy of the allowlist in a test asserts
    what the test author believed, not what ships.
    """
    from pathlib import Path

    route = (
        Path(__file__).resolve().parents[2]
        / "frontend/app/api/public/[...path]/route.ts"
    )
    source = route.read_text()
    upstream = path.replace("/fantasy/nfl/", "/fantasy/nfl/").rstrip("/")
    assert f'upstream: "{upstream}"' not in source, (
        f"{path} became CDN-proxyable; a personalized payload would be cached publicly"
    )


def test_the_personalized_surface_is_not_in_the_degrade_floor():
    """⚠️ A DELIBERATE OMISSION, recorded so it is not read as one.

    Degrade mode's floor is "the free rankings board and your account" — that is what
    `DEGRADE_MESSAGE` promises, and the message is the contract. Personalization is cheap (a
    DynamoDB point read) but it is not the promised floor, and widening an allowlist is exactly the
    move that makes a kill switch stop killing anything. A free user's My League page shows the
    honest 503 message during a cost event.
    """
    from app.backend.services import cost_guardrails

    for path in _PERSONAL_PATHS:
        assert cost_guardrails.is_allowed_in_degrade(path) is False
    # …and the free board it names IS still up, so this is a scoped omission, not a broken floor.
    assert cost_guardrails.is_allowed_in_degrade("/fantasy/nfl/board") is True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The gate map itself
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_every_saved_league_route_carries_the_quota_gate():
    """⭐ ENUMERATED FROM THE APP'S REAL ROUTE TABLE, not from a list written here.

    The characteristic failure of a hand-kept list is silent in the dangerous direction: a route
    added later and forgotten is simply absent from the list and nothing goes red. Walking the
    mounted routes means a NEW `/fantasy/leagues/...` endpoint has to satisfy this or fail.
    """
    from app.backend.dependencies import require_personalized_league_access
    from app.backend.main import app

    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if not (path.startswith("/fantasy/leagues") or path == "/fantasy/nfl/my-teams"):
            continue
        checked += 1
        deps = [getattr(d.dependency, "__name__", "") for d in getattr(route, "dependencies", [])]
        assert require_personalized_league_access.__name__ in deps, (
            f"{path} is not gated on the personalization quota"
        )
    assert checked >= 5, "the route walk found nothing — the enumeration itself is broken"


def test_the_saved_league_routes_are_authenticated_so_they_need_no_gateway_change():
    """NF3.2 in reverse. A route is only reachable ANONYMOUSLY once its API Gateway authorizer is set
    to NONE — per-route console config, outside this repo's IaC. These routes must NOT be on that
    list: they inherit the default Cognito authorizer, and adding an explicit `NONE` route would
    un-gate the saved-league surface entirely.

    The assertion is that they refuse an unauthenticated request in CODE, which is what makes
    "inherits the default authorizer, needs no change" a checked claim rather than a comment.
    """
    status, _ = _call("/fantasy/leagues")
    assert status == 401
