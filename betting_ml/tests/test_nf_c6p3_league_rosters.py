"""NF-C6P3 — storing the WHOLE league's rosters, and the D/ST join that never worked.

Two defects rode on one finding. We ALREADY fetched every team's roster at import
(`ImportedLeague.teams[].players` — it is what the "which team is yours?" screen is built from) and
then stored one of them, so the roster report's waiver section said "we do not hold your league's
other rosters" about a limit we had imposed on ourselves. And the board publishes a team defence as
"DET D/ST" while every platform publishes it as a NICKNAME, so the D/ST starting slot has been empty
— and silently absent from the headline total — for every imported league since the report shipped.

What is pinned here is what a browser cannot see:

  1. THE D/ST JOIN MATCHES, FROM ALL THREE DIRECTIONS, ON REAL CAPTURED DATA — and the pre-fix
     behaviour is reproduced from the same fixtures so "it matches now" is measured against "it
     matched nothing before" rather than asserted.
  2. THE TWO IMPLEMENTATIONS AGREE. The live server joins with `league_scoring.py`; the E2E harness
     scores through `lib/league-scoring.ts`. A map extended in one and not the other is the E9.61
     "two renderers of one field are two rule sets" defect, and it presents as a platform quietly
     ceasing to match.
  3. THE STORED FIELD IS BOUNDED AND TRUNCATES BY WHOLE TEAMS. All of a user's leagues share ONE
     400 KB DynamoDB item, and an overflow there is not a degraded feature — it is a user row that
     can never be written again.
  4. THE FREE-AGENT POOL EXCLUDES ROSTERED PLAYERS, and only calls itself one when we hold every
     roster.

RED-PROVEN: `uv run python betting_ml/tests/nf_c6p3_red_proof.py`. ⚠️ Each clause that names a
specific rule has its OWN fixture in which every other clause is satisfied (NF-D17 §7): a fixture
that trips two clauses tests neither, because the first refusal hides the second.

Pure/offline (fast gate): reads committed fixtures and source files. No DuckDB/S3/network, no
`pipeline` import.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.backend.models import fantasy as models
from app.backend.services import league_scoring as ls

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
TS_SCORING = FRONTEND / "lib/league-scoring.ts"
TS_REPORT_LIB = FRONTEND / "lib/roster-report.ts"
TS_CLAIM_COPY = FRONTEND / "lib/fantasy-claim-copy.ts"
TS_IMPORT_UI = FRONTEND / "components/fantasy/league-import.tsx"
ROUTER = REPO / "app/backend/routers/fantasy.py"
DYNAMO = REPO / "app/backend/services/dynamo.py"

#: The real captured ESPN league — 10 teams, 172 players, 15 team defences under their nicknames.
ESPN_PREVIEW = FRONTEND / "e2e/fixtures/api/fantasy-import-espn-preview-642070-2025.json"
#: The served projection universe the board is built from.
PROJECTIONS = FRONTEND / "e2e/fixtures/api/fantasy-nfl-projections-2026-entitled.synthetic.json"


def _strip_ts_comments(src: str) -> str:
    """Line comments BEFORE block comments — a `//` inside a `/* */` is prose (E9.61).

    ⚠️ This is what stops a source guard being satisfied by a COMMENT (INC-38).
    """
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


@pytest.fixture(scope="module")
def board_players() -> list[dict]:
    """The board rows, in the shape `match_roster_to_board` consumes."""
    players = json.loads(PROJECTIONS.read_text())["players"]
    rows = [{"id": p["id"], "name": p["name"], "pos": p["pos"], "team": p.get("team")} for p in players]
    assert any(r["pos"] == "DST" for r in rows), "the projections fixture carries no D/ST rows"
    return rows


@pytest.fixture(scope="module")
def espn_teams() -> list[dict]:
    teams = json.loads(ESPN_PREVIEW.read_text())["teams"]
    assert len(teams) >= 2, "the captured ESPN league has fewer than two teams"
    return teams


@pytest.fixture(scope="module")
def espn_dst_rows(espn_teams: list[dict]) -> list[dict]:
    """Every D/ST row across the captured league — real platform renderings, nicknames and all."""
    rows = [p for t in espn_teams for p in (t.get("players") or []) if p.get("position") == "DST"]
    # ⚠️ NON-VACUITY FIRST. Every clause below iterates this list; an empty one would make them all
    # pass on nothing, which is the guard-that-cannot-fail class arriving through the fixture.
    assert len(rows) >= 5, f"only {len(rows)} D/ST rows in the capture — the join clauses are thin"
    return rows


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. The D/ST join — measured against what it used to do
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _legacy_key(name: str, pos: str | None) -> str:
    """The PRE-NF-C6P3 join key, restated here so the fix is measured rather than asserted.

    ⚠️ Kept as an independent restatement rather than imported: if the production key function is
    what defines "before", then any change to it silently redefines the baseline and the clause
    below could go green because the comparison moved rather than because the join improved.
    """
    return f"{ls.normalize_player_name(name)}|{ls.normalize_position(pos or '')}"


def test_the_old_name_join_matched_no_team_defence_at_all(board_players, espn_dst_rows):
    """⭐ THE BASELINE, MEASURED. Every captured D/ST row against every board D/ST row under the old
    key: the count must be ZERO. This is what makes the next clause a fix rather than a claim — and
    if a future board ever started publishing nicknames, this clause going red is the signal that
    the whole team-defence branch has become unnecessary."""
    board_keys = {_legacy_key(str(p["name"]), p["pos"]) for p in board_players}
    matched = [r for r in espn_dst_rows if _legacy_key(str(r["name"]), r["position"]) in board_keys]
    assert matched == [], (
        f"{len(matched)} team defences already matched on the plain name join — the premise of "
        f"NF-C6P3's D/ST fix no longer holds: {[r['name'] for r in matched][:5]}"
    )


def test_every_captured_team_defence_now_joins_to_its_board_row(board_players, espn_dst_rows):
    """The fix, on the real capture. Not "more of them match" — ALL of them, to the RIGHT franchise.

    Asserted against `DST-<abbrev>`, so a join that matched the wrong defence (which would credit a
    user with points they never drafted — worse than the honest miss it replaces) fails here rather
    than reading as a success."""
    joined = ls.match_roster_to_board(espn_dst_rows, board_players)
    misses = [r["roster"]["name"] for r in joined if r["board"] is None]
    assert misses == [], f"team defences still unmatched after the fix: {misses}"
    for row in joined:
        assert row["board"]["id"] == f"DST-{row['roster']['team']}", (
            f"{row['roster']['name']} (team {row['roster']['team']}) joined to "
            f"{row['board']['id']} — the WRONG franchise"
        )


def test_the_defence_join_works_without_the_team_field(board_players, espn_dst_rows):
    """A platform that supplies no `team` (an older capture, a hand-entered roster) must still
    resolve — from the NICKNAME in the name. Its own fixture: `team` is the only thing removed, so
    only the nickname branch can be what carries it."""
    stripped = [{**r, "team": None} for r in espn_dst_rows]
    joined = ls.match_roster_to_board(stripped, board_players)
    misses = [r["roster"]["name"] for r in joined if r["board"] is None]
    assert misses == [], f"nickname resolution failed for: {misses}"


def test_the_defence_join_works_when_the_board_carries_no_team(espn_dst_rows):
    """The BOARD side resolved from its own name ("DET D/ST"). Its own fixture: the roster side is
    left intact, so only the board-side abbreviation branch can be what carries it."""
    players = json.loads(PROJECTIONS.read_text())["players"]
    board = [{"id": p["id"], "name": p["name"], "pos": p["pos"]} for p in players]
    joined = ls.match_roster_to_board(espn_dst_rows, board)
    misses = [r["roster"]["name"] for r in joined if r["board"] is None]
    assert misses == [], f"board-side abbreviation resolution failed for: {misses}"


@pytest.mark.parametrize(
    "name,team,expected",
    [
        ("Lions D/ST", "DET", "DET"),   # ESPN, with its team field
        ("Lions D/ST", None, "DET"),    # ESPN, nickname only
        ("Detroit Lions", None, "DET"), # Sleeper's players cache
        ("Detroit", "Det", "DET"),      # Yahoo — city name, mixed-case abbreviation
        ("DET D/ST", None, "DET"),      # our own board
        ("49ers D/ST", None, "SF"),     # ⚠️ folds to "ers" — digits do not survive normalization
        ("Raiders D/ST", "OAK", "LV"),  # a relocated franchise under its old abbreviation
        ("Rams D/ST", "STL", "LAR"),
        ("Commanders D/ST", "WSH", "WAS"),
        ("Jaguars D/ST", "JAC", "JAX"),
    ],
)
def test_every_platform_rendering_of_a_defence_resolves(name, team, expected):
    """The renderings the three adapters actually emit, plus the relocations an older league carries.

    Parametrized so a broken case names ITSELF instead of failing a bundled assertion the other nine
    could satisfy."""
    assert ls.dst_team(name, team) == expected


def test_an_unresolvable_defence_is_an_honest_miss_not_a_guess(board_players):
    """⛔ NO FUZZY FALLBACK. A row we cannot place must come back `board: None` — matching the WRONG
    defence would silently credit a user with points they did not draft, which is strictly worse
    than the miss this replaces (rule 3 of the report: an absence is reported, never imputed)."""
    assert ls.dst_team("Springfield Isotopes D/ST", "XXX") == ""
    joined = ls.match_roster_to_board(
        [{"name": "Springfield Isotopes D/ST", "position": "DST", "team": "XXX"}], board_players
    )
    assert joined[0]["board"] is None


def test_an_unknown_abbreviation_does_not_resolve_to_itself():
    """`normalize_team` answers `""`, never the input. A key built from an unrecognised abbreviation
    can only ever match itself — a silent no-match dressed up as a resolution."""
    assert ls.normalize_team("XYZ") == ""
    assert ls.normalize_team("") == ""
    assert ls.normalize_team(None) == ""


def test_the_defence_branch_leaves_every_other_position_alone(board_players, espn_teams):
    """⚠️ THE REGRESSION SIDE. The name join works for 95% of a roster and this story does not
    rewrite it. Every NON-D/ST row in the capture must join exactly as it did before."""
    skill = [
        p
        for t in espn_teams
        for p in (t.get("players") or [])
        if p.get("position") not in (None, "DST")
    ]
    assert len(skill) > 100, f"only {len(skill)} skill rows — the regression clause is thin"
    board_keys = {}
    for p in board_players:
        board_keys.setdefault(_legacy_key(str(p["name"]), p["pos"]), p["id"])
    joined = ls.match_roster_to_board(skill, board_players)
    for row in joined:
        expected = board_keys.get(_legacy_key(str(row["roster"]["name"]), row["roster"]["position"]))
        got = row["board"]["id"] if row["board"] else None
        assert got == expected, (
            f"{row['roster']['name']} joined to {got}, but the plain name join gives {expected} — "
            "the team-defence branch has changed a non-defence row"
        )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. The two implementations of one join
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _ts_record(name: str) -> dict[str, str]:
    """Parse a `export const NAME: Record<string,string> = { ... }` literal out of the TS module."""
    src = _strip_ts_comments(TS_SCORING.read_text())
    assert name in src, f"{name} is not declared in {TS_SCORING.name}"
    body = src.split(name, 1)[1].split("= {", 1)[1].split("}", 1)[0]
    return {
        k.strip().strip('"').strip("'"): v.strip().strip('"').strip("'")
        for k, v in (pair.split(":", 1) for pair in body.split(",") if ":" in pair)
    }


def test_the_nickname_map_is_identical_in_python_and_typescript():
    """⚠️ THE LIVE SERVER JOINS WITH THE PYTHON; THE E2E HARNESS SCORES THROUGH THE TYPESCRIPT.
    A nickname added to one and not the other is E9.61's "two renderers of one field are two rule
    sets", and it presents as one platform quietly ceasing to match a defence."""
    mirrored = _ts_record("NFL_TEAM_BY_NICKNAME")
    assert mirrored == ls.NFL_TEAM_BY_NICKNAME, (
        "the nickname maps have drifted; "
        f"only in Python: {sorted(set(ls.NFL_TEAM_BY_NICKNAME) - set(mirrored))}; "
        f"only in TypeScript: {sorted(set(mirrored) - set(ls.NFL_TEAM_BY_NICKNAME))}"
    )


