"""NF3.2 — the public fantasy football track-record router (`fantasy_public.py`), deliberately
carrying NO entitlement gate.

Mirrors `test_fantasy_entitlement.py`'s local-dir fixture pattern (endpoint functions called
directly, no S3/network). The properties this file exists to prove: (1) the router carries no
`require_fantasy_access` / `require_fantasy_beta_access` dependency ANYWHERE, unlike every other
`/fantasy/*` router — the whole point of NF3.2's season-scoped entitlement split; (2) a request for
the current/locked season is rejected by the route's own path constraint, never attempted as a read.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.backend import dependencies as deps
from app.backend.routers import fantasy, fantasy_public


@pytest.fixture()
def track_record_dir(tmp_path, monkeypatch):
    d = tmp_path / "track_record"
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"seasons": [2024], "headline": "..."}))
    (d / "season_2024.json").write_text(json.dumps([{"playerId": "1", "position": "RB"}]))
    # fantasy_public reuses fantasy._load_json, which reads fantasy._LOCAL_BOARD_DIR — same
    # local-dir override the gated router's own tests patch.
    monkeypatch.setattr(fantasy, "_LOCAL_BOARD_DIR", str(tmp_path))
    return tmp_path


def test_manifest_endpoint_serves_local_with_no_auth_call(track_record_dir):
    out = fantasy_public.track_record_manifest()
    assert out["seasons"] == [2024]


def test_season_endpoint_serves_local(track_record_dir):
    out = fantasy_public.track_record_season(season=2024)
    assert out == [{"playerId": "1", "position": "RB"}]


def test_season_endpoint_404_on_missing_season(track_record_dir):
    with pytest.raises(HTTPException) as exc:
        fantasy_public.track_record_season(season=2019)
    assert exc.value.status_code == 404


def test_router_carries_no_entitlement_gate():
    """The whole point of this router: no require_fantasy_access / require_fantasy_beta_access
    dependency anywhere, unlike every other /fantasy/* router (see test_router_declares_the_fantasy_
    gate in test_fantasy_entitlement.py for the inverse assertion on the gated router)."""
    dep_calls = [d.dependency for d in fantasy_public.router.dependencies]
    assert deps.require_fantasy_access not in dep_calls
    assert deps.require_fantasy_beta_access not in dep_calls
    for route in fantasy_public.router.routes:
        route_deps = [d.call for d in route.dependant.dependencies]
        assert deps.require_fantasy_access not in route_deps
        assert deps.require_fantasy_beta_access not in route_deps


def test_locked_season_is_rejected_by_the_routes_own_path_constraint():
    """The `season` path parameter's own `le` bound must stop one below LOCKED_SEASON, so a request
    for the current/locked season is rejected by FastAPI's Path(...) validation layer BEFORE the
    endpoint body ever runs (never a "not found yet" 404 — a structurally different, un-probeable
    rejection). Inspects the route's compiled field constraint directly (no TestClient/httpx
    dependency needed to prove FastAPI would enforce it)."""
    season_route = next(
        r for r in fantasy_public.router.routes if r.path == "/fantasy/nfl/track-record/{season}"
    )
    season_param = next(p for p in season_route.dependant.path_params if p.name == "season")
    le_constraints = [m.le for m in season_param.field_info.metadata if hasattr(m, "le")]
    assert le_constraints == [fantasy_public._LOCKED_SEASON - 1]
