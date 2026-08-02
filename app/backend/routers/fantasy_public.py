"""fantasy_public.py — NF3.2: the fantasy football PAST-SEASON TRACK RECORD (receipts), served with
NO entitlement gate.

Every other route under `/fantasy/*` (`fantasy.py`) requires `require_fantasy_access` — that is
deliberate for the paid product (the current-season projections/boards), but this story's whole point
is a GTM proof asset a logged-out visitor can browse: our past-season projection vs that season's
preseason ADP vs the realized outcome, 2019–2025. So this lives on its OWN router with no
`Depends(require_fantasy_access)` anywhere, mirroring `fantasy_import.py`'s `public_router` (a single
exempted route kept on a separate router object, never a flag inside the gated one).

🔒 ENTITLEMENT / DATA-LAYER GUARANTEE: the public/paid split is enforced by WHAT DATA EXISTS to read,
not by a runtime check here. `export_track_record_json.py` (the only writer of the
`fantasy/nfl/track_record/*` key space this router reads) structurally refuses to ever emit the
current/locked season (see `LOCKED_SEASON` there) — so there is no 2026 projection value for this
router to accidentally serve even if a caller asked for it. This router's own `season` bound below is
a second, redundant line of defense (belt-and-suspenders on top of the writer-side guarantee), not the
only one.

Reuses `fantasy.py`'s `_load_json` (S3 vs local-dir read, same key-prefix convention) rather than a
second implementation of the same read path — that helper is already generic over the key and carries
no entitlement logic itself (the gate lives in the router's `dependencies=`, which this router simply
never sets).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from app.backend.routers.fantasy import _load_json

# No `dependencies=[Depends(require_fantasy_access)]` — this is the whole point of the router.
router = APIRouter(prefix="/fantasy/nfl/track-record", tags=["fantasy-public"])

# The current/upcoming season is the PAID product — mirrors
# `export_track_record_json.LOCKED_SEASON`. Kept as a plain literal (not an import) so this router has
# zero dependency on the export script module; the export script is the structural guarantee, this is
# only a redundant belt-and-suspenders bound.
_LOCKED_SEASON = 2026


@router.get("/manifest")
def track_record_manifest():
    """Seasons available, generated_at, and the honest headline (built entirely from the freshly
    regenerated NF-D3 scorecard's own numbers — see `export_track_record_json.build_headline`)."""
    data = _load_json("track_record/manifest.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Track record not found")
    return data


@router.get("/{season}")
def track_record_season(season: int = Path(..., ge=2000, le=_LOCKED_SEASON - 1)):
    """One past season's per-player track record (our projection vs ADP vs realized outcome).
    `le=_LOCKED_SEASON - 1` means a request for the current/locked season 404s before ever attempting
    a read — never treated as "not published yet"."""
    data = _load_json(f"track_record/season_{season}.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Track record not found for that season")
    return data
