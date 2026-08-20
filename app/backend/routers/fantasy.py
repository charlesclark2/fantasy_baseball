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
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.backend.dependencies import (
    get_admin_user,
    require_fantasy_access,
    require_personalized_league_access,
)
from app.backend.models.fantasy import (
    BigBoard,
    BigBoardSave,
    DraftAssistantRequest,
    FantasyPreferences,
    League,
    LeagueSave,
    sanitize_depth_targets,
)
from app.backend.services import (
    draft_assistant,
    dynamo,
    entitlement,
    league_scoring,
    projection_fields,
    scoring_probe_guard,
)
# Aliased because `depth_targets` is also the name of the FIELD this module reads off a league
# record and off a request payload; an unaliased import would shadow-read as the value in every
# local scope that touches one, which is exactly the kind of thing a reviewer skims past.
from app.backend.services import depth_targets as depth_targets_service

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


#: In-process memo of the FULL projections blob, for the server-side league scorer below.
#: Same shape and reasoning as `fantasy_public._featured_memo`: the artifact is rewritten at most
#: once per publish, and without it every `/nfl/my-teams` call would pull 1.3 MB out of S3.
#: ⚠️ Lazy by construction — a module-scope fetch is a live S3 GET paid by every importing test and
#: by every Lambda cold start.
_FULL_PROJECTIONS_TTL_SECONDS = 900
_full_projections_memo: dict[int, tuple[float, dict]] = {}


def _full_projections(season: int) -> dict | None:
    """The COMPLETE projections payload (stat line included), memoized per season.

    ⛔ NEVER returned to a caller as-is except on `/nfl/projections/full`, which is entitlement-
    gated. Every other consumer either reduces it (`public_projections_payload`) or consumes only
    the SCORED OUTPUT (`/nfl/my-teams`), which is what lets a free league be personalized without
    the substrate ever leaving the server.
    """
    import time

    now = time.time()
    hit = _full_projections_memo.get(season)
    if hit is not None and now - hit[0] < _FULL_PROJECTIONS_TTL_SECONDS:
        return hit[1]
    data = _load_json(f"{season}/projections.json")
    if data is None:
        # Deliberately NOT memoized — caching a miss would hold every league board down for the
        # full TTL after a publish blip (the `_featured_memo` rule).
        return None
    _full_projections_memo[season] = (now, data)
    return data


@board_router.get("/nfl/projections")
def nfl_projections(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """NF3 — the format-INDEPENDENT NFL season projection, PUBLIC HALF ONLY.

    FREE — `Capability.GENERIC_BOARD`; see `nfl_manifest` for why there is no caller parameter.

    🔒 NF-EPIC 1 (PM Option C, 2026-08-10) — THE RAW STAT LINE AND THE TWO PAID SCORINGS ARE
    STRIPPED HERE. Until this change the anonymous payload carried `fpStd`, `fpHalf` and the full
    stat line, gated only by which component declined to draw them; a `curl` recovered all three.
    `projection_fields.public_projections_payload` removes them from every row, and the PAID set is
    derived from the scorer's own `STAT_FIELD` map so a new scorable stat is withheld automatically
    rather than shipping public by default.

    ⭐ STILL BYTE-IDENTICAL FOR EVERY CALLER — no `Request`, no entitlement read. A subscriber gets
    this same reduced blob and fetches the paid half from `/nfl/projections/full`. That is what
    keeps G100-D1's CDN cache legal: the edge stores one copy for everybody precisely because the
    bytes do not vary by caller.
    """
    data = _load_json(f"{season}/projections.json")
    if data is None:
        raise HTTPException(status_code=404, detail="Fantasy projections not found")
    return entitlement.open_projections_payload(
        projection_fields.public_projections_payload(data)
    )


@router.get("/nfl/projections-full")
def nfl_projections_full(season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100)):
    """The COMPLETE projection — the raw stat line plus `fpStd`/`fpHalf`. PAID.

    🔒 On `router`, so it inherits the blanket `require_fantasy_access`: this is the substrate the
    PM ruled is "the crown jewel", and the only surface that serves it. A free account never needs
    it — their one personalized league is scored on the server (`/nfl/my-teams`), so their browser
    receives a board it could not have computed and never sees the inputs.

    ⚠️ NEVER add this path to the CDN allowlist (`frontend/app/api/public/[...path]/route.ts`) or
    to `cost_guardrails._PUBLIC_CACHE_RULES`. It is caller-gated, so a shared cache entry would hand
    the paid substrate to anonymous visitors — the precise breach `cache_control_for` exists to
    prevent. It is safe today for a structural reason rather than a remembered one: every request
    carries an `Authorization` header, and `cache_control_for` answers `private, no-store`
    unconditionally when it sees one.
    """
    data = _full_projections(season)
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
# ⭐ G100-C1 — AND THE FREE TIER'S ONE PERSONALIZED LEAGUE
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
# 🔒 ENTITLEMENT — A THIRD ROUTER OBJECT, NOT A PER-ROUTE OVERRIDE (G100-C1, 2026-08-08)
# ──────────────────────────────────────────────────────────────────────────────
# These routes moved OFF `router` entirely. They used to sit on it and add a NARROWER
# per-route `require_fantasy_beta_access` (`admin` + `fantasy_comp`), which worked only
# because that set is a strict SUBSET of the router's `require_fantasy_access` — both
# dependencies ran and the stricter one bound. G100-C1 inverts that relationship: a free
# signed-in account now has a quota of one league and NO fantasy entitlement at all, so
# the router-level `require_fantasy_access` would 403 them before the route was reached.
# A per-route dependency cannot WIDEN a router-level one; only a separate mount can.
#
# That is also this codebase's standing rule (`board_router`, `fantasy_public.router`,
# `fantasy_import.public_router`, `stripe.public_router`): an exemption is a router
# OBJECT, never a flag inside a gated one — so `router` keeps its blanket 403 and nothing
# can fall out of the gate by being written on the wrong function.
#
# ⭐ THE GATE IS THE QUOTA. `require_personalized_league_access` asks
# `entitlement.personalized_league_quota(...) > 0`, so the tier is a NUMBER an operator
# can move (1 today, 0 to withdraw, 25 for a subscriber) rather than a group list. And it
# resolves identity FIRST: an anonymous caller gets 401 ("sign in"), not 403 ("pay"),
# because there is nowhere to store a league without a Cognito `sub`.
#
# ⛔ PERSONALIZATION IS STILL A PAID CAPABILITY. `Capability.PERSONALIZATION` remains in
# `PAID_CAPABILITIES` and is NOT reclassified — the free tier is a quota GRANT against a
# paid capability. Moving the capability itself would have silently freed the surfaces
# that share it.
#
# ⚠️ THESE RESPONSES ARE PER-CALLER BY CONSTRUCTION, so they are the exact opposite of the
# free board's byte-identity invariant above. They must never be added to the CDN
# allowlist (`frontend/app/api/public/[...path]/route.ts`) or to `_PUBLIC_CACHE_RULES` —
# a shared cache entry here would hand one user's league to another. They are safe today
# for a structural reason rather than a remembered one: every request carries an
# `Authorization` header, and `cost_guardrails.cache_control_for` answers `private,
# no-store` unconditionally when it sees one. `test_g100_c1_free_league.py` pins both.
#
# These are WRITE endpoints, so server-side enforcement is the real gate — hiding the
# nav item stops nobody from POSTing a config straight to the API.
personal_router = APIRouter(
    prefix="/fantasy",
    tags=["fantasy"],
    dependencies=[Depends(require_personalized_league_access)],
)


