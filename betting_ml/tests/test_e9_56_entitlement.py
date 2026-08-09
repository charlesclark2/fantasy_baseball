"""E9.56 — guards for the server-side entitlement resolution and the locked-marker redaction.

🗄️ SCOPE CHANGED AT THE FREEMIUM BUILD (2026-08-08). The generic board is now FREE for every
caller, so the redaction below is RETIRED from every live route and the three e2e tests asserting
"anonymous gets a locked payload" were replaced (see the block above
`test_the_locked_redaction_is_retired_from_every_live_route`). What this file still owns, and what
is still live and load-bearing:

  ✅ `resolve_entitlement` + `jwt_verify` — MORE load-bearing than before, not less: the generic
     routes are reachable without the API Gateway authorizer, so a Bearer token on them is
     attacker-controlled, and this is what decides who gets the PAID capabilities.
  ✅ The redaction unit tests — the mechanism must still work if the operator ever withdraws the
     open board.
  ➡️ The LIVE free/paid behaviour is owned by `test_freemium_tier.py`.

Every test here was RED-proven against deliberately-broken source before being trusted (a guard that
cannot fail is worse than none — INC-38/INC-39). The four breaks used, and what went red:

  1. `_lock_row` returns `row` unchanged            → 4 RED (the leak guards)
  2. `lock_projection_rows` drops the `sorted(...)` → 2 RED (the ordering guards)
  3. allowlist → denylist in `_lock_row`            → 1 RED (unknown-field-locked-by-default)
  4. `resolve_entitlement` falls back to the
     unverified decode when claims are absent       → 2 RED (the forged-token guards)

⚠️ THE ORDERING GUARDS ARE THE NON-OBVIOUS HALF. Blanking every number while keeping the array
order still hands over the ranking — `projections.json` is sorted by our projection and
`board_*.json` by `ovrRank`, so the array INDEX is the rank. A redaction that looks complete
field-by-field can leak the single most valuable output we have, which is why "no value survives"
and "no ORDER survives" are separate assertions.
"""

from __future__ import annotations

import base64
import json

import pytest

from app.backend.services import entitlement


# ── fixtures: shaped like the REAL published payloads ────────────────────────────────────────────
# Field names and the model/public split are taken from the live
# s3://credence-prod-s3-api-cache/fantasy/nfl/2026/{projections,board_full_ppr_12}.json (read
# 2026-08-04), not invented — a fixture that drifts from the real export would make these vacuous.


def _projection_row(name, pos, fp, adp, ident):
    return {
        "id": ident,
        "name": name,
        "pos": pos,
        "team": "BUF",
        "bye": 7,
        "rookie": False,
        "draftPick": None,
        "conf": "high",
        "g": 16.5,
        "fpStd": fp,
        "fpHalf": fp,
        "fpPpr": fp,
        "fpSd": 73.0,
        "fpP10": fp - 100,
        "fpP90": fp + 100,
        "uncType": "calibrated_per_player",
        "adp": adp,
        "lowPred": False,
        "predNote": None,
        "contrib": {"totalPts": fp, "drivers": [{"feature": "pergame_fp", "pts": 39.2}]},
        "mktLean": "market-led-adaptive",
        "passYds": 3504.4,
        "passTd": 24.0,
        "rushYds": 456.9,
        "college": "Wyoming",
        "yearsExp": 9,
    }


def _board_row(name, pts, ovr, adp, ident):
    return {
        "id": ident,
        "name": name,
        "pos": "RB",
        "team": "ATL",
        "bye": 11,
        "rookie": False,
        "g": 15.2,
        "pts": pts,
        "ptsP10": pts - 100,
        "ptsP90": pts + 60,
        "repl": 131.4,
        "vor": pts - 131.4,
        "posRank": ovr,
        "ovrRank": ovr,
        "vorP10": -27.5,
        "vorP90": 217.0,
        "adp": adp,
        "lowPred": False,
        "predNote": None,
    }


# Deliberately ADVERSARIAL ordering: our projection order (A, B, C) is the REVERSE of the market's
# ADP order, so a redaction that leaves the array untouched is detectable — under a "sorted by ADP"
# assertion, a payload that merely preserved our order would fail.
PROJECTION_ROWS = [
    _projection_row("Alpha Player", "QB", 325.7, 28.1, "id-a"),
    _projection_row("Bravo Player", "QB", 318.2, 15.3, "id-b"),
    _projection_row("Charlie Player", "QB", 311.4, 4.2, "id-c"),
]

