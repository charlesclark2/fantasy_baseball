"""
Epic 16B, Story 16B.7 — Run-diff-derived H2H evaluation.

Tests whether the NGBoost Normal run_differential model (ngboost_tuned_2026.pkl)
can produce competitive H2H win probabilities by deriving P(home_win) = Φ(μ/σ)
from the run_diff posterior, then compares against the direct home_win XGBoost
champion (xgb_classifier_tuned_2026.pkl) and the 2026 Bovada market.

Runs IN PARALLEL with 16B.1–16B.3 (no training — inference + eval only).

Locked decision D4: run_differential = home_score − away_score.
  P(home_win) = P(run_diff > 0) = 1 − Normal.cdf(0; μ, σ) = Φ(μ/σ);
  μ > 0 ⇒ home favored.

Evaluation framework (H2H three-layer + Layer 4, per _eval_home_win in
evaluate_production_bayesian.py):
  Layer 1: log-loss vs Bernoulli base-rate (training home-win rate)
  Layer 2: ECE + calibration-in-the-large
  Layer 3: blended Brier vs prior-naive AND Bovada market (credible-market gate ≤0.235)
  Layer 4: selective strategy sweep (direction_flip + magnitude; gate: roi_devig)

Supplementary: run_diff intrinsic metrics (NLL, calib_80 on the actual
  run_differential target) show whether the underlying model is well-calibrated
  as a run-scoring predictor.

Output: ablation_results/run_diff_derived_h2h_16b7.md

Snowflake-heavy (load_features) ⇒ HAND-OFF run:
  uv run python betting_ml/scripts/leakage_fix/evaluate_run_diff_h2h.py
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

import joblib  # noqa: E402

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import load_features  # noqa: E402
from betting_ml.utils.preprocessing import build_imputation_pipeline  # noqa: E402
from betting_ml.scripts.train_h2h import logloss as _logloss, ece as _ece  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402
from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.scripts.load_layer3_features import load_devig_home_prob_bovada  # noqa: E402
from betting_ml.scripts.evaluation.bayesian_model_eval import (  # noqa: E402
    sweep_thresholds, layer4_verdict, evaluate_selective_strategy,
    sweep_table_markdown, MIN_BETS_RELIABLE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_MODELS = _PROJECT_ROOT / "betting_ml" / "models"
_BEST_ALPHA = _MODELS / "best_alpha.json"
_OUT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
    / "run_diff_derived_h2h_16b7.md"
)

_OOS_YEAR = 2026
_TRAIN_MAX_YEAR = 2025
_SANE_MARKET_BRIER_MAX = 0.235

# Artifacts (D4 locked 2026-06-04).
_RUN_DIFF_ART  = "run_differential/ngboost_tuned_2026.pkl"
_RUN_DIFF_COLS = "run_differential/feature_columns_ngboost_tuned_2026.json"
_HOME_WIN_ART  = "home_win/xgb_classifier_tuned_2026.pkl"
_HOME_WIN_COLS = "home_win/feature_columns_xgb_classifier_tuned_2026.json"


# ---------------------------------------------------------------------------
# Helpers (replicated from evaluate_production_bayesian to stay standalone)
# ---------------------------------------------------------------------------

def _load_model(artifact: str):
    path = _MODELS / artifact
    if path.exists():
        return joblib.load(path)
    from betting_ml.utils.artifact_store import load_artifact
    return load_artifact(f"s3://baseball-betting-ml-artifacts/{artifact}")


def _resolve_feature_cols(df_cols, cols_file: str) -> list[str]:
    """Load feature contract from sidecar JSON; fall back to df column list."""
    p = _MODELS / cols_file
    if p.exists():
        payload = json.loads(p.read_text())
        cols = payload["feature_cols"] if isinstance(payload, dict) else payload
        return [c for c in cols if c in df_cols]
    # Sidecar absent — use every numeric column not in df_cols
    return [c for c in df_cols if c not in {"game_pk", "game_year", "season",
                                             "home_win", "run_differential", "total_runs"}]


def _transform(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Impute df[feature_cols] and return numeric-only DataFrame (preserves index)."""
    available = [c for c in feature_cols if c in df.columns]
    pipe = build_imputation_pipeline()
    transformed = pipe.fit_transform(df[available])
    return transformed.select_dtypes(include=[np.number])


