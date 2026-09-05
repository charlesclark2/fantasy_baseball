#!/usr/bin/env python3
"""NCAAF-P3.3b RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/ncaaf_p3_3b_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_ncaaf_p3_3b_ratings_stamp.py` is refactored.

WHY IT EXISTS HERE IN PARTICULAR. Most of that suite's clauses assert an ABSENCE — no date literal,
no mtime read, no schedule registered, no second renderer — and an absence-asserting clause is the
single easiest kind to write so that it can never fail. This repo has shipped that shape more than
once and never found it by reading the test: a guard a COMMENT could satisfy (INC-38), an
`and`-composed clause whose fixture a different clause already refused (NF-D17), a `"name" in src`
clause the import line satisfied (NF-C0e). ⭐ It bit AGAIN while this very file's suite was being
written: the mtime clause below failed on unbroken source because the module's own docstring
EXPLAINS that it never reads an S3 `LastModified`, so a comment-only strip was tripped by prose
saying the opposite of the defect. The fix was to strip docstrings too; the lesson is that the
absence clauses are the ones that need this harness most.

THE THREE CONTROLS, all of which this repo paid for:

  1. **BASELINE-PASS** — every named clause is proven GREEN on unbroken source first. A clause
     already failing would be reported RED by every break.
  2. **NOT-SELECTED** — a mistyped or stale test id makes pytest select nothing and exit NON-ZERO,
     which a naive `returncode != 0` reads as "the clause went red": the harness reporting its
     strongest result for a clause it never ran. A false RED is the dangerous direction.
  3. **UNIQUE ANCHOR** — a `replace(old, new, 1)` against a non-unique anchor lands wherever the
     first match happens to be, leaving the clause untouched and the harness reporting a FALSE
     "GREEN — VACUOUS" (NF-INJ2b). An anchor seen more than once is AMBIGUOUS-ANCHOR, never applied.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`,
which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

OWNER = REPO / "betting_ml/monitoring/ncaaf_ratings_vintage.py"
BUILDER = REPO / "quant_sports_intel_models/football/ncaaf/serving/team_payloads.py"
CONTRACT = REPO / "app/backend/models/ncaaf.py"
WRITER = REPO / "scripts/write_ncaaf_serving_store.py"
COPY_TS = REPO / "frontend/lib/ncaaf-copy.ts"
STRENGTH_TSX = REPO / "frontend/components/ncaaf/team-strength.tsx"
FIXTURE = REPO / "frontend/e2e/fixtures/api/ncaaf-team-populated.synthetic.json"

SUITE = "betting_ml/tests/test_ncaaf_p3_3b_ratings_stamp.py"

#: (label, file, find, replace, test id)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ⭐ THE ONE THIS STORY EXISTS FOR. Every surface signal says the roll-forward is the right
    # schedule — weekly, Monday 06:00, NCAAF-named, genuinely refreshing NCAAF data — and #1081's
    # commit message says so outright. It just does not rewrite THIS artifact.
    ("the roll-forward is registered as refreshing the ratings",
     OWNER,
     "RATINGS_REFRESH_SCHEDULES: tuple[str, ...] = ()",
     'RATINGS_REFRESH_SCHEDULES: tuple[str, ...] = ("sports_ncaaf_roll_forward_schedule",)',
     "test_the_roll_forward_schedule_is_refused_by_name"),

    # E9.41: an undeclared field is stripped on serialize — the store is right and the page is not.
    ("the vintage is dropped from the served contract",
     CONTRACT,
     "    ratings_as_of: str | None = None",
     "    _ratings_as_of_removed: str | None = None",
     "test_both_halves_are_declared_on_the_contract"),

    # The two-returns-one-contract shape: a field added to the AVAILABLE dict alone type-checks,
    # validates, and is simply missing on the branch a reader meets during an outage.
    ("the unavailable branch stops carrying the stamp",
     BUILDER,
     '            "ratings_as_of": ratings_as_of, "ratings_next_update": ratings_next_update,\n',
     "",
     "test_the_stamp_survives_the_builder_on_both_block_branches[False]"),

    # INC-41: an mtime is refreshed by any server-side rewrite that changes no data, and read GREEN
    # straight through the 19-day NF-FRESH1 outage.
    ("the vintage is read from an object mtime instead of the Delta log",
     OWNER,
     "    reading = SDF.read_contract(probe, bucket=bucket, local_root=local_root)\n"
     "    return reading.last_commit",
     "    import os.path\n"
     "    return os.path.getmtime(str(probe.source))",
     "test_the_vintage_is_read_from_the_delta_log_not_an_object_mtime"),

    # NF1.7(a): a stale registry entry resolving to None is byte-identical to the correct
    # empty-registry answer, so a typo would look exactly like the measured truth.
    ("an unknown schedule name resolves to None instead of raising",
     OWNER,
     '        raise KeyError(f"no Dagster schedule named {name!r} '
     '— RATINGS_REFRESH_SCHEDULES is stale")',
     '        return "0 0 * * *", "UTC"',
     "test_an_unknown_schedule_name_raises_rather_than_silently_resolving_to_none"),

    # Rule 1 of `ncaaf-copy.ts`: no measured figure in the copy file. A cadence typed as prose is
    # right on the day it is written and free to be wrong forever after.
    ("the copy names a weekday instead of reading a date",
     COPY_TS,
     'export const RATINGS_NEXT_UPDATE_UNSCHEDULED = "next update not scheduled"',
     'export const RATINGS_NEXT_UPDATE_UNSCHEDULED = "next update Monday"',
     "test_the_stamp_copy_contains_no_date_and_no_cadence_sentence"),

    # The serving write is HALT-tier and the stamp is not: an unwrapped read would take the whole
    # NCAAF publish down for a decoration.
    ("the writer stops passing the vintage into the payloads",
     WRITER,
     "        ratings_as_of=stamp[\"ratings_as_of\"],",
     "        # ratings_as_of removed",
     "test_the_writer_passes_both_halves_and_degrades_rather_than_failing"),

    # E9.61: two renderers of one statement is how the two drift, and the drift is invisible until
    # a reader meets both.
    ("a second surface re-words the stamp instead of importing it",
     STRENGTH_TSX,
     "  STRENGTH_PRESEASON_NOTE,",
     "  STRENGTH_PRESEASON_NOTE,\n  RATINGS_AS_OF_PREFIX,",
     "test_the_stamp_has_exactly_one_owner_on_the_frontend"),

    # ⛔ The fixture that reaches the PRESENT arm must not invent a schedule production does not
    # have — a fixture asserting a shape prod never serves tests the render against a fiction.
    ("the generated fixture invents a scheduled next update",
     FIXTURE,
     '    "ratings_next_update": null',
     '    "ratings_next_update": "2026-09-07T13:00:00+00:00"',
     "test_the_fixtures_cover_both_arms_of_the_stamp"),
]


def run_one(test_id: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED"."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_id}", "-q", "--no-header",
         "-p", "no:cacheprovider", "-p", "no:randomly"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    if "no tests ran" in out or "ERROR: not found" in out or "not found:" in out:
        return "NOT-SELECTED"
    return "PASSED" if r.returncode == 0 else "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    print("baseline (every named clause, unbroken source) …")
    baseline = {t: run_one(t) for *_, t in CASES}
    bad = {t: v for t, v in baseline.items() if v != "PASSED"}
    if bad:
        for t, v in bad.items():
            print(f"🚨 baseline: {t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1
    print(f"  all {len(baseline)} green ✅\n")

    results = []
    try:
        for label, path, find, replace, test_id in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, test_id, "ANCHOR-MISSING"))
                continue
            if n > 1:
                results.append((label, test_id, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            assert patched != original, label
            path.write_text(patched)
            try:
                outcome = run_one(test_id)
            finally:
                path.write_text(original)
            results.append((label, test_id, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
                "NOT-SELECTED": "NOT-SELECTED (the named clause does not exist)",
            }[outcome]))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(1 for *_, s in results if s == "RED")
    for label, test_id, status in results:
        print(f"{'✅' if status == 'RED' else '🚨'} {label.ljust(width)}  →  {status}")
    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
