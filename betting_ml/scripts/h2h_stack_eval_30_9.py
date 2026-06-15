"""
h2h_stack_eval_30_9.py — Story 30.9: learned h2h ensemble stack vs the hand-set 50/50 blend.

OFFLINE eval only. Quantifies whether a LEARNED blend of the two independent h2h estimators
beats the hard-coded `cons_win = 0.5*P_classifier + 0.5*P(run_diff>0)` that production uses
(predict_today.py:632/1539/1602), and gates the winner through the codified promotion gate.

The two estimators (BOTH the 27.8-settled base models — inputs are now FINAL):
  - P_classifier : home_win XGB + Platt — the v6 SEASON-NORMALIZED contract
                   (betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_seasonnorm_2026.json)
  - P_run_diff   : Φ(μ/σ) from the run_diff NGBoost — the v5 DEPLOYED contract (run_diff HELD at v5
                   in 27.8: Normal, n_estimators=500, feature_columns_ngboost_tuned_2026.json)

Leak-free structure (forward-chaining, mirrors the gate):
  1. Per season-forward fold (all_season_splits, min_train_seasons=3), fit BOTH base models on the
     train seasons and predict the held-out season → strictly OOF per-season base preds [P_clf, P_rd, y].
  2. STATUS QUO: Brier/NLL/AUC for {50/50 blend, classifier-only, run_diff-only} per season + pooled.
     Establishes whether the 50/50 blend even beats its best single component.
  3. STACK: forward-chain a meta-learner over the OOF seasons — fit on OOF seasons < S, predict S.
     Two variants: (a) convex weight w* (grid) + (b) 2-input LogisticRegression on [P_clf, P_rd].
     The first OOF season is meta-train-only, so gate eval seasons = the remaining (held-out) seasons.
  4. GATE: evaluate_promotion(blend50 vs best-stack, metric=brier) — NO correctness override (accuracy
     refinement, not a compliance fix). Must clear the bars honestly or HOLD (50/50 stands).

⚠ LIVE WIRING IS SHELVED regardless of verdict: best_alpha=0.0 → the live posterior is pure market,
   so the internal blend weight has ZERO live bet payoff until the Story 30.6 alpha-unlock. This script
   PERSISTS the artifact + eval doc; wiring (+ Platt-calibrator refit on the new blend) waits for alpha>0.

HAND-OFF: loads the full feature matrix from Snowflake (load_features, >1 min) and retrains both base
models per fold (NGBoost is slow). Run the whole thing as:

    uv run python betting_ml/scripts/h2h_stack_eval_30_9.py

Outputs:
    quant_sports_intel_models/baseball/ablation_results/h2h_stack_eval_30_9.md      (eval doc)
    betting_ml/evaluation/feature_selection/promotion_gate/promotion_gate_h2h_stack.json  (gate JSON)
    betting_ml/models/layer3/h2h_stack_30_9.json   (persisted stack: w* + logistic coefs, SHELVED)
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.promotion_gate import (  # noqa: E402
    PredictiveOutput, bernoulli_nll, brier, evaluate_promotion,
)
from betting_ml.scripts.promotion_gate_eval import (  # noqa: E402
    XGBPlattSpec, NGBoostSpec, _contract_cols, _challenger_xgb, _impute, _TARGETS,
)
from betting_ml.scripts.ablation_identifier_features import _TARGETS as _CHAMP_HP  # noqa: E402

# ── Config ──────────────────────────────────────────────────────────────────
HW_CFG = _TARGETS["home_win"]
RD_CFG = _TARGETS["run_diff"]
HW_SEASONNORM_CONTRACT = HW_CFG["challenger_contract_seasonnorm"]   # v6 home_win features
RD_V5_CONTRACT = RD_CFG["challenger_contract"]                      # v5 DEPLOYED run_diff features
RD_V5_NGB = {"n_estimators": 500, "dist": "Normal"}                # deployed run_diff recipe

_OUT_DOC = _PROJECT_ROOT / "quant_sports_intel_models/baseball/ablation_results/h2h_stack_eval_30_9.md"
_OUT_GATE = _PROJECT_ROOT / "betting_ml/evaluation/feature_selection/promotion_gate/promotion_gate_h2h_stack.json"
_OUT_STACK = _PROJECT_ROOT / "betting_ml/models/layer3/h2h_stack_30_9.json"

_W_GRID = np.round(np.arange(0.0, 1.001, 0.05), 3)   # convex weight on P_classifier


def _phi(z: np.ndarray) -> np.ndarray:
    """Standard normal CDF, vectorized — P(run_diff > 0) = Φ(μ/σ)."""
    return 0.5 * np.array([math.erfc(-float(v) / math.sqrt(2.0)) for v in np.atleast_1d(z)])


def _metrics(p: np.ndarray, y: np.ndarray) -> dict:
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, int)
    out = {"brier": float(brier(y, p).mean()), "nll": float(bernoulli_nll(y, p).mean())}
    out["auc"] = float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else float("nan")
    return out


# ── 1. Generate strictly-OOF per-season base predictions ────────────────────
def generate_oof(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Forward-chaining OOF: for each held-out season, base models trained on strictly-prior
    train seasons. Returns {season: DataFrame[p_clf, p_rd, y]}."""
    clf_cols = _contract_cols(HW_SEASONNORM_CONTRACT, df)
    rd_cols = _contract_cols(RD_V5_CONTRACT, df)
    print(f"  home_win seasonnorm feats: {len(clf_cols)}  |  run_diff v5 feats: {len(rd_cols)}")
    clf_spec = XGBPlattSpec(_challenger_xgb(HW_CFG["challenger_tuning"]), name="xgb_seasonnorm")
    rd_spec = NGBoostSpec(RD_V5_NGB["n_estimators"], RD_V5_NGB["dist"], name="ngboost_v5")

    oof: dict[int, pd.DataFrame] = {}
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[eval_idx, "game_year"].mode()[0])
        y_hw_tr = df.loc[train_idx, "home_win"].values
        y_hw_ev = df.loc[eval_idx, "home_win"].values
        y_rd_tr = df.loc[train_idx, "run_differential"].values

        Xtr_c, Xev_c = _impute(df.loc[train_idx, clf_cols], df.loc[eval_idx, clf_cols])
        Xtr_r, Xev_r = _impute(df.loc[train_idx, rd_cols], df.loc[eval_idx, rd_cols])

        p_clf = clf_spec.fit_predict(Xtr_c, y_hw_tr, Xev_c, y_hw_ev).prob
        rd_out = rd_spec.fit_predict(Xtr_r, y_rd_tr, Xev_r, y_hw_ev)   # yev unused by NGBoost fit
        z = np.divide(rd_out.loc, rd_out.scale, out=np.zeros_like(rd_out.loc),
                      where=np.asarray(rd_out.scale) != 0)
        p_rd = _phi(z)

        oof[yr] = pd.DataFrame({"p_clf": np.asarray(p_clf, float),
                                "p_rd": np.asarray(p_rd, float),
                                "y": np.asarray(y_hw_ev, int)})
        print(f"  OOF season {yr}: n={len(oof[yr])}  "
              f"clf_brier={_metrics(p_clf, y_hw_ev)['brier']:.4f}  "
              f"rd_brier={_metrics(p_rd, y_hw_ev)['brier']:.4f}")
    return oof