def _normal_discrete_nll(y, mu, sigma) -> float:
    """Discretized-PMF NLL for a Normal distribution (run_diff intrinsic L1)."""
    sigma = np.clip(sigma, 1e-6, None)
    pmf = norm.cdf((y + 0.5 - mu) / sigma) - norm.cdf((y - 0.5 - mu) / sigma)
    return float(-np.mean(np.log(np.clip(pmf, 1e-12, None))))


def _normal_calib_80(y, mu, sigma) -> float:
    """Central-80% interval coverage (run_diff intrinsic L2)."""
    sigma = np.clip(sigma, 1e-6, None)
    return float(np.mean(np.abs(y - mu) <= 1.2815515 * sigma))


def _blend(p: np.ndarray, mkt: np.ndarray, alpha: float) -> np.ndarray:
    return np.array([compute_posterior(float(a), float(b), alpha) for a, b in zip(p, mkt)])


# ---------------------------------------------------------------------------
# Model scoring
# ---------------------------------------------------------------------------

def _score_run_diff(df: pd.DataFrame) -> pd.DataFrame:
    """Inference-only: run_diff NGBoost → (μ, σ) → P(home_win) = Φ(μ/σ).

    D4: run_differential = home_score − away_score; P(run_diff > 0) = P(home_win).
    P(home_win) = 1 − Normal.cdf(0; μ, σ) = norm.sf(0, loc=μ, scale=σ).
    """
    feature_cols = _resolve_feature_cols(df.columns.tolist(), _RUN_DIFF_COLS)
    eval_mask = (df["game_year"] == _OOS_YEAR).to_numpy()
    Xt = _transform(df, feature_cols)
    model = _load_model(_RUN_DIFF_ART)
    pred = model.pred_dist(Xt.loc[eval_mask].values)
    mu = np.asarray(pred.params["loc"], dtype=float)
    sigma = np.clip(np.asarray(pred.params["scale"], dtype=float), 1e-6, None)
    p_home = norm.sf(0, loc=mu, scale=sigma)
    return pd.DataFrame({
        "game_pk": df.loc[eval_mask, "game_pk"].to_numpy(),
        "p_home": p_home,
        "mu": mu,
        "sigma": sigma,
    })


def _score_home_win_xgb(df: pd.DataFrame) -> pd.DataFrame:
    """Inference-only: home_win XGB champion → P(home_win)."""
    feature_cols = _resolve_feature_cols(df.columns.tolist(), _HOME_WIN_COLS)
    eval_mask = (df["game_year"] == _OOS_YEAR).to_numpy()
    Xt = _transform(df, feature_cols)
    model = _load_model(_HOME_WIN_ART)
    Xe = Xt.loc[eval_mask]
    names = [str(f) for f in model.xgb_classifier.feature_names_in_]
    Xe = Xe.reindex(columns=names, fill_value=0.0)
    proba = model.predict_proba(Xe)
    p = np.asarray(proba)[:, 1] if np.ndim(proba) == 2 else np.asarray(proba, dtype=float)
    return pd.DataFrame({
        "game_pk": df.loc[eval_mask, "game_pk"].to_numpy(),
        "p_home": p.astype(float),
    })


# ---------------------------------------------------------------------------
# Three-layer H2H evaluation
# ---------------------------------------------------------------------------

