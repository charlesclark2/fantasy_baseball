"""s3io.py  (NFL-N0.2 lean lakehouse scaffold — SHARED boilerplate, copied from NCAAF-P0.2)
============================================================================================
DataFrame/records → **Delta** table in the sports S3 lake, season-partitioned and idempotent.
This is the sport-agnostic write layer §2 of `sport_data_platform.md` calls shared boilerplate
("copy or symlink across sports") — this file is a VERBATIM copy of the NCAAF-P0.2 `s3io.py`
except for the two NFL-necessary hardenings noted below; `sport` is always a parameter here.

WHY DELTA (not raw Parquet) — the E11.20 inheritance:
  MLB's E11.20 migrated the hot marts to Delta (`scripts/utils/delta_lake.py`). NFL is built
  Delta-native FROM DAY ONE so we never repeat the raw-parquet→Delta migration:
    • ACID single-writer commits (no torn multi-file/glob-dup states — INC-31 is structurally
      impossible: one table = one `_delta_log`).
    • `schema_mode="merge"` makes an ADDITIVE column a metadata commit (the INC-19 cure).
    • A season-partitioned `replaceWhere` overwrite = O(current season), idempotent
      (re-pulling a season is a value-identical rewrite) — the platform §3 "overwrite the
      (source, season) partition" contract, done atomically.
    • Time-travel for point-in-time / leakage audits (the model layer needs it).

TWO NFL-SPECIFIC HARDENINGS vs the NCAAF copy (both live in `write_dataframe`, the TYPED path
— nflverse is typed parquet, not CFBD JSON, so NFL leans on write_dataframe not write_records):
  1. 🕳️ NULL-TYPED-COLUMN → 'void' Delta crash (N0.2 smoke, the wide-pbp landmine): a sparse
     nflverse column that is ALL-NULL in a given season slice collapses (pandas object →)
     pyarrow `null` type → delta-rs writes a Delta `void` column → DuckDB `delta_scan` then
     fails to READ the table (`Unsupported Delta table type: 'void'`). `_sanitize_null_columns`
     recasts every null-typed column to `string` (value-preserving — the column is all-NULL)
     BEFORE the write, so the stored schema is always a concrete Delta type. Bit `pbp`
     (372 cols; e.g. `end_yard_line`, `st_play_type` are null in some seasons).
  2. Empty-slice guard: a below-floor season (FTN <2022, NGS <2016, participation <2016)
     yields 0 rows → skip the write (no empty partition), mirroring `write_records`.

WHY raw_json (a single VARCHAR column) for the raw tier — used by the Odds API feeds only:
  Odds API records carry a nested bookmakers[]→markets[]→outcomes[] array whose field-presence
  varies across books/seasons. Landing each event as a `raw_json` string (+ season/week/source/
  ingested_at scalars) keeps the Delta schema trivially stable; the dbt-duckdb staging flattens
  it with DuckDB JSON functions (MLB's proven W3pre VARIANT→raw pattern, Delta-native). The
  TYPED nflverse feeds instead pass a ready DataFrame via `write_dataframe`.

🪪 S3 AUTH — the AKID landmine, in delta-rs dress (CLAUDE.md / E11.20 delta_lake.py):
  delta-rs takes `storage_options`, NOT boto3, and its object_store reads the AWS_* env vars
  ITSELF. A docker-compose-interpolated EMPTY `AWS_ACCESS_KEY_ID=""` gets signed verbatim
  (→ 400 AuthorizationHeaderMalformed). So `storage_options()` forwards explicit env keys ONLY
  when both id+secret are present & non-empty, else resolves the botocore chain HERE
  (env → profile → IMDS instance role) and passes those credentials explicitly.
  NEVER `aws_access_key_id=os.environ.get(...)` — that is the exact bug the guard forbids.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Iterable

import pyarrow as pa

log = logging.getLogger(__name__)

# ── The sport-agnostic bucket (cross-sport decision #2, sport_data_platform.md §16). Shared
# across NFL/NCAAF/NCAAB, prefix-isolated per sport (`nfl/…`). The operator creates the bucket
# + the instance-role grant. Overridable via env for dev.
DEFAULT_BUCKET = os.environ.get("SPORTS_LAKE_BUCKET", "credence-sports-lakehouse")
DEFAULT_REGION = os.environ.get("SPORTS_LAKE_REGION", "us-east-2")  # DuckDB + delta-rs both need it explicit

# Delta tables live under their OWN prefix (raw/), season-partitioned. The partition column name
# is fixed so the weekly incremental `replaceWhere` always pins it.
PARTITION_COL = "season"

# vacuum below this physically deletes files older versions point to → time-travel BREAKS
# (E11.20 spike gotcha #3). 168h is the FLOOR, clamped in maintenance.
DELTA_MIN_RETENTION_HOURS = 168


# ── S3 lake location ────────────────────────────────────────────────────────────────────
def table_uri(sport: str, source: str, *, bucket: str = DEFAULT_BUCKET, tier: str = "raw") -> str:
    """The Delta table directory (holds `_delta_log/`) for one logical (sport, source).

    Layout: s3://<bucket>/<sport>/<tier>/<source>/  (season is a Delta partition INSIDE).
    Mirrors sport_data_platform.md §3 `s3://<bucket>/<sport>/raw/<source>/season=YYYY/…`.
    """
    return f"s3://{bucket}/{sport}/{tier}/{source}"


def local_table_uri(root: str, sport: str, source: str, *, tier: str = "raw") -> str:
    """A local-FS Delta table path (for the offline round-trip smoke + laptop dev before the
    operator provisions the bucket). delta-rs writes local FS identically to S3."""
    return os.path.join(root, sport, tier, source)


# ── delta-rs S3 auth (the AKID-cure; see module docstring) ──────────────────────────────
def _chain_credentials():
    """Resolve AWS creds through botocore's FULL chain (env → profile → IMDS role), or None.
    Same chain the post-INC-16 exporters use; correctly skips an empty-string env var and
    reaches the instance role. Never raises (no boto3 / no creds → None)."""
    try:
        import boto3

        creds = boto3.session.Session().get_credentials()
        return creds.get_frozen_credentials() if creds is not None else None
    except Exception:  # noqa: BLE001
        return None


def storage_options(region: str = DEFAULT_REGION) -> dict[str, str]:
    """delta-rs S3 storage_options carrying CONCRETE credentials whenever the env can produce
    them (so object_store never signs an empty-string AKID). Region is pinned per RESOURCE
    (never inherited from a serving env's AWS_DEFAULT_REGION). Resolved fresh each call so a
    multi-hour backfill outlives no rotating instance-role credential."""
    opts: dict[str, str] = {"AWS_REGION": region}
    key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
    if key and secret:
        opts["AWS_ACCESS_KEY_ID"] = key
        opts["AWS_SECRET_ACCESS_KEY"] = secret
        token = os.environ.get("AWS_SESSION_TOKEN")
        if token:
            opts["AWS_SESSION_TOKEN"] = token
        return opts
    frozen = _chain_credentials()
    if frozen is not None and frozen.access_key and frozen.secret_key:
        opts["AWS_ACCESS_KEY_ID"] = frozen.access_key
        opts["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            opts["AWS_SESSION_TOKEN"] = frozen.token
    return opts


# ── record normalisation (PURE — unit-tested offline, no IO) ────────────────────────────
def records_to_arrow(
    records: Iterable[dict],
    *,
    source: str,
    season: int,
    week: int | None = None,
    ingested_at: str | None = None,
) -> pa.Table:
    """Wrap raw JSON records (Odds API events) into the schema-stable raw-tier Arrow table:
        season INT64 · week INT64(nullable) · source STRING · ingested_at STRING(ISO) ·
        raw_json STRING (the full record, json.dumps).

    Storing the record as a JSON string keeps the Delta schema identical across every
    season/source (the dbt staging flattens it). `ingested_at` is an ISO VARCHAR (never a
    binary timestamp) — DuckDB casts it at the use-site, no timezone ambiguity.
    """
    recs = list(records)
    stamp = ingested_at or datetime.now(timezone.utc).isoformat()
    seasons = [int(season)] * len(recs)
    weeks = [None if week is None else int(week)] * len(recs)
    return pa.table(
        {
            "season": pa.array(seasons, type=pa.int64()),
            "week": pa.array(weeks, type=pa.int64()),
            "source": pa.array([source] * len(recs), type=pa.string()),
            "ingested_at": pa.array([stamp] * len(recs), type=pa.string()),
            "raw_json": pa.array([json.dumps(r, default=str) for r in recs], type=pa.string()),
        }
    )


def _reject_unsigned(table: pa.Table, context: str) -> None:
    """Delta has NO unsigned types — delta-rs casts uint→signed and OVERFLOWS above 2^63
    (the E11.20 pitch_sk crash). Fail HERE with the cure instead of a cryptic Cast error."""
    import pyarrow.types as pat

    bad = [f.name for f in table.schema if pat.is_unsigned_integer(f.type)]
    if bad:
        raise ValueError(
            f"{context}: unsigned column(s) {bad} cannot be stored in Delta (the protocol "
            f"has no unsigned types; uint64 overflows Int64). Cast them to a signed/decimal "
            f"type before writing."
        )


def _sanitize_null_columns(table: pa.Table) -> pa.Table:
    """Recast every ALL-NULL (pyarrow `null`-typed) column to `string` — hardening #1.

    A sparse nflverse column that is all-null in a season slice arrives as a pyarrow `null`
    type; delta-rs writes it as a Delta `void` column, which DuckDB `delta_scan` then CANNOT
    read (`Unsupported Delta table type: 'void'`). Casting null → string is value-preserving
    (the column is entirely null) and gives the stored table a concrete Delta type. PURE, so
    it's unit-tested offline. No-op when there are no null-typed columns (the common case)."""
    import pyarrow.types as pat

    if not any(pat.is_null(f.type) for f in table.schema):
        return table
    cols, fields = [], []
    for i, f in enumerate(table.schema):
        if pat.is_null(f.type):
            cols.append(table.column(i).cast(pa.string()))
            fields.append(pa.field(f.name, pa.string()))
        else:
            cols.append(table.column(i))
            fields.append(f)
    return pa.table(cols, schema=pa.schema(fields))


# ── the Delta write path (delta-rs — DuckDB's delta extension is READ-only) ──────────────
def write_season_partition(
    table: pa.Table,
    uri: str,
    season: int,
    *,
    partition_col: str = PARTITION_COL,
    storage: dict[str, str] | None = None,
    create_ok: bool = True,
) -> int:
    """Atomically overwrite ONE season partition of a Delta table with `table`.

    `replaceWhere season = <season>` — O(current season), idempotent (re-pulling a season is a
    value-identical rewrite), and the weekly-incremental contract (re-pull the current season,
    rewrite just its partition). `schema_mode="merge"` makes an additive upstream field a
    metadata commit. A missing table is created (partitioned) when `create_ok`. Returns rows
    written. Works against S3 or a local FS path (delta-rs treats both alike).
    """
    from deltalake import DeltaTable, write_deltalake
    from deltalake.exceptions import TableNotFoundError

    _reject_unsigned(table, f"write_season_partition(uri={uri!r}, season={season})")
    table = _sanitize_null_columns(table)
    opts = storage if storage is not None else (storage_options() if uri.startswith("s3://") else None)

    exists = True
    try:
        DeltaTable(uri, storage_options=opts)
    except TableNotFoundError:
        exists = False

    if not exists:
        if not create_ok:
            raise RuntimeError(f"Delta table {uri} does not exist (run the backfill first).")
        write_deltalake(uri, table, mode="overwrite", partition_by=[partition_col], storage_options=opts)
        return table.num_rows

    write_deltalake(
        uri,
        table,
        mode="overwrite",
        predicate=f"{partition_col} = {int(season)}",
        schema_mode="merge",
        storage_options=opts,
    )
    return table.num_rows


def write_records(
    records: Iterable[dict],
    *,
    sport: str,
    source: str,
    season: int,
    week: int | None = None,
    bucket: str = DEFAULT_BUCKET,
    local_root: str | None = None,
    tier: str = "raw",
) -> int:
    """Land raw JSON records (Odds API) for one (sport, source, season[, week]) as a Delta
    season partition. `local_root` routes the write to a local FS Delta table (offline smoke /
    laptop dev before the bucket exists); otherwise it writes to S3.

    NOTE `week` is stored as a COLUMN, not a Delta partition — the partition grain is season.
    """
    recs = list(records)
    if not recs:
        log.info("  [%s/%s] season=%s week=%s: 0 records — skip", sport, source, season, week)
        return 0
    table = records_to_arrow(recs, source=source, season=season, week=week)
    uri = (
        local_table_uri(local_root, sport, source, tier=tier)
        if local_root
        else table_uri(sport, source, bucket=bucket, tier=tier)
    )
    n = write_season_partition(table, uri, season)
    log.info("  [%s/%s] season=%s week=%s: wrote %d rows → %s", sport, source, season, week, n, uri)
    return n


def existing_seasons(
    sport: str,
    source: str,
    *,
    bucket: str = DEFAULT_BUCKET,
    local_root: str | None = None,
    tier: str = "raw",
) -> set[int]:
    """The set of `season` partition values already written for (sport, source) — a PURE
    S3/filesystem listing, ZERO network fetches. Used by `--skip-existing` to resume a backfill
    without re-fetching seasons already landed. Parses `season=YYYY` from the Delta data-file
    paths (partition dirs). Presence of a season's parquet = that season's atomic write
    completed (a season is written whole per the idempotent-partition contract)."""
    import re

    pat = re.compile(r"season=(\d+)")
    seasons: set[int] = set()

    if local_root:
        base = local_table_uri(local_root, sport, source, tier=tier)
        if os.path.isdir(base):
            for entry in os.listdir(base):
                m = pat.match(entry)
                if m:
                    seasons.add(int(m.group(1)))
        return seasons

    # S3 — instance-role-safe client (default chain, NO explicit keys → the AKID cure).
    import boto3

    s3 = boto3.client("s3", region_name=DEFAULT_REGION)
    prefix = f"{sport}/{tier}/{source}/"
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                m = pat.search(obj["Key"])
                if m:
                    seasons.add(int(m.group(1)))
    return seasons


def write_dataframe(
    df,
    *,
    sport: str,
    source: str,
    season: int,
    bucket: str = DEFAULT_BUCKET,
    local_root: str | None = None,
    tier: str = "raw",
    partition_col: str = PARTITION_COL,
) -> int:
    """Land a TYPED pandas DataFrame (an nflverse parquet slice already read via DuckDB) as a
    Delta season partition — the PRIMARY NFL path (the whole player/team/PBP/advanced/roster
    stack is typed parquet). The DataFrame must carry a `season` column (or one is stamped —
    e.g. `pbp_participation` has no season col, so the URL year is stamped).

    Two NFL hardenings apply here (see module docstring): an empty slice is skipped (no empty
    partition — a below-floor season yields 0 rows), and all-null columns are recast to string
    inside `write_season_partition` (the wide-`pbp` `void`-Delta landmine). Unsigned columns
    are rejected with the cure (Delta has no uint)."""
    import pandas as pd  # noqa: F401 — DataFrame path

    if df is None or len(df) == 0:
        log.info("  [%s/%s] season=%s: 0 typed rows — skip (below-floor / empty slice)",
                 sport, source, season)
        return 0
    if partition_col not in df.columns:
        df = df.assign(**{partition_col: int(season)})
    table = pa.Table.from_pandas(df, preserve_index=False)
    uri = (
        local_table_uri(local_root, sport, source, tier=tier)
        if local_root
        else table_uri(sport, source, bucket=bucket, tier=tier)
    )
    n = write_season_partition(table, uri, season, partition_col=partition_col)
    log.info("  [%s/%s] season=%s: wrote %d typed rows → %s", sport, source, season, n, uri)
    return n
