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
#   W11 adds (the FINISH wave — writer→S3 flip for the Tier-A raw feeds): the FanGraphs
#     leaderboards (JSON-VARIANT raw_json) + the savant/statsapi typed feeds. Each source's
#     live writer flips from a Snowflake-only append to append_raw_rows_lakehouse (gated by
#     LAKEHOUSE_RAW_WRITE_MODE), and its stg model's duckdb branch repoints to read
#     lakehouse_raw/<source>/ under the W11_<...>_LAKEHOUSE env gate. The typed feeds carry no
#     raw_json (no _JSON_COLS member) — write_raw_rows_s3 keeps their scalar columns native.
RAW_SOURCES = frozenset({
    "mlb_odds_raw",
    "mlb_events_raw",
    "derivative_odds_raw",
    "monthly_schedule",
    "odds_snapshots_historical",
    "venues_raw",
    # E11.1-W11 Tier-A — JSON-VARIANT FanGraphs leaderboards (raw_json blob)
    "fg_stuff_plus_raw",
    "fg_hitting_leaderboard_raw",
    # E11.1-W11 Tier-A — JSON-VARIANT savant/statsapi feeds (raw_json blob)
    "catcher_framing_raw",
    "player_transactions",
    # E11.1-W11 Tier-A — typed (columnar) savant/external feeds (no raw_json)
    "sprint_speed_raw",
    "oaa_team_season_raw",
    "savant_park_factors_raw",
    # E11.1-W11 Tier-B — the umpire feed: 4 writers (ingest_umpires / _scorecards /
    # _historical / backfill_umpire_assignments) SHARE ONE Snowflake table
    # (baseball_data.statsapi.umpire_game_log) → they migrate as ONE raw source. Typed
    # (columnar) rows, no raw_json; each writer stamps loaded_at (the stg dedup tiebreaker,
    # normally a SF DDL DEFAULT) so the S3 mirror carries it explicitly.
    "umpire_game_log",
    # E11.1-W11 Tier-C — the weather feed. Both writers (ingest_weather / backfill_observed_weather)
    # share baseball_data.statsapi.weather_raw → ONE raw source. Typed (columnar) rows, no raw_json;
    # each writer stamps loaded_at (the stg dedup tiebreaker, normally a SF DDL DEFAULT) so the S3
    # mirror carries it explicitly. Retention: latest-per-(game_pk,venue_id,obs_type,checkpoint) so
    # re-fetch re-runs don't inflate the mirror (INC-20 latest-per-period at the writer).
    "weather_raw",
    # E11.1-W11 Tier-C ADDITION — the hourly all-slate-park weather TIME-SERIES (the E13.16
    # weather→line-movement precursor). Brand-new S3-ONLY source (no SF table to decommission).
    # One snapshot per (game_pk, capture-hour) with an explicit captured_at; retention keeps the
    # LATEST per hour within the game-day (the trajectory IS the signal — do NOT collapse to
    # latest-per-period like weather_raw). Not consumed by any dbt model yet; it accrues forward.
    "weather_intraday_series",
    # E11.1-W11 Tier-D — the ActionNetwork PUBLIC-BETTING feed (ingest_actionnetwork_betting).
    # Typed (columnar) money%/ticket% percentages, no raw_json; the writer stamps ingestion_timestamp
    # (the stg dedup key `order by ingestion_timestamp desc` + the SCD-2 loaded_at, normally the SF DDL
    # DEFAULT CURRENT_TIMESTAMP the record dict lacks). Unlike weather_raw/monthly_schedule this source
    # is NOT INC-20-pruned (idempotent-by-date, no accumulating month snapshots) → the mirror is
    # append-only and every capture is a distinct-ingestion_timestamp snapshot the SCD-2 chain turns
    # into an intraday shift.
    "public_betting_raw",
    # E11.1-W11 Tier-D ADDITION — the hourly public-betting % TIME-SERIES (the E13.16 public-%→line-
    # movement / reverse-line-movement precursor). Sibling of weather_intraday_series. One snapshot per
    # (game, capture-hour) with an EXPLICIT captured_at; retention keeps EVERY hour within the game-day
    # (the trajectory IS the signal — do NOT collapse to latest-per-period). Kept DISTINCT from the
    # migration's public_betting_raw mirror per the operator's W11-D addendum: a flat, join-free
    # substrate (no game_pk resolution / feature spine dependency) purpose-built for the later analysis.
    # Not consumed by any dbt model yet; it accrues forward.
    "public_betting_intraday_series",
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
                v = row.get(col)
                # E11.1-W11: pandas-derived TYPED rows (e.g. sprint_speed's df.to_dict) carry a NaN
                # float for a missing value in an otherwise-STRING column (e.g. player_name for a
                # nameless row). from_pydict then infers utf8 from the strings and chokes on the NaN
                # ("Expected bytes, got a 'float'"). Snowflake-derived rows (the bridge) use None,
                # not NaN, so this is a NO-OP for the odds/bridge path — it only normalizes the
                # pandas NaN → None so the column type resolves cleanly. (NaN is the only float that
                # is not equal to itself, so `v != v` detects it without importing math/numpy.)
                data[col].append(None if isinstance(v, float) and v != v else v)
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


def make_s3_client():
    """Instance-role-safe boto3 S3 client — the shared helper NEW S3 writers should use.

    W7b-1 footgun (2026-06-29): on the EC2 host S3 auth comes from the instance IAM
    ROLE, so AWS_ACCESS_KEY_ID is UNSET. Passing aws_access_key_id=os.environ.get(...)
    (=None) to boto3 DISABLES its default credential chain → AuthorizationHeaderMalformed.
    This client passes NO keys, so boto3 resolves the instance role (or static creds /
    AWS_PROFILE from the env) via its default chain — the same chain DuckDB COPY uses.
    NEVER hand-build a client with aws_access_key_id=os.environ.get(...); the
    test_boto3_credential_lint.py fast-gate guard FAILS the build if you do.
    """
    import boto3
    return boto3.client("s3", region_name=os.environ.get("AWS_DEFAULT_REGION", REGION))


# Back-compat alias for existing internal callers (prune_partitions / write_raw_rows_s3).
_make_s3_client = make_s3_client


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


# E11.1-W11: the Tier-A raw feeds use their OWN write-mode env, NOT the shared
# LAKEHOUSE_RAW_WRITE_MODE. The shared var is already 's3'/'both' in prod (W3pre/W6 odds cut over),
# so reusing it would flip the W11 writers to S3-only the instant they deploy — BEFORE the per-source
# parity + read-side cutover, silently starving the still-Snowflake-reading stg/marts. A separate
# default-'snowflake' env keeps merging the W11 flips a true no-op until the operator opts THIS wave in.
W11_WRITE_MODE_ENV = "W11_RAW_WRITE_MODE"


# E11.1-W11 Tier-B: the canonical umpire_game_log column set (matches the SF DDL + the stg
# duckdb branch's SELECT). The 4 writers each supply a DIFFERENT subset; umpire_mirror_rows()
# normalizes any partial row to this full set so every writer's S3 mirror is schema-uniform.
UMPIRE_GAME_LOG_COLS = (
    "game_pk", "game_date", "season", "umpire_name", "umpire_id",
    "k_pct", "bb_pct", "total_runs", "called_strikes_above_avg",
    "run_expectancy_delta", "total_run_impact", "accuracy_above_expected",
    "data_source", "loaded_at",
)


def umpire_mirror_rows(rows: list[dict], *, data_source: str | None = None,
                       loaded_at: str | None = None) -> list[dict]:
    """Normalize partial umpire_game_log rows to the full column set for the S3 mirror.

    The 4 umpire writers (ingest_umpires / _scorecards / _historical / backfill_umpire_assignments)
    share baseball_data.statsapi.umpire_game_log but each supplies a different subset of columns.
    This fills every missing column with None, sets data_source (a per-writer constant) when absent,
    and STAMPS loaded_at — the stg dedup tiebreaker (order by loaded_at desc), normally the SF DDL
    DEFAULT CURRENT_TIMESTAMP the record dict lacks — to an ISO UTC string so the S3-read stg picks
    the same latest row as Snowflake. game_date is coerced to an ISO string (write_raw_rows_s3 keeps
    scalars native; the stg duckdb branch casts ::date)."""
    stamp = loaded_at or datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for r in rows:
        row = {c: r.get(c) for c in UMPIRE_GAME_LOG_COLS}
        if row.get("data_source") is None and data_source is not None:
            row["data_source"] = data_source
        if row.get("loaded_at") is None:
            row["loaded_at"] = stamp
        if row.get("game_date") is not None:
            row["game_date"] = str(row["game_date"])
        out.append(row)
    return out


# E11.1-W11 Tier-C: the canonical weather_raw column set (matches the SF DDL + the stg duckdb
# branch's SELECT). Both writers (ingest_weather / backfill_observed_weather) supply this set;
# weather_mirror_rows() normalizes to it + stamps loaded_at so the S3 mirror is schema-uniform.
WEATHER_RAW_COLS = (
    "game_pk", "venue_id", "game_datetime_utc", "fetch_offset_hours",
    "temp_f", "wind_speed_mph", "wind_direction_deg", "humidity_pct",
    "condition_text", "api_source", "weather_observation_type",
    "hours_to_first_pitch", "loaded_at",
)

# The natural dedup key stg_weather_raw uses (one row per game×venue×obs-type×checkpoint). The
# retention writer collapses re-fetch re-runs to the latest loaded_at per this tuple (INC-20).
WEATHER_RAW_RETENTION_KEY = ("game_pk", "venue_id", "weather_observation_type", "hours_to_first_pitch")

# E11.1-W11 Tier-C ADDITION: the hourly time-series column set. Superset of the weather scalars +
# an explicit captured_at (the snapshot's wall-clock, so the trajectory is reconstructable) and a
# captured_hour bucket (retention key — one row per hour is kept; the series IS the signal).
WEATHER_SERIES_COLS = (
    "game_pk", "venue_id", "game_datetime_utc", "hours_to_first_pitch",
    "temp_f", "wind_speed_mph", "wind_direction_deg", "humidity_pct",
    "condition_text", "api_source", "weather_observation_type",
    "captured_at", "captured_hour",
)
# Keep the LATEST snapshot per (game, hour) — do NOT collapse across hours (the trajectory is data).
WEATHER_SERIES_RETENTION_KEY = ("game_pk", "venue_id", "captured_hour")


def _iso_or_none(v):
    """Coerce a datetime/date/str to an ISO string, pass None through. (Mirrors umpire_mirror_rows'
    game_date handling — write_raw_rows_s3 keeps scalars native; the stg duckdb branch try_casts.)"""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


def weather_mirror_rows(rows: list[dict], *, loaded_at: str | None = None) -> list[dict]:
    """Normalize partial weather_raw rows to the full column set for the S3 mirror.

    Both writers build a row from the fetched weather + the game metadata but rely on Snowflake's
    `loaded_at DEFAULT CURRENT_TIMESTAMP`; the S3 mirror has no default, so stamp loaded_at (ISO UTC)
    here — it is the stg dedup tiebreaker (`order by loaded_at desc`). game_datetime_utc/loaded_at are
    coerced to ISO strings (write_raw_rows_s3 keeps scalars native; the stg duckdb branch try_casts to
    timestamp — the INC-23 use-site cast that reconciles the SF-typed bridge with these VARCHAR rows).
    """
    stamp = loaded_at or datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for r in rows:
        row = {c: r.get(c) for c in WEATHER_RAW_COLS}
        if row.get("loaded_at") is None:
            row["loaded_at"] = stamp
        row["loaded_at"] = _iso_or_none(row["loaded_at"])
        row["game_datetime_utc"] = _iso_or_none(row["game_datetime_utc"])
        out.append(row)
    return out


def weather_series_rows(rows: list[dict], *, captured_at: str | None = None) -> list[dict]:
    """Normalize hourly-series rows to WEATHER_SERIES_COLS + stamp captured_at / derive captured_hour.

    captured_at is the snapshot wall-clock (a whole run shares one stamp); captured_hour is its
    truncation to the hour (the retention bucket — one kept per hour). Both stored ISO VARCHAR."""
    stamp = captured_at or datetime.now(timezone.utc).isoformat()
    hour_bucket = stamp[:13]  # 'YYYY-MM-DDTHH' — the hour the snapshot belongs to
    out: list[dict] = []
    for r in rows:
        row = {c: r.get(c) for c in WEATHER_SERIES_COLS}
        row["captured_at"] = _iso_or_none(row.get("captured_at") or stamp)
        if row.get("captured_hour") is None:
            row["captured_hour"] = row["captured_at"][:13]
        row["game_datetime_utc"] = _iso_or_none(row.get("game_datetime_utc"))
        if row.get("weather_observation_type") is None:
            row["weather_observation_type"] = "forecast_intraday_series"
        out.append(row)
    return out


def _ts_sort_key(v):
    """A total-order sort key for a loaded_at/captured_at value that may be a datetime OR a mixed-format
    ISO string (the SF-typed bridge datetime vs the live-writer 'T'/space VARCHAR — the INC-23 union).
    Lexicographic string order is WRONG across formats, so parse to a real datetime when possible."""
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, str) and v:
        s = v.replace("T", " ")
        # tolerate a trailing offset/zone by clipping to the second-precision core when parse fails
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[:26] if "." in s else s[:19], fmt)
            except ValueError:
                continue
    return datetime.min


