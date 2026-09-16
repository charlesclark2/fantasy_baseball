"""nf_inc_0916_red_proof.py — prove NF-INC-0916's promotion gate can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE GATE THIS PROVES IS THE ONE THE OPERATOR IS BEING ASKED TO TRUST INSTEAD OF REMEMBERING.
The weekly page is withholding numbers it has measured wrong while a changelog entry announcing an
improvement to those same numbers waits in `changelog-held.json`. Promoting `dev` → `main` is one
click and publishes both. So "the gate is armed" is not a claim that may rest on the guard being
green — a guard can be green because it is correct or because it is vacuous, and those look
identical from a run page.

⭐ THE FOUR WAYS A RED PROOF ITSELF LIES, all guarded here — machinery borrowed verbatim from
`nf_wk_td1_red_proof` rather than re-invented:
  1. **the mutation never LANDS** (#682) — every mutation asserts the file CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — a replacing mutation asserts the
     OLD token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied;
  4. **the node id COLLECTS NOTHING** — pytest exits non-zero on an unresolvable node id, so a
     renamed guard reports a perfect RED for a test that no longer exists. Every node id is
     resolved during the BASELINE phase, before any source is touched.
⭐ Plus a BASELINE-PASS leg and a NOT-SELECTED leg (a mutation must not turn some OTHER test red and
be credited to this one).

⚠️ THE MUTATED FILES HERE ARE `.ts`, `.json` AND `.yml`, NOT `.py`. The borrowed sweep asserted a
`.py` target before restoring a backup; that assertion is a safety rail on the RESTORE path, so it
is widened to the extensions this harness actually touches rather than removed.

⛔ Restores every file in a `finally`, and ALSO sweeps stale backups AT START-UP: this harness's own
worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26 lesson).

⚠️ NOT SAFE TO RUN CONCURRENTLY WITH ITSELF. One at a time.

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_inc_0916_red_proof.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_TESTS = _REPO / "betting_ml/tests"

_CHANGELOG = _REPO / "frontend/data/changelog.json"
_HELD = _REPO / "frontend/data/changelog-held.json"
_FLAG_TS = _REPO / "frontend/lib/weekly-suppression.ts"
_PAGE_TSX = _REPO / "frontend/components/fantasy/weekly-page.tsx"
_CI_YML = _REPO / ".github/workflows/ci.yml"

_GUARD = _TESTS / "test_nf_inc_0916_promotion_gate.py"
_GUARD_FILES = (_GUARD,)

#: An unrelated clause that must stay GREEN through every mutation — otherwise a RED is not
#: attributable to the guard it is credited to. Deliberately one that ALSO reads `ci.yml`, so a
#: mutation that broke the workflow wholesale (rather than the one property under test) shows up
#: here instead of being credited to this story.
NOT_SELECTED = (
    f"{_TESTS / 'test_ncaaf_p3_9_nav.py'}"
    "::test_the_changelog_filter_selects_the_changelog_and_nothing_else"
)

_BAK_SUFFIX = ".redproof.bak"
_RESTORABLE = {".ts", ".tsx", ".json", ".yml"}

def _held_item_json() -> str:
    """The deferred item, serialised exactly as `changelog.json` carries an item.

    ⭐ READ FROM THE REGISTRY rather than typed here. The mutation has to be the REAL restoration or
    it proves nothing about the real gate — and a copy typed into this file would drift from the
    registry on the first reword, at which point the mutation would stop expressing the defect
    while the harness went on reporting a perfect RED.
    """
    entry = json.loads(_HELD.read_text())["held"][0]
    body = json.dumps(entry["item"], indent=2, ensure_ascii=False)
    return "\n".join("      " + ln for ln in body.splitlines())


#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── the gate itself: a held announcement must not ship while its subject is withheld ────────
    ("the deferred announcement is put back into the changelog while the numbers are withheld",
     _CHANGELOG,
     '    "week": "2026-09-14",\n    "items": [\n',
     '    "week": "2026-09-14",\n    "items": [\n' + _held_item_json() + ",\n",
     f"{_GUARD}::test_a_held_announcement_does_not_ship_while_its_subject_is_withheld"),

    ("…and it is caught even when it was lightly reworded on the way back in",
     _CHANGELOG,
     '    "week": "2026-09-14",\n    "items": [\n',
     '    "week": "2026-09-14",\n    "items": [\n'
     + _held_item_json().replace(' of the game."', ' of the game, roughly speaking."')
     + ",\n",
     f"{_GUARD}::test_a_held_announcement_does_not_ship_while_its_subject_is_withheld"),

    ("the held registry is emptied instead of the item being restored — the announcement vanishes",
     _HELD,
     '  "held": [',
     '  "held_disabled": [',
     f"{_GUARD}::test_every_file_this_gate_reads_exists_and_parses"),

    # ── the flag is readable, and is the only lever ──────────────────────────────────────────────
    ("the withholding flag becomes a computed value, so nothing can read its state",
     _FLAG_TS,
     "export const WEEKLY_NUMBERS_WITHHELD = true",
     'export const WEEKLY_NUMBERS_WITHHELD = process.env.NEXT_PUBLIC_WEEKLY_WITHHELD !== "0"',
     f"{_GUARD}::test_every_file_this_gate_reads_exists_and_parses"),

    ("the flag moves to an environment variable, which a Vercel redeploy silently ignores",
     _FLAG_TS,
     "export const WEEKLY_WITHHELD_SINCE = ",
     'const _ENV_OVERRIDE = process.env.NEXT_PUBLIC_WEEKLY_WITHHELD\nexport const WEEKLY_WITHHELD_SINCE = ',
     f"{_GUARD}::test_the_flag_is_not_an_environment_variable"),

    ("the page stops rendering through the shared row plan and decides for itself again",
     _PAGE_TSX,
     "view={weeklyRowView(p, WEEKLY_NUMBERS_WITHHELD)}",
     "view={{ point: { kind: 'withheld' } } as WeeklyRowView}",
     f"{_GUARD}::test_the_weekly_page_reads_the_flag_and_never_decides_for_itself"),

    # ── the CI wiring: the gate must RUN on the PR class that lifts it ───────────────────────────
    ("the release-gate filter is deleted, so the reversal PR runs no Python job at all",
     _CI_YML,
     "            release_gate:\n              - 'frontend/{data/changelog.json,data/changelog-held.json,lib/weekly-suppression.ts}'\n",
     "",
     f"{_GUARD}::test_a_release_gate_filter_selects_every_file_this_invariant_spans"),

    ("the filter is split into three patterns, which under `every` selects nothing at all",
     _CI_YML,
     "              - 'frontend/{data/changelog.json,data/changelog-held.json,lib/weekly-suppression.ts}'",
     "              - 'frontend/data/changelog.json'\n"
     "              - 'frontend/data/changelog-held.json'\n"
     "              - 'frontend/lib/weekly-suppression.ts'",
     f"{_GUARD}::test_a_release_gate_filter_selects_every_file_this_invariant_spans"),

    ("the release-gate job is widened to `backend ||`, destroying the evidence its trigger works",
     _CI_YML,
     "    if: needs.changes.outputs.release_gate == 'true'",
     "    if: needs.changes.outputs.backend == 'true' || needs.changes.outputs.release_gate == 'true'",
     f"{_GUARD}::test_the_release_gate_job_runs_this_file_and_is_gated_on_its_own_filter"),

    ("the release-gate job stops running the gate, so it is wired to a filter and tests nothing",
     _CI_YML,
     "        run: uv run pytest betting_ml/tests/test_nf_inc_0916_promotion_gate.py -v --tb=short",
     "        run: echo 'release gate ok'",
     f"{_GUARD}::test_the_release_gate_job_runs_this_file_and_is_gated_on_its_own_filter"),

    ("the frontend is added to the `backend` filter — the edit that DISARMS the whole Python gate",
     _CI_YML,
     "            backend:\n              - '**'\n",
     "            backend:\n              - '**'\n              - 'frontend/lib/weekly-suppression.ts'\n",
     f"{_GUARD}::test_the_backend_filter_was_not_widened_to_reach_the_frontend"),
]


def _run(nodeid: str) -> bool:
    r = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header", "-p",
                        "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


def _collects(nodeid: str) -> bool:
    """Does this node id resolve to at least one test? ⚠️ Asked ONLY on UNBROKEN source."""
    probe = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header",
                            "--collect-only", "-p", "no:cacheprovider"],
                           cwd=_REPO, capture_output=True, text=True)
    return probe.returncode == 0 and "no tests ran" not in (probe.stdout + probe.stderr)


def _sweep_stale_backups() -> list[str]:
    """⛔ FIRST, before any mutation: a stale backup means real source is still broken.

    ⚠️ The WHOLE known suffix is stripped, never `with_suffix("")` — `Path` treats only the last
    dotted segment as a suffix, so that idiom writes the original to a junk filename, leaves the
    real file mutated and reports success.
    """
    restored = []
    for root in (_REPO / "frontend/data", _REPO / "frontend/lib",
                 _REPO / "frontend/components", _REPO / ".github/workflows"):
        for bak in root.rglob(f"*{_BAK_SUFFIX}"):
            target = Path(str(bak)[: -len(_BAK_SUFFIX)])
            assert target.suffix in _RESTORABLE, (
                f"refusing to restore {bak} onto {target} — that is not a file this harness mutates")
            target.write_text(bak.read_text())
            bak.unlink()
            restored.append(str(target.relative_to(_REPO)))
    return restored


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: every guard must be GREEN on unbroken source "
          "(a 'red' means nothing otherwise)")
    if not all(_run(str(f)) for f in _GUARD_FILES) or not _run(NOT_SELECTED):
        print("⛔ BASELINE FAILED — fix the suite before reading any RED below")
        return 1
    missing = sorted({c[4] for c in CASES if not _collects(c[4])})
    if missing:
        print(f"⛔ BASELINE FAILED — these node ids collect NOTHING (renamed/moved/deleted), so "
              f"every RED credited to them would be meaningless: {missing}")
        return 1
    print(f"   ✅ baseline green, all {len({c[4] for c in CASES})} named guards resolve\n")

    red = 0
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        n = src.count(old)
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            continue
        bak = path.with_suffix(path.suffix + _BAK_SUFFIX)
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            after = path.read_text()
            additive = bool(new) and old in new
            assert after != src, f"{label}: mutation did not land"
            if additive:
                assert new not in src, f"{label}: the additive break was ALREADY present"
                assert new in after, f"{label}: the additive break is not in the file"
            else:
                assert old not in after, (
                    f"{label}: the old token survives — the predicate did not move")

            failed = not _run(nodeid)
            other_ok = _run(NOT_SELECTED)
            mark = "✅ RED" if failed else "⛔ STILL GREEN (VACUOUS GUARD)"
            sel = "" if other_ok else "  ⚠️ NOT-SELECTED control also broke — not attributable"
            print(f"{mark:34s} {label}{sel}")
            red += bool(failed and other_ok)
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    print(f"\n{red}/{len(CASES)} mutations turned their named guard RED (attributably).")
    print("── restoring: verifying the tree is green again")
    ok = all(_run(str(f)) for f in _GUARD_FILES)
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
