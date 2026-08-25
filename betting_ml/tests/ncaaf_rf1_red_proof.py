"""RED proof for NCAAF-RF1's window guards — `uv run python betting_ml/tests/ncaaf_rf1_red_proof.py`.

Every claim the RF1 guards in `test_ncaaf_roll_forward.py` make is proved by RE-INTRODUCING the
defect it guards against and requiring the named test to go RED. A green suite proves nothing on
its own: it is exactly what a vacuous guard also produces (NF1.7 (a) / INC-38 / NF-D17).

Harness contract — identical to `ncaaf_ps_red_proof.py` / `ncaaf_p2_1_s1b_red_proof.py`, on purpose
(ONE harness shape in this vertical), because a red proof has at least four ways to lie:
  * the mutation anchor must be UNIQUE in the file (E11.24 prediction_log — a non-unique anchor
    lands on the WRONG symbol and reports a FALSE "vacuous guard", the dangerous direction);
  * the mutation must be asserted to have LANDED (E11.24 #682);
  * where the guard asserts on a TOKEN, that token must be asserted GONE afterwards (E11.24 #815);
  * pytest runs in a SUBPROCESS so a `Failed` (a `BaseException`) cannot leak past a narrow except;
  * ⚠️ ONLY exit code 1 counts as RED — 2/3/4/5 is a BROKEN HARNESS (NF-INFRA1);
  * every file is restored in a `finally`.

⭐ ISOLATION (NF-D17): each break flips exactly ONE clause, and its selector names a test whose
remaining clauses are all still satisfied — so only the flipped clause can change the verdict.

⚠️ NOT SCHEDULED (like the repo's other Python red proofs). Runtime ~20 s.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TEST = "betting_ml/tests/test_ncaaf_roll_forward.py"
_S = "pipeline/schedules/sports_rollforward_schedules.py"
_B = "services/dagster/aws/BOX_OPERATIONS.md"

_CRON = 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-12,1 1"'


def _note_block() -> str:
    """The CONTIGUOUS comment block immediately above the cron constant — computed, not spelled
    out, so the "delete the whole note" break stays a real deletion as the note is edited (a
    hand-copied anchor rots into an anchor-not-found, which this harness would report as BROKEN)."""
    lines = (REPO / _S).read_text().splitlines()
    idx = next(i for i, ln in enumerate(lines) if ln.startswith(_CRON))
    j = idx
    while j > 0 and lines[j - 1].lstrip().startswith("#"):
        j -= 1
    return "\n".join(lines[j:idx])

_NOTE = _note_block()

#: (name, file, old, new, pytest -k selector, token that must be GONE after the mutation or None)
BREAKS: list[tuple[str, str, str, str, str, str | None]] = [
    # ── 1. the window covers a full season cycle ────────────────────────────────────────────────
    ("cron: reverts to the pre-RF1 Feb–Aug window (the seasonal hole is back)", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"',
     "covers_a_full_season_cycle", '"0 6 * 2-12,1 1"'),
    ("cron: January dropped — bowls/CFP stop advancing mid-season", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-12 1"',
     "covers_a_full_season_cycle", '"0 6 * 2-12,1 1"'),
    ("cron: the in-season half is bought by DROPPING the pre-season churn window", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 9-12,1 1"',
     "covers_a_full_season_cycle", '"0 6 * 2-12,1 1"'),
    ("cron: the weekly-Monday cadence silently becomes daily (8× the CFBD spend)", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-12,1 *"',
     "covers_a_full_season_cycle", '"0 6 * 2-12,1 1"'),
    # INC-38: a COMMENT must not be able to satisfy a guard that asserts on the cron's VALUE.
    ("cron: the real constant reverts while a COMMENT still spells the widened expression", _S,
     _CRON,
     '# NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-12,1 1"  <- prose must not satisfy the guard\n'
     'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"',
     "covers_a_full_season_cycle", None),

    # ── 2. the retired expression is gone ───────────────────────────────────────────────────────
    ("retired: the exact pre-RF1 cron literal is restored", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"',
     "retired_february_to_august_window_is_gone", '"0 6 * 2-12,1 1"'),

    # ── 3. the doc and the schedule cannot drift (one thing, one owner) ─────────────────────────
    ("doc drift: §10 still documents the OLD window while the code is widened", _B,
     "declared cron `0 6 * 2-12,1 1`", "declared cron `0 6 * 2-8 1`",
     "documented_window_matches_the_cron_constant", "declared cron `0 6 * 2-12,1 1`"),
    ("doc drift: the code is widened but §10's machine-checkable cron marker is deleted", _B,
     "The ANNUAL season roll-forward — declared cron `0 6 * 2-12,1 1` ",
     "The ANNUAL season roll-forward — ",
     "documented_window_matches_the_cron_constant", "declared cron `0 6 * 2-12,1 1`"),
    ("doc drift: the code REVERTS while §10 keeps documenting the widened window", _S,
     _CRON, 'NCAAF_ROLL_FORWARD_CRON = "0 6 * 2-8 1"',
     "documented_window_matches_the_cron_constant", '"0 6 * 2-12,1 1"'),

    # ── 4. the incident + defect class stay legible at the constant ─────────────────────────────
    # ⚠️ `gone=None` on these three: the tokens they strip (E9.48 / INC-37 / talent) legitimately
    # appear ELSEWHERE in this file — the NFL cron carries the same class citation, and the module
    # docstring names the covariates — so a file-wide "token is gone" check would false-alarm. The
    # guard reads ONLY the contiguous block above the constant, and these breaks strip the token
    # from exactly that block; the RED verdict is what proves it.
    ("provenance: the defect class (E9.48(c) / INC-37) is dropped from the note", _S,
     "# HOLE of exactly the E9.48(c) / INC-37 month-scoped-cron class, caught BEFORE it fired: the last",
     "# HOLE, caught BEFORE it fired: the last",
     "carries_the_incident_and_the_defect_class", None),
    # The note names `talent` on FIVE lines, so a hand-written excerpt strips only some of them and
    # the break reads GREEN for the wrong reason (the token survives — E11.24 #815, which is exactly
    # what the first cut of this harness did). Scrub the WHOLE computed block instead.
    ("provenance: the leg that made it bite (`talent`) is anonymised throughout the note", _S,
     _NOTE + "\n" + _CRON,
     _NOTE.replace("talent", "a covariate") + "\n" + _CRON,
     "carries_the_incident_and_the_defect_class", None),
    ("provenance: the whole comment block above the constant is deleted", _S,
     _NOTE + "\n" + _CRON,
     "# Weekly Monday 06:00 PT.\n" + _CRON,
     "carries_the_incident_and_the_defect_class", None),
]


def main() -> int:
    failures: list[str] = []
    for name, rel, old, new, selector, gone in BREAKS:
        path = REPO / rel
        original = path.read_text()

        occurrences = original.count(old)
        if occurrences != 1:
            label = "anchor not found" if occurrences == 0 else f"anchor x{occurrences}"
            print(f"{f'BROKEN ❌ ({label})':34} {name}")
            failures.append(f"{name}: anchor appears {occurrences}× in {rel}")
            continue

        mutated = original.replace(old, new, 1)
        if mutated == original:                     # #682 — the break must actually land
            print(f"{'BROKEN ❌ (mutation no-op)':34} {name}")
            failures.append(f"{name}: mutation did not change the file")
            continue
        if gone is not None and gone in mutated:    # #815 — the asserted token must be GONE
            print(f"{'BROKEN ❌ (token survives)':34} {name} -> {gone!r} still present")
            failures.append(f"{name}: asserted token survived the mutation")
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
            print(f"{verdict:34} {name}\n{'':34} -> {tail}")
        finally:
            path.write_text(original)

    print()
    if failures:
        print(f"{len(failures)} break(s) NOT caught:")
        for f in failures:
            print(f"  • {f}")
        return 1
    print(f"All {len(BREAKS)} deliberate breaks were caught RED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
