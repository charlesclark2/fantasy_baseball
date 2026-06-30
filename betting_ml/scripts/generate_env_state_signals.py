"""
generate_env_state_signals.py — Story 27.2: Environment-state signal generation

Emits the 27.1 Kalman within-season scoring-environment state as daily sub-model
signals following the Epic O canonical contract.  Writes four signal_names per
(game_pk, side) into mart_sub_model_signals via the SCD-2 writer:

  env_league_state_mu     — filtered league-level run-scoring environment mean
                            (leakage-safe: pregame state uses games with date < T)
  env_league_state_sigma  — sqrt(posterior variance); calibration uncertainty
  env_team_off_state      — batting team's offensive-environment Kalman state
  env_team_pitch_state    — fielding team's pitching-environment Kalman state

Sub-model registration: sub_model_name="env_state_v1", sub_model_version="v1".

Kalman parameters (Q, R) are loaded from:
    betting_ml/models/state_space/kalman_params.json
(Fitted by Story 27.1 fit_env_state.py — do not re-run MLE here.)

Leakage contract:
  The state used to score game on date T uses only games with game_date < T.
  This is enforced by the _build_pregame_signals() function, which uses
  bisect_left on pre-sorted date arrays to find the last state strictly
  before T.

Usage:
    # Score a single date (daily Dagster op)
    uv run python betting_ml/scripts/generate_env_state_signals.py --date 2026-06-09

    # Backfill all 2021+ regular-season games (hand off to user — >1 min)
    uv run python betting_ml/scripts/generate_env_state_signals.py --backfill

    # Dry-run: compute without writing
    uv run python betting_ml/scripts/generate_env_state_signals.py --date 2026-06-09 --dry-run
    uv run python betting_ml/scripts/generate_env_state_signals.py --backfill --dry-run
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection
from betting_ml.scripts.scd2_writer import scd2_upsert, _SCHEMA_PROD, _SCHEMA_DEV
from betting_ml.models.state_space.fit_env_state import (
    build_daily_league_df,
    build_daily_team_df,
    load_kalman_params,
    run_league_filter,
    run_team_filters,
)

_TRAINING_START = "2021-01-01"
_SUB_MODEL_NAME    = "env_state_v1"
_SUB_MODEL_VERSION = "v1"
_SIGNAL_NAMES = (
    "env_league_state_mu",
    "env_league_state_sigma",
    "env_team_off_state",
    "env_team_pitch_state",
)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def _resolve_tables(env: str) -> tuple[str, str]:
    schema = _SCHEMA_PROD if env == "prod" else _SCHEMA_DEV
    return f"{schema}.mart_sub_model_signals", f"{schema}.tmp_scd2_incoming"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_GAMES_QUERY = """
SELECT
    game_pk,
    TO_DATE(game_date) AS game_date,
    home_team,
    away_team
FROM baseball_data.betting.mart_game_results
WHERE game_type = 'R'
  AND game_date >= '{start_date}'
  AND game_date <= '{end_date}'
ORDER BY game_date, game_pk
"""


def _load_games(conn, start_date: str, end_date: str) -> pd.DataFrame:
    """Load game schedule rows (game_pk, game_date, home_team, away_team)."""
    cur = conn.cursor()
    try:
        cur.execute(_GAMES_QUERY.format(start_date=start_date, end_date=end_date))
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
    finally:
        cur.close()
    df = pd.DataFrame(rows, columns=cols)
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.date
    return df


# ---------------------------------------------------------------------------
# E11.1-W9-tail: read the env_state source (mart_game_results only) from the S3
# lakehouse via DuckDB instead of Snowflake.  env_state is the SIMPLEST W9 generator
# — it reads ONLY mart_game_results (now in S3 post-W8b) — so it is the natural first
# `--s3` repoint.  The SCD-2 WRITE to mart_sub_model_signals stays on Snowflake (the
# W9 export-mirror copies that OUTPUT to S3; re-implementing SCD-2 accumulate in DuckDB
# is the W7a-wipe class the W9 design forbids).  Mirrors the W7a matchup `--s3` pattern,
# but uses the shared scripts.utils.lakehouse_read connection helper (NOT a forked
# `_get_duckdb` triplet — that drift was where W7a's 4 latent bugs lived).
#
# mart_game_results.game_date is DATE in the parquet (verified) → no ::date cast needed;
# Snowflake `TO_DATE(game_date)` has no DuckDB equivalent so it is dropped (the column is
# already a DATE).  These queries mirror fit_env_state.build_daily_league_df /
# build_daily_team_df + _GAMES_QUERY, in DuckDB dialect.
_DUCK_LEAGUE_HIST_SQL = """
SELECT
    game_date,
    COUNT(*)                                    AS n_games,
    AVG(home_final_score + away_final_score)    AS mean_total,
    STDDEV(home_final_score + away_final_score) AS std_total