def _eval_h2h_model(
    label: str,
    p_home: np.ndarray,
    y: np.ndarray,
    mkt_p: np.ndarray,
    cov: np.ndarray,
    base_rate: float,
    prior_nll: float,
    prior_naive_brier: float,
    market_brier: float,
    alpha: float,
) -> dict:
    """Three-layer H2H evaluation for one model that outputs P(home_win).

    Mirrors _eval_home_win in evaluate_production_bayesian.py: L1 log-loss,
    L2 ECE + calib-in-large, L3 blended Brier vs prior-naive + market, L4 sweep.
    """
    blended = (
        _blend(p_home[cov], mkt_p[cov], alpha) if cov.any() else np.array([])
    )
    rec: dict = {
        "label": label,
        "nll": _logloss(p_home, y),
        "ece": _ece(p_home, y),
        "calib_in_large": float(p_home.mean() - y.mean()),
        "brier_model": brier_score(p_home[cov], y[cov]) if cov.any() else float("nan"),
        "blended_brier": brier_score(blended, y[cov]) if cov.any() else float("nan"),
        "mean_p": float(p_home.mean()),
        "prior_nll": prior_nll,
        "prior_naive_brier": prior_naive_brier,
        "market_brier": market_brier,
    }
    if cov.any():
        games4 = pd.DataFrame({
            "market": "h2h",
            "model_p_home": p_home[cov],
            "market_p_home": mkt_p[cov],
            "home_win": y[cov],
        })
        sweep = sweep_thresholds(games4)
        rec["layer4"] = {
            "sweep": sweep,
            "verdict": layer4_verdict(sweep),
            "default": evaluate_selective_strategy(games4),
        }
    return rec