def test_the_abbreviation_alias_map_is_identical_in_python_and_typescript():
    mirrored = _ts_record("NFL_TEAM_ABBREV_ALIASES")
    assert mirrored == ls.NFL_TEAM_ABBREV_ALIASES, (
        "the abbreviation alias maps have drifted; "
        f"only in Python: {sorted(set(ls.NFL_TEAM_ABBREV_ALIASES) - set(mirrored))}; "
        f"only in TypeScript: {sorted(set(mirrored) - set(ls.NFL_TEAM_ABBREV_ALIASES))}"
    )


def test_the_nickname_map_covers_every_franchise_the_research_tree_knows():
    """⭐ ANCHORED ON THE REPO'S EXISTING AUTHORITY rather than on this session's memory of the NFL.
    `coaching_source._FRANCHISE_ERAS` carries every franchise and every name it has played under; a
    map maintained by hand against nothing drifts the first time a team is renamed.

    ⚠️ Asserted through `dst_team` rather than against the map's KEYS, and the difference is not
    cosmetic: a key-membership check assumes the nickname is the last word of the full name, which
    is exactly the assumption "Washington Football Team" breaks — it is what surfaced the two-word
    entry and the adjacent-pair lookup that carries it.
    """
    from quant_sports_intel_models.football.nfl.fantasy import coaching_source as cs

    assert len(cs._FRANCHISE_ERAS) == 32, "the franchise authority no longer covers 32 teams"
    for abbrev, eras in cs._FRANCHISE_ERAS.items():
        for _since, full_name in eras:
            assert ls.dst_team(full_name, None) == abbrev, (
                f"{full_name!r} resolves to {ls.dst_team(full_name, None)!r}, but the franchise "
                f"table says {abbrev} — a league naming its defence that way will not join"
            )


