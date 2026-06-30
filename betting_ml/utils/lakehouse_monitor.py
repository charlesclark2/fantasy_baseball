"""E11.1-W12 — Snowflake-free DuckDB-over-S3 read layer for the monitoring sensors.

The Dagster monitoring sensors run IN-PROCESS in the code location, so they may import
ONLY packaged code (the betting_ml wheel / pipeline) — never ``scripts/`` (the
``feedback_dagster_import_only_packaged_code`` rule). The canonical prediction-path reader
``scripts/utils/lakehouse_read.py`` therefore cannot be imported from a sensor; this module
is its minimal, package-resident sibling for the sensor / monitoring reads.

Why this wave exists (INC-21 / the empty-dashboard class). Pre-W12 every sensor read the
warehouse via ``betting_ml.utils.data_loader.get_snowflake_connection()`` — or, worse, a raw
``open(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"])`` (``odds_current_rebuild_sensor`` /
``check_games_today``). On the EC2 box the Snowflake key is an INLINE env var
(``SNOWFLAKE_PRIVATE_KEY``) that ``pipeline.resources`` materializes to
``/tmp/snowflake_rsa_key.pem`` at import while *unconditionally* setting
``SNOWFLAKE_PRIVATE_KEY_PATH`` to that path. So any gap in that materialization (empty/absent
inline key, or a transient connect failure) makes the slate-reading sensors throw — and every
one of them swallows the throw into a ``SkipReason`` (fail-open), so the odds rebuild silently
never fires and the dashboard goes empty with NO alert. This module reads the SAME S3 lakehouse
the serving path already uses, via DuckDB's instance-role ``credential_chain`` — no Snowflake,
no key file, no inline-key dependency — removing that whole failure mode.

Snowflake-FREE: imports ``duckdb`` (a ``betting_ml`` dependency, available in the code-location
env) + stdlib only. Never imports ``snowflake.connector`` or ``scripts.*``. The lakehouse S3
locations + region mirror ``scripts/utils/lakehouse_read.py`` / ``dbt/macros/lakehouse.sql``.
"""
from __future__ import annotations

import re

# ── S3 lakehouse locations (mirror scripts/utils/lakehouse_read.py) ──────────────
BUCKET = "s3://baseball-betting-ml-artifacts"
LAKEHOUSE = f"{BUCKET}/baseball/lakehouse"
LAKEHOUSE_RAW = f"{BUCKET}/baseball/lakehouse_raw"
S3_REGION = "us-east-2"  # the lakehouse bucket's region (DuckDB needs it explicitly)

# Tables materialized under lakehouse_raw/ (raw-ingestion exports) rather than lakehouse/.
_RAW_TABLES = frozenset({
    "mlb_odds_raw",
    "monthly_schedule",
    "mlb_events_raw",
    "derivative_odds_raw",
    "venues_raw",
})


def lh(table: str) -> str:
    """Glob path for a lakehouse mart/feature/staging table (flat or year-partitioned)."""
    return f"{LAKEHOUSE}/{table}/**/*.parquet"


def lh_raw(table: str) -> str:
    """Glob path for a ``lakehouse_raw/`` raw-ingestion export table."""
    return f"{LAKEHOUSE_RAW}/{table}/**/*.parquet"


def lh_year(table: str, year: int) -> str:
    """Glob path scoped to one ``year=YYYY/`` hive partition of a partitioned lakehouse
    table (e.g. ``stg_batter_pitches``). Reading the single partition avoids a metadata
    scan across every season's parquet (10s → ~2s for the pitch table)."""
    return f"{LAKEHOUSE}/{table}/year={int(year)}/**/*.parquet"


def table_glob(table: str) -> str:
    """Glob path for ``table``, auto-routing the raw-ingestion tables to ``lakehouse_raw/``."""
    return lh_raw(table) if table in _RAW_TABLES else lh(table)


def is_missing_glob(exc: Exception) -> bool:
    """True if ``exc`` is DuckDB's 'no files match this glob' IOException — i.e. the partition
    simply isn't there yet (e.g. a year= partition before its first export), which a presence
    check should read as 'no data' (return 0/empty), NOT a transient read failure. Use to
    distinguish 'absent partition → False' from a genuine S3 error that should propagate."""
    return "No files found that match the pattern" in str(exc)


