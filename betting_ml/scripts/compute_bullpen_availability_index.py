"""
compute_bullpen_availability_index.py — Epic 6.2

Defines and validates the bullpen availability index (v1).

Formula: weighted sum of leverage-adjusted IP over the prior 3 days,
inverted and normalized to [0, 1]. Higher = more rested / available.

  fatigue_score = 3.0 * ip_day1 + 2.0 * ip_day2 + 1.0 * ip_day3
                + 0.50 * closer_used_prev_1d
                + 0.25 * high_leverage_used_prev_2d

  where:
    ip_day1 = bullpen_ip_prev_1d               (yesterday's IP)
    ip_day2 = bullpen_ip_prev_2d - ip_day1     (day -2 incremental IP)
    ip_day3 = bullpen_ip_prev_3d - ip_day2 - ip_day1  (day -3 incremental IP)

  availability_index = clip(1 - fatigue_score / p95_fatigue, 0, 1)

  Normalization anchor: p95 of fatigue_score across 2016-2025 training data
  (excludes 2026 partial season to avoid season-length bias).

Validation:
  - Pearson r between fatigue_score and actual_bullpen_xwoba
    (expected: positive — more fatigue → worse performance → higher xwOBA)
  - Mean actual_bullpen_xwoba by fatigue tier (low / mid / high)
  - Spearman r vs. arm-count proxies (sanity check)

Reads:  betting_ml/data/bullpen_state_train.parquet
Writes: betting_ml/data/bullpen_state_train.parquet  (adds availability_index column)
        betting_ml/models/sub_models/bullpen_availability_index_v1.json (formula params)

Usage:
    uv run python betting_ml/scripts/compute_bullpen_availability_index.py
    uv run python betting_ml/scripts/compute_bullpen_availability_index.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

_PARQUET_PATH = _PROJECT_ROOT / "betting_ml" / "data" / "bullpen_state_train.parquet"
_PARAMS_PATH  = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models"
    / "bullpen_availability_index_v1.json"
)

# ── Formula weights (v1) ───────────────────────────────────────────────────────
_W_DAY1     = 3.0   # yesterday's IP
_W_DAY2     = 2.0   # day -2 incremental IP
_W_DAY3     = 1.0   # day -3 incremental IP
_W_CLOSER   = 0.50  # IP-equivalent penalty for closer used prev 1d
_W_HI_LEV   = 0.25  # IP-equivalent penalty for high-leverage arm used prev 2d


def compute_fatigue(df: pd.DataFrame) -> pd.Series:
    """Return raw fatigue score (higher = more fatigued)."""
    # Cast to float — Snowflake NUMERIC columns arrive as decimal.Decimal
    ip_1d = df["bullpen_ip_prev_1d"].astype(float).fillna(0)
    ip_2d = df["bullpen_ip_prev_2d"].astype(float).fillna(0)
    ip_3d = df["bullpen_ip_prev_3d"].astype(float).fillna(0)

    ip1 = ip_1d
    ip2 = (ip_2d - ip_1d).clip(lower=0)
    ip3 = (ip_3d - ip_2d).clip(lower=0)

    closer_pen   = df["closer_used_prev_1d"].astype(float).fillna(0) * _W_CLOSER
    hi_lev_pen   = df["high_leverage_used_prev_2d"].astype(float).fillna(0) * _W_HI_LEV

    return (_W_DAY1 * ip1 + _W_DAY2 * ip2 + _W_DAY3 * ip3
            + closer_pen + hi_lev_pen)


def compute_index(fatigue: pd.Series, p95: float) -> pd.Series:
    """Invert and normalize fatigue to [0, 1] availability index."""
    return (1.0 - fatigue / p95).clip(0, 1).round(4)


def validate(df: pd.DataFrame) -> None:
    target   = df["actual_bullpen_xwoba"].astype(float).dropna()
    fatigue  = df.loc[target.index, "fatigue_score"]
    avail    = df.loc[target.index, "availability_index"]

    # Pearson r: fatigue vs. actual xwOBA
    r_fat, p_fat = stats.pearsonr(fatigue, target)
    r_avl, p_avl = stats.pearsonr(avail, target)

    # Spearman r: index vs. arm-count proxies
    r_arms, _ = stats.spearmanr(
        df["availability_index"].dropna(),
        df.loc[df["availability_index"].notna(), "pitchers_used_prev_3d"].fillna(0)
    )

    print(f"\n  Pearson r  (fatigue_score  vs. actual_xwoba):  {r_fat:+.4f}  p={p_fat:.3e}")
    print(f"  Pearson r  (availability_index vs. actual_xwoba): {r_avl:+.4f}  p={p_avl:.3e}")
    print(f"  Spearman r (availability_index vs. pitchers_used_prev_3d): {r_arms:+.4f}")

    # Tier analysis: low / mid / high fatigue
    terciles = df["fatigue_score"].quantile([0.33, 0.67])
    lo, hi   = terciles.iloc[0], terciles.iloc[1]

    tiers = pd.cut(
        df["fatigue_score"],
        bins=[-np.inf, lo, hi, np.inf],
        labels=["low_fatigue", "mid_fatigue", "high_fatigue"]
    )
    tier_stats = (
        df.assign(tier=tiers)
        .groupby("tier", observed=True)["actual_bullpen_xwoba"]
        .agg(n="count", mean="mean", std="std")
    )
    print("\n  xwOBA by fatigue tier (expected: low < mid < high):")
    for tier, row in tier_stats.iterrows():
        print(f"    {tier:<15s}  n={int(row['n']):6,}  "
              f"mean_xwoba={row['mean']:.4f}  std={row['std']:.4f}")

    # Season-level stability check
    yr_r = df.groupby("game_year").apply(
        lambda g: stats.pearsonr(g["fatigue_score"], g["actual_bullpen_xwoba"])[0]
        if g["actual_bullpen_xwoba"].notna().sum() > 50 else np.nan,
        include_groups=False
    )
    print("\n  Pearson r by season:")
    for yr, r in yr_r.items():
        bar = "█" * int(abs(r) * 20) if not np.isnan(r) else ""
        sign = "+" if r >= 0 else "-"
        print(f"    {int(yr)}: {sign}{abs(r):.4f}  {bar}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Epic 6.2 — compute and validate bullpen availability index"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate formula but do not write outputs")
    args = parser.parse_args()

    print("=== EPIC 6.2 — BULLPEN AVAILABILITY INDEX ===\n")

    if not _PARQUET_PATH.exists():
        print(f"ERROR: {_PARQUET_PATH} not found. Run build_bullpen_state_dataset.py first.")
        sys.exit(1)

    df = pd.read_parquet(_PARQUET_PATH)
    print(f"Loaded {len(df):,} rows from {_PARQUET_PATH.name}")

    # ── Compute fatigue and availability ──────────────────────────────────────
    df["fatigue_score"] = compute_fatigue(df)

    # Normalize on 2016-2025 (exclude partial 2026 season)
    anchor = df[df["game_year"] <= 2025]["fatigue_score"]
    p95    = float(anchor.quantile(0.95))

    df["availability_index"] = compute_index(df["fatigue_score"], p95)

    print(f"\n  Formula (v1):")
    print(f"    fatigue = {_W_DAY1}×ip_day1 + {_W_DAY2}×ip_day2 + {_W_DAY3}×ip_day3"
          f" + {_W_CLOSER}×closer_prev1d + {_W_HI_LEV}×hi_lev_prev2d")
    print(f"    availability_index = clip(1 - fatigue / p95, 0, 1)")
    print(f"    p95 normalization anchor (2016-2025): {p95:.4f}")
    print(f"\n  fatigue_score  — mean={df['fatigue_score'].mean():.3f}  "
          f"std={df['fatigue_score'].std():.3f}  "
          f"p95={p95:.3f}  max={df['fatigue_score'].max():.3f}")
    print(f"  availability_index — mean={df['availability_index'].mean():.3f}  "
          f"std={df['availability_index'].std():.3f}  "
          f"min={df['availability_index'].min():.3f}")

    # ── Validation ────────────────────────────────────────────────────────────
    print("\n  --- VALIDATION ---")
    validate(df)

    if args.dry_run:
        print("\n[dry-run] Skipping writes.")
        return

    # ── Write parquet with new columns ────────────────────────────────────────
    df.to_parquet(_PARQUET_PATH, index=False)
    print(f"\nUpdated parquet -> {_PARQUET_PATH}")

    # ── Write formula params for registry / downstream scripts ────────────────
    params = {
        "version":        "v1",
        "formula":        "clip(1 - fatigue_score / p95, 0, 1)",
        "fatigue_weights": {
            "ip_day1":            _W_DAY1,
            "ip_day2":            _W_DAY2,
            "ip_day3":            _W_DAY3,
            "closer_used_prev_1d": _W_CLOSER,
            "high_leverage_used_prev_2d": _W_HI_LEV,
        },
        "normalization": {
            "method":      "p95",
            "anchor_years": "2016-2025",
            "p95_value":   p95,
        },
        "output_range": [0.0, 1.0],
        "interpretation": "higher = more rested / available",
    }
    _PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PARAMS_PATH.write_text(json.dumps(params, indent=2))
    print(f"Formula params -> {_PARAMS_PATH}")


if __name__ == "__main__":
    main()
