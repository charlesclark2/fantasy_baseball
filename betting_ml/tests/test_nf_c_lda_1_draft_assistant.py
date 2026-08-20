"""NF-C-LDA-1 — the live-draft assistant's SERVER half.

Covers the two things that decide whether the overlay is trustworthy:

  1. RESOLUTION — ESPN's draftable pool → our board ids, through the SHIPPED join, with a non-match
     reported by CAUSE rather than as one number (NF-K1). Includes the `Travis Hunter` two-way fix.
  2. THE RECOMMENDATION CONTRACT — the response names the pick it reasoned about, says whether it
     knows which team is the caller's, and is entitlement-gated on the server.

⭐ THE POOL FIXTURE IS A REAL ESPN PAYLOAD (`espn_league_642070_2025_drafted.json`, the committed
capture NF-C0 already validates against), not a hand-made one. A hand-made pool would encode what
its author believes ESPN publishes, and every defect this story fixes is a case where that belief
was wrong — `Travis Hunter`'s `eligibleSlots` spanning both sides of the ball is not a shape anyone
would have invented.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60): nothing here is bolted onto an older story's guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.services import draft_assistant, league_scoring, projection_fields
from app.backend.services.platform_import import espn as espn_import

_FIXTURES = Path(__file__).parent / "fixtures"
_ESPN_LEAGUE = _FIXTURES / "espn_league_642070_2025_drafted.json"
_BOARD_INPUT = _FIXTURES / "nf_c_lda_1_optimizer_parity_input.json"

#: ⭐ MEASURED, NOT INVENTED — Travis Hunter's real row from ESPN's 2025 player universe
#: (`artifacts/espn_cache/espn_2025.json`). `defaultPositionId` 3 is WR; the slots span WR (4) and
#: CB/DB/DP (12/14/15), which is why the pre-fix derivation returned "CB" and dropped him.
TRAVIS_HUNTER = {
    "id": "4685415",
    "fullName": "Travis Hunter",
    "proTeamId": 30,
    "defaultPositionId": 3,
    "eligibleSlots": [3, 4, 5, 23, 7, 20, 21, 12, 14, 15],
}


@pytest.fixture(scope="module")
def espn_payload() -> dict:
    return json.loads(_ESPN_LEAGUE.read_text())


@pytest.fixture(scope="module")
def espn_pool(espn_payload: dict) -> list[dict]:
    """Every rostered player in the real capture, as the extension would forward them."""
    pool: list[dict] = []
    for team in espn_payload.get("teams") or []:
        for entry in (team.get("roster") or {}).get("entries") or []:
            player = (entry.get("playerPoolEntry") or {}).get("player") or entry.get("player")
            if not player:
                continue
            pool.append({k: player.get(k) for k in
                         ("id", "fullName", "proTeamId", "defaultPositionId", "eligibleSlots")})
    return pool


@pytest.fixture(scope="module")
def board() -> dict:
    source = json.loads(_BOARD_INPUT.read_text())
    return {"players": source["board"], "replacement": source["replacement"]}


@pytest.fixture(scope="module")
def config():
    from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

    return LeagueConfig.from_dict(json.loads(_BOARD_INPUT.read_text())["config"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Resolution
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_pool_fixture_is_real_and_populated(espn_pool):
    """⚠️ ANTI-VACUITY. Every clause below filters this pool; an empty one passes on nothing."""
    assert len(espn_pool) > 150, f"only {len(espn_pool)} pool rows — the join is barely exercised"
    assert all(r.get("eligibleSlots") for r in espn_pool), "a row lost its slots — position is derived from them"


def test_a_real_espn_pool_resolves_onto_the_board(espn_pool, board):
    """The headline number, with the causes kept apart.

    Measured on this same fixture by `extension/tools/measure_resolution.py`: the NAME rung alone
    resolves 170/172 with a 0.0% JOIN-FAILURE rate, both misses being players absent from the board
    entirely. This asserts that shape rather than a bare rate — a rate hides which of the three
    causes you have (NF-K1), and only `join_failure` is a defect in the join.
    """
    out = draft_assistant.resolve_pool(espn_pool, board["players"])
    report = out["report"]
    assert report["resolved"] >= int(0.95 * report["considered"]), report
    assert report["unresolved_by_cause"].get("join_failure", 0) == 0, (
        f"the board join FAILED on {report['unresolved_by_cause'].get('join_failure')} players "
        f"whose names are on the board: {report['unresolved']}"
    )
    assert report["tier1"] == "not_attempted", (
        "tier 1 must report a NAMED state — a 0 would read as 'the id rung resolved nothing'"
    )


def test_a_two_way_player_resolves_to_his_offensive_position(board):
    """🔴 THE SPIKE'S TOP RESOLUTION DEFECT. Travis Hunter derived as CB and was dropped entirely —
    1 of 1,027 draftable rows, and a premium pick, so the assistant would have shown nothing."""
    assert espn_import._player_position(TRAVIS_HUNTER) == "WR"
    out = draft_assistant.resolve_pool([TRAVIS_HUNTER], board["players"])
    # He resolves, OR he is a cause-3 miss (absent from this season's board) — never a `join_failure`
    # and never dropped for being non-projectable, which is what "derives as CB" produced.
    assert out["report"]["skipped_non_projectable"] == 0, (
        "a two-way player was skipped as non-projectable — the position derivation regressed"
    )


def test_the_position_tiebreak_cannot_override_an_unambiguous_player():
    """⛔ THE GUARD ON THE FIX. `defaultPositionId` is the WRONG source for an ordinary player
    (NF-C0 §4c: id 4 is TE while slot 4 is WR), so it may only CHOOSE among positions
    `eligibleSlots` already established. Kittle carries `defaultPositionId` 4 and must stay TE;
    Mahomes carries 1 and must stay QB. If the tie-break ever became a lookup, these flip."""
    assert espn_import._player_position({"defaultPositionId": 4, "eligibleSlots": [5, 6, 23, 7, 20, 21]}) == "TE"
    assert espn_import._player_position({"defaultPositionId": 1, "eligibleSlots": [0, 7, 20, 21]}) == "QB"
    # A primary id that names a position the slots do NOT support is ignored, not obeyed.
    assert espn_import._player_position({"defaultPositionId": 1, "eligibleSlots": [4, 20]}) == "WR"


def test_an_idp_row_is_skipped_rather_than_counted_as_a_miss(board):
    """A linebacker is not a resolution failure — we never project one. Counting it as unresolved
    would make the report read as though the join were broken on a third of the pool."""
    lb = {"id": "999", "fullName": "Some Linebacker", "proTeamId": 9,
          "defaultPositionId": 9, "eligibleSlots": [10, 15, 20, 21]}
    report = draft_assistant.resolve_pool([lb], board["players"])["report"]
    assert report["skipped_non_projectable"] == 1
    assert report["considered"] == 0, "an IDP row inflated the resolution denominator"


def test_two_pool_rows_claiming_one_board_row_resolve_for_NEITHER(board):
    """⛔ RULE (b) — AMBIGUITY IS AN UNRESOLVED, NOT A COIN FLIP.

    A wrong merge shows one real player's projection under another's name, which is worse than
    showing nothing. Defensive rather than urgent (measured ZERO collisions in a real draftable
    pool), so this fixture manufactures the collision the real pool does not currently contain.
    """
    target = next(p for p in board["players"] if p["pos"] in ("RB", "WR"))
    twins = [
        {"id": "1001", "fullName": target["name"], "proTeamId": None,
         "defaultPositionId": None, "eligibleSlots": [2 if target["pos"] == "RB" else 4]},
        {"id": "1002", "fullName": f"{target['name']} Jr.", "proTeamId": None,
         "defaultPositionId": None, "eligibleSlots": [2 if target["pos"] == "RB" else 4]},
    ]
    out = draft_assistant.resolve_pool(twins, board["players"])
    assert out["report"]["collisions"] == 1, "the two rows did not collide — fixture is not exercising the rule"
    assert "1001" not in out["by_espn_id"] and "1002" not in out["by_espn_id"], (
        "one of two colliding pool rows still claimed the board row"
    )
    assert out["report"]["unresolved_by_cause"].get("ambiguous") == 2


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The recommendation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_live_draft_state_produces_ranked_recommendations(espn_pool, board, config):
    """End to end: a real pool, a real board, a real config, mid-draft."""
    drafted = [r["id"] for r in espn_pool[:24]]
    mine = [str(r) for r in drafted[:3]]
    out = draft_assistant.recommend_for_state(
        board=board, config=config, pool=espn_pool,
        drafted_espn_ids=[str(d) for d in drafted], my_espn_ids=mine, top_n=8,
    )
    recs = out["recommendations"]
    assert len(recs) == 8
    scores = [r["score"] for r in recs]
    # Ordering is the engine's three keys (must_fill, then not-deferred, then score), so score is
    # non-increasing only WITHIN a group — assert the property the engine actually promises.
    assert scores == sorted(scores, reverse=True) or any(r["must_fill"] or r["deferred"] for r in recs)
    assert all(r["why"] for r in recs), "a recommendation shipped without a reason"
    assert all(r["player_id"] not in drafted for r in recs), "an already-drafted player was recommended"


def test_a_drafted_player_never_reappears_as_a_recommendation(espn_pool, board, config):
    """The one correctness property a live tool cannot get wrong twice: it must forget nobody."""
    resolved = draft_assistant.resolve_pool(espn_pool, board["players"])["by_espn_id"]
    taken_espn = list(resolved)[:40]
    taken_board = {resolved[e] for e in taken_espn}
    out = draft_assistant.recommend_for_state(
        board=board, config=config, pool=espn_pool,
        drafted_espn_ids=taken_espn, my_espn_ids=taken_espn[:5], top_n=25,
    )
    assert taken_board, "fixture resolved nobody — the assertion below would be vacuous"
    assert not taken_board & {r["player_id"] for r in out["recommendations"]}


def test_my_roster_comes_back_in_board_terms(espn_pool, board, config):
    """The overlay must never have to re-join anything — that would be a second matcher."""
    resolved = draft_assistant.resolve_pool(espn_pool, board["players"])["by_espn_id"]
    mine = list(resolved)[:4]
    out = draft_assistant.recommend_for_state(
        board=board, config=config, pool=espn_pool,
        drafted_espn_ids=mine, my_espn_ids=mine, top_n=5,
    )
    assert len(out["my_roster"]) == len(mine)
    assert all(row["name"] and row["pos"] for row in out["my_roster"]), (
        "a roster row came back without identity — the overlay would have to re-join it"
    )


def test_the_engine_row_adapter_carries_replacement_even_when_the_row_omits_it(board):
    """`replacement_points` has no same-named board column and drives BOTH the last-player VONA
    fallback and the flex-seat re-basing, so a silent 0 here changes recommendations."""
    row = dict(board["players"][0])
    row.pop("repl", None)
    adapted = draft_assistant.engine_row(row, board["replacement"])
    assert adapted["replacement_points"] == board["replacement"][adapted["position"]]