def duck():
    """A configured, Snowflake-free DuckDB connection for monitoring reads.

    httpfs + icu, UTC tz, the S3 ``credential_chain`` secret (resolves the EC2 instance role;
    locally resolves the ambient AWS creds), and the W4 transient-timeout hardening. AWS creds
    only — no Snowflake env. Mirrors ``scripts/utils/lakehouse_read.duck_connect``. The caller
    owns the connection and should ``close()`` it (a fresh connect per sensor tick is cheap and
    keeps ticks isolated)."""
    import duckdb

    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs")
    try:
        conn.execute("INSTALL icu; LOAD icu")  # for any AT TIME ZONE / tz-aware reads
    except Exception:  # noqa: BLE001 — extension may be vendored already
        pass
    for pragma in ("SET TimeZone='UTC'", "SET preserve_insertion_order=false"):
        try:
            conn.execute(pragma)
        except Exception:  # noqa: BLE001
            pass
    conn.execute(
        f"CREATE OR REPLACE SECRET baseball_monitor_s3 "
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


# ── Snowflake-cursor-compatible adapter ──────────────────────────────────────────
# Used ONLY where pre-existing Snowflake SELECT SQL must run UNCHANGED against the S3
# lakehouse — specifically betting_ml.monitoring.model_health_metrics.evaluate(), which
# takes a `conn`, calls conn.cursor().execute(sql, params), and uses iff()/%(name)s. The
# simple sensors do NOT use this — they were rewritten DuckDB-native (duck() + read_parquet).
_PARAM_RE = re.compile(r"%\((\w+)\)s")
_IFF_RE = re.compile(r"\biff\s*\(", re.IGNORECASE)
# A schema-qualified table reference. Capture the bare table name so it resolves to the
# DuckDB view we register for it.
_SCHEMAS = (
    "betting_features|betting_ml_dev|betting_ml|betting|statsapi|config|"
    "lakehouse_ext|savant|oddsapi|external|fangraphs|actionnetwork|parlayapi"
)
_FQN_RE = re.compile(rf"\bbaseball_data\.(?:{_SCHEMAS})\.([a-zA-Z_][a-zA-Z0-9_]*)")
_TABLE_REF_RE = re.compile(rf"(?:baseball_data\.)?(?:{_SCHEMAS})\.([a-zA-Z_][a-zA-Z0-9_]*)")


def referenced_tables(sql: str) -> list[str]:
    """Bare lakehouse table names referenced by ``sql`` (grep-derived, order-preserving)."""
    return list(dict.fromkeys(_TABLE_REF_RE.findall(sql)))


def translate_sql(sql: str) -> str:
    """Translate the narrow set of Snowflake dialect tokens the monitoring SQL uses to DuckDB:
    the ``%(name)s`` → ``$name`` paramstyle and ``iff(`` → ``if(``. The monitoring queries use
    no other Snowflake-only token — the sensors that DID use DATEDIFF / SYSDATE /
    CONVERT_TIMEZONE / LATERAL FLATTEN were rewritten DuckDB-native, so only model_health's
    iff/paramstyle SQL ever flows through here. Kept deliberately small (not a general
    SF→DuckDB transpiler)."""
    out = _PARAM_RE.sub(r"$\1", sql)
    out = _IFF_RE.sub("if(", out)
    return out


def strip_fqn(sql: str) -> str:
    """Strip the ``baseball_data.<schema>.`` prefix so references resolve to the registered
    bare-name DuckDB views."""
    return _FQN_RE.sub(r"\1", sql)


class _MonitorCursor:
    """A minimal Snowflake-cursor-shaped view over a DuckDB connection — enough of the
    contract (``execute(sql, params)`` / ``description`` / ``fetchone`` / ``fetchall`` /
    ``close``) for ``model_health_metrics`` to run UNCHANGED against the S3 lakehouse."""

    def __init__(self, conn):
        self._conn = conn
        self._rel = None
        self.description = None

    def execute(self, sql, params=None):
        # Register a DuckDB view for every FQN-addressed table so the FQN-stripped SQL resolves.
        for t in referenced_tables(sql):
            self._conn.execute(
                f"CREATE OR REPLACE VIEW {t} AS "
                f"SELECT * FROM read_parquet('{table_glob(t)}', union_by_name=true)"
            )
        duck_sql = strip_fqn(translate_sql(sql))
        self._rel = self._conn.execute(duck_sql, params) if params else self._conn.execute(duck_sql)
        self.description = self._rel.description
        return self

    def fetchone(self):
        return self._rel.fetchone()

    def fetchall(self):
        return self._rel.fetchall()

    def close(self):
        # The DuckDB connection is owned by the MonitorConnection; cursor close is a no-op.
        pass


class MonitorConnection:
    """Snowflake-connection-shaped DuckDB wrapper: ``.cursor()`` returns a ``_MonitorCursor``
    and ``.close()`` closes the underlying DuckDB connection. Use ONLY where pre-existing
    Snowflake SELECT SQL must run unchanged (model_health_metrics); simple sensors use
    ``duck()`` + inline ``read_parquet()`` for clarity."""

    def __init__(self):
        self._conn = duck()

    def cursor(self):
        return _MonitorCursor(self._conn)

    def close(self):
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def monitor_connection() -> MonitorConnection:
    """A Snowflake-connection-shaped DuckDB-over-S3 connection (see ``MonitorConnection``)."""
    return MonitorConnection()
