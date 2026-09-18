"""NF-WVR1 guards — the free-agent pool, the positional-need arithmetic, and the fetch seam.

⛔ ANCHORED IN ITS OWN CLAUSES. Nothing here is bolted onto an older story's guard (the E9.60
coupling trap): every test fails only for a property NF-WVR1 is responsible for.

Each test names the DEFECT it exists to prevent, because several of these are things that were
actually wrong in a first cut and were caught by measurement rather than by review.
"""

from __future__ import annotations

import pytest

from app.backend.services import waiver_pool


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────

FULL_PPR_ROSTER = [
    {"name": "QB", "count": 1, "eligible": ["QB"], "bench": False},
    {"name": "RB", "count": 2, "eligible": ["RB"], "bench": False},
    {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False},
    {"name": "TE", "count": 1, "eligible": ["TE"], "bench": False},
    {"name": "FLEX", "count": 1, "eligible": ["RB", "WR", "TE"], "bench": False},
    {"name": "K", "count": 1, "eligible": ["K"], "bench": False},
    {"name": "DST", "count": 1, "eligible": ["DST"], "bench": False},
    {"name": "BN", "count": 6, "eligible": ["QB", "RB", "WR", "TE"], "bench": True},
]
CFG = {"n_teams": 12, "roster": FULL_PPR_ROSTER}


def _roster(**counts) -> list[dict]:
    rows = []
    for pos, n in counts.items():
        rows += [{"board": {"pos": pos}}] * n
    return rows


# ── 1. the flex double-count, which the first cut got WRONG ──────────────────────────────────────

def test_a_flex_slot_is_counted_once_not_added_to_every_position_it_accepts():
    """THE DEFECT: summing a RB/WR/TE flex into all three inflates a 12-team full-PPR league's
    demand from its real 9 starting slots to 11, so a manager who can fill EVERY slot is told they
    are short at three positions — a confidently wrong annotation on the one number this surface
    exists to state.

    2 RB / 2 WR / 1 TE plus a spare RB fills every slot, the flex taking the spare. Nothing may
    report an open starter.
    """
    need = waiver_pool.positional_need(
        _roster(QB=1, RB=3, WR=2, TE=1, K=1, DST=1), CFG
    )
    opens = [p["pos"] for p in need["positions"] if p["need"] == "open_starter"]
    assert opens == [], f"no starting slot is unfilled, yet these reported open: {opens}"
    assert need["flex"]["short_by"] == 0

    # …and the arithmetic that makes it true: dedicated demand must equal the league's real
    # non-flex starting slots (8), never the 11 the double-count produced.
    dedicated = sum(p["starters_required"] for p in need["positions"])
    assert dedicated == 8, f"dedicated starters should be 8, got {dedicated}"


def test_an_unfilled_flex_is_reported_at_the_league_level_not_blamed_on_a_position():
    """Exactly enough at every position and nothing spare: the flex genuinely cannot be filled, and
    that must show as a LEAGUE-level shortfall rather than as a phantom shortage at RB/WR/TE."""
    need = waiver_pool.positional_need(_roster(QB=1, RB=2, WR=2, TE=1, K=1, DST=1), CFG)
    assert need["flex"]["short_by"] == 1
    assert [p["pos"] for p in need["positions"] if p["need"] == "open_starter"] == []


def test_a_real_shortage_still_reports_an_open_starter():
    """The two tests above must not be satisfiable by a function that never reports anything."""
    need = waiver_pool.positional_need(_roster(QB=1, RB=1, WR=4, TE=1, K=1, DST=1), CFG)
    rb = next(p for p in need["positions"] if p["pos"] == "RB")
    assert rb["need"] == "open_starter" and rb["short_by"] == 1


# ── 2. the pool subtracts, and subtracts by NAME ─────────────────────────────────────────────────

