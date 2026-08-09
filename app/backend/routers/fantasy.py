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
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.backend.dependencies import (
    get_admin_user,
    require_fantasy_access,
    require_fantasy_beta_access,
)
from app.backend.models.fantasy import League, LeagueSave
from app.backend.services import dynamo, entitlement

logger = logging.getLogger(__name__)

# Every route in this router requires fantasy entitlement (defense-in-depth).
router = APIRouter(
    prefix="/fantasy",
    tags=["fantasy"],
    dependencies=[Depends(require_fantasy_access)],
)

# ══════════════════════════════════════════════════════════════════════════════
# ⭐ THE FREE GENERIC BOARD — `Capability.GENERIC_BOARD` (freemium build, 2026-08-08)
# ══════════════════════════════════════════════════════════════════════════════
# A SECOND router object with NO `require_fantasy_access`, mirroring `fantasy_public.router` and
# `fantasy_import.public_router`: this codebase's rule is that an exemption lives as a separate
# router object, never as a flag inside the gated one. `router` above keeps its blanket 403 for
# everything else (`/leagues`, `/nfl/my-teams`, the admin-only MLB board), so the safe default is
# unchanged and nothing can accidentally fall out of the gate by being added to the wrong function.
#
# These three routes are the FREE half of the product: the generic board — the season projection and
# ONE scored preset board (`full_ppr`/12), with the full model output, for anonymous, free and
# paying callers alike. The other 13 preset boards the exporter publishes are paid; `nfl_board`
# below is the only route here that reads its caller, and its docstring says why.
#
# 🗄️ WHAT CHANGED. Until 2026-08-08 these were DUAL-MODE: an entitled caller got the numbers and
# everyone else got an E9.56 LOCKED payload (identity + ADP, every model value stripped, rows
# re-ordered onto market ADP). The freemium build retired that — the generic board is the
# acquisition wedge, so withholding its numbers was withholding the thing that earns the signup.
# The redaction code still exists in `services/entitlement.py`, clearly marked retired; nothing here
# calls it.
#
# ⭐⭐ THE PROPERTY THREE OTHER SYSTEMS DEPEND ON: every FREE response here is ENTITLEMENT-INDEPENDENT
# — the manifest, the projections, and the free board URL are byte-identical for anonymous, free and
# paying callers. Because those bytes do not vary, (a) G100-D1's CDN route may cache one copy for
# everybody, (b) `cost_guardrails.cache_control_for`'s "same URL, two bodies" hazard does not arise,
# and (c) the frontend's `entitled`-keyed query cache can never strand a new subscriber on a stale
# view. ⛔ Re-introducing per-caller variation on a FREE url silently invalidates all three at once.
# Pinned by `test_freemium_tier.py::test_the_free_generic_board_is_byte_identical_for_every_caller`.
#
# ⚠️ THE PAID BOARD URLS ARE THE EXPLICIT EXCEPTION and must be kept outside all three: they answer
# 200 or 403 depending on the caller, so the public CDN route's allowlist validates `config`/`size`
# against the free selection and refuses to proxy anything else. A paid board is fetched by the
# entitled client straight from the API, never through the edge.
#
# ⚠️ GATEWAY. A route is only reachable anonymously once its API Gateway authorizer is set to NONE —
# that is per-route console config, outside this repo's IaC (NF3.2), so a route that is public in
# code still returns 401 before Lambda until the operator flips it. Commands in
# `infrastructure/aws_resources.md`. That flip is also what makes `services/jwt_verify.py`
# load-bearing: with no authorizer the Bearer token is attacker-controlled, and only a
# signature-verified one may grant the PAID capabilities.
board_router = APIRouter(prefix="/fantasy", tags=["fantasy"])

