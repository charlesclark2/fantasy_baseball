"""scoring.py — pure, sport-agnostic scorer: a RAW projected stat line → league fantasy points.

Deterministic and transparent: `league_points = Σ_stat points(stat, position) × raw_stat`. The scoring
policy comes entirely from the `LeagueConfig.scoring` rules; the raw-column mapping comes from the
`SportProfile.stat_columns`. Nothing here is NFL-specific — swap in a baseball config + profile and the
same function scores a hitter's line. A NULL in a raw stat contributes 0 to ITS term only (a missing
passing line never zeroes a WR — NULL kept NULL, per the honest frame).

Uncertainty passthrough (honest, not false-precise): the upstream projection carries an interval on a
CONVENIENCE point total (NFL: `fp_ppr_sd` on `proj_fp_ppr`). We do not have per-format game logs to
re-derive game-to-game variance, so we carry the projection's *coefficient of variation* through the
rescore — `league_sd = (base_sd / base_points) × league_points` — and rebuild an 80% interval from it.
This is a first-order rescale (documented as such): it preserves relative dispersion under the linear
scoring transform, which is exact when the format only rescales the same line and a good approximation
when the reception weight shifts composition. Rookie intervals stay PARAMETER uncertainty (flagged via
`uncertainty_type`), to be recalibrated before any pricing use.
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
        # coefficient of variation of the upstream projection, carried through the rescore
        cv = np.where(base_pts > 1e-9, base_sd / np.where(base_pts > 1e-9, base_pts, 1.0), 0.0)
        league_sd = np.abs(cv * out[out_col].to_numpy())
        out[out_col + "_sd"] = np.round(league_sd, 2)
        out[out_col + "_p10"] = np.round(np.clip(out[out_col].to_numpy() - _Z80 * league_sd, 0.0, None), 1)
        out[out_col + "_p90"] = np.round(out[out_col].to_numpy() + _Z80 * league_sd, 1)
    return out
