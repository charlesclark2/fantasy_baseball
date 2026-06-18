"""run_env_regime.py — Story E1.6: cross-era run-environment regime weighting (soft).

WHY (discovered during E1.3/E1.5, 2026-06-17)
---------------------------------------------
Training is floored at 2021 in `load_features`, but the feature mart is populated back to
2015 and the E1.3 prune showed the slim signal features (bullpen EB quality, park, record,
offense) reach back to 2016. So ~2× more history is available — IF the older seasons share
the current run-environment regime. They don't all: a 2-D regime read (scoring LEVEL +
game-total SPREAD) ranks 2016 (dist 0.35) and 2018 (0.64) as CLOSER to the current 2024–26
regime than 2023 (1.67, already trained on) or 2019 (3.88, peak juiced ball). **Run-environment
regime is NOT time-ordered**, so the right move is to weight games by regime similarity, not
to pick a cutoff year.

WHAT THIS PROVIDES
------------------
- `season_regime_profile(df)` — per-season league run-environment vector: scoring LEVEL
  (mean game total), SPREAD (std of game totals — the totals variance axis), plus any extra
  league aggregates passed in (e.g. a league-xwOBA contact proxy → the contact→runs
  CONVERSION axis where the 2025 over-bias lived, Story 27.6).
- `compute_regime_weights(game_dates, …, target_season=Y)` — a per-GAME weight ∈ (0,1]:
  a Gaussian kernel on the standardized regime distance between each game's season and the
  **trailing** centroid of the seasons just before `Y` (leakage-safe: the regime known at
  training time, never the eval season itself). Off-regime seasons (2019) get ~0.1; on-regime
  seasons (2016/2018/the recent past) get ~1.0.
- Plugs into the **E1.2 `sample_weight` slot** and MULTIPLIES with `compute_sample_uniqueness`
  (regime × uniqueness). Canonical column + drift discipline mirror `season_normalization`.

LEAKAGE NOTE
------------
The centroid for eval season `Y` uses only seasons `[Y-trailing, Y-1]` — the regime you
actually know at training/deployment time. (Standardization uses the full profiled span's
mean/sd as a fixed scale; that is a league-level normalization constant, not per-game target
information.) This mirrors deployment: predicting 2026, you know the 2024–25 regime, not 2026's.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.utils.cv import _as_ordinals

# Canonical column + kernel defaults — pin these; the parity test references them.
REGIME_WEIGHT_COLUMN = "regime_weight"
# Gaussian kernel width (standardized-distance units). 1.5 (not 1.0): a trailing 2-season
# centroid wobbles with normal year-to-year SPREAD variation, and a tight kernel then crushes
# the very recent seasons that DEFINE the current regime (observed 2026-06-17: bw=1.0 sent
# 2024/2025 to 0.25–0.50). 1.5 keeps recent + on-regime seasons high while still flooring a
# genuinely off-regime season (2019 peak juiced ball → ~0.05).
DEFAULT_BANDWIDTH = 1.5
DEFAULT_TRAILING_SEASONS = 2     # seasons before the target that define the "current" regime
MIN_WEIGHT = 0.05                # floor so no season is fully zeroed out (keeps some coverage)

# The regime DISTANCE is computed on run-environment LEVEL + SPREAD only. The contact→runs
# CONVERSION axis (league xwOBA) is deliberately EXCLUDED from the weight: it is the noisiest
# season-to-season axis (2025's xwOBA spike is the Story-27.6 conversion anomaly) and, more
# importantly, that regime is ALREADY corrected at the feature level by season-normalization
# (Story 27.7) — folding it into the sample weight too would double-count and destabilize the
# centroid. Profilers may still REPORT contact as informational context.
WEIGHT_DIMS = ["avg_total_runs", "std_total_runs"]

# The default regime dimensions derived from game outcomes (always available).
LEVEL_DIM = "avg_total_runs"
SPREAD_DIM = "std_total_runs"


def season_regime_profile(
    df: pd.DataFrame,
    *,
    season_col: str = "game_year",
    total_runs_col: str = "total_runs",
    contact_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Per-season league run-environment profile (index = season).

    Always emits LEVEL (`avg_total_runs`) and SPREAD (`std_total_runs`) from the game totals.
    Each name in `contact_cols` (e.g. a league-xwOBA column present in the frame) is averaged
    per season and added as `avg_<col>` — the contact→runs conversion axis. Seasons with too
    few games to estimate a spread are dropped.
    """
    if total_runs_col not in df.columns:
        raise KeyError(f"{total_runs_col!r} not in frame; cannot profile run environment")
    g = df.groupby(season_col)
    prof = pd.DataFrame({
        LEVEL_DIM: g[total_runs_col].mean(),
        SPREAD_DIM: g[total_runs_col].std(),
    })
    for c in (contact_cols or []):
        if c in df.columns:
            prof[f"avg_{c}"] = g[c].mean()
    prof = prof.dropna()
    prof.index = prof.index.astype(int)
    return prof.sort_index()


def _standardize(profile: pd.DataFrame) -> pd.DataFrame:
    """Z-score each regime dimension across seasons so distances are in comparable units."""
    mu = profile.mean(axis=0)
    sd = profile.std(axis=0).replace(0.0, 1.0)
    return (profile - mu) / sd


