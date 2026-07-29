"""scoring.py — pure, sport-agnostic scorer: a RAW projected stat line → league fantasy points.

Deterministic and transparent: `league_points = Σ_stat points(stat, position) × raw_stat`. The scoring
policy comes entirely from the `LeagueConfig.scoring` rules; the raw-column mapping comes from the
`SportProfile.stat_columns`. Nothing here is NFL-specific — swap in a baseball config + profile and the
same function scores a hitter's line. A NULL in a raw stat contributes 0 to ITS term only (a missing
passing line never zeroes a WR — NULL kept NULL, per the honest frame).

Uncertainty passthrough (honest, not false-precise): the upstream projection carries an interval on a
CONVENIENCE point total (NFL: `fp_ppr_p10`/`fp_ppr_p90`/`fp_ppr_sd` on `proj_fp_ppr`). We do not have
per-format game logs to re-derive game-to-game variance, so the projection's own dispersion is carried
through the rescore in the SAME PROPORTION the point moved. Where the profile publishes the upstream
bounds, EACH SIDE is carried independently (`league_p10 = base_p10 × league_points / base_points`);
otherwise we fall back to the *coefficient of variation* and a symmetric `±z·sd` band. Either way this
is a first-order rescale (documented as such): it preserves relative dispersion under the linear
scoring transform, exactly when the format only rescales the same line and approximately when the
reception weight shifts composition.

⚠️ WHY THE PER-SIDE PATH EXISTS (NF1.7): the single-`sd` reconstruction is SYMMETRIC by construction.
That is right for a veteran (a normal approximation off realized game-to-game variance) and wrong for a
rookie, whose per-player band is heavily right-skewed — a mid-round pick's p10 is near zero while his
p90 is a real season. Re-symmetrising it here would slide the interval off its own point and hand the
app back exactly the incoherence NF1.7 removed upstream, in a league format instead of the base one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig, SportProfile

# 80% two-sided normal quantile (matches the MVP-1 projection's interval convention).
_Z80 = 1.2815515594


def _stat_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    """A numeric, NaN→0 view of a raw stat column (absent column ⇒ all-zero term)."""
    if column is None or column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def score_players(
    df: pd.DataFrame,
    config: LeagueConfig,
    profile: SportProfile,
    *,
    out_col: str = "league_points",
    with_interval: bool = True,
) -> pd.DataFrame:
    """Score every row of a raw projection frame under `config`.

    Adds `<out_col>` (league fantasy points) and, when `with_interval` and the profile declares its base
    point/sd columns, `<out_col>_sd/_p10/_p90` (the CV-rescaled 80% interval). Pure: returns a copy.
    """
    out = df.copy()
    positions = out[profile.position_column].map(profile.normalize_position)

    # base (position-agnostic) scoring — vectorised over the per_stat map
    pts = pd.Series(0.0, index=out.index)
    for stat_key, weight in config.scoring.per_stat.items():
        if weight == 0.0:
            continue
        pts = pts + float(weight) * _stat_series(out, profile.stat_columns.get(stat_key))

    # per-position bonuses (TE-premium PPR, position-specific TD values, …)
    for pos, bonus in config.scoring.position_bonuses.items():
        mask = (positions == pos).to_numpy()
        if not mask.any():
            continue
        add = pd.Series(0.0, index=out.index)
        for stat_key, weight in bonus.items():
            if weight == 0.0:
                continue
            add = add + float(weight) * _stat_series(out, profile.stat_columns.get(stat_key))
        pts = pts + add.where(pd.Series(mask, index=out.index), 0.0)

    out[out_col] = pts.astype(float)

    if with_interval and profile.base_points_column and profile.base_sd_column:
        base_pts = _stat_series(out, profile.base_points_column)
        base_sd = _stat_series(out, profile.base_sd_column)
        pts = out[out_col].to_numpy()
        # coefficient of variation of the upstream projection, carried through the rescore
        cv = np.where(base_pts > 1e-9, base_sd / np.where(base_pts > 1e-9, base_pts, 1.0), 0.0)
        league_sd = np.abs(cv * pts)
        lo = np.clip(pts - _Z80 * league_sd, 0.0, None)
        hi = pts + _Z80 * league_sd

        # ── NF1.7: carry EACH SIDE of the upstream band through independently where the projection
        #    publishes its own bounds. Rebuilding the interval from a single sd forces it SYMMETRIC,
        #    which is fine for a veteran (a normal approximation off game-to-game variance) and wrong
        #    for a rookie: the per-player rookie band is heavily right-skewed — a mid-round pick's p10
        #    is near zero while his p90 is a real season — so a ±z·sd reconstruction would slide the
        #    whole interval and hand the app back the very incoherence NF1.7 removed upstream. Scaling
        #    each bound by the same ratio the point moved is the exact analogue of the CV passthrough
        #    (and reduces to it when the band IS symmetric); it is likewise a first-order rescale,
        #    exact when the format only rescales the same line.
        if profile.base_p10_column and profile.base_p90_column:
            b_lo = _stat_series(out, profile.base_p10_column).to_numpy()
            b_hi = _stat_series(out, profile.base_p90_column).to_numpy()
            bp = base_pts.to_numpy()
            usable = (bp > 1e-9) & (b_hi >= b_lo) & ((b_hi > 0) | (b_lo > 0))
            k = np.where(usable, pts / np.where(bp > 1e-9, bp, 1.0), 1.0)
            lo = np.where(usable, np.clip(b_lo * k, 0.0, None), lo)
            hi = np.where(usable, b_hi * k, hi)
            # the band's implied 1-sd equivalent, so `_sd` keeps describing the band actually emitted
            league_sd = np.where(usable, (hi - lo) / (2 * _Z80), league_sd)
        # coherence: a displayed interval must contain its own point estimate (NF1.7)
        lo = np.clip(np.minimum(lo, pts), 0.0, None)
        hi = np.maximum(hi, pts)

        out[out_col + "_sd"] = np.round(league_sd, 2)
        out[out_col + "_p10"] = np.floor(lo * 10.0) / 10.0
        out[out_col + "_p90"] = np.ceil(hi * 10.0) / 10.0
    return out
