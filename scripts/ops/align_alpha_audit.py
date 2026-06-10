#!/usr/bin/env python
"""A2.6 — Aligned alpha diagnostic: what would best_alpha be if the tuner used the
DEPLOYED CONSENSUS instead of the run_diff-NGBoost-only signal?

`run_probability_layer.py` tunes alpha via CV on the NGBoost run_diff-only P(home),
but predict_today applies that alpha to the calibrated CONSENSUS (NGB run_diff + XGB
classifier). The 2026-06-10 audit showed the consensus beats the market on home_win
(Brier 0.198 vs 0.245) while the run_diff-only signal does not — which is why best_alpha
sits at 0 and the app shows no edge. This script re-tunes alpha on the actual deployed
consensus over 2026 OOS to quantify (a) how far alpha lifts off 0 and (b) the resulting
edge distribution — so we can decide whether to release the A2.5 edge guard.

It scores deployed models via rescore_audit._score (same impute→reindex→score path),
then runs tune_alpha on the consensus for h2h, totals, and the combined book — reporting
each best alpha, the log-loss at alpha=0 (market-only) vs best, and the implied edge
distribution at the chosen alpha. AUDIT ONLY — no Snowflake writes.

Read the alpha magnitude as a leakage check too: a modest h2h alpha (~0.2–0.4) is
believable; ≥0.7 is a red flag that the consensus's market-beating margin is inflated by
feature leakage (cross-reference the strict-prior feature spot-check).

Hand-off (loads + scores the feature store; > 1 min):
    uv run python scripts/ops/align_alpha_audit.py --since 2026-03-01
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv  # noqa: E402
load_dotenv()

import rescore_audit as ra          # noqa: E402
import model_health_metrics as mh   # noqa: E402
from betting_ml.utils.probability_layer import (  # noqa: E402
    tune_alpha, compute_posterior, compute_actionable_edge,
)


def _tune_block(name: str, model_p: np.ndarray, market_p: np.ndarray, outcome: np.ndarray) -> dict:
    """Tune alpha for one market and report the log-loss curve + edge distribution."""
    mask = ~np.isnan(model_p) & ~np.isnan(market_p) & ~np.isnan(outcome)
    mp, kp, oc = model_p[mask], market_p[mask], outcome[mask]
    n = len(mp)
    if n < 100:
        return {"name": name, "n": n, "best_alpha": None, "note": f"only {n} games (<100); tuner would default 0.5"}

    best_alpha, scores = tune_alpha(mp, kp, oc)
    by_alpha = {round(s["alpha"], 2): s["log_loss"] for s in scores}
    ll_market = by_alpha.get(0.0)
    ll_best = by_alpha[round(best_alpha, 2)]

    # Edge distribution at the chosen alpha (actionable edge = posterior − market).
    post = np.array([compute_posterior(float(m), float(k), best_alpha) for m, k in zip(mp, kp)])
    edge = post - kp
    return {
        "name": name, "n": n, "best_alpha": best_alpha,
        "ll_market": ll_market, "ll_best": ll_best, "ll_gain": (ll_market - ll_best) if ll_market else None,
        "model_brier": mh._brier(mp, oc), "market_brier": mh._brier(kp, oc),
        "edge_mean_abs": float(np.mean(np.abs(edge))),
        "edge_ge_3pct": int(np.sum(np.abs(edge) >= 0.03)),
        "edge_ge_5pct": int(np.sum(np.abs(edge) >= 0.05)),
        "curve": by_alpha,
    }


def _print_block(b: dict) -> None:
    print(f"\n[{b['name']}]  n={b['n']}")
    if b.get("best_alpha") is None:
        print(f"   {b.get('note')}")
        return
    print(f"   model Brier={b['model_brier']:.4f}   market Brier={b['market_brier']:.4f}   "
          f"(model {'beats' if b['model_brier'] < b['market_brier'] else 'does NOT beat'} market)")
    print(f"   best_alpha = {b['best_alpha']:.2f}   "
          f"log-loss: market(α=0)={b['ll_market']:.4f} → best={b['ll_best']:.4f}  (gain {b['ll_gain']:+.4f})")
    print(f"   at α={b['best_alpha']:.2f}: mean|edge|={b['edge_mean_abs']:.4f}   "
          f"|edge|≥3%: {b['edge_ge_3pct']}/{b['n']} games   |edge|≥5%: {b['edge_ge_5pct']}/{b['n']}")
    curve = "  ".join(f"{a:.1f}:{ll:.4f}" for a, ll in sorted(b["curve"].items()))
    print(f"   log-loss curve: {curve}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Aligned alpha diagnostic on the deployed consensus (A2.6).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=None)
    g.add_argument("--since", type=str, default="2026-03-01")
    ap.add_argument("--end", type=str)
    ap.add_argument("--allow-pre-2026", action="store_true")
    ap.add_argument("--market", choices=["consensus", "bovada"], default="consensus",
                    help="h2h market baseline: 'consensus' (home_win_prob_consensus, can be degraded) "
                         "or 'bovada' (sharp closing de-vig line — the honest edge test).")
    args = ap.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = (end - timedelta(days=args.days)) if args.days else datetime.strptime(args.since, "%Y-%m-%d").date()
    window = f"{start.isoformat()} → {end.isoformat()}"
    if start < date(2026, 1, 1) and not args.allow_pre_2026:
        print(f"[REFUSING] {window} includes pre-2026 (in-sample) games; use --allow-pre-2026 to override.")
        return 1

    registry = yaml.safe_load((_REPO_ROOT / "betting_ml" / "models" / "model_registry.yaml").read_text())
    print(f"Loading + scoring completed games in {window} (deployed consensus)...")
    df = ra.load_features(min_games_played=15)
    df["game_date"] = ra.pd.to_datetime(df["game_date"]).dt.date
    df = df[(df["game_date"] >= start) & (df["game_date"] <= end)].sort_values("game_date").reset_index(drop=True)
    if df.empty:
        print("No completed games in window.")
        return 0
    scored = ra._score(df, registry)
    print(f"  {len(scored)} games scored")

    home = scored["home_final_score"].to_numpy(dtype=float)
    away = scored["away_final_score"].to_numpy(dtype=float)
    total_actual = home + away

    # Resolve the h2h market baseline. The consensus column (home_win_prob_consensus) can
    # be degraded/near-flat (Brier well above the ~0.198 sharp 2026 line); --market bovada
    # tests against the actual sharp closing line we'd bet — the honest edge check.
    h2h_market = scored["h2h_market_implied_prob"].to_numpy(dtype=float)
    market_label = "consensus (home_win_prob_consensus)"
    if args.market == "bovada":
        from betting_ml.scripts.load_layer3_features import load_devig_home_prob_bovada
        gpks = [int(x) for x in scored["game_pk"].tolist()]
        bov = load_devig_home_prob_bovada(gpks, env="prod")
        bmap = {int(g): float(p) for g, p in zip(bov["game_pk"], bov["bovada_devig_home_prob"])
                if ra.pd.notna(p)}
        h2h_market = np.array([bmap.get(int(g), np.nan) for g in scored["game_pk"]])
        market_label = "sharp Bovada de-vig closing line"
        print(f"  Bovada h2h coverage: {int(np.sum(~np.isnan(h2h_market)))}/{len(scored)} games")

    # h2h: deployed calibrated consensus vs the resolved market home prob.
    h2h = _tune_block(
        f"h2h (consensus vs {market_label})",
        scored["calibrated_win_prob"].to_numpy(dtype=float),
        h2h_market,
        (home > away).astype(float),
    )
    # totals: model P(over) vs market P(over), outcome = actual total > line.
    line = scored["total_line_consensus"].to_numpy(dtype=float)
    totals = _tune_block(
        "totals (model P(over) vs market)",
        scored["totals_p_over"].to_numpy(dtype=float),
        scored["over_prob_consensus"].to_numpy(dtype=float),
        np.where(~np.isnan(line), (total_actual > line).astype(float), np.nan),
    )
    # combined book (how run_probability_layer sets the single global alpha).
    def _stack(a, b, key):
        return np.concatenate([a[key], b[key]])
    h2h_arrays = {
        "m": scored["calibrated_win_prob"].to_numpy(dtype=float),
        "k": h2h_market,
        "o": (home > away).astype(float),
    }
    tot_arrays = {
        "m": scored["totals_p_over"].to_numpy(dtype=float),
        "k": scored["over_prob_consensus"].to_numpy(dtype=float),
        "o": np.where(~np.isnan(line), (total_actual > line).astype(float), np.nan),
    }
    combined = _tune_block(
        "combined (h2h + totals — matches run_probability_layer's global alpha)",
        np.concatenate([h2h_arrays["m"], tot_arrays["m"]]),
        np.concatenate([h2h_arrays["k"], tot_arrays["k"]]),
        np.concatenate([h2h_arrays["o"], tot_arrays["o"]]),
    )

    print("\n" + "=" * 78)
    print(f"  ALIGNED ALPHA DIAGNOSTIC — {window}   (current deployed best_alpha = 0.0)")
    print("=" * 78)
    for b in (h2h, totals, combined):
        _print_block(b)

    print("\n" + "-" * 78)
    ha = h2h.get("best_alpha")
    if ha is not None:
        if ha == 0.0:
            print("  h2h alpha tunes to 0 even on the consensus → no h2h edge to release (market wins).")
        elif ha >= 0.7:
            print(f"  ⚠ h2h alpha={ha:.2f} is HIGH — likely inflated by feature leakage; cross-check the")
            print("    strict-prior feature spot-check before releasing the edge guard.")
        else:
            print(f"  h2h alpha={ha:.2f} (believable) → real, modest edge to release once leakage is cleared.")
    print("  AUDIT ONLY — nothing written. To deploy: update alpha_tuning_results / align")
    print("  run_probability_layer's h2h model prob to the consensus, then re-run it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
