"""E9.56b — guards for the PUBLIC (locked-view) fantasy surfaces.

There is no JS unit-test runner in this repo (`frontend/package.json` has no `test` script), so
frontend invariants are pinned by SOURCE INSPECTION from the Python fast gate — the same convention
as `test_nf_c0_platform_import.py` / `test_nf_c0b_league_settings.py`.

⚠️ THE FIXTURE IS REAL PRODUCTION DATA, and that is the point. `fixtures/
e9_56b_locked_projections_sample.json` is a verbatim trim of what
`GET /fantasy/nfl/projections?season=2026` returned to an UNAUTHENTICATED caller on 2026-08-05.
A hand-written fixture would encode the author's ASSUMPTION about which fields survive redaction —
which is exactly the assumption that has to be tested, because the components below break on the
*absence* of fields, and TypeScript cannot see it (`pts`/`fpPpr` are already typed `number | null`,
so a missing field type-checks and produces `NaN`/an empty table at runtime).

Two real defects were found by auditing the components against this fixture, both of which would
have shipped a broken free page and neither of which errors:
  • `rankings-board` filtered `p.pts != null` → on a locked board that drops ALL 858 rows → a
    completely blank page for every free visitor.
  • both tables sorted by a model column → `-Infinity - -Infinity` / `undefined - undefined` = NaN
    on every pair. `Array.sort` treats a NaN comparator as 0, so it *happens* to leave the server's
    ADP order intact — undefined-behaviour-by-luck on the exact ordering that E9.56's anti-scrape
    rule depends on.

⚠️ EVERY SOURCE ASSERTION STRIPS COMMENTS FIRST. Without that, the explanatory comment written above
each fix would satisfy the guard on source with the fix DELETED — the INC-38 "prose cannot satisfy a
source guard" landmine, which this repo has already shipped once.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_FRONTEND = Path("frontend")
_FIXTURE = Path(__file__).parent / "fixtures" / "e9_56b_locked_projections_sample.json"

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")


def _src(rel: str) -> str:
    return (_FRONTEND / rel).read_text()


def _code(rel: str) -> str:
    """Source with `//` line comments and `/* */` blocks stripped — see the module docstring."""
    text = _src(rel)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\{\s*/\*.*?\*/\s*\}", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


# ── the fixture is what we think it is ───────────────────────────────────────────────────────────

_MODEL_FIELDS = [
    "fpStd", "fpHalf", "fpPpr", "fpSd", "fpP10", "fpP90", "g", "conf", "uncType",
    "contrib", "mktLean", "lowPred", "predNote", "passYds", "passTd", "rushYds",
    "pts", "vor", "posRank", "ovrRank", "repl",
]


def _fixture() -> dict:
    return json.loads(_FIXTURE.read_text())


def test_the_real_locked_payload_carries_no_model_field():
    """Grounds every assertion below: these fields really are ABSENT, not null."""
    data = _fixture()
    assert data["locked"] is True and data["entitled"] is False
    for row in data["players"]:
        for f in _MODEL_FIELDS:
            assert f not in row, f"{f} present in a real locked row — redaction changed upstream"


def test_the_real_locked_payload_has_a_large_undrafted_tail():
    """The premise of `trimLockedTail`. If this ever stops being true the trim is pointless — and
    a trim that silently does nothing is worse than none, because the UI still claims a count."""
    rows = _fixture()["players"]
    undrafted = [r for r in rows if not isinstance(r.get("adp"), (int, float))]
    assert undrafted, "no undrafted rows in the sample — re-check the fixture provenance"


# ── the public set is EXACTLY two pages ──────────────────────────────────────────────────────────


def _pages_using(guard: str) -> set[str]:
    return {
        str(p.relative_to(_FRONTEND)).replace("\\", "/")
        for p in (_FRONTEND / "app").rglob("page.tsx")
        if re.search(rf"<{guard}\b", _code(str(p.relative_to(_FRONTEND))))
    }


# 🗄️ MOVED, NOT DELETED (freemium build, 2026-08-08). The "which pages are public" and "the nav
# marks exactly those public" invariants now live in `test_freemium_tier.py`, which owns the tier —
# it added Player Search to the free set and has the matching PAID list beside it.
#
# ⭐ THEY ARE NOT RESTATED HERE, DELIBERATELY. Two files asserting the same membership can disagree,
# and when they do the one a session happens to read first wins — the "one logical thing, many
# owners" shape (INC-38) that this repo keeps paying for. One owner, and a pointer.


# ── the cache-poisoning guard ────────────────────────────────────────────────────────────────────


def test_the_entitlement_is_part_of_every_dual_mode_query_key():
    """🚨 Without this, a subscriber is stranded on the LOCKED view after logging in.

    These queries are `staleTime: Infinity`, and `queryClient.clear()` runs on SIGN-OUT ONLY —
    `onLoginSuccess` does not clear it. So a logged-out visitor caches the locked payload, then
    subscribes, and the cache is never invalidated. It presents as "the paywall is broken", with no
    error anywhere. This could not happen before E9.56b, because `enabled: false` meant nothing was
    ever cached un-entitled — i.e. removing that gate is what introduces it."""
    code = _code("lib/fantasy-queries.ts")
    for key in ("nfl-fantasy-manifest", "nfl-fantasy-projections", "nfl-fantasy-board"):
        m = re.search(rf'queryKey:\s*\[[^\]]*"{re.escape(key)}"[^\]]*\]', code)
        assert m, f"queryKey for {key} not found"
        assert "entitled" in m.group(0), (
            f"{key} queryKey omits `entitled` — a new subscriber will be served the cached "
            f"LOCKED payload indefinitely"
        )


def test_the_three_board_hooks_no_longer_gate_on_entitlement():
    """The un-gating itself. With `enabled: canAccess(...)` still present the fetch never fires for
    a free user, `data === undefined`, and the surface renders its "not available yet" EMPTY STATE
    — which reads as unpublished content, not as a paywall. Silent, and the whole bug this fixes."""
    code = _code("lib/fantasy-queries.ts")
    manifest_to_projections = code[
        code.index("export function useFantasyManifest") : code.index("useSavedLeagues")
        if "useSavedLeagues" in code
        else len(code)
    ]
    assert 'enabled: canAccess("fantasy"' not in manifest_to_projections, (
        "a board hook still gates its fetch on entitlement"
    )


# ── the two NaN-class defects the real payload exposed ───────────────────────────────────────────


def test_the_rankings_board_does_not_drop_every_locked_row():
    """`p.pts != null` on a locked board drops ALL rows → a blank page for every free visitor."""
    code = _code("components/fantasy/rankings-board.tsx")
    assert "boardLocked || p.pts != null" in code, (
        "the rankings board filters on `pts != null` without a locked escape — a locked board has "
        "no `pts` on any row, so this renders EMPTY for every free visitor"
    )


@pytest.mark.parametrize(
    "path,marker",
    [
        ("components/fantasy/projections-table.tsx", "locked\n      ? scoped"),
        ("components/fantasy/rankings-board.tsx", "if (boardLocked) return scoped"),
    ],
)
def test_neither_table_sorts_a_locked_view_by_a_model_column(path, marker):
    """A locked row has no model column, so the comparators evaluate to NaN on every pair. Sort
    treats that as 0 and leaves the server's ADP order intact — which is right by accident, on the
    exact ordering E9.56's anti-scrape rule depends on. Both tables must skip the sort explicitly."""
    code = _code(path).replace("\r\n", "\n")
    assert marker.replace("\n      ", "") in code.replace("\n      ", ""), (
        f"{path} does not skip its sort on a locked view"
    )


def test_the_trim_reports_what_it_hid_rather_than_dropping_it_silently():
    """A truncation the user is not told about is a missing-data bug; one that states its count is
    a conversion prompt. Both tables must render `hiddenCount`."""
    for path in (
        "components/fantasy/projections-table.tsx",
        "components/fantasy/rankings-board.tsx",
    ):
        code = _code(path)
        assert "trimLockedTail" in code or "hiddenCount" in code, f"{path} does not trim"
        assert "hiddenCount > 0" in code, f"{path} hides rows without stating the count"


# ── nav + SEO posture ────────────────────────────────────────────────────────────────────────────


# (the nav-membership guard moved to `test_freemium_tier.py` with the page-set guard above)


@pytest.mark.parametrize("surface", ["projections", "rankings"])
def test_the_indexing_decision_is_explicit(surface):
    """PM gate: 'decide it, don't discover it in Search Console.' Operator decision 2026-08-05 was
    INDEX. What matters for the guard is that the posture is STATED — an inherited default is the
    thing this is meant to prevent."""
    code = _code(f"app/fantasy/{surface}/layout.tsx")
    assert "robots" in code and "index" in code, f"{surface} has no explicit robots directive"
    assert "canonical" in code, f"{surface} has no canonical URL"
