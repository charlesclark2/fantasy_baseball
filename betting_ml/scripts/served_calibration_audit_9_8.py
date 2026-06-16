"""served_calibration_audit_9_8.py — Story 9.8: served predictive-distribution calibration audit.

Story 9.7 made the `*_uncertainty` / `combined_sigma` columns REAL per-game 80% PI widths, but nobody
checked whether the served predictive DISTRIBUTIONS are CALIBRATED. A real-but-miscalibrated posterior is
worse than a stub — it looks trustworthy. This is the cheap, eval-only prerequisite that licenses everything
uncertainty-aware downstream (Story 22.4 σ-aware selection, the over/under product, Epic 12.4 conviction
signals, the Story 30.15 uncertainty the app surfaces).

WHAT IT MEASURES (per target × per served TIER × per eval season):
  - REGRESSION (run_diff, total_runs — NGBoost Normal): coverage of the central 80% / 90% predictive interval
    vs nominal, PIT KS-distance + histogram (U = overconfident / dome = underconfident / slope = directional
    bias), mean NLL + CRPS, and bias = mean_pred − mean_actual. Via promotion_gate.calibration_report.
  - CLASSIFICATION (home_win — XGB+Platt): ECE + 10-bin reliability + a logistic recalibration slope/intercept
    (slope≈1, intercept≈0 = calibrated), reported for BOTH the raw XGB prob AND the Platt-calibrated prob —
    so we directly test whether Platt helps or HURTS (the Story 10.9 / legacy concern: Platt was degrading ECE).

TIERS = the two things actually served: `champion` (full post-lineup contract) and `pre_lineup` (33.0 Class-A
floor). Controlled ablation — same tuned HP (pre_lineup_baseline_30_8._TARGETS), vary only the feature set.
Honest surface: walk-forward (train <Y, eval Y) so the calibration is what the served model gets on UNSEEN
games; 2026 = honest OOS (current/partial), 2024/2025 = completed-fold stability.

This MEASURES only — no model change. If a tier/target is miscalibrated it RECOMMENDS the fix (isotonic/conformal
for totals P(over) already exists in Story 10.9; a σ-scale recalibration for the regression PIs).

Runtime: refits NGBoost/XGB per fold × 2 tiers → minutes. HAND OFF, ONE --target per invocation.

Usage:
    uv run python betting_ml/scripts/served_calibration_audit_9_8.py --target home_win
    uv run python betting_ml/scripts/served_calibration_audit_9_8.py --target run_diff
    uv run python betting_ml/scripts/served_calibration_audit_9_8.py --target total_runs
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

from betting_ml.scripts.pre_lineup_baseline_30_8 import (  # noqa: E402
    _TARGETS, _cols, _ece, _fit_reg, _impute,
)
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.promotion_gate import PredictiveOutput, calibration_report  # noqa: E402

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "calibration_9_8"

# served tier → feature-set key in pre_lineup_baseline_30_8._TARGETS (post = champion, pre = 33.0 floor)
_TIERS = {"champion": "post", "pre_lineup": "pre"}

# flag thresholds (a tier/target is "miscalibrated → recalibrate before use as a decision input")
_COV_GAP_TOL = 0.05    # |empirical coverage − nominal| above this on the 80% PI = miscalibrated
_PIT_KS_TOL = 0.06     # PIT KS-distance above this = distribution shape off
_ECE_TOL = 0.03        # classification ECE above this = miscalibrated


def _fit_clf_raw_and_platt(cfg, Xtr, ytr, Xev, yev):
    """home_win champion recipe — XGB on train, Platt on eval — returning BOTH the raw XGB prob
    and the Platt-calibrated prob so the audit can test whether Platt helps or hurts."""
    from sklearn.linear_model import LogisticRegression
    from xgboost import XGBClassifier
    clf = XGBClassifier(**cfg["xgb_params"])
    clf.fit(Xtr, ytr.astype(int))
    raw = clf.predict_proba(Xev)[:, 1]
    cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
    cal.fit(raw.reshape(-1, 1), yev.astype(int))
    platt = cal.predict_proba(raw.reshape(-1, 1))[:, 1]
    return raw, platt


def _reliability(p, y, n_bins=10) -> list[dict]:
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(p, bins) - 1, 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        m = idx == b
        if m.sum():
            out.append({"bin": f"{bins[b]:.1f}-{bins[b+1]:.1f}", "n": int(m.sum()),
                        "mean_pred": round(float(p[m].mean()), 4),
                        "frac_pos": round(float(y[m].mean()), 4)})
    return out


def _calib_slope_intercept(p, y, eps=1e-6) -> tuple[float, float]:
    """Logistic recalibration check: regress y on logit(p). slope≈1 & intercept≈0 = calibrated;
    slope<1 = overconfident (probs too extreme), slope>1 = underconfident."""
    from sklearn.linear_model import LogisticRegression
    z = np.log(np.clip(p, eps, 1 - eps) / np.clip(1 - p, eps, 1 - eps)).reshape(-1, 1)
    if len(np.unique(y)) < 2:
        return float("nan"), float("nan")
    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)  # ~unpenalized
    lr.fit(z, y.astype(int))
    return float(lr.coef_[0, 0]), float(lr.intercept_[0])


def _clf_calibration(y, raw, platt) -> dict:
    """Reliability for the served (Platt) prob AND the raw XGB prob — does Platt help or hurt?"""
    out = {}
    for name, p in (("raw_xgb", raw), ("served_platt", platt)):
        sl, ic = _calib_slope_intercept(p, y)
        out[name] = {"ece": round(_ece(p, y), 4),
                     "brier": round(float(np.mean((p - y) ** 2)), 4),
                     "calib_slope": round(sl, 3), "calib_intercept": round(ic, 3),
                     "mean_pred": round(float(p.mean()), 4), "frac_pos": round(float(y.mean()), 4)}
    out["reliability_served"] = _reliability(platt, y)
    out["platt_helps"] = out["served_platt"]["ece"] < out["raw_xgb"]["ece"]
    out["miscalibrated"] = out["served_platt"]["ece"] > _ECE_TOL
    return out


def _reg_calibration(y, loc, scale) -> dict:
    out80 = calibration_report(y, PredictiveOutput.normal(loc, scale), level=0.80)
    out90 = calibration_report(y, PredictiveOutput.normal(loc, scale), level=0.90)
    r = {"n": out80["n"],
         "coverage_80": round(out80["coverage"], 4), "coverage_gap_80": round(out80["coverage_gap"], 4),
         "coverage_90": round(out90["coverage"], 4), "coverage_gap_90": round(out90["coverage_gap"], 4),
         "pit_ks": round(out80["pit_ks"], 4), "pit_hist": out80["pit_hist"],
         "nll_mean": round(out80["nll_mean"], 4), "crps_mean": round(out80["crps_mean"], 4),
         "mean_pred": round(out80["mean_pred"], 4), "mean_actual": round(out80["mean_actual"], 4),
         "bias": round(out80["bias"], 4)}
    r["miscalibrated"] = bool(abs(r["coverage_gap_80"]) > _COV_GAP_TOL or r["pit_ks"] > _PIT_KS_TOL)
    # interpret the PIT/coverage shape for the human reader
    if r["coverage_gap_80"] < -_COV_GAP_TOL:
        r["shape"] = "OVERCONFIDENT (PI too tight — coverage below nominal)"
    elif r["coverage_gap_80"] > _COV_GAP_TOL:
        r["shape"] = "UNDERCONFIDENT (PI too wide — coverage above nominal)"
    else:
        r["shape"] = "well-covered"
    return r


def _eval_surface(df, cfg, feat, tr, ev) -> dict:
    Xtr, Xev = _impute(df.loc[tr, feat], df.loc[ev, feat])
    ytr, yev = df.loc[tr, cfg["target_col"]].values, df.loc[ev, cfg["target_col"]].values
    if cfg["kind"] == "classification":
        raw, platt = _fit_clf_raw_and_platt(cfg, Xtr, ytr, Xev, yev)
        return _clf_calibration(yev, raw, platt)
    _pred, loc, scale = _fit_reg(cfg, Xtr, ytr, Xev)
    return _reg_calibration(yev, loc, scale)


def _run(target: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[target]
    res = {"target": target, "kind": cfg["kind"], "tiers": {}}
    for tier, key in _TIERS.items():
        feat = [c for c in _cols(cfg[key]) if c in df.columns]
        print(f"\n=== {target} — tier={tier} ({len(feat)} feats) ===")
        per_year = {}
        for tr, ev in all_season_splits(df, min_train_seasons=3):
            yr = int(df.loc[ev, "game_year"].mode()[0])
            rep = _eval_surface(df, cfg, feat, tr, ev)
            per_year[yr] = rep
            if cfg["kind"] == "classification":
                s = rep["served_platt"]
                print(f"  {yr} (n={len(ev):4d}): ECE served={s['ece']:.4f} raw={rep['raw_xgb']['ece']:.4f}"
                      f"  slope={s['calib_slope']:.2f}  Platt {'helps' if rep['platt_helps'] else 'HURTS'}"
                      f"  {'⚠ MISCAL' if rep['miscalibrated'] else 'ok'}")
            else:
                print(f"  {yr} (n={len(ev):4d}): cov80={rep['coverage_80']:.3f} (gap {rep['coverage_gap_80']:+.3f})"
                      f"  cov90={rep['coverage_90']:.3f}  PIT-KS={rep['pit_ks']:.3f}  bias={rep['bias']:+.3f}"
                      f"  → {rep['shape']}  {'⚠ MISCAL' if rep['miscalibrated'] else 'ok'}")
        res["tiers"][tier] = per_year
    return res


def _verdict_lines(res: dict) -> list[str]:
    """Headline per (tier) on the honest-2026 surface — the decision-relevant calibration state."""
    lines = []
    for tier, per_year in res["tiers"].items():
        y26 = per_year.get(2026)
        if not y26:
            continue
        if res["kind"] == "classification":
            tag = "MISCALIBRATED → recalibrate before decision use" if y26["miscalibrated"] else "calibrated ✓"
            lines.append(f"- **{res['target']} / {tier}** (2026): served ECE {y26['served_platt']['ece']:.4f}, "
                         f"slope {y26['served_platt']['calib_slope']:.2f}; Platt "
                         f"{'helps' if y26['platt_helps'] else 'HURTS (raw better)'} → {tag}")
        else:
            tag = "MISCALIBRATED → recalibrate before decision use" if y26["miscalibrated"] else "calibrated ✓"
            lines.append(f"- **{res['target']} / {tier}** (2026): 80% coverage {y26['coverage_80']:.3f} "
                         f"(gap {y26['coverage_gap_80']:+.3f}), PIT-KS {y26['pit_ks']:.3f}, bias {y26['bias']:+.3f} "
                         f"({y26['shape']}) → {tag}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs"], required=True)
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    res = _run(args.target, df)
    out = _OUT_DIR / f"served_calibration_{args.target}.json"
    out.write_text(json.dumps(res, indent=2))
    print("\n=== 9.8 CALIBRATION VERDICT (honest 2026) ===")
    for ln in _verdict_lines(res):
        print("  " + ln.replace("**", "").replace("- ", ""))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
