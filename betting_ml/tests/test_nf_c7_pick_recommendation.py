"""NF-C7 — the bench INSURANCE valuation and the per-position DEPTH TARGETS.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHY THIS FILE EXISTS SEPARATELY FROM THE PARITY GUARD
═══════════════════════════════════════════════════════════════════════════════════════════════════
`test_nf_c_lda_1_optimizer_parity.py` proves the two engines AGREE. It cannot prove either is right:
the harness in NF-C-LDA-6 held byte-identical through both of its own defects, and PR #945's two
roster-counting bugs were agreed on by both engines before they were found. Parity is a drift guard,
not a correctness guard.

So this file asserts BEHAVIOUR, and its centrepiece is the one the story called load-bearing:

  ⭐⭐ A DEPTH TARGET CAN NEVER STARVE THE RESERVE CONSTRAINT. A user preference must never walk a
  drafter into an illegal roster — that is #945's bug returning wearing a feature's clothes.

⛔ ANCHORED IN ITS OWN CLAUSE (E9.60): everything here fails only for an NF-C7 property.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from app.backend.services.draft_assistant import engine_row
from quant_sports_intel_models.fantasy_engine import draft as D
from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

_INPUT = Path(__file__).parent / "fixtures" / "nf_c_lda_1_optimizer_parity_input.json"


@pytest.fixture(scope="module")
def board() -> tuple[list[dict], LeagueConfig]:
    """The REAL 2026 board in a real 12-team league — the same fixture the parity guard replays.

    ⚠️ A hand-built board cannot exercise this: the whole finding NF-C7 acts on ("positive VOR
    survives only at QB and TE late") is a property of the ACTUAL shape of each position's pool.
    """
    src = json.loads(_INPUT.read_text())
    rows = [engine_row(r, src["replacement"]) for r in src["board"]]
    return rows, LeagueConfig.from_dict(src["config"])


def _by_pos(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["position"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: -(r["league_points"] or 0))
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐⭐ THE LOAD-BEARING GUARD — a preference may never produce an illegal roster
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_depth_target_can_never_starve_the_reserve_constraint(board):
    """With every remaining pick spoken for by an open starter slot, a depth target changes NOTHING.

    ⭐ THE FIXTURE IS BUILT SO ONLY THIS CLAUSE CAN DECIDE THE ANSWER (NF-D17): the roster is one
    pick from full with a mandatory K and D/ST still open, and the target asks for four more of the
    positions the drafter ALREADY holds most of. If a depth target could reach the sort at all, the
    top recommendation would move off the required filler — so a green here is not compatible with
    the bug, which is what makes it a test rather than a restatement.
    """
    rows, cfg = board
    pos = _by_pos(rows)
    # 13 of 15 draftable spots used: 1 QB, 3 RB, 3 WR, 1 TE + 5 more skill bench. Open: K, DST.
    mine = [r["player_id"] for r in
            pos["QB"][:1] + pos["RB"][:4] + pos["WR"][:4] + pos["TE"][:2] + pos["RB"][4:6]]
    drafted = set(mine) | {r["player_id"] for r in rows[:80]}

    greedy = {"QB": 9, "RB": 9, "WR": 9, "TE": 9}
    without = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=8)
    withal = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                         depth_targets=greedy, top_n=8)

    assert without, "the fixture produced no recommendations — the guard would pass on nothing"
    assert without[0].must_fill, (
        "the fixture does not reach the reserve constraint, so this clause proves nothing about it "
        "— rebuild `mine` so every remaining pick is spoken for"
    )
    assert [r.player_id for r in withal] == [r.player_id for r in without], (
        "a DEPTH TARGET changed the ranking while the reserve constraint was binding — a user "
        "preference has been allowed to strand a mandatory starter slot (PR #945's defect, as a "
        "feature)"
    )
    assert all(r.need_level > 0 for r in withal[:1]), (
        "the top recommendation stopped being a required filler while the reserve constraint bound"
    )


def test_a_kicker_depth_target_can_never_lift_a_kicker_into_an_early_round(board):
    """The other half of the same guarantee: a target may not defeat the K/DST DEFERRAL either.

    Deferral is a separate SORT KEY, not a score penalty, so no bonus can cross it — this asserts
    that structural claim rather than trusting it.
    """
    rows, cfg = board
    pos = _by_pos(rows)
    # ⚠️ DEEP in the draft, deliberately. Mid-draft the skill bench out-scores a kicker anyway, so a
    # defeated deferral changes nothing there and the clause passes on a state that cannot decide it
    # — the RED proof caught exactly that. Deep, every real bench candidate is below replacement
    # (negative VOR ⇒ a negative order value) while a kicker's is positive, so an un-deferred K
    # WOULD out-rank them, and only the deferral stops it.
    # ⚠️ THE ROSTER ALREADY HOLDS A KICKER AND A DEFENCE, and that is load-bearing: with the K slot
    # still OPEN a kicker is a level-2 need-filler, `depth_short` is 0 by the level gate, and a break
    # that lets a target clear the deferral could not fire at all. The RED proof caught exactly that.
    mine = [r["player_id"] for r in
            pos["QB"][:1] + pos["RB"][:3] + pos["WR"][:3] + pos["TE"][:1]
            + pos["K"][:1] + pos["DST"][:1]]
    drafted = set(mine) | {r["player_id"] for r in rows[:190]}
    # ⚠️ A LARGE `top_n`. Deferred rows sort LAST, so a six- or twelve-slot panel contains no K/DST
    # at all and the ordering clause below has nothing to compare — it asserted on an empty list.
    # The whole ranking is needed to see the two kinds against each other.
    recs = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                       depth_targets={"K": 6, "DST": 6}, top_n=1000)
    assert recs, "no recommendations — the clause would pass on nothing"
    assert not recs[0].must_fill, "the fixture accidentally binds the reserve constraint"
    assert recs[0].position not in ("K", "DST"), (
        "a K/DST depth target lifted a low-predictability position to the top of the panel"
    )
    kdst = [i for i, r in enumerate(recs) if r.position in ("K", "DST")]
    real = [i for i, r in enumerate(recs) if r.position not in ("K", "DST")]
    assert kdst and real, (
        "the panel holds only one KIND of candidate, so the ordering below proves nothing — the "
        "fixture must reach a state where a kicker and a real candidate compete"
    )
    # The FLAG's own contract: a depth target must not be able to clear it. This is what the break
    # `deferred = low_pred and depth_short <= 0` flips.
    assert all(r.deferred for r in recs if r.position in ("K", "DST")), (
        "a K/DST depth target cleared the low-predictability DEFERRAL flag"
    )
    assert min(kdst) > max(real), (
        f"a K/DST outranked a real candidate with a kicker depth target set: "
        f"{[(r.position, r.order_value) for r in recs]}"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The depth target itself — it must ACT, and it must act only where it is meant to
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_depth_target_changes_which_bench_player_is_recommended(board):
    """The positive control. A guard suite that only proves a feature is HARMLESS is satisfied by a
    feature that does nothing at all (NF-D20: an inactive mechanism is not a passing one)."""
    rows, cfg = board
    pos = _by_pos(rows)
    # A roster whose QB and TE seats are FULL (so both are level 0 and a target can act on them)
    # and which is deep enough at RB/WR that the bench is where the next pick goes.
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:3] + pos["WR"][:3]]
    drafted = set(mine) | {r["player_id"] for r in rows[:100]}
    base = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=8)
    assert base and all(r.need_level == 0 for r in base[:1]), (
        "the fixture's next pick is not a bench pick, so a depth target could not act here"
    )
    tgt = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                      depth_targets={"QB": 2, "TE": 2}, top_n=8)
    assert [r.player_id for r in tgt] != [r.player_id for r in base], (
        "asking for a backup QB and TE changed nothing — the control the story exists to add is inert"
    )
    # ⭐ THE CONTROL MUST BE FELT, NOT MERELY APPLIED. The first cut of this feature was a weighted
    # bonus; it applied correctly, changed `score` by a fraction of a point, and moved NOTHING into
    # a six-slot panel. So the assertion is on the PANEL, not on an internal field.
    asked = {r.position for r in tgt[:6]} & {"QB", "TE"}
    assert asked, (
        f"the user asked for a backup QB and TE and neither reached the panel: "
        f"{[(r.position, r.player_name) for r in tgt[:6]]}"
    )


def test_a_depth_target_is_never_recorded_against_an_open_starter_slot(board):
    """`depth_short` is a BENCH quantity. A candidate filling an open starter slot must carry 0 —
    the lineup is already asking for him, and a rationale reading "you asked for 2 QBs" beside
    "fills your open QB starter" would be explaining a need with a preference."""
    rows, cfg = board
    pos = _by_pos(rows)
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:1]]
    drafted = set(mine) | {r["player_id"] for r in rows[:60]}
    recs = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                       depth_targets={"QB": 9, "RB": 9, "WR": 9, "TE": 9}, top_n=20)
    fillers = [r for r in recs if r.need_level > 0]
    assert fillers, "no need-fillers in the panel — the clause would pass on nothing"
    for r in fillers:
        assert r.depth_short == 0, (
            f"{r.position} {r.player_name} fills an open starter slot and still records a depth "
            f"shortfall of {r.depth_short}"
        )
        assert "You asked for" not in r.rationale, (
            f"a need-filler's reason quotes a depth target: {r.rationale!r}"
        )


def test_a_met_depth_target_pays_nothing(board):
    """`{QB: 1}` on a roster already holding a QB must be byte-identical to no target at all.

    An 'on' state alone cannot tell a working gate from one that always pays.
    """
    rows, cfg = board
    pos = _by_pos(rows)
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:3] + pos["WR"][:3]]
    drafted = set(mine) | {r["player_id"] for r in rows[:100]}
    base = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=8)
    met = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                      depth_targets={"QB": 1, "TE": 1}, top_n=8)
    assert [(r.player_id, r.score) for r in met] == [(r.player_id, r.score) for r in base]


def test_a_depth_target_never_lifts_a_bench_pick_over_an_open_starter_slot(board):
    """The story's ordering requirement — "below a real open starter slot, above generic depth" —
    asserted as ORDERING rather than as a weight, because that is how it is implemented.

    ⭐ THE FIXTURE MAKES ONLY THIS CLAUSE DECISIVE (NF-D17): the roster has an OPEN starter slot and
    a greedy target at a position whose seats are FULL, so if the tier could reach past the bench
    cohort at all, the panel's top row would move.
    """
    rows, cfg = board
    pos = _by_pos(rows)
    # QB + TE seats full, RB/WR seats still open ⇒ real fillers exist AND a target can act.
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:1]]
    drafted = set(mine) | {r["player_id"] for r in rows[:60]}
    base = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=10)
    greedy = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine,
                         depth_targets={"QB": 9, "TE": 9}, top_n=10)
    fillers = [r for r in base if r.need_level > 0]
    assert fillers, "the fixture has no open starter slot, so this clause proves nothing"
    assert base[0].need_level > 0, "the fixture's top pick is not a need-filler"
    assert greedy[0].need_level > 0, (
        f"a DEPTH TARGET lifted a bench pick ({greedy[0].position} {greedy[0].player_name}) above "
        "every open starter slot — a preference must never outrank a slot the lineup requires"
    )
    # …and it must not reorder the FILLERS among themselves either: the tier is bench-only.
    assert [r.player_id for r in greedy if r.need_level > 0] == [r.player_id for r in fillers]


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE CORRECTNESS ASSERTION ON THE RULE — parity is not correctness
# ═══════════════════════════════════════════════════════════════════════════════════════════════
#
# NF-C-LDA-6 measured what each bench rule actually PUTS ON THE BENCH over 120 drafts:
#
#     rule        QB    RB    WR    TE
#     oracle      35%   10%   32%   23%     ⚓ peeking, the target shape
#     insurance   21%   17%   38%   24%
#     incumbent   47%    0%    0%   53%     the retired rule
#     nihilist     0%    0%    2%   98%     ⚓ must lose
#
# The retired rule's bench is 47% backup QB / 53% backup TE with ZERO RBs and ZERO WRs, and its
# tight-end share sits nearer the NIHILIST's than the oracle's. So the shippable claim is
# DIRECTIONAL and checkable on a single real draft state without re-running the simulation.
_ORACLE_MIX = {"QB": 0.35, "RB": 0.10, "WR": 0.32, "TE": 0.23}
_NIHILIST_MIX = {"QB": 0.00, "RB": 0.00, "WR": 0.02, "TE": 0.98}
_MIX_POSITIONS = ("QB", "RB", "WR", "TE")


def _l1(a: dict[str, float], b: dict[str, float]) -> float:
    return sum(abs(a.get(p, 0.0) - b.get(p, 0.0)) for p in _MIX_POSITIONS)


def _drafted_bench_mix(arm: str, slots=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)) -> dict[str, float]:
    """The position mix of the BENCH of rosters this arm actually DRAFTS, from the study harness.

    ⚠️ IT HAS TO BE A REAL DRAFT. The obvious cheap version — take the bench candidates a single
    mid-draft state recommends — measures something else entirely, and measuring it proved the
    point: over the 41 committed parity states the RETIRED rule's mix came out 33/33/29/5, nothing
    like the 47/0/0/53 the study recorded for it. Those states' rosters are arbitrary subsets of the
    top of the board, not rosters a rule built, and the bench mix is a property of the WHOLE draft.
    Drafting reproduces the published incumbent mix to within a point (measured 45.8/0/0/54.2 here
    against the study's 47/0/0/53), which is what makes this comparison readable at all.
    """
    from quant_sports_intel_models.fantasy_engine import bench_valuation_study as study

    rows, cfg, _ = study.load_board()
    counts: dict[str, float] = {}
    total = 0.0
    for slot in slots:
        roster = study.draft_one(rows, cfg, arm, slot, random.Random(f"room-0-{slot}"), None, None)
        for row in study._bench_of(roster, cfg):
            counts[row["position"]] = counts.get(row["position"], 0.0) + 1.0
            total += 1.0
    assert total, f"arm {arm!r} drafted no bench at all — the mix would be computed over nothing"
    return {p: counts.get(p, 0.0) / total for p in _MIX_POSITIONS}


@pytest.mark.slow
def test_the_bench_mix_moves_toward_the_oracle_and_away_from_the_nihilist():
    """⭐ THE CORRECTNESS ASSERTION. Parity proves the two engines AGREE; it cannot prove either is
    right — the NF-C-LDA-6 harness stayed byte-identical through both of its own defects, and PR
    #945's two roster bugs were agreed on by both engines before anyone found them.

    So the shipped rule is scored against the two ANCHORS the study scored it against, on the real
    2026 board, over twelve full drafted rosters. NF-C-LDA-6 measured, over 120 drafts:

        rule        QB    RB    WR    TE
        oracle      35%   10%   32%   23%     ⚓ peeking — the target shape
        insurance   21%   17%   38%   24%
        incumbent   47%    0%    0%   53%     the retired rule
        nihilist     0%    0%    2%   98%     ⚓ must lose

    The retired rule's bench is 47% backup QB and 53% backup TE with ZERO RBs and ZERO WRs, and its
    tight-end share sits nearer the NIHILIST's than the oracle's.

    ⚠️ DIRECTIONAL, NOT A THRESHOLD. A distance target would be a number reverse-engineered from the
    answer (E2.1-r). What the study established is an ORDERING, and that is what is asserted: the
    shipped rule must be CLOSER to the peeking oracle and FARTHER from the nihilist than the rule it
    replaced. ⚠️ Twelve drafts is a far smaller sample than the study's 120, so only the ordering is
    read here — the magnitudes live in `ablation_results/nf_c7_bench_integration.md`.
    """
    shipped = _drafted_bench_mix("insurance_sorted")
    legacy = _drafted_bench_mix("incumbent")

    assert shipped != legacy, (
        "the shipped rule and the retired rule bench the same positions, so this comparison cannot "
        "distinguish them and every clause below would pass on nothing"
    )
    assert _l1(shipped, _ORACLE_MIX) < _l1(legacy, _ORACLE_MIX), (
        f"the bench mix moved AWAY from the peeking oracle's — shipped={shipped} "
        f"legacy={legacy} oracle={_ORACLE_MIX}"
    )
    assert _l1(shipped, _NIHILIST_MIX) > _l1(legacy, _NIHILIST_MIX), (
        f"the bench mix moved TOWARD the nihilist's — shipped={shipped} legacy={legacy}"
    )
    assert shipped["TE"] < legacy["TE"], (
        "the retired rule's tight-end share was its closest resemblance to the nihilist, and it has "
        f"not come down: shipped TE={shipped['TE']:.3f} legacy TE={legacy['TE']:.3f}"
    )
    assert shipped["RB"] + shipped["WR"] > legacy["RB"] + legacy["WR"], (
        "the bench still holds no more running backs or wide receivers than the retired rule did — "
        "the live report NF-C-LDA-6 quantified ('WRs seemed to not even pop up') is unfixed"
    )


@pytest.mark.slow
def test_the_nihilist_anchor_still_loses_and_the_harness_can_see_a_difference():
    """⚓ The anchor that makes the clause above readable. A metric a NIHILIST wins selects nothing
    (NF-D11), so the arm registered to lose must actually be the farthest from the oracle."""
    shipped = _drafted_bench_mix("insurance_sorted")
    nihilist = _drafted_bench_mix("nihilist")
    assert _l1(nihilist, _ORACLE_MIX) > _l1(shipped, _ORACLE_MIX), (
        f"the nihilist ({nihilist}) is not farther from the oracle than the shipped rule "
        f"({shipped}) — the anchor is inactive and the comparison above proves nothing"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The insurance formula's own two corrections, each pinned by the case that produced it
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_bench_candidate_is_never_worth_his_whole_season(board):
    """The seat-count correction. Using the roster's CAPACITY at a position instead of the seats it
    actually OCCUPIES made a candidate who out-rated the single seated TE read as 'walks into a
    seat' and price at his ENTIRE projected season (George Kittle, 248 points of bench cover)."""
    rows, cfg = board
    pos = _by_pos(rows)
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:3] + pos["WR"][:3]]
    drafted = set(mine) | {r["player_id"] for r in rows[:100]}
    recs = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=60)
    bench = [r for r in recs if r.need_level == 0]
    assert bench, "no bench candidates — the clause would pass on nothing"
    for r in bench:
        assert r.seat_value < r.league_points, (
            f"{r.player_name} is valued at {r.seat_value} as BENCH COVER against a projected season "
            f"of {r.league_points} — the seat count is over-stated"
        )


