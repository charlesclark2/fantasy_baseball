"""Phase 5, Task 6 — Daily scoring entry point.

Given a date (default today), score all confirmed regular-season games, print
a picks table to stdout, and write the canonical probability_outputs parquet.

Run from project root:
    uv run python betting_ml/scripts/predict_today.py
    uv run python betting_ml/scripts/predict_today.py --date 2025-04-15

Champion/challenger backfill mode:
    uv run python betting_ml/scripts/predict_today.py \\
        --start-date 2021-04-01 --end-date 2025-10-01 \\
        --model-tag v0 --feature-version v0 --dry-run

    uv run python betting_ml/scripts/predict_today.py \\
        --start-date 2021-04-01 --end-date 2026-05-04 \\
        --model-tag v1 --feature-version v1
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import load_features, load_todays_features, get_snowflake_connection
from betting_ml.utils.preprocessing import build_imputation_pipeline
from betting_ml.utils.model_io import load_model
from betting_ml.utils.calibrated_classifier import PlattCalibratedXGBClassifier  # noqa: F401
from betting_ml.utils.probability_layer import (
    compute_posterior,
    compute_edge,
    compute_kelly,
)
from betting_ml.models.total_runs_trainer import p_over_line

_REGISTRY_PATH = PROJECT_ROOT / "betting_ml" / "models" / "model_registry.yaml"


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

def _load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f) or {}


def _registry_artifact_path(entry: dict, model_tag: str) -> str:
    if model_tag == "v0":
        return entry.get("rollback_artifact_path") or entry["artifact_path"]
    return entry["artifact_path"]


def _registry_feature_columns_path(entry: dict, model_tag: str) -> Path | None:
    """Return the feature columns JSON path for the requested model tag.

    Returns None if the registry entry has no feature_columns_path (legacy entries).
    """
    if model_tag == "v0":
        key = "rollback_feature_columns_path"
    else:
        key = "feature_columns_path"
    path_str = entry.get(key)
    if not path_str:
        return None
    p = Path(path_str)
    return p if p.is_absolute() else PROJECT_ROOT / p


def _load_model_for_tag(target: str, model_tag: str) -> object:
    registry = _load_registry()
    entry = registry[target]
    artifact_path = _registry_artifact_path(entry, model_tag)
    p = Path(artifact_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"Artifact not found: {p}")
    return joblib.load(p)


def _model_version_label(model_tag: str) -> str:
    """Convert a model tag (v0/v1) to the model_version string inserted into Snowflake."""
    return model_tag


# ---------------------------------------------------------------------------
# Feature matrix builder — registry-aware
# ---------------------------------------------------------------------------

def _build_feature_matrix(
    df_raw: pd.DataFrame,
    df_hist: pd.DataFrame,
    target: str,
    model_tag: str,
    model_obj: object,
) -> np.ndarray:
    """Return the imputed feature matrix X for df_raw.

    Dispatches on target + model metadata to select the correct feature columns.
    For NGBoost models: uses the feature_columns.json from the registry.
    For elasticnet home_win: uses elasticnet_feature_columns.json.
    For rollback XGBoost home_win: uses feature_columns.json (294 features).
    In all cases, validates the output column count against model.n_features_in_ (if set).
    """
    registry = _load_registry()
    entry = registry[target]
    feat_path = _registry_feature_columns_path(entry, model_tag)

    if feat_path is not None and feat_path.exists():
        feature_cols = json.loads(feat_path.read_text())
        missing = set(feature_cols) - set(df_raw.columns)
        if missing:
            warnings.warn(
                f"[{target}/{model_tag}] {len(missing)} model features missing from data "
                f"(will fill NaN): {sorted(missing)[:3]}{'...' if len(missing) > 3 else ''}"
            )
        X_hist_raw = df_hist.reindex(columns=feature_cols, fill_value=np.nan)
        X_today_raw = df_raw.reindex(columns=feature_cols, fill_value=np.nan)

        if target in ("total_runs", "run_differential"):
            # NGBoost uses the imputation pipeline which adds indicator columns
            pipeline = build_imputation_pipeline()
            X_hist_imp = pipeline.fit_transform(X_hist_raw)
            X_hist_imp = X_hist_imp.select_dtypes(include=[np.number])
            X_today_imp = pipeline.transform(X_today_raw)
            X_today_imp = X_today_imp.reindex(columns=X_hist_imp.columns, fill_value=0.0)
        else:
            # Elasticnet and XGBoost: no build_imputation_pipeline (they handle imputation internally)
            X_today_imp = X_today_raw
    else:
        # Legacy fallback: no feature columns path configured
        warnings.warn(
            f"[{target}/{model_tag}] No feature_columns_path in registry; "
            f"falling back to all numeric columns"
        )
        from betting_ml.scripts.model_evaluation.cv_harness import _NON_FEATURE_COLS
        _NON_FEAT = _NON_FEATURE_COLS | {"split"}
        numeric_cols = df_raw.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [c for c in numeric_cols if c not in _NON_FEAT]
        X_today_imp = df_raw.reindex(columns=feature_cols, fill_value=np.nan)

    # Validate feature count against model expectation (if model stores it)
    expected_n = getattr(model_obj, "n_features_in_", None)
    if expected_n is None and hasattr(model_obj, "xgb_classifier"):
        expected_n = getattr(model_obj.xgb_classifier, "n_features_in_", None)
    if expected_n is not None and X_today_imp.shape[1] != expected_n:
        raise ValueError(
            f"[{target}/{model_tag}] Feature count mismatch: model expects {expected_n} "
            f"but got {X_today_imp.shape[1]}. Retrain the model or fix feature_columns_path."
        )

    return X_today_imp.values if isinstance(X_today_imp, pd.DataFrame) else X_today_imp


# ---------------------------------------------------------------------------
# Calibrator (home_win v1 elasticnet is natively calibrated)
# ---------------------------------------------------------------------------

def _apply_calibrator(consensus_win_prob: float) -> float:
    return consensus_win_prob


# ---------------------------------------------------------------------------
# Snowflake DDL + DML
# ---------------------------------------------------------------------------

_CREATE_PREDICTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS baseball_data.betting_ml.daily_model_predictions (
    model_version           VARCHAR(20)    NOT NULL,
    feature_version         VARCHAR(30),
    inserted_at             TIMESTAMP_NTZ  NOT NULL,
    score_date              DATE           NOT NULL,
    game_pk                 INTEGER,
    game_date               DATE,
    game_datetime           TIMESTAMP_NTZ,
    home_team               VARCHAR(100),
    away_team               VARCHAR(100),
    home_team_abbrev        VARCHAR(10),
    away_team_abbrev        VARCHAR(10),
    has_odds                BOOLEAN,
    p_home_win_ngboost      FLOAT,
    p_home_win_classifier   FLOAT,
    consensus_win_prob      FLOAT,
    calibrated_win_prob     FLOAT,
    pick                    VARCHAR(60),
    pred_total_runs         FLOAT,
    pred_total_runs_scale   FLOAT,
    pred_run_diff_loc       FLOAT,
    pred_run_diff_scale     FLOAT,
    p_over_ngboost          FLOAT,
    alpha                   FLOAT,
    h2h_market_implied_prob FLOAT,
    h2h_posterior_prob      FLOAT,
    h2h_edge                FLOAT,
    h2h_kelly_fraction      FLOAT,
    total_line_consensus    FLOAT,
    over_prob_consensus     FLOAT,
    totals_model_prob       FLOAT,
    totals_posterior_prob   FLOAT,
    totals_edge             FLOAT,
    totals_kelly_fraction   FLOAT
)
"""

