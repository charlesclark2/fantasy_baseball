"""End-to-end smoke test for the betting_ml pipeline.

Exercises: load_features → build_imputation_pipeline → all_season_splits.
Hard assertions:
  - Zero nulls across all folds after imputation
  - 2020 absent from every fold
  - post_2022_rules and game_year present in every train and eval set

Exits 0 on success; non-zero with a descriptive message on any failure.
"""

import sys
import pandas as pd
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.preprocessing import build_imputation_pipeline


def _check(condition: bool, message: str) -> None:
    if not condition:
        print(f"FAIL: {message}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    print("Loading features from Snowflake...")
    df = load_features()
    print(f"  Loaded {len(df):,} rows × {len(df.columns)} columns")

    required_cols = {"post_2022_rules", "game_year"}
    missing = required_cols - set(df.columns)
    _check(not missing, f"Missing required columns: {missing}")

    pipe = build_imputation_pipeline()
    targets = ["total_runs", "run_differential", "home_win"]
    feature_cols = [c for c in df.columns if c not in targets]
    X = df[feature_cols]

    print("Generating season-forward CV folds...")
    folds = list(all_season_splits(df, min_train_seasons=3))
    _check(len(folds) > 0, "all_season_splits produced zero folds")
    print(f"  {len(folds)} folds generated")

    print("\n{:<8} {:>12} {:>10} {:>10}".format(
        "Fold", "Train rows", "Eval rows", "Nulls"
    ))
    print("-" * 44)

    for i, (ti, ei) in enumerate(folds):
        X_train = X.loc[ti]
        X_eval = X.loc[ei]

        eval_year = sorted(int(y) for y in df.loc[ei, "game_year"].unique())
        fold_label = str(eval_year[0]) if len(eval_year) == 1 else str(eval_year)

        # Fit on train, transform train + eval
        pipe_fold = build_imputation_pipeline()
        pipe_fold.fit(X_train)
        X_train_out = pd.DataFrame(pipe_fold.transform(X_train))
        X_eval_out = pd.DataFrame(pipe_fold.transform(X_eval))

        # Null check
        train_nulls = int(X_train_out.isnull().sum().sum())
        eval_nulls = int(X_eval_out.isnull().sum().sum())
        _check(train_nulls == 0, f"Fold {fold_label}: {train_nulls} nulls in train set")
        _check(eval_nulls == 0, f"Fold {fold_label}: {eval_nulls} nulls in eval set")

        # 2020 check
        train_2020 = (df.loc[ti, "game_year"] == 2020).sum()
        eval_2020 = (df.loc[ei, "game_year"] == 2020).sum()
        _check(train_2020 == 0, f"Fold {fold_label}: 2020 found in training set")
        _check(eval_2020 == 0, f"Fold {fold_label}: 2020 found in eval set")

        # Required column check (using original DataFrame, pre-imputation)
        for col in required_cols:
            _check(col in df.loc[ti].columns, f"Fold {fold_label}: {col} missing from train")
            _check(col in df.loc[ei].columns, f"Fold {fold_label}: {col} missing from eval")

        total_nulls = train_nulls + eval_nulls
        print("{:<8} {:>12,} {:>10,} {:>10}".format(
            fold_label, len(ti), len(ei), total_nulls
        ))

    print("\nAll assertions passed.")
    print(f"Summary: {len(folds)} folds, 0 nulls, 2020 absent, "
          f"post_2022_rules + game_year present in all folds.")


if __name__ == "__main__":
    main()
