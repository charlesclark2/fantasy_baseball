"""auction.py — SPORT-AGNOSTIC auction dollar values + the live budget/inflation math (NF-C5).

An auction draft is not a snake draft with prices bolted on. A snake draft allocates a fixed
sequence of PICKS; an auction allocates a fixed pool of MONEY, and the two dynamics have almost
nothing in common. This module owns the two pieces that are specific to money:

  1. VALUES — turn a VOR board into dollar values for one `(config, size, budget)`.
  2. THE LIVE MATH — inflation, the affordability cap, and the resulting max bid.

Nothing here knows what football is: it reads `vor` (and, when present, the projection's own 80%
interval on VOR) plus the league's roster shape. An MLB roto auction plugs into the same functions
with the same meaning, which is why it lives beside `vor.py` rather than in the NFL package.

──────────────────────────────────────────────────────────────────────────────────────────────────
THE VALUE MODEL, and what it does NOT claim
──────────────────────────────────────────────────────────────────────────────────────────────────
Every drafted roster spot costs at least $1, so that money is not available to bid with — it is
already committed the moment the league's roster shape is known:

    pool     = n_teams x budget                (all the money in the room)
    reserve  = n_teams x roster_spots x $1     (the minimum every spot must cost)
    surplus  = pool - reserve                  (the only money that is actually contested)

The surplus is what a bidding war is fought over, so it is what gets distributed — by each player's
share of the board's total ABOVE-REPLACEMENT value:

    rate     = surplus / SUM(max(vor, 0))
    value    = $1 + rate x max(vor, 0)

A player at or below replacement is worth exactly the minimum, which is the correct answer: he is
freely available, so nobody has a reason to bid a second dollar.

⭐ THE RANGE IS THE PROJECTION'S UNCERTAINTY, NOT A PRICE FORECAST — and conflating those would be
the dishonest reading. `low`/`high` price the player's OWN p10/p90 season at the SAME league rate:
"if he lands at the 10th percentile of what we project, this is what he was worth." It is NOT "you
should expect the bidding to stop between $34 and $61" — we have no market model, and a $ point
estimate quoted to the dollar off a projection with a 100-point interval would be false precision.
The band is the honest form of the same number.

⛔ NOT AN EDGE CLAIM. These are OUR valuations of OUR projections. `best_alpha = 0` throughout: no
part of this says we beat the room, and the product must not say so either.
"""
from __future__ import annotations

from dataclasses import dataclass

# The minimum bid — one unit of the league's currency. A parameter rather than a literal because a
# league can run a $1 or a $0 minimum (and MLB roto sometimes runs $0), and every derivation below
# ("reserve", "affordability") is written in terms of it.
DEFAULT_MIN_BID = 1

# The budget every shipped preset is quoted in when nothing else is said. $200 is the near-universal
# default across the major hosts, and the value model is monotone in it — a league on a different
# budget recomputes from the same board rather than needing a new export.
DEFAULT_AUCTION_BUDGET = 200

DRAFT_TYPES = ("snake", "auction")


