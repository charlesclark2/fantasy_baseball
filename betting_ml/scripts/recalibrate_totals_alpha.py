"""
recalibrate_totals_alpha.py — Epic 10, Story 10.5

Alpha re-calibration for the Layer 3 totals model. With a market-blind P(over)
estimate (no circular market features) now available, find the optimal log-odds
blend between the model's P(over) and Bovada's de-vigged implied probability:

    posterior_p_over = sigmoid( alpha·logodds(model_p_over)
                              + (1-alpha)·logodds(bovada_devig_over_prob) )

alpha=1 → pure model, alpha=0 → pure market. With market circularity removed,
alpha > 0 is expected for the first time (Epic 1.7 found alpha=0 because the CV
models had learned the market price).

Key choice (user-approved): the grid is scored on the **walk-forward OOS surface**
(`oos_predictions_totals_v1.parquet`, each game predicted by a prior-seasons-only
model), NOT the in-sample `load_retained_features()` the spec names — so every
alpha's log-loss is honest. Reuses `probability_layer.tune_alpha`/`compute_posterior`
(the exact blend the H2H path uses) — no reimplementation.

Also re-checks the 10.4/OOS **tail over-confidence** AFTER the blend: blending toward
Bovada should pull the over-confident `[0.9,1.0]`/`[0,0.1]` cells inward. If the blend
fixes them, no isotonic recalibration is needed.

Outputs:
  * betting_ml/models/best_alpha.json            (adds `totals_alpha` — separate from the Epic 1.7 combined key)
  * ablation_results/totals_alpha_tuning.md       (grid table + monotonicity + tail before/after)
  * (--write-snowflake) baseball_data.betting_ml.alpha_tuning_results rows tagged market='totals'

Fully offline by default (reads the local parquet). `predict_today` consuming
`totals_alpha` is part of the Layer 3 live wiring → Story 10.7 (deviation, consistent
with 10.3/10.4 deferring the live path).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.probability_layer import compute_posterior, tune_alpha  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import reliability_table, expected_calibration_error  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_totals_v1.parquet"
_BEST_ALPHA_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
_REPORT_PATH = _PROJECT_ROOT / "quant_sports_intel_models" / "baseball" / "ablation_results" / "totals_alpha_tuning.md"


def load_oos_surface(parquet: Path = _OOS_PARQUET) -> pd.DataFrame:
    """Bovada-line, settled games with model P(over), market de-vig, and outcome."""
    df = pd.read_parquet(parquet)
    keep = (
        (df["total_line_source"] == "bovada")
        & df["oos_p_over"].notna()
        & df["bovada_devig_over_prob"].notna()
        & df["over_hit"].notna()
    )
    out = df[keep].copy()
    log.info("Alpha surface: %d Bovada-line settled games (of %d OOS rows)", len(out), len(df))
    return out


def monotonicity_flags(results: list[dict], best_alpha: float) -> dict:
    """From the best alpha, log-loss should worsen monotonically outward in both directions.

    Returns {'monotone_above': bool, 'monotone_below': bool, 'violations': [...]}.
    """
    res = sorted(results, key=lambda r: r["alpha"])
    alphas = [r["alpha"] for r in res]
    lls = [r["log_loss"] for r in res]
    bi = int(np.argmin([abs(a - best_alpha) for a in alphas]))
    violations = []
    mono_above = True
    for i in range(bi, len(res) - 1):
        if lls[i + 1] < lls[i] - 1e-9:
            mono_above = False
            violations.append(f"α {alphas[i]:.1f}→{alphas[i+1]:.1f}: LL {lls[i]:.6f}→{lls[i+1]:.6f} (improves above best)")
    mono_below = True
    for i in range(bi, 0, -1):
        if lls[i - 1] < lls[i] - 1e-9:
            mono_below = False
            violations.append(f"α {alphas[i]:.1f}→{alphas[i-1]:.1f}: LL {lls[i]:.6f}→{lls[i-1]:.6f} (improves below best)")
    return {"monotone_above": mono_above, "monotone_below": mono_below, "violations": violations}


def tail_before_after(df: pd.DataFrame, best_alpha: float) -> pd.DataFrame:
    """Reliability of the two extreme bins before (model) vs after (blended) the alpha blend."""
    model_p = df["oos_p_over"].to_numpy(float)
    mkt = df["bovada_devig_over_prob"].to_numpy(float)
    y = df["over_hit"].to_numpy(float)
    post = np.array([compute_posterior(float(mp), float(mk), float(best_alpha)) for mp, mk in zip(model_p, mkt)])

    rel_before = reliability_table(model_p, y)
    rel_after = reliability_table(post, y)
    rows = []
    for label in ("[0.00, 0.10)", "[0.90, 1.00]"):
        b = rel_before[rel_before["bin"] == label]
        a = rel_after[rel_after["bin"] == label]
        rows.append({
            "bin": label,
            "n_before": int(b["n"].iloc[0]), "gap_before": float(b["gap"].iloc[0]),
            "n_after": int(a["n"].iloc[0]), "gap_after": float(a["gap"].iloc[0]),
        })
    return pd.DataFrame(rows), post


def run(write_snowflake: bool = False) -> dict:
    df = load_oos_surface()
    model_p = df["oos_p_over"].to_numpy(float)
    market = df["bovada_devig_over_prob"].to_numpy(float)
    outcomes = df["over_hit"].to_numpy(float)

    best_alpha, results = tune_alpha(model_p, market, outcomes)
    best_ll = min(r["log_loss"] for r in results)
    ll_market = next(r["log_loss"] for r in results if abs(r["alpha"]) < 1e-9)   # alpha=0 → pure Bovada
    ll_model = next(r["log_loss"] for r in results if abs(r["alpha"] - 1.0) < 1e-9)  # alpha=1 → pure model
    mono = monotonicity_flags(results, best_alpha)
    tail, post = tail_before_after(df, best_alpha)

    ece_model = expected_calibration_error(model_p, outcomes)
    ece_post = expected_calibration_error(post, outcomes)

    metrics = {
        "totals_alpha": float(best_alpha),
        "totals_log_loss": round(best_ll, 6),
        "log_loss_market_only": round(ll_market, 6),   # alpha=0
        "log_loss_model_only": round(ll_model, 6),      # alpha=1
        "n_games": int(len(df)),
        "monotone": bool(mono["monotone_above"] and mono["monotone_below"]),
        "ece_model": round(ece_model, 4),
        "ece_post_blend": round(ece_post, 4),
    }
    _write_report(results, best_alpha, metrics, mono, tail)
    _update_best_alpha(metrics)
    if write_snowflake:
        _write_alpha_table(results, best_alpha)

    log.info("totals_alpha=%.2f | LL %.6f (market-only %.6f, model-only %.6f) | "
             "post-blend ECE %.4f (model %.4f) | monotone=%s",
             best_alpha, best_ll, ll_market, ll_model, ece_post, ece_model, metrics["monotone"])
    return {"metrics": metrics, "results": results, "tail": tail}


def _grid_table(results: list[dict], best_alpha: float) -> list[str]:
    best_ll = min(r["log_loss"] for r in results)
    rows = ["| alpha | log_loss | Δ vs best | |", "|---:|---:|---:|:--|"]
    for r in sorted(results, key=lambda x: x["alpha"]):
        mark = " ← best" if abs(r["alpha"] - best_alpha) < 1e-9 else ""
        rows.append(f"| {r['alpha']:.1f} | {r['log_loss']:.6f} | {r['log_loss'] - best_ll:+.6f} |{mark} |")
    return rows


def _write_report(results, best_alpha, metrics, mono, tail) -> None:
    g = metrics
    interp = (
        f"**alpha = {best_alpha:.2f} > 0** — the Layer 3 model adds genuine signal beyond Bovada's "
        f"implied probability (log-loss {g['totals_log_loss']:.6f} vs market-only {g['log_loss_market_only']:.6f}, "
        f"an improvement of {g['log_loss_market_only'] - g['totals_log_loss']:.6f}). This is the first non-zero "
        "totals alpha — Epic 1.7 found 0 because its CV models were market-circular."
        if best_alpha > 0 else
        "**alpha = 0.00** — the blend prefers Bovada's implied probability; the model does not improve on the "
        "market on log-loss here. Confirm the Layer 3 matrix is market-clean (`validate_layer3_matrix()`); if it "
        "is, this honestly means the model is at market parity on this surface despite its Brier edge."
    )
    lines = [
        "# Layer 3 Totals — Alpha Re-calibration (Story 10.5)",
        "",
        f"- **Surface:** walk-forward OOS (`oos_predictions_totals_v1.parquet`), **{g['n_games']}** Bovada-line settled games.",
        "- **Blend:** log-odds `compute_posterior` (alpha=1 model, alpha=0 Bovada de-vig); objective = log-loss on `over_hit`.",
        "",
        "## Alpha grid",
        *_grid_table(results, best_alpha),
        "",
        f"- **best totals_alpha = {best_alpha:.2f}**, log-loss **{g['totals_log_loss']:.6f}**.",
        f"- Reference: market-only (α=0) **{g['log_loss_market_only']:.6f}**, model-only (α=1) **{g['log_loss_model_only']:.6f}**.",
        f"- Monotonic worsening away from best: above={mono['monotone_above']}, below={mono['monotone_below']}"
        + ("" if not mono["violations"] else " — **VIOLATIONS:** " + "; ".join(mono["violations"])),
        "",
        "## Interpretation",
        interp,
        "",
        "## Tail over-confidence — before vs after the blend (the 10.4/OOS carry-over)",
        tail.to_markdown(index=False, floatfmt=".4f"),
        "",
        f"- Post-blend ECE **{g['ece_post_blend']:.4f}** (model-only {g['ece_model']:.4f}).",
        ("- The blend pulls the over-confident extremes toward 0 — **no isotonic recalibration needed.**"
         if tail["gap_after"].abs().max() < tail["gap_before"].abs().max()
         else "- The blend did NOT sufficiently temper the tails — **add isotonic recalibration before sizing** (flagged for 10.6)."),
        "",
        "## Acceptance criteria",
        "- [x] Alpha grid table documented with log-loss per alpha",
        f"- [x] `best_alpha.json` updated with `totals_alpha` = {best_alpha:.2f} (separate from Epic 1.7 combined)",
        "- [~] `predict_today.py` uses the totals-specific alpha — **deferred to 10.7** (Layer 3 live wiring)",
        f"- [{'x' if best_alpha > 0 else ' '}] alpha > 0 documented "
        + ("(model adds signal beyond Bovada)" if best_alpha > 0 else "→ root-cause: run validate_layer3_matrix()"),
    ]
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text("\n".join(lines) + "\n")
    log.info("Wrote %s", _REPORT_PATH)


def _update_best_alpha(metrics: dict) -> None:
    data = json.loads(_BEST_ALPHA_PATH.read_text()) if _BEST_ALPHA_PATH.exists() else {}
    data["totals_alpha"] = metrics["totals_alpha"]
    data["totals_log_loss"] = metrics["totals_log_loss"]
    data["totals_n_games"] = metrics["n_games"]
    data["totals_run_ts"] = datetime.now(timezone.utc).isoformat()
    data["totals_source"] = "recalibrate_totals_alpha.py (walk-forward OOS surface)"
    _BEST_ALPHA_PATH.write_text(json.dumps(data, indent=2) + "\n")
    log.info("Updated %s (totals_alpha=%.2f, existing combined key preserved)", _BEST_ALPHA_PATH, metrics["totals_alpha"])


def _write_alpha_table(results: list[dict], best_alpha: float) -> None:
    """Append the totals alpha grid to alpha_tuning_results, tagged market='totals'.

    Adds a nullable `market` column (existing Epic 1.7 rows stay NULL = combined).
    """
    from betting_ml.utils.data_loader import get_snowflake_connection
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute("ALTER TABLE baseball_data.betting_ml.alpha_tuning_results "
                    "ADD COLUMN IF NOT EXISTS market VARCHAR")
        for r in results:
            cur.execute(
                "INSERT INTO baseball_data.betting_ml.alpha_tuning_results (alpha, log_loss, market) "
                "VALUES (%s, %s, 'totals')", (float(r["alpha"]), float(r["log_loss"])))
        conn.commit()
        log.info("Wrote %d totals alpha rows (market='totals') to alpha_tuning_results", len(results))
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Story 10.5 — totals alpha re-calibration (OOS surface)")
    p.add_argument("--write-snowflake", action="store_true",
                   help="also append the grid to alpha_tuning_results (market='totals')")
    args = p.parse_args()
    run(write_snowflake=args.write_snowflake)


if __name__ == "__main__":
    main()
