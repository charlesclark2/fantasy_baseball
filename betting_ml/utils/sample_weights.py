"""Exponential decay sample weights for time-aware model training (Card 8.N)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_sample_weights(
    df: pd.DataFrame,
    date_col: str = "game_date",
    half_life_games: int = 162,
) -> np.ndarray:
    """Exponential decay weights — more recent games receive higher weight.

    Formula: weight_i = exp(-lambda * days_since_game_i)
    Lambda: ln(2) / half_life_games   (default half-life = one season ≈ 162 games)
    Weights are normalized to sum to len(df) to preserve effective sample size
    for regularization scaling.

    Parameters
    ----------
    df : DataFrame containing at least the date column.
    date_col : Column name holding game dates (date, datetime, or date string).
    half_life_games : Number of games after which weight is halved.
        Default 162 ≈ one MLB regular season (~6 months / ~182 days).

    Returns
    -------
    np.ndarray of float64, shape (len(df),), summing to len(df).
    """
    dates = pd.to_datetime(df[date_col])
    ref_date = dates.max()
    days_since = (ref_date - dates).dt.days.clip(lower=0)

    lam = math.log(2) / half_life_games
    weights = np.exp(-lam * days_since.values.astype(float))

    # Normalize so weights sum to n (preserves effective sample size)
    weights = weights * (len(df) / weights.sum())
    return weights
