#!/usr/bin/env python3
"""E9.61 RED PROOF — break the source one clause at a time, require the NAMED test to fail.

    uv run python betting_ml/tests/e9_61_generic_delta_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, run whenever `test_e9_61_generic_delta.py` is touched.

WHY. That suite is almost entirely SOURCE INSPECTION, which is the shape that reads as coverage
while proving nothing — this repo has shipped it twice (a guard a COMMENT could satisfy, INC-38; an
`and`-clause whose fixture a DIFFERENT clause already refused, NF-D17). Neither was found by reading
the test.

⭐ EACH CASE NAMES ONE TEST and asserts THAT test goes red. Turning the whole file red proves much
less: it can mean the clause worked, or that the import broke.

⭐ AND EACH BREAK IS ISOLATING — it trips exactly the clause it names and leaves the others'
preconditions satisfied. That is the NF-D17 lesson: a fixture that trips two clauses at once proves
neither, because either one could be the reason it went red.

Restores every file from an in-memory backup in a `finally`. ⛔ Never `git checkout --`, which would
destroy uncommitted work in the files it patches.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
LEAGUE_BOARD = REPO / "frontend/components/fantasy/league-board.tsx"
MY_LEAGUE = REPO / "frontend/components/fantasy/my-league.tsx"
DRAFT = REPO / "frontend/components/fantasy/draft-optimizer.tsx"
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
GUARDRAILS = REPO / "app/backend/services/cost_guardrails.py"

SUITE = "betting_ml/tests/test_e9_61_generic_delta.py"

# (label, file, [(find, replace)…], test_that_must_go_red)
CASES = [
    # ── axis one: WHO renders personalization ─────────────────────────────────────────────────
    #
    # A FOURTH renderer appears. This is the #681 shape exactly: the delta gets added to another
    # surface and nobody re-asks the gating question. The draft optimizer is the honest choice of
    # victim — it is a real fantasy surface that does not render the delta today.
    ("a fourth component starts rendering the delta", DRAFT,
     [('import Link from "next/link"',
       'import Link from "next/link"\n'
       'import { GenericDeltaCell } from "@/components/fantasy/league-delta-ui"')],
     "test_exactly_the_declared_components_render_the_delta"),

    # ── axis one, the gate itself ─────────────────────────────────────────────────────────────
    #
    # ⭐ THE BREAK THAT MATTERS. The delta is computed for EVERY caller and merely hidden in the
    # render — which is how this would actually regress. Note it leaves the label, the renderer set
    # and every cache clause untouched: only the `isCustom` clause can see it.
    ("Rankings computes the delta for every caller", RANKINGS,
     [("      isCustom\n        ? computeLeagueDelta(genericBoard, board, pool, LOW_PREDICTABILITY_POSITIONS)\n        : null,",
       "      computeLeagueDelta(genericBoard, board, pool, LOW_PREDICTABILITY_POSITIONS),")],
     "test_a_browse_board_only_computes_the_delta_for_a_custom_league[components/fantasy/rankings-board.tsx]"),

    ("the League Board computes the delta for every caller", LEAGUE_BOARD,
     [("      isCustom ? computeLeagueDelta(genericBoard, board, pool, LOW_PREDICTABILITY_POSITIONS) : null,",
       "      computeLeagueDelta(genericBoard, board, pool, LOW_PREDICTABILITY_POSITIONS),")],
     "test_a_browse_board_only_computes_the_delta_for_a_custom_league[components/fantasy/league-board.tsx]"),

    # ── the label ─────────────────────────────────────────────────────────────────────────────
    #
    # One renderer goes its own way. ⚠️ Deliberately a DIFFERENT literal per renderer below, so each
    # parametrized case is isolating: breaking Rankings must not turn My League's case red too.
    ("Rankings hardcodes its own delta label", RANKINGS,
     [("<InfoTip label={GENERIC_DELTA_LABEL}>", '<InfoTip label={"Move"}>')],
     "test_no_renderer_spells_the_label_itself[components/fantasy/rankings-board.tsx]"),

    ("My League reverts to its pre-E9.61 label", MY_LEAGUE,
     [("<InfoTip label={GENERIC_DELTA_LABEL}>", '<InfoTip label={"vs free board"}>')],
     "test_no_renderer_spells_the_label_itself[components/fantasy/my-league.tsx]"),

    # The label stops naming its comparison. `"Movement"` is the plausible wrong answer — it reads
    # fine and inherits the category's "versus ADP" meaning for free.
    ("the shared label goes ambiguous", COPY,
     [('export const GENERIC_DELTA_LABEL = "vs our generic board"',
       'export const GENERIC_DELTA_LABEL = "Movement"')],
     "test_the_label_names_the_comparison_rather_than_inheriting_the_market_reading"),

    # The other side of the same clause: a label that names ADP is worse than a vague one, because
    # it asserts a market comparison this number is not.
    ("the label claims an ADP comparison", COPY,
     [('export const GENERIC_DELTA_LABEL = "vs our generic board"',
       'export const GENERIC_DELTA_LABEL = "vs generic ADP"')],
     "test_the_label_names_the_comparison_rather_than_inheriting_the_market_reading"),

    # ── axis two: the edge ────────────────────────────────────────────────────────────────────
    #
    # Someone "optimises" the personalization read onto the CDN. This is the breach
    # `cache_control_for` exists to prevent, arriving as a one-line config change rather than as
    # code — which is exactly why it needs a test and not a comment.
    ("the saved-league read becomes shared-cacheable", GUARDRAILS,
     [('    ("/blog/posts", 600, 3600),', '    ("/blog/posts", 600, 3600),\n    ("/fantasy/leagues", 900, 3600),')],
     "test_a_personalization_read_is_never_shared_cacheable[/fantasy/leagues]"),

    ("the my-teams read becomes shared-cacheable", GUARDRAILS,
     [('    ("/blog/posts", 600, 3600),', '    ("/blog/posts", 600, 3600),\n    ("/fantasy/nfl/my-teams", 900, 3600),')],
     "test_a_personalization_read_is_never_shared_cacheable[/fantasy/nfl/my-teams]"),

    # Personalization joins the degrade floor — i.e. the spend kill switch stops containing the one
    # class of read that is per-caller.
    ("personalization joins the degrade floor", GUARDRAILS,
     [('    "/blog/posts",', '    "/blog/posts",\n    "/fantasy/leagues",\n    "/fantasy/nfl/my-teams",')],
     "test_the_delta_added_no_new_endpoint_to_the_degrade_floor"),

    # ⭐ THE OTHER SIDE, and it is the half a "nothing is allowlisted" clause would miss: the free
    # board LEAVING the floor. The delta's generic side has to stay up in degrade mode, or a cost
    # event silently turns the free product off. A guard that only checks for extra entries would
    # score this healthy.
    ("the free board falls OUT of the degrade floor", GUARDRAILS,
     [('    "/fantasy/nfl/board",\n', "")],
     "test_the_delta_added_no_new_endpoint_to_the_degrade_floor"),

    # And the `Authorization` braces, independent of the prefix lists above.
    ("an authenticated response stops being private", GUARDRAILS,
     [("    if has_authorization:\n        return PRIVATE_CACHE_CONTROL",
       "    if has_authorization and False:\n        return PRIVATE_CACHE_CONTROL")],
     "test_an_authenticated_read_of_one_is_private_no_store[/fantasy/leagues]"),
]


def run_one(test_name: str) -> bool:
    """True if the named test PASSES."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode == 0


def main() -> int:
    backups = {p: p.read_text() for p in {c[1] for c in CASES}}
    results = []
    try:
        for label, path, patches, test_name in CASES:
            original = backups[path]
            if any(f not in original for f, _ in patches):
                results.append((label, test_name, "ANCHOR-MISSING"))
                continue
            patched = original
            for f, r in patches:
                patched = patched.replace(f, r, 1)
            path.write_text(patched)
            try:
                passed = run_one(test_name)
            finally:
                path.write_text(original)
            results.append((label, test_name, "GREEN — VACUOUS" if passed else "RED"))
    finally:
        for p, text in backups.items():
            p.write_text(text)

    width = max(len(label) for label, _, _ in results)
    red = sum(s == "RED" for _, _, s in results)
    for label, test_name, status in results:
        print(f"{'✅' if status == 'RED' else '🚨'} {label.ljust(width)}  →  {status}   ({test_name})")

    print(f"\n{red}/{len(results)} breaks turned their named clause RED.")
    if red != len(results):
        print("🚨 A clause that stays GREEN with the thing it names broken is not a guard.")
    return 0 if red == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
