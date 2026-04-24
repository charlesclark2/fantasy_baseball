from typing import Generator, Tuple
import pandas as pd


def season_forward_splits(
    df: pd.DataFrame, eval_year: int
) -> Generator[Tuple[pd.Index, pd.Index], None, None]:
    """Yield one (train_idx, eval_idx) tuple for a single season-forward split.

    Train: all rows where game_year < eval_year.
    Eval:  all rows where game_year == eval_year.
    """
    train_idx = df.index[df["game_year"] < eval_year]
    eval_idx = df.index[df["game_year"] == eval_year]
    yield train_idx, eval_idx


def all_season_splits(
    df: pd.DataFrame, min_train_seasons: int = 3
) -> Generator[Tuple[pd.Index, pd.Index], None, None]:
    """Yield season-forward folds in chronological order.

    Walks from the latest available season back to the earliest season where
    the number of distinct training years >= min_train_seasons. Folds are
    yielded in ascending order by eval year (earliest eval year first).
    """
    years = sorted(df["game_year"].unique())
    valid_folds = []
    for eval_year in years:
        train_years = [y for y in years if y < eval_year]
        if len(train_years) >= min_train_seasons:
            valid_folds.append(eval_year)

    for eval_year in valid_folds:
        yield from season_forward_splits(df, eval_year)
