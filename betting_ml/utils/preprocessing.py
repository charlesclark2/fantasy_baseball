import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline


class _NumericNormalizer(BaseEstimator, TransformerMixin):
    """Convert Decimal / object-numeric columns to float64.

    Snowflake's connector returns NUMERIC/DECIMAL columns as decimal.Decimal
    objects. This step casts all object-dtype columns that contain numeric
    values to float so downstream arithmetic works correctly.
    """

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in X.columns:
            if X[col].dtype == object:
                converted = pd.to_numeric(X[col], errors="coerce")
                if converted.notna().sum() >= X[col].notna().sum():
                    X[col] = converted
            if pd.api.types.is_numeric_dtype(X[col]) and X[col].dtype != np.float64:
                try:
                    X[col] = X[col].astype(float)
                except Exception:
                    pass
        return X


# Column patterns for null group identification
_PLATOON_SUFFIXES = ("_vs_lhb", "_vs_rhb", "_vs_lhp", "_vs_rhp", "_adj")
_WIN_PCT_COLS = ["home_win_pct", "away_win_pct"]
_PYTHAGOREAN_COLS = ["home_pythagorean_win_exp", "away_pythagorean_win_exp"]
_PYTHAGOREAN_DIFF_COLS = ["pythagorean_win_exp_diff"]
# Card 8.X — pythagorean residual columns. Zero residual = team is winning
# exactly to run-differential expectation, which is the natural prior. NULLs
# come from the 10-game reliability gate (early season).
_PYTHAGOREAN_RESIDUAL_COLS = [
    "home_pythagorean_residual_season",
    "away_pythagorean_residual_season",
    "home_pythagorean_residual_30d",
    "away_pythagorean_residual_30d",
    "pythagorean_residual_diff",
]
_BOOKMAKER_DISAGREEMENT_ZERO_COLS = [
    "ml_implied_prob_std",
    "ml_implied_prob_range",
    "totals_line_std",
    "totals_line_range",
    "sharp_soft_ml_spread",
]
_VELO_DELTA_COLS = [
    "home_starter_velo_delta_3start",
    "away_starter_velo_delta_3start",
]
_DAYS_REST_COLS = [
    "home_days_rest",
    "away_days_rest",
    "home_starter_days_rest",
    "away_starter_days_rest",
]
_BULLPEN_XWOBA_PATTERN = "bp_xwoba_against"
# Patterns for the bullpen state feature table (feature_pregame_bullpen_state_features)
_BULLPEN_STATE_XWOBA_PATTERNS = (
    "bullpen_lhb_xwoba_against",
    "bullpen_rhb_xwoba_against",
    "bullpen_matchup_quality_vs_lineup",
    "home_bp_matchup_xwoba",
    "away_bp_matchup_xwoba",
)
_BULLPEN_STATE_ZERO_COLS = [
    "bullpen_leverage_pitches_prev_1d",
    "bullpen_leverage_pitches_prev_3d",
    "high_leverage_arms_used_prev_2d",
]
_BULLPEN_LEVERAGE_ZERO_COLS = [
    "home_bp_leverage_sum_3d",
    "away_bp_leverage_sum_3d",
    "home_bp_high_lev_appearances_3d",
    "away_bp_high_lev_appearances_3d",
    "home_bp_leverage_sum_1d",
    "away_bp_leverage_sum_1d",
]
# Card 8.J — H2H pitcher-batter matchup. PA coverage = 0 when no historical
# matchup data exists (debut starters). wOBA/xwOBA priors ≈ league average.
_H2H_PA_COVERAGE_COLS = [
    "home_lineup_h2h_pa_coverage",
    "away_lineup_h2h_pa_coverage",
]
_H2H_WOBA_PRIOR = 0.320
_H2H_WOBA_COLS = [
    "home_lineup_vs_away_starter_h2h_woba",
    "home_lineup_vs_away_starter_h2h_xwoba",
    "away_lineup_vs_home_starter_h2h_woba",
    "away_lineup_vs_home_starter_h2h_xwoba",
]
# Card 8.R — public betting. Neutral prior: 50/50 money-ticket split; no sharp
# signal (difference = 0). Used when no Action Network data is available.
_PUBLIC_BETTING_NEUTRAL_50_COLS = [
    "home_ml_money_pct",
    "home_ml_ticket_pct",
    "over_money_pct",
    "over_ticket_pct",
]
_PUBLIC_BETTING_ZERO_COLS = [
    "ml_sharp_signal",
    "total_sharp_signal",
]
# Card 8.W — masked public betting variants. Computed in dbt as COALESCE(col, 0),
# so they are never null in practice. Zero-fill here is a safety net only.
_PUBLIC_BETTING_ACTIVE_COLS = [
    "home_ml_money_pct_active",
    "home_ml_ticket_pct_active",
    "over_money_pct_active",
    "over_ticket_pct_active",
    "ml_sharp_signal_active",
    "total_sharp_signal_active",
]
# CSW% league average (~28.5% across 2023–2025 starters).
# Applied to debut starters with no prior starts.
CSW_LEAGUE_AVG = 0.285
_CSW_COLS = [
    "home_starter_csw_pct_3start",
    "home_starter_csw_pct_season",
    "away_starter_csw_pct_3start",
    "away_starter_csw_pct_season",
]
# Bat tracking matchup features (Card 8.E). League-average values measured
# from populated 2024–2026 rows in feature_pregame_game_features.
# Applied to pre-2023-07-14 rows (no Hawk-Eye coverage) and opening-day
# starters with no avg_fastball_velo_7d populated yet.
_BAT_TRACKING_FILLS = {
    "home_lineup_avg_bat_speed": 69.6,
    "away_lineup_avg_bat_speed": 69.6,
    "home_lineup_avg_swing_length": 7.2,
    "away_lineup_avg_swing_length": 7.2,
    "home_lineup_avg_attack_angle": 9.1,
    "away_lineup_avg_attack_angle": 9.1,
    "home_lineup_bat_speed_vs_starter_velo": 0.747,
    "away_lineup_bat_speed_vs_starter_velo": 0.747,
}
# Card 8.Y — base-state-split priors. Applied when the trailing 30-day window
# carries fewer than 50 PAs with runners on (early-season noise floor).
# Priors are slightly elevated vs. league wOBA (~0.320) — pitchers pitch
# carefully with traffic, so league average wOBA-with-runners-on sits above
# unconditional league wOBA. Defensive priors mirror offensive ones.
_BASE_STATE_FILLS = {
    "home_woba_with_runners_on_30d":            0.330,
    "away_woba_with_runners_on_30d":            0.330,
    "home_xwoba_with_runners_on_30d":           0.325,
    "away_xwoba_with_runners_on_30d":           0.325,
    "home_woba_with_risp_30d":                  0.335,
    "away_woba_with_risp_30d":                  0.335,
    "home_xwoba_with_risp_30d":                 0.325,
    "away_xwoba_with_risp_30d":                 0.325,
    "home_runs_per_baserunner_30d":             0.25,
    "away_runs_per_baserunner_30d":             0.25,
    "home_woba_against_with_runners_on_30d":    0.330,
    "away_woba_against_with_runners_on_30d":    0.330,
    "home_woba_against_with_risp_30d":          0.335,
    "away_woba_against_with_risp_30d":          0.335,
}
_ROLLING_SUFFIXES = ("_7d", "_14d", "_30d", "_std")
_GAMES_PLAYED_COLS = {
    "_7d": ("home_games_played_7d", "away_games_played_7d"),
    "_14d": ("home_games_played_14d", "away_games_played_14d"),
    "_30d": ("home_games_played_30d", "away_games_played_30d"),
    "_std": ("home_games_played_std", "away_games_played_std"),
}

