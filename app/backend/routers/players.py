"""Player profile endpoints — served from the DynamoDB serving cache (INC-16-P2)."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.backend.dependencies import get_user_id
from app.backend.services import serving_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/players", tags=["players"])


@router.get("")
def list_players(_: str = Depends(get_user_id)) -> dict:
    """Return summary lists of all batters and pitchers (for the players directory page)."""
    today = date.today().isoformat()
    payload = serving_cache.get_cache("players/list", today)
    if payload is None:
        return {"batters": [], "pitchers": []}
    return payload


@router.get("/{batter_id}/zone-overlay")
def get_zone_overlay(
    batter_id: int,
    pitcher_id: int,
    _: str = Depends(get_user_id),
) -> dict:
    """Return zone-matchup overlay JSON for a batter × pitcher pair.

    Read order: Railway PG cache → S3 ml-artifacts serving prefix (today/yesterday/2d ago).
    Returns 404 if no overlay is found (not yet written for this matchup).
    """
    today = date.today().isoformat()
    cache_key = f"zone_matchup/{batter_id}_vs_{pitcher_id}"
    payload = serving_cache.get_cache_latest(cache_key)
    if payload:
        return payload

    artifacts_bucket = os.getenv("ARTIFACTS_BUCKET", "baseball-betting-ml-artifacts")
    s3 = boto3.client("s3", region_name="us-east-2")
    for days_back in range(3):
        as_of = (date.fromisoformat(today) - timedelta(days=days_back)).isoformat()
        key = f"baseball/serving/zone_matchup/overlay/as_of={as_of}/{batter_id}_vs_{pitcher_id}.json"
        try:
            response = s3.get_object(Bucket=artifacts_bucket, Key=key)
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                continue
            logger.warning("zone_overlay S3 error for %s_vs_%s as_of=%s: %s", batter_id, pitcher_id, as_of, e)
            break
        except Exception as e:
            logger.warning("zone_overlay S3 read error: %s", e)
            break

    raise HTTPException(status_code=404, detail=f"Zone overlay not found for {batter_id}_vs_{pitcher_id}")


@router.get("/{player_id}")
def get_player(player_id: int, _: str = Depends(get_user_id)) -> dict:
    """Return the cached player profile for a given MLBAM player_id.

    Profiles are written daily by write_serving_store.py (write_player_profiles).
    Cache key: player/{player_id}
    """
    today = date.today().isoformat()
    payload = serving_cache.get_cache(f"player/{player_id}", today)
    if payload is None:
        logger.warning("Player profile cache miss for player_id=%s", player_id)
        raise HTTPException(
            status_code=404,
            detail=f"Player profile not found for player_id={player_id}",
        )
    return payload
