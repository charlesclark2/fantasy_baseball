"""guards.py — the "RAW STATS ONLY" boundary, enforced in code (NF-W9-0).

THE RULE (operator, NF-W9-0): PFF's raw counting stats are data; PFF's **projections,
grades, rankings and mock drafts are a competitor's MODEL OUTPUT**. Consuming the latter
would launder someone else's model into ours and would make every downstream §0.5 verdict
uninterpretable — a "win" could just be PFF's model showing through. A single validated
graded feature is a later, EXPLICIT decision; it is not something a probe drifts into.

TWO SEPARATE ENFORCEMENT POINTS, because the risk arrives two different ways:

  1. ENDPOINT REFUSAL (`assert_endpoint_allowed`) — a whole tool we must not touch
     (`/projections`, `/rankings`, `/mock-draft`, the reporting suite). Refusing the URL is
     the only way to be sure we never *fetch* it.

  2. COLUMN STRIP (`strip_model_output_columns`) — the one that actually bites. A perfectly
     legitimate raw facet (`rushing/summary`) ships PFF's per-player GRADES inline with the
     carries and yards. Refusing the endpoint would throw away the raw stats we came for; so
     we keep the row and DROP the graded columns — and RECORD what we dropped, because a
     silent strip is indistinguishable from "PFF didn't send any grades", and those are very
     different facts (the repo's silent-empty class).

⚠️ THE MATCH IS TOKEN-BOUNDED, NOT A SUBSTRING. NF-W7 shipped a banned-token scan that
false-fired on `'temp' ⊂ 'attempt'`, making a kicker story unable to say "attempt". The same
trap is live here and worse: a raw substring `"grade"` also matches **`downgrade`**, and
`"rank"` matches **`franchise`**. We therefore split the column name into `[a-z0-9]+` tokens
and require a WHOLE-TOKEN hit, which is why `pass_grades_rate` is dropped (token `grades`)
while `yards_after_contact` and `franchise_id` survive.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

log = logging.getLogger("pff.guards")

# Whole-token markers of a PFF MODEL OUTPUT column. Kept deliberately small and specific:
# every entry here is a thing PFF *derives*, never a thing that happened on the field.
MODEL_OUTPUT_TOKENS: frozenset[str] = frozenset({
    "grade", "grades", "graded",
    "projection", "projections", "projected", "proj",
    "rank", "ranks", "ranking", "rankings",
    "war", "wins",           # PFF WAR / wins-above-replacement style derivations
    "forecast", "forecasts",
    "predicted", "prediction", "predictions",
})

# Endpoint path fragments we must never fetch at all (whole-token, same reason as above).
FORBIDDEN_ENDPOINT_TOKENS: frozenset[str] = frozenset({
    "projections", "projection",
    "rankings", "ranking",
    "mock", "mockdraft",
    "grades",            # a grades-ONLY facet is model output end to end; a raw facet that
                         # merely CARRIES grade columns is fine — those get stripped instead.
    "bigboard",
    "forecast", "forecasts",
})

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ForbiddenEndpointError(RuntimeError):
    """Raised when a caller asks for a PFF model-output endpoint (never caught internally)."""


def tokenize(name: str | None) -> list[str]:
    """Split an identifier into lowercase alphanumeric tokens.

    `pass_grades_rate` → `['pass','grades','rate']`; `downgrade` → `['downgrade']` (ONE token,
    so it can never match `grade` — this is the whole point of tokenizing rather than
    substring-matching).
    """
    return _TOKEN_RE.findall((name or "").lower())


def is_model_output_column(column: str | None) -> bool:
    """True when `column` carries a whole-token model-output marker."""
    return any(t in MODEL_OUTPUT_TOKENS for t in tokenize(column))


def assert_endpoint_allowed(url_or_path: str) -> None:
    """Refuse a PFF model-output endpoint outright.

    Only the PATH is scanned — a query string may legitimately carry e.g. `sort=grade` on an
    otherwise-raw facet, and refusing on that would block raw data for a display parameter.
    """
    path = urlsplit(url_or_path).path or url_or_path
    hits = sorted({t for t in tokenize(path) if t in FORBIDDEN_ENDPOINT_TOKENS})
    if hits:
        raise ForbiddenEndpointError(
            f"Refusing PFF endpoint {url_or_path!r}: it is model output (matched {hits}). "
            "NF-W9-0 is RAW STATS ONLY — PFF's projections/grades/rankings are a competitor's "
            "model and must not be laundered into ours. Consuming a graded feature is a "
            "separate, explicit decision, not a probe side-effect."
        )


def strip_model_output_columns(columns) -> tuple[list[str], list[str]]:
    """Partition `columns` into `(kept, dropped)` by the whole-token rule.

    Returned as a PAIR so the caller can RECORD the dropped list. "We stripped 9 grade
    columns" and "PFF sent no grade columns" must never look the same in the artifact.
    """
    kept, dropped = [], []
    for c in columns:
        (dropped if is_model_output_column(c) else kept).append(c)
    return kept, dropped