def _league_response(record: dict) -> dict:
    """Serialize ONE stored league through the response model.

    Row-by-row on purpose (E9.49): a single malformed stored league must cost only
    itself, never blank the whole collection the way a list comprehension would.
    """
    return League(**record).model_dump()


def _serialize_leagues(records: list[dict]) -> list[dict]:
    out = []
    for record in records:
        try:
            out.append(_league_response(record))
        except Exception:  # noqa: BLE001
            logger.warning(
                "skipping unserializable stored league %s for user", record.get("league_id")
            )
    return out


@personal_router.get("/leagues")
def list_leagues(user_id: str = Depends(require_personalized_league_access)):
    """Every league this user has saved — the MANAGEMENT list.

    ⚠️ DELIBERATELY NOT QUOTA-CAPPED, unlike `/nfl/my-teams` below. This is the surface the
    editor lists and deletes from, and these are configs the user typed in themselves. A
    lapsed subscriber holding five leagues must be able to SEE and DELETE all five —
    capping here would strand them above a quota they can never get back under, and would
    hide their own data from them. What the free tier limits is how many personalized
    BOARDS we compute, which is capped at the point of serving.

    Returns a bare LIST — unchanged shape (NF-C0); the deployed client indexes it directly.
    """
    return _serialize_leagues(dynamo.list_fantasy_leagues(user_id))


