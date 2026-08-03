"""Fast-gate tests for E8.2's league API — the overlay, the gate, and the refusals.

The dangerous failures on this surface are all SILENT and all look like a working board, so each
gets its own test:

  * an empty or unreadable board would mark every prospect AVAILABLE  → must refuse, never serve
  * a stored overlay would rot on the next board publish              → recomputed every read
  * a re-upload that merged would keep a dropped player rostered      → replaces wholesale
  * a live draft pick that lost to a stale upload                     → picks win
  * an un-admin-gated route would expose the 2027 board early         → asserted per route

⚠️ The route FUNCTIONS are called directly rather than through `TestClient` — this repo does not
ship `httpx`, and the fast gate must not grow a dependency just to exercise a router (the
convention set by `test_fantasy_public_router.py`). Everything below is the real handler, the real
pydantic request model and the real matcher; only the store and the board read are stubbed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.backend.dependencies import get_admin_user, require_fantasy_access
from app.backend.routers import fantasy_mlb_league as mod

GRID = (
    "Team,C,1B,SS,OF,P,\n"
    "Antonio Picante,C Jensen,N Kurtz,T WallsW Aloy(M),S Basallo(I)M Clark(M),M Leiter(M)\n"
    "Red Paps,C Narvaez,J Naylor,B Rocchio,C DeLauterJ Chourio(M),K Rocker\n"
)

BOARD = {
    "season": 2026,
    "players": [
        {"rank": 1, "name": "Samuel Basallo", "league": "AL", "org": "BAL", "mlbamId": 701},
        {"rank": 2, "name": "Max Clark", "league": "AL", "org": "DET", "mlbamId": 702},
        {"rank": 3, "name": "Chase DeLauter", "league": "AL", "org": "CLE", "mlbamId": 703},
        {"rank": 4, "name": "Kumar Rocker", "league": "AL", "org": "TEX", "mlbamId": 704},
        {"rank": 5, "name": "Mason Leiter", "league": "AL", "org": "NYY", "mlbamId": 705},
        {"rank": 6, "name": "Wilfred Aloy", "league": "AL", "org": "OAK", "mlbamId": 706},
        {"rank": 7, "name": "Jesus Made", "league": "AL", "org": "TBR", "mlbamId": 707},
        {"rank": 8, "name": "Jackson Chourio", "league": "NL", "org": "MIL", "mlbamId": 708},
    ],
}

USER = "u1"


class FakeStore:
    """Stands in for the DynamoDB league map — same contract, no IO."""

    def __init__(self):
        self.leagues: dict[str, dict] = {}
        self.MAX_MLB_LEAGUES_PER_USER = 5
        self._n = 0

    def list_mlb_leagues(self, user_id):
        return [{**v, "league_id": k} for k, v in self.leagues.items()]

    def get_mlb_league(self, user_id, league_id):
        item = self.leagues.get(league_id)
        return {**item, "league_id": league_id} if item else None

    def put_mlb_league(self, user_id, league_id, league):
        if not league_id:
            if len(self.leagues) >= self.MAX_MLB_LEAGUES_PER_USER:
                raise ValueError("too_many_leagues")
            self._n += 1
            league_id = f"lg{self._n}"
        record = {k: v for k, v in league.items() if k != "league_id"}
        record["updated_at"] = "2026-08-02T00:00:00Z"
        self.leagues[league_id] = record
        return {**record, "league_id": league_id}

    def delete_mlb_league(self, user_id, league_id):
        if league_id not in self.leagues:
            raise ValueError("not_found")
        del self.leagues[league_id]


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(mod, "dynamo", fake)
    return fake


@pytest.fixture
def board(monkeypatch):
    holder = {"data": BOARD}
    monkeypatch.setattr(mod, "_load_json", lambda key, sport="nfl": holder["data"])
    return holder


class FakeEgress:
    """Stands in for E8.5's `coverage_gap_egress` — records every write/delete call, no IO."""

    def __init__(self):
        self.writes: list[tuple] = []
        self.deletes: list[tuple] = []

    def write(self, user_id, league_id, league_meta, coverage_gaps):
        self.writes.append((user_id, league_id, league_meta, list(coverage_gaps)))
        return True

    def delete(self, user_id, league_id):
        self.deletes.append((user_id, league_id))


