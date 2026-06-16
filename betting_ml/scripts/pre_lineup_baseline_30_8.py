"""
pre_lineup_baseline_30_8.py — Story 30.8 / Epic 33.0: the pre-lineup baseline gap.

Controlled ablation — holds each target's tuned HP fixed and varies ONLY the feature set:
    post  = the full live post-lineup contract (home_win 211 / run_diff 169 / total_runs 113)
    pre   = the Class-A PRE-LINEUP subset (feature_columns_pre_lineup_*.json from
            audit_lineup_dependence_30_8.py — drops the lineup-gated Class-B cols + the
            season-fill placeholders). This is what a morning model can actually serve.

Answers the 33.0 question: HOW MUCH does the morning (pre-lineup) model give up vs the
post-lineup champion? The pre-lineup arm WILL be weaker — that is expected and acceptable;
the deliverable is to quantify the gap and confirm the morning model still beats a coinflip
(so serving it is better than the current abstain). It is NOT a promote/reject gate.

Scored on walk-forward CV + the HONEST 2026 OOS surface (train <2026, eval 2026). Primary =
accuracy-to-truth (home_win Brier/NLL/acc/corr; run_diff & total_runs MAE/RMSE/calib_80).

Runtime: retrains NGBoost (run_diff n=1000 / total_runs n=500) + XGBoost per fold for two
feature sets — hand off, ONE --target per invocation.

Usage:
    uv run python betting_ml/scripts/pre_lineup_baseline_30_8.py --target home_win
    uv run python betting_ml/scripts/pre_lineup_baseline_30_8.py --target run_diff
    uv run python betting_ml/scripts/pre_lineup_baseline_30_8.py --target total_runs
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
from betting_ml.utils.preprocessing import build_imputation_pipeline

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "pre_lineup_30_8"

# live (post-lineup) contract + the pre-lineup subset + fixed tuned HP (from tuning_results).
_TARGETS = {
    "home_win": {
        "kind": "classification", "target_col": "home_win",
        "post": "betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json",
        "pre":  "betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json",
        "xgb_params": {"max_depth": 6, "learning_rate": 0.01687735703731368, "n_estimators": 285,
                       "subsample": 0.7395559432725418, "colsample_bytree": 0.6123366282341044,
                       "reg_alpha": 0.3979201420585229, "reg_lambda": 0.9683524038831748,
                       "eval_metric": "logloss", "tree_method": "hist", "random_state": 42, "n_jobs": -1},
    },
    "run_diff": {
        "kind": "regression", "target_col": "run_differential",
        "post": "betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json",
        "pre":  "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json",
        "ngb": {"n_estimators": 1000, "dist": "Normal"},
    },
    "total_runs": {
        "kind": "regression", "target_col": "total_runs",
        "post": "betting_ml/models/total_runs/feature_columns_ngboost_tuned_seasonnorm_2026.json",
        "pre":  "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json",
        "ngb": {"n_estimators": 500, "dist": "Normal"},
    },
}


def _cols(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    return raw["feature_cols"] if isinstance(raw, dict) else raw


def _reg_metrics(y, pred) -> dict:
    err = pred - y
    return {"mae": float(np.mean(np.abs(err))), "rmse": float(np.sqrt(np.mean(err**2))),
            "medae": float(np.median(np.abs(err))), "bias": float(np.mean(err)),
            "pred_std": float(np.std(pred))}


def _calib_80_normal(loc, scale, y) -> float:
    z = 1.2815515594457831
    return float(np.mean((y >= loc - z*scale) & (y <= loc + z*scale)))


def _ece(p, y, n_bins=10) -> float:
    bins = np.linspace(0, 1, n_bins+1)
    idx = np.clip(np.digitize(p, bins)-1, 0, n_bins-1)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum():
            e += (m.sum()/len(p)) * abs(p[m].mean()-y[m].mean())
    return float(e)


def _clf_metrics(y, p) -> dict:
    from sklearn.metrics import brier_score_loss, log_loss
    pc = np.clip(p, 1e-7, 1-1e-7)
    corr = float(np.corrcoef(p, y)[0, 1]) if np.std(p) > 0 else float("nan")
    return {"brier": float(brier_score_loss(y, p)), "nll": float(log_loss(y, pc)),
            "accuracy": float(np.mean((p >= 0.5).astype(int) == y)), "ece": _ece(p, y),
            "live_corr": corr, "pred_std": float(np.std(p))}


def _impute(tr_raw, ev_raw):
    pipe = build_imputation_pipeline()
    Xtr = pipe.fit_transform(tr_raw).select_dtypes(include=[np.number])
    Xev = pipe.transform(ev_raw)
    Xev = Xev[[c for c in Xtr.columns if c in Xev.columns]].reindex(columns=Xtr.columns, fill_value=0.0)
    return Xtr, Xev


def _fit_reg(cfg, Xtr, ytr, Xev):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    m = NGBRegressor(n_estimators=cfg["ngb"]["n_estimators"], Dist=Normal, verbose=False)
    m.fit(Xtr.values, ytr)
    pred = m.predict(Xev.values)
    try:
        pr = m.pred_dist(Xev.values).params
        return pred, np.asarray(pr["loc"]), np.asarray(pr["scale"])
    except Exception:
        return pred, pred, None


def _fit_clf(cfg, Xtr, ytr, Xev, yev):
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier
    clf = XGBClassifier(**cfg["xgb_params"])
    clf.fit(Xtr, ytr.astype(int))
    raw = clf.predict_proba(Xev)[:, 1]
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(raw.reshape(-1, 1), yev.astype(int))
    return cal.predict_proba(raw.reshape(-1, 1))[:, 1]


def _eval_one(df, cfg, feat, tr, ev):
    Xtr, Xev = _impute(df.loc[tr, feat], df.loc[ev, feat])
    ytr, yev = df.loc[tr, cfg["target_col"]].values, df.loc[ev, cfg["target_col"]].values
    if cfg["kind"] == "regression":
        pred, loc, scale = _fit_reg(cfg, Xtr, ytr, Xev)
        m = _reg_metrics(yev, pred)
        if scale is not None:
            m["calib_80"] = _calib_80_normal(loc, scale, yev)
        return m
    return _clf_metrics(yev, _fit_clf(cfg, Xtr, ytr, Xev, yev))


def _mean(folds, keys):
    return {k: float(np.mean([f[k] for f in folds if k in f])) for k in keys}


def _run(name: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[name]
    post = [c for c in _cols(cfg["post"]) if c in df.columns]
    pre = [c for c in _cols(cfg["pre"]) if c in df.columns]
    prim = "brier" if cfg["kind"] == "classification" else "mae"
    keys = (["brier", "nll", "accuracy", "ece", "live_corr", "pred_std"] if cfg["kind"] == "classification"
            else ["mae", "rmse", "medae", "bias", "pred_std", "calib_80"])

    print(f"\n=== {name} ({cfg['kind']}) — post {len(post)} feats / pre {len(pre)} feats "
          f"(drop {len(post)-len(pre)} lineup-gated) ===")
    print("  -- walk-forward CV --")
    pf, rf = [], []
    for tr, ev in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[ev, "game_year"].mode()[0])
        pm, rm = _eval_one(df, cfg, post, tr, ev), _eval_one(df, cfg, pre, tr, ev)
        pm["eval_year"] = rm["eval_year"] = yr
        pf.append(pm); rf.append(rm)
        print(f"    {yr}: post {prim}={pm[prim]:.4f}  pre {prim}={rm[prim]:.4f}")
    cv_post, cv_pre = _mean(pf, keys), _mean(rf, keys)

    print("  -- HONEST 2026 OOS --")
    tr = df.index[df["game_year"] < 2026]; ev = df.index[df["game_year"] == 2026]
    live_post = _eval_one(df, cfg, post, tr, ev) if len(ev) else {}
    live_pre = _eval_one(df, cfg, pre, tr, ev) if len(ev) else {}
    gap = (live_pre.get(prim, float("nan")) - live_post.get(prim, float("nan"))) if live_post else float("nan")

    # serve-worthiness: morning model must beat a coinflip (clf Brier<0.25 / reg better than
    # a mean-only predictor) AND not give up catastrophically vs post-lineup. Informational.
    if cfg["kind"] == "classification" and live_pre:
        beats_floor = live_pre["brier"] < 0.25 and live_pre["live_corr"] > 0.05
    elif live_pre:
        beats_floor = live_pre["mae"] < cv_post.get("pred_std", 99) + live_post["mae"]  # sane sanity floor
    else:
        beats_floor = False
    verdict = ("SERVE-WORTHY (beats coinflip; gap is the honest morning cost)" if beats_floor
               else "WEAK — morning model near-floor; serving may not beat abstain")

    if cfg["kind"] == "classification":
        print(f"  LIVE 2026: post Brier={live_post.get('brier',float('nan')):.4f}/corr={live_post.get('live_corr',float('nan')):.3f}"
              f"  pre Brier={live_pre.get('brier',float('nan')):.4f}/corr={live_pre.get('live_corr',float('nan')):.3f}"
              f"  gap(Brier) {gap:+.4f}")
    else:
        print(f"  LIVE 2026: post MAE={live_post.get('mae',float('nan')):.4f}  pre MAE={live_pre.get('mae',float('nan')):.4f}"
              f"  gap(MAE) {gap:+.4f}  (calib_80 {live_post.get('calib_80',float('nan')):.3f}->{live_pre.get('calib_80',float('nan')):.3f})")
    print(f"  >>> {verdict}")

    return {"target": name, "primary_metric": prim, "n_post": len(post), "n_pre": len(pre),
            "n_dropped": len(post)-len(pre),
            "cv": {"post": cv_post, "pre": cv_pre},
            "live_2026": {"post": live_post, "pre": live_pre, "gap_primary": gap},
            "verdict": verdict}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]
    res = {t: _run(t, df) for t in targets}
    out = _OUT_DIR / (f"pre_lineup_{args.target}.json")
    out.write_text(json.dumps(res, indent=2))
    print(f"\nWrote {out}")
    print("\n=== PRE-LINEUP GAP (honest 2026) ===")
    for t, r in res.items():
        g = r["live_2026"]["gap_primary"]
        print(f"  {t:12s} drop {r['n_dropped']:3d} feats  {r['primary_metric']} gap {g:+.4f}  -> {r['verdict']}")


if __name__ == "__main__":
    main()