# Columns that hold games-played counts (not stats to be shrunk)
_GAMES_PLAYED_COL_NAMES = frozenset(
    col
    for pair in _GAMES_PLAYED_COLS.values()
    for col in pair
)


def bayesian_shrinkage(
    observed: float, league_mean: float, n: int, k: int = 15
) -> float:
    """Compute Bayesian shrinkage estimate.

    weight = n / (n + k)
    result = weight * observed + (1 - weight) * league_mean
    """
    weight = n / (n + k)
    return weight * observed + (1 - weight) * league_mean


class _AddIndicators(BaseEstimator, TransformerMixin):
    """Add has_starter_platoon_data and is_new_venue indicator columns."""

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        platoon_ref = "home_starter_k_pct_vs_lhb"
        if platoon_ref in X.columns:
            away_ref = "away_starter_k_pct_vs_lhb"
            home_ok = X[platoon_ref].notna()
            away_ok = X[away_ref].notna() if away_ref in X.columns else home_ok
            X["has_starter_platoon_data"] = (home_ok & away_ok).astype(int)
        else:
            X["has_starter_platoon_data"] = 0

        park_ref = "runs_per_game_at_park"
        if park_ref in X.columns:
            X["is_new_venue"] = X[park_ref].isna().astype(int)
        else:
            X["is_new_venue"] = 0

        return X