def _board():
    return [
        {"id": "00-0000001", "name": "Rostered Back", "pos": "RB", "team": "SF"},
        {"id": "00-0000002", "name": "Free Back", "pos": "RB", "team": "KC"},
        # ⭐ a SYNTHETIC id, exactly as the live board carries for 81 rookies + 32 defences.
        {"id": "ROO123456", "name": "Rookie Wideout", "pos": "WR", "team": "NYJ"},
    ]


def test_a_rostered_player_never_appears_in_the_pool():
    rosters = [{"team_key": "1", "team_name": "T", "players": [
        {"name": "Rostered Back", "position": "RB", "team": "SF"}]}]
    pool = waiver_pool.free_agent_pool(_board(), rosters)
    names = {p["name"] for g in pool for p in g["players"]}
    assert "Rostered Back" not in names
    assert "Free Back" in names


def test_the_subtraction_joins_on_name_not_id_so_a_synthetic_id_row_still_subtracts():
    """THE DEFECT: 113 of 870 published board rows carry SYNTHETIC ids (81 rookies + 32 team
    defences), and a Sleeper roster carries a THIRD id vocabulary. An id join silently drops the
    rookie class — precisely the population a waiver surface exists to surface.

    The stored roster shape has NO id at all (`LEAGUE_ROSTER_PLAYER_FIELDS` is name/position/team),
    so a rookie with a synthetic board id must still subtract by name.
    """
    rosters = [{"team_key": "1", "team_name": "T", "players": [
        {"name": "Rookie Wideout", "position": "WR", "team": "NYJ"}]}]
    pool = waiver_pool.free_agent_pool(_board(), rosters)
    names = {p["name"] for g in pool for p in g["players"]}
    assert "Rookie Wideout" not in names, (
        "a synthetic-id board row did not subtract — the join has moved onto an id"
    )


def test_a_blank_roster_name_removes_nobody():
    """A roster row with no usable name cannot be matched, so it must subtract NOTHING rather than
    silently removing an arbitrary board player."""
    rosters = [{"team_key": "1", "team_name": "T", "players": [
        {"name": "", "position": "RB", "team": "SF"}]}]
    pool = waiver_pool.free_agent_pool(_board(), rosters)
    assert sum(len(g["players"]) for g in pool) == len(_board())


def test_the_pool_is_grouped_by_position_so_it_cannot_express_a_cross_position_ranking():
    """PM ruling 2: nothing ranks across positions. A FLAT list invites exactly that, so the shape
    itself refuses it — a structure that cannot express the wrong answer beats a comment asking for
    the right one."""
    pool = waiver_pool.free_agent_pool(_board(), [])
    assert isinstance(pool, list) and pool, "pool should be a non-empty list of position groups"
    for group in pool:
        assert set(group) == {"pos", "players"}, (
            f"a position group must carry exactly pos+players, got {sorted(group)} — a flat or "
            "rank-bearing shape would permit cross-position ordering"
        )


# ── 3. refusals withhold; caveats do not ─────────────────────────────────────────────────────────

def _healthy_record():
    return {
        "n_teams": 2,
        "league_rosters": [
            {"team_key": "1", "team_name": "A", "players": []},
            {"team_key": "2", "team_name": "B", "players": []},
        ],
        "league_rosters_truncated": False,
    }


def test_a_truncated_league_refuses():
    """THE WORST OUTPUT THIS FEATURE CAN PRODUCE (PM): `bound_league_rosters` drops WHOLE TEAMS at
    500 players, so a pool computed over a truncated set contains the dropped teams' players — it
    recommends players who are already owned."""
    rec = {**_healthy_record(), "league_rosters_truncated": True}
    assert "rosters_truncated" in waiver_pool.pool_refusals(rec)


def test_a_league_short_of_teams_refuses():
    rec = {**_healthy_record(), "n_teams": 12}
    assert "rosters_incomplete" in waiver_pool.pool_refusals(rec)


def test_a_league_with_no_stored_rosters_refuses():
    assert "no_league_rosters" in waiver_pool.pool_refusals({"n_teams": 12, "league_rosters": None})


def test_a_healthy_league_refuses_nothing():
    """The refusal tests above must not be satisfiable by a function that refuses everything."""
    assert waiver_pool.pool_refusals(_healthy_record()) == []


