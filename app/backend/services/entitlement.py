"""E9.56 — server-side entitlement resolution + the LOCKED-MARKER redaction for gated seasons.

THE RULE THIS ENFORCES (operator, 2026-08-01). FREE (unauthenticated or non-subscriber) sees the
PAST-SEASON model output — that is the NF3.2 receipts surface, public by design. The CURRENT season
(`LOCKED_SEASON`, 2026) projection is LOCKED **everywhere**: rankings, player pages, board, tools.
And a locked point must render a "subscribe to unlock" CTA rather than vanishing, so the payload has
to say a value EXISTS here without ever carrying it.

⇒ the split is NOT "omit 2026". It is: the row survives with its PUBLICLY-KNOWN identity, every
model-derived number is REMOVED, and a `locked: true` marker takes its place.

───────────────────────────────────────────────────────────────────────────────────────────────────
THREE THINGS THAT MAKE THIS ACTUALLY SAFE (each one is a way a "redacted" payload still leaks)
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

from fastapi import Request

logger = logging.getLogger(__name__)

# The first season that is PAID. Everything strictly before it is free.
#
# ⚠️ MOVES WITH TWO OTHER LITERALS, and all three must change together at the season roll:
#   • `quant_sports_intel_models/football/nfl/fantasy/export_track_record_json.py::LOCKED_SEASON`
#     — the writer-side guarantee that the public track-record blob can never contain it.
#   • `app/backend/routers/fantasy_public.py::_LOCKED_SEASON` — the public router's redundant bound.
# Pinned in lockstep by `test_e9_56_entitlement.py::test_locked_season_agrees_across_all_three_owners`
# (the INC-38 "one logical thing, many owners" shape).
LOCKED_SEASON = int(os.getenv("FANTASY_LOCKED_SEASON", "2026"))


def is_locked_season(season: int) -> bool:
    """True iff `season` is paid content. Free is strictly-past only."""
    return int(season) >= LOCKED_SEASON


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


# ── Response envelopes ───────────────────────────────────────────────────────────────────────────
# ⚠️ ADDITIVE ONLY (NF-C0 / E9.41). These keys are ADDED to the existing payload shapes; no key the
# deployed client already reads is renamed or removed, and the container type is preserved —
# projections/manifest stay dicts, the board stays a LIST. A client that has not shipped the
# locked-marker rendering yet keeps working against an entitled response byte-for-byte.


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


# ── The three payload transforms the routers call ────────────────────────────────────────────────
# The whole public/paid policy lives here rather than in the routers, so there is ONE place to read,
# ONE place to test, and no chance of two endpoints redacting to different rules.


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
    return {**data, **entitlement_envelope(locked=False)}


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
