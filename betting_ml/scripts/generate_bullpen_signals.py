"""
generate_bullpen_signals.py — Epic 6, Story 6.4

Loads the bullpen_quality_v1 artifact (NGBoost Normal champion from Story 6.3)
and writes seven bullpen signals per (game_pk, side) into mart_sub_model_signals
via the SCD-2 writer.

Signals emitted per (game_pk, side):
  bullpen_availability_index       — rules-based [0,1]; higher = more rested
  bullpen_fatigue_signal           — 1 - availability_index; higher = more fatigued
  bullpen_quality_mu               — NGBoost predicted bullpen xwOBA; uncertainty = 80% PI width
  bullpen_quality_sigma            — per-row NGBoost σ (predictive uncertainty)
  bullpen_quality_signal           — z-scored mu; negative = strong bullpen; uncertainty = PI width
  high_leverage_availability_proxy — closer / hi-lev arm availability [0,1]
  late_game_volatility_signal      — 80% PI width (2 × 1.2816 × σ); higher = more volatile outcome

Side assignment: pitching_team == home_team → side='home', else side='away'.
Grain: (game_pk, side) — two rows per game.

Usage:
    # Backfill all 2021+ completed regular-season games
    uv run python betting_ml/scripts/generate_bullpen_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/generate_bullpen_signals.py --date 2026-05-29

    # Dry-run: compute without writing
    uv run python betting_ml/scripts/generate_bullpen_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV
from betting_ml.scripts.compute_bullpen_availability_index import compute_fatigue, compute_index

_TRAINING_START    = "2021-01-01"
_ARTIFACT_S3_URI   = "s3://baseball-betting-ml-artifacts/sub_models/bullpen_quality_v1.pkl"
_ARTIFACT_LOCAL    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_quality_v1.pkl"
_AVAIL_PARAMS_PATH = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models"
    / "bullpen_availability_index_v1.json"
)

_SUB_MODEL_NAME    = "bullpen_v1"
_SUB_MODEL_VERSION = "v1"

# 80% PI half-width: z such that P(-z ≤ N(0,1) ≤ z) = 0.80
_CALIB_80_Z        = float(norm.ppf(0.90))   # 1.2816

# Penalty weights for high-leverage proxy (mirrors compute_bullpen_availability_index.py)
_W_CLOSER  = 0.50
_W_HI_LEV  = 0.25
_MAX_HLEV_PENALTY = _W_CLOSER + _W_HI_LEV    # 0.75

# Feature columns must match training script order exactly
FEATURE_COLS = [
    "eb_bullpen_xwoba", "eb_bullpen_uncertainty", "eb_bullpen_coverage_pct",
    "xwoba_against_14d", "k_pct_14d", "bb_pct_14d", "hard_hit_pct_14d",
    "whiff_rate_14d", "innings_pitched_14d",
    "xwoba_against_30d", "k_pct_30d", "bb_pct_30d", "hard_hit_pct_30d",
    "whiff_rate_30d", "innings_pitched_30d",
    "availability_index",
    "bullpen_ip_prev_1d", "bullpen_ip_prev_2d", "bullpen_ip_prev_3d",
    "pitchers_used_prev_3d", "pitchers_used_prev_7d",
    "reliever_appearances_prev_3d", "high_leverage_used_prev_2d",
    "closer_used_prev_1d",
]


# ---------------------------------------------------------------------------
# Schema resolution
# ---------------------------------------------------------------------------

def _resolve_tables(env: str) -> tuple[str, str]:
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    return f"{schema}.mart_sub_model_signals", f"{schema}.tmp_scd2_incoming"


# ---------------------------------------------------------------------------
# Feature query
# One row per (game_pk, pitching_team). Joining workload + effectiveness per
# team gives home and away bullpen features in two separate rows per game.
# ---------------------------------------------------------------------------

_SIGNAL_QUERY = """
SELECT
    g.game_pk,
    g.game_date,
    g.game_year,
    g.home_team,
    g.away_team,
    w.pitching_team,

    -- Workload (availability / fatigue inputs)
    w.bullpen_ip_prev_1d,
    w.bullpen_ip_prev_2d,
    w.bullpen_ip_prev_3d,
    w.pitchers_used_prev_3d,
    w.pitchers_used_prev_7d,
    w.reliever_appearances_prev_3d,
    w.high_leverage_used_prev_2d,
    w.closer_used_prev_1d,

    -- Rolling quality
    e.xwoba_against_14d,
    e.k_pct_14d,
    e.bb_pct_14d,
    e.hard_hit_pct_14d,
    e.whiff_rate_14d,
    e.innings_pitched_14d,
    e.xwoba_against_30d,
    e.k_pct_30d,
    e.bb_pct_30d,
    e.hard_hit_pct_30d,
    e.whiff_rate_30d,
    e.innings_pitched_30d,

    -- EB posteriors (Epic 6A.3)
    e.eb_bullpen_xwoba,
    e.eb_bullpen_uncertainty,
    e.eb_bullpen_coverage_pct