def test_an_unrefreshable_platform_is_a_CAVEAT_and_never_a_refusal():
    """THE DEFECT: withholding the pool because a platform cannot be re-read locks out every ESPN
    user PERMANENTLY — including one who re-imported a minute ago, whose rosters are as current as
    any Sleeper league's. An ESPN league's stored rosters are a correct snapshot that is simply as
    old as the last import, and `league_rosters_synced_at` already says so.

    Correctness and freshness are different claims and must not share a code path.
    """
    assert waiver_pool.pool_refusals(_healthy_record()) == []
    assert waiver_pool.pool_caveats(platform_can_refresh=False) == ["platform_cannot_refresh"]
    assert waiver_pool.pool_caveats(platform_can_refresh=True) == []
    assert "platform_cannot_refresh" not in waiver_pool.POOL_REFUSAL_REASONS, (
        "an un-refreshable platform must not be able to withhold the pool"
    )
    assert "platform_cannot_refresh" in waiver_pool.POOL_CAVEAT_REASONS


# ── 4. the fetch seam: ONE roster-refresh owner, and it is not RC1's ─────────────────────────────

def test_the_roster_refresh_delegates_to_fetch_teams_rather_than_re_querying():
    """PM ruling 3 — ONE owner of `/league/{id}/rosters`. Delegating rather than re-querying is what
    keeps name resolution, the `sleeper_players` artifact fallback and the owner/team-name join from
    EVER differing between an import and a refresh, which is the drift that would make a refreshed
    roster subtly disagree with the one it replaced."""
    from app.backend.services.platform_import import sleeper

    import inspect
    src = inspect.getsource(sleeper.refresh_league_rosters)
    stripped = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    assert "_fetch_teams(" in stripped, "the refresh must delegate to _fetch_teams"
    assert "get_json(" not in stripped, (
        "the refresh issues its own HTTP call — that is a second fetcher on one endpoint"
    )


def test_the_roster_refresh_returns_the_stored_record_shape_and_drops_player_key():
    """The returned rosters must be handable to `LeagueSave` without a second mapping step that
    could drift from `LEAGUE_ROSTER_PLAYER_FIELDS` — and `player_key` must NOT be carried, because
    the pool joins on name and an id here would invite the id join back."""
    from app.backend.models.fantasy import LEAGUE_ROSTER_PLAYER_FIELDS
    from app.backend.services.platform_import import canonical as C
    from app.backend.services.platform_import import sleeper

    fake = (
        C.ImportedTeam(
            team_key="1", name="Team One",
            players=(C.ImportedPlayer(player_key="999", name="A Back", position="RB", team="SF",
                                      slot="ir"),),
        ),
    )
    orig = sleeper._fetch_teams
    sleeper._fetch_teams = lambda lid: (fake, [])
    try:
        out = sleeper.refresh_league_rosters("123")
    finally:
        sleeper._fetch_teams = orig

    assert set(out) == {"rosters", "synced_at", "note", "teams_full"}
    team = out["rosters"][0]
    assert set(team) == {"team_key", "team_name", "players"}
    assert set(team["players"][0]) == set(LEAGUE_ROSTER_PLAYER_FIELDS), (
        "the refresh's player shape must match LEAGUE_ROSTER_PLAYER_FIELDS exactly"
    )
    assert "player_key" not in team["players"][0]
    assert out["synced_at"], "the fetch must stamp its own time — the caller re-stamps this"
    # The caller's OWN-roster refresh reads `teams_full`, which is the full imported shape (id and
    # slot kept) — a DIFFERENT object from the slim `rosters` the pool subtraction joins on.
    assert out["teams_full"]["1"][0]["player_key"] == "999"
    assert out["teams_full"]["1"][0]["slot"] == "ir"


