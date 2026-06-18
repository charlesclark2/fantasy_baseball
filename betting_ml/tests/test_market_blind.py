"""Tests for the market-blind CONTRACT-GUARD (Edge Program §0.1; binds E2/E5/E6/E7/E8).

Covers Story E2.1's AC "market-leakage guard passes": the guard must catch every
market/odds column the feature store ships AND must NOT false-positive on the baseball
features whose names brush up against market vocabulary.
"""

from __future__ import annotations

import pytest

from betting_ml.utils.market_blind import (
    MarketLeakageError,
    assert_market_blind,
    find_market_columns,
    is_market_column,
)

# Real market columns from feature_pregame_game_features (the matrix must never contain these)
MARKET_COLS = [
    "home_moneyline_american", "over_american", "under_american",
    "home_implied_prob", "over_implied_prob", "under_implied_prob",
    "home_win_prob_consensus", "home_win_prob_sharp", "home_win_prob_soft",
    "over_prob_consensus", "total_market_vig", "totals_market_vig",
    "total_line", "total_line_consensus", "total_line_std", "totals_line_std",
    "open_total_line", "home_h2h_line_movement", "total_line_movement", "home_open_win_prob",
    "ml_consensus_std", "ml_implied_prob_std", "sharp_soft_ml_spread",
    "market_bookmaker_count", "n_books_available", "stale_book_flag",
    "odds_bookmaker_key", "odds_hours_before_game", "has_odds",
    "home_ml_money_pct", "over_ticket_pct", "ml_sharp_signal", "total_sharp_signal",
    "has_public_betting_data",
]

# Baseball features whose names flirt with market vocabulary but are NOT market-derived
TRICKY_BASEBALL_COLS = [
    "home_team_sequential_win_prob",     # sequential model output, not a market line
    "away_team_sequential_win_prob",
    "pythagorean_win_exp_diff",          # win_exp, not win_prob
    "home_pythagorean_win_exp",
    "home_win_rate_trailing_3yr",        # win_rate, not win_prob_*
    "home_win_pct",
    "is_day_game",
    "home_starter_avg_fastball_velo",
]

# Plain baseball features the matrix legitimately contains
BASEBALL_COLS = [
    "off_avg_eb_woba", "opp_starter_eb_xwoba_against", "opp_bp_eb_xwoba",
    "opp_bullpen_pitches_prev_3d", "park_run_factor_3yr", "elevation_ft",
    "temp_f", "wind_component_mph", "ump_run_impact_zscore", "is_home",
    "off_lineup_vs_opp_starter_xwoba_adj", "opp_team_oaa_blended",
]


class TestDetectsMarketColumns:
    @pytest.mark.parametrize("col", MARKET_COLS)
    def test_each_market_col_flagged(self, col):
        assert is_market_column(col), f"{col} should be flagged as market-derived"

    def test_find_market_columns_returns_all(self):
        found = find_market_columns(MARKET_COLS + BASEBALL_COLS)
        assert set(found) == set(MARKET_COLS)


class TestNoFalsePositives:
    @pytest.mark.parametrize("col", TRICKY_BASEBALL_COLS + BASEBALL_COLS)
    def test_baseball_cols_not_flagged(self, col):
        assert not is_market_column(col), f"{col} must NOT be flagged as market"

    def test_clean_matrix_passes_guard(self):
        # Should not raise
        assert_market_blind(BASEBALL_COLS + TRICKY_BASEBALL_COLS, context="test matrix")


class TestAssertRaises:
    def test_raises_on_single_leak(self):
        cols = BASEBALL_COLS + ["home_win_prob_consensus"]
        with pytest.raises(MarketLeakageError) as exc:
            assert_market_blind(cols, context="leaky matrix")
        assert "home_win_prob_consensus" in str(exc.value)
        assert "leaky matrix" in str(exc.value)

    def test_case_insensitive(self):
        assert is_market_column("HOME_MONEYLINE_AMERICAN")
        assert is_market_column("Over_Prob_Consensus")
