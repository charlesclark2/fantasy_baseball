"""Phase 5, Task 3 — 3-way temporal production calibration refit for home_win.

Step 1 — Verification split:
  Train XGBoost (best tuned params from Card 4.11) on 2016–2023.
  Fit Platt (sigmoid) calibration on 2024.
  Evaluate ECE and Brier on 2025.
  Compare against Card 4.11 mean Platt CV ECE (0.0119).
  Halt if delta > 0.005.

  Note on method: Card 4.11 isotonic ECE (0.0000) is in-sample degenerate —
  isotonic regression perfectly fits any training set, so CV ECE trivially equals 0
  when calibrator and evaluator use the same fold. Platt (sigmoid) CV ECE (0.0119)
  is a meaningful out-of-sample reference. We compare against Platt ECE for a valid
  generalization check.

Step 2 — Production refit:
  Train XGBoost on 2016–2024. Fit Platt calibrator on 2025. Save as
  betting_ml/models/home_win/xgboost_sigmoid_prod_calibrated.pkl.

Step 3 — Verification documentation:
  Write betting_ml/evaluation/calibration_verification.md.

Run from project root:
    uv run python betting_ml/scripts/refit_win_calibration.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from xgboost import XGBClassifier  # noqa: F401 (kept for XGB_BEST_PARAMS instantiation)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.models.win_outcome_trainer import CalibratedXGBClassifier, compute_ece


# ---------------------------------------------------------------------------
# Constants from Card 4.11 evaluation results
# ---------------------------------------------------------------------------

# Platt (sigmoid) mean CV ECE from win_outcome_results.md — the valid out-of-sample
# reference. Isotonic CV ECE (0.0000) is degenerate because Card 4.11 calibrated and
# evaluated on the same fold (in-sample), making it unsuitable as a generalization baseline.
CARD_4_11_MEAN_CV_ECE = 0.0119   # xgb_platt mean CV ECE
CARD_4_11_MEAN_CV_BRIER = 0.2443  # xgb_platt mean CV Brier
ECE_DELTA_THRESHOLD = 0.005
CALIBRATION_METHOD = "sigmoid"

# Best XGBoost params from tuning_results_xgb_home_win.json (Card 4.11)
XGB_BEST_PARAMS = {
    "max_depth": 3,
    "learning_rate": 0.015059668633956027,
    "n_estimators": 337,
    "subsample": 0.7616675016944651,
    "colsample_bytree": 0.6327986171498169,
    "reg_alpha": 0.6938302669328597,
    "reg_lambda": 1.5624112953406002,
    "eval_metric": "logloss",
    "random_state": 42,
    "n_jobs": -1,
}


def _impute(X_train_raw, X_eval_raw):
    pipeline = build_imputation_pipeline()
    X_train_imp = pipeline.fit_transform(X_train_raw)
    X_train_imp = X_train_imp.select_dtypes(include=[np.number])
    X_eval_imp = pipeline.transform(X_eval_raw)
    X_eval_imp = X_eval_imp.reindex(columns=X_train_imp.columns, fill_value=0.0)
    return X_train_imp, X_eval_imp


def _train_and_calibrate(X_train, y_train, X_calib, y_calib) -> CalibratedXGBClassifier:
    """Train XGBoost on training data, fit Platt calibrator on calibration hold-out."""
    xgb = XGBClassifier(**XGB_BEST_PARAMS)
    xgb.fit(X_train.values, np.asarray(y_train))

    y_raw = xgb.predict_proba(X_calib.values)[:, 1]
    calibrator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    calibrator.fit(y_raw.reshape(-1, 1), np.asarray(y_calib))

    return CalibratedXGBClassifier(xgb, calibrator)


def main() -> None:
    print("=== Phase 5 — Home Win Production Calibration Refit ===\n")

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("Loading features from Snowflake...")
    df = load_features(min_games_played=15)
    print(f"  Loaded {len(df):,} rows")

    feature_cols = load_retained_features()
    feature_cols = [c for c in feature_cols if c in df.columns]
    X_all = df[feature_cols]
    y_all = df["home_win"]

    # ------------------------------------------------------------------
    # Step 1 — Verification split: train 2016–2023, calib 2024, eval 2025
    # ------------------------------------------------------------------
    print("\nStep 1: Verification split (train 2016–2023, calib 2024, eval 2025)...")

    mask_train_v = df["game_year"] <= 2023
    mask_calib_v = df["game_year"] == 2024
    mask_eval_v  = df["game_year"] == 2025

    X_train_v_raw  = X_all[mask_train_v]
    X_calib_v_raw  = X_all[mask_calib_v]
    X_eval_v_raw   = X_all[mask_eval_v]
    y_train_v = y_all[mask_train_v]
    y_calib_v = y_all[mask_calib_v]
    y_eval_v  = y_all[mask_eval_v]

    print(f"  Train: {mask_train_v.sum():,} | Calib: {mask_calib_v.sum():,} | Eval: {mask_eval_v.sum():,}")

    X_train_v_imp, X_calib_v_imp = _impute(X_train_v_raw, X_calib_v_raw)
    _, X_eval_v_imp = _impute(X_train_v_raw, X_eval_v_raw)

    cal_model_v = _train_and_calibrate(X_train_v_imp, y_train_v, X_calib_v_imp, y_calib_v)

    y_pred_v = cal_model_v.predict_proba(X_eval_v_imp.values)[:, 1]
    verification_ece   = compute_ece(np.asarray(y_eval_v), y_pred_v)
    verification_brier = float(brier_score_loss(np.asarray(y_eval_v), y_pred_v))

    delta = verification_ece - CARD_4_11_MEAN_CV_ECE
    verdict = "PASS" if abs(delta) <= ECE_DELTA_THRESHOLD else "INVESTIGATE"

    print(f"  Verification ECE:    {verification_ece:.4f}")
    print(f"  Verification Brier:  {verification_brier:.4f}")
    print(f"  Card 4.11 Platt CV ECE: {CARD_4_11_MEAN_CV_ECE:.4f}")
    print(f"  Delta:               {delta:+.4f}")
    print(f"  Verdict:             {verdict}")

    if verdict == "INVESTIGATE":
        print(
            f"\nHALT: verification ECE delta {delta:.4f} exceeds 0.005 threshold. "
            "Investigate before registering production artifact."
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 2 — Production refit: train 2016–2024, calib 2025
    # ------------------------------------------------------------------
    print("\nStep 2: Production refit (train 2016–2024, calib 2025)...")

    mask_train_p = df["game_year"] <= 2024
    mask_calib_p = df["game_year"] == 2025

    X_train_p_raw = X_all[mask_train_p]
    X_calib_p_raw = X_all[mask_calib_p]
    y_train_p = y_all[mask_train_p]
    y_calib_p = y_all[mask_calib_p]

    print(f"  Train: {mask_train_p.sum():,} | Calib: {mask_calib_p.sum():,}")

    X_train_p_imp, X_calib_p_imp = _impute(X_train_p_raw, X_calib_p_raw)

    cal_model_prod = _train_and_calibrate(X_train_p_imp, y_train_p, X_calib_p_imp, y_calib_p)

    out_path = (
        PROJECT_ROOT / "betting_ml" / "models" / "home_win"
        / "xgboost_sigmoid_prod_calibrated.pkl"
    )
    joblib.dump(cal_model_prod, out_path)
    print(f"  Saved: {out_path}")

    # ------------------------------------------------------------------
    # Step 3 — Write calibration_verification.md
    # ------------------------------------------------------------------
    doc_path = PROJECT_ROOT / "betting_ml" / "evaluation" / "calibration_verification.md"
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    doc = f"""# Home Win Calibration Verification (Phase 5)

