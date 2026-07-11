"""E11.20 — LOCAL delta-rs roundtrip (the laptop pre-prod gate for the Delta write path).

WHY THIS EXISTS (2026-07-10 box backfill crash): the Delta write path only executes on a
real run — CI mocks external IO and the guard tests are source-inspection — so a pure
API-shape bug (`conn.execute(...).arrow()` returning a RecordBatchReader with no
`.num_rows` on the box's newer DuckDB) sailed through every laptop gate and crashed the
one-time `--delta-full` backfill ON THE BOX, costing a deploy round-trip.

This test closes that class LOCALLY: delta-rs writes to a filesystem path exactly like it
writes to S3 (`delta_table_uri` + `storage_options` are monkeypatched to a tmp dir), so
the REAL `scripts/utils/delta_lake.py` functions — overwrite_partition (create +
partition-pinned replace + schema merge), table_exists, compact_and_vacuum — and the REAL
DuckDB→arrow fetch pattern run end-to-end on every fast-gate run, no network, no mocks.
Local FS is not "external IO" (the suite's mock rule targets Snowflake/S3/network).

If this file fails after a `deltalake` or `duckdb` version bump, the box would have
crashed the same way — fix BEFORE deploying.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

deltalake = pytest.importorskip("deltalake")  # project dep (pinned); skip only if env is stale

from scripts.utils import delta_lake  # noqa: E402


@pytest.fixture()
def local_delta(tmp_path, monkeypatch):
    """Point the REAL delta_lake helpers at a local tmp dir (delta-rs treats a plain path
    like any object store) and neutralize the S3 storage options."""
    monkeypatch.setattr(delta_lake, "delta_table_uri", lambda t: str(tmp_path / t))
    monkeypatch.setattr(delta_lake, "storage_options", lambda: {})
    return tmp_path


def _season_slice(conn, year: int, n: int = 40, extra_col: bool = False):
    """A tiny mart-shaped season slice via the SAME fetch the builder uses —
    fetch_arrow_table(), the call whose .arrow() sibling regressed on the box."""
    extra = ", 99.9 AS stuff_plus" if extra_col else ""
    tbl = conn.execute(
        f"SELECT {year} AS game_year, (1000 + i) AS game_pk, "
        f"       ('{year}-06-' || lpad(((i % 28) + 1)::varchar, 2, '0')) AS game_date, "
        f"       (i * 0.1) AS launch_speed{extra} "
        f"FROM range({n}) t(i)"
    ).fetch_arrow_table()
    # the exact attribute the box crash hit — a reader has no num_rows
    assert tbl.num_rows == n, "fetch_arrow_table must return a pyarrow.Table (box crash class)"
    return tbl


def test_backfill_then_daily_partition_swap_roundtrip(local_delta):
    import duckdb
    from deltalake import DeltaTable

    conn = duckdb.connect()
    table = "mart_pitch_roundtrip"

    # daily write against a MISSING table must refuse loudly (never a silent partial table)
    assert not delta_lake.table_exists(table)
    with pytest.raises(RuntimeError, match="--delta-full"):
        delta_lake.overwrite_partition(table, _season_slice(conn, 2026), 2026, create_ok=False)

    # --delta-full backfill: per-season loop, first write creates, later seasons replaceWhere
    for year in (2025, 2026):
        delta_lake.overwrite_partition(table, _season_slice(conn, year), year, create_ok=True)
    dt = DeltaTable(delta_lake.delta_table_uri(table))
    assert dt.to_pyarrow_table().num_rows == 80

    # daily incremental: replace ONLY the current-season partition with a different slice
    delta_lake.overwrite_partition(table, _season_slice(conn, 2026, n=55), 2026)
    got = DeltaTable(delta_lake.delta_table_uri(table)).to_pyarrow_table()
    by_year = {y: 0 for y in (2025, 2026)}
    for y in got.column("game_year").to_pylist():
        by_year[y] += 1
    assert by_year == {2025: 40, 2026: 55}, \
        "replaceWhere must swap ONLY the pinned season partition (2025 untouched)"

    # INC-19 additive cure: an ADDED column via schema_mode='merge' commits without rewrite
    delta_lake.overwrite_partition(table, _season_slice(conn, 2026, n=55, extra_col=True), 2026)
    got = DeltaTable(delta_lake.delta_table_uri(table)).to_pyarrow_table()
    assert "stuff_plus" in got.column_names
    conn.close()


def test_compact_and_vacuum_runs_and_clamps(local_delta, capsys):
    import duckdb

    conn = duckdb.connect()
    table = "mart_pitch_maint"
    for year in (2025, 2026):
        delta_lake.overwrite_partition(table, _season_slice(conn, year), year, create_ok=True)
    # a sub-floor retention must be CLAMPED (vacuum below 168h destroys time-travel)
    info = delta_lake.compact_and_vacuum(table, retention_hours=0)
    assert info["version"] >= 1 and info["files_after_compact"] >= 1
    assert "clamping" in capsys.readouterr().out
    # time-travel survives the clamped vacuum (the whole point of the floor)
    from deltalake import DeltaTable
    assert DeltaTable(delta_lake.delta_table_uri(table), version=0).to_pyarrow_table().num_rows == 40
    conn.close()


def test_unsigned_columns_rejected_loudly_and_signed_wrap_cures(local_delta):
    """The 2026-07-10 backfill crash #2: pitch_sk is UBIGINT (md5-upper64 surrogate key)
    and the Delta protocol has no unsigned types — delta-rs overflowed casting values
    above 2^63 with a cryptic error. The write helper must now fail LOUDLY pre-write,
    and the builder's _delta_signed_wrap must make the same frame writable with the
    uint64 values preserved EXACTLY (DECIMAL(20,0))."""
    import importlib.util

    import duckdb
    from deltalake import DeltaTable

    conn = duckdb.connect()
    # a mart-shaped slice with a REAL above-2^63 uint64 (the crashing value class) + a
    # hash()-derived UBIGINT column, exactly like pitch_sk
    raw_sql = (
        "SELECT 2026 AS game_year, (1000 + i) AS game_pk, "
        "       (17347671816382381815::ubigint + i::ubigint) AS pitch_sk, "
        "       hash(i) AS row_sk, (i * 0.1) AS launch_speed "
        "FROM range(10) t(i)"
    )
    raw_tbl = conn.execute(raw_sql).fetch_arrow_table()

    # (a) the shared write helper refuses unsigned frames with the cure in the message
    with pytest.raises(ValueError, match="_delta_signed_wrap"):
        delta_lake.overwrite_partition("mart_pitch_unsigned", raw_tbl, 2026, create_ok=True)

    # (b) the REAL builder wrap (DESCRIBE-based) pins UBIGINT→DECIMAL(20,0) → write OK
    spec = importlib.util.spec_from_file_location(
        "run_w1_lakehouse_under_test", REPO / "scripts" / "run_w1_lakehouse.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    wrapped_sql = builder._delta_signed_wrap(conn, raw_sql)
    assert wrapped_sql != raw_sql, "wrap must rewrite the unsigned columns"
    wrapped = conn.execute(wrapped_sql).fetch_arrow_table()
    delta_lake.overwrite_partition("mart_pitch_unsigned", wrapped, 2026, create_ok=True)
    got = DeltaTable(delta_lake.delta_table_uri("mart_pitch_unsigned")).to_pyarrow_table()
    vals = sorted(int(v) for v in got.column("pitch_sk").to_pylist())
    assert vals[0] == 17347671816382381815, "uint64 value must round-trip EXACTLY (no overflow/DOUBLE)"

    # (c) the exactness contract the decision rests on: DuckDB compares
    # UBIGINT ⋈ DECIMAL(20,0) exactly — adjacent above-2^63 values must NOT collide
    n = conn.execute(
        "with u as (select (9223372036854775808::ubigint) a "
        "           union all select (9223372036854775809::ubigint)), "
        "     d as (select (9223372036854775808::decimal(20,0)) b) "
        "select count(*) from u join d on u.a = d.b"
    ).fetchone()[0]
    assert n == 1, "UBIGINT vs DECIMAL(20,0) comparison went inexact — joins would corrupt"
    conn.close()


def test_duckdb_delta_scan_reads_the_local_table(local_delta):
    """The read half of the cutover (delta_scan views). The `delta` DuckDB extension may
    need a one-time network INSTALL — offline/CI environments skip rather than fail."""
    import duckdb

    conn = duckdb.connect()
    table = "mart_pitch_scan"
    delta_lake.overwrite_partition(table, _season_slice(conn, 2026), 2026, create_ok=True)
    try:
        conn.execute("INSTALL delta; LOAD delta")
    except Exception as e:  # noqa: BLE001 — extension fetch blocked offline
        pytest.skip(f"duckdb delta extension unavailable here: {e}")
    n = conn.execute(
        f"SELECT count(*) FROM delta_scan('{delta_lake.delta_table_uri(table)}')"
    ).fetchone()[0]
    assert n == 40
    conn.close()
