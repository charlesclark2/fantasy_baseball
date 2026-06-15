"""Run the codified promotion gate (Case 3) on champion vs challenger, per target.

For each base target it evaluates the CURRENT production champion recipe against the
freshly-retrained 30.4 CHALLENGER through `betting_ml.utils.promotion_gate`. The
comparison is **walk-forward** (both recipes retrained per season-forward fold) — NOT
fixed-artifact scoring — because the deployed champion and the challenger are BOTH
trained through 2025, so 2026 is their only shared OOS season; only per-fold retraining
yields genuine held-out 2024 + 2025 seasons for the gate's cross-season criterion.

Per game it collects the accuracy-to-truth score (lower = better):
  - home_win        : Brier vs the 0/1 winner
  - run_diff/total  : absolute error vs actual (→ MAE), the policy's point-accuracy metric
then calls evaluate_promotion(completed_seasons={2024,2025}, current_season=2026).

CHAMPION recipe (current production):
  - home_win / run_diff : the pre-30.4 contract (retained − the ORIGINAL 33 market cols
    − identifiers; i.e. WITH the 9 market leaks + dead weight that 30.4 removes) +
    the deployed tuned hyperparameters.
  - total_runs          : the eb_enriched champion contract (feature_columns_eb_2026.json,
    369 feats) + NGBoost Normal n=500 — the actual S3 totals source.
CHALLENGER recipe (30.4 retrain): the new cleaned contract (feature_columns_*_tuned_2026.json,
  209/167/111) + the retuned hyperparameters persisted in tuning_results_*.json.

Runtime: retrains 2 recipes × 3 folds × 3 targets — minutes. Hand off to run with
Snowflake creds. Writes nothing to prod / daily_model_predictions.

Usage:
    uv run python betting_ml/scripts/promotion_gate_eval.py --target all
    uv run python betting_ml/scripts/promotion_gate_eval.py --target home_win
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.ablation_identifier_features import _TARGETS as _CHAMP_HP, _impute
from betting_ml.scripts.train_elasticnet_prod import _MARKET_COLS_TO_EXCLUDE
from betting_ml.utils.cv_splits import all_season_splits
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_hygiene import is_identifier_name
from betting_ml.utils.feature_selection import load_retained_features
from betting_ml.utils.promotion_gate import (
    PredictiveOutput, calibration_report, evaluate_promotion,
)

# The 9 market cols Story 30.4 ADDED — subtract them to reconstruct the pre-30.4
# champion's market exclude set (so the champion arm still carries the 9 leaks).
_MARKET_LEAK_30_4 = {
    "over_prob_consensus", "under_implied_prob", "total_line_movement",
    "home_ml_money_pct", "over_ticket_pct", "market_bookmaker_count",
    "over_american", "under_american", "total_line_std",
}
_OLD_MARKET_EXCLUDE = set(_MARKET_COLS_TO_EXCLUDE) - _MARKET_LEAK_30_4

# Story 27.7 — season-normalization is now PRODUCTIONIZED in dbt (the leakage-safe AS-OF
# league baseline in feature_league_contact_baseline → `<col>_seasonnorm` columns). The
# `--season-normalize` flag therefore points the totals challenger at the contract trained on
# those `_seasonnorm` columns (see _run_calibration), instead of the old offline in-pandas
# within-season z-score (which was leaky — it used each season's full mean — and only valid to
# prove the mechanism; see betting_ml/scripts/regime/totals_season_norm_fix.py for that history).
# The canonical contact-column list lives in betting_ml/utils/season_normalization.py.

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "promotion_gate"

_TARGETS = {
    "home_win": {
        "kind": "classification", "target_col": "home_win", "metric": "brier",
        "challenger_contract": "betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json",
        # Story 27.8: --season-normalize points the challenger at the contract trained on the
        # dbt `_seasonnorm` contact columns. Champion stays the deployed raw v5 (deployed-vs-normalized).
        "challenger_contract_seasonnorm":
            "betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_seasonnorm_2026.json",
        "challenger_tuning": "betting_ml/evaluation/tuning_results_xgb_home_win.json",
        "champion_kind": "reconstruct",   # pre-30.4 contract
    },
    "run_diff": {
        "kind": "regression", "target_col": "run_differential", "metric": "mae",
        "challenger_contract": "betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json",
        "challenger_contract_seasonnorm":
            "betting_ml/models/run_differential/feature_columns_ngboost_tuned_seasonnorm_2026.json",
        "challenger_tuning": "betting_ml/evaluation/tuning_results_ngboost_run_diff.json",
        "champion_kind": "reconstruct",
    },
    "total_runs": {
        "kind": "regression", "target_col": "total_runs", "metric": "mae",
        "challenger_contract": "betting_ml/models/total_runs/feature_columns_ngboost_tuned_2026.json",
        # Story 27.7: --season-normalize swaps the challenger to the contract trained on the
        # dbt `_seasonnorm` contact columns (written by run_ngboost_total_runs_search.py
        # --season-normalize). Champion stays the deployed raw lineage → deployed-vs-normalized.
        "challenger_contract_seasonnorm":
            "betting_ml/models/total_runs/feature_columns_ngboost_tuned_seasonnorm_2026.json",
        "challenger_tuning": "betting_ml/evaluation/tuning_results_ngboost_total_runs.json",
        # totals champion is the eb_enriched lineage (S3 source), NOT a reconstruct.
        "champion_kind": "contract",
        "champion_contract": "betting_ml/models/total_runs/feature_columns_eb_2026.json",
        "champion_ngb": {"n_estimators": 500, "dist": "Normal"},
    },
}


def _contract_cols(path: str, df: pd.DataFrame) -> list[str]:
    # Contracts come in two shapes: the tuned sidecars are {"feature_cols": [...]},
    # the older eb_2026 contract is a bare list of column names.
    raw = json.loads((PROJECT_ROOT / path).read_text())
    cols = raw["feature_cols"] if isinstance(raw, dict) else raw
    return [c for c in cols if c in df.columns]  # indicators re-added at impute


def _reconstruct_champion_cols(df: pd.DataFrame) -> list[str]:
    """Pre-30.4 production base contract: retained − ORIGINAL market − identifiers
    (so the 9 market leaks + dead weight 30.4 removes are STILL present)."""
    retained = load_retained_features()
    cols = [c for c in retained if c in df.columns and c not in _OLD_MARKET_EXCLUDE]
    return [c for c in cols if not is_identifier_name(c)]


def _challenger_ngb(tuning_path: str) -> dict:
    t = json.loads((PROJECT_ROOT / tuning_path).read_text())
    # NGBoost search schema: top-level best_n_estimators + best_dist.
    bp = t.get("best_params") or {}
    n_est = int(t.get("best_n_estimators", bp.get("n_estimators", 500)))
    dist = t.get("best_dist") or bp.get("dist") or "Normal"
    return {"n_estimators": n_est, "dist": dist}


def _challenger_xgb(tuning_path: str) -> dict:
    t = json.loads((PROJECT_ROOT / tuning_path).read_text())
    bp = dict(t.get("best_params") or {})
    bp.setdefault("eval_metric", "logloss")
    bp.setdefault("tree_method", "hist")
    bp.setdefault("random_state", 42)
    bp.setdefault("n_jobs", -1)
    return bp


# ── Model adapters — ANY architecture plugs in by returning a PredictiveOutput ──
# A ModelSpec is anything with `name` + `fit_predict(Xtr, ytr, Xev, yev) ->
# PredictiveOutput`. Add a new model type = add an adapter; the walk-forward driver and
# the gate are untouched. For models trained/served OUTSIDE this harness (PyMC run
# elsewhere, an external service, a non-Python model), skip adapters entirely and feed
# per-game scores straight to promotion_gate.evaluate_promotion (the universal escape hatch).

@runtime_checkable
class ModelSpec(Protocol):
    name: str
    def fit_predict(self, Xtr, ytr, Xev, yev) -> PredictiveOutput: ...


@dataclass
class XGBPlattSpec:
    """XGBoost + Platt calibration on the eval split (the home_win production recipe)."""
    params: dict
    name: str = "xgb_platt"

    def fit_predict(self, Xtr, ytr, Xev, yev) -> PredictiveOutput:
        from sklearn.linear_model import LogisticRegression
        from xgboost import XGBClassifier
        clf = XGBClassifier(**self.params)
        clf.fit(Xtr, ytr.astype(int))
        raw = clf.predict_proba(Xev)[:, 1]
        cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
        cal.fit(raw.reshape(-1, 1), yev.astype(int))
        return PredictiveOutput.binary(cal.predict_proba(raw.reshape(-1, 1))[:, 1])


@dataclass
class NGBoostSpec:
    """NGBoost Normal/LogNormal — returns the full predictive (loc/scale) so crps/nll
    work, falling back to a point output if dist-param extraction ever changes."""
    n_estimators: int = 500
    dist: str = "Normal"
    name: str = "ngboost"
    seed: int = 42

    def fit_predict(self, Xtr, ytr, Xev, yev) -> PredictiveOutput:
        from ngboost import NGBRegressor
        from ngboost.distns import LogNormal, Normal
        D = {"Normal": Normal, "LogNormal": LogNormal}[self.dist]
        m = NGBRegressor(n_estimators=self.n_estimators, Dist=D, verbose=False,
                         random_state=self.seed)
        m.fit(Xtr.values, ytr)
        pred = np.asarray(m.predict(Xev.values), float)
        try:
            p = m.pred_dist(Xev.values).params
            if self.dist == "Normal":
                return PredictiveOutput.normal(p["loc"], p["scale"])
            return PredictiveOutput.lognormal(np.log(np.asarray(p["scale"], float)), p["s"])
        except Exception:
            return PredictiveOutput.point(pred)


@dataclass
class SklearnPointSpec:
    """Any sklearn-style regressor: factory() -> estimator with fit/predict."""
    factory: object
    name: str = "sklearn_point"

    def fit_predict(self, Xtr, ytr, Xev, yev) -> PredictiveOutput:
        est = self.factory()
        est.fit(Xtr, ytr)
        return PredictiveOutput.point(np.asarray(est.predict(Xev), float))


@dataclass
class SamplesSpec:
    """Bayesian / sampling models (PyMC posterior predictive, bootstrap ensembles, …).
    `sampler(Xtr, ytr, Xev) -> ndarray (n_eval_games, n_draws)`; scored distribution-free
    via CRPS so a posterior is comparable to a point/parametric champion."""
    sampler: object
    name: str = "samples"

    def fit_predict(self, Xtr, ytr, Xev, yev) -> PredictiveOutput:
        return PredictiveOutput.from_samples(self.sampler(Xtr, ytr, Xev))


def walk_forward_gate(df, target_col, *, champion: ModelSpec, challenger: ModelSpec,
                      champion_cols, challenger_cols, metric,
                      completed_seasons=None, current_season=None, **gate_kwargs):
    """Generic, model-agnostic champion-vs-challenger gate. Retrains BOTH specs per
    season-forward fold, scores each per game via PredictiveOutput.score_to_truth(metric),
    and runs evaluate_promotion. Works for ANY pair of ModelSpec adapters."""
    seasons, champ_scores, chal_scores = [], [], []
    warned_kind = False
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[eval_idx, "game_year"].mode()[0])
        ytr_c = df.loc[train_idx, target_col].values
        yev = df.loc[eval_idx, target_col].values
        Xtr_c, Xev_c = _impute(df.loc[train_idx, champion_cols], df.loc[eval_idx, champion_cols])
        Xtr_h, Xev_h = _impute(df.loc[train_idx, challenger_cols], df.loc[eval_idx, challenger_cols])
        co = champion.fit_predict(Xtr_c, ytr_c, Xev_c, yev)
        ho = challenger.fit_predict(Xtr_h, ytr_c, Xev_h, yev)
        # Soundness guard: a distributional metric (crps/nll) across MISMATCHED output
        # kinds credits distribution quality, not just point accuracy — CRPS of a point
        # prediction = |error| ≥ the CRPS of a calibrated distribution at the same mean,
        # so a distributional challenger can "win" on crps purely for HAVING a distribution.
        # For a point-accuracy comparison (the totals-product policy), use metric='mae'.
        if not warned_kind and metric in ("crps", "nll") and co.kind != ho.kind:
            print(f"    ⚠ MIXED OUTPUT KINDS (champion={co.kind}, challenger={ho.kind}) on "
                  f"'{metric}': this credits DISTRIBUTION quality, not just point accuracy. "
                  f"Use metric='mae' for a pure point-accuracy verdict.")
            warned_kind = True
        cs = co.score_to_truth(yev, metric)
        hs = ho.score_to_truth(yev, metric)
        seasons.append(np.full(len(cs), yr)); champ_scores.append(cs); chal_scores.append(hs)
        print(f"    fold {yr}: champ {metric}={cs.mean():.4f}  challenger={hs.mean():.4f}  (n={len(cs)})")
    season = np.concatenate(seasons)
    if current_season is None:
        current_season = int(season.max())
    if completed_seasons is None:
        completed_seasons = {int(s) for s in np.unique(season) if int(s) != current_season}
    return evaluate_promotion(season, np.concatenate(champ_scores), np.concatenate(chal_scores),
                              metric=metric, completed_seasons=completed_seasons,
                              current_season=current_season, **gate_kwargs)


_TOTALS_LINE_COL = "total_line_consensus"   # market line for the directional pct_over check

# Calibration thresholds. coverage_80 + NLL are HARD spread-calibration gates (regime-robust —
# they judge distribution SHAPE/uncertainty, not level). _BIAS_MAX + _PCT_OVER_GAP_MAX are
# DIAGNOSTIC-ONLY as of 2026-06-12 (operator decision): the totals center-bias WAS run-environment
# REGIME LAG, not a model flaw (Normal refit did NOT fix it — disproved the LogNormal hypothesis),
# and the gate could not yet separate regime lag from real bias. Story 27.7 yielded the regime-
# ADJUSTED bias (the season-normalized contact features), so under --season-normalize these two
# become HARD gates again (see _run_calibration; center_hard); without it they stay DIAGNOSTIC-ONLY.
_COVERAGE_BAND = (0.75, 0.85)   # [HARD] central-80% PI empirical coverage must land here
_NLL_TOL = 0.02                 # [HARD] challenger NLL may not exceed champion NLL by more than this
_BIAS_MAX = 0.25                # |mean(pred) − mean(actual)| ceiling (runs) — HARD under --season-normalize
_PCT_OVER_GAP_MAX = 0.10        # |model_pct_over − actual_pct_over| ceiling — HARD under --season-normalize


def _pooled_output(outs: list[PredictiveOutput]) -> PredictiveOutput:
    """Concatenate per-fold predictive outputs (same kind) into one for pooled scoring."""
    kind = outs[0].kind
    mean = np.concatenate([o.mean for o in outs])
    if kind == "normal":
        return PredictiveOutput.normal(np.concatenate([o.loc for o in outs]),
                                       np.concatenate([o.scale for o in outs]))
    if kind == "lognormal":
        return PredictiveOutput.lognormal(np.concatenate([o.loc for o in outs]),
                                          np.concatenate([o.scale for o in outs]))
    if kind == "samples":
        return PredictiveOutput.from_samples(np.concatenate([o.samples for o in outs], axis=0))
    return PredictiveOutput.point(mean)


def _pct_over(out: PredictiveOutput, y, line) -> dict:
    """Directional check vs the market line: does the model lean over/under like reality?

    Uses the model's DISTRIBUTIONAL P(Y > line), NOT mean>line. Run totals are right-skewed, so
    mean>line over-counts overs for ANY unbiased mean predictor (the mean sits above the median-ish
    line) — that made even a calibrated champion 'fail'. The predictive P(over) is the honest
    comparison: a calibrated model's mean P(over) ≈ the actual over-rate.
    """
    line = np.asarray(line, float)
    y = np.asarray(y, float)
    ok = ~np.isnan(line)
    if ok.sum() == 0:
        return {"n_lined": 0}
    if out.kind in ("normal", "lognormal"):
        from scipy.stats import norm
        arg = (np.log(np.maximum(line, 1e-9)) if out.kind == "lognormal" else line)
        p_over = 1.0 - norm.cdf((arg - out.loc) / out.scale)
    elif out.kind == "samples":
        p_over = (out.samples > line[:, None]).mean(axis=1)
    else:  # point/binary — no distribution, fall back to the (skew-contaminated) indicator
        p_over = (out.mean > line).astype(float)
    return {
        "n_lined": int(ok.sum()),
        "model_pct_over": float(np.mean(p_over[ok])),
        "actual_pct_over": float(np.mean(y[ok] > line[ok])),
    }


def walk_forward_calibration(df, target_col, *, champion: ModelSpec, challenger: ModelSpec,
                             champion_cols, challenger_cols, line_col: str | None = None):
    """Same walk-forward folds as the gate, but collect DISTRIBUTION-calibration
    diagnostics (coverage_80 / PIT-KS / NLL / CRPS / directional bias) for champion vs
    challenger — the evidence a distributional challenger needs before it can be a
    projection source. Returns {'per_season': [...], 'pooled': {...}}."""
    champ_outs, chal_outs, ys, lines, per_season = [], [], [], [], []
    for train_idx, eval_idx in all_season_splits(df, min_train_seasons=3):
        yr = int(df.loc[eval_idx, "game_year"].mode()[0])
        ytr = df.loc[train_idx, target_col].values
        yev = df.loc[eval_idx, target_col].values
        Xtr_c, Xev_c = _impute(df.loc[train_idx, champion_cols], df.loc[eval_idx, champion_cols])
        Xtr_h, Xev_h = _impute(df.loc[train_idx, challenger_cols], df.loc[eval_idx, challenger_cols])
        co = champion.fit_predict(Xtr_c, ytr, Xev_c, yev)
        ho = challenger.fit_predict(Xtr_h, ytr, Xev_h, yev)
        rc, rh = calibration_report(yev, co), calibration_report(yev, ho)
        per_season.append({"season": yr, "champion": rc, "challenger": rh})
        print(f"    fold {yr} (n={len(yev)}):  "
              f"cov80 champ={rc['coverage']:.3f}/chal={rh['coverage']:.3f}  "
              f"NLL champ={rc['nll_mean']:.4f}/chal={rh['nll_mean']:.4f}  "
              f"CRPS champ={rc['crps_mean']:.4f}/chal={rh['crps_mean']:.4f}  "
              f"bias champ={rc['bias']:+.3f}/chal={rh['bias']:+.3f}")
        champ_outs.append(co); chal_outs.append(ho); ys.append(yev)
        if line_col and line_col in df.columns:
            lines.append(df.loc[eval_idx, line_col].values)
    y_all = np.concatenate(ys)
    champ_pool, chal_pool = _pooled_output(champ_outs), _pooled_output(chal_outs)
    pooled = {"champion": calibration_report(y_all, champ_pool),
              "challenger": calibration_report(y_all, chal_pool)}
    if lines:
        line_all = np.concatenate(lines)
        pooled["champion"]["pct_over"] = _pct_over(champ_pool, y_all, line_all)
        pooled["challenger"]["pct_over"] = _pct_over(chal_pool, y_all, line_all)
    return {"per_season": per_season, "pooled": pooled}


def _run_calibration(name: str, df: pd.DataFrame, season_normalize: bool = False) -> dict:
    """Distribution-calibration comparison (champion vs challenger) for a regression target.
    The verdict the totals projection promotion needs: is the challenger's PREDICTED SPREAD
    honest, not just its point MAE? With season_normalize=True (Story 27.7), the challenger is
    the contract trained on the dbt `_seasonnorm` contact columns (leakage-safe, AS-OF league
    baseline) — the champion stays the deployed raw lineage, so this is a deployed-vs-normalized
    comparison."""
    cfg = _TARGETS[name]
    if cfg["kind"] != "regression":
        raise SystemExit(f"--eval-calibration is for distributional regression targets; {name} is {cfg['kind']}.")
    chal_contract = cfg["challenger_contract"]
    if season_normalize:
        chal_contract = cfg.get("challenger_contract_seasonnorm", chal_contract)
        print(f"  [Story 27.7] challenger = season-normalized contract: {chal_contract}")
    chal_cols = _contract_cols(chal_contract, df)
    champ_cols = (_reconstruct_champion_cols(df) if cfg["champion_kind"] == "reconstruct"
                  else _contract_cols(cfg["champion_contract"], df))
    champion, challenger = _build_specs(name, cfg)

    print(f"\n=== {name} CALIBRATION (champion {champion.name} vs challenger {challenger.name}) ===")
    print(f"  champion:   {len(champ_cols):3d} feats   challenger: {len(chal_cols):3d} feats")
    res = walk_forward_calibration(
        df, cfg["target_col"], champion=champion, challenger=challenger,
        champion_cols=champ_cols, challenger_cols=chal_cols,
        line_col=_TOTALS_LINE_COL if name == "total_runs" else None)

    pc, ph = res["pooled"]["champion"], res["pooled"]["challenger"]
    print(f"\n  POOLED (all eval games, n={pc['n']}):")
    print(f"    {'metric':<22}{'champion':>12}{'challenger':>12}   {'read':<40}")
    def _row(label, c, h, fmt="{:.4f}", note=""):
        print(f"    {label:<22}{fmt.format(c):>12}{fmt.format(h):>12}   {note}")
    _row("coverage_80", pc["coverage"], ph["coverage"], note="target 0.80; in [0.75,0.85] = calibrated")
    _row("coverage_gap", pc["coverage_gap"], ph["coverage_gap"], "{:+.4f}", "neg ⇒ overconfident (PI too tight)")
    _row("pit_ks", pc["pit_ks"], ph["pit_ks"], note="lower = closer to Uniform (better)")
    _row("nll_mean", pc["nll_mean"], ph["nll_mean"], note="proper; lower better")
    _row("crps_mean", pc["crps_mean"], ph["crps_mean"], note="proper; lower better")
    _row("bias (pred-actual)", pc["bias"], ph["bias"], "{:+.4f}", "≈0 = unbiased mean")
    print(f"    PIT hist champ : {pc['pit_hist']}")
    print(f"    PIT hist chal  : {ph['pit_hist']}   (flat≈calibrated; U=overconfident; dome=underconfident)")
    pct_over_gap = None
    if "pct_over" in ph and ph["pct_over"].get("n_lined"):
        poh = ph["pct_over"]
        poc = pc.get("pct_over", {})
        pct_over_gap = abs(poh["model_pct_over"] - poh["actual_pct_over"])
        if poc.get("n_lined"):
            print(f"    pct_over champ : model={poc['model_pct_over']:.3f} vs actual={poc['actual_pct_over']:.3f}")
        print(f"    pct_over chal  : model={poh['model_pct_over']:.3f} vs actual={poh['actual_pct_over']:.3f} "
              f"(gap={pct_over_gap:.3f}; n_lined={poh['n_lined']}; gap>{_PCT_OVER_GAP_MAX} ⇒ directional bias)")

    # ── Verdict ──────────────────────────────────────────────────────────────
    # HARD GATES — spread calibration only (coverage_80 + NLL non-regress). These ask "is my
    # UNCERTAINTY honest?" and are regime-ROBUST (distribution SHAPE, not level), so they fairly
    # gate a projection source.
    #
    # DIAGNOSTIC ONLY — bias + pct_over (the CENTER / directional checks). Operator decision
    # 2026-06-12: these are NOT gating until the run-environment regime is understood (Story 27.6).
    # The totals over-bias is REGIME LAG, not a model flaw — a model trained on past seasons lags a
    # within-season run-environment shift by ~a season (the 2025 fold drives the pooled bias; 2026
    # ≈ neutral), and market-blind totals lose the market line, the only LIVE regime anchor. A hard
    # pooled-bias gate would reject good market-blind models for a historical regime miss the gate
    # cannot yet separate from real bias. Reported per-season + pooled so a human reads them; once
    # 27.6 gives a regime-ADJUSTED bias, re-promote this to a hard gate. (pct_over is also skew-
    # contaminated — a mean predictor naturally exceeds a median-ish line >50% on right-skewed
    # totals; even the champion "fails" the raw gap. Prefer distributional P(over) when regularized.)
    calibrated = (_COVERAGE_BAND[0] <= ph["coverage"] <= _COVERAGE_BAND[1])
    no_nll_regress = ph["nll_mean"] <= pc["nll_mean"] + _NLL_TOL
    bias_ok = abs(ph["bias"]) <= _BIAS_MAX
    pct_over_ok = (pct_over_gap is None) or (pct_over_gap <= _PCT_OVER_GAP_MAX)
    # Story 27.7: with --season-normalize the contact features are REGIME-ADJUSTED (the
    # leakage-safe AS-OF league baseline), so the center-bias is no longer regime-confounded —
    # bias + pct_over become HARD gates again (as the operator deferred them to be, 2026-06-12).
    # Without --season-normalize they stay DIAGNOSTIC-ONLY (the prior behavior).
    center_hard = bool(season_normalize)
    ok = bool(calibrated and no_nll_regress and (not center_hard or (bias_ok and pct_over_ok)))
    tier = "HARD" if center_hard else "DIAG"
    if ok:
        verdict = (f"CALIBRATION OK — coverage_80 + NLL pass"
                   + (f"; bias + pct_over pass as HARD gates (regime-adjusted, Story 27.7)."
                      if center_hard else
                      " (spread). ⚠ DIRECTIONAL bias/pct_over DIAGNOSTIC-ONLY (regime-confounded; "
                      "Story 27.6) — read the per-season bias table before using as a projection source."))
    else:
        problems = [None if calibrated else "coverage_80 outside [0.75,0.85]",
                    None if no_nll_regress else "NLL regresses vs champion",
                    None if (not center_hard or bias_ok) else f"|bias|>{_BIAS_MAX}",
                    None if (not center_hard or pct_over_ok) else f"pct_over_gap>{_PCT_OVER_GAP_MAX}"]
        verdict = ("CALIBRATION CONCERN — " + "; ".join(p for p in problems if p)
                   + (" — regime-adjusted, so center bias now gates (Story 27.7)." if center_hard
                      else " — spread calibration itself is off, not just the center."))
    print(f"\n  → {verdict}")
    print(f"     [HARD]  coverage_80∈[0.75,0.85]={calibrated}  NLL_non_regress={no_nll_regress}")
    print(f"     [{tier}]  |bias|≤{_BIAS_MAX}={bias_ok} (|bias|={abs(ph['bias']):.3f})  "
          f"pct_over_gap≤{_PCT_OVER_GAP_MAX}={pct_over_ok}"
          + (f" (gap={pct_over_gap:.3f})" if pct_over_gap is not None else "")
          + ("  — HARD (regime-adjusted, 27.7)" if center_hard else "  — NOT gating until regime understood (27.6)"))
    return {"target": name, "pooled": res["pooled"], "per_season": res["per_season"],
            "calibration_ok": ok, "verdict": verdict,
            "hard_gates": {"calibrated": calibrated, "no_nll_regress": no_nll_regress},
            "diagnostics": {"bias_ok": bias_ok, "pct_over_ok": pct_over_ok,
                            "note": "regime-confounded; not gating until Story 27.6"}}


def _build_specs(name: str, cfg: dict, seed: int = 42) -> tuple[ModelSpec, ModelSpec]:
    """Champion + challenger adapters for a base target. Swapping a target to a new
    architecture (e.g. a Bayesian challenger) is just a different spec here.

    `seed` perturbs the MODEL-FIT randomness (XGB tree/column subsampling, NGBoost RNG) so a
    hysteresis re-run is a genuinely INDEPENDENT evaluation, not a byte-identical re-run — the
    bootstrap CI (a separate seed in evaluate_promotion) only captures eval-sample variance."""
    if cfg["kind"] == "classification":
        champion = XGBPlattSpec(dict(_CHAMP_HP[name]["xgb_params"], random_state=seed),
                                name="xgb_platt(champion)")
        challenger = XGBPlattSpec(dict(_challenger_xgb(cfg["challenger_tuning"]), random_state=seed),
                                  name="xgb_platt(challenger)")
    else:
        cn = cfg.get("champion_ngb", {"n_estimators": 500, "dist": "Normal"})
        hn = _challenger_ngb(cfg["challenger_tuning"])
        champion = NGBoostSpec(cn["n_estimators"], cn["dist"], name=f"ngboost-{cn['dist']}(champion)", seed=seed)
        challenger = NGBoostSpec(hn["n_estimators"], hn["dist"], name=f"ngboost-{hn['dist']}(challenger)", seed=seed)
    return champion, challenger


def _run_target(name: str, df: pd.DataFrame, correctness_override: str | None = None,
                season_normalize: bool = False, seed: int = 42) -> dict:
    cfg = _TARGETS[name]
    chal_contract = cfg["challenger_contract"]
    if season_normalize:
        # Story 27.8: challenger = the season-normalized retrain; champion stays deployed raw v5.
        chal_contract = cfg.get("challenger_contract_seasonnorm", chal_contract)
        print(f"  [Story 27.8] {name} challenger = season-normalized contract: {chal_contract}")
    chal_cols = _contract_cols(chal_contract, df)
    if season_normalize:
        # Story 27.8: ISOLATE the seasonnorm swap. Champion = the DEPLOYED model's contract
        # (`challenger_contract` == the v5 raw contract: identical feature set, RAW contact cols),
        # NOT the pre-30.4 reconstruct — otherwise the gate re-measures the already-shipped 30.4
        # hygiene gain instead of the contact-normalization effect (the 27.8 question).
        champ_cols = _contract_cols(cfg["challenger_contract"], df)
        print(f"  [Story 27.8] {name} champion = deployed v5 RAW contract "
              f"({len(champ_cols)} feats) — isolates seasonnorm-vs-raw, not the 30.4 gain")
    else:
        champ_cols = (_reconstruct_champion_cols(df) if cfg["champion_kind"] == "reconstruct"
                      else _contract_cols(cfg["champion_contract"], df))
    champion, challenger = _build_specs(name, cfg, seed=seed)
    if seed != 42:
        print(f"  [hysteresis] seed={seed} (independent re-fit; 42 is the default pass)")

    print(f"\n=== {name} ({cfg['kind']}, metric={cfg['metric']}) ===")
    print(f"  champion:   {len(champ_cols):3d} feats, {champion.name}")
    print(f"  challenger: {len(chal_cols):3d} feats, {challenger.name}")
    if correctness_override:
        print(f"  correctness override requested: {correctness_override}")

    verdict = walk_forward_gate(
        df, cfg["target_col"], champion=champion, challenger=challenger,
        champion_cols=champ_cols, challenger_cols=chal_cols, metric=cfg["metric"],
        correctness_override=correctness_override, seed=seed)
    print(verdict)
    return {
        "target": name, "metric": cfg["metric"],
        "champion_recipe": champion.name, "challenger_recipe": challenger.name,
        "n_features": {"champion": len(champ_cols), "challenger": len(chal_cols)},
        "decision": verdict.decision, "override_applied": verdict.override_applied,
        "correctness_override": correctness_override,
        "overall_delta": verdict.overall_delta, "boot_ci": list(verdict.boot_ci),
        "per_season": [vars(s) for s in verdict.per_season],
        "reasons": verdict.reasons,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    ap.add_argument("--correctness-override", default=None,
                    help="Record a correctness override (e.g. market-/identifier-leakage removal): "
                         "PROMOTE despite no significant accuracy gain, PROVIDED the gate confirms "
                         "accuracy non-regression. Applies to the selected --target. The reason is "
                         "logged to the verdict + JSON for the registry record.")
    ap.add_argument("--eval-calibration", action="store_true",
                    help="Instead of the accuracy gate, report DISTRIBUTION-calibration "
                         "diagnostics (coverage_80 / PIT / NLL / CRPS / directional bias) for "
                         "champion vs 30.4 challenger. Use for distributional regression targets "
                         "(e.g. total_runs LogNormal) before they become a projection source.")
    ap.add_argument("--seed", type=int, default=42,
                    help="Model-fit + bootstrap seed. Re-run with a DIFFERENT seed for a "
                         "hysteresis pass #2: an independent re-fit (not a byte-identical re-run) — "
                         "a PROMOTE that survives a seed change is robust to model-fit randomness.")
    ap.add_argument("--season-normalize", action="store_true",
                    help="Story 27.6: z-score the contact-quality features within season before "
                         "the calibration eval — validates the season-normalization fix for the "
                         "totals run-environment-regime over-bias. Only affects --eval-calibration.")
    args = ap.parse_args()
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].dropna().unique().tolist())}")

    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]

    if args.eval_calibration:
        results = {t: _run_calibration(t, df, season_normalize=args.season_normalize) for t in targets}
        out = _OUT_DIR / (f"calibration_{args.target}.json")
        out.write_text(json.dumps(results, indent=2, default=float))
        print(f"\nWrote {out}")
        print("\n=== CALIBRATION VERDICTS ===")
        for t, r in results.items():
            print(f"  {t:12s} {'OK' if r['calibration_ok'] else 'CONCERN'}  — {r['verdict']}")
        return

    results = {t: _run_target(t, df, args.correctness_override,
                              season_normalize=args.season_normalize, seed=args.seed) for t in targets}

    out = _OUT_DIR / ("promotion_gate_all.json" if args.target == "all"
                      else f"promotion_gate_{args.target}.json")
    out.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nWrote {out}")
    print("\n=== GATE DECISIONS (Case 3) ===")
    for t, r in results.items():
        ov = "  [correctness override]" if r.get("override_applied") else ""
        print(f"  {t:12s} {r['decision']}  (Δ{r['metric']}={r['overall_delta']:+.4f}){ov}")


if __name__ == "__main__":
    main()
