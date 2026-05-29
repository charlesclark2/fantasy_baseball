"""backfill_market_features_scd2.py
-----------------------------------
Builds or incrementally updates the SCD-2 table
baseball_data.betting_features.feature_pregame_market_features (Story 15.1).

Source: baseball_data.betting.mart_odds_outcomes (unified OddsAPI + Parlay API)
        joined to baseball_data.betting.mart_game_odds_bridge for game_pk.

Algorithm:
  For each (game_pk, bookmaker_key, market_type) chain, sorted by ingestion_ts:
    1. Pivot outcome rows into one record per snapshot.
    2. Compute MD5(price columns) as record_hash.
    3. Emit a new SCD-2 row only when the hash differs from the prior snapshot (LAG).
    4. valid_from  = ingestion_ts of the first snapshot in that hash run.
       valid_to    = ingestion_ts of the next changed snapshot (NULL if still current).
    5. MERGE into the target table — idempotent on (game_pk, market_type,
       bookmaker_key, valid_from).

Coverage:
  Odds API:   2021-01-01 onward (append-only raw; full replay possible)
  Parlay API: 2026-05-26 onward (live start)

Usage:
    uv run python scripts/backfill_market_features_scd2.py
    uv run python scripts/backfill_market_features_scd2.py --dry-run
    uv run python scripts/backfill_market_features_scd2.py --bookmakers lowvig bovada
    uv run python scripts/backfill_market_features_scd2.py --since 2026-01-01
    uv run python scripts/backfill_market_features_scd2.py --target dev
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from betting_ml.utils.data_loader import get_snowflake_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# Default bookmakers to include. Covers the lowvig benchmark (feature_pregame_odds_features),
# sharp-side books used in consensus/disagreement marts, and major recreational books.
_DEFAULT_BOOKMAKERS = [
    "lowvig",
    "betonlineag",
    "bovada",
    "draftkings",
    "fanduel",
    "williamhill_us",
    "betmgm",
    "caesars",
]

_PROD_TARGET = "baseball_data.betting_features.feature_pregame_market_features"
_DEV_TARGET  = "baseball_data.dev_betting_features.feature_pregame_market_features"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_BACKFILL_SQL = """
MERGE INTO {target} AS tgt
USING (
    WITH

    bridge AS (
        SELECT
            event_id,
            odds_api_event_id,
            game_pk,
            game_date::date AS game_date
        FROM baseball_data.betting.mart_game_odds_bridge
        WHERE event_id IS NOT NULL
    ),

    -- Join mart_odds_outcomes to the bridge.
    -- Two-path join: Parlay API rows match on bridge.event_id (= parlay_api_event_id
    -- when available); OddsAPI rows for games that also have a Parlay ID use the
    -- odds_api_event_id fallback (same pattern as mart_bookmaker_disagreement).
    -- Leakage guard: bookmaker_last_update < commence_time (pre-game only).
    raw_pre_game AS (
        SELECT
            b.game_pk,
            b.game_date,
            o.bookmaker_key,
            o.market_key,
            o.bookmaker_last_update,    -- canonical line-state timestamp (not bulk-load date)
            o.ingestion_ts,
            o.commence_time,
            o.source_system,
            o.outcome_name,
            o.outcome_price_american,
            o.outcome_price_decimal,
            o.outcome_point,
            o.is_home_outcome,
            o.is_away_outcome
        FROM baseball_data.betting.mart_odds_outcomes o
        INNER JOIN bridge b
            ON  b.event_id = o.event_id
            OR (b.odds_api_event_id IS NOT NULL AND b.odds_api_event_id = o.event_id)
        WHERE o.bookmaker_last_update < o.commence_time
          AND o.bookmaker_key IN ({bookmaker_list})
          AND o.market_key IN ('h2h', 'totals')
          {since_filter}
    ),

    -- Pivot outcome rows into one record per (game_pk, bookmaker_key, market_key, bookmaker_last_update).
    -- Group by bookmaker_last_update (not ingestion_ts) so that repeated live-poll snapshots of
    -- the same unchanged line collapse into a single row. For bulk-loaded historical Odds API data
    -- this also gives the correct anchor timestamp (when the bookmaker last set that line, e.g.
    -- 2024-06-15), rather than the bulk-load date (2026-04-24).
    pivoted AS (
        SELECT
            game_pk,
            game_date,
            bookmaker_key,
            market_key                                                                  AS market_type,
            bookmaker_last_update,
            MAX(ingestion_ts)                                                           AS ingestion_ts,
            MAX(commence_time)                                                          AS commence_time,
            MAX(source_system)                                                          AS source_system,
            -- h2h columns
            MAX(CASE WHEN market_key = 'h2h' AND is_home_outcome THEN outcome_price_american END)   AS home_moneyline_american,
            MAX(CASE WHEN market_key = 'h2h' AND is_away_outcome THEN outcome_price_american END)   AS away_moneyline_american,
            MAX(CASE WHEN market_key = 'h2h' AND is_home_outcome THEN outcome_price_decimal  END)   AS home_moneyline_decimal,
            MAX(CASE WHEN market_key = 'h2h' AND is_away_outcome THEN outcome_price_decimal  END)   AS away_moneyline_decimal,
            -- totals columns
            MAX(CASE WHEN market_key = 'totals' AND outcome_name = 'Over'  THEN outcome_point          END)   AS total_line,
            MAX(CASE WHEN market_key = 'totals' AND outcome_name = 'Over'  THEN outcome_price_american END)   AS over_american,
            MAX(CASE WHEN market_key = 'totals' AND outcome_name = 'Under' THEN outcome_price_american END)   AS under_american,
            MAX(CASE WHEN market_key = 'totals' AND outcome_name = 'Over'  THEN outcome_price_decimal  END)   AS over_decimal,
            MAX(CASE WHEN market_key = 'totals' AND outcome_name = 'Under' THEN outcome_price_decimal  END)   AS under_decimal
        FROM raw_pre_game
        GROUP BY game_pk, game_date, bookmaker_key, market_key, bookmaker_last_update
    ),

    -- Derive vig-adjusted implied probs and record hash.
    with_derived AS (
        SELECT
            game_pk,
            game_date,
            bookmaker_key,
            market_type,
            bookmaker_last_update,
            ingestion_ts,
            commence_time,
            source_system,
            home_moneyline_american,
            away_moneyline_american,
            home_moneyline_decimal,
            away_moneyline_decimal,
            -- h2h implied probs
            CASE WHEN home_moneyline_decimal IS NOT NULL AND away_moneyline_decimal IS NOT NULL
                 THEN (1.0 / home_moneyline_decimal)
                      / ((1.0 / home_moneyline_decimal) + (1.0 / away_moneyline_decimal))
            END::FLOAT                                          AS home_implied_prob,
            CASE WHEN home_moneyline_decimal IS NOT NULL AND away_moneyline_decimal IS NOT NULL
                 THEN (1.0 / away_moneyline_decimal)
                      / ((1.0 / home_moneyline_decimal) + (1.0 / away_moneyline_decimal))
            END::FLOAT                                          AS away_implied_prob,
            CASE WHEN market_type = 'h2h'
                  AND home_moneyline_decimal IS NOT NULL AND away_moneyline_decimal IS NOT NULL
                 THEN (1.0 / home_moneyline_decimal) + (1.0 / away_moneyline_decimal) - 1.0
            END::FLOAT                                          AS total_market_vig,
            -- totals columns
            total_line,
            over_american,
            under_american,
            over_decimal,
            under_decimal,
            -- totals implied probs
            CASE WHEN over_decimal IS NOT NULL AND under_decimal IS NOT NULL
                 THEN (1.0 / over_decimal)
                      / ((1.0 / over_decimal) + (1.0 / under_decimal))
            END::FLOAT                                          AS over_implied_prob,
            CASE WHEN over_decimal IS NOT NULL AND under_decimal IS NOT NULL
                 THEN (1.0 / under_decimal)
                      / ((1.0 / over_decimal) + (1.0 / under_decimal))
            END::FLOAT                                          AS under_implied_prob,
            CASE WHEN market_type = 'totals'
                  AND over_decimal IS NOT NULL AND under_decimal IS NOT NULL
                 THEN (1.0 / over_decimal) + (1.0 / under_decimal) - 1.0
            END::FLOAT                                          AS totals_market_vig,
            -- Record hash over price columns that trigger a new SCD-2 row on change.
            MD5(CONCAT_WS('|',
                COALESCE(TO_VARCHAR(home_moneyline_american), ''),
                COALESCE(TO_VARCHAR(away_moneyline_american), ''),
                COALESCE(TO_VARCHAR(total_line), ''),
                COALESCE(TO_VARCHAR(over_american), ''),
                COALESCE(TO_VARCHAR(under_american), '')
            ))                                                  AS record_hash
        FROM pivoted
    ),

    -- Detect state changes: emit a row only when record_hash differs from the
    -- immediately prior snapshot for the same natural key. Order by bookmaker_last_update
    -- so the sequence reflects actual line-movement chronology, not ingestion order.
    with_change_detection AS (
        SELECT
            *,
            LAG(record_hash) OVER (
                PARTITION BY game_pk, bookmaker_key, market_type
                ORDER BY bookmaker_last_update
            ) AS prev_hash
        FROM with_derived
    ),

    changed_rows AS (
        SELECT * FROM with_change_detection
        WHERE prev_hash IS NULL OR prev_hash != record_hash
    ),

    -- Compute valid_from / valid_to / is_current over the filtered changed-rows set.
    -- valid_from = bookmaker_last_update: when the bookmaker actually set this line state.
    -- valid_to   = bookmaker_last_update of the next changed row (NULL if still current).
    -- LEAD skips unchanged snapshots because we're operating on changed_rows only.
    final AS (
        SELECT
            game_pk,
            market_type,
            bookmaker_key,
            game_date,
            commence_time,
            home_moneyline_american,
            away_moneyline_american,
            home_moneyline_decimal,
            away_moneyline_decimal,
            home_implied_prob,
            away_implied_prob,
            total_market_vig,
            total_line,
            over_american,
            under_american,
            over_decimal,
            under_decimal,
            over_implied_prob,
            under_implied_prob,
            totals_market_vig,
            source_system,
            ingestion_ts,
            -- SCD-2 temporal columns — anchored to bookmaker_last_update, not ingestion_ts.
            -- This ensures AS-OF queries for historical games (bulk-loaded Odds API data)
            -- use the actual line-set timestamp rather than the 2026-04-24 bulk-load date.
            bookmaker_last_update           AS valid_from,
            LEAD(bookmaker_last_update) OVER (
                PARTITION BY game_pk, bookmaker_key, market_type
                ORDER BY bookmaker_last_update
            )                               AS valid_to,
            LEAD(bookmaker_last_update) OVER (
                PARTITION BY game_pk, bookmaker_key, market_type
                ORDER BY bookmaker_last_update
            ) IS NULL                       AS is_current,
            record_hash,
            CURRENT_TIMESTAMP()::TIMESTAMP_NTZ AS computed_at
        FROM changed_rows
    )

    SELECT * FROM final

) AS src
ON  tgt.game_pk       = src.game_pk
AND tgt.market_type   = src.market_type
AND tgt.bookmaker_key = src.bookmaker_key
AND tgt.valid_from    = src.valid_from

