"""
diagnose_16b5_gate.py — Epic 16B.5 combined-μ decision gate (fast/in-sample path)

Loads the Layer 3 feature matrix, fits per-signal in-sample Poisson GLMs (same
protocol as compute_stacking_weights.py), combines with the recomputed stacking
weights, and reports mean combined-μ for May-2026.

Gate: mean combined-μ > 8.85 → Epic 17 confirmed; ≤ 8.85 → proceed to 16B.6.

Usage:
    uv run python betting_ml/scripts/diagnose_16b5_gate.py --env prod
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from betting_ml.scripts.load_layer3_features import load_layer3_features          # noqa: E402
from betting_ml.scripts.compute_stacking_weights import (                         # noqa: E402
    _per_game_signal_dist, combine_distributional_signals,
)

_WEIGHTS_PATH = _ROOT / "betting_ml" / "models" / "layer3" / "stacking_weights.json"
_GATE         = 8.85
_ACTUAL_MEAN  = 8.61   # documented May-2026 actual mean from Epic 10.8


def main(env: str = "prod") -> None:
    weights_data = json.loads(_WEIGHTS_PATH.read_text())
    weights = {k: v["weight"] for k, v in weights_data["targets"]["total_runs"].items()}
    promoted = sorted(weights)

    print(f"\n{'=' * 60}")
    print("EPIC 16B.5 — COMBINED-μ GATE (fast / in-sample)")
    print(f"{'=' * 60}")
    print(f"  Stacking weights : { {k: round(v, 3) for k, v in weights.items()} }")
    print(f"  Gate threshold   : ≤ {_GATE}")
    print(f"  Loading Layer 3 feature matrix (env={env})...")

    df = load_layer3_features(start_date="2021-01-01", env=env)
    print(f"  Loaded {len(df):,} games ({df['game_year'].min()}–{df['game_year'].max()})")

    # Fit per-signal in-sample Poisson GLMs → per-game (μ, σ) on total_runs scale
    print(f"\n  Fitting in-sample GLMs for: {promoted}")
    dist   = {label: _per_game_signal_dist(label, df, "total_runs") for label in promoted}
    mus    = {label: dist[label][0] for label in promoted}
    sigmas = {label: dist[label][1] for label in promoted}

    combined_mu, combined_sigma = combine_distributional_signals(mus, sigmas, weights)

    # Filter to May-2026
    game_dates = df["game_date"]
    may_mask = (
        (game_dates >= "2026-05-01") &
        (game_dates <  "2026-06-01") &
        (df["total_runs"].notna())
    ).to_numpy()

    n_games    = int(may_mask.sum())
    mean_mu    = float(np.mean(combined_mu[may_mask]))
    mean_sigma = float(np.mean(combined_sigma[may_mask]))
    mean_actual = float(df.loc[may_mask, "total_runs"].mean())
    mean_bias  = mean_mu - mean_actual

    print(f"\n{'=' * 60}")
    print(f"  May-2026 results ({n_games} games)")
    print(f"{'=' * 60}")
    print(f"  mean_combined_mu  : {mean_mu:.4f}")
    print(f"  mean_actual       : {mean_actual:.4f}  (historical ref: {_ACTUAL_MEAN})")
    print(f"  mean_bias         : {mean_bias:+.4f}")
    print(f"  mean_combined_sig : {mean_sigma:.4f}")

    print(f"\n  Per-signal May-2026 GLM-predicted means:")
    for label in promoted:
        print(f"    {label:12s}: {float(np.mean(mus[label][may_mask])):.4f}")

    gate_pass = mean_mu <= _GATE
    print(f"\n{'=' * 60}")
    print(f"  Gate (≤ {_GATE}): {'PASS ✅  → proceed to 16B.6' if gate_pass else 'FAIL ❌  → Epic 17 confirmed'}")
    print(f"{'=' * 60}\n")

    # All-2026 for comparison
    yr2026 = (df["game_year"] == 2026) & (df["total_runs"].notna())
    yr2026 = yr2026.to_numpy()
    print(f"  All-2026 mean_combined_mu : {float(np.mean(combined_mu[yr2026])):.4f}  "
          f"(actual: {float(df.loc[yr2026, 'total_runs'].mean()):.4f})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="prod", choices=["prod", "dev"])
    args = parser.parse_args()
    main(env=args.env)
