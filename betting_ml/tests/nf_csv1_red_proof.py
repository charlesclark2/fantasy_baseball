#!/usr/bin/env python3
"""NF-CSV1 RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/nf_csv1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_nf_csv1_export_withheld_note.py` is refactored.

WHY IT EXISTS. That suite is SOURCE INSPECTION — "the note is keyed on the owner", "the registry
matches the clause map", "the row-count contract is exact". That is precisely the shape which reads
as coverage while proving nothing, and none of this repo's vacuous guards was ever found by reading
the test. They were found by breaking the source and noticing the guard stayed green.

⭐ THE TWO CONTROLS ARE HERE FROM DAY ONE, both inherited from `nf_rate1_red_proof.py` because both
were paid for by a harness that lied:

  · BASELINE-PASS. A clause already failing on unbroken source is reported RED by every break, so
    every named clause is run GREEN before anything is patched.
  · NOT-SELECTED. A mistyped or stale test id makes pytest select nothing and exit NON-ZERO, which
    a naive `returncode != 0` reads as "the clause went red" — the harness reporting its strongest
    result for a clause it never ran. A false RED is indistinguishable from a working guard, which
    is the direction that matters.

⭐⭐ AND EVERY ANCHOR IS ASSERTED UNIQUE BEFORE IT IS APPLIED (the NF-INJ2b lesson): a
`replace(old, new, 1)` against a non-unique anchor lands on whichever match came first, leaving the
clause under test untouched and the harness reporting a FALSE "GREEN — VACUOUS".

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`,
which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
EXPORTER = REPO / "frontend/components/fantasy/rankings-board.tsx"
CONTRACT_SPEC = REPO / "frontend/e2e/specs/fantasy-board-flows.spec.ts"
COPY_SPEC = REPO / "frontend/e2e/specs/full-season-rate.spec.ts"

SUITE = "betting_ml/tests/test_nf_csv1_export_withheld_note.py"

# (label, file, find, replace, clause_that_must_go_red)
CASES = [
    # ── the copy: governed, single-line, honest, no forecast ──────────────────────────────────
    ("type the note's wording into the exporting component instead of importing it", EXPORTER,
     "      csvWithheldNote(withheldClasses),",
     '      withheldClasses.length ? "Note — one or more rows in this file have a value withheld." : null,',
     "test_the_note_copy_lives_in_the_governed_module_and_nowhere_else"),

    # ⚠️ A LITERAL `\n` IN THE COPY, not a real one — that is how it would actually arrive (a copy
    # edit adding a paragraph break), and `downloadCsv`'s escaper quotes it into a MULTI-LINE FIELD
    # that silently costs the file a line against every line-counting reader.
    ("break the note across two lines", COPY,
     '  trailer:\n    "The Full-season rate column',
     '  trailer:\n    "\\nThe Full-season rate column',
     "test_every_part_of_the_note_is_a_single_line"),

    ("turn the note into an availability forecast", COPY,
     "above any season a real player has posted at that position since 2006",
     "above what he can post in the games he is expected to miss",
     "test_the_note_makes_no_forecast_and_names_the_condition_a_reader_can_check"),

    ("trim the note back to a bare 'a value is withheld'", COPY,
     "imply a full-season pace above any season a real player has posted at that position since 2006",
     "are inconsistent",
     "test_the_note_makes_no_forecast_and_names_the_condition_a_reader_can_check"),

    # ⭐ THE HONESTY BREAK, and the one this story is most exposed to: a note that reads well and is
    # FALSE about the three served rows whose cell is blank for an entirely different reason.
    ("claim every blank cell in the column is a withholding", COPY,
     "That column is also blank where there is no expected-games figure to divide by, which is an "
     "absence rather than a withholding, and this file cannot tell the two apart.",
     "A blank in that column is a number we are declining to publish.",
     "test_the_note_does_not_claim_that_every_blank_cell_is_a_withholding"),

    ("stop pointing the reader at the on-page column", COPY,
     '    "The Full-season rate column on the site marks the withheld rows and states why.",',
     '    "See our methodology for details.",',
     "test_the_note_points_at_the_surface_that_carries_the_per_row_disclosure"),

    # ── the registry ──────────────────────────────────────────────────────────────────────────
    ("register a second withheld class without giving it a clause", COPY,
     'export const CSV_WITHHELD_CLASSES: readonly CsvWithheldClass[] = ["full-season-rate"]',
     'export const CSV_WITHHELD_CLASSES: readonly CsvWithheldClass[] = ["full-season-rate", "stat-line"]',
     "test_every_registered_class_has_a_clause_and_every_clause_a_class"),

    # ⭐ THE NF-INJ1-C REACH CHECK, EXERCISED. Adding a stat column to this export is exactly the
    # change that would make the note incomplete, and it is a one-line edit somebody makes for an
    # unrelated reason. The clause has to notice it rather than the note quietly under-enumerating.
    ("add a stat-line column to the export without registering its withheld class", EXPORTER,
     '"range_basis", ...(delta ? ["vs_generic_board"] : [])],',
     '"range_basis", "pass_yds", ...(delta ? ["vs_generic_board"] : [])],',
     "test_the_registry_holds_only_classes_that_can_reach_this_export"),

    # ── the trigger ───────────────────────────────────────────────────────────────────────────
    # ⭐⭐ THE HEADLINE BREAK. This is the natural way to write the feature and it is wrong: the
    # served board has 3 blank rate cells and 0 withheld rows, so an emptiness-keyed trigger ships a
    # note claiming a withholding the file does not contain.
    ("key the note on an EMPTY CELL rather than on the owner's withheld state", EXPORTER,
     '    if (rows.some((p) => fullSeasonRateDisplay(p.pts, p.g, p.pos).kind === "withheld")) {',
     "    if (rows.some((p) => fullSeasonRateCsv(p.pts, p.g, p.pos) == null)) {",
     "test_the_export_keys_the_note_on_the_owner_not_on_an_empty_cell"),

    ("emit the note on every export regardless of what the file contains", EXPORTER,
     "      csvWithheldNote(withheldClasses),",
     '      csvWithheldNote(["full-season-rate"]),',
     "test_the_export_keys_the_note_on_the_owner_not_on_an_empty_cell"),

    ("return an empty string instead of null when nothing is withheld", COPY,
     "  if (listed.length === 0) return null",
     '  if (listed.length === 0) return ""',
     "test_the_note_is_absent_rather_than_empty_when_nothing_is_withheld"),

    ("append the note row unconditionally", SHARED,
     "  if (note) {\n    lines.push(",
     "  {\n    lines.push(",
     "test_the_note_is_absent_rather_than_empty_when_nothing_is_withheld"),

    # ── where the row lands ───────────────────────────────────────────────────────────────────
    ("put the note row FIRST, above the data", SHARED,
     "  const lines = [headers.map(esc).join(\",\"), ...rows.map((r) => r.map(esc).join(\",\"))]\n"
     "  if (note) {\n"
     "    lines.push([note, ...Array(Math.max(headers.length - 1, 0)).fill(null)].map(esc).join(\",\"))\n"
     "  }",
     "  const lines = [headers.map(esc).join(\",\")]\n"
     "  if (note) {\n"
     "    lines.push([note, ...Array(Math.max(headers.length - 1, 0)).fill(null)].map(esc).join(\",\"))\n"
     "  }\n"
     "  lines.push(...rows.map((r) => r.map(esc).join(\",\")))",
     "test_the_note_row_is_appended_after_the_data_and_keeps_the_header_arity"),

    ("write the note as a SHORT row rather than one carrying the header's arity", SHARED,
     "    lines.push([note, ...Array(Math.max(headers.length - 1, 0)).fill(null)].map(esc).join(\",\"))",
     "    lines.push([note].map(esc).join(\",\"))",
     "test_the_note_row_is_appended_after_the_data_and_keeps_the_header_arity"),

    # ── the contract, and the E2E that reads the bytes ────────────────────────────────────────
    ("weaken the row count back to a tolerance", CONTRACT_SPEC,
     "    ).toBe(total)\n\n    // ⭐ NF-CSV1 — AND NO NOTE ROW",
     "    ).toBeGreaterThan(total - 1)\n\n    // ⭐ NF-CSV1 — AND NO NOTE ROW",
     "test_the_row_count_contract_is_exact_and_two_sided"),

    ("stop asserting that a board withholding nothing exports no note", CONTRACT_SPEC,
     "    ).toEqual([])\n    expect(\n      csv,",
     "    ).toBeDefined()\n    expect(\n      csv,",
     "test_the_row_count_contract_is_exact_and_two_sided"),

    ("stop asserting that a withheld cell exports exactly one note", CONTRACT_SPEC,
     '      "a row is withheld in this file and the export states nothing about it",\n    ).toBe(1)',
     '      "a row is withheld in this file and the export states nothing about it",\n    ).toBeDefined()',
     "test_the_row_count_contract_is_exact_and_two_sided"),

    ("stop pinning the note's rendered bytes against the copy module", COPY_SPEC,
     '    ).toBe(csvWithheldNote(["full-season-rate"]))',
     "    ).toBeTruthy()",
     "test_the_e2e_reads_the_downloaded_bytes_both_ways"),

    ("assert the withheld side against the board AS SERVED, which withholds nothing", CONTRACT_SPEC,
     "      transform: (pathname, body) =>",
     "      entitlement: \"free\" as const,\n      _transform: (pathname: string, body: any) =>",
     "test_the_e2e_reads_the_downloaded_bytes_both_ways"),

    # ── scope ─────────────────────────────────────────────────────────────────────────────────
    ("let the note machinery read the envelope it is only supposed to disclose", COPY,
     "export type CsvWithheldClass = \"full-season-rate\"",
     "export type CsvWithheldClass = \"full-season-rate\"\n// REALIZED_MAX_SEASON_PACE\nconst _envelopeProbe = REALIZED_MAX_SEASON_PACE",
     "test_the_suppression_owner_is_untouched_by_the_note_machinery[REALIZED_MAX_SEASON_PACE]"),

    ("let an ordering module import the export's note", REPO / "frontend/lib/big-board.ts",
     "// big-board.ts — NF-C4:",
     'import { csvWithheldNote } from "@/lib/fantasy-claim-copy"\n// big-board.ts — NF-C4:',
     "test_the_note_never_reaches_an_ordering_module"),
]


def run_one(test_name: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED" — see the NOT-SELECTED note in the module docstring."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    last = out.splitlines()[-1:][0:1]
    if "no tests ran" in out or "ERROR: not found" in out or (last and " error" in last[0]):
        return "NOT-SELECTED"
    return "PASSED" if r.returncode == 0 else "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    # ⭐ CONTROL 1 — BASELINE-PASS. A clause already red on unbroken source is reported RED by every
    # break, so "RED" would mean nothing. Prove each named clause is GREEN before patching anything.
    baseline = {t: run_one(t) for _, _, _, _, t in CASES}
    bad = {k: v for k, v in baseline.items() if v != "PASSED"}
    if bad:
        for t, v in bad.items():
            print(f"🚨 baseline: {SUITE}::{t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1

    results = []
    try:
        for label, path, find, replace, test_name in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            # ⭐ CONTROL 3 — UNIQUE ANCHOR (NF-INJ2b). A non-unique anchor lands on the first match,
            # which may be a different symbol entirely: the clause under test is never touched and
            # the harness reports a FALSE "GREEN — VACUOUS", the direction that invites weakening a
            # correct guard.
            if n > 1:
                results.append((label, test_name, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            assert patched != original, label
            path.write_text(patched)
            try:
                outcome = run_one(test_name)
            finally:
                path.write_text(original)
            results.append((label, test_name, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
                # ⭐ CONTROL 2 — NOT-SELECTED. Never counted as a RED.
                "NOT-SELECTED": "NOT-SELECTED (the named clause does not exist)",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = 0
    for label, test_name, status in results:
        mark = "✅" if status == "RED" else "🚨"
        print(f"{mark} {label.ljust(width)}  →  {status}   ({test_name})")
        red += status == "RED"

    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
