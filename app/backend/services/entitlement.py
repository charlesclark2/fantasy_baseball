"""Server-side entitlement resolution + the fantasy FREE/PAID capability split.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ THE CURRENT RULE — THE FREEMIUM BUILD (operator, 2026-08-08, GROWTH-100 §1/§6/§14)
═══════════════════════════════════════════════════════════════════════════════════════════════════

The boundary is now drawn by CAPABILITY, not by SEASON:

  FREE, for everyone including anonymous — the GENERIC board. Overall + position rankings for the
  shipped league PRESETS, the format-independent projections, the 80% ranges, market ADP, the
  player pages and the methodology. This is the acquisition wedge: "free tells you what Credence
  thinks."

  PAID — PERSONALIZATION (a board re-scored for YOUR league's saved settings, VOR against your
  roster shape, saved state) and DECISION SUPPORT (the draft optimizer, the weekly tools). "A
  membership helps you decide."

⚠️ A FULLY-FREE GENERIC BOARD IS SCRAPEABLE, AND THAT IS AN ACCEPTED COST, not an oversight. It is
the marketing wedge; the defence is cost-shaping (G100-D1's per-IP limiter + the CDN), never
redaction. Do not "fix" this by re-locking values.

═══════════════════════════════════════════════════════════════════════════════════════════════════
🗄️ WHAT THIS REPLACED — E9.56's LOCKED-MARKER REDACTION (RETIRED FROM THE LIVE PATH 2026-08-08)
═══════════════════════════════════════════════════════════════════════════════════════════════════

Until the freemium build, the rule was season-scoped: the current season (`LOCKED_SEASON`) was
locked everywhere, and a non-entitled caller received each row with its public identity, market ADP
and `locked: true` in place of every model value. That machinery — `lock_projection_rows`,
`lock_board_rows`, `lock_manifest`, the `_PUBLIC_*` allowlists and `_public_sort_key` — is KEPT
below and still unit-tested, but **no live route calls it any more**. Read it as the mechanism the
operator would flip back on if the open board ever has to be withdrawn, NOT as a description of what
users receive today.

⛔ Do not reason from it about current behaviour, and do not re-introduce a call to it without an
operator decision — `test_freemium_tier.py` pins the generic surfaces as free and will go red.

⭐ `resolve_entitlement` below is NOT retired and is MORE load-bearing than before, not less: the
generic routes are reachable without the API Gateway authorizer, so a Bearer token on them is
attacker-controlled. It is what decides whether a caller gets the PAID capabilities.

───────────────────────────────────────────────────────────────────────────────────────────────────
THREE THINGS THAT MADE THE RETIRED REDACTION SAFE (each one is a way a "redacted" payload still
leaks — kept with the code they describe)
───────────────────────────────────────────────────────────────────────────────────────────────────

1. ⭐ **ALLOWLIST, NEVER DENYLIST.** `_PUBLIC_*_FIELDS` names the fields a non-entitled caller MAY
   see; everything else is dropped. This is the load-bearing direction. Under a denylist, the next
   field the exporter adds (`export_draft_board_json.py` gains a column; a new NF-D story ships a new
   projection) would be PUBLIC BY DEFAULT and leak silently on the next publish — no code change, no
   test failure, no error. Under an allowlist a new field is locked by default and the worst outcome
   is a missing field for paying users, which is visible. Guarded by
   `test_e9_56_entitlement.py::test_an_unknown_new_field_is_locked_by_default`.

2. ⭐ **THE ROW ORDER IS ITSELF THE PAID DATA.** `projections.json` is sorted by our projection
   within position, and `board_*.json` by `ovrRank` — so a payload that nulls every number but keeps
   the array order hands over the ranking EXACTLY: the array index IS `ourRank`. Blanking the values
   while preserving the order would look redacted and leak the single most valuable output we have.
   So a locked payload is RE-SORTED onto a public key (market ADP, then name — see
   `_public_sort_key`). This is what the story means by "no derivable ordering that reconstructs it".

3. ⭐ **THE TOKEN ON A PUBLIC ROUTE IS ATTACKER-CONTROLLED.** On a route whose API Gateway
   authorization-type is `NONE` there is no upstream validation, so the usual unverified
   `_decode_jwt_payload` would accept a hand-written `{"cognito:groups":["subscriber"]}`. Groups are
   therefore read from the gateway's authorizer context when present (already validated) and
   otherwise ONLY from a signature-verified token (`services/jwt_verify.py`). See that module's
   docstring for the measured proof.

FAIL CLOSED throughout: anything unresolvable is anonymous, i.e. locked. Degrading a subscriber to
the free view is visible and recoverable; promoting an anonymous caller is the breach.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum

from fastapi import Request

logger = logging.getLogger(__name__)

# The first season with NO GRADED OUTCOMES yet.
#
# ⚠️ THIS IS NO LONGER A PAYWALL BOUNDARY (freemium build, 2026-08-08). The generic board is free
# for every season; what this literal still means is "the season the track record cannot cover",
# because a season that has not been played has nothing to grade a projection against. That is why
# `export_track_record_json` refuses to emit it and why `fantasy_public._LOCKED_SEASON` bounds the
# public receipts route — both are statements about DATA EXISTING, not about entitlement.
#
# ⚠️ MOVES WITH TWO OTHER LITERALS, and all three must change together at the season roll:
#   • `quant_sports_intel_models/football/nfl/fantasy/export_track_record_json.py::LOCKED_SEASON`
#     — the writer-side guarantee that the public track-record blob can never contain it.
#   • `app/backend/routers/fantasy_public.py::_LOCKED_SEASON` — the public router's redundant bound.
# Pinned in lockstep by `test_e9_56_entitlement.py::test_locked_season_agrees_across_all_three_owners`
# (the INC-38 "one logical thing, many owners" shape).
LOCKED_SEASON = int(os.getenv("FANTASY_LOCKED_SEASON", "2026"))


def is_locked_season(season: int) -> bool:
    """True iff `season` has no graded outcomes yet (so the track record cannot cover it).

    ⚠️ NOT an entitlement predicate any more — see the note on `LOCKED_SEASON`. Asking this question
    to decide whether someone may see a NUMBER is the pre-freemium reading and is wrong; ask
    `allows(...)` instead.
    """
    return int(season) >= LOCKED_SEASON


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ THE FREE / PAID SPLIT — one map, and it is the only place the boundary is stated
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Written as a CAPABILITY map rather than a list of route paths on purpose. A path list has to be
# re-derived every time a surface is added or renamed, and the characteristic failure of getting it
# wrong is SILENT in the dangerous direction: a new personalized endpoint that nobody remembered to
# add is free by default. Naming the capability forces the question "which half is this?" at the
# point a route is written, and `test_freemium_tier.py` asserts every fantasy route resolves to one.


class Capability(str, Enum):
    """What a caller is trying to do, in the terms the pricing page uses.

    `str` mixin so a capability serializes as its own name in a payload/log without a conversion
    step, and so a stale string comparison still works if one leaks into a response.
    """

    #: The generic board: rankings + projections for the shipped PRESETS, ranges, ADP, player pages,
    #: methodology. Identical bytes for every caller — which is exactly what makes it CDN-cacheable
    #: (G100-D1) and what `test_freemium_tier` proves.
    GENERIC_BOARD = "generic_board"

    #: The board re-scored for the caller's OWN saved league — their scoring, roster shape and size,
    #: their VOR baseline, their linked roster. Per-user by construction, so it can never be cached
    #: publicly and can never be free-by-accident.
    PERSONALIZATION = "personalization"

    #: Tools that turn the board into a CHOICE: the draft optimizer, and the weekly surfaces as they
    #: land. The paid half of "free tells you what Credence thinks; a membership helps you decide."
    DECISION_SUPPORT = "decision_support"


#: Everything an anonymous visitor gets. Deliberately a frozenset of ONE — the wedge is the generic
#: board and nothing else, and widening this is a pricing decision, not a refactor.
FREE_CAPABILITIES: frozenset[Capability] = frozenset({Capability.GENERIC_BOARD})

#: Stated explicitly rather than derived as "everything else", so a NEW capability is in neither set
#: until someone places it and `test_every_capability_is_placed_on_exactly_one_side` goes red. The
#: alternative ("paid = all - free") makes a forgotten capability silently PAID, which fails safe on
#: revenue but silently breaks a surface nobody tested — and the reverse spelling would make it
#: silently free, which is worse. Neither default is acceptable; being forced to choose is.
PAID_CAPABILITIES: frozenset[Capability] = frozenset(
    {Capability.PERSONALIZATION, Capability.DECISION_SUPPORT}
)


# ── G100-C1: ONE free personalized league ────────────────────────────────────────────────────────
#
# ⭐ RAISED 0 → 1 (G100-C1, 2026-08-08). The freemium build left this as a seam with a real default
# of ZERO and nothing reading it; this story is the flip, and it is deliberately the ONLY number
# that changes. Personalization is still `Capability.PERSONALIZATION` and still PAID — what a free
# account gets is a QUOTA of one, not the capability.
#
# ⚠️ WHY A QUOTA AND NOT A `free_personalization: bool`. A boolean cannot express "one league but
# not five", so this story would have had to REPLACE the predicate — and replacing an entitlement
# predicate is exactly when a surface quietly falls out of its gate. A count expresses the old state
# (0), today (1) and the paid tier (`dynamo.MAX_LEAGUES_PER_USER`) in one shape, so raising it moved
# one literal instead of re-typing a gate.
#
# ⭐ THE QUOTA IS THE GATE — read it through `personalized_league_quota` / `allows_personalization`,
# never by re-deriving the tier at a call site. Both `dependencies.require_personalized_league_access`
# and the create/serve caps below go through those two functions, so there is one place a reviewer
# has to read to know who gets what.
#
# ⛔ ZERO IS STILL A MEANINGFUL VALUE and the code must keep honouring it: setting the env var back
# to "0" is the operator's one-flip withdrawal of the free tier, and it has to refuse cleanly (403 at
# the dependency, not a half-working page). `test_g100_c1_free_league.py` exercises the 0 case
# explicitly, because a gate that has only ever been tested at its open setting is not a tested gate.
FREE_PERSONALIZED_LEAGUE_QUOTA = int(os.getenv("FREE_PERSONALIZED_LEAGUE_QUOTA", "1"))


# ── Which PRESET BOARDS the free capability covers ───────────────────────────────────────────────
#
# `Capability.GENERIC_BOARD` says a caller may read the generic board. This says WHICH ONE. The
# exporter publishes 7 scoring presets × 2 league sizes = 14 boards; the operator's call (2026-08-08)
# is that ONE of them is the free wedge and the other 13 are part of what a membership buys.
#
# ⭐ WHY FULL PPR AT 12 TEAMS SPECIFICALLY. The ADP column we show beside our number is an FFC
# 12-team PPR sample (`nfl/fantasy/benchmarks/adp_benchmark`). At any other preset our points and
# the market's ADP describe DIFFERENT leagues, so the one comparison the free board is built to
# support — ours vs the market's — is only honest here. Picking the free format is therefore a data
# fact as much as a pricing one, and moving it means moving the ADP sample too.
#
# ⚠️ A CONSTANT, DELIBERATELY NOT AN ENV VAR. `FREE_PERSONALIZED_LEAGUE_QUOTA` above is env-read
# because it is a seam a future story flips on purpose. This is the paywall itself: an env var that
# drifts (or is never set on one of the two owners) moves the paywall SILENTLY in either direction,
# which is this repo's documented-but-never-set class (`W7B_LAKEHOUSE_S3`) pointed at revenue.
# Changing it should be a reviewed diff.
FREE_BOARD_CONFIG = "full_ppr"
FREE_BOARD_SIZE = 12


def is_free_board(config: str, size: int) -> bool:
    """Whether the (config, size) board is the free one.

    ⚠️ BOTH must match. A free scoring format at a paid league SIZE is a paid board — the size
    changes the replacement level, so `full_ppr`/10 is a different set of numbers, not a cosmetic
    variant of the free one.
    """
    try:
        return str(config) == FREE_BOARD_CONFIG and int(size) == FREE_BOARD_SIZE
    except (TypeError, ValueError):
        # An unparseable size cannot be the free board. Fail closed: the caller gets the paid path,
        # which 403s an unentitled reader rather than serving them a board on a junk parameter.
        return False


def allows_board(config: str, size: int, ent: "Entitlement | None") -> bool:
    """Whether `ent` may read the (config, size) preset board.

    The free board is readable by anyone; every other preset needs full entitlement. Expressed here
    rather than in the router so the two questions a reviewer asks — "which board is free?" and "who
    may read a paid one?" — are answered next to each other and tested in one place.
    """
    if is_free_board(config, size):
        return True
    return bool(ent and ent.fantasy)


def allows(capability: Capability, ent: "Entitlement | None") -> bool:
    """Whether `ent` may exercise `capability`.

    FAIL CLOSED on anything unrecognised: an unknown capability is PAID, so a capability added
    without being placed in either set above is refused rather than served. That is the safe
    direction — a refused paid surface is visible and reversible; a leaked one is not.
    """
    if capability in FREE_CAPABILITIES:
        return True
    if capability not in PAID_CAPABILITIES:
        logger.warning("entitlement: unplaced capability %r treated as PAID", capability)
        return False
    return bool(ent and ent.fantasy)


def personalized_league_quota(ent: "Entitlement | None") -> int:
    """How many personalized leagues this caller may keep.

    Full entitlement ⇒ the storage cap; otherwise the free quota (1 since G100-C1). Read through
    this rather than branching on `ent.fantasy` at each call site — that is what made raising the
    free tier a one-number edit instead of a hunt through every place the tier was re-derived.

    ⚠️ AN ANONYMOUS CALLER GETS THE FREE QUOTA HERE TOO, and that is correct: this function answers
    "how many", not "may you". There is nowhere to STORE an anonymous caller's league (every record
    is keyed on a Cognito `sub`), so identity is required by the dependency —
    `require_personalized_league_access` resolves `get_user_id` FIRST and 401s before this is ever
    consulted. Keeping the two questions apart is what lets the quota be tested without a request.
    """
    if ent and ent.fantasy:
        from app.backend.services import dynamo

        return int(dynamo.MAX_LEAGUES_PER_USER)
    return FREE_PERSONALIZED_LEAGUE_QUOTA


def allows_personalization(ent: "Entitlement | None") -> bool:
    """Whether this caller may keep ANY personalized league at all.

    ⭐ NOT `allows(Capability.PERSONALIZATION, ent)`, and the difference is the whole story. That
    predicate answers "is personalization in this caller's tier?" — still FALSE for a free account,
    and it must stay false, because `Capability.PERSONALIZATION` is what the pricing page sells and
    what `PAID_CAPABILITIES` has to keep naming. This one answers the narrower operational question
    the routes actually need: "does this caller have a quota to spend?"

    So a free account is `allows(PERSONALIZATION) == False` and `allows_personalization() == True`
    with a quota of exactly 1 — the free tier is a GRANT AGAINST A PAID CAPABILITY, not a
    reclassification of it. Collapsing the two would have moved `PERSONALIZATION` into
    `FREE_CAPABILITIES`, which is a pricing change wearing a refactor's clothes and would have
    silently freed the draft optimizer's sibling surfaces too.
    """
    return personalized_league_quota(ent) > 0


def leagues_within_quota(records: list[dict], quota: int) -> list[dict]:
    """The leagues a caller may have SERVED as personalized boards, capped at `quota`.

    ⭐ WHY A SERVE-SIDE CAP EXISTS AT ALL, when creation is already refused at the quota. A
    subscriber who saves five leagues and then lapses keeps five stored records, and without this
    they would keep receiving five personalized boards forever — the paid tier, retained by having
    once paid for it. The create check cannot see that case, because no create happens.

    ⚠️ THIS IS NOT A DELETE, AND IT IS NOT APPLIED TO `/fantasy/leagues`. The user's own typed-in
    configs stay fully readable and deletable on the MANAGEMENT surface; what is capped is the
    PERSONALIZATION we compute from them. Capping the management list too would strand a lapsed user
    holding data they can see the count of but never reach — hostile, and it would make getting back
    under quota impossible.

    Ordering is OLDEST-FIRST by `created_at`, so which league survives the cap is deterministic and
    is the one the user has had LONGEST. ⚠️ Deliberately NOT `updated_at`, which `list_fantasy_leagues`
    already sorts on: that moves on every edit, so a lapsed user's kept league would change under
    them the moment they opened a different one — the cap has to be stable against browsing.

    A record with a missing/blank `created_at` sorts LAST (it cannot out-rank a known timestamp) with
    a stable `league_id` tiebreak, so one malformed field can never reorder the healthy records.
    """
    if quota <= 0:
        return []

    def key(record: dict):
        raw = str(record.get("created_at") or "")
        return (not raw, raw, str(record.get("league_id") or ""))

    return sorted(records, key=key)[:quota]


# ── Entitlement resolution ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entitlement:
    """What the caller is allowed to see, and — critically — HOW we know it."""

    user_id: str | None = None
    groups: tuple[str, ...] = ()
    fantasy: bool = False
    # "gateway"  — claims came from the API Gateway JWT authorizer context (validated upstream)
    # "verified" — no authorizer context; the Bearer token's SIGNATURE was verified locally
    # "anonymous" — no token, or a token that failed verification
    source: str = "anonymous"

    @property
    def is_anonymous(self) -> bool:
        return self.source == "anonymous"


def resolve_entitlement(request: Request) -> Entitlement:
    """Resolve the caller's entitlement on a route that may or may not be gateway-authorized.

    Never raises and never 403s — an endpoint using this serves a LOCKED payload to a
    non-entitled caller rather than an error, because the CTA has to render.
    """
    from app.backend.dependencies import _claims_from_event, _groups_from_request
    from app.backend.services import cognito, jwt_verify

    claims = _claims_from_event(request)
    if claims:
        # The gateway authorizer ran, so the token is already signature-validated; the existing
        # context+bearer union handles the bracketed-string claim mangling (see _groups_from_request).
        groups = tuple(sorted(_groups_from_request(request)))
        return Entitlement(
            user_id=claims.get("sub"),
            groups=groups,
            fantasy=cognito.has_fantasy_access(list(groups)),
            source="gateway",
        )

    # No authorizer context ⇒ this request did NOT pass a gateway JWT check (a public route, or
    # local uvicorn). The token is untrusted until its signature verifies.
    authorization = request.headers.get("Authorization")
    if not authorization:
        return Entitlement()

    verified = jwt_verify.verify_cognito_token(authorization)
    if not verified:
        # Malformed, expired, forged, or JWKS unreachable — all identical here: anonymous.
        return Entitlement()

    groups = tuple(sorted(jwt_verify.verified_groups(authorization)))
    return Entitlement(
        user_id=verified.get("sub"),
        groups=groups,
        fantasy=cognito.has_fantasy_access(list(groups)),
        source="verified",
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 🗄️ EVERYTHING BELOW IS THE RETIRED E9.56 REDACTION — NOT ON ANY LIVE ROUTE (see the module header)
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# Kept because it is the mechanism for withdrawing the open board, and it was expensive to get right
# (the ORDER-leak in point 2 above is the non-obvious half). Still unit-tested so it would work if
# re-wired. ⛔ It does not describe what any caller receives today.
#
# ── The public field allowlists ──────────────────────────────────────────────────────────────────
# Everything here is a fact about the PLAYER that anyone can look up (identity, team, physicals,
# draft slot) or a THIRD-PARTY market number we did not produce (`adp`). Nothing here is model
# output. Read the comment on `adp` before adding to these sets.

_PUBLIC_IDENTITY_FIELDS = frozenset(
    {
        "id",
        "name",
        "pos",
        "team",
        "bye",
        "rookie",
        "draftPick",  # NFL draft slot — a public fact about the player, not our projection
        "birthDate",
        "heightIn",
        "weightLb",
        "college",
        "yearsExp",
        "headshot",
    }
)

# Market average draft position. Third-party consensus (FFC / MyFantasyLeague), NOT our model — it is
# the benchmark our projection is measured AGAINST, and it is freely available elsewhere. Keeping it
# is what makes the free view coherent (a recognisable board to put the CTA on) and it supplies the
# public sort key that stops the array order from leaking our ranking.
#
# ⇒ if the operator decides ADP should be paid too, remove it from these sets — `_public_sort_key`
# already falls back to name-alphabetical, so nothing else has to change.
_PUBLIC_MARKET_FIELDS = frozenset({"adp"})

_PUBLIC_PROJECTION_FIELDS = _PUBLIC_IDENTITY_FIELDS | _PUBLIC_MARKET_FIELDS
_PUBLIC_BOARD_FIELDS = _PUBLIC_IDENTITY_FIELDS | _PUBLIC_MARKET_FIELDS

# Top-level keys of `projections.json` other than `players`: methodology labels, the ADP format the
# market column is quoted in, and the honest market-lean caveat. Descriptions of HOW the number was
# made — never a number. Kept so the free view can carry the same honest framing the paid one does.
_PUBLIC_PROJECTIONS_META_FIELDS = frozenset(
    {
        "season",
        "generated_at",
        "source",
        "adp_format",
        "adp_teams",
        "projection_source",
        "projection_label",
        "market_lean",
        "market_lean_note",
        "model_version",
        "base_season",
    }
)

# Manifest keys a non-entitled caller keeps: the page shell (positions, league configs, roster
# shapes, honest labels). No per-player value lives here.
#
# PAYLOAD MINIMIZATION (story step 4): `featureLegend` and `featureContributionsMeta` exist ONLY to
# label the entitled `contrib` attribution panel. With `contrib` locked there is nothing for them to
# describe, so they are dropped — ~nothing rendered, so nothing shipped.
_PUBLIC_MANIFEST_FIELDS = frozenset(
    {
        "season",
        "generated_at",
        "source",
        "positions",
        "projectionSource",
        "projectionLabel",
        "sizes",
        "configs",
        "projections",
    }
)

# Keys inside `manifest["projections"]` — methodology/labels and a row COUNT, no values.
_PUBLIC_MANIFEST_PROJECTION_FIELDS = frozenset(
    {
        "players",
        "adp_format",
        "adp_teams",
        "projection_source",
        "projection_label",
        "market_lean",
        "market_lean_note",
        "model_version",
        "base_season",
    }
)


def _public_sort_key(row: dict):
    """Order a LOCKED payload by a PUBLIC key so the array index cannot reconstruct our ranking.

    Market ADP ascending (undrafted last), then name. Falls back cleanly to name-alphabetical when
    `adp` is absent — including if `adp` is ever removed from the allowlist above.
    """
    adp = row.get("adp")
    try:
        adp_val = float(adp)
    except (TypeError, ValueError):
        adp_val = float("inf")  # undrafted / unknown sorts last, deterministically
    return (adp_val, str(row.get("name") or ""), str(row.get("id") or ""))


def _lock_row(row: dict, allowed: frozenset[str]) -> dict:
    """One row, reduced to its public fields, marked locked."""
    out = {k: v for k, v in row.items() if k in allowed}
    out["locked"] = True
    return out


def locked_field_names(rows: list[dict], allowed: frozenset[str]) -> list[str]:
    """The field names that WERE removed — what the UI puts a lock chip on.

    Computed from the real payload rather than hardcoded, so a new exporter field shows up as a
    locked point (and therefore as a CTA) automatically instead of silently disappearing.
    """
    seen: set[str] = set()
    for row in rows:
        seen.update(k for k in row if k not in allowed)
    return sorted(seen)


def lock_projection_rows(rows: list[dict]) -> list[dict]:
    """Redact + re-order the `players` array of a gated-season projections payload."""
    return sorted(
        (_lock_row(r, _PUBLIC_PROJECTION_FIELDS) for r in rows if isinstance(r, dict)),
        key=_public_sort_key,
    )


def lock_board_rows(rows: list[dict]) -> list[dict]:
    """Redact + re-order a gated-season draft board.

    A board is ENTIRELY model output — `pts`, `vor`, `posRank`, `ovrRank` and its ordering are the
    product. So the locked form is the player universe with a lock on every number.
    """
    return sorted(
        (_lock_row(r, _PUBLIC_BOARD_FIELDS) for r in rows if isinstance(r, dict)),
        key=_public_sort_key,
    )


def lock_manifest(manifest: dict) -> dict:
    """Redact a gated-season manifest down to the page shell."""
    out = {k: v for k, v in manifest.items() if k in _PUBLIC_MANIFEST_FIELDS}
    proj = out.get("projections")
    if isinstance(proj, dict):
        out["projections"] = {
            k: v for k, v in proj.items() if k in _PUBLIC_MANIFEST_PROJECTION_FIELDS
        }
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# ✅ LIVE AGAIN FROM HERE — the response envelopes
# ══════════════════════════════════════════════════════════════════════════════════════════════════
# `entitlement_envelope` and the `open_*_payload` transforms ARE on the live path: every generic
# response carries them. The `lock_*_payload` transforms below them are part of the retired block
# above and are called by nothing.
#
# ⚠️ ADDITIVE ONLY (NF-C0 / E9.41). These keys are ADDED to the existing payload shapes; no key the
# deployed client already reads is renamed or removed, and the container type is preserved —
# projections/manifest stay dicts, the board stays a LIST.
#
# ⭐ WHY THE ENVELOPE SURVIVES THE FREEMIUM FLIP RATHER THAN BEING DELETED. The deployed frontend
# reads `locked`/`entitled` on every board response and branches on them. Dropping the keys would be
# the NF-C0 break in its exact original form — a 200 whose missing key makes the client render
# nothing — and the API Lambda ships only via a manual `deploy.sh`, so the two halves cross over in
# an order nobody controls. Every caller now gets `locked: false, entitled: true`, which the already-
# deployed client renders as the full board with no change at all.


@dataclass
class _Envelope:
    locked: bool
    fields: list[str] = field(default_factory=list)


def entitlement_envelope(locked: bool, locked_fields: list[str] | None = None) -> dict:
    """The additive keys every gated-season response carries, entitled or not.

    `entitled` is stated explicitly (rather than left implied by the absence of `locked`) so the
    frontend never has to infer entitlement from a missing key — the E9.41 dropped-field class.
    """
    out: dict = {
        "locked": locked,
        "entitled": not locked,
        "lockedSeason": LOCKED_SEASON,
    }
    if locked:
        out["lockedFields"] = locked_fields or []
        out["upgrade"] = {
            "reason": "subscription_required",
            "message": f"Subscribe to unlock the {LOCKED_SEASON} projections.",
            # 🚨 E9.56c — WAS "/pricing", A ROUTE THAT HAS NEVER EXISTED. This value is rendered
            # directly as the primary CTA's href on every locked surface, so the whole conversion
            # path off the free view was a 404 (verified live). The frontend now maps this through
            # an allowlist of routes it can actually reach (`resolveUpgradeHref` in
            # components/fantasy/shared.tsx) rather than trusting it verbatim — a server-controlled
            # link target is a server-controlled outage otherwise.
            # ⚠️ The Lambda ships only via a manual `deploy.sh`, so until that runs the deployed API
            # keeps sending "/pricing"; the frontend allowlist is what makes that window harmless.
            "ctaHref": "/subscribe",
        }
    return out


# ── The payload transforms ───────────────────────────────────────────────────────────────────────
# The whole public/paid policy lives here rather than in the routers, so there is ONE place to read,
# ONE place to test, and no chance of two endpoints answering to different rules.
#
# ✅ LIVE: `open_*_payload` — what every caller gets on the generic surfaces.
# 🗄️ RETIRED: `lock_*_payload` — part of the withdrawn E9.56 redaction; called by nothing.


def open_projections_payload(data: dict) -> dict:
    """Entitled: the payload UNCHANGED, plus the additive entitlement keys."""
    return {**data, **entitlement_envelope(locked=False)}


def lock_projections_payload(data: dict) -> dict:
    """Non-entitled, gated season: identity + market only, re-ordered, every value locked."""
    players = [r for r in (data.get("players") or []) if isinstance(r, dict)]
    out = {k: v for k, v in data.items() if k in _PUBLIC_PROJECTIONS_META_FIELDS}
    out["players"] = lock_projection_rows(players)
    out.update(
        entitlement_envelope(
            locked=True, locked_fields=locked_field_names(players, _PUBLIC_PROJECTION_FIELDS)
        )
    )
    return out


def open_manifest_payload(data: dict) -> dict:
    """The manifest UNCHANGED, plus the entitlement envelope and the free-board markings.

    ⭐ THE MARKINGS ARE THE SAME FOR EVERY CALLER, and that is the point. The client has to know
    which preset is free in order to draw the boundary — to default an anonymous visitor onto the
    free board, and to show a lock rather than a dead control on the other 13. Deriving that
    client-side from a hardcoded string would put the paywall in two places that drift; sending a
    DIFFERENT manifest to an entitled caller would make this route caller-dependent and cost the
    CDN cache (see the invariant note in `routers/fantasy.py`). Marking every preset identically for
    everybody does neither: the bytes are constant, and the boundary is stated once, here.

    ADDITIVE ONLY (NF-C0). `free` is a new key on each config and `freeBoard` is a new top-level
    key; nothing existing is renamed or removed, so the deployed client — which knows neither —
    keeps rendering exactly what it renders today.
    """
    configs = [
        {**c, "free": c.get("name") == FREE_BOARD_CONFIG} if isinstance(c, dict) else c
        for c in (data.get("configs") or [])
    ]
    out = {**data, **entitlement_envelope(locked=False)}
    if data.get("configs") is not None:
        out["configs"] = configs
    out["freeBoard"] = {"config": FREE_BOARD_CONFIG, "size": FREE_BOARD_SIZE}
    return out


def lock_manifest_payload(data: dict) -> dict:
    """Non-entitled: the page shell only — enough to render the board's frame and the CTA."""
    out = lock_manifest(data)
    out.update(entitlement_envelope(locked=True))
    return out


def lock_board_payload(rows: list) -> list:
    """Non-entitled, gated season: a LIST in, a LIST out.

    ⚠️ The container type is deliberately preserved. `/fantasy/nfl/board` has always returned a bare
    JSON array and the deployed client indexes it directly; wrapping it in an envelope object would
    be exactly the NF-C0 response-shape break (a 200 with a blank screen and no error anywhere). So
    the lock state travels on each ROW (`locked: true`), and the page-level CTA copy comes from the
    manifest, which every board view already loads.
    """
    return lock_board_rows([r for r in rows if isinstance(r, dict)])
