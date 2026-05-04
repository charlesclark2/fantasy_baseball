"""Card 7.MB — Market-blind evaluation: XGBoost + ElasticNet on walk-forward CV folds.

All market-derived columns (implied probabilities, moneylines, consensus odds,
sharp/soft signals, totals line) are excluded from the feature set. This gives
independent probability estimates that can be compared directly against the
market to produce genuine edge — the model's output is not anchored to what the
market already prices in.

Two models are evaluated:
  xgb_no_market    — XGBClassifier/XGBRegressor (baseline hyperparams)
  elastic_no_market — LogisticRegression(elasticnet) + Ridge with inner CV tuning

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_market_blind.py
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
from xgboost import XGBClassifier, XGBRegressor

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import (
    FOLDS, _NON_FEATURE_COLS,
    brier_score, log_loss_score, mean_h2h_edge, pct_positive_edge,
    totals_mae, run_line_roi,
)

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_NON_FEAT = _NON_FEATURE_COLS | {"split"}

# Columns derived from market odds — excluded to produce genuinely independent
# probability estimates. Edge = model_prob - market_implied_prob is meaningful
# only when the model has no direct access to the market signal it is being
# compared against.
_MARKET_COLS = {
    "home_win_prob_consensus", "home_win_prob_sharp", "home_win_prob_soft",
    "away_win_prob_consensus", "away_win_prob_sharp", "away_win_prob_soft",
    "home_moneyline_american", "home_moneyline_decimal",
    "away_moneyline_american", "away_moneyline_decimal",
    "home_implied_prob", "away_implied_prob",
    "market_bookmaker_count", "ml_consensus_std",
    "sharp_soft_ml_delta",
    "odds_hours_before_game",
    "over_american", "over_prob_consensus",
    "under_american",
    "total_line", "total_line_consensus", "total_line_std",
    "totals_market_vig",
}

_C_GRID = [0.001, 0.01, 0.1, 1.0]
_ALPHA_GRID = [0.1, 1.0, 10.0, 100.0]
_INNER_FOLDS = 5


def _load_fold(fold_name: str):
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{fold_name}.parquet")
    tgt  = pd.read_parquet(_OUTPUT_DIR / f"targets_{fold_name}.parquet")

    feat_cols = [
        c for c in feat.columns
        if c not in _NON_FEAT and c not in _MARKET_COLS
    ]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    te_f = feat[feat["split"] == "test"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)
    te_t = tgt[tgt["split"] == "test"].reset_index(drop=True)

    if "game_date" in tr_f.columns:
        sort_idx = tr_f["game_date"].argsort()
        tr_f = tr_f.iloc[sort_idx].reset_index(drop=True)
        tr_t = tr_t.iloc[sort_idx].reset_index(drop=True)

    # Market implied prob for edge calculation (test set only, not a feature)
    mkt = (
        te_f["home_implied_prob"].values.astype(np.float64)
        if "home_implied_prob" in te_f.columns
        else np.full(len(te_f), np.nan)
    )

    return feat_cols, tr_f, te_f, tr_t, te_t, mkt


def _valid(arr: np.ndarray) -> np.ndarray:
    return ~np.isnan(arr)


# ── XGBoost helpers ──────────────────────────────────────────────────────────

def _run_xgb(fold_name: str) -> dict:
    feat_cols, tr_f, te_f, tr_t, te_t, mkt = _load_fold(fold_name)

    X_tr = tr_f[feat_cols].values.astype(np.float32)
    X_te = te_f[feat_cols].values.astype(np.float32)
    y_tr_win  = tr_t["home_win"].values.astype(np.float32)
    y_te_win  = te_t["home_win"].values.astype(np.float32)
    y_tr_runs = tr_t["total_runs"].values.astype(np.float32)
    y_te_runs = te_t["total_runs"].values.astype(np.float32)
    y_tr_diff = tr_t["run_differential"].values.astype(np.float32)
    y_te_diff = te_t["run_differential"].values.astype(np.float32)

    vw, vr, vd = _valid(y_te_win), _valid(y_te_runs), _valid(y_te_diff)
    t0 = time.time()

    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
    )
    clf.fit(X_tr[_valid(y_tr_win)], y_tr_win[_valid(y_tr_win)])
    p_win = clf.predict_proba(X_te)[:, 1]

    reg_diff = XGBRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        tree_method="hist", random_state=42, n_jobs=-1,
    )
    reg_diff.fit(X_tr[_valid(y_tr_diff)], y_tr_diff[_valid(y_tr_diff)])
    p_diff = reg_diff.predict(X_te)

    reg_runs = XGBRegressor(
        n_estimators=200, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        tree_method="hist", random_state=42, n_jobs=-1,
    )
    reg_runs.fit(X_tr[_valid(y_tr_runs)], y_tr_runs[_valid(y_tr_runs)])
    p_runs = reg_runs.predict(X_te)

    fit_time = time.time() - t0
    vwd = vw & vd
    return {
        "fold_name": fold_name,
        "model_name": "xgb_no_market",
        "n_features": len(feat_cols),
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


# ── ElasticNet helpers ───────────────────────────────────────────────────────

def _build_preprocessor() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])


def _tune_logistic_C(X_tr: np.ndarray, y_tr: np.ndarray) -> float:
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


def _run_elastic(fold_name: str) -> dict:
    feat_cols, tr_f, te_f, tr_t, te_t, mkt = _load_fold(fold_name)

    X_tr_raw = tr_f[feat_cols].values.astype(np.float32)
    X_te_raw = te_f[feat_cols].values.astype(np.float32)
    y_tr_win  = tr_t["home_win"].values.astype(np.float32)
    y_te_win  = te_t["home_win"].values.astype(np.float32)
    y_tr_runs = tr_t["total_runs"].values.astype(np.float32)
    y_te_runs = te_t["total_runs"].values.astype(np.float32)
    y_tr_diff = tr_t["run_differential"].values.astype(np.float32)
    y_te_diff = te_t["run_differential"].values.astype(np.float32)

    vw, vr, vd = _valid(y_te_win), _valid(y_te_runs), _valid(y_te_diff)
    t0 = time.time()

    # win probability
    vw_tr = _valid(y_tr_win)
    X_tr_w, y_tr_w = X_tr_raw[vw_tr], y_tr_win[vw_tr]
    best_c = _tune_logistic_C(X_tr_w, y_tr_w)
    pre_clf = _build_preprocessor()
    X_tr_wp = pre_clf.fit_transform(X_tr_w)
    X_te_p  = pre_clf.transform(X_te_raw)
    clf = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5,
        C=best_c, max_iter=1000, random_state=42,
    )
    clf.fit(X_tr_wp, y_tr_w)
    p_win = clf.predict_proba(X_te_p)[:, 1]

    # run differential
    vd_tr = _valid(y_tr_diff)
    X_tr_d, y_tr_d = X_tr_raw[vd_tr], y_tr_diff[vd_tr]
    best_a_d = _tune_ridge_alpha(X_tr_d, y_tr_d)
    pre_diff = _build_preprocessor()
    X_tr_dp = pre_diff.fit_transform(X_tr_d)
    X_te_dp = pre_diff.transform(X_te_raw)
    reg_diff = Ridge(alpha=best_a_d, random_state=42)
    reg_diff.fit(X_tr_dp, y_tr_d)
    p_diff = reg_diff.predict(X_te_dp)

    # total runs
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
        "model_name": "elastic_no_market",
        "n_features": len(feat_cols),
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


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    fold_names = [f["name"] for f in FOLDS]

    for model_label, run_fn, model_name in [
        ("XGBoost (market-blind)",    _run_xgb,     "xgb_no_market"),
        ("ElasticNet (market-blind)", _run_elastic, "elastic_no_market"),
    ]:
        print(f"\n=== {model_label.upper()} — Walk-Forward CV Evaluation ===")
        print(f"  (18 market columns excluded from feature set)\n")
        hdr = f"{'Fold':<12} {'#Feats':>7} {'Brier':>8} {'LogLoss':>9} {'H2H Edge':>10} {'%PosEdge':>10} {'RunsMAE':>9} {'RL ROI':>8} {'Time':>7}"
        print(hdr)
        print("-" * len(hdr))

        records = []
        for fold in fold_names:
            r = run_fn(fold)
            records.append(r)
            print(
                f"{r['fold_name']:<12} {r['n_features']:>7} {r['brier_score']:>8.4f} "
                f"{r['log_loss']:>9.4f} {r['mean_h2h_edge']:>+10.4f} "
                f"{r['pct_positive_edge']:>10.4f} {r['totals_mae']:>9.4f} "
                f"{r['run_line_roi']:>+8.4f} {r['fit_time_seconds']:>6.1f}s"
            )

        df = pd.DataFrame(records)
        out = _OUTPUT_DIR / f"results_{model_name}.parquet"
        df.to_parquet(out, index=False)

        print(
            f"\n{'MEAN':<12} {'':>7} {df['brier_score'].mean():>8.4f} "
            f"{df['log_loss'].mean():>9.4f} {df['mean_h2h_edge'].mean():>+10.4f} "
            f"{df['pct_positive_edge'].mean():>10.4f} {df['totals_mae'].mean():>9.4f} "
            f"{df['run_line_roi'].mean():>+8.4f}"
        )
        print(f"Results written to {out}")


if __name__ == "__main__":
    main()
