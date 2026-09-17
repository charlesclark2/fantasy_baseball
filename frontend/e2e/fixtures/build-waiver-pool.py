#!/usr/bin/env python3
"""NF-WVR1 Phase B — regenerate the waiver-view E2E fixtures from the SHIPPING route over LIVE data.

    uv run python frontend/e2e/fixtures/build-waiver-pool.py      (laptop; reads prod S3, writes nothing to it)

WHY GENERATED AND NOT CAPTURED. `/fantasy/nfl/waiver-pool` is a PAID, per-caller route: a capture
would need a subscriber token and would commit a real user's league. E9.63's rule (⛔ never
hand-write a fixture) is honoured the way `build-featured-player.py` honours it — every byte of the
payload is the output of the code under test.

⭐ WHAT IS REAL: the route function `fantasy.nfl_waiver_pool` itself, the served board
(`fantasy/nfl/2026/projections.json`) and the served season-to-date realized artifact
(`fantasy/nfl/realized/2026/season/…`), read through the route's own `_load_json`. The facts,
ordering, need arithmetic, absences and lineage check are therefore the shipping ones.

⚠️ WHAT IS STUBBED, and only this: the NETWORK and the STORE.
  • `sleeper.refresh_league_rosters` returns a deterministic drafted league — the board's top
    150 by ADP dealt round-robin to 10 teams — so the refresh code path runs (and stamps
    `refreshed: true`) without calling Sleeper for a league id that does not exist.
  • DynamoDB returns the e2e league record (`fantasy-nfl-my-teams.json`'s `e2e-league-1`, with an
    imported roster of team 1 added so the need annotation has something to count).

Outputs (three states, each from the real route):
  fantasy-nfl-waiver-pool.generated.json            the served state
  fantasy-nfl-waiver-pool-refused.generated.json    stored rosters flagged truncated → refusal
  fantasy-nfl-waiver-pool-unpublished.generated.json no season artifact → stated unranked listing

The content moves with the board and with each published week; the specs assert against the
payload's OWN values, never a hardcoded name or number.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "frontend/e2e/fixtures/api"


def main() -> int:
    sys.path.insert(0, str(REPO))
    import os

    os.environ.setdefault("CACHE_BUCKET", "credence-prod-s3-api-cache")
    from starlette.requests import Request

    from app.backend.routers import fantasy
    from app.backend.services.platform_import import sleeper

    fantasy._CACHE_BUCKET = os.environ["CACHE_BUCKET"]
    board = fantasy._full_projections(2026)["players"]
    drafted = sorted((p for p in board if p.get("adp") is not None), key=lambda p: p["adp"])[:150]
    teams = [{"team_key": str(i + 1), "team_name": f"Team {i + 1}", "players": []} for i in range(10)]
    for i, p in enumerate(drafted):
        teams[i % 10]["players"].append({"name": p["name"], "position": p["pos"], "team": p["team"]})

    league = json.loads((API / "fantasy-nfl-my-teams.json").read_text())["leagues"][0]
    mine = [{"name": x["name"], "position": x["position"], "team": x["team"], "starter": True}
            for x in teams[0]["players"]]
    record = {**league, "imported_roster": mine, "league_rosters": teams,
              "league_rosters_truncated": False,
              "league_rosters_synced_at": "2026-09-01T12:00:00+00:00"}

    synced = "2026-09-17T12:00:00+00:00"
    sleeper.refresh_league_rosters = lambda lid: {"rosters": teams, "synced_at": synced}
    fantasy.dynamo.put_fantasy_league = lambda *a, **k: None
    fantasy.entitlement.resolve_entitlement = lambda req: "subscriber"
    fantasy.entitlement.personalized_league_quota = lambda ent: 25
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})

    def run(rec: dict, name: str, refresh: bool = True) -> dict:
        fantasy.dynamo.list_fantasy_leagues = lambda uid: [rec]
        fantasy._realized_season_memo.clear()
        out = fantasy.nfl_waiver_pool(request=req, league_id=rec["league_id"], season=2026,
                                      refresh=refresh, user_id="e2e")
        (API / name).write_text(json.dumps(out, indent=1, default=str) + "\n")
        n = sum(len(g["players"]) for g in out["pool"] or [])
        print(f"wrote {name}: ordering={out['ordering']} pool_rows={n} refusals={out['refusals']}")
        return out

    served = run(record, "fantasy-nfl-waiver-pool.generated.json")
    assert served["ordering"] == "realized_to_date", "live season artifact did not verify"
    run({**record, "league_rosters_truncated": True},
        "fantasy-nfl-waiver-pool-refused.generated.json", refresh=False)

    real_load = fantasy._load_json
    fantasy._load_json = lambda rel, sport="nfl": (
        None if rel.startswith("realized/") else real_load(rel, sport))
    run(record, "fantasy-nfl-waiver-pool-unpublished.generated.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
