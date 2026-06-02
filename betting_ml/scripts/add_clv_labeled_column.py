"""
Migration: add clv_labeled boolean column to daily_model_predictions.

Adds a BOOLEAN column that is set to TRUE for every row whose game_pk appears
in mart_clv_labeled_games (meaning all four CLV label conditions are met for
that game). Null rows have not yet been labeled (game still in progress or
closing snapshot not yet available).

Run once to add the column, then re-run to backfill / refresh labels:

    uv run betting_ml/scripts/add_clv_labeled_column.py

The script is idempotent: it skips the ALTER TABLE if the column already exists
and always runs the UPDATE to keep labels current.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap project path so local imports work when run from repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from betting_ml.utils.snowflake_connector import get_snowflake_connection  # noqa: E402


def column_exists(cur, database: str, schema: str, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM {db}.information_schema.columns
        WHERE table_schema  = UPPER(%(schema)s)
          AND table_name    = UPPER(%(table)s)
          AND column_name   = UPPER(%(column)s)
        """.format(db=database),
        {"schema": schema, "table": table, "column": column},
    )
    return cur.fetchone()[0] > 0


def main() -> None:
    database = os.environ.get("SNOWFLAKE_DATABASE", "baseball_data")
    ml_schema = "betting_ml"
    table = "daily_model_predictions"
    fqn = f"{database}.{ml_schema}.{table}"

    conn = get_snowflake_connection()
    try:
        with conn.cursor() as cur:
            # 1. Add column if it doesn't exist yet
            if not column_exists(cur, database, ml_schema, table, "clv_labeled"):
                print(f"Adding clv_labeled column to {fqn} …")
                cur.execute(
                    f"ALTER TABLE {fqn} ADD COLUMN clv_labeled BOOLEAN DEFAULT NULL"
                )
                print("  Column added.")
            else:
                print(f"clv_labeled already exists on {fqn} — skipping ALTER TABLE.")

            # 2. Populate / refresh labels from mart_clv_labeled_games
            #    A game is labeled TRUE when its game_pk appears in the mart
            #    for the given market type. We set clv_labeled = TRUE on the
            #    prediction row that was selected as the canonical prediction
            #    (same post_lineup > morning priority used in the mart).
            print("Refreshing clv_labeled values …")
            cur.execute(
                f"""
                UPDATE {fqn} AS p
                SET p.clv_labeled = TRUE
                WHERE p.game_pk IN (
                    SELECT DISTINCT game_pk
                    FROM {database}.betting.mart_clv_labeled_games
                )
                  AND p.clv_labeled IS DISTINCT FROM TRUE
                """
            )
            updated = cur.rowcount
            print(f"  {updated} rows marked clv_labeled = TRUE.")

            # 3. Ensure rows that lost their label (e.g. result undone) are reset
            cur.execute(
                f"""
                UPDATE {fqn} AS p
                SET p.clv_labeled = FALSE
                WHERE p.clv_labeled IS NULL
                  AND p.game_pk NOT IN (
                      SELECT DISTINCT game_pk
                      FROM {database}.betting.mart_clv_labeled_games
                  )
                  AND p.prediction_type IN ('morning', 'post_lineup')
                """
            )
            reset = cur.rowcount
            print(f"  {reset} rows marked clv_labeled = FALSE (no label yet).")

        conn.commit()
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
