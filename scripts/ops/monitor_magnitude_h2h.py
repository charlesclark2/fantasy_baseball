"""Story 28.3 — Magnitude H2H live-tracking monitor.

Queries daily_model_predictions for all 'magnitude'-rule H2H triggers that have
settled post-2026-06-04, then applies the pre-committed kill criterion:

  CONFIRM: n >= 150 settled bets, 95% lower-CI real-book ROI > 0, AND
           magnitude-subset model Brier < market Brier on those games.

  KILL (full):    n = 150, 95% lower-CI real-book ROI <= 0.

  KILL (tripwire): at n >= 50, real-book win rate < avg break-even (implied by
                   actual Bovada American odds) over those first 50 bets.

ROI is computed on actual Bovada American odds (layer4_h2h_bovada_ml_home /
layer4_h2h_bovada_ml_away), not the de-vigged consensus probability.

Run from project root (prod data required — use --schema to target prod explicitly):
    uv run python scripts/ops/monitor_magnitude_h2h.py --schema betting_ml
    uv run python scripts/ops/monitor_magnitude_h2h.py --schema betting_ml --min-date 2026-06-04
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
# Kill-criterion thresholds (pre-committed; do not change without updating
# model_registry.yaml home_win.kill_criterion at the same time).
# ---------------------------------------------------------------------------
KILL_N_FULL = 150          # n at which the full CONFIRM/KILL verdict fires
KILL_N_TRIPWIRE = 50       # n for the early win-rate tripwire
CONFIRM_CI_LEVEL = 0.95    # two-tailed; lower-tail z at 95% CI = 1.645
ATTRIBUTION_START = "2026-06-23"  # only bets placed on or after this date count; RESET on E13.11 de-leaked v6 home_win champion swap (was 2026-06-12) — keep in lockstep with home_win.kill_criterion.attribution_start in model_registry.yaml


# ---------------------------------------------------------------------------
# Snowflake query
# ---------------------------------------------------------------------------
_MAGNITUDE_QUERY = """
SELECT
    dmp.score_date,
    dmp.game_pk,
    dmp.layer4_h2h_decision,     -- 'home' or 'away'
    dmp.layer4_h2h_rule,         -- should be 'magnitude'
    dmp.calibrated_win_prob,     -- model P(home win)
    dmp.h2h_market_implied_prob, -- de-vigged consensus P(home win)
    dmp.layer4_h2h_bovada_ml_home,  -- actual Bovada American ML (home side)
    dmp.layer4_h2h_bovada_ml_away,  -- actual Bovada American ML (away side)
    mgr.home_team_won            -- 1 = home won, 0 = away won (NULL = not settled)
FROM baseball_data.{ml_schema}.daily_model_predictions dmp
LEFT JOIN baseball_data.betting.mart_game_results mgr
    ON mgr.game_pk = dmp.game_pk
WHERE dmp.layer4_h2h_rule = 'magnitude'
  AND dmp.score_date >= '{start_date}'
  AND dmp.prediction_type = 'post_lineup'  -- canonical post-lineup run only
