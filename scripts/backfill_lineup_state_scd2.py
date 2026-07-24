"""backfill_lineup_state_scd2.py
-----------------------------------
Builds or incrementally updates the SCD-2 table
baseball_data.betting_features.feature_pregame_lineup_state (Story 15.2).

Source (2026-07-23): baseball_data.lakehouse_ext.stg_statsapi_lineups — the FRESH,
  S3-backed flattened confirmed-lineup feed (one row per game_pk × side × batting slot,
  latest snapshot). This REPLACES the previous `statsapi.monthly_schedule` VARIANT flatten,
  whose native writer was RETIRED 2026-07-20 when schedule capture went S3-native → that table
  FROZE at 7/20 and this SCD-2 table stopped advancing (feature_pregame_lineup_state max
  official_date stuck at 2026-07-20; the pre-lineup archetype/h2h/cluster matchup features that
  read it served stale). See CLAUDE.md "retired native source" landmine + the guard
  betting_ml/tests/test_retired_source_guard.py.

Algorithm (idempotent compare-to-target upsert):
  stg_statsapi_lineups is latest-snapshot only (no append-only history), so the old
  LAG/LEAD-over-snapshots change detection can't apply. Instead, per run:
    1. Build the CURRENT lineup state per (game_pk, home_away): take the latest snapshot,
       pivot the 9 slots wide, compute record_hash = MD5 over the 9 player_ids (IDENTICAL
       expression to the historical rows, so an unchanged lineup hashes the same → no-op).
    2. CLOSE: for a (game, side) whose existing is_current row has a DIFFERENT hash than the
       current lineup, set is_current=FALSE + valid_to = the new observation ts.
    3. INSERT: a new is_current=TRUE row for any current lineup whose hash is not already the
       is_current one (valid_from = the observation ts).
  Idempotent: re-running with an unchanged lineup closes nothing and inserts nothing. A lineup
  change closes the prior row and opens a new one — a clean SCD-2 chain (valid_to_old = valid_from_new).
  Only games in the --since window are touched, so historical/completed rows are never rewritten.

Coverage:
  Forward-only; the fresh feed carries current + recent games. Rows with slot_1 NULL
  (lineup not yet confirmed) are excluded.

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

# FRESH S3-backed source (external table) — replaces the retired statsapi.monthly_schedule flatten.
_SOURCE = "baseball_data.lakehouse_ext.stg_statsapi_lineups"

# ---------------------------------------------------------------------------
# SQL — built from per-slot fragments so the 9 batting slots stay in lockstep.
# ---------------------------------------------------------------------------

_SLOTS = range(1, 10)

_pivot_player = ",\n".join(
    f"            MAX(CASE WHEN batting_order = {i} THEN player_id END)    AS slot_{i}_player_id"
    for i in _SLOTS
)
_pivot_pos = ",\n".join(
    f"            MAX(CASE WHEN batting_order = {i} THEN position_abbr END) AS slot_{i}_position"
    for i in _SLOTS
)
_pass_slots = ", ".join(f"slot_{i}_player_id, slot_{i}_position" for i in _SLOTS)
# record_hash MUST match the historical rows' expression exactly (MD5 over the 9 player_ids)
# so an unchanged lineup hashes identically → the compare-to-target upsert is a true no-op.
_hash_args = ",\n".join(
    f"            COALESCE(TO_VARCHAR(slot_{i}_player_id), '')" for i in _SLOTS
)
# has_full_lineup is computed in the SAME pivot SELECT that defines the slot aliases, so it must use
# the full MAX(CASE ...) expressions (a column alias can't be referenced elsewhere in its own SELECT).
_full_lineup = " AND\n".join(
    f"            MAX(CASE WHEN batting_order = {i} THEN player_id END) IS NOT NULL" for i in _SLOTS
)
_insert_cols = ", ".join(f"slot_{i}_player_id, slot_{i}_position" for i in _SLOTS)
_insert_sel = ", ".join(f"cs.slot_{i}_player_id, cs.slot_{i}_position" for i in _SLOTS)

# Current lineup state per (game_pk, home_away): latest snapshot → pivot wide → record_hash.
# {since_filter} is filled by main(); no other literal braces appear in the SQL.
_CURRENT_STATE = (
    "    SELECT\n"
    "        game_pk, official_date, home_away, ingestion_ts,\n"
    f"        {_pass_slots},\n"
    "        has_full_lineup,\n"
    "        MD5(CONCAT_WS('|',\n"
    f"{_hash_args}\n"
    "        )) AS record_hash\n"
    "    FROM (\n"
    "        SELECT\n"
    "            game_pk, official_date, home_away,\n"
    "            MAX(ingestion_ts) AS ingestion_ts,\n"
    f"{_pivot_player},\n"
    f"{_pivot_pos},\n"
    "            (\n"
    f"{_full_lineup}\n"
    "            )::BOOLEAN AS has_full_lineup\n"
    "        FROM (\n"
    "            SELECT game_pk, official_date, home_away, batting_order,\n"
    "                   player_id, position_abbreviation AS position_abbr, ingestion_ts\n"
    f"            FROM {_SOURCE}\n"
    "            WHERE ingestion_ts IS NOT NULL\n"
    "              {since_filter}\n"
    "            QUALIFY ingestion_ts = MAX(ingestion_ts) OVER (PARTITION BY game_pk, home_away)\n"
    "        )\n"
    "        GROUP BY game_pk, official_date, home_away\n"
    "    )\n"
    "    WHERE slot_1_player_id IS NOT NULL\n"
)

# Step 1 — close out is_current rows whose lineup has changed (hash differs from the current state).
_CLOSE_SQL = (
    "UPDATE {target} AS tgt\n"
    "SET is_current  = FALSE,\n"
    "    valid_to    = cs.ingestion_ts,\n"
    "    computed_at = CURRENT_TIMESTAMP()::TIMESTAMP_NTZ\n"
    "FROM (\n" + _CURRENT_STATE + ") cs\n"
    "WHERE tgt.game_pk    = cs.game_pk\n"
    "  AND tgt.home_away  = cs.home_away\n"
    "  AND tgt.is_current = TRUE\n"
    "  AND tgt.record_hash <> cs.record_hash\n"
)

# Step 2 — open a new is_current row for any current lineup not already the is_current one.
_INSERT_SQL = (
    "INSERT INTO {target} (\n"
    "    game_pk, home_away, official_date, has_full_lineup,\n"
    f"    {_insert_cols},\n"
    "    ingestion_ts, valid_from, valid_to, is_current, record_hash, computed_at\n"
    ")\n"
    "SELECT\n"
    "    cs.game_pk, cs.home_away, cs.official_date, cs.has_full_lineup,\n"
    f"    {_insert_sel},\n"
    "    cs.ingestion_ts, cs.ingestion_ts AS valid_from, NULL AS valid_to, TRUE AS is_current,\n"
    "    cs.record_hash, CURRENT_TIMESTAMP()::TIMESTAMP_NTZ\n"
    "FROM (\n" + _CURRENT_STATE + ") cs\n"
    "WHERE NOT EXISTS (\n"
    "    SELECT 1 FROM {target} t\n"
    "    WHERE t.game_pk     = cs.game_pk\n"
    "      AND t.home_away   = cs.home_away\n"
    "      AND t.record_hash = cs.record_hash\n"
    "      AND t.is_current  = TRUE\n"
    ")\n"
)

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
            "Only process games with official_date >= this date (limits the upsert to recent "
            "games; historical rows are never touched). Useful for incremental runs (e.g. 2-days-ago)."
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

    # Appended to the source WHERE (which already filters ingestion_ts IS NOT NULL).
    since_filter = (
        f"AND official_date >= '{args.since}'::date" if args.since else ""
    )

    close_sql = _CLOSE_SQL.format(target=target_table, since_filter=since_filter)
    insert_sql = _INSERT_SQL.format(target=target_table, since_filter=since_filter)

    if args.dry_run:
        print("-- ── Step 1: CLOSE changed is_current rows ──")
        print(close_sql)
        print("\n-- ── Step 2: INSERT new/changed current rows ──")
        print(insert_sql)
        return

    log.info("Target table : %s", target_table)
    log.info("Source       : %s (fresh S3 lineups)", _SOURCE)
    if args.since:
        log.info("Since filter : official_date >= %s", args.since)

    conn = get_snowflake_connection()
    try:
        cur = conn.cursor()

        cur.execute(_COUNT_SQL.format(target=target_table))
        before = cur.fetchone()[0]
        log.info("Rows before  : %d", before)

        # Order matters: close superseded rows BEFORE opening new ones.
        log.info("Step 1: closing changed is_current rows …")
        cur.execute(close_sql)
        closed = cur.rowcount
        log.info("  closed     : %d", closed)

        log.info("Step 2: inserting new/changed current rows …")
        cur.execute(insert_sql)
        inserted = cur.rowcount
        log.info("  inserted   : %d", inserted)

        cur.execute(_COUNT_SQL.format(target=target_table))
        after = cur.fetchone()[0]
        log.info("Rows after   : %d  (+%d)", after, after - before)

        cur.close()
    finally:
        conn.close()

    log.info("Done.")


if __name__ == "__main__":
    main()
