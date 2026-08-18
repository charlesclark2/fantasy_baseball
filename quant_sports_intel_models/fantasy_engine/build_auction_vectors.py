"""build_auction_vectors.py — the CROSS-LANGUAGE PIN for the NF-C5 auction math.

⭐ WHY THIS FILE EXISTS. The auction value + max-bid rules are implemented TWICE by necessity: in
Python (`fantasy_engine/auction.py`, the authority, which the exporter publishes from) and in
TypeScript (`frontend/lib/auction-optimizer.ts`, which recomputes live in the browser on every bid).
This repo has been bitten repeatedly by two implementations of one rule drifting apart — the E9.61
"two renderers of one field are two rule sets" lesson, and the NF-EPIC 1 three-way scoring parity
gate that had to be made a merge gate for exactly this reason.

A prose comment saying "keep these in sync" is not a mechanism. So the Python authority emits a
GOLDEN VECTOR FILE, and BOTH sides assert against it:

  * `betting_ml/tests/test_fantasy_auction_values.py` regenerates it in memory and refuses any drift
    from the committed bytes — so the file can never be stale relative to the Python.
  * `frontend/e2e/specs/fantasy-auction-optimizer.spec.ts` reads the SAME file across the tree (the
    pattern `ESPN_REAL_PASTES` already uses) and runs the TS through it.

⇒ if either implementation moves, one of those two goes red. Copying the file into `frontend/` would
defeat the whole point (a fixture that drifts from the one the authority is tested against).

Regenerate:  uv run python -m quant_sports_intel_models.fantasy_engine.build_auction_vectors
"""
from __future__ import annotations

import json
from pathlib import Path

from quant_sports_intel_models.fantasy_engine.auction import (
    auction_pool,
    auction_values,
    dollars_per_slot,
    inflation,
    max_bid,
)

VECTORS_PATH = Path(__file__).resolve().parent / "auction_vectors.json"

# A deliberately SMALL, hand-readable board whose arithmetic can be checked by eye. Every shape the
# rules have to handle is present exactly once, so a vector that changes names the rule that broke:
#   * a runaway stud (the whole top of the surplus)
#   * a mid player, kept from the retired-band era for its asymmetric interval
#   * a replacement-level player (vor == 0 → exactly the minimum bid)
#   * a BELOW-replacement player (negative vor → still the minimum, never below it)
#   * a genuinely unprojected gap-fill row (vor is null → minimum, and must not blow up the sum)
#   * a row whose p10/p90 arrive CROSSED — retained ON PURPOSE after the dollar band was retired:
#     the interval columns are now IGNORED, and a board that still carries a crossed one must
#     price exactly like any other. It is the fixture that proves they are not read.
#   * a FRINGE above-replacement player who exists only so the draftable-set truncation has
#     something to exclude — with him the toy board carries FIVE positive-VOR rows against the
#     4-spot pool below, so that pool's rate genuinely differs from the whole-board rate
_BOARD = [
    {"id": "stud", "vor": 150.0, "vorP10": 90.0, "vorP90": 205.0},
    {"id": "mid", "vor": 60.0, "vorP10": 12.0, "vorP90": 140.0},
    {"id": "steady", "vor": 40.0, "vorP10": 30.0, "vorP90": 52.0},
    {"id": "replacement", "vor": 0.0, "vorP10": -20.0, "vorP90": 18.0},
    {"id": "below", "vor": -25.0, "vorP10": -60.0, "vorP90": -4.0},
    {"id": "unprojected", "vor": None, "vorP10": None, "vorP90": None},
    {"id": "crossed", "vor": 20.0, "vorP10": 44.0, "vorP90": 6.0},
    {"id": "fringe", "vor": 15.0, "vorP10": 2.0, "vorP90": 33.0},
]

# (n_teams, roster_spots, budget).
_POOLS = [
    (12, 16, 200),
    (10, 20, 260),
    # The degenerate case the docstring promises to handle: a budget that cannot even cover its own
    # minimum bids ⇒ zero surplus ⇒ everyone at the minimum.
    (12, 16, 10),
    # ⭐ ANTI-VACUITY, AND IT IS LOAD-BEARING. Every pool above has more roster spots (192, 200) than
    # this board has rows (7), so the draftable-set truncation in `auction_values` is INACTIVE in all
    # of them — a port that dropped the truncation entirely would match every vector and still be
    # wrong on any board with more above-replacement players than roster spots (the exact defect the
    # E2E fixture exposed: 722 of them against 180 spots, opening the auction at 2.06x).
    # 2 teams x 2 spots = 4 draftable against FIVE positive-VOR rows, so the truncation
    # BINDS here and only here — `fringe` is excluded from the denominator and the rate moves.
    (2, 2, 50),
]

