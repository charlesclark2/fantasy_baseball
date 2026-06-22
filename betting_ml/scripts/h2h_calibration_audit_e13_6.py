#!/usr/bin/env python
"""Story E13.6 — H2H win-probability calibration / reliability audit.

OBJECTIVE = prediction quality (Brier / log-loss / ECE), NOT CLV. The H2H edge is
dead (E3.1/E4/E1.9/E13.1) and we do not claim it; the product requirement is a
well-CALIBRATED, honestly-framed win probability — "when we say 58%, home wins ~58%".

This audits the SERVED win-prob (`daily_model_predictions.calibrated_win_prob`, which is
the identity-calibrated consensus = 0.5·ngboost + 0.5·xgb-Platt) for the CURRENT champion
(default model_version=v5, the 2026-06-12 market-blind de-leaked re-promotion) against
actual outcomes (`betting.mart_game_results.home_team_won`). It:

  1. Reliability diagram + ECE + Brier + log-loss for the served prob — OVERALL and by
     SEGMENT (served tier, market favorite/dog, home-prob bucket, month, run-environment).
  2. Baselines for CONTEXT (not a beat-claim): no-skill (base-rate & 0.5) and the de-vigged
     market-implied prob on the same games.
  3. Recalibration candidates on a chronological hold-out — {identity, Platt, isotonic,
     temperature} — each scored on Brier / ECE / spread. Temperature scaling (logit/T) is
     the spread-honest, monotone option: T>1 shrinks an OVERconfident prob toward the base
     rate, T<1 sharpens an UNDERconfident one. Selection mirrors the A2.9 discipline (lowest
     Brier that clears the spread floor) AND separately reports the ECE-optimal method,
     since THIS story's objective is calibration, not betting discrimination.

MEASURE + CANDIDATE only: writes a candidate calibrator + JSON + nothing to Snowflake and
NEVER overwrites the live calibrator.joblib (the operator promotes after review, exactly
like A2.9 / refit_home_win_calibrator.py).

Run (Snowflake SELECT + sklearn only — no feature-store load, well under 1 min):

    TARGET_ENV=prod uv run python betting_ml/scripts/h2h_calibration_audit_e13_6.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from betting_ml.utils.calibration import IdentityCalibrator, TemperatureCalibrator  # noqa: E402
from betting_ml.utils.data_loader import get_snowflake_connection  # noqa: E402
from betting_ml.utils.ml_env import ml_schema  # noqa: E402

_OUT_DIR = _REPO_ROOT / "betting_ml" / "models" / "home_win"
_CANDIDATE = _OUT_DIR / "calibrator_e13_6_candidate.joblib"
_EVAL_DIR = _REPO_ROOT / "betting_ml" / "evaluation" / "calibration_e13_6"
_REPORT = (_REPO_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
           / "h2h_calibration_e13_6.md")

_SPREAD_FLOOR = 0.03   # A2.1/A2.9 floor — below this a calibrator has collapsed discrimination
_EPS = 1e-6            # clip for log-loss / logit


# ----------------------------------------------------------------------------- metrics
def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _EPS, 1 - _EPS)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error — |conf − accuracy| weighted by bin population."""
    bins = np.linspace(0, 1, n_bins + 1)
    n = len(p)
    out = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        out += (m.sum() / n) * abs(p[m].mean() - y[m].mean())
    return float(out)