def test_every_board_abbreviation_is_a_target_of_the_nickname_map(board_players):
    """The map's targets must BE the abbreviations the board publishes. A nickname resolving to a
    spelling the board does not use is a key that matches nothing — the silent-empty class."""
    published = {p["team"] for p in board_players if p["pos"] == "DST" and p.get("team")}
    assert len(published) == 32, f"the board publishes {len(published)} defences, not 32"
    missing = sorted(published - set(ls.NFL_TEAM_BY_NICKNAME.values()))
    assert not missing, f"board abbreviations no nickname resolves to: {missing}"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. The stored field — bounded, and truncated by WHOLE TEAMS
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def _rosters(teams: int, players_per_team: int) -> list[dict]:
    return [
        {
            "team_key": f"t{i}",
            "team_name": f"Team {i}",
            "players": [
                {"name": f"P{i}-{j}", "position": "WR", "team": "SF", "player_key": "x", "starter": True}
                for j in range(players_per_team)
            ],
        }
        for i in range(teams)
    ]


def _base_payload(**overrides) -> dict:
    payload = {
        "name": "Test League",
        "n_teams": 12,
        "scoring": {"per_stat": {"rec": 1.0}, "position_bonuses": {}},
        "roster": [
            {"name": "QB", "count": 1, "eligible": ["QB"], "bench": False},
            {"name": "BN", "count": 6, "eligible": [], "bench": True},
        ],
    }
    payload.update(overrides)
    return payload


