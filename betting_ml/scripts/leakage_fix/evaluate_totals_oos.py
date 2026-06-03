"""
evaluate_totals_oos.py — Leakage fix Phase 2c (honest totals re-eval)

Re-evaluate the Epic 9 **stacking combiner** (the totals signal Epic 10 consumes)
on the LEAKAGE-FREE walk-forward Layer 3 matrix (`build_oos_matrix`), and report
the verdict per-season vs. the de-vigged Bovada totals market — the comparison
the leakage-contaminated Epic 10 eval could never make cleanly.

Pipeline, fully walk-forward (no in-sample leakage):
  For eval season S (train = OOS-signal seasons < S):
    1. Per promoted signal (bullpen/offense/run_env from stacking_weights.json),
       fit a single-feature Poisson GLM mapping the signal's mu column(s) onto
       total_runs on train, predict mu_i on S; fit NB2 r on train → sigma_i.
       (Same _per_game_signal_dist math as compute_stacking_weights, but fit on
       prior seasons only — the honest version of its in-sample demonstration.)
    2. Combine to (combined_mu, combined_sigma) via combine_distributional_signals
       with the PERSISTED pseudo-BMA weights (near-uniform ~0.33, fold-std <0.003,
       so their own mild contamination is negligible).
    3. Derive an NB2 dispersion from the combined moments (r = mu²/(var−mu)) and
       compute model P(over) at the Bovada line; compare to market P(over).

Market-quality gate (totals): a season's de-vigged-P(over) market Brier > 0.240
is flagged degraded and excluded from the operational verdict. PER USER (2026-06-03):
the 2024-25 historical totals lines are credible (no quality cliff vs 2026, well
calibrated — see reference_bovada_h2h_line_quality), so all three seasons are
reported side by side; 2026 (Parlay) remains the single cleanest reference. The
0.240 gate still flags any genuinely broken season.

Output: ablation_results/totals_v2_leakage_free.md

Usage:
    uv run python betting_ml/scripts/leakage_fix/evaluate_totals_oos.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="X does not have valid feature names", category=UserWarning)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from scipy.stats import nbinom

from betting_ml.scripts.leakage_fix.build_oos_matrix import build_oos_matrix
from betting_ml.scripts.load_layer3_features import (
    load_total_line_bovada, _SIGNAL_GROUPS, _COMPLETENESS_FLOOR,
)
from betting_ml.scripts.evaluate_layer3_signals import (
    _design, _fit_poisson_mu, _fit_negbin_r, _group_mu_cols,
)
from betting_ml.scripts.compute_stacking_weights import (
    combine_distributional_signals, _WEIGHTS_PATH,
)
from betting_ml.utils.cv_splits import all_season_splits

import json

_OUT_PATH = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_v2_leakage_free.md"
_GROUP_BY_LABEL = {g[0]: g for g in _SIGNAL_GROUPS}
_MIN_TRAIN_SEASONS = 2
# Totals over/under is balanced-by-design (P(over)≈0.5 → self-Brier ≈0.25 even for
# a sharp market), so this gate is looser than the h2h 0.235 and flags only a
# genuinely broken season. See reference_bovada_h2h_line_quality.
_SANE_MARKET_BRIER_MAX = 0.240
_R_MIN, _R_MAX = 0.1, 1e6


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def _implied(american: np.ndarray) -> np.ndarray:
    a = np.asarray(american, dtype=float)
    return np.where(a < 0, np.abs(a) / (np.abs(a) + 100.0), 100.0 / (a + 100.0))


def _devig_p_over(over_price, under_price) -> np.ndarray:
    ro, ru = _implied(over_price), _implied(under_price)
    return ro / (ro + ru)


def _load_weights() -> dict:
    data = json.loads(Path(_WEIGHTS_PATH).read_text())
    blk = data["targets"]["total_runs"]
    return {label: info["weight"] for label, info in blk.items()}


def _nb2_p_over(mu: np.ndarray, sigma: np.ndarray, line: np.ndarray) -> np.ndarray:
    """P(total_runs > line) under an NB2 with the combined moments (mean mu, var sigma²)."""
    mu = np.clip(np.asarray(mu, float), 1e-6, None)
    var = np.clip(np.asarray(sigma, float) ** 2, mu + 1e-6, None)  # enforce overdispersion
    r = np.clip(mu ** 2 / (var - mu), _R_MIN, _R_MAX)
    p = r / (r + mu)
    # over = total_runs > line; X integer → P(X>line) = 1 - cdf(floor(line)).
    return 1.0 - nbinom.cdf(np.floor(np.asarray(line, float)), n=r, p=p)


def _build():
    df = build_oos_matrix(env="prod")
    df = df[df["signal_completeness_score"] >= _COMPLETENESS_FLOOR].reset_index(drop=True)
    line = load_total_line_bovada(df["game_pk"].tolist(), env="prod")
    # over/under prices are pd.NA on consensus-fallback rows (object dtype) → coerce
    # to float NaN so reindex/to_numpy(float) works and price-presence is well-defined.
    for c in ("total_line_bovada", "over_price", "under_price"):
        line[c] = pd.to_numeric(line[c], errors="coerce")
    return df, line


def _signal_dist_walkforward(df, label, tr_idx, ev_idx, y_all):
    """Fit single-feature Poisson(mu→total_runs)+NB2 on train seasons, predict eval."""
    _, mu_name, *_ = _GROUP_BY_LABEL[label]
    cols = _group_mu_cols(label, mu_name)
    y_tr = y_all[df.index.get_indexer(tr_idx)]
    X_tr, means = _design(df, tr_idx, cols)
    X_ev, _ = _design(df, ev_idx, cols, means)
    mu_tr, mu_ev = _fit_poisson_mu(X_tr, y_tr, X_ev)
    r = _fit_negbin_r(y_tr, mu_tr)
    sigma_ev = np.sqrt(mu_ev + mu_ev ** 2 / r)
    return mu_ev, sigma_ev


def evaluate():
    df, line = _build()
    weights = _load_weights()
    promoted = [l for l in weights if weights[l] > 0]
    y_all = pd.to_numeric(df["total_runs"]).to_numpy(float)

    # eval-only market line/prices per game_pk
    line = line.set_index("game_pk")
    has_price = (line["over_price"].notna() & line["under_price"].notna()
                 & line["total_line_bovada"].notna())
    has_price = has_price[~has_price.index.duplicated()]

    folds = list(all_season_splits(df, min_train_seasons=_MIN_TRAIN_SEASONS))
    fold_out = []
    pooled = {"mp": [], "model_p": [], "y": []}
    for tr_idx, ev_idx in folds:
        season = int(df.loc[ev_idx, "game_year"].iloc[0])
        mus = {l: None for l in promoted}
        sigmas = {l: None for l in promoted}
        for l in promoted:
            mus[l], sigmas[l] = _signal_dist_walkforward(df, l, tr_idx, ev_idx, y_all)
        comb_mu, comb_sigma = combine_distributional_signals(mus, sigmas, weights)

        ev = df.loc[ev_idx]
        pk = ev["game_pk"].to_numpy()
        tot = y_all[df.index.get_indexer(ev_idx)]
        # de-dup line index (a stray duplicate game_pk would break reindex)
        ldf = line[~line.index.duplicated()]
        L = ldf["total_line_bovada"].reindex(pk).to_numpy(float)
        op = ldf["over_price"].reindex(pk).to_numpy(float)
        up = ldf["under_price"].reindex(pk).to_numpy(float)
        priced = has_price.reindex(pk).fillna(False).to_numpy(dtype=bool)

        # Need a line + both prices, and a non-push outcome.
        valid = priced & np.isfinite(L) & np.isfinite(op) & np.isfinite(up) & (tot != L)
        if not valid.any():
            continue
        model_p = _nb2_p_over(comb_mu[valid], comb_sigma[valid], L[valid])
        mkt_p = _devig_p_over(op[valid], up[valid])
        over = (tot[valid] > L[valid]).astype(float)

        fold_out.append({
            "season": season, "n": int(valid.sum()),
            "model_brier": brier(model_p, over),
            "market_brier": brier(mkt_p, over),
            "over_rate": float(over.mean()),
            "mean_model_p": float(model_p.mean()),
            "mean_mkt_p": float(mkt_p.mean()),
            "mean_combined_mu": float(comb_mu[valid].mean()),
        })
        pooled["mp"].extend(mkt_p.tolist())
        pooled["model_p"].extend(model_p.tolist())
        pooled["y"].extend(over.tolist())

    mp, model_p, y = map(np.array, (pooled["mp"], pooled["model_p"], pooled["y"]))
    pooled_rec = {
        "n": int(len(y)),
        "model_brier": brier(model_p, y) if len(y) else float("nan"),
        "market_brier": brier(mp, y) if len(y) else float("nan"),
    }
    return fold_out, pooled_rec, weights


def _degraded(f: dict) -> bool:
    return not (f["market_brier"] <= _SANE_MARKET_BRIER_MAX)


def _write_report(fold_out, pooled, weights) -> Path:
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    credible = [f for f in fold_out if not _degraded(f)]
    beats_credible = [f["season"] for f in credible if f["market_brier"] - f["model_brier"] > 0]
    beats_any = [f["season"] for f in fold_out if f["market_brier"] - f["model_brier"] > 0]
    n_seasons = len(fold_out)
    if not beats_any:
        bottom = ("NO EDGE in any season — the cleaner version of the Epic 10 finding; the "
                  "totals Layer 3 architecture does not beat a credible market. Sit with this.")
    elif len(beats_credible) == len(credible) and credible and len(beats_any) == n_seasons:
        bottom = ("Combiner beats the market in ALL seasons on clean OOS data — the totals "
                  "pause conditions may already be met. Verify before acting.")
    elif 2026 not in beats_any and beats_any:
        bottom = (f"Combiner beats the market in {beats_any} but NOT 2026 — the regime-shift "
                  "story, now confirmed on honest (leakage-free) numbers.")
    else:
        bottom = f"Mixed: beats market in {beats_any}. See per-season detail."

    rows = ["| season | n | model Brier | market Brier | Δ (mkt−mdl) | over-rate | mkt quality | beats mkt |",
            "|---|---|---|---|---|---|---|---|"]
    for f in sorted(fold_out, key=lambda x: x["season"]):
        d = f["market_brier"] - f["model_brier"]
        deg = _degraded(f)
        rows.append(f"| {f['season']} | {f['n']} | {f['model_brier']:.4f} | {f['market_brier']:.4f} | "
                    f"{d:+.4f} | {f['over_rate']:.3f} | {'⚠️ degraded' if deg else 'credible'} | "
                    f"{'✅' if d > 0 else '❌'} |")
    d = pooled["market_brier"] - pooled["model_brier"]
    rows.append(f"| **pooled** | {pooled['n']} | **{pooled['model_brier']:.4f}** | "
                f"**{pooled['market_brier']:.4f}** | {d:+.4f} | — | — | {'✅' if d > 0 else '❌'} |")

    lines = [
        "# Totals (Epic 9 Stacking Combiner) — Leakage-Free Re-Evaluation (Phase 2c)",
        "",
        "_The Epic 9 pseudo-BMA stacking combiner (bullpen/offense/run_env → LTV "
        "(mu, sigma) → NB2 P(over)) evaluated on the leakage-free walk-forward matrix "
        "(`build_oos_matrix`). Per-signal mu→total_runs Poisson + NB2 sigma are fit "
        "walk-forward per fold (prior seasons only); weights from `stacking_weights.json`._",
        "",
        f"- Combiner weights (total_runs): "
        + ", ".join(f"{l}={weights[l]:.3f}" for l in sorted(weights)) + ".",
        f"- Market: de-vigged Bovada P(over) on games with a Bovada line + both prices; "
        f"non-push outcomes only. Gate: market Brier ≤ {_SANE_MARKET_BRIER_MAX:.3f} (looser than "
        f"h2h's 0.235 — totals are balanced-by-design so self-Brier ≈0.25 even when sharp).",
        "",
        "## Per-season head-to-head (model vs market, identical games)",
        "",
        *rows,
        "",
        "> **Season inclusion (user decision 2026-06-03):** the 2024-25 historical totals "
        "lines are credible (no quality cliff vs 2026, well-calibrated de-vigged P(over)), so "
        "all three seasons are reported. 2026 (Parlay API) is the single cleanest reference. "
        "Any season the gate flags ⚠️ degraded is excluded from the operational verdict.",
        "",
        "## Verdict",
        "",
        f"- Credible-baseline seasons: {[f['season'] for f in credible] or 'none'}; "
        f"model beats credible market in: **{beats_credible or 'none'}**.",
        f"- Model beats market in (all seasons reported): **{beats_any or 'none'}**.",
        f"- **Bottom line: {bottom}**",
        "",
        "_2026 is the most important single number (cleanest market + current season). "
        "2024-25 distinguish a 2026-specific regime problem from a broader signal-quality "
        "problem. Cross-ref [[project_epic10_totals_verdict]], [[project_layer3_signal_leakage]]._",
    ]
    _OUT_PATH.write_text("\n".join(lines) + "\n")
    return _OUT_PATH


def main() -> None:
    argparse.ArgumentParser(description="Leakage-free totals combiner re-eval (Phase 2c)").parse_args()
    print("Building leakage-free matrix + loading Bovada totals lines...")
    fold_out, pooled, weights = evaluate()
    print(f"weights: {weights}")
    for f in sorted(fold_out, key=lambda x: x["season"]):
        d = f["market_brier"] - f["model_brier"]
        print(f"  {f['season']}: n={f['n']:>4}  model={f['model_brier']:.4f}  market={f['market_brier']:.4f}  "
              f"Δ={d:+.4f}  over_rate={f['over_rate']:.3f}  μ̄={f['mean_combined_mu']:.2f}  "
              f"{'degraded' if _degraded(f) else 'credible'}  {'BEATS' if d > 0 else 'loses'}")
    dp = pooled["market_brier"] - pooled["model_brier"]
    print(f"  POOLED: n={pooled['n']}  model={pooled['model_brier']:.4f}  market={pooled['market_brier']:.4f}  "
          f"Δ={dp:+.4f}  {'BEATS' if dp > 0 else 'loses'}")
    out = _write_report(fold_out, pooled, weights)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
