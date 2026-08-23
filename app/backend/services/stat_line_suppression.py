"""NF-INJ1-C — withhold the COUNTING-STAT LINE on rows whose line is physically impossible.

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐ WHAT THIS IS, AND WHAT IT IS NOT
═══════════════════════════════════════════════════════════════════════════════════════════════════

NF-INJ1 measured a defect on the live board: ~10 rows (all QB) whose served stat line is impossible
at their own expected games — Easton Stick at 153.4 pass attempts over 1.86 projected games, i.e.
**82.7 attempts per game against an all-time realized maximum of 45.4**. The mechanism is NF1.5's
point permutation, which rescales the twelve stat columns to hand a player a different player's
point level and leaves `proj_games` behind (`nf1_model._RAW_SCALE_COLS` contains every stat and not
the games). Nothing in the payload is self-inconsistent in a way a schema or the scorer could see.

The REAL fix is a model change. It was pre-registered, funded as NF-INJ2, run, and **REFUSED by its
own pre-registered whole-board ordering gate** — which fired the fallback the PM had already
recorded in `nf_inj1_diagnosis.md` §8.1:

    > Suppress the stat line on violating rows only (points and expected games still render; the
    > impossible counting stats do not) IF EITHER (a) NF-INJ2 is not funded, OR
    > **(b) NF-INJ2 runs and does not clear its gates.**

⇒ This module is that fallback: **a SYMPTOM patch on the DISPLAY of a paid surface.** It changes no
projection, no ordering, no VOR and no band, and it must never be read as having fixed anything.
NF-INJ2's refusal stands exactly as recorded (E2.1-r — a refused arm is not re-read because a
consequence of the refusal was inconvenient).

═══════════════════════════════════════════════════════════════════════════════════════════════════
⭐⭐ THE PREDICATE IS NF-INJ1's RECORDED ONE — IMPORTED, NEVER RE-DERIVED
═══════════════════════════════════════════════════════════════════════════════════════════════════

`projection_coherence.row_violations` IS the predicate, sourced from
`quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inj1_diagnosis.md` §2.2
("Blast radius") and implemented in `projection_coherence.REALIZED_MAX_PER_GAME` — the MAXIMUM
per-game rate any real NFL player-season posted 2006-2025 over 11,190 player-seasons.

⛔ NO THRESHOLD IS INVENTED HERE, and none may be. The envelope is a MAX, so a breach is a statement
about physical possibility rather than about likelihood; it was fixed before any board row was
scored and ⛔ must never be widened to accommodate a board that failed it.

⭐ AND IT IS IMPORTED RATHER THAN MIRRORED. A copy of those numbers in `app/backend/` would be the
repo's most-repeated defect — one logical rule with two owners (INC-30 crontab, INC-36 deploy,
INC-38 month-boundary, E9.61's two renderers of one field) — and the two owners here would be the
guard that PAGES about a violating row and the code that WITHHOLDS it, which is the pairing you
least want to drift. `deploy.sh` step 3d lifts the module into the Lambda zip the same way step 3b
lifts `game_day.py` and 3c the draft optimizer; it is stdlib-only at module scope (its lone `pandas`
import is nested inside `frame_rows`, which nothing here calls). Pinned by
`test_nf_c_lda_1_lambda_import_weight.py` — a copy list that stops carrying it fails the build.

═══════════════════════════════════════════════════════════════════════════════════════════════════
ABSENT ≠ WITHHELD (NF-FRESH2), AND THE MARKER CARRIES NO NUMBERS
═══════════════════════════════════════════════════════════════════════════════════════════════════

A withheld stat and a stat that was never served arrive at the browser as the SAME absent key, and
they are different facts: one is "we have this and are not showing it", the other is "there is
nothing here". Rendering both as a bare em-dash is the E9.56c inversion (a withheld value silently
reading as "we have nothing for this player"). So a suppressed row carries `statLineWithheld` — the
LIST OF THE KEYS THAT WERE REMOVED — and the render path branches on it:

    key absent, name NOT in `statLineWithheld`  →  never served      →  "—", as before
    key absent, name IN `statLineWithheld`      →  withheld by us    →  "—" + the disclosure

🚨 THE MARKER MUST NEVER CARRY A MAGNITUDE, and this is easy to get wrong while trying to be
helpful. `row_violations` returns `season_total`, `implied_per_game` and `times_over` — and
`implied_per_game × g` reconstructs the withheld season total exactly, as does
`times_over × max_ever_per_game × g`. Publishing any of them would leave the suppressed number one
multiplication away on a payload whose whole purpose is to not carry it. Field NAMES only.

═══════════════════════════════════════════════════════════════════════════════════════════════════
WHAT COUNTS AS "THE COUNTING-STAT LINE" — DERIVED, NOT LISTED
═══════════════════════════════════════════════════════════════════════════════════════════════════

`projection_fields.STAT_FIELD` — the scorer's own map of every payload field a league weight can
multiply. Deriving from it rather than hand-listing keeps the NF-EPIC 1 safety direction: a NEW
scorable stat is withheld on a violating row automatically, on the same publish that introduces it,
with no code change here.

⚠️ `PAID_SCORING_FIELDS` (`fpStd`/`fpHalf`) is deliberately NOT included, and neither is `fpPpr` or
`g`. The PM's ruling is explicit — "points + expected games still render". A drafter needs the
number and the availability figure; what they must not be shown is a per-game rate no human has
ever posted.
"""