def test_a_normal_league_is_stored_whole():
    """⚠️ NON-VACUITY FOR THE THREE CLAUSES BELOW. If the bound rejected everything they would all
    pass while the feature was dead."""
    saved = models.LeagueSave(**_base_payload(league_rosters=_rosters(12, 18)))
    assert len(saved.league_rosters) == 12
    assert saved.league_rosters_truncated is False
    assert sum(len(t["players"]) for t in saved.league_rosters) == 216


def test_the_stored_player_row_is_slimmed_to_the_join_fields():
    """`player_key` is a platform id joinable to nothing of ours; `starter` is THEIR lineup decision,
    which the comparison explicitly does not use. Dropping both is what keeps this field inside the
    shared item budget.

    ⚠️ ASSERTED AGAINST THE LITERAL FIELD SET, NOT AGAINST `LEAGUE_ROSTER_PLAYER_FIELDS`. Comparing
    the stored row to the constant that PRODUCED it is a restatement of the code, not a test of it:
    widen the constant and both sides move together. The red proof caught exactly that — this clause
    stayed green with `player_key` and `starter` added back to the constant (the NF-C0e "a test that
    reads a value back under the key the code wrote can never catch a wrong key" class).
    """
    saved = models.LeagueSave(**_base_payload(league_rosters=_rosters(2, 1)))
    row = saved.league_rosters[0]["players"][0]
    assert set(row) == {"name", "position", "team"}
    for dropped in ("player_key", "starter"):
        assert dropped not in row, (
            f"{dropped!r} is being stored for every player on every team in the league — it joins to "
            "nothing of ours and the field is up against a shared 400 KB item ceiling"
        )
    assert set(models.LEAGUE_ROSTER_PLAYER_FIELDS) == {"name", "position", "team"}


def test_a_league_over_the_player_cap_truncates_by_whole_teams():
    """⭐ THE SHAPE OF THE TRUNCATION IS THE POINT. A team is kept ENTIRE or not at all: a
    half-stored roster produces an optimal-lineup total that is quietly too low and looks exactly
    like a real one, whereas a missing team is simply absent and can be counted and named."""
    over = _rosters(32, 30)  # 960 players against a 500 cap
    kept, truncated = models.bound_league_rosters(over)
    assert truncated is True
    assert sum(len(t["players"]) for t in kept) <= models.MAX_LEAGUE_ROSTER_PLAYERS
    original = {t["team_key"]: len(t["players"]) for t in over}
    for team in kept:
        assert len(team["players"]) == original[team["team_key"]], (
            f"{team['team_key']} was stored with {len(team['players'])} of its "
            f"{original[team['team_key']]} players — truncation must drop whole teams"
        )


def test_a_league_over_the_team_cap_truncates():
    kept, truncated = models.bound_league_rosters(_rosters(40, 1))
    assert truncated is True
    assert len(kept) == models.MAX_LEAGUE_ROSTER_TEAMS