def reliability_table(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> list[dict]:
    bins = np.linspace(0, 1, n_bins + 1)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() == 0:
            continue
        rows.append({"bin_lo": round(float(lo), 2), "bin_hi": round(float(hi), 2),
                     "n": int(m.sum()), "avg_pred": round(float(p[m].mean()), 4),
                     "avg_actual": round(float(y[m].mean()), 4)})
    return rows


def metric_block(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    return {
        "n": int(len(p)),
        "brier": round(brier(p, y), 4),
        "log_loss": round(log_loss(p, y), 4),
        "ece": round(ece(p, y), 4),
        "spread": round(float(np.std(p)), 4),
        "mean_pred": round(float(np.mean(p)), 4),
        "base_rate": round(float(np.mean(y)), 4),
        "corr": round(float(np.corrcoef(p, y)[0, 1]), 4) if np.std(p) > 0 else 0.0,
    }


# ----------------------------------------------------------------------------- calibrators
def fit_temperature(p_tr: np.ndarray, y_tr: np.ndarray) -> float:
    """Single-parameter temperature on the logit: p' = sigmoid(logit(p)/T).

    T>1 shrinks toward 0.5 (fixes OVERconfidence); T<1 sharpens (fixes UNDERconfidence).
    Fit by minimizing NLL on the train split. Monotone & spread-honest (it does not flatten
    to a constant the way a low-slope sigmoid does — it rescales confidence, not signal)."""
    z = logit(np.clip(p_tr, _EPS, 1 - _EPS))

    def nll(t: float) -> float:
        return log_loss(expit(z / t), y_tr)

    res = minimize_scalar(nll, bounds=(0.2, 8.0), method="bounded")
    return float(res.x)


# TemperatureCalibrator is defined in betting_ml.utils.calibration (stable importable module)
# so the promoted pickle resolves in predict_today/backfill — same reason as IdentityCalibrator.


def _apply(cal, x: np.ndarray) -> np.ndarray:
    if cal is None:
        return np.asarray(x, float)
    try:
        return cal.predict_proba(np.asarray(x, float).reshape(-1, 1))[:, 1]
    except (AttributeError, ValueError):
        return cal.predict(np.asarray(x, float))


def fit_candidates(p: np.ndarray, y: np.ndarray, eval_frac: float = 0.25) -> dict:
    """Fit {identity, platt, isotonic, temperature} on a chronological train split and
    score every method on the hold-out. `p`/`y` MUST be chronologically ordered."""
    n = len(p)
    split = max(1, int(n * (1 - eval_frac)))
    Ptr, ytr = p[:split], y[:split]
    Pev, yev = p[split:], y[split:]

    platt = LogisticRegression(C=1.0).fit(Ptr.reshape(-1, 1), ytr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(Ptr, ytr)
    temp_T = fit_temperature(Ptr, ytr)
    temp = TemperatureCalibrator(temp_T)

    fitted = {"identity": IdentityCalibrator(), "platt": platt, "isotonic": iso, "temperature": temp}
    eval_stats = {name: {**metric_block(_apply(cal, Pev), yev), "method": name}
                  for name, cal in fitted.items()}
    eval_stats["temperature"]["T"] = round(temp_T, 4)

    # A2.9 selection: lowest Brier that clears the spread floor (betting lens).
    eligible = {k: v for k, v in eval_stats.items() if v["spread"] >= _SPREAD_FLOOR}
    pool = eligible or eval_stats
    brier_pick = min(pool, key=lambda k: pool[k]["brier"])
    # E13.6 objective lens: lowest ECE (calibration), spread floor still respected.
    ece_pick = min(pool, key=lambda k: pool[k]["ece"])

    # Refit the ECE-pick on the FULL window for the deployable candidate.
    final = _refit_full(ece_pick, p, y, temp_T)
    return {
        "eval_stats": eval_stats, "split": split, "eval_n": n - split,
        "brier_pick": brier_pick, "ece_pick": ece_pick,
        "temperature_T": round(temp_T, 4), "candidate": final, "candidate_method": ece_pick,
    }


def _refit_full(method: str, p: np.ndarray, y: np.ndarray, temp_T: float):
    if method == "platt":
        return LogisticRegression(C=1.0).fit(p.reshape(-1, 1), y)
    if method == "isotonic":
        return IsotonicRegression(out_of_bounds="clip").fit(p, y)
    if method == "temperature":
        return TemperatureCalibrator(fit_temperature(p, y))
    return IdentityCalibrator()


# ----------------------------------------------------------------------------- data
def load_served(conn, model_version: str, since: str) -> pd.DataFrame:
    schema = ml_schema()
    sql = f"""
    WITH v AS (
      SELECT d.game_pk, d.game_date, d.calibrated_win_prob AS p,
             d.consensus_win_prob AS cons, d.h2h_market_implied_prob AS mkt,
             d.prediction_type, d.is_backfill, d.feature_coverage_score AS cov,
             ROW_NUMBER() OVER (PARTITION BY d.game_pk ORDER BY
                CASE d.prediction_type WHEN 'post_lineup' THEN 1 WHEN 'morning' THEN 2 ELSE 3 END,
                d.inserted_at DESC) rn
      FROM {schema}.daily_model_predictions d
      WHERE d.model_version = %(mv)s AND d.game_date >= %(since)s
        AND d.calibrated_win_prob IS NOT NULL
    )
    SELECT v.game_pk, v.game_date, v.p, v.cons, v.mkt, v.prediction_type,
           v.is_backfill, v.cov,
           CASE WHEN r.home_team_won THEN 1 ELSE 0 END AS y,
           (r.home_final_score + r.away_final_score) AS total_runs
    FROM v JOIN baseball_data.betting.mart_game_results r USING (game_pk)
    WHERE v.rn = 1 AND r.home_final_score IS NOT NULL
    ORDER BY v.game_date, v.game_pk
    """
    cur = conn.cursor()
    cur.execute(sql, {"mv": model_version, "since": since})
    cols = [c[0].lower() for c in cur.description]
    df = pd.DataFrame(cur.fetchall(), columns=cols)
    for c in ["p", "cons", "mkt", "cov", "y", "total_runs"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def _tier(row) -> str:
    if row["prediction_type"] == "post_lineup":
        return "post_lineup_live" if not row["is_backfill"] else "post_lineup_backfill"
    if row["prediction_type"] == "morning":
        return "morning_live" if not row["is_backfill"] else "morning_backfill"
    return str(row["prediction_type"])


# ----------------------------------------------------------------------------- segments
def segment_report(df: pd.DataFrame) -> dict:
    p, y = df["p"].to_numpy(), df["y"].to_numpy()
    segs: dict[str, dict] = {}

    def add(label: str, mask: np.ndarray):
        if mask.sum() >= 20:                      # don't report noise on tiny cells
            segs[label] = metric_block(p[mask], y[mask])

    add("tier:morning_live", (df["prediction_type"] == "morning") & (~df["is_backfill"].astype(bool)))
    add("tier:morning_backfill", (df["prediction_type"] == "morning") & (df["is_backfill"].astype(bool)))
    add("tier:post_lineup_live", (df["prediction_type"] == "post_lineup") & (~df["is_backfill"].astype(bool)))

    mkt = df["mkt"].to_numpy()
    add("market:home_favorite", mkt > 0.5)
    add("market:home_dog", mkt <= 0.5)
    add("pred:home_lean(p>0.55)", p > 0.55)
    add("pred:toss_up(0.45-0.55)", (p >= 0.45) & (p <= 0.55))
    add("pred:away_lean(p<0.45)", p < 0.45)

    for m in sorted(df["game_date"].dt.strftime("%Y-%m").unique()):
        add(f"month:{m}", df["game_date"].dt.strftime("%Y-%m").to_numpy() == m)

    tr = df["total_runs"].to_numpy()
    q1, q2 = np.nanpercentile(tr, [33, 67])
    add(f"run_env:low(<{q1:.0f})", tr < q1)
    add(f"run_env:mid({q1:.0f}-{q2:.0f})", (tr >= q1) & (tr <= q2))
    add(f"run_env:high(>{q2:.0f})", tr > q2)
    return segs


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="E13.6 H2H win-prob calibration/reliability audit")
    ap.add_argument("--model-version", default="v5", help="champion version to audit (default v5)")
    ap.add_argument("--since", default="2026-01-01", help="honest-OOS window start (default 2026-01-01)")
    ap.add_argument("--eval-frac", type=float, default=0.25, help="chronological hold-out fraction")
    ap.add_argument("--promote", action="store_true", help="overwrite live calibrator.joblib (default: candidate only)")
    args = ap.parse_args()

    conn = get_snowflake_connection()
    try:
        df = load_served(conn, args.model_version, args.since)
    finally:
        conn.close()
    if df.empty:
        print("No served+settled games in window."); return 1
    print(f"Loaded {len(df)} settled games (model_version={args.model_version}, since {args.since}).")

    p, y, mkt = df["p"].to_numpy(), df["y"].to_numpy(), df["mkt"].to_numpy()
    base = float(np.mean(y))

    # Overall + baselines.
    overall = metric_block(p, y)
    reliability = reliability_table(p, y)
    mkt_mask = ~np.isnan(mkt)
    baselines = {
        "no_skill_base_rate": metric_block(np.full(len(y), base), y),
        "no_skill_coinflip": metric_block(np.full(len(y), 0.5), y),
        "served_model_on_mkt_games": metric_block(p[mkt_mask], y[mkt_mask]),
        "market_implied": metric_block(mkt[mkt_mask], y[mkt_mask]),
    }

    segments = segment_report(df)

    # Recalibration candidates (chronological — df already ordered by date).
    cand = fit_candidates(p, y, args.eval_frac)

    # ---- console summary
    print("\n=== OVERALL served win-prob ===")
    for k, v in overall.items():
        print(f"  {k:>10}: {v}")
    print(f"\n  Baselines (Brier / log-loss / ece):")
    for k, v in baselines.items():
        print(f"    {k:<28} Brier {v['brier']}  LL {v['log_loss']}  ECE {v['ece']}  (n={v['n']})")
    print("\n=== Recalibration candidates (hold-out) ===")
    print(f"  {'method':<13}{'Brier':>9}{'LL':>9}{'ECE':>9}{'spread':>9}{'corr':>8}")
    for name, s in cand["eval_stats"].items():
        print(f"  {name:<13}{s['brier']:>9.4f}{s['log_loss']:>9.4f}{s['ece']:>9.4f}{s['spread']:>9.4f}{s['corr']:>8.3f}")
    print(f"  → Brier-pick (betting lens): {cand['brier_pick']}   "
          f"ECE-pick (calibration lens): {cand['ece_pick']}   temp T={cand['temperature_T']}")

    # ---- persist
    _EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "story": "E13.6", "model_version": args.model_version, "since": args.since,
        "n": int(len(df)), "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall, "reliability": reliability, "baselines": baselines,
        "segments": segments,
        "recalibration": {"eval_stats": cand["eval_stats"], "brier_pick": cand["brier_pick"],
                          "ece_pick": cand["ece_pick"], "temperature_T": cand["temperature_T"],
                          "eval_n": cand["eval_n"], "split": cand["split"]},
    }
    (_EVAL_DIR / f"served_calibration_{args.model_version}.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\n  Wrote JSON → {_EVAL_DIR / f'served_calibration_{args.model_version}.json'}")

    import joblib
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(cand["candidate"], _CANDIDATE)
    print(f"  Wrote candidate ({cand['candidate_method']}) → {_CANDIDATE}")
    if args.promote:
        joblib.dump(cand["candidate"], _OUT_DIR / "calibrator.joblib")
        print("  PROMOTED candidate → live calibrator.joblib")
    else:
        print("  Candidate only — live calibrator untouched (operator promotes after review).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