_CHECK_DUPLICATE = """
SELECT COUNT(*) FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_pk = %(game_pk)s AND model_version = %(model_version)s
"""

_INSERT_PREDICTION = """
INSERT INTO baseball_data.betting_ml.daily_model_predictions (
    model_version, feature_version, inserted_at, score_date,
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
    %(model_version)s, %(feature_version)s, %(inserted_at)s, %(score_date)s,
    %(game_pk)s, %(game_date)s, %(game_datetime)s,
    %(home_team)s, %(away_team)s, %(home_team_abbrev)s, %(away_team_abbrev)s,
    %(has_odds)s,
    %(p_home_win_ngboost)s, %(p_home_win_classifier)s, %(consensus_win_prob)s, %(calibrated_win_prob)s, %(pick)s,
    %(pred_total_runs)s, %(pred_total_runs_scale)s,
    %(pred_run_diff_loc)s, %(pred_run_diff_scale)s,
    %(p_over_ngboost)s,
    %(alpha)s,
    %(h2h_market_implied_prob)s, %(h2h_posterior_prob)s, %(h2h_edge)s, %(h2h_kelly_fraction)s,
    %(total_line_consensus)s, %(over_prob_consensus)s,
    %(totals_model_prob)s, %(totals_posterior_prob)s, %(totals_edge)s, %(totals_kelly_fraction)s
)
"""


