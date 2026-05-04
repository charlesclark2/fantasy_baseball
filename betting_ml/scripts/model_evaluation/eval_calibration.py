"""Card 7.MB Task 4a — Calibration analysis across top candidate models.

For each model × fold:
  1. Fit model on first 85% of training rows (chronological).
  2. Use last 15% as calibration holdout — get raw p_win predictions.
  3. Fit IsotonicRegression and Platt (sigmoid LogisticRegression) on holdout.
  4. Predict raw, isotonic-calibrated, and Platt-calibrated on test split.
  5. Compute Expected Calibration Error (ECE, 10-bin) and Brier for each.

Question being answered: does adding a calibration layer improve ECE, and
which calibration method works better? This informs whether the Platt
calibrator in predict_today.py should be kept, replaced, or removed.

Models evaluated:
  elasticnet       — market-aware; best Brier across all runs
  elastic_no_market — market-blind; best edge story
  xgb_no_market    — market-blind XGBoost; best mean H2H edge
  catboost         — best tree model on Brier (market-aware)

Usage:
    uv run python betting_ml/scripts/model_evaluation/eval_calibration.py
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
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import FOLDS, _NON_FEATURE_COLS

_OUTPUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "model_evaluation"
_NON_FEAT = _NON_FEATURE_COLS | {"split"}
_CAL_FRAC = 0.15   # fraction of training set reserved for calibration fitting
_N_BINS   = 10
_INNER_FOLDS = 5
_C_GRID   = [0.001, 0.01, 0.1, 1.0]
_ALPHA_GRID = [0.1, 1.0, 10.0, 100.0]

_MARKET_COLS = {
    "home_win_prob_consensus", "home_win_prob_sharp", "home_win_prob_soft",
    "away_win_prob_consensus", "away_win_prob_sharp", "away_win_prob_soft",
    "home_moneyline_american", "home_moneyline_decimal",
    "away_moneyline_american", "away_moneyline_decimal",
    "home_implied_prob", "away_implied_prob",
    "market_bookmaker_count", "ml_consensus_std",
    "sharp_soft_ml_delta", "odds_hours_before_game",
    "over_american", "over_prob_consensus", "under_american",
    "total_line", "total_line_consensus", "total_line_std",
    "totals_market_vig",
}


# ── Calibration utilities ────────────────────────────────────────────────────

def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = _N_BINS) -> float:
    """Expected Calibration Error (uniform-width bins)."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        acc  = y_true[mask].mean()
        conf = y_prob[mask].mean()
        ece += (mask.sum() / n) * abs(acc - conf)
    return float(ece)


def _apply_isotonic(p_cal: np.ndarray, y_cal: np.ndarray,
                    p_te: np.ndarray) -> np.ndarray:
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p_cal, y_cal)
    return np.clip(iso.predict(p_te), 1e-7, 1 - 1e-7)


def _apply_platt(p_cal: np.ndarray, y_cal: np.ndarray,
                 p_te: np.ndarray) -> np.ndarray:
    """Platt scaling: LogisticRegression on logit of raw probabilities."""
    logit_cal = np.log(np.clip(p_cal, 1e-7, 1 - 1e-7) /
                       (1 - np.clip(p_cal, 1e-7, 1 - 1e-7))).reshape(-1, 1)
    logit_te  = np.log(np.clip(p_te,  1e-7, 1 - 1e-7) /
                       (1 - np.clip(p_te,  1e-7, 1 - 1e-7))).reshape(-1, 1)
    platt = LogisticRegression(C=1e10, random_state=42)
    platt.fit(logit_cal, y_cal)
    return np.clip(platt.predict_proba(logit_te)[:, 1], 1e-7, 1 - 1e-7)


def _cal_split(X: np.ndarray, y: np.ndarray):
    """Temporal split: first (1-_CAL_FRAC) for model fit, rest for calibration."""
    n_cal = max(1, int(len(X) * _CAL_FRAC))
    return X[:-n_cal], X[-n_cal:], y[:-n_cal], y[-n_cal:]


