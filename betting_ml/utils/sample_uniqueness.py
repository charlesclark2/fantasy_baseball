"""sample_uniqueness.py — Epic E1.2: sequential-bootstrap sample-uniqueness weights.

WHY (AFML §4.3–4.5)
-------------------
Games are not i.i.d. A starter's consecutive starts, games within a series, and shared
bullpen state mean overlapping/concurrent information: the feature windows of nearby games
cover the same underlying events. Equal-weighting over-counts those redundant samples, so a
model (and any bootstrap over it) effectively sees the dense, redundant stretches as "more
data" than they are. AFML's fix is to weight each sample by its **average uniqueness** — the
inverse of how many other samples' information windows it shares.

WHAT THIS MODULE PROVIDES
-------------------------
- `compute_sample_uniqueness(game_dates, …)` — per-game `avg_uniqueness ∈ (0, 1]`:
  the mean, over the days in a game's look-back window, of `1 / concurrency(day)` where
  `concurrency(day)` = how many games' windows cover that day. 1.0 = fully unique; small =
  buried in a dense overlapping cluster.
- `attach_sample_uniqueness(df)` — adds the canonical `sample_uniqueness` column so EVERY
  trainer consumes the SAME weights (`sample_weight=` for XGBoost/LightGBM/NGBoost). This is
  the drift-guard analog of `season_normalization`: one canonical definition, one column
  name, a parity test pinning the parameters.
- `sequential_bootstrap(game_dates, …)` — AFML §4.5 sequential bootstrap: draw indices one
  at a time with probability ∝ uniqueness *given the already-drawn set*, so resamples favor
  unique games instead of redundantly re-drawing concurrent ones. For any bagged/ensemble
  CV variant.

CANONICAL PARAMETERS (pin these; the parity test enforces them)
---------------------------------------------------------------
The weight is a deterministic function of `(game_dates, window_days)`. The production
window is `DEFAULT_WINDOW_DAYS` (30) unless a caller passes the model's own max feature
window (from `cv.max_feature_window`) — matching the purge band in E1.1 so weighting and
purging speak the same look-back.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.utils.cv import _as_ordinals, max_feature_window

# Canonical column name + window — keep stable; the parity test pins them.
UNIQUENESS_COLUMN = "sample_uniqueness"
DEFAULT_WINDOW_DAYS = 30


def _resolve_window(
    feature_cols: list[str] | None, window_days: int | None, default: int
) -> int:
    """The single look-back window (days) the uniqueness calc uses. Explicit `window_days`
    wins; else the model's max feature window (so weighting matches the E1.1 purge band);
    else `default`."""
    if window_days is not None:
        return int(window_days)
    if feature_cols:
        return max_feature_window(feature_cols, default=default)
    return int(default)


def _daily_concurrency(ords: np.ndarray, window: int) -> tuple[np.ndarray, int]:
    """Concurrency per day over the full date span via a +1/−1 difference array.

    Returns `(concurrency, base_ord)` where `concurrency[d - base_ord]` = number of game
    windows `[end-window, end]` covering ordinal day `d`. O(N + span).
    """
    valid = ords[np.isfinite(ords)] if ords.dtype.kind == "f" else ords
    base = int(valid.min())
    span = int(valid.max()) - base + 2  # +2 to hold the +window upper sentinel
    diff = np.zeros(span + window + 1, dtype="int64")
    starts = (ords - window) - base
    ends = (ords - base) + 1  # +1 so the cumsum includes the end day itself
    np.add.at(diff, np.clip(starts, 0, span + window), 1)
    np.add.at(diff, np.clip(ends, 0, span + window), -1)
    conc = np.cumsum(diff)
    return conc, base


def compute_sample_uniqueness(
    game_dates,
    *,
    feature_cols: list[str] | None = None,
    window_days: int | None = None,
    default_window: int = DEFAULT_WINDOW_DAYS,
) -> np.ndarray:
    """Per-game average uniqueness `∈ (0, 1]` (AFML §4.3).

    `uniqueness_g = mean_{d ∈ [end_g - W, end_g]} 1 / concurrency(d)`, where the window `W`
    is resolved by `_resolve_window`. A game whose window is shared by many other games
    (dense schedule, same series) gets a small weight; an isolated game gets ≈ 1.0.
    Deterministic and order-preserving (output aligns to the input row order).
    """
    ords = _as_ordinals(pd.Series(game_dates))
    if ords.size == 0:
        return np.zeros(0)
    W = _resolve_window(feature_cols, window_days, default_window)
    conc, base = _daily_concurrency(ords, W)
    inv = 1.0 / np.maximum(conc, 1)            # concurrency ≥ 1 wherever any window covers
    prefix = np.concatenate([[0.0], np.cumsum(inv)])
    # mean of inv over [end-W, end] (inclusive) = (prefix[hi+1] - prefix[lo]) / (W+1)
    lo = np.clip((ords - W) - base, 0, len(inv))
    hi = np.clip((ords - base) + 1, 0, len(inv))   # exclusive upper for the prefix
    seg = prefix[hi] - prefix[lo]
    width = np.maximum(hi - lo, 1)
    u = seg / width
    return np.clip(u, 1e-6, 1.0)


def attach_sample_uniqueness(
    df: pd.DataFrame,
    *,
    feature_cols: list[str] | None = None,
    window_days: int | None = None,
    date_col: str = "game_date",
    column: str = UNIQUENESS_COLUMN,
) -> pd.DataFrame:
    """Return a copy of `df` with the canonical `sample_uniqueness` column added.

    Every trainer should call this (not re-derive weights inline) so the whole stack shares
    one definition — the parity discipline mirrored from `season_normalization`.
    """
    out = df.copy()
    out[column] = compute_sample_uniqueness(
        out[date_col], feature_cols=feature_cols, window_days=window_days
    )
    return out


def sequential_bootstrap(
    game_dates,
    *,
    n_samples: int | None = None,
    feature_cols: list[str] | None = None,
    window_days: int | None = None,
    default_window: int = DEFAULT_WINDOW_DAYS,
    seed: int = 42,
    max_n: int = 20_000,
) -> np.ndarray:
    """AFML §4.5 sequential bootstrap — draw row positions favoring unique samples.

    Draws `n_samples` (default = len) indices WITH replacement, one at a time. At each step
    a candidate `j`'s draw weight is its average uniqueness GIVEN the already-drawn set
    (`mean_{d ∈ window_j} 1 / (1 + concurrency_drawn(d))`), so once a redundant region is
    sampled, its concurrent neighbors become less likely — unlike a plain i.i.d. bootstrap
    which re-draws dense clusters in proportion to their over-representation.

    Vectorized per draw (O(n_samples · (N + span))); `max_n` caps N to bound cost on the
    full training matrix (raises if exceeded — sample upstream or pass a window). Returns an
    int array of selected row positions.
    """
    ords = _as_ordinals(pd.Series(game_dates))
    N = len(ords)
    if N > max_n:
        raise ValueError(
            f"sequential_bootstrap: N={N} exceeds max_n={max_n}; the per-draw cost is "
            f"O(n_samples·N). Subsample rows first or raise max_n deliberately."
        )
    W = _resolve_window(feature_cols, window_days, default_window)
    n_samples = N if n_samples is None else int(n_samples)
    _, base = _daily_concurrency(ords, W)
    span = int(ords.max()) - base + W + 2
    drawn_conc = np.zeros(span + 1, dtype="float64")   # concurrency contributed by draws
    lo = np.clip((ords - W) - base, 0, span)
    hi = np.clip((ords - base) + 1, 0, span)           # exclusive upper

    rng = np.random.default_rng(seed)
    out = np.empty(n_samples, dtype="int64")
    for i in range(n_samples):
        inv = 1.0 / (1.0 + drawn_conc)
        prefix = np.concatenate([[0.0], np.cumsum(inv)])
        avg_u = (prefix[hi] - prefix[lo]) / np.maximum(hi - lo, 1)
        p = avg_u / avg_u.sum()
        j = int(rng.choice(N, p=p))
        out[i] = j
        drawn_conc[lo[j]:hi[j]] += 1.0
    return out
