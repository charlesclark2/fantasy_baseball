"""Card 7.MB — ElasticNet (linear baseline) evaluation on walk-forward CV folds.

LogisticRegression (elasticnet penalty) for win probability.
Ridge regression for total runs and run differential.
C and alpha tuned via 5-fold inner time-series CV.

Literature reference: Cui (2020) Wharton thesis found ElasticNet logistic
regression achieves 61.77% accuracy / AUC 0.67 at ~10K MLB sample sizes,
outperforming XGBoost. This validates whether a fast linear model matches
gradient boosting on our feature set.

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_elasticnet.py
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

from sklearn.exceptions import ConvergenceWarning
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=ConvergenceWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import (
    FOLDS, _NON_FEATURE_COLS,
    brier_score, log_loss_score, mean_h2h_edge, pct_positive_edge,
    totals_mae, run_line_roi,
)

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_MODEL_NAME = "elasticnet"
_NON_FEAT = _NON_FEATURE_COLS | {"split"}

_C_GRID = [0.001, 0.01, 0.1, 1.0]
_ALPHA_GRID = [0.1, 1.0, 10.0, 100.0]
_INNER_FOLDS = 5


def _load_fold(fold_name: str):
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{fold_name}.parquet")
    tgt = pd.read_parquet(_OUTPUT_DIR / f"targets_{fold_name}.parquet")

    feat_cols = [c for c in feat.columns if c not in _NON_FEAT]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    te_f = feat[feat["split"] == "test"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)
    te_t = tgt[tgt["split"] == "test"].reset_index(drop=True)

    # Temporal sort for inner CV (chrono order required for TimeSeriesSplit)
    if "game_date" in tr_f.columns:
        sort_idx = tr_f["game_date"].argsort()
        tr_f = tr_f.iloc[sort_idx].reset_index(drop=True)
        tr_t = tr_t.iloc[sort_idx].reset_index(drop=True)

    return feat_cols, tr_f, te_f, tr_t, te_t


def _valid(arr: np.ndarray) -> np.ndarray:
    return ~np.isnan(arr)


def _build_preprocessor() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])


def _tune_logistic_C(X_tr: np.ndarray, y_tr: np.ndarray) -> float:
    """Return best C via inner time-series CV on log-loss."""
    tss = TimeSeriesSplit(n_splits=_INNER_FOLDS)
    best_c, best_ll = _C_GRID[0], float("inf")
    for c in _C_GRID:
        lls = []
        for inner_tr, inner_te in tss.split(X_tr):
            Xi_tr, Xi_te = X_tr[inner_tr], X_tr[inner_te]
            yi_tr, yi_te = y_tr[inner_tr], y_tr[inner_te]
            pre = _build_preprocessor()
            Xi_tr_p = pre.fit_transform(Xi_tr)
            Xi_te_p = pre.transform(Xi_te)
            clf = LogisticRegression(
                penalty="elasticnet", solver="saga", l1_ratio=0.5,
                C=c, max_iter=1000, random_state=42,
            )
            clf.fit(Xi_tr_p, yi_tr)
            p = np.clip(clf.predict_proba(Xi_te_p)[:, 1], 1e-7, 1 - 1e-7)
            ll = float(-np.mean(yi_te * np.log(p) + (1 - yi_te) * np.log(1 - p)))
            lls.append(ll)
        mean_ll = float(np.mean(lls))
        if mean_ll < best_ll:
            best_ll, best_c = mean_ll, c
    return best_c


def _tune_ridge_alpha(X_tr: np.ndarray, y_tr: np.ndarray) -> float:
    """Return best alpha via inner time-series CV on MAE."""
    tss = TimeSeriesSplit(n_splits=_INNER_FOLDS)
    best_a, best_mae = _ALPHA_GRID[0], float("inf")
    for a in _ALPHA_GRID:
        maes = []
        for inner_tr, inner_te in tss.split(X_tr):
            Xi_tr, Xi_te = X_tr[inner_tr], X_tr[inner_te]
            yi_tr, yi_te = y_tr[inner_tr], y_tr[inner_te]
            pre = _build_preprocessor()
            Xi_tr_p = pre.fit_transform(Xi_tr)
            Xi_te_p = pre.transform(Xi_te)
            reg = Ridge(alpha=a, random_state=42)
            reg.fit(Xi_tr_p, yi_tr)
            mae = float(np.mean(np.abs(yi_te - reg.predict(Xi_te_p))))
            maes.append(mae)
        mean_mae = float(np.mean(maes))
        if mean_mae < best_mae:
            best_mae, best_a = mean_mae, a
    return best_a


def run_fold(fold_name: str) -> dict:
    feat_cols, tr_f, te_f, tr_t, te_t = _load_fold(fold_name)

    X_tr_raw = tr_f[feat_cols].values.astype(np.float32)
    X_te_raw = te_f[feat_cols].values.astype(np.float32)
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

    t0 = time.time()

    # ---------- win probability: LogisticRegression (ElasticNet) ----------
    vw_tr = _valid(y_tr_win)
    X_tr_w, y_tr_w = X_tr_raw[vw_tr], y_tr_win[vw_tr]
    best_c = _tune_logistic_C(X_tr_w, y_tr_w)
    pre_clf = _build_preprocessor()
    X_tr_wp = pre_clf.fit_transform(X_tr_w)
    X_te_p = pre_clf.transform(X_te_raw)
    clf = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5,
        C=best_c, max_iter=1000, random_state=42,
    )
    clf.fit(X_tr_wp, y_tr_w)
    p_win = clf.predict_proba(X_te_p)[:, 1]

    # ---------- run differential: Ridge ----------
    vd_tr = _valid(y_tr_diff)
    X_tr_d, y_tr_d = X_tr_raw[vd_tr], y_tr_diff[vd_tr]
    best_a_d = _tune_ridge_alpha(X_tr_d, y_tr_d)
    pre_diff = _build_preprocessor()
    X_tr_dp = pre_diff.fit_transform(X_tr_d)
    X_te_dp = pre_diff.transform(X_te_raw)
    reg_diff = Ridge(alpha=best_a_d, random_state=42)
    reg_diff.fit(X_tr_dp, y_tr_d)
    p_diff = reg_diff.predict(X_te_dp)

    # ---------- total runs: Ridge ----------
    vr_tr = _valid(y_tr_runs)
    X_tr_r, y_tr_r = X_tr_raw[vr_tr], y_tr_runs[vr_tr]
    best_a_r = _tune_ridge_alpha(X_tr_r, y_tr_r)
    pre_runs = _build_preprocessor()
    X_tr_rp = pre_runs.fit_transform(X_tr_r)
    X_te_rp = pre_runs.transform(X_te_raw)
    reg_runs = Ridge(alpha=best_a_r, random_state=42)
    reg_runs.fit(X_tr_rp, y_tr_r)
    p_runs = reg_runs.predict(X_te_rp)

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
