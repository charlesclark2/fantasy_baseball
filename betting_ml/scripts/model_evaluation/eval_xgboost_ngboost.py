"""Card 7.MB — Baseline evaluation: XGBoost + NGBoost on walk-forward CV folds.

XGBoost (production hyperparams) is used for all three tasks.
NGBoost is evaluated optionally via --include-ngboost (slow: ~1hr per fold).

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_xgboost_ngboost.py
    uv run python betting_ml/scripts/model_evaluation/eval_xgboost_ngboost.py --include-ngboost
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from xgboost import XGBClassifier, XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import (
    FOLDS, _NON_FEATURE_COLS,
    brier_score, log_loss_score, mean_h2h_edge, pct_positive_edge,
    totals_mae, run_line_roi,
)

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_MODEL_NAME = "xgboost_ngboost"

_NON_FEAT = _NON_FEATURE_COLS | {"split"}


def _load_fold(fold_name: str):
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{fold_name}.parquet")
    tgt = pd.read_parquet(_OUTPUT_DIR / f"targets_{fold_name}.parquet")

    feat_cols = [c for c in feat.columns if c not in _NON_FEAT]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    te_f = feat[feat["split"] == "test"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)
    te_t = tgt[tgt["split"] == "test"].reset_index(drop=True)

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

    return X_tr, X_te, y_tr_win, y_te_win, y_tr_runs, y_te_runs, y_tr_diff, y_te_diff, mkt, len(tr_f), len(te_f)


def _valid(arr: np.ndarray) -> np.ndarray:
    return ~np.isnan(arr)


def run_fold(fold_name: str, include_ngboost: bool = False) -> dict:
    X_tr, X_te, y_tr_win, y_te_win, y_tr_runs, y_te_runs, y_tr_diff, y_te_diff, mkt, n_train, n_test = _load_fold(fold_name)

    vw = _valid(y_te_win)
    vr = _valid(y_te_runs)
    vd = _valid(y_te_diff)

    t0 = time.time()

    # ---------- win probability: XGBClassifier ----------
    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
    )
    clf.fit(X_tr[_valid(y_tr_win)], y_tr_win[_valid(y_tr_win)])
    p_win = clf.predict_proba(X_te)[:, 1]

    # ---------- run differential: XGBRegressor ----------
    reg_diff = XGBRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        tree_method="hist", random_state=42, n_jobs=-1,
    )
    reg_diff.fit(X_tr[_valid(y_tr_diff)], y_tr_diff[_valid(y_tr_diff)])
    p_diff = reg_diff.predict(X_te)

    # ---------- total runs: XGBRegressor ----------
    reg_runs = XGBRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        tree_method="hist", random_state=42, n_jobs=-1,
    )
    reg_runs.fit(X_tr[_valid(y_tr_runs)], y_tr_runs[_valid(y_tr_runs)])
    p_runs = reg_runs.predict(X_te)

    # ---------- optional NGBoost for runs/diff ----------
    if include_ngboost:
        from ngboost import NGBRegressor
        from ngboost.distns import Normal
        from sklearn.impute import SimpleImputer

        imp = SimpleImputer(strategy="median")
        X_tr_imp = imp.fit_transform(X_tr)
        X_te_imp = imp.transform(X_te)

        ngb_diff = NGBRegressor(Dist=Normal, n_estimators=300, learning_rate=0.1, random_state=42, verbose=False)
        vd_tr = _valid(y_tr_diff)
        ngb_diff.fit(X_tr_imp[vd_tr], y_tr_diff[vd_tr])
        p_diff = ngb_diff.predict(X_te_imp)

        ngb_runs = NGBRegressor(Dist=Normal, n_estimators=300, learning_rate=0.1, random_state=42, verbose=False)
        vr_tr = _valid(y_tr_runs)
        ngb_runs.fit(X_tr_imp[vr_tr], y_tr_runs[vr_tr])
        p_runs = ngb_runs.predict(X_te_imp)

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
        "train_rows": n_train,
        "test_rows": n_test,
        "fit_time_seconds": fit_time,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-ngboost", action="store_true",
                        help="Also fit NGBoost for runs/diff targets (slow)")
    args = parser.parse_args()

    print(f"=== {_MODEL_NAME.upper()} — Walk-Forward CV Evaluation ===\n")
    hdr = f"{'Fold':<12} {'Brier':>8} {'LogLoss':>9} {'H2H Edge':>10} {'%PosEdge':>10} {'RunsMAE':>9} {'RL ROI':>8} {'Time':>7}"
    print(hdr)
    print("-" * len(hdr))

    records = []
    for fold in [f["name"] for f in FOLDS]:
        r = run_fold(fold, include_ngboost=args.include_ngboost)
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
