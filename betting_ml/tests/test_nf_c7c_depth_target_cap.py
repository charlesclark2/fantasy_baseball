"""NF-C7c — a depth target is a CAP as well as a floor.

NF-C7 shipped the target as a FLOOR only: a position you were short of got promoted, and one you
had already satisfied was left neutral. Users read the control as a CAP — which is what its label
says ("how many of each position you want on your roster IN TOTAL") — and the measured consequence,
reported from a live mock draft, was that setting `QB: 1` while holding one quarterback changed the
panel by NOTHING: five of six late-round suggestions stayed backup QBs.

⚠️ THE UNDERLYING OVER-VALUATION IS NOT FIXED HERE AND MUST NOT BE CLAIMED AS FIXED. A bench
candidate at a position where you hold exactly one starter and no backup displaces NOBODY, so
`displaced_rate` returns 0 and he is credited with his FULL weekly rate, while a marginal add at a
deep position is credited only with the delta. That is why quarterbacks swept those rounds, and with
QB capped the same panel fills with TIGHT ENDS — the identical mechanism one position over. The cap
gives the user the control they asked for; the valuation fix is a separate, measured change.

The scenario below is the REAL one from the report, rebuilt against the REAL 2026 board.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_sports_intel_models.fantasy_engine.draft import (
    DEPTH_NEUTRAL,
    DEPTH_SATISFIED,
    DEPTH_SHORT,
    recommend,
)
from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

_FIXTURE = Path(__file__).parent / "fixtures" / "nf_c_lda_1_optimizer_parity_input.json"

#: The roster on screen when this was reported — round 12 of 15, every starter filled, K and D/ST
#: still open. Rebuilt by NAME against the shipped board rather than by id, so it stays readable.
REPORTED_ROSTER = [
    "Josh Allen", "Christian McCaffrey", "Chase Brown", "Carnell Tate", "Marvin Harrison Jr.",
    "Travis Kelce", "Kyren Williams", "Jaylen Warren", "Josh Downs", "Quentin Johnston",
    "Chris Godwin Jr.", "Brian Robinson Jr.",
]


@pytest.fixture(scope="module")
def source() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.fixture(scope="module")
def engine_rows(source) -> list[dict]:
    repl = source["replacement"]
    return [
        {
            "player_id": str(p["id"]), "position": p["pos"], "player_name": p["name"],
            "team_id": p.get("team"), "bye": p.get("bye"), "is_rookie": p.get("rookie"),
            "league_points": p.get("pts"), "vor": p.get("vor"),
            "replacement": repl.get(p["pos"]), "games": p.get("g"),
            "positional_rank": p.get("posRank"), "overall_rank": p.get("ovrRank"),
            "vor_p10": p.get("vorP10"), "vor_p90": p.get("vorP90"),
            "adp": p.get("adp"), "low_pred": p.get("lowPred"),
        }
        for p in source["board"]
    ]


@pytest.fixture(scope="module")
def config(source):
    return LeagueConfig.from_dict(source["config"])


@pytest.fixture(scope="module")
def reported_state(source, engine_rows):
    by_name = {p["name"]: str(p["id"]) for p in source["board"]}
    mine = [by_name[n] for n in REPORTED_ROSTER if n in by_name]
    assert len(mine) == len(REPORTED_ROSTER), "the reported roster no longer resolves on this board"
    ranked = sorted(source["board"], key=lambda p: p.get("ovrRank") or 9999)
    drafted = [str(p["id"]) for p in ranked[:141]] + mine
    return {"drafted_ids": drafted, "my_player_ids": mine}


def _panel(engine_rows, config, state, targets, top_n=6):
    return recommend(engine_rows, config=config, top_n=top_n, depth_targets=targets, **state)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The reported defect
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_reported_panel_is_backup_quarterbacks_without_a_target(engine_rows, config,
                                                                    reported_state):
    """The starting condition — asserted so the fix below is not measured against a moving target.

    ⚠️ Without this, "the cap removed the QBs" could pass on a panel that never had any.
    """
    panel = _panel(engine_rows, config, reported_state, None)
    qbs = [r for r in panel if r.position == "QB"]
    assert len(qbs) >= 3, (
        f"the reported over-supply of backup QBs no longer reproduces "
        f"({[r.position for r in panel]}) — re-derive the scenario before trusting the fix below"
    )


def test_a_satisfied_target_removes_that_position_from_the_panel(engine_rows, config,
                                                                 reported_state):
    """The user's actual complaint: `QB: 1` while holding one QB must stop suggesting QBs."""
    panel = _panel(engine_rows, config, reported_state, {"QB": 1})
    assert not [r for r in panel if r.position == "QB"], (
        f"a satisfied QB target still left quarterbacks in the panel: "
        f"{[(r.player_name, r.position) for r in panel]}"
    )


