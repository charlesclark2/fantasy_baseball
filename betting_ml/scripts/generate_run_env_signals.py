"""
generate_run_env_signals.py — Run environment signal generation (Epic 3, Story 3.3)

Loads the trained run_env_v3 artifact and writes two signals per game into
mart_sub_model_signals via the SCD-2 writer:

  run_env_signal        — z-scored predicted total runs
                          (pred - training_mean) / training_std
                          Positive = run-friendly environment; negative = suppressed.

  environment_volatility — per-venue run std dev computed over completed games
                           in the training window. Captures how volatile run
                           scoring is at each park (e.g., Coors > pitcher parks).

Both signals are game-level (not side-level) but are written as separate rows
for side='home' and side='away' so the feature mart can join on (game_pk, side).

Usage:
    # Backfill all 2021+ completed regular-season games
    uv run python betting_ml/scripts/generate_run_env_signals.py --backfill

    # Single date (daily scoring)
    uv run python betting_ml/scripts/generate_run_env_signals.py --date 2026-05-19

    # Dry-run: compute without writing
    uv run python betting_ml/scripts/generate_run_env_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.utils.artifact_store import load_artifact
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV
from betting_ml.scripts.train_run_env import _TRAINING_START
from betting_ml.scripts.train_run_env_v3 import (
    FEATURE_COLS_V3,
    _add_era_features,
    _apply_imputation_v3,
)

_ARTIFACT_PATH = _PROJECT_ROOT / "betting_ml" / "models" / "sub_models" / "run_env_v3.pkl"
_SUB_MODEL_NAME = "run_env_v3"
_SUB_MODEL_VERSION = "v3"
_SIDES = ("home", "away")


def _resolve_tables(env: str) -> tuple[str, str]:
    """Return (target_table, temp_table) for the given environment."""
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    return f"{schema}.mart_sub_model_signals", f"{schema}.tmp_scd2_incoming"

# ---------------------------------------------------------------------------
# Feature query (no outcome filter — includes upcoming games)
# ---------------------------------------------------------------------------

_SIGNAL_QUERY_TEMPLATE = """
select
    g.game_pk,
    g.game_date,
    p.venue_id,
    p.venue_name,
    g.home_final_score + g.away_final_score      as total_runs,

    p.eb_park_run_factor,
    p.elevation_ft,
    p.center_ft,
    iff(p.roof_type = 'Dome', 1, 0)              as is_dome,

    coalesce(w.temp_f,             70)           as temp_f,
    coalesce(w.wind_component_mph,  0)           as wind_component_mph,
    coalesce(w.humidity_pct,       50)           as humidity_pct,

    u.ump_runs_per_game_zscore,
    u.ump_run_impact_zscore,

    th.off_woba_30d                              as home_off_woba_30d,
    ta.off_woba_30d                              as away_off_woba_30d,
    sh.starter_proj_fip                          as home_starter_proj_fip,
    sh.xwoba_against_30d                         as home_starter_xwoba_30d,
    sa.starter_proj_fip                          as away_starter_proj_fip,
    sa.xwoba_against_30d                         as away_starter_xwoba_30d

from baseball_data.betting.mart_game_results g
left join baseball_data.betting_features.feature_pregame_park_features p
    on p.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_weather_features w
    on w.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_umpire_features u
    on u.game_pk = g.game_pk
left join baseball_data.betting_features.feature_pregame_team_features th
    on th.game_pk = g.game_pk and th.side = 'home'
left join baseball_data.betting_features.feature_pregame_team_features ta
    on ta.game_pk = g.game_pk and ta.side = 'away'
left join baseball_data.betting_features.feature_pregame_starter_features sh
    on sh.game_pk = g.game_pk and sh.side = 'home'
left join baseball_data.betting_features.feature_pregame_starter_features sa
    on sa.game_pk = g.game_pk and sa.side = 'away'

where g.game_date >= '{start_date}'
  and g.game_date <= '{end_date}'
  and g.game_type = 'R'

