"""
train_h2h.py — Epic 11, Story 11.3 (Approach B: direct classifier)

Train a binary classifier directly on the Layer 3 feature matrix with `home_win`
as the target, market-blind. Two candidates (two-model minimum), walk-forward CV
on the same season-forward folds as Epic 10:

  A1 — Elasticnet logistic regression (impute → scale → LogisticRegression
       penalty='elasticnet', saga). Direct parallel to Epic 1's market-blind
       baseline; fast and interpretable. Optuna tunes C + l1_ratio.
  A2 — LightGBM binary classifier + Platt scaling (CalibratedClassifierCV
       method='sigmoid', honest internal CV — calibration is NOT fit on the eval
       fold). Optuna tunes n_estimators / learning_rate / num_leaves /
       min_child_samples. Reports calibrated vs. uncalibrated log-loss.

Selection (within Approach B): lower CV log-loss (NLL) is the primary gate;
Brier / ECE reported; Wilcoxon paired test on per-game log-loss for significance.
The A-vs-B champion is decided in Story 11.4 (Brier primary) — this script does
NOT touch model_registry.yaml.

Beta representation: the classifier probability is `p_home_win`; ECE is reported
as a (coarse, global) uncertainty proxy. See the report for why the principled
per-game uncertainty is Approach A's `win_prob_to_beta` / Epic 9 `combined_sigma`,
not a single ECE-derived concentration.

Artifact: betting_ml/models/sub_models/h2h_v2_approach_b.pkl (H2HClassifierModel)
Report:   ablation_results/h2h_v2_approach_b.md
MLflow:   experiment `h2h_v2`

Usage:
    # Full train + CV + candidate comparison (HAND OFF — minutes):
    uv run python betting_ml/scripts/train_h2h.py --env prod
    # Fast smoke (subsample + few trials, no MLflow):
    uv run python betting_ml/scripts/train_h2h.py --env prod --quick --no-mlflow
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import build_h2h_dataset  # noqa: E402
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402
from betting_ml.models.totals_negbin_model import coerce_numeric as _coerce_numeric  # noqa: E402
from betting_ml.models.h2h_classifier_model import H2HClassifierModel  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "h2h_v2_approach_b.pkl"
_COMPARISON_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "h2h_v2_approach_b.md"
)

_MIN_TRAIN_SEASONS = 2     # 2021-2026 → eval folds 2023..2026 (same as Epic 10)
_OPTUNA_SEED = 42
_MLFLOW_EXPERIMENT = "h2h_v2"
_N_TRIALS = 30
_CALIB_BINS = 10
_PLATT_CV = 3              # internal CV folds for CalibratedClassifierCV (sigmoid/Platt)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def per_game_logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, float), 1e-15, 1 - 1e-15)
    y = np.asarray(y, float)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def ece(p: np.ndarray, y: np.ndarray, n_bins: int = _CALIB_BINS) -> float:
    """Expected calibration error: |confidence − accuracy| weighted by bin mass."""
    p = np.asarray(p, float); y = np.asarray(y, float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    idx = np.digitize(p, edges[1:-1])
    n = len(p)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        e += (m.sum() / n) * abs(p[m].mean() - y[m].mean())
    return float(e)


# ---------------------------------------------------------------------------
# Candidate fitters / predictors
# ---------------------------------------------------------------------------

def _fit_elasticnet(X_tr: pd.DataFrame, y_tr: np.ndarray, params: dict):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        # sklearn ≥1.8: l1_ratio controls the elastic-net mix (0=L2, 1=L1);
        # the `penalty` arg is deprecated, so it is intentionally omitted.
        ("clf", LogisticRegression(
            solver="saga", C=params["C"], l1_ratio=params["l1_ratio"],
            max_iter=2000, random_state=_OPTUNA_SEED)),
    ])
    pipe.fit(X_tr, y_tr)
    return pipe


def _lgbm(params: dict):
    import lightgbm as lgb
    return lgb.LGBMClassifier(objective="binary", verbosity=-1,
                              random_state=_OPTUNA_SEED, **params)


def _fit_lightgbm(X_tr: pd.DataFrame, y_tr: np.ndarray, params: dict, calibrate: bool):
    model = _lgbm(params)
    if calibrate:
        from sklearn.calibration import CalibratedClassifierCV
        # method='sigmoid' == Platt scaling; cv fits base model + calibrator on
        # internal train splits only (NOT the eval fold) → honest calibration.
        model = CalibratedClassifierCV(model, method="sigmoid", cv=_PLATT_CV)
    model.fit(X_tr, y_tr)
    return model


def _fit(kind: str, X_tr: pd.DataFrame, y_tr: np.ndarray, params: dict, calibrate: bool = False):
    if kind == "elasticnet":
        return _fit_elasticnet(X_tr, y_tr, params)
    return _fit_lightgbm(X_tr, y_tr, params, calibrate)


def _proba(model, X: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict_proba(X)[:, 1], dtype=float)


# ---------------------------------------------------------------------------
# Walk-forward CV
# ---------------------------------------------------------------------------

def _folds(meta: pd.DataFrame) -> list[tuple[pd.Index, pd.Index]]:
    return list(all_season_splits(meta, min_train_seasons=_MIN_TRAIN_SEASONS))


def _cv(kind: str, X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame,
        params: dict, calibrate: bool = False) -> dict:
    """Walk-forward CV. Returns mean metrics, per-fold (per-season) records, and the
    pooled eval predictions/targets (in fold order, for Wilcoxon + market baseline)."""
    fold_recs: list[dict] = []
    pooled_p: list[float] = []
    pooled_y: list[float] = []
    pooled_idx: list[int] = []
    for tr_idx, ev_idx in _folds(meta):
        X_tr, y_tr = X.loc[tr_idx], y.loc[tr_idx].to_numpy()
        X_ev, y_ev = X.loc[ev_idx], y.loc[ev_idx].to_numpy()
        model = _fit(kind, X_tr, y_tr, params, calibrate)
        p_ev = _proba(model, X_ev)
        fold_recs.append({
            "eval_year": int(meta.loc[ev_idx, "game_year"].iloc[0]),
            "n_eval": int(len(y_ev)),
            "log_loss": logloss(p_ev, y_ev),
            "brier": brier(p_ev, y_ev),
            "ece": ece(p_ev, y_ev),
        })
        pooled_p.extend(p_ev.tolist())
        pooled_y.extend(y_ev.tolist())
        pooled_idx.extend(list(ev_idx))
    agg = _aggregate(kind, fold_recs)
    agg["pooled_p"] = np.asarray(pooled_p, float)
    agg["pooled_y"] = np.asarray(pooled_y, float)
    agg["pooled_idx"] = np.asarray(pooled_idx, int)
    agg["pooled_ece"] = ece(agg["pooled_p"], agg["pooled_y"])
    return agg


def _aggregate(kind: str, fold_recs: list[dict]) -> dict:
    if not fold_recs:
        return {"kind": kind, "log_loss": float("inf"), "brier": float("inf"),
                "ece": 1.0, "folds": []}
    return {
        "kind": kind,
        "log_loss": float(np.mean([f["log_loss"] for f in fold_recs])),
        "brier": float(np.mean([f["brier"] for f in fold_recs])),
        "ece": float(np.mean([f["ece"] for f in fold_recs])),
        "folds": fold_recs,
    }


# ---------------------------------------------------------------------------
# Optuna tuning (minimize CV log-loss; uncalibrated during search)
# ---------------------------------------------------------------------------

def _tune(kind: str, X: pd.DataFrame, y: pd.Series, meta: pd.DataFrame, n_trials: int) -> dict:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        if kind == "elasticnet":
            params = {
                "C": trial.suggest_float("C", 1e-3, 1e2, log=True),
                "l1_ratio": trial.suggest_float("l1_ratio", 0.0, 1.0),
            }
        else:
            params = {
                "n_estimators": trial.suggest_int("n_estimators", 150, 600),
                "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.1, log=True),
                "num_leaves": trial.suggest_int("num_leaves", 15, 63),
                "min_child_samples": trial.suggest_int("min_child_samples", 20, 120),
            }
        return _cv(kind, X, y, meta, params, calibrate=False)["log_loss"]

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=_OPTUNA_SEED))
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    log.info("  Optuna(%s) best log_loss=%.4f params=%s", kind, study.best_value, study.best_params)
    return study.best_params


# ---------------------------------------------------------------------------
# Selection + finalize
# ---------------------------------------------------------------------------

def select_winner(a1: dict, a2: dict) -> tuple[str, dict]:
    """Lower CV log-loss wins (primary gate); Brier breaks ties within 0.0005."""
    if abs(a1["log_loss"] - a2["log_loss"]) < 5e-4:
        return ("elasticnet", a1) if a1["brier"] <= a2["brier"] else ("lightgbm", a2)
    return ("elasticnet", a1) if a1["log_loss"] < a2["log_loss"] else ("lightgbm", a2)


def finalize_model(kind: str, params: dict, X: pd.DataFrame, y: pd.Series) -> H2HClassifierModel:
    y_arr = y.to_numpy()
    if kind == "elasticnet":
        model = _fit_elasticnet(X, y_arr, params)
        return H2HClassifierModel("elasticnet", model, list(X.columns), calibrated=False)
    model = _fit_lightgbm(X, y_arr, params, calibrate=True)  # Platt-calibrated for production
    return H2HClassifierModel("lightgbm", model, list(X.columns), calibrated=True)


def market_baseline(eval_probs: pd.DataFrame, meta: pd.DataFrame, y: pd.Series,
                    pooled_idx: np.ndarray, pooled_y: np.ndarray) -> dict:
    """Brier/log-loss of the de-vigged market on the covered eval games (baseline to beat)."""
    prob_by_pk = dict(zip(eval_probs["game_pk"], eval_probs["bovada_devig_home_prob"]))
    g = meta.loc[pooled_idx, "game_pk"].to_numpy()
    mp, my = [], []
    for pk, yy in zip(g, pooled_y):
        v = prob_by_pk.get(int(pk))
        if v is not None and pd.notna(v):
            mp.append(float(v)); my.append(float(yy))
    if not mp:
        return {"n": 0, "brier": float("nan"), "log_loss": float("nan")}
    mp_arr, my_arr = np.asarray(mp), np.asarray(my)
    return {"n": len(mp), "brier": brier(mp_arr, my_arr), "log_loss": logloss(mp_arr, my_arr)}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fold_table(m: dict) -> list[str]:
    rows = ["| eval year | n | log-loss | Brier | ECE |", "|---|---|---|---|---|"]
    for f in m["folds"]:
        rows.append(f"| {f['eval_year']} | {f['n_eval']} | {f['log_loss']:.4f} | "
                    f"{f['brier']:.4f} | {f['ece']:.4f} |")
    return rows


def write_comparison(a1: dict, a2u: dict, a2c: dict, winner: str, tuned: dict,
                     wilcox_p: float, n_games: int, base_rate: float,
                     market: dict) -> Path:
    _COMPARISON_PATH.parent.mkdir(parents=True, exist_ok=True)
    n_folds = len(a1["folds"]) or len(a2c["folds"])
    win_label = "A1 — Elasticnet logistic" if winner == "elasticnet" else "A2 — LightGBM + Platt"
    win_metrics = a1 if winner == "elasticnet" else a2c
    platt_delta = a2u["log_loss"] - a2c["log_loss"]
    lines = [
        "# Layer 3 H2H — Approach B: Direct Classifier (Story 11.3)",
        "",
        f"- Games: **{n_games}**; `home_win` base rate **{base_rate:.4f}**; walk-forward folds "
        f"**{n_folds}** (min_train_seasons={_MIN_TRAIN_SEASONS}, eval = each held-out season).",
        f"- Selection: lower CV **log-loss** (NLL) is the primary gate; Brier/ECE reported; "
        f"Wilcoxon paired per-game log-loss for significance. A-vs-B champion is Story 11.4.",
        f"- Market baseline (de-vigged Bovada P(home), covered eval games n={market['n']}): "
        f"**Brier {market['brier']:.4f}**, log-loss {market['log_loss']:.4f} — the bar 11.4/11.7 must clear.",
        "",
        "## Candidate comparison (mean CV)",
        "",
        "| Candidate | log-loss | Brier | ECE |",
        "|---|---|---|---|",
        f"| A1 — Elasticnet logistic | {a1['log_loss']:.4f} | {a1['brier']:.4f} | {a1['pooled_ece']:.4f} |",
        f"| A2 — LightGBM (uncalibrated) | {a2u['log_loss']:.4f} | {a2u['brier']:.4f} | {a2u['pooled_ece']:.4f} |",
        f"| A2 — LightGBM + Platt | {a2c['log_loss']:.4f} | {a2c['brier']:.4f} | {a2c['pooled_ece']:.4f} |",
        "",
        f"- **Platt scaling improvement (A2):** log-loss {a2u['log_loss']:.4f} → {a2c['log_loss']:.4f} "
        f"(Δ {platt_delta:+.4f}; ECE {a2u['pooled_ece']:.4f} → {a2c['pooled_ece']:.4f}).",
        f"- **Wilcoxon A1 vs A2(+Platt) per-game log-loss:** p = {wilcox_p:.4g} "
        f"({'significant' if wilcox_p < 0.05 else 'not significant'} at 0.05).",
        "",
        f"**Approach B winner: {win_label}** — tuned params `{json.dumps(tuned)}`. "
        f"CV Brier **{win_metrics['brier']:.4f}**, log-loss {win_metrics['log_loss']:.4f}, "
        f"ECE {win_metrics['pooled_ece']:.4f}.",
        "",
        "## Head-to-head — Approach A vs. Approach B (filled by Story 11.4)",
        "",
        "| Approach | CV Brier | CV log-loss | ECE |",
        "|---|---|---|---|",
        f"| A — derived from run distributions (11.2) | _pending_ | _pending_ | _pending_ |",
        f"| **B — direct classifier (this story)** | **{win_metrics['brier']:.4f}** | "
        f"{win_metrics['log_loss']:.4f} | {win_metrics['pooled_ece']:.4f} |",
        "",
        "## Beta representation for Approach B (uncertainty)",
        "",
        f"The classifier emits a point `p_home_win`; its global ECE ({win_metrics['pooled_ece']:.4f}) "
        "is a *coarse, dataset-level* calibration measure, not a per-game uncertainty. Using ECE as a "
        "single Beta concentration would assign every game the same uncertainty — wrong for the Epic 19 "
        "gate, which needs `win_prob_uncertainty` to widen on low-signal / early-season games. The "
        "principled per-game uncertainty is Approach A's `win_prob_to_beta` (concentration from the "
        "joint run-distribution `combined_sigma`, Epic 9 stacking). **Recommendation:** if Approach B "
        "wins 11.4, pair its `p_home_win` with the Epic 9 `combined_sigma` to form the Beta, rather than "
        "an ECE-derived constant. Documented here per the 11.3 task.",
        "",
        "## Candidate A1 folds", "", *_fold_table(a1),
        "", "## Candidate A2 (+Platt) folds", "", *_fold_table(a2c),
    ]
    _COMPARISON_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote Approach B comparison → %s", _COMPARISON_PATH)
    return _COMPARISON_PATH


def _log_mlflow(a1: dict, a2u: dict, a2c: dict, winner: str, tuned: dict,
                wilcox_p: float, market: dict) -> str | None:
    try:
        import mlflow
        from betting_ml.utils.mlflow_utils import get_or_create_experiment
        exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
        with mlflow.start_run(experiment_id=exp_id, run_name="h2h_v2_approach_b") as run:
            mlflow.log_params({"winner": winner, "approach": "direct_classifier",
                               **{f"param__{k}": v for k, v in tuned.items()}})
            for label, m in (("A1_elasticnet", a1), ("A2_lgbm_uncal", a2u), ("A2_lgbm_platt", a2c)):
                mlflow.log_metric(f"{label}__log_loss", m["log_loss"])
                mlflow.log_metric(f"{label}__brier", m["brier"])
                mlflow.log_metric(f"{label}__ece", m["pooled_ece"])
                for f in m["folds"]:
                    mlflow.log_metric(f"{label}__brier__{f['eval_year']}", f["brier"])
                    mlflow.log_metric(f"{label}__log_loss__{f['eval_year']}", f["log_loss"])
            mlflow.log_metric("wilcoxon_p_a1_vs_a2", wilcox_p)
            mlflow.log_metric("market_brier", market["brier"])
            return run.info.run_id
    except Exception as exc:  # noqa: BLE001 — MLflow non-blocking
        log.warning("MLflow logging skipped: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(env: str = "prod", n_trials: int = _N_TRIALS, quick: bool = False,
        mlflow: bool = True) -> dict:
    X, y, eval_probs, report, meta = build_h2h_dataset(env=env, return_meta=True)
    X = _coerce_numeric(X)  # *_available object→float; NaN signals preserved (LGBM) / imputed (logistic)
    if quick:
        X = X.tail(1500).reset_index(drop=True)
        y = y.tail(1500).reset_index(drop=True)
        meta = meta.tail(1500).reset_index(drop=True)
        n_trials = 4

    n_folds = len(_folds(meta))
    log.info("H2H Approach B: %d games, %d folds (min_train_seasons=%d), base_rate=%.4f",
             len(X), n_folds, _MIN_TRAIN_SEASONS, float(y.mean()))
    if n_folds < 2:
        raise RuntimeError(f"Only {n_folds} CV fold(s) — need ≥2.")

    # A1 — elasticnet logistic
    log.info("Tuning A1 (elasticnet logistic) — %d trials...", n_trials)
    a1_params = _tune("elasticnet", X, y, meta, n_trials)
    a1 = _cv("elasticnet", X, y, meta, a1_params)
    log.info("  A1: log_loss=%.4f brier=%.4f ece=%.4f", a1["log_loss"], a1["brier"], a1["pooled_ece"])

    # A2 — LightGBM (uncalibrated for tuning/report) + Platt-calibrated
    log.info("Tuning A2 (LightGBM) — %d trials...", n_trials)
    a2_params = _tune("lightgbm", X, y, meta, n_trials)
    a2u = _cv("lightgbm", X, y, meta, a2_params, calibrate=False)
    a2c = _cv("lightgbm", X, y, meta, a2_params, calibrate=True)
    log.info("  A2 uncal: log_loss=%.4f brier=%.4f ece=%.4f", a2u["log_loss"], a2u["brier"], a2u["pooled_ece"])
    log.info("  A2 platt: log_loss=%.4f brier=%.4f ece=%.4f", a2c["log_loss"], a2c["brier"], a2c["pooled_ece"])

    # Wilcoxon A1 vs A2(+Platt) on per-game log-loss (folds/indices align by construction).
    ll_a1 = per_game_logloss(a1["pooled_p"], a1["pooled_y"])
    ll_a2 = per_game_logloss(a2c["pooled_p"], a2c["pooled_y"])
    try:
        wilcox_p = float(wilcoxon(ll_a1, ll_a2).pvalue)
    except ValueError:
        wilcox_p = float("nan")

    market = market_baseline(eval_probs, meta, y, a1["pooled_idx"], a1["pooled_y"])

    winner, win_metrics = select_winner(a1, a2c)
    tuned = a1_params if winner == "elasticnet" else a2_params
    log.info("Approach B winner: %s (CV Brier %.4f, log_loss %.4f)",
             winner, win_metrics["brier"], win_metrics["log_loss"])

    model_obj = finalize_model(winner, tuned, X, y)
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_obj, _ARTIFACT_PATH)
    log.info("Saved Approach B winner artifact → %s", _ARTIFACT_PATH)

    run_id = _log_mlflow(a1, a2u, a2c, winner, tuned, wilcox_p, market) if mlflow else None
    write_comparison(a1, a2u, a2c, winner, tuned, wilcox_p, len(X), float(y.mean()), market)

    log.info("Done. Approach B winner=%s | CV Brier=%.4f log_loss=%.4f ece=%.4f | "
             "market Brier=%.4f | mlflow=%s",
             winner, win_metrics["brier"], win_metrics["log_loss"], win_metrics["pooled_ece"],
             market["brier"], run_id or "skipped")
    return {"winner": winner, "metrics": win_metrics, "a1": a1, "a2u": a2u, "a2c": a2c,
            "wilcoxon_p": wilcox_p, "market": market, "params": tuned}


def main() -> None:
    p = argparse.ArgumentParser(description="Train H2H Approach B direct classifier (Epic 11.3)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--n-trials", type=int, default=_N_TRIALS, help="Optuna trials per candidate (default 30)")
    p.add_argument("--quick", action="store_true", help="Subsample + few trials (smoke test)")
    p.add_argument("--no-mlflow", action="store_true")
    args = p.parse_args()
    run(env=args.env, n_trials=args.n_trials, quick=args.quick, mlflow=not args.no_mlflow)


if __name__ == "__main__":
    main()
