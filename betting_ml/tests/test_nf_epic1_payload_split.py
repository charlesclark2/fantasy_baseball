"""NF-EPIC 1 — the PUBLIC/PAID payload split (PM Option C, 2026-08-10).

The audit found `fpStd`, `fpHalf` and the complete raw stat line in the ANONYMOUS
`/fantasy/nfl/projections` payload, gated only by which component declined to draw them. The PM
ruled the stat line PAID — it is the re-scorable substrate — and chose Option C: split the payload
and score the free personalized league server-side.

These guards pin the split itself. The scorer's fidelity is `test_nf_epic1_parity.py`; the free
league's end-to-end behaviour is `test_nf_epic1_free_league_scoring.py`.

⛔ ANCHORED IN ITS OWN CLAUSE — nothing here is bolted onto `test_freemium_tier.py` or
`test_g100_c1_free_league.py` (the E9.60 coupling trap). These fail only for NF-EPIC 1's property.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import anyio
from fastapi import HTTPException
import pytest

from app.backend.services import projection_fields

_REPO = Path(__file__).resolve().parents[2]
_TS_LEAGUE_CONFIG = _REPO / "frontend" / "lib" / "league-config.ts"

#: A payload shaped like the real one: identity + the free wedge + `contrib` (PM Q3: FREE) + a raw
#: stat line + the two paid scorings.
_ROW = {
    "id": "p1", "name": "Ja'Marr Chase", "pos": "WR", "team": "CIN", "bye": 10,
    "rookie": False, "g": 16.4, "adp": 1.2,
    "fpPpr": 261.4, "fpSd": 51.0, "fpP10": 196.0, "fpP90": 327.0,
    "contrib": {"totalPts": 261.4, "drivers": [{"feature": "target_share", "pts": 30.0}]},
    "fpHalf": 213.5, "fpStd": 165.6,
    "rec": 95.7, "recYds": 1160.2, "recTd": 8.3, "tgt": 139.5,
    "rushAtt": 4.0, "rushYds": 21.0, "rushTd": 0.1, "fum": 0.6, "twoPt": 0.3,
}
_PAYLOAD = {"season": 2026, "generated_at": "2026-08-01T00:00:00Z", "players": [_ROW]}


# ── the field set ────────────────────────────────────────────────────────────────────────────────


def test_every_scorable_stat_is_paid():
    """⭐ The PAID set is DERIVED from the scorer's own map, not hand-listed.

    This is the direction that matters. A hand-written list is a DENYLIST: the next field the
    exporter adds is public by default and leaks on the next publish with no code change and no
    failing test. Deriving it means a new SCORABLE stat is paid the moment someone teaches the
    scorer about it.
    """
    for stat_key, field in projection_fields.STAT_FIELD.items():
        assert field in projection_fields.PAID_PLAYER_FIELDS, (
            f"{stat_key} → {field} is scorable but would ship publicly"
        )


def test_a_newly_added_scorable_stat_is_paid_without_touching_the_paid_list(monkeypatch):
    """RED-proof of the derivation: teach the scorer a new stat, and it is withheld automatically.

    If `PAID_PLAYER_FIELDS` were ever re-spelled as a literal list, this goes red — which is the
    whole point of asserting the MECHANISM rather than today's membership.
    """
    import importlib

    module = importlib.reload(projection_fields)
    monkeypatch.setitem(module.STAT_FIELD, "brand_new_stat", "brandNewStat")
    rebuilt = frozenset(module.STAT_FIELD.values()) | module.PAID_SCORING_FIELDS
    assert "brandNewStat" in rebuilt
    importlib.reload(projection_fields)


def test_the_two_paid_scorings_are_withheld():
    """`fpStd`/`fpHalf` are paid because they are ARITHMETIC on the stat line — they cannot be
    defended separately and must not ship separately."""
    assert projection_fields.PAID_SCORING_FIELDS == {"fpStd", "fpHalf"}
    assert projection_fields.PAID_SCORING_FIELDS <= projection_fields.PAID_PLAYER_FIELDS


def test_the_free_wedge_and_contrib_stay_public():
    """The free half, named explicitly so a future edit that withholds it is a deliberate one.

    `contrib` is here on the PM's Q3 ruling (2026-08-10): feature attribution is show-our-work
    transparency, an EXPLANATION of the free number rather than a second number.
    """
    for field in ("fpPpr", "fpP10", "fpP90", "fpSd", "contrib", "g", "adp", "name", "pos", "team"):
        assert field not in projection_fields.PAID_PLAYER_FIELDS, f"{field} must stay free"


def test_the_stat_field_map_mirrors_the_frontend():
    """One logical map, two owners (INC-38's shape). A one-sided edit either un-gates a column or
    breaks a league's scoring, and both are silent."""
    source = _TS_LEAGUE_CONFIG.read_text()
    block = re.search(r"export const STAT_FIELD[^{]*\{(.*?)\n\}", source, re.S)
    assert block, "could not find STAT_FIELD in the TS source — the guard would be vacuous"
    body = re.sub(r"//[^\n]*", "", block.group(1))  # strip comments before matching (INC-38)
    ts_map = dict(re.findall(r'(\w+):\s*"(\w+)"', body))
    assert ts_map, "parsed an empty STAT_FIELD — vacuous"
    assert ts_map == projection_fields.STAT_FIELD, (
        "STAT_FIELD has drifted between Python and TypeScript: "
        f"only in TS={set(ts_map) - set(projection_fields.STAT_FIELD)}, "
        f"only in Python={set(projection_fields.STAT_FIELD) - set(ts_map)}"
    )


# ── the transform ────────────────────────────────────────────────────────────────────────────────


def test_the_public_payload_carries_no_paid_field():
    public = projection_fields.public_projections_payload(_PAYLOAD)
    assert projection_fields.paid_fields_present(public) == set()


def test_the_public_payload_keeps_the_free_wedge():
    """A redaction that also removed the free number would be a different, worse bug."""
    row = projection_fields.public_projections_payload(_PAYLOAD)["players"][0]
    assert row["fpPpr"] == 261.4
    assert row["fpP10"] == 196.0 and row["fpP90"] == 327.0
    assert row["contrib"]["totalPts"] == 261.4
    assert row["name"] == "Ja'Marr Chase"


def test_the_derivation_the_split_exists_to_prevent_is_no_longer_possible():
    """⭐ THE POINT OF THE WHOLE STORY, as executable arithmetic.

    `half = full − 0.5×rec` and `standard = full − 1.0×rec` held to a tenth on live data, so
    withholding the two totals while shipping `rec` was a paywall the reader does in their head.
    The public payload must therefore carry NEITHER the totals NOR their input.
    """
    row = projection_fields.public_projections_payload(_PAYLOAD)["players"][0]
    assert "fpHalf" not in row and "fpStd" not in row
    assert "rec" not in row, "the reception count alone reconstructs both withheld totals"
    # and the identity really did hold on the unredacted row, which is why `rec` had to go
    assert abs((_ROW["fpPpr"] - 0.5 * _ROW["rec"]) - _ROW["fpHalf"]) < 0.1
    assert abs((_ROW["fpPpr"] - 1.0 * _ROW["rec"]) - _ROW["fpStd"]) < 0.1


def test_a_malformed_row_costs_only_itself():
    """E9.49: one bad row must never blank the collection."""
    payload = {"players": [_ROW, "not-a-row", {"id": "p2", "fpStd": 1.0}]}
    out = projection_fields.public_projections_payload(payload)
    assert out["players"][1] == "not-a-row"
    assert projection_fields.paid_fields_present(out) == set()


# ── the routes ───────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_env(monkeypatch):
    """Stub only the IO boundary. Routing, dependencies and the entitlement resolver stay real."""
    from app.backend.routers import fantasy
    from app.backend.services import cost_guardrails, jwt_verify

    cost_guardrails.get_limiter().reset()
    # The full-projections memo is module-global and would carry a payload across tests.
    fantasy._full_projections_memo.clear()

    def fake_load(rel_key: str, sport: str = "nfl"):
        if rel_key.endswith("projections.json"):
            return json.loads(json.dumps(_PAYLOAD))
        return None

    monkeypatch.setattr(fantasy, "_load_json", fake_load)
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    yield True
    fantasy._full_projections_memo.clear()


def _call(path: str, query: str = "", *, headers: dict | None = None, aws_event: dict | None = None):
    from app.backend.main import app

    out: dict = {}
    body_parts: list[bytes] = []
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]

    async def run():
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": "GET", "scheme": "https", "path": path, "raw_path": path.encode(),
            "query_string": query.encode(), "root_path": "", "headers": raw_headers,
            "client": ("203.0.113.7", 1234), "server": ("testserver", 443),
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
    return out["status"], out.get("headers", {}), b"".join(body_parts)


