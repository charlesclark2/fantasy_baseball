"""names.py — NF-W0b: the normalization primitives the ladder's tiers 3–4 are built on.

Three things vendors disagree about, each handled separately because each fails differently:

  • NAME formatting — suffixes (`Jr.`/`II`), apostrophes (`Ka'imi`), accents (`José`), initials
    (`T.J.`). This is pure noise and is folded away by `normalize_name`, which DELEGATES to
    `football/ncaaf/feeder/name_norm` so the NFL and NCAAF sides of the football vertical cannot
    drift to two definitions of "the same name" (that module is already the shared spec and has
    a matching DuckDB-SQL expression for hot paths).

  • NAME *identity* — nicknames. `normalize_name` deliberately does NOT touch these: "Michael
    Woods II" → "michael woods" and "Mike Woods" → "mike woods" stay DIFFERENT strings, because
    collapsing nicknames by rule would silently merge genuinely different players. Nicknames are
    the job of the CONSTRAINED FUZZY rung (`jaro_winkler` inside a single team-week block), where
    a wrong merge is bounded by the block and reported at a lower confidence.

  • POSITION vocabulary — the vendors use different GRAINS, not different spellings. Measured on
    the 2024 lake: `snap_counts` writes T/G/C/NT/DE/DT/FS/SS/CB/FB (19 labels) while
    `weekly_rosters` writes OL/DL/DB (11 labels). So an exact `position = position` join is
    structurally wrong — it does not fail on a typo, it fails on EVERY offensive lineman. Folding
    both sides to a POSITION GROUP makes tier 3's constraint real instead of vacuous.

`jaro_winkler` is implemented here in pure Python (no new dependency) rather than reused from
DuckDB's `jaro_winkler_similarity`, because the resolver is pure pandas so it can be proven in
the offline fast gate. `test_nf_w0b_entity_resolution.py` pins it against the published
Winkler reference values so "our JW" cannot quietly drift into something else.
"""
from __future__ import annotations

import re

# The football-vertical shared name spec (suffixes/accents/punctuation). One definition, two
# sports — see the module docstring for why this is an import and not a copy.
from quant_sports_intel_models.football.ncaaf.feeder.name_norm import (
    normalize_last,
    normalize_name,
)

__all__ = [
    "GIVEN_NAME_ALIASES",
    "POSITION_GROUPS",
    "TEAM_ALIASES",
    "jaro_winkler",
    "normalize_for_matching",
    "normalize_last",
    "normalize_name",
    "normalize_team",
    "position_group",
    "strip_disambiguation",
]

# ── Vendor name-annotation cleaning (NF-W0b follow-on, PM decision Q1) ───────────────────────────
# A books feed disambiguates same-named players INLINE, in the display string: measured on the live
# 2023–24 Odds-API payload — "Michael (Saints) Thomas", "Lamar Jackson (BAL)", "Zach Ertz (Ari)",
# "Case Keenum (Hou)". The parenthetical is an ANNOTATION, never part of the name, so it is stripped
# before normalization; left in, `normalize_name` turns it into name TOKENS ("michael saints thomas")
# and the player can never match. 333 rows in the measured payload.
_PAREN_RE = re.compile(r"\s*\([^)]*\)")


def strip_disambiguation(s: str | None) -> str:
    """Drop parenthetical annotations from a vendor display name."""
    if not s:
        return ""
    return _PAREN_RE.sub(" ", str(s)).strip()


# GIVEN-NAME diminutives, applied to the FIRST token only (a nickname is a given name, not a
# surname). Seeded from the MEASURED residual of the live props payload, not from a general
# nickname corpus — every entry below is a real unresolved cohort with its row count.
#
# ⭐ WHY THIS IS SAFE, AND WHY THE DIRECTION DOES NOT MATTER: the map is applied SYMMETRICALLY to
# both the source and the target, so it cannot create a false pairing that survives — it can only
# make two strings agree. "Eli Manning" (legally Eli) maps to "elijah manning" on BOTH sides and
# still matches itself. And if aliasing ever DOES collapse two genuinely different players onto one
# name, the resolver's season-scope ambiguity rule makes both ABSTAIN rather than pick — so the
# worst case is a visible, queued miss, never a silent wrong merge.
#
# ⛔ IDIOSYNCRATIC aliases do NOT belong here — "Sauce" Gardner (Ahmad), "Chosen" Anderson (a legal
# name change from Robby) are not derivable by any rule. Those are exactly what tier 2's reviewed
# crosswalk is for. A rule-based map that tried to cover them would be a list of special cases
# masquerading as a rule.
GIVEN_NAME_ALIASES: dict[str, str] = {
    "gabe": "gabriel",      # Gabe/Gabriel Davis — 1,073 rows, the single largest cohort
    "chig": "chigoziem",    # Chig/Chigoziem Okonkwo — 851 rows across both spellings
    "mike": "michael",      # Mike/Michael Woods II (148), Mike/Michael Danna (23)
    "eli": "elijah",        # Eli/Elijah Mitchell — 22 rows
    "pat": "patrick",       # Pat/Patrick Surtain II — 16 rows
    "matt": "matthew",
    "matty": "matthew",
    "chris": "christopher",
    "joe": "joseph",
    "jody": "joseph",
    "dan": "daniel",
    "danny": "daniel",
    "tony": "anthony",
    "nick": "nicholas",
    "will": "william",
    "bill": "william",
    "billy": "william",
    "rob": "robert",
    "robby": "robert",
    "bobby": "robert",
    "bob": "robert",
    "jim": "james",
    "jimmy": "james",
    "tom": "thomas",
    "tommy": "thomas",
    "ben": "benjamin",
    "sam": "samuel",
    "greg": "gregory",
    "jeff": "jeffrey",
    "steve": "steven",
    "stephen": "steven",
    "ted": "theodore",
    "andy": "andrew",
    "drew": "andrew",
    "alex": "alexander",
    "zach": "zachary",
    "zack": "zachary",
    "josh": "joshua",
    "jake": "jacob",
    "dave": "david",
    "ken": "kenneth",
    "ron": "ronald",
    "tim": "timothy",
    "cam": "cameron",
    "brad": "bradley",
}