def test_the_roster_refresh_raises_rather_than_returning_a_partial_set():
    """A roster list short by one team yields a pool containing that team's players — a confidently
    wrong recommendation that does not announce itself. So an empty fetch must REACH the caller."""
    from app.backend.services.platform_import import sleeper

    orig = sleeper._fetch_teams
    sleeper._fetch_teams = lambda lid: ((), [])
    try:
        with pytest.raises(sleeper.SleeperInputError):
            sleeper.refresh_league_rosters("123")
    finally:
        sleeper._fetch_teams = orig


def test_the_two_sleeper_fetches_stay_separate_objects():
    """RC1's `sleeper_matchups.fetch_week` is starters-only and deliberately FROZEN; this story's
    refresh is the whole rostered set and deliberately CURRENT. Collapsing them breaks whichever
    loses, so neither may start CALLING the other.

    ⚠️ MATCHES A CALL FORM ON COMMENT- AND DOCSTRING-STRIPPED SOURCE, never a bare word. The first
    cut asserted `"matchups" not in src` and FAILED against correct code, because this function's
    own docstring cites `sleeper_matchups` to explain why it refuses rather than returns a partial
    set. That is the INC-38 lesson — prose must not be able to satisfy OR violate a source scan —
    landing on the guard written to honour it.
    """
    import ast
    import inspect

    from app.backend.services.platform_import import sleeper

    tree = ast.parse(inspect.getsource(sleeper.refresh_league_rosters).strip())
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert called, "no calls parsed — the guard would pass on nothing"
    assert "fetch_week" not in called, (
        "the roster refresh calls RC1's weekly matchup fetch — they are different objects with "
        "deliberately opposite freshness semantics"
    )
    assert "_fetch_teams" in called, "the refresh must still delegate to the import's roster fetch"


# ── 5. a refresh's own verdict replaces the stored truncation flag ───────────────────────────────

def test_a_successful_refresh_clears_a_stale_truncation_flag_rather_than_carrying_it_forever():
    """THE DEFECT: copying `LeagueSave`'s `or` semantics into the REFRESH path leaves any league
    EVER truncated permanently refused — the feature silently dead for that user even after the
    league shrank or the cap was raised.

    The `or` is right on a SAVE (the importer slims before it sends, so a client's own truncation
    claim must not be erased) and wrong here, because the refresh REPLACES the rosters wholesale
    from a fetch that raises rather than returning a partial set. The flag must describe the set now
    stored, not a set that no longer exists.

    Source-inspected because the alternative is standing up DynamoDB: the assertion is that the
    stored flag is NOT OR-ed into the refreshed one.
    """
    import ast
    import inspect

    from app.backend.routers import fantasy

    src = inspect.getsource(fantasy.nfl_waiver_pool)
    tree = ast.parse(src.strip())
    assigned = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "league_rosters_truncated"
    ]
    assert assigned, "the refresh no longer writes league_rosters_truncated at all"

    # The refreshed value must be the fetch's own verdict. An `or` against the stored record is the
    # defect this test exists to prevent.
    stripped = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    idx = stripped.index('"league_rosters_truncated"')
    assignment = stripped[idx:stripped.index("\n", idx)]
    assert 'record.get("league_rosters_truncated")' not in assignment, (
        "the stored truncation flag is being OR-ed into a refresh that replaced the rosters "
        "wholesale — any league ever truncated would be refused forever"
    )
    assert "truncated" in assignment


def test_completeness_is_still_checked_independently_of_the_truncation_flag():
    """The safety argument for clearing a stale flag: `pool_refusals` compares stored teams against
    the league's declared `n_teams` and refuses `rosters_incomplete` WITHOUT consulting the flag, so
    a short roster set cannot slip through on a cleared flag."""
    short = {
        "n_teams": 12,
        "league_rosters": [{"team_key": "1", "team_name": "A", "players": []}],
        "league_rosters_truncated": False,       # ← flag says fine; the count does not
    }
    assert "rosters_incomplete" in waiver_pool.pool_refusals(short)


# ── 6. IR / taxi (operator 2026-09-17: an injured WR on IR was filed under Bench) ─────────────────

