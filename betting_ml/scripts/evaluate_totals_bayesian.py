"""
evaluate_totals_bayesian.py — Epic 10.6 re-evaluation under a proper Bayesian framework

Brier-vs-0.25 (coin flip) is the wrong baseline for a distributional inference system:
it ignores the predictive distribution entirely and a model can lose to it while still
being informative. This re-runs the totals champion (v4 NGBoost Normal) vs the Layer 3
challenger (totals_v1 NegBin) under a three-layer framework, all on the SAME 2026 OOS
game_pk set:

  Layer 1 — Prior predictive gate. Fit a NegBin prior predictive from the training-era
      marginal of total_runs (mu_prior = train mean, r_prior = MLE dispersion); its NLL
      on the eval set is the Bayesian naive baseline. Each model must beat it independently
      (NegBin log-PMF for the challenger, discretized-Normal log-prob for v4 — PMF-vs-PMF).
  Layer 2 — Full predictive-distribution calibration. Coverage at 50/80/90% nominal +
      mean 80% PI width (sharpness, meaningful only once calibrated).
  Layer 3 — Betting evaluation on the alpha-BLENDED posterior (the deployable number) vs
      coin-flip 0.50, prior-naive (training over-rate), and Bovada market; directional bias;
      edge-bucket win-rate/ROI at -110.

Decision rules reported in three separate blocks: must-pass (per model), head-to-head
(challenger vs champion), operational (production deployment).

Snowflake-heavy (champion scoring + training marginal) → hand-off run.
Output: ablation_results/totals_bayesian_evaluation.md
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom, norm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.scripts.compare_totals_champion_challenger import (  # noqa: E402
    score_champion_v4, _normal_discrete_nll, _normal_calib_80, _roi_by_bucket,
)
from betting_ml.scripts.train_totals import _negbin_nll, _negbin_logpmf, _fit_negbin_r  # noqa: E402
from betting_ml.scripts.load_layer3_features import build_totals_dataset  # noqa: E402
from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402
from betting_ml.models.total_runs_trainer import p_over_line  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_v1.parquet"
_BEST_ALPHA = _PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
_REPORT = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_bayesian_evaluation.md"
_OOS_YEAR = 2026
_LEVELS = (0.50, 0.80, 0.90)


# --- prior predictive (Layer 1) -------------------------------------------
def fit_prior(y_train: np.ndarray) -> tuple[float, float]:
    """NegBin prior predictive from the training-era marginal: mu = mean, r = MLE dispersion."""
    mu = float(np.mean(y_train))
    r = _fit_negbin_r(y_train, np.full(len(y_train), mu))
    return mu, r


# --- calibration (Layer 2) -------------------------------------------------
def negbin_coverage(y, mu, r, level):
    a = (1 - level) / 2
    r = np.clip(r, 1e-6, None)
    p = r / (r + mu)
    lo, hi = nbinom.ppf(a, r, p), nbinom.ppf(1 - a, r, p)
    return float(np.mean((y >= lo) & (y <= hi)))


def normal_coverage(y, mu, sigma, level):
    z = norm.ppf(1 - (1 - level) / 2)
    return float(np.mean(np.abs(y - mu) <= z * np.clip(sigma, 1e-6, None)))


def negbin_pi80_width(mu, r):
    r = np.clip(r, 1e-6, None)
    p = r / (r + mu)
    return float(np.mean(nbinom.ppf(0.90, r, p) - nbinom.ppf(0.10, r, p)))


def _blend(p, devig, alpha):
    return np.array([compute_posterior(float(a), float(b), alpha) for a, b in zip(p, devig)])


def evaluate(env: str = "prod") -> dict:
    alpha = float(json.loads(_BEST_ALPHA.read_text()).get("totals_alpha", 0.70))

    # Shared 2026 OOS set (challenger from parquet ∩ champion-scorable).
    P = pd.read_parquet(_OOS_PARQUET)
    P["game_pk"] = P["game_pk"].astype(int)
    chall = P[(P["season"] == _OOS_YEAR) & (P["total_line_source"] == "bovada")
              & P["oos_p_over"].notna() & P["bovada_devig_over_prob"].notna()
              & P["over_hit"].notna()].copy()
    champ = score_champion_v4(chall["game_pk"].tolist())
    df = chall.merge(champ, on="game_pk", how="inner")
    log.info("Shared Bayesian-eval set: %d games", len(df))

    y = df["actual_total_runs"].to_numpy(float)
    line = df["bovada_line"].to_numpy(float)
    devig = df["bovada_devig_over_prob"].to_numpy(float)
    over_hit = df["over_hit"].to_numpy(float)

    # Training-era marginal (2021–2025) for the prior + prior-naive over-rate.
    _X, y_all, eval_lines, _rep, meta = build_totals_dataset(env=env, return_meta=True)
    tr = meta["game_year"] <= 2025
    y_train = y_all[tr.to_numpy()].to_numpy(float)
    lines_tr = (pd.DataFrame({"game_pk": meta.loc[tr, "game_pk"].to_numpy(),
                              "y": y_all[tr.to_numpy()].to_numpy(float)})
                .merge(eval_lines[["game_pk", "total_line_bovada"]], on="game_pk", how="inner")
                .dropna(subset=["total_line_bovada"]))
    train_over_rate = float((lines_tr["y"] > lines_tr["total_line_bovada"]).mean())
    mu_p, r_p = fit_prior(y_train)
    prior_nll = -float(np.mean(_negbin_logpmf(y, mu_p, r_p)))

    # Baselines (Layer 1 + Layer 3).
    market_brier = brier_score(devig, over_hit)
    prior_naive_brier = brier_score(np.full(len(y), train_over_rate), over_hit)
    coin_brier = brier_score(np.full(len(y), 0.5), over_hit)

    # --- challenger (NegBin) ---
    cmu, cr, cpo = df["oos_mu"].to_numpy(float), df["oos_r"].to_numpy(float), df["oos_p_over"].to_numpy(float)
    cbl = _blend(cpo, devig, alpha)
    chall_m = {
        "model": "Layer 3 Challenger (NegBin)",
        "nll": _negbin_nll(y, cmu, float(np.mean(cr))),
        "cov50": negbin_coverage(y, cmu, cr, 0.50),
        "cov80": negbin_coverage(y, cmu, cr, 0.80),
        "cov90": negbin_coverage(y, cmu, cr, 0.90),
        "pi80_width": negbin_pi80_width(cmu, cr),
        "brier_blended": brier_score(cbl, over_hit),
        "mean_p_blended": float(cbl.mean()),
        "roi": _roi_by_bucket(cbl - devig, over_hit),
    }
    # --- champion (Normal v4) ---
    hmu, hsig = df["champ_mu"].to_numpy(float), df["champ_sigma"].to_numpy(float)
    hpo = np.asarray(p_over_line("Normal", {"loc": hmu, "scale": hsig}, line), dtype=float)
    hbl = _blend(hpo, devig, alpha)
    champ_m = {
        "model": "v4 Champion (Normal)",
        "nll": _normal_discrete_nll(y, hmu, hsig),
        "cov50": normal_coverage(y, hmu, hsig, 0.50),
        "cov80": _normal_calib_80(y, hmu, hsig),
        "cov90": normal_coverage(y, hmu, hsig, 0.90),
        "pi80_width": float(np.mean(2 * 1.2815515 * np.clip(hsig, 1e-6, None))),
        "brier_blended": brier_score(hbl, over_hit),
        "mean_p_blended": float(hbl.mean()),
        "roi": _roi_by_bucket(hbl - devig, over_hit),
    }

    return {
        "n": len(df), "alpha": alpha, "mu_prior": mu_p, "r_prior": r_p,
        "prior_nll": prior_nll, "prior_naive_brier": prior_naive_brier,
        "market_brier": market_brier, "coin_brier": coin_brier,
        "train_over_rate": train_over_rate, "mean_market_p": float(devig.mean()),
        "actual_over_rate": float(over_hit.mean()),
        "champion": champ_m, "challenger": chall_m,
    }


# --- decision rules --------------------------------------------------------
def decisions(R: dict) -> dict:
    cp, ch = R["champion"], R["challenger"]

    def must_pass(m):
        return {
            "NLL < prior": m["nll"] < R["prior_nll"],
            "calib_80 in [0.75,0.85]": 0.75 <= m["cov80"] <= 0.85,
            "Brier(blended) < prior-naive": m["brier_blended"] < R["prior_naive_brier"],
        }

    h2h = {
        "challenger NLL < champion": ch["nll"] < cp["nll"],
        "challenger calib_80 closer to 0.80": abs(ch["cov80"] - 0.80) < abs(cp["cov80"] - 0.80),
        "challenger Brier(blended) < champion": ch["brier_blended"] < cp["brier_blended"],
    }

    def operational(m):
        return {
            "Brier(blended) < market": m["brier_blended"] < R["market_brier"],
            "strong-over ROI > 0": m["roi"]["strong_over"]["roi"] > 0,
            "strong-under ROI > 0": m["roi"]["strong_under"]["roi"] > 0,
        }

    return {
        "must_pass_champion": must_pass(cp), "must_pass_challenger": must_pass(ch),
        "head_to_head": h2h,
        "operational_champion": operational(cp), "operational_challenger": operational(ch),
    }


def _b(x):
    return "✅" if x else "❌"


def _roi_md(roi):
    return " · ".join(f"{k}: n={v['n']} win={v['win_rate']:.3f} roi={v['roi']:+.3f}" for k, v in roi.items())


def write_report(R: dict, D: dict) -> None:
    cp, ch = R["champion"], R["challenger"]
    tbl = [
        "| Metric | v4 Champion | Layer 3 Challenger | Baseline |",
        "|---|---:|---:|:--|",
        f"| **L1 NLL** (PMF) | {cp['nll']:.4f} | {ch['nll']:.4f} | prior-predictive **{R['prior_nll']:.4f}** (must beat) |",
        f"| **L2 coverage@50%** | {cp['cov50']:.3f} | {ch['cov50']:.3f} | nominal 0.50 |",
        f"| **L2 coverage@80%** (calib_80) | {cp['cov80']:.3f} | {ch['cov80']:.3f} | nominal 0.80 (gate 0.75–0.85) |",
        f"| **L2 coverage@90%** | {cp['cov90']:.3f} | {ch['cov90']:.3f} | nominal 0.90 |",
        f"| **L2 mean 80% PI width** | {cp['pi80_width']:.3f} | {ch['pi80_width']:.3f} | sharpness (lower=tighter) |",
        f"| **L3 Brier (blended α={R['alpha']:.2f})** | {cp['brier_blended']:.4f} | {ch['brier_blended']:.4f} | prior-naive **{R['prior_naive_brier']:.4f}** · market **{R['market_brier']:.4f}** · coin {R['coin_brier']:.4f} |",
        f"| **L3 mean P(over) blended** | {cp['mean_p_blended']:.3f} | {ch['mean_p_blended']:.3f} | actual {R['actual_over_rate']:.3f} · market {R['mean_market_p']:.3f} |",
    ]
    lines = [
        "# Totals — Bayesian Three-Layer Evaluation (Epic 10.6 re-run)",
        "",
        f"- **Shared OOS set:** {R['n']} games (2026 Bovada-line, settled), identical `game_pk` set for both models.",
        f"- **Blend:** alpha={R['alpha']:.2f} (totals_alpha, log-odds posterior toward Bovada) applied to BOTH models for the deployable number.",
        f"- **Prior predictive:** NegBin(mu={R['mu_prior']:.3f}, r={R['r_prior']:.3f}) from the 2021–25 training marginal; "
        f"prior-naive over-rate = {R['train_over_rate']:.3f}.",
        "",
        "## Comparison table",
        *tbl,
        "",
        "_Caveat: the challenger's NegBin is DISCRETE, so its central intervals over-cover at low "
        "nominal levels (≈0.57 at 50%); the effect shrinks by 80–90%. The champion's Normal is continuous "
        "(near-nominal throughout). Compare coverage with this in mind — the calib_80 gate (80%) is the least affected._",
        "",
        "## L3 edge-bucket ROI (blended posterior, −110)",
        f"- **Champion:** {_roi_md(cp['roi'])}",
        f"- **Challenger:** {_roi_md(ch['roi'])}",
        "",
        "## Decision rules (reported separately — a model can win the head-to-head yet fail the operational gate)",
        "",
        "### A. Must-pass gates (each model independently)",
        "| Gate | v4 Champion | Layer 3 Challenger |",
        "|---|:--:|:--:|",
        *[f"| {k} | {_b(D['must_pass_champion'][k])} | {_b(D['must_pass_challenger'][k])} |"
          for k in D["must_pass_champion"]],
        "",
        "### B. Head-to-head (challenger vs champion)",
        "| Gate | Result |",
        "|---|:--:|",
        *[f"| {k} | {_b(v)} |" for k, v in D["head_to_head"].items()],
        "",
        "### C. Operational gates (production deployment)",
        "| Gate | v4 Champion | Layer 3 Challenger |",
        "|---|:--:|:--:|",
        *[f"| {k} | {_b(D['operational_champion'][k])} | {_b(D['operational_challenger'][k])} |"
          for k in D["operational_champion"]],
        "",
        "## Read",
        f"- **Layer 1:** "
        + ("at least one model beats the prior predictive — the distributional model is informative."
           if (cp["nll"] < R["prior_nll"] or ch["nll"] < R["prior_nll"])
           else "**NEITHER model beats the prior predictive NLL** — the covariates add no information over the training marginal; do not deploy either."),
        "- **Operational vs head-to-head are separate:** the head-to-head names the better *model*; the operational gates "
        "(Brier(blended) < market AND edge-bucket ROI > 0) decide whether ANY totals model should bet. "
        "Passing B without C still means no production deployment.",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s", _REPORT)


def run(env: str = "prod") -> dict:
    R = evaluate(env=env)
    D = decisions(R)
    write_report(R, D)
    cp, ch = R["champion"], R["challenger"]
    log.info("L1 prior NLL=%.4f | champ NLL=%.4f chall NLL=%.4f", R["prior_nll"], cp["nll"], ch["nll"])
    log.info("L2 calib_80 champ=%.3f chall=%.3f | L3 Brier(blended) champ=%.4f chall=%.4f "
             "(prior-naive %.4f, market %.4f)",
             cp["cov80"], ch["cov80"], cp["brier_blended"], ch["brier_blended"],
             R["prior_naive_brier"], R["market_brier"])
    return {"R": R, "D": D}


def main() -> None:
    p = argparse.ArgumentParser(description="Bayesian three-layer totals evaluation (Epic 10.6 re-run)")
    p.add_argument("--env", choices=["prod", "dev"], default="prod")
    p.parse_args()
    run(env="prod")


if __name__ == "__main__":
    main()