def dedupe_latest_per_key(rows: list[dict], key_cols, ts_col: str) -> list[dict]:
    """PURE (no IO; unit-tested): keep the row with the greatest ts_col per key_cols tuple.

    This is the INC-20 latest-per-period retention primitive. For weather_raw the key is
    (game_pk,venue_id,obs_type,checkpoint) → re-fetch re-runs collapse to the newest per checkpoint.
    For the hourly series the key includes the hour bucket → one row per hour survives (the trajectory
    is preserved, only true intra-hour re-captures collapse). Ties keep the last-seen row."""
    best: dict[tuple, dict] = {}
    for row in rows:
        k = tuple(row.get(c) for c in key_cols)
        cur = best.get(k)
        if cur is None or _ts_sort_key(row.get(ts_col)) >= _ts_sort_key(cur.get(ts_col)):
            best[k] = row
    return list(best.values())


def _read_partition_rows(s3, source: str, dt: str) -> list[dict]:
    """Read every existing part-file in a source's dt= partition back into row dicts (for the
    within-day retention merge). Tiny partitions (weather is ≤ a few hundred rows/day), so this is
    cheap. Columns come back as stored (timestamps as VARCHAR for live rows). Missing partition → []."""
    prefix = f"{RAW_PREFIX}/{source}/dt={dt}/"
    rows: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".parquet"):
                continue
            body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
            tbl = pq.read_table(io.BytesIO(body))
            rows.extend(tbl.to_pylist())
    return rows


