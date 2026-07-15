"""s3io.py  (NCAAF-P0.2 lean lakehouse scaffold — SHARED boilerplate)
======================================================================
DataFrame/records → **Delta** table in the sports S3 lake, season-partitioned and
idempotent. This is the sport-agnostic write layer §2 of `sport_data_platform.md` calls
shared boilerplate ("copy or symlink across sports") — NFL/NCAAB reuse it unchanged; only
`sources.py` + the dbt models are sport-specific. `sport` is always a parameter here.

WHY DELTA (not raw Parquet) — the E11.20 inheritance the P0.2 prompt mandates:
  MLB's E11.20 migrated the hot marts to Delta (`scripts/utils/delta_lake.py`). NCAAF is
  built Delta-native FROM DAY ONE so we never repeat the raw-parquet→Delta migration:
    • ACID single-writer commits (no torn multi-file/glob-dup states — INC-31 is
      structurally impossible: one table = one `_delta_log`).
    • `schema_mode="merge"` makes an ADDITIVE column a metadata commit (the INC-19 cure).
    • A season-partitioned `replaceWhere` overwrite = O(current season), idempotent
      (re-pulling a season is a value-identical rewrite) — the platform §3 "overwrite the
      (source, season) partition" contract, done atomically.
    • Time-travel for point-in-time / leakage audits (the model layer needs it).

WHY raw_json (a single VARCHAR column) for the raw tier:
  CFBD JSON records vary field-presence across 12 seasons. Landing each record as a
  `raw_json` string (+ `season`, `week`, `source`, `ingested_at` scalars) keeps the Delta
  schema trivially stable across the whole backfill, and the dbt-duckdb staging layer
  flattens with DuckDB JSON functions (`json_extract*`) — MLB's proven W3pre VARIANT→raw
  pattern, Delta-native. Typed feeds (nflverse parquet) can instead pass a ready DataFrame
  via `write_dataframe`.

🪪 S3 AUTH — the AKID landmine, in delta-rs dress (CLAUDE.md / E11.20 delta_lake.py):
  delta-rs takes `storage_options`, NOT boto3, and its object_store reads the AWS_* env
  vars ITSELF. A docker-compose-interpolated EMPTY `AWS_ACCESS_KEY_ID=""` gets signed
  verbatim (→ 400 AuthorizationHeaderMalformed). So `_storage_options()` forwards explicit
  env keys ONLY when both id+secret are present & non-empty, else resolves the botocore
  chain HERE (env → profile → IMDS instance role) and passes those credentials explicitly.
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

# ── The NEW sport-agnostic bucket (cross-sport decision #2, sport_data_platform.md §16).
# NOT the MLB bucket (baseball-named). Prefix-isolated per sport. The operator creates the
# bucket + the instance-role grant (see the P0.2 handoff). Overridable via env for dev.
DEFAULT_BUCKET = os.environ.get("SPORTS_LAKE_BUCKET", "credence-sports-lakehouse")
DEFAULT_REGION = os.environ.get("SPORTS_LAKE_REGION", "us-east-2")  # DuckDB + delta-rs both need it explicit

# Delta tables live under their OWN prefix (raw/), season-partitioned. The partition column
# name is fixed so the daily/weekly incremental `replaceWhere` always pins it (spike gotcha
# #8: a non-partition-aware predicate scans all history and forfeits the O(season) win).
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
    """delta-rs S3 storage_options carrying CONCRETE credentials whenever the env can
    produce them (so object_store never signs an empty-string AKID). Region is pinned per
    RESOURCE (never inherited from a serving env's AWS_DEFAULT_REGION). Resolved fresh each
    call so a multi-hour backfill outlives no rotating instance-role credential."""
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
    """Wrap raw JSON records into the schema-stable raw-tier Arrow table:
        season INT64 · week INT64(nullable) · source STRING · ingested_at STRING(ISO) ·
        raw_json STRING (the full record, json.dumps).

    Storing the record as a JSON string keeps the Delta schema identical across every
    season/source (the dbt staging flattens it), so no per-season schema drift and no
    Delta unsigned-int / mixed-type surprises. `ingested_at` is an ISO VARCHAR (never a
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

    `replaceWhere season = <season>` — O(current season), idempotent (re-pulling a season
    is a value-identical rewrite), and the weekly-incremental contract (re-pull the current
    season, rewrite just its partition). `schema_mode="merge"` makes an additive upstream
    field a metadata commit. A missing table is created (partitioned) when `create_ok`.
    Returns rows written. Works against S3 or a local FS path (delta-rs treats both alike).
    """
    from deltalake import DeltaTable, write_deltalake
    from deltalake.exceptions import TableNotFoundError

    _reject_unsigned(table, f"write_season_partition(uri={uri!r}, season={season})")
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
    """Land raw JSON records for one (sport, source, season[, week]) as a Delta season
    partition. `local_root` routes the write to a local FS Delta table (offline smoke /
    laptop dev before the bucket exists); otherwise it writes to S3.

    NOTE `week` is stored as a COLUMN, not a Delta partition — the partition grain is season
    (matches the platform §3 idempotent-per-season contract). A weekly re-pull that supplies
    ALL weeks of the current season overwrites the season partition wholesale.
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
    """Land a TYPED pandas DataFrame (e.g. an nflverse parquet slice already read via
    DuckDB) as a Delta season partition. The DataFrame must carry a `season` column (or
    one is stamped). Unsigned columns are rejected with the cure (Delta has no uint)."""
    import pandas as pd  # noqa: F401 — DataFrame path

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
