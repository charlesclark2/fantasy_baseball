"""
totals_2026_gate_check.py — Epic 10.6 follow-up decision gate.

Binary gate (user-defined): does the **alpha-blended posterior** beat naive (Brier < 0.25)
on the 2026 Bovada-line OOS games? Run on the matchup-dropped totals_v2 OOS parquet to
decide whether removing the 7.M cluster-mismatch fixes the 2026 failure:
  PASS  → cluster-mismatch was the driver; proceed to 10.7 shadow with totals_v2.
  FAIL  → regime-adaptation is the complete story; pause totals, move to Epic 11.

Local only (reads a parquet + best_alpha.json). Compares against the v1 baseline if present.
Usage:
  uv run python betting_ml/scripts/totals_2026_gate_check.py \
      --parquet betting_ml/models/layer3/oos_predictions_totals_v2_nomatchup.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.probability_layer import compute_posterior  # noqa: E402
from betting_ml.scripts.calibrate_totals_v1 import brier_score  # noqa: E402

_LAYER3 = _PROJECT_ROOT / "betting_ml" / "models" / "layer3"
_BEST_ALPHA = _PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
_NAIVE = 0.25


def _eval(parquet: Path, alpha: float) -> dict:
    df = pd.read_parquet(parquet)
    d = df[(df["season"] == 2026) & (df["total_line_source"] == "bovada")
           & df["oos_p_over"].notna() & df["bovada_devig_over_prob"].notna()
           & df["over_hit"].notna()].copy()
    y = d["over_hit"].to_numpy(float)
    raw = d["oos_p_over"].to_numpy(float)
    mkt = d["bovada_devig_over_prob"].to_numpy(float)
    blended = np.array([compute_posterior(float(p), float(m), alpha) for p, m in zip(raw, mkt)])
    return {
        "parquet": parquet.name, "n": len(d),
        "brier_raw": brier_score(raw, y),
        "brier_blended": brier_score(blended, y),
        "brier_market": brier_score(mkt, y),
        "brier_naive": brier_score(np.full(len(d), 0.5), y),
        "mean_p_raw": float(raw.mean()), "mean_p_blended": float(blended.mean()),
        "mean_p_market": float(mkt.mean()), "actual_over_rate": float(y.mean()),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="2026 blended-posterior gate check (Story 10.6 follow-up)")
    p.add_argument("--parquet", required=True, help="OOS parquet to test (e.g. totals_v2_nomatchup)")
    p.add_argument("--baseline", default=str(_LAYER3 / "oos_predictions_totals_v1.parquet"),
                   help="v1 baseline parquet to compare against (optional)")
    args = p.parse_args()

    alpha = float(json.loads(_BEST_ALPHA.read_text()).get("totals_alpha", 0.70))
    target = _eval(Path(args.parquet), alpha)
    base = _eval(Path(args.baseline), alpha) if Path(args.baseline).exists() else None

    print(f"\n=== 2026 GATE CHECK (alpha={alpha:.2f}, naive={_NAIVE}) ===")
    hdr = f"{'metric':<22}{'TARGET ('+target['parquet'][:24]+')':>30}"
    if base:
        hdr += f"{'v1 baseline':>16}"
    print(hdr)
    rows = ["n", "brier_raw", "brier_blended", "brier_market", "brier_naive",
            "mean_p_raw", "mean_p_blended", "mean_p_market", "actual_over_rate"]
    for k in rows:
        line = f"{k:<22}{target[k]:>30.4f}" if k != "n" else f"{k:<22}{target[k]:>30d}"
        if base:
            line += (f"{base[k]:>16.4f}" if k != "n" else f"{base[k]:>16d}")
        print(line)

    passed = target["brier_blended"] < _NAIVE
    print(f"\n>>> GATE: blended Brier {target['brier_blended']:.4f} "
          f"{'<' if passed else '>='} naive {_NAIVE} → "
          f"{'PASS — matchup-drop fixes 2026; proceed to 10.7 shadow with totals_v2.' if passed else 'FAIL — regime-adaptation confirmed; pause totals, move to Epic 11.'}")
    if base:
        delta = target["brier_blended"] - base["brier_blended"]
        print(f"    (Δ blended Brier vs v1: {delta:+.4f}; "
              f"mean P(over) {target['mean_p_blended']:.3f} vs market {target['mean_p_market']:.3f} / actual {target['actual_over_rate']:.3f})")


if __name__ == "__main__":
    main()
