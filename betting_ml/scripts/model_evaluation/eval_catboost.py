"""Card 7.MB — CatBoost evaluation on walk-forward CV folds.

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_catboost.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import (
    FOLDS, _NON_FEATURE_COLS,
    brier_score, log_loss_score, mean_h2h_edge, pct_positive_edge,
    totals_mae, run_line_roi,
)

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_MODEL_NAME = "catboost"
_NON_FEAT = _NON_FEATURE_COLS | {"split"}
_EVAL_FRAC = 0.10


def _load_fold(fold_name: str):
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{fold_name}.parquet")
    tgt = pd.read_parquet(_OUTPUT_DIR / f"targets_{fold_name}.parquet")

    feat_cols = [c for c in feat.columns if c not in _NON_FEAT]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    te_f = feat[feat["split"] == "test"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)
    te_t = tgt[tgt["split"] == "test"].reset_index(drop=True)

    if "game_date" in tr_f.columns:
        sort_idx = tr_f["game_date"].argsort()
        tr_f = tr_f.iloc[sort_idx].reset_index(drop=True)
        tr_t = tr_t.iloc[sort_idx].reset_index(drop=True)

    return feat_cols, tr_f, te_f, tr_t, te_t


def _split_early_stop(X, y):
    n_val = max(1, int(len(X) * _EVAL_FRAC))
    return X[:-n_val], X[-n_val:], y[:-n_val], y[-n_val:]


def _valid(arr: np.ndarray) -> np.ndarray:
    return ~np.isnan(arr)


def run_fold(fold_name: str) -> dict:
    from catboost import CatBoostClassifier, CatBoostRegressor, Pool

    feat_cols, tr_f, te_f, tr_t, te_t = _load_fold(fold_name)

    X_tr = tr_f[feat_cols].values.astype(np.float32)
    X_te = te_f[feat_cols].values.astype(np.float32)
    y_tr_win = tr_t["home_win"].values.astype(np.float32)
    y_te_win = te_t["home_win"].values.astype(np.float32)
    y_tr_runs = tr_t["total_runs"].values.astype(np.float32)
    y_te_runs = te_t["total_runs"].values.astype(np.float32)
    y_tr_diff = tr_t["run_differential"].values.astype(np.float32)
    y_te_diff = te_t["run_differential"].values.astype(np.float32)
    mkt = (
        te_f["home_implied_prob"].values.astype(np.float64)
        if "home_implied_prob" in te_f.columns
        else np.full(len(te_f), np.nan)
    )

    # Detect categorical columns by dtype (object or category) — in practice all
    # features are numeric from _get_feature_cols(), so cat_features will be empty.
    cat_indices = [
        i for i, col in enumerate(feat_cols)
        if tr_f[col].dtype == object or hasattr(tr_f[col], "cat")
    ]

    vw, vr, vd = _valid(y_te_win), _valid(y_te_runs), _valid(y_te_diff)

    t0 = time.time()

    # ---------- win probability: CatBoostClassifier ----------
    vw_tr = _valid(y_tr_win)
    X_fit_w, X_val_w, y_fit_w, y_val_w = _split_early_stop(X_tr[vw_tr], y_tr_win[vw_tr])
    clf = CatBoostClassifier(
        iterations=500, learning_rate=0.05, depth=6,
        loss_function="Logloss", eval_metric="Logloss",
        cat_features=cat_indices, verbose=0, random_seed=42,
    )
    clf.fit(
        X_fit_w, y_fit_w,
        eval_set=Pool(X_val_w, y_val_w, cat_features=cat_indices),
        early_stopping_rounds=50,
    )
    p_win = clf.predict_proba(X_te)[:, 1]

    # ---------- run differential: CatBoostRegressor ----------
    vd_tr = _valid(y_tr_diff)
    X_fit_d, X_val_d, y_fit_d, y_val_d = _split_early_stop(X_tr[vd_tr], y_tr_diff[vd_tr])
    reg_diff = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        loss_function="RMSE", cat_features=cat_indices,
        verbose=0, random_seed=42,
    )
    reg_diff.fit(
        X_fit_d, y_fit_d,
        eval_set=Pool(X_val_d, y_val_d, cat_features=cat_indices),
        early_stopping_rounds=50,
    )
    p_diff = reg_diff.predict(X_te)

    # ---------- total runs: CatBoostRegressor ----------
    vr_tr = _valid(y_tr_runs)
    X_fit_r, X_val_r, y_fit_r, y_val_r = _split_early_stop(X_tr[vr_tr], y_tr_runs[vr_tr])
    reg_runs = CatBoostRegressor(
        iterations=500, learning_rate=0.05, depth=6,
        loss_function="RMSE", cat_features=cat_indices,
        verbose=0, random_seed=42,
    )
    reg_runs.fit(
        X_fit_r, y_fit_r,
        eval_set=Pool(X_val_r, y_val_r, cat_features=cat_indices),
        early_stopping_rounds=50,
    )
    p_runs = reg_runs.predict(X_te)

    fit_time = time.time() - t0

    vwd = vw & vd
    return {
        "fold_name": fold_name,
        "model_name": _MODEL_NAME,
        "brier_score": brier_score(y_te_win[vw], p_win[vw]),
        "log_loss": log_loss_score(y_te_win[vw], p_win[vw]),
        "mean_h2h_edge": mean_h2h_edge(p_win[vw], mkt[vw]),
        "pct_positive_edge": pct_positive_edge(p_win[vw], mkt[vw]),
        "totals_mae": totals_mae(y_te_runs[vr], p_runs[vr]),
        "run_line_roi": run_line_roi(y_te_win[vwd], p_diff[vwd]),
        "train_rows": len(tr_f),
        "test_rows": len(te_f),
        "fit_time_seconds": fit_time,
    }


def main() -> None:
    print(f"=== {_MODEL_NAME.upper()} — Walk-Forward CV Evaluation ===\n")
    hdr = f"{'Fold':<12} {'Brier':>8} {'LogLoss':>9} {'H2H Edge':>10} {'%PosEdge':>10} {'RunsMAE':>9} {'RL ROI':>8} {'Time':>7}"
    print(hdr)
    print("-" * len(hdr))

    records = []
    for fold in [f["name"] for f in FOLDS]:
        r = run_fold(fold)
        records.append(r)
        print(
            f"{r['fold_name']:<12} {r['brier_score']:>8.4f} {r['log_loss']:>9.4f} "
            f"{r['mean_h2h_edge']:>+10.4f} {r['pct_positive_edge']:>10.4f} "
            f"{r['totals_mae']:>9.4f} {r['run_line_roi']:>+8.4f} {r['fit_time_seconds']:>6.1f}s"
        )

    df = pd.DataFrame(records)
    out = _OUTPUT_DIR / f"results_{_MODEL_NAME}.parquet"
    df.to_parquet(out, index=False)

    print(f"\n{'MEAN':<12} {df['brier_score'].mean():>8.4f} {df['log_loss'].mean():>9.4f} "
          f"{df['mean_h2h_edge'].mean():>+10.4f} {df['pct_positive_edge'].mean():>10.4f} "
          f"{df['totals_mae'].mean():>9.4f} {df['run_line_roi'].mean():>+8.4f}")
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
