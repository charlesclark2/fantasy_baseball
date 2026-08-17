"""nf_c5_red_proof.py — prove the NF-C5 auction guards can actually FAIL.

A guard nobody has watched fail is not a guard (NF1.7(a) / INC-38 / NF-D17). This applies a
deliberate break to `fantasy_engine/auction.py`, runs the suite, and demands it goes RED — then
restores the file.

Three lessons from this repo's own history are wired in, because each has produced a FALSE result:

  * #682 — ASSERT THE MUTATION LANDED. A break that silently no-ops makes the suite pass and gets
    reported as "the guard is vacuous", which reads as a real finding and invites weakening a
    correct guard.
  * #885 — ASSERT THE ANCHOR IS UNIQUE. Two functions with byte-identical tails make a
    `replace(old, new, 1)` land on the WRONG one, and the run comes back green for the same
    misleading reason.
  * #815 — ASSERT THE OLD TOKEN IS GONE. A mutation that writes without changing the asserted
    predicate is a false green.

Run:  uv run python betting_ml/tests/nf_c5_red_proof.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_AUCTION = _ROOT / "quant_sports_intel_models/fantasy_engine/auction.py"
_SUITE = "betting_ml/tests/test_fantasy_auction_values.py"

# (label, target substring, replacement, consequence, expect_red)
#
# ⭐ `expect_red=False` IS A FINDING, NOT AN EXEMPTION. A break that leaves the suite green is
# either a vacuous guard (bad) or genuinely unreachable code (fine, and worth SAYING so). Recording
# which — with the reason, checked by this script rather than asserted in prose — is the difference
# between "we know that line is belt-and-braces" and "we never looked".
BREAKS: list[tuple[str, str, str, str, bool]] = [
    (
        "drop the never-strand reserve",
        "affordable = budget - int(min_bid) * (slots - 1)",
        "affordable = budget",
        "a bid may now consume the money the remaining spots need",
        True,
    ),
    (
        "off-by-one in the reserve",
        "affordable = budget - int(min_bid) * (slots - 1)",
        "affordable = budget - int(min_bid) * (slots - 2)",
        "leaves one spot short — the exact boundary the grid exists to find",
        True,
    ),
    (
        # STAYS GREEN, and correctly: `_pos` already clamps VOR at zero and `rate` is non-negative,
        # so `min_bid + rate*x >= min_bid` by construction and this clamp is UNREACHABLE. The load-
        # bearing guard for "nobody prices below the minimum" is the `_pos` break below, which does
        # go red. Kept in the code as defence-in-depth against a future change to `_pos`, and kept
        # here so the next reader knows which of the two is actually holding the line.
        "drop the (redundant) minimum-bid floor on a value",
        "return max(pool.min_bid, int(round(pool.min_bid + rate * x)))",
        "return int(round(pool.min_bid + rate * x))",
        "nothing — unreachable given the _pos clamp",
        False,
    ),
    (
        "let a below-replacement VOR subtract from the pool",
        "    return max(0.0, f)",
        "    return f",
        "the long negative tail shrinks the denominator and inflates every value",
        True,
    ),
    (
        "count the un-draftable tail in inflation",
        "top = sorted((int(v) for v in remaining_values), reverse=True)[:slots]",
        "top = sorted((int(v) for v in remaining_values), reverse=True)",
        "the $1 tail drags the denominator up and understates inflation all draft",
        True,
    ),
    (
        "let inflation divide by zero into an infinity",
        "mult = (dollars / value_remaining) if value_remaining > 0 else 1.0",
        "mult = (dollars / value_remaining) if value_remaining > 0 else float('inf')",
        "'∞' renders beside a dollar sign (the fullSeasonRate class)",
        True,
    ),
    (
        "stop ordering a crossed band",
        "                low=min(lo, hi),",
        "                low=lo,",
        "a crossed source interval renders as a backwards $ band",
        True,
    ),
    (
        "move the value model without regenerating the golden vectors",
        "DEFAULT_MIN_BID = 1",
        "DEFAULT_MIN_BID = 2",
        "the committed vectors — which the TS side is pinned to — go stale unnoticed",
        True,
    ),
]


def _purge_bytecode() -> None:
    """⚠️⚠️ THE TRAP THIS SCRIPT SET FOR ITSELF, and it survived the restore.

    CPython validates a cached `.pyc` on (mtime, SIZE). The `DEFAULT_MIN_BID = 1` → `2` break is
    byte-identical in LENGTH, and the restore lands inside the same one-second mtime tick — so both
    checks pass and the NEXT process to import `auction.py` gets the MUTATED bytecode back from
    `__pycache__` while the source on disk reads correct. That poisoned an unrelated smoke run right
    after this script reported success (a $2 minimum bid on a board whose source says $1), and it
    would have been read as an exporter bug.

    Belt and braces: never write bytecode from the mutated source, and sweep any that exists.
    """
    for pycache in _ROOT.joinpath("quant_sports_intel_models/fantasy_engine").rglob("__pycache__"):
        for f in pycache.glob("*.pyc"):
            f.unlink(missing_ok=True)


def run_suite() -> bool:
    """True when the suite is GREEN."""
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", _SUITE, "-qx", "--no-header",
         "-p", "no:cacheprovider"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    return r.returncode == 0


def main() -> int:
    original = _AUCTION.read_text()
    if not run_suite():
        print("✗ the suite is RED before any mutation — fix that first")
        return 1

    failures: list[str] = []
    try:
        for label, target, replacement, consequence, expect_red in BREAKS:
            occurrences = original.count(target)
            if occurrences != 1:
                failures.append(
                    f"{label}: anchor appears {occurrences}x (need exactly 1) — a "
                    f"replace() would land on the wrong symbol (#885)"
                )
                continue
            broken = original.replace(target, replacement, 1)
            if broken == original:
                failures.append(f"{label}: the mutation did not change the file (#682)")
                continue
            if target in broken:
                failures.append(f"{label}: the mutated token is still present (#815)")
                continue
            _AUCTION.write_text(broken)
            green = run_suite()
            _AUCTION.write_text(original)
            if green and expect_red:
                failures.append(f"{label}: suite stayed GREEN — {consequence} goes uncaught")
                print(f"  ✗ {label} → GREEN (expected RED)")
            elif not green and not expect_red:
                # Also a defect: a break DOCUMENTED as unreachable turning red means the comment
                # explaining why it is unreachable has gone stale.
                failures.append(
                    f"{label}: went RED but is recorded as unreachable — update the reasoning"
                )
                print(f"  ✗ {label} → RED (recorded as unreachable)")
            elif green:
                print(f"  · {label} → GREEN, as recorded ({consequence})")
            else:
                print(f"  ✓ {label} → RED")
    finally:
        _AUCTION.write_text(original)
        _purge_bytecode()

    assert _AUCTION.read_text() == original, "failed to restore auction.py"
    if failures:
        print("\nVACUOUS GUARDS:")
        for f in failures:
            print(f"  - {f}")
        return 1
    n_red = sum(1 for b in BREAKS if b[4])
    print(f"\n✓ {n_red} deliberate breaks went RED; "
          f"{len(BREAKS) - n_red} stayed green exactly where recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
