"""
evaluate_layer3_signals.py — Epic 9, Story 9.2

Signal-level NLL evaluation: measure each sub-model signal group's INCREMENTAL
predictive value on the Layer 3 targets (total_runs, home_win) via walk-forward
CV, and assign each group a promote / reject / defer verdict. Consumes the 9.1
matrix (load_layer3_features) and adds groups incrementally in champion order
(run_env → offense → starter → starter_ip → bullpen → matchup): each group's
delta is measured on top of the already-promoted groups.

Per the Sub-model output standard, NLL is the primary gate (not just MAE):
adding a signal must reduce held-out NLL of a distributional baseline.

Modeling choices:
  - total_runs: conditional mean via a Poisson GLM (log link — numerically
    stable across the accreting feature sets), NB2 dispersion r fit separately
    by MLE on the train fold (mirrors train_run_env_v4). Held-out NLL and the
    80% PI use the full NegBin(mu, r). (Mean-estimator pragmatism for an
    ablation; the distributional metrics are still NegBin.)
  - home_win: logistic regression; Brier is the gate metric (per spec).

Calibration (robust hybrid, Epic 9.2 decision):
  (a) gate = incremental held-out NLL delta;
  (b) GLM-level 80% calibration delta reported for ALL groups (total_runs);
  (c) signal-own-PI uncertainty_calibration_score only for the in-matrix-
      observable groups (offense → side runs, run_env → total_runs);
  (d) latent / out-of-matrix groups report uncertainty_calibration_score=None
      with a reason citing that their (mu,sigma) calibration was gated at
      training in their source epic (3D/4D/5D/6D).

Outputs: ablation_results/layer3_signal_evaluation_{ts}.{json,md}; MLflow
experiment 'layer3_evaluation'. No Snowflake writes.

Usage (full run is >1 min — intended to be run by the user):
    uv run python betting_ml/scripts/evaluate_layer3_signals.py --env prod
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import gammaln
from scipy.stats import nbinom, wilcoxon

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    load_layer3_features, _SIGNAL_GROUPS, _ENV_GROUPS,
)
from betting_ml.utils.cv_splits import all_season_splits  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_MIN_MU = 1e-6

# Promotion gates (Sub-model output standard).
_GATE = {
    "total_runs": {"metric": "nll", "threshold": -0.005, "mae_regression_max": 0.005},
    "home_win":   {"metric": "brier", "threshold": -0.001, "mae_regression_max": None},
}
_CONSISTENCY_FRAC = 0.6          # improve in >= ceil(0.6 * n_folds) folds
_CALIB_FLAG_BELOW = 0.70         # uncertainty_calibration_score flagged if below
_COVERAGE_DEGRADE_EPS = 0.001    # delta on available rows must be <= this (not worse)

# Signals whose realized target is observable IN the Layer 3 matrix, so their own
# 80% PI can be calibration-checked here. The rest were gated at training time.
_OBSERVABLE_TARGETS = {
    "offense": ("side_runs", "pred_runs_dispersion_v2"),   # mu per side → that side's runs
    "run_env": ("total_runs", "run_env_dispersion_v4"),    # mu → total runs
}
_SOURCE_EPIC = {
    "starter": "5", "starter_ip": "5D", "bullpen": "6D", "matchup": "8",
}

_ABLATION_DIR = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
_MLFLOW_EXPERIMENT = "layer3_evaluation"


# --------------------------------------------------------------------------- #
# NB2 NegBin helpers (mirror betting_ml/scripts/train_run_env_v4.py)
# --------------------------------------------------------------------------- #
def _negbin_logpmf(y: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    y = np.round(y).clip(0).astype(int)
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
            + r * np.log(p + 1e-12) + y * np.log(1.0 - p + 1e-12))


def _negbin_nll(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    return float(-_negbin_logpmf(y, mu, r).mean())


def _fit_negbin_r(y: np.ndarray, mu: np.ndarray) -> float:
    def neg_loglik(log_r: float) -> float:
        return -_negbin_logpmf(y, mu, np.exp(log_r)).sum()
    res = minimize_scalar(neg_loglik, bounds=(np.log(0.1), np.log(500)), method="bounded")
    return float(np.exp(res.x))


def _negbin_80pct_calibration(y: np.ndarray, mu: np.ndarray, r: float) -> float:
    mu = np.clip(mu, _MIN_MU, None)
    p = r / (r + mu)
    lo = nbinom.ppf(0.10, n=r, p=p)
    hi = nbinom.ppf(0.90, n=r, p=p)
    return float(((y >= lo) & (y <= hi)).mean())


# --------------------------------------------------------------------------- #
# Column helpers (reuse the 9.1 group definitions)
# --------------------------------------------------------------------------- #
def _group_mu_cols(label: str, mu: str) -> list[str]:
    return [mu] if label in _ENV_GROUPS else [f"home_{mu}", f"away_{mu}"]


def _group_avail_mask(df: pd.DataFrame, label: str, avail: str) -> pd.Series:
    if label in _ENV_GROUPS:
        return df[avail].eq(True)
    return df[f"home_{avail}"].eq(True) & df[f"away_{avail}"].eq(True)


def _design(df: pd.DataFrame, idx: pd.Index, cols: list[str],
            train_means: pd.Series | None = None) -> tuple[np.ndarray, pd.Series]:
    """Design matrix with leading constant; mean-impute missing values (fit on train)."""
    ones = np.ones((len(idx), 1))
    if not cols:
        return ones, pd.Series(dtype=float)
    X = df.loc[idx, cols].apply(pd.to_numeric, errors="coerce")
    if train_means is None:
        train_means = X.mean()
    X = X.fillna(train_means)
    return np.column_stack([ones, X.values]), train_means


# --------------------------------------------------------------------------- #
# Per-fold fitting
# --------------------------------------------------------------------------- #
def _fit_poisson_mu(mat_tr: np.ndarray, y_tr: np.ndarray, mat_ev: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (mu_train, mu_eval) from a Poisson GLM (log link). Stable conditional mean."""
    import statsmodels.api as sm
    res = sm.GLM(y_tr, mat_tr, family=sm.families.Poisson()).fit()
    return np.clip(res.predict(mat_tr), _MIN_MU, None), np.clip(res.predict(mat_ev), _MIN_MU, None)


