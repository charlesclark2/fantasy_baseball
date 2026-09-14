"""budget.py — NCAAB Odds-API unit prices (MEASURED) and the FAN-OUT CEILING.

Every constant here was measured against live `x-requests-last` / `x-requests-remaining`
headers on 2026-09-14 and reconciled against an independent free-`/sports` bracket (the two
instruments AGREED exactly on every leg). The witness is
`ablation_results/ncaab_p0_credit_probe.json`. ⛔ Nothing here is quoted from a price sheet —
that is the mistake NF-CAP1 made and had to retract by a factor of 10.

────────────────────────────────────────────────────────────────────────────────────────────
THE ONE NUMBER THAT MATTERS, and it is why this module exists rather than a comment:

    a WHOLE-BOARD historical snapshot of a peak NCAAB Saturday .... 30 credits for 105 events
    the SAME data fetched PER EVENT ................................ 30 credits for 1 event

A per-event fan-out over an NCAAB board is **105x** the price of the bulk call for byte-
identical information. NCAAF could get away with a per-kickoff loop because its ~60 kickoffs
are staggered across one day a week. NCAAB runs 50+ games a night for five months, and the
measured board does NOT cluster (105 events across 45 distinct tip slots), so the per-event
shape that is merely wasteful in football is budget-destroying here.

So the bulk call is the DEFAULT path and a per-event fan-out must ask permission, in code,
every time — `guard_fan_out()` RAISES. It does not truncate. A silently-truncated fan-out
captures a partial board and reports success, which is strictly worse than refusing: the
operator would be paying for a capture whose gaps are invisible.
────────────────────────────────────────────────────────────────────────────────────────────

WHAT THE MEASUREMENTS SHOWED (all 2026-09-14, `us` region):

  FREE (cost 0, measured, not assumed)
    /sports                                     0    (the bracket instrument)
    live /sports/{key}/events                   0    (board enumeration is free)
    live /odds on an EMPTY board                0    ⭐ an out-of-season poll is FREE
    historical /odds before the archive starts  0    ⭐ a pre-archive probe is FREE

  LIVE
    /odds  per market x region                  1    (measured on the futures board)
    /odds  3 markets (h2h,spreads,totals) x us  3    (DERIVED — see LIVE_GAME_LINE_SNAPSHOT)

  HISTORICAL (the 10x tier)
    /odds  per market x region                 10    (measured 3x, one market at a time)
    /odds  3 markets x us                      30    (measured)
    /events                                     1    (NOT free, unlike the live one)
    per-event /odds, 3 markets x us            30    (measured — the fan-out unit price)

  NOT AVAILABLE
    NCAAB player props                        n/a    (measured: HTTP 200, 0 books, 0 markets,
                                                      0 credits — the vendor does not carry
                                                      them, so an E5-style props leg is
                                                      blocked at the source, not budgeted)
"""
from __future__ import annotations

from dataclasses import dataclass

# ── measured unit prices ────────────────────────────────────────────────────────────────
FREE = 0
LIVE_PER_MARKET_PER_REGION = 1
HISTORICAL_PER_MARKET_PER_REGION = 10

#: The historical multiplier, MEASURED rather than quoted: the identical single-market
#: futures call billed 1 live and 10 historical on the same day, same key, same region.
HISTORICAL_MULTIPLIER = HISTORICAL_PER_MARKET_PER_REGION // LIVE_PER_MARKET_PER_REGION  # 10

GAME_LINE_MARKETS = ("h2h", "spreads", "totals")
N_GAME_LINE_MARKETS = len(GAME_LINE_MARKETS)

#: ⚠️ DERIVED, not directly measured — `basketball_ncaab` was out of season on the
#: measurement date so its live board was empty (and an empty board bills 0). The derivation
#: is tight: the per-market HISTORICAL price is measured at 10 and the multiplier is measured
#: at 10x, so the live per-market price is 1 and three markets cost 3. Verify it directly on
#: the first in-season day — it is a one-call check and `credit_probe --no-live` already
#: prints what is needed.
LIVE_GAME_LINE_SNAPSHOT = N_GAME_LINE_MARKETS * LIVE_PER_MARKET_PER_REGION          # 3
HISTORICAL_GAME_LINE_SNAPSHOT = N_GAME_LINE_MARKETS * HISTORICAL_PER_MARKET_PER_REGION  # 30
LIVE_FUTURES_SNAPSHOT = 1 * LIVE_PER_MARKET_PER_REGION                              # 1
HISTORICAL_FUTURES_SNAPSHOT = 1 * HISTORICAL_PER_MARKET_PER_REGION                  # 10
HISTORICAL_EVENTS_LIST = 1
HISTORICAL_PER_EVENT_GAME_LINES = 30

# ── measured board shape (the fan-out sizing input) ─────────────────────────────────────
#: Largest board measured in one snapshot (2026-02-07, a peak February Saturday).
PEAK_BOARD_EVENTS = 105
#: Distinct tip-off slots on that same board — the board does NOT cluster, which is what
#: makes a per-tip-slot strategy nearly as expensive as a per-event one.
PEAK_BOARD_TIP_SLOTS = 45
#: Distinct tip slots falling within 24h of the snapshot, across the five measured dates.
MEASURED_TIP_SLOTS_WITHIN_24H = (16, 20, 24, 30, 16)

