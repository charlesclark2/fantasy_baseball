"""Story 28.6b — Conviction-gate H2H live-tracking monitor.

Tracks the 28.2 disagreement-gate selective strategy on REAL prices, forward-only.
Queries daily_model_predictions for games flagged `layer4_h2h_conviction_flag = TRUE`
(the two independent estimators agree: |calibrated_win_prob − P_run_diff(home)| <= 0.02)
that ALSO took a side (layer4_h2h_decision in home/away), then applies the
pre-committed kill criterion below.

WHY THIS EXISTS (do not lose the framing): the 28.2 backtest edge is NOT proven —
the model-vs-market Brier gap is within noise on n=85 (95% CI crosses zero, ~68%
bootstrap confidence) and roi_devig +0.68 is vig-FREE. Only a forward test on real
Bovada prices can confirm or kill it. SHADOW/manual until live CONFIRM — no
automated bets fire off this monitor.

  CONFIRM: n >= N_FULL settled bets, 95% lower-CI real-book ROI > 0, AND
           conviction-subset model Brier < market Brier on those games.
  KILL (full):    n = N_FULL, 95% lower-CI real-book ROI <= 0.
  KILL (tripwire): at n >= N_TRIPWIRE, real-book win rate < avg break-even.

ROI uses actual Bovada American odds (layer4_h2h_bovada_ml_home/away), NOT roi_devig.

PROVISIONAL thresholds (N_FULL / N_TRIPWIRE) — finalize from the 28.6a real-book-ROI
power analysis (h2h_conviction_gate_28_6a.md) and update model_registry.yaml in lockstep.

Run from project root (prod data required):
    uv run python scripts/ops/monitor_conviction_h2h.py --schema betting_ml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

# ---------------------------------------------------------------------------
# Kill-criterion thresholds — PROVISIONAL (conviction qualifies ~14% of games, so
# accrual is slower than magnitude's). Finalize N_FULL/N_TRIPWIRE from 28.6a power;
# keep in lockstep with model_registry.yaml home_win.conviction_kill_criterion.
# ---------------------------------------------------------------------------
KILL_N_FULL = 60
KILL_N_TRIPWIRE = 20
ATTRIBUTION_START = "2026-06-11"  # set to the actual deploy date of the conviction wiring


_CONVICTION_QUERY = """
SELECT
    dmp.score_date,
    dmp.game_pk,
    dmp.layer4_h2h_decision,            -- 'home' or 'away'
    dmp.layer4_h2h_conviction_disagree, -- |cal_win - p_run_diff|
    dmp.calibrated_win_prob,            -- model P(home win)
    dmp.h2h_market_implied_prob,        -- de-vigged consensus P(home win)
    dmp.layer4_h2h_bovada_ml_home,      -- actual Bovada American ML (home side)
    dmp.layer4_h2h_bovada_ml_away,      -- actual Bovada American ML (away side)
    mgr.home_team_won                   -- 1 = home won, 0 = away won (NULL = not settled)
FROM baseball_data.{ml_schema}.daily_model_predictions dmp
LEFT JOIN baseball_data.betting.mart_game_results mgr
    ON mgr.game_pk = dmp.game_pk
WHERE dmp.layer4_h2h_conviction_flag = TRUE
  AND dmp.layer4_h2h_decision IN ('home', 'away')
  AND dmp.score_date >= '{start_date}'
  AND dmp.prediction_type = 'post_lineup'