# ── 2. Status-quo table ─────────────────────────────────────────────────────
def status_quo(oof: dict[int, pd.DataFrame]) -> dict:
    rows = {}
    pooled = {k: [] for k in ("blend50", "clf_only", "rd_only")}
    py = []
    for yr in sorted(oof):
        d = oof[yr]
        cand = {"blend50": 0.5 * d.p_clf.values + 0.5 * d.p_rd.values,
                "clf_only": d.p_clf.values, "rd_only": d.p_rd.values}
        rows[yr] = {k: _metrics(v, d.y.values) for k, v in cand.items()}
        for k, v in cand.items():
            pooled[k].append(v)
        py.append(d.y.values)
    yall = np.concatenate(py)
    rows["pooled"] = {k: _metrics(np.concatenate(v), yall) for k, v in pooled.items()}
    return rows


# ── 3. Stack: forward-chain a meta-learner over the OOF seasons ──────────────
def _fit_convex_w(train: pd.DataFrame) -> float:
    """Grid-search the convex weight on P_classifier minimizing Brier over the meta-train rows."""
    best_w, best_b = 0.5, np.inf
    for w in _W_GRID:
        b = brier(train.y.values, w * train.p_clf.values + (1 - w) * train.p_rd.values).mean()
        if b < best_b:
            best_b, best_w = b, float(w)
    return best_w


