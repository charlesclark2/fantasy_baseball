"""NF-C6-PH2 — the weekly served CONTRACT and its entitlement boundary.

These guards defend the three things this story could get silently wrong:

  1. the FREE/PAID split — a paid component leaking onto the free wire, or being derivable from it;
  2. the BYTE-IDENTITY invariant the CDN entry, `cache_control_for` and the client's entitled-keyed
     query cache all rest on;
  3. the CLAIM the evidence contradicts — NF-W1 measured the matchup foil LOSING at all four
     positions, so "matchup-based" may not reach a reader through any served name or description.

⚠️ Nothing here imports `pipeline` (E11.23) and nothing does IO. The ASGI harness is the one
`test_freemium_tier.py` established: raw ASGI rather than TestClient, because `httpx` is absent and
because only a raw scope can carry the `aws.event` key that separates a real subscriber from a
forged token.

RED-proven by `betting_ml/tests/nf_c6_ph2_red_proof.py`.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from app.backend.models import nfl_weekly as C
from app.backend.services import cost_guardrails, entitlement, projection_fields

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"

FREE_WEEKLY_PATHS = ("/fantasy/nfl/weekly/manifest", "/fantasy/nfl/weekly/projections")
PAID_WEEKLY_PATH = "/fantasy/nfl/weekly/projections-full"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The contract itself
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_contract_model_registry_is_exhaustive():
    """A model declared in the module but missing from `CONTRACT_MODELS` escapes every schema guard
    below — the vacuity this list exists to prevent (the NCAAF-P3.1 shape)."""
    from pydantic import BaseModel

    declared = {
        v for k, v in vars(C).items()
        if isinstance(v, type) and issubclass(v, BaseModel) and v is not BaseModel
        and v.__module__ == C.__name__
    }
    assert declared == set(C.CONTRACT_MODELS), (
        f"models outside the guarded registry: {sorted(m.__name__ for m in declared - set(C.CONTRACT_MODELS))}"
    )


def test_the_paid_set_is_derived_from_the_scorers_own_stat_field_map():
    """⭐ THE LOAD-BEARING DIRECTION. A hand-written paid list is a DENYLIST: the next component the
    champion's head emits would be PUBLIC BY DEFAULT and leak on the next publish with no code
    change and no failing test. Deriving it means a new SCORABLE stat is withheld automatically."""
    for comp, key in C.WEEKLY_COMPONENT_STAT_KEY.items():
        assert key in projection_fields.STAT_FIELD, f"{comp} maps to unknown stat key {key}"
        assert C.WEEKLY_COMPONENT_FIELD[comp] == projection_fields.STAT_FIELD[key]
    assert C.PAID_WEEKLY_PLAYER_FIELDS == (
        frozenset(C.WEEKLY_COMPONENT_FIELD.values()) | {C.QUANTILE_VECTOR_FIELD}
    )
    # …and every component field is one the SEASON payload also treats as paid, so the two surfaces
    # cannot disagree about whether the same stat is behind the paywall.
    assert set(C.WEEKLY_COMPONENT_FIELD.values()) <= projection_fields.PAID_PLAYER_FIELDS


def test_a_component_with_no_stat_field_entry_is_refused():
    """The derivation is only safe if an unmapped component is a HARD ERROR. A component quietly
    served under a name the paywall does not know about is the NF-C0e wrong-key class, whose whole
    harm is that unrecognized keys pass through as 'captured' with no error."""
    doctored = {k: v for k, v in projection_fields.STAT_FIELD.items() if k != "rec_yds"}
    with pytest.raises(ValueError, match="absent from"):
        C.resolve_component_fields(doctored)
    # …and it resolves cleanly on the real map, so the refusal above is not simply "always raises".
    assert C.resolve_component_fields(projection_fields.STAT_FIELD) == C.WEEKLY_COMPONENT_FIELD
    # A brand-new component with no scorer entry is refused too — the forward-looking case.
    with pytest.raises(ValueError, match="brand_new_stat"):
        C.resolve_component_fields(projection_fields.STAT_FIELD, {"newthing": "brand_new_stat"})


def test_the_free_row_carries_no_paid_field_and_keeps_every_free_one():
    """Set equality in BOTH directions: a leak is a breach, and an over-eager reduction silently
    removes the number the free tier exists to show."""
    row = {"id": "x", "name": "N", "pos": "RB", "team": "BUF", "opp": "NYJ", "home": True,
           "status": "projected", "fpPpr": 12.0, "fpP10": 3.0, "fpP90": 24.0,
           "rosPpr": 200.0, "rosP10": 150.0, "rosP90": 250.0, "rosWeeks": 17, "histWeeks": 40,
           "q": [1.0] * 39, **{f: 5.0 for f in C.WEEKLY_COMPONENT_FIELD.values()}}
    pub = C.public_weekly_player_row(row)
    assert set(pub) & C.PAID_WEEKLY_PLAYER_FIELDS == set()
    assert set(pub) == set(row) - C.PAID_WEEKLY_PLAYER_FIELDS
    for f in ("fpPpr", "fpP10", "fpP90", "rosPpr", "rosWeeks", "histWeeks"):
        assert pub[f] == row[f]
    assert C.paid_weekly_fields_present({"players": [pub]}) == set()
    assert C.paid_weekly_fields_present({"players": [row]}) == C.PAID_WEEKLY_PLAYER_FIELDS


def test_no_paid_value_is_arithmetic_from_the_free_ones():
    """The `half = full − 0.5·rec` lesson: a paywall the reader does the arithmetic on is not one.

    The weekly free set is identity + one PPR number + its band + the ROS triple. `fpStd`/`fpHalf`
    are not served weekly AT ALL, and every reception-bearing component is paid — so neither
    alternate scoring is recoverable."""
    free_fields = {"id", "name", "pos", "team", "opp", "home", "status", "fpPpr", "fpP10", "fpP90",
                   "rosPpr", "rosP10", "rosP90", "rosWeeks", "histWeeks"}
    assert set(C.declared_field_names(C.NflWeeklyPlayer)) == free_fields | C.PAID_WEEKLY_PLAYER_FIELDS
    assert free_fields & projection_fields.PAID_PLAYER_FIELDS == set()
    assert not (free_fields & projection_fields.PAID_SCORING_FIELDS)
    # `rec` is the term both alternate scorings need, and it is paid.
    assert projection_fields.STAT_FIELD["rec"] in C.PAID_WEEKLY_PLAYER_FIELDS


def test_a_malformed_row_costs_only_itself():
    """E9.49: one bad row must never blank the collection."""
    out = C.public_weekly_payload({"players": [{"id": "a", "q": [1.0]}, "junk", 7]})
    assert out["players"][0] == {"id": "a"}
    assert out["players"][1] == "junk" and out["players"][2] == 7


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The claim NF-W1's own field measured as false
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_served_schema_makes_no_matchup_claim():
    C.assert_no_matchup_claim(C._served_texts())


def test_the_matchup_guard_actually_refuses_the_claim():
    """⛔ NOT VACUOUS. A guard that cannot fail is worse than none (NF1.7 (a))."""
    with pytest.raises(ValueError, match="matchup foil LOSING"):
        C.assert_no_matchup_claim([("copy.headline", "Matchup-based weekly projections")])
    with pytest.raises(ValueError):
        C.assert_no_matchup_claim([("copy.sub", "our numbers are matchup driven")])


def test_the_matchup_guard_permits_an_honest_description_of_the_input():
    """⭐ THE SCOPING IS DELIBERATE. The champion legitimately CONSUMES an `opponent_matchup__*`
    feature family, so banning the bare word would refuse an honest description of a model input
    while leaving the actual claim expressible in any other phrasing. What is banned is the CLAIM."""
    C.assert_no_matchup_claim([
        ("features", "consumes an opponent matchup feature family, lagged eight weeks"),
        ("methodology", "the matchup foil was measured and lost at all four positions"),
    ])


def test_the_schema_makes_no_edge_or_pick_claim():
    C.assert_no_edge_claim_in_schema()
    from pydantic import BaseModel

    class _Bad(BaseModel):
        best_pick: str = "x"

    with pytest.raises(ValueError, match="edge/pick claim"):
        C.assert_no_edge_claim_in_schema((_Bad,))


def test_best_alpha_is_zero_on_the_wire_and_the_walk_can_fail():
    assert C.NflWeeklyHonestFraming().best_alpha == 0.0
    C.assert_best_alpha_is_zero({"framing": {"best_alpha": 0.0}})
    with pytest.raises(ValueError, match="must be exactly 0.0"):
        C.assert_best_alpha_is_zero({"framing": {"best_alpha": 0.07}})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Absent vs null vs zero — three facts, three renderings
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_three_absence_reasons_are_distinguishable():
    """NF-C6b/NF-K1: an empty state that means three things costs an investigation every time it
    recurs. K/DST are absent BY DESIGN and must not read like an unresolved player."""
    assert set(C.ABSENCE_REASONS) == {
        "position_not_projected", "no_gameday_roster_row", "pit_gate_dropped"
    }
    assert len(set(C.ABSENCE_REASONS)) == len(C.ABSENCE_REASONS)


def test_a_bye_is_a_declared_zero_not_a_missing_projection():
    """NF-W1's pre-registration: a bye is a DETERMINISTIC zero knowable at schedule release, and
    serving emits the identity 0 exactly. `status` is what tells the two apart."""
    assert set(C.NflWeeklyPlayer.model_fields["status"].annotation.__args__) == {"projected", "bye"}
    row = C.NflWeeklyPlayer(id="x", name="N", pos="TE", team="BUF", status="bye",
                            fpPpr=0.0, fpP10=0.0, fpP90=0.0, rosWeeks=12, histWeeks=30)
    assert row.opp is None and row.home is None and row.fpPpr == 0.0
    # ⭐ and a declared null is ON THE WIRE, never dropped: `ros*` null means "no remaining
    # horizon", which is a different fact from a ROS of zero.
    dumped = row.model_dump()
    for f in ("rosPpr", "rosP10", "rosP90"):
        assert f in dumped and dumped[f] is None


def test_the_projected_positions_are_the_ones_the_champion_covers():
    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

    assert C.PROJECTED_POSITIONS == WP.POSITIONS
    assert "K" not in C.PROJECTED_POSITIONS and "DST" not in C.PROJECTED_POSITIONS


def test_the_served_levels_match_the_certified_ones():
    """The band a reader sees must be the band NF-W1 measured coverage for — serving a different
    pair would relabel a range nobody recomputed."""
    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

    assert (C.INTERVAL_LO_LEVEL, C.INTERVAL_HI_LEVEL) == (WP.INTERVAL_LO, WP.INTERVAL_HI)
    assert C.SCORING_SYSTEM_ID == WP.SCORING_SYSTEM_ID


def test_the_ros_sigma_levels_are_the_ones_that_make_sigma_sigma():
    """`ros_projection` computes σ = (q84 − q16)/2, which is σ ONLY at 0.16/0.84. The nearest
    39-level grid points (0.15/0.85) would give 1.036σ — a 3.6% over-estimate in every ROS band."""
    assert (C.ROS_SIGMA_LO_LEVEL, C.ROS_SIGMA_HI_LEVEL) == (0.16, 0.84)
    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

    assert 0.16 not in set(WP.Q_LEVELS) and 0.84 not in set(WP.Q_LEVELS), (
        "if the grid ever carries 0.16/0.84 exactly, the interpolation note is stale"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The entitlement boundary, end to end through the real ASGI app
# ══════════════════════════════════════════════════════════════════════════════════════════════

_WEEK_PLAYERS = {
    "season": 2026, "week": 1, "generated_at": "2026-09-05T00:00:00+00:00",
    "scoring_system_id": "ppr",
    "players": [
        {"id": "p1", "name": "Alpha Back", "pos": "RB", "team": "BUF", "opp": "NYJ", "home": True,
         "status": "projected", "fpPpr": 12.5, "fpP10": 2.1, "fpP90": 24.9,
         "rosPpr": 205.0, "rosP10": 150.0, "rosP90": 260.0, "rosWeeks": 17, "histWeeks": 48,
         "q": [float(i) for i in range(39)],
         "passAtt": 0.0, "passYds": 0.0, "passTd": 0.0, "passInt": 0.0,
         "rushAtt": 14.2, "rushYds": 61.0, "rushTd": 0.4,
         "tgt": 3.9, "rec": 3.1, "recYds": 24.0, "recTd": 0.1},
    ],
}
_WEEK_MANIFEST = {
    "season": 2026, "week": 1, "season_type": "REG", "scoring_system_id": "ppr",
    "generated_at": "2026-09-05T00:00:00+00:00", "projection_day": "2026-09-09T00:00:00+00:00",
    "n_players": 1, "n_by_position": {"QB": 0, "RB": 1, "WR": 0, "TE": 0}, "n_bye": 0,
    "absences": [{"reason": "position_not_projected", "n": 64, "detail": "K/DST are not projected"}],
    "pit_weeks_checked": 176, "pit_records_checked": 85056, "pit_rows_dropped": 0,
    "input_vintage": {"train_through_season": 2025, "train_through_week": 18},
    "lineage": {"served_version": "nfl_fantasy_weekly_v1",
                "base_model_version": "nfl_fantasy_nf_w1_v1",
                "point_model_version": "nf_w1_lgbm_hurdle",
                "interval_model_version": "nf_w1_lgbm_hurdle"},
}
_CURRENT = {"season": 2026, "week": 1, "generated_at": "2026-09-05T00:00:00+00:00",
            "manifest_key": "weekly/2026/1/manifest.json",
            "players_key": "weekly/2026/1/players.json"}

#: Values that exist ONLY behind the paywall. If any reaches an anonymous body, the split leaked.
_PAID_NUMBERS = {14.2, 61.0, 3.9, 3.1, 24.0}


@pytest.fixture()
def app_env(monkeypatch):
    from app.backend.routers import fantasy
    from app.backend.services import jwt_verify

    # The per-IP limiter is process-global and stateful; an exhausted bucket surfaces as a
    # payload-shape failure in the NEXT file (the documented `test_freemium_tier` hazard).
    cost_guardrails.get_limiter().reset()

    def fake_load(rel_key: str, sport: str = "nfl"):
        if rel_key.endswith("current.json"):
            return _CURRENT
        if rel_key.startswith("weekly/") and rel_key.endswith("manifest.json"):
            return _WEEK_MANIFEST
        if rel_key.startswith("weekly/") and rel_key.endswith("players.json"):
            return _WEEK_PLAYERS
        return None

    monkeypatch.setattr(fantasy, "_load_json", fake_load)
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return True


def _call(path: str, query: str = "", *, headers=None, aws_event=None):
    import anyio

    from app.backend.main import app

    out: dict = {}
    parts: list[bytes] = []

    async def run():
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.1"},
            "http_version": "1.1", "method": "GET", "scheme": "https",
            "path": path, "raw_path": path.encode(), "query_string": query.encode(),
            "root_path": "",
            "headers": [(b"host", b"testserver")]
            + [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": ("test", 1), "server": ("testserver", 443),
        }
        if aws_event is not None:
            scope["aws.event"] = aws_event

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(msg):
            if msg["type"] == "http.response.start":
                out["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                parts.append(msg.get("body", b""))

        await app(scope, receive, send)

    anyio.run(run)
    return out["status"], b"".join(parts)


def _entitled_event(groups: str = "[subscriber]"):
    return {"requestContext": {"authorizer": {"jwt": {"claims": {
        "sub": "sub-1", "cognito:groups": groups}}}}}


def _unsigned_token(groups: list[str]) -> str:
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


@pytest.mark.parametrize("path", FREE_WEEKLY_PATHS)
def test_an_anonymous_caller_reaches_the_free_weekly_surfaces(app_env, path):
    status, body = _call(path, "season=2026&week=1")
    assert status == 200, body[:300]
    assert json.loads(body)


def test_the_free_weekly_projection_carries_no_paid_component(app_env):
    status, body = _call("/fantasy/nfl/weekly/projections", "season=2026&week=1")
    assert status == 200
    payload = json.loads(body)
    assert C.paid_weekly_fields_present(payload) == set()
    seen = set(_scalars(payload))
    leaked = _PAID_NUMBERS & seen
    assert not leaked, f"paid component value(s) {leaked} reached the anonymous body"
    # …and the free wedge IS there. A reduction that removed the number is as wrong as a leak.
    assert payload["players"][0]["fpPpr"] == 12.5
    assert payload["players"][0]["fpP90"] == 24.9
    assert payload["players"][0]["rosPpr"] == 205.0


@pytest.mark.parametrize("path", FREE_WEEKLY_PATHS)
def test_the_free_weekly_url_is_byte_identical_for_every_caller(app_env, path):
    """⭐⭐ THE INVARIANT THREE SYSTEMS REST ON: the CDN entry, `cache_control_for`'s same-URL-two-
    bodies hazard, and the client's `entitled`-keyed query cache. Re-introducing per-caller
    variation on a FREE url invalidates all three at once."""
    q = "season=2026&week=1"
    anon = _call(path, q)[1]
    forged = _call(path, q, headers={"Authorization": f"Bearer {_unsigned_token(['subscriber'])}"})[1]
    subscriber = _call(path, q, aws_event=_entitled_event())[1]
    assert anon == forged == subscriber


def test_the_paid_weekly_route_refuses_an_anonymous_caller(app_env):
    status, _ = _call(PAID_WEEKLY_PATH, "season=2026&week=1")
    assert status in (401, 403)


def test_a_forged_token_does_not_unlock_the_paid_weekly_route(app_env):
    """On a gateway-`NONE` route the Bearer token is attacker-controlled; only a signature-verified
    one (or the authorizer context) may grant a paid capability."""
    status, _ = _call(PAID_WEEKLY_PATH, "season=2026&week=1",
                      headers={"Authorization": f"Bearer {_unsigned_token(['subscriber'])}"})
    assert status in (401, 403)


def test_a_subscriber_gets_the_component_line_and_the_quantile_vector(app_env):
    status, body = _call(PAID_WEEKLY_PATH, "season=2026&week=1", aws_event=_entitled_event())
    assert status == 200, body[:300]
    payload = json.loads(body)
    assert C.paid_weekly_fields_present(payload) == C.PAID_WEEKLY_PLAYER_FIELDS
    assert len(payload["players"][0]["q"]) == 39


def test_the_week_is_resolved_through_the_pointer_when_omitted(app_env):
    """The response DECLARES its own week, so a caller always knows what they got rather than
    inferring it from the request they sent."""
    for path in FREE_WEEKLY_PATHS:
        status, body = _call(path, "season=2026")
        assert status == 200
        assert json.loads(body)["week"] == 1


def test_a_missing_pointer_is_a_404_not_a_guess(app_env, monkeypatch):
    """⛔ Picking 'the highest week directory that exists' would silently serve a stale week whenever
    a publish half-landed."""
    from app.backend.routers import fantasy

    monkeypatch.setattr(fantasy, "_load_json", lambda *a, **k: None)
    for path in (*FREE_WEEKLY_PATHS, PAID_WEEKLY_PATH):
        status, _ = _call(path, "season=2026")
        assert status in (401, 403, 404), path


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The cache/CDN sides — the byte-identity invariant's downstream consumers
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_free_weekly_paths_are_shared_cacheable_and_the_paid_one_never_is():
    for path in FREE_WEEKLY_PATHS:
        assert cost_guardrails.public_cache_control(path), f"{path} is free but not cacheable"
        assert cost_guardrails.cache_control_for(
            path, has_authorization=False, status_code=200).startswith("public,")
        # ⚠️ …and a token on the same URL still forces private, which is the second half of the
        # protection (`Vary: Authorization` is the first). Either alone still allows the breach.
        assert cost_guardrails.cache_control_for(
            path, has_authorization=True, status_code=200) == cost_guardrails.PRIVATE_CACHE_CONTROL
    assert cost_guardrails.public_cache_control(PAID_WEEKLY_PATH) is None
    assert cost_guardrails.cache_control_for(
        PAID_WEEKLY_PATH, has_authorization=False, status_code=200) is None


def test_the_cdn_route_proxies_the_free_weekly_reads_and_never_the_paid_one():
    """A catch-all here would be an open relay into our own API from a trusted origin; the paid path
    would be a 403 written into a public CDN entry and served to subscribers for the window.

    ⚠️ COMMENT-STRIPPED, and that is not tidiness. The first cut of this guard matched the whole
    file and went RED on this story's own explanatory comment — which names
    `weekly/projections-full` precisely to say it must never be here. A source scan that prose can
    satisfy (or, as here, break) is the INC-38 class; the question is what the edge can ASK, so the
    scan reads the `upstream:` values, not the file.
    """
    code = (_FRONTEND / "app/api/public/[...path]/route.ts").read_text()
    routes = code.split("const ROUTES")[1].split("\n}\n")[0]
    live = "\n".join(ln for ln in routes.splitlines() if not ln.strip().startswith("//"))
    upstreams = set(re.findall(r'upstream:\s*"([^"]+)"', live))

    for path in FREE_WEEKLY_PATHS:
        assert path in upstreams, f"{path} is free but the CDN cannot serve it"
    assert PAID_WEEKLY_PATH not in upstreams, "the PAID weekly route reached the CDN allowlist"
    # ⭐ …and NO upstream may be a prefix of the paid path either: a `/fantasy/nfl/weekly` entry
    # would let the edge reach the paid route through path concatenation.
    assert not [u for u in upstreams if PAID_WEEKLY_PATH.startswith(u.rstrip("/") + "/")], (
        f"an allowlisted upstream is a PREFIX of the paid weekly route: {sorted(upstreams)}"
    )
    # `week` is optional upstream (the API resolves the pointer), but an unvalidated param is
    # DROPPED rather than forwarded — so the pattern must exist or a junk week reaches nothing.
    assert re.search(r"week:\s*/\^\\d\{1,2\}\$/", live), "week is not pattern-validated"


def test_the_weekly_paths_are_registered_for_the_gateway_authorizer_flip():
    """NF3.2: a route that is public IN CODE still 401s before Lambda until the operator sets its
    authorizer to NONE. That flip is per-route console config outside this repo's IaC, so the
    inventory is the only place it is written down — a public route missing from it is a route
    nobody will remember to open."""
    doc = (_REPO / "infrastructure/aws_resources.md").read_text()
    for path in FREE_WEEKLY_PATHS:
        assert path in doc, f"{path} is public in code but absent from the authorizer inventory"
    assert PAID_WEEKLY_PATH not in doc.split("authorization-type NONE")[-1], (
        "the paid weekly route must not be listed as an authorizer-NONE route"
    )