def _fit_logit_p(mat_tr: np.ndarray, y_tr: np.ndarray, mat_ev: np.ndarray) -> np.ndarray:
    """Return predicted P(home_win) on eval. Intercept-only → train base rate."""
    if mat_tr.shape[1] == 1:  # constant only
        return np.full(mat_ev.shape[0], float(np.mean(y_tr)))
    from sklearn.linear_model import LogisticRegression
    clf = LogisticRegression(max_iter=1000, fit_intercept=False)
    clf.fit(mat_tr, y_tr)
    return clf.predict_proba(mat_ev)[:, 1]


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# --------------------------------------------------------------------------- #
# Signal-own-PI calibration (observable targets only)
# --------------------------------------------------------------------------- #
def _uncertainty_calibration_score(df: pd.DataFrame, label: str, mu: str) -> dict:
    if label not in _OBSERVABLE_TARGETS:
        return {"score": None, "reason": f"latent/out-of-matrix target — (mu,sigma) "
                f"calibration gated at training in Epic {_SOURCE_EPIC.get(label, '?')}"}
    target_kind, disp_col = _OBSERVABLE_TARGETS[label]
    if label in _ENV_GROUPS:
        y = pd.to_numeric(df["total_runs"]).to_numpy()
        m = pd.to_numeric(df[mu]).to_numpy()
        r = pd.to_numeric(df[disp_col]).to_numpy()
    else:  # per-side: pool home (vs home runs) and away (vs away runs)
        y = pd.concat([pd.to_numeric(df["home_final_score"]),
                       pd.to_numeric(df["away_final_score"])]).to_numpy()
        m = pd.concat([pd.to_numeric(df[f"home_{mu}"]),
                       pd.to_numeric(df[f"away_{mu}"])]).to_numpy()
        r = pd.concat([pd.to_numeric(df[f"home_{disp_col}"]),
                       pd.to_numeric(df[f"away_{disp_col}"])]).to_numpy()
    ok = np.isfinite(y) & np.isfinite(m) & np.isfinite(r) & (r > 0)
    if ok.sum() == 0:
        return {"score": None, "reason": "no rows with mu/dispersion present"}
    # Per-row NegBin 80% PI coverage.
    mm = np.clip(m[ok], _MIN_MU, None)
    rr = r[ok]
    pp = rr / (rr + mm)
    lo = nbinom.ppf(0.10, n=rr, p=pp)
    hi = nbinom.ppf(0.90, n=rr, p=pp)
    score = float(((y[ok] >= lo) & (y[ok] <= hi)).mean())
    return {"score": round(score, 4), "n": int(ok.sum()),
            "miscalibrated": score < _CALIB_FLAG_BELOW}