@pytest.fixture(autouse=True)
def egress(monkeypatch):
    fake = FakeEgress()
    monkeypatch.setattr(mod, "coverage_gap_egress", fake)
    return fake


def preview(text=GRID, scope="AL"):
    return mod.preview(mod.PreviewRequest(text=text, league_scope=scope), season=2026,
                       user_id=USER)


def save(text=GRID, scope="AL", name="Dynasty", league_id=None):
    return mod.save_league(
        mod.SaveRequest(text=text, league_scope=scope, name=name, league_id=league_id),
        season=2026,
        user_id=USER,
    )


def read(league_id):
    return mod.get_league(league_id=league_id, user_id=USER)


# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.usefixtures("store", "board")
class TestTheOverlay:
    def test_preview_resolves_without_saving_anything(self, store):
        body = preview()
        assert body["upload_format"] == "cbs_grid"
        # Basallo, Clark, DeLauter, Rocker, Leiter, Aloy — six AL board rows are rostered.
        assert set(body["rostered"]) == {"1", "2", "3", "4", "5", "6"}
        assert body["rostered"]["1"]["team"] == "Antonio Picante"
        assert body["rostered"]["1"]["status"] == "injured"
        assert body["rostered"]["2"]["status"] == "minors"
        assert store.leagues == {}, "preview must not persist anything"

    def test_a_prospect_nobody_rosters_is_absent_from_the_overlay(self):
        assert "7" not in preview()["rostered"], "Jesus Made is rostered by nobody"

    def test_league_scope_keeps_the_other_league_out(self):
        """`J Chourio(M)` is stashed in this league's minors slot, but Chourio is an NL board row.
        An AL-scoped league must not resolve him — the board it overlays is AL-only."""
        body = preview()
        assert "8" not in body["rostered"]
        assert body["counts"]["board_rows_in_scope"] == 7
        assert "8" in preview(scope="BOTH")["rostered"]

    def test_the_framing_travels_in_the_payload(self):
        assert "not a recommendation" in preview()["framing"]

    def test_a_minors_stash_counts_as_rostered(self):
        """⭐ The whole point of the story: `(M)` is a dynasty stash, so that prospect is NOT
        available even though he has never played an MLB game."""
        assert preview()["rostered"]["2"]["status"] == "minors"

    def test_the_overlay_is_recomputed_against_the_CURRENT_board(self, board):
        """⭐ A stored overlay would silently rot on the next publish. Re-rank the board and the
        same saved league must follow it."""
        league_id = save()["league"]["league_id"]
        assert "1" in read(league_id)["rostered"]

        board["data"] = {"players": [{**p, "rank": p["rank"] + 100} for p in BOARD["players"]]}
        after = read(league_id)
        assert "1" not in after["rostered"]
        assert "101" in after["rostered"], "the overlay did not follow the re-published board"


@pytest.mark.usefixtures("store", "board")
class TestTheRefusals:
    """Every one of these would otherwise render a plausible, entirely wrong board."""

    def test_an_unreadable_board_refuses_rather_than_marking_everything_available(self, board):
        board["data"] = None
        with pytest.raises(HTTPException) as exc:
            preview()
        assert exc.value.status_code == 404

    def test_an_empty_board_refuses(self, board):
        board["data"] = {"players": []}
        with pytest.raises(HTTPException) as exc:
            preview()
        assert exc.value.status_code == 502

    def test_an_unparseable_upload_is_a_422_with_readable_copy(self):
        with pytest.raises(HTTPException) as exc:
            preview(text="Player\nSome Guy\n")
        assert exc.value.status_code == 422
        assert isinstance(exc.value.detail, str), "detail must be a string the UI can show"

    def test_a_bad_scope_is_refused(self):
        with pytest.raises(HTTPException) as exc:
            preview(scope="AAA")
        assert exc.value.status_code == 422