@personal_router.get("/nfl/my-teams")
def nfl_my_teams(
    request: Request,
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
    user_id: str = Depends(require_personalized_league_access),
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

    ⭐ G100-C1 — THIS IS THE SERVE POINT OF THE FREE QUOTA, and the only one that can be. Creation
    is refused at the quota (`create_league` below), but that check never runs for a subscriber who
    saved five leagues and then LAPSED: no create happens, so without a cap here they would keep
    receiving five personalized boards indefinitely — the paid tier, retained by having once paid
    for it. `leagues_within_quota` keeps the OLDEST by `created_at`, deterministically.

    The withheld leagues are still fully visible and deletable on `/fantasy/leagues` — the cap is on
    the personalization we COMPUTE, never on the user's access to their own configs.

    ⚠️ ADDITIVE RESPONSE KEYS ONLY (NF-C0/E8.6). `quota`, `saved_total` and `withheld_by_quota` are
    NEW; `season` and `leagues` are untouched, so the deployed client — which knows none of them —
    keeps rendering exactly what it renders today rather than going blank on a missing key. The
    client reads each new key with a `?? default`.

    🔒 The gate is the caller's QUOTA (`require_personalized_league_access`), not fantasy
    entitlement. It used to be `require_fantasy_access` so that a subscriber who could not yet
    IMPORT a league still saw an honest empty list; that reasoning survives intact — a caller with
    no saved leagues still gets `leagues: []` rather than a refusal — but the set of callers who may
    reach it is now everyone with a quota to spend, which is every signed-in account.
    """
    nfl_records = [
        r for r in dynamo.list_fantasy_leagues(user_id) if str(r.get("sport") or "nfl") == "nfl"
    ]
    quota = entitlement.personalized_league_quota(entitlement.resolve_entitlement(request))
    served = entitlement.leagues_within_quota(nfl_records, quota)
    out = _serialize_leagues(served)
    return {
        "season": season,
        "leagues": out,
        "quota": quota,
        "saved_total": len(nfl_records),
        "withheld_by_quota": max(0, len(nfl_records) - len(served)),
        # 🔒 NF-EPIC 1 — the ROSTER rows, scored SERVER-SIDE (additive key, NF-C0).
        #
        # This surface used to score in the browser off the raw stat line. That substrate is paid
        # now, so the join happens here and the client receives only the OUTPUT.
        #
        # ⚠️ ROSTER ROWS ONLY, NOT THE BOARDS — and the bound is the reason. A full board is ~858
        # rows; at a subscriber's quota of 25 leagues that is ~6 MB, straight through Lambda's
        # proxy-response cap. A roster is ~20 rows per league. The one full board a page actually
        # needs comes from `/nfl/league-board`, one league at a time.
        "rosters": _scored_rosters(served, season),
        # 🔴 NF-K1 — which PROJECTABLE positions the served board actually carries, so a roster row
        # that matched nothing can say WHY. Additive (NF-C0): a deployed client that does not know
        # this key keeps rendering exactly what it renders today.
        #
        # ⚠️ `null`, NOT `[]`, when the projections blob could not be read. An empty list is a real
        # answer ("the board published no projectable position"), and conflating "we don't know"
        # with "nothing is published" would make every unmatched row on a degraded read claim the
        # board is missing that position — a confident wrong explanation is worse than none
        # (NF1.7 (a)). The client renders the plain "not matched" wording when this is null.
        "board_positions": _published_positions(season),
    }


def _published_positions(season: int) -> list[str] | None:
    """The PROJECTABLE positions the served board carries, or None if we could not read it.

    Reads through the same memoized `_full_projections` the roster scorer uses, so this costs no
    extra S3 GET. Best-effort for the same reason `_scored_rosters` is: an unreadable projections
    blob must never take down the caller's league list."""
    try:
        projections = _full_projections(season)
    except Exception:  # noqa: BLE001
        logger.warning("could not load projections for %s; board positions unknown", season)
        return None
    players = (projections or {}).get("players")
    if not players:
        return None
    return league_scoring.published_positions(players)


def _scored_rosters(records: list[dict], season: int) -> dict[str, list[dict]]:
    """`{league_id: [{roster, board}]}` — each league's linked roster joined to its OWN scored board.

    A league with no linked team yields `[]`, which is a real state (hand-entered, or imported
    without picking a team) and distinct from a league whose roster matched nothing.

    Per-league failures are contained (E9.49): one unscoreable config costs only its own entry
    rather than blanking every league the user has.

    ⭐⭐ BEST-EFFORT, AND THIS IS THE LOAD-BEARING PART OF THE FUNCTION.
    `/fantasy/nfl/my-teams` was a pure DynamoDB read before NF-EPIC 1 — it could not fail on S3.
    Adding the scored roster made it read the projections blob, and the first cut let that read
    RAISE: `_load_json` answers 503 when `CACHE_BUCKET` is unset and 502 on a read error, so an
    absent or unreadable projections artifact took the WHOLE endpoint down and the user's saved
    leagues disappeared with it. Someone's league list vanishing because a PROJECTION file is
    missing is the wrong failure by a wide margin — the list is the core of this response and the
    roster join is an enhancement on top of it.

    So the scoring is contained here and degrades to `{}`. The client already reads `rosters`
    with `?? {}` (it is an additive key the deployed frontend does not know about), so an
    unscoreable slate renders as "no roster linked" rather than as an error — and `leagues`,
    `quota`, `saved_total` and `withheld_by_quota` are all unaffected.

    ⚠️ `/fantasy/nfl/league-board` deliberately does NOT do this: there the board IS the response,
    so an unreadable projection must surface as a real failure the page can report ("we couldn't
    score your league"), not as a silently empty board. Same read, opposite correct behaviour,
    because the two endpoints promise different things.
    """
    try:
        projections = _full_projections(season)
    except Exception:  # noqa: BLE001
        logger.warning("could not load projections for %s; serving leagues without rosters", season)
        projections = None
    players = (projections or {}).get("players") or []
    out: dict[str, list[dict]] = {}
    for record in records:
        league_id = str(record.get("league_id") or "")
        roster = record.get("imported_roster") or []
        if not league_id or not roster or not players:
            out[league_id] = []
            continue
        try:
            board = league_scoring.build_board(players, record, projection_fields.STAT_FIELD)
            out[league_id] = league_scoring.match_roster_to_board(roster, board["players"])
        except Exception:  # noqa: BLE001
            logger.warning("could not score roster for league %s", league_id)
            out[league_id] = []
    return out


@personal_router.get("/nfl/league-board")
def nfl_league_board(
    request: Request,
    league_id: str = Query(..., description="a saved league id belonging to the caller"),
    season: int = Query(default=_DEFAULT_SEASON, ge=2000, le=2100),
    user_id: str = Depends(require_personalized_league_access),
):
    """ONE saved league's fully-scored board — the server-side replacement for `buildBoard`.

    🔒 NF-EPIC 1 (PM Option C). This is what makes "the stat line is paid" and "a free account keeps
    one personalized league" coexist: the substrate stays on the server and the caller receives a
    board they could not have computed. `league_scoring` mirrors `fantasy_engine`, so this board
    agrees with the shipped preset boards (see that module's header — the browser port and the
    Python engine already disagreed by up to 0.05 on interval bounds; this follows the engine).

    ⭐ THE QUOTA IS ENFORCED HERE TOO, not just on `/nfl/my-teams`. A league the caller owns but
    which sits OUTSIDE their quota is refused — otherwise a lapsed subscriber could keep pulling
    personalized boards one league at a time by id, which is the exact retention-by-having-once-paid
    hole `leagues_within_quota` exists to close. Ownership alone is not sufficient.

    404 (not 403) for a league that is not the caller's: an id they do not own should be
    indistinguishable from one that does not exist.
    """
    records = [
        r for r in dynamo.list_fantasy_leagues(user_id) if str(r.get("sport") or "nfl") == "nfl"
    ]
    quota = entitlement.personalized_league_quota(entitlement.resolve_entitlement(request))
    served = entitlement.leagues_within_quota(records, quota)

    record = next((r for r in served if str(r.get("league_id") or "") == league_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="League not found")

    projections = _full_projections(season)
    if projections is None:
        raise HTTPException(status_code=404, detail="Fantasy projections not found")

    board = league_scoring.build_board(
        projections.get("players") or [], record, projection_fields.STAT_FIELD
    )
    return {
        "season": season,
        "league": _league_response(record),
        "board": board,
        "roster": league_scoring.match_roster_to_board(
            record.get("imported_roster") or [], board["players"]
        ),
        # 🔑 NF-C6P3 — EVERY team's roster, joined to the SAME board (additive key, NF-C0/E8.6: the
        # deployed client knows none of this and reads `league_rosters ?? []`).
        #
        # ⭐ THE JOIN HAPPENS HERE, NOT IN THE BROWSER, and that is the architecture constraint this
        # story inherited rather than a preference. `match_roster_to_board` is the SAME function the
        # caller's own roster already goes through — no new scorer (the fourth-implementation tax
        # `test_nf_epic1_parity.py` exists to police) and no new read (E9.26b: a wide
        # `lakehouse_query` in this Lambda fails SILENTLY and returns `[]`). It is one extra pass
        # over a board that is already in memory.
        "league_rosters": _joined_league_rosters(record, board["players"]),
    }


def _joined_league_rosters(record: dict, board_players: list[dict]) -> list[dict]:
    """`[{team_key, team_name, is_mine, rows: [{roster, board}]}]` — every stored team's roster,
    joined to this league's own board.

    `is_mine` is resolved from `source_team_key` so the consumer never has to re-derive which team
    is the caller's by NAME — two managers in one league may well pick the same team name, and a
    name match would then highlight the wrong row on the comparison table.

    ⚠️ Returns `[]` when the league has no stored rosters. That is the ordinary state for every
    league imported before this shipped and for every hand-entered one, and it is distinguishable
    from "this league has rosters and they are all empty" by the surfaces that care.
    """
    stored = record.get("league_rosters") or []
    mine = str(record.get("source_team_key") or "")
    out: list[dict] = []
    for entry in stored:
        if not isinstance(entry, dict):
            continue
        team_key = str(entry.get("team_key") or "")
        out.append(
            {
                "team_key": team_key,
                "team_name": str(entry.get("team_name") or ""),
                "is_mine": bool(mine) and team_key == mine,
                "rows": league_scoring.match_roster_to_board(
                    entry.get("players") or [], board_players
                ),
            }
        )
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-C4 — the CUSTOM BIG BOARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# A user's own ranking of one published (config, size) board, saved so it survives a reload and is
# there on draft day. Three routes, all on `router` — i.e. behind `require_fantasy_access`, the SAME
# gate as the live draft and auction optimizers, which is the entitlement this surface was specified
# at. (Not `personal_router`: that gate is the personalization QUOTA, which a free account has one
# of; a custom big board is the paid decision-support half, like the optimizers it sits beside.)
#
# ⛔ THESE ARE PER-CALLER AND MUST NEVER REACH A SHARED CACHE. Same rule, and the same structural
# reason, as the personalization endpoints: every request carries an `Authorization` header, so
# `cost_guardrails.cache_control_for` answers `private, no-store` unconditionally. They must not be
# added to the CDN allowlist (`frontend/app/api/public/[...path]/route.ts`), to `_PUBLIC_CACHE_RULES`
# or to the degrade-mode floor — a saved board is paid personalization, and the floor's promise is
# the FREE board plus the account, not this.
#
# ⚠️ The response is a NEW shape on a NEW path, so there is no NF-C0 additivity hazard here; the
# hazard is on the way out — the deployed client must keep reading every key with `?? default`,
# because `frontend/` ships on merge and this Lambda only on `deploy.sh`.

_BOARD_KEY_RE = re.compile(r"^[A-Za-z0-9_:-]{1,60}\|(?:[2-9]|[12][0-9]|3[0-2])$")


def _big_board_key(config: str, size: int) -> str:
    """The DynamoDB map key for one (config, size) board.

    ⭐ DERIVED HERE, NEVER ACCEPTED FROM THE CLIENT on a write. `config`/`size` are validated by
    `BigBoardSave`, so the key is a function of two already-clean values and a caller cannot choose
    the attribute name it lands on. `frontend/lib/big-board.ts::boardKey` computes the same string
    for its local cache, but nothing here trusts it.
    """
    return f"{config}|{int(size)}"


def _big_board_response(record: dict) -> dict:
    """Serialize ONE stored board through the response model (row-by-row, per E9.49)."""
    return BigBoard(**record).model_dump()


@router.get("/nfl/custom-boards")
def list_custom_boards(user_id: str = Depends(require_fantasy_access)):
    """Every custom big board this caller has saved.

    Returns an ENVELOPE rather than a bare list, so the surface can render the storage ceiling in
    its own words instead of hardcoding a number the server owns (the one-thing-two-owners class).

    ⚠️ Serialized one record at a time and a malformed one is SKIPPED: a single un-representable
    stored board must never blank the whole collection (E9.49's `GET /bets` outage).
    """
    boards = []
    for record in dynamo.list_fantasy_big_boards(user_id):
        try:
            boards.append(_big_board_response(record))
        except Exception:  # noqa: BLE001
            logger.warning(
                "skipping unserializable stored big board %s", record.get("board_key")
            )
    return {"boards": boards, "max_boards": dynamo.MAX_BIG_BOARDS_PER_USER}


@router.put("/nfl/custom-boards")
def save_custom_board(
    payload: BigBoardSave,
    user_id: str = Depends(require_fantasy_access),
):
    """Create or overwrite the caller's board for one (config, size). Idempotent by that pair.

    ⭐ A PUT WITH NO ID IN THE PATH, deliberately. The identity of a big board IS its (config, size)
    — a user has one ranking per board, not a collection of them — so letting the client choose a
    key would only create a way for two saves of the same board to land under different names and
    for the surface to load whichever it happened to ask for.

    ⭐ 413 IS A REAL, RENDERABLE ANSWER, NOT A FAILURE TO PAPER OVER. Every user's whole state shares
    ONE 400 KB DynamoDB item (NF-C6P3), so a save that would overflow it is refused WHOLE and the
    caller is told why — nothing is evicted and nothing is stored half-ranked. The `detail` is
    written to be shown to a person, because the surface renders it verbatim in its save-status line
    (E8.6: Saving… / ✓ Saved / a real error).
    """
    doc = payload.model_dump()
    key = _big_board_key(doc["config"], doc["size"])
    try:
        record = dynamo.put_fantasy_big_board(user_id, key, doc)
    except ValueError as e:
        if str(e) == "too_many_boards":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You can keep {dynamo.MAX_BIG_BOARDS_PER_USER} custom boards. "
                    "Delete one you no longer need to save this."
                ),
            ) from e
        if str(e) == "board_too_large":
            raise HTTPException(
                status_code=413,
                detail=(
                    "This board is too large to save alongside your other saved data. "
                    "Nothing was changed — delete a custom board you no longer need and try again."
                ),
            ) from e
        raise HTTPException(status_code=400, detail="Could not save this board") from e
    return _big_board_response(record)


