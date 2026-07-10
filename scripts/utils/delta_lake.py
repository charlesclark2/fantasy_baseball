#!/usr/bin/env python3
"""
scripts/utils/delta_lake.py   (E11.20)

The shared delta-rs WRITE/MAINTAIN layer for the Delta lakehouse — the write-side twin of
scripts/utils/lakehouse_read.py. Every Delta write in the repo goes through here so the
S3-auth, retention, and partition-predicate discipline live in ONE place.

Spike-anchored design (docs/e11_20a_delta_polars_spike.md — do NOT re-derive):
  • WRITE path = delta-rs (`deltalake`). DuckDB's `delta` extension is READ-ONLY
    (`COPY … (FORMAT delta)` does not exist — the spike's roadmap correction #1).
  • Pinned `deltalake==1.6.x` — 1.x had API churn (`files()`→`file_uris()`,
    `schema().to_pyarrow()`→`.to_arrow()`); this module is written against 1.6.
  • Partition-aware predicates only: an overwrite/MERGE whose predicate does not pin
    the partition column scans the whole table and forfeits the O(partition) win.
  • vacuum() below 168h physically deletes files older versions point to and BREAKS
    time-travel — `compact_and_vacuum` clamps to DELTA_MIN_RETENTION_HOURS (guarded by
    betting_ml/tests/test_delta_lakehouse_guard.py).

🪪 S3 AUTH (the AKID landmine in delta-rs dress — W7b-1 / CLAUDE.md): delta-rs takes
`storage_options`, NOT boto3, but the same rule applies — NEVER pass
`os.environ.get("AWS_ACCESS_KEY_ID")` through when it is unset (None/empty kills the
credential chain). `storage_options()` passes explicit keys ONLY when both are present
(laptop/dev); otherwise it passes region alone so delta-rs' object-store resolves the
EC2 instance role (IMDS), exactly like lakehouse_raw_writer.make_s3_client().

`deltalake` is imported LAZILY inside each function so importing this module never
requires the dep — callers are all gated behind delta_w1_mode() != "off", and a box
running a pre-Delta image must not crash at import time on the un-gated path.
"""
from __future__ import annotations

import os

# The pure registry — the scripts/utils SIBLING home (byte-identical to
# betting_ml/utils/delta_lakehouse.py, guard-tested): the lean capture images COPY
# scripts/utils/ wholesale, so nothing in this dir may carry a betting_ml import node
# (test_lean_capture_images_selfcontained / INC-29 class). Import pattern mirrors
# lakehouse_raw_writer's dual-context resolution (repo-root vs lean-image ./utils/).
try:
    from scripts.utils.delta_lakehouse import (
        DELTA_MIN_RETENTION_HOURS,
        DELTA_PARTITION_COL,
        delta_table_uri,
    )
except ImportError:  # pragma: no cover — lean image layout (COPY scripts/utils/ → ./utils/)
    from utils.delta_lakehouse import (
        DELTA_MIN_RETENTION_HOURS,
        DELTA_PARTITION_COL,
        delta_table_uri,
    )

DEFAULT_REGION = "us-east-2"  # the artifacts bucket's region (DuckDB + delta-rs both need it explicit)


def storage_options() -> dict[str, str]:
    """delta-rs S3 storage_options that resolve the EC2 instance role when no explicit
    keys are present. Explicit keys are forwarded ONLY when BOTH id+secret are set and
    non-empty — a None/empty AKID must never reach the option dict (the
    AuthorizationHeaderMalformed class)."""
    # Region is PINNED to the artifacts bucket's region — never inherited from
    # AWS_DEFAULT_REGION (a laptop/serving env pointing at us-east-1 would misroute the
    # bucket; the INC-31 qualified_bet_notifier lesson: pin region per RESOURCE).
    opts: dict[str, str] = {"AWS_REGION": DEFAULT_REGION}
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if key and secret:
        opts["AWS_ACCESS_KEY_ID"] = key
        opts["AWS_SECRET_ACCESS_KEY"] = secret
        token = os.environ.get("AWS_SESSION_TOKEN")
        if token:
            opts["AWS_SESSION_TOKEN"] = token
    return opts


def table_exists(table: str) -> bool:
    """True if the Delta table (its _delta_log) exists at the registry URI."""
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError

    try:
        DeltaTable(delta_table_uri(table), storage_options=storage_options())
        return True
    except TableNotFoundError:
        return False