def fit_stack(oof: dict[int, pd.DataFrame]) -> dict:
    """Forward-chain: for each held-out season after the first, fit meta on OOF seasons < S,
    predict S. Returns per-season stack preds (convex-w + logistic) and the final fitted params."""
    seasons = sorted(oof)
    eval_seasons = seasons[1:]   # first season is meta-train-only
    out = {"eval_seasons": eval_seasons, "per_season": {}, "params": {}}
    for S in eval_seasons:
        train = pd.concat([oof[s] for s in seasons if s < S], ignore_index=True)
        test = oof[S]
        # (a) convex weight
        w = _fit_convex_w(train)
        p_w = w * test.p_clf.values + (1 - w) * test.p_rd.values
        # (b) logistic meta on [p_clf, p_rd]
        lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        lr.fit(train[["p_clf", "p_rd"]].values, train.y.values.astype(int))
        p_lr = lr.predict_proba(test[["p_clf", "p_rd"]].values)[:, 1]
        out["per_season"][S] = {
            "y": test.y.values, "blend50": 0.5 * test.p_clf.values + 0.5 * test.p_rd.values,
            "convex_w": p_w, "logistic": p_lr, "w": w,
            "lr_coef": lr.coef_[0].tolist(), "lr_intercept": float(lr.intercept_[0]),
        }
    # Final params (last fold = trained on the most data) for persistence
    last = out["per_season"][eval_seasons[-1]]
    out["params"] = {"convex_w_on_clf": last["w"],
                     "logistic_coef": last["lr_coef"], "logistic_intercept": last["lr_intercept"]}
    return out


# ── 4. Gate the best stack variant vs the 50/50 blend ───────────────────────
def gate_stack(stack: dict) -> dict:
    eval_seasons = stack["eval_seasons"]
    season_arr, blend_s, results = [], [], {}
    # choose the stack variant by pooled Brier over eval seasons
    variant_brier = {}
    for variant in ("convex_w", "logistic"):
        ys = np.concatenate([stack["per_season"][S]["y"] for S in eval_seasons])
        ps = np.concatenate([stack["per_season"][S][variant] for S in eval_seasons])
        variant_brier[variant] = float(brier(ys, ps).mean())
    best_variant = min(variant_brier, key=variant_brier.get)

    chal_s = []
    for S in eval_seasons:
        d = stack["per_season"][S]
        season_arr.append(np.full(len(d["y"]), S))
        blend_s.append(brier(d["y"], d["blend50"]))
        chal_s.append(brier(d["y"], d[best_variant]))
    season_arr = np.concatenate(season_arr)
    completed = {int(s) for s in eval_seasons[:-1]}  # last eval season = current/partial
    current = int(eval_seasons[-1])
    verdict = evaluate_promotion(
        season_arr, np.concatenate(blend_s), np.concatenate(chal_s),
        metric="brier", completed_seasons=completed, current_season=current)
    return {"best_variant": best_variant, "variant_brier": variant_brier,
            "completed_seasons": sorted(completed), "current_season": current,
            "verdict": verdict}


