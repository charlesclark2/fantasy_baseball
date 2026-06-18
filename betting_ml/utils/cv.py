"""cv.py — Epic E1.1: Purged & embargoed walk-forward cross-validation.

WHY THIS EXISTS (AFML ch. 7)
---------------------------
Our rolling features (`*_7d/_14d/_30d`, `mart_team_rolling_*`, `mart_bullpen_*`) make a
test-day game's feature vector a function of the SAME recent games whose outcomes appear
as TRAINING LABELS in the immediately-preceding window. A plain season walk-forward
(`cv_splits.all_season_splits`) trains on every prior season and evaluates on the next, so
the games in the last ~30 days of the season just before the test fold are BOTH:
  - training labels (we fit on their realized outcome), and
  - ingredients of the test-fold games' rolling features.
That near-boundary overlap leaks information across the fold edge and inflates CV optimism.

THE FIX
-------
`PurgedWalkForwardSplit` keeps the season-forward outer loop (no future leakage — we never
train on a season ≥ the eval season) and additionally:

  * **Purge** — drop training samples whose information window overlaps the test fold's
    information window. In forward CV this is the band of `purge_days` immediately BEFORE
    the eval season starts (those late prior-season games feed the early eval games'
    rolling features). `purge_days` is **feature-aware**: it is the longest look-back used
    by the model's own feature columns (the window registry below), not a blanket 30d.
  * **Embargo** — additionally drop training samples within `embargo_days` AFTER the test
    fold (default 3d). In pure forward CV the test fold is the latest data so the embargo
    band is usually empty, but it is applied for correctness and for any future
    interleaved/k-fold use (kills leakage from autocorrelated state — bullpen, streaks).

A purged split is a STRICT SUBSET of the corresponding `all_season_splits` fold (same
eval_idx, train_idx with the boundary band removed), so it is value-preserving: it can only
*remove* leaking training rows, never add or relabel any. The size of the metric change when
a champion is re-scored under it is the **leakage estimate** (Story E1.5).

THE LEAKAGE DIRECTION (important, documented on purpose)
--------------------------------------------------------
The implementation guide phrases purge as "drop training samples whose feature look-back
window overlaps [test_start, test_end]." Read literally in a *forward* split that band is
empty — every training game predates the test fold, so its backward-looking window cannot
reach forward into the test season. The real, asymmetric leak is the REVERSE: the test
games' backward windows reach into the late-prior-season training games. `_purge_band`
implements the AFML-correct symmetric overlap test, which in forward CV reduces to dropping
the `purge_days` band before `test_start`. See `_purge_band` for the exact predicate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Generator, Iterable

import numpy as np
import pandas as pd

from betting_ml.utils.cv_splits import all_season_splits

# ── Per-feature look-back window registry ────────────────────────────────────
# Purge length must be feature-aware (spec E1.1): a model that only uses 7d rolling
# features should purge a 7d boundary band; one using 30d features needs 30d. We derive
# each feature's window from its NAME — the project's columns encode the rolling window as
# a suffix (`_1d`/`_2d`/`_3d`/`_7d`/`_14d`/`_30d`). Anything without a parseable DAY window
# (season-cumulative, EB posteriors, static park geom, identifiers) falls back to
# `default_days`.
#
# DELIBERATELY NOT a rolling window: multi-year aggregates like `park_run_factor_3yr` and
# `home_win_rate_trailing_3yr` (a `_Nyr` token). These are slow, near-static covariates, NOT
# per-game recent-form windows — the boundary leakage E1 targets comes from a test game's
# rolling form being built from the prior-season tail it trained on, which a 3-year park
# constant does not create. Treating `_3yr` as a 1095-day window would purge ~3 entire
# seasons and EMPTY the earliest fold's training set (observed 2026-06-17). So `_Nyr` returns
# the default day-window, and `DEFAULT_MAX_PURGE_DAYS` caps the band defensively against any
# future pathological large `_Nd`.

FEATURE_WINDOW_DEFAULT_DAYS = 30   # the documented blanket the registry refines per feature
DEFAULT_MAX_PURGE_DAYS = 120       # safety cap: genuine rolling windows top out at 30d here
_WINDOW_DAYS_RE = re.compile(r"_(\d+)\s*d(?:ays?)?(?:_|$)")


def feature_window_days(col: str, default: int = FEATURE_WINDOW_DEFAULT_DAYS) -> int:
    """Rolling look-back length (in days) implied by a feature column's NAME.

    Parses a trailing DAY-window token: `_7d` → 7, `_30d` → 30. Multi-year aggregates
    (`_3yr`) and columns with no parseable rolling window (e.g. `home_bp_eb_xwoba`,
    `elevation_ft`) return `default` — they are not per-game recent-form windows and must not
    inflate the purge band (see the module comment above). Used to size the purge band
    feature-aware rather than a blanket 30d.
    """
    md = _WINDOW_DAYS_RE.search(col)
    if md:
        return int(md.group(1))
    return int(default)


def max_feature_window(
    feature_cols: Iterable[str],
    *,
    default: int = FEATURE_WINDOW_DEFAULT_DAYS,
    cap: int | None = None,
) -> int:
    """Longest rolling look-back window across `feature_cols` — the purge band length.

    `cap` (days) bounds the band so a single pathological feature can't purge an unreasonable
    slice of training history (the leakage E1 targets is the rolling near-boundary overlap;
    full-season purging would gut the train set for little gain). With no feature list,
    returns `default`.
    """
    cols = list(feature_cols or [])
    if not cols:
        w = int(default)
    else:
        w = max(feature_window_days(c, default=default) for c in cols)
    if cap is not None:
        w = min(w, int(cap))
    return int(w)


# ── Date helpers ─────────────────────────────────────────────────────────────

def _as_ordinals(dates: pd.Series) -> np.ndarray:
    """Day-ordinal (days since epoch) for a date/datetime/'YYYY-MM-DD' string column.

    Robust to the loader returning game_date as a python date, a pandas Timestamp, or an
    ISO string (Snowflake DATE arrives as any of these depending on the path).
    """
    dt = pd.to_datetime(dates, errors="coerce")
    # int64 ns → days; NaT becomes a large negative we never match in a band.
    ns = dt.to_numpy(dtype="datetime64[ns]").astype("int64")
    return ns // (86_400 * 1_000_000_000)


@dataclass
class FoldPurgeStats:
    """How much a single fold's training set was trimmed by purge + embargo."""
    eval_year: int
    purge_days: int
    embargo_days: int
    n_train_raw: int
    n_train_purged: int
    n_eval: int
    test_start: str
    test_end: str

    @property
    def n_dropped(self) -> int:
        return self.n_train_raw - self.n_train_purged

    @property
    def frac_dropped(self) -> float:
        return self.n_dropped / self.n_train_raw if self.n_train_raw else 0.0


