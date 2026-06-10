"""
alpha_recal_h2h_seq.py — Story 28.1 (Epic 28)

Alpha re-calibration for the sequential XGBoost H2H champion.

The deployed α=0 was fit on the original elasticnet models (Epic 1.7). The
sequential XGBoost champion (h2h_v2_approach_b, ECE 0.043) has different raw
outputs. This script finds the optimal α on 2026 market-covered games:

    posterior = sigmoid( α·log_odds(model_p) + (1-α)·log_odds(market_p) )

objective: log-loss minimisation, grid α∈[0.0, 0.1, …, 1.0].

Interpretation recorded on every run:
  α=0 → market mirror; deploy via selective/magnitude path only.
  α>0 → blended value; 28.3 must re-measure magnitude on the new blend
         (blended gap shrinks relative to raw gap).

Outputs:
  betting_ml/models/best_alpha.json              (adds h2h_seq_alpha key)
  ablation_results/h2h_alpha_recal_seq.md        (grid table + interpretation)

Usage:
    uv run python betting_ml/scripts/alpha_recal_h2h_seq.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.probability_layer import compute_posterior, tune_alpha
from betting_ml.scripts.evaluation.bayesian_model_eval import (
    normalize_h2h_frame,
    sweep_thresholds,
    layer4_verdict,
    sweep_table_markdown,
)

_OOS_PARQUET = _PROJECT_ROOT / "betting_ml" / "models" / "layer3" / "oos_predictions_h2h_v2.parquet"
_BEST_ALPHA_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
_REPORT_PATH = (
    _PROJECT_ROOT
    / "quant_sports_intel_models"
    / "baseball"
    / "ablation_results"
    / "h2h_alpha_recal_seq.md"
)

_EVAL_SEASON = 2026


# ---------------------------------------------------------------------------
# Load + filter
# ---------------------------------------------------------------------------

def load_surface(parquet: Path = _OOS_PARQUET) -> pd.DataFrame:
    df = pd.read_parquet(parquet)
    keep = (
        (df["game_year"] == _EVAL_SEASON)
        & df["model_p_home_win"].notna()
        & df["market_devig_home"].notna()
        & df["home_win"].notna()
    )
    out = df[keep].copy().reset_index(drop=True)
    print(
        f"Surface: {len(out)} market-covered 2026 games "
        f"(of {(df['game_year'] == _EVAL_SEASON).sum()} 2026 rows total)"
    )
    return out


# ---------------------------------------------------------------------------
# Alpha grid
# ---------------------------------------------------------------------------

def run_alpha_grid(df: pd.DataFrame) -> tuple[float, list[dict]]:
    model_p = df["model_p_home_win"].to_numpy(float)
    market_p = df["market_devig_home"].to_numpy(float)
    outcomes = df["home_win"].to_numpy(float)

    best_alpha, results = tune_alpha(model_p, market_p, outcomes)

    print(f"\n{'α':>6} | {'Log-Loss':>10} | {'Δ vs best':>10}")
    print("-" * 33)
    best_ll = min(r["log_loss"] for r in results)
    for r in results:
        delta = r["log_loss"] - best_ll
        marker = " ← best" if abs(delta) < 1e-10 else ""
        print(f"{r['alpha']:>6.1f} | {r['log_loss']:>10.6f} | {delta:>10.6f}{marker}")
    print(f"\nSelected best_alpha = {best_alpha}")
    return best_alpha, results


# ---------------------------------------------------------------------------
# Layer-4 attribution (only if α > 0)
# ---------------------------------------------------------------------------

def run_layer4_attribution(df: pd.DataFrame, alpha: float) -> dict:
    """Recompute magnitude gap and Layer-4 sweep on the new blended probabilities."""
    blended = np.array([
        compute_posterior(float(mp), float(mkt), alpha)
        for mp, mkt in zip(df["model_p_home_win"], df["market_devig_home"])
    ])
    df = df.copy()
    df["model_p_blended_new"] = blended

    raw_gap_mean = float(np.mean(np.abs(df["model_p_home_win"] - df["market_devig_home"])))
    blended_gap_mean = float(np.mean(np.abs(blended - df["market_devig_home"])))
    print(f"\nMagnitude gap (raw model):    {raw_gap_mean:.4f}")
    print(f"Magnitude gap (new blend α={alpha:.1f}): {blended_gap_mean:.4f}")
    print(f"Gap shrinkage: {(raw_gap_mean - blended_gap_mean) / raw_gap_mean:.1%}")

    # Canonical Layer-4 frame using blended probabilities
    games = normalize_h2h_frame(
        df,
        model_p_col="model_p_blended_new",
        market_p_col="market_devig_home",
        outcome_col="home_win",
    )
    sweep = sweep_thresholds(games)
    verdict = layer4_verdict(sweep)

    print("\nLayer-4 threshold sweep (blended probs):")
    for line in sweep_table_markdown(sweep):
        print(line)
    print(f"\nLayer-4 verdict: passed={verdict['passed']}")
    if verdict["passed"]:
        print(
            f"  optimal h2h_threshold={verdict['optimal_h2h_threshold']}, "
            f"n_bets={verdict['n_bets']}, roi_devig={verdict.get('roi_devig', float('nan')):.4f}"
        )

    # Also report Layer-4 on raw model probs for comparison
    games_raw = normalize_h2h_frame(df)
    sweep_raw = sweep_thresholds(games_raw)
    verdict_raw = layer4_verdict(sweep_raw)
    print(f"\nLayer-4 verdict (raw probs):  passed={verdict_raw['passed']}")
    if verdict_raw["passed"]:
        print(
            f"  optimal h2h_threshold={verdict_raw['optimal_h2h_threshold']}, "
            f"n_bets={verdict_raw['n_bets']}, roi_devig={verdict_raw.get('roi_devig', float('nan')):.4f}"
        )

    return {
        "raw_gap_mean": raw_gap_mean,
        "blended_gap_mean": blended_gap_mean,
        "gap_shrinkage": (raw_gap_mean - blended_gap_mean) / raw_gap_mean,
        "sweep_blended": sweep,
        "verdict_blended": verdict,
        "sweep_raw": sweep_raw,
        "verdict_raw": verdict_raw,
    }


# ---------------------------------------------------------------------------
# Persist results
# ---------------------------------------------------------------------------

def write_best_alpha(alpha: float, log_loss: float, n_games: int) -> None:
    existing: dict = {}
    if _BEST_ALPHA_PATH.exists():
        existing = json.loads(_BEST_ALPHA_PATH.read_text())
    existing.update({
        "h2h_seq_alpha": float(alpha),
        "h2h_seq_log_loss": float(log_loss),
        "h2h_seq_n_games": int(n_games),
        "h2h_seq_run_ts": datetime.now(timezone.utc).isoformat(),
        "h2h_seq_source": "alpha_recal_h2h_seq.py (2026 market-covered OOS)",
    })
    _BEST_ALPHA_PATH.write_text(json.dumps(existing, indent=2))
    print(f"\nWrote best_alpha.json: h2h_seq_alpha={alpha}")


def write_report(
    df: pd.DataFrame,
    best_alpha: float,
    results: list[dict],
    n_games: int,
    layer4: dict | None,
) -> None:
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    best_ll = min(r["log_loss"] for r in results)

    lines: list[str] = []
    lines += [
        f"# H2H Alpha Re-calibration — Sequential Champion (Story 28.1)",
        f"",
        f"_Run: {run_ts}_  ",
        f"_Source: `{_OOS_PARQUET.name}`, season {_EVAL_SEASON}, market-covered ({n_games} games)_",
        f"",
        f"## Alpha Grid (log-loss objective)",
        f"",
        f"| α | Log-Loss | Δ vs best |",
        f"|--:|--:|--:|",
    ]
    for r in results:
        delta = r["log_loss"] - best_ll
        marker = " ⭐" if abs(delta) < 1e-10 else ""
        lines.append(f"| {r['alpha']:.1f} | {r['log_loss']:.6f} | {delta:.6f}{marker} |")

    lines += [
        f"",
        f"**Best α = {best_alpha}** (log-loss = {best_ll:.6f})",
        f"",
    ]

    # Interpretation — mandated by AC
    lines += [
        f"## Interpretation",
        f"",
    ]
    if best_alpha == 0.0:
        lines += [
            f"**α = 0 → market mirror.**",
            f"",
            f"The sequential champion adds no incremental probability signal beyond the market.",
            f"Deploy H2H **only via the selective/magnitude path** (Story 28.3): bet when",
            f"`|model_p − market_p| > threshold` — the model's role is to identify where",
            f"its raw estimate diverges enough that the market may be mispriced, not to",
            f"blend a blended probability into the price.",
            f"",
            f"28.3 should measure magnitude ROI on **raw** model probabilities (not blended),",
            f"since α=0 means the blend collapses to the market.",
        ]
    else:
        lines += [
            f"**α = {best_alpha} → blended value exists.**",
            f"",
            f"The posterior blend `sigmoid(α·logodds(model) + (1-α)·logodds(market))` with",
            f"α={best_alpha} lowers log-loss vs either pure model (α=1) or pure market (α=0).",
            f"",
            f"**Consequence for Story 28.3:** magnitude kill-criterion measurements must use",
            f"the **blended** probabilities (`posterior`) as `model_p`, not the raw model output.",
            f"The blended gap is {layer4['blended_gap_mean']:.4f} vs raw gap {layer4['raw_gap_mean']:.4f}",
            f"({layer4['gap_shrinkage']:.1%} shrinkage) — the effective signal narrows but the",
            f"blend may reduce calibration error enough to be worth the loss.",
        ]

    if layer4 is not None:
        lines += [
            f"",
            f"## Layer-4 Attribution (blended α={best_alpha})",
            f"",
            f"Mean magnitude gap: raw = {layer4['raw_gap_mean']:.4f}, "
            f"blended = {layer4['blended_gap_mean']:.4f} "
            f"({layer4['gap_shrinkage']:.1%} shrinkage)",
            f"",
            f"### Threshold sweep — blended probabilities",
            f"",
        ]
        lines += sweep_table_markdown(layer4["sweep_blended"])
        v = layer4["verdict_blended"]
        lines += [
            f"",
            f"**Layer-4 verdict (blended): passed={v['passed']}**  ",
        ]
        if v["passed"]:
            lines += [
                f"optimal h2h_threshold={v['optimal_h2h_threshold']}, "
                f"n_bets={v['n_bets']}, roi_devig={v.get('roi_devig', float('nan')):.4f}",
            ]
        lines += [
            f"",
            f"### Threshold sweep — raw model probabilities (baseline)",
            f"",
        ]
        lines += sweep_table_markdown(layer4["sweep_raw"])
        vr = layer4["verdict_raw"]
        lines += [
            f"",
            f"**Layer-4 verdict (raw): passed={vr['passed']}**  ",
        ]
        if vr["passed"]:
            lines += [
                f"optimal h2h_threshold={vr['optimal_h2h_threshold']}, "
                f"n_bets={vr['n_bets']}, roi_devig={vr.get('roi_devig', float('nan')):.4f}",
            ]

    lines += [""]
    _REPORT_PATH.write_text("\n".join(lines))
    print(f"Wrote report: {_REPORT_PATH}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    df = load_surface()
    n_games = len(df)

    best_alpha, results = run_alpha_grid(df)
    best_ll = min(r["log_loss"] for r in results)

    write_best_alpha(best_alpha, best_ll, n_games)

    layer4: dict | None = None
    if best_alpha > 0.0:
        print(f"\nα={best_alpha} > 0 — running Layer-4 attribution on blended probabilities...")
        layer4 = run_layer4_attribution(df, best_alpha)
    else:
        print(
            "\nα=0: market mirror. "
            "Story 28.3 measures magnitude on raw model probabilities."
        )

    write_report(df, best_alpha, results, n_games, layer4)


if __name__ == "__main__":
    main()