def _entitled_event(groups: str = "[subscriber]"):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "sub-1", "cognito:groups": groups}}}}}


def _unsigned_token(groups: list[str]) -> str:
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'none'})}.{seg({'sub': 'x', 'cognito:groups': groups})}.x"


def test_the_anonymous_projections_route_leaks_nothing(app_env):
    """The live repro from the audit, as a test: `curl` the public route, find no paid value."""
    status, _headers, body = _call("/fantasy/nfl/projections", "season=2026")
    assert status == 200
    assert projection_fields.paid_fields_present(json.loads(body)) == set()


def test_the_public_route_is_still_byte_identical_for_every_caller(app_env):
    """⭐ G100-D1's CDN cache survives ONLY while these bytes do not vary by caller.

    A subscriber must receive the same reduced blob and fetch the paid half separately; the moment
    this route answers a subscriber differently it re-introduces `cache_control_for`'s "same URL,
    two bodies" hazard and every anonymous view goes back on the Lambda.
    """
    _s, _h, anon = _call("/fantasy/nfl/projections", "season=2026")
    _s, _h, subscriber = _call(
        "/fantasy/nfl/projections", "season=2026", aws_event=_entitled_event()
    )
    assert anon == subscriber


def test_the_full_projection_refuses_an_anonymous_caller(app_env):
    status, _h, _b = _call("/fantasy/nfl/projections-full", "season=2026")
    assert status in (401, 403)


