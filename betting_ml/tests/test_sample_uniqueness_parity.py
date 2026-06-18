"""Epic E1.2 drift guard: the sample-uniqueness weight must be ONE canonical, deterministic
definition shared by every trainer (the parity discipline mirrored from
`season_normalization` / `test_season_norm_parity`).

A drift here = trainers silently fitting on different sample weights → a train/eval skew the
gate cannot see. These tests pin the canonical column name, the default window, and the
function's determinism + boundedness so any change is a deliberate, reviewed edit.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.utils import sample_uniqueness as su


def test_canonical_constants_pinned():
    # Changing either is a contract change — every trainer keys on these.
    assert su.UNIQUENESS_COLUMN == "sample_uniqueness"
    assert su.DEFAULT_WINDOW_DAYS == 30


def test_attach_uses_canonical_column_and_is_deterministic():
    df = pd.DataFrame({
        "game_date": pd.date_range("2021-04-01", periods=200, freq="D").strftime("%Y-%m-%d"),
        "game_year": [2021] * 200,
    })
    a = su.attach_sample_uniqueness(df)
    b = su.attach_sample_uniqueness(df)
    assert su.UNIQUENESS_COLUMN in a.columns
    assert np.allclose(a[su.UNIQUENESS_COLUMN].values, b[su.UNIQUENESS_COLUMN].values)


def test_weights_are_strictly_positive_and_bounded():
    df = pd.DataFrame({
        "game_date": (["2021-05-01"] * 50 + ["2021-06-01"] * 50),
        "game_year": [2021] * 100,
    })
    w = su.attach_sample_uniqueness(df)[su.UNIQUENESS_COLUMN].values
    assert (w > 0).all() and (w <= 1.0).all()
