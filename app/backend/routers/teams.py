"""Team detail endpoints — served from Railway PG api_cache."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.services import pg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("/{team_id}")
def get_team(team_id: int, _: str = Depends(get_user_id)) -> dict:
    """Return the cached team profile for a given MLB statsapi team_id.

    Profiles are written daily by write_serving_store.py (write_team_profiles).
    Cache key: team/{team_id}
    """
    from datetime import date
    today = date.today().isoformat()

    payload = pg.get_cache(f"team/{team_id}", today)
    if payload is None:
        logger.warning("Team profile cache miss for team_id=%s", team_id)
        raise HTTPException(status_code=404, detail=f"Team profile not found for team_id={team_id}")

    return payload
