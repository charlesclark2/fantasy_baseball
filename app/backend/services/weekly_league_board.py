"""NF-WK-MT1 — score a saved league's roster for ONE WEEK, through the ONE server scorer.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⛔ THIS IS AN ADAPTER, NOT A SCORER, AND THE DISTINCTION IS THE WHOLE POINT
═══════════════════════════════════════════════════════════════════════════════════════════════════

NF-EPIC 1 left this codebase with THREE implementations of one scoring policy (`fantasy_engine` —
the authority, `frontend/lib/league-scoring.ts` — the browser port, and
`app/backend/services/league_scoring.py` — the bare-Python Lambda port), and a merge-gate,
`test_nf_epic1_parity.py`, that exists to keep them from drifting. Every one of them is a standing
tax. A FOURTH would be a new one, paid forever, for a surface that needs no new arithmetic.

So nothing here multiplies a weight by a stat. Every point on this module's output comes out of
`league_scoring.score_row`, unchanged, and the weekly payload is readable by it for a reason that is
structural rather than lucky: `nfl_weekly.WEEKLY_COMPONENT_FIELD` is DERIVED from
`projection_fields.STAT_FIELD`, so the champion's component head is already served under the exact
field names the scorer reads. The reuse is what the contract was built for.

⚠️ `test_nf_wk_mt1_weekly_league_board.py` proves that by SUBSTITUTION, not by reading this
docstring and not by grepping for a call: it replaces `league_scoring.score_row` with a sentinel and
requires the sentinel to come out the other end. A comment claiming reuse cannot satisfy it
(INC-38), and neither can an import that nothing invokes (NF-C0e).

───────────────────────────────────────────────────────────────────────────────────────────────────
⭐ WHAT IS EXACT AND WHAT IS MERELY CARRIED
───────────────────────────────────────────────────────────────────────────────────────────────────

`leaguePts` is EXACT. League scoring is linear in the component line, so applying the league's
weights to the projected stats is the answer, not an estimate of it.

`score_row` also returns an interval, by rescaling the payload's own bounds by the ratio the point
moved. That is a reasonable first-order move on a SEASON board, and it is DELIBERATELY DISCARDED
here — see `nfl_weekly`'s NF-WK-MT1 header. A rescaled range labelled as this league's would assert
a precision the substrate does not have; re-expressing an interval under arbitrary scoring needs the
per-stat DISTRIBUTIONS (NF-W6c/W6d, staged with no consumer), not the per-stat means. The caller
carries the model's own PPR range through instead, labelled, beside the PPR point it belongs to.

⛔ Values are returned UNROUNDED. Rounding is a display concern, the served payload already carries
unrounded bounds (`fpP10: 14.1096`), and — the operative reason — the parity clause compares this
module's output against an INDEPENDENT full-PPR computation at float tolerance. Rounding here would
blunt the one gate that can catch a mis-wired stat key.

───────────────────────────────────────────────────────────────────────────────────────────────────
🕳️ THE FAILURE THIS MODULE REFUSES RATHER THAN ABSORBS
───────────────────────────────────────────────────────────────────────────────────────────────────

Handed the PUBLIC weekly payload, every component field would be absent, `resolve_scoring` would
classify every term CAPTURED, and every player would score exactly 0.0 — with no exception, no empty
list and no error. A whole roster of honest-looking zeroes is the worst available failure: it is
indistinguishable from a bye week and it would be believed. `score_weekly_roster` therefore REFUSES
a payload that carries no component field at all, and says which of the two causes it hit.
"""

from __future__ import annotations

from app.backend.models import nfl_weekly
from app.backend.services import league_scoring


class WeeklySubstrateError(RuntimeError):
    """The weekly payload cannot support league scoring at all.

    A distinct type rather than a bare `RuntimeError` so the router can answer it deliberately
    instead of catching everything and reporting one cause for several (the NF-C6b class)."""


#: The identity + PPR fields carried through from a matched weekly row, verbatim. Named rather than
#: spread so a new PAID field on `NflWeeklyPlayer` cannot reach this response by accident — the
#: NF-EPIC 1 direction (an allowlist, never a denylist).
_CARRIED_FIELDS: tuple[str, ...] = (
    "id", "name", "pos", "team", "opp", "home", "status",
    "rosPpr", "rosP10", "rosP90", "rosWeeks", "histWeeks",
)

#: `(reason, detail)` for every absence this module can attribute. The detail is the sentence a
#: surface may render as-is; each states what is true and stops there.
_ABSENCE_DETAIL: dict[str, str] = {
    "position_not_projected": (
        "We do not project this position. The weekly model covers quarterbacks, running backs, "
        "wide receivers and tight ends."
    ),
    "position_absent_this_week": (
        "We project this position, but this week's projection carries no players at it."
    ),
    "not_in_weekly_payload": (
        "This player has no row in this week's projection. The week's own counts, beside this "
        "roster, record how many players were left out and why."
    ),
    "roster_position_unknown": (
        "The saved roster does not record a position for this player, so there is nothing to "
        "match him against."
    ),
    "roster_row_unnamed": (
        "The saved roster does not record a name for this player, so there is nothing to match."
    ),
}


def component_fields_present(weekly_players: list[dict]) -> set[str]:
    """Which of the champion's ELEVEN component fields this payload actually carries.

    The input to the refusal above, and to the CAPTURED/APPLIED split: a league's weight on a stat
    this week's line does not carry must resolve CAPTURED, which `resolve_scoring` does correctly
    only when it is told which fields are really there."""
    present = league_scoring.available_fields(weekly_players)
    return {f for f in nfl_weekly.WEEKLY_COMPONENT_FIELD.values() if f in present}


