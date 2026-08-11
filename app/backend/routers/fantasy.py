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
    require_personalized_league_access,
)
from app.backend.models.fantasy import League, LeagueSave
from app.backend.services import dynamo, entitlement, league_scoring, projection_fields

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
    }


def _scored_rosters(records: list[dict], season: int) -> dict[str, list[dict]]:
    """`{league_id: [{roster, board}]}` — each league's linked roster joined to its OWN scored board.

    A league with no linked team yields `[]`, which is a real state (hand-entered, or imported
    without picking a team) and distinct from a league whose roster matched nothing.

    Per-league failures are contained (E9.49): one unscoreable config costs only its own entry
    rather than blanking every league the user has.
    """
    projections = _full_projections(season)
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
    }


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
    quota = entitlement.personalized_league_quota(entitlement.resolve_entitlement(request))
    try:
        record = dynamo.put_fantasy_league(
            user_id, None, payload.model_dump(), max_leagues=quota
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
    if dynamo.get_fantasy_league(user_id, league_id) is None:
        raise HTTPException(status_code=404, detail="League not found")
    record = dynamo.put_fantasy_league(user_id, league_id, payload.model_dump())
    return _league_response(record)


@personal_router.delete("/leagues/{league_id}", status_code=204)
def delete_league(league_id: str, user_id: str = Depends(require_personalized_league_access)):
    try:
        dynamo.delete_fantasy_league(user_id, league_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="League not found") from e
    return None
