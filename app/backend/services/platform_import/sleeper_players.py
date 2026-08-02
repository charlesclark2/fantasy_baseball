"""sleeper_players.py — NF-C0c: the READ side of Sleeper player-id → name resolution.

Sleeper's roster endpoint returns bare player ids; resolving them needs Sleeper's ~5 MB
`v1/players/nfl` dump, which Sleeper's own guidance says to fetch at most once a day — far too heavy
to pull inside an import request. `run_sleeper_player_ingest.py` (offline, operator-run) publishes a
SLIM `{sleeper_player_id: {name, position, team, gsis_id?}}` artifact to the SAME static-JSON path
the draft boards use (`s3://$CACHE_BUCKET/fantasy/nfl/...` — E9.26b: no request-time lakehouse read).
This module is the narrow, MEMOIZED read of that artifact: one fetch per Lambda instance, never one
per import (the E9.26b "narrow + memoized" lesson this story was explicitly gated on).

⚠️ AN EMPTY/FAILED READ MUST NEVER LOOK LIKE "THIS PLAYER HAS NO NAME". `_players()` returns `None`
(not `{}`) when the artifact could not be loaded at all — unconfigured, missing, or unreadable — so
`resolve()` can tell "we have no name cache right now" apart from "we checked and truly don't know
this id" and the caller can keep the honest fallback warning instead of rendering an entire roster as
unmatched off a read that never actually happened (the E9.52 "0 rows silently reads as done" shape,
one layer up).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

_CACHE_BUCKET = os.getenv("CACHE_BUCKET")
# Same local-dev override the board endpoints use (app.backend.routers.fantasy._LOCAL_BOARD_DIR) —
# point it at a checked-out fantasy board root that also contains sleeper/players.json.
_LOCAL_BOARD_DIR = os.getenv("FANTASY_BOARD_DIR")
_S3_KEY = "fantasy/nfl/sleeper/players.json"

# Module-level memo: loaded at most ONCE per Lambda instance. `_LOADED` (not `_PLAYERS is not None`)
# is the sentinel, because a legitimate outcome of loading is "nothing there" (None) and we must not
# re-fetch on every call just because the last attempt found nothing.
_PLAYERS: "dict[str, dict] | None" = None
_LOADED = False


def _fetch() -> "dict[str, dict] | None":
    if _LOCAL_BOARD_DIR:
        path = Path(_LOCAL_BOARD_DIR) / "sleeper" / "players.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            logger.warning("sleeper players cache: local file unreadable at %s", path)
            return None
        return data if isinstance(data, dict) else None

    if not _CACHE_BUCKET:
        return None
    try:
        import boto3
        from botocore.exceptions import ClientError

        s3 = boto3.client("s3", region_name="us-east-1")
        resp = s3.get_object(Bucket=_CACHE_BUCKET, Key=_S3_KEY)
        data = json.loads(resp["Body"].read().decode("utf-8"))
        return data if isinstance(data, dict) else None
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404", "NoSuchBucket"):
            logger.error("sleeper players cache read error: %s", e)
        return None
    except Exception as e:  # noqa: BLE001
        logger.error("sleeper players cache parse error: %s", e)
        return None


def _players() -> "dict[str, dict] | None":
    global _PLAYERS, _LOADED
    if not _LOADED:
        _PLAYERS = _fetch()
        _LOADED = True
    return _PLAYERS


def reset_cache() -> None:
    """Test-only: clear the memo so the next call re-reads (production never calls this — the whole
    point is ONE load per Lambda instance)."""
    global _PLAYERS, _LOADED
    _PLAYERS, _LOADED = None, False


def resolve(player_ids: Iterable[str]) -> "tuple[dict[str, dict], bool]":
    """Resolve a batch of Sleeper player ids to `{name, position, team, gsis_id?}`.

    Returns `(matches, artifact_loaded)`. `artifact_loaded=False` means the name cache could not be
    read at all — unconfigured, a cold miss, or a genuinely empty read (treated identically: a
    resolution surface returning nothing for every id is SUSPECT, not evidence the ids have no
    names — see the module docstring). A caller uses this to distinguish "we have no name cache
    right now" (keep the original IDs-only warning) from "we resolved some but not all of these ids"
    (a scoped, honest partial warning).
    """
    players = _players()
    if not players:
        return {}, False
    out = {}
    for pid in player_ids:
        hit = players.get(str(pid))
        if hit:
            out[str(pid)] = hit
    return out, True


__all__ = ["reset_cache", "resolve"]
