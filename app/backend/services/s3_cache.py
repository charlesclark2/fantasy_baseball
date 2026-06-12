"""S3-backed cache for API responses.

Date-scoped keys ensure yesterday's cache never serves as today's data.
Permanent keys (api-cache/permanent/...) are used for immutable completed-game data.
All methods are non-raising — callers fall back to Snowflake on any failure.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

CACHE_BUCKET = os.getenv("CACHE_BUCKET")
_s3 = boto3.client("s3", region_name="us-east-1")

_PERMANENT_PREFIX = "api-cache/permanent"


def _today_prefix() -> str:
    return f"api-cache/{date.today().isoformat()}"


def _full_key(key: str, permanent: bool) -> str:
    prefix = _PERMANENT_PREFIX if permanent else _today_prefix()
    return f"{prefix}/{key}"


def get_cache(key: str, permanent: bool = False) -> dict | list | None:
    """Return parsed JSON from S3, or None on miss/error.

    permanent=True reads from a date-independent prefix (used for Final games
    whose data will never change).
    """
    if not CACHE_BUCKET:
        return None
    fk = _full_key(key, permanent)
    try:
        response = _s3.get_object(Bucket=CACHE_BUCKET, Key=fk)
        return json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.debug("Cache miss: %s", fk)
        else:
            logger.error("Cache read error for %s: %s", fk, e)
        return None
    except Exception as e:
        logger.error("Cache read error for %s: %s", fk, e)
        return None


def set_cache(key: str, data: dict | list, permanent: bool = False) -> bool:
    """Write JSON to S3. Returns True on success, False on failure — never raises.

    permanent=True writes to a date-independent prefix so the entry survives
    daily cache rotation.
    """
    if not CACHE_BUCKET:
        return False
    fk = _full_key(key, permanent)
    try:
        _s3.put_object(
            Bucket=CACHE_BUCKET,
            Key=fk,
            Body=json.dumps(data, default=str),
            ContentType="application/json",
        )
        logger.info("Cache written: %s", fk)
        return True
    except Exception as e:
        logger.error("Cache write error for %s: %s", fk, e)
        return False


def invalidate_today() -> None:
    """Delete all cache keys for today. Used by /admin/cache/invalidate."""
    if not CACHE_BUCKET:
        return
    prefix = _today_prefix()
    try:
        paginator = _s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=CACHE_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                _s3.delete_object(Bucket=CACHE_BUCKET, Key=obj["Key"])
        logger.info("Cache invalidated for prefix: %s", prefix)
    except Exception as e:
        logger.error("Cache invalidation error: %s", e)
