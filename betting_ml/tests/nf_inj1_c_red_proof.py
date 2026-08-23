#!/usr/bin/env python3
"""NF-INJ1-C RED PROOF — break the source one defect at a time, require the NAMED test to go RED.

    uv run python betting_ml/tests/nf_inj1_c_red_proof.py
    uv run python betting_ml/tests/nf_inj1_c_red_proof.py magnitude   # one case, by id substring

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever the suite it proves is refactored.

WHY IT EXISTS. This story's suite is mostly SOURCE-INSPECTION and COPY assertions — the exact shape
that reads as coverage while proving nothing. This repo has been bitten by a guard a COMMENT could
satisfy (INC-38), by an `and`-composed rule whose fixture a different clause already refused
(NF-D17), and by a clause satisfied by a dict KEY named after the function it was counting
(DSR-CONV). None of those was visible in a green run.

⭐ THREE WAYS A RED PROOF ITSELF LIES, and all three are guarded below because each has shipped
here before:

  1. THE MUTATION NEVER LANDS (#682). A break that silently no-ops comes back GREEN and reads as
     "the guard is vacuous" — the dangerous direction, because it invites weakening a correct
     guard. ⇒ every case asserts the file CHANGED on disk.
  2. THE MUTATION LANDS ON THE WRONG SYMBOL (E11.24). Two functions with byte-identical tails make
     a single-occurrence replace hit the wrong one. ⇒ every anchor is asserted UNIQUE in the file.
  3. THE MUTATION LANDS AND DOES NOT MOVE THE ASSERTED PREDICATE (#815). Appending a suffix to a
     name leaves an `x in src` clause satisfied. ⇒ where a case names a token the clause reads, the
     token is asserted ABSENT after the patch.

Restores every file from an in-memory backup in a `finally`. ⛔ Deliberately NOT `git checkout --`:
that destroys uncommitted work in the files it patches (it ate an in-progress page at E9.59). The
backups are also restored AT START-UP if a previous run was killed mid-mutation — a red proof's own
worst case is dying between write and restore (E11.26).
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / "app/backend/services/stat_line_suppression.py"
ROUTER = REPO / "app/backend/routers/fantasy.py"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
DEPLOY = REPO / "infrastructure/lambda/deploy.sh"
FILES = (SERVICE, ROUTER, COPY, DEPLOY)

SUITE = "betting_ml/tests/test_nf_inj1_c_stat_line_suppression.py"
BUNDLE_SUITE = "betting_ml/tests/test_nf_c_lda_1_lambda_import_weight.py"

#: (id, file, old, new, "suite::test", token-that-must-vanish-or-None)
#:
#: `old` is normally ONE anchor that must occur exactly once. It may also be a LIST of anchors, all
#: replaced — the form a clause of the shape "the module mentions X somewhere" needs, since removing
#: one of several mentions leaves such a clause satisfied and reports a false "vacuous" (measured
#: here on `drop-the-citation`). Every element still has to be unique, so the wrong-symbol lie is
#: still guarded.
CASES = [
    # ── the predicate has one owner, and it is NF-INJ1's ──────────────────────────────────────
    ("mirror-the-envelope", SERVICE,
     "def counting_stat_fields() -> frozenset[str]:",
     "_QB_PASS_ATT_CEILING = 45.44\n\n\ndef counting_stat_fields() -> frozenset[str]:",
     f"{SUITE}::test_the_predicate_is_imported_from_nf_inj1_never_restated_in_the_backend", None),

    # ⚠️ EVERY citation, not one of them — and the harness taught me that in two passes. A bare
    # `nf_inj1_diagnosis.md` anchor tripped the uniqueness guard (it appears twice: the header cites
    # it, and so does `row_is_impossible`); disambiguating to ONE occurrence then came back GREEN,
    # correctly, because the clause is satisfied by ANY citation and the other one survived. A
    # clause of the form "the module cites X" can only be proven by removing X entirely — which is
    # what the multi-anchor form below does.
    ("drop-the-citation",
     SERVICE,
     ["`quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inj1_diagnosis.md` §2.2",
      "recorded in `nf_inj1_diagnosis.md` §8.1"],
     "`the NF-INJ1 write-up`",
     f"{SUITE}::test_the_recorded_predicate_is_cited_where_a_reader_will_look",
     "nf_inj1_diagnosis.md"),

    # ── what is withheld ──────────────────────────────────────────────────────────────────────
    ("withhold-the-points-too", SERVICE,
     "    return frozenset(projection_fields.STAT_FIELD.values())",
     "    return frozenset(projection_fields.PAID_PLAYER_FIELDS)",
     f"{SUITE}::test_points_and_games_are_never_in_the_withheld_set", None),

    ("hand-list-the-stat-fields", SERVICE,
     "    return frozenset(projection_fields.STAT_FIELD.values())",
     '    return frozenset({"passAtt", "passCmp", "passYds", "passTd", "passInt",\n'
     '                      "rushAtt", "rushYds", "rushTd", "tgt", "rec", "recYds", "recTd"})',
     f"{SUITE}::test_a_new_scorable_stat_is_withheld_automatically", None),

    # ── which rows ─────────────────────────────────────────────────────────────────────────────
    ("suppress-every-row", SERVICE,
     "    return bool(row_violations(row))",
     "    return True",
     f"{SUITE}::test_a_clean_row_is_byte_identical", None),

    ("suppress-no-row", SERVICE,
     "    return bool(row_violations(row))",
     "    return False",
     f"{SUITE}::test_a_violating_row_loses_its_counting_stats_and_keeps_its_points_and_games", None),

    ("blank-an-unevaluable-row", SERVICE,
     "    if not row_is_impossible(row):\n        return row",
     "    if False:\n        return row",
     f"{SUITE}::test_an_unevaluable_row_is_left_alone_not_blanked", None),

    # ── the marker ─────────────────────────────────────────────────────────────────────────────
    # 🚨 The one that undoes the story: `implied_per_game × g` reconstructs the withheld total.
    ("leak-a-magnitude-in-the-marker", SERVICE,
     "    withheld = sorted(k for k in counting_stat_fields() if k in row)",
     "    withheld = sorted(k for k in counting_stat_fields() if k in row)\n"
     "    withheld = withheld + [row.get('g') or 0.0]",
     f"{SUITE}::test_the_marker_carries_no_magnitude", None),

    ("name-fields-that-were-never-served", SERVICE,
     "    withheld = sorted(k for k in counting_stat_fields() if k in row)",
     "    withheld = sorted(counting_stat_fields())",
     f"{SUITE}::test_a_never_served_stat_is_distinguishable_from_a_withheld_one", None),

    ("emit-the-count-only-when-it-fired", SERVICE,
     '    return {**data, "players": out, WITHHELD_COUNT_KEY: withheld_rows}',
     '    if not withheld_rows:\n        return {**data, "players": out}\n'
     '    return {**data, "players": out, WITHHELD_COUNT_KEY: withheld_rows}',
     f"{SUITE}::test_the_count_is_emitted_even_when_nothing_was_withheld", None),

    # ── blast radius ───────────────────────────────────────────────────────────────────────────
    ("mutate-the-memo-in-place", SERVICE,
     "    return {**{k: v for k, v in row.items() if k not in withheld}, WITHHELD_KEY: withheld}",
     "    for _k in withheld:\n        row.pop(_k, None)\n"
     "    row[WITHHELD_KEY] = withheld\n    return row",
     f"{SUITE}::test_it_never_mutates_its_input", None),

    ("blank-the-collection-on-a-bad-row", SERVICE,
     "        if not isinstance(row, dict):\n"
     "            # A malformed row costs only itself and never blanks the collection (E9.49).\n"
     "            out.append(row)\n            continue",
     "        if not isinstance(row, dict):\n            continue",
     f"{SUITE}::test_a_malformed_row_costs_only_itself", None),

    ("suppress-on-the-public-route-too", ROUTER,
     "    return entitlement.open_projections_payload(\n"
     "        projection_fields.public_projections_payload(data)\n    )",
     "    return entitlement.open_projections_payload(\n"
     "        stat_line_suppression.suppress_projections_payload(\n"
     "            projection_fields.public_projections_payload(data)\n        )\n    )",
     f"{SUITE}::test_only_the_paid_route_suppresses", None),

    ("import-the-model-tree-at-module-scope", SERVICE,
     "from . import projection_fields",
     "from . import projection_fields\n"
     "from quant_sports_intel_models.football.nfl.fantasy import projection_coherence  # noqa: F401",
     f"{SUITE}::test_the_engine_import_is_lazy", None),

    # ── the Lambda bundle contract ─────────────────────────────────────────────────────────────
    # ⛔ The failure this one names is invisible everywhere except production: the module resolves
    # locally, every test passes, and `/projections-full` 500s on the first real request.
    ("stop-copying-the-predicate-into-the-zip", DEPLOY,
     "for _m in __init__ projection_coherence; do",
     "for _m in __init__; do",
     f"{BUNDLE_SUITE}::test_every_engine_module_the_backend_imports_is_in_the_deploy_zip",
     "projection_coherence; do"),

    # ── the copy ───────────────────────────────────────────────────────────────────────────────
    ("copy-forecasts-an-injury", COPY,
     'export const STAT_LINE_WITHHELD_DETAIL =\n  "We hold',
     'export const STAT_LINE_WITHHELD_DETAIL =\n  "This player is sidelined. We hold',
     f"{SUITE}::test_the_withheld_copy_forecasts_nothing_about_the_player", None),

    # ⚠️ ISOLATING: the detail string is untouched, so only the "says it is withheld" clause can
    # flip. A break that tripped two clauses at once would prove neither (NF-D17).
    ("short-label-stops-saying-withheld", COPY,
     'export const STAT_LINE_WITHHELD_LABEL = "stat detail withheld — availability-adjusted"',
     'export const STAT_LINE_WITHHELD_LABEL = "availability-adjusted"',
     # ⚠️ The vanish-token is the EXPORT LINE, not the phrase: the phrase also appears in the
     # comment above the constant (quoting the PM's default treatment), so "withheld —" survives
     # the break and the harness would report a false "the clause never saw it" (#815).
     f"{SUITE}::test_the_withheld_copy_says_what_it_is_and_what_survives",
     'STAT_LINE_WITHHELD_LABEL = "stat detail withheld'),

    ("detail-drops-what-still-renders", COPY,
     "His projected points and projected games are unchanged and still shown.",
     "The rest of the row is unchanged.",
     f"{SUITE}::test_the_withheld_copy_says_what_it_is_and_what_survives",
     "His projected points and projected games"),

    ("copy-drifts-into-the-paywall-wording", COPY,
     "Rather than print a number we would not stand behind, we withhold the stat detail here.",
     "Rather than print a number we would not stand behind, we withhold the stat detail here. "
     "Members see the full line for every other player.",
     f"{SUITE}::test_the_withheld_copy_says_what_it_is_and_what_survives", None),

    ("copy-leaves-the-governed-module", COPY,
     "export const STAT_LINE_WITHHELD_SR_LABEL",
     "const STAT_LINE_WITHHELD_SR_LABEL_MOVED_ELSEWHERE",
     f"{SUITE}::test_the_withheld_copy_lives_where_the_shared_governance_screens_it",
     "export const STAT_LINE_WITHHELD_SR_LABEL"),
]


def run(target: str) -> tuple[int, str]:
    r = subprocess.run(
        ["uv", "run", "pytest", target, "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-500:]


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    backups = {p: p.read_text() for p in FILES}
    failures: list[str] = []
    try:
        # ⚠️ Restore first: a previous run killed mid-mutation would otherwise make every case
        # below run against a broken tree, and the baseline check would blame the suite.
        for p, src in backups.items():
            p.write_text(src)

        code, out = run(SUITE)
        if code != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + out)
            return 1
        print("baseline GREEN\n")

        ran = 0
        for case_id, path, old, new, target, must_vanish in CASES:
            if only and only not in case_id:
                continue
            src = backups[path]
            anchors = old if isinstance(old, list) else [old]
            # (2) EVERY ANCHOR MUST BE UNIQUE — otherwise the patch may land on a sibling.
            bad = [(a, src.count(a)) for a in anchors if src.count(a) != 1]
            if bad:
                failures.append(f"{case_id}: anchor(s) not unique: {bad}")
                print(f"⚠️  {case_id}: anchor(s) occur {[n for _a, n in bad]}x in {path.name}")
                continue
            patched = src
            for a in anchors:
                patched = patched.replace(a, new, 1)
            # (1) THE MUTATION MUST LAND.
            if patched == src:
                failures.append(f"{case_id}: patch is a no-op")
                print(f"⚠️  {case_id}: the patch changed nothing")
                continue
            path.write_text(patched)
            landed = path.read_text() == patched
            # (3) …AND IT MUST MOVE THE ASSERTED PREDICATE.
            moved = (must_vanish not in path.read_text()) if must_vanish else True
            code, out = run(target)
            path.write_text(src)
            ran += 1
            if not landed:
                failures.append(f"{case_id}: the mutation did not reach disk")
                print(f"⚠️  {case_id}: mutation did not land on disk")
                continue
            if not moved:
                failures.append(f"{case_id}: {must_vanish!r} survived the mutation")
                print(f"⚠️  {case_id}: {must_vanish!r} survived — the clause never saw the break")
                continue
            verdict = "RED ✅" if code != 0 else "GREEN ❌ (vacuous!)"
            print(f"{verdict}  {case_id}  ->  {target.split('::')[-1]}")
            if code == 0:
                failures.append(f"{case_id} -> {target} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)

    print()
    if failures:
        print(f"{len(failures)} PROBLEM(S):")
        for f in failures:
            print("  - " + f)
        return 1
    print(f"all {ran} cases RED ✅ — every clause fails when the thing it names is broken")
    return 0


if __name__ == "__main__":
    sys.exit(main())
