"""Tests for Story E2.1 per-side assembly (the wide-mart → game×side unpivot).

Verifies the structural correctness that makes the model meaningful: each batting side is
paired with the OPPOSING pitching, shared context is duplicated, the target is that side's
runs, and the assembled matrix is market-blind. No Snowflake — operates on a synthetic frame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.totals_generative.train_perside_negbin import (
    build_perside_frame,
)
from betting_ml.utils.market_blind import find_market_columns


def _wide_frame() -> pd.DataFrame:
    """Two games with a representative slice of offence/pitching/shared/matchup bases."""
    rows = [
        {
            "game_pk": 1, "game_date": "2024-04-02", "game_year": 2024,
            "home_final_score": 5, "away_final_score": 3,
            # offence bases (home stronger than away)
            "home_avg_eb_woba": 0.330, "away_avg_eb_woba": 0.300,
            "home_off_woba_30d": 0.340, "away_off_woba_30d": 0.305,
            # opposing-pitching bases
            "home_starter_eb_xwoba_against": 0.310, "away_starter_eb_xwoba_against": 0.290,
            "home_bp_eb_xwoba": 0.320, "away_bp_eb_xwoba": 0.300,
            "home_bullpen_pitches_prev_3d": 40, "away_bullpen_pitches_prev_3d": 55,
            # directional matchup
            "home_lineup_vs_away_starter_xwoba_adj": 0.02,
            "away_lineup_vs_home_starter_xwoba_adj": -0.01,
            # categoricals
            "home_starter_pitch_archetype": "power", "away_starter_pitch_archetype": "finesse",
            "home_starter_pitcher_hand": "R", "away_starter_pitcher_hand": "L",
            # shared context
            "elevation_ft": 5200, "temp_f": 75.0, "is_day_game": True, "roof_type": "open",
            # a market column that must be ignored entirely by the assembler
            "home_moneyline_american": -150,
        },
        {
            "game_pk": 2, "game_date": "2024-04-03", "game_year": 2024,
            "home_final_score": 2, "away_final_score": 7,
            "home_avg_eb_woba": 0.295, "away_avg_eb_woba": 0.345,
            "home_off_woba_30d": 0.300, "away_off_woba_30d": 0.350,
            "home_starter_eb_xwoba_against": 0.330, "away_starter_eb_xwoba_against": 0.285,
            "home_bp_eb_xwoba": 0.340, "away_bp_eb_xwoba": 0.295,
            "home_bullpen_pitches_prev_3d": 60, "away_bullpen_pitches_prev_3d": 30,
            "home_lineup_vs_away_starter_xwoba_adj": -0.03,
            "away_lineup_vs_home_starter_xwoba_adj": 0.04,
            "home_starter_pitch_archetype": "finesse", "away_starter_pitch_archetype": "power",
            "home_starter_pitcher_hand": "L", "away_starter_pitcher_hand": "R",
            "elevation_ft": 10, "temp_f": 60.0, "is_day_game": False, "roof_type": "dome",
            "home_moneyline_american": 120,
        },
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def assembled():
    df, numeric_cols, cat_cols = build_perside_frame(_wide_frame())
    return df, numeric_cols, cat_cols


class TestShape:
    def test_two_rows_per_game(self, assembled):
        df, _, _ = assembled
        assert len(df) == 4
        assert sorted(df["side"].unique()) == ["away", "home"]
        assert (df.groupby("game_pk").size() == 2).all()

    def test_index_is_reset(self, assembled):
        df, _, _ = assembled
        assert list(df.index) == list(range(len(df)))

    def test_is_home_indicator(self, assembled):
        df, _, _ = assembled
        assert df.loc[df["side"] == "home", "is_home"].eq(1.0).all()
        assert df.loc[df["side"] == "away", "is_home"].eq(0.0).all()


class TestTarget:
    def test_runs_scored_is_that_sides_score(self, assembled):
        df, _, _ = assembled
        g1h = df[(df.game_pk == 1) & (df.side == "home")].iloc[0]
        g1a = df[(df.game_pk == 1) & (df.side == "away")].iloc[0]
        assert g1h["runs_scored"] == 5
        assert g1a["runs_scored"] == 3


class TestSideMapping:
    def test_offence_is_own_side(self, assembled):
        df, _, _ = assembled
        g1h = df[(df.game_pk == 1) & (df.side == "home")].iloc[0]
        g1a = df[(df.game_pk == 1) & (df.side == "away")].iloc[0]
        assert g1h["off_avg_eb_woba"] == pytest.approx(0.330)   # home offence
        assert g1a["off_avg_eb_woba"] == pytest.approx(0.300)   # away offence

    def test_pitching_is_opposing_side(self, assembled):
        df, _, _ = assembled
        g1h = df[(df.game_pk == 1) & (df.side == "home")].iloc[0]
        g1a = df[(df.game_pk == 1) & (df.side == "away")].iloc[0]
        # home batting faces the AWAY starter/bullpen
        assert g1h["opp_starter_eb_xwoba_against"] == pytest.approx(0.290)
        assert g1h["opp_bullpen_pitches_prev_3d"] == pytest.approx(55)
        # away batting faces the HOME starter/bullpen
        assert g1a["opp_starter_eb_xwoba_against"] == pytest.approx(0.310)
        assert g1a["opp_bullpen_pitches_prev_3d"] == pytest.approx(40)

    def test_directional_matchup_resolves_per_side(self, assembled):
        df, _, _ = assembled
        g1h = df[(df.game_pk == 1) & (df.side == "home")].iloc[0]
        g1a = df[(df.game_pk == 1) & (df.side == "away")].iloc[0]
        assert g1h["off_lineup_vs_opp_starter_xwoba_adj"] == pytest.approx(0.02)
        assert g1a["off_lineup_vs_opp_starter_xwoba_adj"] == pytest.approx(-0.01)

    def test_categorical_side_mapping(self, assembled):
        df, _, _ = assembled
        g1h = df[(df.game_pk == 1) & (df.side == "home")].iloc[0]
        # home lineup faces the away starter (finesse, LHP)
        assert g1h["off_starter_pitch_archetype"] == "power"   # the archetype faced (home's own col)
        assert g1h["opp_starter_pitcher_hand"] == "L"          # away starter's hand


class TestSharedContext:
    def test_shared_cols_duplicated_both_sides(self, assembled):
        df, _, _ = assembled
        g1 = df[df.game_pk == 1]
        assert g1["elevation_ft"].nunique() == 1
        assert g1["elevation_ft"].iloc[0] == pytest.approx(5200)
        assert g1["temp_f"].iloc[0] == pytest.approx(75.0)

    def test_bool_shared_cast_to_float(self, assembled):
        df, numeric_cols, _ = assembled
        assert "is_day_game" in numeric_cols
        assert df["is_day_game"].dtype.kind == "f"


class TestMarketBlind:
    def test_no_market_columns_in_feature_lists(self, assembled):
        _, numeric_cols, cat_cols = assembled
        assert find_market_columns(numeric_cols + cat_cols) == []

    def test_market_column_not_carried_through(self, assembled):
        df, _, _ = assembled
        assert not any("moneyline" in c for c in df.columns)
