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
_DAYS_REST_COLS = [
    "home_days_rest",
    "away_days_rest",
    "home_starter_days_rest",
    "away_starter_days_rest",
]
_BULLPEN_XWOBA_PATTERN = "bp_xwoba_against"
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
    """Groups 3 & 4: Fill team win% with 0.500, days_rest with 4."""

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
        return X


class _BullpenXwobaImputer(BaseEstimator, TransformerMixin):
    """Group 5: Fill bullpen xwOBA nulls with training-set mean."""

    def fit(self, X: pd.DataFrame, y=None):
        self._cols = [c for c in X.columns if _BULLPEN_XWOBA_PATTERN in c]
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
    """Build a sklearn Pipeline that handles all six null groups.

    Steps (in order):
      normalize_types  — convert Snowflake Decimal columns to float64
      indicators       — add has_starter_platoon_data and is_new_venue columns
      platoon          — Group 1: starter platoon splits → column mean
      park             — Group 2: park run factor cascade → league avg → 1.000
      constants        — Groups 3 & 4: win% → 0.500; days_rest → 4
      bullpen_xwoba    — Group 5: bullpen xwOBA → training-set mean
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
            ("bayesian", _BayesianShrinkageTransformer(k=k)),
            ("fallback", _FallbackImputer()),
        ]
    )
