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
            players=(C.ImportedPlayer(player_key="999", name="A Back", position="RB", team="SF"),),
        ),
    )
    orig = sleeper._fetch_teams
    sleeper._fetch_teams = lambda lid: (fake, [])
    try:
        out = sleeper.refresh_league_rosters("123")
    finally:
        sleeper._fetch_teams = orig

    assert set(out) == {"rosters", "synced_at", "note"}
    team = out["rosters"][0]
    assert set(team) == {"team_key", "team_name", "players"}
    assert set(team["players"][0]) == set(LEAGUE_ROSTER_PLAYER_FIELDS), (
        "the refresh's player shape must match LEAGUE_ROSTER_PLAYER_FIELDS exactly"
    )
    assert "player_key" not in team["players"][0]
    assert out["synced_at"], "the fetch must stamp its own time — the caller re-stamps this"


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
