"""Fast-gate tests for NF-C6 Phase 1 — My Teams (cross-league browse).

Two things have to hold:

1. THE NEW ROSTER-LINK FIELDS ARE PURELY ADDITIVE. `source_team_key`/`source_team_name`/
   `imported_roster`/`roster_synced_at` must round-trip through both `LeagueSave` (write) and
   `League` (read) without breaking any existing league (E9.49: a write-time rule must never run on
   read), and `imported_roster` gets the same "keep a payload sane" size bound the rest of this
   model already uses for roster slots / scoring terms.

2. `GET /fantasy/nfl/my-teams` ASSEMBLES ONLY. It reads the user's own saved leagues (real
   DynamoDB update/get semantics via a minimal fake table, not mocked at the function boundary) and
   scores NOTHING — no `fantasy_engine` import happens anywhere in this file or the endpoint, which
   is the point: that stays impossible inside this Lambda (see `models/fantasy.py`'s docstring). A
   malformed stored league costs only itself (E9.49) and a non-NFL league is excluded. The gate is
   the BROADER `require_fantasy_access`, not the beta-only editor gate `/fantasy/leagues` uses.

Fast-gate discipline: no `pipeline` import, IO faked with a minimal in-memory table (mirrors
`TestLeagueSettingsStore`'s fake table in test_nf_c0b_league_settings.py).
"""
from __future__ import annotations

import inspect

import pytest


def _base_payload(**overrides):
    base = dict(
        name="test league",
        sport="nfl",
        n_teams=12,
        scoring={"per_stat": {"pass_yds": 0.04}, "position_bonuses": {}},
        roster=[{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}],
        ppr="custom",
    )
    base.update(overrides)
    return base


class TestRosterLinkFields:
    def test_roster_link_fields_default_to_none(self):
        models = pytest.importorskip("app.backend.models.fantasy")
        saved = models.LeagueSave(**_base_payload())
        assert saved.source_team_key is None
        assert saved.source_team_name is None
        assert saved.imported_roster is None
        assert saved.roster_synced_at is None

    def test_roster_link_fields_round_trip_through_save_and_read(self):
        models = pytest.importorskip("app.backend.models.fantasy")
        roster = [
            {
                "player_key": "1",
                "name": "Bijan Robinson",
                "position": "RB",
                "team": "ATL",
                "starter": True,
            },
            {"player_key": "2", "name": "Some Guy", "position": "WR", "team": "NYJ", "starter": False},
        ]
        saved = models.LeagueSave(
            **_base_payload(
                source_platform="sleeper",
                source_league_id="999",
                source_team_key="3",
                source_team_name="My Squad",
                imported_roster=roster,
                roster_synced_at="2026-08-02T00:00:00Z",
            )
        )
        assert saved.source_team_key == "3"
        assert saved.imported_roster == roster

        record = saved.model_dump()
        record["league_id"] = "lg-1"
        out = models.League(**record)
        assert out.imported_roster == roster
        assert out.source_team_name == "My Squad"
        assert out.roster_synced_at == "2026-08-02T00:00:00Z"

    def test_a_league_stored_before_nf_c6_still_reads(self):
        """E9.49 — a league saved before these fields existed has none of them at all; the
        response model must not require them."""
        models = pytest.importorskip("app.backend.models.fantasy")
        legacy = _base_payload()
        legacy["league_id"] = "legacy-1"
        out = models.League(**legacy)
        assert out.imported_roster is None
        assert out.source_team_key is None

    def test_imported_roster_is_size_bounded_on_save(self):
        models = pytest.importorskip("app.backend.models.fantasy")
        too_many = [
            {"player_key": str(i), "name": f"P{i}", "position": "WR", "team": None, "starter": False}
            for i in range(models.MAX_IMPORTED_ROSTER_PLAYERS + 1)
        ]
        with pytest.raises(Exception):
            models.LeagueSave(**_base_payload(imported_roster=too_many))

    def test_the_size_bound_is_write_only_and_never_blocks_a_read(self):
        """Mirrors `test_response_model_inherits_no_write_validators`: a save-time bound tightened
        after a league was stored must never make that stored league unreadable."""
        models = pytest.importorskip("app.backend.models.fantasy")
        assert not issubclass(models.League, models.LeagueSave)
        oversized = [
            {"player_key": str(i), "name": f"P{i}", "position": "WR", "team": None, "starter": False}
            for i in range(models.MAX_IMPORTED_ROSTER_PLAYERS + 5)
        ]
        legacy = _base_payload(imported_roster=oversized)
        legacy["league_id"] = "legacy-2"
        out = models.League(**legacy)  # must not raise
        assert len(out.imported_roster) == models.MAX_IMPORTED_ROSTER_PLAYERS + 5


