"""write_serving_store.py
-----------------------
Dagster write-path: queries the prediction/feature data (Snowflake by default, or
the S3 lakehouse via DuckDB with --s3) after predict_today_morning completes,
builds the same JSON payloads FastAPI serves, and writes them to the DynamoDB
serving cache (INC-16-P2; replaces the decommissioned Railway PostgreSQL
api_cache). The DynamoDB schema matches app/backend/services/serving_cache.py:
PK = namespace, SK = "{rest}#{date}" or "{rest}#PERMANENT", value = JSON string.

E11.1-W7b — DuckDB-over-S3 read mode (--s3): with --s3 every READ is served
directly from the S3 lakehouse parquet through DuckDB (scripts/utils/lakehouse_read.py)
instead of Snowflake. This is GATED/TRANSITIONAL: shipped OFF by default; an operator
runs a multi-day parallel comparison (both modes side-by-side) before cutover, so the
Snowflake path stays 100% intact as the instant rollback. There are NO Snowflake WRITES
anywhere here — every write goes to DynamoDB / S3 — so --s3 is a pure read repoint.
In --s3 mode the connection needs AWS creds only (DuckDB credential_chain); the Snowflake
env vars below are NOT required. The two read helpers (_sf_query / _sf_query_batch) detect
a DuckDB connection and route through the shared lakehouse helper, so every call site is
unchanged; a small per-query dialect shim (_duck_dialect) rewrites the handful of
Snowflake-only tokens (IFF, DATEADD, TIMESTAMP_NTZ/TZ casts, ::FLOAT→::DOUBLE) that
DuckDB does not parse — applied ONLY on the DuckDB branch, never to the Snowflake SQL.

Also writes to S3 (the read-order fallback) — DynamoDB → S3 at request time, so
the S3 writes are KEPT (not deprecated). The legacy daily_picks table is retired
(the backend never read it).

Called by write_serving_store_op in pipeline/ops/daily_ingestion_ops.py.

SQL mirrors:
  - picks/today + picks/ev + picks/history + performance/summary:
      write_api_cache.py (kept in sync manually; picks.py is the source of truth
      for game-detail SQL)
  - game detail (12 queries per game batch):
      app/backend/routers/picks.py _*_QUERY constants

Env vars required:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_WAREHOUSE
    SNOWFLAKE_PRIVATE_KEY_PATH  (preferred)  or  SNOWFLAKE_PRIVATE_KEY (PEM/base64)
    SERVING_CACHE_TABLE         (DynamoDB table; default credence-prod-serving-cache)
    AWS_REGION                  (default us-east-1; the EC2 instance role grants access)
    CACHE_BUCKET                (S3 bucket name; optional — skipped if not set)

Exits 0 on full success, 1 if any write fails.
"""

from __future__ import annotations

import argparse
import base64
import decimal
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import boto3
import snowflake.connector
from dotenv import load_dotenv

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from scipy.stats import norm as _scipy_norm

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day
from betting_ml.utils.h2h_probability import devig_home_prob
from betting_ml.utils.totals_probability import devig_over_prob, prob_to_american
from betting_ml.utils.probability_layer import compute_kelly

# Load .env BEFORE importing pipeline.* — pipeline.resources instantiates the
# Snowflake resource at IMPORT time and reads os.environ["SNOWFLAKE_ACCOUNT"]
# eagerly, so the creds must already be present. In dev that means .env; in
# prod/containers the vars are injected and load_dotenv() is a harmless no-op.
load_dotenv()

try:
    from pipeline.utils.alerting import send_alert as _send_alert
except Exception:
    # Catch broadly (not just ImportError): pipeline.resources can raise KeyError
    # at import if Snowflake env vars are absent. Alerting is non-essential to the
    # serving write, so degrade to a no-op rather than crash the whole script.
    def _send_alert(*args, **kwargs):  # type: ignore[misc]
        return False

# A0.4.32 — curated book set (verified live 2026-06-17; Fanatics added E9.14)
_BOOK_DISPLAY: dict[str, str] = {
    "pinnacle": "Pinnacle",
    "betmgm": "BetMGM",
    "caesars": "Caesars",
    "fanduel": "FanDuel",
    "draftkings": "DraftKings",
    "fanatics": "Fanatics",
    "bovada": "Bovada",
}
_BOOK_ORDER = list(_BOOK_DISPLAY.keys())  # Pinnacle first (sharp reference)

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ── Snowflake connection ─────────────────────────────────────────────────────

def _load_private_key() -> bytes:
    pk_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if pk_path:
        with open(pk_path, "rb") as fh:
            pem_bytes = fh.read()
    else:
        key_val = os.environ.get("SNOWFLAKE_PRIVATE_KEY", "").strip()
        if not key_val:
            raise RuntimeError("Neither SNOWFLAKE_PRIVATE_KEY_PATH nor SNOWFLAKE_PRIVATE_KEY is set")
        # INC-16-P2: a Compose env_file can't carry real newlines. Check the
        # \n-escaped form FIRST (it still starts with "-----BEGIN"), then base64.
        if "\\n" in key_val:
            key_val = key_val.replace("\\n", "\n").strip()
        elif not key_val.startswith("-----"):
            key_val = base64.b64decode(key_val).decode("utf-8")
        pem_bytes = key_val.encode("utf-8")
    p_key = serialization.load_pem_private_key(pem_bytes, password=None, backend=default_backend())
    return p_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _sf_connect() -> snowflake.connector.SnowflakeConnection:
    kwargs = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database="baseball_data",
        private_key=_load_private_key(),
    )
    role = os.environ.get("SNOWFLAKE_ROLE")
    if role:
        kwargs["role"] = role
    # E11.3 cost tagging — attribute Snowflake credits to the calling Dagster job.
    job_tag = os.environ.get("DAGSTER_JOB_NAME", "manual")
    env_tag = os.environ.get("TARGET_ENV", "dev")
    kwargs["session_parameters"] = {"QUERY_TAG": f"write_serving_store|{job_tag}|{env_tag}"}
    return snowflake.connector.connect(**kwargs)


# ── E11.1-W7b: DuckDB-over-S3 read mode (gated; --s3) ─────────────────────────
# The connection object threaded through main() is either a Snowflake connection
# (default) or a DuckDB connection (--s3). `_is_duck` lets the two read helpers below
# stay polymorphic so EVERY call site is unchanged — _sf_query / _sf_query_batch route
# a DuckDB handle through the shared lakehouse helper (scripts/utils/lakehouse_read.py),
# otherwise the original Snowflake DictCursor path. There are no Snowflake WRITES here,
# so this is a pure read repoint.


def _is_duck(conn) -> bool:
    """True iff `conn` is a DuckDB connection (the --s3 read mode).

    Note: a DuckDB connection's type module is the C-extension name ``_duckdb`` (leading
    underscore) and its class is ``DuckDBPyConnection`` — so match on both the (underscore-
    stripped) module AND the class name to be robust across DuckDB versions."""
    tp = type(conn)
    mod = (tp.__module__ or "").lstrip("_").lower()
    return mod.startswith("duckdb") or tp.__name__ == "DuckDBPyConnection"


def _duck_dialect(sql: str) -> str:
    """Rewrite the Snowflake-only tokens DuckDB cannot parse — applied ONLY on the DuckDB
    branch, NEVER to the Snowflake SQL (the Snowflake path runs the constants verbatim).

    Cross-dialect-safe rewrites we leave to the constants themselves (CASE / QUALIFY /
    ROW_NUMBER / ABS / COALESCE / SPLIT_PART / MEDIAN / YEAR / windowed aggs / NULLS LAST /
    ::VARCHAR / ::DATE / ::INTEGER all parse on both). What needs rewriting here:
      - ``::TIMESTAMP_NTZ`` → ``::TIMESTAMP``  and  ``::TIMESTAMP_TZ`` → ``::TIMESTAMPTZ``
        (DuckDB has no TIMESTAMP_NTZ/_TZ type names).
      - ``::FLOAT`` → ``::DOUBLE`` (DuckDB ``::FLOAT`` is 32-bit; Snowflake FLOAT is 64-bit —
        ``::DOUBLE`` matches for parity, per the W6 lesson).
      - ``DATEADD(part, n, expr)`` → ``(expr + INTERVAL (n) PART)`` (DuckDB has no DATEADD).
      - ``IFF(cond, a, b)`` → ``CASE WHEN cond THEN a ELSE b END`` (DuckDB has no IFF).
    All verified against DuckDB; the constants are otherwise FQN-stripped + paramstyle-shifted
    by the shared helper. Parenthesis-balanced so nested calls (COALESCE inside IFF, ::DATE
    inside DATEADD) translate cleanly."""
    import re

    out = re.sub(r"::\s*TIMESTAMP_NTZ", "::TIMESTAMP", sql, flags=re.IGNORECASE)
    out = re.sub(r"::\s*TIMESTAMP_TZ", "::TIMESTAMPTZ", out, flags=re.IGNORECASE)
    out = re.sub(r"::\s*FLOAT\b", "::DOUBLE", out, flags=re.IGNORECASE)
    out = _rewrite_call(out, "DATEADD", _dateadd_repl)
    out = _rewrite_call(out, "IFF", _iff_repl)
    return out


def _split_top_args(s: str) -> list[str]:
    """Split a function arg list on top-level commas (respecting nested parens)."""
    args: list[str] = []
    depth = 0
    cur: list[str] = []
    for ch in s:
        if ch == "(":
            depth += 1
            cur.append(ch)
        elif ch == ")":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur))
    return [a.strip() for a in args]


def _rewrite_call(sql: str, name: str, repl_fn) -> str:
    """Replace every top-level ``name(...)`` call via `repl_fn(arg_list) -> str`,
    matching the closing paren by balancing (so nested parens are handled)."""
    import re

    pat = re.compile(r"\b" + name + r"\s*\(", re.IGNORECASE)
    while True:
        m = pat.search(sql)
        if not m:
            return sql
        open_i = m.end() - 1
        depth = 0
        close_i = None
        for i in range(open_i, len(sql)):
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
                if depth == 0:
                    close_i = i
                    break
        if close_i is None:
            return sql  # unbalanced — leave untouched rather than corrupt
        args = _split_top_args(sql[open_i + 1 : close_i])
        replacement = repl_fn(args)
        if replacement is None:  # arity mismatch — leave untouched
            return sql
        sql = sql[: m.start()] + replacement + sql[close_i + 1 :]


def _dateadd_repl(args: list[str]) -> str | None:
    if len(args) != 3:
        return None
    part, n, expr = args
    return f"({expr} + INTERVAL ({n}) {part.upper()})"


def _iff_repl(args: list[str]) -> str | None:
    if len(args) != 3:
        return None
    cond, a, b = args
    return f"CASE WHEN {cond} THEN {a} ELSE {b} END"


def _duck_connect_and_register():
    """E11.1-W7b: build the canonical DuckDB-over-S3 connection (AWS creds only — NO Snowflake
    env) and register a view for EVERY lakehouse table referenced by this module's reads.

    GREP-DRIVEN registration (NOT a fixed list): we scan this module's globals for every
    str constant that contains ``baseball_data.`` (i.e. all the SQL constants) and feed them to
    `referenced_tables`, so a query added by a concurrent app story is auto-covered without
    maintaining a table list here (the W7b 'grep the live reads, don't trust a fixed list'
    discipline).

    RESILIENT registration (W7b is mid-migration): a few referenced tables are not yet in the
    lakehouse (the feature_pregame_* features, mart_bankroll_state, mart_player_profile_identity,
    stg_statsapi_lineups_wide, stg_statsapi_probable_pitchers, team_elo_history — un-migrated
    stragglers, NOT a place to re-add a Snowflake read). `register_views` would raise at
    CREATE-VIEW time on a missing parquet glob and kill the whole --s3 run, so we register
    each view individually and skip the ones with no parquet, logging a loud WARNING that
    names them. Sections that touch only migrated tables (e.g. --picks) then run fine; a
    section that hits a missing table fails LOUDLY with DuckDB's "Table … does not exist"
    (which names the table) and is caught by that section's try/except in main() — exactly
    what the operator's parallel-comparison run needs (run what's ready, see what isn't).
    Returns the registered DuckDB connection."""
    from scripts.utils.lakehouse_read import (  # local import: Snowflake-free, AWS creds only
        duck_connect,
        referenced_tables,
        register_views,
    )

    sql_constants = [
        v for v in globals().values()
        if isinstance(v, str) and "baseball_data." in v
    ]
    tables = referenced_tables(*sql_constants)
    conn = duck_connect()
    registered: list[str] = []
    missing: list[str] = []
    for t in tables:
        try:
            register_views(conn, [t])
            registered.append(t)
        except Exception as exc:  # noqa: BLE001 — missing parquet / un-migrated straggler
            missing.append(t)
            log.debug("Lakehouse view %s not registered (no parquet?): %s", t, exc)
    log.info("DuckDB-over-S3 read mode (--s3): registered %d/%d lakehouse views: %s",
             len(registered), len(tables), ", ".join(sorted(registered)))
    if missing:
        log.warning(
            "DuckDB-over-S3 read mode (--s3): %d referenced table(s) have NO lakehouse "
            "parquet yet (un-migrated W7b stragglers) — any section that reads them will fail "
            "loudly (Table does not exist), not silently: %s",
            len(missing), ", ".join(sorted(missing)),
        )
    return conn


def _sf_query(conn, sql: str, params: dict | None = None) -> list[dict]:
    if _is_duck(conn):
        # --s3: route through the shared lakehouse helper. _duck_dialect handles the
        # Snowflake-only tokens; query_upper does strip_fqn + paramstyle + UPPERCASE dicts.
        from scripts.utils.lakehouse_read import query_upper
        return query_upper(conn, _duck_dialect(sql), params)
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql, params)
    return cur.fetchall()


def _sf_query_batch(conn, sql_template: str, game_pks: list[int]) -> list[dict]:
    """Runs sql_template with {game_pk_list} replaced by the int list. Safe: game_pks are DB integers."""
    if not game_pks:
        return []
    if _is_duck(conn):  # --s3: dialect-shim the template, then the shared batch helper.
        from scripts.utils.lakehouse_read import query_upper_batch
        return query_upper_batch(conn, _duck_dialect(sql_template), game_pks)
    gp_list = ",".join(str(g) for g in game_pks)
    cur = conn.cursor(snowflake.connector.DictCursor)
    cur.execute(sql_template.format(game_pk_list=gp_list))
    return cur.fetchall()


def _alert_empty_serving_date(conn, today: str) -> None:
    """ALERT-loud-but-continue (INC-22): no predictions exist for the resolved serving
    date `today`. This used to be a benign `log.info` — which is exactly how the
    UTC-midnight date-rollover bug HID (the evening intraday write silently skipped the
    live slate). Emit a WARNING (→ stderr → the op's context.log.warning → visible to the
    dead-man monitor) and, when possible, report the latest date predictions DO exist for
    so a date-ahead-of-slate mismatch is self-describing vs. a legit off-day.
    """
    latest = None
    try:
        rows = _sf_query(conn, _LATEST_PREDICTION_DATE_SQL)
        if rows:
            val = next(iter(rows[0].values()))
            latest = val.isoformat() if hasattr(val, "isoformat") else (str(val) if val is not None else None)
    except Exception:  # noqa: BLE001 — diagnostic only; never let it break the (already-empty) serve
        log.debug("Could not look up latest prediction date for the empty-serve alert", exc_info=True)

    if latest and latest < today:
        log.warning(
            "⚠️ INC-22: NO predictions for resolved serving date %s, but predictions exist "
            "through %s — the serving date is AHEAD of the latest slate (likely a TZ/date "
            "rollover, NOT an off-day). picks/today NOT refreshed → app slate will go STALE. "
            "Re-run with --date %s to refresh now.", today, latest, latest,
        )
    else:
        log.warning(
            "⚠️ No predictions for resolved serving date %s — skipping picks/today cache write. "
            "If games are scheduled today this is a MISS (predict_today may not have run, or the "
            "serving date is wrong); the app slate will not refresh. (latest available: %s)",
            today, latest or "unknown",
        )


# ── DynamoDB serving cache (INC-16-P2; replaces the Railway PG api_cache) ──────
# NOTE: the legacy `_pg_*` helper names and the `pg`/`pg_conn` locals are RETAINED
# to keep the diff small across this large writer — but the handle is now a boto3
# DynamoDB Table, not a Postgres connection, and `_pg_set_cache` writes a DynamoDB
# item. The schema mirrors app/backend/services/serving_cache.py exactly so reads
# line up: PK = namespace, SK = "{rest}#{date}" | "{rest}#PERMANENT", value = JSON
# string, plus is_permanent / updated_at / cache_date.

_SERVING_CACHE_TABLE = os.environ.get("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_PERMANENT_SK = "PERMANENT"


def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _split_cache_key(cache_key: str) -> tuple[str, str]:
    """('picks/game/123') → ('picks', 'game/123'); ('foo') → ('foo', '_')."""
    ns, sep, rest = cache_key.partition("/")
    return ns, (rest if sep else "_")


def _pg_connect():
    """Return the boto3 DynamoDB Table for the serving cache, or None on failure.

    (Legacy name; this is a DynamoDB handle.) On the EC2 box the instance-profile
    role grants access — no static creds. None ⇒ writers fall through to S3 only.
    """
    try:
        region = os.environ.get("AWS_REGION", "us-east-1")
        return boto3.resource("dynamodb", region_name=region).Table(_SERVING_CACHE_TABLE)
    except Exception as exc:
        log.warning("DynamoDB resource init failed — serving writes will be S3-only: %s", exc)
        _send_alert(
            "DynamoDB connect failed — serving cache degraded (S3-only)",
            f"boto3 DynamoDB Table init raised: {exc}\n"
            f"Table: {_SERVING_CACHE_TABLE}\n"
            "All serving-cache writes will fall through to S3 until resolved.\n"
            "Check IAM role permissions for credence-prod-serving-cache.",
            severity="ERROR",
            dedup_key="dynamodb-connect-failed",
        )
        return None


def _pg_set_cache(pg, cache_key: str, today: str, payload: dict, is_permanent: bool = False) -> None:
    """Upsert one serving-cache item into DynamoDB. `pg` is the boto3 Table.

    Non-raising: an oversized payload (>400 KB item limit) or any DynamoDB error
    is logged, not raised — the parallel S3 write keeps the key servable via the
    DynamoDB → S3 read fallback.
    """
    ns, rest = _split_cache_key(cache_key)
    sk = f"{rest}#{_PERMANENT_SK}" if is_permanent else f"{rest}#{today}"
    try:
        pg.put_item(Item={
            "pk": ns,
            "sk": sk,
            "value": json.dumps(payload, default=_json_default),
            "is_permanent": is_permanent,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "cache_date": _PERMANENT_SK if is_permanent else today,
        })
    except Exception as exc:
        log.warning("DynamoDB set_cache failed for key=%s (S3 fallback covers): %s", cache_key, exc)
        _send_alert(
            "DynamoDB write failed — serving cache degraded (S3-only)",
            f"put_item raised for cache_key={cache_key!r}: {exc}\n"
            f"Table: {_SERVING_CACHE_TABLE}\n"
            "Serving reads will fall back to S3. If this persists, DynamoDB is degraded.\n"
            "Check IAM role permissions and table health in credence-prod-serving-cache.",
            severity="ERROR",
            dedup_key="dynamodb-write-failed",
        )


# ── S3 write ─────────────────────────────────────────────────────────────────

def _write_s3(bucket: str, key: str, data: dict | list) -> None:
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, default=str),
        ContentType="application/json",
    )
    log.info("Wrote s3://%s/%s", bucket, key)


# ── SQL — bulk endpoint queries (mirrors write_api_cache.py) ─────────────────