def classify_absence(roster_row: dict, served_positions: set[str]) -> dict:
    """Why this rostered player has no weekly line — `{reason, detail}`.

    ⭐ THE ORDER IS THE SPECIFICITY ORDER, and it matters: a roster row with no name would also
    have no position, so checking the name first keeps the report on the thing that is actually
    wrong rather than on a consequence of it.

    ⛔ Never returns `no_gameday_roster_row` or `pit_gate_dropped`. Those are real reasons and they
    are counted on the manifest — but per PLAYER this route cannot tell which applies, and naming
    one anyway is a confident wrong explanation, which is worse than an honest "not in this week's
    projection" (NF1.7 (a); the NF-K1 symptom that cost two investigations)."""
    name = str(roster_row.get("name") or "").strip()
    if not name:
        reason = "roster_row_unnamed"
    else:
        raw_pos = str(roster_row.get("position") or "").strip()
        pos = league_scoring.normalize_position(raw_pos)
        if not pos:
            reason = "roster_position_unknown"
        elif pos not in nfl_weekly.PROJECTED_POSITIONS:
            reason = "position_not_projected"
        elif pos not in served_positions:
            reason = "position_absent_this_week"
        else:
            reason = "not_in_weekly_payload"
    return {"reason": reason, "detail": _ABSENCE_DETAIL[reason]}


def served_positions(weekly_players: list[dict]) -> list[str]:
    """The projectable positions this week's payload ACTUALLY carries, read off the rows.

    🔴 NF-K1 — DERIVED, NEVER DECLARED. Returning `PROJECTED_POSITIONS` would restate what the
    builder INTENDED and would have reported a position as served right through an outage in which
    it was not, which is the "documented ≠ actually served" class. A position counts as served only
    if a row exists for it, so this can only ever describe the payload in hand."""
    seen = {
        league_scoring.normalize_position(p.get("pos"))
        for p in weekly_players
        if isinstance(p, dict)
    }
    return [p for p in nfl_weekly.PROJECTED_POSITIONS if p in seen]


def score_weekly_roster(
    *,
    weekly_players: list[dict],
    roster: list[dict],
    cfg: dict,
    stat_field: dict[str, str],
) -> dict:
    """`{rows, coverage, weekly_positions}` — one roster, scored for one week in one league.

    `weekly_players` MUST be the full (paid) payload; see the module header for what happens
    otherwise, and for why that case raises instead of returning zeroes.

    ⭐ THE JOIN IS `league_scoring.match_roster_to_board`, UNCHANGED. It is the same function the
    caller's season roster already goes through, so a name that matches on the season board matches
    here — and a divergence between the two would present to a user as "my players disappeared on
    the weekly tab", which is exactly the kind of thing a second join implementation produces
    (NF-C6P3). It also brings the D/ST franchise join with it at no cost; no weekly row is a team
    defence today, so a rostered D/ST falls through to `position_not_projected`, which is the
    correct answer rather than a missed match.
    """
    if not weekly_players:
        raise WeeklySubstrateError(
            "this week's projection carries no players at all, so there is nothing to score"
        )
    present = component_fields_present(weekly_players)
    if not present:
        raise WeeklySubstrateError(
            "this week's projection carries none of the model's component stats, so a league's "
            "scoring cannot be applied to it. The full (entitled) payload is required — scoring "
            "the public one would silently return zero for every player."
        )

    resolved, coverage = league_scoring.resolve_scoring(
        cfg.get("scoring") or {},
        stat_field=stat_field,
        # ⭐ THE FIELDS ACTUALLY PRESENT, not the scorer's whole map. This is what makes a league's
        # fumble / two-point / kicker / defence weights resolve CAPTURED on a weekly line rather
        # than silently scoring as zero behind an "applied" label.
        fields=league_scoring.available_fields(weekly_players),
        captured_rules=list((cfg.get("captured_rules") or {}).keys()),
    )

    scored: list[dict] = []
    for player in weekly_players:
        if not isinstance(player, dict):
            continue
        pos = league_scoring.normalize_position(player.get("pos"))
        # ⭐ THE ONE SCORER. Its interval is discarded on purpose (module header).
        points = league_scoring.score_row(player, pos, resolved, stat_field)["pts"]
        row = {field: player.get(field) for field in _CARRIED_FIELDS}
        row["pos"] = pos
        row["leaguePts"] = points
        # ⚠️ THE PPR FIELD NAMES COME FROM THE SCORER'S OWN CONSTANTS, never re-typed here. They are
        # the same three `score_row` reads to build the interval this module discards, so a rename
        # moves both sides at once instead of leaving this one silently reading a missing key and
        # serving `null` for a number the payload was carrying all along (the E9.41 / NF-C0e shape).
        row["pprPts"] = player.get(league_scoring.BASE_POINTS_FIELD)
        row["bandP10"] = player.get(league_scoring.BASE_P10_FIELD)
        row["bandP90"] = player.get(league_scoring.BASE_P90_FIELD)
        scored.append(row)

    positions = served_positions(weekly_players)
    position_set = set(positions)

    rows: list[dict] = []
    for matched in league_scoring.match_roster_to_board(roster, scored):
        roster_row = matched.get("roster") or {}
        weekly_row = matched.get("board")
        out: dict = {
            "rosterName": str(roster_row.get("name") or ""),
            "rosterPos": roster_row.get("position"),
            "rosterTeam": roster_row.get("team"),
            "starter": roster_row.get("starter"),
        }
        if weekly_row is None:
            out["absence"] = classify_absence(roster_row, position_set)
        else:
            out.update(weekly_row)
            out["absence"] = None
        rows.append(out)

    return {"rows": rows, "coverage": coverage, "weekly_positions": positions}
