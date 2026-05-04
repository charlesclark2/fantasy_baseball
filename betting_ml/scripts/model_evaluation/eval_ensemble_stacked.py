"""Card 7.MB — Stacked ensemble evaluation on walk-forward CV folds.

Base estimators: XGBoost + LightGBM + CatBoost
Meta-learner: LogisticRegression (win), Ridge (runs/diff)

Out-of-fold (OOF) predictions from 5 temporal inner folds are used to train
the meta-learner. Temporal ordering is preserved throughout: inner folds split
the outer training window chronologically so no future data leaks into training.

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_ensemble_stacked.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor, Pool
from lightgbm import LGBMClassifier, LGBMRegressor, early_stopping, log_evaluation
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier, XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import (
    FOLDS, _NON_FEATURE_COLS,
    brier_score, log_loss_score, mean_h2h_edge, pct_positive_edge,
    totals_mae, run_line_roi,
)

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_MODEL_NAME = "ensemble_stacked"
_NON_FEAT = _NON_FEATURE_COLS | {"split"}
_INNER_FOLDS = 5
_LGBM_EARLY_STOP = 50
_CB_EARLY_STOP = 50
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


def _valid(arr: np.ndarray) -> np.ndarray:
    return ~np.isnan(arr)


def _lgbm_split(X, y):
    n_val = max(1, int(len(X) * _EVAL_FRAC))
    return X[:-n_val], X[-n_val:], y[:-n_val], y[-n_val:]


def _fit_xgb_clf(X, y):
    m = XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.05,
                      subsample=0.8, colsample_bytree=0.8,
                      eval_metric="logloss", random_state=42, n_jobs=-1)
    m.fit(X, y)
    return m


def _fit_xgb_reg(X, y):
    m = XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.05,
                     subsample=0.8, colsample_bytree=0.8,
                     tree_method="hist", random_state=42, n_jobs=-1)
    m.fit(X, y)
    return m


def _fit_lgbm_clf(X, y):
    Xf, Xv, yf, yv = _lgbm_split(X, y)
    m = LGBMClassifier(n_estimators=500, learning_rate=0.05, num_leaves=63,
                       min_child_samples=20, colsample_bytree=0.8, subsample=0.8,
                       verbose=-1, random_state=42, n_jobs=-1)
    m.fit(Xf, yf, eval_set=[(Xv, yv)],
          callbacks=[early_stopping(_LGBM_EARLY_STOP, verbose=False), log_evaluation(-1)])
    return m


def _fit_lgbm_reg(X, y):
    Xf, Xv, yf, yv = _lgbm_split(X, y)
    m = LGBMRegressor(n_estimators=500, learning_rate=0.05, num_leaves=63,
                      min_child_samples=20, colsample_bytree=0.8, subsample=0.8,
                      objective="regression", verbose=-1, random_state=42, n_jobs=-1)
    m.fit(Xf, yf, eval_set=[(Xv, yv)],
          callbacks=[early_stopping(_LGBM_EARLY_STOP, verbose=False), log_evaluation(-1)])
    return m


def _fit_cb_clf(X, y):
    Xf, Xv, yf, yv = _lgbm_split(X, y)
    m = CatBoostClassifier(iterations=500, learning_rate=0.05, depth=6,
                           loss_function="Logloss", verbose=0, random_seed=42)
    m.fit(Xf, yf, eval_set=Pool(Xv, yv), early_stopping_rounds=_CB_EARLY_STOP)
    return m


def _fit_cb_reg(X, y):
    Xf, Xv, yf, yv = _lgbm_split(X, y)
    m = CatBoostRegressor(iterations=500, learning_rate=0.05, depth=6,
                          loss_function="RMSE", verbose=0, random_seed=42)
    m.fit(Xf, yf, eval_set=Pool(Xv, yv), early_stopping_rounds=_CB_EARLY_STOP)
    return m


def _predict_clf(models: list, X: np.ndarray) -> np.ndarray:
    return np.column_stack([m.predict_proba(X)[:, 1] for m in models])


def _predict_reg(models: list, X: np.ndarray) -> np.ndarray:
    return np.column_stack([m.predict(X) for m in models])


def _generate_oof(
    X_tr: np.ndarray, y_tr: np.ndarray,
    task: str,  # "clf" or "reg"
) -> np.ndarray:
    """Generate OOF predictions from 3 base models via temporal inner CV."""
    n = len(X_tr)
    oof = np.full((n, 3), np.nan)
    tss = TimeSeriesSplit(n_splits=_INNER_FOLDS)
    for inner_tr, inner_te in tss.split(X_tr):
        Xi_tr, Xi_te = X_tr[inner_tr], X_tr[inner_te]
        yi_tr = y_tr[inner_tr]
        if task == "clf":
            ms = [_fit_xgb_clf(Xi_tr, yi_tr), _fit_lgbm_clf(Xi_tr, yi_tr), _fit_cb_clf(Xi_tr, yi_tr)]
            oof[inner_te] = _predict_clf(ms, Xi_te)
        else:
            ms = [_fit_xgb_reg(Xi_tr, yi_tr), _fit_lgbm_reg(Xi_tr, yi_tr), _fit_cb_reg(Xi_tr, yi_tr)]
            oof[inner_te] = _predict_reg(ms, Xi_te)
    return oof


def run_fold(fold_name: str) -> dict:
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

    vw, vr, vd = _valid(y_te_win), _valid(y_te_runs), _valid(y_te_diff)
    vw_tr, vr_tr, vd_tr = _valid(y_tr_win), _valid(y_tr_runs), _valid(y_tr_diff)

    t0 = time.time()

    # --- Win probability ---
    print(f"  [{fold_name}] Generating OOF predictions for win…", flush=True)
    oof_win = _generate_oof(X_tr[vw_tr], y_tr_win[vw_tr], "clf")
    valid_oof_w = ~np.isnan(oof_win).any(axis=1)
    meta_clf = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
    meta_clf.fit(oof_win[valid_oof_w], y_tr_win[vw_tr][valid_oof_w])

    print(f"  [{fold_name}] Fitting final base models for win…", flush=True)
    base_clfs = [
        _fit_xgb_clf(X_tr[vw_tr], y_tr_win[vw_tr]),
        _fit_lgbm_clf(X_tr[vw_tr], y_tr_win[vw_tr]),
        _fit_cb_clf(X_tr[vw_tr], y_tr_win[vw_tr]),
    ]
    meta_features_te_w = _predict_clf(base_clfs, X_te)
    p_win = meta_clf.predict_proba(meta_features_te_w)[:, 1]

    # --- Run differential ---
    print(f"  [{fold_name}] Generating OOF predictions for run_diff…", flush=True)
    oof_diff = _generate_oof(X_tr[vd_tr], y_tr_diff[vd_tr], "reg")
    valid_oof_d = ~np.isnan(oof_diff).any(axis=1)
    meta_reg_diff = Ridge(alpha=1.0)
    meta_reg_diff.fit(oof_diff[valid_oof_d], y_tr_diff[vd_tr][valid_oof_d])

    print(f"  [{fold_name}] Fitting final base models for run_diff…", flush=True)
    base_regs_diff = [
        _fit_xgb_reg(X_tr[vd_tr], y_tr_diff[vd_tr]),
        _fit_lgbm_reg(X_tr[vd_tr], y_tr_diff[vd_tr]),
        _fit_cb_reg(X_tr[vd_tr], y_tr_diff[vd_tr]),
    ]
    meta_features_te_d = _predict_reg(base_regs_diff, X_te)
    p_diff = meta_reg_diff.predict(meta_features_te_d)

    # --- Total runs ---
    print(f"  [{fold_name}] Generating OOF predictions for total_runs…", flush=True)
    oof_runs = _generate_oof(X_tr[vr_tr], y_tr_runs[vr_tr], "reg")
    valid_oof_r = ~np.isnan(oof_runs).any(axis=1)
    meta_reg_runs = Ridge(alpha=1.0)
    meta_reg_runs.fit(oof_runs[valid_oof_r], y_tr_runs[vr_tr][valid_oof_r])

    print(f"  [{fold_name}] Fitting final base models for total_runs…", flush=True)
    base_regs_runs = [
        _fit_xgb_reg(X_tr[vr_tr], y_tr_runs[vr_tr]),
        _fit_lgbm_reg(X_tr[vr_tr], y_tr_runs[vr_tr]),
        _fit_cb_reg(X_tr[vr_tr], y_tr_runs[vr_tr]),
    ]
    meta_features_te_r = _predict_reg(base_regs_runs, X_te)
    p_runs = meta_reg_runs.predict(meta_features_te_r)

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
    print("NOTE: This script trains 3 base models × 5 inner folds × 3 tasks × 4 outer folds.")
    print("Expected runtime: 20–60 min depending on hardware.\n")
    hdr = f"{'Fold':<12} {'Brier':>8} {'LogLoss':>9} {'H2H Edge':>10} {'%PosEdge':>10} {'RunsMAE':>9} {'RL ROI':>8} {'Time':>8}"
    print(hdr)
    print("-" * len(hdr))

    records = []
    for fold in [f["name"] for f in FOLDS]:
        r = run_fold(fold)
        records.append(r)
        print(
            f"{r['fold_name']:<12} {r['brier_score']:>8.4f} {r['log_loss']:>9.4f} "
            f"{r['mean_h2h_edge']:>+10.4f} {r['pct_positive_edge']:>10.4f} "
            f"{r['totals_mae']:>9.4f} {r['run_line_roi']:>+8.4f} {r['fit_time_seconds']:>7.1f}s"
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
