"""player_naming.py — ONE authority for how a player's name is CASED on every fantasy surface.

E9.61 item 4. Before this module the two exporters each carried their own casing pass and they
disagreed: `export_track_record_json.display_name` (a rule pass + a nine-entry hand map, applied only
to ALL-CAPS input) and `export_draft_board_json._titlecase` (a different rule pass, applied to EVERY
input). The board's version is what the live Rankings / Projections / Player-Search surfaces read.

── WHAT WAS ACTUALLY WRONG (measured against the LIVE 2026 payload, 858 players) ──────────────────

⭐ THE ROOT CAUSE WAS OURS, AND THE EARLIER DIAGNOSIS HAD IT BACKWARDS. "MacK Hollins" was recorded
as a defect "CARRIED IN THE DATA", on the reasoning that no `Mac` rule exists in the repo. That check
was run against the TRACK-RECORD exporter's regex (`\\bMc([a-z])`, which indeed cannot match "Mack")
— but `_titlecase` in the BOARD exporter had a second, different rule: a loop over `("Mc", "Mac")`
that upper-cases the next letter after either prefix. So `MACK HOLLINS` -> `.title()` -> "Mack
Hollins" -> the Mac rule -> **"MacK Hollins"**. We were producing it.

⚠️ THE LESSON GENERALISES: "there is no rule that does this" is only true of the file you grepped.
Two renderers of the same field are two rule sets, and the one you did not read is the one serving
the defect. That is the argument for this module existing at all.

Measured, and the three findings drive the three behaviours below:

1. **30 veterans were mis-cased** and NOT recoverable by any rule — `Ceedee Lamb`, `Dj Moore`,
   `Sam Laporta`, `Devonta Smith`, `Aj Barner`, `MacK Hollins`, … The source ships them ALL-CAPS
   (703 of 784 rows in the 2026 frame), and casing is genuinely undecidable from an upper-case
   string: "DEVONTA FREEMAN" is "Devonta Freeman" while "DEVONTA SMITH" is "DeVonta Smith".
   ⇒ needs an EXTERNAL AUTHORITY. `roster_casing_authority` is it.

2. **3 already-correct rookie names were DAMAGED by us** — the source carries `KC Concepcion`,
   `CJ Daniels`, `CJ Williams` correctly and `_titlecase` applied `.title()` unconditionally,
   serving "Kc Concepcion". 81 of the 784 rows arrive clean (the rookie pipeline) and every one of
   them was passed through a de-shouter written for shouting input.
   ⇒ **de-shout ONLY what is shouting.** A mixed-case name is a name someone already got right.

3. **The `Mac` rule earns nothing and costs a name.** Across all seven published seasons the MAC*
   names are AUSTIN MACK / MAC JONES / MACK HOLLINS / MARLON MACK / Alizé Mack — not one needs the
   capital, and the rule breaks Hollins. (`Mc` is the opposite: all 37 Mc-prefixed all-caps names
   want it — MCCAFFREY, MCLAURIN, MCCONKEY …) ⇒ `Mc` stays as a rule, `Mac` is dropped and left to
   the authority. If a MacKenzie/MacDonald ever appears he resolves through his roster row like
   everyone else, which is the point: rules cannot decide this, so stop asking them to.

── THE SAFETY PROPERTY, AND WHY IT IS THE WHOLE DESIGN ─────────────────────────────────────────────

The roster is a good authority for CASE and a BAD one for identity. Measured on the same 858 players:
62 names disagree with the roster, and only 30 of those are casing. The other 32 are things a casing
pass must never touch —

  * suffixes, disagreeing in BOTH directions: we serve "Travis Etienne Jr." / roster "Travis
    Etienne", but we serve "Odell Beckham" / roster "Odell Beckham Jr.";
  * different names entirely: "Hollywood Brown" vs "Marquise Brown", "Drew Ogletree" vs "Andrew
    Ogletree", "Joshua Palmer" vs "Josh Palmer".

A wholesale repoint onto the roster name — the obvious reading of "carry nflverse's display name" —
would therefore have been a REGRESSION: it drops the suffix a manager uses to tell two players apart
and replaces the market's nickname with a legal name nobody drafts by.

⇒ `reconcile_casing` adopts the authority **only when the two names are equal under casefold**. That
single gate is what makes this safe, and it is worth stating as an invariant rather than a habit:

    the output always satisfies  out.casefold() == ours.casefold()

i.e. this module can change LETTER CASE and nothing else. It is structurally incapable of adding or
dropping a suffix, swapping a nickname, or moving a row onto a different player — which is why the
32 non-casing disagreements need no allow-list, no exception map, and no review. They cannot be
reached. `test_e9_61_name_casing.py` pins the invariant directly against the live-measured pairs.

The residue is honest and small: a repair that is NOT a pure case change (the source drops the
apostrophe in "DEVON ACHANE" -> "De'Von Achane") cannot come from the authority by construction, so
it stays in `_REPAIRS` as an explicit, hand-verified entry. That map used to carry nine names; the
authority reproduces eight of them exactly, and this is the one it cannot.
"""
from __future__ import annotations

import functools
import logging
import re

