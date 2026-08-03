"""E8.2 — roster entry → prospect-board row, and the availability overlay that falls out of it.

The upload gives us `F Surname` and NOTHING ELSE: no player id, no MLB team, and only a fantasy
SLOT as a position hint. So this is a name match, and the E7.4 caution applies — a name-only fuzzy
match across all of MLB manufactures false positives. Four things keep it honest:

  1. **LEAGUE SCOPE FIRST.** A dynasty league is AL-only or NL-only, so the candidate set is one
     league's board rows (713) rather than the whole board (1,451). Measured on the operator's real
     export, scoping to the AL cuts ambiguous names from 6 to 2. It is a REAL narrowing.
  2. **THE FANTASY SLOT IS USED WHERE IT IS UNAMBIGUOUS.** It cannot make a match, but a batter
     slot contradicting a pitching prospect can unmake one — worth 4 corrections in 103 on the real
     export, every one a false positive (`_slot_allows`).
  3. **AN AMBIGUOUS NAME IS NEVER GUESSED.** Three `E Rodriguez`es on the AL board is not a match
     to the first one; it is a question for the user, carried in `review` with its candidates.
  4. **NOTHING IS EVER SILENTLY DROPPED.** Every entry lands in exactly one tier, every tier is
     reported, and two entries can never quietly collapse onto one board row (`CONTESTED`).

⚠️ THE ASYMMETRY THAT DRIVES THE DESIGN. The two failure directions are not equally bad:

    a rostered prospect we FAIL to match  → the board shows him AVAILABLE → the user drafts a
                                            player somebody already owns.        ← the bad one
    an available prospect we match WRONGLY → he is hidden from the pool, and the user sees exactly
                                            who supposedly owns him, so it is visible + fixable.

Hence: the variant leg (below) is applied rather than withheld, but it is LABELLED, listed for
review, and counted separately — never folded into the exact count.

🔎 WHAT AN UNRESOLVED ROW ACTUALLY MEANS, measured rather than assumed. On the real export, 334 of
442 rostered players match no board row — and that is CORRECT, because a fantasy roster is mostly
established major-leaguers who are not prospects at all. Of the 61 minors-slot stashes, 57 matched;
the 3 that did not (C.J. Kayfus, V Honeycutt, D Lesko) are absent from the board ENTIRELY, so there
is no board row for them to wrongly mark available. That is why `unresolved` is reported plainly
instead of as a failure — but minors stashes are surfaced FIRST, because they are the only tier
where an unresolved row is likely to be a prospect.

⭐ AND THAT TIER IS ALSO A PRODUCT SIGNAL, NOT JUST A CAVEAT (operator, 2026-08-03). A player in
somebody's MINORS slot who matches no board row is evidence the board is INCOMPLETE: a competitive
dynasty owner is spending a roster spot on him. `RosterMatch.coverage_gaps` reports those rather
than letting a dismissal delete them — see the field's own note for why "not a prospect" and
"missing from our board" had to become two different statements.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from app.backend.services.mlb_roster.roster_upload import RosterEntry

#: Name particles that are a SUFFIX rather than part of the surname.
_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})

#: How an entry was resolved. Ordered worst → best for reporting.
UNRESOLVED = "unresolved"
#: The admin says this player IS a prospect we simply do not carry. Kept, and REPORTED — see
#: `RosterMatch.coverage_gaps`.
MISSING_FROM_BOARD = "missing_from_board"
NOT_A_PROSPECT = "not_a_prospect"
POSITION_CONFLICT = "position_conflict"
CONTESTED = "contested"
AMBIGUOUS = "ambiguous"
VARIANT = "variant"
EXACT = "exact"
MANUAL = "manual"

#: Fantasy slots that hold a PITCHER. Anything else is a batter slot; anything UNKNOWN (a long-form
#: upload with no position column, a league with exotic slot names) disables the check rather than
#: guessing — a hint we do not understand must not be allowed to reject a match.
_PITCHER_SLOTS = frozenset({"P", "SP", "RP", "PITCHER", "SP/RP", "RP/SP"})
_BATTER_SLOTS = frozenset(
    {"C", "1B", "2B", "3B", "SS", "MI", "CI", "OF", "DH", "UT", "IF", "LF", "CF", "RF"}
)


def _slot_allows(slot: str, board_type: str) -> bool:
    """Is a roster SLOT consistent with a board row's player type?

    ⭐ THIS IS THE ONE PIECE OF SIGNAL THE UPLOAD CARRIES BESIDES THE NAME, and on the operator's
    real export it is worth 4 corrections in 103 matches — every one of them a FALSE POSITIVE where
    an established major-leaguer collided with a same-named pitching prospect:

        `S Perez` in the C slot   (Salvador Perez)  → "Steven Pérez",  a SIRP prospect
        `M Massey` at 2B          (Michael Massey)  → "Michael Massey", a SIRP prospect
        `D Hill` at DH                              → "Dasan Hill",     an SP prospect
        `C Smith` in OF                             → "Cade Smith",     an SP prospect

    Each of those wrongly marked an AVAILABLE prospect as rostered, hiding him from the draft pool.
    A batter is not rostered in a pitcher slot and a pitcher is not rostered in a batter slot, so
    the contradiction is real information — but it is applied ONLY as a filter over same-name
    candidates, never as a match on its own, and a `two_way` prospect satisfies both (Ohtani is the
    reason that case exists).
    """
    slot = (slot or "").strip().upper()
    # Symmetric "no opinion" cases: an unknown SLOT and an unknown board TYPE must both disable the
    # check. A hint we cannot interpret has to be inert — silently rejecting a real match because a
    # board row happened to omit its type would create the exact false-negative this check exists
    # to avoid, and it would be invisible.
    if board_type not in ("batter", "pitcher"):
        return True
    if slot in _PITCHER_SLOTS:
        return board_type == "pitcher"
    if slot in _BATTER_SLOTS:
        return board_type != "pitcher"
    return True  # unknown slot → no opinion


@dataclass(frozen=True)
class MatchedEntry:
    entry: RosterEntry
    #: The board row's `rank` — the board's only unique key (see `_board_key`). None when unresolved.
    board_rank: int | None
    confidence: str
    #: Board rows the user could pick from, when we refused to guess.
    candidates: tuple[dict, ...] = ()


@dataclass
class RosterMatch:
    matched: list[MatchedEntry] = field(default_factory=list)
    #: board rank → the entry that owns it.
    by_rank: dict[int, MatchedEntry] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    scope_rows: int = 0
    #: ⭐ BOARD-COVERAGE GAPS — rostered players who look like prospects we do not carry.
    #:
    #: This is the signal that would otherwise be thrown away. A player sitting in somebody's
    #: MINORS slot who matches no board row is not noise: a competitive dynasty owner is spending a
    #: roster spot on him, which is independent evidence he is worth tracking. The old "not a board
    #: prospect" dismissal collapsed two very different statements — "this is Salvador Perez, an
    #: established major-leaguer" and "this is a real prospect you are missing" — into one silent
    #: delete. They are now separate, and the second is REPORTED.
    coverage_gaps: list[dict] = field(default_factory=list)

    @property
    def review(self) -> list[MatchedEntry]:
        """Everything the user should look at, most-actionable first.

        Order is deliberate, most-actionable first: AMBIGUOUS and CONTESTED rows are definitionally
        about a board prospect, so they are real holes in the overlay. A POSITION_CONFLICT is a
        same-name candidate the slot rejected — usually correctly. An unresolved MINORS stash is the
        next most likely to be a prospect. A VARIANT match is applied already, so it is last: a
        confirmation, not a blocker.
        """
        def rank(item: MatchedEntry) -> tuple[int, str]:
            order = {AMBIGUOUS: 0, CONTESTED: 1, POSITION_CONFLICT: 2, VARIANT: 4}
            if item.confidence == UNRESOLVED and item.entry.status == "minors":
                return 3, item.entry.name
            return order.get(item.confidence, 5), item.entry.name

        return sorted(
            (
                m
                for m in self.matched
                if m.confidence in (AMBIGUOUS, CONTESTED, POSITION_CONFLICT, VARIANT)
                or (m.confidence == UNRESOLVED and m.entry.status == "minors")
            ),
            key=rank,
        )


def _deaccent(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def name_key(name: str) -> tuple[str, str, str] | None:
    """`"J.P. Crawford"` → `("j", "crawford", "crawford")`; `"E De Los Santos"` →
    `("e", "delossantos", "santos")`.

    Returns `(initial, surname, last_word)`. The third element powers the VARIANT leg: CBS renders
    `Hao-Yu Lee` as `H Yu Lee`, so the full surname disagrees (`yulee` vs `lee`) while the last word
    does not. Without that leg a genuinely rostered prospect reads as available.

    Middle initials are dropped (`J H. Smith` → `smith`), because MLBAM writes `Josh H. Smith` to
    separate two Josh Smiths and the board may carry either form.
    """
    tokens = [t for t in re.split(r"\s+", _deaccent(name).strip()) if t]
    if not tokens:
        return None
    initial = re.sub(r"[^A-Za-z]", "", tokens[0])[:1].lower()
    if not initial:
        return None

    words: list[str] = []
    for token in tokens[1:]:
        bare = re.sub(r"[^A-Za-z]", "", token)
        if not bare or bare.lower() in _SUFFIXES or len(bare) == 1:
            continue
        words.append(bare.lower())
    if not words:
        return None
    return initial, "".join(words), words[-1]


def full_name_key(name: str) -> str | None:
    """`"Chase DeLauter"` → `"chasedelauter"`; `"J.P. Crawford"` → `"jpcrawford"`.

    ⭐ THE HIGHEST-VALUE KEY WE HAVE, when the upload carries full names. Measured on the live AL
    board: keyed on INITIAL + surname, **9 board keys are ambiguous** (three `E Rodriguez`es, two
    `J Sanchez`es, …); keyed on the full name, **zero** are. So a per-team "roster overview" export
    does not merely reduce the ambiguity class, it removes it.

    Returns None for a name that is only an initial + surname (`C DeLauter`), so a league-wide grid
    simply does not use this leg and falls through to the initial key — rather than matching
    `cdelauter` against `chasedelauter` and finding nothing.
    """
    tokens = [t for t in re.split(r"\s+", _deaccent(name).strip()) if t]
    if len(tokens) < 2:
        return None
    first = re.sub(r"[^A-Za-z]", "", tokens[0])
    if len(first) < 2:
        return None  # an initial, not a given name — this leg does not apply
    words = [first]
    for token in tokens[1:]:
        bare = re.sub(r"[^A-Za-z]", "", token)
        if not bare or bare.lower() in _SUFFIXES or len(bare) == 1:
            continue
        words.append(bare)
    return "".join(words).lower() if len(words) > 1 else None


def _board_key(row: Mapping[str, Any]) -> int | None:
    """The board's unique row identity.

    ⚠️ It is `rank`, NOT `mlbamId`. Measured on the live 2026 board: `rank` is unique across all
    1,451 rows, `(name, org)` is NOT unique, and **9 rows carry no `mlbamId` at all** — keying the
    overlay on the MLBAM id would leave those 9 permanently un-markable, i.e. permanently and
    wrongly "available". The MLBAM id is still reported when present; it is just not the join key.
    """
    rank = row.get("rank")
    return int(rank) if isinstance(rank, (int, float)) and not isinstance(rank, bool) else None


def _candidate_summary(row: Mapping[str, Any]) -> dict:
    return {
        "rank": _board_key(row),
        "name": row.get("name"),
        "org": row.get("org"),
        "pos": row.get("pos"),
        "level": row.get("level"),
        "eta": row.get("eta"),
        "mlbamId": row.get("mlbamId"),
    }


def _dedupe_same_player(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Collapse board rows that are plainly ONE player listed twice.

    The live board carries 4 duplicate-name pairs (`Griffin Hugus`, `Micah Bucknam`,
    `Jose Luis Acevedo`) where the two rows share a name AND an org and one of them simply has no
    MLBAM id. Treating those as an ambiguity would ask the user to choose between a player and
    himself. Same name + same org collapses to the row that carries the id.
    """
    if len(rows) < 2:
        return list(rows)
    best: dict[tuple, Mapping[str, Any]] = {}
    for row in rows:
        key = (str(row.get("name") or "").lower(), str(row.get("org") or "").lower())
        current = best.get(key)
        if current is None or (row.get("mlbamId") and not current.get("mlbamId")):
            best[key] = row
    return list(best.values())