_PICKS_TODAY_SQL = """
WITH ranked AS (
    SELECT
        p.*,
        g.game_date                                                          AS game_start_utc,
        MAX(p.meta_p_clv_positive) OVER (PARTITION BY p.game_pk)            AS _meta_p,
        MAX(p.meta_ci_low) OVER (PARTITION BY p.game_pk)                    AS _meta_ci_low,
        MAX(p.meta_ci_high) OVER (PARTITION BY p.game_pk)                   AS _meta_ci_high,
        MAX(p.totals_meta_p_clv_positive) OVER (PARTITION BY p.game_pk)     AS _totals_meta_p,
        MAX(p.totals_meta_ci_low) OVER (PARTITION BY p.game_pk)             AS _totals_meta_ci_low,
        MAX(p.totals_meta_ci_high) OVER (PARTITION BY p.game_pk)            AS _totals_meta_ci_high,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                -- Prefer rows carrying market data so a degraded run (post_lineup
                -- with NULL odds/abstain) never shadows a complete morning row.
                CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_date = %(today)s
      AND p.prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.game_date,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.win_prob_ci_low,
        b.win_prob_ci_high,
        b.win_prob_ci_width,
        b.gate_signals_met,
        b.home_team, b.away_team,
        b.layer4_h2h_decision                        AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        NULL::FLOAT                                  AS model_total_runs,
        NULL::FLOAT                                  AS market_total_line,
        b.prediction_type,
        b._meta_p                                    AS meta_p_clv_positive,
        b._meta_ci_low                               AS meta_ci_low,
        b._meta_ci_high                              AS meta_ci_high
    FROM base b
    WHERE b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk, b.game_date,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus) AS edge,  -- prob-points edge (NOT layer4_totals_over_signal, which is runs: mu - line)
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                  AS win_prob_ci_low,
        NULL::FLOAT                                  AS win_prob_ci_high,
        NULL::FLOAT                                  AS win_prob_ci_width,
        NULL::INTEGER                                AS gate_signals_met,
        b.home_team, b.away_team,
        b.layer4_totals_decision                     AS pick_side,
        b.game_start_utc,
        b.inserted_at,
        b.pred_total_runs                            AS model_total_runs,
        b.total_line_consensus                       AS market_total_line,
        b.prediction_type,
        b._totals_meta_p                             AS meta_p_clv_positive,
        b._totals_meta_ci_low                        AS meta_ci_low,
        b._totals_meta_ci_high                       AS meta_ci_high
    FROM base b
    WHERE b.layer4_totals_decision IN ('over', 'under')
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_start_utc, game_pk, market_type
"""

_EV_TODAY_SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_date = %(today)s
      AND prediction_type IN ('post_lineup', 'morning')
),
base AS (
    SELECT r.*, g.game_date AS game_start_utc
    FROM ranked r
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = r.game_pk
    WHERE r._rn = 1
),
h2h AS (
    SELECT
        b.game_pk, b.game_date, b.game_start_utc,
        'h2h'                                        AS market_type,
        b.calibrated_win_prob                        AS model_prob,
        b.h2h_market_implied_prob                    AS bovada_devig_prob,
        b.layer4_h2h_edge                            AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_h2h_decision <> 'abstain'           AS qualified_bet,
        b.home_team, b.away_team,
        b.h2h_kelly_fraction                         AS kelly_fraction,
        b.total_line_consensus,
        NULL::FLOAT                                  AS pred_total_runs,
        b.prediction_type
    FROM base b
    WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk, b.game_date, b.game_start_utc,
        'totals'                                     AS market_type,
        b.totals_model_prob                          AS model_prob,
        b.over_prob_consensus                        AS bovada_devig_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus) AS edge,  -- prob-points edge (NOT layer4_totals_over_signal, which is runs: mu - line)
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed,
        b.layer4_totals_decision <> 'abstain'        AS qualified_bet,
        b.home_team, b.away_team,
        b.totals_kelly_fraction                      AS kelly_fraction,
        b.total_line_consensus,
        b.pred_total_runs,
        b.prediction_type
    FROM base b
    WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_pk, market_type
"""

_HISTORY_SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                CASE WHEN lineup_confirmed THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_date >= DATEADD(day, -30, CURRENT_DATE)
      AND qualified_bet = TRUE
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.game_date,
        'h2h'                                       AS market_type,
        b.calibrated_win_prob                       AS model_prob,
        b.h2h_market_implied_prob                   AS bovada_devig_prob,
        b.h2h_edge                                  AS edge,
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team, b.away_team, b.inserted_at,
        clv.clv, clv.clv_positive, clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.h2h_edge IS NOT NULL
),
totals AS (
    SELECT
        b.game_pk, b.game_date,
        'totals'                                    AS market_type,
        b.totals_model_prob                         AS model_prob,
        b.over_prob_consensus                       AS bovada_devig_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus) AS edge,  -- prob-points edge (totals_edge is unpopulated upstream)
        b.game_conviction_score,
        b.lineup_confirmed,
        NULL::FLOAT                                 AS win_prob_ci_low,
        NULL::FLOAT                                 AS win_prob_ci_high,
        b.home_team, b.away_team, b.inserted_at,
        clv.clv, clv.clv_positive, clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.totals_model_prob IS NOT NULL AND b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_date DESC, game_pk, market_type
"""

_FRESHNESS_SQL = """
SELECT MAX(inserted_at) AS last_updated_at
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_date = %(today)s
"""

# INC-22 — diagnostic for the ALERT-loud empty-skip: the most recent date predictions
# actually exist for. If this is BEHIND the resolved serving `today`, the serving date
# rolled ahead of the slate (the UTC-midnight bug class) rather than a legit off-day.
# Contains `baseball_data.` so the --s3 grep-driven registration auto-covers it.
_LATEST_PREDICTION_DATE_SQL = """
SELECT MAX(game_date) AS latest_game_date
FROM baseball_data.betting_ml.daily_model_predictions
"""

_BANKROLL_SQL = """
SELECT total_bets, wins, win_rate, mean_clv,
       net_pnl_flat, net_pnl_kelly, sharpe_ratio
FROM baseball_data.betting.mart_bankroll_state
ORDER BY recorded_at DESC LIMIT 1
"""

_CLV_SUMMARY_SQL = """
SELECT
    COUNT(*)                                                       AS total_bets,
    SUM(CASE WHEN actual_outcome = 1 AND clv_positive THEN 1
             WHEN actual_outcome = 0 AND NOT clv_positive THEN 1
             ELSE 0 END)                                           AS wins,
    AVG(clv)                                                       AS mean_clv,
    SUM(CASE WHEN clv_positive THEN 1.0 ELSE -1.0 END)            AS net_pnl_flat
FROM baseball_data.betting.mart_clv_labeled_games
WHERE actual_outcome IS NOT NULL
"""

# ── Game-detail batch queries (source-of-truth: picks.py _*_QUERY constants) ─
# Use {game_pk_list} as a safe integer-list placeholder (filled by _sf_query_batch).

_GAME_STATUS_BATCH = """
SELECT
    g.game_pk,
    g.abstract_game_state,
    g.home_score,
    g.away_score,
    g.home_is_winner,
    g.home_team_name,
    g.away_team_name,
    g.home_wins,
    g.home_losses,
    g.away_wins,
    g.away_losses,
    g.home_team_id,
    g.away_team_id,
    hp.pythagorean_win_exp_30d AS home_pyth_pct,
    hp.pythagorean_residual_30d AS home_pyth_residual,
    ap.pythagorean_win_exp_30d AS away_pyth_pct,
    ap.pythagorean_residual_30d AS away_pyth_residual
FROM baseball_data.betting.stg_statsapi_games g
LEFT JOIN baseball_data.betting.mart_team_pythagorean_rolling hp
    ON hp.game_pk = g.game_pk AND hp.team_id = g.home_team_id
LEFT JOIN baseball_data.betting.mart_team_pythagorean_rolling ap
    ON ap.game_pk = g.game_pk AND ap.team_id = g.away_team_id
WHERE g.game_pk IN ({game_pk_list})
"""

_STARTERS_BATCH = """
WITH game_meta AS (
    -- INC-23: game_date from stg_statsapi_games is an ISO VARCHAR in the S3 lakehouse view
    -- (TIMESTAMP-origin, stringified by the W8a cure) → year(VARCHAR) HALTs DuckDB in --s3 mode.
    -- Cast ::date so game_meta.game_date is a real DATE: it's compared below against
    -- mart_starting_pitcher_game_log.game_date (native DATE in the lakehouse) at
    -- ``g.game_date < gm.game_date`` — a VARCHAR here HALTs with DATE↔VARCHAR. The cast is a
    -- no-op on the native Snowflake DATE/TS. See CLAUDE.md INC-23.
    SELECT game_pk, game_date::date AS game_date, YEAR(game_date::date) AS game_year
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
starters AS (
    SELECT game_pk, side, probable_pitcher_id, probable_pitcher_name
    FROM baseball_data.betting.stg_statsapi_probable_pitchers
    WHERE game_pk IN ({game_pk_list})
    QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk, side ORDER BY ingestion_ts DESC) = 1
),
current_season AS (
    SELECT
        s.game_pk,
        g.pitcher_id,
        COUNT(*) AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2) AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1) AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
    JOIN game_meta gm ON gm.game_pk = s.game_pk
    WHERE g.game_year = gm.game_year
      AND g.game_date < gm.game_date
    GROUP BY s.game_pk, g.pitcher_id
),
prior_season AS (
    SELECT
        s.game_pk,
        g.pitcher_id,
        COUNT(*) AS starts,
        ROUND(SUM(g.runs_allowed) * 9.0 / NULLIF(SUM(g.innings_pitched), 0), 2) AS ra9,
        ROUND((SUM(g.walks) + SUM(g.hits_allowed)) / NULLIF(SUM(g.innings_pitched), 0), 2) AS whip,
        ROUND(SUM(g.strikeouts)::FLOAT / NULLIF(SUM(g.batters_faced), 0) * 100, 1) AS k_pct
    FROM baseball_data.betting.mart_starting_pitcher_game_log g
    JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
    JOIN game_meta gm ON gm.game_pk = s.game_pk
    WHERE g.game_year = gm.game_year - 1
    GROUP BY s.game_pk, g.pitcher_id
),
last5 AS (
    SELECT sub.game_pk, sub.pitcher_id, MEDIAN(sub.innings_pitched) AS median_ip_last5
    FROM (
        SELECT s.game_pk, g.pitcher_id, g.innings_pitched,
               ROW_NUMBER() OVER (PARTITION BY s.game_pk, g.pitcher_id ORDER BY g.game_date DESC) AS rn
        FROM baseball_data.betting.mart_starting_pitcher_game_log g
        JOIN starters s ON g.pitcher_id = s.probable_pitcher_id
        JOIN game_meta gm ON gm.game_pk = s.game_pk
        WHERE g.game_date < gm.game_date
    ) sub
    WHERE sub.rn <= 5
    GROUP BY sub.game_pk, sub.pitcher_id
)
SELECT
    s.game_pk,
    s.side,
    s.probable_pitcher_id,
    s.probable_pitcher_name,
    gm.game_year                                                AS current_season_year,
    cs.starts                                                   AS current_starts,
    cs.ra9                                                      AS current_ra9,
    cs.whip                                                     AS current_whip,
    cs.k_pct                                                    AS current_k_pct,
    gm.game_year - 1                                            AS prior_season_year,
    ps.starts                                                   AS prior_starts,
    ps.ra9                                                      AS prior_ra9,
    ps.whip                                                     AS prior_whip,
    ps.k_pct                                                    AS prior_k_pct,
    IFF(COALESCE(l5.median_ip_last5, 5.0) < 2.5, TRUE, FALSE)  AS is_opener
FROM starters s
JOIN game_meta gm ON gm.game_pk = s.game_pk
LEFT JOIN current_season cs ON cs.game_pk = s.game_pk AND cs.pitcher_id = s.probable_pitcher_id
LEFT JOIN prior_season ps ON ps.game_pk = s.game_pk AND ps.pitcher_id = s.probable_pitcher_id
LEFT JOIN last5 l5 ON l5.game_pk = s.game_pk AND l5.pitcher_id = s.probable_pitcher_id
"""

# E9.36 — last 3 completed starts for each game's probable starters (context only, no
# edge claim). Keyed by game_pk so it rides _sf_query_batch; bounded to starts BEFORE
# each game's own date (correct for historical pick pages too, not just upcoming).
# Sourced from the W-migrated mart_starting_pitcher_game_log via the established
# Snowflake-FQN-over-lakehouse pattern (W7b repoints to direct-S3 with the rest of this
# writer). Tiny: ≤3 rows per (game, side).
_SP_LAST3_BATCH = """
WITH targets AS (
    SELECT g.game_pk, CAST(g.game_date AS DATE) AS game_date, p.side, p.probable_pitcher_id AS pitcher_id
    FROM baseball_data.betting.stg_statsapi_games g
    JOIN (
        SELECT game_pk, side, probable_pitcher_id
        FROM baseball_data.betting.stg_statsapi_probable_pitchers
        QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk, side ORDER BY ingestion_ts DESC) = 1
    ) p ON p.game_pk = g.game_pk
    WHERE g.game_pk IN ({game_pk_list}) AND p.probable_pitcher_id IS NOT NULL
)
SELECT
    t.game_pk, t.side, t.pitcher_id,
    l.game_date::VARCHAR AS start_date,
    l.batting_team AS opposing_team, l.is_home_team, l.outs_recorded,
    l.strikeouts, l.walks, l.hits_allowed, l.runs_allowed, l.home_runs_allowed
FROM targets t
JOIN baseball_data.betting.mart_starting_pitcher_game_log l
    ON l.pitcher_id = t.pitcher_id AND l.game_date < t.game_date
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.game_pk, t.side ORDER BY l.game_date DESC) <= 3
ORDER BY t.game_pk, t.side, l.game_date DESC
"""

_BOVADA_BATCH = """
WITH pre_game AS (
    SELECT
        g.game_pk,
        o.market_key,
        o.outcome_name,
        o.outcome_price_american,
        o.outcome_point,
        o.is_home_outcome,
        o.ingestion_ts
    FROM baseball_data.betting.mart_odds_outcomes o
    JOIN baseball_data.betting.stg_statsapi_games g
        ON g.official_date = o.commence_date
    JOIN baseball_data.betting.dim_team_name_lookup gh
        ON gh.name_lower = lower(regexp_replace(trim(g.home_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup ga
        ON ga.name_lower = lower(regexp_replace(trim(g.away_team_name), '^G[12] ', ''))
    JOIN baseball_data.betting.dim_team_name_lookup oh
        ON oh.name_lower = lower(regexp_replace(trim(o.home_team), '^G[12] ', ''))
       AND oh.team_id = gh.team_id
    JOIN baseball_data.betting.dim_team_name_lookup oa
        ON oa.name_lower = lower(regexp_replace(trim(o.away_team), '^G[12] ', ''))
       AND oa.team_id = ga.team_id
    WHERE g.game_pk IN ({game_pk_list})
      AND o.bookmaker_key = 'bovada'
      AND o.ingestion_ts::TIMESTAMP_NTZ < g.game_date::TIMESTAMP_NTZ
),
-- Latest snapshot per game where BOTH home and away h2h outcomes exist.
-- Falls back to an earlier snapshot rather than showing a one-sided line.
best_h2h_snap AS (
    SELECT game_pk, MAX(ingestion_ts) AS best_ts
    FROM (
        SELECT game_pk, ingestion_ts
        FROM pre_game
        WHERE market_key = 'h2h'
        GROUP BY game_pk, ingestion_ts
        HAVING SUM(CASE WHEN is_home_outcome     THEN 1 ELSE 0 END) >= 1
           AND SUM(CASE WHEN NOT is_home_outcome THEN 1 ELSE 0 END) >= 1
    ) paired
    GROUP BY game_pk
)
SELECT p.game_pk, p.market_key, p.outcome_name, p.outcome_price_american, p.outcome_point,
       p.is_home_outcome, p.ingestion_ts
FROM pre_game p
JOIN best_h2h_snap s ON s.game_pk = p.game_pk AND p.ingestion_ts = s.best_ts
WHERE p.market_key = 'h2h'
UNION ALL
SELECT game_pk, market_key, outcome_name, outcome_price_american, outcome_point,
       is_home_outcome, ingestion_ts
FROM pre_game
WHERE market_key != 'h2h'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk, market_key, outcome_name
    ORDER BY ingestion_ts DESC
) = 1
ORDER BY game_pk, market_key, is_home_outcome DESC
"""

_TEAM_FEATURES_BATCH = """
SELECT
    game_pk,
    home_off_woba_30d, away_off_woba_30d,
    home_off_xwoba_30d, away_off_xwoba_30d,
    home_off_runs_per_game_30d, away_off_runs_per_game_30d,
    home_starter_xwoba_against_30d, away_starter_xwoba_against_30d,
    home_starter_k_pct_30d, away_starter_k_pct_30d,
    home_starter_pitcher_hand, away_starter_pitcher_hand,
    home_lineup_vs_away_starter_xwoba_adj, away_lineup_vs_home_starter_xwoba_adj,
    home_bp_xwoba_against_14d, away_bp_xwoba_against_14d,
    home_bp_innings_pitched_14d, away_bp_innings_pitched_14d,
    home_days_rest, away_days_rest,
    park_run_factor_3yr, elo_diff
FROM baseball_data.betting_features.feature_pregame_game_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_date DESC) = 1
"""

_LINEUP_BATCH = """
WITH wide AS (
    SELECT * FROM baseball_data.betting.stg_statsapi_lineups_wide
    WHERE game_pk IN ({game_pk_list})
),
slots AS (
    SELECT game_pk, home_away, official_date, 1 AS slot, slot_1_player_id AS player_id, slot_1_full_name AS player_name, slot_1_position AS position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 2, slot_2_player_id, slot_2_full_name, slot_2_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 3, slot_3_player_id, slot_3_full_name, slot_3_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 4, slot_4_player_id, slot_4_full_name, slot_4_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 5, slot_5_player_id, slot_5_full_name, slot_5_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 6, slot_6_player_id, slot_6_full_name, slot_6_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 7, slot_7_player_id, slot_7_full_name, slot_7_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 8, slot_8_player_id, slot_8_full_name, slot_8_position FROM wide
    UNION ALL SELECT game_pk, home_away, official_date, 9, slot_9_player_id, slot_9_full_name, slot_9_position FROM wide
),
season_stats AS (
    SELECT
        rs.batter_id,
        rs.ops_std   AS season_ops,
        rs.xwoba_std AS season_xwoba
    FROM baseball_data.betting.mart_batter_rolling_stats rs
    JOIN slots s ON rs.batter_id = s.player_id
        AND rs.game_year  = YEAR(s.official_date)
        AND rs.game_date  < s.official_date
    QUALIFY ROW_NUMBER() OVER (PARTITION BY rs.batter_id ORDER BY rs.game_date DESC) = 1
)
SELECT s.game_pk, s.home_away, s.slot, s.player_id, s.player_name, s.position,
       st.season_ops, st.season_xwoba
FROM slots s
LEFT JOIN season_stats st ON st.batter_id = s.player_id
WHERE s.player_id IS NOT NULL
ORDER BY s.game_pk, s.home_away, s.slot
"""

