"""RED proof for the orchestration-CD path guard —
`uv run python betting_ml/tests/nf_k1_cd_paths_red_proof.py`.

Same harness contract as `nf_k1_red_proof.py` / `nf_tr2_red_proof.py`: mutate the source, assert the
mutation LANDED (#682) and that the asserted token is GONE where relevant (#815), run pytest in a
SUBPROCESS (so `pytest.raises`' `Failed` cannot leak past a narrow `except` — NF-W6c), and treat ONLY
exit code 1 as RED (2/3/4/5 is a broken harness, never a caught break — NF-INFRA1).

⭐ THE FIRST BREAK IS THE ONE THAT MATTERS: it removes the NFL fantasy line, i.e. it restores the
repo to the exact state that let NF-K1 publish a board with no K/DST from a stale image. If that
does not go RED, this guard would not have caught the incident it was written for.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_orchestration_cd_paths.py"
_WF = ".github/workflows/orchestration_cd.yml"

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS = [
    ("🔴 the NF-K1 state itself: the NFL fantasy subtree does not trigger a deploy", _WF,
     '      - "quant_sports_intel_models/football/nfl/fantasy/**"\n',
     "",
     "every_box_run_subtree_triggers_a_deploy",
     '"quant_sports_intel_models/football/nfl/fantasy/**"'),
    ("the board SCORER (fantasy_engine) does not trigger a deploy", _WF,
     '      - "quant_sports_intel_models/fantasy_engine/**"\n',
     "",
     "every_box_run_subtree_triggers_a_deploy", None),
    ("the NFL ingest subtree does not trigger a deploy", _WF,
     '      - "quant_sports_intel_models/football/nfl/ingest/**"\n',
     "",
     "every_box_run_subtree_triggers_a_deploy", None),
    ("the NCAAF ingest subtree does not trigger a deploy", _WF,
     '      - "quant_sports_intel_models/football/ncaaf/ingest/**"\n',
     "",
     "every_box_run_subtree_triggers_a_deploy", None),
    ("a pinned-ML-lib bump does not rebuild the image (Dockerfile)", _WF,
     '      - "Dockerfile"\n', "",
     "image_build_inputs", None),
    ("a dependency bump does not rebuild the image (uv.lock)", _WF,
     '      - "uv.lock"\n', "",
     "image_build_inputs", None),
    ("scripts/ stops triggering a deploy (a previously-bitten entry removed)", _WF,
     '      - "scripts/**"\n', "",
     "long_standing_entries", None),
    ("betting_ml/ stops triggering a deploy", _WF,
     '      - "betting_ml/**"\n', "",
     "long_standing_entries", None),
    ("the API Lambda is wired to the BOX deploy (implying a deploy that never happens)", _WF,
     '      - "Dockerfile"\n',
     '      - "Dockerfile"\n      - "app/backend/**"\n',
     "lambda_and_frontend_are_not_wired", None),
    # ── the guard's own anti-vacuity floor ──────────────────────────────────────────────────────
    ("the derivation silently finds nothing (the guard would pass on an empty set)", TEST,
     'pattern = re.compile(r"quant_sports_intel_models[\\w.]*")',
     'pattern = re.compile(r"NOTHING_MATCHES_THIS_XX")',
     "derivation_is_not_vacuous", None),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        if old not in original:
            print(f"{'BROKEN ❌ (anchor not found)':30} {name}")
            failures.append(f"{name}: anchor not found in {rel}")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name                      # #682 — the mutation must land
        if gone is not None and gone in mutated:               # #815 — and must move the assertion
            print(f"{'BROKEN ❌ (token survives)':30} {name}")
            failures.append(f"{name}: asserted token survived")
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
                verdict = f"BROKEN ❌ (pytest rc={proc.returncode})"
                failures.append(f"{name}: harness rc={proc.returncode}")
            print(f"{verdict:30} {name}\n{'':30} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"all {len(BREAKS)} breaks caught — the CD path guard is RED-provable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
