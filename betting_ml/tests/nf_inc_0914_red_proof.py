"""nf_inc_0914_red_proof.py — prove the NF-INC-0914 entrypoint guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17) — and this incident IS
that lesson's bill arriving. Thirty-one test files imported the exporter, two of them touched
`main()`, and both read it as TEXT. The suite was green while every scheduled publish died at line
2138. So the guard written to close that gap is held to the harder standard, not the softer.

⭐ THE HARNESS IS IMPORTED, NOT RE-IMPLEMENTED — `nf_inj4b_red_proof` already encodes the four ways
a red proof lies (the mutation never LANDS #682; it lands but does not MOVE the asserted predicate
#815; it lands on the WRONG symbol E11.24; an unresolvable node id scores a perfect RED forever),
plus the stale-backup sweep that exists because this harness's worst case is being killed mid-edit.

⚠️ THE CASES ARE TWO-SIDED BY CONSTRUCTION. Two break the SOURCE toward the outage (the historical
NameError verbatim; a silently wrong season) and two break the GUARD toward the vacuity it exists to
prevent (a fixture emptied until the smoke asserts nothing; the executing caller removed, leaving
the suite back in the state that produced run dd44e28e). A guard that can only ever pass is the same
vacuity in a friendlier costume — and the fourth case is the one that keeps THIS file honest.

RUN (LAPTOP, ~25 s):
    uv run python betting_ml/tests/nf_inc_0914_red_proof.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from betting_ml.tests.nf_inj4b_red_proof import (  # noqa: E402
    _collects,
    _run,
    _sweep_stale_backups,
)

_EXPORTER = _REPO / "quant_sports_intel_models/football/nfl/fantasy/export_draft_board_json.py"
_GUARD = _REPO / "betting_ml/tests/test_nf_inc_0914_publish_entrypoint.py"

_SMOKE = f"{_GUARD}::test_the_publish_entrypoint_runs_end_to_end_with_the_designation_branch_taken"
_SEASON_CLAUSE = f"{_GUARD}::test_the_season_the_stamp_reads_is_the_season_the_run_was_asked_for"
_SCOPE = f"{_GUARD}::test_no_name_in_the_exporter_resolves_nowhere"
_CALLER = f"{_GUARD}::test_the_entrypoint_has_an_executing_caller_and_not_only_a_source_reader"

#: The NOT-SELECTED control: must stay GREEN under every mutation, so a red reading is never
#: credited to a break that simply broke everything. ⚠️ Deliberately in ANOTHER FILE and over the
#: served CONSTANTS, not the entrypoint — a control inside `_GUARD` would share this file's fate
#: under the two mutations that break the guard itself, and would report "not attributable" for a
#: perfectly attributable red.
NOT_SELECTED = (f"{_REPO}/betting_ml/tests/test_nf_inj4b_ship_wiring.py"
                "::test_the_served_arm_is_the_one_the_decisive_run_certified")

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── toward the OUTAGE: the source breaks exactly as it did on 2026-09-14 ──────────────────
    ("THE HISTORICAL BREAK, VERBATIM — `season` unbound at the stamp's call site (run dd44e28e)",
     _EXPORTER,
     "        pdf, designations, season=args.season)",
     "        pdf, designations, season=season)",
     _SMOKE),

    ("the season is silently re-pointed at a WRONG year — the stamp reads another build's count",
     _EXPORTER,
     "        pdf, designations, season=args.season)",
     "        pdf, designations, season=2000)",
     _SEASON_CLAUSE),

    # ⭐ On a path the smoke DOES NOT EXECUTE (`_maybe_publish` is stubbed), which is the entire
    #    claim the static clause makes: the smoke covers the path it runs, this covers the rest.
    ("an unbound name on a branch the smoke never enters — the residual the smoke cannot cover",
     _EXPORTER,
     '    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)",'
     " bucket, prefix, len(files))",
     '    log.warning("🚨 PUBLISHING TO LIVE PROD api-cache — s3://%s/%s/ (%d files)",'
     " bucket, prefix, len(undefined_name_nf_inc_0914))",
     _SCOPE),

    # ── toward the VACUITY this guard could itself acquire ────────────────────────────────────
    ("the fixture is emptied until the smoke asserts NOTHING (0 == 0 satisfies the equality)",
     _GUARD,
     '_DESIGNATED = {"00-0000": "Questionable", "00-0001": "Out"}',
     "_DESIGNATED = {}",
     _SMOKE),

    ("the executing caller is removed — the suite returns to reading main() without running it",
     _GUARD,
     "        return EX.main(argv)",
     "        return 0  # no executing caller",
     _CALLER),
]


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: the guard must be GREEN on unbroken source "
          "(a 'red' means nothing otherwise)")
    if not _run(str(_GUARD)) or not _run(NOT_SELECTED):
        print("⛔ BASELINE FAILED — fix the suite before reading any RED below")
        return 1
    missing = sorted({c[4] for c in CASES if not _collects(c[4])})
    if missing:
        print(f"⛔ BASELINE FAILED — these node ids collect NOTHING (renamed/moved/deleted), so "
              f"every RED credited to them would be meaningless: {missing}")
        return 1
    print(f"   ✅ baseline green, all {len({c[4] for c in CASES})} named guards resolve\n")

    red = 0
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        # ⛔ #815 + E11.24: the anchor must be UNIQUE, or the mutation lands on the wrong symbol.
        n = src.count(old)
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            continue
        bak = path.with_suffix(path.suffix + ".redproof.bak")
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            # ⛔ #682: the mutation LANDED.  ⛔ #815: it MOVED the asserted predicate.
            after = path.read_text()
            additive = old in new
            assert after != src, f"{label}: mutation did not land"
            if additive:
                assert new not in src, f"{label}: the additive break was ALREADY present"
                assert new in after, f"{label}: the additive break is not in the file"
            else:
                assert old not in after, (
                    f"{label}: the old token survives — the predicate did not move")

            failed = not _run(nodeid)
            other_ok = _run(NOT_SELECTED)
            mark = "✅ RED" if failed else "⛔ STILL GREEN (VACUOUS GUARD)"
            sel = "" if other_ok else "  ⚠️ NOT-SELECTED control also broke — not attributable"
            print(f"{mark:34s} {label}{sel}")
            red += bool(failed and other_ok)
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    print(f"\n{red}/{len(CASES)} mutations turned their named guard RED (attributably).")
    print("── restoring: verifying the tree is green again")
    ok = _run(str(_GUARD)) and _run(NOT_SELECTED)
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