BOARD_ROWS = [
    _board_row("Alpha Player", 280.7, 1, 9.9, "id-a"),
    _board_row("Bravo Player", 240.1, 2, 5.5, "id-b"),
    _board_row("Charlie Player", 210.0, 3, 1.7, "id-c"),
]

PROJECTIONS_PAYLOAD = {
    "season": 2026,
    "generated_at": "2026-08-04T04:49:33Z",
    "source": "local-artifacts",
    "adp_format": "ppr",
    "adp_teams": 12,
    "projection_source": "nf1_5",
    "projection_label": "market-aware refined (NF1.5)",
    "market_lean": {"QB": "market-led-adaptive"},
    "market_lean_note": "At positions labelled market-led ...",
    "model_version": "nfl_fantasy_nf1_v1",
    "base_season": 2025,
    "players": PROJECTION_ROWS,
}

MANIFEST_PAYLOAD = {
    "season": 2026,
    "generated_at": "2026-08-04T04:49:33Z",
    "source": "local-artifacts",
    "positions": ["QB", "RB", "WR", "TE", "K", "DST"],
    "projectionSource": "nf1_5",
    "projectionLabel": "market-aware refined (NF1.5)",
    "sizes": [10, 12],
    "configs": [{"name": "full_ppr", "label": "Full-PPR", "roster": [{"name": "QB", "count": 1}]}],
    "projections": {
        "players": 858,
        "adp_format": "ppr",
        "market_lean_note": "honest caveat text",
        "model_version": "nfl_fantasy_nf1_v1",
    },
    "featureLegend": {"pergame_fp": "per-game fantasy points"},
    "featureContributionsMeta": {"model_version": "nfl_fantasy_nf1_v1", "n_players": 703},
}

# Every model-produced NUMBER in the fixtures. A locked payload may contain none of them.
_SECRET_NUMBERS = {325.7, 318.2, 311.4, 73.0, 16.5, 3504.4, 456.9, 280.7, 240.1, 210.0, 149.3}


