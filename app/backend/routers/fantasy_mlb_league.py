"""E8.2 — a user's MLB dynasty league, and the availability overlay it puts on the E8.1 board.

WHAT THIS IS FOR. The prospect board is only actionable in a dynasty league if it shows who is
actually DRAFTABLE. A user uploads their league's rosters; we resolve those names against the
board, scoped to the league's AL/NL; the board then reads `available` or `rostered by <team>`.

🚪 ACCESS PATH — UPLOAD ONLY, BY DECISION. E8.2a probed CBS for a compliant read and found none
(dead API, login-walled pages, a blanket robots.txt, no OAuth program), so the one-click import was
OMITTED rather than deferred. Nothing in this module contacts a platform, and there is no
credential of any kind to accept, store or replay. If CBS ever ships an OAuth program, the adapter
would slot in beside `parse_roster_upload` and everything downstream is unchanged.

🔒 GATE. Same as E8.1 and for the same reason: `require_fantasy_access` at the router, plus
`get_admin_user` per route, because the MLB surface is admin-only dogfood until 2027 and
`require_fantasy_beta_access` (admin + fantasy_comp) is still too wide. ⚠️ These routes are
AUTHENTICATED, so they need NO API-Gateway change — they inherit the Cognito authorizer. Adding an
explicit gateway route for them would UN-gate them (NF3.2, facing the other way).

⭐ WHY THE OVERLAY IS RECOMPUTED ON EVERY READ AND NEVER STORED. The stored league holds the roster
ENTRIES; the rank-by-rank overlay is derived fresh each time. A stored overlay would silently rot
the next time the operator re-publishes the board — every rank shifts, and a board showing a
prospect as available when he is rostered looks EXACTLY like a correct board (the NF-C0 live-draft
lesson: the settings are durable, the state is always recomputed).
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.backend.dependencies import get_admin_user, require_fantasy_access
from app.backend.routers.fantasy import _load_json
from app.backend.services import dynamo
from app.backend.services.mlb_roster import (
    RosterEntry,
    RosterUploadError,
    match_roster,
    parse_roster_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/fantasy/mlb",
    tags=["fantasy"],
    dependencies=[Depends(require_fantasy_access)],
)

_SEASON = int(os.getenv("MLB_PROSPECT_BOARD_SEASON", "2026"))

#: What the availability read does and does not claim. Written HERE, server-side, so the wording
#: travels with the computation that earned it rather than drifting in a component (the NF3/E8.1
#: convention). Every number it quotes is computed per-league, not asserted in prose.
FRAMING = (
    "Availability is a factual overlay on your own uploaded rosters — not a recommendation, and "
    "not a claim about any player's value. A prospect reads as AVAILABLE when no name on any "
    "team's roster resolved to his board row. Most of a fantasy roster is established "
    "major-leaguers who are not on this board at all, so a large unresolved count is normal and "
    "expected. The rows worth checking are listed for review: a name matching two board prospects "
    "is never guessed, a same-name player whose roster position contradicts the board is not "
    "matched, and a minors-slot stash we could not place is the case where a rostered prospect "
    "could still be showing as available."
)


class PreviewRequest(BaseModel):
    # ⚠️ Deliberately NOT `Field(max_length=...)`: pydantic would reject an oversized paste with a
    # validation error whose `detail` is a LIST of objects the frontend's `apiFetch` cannot
    # surface. The parser's own size check returns a plain, actionable string instead (NF-C0).
    text: str = Field(min_length=1)
    league_scope: str = Field(default="AL")


class SaveRequest(PreviewRequest):
    name: str = Field(default="My league", min_length=1, max_length=80)
    league_id: str | None = None


class UpdateRequest(BaseModel):
    """A partial update. Every field optional — an absent field is LEFT ALONE, not cleared."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    league_scope: str | None = None
    #: `{entry_key: board_rank}` pins a manual fix; `{entry_key: null}` dismisses the row.
    overrides: dict[str, int | None] | None = None


class PickRequest(BaseModel):
    team: str = Field(min_length=1, max_length=80)


def _scope(value: str | None) -> str:
    scope = (value or "AL").strip().upper()
    if scope not in ("AL", "NL", "BOTH"):
        raise HTTPException(
            status_code=422, detail="League scope must be AL, NL or BOTH."
        )
    return scope


def _board(season: int) -> list[dict]:
    data = _load_json(f"{season}/board.json", sport="mlb")
    if not data:
        raise HTTPException(
            status_code=404,
            detail="The prospect board for that season has not been published yet.",
        )
    players = data.get("players") if isinstance(data, dict) else data
    if not isinstance(players, list) or not players:
        # ⚠️ An empty board would mark every roster player "unresolved" and every prospect
        # "available" — a plausible-looking answer that is entirely wrong. Refuse instead.
        raise HTTPException(status_code=502, detail="The prospect board could not be read.")
    return players


