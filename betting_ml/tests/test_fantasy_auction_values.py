"""NF-C5 — the auction value model + the live budget/inflation math.

Three families here, and they answer different questions:

  1. THE GOLDEN VECTORS are the CROSS-LANGUAGE pin. `frontend/lib/auction-optimizer.ts` re-implements
     this arithmetic to recompute live in the browser, and `fantasy-auction-optimizer.spec.ts` runs
     the TS through the SAME file. Regenerating here and refusing any drift is what stops the
     committed vectors going stale relative to the Python — without that the TS could be pinned to a
     fossil and both sides would be green while disagreeing (the E9.61 two-implementations class).

  2. THE PROPERTIES are what actually has to be true of a bid — above all NEVER STRAND A SLOT, which
     is a correctness property rather than a preference and is therefore asserted exhaustively over
     a grid rather than at a couple of hand-picked points.

  3. THE FACE VALIDITY runs the real formula over a REALISTICALLY-SHAPED board, because every number
     in family 1 is scale-free arithmetic on a 7-row toy: it would be perfectly happy to price the
     best player in a $200 league at $1,228 (it does — see the vectors), and a reader has no way to
     tell from the vectors alone whether the model produces sane dollars. The conservation identity
     below is the check that it does.
"""
from __future__ import annotations

import json

import pytest

from quant_sports_intel_models.fantasy_engine import auction as A
from quant_sports_intel_models.fantasy_engine import build_auction_vectors as BV
from quant_sports_intel_models.fantasy_engine.league_config import (
    LeagueConfig,
    RosterSlot,
    ScoringRules,
)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The golden vectors — the pin the TS side reads
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_committed_vectors_are_what_this_engine_produces_today():
    """⭐ THE POINT OF THE WHOLE FILE. The TS auction lib is pinned to
    `fantasy_engine/auction_vectors.json`; if the Python moves and the file does not, the TS stays
    green against a fossil and the two implementations silently disagree. Regenerate in memory and
    demand byte equality, so a Python change MUST be accompanied by a regenerated file — at which
    point the TS spec is the thing that goes red, which is exactly the signal wanted.

    Fix on failure:
        uv run python -m quant_sports_intel_models.fantasy_engine.build_auction_vectors
    """
    assert BV.VECTORS_PATH.exists(), f"the golden vectors are missing at {BV.VECTORS_PATH}"
    assert BV.VECTORS_PATH.read_text() == BV.serialise(BV.build()), (
        "auction_vectors.json is stale — regenerate it (see the docstring) and re-run the TS "
        "auction spec, which is pinned to the same file"
    )


def test_the_vectors_exercise_every_binding_branch():
    """⚠️ ANTI-VACUITY. A fixture that only ever produced `binding == "affordability"` would let a
    max-bid implementation that IGNORED the valuation entirely pass every vector — the first cut of
    these vectors did exactly that, because the toy board's values dwarf every probe budget."""
    vectors = json.loads(BV.VECTORS_PATH.read_text())
    bindings = {c["binding"] for c in vectors["maxBids"]}
    assert bindings == {"value", "affordability", "no_slot", "roster_full"}, (
        f"the vectors no longer cover every binding constraint — got {sorted(bindings)}"
    )
    # ...and the inflation multiplier must move the answer in BOTH directions, or a TS that
    # ignored inflation would still pass.
    by_case = {c["case"]: c for c in vectors["maxBids"]}
    assert by_case["inflation_lifts_the_bid"]["maxBid"] > by_case["value_binds"]["maxBid"]
    assert by_case["deflation_lowers_the_bid"]["maxBid"] < by_case["value_binds"]["maxBid"]


