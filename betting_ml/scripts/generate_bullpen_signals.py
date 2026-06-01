"""
generate_bullpen_signals.py — Epic 6 (v1) + Epic 6D.3 (v2)

Loads both bullpen artifact generations and writes signals per (game_pk, side)
into mart_sub_model_signals via the SCD-2 writer.

v1 signals (bullpen_quality_v1 — NGBoost Normal; 7 signals per game-side):
  bullpen_availability_index       — rules-based [0,1]; higher = more rested
  bullpen_fatigue_signal           — 1 - availability_index; higher = more fatigued
  bullpen_quality_mu               — NGBoost predicted bullpen xwOBA; uncertainty = 80% PI width
  bullpen_quality_sigma            — per-row NGBoost σ (predictive uncertainty)
  bullpen_quality_signal           — z-scored mu; negative = strong bullpen; uncertainty = PI width
  high_leverage_availability_proxy — closer / hi-lev arm availability [0,1]
  late_game_volatility_signal      — 80% PI width (2 × 1.2816 × σ); higher = more volatile outcome

v2 signals (bullpen_v2 — LightGBM + NegBin; 4 signals per game-side):
  bullpen_mu                  — NegBin μ; expected bullpen runs allowed
  bullpen_dispersion          — NegBin r = 1.4474 (constant per model); lower r = higher overdispersion
  bullpen_fatigue_adjusted_mu — mu × (eb_bullpen_xwoba / season_avg_xwoba); quality-corrected expected runs
  uncertainty                 — 80% NegBin PI width: nbinom.ppf(0.90) − nbinom.ppf(0.10)

Side assignment: pitching_team == home_team → side='home', else side='away'.
Grain: (game_pk, side) — two rows per game, 11 total signals per game-side (7 v1 + 4 v2).

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
from scipy.stats import nbinom, norm

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV
from betting_ml.scripts.compute_bullpen_availability_index import compute_fatigue, compute_index

_TRAINING_START = "2021-01-01"

# v1 artifact
_ARTIFACT_S3_URI_V1   = "s3://baseball-betting-ml-artifacts/sub_models/bullpen_quality_v1.pkl"
_ARTIFACT_LOCAL_V1    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_quality_v1.pkl"
_AVAIL_PARAMS_PATH    = (
    _PROJECT_ROOT / "betting_ml" / "models" / "sub_models"
    / "bullpen_availability_index_v1.json"
)
_SUB_MODEL_NAME_V1    = "bullpen_v1"
_SUB_MODEL_VERSION_V1 = "v1"

# v2 artifact
_ARTIFACT_S3_URI_V2   = "s3://baseball-betting-ml-artifacts/sub_models/bullpen_v2.pkl"
_ARTIFACT_LOCAL_V2    = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "bullpen_v2.pkl"
_SUB_MODEL_NAME_V2    = "bullpen_v2"
_SUB_MODEL_VERSION_V2 = "v2"

# NegBin signal_available gate: require EB posterior coverage ≥ 50%
_EB_COVERAGE_GATE = 0.50

# 80% PI half-width: z such that P(-z ≤ N(0,1) ≤ z) = 0.80
_CALIB_80_Z = float(norm.ppf(0.90))   # 1.2816

# Penalty weights for high-leverage proxy (mirrors compute_bullpen_availability_index.py)
_W_CLOSER  = 0.50
_W_HI_LEV  = 0.25
_MAX_HLEV_PENALTY = _W_CLOSER + _W_HI_LEV    # 0.75

# Feature columns shared by v1 and v2 (same 24 as Epic 6 training)
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
    e.eb_bullpen_coverage_pct,

    -- Starter IP p20 (Epic 5D; Candidate B scaling input — NULL pre-2020 or no probable)
    ip.starter_ip_p20_outs

FROM baseball_data.betting.mart_game_results g
JOIN baseball_data.betting.mart_bullpen_workload w
    ON  w.game_pk       = g.game_pk
    AND w.pitching_team IN (g.home_team, g.away_team)
LEFT JOIN baseball_data.betting.mart_bullpen_effectiveness e
    ON  e.game_pk       = g.game_pk
    AND e.team_abbrev   = w.pitching_team
LEFT JOIN baseball_data.betting_features.starter_ip_signals ip
    ON  ip.game_pk       = g.game_pk
    AND ip.side          = CASE WHEN w.pitching_team = g.home_team THEN 'home' ELSE 'away' END
    AND ip.model_version = 'starter_ip_v1'

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
# v1 signal generation (bullpen_quality_v1 — NGBoost Normal)
# ---------------------------------------------------------------------------

def generate_v1_signals(df: pd.DataFrame, artifact: dict) -> list[dict]:
    """Emit 7 v1 signal rows per (game_pk, side).

    Expects df to already have 'availability_index' as a column (computed
    in main() before calling this function).
    """
    model          = artifact["model"]
    model_type     = artifact["model_type"]
    impute_vals    = artifact["impute_vals"]
    target_mean    = artifact["target_mean"]
    target_std     = artifact["target_std"]
    residual_sigma = artifact["residual_sigma"]
    min_sigma      = artifact["min_sigma"]

    # Cast numeric columns
    for col in FEATURE_COLS + ["bullpen_ip_prev_1d", "bullpen_ip_prev_2d",
                                "bullpen_ip_prev_3d", "closer_used_prev_1d",
                                "high_leverage_used_prev_2d"]:
        if col in df.columns:
            df[col] = df[col].astype(float)

    # Model imputation
    df_imp = df.copy()
    for col in FEATURE_COLS:
        df_imp[col] = df_imp[col].fillna(impute_vals.get(col, 0.0))

    X = df_imp[FEATURE_COLS].to_numpy(dtype=float)

    # Model inference
    if model_type == "ngboost":
        mu_arr    = model.predict(X)
        sigma_arr = np.clip(model.pred_dist(X).params["scale"], min_sigma, None)
    else:  # lgbm
        mu_arr    = model.predict(X)
        sigma_arr = np.full(len(mu_arr), max(residual_sigma, min_sigma))

    z_score_arr  = (mu_arr - target_mean) / target_std
    pi_width_arr = 2.0 * _CALIB_80_Z * sigma_arr

    # High-leverage availability proxy
    closer_used = df["closer_used_prev_1d"].fillna(0.0)
    hilev_used  = df["high_leverage_used_prev_2d"].fillna(0.0)
    hlev_proxy  = (1.0 - (closer_used * _W_CLOSER + hilev_used * _W_HI_LEV)
                   / _MAX_HLEV_PENALTY).clip(0.0, 1.0)

    rows: list[dict] = []
    _hash_cols = [c for c in FEATURE_COLS if c != "availability_index"]
    for i, (_, game_row) in enumerate(df.iterrows()):
        game_pk  = int(game_row["game_pk"])
        side     = "home" if game_row["pitching_team"] == game_row["home_team"] else "away"
        avail_i  = float(df["availability_index"].iloc[i])
        feat_hash = _feature_hash(game_row, _hash_cols)

        mu_i  = float(mu_arr[i])
        sig_i = float(sigma_arr[i])
        z_i   = float(z_score_arr[i])
        pi_i  = float(pi_width_arr[i])
        hl_i  = float(hlev_proxy.iloc[i])

        base = {
            "game_pk":            game_pk,
            "side":               side,
            "sub_model_name":     _SUB_MODEL_NAME_V1,
            "sub_model_version":  _SUB_MODEL_VERSION_V1,
            "signal_available":   True,
            "input_feature_hash": feat_hash,
        }

        rows.append({**base, "signal_name": "bullpen_availability_index",       "signal_value": avail_i,      "uncertainty": None})
        rows.append({**base, "signal_name": "bullpen_fatigue_signal",           "signal_value": 1.0 - avail_i, "uncertainty": None})
        rows.append({**base, "signal_name": "bullpen_quality_mu",               "signal_value": mu_i,          "uncertainty": pi_i})
        rows.append({**base, "signal_name": "bullpen_quality_sigma",            "signal_value": sig_i,         "uncertainty": None})
        rows.append({**base, "signal_name": "bullpen_quality_signal",           "signal_value": z_i,           "uncertainty": pi_i})
        rows.append({**base, "signal_name": "high_leverage_availability_proxy", "signal_value": hl_i,          "uncertainty": None})
        rows.append({**base, "signal_name": "late_game_volatility_signal",      "signal_value": pi_i,          "uncertainty": None})

    return rows


# ---------------------------------------------------------------------------
# v2 signal generation (bullpen_v2 — LightGBM + NegBin)
# ---------------------------------------------------------------------------

def generate_v2_signals(df: pd.DataFrame, artifact: dict) -> list[dict]:
    """Emit 4 v2 NegBin signal rows per (game_pk, side).

    Expects df to have 'availability_index' and 'starter_ip_p20_outs' columns.

    Candidate A: mu = LightGBM predicted mean directly.
    Candidate B: mu_adj = mu_base × (27 − starter_ip_p20_outs) / league_avg_bullpen_outs
                 (rows where p20 is null fall back to scale=1.0; covers pre-2020 and no-probable games)

      bullpen_mu                  — NegBin μ (expected bullpen runs)
      bullpen_dispersion          — constant NegBin r from artifact
      bullpen_fatigue_adjusted_mu — μ × (eb_bullpen_xwoba / season_avg_xwoba)
      uncertainty                 — 80% NegBin PI width

    signal_available = True when eb_bullpen_coverage_pct >= 0.50.
    """
    model       = artifact["model"]
    r           = float(artifact["r"])
    impute_vals = artifact["impute_vals"]
    candidate   = artifact.get("candidate", "A")

    # Cast numeric columns
    for col in FEATURE_COLS:
        if col in df.columns:
            df[col] = df[col].astype(float)

    # Model imputation
    df_imp = df.copy()
    for col in FEATURE_COLS:
        df_imp[col] = df_imp[col].fillna(impute_vals.get(col, 0.0))

    X = df_imp[FEATURE_COLS].to_numpy(dtype=float)

    # NegBin inference — base mu from LightGBM
    mu_arr = np.clip(model.predict(X), 1e-6, None)

    # Candidate B: apply two-stage starter-IP exposure scaling
    if candidate == "B":
        league_avg_bullpen_outs = float(artifact.get("league_avg_bullpen_outs", 15.268))
        p20_raw = pd.to_numeric(df["starter_ip_p20_outs"], errors="coerce").to_numpy(dtype=float)
        scale = np.where(
            np.isnan(p20_raw),
            1.0,
            (27.0 - p20_raw) / max(league_avg_bullpen_outs, 1e-3),
        )
        mu_arr = np.clip(mu_arr * scale, 1e-6, None)

    p_arr  = r / (r + mu_arr)
    lo_arr = nbinom.ppf(0.10, n=r, p=p_arr).astype(float)
    hi_arr = nbinom.ppf(0.90, n=r, p=p_arr).astype(float)
    pi_width_arr = hi_arr - lo_arr

    # Fatigue-adjusted mu: μ × (eb_bullpen_xwoba / season_avg_xwoba)
    eb_xwoba   = df["eb_bullpen_xwoba"].astype(float)
    season_avg = df.groupby("game_year")["eb_bullpen_xwoba"].transform("mean")
    ratio      = (eb_xwoba / season_avg.replace(0, np.nan)).fillna(1.0).clip(0.1, 3.0)
    adj_mu_arr = np.clip(mu_arr * ratio.values, 1e-6, None)

    # signal_available gate
    cov_pct       = df["eb_bullpen_coverage_pct"].fillna(0.0).astype(float)
    available_arr = (cov_pct >= _EB_COVERAGE_GATE).values

    rows: list[dict] = []
    _hash_cols = [c for c in FEATURE_COLS if c != "availability_index"]
    for i, (_, game_row) in enumerate(df.iterrows()):
        game_pk   = int(game_row["game_pk"])
        side      = "home" if game_row["pitching_team"] == game_row["home_team"] else "away"
        sig_avail = bool(available_arr[i])
        feat_hash = _feature_hash(game_row, _hash_cols)

        mu_i     = float(mu_arr[i])
        adj_mu_i = float(adj_mu_arr[i])
        pi_i     = float(pi_width_arr[i])

        base = {
            "game_pk":            game_pk,
            "side":               side,
            "sub_model_name":     _SUB_MODEL_NAME_V2,
            "sub_model_version":  _SUB_MODEL_VERSION_V2,
            "signal_available":   sig_avail,
            "input_feature_hash": feat_hash,
        }

        rows.append({**base, "signal_name": "bullpen_mu",                  "signal_value": mu_i,     "uncertainty": pi_i})
        rows.append({**base, "signal_name": "bullpen_dispersion",          "signal_value": r,         "uncertainty": None})
        rows.append({**base, "signal_name": "bullpen_fatigue_adjusted_mu", "signal_value": adj_mu_i, "uncertainty": pi_i})
        rows.append({**base, "signal_name": "uncertainty",                 "signal_value": pi_i,     "uncertainty": None})

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate bullpen_v1 (NGBoost xwOBA) + bullpen_v2 (LightGBM NegBin runs) signals"
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
    parser.add_argument(
        "--v1-only",
        action="store_true",
        help="Emit only v1 signals (skip bullpen_v2 artifact load).",
    )
    parser.add_argument(
        "--v2-only",
        action="store_true",
        help="Emit only v2 NegBin signals (skip bullpen_quality_v1 artifact load).",
    )
    args = parser.parse_args()

    if args.v1_only and args.v2_only:
        print("ERROR: --v1-only and --v2-only are mutually exclusive.")
        sys.exit(1)

    target_table, temp_table = _resolve_tables(args.env)
    env_label = f"[{args.env.upper()}]"
    emit_v1 = not args.v2_only
    emit_v2 = not args.v1_only
    print(
        f"=== BULLPEN SIGNAL GENERATION (v1={'yes' if emit_v1 else 'no'}, "
        f"v2={'yes' if emit_v2 else 'no'}) ===\n"
        f"{env_label} target={target_table}"
    )

    today = date.today().isoformat()
    start_date = _TRAINING_START if args.backfill else args.date
    end_date   = today if args.backfill else args.date

    # --- Load v1 artifact and availability params ----------------------------
    v1_artifact = None
    avail_params = None
    if emit_v1:
        artifact_path = _ARTIFACT_S3_URI_V1 if os.environ.get("AWS_ACCESS_KEY_ID") else _ARTIFACT_LOCAL_V1
        print(f"\nLoading v1 artifact from {artifact_path}...")
        if isinstance(artifact_path, Path) and not artifact_path.exists():
            print(f"ERROR: {artifact_path} not found. Run train_bullpen_quality_v1.py first.")
            sys.exit(1)
        v1_artifact = load_artifact(artifact_path)
        print(
            f"  model_type={v1_artifact['model_type']}, "
            f"CV MAE={v1_artifact['cv_mae']:.4f}"
        )

        if not _AVAIL_PARAMS_PATH.exists():
            print(f"ERROR: {_AVAIL_PARAMS_PATH} not found. Run compute_bullpen_availability_index.py first.")
            sys.exit(1)
        avail_params = json.loads(_AVAIL_PARAMS_PATH.read_text())
        print(f"  Availability index p95 = {avail_params['normalization']['p95_value']:.4f}")

    # --- Load v2 artifact ----------------------------------------------------
    v2_artifact = None
    if emit_v2:
        artifact_path_v2 = _ARTIFACT_S3_URI_V2 if os.environ.get("AWS_ACCESS_KEY_ID") else _ARTIFACT_LOCAL_V2
        print(f"\nLoading v2 artifact from {artifact_path_v2}...")
        if isinstance(artifact_path_v2, Path) and not artifact_path_v2.exists():
            print(f"ERROR: {artifact_path_v2} not found. Run train_bullpen_distributional.py first.")
            sys.exit(1)
        v2_artifact = load_artifact(artifact_path_v2)
        print(
            f"  model_type={v2_artifact['model_type']}, "
            f"r={v2_artifact['r']:.4f}, "
            f"tuned CV NLL={v2_artifact.get('tuned_cv_nll', v2_artifact['cv_nll']):.4f}"
        )

    # --- Load games ----------------------------------------------------------
    print(f"\nLoading games {start_date} → {end_date}...")
    df = load_games(start_date, end_date)
    n_team_games = len(df)
    n_games = df["game_pk"].nunique()
    print(f"  Loaded {n_team_games:,} team-game rows ({n_games:,} unique games).")

    if df.empty:
        print("No games found for the given date range. Exiting.")
        return

    # --- Compute availability_index once (shared by v1 and v2) ---------------
    if emit_v1 and avail_params is not None:
        p95 = float(avail_params["normalization"]["p95_value"])
        fatigue  = compute_fatigue(df)
        avail_idx = compute_index(fatigue, p95)
    else:
        # v2-only: still need availability_index for the feature matrix
        # Use a neutral default (p95=1.0 → avail_idx = raw fatigue normalized)
        fatigue  = compute_fatigue(df)
        # Fallback: read p95 from v1 params if available, else use 1.0
        p95 = 1.0
        if _AVAIL_PARAMS_PATH.exists():
            _params = json.loads(_AVAIL_PARAMS_PATH.read_text())
            p95 = float(_params["normalization"]["p95_value"])
        avail_idx = compute_index(fatigue, p95)

    df = df.copy()
    df["availability_index"] = avail_idx.values

    # --- Generate signals ----------------------------------------------------
    all_rows: list[dict] = []

    if emit_v1 and v1_artifact is not None:
        print("\nGenerating v1 signals (NGBoost xwOBA)...")
        v1_rows = generate_v1_signals(df, v1_artifact)
        print(f"  {len(v1_rows):,} rows ({n_team_games:,} game-sides × 7 signals)")
        all_rows.extend(v1_rows)

    if emit_v2 and v2_artifact is not None:
        print("\nGenerating v2 signals (LightGBM NegBin runs)...")
        v2_rows = generate_v2_signals(df, v2_artifact)
        print(f"  {len(v2_rows):,} rows ({n_team_games:,} game-sides × 4 signals)")
        all_rows.extend(v2_rows)

    print(f"\n  Total signal rows: {len(all_rows):,}")

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 22 — one game, both sides, all signals):")
        for r in all_rows[:22]:
            print(f"  {r}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    # --- Write ---------------------------------------------------------------
    print(f"\nWriting to {target_table}...")
    conn = get_snowflake_connection()
    try:
        computed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        result = scd2_upsert(
            conn, all_rows,
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
    print("\nEpic 6D.3 signal generation complete.")
    print("Next steps:")
    print("  1. dbtf build --select feature_pregame_sub_model_signals")
    print("  2. Verify bullpen_mu_v2 / bullpen_dispersion_v2 columns present and non-null")


if __name__ == "__main__":
    main()