@dataclass
class PurgedWalkForwardSplit:
    """Forward-chained, purged + embargoed season walk-forward splitter.

    Drop-in for `cv_splits.all_season_splits`: `.split(df)` yields `(train_idx, eval_idx)`
    pandas Index pairs in ascending eval-year order, identical eval folds, with the
    boundary-leaking training band removed.

    Parameters
    ----------
    min_train_seasons : same season-count floor as `all_season_splits` (default 3).
    embargo_days : days AFTER the test fold to drop from training (default 3).
    purge_days : explicit purge band (days before the test fold). If None (default), it is
        derived per fold from `feature_cols` via `max_feature_window` (feature-aware); if
        `feature_cols` is also None it falls back to `default_lookback_days`.
    default_lookback_days : the blanket window when a feature list is unavailable (30d).
    max_purge_days : safety cap on the feature-derived band (None = uncapped).
    date_col / year_col : column names (defaults match the project's training surface).
    """
    min_train_seasons: int = 3
    embargo_days: int = 3
    purge_days: int | None = None
    default_lookback_days: int = FEATURE_WINDOW_DEFAULT_DAYS
    max_purge_days: int | None = DEFAULT_MAX_PURGE_DAYS
    date_col: str = "game_date"
    year_col: str = "game_year"
    last_stats: list[FoldPurgeStats] = field(default_factory=list)

    def _purge_days_for(self, feature_cols: Iterable[str] | None) -> int:
        if self.purge_days is not None:
            return int(self.purge_days)
        if feature_cols:
            return max_feature_window(
                feature_cols, default=self.default_lookback_days, cap=self.max_purge_days
            )
        d = int(self.default_lookback_days)
        return min(d, self.max_purge_days) if self.max_purge_days is not None else d

    def _purge_band(
        self, ords: np.ndarray, train_idx: pd.Index, eval_idx: pd.Index, purge_days: int
    ) -> pd.Index:
        """Return the train subset with the purge + embargo band removed.

        The purge band is anchored to the LAST training game-date, not to `test_start`.
        This is the key adaptation for SEASON-forward CV with an offseason gap. The eval
        season's early games carry forward rolling features computed from the games in the
        window ending at each game — but across the offseason the most recent ACTUAL games
        are the *prior season's final games* (data_loader carries the last value forward).
        So a calendar band before `test_start` (April) would land in the offseason and
        purge nothing, while the real leak is the prior season's TAIL feeding those
        carried-forward features. Dropping training rows within `purge_days` of the last
        training game removes exactly that tail. When folds are sub-season (no offseason
        gap) `max_train_ord` sits just before `test_start`, so this reduces to the plain
        AFML `[test_start - purge_days, …]` band. The embargo additionally drops a
        `embargo_days` band AFTER the test fold (empty in pure forward CV; applied for
        interleaved/k-fold generality).
        """
        pos_train = df_positions(train_idx)
        t = ords[pos_train]
        if t.size == 0:
            return train_idx
        max_train_ord = int(t.max())
        test_end = int(ords[df_positions(eval_idx)].max())
        purge_lo = max_train_ord - int(purge_days)          # purge the prior-season tail
        emb_hi = test_end + int(self.embargo_days)          # post-fold embargo band
        dropped = (t > purge_lo) | ((t > test_end) & (t <= emb_hi))
        return train_idx[~dropped]

    def split(
        self, df: pd.DataFrame, feature_cols: Iterable[str] | None = None
    ) -> Generator[tuple[pd.Index, pd.Index], None, None]:
        """Yield `(train_idx, eval_idx)` for each forward fold with purge + embargo applied.

        `feature_cols` (optional) sizes the feature-aware purge band; pass the union of the
        model(s) being evaluated so the band covers the longest window any model uses.
        Populates `self.last_stats` with per-fold trim diagnostics as it iterates.
        """
        ords = _as_ordinals(df[self.date_col])
        purge_days = self._purge_days_for(feature_cols)
        self.last_stats = []
        for train_idx, eval_idx in all_season_splits(df, min_train_seasons=self.min_train_seasons):
            kept = self._purge_band(ords, train_idx, eval_idx, purge_days)
            ev_pos = df_positions(eval_idx)
            yr = int(df.loc[eval_idx, self.year_col].mode().iloc[0])
            self.last_stats.append(FoldPurgeStats(
                eval_year=yr, purge_days=purge_days, embargo_days=self.embargo_days,
                n_train_raw=len(train_idx), n_train_purged=len(kept), n_eval=len(eval_idx),
                test_start=str(pd.to_datetime(df[self.date_col]).iloc[ev_pos].min().date()),
                test_end=str(pd.to_datetime(df[self.date_col]).iloc[ev_pos].max().date()),
            ))
            yield kept, eval_idx

    # Convenience: a bound callable matching the `splitter(df) -> iterator` interface the
    # promotion-gate driver consumes, with feature_cols baked in.
    def as_callable(
        self, feature_cols: Iterable[str] | None = None
    ) -> Callable[[pd.DataFrame], Generator[tuple[pd.Index, pd.Index], None, None]]:
        cols = list(feature_cols) if feature_cols is not None else None
        return lambda df: self.split(df, feature_cols=cols)