from __future__ import annotations

import logging

from . import projection_fields

logger = logging.getLogger(__name__)

#: The row key naming the withheld fields. Absent on every coherent row, so an unaffected row is
#: byte-identical to what it was before this story.
WITHHELD_KEY = "statLineWithheld"

#: The payload-level count. ⭐ EMITTED EVEN WHEN ZERO, on purpose. "0 rows were withheld" and "this
#: build does not run the check" are different facts, and a key that appears only when something
#: fired cannot distinguish them — the exact NF1.7 (a) vacuous-pass shape this story is full of.
#: It is a payload-level diagnostic, not a projection field, so the "projection fields byte-
#: identical" acceptance criterion is untouched.
WITHHELD_COUNT_KEY = "stat_line_withheld_players"


def counting_stat_fields() -> frozenset[str]:
    """The published field names that make up the counting-stat line.

    Derived from the scorer's own map so a new scorable stat joins it automatically (see the
    header). ⛔ Excludes `fpStd`/`fpHalf`/`fpPpr`/`g` — those are the values that must still render.
    """
    return frozenset(projection_fields.STAT_FIELD.values())


def row_is_impossible(row: dict) -> bool:
    """Does this published row breach NF-INJ1's recorded per-game envelope?

    Thin by design: the predicate itself lives in `projection_coherence` and is imported, never
    restated. The import is LAZY so it stays off every other route's cold-start path (the PERF
    audit's finding in this Lambda: a transitive module-scope import cost every caller ~4 s of init
    for three endpoints' benefit).
    """
    # ⚠️ IMPORTED BY ITS LEAF MODULE PATH, not as `from …fantasy import projection_coherence`.
    # `test_nf_c_lda_1_lambda_import_weight` reads these imports with AST and checks each one
    # against what `deploy.sh` actually copies — and the package form records the PACKAGE
    # (`…nfl.fantasy`), which the copy step satisfies with a bare directory. The leaf form makes the
    # bundle contract real: drop `projection_coherence` from step 3d's copy list and the guard goes
    # red instead of shipping a ModuleNotFoundError that only production can see.
    from quant_sports_intel_models.football.nfl.fantasy.projection_coherence import row_violations

    return bool(row_violations(row))


def suppress_row(row: dict) -> dict:
    """One published row with its counting-stat line withheld IFF the row is impossible.

    ⭐ RETURNS THE *SAME OBJECT* FOR A COHERENT ROW. Not a courtesy: `/nfl/projections-full` is the
    paid substrate and one of this story's acceptance criteria is that a clean row is byte-identical
    to what it served before. Returning the original object makes that true by construction rather
    than by careful key ordering.
    """
    if not row_is_impossible(row):
        return row
    withheld = sorted(k for k in counting_stat_fields() if k in row)
    if not withheld:
        # The row breached the envelope on a field it no longer carries — impossible today (the
        # envelope reads the same keys), but if it ever happens, marking a row whose line was never
        # served would claim we withheld something we never had. Leave it alone.
        return row
    return {**{k: v for k, v in row.items() if k not in withheld}, WITHHELD_KEY: withheld}


def suppress_projections_payload(data: dict) -> dict:
    """The projections payload with the impossible counting-stat lines withheld.

    ⛔ PURE — it must never mutate its input. The blob it is handed is `_full_projections`'s MEMO,
    which `/nfl/my-teams` scores a user's league from; mutating it in place would change a served
    board's numbers from a display patch, which is the one thing this story promises not to do.

    ⚠️ A ROW THAT CANNOT BE EVALUATED IS LEFT ALONE, and that direction is deliberate. NF1.7 (a)
    ("a check that did not run is not a pass") argues for failing closed — but failing closed here
    means blanking a stat line, and a bug in a symptom patch for ~10 undraftable backup QBs must not
    be able to blank the paid substrate for 868 players. So an unexpected failure degrades to
    exactly the pre-story behaviour and is LOGGED, never swallowed silently (E11.7's ALERT tier).
    The count below then under-reports rather than over-reporting, which is the safe direction for a
    number a reader might quote.
    """
    players = data.get("players")
    if not isinstance(players, list):
        return {**data, WITHHELD_COUNT_KEY: 0}
    out: list = []
    withheld_rows = 0
    for row in players:
        if not isinstance(row, dict):
            # A malformed row costs only itself and never blanks the collection (E9.49).
            out.append(row)
            continue
        try:
            patched = suppress_row(row)
        except Exception:  # noqa: BLE001 — see the docstring: degrade to pre-story behaviour, loudly
            logger.error(
                "NF-INJ1-C: coherence check failed for player %r; its stat line is served "
                "unsuppressed and is NOT counted in %s",
                row.get("id"),
                WITHHELD_COUNT_KEY,
                exc_info=True,
            )
            out.append(row)
            continue
        if patched is not row:
            withheld_rows += 1
        out.append(patched)
    return {**data, "players": out, WITHHELD_COUNT_KEY: withheld_rows}