def test_sleeper_files_reserve_and_taxi_ids_by_their_slot_not_as_bench(monkeypatch):
    """THE DEFECT: Sleeper lists EVERY rostered id in `players` and marks IR / taxi only by repeating
    the id under `reserve` / `taxi`. Reading `players` + `starters` alone files an IR player as bench."""
    from app.backend.services.platform_import import sleeper

    payload = [{
        "roster_id": 1, "owner_id": "u1",
        "players": ["10", "20", "30", "40"], "starters": ["10"],
        "reserve": ["20"], "taxi": ["30"],
    }]
    monkeypatch.setattr(sleeper, "get_json",
                        lambda url: payload if url.endswith("/rosters") else [
                            {"user_id": "u1", "display_name": "Me", "metadata": {}}])
    monkeypatch.setattr(sleeper.sleeper_players, "resolve", lambda ids: (
        {i: {"full_name": f"P{i}", "position": "WR", "team": "NYJ"} for i in ids}, True))
    teams, _ = sleeper._fetch_teams("123")
    slots = {p.player_key: (p.slot, p.starter) for p in teams[0].players}
    assert slots == {"10": ("starter", True), "20": ("ir", False),
                     "30": ("taxi", False), "40": ("bench", False)}
    assert teams[0].players[1].to_dict()["slot"] == "ir"


def test_an_ir_player_is_not_counted_as_depth():
    """2 WR starters, 2 healthy WR + 1 on IR: the IR player must not make WR look covered."""
    rows = [{"roster": {"position": "WR", "slot": s}, "board": {"pos": "WR"}}
            for s in ("starter", "starter", "ir")]
    need = waiver_pool.positional_need(rows, {"roster": [
        {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False}]})
    wr = next(p for p in need["positions"] if p["pos"] == "WR")
    assert (wr["held"], wr["reserved"], wr["need"]) == (2, 1, "thin")

    two_healthy_one_ir = [{"roster": {"position": "WR", "slot": s}, "board": {"pos": "WR"}}
                          for s in ("starter", "ir", "ir")]
    need = waiver_pool.positional_need(two_healthy_one_ir, {"roster": [
        {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False}]})
    wr = next(p for p in need["positions"] if p["pos"] == "WR")
    assert (wr["held"], wr["short_by"], wr["need"]) == (1, 1, "open_starter")


def test_a_row_without_a_slot_still_counts_as_before():
    """A league saved before `slot` existed has none; unknown must not be read as IR."""
    rows = [{"roster": {"position": "RB"}, "board": {"pos": "RB"}}] * 2
    need = waiver_pool.positional_need(rows, {"roster": [
        {"name": "RB", "count": 2, "eligible": ["RB"], "bench": False}]})
    rb = next(p for p in need["positions"] if p["pos"] == "RB")
    assert (rb["held"], rb["reserved"]) == (2, 0)


def _waiver_route_harness(monkeypatch, record, fresh, projections=None):
    from starlette.requests import Request

    from app.backend.routers import fantasy
    from app.backend.services.platform_import import sleeper

    saved = {}
    monkeypatch.setattr(fantasy.dynamo, "list_fantasy_leagues", lambda uid: [record])
    monkeypatch.setattr(fantasy.dynamo, "put_fantasy_league",
                        lambda uid, lid, cfg, quota: saved.update(cfg=cfg))
    monkeypatch.setattr(fantasy.entitlement, "resolve_entitlement", lambda req: "subscriber")
    monkeypatch.setattr(fantasy.entitlement, "personalized_league_quota", lambda ent: 25)
    # ⑰ made the board INJECTABLE: an alias case is a property of the two spellings, so a test of it
    # has to choose both. Default is unchanged, so every earlier caller reads exactly as before.
    monkeypatch.setattr(fantasy, "_full_projections", lambda season: projections or {"players": [
        {"id": "00-0000001", "name": "Healthy Wideout", "pos": "WR", "team": "NYJ", "fpPpr": 100.0},
        {"id": "00-0000002", "name": "Hurt Wideout", "pos": "WR", "team": "NYJ", "fpPpr": 100.0},
    ]})
    monkeypatch.setattr(fantasy, "_realized_season", lambda season: (None, None, "realized_not_published"))
    monkeypatch.setattr(sleeper, "refresh_league_rosters", lambda lid: fresh)
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})
    out = fantasy.nfl_waiver_pool(request=req, league_id="L1", season=2026, refresh=True, user_id="u")
    return out, saved