@router.delete("/nfl/custom-boards/{board_key}", status_code=204)
def delete_custom_board(board_key: str, user_id: str = Depends(require_fantasy_access)):
    """Delete one saved board. 404 for a key the caller does not own.

    The key is validated before it reaches storage — not because a map key can traverse a path
    (it cannot), but because an unbounded caller-supplied attribute name is how an item grows keys
    nothing will ever read, on a row whose size ceiling is the constraint this whole feature is
    built around.
    """
    if not _BOARD_KEY_RE.match(board_key):
        raise HTTPException(status_code=404, detail="Board not found")
    try:
        dynamo.delete_fantasy_big_board(user_id, board_key)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Board not found") from e
    return None


def _enforce_scoring_probe_guard(
    user_id: str, ent, *, before: dict | None, after: dict
) -> None:
    """NF-LEAK1 — price a scoring change, or refuse a config shaped like an extraction probe.

    🔒 WHAT THIS DEFENDS. `/fantasy/nfl/league-board` scores an ARBITRARY caller-supplied config
    against the full projection and returns `pts` per player. That is what lets a free account keep a
    personalized league without ever seeing the paid stat line — and, by construction, it also leaks
    information about that stat line: zero every weight but one and `pts` IS the stat.
    Measured on the pre-fix code (`scripts/nf_leak1_reconstruction_cost.py`): the whole paid line for
    all 858 players in 44 round trips and 22 seconds. See `scoring_probe_guard`'s header for the
    model-by-model breakdown and for why this is "impractical + attributable", never "closed".

    ⭐ ORDER IS DELIBERATE — SHAPE FIRST, THEN BUDGET. A config we are going to refuse outright must
    not spend one of the caller's tokens; otherwise a scripted attacker could drain a real user's
    bucket with configs that were never going to be stored, and a user who typo'd a weight would be
    charged for our own refusal.

    ⚠️ KNOWN, ACCEPTED WART: on `POST`, this runs BEFORE the quota check inside
    `put_fantasy_league`, so a free caller already at their one-league quota spends a token and then
    gets a 409. Costing them 1 of 12 in a flow the editor already disables (`atQuota`) is the
    cheaper trade — the alternative is re-deriving the quota count here, which duplicates a rule
    G100-C1 deliberately keeps in the WRITER (and the E9.60 coupling trap).

    ⚠️ THE SHAPE RULES ARE UNIFORM; THE BUDGET IS NOT. An entitled caller can already `GET
    /fantasy/nfl/projections/full` and receive the whole stat line in one request, so metering their
    league edits protects nothing and only degrades what they paid for. The shape rules stay uniform
    because they are league-plausibility rules that no real config violates, and applying them only
    to free accounts would make a subscriber's saved league unsavable the day they lapse.
    """
    problems = scoring_probe_guard.shape_violations(after)
    if problems:
        raise HTTPException(status_code=400, detail="; ".join(problems))

    if getattr(ent, "fantasy", False):
        return
    if not scoring_probe_guard.scoring_changed(before, after):
        return

    verdict = scoring_probe_guard.charge(
        dynamo.get_fantasy_scoring_ledger(user_id), after, time.time()
    )

    if verdict.probe_shaped:
        # Attributable by construction — every one of these carries a Cognito `sub`, which is the
        # difference between this vector and the anonymous `curl` NF-EPIC 1 closed.
        logger.warning(
            "[METRIC] fantasy_scoring_probe user=%s changes=%s probe_hits=%s allowed=%s",
            user_id, verdict.ledger.get("changes"), verdict.ledger.get("probe_hits"),
            verdict.allowed,
        )

    if not dynamo.put_fantasy_scoring_ledger(user_id, verdict.ledger):
        # The charge did not land. Loud, never silent (NF1.7 (a)): a guard that could not record
        # its own state has not passed, and a run of these means the budget is not being enforced.
        logger.warning(
            "[METRIC] fantasy_scoring_ledger_write_failed=1 user=%s — this change went uncounted",
            user_id,
        )

    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail=scoring_probe_guard.throttle_message(verdict.retry_after_seconds),
            headers={"Retry-After": str(verdict.retry_after_seconds)},
        )


