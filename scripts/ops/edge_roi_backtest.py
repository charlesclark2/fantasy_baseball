#!/usr/bin/env python
"""A2.6 — Decisive edge test: does the α=0.30 h2h posterior actually MAKE MONEY vs the
Bovada closing line, after vig?

The aligned-alpha diagnostic found a modest real signal: against the sharp Bovada line the
model doesn't win standalone (Brier 0.203 vs 0.188) but a 30% blend improves log-loss
(α=0.30, smooth interior minimum) — genuine orthogonal information. BUT a log-loss gain is
NOT the same as a profitable edge after vig. This backtest answers the only question that
matters for releasing edges to the product: betting the posterior at the ACTUAL Bovada
American closing prices, is ROI positive and stable?

This is the HARDEST honest test — we bet at the CLOSING line, so there's no CLV tailwind
from beating the close. Profiting here means the model carries real predictive edge the
sharp closing market hasn't fully priced.

Method (per 2026 completed game with Bovada h2h prices + outcome):
  posterior = blend(consensus, bovada_devig_home_prob, alpha)
  EV_home   = posterior      * decimal(home_price) - 1
  EV_away   = (1-posterior)  * decimal(away_price) - 1
  bet the side with EV > threshold; settle at actual American odds.
Reports, by EV threshold: #bets, win%, flat-stake ROI, half-Kelly ROI, total units.

Sanity baseline: α=0.0 (bet the market itself) should return ≈ −vig — if it doesn't, the
prices/outcomes are misaligned. AUDIT ONLY — no writes.

Hand-off:  uv run python scripts/ops/edge_roi_backtest.py --since 2026-03-01 --alpha 0.30
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

import rescore_audit as ra  # noqa: E402
from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.scripts.load_layer3_features import load_devig_home_prob_bovada  # noqa: E402


def _american_to_decimal(price: float) -> float:
    return (price / 100.0 + 1.0) if price > 0 else (100.0 / abs(price) + 1.0)


def _backtest(posterior: np.ndarray, home_dec: np.ndarray, away_dec: np.ndarray,
              home_won: np.ndarray, thresholds: list[float], kelly_frac: float = 0.5) -> list[dict]:
    """For each EV threshold, bet the +EV side and settle at the actual odds."""
    ev_home = posterior * home_dec - 1.0
    ev_away = (1.0 - posterior) * away_dec - 1.0
    # Pick the better side per game.
    bet_home = ev_home >= ev_away
    ev_best = np.where(bet_home, ev_home, ev_away)
    dec_best = np.where(bet_home, home_dec, away_dec)
    p_best = np.where(bet_home, posterior, 1.0 - posterior)
    won = np.where(bet_home, home_won, 1.0 - home_won).astype(bool)

    rows = []
    for thr in thresholds:
        sel = np.ones(len(ev_best), dtype=bool) if thr <= -1.0 else (ev_best > thr)
        n = int(sel.sum())
        if n == 0:
            rows.append({"thr": thr, "n": 0})
            continue
        w = won[sel]
        d = dec_best[sel]
        # Flat stake: +（dec-1) on win, -1 on loss.
        flat_profit = np.where(w, d - 1.0, -1.0)
        flat_roi = float(flat_profit.sum() / n)
        # Fractional Kelly: f = EV / (dec - 1), clipped to [0, 1], scaled.
        f = np.clip(ev_best[sel] / (d - 1.0), 0.0, 1.0) * kelly_frac
        kelly_profit = np.where(w, f * (d - 1.0), -f)
        kelly_roi = float(kelly_profit.sum() / f.sum()) if f.sum() > 0 else float("nan")
        rows.append({
            "thr": thr, "n": n, "win_pct": float(w.mean()),
            "flat_roi": flat_roi, "flat_units": float(flat_profit.sum()),
            "kelly_roi": kelly_roi, "avg_p": float(p_best[sel].mean()),
        })
    return rows


def _print(label: str, rows: list[dict]) -> None:
    print(f"\n[{label}]")
    print(f"  {'EV>thr':>8}{'#bets':>8}{'win%':>9}{'flat ROI':>11}{'flat units':>12}{'½Kelly ROI':>12}")
    for r in rows:
        tag = " ALL" if r["thr"] <= -1.0 else f"{r['thr']*100:>5.1f}%"
        if r.get("n", 0) == 0:
            print(f"  {tag:>8}{0:>8}{'—':>9}{'—':>11}{'—':>12}{'—':>12}")
            continue
        print(f"  {tag:>8}{r['n']:>8}{r['win_pct']*100:>8.1f}%"
              f"{r['flat_roi']*100:>10.2f}%{r['flat_units']:>11.1f}u{r['kelly_roi']*100:>11.2f}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="h2h edge ROI backtest vs Bovada closing line (A2.6).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=int, default=None)
    g.add_argument("--since", type=str, default="2026-03-01")
    ap.add_argument("--end", type=str)
    ap.add_argument("--alpha", type=float, default=0.30, help="blend weight on the model (default 0.30)")
    ap.add_argument("--allow-pre-2026", action="store_true")
    args = ap.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = (end - timedelta(days=args.days)) if args.days else datetime.strptime(args.since, "%Y-%m-%d").date()
    window = f"{start.isoformat()} → {end.isoformat()}"
    if start < date(2026, 1, 1) and not args.allow_pre_2026:
        print(f"[REFUSING] {window} includes pre-2026 (in-sample) games; use --allow-pre-2026 to override.")
        return 1

    registry = yaml.safe_load((_REPO_ROOT / "betting_ml" / "models" / "model_registry.yaml").read_text())
    print(f"Loading + scoring completed games in {window}...")
    df = ra.load_features(min_games_played=15)
    df["game_date"] = ra.pd.to_datetime(df["game_date"]).dt.date
    df = df[(df["game_date"] >= start) & (df["game_date"] <= end)].sort_values("game_date").reset_index(drop=True)
    if df.empty:
        print("No games.")
        return 0
    scored = ra._score(df, registry)

    bov = load_devig_home_prob_bovada([int(x) for x in scored["game_pk"].tolist()], env="prod")
    bov = bov[bov["home_price"].notna() & bov["away_price"].notna()
              & bov["bovada_devig_home_prob"].notna()].copy()
    merged = scored.merge(
        bov[["game_pk", "bovada_devig_home_prob", "home_price", "away_price"]],
        on="game_pk", how="inner",
    )
    print(f"  {len(merged)} games with Bovada h2h prices + outcome")
    if merged.empty:
        return 0

    consensus = merged["consensus_win_prob"].to_numpy(dtype=float)
    devig = merged["bovada_devig_home_prob"].to_numpy(dtype=float)
    home_dec = np.array([_american_to_decimal(float(p)) for p in merged["home_price"]])
    away_dec = np.array([_american_to_decimal(float(p)) for p in merged["away_price"]])
    home_won = (merged["home_final_score"] > merged["away_final_score"]).astype(float).to_numpy()

    thresholds = [-1.0, 0.0, 0.01, 0.02, 0.03, 0.05]  # -1.0 = bet ALL games (sanity row)
    print("\n" + "=" * 78)
    print(f"  h2h EDGE ROI BACKTEST vs Bovada closing line — {window}  (n={len(merged)})")
    print("  Betting AT the close (no CLV tailwind). Positive flat ROI = real edge after vig.")
    print("=" * 78)

    # Sanity: the book's implied hold (vig). And α=0 bets the market itself — at α=0
    # EV_home==EV_away exactly, so the "ALL" row degenerates to "bet home every game"
    # (ignore it); the VALID α=0 sanity is "EV>0 → ~0 bets" (you can't beat the market
    # with the market). If EV>0 finds many +EV bets at α=0, the prices are misaligned.
    implied_hold = float(np.mean(1.0 / home_dec + 1.0 / away_dec) - 1.0)
    print(f"\n  Book implied hold (vig): {implied_hold*100:.2f}%  "
          f"(home-win rate in set: {home_won.mean()*100:.1f}%)")
    _print("SANITY α=0.00 (valid check = EV>0 row finds ~0 bets; ignore the ALL row)",
           _backtest(devig.copy(), home_dec, away_dec, home_won, thresholds))

    post = np.array([compute_posterior(float(c), float(m), args.alpha) for c, m in zip(consensus, devig)])
    _print(f"MODEL POSTERIOR α={args.alpha:.2f} (the tuned blend)",
           _backtest(post, home_dec, away_dec, home_won, thresholds))

    print("\n" + "-" * 78)
    print("  READ: a REAL edge has flat ROI > 0 that IMPROVES as the EV threshold rises")
    print("  (keeping only high-conviction bets) ⇒ release α-blend h2h edges (Bovada-gated).")
    print("  ROI that hovers near 0 and DECLINES with the threshold ⇒ the model's biggest")
    print("  disagreements are where the sharp close is right ⇒ no bettable edge, keep the")
    print("  guard engaged. (½-Kelly col can spike on a few high-variance dog hits — trust")
    print("  flat ROI.) AUDIT ONLY — nothing written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
