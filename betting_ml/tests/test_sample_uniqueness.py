"""Tests for Epic E1.2 — sample-uniqueness weights + sequential bootstrap."""

from __future__ import annotations

import numpy as np
import pandas as pd

from betting_ml.utils.sample_uniqueness import (
    DEFAULT_WINDOW_DAYS, UNIQUENESS_COLUMN, attach_sample_uniqueness,
    compute_sample_uniqueness, sequential_bootstrap,
)


def _dates():
    # one isolated early game + two dense same-day clusters
    return ["2021-04-01"] + ["2021-07-01"] * 20 + ["2021-07-02"] * 20


class TestUniqueness:
    def test_bounded_0_1(self):
        u = compute_sample_uniqueness(_dates(), window_days=10)
        assert (u > 0).all() and (u <= 1.0).all()

    def test_isolated_more_unique_than_cluster(self):
        u = compute_sample_uniqueness(_dates(), window_days=10)
        assert u[0] > u[1]
        assert np.isclose(u[0], 1.0)

    def test_deterministic(self):
        u1 = compute_sample_uniqueness(_dates(), window_days=10)
        u2 = compute_sample_uniqueness(_dates(), window_days=10)
        assert np.allclose(u1, u2)

    def test_order_preserved(self):
        d = _dates()
        u = compute_sample_uniqueness(d, window_days=10)
        assert len(u) == len(d)

    def test_window_resolution_default(self):
        # no window/feature_cols → DEFAULT_WINDOW_DAYS
        u = compute_sample_uniqueness(_dates())
        assert len(u) == len(_dates())
        assert DEFAULT_WINDOW_DAYS == 30

    def test_feature_cols_window(self):
        # max feature window drives the calc; a wider window overlaps more → lower uniqueness
        narrow = compute_sample_uniqueness(_dates(), feature_cols=["x_7d"])
        wide = compute_sample_uniqueness(_dates(), feature_cols=["x_30d"])
        assert wide[1] <= narrow[1] + 1e-9


class TestAttach:
    def test_adds_canonical_column(self):
        df = pd.DataFrame({"game_date": _dates(), "game_year": [2021] * len(_dates())})
        out = attach_sample_uniqueness(df, window_days=10)
        assert UNIQUENESS_COLUMN in out.columns
        assert len(out) == len(df)
        assert (out[UNIQUENESS_COLUMN] > 0).all()
        # original df not mutated
        assert UNIQUENESS_COLUMN not in df.columns


class TestSequentialBootstrap:
    def test_overweights_unique_sample(self):
        d = _dates()
        sel = sequential_bootstrap(d, window_days=10, n_samples=4100, seed=1)
        frac_iso = (sel == 0).mean()
        assert frac_iso > 1.0 / len(d)   # beats the i.i.d. 1/N share

    def test_returns_valid_indices(self):
        d = _dates()
        sel = sequential_bootstrap(d, window_days=10, n_samples=50, seed=3)
        assert sel.min() >= 0 and sel.max() < len(d)
        assert len(sel) == 50

    def test_caps_n(self):
        d = ["2021-04-01"] * 30
        import pytest
        with pytest.raises(ValueError):
            sequential_bootstrap(d, window_days=5, max_n=10)