class _PlatoonImputer(BaseEstimator, TransformerMixin):
    """Group 1: Fill starter platoon split nulls with training-set column mean.

    Grouped-by-pitcher_hand imputation is approximated by overall column mean
    because pitcher_hand is a categorical identifier not always present.
    """

    def fit(self, X: pd.DataFrame, y=None):
        self._cols = [
            c for c in X.columns if any(c.endswith(s) for s in _PLATOON_SUFFIXES)
        ]
        self._means = {
            c: (X[c].mean() if X[c].notna().any() else 0.0) for c in self._cols
        }
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in self._cols:
            if col in X.columns:
                fill = self._means.get(col, 0.0)
                X[col] = X[col].fillna(fill if not pd.isna(fill) else 0.0)
        return X


class _ParkRunFactorImputer(BaseEstimator, TransformerMixin):
    """Group 2: Cascade park_run_factor_3yr → runs_per_game_at_park → 1.000."""

    def fit(self, X: pd.DataFrame, y=None):
        park_col = "runs_per_game_at_park"
        if park_col in X.columns:
            m = X[park_col].mean()
            self._league_avg = m if not pd.isna(m) else 1.0
        else:
            self._league_avg = 1.0
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        col_3yr = "park_run_factor_3yr"
        col_1yr = "runs_per_game_at_park"
        if col_3yr in X.columns and col_1yr in X.columns:
            X[col_3yr] = X[col_3yr].fillna(X[col_1yr]).fillna(self._league_avg)
            X[col_1yr] = X[col_1yr].fillna(self._league_avg)
        elif col_3yr in X.columns:
            X[col_3yr] = X[col_3yr].fillna(self._league_avg)
        elif col_1yr in X.columns:
            X[col_1yr] = X[col_1yr].fillna(self._league_avg)
        return X