def test_an_oversized_league_is_truncated_rather_than_rejected():
    """⚠️ DELIBERATELY NOT A `raise`, unlike `imported_roster`'s bound. A league's combined rosters
    legitimately run large; refusing the save would fail the user's whole import over an enhancement
    they never asked for, and the visible symptom would be "saving is broken" (E8.6)."""
    saved = models.LeagueSave(**_base_payload(league_rosters=_rosters(40, 30)))
    assert saved.league_rosters_truncated is True
    assert len(saved.league_rosters) <= models.MAX_LEAGUE_ROSTER_TEAMS


def test_a_client_declared_truncation_is_never_overwritten():
    """Truncation is a claim that can only be ADDED to. A client that already dropped teams has told
    us something true, and answering with our own `False` would erase it."""
    saved = models.LeagueSave(
        **_base_payload(league_rosters=_rosters(2, 2), league_rosters_truncated=True)
    )
    assert saved.league_rosters_truncated is True


def test_a_malformed_roster_entry_costs_only_itself():
    """A single junk row must not cost the user their save — but it counts as truncation, so the
    loss is never silent."""
    kept, truncated = models.bound_league_rosters(
        [*_rosters(1, 2), "not a team", {"team_key": "t9", "team_name": "T9", "players": "nope"}]
    )
    assert truncated is True
    assert [t["team_key"] for t in kept] == ["t0", "t9"]
    assert kept[1]["players"] == []


def test_the_response_model_carries_no_write_rule():
    """🚨 E9.49. A rule tightened for SAVES must never run on the READ path: a stored league that
    predates a tightening would start raising on read, and one bad row blanks the whole collection.
    An oversized league already in storage must read back INTACT."""
    stored = _base_payload(league_id="lg1", league_rosters=_rosters(40, 30))
    out = models.League(**stored)
    assert len(out.league_rosters) == 40
    assert len(out.league_rosters[0]["players"]) == 30


def test_the_writer_carries_a_total_item_budget():
    """⭐ THE PER-LEAGUE CAP ALONE CANNOT KEEP THE ITEM SAFE, AND THAT IS WHY THIS EXISTS.

    Every one of a user's leagues lives in ONE DynamoDB `fantasy_leagues` map on ONE item, sharing a
    400 KB ceiling with their portfolio, platform tokens and MLB leagues. 25 leagues × a 14-team
    roster set is past that ceiling on its own — and an overflow is not a degraded feature, it is a
    user row that can never be written again (no new league, no bet, no preference).

    Asserted as ARITHMETIC on the shipped constants, so a per-league cap raised without moving the
    budget fails here rather than in production.
    """
    worst_case = models.MAX_LEAGUE_ROSTER_PLAYERS * 60  # ~60 bytes per slimmed player row
    assert worst_case * 25 > dynamo_module().DYNAMO_ITEM_LIMIT_BYTES, (
        "the per-league cap now fits 25 times inside the item limit — if that is genuinely true the "
        "budget below is redundant, but check the arithmetic before deleting it"
    )
    # ⚠️ READ THE CALL SITE INSIDE `put_fantasy_league`, NOT THE FILE. `"_fits_fantasy_budget" in
    # src` is satisfied by the function's own DEFINITION, so it stays true with every caller
    # deleted — the red proof caught this clause green with the check replaced by `if False:`. The
    # repo's own lesson, one file over: count CALL SITES, never `grep` a name (DSR-CONV #690).
    body = _put_fantasy_league_body()
    assert re.search(r"_fits_fantasy_budget\(\s*user_id", body), (
        "put_fantasy_league no longer CALLS the item-budget check before storing the league rosters"
    )
    assert "league_rosters" in body


def dynamo_module():
    """Imported lazily: `services.dynamo` constructs a boto3 resource at import, which is fine
    offline (no call is made) but is not worth paying for in the clauses that do not need it."""
    from app.backend.services import dynamo

    return dynamo


def _put_fantasy_league_body() -> str:
    """The BODY of `put_fantasy_league`, comments stripped.

    Scoping every writer clause to the function keeps them off the module's other 1,000 lines — a
    guard satisfied by a definition or by an unrelated mention elsewhere in the file is not a guard.
    """
    src = DYNAMO.read_text()
    body = src[src.index("def put_fantasy_league(") :]
    body = body[: body.index("\ndef delete_fantasy_league")]
    return re.sub(r"#[^\n]*", "", body)