FROM mart_game_results
WHERE game_type = 'R'
  AND game_year >= 2021
GROUP BY game_date
ORDER BY game_date
"""

_DUCK_TEAM_HIST_SQL = """
SELECT game_date, home_team AS team, home_final_score AS runs_scored, away_final_score AS runs_allowed
FROM mart_game_results
WHERE game_type = 'R' AND game_year >= 2021
UNION ALL
SELECT game_date, away_team AS team, away_final_score AS runs_scored, home_final_score AS runs_allowed
FROM mart_game_results
WHERE game_type = 'R' AND game_year >= 2021
ORDER BY game_date, team
"""


def _load_s3_inputs(start_date: str, end_date: str):
    """Return (league_hist, team_hist, games_df) read from the S3 lakehouse via DuckDB.

    Shape-/dtype-identical to the Snowflake path (build_daily_league_df /
    build_daily_team_df / _load_games) so the Kalman filter + signal generation run
    unchanged.  Holds only a DuckDB connection (S3 reads); the SCD-2 write stays SF.
    """
    from scripts.utils.lakehouse_read import duck_connect, register_views, strip_fqn

    duck = duck_connect()
    try:
        register_views(duck, ["mart_game_results"])

        def _df(sql: str) -> pd.DataFrame:
            cur = duck.execute(sql)
            cols = [d[0].lower() for d in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)

        league_hist = _df(_DUCK_LEAGUE_HIST_SQL)
        league_hist["game_date"] = pd.to_datetime(league_hist["game_date"]).dt.date
        league_hist = league_hist.sort_values("game_date").reset_index(drop=True)

        team_hist = _df(_DUCK_TEAM_HIST_SQL)
        team_hist["game_date"] = pd.to_datetime(team_hist["game_date"]).dt.date

        # _GAMES_QUERY already filters on a DATE column; drop the SF-only TO_DATE wrapper.
        games_sql = (
            strip_fqn(_GAMES_QUERY)
            .replace("TO_DATE(game_date)", "game_date")
            .format(start_date=start_date, end_date=end_date)
        )
        games_df = _df(games_sql)
        games_df["game_date"] = pd.to_datetime(games_df["game_date"]).dt.date
    finally:
        duck.close()
    return league_hist, team_hist, games_df


# ---------------------------------------------------------------------------
# Leakage-safe fast state lookup
# ---------------------------------------------------------------------------

def _build_sorted_league_lookup(league_df: pd.DataFrame) -> tuple[list, np.ndarray, np.ndarray]:
    """Pre-sort league filter outputs for O(log n) pregame lookups.

    Returns (sorted_dates, states_mu, states_sigma) where each array is aligned
    by index.  State at sorted_dates[i] = posterior AFTER processing that day's
    games.  Pregame state for date T uses sorted_dates[bisect_left(..., T) - 1].
    """
    sorted_dates = sorted(league_df.index)
    mu    = np.array([float(league_df.loc[d, "env_league_state"]) for d in sorted_dates])
    sigma = np.array([
        float(math.sqrt(max(float(league_df.loc[d, "env_league_var"]), 0.0)))
        for d in sorted_dates
    ])
    return sorted_dates, mu, sigma


def _build_sorted_team_lookup(
    team_df: pd.DataFrame,
) -> dict[str, dict]:
    """Pre-sort per-team filter outputs for O(log n) pregame lookups.

    Returns { team: {"dates": [...], "off": np.ndarray, "pit": np.ndarray} }
    """
    teams = team_df.index.get_level_values("team").unique()
    result = {}
    for team in teams:
        mask = team_df.index.get_level_values("team") == team
        sub = team_df[mask]
        sub_dates = sorted(d for d, _ in sub.index)
        off = np.array([float(sub.loc[(d, team), "env_team_off_state"])   for d in sub_dates])
        pit = np.array([float(sub.loc[(d, team), "env_team_pitch_state"]) for d in sub_dates])
        result[team] = {"dates": sub_dates, "off": off, "pit": pit}
    return result


def _pregame_lookup_league(
    sorted_dates: list,
    mu: np.ndarray,
    sigma: np.ndarray,
    game_date: date,
) -> tuple[float | None, float | None]:
    """Leakage-safe: return league state strictly before game_date."""
    idx = bisect.bisect_left(sorted_dates, game_date) - 1
    if idx < 0:
        return None, None
    return float(mu[idx]), float(sigma[idx])


def _pregame_lookup_team(
    team_lookup: dict,
    team: str,
    game_date: date,
) -> float | None:
    """Leakage-safe: return team offensive state strictly before game_date."""
    if team not in team_lookup:
        return None
    lk = team_lookup[team]
    idx = bisect.bisect_left(lk["dates"], game_date) - 1
    if idx < 0:
        return None
    return float(lk["off"][idx])


def _pregame_lookup_team_pit(
    team_lookup: dict,
    team: str,
    game_date: date,
) -> float | None:
    """Leakage-safe: return team pitching state strictly before game_date."""
    if team not in team_lookup:
        return None
    lk = team_lookup[team]
    idx = bisect.bisect_left(lk["dates"], game_date) - 1
    if idx < 0:
        return None
    return float(lk["pit"][idx])


# ---------------------------------------------------------------------------
# Signal generation
# ---------------------------------------------------------------------------

def _feature_hash(game_pk: int, Q: float, R: float) -> str:
    """Stable hash encoding which Kalman model version was used."""
    key = f"{game_pk}|{Q:.8f}|{R:.8f}"
    return hashlib.md5(key.encode()).hexdigest()


def generate_signals(
    games_df: pd.DataFrame,
    league_df: pd.DataFrame,
    team_df: pd.DataFrame,
    Q: float,
    R: float,
) -> list[dict]:
    """Generate env_state signal rows for all (game_pk, side) in games_df.

    Emits four signal_names per (game_pk, side):
      env_league_state_mu     — filtered league-level run-scoring env mean
      env_league_state_sigma  — posterior std dev of the league state
      env_team_off_state      — batting team offensive-environment state
      env_team_pitch_state    — fielding team pitching-environment state

    Leakage guard is enforced by the pregame lookup functions (bisect on
    pre-sorted date arrays).
    """
    league_dates, league_mu, league_sigma = _build_sorted_league_lookup(league_df)
    team_lookup = _build_sorted_team_lookup(team_df)

    rows = []
    for _, g in games_df.iterrows():
        gd        = g["game_date"] if isinstance(g["game_date"], date) else pd.Timestamp(g["game_date"]).date()
        gp        = int(g["game_pk"])
        home_team = str(g["home_team"])
        away_team = str(g["away_team"])
        feat_hash = _feature_hash(gp, Q, R)

        lmu, lsigma = _pregame_lookup_league(league_dates, league_mu, league_sigma, gd)
        signal_available = lmu is not None

        for side in ("home", "away"):
            batting_team  = home_team if side == "home" else away_team
            fielding_team = away_team if side == "home" else home_team

            off_state = _pregame_lookup_team(team_lookup, batting_team, gd)
            pit_state = _pregame_lookup_team_pit(team_lookup, fielding_team, gd)

            base = {
                "game_pk":           gp,
                "side":              side,
                "sub_model_name":    _SUB_MODEL_NAME,
                "sub_model_version": _SUB_MODEL_VERSION,
                "signal_available":  signal_available,
                "input_feature_hash": feat_hash,
            }

            rows.append({**base,
                "signal_name":  "env_league_state_mu",
                "signal_value": lmu,
                "uncertainty":  lsigma,   # posterior std as calibration uncertainty
            })
            rows.append({**base,
                "signal_name":  "env_league_state_sigma",
                "signal_value": lsigma,
                "uncertainty":  None,
            })
            rows.append({**base,
                "signal_name":    "env_team_off_state",
                "signal_value":   off_state,
                "uncertainty":    None,
                "signal_available": signal_available and off_state is not None,
            })
            rows.append({**base,
                "signal_name":    "env_team_pitch_state",
                "signal_value":   pit_state,
                "uncertainty":    None,
                "signal_available": signal_available and pit_state is not None,
            })

    return rows


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate env_state_v1 signals (Story 27.2)"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--backfill",
        action="store_true",
        help=f"Generate signals for all regular-season games from {_TRAINING_START} through today.",
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
        help="Compute signals but skip the Snowflake write.",
    )
    parser.add_argument(
        "--s3",
        action="store_true",
        help="E11.1-W9-tail: read mart_game_results from the S3 lakehouse via DuckDB "
             "instead of Snowflake. The SCD-2 write stays on Snowflake.",
    )
    args = parser.parse_args()

    target_table, temp_table = _resolve_tables(args.env)
    today = date.today().isoformat()

    if args.backfill:
        game_start, game_end = _TRAINING_START, today
    else:
        game_start = game_end = args.date

    env_label = f"[{args.env.upper()}]"
    print(f"{env_label} target={target_table}")
    print(f"Mode: {'backfill' if args.backfill else 'date=' + args.date}")

    # ---- Load Kalman params (fitted in 27.1) ----
    Q, R = load_kalman_params()
    print(f"\nKalman params: Q={Q:.6f}  R={R:.4f}")

    # ---- Load all historical data for the filter ----
    src = "S3 lakehouse (DuckDB)" if args.s3 else "Snowflake"
    print(f"\nLoading historical game data for Kalman filter from {src}...")
    if args.s3:
        league_hist, team_hist, games_df = _load_s3_inputs(game_start, game_end)
    else:
        conn = get_snowflake_connection()
        try:
            league_hist = build_daily_league_df(conn)
            team_hist   = build_daily_team_df(conn)
            games_df    = _load_games(conn, game_start, game_end)
        finally:
            conn.close()

    print(f"  League history: {len(league_hist):,} dates")
    print(f"  Team history  : {len(team_hist):,} rows")
    print(f"  Target games  : {len(games_df):,} games to score")

    if games_df.empty:
        print("No games found for the given date range. Exiting.")
        return

    # ---- Run Kalman filters ----
    prior_mean = float(league_hist["mean_total"].mean())
    print(f"\nRunning league Kalman filter (prior_mean={prior_mean:.4f})...")
    league_df = run_league_filter(league_hist, Q, R, prior_mean=prior_mean)
    print(f"  League filter: {len(league_df):,} dates")

    print("Running per-team Kalman filters (30 teams × partial pooling)...")
    team_df = run_team_filters(team_hist, league_df, Q, R)
    print(f"  Team filter  : {len(team_df):,} (date, team) states")

    # ---- Generate signals ----
    print("\nGenerating signals...")
    signal_rows = generate_signals(games_df, league_df, team_df, Q, R)
    n_signals_per_game = 4
    print(
        f"  {len(signal_rows):,} signal rows "
        f"({len(games_df):,} games × 2 sides × {n_signals_per_game} signals)"
    )

    if args.dry_run:
        print("\n[DRY RUN] Sample rows (first 8):")
        for r in signal_rows[:8]:
            print(f"  {r}")
        # Coverage summary
        available = sum(1 for r in signal_rows if r["signal_available"] and r["signal_name"] == "env_league_state_mu")
        total_game_sides = sum(1 for r in signal_rows if r["signal_name"] == "env_league_state_mu")
        if total_game_sides > 0:
            pct = 100.0 * available / total_game_sides
            print(f"\n[DRY RUN] Coverage: {available}/{total_game_sides} game-sides have env_league_state_mu ({pct:.1f}%)")
        print("[DRY RUN] Skipping Snowflake write.")
        return

    # ---- Write via SCD-2 ----
    print(f"\nWriting {len(signal_rows):,} rows to {target_table}...")
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

    # Coverage check
    available = sum(
        1 for r in signal_rows
        if r["signal_available"] and r["signal_name"] == "env_league_state_mu"
    )
    total_sides = sum(1 for r in signal_rows if r["signal_name"] == "env_league_state_mu")
    if total_sides > 0:
        pct = 100.0 * available / total_sides
        print(f"  Coverage: {available}/{total_sides} game-sides ({pct:.1f}%) have non-null env_league_state_mu")
        if pct < 99.0 and total_sides > 100:
            print(f"  WARNING: coverage {pct:.1f}% is below the 99% acceptance criterion (AC1)")

    print("\nStory 27.2 complete.")
    print("Next step: dbtf build --select feature_pregame_sub_model_signals --target baseball_betting_and_fantasy")


if __name__ == "__main__":
    main()