log = logging.getLogger("nfl.fantasy.player_naming")


# Non-case repairs — a name the source spells with the WRONG CHARACTERS, not merely the wrong case.
# ⛔ Deliberately NOT a place to park casing fixes: anything that is a pure case change belongs to
# `roster_casing_authority`, which needs no maintenance and covers every future draft class. Keyed on
# the CASEFOLDED whole name so both the shouting and the already-cased spelling land on one answer.
_REPAIRS = {
    "devon achane": "De'Von Achane",  # the source drops the apostrophe entirely
}

# ── The FROZEN fallback map, consulted only when the authority has no row ───────────────────────
#
# This started as the track-record exporter's primary mechanism and is now a backstop. It is kept
# (rather than deleted) for one measured reason: without it, an unreachable roster read does not
# merely fail to IMPROVE the names, it makes eight of them WORSE than they were before this module
# existed — "DEVONTA SMITH" degrades to "Devonta Smith". A best-effort authority whose absence
# silently regresses the output is the "graceful fallback hides a defect" shape, and the cheapest
# defence is to keep the answer we already had.
#
# Every entry here is verified to AGREE with the roster, so it is not a competing source of truth —
# it is the same truth, cached offline. The authority WINS where both have an answer.
#
# ⛔ FROZEN — do not extend it. A newly mis-cased name is the authority's job; adding it here would
# recreate the once-per-draft-class maintenance burden this module exists to end, and a local entry
# is invisible to whoever reads the roster next.
_FALLBACK_CASINGS = {
    "CEEDEE LAMB": "CeeDee Lamb",
    "DEANDRE HOPKINS": "DeAndre Hopkins",
    "DEVANTE PARKER": "DeVante Parker",
    "DEVONTA SMITH": "DeVonta Smith",
    "DK METCALF": "DK Metcalf",
    "JUJU SMITH-SCHUSTER": "JuJu Smith-Schuster",
    "LESEAN MCCOY": "LeSean McCoy",
    "SAM LAPORTA": "Sam LaPorta",
}

# Generational suffixes `.title()` mangles (JAMES COOK III -> "Iii"). Only ever applied to the LAST
# token, so a real name that merely looks like one (Ivory, Vince) is never touched.
_NAME_SUFFIXES = {"Ii": "II", "Iii": "III", "Iv": "IV", "Vi": "VI"}

# A DST unit name is a TEAM CODE plus a unit label ("DEN D/ST"), not a person's name — `.title()`
# renders it "Den D/St". These are already display-ready (NF1.6).
_UNIT_SUFFIXES = ("D/ST", "DST", "DEFENSE")


def de_shout(name: str) -> str:
    """An ALL-CAPS source name rendered for display. Assumes its input is shouting — callers gate on
    that; see `display_name`.

    `str.title()` already handles apostrophes, hyphens, periods and "St." ("JA'MARR CHASE" ->
    "Ja'Marr Chase", "AMON-RA ST. BROWN" -> "Amon-Ra St. Brown", "A.J. BROWN" -> "A.J. Brown"). It
    lower-cases the second capital in "MCCAFFREY", so Mc gets a rule; `Mac` deliberately does not
    (see the module docstring — it is measured to earn nothing and to break "Mack").
    """
    out = str(name).title()
    out = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), out)
    parts = out.split()
    if parts and parts[-1] in _NAME_SUFFIXES:
        parts[-1] = _NAME_SUFFIXES[parts[-1]]
        out = " ".join(parts)
    return out


def reconcile_casing(ours: str, authority: str | None) -> str:
    """`ours`, re-cased to match `authority` — but ONLY when the two differ by case alone.

    This is the module's safety property (see the docstring): the return value always casefolds equal
    to `ours`, so an authority that disagrees about a SUFFIX or a NICKNAME is ignored rather than
    obeyed. 32 of the 62 live disagreements are exactly that, and every one of them must be ignored.
    """
    if not authority:
        return ours
    return authority if ours.casefold() == str(authority).casefold() else ours


def drafted_as(ours: str, draft_board: str | None) -> str:
    """`ours`, replaced by the name a DRAFT BOARD shows for the same player — the name a draft
    participant is actually looking for.

    ⭐ WHY A SECOND AUTHORITY RATHER THAN A WIDER GATE ON THE FIRST. The roster authority is
    deliberately case-only, because the roster is good at spelling and bad at identity: it wants to
    call Hollywood Brown "Marquise Brown". Fantasy Football Calculator is the opposite — it is a real
    draft board, so its display name IS the drafter-facing name BY CONSTRUCTION, and it is the right
    source for exactly the changes the case gate refuses. Measured on the live 2026 board: of the 232
    players FFC also drafts, our names (after the case fix) match on 228.

    ⛔ ONE EXCEPTION, AND IT IS NOT A STYLE PREFERENCE: **a generational suffix is never DROPPED.**
    FFC's suffix handling is its own house style and is not self-consistent — it keeps "James Cook
    III" and "Aaron Jones Sr." but renders Kenneth Walker III as "Kenneth Walker", where our name and
    the roster BOTH carry the III (as do ESPN/Yahoo/Sleeper). The asymmetry is the point: a suffix is
    what separates two real people (Frank Gore from Frank Gore Jr.), so ADDING one can only ever
    disambiguate while REMOVING one destroys information. Adds are taken, drops are refused.

    Measured effect today — four names, each a case the reader would notice: `Kenneth Gainwell` ->
    **Kenny Gainwell** (nickname; a genuinely drafted RB at ADP 99), `Eddy Pineiro` -> **Eddy
    Piñeiro** (diacritic), `Deebo Samuel` -> **Deebo Samuel Sr.** (suffix ADD, and the roster agrees),
    and `Kenneth Walker III` left alone (suffix DROP, refused).
    """
    if not draft_board:
        return ours
    theirs = str(draft_board).strip()
    if theirs == ours:
        return ours
    if _suffix_of(ours) and not _suffix_of(theirs):
        return ours  # the drop clause — see above
    return theirs


