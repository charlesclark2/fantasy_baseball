"""Story 28.6a (completion) — REAL-BOOK ROI for the 28.2 conviction gate.

The local robustness preview already showed the gate's model-vs-market Brier edge
is within noise on n=85 (95% CI crosses zero, ~68% bootstrap confidence). This
script supplies the remaining 28.6a evidence: ROI on ACTUAL Bovada American H2H
odds (not the optimistic vig-free roi_devig), with a bootstrap 95% lower-CI.

Strategy under test: among games where the two independent estimators AGREE
(|p_classifier - p_run_diff| <= 0.02), bet the model's favored side. Two views:
  (1) bet EVERY agreeing game  (the pure conviction filter)
  (2) bet agreeing games that also clear the operational edge threshold
      (assign_decisions: direction_flip OR magnitude > threshold)

Pre-committed go/no-go for the forward test (28.6b): real-book ROI 95% lower-CI > 0.

NEEDS SNOWFLAKE (load_devig_home_prob_bovada). Hand-off — run from project root:
    uv run python betting_ml/scripts/h2h_conviction_realbook_roi_28_6a.py --env prod
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
L3 = REPO / "betting_ml" / "models" / "layer3"
OUT_MD = REPO / "quant_sports_intel_models" / "baseball" / "ablation_results" / "h2h_conviction_gate_28_6a.md"

DISAGREE_CAP = 0.02
ENSEMBLE_W = 0.25  # 28.2 best ensemble: p = w*p_clf + (1-w)*p_run_diff
B_BOOT = 10000


def _american_to_decimal(a: float) -> float:
    if a is None or pd.isna(a) or a == 0:
        return float("nan")
    return 1.0 + (a / 100.0 if a > 0 else 100.0 / abs(a))


def _bet_result(won: bool, dec_odds: float) -> float:
    """Profit per 1u staked: (decimal-1) on a win, -1 on a loss."""
    return (dec_odds - 1.0) if won else -1.0


def _roi_with_ci(profits: np.ndarray, rng: np.random.Generator) -> dict:
    n = len(profits)
    if n == 0:
        return {"n": 0, "roi": float("nan"), "lo95": float("nan"), "hi95": float("nan"), "p_pos": float("nan")}
    boots = np.array([profits[rng.integers(0, n, n)].mean() for _ in range(B_BOOT)])
    return {
        "n": n,
        "roi": float(profits.mean()),
        "lo95": float(np.percentile(boots, 2.5)),
        "hi95": float(np.percentile(boots, 97.5)),
        "p_pos": float(np.mean(boots > 0)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="prod")
    args = ap.parse_args()

    import sys
    sys.path.insert(0, str(REPO))
    from betting_ml.scripts.evaluation.bayesian_model_eval import (
        assign_decisions, DEFAULT_H2H_MAGNITUDE_THRESHOLD,
    )
    from betting_ml.scripts.load_layer3_features import load_devig_home_prob_bovada

    # --- predictions (local, leakage-free 2026 OOS) ---
    clf = pd.read_parquet(L3 / "oos_predictions_h2h_v2.parquet")
    rd = pd.read_parquet(L3 / "run_diff_derived_h2h_2026.parquet")
    clf["game_pk"] = clf["game_pk"].astype(int)
    rd["game_pk"] = rd["game_pk"].astype(int)
    clf26 = clf[clf["game_year"] == 2026].copy()
    m = clf26.merge(rd[["game_pk", "p_run_diff"]], on="game_pk", how="inner")
    m = m.dropna(subset=["market_devig_home", "home_win"]).reset_index(drop=True)

    p_clf = m["model_p_home_win"].to_numpy(float)
    p_rd = m["p_run_diff"].to_numpy(float)
    m["model_p_home"] = ENSEMBLE_W * p_clf + (1 - ENSEMBLE_W) * p_rd
    m["market_p_home"] = m["market_devig_home"].astype(float)
    m["market"] = "h2h"
    m["disagree"] = np.abs(p_clf - p_rd)

    gate = m[m["disagree"] <= DISAGREE_CAP].copy()

    # --- real Bovada American odds for the gate games ---
    odds = load_devig_home_prob_bovada(game_pks=gate["game_pk"].tolist(), env=args.env)
    odds["game_pk"] = odds["game_pk"].astype(int)
    gate = gate.merge(
        odds[["game_pk", "home_price", "away_price", "devig_home_source"]],
        on="game_pk", how="left",
    )

    # --- bet decisions (model's favored side; direction_flip OR magnitude>thr) ---
    decided = assign_decisions(gate, h2h_magnitude_threshold=DEFAULT_H2H_MAGNITUDE_THRESHOLD)

    rng = np.random.default_rng(42)

    def _profits(df: pd.DataFrame, only_threshold: bool) -> tuple[np.ndarray, int, int]:
        rows, n_bovada, n_total = [], 0, 0
        for _, r in df.iterrows():
            side = r["bet_decision"]
            if side == "abstain":
                if only_threshold:
                    continue
                # pure conviction filter: bet the model's favored side regardless of edge
                side = "home" if r["model_p_home"] > 0.5 else "away"
            n_total += 1
            price = r["home_price"] if side == "home" else r["away_price"]
            dec = _american_to_decimal(price)
            if pd.isna(dec):  # no real Bovada price for this game/side
                continue
            n_bovada += 1
            won = (int(r["home_win"]) == 1) if side == "home" else (int(r["home_win"]) == 0)
            rows.append(_bet_result(won, dec))
        return np.array(rows, float), n_bovada, n_total

    views = {}
    for name, only_thr in [("threshold_bets", True), ("all_agreeing_games", False)]:
        profits, n_bov, n_tot = _profits(decided, only_thr)
        stats = _roi_with_ci(profits, rng)
        stats.update({"n_with_real_odds": n_bov, "n_decisions": n_tot})
        views[name] = stats

    # --- verdict (pre-committed: forward-test only if real-book ROI lower-CI > 0) ---
    primary = views["threshold_bets"]
    go = np.isfinite(primary["lo95"]) and primary["lo95"] > 0
    verdict = (
        f"GO — real-book ROI 95% lower-CI {primary['lo95']:+.4f} > 0 on the operational "
        f"threshold bets (n={primary['n']}). Combined with the ≥2-adjacent-cap plateau, proceed to 28.6b "
        f"shadow forward test."
        if go else
        f"NO-GO (backtest) — real-book ROI 95% lower-CI {primary['lo95']:+.4f} ≤ 0 (n={primary['n']}). "
        f"The backtest does not clear the pre-committed bar. 28.6b only justifiable as a free shadow accrual "
        f"(no money at risk); otherwise redirect to 12.10′ CLV."
    )

    def _row(v: dict) -> str:
        return (f"| {v['n']} | {v['n_with_real_odds']}/{v['n_decisions']} | {v['roi']:+.4f} | "
                f"[{v['lo95']:+.4f}, {v['hi95']:+.4f}] | {v['p_pos']:.1%} |")

    report = f"""# Story 28.6a — Conviction Gate Real-Book ROI (Bovada American odds)