def write_raw_rows_s3_retained(
    source: str,
    rows: list[dict],
    *,
    key_cols,
    ts_col: str = "loaded_at",
    s3_client=None,
) -> int:
    """Write rows to S3 with INC-20 latest-per-key retention applied WITHIN each dt= partition.

    Unlike write_raw_rows_s3 (pure append), this MERGES the incoming rows with what already exists in
    the touched dt= partition(s), keeps the latest row per key_cols (dedupe_latest_per_key), and
    overwrites the partition with the single deduped part. So a re-fetch / re-run never inflates the
    mirror — the physical row count stays bounded to the distinct keys per day, matching the stg dedup
    the reader applies anyway. Returns the number of rows written (post-dedup). Read-back is scoped to
    today's partition only (tiny), so the extra S3 GETs are negligible for the weather volume.
    """
    if source not in RAW_SOURCES:
        raise ValueError(f"Unknown raw source '{source}'. Valid: {sorted(RAW_SOURCES)}")
    if not rows:
        return 0

    s3 = s3_client or _make_s3_client()

    by_dt: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_dt[_partition_date(row)].append(row)

    written = 0
    for dt, new_rows in by_dt.items():
        existing = _read_partition_rows(s3, source, dt)
        merged = dedupe_latest_per_key(existing + new_rows, key_cols, ts_col)
        _delete_partition(s3, source, dt)
        table = rows_to_arrow_table(merged)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression="snappy")
        buf.seek(0)
        key = f"{RAW_PREFIX}/{source}/dt={dt}/part-{uuid.uuid4().hex[:12]}.parquet"
        s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
        log.info("  wrote %d rows (retained latest-per-key from %d) → s3://%s/%s",
                 len(merged), len(existing) + len(new_rows), BUCKET, key)
        written += len(merged)
    return written


