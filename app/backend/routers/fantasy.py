"""Fantasy surface data endpoints (E9.45) — the SERVER-SIDE gate for the paid
fantasy product.

The NFL draft-board data used to be served as static JSON from the Next.js public
dir (`/data/nfl-fantasy/...`), which is publicly fetchable by URL regardless of any
nav gating — so a client-only gate on this paid feature was bypassable (the same
class as E9.8's server-side MFA lesson). These endpoints move the board behind the
API and enforce `require_fantasy_access` (subscriber OR admin OR the fantasy_comp
allow-list), returning 403 for everyone else.

Data source: the operator's draft-board export (`export_draft_board_json.py --s3`)
uploads the boards to `s3://$CACHE_BUCKET/fantasy/nfl/<season>/`. For local backend
dev, set FANTASY_BOARD_DIR to a checked-out board directory to read from disk.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query

from app.backend.dependencies import require_fantasy_access, require_fantasy_beta_access
from app.backend.models.fantasy import League, LeagueSave
from app.backend.services import dynamo

logger = logging.getLogger(__name__)

# Every route in this router requires fantasy entitlement (defense-in-depth).
router = APIRouter(
    prefix="/fantasy",
    tags=["fantasy"],
    dependencies=[Depends(require_fantasy_access)],
)

_DEFAULT_SEASON = int(os.getenv("NFL_FANTASY_SEASON", "2026"))
_CACHE_BUCKET = os.getenv("CACHE_BUCKET")
# Optional local board dir for backend dev (skips S3). Points at e.g. a checked-out
# `.../nfl-fantasy` root that contains `<season>/manifest.json`.
_LOCAL_BOARD_DIR = os.getenv("FANTASY_BOARD_DIR")

# config names are league presets (e.g. "full_ppr_3wr"); size is a team count. Both
# feed an S3 key / filename, so validate strictly to prevent path traversal.
_CONFIG_RE = re.compile(r"^[a-z0-9_]{1,40}$")

_s3 = boto3.client("s3", region_name="us-east-1")


def _load_json(rel_key: str) -> dict | list | None:
    """Load a board JSON blob by its relative key ("<season>/manifest.json"), from a
    local dir when configured, else S3. Returns None on miss."""
    if _LOCAL_BOARD_DIR:
        path = Path(_LOCAL_BOARD_DIR) / rel_key
        if path.is_file():
            return json.loads(path.read_text())
        return None
    if not _CACHE_BUCKET:
        raise HTTPException(status_code=503, detail="Fantasy data store is not configured")
    key = f"fantasy/nfl/{rel_key}"
    try:
        resp = _s3.get_object(Bucket=_CACHE_BUCKET, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NoSuchBucket"):
            return None
        logger.error("fantasy board read error for %s: %s", key, e)
        raise HTTPException(status_code=502, detail="Could not read fantasy data") from e
    except Exception as e:  # noqa: BLE001
        logger.error("fantasy board parse error for %s: %s", key, e)
        raise HTTPException(status_code=502, detail="Could not read fantasy data") from e


@router.get("/nfl/manifest")
def nfl_manifest(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """The NFL fantasy draft-board manifest (available configs + sizes + roster shapes)."""
    data = _load_json(f"{season}/manifest.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy manifest not found")
    return data


@router.get("/nfl/projections")
def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """NF3 — the format-INDEPENDENT NFL season projection (raw stat line + the 80% PPR
    interval + uncertainty type / confidence). The browse Projections surface reads this;
    the format-SCORED numbers come from /nfl/board."""
    data = _load_json(f"{season}/projections.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy projections not found")
    return data


@router.get("/nfl/board")
def nfl_board(
    config: str = Query(..., description="league preset name, e.g. full_ppr_3wr"),
    size: int = Query(..., ge=2, le=32, description="team count"),
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
):
    """A single (config, size) NFL fantasy draft board."""
    if not _CONFIG_RE.match(config):
        raise HTTPException(status_code=422, detail="Invalid config name")
    data = _load_json(f"{season}/board_{config}_{size}.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy board not found")
    return data


# ══════════════════════════════════════════════════════════════════════════════
# NF-C0b — saved league settings (the manual customization FLOOR)
# ══════════════════════════════════════════════════════════════════════════════
# Platform import (NF-C0) is the convenience path and it will never cover every
# league: unofficial/fragile ESPN endpoints, long-tail platforms, private leagues,
# partial imports. These endpoints are the GUARANTEE underneath it — a user can
# always hand-enter their settings and get the same product.
#
# Both paths produce the IDENTICAL object: the `fantasy_engine` LeagueConfig, stored
# as its `to_dict()` JSON. An imported league and a typed-in league are therefore
# indistinguishable to every consumer, and a config is portable between them.
#
# 🔒 ENTITLEMENT — NARROWER THAN THE REST OF THIS ROUTER. The read-only board endpoints
# above run on the router-level `require_fantasy_access` (subscriber OR admin OR comp).
# These league routes additionally require `require_fantasy_beta_access`: `admin` +
# `fantasy_comp` ONLY, so a paying subscriber does NOT get the editor yet.
#
# The narrower gate lives on each ROUTE rather than on the router, because the router's
# dependency is shared with the board endpoints that must stay open to subscribers.
# Since FANTASY_BETA_GROUPS is a strict subset of FANTASY_ACCESS_GROUPS, both
# dependencies run and the stricter one binds.
#
# These are WRITE endpoints, so server-side enforcement is the real gate — hiding the
# nav item stops nobody from POSTing a config straight to the API.


def _league_response(record: dict) -> dict:
    """Serialize ONE stored league through the response model.

    Row-by-row on purpose (E9.49): a single malformed stored league must cost only
    itself, never blank the whole collection the way a list comprehension would.
    """
    return League(**record).model_dump()


@router.get("/leagues")
def list_leagues(user_id: str = Depends(require_fantasy_beta_access)):
    """Every league this user has saved."""
    out = []
    for record in dynamo.list_fantasy_leagues(user_id):
        try:
            out.append(_league_response(record))
        except Exception:  # noqa: BLE001
            logger.warning(
                "skipping unserializable stored league %s for user", record.get("league_id")
            )
    return out


@router.post("/leagues", status_code=201)
def create_league(payload: LeagueSave, user_id: str = Depends(require_fantasy_beta_access)):
    """Save a new league config (the editor's 'start from a preset, then edit' output)."""
    try:
        record = dynamo.put_fantasy_league(user_id, None, payload.model_dump())
    except ValueError as e:
        if str(e) == "too_many_leagues":
            raise HTTPException(
                status_code=409,
                detail=f"You can save at most {dynamo.MAX_LEAGUES_PER_USER} leagues",
            ) from e
        raise HTTPException(status_code=400, detail="Could not save league") from e
    return _league_response(record)


@router.put("/leagues/{league_id}")
def update_league(
    league_id: str, payload: LeagueSave, user_id: str = Depends(require_fantasy_beta_access)
):
    if dynamo.get_fantasy_league(user_id, league_id) is None:
        raise HTTPException(status_code=404, detail="League not found")
    record = dynamo.put_fantasy_league(user_id, league_id, payload.model_dump())
    return _league_response(record)


@router.delete("/leagues/{league_id}", status_code=204)
def delete_league(league_id: str, user_id: str = Depends(require_fantasy_beta_access)):
    try:
        dynamo.delete_fantasy_league(user_id, league_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="League not found") from e
    return None
