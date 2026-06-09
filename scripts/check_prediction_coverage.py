"""
check_prediction_coverage.py
-----------------------------
Verify that daily_model_predictions has a row for every scheduled game with
has_full_lineup = true. Exits non-zero if coverage < 90%.

Usage:
    uv run python scripts/check_prediction_coverage.py
    uv run python scripts/check_prediction_coverage.py --date 2026-05-01
    uv run python scripts/check_prediction_coverage.py --min-coverage 0.85

Snowflake auth env vars (same pattern as other scripts):
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE              (optional)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime

import snowflake.connector
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DEFAULT_MIN_COVERAGE = 0.90
# A1.10 — non-blocking warn threshold on the mean feature_coverage_score. Set
# below the intraday-assembly steady-state (~0.77 — carry-forward team blocks +
# overlaid lineup/starter) so it fires on genuine regression, not every day. The
# durable schedule-spined feature store (A1.11) should reach ~1.0.
DEFAULT_MIN_FEATURE_COVERAGE = 0.70

# ---------------------------------------------------------------------------
# Snowflake connection
# ---------------------------------------------------------------------------


def _load_private_key(path: str, passphrase: str | None) -> bytes:
    with open(path, "rb") as fh:
        pem = fh.read()
    pwd = passphrase.encode() if passphrase else None
    key = load_pem_private_key(pem, password=pwd, backend=default_backend())
    return key.private_bytes(
        encoding=Encoding.DER,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption(),
    )


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_WAREHOUSE"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    kwargs: dict = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "warehouse": os.environ["SNOWFLAKE_WAREHOUSE"],
        "database":  "baseball_data",
    }

    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        passphrase = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        kwargs["private_key"] = _load_private_key(pk_path, passphrase)
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            raise EnvironmentError(
                "Either SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD must be set."
            )
        kwargs["password"] = password

    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role

    return snowflake.connector.connect(**kwargs)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _feature_source_summary(cur, check_date: date) -> dict | None:
    """A1.10 — mean feature_coverage_score + data_source breakdown for the date.

    Returns None when the columns don't exist yet (first deploy) so the core
    coverage check still runs. Defensive: any error degrades to None.
    """
    try:
        # Summarize the LATEST row per game (what the app actually serves) so the
        # counts reflect the current prediction set, not stale earlier runs
        # (morning / a prior intraday_fallback) that also exist for the date.
        cur.execute(
            """
            WITH latest AS (
                SELECT game_pk, data_source, feature_coverage_score
                FROM baseball_data.betting_ml.daily_model_predictions
                WHERE game_date = %s
                QUALIFY ROW_NUMBER() OVER (
                    PARTITION BY game_pk ORDER BY inserted_at DESC
                ) = 1
            )
            SELECT
                AVG(feature_coverage_score)                      AS avg_cov,
                MIN(feature_coverage_score)                      AS min_cov,
                COUNT_IF(data_source = 'feature_store')          AS n_feature_store,
                COUNT_IF(data_source = 'intraday_assembly')      AS n_assembly,
                COUNT_IF(data_source = 'intraday_fallback')      AS n_fallback,
                COUNT(DISTINCT game_pk)                          AS n_games
            FROM latest
            """,
            (check_date.isoformat(),),
        )
        r = cur.fetchone()
        if not r or r[5] == 0:
            return None
        return {
            "avg_cov": r[0], "min_cov": r[1],
            "n_feature_store": r[2], "n_assembly": r[3], "n_fallback": r[4],
            "n_games": r[5],
        }
    except Exception as exc:  # column not yet present, etc.
        log.warning("feature-source summary unavailable (%s)", exc)
        return None


def run(
    check_date: date,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    min_feature_coverage: float = DEFAULT_MIN_FEATURE_COVERAGE,
) -> None:
    con = _get_connection()
    try:
        cur = con.cursor()

        # A1.10 — expected games come from the SCHEDULE (forward-looking), not
        # feature_pregame_game_features. The feature mart is spined on completed
        # games and has zero rows for today, which previously made this check a
        # silent daily no-op (expected_games == 0 → "skipped").
        cur.execute(
            """
            SELECT COUNT(DISTINCT game_pk) AS expected_games
            FROM baseball_data.betting.stg_statsapi_games
            WHERE official_date = %s
              AND game_type = 'R'
            """,
            (check_date.isoformat(),),
        )
        row = cur.fetchone()
        expected_games = row[0] if row else 0

        if expected_games == 0:
            log.info("No regular-season games scheduled on %s — skipping coverage check.", check_date)
            print(f"No games scheduled on {check_date}. Coverage check skipped.")
            return

        cur.execute(
            """
            SELECT COUNT(DISTINCT game_pk) AS scored_games
            FROM baseball_data.betting_ml.daily_model_predictions
            WHERE game_date = %s
            """,
            (check_date.isoformat(),),
        )
        row = cur.fetchone()
        scored_games = row[0] if row else 0

        feat = _feature_source_summary(cur, check_date)
    finally:
        con.close()

    coverage = scored_games / expected_games

    print(f"\n--- Prediction Coverage for {check_date} ---")
    print(f"  Scheduled regular-season games: {expected_games}")
    print(f"  Scored games in daily_model_predictions: {scored_games}")
    print(f"  Coverage: {coverage:.1%} (threshold: {min_coverage:.0%})")

    # A1.10 — feature-source observability. Emit a [METRIC] line for Dagster
    # metadata and warn (non-blocking) on a degraded feature set / fallback days.
    if feat is not None:
        avg_cov = feat["avg_cov"] or 0.0
        print(
            f"  Feature source: feature_store={feat['n_feature_store']} "
            f"intraday_assembly={feat['n_assembly']} intraday_fallback={feat['n_fallback']}"
        )
        print(f"  Mean feature_coverage_score: {avg_cov:.3f} (min {feat['min_cov']}) "
              f"(warn threshold: {min_feature_coverage:.2f})")
        print(f"[METRIC] feature_coverage_score={avg_cov:.4f}")
        if feat["n_fallback"] > 0:
            log.warning(
                "WARN: %d game(s) on %s served via intraday_fallback "
                "(team rolling stats only — no lineup/starter overlay).",
                feat["n_fallback"], check_date,
            )
        if avg_cov < min_feature_coverage:
            log.warning(
                "WARN: mean feature_coverage_score %.3f below threshold %.2f on %s — "
                "the live feature set is degraded.",
                avg_cov, min_feature_coverage, check_date,
            )

    if coverage < min_coverage:
        log.error(
            "ALERT: Prediction coverage %.1f%% is below threshold %.0f%% on %s",
            coverage * 100, min_coverage * 100, check_date,
        )
        sys.exit(1)

    print(f"\nCoverage check passed ({coverage:.1%}).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that daily_model_predictions covers all scheduled games."
    )
    parser.add_argument("--date", default=None,
                        help="Game date in YYYY-MM-DD format (default: today ET)")
    parser.add_argument("--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE,
                        help=f"Minimum coverage fraction to pass (default: {DEFAULT_MIN_COVERAGE})")
    parser.add_argument("--min-feature-coverage", type=float, default=DEFAULT_MIN_FEATURE_COVERAGE,
                        help=f"Non-blocking warn threshold on mean feature_coverage_score "
                             f"(default: {DEFAULT_MIN_FEATURE_COVERAGE})")
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        check_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(check_date=check_date, min_coverage=args.min_coverage,
        min_feature_coverage=args.min_feature_coverage)


if __name__ == "__main__":
    main()