# E11.1-W11 Tier-D: the canonical public_betting_raw column set (matches the SF DDL
# create_actionnetwork_public_betting_raw.sql + the stg duckdb branch's SELECT). ingest_actionnetwork
# _betting builds a per-game row from the parsed ActionNetwork response; public_betting_mirror_rows()
# normalizes it to this set + stamps ingestion_timestamp so the S3 mirror is schema-uniform.
PUBLIC_BETTING_RAW_COLS = (
    "game_date", "an_game_id", "home_team_abbr", "away_team_abbr",
    "home_ml_money_pct", "away_ml_money_pct", "home_ml_ticket_pct", "away_ml_ticket_pct",
    "over_money_pct", "under_money_pct", "over_ticket_pct", "under_ticket_pct",
    "book_ids_used", "ingestion_timestamp",
)

# The hourly TIME-SERIES column set (public_betting_intraday_series). Same percentages as the raw
# mirror + an EXPLICIT captured_at (the snapshot wall-clock) so the trajectory is reconstructable and
# join-free. NO game_pk (that resolution lives in the SCD-2 chain, not here) — the series keys on the
# ActionNetwork identifiers + captured_at. Append-only, never pruned (every hour kept — W11-D addendum).
PUBLIC_BETTING_SERIES_COLS = (
    "game_date", "an_game_id", "home_team_abbr", "away_team_abbr",
    "home_ml_money_pct", "away_ml_money_pct", "home_ml_ticket_pct", "away_ml_ticket_pct",
    "over_money_pct", "under_money_pct", "over_ticket_pct", "under_ticket_pct",
    "book_ids_used", "captured_at",
)