def _record(model_name, fold_name, n_feat, p_raw, p_iso, p_platt,
            y_te, fit_time) -> dict:
    return {
        "model_name":   model_name,
        "fold_name":    fold_name,
        "n_features":   n_feat,
        "ece_raw":      _ece(y_te, p_raw),
        "ece_isotonic": _ece(y_te, p_iso),
        "ece_platt":    _ece(y_te, p_platt),
        "brier_raw":    float(brier_score_loss(y_te, p_raw)),
        "brier_isotonic": float(brier_score_loss(y_te, p_iso)),
        "brier_platt":  float(brier_score_loss(y_te, p_platt)),
        "fit_time_seconds": fit_time,
    }


# ── Data loading ─────────────────────────────────────────────────────────────

def _load_fold(fold_name: str, market_blind: bool):
    feat = pd.read_parquet(_OUTPUT_DIR / f"features_{fold_name}.parquet")
    tgt  = pd.read_parquet(_OUTPUT_DIR / f"targets_{fold_name}.parquet")

    exclude = _NON_FEAT | (_MARKET_COLS if market_blind else set())
    feat_cols = [c for c in feat.columns if c not in exclude]

    tr_f = feat[feat["split"] == "train"].reset_index(drop=True)
    te_f = feat[feat["split"] == "test"].reset_index(drop=True)
    tr_t = tgt[tgt["split"] == "train"].reset_index(drop=True)
    te_t = tgt[tgt["split"] == "test"].reset_index(drop=True)

    if "game_date" in tr_f.columns:
        idx = tr_f["game_date"].argsort()
        tr_f = tr_f.iloc[idx].reset_index(drop=True)
        tr_t = tr_t.iloc[idx].reset_index(drop=True)

    X_tr = tr_f[feat_cols].values.astype(np.float32)
    X_te = te_f[feat_cols].values.astype(np.float32)
    y_tr = tr_t["home_win"].values.astype(np.float32)
    y_te = te_t["home_win"].values.astype(np.float32)

    valid_tr = ~np.isnan(y_tr)
    valid_te = ~np.isnan(y_te)
    return feat_cols, X_tr[valid_tr], y_tr[valid_tr], X_te[valid_te], y_te[valid_te]


# ── Model-specific calibration runs ─────────────────────────────────────────

def _run_xgb_no_market(fold_name: str) -> dict:
    feat_cols, X_tr, y_tr, X_te, y_te = _load_fold(fold_name, market_blind=True)
    X_fit, X_cal, y_fit, y_cal = _cal_split(X_tr, y_tr)

    t0 = time.time()
    clf = XGBClassifier(
        n_estimators=400, max_depth=5, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        eval_metric="logloss", random_state=42, n_jobs=-1,
    )
    clf.fit(X_fit, y_fit)
    fit_time = time.time() - t0

    p_cal_raw = clf.predict_proba(X_cal)[:, 1]
    p_raw     = clf.predict_proba(X_te)[:, 1]
    p_iso     = _apply_isotonic(p_cal_raw, y_cal, p_raw)
    p_platt   = _apply_platt(p_cal_raw, y_cal, p_raw)

    return _record("xgb_no_market", fold_name, len(feat_cols),
                   p_raw, p_iso, p_platt, y_te, fit_time)


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


def _run_elastic(fold_name: str, market_blind: bool, model_name: str) -> dict:
    feat_cols, X_tr, y_tr, X_te, y_te = _load_fold(fold_name, market_blind=market_blind)
    X_fit, X_cal, y_fit, y_cal = _cal_split(X_tr, y_tr)

    t0 = time.time()
    best_c = _tune_logistic_C(X_fit, y_fit)
    pre = _build_preprocessor()
    X_fit_p = pre.fit_transform(X_fit)
    X_cal_p = pre.transform(X_cal)
    X_te_p  = pre.transform(X_te)
    clf = LogisticRegression(
        penalty="elasticnet", solver="saga", l1_ratio=0.5,
        C=best_c, max_iter=1000, random_state=42,
    )
    clf.fit(X_fit_p, y_fit)
    fit_time = time.time() - t0

    p_cal_raw = clf.predict_proba(X_cal_p)[:, 1]
    p_raw     = clf.predict_proba(X_te_p)[:, 1]
    p_iso     = _apply_isotonic(p_cal_raw, y_cal, p_raw)
    p_platt   = _apply_platt(p_cal_raw, y_cal, p_raw)

    return _record(model_name, fold_name, len(feat_cols),
                   p_raw, p_iso, p_platt, y_te, fit_time)