def _run_diff_intrinsic(df: pd.DataFrame, scored_rd: pd.DataFrame) -> dict:
    """Supplementary: run_diff model intrinsic quality (NLL, calib_80 on run_differential)."""
    base = (
        df[df["game_year"] == _OOS_YEAR][["game_pk", "run_differential"]]
        .dropna(subset=["run_differential"])
        .copy()
    )
    train_y = (
        df.loc[df["game_year"] <= _TRAIN_MAX_YEAR, "run_differential"]
        .dropna()
        .to_numpy(float)
    )
    mu0 = float(np.mean(train_y))
    sig0 = float(np.std(train_y, ddof=1))

    pk_set = set(base["game_pk"]) & set(scored_rd["game_pk"])
    base = base[base["game_pk"].isin(pk_set)].reset_index(drop=True)
    m = scored_rd[scored_rd["game_pk"].isin(pk_set)].set_index("game_pk").loc[base["game_pk"]]
    y = base["run_differential"].to_numpy(float)
    mu = m["mu"].to_numpy(float)
    sigma = m["sigma"].to_numpy(float)

    prior_nll = _normal_discrete_nll(y, np.full(len(y), mu0), np.full(len(y), sig0))
    return {
        "n": len(base),
        "prior_nll": prior_nll,
        "prior_desc": f"Normal(μ={mu0:.3f}, σ={sig0:.3f})",
        "model_nll": _normal_discrete_nll(y, mu, sigma),
        "model_calib_80": _normal_calib_80(y, mu, sigma),
        "mean_mu": float(mu.mean()),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _b(x) -> str:
    return "✅" if x else "❌"


def _write_report(
    rd_rec: dict,
    hw_rec: dict,
    intrinsic: dict,
    base_rate: float,
    market_brier: float,
    market_credible: bool,
    n_market: int,
    alpha: float,
) -> Path:
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    prior_nll       = rd_rec["prior_nll"]
    prior_naive_b   = rd_rec["prior_naive_brier"]

    # At alpha=0 the blended posterior collapses to the market exactly:
    # compute_posterior(p, mkt, 0.0) = mkt. So:
    #   blended_brier = market_brier  (always)
    #   L3 Brier(blended) < market   = always False (trivially)
    #   L3 Brier(blended) < prior-naive = market_brier < prior_naive (market vs naive, not model)
    # The meaningful L3 gate at alpha=0 is raw model Brier < market Brier.
    alpha_degenerate = (alpha == 0.0)

    def _l1(r):    return r["nll"] < r["prior_nll"]
    def _l3n(r):   return r["blended_brier"] < r["prior_naive_brier"]
    def _l3m_raw(r): return r["brier_model"] < r["market_brier"]  # honest at alpha=0
    def _l4(r):    return r.get("layer4", {}).get("verdict", {}).get("passed", False)

    alpha_note = (
        f"⚠️ alpha={alpha:.2f}: blended posterior = market exactly "
        f"(compute_posterior(p, mkt, 0) = mkt). "
        f"Brier(blended) = market_brier for all games — "
        f"L3-vs-market gate uses **raw model Brier** instead."
        if alpha_degenerate else ""
    )

    lines = [
        "# 16B.7 — Run-Diff-Derived H2H Evaluation",
        "",
        "_Epic 16B, Story 16B.7 (parallel, no training). Tests whether the NGBoost Normal "
        "`run_differential` posterior (μ, σ) → P(home_win) = Φ(μ/σ) can match or beat the "
        "direct `home_win` XGBoost champion (xgb_classifier_tuned_2026.pkl) and the 2026 "
        "Bovada market._",
        "",
        f"- **D4 sign convention (locked 2026-06-04):** run_differential = home_score − "
        f"away_score; P(home_win) = 1 − Normal.cdf(0; μ, σ) = Φ(μ/σ); μ > 0 ⇒ home favored.",
        f"- **OOS set:** {rd_rec.get('n', '?')} games (2026 fold; trained 2021–25 → genuine OOS).",
        f"- **Market gate:** Bovada de-vigged P(home win); ≤{_SANE_MARKET_BRIER_MAX} = credible; "
        f"n_market = {n_market}.",
        f"- **Market Brier (2026):** {market_brier:.4f} "
        f"({'credible ✅' if market_credible else '⚠️ DEGRADED — below-gate Brier'}).",
        f"- **Layer 1 prior:** Bernoulli base-rate {base_rate:.3f} → log-loss "
        f"{prior_nll:.4f} (must beat).",
        f"- **L3 baselines:** prior-naive Brier {prior_naive_b:.4f} · market Brier "
        f"{market_brier:.4f}.",
        *(([f"- **Alpha note:** {alpha_note}"] if alpha_degenerate else [])),
        "",
        "## Three-Layer H2H Metrics",
        "",
        "| Metric | run_diff_derived | home_win_champion |",
        "|---|---:|---:|",
        f"| L1 log-loss | {rd_rec['nll']:.4f} | {hw_rec['nll']:.4f} |",
        f"| L2 ECE | {rd_rec['ece']:.4f} | {hw_rec['ece']:.4f} |",
        f"| L2 calib-in-large | {rd_rec['calib_in_large']:+.4f} | {hw_rec['calib_in_large']:+.4f} |",
        f"| L3 Brier(blended) | {rd_rec['blended_brier']:.4f} | {hw_rec['blended_brier']:.4f} |",
        f"| Brier(model raw) | {rd_rec['brier_model']:.4f} | {hw_rec['brier_model']:.4f} |",
        f"| mean P(home) | {rd_rec['mean_p']:.4f} | {hw_rec['mean_p']:.4f} |",
        "",
        "## Gates",
        "",
        f"| Gate | run_diff_derived | home_win_champion |",
        "|---|:---:|:---:|",
        f"| L1 log-loss < prior | {_b(_l1(rd_rec))} | {_b(_l1(hw_rec))} |",
        f"| L3 raw Brier < market{'*' if alpha_degenerate else ''} | "
        f"{_b(_l3m_raw(rd_rec))} | {_b(_l3m_raw(hw_rec))} |",
        f"| L3 Brier(blended) < prior-naive | {_b(_l3n(rd_rec))} | {_b(_l3n(hw_rec))} |",
        f"| Market credible (≤{_SANE_MARKET_BRIER_MAX}) | {_b(market_credible)} | {_b(market_credible)} |",
        f"| L4 roi_devig>0 & n≥{MIN_BETS_RELIABLE} | {_b(_l4(rd_rec))} | {_b(_l4(hw_rec))} |",
        *(([f"", f"_* alpha={alpha:.2f} → blended=market; raw Brier < market is the honest "
            f"L3 test (blended=market makes Brier(blended)<market trivially False)._"]
          if alpha_degenerate else [])),
        "",
        "**Head-to-head (run_diff_derived vs home_win_champion):**",
        f"- NLL: {rd_rec['nll']:.4f} vs {hw_rec['nll']:.4f} "
        f"({'run_diff wins ✅' if rd_rec['nll'] < hw_rec['nll'] else 'home_win wins ❌'})",
        f"- Brier(raw): {rd_rec['brier_model']:.4f} vs {hw_rec['brier_model']:.4f} "
        f"({'run_diff wins ✅' if rd_rec['brier_model'] < hw_rec['brier_model'] else 'home_win wins ❌'})",
        f"- ECE: {rd_rec['ece']:.4f} vs {hw_rec['ece']:.4f} "
        f"({'run_diff wins ✅' if rd_rec['ece'] < hw_rec['ece'] else 'home_win wins ❌'})",
        "",
    ]

    # Layer 4 sections.
    for label, rec in [("run_diff_derived", rd_rec), ("home_win_champion", hw_rec)]:
        if "layer4" not in rec:
            lines += [f"## Layer 4 — {label}", "", "_No market-covered games for Layer 4._", ""]
            continue
        l4 = rec["layer4"]
        v = l4["verdict"]
        d = l4["default"]
        lines += [
            f"## Layer 4 — {label}",
            "",
            "_Gate metric: roi_devig (de-vigged fair-odds ROI; vig-free upper bound). "
            f"Gate: roi_devig > 0 AND n_bets ≥ {MIN_BETS_RELIABLE}._",
            "",
        ] + sweep_table_markdown(l4["sweep"]) + [""]
        if v["passed"]:
            lines += [
                f"- **Verdict: ✅ PASS** — optimal h2h_threshold={v['optimal_h2h_threshold']:.2f}: "
                f"n_bets={v['n_bets']}, win_rate={v['win_rate']:.3f}, "
                f"roi_devig={v['roi_devig']:+.4f}.",
                "",
            ]
        else:
            lines += [
                f"- **Verdict: ❌ FAIL** — no threshold with roi_devig > 0 "
                f"AND n_bets ≥ {MIN_BETS_RELIABLE}.",
                "",
            ]
        if "h2h" in d:
            hb = d["h2h"]
            nb = d["no_bet"]
            lines += [
                f"- @default h2h_threshold=0.12 — "
                f"direction_flip: n={hb['direction_flip']['n_bets']} "
                f"roi_110={hb['direction_flip']['roi_110']:+.4f} "
                f"roi_devig={hb['direction_flip']['roi_devig']:+.4f} · "
                f"magnitude: n={hb['magnitude']['n_bets']} "
                f"roi_110={hb['magnitude']['roi_110']:+.4f} "
                f"roi_devig={hb['magnitude']['roi_devig']:+.4f}.",
                f"- No-bet (n={nb['n']}): model Brier "
                f"{nb.get('h2h_model_brier', float('nan')):.4f} vs market "
                f"{nb.get('h2h_market_brier', float('nan')):.4f}.",
                "",
            ]

    # Supplementary run_diff intrinsic.
    lines += [
        "## Supplementary — Run-Diff Model Intrinsic Quality",
        "",
        "_How well the NGBoost Normal model predicts `run_differential` itself "
        "(not derived P(home_win)). L1 uses discretized-PMF NLL; L2 uses calib_80 "
        "(central-80% interval coverage, gate [0.75, 0.85])._",
        "",
        f"- Prior: {intrinsic['prior_desc']} → NLL {intrinsic['prior_nll']:.4f}",
        f"- Model NLL (PMF): **{intrinsic['model_nll']:.4f}** "
        f"({'beats prior ✅' if intrinsic['model_nll'] < intrinsic['prior_nll'] else 'fails prior ❌'})",
        f"- Model calib_80: **{intrinsic['model_calib_80']:.3f}** "
        f"(gate [0.75, 0.85]: "
        f"{'✅' if 0.75 <= intrinsic['model_calib_80'] <= 0.85 else '❌'})",
        f"- Mean predicted μ: {intrinsic['mean_mu']:.3f}  (n={intrinsic['n']})",
        "",
        "## Verdict",
        "",
    ]

    # Verdict.
    rd_l1 = _l1(rd_rec)
    rd_l3n = _l3n(rd_rec)
    rd_l3m = _l3m_raw(rd_rec)   # raw Brier < market (honest at alpha=0)
    rd_beats_nll = rd_rec["nll"] < hw_rec["nll"]
    rd_beats_brier = rd_rec["brier_model"] < hw_rec["brier_model"]

    if rd_l1 and rd_l3n and _l3m_raw(rd_rec) and market_credible:
        posture = (
            "**CHANGES H2H POSTURE** — run_diff-derived P(home_win) clears all three layers "
            "on a credible market. Warrants further investigation before 16B.6/Epic 17 gates."
        )
    elif not market_credible:
        posture = (
            "**INCONCLUSIVE** — market Brier exceeds credible-market gate; "
            "L3-vs-market result is an artifact of degraded lines, not model skill."
        )
    elif rd_l1 and not _l3m_raw(rd_rec):
        posture = (
            "**NO CHANGE** — run_diff-derived P(home_win) is informative (beats Bernoulli prior) "
            "but does NOT beat the 2026 Bovada market on L3 Brier. "
            "Consistent with Epic 11 finding: no H2H edge against a sharp market."
        )
    elif not rd_l1:
        posture = (
            "**NO CHANGE** — run_diff-derived P(home_win) fails L1 (worse than Bernoulli "
            "base-rate). The run_diff posterior does not translate to a useful win probability."
        )
    else:
        posture = (
            "**INCONCLUSIVE** — passes some layers but not the full gate set. "
            "Review the per-layer table above."
        )

    vs_champion = (
        f"run_diff_derived {'beats' if rd_beats_nll and rd_beats_brier else 'loses to'} "
        f"home_win_champion on NLL+Brier"
        if (rd_beats_nll == rd_beats_brier)
        else f"run_diff_derived wins NLL {'but' if not rd_beats_brier else 'and'} "
             f"{'loses' if not rd_beats_brier else 'wins'} Brier vs home_win_champion"
    )

    lines += [
        f"- **vs champion (xgb_classifier_tuned_2026):** {vs_champion} "
        f"(NLL {rd_rec['nll']:.4f} vs {hw_rec['nll']:.4f}; "
        f"Brier {rd_rec['brier_model']:.4f} vs {hw_rec['brier_model']:.4f}).",
        f"- **vs 2026 Bovada market (Brier {market_brier:.4f}):** "
        f"run_diff_derived {'closes the gap (' if rd_rec['brier_model'] <= hw_rec['brier_model'] else 'does NOT close the gap ('}"
        f"rd={rd_rec['brier_model']:.4f} hw={hw_rec['brier_model']:.4f} mkt={market_brier:.4f}).",
        f"- **16B.7 verdict: {posture}**",
        "",
    ]

    _OUT_PATH.write_text("\n".join(lines) + "\n")
    return _OUT_PATH


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="16B.7 — run_diff-derived H2H eval (no training, inference + eval only)"
    )
    ap.add_argument("--env", default="prod")
    args = ap.parse_args()

    log.info("Loading full feature matrix (Snowflake — may take 1-2 min)...")
    df = load_features(min_games_played=15)
    df["game_pk"] = df["game_pk"].astype(int)
    log.info("  loaded: %d rows × %d cols", *df.shape)

    # Training base-rate (Bernoulli prior predictive).
    train_mask = df["game_year"] <= _TRAIN_MAX_YEAR
    base_rate = float(df.loc[train_mask, "home_win"].astype(float).mean())
    log.info("  base_rate=%.4f", base_rate)

    # Score both models on the 2026 eval fold.
    log.info("Scoring run_diff NGBoost (ngboost_tuned_2026.pkl)...")
    scored_rd = _score_run_diff(df)
    log.info("  run_diff scored: %d 2026 games", len(scored_rd))

    log.info("Scoring home_win XGB (xgb_classifier_tuned_2026.pkl)...")
    scored_hw = _score_home_win_xgb(df)
    log.info("  home_win scored: %d 2026 games", len(scored_hw))

    # Align on settled 2026 outcomes ∩ both scored sets.
    base = (
        df[df["game_year"] == _OOS_YEAR][["game_pk", "home_win"]]
        .dropna(subset=["home_win"])
        .copy()
    )
    pk_set = set(base["game_pk"]) & set(scored_rd["game_pk"]) & set(scored_hw["game_pk"])
    base = base[base["game_pk"].isin(pk_set)].reset_index(drop=True)
    y = base["home_win"].to_numpy(float)
    p_rd = scored_rd.set_index("game_pk").loc[base["game_pk"], "p_home"].to_numpy(float)
    p_hw = scored_hw.set_index("game_pk").loc[base["game_pk"], "p_home"].to_numpy(float)
    log.info("  aligned eval set: %d games", len(base))

    # Market probs.
    log.info("Loading Bovada de-vigged home win probs...")
    mkt = load_devig_home_prob_bovada(base["game_pk"].tolist(), env=args.env)
    mkt_by_pk = {
        int(pk): float(v) for pk, v in
        zip(mkt["game_pk"], mkt["bovada_devig_home_prob"])
        if pd.notna(v)
    }
    cov = base["game_pk"].map(lambda pk: int(pk) in mkt_by_pk).to_numpy()
    mkt_p = base["game_pk"].map(lambda pk: mkt_by_pk.get(int(pk), np.nan)).to_numpy(float)
    n_market = int(cov.sum())
    log.info("  market coverage: %d/%d", n_market, len(base))

    market_brier = brier_score(mkt_p[cov], y[cov]) if cov.any() else float("nan")
    market_credible = bool(market_brier <= _SANE_MARKET_BRIER_MAX)
    prior_naive_brier = (
        brier_score(np.full(int(cov.sum()), base_rate), y[cov])
        if cov.any() else float("nan")
    )
    alpha = float(json.loads(_BEST_ALPHA.read_text()).get("best_alpha", 0.0))
    prior_nll = float(_logloss(np.full(len(y), base_rate), y))

    log.info(
        "  market_brier=%.4f (%s)  prior_naive_brier=%.4f  prior_nll=%.4f  alpha=%.2f",
        market_brier,
        "credible" if market_credible else "DEGRADED",
        prior_naive_brier,
        prior_nll,
        alpha,
    )

    # Three-layer H2H evaluation.
    log.info("Evaluating three-layer H2H metrics for both models...")
    rd_rec = _eval_h2h_model(
        "run_diff_derived", p_rd, y, mkt_p, cov,
        base_rate, prior_nll, prior_naive_brier, market_brier, alpha,
    )
    rd_rec["n"] = len(base)
    hw_rec = _eval_h2h_model(
        "home_win_champion", p_hw, y, mkt_p, cov,
        base_rate, prior_nll, prior_naive_brier, market_brier, alpha,
    )

    # Run_diff intrinsic metrics.
    log.info("Computing run_diff intrinsic quality metrics...")
    intrinsic = _run_diff_intrinsic(df, scored_rd)

    # Console summary.
    log.info("\n=== 16B.7 RESULTS ===")
    for label, rec in [("run_diff_derived", rd_rec), ("home_win_champion", hw_rec)]:
        log.info(
            "  %-22s  NLL=%.4f  ECE=%.4f  Brier(raw)=%.4f  Brier(blended)=%.4f",
            label, rec["nll"], rec["ece"], rec["brier_model"], rec["blended_brier"],
        )
    log.info("  market Brier=%.4f (%s)", market_brier, "credible" if market_credible else "DEGRADED")
    log.info("  prior NLL=%.4f  prior-naive Brier=%.4f", prior_nll, prior_naive_brier)
    log.info(
        "  run_diff intrinsic: NLL=%.4f (prior=%.4f)  calib_80=%.3f",
        intrinsic["model_nll"], intrinsic["prior_nll"], intrinsic["model_calib_80"],
    )
    for label, rec in [("run_diff_derived", rd_rec), ("home_win_champion", hw_rec)]:
        v = rec.get("layer4", {}).get("verdict", {})
        log.info("  L4 %-22s  %s", label, "PASS" if v.get("passed") else "FAIL")

    out = _write_report(rd_rec, hw_rec, intrinsic, base_rate, market_brier,
                        market_credible, n_market, alpha)
    log.info("Report written to %s", out)


if __name__ == "__main__":
    main()