@pytest.mark.usefixtures("board")
class TestSavedLeagues:
    def test_save_then_read_back(self, store):
        saved = save()
        league_id = saved["league"]["league_id"]
        assert saved["league"]["player_count"] == 13
        assert saved["league"]["team_count"] == 2

        got = read(league_id)
        assert got["league"]["name"] == "Dynasty"
        assert len(got["entries"]) == 13
        assert got["rostered"]["3"]["team"] == "Red Paps"

        listed = mod.list_leagues(user_id=USER)["leagues"]
        assert [lg["league_id"] for lg in listed] == [league_id]
        assert "entries" not in listed[0], "the picker must not carry every roster"

    def test_the_raw_upload_is_never_stored(self, store):
        save()
        stored = next(iter(store.leagues.values()))
        assert "text" not in stored and "raw" not in stored
        assert set(stored["entries"][0]) <= {"team", "slot", "name", "status"}

    def test_a_reupload_replaces_the_roster_rather_than_merging(self, store):
        """A merge would keep a player the user has since DROPPED marked as rostered — invisible
        on the board, and wrong in the dangerous direction."""
        league_id = save()["league"]["league_id"]
        after = save(text="Team,C,\nAntonio Picante,C Jensen\n", league_id=league_id)
        assert after["league"]["player_count"] == 1
        assert after["rostered"] == {}

    def test_a_reupload_keeps_the_users_manual_fixes_and_picks(self, store):
        """Those are corrections to OUR matching, not to their roster. Wiping them on every upload
        would train the user to skip the review step."""
        league_id = save()["league"]["league_id"]
        mod.assign_pick(mod.PickRequest(team="KCStat"), league_id=league_id, board_rank=7,
                        user_id=USER)
        after = save(league_id=league_id)
        assert after["picks"] == {"7": "KCStat"}

    def test_delete_is_a_real_delete(self, store):
        league_id = save()["league"]["league_id"]
        assert mod.delete_league(league_id=league_id, user_id=USER) is None
        assert store.leagues == {}
        with pytest.raises(HTTPException) as exc:
            read(league_id)
        assert exc.value.status_code == 404

    def test_a_league_the_user_does_not_own_is_a_404_not_a_500(self, store):
        for call in (
            lambda: read("nope"),
            lambda: mod.update_league(mod.UpdateRequest(name="x"), league_id="nope",
                                      user_id=USER),
            lambda: mod.delete_league(league_id="nope", user_id=USER),
            lambda: mod.assign_pick(mod.PickRequest(team="t"), league_id="nope", board_rank=1,
                                    user_id=USER),
        ):
            with pytest.raises(HTTPException) as exc:
                call()
            assert exc.value.status_code == 404

    def test_the_per_user_cap_is_a_409_with_actionable_copy(self, store):
        for _ in range(store.MAX_MLB_LEAGUES_PER_USER):
            save()
        with pytest.raises(HTTPException) as exc:
            save(name="one more")
        assert exc.value.status_code == 409
        assert "Delete one" in exc.value.detail


@pytest.mark.usefixtures("store", "board")
class TestManualFixes:
    def test_an_override_pins_a_match_and_survives_a_read(self):
        first = preview()["entries"][0]
        entry_key = f"{first['team']}␟{first['slot']}␟{first['name']}␟{first['status'] or ''}"
        league_id = save()["league"]["league_id"]

        out = mod.update_league(
            mod.UpdateRequest(overrides={entry_key: 7}), league_id=league_id, user_id=USER
        )
        assert out["rostered"]["7"]["confidence"] == "manual"
        assert read(league_id)["rostered"]["7"]["confidence"] == "manual"

    def test_a_patch_leaves_absent_fields_alone(self):
        league_id = save()["league"]["league_id"]
        out = mod.update_league(
            mod.UpdateRequest(name="Renamed"), league_id=league_id, user_id=USER
        )
        assert out["league"]["name"] == "Renamed"
        assert out["league_scope"] == "AL"
        assert read(league_id)["league"]["player_count"] == 13