def _all_scalars(obj):
    """Every scalar anywhere in a nested payload — the leak check must be recursive, or a value
    hiding inside a nested dict (`contrib.totalPts`) passes a top-level-keys-only assertion."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _all_scalars(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_scalars(v)
    else:
        yield obj


# ── the leak guards ──────────────────────────────────────────────────────────────────────────────


def test_locked_projections_carry_no_model_value_anywhere():
    out = entitlement.lock_projections_payload(PROJECTIONS_PAYLOAD)
    numbers = {v for v in _all_scalars(out) if isinstance(v, (int, float)) and not isinstance(v, bool)}
    leaked = numbers & _SECRET_NUMBERS
    assert not leaked, f"locked projections payload leaked model values: {leaked}"


def test_locked_projections_drop_every_model_field():
    out = entitlement.lock_projections_payload(PROJECTIONS_PAYLOAD)
    for row in out["players"]:
        for banned in (
            "fpStd", "fpHalf", "fpPpr", "fpSd", "fpP10", "fpP90",
            "g", "conf", "uncType", "lowPred", "predNote", "contrib", "mktLean",
            "passYds", "passTd", "rushYds",
        ):
            assert banned not in row, f"{banned} survived redaction"


def test_locked_board_drops_the_ranks_and_the_points():
    out = entitlement.lock_board_payload(BOARD_ROWS)
    for row in out:
        for banned in ("pts", "ptsP10", "ptsP90", "repl", "vor", "posRank", "ovrRank", "vorP10", "vorP90", "g"):
            assert banned not in row, f"{banned} survived board redaction"
    numbers = {v for v in _all_scalars(out) if isinstance(v, (int, float)) and not isinstance(v, bool)}
    assert not (numbers & _SECRET_NUMBERS)


def test_locked_rows_keep_public_identity_so_the_cta_has_something_to_render():
    """The whole point of a marker over an omission: the row must still be recognisable."""
    out = entitlement.lock_projections_payload(PROJECTIONS_PAYLOAD)
    assert len(out["players"]) == len(PROJECTION_ROWS)
    for row in out["players"]:
        assert row["locked"] is True
        assert row["name"] and row["pos"] and row["id"]


def test_locked_payload_names_the_locked_fields_for_the_cta():
    out = entitlement.lock_projections_payload(PROJECTIONS_PAYLOAD)
    assert out["locked"] is True
    assert out["entitled"] is False
    assert out["lockedSeason"] == entitlement.LOCKED_SEASON
    assert "fpPpr" in out["lockedFields"] and "contrib" in out["lockedFields"]
    assert out["upgrade"]["reason"] == "subscription_required"


def test_manifest_keeps_the_page_shell_but_drops_the_attribution_metadata():
    out = entitlement.lock_manifest_payload(MANIFEST_PAYLOAD)
    assert out["positions"] and out["configs"] and out["sizes"]
    # Payload minimization: these exist only to label the entitled `contrib` panel.
    assert "featureLegend" not in out
    assert "featureContributionsMeta" not in out


# ── the ORDERING guards (the non-obvious leak) ───────────────────────────────────────────────────


def test_locked_projections_do_not_preserve_our_ranking_order():
    """Our order is A,B,C; the public (ADP) order is C,B,A. A locked payload must not be ours."""
    out = entitlement.lock_projections_payload(PROJECTIONS_PAYLOAD)
    names = [r["name"] for r in out["players"]]
    ours = [r["name"] for r in PROJECTION_ROWS]
    assert names != ours, "array order still reconstructs our ranking"
    assert names == ["Charlie Player", "Bravo Player", "Alpha Player"], names


def test_locked_board_order_is_market_adp_not_our_ovrrank():
    out = entitlement.lock_board_payload(BOARD_ROWS)
    names = [r["name"] for r in out]
    assert names != [r["name"] for r in BOARD_ROWS]
    assert names == ["Charlie Player", "Bravo Player", "Alpha Player"], names


def test_rows_without_adp_sort_last_and_do_not_crash():
    rows = PROJECTION_ROWS + [_projection_row("Zulu Undrafted", "QB", 90.0, None, "id-z")]
    out = entitlement.lock_projections_payload({**PROJECTIONS_PAYLOAD, "players": rows})
    assert out["players"][-1]["name"] == "Zulu Undrafted"


# ── allowlist-by-default: the property that survives the NEXT exporter change ────────────────────


def test_an_unknown_new_field_is_locked_by_default():
    """A denylist would make the next field the exporter adds public on the next publish, with no
    code change and no failing test. This is the single assertion that catches that class."""
    rows = [{**PROJECTION_ROWS[0], "nf_d21_brand_new_projection": 412.7}]
    out = entitlement.lock_projections_payload({**PROJECTIONS_PAYLOAD, "players": rows})
    assert "nf_d21_brand_new_projection" not in out["players"][0]
    assert 412.7 not in set(_all_scalars(out))
    # ...and it must be ADVERTISED as locked, so it renders a CTA rather than silently vanishing.
    assert "nf_d21_brand_new_projection" in out["lockedFields"]


def test_entitled_payload_is_unchanged_apart_from_the_additive_keys():
    """NF-C0: no key the deployed client reads may be removed, renamed, or reordered away."""
    out = entitlement.open_projections_payload(PROJECTIONS_PAYLOAD)
    for k, v in PROJECTIONS_PAYLOAD.items():
        assert out[k] == v, f"entitled payload altered {k}"
    assert out["locked"] is False and out["entitled"] is True


def test_board_stays_a_list_in_both_modes():
    """An envelope object here would be the NF-C0 blank-screen break."""
    assert isinstance(entitlement.lock_board_payload(BOARD_ROWS), list)


# ── season boundary ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("season,locked", [(2019, False), (2025, False), (2026, True), (2027, True)])
def test_free_is_strictly_past_seasons(season, locked):
    assert entitlement.is_locked_season(season) is locked


def test_locked_season_agrees_across_all_three_owners():
    """One logical constant, three owners (INC-38). A drift here silently publishes a paid season."""
    from pathlib import Path

    from app.backend.routers import fantasy_public

    assert fantasy_public._LOCKED_SEASON == entitlement.LOCKED_SEASON

    writer = Path("quant_sports_intel_models/football/nfl/fantasy/export_track_record_json.py")
    if writer.is_file():
        src = [
            ln for ln in writer.read_text().splitlines()
            if ln.strip().startswith("LOCKED_SEASON") and "=" in ln
        ]
        assert src, "export_track_record_json.py no longer defines LOCKED_SEASON"
        assert str(entitlement.LOCKED_SEASON) in src[0], src[0]


# ── the forged-token guards ──────────────────────────────────────────────────────────────────────


class _FakeRequest:
    """Minimal Request stand-in: headers + the API-Gateway event scope."""

    def __init__(self, headers=None, aws_event=None):
        self.headers = headers or {}
        self.scope = {"aws.event": aws_event} if aws_event is not None else {}


def _unsigned_token(groups):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    return (
        b64({"alg": "RS256", "kid": "attacker"})
        + "."
        + b64({"sub": "attacker", "cognito:groups": groups, "token_use": "access", "exp": 9999999999})
        + ".not-a-real-signature"
    )


def test_a_forged_token_without_the_gateway_authorizer_is_anonymous(monkeypatch):
    """THE breach this story exists to prevent.

    On a route whose API Gateway authorization-type is `NONE` there is no upstream validation and
    the caller controls the whole token (measured live 2026-08-04: a forged JWT returns 200 on the
    public track-record route while gated routes 401). If entitlement were read through the usual
    unverified decode, base64-encoding `{"cognito:groups":["subscriber"]}` would buy the paid 2026
    projections. JWKS is monkeypatched to unreachable so the test never touches the network and so
    the "verifier is unavailable" path is exercised too — it must fail CLOSED.
    """
    from app.backend.services import jwt_verify

    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()

    req = _FakeRequest(headers={"Authorization": "Bearer " + _unsigned_token(["subscriber", "admin"])})
    ent = entitlement.resolve_entitlement(req)

    assert ent.fantasy is False
    assert ent.source == "anonymous"
    assert ent.groups == ()


def test_a_forged_token_cannot_reach_groups_through_the_dependency_helper(monkeypatch):
    """Same breach, via the OTHER door: `require_fantasy_access` reads `_groups_from_request`."""
    from app.backend.dependencies import _groups_from_request
    from app.backend.services import jwt_verify

    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()

    req = _FakeRequest(headers={"Authorization": "Bearer " + _unsigned_token(["subscriber"])})
    assert _groups_from_request(req) == []


def test_gateway_validated_claims_are_still_trusted():
    """The authorizer path must keep working exactly as before — this is the no-regression half.
    Without it, tightening the bearer union could silently 403 every real subscriber."""
    req = _FakeRequest(
        headers={},
        aws_event={
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "real-user", "cognito:groups": "[subscriber]"}}}
            }
        },
    )
    ent = entitlement.resolve_entitlement(req)
    assert ent.source == "gateway"
    assert ent.fantasy is True
    assert ent.user_id == "real-user"


def test_no_token_at_all_is_anonymous_and_locked():
    ent = entitlement.resolve_entitlement(_FakeRequest())
    assert ent.is_anonymous and ent.fantasy is False


@pytest.mark.parametrize("alg", ["none", "HS256", "RS512"])
def test_non_rs256_algorithms_are_refused(alg):
    """The classic JWT confusion attack — never take the token's word for its own algorithm."""
    from app.backend.services import jwt_verify

    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    token = b64({"alg": alg, "kid": "k"}) + "." + b64({"sub": "x"}) + ".sig"
    assert jwt_verify.verify_cognito_token(token) is None


