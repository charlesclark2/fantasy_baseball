"""NF-C-LDA-1 follow-up — the two roster-accounting defects a live 2026 ESPN mock draft surfaced.

Both were found by DRAFTING, not by a test: the shipped engines ran clean, returned plausible
recommendations, and were wrong in a way only a full draft reveals.

  1. ⛔ AN IR SPOT IS NOT A PICK. `translate_roster` maps ESPN slot 21 (and Sleeper's reserve/taxi)
     to bench depth, and the reserve constraint counted it as a draftable slot. On the live league
     (9 starters + 6 bench + 2 IR) the roster counted as 17 against ESPN's own limit of 15, so
     `must_fill` first turned true with the roster ALREADY FULL — never in time. The user reached
     his final two picks with D/ST and K empty and was recommended a backup QB and five tight ends:
     the exact illegal-roster ending the constraint exists to prevent.

  2. ⛔ A FILLED FLEX SEAT IS NOT CAPACITY. The bench-depth discount hardened on `held >= capacity`,
     where `capacity` summed every flex seat the position was eligible for — including one already
     filled by somebody else. Holding one TE with an RB in the flex read as "still has room", so a
     backup TE kept 50% of its VOR against a bench RB's 15%: a 3.3x boost for a player no lineup
     could start, which is why that draft's depth phase came back tight ends.

⚠️ BOTH SHIP ON THE WEBSITE TOO — `frontend/lib/draft-optimizer.ts` carried the identical lines, and
the parity harness held the two engines in lock-step INCLUDING the defects. `_optimizer_parity` pins
that they moved together; this file pins that they moved to the right place. Neither file is
sufficient alone: parity would be satisfied by two engines that are identically wrong.

⛔ ANCHORED IN ITS OWN CLAUSES (E9.60) — nothing here is bolted onto an older story's guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.services.draft_assistant import engine_row
from quant_sports_intel_models.fantasy_engine.draft import (
    SURPLUS_BASE,
    SURPLUS_CAP,
    SURPLUS_OVER,
    recommend,
)
from quant_sports_intel_models.fantasy_engine.league_config import (
    RESERVE_SLOT_NAMES,
    LeagueConfig,
    draftable_slot_count,
)

_FIXTURES = Path(__file__).parent / "fixtures"
_SOURCE = json.loads((_FIXTURES / "nf_c_lda_1_optimizer_parity_input.json").read_text())

#: The league from the live draft the screenshots came from: 9 starters + 6 bench, plus 2 IR spots.
_LIVE_ROSTER = [
    {"name": "QB", "count": 1, "eligible": ["QB"], "bench": False},
    {"name": "RB", "count": 2, "eligible": ["RB"], "bench": False},
    {"name": "WR", "count": 2, "eligible": ["WR"], "bench": False},
    {"name": "TE", "count": 1, "eligible": ["TE"], "bench": False},
    {"name": "FLEX", "count": 1, "eligible": ["RB", "WR", "TE"], "bench": False},
    {"name": "DST", "count": 1, "eligible": ["DST"], "bench": False},
    {"name": "K", "count": 1, "eligible": ["K"], "bench": False},
    {"name": "BN", "count": 6, "eligible": [], "bench": True},
    {"name": "IR", "count": 2, "eligible": [], "bench": True},
]


def _config(roster: list[dict]) -> LeagueConfig:
    return LeagueConfig.from_dict({**_SOURCE["config"], "roster": roster})


def _board() -> list[dict]:
    return [engine_row(r, _SOURCE["replacement"]) for r in _SOURCE["board"]]


def _fill(board: list[dict], wanted: list[str]) -> list[str]:
    """Best available at each requested position, in order — a plausible roster, not a synthetic one."""
    out, used = [], set()
    for pos in wanted:
        for row in sorted(board, key=lambda r: -(r.get("league_points") or 0)):
            pid = str(row["player_id"])
            if pid in used or row.get("position") != pos:
                continue
            used.add(pid)
            out.append(pid)
            break
    assert len(out) == len(wanted), f"the board could not fill {wanted}"
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. An IR spot is not a pick
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_reserve_slots_are_excluded_from_the_draftable_count():
    total = sum(s.count for s in _config(_LIVE_ROSTER).roster)
    draftable = draftable_slot_count(_config(_LIVE_ROSTER).roster)
    # ⚠️ NON-VACUITY: the two must actually DIFFER on this roster, or every clause below would pass
    # against an unchanged implementation (NF1.7(a)).
    assert total == 17 and draftable == 15, (total, draftable)


def test_every_adapter_emits_reserve_slots_under_a_name_the_rule_recognises():
    """⭐ THE RULE IS NAME-KEYED, so it is only as good as the names the adapters actually produce —
    and a name-keyed rule fails SILENTLY where the registry is incomplete (INC-38). Read the real
    slot maps rather than restating them."""
    from app.backend.services.platform_import import espn, sleeper, yahoo

    emitted = {
        name
        for mapping in (espn.ROSTER_SLOT_MAP, sleeper.ROSTER_SLOT_MAP, yahoo.ROSTER_SLOT_MAP)
        for name, _elig, bench in mapping.values()
        if bench
    }
    assert emitted, "no bench-tier slot names found — the maps were read wrong"
    reserve = {n for n in emitted if n.upper() != "BN"}
    assert reserve, "no reserve-tier slot names found; this guard would prove nothing"
    unrecognised = {n for n in reserve if n.upper() not in RESERVE_SLOT_NAMES}
    assert not unrecognised, (
        f"{sorted(unrecognised)} are reserve slots no pick can reach, but "
        f"RESERVE_SLOT_NAMES={sorted(RESERVE_SLOT_NAMES)} does not list them, so they would be "
        "counted as draftable and delay the reserve constraint"
    )


def test_an_unknown_slot_stays_draftable_so_the_constraint_can_only_fire_late_never_early():
    """⚠️ THE ERROR DIRECTION IS DELIBERATE. Over-counting delays a constraint that is inert while
    there is slack; under-counting fires it EARLY and forces K/DST on a user with picks to spare,
    distorting normal drafting — which the constraint explicitly must not do."""
    roster = _LIVE_ROSTER + [{"name": "SLOT_99", "count": 1, "eligible": [], "bench": True}]
    assert draftable_slot_count(_config(roster).roster) == 16


def test_the_reserve_constraint_fires_in_time_with_dst_and_k_still_open():
    """⭐ THE LIVE FAILURE, END TO END. 13 of 15 picks made, both mandatory slots empty: the only
    correct advice is a D/ST or a K, and before the fix the panel showed a backup QB and five TEs."""
    board = _board()
    mine = _fill(board, ["QB", "RB", "RB", "WR", "WR", "TE", "RB", "RB", "WR", "WR", "RB", "WR", "TE"])
    assert len(mine) == 13
    recs = recommend(board, config=_config(_LIVE_ROSTER), drafted_ids=mine, my_player_ids=mine, top_n=6)

    assert recs, "the engine returned nothing"
    assert all(r.must_fill for r in recs), (
        "the reserve constraint did not bind with 2 picks left and 2 mandatory slots open: "
        + ", ".join(f"{r.position} {r.player_name} must_fill={r.must_fill}" for r in recs)
    )
    assert {r.position for r in recs} <= {"DST", "K"}, (
        "a player who cannot fill an open mandatory slot was recommended with no picks to spare: "
        + ", ".join(f"{r.position} {r.player_name}" for r in recs)
    )


def test_the_constraint_stays_inert_while_there_is_genuine_slack():
    """The other side of the same property — a constraint that always fires would be no better than
    one that never does, and would drag K/DST into the middle rounds."""
    board = _board()
    mine = _fill(board, ["QB", "RB", "RB", "WR", "WR", "TE", "RB"])  # 7 of 15, 8 picks left
    recs = recommend(board, config=_config(_LIVE_ROSTER), drafted_ids=mine, my_player_ids=mine, top_n=8)
    assert not any(r.must_fill for r in recs), "the constraint bound with 8 picks left for 2 slots"
    assert not any(r.position in ("DST", "K") for r in recs), "K/DST surfaced in the middle rounds"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. A filled flex seat is not capacity
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def depth_recs():
    """The screenshot-2 roster: QB1 RB3 WR2 TE1, the flex already filled by an RB, 8 picks left.
    Every recommendation here is bench depth."""
    board = _board()
    mine = _fill(board, ["QB", "RB", "RB", "WR", "WR", "TE", "RB"])
    # Only my own picks are off the board, deliberately: the question is how the engine RANKS bench
    # depth across positions, and thinning the pool first would decide the answer by which players
    # happened to survive rather than by the rule under test.
    return recommend(board, config=_config(_LIVE_ROSTER), drafted_ids=mine,
                     my_player_ids=mine, top_n=25)


def test_the_depth_scenario_actually_reaches_bench_depth(depth_recs):
    """⚠️ NON-VACUITY: the clauses below say nothing unless these rows are genuinely level-0 picks
    at more than one position."""
    assert len(depth_recs) >= 15
    assert all(r.need_level == 0 for r in depth_recs), "this state is not the depth phase"
    assert len({r.position for r in depth_recs}) >= 3, "too few positions to compare discounts"


def test_bench_depth_is_discounted_identically_across_positions(depth_recs):
    """⭐ THE DEFECT ITSELF. A bench TE and a bench RB fill the same number of open slots — none —
    so they must be discounted the same. The old `capacity` said otherwise only because it counted
    a flex seat an RB was already sitting in."""
    # A bye-week stack carries its own penalty, so only clean rows isolate the surplus discount.
    clean = [r for r in depth_recs if r.vor > 0 and r.bye_conflict == 0]
    kept: dict[str, list[float]] = {}
    for r in clean:
        kept.setdefault(r.position, []).append(r.score / r.vor)
    assert len(kept) >= 2, f"only one position produced a clean positive-VOR bench pick: {list(kept)}"

    flat = [v for vs in kept.values() for v in vs]
    # Tolerance is the engine's own 0.1 output rounding carried through the smallest VOR in the set.
    # Doubled because the two rows furthest apart may have rounded in OPPOSITE directions.
    tol = 2 * 0.05 / min(r.vor for r in clean)
    assert max(flat) - min(flat) <= tol, (
        "positions keep different fractions of their VOR as bench depth — a position-dependent "
        f"discount is back: { {p: [round(v, 4) for v in vs] for p, vs in kept.items()} }"
    )
    expected = 1.0 - min(SURPLUS_CAP, SURPLUS_BASE + SURPLUS_OVER)
    assert abs(sum(flat) / len(flat) - expected) <= tol, (
        f"bench depth keeps {sum(flat) / len(flat):.4f} of its VOR, not the {expected:.4f} the "
        "constants describe"
    )


def test_bench_depth_ranks_by_player_value(depth_recs):
    """Once every candidate is bench depth, the ordering is the board's own currency. Before the fix
    a backup TE outranked a bench RB worth 80 more VOR."""
    positive = [r for r in depth_recs if r.vor > 0 and r.bye_conflict == 0]
    assert len(positive) >= 8, "too few clean rows to check the ordering"
    vors = [r.vor for r in positive]
    assert vors == sorted(vors, reverse=True), (
        "bench depth is not ordered by VOR: "
        + ", ".join(f"{r.position} {r.player_name} vor={r.vor:.1f}" for r in positive[:8])
    )


def test_a_second_tight_end_no_longer_outranks_clearly_better_bench_backs(depth_recs):
    """The user-visible symptom, stated as the property that failed: with the flex filled by an RB,
    a backup TE must not lead a bench RB carrying materially more value."""
    # A bye stack carries its own penalty, so comparing across one would test the wrong rule.
    best_te = next((r for r in depth_recs if r.position == "TE" and r.bye_conflict == 0), None)
    better_rbs = [r for r in depth_recs if r.position == "RB" and r.bye_conflict == 0
                  and best_te is not None and r.vor > best_te.vor + 20]
    assert best_te is not None and better_rbs, "the fixture does not pose the question"
    assert all(r.score > best_te.score for r in better_rbs), (
        f"TE {best_te.player_name} (vor {best_te.vor:.1f}, score {best_te.score:.1f}) outranks bench backs "
        "worth more: " + ", ".join(f"{r.player_name} vor={r.vor:.1f} score={r.score:.1f}" for r in better_rbs)
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. One rule, three owners
# ══════════════════════════════════════════════════════════════════════════════════════════════
_REPO = Path(__file__).resolve().parents[2]

#: Every file that computes "how many picks do I have left". THREE separate implementations of the
#: reserve constraint exist — the Python engine, the TS engine, and the mock-draft simulator's own
#: CPU logic — and all three carried the defect. This is the repo's recurring one-logical-rule-many-
#: owners shape (INC-30 crontab, INC-36 concurrency, INC-38 per-caller flags), so the registry is
#: pinned rather than trusted: a FOURTH copy must fail here rather than ship silently.
_PICK_COUNT_OWNERS = {
    "quant_sports_intel_models/fantasy_engine/draft.py": "draftable_slot_count(config.roster)",
    "frontend/lib/draft-optimizer.ts": "draftableSlotCount(config.roster)",
    "frontend/lib/mock-draft.ts": "draftableSlotCount(config.roster)",
}

#: The pre-fix expression, in both languages. Its ABSENCE is the property.
_RAW_TOTALS = (
    "sum(s.count for s in config.roster)",
    "config.roster.reduce((a, s) => a + s.count, 0)",
)


def _strip_comments(src: str, ts: bool) -> str:
    """⚠️ A COMMENT MUST NOT SATISFY A SOURCE GUARD (INC-38) — every file here explains the rule in
    prose that quotes the very expression being banned. ⛔ And the line-comment pattern must not eat
    a URL: `//` is matched only where it is NOT preceded by a colon (the NF-C-LDA-1 stripper bug)."""
    import re

    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?<!:)//[^\n]*", "", src) if ts else re.sub(r"(?<!:)#[^\n]*", "", src)


def test_every_owner_of_the_pick_count_goes_through_the_shared_rule():
    checked = 0
    for rel, expected in _PICK_COUNT_OWNERS.items():
        path = _REPO / rel
        assert path.exists(), f"{rel} moved — this registry is now measuring nothing"
        src = _strip_comments(path.read_text(), ts=rel.endswith(".ts"))
        assert expected in src, f"{rel} no longer computes its pick count via the shared rule"
        for raw in _RAW_TOTALS:
            assert raw not in src, (
                f"{rel} counts EVERY roster slot as a pick ({raw!r}) — an IR/taxi spot is depth no "
                "pick can reach, so the reserve constraint fires that many picks late"
            )
        checked += 1
    assert checked == len(_PICK_COUNT_OWNERS) == 3, "the registry shrank"


#: ⚠️ KNOWN, MEASURED, AND DELIBERATELY UNCHANGED HERE — the AUCTION reserve asks the same question
#: ("how many players does a team acquire?") and answers it the same wrong way: an IR spot cannot be
#: bought at auction, so counting it over-reserves `n_teams x IR x min_bid`. Measured on the default
#: 12-team/$200 roster: reserve $216 against $180, understating every player's dollar surplus by
#: 1.62%. It is NOT fixed in this change because correcting it re-prices every published auction
#: value and needs `build_auction_vectors.py` re-run and the artifacts republished — a separate
#: story, not a ride-along. Listed so the sweep below stays exhaustive and this cannot be forgotten.
_KNOWN_DEFERRED = {"frontend/lib/auction-optimizer.ts"}


def test_no_further_implementation_has_appeared():
    """⭐ THE REGISTRY'S OWN EXHAUSTIVENESS (INC-38). Pinning three files says nothing if a fourth
    can be added beside them; this sweeps the whole TS library and the engine package instead — and
    it earned its keep on the first run, catching the auction twin above."""
    candidates = sorted(
        [p for p in (_REPO / "frontend/lib").glob("*.ts")]
        + [p for p in (_REPO / "quant_sports_intel_models/fantasy_engine").glob("*.py")]
    )
    assert len(candidates) > 10, "the sweep found almost nothing — it would prove little"
    offenders = set()
    for path in candidates:
        src = _strip_comments(path.read_text(), ts=path.suffix == ".ts")
        if any(raw in src for raw in _RAW_TOTALS):
            offenders.add(str(path.relative_to(_REPO)))
    assert offenders <= _KNOWN_DEFERRED, (
        f"{sorted(offenders - _KNOWN_DEFERRED)} count EVERY roster slot as an acquirable spot; "
        "route them through draftable_slot_count / draftableSlotCount"
    )
    # ⚠️ …and the deferral must stay HONEST: an entry that has been fixed (or deleted) must leave
    # this list, or the exclusion silently grows into a place a real regression can hide.
    assert offenders == _KNOWN_DEFERRED, (
        f"{sorted(_KNOWN_DEFERRED - offenders)} no longer needs deferring — drop it from "
        "_KNOWN_DEFERRED so the sweep keeps its teeth"
    )


def test_the_comment_stripper_works_in_both_directions():
    """⚠️ A SOURCE GUARD IS ONLY AS GOOD AS ITS STRIPPER, and this one can fail either way.

    Too weak and the prose explaining the rule SATISFIES it (INC-38: a comment cannot be allowed to
    stand in for code). Too greedy and it eats a URL — a naive `//[^\n]*` turns
    `"https://api.credencesports.com"` into `"https:` and the guard silently measures a truncated
    file, which is a defect this very story shipped once and had to fix.
    """
    banned = _RAW_TOTALS[1]
    assert banned not in _strip_comments(f"// was {banned}\nconst x = 1\n", ts=True)
    assert banned not in _strip_comments(f"/* was {banned} */\nconst x = 1\n", ts=True)
    assert banned not in _strip_comments(f"# was {banned}\nx = 1\n", ts=False)
    # …but real code is kept, or every clause above passes on an empty string.
    assert banned in _strip_comments(f"const t = {banned}\n", ts=True)
    # …and a URL survives intact.
    kept = _strip_comments('const API = "https://api.credencesports.com" // note\n', ts=True)
    assert "https://api.credencesports.com" in kept, kept
