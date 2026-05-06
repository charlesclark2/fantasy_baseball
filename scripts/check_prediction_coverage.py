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


def run(check_date: date, min_coverage: float = DEFAULT_MIN_COVERAGE) -> None:
    con = _get_connection()
    try:
        cur = con.cursor()

        cur.execute(
            """
            SELECT COUNT(*) AS expected_games
            FROM baseball_data.betting_features.feature_pregame_game_features
            WHERE game_date = %s
              AND has_full_data = true
            """,
            (check_date.isoformat(),),
        )
        row = cur.fetchone()
        expected_games = row[0] if row else 0

        if expected_games == 0:
            log.info("No games scheduled with confirmed lineups on %s — skipping coverage check.", check_date)
            print(f"No games scheduled on {check_date}. Coverage check skipped.")
            return

        cur.execute(
            """
            SELECT COUNT(*) AS scored_games
            FROM baseball_data.betting_ml.daily_model_predictions
            WHERE game_date = %s
            """,
            (check_date.isoformat(),),
        )
        row = cur.fetchone()
        scored_games = row[0] if row else 0
    finally:
        con.close()

    coverage = scored_games / expected_games

    print(f"\n--- Prediction Coverage for {check_date} ---")
    print(f"  Expected games (has_full_lineup=true): {expected_games}")
    print(f"  Scored games in daily_model_predictions: {scored_games}")
    print(f"  Coverage: {coverage:.1%} (threshold: {min_coverage:.0%})")

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
    args = parser.parse_args()

    if args.date:
        check_date = date.fromisoformat(args.date)
    else:
        from zoneinfo import ZoneInfo
        check_date = datetime.now(ZoneInfo("America/New_York")).date()

    run(check_date=check_date, min_coverage=args.min_coverage)


if __name__ == "__main__":
    main()