@pytest.mark.usefixtures("store", "board")
class TestLiveDraftAssignment:
    def test_marking_a_prospect_drafted_removes_him_from_the_pool_immediately(self):
        league_id = save()["league"]["league_id"]
        assert "7" not in read(league_id)["rostered"]

        out = mod.assign_pick(mod.PickRequest(team="Sea Monkeys"), league_id=league_id,
                              board_rank=7, user_id=USER)
        assert out["rostered"]["7"] == {
            "team": "Sea Monkeys", "slot": "—", "status": None,
            "confidence": "draft", "source": "draft",
        }
        assert out["counts"]["drafted_in_session"] == 1

    def test_a_pick_wins_over_a_stale_uploaded_roster(self):
        """The upload is a point-in-time file; the pick is what just happened in the room."""
        league_id = save()["league"]["league_id"]
        out = mod.assign_pick(mod.PickRequest(team="phantoms"), league_id=league_id,
                              board_rank=1, user_id=USER)
        assert out["rostered"]["1"]["team"] == "phantoms"
        assert out["rostered"]["1"]["source"] == "draft"

    def test_a_pick_can_be_undone(self):
        league_id = save()["league"]["league_id"]
        mod.assign_pick(mod.PickRequest(team="KCStat"), league_id=league_id, board_rank=7,
                        user_id=USER)
        out = mod.undo_pick(league_id=league_id, board_rank=7, user_id=USER)
        assert "7" not in out["rostered"]

    def test_picks_persist_across_reads(self):
        league_id = save()["league"]["league_id"]
        mod.assign_pick(mod.PickRequest(team="KCStat"), league_id=league_id, board_rank=7,
                        user_id=USER)
        assert read(league_id)["picks"] == {"7": "KCStat"}

    def test_a_pick_can_be_reassigned_to_a_different_team_without_undoing_first(self):
        """E8.6: a mis-click during a live draft is corrected by picking the RIGHT team directly —
        `assign_pick` overwrites unconditionally, keyed on the board's immutable rank, so there is
        no intermediate 'unassigned' state a stray read could ever show as available."""
        league_id = save()["league"]["league_id"]
        mod.assign_pick(mod.PickRequest(team="Wrong Team"), league_id=league_id, board_rank=7,
                        user_id=USER)
        out = mod.assign_pick(mod.PickRequest(team="Right Team"), league_id=league_id,
                              board_rank=7, user_id=USER)
        assert out["rostered"]["7"]["team"] == "Right Team"
        assert out["picks"] == {"7": "Right Team"}
        assert read(league_id)["rostered"]["7"]["team"] == "Right Team"

    def test_reassigning_one_pick_leaves_other_picks_alone(self):
        league_id = save()["league"]["league_id"]
        mod.assign_pick(mod.PickRequest(team="Sea Monkeys"), league_id=league_id, board_rank=1,
                        user_id=USER)
        mod.assign_pick(mod.PickRequest(team="KCStat"), league_id=league_id, board_rank=7,
                        user_id=USER)
        out = mod.assign_pick(mod.PickRequest(team="phantoms"), league_id=league_id,
                              board_rank=7, user_id=USER)
        assert out["rostered"]["1"]["team"] == "Sea Monkeys"
        assert out["rostered"]["7"]["team"] == "phantoms"