_BOX_SCORE_BATCH = """
WITH pa_end AS (
    SELECT
        game_pk, batter_id, player_name, inning_half, at_bat_number,
        plate_appearance_event, woba_value, woba_denom, xwoba
    FROM baseball_data.betting.stg_batter_pitches
    WHERE game_pk IN ({game_pk_list}) AND woba_denom = 1
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY game_pk, batter_id, at_bat_number
        ORDER BY pitch_number DESC
    ) = 1
)
SELECT
    game_pk, batter_id, player_name,
    CASE WHEN UPPER(inning_half) = 'TOP' THEN 'away' ELSE 'home' END AS home_away,
    COUNT(*)                                                                                            AS pa,
    SUM(CASE WHEN plate_appearance_event NOT IN (
        'walk','intent_walk','hit_by_pitch','sac_fly','sac_bunt',
        'catcher_interf','sac_fly_double_play'
    ) THEN 1 ELSE 0 END)                                                                                AS ab,
    SUM(CASE WHEN plate_appearance_event IN ('single','double','triple','home_run') THEN 1 ELSE 0 END)  AS h,
    SUM(CASE WHEN plate_appearance_event IN ('strikeout','strikeout_double_play') THEN 1 ELSE 0 END)    AS k,
    SUM(CASE WHEN plate_appearance_event IN ('walk','intent_walk') THEN 1 ELSE 0 END)                   AS bb,
    SUM(CASE WHEN plate_appearance_event = 'home_run' THEN 1 ELSE 0 END)                                AS hr,
    ROUND(SUM(COALESCE(xwoba, woba_value, 0) * woba_denom) / NULLIF(SUM(woba_denom), 0), 3)            AS xwoba_game
FROM pa_end
GROUP BY game_pk, batter_id, player_name, inning_half
ORDER BY game_pk, home_away, batter_id
"""

_WEATHER_BATCH = """
SELECT game_pk, temp_f, wind_speed_mph, wind_component_mph, is_dome, weather_observation_type
FROM baseball_data.betting_features.feature_pregame_weather_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_PUBLIC_BETTING_BATCH = """
SELECT game_pk,
    home_ml_money_pct, away_ml_money_pct,
    home_ml_ticket_pct, away_ml_ticket_pct,
    over_money_pct, under_money_pct,
    over_ticket_pct, under_ticket_pct,
    ml_sharp_signal, total_sharp_signal
FROM baseball_data.betting_features.feature_pregame_public_betting_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_LINE_MOVEMENT_BATCH = """
SELECT game_pk,
    open_home_win_prob, pregame_home_win_prob, h2h_line_movement,
    open_total_line, pregame_total_line, total_line_movement
FROM baseball_data.betting.mart_odds_line_movement
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk) = 1
"""

_LINE_MOVEMENT_SERIES_BATCH = """
-- E9.37: compact per-book, per-market odds-snapshot series (open→current) for the
-- game-detail payload, across the curated book set (E9.37b — was Bovada-only).
-- Source = mart_odds_outcomes (live intraday snapshots) bridged to game_pk via
-- mart_game_odds_bridge; leakage-guarded (snapshot < commence). williamhill_us is
-- canonicalized to 'caesars' (matches the Book Comparison key). h2h is DE-VIGGED
-- (home_imp / (home_imp + away_imp)) so levels are comparable across books with
-- different vig; totals carries BOTH the over/under line (runs) AND a de-vigged
-- Over probability (E9.37c — totals lines are sticky at half-run steps; the real
-- market move is often in the juice, which over_prob captures). Collapsed/
-- downsampled in Python to keep the blob lean.
-- NOTE (W7b coordination): these are W6-migrated marts read here through the
-- established Snowflake-FQN-over-lakehouse pattern; repoint alongside the other
-- game-detail batch reads when W7b moves write_serving_store to direct-S3.
WITH bridge AS (
    SELECT game_pk, event_id
    FROM baseball_data.betting.mart_game_odds_bridge
    WHERE game_pk IN ({game_pk_list}) AND event_id IS NOT NULL
),
snaps AS (
    SELECT
        b.game_pk,
        CASE o.bookmaker_key WHEN 'williamhill_us' THEN 'caesars' ELSE o.bookmaker_key END AS book,
        o.market_key,
        o.ingestion_ts AS snapshot_ts,
        CASE WHEN o.market_key = 'h2h' AND o.is_home_outcome THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN ABS(o.outcome_price_american) / (ABS(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS home_imp,
        CASE WHEN o.market_key = 'h2h' AND o.is_away_outcome THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN ABS(o.outcome_price_american) / (ABS(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS away_imp,
        CASE WHEN o.market_key = 'totals' THEN o.outcome_point END AS total_line,
        CASE WHEN o.market_key = 'totals' AND o.outcome_name = 'Over' THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN ABS(o.outcome_price_american) / (ABS(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS over_imp,
        CASE WHEN o.market_key = 'totals' AND o.outcome_name = 'Under' THEN
            CASE WHEN o.outcome_price_american < 0
                 THEN ABS(o.outcome_price_american) / (ABS(o.outcome_price_american) + 100.0)
                 ELSE 100.0 / (o.outcome_price_american + 100.0)
            END
        END AS under_imp
    FROM baseball_data.betting.mart_odds_outcomes o
    INNER JOIN bridge b ON b.event_id = o.event_id
    WHERE o.bookmaker_key IN ('pinnacle', 'betmgm', 'williamhill_us', 'fanduel', 'draftkings', 'fanatics', 'bovada')
      AND o.market_key IN ('h2h', 'totals')
      -- INC-23: mart_odds_outcomes.commence_time is string-wrapped (VARCHAR) in the S3 lakehouse
      -- view while ingestion_ts is a real TIMESTAMP → a bare compare HALTs DuckDB (TIMESTAMP↔VARCHAR)
      -- in --s3 mode. Cast ::timestamp (no-op on the native Snowflake TIMESTAMP_NTZ). CLAUDE.md INC-23.
      AND o.ingestion_ts < o.commence_time::timestamp
),
-- Group per LINE (outcome_point) so Over/Under prices pair within the same line;
-- h2h rows have a NULL line → one group per snapshot. This avoids conflating a
-- main line's price with a simultaneously-posted alternate line.
agg AS (
    SELECT
        game_pk, book, market_key, snapshot_ts, total_line AS line,
        MAX(home_imp)  AS home_imp,
        MAX(away_imp)  AS away_imp,
        MAX(over_imp)  AS over_imp,
        MAX(under_imp) AS under_imp
    FROM snaps
    GROUP BY game_pk, book, market_key, snapshot_ts, total_line
)
SELECT
    game_pk,
    book,
    market_key,
    snapshot_ts,
    CASE WHEN home_imp IS NOT NULL AND away_imp IS NOT NULL AND (home_imp + away_imp) > 0
         THEN home_imp / (home_imp + away_imp) END AS home_win_prob,
    CASE WHEN market_key = 'totals' THEN line END AS total_line,
    CASE WHEN over_imp IS NOT NULL AND under_imp IS NOT NULL AND (over_imp + under_imp) > 0
         THEN over_imp / (over_imp + under_imp) END AS over_prob
FROM agg
WHERE (home_imp IS NOT NULL AND away_imp IS NOT NULL) OR market_key = 'totals'
-- When a book posts >1 total line in one snapshot (alternates), keep the MAIN
-- line: fully-priced first, then juice closest to even (the balanced market).
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk, book, market_key, snapshot_ts
    ORDER BY
        CASE WHEN market_key = 'totals' AND over_imp IS NOT NULL AND under_imp IS NOT NULL THEN 0 ELSE 1 END,
        CASE WHEN market_key = 'totals' AND over_imp IS NOT NULL AND under_imp IS NOT NULL AND (over_imp + under_imp) > 0
             THEN ABS(over_imp / (over_imp + under_imp) - 0.5) ELSE 0 END
) = 1
ORDER BY game_pk, book, market_key, snapshot_ts ASC
"""

_RECENT_FORM_BATCH = """
WITH game_meta AS (
    SELECT game_pk, game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
home_recent AS (
    SELECT
        gm.game_pk,
        'home' AS team_side,
        CASE WHEN g.home_team_id = gm.home_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS won,
        ROW_NUMBER() OVER (PARTITION BY gm.game_pk ORDER BY g.game_date DESC) AS rn
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND g.game_date < gm.game_date
      AND YEAR(g.game_date::date) = YEAR(gm.game_date::date)  -- INC-23: stg_statsapi_games game_date is ISO VARCHAR in --s3
      AND g.home_is_winner IS NOT NULL
      AND (g.home_team_id = gm.home_team_id OR g.away_team_id = gm.home_team_id)
),
away_recent AS (
    SELECT
        gm.game_pk,
        'away' AS team_side,
        CASE WHEN g.home_team_id = gm.away_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS won,
        ROW_NUMBER() OVER (PARTITION BY gm.game_pk ORDER BY g.game_date DESC) AS rn
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND g.game_date < gm.game_date
      AND YEAR(g.game_date::date) = YEAR(gm.game_date::date)  -- INC-23: stg_statsapi_games game_date is ISO VARCHAR in --s3
      AND g.home_is_winner IS NOT NULL
      AND (g.home_team_id = gm.away_team_id OR g.away_team_id = gm.away_team_id)
),
combined AS (SELECT * FROM home_recent UNION ALL SELECT * FROM away_recent)
SELECT game_pk, team_side,
    SUM(CASE WHEN rn <= 5  AND won = TRUE  THEN 1 ELSE 0 END) AS l5_wins,
    SUM(CASE WHEN rn <= 5  AND won = FALSE THEN 1 ELSE 0 END) AS l5_losses,
    SUM(CASE WHEN rn <= 5  THEN 1 ELSE 0 END)                 AS l5_games,
    SUM(CASE WHEN rn <= 10 AND won = TRUE  THEN 1 ELSE 0 END) AS l10_wins,
    SUM(CASE WHEN rn <= 10 AND won = FALSE THEN 1 ELSE 0 END) AS l10_losses,
    SUM(CASE WHEN rn <= 10 THEN 1 ELSE 0 END)                 AS l10_games
FROM combined WHERE rn <= 10
GROUP BY game_pk, team_side
"""

_H2H_BATCH = """
WITH game_meta AS (
    SELECT game_pk, game_date, home_team_id, away_team_id
    FROM baseball_data.betting.stg_statsapi_games
    WHERE game_pk IN ({game_pk_list})
),
h2h_games AS (
    SELECT
        gm.game_pk,
        CASE WHEN g.home_team_id = gm.home_team_id THEN g.home_is_winner
             ELSE g.away_is_winner END AS home_team_won,
        g.home_score + g.away_score   AS total_runs
    FROM baseball_data.betting.stg_statsapi_games g
    CROSS JOIN game_meta gm
    WHERE g.abstract_game_state = 'Final'
      AND YEAR(g.game_date::date) = YEAR(gm.game_date::date)  -- INC-23: stg_statsapi_games game_date is ISO VARCHAR in --s3
      AND g.game_date < gm.game_date
      AND g.home_is_winner IS NOT NULL
      AND (
        (g.home_team_id = gm.home_team_id AND g.away_team_id = gm.away_team_id)
        OR (g.home_team_id = gm.away_team_id AND g.away_team_id = gm.home_team_id)
      )
)
SELECT game_pk,
    SUM(CASE WHEN home_team_won = TRUE  THEN 1 ELSE 0 END) AS home_wins,
    SUM(CASE WHEN home_team_won = FALSE THEN 1 ELSE 0 END) AS away_wins,
    COUNT(*)                                                AS games_played,
    ROUND(AVG(total_runs), 2)                              AS avg_total_runs
FROM h2h_games
GROUP BY game_pk
"""

_UMPIRE_BATCH = """
SELECT game_pk, umpire_name, ump_games_sample,
    CASE WHEN ump_k_pct_trailing  IS NULL THEN NULL ELSE ump_k_pct_zscore  END AS ump_k_pct_zscore,
    CASE WHEN ump_bb_pct_trailing IS NULL THEN NULL ELSE ump_bb_pct_zscore END AS ump_bb_pct_zscore,
    ump_runs_per_game_zscore, ump_run_impact_zscore
FROM baseball_data.betting_features.feature_pregame_umpire_features
WHERE game_pk IN ({game_pk_list})
QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY game_pk DESC) = 1
"""

_EXPLANATION_BATCH = """
SELECT game_pk, pick_explanation, pick_narrative, prediction_type
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_pk IN ({game_pk_list})
  AND pick_explanation IS NOT NULL
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY game_pk
    ORDER BY CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
             CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END, inserted_at DESC
) = 1
"""

_FEATURED_TODAY_SERVING_SQL = """
WITH ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY
                -- Prefer rows carrying market data so a degraded run (post_lineup
                -- with NULL odds/abstain) never shadows a complete morning row.
                CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                p.inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    WHERE p.game_date = %(today)s
      AND p.prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.home_team, b.away_team,
        'h2h'                                                         AS market_type,
        b.calibrated_win_prob                                         AS model_prob,
        b.h2h_market_implied_prob                                     AS market_prob,
        ABS(b.calibrated_win_prob - b.h2h_market_implied_prob)        AS edge,
        b.win_prob_ci_low, b.win_prob_ci_high,
        b.game_datetime, b.game_date, b.prediction_type,
        b.layer4_h2h_decision                                         AS pick_side
    FROM base b
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk, b.home_team, b.away_team,
        'totals'                                                      AS market_type,
        b.totals_model_prob                                           AS model_prob,
        b.over_prob_consensus                                         AS market_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus)              AS edge,
        b.win_prob_ci_low, b.win_prob_ci_high,
        b.game_datetime, b.game_date, b.prediction_type,
        b.layer4_totals_decision                                      AS pick_side
    FROM base b
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_totals_decision IN ('over', 'under')
)
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date,
       prediction_type, pick_side
FROM h2h UNION ALL
SELECT game_pk, home_team, away_team, market_type, model_prob, market_prob,
       edge, win_prob_ci_low, win_prob_ci_high, game_datetime, game_date,
       prediction_type, pick_side
FROM totals
ORDER BY game_datetime ASC NULLS LAST, game_pk ASC
LIMIT 1
"""

