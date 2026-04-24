import pandas as pd
import pytest
from betting_ml.utils.cv_splits import all_season_splits, season_forward_splits


def _make_df(years):
    rows_per_year = 5
    return pd.DataFrame({"game_year": [y for y in years for _ in range(rows_per_year)]})


class TestSeasonForwardSplits:
    def test_eval_year_only_in_eval_set(self):
        df = _make_df(range(2016, 2026))
        ti, ei = next(season_forward_splits(df, eval_year=2022))
        assert set(df.loc[ei, "game_year"]) == {2022}

    def test_eval_year_not_in_train_set(self):
        df = _make_df(range(2016, 2026))
        ti, ei = next(season_forward_splits(df, eval_year=2022))
        assert 2022 not in set(df.loc[ti, "game_year"])

    def test_train_years_all_before_eval(self):
        df = _make_df(range(2016, 2026))
        ti, ei = next(season_forward_splits(df, eval_year=2023))
        train_years = set(df.loc[ti, "game_year"])
        assert all(y < 2023 for y in train_years)

    def test_no_row_overlap(self):
        df = _make_df(range(2016, 2026))
        ti, ei = next(season_forward_splits(df, eval_year=2025))
        assert len(set(ti) & set(ei)) == 0


class TestAllSeasonSplits:
    def test_produces_folds(self):
        df = _make_df(range(2016, 2026))
        folds = list(all_season_splits(df, min_train_seasons=3))
        assert len(folds) > 0

    def test_chronological_order_no_leak(self):
        df = _make_df(range(2016, 2026))
        folds = list(all_season_splits(df, min_train_seasons=3))
        for ti, ei in folds:
            max_train = df.loc[ti, "game_year"].max()
            min_eval = df.loc[ei, "game_year"].min()
            assert max_train < min_eval, f"Leak: train max {max_train} >= eval min {min_eval}"

    def test_min_train_seasons_boundary(self):
        # With years 2016–2019 and min_train_seasons=3:
        # eval_year=2019 is the only valid fold (train: 2016, 2017, 2018 = 3 years)
        df = _make_df(range(2016, 2020))
        folds = list(all_season_splits(df, min_train_seasons=3))
        assert len(folds) == 1
        _, ei = folds[0]
        assert set(df.loc[ei, "game_year"]) == {2019}

    def test_min_train_seasons_prevents_folds_with_insufficient_history(self):
        df = _make_df(range(2016, 2020))
        folds = list(all_season_splits(df, min_train_seasons=4))
        # Need 4 train years before eval, so no fold is possible (max train = 3 years)
        assert len(folds) == 0

    def test_expected_fold_count(self):
        # years 2016–2025; min_train_seasons=3
        # valid eval years: 2019, 2020, 2021, 2022, 2023, 2024, 2025 → 7 folds
        df = _make_df(range(2016, 2026))
        folds = list(all_season_splits(df, min_train_seasons=3))
        assert len(folds) == 7

    def test_no_eval_year_in_any_training_fold(self):
        df = _make_df(range(2016, 2026))
        folds = list(all_season_splits(df, min_train_seasons=3))
        for ti, ei in folds:
            eval_years = set(df.loc[ei, "game_year"])
            train_years = set(df.loc[ti, "game_year"])
            overlap = eval_years & train_years
            assert not overlap, f"Eval years {eval_years} found in training set"