# --------------------------------------------------------------------------- #
# Group evaluation
# --------------------------------------------------------------------------- #
def evaluate_signal_group(group: tuple, baseline_cols: list[str], df: pd.DataFrame,
                          target: str, min_train_seasons: int) -> dict:
    label, mu, spread, unc, avail, in_floor = group
    group_cols = _group_mu_cols(label, mu)
    is_negbin = target == "total_runs"
    y_all = pd.to_numeric(df[target]).to_numpy(dtype=float)
    avail_all = _group_avail_mask(df, label, avail).to_numpy()

    folds = list(all_season_splits(df, min_train_seasons=min_train_seasons))
    eval_years = sorted(df.loc[ev, "game_year"].iloc[0] if len(ev) else None
                        for _, ev in folds)

    per_fold, pooled = [], {"y": [], "base": [], "sig": [], "avail": []}
    for tr_idx, ev_idx in folds:
        y_tr, y_ev = y_all[df.index.get_indexer(tr_idx)], y_all[df.index.get_indexer(ev_idx)]

        Xb_tr, means_b = _design(df, tr_idx, baseline_cols)
        Xb_ev, _ = _design(df, ev_idx, baseline_cols, means_b)
        Xs_tr, means_s = _design(df, tr_idx, baseline_cols + group_cols)
        Xs_ev, _ = _design(df, ev_idx, baseline_cols + group_cols, means_s)

        if is_negbin:
            mu_b_tr, mu_b_ev = _fit_poisson_mu(Xb_tr, y_tr, Xb_ev)
            mu_s_tr, mu_s_ev = _fit_poisson_mu(Xs_tr, y_tr, Xs_ev)
            r_b, r_s = _fit_negbin_r(y_tr, mu_b_tr), _fit_negbin_r(y_tr, mu_s_tr)
            nll_b, nll_s = _negbin_nll(y_ev, mu_b_ev, r_b), _negbin_nll(y_ev, mu_s_ev, r_s)
            mae_b = float(np.mean(np.abs(y_ev - mu_b_ev)))
            mae_s = float(np.mean(np.abs(y_ev - mu_s_ev)))
            cal_b = _negbin_80pct_calibration(y_ev, mu_b_ev, r_b)
            cal_s = _negbin_80pct_calibration(y_ev, mu_s_ev, r_s)
            per_fold.append({"eval_year": int(df.loc[ev_idx, "game_year"].iloc[0]),
                             "nll_delta": nll_s - nll_b, "mae_delta": mae_s - mae_b,
                             "calib80_delta": cal_s - cal_b})
            pooled["y"].append(y_ev); pooled["base"].append(mu_b_ev); pooled["sig"].append(mu_s_ev)
            pooled["avail"].append(avail_all[df.index.get_indexer(ev_idx)])
            pooled["r_base"] = r_b; pooled["r_sig"] = r_s
        else:
            p_b = _fit_logit_p(Xb_tr, y_tr, Xb_ev)
            p_s = _fit_logit_p(Xs_tr, y_tr, Xs_ev)
            per_fold.append({"eval_year": int(df.loc[ev_idx, "game_year"].iloc[0]),
                             "brier_delta": _brier(p_s, y_ev) - _brier(p_b, y_ev),
                             "logloss_delta": _logloss(p_s, y_ev) - _logloss(p_b, y_ev)})

    gate = _GATE[target]
    metric_delta_key = "nll_delta" if is_negbin else "brier_delta"
    deltas = np.array([f[metric_delta_key] for f in per_fold])
    n_folds = len(deltas)
    win_count = int((deltas < 0).sum())
    needed = math.ceil(_CONSISTENCY_FRAC * n_folds)
    mean_delta = float(deltas.mean())
    try:
        _, wilcoxon_p = wilcoxon(deltas)
        wilcoxon_p = float(wilcoxon_p)
    except Exception:  # noqa: BLE001 — degenerate / too few folds
        wilcoxon_p = None

    mae_delta = float(np.mean([f["mae_delta"] for f in per_fold])) if is_negbin else None
    calib80_delta = float(np.mean([f["calib80_delta"] for f in per_fold])) if is_negbin else None

    # Coverage-conditional (total_runs only — pooled eval rows).
    coverage = {}
    if is_negbin and pooled["y"]:
        y = np.concatenate(pooled["y"]); mb = np.concatenate(pooled["base"])
        ms = np.concatenate(pooled["sig"]); av = np.concatenate(pooled["avail"])
        for sub, mask in (("available", av), ("unavailable", ~av)):
            if mask.sum() == 0:
                coverage[sub] = {"n": 0, "nll_delta": None}
                continue
            d = (_negbin_nll(y[mask], ms[mask], pooled["r_sig"])
                 - _negbin_nll(y[mask], mb[mask], pooled["r_base"]))
            coverage[sub] = {"n": int(mask.sum()), "nll_delta": round(d, 5)}

    # Verdict.
    met_gate = mean_delta <= gate["threshold"]
    met_consistency = win_count >= needed
    met_regression = (gate["mae_regression_max"] is None or
                      (mae_delta is not None and mae_delta <= gate["mae_regression_max"]))
    cov_av = coverage.get("available", {}).get("nll_delta")
    met_coverage = (cov_av is None) or (cov_av <= _COVERAGE_DEGRADE_EPS)
    if met_gate and met_consistency and met_regression and met_coverage:
        verdict = "promote"
    elif mean_delta < 0:
        verdict = "defer"
    else:
        verdict = "reject"

    return {
        "signal_group": label, "target": target, "n_folds": n_folds,
        "gate_metric": gate["metric"], "gate_threshold": gate["threshold"],
        "mean_delta": round(mean_delta, 6), "win_count": f"{win_count}/{n_folds}",
        "consistency_needed": needed, "wilcoxon_p": wilcoxon_p,
        "mae_delta": None if mae_delta is None else round(mae_delta, 6),
        "calib80_delta": None if calib80_delta is None else round(calib80_delta, 6),
        "coverage_conditional": coverage,
        "per_fold": [{k: (round(v, 6) if isinstance(v, float) else v) for k, v in f.items()}
                     for f in per_fold],
        "eval_years": [y for y in eval_years if y is not None],
        "signal_verdict": verdict,
    }


