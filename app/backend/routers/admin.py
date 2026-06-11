"""Admin endpoints.

POST /admin/cache/invalidate — invalidate today's S3 cache
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.backend.services.s3_cache import invalidate_today

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/cache/invalidate")
def invalidate_cache() -> dict:
    """
    Invalidates today's S3 cache — forces next request to re-query Snowflake.
    Used by the admin dashboard Force Refresh button.
    Requires admin Cognito group — enforce this in A0.4 when auth is wired.
    """
    invalidate_today()
    return {"status": "ok", "message": "Cache invalidated — next request will re-query Snowflake"}