def test_the_vectors_contain_a_pool_where_the_draftable_truncation_actually_binds():
    """⭐ ANTI-VACUITY FOR THE FIX THAT MATTERS MOST, and it is not obvious.

    Every large pool in the vectors has far more roster spots than the toy board has rows, so the
    draftable-set truncation is INACTIVE in all of them — a TS port that dropped the truncation
    entirely would reproduce every one of those vectors and still be wrong on any real board with
    more above-replacement players than roster spots (the shipped E2E fixture: 722 against 180,
    which opened the auction at 2.06x).

    So at least one pool must be small enough that the truncation changes the answer. Proved by
    computing the untruncated rate and demanding it DISAGREE, rather than by trusting the pool's
    dimensions to imply it.
    """
    vectors = json.loads(BV.VECTORS_PATH.read_text())
    board = vectors["board"]
    positives = [max(0.0, r["vor"] or 0.0) for r in board]

    discriminating = []
    for p in vectors["pools"]:
        spots = p["nTeams"] * p["rosterSpots"]
        if spots >= len(board) or p["pool"]["surplus"] == 0:
            continue  # truncation cannot bind, or there is no money to distribute
        truncated = sum(sorted(positives, reverse=True)[:spots])
        if truncated < sum(positives) - 1e-9:
            discriminating.append(p)

    assert discriminating, (
        "no vector pool distinguishes the draftable-set truncation from a whole-board sum — the "
        "TS side could drop it entirely and stay green"
    )
    # ...and confirm it moves a real, published number rather than a rounding artifact.
    p = discriminating[0]
    spots = p["nTeams"] * p["rosterSpots"]
    surplus = p["pool"]["surplus"]
    truncated_rate = surplus / sum(sorted(positives, reverse=True)[:spots])
    whole_rate = surplus / sum(positives)
    top = max(v["value"] for v in p["values"])
    assert top == A._round_half_up(1 + truncated_rate * max(positives))
    assert top != A._round_half_up(1 + whole_rate * max(positives)), (
        "the two denominators round to the same dollar here — pick a pool where they do not"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The pool and the values
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_pool_reserves_a_minimum_bid_for_every_roster_spot():
    pool = A.auction_pool(12, 16, 200)
    assert pool.total == 2400
    assert pool.reserve == 12 * 16  # every one of the 192 spots must cost at least $1
    assert pool.surplus == 2400 - 192
    assert pool.spots_total == 192


def test_a_budget_too_small_to_cover_its_own_minimums_yields_no_surplus():
    """A misconfiguration must degrade to "everybody costs the minimum", never to a NEGATIVE rate
    that would invert the board and make the best player the cheapest."""
    pool = A.auction_pool(12, 16, 10)
    assert pool.surplus == 0
    values = A.auction_values(
        [{"id": "stud", "vor": 150.0}, {"id": "scrub", "vor": 1.0}], pool
    )
    assert [v.value for v in values] == [1, 1]


@pytest.mark.parametrize("bad", [{"n_teams": 0}, {"roster_spots": 0}, {"budget": 0}])
def test_a_degenerate_pool_is_refused_rather_than_silently_computed(bad):
    kwargs = {"n_teams": 12, "roster_spots": 16, "budget": 200, **bad}
    with pytest.raises(ValueError):
        A.auction_pool(**kwargs)


def test_a_player_at_or_below_replacement_is_worth_exactly_the_minimum():
    """He is freely available, so there is no reason to bid a second dollar — and a NEGATIVE value
    would be nonsense at an auction, where the floor is the minimum bid."""
    pool = A.auction_pool(12, 16, 200)
    vals = {
        v.player_id: v
        for v in A.auction_values(
            [
                {"id": "good", "vor": 100.0},
                {"id": "at_repl", "vor": 0.0},
                {"id": "below", "vor": -80.0},
                {"id": "unprojected", "vor": None},
            ],
            pool,
        )
    }
    assert vals["good"].value > 1
    assert vals["at_repl"].value == 1
    assert vals["below"].value == 1
    assert vals["unprojected"].value == 1


def test_the_band_comes_back_ordered_even_when_the_interval_arrives_crossed():
    pool = A.auction_pool(12, 16, 200)
    (v,) = A.auction_values([{"id": "x", "vor": 20.0, "vorP10": 44.0, "vorP90": 6.0}], pool)
    assert v.low <= v.value or v.low <= v.high
    assert v.low <= v.high, "a crossed source interval rendered as a backwards $ band"


def test_a_board_with_no_interval_columns_gives_a_degenerate_band_not_a_wrong_one():
    pool = A.auction_pool(12, 16, 200)
    (v,) = A.auction_values([{"id": "x", "vor": 50.0}], pool)
    assert v.low == v.value == v.high


def test_the_band_is_the_players_own_interval_priced_at_the_league_rate():
    """⭐ THE RATE IS HELD FIXED ACROSS THE BAND. Re-deriving a rate from the p10 column would
    answer "what if EVERY player simultaneously landed at his 10th percentile" — a world where the
    money is unchanged, so the values barely move. The drafter's question is about ONE player."""
    pool = A.auction_pool(12, 16, 200)
    rows = [
        {"id": "a", "vor": 100.0, "vorP10": 50.0, "vorP90": 150.0},
        {"id": "b", "vor": 100.0, "vorP10": 50.0, "vorP90": 150.0},
    ]
    vals = A.auction_values(rows, pool)
    rate = pool.surplus / 200.0  # sum of the two vors
    assert vals[0].value == round(1 + rate * 100)
    assert vals[0].low == round(1 + rate * 50)
    assert vals[0].high == round(1 + rate * 150)


def test_an_asymmetric_projection_interval_survives_as_an_asymmetric_dollar_band():
    """The rookie/veteran bands are strongly skewed (NF1.7), and a band that got re-centred on the
    way into dollars would quietly delete exactly the information it exists to carry."""
    pool = A.auction_pool(12, 16, 200)
    (v,) = A.auction_values(
        [{"id": "skewed", "vor": 60.0, "vorP10": 55.0, "vorP90": 200.0}], pool
    )
    assert (v.high - v.value) > 4 * (v.value - v.low)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. THE NEVER-STRAND RULE — a correctness property, asserted over a grid
# ══════════════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("budget_remaining", [0, 1, 3, 9, 17, 40, 88, 200])
@pytest.mark.parametrize("open_slots", [1, 2, 3, 6, 9, 16])
@pytest.mark.parametrize("value", [1, 5, 40, 300])
def test_bidding_the_max_can_never_strand_a_remaining_roster_spot(
    budget_remaining, open_slots, value
):
    """⭐⭐ THE PROPERTY THE WHOLE OPTIMIZER EXISTS TO GUARANTEE. After paying `max_bid` for this
    player, whatever is left must still cover the minimum bid on every OTHER open spot. An empty
    starter slot scores zero on Sunday, so this is not a preference to be traded off.

    Asserted over a GRID rather than at a few points because the failure is an off-by-one at the
    boundary (`open_slots - 1` vs `open_slots`), which a hand-picked case is exactly the wrong
    instrument to find.

    ⚠️ THE GRID CONTAINS STATES THAT ARE **ALREADY** STRANDED ON ARRIVAL ($1 in hand with 2 spots
    to fill), which this rule cannot undo and must not be blamed for — reached only by bidding
    outside the tool, or by a league whose budget cannot cover its own roster. The obligation there
    is the weaker, still-meaningful one: do not make it worse, i.e. bid NOTHING. Conflating the two
    would have this test demand money that does not exist, which is how a correct implementation
    gets "fixed" into a wrong one.
    """
    mb = A.max_bid(value, 1.0, budget_remaining, open_slots)
    assert mb.max_bid >= 0, "a negative bid is not a bid"
    assert mb.max_bid <= budget_remaining, "bid more money than the team has"

    feasible_on_arrival = budget_remaining >= A.DEFAULT_MIN_BID * open_slots
    if not feasible_on_arrival:
        assert mb.max_bid == 0, (
            f"spent from an already-stranded roster: ${budget_remaining} for {open_slots} spots"
        )
        return

    left_after = budget_remaining - mb.max_bid
    slots_after = open_slots - (1 if mb.max_bid > 0 else 0)
    assert left_after >= A.DEFAULT_MIN_BID * slots_after, (
        f"stranded a slot: ${budget_remaining} with {open_slots} open → bid ${mb.max_bid} "
        f"leaves ${left_after} for {slots_after} spot(s)"
    )
    # ...and the rule must not be satisfied by simply refusing to bid: with a feasible state and an
    # open slot there is ALWAYS at least the minimum bid available. A `max_bid` hardcoded to 0 would
    # pass every clause above.
    assert mb.max_bid >= A.DEFAULT_MIN_BID, "refused a bid a feasible roster could afford"


def test_the_affordability_cap_is_inert_while_there_is_slack():
    """With money to spare the answer must be the VALUATION, untouched. A cap that quietly shaved
    early bids would be a made-up reserve overriding a real number."""
    mb = A.max_bid(40, 1.0, 200, 16)
    assert mb.max_bid == 40
    assert mb.binding == "value"


def test_a_player_with_no_open_slot_is_refused_distinguishably_from_a_full_roster():
    """⚠️ "you have spots but none for a tight end" and "you have no spots at all" are different
    facts. Rendering them identically is how a user re-checks the same thing twice."""
    no_slot = A.max_bid(40, 1.0, 150, 5, eligible=False)
    full = A.max_bid(40, 1.0, 150, 0)
    assert (no_slot.max_bid, no_slot.binding) == (0, "no_slot")
    assert (full.max_bid, full.binding) == (0, "roster_full")


def test_inflation_scales_the_bid_in_both_directions():
    assert A.max_bid(40, 1.25, 200, 16).max_bid == 50
    assert A.max_bid(40, 0.80, 200, 16).max_bid == 32


def test_dollars_per_slot_is_zero_rather_than_infinite_on_a_full_roster():
    assert A.dollars_per_slot(50, 0) == 0.0
    assert A.dollars_per_slot(60, 4) == 15.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Inflation — the dynamic a snake optimizer has no analog for
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_inflation_starts_at_one_and_moves_the_right_way_when_the_room_overpays():
    """⭐ THE DIRECTION IS THE WHOLE SIGNAL, and it is the half a reader most often gets backwards.
    A room that OVERPAYS has less money left chasing the same remaining value, so everyone still on
    the board gets CHEAPER — inflation goes BELOW 1. Bargains early ⇒ above 1 later."""
    values = [60, 40, 30, 20, 10] + [1] * 20
    slots = len(values)
    start = A.inflation(sum(values), values, slots)
    assert start.multiplier == pytest.approx(1.0)

    # the $60 player went for $80 — $20 more money left the room than value left the board
    after_overpay = A.inflation(sum(values) - 80, values[1:], slots - 1)
    assert after_overpay.multiplier < 1.0

    # ...and the mirror: he went for $40, so $20 of purchasing power stayed behind
    after_bargain = A.inflation(sum(values) - 40, values[1:], slots - 1)
    assert after_bargain.multiplier > 1.0


def test_inflations_denominator_is_the_draftable_remainder_not_the_whole_board():
    """⚠️ A 700-row board has a long tail of minimum-bid players nobody will roster. Counting them
    would inflate the denominator permanently and understate the multiplier all draft long."""
    contenders = [50, 40, 30]
    tail = [1] * 500
    scoped = A.inflation(120, contenders + tail, 3)
    assert scoped.value_remaining == 120, "the un-draftable tail leaked into the denominator"
    assert scoped.multiplier == pytest.approx(1.0)


def test_a_degenerate_room_reports_a_neutral_multiplier_rather_than_an_infinity():
    """`value x multiplier` must stay well-defined for the caller. `Infinity` is a number in JS and
    would render as '∞' beside a dollar sign (the `fullSeasonRate` lesson, one surface over)."""
    assert A.inflation(0, [], 0).multiplier == 1.0
    assert A.inflation(500, [], 10).multiplier == 1.0
    assert A.inflation(500, [10, 20], 0).multiplier == 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. FACE VALIDITY on a realistically-shaped board — the check the toy vectors cannot make
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _realistic_board(n_above: int = 120, n_total: int = 700) -> list[dict]:
    """A board shaped like a real one: a steep top, a long above-replacement middle, and a very
    long tail at or below replacement. VOR decays from 150 (the best RB on the served 2026 board)
    to 0 across the startable population, which is the shape `vor.py` produces by construction."""
    rows: list[dict] = []
    for i in range(n_total):
        if i < n_above:
            # convex decay: a handful of studs, then a long flat middle
            vor = 150.0 * ((1.0 - i / n_above) ** 1.6)
        else:
            vor = -0.5 * (i - n_above)
        rows.append({"id": f"p{i}", "vor": vor, "vorP10": vor - 40, "vorP90": vor + 55})
    return rows


def test_the_dollars_that_will_actually_be_spent_add_up_to_the_pool():
    """⭐ THE CONSERVATION IDENTITY, and it is the single strongest check on the model.

    Only `spots_total` players ever get bought, so the values of the TOP `spots_total` players must
    sum to the money in the room. Every $1 tail row beyond that is a player nobody rosters, which is
    why summing the WHOLE board (~700 rows) legitimately exceeds the pool and is NOT the identity.

    This is also precisely why `inflation` reads ~1.00 at the start of a draft — same numerator,
    same denominator. A model that failed here would hand out a room's worth of money that does not
    exist, and every max bid downstream would be wrong in the same direction.
    """
    pool = A.auction_pool(12, 16, 200)
    values = sorted((v.value for v in A.auction_values(_realistic_board(), pool)), reverse=True)
    spent = sum(values[: pool.spots_total])
    assert spent == pytest.approx(pool.total, rel=0.01), (
        f"the draftable board is worth ${spent} against a ${pool.total} room"
    )
    assert sum(values) > pool.total, (
        "the whole-board sum did NOT exceed the pool — the $1 tail has gone missing, so this "
        "test's identity is being satisfied for the wrong reason"
    )


def test_the_identity_survives_a_board_with_far_more_good_players_than_roster_spots():
    """⭐ THE DEFECT THE FACE-VALIDITY CHECK ACTUALLY CAUGHT, kept as its own regression.

    The first cut divided the surplus by the WHOLE board's above-replacement value. On a board
    carrying far more above-replacement players than the league has roster spots, most of the money
    was allocated to players nobody will ever buy — the draftable 180 came out worth 44% of the pool
    and the auction opened at an inflation of 2.06x, which would have told every user that prices
    were double value before a single dollar was spent.

    ⚠️ THIS SHAPE IS NOT HYPOTHETICAL — it is the shipped E2E board fixture (722 above-replacement
    rows against 180 spots), and no unit of arithmetic on a normally-shaped board can see it.
    """
    pool = A.auction_pool(12, 15, 200)  # 180 roster spots
    # 722 above-replacement players, near-flat — the fixture's real shape.
    board = [
        {"id": f"p{i}", "vor": 250.0 - (i * 60.0 / 722)} if i < 722 else {"id": f"p{i}", "vor": -1.0}
        for i in range(858)
    ]
    values = sorted((v.value for v in A.auction_values(board, pool)), reverse=True)
    drafted = sum(values[: pool.spots_total])
    assert drafted == pytest.approx(pool.total, rel=0.01), (
        f"the draftable board is worth ${drafted} against a ${pool.total} room — the surplus is "
        f"leaking to players nobody will roster"
    )
    # ...which is the same statement as "the auction opens at par".
    start = A.inflation(pool.total, values, pool.spots_total)
    assert start.multiplier == pytest.approx(1.0, abs=0.02)


def test_the_top_player_prices_in_the_band_a_real_auction_would_recognise():
    """The vectors are scale-free arithmetic on a 7-row toy and will happily price the best player
    in a $200 league at $1,228. Only a realistic board can say whether the DOLLARS are sane.

    A top value between a fifth and a half of one team's budget is the range every published
    auction-value set lands in; outside it the model is broken in a way no unit of arithmetic
    would show."""
    pool = A.auction_pool(12, 16, 200)
    values = sorted((v.value for v in A.auction_values(_realistic_board(), pool)), reverse=True)
    assert 0.20 * pool.budget <= values[0] <= 0.50 * pool.budget, (
        f"the best player is worth ${values[0]} of a ${pool.budget} budget"
    )
    # Non-increasing throughout, and STRICTLY decreasing across a gap wide enough to clear the
    # rounding. ⚠️ Adjacent ties are correct, not a defect: values are whole dollars, so two players
    # a point of VOR apart genuinely price the same — demanding `values[0] > values[1]` would be
    # asserting a precision the dollar does not have.
    assert values == sorted(values, reverse=True)
    assert values[0] > values[10] > values[100], "the board is flat where it should be decaying"


def test_a_bigger_budget_raises_every_contested_value_and_leaves_the_floor_alone():
    """Monotonicity in the budget — the property that lets one exported board be re-priced for any
    league's budget instead of needing an export per budget."""
    board = _realistic_board()
    cheap = A.auction_values(board, A.auction_pool(12, 16, 100))
    rich = A.auction_values(board, A.auction_pool(12, 16, 300))
    assert rich[0].value > cheap[0].value
    assert rich[-1].value == cheap[-1].value == 1, "the minimum bid moved with the budget"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The config carries the draft type
# ══════════════════════════════════════════════════════════════════════════════════════════════


def _cfg(**kw) -> LeagueConfig:
    base = dict(
        name="t",
        sport="nfl",
        n_teams=12,
        scoring=ScoringRules(per_stat={"rec": 1.0}),
        roster=(
            RosterSlot("QB", 1, ("QB",)),
            RosterSlot("RB", 2, ("RB",)),
            RosterSlot("BN", 6, ("QB", "RB"), bench=True),
        ),
    )
    base.update(kw)
    return LeagueConfig(**base).validate()


def test_a_league_config_round_trips_its_draft_type_and_budget():
    cfg = _cfg(draft_type="auction", auction_budget=260)
    back = LeagueConfig.from_dict(cfg.to_dict())
    assert (back.draft_type, back.auction_budget) == ("auction", 260)


def test_a_config_serialized_before_this_shipped_reads_as_a_snake_league():
    """⚠️ The safe default, and the reverse would invent a budget nobody set. Every league that
    exists in the store today is a snake league."""
    d = _cfg().to_dict()
    d.pop("draft_type")
    d.pop("auction_budget")
    assert LeagueConfig.from_dict(d).draft_type == "snake"


def test_the_draft_type_is_always_serialized_so_a_reader_sees_one_shape():
    """A key that appears only sometimes is the shape a reader gets wrong (the NF-C0 dropped-key
    class, on the serialize side)."""
    d = _cfg().to_dict()
    assert d["draft_type"] == "snake" and d["auction_budget"] == 200


def test_an_unknown_draft_type_is_refused():
    with pytest.raises(ValueError, match="draft_type"):
        _cfg(draft_type="salary_cap")


def test_only_an_auction_league_is_required_to_carry_a_positive_budget():
    """A snake league carries the default as inert baggage; refusing it there would fail configs
    with no auction in them at all."""
    with pytest.raises(ValueError, match="auction_budget"):
        _cfg(draft_type="auction", auction_budget=0)
    assert _cfg(draft_type="snake", auction_budget=0).auction_budget == 0


def test_roster_spots_counts_the_bench_because_a_bench_spot_still_costs_a_dollar():
    assert _cfg().roster_spots() == 9  # 1 QB + 2 RB + 6 bench


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The published fields, and who may read them
# ══════════════════════════════════════════════════════════════════════════════════════════════


def test_the_exporter_stamps_the_auction_fields_on_every_row_additively():
    """⚠️ ADDITIVE ONLY. The API Lambda has no CD (NF-C0), so the deployed client is always some
    previous build; a dropped or renamed key blanks it with a 200 and no error anywhere. Assert the
    NEW keys arrive AND that the ones the current client reads are untouched."""
    from quant_sports_intel_models.football.nfl.fantasy import export_draft_board_json as EX

    before = [
        {"id": "a", "pos": "RB", "vor": 150.0, "vorP10": 90.0, "vorP90": 205.0, "ovrRank": 1},
        {"id": "b", "pos": "WR", "vor": 40.0, "ovrRank": 2},
        {"id": "gapfill", "pos": "K", "vor": None, "ovrRank": 3},
    ]
    rows = [dict(r) for r in before]
    EX.attach_auction_values(rows, "half_ppr", 12)

    for original, row in zip(before, rows):
        for k, v in original.items():
            assert row[k] == v, f"the exporter changed the existing field {k!r}"
        assert {"aucVal", "aucLo", "aucHi"} <= set(row), "a published row carries no auction value"
        assert row["aucLo"] <= row["aucVal"] <= row["aucHi"]
    # ...including the gap-fill row, which must price rather than render blank on an auction board.
    assert rows[-1]["aucVal"] == 1


def test_a_saved_league_round_trips_its_draft_type_through_the_api_model():
    """⚠️ THE SILENT-SAVE CLASS (E8.6), and it is why this is a test rather than a glance.

    The league API models set no `extra="forbid"`, so a key the model does not DECLARE is accepted,
    ignored and lost with a 200 and no error anywhere. `canonical.build_config` now emits
    `draft_type`/`auction_budget` on every import, so a model missing them would round-trip every
    imported league through the store having quietly dropped its draft type — the config would claim
    a field the store does not keep.
    """
    from app.backend.models import fantasy as M

    payload = {
        "name": "Auction Home League",
        "sport": "nfl",
        "n_teams": 12,
        "scoring": {"per_stat": {"rec": 1.0}, "position_bonuses": {}},
        "roster": [{"name": "QB", "count": 1, "eligible": ["QB"], "bench": False}],
        "draft_type": "auction",
        "auction_budget": 260,
    }
    saved = M.LeagueSave(**payload)
    assert saved.draft_type == "auction", "the draft type was dropped on save"
    assert saved.auction_budget == 260, "the budget was dropped on save"
    # ...and the default is snake, so every league already in the store reads correctly.
    assert M.LeagueSave(**{k: v for k, v in payload.items()
                          if k not in ("draft_type", "auction_budget")}).draft_type == "snake"


def test_a_locked_caller_never_receives_an_auction_dollar_value():
    """⭐ AUCTION DOLLARS ARE A PAID FIELD, and this is the assertion that says so.

    They are OUR valuation of OUR projections — `vor` rescaled into money — so a locked board that
    carried them would hand over the model output the lock exists to withhold, in a different unit.
    The board allowlist is IDENTITY + MARKET, so they are stripped automatically; this pins that
    the automatic behaviour is the intended one rather than an accident nobody checked.

    ⛔ THE FIX IF THIS EVER FAILS IS NOT TO ADD THEM TO THE ALLOWLIST. `aucVal` is derivable back
    into `vor` by anyone who knows the pool.
    """
    from app.backend.services import entitlement

    row = {
        "id": "x", "name": "A Player", "pos": "RB", "team": "KC", "bye": 6, "adp": 4.2,
        "pts": 300.0, "vor": 150.0, "ovrRank": 1, "posRank": 1,
        "aucVal": 63, "aucLo": 38, "aucHi": 88,
    }
    (locked,) = entitlement.lock_board_rows([row])
    for field in ("aucVal", "aucLo", "aucHi"):
        assert field not in locked, f"a locked board leaked {field} — auction dollars are paid"
    # ...and the row is still recognisably a player, or the free board stops being coherent.
    assert locked["name"] == "A Player" and locked["adp"] == 4.2
    # The lock chip is computed from the real payload, so the new fields must SHOW as withheld
    # rather than silently vanishing (that is what turns them into a CTA instead of a hole).
    assert {"aucVal", "aucLo", "aucHi"} <= set(
        entitlement.locked_field_names([row], entitlement._PUBLIC_BOARD_FIELDS)
    )
