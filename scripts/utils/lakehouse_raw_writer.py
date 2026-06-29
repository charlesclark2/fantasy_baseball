"""
lakehouse_raw_writer.py  (E11.1-W3pre lakehouse decommission)
-------------------------------------------------------------
Shared S3-parquet equivalent of snowflake_loader.append_raw_rows().

THE CHOKEPOINT MOVE
  snowflake_loader.append_raw_rows(table_fqn, rows, conn) inserts raw rows into a
  Snowflake VARIANT table (raw_json wrapped in PARSE_JSON). This module provides the
  S3/lakehouse twin so the odds/staging WRITERS can stop writing Snowflake without each
  re-implementing parquet/S3 plumbing. A writer flips by calling append_raw_rows_lakehouse()
  with a `source` name and a mode (snowflake | s3 | both) instead of inserting directly.

WHY raw_json stays a JSON STRING (not a typed/nested parquet column)
  The dbt staging models flatten this JSON in their duckdb branch with DuckDB JSON
  functions (from_json / json_extract / json_extract_string — see W3pre stg_oddsapi_*,
  stg_statsapi_games duckdb branches). A VARCHAR JSON column is schema-stable across
  every snapshot and every source (live-writer rows and one-time Snowflake→S3 export
  rows produce byte-identical layout), so the flatten reads a single uniform parquet.
  This mirrors Snowflake's TO_JSON(raw_json) and avoids parquet schema drift.

S3 LAYOUT (date sub-partitions for incremental glob + the W2 hardened pre-flight)
  s3://baseball-betting-ml-artifacts/baseball/lakehouse_raw/<source>/dt=YYYY-MM-DD/part-<uuid>.parquet
  Append-only: each call writes a NEW part file (unique uuid), exactly like Snowflake's
  append model — snapshot multiplicity is collapsed downstream by the same row_number()/
  qualify dedup the Snowflake staging already uses. The runner globs **/*.parquet.
  mode='overwrite_partition' (for idempotent re-exports) deletes the dt= partition first
  so a re-run can't leave a stale double-counting part (the W2 re-ingest dupe class).

PUBLIC API
  raw_lakehouse_loc(source)                         -> s3 prefix for a source
  rows_to_arrow_table(rows, json_cols)              -> pyarrow.Table (pure; unit-tested)
  write_raw_rows_s3(source, rows, mode, ...)        -> int rows written
  append_raw_rows_lakehouse(table_fqn, source, rows, conn=None, mode=None) -> dispatcher

Auth: AWS via boto3 default credential chain (same as ingest_statcast_to_s3.py). Snowflake
leg (mode in {snowflake, both}) reuses snowflake_loader.append_raw_rows.
"""

from __future__ import annotations

import io
import json
import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq

log = logging.getLogger(__name__)

# ── S3 location (mirrors lakehouse_loc() macro; RAW tier is a sibling of lakehouse/) ──
BUCKET = "baseball-betting-ml-artifacts"
RAW_PREFIX = "baseball/lakehouse_raw"
REGION = "us-east-2"

# Columns serialised to a JSON string (superset of snowflake_loader._JSON_COLS so the
# Snowflake and S3 legs accept identical row dicts). 'json_field' is monthly_schedule's
# VARIANT column. A value that is ALREADY a JSON string passes through unchanged (the
# Snowflake→S3 export emits TO_JSON(...) strings); only dict/list values are dumped.
_JSON_COLS = frozenset({"raw_json", "request_params", "json_field"})

# Valid raw sources. Keep in sync with the export + runner + DDL gen.
#   W3pre scope: mlb_odds_raw, mlb_events_raw, derivative_odds_raw, monthly_schedule,
#                odds_snapshots_historical.
#   W6 adds:     venues_raw (Group-C venues flatten — stg_statsapi_venues).
RAW_SOURCES = frozenset({
    "mlb_odds_raw",
    "mlb_events_raw",
    "derivative_odds_raw",
    "monthly_schedule",
    "odds_snapshots_historical",
    "venues_raw",
})

_VALID_MODES = frozenset({"snowflake", "s3", "both"})


def raw_lakehouse_loc(source: str) -> str:
    """S3 prefix (directory, trailing slash) for a raw source's parquet."""
    return f"s3://{BUCKET}/{RAW_PREFIX}/{source}/"