Strategy: games where `|p_classifier − p_run_diff| ≤ {DISAGREE_CAP}` (ensemble w={ENSEMBLE_W}); bet the model's
favored side. ROI on **actual Bovada American H2H odds** (load_devig_home_prob_bovada), profit per 1u =
(decimal−1) on a win, −1 on a loss. Bootstrap B={B_BOOT}. 2026 OOS.

`n_with_real_odds/n_decisions` = bets that had a real Bovada price (rest dropped — no priced market).

## VERDICT
{verdict}

| view | n bets | priced/total | real-book ROI | ROI 95% CI | P(ROI>0) |
|---|--:|--:|--:|--:|--:|
| threshold bets (operational) {_row(views['threshold_bets'])}
| all agreeing games {_row(views['all_agreeing_games'])}

## Context (from the local robustness preview)
- The model-vs-market **Brier** edge at cap 0.02 is within noise: gap −0.0102, 95% CI [−0.053, +0.032],
  ~68% bootstrap confidence. The edge is a real point-estimate plateau (caps 0.01 & 0.02) but NOT significant
  on n=85. This real-book ROI is the second, independent read on the same finding.
- Pre-committed go/no-go for 28.6b forward test: real-book ROI 95% lower-CI > 0 (primary = threshold bets).
- Reminder: roi_devig (vig-free) reported +0.68 in 28.2 — the gap between that and the real-book number here
  is exactly the vig the 28.3 magnitude work warned about.
"""
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report)
    print(report)
    print(f"\nWrote {OUT_MD.relative_to(REPO)}")


if __name__ == "__main__":
    main()