def _own_team_fresh():
    rows = [
        {"player_key": "1", "name": "Healthy Wideout", "position": "WR", "team": "NYJ",
         "starter": True, "slot": "starter"},
        {"player_key": "2", "name": "Hurt Wideout", "position": "WR", "team": "NYJ",
         "starter": False, "slot": "ir"},
    ]
    slim = [{"name": r["name"], "position": r["position"], "team": r["team"]} for r in rows]
    return {"rosters": [{"team_key": "7", "team_name": "Mine", "players": slim}],
            "synced_at": "2026-09-17T12:00:00+00:00", "note": [], "teams_full": {"7": rows}}


def test_the_waiver_refresh_rewrites_the_callers_own_roster_with_its_slots(monkeypatch):
    """THE DEFECT: a league imported before `slot` existed kept filing an IR player under Bench (and
    counting him as depth) until a re-import. The refresh already reads every roster; the caller's
    own must ride the same read."""
    record = {"league_id": "L1", "sport": "nfl", "source_platform": "sleeper",
              "source_league_id": "123", "source_team_key": "7", "n_teams": 1,
              "roster": [{"name": "WR", "count": 2, "eligible": ["WR"], "bench": False}],
              "imported_roster": [{"player_key": "1", "name": "Healthy Wideout", "position": "WR",
                                   "team": "NYJ", "starter": True},
                                  {"player_key": "2", "name": "Hurt Wideout", "position": "WR",
                                   "team": "NYJ", "starter": False}],
              "roster_synced_at": "2026-08-01T00:00:00+00:00"}
    out, saved = _waiver_route_harness(monkeypatch, record, _own_team_fresh())
    assert out["rosters"]["own_roster_refreshed"] is True
    assert [r.get("slot") for r in saved["cfg"]["imported_roster"]] == ["starter", "ir"]
    assert saved["cfg"]["roster_synced_at"] == "2026-09-17T12:00:00+00:00"
    wr = next(p for p in out["need"]["positions"] if p["pos"] == "WR")
    assert (wr["held"], wr["reserved"], wr["need"]) == (1, 1, "open_starter")


def test_an_unlinked_league_keeps_its_stored_roster(monkeypatch):
    """No `source_team_key` ⇒ no own team to find ⇒ nothing about the caller's roster is replaced."""
    record = {"league_id": "L1", "sport": "nfl", "source_platform": "sleeper",
              "source_league_id": "123", "n_teams": 1, "roster": [],
              "imported_roster": None}
    out, saved = _waiver_route_harness(monkeypatch, record, _own_team_fresh())
    assert out["rosters"]["own_roster_refreshed"] is False
    assert saved["cfg"].get("imported_roster") is None


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ⑰ (PM ruling 2026-09-18) — THE ALIAS DETECTOR.
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# The PM refused the crosswalk fix (it re-opens a bounded 400 KB item budget for an unobserved
# residual) AND refused accepting the residual unwatched, and ruled the middle: reconcile at every
# build and refuse loudly. These are the two sides that make the detector a detector — it must FIRE
# on the measured alias case and STAY SILENT on a rostered player who is genuinely off the board.

_ALIAS_BOARD = [
    {"name": "Joshua Palmer", "pos": "WR", "team": "BUF", "id": "b1"},
    {"name": "Bijan Robinson", "pos": "RB", "team": "ATL", "id": "b2"},
    {"name": "Somebody Else", "pos": "WR", "team": "NYJ", "id": "b3"},
]


def _recon(board, rosters):
    groups = waiver_pool.free_agent_pool(board, rosters)
    return groups, waiver_pool.reconcile_rostered(board, groups, rosters)


