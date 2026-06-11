"""
train_h2h_28_4.py — Story 28.4: H2H-specific features + retrain

Augments the Layer 3 H2H matrix with:
  • Travel/fatigue features (home/away): travel_distance_miles, tz_delta_hours,
    is_3rd_consecutive_road_game, is_getaway_day — from mart_team_schedule_context
  • starter_suppression_mu × opp pred_runs_mu interaction terms
  • run_diff_sigma conviction feature (uncertainty about the run differential)

Retrains the home_win LightGBM + Platt challenger on the augmented matrix,
evaluates on the credible 2026 OOS surface (market Brier ≤ 0.235 gate), and
reports whether the confirmation gate (model Brier ≤ 0.195) is met.

Artifact:  betting_ml/models/sub_models/h2h_v2_28_4_challenger.pkl
Report:    quant_sports_intel_models/baseball/ablation_results/h2h_features_28_4.md

Usage (hand-off — Snowflake load + train takes > 1 min):
    uv run python betting_ml/scripts/train_h2h_28_4.py --env prod
    uv run python betting_ml/scripts/train_h2h_28_4.py --env prod --quick   # smoke test
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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.load_layer3_features import (  # noqa: E402
    build_h2h_augmented_dataset,
    _H2H_EXTRA_COLS,
)
from betting_ml.scripts.train_h2h import (  # noqa: E402
    brier, logloss, ece, _proba, _tune, _folds, select_winner,
    _fit_lightgbm, _fit_elasticnet,
    _MIN_TRAIN_SEASONS, _N_TRIALS,
    per_game_logloss,
)
from betting_ml.models.h2h_classifier_model import H2HClassifierModel  # noqa: E402
from betting_ml.models.totals_negbin_model import coerce_numeric as _coerce_numeric  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_ARTIFACT_PATH = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "h2h_v2_28_4_challenger.pkl"
)
_REPORT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball"
    / "ablation_results" / "h2h_features_28_4.md"
)
_OPTUNA_SEED = 42
_SANE_MARKET_BRIER_MAX = 0.235   # seasons above this have degraded/flat lines
_CONFIRM_BRIER_GATE    = 0.195   # Story 28.4 confirmation gate


# ---------------------------------------------------------------------------
# Walk-forward CV (model vs market, identical coverage)
# ---------------------------------------------------------------------------

def _cv_vs_market(
    kind: str,
    X: pd.DataFrame,
    y: pd.Series,
    meta: pd.DataFrame,
    params: dict,
    prob_by_pk: dict,
    calibrate: bool = False,
) -> dict:
    """Walk-forward CV that scores model AND market on identical covered games."""
    from betting_ml.scripts.train_h2h import _fit, _aggregate

    folds_out: list[dict] = []
    pooled: dict = {"mp": [], "my": [], "model_p": [], "model_y": []}

    for tr_idx, ev_idx in _folds(meta):
        X_tr, y_tr = X.loc[tr_idx], y.loc[tr_idx].to_numpy()
        X_ev, y_ev = X.loc[ev_idx], y.loc[ev_idx].to_numpy()
        model = _fit(kind, X_tr, y_tr, params, calibrate)
        p_ev  = _proba(model, X_ev)
        pks   = meta.loc[ev_idx, "game_pk"].to_numpy()

        cov      = np.array([int(pk) in prob_by_pk for pk in pks])
        mkt_p    = np.array([prob_by_pk.get(int(pk), np.nan) for pk in pks])
        mp, my   = mkt_p[cov], y_ev[cov]
        mdl_cov  = p_ev[cov]

        folds_out.append({
            "eval_year":       int(meta.loc[ev_idx, "game_year"].iloc[0]),
            "n_eval":          int(len(y_ev)),
            "n_covered":       int(cov.sum()),
            "model_brier_cov": brier(mdl_cov, my) if cov.any() else float("nan"),
            "market_brier_cov":brier(mp, my)       if cov.any() else float("nan"),
            "ece":             ece(p_ev, y_ev),
        })
        pooled["mp"].extend(mp.tolist()); pooled["my"].extend(my.tolist())
        pooled["model_p"].extend(mdl_cov.tolist()); pooled["model_y"].extend(my.tolist())

    agg = _aggregate(kind, [{"eval_year": f["eval_year"], "n_eval": f["n_eval"],
                              "log_loss": float("nan"), "brier": f["model_brier_cov"],
                              "ece": f["ece"]} for f in folds_out])
    mp_arr = np.array(pooled["mp"]); my_arr = np.array(pooled["my"])
    mdl_arr = np.array(pooled["model_p"])
    agg.update({
        "folds_vs_market":        folds_out,
        "pooled_model_brier_cov": brier(mdl_arr, my_arr) if len(my_arr) else float("nan"),
        "pooled_market_brier_cov":brier(mp_arr,  my_arr) if len(my_arr) else float("nan"),
        "n_covered":              int(len(my_arr)),
    })
    return agg


# ---------------------------------------------------------------------------
# Orthogonality check for travel features (Story 28.4 AC1)
# ---------------------------------------------------------------------------

def _check_travel_orthogonality(df: pd.DataFrame) -> dict:
    """Confirm travel features are not redundant with existing signal columns.

    Reports pairwise Pearson correlation of each travel feature against the
    top signal columns. 'Orthogonal' here means |corr| < 0.70 with any single
    existing signal column — confirming they add independent information.
    """
    signal_cols = [
        "run_env_mu_v4",
        "home_pred_runs_mu_v2", "away_pred_runs_mu_v2",
        "home_starter_suppression_mu_v1", "away_starter_suppression_mu_v1",
        "home_bullpen_mu_v2", "away_bullpen_mu_v2",
    ]
    travel_cols = [c for c in _H2H_EXTRA_COLS if c in df.columns]
    results: dict = {}
    for tc in travel_cols:
        if df[tc].dtype == bool:
            col = df[tc].astype(float)
        else:
            col = pd.to_numeric(df[tc], errors="coerce")
        if col.isna().all():
            results[tc] = {"max_abs_corr": float("nan"), "orthogonal": True}
            continue
        max_corr = 0.0
        for sc in signal_cols:
            if sc not in df.columns:
                continue
            sig = pd.to_numeric(df[sc], errors="coerce")
            valid = col.notna() & sig.notna()
            if valid.sum() < 30:
                continue
            c = float(abs(np.corrcoef(col[valid], sig[valid])[0, 1]))
            if c > max_corr:
                max_corr = c
        results[tc] = {"max_abs_corr": round(max_corr, 4), "orthogonal": max_corr < 0.70}
    return results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _write_report(
    winner: str,
    wm: dict,
    coverage_report: dict,
    orth_report: dict,
    n_games: int,
    base_rate: float,
    augmented_cols: list[str],
) -> Path:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Per-season verdict
    credible   = [f for f in wm["folds_vs_market"]
                  if f["market_brier_cov"] <= _SANE_MARKET_BRIER_MAX]
    degraded   = [f["eval_year"] for f in wm["folds_vs_market"]
                  if f["market_brier_cov"] > _SANE_MARKET_BRIER_MAX]
    cr_2026    = next((f for f in credible if f["eval_year"] == 2026), None)
    gate_met   = (cr_2026 is not None
                  and cr_2026["model_brier_cov"] <= _CONFIRM_BRIER_GATE)

    null_rates   = coverage_report.get("null_rates", {})
    coverage_ok  = coverage_report.get("coverage_ok", False)

    lines = [
        "# H2H Features (Story 28.4) — Travel/Fatigue + Interaction Terms",
        "",
        f"**Goal:** Add H2H-specific features and retrain, targeting credible-2026 "
        f"Brier ≤ {_CONFIRM_BRIER_GATE} (the 0.18–0.20 sharp-market band).",
        "",
        f"- Games: **{n_games}**, home_win base rate {base_rate:.4f}.",
        f"- Augmented features added: `{', '.join(augmented_cols)}`",
        "",
        "## AC1 — Feature coverage (≥95% non-null required)",
        "",
        "| feature | null rate | pass |",
        "|---|---|---|",
    ]
    for c, r in null_rates.items():
        ok = "✅" if r <= 0.05 else "❌"
        lines.append(f"| `{c}` | {r:.4f} | {ok} |")
    lines += [
        "",
        f"**Coverage gate:** {'✅ PASS' if coverage_ok else '❌ FAIL — rebuild mart before promoting'}",
        "",
        "## AC1 — Orthogonality of travel features (|corr| < 0.70 with any signal column)",
        "",
        "| feature | max |corr| vs signals | orthogonal |",
        "|---|---|---|",
    ]
    for c, r in orth_report.items():
        ok = "✅" if r["orthogonal"] else "❌"
        lines.append(f"| `{c}` | {r['max_abs_corr']:.4f} | {ok} |")

    # CV verdict table
    lines += [
        "",
        "## Per-season head-to-head (identical market-covered games)",
        "",
        "| season | n cov | model Brier | market Brier | Δ (mkt−mdl) | market quality | beats mkt |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in wm["folds_vs_market"]:
        deg  = f["market_brier_cov"] > _SANE_MARKET_BRIER_MAX
        qual = "⚠️ degraded" if deg else "credible"
        d    = f["market_brier_cov"] - f["model_brier_cov"]
        beat = "—" if deg else ("✅" if d > 0 else "❌")
        lines.append(
            f"| {f['eval_year']} | {f['n_covered']} | {f['model_brier_cov']:.4f} | "
            f"{f['market_brier_cov']:.4f} | {d:+.4f} | {qual} | {beat} |"
        )
    dp = wm["pooled_market_brier_cov"] - wm["pooled_model_brier_cov"]
    lines += [
        f"| POOLED | {wm['n_covered']} | {wm['pooled_model_brier_cov']:.4f} | "
        f"{wm['pooled_market_brier_cov']:.4f} | {dp:+.4f} | mixed | — |",
        "",
        f"> Degraded seasons (excluded from verdict): {degraded or 'none'} "
        f"(market Brier > {_SANE_MARKET_BRIER_MAX}).",
    ]

    # Confirmation gate
    gate_2026_str = (
        f"{cr_2026['model_brier_cov']:.4f}" if cr_2026 else "N/A (2026 not in eval)"
    )
    gate_symbol = "✅ GATE MET" if gate_met else "❌ GATE NOT MET"
    lines += [
        "",
        "## AC2 — Confirmation gate",
        "",
        f"| gate | target | actual (2026) | result |",
        "|---|---|---|---|",
        f"| credible-2026 Brier | ≤ {_CONFIRM_BRIER_GATE} | {gate_2026_str} | {gate_symbol} |",
        "",
    ]
    if gate_met:
        lines += [
            f"**{gate_symbol}** — credible-2026 Brier {gate_2026_str} ≤ {_CONFIRM_BRIER_GATE}. "
            "The augmented challenger enters the 0.18–0.20 sharp-market band. "
            "Justifies a non-zero blend alpha; route to model_registry promotion.",
        ]
    else:
        gap = (
            f"{cr_2026['model_brier_cov']:.4f} − {_CONFIRM_BRIER_GATE} = "
            f"{cr_2026['model_brier_cov'] - _CONFIRM_BRIER_GATE:+.4f}"
            if cr_2026 else "2026 fold absent"
        )
        lines += [
            f"**{gate_symbol}** — residual gap: {gap}. "
            "Feature augmentation does not close the market gap by itself. "
            "Route to Story 28.5 (Hierarchical Bradley-Terry).",
        ]
    lines.append("")
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote report → %s", _REPORT_PATH)
    return _REPORT_PATH


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(env: str = "prod", n_trials: int = _N_TRIALS, quick: bool = False) -> dict:
    log.info("Story 28.4 — loading augmented H2H dataset (env=%s)...", env)
    X, y, eval_probs, report, meta = build_h2h_augmented_dataset(
        env=env, return_meta=True,
    )
    X = _coerce_numeric(X)

    if quick:
        X    = X.tail(1500).reset_index(drop=True)
        y    = y.tail(1500).reset_index(drop=True)
        meta = meta.tail(1500).reset_index(drop=True)
        n_trials = 4

    coverage_report = report.get("h2h_extra_coverage", {})
    prob_by_pk = {
        int(pk): float(v)
        for pk, v in zip(eval_probs["game_pk"], eval_probs["bovada_devig_home_prob"])
        if pd.notna(v)
    }

    log.info("Augmented matrix: X=%s, base_rate=%.4f, market_coverage=%d/%d",
             X.shape, float(y.mean()), len(prob_by_pk), len(y))

    # Orthogonality check (AC1)
    orth = _check_travel_orthogonality(X)
    for c, r in orth.items():
        status = "✅ orthogonal" if r["orthogonal"] else "⚠️ correlated"
        log.info("  orth[%s]: max_corr=%.4f %s", c, r["max_abs_corr"], status)

    # Tune LightGBM on the augmented matrix
    log.info("Tuning LightGBM on augmented matrix (%d trials)...", n_trials)
    params = _tune("lightgbm", X, y, meta, n_trials)

    # CV vs market (per fold)
    log.info("Walk-forward CV vs market...")
    wm = _cv_vs_market("lightgbm", X, y, meta, params, prob_by_pk, calibrate=True)

    # Log per-fold results
    for f in wm["folds_vs_market"]:
        d   = f["market_brier_cov"] - f["model_brier_cov"]
        deg = f["market_brier_cov"] > _SANE_MARKET_BRIER_MAX
        log.info("  %d: n_cov=%d  model=%.4f  market=%.4f  Δ=%+.4f  %s",
                 f["eval_year"], f["n_covered"],
                 f["model_brier_cov"], f["market_brier_cov"], d,
                 "⚠️ degraded" if deg else ("✅ beats" if d > 0 else "❌ loses"))

    dp = wm["pooled_market_brier_cov"] - wm["pooled_model_brier_cov"]
    log.info("  POOLED: model=%.4f  market=%.4f  Δ=%+.4f",
             wm["pooled_model_brier_cov"], wm["pooled_market_brier_cov"], dp)

    # Finalize and save the challenger artifact (Platt-calibrated for deployment)
    final_model = _fit_lightgbm(X, y.to_numpy(), params, calibrate=True)
    challenger  = H2HClassifierModel("lightgbm", final_model, list(X.columns), calibrated=True)
    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(challenger, _ARTIFACT_PATH)
    log.info("Saved challenger artifact → %s", _ARTIFACT_PATH)

    # Write report
    report_path = _write_report(
        winner="lightgbm",
        wm=wm,
        coverage_report=coverage_report,
        orth_report=orth,
        n_games=len(X),
        base_rate=float(y.mean()),
        augmented_cols=[c for c in _H2H_EXTRA_COLS if c in X.columns],
    )
    log.info("Done. Report → %s", report_path)
    return {
        "wm": wm, "orth": orth, "coverage": coverage_report, "params": params,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Story 28.4: H2H augmented retrain")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.add_argument("--n-trials", type=int, default=_N_TRIALS)
    p.add_argument("--quick", action="store_true", help="Subsample + few trials (smoke test)")
    args = p.parse_args()
    run(env=args.env, n_trials=args.n_trials, quick=args.quick)


if __name__ == "__main__":
    main()
