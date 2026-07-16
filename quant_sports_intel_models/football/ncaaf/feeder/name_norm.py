"""name_norm.py  (NCAAF-P0.3 — shared player-name normalisation)
================================================================
The 2–8% surname disagreement in the draft-slot match (ncaaf_data_inventory.md §4.2) is
NOT a bad key — it is name-formatting noise: suffixes (`Jr.`/`III`), apostrophes
(`Ka'imi`), accents (`José`), and punctuation (`T.J.`). Both the surname-agreement
VALIDATION (which proves the slot key is sound independently of the join) and the UDFA
FUZZY match need the two name systems normalised the SAME way, or the comparison is noise.

This module is the single source of that normalisation, expressed two ways so the Python
build path (`xref.py`) and any dbt-SQL path share one definition:

  • `normalize_name(s)`        — pure Python (unit-tested; used nowhere hot, but the spec).
  • `norm_full_sql(col)`       — a DuckDB SQL expression normalising a name column.
  • `norm_last_sql(col)`       — the normalised LAST token (surname) of a name column.

Normalisation = lower → strip accents → drop apostrophes/periods → non-alphanumeric to a
single space → drop trailing generational suffix tokens (jr/sr/ii/iii/iv/v) → collapse
whitespace. It is deliberately conservative: it never reorders tokens or drops middle
names, so `norm_full` stays a faithful full-name key and only the KNOWN noise is removed.
"""
from __future__ import annotations

import re
import unicodedata

# Generational suffixes that appear as trailing tokens and are pure formatting noise for a
# name match. Kept as a shared constant so the Python + SQL paths agree exactly.
SUFFIX_TOKENS = ("jr", "sr", "ii", "iii", "iv", "v")

_SUFFIX_RE = re.compile(r"\b(?:%s)\b" % "|".join(SUFFIX_TOKENS))
_APOS_RE = re.compile(r"[.'`’]")          # . ' ` and the unicode right-single-quote
_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def normalize_name(s: str | None) -> str:
    """Normalise a full player name to the shared comparison key (pure Python spec).

    Example: "T.J. Watt Jr." → "tj watt"; "Ka'imi Fairbairn" → "kaimi fairbairn";
    "José Ramírez III" → "jose ramirez".
    """
    if not s:
        return ""
    # strip accents (NFKD → drop combining marks), lowercase
    decomposed = unicodedata.normalize("NFKD", str(s))
    ascii_str = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    ascii_str = _APOS_RE.sub("", ascii_str)        # drop apostrophes/periods FIRST (T.J.→tj)
    ascii_str = _NONALNUM_RE.sub(" ", ascii_str)   # any other punctuation → space
    ascii_str = _SUFFIX_RE.sub(" ", ascii_str)     # drop generational suffix tokens
    return _WS_RE.sub(" ", ascii_str).strip()


def normalize_last(s: str | None) -> str:
    """The normalised surname (last token of the normalised full name)."""
    full = normalize_name(s)
    return full.rsplit(" ", 1)[-1] if full else ""


# ── DuckDB SQL expressions (the hot path — xref.py builds over Delta with these) ─────────
def norm_full_sql(col: str) -> str:
    """A DuckDB expression normalising `col` to the shared full-name key.

    Mirrors `normalize_name` step-for-step:
      strip_accents · lower · drop . ' ` → drop other punctuation → drop suffix tokens →
      collapse whitespace · trim.
    (`strip_accents` handles the accent fold; DuckDB has no NFKD but strip_accents suffices
    for Latin-1 player names. Regexes use the 'g' global flag.)
    """
    suffix_alt = "|".join(SUFFIX_TOKENS)
    return (
        "trim(regexp_replace("
        "regexp_replace("
        "regexp_replace("
        "regexp_replace("
        f"lower(strip_accents(cast({col} as varchar))), "
        r"'[.''`’]', '', 'g'), "          # drop . ' ` ’
        r"'[^a-z0-9]+', ' ', 'g'), "            # non-alnum → space
        rf"'\b({suffix_alt})\b', ' ', 'g'), "   # drop suffix tokens (jr/sr/ii/…)
        r"'\s+', ' ', 'g'))"                     # collapse whitespace
    )


def norm_last_sql(col: str) -> str:
    """A DuckDB expression for the normalised surname (last alphanumeric token of the
    normalised full name). Used for the independent surname-agreement validation + as the
    UDFA fuzzy-match blocking key."""
    return f"regexp_extract({norm_full_sql(col)}, '([a-z0-9]+)$', 1)"