def test_the_alias_detector_fires_on_the_measured_case_and_names_both_spellings():
    """"Josh Palmer" on the roster vs "Joshua Palmer" on the board — same player, same gsis id.

    THE DEFECT: the name join misses, the board row is never subtracted, and the surface offers a
    player who is already rostered — this feature's one must-never.
    """
    rosters = [{"players": [
        {"name": "Josh Palmer", "position": "WR", "team": "BUF"},
        {"name": "Bijan Robinson", "position": "RB", "team": "ATL"},
    ]}]
    groups, rec = _recon(_ALIAS_BOARD, rosters)

    # The alias player IS still being offered — which is exactly what the detector must catch.
    offered = {p["name"] for g in groups for p in g["players"]}
    assert "Joshua Palmer" in offered

    assert waiver_pool.alias_refusals(rec) == ["rostered_alias_unmatched"]
    assert len(rec["alias_suspects"]) == 1
    suspect = rec["alias_suspects"][0]
    assert suspect["rostered"]["name"] == "Josh Palmer"
    assert [b["name"] for b in suspect["board"]] == ["Joshua Palmer"]
    # The counts the ruling named, and they disagree — 1 WR implied rostered short of the live 1.
    assert rec["implied_rostered"]["WR"] == 0
    assert rec["live_rostered"]["WR"] == 1


def test_a_rostered_player_genuinely_off_the_board_does_NOT_refuse():
    """THE OTHER CAUSE OF THE SAME COUNT MISMATCH, and it is not a defect.

    A deep roster reaches past the board's tail (⑦ measured 2.2% of real week-1 skill performers
    past it). The pool is a SUBSET of the board, so an off-board player CANNOT be offered — the pool
    is correct, and refusing here would withhold a healthy league's list for a non-defect. That is
    how a guard gets muted, so the cause split is part of the detector, not a softening of it.
    """
    rosters = [{"players": [
        {"name": "Joshua Palmer", "position": "WR", "team": "BUF"},
        {"name": "Practice Squad Guy", "position": "WR", "team": "NYJ"},
    ]}]
    _, rec = _recon(_ALIAS_BOARD, rosters)
    assert waiver_pool.alias_refusals(rec) == []
    assert [r["name"] for r in rec["off_board"]] == ["Practice Squad Guy"]
    assert rec["alias_suspects"] == []


def test_the_detector_is_silent_on_a_league_that_reconciles_exactly():
    """The ⑫ runtime-gate shape: every rostered player matched, nothing to report."""
    rosters = [{"players": [
        {"name": "Joshua Palmer", "position": "WR", "team": "BUF"},
        {"name": "Bijan Robinson", "position": "RB", "team": "ATL"},
    ]}]
    _, rec = _recon(_ALIAS_BOARD, rosters)
    assert waiver_pool.alias_refusals(rec) == []
    assert (rec["off_board"], rec["alias_suspects"]) == ([], [])
    assert rec["matched"] == 2
    assert rec["implied_rostered"]["WR"] == 1 and rec["live_rostered"]["WR"] == 1


def test_the_alias_comparison_does_not_fire_on_two_different_players():
    """⛔ A DETECTOR MAY BE GENEROUS; IT MAY NOT BE FUZZY.

    Same last name, same position, DIFFERENT first names that are not a prefix of each other. A
    comparison loose enough to call these one player would refuse healthy leagues on brothers and
    namesakes — and the refusal costs the whole list.
    """
    board = [{"name": "Jason Kelce", "pos": "TE", "team": "PHI", "id": "k1"}]
    rosters = [{"players": [{"name": "Travis Kelce", "position": "TE", "team": "PHI"}]}]
    _, rec = _recon(board, rosters)
    assert rec["alias_suspects"] == []
    assert [r["name"] for r in rec["off_board"]] == ["Travis Kelce"]


