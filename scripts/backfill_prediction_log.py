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


def _get_connection() -> snowflake.connector.SnowflakeConnection:
    # INC-22 straggler cure (2026-07-05): the box authenticates via the INLINE key
    # (SNOWFLAKE_PRIVATE_KEY), NOT a key FILE, and has NO SNOWFLAKE_PASSWORD — the old
    # file-path→password resolver KeyError'd on the box. Delegate to the shared
    # PATH-if-exists→inline→password resolver. Queries are fully-qualified, so the default
    # schema is immaterial. See CLAUDE.md INC-22 landmine.
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from betting_ml.utils.data_loader import get_snowflake_connection
    return get_snowflake_connection(schema="config")


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