FROM baseball_data.betting.mart_game_results g
JOIN baseball_data.betting.mart_bullpen_workload w
    ON  w.game_pk       = g.game_pk
    AND w.pitching_team IN (g.home_team, g.away_team)
LEFT JOIN baseball_data.betting.mart_bullpen_effectiveness e
    ON  e.game_pk       = g.game_pk
    AND e.team_abbrev   = w.pitching_team

WHERE g.game_date >= '{start_date}'
  AND g.game_date <= '{end_date}'
  AND g.game_type  = 'R'

ORDER BY g.game_date, g.game_pk, w.pitching_team
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(start_date: str, end_date: str) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNAL_QUERY.format(start_date=start_date, end_date=end_date))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for col in df.select_dtypes(include="object").columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() >= df[col].notna().sum() * 0.9:
            df[col] = converted

    return df


# ---------------------------------------------------------------------------
# Feature hashing (SCD-2 idempotency key)
# ---------------------------------------------------------------------------

def _feature_hash(row: pd.Series, cols: list[str]) -> str:
    parts = "|".join(
        "" if pd.isna(row[c]) else f"{float(row[c]):.6g}" for c in cols
    )
    return hashlib.md5(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def generate_signals(df: pd.DataFrame, artifact: dict, avail_params: dict) -> list[dict]:
    """Return signal rows ready for scd2_upsert.

    Emits 7 signal_names per (game_pk, side):
      bullpen_availability_index       — [0,1]; higher = more rested
      bullpen_fatigue_signal           — 1 - availability_index
      bullpen_quality_mu               — NGBoost predicted xwOBA
      bullpen_quality_sigma            — per-row NGBoost σ
      bullpen_quality_signal           — z-score of mu
      high_leverage_availability_proxy — closer/hi-lev arm availability [0,1]
      late_game_volatility_signal      — 80% PI width
    """
    model          = artifact["model"]
    model_type     = artifact["model_type"]
    impute_vals    = artifact["impute_vals"]
    target_mean    = artifact["target_mean"]
    target_std     = artifact["target_std"]
    residual_sigma = artifact["residual_sigma"]
    min_sigma      = artifact["min_sigma"]

    p95 = float(avail_params["normalization"]["p95_value"])

    # Cast numeric columns (Snowflake NUMERIC arrives as Decimal)
    for col in FEATURE_COLS + ["bullpen_ip_prev_1d", "bullpen_ip_prev_2d",
                                "bullpen_ip_prev_3d", "closer_used_prev_1d",
                                "high_leverage_used_prev_2d"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    # --- Availability index --------------------------------------------------
    fatigue    = compute_fatigue(df)
    avail_idx  = compute_index(fatigue, p95)

    # Temporarily attach availability_index so the feature matrix is complete
    df = df.copy()
    df["availability_index"] = avail_idx

    # --- Model imputation ---------------------------------------------------
    df_imp = df.copy()
    for col in FEATURE_COLS:
        df_imp[col] = df_imp[col].fillna(impute_vals.get(col, 0.0))

    X = df_imp[FEATURE_COLS].to_numpy(dtype=float)

    # --- Model inference ----------------------------------------------------
    if model_type == "ngboost":
        mu_arr    = model.predict(X)
        sigma_arr = np.clip(model.pred_dist(X).params["scale"], min_sigma, None)
    else:  # lgbm
        mu_arr    = model.predict(X)
        sigma_arr = np.full(len(mu_arr), max(residual_sigma, min_sigma))

    z_score_arr = (mu_arr - target_mean) / target_std
    pi_width_arr = 2.0 * _CALIB_80_Z * sigma_arr

    # --- High-leverage availability proxy -----------------------------------
    closer_used = df["closer_used_prev_1d"].fillna(0.0)
    hilev_used  = df["high_leverage_used_prev_2d"].fillna(0.0)
    hlev_proxy  = (1.0 - (closer_used * _W_CLOSER + hilev_used * _W_HI_LEV)
                   / _MAX_HLEV_PENALTY).clip(0.0, 1.0)

    rows: list[dict] = []
    for i, (row_i, game_row) in enumerate(df.iterrows()):
        game_pk = int(game_row["game_pk"])
        side    = "home" if game_row["pitching_team"] == game_row["home_team"] else "away"

        feat_cols_for_hash = [c for c in FEATURE_COLS if c != "availability_index"]
        feat_hash = _feature_hash(game_row, feat_cols_for_hash)

        mu_i      = float(mu_arr[i])
        sigma_i   = float(sigma_arr[i])
        z_i       = float(z_score_arr[i])
        pi_i      = float(pi_width_arr[i])
        avail_i   = float(avail_idx.iloc[i])
        hlev_i    = float(hlev_proxy.iloc[i])

        base = {
            "game_pk":            game_pk,
            "side":               side,
            "sub_model_name":     _SUB_MODEL_NAME,
            "sub_model_version":  _SUB_MODEL_VERSION,
            "signal_available":   True,
            "input_feature_hash": feat_hash,
        }

        rows.append({**base,
            "signal_name":  "bullpen_availability_index",
            "signal_value": avail_i,
            "uncertainty":  None,
        })
        rows.append({**base,
            "signal_name":  "bullpen_fatigue_signal",
            "signal_value": 1.0 - avail_i,
            "uncertainty":  None,
        })
        rows.append({**base,
            "signal_name":  "bullpen_quality_mu",
            "signal_value": mu_i,
            "uncertainty":  pi_i,
        })
        rows.append({**base,
            "signal_name":  "bullpen_quality_sigma",
            "signal_value": sigma_i,
            "uncertainty":  None,
        })
        rows.append({**base,
            "signal_name":  "bullpen_quality_signal",
            "signal_value": z_i,
            "uncertainty":  pi_i,
        })
        rows.append({**base,
            "signal_name":  "high_leverage_availability_proxy",
            "signal_value": hlev_i,
            "uncertainty":  None,
        })
        rows.append({**base,
            "signal_name":  "late_game_volatility_signal",
            "signal_value": pi_i,
            "uncertainty":  None,
        })

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate bullpen_v1 signals (Story 6.4)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help=f"Generate signals for all games from {_TRAINING_START} through today.",
    )
    mode.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Generate signals for a single game date.",
    )
    parser.add_argument(
        "--env",
        choices=["prod", "dev"],
        default="prod",
        help="Target environment: prod or dev. Default: prod.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute signals but skip Snowflake write.",
    )
    args = parser.parse_args()

    target_table, temp_table = _resolve_tables(args.env)
    env_label = f"[{args.env.upper()}]"
    print(f"=== EPIC 6.4 — BULLPEN SIGNAL GENERATION ===\n{env_label} target={target_table}")

    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    # --- Load artifact -------------------------------------------------------
    artifact_path = _ARTIFACT_S3_URI if os.environ.get("AWS_ACCESS_KEY_ID") else _ARTIFACT_LOCAL
    print(f"\nLoading artifact from {artifact_path}...")
    if isinstance(artifact_path, Path) and not artifact_path.exists():
        print(f"ERROR: {artifact_path} not found. Run train_bullpen_quality_v1.py first.")
        sys.exit(1)
    artifact = load_artifact(artifact_path)
    print(
        f"  model_type={artifact['model_type']}, "
        f"tuned CV NLL={artifact.get('tuned_cv_nll', artifact['cv_nll']):.4f}, "
        f"CV MAE={artifact['cv_mae']:.4f}"
    )

    # --- Load availability params --------------------------------------------
    if not _AVAIL_PARAMS_PATH.exists():
        print(f"ERROR: {_AVAIL_PARAMS_PATH} not found. Run compute_bullpen_availability_index.py first.")
        sys.exit(1)
    avail_params = json.loads(_AVAIL_PARAMS_PATH.read_text())
    print(f"  Availability index p95 = {avail_params['normalization']['p95_value']:.4f}")

    # --- Load games ----------------------------------------------------------
    print(f"\nLoading games {start_date} → {end_date}...")
    df = load_games(start_date, end_date)
    n_team_games = len(df)
    n_games = df["game_pk"].nunique()
    print(f"  Loaded {n_team_games:,} team-game rows ({n_games:,} unique games).")

    if df.empty:
        print("No games found for the given date range. Exiting.")
        return

    # --- Generate signals ----------------------------------------------------
    print("\nGenerating signals...")
    signal_rows = generate_signals(df, artifact, avail_params)
    n_signals = len(signal_rows)
    signals_per_team_game = 7
    print(
        f"  {n_signals:,} signal rows "
        f"({n_team_games:,} team-games × {signals_per_team_game} signals)."
    )

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 14 — one game, both sides):")
        for r in signal_rows[:14]:
            print(f"  {r}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    # --- Write ---------------------------------------------------------------
    print(f"\nWriting to {target_table}...")
    conn = get_snowflake_connection()
    try:
        computed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = scd2_upsert(
            conn, signal_rows,
            target_table=target_table,
            temp_table=temp_table,
            computed_at=computed_at,
        )
    finally:
        conn.close()

    print(
        f"  Done. inserted={result['inserted']}, "
        f"skipped={result['skipped']}, closed={result['closed']}"
    )
    print("\nStory 6.4 complete.")
    print("Next steps (Story 6.5):")
    print("  1. Run ablation test:")
    print("     uv run python betting_ml/scripts/ablation_bullpen_signals.py")
    print("  2. If gate passes, add bullpen signal columns to feature_pregame_sub_model_signals:")
    print("     dbtf build --select feature_pregame_sub_model_signals")


if __name__ == "__main__":
    main()
