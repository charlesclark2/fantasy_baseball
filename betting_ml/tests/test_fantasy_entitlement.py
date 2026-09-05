"""E9.45 — server-side fantasy entitlement gate (per-SURFACE model).

Betting is grandfathered (untouched); fantasy is `subscriber` / `admin` / the
`fantasy_comp` allow-list ONLY (beta_tester deliberately excluded). This exercises
the backend half of the defense-in-depth pair — the client nav gate is not the only
thing standing between a non-subscriber and the paid board data.

No network / no boto3 / no TestClient — dependency + service functions are called
directly with a fabricated API-Gateway Request, matching test_stripe_billing.py.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.backend import dependencies as deps
from app.backend.routers import fantasy
from app.backend.services import cognito


# ── helpers ──────────────────────────────────────────────────────────────────


def _request(ctx_groups=None, auth_token=None, sub="user-1") -> Request:
    """A minimal Request. `ctx_groups` populates the API-Gateway authorizer claims
    (the preferred path); `auth_token` sets an Authorization bearer (the fallback)."""
    claims: dict = {"sub": sub}
    if ctx_groups is not None:
        claims["cognito:groups"] = ",".join(ctx_groups)
    scope = {
        "type": "http",
        "headers": [],
        "aws.event": {"requestContext": {"authorizer": {"jwt": {"claims": claims}}}},
    }
    if auth_token is not None:
        scope["headers"] = [(b"authorization", f"Bearer {auth_token}".encode())]
    return Request(scope)


def _bearer(groups, sub="user-1") -> str:
    """A fake (unsigned) JWT whose payload carries cognito:groups — the fallback path
    decodes the payload without verification (safe: API GW validated it upstream)."""
    payload = {"sub": sub, "cognito:groups": list(groups)}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"header.{b64}.sig"


# ── the group-membership predicate ───────────────────────────────────────────


@pytest.mark.parametrize(
    "groups,expected",
    [
        (["subscriber"], True),
        (["admin"], True),
        (["fantasy_comp"], True),
        (["subscriber", "fantasy_comp"], True),
        (["beta_tester"], False),          # the deliberate divergence from E9.8
        (["churned"], False),
        ([], False),
        (["beta_tester", "churned"], False),
    ],
)
def test_has_fantasy_access(groups, expected):
    assert cognito.has_fantasy_access(groups) is expected


def test_fantasy_comp_is_separate_from_subscriber():
    # The comp allow-list must NOT be the subscriber group (keeps the founding-100
    # count accurate) — but both grant fantasy.
    assert cognito.GROUP_FANTASY_COMP != cognito.GROUP_SUBSCRIBER
    assert cognito.has_fantasy_access(["fantasy_comp"])
    # A comp is not a subscriber, so it must not read as a paying tier.
    assert cognito.GROUP_FANTASY_COMP not in {cognito.GROUP_SUBSCRIBER, cognito.GROUP_BETA}


# ── the dependency (authorizer-context path) ─────────────────────────────────


@pytest.mark.parametrize("groups", [["subscriber"], ["admin"], ["fantasy_comp"]])
def test_require_fantasy_access_grants_via_context(groups):
    assert deps.require_fantasy_access(_request(ctx_groups=groups), "user-1") == "user-1"


@pytest.mark.parametrize("groups", [["beta_tester"], ["churned"], []])
def test_require_fantasy_access_denies_via_context(groups):
    with pytest.raises(HTTPException) as exc:
        deps.require_fantasy_access(_request(ctx_groups=groups), "user-1")
    assert exc.value.status_code == 403


def test_beta_tester_keeps_betting_but_is_denied_fantasy():
    # The whole point of the per-surface split: a beta_tester is blocked at the
    # fantasy gate even though the app leaves their betting access untouched.
    req = _request(ctx_groups=["beta_tester"])
    with pytest.raises(HTTPException) as exc:
        deps.require_fantasy_access(req, "user-1")
    assert exc.value.status_code == 403


# ── the dependency (bearer-token fallback path) ──────────────────────────────


def test_require_fantasy_access_grants_via_bearer_fallback():
    # No cognito:groups in the authorizer context → decode the bearer payload.
    req = _request(ctx_groups=None, auth_token=_bearer(["fantasy_comp"]))
    assert deps.require_fantasy_access(req, "user-1") == "user-1"


def _request_raw_ctx(raw_groups: str) -> Request:
    """A Request whose authorizer context carries cognito:groups as a raw string, to
    exercise the exact API-Gateway HTTP-API v2 bracketed/space delimiter format."""
    scope = {
        "type": "http",
        "headers": [],
        "aws.event": {
            "requestContext": {
                "authorizer": {"jwt": {"claims": {"sub": "u", "cognito:groups": raw_groups}}}
            }
        },
    }
    return Request(scope)


@pytest.mark.parametrize(
    "raw,granted",
    [
        ("[fantasy_comp subscriber]", True),   # HTTP API v2 bracketed + space-separated
        ("[fantasy_comp]", True),
        ("[beta_tester churned]", False),      # bracketed, no fantasy tier
        ("subscriber,fantasy_comp", True),     # comma style
        ("[beta_tester]", False),
    ],
)
def test_require_fantasy_access_parses_gateway_group_formats(raw, granted):
    # The 403-on-a-real-comp bug: a bracketed context claim was comma-split into garbage
    # and never fell back → a legit fantasy_comp user was rejected. Both formats must work.
    req = _request_raw_ctx(raw)
    if granted:
        assert deps.require_fantasy_access(req, "u") == "u"
    else:
        with pytest.raises(HTTPException) as exc:
            deps.require_fantasy_access(req, "u")
        assert exc.value.status_code == 403


def test_require_fantasy_access_denies_via_bearer_fallback():
    req = _request(ctx_groups=None, auth_token=_bearer(["beta_tester"]))
    with pytest.raises(HTTPException) as exc:
        deps.require_fantasy_access(req, "user-1")
    assert exc.value.status_code == 403


# ── the data endpoints (local-dir source; no S3) ─────────────────────────────


@pytest.fixture()
def board_dir(tmp_path, monkeypatch):
    season = tmp_path / "2026"
    season.mkdir()
    (season / "manifest.json").write_text(json.dumps({"season": 2026, "configs": []}))
    (season / "board_full_ppr_12.json").write_text(json.dumps([{"id": "1", "pos": "RB"}]))
    (season / "projections.json").write_text(
        json.dumps({"season": 2026, "model_version": "v1", "players": [{"id": "1", "pos": "RB"}]})
    )
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    return tmp_path


# ⭐ TWO OF THE THREE HANDLERS TAKE NO CALLER AT ALL, and the missing parameter is the point rather
# than an accident. The manifest and the projections are `Capability.GENERIC_BOARD` and are
# format-INDEPENDENT, so a handler that cannot see who is asking cannot branch on them — the
# strongest available statement that those payloads are entitlement-independent.
#
# ⚠️ `nfl_board` IS THE EXCEPTION and takes a `request`. Since 2026-08-08 exactly one preset
# (`full_ppr`/12) is free and the other thirteen are paid, so that route has to know its caller.
# Both facts are asserted, in opposite directions, by `test_the_generic_board_handlers_take_no_caller`
# and `test_the_board_handler_does_take_a_caller` below — either alone is satisfiable by breaking the
# other.
#
# 🗄️ HISTORY, because these signatures have now moved three times and each move was a real change:
#   · pre-E9.56 they took no Request and 403'd a non-entitled caller at the ROUTER.
#   · E9.56 gave them a Request so they could serve a LOCKED payload instead of a 403.
#   · the freemium build removed it again — nothing was locked, so nothing needed the caller.
#   · the format split gave it back to `nfl_board` alone.
#
# What these tests have always asserted is the READ ITSELF: the right blob, the right container
# type, and 404/422 where they belong. That is preserved verbatim. The free/paid split is asserted
# in `test_freemium_tier.py`; `test_e9_56_entitlement.py` keeps the retired redaction's unit tests.


def test_manifest_endpoint_serves_local(board_dir):
    out = fantasy.nfl_manifest(season=2026)
    assert out["season"] == 2026
    # The additive envelope survives the flip and now says `false` for everyone — dropping the key
    # would be the NF-C0 break, since the deployed client branches on it.
    assert out["locked"] is False


def test_board_endpoint_serves_local(board_dir):
    # ⚠️ TAKES A `request` SINCE THE FREEMIUM FORMAT SPLIT — one preset is free and thirteen are
    # paid, so this route (alone among the three) has to see its caller. `full_ppr`/12 is the free
    # one, so an anonymous request is the right fixture here.
    out = fantasy.nfl_board(_request(), config="full_ppr", size=12, season=2026)
    # Still the raw list, byte-for-byte (NF-C0: the container type and contents must not move for
    # anyone who could already read it).
    assert out == [{"id": "1", "pos": "RB"}]


def test_board_endpoint_404_on_missing(board_dir):
    # ⚠️ ENTITLED, DELIBERATELY. `superflex`/10 is a PAID preset, so an anonymous caller would be
    # refused with a 403 before the read ever happens and this clause would assert the paywall
    # while claiming to test the missing-file path — a test passing for the wrong reason.
    with pytest.raises(HTTPException) as exc:
        fantasy.nfl_board(
            _request(ctx_groups=["subscriber"]), config="superflex", size=10, season=2026
        )
    assert exc.value.status_code == 404


def test_board_endpoint_rejects_path_traversal(board_dir):
    with pytest.raises(HTTPException) as exc:
        fantasy.nfl_board(_request(), config="../../etc/passwd", size=12, season=2026)
    assert exc.value.status_code == 422


def test_projections_endpoint_serves_local(board_dir):
    # NF3 — the browse Projections surface reads this blob.
    out = fantasy.nfl_projections(season=2026)
    assert out["season"] == 2026
    assert out["players"] == [{"id": "1", "pos": "RB"}]


def test_projections_endpoint_404_on_missing(board_dir):
    # The blob is exported separately from the boards, so a season with boards but no projections
    # must 404 (the UI shows an honest empty state) rather than 500.
    with pytest.raises(HTTPException) as exc:
        fantasy.nfl_projections(season=2025)
    assert exc.value.status_code == 404


def test_the_generic_board_handlers_take_no_caller(board_dir):
    """🗄️ REPLACES `test_a_non_entitled_caller_is_not_403d_but_locked`, which asserted the E9.56
    behaviour this story retired (a non-entitled caller got a 200 with the values removed).

    ⭐ Kept as a clause rather than deleted, because the *signature* is load-bearing and nothing else
    in this file would notice it changing. A `Request` parameter reappearing here is the first step
    of re-gating the free board, and it would type-check, build and pass every other test in this
    module — the handlers would simply start being able to tell callers apart again.

    ⚠️ `nfl_board` IS EXCLUDED, DELIBERATELY, AND IS ASSERTED THE OTHER WAY BELOW. Since the free
    tier narrowed to one preset (2026-08-08) that route must read its caller — one board is free and
    thirteen are not. The two format-independent payloads are the ones that still cannot vary."""
    import inspect

    for handler in (fantasy.nfl_manifest, fantasy.nfl_projections):
        params = inspect.signature(handler).parameters
        assert "request" not in params, (
            f"{handler.__name__} takes a Request again — a generic-board handler that can see its "
            f"caller can branch on them; see test_freemium_tier.py"
        )


def test_the_board_handler_does_take_a_caller():
    """The other side of the clause above, so 'no handler takes a Request' cannot be satisfied by
    dropping the one that must. `nfl_board` gates the paid presets and therefore has to know who is
    asking; a signature that loses `request` again would make every preset free without a single
    other test noticing."""
    import inspect

    assert "request" in inspect.signature(fantasy.nfl_board).parameters, (
        "nfl_board can no longer see its caller — every paid preset is now free"
    )


def test_router_declares_the_fantasy_gate():
    # Every route in the router must sit behind require_fantasy_access.
    dep_calls = [d.dependency for d in fantasy.router.dependencies]
    assert deps.require_fantasy_access in dep_calls


def test_exactly_the_enumerated_routes_live_outside_the_fantasy_gate():
    """E9.56 — the exemption must stay an ENUMERATED list, not an open door.

    The generic-board reads live on a second router with no `require_fantasy_access` (this
    codebase's idiom: an exemption is a separate router object, never a flag inside the gated one).
    The failure mode that idiom exists to prevent is a route quietly joining the un-gated router — a
    write endpoint, or `/nfl/my-teams` (a user's OWN leagues), would then be readable by anyone.
    Pinning the exact set makes that a failing test rather than a silent leak.

    ⭐ GROWING THIS SET IS A REVIEWABLE ACT, WHICH IS THE WHOLE POINT. NF-C6-PH2 added the two FREE
    weekly reads and this guard is what forced them to be declared here rather than absorbed. They
    belong outside the gate for the same reason the season pair does: neither handler takes a
    `Request`, so neither can see its caller, and their bytes are identical for anonymous, free and
    paying callers alike — which is what the CDN entry, `cache_control_for` and the client's
    `entitled`-keyed query cache all rest on.

    ⛔ `/fantasy/nfl/weekly/projections-full` is deliberately NOT here: it is the paid substrate and
    sits on the gated `router`."""
    assert {r.path for r in fantasy.board_router.routes} == {
        "/fantasy/nfl/manifest",
        "/fantasy/nfl/projections",
        "/fantasy/nfl/board",
        # NF-C6-PH2 — the free weekly half.
        "/fantasy/nfl/weekly/manifest",
        "/fantasy/nfl/weekly/projections",
    }
    assert deps.require_fantasy_access not in [d.dependency for d in fantasy.board_router.dependencies]
    # ...and every one of them is a READ. A write outside the gate would be far worse than a read.
    for route in fantasy.board_router.routes:
        assert set(route.methods) == {"GET"}, f"{route.path} is not read-only outside the gate"


# ── NF-C0b: the league-settings editor is gated NARROWER than the surface ────────────


@pytest.mark.parametrize("groups", [["admin"], ["fantasy_comp"], ["admin", "subscriber"]])
def test_require_fantasy_beta_access_grants_admin_and_comp(groups):
    assert deps.require_fantasy_beta_access(_request(groups), user_id="user-1") == "user-1"


@pytest.mark.parametrize("groups", [["subscriber"], ["beta_tester"], [], ["subscriber", "beta_tester"]])
def test_require_fantasy_beta_access_denies_everyone_else(groups):
    """A paying SUBSCRIBER is denied here while keeping the fantasy surface itself.

    That divergence is the whole point of the narrower gate, so it is asserted directly
    rather than inferred: NF-C0b ships to operator + comp accounts first.
    """
    with pytest.raises(HTTPException) as exc:
        deps.require_fantasy_beta_access(_request(groups), user_id="user-1")
    assert exc.value.status_code == 403


def test_a_subscriber_keeps_the_fantasy_surface_but_not_the_editor():
    """The two gates must diverge for exactly one group — `subscriber`."""
    req = _request(["subscriber"])
    assert deps.require_fantasy_access(req, user_id="user-1") == "user-1"  # surface: allowed
    with pytest.raises(HTTPException):
        deps.require_fantasy_beta_access(req, user_id="user-1")  # editor: denied


def test_beta_groups_are_a_strict_subset_of_fantasy_access_groups():
    """Anyone who clears the editor gate must also clear the surface gate.

    If these ever crossed, a caller could reach the league WRITE endpoints without holding
    the surface entitlement the router itself requires — an incoherent state rather than a
    merely stricter one.
    """
    assert cognito.FANTASY_BETA_GROUPS < cognito.FANTASY_ACCESS_GROUPS
    assert "subscriber" not in cognito.FANTASY_BETA_GROUPS


def test_every_league_route_carries_the_personalization_gate():
    """Every `/fantasy/leagues` route is gated, and a new one cannot ship without it.

    🗄️ THE GATE CHANGED AT G100-C1 (2026-08-08): `require_fantasy_beta_access` (`admin` +
    `fantasy_comp`) → `require_personalized_league_access` (signed in, with a personalization
    QUOTA above zero). A free account now gets ONE personalized league, so a group-list gate would
    refuse exactly the users the free tier exists for.

    ⭐ The routes also MOVED, from `fantasy.router` to `fantasy.personal_router`, and that is not
    cosmetic: their gate is now WIDER than the parent router's blanket `require_fantasy_access`,
    and a per-route dependency can only ever TIGHTEN a router-level one. So the exemption had to
    become its own mount — this repo's standing rule.

    These are WRITE endpoints; hiding the nav item stops nobody from POSTing straight to the API.
    """
    league_routes = [
        r for r in fantasy.personal_router.routes
        if getattr(r, "path", "").startswith("/fantasy/leagues")
    ]
    assert league_routes, "expected the /fantasy/leagues routes to exist"
    # The gate is declared once on the ROUTER, so assert it there and then confirm every league
    # route actually hangs off that router (a route added to the wrong object would be missed).
    router_deps = [d.dependency for d in fantasy.personal_router.dependencies]
    assert deps.require_personalized_league_access in router_deps, (
        "personal_router lost its personalization gate — every league route is now open"
    )
    from app.backend.main import app

    mounted = {
        getattr(r, "path", "") for r in app.routes
        if getattr(r, "path", "").startswith("/fantasy/leagues")
    }
    assert mounted <= {getattr(r, "path", "") for r in league_routes}, (
        f"a /fantasy/leagues route is mounted outside personal_router and is ungated: "
        f"{mounted - {getattr(r, 'path', '') for r in league_routes}}"
    )