def _fmt_sq(rows: dict) -> str:
    hdr = "| season | 50/50 Brier | clf-only Brier | run_diff-only Brier | 50/50 NLL | 50/50 AUC |\n"
    hdr += "|---|---|---|---|---|---|\n"
    for yr in [k for k in rows if k != "pooled"] + ["pooled"]:
        r = rows[yr]
        hdr += (f"| {yr} | {r['blend50']['brier']:.4f} | {r['clf_only']['brier']:.4f} | "
                f"{r['rd_only']['brier']:.4f} | {r['blend50']['nll']:.4f} | {r['blend50']['auc']:.4f} |\n")
    return hdr


def main() -> None:
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].unique())}")
    assert "home_win" in df.columns and "run_differential" in df.columns, "missing target columns"

    print("\n[1/4] Generating strictly-OOF per-season base predictions...")
    oof = generate_oof(df)
    print("\n[2/4] Status-quo table (50/50 vs clf-only vs run_diff-only)...")
    sq = status_quo(oof)
    print(_fmt_sq(sq))
    print("[3/4] Fitting forward-chained stack (convex-w + logistic)...")
    stack = fit_stack(oof)
    print("[4/4] Gating best stack vs 50/50 blend...")
    g = gate_stack(stack)
    v = g["verdict"]
    print(f"\n=== 30.9 GATE → {v.decision}  (best stack variant: {g['best_variant']}) ===")
    print(f"  variant pooled Brier: {g['variant_brier']}")
    print(f"  eval seasons: completed={g['completed_seasons']} current={g['current_season']}")
    for r in v.reasons:
        print("  •", r)

    # Persist (artifact SHELVED — best_alpha=0.0, no live wiring)
    _OUT_GATE.parent.mkdir(parents=True, exist_ok=True)
    _OUT_GATE.write_text(json.dumps({
        "story": "30.9", "decision": v.decision, "best_variant": g["best_variant"],
        "variant_brier": g["variant_brier"], "overall_delta": v.overall_delta,
        "boot_ci": list(v.boot_ci), "per_season": v.per_season,
        "completed_seasons": g["completed_seasons"], "current_season": g["current_season"],
        "reasons": v.reasons, "shelved": True,
        "shelve_reason": "best_alpha=0.0 → live posterior is pure market; wire on alpha>0 (Story 30.6)",
    }, indent=2, default=str))
    _OUT_STACK.parent.mkdir(parents=True, exist_ok=True)
    _OUT_STACK.write_text(json.dumps({
        "story": "30.9", "status": "SHELVED (best_alpha=0.0)", "decision": v.decision,
        "best_variant": g["best_variant"], "params": stack["params"],
        "note": "Replaces cons_win=0.5*clf+0.5*rd in predict_today.py {632,1539,1602} ONLY after "
                "alpha>0 AND refitting the Platt calibrator (scripts/predict_today.py:84) on the new blend.",
    }, indent=2))

    doc = (f"# Story 30.9 — Learned h2h ensemble stack vs 50/50 blend\n\n"
           f"**Decision:** {v.decision}  (best variant: {g['best_variant']}, "
           f"pooled Δbrier={v.overall_delta:+.4f})\n\n"
           f"⚠ **SHELVED regardless of verdict** — `best_alpha=0.0` makes the live posterior pure market, "
           f"so the blend weight has no live bet payoff until the Story 30.6 alpha-unlock.\n\n"
           f"## Status quo — does 50/50 beat its best component?\n\n{_fmt_sq(sq)}\n"
           f"## Stack gate\n\n- variant pooled Brier: `{g['variant_brier']}`\n"
           f"- eval seasons: completed={g['completed_seasons']}, current={g['current_season']}\n"
           f"- params (last fold): `{stack['params']}`\n\n"
           + "\n".join(f"- {r}" for r in v.reasons) + "\n")
    _OUT_DOC.parent.mkdir(parents=True, exist_ok=True)
    _OUT_DOC.write_text(doc)
    print(f"\nWrote {_OUT_DOC}\n      {_OUT_GATE}\n      {_OUT_STACK}")


if __name__ == "__main__":
    main()
