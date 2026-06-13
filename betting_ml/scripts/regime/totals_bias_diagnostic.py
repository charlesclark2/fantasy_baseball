"""
totals_bias_diagnostic.py — Story 27.6, Task 2.

WHY the totals model over-predicts the 2025 fold by ~0.6 runs when the LEAGUE run rate is flat
(2024≈8.76 → 2025≈8.85, +0.05). The league-level monitor (Task 1) cannot see this — it is a
feature→runs RELATIONSHIP shift, not a level shift. This isolates which features drive it and
whether the shift is a *learnable* regime signal (→ a real 30.10 unblock) or just the lag of
training on past seasons (→ totals stays held, no auto-fix).

Two stages on the market-blind totals challenger (NGBoost Normal, the 30.10 projection candidate):
  A. DISTRIBUTION SHIFT — standardized mean shift of every feature, train(2021–2024) vs 2025
     eval; ranks which inputs moved.
  B. BIAS ATTRIBUTION — for the top-shifted features, substitute their 2025 values with the
     TRAIN median, re-predict 2025, and measure how much the +0.6 over-prediction shrinks. The
     feature(s) whose substitution most reduces the bias ARE the culprits: the model is reading
     a 2025 feature value as "more scoring" when the relationship no longer holds.

Reads nothing from prod; retrains in-memory. Runs >1 min (Snowflake load + NGBoost fits) — hand
off to run with creds:
    uv run python betting_ml/scripts/regime/totals_bias_diagnostic.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from betting_ml.scripts.ablation_identifier_features import _impute
from betting_ml.scripts.promotion_gate_eval import _contract_cols, _challenger_ngb
from betting_ml.utils.data_loader import load_features

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "regime"
_CONTRACT = "betting_ml/models/total_runs/feature_columns_ngboost_tuned_2026.json"
_TUNING = "betting_ml/evaluation/tuning_results_ngboost_total_runs.json"
_TARGET = "total_runs"
_TRAIN_SEASONS = [2021, 2022, 2023, 2024]
_EVAL_SEASON = 2025
_TOP_K = 15          # features to inspect / attribute
_SUBSTITUTE_K = 8    # top-shifted features to test in the bias-attribution substitution


def _fit_ngb(Xtr, ytr):
    from ngboost import NGBRegressor
    from ngboost.distns import Normal
    hn = _challenger_ngb(_TUNING)
    m = NGBRegressor(n_estimators=hn["n_estimators"], Dist=Normal, verbose=False)
    m.fit(Xtr.values, ytr)
    return m


def run() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    cols = _contract_cols(_CONTRACT, df)
    print(f"Totals market-blind contract: {len(cols)} features")

    tr = df[df["game_year"].isin(_TRAIN_SEASONS)]
    ev = df[df["game_year"] == _EVAL_SEASON]
    ytr = tr[_TARGET].values
    yev = ev[_TARGET].values
    Xtr, Xev = _impute(tr[cols], ev[cols])

    print(f"\nTrain {_TRAIN_SEASONS} n={len(Xtr)}  |  Eval {_EVAL_SEASON} n={len(Xev)}")
    m = _fit_ngb(Xtr, ytr)
    pred = np.asarray(m.predict(Xev.values), float)
    bias0 = float(pred.mean() - yev.mean())
    print(f"\nBASELINE 2025 bias (mean pred − mean actual) = {bias0:+.3f}  "
          f"(pred {pred.mean():.3f} vs actual {yev.mean():.3f})")
    if abs(bias0) < 0.2:
        print("  ⚠ bias did not reproduce at the expected magnitude — check contract/seasons before reading on.")

    # ── Stage A: distribution shift ──────────────────────────────────────────
    rows = []
    for c in cols:
        mu_tr, sd_tr = float(Xtr[c].mean()), float(Xtr[c].std())
        mu_ev = float(Xev[c].mean())
        z = (mu_ev - mu_tr) / sd_tr if sd_tr > 1e-9 else 0.0
        rows.append({"feature": c, "train_mean": mu_tr, "eval_2025_mean": mu_ev,
                     "std_shift_z": z, "abs_z": abs(z)})
    shift = pd.DataFrame(rows).sort_values("abs_z", ascending=False).reset_index(drop=True)
    print(f"\n── Stage A: top {_TOP_K} feature distribution shifts (train→2025, in train-SDs) ──")
    print(f"  {'feature':<40}{'train':>10}{'2025':>10}{'z-shift':>9}")
    for _, r in shift.head(_TOP_K).iterrows():
        print(f"  {r['feature']:<40}{r['train_mean']:>10.3f}{r['eval_2025_mean']:>10.3f}{r['std_shift_z']:>+9.2f}")

    # ── Stage B: bias attribution via train-median substitution ──────────────
    # Substitute each top-shifted feature's 2025 values with the TRAIN median; the drop in bias
    # attributes the over-prediction to that feature's 2025 distribution.
    print(f"\n── Stage B: bias attribution — substitute 2025 feature → train median, re-predict ──")
    print(f"  (baseline bias {bias0:+.3f}; a LARGE drop toward 0 ⇒ that feature drives the over-prediction)")
    train_median = Xtr.median()
    att60 = []
    for c in shift.head(_SUBSTITUTE_K)["feature"]:
        Xsub = Xev.copy()
        Xsub[c] = train_median[c]
        pred_sub = np.asarray(m.predict(Xsub.values), float)
        bias_sub = float(pred_sub.mean() - yev.mean())
        att60.append({"feature": c, "bias_after": bias_sub,
                      "bias_reduction": bias0 - bias_sub})
    att = pd.DataFrame(att60).sort_values("bias_reduction", ascending=False, key=abs).reset_index(drop=True)
    print(f"  {'feature':<40}{'bias_after':>12}{'Δbias':>10}")
    for _, r in att.iterrows():
        print(f"  {r['feature']:<40}{r['bias_after']:>+12.3f}{r['bias_reduction']:>+10.3f}")

    # Combined: substitute the whole top-K block at once (interactions).
    Xblock = Xev.copy()
    for c in shift.head(_SUBSTITUTE_K)["feature"]:
        Xblock[c] = train_median[c]
    bias_block = float(np.asarray(m.predict(Xblock.values), float).mean() - yev.mean())
    print(f"\n  ALL top-{_SUBSTITUTE_K} substituted together: bias {bias0:+.3f} → {bias_block:+.3f} "
          f"(Δ {bias0 - bias_block:+.3f})")

    verdict = ("LEARNABLE-REGIME CANDIDATE: a small set of shifted features explains most of the "
               "bias → a regime-adjusted correction on them is viable (feeds 30.10)."
               if abs(bias0 - bias_block) >= 0.5 * abs(bias0) else
               "DIFFUSE / TRAINING-LAG: no small feature set explains the bias → it is likely the "
               "lag of training on past seasons, NOT a learnable signal. Totals stays held; a recent-"
               "window recenter (not a feature signal) is the only lever.")
    print(f"\n  → {verdict}")

    out = _OUT_DIR / "totals_bias_diagnostic.csv"
    shift.merge(att, on="feature", how="left").to_csv(out, index=False)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    run()