def df_positions(idx: pd.Index) -> np.ndarray:
    """Positional (iloc) indices for a label Index. The training surface is
    `reset_index(drop=True)` so labels == positions, but resolve explicitly so the splitter
    is correct even if a caller passes a non-default index."""
    return np.asarray(idx, dtype="int64")


def make_purged_splitter(
    feature_cols: Iterable[str] | None = None,
    *,
    embargo_days: int = 3,
    purge_days: int | None = None,
    default_lookback_days: int = FEATURE_WINDOW_DEFAULT_DAYS,
    max_purge_days: int | None = DEFAULT_MAX_PURGE_DAYS,
    min_train_seasons: int = 3,
) -> tuple[PurgedWalkForwardSplit, Callable[[pd.DataFrame], Generator[tuple[pd.Index, pd.Index], None, None]]]:
    """Build a `PurgedWalkForwardSplit` and its `splitter(df)` callable in one step.

    Returns `(splitter_obj, splitter_callable)` so the caller can both iterate folds AND
    read `splitter_obj.last_stats` for the recalibration report after iteration.
    """
    sp = PurgedWalkForwardSplit(
        min_train_seasons=min_train_seasons, embargo_days=embargo_days, purge_days=purge_days,
        default_lookback_days=default_lookback_days, max_purge_days=max_purge_days,
    )
    return sp, sp.as_callable(feature_cols)