@personal_router.post("/leagues", status_code=201)
def create_league(
    request: Request,
    payload: LeagueSave,
    user_id: str = Depends(require_personalized_league_access),
):
    """Save a NEW league config (the editor's 'start from a preset, then edit' output).

    ⭐ G100-C1 — THE FREE CAP IS ENFORCED HERE, SERVER-SIDE. The quota comes from the caller's
    entitlement, not from `dynamo.MAX_LEAGUES_PER_USER` (which is the storage ceiling and is what a
    SUBSCRIBER's quota resolves to). A free account's second league is a 409 whether it arrives from
    the UI or from a hand-rolled POST — hiding the button is not a gate.

    The 409 detail is written from the caller's OWN quota so a free user reads "1" and a subscriber
    reads "25"; quoting the storage constant would have told a free user the wrong number, which on
    a paywall is worse than saying nothing.
    """
    ent = entitlement.resolve_entitlement(request)
    config = payload.model_dump()
    _enforce_scoring_probe_guard(user_id, ent, before=None, after=config)

    quota = entitlement.personalized_league_quota(ent)
    try:
        record = dynamo.put_fantasy_league(
            user_id, None, config, max_leagues=quota
        )
    except ValueError as e:
        if str(e) == "too_many_leagues":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You can save {quota} league{'s' if quota != 1 else ''} on your current plan."
                ),
            ) from e
        raise HTTPException(status_code=400, detail="Could not save league") from e
    return _league_response(record)


