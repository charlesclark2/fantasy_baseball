"""backfill_lineup_state_scd2.py
-----------------------------------
Builds or incrementally updates the SCD-2 table
baseball_data.betting_features.feature_pregame_lineup_state (Story 15.2).

Source: baseball_data.statsapi.monthly_schedule (append-only, post-Epic-T)
  Each row in monthly_schedule contains a full month's schedule JSON including
  lineup data for games that have confirmed lineups. The ingest script writes
  a new row on every run, so the same lineup may appear in hundreds of
  successive snapshots.

Algorithm:
  For each (game_pk, home_away) chain, sorted by ingestion_ts:
    1. Flatten JSON → pivot wide (one row per snapshot per game × side).
    2. Compute MD5(slot_1..9 player_ids) as record_hash.
    3. Emit a new SCD-2 row only when the hash differs from the prior snapshot.
    4. valid_from = ingestion_ts of the first snapshot in that hash run.
       valid_to   = ingestion_ts of the next changed snapshot (NULL if current).
    5. MERGE into the target table — idempotent on (game_pk, home_away, valid_from).

Coverage:
  Forward-only from Epic T conversion date (2026-05-12).
  Pre-Epic-T rows have NULL ingestion_ts and are skipped.

Usage:
    uv run python scripts/backfill_lineup_state_scd2.py
    uv run python scripts/backfill_lineup_state_scd2.py --dry-run
    uv run python scripts/backfill_lineup_state_scd2.py --since 2026-05-20
    uv run python scripts/backfill_lineup_state_scd2.py --target dev
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

_PROD_TARGET = "baseball_data.betting_features.feature_pregame_lineup_state"
_DEV_TARGET  = "baseball_data.dev_betting_features.feature_pregame_lineup_state"

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_BACKFILL_SQL = """
MERGE INTO {target} AS tgt
USING (
    WITH

    -- Flatten monthly_schedule JSON to one row per (game_pk, home_away, batting_order, ingestion_ts).
    -- Only post-Epic-T rows (ingestion_ts IS NOT NULL) are processed; pre-T history is unavailable.
    dates_flat AS (
        SELECT d.value AS date_obj, ingestion_ts
        FROM baseball_data.statsapi.monthly_schedule,
        LATERAL FLATTEN(input => json_field:dates) d
        WHERE ingestion_ts IS NOT NULL
    ),

    games_flat AS (
        SELECT g.value AS game, ingestion_ts
        FROM dates_flat,
        LATERAL FLATTEN(input => date_obj:games) g
    ),

    home_slots AS (
        SELECT
            game:gamePk::INTEGER                                    AS game_pk,
            game:officialDate::DATE                                 AS official_date,
            'home'                                                  AS home_away,
            p.index + 1                                             AS batting_order,
            p.value:id::INTEGER                                     AS player_id,
            p.value:primaryPosition:abbreviation::VARCHAR           AS position_abbr,
            ingestion_ts
        FROM games_flat,
        LATERAL FLATTEN(input => game:lineups:homePlayers) p
    ),

    away_slots AS (
        SELECT
            game:gamePk::INTEGER                                    AS game_pk,
            game:officialDate::DATE                                 AS official_date,
            'away'                                                  AS home_away,
            p.index + 1                                             AS batting_order,
            p.value:id::INTEGER                                     AS player_id,
            p.value:primaryPosition:abbreviation::VARCHAR           AS position_abbr,
            ingestion_ts
        FROM games_flat,
        LATERAL FLATTEN(input => game:lineups:awayPlayers) p
    ),

    all_slots AS (
        SELECT * FROM home_slots
        UNION ALL
        SELECT * FROM away_slots
    ),

    -- Pivot slot rows to one wide row per (game_pk, home_away, ingestion_ts).
    -- Multiple ingest snapshots with identical composition will produce identical
    -- hashes and collapse into a single SCD-2 row in the change-detection step.
    -- since_filter applied here to limit data volume for incremental runs.
    pivoted AS (
        SELECT
            game_pk,
            official_date,
            home_away,
            ingestion_ts,
            MAX(CASE WHEN batting_order = 1 THEN player_id   END)   AS slot_1_player_id,
            MAX(CASE WHEN batting_order = 1 THEN position_abbr END) AS slot_1_position,
            MAX(CASE WHEN batting_order = 2 THEN player_id   END)   AS slot_2_player_id,
            MAX(CASE WHEN batting_order = 2 THEN position_abbr END) AS slot_2_position,
            MAX(CASE WHEN batting_order = 3 THEN player_id   END)   AS slot_3_player_id,
            MAX(CASE WHEN batting_order = 3 THEN position_abbr END) AS slot_3_position,
            MAX(CASE WHEN batting_order = 4 THEN player_id   END)   AS slot_4_player_id,
            MAX(CASE WHEN batting_order = 4 THEN position_abbr END) AS slot_4_position,
            MAX(CASE WHEN batting_order = 5 THEN player_id   END)   AS slot_5_player_id,
            MAX(CASE WHEN batting_order = 5 THEN position_abbr END) AS slot_5_position,
            MAX(CASE WHEN batting_order = 6 THEN player_id   END)   AS slot_6_player_id,
            MAX(CASE WHEN batting_order = 6 THEN position_abbr END) AS slot_6_position,
            MAX(CASE WHEN batting_order = 7 THEN player_id   END)   AS slot_7_player_id,
            MAX(CASE WHEN batting_order = 7 THEN position_abbr END) AS slot_7_position,
            MAX(CASE WHEN batting_order = 8 THEN player_id   END)   AS slot_8_player_id,
            MAX(CASE WHEN batting_order = 8 THEN position_abbr END) AS slot_8_position,
            MAX(CASE WHEN batting_order = 9 THEN player_id   END)   AS slot_9_player_id,
            MAX(CASE WHEN batting_order = 9 THEN position_abbr END) AS slot_9_position,
            (
                MAX(CASE WHEN batting_order = 1 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 2 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 3 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 4 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 5 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 6 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 7 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 8 THEN player_id END) IS NOT NULL AND
                MAX(CASE WHEN batting_order = 9 THEN player_id END) IS NOT NULL
            )::BOOLEAN                                              AS has_full_lineup
        FROM all_slots
        {since_filter}
        GROUP BY game_pk, official_date, home_away, ingestion_ts
    ),

    -- Only process rows where the lineup has at least one player (slot_1 not null).
    -- Snapshots where the lineup is completely absent (game not yet confirmed) are excluded.
    non_empty AS (
        SELECT * FROM pivoted
        WHERE slot_1_player_id IS NOT NULL
    ),

    -- Compute record hash over the 9 player_ids.
    -- Position changes for the same player do not trigger a new SCD-2 row.
    with_hash AS (
        SELECT
            *,
            MD5(CONCAT_WS('|',
                COALESCE(TO_VARCHAR(slot_1_player_id), ''),
                COALESCE(TO_VARCHAR(slot_2_player_id), ''),
                COALESCE(TO_VARCHAR(slot_3_player_id), ''),
                COALESCE(TO_VARCHAR(slot_4_player_id), ''),
                COALESCE(TO_VARCHAR(slot_5_player_id), ''),
                COALESCE(TO_VARCHAR(slot_6_player_id), ''),
                COALESCE(TO_VARCHAR(slot_7_player_id), ''),
                COALESCE(TO_VARCHAR(slot_8_player_id), ''),
                COALESCE(TO_VARCHAR(slot_9_player_id), '')
            )) AS record_hash
        FROM non_empty
    ),

    -- Detect state changes: emit a row only when record_hash differs from the
    -- immediately prior snapshot for this (game_pk, home_away) chain.
    -- ORDER BY ingestion_ts reflects actual observation chronology.
    with_change_detection AS (
        SELECT
            *,
            LAG(record_hash) OVER (
                PARTITION BY game_pk, home_away
                ORDER BY ingestion_ts
            ) AS prev_hash
        FROM with_hash
    ),

    changed_rows AS (
        SELECT * FROM with_change_detection
        WHERE prev_hash IS NULL OR prev_hash != record_hash
    ),

    -- Compute valid_from / valid_to / is_current over the filtered changed-rows set.
    -- valid_from = ingestion_ts: when this lineup composition was first observed.
    -- valid_to   = ingestion_ts of the next changed observation (NULL if still current).
    final AS (
        SELECT
            game_pk,
            home_away,
            official_date,
            has_full_lineup,
            slot_1_player_id,   slot_1_position,
            slot_2_player_id,   slot_2_position,
            slot_3_player_id,   slot_3_position,
            slot_4_player_id,   slot_4_position,
            slot_5_player_id,   slot_5_position,
            slot_6_player_id,   slot_6_position,
            slot_7_player_id,   slot_7_position,
            slot_8_player_id,   slot_8_position,
            slot_9_player_id,   slot_9_position,
            ingestion_ts,
            -- SCD-2 temporal columns anchored to ingestion_ts (when we observed this state).
            ingestion_ts                            AS valid_from,
            LEAD(ingestion_ts) OVER (
                PARTITION BY game_pk, home_away
                ORDER BY ingestion_ts
            )                                       AS valid_to,
            LEAD(ingestion_ts) OVER (
                PARTITION BY game_pk, home_away
                ORDER BY ingestion_ts
            ) IS NULL                               AS is_current,
            record_hash,
            CURRENT_TIMESTAMP()::TIMESTAMP_NTZ      AS computed_at
        FROM changed_rows
    )

    SELECT * FROM final

) AS src
ON  tgt.game_pk   = src.game_pk
AND tgt.home_away = src.home_away
AND tgt.valid_from = src.valid_from

