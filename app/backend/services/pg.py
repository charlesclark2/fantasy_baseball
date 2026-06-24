"""Railway PostgreSQL serving store — sync interface via psycopg2.

All FastAPI handlers are sync `def` (not async), so we use psycopg2 with a
ThreadedConnectionPool rather than asyncpg. The pool is created lazily on first
use and reused across warm Lambda invocations.

Tables (see infrastructure/pg/create_serving_tables.sql):
  api_cache      — blob store keyed by (cache_key, cache_date); replaces S3 JSON files
  daily_picks    — individual pick rows for portfolio-side filtering
  user_portfolios — per-user portfolio preferences

Env var: DATABASE_URL — standard PostgreSQL connection string from Railway.
If DATABASE_URL is not set, all functions return None / no-op (graceful degradation
during the S3 → PG transition period).
"""

from __future__ import annotations

import logging
import os

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool | None:
    global _pool
    if _pool is not None:
        return _pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    try:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 5, dsn=url)
    except Exception:
        logger.exception("PG pool creation failed — serving store unavailable")
        _pool = None
    return _pool


def _conn():
    pool = _get_pool()
    if pool is None:
        return None
    try:
        return pool.getconn()
    except Exception:
        logger.warning("PG getconn failed")
        return None


def _release(conn) -> None:
    if conn is None:
        return
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass


# ── Blob cache (api_cache table) ─────────────────────────────────────────────

def get_cache(cache_key: str, date_str: str) -> dict | None:
    """Returns the payload dict, or None on miss.

    Checks is_permanent rows first (Final-game blobs survive date rollover),
    then falls through to the date-scoped row.
    """
    conn = _conn()
    if conn is None:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT payload FROM api_cache WHERE cache_key = %s AND is_permanent = TRUE ORDER BY updated_at DESC LIMIT 1",
                (cache_key,),
            )
            row = cur.fetchone()
            if row:
                return dict(row["payload"])
            cur.execute(
                "SELECT payload FROM api_cache WHERE cache_key = %s AND cache_date = %s LIMIT 1",
                (cache_key, date_str),
            )
            row = cur.fetchone()
            return dict(row["payload"]) if row else None
    except Exception:
        logger.warning("PG get_cache failed for key=%s", cache_key)
        return None
    finally:
        _release(conn)


def get_cache_latest(cache_key: str) -> dict | None:
    """Return the most recently written payload for a key, ignoring cache_date.

    Used for data that is 'latest available' rather than strictly date-scoped
    (e.g. book-odds blobs where the most recent write is always the right one).
    """
    conn = _conn()
    if conn is None:
        return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT payload FROM api_cache WHERE cache_key = %s ORDER BY updated_at DESC LIMIT 1",
                (cache_key,),
            )
            row = cur.fetchone()
            return dict(row["payload"]) if row else None
    except Exception:
        logger.warning("PG get_cache_latest failed for key=%s", cache_key)
        return None
    finally:
        _release(conn)


