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


def test_manifest_endpoint_serves_local(board_dir):
    out = fantasy.nfl_manifest(season=2026)
    assert out["season"] == 2026


def test_board_endpoint_serves_local(board_dir):
    out = fantasy.nfl_board(config="full_ppr", size=12, season=2026)
    assert out == [{"id": "1", "pos": "RB"}]


def test_board_endpoint_404_on_missing(board_dir):
    with pytest.raises(HTTPException) as exc:
        fantasy.nfl_board(config="superflex", size=10, season=2026)
    assert exc.value.status_code == 404


def test_board_endpoint_rejects_path_traversal(board_dir):
    with pytest.raises(HTTPException) as exc:
        fantasy.nfl_board(config="../../etc/passwd", size=12, season=2026)
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


def test_router_declares_the_fantasy_gate():
    # Every route in the router must sit behind require_fantasy_access.
    dep_calls = [d.dependency for d in fantasy.router.dependencies]
    assert deps.require_fantasy_access in dep_calls