def test_the_budget_drops_only_the_rosters_and_only_from_the_incoming_league():
    """⭐ FIRST-COME-FIRST-SERVED, NOT EVICTION. Making room by dropping OTHER stored leagues'
    rosters would mutate data the caller did not ask us to touch, on a write they experience as
    saving one league. Dropping this one's degrades it exactly to the pre-NF-C6P3 product."""
    body = _put_fantasy_league_body()
    block = body[body.index("_fits_fantasy_budget(user_id, league_id, record)") :]
    block = block[: block.index("table = _users_table()")]
    assert 'record["league_rosters"] = None' in block
    assert 'record["league_rosters_truncated"] = True' in block, (
        "the size-drop is silent — nothing on the stored league records that it happened"
    )
    assert "raise" not in block, "a save must not FAIL over an enhancement the user never asked for"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. What the surfaces may say about it
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_free_agent_pool_excludes_players_on_another_roster():
    """The pool is `!rosteredIds.has(id)` — read off the SHIPPING source, because this is the one
    line that turns "outside the drafted pool" into "on nobody's roster"."""
    src = _strip_ts_comments(TS_REPORT_LIB.read_text())
    assert re.search(r"if\s*\(rosteredIds\)\s*return\s*!rosteredIds\.has\(p\.id\)", src), (
        "waiverIdeas no longer excludes rostered players when the league's rosters are held"
    )


def test_a_partial_league_does_not_produce_a_free_agent_pool():
    """⭐ `complete`, NOT "we hold at least one". A pool computed from 8 of 12 rosters would list
    four teams' worth of rostered players as free agents — a confidently wrong list that reads
    exactly like a right one."""
    src = _strip_ts_comments(TS_REPORT_LIB.read_text())
    assert "rosteredIds: complete ? ids : null" in src, (
        "leagueRosterCoverage hands out a rostered-id set on PARTIAL coverage"
    )


def test_the_waiver_copy_states_which_definition_it_is_using():
    """Three states, three sentences: a true pool, a partial absence, and the old drafted-pool
    definition. Sharing copy between them is how "we could not check" starts reading as "we
    checked" (NF1.7 (a))."""
    copy = TS_CLAIM_COPY.read_text()
    for const in (
        "REPORT_FREE_AGENT_NOTE",
        "REPORT_FREE_AGENT_PARTIAL_NOTE",
        "REPORT_WAIVER_NOTE",
    ):
        assert f"export const {const}" in copy, f"{const} is missing"


def test_the_free_agent_copy_keeps_its_snapshot_hedge():
    """⚠️ ITS OWN FIXTURE, AND THE HEDGE IS THE WHOLE SENTENCE'S HONESTY. We read the league once, at
    import, and never again — so a player claimed an hour later is still listed. Dropping the clause
    turns a true sentence into a false one without changing a single number."""
    # ⚠️ COMMENTS STRIPPED FIRST. `REPORT_FREE_AGENT_NOTE` is NAMED in the prose above
    # `REPORT_WAIVER_NOTE`, so a raw split lands on the wrong constant's string and this clause
    # would screen a sentence it was not written about (INC-38: prose must not satisfy a guard).
    copy = _strip_ts_comments(TS_CLAIM_COPY.read_text())
    note = copy.split("REPORT_FREE_AGENT_NOTE", 1)[1].split('"', 2)[1]
    assert "imported" in note.lower(), "the free-agent copy no longer says the pool is a snapshot"
    assert "re-read" in note.lower() or "reread" in note.lower(), (
        "the free-agent copy no longer says we never re-read the league"
    )


def test_the_import_confirms_what_the_server_actually_stored():
    """E8.6 / NF-C0 — THE DEPLOY-SKEW GUARD. The API Lambda has no CI/CD and the FastAPI request
    models carry no `extra="forbid"`, so an un-deployed backend ACCEPTS `league_rosters`, IGNORES it
    and returns 200. Feedback derived from the payload we SENT would report "all 12 rosters stored"
    over a server that stored none — the silent-save phantom E8.6 records.

    Keyed on the read being off the RESPONSE (`res.`), which is the only thing that knows."""
    src = _strip_ts_comments(TS_IMPORT_UI.read_text())
    assert re.search(r"setStoredRosterTeams\(\s*\(res[^)]*\)[^)]*league_rosters", src, re.S), (
        "the import's roster confirmation is not read off the save RESPONSE"
    )
    assert "data-testid=\"import-stored-rosters\"" in TS_IMPORT_UI.read_text(), (
        "nothing on the import screen renders what was actually stored"
    )


def test_the_league_board_serves_the_rosters_joined_by_the_shared_function():
    """⛔ NO FOURTH SCORER, NO SECOND JOIN. The other teams go through the SAME
    `match_roster_to_board` the caller's own roster does — a second join would drift, and the
    symptom would be one table disagreeing with another with neither looking wrong."""
    src = ROUTER.read_text()
    block = src[src.index("def _joined_league_rosters") :]
    block = block[: block.index("\ndef ", 10)] if "\ndef " in block[10:] else block
    assert "league_scoring.match_roster_to_board" in block
    assert "build_board" not in block, "the league-roster join is building its own board"


