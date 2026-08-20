"""RED proof for the NF-C7c cap guards — `uv run python betting_ml/tests/nf_c7c_red_proof.py`.

Same harness contract as `nf_c7_red_proof.py` / `nf_c7b_red_proof.py`: the anchor must be UNIQUE,
the mutation must LAND, any asserted token must be GONE, pytest runs in a SUBPROCESS, only exit code
1 counts as RED, and the file is restored in a `finally`.

⭐ THE SECOND BREAK IS THE ONE THAT MATTERS. Collapsing three depth states into two is the obvious
way to write this feature and it is WRONG in a way nothing user-facing would show: a target on ONE
position silently demotes every position the user never mentioned. It is caught only by a clause
that compares an untargeted position's rank before and after.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_nf_c7c_depth_target_cap.py"
_DRAFT = "quant_sports_intel_models/fantasy_engine/draft.py"

#: (name, file, old, new, pytest -k selector, token that must be GONE or None)
BREAKS = [
    ("cap: revert to a FLOOR only (the shipped defect — a satisfied target does nothing)", _DRAFT,
     "            if depth_short > 0:\n                depth_tier = DEPTH_SHORT\n"
     "            elif target > 0:\n                depth_tier = DEPTH_SATISFIED",
     "            if depth_short > 0:\n                depth_tier = DEPTH_SHORT",
     "removes_that_position_from_the_panel", "depth_tier = DEPTH_SATISFIED"),

    ("cap: collapse THREE states into two, so an UNTARGETED position is demoted too", _DRAFT,
     "        depth_tier = DEPTH_NEUTRAL\n        if level == 0 and depth_targets:",
     "        depth_tier = DEPTH_SATISFIED if (level == 0 and depth_targets) else DEPTH_NEUTRAL\n"
     "        if level == 0 and depth_targets:",
     "left_neutral", None),

    ("cap: let it reach a candidate filling an OPEN starter slot", _DRAFT,
     "        if level == 0 and depth_targets:\n            target = int(depth_targets.get(pos, 0))",
     "        if depth_targets:\n            target = int(depth_targets.get(pos, 0))",
     "open_starter_slot or starve_the_reserve or carry_a_depth_TIER", "if level == 0 and depth_targets:"),

    # ⛔ A BREAK WAS TRIED HERE AND REMOVED AS UNREACHABLE, recorded rather than deleted silently:
    # moving `depth_tier` ahead of `must_fill` in the final sort changes NOTHING, because the two
    # are disjoint by construction (`must_fill` needs level > 0, a depth tier is assigned only at
    # level == 0). Measured: in a reserve-binding state every candidate is a K or D/ST filling an
    # open slot, so every row is level > 0 and every tier is neutral. The invariant that actually
    # protects the reserve constraint is "a must_fill row never carries a tier", which break #3
    # below violates — so it is guarded, just not by an ordering test.

    ("cap: drop the tier from the bench RE-RANK, so the demotion never reaches the panel", _DRAFT,
     "                        key=lambda r: (r.depth_tier, -r.score, -r.order_value, r.player_id))",
     "                        key=lambda r: (-r.score, -r.order_value, r.player_id))",
     "removes_that_position_from_the_panel", None),

    ("cap: stop stating the demotion on the row (an invisible preference)", _DRAFT,
     "    elif depth_tier == DEPTH_SATISFIED:",
     "    elif False:",
     "stated_on_the_row", "elif depth_tier == DEPTH_SATISFIED:"),

    ("tiers: make SATISFIED sort ABOVE neutral (the cap becomes a promotion)", _DRAFT,
     "DEPTH_SHORT = -1\nDEPTH_NEUTRAL = 0\nDEPTH_SATISFIED = 1",
     "DEPTH_SHORT = -1\nDEPTH_NEUTRAL = 0\nDEPTH_SATISFIED = -2",
     "ordered or removes_that_position", None),
]


def main() -> int:
    failures = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()
        n = original.count(old)
        if n != 1:
            print(f"{('BROKEN ❌ (anchor x%d)' % n):36} {name}")
            failures.append(f"{name}: anchor appears {n}x")
            continue
        mutated = original.replace(old, new, 1)
        assert mutated != original, name
        if gone is not None and gone in mutated:
            print(f"{'BROKEN ❌ (token survives)':36} {name}")
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
                verdict = f"BROKEN ❌ (rc={proc.returncode})"
                failures.append(f"{name}: rc={proc.returncode}")
            print(f"{verdict:36} {name}\n{'':36} -> {tail}")
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