def _round_half_up(x: float) -> int:
    """⭐⭐ ROUND HALF UP, NOT PYTHON'S DEFAULT — and this is a cross-language correctness
    requirement, not a style preference.

    Python's built-in `round` is BANKER'S rounding (half to even): `round(2.5) == 2`. JavaScript's
    `Math.round` is half UP: `Math.round(2.5) === 3`. `frontend/lib/auction-optimizer.ts`
    re-implements this arithmetic to recompute live in the browser, so leaving each side on its
    native rounding would make the two disagree by exactly $1 on every value that lands on a half —
    a drift too small to notice by eye, on the number a user is about to bid real money against.

    Every quantity rounded here is non-negative (`min_bid + rate * x` with a non-negative rate and a
    clamped-non-negative VOR; `value * multiplier` likewise), so `floor(x + 0.5)` is exactly half-up
    and needs no negative-number branch. The golden vectors pin the two implementations together;
    this is what makes them agree in the first place.
    """
    return int((x + 0.5) // 1)


@dataclass(frozen=True)
class AuctionPool:
    """The three league-level money quantities every other number here is derived from."""

    total: int
    """All the money in the room — `n_teams x budget`."""
    reserve: int
    """Committed to minimum bids — `n_teams x roster_spots x min_bid`. Never contested."""
    surplus: int
    """`total - reserve`. The only money a bidding war is actually about."""
    roster_spots: int
    """Spots on ONE team (starters + bench)."""
    n_teams: int
    budget: int
    min_bid: int

    @property
    def spots_total(self) -> int:
        """Roster spots across the whole league — how many players get bought."""
        return self.n_teams * self.roster_spots


def auction_pool(
    n_teams: int,
    roster_spots: int,
    budget: int = DEFAULT_AUCTION_BUDGET,
    *,
    min_bid: int = DEFAULT_MIN_BID,
) -> AuctionPool:
    """The money decomposition for one `(size, roster shape, budget)`.

    ⚠️ `surplus` is clamped at 0 rather than allowed to go negative. A league whose budget cannot
    even cover its own minimum bids (`budget < roster_spots x min_bid`) is a misconfiguration, and
    the honest degenerate answer is "every player is worth the minimum" — not a negative rate that
    would invert the whole board.
    """
    if n_teams <= 0:
        raise ValueError(f"n_teams must be positive, got {n_teams}")
    if roster_spots <= 0:
        raise ValueError(f"roster_spots must be positive, got {roster_spots}")
    if budget <= 0:
        raise ValueError(f"budget must be positive, got {budget}")
    if min_bid < 0:
        raise ValueError(f"min_bid must be non-negative, got {min_bid}")
    total = int(n_teams) * int(budget)
    reserve = int(n_teams) * int(roster_spots) * int(min_bid)
    return AuctionPool(
        total=total,
        reserve=reserve,
        surplus=max(0, total - reserve),
        roster_spots=int(roster_spots),
        n_teams=int(n_teams),
        budget=int(budget),
        min_bid=int(min_bid),
    )


@dataclass(frozen=True)
class AuctionValue:
    """One player's dollar value, with the honest band around it."""

    player_id: str
    value: int
    """The point valuation, in whole dollars. Bids are whole dollars, so this is."""
    low: int
    """Value if the season lands at the projection's 10th percentile."""
    high: int
    """Value at the 90th percentile."""
    share: float
    """This player's share of the board's total above-replacement value. Kept because it is the
    only budget-INDEPENDENT quantity here: the same share re-prices at any budget."""


def _pos(v) -> float:
    """Above-replacement value, floored at zero — and `None`/NaN reads as zero.

    A genuinely unprojected gap-fill row carries `vor = None`. Treating that as 0 gives it the
    minimum bid, which is the right answer, and (unlike dropping it) keeps it on the board where a
    drafter can still see it.
    """
    if v is None:
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f != f:  # NaN
        return 0.0
    return max(0.0, f)


def auction_values(
    rows,
    pool: AuctionPool,
) -> list[AuctionValue]:
    """Dollar-value every row of a board for one `pool`.

    `rows` is any iterable of mappings carrying `id` (or `player_id`) and `vor`, optionally
    `vorP10`/`vorP90` (or `vor_p10`/`vor_p90`). Pure: no IO, no ordering assumption, and the input
    is not mutated.

    ⭐ THE RATE IS A LEAGUE CONSTANT, AND BOTH BAND EDGES ARE PRICED AT IT. Re-deriving a separate
    rate from the p10 column would answer a different question — "what if EVERY player simultaneously
    landed at his 10th percentile", a world in which the money is unchanged and so the values barely
    move at all. The question a drafter is asking is about ONE player: hold the league fixed, vary
    him. That is this rate applied to his own interval.
    """
    materialised = list(rows)
    values: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    ids: list[str] = []
    for r in materialised:
        ids.append(str(r.get("id", r.get("player_id", ""))))
        v = _pos(r.get("vor"))
        values.append(v)
        # A board with no interval columns falls back to the point value on both edges, which
        # renders as a degenerate band rather than a wrong one.
        lo = r.get("vorP10", r.get("vor_p10"))
        hi = r.get("vorP90", r.get("vor_p90"))
        lows.append(_pos(lo) if lo is not None else v)
        highs.append(_pos(hi) if hi is not None else v)

    # ⭐⭐ THE DENOMINATOR IS THE DRAFTABLE SET, NOT THE WHOLE BOARD — and this is a correctness
    # fix, not a tidy-up. Only `spots_total` players are ever BOUGHT, so only they can absorb the
    # room's money. Dividing the surplus by the whole board's above-replacement value hands real
    # dollars to players nobody will roster, and the players who ARE drafted then come out worth
    # strictly less than the money chasing them.
    #
    # It was found by the face-validity check that inflation must read ~1.00 before a dollar is
    # spent: on a board carrying 722 above-replacement players against 180 roster spots, the first
    # cut priced the draftable 180 at 44% of the pool and the auction opened at 2.06x. On a
    # normally-shaped board (above-replacement count ~= the startable population, comfortably under
    # the roster spots) the eligible set is every positive-VOR player plus a tail of zeros, so this
    # changes nothing at all — it makes the model right on the boards where it was wrong, and is
    # inert on the ones where it was already right.
    #
    # The rate is still APPLIED to every row: a player outside the draftable set is honestly worth
    # what the rate says he is worth, he simply is not part of the money's denominator. That keeps
    # the conservation identity exact BY CONSTRUCTION on any board shape:
    #     sum(value over the top `spots_total`) == reserve + surplus == pool
    # which is in turn why inflation opens at exactly 1.00.
    #
    # ⚠️ The ordering must be DETERMINISTIC and identical to the TS port's. Python's `sorted` and
    # JS's `Array.prototype.sort` are both stable, so ties fall back to the original row order on
    # both sides.
    draftable = sorted(range(len(values)), key=lambda i: -values[i])[: pool.spots_total]
    total_vor = sum(values[i] for i in draftable)
    rate = (pool.surplus / total_vor) if total_vor > 0 else 0.0

    def price(x: float) -> int:
        return max(pool.min_bid, _round_half_up(pool.min_bid + rate * x))

    out: list[AuctionValue] = []
    for i, pid in enumerate(ids):
        lo, hi = price(lows[i]), price(highs[i])
        out.append(
            AuctionValue(
                player_id=pid,
                value=price(values[i]),
                # An interval that arrives crossed (or a rounding tie) must never render as a
                # backwards band — order the two edges rather than trusting the source columns.
                low=min(lo, hi),
                high=max(lo, hi),
                share=round(values[i] / total_vor, 6) if total_vor > 0 else 0.0,
            )
        )
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# THE LIVE MATH — inflation, affordability, max bid
# ══════════════════════════════════════════════════════════════════════════════════════════════════
#
# ⭐⭐ INFLATION IS THE DYNAMIC A SNAKE OPTIMIZER HAS NO ANALOG FOR. In a snake draft the pick you
# hold is worth what it is worth; nothing another team does changes your purchasing power. In an
# auction it does, continuously: every dollar somebody overpays is a dollar that is no longer
# chasing the players still on the board, so everyone left gets CHEAPER. The multiplier is the ratio
# of the two things the room has left:
#
#     inflation = dollars still in the room / value still on the board
#
# It starts at ~1.00 by construction (the values were built to exhaust the pool) and drifts from
# there. Reading its DIRECTION is the whole skill: below 1.00 the room has overpaid and the players
# left are bargains; above 1.00 the room has been thrifty and the rest will cost over sticker.
#
# ⚠️ THE DENOMINATOR IS THE DRAFTABLE REMAINDER, NOT THE WHOLE BOARD. Only as many players as there
# are open roster spots will ever be bought; a 700-row board has a long tail of minimum-bid players
# nobody will roster, and counting them would drag the denominator up and understate inflation
# permanently. So it is the top `slots_remaining` players by value.


@dataclass(frozen=True)
class Inflation:
    multiplier: float
    dollars_remaining: int
    value_remaining: int
    slots_remaining: int


def inflation(
    dollars_remaining: int,
    remaining_values: list[int],
    slots_remaining: int,
) -> Inflation:
    """The room's current price multiplier.

    `remaining_values` is every undrafted player's `value`; `slots_remaining` is how many roster
    spots the whole league still has to fill. Degenerate inputs return a multiplier of exactly 1.0
    — a neutral answer is the only honest one when there is nothing left to measure, and it keeps
    `value x multiplier` well-defined for the caller instead of producing an infinity.
    """
    slots = max(0, int(slots_remaining))
    top = sorted((int(v) for v in remaining_values), reverse=True)[:slots]
    value_remaining = sum(top)
    dollars = max(0, int(dollars_remaining))
    mult = (dollars / value_remaining) if value_remaining > 0 else 1.0
    return Inflation(
        multiplier=mult,
        dollars_remaining=dollars,
        value_remaining=value_remaining,
        slots_remaining=slots,
    )


@dataclass(frozen=True)
class MaxBid:
    """What you may bid on one player, and WHY that number and not another."""

    max_bid: int
    value: int
    """The board's sticker value."""
    inflated: int
    """`value x inflation`, rounded — what he is worth at today's prices."""
    affordable: int
    """The most you can bid and still put `min_bid` on every remaining spot."""
    open_slots: int
    """Your open roster spots BEFORE this player."""
    binding: str
    """Which constraint produced `max_bid`: `"value"`, `"affordability"`, `"no_slot"` or
    `"roster_full"`. Rendered as the "why this bid" line, so it is part of the contract."""


def max_bid(
    value: int,
    inflation_multiplier: float,
    budget_remaining: int,
    open_slots: int,
    *,
    min_bid: int = DEFAULT_MIN_BID,
    eligible: bool = True,
) -> MaxBid:
    """⭐ THE NEVER-STRAND RULE, and it is a correctness property rather than a preference.

    An empty roster spot scores zero, so spending down to a point where a spot cannot be filled is
    not a trade-off a drafter should be allowed to make by accident. Whatever is left after this
    player must still cover the minimum on every OTHER open spot:

        affordable = budget_remaining - min_bid x (open_slots - 1)

    and the bid is `min(inflation-adjusted value, affordable)`. The affordability cap is EXACT —
    with money to spare it is inert, and at the end of a draft it is total, walking the last few
    dollars down to $1 a spot. Deliberately no safety margin: a reserve above the true minimum would
    be a made-up number overriding a real valuation.

    ⚠️ `eligible=False` (no open roster slot this player's position can fill) returns 0 with
    `binding="no_slot"` — DISTINCT from `"roster_full"`, because "you have spots but none for a
    tight end" and "you have no spots at all" are different facts and rendering them identically is
    how a user ends up re-checking the same thing twice.
    """
    slots = max(0, int(open_slots))
    budget = max(0, int(budget_remaining))
    inflated = max(min_bid, _round_half_up(int(value) * float(inflation_multiplier)))
    if slots <= 0:
        return MaxBid(0, int(value), inflated, 0, 0, "roster_full")
    affordable = budget - int(min_bid) * (slots - 1)
    if not eligible:
        return MaxBid(0, int(value), inflated, max(0, affordable), slots, "no_slot")
    if affordable <= 0:
        # Cannot even cover this spot's own minimum. Report 0 rather than a negative number.
        return MaxBid(0, int(value), inflated, 0, slots, "affordability")
    bid = min(inflated, affordable)
    return MaxBid(
        max_bid=int(bid),
        value=int(value),
        inflated=inflated,
        affordable=int(affordable),
        open_slots=slots,
        binding="affordability" if affordable < inflated else "value",
    )


def dollars_per_slot(budget_remaining: int, open_slots: int) -> float:
    """`$X left for Y slots = $Z/slot` — the single most-used number at an auction table."""
    slots = max(0, int(open_slots))
    if slots <= 0:
        return 0.0
    return max(0, int(budget_remaining)) / slots
