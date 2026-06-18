"""Tests for Epic E1.1 — PurgedWalkForwardSplit + the per-feature window registry."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils.cv import (
    PurgedWalkForwardSplit, feature_window_days, make_purged_splitter, max_feature_window,
)
from betting_ml.utils.cv_splits import all_season_splits


def _season_df(years=(2021, 2022, 2023, 2024), games_per_day=3):
    rows = []
    for yr in years:
        for d in pd.date_range(f"{yr}-04-01", f"{yr}-09-30", freq="D"):
            for _ in range(games_per_day):
                rows.append({"game_year": yr, "game_date": d.strftime("%Y-%m-%d")})
    return pd.DataFrame(rows).reset_index(drop=True)


class TestWindowRegistry:
    def test_parses_day_windows(self):
        assert feature_window_days("home_off_woba_30d") == 30
        assert feature_window_days("away_pit_k_pct_7d") == 7
        assert feature_window_days("home_bp_xwoba_against_14d") == 14

    def test_year_aggregates_are_not_rolling_windows(self):
        # multi-year aggregates must NOT inflate the purge band (a 1095d band empties the
        # earliest fold's training set) — they fall back to the default day window.
        assert feature_window_days("park_run_factor_3yr") == 30
        assert feature_window_days("home_win_rate_trailing_3yr") == 30

    def test_unwindowed_falls_back_to_default(self):
        assert feature_window_days("home_bp_eb_xwoba") == 30
        assert feature_window_days("elevation_ft", default=12) == 12

    def test_max_feature_window_and_cap(self):
        cols = ["a_7d", "b_30d", "c_90d", "park_x_3yr"]
        assert max_feature_window(cols) == 90          # _3yr ignored; 90d is the max rolling
        assert max_feature_window(cols, cap=30) == 30
        assert max_feature_window([]) == 30  # default with no cols


class TestPurgedWalkForwardSplit:
    def test_same_eval_folds_as_baseline(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=30)
        purged = list(sp.split(df))
        base = list(all_season_splits(df, min_train_seasons=3))
        assert len(purged) == len(base)
        for (_, ev), (_, bev) in zip(purged, base):
            assert set(ev) == set(bev)

    def test_train_is_subset_of_baseline(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=30)
        for (tr, _), (btr, _) in zip(sp.split(df), all_season_splits(df, min_train_seasons=3)):
            assert set(tr).issubset(set(btr))

    def test_prior_season_tail_is_purged(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=30)
        for (tr, _), (btr, _) in zip(sp.split(df), all_season_splits(df, min_train_seasons=3)):
            tr_dates = pd.to_datetime(df.loc[tr, "game_date"])
            last_train = pd.to_datetime(df.loc[btr, "game_date"]).max()
            band_lo = last_train - pd.Timedelta(days=30)
            assert not (tr_dates > band_lo).any(), "prior-season tail not purged"

    def test_no_future_leakage(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=30)
        for tr, ev in sp.split(df):
            assert df.loc[tr, "game_year"].max() < df.loc[ev, "game_year"].min()

    def test_purge_stats_recorded(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=30)
        list(sp.split(df))
        assert len(sp.last_stats) == len(list(all_season_splits(df, min_train_seasons=3)))
        for st in sp.last_stats:
            assert st.n_dropped > 0           # there IS a tail to purge
            assert st.purge_days == 30
            assert 0.0 < st.frac_dropped < 1.0

    def test_feature_aware_purge_days(self):
        df = _season_df()
        sp = PurgedWalkForwardSplit(min_train_seasons=3)  # purge_days=None → derive
        list(sp.split(df, feature_cols=["a_7d", "b_14d"]))
        assert sp.last_stats[0].purge_days == 14
        sp2 = PurgedWalkForwardSplit(min_train_seasons=3)
        list(sp2.split(df, feature_cols=["a_7d", "b_90d"]))
        assert sp2.last_stats[0].purge_days == 90

    def test_larger_purge_drops_more(self):
        df = _season_df()
        small = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=7)
        big = PurgedWalkForwardSplit(min_train_seasons=3, purge_days=45)
        list(small.split(df)); list(big.split(df))
        assert big.last_stats[0].n_dropped > small.last_stats[0].n_dropped

    def test_make_purged_splitter_callable(self):
        df = _season_df()
        sp, call = make_purged_splitter(["a_7d", "b_30d"], embargo_days=2)
        folds = list(call(df))
        assert len(folds) == len(list(all_season_splits(df, min_train_seasons=3)))
        assert sp.last_stats[0].purge_days == 30
