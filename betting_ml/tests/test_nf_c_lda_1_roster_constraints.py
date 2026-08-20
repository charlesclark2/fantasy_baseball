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
    # ⚠️ TWO, NOT THREE, SINCE NF-C7. This asked for three positions when a bench pick was ranked by
    # VOR, which surfaced backup QBs and TEs in every depth panel — the symptom NF-C-LDA-6 then
    # quantified (47% backup QB / 53% backup TE across 120 drafts, zero RBs and zero WRs). NF-C7
    # ranks a bench pick on how many weeks it would actually be started, so a top-25 depth panel is
    # now RB/WR, and requiring three positions would be requiring the defect back.
    assert len({r.position for r in depth_recs}) >= 2, "too few positions to compare"


def test_a_flex_seat_an_rb_is_sitting_in_is_not_capacity_for_a_tight_end():
    """⭐ THE DEFECT ITSELF, RE-ANCHORED ONTO THE NF-C7 IMPLEMENTATION (E9.60: re-anchor an existing
    property onto a new implementation; do not delete it and do not bolt a new story's requirement
    onto an old clause).

    The bug was in `open_starter_slots`: a user holding one TE with an RB already in the flex read as
    "TE capacity 2, held 1 ⇒ still has room", so a backup TE kept 50% of its VOR while a bench back
    kept 15% — a 3.3x boost for a player no lineup could ever start.

    The retired surplus constants that clause used to measure are gone. The MISCOUNT is not: NF-C7's
    bench valuation asks how many seats the position actually OCCUPIES, and getting that wrong the
    same way would credit a second tight end with covering a seat an RB is in. `OpenSlots.seated` is
    where the answer now lives, so that is what this asserts — the same question, one layer nearer
    the cause than a discount ratio was.
    """
    from quant_sports_intel_models.fantasy_engine.draft import (
        RosterRequirements, open_starter_slots, starter_seats_for,
    )

    cfg = _config(_LIVE_ROSTER)
    req = RosterRequirements.from_config(cfg)
    # QB1 RB3 WR2 TE1 — the screenshot-2 roster. The third RB is in the flex.
    open_slots = open_starter_slots(["QB", "RB", "RB", "WR", "WR", "TE", "RB"], req)

    assert open_slots.seated.get("TE") == 1, (
        f"a tight end is seated {open_slots.seated.get('TE')} times with an RB in the flex — the "
        "flex-capacity miscount is back, and a second TE would be credited with covering a seat he "
        "can never reach"
    )
    assert open_slots.seated.get("RB") == 3, (
        "the third running back is not counted as occupying the flex seat he is actually in"
    )
    # ⭐ AND THE TWO NUMBERS MUST DIFFER, or this clause is agreeing with the defect by accident:
    # `starter_seats_for` is the roster's CAPACITY at the position (2 for TE here), which is exactly
    # the wrong answer, and the bench valuation must not be reading it.
    assert starter_seats_for(req, "TE") == 2 and open_slots.seated["TE"] == 1, (
        "capacity and seated agree for TE in this fixture, so it cannot tell the two apart"
    )


def test_bench_depth_ranks_by_player_value(depth_recs):
    """Once every candidate is bench depth, the ordering is the board's own currency. Before the fix
    a backup TE outranked a bench RB worth 80 more VOR."""
    # ⚠️ WITHIN A POSITION SINCE NF-C7, and the narrowing is the point rather than a weakening.
    # ACROSS positions a bench pick is no longer ranked in VOR at all — it is ranked on how many
    # weeks you would actually start him, which is the whole NF-C7 change and is deliberately not
    # VOR-ordered. WITHIN a position the guarantee survives intact and is what the K31 inversion was
    # about: a worse player at a position can never out-rank a better one.
    positive = [r for r in depth_recs if r.vor > 0 and r.bye_conflict == 0]
    assert len(positive) >= 8, "too few clean rows to check the ordering"
    by_pos: dict[str, list] = {}
    for r in positive:
        by_pos.setdefault(r.position, []).append(r)
    assert any(len(v) >= 3 for v in by_pos.values()), (
        "no position has three clean rows, so a within-position ordering claim proves nothing"
    )
    for pos, rows in by_pos.items():
        vors = [r.vor for r in rows]
        assert vors == sorted(vors, reverse=True), (
            f"bench depth at {pos} is not ordered by VOR: "
            + ", ".join(f"{r.player_name} vor={r.vor:.1f}" for r in rows[:8])
        )


def test_a_second_tight_end_is_valued_against_one_seat_not_two(depth_recs):
    """The user-visible symptom, RE-ANCHORED (E9.60). It used to read "a backup TE must not lead a
    bench RB carrying materially more value", which was a statement about the VOR ordering NF-C7
    replaced — under the new rule a tight end you have no cover for can legitimately be worth more
    than a fourth running back, and that is the change, not a regression.

    What must still hold is the DEFECT's own signature: with the flex filled by a running back, a
    second tight end is covering ONE seat, and his value must be exactly what it would be if the
    flex did not exist at all.
    """
    from quant_sports_intel_models.fantasy_engine.draft import bench_insurance_value

    board = _board()
    mine_ids = _fill(board, ["QB", "RB", "RB", "WR", "WR", "TE", "RB"])
    by_id = {str(r["player_id"]): r for r in board}
    my_tes = [by_id[p] for p in mine_ids if by_id[p]["position"] == "TE"]
    # ⚠️ READ FROM THE WHOLE RANKING, not from `depth_recs`. Since NF-C7 a top-25 depth panel holds
    # no tight end at all (that IS the change), so pulling the candidate out of the panel would make
    # this clause pass on `None` — the vacuous shape it is written to avoid.
    full = recommend(board, config=_config(_LIVE_ROSTER), drafted_ids=mine_ids,
                     my_player_ids=mine_ids, top_n=600)
    best_te = next((r for r in full if r.position == "TE"), None)
    assert best_te is not None and len(my_tes) == 1, "the fixture does not pose the question"

    cand = by_id[best_te.player_id]
    one_seat = bench_insurance_value(cand, my_tes, 1)
    two_seats = bench_insurance_value(cand, my_tes, 2)
    assert one_seat != two_seats, (
        "the seat count makes no difference to this candidate, so the clause cannot detect the "
        "miscount it exists to catch"
    )
    assert abs(best_te.seat_value - round(one_seat, 1)) < 0.11, (
        f"TE {best_te.player_name} is valued at {best_te.seat_value} as bench cover, but covering "
        f"ONE seat is worth {one_seat:.1f} and covering TWO is worth {two_seats:.1f} — he is being "
        "credited with a flex seat a running back is sitting in"
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