class _ConstantImputer(BaseEstimator, TransformerMixin):
    """Groups 3, 4 & 5: Fill team win% with 0.500, days_rest with 4,
    Pythagorean win expectation with 0.5, and Pythagorean diff with 0.0."""

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in _WIN_PCT_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.500)
        for col in _DAYS_REST_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(4)
        for col in _PYTHAGOREAN_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.500)
        for col in _PYTHAGOREAN_DIFF_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Card 8.X — pythagorean residual columns: zero residual = exactly
        # to expectation (the natural prior).
        for col in _PYTHAGOREAN_RESIDUAL_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        for col in _VELO_DELTA_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Bookmaker disagreement features (Card 8.T): no morning odds = no
        # disagreement signal, so impute dispersion metrics to 0.0 and counts
        # to their single-book defaults.
        for col in _BOOKMAKER_DISAGREEMENT_ZERO_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        if "n_books_available" in X.columns:
            X["n_books_available"] = X["n_books_available"].fillna(1)
        if "stale_book_flag" in X.columns:
            X["stale_book_flag"] = X["stale_book_flag"].fillna(0)
        # Bullpen state workload columns: no usage = 0 pitches
        for col in _BULLPEN_STATE_ZERO_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Bullpen leverage exhaustion columns (Card 8.U): no appearances = 0.0
        for col in _BULLPEN_LEVERAGE_ZERO_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # closer_availability_proxy: null means unknown → assume available (1)
        if "closer_availability_proxy" in X.columns:
            X["closer_availability_proxy"] = X["closer_availability_proxy"].fillna(1)
        # Card 8.J H2H pa_coverage: 0 = no historical matchup data (debut starters)
        for col in _H2H_PA_COVERAGE_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Card 8.J H2H wOBA/xwOBA: league-average prior when no matchup history
        for col in _H2H_WOBA_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(_H2H_WOBA_PRIOR)
        # Card 8.R public betting: neutral 50/50 split when no Action Network data
        for col in _PUBLIC_BETTING_NEUTRAL_50_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(50.0)
        # Card 8.R sharp signal: 0.0 = no money/ticket divergence detected
        for col in _PUBLIC_BETTING_ZERO_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Card 8.W masked public betting variants: 0 = no data era (dbt COALESCE
        # already handles this; zero-fill here is a safety net only)
        for col in _PUBLIC_BETTING_ACTIVE_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(0.0)
        # Card 8.W era indicator: 0 = no Action Network coverage for this game
        if "has_public_betting_data" in X.columns:
            X["has_public_betting_data"] = X["has_public_betting_data"].fillna(0)
        return X


class _BullpenXwobaImputer(BaseEstimator, TransformerMixin):
    """Group 5: Fill bullpen xwOBA nulls with training-set mean."""

    def fit(self, X: pd.DataFrame, y=None):
        self._cols = [
            c for c in X.columns
            if _BULLPEN_XWOBA_PATTERN in c
            or any(c == pat for pat in _BULLPEN_STATE_XWOBA_PATTERNS)
        ]
        self._means = {
            c: (X[c].mean() if X[c].notna().any() else 0.310) for c in self._cols
        }
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in self._cols:
            if col in X.columns:
                fill = self._means.get(col, 0.310)
                X[col] = X[col].fillna(fill if not pd.isna(fill) else 0.310)
        return X


class _BayesianShrinkageTransformer(BaseEstimator, TransformerMixin):
    """Group 6: Apply Bayesian shrinkage to rolling stat columns.

    For null stat values the games_played count is treated as 0, so the
    imputed value equals the league mean from the training set.
    """

    def __init__(self, k: int = 15):
        self.k = k

    def fit(self, X: pd.DataFrame, y=None):
        # Pair each rolling stat column with its games_played counterpart
        self._pairs = []
        for col in X.columns:
            if col in _GAMES_PLAYED_COL_NAMES:
                continue
            for suffix, (home_n, away_n) in _GAMES_PLAYED_COLS.items():
                if col.endswith(suffix):
                    n_col = home_n if col.startswith("home_") else away_n
                    if n_col in X.columns:
                        self._pairs.append((col, n_col))
                    break

        self._league_means = {
            col: (X[col].mean() if X[col].notna().any() else 0.0)
            for col, _ in self._pairs
        }
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for stat_col, n_col in self._pairs:
            if stat_col not in X.columns:
                continue
            league_mean = self._league_means.get(stat_col, 0.0)
            if pd.isna(league_mean):
                league_mean = 0.0

            stat_series = X[stat_col]
            n_series = (
                X[n_col].fillna(0).clip(lower=0).astype(float)
                if n_col in X.columns
                else pd.Series(0.0, index=X.index)
            )

            # When stat is null, treat n as 0 (opening day / no window data)
            n_adj = n_series.where(stat_series.notna(), other=0.0)
            weight = n_adj / (n_adj + self.k)
            X[stat_col] = (
                weight * stat_series.fillna(league_mean)
                + (1 - weight) * league_mean
            )
        return X


class _CSWImputer(BaseEstimator, TransformerMixin):
    """Impute CSW% columns with league-average (0.285) for debut starters."""

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col in _CSW_COLS:
            if col in X.columns:
                X[col] = X[col].fillna(CSW_LEAGUE_AVG)
        return X


class _BatTrackingImputer(BaseEstimator, TransformerMixin):
    """Impute bat tracking matchup columns with league-average values for
    pre-Hawk-Eye-coverage rows (pre-2023-07-14) and opening-day starters."""

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col, fill in _BAT_TRACKING_FILLS.items():
            if col in X.columns:
                X[col] = X[col].fillna(fill)
        return X


class _BaseStateSplitImputer(BaseEstimator, TransformerMixin):
    """Card 8.Y. Fill base-state-split columns with per-column league-average
    priors when the trailing 30-day window had fewer than 50 PAs with runners
    on (early-season noise floor)."""

    def fit(self, X: pd.DataFrame, y=None):
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col, fill in _BASE_STATE_FILLS.items():
            if col in X.columns:
                X[col] = X[col].fillna(fill)
        return X


class _FallbackImputer(BaseEstimator, TransformerMixin):
    """Final fallback: fill any remaining nulls (numeric → mean, object → mode)."""

    def fit(self, X: pd.DataFrame, y=None):
        self._numeric_fills = {}
        self._object_fills = {}
        for col in X.columns:
            if pd.api.types.is_numeric_dtype(X[col]):
                m = X[col].mean()
                self._numeric_fills[col] = m if not pd.isna(m) else 0.0
            else:
                mode_vals = X[col].mode()
                self._object_fills[col] = mode_vals.iloc[0] if len(mode_vals) > 0 else "UNKNOWN"
        self.is_fitted_ = True
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        X = X.copy()
        for col, fill in self._numeric_fills.items():
            if col in X.columns and X[col].isna().any():
                X[col] = X[col].fillna(fill)
        for col, fill in self._object_fills.items():
            if col in X.columns and X[col].isna().any():
                X[col] = X[col].fillna(fill)
        return X


def build_imputation_pipeline(k: int = 15) -> Pipeline:
    """Build a sklearn Pipeline that handles all null groups.

    Steps (in order):
      normalize_types  — convert Snowflake Decimal columns to float64
      indicators       — add has_starter_platoon_data and is_new_venue columns
      platoon          — Group 1: starter platoon splits → column mean
      park             — Group 2: park run factor cascade → league avg → 1.000
      constants        — Groups 3 & 4: win% → 0.500; days_rest → 4; pythagorean → 0.5 / 0.0
      bullpen_xwoba    — Group 5: bullpen xwOBA → training-set mean
      csw              — CSW% columns → league-average 0.285 (Card 8.Q)
      bat_tracking     — bat tracking matchup columns → league avgs (Card 8.E)
      base_state       — base-state-split columns → per-column priors (Card 8.Y)
      bayesian         — Group 6: rolling stats → Bayesian shrinkage
      fallback         — catch-all mean/mode fill for any remaining nulls
    """
    return Pipeline(
        steps=[
            ("normalize_types", _NumericNormalizer()),
            ("indicators", _AddIndicators()),
            ("platoon", _PlatoonImputer()),
            ("park", _ParkRunFactorImputer()),
            ("constants", _ConstantImputer()),
            ("bullpen_xwoba", _BullpenXwobaImputer()),
            ("csw", _CSWImputer()),
            ("bat_tracking", _BatTrackingImputer()),
            ("base_state", _BaseStateSplitImputer()),
            ("bayesian", _BayesianShrinkageTransformer(k=k)),
            ("fallback", _FallbackImputer()),
        ]
    )
