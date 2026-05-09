"""Card 7.C / 8.O — Fit and persist the in-season win-probability calibrator.

Static calibrator (Card 7.C):
  Fetches all 2026 completed game results joined to daily_model_predictions,
  fits Platt scaling and isotonic regression on the first 80% (chronological),
  evaluates on the held-out 20%, keeps whichever method produces lower ECE.
  Outputs:
    betting_ml/models/home_win/calibrator.joblib
    betting_ml/models/home_win/calibrator_meta.json

Rolling calibrator (Card 8.O):
  Queries the most recent `lookback_days` (default 60) of results, fits a new
  Platt scaler, and writes:
    betting_ml/models/home_win/calibrator_rolling.joblib
  Updates `calibrator_last_fit_date` in model_registry.yaml.
  Skips refit if fewer than `min_samples` (default 30) results are available.

Run from project root:
    uv run python betting_ml/scripts/train_calibrator.py           # static
    uv run python betting_ml/scripts/train_calibrator.py --rolling  # rolling

NOTE — sample_weights: time-decay weighting (Card 8.N) is NOT applied here.
This calibrator is fit on 2026 in-season prediction data (already recent by
definition); sample_weight=None throughout. Decay sample_weights belong only
in the base model training scripts (train_time_decay_weighted.py et al.).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(probs)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / n) * abs(probs[mask].mean() - outcomes[mask].mean())
    return float(ece)


def _fetch_2026_data() -> tuple[np.ndarray, np.ndarray]:
    """Return (consensus_win_prob, actual_outcome) arrays sorted chronologically."""
    sql = """
        SELECT
            p.score_date,
            p.consensus_win_prob,
            CASE WHEN r.home_team_won THEN 1 ELSE 0 END AS actual_outcome
        FROM baseball_data.betting_ml.daily_model_predictions p
        JOIN baseball_data.betting.mart_game_results r ON p.game_pk = r.game_pk
        WHERE p.has_odds = TRUE
          AND YEAR(p.score_date) = 2026
          AND p.model_version = 'v1'
          AND r.home_team_won IS NOT NULL
          AND p.consensus_win_prob IS NOT NULL
        ORDER BY p.score_date, p.game_pk
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        raise RuntimeError("No 2026 training data found — ensure the data gate has cleared.")

    dates = [r[0] for r in rows]
    probs = np.array([float(r[1]) for r in rows])
    outcomes = np.array([float(r[2]) for r in rows])
    print(f"Fetched {len(probs)} 2026 rows "
          f"({min(dates)} → {max(dates)})")
    return probs, outcomes, dates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    probs, outcomes, dates = _fetch_2026_data()

    n = len(probs)
    split = int(n * 0.8)
    X_train, y_train = probs[:split], outcomes[:split]
    X_eval,  y_eval  = probs[split:], outcomes[split:]
    print(f"Train: {len(X_train)} rows  ({dates[0]} → {dates[split-1]})")
    print(f"Eval:  {len(X_eval)} rows   ({dates[split]} → {dates[-1]})")

    # Baseline ECE on eval set
    ece_before = _ece(X_eval, y_eval)
    print(f"\nECE before calibration: {ece_before:.4f}")

    # --- Platt scaling (logistic regression) --------------------------------
    platt = LogisticRegression(C=1.0)
    platt.fit(X_train.reshape(-1, 1), y_train)
    platt_preds = platt.predict_proba(X_eval.reshape(-1, 1))[:, 1]
    ece_platt = _ece(platt_preds, y_eval)
    print(f"ECE after Platt scaling:      {ece_platt:.4f}")

    # --- Isotonic regression ------------------------------------------------
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(X_train, y_train)
    iso_preds = iso.predict(X_eval)
    ece_iso = _ece(iso_preds, y_eval)
    print(f"ECE after isotonic regression: {ece_iso:.4f}")

    # --- Pick the winner ----------------------------------------------------
    if ece_platt <= ece_iso:
        best_cal = platt
        best_preds = platt_preds
        ece_after = ece_platt
        method = "platt"
    else:
        best_cal = iso
        best_preds = iso_preds
        ece_after = ece_iso
        method = "isotonic"

    print(f"\nSelected method: {method}  (ECE {ece_before:.4f} → {ece_after:.4f})")

    if ece_after >= ece_before:
        print("WARNING: calibration did not improve ECE on the eval set. "
              "Saving anyway; review the diagnostic before deploying.")

    # --- Persist calibrator -------------------------------------------------
    out_dir = PROJECT_ROOT / "betting_ml" / "models" / "home_win"
    out_dir.mkdir(parents=True, exist_ok=True)

    cal_path = out_dir / "calibrator.joblib"
    joblib.dump(best_cal, cal_path)
    print(f"Saved calibrator → {cal_path}")

    # Quick smoke-test
    test_in = np.array([0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70])
    try:
        test_out = best_cal.predict_proba(test_in.reshape(-1, 1))[:, 1]
    except AttributeError:
        test_out = best_cal.predict(test_in)
    assert test_out.shape == test_in.shape
    assert all(0.0 <= p <= 1.0 for p in test_out)
    print(f"Smoke-test OK:  {np.round(test_in, 2)} → {np.round(test_out, 4)}")

    # --- Metadata sidecar ---------------------------------------------------
    meta = {
        "method": method,
        "train_n": int(len(X_train)),
        "eval_n": int(len(X_eval)),
        "ece_before": round(float(ece_before), 6),
        "ece_after": round(float(ece_after), 6),
        "train_date_range": [str(dates[0]), str(dates[split - 1])],
        "eval_date_range":  [str(dates[split]), str(dates[-1])],
        "fitted_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = out_dir / "calibrator_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Saved metadata  → {meta_path}")
    print(json.dumps(meta, indent=2))


def fit_rolling_calibrator(lookback_days: int = 60, min_samples: int = 30) -> bool:
    """Card 8.O — Fit a rolling Platt calibrator on the most recent lookback_days of results.

    Returns True if the calibrator was fit and saved, False if skipped (< min_samples).
    Updates calibrator_last_fit_date in model_registry.yaml on success.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    sql = f"""
        SELECT
            p.score_date,
            p.consensus_win_prob,
            CASE WHEN r.home_team_won THEN 1 ELSE 0 END AS actual_outcome
        FROM baseball_data.betting_ml.daily_model_predictions p
        JOIN baseball_data.betting.mart_game_results r ON p.game_pk = r.game_pk
        WHERE p.has_odds = TRUE
          AND p.score_date >= '{cutoff}'
          AND p.model_version = 'v1'
          AND r.home_team_won IS NOT NULL
          AND p.consensus_win_prob IS NOT NULL
        ORDER BY p.score_date, p.game_pk
    """
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
    finally:
        conn.close()

    n = len(rows)
    print(f"Rolling window ({lookback_days}d since {cutoff}): {n} samples found")
    if n < min_samples:
        print(f"WARNING: only {n} samples in lookback window (min {min_samples}), skipping refit")
        return False

    probs    = np.array([float(r[1]) for r in rows])
    outcomes = np.array([float(r[2]) for r in rows])

    cal = LogisticRegression(C=1.0)
    cal.fit(probs.reshape(-1, 1), outcomes)

    out_dir  = PROJECT_ROOT / "betting_ml" / "models" / "home_win"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "calibrator_rolling.joblib"
    joblib.dump(cal, out_path)
    print(f"Rolling calibrator fit on {n} samples → {out_path}")

    # Smoke-test
    test_in  = np.array([0.40, 0.50, 0.60])
    test_out = cal.predict_proba(test_in.reshape(-1, 1))[:, 1]
    assert all(0.0 <= p <= 1.0 for p in test_out), "Smoke-test failed: out-of-range probability"
    print(f"Smoke-test OK: {test_in} → {np.round(test_out, 4)}")

    # Update model_registry.yaml
    reg_path = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"
    if reg_path.exists():
        reg = yaml.safe_load(reg_path.read_text()) or {}
        if "home_win" in reg:
            reg["home_win"]["calibrator_last_fit_date"] = date.today().isoformat()
            reg_path.write_text(yaml.dump(reg, default_flow_style=False, sort_keys=False))
            print(f"Updated calibrator_last_fit_date → {date.today().isoformat()}")

    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--rolling", action="store_true",
                        help="Fit rolling calibrator (lookback 60 days) instead of full static fit")
    args = parser.parse_args()
    if args.rolling:
        fit_rolling_calibrator()
    else:
        main()