# (label, value, inflation, budget_remaining, open_slots, eligible) probes for the never-strand
# rule. ⚠️ `value` is carried PER CASE rather than reused from the board above, deliberately: the
# board's toy values are far larger than any of these budgets, so reusing them would make the
# affordability cap bind in EVERY case and the `binding == "value"` branch would never be exercised
# — a fixture that cannot distinguish the two outcomes it exists to distinguish.
_BID_CASES = [
    # value binds: plenty of budget and slots, so the valuation is the whole answer
    ("value_binds", 40, 1.0, 200, 16, True),
    # inflation moves the bid in BOTH directions off the same sticker value
    ("inflation_lifts_the_bid", 40, 1.25, 200, 16, True),
    ("deflation_lowers_the_bid", 40, 0.80, 200, 16, True),
    # affordability binds: the money left cannot cover the valuation AND the other spots' minimums
    ("affordability_binds", 40, 1.0, 20, 6, True),
    ("one_slot_left_spend_it_all", 40, 1.0, 33, 1, True),
    ("last_dollar_last_slot", 40, 1.0, 1, 1, True),
    # the never-strand edge: enough for this spot only if the others get nothing ⇒ refuse
    ("cannot_cover_minimums", 40, 1.0, 3, 9, True),
    ("exactly_covers_minimums", 40, 1.0, 9, 9, True),
    # ⭐ PINS THE ROUNDING RULE, and nothing else in the vectors does. 45 x 0.5 = 22.5, whose FLOOR
    # IS EVEN — so Python's default `round` (banker's, half-to-even) gives 22 while JS `Math.round`
    # and our `_round_half_up` give 23. Without a case landing on a half with an even floor, the two
    # implementations could use different rounding and match every vector, then disagree by $1 on
    # real boards. (17.5 is included as the control: there the two rules AGREE, so a fixture built
    # only from that value would prove nothing.)
    ("half_with_even_floor_rounds_up", 45, 0.5, 200, 16, True),
    ("half_with_odd_floor_is_unambiguous", 35, 0.5, 200, 16, True),
    ("no_slot_for_position", 40, 1.0, 150, 5, False),
    ("roster_full", 40, 1.0, 150, 0, True),
]

# (label, dollars_remaining, slots_remaining) — the room's state. `remaining_values` is always the
# board's own values for the first pool, so the multiplier is comparable across cases.
_INFLATION_CASES = [
    ("start_of_draft", 2400, 192),
    ("room_overpaid", 1000, 120),
    ("room_thrifty", 1800, 120),
    ("nothing_left", 0, 0),
    ("more_slots_than_board", 500, 999),
]


def build() -> dict:
    out: dict = {
        "_note": (
            "GENERATED by fantasy_engine/build_auction_vectors.py — do not hand-edit. "
            "Read by BOTH the Python auction tests and the TS auction E2E spec; the two "
            "implementations of the NF-C5 auction math are pinned to each other through it."
        ),
        "board": _BOARD,
        "pools": [],
        "maxBids": [],
        "inflation": [],
        "dollarsPerSlot": [],
    }

    first_values: list[int] = []
    for n_teams, roster_spots, budget in _POOLS:
        pool = auction_pool(n_teams, roster_spots, budget)
        vals = auction_values(_BOARD, pool)
        if not first_values:
            first_values = [v.value for v in vals]
        out["pools"].append({
            "nTeams": n_teams,
            "rosterSpots": roster_spots,
            "budget": budget,
            "pool": {"total": pool.total, "reserve": pool.reserve, "surplus": pool.surplus},
            "values": [
                {"id": v.player_id, "value": v.value, "share": v.share}
                for v in vals
            ],
        })

    for label, value, mult, budget_remaining, open_slots, eligible in _BID_CASES:
        mb = max_bid(value, mult, budget_remaining, open_slots, eligible=eligible)
        out["maxBids"].append({
            "case": label,
            "value": value,
            "inflationMultiplier": mult,
            "budgetRemaining": budget_remaining,
            "openSlots": open_slots,
            "eligible": eligible,
            "maxBid": mb.max_bid,
            "inflated": mb.inflated,
            "affordable": mb.affordable,
            "binding": mb.binding,
        })

    for label, dollars, slots in _INFLATION_CASES:
        inf = inflation(dollars, first_values, slots)
        out["inflation"].append({
            "case": label,
            "dollarsRemaining": dollars,
            "slotsRemaining": slots,
            "remainingValues": first_values,
            "multiplier": round(inf.multiplier, 6),
            "valueRemaining": inf.value_remaining,
        })

    for budget_remaining, open_slots in ((200, 16), (37, 4), (5, 0)):
        out["dollarsPerSlot"].append({
            "budgetRemaining": budget_remaining,
            "openSlots": open_slots,
            "perSlot": round(dollars_per_slot(budget_remaining, open_slots), 6),
        })

    return out


def serialise(payload: dict) -> str:
    """One canonical rendering, so "regenerate and diff" is a byte comparison."""
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def main() -> int:
    VECTORS_PATH.write_text(serialise(build()))
    print(f"wrote {VECTORS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
