"""Backfill v3 total_runs predictions (market-blind model, Epic 1).

Loads ngboost_market_blind_2026.pkl, scores every regular-season game with
finalized results in mart_game_results, and inserts per-game rows into
baseball_data.betting_ml.daily_model_predictions with model_version='v3'.

Only total_runs columns are populated:
    pred_total_runs, pred_total_runs_scale, p_over_ngboost,
    total_line_consensus, over_prob_consensus, totals_model_prob, totals_edge
home_win and run_diff columns are left NULL — v3 changes only the total_runs
model (market-blind feature set, 307 features, Normal distribution).

Idempotent: skips (game_pk, model_version='v3') pairs that already exist
unless --force is passed (which deletes existing v3 rows first).

Run from project root:
    uv run python betting_ml/scripts/backfill_total_runs_v3.py --dry-run
    uv run python betting_ml/scripts/backfill_total_runs_v3.py
    uv run python betting_ml/scripts/backfill_total_runs_v3.py --force
    uv run python betting_ml/scripts/backfill_total_runs_v3.py --start-year 2026
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.probability_layer import compute_edge
from betting_ml.models.total_runs_trainer import p_over_line


_ARTIFACT_PATH = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "ngboost_market_blind_2026.pkl"
_FEATURE_COLS_PATH = PROJECT_ROOT / "betting_ml" / "models" / "total_runs" / "feature_columns_market_blind.json"
_DIST_NAME = "Normal"
_MODEL_VERSION = "v3"
_FEATURE_VERSION = "v3"

_INSERT_SQL = """
INSERT INTO baseball_data.betting_ml.daily_model_predictions (
    model_version, feature_version, inserted_at, score_date,
    game_pk, game_date, game_datetime,
    home_team, away_team, home_team_abbrev, away_team_abbrev,
    has_odds,
    pred_total_runs, pred_total_runs_scale,
    p_over_ngboost,
    total_line_consensus, over_prob_consensus,
    totals_model_prob, totals_edge
) VALUES (
    %(model_version)s, %(feature_version)s, %(inserted_at)s, %(score_date)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(p_over_ngboost)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_edge)s
)
"""

_DELETE_V3_SQL = """
DELETE FROM baseball_data.betting_ml.daily_model_predictions
WHERE model_version = %(model_version)s
"""

_EXISTING_PKS_SQL = """
SELECT game_pk
FROM baseball_data.betting_ml.daily_model_predictions
WHERE model_version = %(model_version)s
"""


def _f(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, float) and (v != v):
        return None
    return float(v)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill v3 total_runs predictions.")
    parser.add_argument("--force", action="store_true",
                        help="Delete existing v3 rows before inserting (full rewrite).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Score and report counts but do not write to Snowflake.")
    parser.add_argument("--start-year", type=int, default=2021,
                        help="Earliest season to include (default: 2021).")
    args = parser.parse_args()

    print(f"Loading v3 artifact: {_ARTIFACT_PATH}")
    ngb = joblib.load(_ARTIFACT_PATH)
    feature_cols = json.loads(_FEATURE_COLS_PATH.read_text())
    print(f"  Model: {type(ngb).__name__} (Dist={_DIST_NAME})")
    print(f"  Feature columns: {len(feature_cols)}")

    print(f"Loading {args.start_year}+ historical features (joined with mart_game_results)...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= args.start_year].copy()
    print(f"  Loaded {len(df):,} rows; seasons {sorted(df['game_year'].unique())}")

    train_input_cols = [c for c in feature_cols if c in df.columns]
    print(f"  Using {len(train_input_cols)} of {len(feature_cols)} model features present in df")

    pipe = build_imputation_pipeline()
    X = pipe.fit_transform(df[train_input_cols])
    X = X.reindex(columns=feature_cols, fill_value=0.0)
    print(f"  Imputed feature matrix: {X.shape}")

    print("Scoring all rows with v3...")
    pred_dist = ngb.pred_dist(X.values)
    loc = pred_dist.params["loc"]
    scale = pred_dist.params["scale"]
    pred_mean = ngb.predict(X.values)
    print(f"  pred mean: avg={pred_mean.mean():.3f}, std={pred_mean.std():.3f}, "
          f"min={pred_mean.min():.2f}, max={pred_mean.max():.2f}")

    has_odds = df.get("has_odds", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    total_line = df.get("total_line_consensus", pd.Series(np.nan, index=df.index))
    over_mkt = df.get("over_prob_consensus", pd.Series(np.nan, index=df.index))

    p_over = np.full(len(df), np.nan)
    line_arr = total_line.astype(float).values
    mask = ~np.isnan(line_arr)
    if mask.sum() > 0:
        p_over[mask] = p_over_line(_DIST_NAME, {"loc": loc[mask], "scale": scale[mask]},
                                   total_line=line_arr[mask])

    inserted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    rows: list[dict] = []
    for i, idx in enumerate(df.index):
        ho = bool(has_odds.iloc[i])
        line_v = _f(line_arr[i])
        over_v = _f(over_mkt.iloc[i])
        p_over_v = _f(p_over[i])
        totals_edge_v = (compute_edge(p_over_v, over_v)
                         if (ho and p_over_v is not None and over_v is not None)
                         else None)

        game_pk = df.at[idx, "game_pk"] if "game_pk" in df.columns else None
        game_date = df.at[idx, "game_date"] if "game_date" in df.columns else None

        if pd.notna(game_date):
            try:
                game_date = pd.Timestamp(game_date).date()
            except Exception:
                pass

        rows.append({
            "model_version":         _MODEL_VERSION,
            "feature_version":       _FEATURE_VERSION,
            "inserted_at":           inserted_at,
            "score_date":            game_date,
            "game_pk":               int(game_pk) if pd.notna(game_pk) else None,
            "game_date":             game_date,
            "game_datetime":         None,
            "home_team":             df.at[idx, "home_team"] if "home_team" in df.columns else None,
            "away_team":             df.at[idx, "away_team"] if "away_team" in df.columns else None,
            "home_team_abbrev":      df.at[idx, "home_team"] if "home_team" in df.columns else None,
            "away_team_abbrev":      df.at[idx, "away_team"] if "away_team" in df.columns else None,
            "has_odds":              ho,
            "pred_total_runs":       float(pred_mean[i]),
            "pred_total_runs_scale": float(scale[i]),
            "p_over_ngboost":        p_over_v,
            "total_line_consensus":  line_v if ho else None,
            "over_prob_consensus":   over_v if ho else None,
            "totals_model_prob":     p_over_v if ho else None,
            "totals_edge":           totals_edge_v,
        })

    print(f"  Built {len(rows)} candidate rows")
    has_odds_count = sum(1 for r in rows if r["has_odds"])
    print(f"  has_odds rows: {has_odds_count}")

    if args.dry_run:
        print("\n[dry-run] Skipping Snowflake writes.")
        return

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        if args.force:
            cur.execute(_DELETE_V3_SQL, {"model_version": _MODEL_VERSION})
            print(f"  --force: deleted {cur.rowcount or 0} existing v3 row(s)")
            existing: set[int] = set()
        else:
            cur.execute(_EXISTING_PKS_SQL, {"model_version": _MODEL_VERSION})
            existing = {int(r[0]) for r in cur.fetchall() if r[0] is not None}
            print(f"  Existing v3 rows: {len(existing)}; will skip those game_pks")

        to_insert = [r for r in rows if r["game_pk"] is not None and r["game_pk"] not in existing]
        print(f"  Inserting {len(to_insert)} new row(s)...")

        chunk = 1000
        n_inserted = 0
        for start in range(0, len(to_insert), chunk):
            cur.executemany(_INSERT_SQL, to_insert[start:start + chunk])
            n_inserted += len(to_insert[start:start + chunk])
            print(f"    {n_inserted}/{len(to_insert)}")
        conn.commit()
        print(f"  Committed {n_inserted} v3 rows.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
