"""Player profile endpoints — served from Railway PG api_cache."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.services import pg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
def list_players(_: str = Depends(get_user_id)) -> dict:
    """Return summary lists of all batters and pitchers (for the players directory page)."""
    today = date.today().isoformat()
    payload = pg.get_cache("players/list", today)
    if payload is None:
        return {"batters": [], "pitchers": []}
    return payload


@router.get("/{player_id}")
def get_player(player_id: int, _: str = Depends(get_user_id)) -> dict:
    """Return the cached player profile for a given MLBAM player_id.

    Profiles are written daily by write_serving_store.py (write_player_profiles).
    Cache key: player/{player_id}
    """
    today = date.today().isoformat()
    payload = pg.get_cache(f"player/{player_id}", today)
    if payload is None:
        logger.warning("Player profile cache miss for player_id=%s", player_id)
        raise HTTPException(
            status_code=404,
            detail=f"Player profile not found for player_id={player_id}",
        )
    return payload
