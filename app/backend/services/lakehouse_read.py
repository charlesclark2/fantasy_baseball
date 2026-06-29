"""app/backend/services/lakehouse_read.py   (E11.1-W7b)

Backend-local DuckDB-over-S3 read layer — the **cold last-resort** for the live
FastAPI routers when BOTH the DynamoDB serving cache AND the S3 JSON cache miss.
It reads the lakehouse parquet DIRECTLY (DuckDB + httpfs) instead of through the
(now-being-decommissioned) Snowflake `lakehouse_ext.*` external-table views, so the
request path becomes ZERO-Snowflake.

⚠️ This is a SIBLING COPY of scripts/utils/lakehouse_read.py (the canonical
prediction-path reader). The backend ships a thin Lambda bundle and CANNOT import
scripts/, so the helper is duplicated here (same pattern as
backfill_line_movement_series.py). Keep the two in sync — same functions:
duck_connect / register_views / strip_fqn / to_duckdb_param_sql / referenced_tables /
query_upper. The backend adds two things the scripts copy doesn't need:
  • a module-level CACHED singleton connection (the Lambda container is reused across
    invocations, so build the DuckDB connection + register the views ONCE per warm
    container, not per request), and
  • a defensive top-level `lakehouse_query(sql, params)` that returns UPPERCASE-keyed
    dicts (a near drop-in for snowflake.execute_query) and NEVER raises: on any
    DuckDB/S3/import failure it logs and returns [] so a last-resort miss still 200s
    with an empty/empty-shell response (never a 500).

Snowflake-FREE: needs AWS creds only (DuckDB credential_chain = the Lambda execution
role). Importing this module does NOT import snowflake.connector. `duckdb` itself is
imported LAZILY (inside duck_connect) and guarded so that if the wheel is somehow
absent from the bundle the last-resort logs+returns [] rather than 500-ing the whole
router import.
"""
from __future__ import annotations

import logging
import re
import threading

logger = logging.getLogger(__name__)

# ── S3 lakehouse locations (mirror scripts/utils/lakehouse_read.py + dbt lakehouse macros) ──
BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
LAKEHOUSE_RAW = f"{BUCKET}/baseball/lakehouse_raw"
S3_REGION = "us-east-2"  # lakehouse bucket region (DIFFERENT from the us-east-1 JSON-cache bucket)

