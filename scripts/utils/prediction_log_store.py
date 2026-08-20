#!/usr/bin/env python3
"""
scripts/utils/prediction_log_store.py   (E11.24 P1)

THE S3 HOME OF `prediction_log` — the single owner of its layout, its write
semantics and its read view.

WHY THIS EXISTS
  `prediction_log` used to live in `baseball_data.config.prediction_log`. It is
  MONITORING substrate, not a serving artifact (`daily_model_predictions` is the
  served table and is untouched by this module) — its only live reader is
  `compute_model_health.py`. Keeping it in Snowflake cost three separate burns:

    1. the per-run `DELETE FROM ... WHERE prediction_date = <date>` was the #2 waker
       on COMPUTE_WH and is structurally irreducible IN PLACE (the lineup sensor fires
       one scoped `predict_today` per completing lineup, so a slate issues ~8-14 of them);
    2. `predict_today._backfill_outcomes()` re-ran six unbounded UPDATE sweeps on EVERY
       predict invocation — 36% of all billable COMPUTE_WH elapsed;
    3. `compute_model_health` read it over Snowflake once a day.

  Moving the whole table to S3 parquet deletes all three at the source.

LAYOUT
  s3://baseball-betting-ml-artifacts/baseball/lakehouse/prediction_log/
      dt=YYYY-MM-DD/part-<uuid>.parquet

  One partition per prediction_date; each WRITE lands a NEW part file. The read view
  collapses part multiplicity — the same append-then-dedup model `lakehouse_raw_writer`
  documents, and the reason this module does NOT read-modify-write a shared object.

WHY APPEND-AND-DEDUP RATHER THAN READ-MODIFY-WRITE
  `services/dagster/dagster.yaml` caps each `concurrency_group` at ONE run but allows
  `max_concurrent_runs: 5` ACROSS groups, so `daily_ingestion_job` (morning predict) and
  `lineup_monitor_job` (the scoped re-scores) can overlap. A read-modify-write of a shared
  date object would silently LOSE one of two overlapping writes. An append has no such
  window: every writer only ever creates its own object.

THE OVERWRITE SEMANTICS, PRESERVED EXACTLY
  The Snowflake writer expressed two shapes and BOTH are load-bearing (they are the
  #885 fix — before it, a scoped run's date-wide DELETE wiped the rest of the slate and
  the log ended each day holding 1-2 games against a 15-game slate):

    · FULL-SLATE run  → date-wide overwrite. Games that dropped off the slate (postponed)
      must LOSE their stale rows. Here: write the new part, then delete the parts that
      were present before it.
    · SCOPED run (`--game-pks`) → replaces ONLY the games that run owns, leaving the rest
      of the slate — and its accumulated actual_outcome / closing_market_prob — intact.

  Append-only cannot express "this run owns game G but produced no row for it" (a scored
  game whose odds vanished) with data rows alone, so a scoped write also emits an
  OWNERSHIP MARKER row per owned game: a row with `market IS NULL`. The view resolves a
  game to the LATEST BATCH THAT OWNED IT and then drops the markers — so a batch replaces
  every row of the games it owns, including replacing them with nothing. That is exactly
  what `DELETE ... WHERE prediction_date=d AND game_pk IN (...)` + `INSERT` did.

TIMESTAMPS ARE ISO STRINGS ON PURPOSE
  `loaded_at` is a fixed-width ISO VARCHAR, not a binary parquet TIMESTAMP — the repo's
  standing cure for "Snowflake misreads binary parquet timestamps" (the W8a 24h outage).
  Nothing builds an external table over this prefix today, but the cure is free and the
  next reader may. Fixed width matters: lexicographic order of these strings IS
  chronological order, which is what the dedup orders by.

AUTH
  boto3 via `make_s3_client()` (instance-role safe — NEVER pass
  `aws_access_key_id=os.environ.get(...)`, the AKID-chain landmine) and DuckDB via the
  `credential_chain` S3 secret in `lakehouse_read.duck_connect()` (REGION us-east-2).

  Snowflake-FREE and betting_ml-FREE: `scripts/utils/` is COPY'd wholesale into the lean
  weather-capture image, which has no betting_ml (the INC-29 guard). Callers pass dates
  in; this module never resolves "today" itself.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

try:  # normal repo layout
    from scripts.utils.lakehouse_read import LAKEHOUSE, duck_connect
    from scripts.utils.lakehouse_raw_writer import make_s3_client
except ImportError:  # pragma: no cover — lean image layout (COPY scripts/utils/ → ./utils/)
    from utils.lakehouse_read import LAKEHOUSE, duck_connect
    from utils.lakehouse_raw_writer import make_s3_client

__all__ = [
    "COLUMNS", "LOC", "TABLE", "partition_prefix", "view_sql", "register_view",
    "normalise_rows", "rows_to_arrow_table", "write_rows", "compact_partition",
    "list_partition_keys", "utc_stamp",
]

TABLE = "prediction_log"
LOC = f"{LAKEHOUSE}/{TABLE}"
BUCKET = "baseball-betting-ml-artifacts"
KEY_PREFIX = f"baseball/lakehouse/{TABLE}"

# The column contract — byte-for-byte the Snowflake DDL's column list plus `loaded_at`
# (which was a DEFAULT CURRENT_TIMESTAMP there and must be explicit here, because it is
# the dedup's ordering key). Order is fixed so every part file has an identical schema.
COLUMNS: tuple[str, ...] = (
    "prediction_date",
    "game_pk",
    "market",
    "model_prob",
    "market_prob_at_prediction",
    "closing_market_prob",
    "actual_outcome",
    "decimal_odds",
    "ev",
    "kelly_fraction",
    "model_version",
    "loaded_at",
)

_FLOAT_COLUMNS = (
    "model_prob", "market_prob_at_prediction", "closing_market_prob",
    "actual_outcome", "decimal_odds", "ev", "kelly_fraction",
)

# Fixed-width so string order == chronological order (see the module docstring).
_STAMP_FMT = "%Y-%m-%d %H:%M:%S.%f"


def utc_stamp(when: datetime | None = None) -> str:
    """The `loaded_at` value for one write. One stamp per WRITE, shared by every row it
    emits — that is what makes a batch identifiable in the view."""
    dt = when or datetime.now(timezone.utc)
    return dt.strftime(_STAMP_FMT)


def partition_prefix(prediction_date) -> str:
    return f"{KEY_PREFIX}/dt={_iso_date(prediction_date)}/"


def _iso_date(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    return date.fromisoformat(str(value)[:10])


# ---------------------------------------------------------------------------
# Read view
# ---------------------------------------------------------------------------

def view_sql(loc: str | None = None) -> str:
    """The canonical SELECT for `prediction_log` — the ONLY definition.

    Resolves each (prediction_date, game_pk) to the latest batch that OWNED it and drops
    that batch's ownership markers. A consumer that globs the parquet without this dedup
    would count every superseded snapshot, so this body is also registered in
    `lakehouse_read._TYPED_VIEWS` — any reader reaching `prediction_log` through
    `register_views()` gets the dedup for free.

    `filename` is the deterministic tiebreak: two batches sharing a `loaded_at` to the
    microsecond is not physically reachable (separate processes, minutes apart), but an
    arbitrary winner is worse than a deterministic one for a monitoring substrate.
    """
    base = loc or LOC
    cols = ", ".join(f"r.{c}" for c in COLUMNS)
    return f"""
