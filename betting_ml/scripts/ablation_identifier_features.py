"""Story 30.1 — identifier/temporal feature-hygiene ABLATION.

Controlled ablation: hold each production v4 model's ARCHITECTURE fixed (the
tuned champion hyperparameters) and vary ONLY the feature set —
    champion  = the full *_tuned_2026.json contract (379 features)
    ablated   = champion minus the identifier/temporal columns flagged by
                betting_ml.utils.feature_hygiene (home_starter_pitcher_id,
                venue_id, game_year)
Both are scored on:
  1. Walk-forward temporal CV  (all_season_splits, min_train_seasons=3)
  2. The HONEST 2026 out-of-sample surface (train game_year < 2026, eval == 2026)

Per the Epic 30 operator directive, the PRIMARY metric is accuracy-to-truth:
  - totals / run_diff : MAE, RMSE, MedAE vs the actual outcome (+ calib_80 for
                        the NGBoost distribution).
  - home_win          : Brier, NLL (log-loss), accuracy, ECE, and live corr of
                        P(home win) vs the 0/1 outcome (the zero-skill probe).
Market comparison is reported as SECONDARY context only — never the gate.

Why this is the right ablation: a memorized identifier scores as "important"
(home_starter_pitcher_id is SHAP #12; shuffling it HURTS CV MAE), so importance
filters cannot catch it. `game_year` is the worst case — trained on 2021-2025,
served as the constant 2026 (out-of-distribution). The 2026 surface is where
that OOD penalty actually shows up.

Runtime: this RETRAINS NGBoost (run_diff/total_runs) and XGBoost (home_win) per
fold for two feature sets — minutes, not seconds. Per project convention, hand
this off to be run with real Snowflake credentials; do not block on it.

Usage:
    uv run python betting_ml/scripts/ablation_identifier_features.py --target all
    uv run python betting_ml/scripts/ablation_identifier_features.py --target home_win
    uv run python betting_ml/scripts/ablation_identifier_features.py --target run_diff
    uv run python betting_ml/scripts/ablation_identifier_features.py --target total_runs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.preprocessing import build_imputation_pipeline

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "ablation_identifier"

# ── Champion contracts + fixed (tuned) hyperparameters ──────────────────────
# Hyperparameters copied verbatim from the persisted tuning results so the
# ablation varies ONLY the feature set:
#   betting_ml/evaluation/tuning_results_xgb_home_win.json
#   betting_ml/evaluation/tuning_results_ngboost_run_diff.json   (n_est 500, Normal)
#   betting_ml/evaluation/tuning_results_ngboost_total_runs.json (n_est 500, Normal)
_TARGETS = {
    "home_win": {
        "kind": "classification",
        "target_col": "home_win",
        "contract": "betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json",
        "xgb_params": {
            "max_depth": 6,
            "learning_rate": 0.04382008396889068,
            "n_estimators": 319,
            "subsample": 0.8703615621723709,
            "colsample_bytree": 0.9213036632642531,
            "reg_alpha": 0.5674150208954939,
            "reg_lambda": 0.8659314047407293,
            "eval_metric": "logloss",
            "tree_method": "hist",
            "random_state": 42,
            "n_jobs": -1,
        },
    },
    "run_diff": {
        "kind": "regression",
        "target_col": "run_differential",
        "contract": "betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json",
        "ngb": {"n_estimators": 500, "dist": "Normal"},
    },
    "total_runs": {
        "kind": "regression",
        "target_col": "total_runs",
        "contract": "betting_ml/models/total_runs/feature_columns_ngboost_tuned_2026.json",
        "ngb": {"n_estimators": 500, "dist": "Normal"},
    },
}

_CV_TOL = {"mae": 0.01, "brier": 0.001}  # max tolerated CV regression to still PROMOTE


# ── Metrics ─────────────────────────────────────────────────────────────────

def _reg_metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    err = pred - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "medae": float(np.median(np.abs(err))),
        "mean_pred": float(np.mean(pred)),
        "mean_actual": float(np.mean(y)),
        "bias": float(np.mean(err)),
        "pred_std": float(np.std(pred)),
    }


def _calib_80_normal(loc: np.ndarray, scale: np.ndarray, y: np.ndarray) -> float:
    """Empirical coverage of the NGBoost Normal central 80% interval."""
    z = 1.2815515594457831  # Phi^-1(0.90)
    lo, hi = loc - z * scale, loc + z * scale
    return float(np.mean((y >= lo) & (y <= hi)))


def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        ece += (m.sum() / len(p)) * abs(p[m].mean() - y[m].mean())
    return float(ece)


def _clf_metrics(y: np.ndarray, p: np.ndarray) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss
    pc = np.clip(p, 1e-7, 1 - 1e-7)
    corr = float(np.corrcoef(p, y)[0, 1]) if np.std(p) > 0 else float("nan")
    return {
        "brier": float(brier_score_loss(y, p)),
        "nll": float(log_loss(y, pc)),
        "accuracy": float(np.mean((p >= 0.5).astype(int) == y)),
        "ece": _ece(p, y),
        "live_corr": corr,
        "pred_std": float(np.std(p)),
    }


# ── Model fit/predict per kind ──────────────────────────────────────────────

def _impute(train_raw: pd.DataFrame, eval_raw: pd.DataFrame):
    pipe = build_imputation_pipeline()
    Xtr = pipe.fit_transform(train_raw).select_dtypes(include=[np.number])
    Xev = pipe.transform(eval_raw)
    Xev = Xev[[c for c in Xtr.columns if c in Xev.columns]].reindex(columns=Xtr.columns, fill_value=0.0)
    return Xtr, Xev


def _fit_predict_regression(cfg, Xtr, ytr, Xev):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    dist = {"Normal": Normal}[cfg["ngb"]["dist"]]
    m = NGBRegressor(n_estimators=cfg["ngb"]["n_estimators"], Dist=dist, verbose=False)
    m.fit(Xtr.values, ytr)
    pred = m.predict(Xev.values)
    try:
        params = m.pred_dist(Xev.values).params
        loc, scale = np.asarray(params["loc"]), np.asarray(params["scale"])
    except Exception:
        loc, scale = pred, None
    return pred, loc, scale


def _fit_predict_classification(cfg, Xtr, ytr, Xev, yev):
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier
    clf = XGBClassifier(**cfg["xgb_params"])
    clf.fit(Xtr, ytr.astype(int))
    raw = clf.predict_proba(Xev)[:, 1]
    # Platt calibration fit on the eval split (faithful to production recipe).
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(raw.reshape(-1, 1), yev.astype(int))
    return cal.predict_proba(raw.reshape(-1, 1))[:, 1]


# ── Evaluation surfaces ─────────────────────────────────────────────────────

def _eval_one(df, cfg, feat_cols, train_idx, eval_idx):
    Xtr, Xev = _impute(df.loc[train_idx, feat_cols], df.loc[eval_idx, feat_cols])
    ytr = df.loc[train_idx, cfg["target_col"]].values
    yev = df.loc[eval_idx, cfg["target_col"]].values
    if cfg["kind"] == "regression":
        pred, loc, scale = _fit_predict_regression(cfg, Xtr, ytr, Xev)
        m = _reg_metrics(yev, pred)
        if scale is not None:
            m["calib_80"] = _calib_80_normal(loc, scale, yev)
        return m
    p = _fit_predict_classification(cfg, Xtr, ytr, Xev, yev)
    return _clf_metrics(yev, p)


def _run_cv(df, cfg, champ_cols, abl_cols):
    champ_folds, abl_folds = [], []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        eval_year = int(df.loc[eval_idx, "game_year"].mode()[0])
        cm = _eval_one(df, cfg, champ_cols, train_idx, eval_idx)
        am = _eval_one(df, cfg, abl_cols, train_idx, eval_idx)
        cm["eval_year"] = am["eval_year"] = eval_year
        champ_folds.append(cm)
        abl_folds.append(am)
        prim = "brier" if cfg["kind"] == "classification" else "mae"
        print(f"    fold {eval_year}: champ {prim}={cm[prim]:.4f}  ablated {prim}={am[prim]:.4f}")
    return champ_folds, abl_folds


def _mean_over_folds(folds, keys):
    return {k: float(np.mean([f[k] for f in folds if k in f])) for k in keys}


def _run_target(name: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[name]
    contract = json.loads((PROJECT_ROOT / cfg["contract"]).read_text())
    champ_cols_all = contract["feature_cols"]
    champ_cols = [c for c in champ_cols_all if c in df.columns]
    dropped = [c for c in champ_cols if is_identifier_name(c)]
    abl_cols = [c for c in champ_cols if not is_identifier_name(c)]

    print(f"\n=== {name} ({cfg['kind']}) ===")
    print(f"  contract features: {len(champ_cols_all)}  present-in-df: {len(champ_cols)}")
    print(f"  identifier/temporal dropped ({len(dropped)}): {dropped}")
    print(f"  champion feats: {len(champ_cols)}  ablated feats: {len(abl_cols)}")

    prim = "brier" if cfg["kind"] == "classification" else "mae"
    metric_keys = (["brier", "nll", "accuracy", "ece", "live_corr", "pred_std"]
                   if cfg["kind"] == "classification"
                   else ["mae", "rmse", "medae", "bias", "pred_std", "calib_80"])

    print("  -- walk-forward CV --")
    champ_folds, abl_folds = _run_cv(df, cfg, champ_cols, abl_cols)
    cv_champ = _mean_over_folds(champ_folds, metric_keys)
    cv_abl = _mean_over_folds(abl_folds, metric_keys)

    print("  -- honest 2026 OOS --")
    tr = df.index[df["game_year"] < 2026]
    ev = df.index[df["game_year"] == 2026]
    if len(ev) == 0:
        print("    WARNING: no 2026 rows in load_features() — skipping live surface.")
        live_champ = live_abl = {}
    else:
        print(f"    train n={len(tr)} (<=2025), eval n={len(ev)} (2026)")
        live_champ = _eval_one(df, cfg, champ_cols, tr, ev)
        live_abl = _eval_one(df, cfg, abl_cols, tr, ev)

    cv_delta = cv_abl[prim] - cv_champ[prim]            # >0 = ablated worse on CV
    cv_regressed = cv_delta > _CV_TOL[prim]
    # Decision: PROMOTE if no CV regression beyond tolerance (OOD/memorization
    # risk is removed structurally by dropping game_year + the raw IDs).
    decision = "KEEP (CV regression — review)" if cv_regressed else "PROMOTE (ablated)"

    result = {
        "target": name,
        "kind": cfg["kind"],
        "primary_metric": prim,
        "n_features_champion": len(champ_cols),
        "n_features_ablated": len(abl_cols),
        "dropped_features": dropped,
        "cv": {"champion": cv_champ, "ablated": cv_abl,
               "delta_primary": cv_delta, "regressed": bool(cv_regressed),
               "folds_champion": champ_folds, "folds_ablated": abl_folds},
        "live_2026": {"champion": live_champ, "ablated": live_abl},
        "decision": decision,
    }

    print(f"  CV {prim}: champ={cv_champ[prim]:.4f}  ablated={cv_abl[prim]:.4f}  "
          f"delta={cv_delta:+.4f}  -> {decision}")
    if live_champ:
        if cfg["kind"] == "classification":
            print(f"  LIVE 2026: champ Brier={live_champ['brier']:.4f}/corr={live_champ['live_corr']:.4f}  "
                  f"ablated Brier={live_abl['brier']:.4f}/corr={live_abl['live_corr']:.4f}")
        else:
            print(f"  LIVE 2026: champ MAE={live_champ['mae']:.4f}  ablated MAE={live_abl['mae']:.4f}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    args = ap.parse_args()

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].dropna().unique().tolist())}")

    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]
    results = {}
    for name in targets:
        results[name] = _run_target(name, df)

    out = _OUT_DIR / ("ablation_identifier_all.json" if args.target == "all"
                      else f"ablation_identifier_{args.target}.json")
    out.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out}")
    print("\n=== DECISIONS ===")
    for name, r in results.items():
        print(f"  {name:12s} {r['decision']}")


if __name__ == "__main__":
    main()