# Sentinel dt= partition for rows whose ingestion_ts is an EXPLICIT NULL (see _partition_date).
NULL_TS_PARTITION = "__nullts__"


def _partition_date(row: dict) -> str:
    """dt= partition key for a row.

    - real ingestion_ts (datetime / ISO str)            -> its date
    - EXPLICIT NULL ingestion_ts (key present, value None) -> the stable NULL_TS_PARTITION
      sentinel. These are historical-backfill rows (e.g. monthly_schedule's pre-2026 schedule)
      that legitimately have no ingestion time in Snowflake; a real date would be a lie and
      'today' would break idempotent re-export. The sentinel keeps them in one stable partition.
    - ingestion_ts key ABSENT (live writers relying on Snowflake's DEFAULT CURRENT_TIMESTAMP)
      -> today (UTC), matching the now()-stamp rows_to_arrow_table applies to the same rows.
    """
    ts = row.get("ingestion_ts")
    if isinstance(ts, datetime):
        return ts.date().isoformat()
    if isinstance(ts, str) and len(ts) >= 10:
        return ts[:10]
    if "ingestion_ts" in row and ts is None:
        return NULL_TS_PARTITION
    return datetime.now(timezone.utc).date().isoformat()


def rows_to_arrow_table(rows: list[dict], json_cols: frozenset = _JSON_COLS) -> pa.Table:
    """Build a pyarrow.Table from raw row dicts (PURE — no IO; unit-tested offline).

    JSON columns are serialised to a JSON string. ingestion_ts is stamped (UTC now) when
    absent so the S3 column matches Snowflake's DDL DEFAULT CURRENT_TIMESTAMP. Column order
    is taken from the first row; every row is normalised to that column set.
    """
    if not rows:
        raise ValueError("rows_to_arrow_table called with no rows")

    columns = list(rows[0].keys())
    if "ingestion_ts" not in columns:
        columns = ["ingestion_ts"] + columns

    now_iso = datetime.now(timezone.utc).isoformat()
    data: dict[str, list] = {c: [] for c in columns}
    for row in rows:
        for col in columns:
            if col == "ingestion_ts":
                # Preserve an EXPLICIT NULL (key present, value None): historical-backfill rows
                # whose Snowflake ingestion_ts is NULL must stay NULL here, so the duckdb
                # branch's ingestion_ts::timestamp equals Snowflake's AND the staging qualify's
                # 'order by ingestion_ts desc nulls last' picks the same row. Stamping now()
                # would both mismatch the value and make these rows win the dedup (data loss).
                # Key ABSENT -> stamp now() (matches Snowflake DEFAULT CURRENT_TIMESTAMP).
                if "ingestion_ts" in row and row["ingestion_ts"] is None:
                    data[col].append(None)
                else:
                    v = row.get("ingestion_ts") or now_iso
                    data[col].append(v.isoformat() if isinstance(v, datetime) else str(v))
            elif col in json_cols:
                v = row.get(col)
                data[col].append(json.dumps(v) if not isinstance(v, str) and v is not None else v)
            else:
                data[col].append(row.get(col))
    # Keep scalars native so numeric metadata (x_requests_used) stays numeric; pyarrow infers
    # per-column type — EXCEPT ingestion_ts: an all-NULL batch (a NULL_TS_PARTITION historical
    # partition) would infer arrow 'null' type and write a parquet that drifts from the utf8
    # ingestion_ts of every dated partition, breaking the union_by_name glob. Pin it to utf8.
    table = pa.Table.from_pydict(data)
    i = table.schema.get_field_index("ingestion_ts")
    if i != -1 and table.schema.field(i).type != pa.string():
        table = table.set_column(
            i, pa.field("ingestion_ts", pa.string()), table.column(i).cast(pa.string())
        )
    return table


def _make_s3_client():
    import boto3
    return boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", REGION))


def _delete_partition(s3, source: str, dt: str) -> None:
    prefix = f"{RAW_PREFIX}/{source}/dt={dt}/"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            s3.delete_object(Bucket=BUCKET, Key=obj["Key"])


def list_partition_dts(s3, source: str) -> list[str]:
    """Return the dt= partition keys present for a source (e.g. '2026-06-28', '__nullts__')."""
    prefix = f"{RAW_PREFIX}/{source}/dt="
    dts: set[str] = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            tail = obj["Key"].split(f"{source}/dt=", 1)
            if len(tail) == 2:
                dts.add(tail[1].split("/", 1)[0])
    return sorted(dts)