Generated: {now}

## Configuration

calibration_method: {CALIBRATION_METHOD}
reference_cv_ece_source: Card 4.11 xgb_platt mean CV ECE
verification_train_years: 2016-2023 (2020 excluded by data loader)
verification_calib_year: 2024
verification_eval_year: 2025
production_train_years: 2016-2024 (2020 excluded)
production_calib_year: 2025

## Results

CV ECE (Card 4.11 Platt mean): {CARD_4_11_MEAN_CV_ECE:.4f}
verification_ece: {verification_ece:.4f}
verification_brier: {verification_brier:.4f}
delta: {delta:+.4f}
ECE threshold: 0.0050
verdict: {verdict}

## Method Note

Card 4.11 isotonic CV ECE (0.0000) is in-sample degenerate: isotonic regression
perfectly fits any training set, so the ECE trivially equals 0 when calibrator and
evaluator use the same fold. Platt (sigmoid) CV ECE (0.0119) is a valid out-of-sample
reference — LogisticRegression on raw XGB scores is a smooth parametric calibrator
that generalizes without memorizing the calibration set.

A delta ≤ 0.005 (verification ECE vs. Platt CV ECE) confirms that the Platt calibrator
generalizes from the 2024 hold-out to unseen 2025 data within acceptable tolerance.

## Artifact

`betting_ml/models/home_win/xgboost_sigmoid_prod_calibrated.pkl`
(CalibratedXGBClassifier wrapping XGBClassifier + LogisticRegression; calibration_split=2025)
"""

    with open(doc_path, "w") as f:
        f.write(doc)
    print(f"\nWrote: {doc_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