_FEATURED_YESTERDAY_SERVING_SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY
                -- Mirror today's ranking: prefer rows with market data, then post_lineup,
                -- then latest inserted_at — so yesterday's "featured" pick is the same
                -- one that would have been shown as today's pick on that date.
                CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_date = DATEADD(day, -1, %(today)s::DATE)
      AND prediction_type IN ('post_lineup', 'morning')
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT
        b.game_pk, b.home_team, b.away_team,
        'h2h'                     AS market_type,
        b.layer4_h2h_decision     AS pick_side,
        b.game_datetime,
        clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'h2h'
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_h2h_decision IN ('home', 'away')
),
totals AS (
    SELECT
        b.game_pk, b.home_team, b.away_team,
        'totals'                      AS market_type,
        b.layer4_totals_decision      AS pick_side,
        b.game_datetime,
        clv.actual_outcome
    FROM base b
    LEFT JOIN baseball_data.betting.mart_clv_labeled_games clv
        ON clv.game_pk = b.game_pk AND clv.market_type = 'totals'
    WHERE b.layer4_h2h_conviction_flag = TRUE
      AND b.layer4_totals_decision IN ('over', 'under')
)
SELECT game_pk, home_team, away_team, market_type, pick_side, actual_outcome, game_datetime
FROM h2h UNION ALL
SELECT game_pk, home_team, away_team, market_type, pick_side, actual_outcome, game_datetime
FROM totals
ORDER BY game_datetime ASC NULLS LAST, game_pk ASC
LIMIT 1
"""

_GAME_PICKS_BATCH = """
WITH ranked AS (
    SELECT
        p.*,
        g.game_date                                                          AS game_start_utc,
        MAX(p.meta_p_clv_positive) OVER (PARTITION BY p.game_pk)            AS _meta_p,
        MAX(p.meta_ci_low) OVER (PARTITION BY p.game_pk)                    AS _meta_ci_low,
        MAX(p.meta_ci_high) OVER (PARTITION BY p.game_pk)                   AS _meta_ci_high,
        MAX(p.totals_meta_p_clv_positive) OVER (PARTITION BY p.game_pk)     AS _totals_meta_p,
        MAX(p.totals_meta_ci_low) OVER (PARTITION BY p.game_pk)             AS _totals_meta_ci_low,
        MAX(p.totals_meta_ci_high) OVER (PARTITION BY p.game_pk)            AS _totals_meta_ci_high,
        ROW_NUMBER() OVER (
            PARTITION BY p.game_pk
            ORDER BY CASE WHEN (p.h2h_market_implied_prob IS NOT NULL OR p.over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                     CASE WHEN p.prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                     p.inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions p
    LEFT JOIN baseball_data.betting.stg_statsapi_games g ON g.game_pk = p.game_pk
    WHERE p.game_pk IN ({game_pk_list})
),
base AS (SELECT * FROM ranked WHERE _rn = 1),
h2h AS (
    SELECT b.game_pk, b.game_date, 'h2h' AS market_type,
        b.calibrated_win_prob AS model_prob, b.h2h_market_implied_prob AS bovada_devig_prob,
        b.layer4_h2h_edge AS edge,
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed, b.win_prob_ci_low, b.win_prob_ci_high, b.win_prob_ci_width, b.gate_signals_met,
        b.home_team, b.away_team, NULLIF(b.layer4_h2h_decision, 'abstain') AS pick_side,
        b.game_start_utc, b.inserted_at AS predicted_at,
        NULL::FLOAT AS model_total_runs, NULL::FLOAT AS market_total_line,
        b._meta_p AS meta_p_clv_positive, b._meta_ci_low AS meta_ci_low, b._meta_ci_high AS meta_ci_high
    FROM base b WHERE b.h2h_market_implied_prob IS NOT NULL
),
totals AS (
    SELECT b.game_pk, b.game_date, 'totals' AS market_type,
        b.totals_model_prob AS model_prob, b.over_prob_consensus AS bovada_devig_prob,
        ABS(b.totals_model_prob - b.over_prob_consensus) AS edge,  -- prob-points edge (NOT layer4_totals_over_signal, which is runs: mu - line)
        IFF(b.layer4_h2h_conviction_flag, 0.8, 0.4) AS game_conviction_score,
        b.lineup_confirmed, NULL::FLOAT AS win_prob_ci_low, NULL::FLOAT AS win_prob_ci_high,
        NULL::FLOAT AS win_prob_ci_width, NULL::INTEGER AS gate_signals_met,
        b.home_team, b.away_team, NULLIF(b.layer4_totals_decision, 'abstain') AS pick_side,
        b.game_start_utc, b.inserted_at AS predicted_at,
        b.pred_total_runs AS model_total_runs, b.total_line_consensus AS market_total_line,
        b._totals_meta_p AS meta_p_clv_positive, b._totals_meta_ci_low AS meta_ci_low, b._totals_meta_ci_high AS meta_ci_high
    FROM base b WHERE b.over_prob_consensus IS NOT NULL
)
SELECT * FROM h2h UNION ALL SELECT * FROM totals
ORDER BY game_pk, market_type
"""


# A0.4.32 — Latest multi-book odds snapshot per game (all 6 curated books).
# We pick the latest ingestion_ts where BOTH outcomes are present in the same
# snapshot (snapshot-aligned), avoiding mixed-snapshot lines where a partial
# feed update causes e.g. home +315 / away +139 (both positive — impossible).
_BOOK_ODDS_BATCH = """
WITH bridge AS (
    -- E9.27: left-join precise game-start time for the pre-game-start leakage guard.
    -- game_date from stg_statsapi_games is TIMESTAMP_TZ (real scheduled UTC start).
    -- QUALIFY picks the latest ingestion when multiple schedule snapshots exist.
    SELECT b.game_pk, b.event_id, gs.game_start_ts
    FROM baseball_data.betting.mart_game_odds_bridge b
    LEFT JOIN (
        SELECT game_pk, game_date::TIMESTAMP_NTZ AS game_start_ts
        FROM baseball_data.betting.stg_statsapi_games
        WHERE game_pk IN ({game_pk_list})
        QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk ORDER BY ingestion_ts DESC) = 1
    ) gs ON gs.game_pk = b.game_pk
    WHERE b.game_pk IN ({game_pk_list})
),
all_odds AS (
    SELECT
        o.event_id,
        o.bookmaker_key,
        o.market_key,
        o.outcome_name,
        o.outcome_price_american,
        o.outcome_price_decimal,
        o.outcome_point,
        o.is_home_outcome,
        o.ingestion_ts
    FROM baseball_data.betting.mart_odds_outcomes o
    INNER JOIN bridge b ON b.event_id = o.event_id
    WHERE o.bookmaker_key IN ('betmgm', 'williamhill_us', 'fanduel', 'draftkings', 'fanatics', 'bovada', 'pinnacle')
      AND (b.game_start_ts IS NULL OR o.ingestion_ts < b.game_start_ts)  -- pre-game-start guard (E9.27); fail-open when start time unknown
),
-- Latest ingestion_ts for which the full set of outcomes is present
-- (h2h needs 2 sides, totals needs over+under). Prevents mixing a partial
-- feed update (e.g. only home price updated) with a stale away price.
complete_snapshots AS (
    SELECT event_id, bookmaker_key, market_key, ingestion_ts
    FROM all_odds
    GROUP BY event_id, bookmaker_key, market_key, ingestion_ts
    HAVING COUNT(DISTINCT outcome_name) >= 2
),
latest_complete AS (
    SELECT event_id, bookmaker_key, market_key,
           MAX(ingestion_ts) AS latest_ts
    FROM complete_snapshots
    GROUP BY event_id, bookmaker_key, market_key
),
latest_odds AS (
    SELECT o.event_id, o.bookmaker_key, o.market_key, o.outcome_name,
           o.outcome_price_american, o.outcome_price_decimal, o.outcome_point,
           o.is_home_outcome, lc.latest_ts
    FROM all_odds o
    INNER JOIN latest_complete lc
        ON  lc.event_id      = o.event_id
        AND lc.bookmaker_key = o.bookmaker_key
        AND lc.market_key    = o.market_key
        AND lc.latest_ts     = o.ingestion_ts
)
SELECT b.game_pk,
       lo.bookmaker_key, lo.market_key, lo.outcome_name,
       lo.outcome_price_american, lo.outcome_price_decimal, lo.outcome_point,
       lo.is_home_outcome, lo.latest_ts
FROM latest_odds lo
JOIN bridge b ON b.event_id = lo.event_id
ORDER BY b.game_pk, lo.bookmaker_key, lo.market_key, lo.outcome_name
"""

# A0.4.32 — Model distribution params for per-book P(over) recomputation
_MODEL_DIST_BATCH = """
WITH ranked AS (
    SELECT
        game_pk, calibrated_win_prob, pred_total_runs, pred_total_runs_scale,
        home_team, away_team,
        ROW_NUMBER() OVER (
            PARTITION BY game_pk
            ORDER BY CASE WHEN (h2h_market_implied_prob IS NOT NULL OR over_prob_consensus IS NOT NULL) THEN 0 ELSE 1 END,
                     CASE WHEN prediction_type = 'post_lineup' THEN 0 ELSE 1 END,
                     inserted_at DESC
        ) AS _rn
    FROM baseball_data.betting_ml.daily_model_predictions
    WHERE game_pk IN ({game_pk_list})
)
SELECT game_pk, calibrated_win_prob, pred_total_runs, pred_total_runs_scale,
       home_team, away_team
FROM ranked WHERE _rn = 1
"""

# A0.4.32 — standalone --book-odds game-pk resolver (no --picks given).
# Module-level (not inlined in main()) so the --s3 grep-driven view registration
# auto-discovers daily_model_predictions for it like every other SQL constant.
_STANDALONE_BOOK_PKS_SQL = """
SELECT DISTINCT game_pk
FROM baseball_data.betting_ml.daily_model_predictions
WHERE game_date = %(today)s
  AND prediction_type IN ('post_lineup', 'morning')
"""


# ── Payload builders ──────────────────────────────────────────────────────────

def _ts(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _flt(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


# E9.37 — per-market line-movement series: cap points so the game-detail blob
# stays lean (intraday snapshots can run to dozens of rows per market).
_LM_SERIES_MAX_POINTS = 24


def _downsample_series(points: list[dict], value_keys, cap: int = _LM_SERIES_MAX_POINTS) -> list[dict]:
    """Collapse consecutive no-change snapshots (a value frequently holds flat),
    then cap to `cap` points via even stride — always pinning the first (open) and
    last (current) snapshot. `value_keys` is a key (str) or list of keys — a point
    is kept when ANY listed key changes (so totals keeps both line and juice
    moves). Input must be time-ordered ascending."""
    if not points:
        return []
    keys = [value_keys] if isinstance(value_keys, str) else list(value_keys)
    def _val(p):
        return tuple(p.get(k) for k in keys)
    deduped = [points[0]]
    for p in points[1:]:
        if _val(p) != _val(deduped[-1]):
            deduped.append(p)
    # Always keep the latest snapshot so the series ends at "current".
    if deduped[-1] is not points[-1]:
        deduped.append(points[-1])
    if len(deduped) <= cap:
        return deduped
    step = (len(deduped) - 1) / (cap - 1)
    idxs = sorted({round(i * step) for i in range(cap)})
    return [deduped[i] for i in idxs]


def _build_line_movement_series(rows: list[dict]) -> dict | None:
    """Group time-ordered odds snapshots into a compact per-book, per-market
    open→current series for the game-detail payload (E9.37 / E9.37b multi-book).
    Returns {"books": [<canonical, ordered>], "series": {book: {"h2h":
    [{ts, home_win_prob}], "totals": [{ts, line}]}}} or None when there are no
    usable snapshots. h2h is de-vigged. Market context only — not an edge claim
    (our h2h/totals models show no demonstrated market edge). Input must be
    time-ordered ascending per (book, market)."""
    by_book: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"h2h": [], "totals": []})
    for r in rows:
        ts = _ts(r.get("SNAPSHOT_TS"))
        if ts is None:
            continue
        book = str(r.get("BOOK") or "").lower()
        if not book:
            continue
        mkt = str(r.get("MARKET_KEY") or "").lower()
        if mkt == "h2h":
            v = _flt(r.get("HOME_WIN_PROB"))
            if v is not None:
                by_book[book]["h2h"].append({"ts": ts, "home_win_prob": round(v, 4)})
        elif mkt == "totals":
            line = _flt(r.get("TOTAL_LINE"))
            if line is not None:
                op = _flt(r.get("OVER_PROB"))
                by_book[book]["totals"].append({
                    "ts": ts, "line": line,
                    "over_prob": round(op, 4) if op is not None else None,
                })
    series: dict[str, dict] = {}
    for book, mkts in by_book.items():
        h2h_pts = _downsample_series(mkts["h2h"], "home_win_prob")
        # totals: keep a point when EITHER the line or the de-vigged Over% moves.
        tot_pts = _downsample_series(mkts["totals"], ["line", "over_prob"])
        if h2h_pts or tot_pts:
            series[book] = {"h2h": h2h_pts, "totals": tot_pts}
    if not series:
        return None
    # Order books by the curated display order; append any unexpected key last.
    books = [b for b in _BOOK_ORDER if b in series]
    books += [b for b in series if b not in books]
    return {"books": books, "series": series}


def _build_picks_payload(rows: list[dict], freshness_rows: list[dict]) -> dict:
    last_updated_at = None
    if freshness_rows and freshness_rows[0].get("LAST_UPDATED_AT"):
        last_updated_at = _ts(freshness_rows[0]["LAST_UPDATED_AT"])
    if last_updated_at:
        try:
            ts_dt = datetime.fromisoformat(last_updated_at.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - ts_dt.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            pipeline_status = "ok" if age_h < 6 else "stale"
        except Exception:
            pipeline_status = "ok"
    else:
        pipeline_status = "no_predictions"
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]),
            "market_type": r["MARKET_TYPE"], "model_prob": r.get("MODEL_PROB"),
            "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"), "edge": r.get("EDGE"),
            "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "win_prob_ci_width": r.get("WIN_PROB_CI_WIDTH"), "gate_signals_met": r.get("GATE_SIGNALS_MET"),
            "meta_p_clv_positive": r.get("META_P_CLV_POSITIVE"),
            "meta_ci_low": r.get("META_CI_LOW"), "meta_ci_high": r.get("META_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"), "pick_side": r.get("PICK_SIDE"),
            "game_start_utc": _ts(r.get("GAME_START_UTC")),
            "model_total_runs": r.get("MODEL_TOTAL_RUNS"), "market_total_line": r.get("MARKET_TOTAL_LINE"),
        }
        for r in rows
    ]
    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    return {"picks": picks, "data_quality": {"signal_completeness_score": None,
        "last_updated_at": last_updated_at, "pipeline_status": pipeline_status},
        "is_preliminary": is_preliminary}


def _build_ev_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r.get("GAME_DATE") or ""),
            "game_start_utc": _ts(r.get("GAME_START_UTC")), "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"), "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"), "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "qualified_bet": r.get("QUALIFIED_BET"),
            "home_team": r.get("HOME_TEAM"), "away_team": r.get("AWAY_TEAM"),
            "kelly_fraction": r.get("KELLY_FRACTION"), "total_line_consensus": r.get("TOTAL_LINE_CONSENSUS"),
            "pred_total_runs": r.get("PRED_TOTAL_RUNS"),
        }
        for r in rows
    ]
    is_preliminary = bool(rows) and any(
        (r.get("PREDICTION_TYPE") or "") == "morning" for r in rows
    )
    return {"picks": picks, "total": len(picks), "is_preliminary": is_preliminary}


def _build_history_payload(rows: list[dict]) -> dict:
    picks = [
        {
            "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]), "market_type": r["MARKET_TYPE"],
            "model_prob": r.get("MODEL_PROB"), "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"),
            "edge": r.get("EDGE"), "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
            "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
            "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
            "away_team": r.get("AWAY_TEAM"), "clv": r.get("CLV"),
            "clv_positive": r.get("CLV_POSITIVE"), "actual_outcome": r.get("ACTUAL_OUTCOME"),
        }
        for r in rows
    ]
    return {"picks": picks, "total": len(picks)}


def _build_performance_payload(rows: list[dict], source: str) -> dict:
    if not rows:
        return {"total_bets": 0, "wins": 0, "source": source}
    r = rows[0]
    total = r.get("TOTAL_BETS") or 0
    wins = r.get("WINS") or 0
    return {
        "total_bets": total, "wins": wins,
        "win_rate": r.get("WIN_RATE") if source == "mart_bankroll_state" else (wins / total if total > 0 else None),
        "mean_clv": r.get("MEAN_CLV"), "net_pnl_flat": r.get("NET_PNL_FLAT"),
        "net_pnl_kelly": r.get("NET_PNL_KELLY"), "sharpe_ratio": r.get("SHARPE_RATIO"),
        "source": source,
    }


def _compute_book_odds_payloads(sf, game_pks: list[int]) -> dict[int, dict]:
    """Fetch per-book odds + model distribution params; compute EV/edge/kelly Python-side.

    Returns {game_pk: book_odds_payload} where the payload matches BookOddsComparison schema.
    Gracefully skips books with incomplete lines rather than erroring.
    """
    if not game_pks:
        return {}

    odds_rows = _sf_query_batch(sf, _BOOK_ODDS_BATCH, game_pks)
    dist_rows = _sf_query_batch(sf, _MODEL_DIST_BATCH, game_pks)

    # Index model params by game_pk
    dist_by_pk: dict[int, dict] = {r["GAME_PK"]: r for r in dist_rows}

    # Group odds by game_pk → bookmaker_key → market_key → list[row]
    # Canonicalize williamhill_us → caesars (Parlay API still sends the Odds API key).
    _BOOK_KEY_CANONICAL = {"williamhill_us": "caesars"}
    odds_by_pk: dict[int, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in odds_rows:
        gp = row["GAME_PK"]
        bk = str(row["BOOKMAKER_KEY"]).lower()
        bk = _BOOK_KEY_CANONICAL.get(bk, bk)
        mk = str(row["MARKET_KEY"]).lower()
        odds_by_pk[gp][bk][mk].append(row)

    result: dict[int, dict] = {}

    for gp in game_pks:
        dist = dist_by_pk.get(gp)
        calib_win_prob = _flt(dist.get("CALIBRATED_WIN_PROB")) if dist else None
        pred_mu = _flt(dist.get("PRED_TOTAL_RUNS")) if dist else None
        pred_scale = _flt(dist.get("PRED_TOTAL_RUNS_SCALE")) if dist else None
        home_team = dist.get("HOME_TEAM") if dist else None
        away_team = dist.get("AWAY_TEAM") if dist else None

        h2h_rows: list[dict] = []
        totals_rows: list[dict] = []

        for book_key in _BOOK_ORDER:
            book_name = _BOOK_DISPLAY[book_key]
            is_sharp = book_key == "pinnacle"
            book_odds = odds_by_pk[gp].get(book_key, {})

            # ── H2H ──────────────────────────────────────────────────────────
            h2h_market = book_odds.get("h2h", [])
            home_h2h = next((r for r in h2h_market if r.get("IS_HOME_OUTCOME")), None)
            away_h2h = next((r for r in h2h_market if not r.get("IS_HOME_OUTCOME")), None)
            if home_h2h and away_h2h and calib_win_prob is not None:
                home_am = _int(home_h2h.get("OUTCOME_PRICE_AMERICAN"))
                away_am = _int(away_h2h.get("OUTCOME_PRICE_AMERICAN"))
                # Sanity: both sides positive = impossible moneyline (feed glitch).
                # Treat as missing rather than showing nonsense EV.
                if home_am is not None and away_am is not None and home_am > 0 and away_am > 0:
                    log.warning(
                        "Skipping %s h2h for game_pk=%s — both sides positive (%s/%s)",
                        book_key, gp, home_am, away_am,
                    )
                    h2h_rows.append({"book_key": book_key, "book_name": book_name,
                                     "is_sharp_reference": is_sharp})
                    continue
                h2h_odds_as_of = _ts(home_h2h.get("LATEST_TS"))
                home_dec = _flt(home_h2h.get("OUTCOME_PRICE_DECIMAL"))
                away_dec = _flt(away_h2h.get("OUTCOME_PRICE_DECIMAL"))
                try:
                    mkt_pct_home = float(devig_home_prob(home_am, away_am))
                except Exception:
                    mkt_pct_home = None
                ev_home = None
                edge_home = None
                kelly_home = None
                if mkt_pct_home is not None and not (mkt_pct_home != mkt_pct_home):  # not NaN
                    edge_home = calib_win_prob - mkt_pct_home
                    if home_dec is not None:
                        ev_home = calib_win_prob * (home_dec - 1.0) - (1.0 - calib_win_prob)
                    try:
                        kelly_home = compute_kelly(edge_home, mkt_pct_home) if mkt_pct_home > 0 else None
                    except Exception:
                        kelly_home = None
                else:
                    mkt_pct_home = None
                # E9.1 — breakeven American price for home and away sides
                be_home = prob_to_american(calib_win_prob)
                be_away = prob_to_american(1.0 - calib_win_prob)
                h2h_rows.append({
                    "book_key": book_key, "book_name": book_name,
                    "is_sharp_reference": is_sharp,
                    "home_american": home_am, "away_american": away_am,
                    "home_decimal": home_dec, "away_decimal": away_dec,
                    "market_bet_pct_home": round(mkt_pct_home, 4) if mkt_pct_home is not None else None,
                    "model_prob_home": round(calib_win_prob, 4),
                    "ev_home": round(ev_home, 4) if ev_home is not None else None,
                    "edge_home": round(edge_home, 4) if edge_home is not None else None,
                    "kelly_home": round(kelly_home, 4) if kelly_home is not None else None,
                    "odds_as_of": h2h_odds_as_of,
                    "breakeven_american_home": be_home,
                    "breakeven_american_away": be_away,
                })
            else:
                # Book has no line for this game — include placeholder so frontend knows
                h2h_rows.append({
                    "book_key": book_key, "book_name": book_name,
                    "is_sharp_reference": is_sharp,
                    "home_american": None, "away_american": None,
                    "home_decimal": None, "away_decimal": None,
                    "market_bet_pct_home": None, "model_prob_home": None,
                    "ev_home": None, "edge_home": None, "kelly_home": None,
                    "odds_as_of": None,
                    "breakeven_american_home": None, "breakeven_american_away": None,
                })

            # ── Totals ────────────────────────────────────────────────────────
            tot_market = book_odds.get("totals", [])
            over_row = next((r for r in tot_market if str(r.get("OUTCOME_NAME", "")).lower() == "over"), None)
            under_row = next((r for r in tot_market if str(r.get("OUTCOME_NAME", "")).lower() == "under"), None)
            if over_row and under_row:
                # Market lines are always written even when model params are unavailable.
                # Model prob/EV/edge columns go null — frontend renders "—" for those cells
                # so raw book prices remain visible without a working totals model.
                totals_odds_as_of = _ts(over_row.get("LATEST_TS"))
                line = _flt(over_row.get("OUTCOME_POINT"))
                over_am = _int(over_row.get("OUTCOME_PRICE_AMERICAN"))
                under_am = _int(under_row.get("OUTCOME_PRICE_AMERICAN"))
                over_dec = _flt(over_row.get("OUTCOME_PRICE_DECIMAL"))
                under_dec = _flt(under_row.get("OUTCOME_PRICE_DECIMAL"))
                try:
                    mkt_pct_over = float(devig_over_prob(over_am, under_am))
                except Exception:
                    mkt_pct_over = None
                p_over = p_under = p_push = ev_over = ev_under = edge_over = kelly_over = None
                if (
                    pred_mu is not None and pred_scale is not None
                    and line is not None
                    and mkt_pct_over is not None and not (mkt_pct_over != mkt_pct_over)
                ):
                    try:
                        # Champion totals model is NGBoost Normal — use Normal CDF.
                        # P(push) = 0 for a continuous distribution.
                        p_over = float(_scipy_norm.sf(line, loc=pred_mu, scale=pred_scale))
                        p_under = 1.0 - p_over
                        p_push = 0.0
                        edge_over = p_over - mkt_pct_over
                        if over_dec is not None:
                            ev_over = p_over * (over_dec - 1.0) - (1.0 - p_over)
                        if under_dec is not None:
                            ev_under = p_under * (under_dec - 1.0) - (1.0 - p_under)
                        if mkt_pct_over > 0:
                            kelly_over = compute_kelly(edge_over, mkt_pct_over)
                    except Exception:
                        pass
                elif mkt_pct_over is not None and mkt_pct_over != mkt_pct_over:  # NaN guard
                    mkt_pct_over = None
                # E9.1 — breakeven American price for over and under sides
                be_over = prob_to_american(p_over) if p_over is not None else None
                be_under = prob_to_american(p_under) if p_under is not None else None
                totals_rows.append({
                    "book_key": book_key, "book_name": book_name,
                    "is_sharp_reference": is_sharp,
                    "line": line,
                    "over_american": over_am, "under_american": under_am,
                    "over_decimal": over_dec, "under_decimal": under_dec,
                    "market_bet_pct_over": round(mkt_pct_over, 4) if mkt_pct_over is not None else None,
                    "model_prob_over": round(p_over, 4) if p_over is not None else None,
                    "model_prob_under": round(p_under, 4) if p_under is not None else None,
                    "p_push": round(p_push, 4) if p_push is not None else None,
                    "ev_over": round(ev_over, 4) if ev_over is not None else None,
                    "ev_under": round(ev_under, 4) if ev_under is not None else None,
                    "edge_over": round(edge_over, 4) if edge_over is not None else None,
                    "kelly_over": round(kelly_over, 4) if kelly_over is not None else None,
                    "odds_as_of": totals_odds_as_of,
                    "breakeven_american_over": be_over,
                    "breakeven_american_under": be_under,
                })
            else:
                totals_rows.append({
                    "book_key": book_key, "book_name": book_name,
                    "is_sharp_reference": is_sharp,
                    "line": None, "over_american": None, "under_american": None,
                    "over_decimal": None, "under_decimal": None,
                    "market_bet_pct_over": None, "model_prob_over": None,
                    "model_prob_under": None, "p_push": None,
                    "ev_over": None, "ev_under": None, "edge_over": None, "kelly_over": None,
                    "odds_as_of": None,
                    "breakeven_american_over": None, "breakeven_american_under": None,
                })

        # ── E9.11 — best US price per side (Pinnacle excluded) ───────────────
        # "Best" = highest American odds for that side (most favorable payout).
        # For negative lines, e.g. -110 > -120; for positive, +150 > +130.

        def _best_h2h_side(rows: list[dict], am_key: str, dec_key: str,
                           mkt_key: str, ev_key: str, edge_key: str, be_key: str):
            us_rows = [r for r in rows if not r.get("is_sharp_reference") and r.get(am_key) is not None]
            if not us_rows:
                return None
            best = max(us_rows, key=lambda r: r.get(am_key) or -9999)
            am = best.get(am_key)
            if am is None:
                return None
            return {
                "book_key": best["book_key"],
                "book_name": best["book_name"],
                "american": am,
                "decimal": best.get(dec_key),
                "market_bet_pct": best.get(mkt_key),
                "ev": best.get(ev_key),
                "edge": best.get(edge_key),
                "breakeven_american": best.get(be_key),
            }

        best_h2h_home = _best_h2h_side(
            h2h_rows, "home_american", "home_decimal",
            "market_bet_pct_home", "ev_home", "edge_home", "breakeven_american_home",
        )
        best_h2h_away = _best_h2h_side(
            h2h_rows, "away_american", "away_decimal",
            "market_bet_pct_home", "ev_home", "edge_home", "breakeven_american_away",
        )
        # Away side: market_bet_pct, ev, edge must be recomputed for the away perspective.
        if best_h2h_away is not None and calib_win_prob is not None:
            away_dec = best_h2h_away.get("decimal")
            away_mkt_pct_home = best_h2h_away.get("market_bet_pct")
            away_mkt_pct = (1.0 - away_mkt_pct_home) if away_mkt_pct_home is not None else None
            away_model_prob = 1.0 - calib_win_prob
            away_ev = None
            away_edge = None
            if away_dec is not None and away_model_prob is not None:
                away_ev = round(away_model_prob * (away_dec - 1.0) - (1.0 - away_model_prob), 4)
            if away_mkt_pct is not None:
                away_edge = round(away_model_prob - away_mkt_pct, 4)
            best_h2h_away.update({
                "market_bet_pct": round(away_mkt_pct, 4) if away_mkt_pct is not None else None,
                "ev": away_ev,
                "edge": away_edge,
                "breakeven_american": best_h2h_away.get("breakeven_american"),
            })

        best_totals_over = None
        best_totals_under = None
        us_tot_rows = [r for r in totals_rows if not r.get("is_sharp_reference") and r.get("over_american") is not None]
        if us_tot_rows:
            best_over_row = max(us_tot_rows, key=lambda r: r.get("over_american") or -9999)
            if best_over_row.get("over_american") is not None:
                best_totals_over = {
                    "book_key": best_over_row["book_key"],
                    "book_name": best_over_row["book_name"],
                    "line": best_over_row["line"],
                    "american": best_over_row["over_american"],
                    "decimal": best_over_row.get("over_decimal"),
                    "market_bet_pct": best_over_row.get("market_bet_pct_over"),
                    "model_prob": best_over_row.get("model_prob_over"),
                    "ev": best_over_row.get("ev_over"),
                    "edge": best_over_row.get("edge_over"),
                    "breakeven_american": best_over_row.get("breakeven_american_over"),
                }
            us_tot_under = [r for r in us_tot_rows if r.get("under_american") is not None]
            if us_tot_under:
                best_under_row = max(us_tot_under, key=lambda r: r.get("under_american") or -9999)
                if best_under_row.get("under_american") is not None:
                    under_mkt = best_under_row.get("market_bet_pct_over")
                    under_mkt_pct = (1.0 - under_mkt) if under_mkt is not None else None
                    best_totals_under = {
                        "book_key": best_under_row["book_key"],
                        "book_name": best_under_row["book_name"],
                        "line": best_under_row["line"],
                        "american": best_under_row["under_american"],
                        "decimal": best_under_row.get("under_decimal"),
                        "market_bet_pct": round(under_mkt_pct, 4) if under_mkt_pct is not None else None,
                        "model_prob": best_under_row.get("model_prob_under"),
                        "ev": best_under_row.get("ev_under"),
                        "edge": best_under_row.get("edge_over") * -1 if best_under_row.get("edge_over") is not None else None,
                        "breakeven_american": best_under_row.get("breakeven_american_under"),
                    }
                    # Recompute edge for under: model_prob_under - market_bet_pct_under
                    under_model_p = best_under_row.get("model_prob_under")
                    if under_model_p is not None and under_mkt_pct is not None:
                        best_totals_under["edge"] = round(under_model_p - under_mkt_pct, 4)

        result[gp] = {
            "game_pk": gp,
            "home_team": home_team,
            "away_team": away_team,
            "pred_total_runs": round(pred_mu, 2) if pred_mu is not None else None,
            "pred_total_runs_scale": round(pred_scale, 4) if pred_scale is not None else None,
            "h2h": h2h_rows,
            "totals": totals_rows,
            "best_h2h_home": best_h2h_home,
            "best_h2h_away": best_h2h_away,
            "best_totals_over": best_totals_over,
            "best_totals_under": best_totals_under,
        }

    return result


def _compute_line_shopping_payload(
    book_odds_map: dict[int, dict],
    ev_rows: list[dict],
) -> dict:
    """E9.11 — assemble the +EV line-shopping view from pre-computed book-odds payloads.

    Returns a dict matching LineshoppingResponse schema:
    { plays: [...], total: int, is_preliminary: bool }

    Filters to plays where model_prob > best US book de-vigged prob (positive edge).
    Sorted by edge descending (largest first).
    is_preliminary=True when any ev_row has prediction_type='morning'.
    """
    # Index ev metadata by game_pk for game_date, game_start_utc, is_preliminary
    ev_meta: dict[int, dict] = {}
    is_preliminary = False
    for r in ev_rows:
        gp = r.get("GAME_PK")
        if gp is None:
            continue
        ev_meta.setdefault(gp, r)
        if (r.get("PREDICTION_TYPE") or "") == "morning":
            is_preliminary = True

    plays = []

    for gp, payload in book_odds_map.items():
        meta = ev_meta.get(gp, {})
        game_date = str(meta.get("GAME_DATE") or "")
        game_start_utc = _ts(meta.get("GAME_START_UTC"))
        home_team = payload.get("home_team")
        away_team = payload.get("away_team")

        # Pinnacle de-vigged fair values for the anchor column
        pinnacle_h2h = next(
            (r for r in (payload.get("h2h") or []) if r.get("book_key") == "pinnacle"), {}
        )
        pinnacle_totals_over = next(
            (r for r in (payload.get("totals") or []) if r.get("book_key") == "pinnacle"), {}
        )

        pinn_h2h_home = pinnacle_h2h.get("market_bet_pct_home")
        pinn_h2h_away = (1.0 - pinn_h2h_home) if pinn_h2h_home is not None else None
        pinn_totals_over = pinnacle_totals_over.get("market_bet_pct_over")
        pinn_totals_under = (1.0 - pinn_totals_over) if pinn_totals_over is not None else None

        # H2H home side
        bph = payload.get("best_h2h_home")
        if bph and (bph.get("edge") or 0) > 0 and bph.get("best_devigged_prob") is None:
            # market_bet_pct is the de-vigged prob for this side
            plays.append({
                "game_pk": gp,
                "game_date": game_date,
                "game_start_utc": game_start_utc,
                "home_team": home_team,
                "away_team": away_team,
                "market_type": "h2h",
                "side": "home",
                "model_prob": round(bph["edge"] + (bph.get("market_bet_pct") or 0), 4),
                "best_book_key": bph["book_key"],
                "best_book_name": bph["book_name"],
                "best_american": bph["american"],
                "best_devigged_prob": round(bph.get("market_bet_pct") or 0, 4),
                "edge": round(bph["edge"], 4),
                "ev": bph.get("ev"),
                "breakeven_american": bph.get("breakeven_american"),
                "pinnacle_devigged_prob": round(pinn_h2h_home, 4) if pinn_h2h_home is not None else None,
            })
        elif bph and (bph.get("edge") or 0) > 0:
            # Already has best_devigged_prob from a prior path; rebuild correctly
            model_prob = round((bph.get("edge") or 0) + (bph.get("market_bet_pct") or 0), 4)
            plays.append({
                "game_pk": gp,
                "game_date": game_date,
                "game_start_utc": game_start_utc,
                "home_team": home_team,
                "away_team": away_team,
                "market_type": "h2h",
                "side": "home",
                "model_prob": model_prob,
                "best_book_key": bph["book_key"],
                "best_book_name": bph["book_name"],
                "best_american": bph["american"],
                "best_devigged_prob": round(bph.get("market_bet_pct") or 0, 4),
                "edge": round(bph["edge"], 4),
                "ev": bph.get("ev"),
                "breakeven_american": bph.get("breakeven_american"),
                "pinnacle_devigged_prob": round(pinn_h2h_home, 4) if pinn_h2h_home is not None else None,
            })

        # H2H away side
        bpa = payload.get("best_h2h_away")
        if bpa and (bpa.get("edge") or 0) > 0:
            model_prob = round((bpa.get("edge") or 0) + (bpa.get("market_bet_pct") or 0), 4)
            plays.append({
                "game_pk": gp,
                "game_date": game_date,
                "game_start_utc": game_start_utc,
                "home_team": home_team,
                "away_team": away_team,
                "market_type": "h2h",
                "side": "away",
                "model_prob": model_prob,
                "best_book_key": bpa["book_key"],
                "best_book_name": bpa["book_name"],
                "best_american": bpa["american"],
                "best_devigged_prob": round(bpa.get("market_bet_pct") or 0, 4),
                "edge": round(bpa["edge"], 4),
                "ev": bpa.get("ev"),
                "breakeven_american": bpa.get("breakeven_american"),
                "pinnacle_devigged_prob": round(pinn_h2h_away, 4) if pinn_h2h_away is not None else None,
            })

        # Totals over
        bto = payload.get("best_totals_over")
        if bto and (bto.get("edge") or 0) > 0:
            model_prob = round((bto.get("edge") or 0) + (bto.get("market_bet_pct") or 0), 4)
            plays.append({
                "game_pk": gp,
                "game_date": game_date,
                "game_start_utc": game_start_utc,
                "home_team": home_team,
                "away_team": away_team,
                "market_type": "totals",
                "side": "over",
                "model_prob": model_prob,
                "best_book_key": bto["book_key"],
                "best_book_name": bto["book_name"],
                "best_american": bto["american"],
                "best_devigged_prob": round(bto.get("market_bet_pct") or 0, 4),
                "edge": round(bto["edge"], 4),
                "ev": bto.get("ev"),
                "breakeven_american": bto.get("breakeven_american"),
                "pinnacle_devigged_prob": round(pinn_totals_over, 4) if pinn_totals_over is not None else None,
            })

        # Totals under
        btu = payload.get("best_totals_under")
        if btu and (btu.get("edge") or 0) > 0:
            model_prob = round((btu.get("edge") or 0) + (btu.get("market_bet_pct") or 0), 4)
            plays.append({
                "game_pk": gp,
                "game_date": game_date,
                "game_start_utc": game_start_utc,
                "home_team": home_team,
                "away_team": away_team,
                "market_type": "totals",
                "side": "under",
                "model_prob": model_prob,
                "best_book_key": btu["book_key"],
                "best_book_name": btu["book_name"],
                "best_american": btu["american"],
                "best_devigged_prob": round(btu.get("market_bet_pct") or 0, 4),
                "edge": round(btu["edge"], 4),
                "ev": btu.get("ev"),
                "breakeven_american": btu.get("breakeven_american"),
                "pinnacle_devigged_prob": round(pinn_totals_under, 4) if pinn_totals_under is not None else None,
            })

    plays.sort(key=lambda p: -(p.get("edge") or 0))
    return {"plays": plays, "total": len(plays), "is_preliminary": is_preliminary}


def _assemble_game_detail_payloads(sf, game_pks: list[int], final_game_pks: set[int]) -> dict[int, tuple[dict, bool]]:
    """Runs all 12 batch queries and assembles per-game detail dicts.

    Returns {game_pk: (payload_dict, is_final)}.
    """
    log.info("Assembling game detail for %d games", len(game_pks))

    # Run all 13 batch queries
    status_rows     = _sf_query_batch(sf, _GAME_STATUS_BATCH, game_pks)
    starter_rows    = _sf_query_batch(sf, _STARTERS_BATCH, game_pks)
    sp_last3_rows    = _sf_query_batch(sf, _SP_LAST3_BATCH, game_pks)
    bovada_rows     = _sf_query_batch(sf, _BOVADA_BATCH, game_pks)
    features_rows   = _sf_query_batch(sf, _TEAM_FEATURES_BATCH, game_pks)
    lineup_rows     = _sf_query_batch(sf, _LINEUP_BATCH, game_pks)
    box_score_rows  = _sf_query_batch(sf, _BOX_SCORE_BATCH, game_pks)
    weather_rows    = _sf_query_batch(sf, _WEATHER_BATCH, game_pks)
    pb_rows         = _sf_query_batch(sf, _PUBLIC_BETTING_BATCH, game_pks)
    lm_rows         = _sf_query_batch(sf, _LINE_MOVEMENT_BATCH, game_pks)
    lm_series_rows  = _sf_query_batch(sf, _LINE_MOVEMENT_SERIES_BATCH, game_pks)
    form_rows       = _sf_query_batch(sf, _RECENT_FORM_BATCH, game_pks)
    h2h_rows        = _sf_query_batch(sf, _H2H_BATCH, game_pks)
    umpire_rows     = _sf_query_batch(sf, _UMPIRE_BATCH, game_pks)
    pick_rows       = _sf_query_batch(sf, _GAME_PICKS_BATCH, game_pks)
    expl_rows       = _sf_query_batch(sf, _EXPLANATION_BATCH, game_pks)

    # Index by game_pk
    status_by_pk   = {r["GAME_PK"]: r for r in status_rows}
    features_by_pk = {r["GAME_PK"]: r for r in features_rows}
    weather_by_pk  = {r["GAME_PK"]: r for r in weather_rows}
    pb_by_pk       = {r["GAME_PK"]: r for r in pb_rows}
    lm_by_pk       = {r["GAME_PK"]: r for r in lm_rows}
    h2h_by_pk      = {r["GAME_PK"]: r for r in h2h_rows}
    umpire_by_pk   = {r["GAME_PK"]: r for r in umpire_rows}
    expl_by_pk     = {r["GAME_PK"]: r for r in expl_rows}

    starters_by_pk  = defaultdict(list)
    for r in starter_rows:
        starters_by_pk[r["GAME_PK"]].append(r)

    # E9.36 — last-3-starts keyed by (game_pk, side); rows already ordered newest-first.
    sp_last3_by_pk_side: dict = defaultdict(list)
    for r in sp_last3_rows:
        outs = _int(r.get("OUTS_RECORDED"))
        sp_last3_by_pk_side[(r["GAME_PK"], str(r.get("SIDE", "")).lower())].append({
            "date": str(r["START_DATE"]),
            "opp": r.get("OPPOSING_TEAM"),
            "home_away": "home" if r.get("IS_HOME_TEAM") else "away",
            "ip": (f"{outs // 3}.{outs % 3}" if outs is not None else None),
            "k": _int(r.get("STRIKEOUTS")),
            "bb": _int(r.get("WALKS")),
            "h": _int(r.get("HITS_ALLOWED")),
            "r": _int(r.get("RUNS_ALLOWED")),
            "hr": _int(r.get("HOME_RUNS_ALLOWED")),
        })

    bovada_by_pk = defaultdict(list)
    for r in bovada_rows:
        bovada_by_pk[r["GAME_PK"]].append(r)

    lineup_by_pk = defaultdict(list)
    for r in lineup_rows:
        lineup_by_pk[r["GAME_PK"]].append(r)

    box_score_by_pk = defaultdict(dict)
    for r in box_score_rows:
        bid = r.get("BATTER_ID")
        if bid is not None:
            box_score_by_pk[r["GAME_PK"]][int(bid)] = r

    form_by_pk = defaultdict(list)
    for r in form_rows:
        form_by_pk[r["GAME_PK"]].append(r)

    # E9.37 — intraday line-movement snapshots, kept in ascending ts order per game.
    lm_series_by_pk = defaultdict(list)
    for r in lm_series_rows:
        lm_series_by_pk[r["GAME_PK"]].append(r)

    picks_by_pk = defaultdict(list)
    for r in pick_rows:
        picks_by_pk[r["GAME_PK"]].append(r)

    result: dict[int, tuple[dict, bool]] = {}

    for gp in game_pks:
        # ── picks ──
        picks_out = [
            {
                "game_pk": r["GAME_PK"], "game_date": str(r["GAME_DATE"]),
                "market_type": r["MARKET_TYPE"], "model_prob": r.get("MODEL_PROB"),
                "bovada_devig_prob": r.get("BOVADA_DEVIG_PROB"), "edge": r.get("EDGE"),
                "game_conviction_score": r.get("GAME_CONVICTION_SCORE"),
                "win_prob_ci_low": r.get("WIN_PROB_CI_LOW"), "win_prob_ci_high": r.get("WIN_PROB_CI_HIGH"),
                "win_prob_ci_width": r.get("WIN_PROB_CI_WIDTH"), "gate_signals_met": r.get("GATE_SIGNALS_MET"),
                "meta_p_clv_positive": r.get("META_P_CLV_POSITIVE"),
                "meta_ci_low": r.get("META_CI_LOW"), "meta_ci_high": r.get("META_CI_HIGH"),
                "lineup_confirmed": r.get("LINEUP_CONFIRMED"), "home_team": r.get("HOME_TEAM"),
                "away_team": r.get("AWAY_TEAM"), "pick_side": r.get("PICK_SIDE"),
                "game_start_utc": _ts(r.get("GAME_START_UTC")),
                "model_total_runs": r.get("MODEL_TOTAL_RUNS"), "market_total_line": r.get("MARKET_TOTAL_LINE"),
                "predicted_at": _ts(r.get("PREDICTED_AT")),
            }
            for r in picks_by_pk[gp]
        ]

        # ── game status ──
        game_score = None
        home_team_name = None
        away_team_name = None
        sr = status_by_pk.get(gp)
        if sr:
            state = str(sr.get("ABSTRACT_GAME_STATE") or "Preview")
            hw_raw = _int(sr.get("HOME_WINS"))
            hl_raw = _int(sr.get("HOME_LOSSES"))
            aw_raw = _int(sr.get("AWAY_WINS"))
            al_raw = _int(sr.get("AWAY_LOSSES"))
            if state == "Final" and hw_raw is not None:
                home_won = bool(sr.get("HOME_IS_WINNER"))
                hw = hw_raw - (1 if home_won else 0)
                hl = hl_raw - (0 if home_won else 1) if hl_raw is not None else None
                aw = aw_raw - (0 if home_won else 1) if aw_raw is not None else None
                al = al_raw - (1 if home_won else 0) if al_raw is not None else None
            else:
                hw, hl, aw, al = hw_raw, hl_raw, aw_raw, al_raw
            game_score = {
                "home_score": _int(sr.get("HOME_SCORE")),
                "away_score": _int(sr.get("AWAY_SCORE")),
                "status": state if state in ("Live", "Final") else "Preview",
                "home_wins": hw, "home_losses": hl,
                "away_wins": aw, "away_losses": al,
                "home_pyth_pct": _flt(sr.get("HOME_PYTH_PCT")),
                "home_pyth_residual": _flt(sr.get("HOME_PYTH_RESIDUAL")),
                "away_pyth_pct": _flt(sr.get("AWAY_PYTH_PCT")),
                "away_pyth_residual": _flt(sr.get("AWAY_PYTH_RESIDUAL")),
            }
            home_team_name = sr.get("HOME_TEAM_NAME")
            away_team_name = sr.get("AWAY_TEAM_NAME")

        is_final = game_score is not None and game_score.get("status") == "Final"

        # ── starters ──
        starters = None
        home_sp = None
        away_sp = None
        for row in starters_by_pk[gp]:
            side = str(row.get("SIDE", "")).lower()
            sp = {
                "pitcher_id": row.get("PROBABLE_PITCHER_ID"),
                "name": row.get("PROBABLE_PITCHER_NAME"),
                "is_opener": bool(row.get("IS_OPENER", False)),
                "season": row.get("CURRENT_SEASON_YEAR"),
                "starts": row.get("CURRENT_STARTS"),
                "ra9": row.get("CURRENT_RA9"), "whip": row.get("CURRENT_WHIP"),
                "k_pct": row.get("CURRENT_K_PCT"),
                "prior_season": row.get("PRIOR_SEASON_YEAR"),
                "prior_starts": row.get("PRIOR_STARTS"),
                "prior_ra9": row.get("PRIOR_RA9"), "prior_whip": row.get("PRIOR_WHIP"),
                "prior_k_pct": row.get("PRIOR_K_PCT"),
                "last_3_starts": sp_last3_by_pk_side.get((gp, side), []),
            }
            if side == "home":
                home_sp = sp
            else:
                away_sp = sp
        if home_sp or away_sp:
            starters = {"home": home_sp, "away": away_sp}

        # ── Bovada lines ──
        bovada_lines = None
        bov = bovada_by_pk[gp]
        h2h_bov = [r for r in bov if str(r.get("MARKET_KEY", "")).lower() == "h2h"]
        tot_bov = [r for r in bov if str(r.get("MARKET_KEY", "")).lower() == "totals"]
        bov_h2h = None
        if h2h_bov:
            home_r = next((r for r in h2h_bov if r.get("IS_HOME_OUTCOME")), None)
            away_r = next((r for r in h2h_bov if not r.get("IS_HOME_OUTCOME")), None)
            snap = str(max(r["INGESTION_TS"] for r in h2h_bov)) if h2h_bov else None
            bov_h2h = {
                "home_american": _int(home_r["OUTCOME_PRICE_AMERICAN"]) if home_r and home_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "away_american": _int(away_r["OUTCOME_PRICE_AMERICAN"]) if away_r and away_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "snapshot_utc": snap,
            }
        bov_totals = None
        if tot_bov:
            over_r  = next((r for r in tot_bov if str(r.get("OUTCOME_NAME", "")).lower() == "over"), None)
            under_r = next((r for r in tot_bov if str(r.get("OUTCOME_NAME", "")).lower() == "under"), None)
            snap = str(max(r["INGESTION_TS"] for r in tot_bov)) if tot_bov else None
            bov_totals = {
                "line": _flt(over_r["OUTCOME_POINT"]) if over_r and over_r.get("OUTCOME_POINT") is not None else None,
                "over_american": _int(over_r["OUTCOME_PRICE_AMERICAN"]) if over_r and over_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "under_american": _int(under_r["OUTCOME_PRICE_AMERICAN"]) if under_r and under_r.get("OUTCOME_PRICE_AMERICAN") is not None else None,
                "snapshot_utc": snap,
            }
        if bov_h2h or bov_totals:
            bovada_lines = {"h2h": bov_h2h, "totals": bov_totals}

        # ── team features ──
        team_features = None
        fr = features_by_pk.get(gp)
        if fr:
            team_features = {
                "home": {
                    "off_woba_30d": _flt(fr.get("HOME_OFF_WOBA_30D")),
                    "off_xwoba_30d": _flt(fr.get("HOME_OFF_XWOBA_30D")),
                    "off_runs_per_game_30d": _flt(fr.get("HOME_OFF_RUNS_PER_GAME_30D")),
                    "starter_xwoba_against_30d": _flt(fr.get("HOME_STARTER_XWOBA_AGAINST_30D")),
                    "starter_k_pct_30d": _flt(fr.get("HOME_STARTER_K_PCT_30D")),
                    "starter_hand": fr.get("HOME_STARTER_PITCHER_HAND"),
                    "lineup_vs_sp_xwoba_adj": _flt(fr.get("HOME_LINEUP_VS_AWAY_STARTER_XWOBA_ADJ")),
                    "bp_xwoba_against_14d": _flt(fr.get("HOME_BP_XWOBA_AGAINST_14D")),
                    "bp_innings_pitched_14d": _flt(fr.get("HOME_BP_INNINGS_PITCHED_14D")),
                    "days_rest": _flt(fr.get("HOME_DAYS_REST")),
                },
                "away": {
                    "off_woba_30d": _flt(fr.get("AWAY_OFF_WOBA_30D")),
                    "off_xwoba_30d": _flt(fr.get("AWAY_OFF_XWOBA_30D")),
                    "off_runs_per_game_30d": _flt(fr.get("AWAY_OFF_RUNS_PER_GAME_30D")),
                    "starter_xwoba_against_30d": _flt(fr.get("AWAY_STARTER_XWOBA_AGAINST_30D")),
                    "starter_k_pct_30d": _flt(fr.get("AWAY_STARTER_K_PCT_30D")),
                    "starter_hand": fr.get("AWAY_STARTER_PITCHER_HAND"),
                    "lineup_vs_sp_xwoba_adj": _flt(fr.get("AWAY_LINEUP_VS_HOME_STARTER_XWOBA_ADJ")),
                    "bp_xwoba_against_14d": _flt(fr.get("AWAY_BP_XWOBA_AGAINST_14D")),
                    "bp_innings_pitched_14d": _flt(fr.get("AWAY_BP_INNINGS_PITCHED_14D")),
                    "days_rest": _flt(fr.get("AWAY_DAYS_REST")),
                },
                "park_run_factor": _flt(fr.get("PARK_RUN_FACTOR_3YR")),
                "elo_diff": _flt(fr.get("ELO_DIFF")),
            }

        # ── lineups + box score ──
        lineups = None
        home_players = []
        away_players = []
        bs_map = box_score_by_pk[gp] if is_final else {}
        for row in lineup_by_pk[gp]:
            pid = row.get("PLAYER_ID")
            bs = bs_map.get(int(pid)) if pid is not None else None
            player = {
                "slot": _int(row["SLOT"]), "player_id": _int(pid),
                "player_name": row.get("PLAYER_NAME"), "position": row.get("POSITION"),
                "season_ops": _flt(row.get("SEASON_OPS")), "season_xwoba": _flt(row.get("SEASON_XWOBA")),
                "game_pa": _int(bs["PA"]) if bs and bs.get("PA") is not None else None,
                "game_ab": _int(bs["AB"]) if bs and bs.get("AB") is not None else None,
                "game_h": _int(bs["H"]) if bs and bs.get("H") is not None else None,
                "game_k": _int(bs["K"]) if bs and bs.get("K") is not None else None,
                "game_bb": _int(bs["BB"]) if bs and bs.get("BB") is not None else None,
                "game_hr": _int(bs["HR"]) if bs and bs.get("HR") is not None else None,
                "game_xwoba": _flt(bs["XWOBA_GAME"]) if bs and bs.get("XWOBA_GAME") is not None else None,
            }
            if str(row.get("HOME_AWAY", "")).lower() == "home":
                home_players.append(player)
            else:
                away_players.append(player)
        if home_players or away_players:
            lineups = {"home": home_players, "away": away_players}

        # ── weather ──
        weather = None
        wr = weather_by_pk.get(gp)
        if wr:
            weather = {
                "temp_f": _flt(wr.get("TEMP_F")), "wind_speed_mph": _flt(wr.get("WIND_SPEED_MPH")),
                "wind_component_mph": _flt(wr.get("WIND_COMPONENT_MPH")),
                "is_dome": bool(wr.get("IS_DOME", False)),
                "observation_type": wr.get("WEATHER_OBSERVATION_TYPE"),
            }

        # ── public betting ──
        public_betting = None
        pb = pb_by_pk.get(gp)
        if pb:
            public_betting = {
                "home_ml_money_pct": _flt(pb.get("HOME_ML_MONEY_PCT")),
                "away_ml_money_pct": _flt(pb.get("AWAY_ML_MONEY_PCT")),
                "home_ml_ticket_pct": _flt(pb.get("HOME_ML_TICKET_PCT")),
                "away_ml_ticket_pct": _flt(pb.get("AWAY_ML_TICKET_PCT")),
                "over_money_pct": _flt(pb.get("OVER_MONEY_PCT")),
                "under_money_pct": _flt(pb.get("UNDER_MONEY_PCT")),
                "over_ticket_pct": _flt(pb.get("OVER_TICKET_PCT")),
                "under_ticket_pct": _flt(pb.get("UNDER_TICKET_PCT")),
                "ml_sharp_signal": _flt(pb.get("ML_SHARP_SIGNAL")),
                "total_sharp_signal": _flt(pb.get("TOTAL_SHARP_SIGNAL")),
            }

        # ── line movement ──
        line_movement = None
        lm = lm_by_pk.get(gp)
        if lm:
            line_movement = {
                "open_home_win_prob": _flt(lm.get("OPEN_HOME_WIN_PROB")),
                "pregame_home_win_prob": _flt(lm.get("PREGAME_HOME_WIN_PROB")),
                "h2h_line_movement": _flt(lm.get("H2H_LINE_MOVEMENT")),
                "open_total_line": _flt(lm.get("OPEN_TOTAL_LINE")),
                "pregame_total_line": _flt(lm.get("PREGAME_TOTAL_LINE")),
                "total_line_movement": _flt(lm.get("TOTAL_LINE_MOVEMENT")),
            }

        # ── line-movement series (E9.37; per-market open→current, Bovada) ──
        line_movement_series = _build_line_movement_series(lm_series_by_pk.get(gp, []))

        # ── recent form + H2H ──
        game_context = None
        home_form = None
        away_form = None
        for row in form_by_pk[gp]:
            form = {
                "l5_wins": _int(row.get("L5_WINS")), "l5_losses": _int(row.get("L5_LOSSES")),
                "l5_games": _int(row.get("L5_GAMES")), "l10_wins": _int(row.get("L10_WINS")),
                "l10_losses": _int(row.get("L10_LOSSES")), "l10_games": _int(row.get("L10_GAMES")),
            }
            if str(row.get("TEAM_SIDE", "")).lower() == "home":
                home_form = form
            else:
                away_form = form
        h2h_rec = None
        hr = h2h_by_pk.get(gp)
        if hr:
            gp_count = _int(hr.get("GAMES_PLAYED"))
            if gp_count and gp_count > 0:
                h2h_rec = {
                    "home_wins": _int(hr.get("HOME_WINS")), "away_wins": _int(hr.get("AWAY_WINS")),
                    "games_played": gp_count, "avg_total_runs": _flt(hr.get("AVG_TOTAL_RUNS")),
                }
        if home_form or away_form or h2h_rec:
            game_context = {"home_form": home_form, "away_form": away_form, "h2h": h2h_rec}

        # ── umpire ──
        umpire = None
        ur = umpire_by_pk.get(gp)
        if ur:
            umpire = {
                "name": ur.get("UMPIRE_NAME"), "k_pct_zscore": _flt(ur.get("UMP_K_PCT_ZSCORE")),
                "runs_per_game_zscore": _flt(ur.get("UMP_RUNS_PER_GAME_ZSCORE")),
                "run_impact_zscore": _flt(ur.get("UMP_RUN_IMPACT_ZSCORE")),
                "bb_pct_zscore": _flt(ur.get("UMP_BB_PCT_ZSCORE")),
                "games_sample": _int(ur.get("UMP_GAMES_SAMPLE")),
            }

        # ── pick explanation + narrative (Story 30.15) ──
        pick_explanation = None
        pick_narrative = None
        er = expl_by_pk.get(gp)
        if er:
            raw_expl = er.get("PICK_EXPLANATION")
            if raw_expl:
                try:
                    pick_explanation = json.loads(raw_expl) if isinstance(raw_expl, str) else raw_expl
                except Exception:
                    pass
            pick_narrative = er.get("PICK_NARRATIVE")

        payload = {
            "picks": picks_out, "total": len(picks_out),
            "home_team_name": home_team_name, "away_team_name": away_team_name,
            "game_score": game_score, "starters": starters, "bovada_lines": bovada_lines,
            "team_features": team_features, "lineups": lineups, "weather": weather,
            "public_betting": public_betting, "line_movement": line_movement,
            "line_movement_series": line_movement_series,
            "umpire": umpire, "game_context": game_context,
            "pick_explanation": pick_explanation, "pick_narrative": pick_narrative,
        }
        result[gp] = (payload, is_final)

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write Snowflake prediction outputs to the PG serving store and S3 cache.",
    )
    parser.add_argument(
        "--picks", action="store_true",
        help="Write picks/today + picks/ev cache blobs.",
    )
    parser.add_argument(
        "--game-detail", action="store_true",
        help="Write per-game detail blobs (picks/game/<pk>). Requires --picks or pre-existing picks_rows.",
    )
    parser.add_argument(
        "--history", action="store_true",
        help="Write picks/history.",
    )
    parser.add_argument(
        "--performance", action="store_true",
        help="Write performance/summary.",
    )
    parser.add_argument(
        "--teams", action="store_true",
        help="Write team profile blobs.",
    )
    parser.add_argument(
        "--players", action="store_true",
        help="Write player profile blobs.",
    )
    parser.add_argument(
        "--book-odds", action="store_true",
        help="Write per-book odds comparison blobs (A0.4.32). Runs alongside --picks.",
    )
    parser.add_argument(
        "--date", default=None,
        help="Override today's date (YYYY-MM-DD). Useful for backfilling or testing with yesterday's predictions.",
    )
    parser.add_argument(
        "--s3", action="store_true",
        help=("Read serving data from the S3 lakehouse via DuckDB instead of Snowflake "
              "(E11.1-W7b). Gated/transitional, OFF by default; needs AWS creds (DuckDB "
              "credential_chain), NOT the Snowflake env. Writes are unchanged (DynamoDB / S3)."),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    # If no section flags given, run everything.
    run_all = not any([args.picks, args.game_detail, args.history,
                       args.performance, args.teams, args.players,
                       getattr(args, "book_odds", False)])

    # INC-22 — resolve "today" in the canonical US baseball-day TZ (LA), NOT the UTC box
    # clock. A naive date.today() on the UTC box rolls to tomorrow at 00:00 UTC (= evening
    # US time), so the EVENING intraday serving write resolved an empty future date and
    # silently skipped the live slate. --date still overrides (backfill / mitigation).
    today = args.date if args.date else current_game_date_iso()
    bucket = os.environ.get("CACHE_BUCKET")

    # E11.1-W7b: `sf` is the read connection — DuckDB-over-S3 with --s3 (AWS creds only),
    # else the default Snowflake connection. Every read helper is polymorphic on it; writes
    # are unaffected. Both connection types expose .close() (called at the end of main()).
    try:
        sf = _duck_connect_and_register() if args.s3 else _sf_connect()
    except Exception:
        log.exception("%s connection failed", "DuckDB-over-S3 (--s3)" if args.s3 else "Snowflake")
        return 1

    pg = _pg_connect()
    errors = 0

    # ── picks/today ─────────────────────────────────────────────────────────
    picks_rows: list[dict] = []
    ev_rows: list[dict] = []
    if run_all or args.picks or args.game_detail:
        try:
            picks_rows = _sf_query(sf, _PICKS_TODAY_SQL, {"today": today})
            fresh_rows = _sf_query(sf, _FRESHNESS_SQL, {"today": today})
            if not picks_rows:
                _alert_empty_serving_date(sf, today)  # INC-22 — ALERT-loud, was a benign log.info
            elif run_all or args.picks:
                payload = _build_picks_payload(picks_rows, fresh_rows)
                if pg:
                    _pg_set_cache(pg, "picks/today", today, payload)
                    log.info("DynamoDB: picks/today written (%d picks)", len(picks_rows))
                if bucket:
                    _write_s3(bucket, f"api-cache/{today}/picks/today.json", payload)
        except Exception:
            log.exception("Failed to write picks/today")
            errors += 1

        # ── picks/featured ───────────────────────────────────────────────────
        # Prevents /picks/featured from querying Snowflake on every request.
        # Runs 2 LIMIT-1 queries + 1 targeted explanation lookup; cheap vs per-request cost.
        if pg and (run_all or args.picks):
            try:
                _feat_rows = _sf_query(sf, _FEATURED_TODAY_SERVING_SQL, {"today": today})
                _yest_rows = _sf_query(sf, _FEATURED_YESTERDAY_SERVING_SQL, {"today": today})
                if _feat_rows:
                    fr = _feat_rows[0]
                    gp = fr.get("GAME_PK")
                    # Fetch explanation for the featured game (single row lookup)
                    _expl_rows = _sf_query(sf, _EXPLANATION_BATCH.format(game_pk_list=str(gp))) if gp else []
                    _expl_data = _expl_rows[0] if _expl_rows else {}
                    # Parse pick_explanation JSON
                    _expl_dict = None
                    _pick_narrative = None
                    if _expl_data:
                        _raw_expl = _expl_data.get("PICK_EXPLANATION")
                        if _raw_expl:
                            try:
                                _expl_dict = json.loads(_raw_expl) if isinstance(_raw_expl, str) else _raw_expl
                            except Exception:
                                pass
                        _pick_narrative = _expl_data.get("PICK_NARRATIVE")
                    # Extract top 3 drivers for both markets
                    _market_type = fr.get("MARKET_TYPE") or ""
                    _top_drivers_h2h = None
                    _top_drivers_totals = None
                    if _expl_dict:
                        _h2h_t = (_expl_dict.get("targets") or {}).get("home_win")
                        if _h2h_t:
                            _top_drivers_h2h = (_h2h_t.get("drivers") or [])[:3]
                        _tot_t = (_expl_dict.get("targets") or {}).get("total_runs")
                        if _tot_t:
                            _top_drivers_totals = (_tot_t.get("drivers") or [])[:3]
                    # Build yesterday result
                    _yesterday = None
                    if _yest_rows:
                        yr = _yest_rows[0]
                        _outcome_flag = yr.get("ACTUAL_OUTCOME")
                        _pick_side = (yr.get("PICK_SIDE") or "").lower()
                        if _outcome_flag is None:
                            # Game not yet settled (e.g. postponed or CLV mart not refreshed)
                            _status = "pending"
                            _outcome_str = "Pending"
                        else:
                            # actual_outcome semantics:
                            #   h2h:    1 = home team won  (home-perspective CLV)
                            #   totals: 1 = over hit
                            # Map to "did the picked side win?"
                            if _pick_side in ("home", "over"):
                                _bet_won = int(_outcome_flag) == 1
                            elif _pick_side in ("away", "under"):
                                _bet_won = int(_outcome_flag) == 0
                            else:
                                _bet_won = bool(_outcome_flag)
                            _status = "win" if _bet_won else "loss"
                            _outcome_str = "Won" if _bet_won else "Lost"
                        _yesterday = {
                            "matchup": f"{yr.get('AWAY_TEAM') or ''} @ {yr.get('HOME_TEAM') or ''}",
                            "market_type": yr.get("MARKET_TYPE") or "",
                            "outcome": _outcome_str,
                            "status": _status,
                        }
                    # game_time_et
                    _game_time_et = None
                    _gdt = fr.get("GAME_DATETIME")
                    if _gdt is not None:
                        try:
                            _ET_zone = ZoneInfo("America/New_York")
                            if _gdt.tzinfo is None:
                                _gdt = _gdt.replace(tzinfo=timezone.utc)
                            _game_time_et = _gdt.astimezone(_ET_zone).strftime("%-I:%M %p ET")
                        except Exception:
                            pass
                    # ai_summary
                    _model_prob = fr.get("MODEL_PROB")
                    _edge_raw = fr.get("EDGE")
                    _mp = round((_model_prob or 0) * 100, 1)
                    _ep = round((_edge_raw or 0) * 100, 1)
                    _sign = "+" if _ep >= 0 else ""
                    if _market_type == "h2h":
                        _ai_summary = (f"Model assigns {_mp}% win probability — "
                                       f"a {_sign}{_ep}pp edge over the Bovada closing line.")
                    else:
                        _ai_summary = (f"Totals model assigns {_mp}% probability this game goes over — "
                                       f"a {_sign}{_ep}pp edge over the consensus line.")
                    # pick_date
                    _game_date_raw = fr.get("GAME_DATE")
                    _pick_date = (_game_date_raw.isoformat() if hasattr(_game_date_raw, "isoformat")
                                  else str(_game_date_raw) if _game_date_raw else None)
                    _away = fr.get("AWAY_TEAM") or ""
                    _home = fr.get("HOME_TEAM") or ""
                    _prediction_type = fr.get("PREDICTION_TYPE") or ""
                    _featured_payload = {
                        "game_pk": gp,
                        "matchup": f"{_away} @ {_home}",
                        "game_time_et": _game_time_et,
                        "market_type": _market_type,
                        "edge": round(_edge_raw * 100, 2) if _edge_raw is not None else None,
                        "model_prob": _model_prob,
                        "market_prob": fr.get("MARKET_PROB"),
                        "ci_low": fr.get("WIN_PROB_CI_LOW"),
                        "ci_high": fr.get("WIN_PROB_CI_HIGH"),
                        "conviction_label": "HIGH CONVICTION",
                        "ai_summary": _ai_summary,
                        "yesterday": _yesterday,
                        "is_stale": False,
                        "is_preliminary": _prediction_type == "morning",
                        "pick_date": _pick_date,
                        "home_team": _home or None,
                        "away_team": _away or None,
                        "pick_side": fr.get("PICK_SIDE"),
                        "model_narrative": _pick_narrative,
                        "top_drivers_h2h": _top_drivers_h2h,
                        "top_drivers_totals": _top_drivers_totals,
                        "served_tier": (_expl_dict or {}).get("served_tier"),
                    }
                    _pg_set_cache(pg, "picks/featured", today, _featured_payload)
                    log.info("DynamoDB: picks/featured written (game_pk=%s, market=%s, narrative=%s)",
                             gp, _market_type, "yes" if _pick_narrative else "no")
                else:
                    log.info("No conviction picks for %s — skipping picks/featured cache write", today)
            except Exception:
                log.exception("Failed to write picks/featured")
                errors += 1

        # ── picks/ev ────────────────────────────────────────────────────────
        try:
            ev_rows = _sf_query(sf, _EV_TODAY_SQL, {"today": today})
            if not ev_rows:
                log.info("No EV rows for %s — skipping picks/ev cache write", today)
            elif run_all or args.picks:
                payload = _build_ev_payload(ev_rows)
                if pg:
                    _pg_set_cache(pg, "picks/ev", today, payload)
                    log.info("DynamoDB: picks/ev written (%d rows)", len(ev_rows))
                if bucket:
                    _write_s3(bucket, f"api-cache/{today}/picks/ev.json", payload)
        except Exception:
            log.exception("Failed to write picks/ev")
            errors += 1

        # ── daily_picks retired (INC-16-P2) ──────────────────────────────────
        # The legacy daily_picks table is gone; the backend never read it.
        # Portfolio filtering reads the picks/today blob + per-user bets in
        # DynamoDB, so no per-pick row write is needed here anymore.

    # ── picks/history ────────────────────────────────────────────────────────
    if run_all or args.history:
        try:
            history_rows = _sf_query(sf, _HISTORY_SQL)
            payload = _build_history_payload(history_rows)
            if pg:
                _pg_set_cache(pg, "picks/history", today, payload)
                log.info("DynamoDB: picks/history written (%d rows)", len(history_rows))
            if bucket:
                _write_s3(bucket, f"api-cache/{today}/picks/history.json", payload)
        except Exception:
            log.exception("Failed to write picks/history")
            errors += 1

    # ── performance/summary ──────────────────────────────────────────────────
    if run_all or args.performance:
        try:
            try:
                perf_rows = _sf_query(sf, _BANKROLL_SQL)
                source = "mart_bankroll_state"
            except Exception:
                log.warning("mart_bankroll_state unavailable — falling back")
                perf_rows = _sf_query(sf, _CLV_SUMMARY_SQL)
                source = "mart_clv_labeled_games"
            if not perf_rows:
                perf_rows = _sf_query(sf, _CLV_SUMMARY_SQL)
                source = "mart_clv_labeled_games"
            payload = _build_performance_payload(perf_rows, source)
            if pg:
                _pg_set_cache(pg, "performance/summary", today, payload)
                log.info("DynamoDB: performance/summary written (source=%s)", source)
            if bucket:
                _write_s3(bucket, f"api-cache/{today}/performance/summary.json", payload)
        except Exception:
            log.exception("Failed to write performance/summary")
            errors += 1

    # ── game detail blobs (one blob per game) ────────────────────────────────
    if run_all or args.game_detail:
        game_pks = list({r["GAME_PK"] for r in picks_rows} | {r["GAME_PK"] for r in ev_rows})
        if game_pks and pg:
            try:
                final_pks: set[int] = set()
                detail_map = _assemble_game_detail_payloads(sf, game_pks, final_pks)
                for gp, (detail_payload, is_final) in detail_map.items():
                    cache_key = f"picks/game/{gp}"
                    _has_expl = bool(detail_payload.get("pick_explanation"))
                    # INC-31: never FREEZE a Final game's blob PERMANENT while its lineups are
                    # null. The S3 stg_statsapi_lineups_wide parquet is re-exported only in the
                    # daily (morning) run, so an evening Final game read via --s3 can miss that
                    # slate's lineups → lineups=None. A permanent blob is never re-read, so that
                    # would serve null lineups FOREVER (the 26 frozen-null finals we found). Keep
                    # it date-scoped until lineups attach; the next cycle (post daily lineups_wide
                    # re-export) rebuilds it populated and it self-heals. A played game always has
                    # a lineup, so this only defers permanence, never suppresses it.
                    _ln = detail_payload.get("lineups") or {}
                    _lineups_ok = bool(_ln.get("home") or _ln.get("away"))
                    _permanent = is_final and _has_expl and _lineups_ok
                    _pg_set_cache(pg, cache_key, today, detail_payload, is_permanent=_permanent)
                    if bucket and is_final and _lineups_ok:
                        _write_s3(bucket, f"api-cache/permanent/{cache_key}.json", detail_payload)
                    elif bucket:
                        _write_s3(bucket, f"api-cache/{today}/{cache_key}.json", detail_payload)
                log.info("DynamoDB: game detail written for %d games", len(detail_map))
            except Exception:
                log.exception("Failed to write game detail blobs")
                errors += 1
        elif not game_pks:
            log.info("No game_pks resolved — skipping game detail (run --picks first or alongside --game-detail)")

    # ── per-book odds comparison (A0.4.32) ──────────────────────────────────────
    if (run_all or getattr(args, "book_odds", False)) and pg:
        book_pks = list({r["GAME_PK"] for r in picks_rows} | {r["GAME_PK"] for r in ev_rows})
        if not book_pks:
            # Standalone --book-odds run (no --picks): resolve game_pks directly from predictions.
            # (Module-level constant so the --s3 grep-driven view registration auto-discovers it.)
            try:
                pk_rows = _sf_query(sf, _STANDALONE_BOOK_PKS_SQL, {"today": today})
                book_pks = [r["GAME_PK"] for r in pk_rows]
                log.info("book-odds standalone: resolved %d game_pks for %s", len(book_pks), today)
            except Exception:
                log.warning("Failed to resolve standalone game_pks for book-odds")
        if book_pks:
            try:
                book_odds_map = _compute_book_odds_payloads(sf, book_pks)
                for gp, payload in book_odds_map.items():
                    cache_key = f"picks/book-odds/{gp}"
                    _pg_set_cache(pg, cache_key, today, payload, is_permanent=False)
                log.info("DynamoDB: book-odds written for %d games", len(book_odds_map))
                # E9.11 — write line-shopping payload (best price per play, sorted by edge)
                ls_payload = _compute_line_shopping_payload(book_odds_map, ev_rows)
                _pg_set_cache(pg, "picks/line-shopping", today, ls_payload, is_permanent=False)
                log.info("DynamoDB: line-shopping written (%d plays)", ls_payload["total"])
            except Exception:
                log.exception("Failed to write book-odds")
                errors += 1
        else:
            log.info("No game_pks resolved for %s — skipping book-odds", today)

    # ── team profiles ─────────────────────────────────────────────────────────
    if (run_all or args.teams) and pg:
        try:
            errors += write_team_profiles(sf, pg, today)
        except Exception:
            log.exception("Failed to write team profiles")
            errors += 1

    # ── player profiles ───────────────────────────────────────────────────────
    if (run_all or args.players) and pg:
        try:
            errors += write_player_profiles(sf, pg, today)
        except Exception:
            log.exception("Failed to write player profiles")
            errors += 1

    # ── INC-16-P6 daily heartbeat (dead-man switch source) ───────────────────
    # One tiny item the OFF-box deadman Lambda checks each morning: it proves the
    # serving cycle actually RAN today, which a raw "are there picks?" check can't
    # (0 picks on a legit off-day looks identical to a dead box). Best-effort —
    # never fail serving for the heartbeat.
    if pg and (run_all or args.picks):
        try:
            from datetime import datetime, timezone

            _n_picks = len(picks_rows) if "picks_rows" in locals() else None
            _now_iso = datetime.now(timezone.utc).isoformat()
            pg.put_item(Item={
                "pk": "ops",
                "sk": "heartbeat#daily",
                "value": json.dumps({
                    "date": today,
                    "n_picks": _n_picks,
                    "errors": errors,
                    "written_at": _now_iso,
                }),
                "is_permanent": True,
                "updated_at": _now_iso,
                "cache_date": today,
            })
            log.info("DynamoDB: ops/heartbeat#daily written (date=%s, n_picks=%s)", today, _n_picks)
        except Exception:
            log.warning("Failed to write daily heartbeat (non-fatal)", exc_info=True)

    sf.close()
    # `pg` is a boto3 DynamoDB Table (INC-16-P2) — no connection to close.

    return 0 if errors == 0 else 1


# ── Team profile SQL ──────────────────────────────────────────────────────────

_TEAM_SUMMARY_SQL = """
WITH current_record AS (
    SELECT *
    FROM baseball_data.betting.mart_team_season_record
    WHERE game_year = YEAR(CURRENT_DATE) AND is_current = TRUE
),
latest_offense AS (
    SELECT *
    FROM baseball_data.betting.mart_team_rolling_offense
    WHERE game_year = YEAR(CURRENT_DATE)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY team ORDER BY game_date DESC) = 1
),
latest_pitching AS (
    SELECT *
    FROM baseball_data.betting.mart_team_rolling_pitching
    WHERE game_year = YEAR(CURRENT_DATE)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY team ORDER BY game_date DESC) = 1
)
SELECT
    t.team_id,
    t.canonical_abbrev                      AS team_abbrev,
    t.canonical_name                        AS team_name,
    r.wins, r.losses, r.games_played, r.win_pct,
    r.runs_scored_ytd, r.runs_allowed_ytd,
    r.pythagorean_win_exp,
    r.games_back, r.is_division_leader,
    r.streak_direction, r.streak_length,
    r.league, r.division,
    off.xwoba_std                           AS off_xwoba_std,
    off.runs_per_game_std                   AS off_runs_per_game_std,
    off.woba_std                            AS off_woba_std,
    off.k_pct_std                           AS off_k_pct_std,
    off.bb_pct_std                          AS off_bb_pct_std,
    off.xwoba_30d                           AS off_xwoba_30d,
    off.runs_per_game_30d                   AS off_runs_per_game_30d,
    pit.runs_allowed_per_game_std           AS pit_ra_per_game_std,
    pit.xwoba_against_std                   AS pit_xwoba_against_std,
    pit.starter_xwoba_against_std           AS pit_starter_xwoba_against_std,
    pit.starter_k_pct_std                   AS pit_starter_k_pct_std,
    pit.bullpen_xwoba_against_std           AS pit_bullpen_xwoba_against_std,
    pit.xwoba_against_30d                   AS pit_xwoba_against_30d