@pytest.mark.usefixtures("store", "board")
class TestMyTeamDesignation:
    """E8.6 — which team is the user's OWN, for the board's 'my roster' highlight."""

    def test_setting_it_persists_and_surfaces_in_the_overlay(self):
        league_id = save()["league"]["league_id"]
        out = mod.update_league(
            mod.UpdateRequest(my_team="Antonio Picante"), league_id=league_id, user_id=USER
        )
        assert out["my_team"] == "Antonio Picante"
        assert read(league_id)["my_team"] == "Antonio Picante"

    def test_an_omitted_field_leaves_it_alone(self):
        league_id = save()["league"]["league_id"]
        mod.update_league(mod.UpdateRequest(my_team="Antonio Picante"), league_id=league_id,
                          user_id=USER)
        out = mod.update_league(mod.UpdateRequest(name="Renamed"), league_id=league_id,
                                user_id=USER)
        assert out["my_team"] == "Antonio Picante"

    def test_an_explicit_empty_string_clears_it(self):
        league_id = save()["league"]["league_id"]
        mod.update_league(mod.UpdateRequest(my_team="Antonio Picante"), league_id=league_id,
                          user_id=USER)
        out = mod.update_league(mod.UpdateRequest(my_team=""), league_id=league_id, user_id=USER)
        assert out["my_team"] is None
        assert read(league_id)["my_team"] is None

    def test_a_league_with_no_designation_reads_none_not_an_error(self):
        league_id = save()["league"]["league_id"]
        assert read(league_id)["my_team"] is None
        assert read(league_id)["counts"]["on_my_team"] == 0

    def test_on_my_team_counts_rostered_AND_drafted_rows_under_that_team(self):
        league_id = save()["league"]["league_id"]
        mod.update_league(mod.UpdateRequest(my_team="Antonio Picante"), league_id=league_id,
                          user_id=USER)
        baseline = read(league_id)["counts"]["on_my_team"]  # ranks 1/2/5/6 already on this roster

        # #7 (Jesus Made) is unrostered in the fixture upload — a live-draft pick to the SAME team
        # as `my_team` must add to the count, exactly like an uploaded roster match does.
        out = mod.assign_pick(mod.PickRequest(team="Antonio Picante"), league_id=league_id,
                              board_rank=7, user_id=USER)
        assert out["counts"]["on_my_team"] == baseline + 1
        assert out["rostered"]["7"]["team"] == "Antonio Picante"

        # #8 (Jackson Chourio) is also unrostered — a pick to a DIFFERENT team must not inflate it.
        out = mod.assign_pick(mod.PickRequest(team="Red Paps"), league_id=league_id,
                              board_rank=8, user_id=USER)
        assert out["counts"]["on_my_team"] == baseline + 1

    def test_it_is_free_text_not_constrained_to_the_uploaded_teams(self):
        """A re-upload can rename a team; rejecting an unrecognised name here would make that
        rename silently break the designation instead of just failing to highlight anything."""
        league_id = save()["league"]["league_id"]
        out = mod.update_league(
            mod.UpdateRequest(my_team="A Team Not In This Upload"), league_id=league_id,
            user_id=USER,
        )
        assert out["my_team"] == "A Team Not In This Upload"


OVERVIEW = """Batters
,,,Schedule,,Rankings,,Trends,,Contracts,,Stats,,,,,
,Pos,Players, 8/3, 8/4- 8/11,Proj,Actual,Rost,Start,salary,contract,BA,R,HR,RBI,SB,
,OF,Chase DeLauter OF | CLE ,No Game,x,108,55,91%,77%,1,,0.276,40,12,52,6
,DH,Samuel Basallo C | BAL ,No Game,x,1,1,99%,90%,9,,0.280,50,20,60,1
Reserves
, OF,Max Clark OF | DET ,No Game,x,2,2,90%,50%,5,,0.270,40,10,40,10
Injured
Minors
, OF,Vance Honeycutt OF | BAL ,No Game,x,N/A,N/A,10%,0%,,M,0.000,0,0,0,0
Pitchers
,,,Schedule,,Rankings,,Trends,,Contracts,,Stats,,,,,
,Pos,Players, 8/3, 8/4- 8/11,Proj,Actual,Rost,Start,salary,contract,ERA,WHIP,W,K,S,
,P,Kumar Rocker P | TEX ,No Game,x,41,12,98%,84%,27,,2.41,1.08,7,174,0
Reserves
Injured
Minors
Active: 3 Reserve: 1 Injured: 0 Minors: 1 Active salary: 226.00 Total salary: 291.00
"""


