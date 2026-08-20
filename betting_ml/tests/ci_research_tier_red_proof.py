"""RED proof for the TD4 research-tier guards — `uv run python betting_ml/tests/ci_research_tier_red_proof.py`.

The `research` tier takes a test OFF the merge bar. Its precondition — nothing under `scripts/`,
`app/` or `pipeline/` imports what the test guards — was prose from TD2 until now, with nothing
checking it. These breaks re-introduce each way it can rot.

⭐ THE FIRST BREAK IS THE REASON THIS EXISTS: a research module that LATER gains a serving importer
keeps its nightly-only tier silently, and the first sign is a production break that a non-blocking
job noticed hours earlier.

Same harness contract as the other RED proofs here: unique anchor, mutation must land, pytest in a
SUBPROCESS, only exit code 1 is RED, restore in a `finally`.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_fast_gate_hygiene.py"
_GUARD = "betting_ml/tests/test_fast_gate_hygiene.py"
_VICTIM = "scripts/write_serving_store.py"          # a real serving script
_RESEARCH = "betting_ml/tests/test_mh2_6_calibration_audit.py"

BREAKS = [
    # ⭐ the real-world case, simulated on a REAL serving file
    # ⚠️ the anchor is a UNIQUE line — `'"""'` appears 116 times in this file, and a
    # `replace(old, new, 1)` on it would land on an arbitrary docstring (E11.24 prediction_log).
    ("a research module GAINS a serving importer (the tier has rotted)", _VICTIM,
     "^import json$",
     "import json\nfrom betting_ml.scripts import mh2_6_calibration_audit  # noqa: F401", None,
     "no_research_module_has_gained"),

    ("a new research file is added and never registered", _RESEARCH,
     "@pytest.mark.slow\n@pytest.mark.research",
     "@pytest.mark.slow\n@pytest.mark.research",   # unchanged; the registry is what moves
     None, None),  # replaced below by a registry deletion instead

    ("the registry names a module that does not exist (a typo checks nothing)", _GUARD,
     '"betting_ml.scripts.mh2_6_calibration_audit",',
     '"betting_ml.scripts.mh2_6_calibration_audit_TYPO",',
     None, "registered_modules_actually_exist"),

    # ⛔ A BREAK WAS TRIED HERE AND REMOVED AS REDUNDANT, recorded rather than dropped silently:
    # "make the scanner ignore the `from pkg import mod` form". On a clean repo it is UNREACHABLE
    # (no serving file imports a research module, so narrowing the scan changes nothing), and it is
    # already covered by break #1 — the importer that break injects is written in exactly that
    # form, which is how the gap was found: the first scanner used string needles, missed it, and
    # reported a rotted tier as healthy.

    ("research detection goes back to a SUBSTRING scan (the guard finds itself)", _GUARD,
     '            if ci_shards._uses_marker(_REPO_ROOT / p, "research")]',
     '            if "mark.research" in (_REPO_ROOT / p).read_text()]',
     None, "declares_what_it_guards"),
]

# break #2 is a registry DELETION — expressed directly rather than as a source edit of the test file
BREAKS[1] = ("a research file is dropped from the registry (exhaustiveness)", _GUARD,
             '    "test_mh2_10_morning_audit.py": ("betting_ml.scripts.mh2_10_morning_audit",),\n',
             "", None, "declares_what_it_guards")


def main() -> int:
    failures = []
    for name, rel, old, new, _unused, selector in BREAKS:
        path = REPO / rel
        original = path.read_text()
        anchor = old[1:-1] if old.startswith("^") and old.endswith("$") else old
        n = original.count(anchor)
        if n != 1:
            print(f"{('BROKEN ❌ (anchor x%d)' % n):40} {name}")
            failures.append(f"{name}: anchor x{n}")
            continue
        mutated = original.replace(anchor, new, 1)
        if mutated == original:
            print(f"{'BROKEN ❌ (no-op mutation)':40} {name}")
            failures.append(f"{name}: mutation did not change the file")
            continue
        path.write_text(mutated)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TEST, "-q", "-k", selector,
                 "-p", "no:cacheprovider", "-o", "addopts="],
                cwd=REPO, capture_output=True, text=True)
            tail = (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else ""
            if proc.returncode == 1:
                verdict = "RED ✅"
            elif proc.returncode == 0:
                verdict = "GREEN ❌ (VACUOUS GUARD)"
                failures.append(name)
            else:
                verdict = f"BROKEN ❌ (rc={proc.returncode})"
                failures.append(f"{name}: rc={proc.returncode}")
            print(f"{verdict:40} {name}\n{'':40} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} deliberate breaks were caught ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