WHEN MATCHED THEN UPDATE SET
    -- Re-apply valid_to and is_current in case a previously-current row
    -- has since been closed out by a new line movement.
    tgt.valid_to    = src.valid_to,
    tgt.is_current  = src.is_current,
    tgt.computed_at = src.computed_at

WHEN NOT MATCHED THEN INSERT (
    game_pk, market_type, bookmaker_key,
    game_date, commence_time,
    home_moneyline_american, away_moneyline_american,
    home_moneyline_decimal, away_moneyline_decimal,
    home_implied_prob, away_implied_prob, total_market_vig,
    total_line, over_american, under_american,
    over_decimal, under_decimal,
    over_implied_prob, under_implied_prob, totals_market_vig,
    source_system, ingestion_ts,
    valid_from, valid_to, is_current, record_hash, computed_at
) VALUES (
    src.game_pk, src.market_type, src.bookmaker_key,
    src.game_date, src.commence_time,
    src.home_moneyline_american, src.away_moneyline_american,
    src.home_moneyline_decimal, src.away_moneyline_decimal,
    src.home_implied_prob, src.away_implied_prob, src.total_market_vig,
    src.total_line, src.over_american, src.under_american,
    src.over_decimal, src.under_decimal,
    src.over_implied_prob, src.under_implied_prob, src.totals_market_vig,
    src.source_system, src.ingestion_ts,
    src.valid_from, src.valid_to, src.is_current, src.record_hash, src.computed_at
)
"""

_COUNT_SQL = "SELECT COUNT(*) FROM {target}"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--bookmakers", nargs="+", default=_DEFAULT_BOOKMAKERS,
        metavar="BOOK",
        help="Bookmakers to include (default: %(default)s)",
    )
    p.add_argument(
        "--since",
        metavar="YYYY-MM-DD",
        help="Only process odds with ingestion_ts >= this date. Useful for incremental runs.",
    )
    p.add_argument(
        "--target", choices=["prod", "dev"], default="prod",
        help="Write to prod or dev schema (default: prod)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the generated SQL but do not execute it.",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    target_table = _PROD_TARGET if args.target == "prod" else _DEV_TARGET
    bookmaker_list = ", ".join(f"'{b}'" for b in args.bookmakers)
    since_filter = (
        f"AND b.game_date >= '{args.since}'::date" if args.since else ""
    )

    sql = _BACKFILL_SQL.format(
        target=target_table,
        bookmaker_list=bookmaker_list,
        since_filter=since_filter,
    )

    if args.dry_run:
        print(sql)
        return

    log.info("Target table : %s", target_table)
    log.info("Bookmakers   : %s", args.bookmakers)
    if args.since:
        log.info("Since filter : game_date >= %s", args.since)

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        # Row count before
        cur.execute(_COUNT_SQL.format(target=target_table))
        before = cur.fetchone()[0]
        log.info("Rows before  : %d", before)

        log.info("Running MERGE …")
        cur.execute(sql)
        rows_affected = cur.rowcount
        log.info("Rows affected: %d (inserts + updates)", rows_affected)

        # Row count after
        cur.execute(_COUNT_SQL.format(target=target_table))
        after = cur.fetchone()[0]
        log.info("Rows after   : %d  (+%d)", after, after - before)

        cur.close()
    finally:
        conn.close()

    log.info("Done.")


if __name__ == "__main__":
    main()