def trailing_centroid(
    zprofile: pd.DataFrame, target_season: int, *, trailing: int = DEFAULT_TRAILING_SEASONS
) -> np.ndarray:
    """Standardized regime vector of the 'current' regime for `target_season`: the mean over
    the `trailing` seasons immediately BEFORE it (leakage-safe). Falls back to all prior
    seasons if fewer exist, and to the target season itself only if none precede it."""
    prior = [s for s in zprofile.index if s < target_season]
    use = prior[-trailing:] if len(prior) >= 1 else [s for s in zprofile.index if s == target_season]
    if not use:  # target_season not in profile and nothing prior — use the whole span
        use = list(zprofile.index)
    return zprofile.loc[use].mean(axis=0).to_numpy()


def regime_distances(zprofile: pd.DataFrame, centroid: np.ndarray) -> pd.Series:
    """Euclidean distance per season from `centroid` (standardized units)."""
    diff = zprofile.to_numpy() - centroid[None, :]
    return pd.Series(np.sqrt((diff ** 2).sum(axis=1)), index=zprofile.index, name="regime_dist")


def _weight_frame(profile: pd.DataFrame, weight_dims) -> pd.DataFrame:
    """Restrict a (possibly contact-carrying) profile to the columns that enter the regime
    distance. Falls back to all columns if none of `weight_dims` are present."""
    if weight_dims is None:
        return profile
    cols = [c for c in weight_dims if c in profile.columns]
    return profile[cols] if cols else profile


def season_regime_weights(
    profile: pd.DataFrame,
    target_season: int,
    *,
    trailing: int = DEFAULT_TRAILING_SEASONS,
    bandwidth: float = DEFAULT_BANDWIDTH,
    min_weight: float = MIN_WEIGHT,
    weight_dims=WEIGHT_DIMS,
) -> pd.Series:
    """Per-season similarity weight ∈ [min_weight, 1] toward `target_season`'s trailing
    regime. Gaussian kernel `exp(-½ (dist/bandwidth)²)`, normalized so the closest season = 1,
    floored at `min_weight` (so an off-regime season is down-weighted, not deleted). The
    distance uses `weight_dims` only (default: LEVEL + SPREAD — contact is excluded; see
    WEIGHT_DIMS)."""
    z = _standardize(_weight_frame(profile, weight_dims))
    centroid = trailing_centroid(z, target_season, trailing=trailing)
    dist = regime_distances(z, centroid)
    w = np.exp(-0.5 * (dist / bandwidth) ** 2)
    w = w / w.max() if w.max() > 0 else w
    w = np.clip(w, min_weight, 1.0)
    return pd.Series(w, index=profile.index, name="regime_weight")


def compute_regime_weights(
    game_dates,
    *,
    target_season: int,
    profile: pd.DataFrame | None = None,
    df: pd.DataFrame | None = None,
    season_of=None,
    trailing: int = DEFAULT_TRAILING_SEASONS,
    bandwidth: float = DEFAULT_BANDWIDTH,
    min_weight: float = MIN_WEIGHT,
    contact_cols: list[str] | None = None,
) -> np.ndarray:
    """Per-GAME regime-similarity weight for training rows, toward `target_season`.

    Provide the season profile directly (`profile`, preferred — compute it ONCE per gate run)
    or a frame `df` to build it from. Each game's weight = its season's
    `season_regime_weights` value; `season_of` maps a date to its season (defaults to the
    calendar year of `game_dates`). Returns an array aligned to `game_dates`.
    """
    if profile is None:
        if df is None:
            raise ValueError("compute_regime_weights needs either `profile` or `df`")
        profile = season_regime_profile(df, contact_cols=contact_cols)
    wk = season_regime_weights(profile, target_season, trailing=trailing,
                               bandwidth=bandwidth, min_weight=min_weight)
    if season_of is not None:
        seasons = np.asarray([season_of(d) for d in game_dates], dtype="int64")
    else:
        # calendar year from the date ordinals (robust to date/str/Timestamp inputs)
        seasons = pd.to_datetime(pd.Series(game_dates)).dt.year.to_numpy()
    wmap = wk.to_dict()
    default = float(wk.min()) if len(wk) else 1.0
    return np.array([wmap.get(int(s), default) for s in seasons], dtype="float64")


def attach_regime_weight(
    df: pd.DataFrame,
    target_season: int,
    *,
    season_col: str = "game_year",
    column: str = REGIME_WEIGHT_COLUMN,
    trailing: int = DEFAULT_TRAILING_SEASONS,
    bandwidth: float = DEFAULT_BANDWIDTH,
    contact_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Return a copy of `df` with the canonical `regime_weight` column toward `target_season`.
    One canonical definition for every consumer (the parity discipline from
    `season_normalization`)."""
    out = df.copy()
    profile = season_regime_profile(df, season_col=season_col, contact_cols=contact_cols)
    wk = season_regime_weights(profile, target_season, trailing=trailing, bandwidth=bandwidth)
    out[column] = out[season_col].astype(int).map(wk.to_dict()).fillna(float(wk.min()))
    return out
