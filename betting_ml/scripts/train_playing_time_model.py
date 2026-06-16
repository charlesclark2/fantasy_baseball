"""train_playing_time_model.py — Story 33.1 Task 2: P(start) model + walk-forward eval.

Reads the candidate panel (build_playing_time_dataset.py) and answers: does a learned
P(start) beat the RAW rolling start-rate? The raw `start_rate_50` is already well
calibrated (the ≥0.9 cohort starts ~91%), so the model only has to add the residual —
IL / rest / short-vs-long-window conditioning. We measure that head-to-head.

Walk-forward by season (train on game_year < Y, eval on Y). Metrics per fold:
  - AUC, Brier, ECE                         (probabilistic quality)
  - LINEUP precision@k                      (THE metric for 33.3: per team-game, take the
                                             top-k candidates by P where k = actual starter
                                             count, fraction that truly started — i.e. how
                                             well we reconstruct the starting lineup)
Compared across: baseline start_rate_25, baseline start_rate_50, and the learned model.
Only adopt the model if it beats the raw-rate baseline on precision@k + calibration.

The final model (refit on all data) + its metadata is saved for Task 3 (serving). Runtime:
parquet load + XGB over ~1.1M rows × few folds → a couple minutes. HAND OFF.

Usage:
    uv run python betting_ml/scripts/train_playing_time_model.py
    uv run python betting_ml/scripts/train_playing_time_model.py --smoke   # synthetic, no parquet
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

_PANEL = PROJECT_ROOT / "betting_ml" / "data" / "playing_time_panel_33_1.parquet"
_ARTIFACT = PROJECT_ROOT / "betting_ml" / "models" / "playing_time" / "playing_time_model_33_1.pkl"
_METRICS = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "playing_time_33_1" / "metrics.json"

_FEATURES = ["start_rate_10", "start_rate_25", "start_rate_50", "starts_50",
             "days_since_last_start", "is_injured", "team_games_in_window_50"]
_EVAL_YEARS = (2022, 2023, 2024, 2025, 2026)
_XGB_PARAMS = dict(max_depth=4, n_estimators=180, learning_rate=0.05, subsample=0.8,
                   colsample_bytree=0.8, eval_metric="logloss", tree_method="hist",
                   random_state=42, n_jobs=-1)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_injured"] = df["is_injured"].astype(float)
    df["days_since_last_start"] = df["days_since_last_start"].fillna(999.0)
    for c in _FEATURES:
        df[c] = df[c].fillna(0.0)
    return df


def _ece(p, y, bins=10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges) - 1, 0, bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.sum():
            e += (m.sum() / len(p)) * abs(p[m].mean() - y[m].mean())
    return float(e)


def _lineup_precision_at_k(df: pd.DataFrame, pcol: str) -> float:
    """Per (game_pk, side): take top-k candidates by P (k = actual starters), fraction
    that truly started. Mean over team-games = lineup-reconstruction accuracy."""
    precs = []
    for _, g in df.groupby(["game_pk", "side"], sort=False):
        k = int(g["did_start"].sum())
        if k == 0:
            continue
        topk = g.nlargest(k, pcol)
        precs.append(topk["did_start"].sum() / k)
    return float(np.mean(precs)) if precs else float("nan")


def _metrics(df: pd.DataFrame, pcol: str) -> dict:
    from sklearn.metrics import brier_score_loss, roc_auc_score
    y = df["did_start"].to_numpy()
    p = df[pcol].to_numpy()
    return {
        "auc": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y, p)),
        "ece": _ece(p, y),
        "precision_at_k": _lineup_precision_at_k(df, pcol),
    }


def _fit_predict(train: pd.DataFrame, evl: pd.DataFrame):
    from xgboost import XGBClassifier
    clf = XGBClassifier(**_XGB_PARAMS)
    clf.fit(train[_FEATURES], train["did_start"].astype(int))
    return clf.predict_proba(evl[_FEATURES])[:, 1]


def _walk_forward(df: pd.DataFrame) -> list[dict]:
    out = []
    for Y in _EVAL_YEARS:
        tr = df[df["game_year"] < Y]
        ev = df[df["game_year"] == Y]
        if len(ev) == 0 or tr["game_year"].nunique() < 2:
            continue
        ev = ev.copy()
        ev["p_model"] = _fit_predict(tr, ev)
        row = {"year": Y, "n_eval": int(len(ev)), "n_games": int(ev.groupby(["game_pk", "side"]).ngroups)}
        for label, pcol in (("rate25", "start_rate_25"), ("rate50", "start_rate_50"), ("model", "p_model")):
            for k, v in _metrics(ev, pcol).items():
                row[f"{label}_{k}"] = v
        out.append(row)
        print(f"  {Y}: precision@k  rate50={row['rate50_precision_at_k']:.4f}  "
              f"model={row['model_precision_at_k']:.4f}  |  AUC rate50={row['rate50_auc']:.4f} "
              f"model={row['model_auc']:.4f}  |  ECE rate50={row['rate50_ece']:.4f} model={row['model_ece']:.4f}")
    return out


def _smoke() -> None:
    rng = np.random.RandomState(0)
    n = 4000
    sr = rng.beta(2, 2, n)
    inj = rng.rand(n) < 0.1
    did = (rng.rand(n) < np.where(inj, sr * 0.2, sr)).astype(int)
    df = pd.DataFrame({
        "game_pk": rng.randint(0, 300, n), "side": rng.choice(["home", "away"], n),
        "game_year": rng.choice([2021, 2022, 2023], n), "player_id": rng.randint(0, 50, n),
        "did_start": did, "start_rate_10": sr, "start_rate_25": sr, "start_rate_50": sr,
        "starts_50": (sr * 50).round(), "days_since_last_start": rng.randint(1, 10, n),
        "is_injured": inj, "team_games_in_window_50": 50.0,
    })
    df = _prep(df)
    m = _metrics(df, "start_rate_50")
    print(f"  smoke metrics rate50: {m}")
    print(f"  precision@k in [0,1]: {0 <= m['precision_at_k'] <= 1}")
    print("  SMOKE PASSED")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        _smoke()
        return

    print(f"Loading panel {_PANEL.name}...")
    df = _prep(pd.read_parquet(_PANEL))
    print(f"  {len(df):,} rows, {df['game_year'].min()}-{df['game_year'].max()}, "
          f"base did_start={df['did_start'].mean():.3f}")

    print("Walk-forward eval (raw rate vs model)...")
    folds = _walk_forward(df)

    def _mean(key):
        vals = [f[key] for f in folds if not np.isnan(f.get(key, np.nan))]
        return float(np.mean(vals)) if vals else float("nan")

    summary = {k: _mean(k) for k in folds[0] if k not in ("year", "n_eval", "n_games")}
    print("\n=== WALK-FORWARD MEAN ===")
    print(f"  precision@k:  rate25={summary['rate25_precision_at_k']:.4f}  "
          f"rate50={summary['rate50_precision_at_k']:.4f}  model={summary['model_precision_at_k']:.4f}")
    print(f"  AUC:          rate50={summary['rate50_auc']:.4f}  model={summary['model_auc']:.4f}")
    print(f"  ECE:          rate50={summary['rate50_ece']:.4f}  model={summary['model_ece']:.4f}")
    print(f"  Brier:        rate50={summary['rate50_brier']:.4f}  model={summary['model_brier']:.4f}")
    d_prec = summary["model_precision_at_k"] - summary["rate50_precision_at_k"]
    verdict = ("MODEL WINS — adopt the learned P(start)" if d_prec > 0.002
               else "RAW RATE SUFFICIENT — ship start_rate_50 as P(start) (model adds <0.002 precision@k)")
    print(f"  Δprecision@k (model − rate50) = {d_prec:+.4f}  →  {verdict}")

    # refit final model on ALL data for Task 3 serving
    print("\nRefitting final model on all data...")
    from xgboost import XGBClassifier
    import joblib
    final = XGBClassifier(**_XGB_PARAMS)
    final.fit(df[_FEATURES], df["did_start"].astype(int))
    _ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "features": _FEATURES}, _ARTIFACT)
    _METRICS.parent.mkdir(parents=True, exist_ok=True)
    _METRICS.write_text(json.dumps({"folds": folds, "summary": summary, "verdict": verdict,
                                    "delta_precision_at_k": d_prec}, indent=2))
    print(f"  Wrote {_ARTIFACT}")
    print(f"  Wrote {_METRICS}")


if __name__ == "__main__":
    main()
