"""S3-backed cache for API responses.

Date-scoped keys ensure yesterday's cache never serves as today's data.
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


def _today_prefix() -> str:
    return f"api-cache/{date.today().isoformat()}"


def get_cache(key: str) -> dict | list | None:
    """Return parsed JSON from S3, or None on miss/error."""
    if not CACHE_BUCKET:
        logger.warning("CACHE_BUCKET not set — skipping cache read")
        return None
    full_key = f"{_today_prefix()}/{key}"
    try:
        response = _s3.get_object(Bucket=CACHE_BUCKET, Key=full_key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            logger.info("Cache miss: %s", full_key)
        else:
            logger.error("Cache read error for %s: %s", full_key, e)
        return None
    except Exception as e:
        logger.error("Cache read error for %s: %s", full_key, e)
        return None


def set_cache(key: str, data: dict | list) -> bool:
    """Write JSON to S3. Returns True on success, False on failure — never raises."""
    if not CACHE_BUCKET:
        logger.warning("CACHE_BUCKET not set — skipping cache write")
        return False
    full_key = f"{_today_prefix()}/{key}"
    try:
        _s3.put_object(
            Bucket=CACHE_BUCKET,
            Key=full_key,
            Body=json.dumps(data, default=str),
            ContentType="application/json",
        )
        logger.info("Cache written: %s", full_key)
        return True
    except Exception as e:
        logger.error("Cache write error for %s: %s", full_key, e)
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
