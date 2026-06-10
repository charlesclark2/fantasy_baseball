"""
h2h_ensemble_eval.py — Story 28.2: run_diff × classifier ensemble + disagreement gate.

Epic 28, Story 28.2. Eval-only — no training, no retrain.

Goal: test the ensemble of two genuinely-independent H2H estimators:
  - p_classifier : from oos_predictions_h2h_v2.parquet (leakage-free walk-forward OOS)
  - p_run_diff   : Φ(μ/σ) from the NGBoost run_diff model (16B.7 methodology)

Sweep mix weight w ∈ {0, 0.25, 0.5, 0.75, 1.0}:
  p_ensemble(w) = w * p_classifier + (1 - w) * p_run_diff

Three-layer eval per w:
  L1: NLL vs Bernoulli(base_rate)
  L2: ECE + calib-in-large
  L3: raw Brier vs market (credible gate ≤ 0.235; 2026 Bovada Brier = 0.182)

Disagreement gate (conviction filter):
  For each cap d ∈ {0.02, 0.05, 0.08, 0.10, 0.15, 0.20}:
    Keep games where |p_classifier − p_run_diff| ≤ d ("both models agree")
    Run bayesian_model_eval.normalize_h2h_frame + sweep_thresholds on best-w ensemble
  Adopt as conviction filter if it tightens the magnitude subset Brier.

HAND-OFF: scoring the run_diff NGBoost model requires loading the full feature
matrix from Snowflake (>1 min). Run the whole script as:

    uv run python betting_ml/scripts/h2h_ensemble_eval.py

On subsequent runs, skip Snowflake by passing the cached run_diff parquet:

    uv run python betting_ml/scripts/h2h_ensemble_eval.py \\
        --run-diff-parquet betting_ml/models/layer3/run_diff_derived_h2h_2026.parquet

Output:
    quant_sports_intel_models/baseball/ablation_results/h2h_ensemble_eval_28_2.md
    betting_ml/models/layer3/run_diff_derived_h2h_{oos_year}.parquet  (cached on first run)
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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.train_h2h import logloss as _logloss, ece as _ece  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402
from betting_ml.scripts.evaluation.bayesian_model_eval import (  # noqa: E402
    normalize_h2h_frame, sweep_thresholds, layer4_verdict,
    evaluate_selective_strategy, sweep_table_markdown, MIN_BETS_RELIABLE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_MODELS = _PROJECT_ROOT / "betting_ml" / "models"
_BEST_ALPHA = _MODELS / "best_alpha.json"

_H2H_PARQUET_DEFAULT = _MODELS / "layer3" / "oos_predictions_h2h_v2.parquet"
_OUT_PATH = (
    _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results"
    / "h2h_ensemble_eval_28_2.md"
)

_OOS_YEAR = 2026
_SANE_MARKET_BRIER_MAX = 0.235

# Artifacts (locked from 16B.7 / D4).
_RUN_DIFF_ART  = "run_differential/ngboost_tuned_2026.pkl"
_RUN_DIFF_COLS = "run_differential/feature_columns_ngboost_tuned_2026.json"

MIX_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
# Disagreement caps: keep games where |p_clf - p_rd| <= d (ascending = more inclusive)
DISAGREE_CAPS = (0.02, 0.05, 0.08, 0.10, 0.15, 0.20)


# ---------------------------------------------------------------------------
# Run_diff model scoring (reuses 16B.7 methodology — no training)
# ---------------------------------------------------------------------------

def _load_model(artifact: str):
    path = _MODELS / artifact
    if path.exists():
        return __import__("joblib").load(path)
    from betting_ml.utils.artifact_store import load_artifact
    return load_artifact(f"s3://baseball-betting-ml-artifacts/{artifact}")


def _resolve_feature_cols(df_cols: list[str], cols_file: str) -> list[str]:
    p = _MODELS / cols_file
    if p.exists():
        payload = json.loads(p.read_text())
        cols = payload["feature_cols"] if isinstance(payload, dict) else payload
        return [c for c in cols if c in df_cols]
    return [c for c in df_cols if c not in {
        "game_pk", "game_year", "season", "home_win", "run_differential", "total_runs"
    }]


def _transform(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    from betting_ml.utils.preprocessing import build_imputation_pipeline
    available = [c for c in feature_cols if c in df.columns]
    pipe = build_imputation_pipeline()
    transformed = pipe.fit_transform(df[available])
    return transformed.select_dtypes(include=[np.number])


def _score_run_diff_from_features(df: pd.DataFrame) -> pd.DataFrame:
    """Score NGBoost run_diff model on OOS year → P(home_win) = Φ(μ/σ).

    D4 sign convention: run_differential = home_score − away_score;
    P(home_win) = P(run_diff > 0) = norm.sf(0, loc=μ, scale=σ).
    """
    feature_cols = _resolve_feature_cols(df.columns.tolist(), _RUN_DIFF_COLS)
    eval_mask = (df["game_year"] == _OOS_YEAR).to_numpy()
    log.info("  run_diff eval fold: %d rows", eval_mask.sum())
    Xt = _transform(df, feature_cols)
    model = _load_model(_RUN_DIFF_ART)
    pred = model.pred_dist(Xt.loc[eval_mask].values)
    mu    = np.asarray(pred.params["loc"],   dtype=float)
    sigma = np.clip(np.asarray(pred.params["scale"], dtype=float), 1e-6, None)
    p_home = norm.sf(0, loc=mu, scale=sigma)
    return pd.DataFrame({
        "game_pk": df.loc[eval_mask, "game_pk"].to_numpy(),
        "p_run_diff": p_home,
        "run_diff_mu": mu,
        "run_diff_sigma": sigma,
    })


def _get_run_diff_probs(args) -> pd.DataFrame:
    """Return DataFrame[game_pk, p_run_diff] for the OOS year.

    If --run-diff-parquet is provided and exists, read it directly (fast).
    Otherwise load features from Snowflake and score the model (slow, >1 min).
    Saves a cached parquet automatically for future use.
    """
    cache_path = _MODELS / "layer3" / f"run_diff_derived_h2h_{_OOS_YEAR}.parquet"

    if args.run_diff_parquet and Path(args.run_diff_parquet).exists():
        log.info("Loading cached run_diff probs from %s", args.run_diff_parquet)
        rd = pd.read_parquet(args.run_diff_parquet)
        log.info("  %d rows", len(rd))
        return rd[["game_pk", "p_run_diff"]]

    log.info("No cached run_diff parquet found; loading features from Snowflake (>1 min)...")
    from betting_ml.utils.data_loader import load_features
    df = load_features(min_games_played=15)
    df["game_pk"] = df["game_pk"].astype(int)
    log.info("  feature matrix loaded: %d rows × %d cols", *df.shape)

    log.info("Scoring run_diff NGBoost model...")
    rd = _score_run_diff_from_features(df)
    log.info("  scored %d OOS games", len(rd))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    rd.to_parquet(cache_path, index=False)
    log.info("  cached to %s (use --run-diff-parquet to skip Snowflake next run)", cache_path)

    return rd[["game_pk", "p_run_diff"]]


# ---------------------------------------------------------------------------
# Three-layer metrics
# ---------------------------------------------------------------------------

def _three_layer(
    label: str,
    p_home: np.ndarray,
    y: np.ndarray,
    mkt_p: np.ndarray,
    base_rate: float,
) -> dict:
    """L1 NLL, L2 ECE + calib_in_large, L3 raw Brier vs market."""
    prior_nll    = _logloss(np.full(len(y), base_rate), y)
    nll          = _logloss(p_home, y)
    ece          = _ece(p_home, y)
    calib_large  = float(p_home.mean() - y.mean())

    ok = ~np.isnan(mkt_p)
    model_brier  = brier_score(p_home[ok], y[ok]) if ok.any() else float("nan")
    market_brier = brier_score(mkt_p[ok],  y[ok]) if ok.any() else float("nan")

    return {
        "label":         label,
        "n":             int(len(y)),
        "n_market":      int(ok.sum()),
        "base_rate":     base_rate,
        "prior_nll":     prior_nll,
        "nll":           nll,
        "nll_beats_prior": bool(nll < prior_nll),
        "ece":           ece,
        "calib_in_large": calib_large,
        "model_brier":   model_brier,
        "market_brier":  market_brier,
        "brier_beats_market": bool(model_brier < market_brier) if np.isfinite(model_brier) else False,
        "market_credible": bool(market_brier <= _SANE_MARKET_BRIER_MAX) if np.isfinite(market_brier) else False,
    }


# ---------------------------------------------------------------------------
# Disagreement-gate analysis
# ---------------------------------------------------------------------------

def _disagree_gate_analysis(
    df: pd.DataFrame,
    best_w: float,
    base_rate: float,
) -> list[dict]:
    """For each disagreement cap d, keep games where |p_clf - p_rd| ≤ d.

    Reports: n_games_kept, n_bets, roi_devig, model_brier, market_brier
    for the best-w ensemble on that subset.
    """
    rows = []
    all_n = len(df)
    for d in DISAGREE_CAPS:
        sub = df[df["disagree"] <= d].copy()
        if len(sub) < MIN_BETS_RELIABLE:
            rows.append({
                "disagree_cap": d,
                "n_kept": int(len(sub)),
                "pct_kept": len(sub) / all_n if all_n else float("nan"),
                "n_bets": 0,
                "roi_devig": float("nan"),
                "model_brier": float("nan"),
                "market_brier": float("nan"),
                "brier_beats_market": False,
                "note": "too few games",
            })
            continue

        p_ens = sub["p_ens"].to_numpy(float)
        y     = sub["home_win"].to_numpy(float)
        mkt   = sub["market_devig_home"].to_numpy(float)

        ok = ~np.isnan(mkt)
        model_brier  = brier_score(p_ens[ok], y[ok]) if ok.any() else float("nan")
        market_brier = brier_score(mkt[ok],   y[ok]) if ok.any() else float("nan")

        games4 = normalize_h2h_frame(
            pd.DataFrame({
                "game_pk":          sub["game_pk"].to_numpy(),
                "model_p_home_win": p_ens,
                "market_devig_home": mkt,
                "home_win":         y,
            })
        )
        sw  = sweep_thresholds(games4)
        vrd = layer4_verdict(sw)
        rows.append({
            "disagree_cap":     d,
            "n_kept":           int(len(sub)),
            "pct_kept":         len(sub) / all_n if all_n else float("nan"),
            "n_bets":           vrd["n_bets"] or 0,
            "roi_devig":        vrd["roi_devig"],
            "model_brier":      model_brier,
            "market_brier":     market_brier,
            "brier_beats_market": bool(model_brier < market_brier) if np.isfinite(model_brier) else False,
            "optimal_h2h_thr":  vrd["optimal_h2h_threshold"],
        })
    return rows


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _fmt(x, fmt=".4f") -> str:
    return f"{x:{fmt}}" if pd.notna(x) and np.isfinite(float(x)) else "—"


def _b(flag: bool) -> str:
    return "✅" if flag else "❌"


def _write_report(
    recs: list[dict],
    disagree_rows: list[dict],
    all_df: pd.DataFrame,
    best_w: float,
    base_rate: float,
    market_brier: float,
    n_ensemble: int,
) -> None:
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 28.2 — run_diff × Classifier Ensemble + Disagreement Gate",
        "",
        "_Epic 28, Story 28.2. Eval-only (no retrain). "
        "Tests the ensemble of two genuinely-independent H2H estimators "
        "and `|p_classifier − p_run_diff|` as a conviction filter._",
        "",
        f"- **OOS year:** {_OOS_YEAR}",
        f"- **n_ensemble:** {n_ensemble} games (classifier ∩ run_diff ∩ market coverage)",
        f"- **Base rate (train ≤{_OOS_YEAR - 1}):** {base_rate:.4f}  "
        f"→ prior NLL {float(_logloss(np.full(1, base_rate), np.array([base_rate]))):.4f}",
        f"- **Market Brier (2026 Bovada):** {market_brier:.4f} "
        f"({'credible ✅' if market_brier <= _SANE_MARKET_BRIER_MAX else '⚠️ DEGRADED'})",
        f"- **Mix weights swept:** w ∈ {{0=pure_run_diff, 0.25, 0.50, 0.75, 1.0=pure_classifier}}",
        "",
        "---",
        "",
        "## Three-Layer Summary per Mix Weight",
        "",
        "| w (classifier weight) | L1 NLL | beats prior? | L2 ECE | calib_large | "
        "L3 model Brier | vs market | best_w? |",
        "|---:|---:|:---:|---:|---:|---:|:---:|:---:|",
    ]

    for r in recs:
        w_label = (
            "0 (pure run_diff)" if r["label"] == "w=0.00" else
            "1 (pure classifier)" if r["label"] == "w=1.00" else
            r["label"]
        )
        best_mark = " ⭐" if abs(float(r["label"].replace("w=", "")) - best_w) < 1e-6 else ""
        lines.append(
            f"| {w_label}{best_mark} "
            f"| {_fmt(r['nll'])} "
            f"| {_b(r['nll_beats_prior'])} "
            f"| {_fmt(r['ece'])} "
            f"| {_fmt(r['calib_in_large'], '+.4f')} "
            f"| {_fmt(r['model_brier'])} "
            f"| {_b(r['brier_beats_market'])} "
            f"| {_b(abs(float(r['label'].replace('w=','')) - best_w) < 1e-6)} |"
        )

    lines += [
        "",
        f"_Best w = **{best_w:.2f}** (lowest model Brier on market-covered games)._",
        "",
        "---",
        "",
        "## Layer 4 Threshold Sweep — Best Ensemble (w={:.2f})".format(best_w),
        "",
    ]

    # Find the best-w record and add its Layer 4 sweep.
    best_rec = next(r for r in recs if abs(float(r["label"].replace("w=","")) - best_w) < 1e-6)
    if "layer4" in best_rec:
        l4 = best_rec["layer4"]
        lines += sweep_table_markdown(l4["sweep"]) + [""]
        v = l4["verdict"]
        if v["passed"]:
            lines += [
                f"- **Layer 4: ✅ PASS** (gate=roi_devig) — "
                f"h2h_thr={v['optimal_h2h_threshold']:.2f}: "
                f"n_bets={v['n_bets']}, win_rate={v['win_rate']:.3f}, "
                f"roi_devig={v['roi_devig']:+.4f}.",
                "",
            ]
        else:
            lines += [
                f"- **Layer 4: ❌ FAIL** — no h2h_threshold with roi_devig>0 "
                f"AND n_bets≥{MIN_BETS_RELIABLE}.",
                "",
            ]
        if "h2h" in l4.get("default", {}):
            hb = l4["default"]["h2h"]
            nb = l4["default"]["no_bet"]
            lines += [
                "**@default h2h_threshold=0.12:**",
                f"- direction_flip: n={hb['direction_flip']['n_bets']} "
                f"roi_110={_fmt(hb['direction_flip']['roi_110'], '+.4f')} "
                f"roi_devig={_fmt(hb['direction_flip']['roi_devig'], '+.4f')}",
                f"- magnitude:      n={hb['magnitude']['n_bets']} "
                f"roi_110={_fmt(hb['magnitude']['roi_110'], '+.4f')} "
                f"roi_devig={_fmt(hb['magnitude']['roi_devig'], '+.4f')}",
                f"- no-bet (n={nb.get('h2h_n', nb['n'])}): model Brier "
                f"{_fmt(nb.get('h2h_model_brier', float('nan')))} vs market "
                f"{_fmt(nb.get('h2h_market_brier', float('nan')))}",
                "",
            ]
    else:
        lines += ["_No market-covered games for Layer 4._", ""]

    # Per-weight Layer 4 sweep tables (all weights).
    lines += [
        "---",
        "",
        "## Layer 4 Sweep — All Mix Weights",
        "",
    ]
    for r in recs:
        if "layer4" not in r:
            continue
        l4 = r["layer4"]
        v  = l4["verdict"]
        lines += [
            f"### {r['label']}",
            "",
        ] + sweep_table_markdown(l4["sweep"]) + [
            f"- **{'✅ PASS' if v['passed'] else '❌ FAIL'}**"
            + (f" roi_devig={v['roi_devig']:+.4f} (n_bets={v['n_bets']})" if v["passed"] else ""),
            "",
        ]

    # Disagreement gate table.
    lines += [
        "---",
        "",
        "## Disagreement Gate (Conviction Filter)",
        "",
        f"_Filter to games where `|p_classifier − p_run_diff| ≤ d` (both models agree within d)._",
        f"_Best ensemble w={best_w:.2f} used throughout. Market Brier on full set = {market_brier:.4f}._",
        "",
        "| disagree_cap | n_kept | pct_kept | n_bets (L4 sweep) | roi_devig | "
        "model Brier | market Brier | beats market? |",
        "|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for dr in disagree_rows:
        lines.append(
            f"| ≤{dr['disagree_cap']:.2f} "
            f"| {dr['n_kept']} "
            f"| {dr['pct_kept']:.1%} "
            f"| {dr['n_bets']} "
            f"| {_fmt(dr['roi_devig'], '+.4f')} "
            f"| {_fmt(dr['model_brier'])} "
            f"| {_fmt(dr['market_brier'])} "
            f"| {_b(dr['brier_beats_market'])} |"
        )

    # Verdict on conviction filter.
    any_beats = [dr for dr in disagree_rows
                 if dr["brier_beats_market"] and dr["n_kept"] >= MIN_BETS_RELIABLE]
    if any_beats:
        best_dr = min(any_beats, key=lambda x: x["model_brier"])
        verdict_conv = (
            f"✅ **ADOPT as conviction filter** — "
            f"at disagree_cap={best_dr['disagree_cap']:.2f} "
            f"({best_dr['pct_kept']:.1%} of games), "
            f"model Brier {best_dr['model_brier']:.4f} < market {best_dr['market_brier']:.4f}. "
            f"n_bets={best_dr['n_bets']}, roi_devig={_fmt(best_dr['roi_devig'], '+.4f')}."
        )
    else:
        verdict_conv = (
            "❌ **NOT adopted** — no disagreement cap achieves model Brier < market Brier "
            f"with n_kept ≥ {MIN_BETS_RELIABLE}."
        )

    lines += [
        "",
        f"**Conviction filter verdict:** {verdict_conv}",
        "",
        "---",
        "",
        "## Overall Verdict",
        "",
    ]

    # Best-w vs baseline models.
    best_brier = best_rec["model_brier"]
    pure_clf   = next(r for r in recs if r["label"] == "w=1.00")
    pure_rd    = next(r for r in recs if r["label"] == "w=0.00")

    lines += [
        f"- **Best ensemble (w={best_w:.2f}) Brier:** {_fmt(best_brier)} "
        f"vs market {_fmt(market_brier)} "
        f"({'beats market ✅' if best_rec['brier_beats_market'] else 'does NOT beat market ❌'})",
        f"- **Pure classifier (w=1.0) Brier:** {_fmt(pure_clf['model_brier'])}",
        f"- **Pure run_diff  (w=0.0) Brier:** {_fmt(pure_rd['model_brier'])}",
        f"- **Ensemble improvement over pure classifier:** "
        f"{float(pure_clf['model_brier']) - float(best_brier):+.4f} (positive = ensemble better)",
        "",
        "**The disagreement gate is the primary deliverable (Story 28.2 AC).**",
        f"Conviction filter: {verdict_conv}",
        "",
    ]

    _OUT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Report written to %s", _OUT_PATH)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="28.2: run_diff × classifier ensemble + disagreement gate (eval-only)"
    )
    ap.add_argument(
        "--h2h-parquet",
        default=str(_H2H_PARQUET_DEFAULT),
        help="oos_predictions_h2h_v2.parquet (direct classifier OOS surface)",
    )
    ap.add_argument(
        "--run-diff-parquet",
        default=None,
        help="Pre-computed run_diff probabilities parquet (skips Snowflake if provided). "
             "Auto-saved to models/layer3/run_diff_derived_h2h_{year}.parquet on first run.",
    )
    ap.add_argument(
        "--season", type=int, default=_OOS_YEAR,
        help=f"OOS year (default {_OOS_YEAR}). run_diff model is OOS for this year only.",
    )
    args = ap.parse_args()

    # --- Load direct classifier OOS surface ---
    clf_path = Path(args.h2h_parquet)
    if not clf_path.exists():
        log.error("Classifier OOS parquet not found: %s", clf_path)
        log.error("Run build_h2h_oos_parquet.py first.")
        sys.exit(1)
    clf_df = pd.read_parquet(clf_path)
    clf_df["game_pk"] = clf_df["game_pk"].astype(int)

    # Restrict to the OOS season for apples-to-apples comparison with run_diff.
    clf_oos = clf_df[clf_df["game_year"] == args.season].copy()
    log.info("Classifier OOS: %d games for season %d", len(clf_oos), args.season)
    if len(clf_oos) == 0:
        log.error("No classifier OOS games for season %d", args.season)
        sys.exit(1)

    # Derive training base rate from all other seasons in the parquet.
    train_y = clf_df.loc[clf_df["game_year"] < args.season, "home_win"].astype(float)
    base_rate = float(train_y.mean()) if len(train_y) else 0.54
    log.info("Base rate (seasons < %d): %.4f", args.season, base_rate)

    # --- Load or compute run_diff-derived probabilities ---
    rd_df = _get_run_diff_probs(args)
    rd_df["game_pk"] = rd_df["game_pk"].astype(int)

    # --- Merge on game_pk (inner join: only games with both estimates) ---
    merged = clf_oos.merge(rd_df, on="game_pk", how="inner")
    merged = merged.dropna(subset=["market_devig_home"]).reset_index(drop=True)
    log.info("Merged (classifier ∩ run_diff ∩ market): %d games", len(merged))
    if len(merged) < MIN_BETS_RELIABLE:
        log.error("Too few merged games (%d) for reliable evaluation.", len(merged))
        sys.exit(1)

    p_clf = merged["model_p_home_win"].to_numpy(float)
    p_rd  = merged["p_run_diff"].to_numpy(float)
    y     = merged["home_win"].to_numpy(float)
    mkt   = merged["market_devig_home"].to_numpy(float)

    merged["disagree"] = np.abs(p_clf - p_rd)

    ok = ~np.isnan(mkt)
    market_brier = brier_score(mkt[ok], y[ok]) if ok.any() else float("nan")
    log.info("Market Brier (2026 Bovada): %.4f", market_brier)

    n_ensemble = int(ok.sum())

    # --- Three-layer eval per mix weight ---
    log.info("Running three-layer eval for w ∈ %s ...", MIX_WEIGHTS)
    recs: list[dict] = []
    best_w    = float(MIX_WEIGHTS[-1])
    best_brier = float("inf")

    for w in MIX_WEIGHTS:
        p_ens = w * p_clf + (1.0 - w) * p_rd
        rec   = _three_layer(f"w={w:.2f}", p_ens, y, mkt, base_rate)

        # Layer 4 sweep (need market coverage).
        if ok.any():
            games4 = normalize_h2h_frame(
                pd.DataFrame({
                    "game_pk":           merged.loc[ok, "game_pk"].to_numpy(),
                    "model_p_home_win":  p_ens[ok],
                    "market_devig_home": mkt[ok],
                    "home_win":          y[ok],
                })
            )
            sw  = sweep_thresholds(games4)
            rec["layer4"] = {
                "sweep":   sw,
                "verdict": layer4_verdict(sw),
                "default": evaluate_selective_strategy(games4),
            }

        log.info(
            "  w=%.2f  NLL=%.4f (prior=%.4f)  ECE=%.4f  Brier=%.4f  mkt=%.4f  "
            "beats_prior=%s  beats_market=%s",
            w, rec["nll"], rec["prior_nll"], rec["ece"], rec["model_brier"],
            market_brier, _b(rec["nll_beats_prior"]), _b(rec["brier_beats_market"]),
        )
        recs.append(rec)

        if np.isfinite(rec["model_brier"]) and rec["model_brier"] < best_brier:
            best_brier = rec["model_brier"]
            best_w     = w

    log.info("Best w = %.2f (model Brier = %.4f)", best_w, best_brier)

    # --- Attach best-w ensemble to merged frame for disagreement analysis ---
    merged["p_ens"] = best_w * p_clf + (1.0 - best_w) * p_rd

    # --- Disagreement gate analysis ---
    log.info("Running disagreement gate analysis (caps=%s)...", DISAGREE_CAPS)
    disagree_rows = _disagree_gate_analysis(merged, best_w, base_rate)
    for dr in disagree_rows:
        log.info(
            "  cap≤%.2f  n_kept=%d (%.1f%%)  n_bets=%d  roi_devig=%s  "
            "model_brier=%s  beats_market=%s",
            dr["disagree_cap"], dr["n_kept"], 100 * dr["pct_kept"],
            dr["n_bets"], _fmt(dr.get("roi_devig", float("nan")), "+.4f"),
            _fmt(dr["model_brier"]), _b(dr["brier_beats_market"]),
        )

    # --- Write report ---
    _write_report(recs, disagree_rows, merged, best_w, base_rate, market_brier, n_ensemble)
    log.info("DONE. Report: %s", _OUT_PATH)


if __name__ == "__main__":
    main()