def test_a_player_projected_for_almost_no_games_cannot_buy_a_bench_seat(board):
    """The availability correction. Without discounting the candidate's OWN availability, a bench
    value is `weeks x pts/g`, which EXPLODES as `g` falls: Bailey Zappe (g=0.8, 33.3 points ⇒ a
    41.6/game 'rate') priced at 394 points and was the top-ranked pick on the whole board."""
    rows, cfg = board
    pos = _by_pos(rows)
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:3] + pos["WR"][:3]]
    drafted = set(mine) | {r["player_id"] for r in rows[:100]}
    recs = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=200)
    bench = [r for r in recs if r.need_level == 0]
    fragile = [r for r in bench if 0 < (next(x for x in rows if x["player_id"] == r.player_id)
                                        ["games"] or 0) <= 4]
    assert fragile, "the board carries no sub-4-game bench candidate — the clause proves nothing"
    healthy_best = max((r.seat_value for r in bench
                        if (next(x for x in rows if x["player_id"] == r.player_id)["games"] or 0) >= 14),
                       default=0.0)
    assert healthy_best > 0, "no healthy bench candidate to compare against"
    for r in fragile:
        assert r.seat_value <= healthy_best, (
            f"{r.player_name}, projected for under 4 games, is worth more as bench cover "
            f"({r.seat_value}) than every candidate projected for a full season ({healthy_best})"
        )


