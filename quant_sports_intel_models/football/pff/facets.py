"""facets.py — the PFF facet catalog, the per-game crawler, and the facet→signal map (NF-W9-0).

PFF's per-game data is exposed as "facets": one JSON per (game, unit, view).

    GET /api/v1/games?league=ncaa|nfl&season=YYYY&week=N     → the game list
    GET /api/v1/facet/<unit>/<view>?game_id=…                → one facet for one game

⭐ THE CATALOG IS DISCOVERED, NOT DECLARED. `discover_facets` probes each candidate against a
REAL game and records which ones actually return rows. A hardcoded list would be a claim about
PFF's API written by us, and the repo has been bitten repeatedly by a declaration outranking its
production (NF-C0e "wired ≠ invoked", NF-K1's PROJECTABLE positions that the exporter declared
and never produced). What lands in the report is therefore what ANSWERED, with the ones that
404'd listed beside it — an absent facet is a recorded fact, not a silent omission.

⭐ THE FACET→SIGNAL MAP IS THE POINT OF THE SPIKE. NF-W9-1/2/3 do not need "PFF data", they need
specific quantities PFF has and nflverse/CFBD do not (see `SIGNAL_MAP`). Routes run and aDOT are
the two that genuinely change what NF-W9-1 can model: a zero-atom opportunity model is currently
forced to treat "did not play", "played but ran no routes" and "ran routes, saw no target" as one
undifferentiated zero, and ROUTES is what splits them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable

from .client import PFFClient, PFFClientError, PFFNotFoundError
from .guards import assert_endpoint_allowed, strip_model_output_columns

log = logging.getLogger("pff.facets")

GAMES_PATH = "/api/v1/games"
FACET_PATH_TMPL = "/api/v1/facet/{unit}/{view}"

# Units and views to PROBE. `discover_facets` decides which are real — and it earned its keep:
# the symmetric guess included `receiving/direction` (404) and omitted `receiving/depth` and
# `receiving/concept` (both real). MEASURED LIVE 2026-08-18 against NFL 2024 wk1 game 25907:
#   ✅ rushing/{summary,direction}, receiving/{summary,depth,concept},
#      passing/{summary,depth,concept}, defense/summary
#   ❌ blocking/*, coverage/*, special_teams/*, receiving/direction, passing/direction (404)
CANDIDATE_UNITS: tuple[str, ...] = (
    "rushing", "receiving", "passing", "blocking", "coverage", "defense", "special_teams",
)
CANDIDATE_VIEWS: tuple[str, ...] = ("summary", "direction", "depth", "concept")

# PFF names the row list after the facet (`rushing_summary`, `rushing_direction_stats`), and
# ships a SECOND list called `restricted` alongside it. `restricted` must never be mistaken for
# the data — see `_rows`.
RESTRICTED_KEY = "restricted"


@dataclass(frozen=True)
class Facet:
    unit: str
    view: str

    @property
    def path(self) -> str:
        return FACET_PATH_TMPL.format(unit=self.unit, view=self.view)

    @property
    def key(self) -> str:
        return f"{self.unit}/{self.view}"


# The facets the probe pulls by default: the OPPORTUNITY carriers NF-W9-1/2/3 need. Deliberately
# a short list — this is a feasibility probe, not an ingest.
PROBE_FACETS: tuple[Facet, ...] = (
    Facet("rushing", "summary"),
    Facet("rushing", "direction"),
    Facet("receiving", "summary"),
    Facet("receiving", "depth"),      # `receiving/direction` does NOT exist (measured 404)
)

# ── facet → downstream signal ──────────────────────────────────────────────────────────────
# WHY each downstream story needs PFF at all, stated as the quantity we cannot already get.
SIGNAL_MAP: dict[str, dict[str, Any]] = {
    "NF-W9-1 zero-atom opportunity": {
        "facets": ["receiving/summary", "rushing/summary"],
        "fields_sought": ["routes", "snaps", "targets", "adot", "slot_rate", "wide_rate"],
        "why": (
            "The blocking constraint measured across NF-W6d/W7c-f is that our per-stat zero atom "
            "is MARGINAL — we cannot distinguish 'inactive', 'active but ran no routes' and 'ran "
            "routes, no target'. nflverse gives targets and snap COUNTS but not ROUTES RUN, so "
            "those three states collapse into one zero. Routes is the field that splits them, and "
            "it is the single most decision-relevant thing in this probe."
        ),
    },
    "NF-W9-2 RB volume": {
        "facets": ["rushing/summary", "rushing/direction", "receiving/summary"],
        "fields_sought": [
            "attempts", "yards_after_contact", "elusive_events", "gap_direction", "designed_runs",
        ],
        "why": (
            "RB volume modelling wants the DIRECTIONAL/gap split and contact-adjusted yardage that "
            "nflverse pbp only partially reconstructs. `rushing/direction` is the facet with no "
            "nflverse equivalent."
        ),
    },
    "NF-W9-3 college charting": {
        "facets": ["receiving/summary", "receiving/direction", "rushing/summary"],
        "fields_sought": ["routes", "adot", "slot_rate", "targets", "snaps"],
        "why": (
            "CFBD has NO charting layer at all — no routes, no aDOT, no alignment. If PFF's NCAA "
            "facets carry them, this is net-new substrate for the college→NFL feeder; if they do "
            "not, NF-W9-3 has no data and should not be carded."
        ),
    },
}


def fetch_facet_export(
    client: PFFClient,
    facet: Facet,
    *,
    league: str,
    season: int,
    weeks: Iterable[int],
    division: str | None = None,
) -> list[dict]:
    """One facet's FULL field set for a whole season, in ONE request.

    ⭐ THIS IS THE PATH THAT ACTUALLY DELIVERS THE STORY. `&export=true` on the season-aggregate
    query returns the complete CSV — every field the plain JSON reports as `restricted`. And
    because `week=` takes a LIST, a whole season is a single call: ~1 request per (league,
    season, facet) instead of the 2,176 per-game JSON calls first sized, and instead of the
    manual CSV downloads this story set out to replace.

    Pass a single week to get weekly grain (the granularity NF-W9-1 wants for a zero-atom
    opportunity model) — still one request per week, not per game.

    `division` is NCAA-only (`fbs`); the NFL query takes no division.
    """
    params: dict[str, Any] = {
        "league": league,
        "season": season,
        "week": ",".join(str(w) for w in weeks),
    }
    if division:
        params["division"] = division
    rows = client.get_export(facet.path, params)
    stripped = [_strip_row(r) for r in rows]
    log.info(
        "PFF export %s league=%s season=%s → %d row(s), %d col(s) after the raw-stats guard",
        facet.key, league, season, len(stripped), len(stripped[0]) if stripped else 0,
    )
    return stripped


def list_games(client: PFFClient, *, league: str, season: int, week: int) -> list[dict]:
    """The game list for one (league, season, week). Raises rather than returning `[]` blindly."""
    payload = client.get(GAMES_PATH, {"league": league, "season": season, "week": week})
    games = _rows(payload, prefer=("games", "data"))
    log.info("PFF games league=%s season=%s week=%s → %d game(s)", league, season, week, len(games))
    return games


def fetch_facet(client: PFFClient, facet: Facet, game_id: Any) -> list[dict]:
    """One facet for one game, with PFF's model-output columns STRIPPED and the strip recorded."""
    rows, _ = fetch_facet_with_entitlement(client, facet, game_id)
    return rows