# ── END-TO-END through the REAL app ──────────────────────────────────────────────────────────────
# Everything above tests the policy functions directly. These drive the ACTUAL FastAPI stack —
# route → router dependencies → resolve_entitlement → redaction → JSON serialization — with only
# the S3 read stubbed, because a policy that is correct in isolation and never reaches the response
# is the defect this codebase keeps re-finding (E9.41's Pydantic model silently dropping a field;
# INC-39's op-level test that monkeypatched the real leg away and asserted against a string the test
# author wrote). The `--authorization-type NONE` launch state cannot be exercised against prod until
# the operator flips the gateway route, so this is the only pre-launch proof of that path.


@pytest.fixture()
def app_env(monkeypatch):
    """Stub ONLY the two IO boundaries (the S3 read, the JWKS fetch). Everything else — routing,
    router dependencies, the entitlement resolver, the redaction, JSON serialization — is the real
    thing.

    Driven through raw ASGI rather than starlette's TestClient on purpose: TestClient needs `httpx`
    (absent from this env, and a test-only dependency in the merge-gating CI image is a poor trade),
    AND it offers no way to set the `aws.event` scope key that Mangum uses to carry the API Gateway
    authorizer context — which is precisely the thing that separates a real subscriber from a
    forged token here. Raw ASGI gives both for free.
    """
    from app.backend.routers import fantasy
    from app.backend.services import jwt_verify

    def fake_load(rel_key: str, sport: str = "nfl"):
        if rel_key.endswith("projections.json"):
            return PROJECTIONS_PAYLOAD
        if rel_key.endswith("manifest.json"):
            return MANIFEST_PAYLOAD
        if "board_" in rel_key:
            return BOARD_ROWS
        return None

    monkeypatch.setattr(fantasy, "_load_json", fake_load)
    # No network: an unreachable JWKS makes every presented token unverifiable — which is both the
    # anonymous path we assert on and a proof that the verifier fails CLOSED when it is unavailable.
    monkeypatch.setattr(jwt_verify, "_fetch_jwks", lambda: None)
    jwt_verify.reset_jwks_cache()
    return True


