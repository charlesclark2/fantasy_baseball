"""
market_features.py — Edge Program, Story E3.0 (shared market-data layer)

Serve-time helpers for the cross-book sharp-anchor / closing-line market models
(Epics E3 + E4). The heavy per-game de-vig / open-close derivation lives in the
dbt model `feature_pregame_edge_market`; this module is the thin Python layer
the daily pipeline (`scripts/predict_today.py`) and the serving store use to:

  1. De-vig a raw two-way price into fair probabilities — REUSING the existing
     odds math (`totals_probability.american_to_implied`, the additive de-vig in
     `h2h_probability` / `totals_probability`). We do NOT reinvent odds math.
  2. Compute the per-book divergence signal `edge_book = pinnacle_fair − book_implied`
     (the E4.1 signal), for each soft book the user might bet.
  3. Apply the freshness rule the spec mandates: "never anchor to a quote older
     than a configurable window." Freshness is a *decision-time* property (how old
     is the sharp quote relative to when the user is acting), so it belongs in code
     that runs at serve time, not baked into the nightly batch — the mart stores the
     quote timestamp; this function judges it against an `as_of` clock.

Honest-framing rule (program-wide): nothing here asserts a bet is +EV or should be
placed. `edge_book` is a transparency signal — the gap between the sharp anchor and
the user's book — surfaced advisory-only (manual betting; `[[feedback_no_auto_betting]]`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from betting_ml.utils.h2h_probability import devig_home_prob
from betting_ml.utils.totals_probability import american_to_implied, devig_over_prob

# Soft books a beta user may bet, in display order. Pinnacle is the sharp ANCHOR,
# never a "book to bet" — it is excluded from this list on purpose.
SOFT_BOOKS: tuple[str, ...] = ("bovada", "caesars", "fanduel")

# Default staleness window (minutes). A sharp quote older than this at decision
# time is treated as stale and must not be used as the fair-value anchor. Tunable
# per call; the spec requires it be configurable, not hard-coded into the signal.
DEFAULT_FRESHNESS_WINDOW_MIN: int = 180


@dataclass(frozen=True)
class QuoteFreshness:
    """Decision-time freshness verdict for a single sharp quote."""

    quote_ts: datetime | None
    as_of: datetime
    age_minutes: float | None
    is_fresh: bool
    window_minutes: int

    def as_dict(self) -> dict:
        return {
            "pinnacle_quote_ts": self.quote_ts.isoformat() if self.quote_ts else None,
            "pinnacle_quote_age_min": self.age_minutes,
            "pinnacle_fresh_flag": self.is_fresh,
            "pinnacle_freshness_window_min": self.window_minutes,
        }


def quote_freshness(
    quote_ts: datetime | None,
    as_of: datetime,
    window_minutes: int = DEFAULT_FRESHNESS_WINDOW_MIN,
) -> QuoteFreshness:
    """Judge a sharp quote's freshness against a decision-time clock.

    `quote_ts` is the timestamp of the freshest pre-game Pinnacle quote (from the
    `feature_pregame_edge_market` mart). `as_of` is when the recommendation is
    being made (the predict_today run time, or request time). A missing quote, or
    a quote older than `window_minutes`, is NOT fresh — callers must then refuse to
    anchor to it (show "no current sharp price" rather than a stale one).
    """
    if quote_ts is None:
        return QuoteFreshness(None, as_of, None, False, window_minutes)
    age_minutes = (as_of - quote_ts).total_seconds() / 60.0
    # A future-dated quote (clock skew) is treated as age 0, still fresh.
    age_minutes = max(age_minutes, 0.0)
    is_fresh = age_minutes <= window_minutes
    return QuoteFreshness(quote_ts, as_of, age_minutes, is_fresh, window_minutes)


def fair_home_prob(home_american: float, away_american: float) -> float:
    """De-vigged P(home win) for an h2h two-way price. Thin alias over the Epic-11
    additive de-vig so market-model callers import one module. NaN on bad input."""
    return devig_home_prob(home_american, away_american)


def fair_over_prob(over_american: float, under_american: float) -> float:
    """De-vigged P(over) for a totals two-way price (at THIS book's own line).
    Thin alias over the Story-10.3 additive de-vig. NaN on bad input."""
    return devig_over_prob(over_american, under_american)


def compute_edge_book(pinnacle_fair_prob: float, book_implied_prob: float) -> float:
    """The E4.1 cross-book signal: `pinnacle_fair − book_implied` (both de-vigged).

    Positive → the sharp anchor prices the reference side (home / over) higher than
    the soft book does, i.e. the soft book may be lagging the sharp price on that
    side. This is a *gap*, surfaced advisory-only — not a +EV assertion.
    Returns NaN if either input is NaN/missing so callers omit the book gracefully.
    """
    try:
        p = float(pinnacle_fair_prob)
        b = float(book_implied_prob)
    except (TypeError, ValueError):
        return float("nan")
    if p != p or b != b:  # NaN guard
        return float("nan")
    return p - b


def h2h_book_edges(
    pinnacle_home_american: float,
    pinnacle_away_american: float,
    book_prices: dict[str, tuple[float, float]],
) -> dict[str, dict]:
    """Per-book h2h divergence vs the Pinnacle anchor.

    `book_prices`: {book_key: (home_american, away_american)} for the soft books the
    user might bet. Returns {book_key: {book_implied_home, edge_home}}; books whose
    price is missing/invalid yield NaN and should be omitted by the caller.
    """
    pinn_fair = fair_home_prob(pinnacle_home_american, pinnacle_away_american)
    out: dict[str, dict] = {}
    for book, (home_px, away_px) in book_prices.items():
        implied = fair_home_prob(home_px, away_px)
        out[book] = {
            "book_implied_home_prob": implied,
            "edge_home": compute_edge_book(pinn_fair, implied),
        }
    return out


def implied_no_vig_pair(price_a: float, price_b: float) -> tuple[float, float]:
    """De-vig a two-way price into (fair_a, fair_b) via the additive method.
    Generic version used where the two outcomes aren't home/over-labelled.
    Returns (nan, nan) on bad input."""
    try:
        ia = american_to_implied(price_a)
        ib = american_to_implied(price_b)
    except (TypeError, ValueError):
        return float("nan"), float("nan")
    total = ia + ib
    if total <= 0:
        return float("nan"), float("nan")
    return ia / total, ib / total