def _write_predictions_to_snowflake(
    df_today: pd.DataFrame,
    target_date: str,
    inserted_at: datetime,
    p_home_win_ngb: np.ndarray,
    p_home_win_clf: np.ndarray,
    loc_tot: np.ndarray,
    scale_tot: np.ndarray,
    loc_diff: np.ndarray,
    scale_diff: np.ndarray,
    p_over_total: np.ndarray,
    h2h_mkt: np.ndarray,
    over_mkt: np.ndarray,
    total_line_vals: np.ndarray,
    has_odds_col: pd.Series,
    best_alpha: float,
    picks: list[str],
    model_version: str,
    feature_version: str,
    dry_run: bool = False,
) -> None:
    def _f(arr, i) -> float | None:
        v = arr[i]
        return None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)

    def _s(df, col, i):
        if col not in df.columns:
            return None
        v = df.iloc[i][col]
        if pd.isna(v):
            return None
        return v.item() if hasattr(v, "item") else v

    def _sanitize(row: dict) -> dict:
        return {
            k: (None if isinstance(v, float) and v != v else v)
            for k, v in row.items()
        }

    rows: list[dict] = []
    score_date = date.fromisoformat(target_date)

    for i in range(len(df_today)):
        has_odds = bool(has_odds_col.iloc[i])
        ngb_win  = float(p_home_win_ngb[i])
        clf_win  = float(p_home_win_clf[i])
        cons_win = ngb_win * 0.5 + clf_win * 0.5
        cal_win  = _apply_calibrator(cons_win)

        h2h_mkt_v = _f(h2h_mkt, i)
        if has_odds and h2h_mkt_v is not None:
            h2h_edge  = compute_edge(cal_win, h2h_mkt_v)
            h2h_post  = compute_posterior(cal_win, h2h_mkt_v, best_alpha)
            h2h_kelly = compute_kelly(h2h_edge, h2h_mkt_v)
        else:
            h2h_edge = h2h_post = h2h_kelly = None

        over_mkt_v   = _f(over_mkt, i)
        total_line_v = _f(total_line_vals, i)
        p_over_v     = float(p_over_total[i])
        if has_odds and over_mkt_v is not None:
            tot_edge  = compute_edge(p_over_v, over_mkt_v)
            tot_post  = compute_posterior(p_over_v, over_mkt_v, best_alpha)
            tot_kelly = compute_kelly(tot_edge, over_mkt_v)
        else:
            tot_edge = tot_post = tot_kelly = None

        raw_dt = _s(df_today, "game_datetime", i)
        game_dt: datetime | None = None
        if raw_dt is not None:
            try:
                game_dt = pd.Timestamp(raw_dt).to_pydatetime().replace(tzinfo=None)
            except Exception:
                pass

        game_pk_val = _s(df_today, "game_pk", i)

        rows.append(_sanitize({
            "model_version":          model_version,
            "feature_version":        feature_version,
            "inserted_at":            inserted_at,
            "score_date":             score_date,
            "game_pk":                game_pk_val,
            "game_date":              score_date,
            "game_datetime":          game_dt,
            "home_team":              _s(df_today, "home_name", i) or _s(df_today, "home_team", i),
            "away_team":              _s(df_today, "away_name", i) or _s(df_today, "away_team", i),
            "home_team_abbrev":       _s(df_today, "home_team_abbrev", i) or _s(df_today, "home_abbr", i),
            "away_team_abbrev":       _s(df_today, "away_team_abbrev", i) or _s(df_today, "away_abbr", i),
            "has_odds":               has_odds,
            "p_home_win_ngboost":     ngb_win,
            "p_home_win_classifier":  clf_win,
            "consensus_win_prob":     cons_win,
            "calibrated_win_prob":    cal_win,
            "pick":                   picks[i],
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

    if dry_run:
        print(f"\n[dry-run] Would insert {len(rows)} row(s) for {target_date} "
              f"(model_version={model_version}, feature_version={feature_version})")
        return

    try:
        conn = get_snowflake_connection()
        try:
            cur = conn.cursor()
            cur.execute(_CREATE_PREDICTIONS_TABLE)

            inserted = 0
            skipped = 0
            for row in rows:
                # Idempotent guard: skip if (game_pk, model_version) already exists
                if row.get("game_pk") is not None:
                    cur.execute(_CHECK_DUPLICATE, {"game_pk": row["game_pk"], "model_version": row["model_version"]})
                    if cur.fetchone()[0] > 0:
                        skipped += 1
                        continue
                cur.execute(_INSERT_PREDICTION, row)
                inserted += 1

            conn.commit()
            print(f"\nWrote {inserted} prediction row(s) to "
                  f"baseball_data.betting_ml.daily_model_predictions "
                  f"(model_version={model_version}, feature_version={feature_version}, "
                  f"skipped_duplicates={skipped}, date={target_date})")
        finally:
            conn.close()
    except Exception as exc:
        print(f"\nWarning: Could not write predictions to Snowflake ({exc}).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_ngb_cfg(path: str, target_label: str) -> tuple[int, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"NGBoost tuning results not found: {path}. "
            f"Run Card 4.12 hyperparameter search first."
        )
    with open(p) as f:
        cfg = json.load(f)
    for key in ("best_n_estimators", "best_dist"):
        if key not in cfg:
            raise KeyError(f"Required key '{key}' missing from {path} ({target_label})")
    return int(cfg["best_n_estimators"]), str(cfg["best_dist"])


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
            print("Warning: alpha_tuning_results is empty; trying local cache")
        finally:
            conn.close()
    except Exception as exc:
        print(f"Warning: Could not load alpha from Snowflake ({exc}); trying local cache")

    cache_path = PROJECT_ROOT / "betting_ml" / "models" / "best_alpha.json"
    if cache_path.exists():
        with open(cache_path) as f:
            return float(json.load(f)["best_alpha"])

    print("Warning: best_alpha.json not found; using 0.5")
    return 0.5


_CREATE_PREDICTION_LOG = """
CREATE TABLE IF NOT EXISTS baseball_data.config.prediction_log (
    prediction_date           DATE        NOT NULL,
    game_pk                   INTEGER     NOT NULL,
    market                    VARCHAR(20) NOT NULL,
    model_prob                FLOAT,
    market_prob_at_prediction FLOAT,
    closing_market_prob       FLOAT,
    actual_outcome            INTEGER,
    decimal_odds              FLOAT,
    ev                        FLOAT,
    kelly_fraction            FLOAT,
    loaded_at                 TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
)
"""

_INSERT_PREDICTION_LOG = """
INSERT INTO baseball_data.config.prediction_log (
    prediction_date, game_pk, market, model_prob, market_prob_at_prediction,
    closing_market_prob, actual_outcome, decimal_odds, ev, kelly_fraction
) VALUES (
    %(prediction_date)s, %(game_pk)s, %(market)s, %(model_prob)s,
    %(market_prob_at_prediction)s, %(closing_market_prob)s, %(actual_outcome)s,
    %(decimal_odds)s, %(ev)s, %(kelly_fraction)s
)
"""


def _write_prediction_log(output_rows: list[dict], prediction_date: str, dry_run: bool = False) -> None:
    rows = []
    pred_date = date.fromisoformat(prediction_date)
    for r in output_rows:
        mkt_prob = r.get("market_implied_prob")
        model_prob = r.get("model_prob")
        if mkt_prob and mkt_prob > 0:
            decimal_odds = 1.0 / mkt_prob
            ev = model_prob * (decimal_odds - 1) - (1 - model_prob) if model_prob is not None else None
        else:
            decimal_odds = None
            ev = None
        try:
            game_pk = int(r["game_key"])
        except (ValueError, TypeError):
            game_pk = None
        rows.append({
            "prediction_date":           pred_date,
            "game_pk":                   game_pk,
            "market":                    r.get("market"),
            "model_prob":                r.get("model_prob"),
            "market_prob_at_prediction": mkt_prob,
            "closing_market_prob":       None,
            "actual_outcome":            None,
            "decimal_odds":              decimal_odds,
            "ev":                        ev,
            "kelly_fraction":            r.get("implied_kelly_fraction"),
        })

    if dry_run:
        print(f"[dry-run] Would write {len(rows)} rows to prediction_log for {prediction_date}")
        return

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        cur.execute(_CREATE_PREDICTION_LOG)
        cur.execute(
            f"DELETE FROM baseball_data.config.prediction_log "
            f"WHERE prediction_date = '{prediction_date}'"
        )
        if rows:
            cur.executemany(_INSERT_PREDICTION_LOG, rows)
        conn.commit()
        print(f"\nWrote {len(rows)} rows to prediction_log for {prediction_date}")
    finally:
        conn.close()


_BACKFILL_OUTCOME_H2H_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET actual_outcome = CASE WHEN mgr.home_team_won THEN 1.0 ELSE 0.0 END
FROM baseball_data.betting.mart_game_results mgr
WHERE pl.game_pk = mgr.game_pk
  AND pl.market = 'h2h'
  AND pl.actual_outcome IS NULL
"""

_BACKFILL_OUTCOME_TOTALS_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET actual_outcome = CASE
    WHEN (mgr.home_final_score + mgr.away_final_score) > fpof.total_line_consensus THEN 1.0
    WHEN (mgr.home_final_score + mgr.away_final_score) < fpof.total_line_consensus THEN 0.0
    ELSE NULL
END
FROM baseball_data.betting.mart_game_results mgr
JOIN baseball_data.betting_features.feature_pregame_odds_features fpof
    ON mgr.game_pk = fpof.game_pk
WHERE pl.game_pk = mgr.game_pk
  AND pl.market = 'totals'
  AND pl.actual_outcome IS NULL
  AND fpof.total_line_consensus IS NOT NULL
"""

_BACKFILL_CLOSING_H2H_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    JOIN (
        SELECT bridge2.game_pk, MAX(moe2.ingestion_ts) AS last_ts
        FROM baseball_data.betting.mart_odds_outcomes moe2
        JOIN baseball_data.betting.mart_game_odds_bridge bridge2 ON moe2.event_id = bridge2.event_id
        WHERE moe2.market_key = 'h2h'
          AND moe2.ingestion_ts < moe2.commence_time
        GROUP BY bridge2.game_pk
    ) ls ON bridge.game_pk = ls.game_pk AND moe.ingestion_ts = ls.last_ts
    WHERE moe.market_key = 'h2h'
      AND moe.is_home_outcome = TRUE
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'h2h'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_TOTALS_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    JOIN (
        SELECT bridge2.game_pk, MAX(moe2.ingestion_ts) AS last_ts
        FROM baseball_data.betting.mart_odds_outcomes moe2
        JOIN baseball_data.betting.mart_game_odds_bridge bridge2 ON moe2.event_id = bridge2.event_id
        WHERE moe2.market_key = 'totals'
          AND moe2.ingestion_ts < moe2.commence_time
        GROUP BY bridge2.game_pk
    ) ls ON bridge.game_pk = ls.game_pk AND moe.ingestion_ts = ls.last_ts
    WHERE moe.market_key = 'totals'
      AND moe.outcome_name = 'Over'
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'totals'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_H2H_FALLBACK_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    WHERE moe.market_key = 'h2h'
      AND moe.is_home_outcome = TRUE
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'h2h'
  AND pl.closing_market_prob IS NULL
"""

_BACKFILL_CLOSING_TOTALS_FALLBACK_SQL = """
UPDATE baseball_data.config.prediction_log pl
SET closing_market_prob = c.closing_prob
FROM (
    SELECT bridge.game_pk, AVG(1.0 / moe.outcome_price_decimal) AS closing_prob
    FROM baseball_data.betting.mart_odds_outcomes moe
    JOIN baseball_data.betting.mart_game_odds_bridge bridge ON moe.event_id = bridge.event_id
    WHERE moe.market_key = 'totals'
      AND moe.outcome_name = 'Over'
      AND moe.outcome_price_decimal > 0
    GROUP BY bridge.game_pk
) c
WHERE pl.game_pk = c.game_pk
  AND pl.market = 'totals'
  AND pl.closing_market_prob IS NULL
"""


def _backfill_outcomes() -> None:
    steps = [
        ("actual_outcome h2h",              _BACKFILL_OUTCOME_H2H_SQL),
        ("actual_outcome totals",           _BACKFILL_OUTCOME_TOTALS_SQL),
        ("closing_market_prob h2h",         _BACKFILL_CLOSING_H2H_SQL),
        ("closing_market_prob totals",      _BACKFILL_CLOSING_TOTALS_SQL),
        ("closing_market_prob h2h fallback",    _BACKFILL_CLOSING_H2H_FALLBACK_SQL),
        ("closing_market_prob totals fallback", _BACKFILL_CLOSING_TOTALS_FALLBACK_SQL),
    ]
    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()
        for label, sql in steps:
            cur.execute(sql)
            print(f"  Backfill [{label}]: {cur.rowcount or 0} row(s) updated")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score MLB games using production models. Supports single-date and backfill modes."
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Target game date (default: today). Mutually exclusive with --start-date/--end-date.",
    )
    parser.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Start date for backfill range (inclusive). Requires --end-date.",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="End date for backfill range (inclusive). Requires --start-date.",
    )
    parser.add_argument(
        "--model-tag",
        choices=["v0", "v1"],
        default="v1",
        help="Which model version to score with: v1=current champion, v0=rollback/challenger. "
             "Default: v1",
    )
    parser.add_argument(
        "--feature-version",
        default=None,
        help="Label stored in feature_version column (default: same as --model-tag).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Score and print output but do not write to Snowflake.",
    )
    parser.add_argument(
        "--no-log-snowflake",
        action="store_true",
        default=False,
        help="Skip writing to prediction_log.",
    )
    args = parser.parse_args()

    if args.date and (args.start_date or args.end_date):
        parser.error("--date is mutually exclusive with --start-date/--end-date")
    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date and --end-date must be used together")
    if args.feature_version is None:
        args.feature_version = args.model_tag

    return args


def _date_range(start: str, end: str) -> list[str]:
    d = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    result = []
    while d <= stop:
        result.append(d.isoformat())
        d += timedelta(days=1)
    return result


# ---------------------------------------------------------------------------
# Single-date scoring core
# ---------------------------------------------------------------------------

def _score_date(
    target_date: str,
    df_hist: pd.DataFrame,
    ngb_total: object,
    ngb_diff: object,
    clf_hw: object,
    ngb_tot_dist: str,
    ngb_diff_dist: str,
    best_alpha: float,
    model_tag: str,
    model_version: str,
    feature_version: str,
    dry_run: bool,
    log_snowflake: bool,
) -> None:
    print(f"\n--- Scoring {target_date} (model_tag={model_tag}) ---")
    df_today = load_todays_features(target_date)

    if df_today.empty:
        print(f"  No games found for {target_date}.")
        return

    print(f"  Found {len(df_today)} game(s)")

    lineup_cols = ("home_lineup_slot_1", "away_lineup_slot_1")
    if all(c in df_today.columns for c in lineup_cols):
        before = len(df_today)
        df_today = df_today[
            df_today["home_lineup_slot_1"].notna() & df_today["away_lineup_slot_1"].notna()
        ]
        if len(df_today) < before:
            print(f"  Lineup filter: {before} → {len(df_today)} game(s)")
        if df_today.empty:
            print("  No games with confirmed lineups.")
            return

    for col in ("has_odds", "home_win_prob_consensus"):
        if col not in df_today.columns:
            raise ValueError(f"Required column '{col}' missing from today's features.")

    # ------ NGBoost feature matrices ------
    X_ngb = _build_feature_matrix(df_today, df_hist, "total_runs", model_tag, ngb_total)
    X_diff = _build_feature_matrix(df_today, df_hist, "run_differential", model_tag, ngb_diff)
    X_clf  = _build_feature_matrix(df_today, df_hist, "home_win", model_tag, clf_hw)

    # ------ Score NGBoost total runs ------
    pred_dist_tot = ngb_total.pred_dist(X_ngb)
    if "s" in pred_dist_tot.params:
        scale_tot = pred_dist_tot.params["s"]
        loc_tot   = np.log(pred_dist_tot.params["scale"])
    else:
        loc_tot   = pred_dist_tot.params["loc"]
        scale_tot = pred_dist_tot.params["scale"]

    total_line_vals = (
        df_today["total_line_consensus"].values
        if "total_line_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    p_over_total = p_over_line(
        ngb_tot_dist, {"loc": loc_tot, "scale": scale_tot}, total_line=total_line_vals
    )

    # ------ Score NGBoost run diff ------
    pred_dist_diff = ngb_diff.pred_dist(X_diff)
    loc_diff   = pred_dist_diff.params["loc"]
    scale_diff = pred_dist_diff.params["scale"]
    p_home_win_ngb = p_over_line(
        ngb_diff_dist, {"loc": loc_diff, "scale": scale_diff}, total_line=0
    )

    # ------ Score classifier ------
    p_home_win_clf = clf_hw.predict_proba(X_clf)[:, 1]

    # ------ Market data ------
    has_odds_col = df_today["has_odds"].fillna(False).astype(bool)
    h2h_mkt = (
        df_today["home_win_prob_consensus"].values
        if "home_win_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )
    over_mkt = (
        df_today["over_prob_consensus"].values
        if "over_prob_consensus" in df_today.columns
        else np.full(len(df_today), np.nan)
    )

    # ------ Build picks ------
    picks_list: list[str] = []
    for i in range(len(df_today)):
        ngb_win = float(p_home_win_ngb[i])
        clf_win = float(p_home_win_clf[i])
        cal_win = _apply_calibrator(ngb_win * 0.5 + clf_win * 0.5)
        if cal_win >= 0.55:
            picks_list.append(f"HOME ({cal_win*100:.0f}%)")
        elif cal_win <= 0.45:
            picks_list.append(f"AWAY ({(1-cal_win)*100:.0f}%)")
        elif cal_win > 0.50:
            picks_list.append(f"TOSS-UP (lean HOME {cal_win*100:.0f}%)")
        elif cal_win < 0.50:
            picks_list.append(f"TOSS-UP (lean AWAY {(1-cal_win)*100:.0f}%)")
        else:
            picks_list.append("EVEN")

    # ------ Build output rows for prediction_log ------
    output_rows: list[dict] = []
    for i, row_idx in enumerate(df_today.index):
        game_key = str(row_idx)
        if "game_pk" in df_today.columns:
            game_key = str(df_today.loc[row_idx, "game_pk"])

        if not has_odds_col.iloc[i]:
            continue

        if pd.notna(h2h_mkt[i]):
            cons_prob = float(p_home_win_ngb[i]) * 0.5 + float(p_home_win_clf[i]) * 0.5
            cal = _apply_calibrator(cons_prob)
            mkt = float(h2h_mkt[i])
            edge = compute_edge(cal, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "h2h",
                "model_prob":           cal,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(cal, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

        if pd.notna(over_mkt[i]):
            mp  = float(p_over_total[i])
            mkt = float(over_mkt[i])
            edge = compute_edge(mp, mkt)
            output_rows.append({
                "game_key":             game_key,
                "market":               "totals",
                "model_prob":           mp,
                "market_implied_prob":  mkt,
                "alpha":                best_alpha,
                "posterior_prob":       compute_posterior(mp, mkt, best_alpha),
                "edge":                 edge,
                "implied_kelly_fraction": compute_kelly(edge, mkt),
            })

    output_rows.sort(key=lambda r: abs(r.get("edge") or 0.0), reverse=True)

    if log_snowflake and not dry_run:
        _write_prediction_log(output_rows, target_date, dry_run=False)
        _backfill_outcomes()

    run_ts = datetime.now(timezone.utc).replace(tzinfo=None)
    _write_predictions_to_snowflake(
        df_today=df_today,
        target_date=target_date,
        inserted_at=run_ts,
        p_home_win_ngb=p_home_win_ngb,
        p_home_win_clf=p_home_win_clf,
        loc_tot=loc_tot,
        scale_tot=scale_tot,
        loc_diff=loc_diff,
        scale_diff=scale_diff,
        p_over_total=p_over_total,
        h2h_mkt=h2h_mkt,
        over_mkt=over_mkt,
        total_line_vals=total_line_vals,
        has_odds_col=has_odds_col,
        best_alpha=best_alpha,
        picks=picks_list,
        model_version=model_version,
        feature_version=feature_version,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = _parse_args()
    model_tag     = args.model_tag
    feature_version = args.feature_version
    model_version = _model_version_label(model_tag)
    dry_run       = args.dry_run
    log_snowflake = not args.no_log_snowflake

    # Determine date range
    if args.start_date:
        dates = _date_range(args.start_date, args.end_date)
        print(f"Backfill mode: {len(dates)} dates from {args.start_date} to {args.end_date} "
              f"(model_tag={model_tag}, feature_version={feature_version})")
    else:
        target = args.date or date.today().isoformat()
        dates = [target]
        print(f"Scoring {target} (model_tag={model_tag})")

    # ------ Load historical data for imputation ------
    print("Loading historical features for imputation pipeline fitting...")
    df_hist = load_features(min_games_played=15)
    print(f"  Loaded {len(df_hist):,} historical rows")

    # ------ Load models ------
    print(f"Loading models (tag={model_tag})...")
    ngb_total = _load_model_for_tag("total_runs", model_tag)
    ngb_diff  = _load_model_for_tag("run_differential", model_tag)
    clf_hw    = _load_model_for_tag("home_win", model_tag)
    print(f"  total_runs: {type(ngb_total).__name__}")
    print(f"  run_differential: {type(ngb_diff).__name__}")
    print(f"  home_win: {type(clf_hw).__name__}")

    # ------ Load NGBoost distribution config ------
    _, ngb_tot_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_total_runs.json", "total_runs"
    )
    _, ngb_diff_dist = _load_ngb_cfg(
        "betting_ml/evaluation/tuning_results_ngboost_run_diff.json", "run_differential"
    )

    best_alpha = _load_best_alpha()
    print(f"  best_alpha={best_alpha}")

    # ------ Score each date ------
    for target_date in dates:
        try:
            _score_date(
                target_date=target_date,
                df_hist=df_hist,
                ngb_total=ngb_total,
                ngb_diff=ngb_diff,
                clf_hw=clf_hw,
                ngb_tot_dist=ngb_tot_dist,
                ngb_diff_dist=ngb_diff_dist,
                best_alpha=best_alpha,
                model_tag=model_tag,
                model_version=model_version,
                feature_version=feature_version,
                dry_run=dry_run,
                log_snowflake=log_snowflake,
            )
        except Exception as exc:
            print(f"  Error scoring {target_date}: {exc}")
            if len(dates) == 1:
                raise


if __name__ == "__main__":
    main()
