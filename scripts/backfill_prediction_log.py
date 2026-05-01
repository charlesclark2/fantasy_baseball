"""
backfill_prediction_log.py
--------------------------
Nightly backfill of actual_outcome and closing_market_prob in
baseball_data.config.prediction_log.

Run after dbt build so mart tables are current.

Updates are idempotent (only touches rows where the column IS NULL) so reruns
are safe. Prints row counts for each update step and exits non-zero on error.

Snowflake auth — same env-var pattern as other scripts in this directory:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE              (optional)
"""

from __future__ import annotations

import logging
import os
import sys

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

# ---------------------------------------------------------------------------
# SQL — actual_outcome
# ---------------------------------------------------------------------------

_UPDATE_OUTCOME_H2H = """
UPDATE baseball_data.config.prediction_log pl
SET actual_outcome = CASE WHEN mgr.home_team_won THEN 1.0 ELSE 0.0 END
FROM baseball_data.betting.mart_game_results mgr
WHERE pl.game_pk = mgr.game_pk
  AND pl.market = 'h2h'
  AND pl.actual_outcome IS NULL
"""

_UPDATE_OUTCOME_TOTALS = """
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

# ---------------------------------------------------------------------------
# SQL — closing_market_prob
# Uses last ingestion_ts before game commence_time (requires live odds data).
# Games where odds were never ingested before first pitch will remain NULL.
# ---------------------------------------------------------------------------

_UPDATE_CLOSING_H2H = """
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

_UPDATE_CLOSING_TOTALS = """
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

# ---------------------------------------------------------------------------
# SQL — closing_market_prob fallback (historical / post-game ingested odds)
# Used when no pre-game snapshot exists (e.g. early-season games ingested
# retroactively via The Odds API historical endpoint).  The API returns the
# closing line for completed events, so this is still a valid CLV proxy.
# Only touches rows that are still NULL after the live-snapshot queries above.
# ---------------------------------------------------------------------------

_UPDATE_CLOSING_H2H_FALLBACK = """
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

_UPDATE_CLOSING_TOTALS_FALLBACK = """
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
        "schema":    "config",
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


def _run_update(cur: snowflake.connector.cursor.SnowflakeCursor, label: str, sql: str) -> int:
    log.info("Running: %s", label)
    cur.execute(sql)
    rows = cur.rowcount or 0
    log.info("  → %d row(s) updated", rows)
    return rows


def main() -> None:
    steps = [
        ("actual_outcome  h2h",              _UPDATE_OUTCOME_H2H),
        ("actual_outcome  totals",           _UPDATE_OUTCOME_TOTALS),
        ("closing_market_prob h2h",          _UPDATE_CLOSING_H2H),
        ("closing_market_prob totals",       _UPDATE_CLOSING_TOTALS),
        ("closing_market_prob h2h fallback",     _UPDATE_CLOSING_H2H_FALLBACK),
        ("closing_market_prob totals fallback",  _UPDATE_CLOSING_TOTALS_FALLBACK),
    ]

    conn = _get_connection()
    try:
        cur = conn.cursor()
        total = 0
        for label, sql in steps:
            total += _run_update(cur, label, sql)
        log.info("Backfill complete — %d total row(s) updated across all steps.", total)
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.error("Backfill failed: %s", exc)
        sys.exit(1)