def normalize_for_matching(s: str | None, *, aliasing: bool = False) -> str:
    """The matching key: `normalize_name` after stripping vendor annotations, optionally with
    given-name aliasing folded in.

    `aliasing` is OPT-IN PER SOURCE (`ResolutionSpec.name_aliasing`) rather than global, because
    turning it on changes which rows a rung resolves — and the snap leg is already validated and
    must not move (NF-W0b PM decision: "do NOT touch the snap leg").
    """
    base = normalize_name(strip_disambiguation(s))
    if not aliasing or not base:
        return base
    head, _, rest = base.partition(" ")
    return f"{GIVEN_NAME_ALIASES.get(head, head)} {rest}".strip() if rest else GIVEN_NAME_ALIASES.get(head, head)

# Vendor position label → position GROUP. Keyed to the COARSER vocabulary (`weekly_rosters`), so a
# group is always a label some vendor actually emits. Any label not listed maps to itself upper-cased,
# which is the safe direction: an unknown label constrains to exactly itself and can only make tier 3
# STRICTER (it can never merge two players), so a new vendor label degrades to a tier-4 match rather
# than to a wrong tier-3 one.
POSITION_GROUPS: dict[str, str] = {
    # offensive line — the family that makes an exact position join fail wholesale
    "T": "OL", "OT": "OL", "LT": "OL", "RT": "OL",
    "G": "OL", "OG": "OL", "LG": "OL", "RG": "OL",
    "C": "OL", "OL": "OL",
    # defensive line
    "DE": "DL", "DT": "DL", "NT": "DL", "DL": "DL",
    # secondary
    "CB": "DB", "FS": "DB", "SS": "DB", "S": "DB", "DB": "DB",
    # linebackers (EDGE is charted as LB by the coarse feed)
    "LB": "LB", "ILB": "LB", "OLB": "LB", "MLB": "LB", "EDGE": "LB",
    # backfield — `weekly_rosters` carries no FB label; snap_counts does
    "RB": "RB", "FB": "RB", "HB": "RB",
    # unambiguous across both vocabularies
    "QB": "QB", "WR": "WR", "TE": "TE", "K": "K", "PK": "K", "P": "P", "LS": "LS",
}

# Franchise relocations / vendor abbreviation drift, mirroring the CASE already in
# `stg_nfl_weekly_rosters` so the Python and dbt paths agree on one team key.
TEAM_ALIASES: dict[str, str] = {
    "ARZ": "ARI", "CLV": "CLE", "HST": "HOU",
    "LA": "LAR", "SL": "LAR", "STL": "LAR",
    "SD": "LAC", "OAK": "LV", "BLT": "BAL",
    "WSH": "WAS", "WFT": "WAS",
}


def normalize_team(team: str | None) -> str:
    """Fold a vendor team code to the canonical one (`ARZ`→`ARI`, `OAK`→`LV`). Empty on missing."""
    if team is None:
        return ""
    t = str(team).strip().upper()
    return TEAM_ALIASES.get(t, t)


def position_group(position: str | None) -> str:
    """Fold a vendor position label to its position GROUP (`G`→`OL`, `FB`→`RB`).

    An unknown label returns itself upper-cased — see `POSITION_GROUPS` for why that direction is
    the safe one.
    """
    if position is None:
        return ""
    p = str(position).strip().upper()
    return POSITION_GROUPS.get(p, p)


def jaro_winkler(a: str, b: str, *, prefix_weight: float = 0.1) -> float:
    """Jaro-Winkler similarity in [0, 1] — the score the CONSTRAINED fuzzy rung ranks on.

    Standard definition: the Jaro similarity boosted by the length of the common prefix (capped at
    4) weighted by `prefix_weight`. Two empty strings score 1.0; one empty scores 0.0.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    la, lb = len(a), len(b)
    window = max(la, lb) // 2 - 1
    if window < 0:
        window = 0

    a_matched = [False] * la
    b_matched = [False] * lb
    matches = 0
    for i, ch in enumerate(a):
        lo = max(0, i - window)
        hi = min(i + window + 1, lb)
        for j in range(lo, hi):
            if b_matched[j] or b[j] != ch:
                continue
            a_matched[i] = b_matched[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0

    # transpositions = half the number of matched-but-out-of-order pairs
    transpositions = 0
    j = 0
    for i in range(la):
        if not a_matched[i]:
            continue
        while not b_matched[j]:
            j += 1
        if a[i] != b[j]:
            transpositions += 1
        j += 1
    transpositions //= 2

    m = float(matches)
    jaro = (m / la + m / lb + (m - transpositions) / m) / 3.0

    prefix = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca != cb:
            break
        prefix += 1
    return jaro + prefix * prefix_weight * (1.0 - jaro)
