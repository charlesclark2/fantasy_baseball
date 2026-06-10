#!/usr/bin/env python
"""Story A2.9 — Re-fit the home_win Platt calibrator on GOOD-FEATURE predictions.

The 2026-06-10 re-score audit proved the model has strong skill when served populated
features (consensus corr 0.46, Brier 0.198 == CV, beats market), but the live Platt
calibrator — fit 2026-05-08 on the feature-degraded logged predictions, and SELECTED BY
ECE (which a flat predictor passes trivially) — collapses that signal to spread 0.02 and
WORSENS Brier 0.198→0.243. This script fixes both root causes:

  1. Fit set = GOOD-FEATURE consensus, not the degraded logged predictions. It re-scores
     completed 2026 (OOS) games against the current feature marts via rescore_audit._score
     — the same impute→reindex→score path as the deployed model — so the calibrator sees
     the recovered signal it must actually map.
  2. Selection metric = BRIER with a spread floor, not ECE. A calibrator that worsens Brier
     vs the raw consensus, or flattens spread below the floor, is rejected.

It compares {raw consensus, OLD live calibrator, Platt, isotonic} on a chronological
hold-out, selects the lowest-Brier method that keeps spread ≥ floor, refits it on the full
window, and writes a CANDIDATE artifact (does NOT overwrite the live calibrator.joblib —
the user promotes it). Audit/produce-only; no Snowflake writes.

Hand-off (loads + scores the feature store; > 1 min):

    uv run python scripts/ops/refit_home_win_calibrator.py --since 2026-03-01
    # then, once you've reviewed the before/after, promote:
    cp betting_ml/models/home_win/calibrator_refit_candidate.joblib \
       betting_ml/models/home_win/calibrator.joblib
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import yaml
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import rescore_audit as ra          # noqa: E402  (reuses the deployed scoring path)
import model_health_metrics as mh   # noqa: E402  (shared _brier/_corr/_ece-free metrics)
# IdentityCalibrator lives in a stable importable module so the promoted candidate
# unpickles in predict_today/backfill (a script-local class would pickle as __main__).
from betting_ml.utils.calibration import IdentityCalibrator  # noqa: E402

_OUT_DIR = _REPO_ROOT / "betting_ml" / "models" / "home_win"
_LIVE_CAL = _OUT_DIR / "calibrator.joblib"
_CANDIDATE = _OUT_DIR / "calibrator_refit_candidate.joblib"
_CANDIDATE_META = _OUT_DIR / "calibrator_refit_meta.json"

_SPREAD_FLOOR = mh.MIN_SPREAD_PROB  # 0.03 — same floor the A2.1 gate uses


def _ece(probs: np.ndarray, outcomes: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    n = len(probs)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (probs >= lo) & (probs < hi)
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / n) * abs(probs[mask].mean() - outcomes[mask].mean())
    return float(ece)


def _apply(cal, x: np.ndarray) -> np.ndarray:
    """Apply a calibrator the same way predict_today does."""
    if cal is None:
        return x
    try:
        return cal.predict_proba(x.reshape(-1, 1))[:, 1]
    except AttributeError:
        return cal.predict(x)


def _stats(name: str, probs: np.ndarray, outcomes: np.ndarray) -> dict:
    return {
        "name": name,
        "brier": mh._brier(probs, outcomes),
        "ece": _ece(probs, outcomes),
        "spread": float(np.std(probs)),
        "corr": mh._corr(probs, outcomes),
        "mean": float(np.mean(probs)),
    }


# Robustness/simplicity preference, used to break near-ties in Brier. A smooth/simple map
# generalizes better per-game than isotonic's step function, so when two methods are within
# brier_epsilon (i.e. the Brier difference is inside sampling noise) we take the earlier one.
_PREFERENCE = ["identity", "platt", "isotonic"]


def fit_and_select(consensus: np.ndarray, outcome: np.ndarray, eval_frac: float = 0.2,
                   old_cal=None, spread_floor: float = _SPREAD_FLOOR,
                   brier_epsilon: float = 0.005) -> dict:
    """Fit Platt + isotonic on the chronological train split, evaluate {raw, old, platt,
    iso} on the hold-out, and select a method by Brier with a spread floor AND a
    robustness tie-break: among methods whose Brier is within `brier_epsilon` of the best
    (a difference inside sampling noise) and which clear the spread floor, prefer the
    smoother/simpler one (identity > platt > isotonic).

    `consensus`/`outcome` MUST already be in chronological order. Returns a report dict
    with per-method eval stats, the selected method name, and the model refit on ALL data.
    Pure (no I/O) so it can be unit-tested offline.
    """
    n = len(consensus)
    split = max(1, int(n * (1 - eval_frac)))
    Xtr, ytr = consensus[:split], outcome[:split]
    Xev, yev = consensus[split:], outcome[split:]

    platt = LogisticRegression(C=1.0).fit(Xtr.reshape(-1, 1), ytr)
    iso = IsotonicRegression(out_of_bounds="clip").fit(Xtr, ytr)

    eval_stats = {
        "raw_consensus": _stats("raw_consensus", Xev, yev),
        "platt": _stats("platt", _apply(platt, Xev), yev),
        "isotonic": _stats("isotonic", _apply(iso, Xev), yev),
    }
    if old_cal is not None:
        eval_stats["old_live_calibrator"] = _stats("old_live_calibrator", _apply(old_cal, Xev), yev)

    raw_brier = eval_stats["raw_consensus"]["brier"]
    # Candidates: identity (= run uncalibrated), Platt, isotonic. Selection by Brier with a
    # spread floor. identity's eval == raw_consensus, so when the consensus is already the
    # best-calibrated option identity wins and we deploy a pass-through (drop the harmful
    # calibrator) rather than degrade with a small-sample fit.
    candidates = {
        "identity": eval_stats["raw_consensus"],
        "platt": eval_stats["platt"],
        "isotonic": eval_stats["isotonic"],
    }
    eligible = {k: v for k, v in candidates.items() if v["spread"] >= spread_floor}
    pool = eligible or candidates  # if none clear the floor, still pick the best by Brier
    best_brier = min(pool[k]["brier"] for k in pool)
    # Tie-break: among methods within brier_epsilon of the best (noise-equivalent), take the
    # most-preferred (smoothest) one; otherwise the strict Brier minimum.
    near_best = [k for k in pool if pool[k]["brier"] <= best_brier + brier_epsilon]
    method = min(near_best, key=lambda k: _PREFERENCE.index(k))
    brier_min_method = min(pool, key=lambda k: pool[k]["brier"])
    tie_broken = method != brier_min_method
    beats_raw = candidates[method]["brier"] <= raw_brier

    # Refit the chosen method on the FULL window for the deployed candidate.
    if method == "platt":
        final = LogisticRegression(C=1.0).fit(consensus.reshape(-1, 1), outcome)
    elif method == "isotonic":
        final = IsotonicRegression(out_of_bounds="clip").fit(consensus, outcome)
    else:  # identity — pass-through, run uncalibrated
        final = IdentityCalibrator()

    return {
        "method": method, "model": final, "eval_stats": eval_stats,
        "selected_eval": candidates[method],  # identity → raw_consensus stats
        "raw_brier": raw_brier, "beats_raw": beats_raw,
        "split": split, "n": n, "eval_n": n - split,
        "spread_floor": spread_floor, "brier_epsilon": brier_epsilon,
        "brier_min_method": brier_min_method, "tie_broken": tie_broken,
        "selected_clears_floor": candidates[method]["spread"] >= spread_floor,
    }


def _print_report(rep: dict) -> None:
    print("\n" + "=" * 78)
    print("  HOME_WIN CALIBRATOR RE-FIT — hold-out comparison (lower Brier is better)")
    print("=" * 78)
    order = ["raw_consensus", "old_live_calibrator", "platt", "isotonic"]
    # identity selection is reported against the raw_consensus row (identical performance).
    sel_row = "raw_consensus" if rep["method"] == "identity" else rep["method"]
    print(f"  {'method':<22}{'Brier':>10}{'ECE':>10}{'spread':>10}{'corr':>10}{'mean':>10}")
    for k in order:
        s = rep["eval_stats"].get(k)
        if not s:
            continue
        flag = ("  ← SELECTED (identity / uncalibrated)" if rep["method"] == "identity"
                else "  ← SELECTED") if k == sel_row else ""
        print(f"  {k:<22}{s['brier']:>10.4f}{s['ece']:>10.4f}{s['spread']:>10.4f}"
              f"{s['corr']:>10.4f}{s['mean']:>10.4f}{flag}")
    print("-" * 78)
    print(f"  selected: {rep['method']}  | beats raw consensus Brier: {rep['beats_raw']}  "
          f"| clears spread floor {rep['spread_floor']}: {rep['selected_clears_floor']}")
    if rep.get("tie_broken"):
        print(f"  tie-break applied: '{rep['brier_min_method']}' had the lowest Brier but was within "
              f"{rep['brier_epsilon']} of '{rep['method']}' (noise); kept the smoother '{rep['method']}'.")
    if rep["method"] == "identity":
        print("  → identity selected: the consensus is already best-calibrated. Deploying a")
        print("    pass-through DROPS the harmful flat calibrator (calibrated == consensus).")
    elif not rep["beats_raw"]:
        print("  ⚠ selected calibrator does NOT beat the raw consensus Brier — consider running")
        print("    UNCALIBRATED (drop the calibrator) until more good-feature data accumulates.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-fit the home_win Platt calibrator on good-feature data (A2.9).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=None, help="rolling window ending --end")
    g.add_argument("--since", type=str, default="2026-03-01", help="window start YYYY-MM-DD (default 2026-03-01)")
    ap.add_argument("--end", type=str, help="window end YYYY-MM-DD (default today)")
    ap.add_argument("--eval-frac", type=float, default=0.2, help="chronological hold-out fraction (default 0.2)")
    ap.add_argument("--brier-epsilon", type=float, default=0.005,
                    help="Brier tie-break band: within this of the best, prefer the smoother method "
                         "(identity>platt>isotonic). Default 0.005 (≈ sampling noise on a few hundred games).")
    ap.add_argument("--allow-pre-2026", action="store_true", help="permit pre-2026 (in-sample) games")
    ap.add_argument("--promote", action="store_true",
                    help="overwrite the live calibrator.joblib with the candidate (default: write candidate only)")
    args = ap.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = (end - timedelta(days=args.days)) if args.days else datetime.strptime(args.since, "%Y-%m-%d").date()
    window = f"{start.isoformat()} → {end.isoformat()}"
    if start < date(2026, 1, 1) and not args.allow_pre_2026:
        print(f"[REFUSING] window {window} includes pre-2026 (in-sample) games; use --allow-pre-2026 to override.")
        return 1

    registry = yaml.safe_load((_REPO_ROOT / "betting_ml" / "models" / "model_registry.yaml").read_text())

    print(f"Loading + scoring completed games in {window} (good-feature consensus)...")
    df = ra.load_features(min_games_played=15)
    df["game_date"] = ra.pd.to_datetime(df["game_date"]).dt.date
    df = df[(df["game_date"] >= start) & (df["game_date"] <= end)].sort_values("game_date").reset_index(drop=True)
    if df.empty:
        print("No completed games in window.")
        return 0
    scored = ra._score(df, registry)
    print(f"  {len(scored)} games scored")

    consensus = scored["consensus_win_prob"].to_numpy(dtype=float)
    outcome = (scored["home_final_score"] > scored["away_final_score"]).astype(float).to_numpy()
    old_cal = joblib.load(_LIVE_CAL) if _LIVE_CAL.exists() else None

    rep = fit_and_select(consensus, outcome, args.eval_frac, old_cal, brier_epsilon=args.brier_epsilon)
    _print_report(rep)

    # Persist candidate (never silently clobber the live artifact).
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(rep["model"], _CANDIDATE)
    test_in = np.array([0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70])
    print(f"  smoke-test: {np.round(test_in,2)} → {np.round(_apply(rep['model'], test_in), 4)}")
    meta = {
        "story": "A2.9", "method": rep["method"], "fit_window": [start.isoformat(), end.isoformat()],
        "n_total": rep["n"], "eval_n": rep["eval_n"], "eval_frac": args.eval_frac,
        "selected_eval": rep["selected_eval"],
        "raw_consensus_eval": rep["eval_stats"]["raw_consensus"],
        "old_live_calibrator_eval": rep["eval_stats"].get("old_live_calibrator"),
        "beats_raw_consensus_brier": rep["beats_raw"],
        "clears_spread_floor": rep["selected_clears_floor"],
        "brier_epsilon": rep["brier_epsilon"], "brier_min_method": rep["brier_min_method"],
        "tie_broken": rep["tie_broken"],
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "fit_set": "good-feature re-scored 2026 OOS consensus (rescore_audit._score)",
    }
    _CANDIDATE_META.write_text(json.dumps(meta, indent=2, default=str))
    print(f"\n  Wrote candidate → {_CANDIDATE}")
    print(f"  Wrote meta      → {_CANDIDATE_META}")

    if args.promote:
        joblib.dump(rep["model"], _LIVE_CAL)
        print(f"  PROMOTED candidate → {_LIVE_CAL} (live calibrator overwritten)")
    else:
        print("\n  Candidate only (live calibrator untouched). To promote after review:")
        print(f"    cp {_CANDIDATE} {_LIVE_CAL}")
    print("\n  Next: re-run alpha tuning (best_alpha should rise > 0), then A2.6 live re-measure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
