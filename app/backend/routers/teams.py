"""Team detail endpoints — served from the DynamoDB serving cache (INC-16-P2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from betting_ml.utils.game_day import current_game_date_iso  # INC-22 — canonical US baseball-day

from app.backend.dependencies import get_user_id
from app.backend.services import serving_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
def list_teams(_: str = Depends(get_user_id)) -> list:
    """Return a summary list of all team profiles (for the teams directory page)."""
    payloads = serving_cache.list_cache_by_prefix("team/")
    return [
        {
            "team_id": p["team_id"],
            "team_name": p["team_name"],
            "team_abbrev": p["team_abbrev"],
            "league": p["league"],
            "division": p["division"],
            "record": p.get("record"),
        }
        for p in payloads
        if "team_id" in p
    ]


@router.get("/{team_id}")
def get_team(team_id: int, _: str = Depends(get_user_id)) -> dict:
    """Return the cached team profile for a given MLB statsapi team_id.

    Profiles are written daily by write_serving_store.py (write_team_profiles).
    Cache key: team/{team_id}
    """
    today = current_game_date_iso()  # INC-22 — match the LA baseball-day write key

    payload = serving_cache.get_cache(f"team/{team_id}", today)
    if payload is None:
        logger.warning("Team profile cache miss for team_id=%s", team_id)
        raise HTTPException(status_code=404, detail=f"Team profile not found for team_id={team_id}")

    return payload