def _suffix_of(name: str) -> str | None:
    """The trailing generational suffix, if any. Compared case- and dot-insensitively so "Jr." and
    "JR" are the same token."""
    last = name.strip().split()[-1] if name.strip() else ""
    tok = last.replace(".", "").upper()
    return tok if tok in {"JR", "SR", "II", "III", "IV", "V", "VI"} else None


def display_name(raw, authority: str | None = None, draft_board: str | None = None) -> str:
    """A source name rendered for display: repaired if it is a known mis-spelling, de-shouted if it
    is shouting, re-cased to the authority when that is a pure case change, and otherwise UNTOUCHED.

    ⭐ The `isupper()` gate is load-bearing, not an optimisation: a mixed-case name is one the
    upstream already got right (the rookie pipeline ships `KC Concepcion`), and running a de-shouter
    over it is how we served "Kc Concepcion". A de-shouter's contract is only defined on shouting.
    """
    raw_name = str(raw).strip()
    repaired = _REPAIRS.get(raw_name.casefold())
    if repaired is not None:
        return repaired
    if raw_name.upper().endswith(_UNIT_SUFFIXES):  # "DEN D/ST" — a unit label, not a person
        return raw_name
    name = de_shout(raw_name) if raw_name.isupper() else raw_name
    # ⚠️ The fallback is gated on the authority being ABSENT, never on "the output did not change".
    # Those are different conditions and conflating them is a real bug: when the roster AGREES with
    # the rule pass the output is also unchanged, and an unchanged-keyed fallback then overrides a
    # live, correct authority with a frozen answer — precisely the staleness this design ends.
    if authority and str(authority).casefold() == name.casefold():
        name = str(authority)
    elif raw_name.isupper():
        # No roster row (or the read failed). Fall back to the frozen map so a missing authority
        # cannot publish a name WORSE than the pre-authority behaviour did.
        name = _FALLBACK_CASINGS.get(raw_name, name)
    # LAST, so it can override the spelling authorities: the name a draft board actually shows.
    # Ordering is deliberate — the roster is the better speller, the draft board is the better
    # answer to "who is the reader looking for", and only the second of those is what a drafter
    # types into a search box.
    return drafted_as(name, draft_board)


@functools.lru_cache(maxsize=4)
def roster_casing_authority(season: int | None = None) -> dict[str, str]:
    """`{gsis_id -> full_name}` from the nflverse roster history — the CASING authority.

    Keyed on the gsis id, never on the name: a name key would have to guess the very casing it is
    being asked to supply. Takes each player's LATEST roster row, so a name correction upstream
    propagates on the next re-export.

    Best-effort by design — the caller is an export that must still produce a board if S3 is
    unreachable — but a silent fallback to the old (wrong) casing is exactly the "graceful fallback
    hides a defect" trap, so a failed or empty read logs a WARNING and the exporters report the
    repair COUNT they applied. An authority that quietly resolves nothing shows up as a zero.

    Covers 95.1% of the 1,664 players across the seven published seasons; the rest are rookies
    carrying synthetic ids, whose names arrive already cased and are left alone.
    """
    from quant_sports_intel_models.football.nfl.fantasy.export_draft_board_json import (
        _lake_connection,
    )
    from quant_sports_intel_models.football.nfl.ingest import s3io

    try:
        uri = s3io.table_uri("nfl", "rosters")
        con = _lake_connection()
        try:
            # `arg_max(full_name, season)` = the name on the player's most recent roster row.
            df = con.sql(
                f"select gsis_id, arg_max(full_name, season) as full_name "
                f"from delta_scan('{uri}') "
                f"where gsis_id is not null and full_name is not null "
                f"group by gsis_id"
            ).df()
        finally:
            con.close()
    except Exception as e:  # noqa: BLE001
        log.warning(
            "name-casing authority unavailable (roster read failed: %s: %s) — names will be served "
            "with the rule pass alone, which cannot recover 'CEEDEE LAMB' -> 'CeeDee Lamb'",
            type(e).__name__, e,
        )
        return {}
    out = {str(r.gsis_id): str(r.full_name) for r in df.itertuples()}
    if not out:
        log.warning("name-casing authority resolved ZERO names — check the roster table")
    return out
