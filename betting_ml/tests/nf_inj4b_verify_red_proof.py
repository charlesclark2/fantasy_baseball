"""nf_inj4b_verify_red_proof.py — prove the NF-INJ4b-VERIFY guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17) — and this follow-up
exists BECAUSE a check said something it could not support. `--verify-published` printed "the
discount is not reaching the served board" about a board the discount was reaching perfectly; the
four flagged rows carried the four smallest discounts in the set, and the base had drifted under
them. So the guards written to repair that claim get held to the harder standard, not the softer.

⭐ THE HARNESS IS IMPORTED, NOT RE-IMPLEMENTED — `nf_inj4b_red_proof` already encodes the four ways
a red proof lies (the mutation never LANDS #682; it lands but does not MOVE the asserted predicate
#815; it lands on the WRONG symbol E11.24; an unresolvable node id scores a perfect RED forever),
plus the stale-backup sweep that exists because this harness's worst case is being killed mid-edit.

⚠️ EVERY CASE IS TWO-SIDED BY CONSTRUCTION. Half break the fix toward the OLD defect (a cleared
player scored as a failure); half break it toward the NEW one the fix could have introduced — a
check so forgiving it can no longer say NO. A repair that only ever passes is the same vacuity in a
friendlier costume.

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_inj4b_verify_red_proof.py
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

_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_BATTERY = _FAN / "run_nf_inj4b_ship_battery.py"
_EXPORTER = _FAN / "export_draft_board_json.py"
_PROJ = _FAN / "run_season_projection.py"

_V = _REPO / "betting_ml/tests/test_nf_inj4b_verify_live.py"
_SHIP = _REPO / "betting_ml/tests/test_nf_inj4b_ship_wiring.py"

#: must stay GREEN under every mutation below — otherwise a RED is not attributable to the break.
NOT_SELECTED = f"{_V}::test_a_discount_below_the_boards_rounding_is_its_own_state_not_a_pass"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    # ── toward the OLD defect: the states collapse back into one another ──────────────────────
    ("a CLEARED player is scored as a missed discount (the 2026-09-13 false ⛔, verbatim)",
     _BATTERY,
     '            state, shown = VERIFY_NO_LONGER_DESIGNATED, "—"',
     '            state, shown = VERIFY_UNMOVED, "—"',
     f"{_V}::test_a_player_who_LEFT_the_feed_is_not_reported_as_unmoved"),

    ("a CHANGED designation is compared against the constant it no longer prices",
     _BATTERY,
     "        elif _norm_label(live_label) != _norm_label(captured):",
     "        elif False:",
     f"{_V}::test_a_player_whose_designation_CHANGED_is_its_own_state"),

    ("an UNREADABLE feed returns GREEN over a board the check could not assess",
     _BATTERY,
     '              "return a verdict rather than scoring every row against an expired expectation.")\n        return 2',
     '              "return a verdict rather than scoring every row against an expired expectation.")\n        return 0',
     f"{_V}::test_an_unreadable_designation_feed_is_UNVERIFIABLE_and_never_green"),

    # ── toward the NEW defect this fix could have introduced: a check that cannot say NO ──────
    ("the check loses its teeth — a still-designated unmoved row can no longer be caught",
     _BATTERY,
     '        elif abs(float(g) - float(e["games_before"])) <= 1e-6:',
     "        elif False:",
     f"{_V}::test_a_STILL_designated_row_at_its_pre_ship_games_is_still_UNMOVED"),

    ("the verifier stops reading the build's record and silently re-infers",
     _BATTERY,
     '    moved_at_build = built.get("rows_discounted")',
     "    moved_at_build = None",
     f"{_V}::test_the_verifier_prefers_the_build_record_over_its_own_inference"),

    # ── toward the reporting defect: UNKNOWN quietly rendered as a measurement ────────────────
    ("an ABSENT build record is rendered as 'the discount moved nothing'",
     _EXPORTER,
     "        if not path.exists():\n            return {}",
     '        if not path.exists():\n            return {"rows_moved": 0, "designated_rows_on_frame": 0}',
     f"{_V}::test_an_absent_build_record_is_UNKNOWN_and_never_zero"),

    ("an unknown season falls back to a GUESSED year and reads another build's count",
     _EXPORTER,
     "    if season is None:\n        return {}",
     "    if season is None:\n        season = 2026",
     f"{_V}::test_an_unknown_season_is_UNKNOWN_rather_than_a_guessed_year"),

    ("the served stamp drops the build's moved-row count",
     _EXPORTER,
     '        stamp["rows_discounted"] = applied.get("rows_moved")',
     '        stamp["rows_discounted"] = None',
     f"{_V}::test_the_build_record_reaches_the_served_stamp"),

    ("the stamp stops saying that an absent count is UNKNOWN rather than zero",
     _EXPORTER,
     '"`rows_discounted: null` means UNKNOWN, never zero")',
     '"and that is all")',
     f"{_SHIP}::test_the_manifest_stamp_is_actually_EXERCISED_and_says_what_it_does_not_know"),

    # ── toward the SILENT hop: the record never leaves the build ──────────────────────────────
    ("the build stops handing its record to the caller (the manifest says UNKNOWN forever)",
     _PROJ,
     "    if desig_log is not None:\n        desig_log.update(_desig_log)",
     "    if desig_log is not None:\n        pass",
     f"{_V}::test_the_build_threads_its_discount_record_all_the_way_to_the_summary"),
]


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: every guard GREEN on unbroken source (a 'red' means nothing otherwise)")
    for g in (_V, _SHIP):
        if not _run(str(g)):
            print(f"⛔ BASELINE FAILED in {g.name} — fix the suite before reading any RED below")
            return 1
    missing = sorted({c[4] for c in CASES if not _collects(c[4])})
    if missing:
        print(f"⛔ BASELINE FAILED — these node ids collect NOTHING (renamed/moved/deleted), so "
              f"every RED credited to them would be meaningless: {missing}")
        return 1
    print(f"   ✅ baseline green, all {len({c[4] for c in CASES})} named guards resolve\n")

    red, ok = 0, True
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        n = src.count(old)
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            ok = False
            continue
        bak = path.with_suffix(path.suffix + ".redproof.bak")
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            if path.read_text() == src:
                print(f"⛔ {label}: the mutation did not LAND (#682)")
                ok = False
                continue
            if old in path.read_text():
                print(f"⛔ {label}: the broken token SURVIVES the mutation (#815)")
                ok = False
                continue
            went_red = not _run(nodeid)
            still_green = _run(NOT_SELECTED)
            if went_red and still_green:
                red += 1
                print(f"   ✅ RED (attributably): {label}")
            elif went_red and not still_green:
                print(f"   ⚠️  RED but NOT-SELECTED also failed — not attributable: {label}")
                ok = False
            else:
                print(f"   ⛔ STAYED GREEN — the guard does not cover it: {label}")
                ok = False
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    print(f"\n{red}/{len(CASES)} mutations turned their named guard RED (attributably).")
    if red != len(CASES) or not ok:
        print("⛔ at least one clause is vacuous or unattributable — fix it before shipping.")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
