"""Shared safe numeric conversions for the Streamlit app pages.

A pandas ``NaN`` is a float and passes ``is not None``, so a bare ``int(val)`` on a
column that may be missing (an un-announced probable starter, a game with no score
yet) raises ``ValueError: cannot convert float NaN to integer``. These helpers
centralise the ``pd.isna`` guard so each page doesn't re-implement it inline.
"""

from __future__ import annotations

import pandas as pd


def safe_int(val, default: int | None = None) -> int | None:
    """Convert ``val`` to ``int``, returning ``default`` for None/NaN/unparseable."""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
    except (TypeError, ValueError):
        pass  # not a scalar pandas can test (e.g. a list) — fall through to int()
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_float(val, default: float | None = None) -> float | None:
    """Convert ``val`` to ``float``, returning ``default`` for None/NaN/unparseable."""
    if val is None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    return default if f != f else f  # NaN != NaN
