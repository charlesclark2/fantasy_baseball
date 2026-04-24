import numpy as np
import pandas as pd
import pytest
from betting_ml.utils.preprocessing import (
    bayesian_shrinkage,
    build_imputation_pipeline,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_df(n=50):
    """Minimal synthetic DataFrame with rolling-stat columns and games_played."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "game_year": rng.integers(2019, 2025, n),
            "home_games_played_7d": rng.integers(3, 7, n).astype(float),
            "home_games_played_14d": rng.integers(8, 14, n).astype(float),
            "home_games_played_30d": rng.integers(20, 30, n).astype(float),
            "home_games_played_std": rng.integers(30, 80, n).astype(float),
            "away_games_played_7d": rng.integers(3, 7, n).astype(float),
            "away_games_played_14d": rng.integers(8, 14, n).astype(float),
            "away_games_played_30d": rng.integers(20, 30, n).astype(float),
            "away_games_played_std": rng.integers(30, 80, n).astype(float),
        }
    )


# ---------------------------------------------------------------------------
# bayesian_shrinkage unit tests
# ---------------------------------------------------------------------------

class TestBayesianShrinkage:
    def test_n0_returns_league_mean(self):
        result = bayesian_shrinkage(observed=0.400, league_mean=0.330, n=0)
        assert result == pytest.approx(0.330)

    def test_n_equals_k_gives_midpoint(self):
        result = bayesian_shrinkage(observed=0.400, league_mean=0.300, n=15, k=15)
        # weight = 15/(15+15) = 0.5  →  0.5*0.400 + 0.5*0.300 = 0.350
        assert result == pytest.approx(0.350)

    def test_large_n_approaches_observed(self):
        result = bayesian_shrinkage(observed=0.400, league_mean=0.300, n=10000, k=15)
        assert abs(result - 0.400) < 0.001

    def test_n5_further_from_obs_than_n25(self):
        obs, lm = 0.400, 0.330
        s5 = bayesian_shrinkage(obs, lm, n=5)
        s25 = bayesian_shrinkage(obs, lm, n=25)
        assert abs(s5 - lm) < abs(s25 - lm)

    def test_custom_k(self):
        result = bayesian_shrinkage(observed=0.400, league_mean=0.300, n=10, k=10)
        # weight = 10/(10+10) = 0.5
        assert result == pytest.approx(0.350)


# ---------------------------------------------------------------------------
# Group 1: Starter platoon splits
# ---------------------------------------------------------------------------

class TestPlatoonImputer:
    def test_platoon_nulls_filled(self):
        df = _base_df(40)
        df["home_starter_k_pct_vs_lhb"] = np.where(
            np.arange(40) < 20, np.nan, 0.25
        )
        df["home_starter_k_pct_vs_rhb"] = 0.22
        df["away_starter_k_pct_vs_lhb"] = 0.24
        df["away_starter_k_pct_vs_rhb"] = 0.21
        pipe = build_imputation_pipeline()
        out = pd.DataFrame(pipe.fit_transform(df))
        assert out.isnull().sum().sum() == 0

    def test_has_starter_platoon_data_indicator_present(self):
        df = _base_df(20)
        df["home_starter_k_pct_vs_lhb"] = np.where(
            np.arange(20) < 10, np.nan, 0.25
        )
        df["away_starter_k_pct_vs_lhb"] = 0.24
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert "has_starter_platoon_data" in out.columns

    def test_has_starter_platoon_data_values(self):
        df = _base_df(10)
        df["home_starter_k_pct_vs_lhb"] = [np.nan] * 5 + [0.25] * 5
        df["away_starter_k_pct_vs_lhb"] = 0.24
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        # First 5 rows: home platoon data null → 0; last 5 rows: not null → 1
        assert list(out["has_starter_platoon_data"].iloc[:5]) == [0, 0, 0, 0, 0]
        assert list(out["has_starter_platoon_data"].iloc[5:]) == [1, 1, 1, 1, 1]


# ---------------------------------------------------------------------------
# Group 2: Park run factor cascade
# ---------------------------------------------------------------------------

class TestParkRunFactorImputer:
    def test_3yr_used_when_available(self):
        df = _base_df(5)
        df["runs_per_game_at_park"] = 9.2
        df["park_run_factor_3yr"] = [1.05, 1.10, np.nan, 1.02, np.nan]
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        # Rows 0,1,3 keep their 3yr values; rows 2,4 fall back to 1yr
        assert out["park_run_factor_3yr"].iloc[0] == pytest.approx(1.05)
        assert out["park_run_factor_3yr"].iloc[1] == pytest.approx(1.10)
        assert out["park_run_factor_3yr"].iloc[2] == pytest.approx(9.2)
        assert out["park_run_factor_3yr"].iloc[4] == pytest.approx(9.2)

    def test_fallback_to_league_avg_when_both_null(self):
        df = _base_df(5)
        df["runs_per_game_at_park"] = [9.2, 9.2, np.nan, 9.2, np.nan]
        df["park_run_factor_3yr"] = [1.05, np.nan, np.nan, np.nan, np.nan]
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert out["park_run_factor_3yr"].isnull().sum() == 0
        assert out["runs_per_game_at_park"].isnull().sum() == 0

    def test_is_new_venue_indicator_present(self):
        df = _base_df(10)
        df["runs_per_game_at_park"] = [np.nan] * 5 + [9.2] * 5
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert "is_new_venue" in out.columns
        assert list(out["is_new_venue"].iloc[:5]) == [1, 1, 1, 1, 1]
        assert list(out["is_new_venue"].iloc[5:]) == [0, 0, 0, 0, 0]


# ---------------------------------------------------------------------------
# Group 3: Opening Day win%
# ---------------------------------------------------------------------------

class TestWinPctImputer:
    def test_win_pct_nulls_filled_with_500(self):
        df = _base_df(10)
        df["home_win_pct"] = [np.nan] * 5 + [0.550] * 5
        df["away_win_pct"] = np.nan
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert np.allclose(out["home_win_pct"].iloc[:5].values, 0.500)
        assert np.allclose(out["away_win_pct"].values, 0.500)


# ---------------------------------------------------------------------------
# Group 4: Opening Day days_rest
# ---------------------------------------------------------------------------

class TestDaysRestImputer:
    def test_days_rest_nulls_filled_with_4(self):
        df = _base_df(10)
        df["home_days_rest"] = [np.nan] * 5 + [3.0] * 5
        df["away_days_rest"] = np.nan
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert (out["home_days_rest"].iloc[:5] == 4).all()
        assert (out["away_days_rest"] == 4).all()


# ---------------------------------------------------------------------------
# Group 5: Bullpen xwOBA
# ---------------------------------------------------------------------------

class TestBullpenXwobaImputer:
    def test_bullpen_xwoba_nulls_filled(self):
        df = _base_df(20)
        df["home_bp_xwoba_against_14d"] = [np.nan] * 10 + [0.32] * 10
        df["away_bp_xwoba_against_30d"] = np.nan
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert out["home_bp_xwoba_against_14d"].isnull().sum() == 0
        assert out["away_bp_xwoba_against_30d"].isnull().sum() == 0

    def test_filled_with_training_mean(self):
        df = _base_df(20)
        known_val = 0.350
        df["home_bp_xwoba_against_14d"] = [np.nan] * 10 + [known_val] * 10
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        # Null rows should be filled with mean of known values
        assert out["home_bp_xwoba_against_14d"].iloc[:10].mean() == pytest.approx(
            known_val, abs=0.01
        )


# ---------------------------------------------------------------------------
# Group 6: Bayesian shrinkage on rolling stats
# ---------------------------------------------------------------------------

class TestBayesianShrinkageTransformer:
    def test_rolling_nulls_filled(self):
        df = _base_df(20)
        df["home_off_woba_7d"] = [np.nan] * 10 + [0.330] * 10
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        assert out["home_off_woba_7d"].isnull().sum() == 0

    def test_null_values_get_league_mean(self):
        df = _base_df(20)
        known_mean = 0.330
        df["home_off_woba_7d"] = [np.nan] * 10 + [known_mean] * 10
        # Set games_played to 0 for null rows (will be 7d mean)
        df["home_games_played_7d"] = [0.0] * 10 + [7.0] * 10
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        # The null rows (n=0) should be close to league mean
        null_filled = out["home_off_woba_7d"].iloc[:10]
        assert (abs(null_filled - known_mean) < 0.01).all()

    def test_shrinkage_applied_to_non_null_values(self):
        df = _base_df(20)
        # Half the rows have low values (0.200) to pull the league mean below obs_val.
        # The last row has obs_val=0.400 with n=5, so it should be shrunk toward the mean.
        df["home_off_woba_7d"] = [0.200] * 15 + [0.400] * 5
        df["home_games_played_7d"] = 5.0  # low games → pulled toward mean
        pipe = build_imputation_pipeline()
        out = pipe.fit_transform(df)
        # League mean ≈ 0.250; with n=5, k=15: weight=0.25 → 0.25*0.400 + 0.75*0.250 = 0.2875
        # Result should be less than obs_val (0.400)
        result = out["home_off_woba_7d"].iloc[-1]
        assert result < 0.400  # pulled toward league mean


# ---------------------------------------------------------------------------
# Zero-null guarantee with combined groups
# ---------------------------------------------------------------------------

class TestZeroNullsGuarantee:
    def test_all_groups_combined_zero_nulls(self):
        df = _base_df(30)
        df["home_starter_k_pct_vs_lhb"] = [np.nan] * 15 + [0.25] * 15
        df["away_starter_k_pct_vs_lhb"] = 0.24
        df["runs_per_game_at_park"] = [np.nan] * 5 + [9.2] * 25
        df["park_run_factor_3yr"] = np.nan
        df["home_win_pct"] = [np.nan] * 10 + [0.500] * 20
        df["away_win_pct"] = np.nan
        df["home_days_rest"] = [np.nan] * 10 + [4.0] * 20
        df["home_bp_xwoba_against_14d"] = [np.nan] * 15 + [0.320] * 15
        df["home_off_woba_7d"] = [np.nan] * 10 + [0.330] * 20
        pipe = build_imputation_pipeline()
        out = pd.DataFrame(pipe.fit_transform(df))
        assert out.isnull().sum().sum() == 0