# Snowflake schema prefixes that address a lakehouse table by its BARE model name.
# The lakehouse stores every table at {LAKEHOUSE}/<bare_name>/... regardless of which
# Snowflake schema the native table lived in, so a read repoint = strip the prefix.
# NOTE vs the scripts copy: the backend's daily_model_predictions reference is
# schema-qualified as betting_ml / betting_ml_dev (see picks.py _ML_SCHEMA and
# performance.py), so BOTH of those prefixes are listed here.
_FQN_PREFIXES = (
    "baseball_data.betting_features.",
    "baseball_data.betting_ml_dev.",
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
# dates/timestamps as VARCHAR / loose types; mirror scripts/utils/lakehouse_read._TYPED_VIEWS).
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
    """The canonical DuckDB connection for backend last-resort reads: httpfs + icu, the
    S3 credential-chain secret (Lambda execution role), UTC tz, and transient-timeout
    hardening. AWS creds only — no Snowflake env. ``duckdb`` is imported here (lazy) so a
    missing wheel surfaces as a caught ImportError, not an import-time router crash."""
    import duckdb  # lazy import — see module docstring

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    try:
        conn.execute("INSTALL icu; LOAD icu")  # AT TIME ZONE / tz casts in the odds reads
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
    writers emit — flat ``data.parquet``/``part-0.parquet`` (``**`` matches zero subdirs),
    year-partitioned ``year=YYYY/*.parquet`` (pitch marts / stg_batter_pitches), and the
    W6 date-bucket split ``_history``/``_current`` (mart_odds_outcomes) in ONE read — so
    there is no fixed per-table layout list to drift. ``union_by_name=true`` tolerates
    benign column-order/superset differences across buckets.

    ⚠️ Intraday freshness (W7b note): stg_statsapi_games' source monthly_schedule is
    re-flattened to the SAME S3 path by the 30-min intraday re-export, so a fresh read
    just re-globs the live dir — no special-casing needed (the glob points at the live
    path). This is what makes the bets.py auto-void read pick up postponements promptly."""
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
    paramstyle) are handled by ``_duck_dialect_fix`` / ``to_duckdb_param_sql`` below."""
    out = sql
    for prefix in _FQN_PREFIXES:
        out = out.replace(prefix, "")
    return out


_PARAM_RE = re.compile(r"%\((\w+)\)s")


def to_duckdb_param_sql(sql: str) -> str:
    """Translate Snowflake pyformat params ``%(name)s`` → DuckDB named params ``$name``.
    DuckDB's Python API binds ``$name`` from a dict passed to ``execute`` — the SAME dict
    the Snowflake DictCursor took, so callers pass the SAME params unchanged."""
    return _PARAM_RE.sub(r"$\1", sql)


# ── Duck-only dialect fixers ──────────────────────────────────────────────────
# These rewrite Snowflake-only tokens that survive in a few router constants which are
# now ONLY executed via DuckDB (Snowflake is being decommissioned). Applied centrally so
# the router SQL constants need not be hand-edited (and stay readable). Each is safe to
# run on already-cross-dialect SQL (no-op if the token is absent).
_DATEADD_RE = re.compile(
    r"DATEADD\(\s*(\w+)\s*,\s*(-?\d+)\s*,\s*([^,()]+?)\s*\)", re.IGNORECASE
)
_IFF_RE = re.compile(r"\bIFF\s*\(", re.IGNORECASE)
_YEAR_RE = re.compile(r"\bYEAR\s*\(\s*([^()]+?)\s*\)", re.IGNORECASE)
_TS_NTZ_RE = re.compile(r"::\s*TIMESTAMP_NTZ\b", re.IGNORECASE)
_FLOAT_CAST_RE = re.compile(r"::\s*FLOAT\b", re.IGNORECASE)


def _duck_dialect_fix(sql: str) -> str:
    """Rewrite Snowflake-dialect tokens DuckDB won't accept into cross/duck-dialect SQL.

    Covered (the only tokens present in the converted router constants):
      • DATEADD(unit, n, expr)  → (expr + INTERVAL (n) unit)   [day offsets in featured/history]
      • IFF(                    → IF(                            [_STARTERS is_opener]
      • YEAR(x)                 → EXTRACT(year FROM x)           [season/year filters]
      • ::TIMESTAMP_NTZ         → ::timestamp                    [_BOVADA_LINES pre-game filter]
      • ::FLOAT                 → ::double  (DuckDB FLOAT = 32-bit; W6 lesson)
    MEDIAN / QUALIFY / ROW_NUMBER / CASE / COALESCE / NULLIF / ABS / POWER / AVG / regexp_replace
    all parse natively on DuckDB and are left untouched."""
    out = sql
    out = _DATEADD_RE.sub(r"(\3 + INTERVAL (\2) \1)", out)
    out = _IFF_RE.sub("IF(", out)
    out = _YEAR_RE.sub(r"EXTRACT(year FROM \1)", out)
    out = _TS_NTZ_RE.sub("::timestamp", out)
    out = _FLOAT_CAST_RE.sub("::double", out)
    return out


def referenced_tables(*sqls: str) -> list[str]:
    """Best-effort list of the bare lakehouse table names referenced across one or more
    Snowflake queries (scans for ``baseball_data.<schema>.<table>`` / ``<schema>.<table>``).
    Lets a caller register exactly the views a query set needs without hand-maintaining a
    fixed list — the W7b 'grep the live reads, don't trust a fixed list' discipline in code."""
    pat = re.compile(
        r"(?:baseball_data\.)?(?:betting_features|betting_ml_dev|betting_ml|betting|statsapi|config|lakehouse_ext)"
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
    DictCursor contract (consumers index ``r["GAME_PK"]``). Strips FQNs + applies the
    duck-dialect fix + translates the paramstyle; the caller must have registered the
    referenced views. ``params`` is the SAME dict the Snowflake call used."""
    # Order matters: translate the paramstyle FIRST so the dialect fixers see ``$today``
    # (no parens) instead of ``%(today)s`` — otherwise DATEADD(day, -1, %(today)s::DATE)
    # wouldn't match the DATEADD rewrite (its expr-group excludes parens).
    duck_sql = _duck_dialect_fix(to_duckdb_param_sql(strip_fqn(sql)))
    cur = conn.execute(duck_sql, params) if params else conn.execute(duck_sql)
    return _upper_records(cur)


# ── Cached singleton connection (one DuckDB conn + view registration per warm Lambda) ──
# All bare table names referenced by ANY converted router SQL constant. Discovered with
# referenced_tables() over the live router source at module-import time (below) so the
# set stays honest, but we keep an explicit fallback list in case a constant's schema
# prefix changes. Registration is idempotent.
_conn = None
_conn_lock = threading.Lock()
_registered: set[str] = set()


def _get_conn():
    """Return the process-wide cached DuckDB connection, building it (and the httpfs/S3
    secret) on first use. Returns None if DuckDB cannot be imported/initialised so callers
    degrade to an empty result instead of raising at the router level."""
    global _conn
    if _conn is not None:
        return _conn
    with _conn_lock:
        if _conn is None:
            _conn = duck_connect()
    return _conn


def lakehouse_query(sql: str, params: dict | None = None) -> list[dict]:
    """Near drop-in for snowflake.execute_query(sql, params): runs the (Snowflake-dialect)
    SQL against the S3 lakehouse via the cached DuckDB connection and returns UPPERCASE-keyed
    dicts. Lazily registers any views the query references that aren't registered yet.

    DEFENSIVE: never raises. On a DuckDB/import/S3 failure it logs at WARNING and returns
    [] so a cold last-resort miss still 200s with an empty/empty-shell response. Callers may
    keep their existing try/except (defence in depth) — this just guarantees they never see
    a 500 from the last-resort path itself."""
    try:
        conn = _get_conn()
        if conn is None:
            return []
        needed = referenced_tables(sql)
        missing = [t for t in needed if t not in _registered]
        if missing:
            with _conn_lock:
                # re-check under lock; register only the still-missing views
                missing = [t for t in needed if t not in _registered]
                if missing:
                    register_views(conn, missing)
                    _registered.update(missing)
        return query_upper(conn, sql, params)
    except Exception:  # noqa: BLE001 — last-resort must never 500
        logger.warning("lakehouse_query (DuckDB/S3 last-resort) failed; returning []", exc_info=True)
        return []
