"""store.py — the IMMUTABLE point-in-time capture store (Delta + write-once raw payloads).

⭐ THE ONE STRUCTURAL DIVERGENCE FROM `ingest/s3io.py`, and the reason this module exists:

    `s3io.write_season_partition` writes `mode="overwrite"` with `replaceWhere season = N`.
    That is exactly right for a REPRODUCIBLE feed (re-pull a season, rewrite its partition, get
    a value-identical result) and exactly WRONG for a point-in-time capture. A PIT capture is
    not reproducible — it is a MEASUREMENT OF A MOMENT. Overwriting the Tuesday forecast with
    the Friday forecast destroys the only copy of what was knowable on Tuesday, and the archive
    cannot give it back (Open-Meteo's archive returns OBSERVATIONS, and the odds history holds
    only CLOSING lines). So this store is APPEND-ONLY, partitioned by `capture_date`, and
    nothing here ever issues an overwrite.

DEDUPLICATION WITHOUT OVERWRITING: `capture_id` is deterministic over
(capture_source, subject_key, checkpoint), so a cron that re-fires inside the same checkpoint
window produces the same id. `append_captures` reads the existing ids for the capture_date and
drops already-present ones BEFORE writing, so a re-fire is a no-op instead of a duplicate.
⚠️ It drops on `capture_id` ALONE, never on payload equality: if the same capture identity comes
back with a DIFFERENT payload, that is a vendor REVISION, and the store keeps the original and
declines the revision (the revision is still recorded in the `revisions` manifest so the fact of
it is visible — a silently-dropped revision would be its own silent death).

RAW PAYLOADS ARE RETAINED IMMUTABLY (§13): every capture's raw payload is written WRITE-ONCE as
a JSON object under `<sport>/pit_raw/<source>/capture_date=…/<capture_id>.json`. The writer HEADs
before it PUTs and refuses to replace an existing object. That is the physical guarantee behind
the "revised vendor data replaced the original" rejection — the guard can only be trusted if the
original is genuinely still on disk.

TIMESTAMP STORAGE: every stamp is an ISO-8601 UTC VARCHAR (INC-23 / the W8a binary-parquet-
timestamp landmine). `capture_date` is a plain `YYYY-MM-DD` string partition value.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable

from ..ingest import s3io
from .timestamps import parse_utc

log = logging.getLogger(__name__)

SPORT = "nfl"

#: The PIT tier lives beside `raw/` but is NEVER touched by the season-overwrite ingest path.
PIT_TIER = "pit"
PIT_RAW_TIER = "pit_raw"

#: Partition grain. Capture DATE (not season): an append-only table partitioned by season would
#: grow one unbounded partition per season and make a day's captures unlistable.
PARTITION_COL = "capture_date"


class ImmutableStoreError(RuntimeError):
    """A write would have destroyed or replaced an existing immutable capture."""


def capture_date_of(capture_timestamp) -> str:
    """The `YYYY-MM-DD` UTC partition value for a capture stamp (fail-closed on a naive stamp)."""
    return parse_utc(capture_timestamp, field="capture_timestamp").date().isoformat()


def table_uri(source: str, *, bucket: str | None = None, local_root: str | None = None) -> str:
    if local_root:
        return s3io.local_table_uri(local_root, SPORT, source, tier=PIT_TIER)
    return s3io.table_uri(SPORT, source, bucket=bucket or s3io.DEFAULT_BUCKET, tier=PIT_TIER)


def _raw_key(source: str, capture_date: str, capture_id: str) -> str:
    return f"{SPORT}/{PIT_RAW_TIER}/{source}/capture_date={capture_date}/{capture_id}.json"


# ── write-once raw payload retention ────────────────────────────────────────────────────
def retain_raw_payload(
    *,
    source: str,
    capture_id: str,
    capture_date: str,
    payload,
    bucket: str | None = None,
    local_root: str | None = None,
    overwrite_ok: bool = False,
) -> str:
    """Persist ONE capture's raw payload write-once. Returns the object key/path.

    Refuses to replace an existing object unless `overwrite_ok` (which no caller in this package
    sets — it exists so a test can prove the refusal fires rather than being unreachable).
    Returns the existing location unchanged when the payload is already retained, so a re-fired
    cron is idempotent rather than an error.
    """
    key = _raw_key(source, capture_date, capture_id)
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")

    if local_root:
        path = os.path.join(local_root, key)
        if os.path.exists(path) and not overwrite_ok:
            log.debug("raw payload already retained (write-once) — %s", path)
            return path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(blob)
        return path

    client = _s3_client()
    target = bucket or s3io.DEFAULT_BUCKET
    if not overwrite_ok and _object_exists(client, target, key):
        log.debug("raw payload already retained (write-once) — s3://%s/%s", target, key)
        return key
    client.put_object(Bucket=target, Key=key, Body=blob, ContentType="application/json")
    return key


def _s3_client():
    """Instance-role-safe S3 client.

    ⛔ NEVER `aws_access_key_id=os.environ.get(...)` — on the EC2 box that env var is UNSET, so
    passing it hands boto3 an explicit `None`, which DISABLES the default credential chain and
    fails with `AuthorizationHeaderMalformed`. Constructing with no explicit keys lets the chain
    reach the instance role. (CLAUDE.md 🪪; enforced by `test_boto3_credential_lint.py`.)
    """
    import boto3

    return boto3.client("s3", region_name=s3io.DEFAULT_REGION)


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001 — 404/403 both mean "not retained by us"
        return False


# ── the append-only Delta capture table ─────────────────────────────────────────────────
def existing_capture_ids(
    source: str,
    capture_date: str,
    *,
    bucket: str | None = None,
    local_root: str | None = None,
) -> dict[str, str]:
    """`capture_id -> payload_sha256` already stored for (source, capture_date).

    Returns `{}` when the table does not exist yet (a first capture is not an error). Any OTHER
    read failure PROPAGATES — a store we cannot read must never be treated as an empty store, or
    a re-fire would happily append duplicates and a revision would look like a first capture.
    """
    uri = table_uri(source, bucket=bucket, local_root=local_root)
    try:
        import duckdb
        from deltalake import DeltaTable
        from deltalake.exceptions import TableNotFoundError
    except ImportError as exc:  # pragma: no cover — environment problem, not a data state
        raise ImmutableStoreError(f"cannot read the PIT store ({exc})") from exc

    opts = s3io.storage_options() if uri.startswith("s3://") else None
    try:
        dt = DeltaTable(uri, storage_options=opts)
    except TableNotFoundError:
        return {}

    rows = _query_ids(duckdb.connect(), dt, capture_date)
    return {r[0]: r[1] for r in rows}


def _query_ids(con, dt, capture_date: str):
    """Read (capture_id, payload_sha256) for one capture_date via the Delta table's Arrow dataset.

    Goes through `to_pyarrow_dataset()` rather than a DuckDB `delta_scan` URI so the read reuses
    the credentials `DeltaTable` already resolved (the delta-rs `storage_options` path) instead of
    requiring DuckDB's own S3 secret to be configured in-process.
    """
    dataset = dt.to_pyarrow_dataset()
    con.register("pit_captures", dataset)
    try:
        return con.execute(
            "SELECT capture_id, payload_sha256 FROM pit_captures WHERE capture_date = ?",
            [capture_date],
        ).fetchall()
    finally:
        con.unregister("pit_captures")


#: How to interpret "same capture_id, different payload". A PER-SOURCE property, and getting it
#: wrong in either direction is costly, so it is declared rather than inferred:
#:
#:   REVISION_SEMANTICS — the vendor is expected to publish a STABLE record for this identity
#:     (an injury report row, an asset schema). A changed payload is the §13 "revised vendor data
#:     replaced the original captured record" case: keep the original, ALERT.
#:   LIVE_VALUE_SEMANTICS — the feed is a CONTINUOUSLY MOVING quantity (a weather forecast, an
#:     odds board). Within one checkpoint window a re-fetch legitimately differs, so a changed
#:     payload is an expected re-read, NOT a revision: keep the first (it is the point-in-time
#:     record for that checkpoint), count it, do NOT alert.
#:
#: Measured 2026-08-05: without this split, EVERY benign weather re-fire alerted as a vendor
#: revision — a 100%-false-positive channel, i.e. the over-paging monitor that gets muted.
REVISION_SEMANTICS = "revision"
LIVE_VALUE_SEMANTICS = "live_value"


def append_captures(
    rows: Iterable[dict],
    *,
    source: str,
    bucket: str | None = None,
    local_root: str | None = None,
    retain_raw: bool = True,
    semantics: str = REVISION_SEMANTICS,
) -> dict:
    """APPEND capture rows to the immutable store. Never overwrites. Returns a manifest.

    Manifest: `{written, skipped_duplicate, skipped_recapture, revisions, capture_dates, uri}`.
      • `skipped_duplicate`  — same capture_id, same payload: a benign cron re-fire.
      • `skipped_recapture`  — same capture_id, different payload, LIVE_VALUE source: the first
                               capture stands as that checkpoint's record. Counted, not alerted.
      • `revisions`          — same capture_id, different payload, REVISION source: the original
                               is KEPT and the revision declined, and it is REPORTED so an
                               upstream rewrite is never silent.

    ⭐ In EVERY case the ORIGINAL stands and nothing is overwritten — `semantics` changes only how
    the difference is REPORTED, never what is stored.

    Each row must carry the `CaptureStamps` fields plus a `payload` (retained write-once) — the
    `payload` key itself is popped before the Delta write so the tabular row stays narrow.
    """
    rows = list(rows)
    if not rows:
        log.info("  [nfl/pit/%s] 0 capture rows — nothing to append", source)
        return {
            "written": 0, "skipped_duplicate": 0, "skipped_recapture": 0,
            "revisions": [], "capture_dates": [], "uri": None,
        }

    for row in rows:
        row.setdefault(PARTITION_COL, capture_date_of(row["capture_timestamp"]))

    dates = sorted({r[PARTITION_COL] for r in rows})
    known: dict[str, str] = {}
    for d in dates:
        known.update(existing_capture_ids(source, d, bucket=bucket, local_root=local_root))

    fresh, dupes, recaptures, revisions = [], 0, 0, []
    seen_this_batch: set[str] = set()
    for row in rows:
        cid = row["capture_id"]
        if cid in seen_this_batch:
            dupes += 1
            continue
        prior = known.get(cid)
        if prior is not None:
            if prior == row.get("payload_sha256"):
                dupes += 1
            elif semantics == LIVE_VALUE_SEMANTICS:
                # Expected: a moving quantity re-read inside the same checkpoint window. The
                # FIRST capture is that checkpoint's point-in-time record and it stands.
                recaptures += 1
            else:
                revisions.append(
                    {
                        "capture_id": cid,
                        "subject_key": row.get("subject_key"),
                        "original_sha256": prior,
                        "revised_sha256": row.get("payload_sha256"),
                    }
                )
            continue
        seen_this_batch.add(cid)
        fresh.append(row)

    if revisions:
        log.warning(
            "ALERT [nfl/pit/%s] %d vendor REVISION(s) declined — the ORIGINAL capture stands "
            "(immutable store). subjects=%s",
            source,
            len(revisions),
            [r["subject_key"] for r in revisions][:10],
        )
    if recaptures:
        log.info(
            "  [nfl/pit/%s] %d re-capture(s) inside an already-recorded checkpoint — the first "
            "capture stands (live-value source, expected)", source, recaptures,
        )

    uri = table_uri(source, bucket=bucket, local_root=local_root)
    if not fresh:
        log.info(
            "  [nfl/pit/%s] nothing new (%d duplicate, %d re-capture, %d revision) — append skipped",
            source, dupes, recaptures, len(revisions),
        )
        return {
            "written": 0, "skipped_duplicate": dupes, "skipped_recapture": recaptures,
            "revisions": revisions, "capture_dates": dates, "uri": uri,
        }

    payloads = [(r["capture_id"], r[PARTITION_COL], r.pop("payload", None)) for r in fresh]
    if retain_raw:
        for cid, cdate, payload in payloads:
            if payload is not None:
                retain_raw_payload(
                    source=source, capture_id=cid, capture_date=cdate, payload=payload,
                    bucket=bucket, local_root=local_root,
                )

    _append_delta(fresh, uri)
    log.info(
        "  [nfl/pit/%s] appended %d row(s) (%d duplicate, %d re-capture, %d revision declined) → %s",
        source, len(fresh), dupes, recaptures, len(revisions), uri,
    )
    return {
        "written": len(fresh), "skipped_duplicate": dupes, "skipped_recapture": recaptures,
        "revisions": revisions, "capture_dates": dates, "uri": uri,
    }


def _append_delta(rows: list[dict], uri: str) -> None:
    """`mode='append'` — the whole point of this module. NEVER 'overwrite'.

    Reuses `s3io`'s hardenings: all-null columns are recast to string (a Delta `void` column is
    unreadable by `delta_scan`) and unsigned columns are rejected with the cure. Column ordering
    is normalised across rows so a row missing an optional key does not shift the schema.
    """
    import pyarrow as pa
    from deltalake import write_deltalake

    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    table = pa.table({col: pa.array([r.get(col) for r in rows]) for col in columns})
    s3io._reject_unsigned(table, f"append_captures(uri={uri!r})")
    table = s3io._sanitize_null_columns(table)

    opts = s3io.storage_options() if uri.startswith("s3://") else None
    write_deltalake(
        uri, table, mode="append", partition_by=[PARTITION_COL], schema_mode="merge",
        storage_options=opts,
    )


def build_store_index(
    source: str,
    capture_dates: Iterable[str],
    *,
    bucket: str | None = None,
    local_root: str | None = None,
) -> dict[str, list[dict]]:
    """`subject_key -> [{capture_timestamp, payload_sha256}, …]` for the leakage guard's
    `check_original_capture`. Reading it is MANDATORY for a build — the guard rejects when the
    index is absent rather than assuming no revisions exist."""
    import duckdb
    from deltalake import DeltaTable
    from deltalake.exceptions import TableNotFoundError

    uri = table_uri(source, bucket=bucket, local_root=local_root)
    opts = s3io.storage_options() if uri.startswith("s3://") else None
    try:
        dt = DeltaTable(uri, storage_options=opts)
    except TableNotFoundError:
        return {}

    con = duckdb.connect()
    con.register("pit_captures", dt.to_pyarrow_dataset())
    try:
        dates = list(capture_dates)
        placeholders = ",".join("?" * len(dates))
        sql = "SELECT subject_key, capture_timestamp, payload_sha256 FROM pit_captures"
        params: list = []
        if dates:
            sql += f" WHERE capture_date IN ({placeholders})"
            params = dates
        rows = con.execute(sql, params).fetchall()
    finally:
        con.unregister("pit_captures")

    index: dict[str, list[dict]] = {}
    for subject, cap_ts, sha in rows:
        index.setdefault(subject, []).append({"capture_timestamp": cap_ts, "payload_sha256": sha})
    return index