def prune_partitions(source: str, keep_dts, *, s3_client=None) -> list[str]:
    """Delete every dt= partition for `source` NOT in keep_dts. The NULL_TS_PARTITION sentinel is
    ALWAYS kept (historical-backfill rows). Returns the sorted list of deleted dt= keys.

    E11.1-W6 / INC-20 monthly_schedule retention: the daily export re-materialises the full
    accumulating month-snapshot history, but the stg_statsapi_lineups/games flatten dedups to the
    latest ingestion per game_pk — so only the latest-ingestion partition per calendar month
    affects the output. Pruning the rest is value-identical and stops the unbounded growth that
    OOM'd the W6 DuckDB flatten (~750k pre-dedup fat-JSON game-rows, unspillable)."""
    if source not in RAW_SOURCES:
        raise ValueError(f"Unknown raw source '{source}'. Valid: {sorted(RAW_SOURCES)}")
    s3 = s3_client or _make_s3_client()
    keep = set(keep_dts) | {NULL_TS_PARTITION}
    deleted: list[str] = []
    for dt in list_partition_dts(s3, source):
        if dt not in keep:
            _delete_partition(s3, source, dt)
            deleted.append(dt)
    return sorted(deleted)


def write_raw_rows_s3(
    source: str,
    rows: list[dict],
    *,
    mode: str = "append",
    s3_client=None,
) -> int:
    """Write raw rows to S3 parquet under the source's lakehouse_raw prefix.

    mode='append'              : one new part-<uuid>.parquet per dt= partition (live writers).
    mode='overwrite_partition' : delete each touched dt= partition first (idempotent re-export).
    Returns the number of rows written.
    """
    if source not in RAW_SOURCES:
        raise ValueError(f"Unknown raw source '{source}'. Valid: {sorted(RAW_SOURCES)}")
    if not rows:
        return 0

    s3 = s3_client or _make_s3_client()

    # Group rows by dt= partition so each file lands in the right partition.
    by_dt: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_dt[_partition_date(row)].append(row)

    written = 0
    for dt, dt_rows in by_dt.items():
        if mode == "overwrite_partition":
            _delete_partition(s3, source, dt)
        table = rows_to_arrow_table(dt_rows)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)
        key = f"{RAW_PREFIX}/{source}/dt={dt}/part-{uuid.uuid4().hex[:12]}.parquet"
        s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
        log.info("  wrote %d rows → s3://%s/%s", len(dt_rows), BUCKET, key)
        written += len(dt_rows)
    return written


def append_raw_rows_lakehouse(
    table_fqn: str,
    source: str,
    rows: list[dict],
    conn=None,
    mode: str | None = None,
) -> int:
    """Dispatcher the odds/staging writers call to flip Snowflake → S3 via the shared util.

    mode resolution: explicit arg → env LAKEHOUSE_RAW_WRITE_MODE → default 'snowflake'.
    The default is NON-BREAKING (current behaviour) so importing this module changes
    nothing until a writer/operator opts in. Rollout: 'both' (dual-write, validate parity)
    → 's3' (Snowflake leg retired). 'snowflake'/'both' require a live `conn`.

    Returns rows written on the PRIMARY leg (s3 for s3/both, snowflake for snowflake).
    """
    mode = (mode or os.environ.get("LAKEHOUSE_RAW_WRITE_MODE", "snowflake")).lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"LAKEHOUSE_RAW_WRITE_MODE='{mode}' invalid; expected one of {sorted(_VALID_MODES)}")
    if not rows:
        return 0

    n_sf = n_s3 = 0
    if mode in ("snowflake", "both"):
        if conn is None:
            raise ValueError(f"mode='{mode}' needs a Snowflake conn for {table_fqn}")
        try:  # 'utils.' path under pytest (pythonpath=scripts); bare under script runtime
            from utils.snowflake_loader import append_raw_rows
        except ImportError:
            from snowflake_loader import append_raw_rows
        n_sf = append_raw_rows(table_fqn, rows, conn)
    if mode in ("s3", "both"):
        n_s3 = write_raw_rows_s3(source, rows, mode="append")

    return n_s3 if mode in ("s3", "both") else n_sf
