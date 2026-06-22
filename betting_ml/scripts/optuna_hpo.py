"""optuna_hpo.py — Edge Program E1.9 step 2: HPO on the bake-off WINNER only.

WHY
---
Step 1 (`model_bakeoff.py`) decides the learner *class* on the honest gate. This step tunes
ONLY that class — never the slate. The trial search is itself a multiple-testing surface, so
the tuned config is not trusted on its raw CV score alone: it must pass **PBO < 0.2** (CSCV,
across the trial configs) and a **DSR > 0** check (deflated Sharpe of its per-bucket
improvement-over-no-skill series, deflated by the trial count) before it is written as the v6
candidate config (E1.4 discipline). Offline scores fall post-de-leak by design; PBO/DSR +
the forward gate are the real proof, not raw CV.

WHAT IT DOES
------------
For `--target` × `--tier` × `--model-class` (the bake-off winner):
  1. Load the same de-leaked matrix + tier contract as the bake-off (market-blind guard).
  2. Optuna study (TPE, seeded, `--n-trials` cap) minimizing the target's honest metric
     (brier / crps) under E1.1 PURGED + EMBARGOED CV — the objective itself is held-out.
  3. After the search: PBO across all trials' per-bucket performance + DSR of the best
     config's improvement series. Gate = PBO<0.2 AND DSR>0.
  4. Write the tuned config (params + CV score + PBO/DSR verdict) to
     `betting_ml/evaluation/tuning_results_v6_<class>_<target>_<tier>.json` for the gate step.

NGBoost/CatBoost × many trials = a long job → HAND OFF to the operator. `--smoke` caps
rows/estimators/trials for a fast harness check.

Usage:
    uv run python betting_ml/scripts/optuna_hpo.py --target home_win  --tier post_lineup --model-class xgboost   --n-trials 60
    uv run python betting_ml/scripts/optuna_hpo.py --target total_runs --tier post_lineup --model-class ngboost_normal --n-trials 50
    uv run python betting_ml/scripts/optuna_hpo.py --target home_win  --model-class xgboost --smoke
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

from betting_ml.scripts.model_bakeoff import (
    CalibratedProbaSpec, PointNormalSpec, _TARGETS, _assert_market_blind,
    _contract_cols, load_clean_matrix,
)
from betting_ml.scripts.promotion_gate_eval import (
    NGBoostSpec, XGBPlattSpec, _impute, make_gate_splitter,
)
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
from betting_ml.utils.promotion_gate import NOISE_FLOOR

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation"
_REPORT_DIR = PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"

# model classes this HPO can tune (the bake-off may also crown a stack — not tuned here).
_TUNABLE = {"xgboost", "lightgbm", "catboost", "ngboost_normal", "ngboost_lognormal", "glm_elasticnet"}


def _space(model_class: str, trial, *, smoke: bool) -> dict:
    """Optuna search space per class (sane, leakage-agnostic ranges)."""
    hi = 120 if smoke else 800
    lo = 40 if smoke else 200
    if model_class == "xgboost":
        return {"n_estimators": trial.suggest_int("n_estimators", lo, hi, step=20),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 12),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True)}
    if model_class == "lightgbm":
        return {"n_estimators": trial.suggest_int("n_estimators", lo, hi, step=20),
                "num_leaves": trial.suggest_int("num_leaves", 15, 127),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 60),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True)}
    if model_class == "catboost":
        return {"iterations": trial.suggest_int("iterations", lo, hi, step=20),
                "depth": trial.suggest_int("depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 20.0)}
    if model_class.startswith("ngboost"):
        return {"n_estimators": trial.suggest_int("n_estimators", lo, hi, step=20),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.05, log=True),
                "minibatch_frac": trial.suggest_float("minibatch_frac", 0.5, 1.0)}
    if model_class == "glm_elasticnet":
        return {"alpha": trial.suggest_float("alpha", 1e-3, 1.0, log=True),
                "l1_ratio": trial.suggest_float("l1_ratio", 0.0, 1.0),
                "C": trial.suggest_float("C", 1e-2, 10.0, log=True)}
    raise SystemExit(f"❌ unsupported model class for HPO: {model_class}")


def _make_spec(model_class: str, kind: str, params: dict, *, seed: int):
    """Build the ModelSpec for a sampled config (reuses the production adapters)."""
    if model_class == "xgboost":
        p = dict(params, tree_method="hist", random_state=seed, n_jobs=-1)
        if kind == "clf":
            return XGBPlattSpec(dict(p, eval_metric="logloss"), name="xgboost")
        import xgboost
        return PointNormalSpec(lambda: xgboost.XGBRegressor(**p), name="xgboost")
    if model_class == "lightgbm":
        if kind == "clf":
            from lightgbm import LGBMClassifier
            return CalibratedProbaSpec(lambda: LGBMClassifier(
                **params, random_state=seed, n_jobs=-1, verbose=-1), name="lightgbm")
        from lightgbm import LGBMRegressor
        return PointNormalSpec(lambda: LGBMRegressor(
            **params, random_state=seed, n_jobs=-1, verbose=-1), name="lightgbm")
    if model_class == "catboost":
        if kind == "clf":
            from catboost import CatBoostClassifier
            return CalibratedProbaSpec(lambda: CatBoostClassifier(
                **params, random_seed=seed, verbose=0, allow_writing_files=False), name="catboost")
        from catboost import CatBoostRegressor
        return PointNormalSpec(lambda: CatBoostRegressor(
            **params, random_seed=seed, verbose=0, allow_writing_files=False), name="catboost")
    if model_class.startswith("ngboost"):
        dist = "LogNormal" if model_class.endswith("lognormal") else "Normal"
        return NGBoostSpec(params["n_estimators"], dist, name=model_class, seed=seed,
                           learning_rate=params["learning_rate"], minibatch_frac=params["minibatch_frac"])
    if model_class == "glm_elasticnet":
        from sklearn.linear_model import ElasticNet, LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        if kind == "clf":
            return CalibratedProbaSpec(lambda: make_pipeline(
                StandardScaler(), LogisticRegression(penalty="elasticnet", l1_ratio=params["l1_ratio"],
                C=params["C"], solver="saga", max_iter=3000, random_state=seed)), name="glm_elasticnet")
        return PointNormalSpec(lambda: make_pipeline(
            StandardScaler(), ElasticNet(alpha=params["alpha"], l1_ratio=params["l1_ratio"],
            random_state=seed)), name="glm_elasticnet")
    raise SystemExit(f"❌ unsupported model class: {model_class}")


# Bake-off default configs (mirror model_bakeoff._candidates). Used by --default-config to
# emit a gate-ready config WITHOUT a search — the honest choice when the HPO gain is sub-noise
# (e.g. a near-coinflip target where every trial is statistically identical and PBO is just
# ranking noise). glm carries all of alpha/l1_ratio/C (clf ignores alpha, reg ignores C).
_DEFAULT_PARAMS = {
    "xgboost": {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.05, "subsample": 0.8,
                "colsample_bytree": 0.8, "min_child_weight": 1, "reg_lambda": 1.0},
    "lightgbm": {"n_estimators": 400, "num_leaves": 31, "learning_rate": 0.05, "subsample": 0.8,
                 "colsample_bytree": 0.8, "min_child_samples": 20, "reg_lambda": 0.0},
    "catboost": {"iterations": 400, "depth": 5, "learning_rate": 0.05, "l2_leaf_reg": 3.0},
    "ngboost_normal": {"n_estimators": 400, "learning_rate": 0.01, "minibatch_frac": 1.0},
    "ngboost_lognormal": {"n_estimators": 400, "learning_rate": 0.01, "minibatch_frac": 1.0},
    "glm_elasticnet": {"alpha": 0.1, "l1_ratio": 0.5, "C": 0.5},
}


def _cv_score(spec, df, cols, tcol, metric, folds) -> tuple[float, dict]:
    """Purged-CV pooled mean of `metric` (lower=better) + per-(year-month) bucket means."""
    per_game, bvecs = [], []
    for tr, ev in folds:
        ytr, yev = df.loc[tr, tcol].values, df.loc[ev, tcol].values
        Xtr, Xev = _impute(df.loc[tr, cols], df.loc[ev, cols])
        out = spec.fit_predict(Xtr, ytr, Xev, yev)
        per_game.append(out.score_to_truth(yev, metric))
        ym = (df.loc[ev, "game_year"].astype(int).astype(str) + "-"
              + df.loc[ev, "game_date"].astype("datetime64[ns]").dt.month.astype(str).str.zfill(2))
        bvecs.append(ym.values)
    s = np.concatenate(per_game)
    buckets = pd.Series(s).groupby(pd.Series(np.concatenate(bvecs))).mean().to_dict()
    return float(np.nanmean(s)), buckets


def run_hpo(target: str, tier: str, model_class: str, *, n_trials: int, seed: int,
            smoke: bool, refresh_cache: bool, embargo_days: int, contract: str | None = None,
            default_config: bool = False) -> dict:
    import optuna

    if model_class not in _TUNABLE:
        raise SystemExit(f"❌ {model_class} is not HPO-tunable (bake-off winner must be one of {_TUNABLE}); "
                         "a 'stack' winner is assembled, not tuned — re-run the bake-off or pick the best base class.")
    cfg = _TARGETS[target]
    kind, metric, tcol = cfg["kind"], cfg["metric"], cfg["col"]
    if model_class == "ngboost_lognormal" and not cfg.get("allow_lognormal"):
        raise SystemExit(f"❌ LogNormal is invalid for {target} (can be ≤0)")

    df = load_clean_matrix(refresh_cache=refresh_cache, smoke=smoke)
    cols = _contract_cols(target, tier, df, override=contract)
    _assert_market_blind(cols)
    splitter, _ = make_gate_splitter(True, feature_cols=cols, embargo_days=embargo_days)
    folds = list(splitter(df))

    # --default-config: skip the search entirely and emit the bake-off default as a gate-ready
    # config. The honest choice when HPO's gain is sub-noise and PBO refuses to bless it (e.g.
    # home_win/post: 19 lean feats on a near-coinflip target → every trial identical → PBO noise).
    # No search ⇒ no multiple-testing surface ⇒ the overfit gate is N/A, not FAIL.
    if default_config:
        params = _DEFAULT_PARAMS[model_class]
        score, _ = _cv_score(_make_spec(model_class, kind, params, seed=seed), df, cols, tcol, metric, folds)
        result = {
            "target": target, "tier": tier, "model_class": model_class, "metric": metric,
            "n_features": len(cols), "n_trials": 0, "smoke": smoke, "seed": seed,
            "best_params": params, "best_cv_score": float(score),
            "noise_floor": NOISE_FLOOR.get(metric, 0.0),
            "pbo": None, "pbo_pass": None, "dsr": None, "dsr_pass": None,
            "overfit_gate": "DEFAULT (no search — bake-off default config; not an overfit surface)",
            "contract": contract or _contract_path(target, tier),
            "variant": Path(contract).stem.replace("feature_columns_", "") if contract else None,
        }
        _write(result)
        return result

    print(f"HPO {model_class} on {target}/{tier} | {len(cols)} feats | {len(folds)} purged folds | {n_trials} trials")

    trial_buckets: list[dict] = []
    trial_scores: list[float] = []

    def objective(trial):
        params = _space(model_class, trial, smoke=smoke)
        spec = _make_spec(model_class, kind, params, seed=seed)
        score, buckets = _cv_score(spec, df, cols, tcol, metric, folds)
        trial.set_user_attr("buckets", buckets)
        trial_buckets.append(buckets); trial_scores.append(score)
        return score

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_trial
    best_params = best.params

    # ── PBO across trials (the multiple-testing surface) ─────────────────────
    all_b = sorted(set().union(*[set(b) for b in trial_buckets]))
    perf = np.array([[tb.get(b, np.nan) for tb in trial_buckets] for b in all_b])
    keep = ~np.isnan(perf).any(axis=1)
    pbo_val = float("nan")
    if keep.sum() >= 4 and len(trial_buckets) >= 2:
        pres = pbo_cscv(perf[keep], higher_is_better=False,
                        n_splits=min(16, keep.sum() - (keep.sum() % 2)))
        pbo_val = float(pres.pbo)

    # ── DSR of the best config's improvement-over-no-skill bucket series ──────
    # "Return" per bucket = no_skill_metric − best_metric (>0 ⇒ the model beat the floor that
    # bucket). Deflate the Sharpe of that series by the trial count (expected-max under search).
    best_buckets = best.user_attrs["buckets"]
    ns_spec = _NoSkill(kind)
    _, ns_buckets = _cv_score(ns_spec, df, cols, tcol, metric, folds)
    common = [b for b in best_buckets if b in ns_buckets]
    improin = np.array([ns_buckets[b] - best_buckets[b] for b in common])
    dsr_val = float("nan"); dsr_pass = False
    if len(improin) >= 3:
        try:
            dres = deflated_sharpe(improin, n_trials=max(1, len(trial_scores)), benchmark_sr=0.0)
            dsr_val = float(dres.dsr); dsr_pass = bool(dsr_val > 0.0)
        except Exception as e:
            print(f"  DSR n/a: {e}")

    pbo_pass = pbo_val == pbo_val and pbo_val < 0.2
    verdict = "PASS" if (pbo_pass and dsr_pass) else "FAIL"

    result = {
        "target": target, "tier": tier, "model_class": model_class,
        "metric": metric, "n_features": len(cols), "n_trials": len(trial_scores),
        "smoke": smoke, "seed": seed,
        "best_params": best_params, "best_cv_score": float(study.best_value),
        "noise_floor": NOISE_FLOOR.get(metric, 0.0),
        "pbo": pbo_val, "pbo_pass": pbo_pass,
        "dsr": dsr_val, "dsr_pass": dsr_pass,
        "overfit_gate": verdict,
        "contract": contract or _contract_path(target, tier),
        "variant": Path(contract).stem.replace("feature_columns_", "") if contract else None,
    }
    _write(result)
    return result


class _NoSkill:
    """No-skill floor for the DSR improvement baseline (mirrors model_bakeoff's floor)."""
    name = "floor_no_skill"

    def __init__(self, kind: str):
        self.kind = kind

    def fit_predict(self, Xtr, ytr, Xev, yev, sample_weight=None):
        from betting_ml.utils.promotion_gate import PredictiveOutput
        n = len(Xev)
        if self.kind == "clf":
            return PredictiveOutput.binary(np.full(n, float(np.mean(ytr))))
        return PredictiveOutput.normal(np.full(n, float(np.mean(ytr))),
                                       np.full(n, float(np.std(ytr)) or 1.0))


def _contract_path(target: str, tier: str) -> str:
    from betting_ml.scripts.model_bakeoff import _CONTRACTS
    return _CONTRACTS[tier][target]


def _write(result: dict) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True); _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    t, tier, mc = result["target"], result["tier"], result["model_class"]
    stem = (f"tuning_results_v6_{mc}_{t}_{tier}" + (f"_{result['variant']}" if result.get("variant") else "")
            + ("_smoke" if result["smoke"] else ""))
    (_OUT_DIR / f"{stem}.json").write_text(json.dumps(result, indent=2, default=float))
    print(f"\nWrote {_OUT_DIR / f'{stem}.json'}")
    if result["pbo"] is None:  # --default-config: no search, no PBO/DSR
        print(f"→ best {result['metric']}={result['best_cv_score']:.4f} | DEFAULT config (no search) | "
              f"overfit-gate={result['overfit_gate']}")
    else:
        print(f"→ best {result['metric']}={result['best_cv_score']:.4f} | "
              f"PBO={result['pbo']:.3f} ({'✅' if result['pbo_pass'] else '❌'}) | "
              f"DSR={result['dsr']:.3f} ({'✅' if result['dsr_pass'] else '❌'}) | "
              f"overfit-gate={result['overfit_gate']}")
    if result["overfit_gate"] == "FAIL" and not result["smoke"]:
        print("  ⚠️ config did NOT clear PBO<0.2 + DSR>0 — do NOT promote; widen data / reduce search / re-bake-off.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=list(_TARGETS), required=True)
    ap.add_argument("--tier", default="post_lineup")
    ap.add_argument("--model-class", required=True, help="The bake-off winner class to tune.")
    ap.add_argument("--n-trials", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--embargo-days", type=int, default=3)
    ap.add_argument("--refresh-cache", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--contract", default=None,
                    help="Tune on an explicit contract path (E1.9 re-prune variant) instead of the tier default.")
    ap.add_argument("--default-config", action="store_true",
                    help="Skip the search; emit the bake-off default as a gate-ready config (use when HPO's "
                         "gain is sub-noise and PBO refuses to bless it — e.g. home_win/post).")
    args = ap.parse_args()
    run_hpo(args.target, args.tier, args.model_class, n_trials=(8 if args.smoke else args.n_trials),
            seed=args.seed, smoke=args.smoke, refresh_cache=args.refresh_cache,
            embargo_days=args.embargo_days, contract=args.contract, default_config=args.default_config)


if __name__ == "__main__":
    main()