def test_the_league_board_response_key_is_additive():
    """NF-C0. The deployed client knows none of this; every key it already reads must survive."""
    src = ROUTER.read_text()
    block = src[src.index('"league_rosters": _joined_league_rosters') - 1200 :]
    block = block[: block.index("def _joined_league_rosters")]
    for key in ('"season"', '"league"', '"board"', '"roster"'):
        assert key in block, f"{key} was removed from the league-board response — a deployed client reads it"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 5. NF-C6P3 (b) — the LEAGUE COMPARISON's honest-framing boundary
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# ⛔ THE MOST DANGEROUS SURFACE THIS STORY SHIPS. A standings-shaped table answers "did I win my
# draft?" whether or not it was asked, and that is the one question the product has measured nothing
# about: there is no weekly-variance schedule simulation and `best_alpha = 0`. A rank ON THIS MEASURE
# is a fact about arithmetic we performed; a projected finish is a claim about work that does not
# exist, and the distance between the two is one careless sentence.
COMPARISON_COMPONENT = FRONTEND / "components/fantasy/roster-report.tsx"

#: Outcome vocabulary the SHARED denylist does not carry, because no other surface in the product
#: was ever shaped like a standings table. ⚠️ Screened NEGATION-AWARE below: the copy's own
#: disclaimer ("it is not a projected finish") must not be what trips the guard — an over-eager scan
#: pushes the copy the wrong way, and the cheapest way to satisfy it would be to delete the hedge
#: (the NF-W7 `'temp' ⊂ 'attempt'` shape).
_OUTCOME_CLAIMS = (
    "projected finish",
    "will finish",
    "finish nth",
    "playoff odds",
    "playoff chance",
    "chance of making",
    "win probability",
    "odds of winning",
    "championship odds",
    "expected to win",
    "your ceiling is",
)

_COMPARISON_CONSTANTS = (
    "REPORT_COMPARISON_HEADING",
    "REPORT_COMPARISON_NOTE",
    "REPORT_COMPARISON_CAVEAT_LINEUP",
    "REPORT_COMPARISON_CAVEAT_SNAPSHOT",
    "REPORT_COMPARISON_CAVEAT_OURS",
    "REPORT_COMPARISON_PARTIAL",
)


def _comparison_copy() -> dict[str, str]:
    """Each comparison constant's shipped string, comments stripped.

    ⚠️ COMMENTS FIRST — the constants are NAMED in the prose above them, so a raw split lands on a
    docstring rather than on a sentence a user reads (INC-38: prose must not satisfy a guard).
    """
    src = _strip_ts_comments(TS_CLAIM_COPY.read_text())
    out: dict[str, str] = {}
    for const in _COMPARISON_CONSTANTS:
        assert f"export const {const}" in src, f"{const} is not exported from the copy module"
        out[const] = src.split(f"export const {const}", 1)[1].split('"', 2)[1]
    return out


def test_the_comparison_copy_exists_and_is_extractable():
    """⚠️ NON-VACUITY FIRST. Every clause below iterates these strings; an empty extraction would
    make them all pass on nothing — the guard-that-cannot-fail class arriving through the fixture."""
    copy = _comparison_copy()
    assert len(copy) == len(_COMPARISON_CONSTANTS)
    for const, text in copy.items():
        assert len(text) > 40, f"{const} extracted as {text!r} — the split has gone stale"


@pytest.mark.parametrize("phrase", _OUTCOME_CLAIMS)
def test_the_comparison_copy_makes_no_finish_or_odds_claim(phrase: str):
    """Parametrized so a forbidden phrase names ITSELF rather than failing a bundled assertion the
    other ten could satisfy.

    Negation-aware: the phrase may appear only after a `not`/`never`/`no` in the same sentence, which
    is exactly what the surface's own disclaimer does."""
    for const, text in _comparison_copy().items():
        lowered = text.lower()
        start = 0
        while (at := lowered.find(phrase, start)) >= 0:
            lead = lowered[max(0, at - 24) : at]
            assert re.search(r"\b(not|never|no|without)\b[^.]*$", lead), (
                f"{const} claims {phrase!r}: …{lead}{phrase}…"
            )
            start = at + len(phrase)


def test_the_comparison_copy_passes_the_shared_claim_denylist():
    """The same screen every other claim surface in the product passes. `test_nf_tr1_claim_copy.py`
    screens the whole copy module; this narrows it to the constants this story added, so a failure
    here names the sentence rather than the file."""
    from quant_sports_intel_models.football.nfl.fantasy import export_track_record_json as ex

    for const, text in _comparison_copy().items():
        hits = [t for t in ex._CLAIM_DENYLIST if t in text.lower()]
        assert not hits, f"{const} makes a forbidden claim {hits}: {text!r}"