FROM baseball_data.betting.dim_team_name_lookup t
JOIN current_record r ON r.team_id = t.team_id
LEFT JOIN latest_offense off ON off.team = t.canonical_abbrev
LEFT JOIN latest_pitching pit ON pit.team = t.canonical_abbrev
"""

_TEAM_PLATOON_SQL = """
SELECT
    t.team_id,
    vs.opp_starter_hand                     AS pitcher_hand,
    vs.xwoba_std,
    vs.woba_std,
    vs.k_pct_std,
    vs.bb_pct_std,
    vs.runs_per_game_std
FROM baseball_data.betting.mart_team_vs_pitcher_hand vs
JOIN baseball_data.betting.dim_team_name_lookup t ON t.canonical_abbrev = vs.team
WHERE vs.game_year = YEAR(CURRENT_DATE)
QUALIFY ROW_NUMBER() OVER (PARTITION BY vs.team, vs.opp_starter_hand ORDER BY vs.game_date DESC) = 1
"""

_TEAM_ELO_SQL = """
SELECT
    t.team_id,
    e.game_date,
    e.elo_after_game                        AS elo
FROM baseball_data.betting.team_elo_history e
JOIN baseball_data.betting.dim_team_name_lookup t ON t.canonical_abbrev = e.team_abbrev
WHERE e.game_date::date >= DATEADD(day, -60, CURRENT_DATE)  -- INC-23: ::date safe on native DATE; parses ISO VARCHAR in --s3
QUALIFY ROW_NUMBER() OVER (PARTITION BY t.team_id ORDER BY e.game_date DESC) <= 30
ORDER BY t.team_id, e.game_date
"""

_TEAM_FORM_SQL = """
WITH team_games AS (
    SELECT
        t.team_id,
        g.game_pk,
        g.game_date,
        CASE WHEN g.home_team_id = t.team_id THEN g.away_team ELSE g.home_team END AS opponent,
        CASE WHEN g.home_team_id = t.team_id THEN 'home' ELSE 'away' END           AS home_away,
        CASE WHEN g.home_team_id = t.team_id THEN g.home_final_score
             ELSE g.away_final_score END                                             AS runs_scored,
        CASE WHEN g.home_team_id = t.team_id THEN g.away_final_score
             ELSE g.home_final_score END                                             AS runs_allowed,
        (g.home_team_won IS NOT NULL AND (
            (g.home_team_id = t.team_id AND g.home_team_won) OR
            (g.away_team_id = t.team_id AND NOT g.home_team_won)
        ))                                                                           AS won,
        ROW_NUMBER() OVER (PARTITION BY t.team_id ORDER BY g.game_date DESC, g.game_pk DESC) AS rn
    FROM baseball_data.betting.mart_game_results g
    JOIN baseball_data.betting.dim_team_name_lookup t
        ON t.team_id = g.home_team_id OR t.team_id = g.away_team_id
    WHERE g.game_year = YEAR(CURRENT_DATE)
      AND g.home_team_won IS NOT NULL
)
SELECT team_id, game_pk, game_date, opponent, home_away, runs_scored, runs_allowed, won
FROM team_games
WHERE rn <= 10
ORDER BY team_id, rn
"""

_TEAM_H2H_ACCURACY_SQL = """
SELECT
    t.team_id,
    COUNT(*)                                                                            AS games_predicted,
    SUM(CASE WHEN (clv.model_prob > 0.5 AND clv.actual_outcome = 1)
                  OR (clv.model_prob <= 0.5 AND clv.actual_outcome = 0) THEN 1 ELSE 0
         END)                                                                           AS games_correct,
    ROUND(
        SUM(CASE WHEN (clv.model_prob > 0.5 AND clv.actual_outcome = 1)
                      OR (clv.model_prob <= 0.5 AND clv.actual_outcome = 0) THEN 1.0 ELSE 0
             END) / NULLIF(COUNT(*), 0),
        4
    )                                                                                   AS accuracy