ORDER BY dmp.score_date, dmp.game_pk
"""


def _american_to_decimal(american: int | None) -> float | None:
    if american is None:
        return None
    return 1.0 + (american / 100.0 if american > 0 else 100.0 / abs(american))


def _roi_95_lower_ci(profits: list[float]) -> tuple[float, float, float]:
    n = len(profits)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(profits, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else float("nan")
    lower_ci = mean - 1.645 * std / np.sqrt(n) if n > 1 else float("nan")
    return mean, std, lower_ci


def _brier(probs: list[float], outcomes: list[float]) -> float:
    if not probs:
        return float("nan")
    return float(np.mean((np.array(probs, float) - np.array(outcomes, float)) ** 2))


def run_monitor(ml_schema: str, min_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_CONVICTION_QUERY.format(ml_schema=ml_schema, start_date=min_date))
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    print("\n=== Story 28.6b — Conviction-Gate H2H Kill-Criterion Monitor ===")
    print(f"Attribution start: {min_date}   Schema: baseball_data.{ml_schema}")
    print("SHADOW/manual — no automated bets fire off this monitor until live CONFIRM.")
    print(f"Total conviction rows fetched: {len(rows)}")

    seen: set[tuple] = set()
    deduped = []
    for r in rows:
        key = (r["score_date"], r["game_pk"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    rows = deduped
    print(f"Unique (date, game_pk) conviction triggers: {len(rows)}")

    settled = [r for r in rows if r["home_team_won"] is not None]
    pending = [r for r in rows if r["home_team_won"] is None]
    print(f"Settled: {len(settled)}   Pending: {len(pending)}\n")
    if not settled:
        print("No settled conviction bets yet — nothing to evaluate (expected early in accrual).")
        return

    profits: list[float] = []
    win_indicators: list[float] = []
    break_even_rates: list[float] = []
    model_probs: list[float] = []
    market_probs: list[float] = []
    actual_home_outcomes: list[float] = []
    skipped_no_odds = 0

    for r in settled:
        decision = (r.get("layer4_h2h_decision") or "").lower()
        home_won = float(r["home_team_won"])
        if decision == "home":
            american, bet_won = r.get("layer4_h2h_bovada_ml_home"), home_won
        elif decision == "away":
            american, bet_won = r.get("layer4_h2h_bovada_ml_away"), 1.0 - home_won
        else:
            skipped_no_odds += 1
            continue
        decimal = _american_to_decimal(american)
        if decimal is None:
            skipped_no_odds += 1
            continue
        profits.append((decimal - 1.0) if bet_won > 0.5 else -1.0)
        win_indicators.append(float(bet_won > 0.5))
        break_even_rates.append(1.0 / decimal)
        if r.get("calibrated_win_prob") is not None:
            model_probs.append(float(r["calibrated_win_prob"]))
            market_probs.append(float(r["h2h_market_implied_prob"]))
            actual_home_outcomes.append(home_won)

    n = len(profits)
    if skipped_no_odds:
        print(f"  Skipped {skipped_no_odds} settled row(s) with no Bovada odds on file.\n")
    if n == 0:
        print("No settled conviction bets with Bovada odds available — cannot evaluate.")
        return

    mean_roi, std_roi, lower_ci = _roi_95_lower_ci(profits)
    win_rate = float(np.mean(win_indicators))
    avg_be = float(np.mean(break_even_rates))
    print(f"--- Real-book ROI (n={n} settled bets) ---")
    print(f"  Win rate:          {win_rate:.3f}  (break-even avg: {avg_be:.3f})")
    print(f"  Mean ROI per bet:  {mean_roi:+.4f}")
    print(f"  95% lower-CI ROI:  {lower_ci:+.4f}")

    model_brier = _brier(model_probs, actual_home_outcomes)
    market_brier = _brier(market_probs, actual_home_outcomes)
    print(f"\n--- Brier (conviction-subset, n={len(model_probs)}) ---")
    print(f"  Model Brier:   {model_brier:.4f}   Market Brier:  {market_brier:.4f}")
    print(f"  Verdict:       {'MODEL < MARKET ✓' if model_brier < market_brier else 'model >= market ✗'}")

    print(f"\n--- Early Tripwire (first {KILL_N_TRIPWIRE}) ---")
    if n >= KILL_N_TRIPWIRE:
        trip_win_rate = float(np.mean(win_indicators[:KILL_N_TRIPWIRE]))
        trip_avg_be = float(np.mean(break_even_rates[:KILL_N_TRIPWIRE]))
        tripwire_fires = trip_win_rate < trip_avg_be
        print(f"  Win rate over first {KILL_N_TRIPWIRE}: {trip_win_rate:.3f}  (break-even {trip_avg_be:.3f})")
        print(f"  Tripwire fires: {'YES — KILL signal' if tripwire_fires else 'No'}")
    else:
        print(f"  Not yet reached {KILL_N_TRIPWIRE} settled bets ({n}/{KILL_N_TRIPWIRE}).")
        tripwire_fires = False

    print(f"\n--- Full Verdict (gate: n={KILL_N_FULL}, PROVISIONAL — finalize from 28.6a) ---")
    if n >= KILL_N_FULL:
        if lower_ci > 0 and model_brier < market_brier:
            verdict = ("✅ CONFIRM — conviction gate beats real prices on the forward sample. "
                       "Promote from shadow/informational to a TRUSTED manual-bet signal "
                       "(bets remain placed by hand — US manual-only; no automated placement).")
        else:
            verdict = "❌ KILL — conviction gate fails kill criterion"
            if not lower_ci > 0:
                verdict += f"\n  ROI lower-CI {lower_ci:+.4f} ≤ 0"
            if not model_brier < market_brier:
                verdict += f"\n  Model Brier {model_brier:.4f} ≥ market {market_brier:.4f}"
    elif tripwire_fires:
        verdict = f"❌ KILL (early tripwire at n={KILL_N_TRIPWIRE}) — win rate below break-even"
    else:
        verdict = (f"⏳ ACCRUING — {n}/{KILL_N_FULL} settled bets. "
                   f"~{max(KILL_N_FULL - n, 0)} more needed for full verdict. No tripwire fired.")
    print(f"  {verdict}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 28.6b conviction-gate H2H kill-criterion monitor")
    parser.add_argument("--min-date", default=ATTRIBUTION_START,
                        help=f"Only count bets on or after this date (default: {ATTRIBUTION_START})")
    parser.add_argument("--schema", default=None,
                        help="Override Snowflake ML schema (default: auto-detect via TARGET_ENV)")
    args = parser.parse_args()
    if args.schema:
        schema = args.schema
    else:
        from betting_ml.utils.ml_env import ml_schema
        schema = ml_schema()
        schema = schema.split(".")[-1] if "." in schema else schema
    run_monitor(schema, args.min_date)


if __name__ == "__main__":
    main()