def test_the_headline_sentence_names_the_measure_it_ranks_on():
    """⭐ THE ONE SENTENCE THE STORY PERMITS, AND ITS SHAPE IS THE PERMISSION. "You sit 7th" is what
    a reader turns into "I will finish 7th"; "7th on projected starting points" is a fact about
    arithmetic and cannot be read as a forecast. Asserted on the RENDERED string, so moving the
    qualifier out of the sentence is a failure even if the words survive elsewhere on the page."""
    src = _strip_ts_comments(COMPARISON_COMPONENT.read_text())
    block = src[src.index('data-testid="league-comparison-summary"') :]
    block = block[: block.index("</p>")]
    assert "on projected starting" in block, (
        "the comparison's headline sentence no longer names the measure its rank is on — a bare "
        "rank reads as a projected finish"
    )


def test_all_three_caveats_render_unconditionally_with_the_table():
    """⭐ NOT BEHIND A DISCLOSURE, NOT IN A TOOLTIP, NOT CONDITIONAL. A caveat behind a click is a
    caveat that did not render, and each of these three names something a reader cannot work out.

    ⚠️ Asserted inside the caveat LIST and required to be free of a `&&` guard, because "rendered"
    and "rendered when some state happens to be true" are different claims and only one of them is
    what the story requires."""
    src = _strip_ts_comments(COMPARISON_COMPONENT.read_text())
    block = src[src.index('data-testid="league-comparison-caveats"') :]
    block = block[: block.index("</ul>")]
    flat = re.sub(r"\s+", " ", block)
    for const in (
        "REPORT_COMPARISON_CAVEAT_LINEUP",
        "REPORT_COMPARISON_CAVEAT_SNAPSHOT",
        "REPORT_COMPARISON_CAVEAT_OURS",
    ):
        item = f"<li>{{{const}}}</li>"
        assert item in flat, f"{const} does not render as a caveat in the table's own list"
        # ⚠️ AND IT IS UNGUARDED. `{const in block}` alone is satisfied by
        # `{someState && <li>{CONST}</li>}`, which renders in the happy case — so a screenshot looks
        # right — and vanishes for exactly the readers who most need the hedge. The red proof caught
        # this clause green on that break, which is the whole reason the check reads the preceding
        # characters as well as the presence.
        lead = flat[max(0, flat.index(item) - 48) : flat.index(item)]
        assert "&&" not in lead and "?" not in lead, (
            f"{const} is rendered CONDITIONALLY (…{lead}{item}) — a caveat that can disappear is not "
            "a caveat the surface carries"
        )


def test_the_comparison_scores_nothing_and_reads_nothing():
    """⛔ THE NF-C6P2 ARCHITECTURE CONSTRAINT, EXTENDED TO THE NEW SECTION. It is still an
    AGGREGATOR: every total is a sum of `pts` the server already computed, through the same
    `fillLineup`/`combineInterval` the caller's own team goes through. A fourth scorer would inherit
    the whole `test_nf_epic1_parity.py` tax, and a wide read in this Lambda fails silently (E9.26b).

    ⚠️ The repo-wide version of this clause lives in `test_nf_c6p2_roster_report.py` and covers the
    same two files; this one is scoped to the comparison's own function, so a violation introduced
    HERE names this story rather than the older one (the E9.60 coupling trap)."""
    src = _strip_ts_comments(TS_REPORT_LIB.read_text())
    block = src[src.index("export function leagueComparison") :]
    # ⚠️ Bounded by a CODE anchor, not by the section comment — comments are stripped above, so a
    # comment anchor would raise and the clause would fail for a reason unrelated to what it defends.
    block = block[: block.index("export function buildRosterReport")]
    for token in ("per_stat", "STAT_FIELD", "resolveScoring", "buildBoard", "fetch(", "apiFetch"):
        assert token not in block, (
            f"{token!r} appears in leagueComparison — it is re-deriving scoring or reaching for a "
            "second source rather than aggregating the served board"
        )
    # …and it DOES go through the shared construction, so the league table and the caller's own
    # headline cannot disagree about what a lineup is.
    assert "fillLineup(" in block and "combineInterval(" in block


def test_a_single_team_is_not_rendered_as_a_comparison():
    """A one-row "comparison" is not one, and rendering it would imply a league-wide reading from a
    single team. Every league imported before this story shipped is in exactly that state."""
    src = _strip_ts_comments(TS_REPORT_LIB.read_text())
    block = src[src.index("export function leagueComparison") :]
    assert "if (held.length < 2) return null" in block, (
        "leagueComparison no longer refuses to build a table from fewer than two rosters"
    )