def set_cache(cache_key: str, date_str: str, payload: dict, is_permanent: bool = False) -> None:
    """Upserts a payload into api_cache. is_permanent rows are never downgraded."""
    conn = _conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_cache (cache_key, cache_date, payload, is_permanent, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (cache_key, cache_date) DO UPDATE SET
                    payload      = EXCLUDED.payload,
                    is_permanent = api_cache.is_permanent OR EXCLUDED.is_permanent,
                    updated_at   = NOW()
                """,
                (cache_key, date_str, psycopg2.extras.Json(payload), is_permanent),
            )
        conn.commit()
    except Exception:
        logger.warning("PG set_cache failed for key=%s", cache_key)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        _release(conn)


def invalidate(cache_key: str, date_str: str) -> None:
    """Deletes the date-scoped (non-permanent) entry for cache_key+date_str."""
    conn = _conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM api_cache WHERE cache_key = %s AND cache_date = %s AND is_permanent = FALSE",
                (cache_key, date_str),
            )
        conn.commit()
    except Exception:
        logger.warning("PG invalidate failed for key=%s", cache_key)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        _release(conn)


def invalidate_today(date_str: str) -> None:
    """Clears all non-permanent cache entries for today (full slate refresh)."""
    conn = _conn()
    if conn is None:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM api_cache WHERE cache_date = %s AND is_permanent = FALSE",
                (date_str,),
            )
            cur.execute(
                "DELETE FROM daily_picks WHERE prediction_date = %s",
                (date_str,),
            )
        conn.commit()
    except Exception:
        logger.warning("PG invalidate_today failed for date=%s", date_str)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        _release(conn)


def invalidate_game(game_pk: int, date_str: str) -> None:
    """Deletes the date-scoped game_detail cache entry for a single game."""
    invalidate(f"picks/game/{game_pk}", date_str)


def invalidate_permanent_picks() -> int:
    """Deletes all is_permanent=TRUE entries whose cache_key matches picks/game/%.

    Use after a champion promotion to clear stale Final-game blobs that
    day-scoped invalidations never touch. Returns the row count deleted.
    Idempotent — safe to re-run.
    """
    conn = _conn()
    if conn is None:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM api_cache WHERE cache_key LIKE 'picks/game/%' AND is_permanent = TRUE"
            )
            deleted = cur.rowcount
        conn.commit()
        logger.info("invalidate_permanent_picks: deleted %d PG rows", deleted)
        return deleted
    except Exception:
        logger.warning("PG invalidate_permanent_picks failed")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        _release(conn)


def list_cache_by_prefix(prefix: str) -> list[dict]:
    """Returns all is_permanent payloads whose cache_key starts with `prefix`."""
    conn = _conn()
    if conn is None:
        return []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT payload FROM api_cache WHERE cache_key LIKE %s AND is_permanent = TRUE ORDER BY cache_key",
                (prefix + "%",),
            )
            rows = cur.fetchall()
        return [dict(r["payload"]) for r in rows]
    except Exception:
        logger.warning("PG list_cache_by_prefix failed for prefix=%s", prefix)
        return []
    finally:
        _release(conn)


# ── User portfolios ───────────────────────────────────────────────────────────

_DEFAULT_PORTFOLIO = {
    "min_ev_threshold": 0.02,
    "markets": ["h2h", "totals"],
    "bankroll": None,
    "max_kelly_fraction": 0.05,
}


def get_user_portfolio(user_id: str) -> dict:
    """Returns user's portfolio preferences, or defaults if not yet saved."""
    conn = _conn()
    if conn is None:
        return {"user_id": user_id, **_DEFAULT_PORTFOLIO}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM user_portfolios WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if row:
            return dict(row)
        return {"user_id": user_id, **_DEFAULT_PORTFOLIO}
    except Exception:
        logger.warning("PG get_user_portfolio failed for user=%s", user_id)
        return {"user_id": user_id, **_DEFAULT_PORTFOLIO}
    finally:
        _release(conn)


def upsert_user_portfolio(user_id: str, prefs: dict) -> dict:
    """Saves user portfolio preferences. Returns the saved row."""
    conn = _conn()
    if conn is None:
        return {"user_id": user_id, **prefs}
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO user_portfolios
                    (user_id, min_ev_threshold, markets, bankroll, max_kelly_fraction, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    min_ev_threshold   = EXCLUDED.min_ev_threshold,
                    markets            = EXCLUDED.markets,
                    bankroll           = EXCLUDED.bankroll,
                    max_kelly_fraction = EXCLUDED.max_kelly_fraction,
                    updated_at         = NOW()
                RETURNING *
                """,
                (
                    user_id,
                    prefs.get("min_ev_threshold", 0.02),
                    psycopg2.extras.Json(prefs.get("markets", ["h2h", "totals"])),
                    prefs.get("bankroll"),
                    prefs.get("max_kelly_fraction", 0.05),
                ),
            )
            row = cur.fetchone()
        conn.commit()
        return dict(row) if row else {"user_id": user_id, **prefs}
    except Exception:
        logger.warning("PG upsert_user_portfolio failed for user=%s", user_id)
        try:
            conn.rollback()
        except Exception:
            pass
        return {"user_id": user_id, **prefs}
    finally:
        _release(conn)
