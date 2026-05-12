"""Epic 1 / Story 1.6 — Backfill daily_model_predictions with market-blind v2 rows.

Loads the 2024+ feature store in one batch, runs all three promoted market-blind
models, and writes one row per game to baseball_data.betting_ml.daily_model_predictions.
score_date and game_date are set from the actual game date in the feature store, not
from today — so the backfill covers the true starting and ending dates of each season.

Idempotent: existing (game_pk, model_version, retrain_tag) tuples are skipped.

Usage
-----
    # Dry-run — validate row format for 2026 games only
    uv run python betting_ml/scripts/backfill_predictions.py --dry-run --start-year 2026

    # Full backfill for 2024-2026
    uv run python betting_ml/scripts/backfill_predictions.py --start-year 2024
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from betting_ml.utils.data_loader import load_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.model_io import load_model
from betting_ml.utils.probability_layer import compute_edge, compute_posterior, compute_kelly
from betting_ml.models.total_runs_trainer import p_over_line

_MODELS = PROJECT_ROOT / "betting_ml" / "models"
_REGISTRY_PATH = _MODELS / "model_registry.yaml"
_CALIBRATOR_PATH = _MODELS / "home_win" / "calibrator.joblib"

_ML_SCHEMA = "baseball_data.betting_ml"
_RETRAIN_TAG = "market_blind_epic1"
_PREDICTION_TYPE = "backfill"
_BATCH_SIZE = 500


_ALTER_RETRAIN_TAG = f"""
ALTER TABLE {_ML_SCHEMA}.daily_model_predictions
ADD COLUMN IF NOT EXISTS retrain_tag VARCHAR(50)
"""

_INSERT_ROW = f"""
INSERT INTO {_ML_SCHEMA}.daily_model_predictions (
    model_version, inserted_at, score_date, prediction_type, retrain_tag,
    game_pk, game_date, game_datetime,
    home_team, away_team, home_team_abbrev, away_team_abbrev,
    has_odds,
    p_home_win_ngboost, p_home_win_classifier, consensus_win_prob, calibrated_win_prob, pick,
    pred_total_runs, pred_total_runs_scale,
    pred_run_diff_loc, pred_run_diff_scale,
    p_over_ngboost,
    alpha,
    h2h_market_implied_prob, h2h_posterior_prob, h2h_edge, h2h_kelly_fraction,
    total_line_consensus, over_prob_consensus,
    totals_model_prob, totals_posterior_prob, totals_edge, totals_kelly_fraction
) VALUES (
    %(model_version)s, %(inserted_at)s, %(score_date)s, %(prediction_type)s, %(retrain_tag)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(p_home_win_ngboost)s, %(p_home_win_classifier)s, %(consensus_win_prob)s,
    %(calibrated_win_prob)s, %(pick)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(pred_run_diff_loc)s, %(pred_run_diff_scale)s,
    %(p_over_ngboost)s,
    %(alpha)s,
    %(h2h_market_implied_prob)s, %(h2h_posterior_prob)s, %(h2h_edge)s, %(h2h_kelly_fraction)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_posterior_prob)s, %(totals_edge)s, %(totals_kelly_fraction)s
)
"""


def _load_calibrator():
    if _CALIBRATOR_PATH.exists():
        return joblib.load(_CALIBRATOR_PATH)
    print("[WARN] calibrator.joblib not found — using raw consensus_win_prob")
    return None


def _apply_calibrator(calibrator, consensus_win_prob: float) -> float:
    if calibrator is not None:
        raw = np.array([consensus_win_prob])
        try:
            return float(calibrator.predict_proba(raw.reshape(-1, 1))[0, 1])
        except AttributeError:
            return float(calibrator.predict(raw)[0])
    return consensus_win_prob


def _load_best_alpha() -> float:
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT alpha FROM baseball_data.betting_ml.alpha_tuning_results "
                "ORDER BY loaded_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            if row is not None:
                return float(row[0])
            print("[WARN] alpha_tuning_results is empty; trying local cache")
        finally:
            conn.close()
    except Exception as exc:
        print(f"[WARN] Could not load alpha from Snowflake ({exc}); trying local cache")

    cache = PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
    if cache.exists():
        return float(json.loads(cache.read_text())["best_alpha"])

    print("[WARN] best_alpha.json not found; using 0.5")
    return 0.5


def _get_existing_game_pks(model_version: str) -> set[int]:
    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT DISTINCT game_pk FROM {_ML_SCHEMA}.daily_model_predictions "
                "WHERE model_version = %s AND retrain_tag = %s",
                (model_version, _RETRAIN_TAG),
            )
            return {int(row[0]) for row in cur.fetchall() if row[0] is not None}
        finally:
            conn.close()
    except Exception as exc:
        print(f"[WARN] Could not query existing game_pks ({exc}); will insert all rows")
        return set()


def _sanitize(row: dict) -> dict:
    return {k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()}


def _col(df: pd.DataFrame, col: str, i: int):
    if col not in df.columns:
        return None
    v = df.iloc[i][col]
    if pd.isna(v):
        return None
    return v.item() if hasattr(v, "item") else v


def _to_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if hasattr(val, "date"):
        return val.date()
    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except ValueError:
            return None
    return None


def _build_rows(
    df: pd.DataFrame,
    model_version: str,
    p_hw_ngb: np.ndarray,
    p_hw_clf: np.ndarray,
    loc_tot: np.ndarray,
    scale_tot: np.ndarray,
    loc_diff: np.ndarray,
    scale_diff: np.ndarray,
    p_over_tot: np.ndarray,
    total_line_vals: np.ndarray,
    best_alpha: float,
    calibrator,
    inserted_at: datetime,
) -> list[dict]:
    rows = []
    for i in range(len(df)):
        game_date_val = _to_date(_col(df, "game_date", i))
        if game_date_val is None:
            continue

        ngb_win = float(p_hw_ngb[i])
        clf_win = float(p_hw_clf[i])
        cons_win = ngb_win * 0.5 + clf_win * 0.5
        cal_win = _apply_calibrator(calibrator, cons_win)

        if cal_win >= 0.55:
            pick = f"HOME ({cal_win*100:.0f}%)"
        elif cal_win <= 0.45:
            pick = f"AWAY ({(1-cal_win)*100:.0f}%)"
        elif cal_win > 0.50:
            pick = f"TOSS-UP (lean HOME {cal_win*100:.0f}%)"
        elif cal_win < 0.50:
            pick = f"TOSS-UP (lean AWAY {(1-cal_win)*100:.0f}%)"
        else:
            pick = "EVEN"

        h2h_mkt_v = _col(df, "home_win_prob_consensus", i)
        h2h_mkt_v = float(h2h_mkt_v) if h2h_mkt_v is not None else None
        over_mkt_v = _col(df, "over_prob_consensus", i)
        over_mkt_v = float(over_mkt_v) if over_mkt_v is not None else None
        tl = total_line_vals[i]
        total_line_v = float(tl) if not np.isnan(tl) else None

        has_odds = h2h_mkt_v is not None

        if has_odds:
            h2h_edge = compute_edge(cal_win, h2h_mkt_v)
            h2h_post = compute_posterior(cal_win, h2h_mkt_v, best_alpha)
            h2h_kelly = compute_kelly(h2h_edge, h2h_mkt_v)
        else:
            h2h_edge = h2h_post = h2h_kelly = None

        p_over_v = float(p_over_tot[i])
        if has_odds and over_mkt_v is not None:
            tot_edge = compute_edge(p_over_v, over_mkt_v)
            tot_post = compute_posterior(p_over_v, over_mkt_v, best_alpha)
            tot_kelly = compute_kelly(tot_edge, over_mkt_v)
        else:
            tot_edge = tot_post = tot_kelly = None

        home_team = _col(df, "home_team", i)
        away_team = _col(df, "away_team", i)

        rows.append(_sanitize({
            "model_version":          model_version,
            "inserted_at":            inserted_at,
            "score_date":             game_date_val,
            "prediction_type":        _PREDICTION_TYPE,
            "retrain_tag":            _RETRAIN_TAG,
            "game_pk":                _col(df, "game_pk", i),
            "game_date":              game_date_val,
            "game_datetime":          None,
            "home_team":              home_team,
            "away_team":              away_team,
            "home_team_abbrev":       home_team,
            "away_team_abbrev":       away_team,
            "has_odds":               has_odds,
            "p_home_win_ngboost":     ngb_win,
            "p_home_win_classifier":  clf_win,
            "consensus_win_prob":     cons_win,
            "calibrated_win_prob":    cal_win,
            "pick":                   pick,
            "pred_total_runs":        float(loc_tot[i]),
            "pred_total_runs_scale":  float(scale_tot[i]),
            "pred_run_diff_loc":      float(loc_diff[i]),
            "pred_run_diff_scale":    float(scale_diff[i]),
            "p_over_ngboost":         p_over_v,
            "alpha":                  best_alpha,
            "h2h_market_implied_prob": h2h_mkt_v if has_odds else None,
            "h2h_posterior_prob":     h2h_post,
            "h2h_edge":               h2h_edge,
            "h2h_kelly_fraction":     h2h_kelly,
            "total_line_consensus":   total_line_v if has_odds else None,
            "over_prob_consensus":    over_mkt_v if has_odds else None,
            "totals_model_prob":      p_over_v if has_odds else None,
            "totals_posterior_prob":  tot_post,
            "totals_edge":            tot_edge,
            "totals_kelly_fraction":  tot_kelly,
        }))
    return rows


def _write_rows(rows: list[dict], model_version: str) -> None:
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(_ALTER_RETRAIN_TAG)
        except Exception as exc:
            print(f"[WARN] ALTER TABLE for retrain_tag skipped ({exc})")

        total = 0
        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start: start + _BATCH_SIZE]
            cur.executemany(_INSERT_ROW, batch)
            total += len(batch)
            print(f"  Inserted {total}/{len(rows)} rows...")
        conn.commit()
        print(f"\nWrote {len(rows)} rows to {_ML_SCHEMA}.daily_model_predictions "
              f"(model_version={model_version}, retrain_tag={_RETRAIN_TAG})")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill daily_model_predictions with market-blind v2 rows for 2024+."
    )
    parser.add_argument(
        "--start-year", type=int, default=2024,
        help="First season to include (default: 2024)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Print row count and sample row without writing to Snowflake",
    )
    args = parser.parse_args()

    registry = yaml.safe_load(_REGISTRY_PATH.read_text())
    model_version = registry["home_win"]["model_version"]
    tot_dist = registry["total_runs"]["dist"]
    diff_dist = registry["run_differential"]["dist"]

    print("=== Epic 1 / Story 1.6 — Historical Prediction Backfill ===")
    print(f"  model_version={model_version}  start_year={args.start_year}  "
          f"dry_run={args.dry_run}")

    print("\nLoading feature store from Snowflake...")
    df = load_features(min_games_played=15)
    df = df[df["game_year"] >= args.start_year].reset_index(drop=True)
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    if "game_date" in df.columns and "game_year" in df.columns:
        for yr in sorted(df["game_year"].unique()):
            sub = df[df["game_year"] == yr]["game_date"]
            print(f"  {yr}: {sub.min()} → {sub.max()}  ({len(sub):,} games)")
    else:
        print(f"  {len(df):,} rows loaded")

    if not args.dry_run:
        # Ensure retrain_tag column exists before querying it
        try:
            conn = get_snowflake_connection()
            try:
                conn.cursor().execute(_ALTER_RETRAIN_TAG)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            print(f"[WARN] Could not add retrain_tag column ({exc})")

        print("\nChecking for existing backfill rows in Snowflake...")
        existing_pks = _get_existing_game_pks(model_version)
        if existing_pks and "game_pk" in df.columns:
            before = len(df)
            df = df[~df["game_pk"].isin(existing_pks)].reset_index(drop=True)
            print(f"  Idempotency: skipped {before - len(df)} existing rows, "
                  f"{len(df):,} remaining")
        else:
            print(f"  No existing rows found — inserting all {len(df):,} games")

    if df.empty:
        print("Nothing to backfill.")
        return

    print("\nFitting imputation pipeline on numeric columns...")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    pipe = build_imputation_pipeline()
    pipe.fit(df[numeric_cols])
    df_t = pd.DataFrame(
        pipe.transform(df[numeric_cols]),
        columns=numeric_cols,
        index=df.index,
    )
    print(f"  Transformed shape: {df_t.shape}")

    def feat_cols(target: str) -> list[str]:
        path = PROJECT_ROOT / registry[target]["feature_columns_path"]
        return json.loads(path.read_text())

    hw_cols = feat_cols("home_win")
    tot_cols = feat_cols("total_runs")
    diff_cols = feat_cols("run_differential")
    print(f"  Feature columns: home_win={len(hw_cols)}, "
          f"total_runs={len(tot_cols)}, run_diff={len(diff_cols)}")

    print("\nLoading production models from registry...")
    clf_hw = load_model("home_win", "prod")
    ngb_tot = load_model("total_runs", "prod")
    ngb_diff = load_model("run_differential", "prod")
    print(f"  home_win:        {type(clf_hw).__name__}")
    print(f"  total_runs:      {type(ngb_tot).__name__}  dist={tot_dist}")
    print(f"  run_differential:{type(ngb_diff).__name__}  dist={diff_dist}")

    calibrator = _load_calibrator()
    best_alpha = _load_best_alpha()
    print(f"  best_alpha={best_alpha}")

    print("\nRunning inference...")
    # Elasticnet uses its own internal imputer — pass raw df with NaN fill
    X_hw = df.reindex(columns=hw_cols, fill_value=np.nan).values.astype(np.float32)
    p_hw_clf = clf_hw.predict_proba(X_hw)[:, 1]

    # NGBoost models use the externally imputed df_t
    X_tot = df_t.reindex(columns=tot_cols, fill_value=0.0).values
    pred_dist_tot = ngb_tot.pred_dist(X_tot)
    loc_tot = pred_dist_tot.params["loc"]
    scale_tot = pred_dist_tot.params["scale"]

    X_diff = df_t.reindex(columns=diff_cols, fill_value=0.0).values
    pred_dist_diff = ngb_diff.pred_dist(X_diff)
    loc_diff = pred_dist_diff.params["loc"]
    scale_diff = pred_dist_diff.params["scale"]

    # P(run_diff > 0) is the NGBoost-derived home win probability
    p_hw_ngb = p_over_line(diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0)

    total_line_vals = (
        df["total_line_consensus"].values
        if "total_line_consensus" in df.columns
        else np.full(len(df), np.nan)
    )
    p_over_tot_arr = p_over_line(
        tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals
    )

    inserted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = _build_rows(
        df, model_version,
        p_hw_ngb, p_hw_clf,
        loc_tot, scale_tot,
        loc_diff, scale_diff,
        p_over_tot_arr, total_line_vals,
        best_alpha, calibrator, inserted_at,
    )

    has_odds_count = sum(1 for r in rows if r.get("has_odds"))
    print(f"\n  Built {len(rows):,} rows ({has_odds_count:,} with market odds)")

    if rows:
        s = rows[0]
        print(f"  Sample [0]: game_pk={s['game_pk']}, game_date={s['game_date']}, "
              f"p_hw_clf={s['p_home_win_classifier']:.4f}, "
              f"pred_total={s['pred_total_runs']:.2f}, "
              f"pred_rdiff={s['pred_run_diff_loc']:.2f}")
        s = rows[-1]
        print(f"  Sample [-1]: game_pk={s['game_pk']}, game_date={s['game_date']}, "
              f"p_hw_clf={s['p_home_win_classifier']:.4f}, "
              f"pred_total={s['pred_total_runs']:.2f}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would insert {len(rows):,} rows — Snowflake write skipped.")
        return

    print("\nWriting to Snowflake...")
    _write_rows(rows, model_version)


if __name__ == "__main__":
    main()
