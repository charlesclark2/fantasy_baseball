"""model_bakeoff.py — Edge Program E1.9 step 1: model-class bake-off (selection BEFORE tuning).

WHY
---
The v5 champions are historical defaults (XGBoost for home_win, NGBoost for totals) that
were never validated as best-in-class. E1.9 rebuilds v6 from a clean slate: first decide
*which learner class* wins under the honest gate on the de-leaked + leak-swept matrix, THEN
(separately, `optuna_hpo.py`) tune only the winner. This module is the bake-off — it does
NOT tune; it compares default-ish configs of each class so the choice of family is honest.

WHAT IT DOES
------------
For a `--target` × `--tier`:
  1. Load the cached training matrix and apply BOTH E1-de-leak swaps in memory
     (bullpen_v3 + Stuff+ prior-season) so the bake-off trains on exactly the matrix the
     E1.8 slim contracts were derived on. (The cache `edge_e1_training` is the OLD leaky
     pull; the swaps are how clustered_feature_importance.py de-leaks it.)
  2. Select the tier-appropriate contract — post_lineup = the FINAL slim de-leaked contract
     (dense matrix), pre_lineup = the 33.0 morning contract (lineup-gated families dropped).
     Evaluate each tier on its OWN contract so the morning model is never graded on dense
     re-reads (the optimistic-0.42 trap, E12).
  3. CONTRACT-GUARD: assert no market column is in the trained feature set (market-blind).
  4. Run a slate of candidate learners under E1.1 PURGED CV (embargoed). Score each per game
     via PredictiveOutput.score_to_truth on the target's HONEST metric:
       - home_win  : brier (gate metric) + nll + binary calibration (ECE/reliability)
       - totals/rd : crps (DISTRIBUTIONAL) + nll + mae + predictive calibration (PIT/coverage)
     plus no-skill and (where available) market FLOORS — reference baselines, not candidates.
  5. PBO (E1.4 CSCV) across the candidate slate: is the bake-off winner an overfit pick?
  6. Pick the winner by primary metric; ties (within the noise floor) break to better
     calibration, then to the simpler/more-distributional class. Write the full table +
     winner to ablation_results/ for E1.9's record.

The NGBoost/CatBoost arms make this a multi-minute job → HAND OFF to the operator. `--smoke`
caps rows/estimators/candidates for a fast end-to-end harness check.

Usage:
    uv run python betting_ml/scripts/model_bakeoff.py --target home_win  --tier post_lineup
    uv run python betting_ml/scripts/model_bakeoff.py --target total_runs --tier pre_lineup
    uv run python betting_ml/scripts/model_bakeoff.py --target home_win  --smoke   # harness check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.clustered_feature_importance import (
    _swap_bullpen_v3, _swap_stuff_plus_deleaked,
)
from betting_ml.scripts.promotion_gate_eval import (
    NGBoostSpec, XGBPlattSpec, _Predictor, _impute, make_gate_splitter,
)
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.overfitting import pbo_cscv
from betting_ml.utils.promotion_gate import (
    NOISE_FLOOR, PredictiveOutput, calibration_report,
)
from betting_ml.utils.training_cache import get_cached_df

_REPORT_DIR = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_JSON_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "bakeoff"

# ── target config: column, kind, honest metric, market-floor source ──────────
_TARGETS = {
    "home_win":   {"col": "home_win",        "kind": "clf", "metric": "brier",
                   "market_prob": "home_win_prob_consensus"},
    "total_runs": {"col": "total_runs",      "kind": "reg", "metric": "crps",
                   "allow_lognormal": True, "market_point": "total_line_consensus"},
    "run_diff":   {"col": "run_differential","kind": "reg", "metric": "crps",
                   "allow_lognormal": False, "market_point": None},
}

# tier → contract path template per target. post_lineup = E1.8 FINAL slim; pre_lineup = 33.0.
_CONTRACTS = {
    "post_lineup": {
        "home_win":   "betting_ml/models/home_win/feature_columns_xgb_classifier_pruned_clustered_deleaked_2026.json",
        "run_diff":   "betting_ml/models/run_differential/feature_columns_ngboost_pruned_clustered_deleaked_2026.json",
        "total_runs": "betting_ml/models/total_runs/feature_columns_ngboost_pruned_clustered_deleaked_2026.json",
    },
    "pre_lineup": {
        "home_win":   "betting_ml/models/home_win/feature_columns_pre_lineup_home_win.json",
        "run_diff":   "betting_ml/models/run_differential/feature_columns_pre_lineup_run_diff.json",
        "total_runs": "betting_ml/models/total_runs/feature_columns_pre_lineup_total_runs.json",
    },
}

# Simplicity rank for the tie-break (lower = simpler/more-preferred per the E1.9 spec:
# "ties → simpler / more-calibrated wins"). A linear GLM is simplest; a stack of models is
# the most complex. Used only to surface the SIMPLEST tied candidate — the automated pick
# still breaks on calibration, but the report shows the leader + simplest so a human can override.
_COMPLEXITY = {"glm_elasticnet": 0, "ngboost_normal": 1, "ngboost_lognormal": 1,
               "xgboost": 2, "lightgbm": 2, "catboost": 2, "stack_mean": 3}


# Market-blindness CONTRACT-GUARD: any feature whose name matches one of these stems is a
# market/odds signal and must NOT be in a non-market model's trained feature set.
_MARKET_STEMS = ("implied_prob", "_ml_", "ml_money", "ml_ticket", "consensus", "total_line",
                 "over_prob", "under_prob", "over_american", "under_american", "devig",
                 "close_vf", "open_total", "line_movement", "sharp_soft", "money_pct",
                 "ticket_pct", "vig", "odds", "american")


def _contract_cols(target: str, tier: str, df: pd.DataFrame, override: str | None = None) -> list[str]:
    path = override or _CONTRACTS[tier][target]
    raw = json.loads((PROJECT_ROOT / path).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    return [c for c in cols if c in df.columns]


def _assert_market_blind(cols: list[str]) -> None:
    """CONTRACT-GUARD: a non-market model may not train on market/odds columns."""
    bad = [c for c in cols if any(s in c.lower() for s in _MARKET_STEMS)]
    if bad:
        raise SystemExit(f"❌ CONTRACT-GUARD: market columns in the trained contract: {bad}")


# ── candidate adapters (each returns a PredictiveOutput) ─────────────────────

@dataclass
class CalibratedProbaSpec:
    """Any sklearn-style classifier (predict_proba) + Platt calibration on the eval split —
    the home_win production recipe generalized to LightGBM/CatBoost/logistic."""
    factory: object
    name: str

    def fit(self, Xtr, ytr, Xcal, ycal, sample_weight=None):
        """Split fit→predict so this class can be an MDA scorer (fit once, re-predict on
        permuted matrices). Mirrors XGBPlattSpec: Platt calibrator frozen on the cal split."""
        from sklearn.linear_model import LogisticRegression
        clf = self.factory()
        if sample_weight is None:
            clf.fit(Xtr, ytr.astype(int))
        else:
            try:
                clf.fit(Xtr, ytr.astype(int), sample_weight=sample_weight)
            except (TypeError, ValueError):
                clf.fit(Xtr, ytr.astype(int))
        raw_cal = clf.predict_proba(Xcal)[:, 1]
        cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        cal.fit(raw_cal.reshape(-1, 1), ycal.astype(int))

        def _output(X) -> PredictiveOutput:
            raw = clf.predict_proba(X)[:, 1]
            return PredictiveOutput.binary(cal.predict_proba(raw.reshape(-1, 1))[:, 1])

        return _Predictor(_output)

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None) -> PredictiveOutput:
        return self.fit(Xtr, ytr, Xev, yev, sample_weight=sample_weight).output(Xev)


@dataclass
class PointNormalSpec:
    """Any point regressor → a homoscedastic Normal predictive: Normal(pred, σ̂) where σ̂ is
    the in-fold training residual std. Gives point learners an honest predictive distribution
    so they are comparable to NGBoost on crps/nll (a point mass would otherwise score crps=|e|
    and be unfairly credited/penalized vs a calibrated spread)."""
    factory: object
    name: str

    def fit(self, Xtr, ytr, Xcal=None, ycal=None, sample_weight=None):
        """Split fit→predict so this class can be an MDA scorer (the homoscedastic σ̂ is the
        training residual std, frozen; output(X) emits Normal(pred(X), σ̂))."""
        est = self.factory()
        if sample_weight is None:
            est.fit(Xtr, ytr)
        else:
            try:
                est.fit(Xtr, ytr, sample_weight=sample_weight)
            except (TypeError, ValueError):
                est.fit(Xtr, ytr)
        resid = np.asarray(ytr, float) - np.asarray(est.predict(Xtr), float)
        sigma = float(np.std(resid)) or 1.0

        def _output(X) -> PredictiveOutput:
            pred = np.asarray(est.predict(X), float)
            return PredictiveOutput.normal(pred, np.full(len(pred), sigma))

        return _Predictor(_output)

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None) -> PredictiveOutput:
        return self.fit(Xtr, ytr, Xev, yev, sample_weight=sample_weight).output(Xev)


@dataclass
class StackMeanSpec:
    """Simple ensemble: average the base specs' predictive means (and, for Normal arms, pool
    σ as the RMS) — a no-tuning stack baseline so 'does combining classes help?' is on record."""
    bases: list
    kind: str
    name: str = "stack_mean"

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None) -> PredictiveOutput:
        outs = [b.fit_predict(Xtr, ytr, Xev, yev, sample_weight=sample_weight) for b in self.bases]
        if self.kind == "clf":
            p = np.mean([o.prob for o in outs], axis=0)
            return PredictiveOutput.binary(p)
        loc = np.mean([o.mean for o in outs], axis=0)
        scales = [o.scale for o in outs if o.scale is not None]
        sigma = (np.sqrt(np.mean([s ** 2 for s in scales], axis=0)) if scales
                 else np.full(len(loc), float(np.std(ytr)) or 1.0))
        return PredictiveOutput.normal(loc, sigma)


@dataclass
class _ConstFloor:
    """Non-trainable reference floor: emits a fixed predictive ignoring X (no-skill / market)."""
    kind: str
    name: str
    market_col: str | None = None
    _df: pd.DataFrame | None = None  # set by the driver for market floors (eval-row lookup)

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None) -> PredictiveOutput:
        n = len(Xev)
        if self.market_col is not None:  # market floor reads the market column on eval rows
            vals = np.asarray(self._df.loc[Xev.index, self.market_col], float)
            if self.kind == "clf":
                return PredictiveOutput.binary(np.clip(vals, 1e-6, 1 - 1e-6))
            sigma = float(np.std(np.asarray(ytr, float))) or 1.0
            return PredictiveOutput.normal(vals, np.full(n, sigma))
        if self.kind == "clf":  # no-skill = train base rate
            return PredictiveOutput.binary(np.full(n, float(np.mean(ytr))))
        return PredictiveOutput.normal(np.full(n, float(np.mean(ytr))),
                                       np.full(n, float(np.std(ytr)) or 1.0))


def _candidates(kind: str, target: str, df: pd.DataFrame, *, seed: int, smoke: bool) -> list:
    """The bake-off slate (default-ish configs — tuning is the SEPARATE Optuna step)."""
    n_est = 60 if smoke else 400
    cfg = _TARGETS[target]
    cands: list = []
    if kind == "clf":
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        xgb = XGBPlattSpec({"n_estimators": n_est, "max_depth": 4, "learning_rate": 0.05,
                            "subsample": 0.8, "colsample_bytree": 0.8, "tree_method": "hist",
                            "eval_metric": "logloss", "random_state": seed, "n_jobs": -1},
                           name="xgboost")
        lgbm = CalibratedProbaSpec(lambda: LGBMClassifier(
            n_estimators=n_est, max_depth=-1, num_leaves=31, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, random_state=seed, n_jobs=-1, verbose=-1),
            name="lightgbm")
        cat = CalibratedProbaSpec(lambda: CatBoostClassifier(
            iterations=n_est, depth=5, learning_rate=0.05, random_seed=seed, verbose=0,
            allow_writing_files=False), name="catboost")
        glm = CalibratedProbaSpec(lambda: make_pipeline(
            StandardScaler(), LogisticRegression(penalty="elasticnet", l1_ratio=0.5, C=0.5,
            solver="saga", max_iter=2000, random_state=seed)), name="glm_elasticnet")
        cands = [xgb, lgbm, cat, glm]
        if not smoke:
            cands.append(StackMeanSpec([xgb, lgbm, glm], kind="clf", name="stack_mean"))
        cands.append(_ConstFloor("clf", "floor_no_skill"))
        if cfg.get("market_prob") in df.columns:
            cands.append(_ConstFloor("clf", "floor_market", market_col=cfg["market_prob"], _df=df))
    else:
        from catboost import CatBoostRegressor
        from lightgbm import LGBMRegressor
        from sklearn.linear_model import ElasticNet
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        ngb = NGBoostSpec(n_est, "Normal", name="ngboost_normal", seed=seed)
        xgbr = PointNormalSpec(lambda: __import__("xgboost").XGBRegressor(
            n_estimators=n_est, max_depth=4, learning_rate=0.05, subsample=0.8,
            colsample_bytree=0.8, tree_method="hist", random_state=seed, n_jobs=-1),
            name="xgboost")
        lgbmr = PointNormalSpec(lambda: LGBMRegressor(
            n_estimators=n_est, num_leaves=31, learning_rate=0.05, subsample=0.8,
            colsample_bytree=0.8, random_state=seed, n_jobs=-1, verbose=-1), name="lightgbm")
        catr = PointNormalSpec(lambda: CatBoostRegressor(
            iterations=n_est, depth=5, learning_rate=0.05, random_seed=seed, verbose=0,
            allow_writing_files=False), name="catboost")
        glmr = PointNormalSpec(lambda: make_pipeline(
            StandardScaler(), ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=seed)),
            name="glm_elasticnet")
        cands = [ngb, xgbr, lgbmr, catr, glmr]
        if cfg.get("allow_lognormal") and not smoke:
            cands.append(NGBoostSpec(n_est, "LogNormal", name="ngboost_lognormal", seed=seed))
        if not smoke:
            cands.append(StackMeanSpec([ngb, xgbr, lgbmr], kind="reg", name="stack_mean"))
        cands.append(_ConstFloor("reg", "floor_no_skill"))
        if cfg.get("market_point") and cfg["market_point"] in df.columns:
            cands.append(_ConstFloor("reg", "floor_market", market_col=cfg["market_point"], _df=df))
    return cands


def _binary_ece(y, p, n_bins: int = 10) -> float:
    """Expected Calibration Error for a binary predictive (lower = better calibrated)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    ok = np.isfinite(p)
    if not ok.all():
        y, p = y[ok], p[ok]
    if len(p) == 0:
        return float("nan")
    bins = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    ece = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            ece += abs(p[m].mean() - y[m].mean()) * m.mean()
    return float(ece)