def test_a_backup_sharing_his_starters_bye_is_worth_less_than_one_who_does_not():
    """A bye week the backup ALSO misses is the one week he certainly cannot cover. Before the
    availability correction it was the single most valuable week in the sum."""
    # ⚠️ The starter must have REAL absence risk (g < 17), or the same-bye backup is worth exactly
    # zero — correct, but then the clause is comparing a positive number against a structural 0 and
    # would pass even if the bye were ignored entirely.
    starter = {"player_id": "s", "position": "QB", "league_points": 300.0, "games": 14.0, "bye": 7}
    same = {"player_id": "a", "position": "QB", "league_points": 200.0, "games": 17.0, "bye": 7}
    diff = {"player_id": "b", "position": "QB", "league_points": 200.0, "games": 17.0, "bye": 9}
    same_v = D.bench_insurance_value(same, [starter], seats=1)
    diff_v = D.bench_insurance_value(diff, [starter], seats=1)
    assert diff_v > same_v > 0, (
        f"a backup on his starter's own bye ({same_v}) is not worth less than one who is not "
        f"({diff_v})"
    )


def test_a_candidate_who_walks_into_a_seat_displaces_the_weakest_seat_holder():
    """The branch the study's rule never took, pinned directly on the pure function.

    If I hold two running backs in two seats and a BETTER one falls to me, he does not appear from
    nowhere — he pushes my weaker starter onto the bench, so what he is worth is the gap over THAT
    man. The study's rule always asked "who is my best BENCH player at this position?", which is
    NOBODY when both seats are full, so it valued him at his entire projected season.

    ⭐ ASSERTED ON `displaced_rate` ITSELF because the branch is a pure function with a right answer,
    and a full-`recommend` fixture that happens to reach it is a fixture a later board change can
    quietly stop reaching (the RED proof found exactly that: breaking this branch left every
    engine-level clause green).
    """
    rates_desc = [12.0, 9.0]          # two seat-holders, no bench
    assert D.displaced_rate(rates_desc, seats=2, candidate_rate=15.0) == 9.0, (
        "a candidate who out-rates both seat-holders must displace the WEAKER of them"
    )
    assert D.displaced_rate(rates_desc, seats=2, candidate_rate=10.0) == 9.0, (
        "a candidate who out-rates one of two seat-holders still takes a seat, from the weaker"
    )
    # He is behind BOTH, so he only plays when one is out — and then he covers for whoever would
    # otherwise have filled in, which is nobody here.
    assert D.displaced_rate(rates_desc, seats=2, candidate_rate=5.0) == 0.0
    # …and with a bench player present, that is who he displaces.
    assert D.displaced_rate([12.0, 9.0, 6.0], seats=2, candidate_rate=5.0) == 6.0


