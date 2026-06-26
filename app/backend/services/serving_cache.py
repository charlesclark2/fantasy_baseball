"""DynamoDB serving cache (INC-16-P2) — replaces the Railway Postgres api_cache.

The serving store is a key→JSON blob cache. INC-16 took down the Railway PG that
held it; this module re-homes it on DynamoDB (already in-stack for users/bets).
Read order at request time becomes **DynamoDB → S3** (s3_cache is the fallback);
Snowflake stays the last resort in the routers.

Interface mirrors the old app.backend.services.pg cache functions 1:1 so the
routers change only their import:
    get_cache / get_cache_latest / set_cache / invalidate / invalidate_today /
    invalidate_game / invalidate_permanent_picks / list_cache_by_prefix

── Table design (single table, structured PK/SK — INC-16-P2 decision) ──────────
Table: SERVING_CACHE_TABLE (default credence-prod-serving-cache).
  pk (S)          = namespace = the cache_key up to the first '/'
                    ("picks", "team", "player", "players", "performance",
                     "zone_matchup")
  sk (S)          = "{rest}#{cache_date}"  for date-scoped rows
                    "{rest}#PERMANENT"     for permanent rows (survive rollover)
                    where rest = the cache_key after the first '/'.
  value (S)       = JSON string of the payload (opaque; keeps the 400 KB item
                    limit simple and dodges float→Decimal round-tripping).
  is_permanent (BOOL)
  updated_at (S)  = ISO timestamp
  cache_date (S)  = the date, or "PERMANENT" — lets invalidate_today filter.

Why this shape: ~95 % of reads are point reads → GetItem on (pk, sk). The only
non-point ops map cleanly: list_cache_by_prefix("team/") → Query(pk="team");
invalidate_permanent_picks → Query(pk="picks", begins_with "game/"); the rare
admin invalidate_today → a Scan (small table). No GSI needed.

All functions are non-raising: on any DynamoDB error they degrade to None / [] /
0 / no-op so the router falls through to S3 (matching the old pg.py contract).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger(__name__)

_REGION = os.getenv("AWS_REGION", "us-east-1")
_TABLE_NAME = os.getenv("SERVING_CACHE_TABLE", "credence-prod-serving-cache")
_PERMANENT = "PERMANENT"

# Lazily-created boto3 resource so import never fails (e.g. no creds in unit tests).
_ddb = boto3.resource("dynamodb", region_name=_REGION)


def _table():
    return _ddb.Table(_TABLE_NAME)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_key(cache_key: str) -> tuple[str, str]:
    """('picks/game/123') → ('picks', 'game/123'); ('foo') → ('foo', '_')."""
    ns, sep, rest = cache_key.partition("/")
    return ns, (rest if sep else "_")


def _sk(rest: str, date_str: str, is_permanent: bool) -> str:
    return f"{rest}#{_PERMANENT}" if is_permanent else f"{rest}#{date_str}"


def _decode(item: dict | None) -> dict | None:
    if not item:
        return None
    try:
        return json.loads(item["value"])
    except Exception:
        logger.warning("serving_cache: undecodable value for sk=%s", item.get("sk"))
        return None


# ── Blob cache reads ──────────────────────────────────────────────────────────

def get_cache(cache_key: str, date_str: str) -> dict | None:
    """Return the payload dict, or None on miss.

    Checks the permanent row first (Final-game blobs survive date rollover),
    then the date-scoped row — matching the old PG get_cache semantics.
    """
    ns, rest = _split_key(cache_key)
    try:
        tbl = _table()
        perm = tbl.get_item(Key={"pk": ns, "sk": _sk(rest, date_str, True)}).get("Item")
        if perm:
            return _decode(perm)
        row = tbl.get_item(Key={"pk": ns, "sk": _sk(rest, date_str, False)}).get("Item")
        return _decode(row)
    except Exception:
        logger.warning("serving_cache.get_cache failed for key=%s", cache_key)
        return None


def get_cache_latest(cache_key: str) -> dict | None:
    """Most recently written payload for a key, ignoring date (latest-wins).

    Used for 'latest available' blobs (book-odds, zone_matchup) where the newest
    write is always the right one.
    """
    ns, rest = _split_key(cache_key)
    try:
        items = _query_all(Key("pk").eq(ns) & Key("sk").begins_with(f"{rest}#"))
        if not items:
            return None
        latest = max(items, key=lambda it: it.get("updated_at", ""))
        return _decode(latest)
    except Exception:
        logger.warning("serving_cache.get_cache_latest failed for key=%s", cache_key)
        return None


def list_cache_by_prefix(prefix: str) -> list[dict]:
    """All permanent payloads whose cache_key starts with `prefix` (e.g. 'team/').

    prefix maps to (pk, sk-begins_with): 'team/' → pk='team'; a deeper prefix
    like 'picks/game/' → pk='picks', sk begins_with 'game/'.
    """
    ns, sep, rest_prefix = prefix.partition("/")
    try:
        cond = Key("pk").eq(ns)
        if rest_prefix:
            cond = cond & Key("sk").begins_with(rest_prefix)
        items = _query_all(cond, filter_expr=Attr("is_permanent").eq(True))
        items.sort(key=lambda it: it.get("sk", ""))
        return [d for it in items if (d := _decode(it)) is not None]
    except Exception:
        logger.warning("serving_cache.list_cache_by_prefix failed for prefix=%s", prefix)
        return []


# ── Blob cache writes ─────────────────────────────────────────────────────────

def set_cache(cache_key: str, date_str: str, payload: dict, is_permanent: bool = False) -> None:
    """Upsert a payload. Permanent rows live at a date-independent SK so they
    survive daily rollover (the get_cache permanent-first branch finds them).

    Non-raising: large payloads that exceed the 400 KB item limit are caught and
    logged — the parallel S3 write keeps the key servable via the S3 fallback.
    """
    ns, rest = _split_key(cache_key)
    try:
        _table().put_item(Item={
            "pk": ns,
            "sk": _sk(rest, date_str, is_permanent),
            "value": json.dumps(payload, default=str),
            "is_permanent": is_permanent,
            "updated_at": _now_iso(),
            "cache_date": _PERMANENT if is_permanent else date_str,
        })
    except Exception:
        logger.warning("serving_cache.set_cache failed for key=%s (S3 fallback covers)", cache_key)


def invalidate(cache_key: str, date_str: str) -> None:
    """Delete the date-scoped (non-permanent) entry for cache_key+date_str."""
    ns, rest = _split_key(cache_key)
    try:
        _table().delete_item(Key={"pk": ns, "sk": _sk(rest, date_str, False)})
    except Exception:
        logger.warning("serving_cache.invalidate failed for key=%s", cache_key)


def invalidate_game(game_pk: int, date_str: str) -> None:
    """Delete the date-scoped game_detail entry for a single game."""
    invalidate(f"picks/game/{game_pk}", date_str)


def invalidate_today(date_str: str) -> None:
    """Clear all non-permanent cache entries for a date (full slate refresh).

    The one cross-partition op — a Scan filtered on cache_date. Cheap at beta
    table size; admin-triggered and rare (mirrors the S3 list-by-today-prefix).
    """
    try:
        tbl = _table()
        items = _scan_all(filter_expr=Attr("cache_date").eq(date_str))
        with tbl.batch_writer() as batch:
            for it in items:
                batch.delete_item(Key={"pk": it["pk"], "sk": it["sk"]})
    except Exception:
        logger.warning("serving_cache.invalidate_today failed for date=%s", date_str)


def invalidate_permanent_picks() -> int:
    """Delete all is_permanent picks/game/* entries; return the count deleted.

    Use after a champion promotion to clear stale Final-game blobs that
    day-scoped invalidations never touch. Idempotent.
    """
    try:
        tbl = _table()
        items = _query_all(
            Key("pk").eq("picks") & Key("sk").begins_with("game/"),
            filter_expr=Attr("is_permanent").eq(True),
        )
        with tbl.batch_writer() as batch:
            for it in items:
                batch.delete_item(Key={"pk": it["pk"], "sk": it["sk"]})
        logger.info("invalidate_permanent_picks: deleted %d DynamoDB items", len(items))
        return len(items)
    except Exception:
        logger.warning("serving_cache.invalidate_permanent_picks failed")
        return 0


# ── Pagination helpers ────────────────────────────────────────────────────────

def _query_all(key_cond, filter_expr=None) -> list[dict]:
    tbl = _table()
    kwargs: dict = {"KeyConditionExpression": key_cond}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    items: list[dict] = []
    while True:
        resp = tbl.query(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items


def _scan_all(filter_expr=None) -> list[dict]:
    tbl = _table()
    kwargs: dict = {}
    if filter_expr is not None:
        kwargs["FilterExpression"] = filter_expr
    items: list[dict] = []
    while True:
        resp = tbl.scan(**kwargs)
        items.extend(resp.get("Items", []))
        lek = resp.get("LastEvaluatedKey")
        if not lek:
            break
        kwargs["ExclusiveStartKey"] = lek
    return items