def test_a_generational_suffix_is_not_an_alias_because_the_join_already_folds_it():
    """"Tyrone Tracy" / "Tyrone Tracy Jr." was the RUNTIME CHECK's artifact, never the join's.

    `normalize_player_name` strips suffixes, so these key identically and subtract normally. The
    detector must therefore report NOTHING here — if it fired, it would be duplicating a fold that
    already works and refusing a league for it.
    """
    board = [{"name": "Tyrone Tracy Jr.", "pos": "RB", "team": "NYG", "id": "t1"}]
    rosters = [{"players": [{"name": "Tyrone Tracy", "position": "RB", "team": "NYG"}]}]
    groups, rec = _recon(board, rosters)
    assert [p["name"] for g in groups for p in g["players"]] == []
    assert (rec["off_board"], rec["alias_suspects"]) == ([], [])


def test_a_team_defence_is_never_an_alias_suspect():
    """The D/ST key is the FRANCHISE, not the name (NF-C6P3), so no spelling can miss it."""
    board = [{"name": "DET D/ST", "pos": "DST", "team": "DET", "id": "d1"}]
    rosters = [{"players": [{"name": "Detroit Lions", "position": "DEF", "team": "DET"}]}]
    groups, rec = _recon(board, rosters)
    assert [p["name"] for g in groups for p in g["players"]] == []
    assert rec["alias_suspects"] == []


def test_the_endpoint_withholds_the_pool_when_the_alias_detector_fires(monkeypatch):
    """⑰ END TO END: the detector is wired AHEAD of serving, not merely importable.

    The board carries "Joshua Palmer"; the league's refreshed roster spells him "Josh Palmer". The
    response must withhold the pool, carry the named reason, and hand back the pair — a detector that
    computed all this and still served the list would be the defect wearing a report.
    """
    record = {"league_id": "L1", "season": 2026, "platform": "sleeper", "n_teams": 1,
              "source_league_id": "S1", "source_team_key": "7", "imported_roster": [],
              "roster": FULL_PPR_ROSTER,
              "league_rosters": [{"team_key": "7", "players": [
                  {"name": "Josh Palmer", "position": "WR", "team": "NYJ"}]}]}
    fresh = {"rosters": [{"team_key": "7", "team_name": "Mine", "players": [
        {"name": "Josh Palmer", "position": "WR", "team": "NYJ"}]}],
        "synced_at": "2026-09-18T12:00:00+00:00", "note": [], "teams_full": {}}
    board = {"players": [
        {"id": "00-0000003", "name": "Joshua Palmer", "pos": "WR", "team": "NYJ", "fpPpr": 100.0},
    ]}
    out, _ = _waiver_route_harness(monkeypatch, record, fresh, projections=board)

    assert out["pool"] is None, "the pool was served with a rostered player still in it"
    assert out["refusals"] == ["rostered_alias_unmatched"]
    assert out["reconciliation"]["alias_suspects"][0]["rostered"]["name"] == "Josh Palmer"
    assert [b["name"] for b in out["reconciliation"]["alias_suspects"][0]["board"]] == ["Joshua Palmer"]


def test_the_endpoint_still_serves_a_pool_when_a_rostered_player_is_merely_off_the_board(monkeypatch):
    """The two-sided half at the ROUTE: an off-board rostered player must not cost the list."""
    record = {"league_id": "L1", "season": 2026, "platform": "sleeper", "n_teams": 1,
              "source_league_id": "S1", "source_team_key": "7", "imported_roster": [],
              "roster": FULL_PPR_ROSTER,
              "league_rosters": [{"team_key": "7", "players": [
                  {"name": "Nobody On Our Board", "position": "WR", "team": "NYJ"}]}]}
    fresh = {"rosters": record["league_rosters"], "synced_at": "2026-09-18T12:00:00+00:00",
             "note": [], "teams_full": {}}
    out, _ = _waiver_route_harness(monkeypatch, record, fresh)

    assert out["refusals"] == []
    assert out["pool"] is not None
    assert [r["name"] for r in out["reconciliation"]["off_board"]] == ["Nobody On Our Board"]
