"""NCAAF-P3.9 — the parts of the nav/logo/CI change a browser cannot see.

⭐ THIS FILE IS DELIBERATELY NARROW, and the boundary is the point. Everything about whether the
NCAAF door RENDERS, NAVIGATES and HIGHLIGHTS is asserted on the DOM by
`frontend/e2e/specs/ncaaf-nav-logos.spec.ts` and `ncaaf-games-mobile.spec.ts`, because NF-C4
measured eight frontend defects that were all green in CI precisely because the suite asserted on
SOURCE: a guard that greps a component proves somebody TYPED a string, never that the branch it
sits in renders for the visitor who needs it.

What is left over is the residue no browser can reach:

  1. A CROSS-FILE AGREEMENT. The same link is declared twice — `NCAAF_NAV` in `nav.tsx` (the
     signed-in, sport-first menu) and an entry in `SIGNED_OUT_NAV` (authored marketing navigation).
     `Track Record` already carries the identical duplication. Two owners of one logical thing is
     this repo's most-repeated defect class, so the agreement is PINNED rather than commented. Note
     what this does NOT claim: an E2E clause drives each menu separately and would catch either one
     being broken — what it could not catch is the two silently pointing at DIFFERENT places, since
     each spec only ever sees one of them.

  2. THE CI WIRING (finding ⑧). A workflow file's behaviour is not observable from inside a test
     run at all, and the defect being closed here is that a guard STOPPED BEING TRIGGERED — the
     E11.30 / NF-K1 shape, where the detection still exists and simply never runs.

  3. THE CSP ALLOWLIST. E9.46: a CSP refusal has NO server-side signal and, behind a fallback,
     presents identically to "there is no image for this team". A browser in the E2E harness never
     tells us either, because the shipped CSP header is not what a locally served build enforces on
     an intercepted route.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_FRONTEND = _REPO / "frontend"
_NAV_TSX = _FRONTEND / "components" / "nav.tsx"
_COPY_TS = _FRONTEND / "lib" / "positioning-copy.ts"
_FOOTER_TSX = _FRONTEND / "components" / "site-footer.tsx"
_NEXT_CONFIG = _FRONTEND / "next.config.mjs"
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(not _FRONTEND.is_dir(), reason="frontend/ not present")

_HREF = "/ncaaf/games"
_KEY = "ncaaf-games"


def _code(path: Path) -> str:
    """Source with `//` line comments and `/* */` blocks stripped.

    ⚠️ INC-38: without this, the explanatory comment written above each change satisfies the guard
    on source with the change itself deleted. This repo has shipped that exact vacuity once, and
    every clause below names strings that also appear in the prose beside them — so stripping is
    not hygiene here, it is the difference between a guard and a decoration."""
    text = path.read_text()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", ln) for ln in text.splitlines())


def _signed_out_nav_block() -> str:
    src = _code(_COPY_TS)
    assert "export const SIGNED_OUT_NAV" in src, "SIGNED_OUT_NAV is gone from positioning-copy.ts"
    block = src.split("export const SIGNED_OUT_NAV", 1)[1].split("\n]", 1)[0]
    # Anti-vacuity, the same shape E9.60's own clauses use: a bad slice would make every assertion
    # below pass on an empty string.
    assert block.count("href:") >= 5, (
        f"only {block.count('href:')} entries extracted from SIGNED_OUT_NAV — the slice is wrong "
        f"and every clause reading it is suspect"
    )
    return block


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The two declarations of one door
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_two_ncaaf_nav_declarations_agree():
    """`nav.tsx`'s `NCAAF_NAV` (signed-in) and `SIGNED_OUT_NAV`'s entry (signed-out) are the same
    door drawn from two different models. They must not drift apart: a reader who signs in would
    otherwise be handed a different destination than the one they were browsing."""
    nav = _code(_NAV_TSX)
    decl = re.search(r"const NCAAF_NAV\s*=\s*\{(.*?)\}", nav, re.S)
    assert decl, "nav.tsx no longer declares NCAAF_NAV — the signed-in door is gone"
    signed_in = decl.group(1)
    assert f'href: "{_HREF}"' in signed_in, f"the signed-in NCAAF door does not point at {_HREF}"
    assert f'key: "{_KEY}"' in signed_in, (
        f"the signed-in NCAAF door does not carry the {_KEY!r} key the page passes as `activeLink`"
    )

    block = _signed_out_nav_block()
    entries = [e for e in re.split(r"\},", block) if _HREF in e]
    assert entries, (
        "SIGNED_OUT_NAV has no NCAAF entry — an anonymous visitor is the DEFAULT reader of "
        "/ncaaf/games (it is free and unguarded), so the signed-in menu alone leaves the surface "
        "as unfindable as it was before this story"
    )
    assert len(entries) == 1, f"{len(entries)} NCAAF entries in SIGNED_OUT_NAV — one door, once"
    assert f'key: "{_KEY}"' in entries[0], (
        "the signed-out NCAAF entry carries no `key`, so the bar can never mark it current — and "
        "the signed-out bar is the one that renders on the board itself"
    )


def test_the_ncaaf_door_is_drawn_at_every_viewport_and_auth_state():
    """`Nav` renders FOUR menus (signed-out bar, signed-out phone panel, signed-in sub-nav,
    signed-in phone panel). The desktop halves are `hidden … sm:*` and the phone halves live behind
    the hamburger, so missing one is invisible to a reader at the other viewport — E9.58's second
    defect exactly.

    ⚠️ This counts `data-nav-item` SITES, not the string `/ncaaf/games`: the signed-in pair render
    `NCAAF_NAV.href`, so an href count would be blind to them."""
    nav = _code(_NAV_TSX)
    sites = nav.count("data-nav-item=")
    assert sites == 4, (
        f"{sites} nav render sites carry `data-nav-item` — expected 4 (signed-out bar, signed-out "
        f"phone menu, signed-in sub-nav, signed-in phone menu). A door missing from one of them is "
        f"invisible to any reader who is not at that viewport in that auth state."
    )
    # Both signed-in sites must read the shared constant rather than re-typing the URL.
    assert nav.count("NCAAF_NAV.href") == 2, (
        "a signed-in NCAAF link spells its own href instead of reading NCAAF_NAV — a third owner "
        "of one link"
    )


def test_the_signed_out_ncaaf_door_is_not_filed_under_the_mlb_product_key():
    """⛔ `product: "betting"` is the proxy TWO existing guards use for "an MLB door was re-added"
    (`test_e9_60_positioning_copy.py::test_the_signed_out_nav_has_no_mlb_door` and
    `positioning-alignment.spec.ts`'s "offers no MLB door"). Filing college football under it would
    turn both red for a reason unrelated to what they defend, and the tempting repair — relaxing the
    clause the operator marked ⛔ DO NOT DELETE — would quietly reopen the decision it records.

    The two products genuinely differ on the axis those guards care about: every MLB route refuses
    an anonymous caller, `/ncaaf/games` serves one."""
    entry = [e for e in re.split(r"\},", _signed_out_nav_block()) if _HREF in e]
    assert entry, "no NCAAF entry to check — this clause would be vacuous"
    assert 'product: "betting"' not in entry[0], (
        "the NCAAF door is filed under the MLB/betting product key; read the note on "
        "`SignedOutNavLink.product` before changing this"
    )
    assert 'product: "ncaaf"' in entry[0], "the NCAAF door carries no product group of its own"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The route and the footer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_bare_ncaaf_redirects_to_the_board_and_is_not_cached_forever():
    """⚠️ `permanent: false`. A 308 is cached by the browser essentially forever, so if `/ncaaf`
    later becomes a real hub (P3.3 team pages, P3.6 futures — both carded) every reader who once hit
    a permanent redirect would keep being bounced past it with no round-trip and no way for us to
    correct it. `/pricing` above it is permanent because that URL is a mistake being retired; this
    one is a placeholder we intend to fill."""
    cfg = _code(_NEXT_CONFIG)
    block = re.search(r"async redirects\(\)\s*\{(.*?)\n  \},", cfg, flags=re.S)
    assert block, "next.config.mjs no longer declares a redirects() block"
    rule = re.search(r'\{\s*source:\s*"/ncaaf",(.*?)\}', block.group(1), flags=re.S)
    assert rule, "a bare /ncaaf has no redirect — it 404s, which is the state P3.9 was opened on"
    assert f'destination: "{_HREF}"' in rule.group(1)
    assert "permanent: false" in rule.group(1), (
        "the /ncaaf redirect is permanent (308) — a browser will cache it past any future hub page"
    )


def test_the_footer_links_ncaaf_instead_of_calling_it_unbuilt():
    """The footer renders on EVERY page, so "Coming this season" over a product that shipped at P3.2
    was the site telling every visitor the opposite of the truth.

    ⚠️ BOTH HALVES. A presence-only assertion passes while the stale row is still there beside the
    new link, which is the likelier half-fix — and the "Coming this season" heading itself must
    SURVIVE, because NFL betting is genuinely unbuilt and deleting the group would be the repair
    overshooting."""
    src = _code(_FOOTER_TSX)
    products = src.split("const PRODUCTS", 1)[1].split("] as const", 1)[0]
    coming = src.split("const COMING", 1)[1].split("] as const", 1)[0]
    assert products.count("href:") >= 2, "the PRODUCTS slice is wrong — this clause would be vacuous"

    assert f'href: "{_HREF}"' in products, "the footer has no live NCAAF link"
    assert "NCAAF" not in coming, "NCAAF is still listed as 'Coming this season' — it is live"
    assert "NFL" in coming, (
        "the 'Coming this season' group is now empty; NFL betting is genuinely unbuilt and the "
        "group is what keeps an unshipped product honest"
    )


def test_the_espn_logo_host_is_allowlisted_by_the_csp():
    """E9.46, and it is the reason the fallback below it is not enough on its own: a CSP refusal has
    NO server-side signal and, behind an `onError` fallback, is indistinguishable from "this team
    has no mark". `static.www.nfl.com` was missing for as long as it existed for exactly that
    reason. `a.espncdn.com` is already listed (the MLB game page renders from it) — this pins that
    it stays listed now that a second surface depends on it."""
    # ⚠️ READ FROM THE RAW FILE, NOT `_code`. The `//` line-comment stripper this module uses
    # everywhere else would eat `https://a.espncdn.com` at its own `//` — a URL is not a comment,
    # and a stripper that cannot tell them apart turns this clause into a guaranteed failure. So the
    # comment defence is done the other way round here: locate the img-src LINE and refuse it if it
    # is itself commented out, which is the only way prose could satisfy this one.
    line = next(
        (ln for ln in _NEXT_CONFIG.read_text().splitlines() if '"img-src' in ln),
        None,
    )
    assert line, "the CSP declares no img-src"
    assert not line.lstrip().startswith(("//", "*")), "the img-src directive is commented out"
    assert "https://a.espncdn.com" in line, (
        "the ESPN logo host is not in the CSP img-src allowlist — every NCAAF team mark would be "
        "refused by the browser and render as the fallback, silently and product-wide"
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Finding ⑧ — the changelog guard runs on the PR class that edits the changelog
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ci() -> dict:
    return yaml.safe_load(_CI_YML.read_text())


def test_the_changelog_filter_selects_the_changelog_and_nothing_else():
    """⚠️ THE OBVIOUS EDIT IS THE CATASTROPHIC ONE, which is why this is pinned as its own clause.
    Under `predicate-quantifier: every` a file must match EVERY pattern in its list — so adding
    `frontend/data/changelog.json` to the `backend` filter would demand that `betting_ml/x.py` also
    match that path, resolving `backend` to FALSE for every backend file in the repo and silently
    disarming the entire Python gate."""
    ci = _ci()
    step = next(
        s for s in ci["jobs"]["changes"]["steps"] if str(s.get("uses", "")).startswith("dorny/")
    )
    assert step["with"]["predicate-quantifier"] == "every", (
        "E9.63b's `predicate-quantifier: every` is gone — without it the backend filter answers "
        "true for every possible diff"
    )
    filters = yaml.safe_load(step["with"]["filters"])
    assert filters["changelog"] == ["frontend/data/changelog.json"], (
        f"the changelog filter is {filters.get('changelog')!r}"
    )
    assert "frontend/data/changelog.json" not in filters["backend"], (
        "the changelog was added to the `backend` filter; under `every` that makes `backend` FALSE "
        "for every backend file in the repo — it disarms the whole Python gate rather than "
        "extending it"
    )
    assert ci["jobs"]["changes"]["outputs"]["changelog"], "the changes job does not export it"


def test_the_changelog_guard_job_is_gated_on_the_changelog_alone():
    """⚠️ `changelog == 'true'`, NEVER `backend || changelog`, on two counts.

    COVERAGE: the job is ADDITIVE — a backend PR still runs the same test inside the `guards` shard,
    so nothing moved out of the fast gate.

    PROVABILITY: this story's own PR edits `.github/workflows/ci.yml`, so `backend` is true on it.
    An `||` would make "the guard ran" true for the OLD reason and prove nothing about the new path
    — the spec asks for the guard to be shown RUNNING on this PR, and only a `changelog`-alone gate
    makes that observation mean anything."""
    job = _ci()["jobs"]["changelog-guard"]
    cond = job["if"]
    assert "changelog" in cond, "the changelog guard is not gated on the changelog filter"
    assert "backend" not in cond, (
        f"the changelog-guard job's `if:` reads {cond!r} — a `backend` term makes it fire for the "
        f"pre-existing reason and destroys the evidence that the new trigger works"
    )
    ran = " ".join(str(s.get("run", "")) for s in job["steps"])
    assert "test_changelog_guard.py" in ran, (
        "the changelog-guard job does not run the changelog guard — the trigger was fixed and "
        "wired to nothing (the NF-C0e wired-but-never-invoked shape)"
    )


def test_the_changelog_guard_is_inside_the_named_required_check():
    """⭐ A guard that runs red BESIDE the gate rather than INSIDE it leaves the named check green
    on a frontend-only PR — finding ⑧ moved one job over rather than fixed. `Unit Tests (fast gate)`
    is the name a required status check references (⛔ do not rename), so the roll-up is where the
    verdict has to land."""
    rollup = _ci()["jobs"]["unit-tests"]
    assert rollup["name"] == "Unit Tests (fast gate)", "the required check's name moved"
    assert "changelog-guard" in rollup["needs"], "the changelog guard is not a dependency of the gate"
    script = " ".join(str(s.get("run", "")) for s in rollup["steps"])
    assert "needs.changelog-guard.result" in script, (
        "the roll-up depends on the changelog guard but never reads its result — a dependency that "
        "cannot fail the gate is decoration"
    )
    # ⚠️ And it must be read the SAME way as the others: `skipped` is a pass (no changelog edit),
    # anything else is not. A clause that only checked for the string would pass on a job whose
    # result is collected and discarded.
    assert re.search(r'for r in .*\$CHANGELOG"', script), (
        "the changelog guard's result is not in the roll-up's pass/fail loop"
    )
