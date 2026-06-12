"""Epic 30 — per-target feature-influence report (what's driving each model).

For each production target, loads the LOCAL champion artifact + its contract,
computes permutation importance on the honest 2026 OOS surface, aggregates by
feature family, and classifies every feature as strong / moderate / weak /
dead-weight (exclusion candidate) / identifier. Writes a per-target markdown +
a combined "improvement levers" summary + JSON.

Why LOCAL (not load_model "prod"): load_model pulls the registry's S3 artifact,
which is the OLD pre-scrub champion until the operator uploads. This harness is
meant to inspect the FRESHLY-RETRAINED local champions, so it reads the local
pkl + the registry's local feature_columns_path.

Permutation importance is model-agnostic:
  - classification (home_win): scorer = -Brier (shuffling a useful feature raises Brier)
  - regression (run_diff, total_runs): scorer = -MAE

Runtime: loads from Snowflake + permutes every feature × n_repeats × 3 models —
minutes. Hand off to run with real credentials.

Usage:
    uv run python betting_ml/scripts/influence_report.py --target all
    uv run python betting_ml/scripts/influence_report.py --target home_win --n-repeats 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import brier_score_loss

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.scripts.model_evaluation.analyze_feature_importance import _infer_feature_group
from betting_ml.utils.data_loader import load_features
from betting_ml.utils.feature_hygiene import is_identifier_name

_OUT_DIR = PROJECT_ROOT / "betting_ml" / "evaluation" / "feature_selection" / "influence_report"


class _PermAdapter:
    """Thin wrapper so sklearn.permutation_importance accepts an already-fitted
    model. permutation_importance's param-validation requires a `fit` method even
    though it never refits (it only permutes columns and re-scores via our custom
    scorer). PlattCalibratedXGBClassifier exposes predict_proba but no fit/predict,
    so wrap it; delegate predict/predict_proba to the real model unchanged."""

    def __init__(self, model):
        self._model = model

    def fit(self, X=None, y=None):  # no-op — model is pre-fitted
        return self

    def predict(self, X):
        if hasattr(self._model, "predict"):
            return self._model.predict(X)
        # classification fallback: threshold the calibrated P(class 1)
        return (self._model.predict_proba(X)[:, 1] >= 0.5).astype(int)

    def predict_proba(self, X):
        return self._model.predict_proba(X)

# Local champion artifact + contract per target (the freshly-retrained files).
_TARGETS = {
    "home_win": {
        "kind": "classification", "target_col": "home_win",
        "pkl": "betting_ml/models/home_win/xgb_classifier_tuned_2026.pkl",
        "contract": "betting_ml/models/home_win/feature_columns_xgb_classifier_tuned_2026.json",
    },
    "run_diff": {
        "kind": "regression", "target_col": "run_differential",
        "pkl": "betting_ml/models/run_differential/ngboost_tuned_2026.pkl",
        "contract": "betting_ml/models/run_differential/feature_columns_ngboost_tuned_2026.json",
    },
    "total_runs": {
        "kind": "regression", "target_col": "total_runs",
        # NOTE: deployed total_runs champion is ngboost_eb_enriched (S3-only). This
        # inspects the local freshly-scrubbed `tuned` totals model on the shelf.
        "pkl": "betting_ml/models/total_runs/ngboost_tuned_2026.pkl",
        "contract": "betting_ml/models/total_runs/feature_columns_ngboost_tuned_2026.json",
    },
}


def _eval_surface(df: pd.DataFrame, target_col: str, feat_cols: list[str], year: int):
    sub = df[(df["game_year"] == year) & df[target_col].notna()].reset_index(drop=True)
    missing = [c for c in feat_cols if c not in sub.columns]
    for c in missing:
        sub[c] = 0.0
    X = sub[feat_cols].fillna(0.0).values.astype(np.float32)
    y = sub[target_col].values.astype(np.float32)
    return X, y, missing


def _run_target(name: str, df: pd.DataFrame, n_repeats: int) -> dict:
    cfg = _TARGETS[name]
    contract = json.loads((PROJECT_ROOT / cfg["contract"]).read_text())
    feat_cols = contract["feature_cols"] if isinstance(contract, dict) else contract
    model = _PermAdapter(joblib.load(PROJECT_ROOT / cfg["pkl"]))

    X, y, missing = _eval_surface(df, cfg["target_col"], feat_cols, 2026)
    print(f"\n=== {name} ({cfg['kind']}) — {len(feat_cols)} feats, 2026 eval n={len(X)} ===")
    if missing:
        print(f"  WARNING: {len(missing)} contract feats absent from df (zero-filled): {missing[:5]}")

    if cfg["kind"] == "classification":
        def scorer(est, X_, y_):
            return -float(brier_score_loss(y_, est.predict_proba(X_)[:, 1]))
        baseline = -scorer(model, X, y)
        print(f"  baseline Brier={baseline:.4f}")
    else:
        def scorer(est, X_, y_):
            return -float(np.mean(np.abs(est.predict(X_) - y_)))
        baseline = -scorer(model, X, y)
        print(f"  baseline MAE={baseline:.4f}")

    res = permutation_importance(model, X, y, scoring=scorer, n_repeats=n_repeats,
                                 random_state=42, n_jobs=-1)
    imp, std = res.importances_mean, res.importances_std
    ci_lower = imp - std

    rows = []
    for i, c in enumerate(feat_cols):
        rows.append({
            "feature": c, "mean_imp": float(imp[i]), "ci_lower": float(ci_lower[i]),
            "group": _infer_feature_group(c), "identifier": bool(is_identifier_name(c)),
        })
    fi = pd.DataFrame(rows).sort_values("mean_imp", ascending=False).reset_index(drop=True)

    # Classify: dead-weight (shuffling doesn't hurt), weak, moderate, strong (by quantile of positives)
    pos = fi[fi["mean_imp"] > 0]["mean_imp"]
    q80 = pos.quantile(0.80) if len(pos) else 0.0
    q50 = pos.quantile(0.50) if len(pos) else 0.0

    def _tier(v):
        if v <= 0:
            return "dead"
        if v >= q80:
            return "strong"
        if v >= q50:
            return "moderate"
        return "weak"

    fi["tier"] = fi["mean_imp"].apply(_tier)
    n_dead = int((fi["tier"] == "dead").sum())
    total_imp = fi[fi["mean_imp"] > 0]["mean_imp"].sum()

    # Family aggregation
    fam = (fi.groupby("group")["mean_imp"].agg(["sum", "count"])
           .sort_values("sum", ascending=False))

    print(f"  dead-weight: {n_dead}/{len(fi)} features ({100*n_dead/len(fi):.0f}%) don't help")
    print(f"  identifier cols present: {fi[fi['identifier']]['feature'].tolist() or 'none (clean)'}")
    print("  TOP 10 DRIVERS:")
    for _, r in fi.head(10).iterrows():
        share = 100 * r["mean_imp"] / total_imp if total_imp > 0 else 0
        print(f"    {r['feature']:42s} imp={r['mean_imp']:.5f} ({share:4.1f}%)  {r['group']}")

    return {
        "target": name, "kind": cfg["kind"], "n_features": len(feat_cols),
        "eval_year": 2026, "eval_n": int(len(X)), "baseline": baseline,
        "n_dead_weight": n_dead, "identifier_cols": fi[fi["identifier"]]["feature"].tolist(),
        "top_drivers": fi.head(20).to_dict("records"),
        "families": [{"group": g, "sum": float(r["sum"]), "count": int(r["count"])}
                     for g, r in fam.iterrows()],
        "all_features": fi.to_dict("records"),
    }


def _write_markdown(results: dict) -> None:
    lines = ["# Epic 30 — Per-Target Feature-Influence Report", "",
             "Permutation importance on the honest 2026 OOS surface, local champion artifacts.",
             "Higher imp = shuffling that feature hurts the model more (it carries signal).", ""]
    for name, r in results.items():
        tot = sum(d["mean_imp"] for d in r["top_drivers"] if d["mean_imp"] > 0)
        lines += [f"## {name} ({r['kind']}, {r['n_features']} feats, 2026 n={r['eval_n']})", "",
                  f"- Baseline {'Brier' if r['kind']=='classification' else 'MAE'}: {r['baseline']:.4f}",
                  f"- **Dead-weight: {r['n_dead_weight']}/{r['n_features']} "
                  f"({100*r['n_dead_weight']/r['n_features']:.0f}%)** features don't help (prune candidates)",
                  f"- Identifier cols present: {r['identifier_cols'] or 'none — clean ✓'}", "",
                  "**Top drivers:**", "", "| # | feature | imp | group |", "|--|--|--|--|"]
        for i, d in enumerate(r["top_drivers"][:15]):
            lines.append(f"| {i+1} | {d['feature']} | {d['mean_imp']:.5f} | {d['group']} |")
        lines += ["", "**Signal by family (aggregate importance):**", "", "| family | sum imp | n |", "|--|--|--|"]
        for f in r["families"][:10]:
            lines.append(f"| {f['group']} | {f['sum']:.4f} | {f['count']} |")
        lines += [""]
    # NOTE: filename is deliberately NOT "influence_report.md" — on a case-insensitive
    # filesystem (macOS) that collides with the curated INFLUENCE_REPORT.md evidence doc
    # in this same dir and silently overwrites it. Keep the generated report distinct.
    (_OUT_DIR / "influence_report_generated.md").write_text("\n".join(lines))
    print(f"\nWrote {_OUT_DIR / 'influence_report_generated.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["home_win", "run_diff", "total_runs", "all"], default="all")
    ap.add_argument("--n-repeats", type=int, default=10)
    args = ap.parse_args()

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Loading features from Snowflake...")
    df = load_features().reset_index(drop=True)
    print(f"Loaded {len(df)} rows, seasons: {sorted(df['game_year'].dropna().unique().tolist())}")

    targets = ["home_win", "run_diff", "total_runs"] if args.target == "all" else [args.target]
    results = {t: _run_target(t, df, args.n_repeats) for t in targets}

    out = _OUT_DIR / ("influence_all.json" if args.target == "all" else f"influence_{args.target}.json")
    out.write_text(json.dumps(results, indent=2, default=float))
    print(f"\nWrote {out}")
    _write_markdown(results)


if __name__ == "__main__":
    main()