def test_a_bench_candidate_worse_than_the_cover_i_already_have_is_worth_nothing():
    """Floored on the UPGRADE, not on the product: a negative insurance value would claim that
    holding him makes my lineup worse, which is false — I would simply never start him."""
    # ⚠️ THE HELD PLAYERS MUST HAVE REAL ABSENCE RISK. With `games=17` on both, the candidate is
    # third in line behind two men who are never out, so `expected_starts` is ~0 and the product is
    # `0 * negative == -0.0`, which equals 0.0 — the clause then passes with the floor DELETED. The
    # RED proof caught it; `games=14` gives him a real chance of being needed.
    starter = {"player_id": "s", "position": "RB", "league_points": 250.0, "games": 14.0, "bye": 7}
    cover = {"player_id": "c", "position": "RB", "league_points": 165.0, "games": 14.0, "bye": 9}
    worse = {"player_id": "w", "position": "RB", "league_points": 40.0, "games": 14.0, "bye": 5}
    assert D.expected_starts(worse, [starter, cover], 1) > 0.3, (
        "the fixture never needs him, so the floor below is untested"
    )
    assert D.bench_insurance_value(worse, [starter, cover], seats=1) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The PLACEMENT rule — a bench pick must not out-rank an unfilled starter slot
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def test_bench_depth_does_not_outrank_an_open_starter_slot_more_often_than_the_retired_rule(board):
    """⭐ THE REGRESSION THIS RULE EXISTS TO PREVENT, measured over all 41 committed draft states.

    An insurance value is points added to MY lineup; a need-filler's VOR is points over the
    FREELY-AVAILABLE alternative. Comparing them directly made bench depth outrank EVERY open-slot
    filler in 8 of the 23 states that have both — one preferring a bench RB (55.6) to filling an
    EMPTY QB1 (12.9). The retired rule did it in 1 of 8, by 0.3 points.
    """
    src = json.loads(_INPUT.read_text())
    rows = [engine_row(r, src["replacement"]) for r in src["board"]]
    cfg = LeagueConfig.from_dict(src["config"])
    comparable = outranked = 0
    for sc in src["scenarios"].values():
        recs = D.recommend(rows, config=cfg, drafted_ids=sc["drafted"], my_player_ids=sc["mine"],
                           depth_targets=sc.get("depthTargets"), top_n=200)
        if not any(r.need_level > 0 for r in recs) or not any(r.need_level == 0 for r in recs):
            continue
        comparable += 1
        if recs[0].need_level == 0 and not recs[0].deferred:
            outranked += 1
    assert comparable >= 15, f"only {comparable} states can decide this — the clause is too thin"
    assert outranked <= 2, (
        f"bench depth out-ranked every open-starter-slot filler in {outranked} of {comparable} "
        "draft states; the retired rule did it in 1 of 8. An empty starter slot scores ZERO every "
        "week — this is PR #945's illegal-roster ending arriving earlier in the draft."
    )


