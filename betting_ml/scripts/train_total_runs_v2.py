"""Card 7.V Task 3 — full v2 retrain for total_runs.

Trains NGBoost(Normal, max_depth=3, n_estimators=500) on the full 2021+
window using the current Phase 7 retained feature set, fits an imputation
pipeline against the same training data, computes season-forward CV MAE
for parity with the v1 reporting, and persists the artifact to
betting_ml/models/total_runs/ngboost_tuned_v2.pkl.

Run from project root:
    uv run python betting_ml/scripts/train_total_runs_v2.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.sample_weights import compute_sample_weights


_ARTIFACT_PATH = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "ngboost_tuned_v2.pkl"
_FEATURE_COLS_PATH = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "feature_columns_v2.json"
_RESULTS_PATH = PROJECT_ROOT / "betting_ml" / "evaluation" / "v2_train_results.json"

# Pass --weighted to enable exponential decay sample_weights (Card 8.N)
import argparse as _argparse
_WEIGHTED_FLAG = "--weighted" in sys.argv

_DIST_NAME = "Normal"
_MAX_DEPTH = 3
_N_ESTIMATORS = 500


def main() -> None:
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    if _WEIGHTED_FLAG:
        print("=== WEIGHTED MODE (Card 8.N time-decay sample_weights) ===")

    print("Loading historical features (2021+)...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows; seasons {sorted(df['game_year'].unique())}")

    retained = load_retained_features()
    feature_cols = [f for f in retained if f in df.columns]
    print(f"  Using {len(feature_cols)} retained features")

    # ------ Season-forward CV for MAE reporting (parity with 4.12d / 7.MA) ------
    fold_maes = []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])

        Xtr_raw = df.loc[train_idx, feature_cols]
        Xev_raw = df.loc[eval_idx, feature_cols]
        ytr = df.loc[train_idx, "total_runs"].values
        yev = df.loc[eval_idx, "total_runs"].values

        pipe = build_imputation_pipeline()
        Xtr = pipe.fit_transform(Xtr_raw).select_dtypes(include=[np.number])
        Xev = pipe.transform(Xev_raw).reindex(columns=Xtr.columns, fill_value=0.0)

        sample_weights = compute_sample_weights(df.loc[train_idx], date_col="game_date") if _WEIGHTED_FLAG and "game_date" in df.columns else None
        base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
        ngb = NGBRegressor(Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False)
        t0 = time.time()
        ngb.fit(Xtr.values, ytr, sample_weight=sample_weights)
        pred = ngb.predict(Xev.values)
        mae = float(np.mean(np.abs(pred - yev)))
        dur = time.time() - t0
        print(f"  Fold eval_year={eval_year}: train_n={len(train_idx)} eval_n={len(eval_idx)} "
              f"MAE={mae:.4f} ({dur:.0f}s)")
        fold_maes.append({"eval_year": eval_year, "mae": mae, "n_train": len(train_idx),
                          "n_eval": len(eval_idx)})

    cv_mae = float(np.mean([f["mae"] for f in fold_maes]))
    print(f"\nCV MAE (mean across {len(fold_maes)} folds): {cv_mae:.4f}")

    # ------ Final model: train on ALL 2021+ rows for production artifact ------
    print("\nTraining final v2 artifact on full 2021+ window...")
    X_full_raw = df[feature_cols]
    y_full = df["total_runs"].values

    pipe_full = build_imputation_pipeline()
    X_full = pipe_full.fit_transform(X_full_raw).select_dtypes(include=[np.number])
    final_feature_cols = X_full.columns.tolist()
    print(f"  Final feature matrix: {X_full.shape}")

    sample_weights_full = compute_sample_weights(df, date_col="game_date") if _WEIGHTED_FLAG and "game_date" in df.columns else None
    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=_MAX_DEPTH)
    ngb_final = NGBRegressor(Dist=Normal, n_estimators=_N_ESTIMATORS, Base=base, verbose=False)
    t0 = time.time()
    ngb_final.fit(X_full.values, y_full, sample_weight=sample_weights_full)
    fit_dur = time.time() - t0
    print(f"  Fit complete in {fit_dur:.0f}s")

    # In-sample residual sanity check
    pred_full = ngb_final.predict(X_full.values)
    in_mae = float(np.mean(np.abs(pred_full - y_full)))
    in_std_pred = float(np.std(pred_full))
    in_mean_resid = float(np.mean(pred_full - y_full))
    print(f"  In-sample: MAE={in_mae:.4f}, std(pred)={in_std_pred:.4f}, "
          f"mean_residual={in_mean_resid:+.4f}")

    # ------ Persist artifact + feature columns ------
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(ngb_final, _ARTIFACT_PATH)
    print(f"\nSaved artifact: {_ARTIFACT_PATH}")

    _FEATURE_COLS_PATH.write_text(json.dumps(final_feature_cols, indent=0))
    print(f"Saved feature columns: {_FEATURE_COLS_PATH} ({len(final_feature_cols)} cols)")

    results = {
        "target": "total_runs",
        "model_version": "v2",
        "dist": _DIST_NAME,
        "max_depth": _MAX_DEPTH,
        "n_estimators": _N_ESTIMATORS,
        "training_rows": int(len(df)),
        "training_cutoff": "2021+",
        "n_features_in": len(final_feature_cols),
        "cv_mae": cv_mae,
        "fold_maes": fold_maes,
        "in_sample_mae": in_mae,
        "in_sample_std_pred": in_std_pred,
        "in_sample_mean_residual": in_mean_resid,
        "artifact_path": str(_ARTIFACT_PATH.relative_to(PROJECT_ROOT)),
        "feature_columns_path": str(_FEATURE_COLS_PATH.relative_to(PROJECT_ROOT)),
    }
    _RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {_RESULTS_PATH}")


if __name__ == "__main__":
    main()