def overwrite_partition(table: str, data, year: int, *, create_ok: bool = False) -> None:
    """Atomically replace ONE season partition of a Delta table with `data`
    (a pyarrow Table whose rows are all game_year == `year`).

    This is the phase-1 daily-incremental mechanism: a partition-pinned replaceWhere
    (`game_year = <year>`) — O(current season), never O(history) — chosen over row-level
    MERGE because the W1 pitch marts are pure row-local projections with no single-column
    PK; a deterministic partition rebuild needs no PK assumptions and is idempotent
    (re-running a day is a no-op-equivalent rewrite). `schema_mode="merge"` makes an
    ADDITIVE upstream column change a metadata commit instead of an INC-19-class
    DROP+rebuild (a genuine stored-type flip still needs a deliberate migration —
    the spike is explicit that Delta does not make those free).

    A MISSING table is a loud error unless `create_ok` (the --delta-full backfill):
    auto-creating a table holding only the current season on the daily path would be a
    silent partial table — the INC-25 "consumer parquet lags the stores" class.
    """
    from deltalake import write_deltalake

    uri = delta_table_uri(table)
    if not table_exists(table):
        if not create_ok:
            raise RuntimeError(
                f"Delta table {uri} does not exist — run the one-time backfill first "
                f"(run_w1_lakehouse.py --w1-only --delta-full) so the daily "
                f"season-partition write can never silently serve a partial table."
            )
        write_deltalake(
            uri, data,
            mode="overwrite",
            partition_by=[DELTA_PARTITION_COL],
            storage_options=storage_options(),
        )
        return
    write_deltalake(
        uri, data,
        mode="overwrite",
        predicate=f"{DELTA_PARTITION_COL} = {int(year)}",
        schema_mode="merge",
        storage_options=storage_options(),
    )


def merge_upsert(table: str, data, predicate: str) -> dict:
    """Row-level MERGE upsert (when_matched_update_all / when_not_matched_insert_all) —
    the spike §7 INCREMENTAL pattern, provided for LATER phases where a table has a real
    PK and a narrower-than-partition daily delta (e.g. the W6 odds hot set). ⚠️ The
    predicate MUST pin the partition column (`t.game_year = <year> AND t.<pk> = s.<pk>`)
    or the MERGE scans all history (spike gotcha #8). Unused in phase 1 by design."""
    if DELTA_PARTITION_COL not in predicate:
        raise ValueError(
            f"merge_upsert predicate must pin the partition column "
            f"'{DELTA_PARTITION_COL}' to stay O(partition); got: {predicate!r}"
        )
    from deltalake import DeltaTable

    dt = DeltaTable(delta_table_uri(table), storage_options=storage_options())
    return (
        dt.merge(source=data, predicate=predicate, source_alias="s", target_alias="t")
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )


def compact_and_vacuum(table: str, retention_hours: int = DELTA_MIN_RETENTION_HOURS) -> dict:
    """The REQUIRED companion op to the daily overwrite/MERGE pattern (spike gotcha #7:
    every incremental write adds small files; without compaction read planning degrades).
    Clamps retention to DELTA_MIN_RETENTION_HOURS — vacuuming younger versions physically
    deletes their files and destroys time-travel (spike gotcha #3), and time-travel is a
    load-bearing win here (leakage-audit / point-in-time). Returns per-table metrics."""
    from deltalake import DeltaTable

    if retention_hours < DELTA_MIN_RETENTION_HOURS:
        print(
            f"WARNING: [delta-maintenance] retention_hours={retention_hours} below the "
            f"{DELTA_MIN_RETENTION_HOURS}h floor — clamping (vacuum below the floor "
            f"destroys time-travel; the floor is the INC-20-cure knob, not a suggestion)."
        )
        retention_hours = DELTA_MIN_RETENTION_HOURS
    dt = DeltaTable(delta_table_uri(table), storage_options=storage_options())
    compact_metrics = dt.optimize.compact()
    removed = dt.vacuum(
        retention_hours=retention_hours,
        enforce_retention_duration=True,
        dry_run=False,
    )
    return {
        "table": table,
        "version": dt.version(),
        "files_after_compact": len(dt.file_uris()),  # 1.6 API: file_uris(), not files()
        "compact": compact_metrics,
        "vacuumed_files": len(removed),
    }


def table_info(table: str) -> dict:
    """Version + file-count snapshot (observability for the maintenance op logs)."""
    from deltalake import DeltaTable

    dt = DeltaTable(delta_table_uri(table), storage_options=storage_options())
    return {"table": table, "version": dt.version(), "files": len(dt.file_uris())}
