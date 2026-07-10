#!/usr/bin/env python3
"""
scripts/parity_check_delta_w1.py   (E11.20 — the mirror-window validation gate)

Compare each Delta-backed W1 pitch mart against its legacy lakehouse parquet, per season
partition: row count, distinct-game count, and an order-insensitive game_pk hash-sum. Run
during LAKEHOUSE_DELTA_W1=mirror (both stores freshly written by the same daily build)
BEFORE flipping cutover — and remember the standing landmine: parity is NECESSARY, not
sufficient; the cutover gate also needs the real per-row reads through the actual
consumers on the box (write_serving_store --s3 / the W2 build reading delta_scan).

Scope note (why this is enough here, unlike the SF-ext parity blindness): both sides are
read by the SAME DuckDB engine in this process, and both stores are produced from the SAME
deterministic row-local SQL — the failure modes this must catch are missing/duplicated
rows (a wrong partition predicate, a stale season), which counts + key-sums catch. There
is no Snowflake ext-table read in the Delta path by design (spike gotcha #5 resolution:
"don't have Snowflake read Delta at all").

Usage (box or laptop; needs AWS creds via the credential chain):
  uv run python scripts/parity_check_delta_w1.py              # all 7 W1 marts, all seasons
  uv run python scripts/parity_check_delta_w1.py --year 2026  # current season only

Exits 1 on any mismatch (wire into the runtime gate).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
try:
    from betting_ml.utils.delta_lakehouse import (
        DELTA_PARTITION_COL,
        DELTA_W1_TABLES,
        delta_table_uri,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(REPO_ROOT))
    from betting_ml.utils.delta_lakehouse import (
        DELTA_PARTITION_COL,
        DELTA_W1_TABLES,
        delta_table_uri,
    )

LAKEHOUSE = "s3://baseball-betting-ml-artifacts/baseball/lakehouse"

_STATS_SQL = (
    "SELECT {p} AS yr, count(*) AS n, count(DISTINCT game_pk) AS games, "
    "sum(hash(game_pk)) AS pk_hash FROM {src} {where} GROUP BY 1 ORDER BY 1"
)


def main() -> int:
    import duckdb

    year = None
    if "--year" in sys.argv:
        year = int(sys.argv[sys.argv.index("--year") + 1])

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    conn.execute("INSTALL delta; LOAD delta")
    conn.execute(
        "CREATE OR REPLACE SECRET baseball_s3 "
        "(TYPE S3, PROVIDER credential_chain, REGION 'us-east-2')"
    )

    where = f"WHERE {DELTA_PARTITION_COL} = {year}" if year else ""
    bad = 0
    for table in sorted(DELTA_W1_TABLES):
        pq = f"read_parquet('{LAKEHOUSE}/{table}/**/*.parquet', union_by_name=true)"
        dl = f"delta_scan('{delta_table_uri(table)}')"
        try:
            pq_rows = conn.execute(_STATS_SQL.format(p=DELTA_PARTITION_COL, src=pq, where=where)).fetchall()
            dl_rows = conn.execute(_STATS_SQL.format(p=DELTA_PARTITION_COL, src=dl, where=where)).fetchall()
        except Exception as e:  # noqa: BLE001 — a missing store is a parity FAIL, reported not raised
            print(f"  ✗ {table}: read failed — {e}", file=sys.stderr)
            bad += 1
            continue
        pq_by, dl_by = dict((r[0], r[1:]) for r in pq_rows), dict((r[0], r[1:]) for r in dl_rows)
        for yr in sorted(set(pq_by) | set(dl_by)):
            a, b = pq_by.get(yr), dl_by.get(yr)
            if a == b:
                print(f"  ✔ {table} {DELTA_PARTITION_COL}={yr}: {a[0]:,} rows, {a[1]:,} games — MATCH")
            else:
                print(f"  ✗ {table} {DELTA_PARTITION_COL}={yr}: parquet={a} delta={b} — MISMATCH",
                      file=sys.stderr)
                bad += 1
    conn.close()
    if bad:
        print(f"\nDelta W1 parity FAILED: {bad} mismatching table-seasons.", file=sys.stderr)
        return 1
    print("\nDelta W1 parity PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