def _call(path: str, query: str = "", *, headers: dict | None = None, aws_event: dict | None = None):
    """Drive the real ASGI app. Returns (status, parsed_json)."""
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
    return out["status"], json.loads(b"".join(body_parts))


def _entitled_headers():
    """Simulate the API Gateway authorizer context for a real subscriber, the way Mangum delivers
    it — the ONE shape that legitimately grants access."""
    return {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "sub-1", "cognito:groups": "[subscriber]"}}}
        }
    }


# ── 🗄️ THE THREE "ANONYMOUS GETS A LOCKED PAYLOAD" E2E TESTS WERE RETIRED (freemium build) ───────
#
# They asserted the OPPOSITE of what the product now does: the generic board is free, so an
# anonymous caller receives the real numbers. Their replacements — including the forged-token case,
# which still matters and now asserts that a forged token changes nothing rather than that it
# unlocks nothing — live in `test_freemium_tier.py`, which owns the live behaviour.
#
# ⭐ WHAT REPLACES THEM HERE IS ONE CLAUSE WITH A DIFFERENT JOB, and it is the reason this file did
# not simply shrink. The redaction unit tests above still pass because the machinery still WORKS;
# nothing in them can tell you it is no longer CALLED. Left at that, this file would read as live
# coverage of a live gate — the most misleading state a retired mechanism can be in. The clause
# below makes "retired" an asserted fact instead of a comment, and makes silently re-wiring the
# lock — which would re-gate the free board with no operator decision — a red build.


def test_the_locked_redaction_is_retired_from_every_live_route(app_env):
    """⭐ THE REDACTION EXISTS AND NOTHING CALLS IT. Both halves are the assertion.

    Withdrawing the open board is a pricing decision the operator may want back, so the mechanism is
    kept and still unit-tested above. But a reader who found `lock_projections_payload` in this file
    and assumed it described what users receive would be wrong, and a session that re-wired it would
    silently un-ship the freemium build.

    Asserted on the ROUTER SOURCE rather than on a response, so it fails on the re-wiring itself
    rather than only once a payload happens to be exercised."""
    from pathlib import Path

    src = Path("app/backend/routers/fantasy.py").read_text()
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))
    called = [fn for fn in ("lock_projections_payload", "lock_manifest_payload", "lock_board_payload")
              if f"entitlement.{fn}" in code]
    assert not called, (
        f"{called} is called from a live route — the generic board is being redacted again. That is "
        f"a pricing decision, not a refactor: see test_freemium_tier.py."
    )
    # The other half: the machinery is still here to be re-wired if that decision is ever made.
    assert callable(entitlement.lock_projections_payload)


def test_e2e_a_gateway_validated_subscriber_gets_the_REAL_numbers(app_env):
    """The no-regression half. Without it, a redaction bug that locked EVERYONE would satisfy every
    leak assertion above — the suite would be perfectly green and the paid product broken."""
    status, body = _call("/fantasy/nfl/projections", "season=2026", aws_event=_entitled_headers())
    assert status == 200
    assert body["locked"] is False and body["entitled"] is True
    assert body["players"][0]["fpPpr"] == 325.7, "an entitled subscriber lost the real numbers"
    assert [p["name"] for p in body["players"]] == [p["name"] for p in PROJECTION_ROWS]


def test_e2e_a_past_season_is_free_for_everyone(app_env):
    """The NF3.2 half of the operator's rule: past seasons are public by design."""
    status, body = _call("/fantasy/nfl/projections", "season=2025")
    assert status == 200
    assert body["locked"] is False, "a PAST season was locked — the free tier is broken"
    assert body["players"][0]["fpPpr"] == 325.7


def test_e2e_the_gated_router_still_403s_a_non_entitled_caller(app_env):
    """The dual-mode router must NOT have widened anything else. `/fantasy/nfl/my-teams` stays on
    the gated router, so a caller with a validated token but no fantasy entitlement is refused
    outright rather than served a locked payload."""
    beta_only = {
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"sub": "sub-2", "cognito:groups": "[beta_tester]"}}}
        }
    }
    status, _ = _call("/fantasy/nfl/my-teams", "season=2026", aws_event=beta_only)
    assert status == 403