#: The archive floor, as the API itself reported it via `next_timestamp` on three
#: pre-archive probes (no binary search needed — the vendor names it).
ARCHIVE_FIRST_SNAPSHOT_GAME_LINES = "2020-11-16T09:15:00Z"
ARCHIVE_FIRST_SNAPSHOT_FUTURES = "2023-10-24T05:45:43Z"
#: Snapshot spacing, measured off the envelope's previous/next timestamps.
ARCHIVE_GRANULARITY_MINUTES = {2021: 10, 2022: 10, 2023: 5, 2024: 5, 2025: 5, 2026: 5}


class FanOutRefused(RuntimeError):
    """A per-event fan-out exceeded its ceiling. Raised — never truncated."""


#: The default ceiling on a per-event loop. Deliberately SMALL: at 30 credits an event the
#: only legitimate per-event use is a targeted repair of a handful of games the bulk call
#: missed. Anything board-sized must use the bulk call, which is 105x cheaper.
DEFAULT_FAN_OUT_CEILING = 8


def guard_fan_out(n_events: int, *, ceiling: int = DEFAULT_FAN_OUT_CEILING,
                  unit_credits: int = HISTORICAL_PER_EVENT_GAME_LINES,
                  context: str = "per-event odds fan-out") -> int:
    """Authorise a per-event fan-out of `n_events`, or REFUSE loudly. Returns the credit cost.

    ⛔ Refuses rather than truncating. A truncated fan-out silently captures a partial board
    and reports success, so the gap is invisible in the artifact and the operator pays for a
    capture they cannot trust. Refusing is recoverable; a silent partial is not.
    """
    if n_events < 0:
        raise ValueError(f"{context}: n_events must be >= 0, got {n_events}")
    cost = n_events * unit_credits
    if n_events > ceiling:
        bulk = HISTORICAL_GAME_LINE_SNAPSHOT
        raise FanOutRefused(
            f"{context}: REFUSING a {n_events}-event fan-out (ceiling {ceiling}). "
            f"It would cost {cost:,} credits. The SAME board is available from ONE bulk "
            f"/odds snapshot for {bulk} credits ({cost // max(bulk, 1)}x cheaper) — use the "
            f"bulk call. If a genuine per-event repair of more than {ceiling} events is "
            f"really intended, raise `ceiling` explicitly at the call site so the extra "
            f"spend is a decision someone made, not a default nobody saw. "
            f"⛔ Do NOT 'fix' this by truncating to the first {ceiling}: a partial board that "
            f"reports success is worse than a refusal."
        )
    return cost


@dataclass(frozen=True)
class CadenceOption:
    """One proposed forward-capture cadence, priced from the measured unit costs."""

    name: str
    polls_per_day: int
    unit_credits: int
    season_days: int
    note: str = ""

    @property
    def credits_per_day(self) -> int:
        return self.polls_per_day * self.unit_credits

    @property
    def credits_per_season(self) -> int:
        return self.credits_per_day * self.season_days


#: The 2026-27 D-I season, first tip to title game (the launch target's own window).
SEASON_2026_27_DAYS = 154


def forward_cadence_menu(season_days: int = SEASON_2026_27_DAYS) -> list[CadenceOption]:
    """The priced forward-capture menu the operator chooses from.

    Game-line polls are whole-board: ONE call returns the entire upcoming board no matter how
    many games are on it (measured up to 105), so cadence — not slate size — is the only
    lever on cost. That is the opposite of the per-event shape and it is why even aggressive
    polling stays cheap.
    """
    g = LIVE_GAME_LINE_SNAPSHOT
    return [
        CadenceOption("game_lines/twice_daily", 2, g, season_days,
                      "a T-1 morning snapshot + one evening snapshot"),
        CadenceOption("game_lines/hourly_16h", 16, g, season_days,
                      "hourly across the 16h window that carries a US slate"),
        CadenceOption("game_lines/every_30min_16h", 32, g, season_days,
                      "30-minute resolution — enough to sit within half an hour of any tip"),
        CadenceOption("game_lines/every_5min_16h", 192, g, season_days,
                      "5-minute resolution — matches the vendor's own archive granularity, "
                      "i.e. the finest closing line that exists"),
        CadenceOption("futures/weekly", 1, LIVE_FUTURES_SNAPSHOT, season_days // 7,
                      "title futures once a week"),
        CadenceOption("futures/daily", 1, LIVE_FUTURES_SNAPSHOT, season_days,
                      "title futures daily — the whole season costs less than one "
                      "historical Saturday"),
    ]


def backfill_cost(seasons: int, snapshots_per_day: int, *,
                  season_days: int = SEASON_2026_27_DAYS,
                  unit: int = HISTORICAL_GAME_LINE_SNAPSHOT) -> int:
    """Priced historical backfill: seasons x days x snapshots/day x measured unit cost."""
    return seasons * season_days * snapshots_per_day * unit
