"""schools.py — college school-name normalization for the NCAAF join (NF-W9-0).

WHY THIS EXISTS AS ITS OWN MODULE. The NCAAF player join is blocked on the SCHOOL, so the school
key IS the join. `nfl.entity.names.normalize_team` cannot do this job — it is an NFL alias-code
folder (`ARZ`→`ARI`) that merely upper-cases anything it does not recognise, so it leaves
`Ole Miss` ≠ `Mississippi`, `San José State` ≠ `San Jose State` and `Miami (OH)` ≠ `Miami OH`.
Feeding college names through it produces a join that fails on exactly the schools whose names
vendors disagree about — the NF-W3 franchise-code class, where an uncanonicalized team key
silently drops real rows.

⛔ AND IT IS DELIBERATELY *NOT* A CHANGE TO `normalize_team`. That function is shared with the
NFL snap/props legs, which are already validated against the live lake; widening it to swallow
college names would move a validated join for an unrelated story's benefit. A new key for a new
population is the safe shape.

MEASURED (CFBD 2024 roster, live lake): 308 distinct schools, 22 carrying punctuation or
accents. `school_key` folds those deterministically. The ALIAS map on top is for genuinely
different NAMES for one school (`Ole Miss` / `Mississippi`), which no amount of character
folding can reconcile — it is seeded from the known offenders and is EXPECTED to grow when the
operator's probe reports its unmatched schools. That growth is the point: an unmatched school is
reported, not silently dropped, so the residual is a work item rather than a mystery.
"""
from __future__ import annotations

import re
import unicodedata

# Genuinely different names for one school. Both sides are stored already-folded so a lookup is
# a single pass. Seeded from the classic vendor disagreements; extend from the probe's report.
SCHOOL_ALIASES: dict[str, str] = {
    "mississippi": "ole miss",
    "southern california": "usc",
    "southern cal": "usc",
    "pitt": "pittsburgh",
    "uconn": "connecticut",
    "umass": "massachusetts",
    "ucf": "central florida",
    "usf": "south florida",
    "utsa": "texas san antonio",
    "utep": "texas el paso",
    "ul monroe": "louisiana monroe",
    "ulm": "louisiana monroe",
    "louisiana lafayette": "louisiana",
    "nc state": "north carolina state",
    "north carolina st": "north carolina state",
    "miami fl": "miami",
    "miami florida": "miami",
    "texas am": "texas a m",
    "hawaii": "hawai i",

    # ── MEASURED from the first live NCAAF probe (2025 wk11, 116 games / 5,034 rows). Every
    # entry was VERIFIED to exist in the CFBD roster under the mapped name — the designed
    # workflow: an unmatched school is reported, checked against CFBD, then keyed.
    # (a) PFF appends "State" where CFBD does not. ⛔ NOT a blanket rule — measured, `Ohio` /
    #     `Ohio State`, `Michigan` / `Michigan State` and `Florida` / `Florida State` ALL
    #     coexist in CFBD as distinct schools, so stripping "State" wholesale would merge real
    #     rivals. Only added where CFBD has the BASE and NOT the "State" form.
    "central connecticut state": "central connecticut",
    "grambling state": "grambling",
    "mcneese state": "mcneese",
    "sam houston state": "sam houston",
    # (b) CFBD's preferred short/long form differs from PFF's.
    "albany": "ualbany",
    "appalachian state": "app state",
    "southeastern louisiana": "se louisiana",
    "st thomas": "st thomas mn",
    "tennessee martin": "ut martin",
    "liu": "long island",
    "virginia military institute": "vmi",
    "virginia lynchburg": "virginia of lynchburg",
    # (c) A TYPO on PFF's side: "Rio Grand" for "Rio Grande". Aliased rather than fuzzy-matched
    #     — a typo is a fact about the feed, and pinning it keeps the join exact.
    "ut rio grand valley": "ut rio grande valley",
}

_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_SUFFIX_RE = re.compile(r"\b(university|college|the)\b")
# `Ohio St` → `Ohio State`. Anchored at the END on purpose: a LEADING `St` is *Saint*
# (`St. Francis`), so an unanchored expansion would turn `st francis` into `state francis` —
# a systematic convention and a homograph, handled by position rather than by a word list.
_TRAILING_ST_RE = re.compile(r"\bst$")


def school_key(name: str | None) -> str:
    """A deterministic, accent- and punctuation-free join key for a college school name.

    `San José State` → `san jose state`; `Miami (OH)` → `miami oh`; `Texas A&M` → `texas a m`.
    Aliases are applied AFTER folding so both sides of the map are reached the same way.
    """
    if name is None:
        return ""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = _SUFFIX_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s).strip()
    s = re.sub(r"\s+", " ", s)
    s = _TRAILING_ST_RE.sub("state", s).strip()
    return SCHOOL_ALIASES.get(s, s)
