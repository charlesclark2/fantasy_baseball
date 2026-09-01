#!/usr/bin/env python3
"""NF-RATE1 RED PROOF — break the source one defect at a time, require the NAMED clause to fail.

    uv run python betting_ml/tests/nf_rate1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run by hand whenever `test_nf_rate1_full_season_rate_suppression.py` is refactored.

WHY IT EXISTS. That suite is SOURCE INSPECTION — "this site renders through that owner", "this
constant records its own derivation". That is precisely the shape which reads as coverage while
proving nothing, and this repo has shipped it repeatedly: a guard a COMMENT could satisfy (INC-38),
an `and`-composed clause whose fixture was already refused by a different clause (NF-D17), a
`"name" in src` clause satisfied by the import line alone (NF-C0e). None was found by reading the
test. All were found by breaking the source and noticing the guard stayed green.

⭐ EACH CASE NAMES ONE CLAUSE and asserts THAT clause fails. A break that turns the whole file red
proves much less — it can mean the clause worked, or that the import broke.

⭐⭐ AND EVERY ANCHOR IS ASSERTED UNIQUE BEFORE IT IS APPLIED (the NF-INJ2b lesson). Two functions
with byte-identical tails made a `replace(old, new, 1)` land on the WRONG one there, and the harness
came back GREEN reporting a FALSE "the guard is vacuous" — the dangerous direction, because it reads
as a real finding and invites weakening a correct guard. An anchor that appears twice is reported as
AMBIGUOUS-ANCHOR and never applied.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --`, which would destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

OWNER = REPO / "frontend/lib/fantasy.ts"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
PROJECTIONS = REPO / "frontend/components/fantasy/projections-table.tsx"
PLAYER_PAGE = REPO / "frontend/components/fantasy/player-page.tsx"
BIG_BOARD = REPO / "frontend/lib/big-board.ts"
SPEC = REPO / "frontend/e2e/specs/full-season-rate.spec.ts"

SUITE = "betting_ml/tests/test_nf_rate1_full_season_rate_suppression.py"
FREEMIUM = "betting_ml/tests/test_freemium_tier.py"

# (label, file, find, replace, clause_that_must_go_red, suite)
CASES = [
    # ── the anchor itself ─────────────────────────────────────────────────────────────────────
    ("drop a position from the envelope", OWNER,
     '  TE: 414.0,\n',
     '',
     "test_the_envelope_covers_exactly_the_positions_the_anchor_family_covers", SUITE),

    # ⚠️ THE FIRST SPELLING OF THIS BREAK LANDED ON THE `with s as (...)` LINE AND CAME BACK GREEN —
    # correctly, because the clause reads the TABLE NAME and that line does not contain it. A break
    # that lands on disk but does not move the asserted predicate is a false "vacuous" report
    # (E11.24 #815), so the anchor is the token the clause actually asserts.
    ("erase the source table from the derivation", OWNER,
     "//                from main_nfl_marts.fct_player_week",
     "//                from the marts",
     "test_the_envelope_pins_its_derivation_not_merely_its_values", SUITE),

    # ⭐ THE SUBTLEST BREAK HERE, and the reason the TE clause exists at all. Deriving the ceiling on
    # full PPR alone is the natural mistake — it is the scoring most boards use — and it produces a
    # ceiling that is TOO LOW for the TE-premium preset, i.e. a FALSE suppression of a rate that
    # scoring genuinely permits. Nothing else in the suite would notice: every other clause is
    # satisfied by 354.5, because it is a plausible number in the right units.
    ("re-derive the TE ceiling on full PPR only, dropping the TE-premium headroom", OWNER,
     "  TE: 414.0,",
     "  TE: 354.5,",
     "test_the_ceiling_is_a_max_over_the_most_generous_scoring_we_publish", SUITE),

    ("widen the QB ceiling until the pre-existing violator fits under it", OWNER,
     "  QB: 471.1,",
     "  QB: 700.0,",
     "test_the_rule_catches_every_measured_absurd_row[Will Levis-QB-137.7-3.7-633]", SUITE),

    ("tighten the WR ceiling until a rate football has actually posted is suppressed", OWNER,
     "  WR: 435.2,",
     "  WR: 300.0,",
     "test_the_rule_leaves_a_high_but_real_rate_alone[Jayden Higgins-WR-121.5-5.0-413]", SUITE),

    # ── one owner, four sites ─────────────────────────────────────────────────────────────────
    ("give the rule a second owner in a component", SHARED,
     "  const d = fullSeasonRateDisplay(pts, games, pos)\n  if (d.kind === \"withheld\") return <WithheldFullSeasonRate />",
     "  const d = fullSeasonRateDisplay(pts, games, pos)\n  const _ceiling = REALIZED_MAX_SEASON_PACE[String(pos).toUpperCase()]\n  if (d.kind === \"withheld\") return <WithheldFullSeasonRate />",
     "test_the_rule_is_declared_in_exactly_one_place", SUITE),

    ("revert the rankings column to the raw helper", RANKINGS,
     "<FullSeasonRateCell pts={p.pts} games={p.g} pos={p.pos} />",
     "{num(fullSeasonRate(p.pts, p.g))}",
     "test_no_render_site_recomputes_the_rate_inline", SUITE),

    ("revert the projections column to inline arithmetic", PROJECTIONS,
     "<FullSeasonRateCell pts={p[effScoring]} games={p.g} pos={p.pos} />",
     "{(p[effScoring] * 17) / p.g}",
     "test_every_on_page_site_renders_through_the_shared_component[components/fantasy/projections-table.tsx-<FullSeasonRateCell]",
     SUITE),

    ("fix only ONE of the player page's two tiles", PLAYER_PAGE,
     "FullSeasonRateSubLine({ pts: boardRow?.pts, games: proj.g, pos: proj.pos }),",
     "false,",
     "test_the_player_page_renders_the_rate_on_both_of_its_tiles", SUITE),

    # ── the CSV, the site a table-only fix misses ─────────────────────────────────────────────
    ("fix the table and leave the export alone", RANKINGS,
     "fullSeasonRateCsv(p.pts, p.g, p.pos),",
     "fullSeasonRate(p.pts, p.g),",
     "test_the_csv_column_is_fed_by_the_owner", SUITE),

    ("export a sentinel instead of an empty cell", OWNER,
     '  return d.kind === "rate" ? d.value : null\n',
     "  return d.kind === \"rate\" ? d.value : 0\n",
     "test_the_csv_cell_is_empty_on_a_suppressed_row_and_a_number_otherwise", SUITE),

    ("let downloadCsv write a null cell as the literal 'null'", SHARED,
     '    if (v == null) return ""',
     "    if (v == null) return String(v)",
     "test_the_csv_cell_is_empty_on_a_suppressed_row_and_a_number_otherwise", SUITE),

    ("delete the empty-cell semantics from the export", RANKINGS,
     "      // this one is a WITHHOLDING, not a missing field — we have the number and are declining to",
     "      // this one carries no number.",
     "test_the_empty_cell_semantics_are_written_down_where_the_export_is_built", SUITE),

    # ── what must not have changed ────────────────────────────────────────────────────────────
    ("restate the MIN_GAMES floor inside the new owner instead of inheriting it", OWNER,
     "  const rate = fullSeasonRate(pts, games)\n  if (rate == null) return { kind: \"unavailable\" }",
     "  if (typeof pts !== \"number\" || typeof games !== \"number\" || games <= 0) "
     "return { kind: \"unavailable\" }\n  const rate = (pts * FULL_SEASON_GAMES) / games",
     "test_the_min_games_floor_is_untouched", SUITE),

    ("make the rate's refusal borrow NF-INJ1-C's stat-line wording", SHARED,
     "      <p className=\"font-medium text-gray-300\">{FULL_SEASON_RATE_WITHHELD_LABEL}</p>\n"
     "      <p className=\"mt-1.5\">{FULL_SEASON_RATE_WITHHELD_DETAIL}</p>\n"
     "    </InfoTip>\n"
     "  )\n"
     "}\n"
     "\n"
     "/** The whole TABLE CELL",
     "      <p className=\"font-medium text-gray-300\">{STAT_LINE_WITHHELD_LABEL}</p>\n"
     "      <p className=\"mt-1.5\">{STAT_LINE_WITHHELD_DETAIL}</p>\n"
     "    </InfoTip>\n"
     "  )\n"
     "}\n"
     "\n"
     "/** The whole TABLE CELL",
     "test_the_nf_inj1_c_stat_line_machinery_is_adjacent_not_shared", SUITE),

    ("turn the withheld disclosure into an availability forecast", COPY,
     "so we don't print it here",
     "because he is expected to miss most of the season, so we don't print it here",
     "test_the_withheld_copy_lives_in_claim_copy_and_makes_no_forecast", SUITE),

    ("type the withheld wording into a component instead of importing it", RANKINGS,
     "                              <FullSeasonRateCell pts={p.pts} games={p.g} pos={p.pos} />",
     "                              <span>higher than any full season on record</span>",
     "test_no_component_writes_the_withheld_prose_inline", SUITE),

    ("let the display transform reach an ordering module", BIG_BOARD,
     "// big-board.ts — NF-C4:",
     "import { fullSeasonRateDisplay } from \"@/lib/fantasy\"\n// big-board.ts — NF-C4:",
     "test_the_rate_is_still_a_display_transform_only", SUITE),

    # ── the E2E spec's own coverage ───────────────────────────────────────────────────────────
    ("stop the E2E spec asserting an untouched control row", SPEC,
     "      `${CLEAN.name} was withheld on the projections table`,\n    ).toHaveCount(0)",
     "      `${CLEAN.name} was withheld on the projections table`,\n    ).toBeDefined()",
     "test_the_e2e_spec_exists_and_covers_every_surface_both_ways", SUITE),

    ("drop the CSV export from the E2E spec", SPEC,
     'page.getByRole("button", { name: "Export CSV" }).click(),',
     "page.getByRole(\"button\", { name: \"Download\" }).click(),",
     "test_the_e2e_spec_exists_and_covers_every_surface_both_ways", SUITE),

    # ── the clause NF-RATE1 re-anchored rather than weakened ──────────────────────────────────
    # ⚠️ The pre-existing freemium clause used to accept a bare `fullSeasonRate(` call. NF-RATE1
    # re-anchored it onto the shared component, which makes it STRICTER — a site reverting to the
    # raw helper is now a second owner AND fails there. This case proves the re-anchored clause
    # still bites rather than having been quietly loosened.
    ("head the rate column but never populate it", PROJECTIONS,
     "<FullSeasonRateCell pts={p[effScoring]} games={p.g} pos={p.pos} />",
     "{null}",
     "test_the_rate_renders_beside_the_expected_total[components/fantasy/projections-table.tsx]",
     FREEMIUM),
]


def run_one(test_name: str, suite: str) -> str:
    """"PASSED" | "FAILED" | "NOT-SELECTED".

    ⭐⭐ THE THIRD OUTCOME IS LOAD-BEARING AND WAS ADDED AFTER THIS HARNESS PRODUCED A FALSE RED.
    A mistyped or stale test id makes pytest select nothing and exit NON-ZERO, which a naive
    `returncode == 0` reads as "the clause went red" — i.e. the harness reports its strongest
    possible result for a clause it never ran. That is the vacuous-guard family landing on the
    guard-of-the-guard (E11.24 #682: a RED proof must assert its break actually took effect), and it
    is the direction that matters, because a false RED is indistinguishable from a working guard.
    Measured here: one case named a parametrized id for a clause that is not parametrized, ran
    nothing, and was reported RED."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{suite}::{test_name}", "-q", "--no-header", "-p",
         "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    out = r.stdout + r.stderr
    if "no tests ran" in out or "ERROR: not found" in out or " error" in out.splitlines()[-1:][0:1]:
        return "NOT-SELECTED"
    if r.returncode == 0:
        return "PASSED"
    return "FAILED"


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}

    # ⭐ THE OTHER SIDE OF THE CONTROL. A clause that is ALREADY FAILING on unbroken source would be
    # reported RED by every break, so the harness first proves each named clause is GREEN before
    # anything is patched. Together with NOT-SELECTED above, "RED" then means what it says:
    # the clause exists, it passes today, and this specific break is what makes it fail.
    baseline = {(t, s): run_one(t, s) for _, _, _, _, t, s in CASES}
    bad = {k: v for k, v in baseline.items() if v != "PASSED"}
    if bad:
        for (t, s), v in bad.items():
            print(f"🚨 baseline: {s}::{t} is {v} on UNBROKEN source")
        print("🚨 A break cannot prove anything about a clause that is not green to begin with.")
        return 1

    results = []
    try:
        for label, path, find, replace, test_name, suite in CASES:
            original = backups[path]
            n = original.count(find)
            if n == 0:
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            # ⭐ THE NF-INJ2b GUARD ON THE HARNESS ITSELF. A `replace(..., 1)` against a
            # non-unique anchor lands wherever the first match happens to be — which may be a
            # different symbol entirely, leaving the clause under test untouched and the harness
            # reporting a FALSE "GREEN — VACUOUS".
            if n > 1:
                results.append((label, test_name, f"AMBIGUOUS-ANCHOR (x{n})"))
                continue
            patched = original.replace(find, replace, 1)
            assert patched != original, label
            path.write_text(patched)
            try:
                outcome = run_one(test_name, suite)
            finally:
                path.write_text(original)
            results.append((label, test_name, {
                "PASSED": "GREEN — VACUOUS",
                "FAILED": "RED",
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