@pytest.mark.usefixtures("store", "board")
class TestThePerTeamUpload:
    def test_it_replaces_only_that_team(self):
        league_id = save()["league"]["league_id"]
        before = read(league_id)
        assert set(before["teams"]) == {"Antonio Picante", "Red Paps"}

        out = mod.upsert_team(
            mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
            league_id=league_id, user_id=USER,
        )
        assert out["upload_format"] == "roster_overview"
        assert out["imported"] == 5
        assert out["replaced"] == 6, "the old Red Paps roster should have been swapped out"

        after = read(league_id)
        # Antonio Picante is untouched…
        assert {e["name"] for e in after["entries"] if e["team"] == "Antonio Picante"} == {
            e["name"] for e in before["entries"] if e["team"] == "Antonio Picante"
        }
        # …and Red Paps now carries the full names from the per-team export.
        assert {e["name"] for e in after["entries"] if e["team"] == "Red Paps"} == {
            "Chase DeLauter", "Samuel Basallo", "Max Clark", "Vance Honeycutt", "Kumar Rocker",
        }

    def test_the_mlb_club_is_stored_and_survives_a_read(self):
        league_id = save()["league"]["league_id"]
        mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                        league_id=league_id, user_id=USER)
        delauter = next(e for e in read(league_id)["entries"] if e["name"] == "Chase DeLauter")
        assert delauter["team"] == "Red Paps"

    def test_a_bad_export_is_a_422_not_a_partial_import(self):
        league_id = save()["league"]["league_id"]
        with pytest.raises(HTTPException) as exc:
            mod.upsert_team(
                mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW.replace("Active: 3", "Active: 9")),
                league_id=league_id, user_id=USER,
            )
        assert exc.value.status_code == 422
        assert "missing players" in exc.value.detail
        # and nothing was written
        assert {e["name"] for e in read(league_id)["entries"] if e["team"] == "Red Paps"} != set()


@pytest.mark.usefixtures("store", "board")
class TestBoardCoverageIsReported:
    def test_an_unplaceable_minors_stash_reaches_the_payload(self):
        league_id = save()["league"]["league_id"]
        out = mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                              league_id=league_id, user_id=USER)
        gaps = {g["name"]: g for g in out["coverage_gaps"]}
        assert "Vance Honeycutt" in gaps, "a minors stash we cannot place must be reported"
        assert gaps["Vance Honeycutt"]["org"] == "BAL"      # what makes it actionable
        assert gaps["Vance Honeycutt"]["source"] == "suggested"

    def test_flagging_missing_keeps_it_reported_while_clearing_the_queue(self):
        league_id = save()["league"]["league_id"]
        out = mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                              league_id=league_id, user_id=USER)
        key = next(g["key"] for g in out["coverage_gaps"] if g["name"] == "Vance Honeycutt")

        after = mod.update_league(
            mod.UpdateRequest(overrides={key: "missing_from_board"}),
            league_id=league_id, user_id=USER,
        )
        assert [g["source"] for g in after["coverage_gaps"] if g["name"] == "Vance Honeycutt"] == [
            "confirmed"
        ]
        assert "Vance Honeycutt" not in [r["name"] for r in after["review"]]
        assert read(league_id)["coverage_gaps"], "the flag must survive a round trip"

    def test_not_a_prospect_does_NOT_land_in_the_coverage_report(self):
        """The whole point of splitting the dismissal: an established major-leaguer is not a gap."""
        league_id = save()["league"]["league_id"]
        out = mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                              league_id=league_id, user_id=USER)
        key = next(g["key"] for g in out["coverage_gaps"] if g["name"] == "Vance Honeycutt")
        after = mod.update_league(
            mod.UpdateRequest(overrides={key: "not_a_prospect"}),
            league_id=league_id, user_id=USER,
        )
        assert after["coverage_gaps"] == []
        assert "Vance Honeycutt" not in [r["name"] for r in after["review"]]