def test_the_demotion_is_stated_on_the_row(engine_rows, config, reported_state):
    """A demotion the user cannot see reads as the tool ignoring good players for no reason.

    That is precisely how the floor-only version was experienced — a target was set, nothing
    changed, and there was nothing to point at.
    """
    panel = _panel(engine_rows, config, reported_state, {"QB": 1}, top_n=200)
    demoted = [r for r in panel if r.position == "QB" and r.depth_tier == DEPTH_SATISFIED]
    assert demoted, "no QB was demoted — the clause below would be vacuous"
    assert any("you asked for 1 QB and have 1" in r.rationale for r in demoted), (
        f"the demotion is invisible on the row: {demoted[0].rationale!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE LOAD-BEARING HALF: a target on ONE position must not move the others
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_position_with_no_target_is_left_neutral(engine_rows, config, reported_state):
    """Three states, not two — and the middle one is where a two-state implementation breaks.

    Folding "no target" into "satisfied" would demote every position the user never mentioned the
    moment they set a target on ONE, so naming a QB target would quietly push down every running
    back on the board. That is the opposite of expressing a preference.
    """
    base = _panel(engine_rows, config, reported_state, None, top_n=200)
    with_qb = _panel(engine_rows, config, reported_state, {"QB": 1}, top_n=200)

    # ⚠️ THE ASSERTION IS "NEVER WORSE", NOT "IDENTICAL", and the difference is a real property of
    # the mechanism rather than a weakened bar. The bench re-rank redistributes the cohort's own
    # order values among its members, so demoting the QBs necessarily hands the higher slots to
    # somebody — a non-QB inside the cohort legitimately moves UP past one outside it. What must
    # never happen is a non-QB moving DOWN: that is what "no target" being read as "satisfied"
    # would look like, and it is exactly what this clause exists to catch.
    before = {r.player_id: i for i, r in enumerate(base) if r.position != "QB"}
    after = {r.player_id: i for i, r in enumerate(with_qb) if r.position != "QB"}
    shared = set(before) & set(after)
    assert len(shared) >= 20, f"only {len(shared)} comparable non-QB rows — too few to prove much"
    demoted = {pid for pid in shared if after[pid] > before[pid]}
    assert not demoted, (
        f"{len(demoted)} candidate(s) at positions with NO target were pushed DOWN by a QB target — "
        f"the neutral tier is being read as satisfied"
    )
    assert all(r.depth_tier == DEPTH_NEUTRAL for r in with_qb if r.position != "QB")

    # ⚠️ A STRONGER CLAIM WAS TRIED AND MEASURED FALSE, and it is recorded rather than quietly
    # dropped: "the untargeted candidates keep their exact order among themselves" FAILS, because
    # the re-rank only redistributes order values WITHIN its top-40 cohort. A cohort member that
    # gains a freed slot legitimately overtakes a non-cohort candidate it previously sat behind, so
    # the sequence changes while nobody moves DOWN. Both facts are consistent, and "never worse" is
    # the one that discriminates a working neutral tier from a broken one.


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The guarantee NF-C7 shipped, re-asserted against the CAP
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_cap_can_never_starve_the_reserve_constraint(engine_rows, config, source):
    """A preference must never walk the user into an illegal roster — now from the other direction.

    NF-C7 proved a FLOOR cannot outrank a required slot. A CAP is the mirror risk: it must not push a
    position DOWN so far that a slot the lineup requires goes unfilled.
    """
    # ⚠️ A SKILL-ONLY ROSTER, DELIBERATELY. The first cut of this test drafted the top 13 players
    # OUTRIGHT, which happens to include a kicker and a defence, so nothing was ever `must_fill` and
    # the clause below never ran — it passed on NOTHING, and the RED proof caught it (NF1.7(a)).
    # Filling only skill positions leaves a required slot genuinely open, and the assertion is now
    # unconditional so it cannot silently go vacuous again.
    ranked = sorted(source["board"], key=lambda p: p.get("ovrRank") or 9999)
    skill = [p for p in ranked if p["pos"] in ("QB", "RB", "WR", "TE")]
    mine = [str(p["id"]) for p in skill[:13]]
    drafted = [str(p["id"]) for p in ranked[:160]] + mine
    panel = recommend(engine_rows, config=config, drafted_ids=drafted, my_player_ids=mine,
                      top_n=40, depth_targets={p: 1 for p in ("QB", "RB", "WR", "TE", "K", "DST")})
    assert panel, "fixture produced nothing — the assertion would be vacuous"
    must_fill = [r for r in panel if r.must_fill]
    assert must_fill, (
        "this state reaches no must_fill row, so it cannot test the reserve constraint at all — "
        "the fixture, not the engine, is what needs fixing"
    )
    assert panel[0].must_fill, (
        "a depth-target CAP outranked a slot the lineup REQUIRES — a preference has walked the "
        "user toward an illegal roster"
    )


def test_a_must_fill_row_can_never_carry_a_depth_TIER_at_all(engine_rows, config, source):
    """⭐ WHY THE RESERVE CONSTRAINT IS SAFE BY CONSTRUCTION, NOT BY ORDERING.

    The obvious guard here is "a depth tier must never sort above `must_fill`". Trying to break the
    engine that way and watching nothing happen is what surfaced the real reason: `must_fill` is
    `must_fill_now and level > 0`, while a depth tier is only ever assigned at `level == 0`. The two
    are DISJOINT — a row can carry one or the other, never both — so no arrangement of the sort keys
    can let a preference outrank a required slot.

    Measured, not asserted from the armchair: in a reserve-binding state EVERY candidate is a K or a
    D/ST filling an open slot, so every row is level > 0 and every tier is neutral.

    This invariant is the load-bearing statement, and it is checked across many states rather than
    one — an ordering test could only ever cover the arrangement it happened to construct.
    """
    ranked = sorted(source["board"], key=lambda p: p.get("ovrRank") or 9999)
    skill = [p for p in ranked if p["pos"] in ("QB", "RB", "WR", "TE")]
    targets = {p: 2 for p in ("QB", "RB", "WR", "TE", "K", "DST")}
    checked = 0
    for roster_size in (6, 9, 11, 13, 14, 15):
        mine = [str(p["id"]) for p in skill[:roster_size]]
        drafted = [str(p["id"]) for p in ranked[:170]] + mine
        panel = recommend(engine_rows, config=config, drafted_ids=drafted, my_player_ids=mine,
                          top_n=60, depth_targets=targets)
        for r in panel:
            if r.must_fill:
                checked += 1
                assert r.depth_tier == DEPTH_NEUTRAL, (
                    f"{r.player_name} is must_fill AND carries depth tier {r.depth_tier} — the "
                    f"level-0 restriction has been lost and a preference can now reach a required slot"
                )
    assert checked >= 20, (
        f"only {checked} must_fill rows across every state — this invariant was checked on almost "
        f"nothing (the first version of this test passed on ZERO)"
    )


def test_a_cap_never_demotes_a_candidate_filling_an_open_starter_slot(engine_rows, config, source):
    """LEVEL 0 ONLY, from the cap side. A position with an OPEN starter slot is being asked for by
    the LINEUP; a preference must not speak there at all, in either direction."""
    ranked = sorted(source["board"], key=lambda p: p.get("ovrRank") or 9999)
    mine = [str(ranked[0]["id"])]
    drafted = [str(p["id"]) for p in ranked[:40]] + mine
    panel = recommend(engine_rows, config=config, drafted_ids=drafted, my_player_ids=mine,
                      top_n=60, depth_targets={"QB": 1, "RB": 1, "WR": 1, "TE": 1})
    fillers = [r for r in panel if r.need_level > 0]
    assert fillers, "no starter-slot fillers in the panel — the assertion would be vacuous"
    assert all(r.depth_tier == DEPTH_NEUTRAL for r in fillers), (
        "a depth target reached a candidate filling an open STARTER slot"
    )


def test_a_cap_never_reorders_the_kdst_deferral(engine_rows, config, source):
    """A kicker CAP must not lift a kicker above a real candidate, and must not sink one the
    reserve constraint has already promoted."""
    ranked = sorted(source["board"], key=lambda p: p.get("ovrRank") or 9999)
    mine = [str(p["id"]) for p in ranked[:6]]
    drafted = [str(p["id"]) for p in ranked[:80]] + mine
    panel = recommend(engine_rows, config=config, drafted_ids=drafted, my_player_ids=mine,
                      top_n=80, depth_targets={"K": 1, "DST": 1})
    non_deferred_after_deferred = False
    seen_deferred = False
    for r in panel:
        if r.deferred and not r.must_fill:
            seen_deferred = True
        elif seen_deferred and not r.must_fill:
            non_deferred_after_deferred = True
    assert not non_deferred_after_deferred, "a K/DST target broke the deferral ordering"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The tiers themselves
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_three_tiers_are_distinct_and_ordered():
    """Lower sorts first: short, then untargeted, then satisfied."""
    assert DEPTH_SHORT < DEPTH_NEUTRAL < DEPTH_SATISFIED