def load_clean_matrix(*, refresh_cache: bool, smoke: bool) -> pd.DataFrame:
    """The cached training matrix with BOTH E1 de-leak swaps applied in memory — i.e. exactly
    the matrix the E1.8 slim contracts were derived on. `--smoke` caps to 400 rows/season."""
    df = get_cached_df("edge_e1_training", load_features, refresh=refresh_cache).reset_index(drop=True)
    print("Applying E1 de-leak swaps (bullpen_v3 + Stuff+ prior-season) ...")
    df = _swap_bullpen_v3(df, 1.0)
    df = _swap_stuff_plus_deleaked(df).reset_index(drop=True)
    if smoke:
        df = df.groupby("game_year", group_keys=False).head(400).reset_index(drop=True)
    return df


def run_bakeoff(target: str, tier: str, *, seed: int, smoke: bool, refresh_cache: bool,
                embargo_days: int, contract: str | None = None) -> dict:
    cfg = _TARGETS[target]
    kind, metric, tcol = cfg["kind"], cfg["metric"], cfg["col"]

    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke)
    cols = _contract_cols(target, tier, df, override=contract)
    _assert_market_blind(cols)
    if any(is_identifier_name(c) for c in cols):
        raise SystemExit(f"❌ identifier column(s) in contract: {[c for c in cols if is_identifier_name(c)]}")
    contract_path = contract or _CONTRACTS[tier][target]
    print(f"target={target} tier={tier} | {len(cols)} features | {len(df)} rows | metric={metric}")
    if contract:
        print(f"  [--contract] evaluating override contract: {contract}")

    cands = _candidates(kind, target, df, seed=seed, smoke=smoke)
    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=embargo_days)
    folds = list(splitter(df))
    print(f"{len(cands)} candidates × {len(folds)} purged folds")

    # per-candidate: pooled per-game scores (+ eval index for bucketing) and calibration
    per_game: dict[str, list] = {c.name: [] for c in cands}
    extra_metric = "nll"
    for tr, ev in folds:
        ytr, yev = df.loc[tr, tcol].values, df.loc[ev, tcol].values
        Xtr, Xev = _impute(df.loc[tr, cols], df.loc[ev, cols])
        for c in cands:
            out = c.fit_predict(Xtr, ytr, Xev, yev)
            per_game[c.name].append((ev, out, yev))

    # pool across folds, compute primary + extras + calibration, and a (bucket × cand) matrix
    rows = []
    bucket_perf: dict[str, dict] = {}
    for c in cands:
        primary, extra, mae_all, ys, buckets = [], [], [], [], []
        cal_accum = {"pit_ks": [], "coverage_gap": [], "ece": []}
        for ev, out, yev in per_game[c.name]:
            primary.append(out.score_to_truth(yev, metric))
            try:
                extra.append(out.score_to_truth(yev, extra_metric))
            except Exception:
                extra.append(np.full(len(yev), np.nan))
            mae_all.append(out.score_to_truth(yev, "mae"))
            ys.append(yev)
            ym = (df.loc[ev, "game_year"].astype(int).astype(str) + "-"
                  + df.loc[ev, "game_date"].astype("datetime64[ns]").dt.month.astype(str).str.zfill(2))
            buckets.append(ym.values)
            if kind == "reg" and out.kind in ("normal", "lognormal", "samples"):
                rep = calibration_report(yev, out)
                cal_accum["pit_ks"].append(rep["pit_ks"]); cal_accum["coverage_gap"].append(rep["coverage_gap"])
            elif kind == "clf":
                cal_accum["ece"].append(_binary_ece(yev, out.prob))
        primary = np.concatenate(primary); extra = np.concatenate(extra)
        mae_all = np.concatenate(mae_all); bvec = np.concatenate(buckets)
        bucket_perf[c.name] = pd.Series(primary).groupby(pd.Series(bvec)).mean().to_dict()
        cal = (float(np.nanmean(cal_accum["ece"])) if kind == "clf"
               else float(np.nanmean(cal_accum["pit_ks"])) if cal_accum["pit_ks"] else float("nan"))
        rows.append({
            "candidate": c.name,
            "is_floor": c.name.startswith("floor_"),
            f"{metric}_mean": float(np.nanmean(primary)),
            f"{extra_metric}_mean": float(np.nanmean(extra)),
            "mae_mean": float(np.nanmean(mae_all)),
            "calibration": cal,  # clf: ECE; reg: PIT-KS (lower = better)
            "n": int(len(primary)),
        })

    table = pd.DataFrame(rows).sort_values(f"{metric}_mean").reset_index(drop=True)

    # PBO across the NON-floor candidate slate (the multiple-testing surface)
    slate = [c.name for c in cands if not c.name.startswith("floor_")]
    all_buckets = sorted(set().union(*[set(bucket_perf[n]) for n in slate]))
    perf = np.array([[bucket_perf[n].get(b, np.nan) for n in slate] for b in all_buckets])
    keep = ~np.isnan(perf).any(axis=1)
    pbo_val = float("nan")
    if keep.sum() >= 4 and len(slate) >= 2:
        pres = pbo_cscv(perf[keep], higher_is_better=False, n_splits=min(16, keep.sum() - (keep.sum() % 2)))
        pbo_val = float(pres.pbo)

    # winner: lowest primary among non-floors; ties within the noise floor break to better
    # calibration. The tie set, the primary leader, and the SIMPLEST tied class are all
    # recorded so the choice is transparent and a human can override (E1.9 spec: ties →
    # simpler/more-calibrated wins; the auto-pick uses calibration).
    nf = NOISE_FLOOR.get(metric, 0.0)
    non_floor = table[~table["is_floor"]].reset_index(drop=True)
    best = non_floor.iloc[0]
    tied = non_floor[non_floor[f"{metric}_mean"] <= best[f"{metric}_mean"] + nf]
    tie_members = list(tied["candidate"])
    primary_leader = str(best["candidate"])
    simplest = min(tie_members, key=lambda c: (_COMPLEXITY.get(c, 9), tie_members.index(c)))
    if len(tied) > 1:
        winner_row = tied.sort_values("calibration").iloc[0]
        reason = (f"tie within {nf} noise floor among {len(tied)} "
                  f"({', '.join(tie_members)}) → picked on best calibration; "
                  f"primary-leader={primary_leader}, simplest={simplest}")
    else:
        winner_row = best
        reason = f"clear best on {metric} (margin > {nf} noise floor)"
    winner = str(winner_row["candidate"])
    # margins vs the floors (honest framing: is there signal over no-skill / over market?)
    floor_rows = {r["candidate"]: r[f"{metric}_mean"] for r in table.to_dict("records") if r["is_floor"]}
    win_primary = float(winner_row[f"{metric}_mean"])
    margins = {f"vs_{k}": round(v - win_primary, 4) for k, v in floor_rows.items()}  # >0 ⇒ winner better

    result = {
        "target": target, "tier": tier, "metric": metric, "n_features": len(cols),
        "n_folds": len(folds), "seed": seed, "smoke": smoke,
        "winner": winner, "winner_reason": reason, "winner_within_noise_tie": int(len(tied)),
        "tie_members": tie_members, "primary_leader": primary_leader, "simplest_in_tie": simplest,
        "winner_margin_vs_floors": margins,
        "pbo_slate": pbo_val, "noise_floor": nf,
        "table": table.to_dict(orient="records"),
        "contract": contract_path,
        "variant": Path(contract).stem.replace("feature_columns_", "") if contract else None,
    }
    _write_report(result, table, winner_row)
    return result


