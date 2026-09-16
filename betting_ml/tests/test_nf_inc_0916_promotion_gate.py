"""NF-INC-0916 — THE PROMOTION GATE: an announcement may not ship while its subject is withheld.

══ WHAT THIS EXISTS TO PREVENT, AND WHY A HUMAN REMEMBERING IS NOT ENOUGH ════════════════════════

The weekly model's two training feeds were never ingested, so it fitted a week of fabricated zeros
and its served point runs at roughly a third of realized scoring. `frontend/lib/weekly-suppression`
therefore withholds every number that fit produced — the point, the band, the rest-of-season
figures and the paid per-stat line.

At the same moment, `dev` carried a changelog entry announcing that the weekly stat line now
projects touchdowns. Both statements are individually true. Shipping them together tells a reader
about a stat line the same release is refusing to show him.

⭐ AND THE PROMOTION IS ONE CLICK. `orchestration_cd.yml` fires on a push to `main` and its path
filter covers the fantasy tree, so merging `dev` → `main` rebuilds and deploys the box image; the
weekly serving schedule is DAILY and `default_status=RUNNING`; Vercel production is `main`. There
is no gate between merging and both publishing and announcing. Until this file existed, the only
control was somebody remembering — which is this repo's recorded E11.30 shape (the detection
exists, the enforcement does not).

══ THE INVARIANT, IN BOTH DIRECTIONS ═════════════════════════════════════════════════════════════

    gate ARMED   ⇒ no held item's text appears in changelog.json
    gate LIFTED  ⇒ the held registry is EMPTY

The second half is the one that makes the reversal safe rather than merely possible. A reversal
that flips the flag and forgets the deferred entry would quietly delete an announcement we owe
users; this turns that into a red build that names the file and the item.

⚠️ AN EXPLICIT REGISTRY, NOT A PHRASE SCAN. The tempting form is "while withheld, no changelog item
may mention weekly projections" — and it would be the NF-DS defect: a substring screen is
negation-blind, so the cheapest way to pass it is to delete the honest sentence that says the
numbers are down. A registry names the exact items a human decided to hold, cannot false-fire on
copy nobody deferred, and keeps the text verbatim so restoring it is a copy rather than a rewrite.

⚠️ CI WIRING IS PART OF THE GUARD, not an afterthought. A frontend-only PR resolves `backend ==
false` and runs no Python job at all (the NCAAF-P3.9 finding) — and the PR that lifts this gate is
exactly such a PR, since flipping the flag touches one `.ts` file. So `ci.yml` carries a
`release_gate` filter selecting the three files this invariant spans, and the clauses below assert
that wiring rather than trusting it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[2]
_CHANGELOG = _REPO / "frontend" / "data" / "changelog.json"
_HELD = _REPO / "frontend" / "data" / "changelog-held.json"
_FLAG_TS = _REPO / "frontend" / "lib" / "weekly-suppression.ts"
_PAGE_TSX = _REPO / "frontend" / "components" / "fantasy" / "weekly-page.tsx"
_CI_YML = _REPO / ".github" / "workflows" / "ci.yml"

_FLAG_NAME = "WEEKLY_NUMBERS_WITHHELD"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The readers. Pure, so the two-sided clauses below can drive them on synthetic input rather than
# on whatever this checkout happens to hold — a guard exercised only against the live files can
# only ever be tested in the state the repo is in today.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def read_flag(src: str) -> bool:
    """The armed state of the withholding flag, read from its declaration.

    ⚠️ RAISES rather than defaulting. A flag this cannot parse leaves every clause below deciding
    on a guess, and the safe-looking default (`True`) would silently turn the reversal's clause
    off. An unreadable gate is not a lifted gate and is not an armed one — it is a broken guard,
    and it says so (NF1.7 (a)).
    """
    m = re.search(rf"^export const {_FLAG_NAME} = (true|false)\b", src, flags=re.M)
    if not m:
        raise AssertionError(
            f"could not read `{_FLAG_NAME}` from weekly-suppression.ts. It must stay a top-level "
            "`export const … = true|false` — the whole promotion gate reads it, and a computed or "
            "renamed value makes every clause in this file decide on nothing."
        )
    return m.group(1) == "true"


#: How much of a held item's lead sentence has to reappear for it to count as restored.
#:
#: ⚠️ NOT EXACT EQUALITY, and not a bare substring either. Exact equality waves through a
#: restoration that fixed a typo on the way back in — still the same announcement, still shipped.
#: A bare substring test in the other direction (`t in held_text`) would let an unrelated one-line
#: entry collide with a long held one by accident. An announcement's opening sentence is what makes
#: it recognisable, and 80 characters of it is far longer than any accidental collision.
_LEAD = 80


def held_items_present(changelog: list[dict], held: dict) -> list[str]:
    """The id of every held item whose announcement is nonetheless in the changelog."""
    texts = [item["text"] for block in changelog for item in block["items"]]
    out: list[str] = []
    for entry in held.get("held", []):
        held_text = entry["item"]["text"]
        lead = held_text[:_LEAD]
        if any(t == held_text or t.startswith(lead) for t in texts):
            out.append(entry["id"])
    return out


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 0 — the non-vacuity floor. Every clause below reads these files; a rename would otherwise make
# them pass against nothing.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_every_file_this_gate_reads_exists_and_parses():
    for path in (_CHANGELOG, _HELD, _FLAG_TS, _PAGE_TSX, _CI_YML):
        assert path.exists(), f"{path.relative_to(_REPO)} is missing — the gate would be vacuous"
    json.loads(_CHANGELOG.read_text())
    held = json.loads(_HELD.read_text())
    assert "held" in held and isinstance(held["held"], list)
    assert held.get("note"), "the held registry has no note saying what it is for"
    for entry in held["held"]:
        assert len(entry["item"]["text"]) > _LEAD, (
            f"held item {entry['id']!r} is shorter than the lead the gate matches on — the prefix "
            "comparison would degenerate toward matching anything that starts the same way"
        )
        for field in ("id", "gate", "why", "week", "restore_at"):
            assert entry.get(field), f"held item {entry.get('id')!r} has no {field}"
    # The flag is readable — asserted separately from the branches that use it, so an unreadable
    # flag reports as itself rather than as whichever clause happened to touch it first.
    read_flag(_FLAG_TS.read_text())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1 — THE GATE ITSELF, both directions
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_a_held_announcement_does_not_ship_while_its_subject_is_withheld():
    withheld = read_flag(_FLAG_TS.read_text())
    changelog = json.loads(_CHANGELOG.read_text())
    held = json.loads(_HELD.read_text())

    if not withheld:
        pytest.skip("the withholding is lifted — the sibling clause owns this state")

    assert held["held"], (
        "nothing is held while the weekly numbers are withheld. That is a legitimate state, but it "
        "makes this clause pass on nothing — if the incident really holds no announcement, delete "
        "frontend/data/changelog-held.json and this clause together rather than leaving an empty "
        "registry that reads like enforcement."
    )
    leaked = held_items_present(changelog, held)
    assert leaked == [], (
        f"held changelog item(s) {leaked} are in changelog.json while "
        f"{_FLAG_NAME} is armed. Merging this to `main` publishes an announcement about weekly "
        "projections into a product that is simultaneously withholding them. Either lift the "
        "withholding (and restore the item deliberately) or take the item back out."
    )


def test_lifting_the_withholding_forces_every_held_announcement_to_be_restored():
    """⭐ THE HALF THAT MAKES THE REVERSAL SAFE RATHER THAN MERELY POSSIBLE.

    Node 4 flips one constant. Without this clause, a reversal that forgot the deferred entry would
    silently drop an announcement users are owed — and nothing would ever say so, because the
    absence of a changelog item is not an error anywhere else in the repo.
    """
    withheld = read_flag(_FLAG_TS.read_text())
    if withheld:
        pytest.skip("the withholding is armed — the sibling clause owns this state")

    held = json.loads(_HELD.read_text())
    assert held["held"] == [], (
        f"{_FLAG_NAME} is false but items are still held: "
        f"{[e['id'] for e in held['held']]}. Restoring the withheld numbers without restoring the "
        "announcements deferred behind them drops them permanently. Move each item's `item` block "
        "back into frontend/data/changelog.json under its stated `week`, VERBATIM, and empty the "
        "`held` list."
    )


def test_the_gate_detects_a_leak_and_clears_a_clean_registry():
    """The two-sided proof, on synthetic input. A screen that cannot refuse is not a screen, and
    `held_items_present` is exercised here on both answers rather than only on whichever one this
    checkout happens to produce."""
    item = {
        "tag": "improved",
        "text": (
            "A distinctive announcement about a thing we have decided to defer, written long "
            "enough that its opening sentence cannot collide with anything by accident."
        ),
    }
    assert len(item["text"]) > _LEAD, "the fixture is shorter than the lead — it would prove nothing"
    held = {"held": [{"id": "x", "item": item}]}

    def cl(*items):
        return [{"week": "2026-09-14", "items": list(items)}]

    assert held_items_present(cl(item), held) == ["x"]
    assert held_items_present(cl(), held) == []
    assert held_items_present(cl({"tag": "fixed", "text": "Something else entirely, and longer."}), held) == []

    # ⭐ A RESTORATION THAT WAS EDITED ON THE WAY BACK IN IS STILL THE SAME ANNOUNCEMENT. This is
    # the case exact equality would wave through, and it is the likely one — nobody re-pastes a
    # paragraph without touching it.
    edited = {"tag": "improved", "text": item["text"][:-6] + " thing, slightly reworded at the end."}
    assert held_items_present(cl(edited), held) == ["x"]


def test_read_flag_reads_both_states_and_refuses_an_unreadable_one():
    assert read_flag(f"export const {_FLAG_NAME} = true\n") is True
    assert read_flag(f"export const {_FLAG_NAME} = false\n") is False
    # A computed value is the realistic way this breaks — someone "makes it configurable".
    with pytest.raises(AssertionError, match=_FLAG_NAME):
        read_flag(f"export const {_FLAG_NAME} = process.env.X === '1'\n")
    with pytest.raises(AssertionError, match=_FLAG_NAME):
        read_flag("export const SOMETHING_ELSE = true\n")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2 — THE FLAG IS THE ONLY LEVER, so the reversal really is the two-line change it is described as
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def test_the_weekly_page_reads_the_flag_and_never_decides_for_itself():
    """⚠️ COMMENT-STRIPPED, because this file's own explanatory prose names the flag repeatedly and
    a raw scan would be satisfied by the comments alone (the INC-38 prose-cannot-satisfy lesson)."""
    page = _strip_ts_comments(_PAGE_TSX.read_text())
    assert _FLAG_NAME in page, (
        "the weekly page does not read the withholding flag — the withholding is decided somewhere "
        "this gate cannot see"
    )
    # Every rendering decision goes through `weeklyRowView` / `weeklyRowOrder`; the page may consult
    # the flag to CALL them and to draw the notice, but a second, page-local rule for what a cell
    # shows would be a copy of the decision that the reversal could leave behind.
    assert "weeklyRowView(" in page and "weeklyRowOrder(" in page, (
        "the weekly page no longer renders through weeklyRowView/weeklyRowOrder — the withheld and "
        "restored pages are no longer one code path, so flipping the flag cannot be trusted to "
        "restore the page exactly"
    )


def test_the_flag_is_not_an_environment_variable():
    """⛔ A Vercel env change does not change git, so a plain Redeploy re-diffs the same commit,
    `vercel.json`'s `ignoreCommand` skips the build and the new value never takes effect — with no
    error anywhere (`docs/vercel_build_skipping.md`). The reversal must ship through the ordinary
    `frontend/` path that actually rebuilds."""
    src = _strip_ts_comments(_FLAG_TS.read_text())
    assert "process.env" not in src, (
        "the withholding flag reads an environment variable. On this project that is a silent "
        "no-op on redeploy — flip a constant and let the push rebuild instead."
    )


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3 — THE CI WIRING. The PR that lifts this gate is frontend-only, and a frontend-only PR runs no
# Python job at all unless a filter says otherwise.
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _ci() -> dict:
    return yaml.safe_load(_CI_YML.read_text())


def _filters() -> dict:
    ci = _ci()
    step = next(
        s for s in ci["jobs"]["changes"]["steps"] if str(s.get("uses", "")).startswith("dorny/")
    )
    return yaml.safe_load(step["with"]["filters"])


def test_a_release_gate_filter_selects_every_file_this_invariant_spans():
    """⚠️ ONE PATTERN, NOT THREE. Under `predicate-quantifier: every` a file must match EVERY entry
    in its list, so a three-line list would select NOTHING — the documented trap that makes the
    obvious edit the disarming one. A single brace pattern is therefore the correct form here, and
    it was MEASURED against picomatch with the action's own options (`{dot: true}`):

        frontend/data/changelog.json          -> true
        frontend/data/changelog-held.json     -> true
        frontend/lib/weekly-suppression.ts    -> true
        frontend/components/nav.tsx           -> false
        betting_ml/tests/test_x.py            -> false
    """
    filters = _filters()
    assert "release_gate" in filters, (
        "ci.yml has no `release_gate` filter — a PR that only flips the withholding flag would run "
        "no Python job, and the reversal clause above would never execute on the one PR it exists "
        "for"
    )
    patterns = filters["release_gate"]
    assert len(patterns) == 1, (
        f"the release_gate filter has {len(patterns)} patterns. Under `predicate-quantifier: every` "
        "a file must match them ALL, so more than one selects nothing at all — use a single brace "
        "pattern."
    )
    pattern = patterns[0]
    for needed in ("changelog.json", "changelog-held.json", "weekly-suppression.ts"):
        assert needed in pattern, f"the release_gate pattern does not cover {needed}: {pattern!r}"
    assert _ci()["jobs"]["changes"]["outputs"].get("release_gate"), (
        "the changes job does not export release_gate, so no job can gate on it"
    )


def test_the_release_gate_job_runs_this_file_and_is_gated_on_its_own_filter():
    ci = _ci()
    job = ci["jobs"].get("release-gate")
    assert job, "ci.yml has no `release-gate` job"
    cond = job["if"]
    assert "release_gate" in cond, f"the release-gate job is not gated on its filter: {cond!r}"
    # ⚠️ NOT `backend || release_gate`. The PR this must fire on is frontend-only; an `||` would
    # make the job green for the pre-existing reason on a mixed PR and prove nothing about the new
    # trigger (the NCAAF-P3.9 clause makes the identical point about the changelog job).
    assert "backend" not in cond, (
        f"the release-gate job's `if:` reads {cond!r} — a `backend` term makes it fire for the old "
        "reason and destroys the evidence that the frontend-only trigger works"
    )
    run = " ".join(str(s.get("run", "")) for s in job["steps"])
    assert Path(__file__).name in run, (
        "the release-gate job does not run this file — it is wired to a filter and tests nothing"
    )


def test_the_backend_filter_was_not_widened_to_reach_the_frontend():
    """⚠️ THE CATASTROPHIC EDIT WEARING THE COSTUME OF THE ONE-LINE FIX, pinned here as well as in
    `test_ncaaf_p3_9_nav.py` because this story is exactly the kind that would reach for it: under
    `every`, adding a `frontend/**` path to `backend` resolves `backend` to FALSE for every file in
    the repo and disarms the entire Python gate."""
    backend = _filters()["backend"]
    offenders = [p for p in backend if p.startswith("frontend/")]
    assert offenders == [], (
        f"frontend path(s) {offenders} were added to the `backend` filter. Under "
        "`predicate-quantifier: every` that makes `backend` false for every backend file in the "
        "repo — it disarms the Python gate rather than extending it. Add a separate filter output."
    )
