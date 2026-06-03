"""
build_h2h_dataset.py — Epic 11, Story 11.1 runner

Build the Layer 3 H2H training dataset (target=`home_win`), validate it (no market
features, no target leakage), check the home-win base rate, attach the eval-only
de-vigged Bovada P(home win), and write the dataset audit.

    uv run python betting_ml/scripts/build_h2h_dataset.py --env prod
    uv run python betting_ml/scripts/build_h2h_dataset.py --env prod --no-write   # print only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.scripts.load_layer3_features import (
    build_h2h_dataset,
    write_h2h_dataset_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Story 11.1: build the Layer 3 H2H dataset")
    parser.add_argument("--env", default="prod", choices=["prod", "dev"])
    parser.add_argument("--start-date", default="2021-01-01")
    parser.add_argument("--min-games-played", type=int, default=15)
    parser.add_argument("--no-write", action="store_true", help="Skip writing the audit md")
    args = parser.parse_args()

    X, y, eval_probs, report = build_h2h_dataset(
        start_date=args.start_date, min_games_played=args.min_games_played, env=args.env,
    )

    br = report["base_rate"]
    mc = report["market_coverage"]
    v  = report["validation"]
    print("\n=== Story 11.1 — H2H dataset ===")
    print(f"  X={X.shape}  y={len(y)}  (completeness-filtered games={report['n_games']})")
    print(f"  leakage: target_cols={v.get('target_columns', 0)}  "
          f"raw_feature_violations={v['raw_feature_violations']}  "
          f"bovada_devig_home_prob in X? {'bovada_devig_home_prob' in X.columns}")
    print(f"  home_win base_rate={br['base_rate']}  "
          f"expected {br['expected_range']}  in_range={br['in_expected_range']}")
    print(f"  market coverage: {mc['n_with_prob']}/{mc['n_games']} ({mc['pct_with_prob']}%)  "
          f"bovada={mc['n_bovada']}  consensus_fallback={mc['n_consensus_fallback']}")

    if not br["in_expected_range"]:
        print("  ⚠️  home_win base rate is OUTSIDE [0.52, 0.56] — investigate data quality.")

    if not args.no_write:
        path = write_h2h_dataset_audit(report, start_date=args.start_date)
        print(f"\n  wrote audit → {path}")


if __name__ == "__main__":
    main()