@pytest.mark.usefixtures("board")
class TestALegacyStoredLeagueStillServesAndSelfHeals:
    """⚠️ Runtime-gate discipline (E9.49/E8.6): CI mocks all IO and every OTHER fixture in this file
    is a well-formed record this session's own code just wrote. A record stored by an EARLIER
    version of this feature — missing fields E8.2b/E8.5 later added — must still read cleanly and
    still self-heal, not 500 or silently drop the coverage-gap signal."""

    def test_a_pre_org_positions_entry_still_overlays_and_reports_a_gap(self, store):
        """The very first E8.2 shape stored only team/slot/name/status — `org` and `positions`
        arrived later. `_entries()` must default them, not KeyError."""
        legacy_league = {
            "name": "Legacy League",
            "league_scope": "AL",
            "season": 2026,
            "teams": ["Legacy Team"],
            "entries": [
                {"team": "Legacy Team", "slot": "OF", "name": "Vance Honeycutt", "status": "minors"}
                # no "org", no "positions" — the pre-E8.2-second-export shape
            ],
            "overrides": {},
            "picks": {},
        }
        store.leagues["legacy1"] = legacy_league
        out = read("legacy1")
        gaps = {g["name"]: g for g in out["coverage_gaps"]}
        assert "Vance Honeycutt" in gaps
        assert gaps["Vance Honeycutt"]["org"] is None, "a legacy row must default, not KeyError"
        assert gaps["Vance Honeycutt"]["source"] == "suggested"

    def test_a_confirmed_gap_from_a_legacy_override_shape_still_self_heals(self, store, board):
        """A `missing_from_board` override recorded before the board carried the player must clear
        itself once the board does — the legacy stored shape (bare team/slot/name/status, an
        override keyed the old way) exercises the exact self-heal path E8.5 fixes."""
        key = "Legacy Team␟OF␟Vance Honeycutt␟minors"
        store.leagues["legacy2"] = {
            "name": "Legacy League 2",
            "league_scope": "AL",
            "season": 2026,
            "teams": ["Legacy Team"],
            "entries": [
                {"team": "Legacy Team", "slot": "OF", "name": "Vance Honeycutt", "status": "minors"}
            ],
            "overrides": {key: "missing_from_board"},
            "picks": {},
        }
        before = read("legacy2")
        assert [g["name"] for g in before["coverage_gaps"]] == ["Vance Honeycutt"]

        board["data"] = {"players": [*BOARD["players"], {
            "rank": 300, "name": "Vance Honeycutt", "league": "AL", "org": "BAL", "mlbamId": 555,
        }]}
        after = read("legacy2")
        assert after["coverage_gaps"] == []
        assert after["rostered"]["300"]["team"] == "Legacy Team"

    def test_a_gap_entry_missing_optional_upload_fields_does_not_break_the_response(self, store):
        """`positions`/`status_code` are newer fields still — a row missing them must serialize
        cleanly rather than crashing the whole overlay response."""
        store.leagues["legacy3"] = {
            "name": "Legacy League 3", "league_scope": "AL", "season": 2026,
            "teams": ["T"],
            "entries": [{"team": "T", "slot": "OF", "name": "D Lesko", "status": "minors"}],
            "overrides": {}, "picks": {},
        }
        out = read("legacy3")  # must not raise
        assert any(g["name"] == "D Lesko" for g in out["coverage_gaps"])