def fetch_facet_with_entitlement(
    client: PFFClient, facet: Facet, game_id: Any
) -> tuple[list[dict], list[str]]:
    """`(rows, restricted_fields)` for one facet.

    ⭐ `restricted` NAMES THE FIELDS THIS RESPONSE OMITS — surfacing it is what stops the probe
    reporting a cheerful "12 rows pulled" for a payload carrying nothing we do not already have
    from nflverse (present, but empty of the thing we came for).

    ⚠️⚠️ IT IS **NOT** AN ACCOUNT ENTITLEMENT, AND READING IT AS ONE COST THIS STORY ITS HEADLINE.
    NF-W9-0 first concluded "the subscription tier withholds every field NF-W9-1/2/3 need" and
    recommended not carding them. That was WRONG: a CSV exported from the PFF UI on the SAME
    account contains all 28 of the 28 fields this endpoint called `restricted`, grades included.
    The `/api/v1/facet/*` JSON API simply serves a REDUCED field set — measured identically on
    NFL per-game, NFL season-aggregate and NCAA season-aggregate — while the CSV export serves
    the full one.

    ⭐ THE TELL, FOR NEXT TIME: the list contained `grades_offense`. PFF's entire consumer product
    IS the grades, so "the tier withholds them" was never plausible — the evidence to falsify the
    reading was inside the very list being read. A field named `restricted` is a NAME, not a
    measurement; before building a verdict on what a vendor's field MEANS, find a second,
    independent path to the same data and compare (here: the CSV). This is the repo's
    documented-vs-actually-served class, one level in — the documentation was ours.
    """
    assert_endpoint_allowed(facet.path)
    payload = client.get(facet.path, {"game_id": game_id})
    restricted = []
    if isinstance(payload, dict):
        r = payload.get(RESTRICTED_KEY)
        if isinstance(r, list):
            restricted = [str(x) for x in r]
    rows = _rows(payload, prefer=(f"{facet.unit}_{facet.view}", "players", "data", "rows"))
    return [_strip_row(r) for r in rows], restricted


