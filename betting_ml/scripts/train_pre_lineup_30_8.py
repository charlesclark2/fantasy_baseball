"""train_pre_lineup_30_8.py — Story 33.0: FINAL pre-lineup serving artifacts.

Trains the Class-A PRE-LINEUP model for ONE target on its
`feature_columns_pre_lineup_*.json` contract (from audit_lineup_dependence_30_8.py),
using the SAME model class + HP as the DEPLOYED post-lineup champion (model_registry),
so the morning model is a faithful pre-lineup analog of the post-lineup champion — only
the feature set differs (Class-A only; the Class-B lineup-gated cols are dropped).

This produces a SHELF artifact; it does NOT touch the live champion. The Story 33.0
serving split (predict_today) loads it as the registry `pre_lineup` variant in the
morning slot (lineups unconfirmed) and the full champion post-lineup.

RECIPE PARITY with the champions:
  home_win   — XGBClassifier(tuned params) + Platt(LogisticRegression) in a
               PlattCalibratedXGBClassifier; XGB fit on the last CV fold's TRAIN split,
               Platt calibrator fit on its EVAL split (mirrors run_xgb_home_win_search.py).
  run_diff   — NGBoost Normal, base DecisionTreeRegressor(max_depth=3), n=500, all 2021+.
  total_runs — NGBoost Normal, base DecisionTreeRegressor(max_depth=3), n=500, all 2021+.
  (n=500 + depth-3 match the registry-deployed champions; the 33.0 gap harness used
   n=1000 for run_diff — the gap direction holds, but the SERVING artifact matches the
   champion so morning/post-lineup are directly comparable.)

FEATURE PARITY with serving (no train/serve column skew): builds the FULL imputed matrix
exactly as predict_today does (build_imputation_pipeline over the full numeric store) and
SELECTS the pre-lineup contract from it — so the saved contract ⊆ the full-store pipeline
output and predict_today's reindex(columns=contract) is exact.

Runtime: load_features + NGBoost fit = minutes → HAND OFF, ONE --target per invocation.

STORY 33.5 (--variant proj): SAME recipe, EXPANDED contract = the 33.0 Class-A set PLUS the
Story-33.3 expected-lineup `exp_*` projection features (the pre-lineup replacement for the dropped
confirmed-lineup batter aggregates). Writes `*_proj` artifacts/contracts so the 33.0 base set stays
intact as the deployed floor + gate baseline. The proj artifact is a CHALLENGER — gate on honest-2026
(beat the 33.0 floor; measure lineup-gap recovery vs the post-lineup champion) BEFORE any registry repoint.

Usage:
    # Story 33.0 floor (default):
    uv run python betting_ml/scripts/train_pre_lineup_30_8.py --target home_win
    # Story 33.5 projection challenger:
    uv run python betting_ml/scripts/train_pre_lineup_30_8.py --target home_win --variant proj
    uv run python betting_ml/scripts/train_pre_lineup_30_8.py --target run_diff --variant proj
    uv run python betting_ml/scripts/train_pre_lineup_30_8.py --target total_runs --variant proj
    (add --no-upload to skip the S3 push; artifact is always written locally)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS
from betting_ml.utils.calibrated_classifier import PlattCalibratedXGBClassifier
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.preprocessing import build_imputation_pipeline

_HW_XGB_PARAMS = {
    "max_depth": 6, "learning_rate": 0.01687735703731368, "n_estimators": 285,
    "subsample": 0.7395559432725418, "colsample_bytree": 0.6123366282341044,
    "reg_alpha": 0.3979201420585229, "reg_lambda": 0.9683524038831748,
    "eval_metric": "logloss", "tree_method": "hist", "random_state": 42, "n_jobs": -1,
}

_TARGETS = {
    "home_win": {
        "kind": "classification", "target_col": "home_win",
        "contract": "betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json",
        "artifact": "betting_ml/models/home_win/xgb_classifier_pre_lineup_2026.pkl",
        "out_contract": "betting_ml/models/home_win/feature_columns_pre_lineup_home_win_fitted.json",
        "s3": "s3://baseball-betting-ml-artifacts/home_win/xgb_classifier_pre_lineup_2026.pkl",
    },
    "run_diff": {
        "kind": "regression", "target_col": "run_differential",
        "contract": "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json",
        "artifact": "betting_ml/models/run_differential/ngboost_pre_lineup_2026.pkl",
        "out_contract": "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff_fitted.json",
        "s3": "s3://baseball-betting-ml-artifacts/run_differential/ngboost_pre_lineup_2026.pkl",
        "n_estimators": 500, "max_depth": 3,
    },
    "total_runs": {
        "kind": "regression", "target_col": "total_runs",
        "contract": "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json",
        "artifact": "betting_ml/models/total_runs/ngboost_pre_lineup_2026.pkl",
        "out_contract": "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs_fitted.json",
        "s3": "s3://baseball-betting-ml-artifacts/total_runs/ngboost_pre_lineup_2026.pkl",
        "n_estimators": 500, "max_depth": 3,
    },
}


def _apply_variant(cfg: dict, variant: str) -> dict:
    """Story 33.5: the `proj` variant trains the SAME recipe on the EXPANDED contract
    (33.0 Class-A + the Story-33.3 expected-lineup `exp_*` projection features). It writes
    `*_proj` artifacts/contracts so the 33.0 base set stays intact as the gate floor.
    `base` (default) = unchanged 33.0 behavior."""
    if variant == "base":
        return cfg
    out = dict(cfg)
    for k in ("contract", "artifact", "out_contract", "s3"):
        if k == "s3":
            head, _, tail = cfg[k].rpartition(".")
            out[k] = f"{head}_proj.{tail}"
        else:
            p = Path(cfg[k])
            out[k] = str(p.with_name(p.stem + "_proj" + p.suffix))
    return out


def _contract_cols(path: str) -> list[str]:
    raw = json.loads((PROJECT_ROOT / path).read_text())
    return raw["feature_cols"] if isinstance(raw, dict) else raw


def _build_pre_lineup_matrix(df: pd.DataFrame, contract: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Full-store imputation (parity with predict_today) → SELECT the pre-lineup contract.

    Guarantees the saved contract ⊆ the full-store pipeline output, so serving
    reindex(columns=contract) is exact (no train/serve column skew)."""
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    full_feats = [c for c in numeric if c not in (_NON_FEATURE_COLS | {"split"})]
    imp = build_imputation_pipeline().fit_transform(df[full_feats]).select_dtypes(include=[np.number])
    present = [c for c in contract if c in imp.columns]
    missing = [c for c in contract if c not in imp.columns]
    if missing:
        print(f"  NOTE: {len(missing)} contract cols absent from the imputed store "
              f"(dropped from the fitted set): {missing[:8]}{'...' if len(missing) > 8 else ''}")
    return imp[present], present