def _write_report(result: dict, table: pd.DataFrame, winner_row) -> None:
    _REPORT_DIR.mkdir(parents=True, exist_ok=True); _JSON_DIR.mkdir(parents=True, exist_ok=True)
    t, tier, metric = result["target"], result["tier"], result["metric"]
    stem = (f"bakeoff_{t}_{tier}" + (f"_{result['variant']}" if result.get("variant") else "")
            + ("_smoke" if result["smoke"] else ""))
    (_JSON_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))
    lines = [
        f"# Model-Class Bake-off — {t} ({tier})  [E1.9 step 1]", "",
        f"- Honest metric: **{metric}** (lower=better) · {result['n_features']} feats · "
        f"{result['n_folds']} purged folds · seed {result['seed']}"
        + ("  ⚠️ **SMOKE** (capped rows/estimators — not a real result)" if result["smoke"] else ""),
        f"- **Auto-winner: `{result['winner']}`** — {result['winner_reason']}",
    ]
    if result["winner_within_noise_tie"] > 1:
        lines.append(
            f"  - ⚖️ **Tie set** (within {result['noise_floor']} noise floor): "
            + ", ".join(f"`{m}`" for m in result["tie_members"])
            + f". **Primary leader** = `{result['primary_leader']}`; **simplest** = `{result['simplest_in_tie']}`. "
            "The auto-pick used calibration — **operator/PM may override toward the primary-leader or "
            "simplest class before HPO** (all are statistically tied here).")
    mg = result.get("winner_margin_vs_floors", {})
    if mg:
        lines.append("  - Winner margin vs floors (>0 ⇒ winner better): "
                     + ", ".join(f"{k.replace('vs_floor_', 'vs ')} {v:+.4f}" for k, v in mg.items())
                     + f"  _(noise floor {result['noise_floor']})_")
    lines += [
        f"- PBO across slate (CSCV, E1.4): **{result['pbo_slate']:.3f}**"
        + ("  ✅ < 0.2" if result["pbo_slate"] == result["pbo_slate"] and result["pbo_slate"] < 0.2
           else "  ⚠️ ≥ 0.2 (selection may be overfit)" if result["pbo_slate"] == result["pbo_slate"] else "  (n/a)"),
        "",
        f"| rank | candidate | {metric} | nll | mae | calibration | floor? |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(table.itertuples(), 1):
        cal = f"{r.calibration:.4f}" if r.calibration == r.calibration else "—"
        primary = getattr(r, f"{metric}_mean")
        nll = getattr(r, "nll_mean")
        floor = "✅" if r.is_floor else ""
        lines.append(f"| {i} | `{r.candidate}` | {primary:.4f} | {nll:.4f} | "
                     f"{r.mae_mean:.4f} | {cal} | {floor} |")
    lines += ["",
              "Calibration = ECE (home_win) / PIT-KS (totals/run_diff), lower=better. Floors "
              "(no-skill, market) are reference baselines, NOT promotable candidates. Winner "
              "feeds Optuna HPO (E1.9 step 2); offline scores are LOWER post-de-leak by design "
              "— the honest gate is forward/serving-parity + PBO/DSR, not raw offline metric."]
    (_REPORT_DIR / f"{stem}.md").write_text("\n".join(lines))
    print(f"\nWrote {_REPORT_DIR / f'{stem}.md'}")
    print(f"→ WINNER: {result['winner']}  | PBO={result['pbo_slate']:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(_TARGETS), required=True)
    ap.add_argument("--tier", choices=list(_CONTRACTS), default="post_lineup")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="Cap rows/estimators/candidates for a fast harness check.")
    ap.add_argument("--contract", default=None,
                    help="Evaluate an explicit contract path (E1.9 re-prune variant) instead of the tier default.")
    args = ap.parse_args()
    run_bakeoff(args.target, args.tier, seed=args.seed, smoke=args.smoke,
                refresh_cache=args.refresh_cache, embargo_days=args.embargo_days,
                contract=args.contract)


if __name__ == "__main__":
    main()