@personal_router.put("/leagues/{league_id}")
def update_league(
    request: Request,
    league_id: str,
    payload: LeagueSave,
    user_id: str = Depends(require_personalized_league_access),
):
    """Overwrite an EXISTING league.

    ⚠️ No quota check, deliberately: the cap counts leagues, and an update creates none. A free user
    at their quota of one must still be able to edit that one — a cap applied here would freeze their
    league at whatever they first typed and present as "saving is broken" (E8.6's silent-save class).
    The `get_fantasy_league` ownership check is what keeps this from reaching anyone else's record.
    """
    existing = dynamo.get_fantasy_league(user_id, league_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="League not found")

    config = payload.model_dump()
    # NF-LEAK1 — the SCORING is what opens the leak channel, so `existing` is passed in and an edit
    # that leaves it alone (rename, roster, linked team, a re-import refreshing the roster snapshot)
    # is not charged at all.
    _enforce_scoring_probe_guard(
        user_id, entitlement.resolve_entitlement(request), before=existing, after=config
    )

    record = dynamo.put_fantasy_league(user_id, league_id, config)
    return _league_response(record)


@personal_router.get("/preferences")
def get_fantasy_preferences(user_id: str = Depends(require_personalized_league_access)) -> dict:
    """The caller's ACCOUNT-level fantasy defaults.

    Today: `depth_targets`, the per-position depth target applied to every league that has not been
    given its own (NF-C7b). Precedence lives in `services/depth_targets.py`.

    ⚠️ Returns `{}` rather than 404 when nothing has been saved. "You have no defaults" is a normal
    state, not a missing resource, and a 404 here would have every client branch on an error path
    for the commonest case — which is how an empty state ends up rendering as a failure.
    """
    prefs = dynamo.get_fantasy_prefs(user_id)
    return {"depth_targets": sanitize_depth_targets(prefs.get("depth_targets"))}