def match_roster(
    entries: Sequence[RosterEntry],
    board_rows: Iterable[Mapping[str, Any]],
    league_scope: str | None = None,
    overrides: Mapping[str, int | None] | None = None,
) -> RosterMatch:
    """Resolve every roster entry against the board, scoped to the league.

    `overrides` is the manual-fix fallback: `{entry.key: board_rank}` pins a match the user made by
    hand, and `{entry.key: None}` records "this is not a board prospect, stop asking" so a dismissed
    row leaves the review queue without ever being counted as matched.
    """
    overrides = overrides or {}
    scope = (league_scope or "").strip().upper()

    rows = [r for r in board_rows if _board_key(r) is not None]
    if scope in ("AL", "NL"):
        rows = [r for r in rows if str(r.get("league") or "").upper() == scope]

    by_rank = {_board_key(r): r for r in rows}
    name_index: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    full_index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    last_index: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        whole = full_name_key(str(row.get("name") or ""))
        if whole:
            name_index[whole].append(row)
        key = name_key(str(row.get("name") or ""))
        if not key:
            continue
        full_index[(key[0], key[1])].append(row)
        last_index[(key[0], key[2])].append(row)

    result = RosterMatch(scope_rows=len(rows))
    counts: dict[str, int] = defaultdict(int)
    claimed: dict[int, MatchedEntry] = {}

    # ── PASS 1: the user's manual pins, before anything automatic ──
    # ⭐ TWO PASSES, NOT ONE, so the outcome cannot depend on ROSTER ORDER. In a single pass an
    # automatic match that happened to be read first would claim a board row and the user's explicit
    # pin for that row would silently lose — a correction that appears to be accepted and then does
    # nothing. A manual pin is the strongest signal we have and must always win; an automatic match
    # that collides with one falls through to CONTESTED in pass 2, which is visible.
    resolved: dict[str, MatchedEntry] = {}
    for entry in entries:
        override = overrides.get(entry.key, "__absent__")
        if override == "__absent__":
            continue
        if override is None or override == NOT_A_PROSPECT:
            # "This is an established major-leaguer." Resolved, silent, not a coverage gap.
            resolved[entry.key] = MatchedEntry(entry=entry, board_rank=None, confidence=MANUAL)
            counts["dismissed"] += 1
        elif override == MISSING_FROM_BOARD:
            # "This IS a prospect — we just do not carry him." Leaves the review queue so it stops
            # nagging, but is REPORTED as a coverage gap instead of being forgotten.
            resolved[entry.key] = MatchedEntry(
                entry=entry, board_rank=None, confidence=MISSING_FROM_BOARD
            )
            counts[MISSING_FROM_BOARD] += 1
        elif str(override).lstrip("-").isdigit() and by_rank.get(int(override)) is not None:
            matched = MatchedEntry(entry=entry, board_rank=int(override), confidence=MANUAL)
            resolved[entry.key] = matched
            counts[MANUAL] += 1
            claimed[int(override)] = matched
        # An override pointing OUTSIDE the current scope (the user changed AL→NL, or the board was
        # re-published) is left unresolved here and re-matched below, rather than honoured as a
        # dangling pin that resolves to nothing.

    # ── PASS 2: everything else ──
    for entry in entries:
        pinned = resolved.get(entry.key)
        if pinned is not None:
            result.matched.append(pinned)
            continue

        key = name_key(entry.name)
        if key is None:
            result.matched.append(MatchedEntry(entry=entry, board_rank=None, confidence=UNRESOLVED))
            counts[UNRESOLVED] += 1
            continue

        # LEG 1 — the whole name, when the upload gives one. Unambiguous on the live board.
        whole = full_name_key(entry.name)
        candidates = _dedupe_same_player(name_index.get(whole, [])) if whole else []
        confidence = EXACT
        # LEG 2 — initial + surname, which is all a league-wide grid carries.
        if not candidates:
            candidates = _dedupe_same_player(full_index.get((key[0], key[1]), []))
        # LEG 3 — initial + the LAST word of the surname (`H Yu Lee` → `Hao-Yu Lee`).
        if not candidates:
            candidates = _dedupe_same_player(last_index.get((key[0], key[2]), []))
            confidence = VARIANT

        # The slot filters same-name candidates; it never creates a match. When it rejects the ONLY
        # candidate the entry is NOT counted as rostered — but it is surfaced WITH that candidate
        # attached, so if the board's type is what is wrong the user can still pin it by hand. An
        # unexplained non-match on this surface is the failure that hides.
        if candidates:
            allowed = [c for c in candidates if _slot_allows(entry.slot, str(c.get("type") or ""))]
            if not allowed:
                result.matched.append(
                    MatchedEntry(
                        entry=entry,
                        board_rank=None,
                        confidence=POSITION_CONFLICT,
                        candidates=tuple(_candidate_summary(c) for c in candidates),
                    )
                )
                counts[POSITION_CONFLICT] += 1
                continue
            candidates = allowed

        # The MLB club narrows a remaining tie. ⚠️ Used ONLY to choose between same-name
        # candidates, never to reject a lone one: a player's club changes constantly (the board
        # carries his PARENT org, and a trade moves it), so an org mismatch is weak evidence of a
        # different player while an org MATCH is strong evidence of the same one. Contrast the slot
        # check above, which may reject — batter-vs-pitcher does not change.
        if len(candidates) > 1 and entry.org:
            same_org = [
                c for c in candidates
                if str(c.get("org") or "").upper() == entry.org.strip().upper()
            ]
            if len(same_org) == 1:
                candidates = same_org

        if len(candidates) == 1:
            rank = _board_key(candidates[0])
            if rank is not None and rank in claimed:
                # ⚠️ TWO roster entries resolved to ONE board row, and a player can only be on one
                # roster — so one of them is a different person we cannot tell apart. Taking the
                # first and discarding the second silently is the drop this module exists to
                # prevent, so the loser is reported instead. (The slot filter above already
                # resolves the common case: `Texas Chaos` listing `C Smith` at both OF and P.)
                contested = MatchedEntry(
                    entry=entry,
                    board_rank=None,
                    confidence=CONTESTED,
                    candidates=(_candidate_summary(candidates[0]),),
                )
                counts[CONTESTED] += 1
                result.matched.append(contested)
                continue
            matched = MatchedEntry(entry=entry, board_rank=rank, confidence=confidence)
            counts[confidence] += 1
            result.matched.append(matched)
            if rank is not None:
                claimed[rank] = matched
        elif candidates:
            matched = MatchedEntry(
                entry=entry,
                board_rank=None,
                confidence=AMBIGUOUS,
                candidates=tuple(_candidate_summary(c) for c in candidates),
            )
            counts[AMBIGUOUS] += 1
            result.matched.append(matched)
        else:
            result.matched.append(MatchedEntry(entry=entry, board_rank=None, confidence=UNRESOLVED))
            counts[UNRESOLVED] += 1

    # A gap is either CONFIRMED by the admin, or SUGGESTED because an unresolved player sits in a
    # minors slot — the tier where "we could not place him" most often means "we do not carry him".
    for m in result.matched:
        if m.confidence == MISSING_FROM_BOARD:
            source = "confirmed"
        elif m.confidence == UNRESOLVED and m.entry.status == "minors":
            source = "suggested"
        else:
            continue
        result.coverage_gaps.append(
            {
                "key": m.entry.key,
                "name": m.entry.name,
                "team": m.entry.team,
                "slot": m.entry.slot,
                "status": m.entry.status,
                "org": m.entry.org,
                "positions": m.entry.positions,
                "source": source,
            }
        )
    result.coverage_gaps.sort(key=lambda g: (g["source"] != "confirmed", g["name"]))

    result.by_rank = claimed
    result.counts = {
        "players": len(entries),
        EXACT: counts[EXACT],
        VARIANT: counts[VARIANT],
        MANUAL: counts[MANUAL],
        AMBIGUOUS: counts[AMBIGUOUS],
        POSITION_CONFLICT: counts[POSITION_CONFLICT],
        CONTESTED: counts[CONTESTED],
        MISSING_FROM_BOARD: counts[MISSING_FROM_BOARD],
        UNRESOLVED: counts[UNRESOLVED],
        "dismissed": counts["dismissed"],
        "rostered_board_rows": len(claimed),
        "board_rows_in_scope": len(rows),
        "coverage_gaps": len(result.coverage_gaps),
        "minors_unresolved": sum(
            1 for m in result.matched
            if m.confidence == UNRESOLVED and m.entry.status == "minors"
        ),
    }
    return result
