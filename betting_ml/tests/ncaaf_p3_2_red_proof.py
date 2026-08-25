#!/usr/bin/env python3
"""NCAAF-P3.2 RED PROOF — break the source one defect at a time, require the NAMED clause to go RED.

    uv run python betting_ml/tests/ncaaf_p3_2_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix; `scripts/ci_shards.py` globs `test_*.py`). A
developer tool, re-run whenever `test_ncaaf_p3_2_surface.py` is refactored.

WHY. A copy-governance suite is exactly the shape that reads as coverage while proving nothing, and
this repo has been bitten by it repeatedly — a source scan a COMMENT could satisfy (INC-38), a
clause whose fixture was already refused by a different clause in the same conjunction (NF-D17), a
mutation that landed on the WRONG symbol because two functions shared a tail (E11.24), and a
mutation that landed and did not move the asserted predicate (#815).

⭐ EVERY ONE OF THOSE FAILURE MODES IS CHECKED HERE, NOT ASSUMED:

  * THE ANCHOR MUST BE UNIQUE — `old` must appear EXACTLY ONCE in the file, so a `replace(…, 1)`
    cannot silently patch a different occurrence and report a FALSE "the guard is vacuous", which
    is the dangerous direction (it invites weakening a correct guard).
  * THE MUTATION MUST LAND — the file on disk must differ afterwards.
  * THE PREDICATE MUST MOVE — where a clause asserts a token's PRESENCE, the token must be ABSENT
    after the break; an `x in src` assertion is blind to a suffix rename and to a break that writes
    without changing what is asserted.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately NOT
`git checkout --`, which would destroy uncommitted work in the files it patches.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/ncaaf-copy.ts"
CURVE = REPO / "frontend/lib/ncaaf-curve.ts"
DATA = REPO / "frontend/lib/ncaaf.ts"
PANEL = REPO / "frontend/components/ncaaf/market-comparison.tsx"
CARD = REPO / "frontend/components/ncaaf/game-card.tsx"
PAGE = REPO / "frontend/components/ncaaf/games-page.tsx"
DEGRADED_FX = REPO / "frontend/e2e/fixtures/api/ncaaf-slate-degraded.synthetic.json"
CAPTURED_FX = REPO / "frontend/e2e/fixtures/api/ncaaf-slate-2026-08-29.json"

SUITE = "betting_ml/tests/test_ncaaf_p3_2_surface.py"

TOUCHED = {COPY, CURVE, DATA, PANEL, CARD, PAGE, DEGRADED_FX, CAPTURED_FX}

#: (name, file, old, new, test, gone) — `gone`, when given, is a substring the mutation must REMOVE
#: from the file. That is the #815 lesson: a break that writes but leaves the asserted predicate
#: intact comes back GREEN and reads as a vacuous guard when the guard is fine.
CASES = [
    # ── the denylist, over the copy module and over a component's JSX ──────────────────────────
    ("write an edge claim into the market framing", COPY,
     "We make no claim to an advantage over the market",
     "We beat the market more often than not",
     "test_every_ncaaf_frontend_string_passes_the_claim_denylist",
     "We make no claim to an advantage over the market"),

    ("write an overclaim into a COMPONENT's JSX text, where no copy module can see it", CARD,
     "<span className=\"px-1.5 text-gray-600\">at</span>",
     "<span className=\"px-1.5 text-gray-600\">guaranteed</span>",
     "test_every_ncaaf_frontend_string_passes_the_claim_denylist",
     None),

    ("hardcode a measured figure into the copy module", COPY,
     'export const PAGE_TITLE = "College football projections"',
     'export const PAGE_TITLE = "College football projections, calibrated to 0.7603"',
     "test_the_copy_module_carries_no_measured_figure",
     None),

    # ── the structural clauses ────────────────────────────────────────────────────────────────
    ("duplicate the SERVED disclosure as a frontend constant", COPY,
     "export const PAGE_TITLE =",
     'export const LOCAL_DISCLOSURE =\n  "These are market-blind projections: probabilities and '
     'distributional intervals from a model that never sees a betting line."\n'
     "export const PAGE_TITLE =",
     "test_the_served_disclosure_is_never_duplicated_in_the_frontend",
     None),

    ("write a sentence inline in a component instead of in the copy module", CARD,
     "{TEAM_PAGE_STUB_LABEL}\n        </button>",
     "Our projection for this game is the sharpest number you will find anywhere\n        </button>",
     "test_the_prose_lives_in_the_copy_module_not_in_the_components",
     None),

    ("name a client-side edge quantity", PANEL,
     "  const marketHomeMargin =",
     "  const edge = 1\n  const marketHomeMargin =",
     "test_no_ncaaf_frontend_identifier_names_a_pick_or_an_edge",
     None),

    ("add a difference column to the model-and-market panel", PANEL,
     "  const margin = modelCentre(game.margin)",
     "  const marginGap = 0\n  const margin = modelCentre(game.margin)",
     "test_the_market_panel_names_no_difference_between_the_two_columns",
     None),

    # ── fixture provenance ────────────────────────────────────────────────────────────────────
    ("hand-edit a GENERATED fixture instead of re-running its generator", DEGRADED_FX,
     '"mu": 6.0,',
     '"mu": 9.0,',
     "test_the_generated_fixtures_are_the_shipping_builders_own_output",
     None),

    # ⚠️ ANCHORED ON A GAME ID, because every other candidate anchor in an 8-game slate occurs
    # eight times — the uniqueness check above REFUSED the first attempt at this case, which is the
    # protection working rather than an inconvenience.
    ("hand-edit the CAPTURED slate into a payload the contract cannot carry", CAPTURED_FX,
     '"game_id": 401856766,',
     '"game_id": 401856766,\n      "model_advantage_points": 3.5,',
     "test_the_captured_fixtures_are_payloads_the_server_could_actually_send[slate]",
     None),
]

#: Cases whose intent IS every occurrence. The uniqueness rule is waived HERE AND ONLY HERE, and it
#: is named per case rather than being a flag anyone can set: "a re-capture landed a market line on
#: the whole slate" is not a defect you can express by editing one game.
GLOBAL_CASES = [
    ("a re-capture that quietly lands a market line on every game", CAPTURED_FX,
     '"status": "unavailable"',
     '"status": "available"',
     "test_the_captured_slate_still_holds_the_state_the_specs_reason_from",
     '"status": "unavailable"'),
]


def run(test_name):
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-500:]


def main():
    backups = {p: p.read_text() for p in TOUCHED}
    failures = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for name, path, old, new, test, gone in CASES + GLOBAL_CASES:
            src = backups[path]
            every = (name, path, old, new, test, gone) in GLOBAL_CASES

            # ⭐ THE ANCHOR MUST BE UNIQUE. Two identical tails is how a mutation lands on the wrong
            # symbol and reports a FALSE vacuity (E11.24).
            occurrences = src.count(old)
            if not every and occurrences != 1:
                failures.append(f"{name}: anchor occurs {occurrences}x (must be exactly 1)")
                print(f"⚠️  {name}: anchor occurs {occurrences}x — refusing to patch")
                continue
            if every and occurrences < 2:
                failures.append(f"{name}: declared GLOBAL but the anchor occurs {occurrences}x")
                print(f"⚠️  {name}: declared GLOBAL but occurs {occurrences}x")
                continue

            patched = src.replace(old, new) if every else src.replace(old, new, 1)
            path.write_text(patched)
            # ⭐ THE MUTATION MUST LAND (#682) …
            landed = path.read_text() != src
            # … AND THE ASSERTED PREDICATE MUST MOVE (#815).
            moved = gone is None or gone not in path.read_text()
            code, out = run(test)
            path.write_text(src)

            if not landed:
                failures.append(f"{name}: the mutation did not land on disk")
                print(f"⚠️  {name}: mutation did not land")
                continue
            if not moved:
                failures.append(f"{name}: the mutation landed but left {gone!r} in place")
                print(f"⚠️  {name}: predicate did not move")
                continue

            verdict = "RED ✅" if code != 0 else "GREEN ❌ (vacuous!)"
            print(f"{verdict}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print("\n❌ VACUOUS OR MIS-AIMED CLAUSES:\n  " + "\n  ".join(failures))
        return 1
    n = len(CASES) + len(GLOBAL_CASES)
    print(f"\n✅ {n}/{n} clauses RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