def _fit_classification(X: pd.DataFrame, y: np.ndarray, df: pd.DataFrame):
    """home_win champion recipe: XGB on last-fold TRAIN, Platt on last-fold EVAL."""
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier

    splits = list(all_season_splits(df, min_train_seasons=3))
    if not splits:
        raise RuntimeError("no season folds available for calibration")
    tr_idx, ev_idx = splits[-1]  # most-recent eval year (mirrors the champion's last fold)
    Xv = X.values
    xgb = XGBClassifier(**_HW_XGB_PARAMS)
    xgb.fit(Xv[tr_idx], y[tr_idx].astype(int))
    raw = xgb.predict_proba(Xv[ev_idx])[:, 1]
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(raw.reshape(-1, 1), y[ev_idx].astype(int))
    ev_year = int(df.loc[ev_idx, "game_year"].mode()[0]) if "game_year" in df.columns else -1
    print(f"  XGB fit on {len(tr_idx):,} train rows; Platt calibrated on {len(ev_idx):,} "
          f"eval rows (year {ev_year}).")
    return PlattCalibratedXGBClassifier(xgb, cal)


def _fit_regression(X: pd.DataFrame, y: np.ndarray, cfg: dict):
    """NGBoost champion recipe: Normal, friedman_mse depth-3 base, n_estimators, all data."""
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    from sklearn.tree import DecisionTreeRegressor

    base = DecisionTreeRegressor(criterion="friedman_mse", max_depth=cfg["max_depth"])
    ngb = NGBRegressor(Dist=Normal, n_estimators=cfg["n_estimators"], Base=base, verbose=False)
    t0 = time.time()
    ngb.fit(X.values, y)
    print(f"  NGBoost fit: {time.time()-t0:.0f}s, {len(y):,} rows, n_estimators={cfg['n_estimators']}.")
    return ngb