SELECT {cols}
FROM (
    SELECT *, filename AS _part
    FROM read_parquet('{base}/**/*.parquet', union_by_name=true, filename=true)
) r
JOIN (
    SELECT prediction_date, game_pk, loaded_at AS _lt, _part AS _pf
    FROM (
        SELECT prediction_date, game_pk, loaded_at, filename AS _part
        FROM read_parquet('{base}/**/*.parquet', union_by_name=true, filename=true)
    )
    QUALIFY row_number() OVER (
        PARTITION BY prediction_date, game_pk
        ORDER BY loaded_at DESC, _part DESC
    ) = 1
) w
  ON  r.prediction_date = w.prediction_date
  AND r.game_pk         = w.game_pk
  AND r.loaded_at       = w._lt
  AND r._part           = w._pf
WHERE r.market IS NOT NULL
""".strip()


def register_view(conn, *, loc: str | None = None, name: str = TABLE) -> bool:
    """Register `prediction_log` as a DuckDB view. Returns False (and registers an EMPTY
    typed relation) when the prefix holds no parquet yet.

    DuckDB BINDS a parquet view at CREATE time, so a plain CREATE VIEW over an absent
    prefix raises immediately and would take the whole connection down (the E11.24-Bundle
    lesson). Before the operator's one-time history migration this prefix is empty, and a
    monitoring read must degrade to "no rows", never to a crash.
    """
    try:
        conn.execute(f"CREATE OR REPLACE VIEW {name} AS {view_sql(loc=loc)}")
        return True
    except Exception:  # noqa: BLE001 — an absent/empty prefix is the expected case here
        empty = ", ".join(
            f"{_empty_expr(c)} AS {c}" for c in COLUMNS
        )
        conn.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT {empty} WHERE false")
        return False


def _empty_expr(col: str) -> str:
    if col == "prediction_date":
        return "CAST(NULL AS DATE)"
    if col == "game_pk":
        return "CAST(NULL AS BIGINT)"
    if col in _FLOAT_COLUMNS:
        return "CAST(NULL AS DOUBLE)"
    return "CAST(NULL AS VARCHAR)"


# ---------------------------------------------------------------------------
# Row normalisation (PURE — the unit-testable core)
# ---------------------------------------------------------------------------

def normalise_rows(
    rows,
    prediction_date,
    *,
    loaded_at: str,
    scoped_game_pks=None,
) -> tuple[list[dict], list[int]]:
    """Turn a writer's row dicts into the exact parquet row set for one batch.

    Returns ``(parquet_rows, dropped_game_pks)``. A scoped batch is suffixed with one
    ownership MARKER row (``market IS NULL``) per owned game — including games that
    produced no data row, which is precisely how "this run scored the game and it has no
    loggable market" survives an append-only store.

    A row whose game_pk could not be coerced to an int is DROPPED and reported: the
    Snowflake column was ``INTEGER NOT NULL``, so such a row could never have been
    inserted — dropping it loudly is the same outcome without the HALT.
    """
    pdate = _as_date(prediction_date)
    out: list[dict] = []
    dropped: list[int] = []
    for r in rows:
        pk = _coerce_pk(r.get("game_pk", r.get("game_key")))
        if pk is None:
            dropped.append(r.get("game_key"))
            continue
        out.append({
            "prediction_date":           pdate,
            "game_pk":                   pk,
            "market":                    _str_or_none(r.get("market")),
            "model_prob":                _float_or_none(r.get("model_prob")),
            "market_prob_at_prediction": _float_or_none(r.get("market_prob_at_prediction")),
            "closing_market_prob":       _float_or_none(r.get("closing_market_prob")),
            "actual_outcome":            _float_or_none(r.get("actual_outcome")),
            "decimal_odds":              _float_or_none(r.get("decimal_odds")),
            "ev":                        _float_or_none(r.get("ev")),
            "kelly_fraction":            _float_or_none(r.get("kelly_fraction")),
            "model_version":             _str_or_none(r.get("model_version")),
            "loaded_at":                 r.get("loaded_at") or loaded_at,
        })

    for pk in _int_list(scoped_game_pks):
        out.append({
            **{c: None for c in COLUMNS},
            "prediction_date": pdate,
            "game_pk": pk,
            "market": None,          # the ownership marker
            "loaded_at": loaded_at,
        })
    return out, dropped


def _coerce_pk(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # NaN → NULL


def _str_or_none(value):
    return None if value is None else str(value)


def _int_list(values) -> list[int]:
    if not values:
        return []
    seen: dict[int, None] = {}
    for v in values:
        pk = _coerce_pk(v)
        if pk is not None:
            seen.setdefault(pk, None)
    return list(seen)


# ---------------------------------------------------------------------------
# Parquet / S3
# ---------------------------------------------------------------------------

def _arrow_schema():
    import pyarrow as pa
    fields = []
    for col in COLUMNS:
        if col == "prediction_date":
            fields.append(pa.field(col, pa.date32()))
        elif col == "game_pk":
            fields.append(pa.field(col, pa.int64()))
        elif col in _FLOAT_COLUMNS:
            fields.append(pa.field(col, pa.float64()))
        else:
            fields.append(pa.field(col, pa.string()))
    return pa.schema(fields)


def rows_to_arrow_table(rows):
    """Explicit schema, always — an inferred schema turns an all-NULL column (a fresh
    slate's `actual_outcome`) into arrow `null` type, which then collides with a typed
    column in another part file under `union_by_name`."""
    import pyarrow as pa
    schema = _arrow_schema()
    cols = {c: [r.get(c) for r in rows] for c in COLUMNS}
    return pa.Table.from_pydict(cols, schema=schema)


def _put_part(s3, rows, prediction_date) -> str:
    import io
    import pyarrow.parquet as pq

    buf = io.BytesIO()
    pq.write_table(rows_to_arrow_table(rows), buf, compression="snappy")
    key = f"{partition_prefix(prediction_date)}part-{uuid.uuid4().hex}.parquet"
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    return key


def list_partition_keys(prediction_date, *, s3=None) -> list[str]:
    s3 = s3 or make_s3_client()
    prefix = partition_prefix(prediction_date)
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                keys.append(obj["Key"])
    return keys


def _delete_keys(s3, keys) -> None:
    for key in keys:
        s3.delete_object(Bucket=BUCKET, Key=key)


def write_rows(
    rows,
    prediction_date,
    *,
    scoped_game_pks=None,
    loaded_at: str | None = None,
    s3=None,
) -> dict:
    """Write ONE batch of prediction_log rows.

    ``scoped_game_pks`` falsy  → FULL-SLATE overwrite of the date partition.
    ``scoped_game_pks`` given  → append a batch that owns exactly those games.

    The full-slate path lists the existing parts FIRST, writes the new one, and only then
    deletes the listed keys — so the served date is never momentarily empty, and a part
    appended by an overlapping scoped run mid-flight is not collateral damage.
    """
    stamp = loaded_at or utc_stamp()
    parquet_rows, dropped = normalise_rows(
        rows, prediction_date, loaded_at=stamp, scoped_game_pks=scoped_game_pks
    )
    s3 = s3 or make_s3_client()
    scoped = bool(_int_list(scoped_game_pks))

    stale_keys = [] if scoped else list_partition_keys(prediction_date, s3=s3)
    key = _put_part(s3, parquet_rows, prediction_date) if parquet_rows else None
    if stale_keys:
        _delete_keys(s3, stale_keys)

    return {
        "key": key,
        "rows": len(parquet_rows),
        "data_rows": sum(1 for r in parquet_rows if r["market"] is not None),
        "markers": sum(1 for r in parquet_rows if r["market"] is None),
        "cleared_parts": len(stale_keys),
        "dropped_game_keys": dropped,
        "loaded_at": stamp,
        "scoped": scoped,
    }


def compact_partition(rows, prediction_date, *, replace_keys, s3=None) -> dict:
    """Replace a date partition with ``rows`` (already deduped + enriched).

    ``replace_keys`` MUST be the key list read BEFORE the rows were computed: only those
    are deleted, so a part appended after the read survives. Row `loaded_at` values are
    carried through unchanged — the batch identity that the view resolves on is history,
    not something a compaction gets to restamp.
    """
    s3 = s3 or make_s3_client()
    key = _put_part(s3, list(rows), prediction_date) if rows else None
    _delete_keys(s3, list(replace_keys))
    return {"key": key, "rows": len(rows), "replaced_parts": len(list(replace_keys))}


def connect():
    """A DuckDB connection with `prediction_log` registered. Snowflake-free."""
    conn = duck_connect()
    register_view(conn)
    return conn
