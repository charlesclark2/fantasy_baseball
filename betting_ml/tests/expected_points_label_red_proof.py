#!/usr/bin/env python3
"""EXPECTED-POINTS LABEL RED PROOF — break the source one defect at a time, require the NAMED test
to go RED.

    uv run python betting_ml/tests/expected_points_label_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). Run it
by hand whenever `test_expected_points_label_copy.py` is refactored.

WHY IT EXISTS. This story's suite is copy governance plus source inspection — the two shapes this
repo has repeatedly shipped VACUOUS. NF-TR1 found four of its own guards passing against deliberately
broken source; INC-38 found a guard a COMMENT could satisfy. Neither was visible to review.

⭐ ONE ISOLATING CASE PER CLAUSE (NF-D17 §7). The obvious break — revert a header to "Proj pts" —
trips BOTH the per-surface clause and the registry-exhaustiveness clause, so it proves neither. So
the per-surface case swaps the constant for an equivalent LITERAL (exhaustiveness stays satisfied,
only the constant clause can flip) and the exhaustiveness case reintroduces a retired label in a
component the registry does NOT list (every per-surface clause stays satisfied). Each case names
the one thing it removes.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately NOT
`git checkout --` (see `nf_tr1_red_proof.py`: that shape ate uncommitted work at E9.59).
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COPY = REPO / "frontend/lib/fantasy-claim-copy.ts"
SHARED = REPO / "frontend/components/fantasy/shared.tsx"
TRACK = REPO / "frontend/components/fantasy/track-record-page.tsx"
RANKINGS = REPO / "frontend/components/fantasy/rankings-board.tsx"
# ⭐ NOT in `_POINTS_SURFACES` — which is exactly what makes it the right file for the
# exhaustiveness case: a retired label here can only be caught by the registry clause.
UNREGISTERED = REPO / "frontend/components/fantasy/draft-optimizer.tsx"
SUITE = "betting_ml/tests/test_expected_points_label_copy.py"

CASES = [
    # ── 1. the overclaim guards ───────────────────────────────────────────────────────────────
    ("drop 'not the only reason' — let the label absorb the residual miscalibration", COPY,
     "It is not the only reason a projection lands under a finished season, and we do not present it as one.",
     "",
     "test_the_note_states_that_availability_is_not_the_whole_story"),

    # ⚠️ Keeps the hedge sentence INTACT and adds a contradicting one — so the clause above stays
    # satisfied and only the "no sentence contradicts it" clause can flip.
    ("add a sentence claiming the games column explains the difference", COPY,
     "The projected-games column shows how much of that discount is availability for each player.",
     "The projected-games column shows how much of that discount is availability for each player. That is what accounts for the difference you see.",
     "test_the_note_does_not_promise_the_games_column_explains_the_gap"),

    ("soften the disclosure into an apology", COPY,
     "by design, not by accident",
     "and we are sorry it looks low",
     "test_the_framing_is_a_disclosure_and_not_an_apology"),

    # ── 2. the copy must actually say the thing ───────────────────────────────────────────────
    # Removes ONLY the "ours is lower" half; the missed-games half is untouched, so the sibling
    # assertion in the same clause is not what fires.
    ("stop telling the reader our number is deliberately lower", COPY,
     "so ours is deliberately lower — and lower by more at the positions that lose the most time to injury",
     "so it is computed differently from the numbers published elsewhere",
     "test_the_definition_names_missed_games_as_the_reason_the_number_is_lower"),

    ("drop the explanation of why projected games is a fraction", COPY,
     "It is an average across everything that could happen to him, not a prediction that he misses exactly that many weeks",
     "It is our projection for him",
     "test_the_projected_games_definition_explains_the_fractional_value"),

    ("hardcode a measured per-position figure into the definition", COPY,
     "lower by more at the positions that lose the most time to injury",
     "lower by a factor of 0.693 at running back",
     "test_the_new_copy_carries_no_measured_figure"),

    ("turn the definition into a market claim", COPY,
     "Most published projections are “if he plays every week” numbers",
     "Most published projections are guaranteed to be wrong",
     "test_the_new_copy_passes_the_track_record_denylist"),

    # ── 3. the methodology caution ────────────────────────────────────────────────────────────
    ("cite the outcome-bucketed decile comparison on the page", TRACK,
     "        {EXPECTED_POINTS_NOTE.title}",
     "        {EXPECTED_POINTS_NOTE.title} (see the top realized decile)",
     "test_no_surface_cites_the_outcome_bucketed_decile_comparison"),

    # ── 4. coverage ───────────────────────────────────────────────────────────────────────────
    # ⭐ ISOLATION: an equivalent literal, so the wording on screen is unchanged and the retired
    # labels stay absent — the exhaustiveness clause cannot fire, leaving only the constant clause.
    ("re-type one board's label as a literal instead of the canonical constant", RANKINGS,
     "<InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>",
     '<InfoTip label="Expected pts">{GLOSSARY.expectedPoints}</InfoTip>',
     "test_every_points_surface_labels_its_number_as_expected"),

    # ⭐ ISOLATION: in a component the registry does NOT list, so every per-surface clause stays
    # green and only the exhaustiveness clause can catch it — which is the whole claim being made
    # about the registry ("a surface added later cannot quietly ship with the old wording").
    ("ship a NEW surface still using a retired label", UNREGISTERED,
     "  const [started, setStarted] = useState(false)",
     '  const heading = "Proj pts"\n  const [started, setStarted] = useState(false)',
     "test_the_points_surface_registry_is_still_exhaustive"),

    ("re-type the definition prose into GLOSSARY, outside every copy screen", SHARED,
     "  expectedPoints: EXPECTED_POINTS_DEFINITION,",
     '  expectedPoints: "What we expect this player to score across the whole season.",',
     "test_the_definitions_are_the_canonical_constants_rather_than_retyped_prose"),

    # ⚠️ Keeps EXPECTED_POINTS_LABEL in the file (via the sibling projected-games header and the
    # import), so the coverage clause stays satisfied and only the tappability clause flips.
    ("downgrade the definition to a hover-only title attribute", TRACK,
     "<InfoTip label={EXPECTED_POINTS_LABEL}>{GLOSSARY.expectedPoints}</InfoTip>",
     "<span title={GLOSSARY.expectedPoints}>{EXPECTED_POINTS_LABEL}</span>",
     "test_the_definition_is_tappable_and_not_a_hover_only_tooltip"),
]


def run(test_name):
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-400:]


def main():
    backups = {p: p.read_text() for p in {COPY, SHARED, TRACK, RANKINGS, UNREGISTERED}}
    failures = []
    try:
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for name, path, old, new, test in CASES:
            src = backups[path]
            if old not in src:
                failures.append(f"{name}: PATCH ANCHOR NOT FOUND in {path.name}")
                print(f"⚠️  {name}: anchor not found in {path.name} (the source moved)")
                continue
            path.write_text(src.replace(old, new, 1))
            code, out = run(test)
            path.write_text(src)
            print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print("\n❌ VACUOUS CLAUSES:\n  " + "\n  ".join(failures))
        return 1
    print(f"\n✅ every clause RED-proven ({len(CASES)}/{len(CASES)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
