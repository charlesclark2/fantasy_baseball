"""INC-23 guard — `run_w1_lakehouse._string_timestamp_wrap` must HALT (raise) on a DESCRIBE
failure, and must NEVER fall back to an unwrapped COPY.

WHY THIS EXISTS
---------------
The W8a binary-timestamp cure stringifies every TIMESTAMP output column to ISO VARCHAR *before*
the parquet COPY, because Snowflake's external table misreads a BINARY parquet timestamp PER ROW
(a 2026 micros value materializes as year ~56,000,000 → connector EOVERFLOW = the W8a 24h serving
outage). Parity (DuckDB-over-parquet) is blind to it because it never reads through the Snowflake
ext table.

The original helper, when its type-probing DESCRIBE failed, printed a WARNING and *returned the
unwrapped SQL* so "the COPY surfaces the real error". INC-23 (2026-06-30) showed why that is
dangerous: `mart_bookmaker_disagreement` applied `year(b.game_date)` to a column an upstream wrap
had already stringified to VARCHAR, the DESCRIBE failed, and the helper's silent fallback is the
exact pattern that could re-emit binary timestamps for any model whose DESCRIBE fails but whose
COPY could still write. The fix: a DESCRIBE failure now RAISES. These tests pin that invariant so
the warn-and-proceed-unwrapped pattern can't come back.

All in-memory DuckDB; no external IO. Fast gate (<5s, no `slow` marker).
"""
import os
import tempfile

import duckdb
import pytest

from run_w1_lakehouse import _string_timestamp_wrap


def _conn():
    return duckdb.connect()


def test_describe_failure_raises_not_unwrapped():
    """A model SQL the DuckDB binder rejects — `year()` on a VARCHAR date column, the exact INC-23
    trigger — must RAISE (HALT), never return the unwrapped SQL for a COPY to attempt."""
    con = _conn()
    # game_date VARCHAR (as a stringified-timestamp parquet column reads back) → year(VARCHAR) fails to bind.
    bad_sql = "SELECT * FROM (SELECT '2026-06-30' AS game_date) WHERE year(game_date) >= 2026"
    with pytest.raises(RuntimeError) as ei:
        _string_timestamp_wrap(con, bad_sql)
    msg = str(ei.value)
    # The raise must be LOUD + actionable: it names the binary-ts risk and the ::date cure.
    assert "REFUSING to COPY unwrapped" in msg
    assert "::date" in msg
    # The old dangerous behaviour ("COPY proceeds unwrapped") must be gone.
    assert "proceeds unwrapped" not in msg


def test_timestamp_column_is_stringified_to_varchar():
    """When DESCRIBE succeeds and a TIMESTAMP output exists, the wrap REPLACEs it with ::varchar,
    and a parquet written from the wrapped SQL stores the column as VARCHAR — never a binary ts."""
    con = _conn()
    sql = "SELECT 1 AS game_pk, TIMESTAMP '2026-06-30 12:34:56' AS odds_ingestion_ts"
    wrapped = _string_timestamp_wrap(con, sql)
    assert '"odds_ingestion_ts"::varchar' in wrapped  # REPLACE applied to the ts column

    # Stronger end-to-end guard: materialize to a local parquet and confirm the STORED type is
    # VARCHAR (the only thing that actually protects the Snowflake ext-table read).
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.parquet")
        con.execute(f"COPY (\n{wrapped}\n) TO '{path}' (FORMAT PARQUET)")
        types = {
            r[0]: str(r[1]).upper()
            for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
        }
    assert types["odds_ingestion_ts"] == "VARCHAR"
    assert not types["odds_ingestion_ts"].startswith("TIMESTAMP")


def test_no_timestamp_columns_is_noop():
    """No TIMESTAMP output (DATE + numerics) → return the SQL unchanged (nothing to stringify;
    DATE is read correctly by Snowflake as INT32 days, so it is intentionally left alone)."""
    con = _conn()
    sql = "SELECT 1 AS game_pk, CAST('2026-06-30' AS DATE) AS game_date, 2.5 AS x"
    assert _string_timestamp_wrap(con, sql) == sql
