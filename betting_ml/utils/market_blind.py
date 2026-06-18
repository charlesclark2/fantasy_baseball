"""market_blind.py — the CONTRACT-GUARD for market-blind models (Edge Program §0.1).

WHY THIS EXISTS (architecture Principle 3, non-negotiable)
----------------------------------------------------------
The markets we are trying to beat already price in everything our *baseball* features
contain. So every model that is not itself modelling market behaviour MUST be
market-blind: no odds, implied probabilities, line-movement, consensus, public-betting,
or book-availability features in its training matrix. A non-market model trained on the
line just *relearns the line* (circularity / leakage) and can add nothing orthogonal —
the root reason the current stack cannot beat the market. Market data is permitted only
in the market models (E3/E4) and at the evaluation/CLV-gating layer (E2.6, E5.4).

This module is the single, reusable enforcement point named by the guide for E2, E5, E6,
E7 and E8 ("enforce with a CONTRACT-GUARD-style assertion on every non-market feature
matrix"). Call `assert_market_blind(feature_columns)` immediately before fitting; it raises
`MarketLeakageError` if any column looks market-derived.

DETECTION
---------
Two layers, OR-ed:
  1. `CANONICAL_MARKET_COLS` — the exact column names the project's feature store ships
     (kept in sync with the base models' exclude list, e.g. `train_run_diff_prod.py`).
  2. `MARKET_TOKEN_RE` — a substring regex over token fragments that only ever appear in
     market columns (`odds`, `moneyline`, `implied_prob`, `vig`, `consensus`, `sharp`,
     `book`, `ticket`, `money_pct`, `line_movement`, `open_total`, `total_line`, …). The
     fragments are chosen NOT to collide with any baseball feature name — in particular we
     match `win_prob_consensus`/`open_win_prob`, never a bare `win_prob` (which would
     falsely flag the baseball `team_sequential_win_prob`). New market columns added to the
     store after this file are caught by the regex even if absent from the canonical set.
"""

from __future__ import annotations

import re
from typing import Iterable


class MarketLeakageError(AssertionError):
    """Raised when a market/odds column reaches a market-blind feature matrix."""


# ── Layer 1: exact canonical market columns shipped by feature_pregame_game_features ──
# Mirrors the base models' market exclude set (train_run_diff_prod.py `_MARKET_COLS_TO_EXCLUDE`).
CANONICAL_MARKET_COLS: frozenset[str] = frozenset({
    # Raw American / decimal odds
    "home_moneyline_american", "away_moneyline_american",
    "home_moneyline_decimal", "away_moneyline_decimal",
    "home_moneyline", "away_moneyline",
    "over_american", "under_american",
    # Implied probabilities (de-vigged or raw)
    "home_implied_prob", "away_implied_prob",
    "over_implied_prob", "under_implied_prob",
    "home_win_prob_consensus", "home_win_prob_sharp", "home_win_prob_soft",
    "over_prob_consensus",
    # Vig / hold
    "total_market_vig", "totals_market_vig",
    # Lines + movement
    "total_line", "total_line_consensus", "total_line_std", "totals_line_std",
    "total_line_range", "totals_line_range", "open_total_line", "open_total",
    "close_total", "home_h2h_line_movement", "total_line_movement",
    "home_open_win_prob", "home_open_line", "away_open_line",
    # Market dispersion / book availability
    "ml_consensus_std", "ml_implied_prob_std", "ml_implied_prob_range",
    "sharp_soft_ml_delta", "sharp_soft_ml_spread", "market_bookmaker_count",
    "n_books_available", "stale_book_flag", "odds_bookmaker_key",
    "odds_ingestion_ts", "odds_hours_before_game", "has_odds",
    # Public-betting / sharp-money signals
    "home_ml_money_pct", "home_ml_ticket_pct", "over_money_pct", "over_ticket_pct",
    "home_ml_money_pct_active", "home_ml_ticket_pct_active",
    "over_money_pct_active", "over_ticket_pct_active",
    "ml_sharp_signal", "total_sharp_signal",
    "ml_sharp_signal_active", "total_sharp_signal_active",
    "has_public_betting", "has_public_betting_data",
})

# ── Layer 2: token fragments that occur ONLY in market columns ──
# Each alternative is verified against the full feature_pregame_game_features schema to not
# collide with a baseball feature. NB: we match `win_prob_consensus`/`open_win_prob`, never a
# bare `win_prob`, so the baseball `*_team_sequential_win_prob` is NOT flagged.
_MARKET_TOKENS = [
    r"odds",
    r"moneyline",
    r"implied_prob",
    r"vig",
    r"consensus",
    r"sharp",
    r"book",            # bookmaker / n_books / stale_book
    r"ticket",
    r"money_pct",
    r"line_movement",
    r"open_win_prob",
    r"win_prob_consensus",
    r"win_prob_sharp",
    r"win_prob_soft",
    r"open_total",
    r"close_total",
    r"total_line",
    r"over_american",
    r"under_american",
    r"over_money",
    r"over_ticket",
    r"public_betting",
    r"market",
]
MARKET_TOKEN_RE = re.compile("|".join(_MARKET_TOKENS))


def is_market_column(col: str) -> bool:
    """True if `col` is market/odds-derived (canonical set OR token regex)."""
    c = col.strip().lower()
    return c in CANONICAL_MARKET_COLS or bool(MARKET_TOKEN_RE.search(c))


def find_market_columns(columns: Iterable[str]) -> list[str]:
    """Return the market/odds-derived columns among `columns` (sorted, de-duped)."""
    return sorted({c for c in columns if is_market_column(c)})


def assert_market_blind(columns: Iterable[str], *, context: str = "feature matrix") -> None:
    """CONTRACT-GUARD: raise `MarketLeakageError` if any market column is present.

    Call immediately before fitting any market-blind model (E2/E5/E6/E7/E8). `context`
    is echoed in the error message to identify the offending matrix.
    """
    leaks = find_market_columns(columns)
    if leaks:
        raise MarketLeakageError(
            f"Market-blind violation in {context}: {len(leaks)} market/odds column(s) "
            f"reached the feature matrix (architecture Principle 3): {leaks}"
        )
