"""NF-C6P2 — the guards that live OUTSIDE the browser suite.

The roster report's arithmetic and render are asserted end-to-end in
`frontend/e2e/specs/fantasy-roster-report.spec.ts`, every clause RED-proven through
`e2e/red-proof.mjs`. What is pinned HERE is the class of thing a browser cannot see:

  1. THE E2E REGISTRIES ARE EXHAUSTIVE. Two hand-maintained lists decide which surfaces get gate
     coverage. A nav item added to the menu but to neither list is asserted reachable nowhere and
     asserted withheld nowhere — the registry-drift shape INC-38 records, and a green suite is
     exactly what it looks like.
  2. THE REPORT SCORES NOTHING. The repo already carries three implementations of one scoring
     policy, pinned against each other by `test_nf_epic1_parity.py`. A fourth would inherit that
     whole tax silently, and it would arrive as a helpful-looking `pts = weight * stat` in the
     aggregator rather than as a decision anybody made.
  3. THE REPORT ISSUES NO WIDE READ. `lakehouse_query` in the API Lambda fails SILENTLY and returns
     `[]` (E9.26b), so a panel built on one renders empty with no error anywhere.

Pure source inspection (fast gate): no browser, no network, no `pipeline` import.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"

NAV_MODEL = FRONTEND / "lib/nav-model.ts"
REPORT_LIB = FRONTEND / "lib/roster-report.ts"
REPORT_COMPONENT = FRONTEND / "components/fantasy/roster-report.tsx"
FREE_LEAGUE_SPEC = FRONTEND / "e2e/specs/free-league.spec.ts"
GATES_SPEC = FRONTEND / "e2e/specs/fantasy-entitlement-gates.spec.ts"


def _strip_comments(src: str) -> str:
    """Line comments BEFORE block comments — a `//` inside a `/* */` is prose, and stripping blocks
    first would leave the line stripper eating real code that follows on the same line.

    ⚠️ This is what stops a source guard being satisfied by a COMMENT (INC-38: a fix whose only
    evidence was the explanatory comment written above it).
    """
    src = re.sub(r"//[^\n]*", "", src)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _free_signed_in_hrefs() -> list[str]:
    """Every nav item carrying `freeSignedIn: true`, by href, read from the SHIPPING nav model."""
    src = _strip_comments(NAV_MODEL.read_text())
    # Items are object literals; `href` precedes `freeSignedIn` in every one. Matching the pair
    # together (rather than collecting hrefs and flags separately) is what keeps a flag from being
    # attributed to the wrong item when the file is reordered.
    return re.findall(r'href:\s*"([^"]+)"[^}]*?freeSignedIn:\s*true', src, flags=re.S)


def test_the_nav_model_actually_declares_free_signed_in_items():
    """⚠️ NON-VACUITY FIRST. Every assertion below iterates this list, so an empty one would make
    them all pass on nothing — the guard-that-cannot-fail class, arriving through the fixture rather
    than through the clause."""
    hrefs = _free_signed_in_hrefs()
    assert len(hrefs) >= 4, f"the freeSignedIn extraction found {hrefs} — the regex has gone stale"
    assert "/fantasy/roster-report" in hrefs, "the roster report is not a freeSignedIn nav item"


def test_every_free_signed_in_nav_item_is_in_both_registries():
    """⭐ THE REGISTRY GUARD. `free-league.spec.ts` asserts these hrefs ARE offered to a signed-in
    free account and are NOT offered to a stranger; `fantasy-entitlement-gates.spec.ts` asserts the
    gate each one sits behind. Both lists are hand-written, so a new item joins neither by default —
    and the E2E suite stays green while covering one surface fewer.

    ⚠️ Asserted against the LISTS rather than against the whole file, so a passing mention in a
    comment or an unrelated `page.goto` cannot satisfy it."""
    hrefs = _free_signed_in_hrefs()

    league_nav = _strip_comments(FREE_LEAGUE_SPEC.read_text())
    block = league_nav[league_nav.index("LEAGUE_NAV_HREFS") :]
    block = block[: block.index("]")]
    missing_nav = [h for h in hrefs if h not in block]
    assert not missing_nav, (
        f"freeSignedIn nav items missing from free-league.spec.ts's LEAGUE_NAV_HREFS: {missing_nav}. "
        "They are asserted reachable nowhere and asserted withheld nowhere."
    )

    gates = _strip_comments(GATES_SPEC.read_text())
    gated = gates[gates.index("GATED_SURFACES") :]
    gated = gated[: gated.index("] as const")]
    missing_gate = [h for h in hrefs if h not in gated]
    assert not missing_gate, (
        f"freeSignedIn nav items missing from fantasy-entitlement-gates.spec.ts's GATED_SURFACES: "
        f"{missing_gate}. Nothing asserts which gate they sit behind."
    )


def test_the_report_does_not_become_a_fourth_scorer():
    """⛔ THE AGGREGATOR MULTIPLIES NO STAT BY NO WEIGHT.

    `fantasy_engine` (the authority), `lib/league-scoring.ts` and the Lambda's `league_scoring.py`
    are three implementations of one policy, and `test_nf_epic1_parity.py` is a merge gate holding
    them together. A fourth would inherit that tax without anybody deciding to — and it cannot work
    anyway: the raw stat line is PAID and never reaches this browser (NF-EPIC 1), so a scorer here
    would silently produce zeros while reporting itself as covered.

    Keyed on the scoring VOCABULARY rather than on arithmetic in general: the module is nothing but
    sums and ratios, so forbidding multiplication would forbid the module."""
    src = _strip_comments(REPORT_LIB.read_text()) + _strip_comments(REPORT_COMPONENT.read_text())
    for token in ("per_stat", "STAT_FIELD", "resolveScoring", "resolve_scoring", "buildBoard"):
        assert token not in src, (
            f"{token!r} appears in the roster report — it is re-deriving scoring rather than "
            "consuming the served board, which makes it a fourth implementation of the scoring policy"
        )


def test_the_report_issues_no_wide_lakehouse_read():
    """E9.26b. A wide `lakehouse_query` inside the API Lambda fails SILENTLY and comes back `[]`, so
    the panel renders empty with no error anywhere and no CloudWatch line. The report is built from
    ONE already-served payload; nothing here may reach for another source."""
    src = _strip_comments(REPORT_LIB.read_text())
    for token in ("lakehouse_query", "fetch(", "apiFetch", "useQuery"):
        assert token not in src, (
            f"{token!r} appears in roster-report.ts — the report must be a pure function of the "
            "already-fetched league-board payload"
        )


def test_the_upgrade_prompt_is_entitlement_gated_in_source():
    """⚠️ BELT AND BRACES ON A CLAUSE THE BROWSER ALREADY PROVES (and RED-proves). It is here because
    the render assertion is one `if` away from silently inverting, and selling a subscriber what they
    already pay for reads to them as a billing bug rather than as a missing feature."""
    src = _strip_comments(REPORT_COMPONENT.read_text())
    assert re.search(r"if\s*\(\s*entitled\s*\)\s*return null", src), (
        "UpgradePrompt no longer refuses to render for an entitled caller"
    )


@pytest.mark.parametrize(
    "reason",
    ["no-league", "no-team-linked", "not-drafted", "no-board", "nothing-matched"],
)
def test_each_empty_state_has_its_own_message(reason: str):
    """NF-C6 shipped the bug where two of these shared a message and told a user to redo something
    they had already done. Each reason must resolve to its own copy entry — parametrized so a
    missing one names ITSELF rather than failing a bundled assertion that could be satisfied by the
    other four (the `and`-composed-guard trap)."""
    copy = (FRONTEND / "lib/fantasy-claim-copy.ts").read_text()
    block = copy[copy.index("REPORT_EMPTY") :]
    block = block[: block.index("} as const")]
    assert f'"{reason}"' in block, f"the {reason!r} empty state has no message of its own"
