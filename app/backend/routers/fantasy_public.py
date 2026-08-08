"""fantasy_public.py — NF3.2: the fantasy football PAST-SEASON TRACK RECORD (receipts), served with
NO entitlement gate.

Every other route under `/fantasy/*` (`fantasy.py`) requires `require_fantasy_access` — that is
deliberate for the paid product (the current-season projections/boards), but this story's whole point
is a GTM proof asset a logged-out visitor can browse: our past-season projection vs that season's
preseason ADP vs the realized outcome, 2019–2025. So this lives on its OWN router with no
`Depends(require_fantasy_access)` anywhere, mirroring `fantasy_import.py`'s `public_router` (a single
exempted route kept on a separate router object, never a flag inside the gated one).

🔒 ENTITLEMENT / DATA-LAYER GUARANTEE (the TRACK-RECORD router only — see the carve-out below): the
public/paid split is enforced by WHAT DATA EXISTS to read, not by a runtime check here.
`export_track_record_json.py` (the only writer of the `fantasy/nfl/track_record/*` key space
`router` reads) structurally refuses to ever emit the current/locked season (see `LOCKED_SEASON`
there) — so there is no 2026 projection value for that router to accidentally serve even if a caller
asked for it. Its own `season` bound below is a second, redundant line of defense
(belt-and-suspenders on top of the writer-side guarantee), not the only one.

⚠️⚠️ E9.46 ADDS ONE DELIBERATE EXCEPTION TO THAT GUARANTEE, AND IT IS WHY THIS PARAGRAPH EXISTS.
`featured_router` below reads the LOCKED season's `projections.json` and serves REAL model values —
so the sentence above is no longer true of this module as a whole, and a future reader who trusted it
would be wrong. The exception is bounded three ways, and all three are load-bearing rather than
stylistic:

  1. **ONE PLAYER.** Exactly the single selected player is ever serialized. Not a list, not a page,
     not a "top N" — the selection collapses the 858-row artifact to one record before anything is
     returned, so there is no offset/limit/filter a caller can walk to enumerate the board.
  2. **A FIXED FIELD SET.** Only the fields the homepage card renders (see `_featured_payload`). The
     served artifact carries a full per-player stat line — attempts, yards, touchdowns, the K and DST
     distributions — and none of it leaves this module.
  3. **NO CALLER INPUT.** The route takes no parameters at all. A caller cannot ask for a different
     player, position, season or format, so the exception cannot be steered.

It exists because the operator decided (2026-08-08) that the homepage needs one concrete, real
fantasy demonstration, and every field that makes such a card meaningful — the projection, its 80%
range, our rank, the drivers — is exactly what `entitlement.lock_projections_payload` strips. That
is a product/pricing decision, not something to widen casually: ⛔ do not add a `player_id`,
`position` or `limit` parameter here. If a second public player is ever wanted, that is a new
decision and it should be a new, equally-bounded route.

Reuses `fantasy.py`'s `_load_json` (S3 vs local-dir read, same key-prefix convention) rather than a
second implementation of the same read path — that helper is already generic over the key and carries
no entitlement logic itself (the gate lives in the router's `dependencies=`, which this router simply
never sets).
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Path

from app.backend.routers.fantasy import _load_json

logger = logging.getLogger(__name__)

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


# ══════════════════════════════════════════════════════════════════════════════════════════════
# E9.46 — the ONE public current-season player. Read the ⚠️ carve-out in the module docstring
# before touching anything below.
# ══════════════════════════════════════════════════════════════════════════════════════════════

featured_router = APIRouter(prefix="/fantasy/nfl", tags=["fantasy-public"])

#: Positions a homepage card should ever feature. K and DST carry deliberately BASE projections
#: (NF1.6) that must not be presented as a confident rank, so they are out.
_FEATURED_POSITIONS = ("QB", "RB", "WR", "TE")

#: ADP ceiling for the universe — roughly ten rounds of a 12-team draft. A player nobody has heard
#: of is a worse demonstration than a smaller disagreement about a player they have.
_FEATURED_MAX_ADP = 120.0

#: How many drivers the card shows. The artifact carries six; three is what fits without the card
#: becoming a table, and they are already ordered by absolute contribution.
_FEATURED_DRIVER_COUNT = 3

#: In-process memo. The artifact is rewritten at most once per publish, so a few minutes of
#: staleness on a marketing card is harmless — and this is the homepage, so without it every
#: anonymous visitor would pull the full 1.3 MB projections blob out of S3.
#: ⚠️ Lazy by construction (populated on first request, never at import): a module-scope fetch is a
#: live S3 GET paid by every test that imports this module and by every Lambda cold start.
_FEATURED_TTL_SECONDS = 900
_featured_memo: tuple[float, dict] | None = None


def _within_position_ranks(players: list[dict], key, reverse: bool) -> dict[str, int]:
    """Rank players inside their own position. Returns {player_id: rank}, 1-based.

    ⚠️ Ranked WITHIN POSITION, not overall, because that is the comparison a drafter actually makes
    and the only one where our number and ADP are measuring the same thing. An overall rank would
    silently compare a TE against a stack of running backs."""
    ranks: dict[str, int] = {}
    by_pos: dict[str, list[dict]] = {}
    for p in players:
        by_pos.setdefault(p.get("pos") or "", []).append(p)
    for pos_players in by_pos.values():
        ordered = sorted(pos_players, key=key, reverse=reverse)
        for i, p in enumerate(ordered, start=1):
            ranks[p["id"]] = i
    return ranks


def _select_featured(players: list[dict]) -> tuple[dict, int, int, int] | None:
    """Pick the player to feature. Returns (player, our_rank, adp_rank, universe_size) or None.

    ⭐ THE RULE IS DETERMINISTIC AND IS THE HONEST PART OF THIS ENDPOINT. It is computed from the
    served artifact on every request rather than curated, so nobody is choosing a flattering
    example and the card follows the model when it is re-published:

        of draftable skill-position players who carry driver data, take the LARGEST
        within-position rank disagreement against market ADP.

    Each clause earns its place:
      · `contrib.drivers` REQUIRED — the card has to explain the difference, and a projection we
        cannot explain is the wrong thing to lead with. ⚠️ It also excludes rookies as a side
        effect: they are projected off the draft-slot curve, which produces no driver
        decomposition (`contrib` is null). Measured on the live 2026 artifact: 111 of 858 players
        qualify.
      · ⛔ NOT filtered to `mktLean == "independent"`, which was the first design and is EMPTY in
        practice — `independent` is precisely the thin-data rookie case that has no drivers, so
        the two requirements have no overlap at all (measured: 0 of 111). Every eligible player's
        ranking therefore blends market consensus to some degree, which is why `lean`/`leanNote`
        ship WITH the card rather than as an optional extra: the rank gap is a real disagreement
        but it is not an independent one, and the card has to say so.
      · Direction is NOT constrained. The winner may be a player we are higher OR lower on than
        the market; forcing the flattering direction would be exactly the curation this rule
        exists to avoid, and the card renders both.

    Ties break on lower ADP then player id, so the result is stable across identical inputs.
    """
    # ⚠️⚠️ TWO DIFFERENT POPULATIONS, AND CONFLATING THEM SHIPS A WRONG NUMBER TO THE HOMEPAGE.
    #
    #   `ranked`  — every player at the position carrying BOTH our projection and an ADP. This is
    #               what the RANKS ARE COMPUTED OVER, because "WR15" has to mean fifteenth on the
    #               board. Matched on both fields for the same reason the track-record export
    #               matches them: ranking our side over a different population than the market's
    #               would make the two numbers uncomparable and the gap meaningless.
    #   `universe` — the subset ELIGIBLE TO BE FEATURED (draftable, explainable). Selection only.
    #
    # The first cut ranked inside `universe`, so the card would have rendered "our WR15" meaning
    # fifteenth of the 111 filtered players rather than fifteenth on the board — a plausible-looking
    # number that is simply not the one the label claims. It also changed WHICH player won.
    ranked = [
        p
        for p in players
        if p.get("pos") in _FEATURED_POSITIONS
        and isinstance(p.get("adp"), (int, float))
        and isinstance(p.get("fpPpr"), (int, float))
        and p.get("id")
    ]
    if not ranked:
        return None

    our_ranks = _within_position_ranks(ranked, key=lambda p: p["fpPpr"], reverse=True)
    adp_ranks = _within_position_ranks(ranked, key=lambda p: p["adp"], reverse=False)

    universe = [
        p
        for p in ranked
        if p["adp"] <= _FEATURED_MAX_ADP and (p.get("contrib") or {}).get("drivers")
    ]
    if not universe:
        return None

    def sort_key(p: dict):
        gap = abs(adp_ranks[p["id"]] - our_ranks[p["id"]])
        return (-gap, p["adp"], p["id"])

    winner = sorted(universe, key=sort_key)[0]
    return winner, our_ranks[winner["id"]], adp_ranks[winner["id"]], len(universe)


def _featured_payload() -> dict | None:
    """Build the bounded public record for the selected player, or None when unavailable.

    ⛔ THE FIELD LIST HERE IS THE ENTITLEMENT BOUNDARY. It is an explicit allow-list, never a
    `{**player}` spread minus a few keys: the served artifact carries the whole stat line plus the
    K/DST distributions, and a spread would publish all of it the moment the exporter adds a field.
    """
    projections = _load_json("2026/projections.json")
    if not isinstance(projections, dict):
        return None
    players = projections.get("players")
    if not isinstance(players, list) or not players:
        return None

    picked = _select_featured(players)
    if picked is None:
        return None
    p, our_rank, adp_rank, universe = picked

    # Driver labels come from the manifest's own legend so the plain-English wording has ONE home
    # (it is already rendered on the entitled player page). A missing legend degrades to the raw
    # feature key rather than dropping the driver — a card with an unlabelled row is still honest;
    # a card that silently omits the biggest negative driver is not.
    manifest = _load_json("2026/manifest.json")
    legend = (manifest or {}).get("featureLegend") or {} if isinstance(manifest, dict) else {}
    drivers = []
    for d in ((p.get("contrib") or {}).get("drivers") or [])[:_FEATURED_DRIVER_COUNT]:
        feature = d.get("feature")
        drivers.append(
            {
                "feature": feature,
                "label": (legend.get(feature) or {}).get("label") or feature,
                "pts": d.get("pts"),
            }
        )

    return {
        "season": projections.get("season"),
        "generatedAt": projections.get("generated_at"),
        "player": {
            "id": p.get("id"),
            "name": p.get("name"),
            "pos": p.get("pos"),
            "team": p.get("team"),
            "bye": p.get("bye"),
            "headshot": p.get("headshot"),
        },
        # ⭐ THE THREE FORMAT SCORINGS ARE THE PERSONALISATION PROOF, and they cost nothing extra:
        # they are the SAME player's season under standard, half-PPR and full-PPR rules. "Built for
        # your league, not a generic one" is a claim until a visitor sees one player's number move
        # 65.9 → 83.2 → 100.6 by format, at which point it is an observation.
        "projection": {
            "ptsStd": p.get("fpStd"),
            "ptsHalf": p.get("fpHalf"),
            "ptsPpr": p.get("fpPpr"),
            "p10": p.get("fpP10"),
            "p90": p.get("fpP90"),
            "games": p.get("g"),
            "conf": p.get("conf"),
        },
        "market": {
            "adp": p.get("adp"),
            "adpFormat": projections.get("adp_format"),
            "adpTeams": projections.get("adp_teams"),
            "adpRank": adp_rank,
            "ourRank": our_rank,
            # Positive ⇒ we rank him HIGHER than the market drafts him.
            "rankGap": adp_rank - our_rank,
        },
        "drivers": drivers,
        "lean": p.get("mktLean"),
        "leanNote": projections.get("market_lean_note"),
        "universeSize": universe,
    }


@featured_router.get("/featured-player")
def featured_player():
    """ONE current-season player, with real model values, for the public homepage card.

    Takes NO parameters by design (module docstring, bound 3). 404 when the artifact is missing or
    no player qualifies — the homepage hides the card on a 404 rather than rendering an empty one.
    """
    global _featured_memo
    now = time.monotonic()
    if _featured_memo is not None and now - _featured_memo[0] < _FEATURED_TTL_SECONDS:
        return _featured_memo[1]

    payload = _featured_payload()
    if payload is None:
        # ⚠️ Deliberately NOT memoized. Caching a miss would hold the card down for the full TTL
        # after a publish that fixed it, and a 404 here is cheap (the homepage degrades silently).
        raise HTTPException(status_code=404, detail="No featured player available")

    _featured_memo = (now, payload)
    return payload