def _entries(league: dict) -> list[RosterEntry]:
    out: list[RosterEntry] = []
    for raw in league.get("entries") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        team = str(raw.get("team") or "").strip()
        if not name or not team:
            continue
        out.append(
            RosterEntry(
                team=team,
                slot=str(raw.get("slot") or "—"),
                name=name,
                status=(str(raw["status"]) if raw.get("status") else None),
                status_code=(str(raw["status_code"]) if raw.get("status_code") else None),
            )
        )
    return out


def _overlay(league: dict, entries: list[RosterEntry]) -> dict:
    """The league's roster + in-draft picks → what the board should show, by board rank."""
    season = int(league.get("season") or _SEASON)
    scope = _scope(league.get("league_scope"))
    overrides = {str(k): v for k, v in (league.get("overrides") or {}).items()}
    result = match_roster(entries, _board(season), None if scope == "BOTH" else scope, overrides)

    rostered: dict[str, dict] = {}
    for rank, matched in result.by_rank.items():
        rostered[str(rank)] = {
            "team": matched.entry.team,
            "slot": matched.entry.slot,
            "status": matched.entry.status,
            "confidence": matched.confidence,
            "source": "roster",
        }

    # Slice 2 — live draft picks. They are applied AFTER the roster so a player marked drafted
    # during the draft wins over a stale uploaded snapshot, which is the whole point of the
    # in-draft control: the upload is a point-in-time file, the pick is what just happened.
    picks = league.get("picks") or {}
    drafted = 0
    for rank, team in picks.items():
        if not team:
            continue
        rostered[str(rank)] = {
            "team": str(team),
            "slot": "—",
            "status": None,
            "confidence": "draft",
            "source": "draft",
        }
        drafted += 1

    counts = dict(result.counts)
    counts["drafted_in_session"] = drafted
    counts["rostered_board_rows"] = len(rostered)

    return {
        "league_scope": scope,
        "season": season,
        "teams": sorted({e.team for e in entries}) or list(league.get("teams") or []),
        "counts": counts,
        "rostered": rostered,
        "picks": {str(k): v for k, v in picks.items() if v},
        "review": [
            {
                "key": m.entry.key,
                "name": m.entry.name,
                "team": m.entry.team,
                "slot": m.entry.slot,
                "status": m.entry.status,
                "confidence": m.confidence,
                "candidates": list(m.candidates),
            }
            for m in result.review
        ],
        "framing": FRAMING,
    }


def _summary(league: dict) -> dict:
    """A league without its roster body — for the picker."""
    return {
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "league_scope": league.get("league_scope"),
        "season": league.get("season"),
        "team_count": len(league.get("teams") or []),
        "player_count": len(league.get("entries") or []),
        "updated_at": league.get("updated_at"),
        "created_at": league.get("created_at"),
    }


def _require(user_id: str, league_id: str) -> dict:
    league = dynamo.get_mlb_league(user_id, league_id)
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return league


# ── preview (parse + match, save NOTHING) ────────────────────────────────────────────────────────


@router.post("/league/preview")
def preview(
    payload: PreviewRequest,
    season: int = Query(default=_SEASON, ge=2000, le=2100),
    user_id: str = Depends(get_admin_user),
):
    """Read an upload and report what it would do — WITHOUT storing it.

    Preview-then-save is deliberate (the NF-C0 convention): the response carries the match tiers and
    the review queue, so the user agrees to an honest resolution before it becomes their league,
    rather than discovering afterwards that a rostered prospect was quietly counted as available.
    """
    scope = _scope(payload.league_scope)
    try:
        parsed = parse_roster_upload(payload.text)
    except RosterUploadError as e:
        # A user's malformed paste is a 422 with actionable copy, never a 500 — and the paste
        # itself is never logged.
        raise HTTPException(status_code=422, detail=str(e)) from e

    league = {"season": season, "league_scope": scope, "teams": parsed.teams}
    overlay = _overlay(league, parsed.entries)
    return {
        "upload_format": parsed.upload_format,
        "warnings": parsed.warnings,
        "entries": [
            {"team": e.team, "slot": e.slot, "name": e.name, "status": e.status}
            for e in parsed.entries
        ],
        **overlay,
    }


# ── saved leagues ────────────────────────────────────────────────────────────────────────────────


@router.get("/leagues")
def list_leagues(user_id: str = Depends(get_admin_user)):
    """Every MLB league this user has saved. Never raises on a store blip — an empty list and a
    failed read both render the same 'set up a league' path."""
    return {"leagues": [_summary(lg) for lg in dynamo.list_mlb_leagues(user_id)]}


