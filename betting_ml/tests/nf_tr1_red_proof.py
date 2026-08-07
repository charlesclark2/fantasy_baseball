#!/usr/bin/env python3
"""NF-TR1 RED PROOF — break the source one defect at a time, require the NAMED test to go RED.

    uv run python betting_ml/tests/nf_tr1_red_proof.py

⚠️ NOT COLLECTED BY PYTEST (no `test_` prefix, and `scripts/ci_shards.py` globs `test_*.py`). It is
a developer tool, run by hand whenever `test_nf_tr1_claim_copy.py` is refactored.

WHY IT EXISTS. NF-TR1 is a COPY-GOVERNANCE story: its tests assert that a sentence contains a
hedge. That is exactly the shape that reads as coverage while proving nothing — this repo has been
bitten by a source-inspection guard a COMMENT could satisfy, and by an `and`-composed rule whose
fixture was already refused by a different clause. Both were found only by deliberately breaking
the source and noticing the guard stayed green.

⭐ IT ALREADY EARNED ITS KEEP. On the first run, `test_the_headline_adp_claim_is_not_swapped_for_
the_flattering_source` stayed GREEN with the population pin DELETED OUTRIGHT — because
`P0_shipped × adp` happens to be the FIRST row in the committed NF-D17 artifact, so "take whatever
comes first" returned the right answer by luck. That clause now runs against a list where a
flattering cell leads and the real one is buried. A test written against a real artifact inherits
that artifact's incidental ordering; only a break proves whether the assertion or the accident is
doing the work.

Restores every file from an in-memory backup in a `finally` block. ⛔ Deliberately does NOT use
`git checkout --` the way `frontend/e2e/red-proof.mjs` does — that harness destroys uncommitted
work in the files it patches (it ate an in-progress `subscribe/page.tsx` at E9.59).
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXPORT = REPO / "quant_sports_intel_models/football/nfl/fantasy/export_track_record_json.py"
PAGE = REPO / "frontend/components/fantasy/track-record-page.tsx"
FIXTURE = REPO / "frontend/e2e/fixtures/api/fantasy-nfl-track-record-manifest.json"
SUITE = "betting_ml/tests/test_nf_tr1_claim_copy.py"

CASES = [
    ("drop the 'gap is small' caveat", EXPORT,
     'caveats = ["the gap is small", "it swings a lot from year to year and from position to position"]',
     'caveats = ["it swings a lot from year to year and from position to position"]',
     "test_the_lead_says_the_gap_is_small"),

    ("hardcode the luck hedge ON", EXPORT,
     '    if could_be_luck:\n        hedge += " It is small enough that it could just be luck',
     '    if True:\n        hedge += " It is small enough that it could just be luck',
     "test_the_luck_hedge_is_dropped_when_the_interval_excludes_zero"),

    ("hardcode the luck hedge OFF", EXPORT,
     '    if could_be_luck:\n        hedge += " It is small enough that it could just be luck',
     '    if False:\n        hedge += " It is small enough that it could just be luck',
     "test_the_lead_carries_the_luck_hedge_while_zero_is_in_the_interval"),

    ("hardcode 'running back' as the level position", EXPORT,
     'caveats.append(f"and at {_join(level_positions)} it is basically even")',
     'caveats.append("and at running back it is basically even")',
     "test_the_level_position_is_read_from_the_data_not_asserted"),

    ("emit the approved sentence unconditionally", EXPORT,
     "    if gap > 0 and could_be_luck:\n        approved = (",
     "    if True:\n        approved = (",
     "test_the_approved_sentence_is_withdrawn_when_the_shape_changes"),

    ("put the benchmark comparison ahead of the calibration hook", EXPORT,
     'return " ".join([hook, record, hedge])',
     'return " ".join([record, hedge, hook])',
     "test_calibration_leads_the_consumer_lead"),

    ("drop the governance term 'market-beating' from the export denylist", EXPORT,
     '"beats the market", "outperforms the market", "market-beating", "profitable",',
     '"beats the market", "outperforms the market", "profitable",',
     "test_the_export_denylist_is_a_superset_of_the_governance_gate"),

    ("stop reconciling the interval against the scorecard", EXPORT,
     "    _reconcile(agg, unc, adp_seasons)",
     "    pass  # _reconcile removed",
     "test_an_interval_from_a_different_reading_is_refused"),

    ("accept an un-evaluated bootstrap", EXPORT,
     '            if not boot.get("evaluated"):',
     '            if False:',
     "test_an_uncomputed_bootstrap_is_refused_rather_than_silently_dropped"),

    ("select whatever population row comes first", EXPORT,
     '        if row.get("population") == "P0_shipped" and row.get("source") == "adp":',
     '        if True:',
     "test_the_headline_adp_claim_is_not_swapped_for_the_flattering_source"),

    ("render the claim above the calibration hook", PAGE,
     "      <CalibrationLead />\n",
     "",
     "test_the_page_renders_calibration_before_the_benchmark_claim"),

    ("fall back to the legacy headline in the lead", PAGE,
     "              <ClaimLead lead={manifest.claim.lead} />",
     "              <ClaimLead lead={manifest.claim?.lead ?? manifest.headline} />",
     "test_the_page_never_promotes_a_legacy_headline_into_the_lead"),

    ("stop rendering the position table", PAGE,
     "              <PositionTable rows={manifest.claim.byPosition} />\n",
     "",
     "test_the_position_table_reaches_the_rendered_page"),
]


def run(test_name):
    r = subprocess.run(
        ["uv", "run", "pytest", f"{SUITE}::{test_name}", "-q", "--no-header", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True,
    )
    return r.returncode, r.stdout[-400:]


def main():
    backups = {p: p.read_text() for p in {EXPORT, PAGE, FIXTURE}}
    failures = []
    try:
        # sanity: everything green before we break anything
        r = subprocess.run(["uv", "run", "pytest", SUITE, "-q", "--no-header"],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print("BASELINE IS NOT GREEN — aborting\n" + r.stdout[-2000:])
            return 1
        print("baseline GREEN\n")

        for name, path, old, new, test in CASES:
            src = backups[path]
            if old not in src:
                failures.append(f"{name}: PATCH ANCHOR NOT FOUND")
                print(f"⚠️  {name}: anchor not found")
                continue
            path.write_text(src.replace(old, new, 1))
            code, out = run(test)
            path.write_text(src)
            verdict = "RED ✅" if code != 0 else "GREEN ❌ (vacuous!)"
            print(f"{verdict}  {name}  ->  {test}")
            if code == 0:
                failures.append(f"{name} -> {test} stayed GREEN")
                print("   " + out.replace("\n", "\n   "))

        # fixture-drift case: mutate the generated claim block
        fx = json.loads(backups[FIXTURE])
        fx["claim"]["lead"] = fx["claim"]["lead"].replace("a little closer", "far closer")
        FIXTURE.write_text(json.dumps(fx, indent=2) + "\n")
        code, out = run("test_the_e2e_fixture_claim_is_the_shipping_builders_own_output")
        FIXTURE.write_text(backups[FIXTURE])
        print(f"{'RED ✅' if code else 'GREEN ❌ (vacuous!)'}  edit the fixture's claim copy by hand"
              f"  ->  test_the_e2e_fixture_claim_is_the_shipping_builders_own_output")
        if code == 0:
            failures.append("fixture drift stayed GREEN")
    finally:
        for p, src in backups.items():
            p.write_text(src)
        print("\nrestored all files")

    if failures:
        print("\n❌ VACUOUS CLAUSES:\n  " + "\n  ".join(failures))
        return 1
    print("\n✅ every clause RED-proven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
