"""pre_lineup_proj_gate_33_5.py — Story 33.5: gate the projection-feature pre-lineup model.

The 33.5 question: do the Story-33.3 expected-lineup `exp_*` projection features make the
PRE-LINEUP (morning) model measurably better than the deployed 33.0 floor? This is a
PROMOTE/HOLD gate (unlike pre_lineup_baseline_30_8.py, which only quantified the 33.0 gap).

Controlled ablation — same tuned HP per target (from pre_lineup_baseline_30_8._TARGETS),
vary ONLY the feature set, three arms:
    post  = full live post-lineup contract            (the ceiling / lineup-gap context)
    pre   = 33.0 Class-A subset                        (the deployed floor = gate CHAMPION)
    proj  = 33.5 = Class-A + exp_* projection features (the gate CHALLENGER)

GATE (betting_ml.utils.promotion_gate, the canonical Case-3 ruleset): per-GAME walk-forward
scores (brier for home_win, abs_error→MAE for run_diff/total_runs) tagged by season, champion=pre,
challenger=proj. PROMOTE iff proj clears the noise floor + paired-bootstrap-significant + no
completed-season regression. 2026 is the current/partial season (corroboration only). The
honest-2026 surface is reported for context (and the lineup-gap recovery vs the post champion).

A PROMOTE means: repoint registry `pre_lineup` → the 33.5 `*_proj` artifacts (Phase 2 of 33.5)
and bump pre_lineup_model_version v1→v2. A HOLD keeps the 33.0 floor deployed.

Runtime: retrains 3 feature-set arms per season fold (NGBoost) → HAND OFF, ONE --target per invocation.

Usage:
    uv run python betting_ml/scripts/pre_lineup_proj_gate_33_5.py --target home_win
    uv run python betting_ml/scripts/pre_lineup_proj_gate_33_5.py --target run_diff
    uv run python betting_ml/scripts/pre_lineup_proj_gate_33_5.py --target total_runs
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
    _TARGETS, _cols, _fit_clf, _fit_reg, _impute,
)
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.promotion_gate import brier as _brier_score  # noqa: E402
from betting_ml.utils.promotion_gate import abs_error, evaluate_promotion  # noqa: E402

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "pre_lineup_33_5"

# proj contract = the 33.0 `pre` contract path with `_proj` inserted (build_pre_lineup_proj_contracts_33_5.py).
def _proj_path(pre_path: str) -> str:
    p = Path(pre_path)
    return str(p.with_name(p.stem + "_proj" + p.suffix))


def _per_game_scores(df, cfg, feat, tr, ev) -> np.ndarray:
    """Per-game accuracy-to-truth score (LOWER = better): brier for home_win, abs_error else."""
    Xtr, Xev = _impute(df.loc[tr, feat], df.loc[ev, feat])
    ytr, yev = df.loc[tr, cfg["target_col"]].values, df.loc[ev, cfg["target_col"]].values
    if cfg["kind"] == "classification":
        p = _fit_clf(cfg, Xtr, ytr, Xev, yev)
        return _brier_score(yev, p)
    pred, _loc, _scale = _fit_reg(cfg, Xtr, ytr, Xev)
    return abs_error(yev, pred)


def _run(name: str, df: pd.DataFrame) -> dict:
    cfg = _TARGETS[name]
    post = [c for c in _cols(cfg["post"]) if c in df.columns]
    pre = [c for c in _cols(cfg["pre"]) if c in df.columns]
    proj = [c for c in _cols(_proj_path(cfg["pre"])) if c in df.columns]
    metric = "brier" if cfg["kind"] == "classification" else "mae"
    n_exp = len(set(proj) - set(pre))

    print(f"\n=== {name} ({cfg['kind']}) — post {len(post)} / pre {len(pre)} / proj {len(proj)} "
          f"(+{n_exp} exp_* over the 33.0 floor) — metric={metric} ===")

    # Walk-forward per-game scores for the gate (champion=pre floor, challenger=proj).
    seasons, s_pre, s_proj = [], [], []
    ctx = {}  # per eval-year aggregate for all 3 arms (context)
    for tr, ev in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[ev, "game_year"].mode()[0])
        sc_pre = _per_game_scores(df, cfg, pre, tr, ev)
        sc_proj = _per_game_scores(df, cfg, proj, tr, ev)
        sc_post = _per_game_scores(df, cfg, post, tr, ev)
        seasons.append(np.full(len(ev), yr))
        s_pre.append(sc_pre); s_proj.append(sc_proj)
        ctx[yr] = {"post": float(sc_post.mean()), "pre": float(sc_pre.mean()),
                   "proj": float(sc_proj.mean()), "n": int(len(ev))}
        print(f"    {yr} (n={len(ev):4d}): post {sc_post.mean():.4f}  pre {sc_pre.mean():.4f}  "
              f"proj {sc_proj.mean():.4f}  Δ(proj-pre) {sc_proj.mean()-sc_pre.mean():+.4f}")

    season = np.concatenate(seasons)
    champ = np.concatenate(s_pre)    # 33.0 floor
    chal = np.concatenate(s_proj)    # 33.5 challenger
    verdict = evaluate_promotion(season, champ, chal, metric=metric)

    # honest-2026 lineup-gap RECOVERY: how much of the (pre→post) gap proj closes.
    rec = None
    if 2026 in ctx:
        c = ctx[2026]
        gap_floor = c["pre"] - c["post"]   # the morning cost the floor pays (≥0 expected)
        gap_proj = c["proj"] - c["post"]
        rec = {"post": c["post"], "pre": c["pre"], "proj": c["proj"],
               "floor_gap_vs_post": gap_floor, "proj_gap_vs_post": gap_proj,
               "recovery_frac": (float((gap_floor - gap_proj) / gap_floor)
                                 if abs(gap_floor) > 1e-9 else float("nan"))}

    print("\n" + str(verdict))
    print(f"\n  >>> 33.5 GATE: {verdict.decision}  "
          f"(proj {'BEATS' if verdict.single_eval_pass else 'does NOT beat'} the 33.0 floor "
          f"on completed seasons)")
    if rec is not None:
        print(f"  honest-2026: post {rec['post']:.4f} / floor {rec['pre']:.4f} / proj {rec['proj']:.4f}"
              f"  — proj recovers {rec['recovery_frac']*100:.0f}% of the floor→post lineup gap")

    return {"target": name, "metric": metric, "n_post": len(post), "n_pre": len(pre),
            "n_proj": len(proj), "n_exp_added": n_exp, "per_year": ctx,
            "gate": {"decision": verdict.decision, "single_eval_pass": verdict.single_eval_pass,
                     "overall_delta": verdict.overall_delta, "boot_ci": list(verdict.boot_ci),
                     "effect_size_pass": verdict.effect_size_pass, "significant": verdict.significant,
                     "consistency_pass": verdict.consistency_pass,
                     "tolerance": verdict.tolerance, "reasons": verdict.reasons,
                     "per_season": [vars(s) for s in verdict.per_season]},
            "honest_2026_recovery": rec}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs"], required=True)
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons {sorted(df['game_year'].dropna().unique().tolist())}")
    res = _run(args.target, df)
    out = _OUT_DIR / f"pre_lineup_proj_gate_{args.target}.json"
    out.write_text(json.dumps(res, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