WHEN MATCHED THEN UPDATE SET
    -- Re-apply valid_to and is_current in case a previously-current row
    -- has since been closed out by a new lineup change.
    tgt.valid_to    = src.valid_to,
    tgt.is_current  = src.is_current,
    tgt.computed_at = src.computed_at

WHEN NOT MATCHED THEN INSERT (
    game_pk, home_away,
    official_date, has_full_lineup,
    slot_1_player_id, slot_1_position,
    slot_2_player_id, slot_2_position,
    slot_3_player_id, slot_3_position,
    slot_4_player_id, slot_4_position,
    slot_5_player_id, slot_5_position,
    slot_6_player_id, slot_6_position,
    slot_7_player_id, slot_7_position,
    slot_8_player_id, slot_8_position,
    slot_9_player_id, slot_9_position,
    ingestion_ts,
    valid_from, valid_to, is_current, record_hash, computed_at
) VALUES (
    src.game_pk, src.home_away,
    src.official_date, src.has_full_lineup,
    src.slot_1_player_id, src.slot_1_position,
    src.slot_2_player_id, src.slot_2_position,
    src.slot_3_player_id, src.slot_3_position,
    src.slot_4_player_id, src.slot_4_position,
    src.slot_5_player_id, src.slot_5_position,
    src.slot_6_player_id, src.slot_6_position,
    src.slot_7_player_id, src.slot_7_position,
    src.slot_8_player_id, src.slot_8_position,
    src.slot_9_player_id, src.slot_9_position,
    src.ingestion_ts,
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
        "--since",
        metavar="YYYY-MM-DD",
        help=(
            "Only process games with official_date >= this date. "
            "Processes all ingestion snapshots for those games. "
            "Useful for incremental runs (e.g. --since 2-days-ago)."
        ),
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

    # since_filter is applied as a WHERE clause in the pivoted CTE so all
    # ingestion snapshots for qualifying games are included in the chain.
    # This ensures LAG/LEAD windows see the full history for those games.
    since_filter = (
        f"WHERE official_date >= '{args.since}'::date" if args.since else ""
    )

    sql = _BACKFILL_SQL.format(
        target=target_table,
        since_filter=since_filter,
    )

    if args.dry_run:
        print(sql)
        return

    log.info("Target table : %s", target_table)
    if args.since:
        log.info("Since filter : official_date >= %s", args.since)

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