def _run_catboost(fold_name: str) -> dict:
    from catboost import CatBoostClassifier, Pool
    feat_cols, X_tr, y_tr, X_te, y_te = _load_fold(fold_name, market_blind=False)
    X_fit, X_cal, y_fit, y_cal = _cal_split(X_tr, y_tr)

    t0 = time.time()
    clf = CatBoostClassifier(
        iterations=500, learning_rate=0.05, depth=6,
        loss_function="Logloss", verbose=0, random_seed=42,
    )
    clf.fit(X_fit, y_fit,
            eval_set=Pool(X_cal, y_cal),
            early_stopping_rounds=50)
    fit_time = time.time() - t0

    p_cal_raw = clf.predict_proba(X_cal)[:, 1]
    p_raw     = clf.predict_proba(X_te)[:, 1]
    p_iso     = _apply_isotonic(p_cal_raw, y_cal, p_raw)
    p_platt   = _apply_platt(p_cal_raw, y_cal, p_raw)

    return _record("catboost", fold_name, len(feat_cols),
                   p_raw, p_iso, p_platt, y_te, fit_time)


# ── Main ─────────────────────────────────────────────────────────────────────

_MODELS = [
    ("xgb_no_market",     lambda f: _run_xgb_no_market(f)),
    ("elastic_no_market", lambda f: _run_elastic(f, market_blind=True,  model_name="elastic_no_market")),
    ("elasticnet",        lambda f: _run_elastic(f, market_blind=False, model_name="elasticnet")),
    ("catboost",          lambda f: _run_catboost(f)),
]


def main() -> None:
    print("=== Calibration Analysis — Raw vs Isotonic vs Platt ===")
    print(f"Calibration holdout: last {int(_CAL_FRAC*100)}% of training rows (temporal)\n")

    fold_names = [f["name"] for f in FOLDS]
    hdr = (f"{'Model':<22} {'Fold':<12} "
           f"{'ECE raw':>9} {'ECE iso':>9} {'ECE platt':>10} "
           f"{'Brier raw':>10} {'Brier iso':>10} {'Brier platt':>12} {'Time':>7}")
    print(hdr)
    print("-" * len(hdr))

    records = []
    for model_name, run_fn in _MODELS:
        for fold in fold_names:
            print(f"  fitting {model_name} / {fold}…", flush=True)
            r = run_fn(fold)
            records.append(r)
            print(
                f"{r['model_name']:<22} {r['fold_name']:<12} "
                f"{r['ece_raw']:>9.4f} {r['ece_isotonic']:>9.4f} {r['ece_platt']:>10.4f} "
                f"{r['brier_raw']:>10.4f} {r['brier_isotonic']:>10.4f} {r['brier_platt']:>12.4f} "
                f"{r['fit_time_seconds']:>6.1f}s"
            )

    df = pd.DataFrame(records)
    out = _OUTPUT_DIR / "results_calibration.parquet"
    df.to_parquet(out, index=False)

    print(f"\n{'='*40}")
    print("MEAN by model:")
    mean_cols = ["ece_raw","ece_isotonic","ece_platt","brier_raw","brier_isotonic","brier_platt"]
    summary = df.groupby("model_name")[mean_cols].mean().round(4)
    print(summary.to_string())
    print(f"\nResults written to {out}")


if __name__ == "__main__":
    main()