@personal_router.put("/preferences")
def update_fantasy_preferences(
    payload: FantasyPreferences,
    user_id: str = Depends(require_personalized_league_access),
) -> dict:
    """Overwrite the caller's account-level fantasy defaults.

    ⚠️ NO QUOTA CHECK, matching `update_league` directly above: a default is not a league and
    creates none, so a free user at their quota of one must still be able to set one. A cap applied
    here would present as "saving is broken" (E8.6).
    """
    targets = sanitize_depth_targets(payload.depth_targets)
    saved = dynamo.upsert_fantasy_prefs(user_id, {"depth_targets": targets})
    # Echoing the SAVED value rather than the requested one is what lets the client detect a
    # silently-dropped field: NF-C7's own E8.6 lesson is that an un-deployed backend accepts an
    # unknown key, returns 200, and the user watches their setting vanish on reload. A client that
    # compares returned-vs-sent sees that immediately.
    return {"depth_targets": sanitize_depth_targets(saved.get("depth_targets"))}


@personal_router.delete("/leagues/{league_id}", status_code=204)
def delete_league(league_id: str, user_id: str = Depends(require_personalized_league_access)):
    try:
        dynamo.delete_fantasy_league(user_id, league_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="League not found") from e
    return None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# NF-C-LDA-1 — THE LIVE DRAFT ASSISTANT
# ══════════════════════════════════════════════════════════════════════════════════════════════
#
# The server half of the ESPN draft-room overlay. The Chrome extension observes the live draft
# (`extension/`) and posts a normalized state here; this returns the recommendation.
#
# 🔒 ON `router`, so it inherits the blanket `require_fantasy_access` — the same paid gate as the
# custom big board and the auction optimizer, which is the tier this surface was specified at. The
# extension therefore cannot show a recommendation to an unentitled account no matter what its own
# UI does, which is the point: a client-side gate on a paid feature is not a gate (E9.45).
#
# ⚠️ NO GATEWAY CHANGE IS NEEDED, AND THAT IS WORTH STATING because the story anticipated one.
# NF3.2's rule is that a route is only reachable ANONYMOUSLY once its API Gateway authorizer is set
# to NONE — the catch-all `ANY /{proxy+}` carries the Cognito JWT authorizer and an explicit route
# EXEMPTS a path from it. This route is the opposite case: it REQUIRES a token, so it wants the
# catch-all's authorizer and must NOT get an explicit `--authorization-type NONE` route. Adding one
# would strip a layer of defence rather than add one. (`infrastructure/aws_resources.md`.)
#
# ⚠️ IT SHIPS ONLY VIA `infrastructure/lambda/deploy.sh` (NF-C0: the API Lambda has no CD), and
# `deploy.sh` step 3c must carry `fantasy_engine/{__init__,draft,league_config}.py` or the import
# below `ModuleNotFoundError`s in prod while passing every local test.
#
# ⛔ PER-CALLER: never add this path to the CDN allowlist, `_PUBLIC_CACHE_RULES`, or the degrade
# floor. It is safe today for a structural reason rather than a remembered one — every request
# carries an `Authorization` header and `cost_guardrails.cache_control_for` answers
# `private, no-store` unconditionally when it sees one.


def _draft_league_config(payload: DraftAssistantRequest, request: Request, user_id: str) -> dict:
    """The league this draft is being ranked against, as a `LeagueConfig`-shaped dict.

    Either one of the caller's SAVED leagues (quota-enforced exactly as `/nfl/league-board` does —
    ownership alone is not sufficient, or a lapsed subscriber could keep pulling personalized
    boards one id at a time), or the draft room's own settings block translated by the SHIPPED ESPN
    adapter.

    ⭐ THE SETTINGS PATH REUSES `parse_settings_payload` RATHER THAN A NEW TRANSLATOR — the same
    function the paste import calls, so a league read through the extension and the same league
    pasted by hand produce the identical config. It also brings `assert_no_credentials` with it,
    which is a real backstop and not a formality: it runs BEFORE any parsing, so if the extension
    ever regressed into forwarding something credential-shaped, the request is refused here too.
    """
    if payload.league_id:
        records = [
            r for r in dynamo.list_fantasy_leagues(user_id)
            if str(r.get("sport") or "nfl") == "nfl"
        ]
        quota = entitlement.personalized_league_quota(entitlement.resolve_entitlement(request))
        served = entitlement.leagues_within_quota(records, quota)
        record = next(
            (r for r in served if str(r.get("league_id") or "") == payload.league_id), None
        )
        if record is None:
            # 404, not 403: an id the caller does not own must be indistinguishable from one that
            # does not exist.
            raise HTTPException(status_code=404, detail="League not found")
        return record

    from app.backend.services.platform_import import espn as espn_import

    try:
        imported = espn_import.parse_settings_payload(
            json.dumps({"settings": payload.espn_settings}), season=payload.season
        )
    except espn_import.EspnInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return imported.config


