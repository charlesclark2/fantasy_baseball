#!/usr/bin/env python3
"""
scripts/utils/lakehouse_read.py   (E11.1-W7b)

Canonical DuckDB-over-S3 read layer for the PREDICTION / SERVING path — the single
source of truth that lets `write_serving_store.py`, `predict_today.py` /
`betting_ml/utils/data_loader.py`, the feature export-mirror, and the W7b parity
tooling read the lakehouse parquet DIRECTLY (DuckDB) instead of through Snowflake
`lakehouse_ext.*` external-table views.

WHY a shared module: W7a's lesson — every prior wave grew its own `_get_duckdb` /
`_register_s3_views` / `_duck_sql_for` triplet and they drifted (4 latent bugs surfaced
when W7a finally exercised the `--s3` write path). The prediction path is the highest
blast-radius surface in the program, so its reads go through ONE helper: one connection
setup, one view-registration that knows the partitioned (mart_odds_outcomes _history/
_current) + typed (daily_model_predictions, odds_snapshots_historical) layouts, one
FQN-strip, one UPPERCASE-dict fetch (to match the Snowflake DictCursor contract every
write_serving_store / router consumer assumes).

⚠️ Snowflake-FREE: needs AWS creds only (DuckDB credential_chain). Importing this module
does NOT pull in pipeline.resources / snowflake.connector, so it is safe to use from
write_serving_store.py without re-introducing the import-time Snowflake env dependency.

The backend (app/backend) cannot import scripts/ (it ships a thin Lambda bundle), so it
carries a sibling copy at app/backend/services/lakehouse_read.py — keep the two in sync
(same as backfill_line_movement_series.py duplicates the series builders for the same reason).
"""
from __future__ import annotations

import re

# E11.20: the Delta rollout registry (PURE stdlib — keeps this module's "importing pulls
# in no Snowflake/heavy deps" contract intact). Under LAKEHOUSE_DELTA_W1=cutover the W1
# pitch marts resolve via delta_scan instead of the frozen legacy parquet glob.
# Imported from the scripts/utils SIBLING home (byte-identical to
# betting_ml/utils/delta_lakehouse.py, guard-tested) — the lean capture images COPY
# scripts/utils/ wholesale, so this file may not carry a betting_ml import node
# (test_lean_capture_images_selfcontained / INC-29 class).
# ⚠️ The backend sibling copy (app/backend/services/lakehouse_read.py) intentionally does
# NOT carry this branch: the Lambda bundle cannot import scripts/betting_ml, and no
# Delta-backed table is backend-served today — revisit if a phase-2 family adds one.
try:
    from scripts.utils.delta_lakehouse import (
        delta_read_enabled,
        delta_scan_view_sql,
        delta_w1_mode,
    )
except ImportError:  # pragma: no cover — lean image layout (COPY scripts/utils/ → ./utils/)
    from utils.delta_lakehouse import (
        delta_read_enabled,
        delta_scan_view_sql,
        delta_w1_mode,
    )

# ── S3 lakehouse locations (mirror dbt/macros/lakehouse.sql + run_w1_lakehouse.py) ──
BUCKET        = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE     = f"{BUCKET}/baseball/lakehouse"
LAKEHOUSE_RAW = f"{BUCKET}/baseball/lakehouse_raw"
S3_REGION     = "us-east-2"   # lakehouse bucket region for the DuckDB S3 secret

# Snowflake schema prefixes that address a lakehouse table by its BARE model name.
# The lakehouse stores every table at {LAKEHOUSE}/<bare_name>/... regardless of which
# Snowflake schema the native table lived in, so a read repoint = strip the prefix.
_FQN_PREFIXES = (
    "baseball_data.betting_features.",
    "baseball_data.betting_ml_dev.",   # predict_today writes/reads via {_ML_SCHEMA} = betting_ml[_dev]
    "baseball_data.betting_ml.",
    "baseball_data.betting.",
    "baseball_data.statsapi.",
    "baseball_data.config.",
    "baseball_data.lakehouse_ext.",
    # bare-schema forms (some queries omit the database)
    "betting_features.",
    "betting_ml_dev.",
    "betting_ml.",
    "lakehouse_ext.",
)