@router.post("/leagues")
def save_league(
    payload: SaveRequest,
    season: int = Query(default=_SEASON, ge=2000, le=2100),
    user_id: str = Depends(get_admin_user),
):
    """Store a league's roster snapshot (replacing it wholesale when `league_id` is given).

    🔒 The raw upload is NOT stored — only the parsed entries the overlay needs. A re-upload
    replaces the snapshot rather than merging, because a merge would silently keep a player the
    user has since dropped, and a stale ROSTERED marking is invisible on the board.
    """
    scope = _scope(payload.league_scope)
    try:
        parsed = parse_roster_upload(payload.text)
    except RosterUploadError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    existing = _require(user_id, payload.league_id) if payload.league_id else {}
    record = {
        "name": payload.name.strip(),
        "league_scope": scope,
        "season": season,
        "teams": parsed.teams,
        "entries": [
            {
                "team": e.team,
                "slot": e.slot,
                "name": e.name,
                **({"status": e.status} if e.status else {}),
            }
            for e in parsed.entries
        ],
        # A re-upload keeps the user's manual fixes and in-draft picks: those are corrections to
        # OUR matching, not to their roster, and making them re-do them every upload would train
        # them to skip the review step entirely.
        "overrides": existing.get("overrides") or {},
        "picks": existing.get("picks") or {},
    }
    try:
        stored = dynamo.put_mlb_league(user_id, payload.league_id, record)
    except ValueError as e:
        if str(e) == "too_many_leagues":
            raise HTTPException(
                status_code=409,
                detail=f"You already have {dynamo.MAX_MLB_LEAGUES_PER_USER} leagues saved. "
                       "Delete one first.",
            ) from e
        raise
    return {
        "league": _summary(stored),
        "warnings": parsed.warnings,
        "upload_format": parsed.upload_format,
        **_overlay(stored, parsed.entries),
    }


@router.get("/leagues/{league_id}")
def get_league(
    league_id: str = Path(min_length=1, max_length=64),
    user_id: str = Depends(get_admin_user),
):
    """One league: its summary, its full roster (the user's own data, back to them), and the
    freshly-recomputed availability overlay."""
    league = _require(user_id, league_id)
    entries = _entries(league)
    return {
        "league": _summary(league),
        "entries": [
            {"team": e.team, "slot": e.slot, "name": e.name, "status": e.status} for e in entries
        ],
        **_overlay(league, entries),
    }


@router.patch("/leagues/{league_id}")
def update_league(
    payload: UpdateRequest,
    league_id: str = Path(min_length=1, max_length=64),
    user_id: str = Depends(get_admin_user),
):
    """Rename, re-scope, or record manual name fixes — without re-uploading the roster."""
    league = _require(user_id, league_id)
    record = {k: v for k, v in league.items() if k != "league_id"}
    if payload.name is not None:
        record["name"] = payload.name.strip()
    if payload.league_scope is not None:
        record["league_scope"] = _scope(payload.league_scope)
    if payload.overrides is not None:
        merged = dict(record.get("overrides") or {})
        merged.update({str(k): v for k, v in payload.overrides.items()})
        record["overrides"] = merged
    stored = dynamo.put_mlb_league(user_id, league_id, record)
    entries = _entries(stored)
    return {"league": _summary(stored), **_overlay(stored, entries)}


@router.delete("/leagues/{league_id}", status_code=204)
def delete_league(
    league_id: str = Path(min_length=1, max_length=64),
    user_id: str = Depends(get_admin_user),
):
    """Forget this league entirely — a real delete of the user's roster data, not a soft flag."""
    try:
        dynamo.delete_mlb_league(user_id, league_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="League not found") from e
    return None


# ── live draft assignment (slice 2) ──────────────────────────────────────────────────────────────
# During the minor-league draft the uploaded snapshot goes stale within minutes: players come off
# the board one pick at a time. These two routes are the smallest thing that keeps the board honest
# while that happens — mark a prospect as taken, or undo it. They write ONE map entry, so a pick
# recorded mid-draft cannot clobber a roster re-upload happening in another tab.


@router.put("/leagues/{league_id}/picks/{board_rank}")
def assign_pick(
    payload: PickRequest,
    league_id: str = Path(min_length=1, max_length=64),
    board_rank: int = Path(ge=1, le=100_000),
    user_id: str = Depends(get_admin_user),
):
    """Mark one board prospect as just drafted by a team; availability recomputes immediately.

    The team is accepted as free text rather than constrained to the uploaded roster's teams: a
    draft can seat a team whose roster was not in the upload, and rejecting the pick would leave
    the board saying a player who is visibly gone is still available.
    """
    league = _require(user_id, league_id)
    record = {k: v for k, v in league.items() if k != "league_id"}
    picks = dict(record.get("picks") or {})
    picks[str(board_rank)] = payload.team.strip()
    record["picks"] = picks
    stored = dynamo.put_mlb_league(user_id, league_id, record)
    return {"league": _summary(stored), **_overlay(stored, _entries(stored))}


@router.delete("/leagues/{league_id}/picks/{board_rank}")
def undo_pick(
    league_id: str = Path(min_length=1, max_length=64),
    board_rank: int = Path(ge=1, le=100_000),
    user_id: str = Depends(get_admin_user),
):
    """Undo a pick recorded by mistake — the mis-click is expected during a live draft."""
    league = _require(user_id, league_id)
    record = {k: v for k, v in league.items() if k != "league_id"}
    picks = dict(record.get("picks") or {})
    picks.pop(str(board_rank), None)
    record["picks"] = picks
    stored = dynamo.put_mlb_league(user_id, league_id, record)
    return {"league": _summary(stored), **_overlay(stored, _entries(stored))}