ORDER BY dmp.score_date, dmp.game_pk
"""


def _american_to_decimal(american: int | None) -> float | None:
    """Convert American moneyline to decimal odds (return per unit staked)."""
    if american is None:
        return None
    if american > 0:
        return 1.0 + american / 100.0
    else:
        return 1.0 + 100.0 / abs(american)


def _roi_95_lower_ci(profits: list[float]) -> tuple[float, float, float]:
    """Return (mean_roi, std_roi, lower_95_ci) for a list of per-bet profits."""
    n = len(profits)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    arr = np.array(profits, dtype=float)
    mean = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if n > 1 else float("nan")
    # 95% lower bound: one-tailed z = 1.645 (same as lower half of two-tailed 95% CI)
    z = 1.645
    lower_ci = mean - z * std / np.sqrt(n) if n > 1 else float("nan")
    return mean, std, lower_ci


def _brier(probs: list[float], outcomes: list[float]) -> float:
    """Mean squared error between probabilities and binary outcomes."""
    if not probs:
        return float("nan")
    arr = np.array(probs, dtype=float)
    out = np.array(outcomes, dtype=float)
    return float(np.mean((arr - out) ** 2))


def run_monitor(ml_schema: str, min_date: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        query = _MAGNITUDE_QUERY.format(ml_schema=ml_schema, start_date=min_date)
        cur.execute(query)
        cols = [d[0].lower() for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

    print(f"\n=== Story 28.3 — Magnitude H2H Kill-Criterion Monitor ===")
    print(f"Attribution start: {min_date}   Schema: baseball_data.{ml_schema}")
    print(f"Total magnitude rows fetched: {len(rows)}")

    # Deduplicate: keep only the latest prediction per (score_date, game_pk) in case
    # multiple runs exist (sensor + scheduled).  We pick the post_lineup run above via
    # prediction_type filter; this dedup guards against sensor re-fires on the same game.
    seen: set[tuple] = set()
    deduped = []
    for r in rows:
        key = (r["score_date"], r["game_pk"])
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    rows = deduped
    print(f"Unique (date, game_pk) magnitude triggers: {len(rows)}")

    # Split into settled vs pending
    settled = [r for r in rows if r["home_team_won"] is not None]
    pending = [r for r in rows if r["home_team_won"] is None]
    print(f"Settled: {len(settled)}   Pending: {len(pending)}\n")

    if not settled:
        print("No settled magnitude bets yet — nothing to evaluate.")
        return

    # --- Build per-bet profit series ----------------------------------------
    profits: list[float] = []
    win_indicators: list[float] = []
    break_even_rates: list[float] = []
    model_probs: list[float] = []
    market_probs: list[float] = []
    actual_home_outcomes: list[float] = []

    skipped_no_odds = 0

    for r in settled:
        decision = (r.get("layer4_h2h_decision") or "").lower()
        home_won = float(r["home_team_won"])  # 1.0 = home won

        # Pick the appropriate Bovada American odds for the side we'd bet
        if decision == "home":
            american = r.get("layer4_h2h_bovada_ml_home")
            bet_won = home_won
        elif decision == "away":
            american = r.get("layer4_h2h_bovada_ml_away")
            bet_won = 1.0 - home_won
        else:
            skipped_no_odds += 1
            continue

        decimal = _american_to_decimal(american)
        if decimal is None:
            skipped_no_odds += 1
            continue

        # Profit: +( decimal - 1 ) on a win, -1 on a loss  (1-unit stake)
        profit = (decimal - 1.0) if bet_won > 0.5 else -1.0
        profits.append(profit)
        win_indicators.append(float(bet_won > 0.5))
        break_even_rates.append(1.0 / decimal)

        # For Brier score: we always track P(home win) vs home_won regardless of
        # which side the model bet on.
        if r.get("calibrated_win_prob") is not None:
            model_probs.append(float(r["calibrated_win_prob"]))
            market_probs.append(float(r["h2h_market_implied_prob"]))
            actual_home_outcomes.append(home_won)

    n = len(profits)
    if skipped_no_odds:
        print(f"  Skipped {skipped_no_odds} settled row(s) with no Bovada odds on file.\n")

    if n == 0:
        print("No settled bets with Bovada odds available — cannot evaluate.")
        return

    # --- ROI stats -----------------------------------------------------------
    mean_roi, std_roi, lower_ci = _roi_95_lower_ci(profits)
    win_rate = float(np.mean(win_indicators))
    avg_be = float(np.mean(break_even_rates))

    print(f"--- Real-book ROI (n={n} settled bets) ---")
    print(f"  Win rate:          {win_rate:.3f}  (break-even avg: {avg_be:.3f})")
    print(f"  Mean ROI per bet:  {mean_roi:+.4f}")
    print(f"  Std ROI:           {std_roi:.4f}")
    print(f"  95% lower-CI ROI:  {lower_ci:+.4f}")

    # --- Brier scores -------------------------------------------------------
    model_brier = _brier(model_probs, actual_home_outcomes)
    market_brier = _brier(market_probs, actual_home_outcomes)
    print(f"\n--- Brier Scores (magnitude-subset, n={len(model_probs)}) ---")
    print(f"  Model Brier:   {model_brier:.4f}")
    print(f"  Market Brier:  {market_brier:.4f}")
    brier_edge = "MODEL < MARKET ✓" if model_brier < market_brier else "model >= market ✗"
    print(f"  Verdict:       {brier_edge}")

    # --- Tripwire (first 50 settled bets) -----------------------------------
    print(f"\n--- Early Tripwire (n={min(n, KILL_N_TRIPWIRE)} of first {KILL_N_TRIPWIRE}) ---")
    if n >= KILL_N_TRIPWIRE:
        trip_wins = win_indicators[:KILL_N_TRIPWIRE]
        trip_be   = break_even_rates[:KILL_N_TRIPWIRE]
        trip_win_rate = float(np.mean(trip_wins))
        trip_avg_be   = float(np.mean(trip_be))
        tripwire_fires = trip_win_rate < trip_avg_be
        print(f"  Win rate over first {KILL_N_TRIPWIRE}: {trip_win_rate:.3f}")
        print(f"  Avg break-even rate:               {trip_avg_be:.3f}")
        print(f"  Tripwire fires: {'YES — KILL signal' if tripwire_fires else 'No'}")
    else:
        print(f"  Not yet reached {KILL_N_TRIPWIRE} settled bets ({n}/{KILL_N_TRIPWIRE}).")
        tripwire_fires = False

    # --- Full CONFIRM / KILL verdict ----------------------------------------
    print(f"\n--- Full Verdict (gate: n={KILL_N_FULL}) ---")
    if n >= KILL_N_FULL:
        confirm_roi_pass   = lower_ci > 0
        confirm_brier_pass = model_brier < market_brier
        if confirm_roi_pass and confirm_brier_pass:
            verdict = "✅ CONFIRM — deploy magnitude H2H (set automated_bets: true after review)"
        else:
            verdict = "❌ KILL — magnitude H2H fails kill criterion"
            if not confirm_roi_pass:
                verdict += f"\n  ROI lower-CI {lower_ci:+.4f} ≤ 0"
            if not confirm_brier_pass:
                verdict += f"\n  Model Brier {model_brier:.4f} ≥ market {market_brier:.4f}"
    elif tripwire_fires:
        verdict = f"❌ KILL (early tripwire at n={KILL_N_TRIPWIRE}) — win rate below break-even"
    else:
        remaining = max(KILL_N_FULL - n, 0)
        verdict = (
            f"⏳ ACCRUING — {n}/{KILL_N_FULL} settled bets. "
            f"~{remaining} more needed for full verdict. "
            f"No tripwire fired."
        )
    print(f"  {verdict}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 28.3 magnitude H2H kill-criterion monitor")
    parser.add_argument(
        "--min-date",
        default=ATTRIBUTION_START,
        help=f"Only count bets on or after this date (default: {ATTRIBUTION_START})",
    )
    parser.add_argument(
        "--schema",
        default=None,
        help="Override Snowflake ML schema (default: auto-detect via TARGET_ENV)",
    )
    args = parser.parse_args()

    # Resolve schema the same way predict_today.py does via ml_env
    if args.schema:
        schema = args.schema
    else:
        from betting_ml.utils.ml_env import ml_schema
        schema = ml_schema()
        # Strip "baseball_data." prefix if present — the query uses schema name only
        schema = schema.split(".")[-1] if "." in schema else schema

    run_monitor(schema, args.min_date)


if __name__ == "__main__":
    main()