# Tables whose parquet needs explicit type casts on read (the flat-export writers store
# dates/timestamps as VARCHAR / loose types; mirror run_w1_lakehouse._build_w6_precursor_views).
_TYPED_VIEWS: dict[str, str] = {
    "daily_model_predictions": (
        "SELECT * REPLACE ("
        "  score_date::date         AS score_date,"
        "  game_date::date          AS game_date,"
        "  inserted_at::timestamp   AS inserted_at,"
        "  game_datetime::timestamp AS game_datetime"
        ") FROM read_parquet('{loc}', union_by_name=true)"
    ),
    "odds_snapshots_historical": (
        "SELECT * REPLACE ("
        "  snapshot_ts::timestamptz AS snapshot_ts,"
        "  game_date::date          AS game_date,"
        "  loaded_at::timestamptz   AS loaded_at"
        ") FROM read_parquet('{loc}', union_by_name=true)"
    ),
}


def duck_connect():
    """The canonical DuckDB connection for prediction-path reads: httpfs + icu, the S3
    credential-chain secret, UTC tz, and the W4 transient-timeout hardening. AWS creds
    only — no Snowflake env. Mirrors run_w1_lakehouse.run() / backfill_line_movement_series."""
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    try:
        conn.execute("INSTALL icu; LOAD icu")  # AT TIME ZONE in the odds/CLV reads
    except Exception:  # noqa: BLE001
        pass
    for pragma in (
        "SET TimeZone='UTC'",
        "SET preserve_insertion_order=false",
    ):
        try:
            conn.execute(pragma)
        except Exception:  # noqa: BLE001
            pass
    conn.execute(
        f"CREATE OR REPLACE SECRET baseball_s3 "
        f"(TYPE S3, PROVIDER credential_chain, REGION '{S3_REGION}')"
    )
    # E11.20: under Delta CUTOVER the W1 views resolve via delta_scan — the read-only
    # `delta` extension must load, and a failure must be LOUD (a silent fallback to the
    # frozen parquet is the INC-31 stale-key class). Under off/mirror nothing reads
    # Delta, so a pre-Delta image stays green.
    if delta_w1_mode() == "cutover":
        conn.execute("INSTALL delta; LOAD delta")
    for pragma in (
        "SET http_timeout = 600000",
        "SET http_retries = 8",
        "SET http_retry_wait_ms = 500",
        "SET http_retry_backoff = 4",
    ):
        try:
            conn.execute(pragma)
        except Exception:  # noqa: BLE001
            pass
    return conn


def _view_sql(table: str) -> str:
    """The CREATE-VIEW body for one lakehouse table.

    The universal glob ``<table>/**/*.parquet`` matches every layout the lakehouse
    writers emit — flat ``data.parquet`` / ``part-0.parquet`` (``**`` matches zero
    subdirs), year-partitioned ``year=YYYY/*.parquet`` (W1 pitch marts / stg_batter_pitches),
    and the W6 date-bucket split ``_history/data.parquet`` + ``_current/data.parquet``
    (mart_odds_outcomes) in one read — so there is no fixed per-table layout list to drift
    (matches the W7b guidance: don't trust a fixed list). ``union_by_name=true`` tolerates
    benign column-order/superset differences across buckets.

    ⚠️ Intraday freshness (W7b note): stg_statsapi_games' source monthly_schedule is
    re-flattened to the SAME S3 path by the 30-min intraday re-export
    (SCHEDULE_LAKEHOUSE_INTRADAY=1), so a fresh read just re-globs — no special-casing
    needed as long as the glob points at the live path (it does)."""
    if delta_read_enabled(table):
        # E11.20 cutover: Delta-backed table — the legacy parquet glob is FROZEN; the
        # Delta table (ACID, single-writer) is authoritative. delta_scan latency is on
        # par with read_parquet (spike §2).
        return delta_scan_view_sql(table)
    if table in _TYPED_VIEWS:
        return _TYPED_VIEWS[table].format(loc=f"{LAKEHOUSE}/{table}/**/*.parquet")
    return (
        f"SELECT * FROM read_parquet('{LAKEHOUSE}/{table}/**/*.parquet', union_by_name=true)"
    )