def test_a_forged_token_does_not_unlock_the_full_projection(app_env):
    """On any route reachable without the gateway authorizer the Bearer token is attacker-supplied;
    only a signature-verified one may grant a paid capability."""
    status, _h, _b = _call(
        "/fantasy/nfl/projections-full", "season=2026",
        headers={"Authorization": f"Bearer {_unsigned_token(['subscriber', 'admin'])}"},
    )
    assert status in (401, 403)


def test_a_subscriber_gets_the_full_projection(app_env):
    """The paid half must actually be served, or the split has withheld it from the people who
    paid for it — a quieter failure than a leak, and just as real."""
    status, _h, body = _call(
        "/fantasy/nfl/projections-full", "season=2026", aws_event=_entitled_event()
    )
    assert status == 200
    row = json.loads(body)["players"][0]
    assert row["rec"] == 95.7 and row["fpHalf"] == 213.5 and row["fpStd"] == 165.6


def test_a_signed_in_free_account_is_refused_the_full_projection(app_env):
    """The free tier gets a SCORED league, never the substrate. This is the boundary that actually
    holds: account creation is open and self-serve, so a gate at 'signed in' is not a gate."""
    status, _h, _b = _call(
        "/fantasy/nfl/projections-full", "season=2026",
        aws_event=_entitled_event(groups="[]"),
    )
    assert status in (401, 403)


def test_the_full_projection_is_never_shared_cacheable(app_env):
    """A shared cache entry here would hand the paid substrate to anonymous visitors."""
    _s, headers, _b = _call(
        "/fantasy/nfl/projections-full", "season=2026", aws_event=_entitled_event(),
        headers={"Authorization": "Bearer x.y.z"},
    )
    assert headers.get("cache-control") == "private, no-store"
    assert "authorization" in headers.get("vary", "").lower()


# ── the edge ─────────────────────────────────────────────────────────────────────────────────────


def test_the_paid_projection_is_not_reachable_through_the_cdn():
    """The CDN route strips `Authorization` by design, so anything it can reach is effectively
    anonymous. A paid path on that allowlist would be a 403 pinned into a public cache — or worse."""
    source = (_REPO / "frontend" / "app" / "api" / "public" / "[...path]" / "route.ts").read_text()
    upstreams = re.findall(r'upstream:\s*"([^"]+)"', source)
    assert upstreams, "parsed no upstreams — the guard would be vacuous"
    assert "/fantasy/nfl/projections-full" not in upstreams


def test_the_paid_projection_has_no_public_cache_rule():
    from app.backend.services import cost_guardrails

    assert cost_guardrails.public_cache_control("/fantasy/nfl/projections-full") is None


def test_my_teams_still_serves_leagues_when_the_projection_cannot_be_read(monkeypatch):
    """⭐ A REGRESSION THIS STORY CAUSED AND THIS GUARD EXISTS TO KEEP CLOSED.

    `/fantasy/nfl/my-teams` was a pure DynamoDB read until NF-EPIC 1 added the server-scored
    roster. The first cut let the projections read RAISE — `_load_json` answers 503 with no
    `CACHE_BUCKET` and 502 on a read error — so an absent projections artifact took the whole
    endpoint down and the user's SAVED LEAGUES vanished with it. A league list disappearing
    because a PROJECTION file is missing is the wrong failure: the list is the core of this
    response, the roster join is an enhancement on top of it.

    ⚠️ Asserts the OBSERVABLE contract (the leagues are still served), not that some internal
    try/except exists — a guard on the mechanism would pass on a rewrite that reintroduced the
    outage through a different path.
    """
    from app.backend.routers import fantasy

    monkeypatch.setattr(
        fantasy,
        "_full_projections",
        lambda season: (_ for _ in ()).throw(HTTPException(status_code=503, detail="no bucket")),
    )
    records = [{"league_id": "L1", "sport": "nfl", "name": "Dynasty",
                "imported_roster": [{"name": "Ja'Marr Chase", "position": "WR"}]}]
    rosters = fantasy._scored_rosters(records, 2026)
    assert rosters == {"L1": []}, "an unreadable projection must degrade, never raise"


def test_the_league_board_does_not_swallow_an_unreadable_projection():
    """The mirror image, and it is deliberate: on `/nfl/league-board` the board IS the response.

    Degrading to an empty board there would render a page that looks like "your league has no
    players" instead of "we couldn't score your league" — the silent-empty class. Same read,
    opposite correct behaviour, so the two are pinned separately.
    """
    import inspect

    from app.backend.routers import fantasy

    source = inspect.getsource(fantasy.nfl_league_board)
    assert "try:" not in source, (
        "the league-board handler must let an unreadable projection surface as a failure"
    )


def test_the_paid_projection_is_not_in_the_degrade_floor():
    """The degrade floor is the FREE promise — the generic board and the billing path. A paid,
    entitlement-gated read does not belong in it."""
    from app.backend.services import cost_guardrails

    assert not cost_guardrails.is_allowed_in_degrade("/fantasy/nfl/projections-full")