_DEFAULT_SEASON = int(os.getenv("NFL_FANTASY_SEASON", "2026"))
_CACHE_BUCKET = os.getenv("CACHE_BUCKET")
# Optional local board dir for backend dev (skips S3). Points at e.g. a checked-out
# `.../nfl-fantasy` root that contains `<season>/manifest.json`.
_LOCAL_BOARD_DIR = os.getenv("FANTASY_BOARD_DIR")

# config names are league presets (e.g. "full_ppr_3wr"); size is a team count. Both
# feed an S3 key / filename, so validate strictly to prevent path traversal.
_CONFIG_RE = re.compile(r"^[a-z0-9_]{1,40}$")

_s3 = boto3.client("s3", region_name="us-east-1")


def _load_json(rel_key: str, sport: str = "nfl") -> dict | list | None:
    """Load a board JSON blob by its relative key ("<season>/manifest.json"), from a
    local dir when configured, else S3. Returns None on miss.

    `sport` selects the key space (`fantasy/nfl/...` vs E8.1's `fantasy/mlb/...`). It defaults to
    `"nfl"` so every pre-E8.1 caller — including `fantasy_public.py`, which imports this helper —
    keeps its exact behaviour: this is an ADDITIVE parameter, not a signature change (NF-C0).
    """
    local_dir = _LOCAL_BOARD_DIR if sport == "nfl" else os.getenv("MLB_FANTASY_BOARD_DIR")
    if local_dir:
        path = Path(local_dir) / rel_key
        if path.is_file():
            return json.loads(path.read_text())
        return None
    if not _CACHE_BUCKET:
        raise HTTPException(status_code=503, detail="Fantasy data store is not configured")
    key = f"fantasy/{sport}/{rel_key}"
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