def run_evaluation(env: str = "prod", targets: tuple = ("total_runs", "home_win"),
                   min_train_seasons: int = 2, start_date: str = "2021-01-01") -> dict:
    df = load_layer3_features(start_date=start_date, env=env)
    log.info("Loaded Layer 3 matrix: %d games for evaluation", len(df))

    results: dict = {"meta": {"env": env, "start_date": start_date, "n_games": len(df),
                              "min_train_seasons": min_train_seasons,
                              "generated_at": datetime.now().isoformat(timespec="seconds")},
                     "targets": {}}

    for target in targets:
        baseline_cols: list[str] = []          # intercept-only start
        promoted: list[str] = []
        target_results = []
        for group in _SIGNAL_GROUPS:
            label, mu, *_ = group
            res = evaluate_signal_group(group, baseline_cols, df, target, min_train_seasons)
            res["uncertainty_calibration"] = _uncertainty_calibration_score(df, label, mu)
            target_results.append(res)
            # Accrete onto the baseline so the next group is incremental.
            if res["signal_verdict"] == "promote":
                cols = _group_mu_cols(label, mu)
                baseline_cols += cols
                promoted.append(label)
            log.info("[%s] %-11s → %-8s (Δ%s=%+.4f, %s folds, calib=%s)",
                     target, label, res["signal_verdict"], res["gate_metric"],
                     res["mean_delta"], res["win_count"],
                     res["uncertainty_calibration"]["score"])
        results["targets"][target] = {"promoted_order": promoted, "groups": target_results}

    return results


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def _write_outputs(results: dict) -> tuple[Path, Path]:
    _ABLATION_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = _ABLATION_DIR / f"layer3_signal_evaluation_{ts}.json"
    md_path = _ABLATION_DIR / f"layer3_signal_evaluation_{ts}.md"
    json_path.write_text(json.dumps(results, indent=2, default=str))

    m = results["meta"]
    lines = [
        "# Layer 3 Signal Evaluation (Story 9.2)", "",
        f"- env={m['env']} · games={m['n_games']} · min_train_seasons={m['min_train_seasons']} · {m['generated_at']}",
        "- Incremental walk-forward CV; gate = held-out NLL delta (Brier for home_win).",
        "",
    ]
    for target, blk in results["targets"].items():
        lines += [f"## Target: `{target}`  (promoted in order: {', '.join(blk['promoted_order']) or 'none'})",
                  "", "| group | verdict | Δmetric | folds won | MAEΔ | calib80Δ | self-PI cal |",
                  "|---|---|---|---|---|---|---|"]
        for r in blk["groups"]:
            cal = r["uncertainty_calibration"]["score"]
            cal_s = "n/a" if cal is None else (f"{cal}⚠️" if r["uncertainty_calibration"].get("miscalibrated") else f"{cal}")
            lines.append(f"| {r['signal_group']} | **{r['signal_verdict']}** | {r['mean_delta']:+} "
                         f"| {r['win_count']} | {r['mae_delta']} | {r['calib80_delta']} | {cal_s} |")
        lines.append("")
    md_path.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s and %s", json_path.name, md_path.name)
    return json_path, md_path


