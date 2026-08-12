#!/usr/bin/env python
"""Compact a `lakehouse_raw/<source>/dt=<date>/` partition's many small parquet files into one.

WHY (INC-42, 2026-08-11)
------------------------
`lakehouse_raw/mlb_odds_raw` is an APPEND-ONLY store with no compaction and no retention: the
30-min host-cron odds capture writes ONE `part-<uuid>.parquet` per fire, so the glob every reader
binds grows by **48 files/day, forever**. Measured 2026-08-12: 97 partitions / **1,859 files** /
129.5 MB, of which 1,800 files sit in the 38 partitions written since the 2026-07-05 S3-native
flip (`dt=2026-07-05` holds exactly 1 file — the flip date).

DuckDB's `read_parquet(..., union_by_name=true)` binds by LISTING the glob and OPENING every
file's footer, so bind cost is ~linear in the FILE COUNT, not the byte count. Measured on an idle
laptop: **21.8 s to bind `mlb_odds_raw`** vs 0.4–0.6 s for the small w3pre sources. That bind is
the standing lead for INC-42 (both `RequestTimeTooSkewed` failures were on this source, both at
`:00` — the peak-contention minute on a 2-vCPU box), and it is a real unbounded-growth defect on
its own merits regardless of whether it turns out to be INC-42's cause.

Compaction is **row-preserving**: every row of every file is kept. ⛔ This is NOT retention —
nothing is dropped. The odds snapshot TRAJECTORY is the signal (`mart_odds_line_movement`,
`mart_bookmaker_disagreement`), so deleting old snapshots would destroy data the program uses.
1,859 files → ~97, with byte-for-byte the same rows.

WHY THE WRITE ORDER IS "PROMOTE, THEN DELETE" (measured, not assumed)
--------------------------------------------------------------------
Mutating a glob-backed store concurrently with readers admits exactly two orders, and each has a
transient window:

  * **promote-then-delete** → a window where the compacted file AND the originals are both
    visible ⇒ a reader binding in that window sees the partition's rows TWICE.
  * **delete-then-promote** → a window where NEITHER is visible ⇒ a reader binding in that window
    silently sees a partition's rows ZERO times.

Which is safe is a property of the READERS, so it was measured rather than reasoned about. All
three readers of this glob are DUPLICATE-IDEMPOTENT and none is missing-row-idempotent:

  1. `dbt/models/staging/stg_oddsapi_odds.sql` — `qualify row_number() over (partition by
     load_id, event_id, bookmaker_key, market_key, outcome_name order by ingestion_ts) = 1`
     collapses a duplicated file to one row per key.
  2. `dbt/models/mart/mart_bookmaker_disagreement.sql` (historical path) — `group by` +
     `qualify row_number() ... = 1`; it also filters `year(commence_ts) between 2021 and 2025`,
     so the 2026 partitions this script touches are excluded from its output entirely.
  3. `pipeline/sensors/odds_freshness_alert_sensor.py` — `MAX(ingestion_ts)` and an
     `ORDER BY ingestion_ts DESC LIMIT 1`; both are duplicate-invariant, and it reads the NEWEST
     partition, which `--min-age-days` never touches.

⇒ the dup window is a NO-OP for every consumer; the empty window would silently drop a day of
odds from a mart. Hence promote-then-delete. That argument is PER-SOURCE — a source whose readers
do not dedup needs the opposite order or no compaction at all — so `COMPACTABLE_SOURCES` below is
an allowlist, and an unvetted source is REFUSED rather than compacted with a borrowed rationale.
`scripts/tests/test_compact_lakehouse_raw.py` pins both the allowlist and the reader claim (it
greps the real reader files for their dedup, so removing a `qualify` fails the build).

CRASH SEMANTICS
---------------
A crash between the promote and the delete leaves `part-compact-*` beside the originals — i.e.
duplicate rows, which every reader above tolerates. That state is DECIDABLE and is repaired
automatically on the next run: if the compacted file's row count equals the sum of the other
files' rows, the originals are deleted; if it does not, the run REFUSES loudly rather than
guessing. ⛔ The reverse order has no such repair — a crash there destroys the only copy.

SAFETY INVARIANTS (all enforced, all tested)
--------------------------------------------
  * the compacted object is written, RE-READ FROM S3, and verified (row count, column set,
    per-column non-null counts) BEFORE a single original is deleted — a verification failure
    deletes the new object and raises, so a bad compaction can never cost data (the E11.24
    target-6 rule: LOAD, then delete; a destructive step that runs before its source is proven
    readable just relocates the outage);
  * `--min-age-days` (default 2, floor 1) keeps the LIVE partition — the one the 30-min capture
    is appending to — permanently out of scope, so this never races the writer;
  * DRY-RUN IS THE DEFAULT; `--apply` is required to mutate. It writes PRODUCTION S3.

USAGE (LAPTOP or BOX; writes PRODUCTION S3 either way)
-----------------------------------------------------
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/compact_lakehouse_raw.py \
        --source mlb_odds_raw                      # dry-run: plan only
    AWS_DEFAULT_REGION=us-east-2 uv run python scripts/compact_lakehouse_raw.py \
        --source mlb_odds_raw --apply              # mutate

Exit codes: 0 = clean (including a clean dry-run), 1 = a partition refused or failed
verification. Emits `[METRIC] ...` lines for a future monitor to key on.
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pyarrow as pa
import pyarrow.parquet as pq

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root
sys.path.insert(0, _HERE)                    # scripts/ (the `from utils...` convention)

try:  # `python scripts/compact_lakehouse_raw.py` and the box's PYTHONPATH=/app
    from scripts.utils.lakehouse_raw_writer import (  # noqa: E402
        BUCKET, NULL_TS_PARTITION, RAW_PREFIX, RAW_SOURCES, list_partition_dts, make_s3_client,
    )
except ModuleNotFoundError:  # pytest puts scripts/ (not the repo root) on sys.path
    from utils.lakehouse_raw_writer import (  # noqa: E402
        BUCKET, NULL_TS_PARTITION, RAW_PREFIX, RAW_SOURCES, list_partition_dts, make_s3_client,
    )

# ── The allowlist. A source belongs here ONLY once its readers have been enumerated and each
# proven duplicate-idempotent (see the module docstring). The value is that rationale, kept
# beside the entry so a future addition has to state one. ⛔ Never add a source because "it looks
# like the same shape" — the write order's safety is a property of the readers, not the writer.
COMPACTABLE_SOURCES: dict[str, str] = {
    "mlb_odds_raw": (
        "All three readers dedup: stg_oddsapi_odds qualifies row_number()=1 per "
        "(load_id, event_id, bookmaker_key, market_key, outcome_name); "
        "mart_bookmaker_disagreement group-bys + qualifies (and its historical path filters to "
        "commence years 2021-2025, excluding every partition this touches); "
        "odds_freshness_alert_sensor reads MAX(ingestion_ts) / ORDER BY ... LIMIT 1. "
        "So the promote-then-delete duplicate window is a no-op for every consumer."
    ),
}

COMPACT_PREFIX = "part-compact-"
_DEFAULT_MIN_AGE_DAYS = 2   # the live partition (today, UTC) plus one full day of slack
_MIN_AGE_DAYS_FLOOR = 1     # ⛔ 0 would race the 30-min capture writing dt=<today>
_LARGE_PARTITION_MB = 512   # advisory only — log if a single output file gets unusually big


class CompactionRefused(RuntimeError):
    """A partition is in a state this script will not guess about. Never auto-resolved."""


# ────────────────────────────────────────────────────────────────────────────────
# S3 helpers (thin; every one takes an injected client so the tests run offline)
# ────────────────────────────────────────────────────────────────────────────────
def _partition_prefix(source: str, dt: str) -> str:
    return f"{RAW_PREFIX}/{source}/dt={dt}/"


def list_partition_files(s3, source: str, dt: str) -> list[str]:
    """Every `.parquet` key directly under a dt= partition, sorted. Non-parquet keys are ignored."""
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=_partition_prefix(source, dt)):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                keys.append(obj["Key"])
    return sorted(keys)


def _is_compacted(key: str) -> bool:
    return key.rsplit("/", 1)[-1].startswith(COMPACT_PREFIX)


def _read_table(s3, key: str) -> pa.Table:
    body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    return pq.read_table(io.BytesIO(body))


def _delete_keys(s3, keys: list[str]) -> None:
    """Batch-delete (S3 caps delete_objects at 1000 keys/call), so the window stays sub-second."""
    for i in range(0, len(keys), 1000):
        s3.delete_objects(
            Bucket=BUCKET,
            Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True},
        )


# ────────────────────────────────────────────────────────────────────────────────
# Planning
# ────────────────────────────────────────────────────────────────────────────────
def is_date_partition(dt: str) -> bool:
    """True for a real 'YYYY-MM-DD' dt= key. The NULL_TS_PARTITION sentinel is never compacted."""
    if dt == NULL_TS_PARTITION or len(dt) != 10:
        return False
    try:
        date.fromisoformat(dt)
    except ValueError:
        return False
    return True


def eligible_partitions(all_dts, *, today: date, min_age_days: int) -> list[str]:
    """dt= keys old enough to be closed to the live writer, newest-first excluded.

    A partition is eligible iff it is a real date AND `dt <= today - min_age_days`. The live
    partition is defined by the WRITER's clock (ingestion_ts, UTC), so this is a UTC comparison.
    """
    cutoff = today - timedelta(days=min_age_days)
    return sorted(d for d in all_dts if is_date_partition(d) and date.fromisoformat(d) <= cutoff)


# ────────────────────────────────────────────────────────────────────────────────
# Verification — the invariants that let us delete the originals
# ────────────────────────────────────────────────────────────────────────────────
def _nonnull_counts(table: pa.Table) -> dict[str, int]:
    return {name: table.column(name).length() - table.column(name).null_count
            for name in table.column_names}


def _sum_nonnull(tables: list[pa.Table]) -> dict[str, int]:
    total: dict[str, int] = {}
    for t in tables:
        for name, n in _nonnull_counts(t).items():
            total[name] = total.get(name, 0) + n
    return total


def verify_compacted(compacted: pa.Table, sources: list[pa.Table]) -> None:
    """Raise unless `compacted` preserves every row, column and non-null value of `sources`.

    Three checks, because each catches a different way a union can silently lose data:
      * row count   — a dropped/duplicated FILE;
      * column set  — a column present in only some files being dropped by the schema union
                      (`union_by_name=true` readers would silently lose it);
      * per-column non-null counts — a botched type promotion turning values into nulls.
    """
    want_rows = sum(t.num_rows for t in sources)
    if compacted.num_rows != want_rows:
        raise CompactionRefused(
            f"row count mismatch after compaction: wrote {compacted.num_rows:,}, "
            f"sources hold {want_rows:,}"
        )
    want_cols = set()
    for t in sources:
        want_cols |= set(t.column_names)
    got_cols = set(compacted.column_names)
    if got_cols != want_cols:
        raise CompactionRefused(
            f"column set changed: missing {sorted(want_cols - got_cols)}, "
            f"unexpected {sorted(got_cols - want_cols)}"
        )
    want_nn, got_nn = _sum_nonnull(sources), _nonnull_counts(compacted)
    bad = {c: (want_nn[c], got_nn[c]) for c in want_nn if want_nn[c] != got_nn.get(c)}
    if bad:
        raise CompactionRefused(f"non-null counts changed (want, got): {bad}")


# ────────────────────────────────────────────────────────────────────────────────
# The per-partition operation
# ────────────────────────────────────────────────────────────────────────────────
def _repair_partial(s3, source: str, dt: str, keys: list[str], *, apply: bool) -> dict:
    """A prior run died between the promote and the delete: `part-compact-*` beside originals.

    Decidable, so it is repaired rather than refused: the compacted file either already holds
    every original row (⇒ delete the originals, finishing the interrupted run) or it does not
    (⇒ REFUSE — something else is going on and a human must look).
    """
    compact_keys = [k for k in keys if _is_compacted(k)]
    original_keys = [k for k in keys if not _is_compacted(k)]
    if len(compact_keys) > 1:
        raise CompactionRefused(
            f"{source}/dt={dt}: {len(compact_keys)} compacted files present "
            f"({[k.rsplit('/', 1)[-1] for k in compact_keys]}) — this script only ever writes "
            f"one. Inspect before deleting anything."
        )
    compacted = _read_table(s3, compact_keys[0])
    originals = [_read_table(s3, k) for k in original_keys]
    want = sum(t.num_rows for t in originals)
    if compacted.num_rows != want:
        raise CompactionRefused(
            f"{source}/dt={dt}: interrupted run cannot be repaired automatically — the compacted "
            f"file holds {compacted.num_rows:,} rows but the {len(original_keys)} originals hold "
            f"{want:,}. Neither file set is deleted; inspect manually."
        )
    print(f"  dt={dt}: REPAIRING an interrupted prior run "
          f"(compacted file already holds all {want:,} rows; deleting {len(original_keys)} originals)")
    if apply:
        _delete_keys(s3, original_keys)
    return {"dt": dt, "repaired": True, "files_before": len(keys), "files_after": 1, "rows": want}


def compact_partition(s3, source: str, dt: str, *, apply: bool, max_workers: int = 8) -> dict | None:
    """Compact one dt= partition. Returns a result dict, or None if there was nothing to do.

    Order (see the module docstring): read → write the compacted object → RE-READ it from S3 and
    verify → only then delete the originals. A verification failure removes the object this run
    wrote and raises; the originals are untouched, so a failed run costs nothing but time.
    """
    keys = list_partition_files(s3, source, dt)
    if not keys:
        return None
    if any(_is_compacted(k) for k in keys):
        if len(keys) == 1:
            return None                                    # already compacted — the steady state
        return _repair_partial(s3, source, dt, keys, apply=apply)
    if len(keys) < 2:
        return None                                        # a single file: nothing to gain

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        tables = list(pool.map(lambda k: _read_table(s3, k), keys))
    rows = sum(t.num_rows for t in tables)

    # `promote_options="permissive"` unifies differing/missing columns across files — the same
    # union the readers' `union_by_name=true` performs at bind time, so the compacted file is
    # exactly what a reader would have seen. verify_compacted() then proves nothing was lost.
    compacted = pa.concat_tables(tables, promote_options="permissive")
    verify_compacted(compacted, tables)

    buf = io.BytesIO()
    pq.write_table(compacted, buf, compression="snappy")
    payload = buf.getvalue()
    mb = len(payload) / 1e6
    if mb > _LARGE_PARTITION_MB:
        print(f"  ⚠️  dt={dt}: compacted output is {mb:,.0f} MB — consider splitting this source "
              f"into several output files if it keeps growing")

    if not apply:
        print(f"  dt={dt}: would compact {len(keys)} files → 1 "
              f"({rows:,} rows, {mb:.2f} MB)  [dry-run]")
        return {"dt": dt, "repaired": False, "files_before": len(keys), "files_after": 1,
                "rows": rows, "dry_run": True}

    new_key = f"{_partition_prefix(source, dt)}{COMPACT_PREFIX}{uuid.uuid4().hex[:12]}.parquet"
    s3.put_object(Bucket=BUCKET, Key=new_key, Body=payload)

    # ⭐ Re-read from S3 (not from the in-memory table) — this proves the PUT actually landed and
    # is READABLE before anything is deleted. Verifying the local object would prove nothing about
    # what a reader will find.
    try:
        verify_compacted(_read_table(s3, new_key), tables)
    except Exception:
        s3.delete_object(Bucket=BUCKET, Key=new_key)       # leave the partition exactly as found
        raise

    _delete_keys(s3, keys)
    print(f"  dt={dt}: compacted {len(keys)} files → 1 "
          f"({rows:,} rows, {mb:.2f} MB, {time.time() - t0:.1f}s)")
    return {"dt": dt, "repaired": False, "files_before": len(keys), "files_after": 1, "rows": rows}


# ────────────────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", required=True,
                    help=f"raw source to compact. Allowlisted: {sorted(COMPACTABLE_SOURCES)}")
    ap.add_argument("--apply", action="store_true",
                    help="actually mutate PRODUCTION S3 (default: dry-run plan only)")
    ap.add_argument("--min-age-days", type=int, default=_DEFAULT_MIN_AGE_DAYS,
                    help=f"only compact partitions at least this old, UTC "
                         f"(default {_DEFAULT_MIN_AGE_DAYS}; floor {_MIN_AGE_DAYS_FLOOR} — the "
                         f"live partition is never compacted)")
    ap.add_argument("--max-partitions", type=int, default=None,
                    help="stop after this many partitions (for a first, cautious pass)")
    ap.add_argument("--max-workers", type=int, default=8,
                    help="parallel S3 GETs within one partition (default 8)")
    args = ap.parse_args(argv)

    if args.source not in COMPACTABLE_SOURCES:
        known = "a known raw source" if args.source in RAW_SOURCES else "not a known raw source"
        print(f"❌ '{args.source}' is {known}, but it is NOT allowlisted for compaction.\n"
              f"   Allowlisted: {sorted(COMPACTABLE_SOURCES)}\n"
              f"   Compaction's write order is only safe if EVERY reader of this source's glob is\n"
              f"   duplicate-idempotent (see the module docstring). Enumerate this source's\n"
              f"   readers, prove each dedups, then add it to COMPACTABLE_SOURCES with that\n"
              f"   rationale — do not borrow mlb_odds_raw's.", file=sys.stderr)
        return 1
    if args.min_age_days < _MIN_AGE_DAYS_FLOOR:
        print(f"❌ --min-age-days {args.min_age_days} is below the floor {_MIN_AGE_DAYS_FLOOR}; "
              f"0 would race the live writer appending to dt=<today>.", file=sys.stderr)
        return 1

    s3 = make_s3_client()
    all_dts = list_partition_dts(s3, args.source)
    todo = eligible_partitions(all_dts, today=date.today(), min_age_days=args.min_age_days)
    if args.max_partitions is not None:
        todo = todo[:args.max_partitions]

    mode = "APPLY (mutating PRODUCTION S3)" if args.apply else "DRY-RUN (no writes, no deletes)"
    print(f"compact_lakehouse_raw — source={args.source}  {mode}")
    print(f"  {len(all_dts)} dt= partitions present; {len(todo)} eligible "
          f"(>= {args.min_age_days}d old)")
    print(f"[METRIC] compact_source={args.source}")
    print(f"[METRIC] compact_partitions_eligible={len(todo)}")

    done = failed = files_before = files_after = rows = repaired = 0
    for dt in todo:
        try:
            res = compact_partition(s3, args.source, dt,
                                    apply=args.apply, max_workers=args.max_workers)
        except Exception as exc:  # noqa: BLE001 — one partition's failure must not stop the rest
            failed += 1
            print(f"  ❌ dt={dt}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if res is None:
            continue
        done += 1
        repaired += 1 if res["repaired"] else 0
        files_before += res["files_before"]
        files_after += res["files_after"]
        rows += res["rows"]

    print(f"[METRIC] compact_partitions_done={done}")
    print(f"[METRIC] compact_partitions_repaired={repaired}")
    print(f"[METRIC] compact_files_before={files_before}")
    print(f"[METRIC] compact_files_after={files_after}")
    print(f"[METRIC] compact_rows_preserved={rows}")
    print(f"[METRIC] compact_failures={failed}")
    if failed:
        print(f"\n❌ {failed} partition(s) failed or were refused — see stderr above. "
              f"No partition loses data on a failure: originals are deleted only after the "
              f"compacted object is re-read from S3 and verified.", file=sys.stderr)
        return 1
    print(f"\n✅ {done} partition(s) compacted "
          f"({files_before} files → {files_after}, {rows:,} rows preserved)"
          f"{'  [dry-run — nothing was written]' if not args.apply else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