@board_router.get("/nfl/manifest")
def nfl_manifest(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """The NFL fantasy draft-board manifest (available configs + sizes + roster shapes).

    FREE — `Capability.GENERIC_BOARD`. No `Request` parameter and no entitlement read at all: the
    absence is deliberate and is the strongest available statement that nothing here varies by
    caller (a handler that cannot see the caller cannot branch on them).
    """
    data = _load_json(f"{season}/manifest.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy manifest not found")
    return entitlement.open_manifest_payload(data)


@board_router.get("/nfl/projections")
def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """NF3 — the format-INDEPENDENT NFL season projection (raw stat line + the 80% PPR
    interval + uncertainty type / confidence). The browse Projections surface reads this;
    the format-SCORED numbers come from /nfl/board.

    FREE — `Capability.GENERIC_BOARD`; see `nfl_manifest` for why there is no caller parameter.
    """
    data = _load_json(f"{season}/projections.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy projections not found")
    return entitlement.open_projections_payload(data)


@board_router.get("/nfl/board")
def nfl_board(
    request: Request,
    config: str = Query(..., description="league preset name, e.g. full_ppr_3wr"),
    size: int = Query(..., ge=2, le=32, description="team count"),
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
):
    """A single (config, size) NFL fantasy draft board for a shipped league PRESET.

    ⭐ ONE PRESET IS FREE — `full_ppr`/12 (`entitlement.FREE_BOARD_CONFIG`/`FREE_BOARD_SIZE`); the
    other 13 the exporter publishes need full entitlement. Operator decision 2026-08-08: the free
    board is the acquisition wedge and one format makes that case, while "the board scored for the
    format you actually play" is a real, legible thing a membership buys. The reason it is full PPR
    at 12 teams rather than any other preset is a DATA fact — that is the league our ADP sample
    describes — and it is written up on the constant.

    ⚠️ THIS IS THE ONE ROUTE ON THIS ROUTER THAT READS ITS CALLER, and it is why `nfl_manifest` /
    `nfl_projections` take no `Request` while this one does. The consequence for the CDN is exact:
    the FREE board URL is still byte-identical for everybody and stays cacheable, and every PAID
    board URL is caller-dependent and must never be proxied through the public edge route (the
    Next.js allowlist validates `config`/`size` against the free selection for precisely this
    reason). Pinned by `test_freemium_tier.py`.

    A paid board is a 403, NOT a redacted 200. The E9.56 lock existed to render a per-cell CTA on a
    board the visitor had asked for; here the visitor is not on a paid board at all — the client
    keeps them on the free one and shows the boundary — so a lock payload would be an elaborate way
    of describing a page nobody is looking at. 403 also keeps the answer unambiguous for the CDN.

    ⛔ A PERSONALIZED board is a different thing again: computed from a stored per-user config, it
    is `Capability.PERSONALIZATION`, and it lives behind `require_fantasy_access` on
    `/fantasy/leagues` + `/fantasy/nfl/my-teams`. Nothing here serves one.

    Returns a bare LIST — never an envelope object; the deployed client indexes it directly and
    wrapping it would be the NF-C0 blank-screen break.
    """
    if not _CONFIG_RE.match(config):
        raise HTTPException(status_code=422, detail="Invalid config name")
    # Resolved AFTER the syntactic check so a junk config is a 422 for everyone rather than leaking
    # the caller's tier through the status code.
    if not entitlement.allows_board(config, size, entitlement.resolve_entitlement(request)):
        raise HTTPException(
            status_code=403,
            detail="This league format is part of a Credence membership.",
        )
    data = _load_json(f"{season}/board_{config}_{size}.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy board not found")
    return data


# ══════════════════════════════════════════════════════════════════════════════
# E8.1 — MLB DYNASTY PROSPECT BOARD (the baseball analog of the NFL surfaces above)
# ══════════════════════════════════════════════════════════════════════════════
# Same serving shape as NFL, deliberately: static JSON written by
# `quant_sports_intel_models/baseball/fantasy/export_prospect_board_json.py` to
# s3://$CACHE_BUCKET/fantasy/mlb/<season>/, read here behind the router's
# `require_fantasy_access`. NF3 rejected a request-time `lakehouse_query` for the NFL
# boards because a wide lakehouse read fails SILENTLY inside the API Lambda (E9.26b —
# `lakehouse_query` catches and returns `[]`, so the panel renders empty with no error
# anywhere); the same reasoning applies verbatim to a ~1,450-row prospect board.
#
# 🔒 ADMIN-ONLY WHILE THIS SURFACE IS IN DEVELOPMENT (operator, 2026-08-02).
#
# ⚠️ NARROWER THAN THE ROUTER, AND NARROWER THAN NF-C0b's BETA GATE. The router's
# `require_fantasy_access` grants `subscriber` OR `admin` OR `fantasy_comp` — that is
# correct for the shipped NFL board endpoints it is shared with, and WRONG here: it
# would put an in-development surface in front of every paying subscriber.
# `require_fantasy_beta_access` (`admin` + `fantasy_comp`) is still too wide. So these
# two routes additionally depend on `get_admin_user` — the only genuinely admin-only
# gate in the codebase.
#
# The extra dependency lives on each ROUTE rather than on the router because the router
# object is shared with the NFL board endpoints, which must stay open to subscribers.
# Both dependencies run and the stricter one binds, exactly as NF-C0b's beta gate does.
#
# ⏭️ TO OPEN THIS TO SUBSCRIBERS LATER: delete the `_admin` parameter from both routes
# AND flip `restrict: "admin"` on the two MLB items in `frontend/lib/nav-model.ts`, AND
# swap `AdminGuard` back to `FantasyGuard` on both pages. All four move together — the
# server gate is the real one, but leaving a nav item pointing at a route that 403s is
# its own bug.
#
# ⚠️ The API Gateway Cognito authorizer must stay ON for `/fantasy/mlb/*`: an authorizer
# is per-ROUTE console config, outside this repo's IaC (NF3.2), so these need NO gateway
# change — they inherit the default. An explicit `--authorization-type NONE` route would
# silently un-gate the board.
#
# ⚠️ BUILD-TIME FRESHNESS. These blobs change only when the exporter re-publishes. A
# rebuilt board does NOT reach users until then.

_MLB_DEFAULT_SEASON = int(os.getenv("MLB_PROSPECT_BOARD_SEASON", "2026"))


@router.get("/mlb/prospects/manifest")
def mlb_prospect_manifest(
    season: int = Query(default=_MLB_DEFAULT_SEASON, ge=2000, le=2100),
    _admin: str = Depends(get_admin_user),
):
    """Board meta: counts, the filter vocabularies (orgs / levels / positions / ETAs / AL-NL),
    and the honest framing strings — which are carried in the PAYLOAD, not written into the
    frontend, so the wording lives with the model that earned it (E7.8's position asymmetry,
    E7.3's per-metric confidence, the measured absences).

    ADMIN ONLY while the surface is in development — see the block above."""
    data = _load_json(f"{season}/manifest.json", sport="mlb")
    if data is None:
        raise HTTPException(status_code=404, detail="Prospect board manifest not found")
    return data


@router.get("/mlb/prospects/board")
def mlb_prospect_board(
    season: int = Query(default=_MLB_DEFAULT_SEASON, ge=2000, le=2100),
    _admin: str = Depends(get_admin_user),
):
    """The full prospect board — one row per prospect, all three views plus the E7.13 comps.

    Served whole (~2 MB) and filtered/sorted CLIENT-side: the board is a browse surface where
    every interaction is a re-filter, so per-query round trips would be strictly worse, and the
    exporter guards the size against Lambda's 6 MB proxy-response cap.

    ADMIN ONLY while the surface is in development — see the block above."""
    data = _load_json(f"{season}/board.json", sport="mlb")
    if data is None:
        raise HTTPException(status_code=404, detail="Prospect board not found")
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


@router.get("/nfl/my-teams")
def nfl_my_teams(
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
    user_id: str = Depends(require_fantasy_access),
):
    """NF-C6 — every saved NFL league's linked team, ready for CLIENT-SIDE league-scoring.

    ⚠️ NO STAT IS SCORED HERE. The actual league-scoring math (`per_stat` weights × the projection's
    raw stat line, the FG-bucket fold, the coverage report) stays entirely client-side against
    `/fantasy/nfl/projections` — the SAME reusable `buildBoard`/`resolveScoring` path NF-C0b's board
    already runs, because `fantasy_engine` (pandas/numpy) cannot be imported into this Lambda (see
    `models/fantasy.py`'s module docstring). Re-deriving that math here in bare Python would be a
    SECOND, driftable scorer — this endpoint only assembles the config + the linked roster snapshot
    (`League.imported_roster`/`source_team_key`, set when the league was imported — see the field
    docstrings) so the browser can call the one scorer that already exists.

    A single narrow DynamoDB item read (E9.26b: never a wide/lakehouse query that can fail silently
    inside this Lambda and come back `[]`), one row per league, malformed rows skipped individually.

    🔒 BROADER gate than `/fantasy/leagues` (`require_fantasy_access`, not the beta-only editor
    gate) on purpose: these are the user's OWN leagues, and the 2026 projection VALUES a subscriber
    is entitled to are gated identically to every other NFL fantasy read in this router — the same
    `require_fantasy_access` check `/fantasy/nfl/projections` and `/fantasy/nfl/board` already use.
    A caller who is not yet entitled to IMPORT a league (still beta-only) simply sees an honest empty
    list here, not a 403 — this stays correct without a second migration whenever NF-C0 opens wider.
    """
    out = []
    for record in dynamo.list_fantasy_leagues(user_id):
        if str(record.get("sport") or "nfl") != "nfl":
            continue
        try:
            out.append(_league_response(record))
        except Exception:  # noqa: BLE001
            logger.warning(
                "skipping unserializable stored league %s for my-teams", record.get("league_id")
            )
    return {"season": season, "leagues": out}


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