@router.post("/nfl/draft-assistant")
def nfl_draft_assistant(
    payload: DraftAssistantRequest,
    request: Request,
    user_id: str = Depends(require_fantasy_access),
):
    """Rank the caller's next pick in a LIVE ESPN draft.

    ⭐⭐ THE RESPONSE ALWAYS NAMES THE PICK IT REASONED ABOUT, and that is a FEATURE of this story
    rather than a nicety. A draft assistant fails in a once-a-year two-hour window, and its failure
    mode is that the read goes stale: the overlay keeps rendering a recommendation that was true
    four picks ago. "We cannot read your draft" and "nothing has happened yet" are otherwise
    PIXEL-IDENTICAL, so `state.overall_pick` / `state.picks_seen` / `state.on_the_clock_team` are
    echoed back verbatim for the overlay to display. A user comparing "reasoning about pick 31" with
    the pick number on ESPN's own screen can see a freeze in one glance; nothing inferable would do
    that.

    ⚠️ `resolution` IS PART OF THE ANSWER, NOT DIAGNOSTICS. A player we could not resolve is not
    recommendable, and a non-match has three genuinely different causes (NF-K1). The report keeps
    them apart so "we do not project this player" never renders the same as "our join broke".

    Honest framing: this ranks a projection under the league's own scoring. It is not a market
    edge and makes no win-rate claim — `best_alpha = 0`.
    """
    record = _draft_league_config(payload, request, user_id)

    projections = _full_projections(payload.season)
    if projections is None:
        # ⚠️ A REAL FAILURE, deliberately — the mirror of `_scored_rosters`' best-effort rule. There
        # the league LIST is the response and a missing projection must not blank it; here the
        # recommendation IS the response, so an unreadable board must surface as something the
        # overlay can report ("we couldn't score your league"), never as an empty board that reads
        # like sound advice about nobody.
        raise HTTPException(status_code=404, detail="Fantasy projections not found")

    board = league_scoring.build_board(
        projections.get("players") or [], record, projection_fields.STAT_FIELD
    )

    # ⭐ WHOSE PICKS ARE MINE IS DERIVED HERE, from `my_team` — never sent as a second list. The
    # extension reads its own team id from the draft-room URL; asking it to also partition the pick
    # stream would be a rule the two surfaces could disagree about.
    drafted = [p.player for p in payload.picks]
    mine = [p.player for p in payload.picks if payload.my_team and p.team == payload.my_team]

    from quant_sports_intel_models.fantasy_engine.league_config import LeagueConfig

    # ⭐ NF-C7b — THE EXTENSION GETS DEPTH TARGETS WITHOUT SENDING ANYTHING. `record` is the saved
    # league we just resolved (or the draft room's own settings, which carry none), so the targets
    # ride in on data already fetched. That is what keeps this free of the E8.6 deploy-skew hazard:
    # no new request field means no window in which an un-deployed backend accepts, ignores and
    # silently drops one, returning a 200 and a phantom save.
    applied_targets, targets_source = depth_targets_service.resolve_for_record(
        record, dynamo.get_fantasy_prefs(user_id).get("depth_targets")
    )

    result = draft_assistant.recommend_for_state(
        board=board,
        config=LeagueConfig.from_dict(record),
        pool=[p.model_dump() for p in payload.pool],
        drafted_espn_ids=drafted,
        my_espn_ids=mine,
        top_n=payload.top_n,
        depth_targets=applied_targets,
        depth_targets_source=targets_source,
    )
    result["season"] = payload.season
    result["league"] = {
        "name": str(record.get("name") or "Your league"),
        "n_teams": int(record.get("n_teams") or 0),
        "source": "saved" if payload.league_id else "espn_settings",
    }
    result["state"] = {
        "overall_pick": payload.overall_pick,
        "on_the_clock_team": payload.on_the_clock_team,
        "on_the_clock_is_me": bool(
            payload.my_team and payload.on_the_clock_team == payload.my_team
        ),
        "my_team": payload.my_team,
        "picks_seen": len(payload.picks),
        "pool_size": len(payload.pool),
        # ⚠️ NAMED, not implied. With no `my_team` the roster is empty for a REASON, and a roster
        # that is empty because we could not identify the caller's team must not be presented as a
        # roster that is empty because they have not picked yet — that is the same
        # "broken looks like quiet" failure the pick echo above exists to remove (NF1.7(a)).
        "my_team_known": bool(payload.my_team),
    }
    return result