class TestMyTeamsEndpoint:
    """Exercises `nfl_my_teams` directly — no TestClient/HTTP, matching this file family's existing
    convention of calling FastAPI route functions as plain Python once `Depends` is bypassed."""

    @staticmethod
    def _fake_table():
        class FakeTable:
            def __init__(self):
                self.items: dict[str, dict] = {}

            def get_item(self, Key):  # noqa: N803
                item = self.items.get(Key["user_id"])
                return {"Item": item} if item is not None else {}

            def update_item(  # noqa: N803
                self,
                Key,
                UpdateExpression,
                ExpressionAttributeNames=None,
                ExpressionAttributeValues=None,
                ConditionExpression=None,
            ):
                names = ExpressionAttributeNames or {}
                values = ExpressionAttributeValues or {}
                item = self.items.setdefault(Key["user_id"], {})
                expr = " ".join(UpdateExpression.split())
                if expr == "SET #fl = :empty":
                    if ConditionExpression and "fantasy_leagues" in item:
                        raise RuntimeError("ConditionalCheckFailedException")
                    item[names["#fl"]] = values[":empty"]
                elif expr == "SET #fl.#id = :cfg":
                    item.setdefault(names["#fl"], {})[names["#id"]] = values[":cfg"]
                else:
                    raise AssertionError(f"unhandled UpdateExpression: {expr}")

        return FakeTable()

    @pytest.fixture()
    def dynamo(self, monkeypatch):
        dynamo = pytest.importorskip("app.backend.services.dynamo")
        table = self._fake_table()
        monkeypatch.setattr(dynamo, "_users_table", lambda: table)
        return dynamo

    @pytest.fixture()
    def fantasy_router(self):
        return pytest.importorskip("app.backend.routers.fantasy")

    @staticmethod
    def _cfg(**overrides):
        base = dict(
            name="My League",
            sport="nfl",
            n_teams=10,
            scoring={"per_stat": {"pass_yds": 0.04}, "position_bonuses": {}},
            roster=[{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}],
            ppr="custom",
            source_platform="sleeper",
            source_league_id="123",
        )
        base.update(overrides)
        return base

    def test_returns_only_this_users_leagues_with_the_roster_snapshot(self, dynamo, fantasy_router):
        roster = [{"player_key": "1", "name": "A B", "position": "QB", "team": "KC", "starter": True}]
        dynamo.put_fantasy_league("u1", None, self._cfg(source_team_key="7", imported_roster=roster))
        dynamo.put_fantasy_league("u2", None, self._cfg(name="Someone else's"))

        out = fantasy_router.nfl_my_teams(season=2026, user_id="u1")
        assert out["season"] == 2026
        assert len(out["leagues"]) == 1
        assert out["leagues"][0]["imported_roster"] == roster
        assert out["leagues"][0]["source_team_key"] == "7"

    def test_a_league_with_no_linked_roster_still_appears(self, dynamo, fantasy_router):
        """A hand-entered league, or an imported one nobody has picked a team for yet, still shows
        up — `imported_roster` is honestly `None`, never hidden. The frontend's "not linked yet"
        state is built off exactly this (never a dropped league)."""
        dynamo.put_fantasy_league("u1", None, self._cfg())
        out = fantasy_router.nfl_my_teams(season=2026, user_id="u1")
        assert len(out["leagues"]) == 1
        assert out["leagues"][0]["imported_roster"] is None

    def test_non_nfl_leagues_are_excluded(self, dynamo, fantasy_router):
        dynamo.put_fantasy_league("u1", None, self._cfg(sport="mlb", name="MLB one"))
        dynamo.put_fantasy_league("u1", None, self._cfg(name="NFL one"))
        out = fantasy_router.nfl_my_teams(season=2026, user_id="u1")
        assert [l["name"] for l in out["leagues"]] == ["NFL one"]

    def test_a_malformed_stored_league_does_not_blank_the_collection(self, dynamo, fantasy_router):
        """E9.49: one bad row must cost only itself, never the whole My Teams page."""
        good = dynamo.put_fantasy_league("u1", None, self._cfg(name="Good"))
        table = dynamo._users_table()
        table.items["u1"]["fantasy_leagues"]["corrupt"] = "not-a-dict"

        out = fantasy_router.nfl_my_teams(season=2026, user_id="u1")
        assert [l["league_id"] for l in out["leagues"]] == [good["league_id"]]

    def test_the_gate_is_the_broader_fantasy_access_gate_not_the_beta_editor_gate(self, fantasy_router):
        """The endpoint must depend on `require_fantasy_access` (subscriber/admin/fantasy_comp),
        NOT `require_fantasy_beta_access` (admin/fantasy_comp only) — this is what lets a plain
        subscriber's own leagues read here the moment NF-C0's write side opens wider, without a
        second migration (see the endpoint's own docstring)."""
        sig = inspect.signature(fantasy_router.nfl_my_teams)
        dep = sig.parameters["user_id"].default
        assert dep.dependency is fantasy_router.require_fantasy_access