@pytest.mark.usefixtures("store", "board")
class TestCoverageGapEgressWiring:
    """E8.5 — the coverage-gap signal must reach the durable S3 egress from every route that can
    change it, and must NEVER be persisted from `preview` (which stores nothing, by design)."""

    def test_preview_never_writes_to_the_egress(self, egress):
        preview()
        assert egress.writes == []

    def test_saving_a_league_writes_its_coverage_gaps(self, egress):
        league_id = save()["league"]["league_id"]
        assert egress.writes, "save_league must persist the coverage-gap egress"
        user_id, written_league_id, meta, gaps = egress.writes[-1]
        assert user_id == USER
        assert written_league_id == league_id
        assert meta["name"] == "Dynasty"

    def test_reading_a_saved_league_also_refreshes_the_egress(self, egress):
        """A GET recomputes the overlay fresh (E8.2's existing convention) — E8.5 persists on every
        computation, not just on a write, so a board republish is reflected without the admin having
        to touch the league again."""
        league_id = save()["league"]["league_id"]
        egress.writes.clear()
        read(league_id)
        assert egress.writes, "get_league must also refresh the durable egress"

    def test_upserting_a_team_writes_the_egress(self, egress):
        league_id = save()["league"]["league_id"]
        egress.writes.clear()
        mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                        league_id=league_id, user_id=USER)
        assert egress.writes

    def test_a_manual_gap_confirmation_reaches_the_egress(self, egress):
        league_id = save()["league"]["league_id"]
        out = mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                              league_id=league_id, user_id=USER)
        key = next(g["key"] for g in out["coverage_gaps"] if g["name"] == "Vance Honeycutt")
        egress.writes.clear()
        mod.update_league(mod.UpdateRequest(overrides={key: "missing_from_board"}),
                          league_id=league_id, user_id=USER)
        _, _, _, gaps = egress.writes[-1]
        assert [g["name"] for g in gaps] == ["Vance Honeycutt"]

    def test_the_egress_self_heals_when_the_board_is_republished(self, egress, board):
        """⭐ The end-to-end version of `TestTheGapSelfHeals` (board_match), through the router: once
        the board carries the player, the NEXT read must write an EMPTY coverage-gap list to S3, not
        leave the stale confirmed entry sitting there forever."""
        league_id = save()["league"]["league_id"]
        out = mod.upsert_team(mod.TeamUploadRequest(team="Red Paps", text=OVERVIEW),
                              league_id=league_id, user_id=USER)
        key = next(g["key"] for g in out["coverage_gaps"] if g["name"] == "Vance Honeycutt")
        mod.update_league(mod.UpdateRequest(overrides={key: "missing_from_board"}),
                          league_id=league_id, user_id=USER)
        assert egress.writes[-1][3], "the confirmed gap should have been written"

        board["data"] = {"players": [*BOARD["players"], {
            "rank": 200, "name": "Vance Honeycutt", "league": "AL", "org": "BAL", "mlbamId": 999,
        }]}
        egress.writes.clear()
        out = read(league_id)
        assert out["coverage_gaps"] == []
        assert egress.writes[-1][3] == [], "the self-healed empty list must reach the egress"

    def test_assign_and_undo_pick_write_the_egress(self, egress):
        league_id = save()["league"]["league_id"]
        egress.writes.clear()
        mod.assign_pick(mod.PickRequest(team="KCStat"), league_id=league_id, board_rank=7,
                        user_id=USER)
        assert egress.writes
        egress.writes.clear()
        mod.undo_pick(league_id=league_id, board_rank=7, user_id=USER)
        assert egress.writes

    def test_deleting_a_league_clears_its_egress_object(self, egress):
        league_id = save()["league"]["league_id"]
        mod.delete_league(league_id=league_id, user_id=USER)
        assert egress.deletes == [(USER, league_id)]

class TestTheGate:
    def test_every_route_is_admin_gated(self):
        """⚠️ The MLB board is admin-only dogfood until 2027. `require_fantasy_access` alone would
        expose it to every paying subscriber, so each route must ALSO depend on `get_admin_user`."""
        routes = [r for r in mod.router.routes if getattr(r, "path", "").startswith("/fantasy")]
        assert len(routes) >= 7, "no routes found — the assertion below would be vacuous"
        for route in routes:
            names = {d.call for d in route.dependant.dependencies}
            assert get_admin_user in names, f"{route.path} is not admin-gated"

    def test_the_router_carries_the_fantasy_entitlement(self):
        assert any(
            d.dependency is require_fantasy_access for d in (mod.router.dependencies or [])
        )

    def test_no_route_here_is_public(self):
        """A public route would need an API-Gateway change to work at all — and getting one would
        mean the paid/dogfood board had been un-gated (NF3.2)."""
        assert not hasattr(mod, "public_router")


class TestNothingContactsCbs:
    def test_the_module_makes_no_outbound_call(self):
        """E8.2a declined every CBS path. That decision has to be structural, not a promise: this
        module must not import an HTTP client at all."""
        from pathlib import Path

        source = Path(mod.__file__).read_text()
        for forbidden in ("requests", "httpx", "urllib.request", "cbssports"):
            assert forbidden not in source, f"{forbidden} must not appear in the league router"