def public_betting_mirror_rows(rows: list[dict], *, ingestion_timestamp: str | None = None) -> list[dict]:
    """Normalize parsed ActionNetwork rows to PUBLIC_BETTING_RAW_COLS for the S3 raw mirror.

    The writer parses one row per game (an_game_id + the money%/ticket% columns + book_ids_used) and
    supplies game_date from the requested date; Snowflake fills ingestion_timestamp via its DDL
    DEFAULT CURRENT_TIMESTAMP. The S3 mirror has no default → stamp ingestion_timestamp (ISO UTC) here:
    it is the stg dedup key (`order by ingestion_timestamp desc`) AND the SCD-2 loaded_at, so the
    S3-read stg/SCD-2 picks the same snapshots as Snowflake. A whole capture shares ONE stamp → each
    hourly run is a distinct snapshot the SCD-2 chain turns into an intraday shift. game_date is coerced
    to an ISO string (write_raw_rows_s3 keeps scalars native; the stg duckdb branch casts ::date)."""
    stamp = ingestion_timestamp or datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for r in rows:
        row = {c: r.get(c) for c in PUBLIC_BETTING_RAW_COLS}
        if row.get("ingestion_timestamp") is None:
            row["ingestion_timestamp"] = stamp
        row["ingestion_timestamp"] = _iso_or_none(row["ingestion_timestamp"])
        if row.get("game_date") is not None:
            row["game_date"] = str(row["game_date"])
        out.append(row)
    return out


def public_betting_series_rows(rows: list[dict], *, captured_at: str | None = None) -> list[dict]:
    """Normalize parsed ActionNetwork rows to PUBLIC_BETTING_SERIES_COLS + stamp captured_at.

    The dedicated hourly trajectory (E13.16 public-%→line-movement precursor). captured_at is the
    snapshot wall-clock (a whole run shares one stamp) — stored ISO VARCHAR. Written APPEND-ONLY via
    write_raw_rows_s3 (NOT the latest-per-key retained writer): the operator's W11-D addendum wants
    EVERY hourly snapshot kept within the game-day, so nothing is collapsed."""
    stamp = captured_at or datetime.now(timezone.utc).isoformat()
    out: list[dict] = []
    for r in rows:
        row = {c: r.get(c) for c in PUBLIC_BETTING_SERIES_COLS}
        row["captured_at"] = _iso_or_none(row.get("captured_at") or stamp)
        if row.get("game_date") is not None:
            row["game_date"] = str(row["game_date"])
        out.append(row)
    return out


def w11_write_mode() -> str:
    """The W11 Tier-A write mode (snowflake | both | s3), default 'snowflake' (no-op). Pass the
    result to lakehouse_write_legs() (typed writers) or append_raw_rows_lakehouse(..., mode=) (the
    FanGraphs JSON writers) so all 7 Tier-A flips share ONE wave-level switch independent of odds."""
    return os.environ.get(W11_WRITE_MODE_ENV, "snowflake").lower()


def lakehouse_write_legs(mode: str | None = None) -> tuple[bool, bool]:
    """Resolve a write mode → (write_snowflake, write_s3). Defaults to LAKEHOUSE_RAW_WRITE_MODE when
    mode is None; W11 writers pass w11_write_mode() explicitly (their own env — see W11_WRITE_MODE_ENV).

    E11.1-W11: append_raw_rows_lakehouse couples the Snowflake leg to snowflake_loader.append_raw_rows
    (the VARIANT append model). The Tier-A TYPED writers (sprint_speed/oaa/catcher/park_factors/
    transactions) have a BESPOKE Snowflake write — a temp-table upsert / write_pandas — that the
    dispatcher can't drive. They instead call this to decide which legs run, then gate their existing
    SF write on the first bool and a write_raw_rows_s3(source, rows, mode='append') mirror on the
    second. Default 'snowflake' → (True, False) = importing/running the writer is unchanged until the
    operator opts in (mirror of odds_api_ingestion._lakehouse_write_mode)."""
    mode = (mode or os.environ.get("LAKEHOUSE_RAW_WRITE_MODE", "snowflake")).lower()
    if mode not in _VALID_MODES:
        raise ValueError(f"LAKEHOUSE_RAW_WRITE_MODE='{mode}' invalid; expected one of {sorted(_VALID_MODES)}")
    return (mode in ("snowflake", "both"), mode in ("s3", "both"))


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
