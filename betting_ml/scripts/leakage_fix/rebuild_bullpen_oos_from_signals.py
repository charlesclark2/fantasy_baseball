"""
rebuild_bullpen_oos_from_signals.py — Story 17.1 prep

Re-exports oos_signals_bullpen.parquet from mart_sub_model_signals using the
already-written bullpen_v2 signals (written by generate_bullpen_signals.py
--backfill after the 17.0-retune). Avoids a full Optuna re-run.

The parquet is read directly by run_scoring_nuts.py and run_scoring_advi.py
via _load_oos_signals(). Grain: (game_pk, side). Columns match the existing
leakage_fix parquet format.

Usage:
    uv run python betting_ml/scripts/leakage_fix/rebuild_bullpen_oos_from_signals.py
    uv run python betting_ml/scripts/leakage_fix/rebuild_bullpen_oos_from_signals.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from betting_ml.utils.data_loader import get_snowflake_connection

_OUT_PATH = (
    _PROJECT_ROOT
    / "betting_ml"
    / "models"
    / "layer3"
    / "oos_signals"
    / "oos_signals_bullpen.parquet"
)

_QUERY = """
SELECT
    s.game_pk,
    s.side,
    g.game_year                                                             AS season,
    MAX(CASE WHEN s.signal_name = 'bullpen_mu'          THEN s.signal_value END) AS bullpen_mu,
    MAX(CASE WHEN s.signal_name = 'bullpen_dispersion'  THEN s.signal_value END) AS bullpen_dispersion,
    MAX(CASE WHEN s.signal_name = 'uncertainty'         THEN s.signal_value END) AS bullpen_uncertainty
FROM baseball_data.betting.mart_sub_model_signals s
JOIN baseball_data.betting.mart_game_results g
    ON g.game_pk = s.game_pk
WHERE s.sub_model_name    = 'bullpen_v2'
  AND s.sub_model_version = 'v2'
  AND g.game_year >= 2021
GROUP BY s.game_pk, s.side, g.game_year
ORDER BY s.game_pk, s.side
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild oos_signals_bullpen.parquet from mart_sub_model_signals")
    parser.add_argument("--dry-run", action="store_true", help="Print stats but do not write parquet")
    args = parser.parse_args()

    print("=== Rebuild oos_signals_bullpen.parquet from mart_sub_model_signals ===")
    print("Loading bullpen_v2 signals from Snowflake...")

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_QUERY)
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    df["season"] = df["season"].astype(int)

    print(f"\nLoaded {len(df):,} rows ({df['season'].nunique()} seasons: "
          f"{df['season'].min()}–{df['season'].max()})")

    print("\nbullpen_mu by season:")
    for s, g in df.groupby("season"):
        print(f"  {s}: n={len(g):5,}  mu mean={g['bullpen_mu'].mean():.4f}  "
              f"std={g['bullpen_mu'].std():.4f}  "
              f"null={g['bullpen_mu'].isna().mean():.1%}")

    null_rate = df["bullpen_mu"].isna().mean()
    if null_rate > 0.05:
        print(f"\nWARNING: bullpen_mu null rate = {null_rate:.1%} — check signal generation")
    else:
        print(f"\nbullpen_mu null rate: {null_rate:.1%} OK")

    if args.dry_run:
        print("\n[dry-run] Skipping parquet write.")
        return

    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_OUT_PATH, index=False)
    print(f"\nWritten → {_OUT_PATH.relative_to(_PROJECT_ROOT)}")
    print(f"  Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print("\nNext: uv run python betting_ml/models/bayesian/run_scoring_nuts.py")


if __name__ == "__main__":
    main()