def test_the_bench_cohort_is_ordered_by_insurance_not_by_the_placement_term(board):
    """The other half: the placement rule must not undo the valuation. Within the bench cohort the
    order must be insurance-descending — that IS the NF-C7 change."""
    rows, cfg = board
    pos = _by_pos(rows)
    mine = [r["player_id"] for r in pos["QB"][:1] + pos["TE"][:1] + pos["RB"][:3] + pos["WR"][:3]]
    drafted = set(mine) | {r["player_id"] for r in rows[:100]}
    # ⚠️ WITHIN THE SHORTLIST. Only the top `BENCH_RERANK_SHORTLIST` candidates by the retired
    # ordering are re-ranked (see `BENCH_RERANK_SHORTLIST` — removing that bound turns the whole
    # rule into a measured NULL), so the claim is about the panel a user sees, not about all ~600
    # available players. `top_n=12` is comfortably inside the shortlist, because the returned list
    # is itself sorted by the same key the shortlist is taken on.
    panel = D.recommend(rows, config=cfg, drafted_ids=drafted, my_player_ids=mine, top_n=12)
    bench = [r for r in panel if r.need_level == 0 and not r.deferred]
    assert len(bench) >= 5, "too few bench candidates in the panel to establish an ordering"
    scores = [r.score for r in bench]
    assert scores == sorted(scores, reverse=True), (
        f"the bench cohort is not ordered by its insurance value: {scores[:8]}"
    )
    # …and the ordering must not simply BE the retired one, or this passes on a no-op.
    legacy_order = [r.player_id for r in sorted(bench, key=lambda r: (-r.order_value, r.player_id))]
    assert legacy_order != [r.player_id for r in bench] or len({r.order_value for r in bench}) == 1, (
        "the bench ordering is identical to the retired damped-VOR ordering — insurance is deciding "
        "nothing here, so the clause above passes on a no-op"
    )
