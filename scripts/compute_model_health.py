"""
compute_model_health.py
-----------------------
Compute rolling 14-day calibration metrics (ECE and Brier score) for a
prediction target and write a row to baseball_data.betting_ml.model_health_log.

Exits non-zero if ECE > 0.04 (2× the elasticnet baseline of 0.0202).

Usage:
    uv run python scripts/compute_model_health.py
    uv run python scripts/compute_model_health.py --target home_win
    uv run python scripts/compute_model_health.py --target home_win --date 2026-05-01

Snowflake auth env vars (same pattern as other scripts):
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE              (optional)
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

load_dotenv()

import numpy as np
import snowflake.connector

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

ECE_ALERT_THRESHOLD = 0.04
WINDOW_DAYS = 14

# Write isolation: dev/unset → betting_ml_dev; prod (set by daily_ingestion.yml) → betting_ml.
TARGET_ENV = os.getenv("TARGET_ENV", "dev")
_ML_SCHEMA_NAME = "betting_ml" if TARGET_ENV == "prod" else "betting_ml_dev"
_ML_SCHEMA = f"baseball_data.{_ML_SCHEMA_NAME}"

# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    import sys as _sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema=_ML_SCHEMA_NAME)


# ---------------------------------------------------------------------------
# ECE computation
# ---------------------------------------------------------------------------


def compute_ece(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Expected Calibration Error over 10 equal-width probability bins."""
    n = len(probs)
    bins = np.linspace(0, 1, 11)  # 10 equal-width bins
    bin_idx = np.digitize(probs, bins) - 1
    # clip to [0, 9] — edge case when prob == 1.0 lands in bin 10
    bin_idx = np.clip(bin_idx, 0, 9)
    ece = 0.0
    for b in range(10):
        mask = bin_idx == b
        if mask.sum() == 0:
            continue
        ece += (mask.sum() / n) * abs(probs[mask].mean() - outcomes[mask].mean())
    return float(ece)


def compute_brier(probs: np.ndarray, outcomes: np.ndarray) -> float:
    return float(np.mean((probs - outcomes) ** 2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _market_for_target(target: str) -> str:
    mapping = {
        "home_win": "h2h",
        "total_runs": "totals",
        "run_differential": "run_diff",
    }
    return mapping.get(target, target)


def run(target: str, run_date: date, model_version: str | None = None) -> None:
    window_start = run_date - timedelta(days=WINDOW_DAYS)
    market = _market_for_target(target)

    log.info("Fetching prediction_log rows for target=%s version=%s window=[%s, %s]",
             target, model_version or "all", window_start, run_date)

    if model_version:
        fetch_sql = """
            SELECT model_prob, actual_outcome
            FROM baseball_data.config.prediction_log
            WHERE market = %s
              AND prediction_date >= %s
              AND prediction_date < %s
              AND actual_outcome IS NOT NULL
              AND model_prob IS NOT NULL
              AND model_version = %s
        """
        fetch_params = (market, window_start.isoformat(), run_date.isoformat(), model_version)
    else:
        fetch_sql = """
            SELECT model_prob, actual_outcome
            FROM baseball_data.config.prediction_log
            WHERE market = %s
              AND prediction_date >= %s
              AND prediction_date < %s
              AND actual_outcome IS NOT NULL
              AND model_prob IS NOT NULL
        """
        fetch_params = (market, window_start.isoformat(), run_date.isoformat())

    con = _get_connection()
    try:
        cur = con.cursor()
        cur.execute(fetch_sql, fetch_params)
        rows = cur.fetchall()
    finally:
        con.close()

    sample_n = len(rows)
    log.info("Fetched %d prediction_log rows with outcomes", sample_n)

    if sample_n == 0:
        log.warning("No rows with outcomes in rolling window — skipping write.")
        return

    probs = np.array([r[0] for r in rows], dtype=float)
    outcomes = np.array([r[1] for r in rows], dtype=float)

    ece = compute_ece(probs, outcomes)
    brier = compute_brier(probs, outcomes)
    alert_fired = ece > ECE_ALERT_THRESHOLD

    log.info("ECE=%.4f  Brier=%.4f  n=%d  version=%s  alert_fired=%s",
             ece, brier, sample_n, model_version or "all", alert_fired)

    insert_sql = f"""
        INSERT INTO {_ML_SCHEMA}.model_health_log
            (run_date, target, window_days, ece, brier, sample_n, alert_fired, model_version)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    con2 = _get_connection()
    try:
        cur2 = con2.cursor()
        cur2.execute(insert_sql, (
            run_date.isoformat(), target, WINDOW_DAYS,
            ece, brier, sample_n, alert_fired, model_version,
        ))
        con2.commit()
        log.info("Wrote row to model_health_log (version=%s)", model_version or "NULL")
    finally:
        con2.close()

    if alert_fired:
        log.error(
            "ALERT: ECE %.4f exceeds threshold %.4f for target=%s — model calibration drift detected."
            " Drift logged; pipeline continues (retraining deferred).",
            ece, ECE_ALERT_THRESHOLD, target,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute rolling ECE/Brier for a prediction target.")
    parser.add_argument("--target", default="home_win",
                        choices=["home_win", "total_runs", "run_differential"],
                        help="Prediction target to evaluate (default: home_win)")
    parser.add_argument("--date", default=None,
                        help="Run date in YYYY-MM-DD format (default: today ET)")
    parser.add_argument("--model-version", default=None,
                        help="Filter prediction_log to a specific model version tag "
                             "(e.g. v1, v2). If omitted, all versions in the window are used.")
    args = parser.parse_args()

    if args.date:
        run_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        run_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(target=args.target, run_date=run_date, model_version=args.model_version)


if __name__ == "__main__":
    main()