FROM baseball_data.betting.mart_clv_labeled_games clv
JOIN baseball_data.betting.mart_game_results g ON g.game_pk = clv.game_pk
JOIN baseball_data.betting.dim_team_name_lookup t
    ON t.team_id = g.home_team_id OR t.team_id = g.away_team_id
WHERE YEAR(clv.game_date) = YEAR(CURRENT_DATE)
  AND clv.market_type = 'h2h'
  AND clv.actual_outcome IS NOT NULL
GROUP BY t.team_id
"""

_TEAM_SCHEDULE_SQL = """
WITH probable AS (
    SELECT game_pk, side, probable_pitcher_id, probable_pitcher_name
    FROM baseball_data.betting.stg_statsapi_probable_pitchers
    QUALIFY ROW_NUMBER() OVER (PARTITION BY game_pk, side ORDER BY ingestion_ts DESC) = 1
)
SELECT
    t.team_id,
    g.game_pk,
    g.game_date,
    opp.canonical_abbrev                                                               AS opponent,
    CASE WHEN g.home_team_id = t.team_id THEN 'home' ELSE 'away' END                 AS home_away,
    g.venue_name,
    CASE WHEN g.home_team_id = t.team_id THEN ph.probable_pitcher_name
         ELSE pa.probable_pitcher_name END                                             AS our_probable_pitcher,
    CASE WHEN g.home_team_id = t.team_id THEN ph.probable_pitcher_id
         ELSE pa.probable_pitcher_id END                                               AS our_probable_pitcher_id