def _log_mlflow(results: dict) -> None:
    import mlflow
    from betting_ml.utils.mlflow_utils import get_or_create_experiment
    exp_id = get_or_create_experiment(_MLFLOW_EXPERIMENT)
    with mlflow.start_run(experiment_id=exp_id, run_name="layer3_signal_eval"):
        mlflow.log_params({k: results["meta"][k] for k in ("env", "start_date", "n_games", "min_train_seasons")})
        for target, blk in results["targets"].items():
            for r in blk["groups"]:
                g = r["signal_group"]
                mlflow.log_metric(f"{target}__{g}__mean_delta", r["mean_delta"])
                if r["calib80_delta"] is not None:
                    mlflow.log_metric(f"{target}__{g}__calib80_delta", r["calib80_delta"])
                cal = r["uncertainty_calibration"]["score"]
                if cal is not None:
                    mlflow.log_metric(f"{g}__self_pi_calibration", cal)
                mlflow.set_tag(f"{target}__{g}__verdict", r["signal_verdict"])
    log.info("Logged MLflow run under '%s'", _MLFLOW_EXPERIMENT)


def main() -> None:
    parser = argparse.ArgumentParser(description="Layer 3 signal-level NLL evaluation (Epic 9.2)")
    parser.add_argument("--env", choices=["prod", "dev"], default="prod")
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--targets", default="total_runs,home_win",
                        help="comma-separated subset of: total_runs,home_win")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    targets = tuple(t.strip() for t in args.targets.split(",") if t.strip())
    results = run_evaluation(env=args.env, targets=targets,
                             min_train_seasons=args.min_train_seasons, start_date=args.start_date)
    _write_outputs(results)
    if not args.no_mlflow:
        try:
            _log_mlflow(results)
        except Exception as exc:  # noqa: BLE001 — MLflow non-blocking
            log.warning("MLflow logging skipped: %s", exc)

    # AC summary: run_env + offense must promote on total_runs.
    tr = {r["signal_group"]: r["signal_verdict"] for r in results["targets"].get("total_runs", {}).get("groups", [])}
    foundational = {g: tr.get(g) for g in ("run_env", "offense")}
    log.info("Foundational verdicts (total_runs): %s", foundational)
    if any(v != "promote" for v in foundational.values()):
        log.warning("AC ALERT: run_env/offense did not both promote on total_runs — investigate before Epic 10.")


if __name__ == "__main__":
    main()