_STRIPPED_SEEN: set[str] = set()


def _strip_row(row: dict) -> dict:
    kept, dropped = strip_model_output_columns(list(row.keys()))
    for d in dropped:
        if d not in _STRIPPED_SEEN:
            _STRIPPED_SEEN.add(d)
            log.info("RAW-STATS-ONLY guard dropped PFF model-output column %r", d)
    return {k: row[k] for k in kept}


def stripped_columns() -> list[str]:
    """Every model-output column dropped so far — recorded in the probe artifact so a strip is
    never confused with PFF simply not having sent grades."""
    return sorted(_STRIPPED_SEEN)


def discover_facets(
    client: PFFClient,
    game_id: Any,
    *,
    units: Iterable[str] = CANDIDATE_UNITS,
    views: Iterable[str] = CANDIDATE_VIEWS,
) -> dict[str, dict[str, Any]]:
    """Probe every (unit, view) against ONE real game; report what answered.

    A facet that errors is recorded with its error rather than dropped, so the catalog
    distinguishes "PFF has no such facet" from "we failed to fetch it" — two different findings
    that a bare presence list would render identically.
    """
    out: dict[str, dict[str, Any]] = {}
    for unit in units:
        for view in views:
            f = Facet(unit, view)
            try:
                rows = fetch_facet(client, f, game_id)
                cols = sorted({k for r in rows[:50] for k in r})
                out[f.key] = {"available": True, "n_rows": len(rows), "columns": cols}
                log.info("facet %s → %d rows, %d cols", f.key, len(rows), len(cols))
            except PFFNotFoundError:
                # PFF does not publish this facet — a finding, not a failure.
                out[f.key] = {"available": False, "reason": "not_published_404"}
            except PFFClientError as exc:
                # We failed to FETCH it — a different fact, and one worth investigating.
                out[f.key] = {"available": False, "reason": "fetch_failed",
                              "error": str(exc)[:300]}
    return out


def _rows(payload: Any, *, prefer: tuple[str, ...] = ()) -> list[dict]:
    """Pull the row list out of a PFF payload without guessing a single fixed shape.

    Tolerant BY DESIGN: this is a first-contact probe against an API whose exact envelope we
    have not seen. It never silently returns `[]` for a non-empty payload — an unrecognised
    shape raises, because a quietly-empty parse is the failure mode that costs days.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in (*prefer, "results", "items", "games"):
            v = payload.get(k)
            if isinstance(v, list):
                return [r for r in v if isinstance(r, dict)]
        # ⛔ `restricted` is a list of FIELD NAMES, not rows. Falling through to "the single
        # list in the envelope" would hand the caller PFF's entitlement list as if it were data
        # — strings, not dicts, so it would silently normalise to an all-NA frame.
        lists = [
            v for k, v in payload.items()
            if isinstance(v, list) and k != RESTRICTED_KEY
        ]
        if len(lists) == 1:
            return [r for r in lists[0] if isinstance(r, dict)]
        if not payload:
            return []
        raise PFFClientError(
            f"Unrecognised PFF payload shape: dict with keys {sorted(payload)[:12]}. "
            "Refusing to guess — an empty parse here would look exactly like a quiet day."
        )
    raise PFFClientError(f"Unrecognised PFF payload type {type(payload).__name__}")