order by g.game_date, g.game_pk
"""


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_games(start_date: str, end_date: str) -> pd.DataFrame:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_SIGNAL_QUERY_TEMPLATE.format(start_date=start_date, end_date=end_date))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows, columns=cols)
    for col in df.columns:
        if df[col].dtype == object:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() >= df[col].notna().sum() * 0.9:
                df[col] = converted

    # game_year is required by era feature engineering
    df["game_year"] = pd.to_datetime(df["game_date"]).dt.year
    return df


# ---------------------------------------------------------------------------
# Environment volatility
# ---------------------------------------------------------------------------

def compute_venue_volatility(df: pd.DataFrame) -> dict[int, float]:
    """Compute per-venue run std dev over completed games.

    Venue IDs with fewer than 10 completed games fall back to the league-wide
    std dev (prevents noisy estimates from single-game venues).
    """
    completed = df[df["total_runs"].notna()].copy()
    league_std = float(completed["total_runs"].std()) if len(completed) > 1 else 3.0

    venue_stats = (
        completed.groupby("venue_id")["total_runs"]
        .agg(["std", "count"])
        .reset_index()
    )
    venue_vol: dict[int, float] = {}
    for _, row in venue_stats.iterrows():
        if row["count"] >= 10:
            venue_vol[int(row["venue_id"])] = float(row["std"])
        else:
            venue_vol[int(row["venue_id"])] = league_std

    return venue_vol


# ---------------------------------------------------------------------------
# Feature hashing
# ---------------------------------------------------------------------------

def _feature_hash(row: pd.Series) -> str:
    parts = "|".join(
        "" if pd.isna(row[c]) else f"{row[c]:.6g}" for c in FEATURE_COLS_V3
    )
    return hashlib.md5(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def generate_signals(
    df: pd.DataFrame,
    artifact: dict,
    venue_vol: dict[int, float],
    league_vol: float,
) -> list[dict]:
    """Return a list of signal dicts ready for scd2_upsert."""
    model = artifact["model"]
    impute_vals = artifact["impute_values"]
    prior_season_runs = artifact["prior_season_runs"]
    target_mean = artifact["target_mean"]
    target_std = artifact["target_std"]
    cv_mae = artifact["cv_mae"]

    df_era = _add_era_features(df, prior_season_runs)
    df_imp = _apply_imputation_v3(df_era, impute_vals)

    X = df_imp[FEATURE_COLS_V3].to_numpy(dtype=float)
    y_pred = model.predict(X)
    run_env_z = (y_pred - target_mean) / target_std

    rows = []
    for i, (_, game_row) in enumerate(df.iterrows()):
        game_pk = int(game_row["game_pk"])
        venue_id = int(game_row["venue_id"]) if pd.notna(game_row.get("venue_id")) else -1
        feat_hash = _feature_hash(df_imp.iloc[i])

        vol = venue_vol.get(venue_id, league_vol)
        vol_z = (vol - league_vol) / (league_vol * 0.5) if league_vol > 0 else 0.0

        for side in _SIDES:
            # run_env_signal
            rows.append({
                "game_pk": game_pk,
                "side": side,
                "signal_name": "run_env_signal",
                "sub_model_name": _SUB_MODEL_NAME,
                "sub_model_version": _SUB_MODEL_VERSION,
                "signal_value": float(run_env_z[i]),
                "uncertainty": float(cv_mae),
                "signal_available": True,
                "input_feature_hash": feat_hash,
            })
            # environment_volatility
            rows.append({
                "game_pk": game_pk,
                "side": side,
                "signal_name": "environment_volatility",
                "sub_model_name": _SUB_MODEL_NAME,
                "sub_model_version": _SUB_MODEL_VERSION,
                "signal_value": float(vol),
                "uncertainty": None,
                "signal_available": True,
                "input_feature_hash": feat_hash,
            })

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate run_env_v3 signals (Story 3.3)")
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
        help="Target environment: prod (baseball_data.betting) or dev (baseball_data.dev_betting). Default: prod.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute signals but skip the Snowflake write.",
    )
    args = parser.parse_args()

    target_table, temp_table = _resolve_tables(args.env)

    # Date range
    today = date.today().isoformat()
    if args.backfill:
        start_date, end_date = _TRAINING_START, today
    else:
        start_date = end_date = args.date

    env_label = f"[{args.env.upper()}]"
    print(f"{env_label} target={target_table}")

    print(f"\nLoading artifact from {_ARTIFACT_PATH}...")
    artifact = load_artifact(_ARTIFACT_PATH)
    print(f"  model_type={artifact['model_type']}, CV MAE={artifact['cv_mae']}")

    print(f"\nLoading games {start_date} → {end_date}...")
    df = load_games(start_date, end_date)
    print(f"  Loaded {len(df):,} games.")

    if df.empty:
        print("No games found for the given date range. Exiting.")
        return

    print("\nComputing environment volatility by venue...")
    venue_vol = compute_venue_volatility(df)
    league_vol = float(np.mean(list(venue_vol.values()))) if venue_vol else 3.0
    print(f"  {len(venue_vol)} venues tracked. League-mean vol: {league_vol:.3f} runs.")

    print("\nGenerating signals...")
    signal_rows = generate_signals(df, artifact, venue_vol, league_vol)
    n_games = len(df)
    print(f"  {len(signal_rows):,} signal rows ({n_games:,} games × 2 signals × 2 sides).")

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 4):")
        for r in signal_rows[:4]:
            print(f"  {r}")
        print("[DRY RUN] Skipping Snowflake write.")
        return

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
    print("\nStory 3.3 complete. Next: run dbtf build to refresh feature_pregame_sub_model_signals.")


if __name__ == "__main__":
    main()