def register_views(conn, tables) -> None:
    """Register each bare lakehouse table name as a DuckDB view so an FQN-stripped query
    (``baseball_data.betting.mart_x`` → ``mart_x``) resolves. Idempotent (CREATE OR REPLACE)."""
    for table in dict.fromkeys(tables):  # de-dupe, preserve order
        conn.execute(f"CREATE OR REPLACE VIEW {table} AS {_view_sql(table)}")


def strip_fqn(sql: str) -> str:
    """Strip the ``baseball_data.<schema>.`` / ``<schema>.`` prefixes from a Snowflake query
    so its table references resolve to the registered bare-name DuckDB views. Mechanical and
    safe (only rewrites the schema prefix; leaves SQL logic untouched). Dialect tokens that
    DIFFER between Snowflake and DuckDB (IFF, DATEADD, ::FLOAT vs ::DOUBLE, the %(name)s
    paramstyle) are the caller's responsibility — use `to_duckdb_param_sql` for the paramstyle
    and translate the rest per-query (most prediction-path SQL is already cross-dialect:
    CASE / QUALIFY / ROW_NUMBER / ABS / windowed aggs all parse on both)."""
    out = sql
    for prefix in _FQN_PREFIXES:
        out = out.replace(prefix, "")
    return out


_PARAM_RE = re.compile(r"%\((\w+)\)s")


def to_duckdb_param_sql(sql: str) -> str:
    """Translate Snowflake pyformat params ``%(name)s`` → DuckDB named params ``$name``.
    DuckDB's Python API binds ``$name`` from a dict passed to ``execute`` — same dict the
    Snowflake DictCursor took, so callers pass the SAME params unchanged."""
    return _PARAM_RE.sub(r"$\1", sql)


def referenced_tables(*sqls: str) -> list[str]:
    """Best-effort list of the bare lakehouse table names referenced across one or more
    Snowflake queries (scans for ``baseball_data.<schema>.<table>`` / ``<schema>.<table>``).
    Lets a caller register exactly the views a query set needs without hand-maintaining a
    fixed list — the W7b 'grep the live reads, don't trust a fixed list' discipline in code."""
    pat = re.compile(
        r"(?:baseball_data\.)?(?:betting_features|betting_ml|betting|statsapi|config|lakehouse_ext)"
        r"\.([a-zA-Z_][a-zA-Z0-9_]*)"
    )
    found: list[str] = []
    for sql in sqls:
        for m in pat.finditer(sql):
            found.append(m.group(1).lower())
    return list(dict.fromkeys(found))


def _upper_records(cur) -> list[dict]:
    cols = [d[0].upper() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def query_upper(conn, sql: str, params: dict | None = None) -> list[dict]:
    """Run a query and return rows as UPPERCASE-keyed dicts — matching the Snowflake
    DictCursor contract (consumers index ``r["GAME_PK"]``). Strips FQNs + translates the
    paramstyle; the caller must have registered the referenced views. ``params`` is the
    SAME dict the Snowflake call used (``%(name)s`` → ``$name`` is handled here)."""
    duck_sql = to_duckdb_param_sql(strip_fqn(sql))
    cur = conn.execute(duck_sql, params) if params else conn.execute(duck_sql)
    return _upper_records(cur)


def query_upper_batch(conn, sql_template: str, game_pks) -> list[dict]:
    """DuckDB twin of write_serving_store._sf_query_batch — fills the ``{game_pk_list}``
    placeholder with a comma-joined int list and returns UPPERCASE-keyed dicts."""
    if not game_pks:
        return []
    gp_list = ",".join(str(int(g)) for g in game_pks)
    duck_sql = strip_fqn(sql_template.format(game_pk_list=gp_list))
    cur = conn.execute(duck_sql)
    return _upper_records(cur)