FROM baseball_data.betting.stg_statsapi_games g
JOIN baseball_data.betting.dim_team_name_lookup t
    ON t.team_id = g.home_team_id OR t.team_id = g.away_team_id
JOIN baseball_data.betting.dim_team_name_lookup opp
    ON opp.team_id = CASE WHEN g.home_team_id = t.team_id THEN g.away_team_id ELSE g.home_team_id END
LEFT JOIN probable ph ON ph.game_pk = g.game_pk AND ph.side = 'home'
LEFT JOIN probable pa ON pa.game_pk = g.game_pk AND pa.side = 'away'
WHERE g.game_date::date BETWEEN CURRENT_DATE AND DATEADD(day, 7, CURRENT_DATE)  -- INC-23: stg_statsapi_games game_date is ISO VARCHAR in --s3
  AND g.abstract_game_state NOT IN ('Final', 'Live')
  AND YEAR(g.game_date::date) = YEAR(CURRENT_DATE)
ORDER BY t.team_id, g.game_date
"""


def write_team_profiles(sf, pg_conn, today: str) -> int:
    """Builds and writes team profile blobs to the DynamoDB serving cache. Returns error count."""
    errors = 0
    try:
        summary_rows  = _sf_query(sf, _TEAM_SUMMARY_SQL)
        platoon_rows  = _sf_query(sf, _TEAM_PLATOON_SQL)
        elo_rows      = _sf_query(sf, _TEAM_ELO_SQL)
        form_rows     = _sf_query(sf, _TEAM_FORM_SQL)
        schedule_rows = _sf_query(sf, _TEAM_SCHEDULE_SQL)
        h2h_rows      = _sf_query(sf, _TEAM_H2H_ACCURACY_SQL)
    except Exception:
        log.exception("Failed to query Snowflake for team profiles")
        return 1

    # Index secondary tables by team_id
    platoon_by_team: dict = defaultdict(dict)
    for r in platoon_rows:
        hand = str(r.get("PITCHER_HAND") or "").upper()
        platoon_by_team[r["TEAM_ID"]][hand] = {
            "xwoba": _flt(r.get("XWOBA_STD")),
            "woba": _flt(r.get("WOBA_STD")),
            "k_pct": _flt(r.get("K_PCT_STD")),
            "bb_pct": _flt(r.get("BB_PCT_STD")),
            "runs_per_game": _flt(r.get("RUNS_PER_GAME_STD")),
        }

    elo_by_team: dict = defaultdict(list)
    for r in elo_rows:
        elo_by_team[r["TEAM_ID"]].append({
            "date": str(r["GAME_DATE"]),
            "elo": _flt(r.get("ELO")),
        })

    form_by_team: dict = defaultdict(list)
    for r in form_rows:
        form_by_team[r["TEAM_ID"]].append({
            "game_pk": _int(r.get("GAME_PK")),
            "date": str(r["GAME_DATE"]),
            "opponent": r.get("OPPONENT"),
            "home_away": r.get("HOME_AWAY"),
            "runs_scored": _int(r.get("RUNS_SCORED")),
            "runs_allowed": _int(r.get("RUNS_ALLOWED")),
            "won": bool(r.get("WON")),
        })

    h2h_by_team: dict = {r["TEAM_ID"]: r for r in h2h_rows}

    schedule_by_team: dict = defaultdict(list)
    for r in schedule_rows:
        schedule_by_team[r["TEAM_ID"]].append({
            "game_pk": _int(r.get("GAME_PK")),
            "date": str(r["GAME_DATE"]),
            "opponent": r.get("OPPONENT"),
            "home_away": r.get("HOME_AWAY"),
            "venue_name": r.get("VENUE_NAME"),
            "our_probable_pitcher": r.get("OUR_PROBABLE_PITCHER"),
            "our_probable_pitcher_id": _int(r.get("OUR_PROBABLE_PITCHER_ID")),
        })

    for r in summary_rows:
        tid = r["TEAM_ID"]
        payload = {
            "team_id": tid,
            "team_abbrev": r.get("TEAM_ABBREV"),
            "team_name": r.get("TEAM_NAME"),
            "league": r.get("LEAGUE"),
            "division": r.get("DIVISION"),
            "record": {
                "wins": _int(r.get("WINS")),
                "losses": _int(r.get("LOSSES")),
                "games_played": _int(r.get("GAMES_PLAYED")),
                "win_pct": _flt(r.get("WIN_PCT")),
                "runs_scored_ytd": _int(r.get("RUNS_SCORED_YTD")),
                "runs_allowed_ytd": _int(r.get("RUNS_ALLOWED_YTD")),
                "run_differential": (
                    _int(r.get("RUNS_SCORED_YTD")) - _int(r.get("RUNS_ALLOWED_YTD"))
                    if r.get("RUNS_SCORED_YTD") is not None and r.get("RUNS_ALLOWED_YTD") is not None
                    else None
                ),
                "pythagorean_win_exp": _flt(r.get("PYTHAGOREAN_WIN_EXP")),
                "games_back": _flt(r.get("GAMES_BACK")),
                "is_division_leader": bool(r.get("IS_DIVISION_LEADER")),
                "streak_direction": r.get("STREAK_DIRECTION"),
                "streak_length": _int(r.get("STREAK_LENGTH")),
            },
            "offense": {
                "xwoba_std": _flt(r.get("OFF_XWOBA_STD")),
                "woba_std": _flt(r.get("OFF_WOBA_STD")),
                "runs_per_game_std": _flt(r.get("OFF_RUNS_PER_GAME_STD")),
                "k_pct_std": _flt(r.get("OFF_K_PCT_STD")),
                "bb_pct_std": _flt(r.get("OFF_BB_PCT_STD")),
                "xwoba_30d": _flt(r.get("OFF_XWOBA_30D")),
                "runs_per_game_30d": _flt(r.get("OFF_RUNS_PER_GAME_30D")),
                "vs_lhp": platoon_by_team[tid].get("L"),
                "vs_rhp": platoon_by_team[tid].get("R"),
            },
            "pitching": {
                "ra9": _flt(r.get("PIT_RA_PER_GAME_STD")),
                "xwoba_against_std": _flt(r.get("PIT_XWOBA_AGAINST_STD")),
                "starter_xwoba_against_std": _flt(r.get("PIT_STARTER_XWOBA_AGAINST_STD")),
                "starter_k_pct_std": _flt(r.get("PIT_STARTER_K_PCT_STD")),
                "bullpen_xwoba_against_std": _flt(r.get("PIT_BULLPEN_XWOBA_AGAINST_STD")),
                "xwoba_against_30d": _flt(r.get("PIT_XWOBA_AGAINST_30D")),
            },
            "elo": {
                "current": elo_by_team[tid][-1]["elo"] if elo_by_team[tid] else None,
                "history": elo_by_team[tid],
            },
            "recent_form": form_by_team[tid],
            "schedule": schedule_by_team[tid],
            "h2h_model": (
                {
                    "games": _int(h2h_by_team[tid].get("GAMES_PREDICTED")),
                    "correct": _int(h2h_by_team[tid].get("GAMES_CORRECT")),
                    "accuracy": _flt(h2h_by_team[tid].get("ACCURACY")),
                }
                if tid in h2h_by_team
                else None
            ),
        }
        try:
            _pg_set_cache(pg_conn, f"team/{tid}", today, payload, is_permanent=True)
        except Exception:
            log.exception("Failed to write team profile for team_id=%s", tid)
            errors += 1

    log.info("Team profiles written: %d teams, %d errors", len(summary_rows), errors)
    return errors


# ── Player profile SQL ────────────────────────────────────────────────────────

_PLAYER_BATTER_SQL = """
SELECT
    b.game_pk,
    b.game_date::VARCHAR           AS game_date,
    b.game_year,
    b.batter_id,
    b.batter_hand,
    b.batting_team,
    b.opposing_team,
    b.pa_count,
    b.hits,
    b.home_runs,
    b.strikeouts,
    b.walks,
    b.pitches_seen,
    b.avg_std,
    b.obp_std,
    b.slg_std,
    b.ops_std,
    b.iso_std,
    b.woba_std,
    b.xwoba_std,
    b.xba_std,
    b.xslg_std,
    b.k_pct_std,
    b.bb_pct_std,
    b.hard_hit_pct_std,
    b.barrel_pct_std,
    b.whiff_rate_std,
    b.games_std,
    b.pa_count_std,
    b.games_30d,
    b.pa_count_30d,
    b.woba_30d,
    b.xwoba_30d,
    b.k_pct_30d,
    b.bb_pct_30d,
    b.hard_hit_pct_30d,
    b.barrel_pct_30d,
    b.whiff_rate_30d