def _smoke(model, X: pd.DataFrame, kind: str) -> None:
    sample = X.values[:5]
    if kind == "classification":
        p = model.predict_proba(sample)[:, 1]
        assert np.all((p >= 0) & (p <= 1)), f"prob out of range: {p}"
        print(f"  Smoke test passed: P(home win) sample {p.round(3)}")
    else:
        pred = model.predict(sample)
        assert np.all(np.abs(pred) < 30.0), f"pred out of range: {pred}"
        print(f"  Smoke test passed: pred sample {pred.round(2)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=["home_win", "run_diff", "total_runs"])
    ap.add_argument("--variant", choices=["base", "proj"], default="base",
                    help="base = 33.0 Class-A contract; proj = 33.5 (+ Story-33.3 exp_* projection features)")
    ap.add_argument("--no-upload", action="store_true", help="skip S3 upload (local artifact only)")
    args = ap.parse_args()
    cfg = _apply_variant(_TARGETS[args.target], args.variant)

    story = "33.0" if args.variant == "base" else "33.5"
    label = "Class-A" if args.variant == "base" else "Class-A + 33.3 exp_* projection"
    print(f"=== STORY {story} — PRE-LINEUP ARTIFACT ({args.variant}): {args.target} ({cfg['kind']}) ===\n")
    contract = _contract_cols(cfg["contract"])
    print(f"  Pre-lineup contract: {len(contract)} {label} features ({cfg['contract']})")

    print("\nLoading features from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= 2021]
    if "game_date" in df.columns:
        df = df.sort_values("game_date")
    df = df[df[cfg["target_col"]].notna()].reset_index(drop=True)
    print(f"  {len(df):,} rows with a {cfg['target_col']} label, "
          f"seasons {sorted(df['game_year'].unique().tolist())}")

    X, fitted_cols = _build_pre_lineup_matrix(df, contract)
    y = df[cfg["target_col"]].values
    print(f"  Fitted feature set: {len(fitted_cols)} columns")

    print("\nFitting final pre-lineup model...")
    if cfg["kind"] == "classification":
        model = _fit_classification(X, y, df)
    else:
        model = _fit_regression(X, y, cfg)
    _smoke(model, X, cfg["kind"])

    artifact_path = PROJECT_ROOT / cfg["artifact"]
    out_contract_path = PROJECT_ROOT / cfg["out_contract"]
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, artifact_path)
    out_contract_path.write_text(json.dumps(
        {"target": cfg["target_col"],
         "model_name": f"pre_lineup_{args.target}" + ("_proj" if args.variant == "proj" else ""),
         "story": story,
         "n_features": len(fitted_cols), "derived_from": cfg["contract"],
         "feature_cols": fitted_cols}, indent=2))
    print(f"\nArtifact: {artifact_path}")
    print(f"Contract: {out_contract_path}  ({len(fitted_cols)} cols)")

    if not args.no_upload:
        try:
            from betting_ml.utils.artifact_store import upload_artifact
            upload_artifact(artifact_path, cfg["s3"])
            print(f"Uploaded: {cfg['s3']}")
        except Exception as exc:
            print(f"  WARNING: S3 upload skipped ({exc}). Local artifact is valid; "
                  f"point the registry at the local path or re-upload later.")

    if args.variant == "base":
        print(f"""
=== NEXT STEPS (Story 33.0 serving split) ===
Add a `pre_lineup` variant to model_registry.yaml under '{cfg['target_col']}':
   pre_lineup: {cfg['artifact']}        # (or {cfg['s3']})
   pre_lineup_feature_columns_path: {cfg['out_contract']}
Then the predict_today serving split loads load_model('{cfg['target_col']}', 'pre_lineup')
+ this contract in the morning (lineups unconfirmed) and the champion post-lineup.
Do this for all 3 targets, then verify with a dev predict_today run.
""")
    else:
        print(f"""
=== NEXT STEPS (Story 33.5 — GATE before any promotion) ===
This `proj` artifact is a CHALLENGER to the deployed 33.0 pre-lineup floor. Do NOT repoint
the registry yet. Run the honest-2026 gate (pre_lineup_baseline_30_8.py / promotion_gate.py):
   proj challenger  vs  33.0 pre-lineup floor   (must beat — the projection features must add lift)
   proj challenger  vs  post-lineup champion    (context — how much of the lineup gap is recovered)
Only on a PROMOTE verdict: repoint model_registry `pre_lineup` → {cfg['artifact']}
   + pre_lineup_feature_columns_path → {cfg['out_contract']}, bump pre_lineup_model_version v1→v2.
Artifact + fitted contract written ({len(fitted_cols)} cols); batch-ship with the deploy.
""")


if __name__ == "__main__":
    main()