FROM baseball_data.betting.mart_batter_rolling_stats b
WHERE b.game_year = 2026
ORDER BY b.batter_id, b.game_date
"""

_PLAYER_IDENTITY_SQL = """
SELECT
    player_id,
    player_type,
    full_name,
    first_name,
    last_name,
    position_abbreviation,
    team,
    bats,
    birth_date::VARCHAR AS birth_date,
    age,
    height_inches,
    weight_lbs,
    is_on_il,
    il_since::VARCHAR AS il_since
FROM baseball_data.betting.mart_player_profile_identity
"""

_PLAYER_PITCHER_SQL = """
SELECT
    p.game_pk,
    p.game_date::VARCHAR           AS game_date,
    p.game_year,
    p.pitcher_id,
    p.pitching_team,
    p.batting_team                 AS opposing_team,
    p.is_home_team,
    p.total_pitches,
    p.batters_faced,
    p.outs_recorded,
    p.innings_pitched,
    p.strikeouts,
    p.walks,
    p.hit_by_pitch,
    p.home_runs_allowed,
    p.hits_allowed,
    p.runs_allowed,
    p.xwoba_against,
    p.avg_fastball_velo,
    p.cumulative_season_ip,
    p.cumulative_season_pitches
FROM baseball_data.betting.mart_starting_pitcher_game_log p
WHERE p.game_year = 2026
ORDER BY p.pitcher_id, p.game_date
"""



def write_player_profiles(sf, pg_conn, today: str) -> int:
    """Builds and writes player profile blobs (batters + pitchers) to the DynamoDB serving cache.

    Writes:
      - player/{player_id}  (is_permanent=True) — full profile with season stats + game log
      - players/list        (is_permanent=True) — all-player summary for listing/search
    """
    errors = 0
    try:
        batter_rows    = _sf_query(sf, _PLAYER_BATTER_SQL)
        pitcher_rows   = _sf_query(sf, _PLAYER_PITCHER_SQL)
        identity_rows  = _sf_query(sf, _PLAYER_IDENTITY_SQL)
    except Exception:
        log.exception("Failed to query Snowflake for player profiles")
        return 1

    # Index identity rows by (player_id, player_type)
    batter_identity: dict[int, dict] = {
        r["PLAYER_ID"]: r for r in identity_rows if r["PLAYER_TYPE"] == "batter"
    }
    pitcher_identity: dict[int, dict] = {
        r["PLAYER_ID"]: r for r in identity_rows if r["PLAYER_TYPE"] == "pitcher"
    }

    # Group batter game rows by batter_id (already ordered by game_date ASC)
    batter_games: dict[int, list] = defaultdict(list)
    for r in batter_rows:
        batter_games[r["BATTER_ID"]].append(r)

    # Group pitcher game rows by pitcher_id
    pitcher_games: dict[int, list] = defaultdict(list)
    for r in pitcher_rows:
        pitcher_games[r["PITCHER_ID"]].append(r)

    batter_summaries = []
    pitcher_summaries = []

    # ── Batter profiles ──────────────────────────────────────────────────────
    for batter_id, rows in batter_games.items():
        last = rows[-1]  # most recent game — STD cols hold season-to-date totals
        identity = batter_identity.get(batter_id, {})

        season = {
            "games": _int(last.get("GAMES_STD")),
            "pa": _int(last.get("PA_COUNT_STD")),
            "hits": sum(_int(r.get("HITS")) or 0 for r in rows),
            "hr": sum(_int(r.get("HOME_RUNS")) or 0 for r in rows),
            "bb": sum(_int(r.get("WALKS")) or 0 for r in rows),
            "k": sum(_int(r.get("STRIKEOUTS")) or 0 for r in rows),
            "avg": _flt(last.get("AVG_STD")),
            "obp": _flt(last.get("OBP_STD")),
            "slg": _flt(last.get("SLG_STD")),
            "ops": _flt(last.get("OPS_STD")),
            "iso": _flt(last.get("ISO_STD")),
            "woba": _flt(last.get("WOBA_STD")),
            "xwoba": _flt(last.get("XWOBA_STD")),
            "xba": _flt(last.get("XBA_STD")),
            "xslg": _flt(last.get("XSLG_STD")),
            "k_pct": _flt(last.get("K_PCT_STD")),
            "bb_pct": _flt(last.get("BB_PCT_STD")),
            "hard_hit_pct": _flt(last.get("HARD_HIT_PCT_STD")),
            "barrel_pct": _flt(last.get("BARREL_PCT_STD")),
            "whiff_rate": _flt(last.get("WHIFF_RATE_STD")),
        }

        rolling_30d = {
            "games": _int(last.get("GAMES_30D")),
            "pa": _int(last.get("PA_COUNT_30D")),
            "woba": _flt(last.get("WOBA_30D")),
            "xwoba": _flt(last.get("XWOBA_30D")),
            "k_pct": _flt(last.get("K_PCT_30D")),
            "bb_pct": _flt(last.get("BB_PCT_30D")),
            "hard_hit_pct": _flt(last.get("HARD_HIT_PCT_30D")),
            "barrel_pct": _flt(last.get("BARREL_PCT_30D")),
            "whiff_rate": _flt(last.get("WHIFF_RATE_30D")),
        }

        game_log = [
            {
                "game_pk": _int(r.get("GAME_PK")),
                "date": str(r.get("GAME_DATE")),
                "opp": r.get("OPPOSING_TEAM"),
                "pa": _int(r.get("PA_COUNT")),
                "hits": _int(r.get("HITS")),
                "hr": _int(r.get("HOME_RUNS")),
                "bb": _int(r.get("WALKS")),
                "k": _int(r.get("STRIKEOUTS")),
                "pitches": _int(r.get("PITCHES_SEEN")),
            }
            for r in rows
        ]

        full_name = identity.get("FULL_NAME")
        team = last.get("BATTING_TEAM")
        position = identity.get("POSITION_ABBREVIATION")

        payload = {
            "player_id": batter_id,
            "player_type": "batter",
            "full_name": full_name,
            "first_name": identity.get("FIRST_NAME"),
            "last_name": identity.get("LAST_NAME"),
            "position": position,
            "bats": last.get("BATTER_HAND"),
            "team": team,
            "birth_date": identity.get("BIRTH_DATE"),
            "age": _int(identity.get("AGE")),
            "height_inches": _int(identity.get("HEIGHT_INCHES")),
            "weight_lbs": _int(identity.get("WEIGHT_LBS")),
            "is_on_il": bool(identity.get("IS_ON_IL")),
            "il_since": identity.get("IL_SINCE"),
            "season_2026": season,
            "rolling_30d": rolling_30d,
            "game_log": game_log,
        }

        try:
            _pg_set_cache(pg_conn, f"player/{batter_id}", today, payload, is_permanent=True)
        except Exception:
            log.exception("Failed to write batter profile for player_id=%s", batter_id)
            errors += 1
            continue

        batter_summaries.append({
            "player_id": batter_id,
            "full_name": full_name,
            "position": position,
            "bats": last.get("BATTER_HAND"),
            "team": team,
            "season_2026": {
                "pa": season["pa"],
                "avg": season["avg"],
                "obp": season["obp"],
                "slg": season["slg"],
                "hr": season["hr"],
                "woba": season["woba"],
                "xwoba": season["xwoba"],
            },
        })

    # ── Pitcher profiles ─────────────────────────────────────────────────────
    for pitcher_id, rows in pitcher_games.items():
        last = rows[-1]
        identity = pitcher_identity.get(pitcher_id, {})

        ip = _flt(last.get("CUMULATIVE_SEASON_IP")) or 0
        k_total = sum(_int(r.get("STRIKEOUTS")) or 0 for r in rows)
        bb_total = sum(_int(r.get("WALKS")) or 0 for r in rows)
        ra_total = sum(_int(r.get("RUNS_ALLOWED")) or 0 for r in rows)

        xw_num = sum(
            (_flt(r.get("XWOBA_AGAINST")) or 0) * (_int(r.get("BATTERS_FACED")) or 0)
            for r in rows if r.get("XWOBA_AGAINST") is not None
        )
        xw_den = sum(
            _int(r.get("BATTERS_FACED")) or 0
            for r in rows if r.get("XWOBA_AGAINST") is not None
        )

        season = {
            "starts": len(rows),
            "ip": round(ip, 1) if ip else None,
            "total_pitches": sum(_int(r.get("TOTAL_PITCHES")) or 0 for r in rows),
            "k": k_total,
            "bb": bb_total,
            "hbp": sum(_int(r.get("HIT_BY_PITCH")) or 0 for r in rows),
            "hr": sum(_int(r.get("HOME_RUNS_ALLOWED")) or 0 for r in rows),
            "hits": sum(_int(r.get("HITS_ALLOWED")) or 0 for r in rows),
            "runs": ra_total,
            "batters_faced": sum(_int(r.get("BATTERS_FACED")) or 0 for r in rows),
            "era": round(ra_total / ip * 9, 2) if ip > 0 else None,
            "k9": round(k_total / ip * 9, 2) if ip > 0 else None,
            "bb9": round(bb_total / ip * 9, 2) if ip > 0 else None,
            "xwoba_against": round(xw_num / xw_den, 4) if xw_den > 0 else None,
            "avg_velo": _flt(last.get("AVG_FASTBALL_VELO")),
        }

        game_log = [
            {
                "game_pk": _int(r.get("GAME_PK")),
                "date": str(r.get("GAME_DATE")),
                "opp": r.get("OPPOSING_TEAM"),
                "home_away": "home" if r.get("IS_HOME_TEAM") else "away",
                "ip": _flt(r.get("INNINGS_PITCHED")),
                "outs": _int(r.get("OUTS_RECORDED")),
                "k": _int(r.get("STRIKEOUTS")),
                "bb": _int(r.get("WALKS")),
                "hr": _int(r.get("HOME_RUNS_ALLOWED")),
                "hits": _int(r.get("HITS_ALLOWED")),
                "runs": _int(r.get("RUNS_ALLOWED")),
                "pitches": _int(r.get("TOTAL_PITCHES")),
                "xwoba_against": _flt(r.get("XWOBA_AGAINST")),
                "velo": _flt(r.get("AVG_FASTBALL_VELO")),
            }
            for r in rows
        ]

        full_name = identity.get("FULL_NAME")
        team = last.get("PITCHING_TEAM")
        position = identity.get("POSITION_ABBREVIATION") or "P"

        payload = {
            "player_id": pitcher_id,
            "player_type": "pitcher",
            "full_name": full_name,
            "first_name": identity.get("FIRST_NAME"),
            "last_name": identity.get("LAST_NAME"),
            "position": position,
            "team": team,
            "birth_date": identity.get("BIRTH_DATE"),
            "age": _int(identity.get("AGE")),
            "height_inches": _int(identity.get("HEIGHT_INCHES")),
            "weight_lbs": _int(identity.get("WEIGHT_LBS")),
            "is_on_il": bool(identity.get("IS_ON_IL")),
            "il_since": identity.get("IL_SINCE"),
            "season_2026": season,
            "game_log": game_log,
        }

        try:
            _pg_set_cache(pg_conn, f"player/{pitcher_id}", today, payload, is_permanent=True)
        except Exception:
            log.exception("Failed to write pitcher profile for player_id=%s", pitcher_id)
            errors += 1
            continue

        pitcher_summaries.append({
            "player_id": pitcher_id,
            "full_name": full_name,
            "position": position,
            "team": team,
            "season_2026": {
                "starts": season["starts"],
                "ip": season["ip"],
                "era": season["era"],
                "k": season["k"],
                "bb": season["bb"],
                "xwoba_against": season["xwoba_against"],
            },
        })

    # ── Combined list blob ───────────────────────────────────────────────────
    list_payload = {"batters": batter_summaries, "pitchers": pitcher_summaries}
    try:
        _pg_set_cache(pg_conn, "players/list", today, list_payload, is_permanent=True)
    except Exception:
        log.exception("Failed to write players/list blob")
        errors += 1

    log.info(
        "Player profiles written: %d batters, %d pitchers, %d errors",
        len(batter_games), len(pitcher_games), errors,
    )
    return errors


if __name__ == "__main__":
    sys.exit(main())
