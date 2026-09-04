"""nf_inj4b_red_proof.py — prove NF-INJ4b's guards can FAIL.

⛔ A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks
the source ONE MUTATION AT A TIME and asserts the NAMED guard goes RED.

⭐ THE THREE WAYS A RED PROOF ITSELF LIES, all guarded here:
  1. **the mutation never LANDS** (#682) — every mutation asserts the file actually CHANGED on disk;
  2. **it lands but does not MOVE the asserted predicate** (#815) — every mutation asserts the OLD
     token is GONE afterwards, not merely that bytes changed;
  3. **it lands on the WRONG symbol** (E11.24 prediction_log) — every anchor is asserted UNIQUE in
     its file before it is applied.
⭐ Plus a BASELINE-PASS leg (the guard must be GREEN on unbroken source, or "red" means nothing) and
a NOT-SELECTED leg (a mutation must not turn some OTHER test red and be credited to this one).

⛔ It restores every file in a `finally`, and it ALSO sweeps stale backups AT START-UP: this
harness's own worst case is being killed mid-mutation, and a signal skips `finally` (the E11.26
lesson, learned when a RED proof SIGKILLed itself).

RUN (LAPTOP, ~40 s):
    uv run python betting_ml/tests/nf_inj4b_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_FAN = _REPO / "quant_sports_intel_models/football/nfl/fantasy"
_RUNNER = _FAN / "run_nf_inj4b_designation_duration.py"
_MODULE = _FAN / "nf_inj4b_designation_duration.py"
_SEASON = _FAN / "season_projection.py"
_SCORER = _FAN / "run_nf_inj4_designation_duration.py"
_CF = _FAN / "run_nf_inj4b_counterfactual.py"

_GUARD = _REPO / "betting_ml/tests/test_nf_inj4b_matched_resolution.py"
_INJ4_GUARD = _REPO / "betting_ml/tests/test_nf_inj4_designation_duration.py"

#: (label, file, old, new, guard-file::test-name)
CASES: list[tuple[str, Path, str, str, str]] = [
    ("the NF1.9 (f) floor clause stops refusing a VIOLATED pair",
     _RUNNER,
     '''        state = ("ACTIVE" if margin < -tol else
                 "VIOLATED" if margin > tol else "INACTIVE")''',
     '''        state = ("ACTIVE" if margin < -tol else
                 "INACTIVE" if margin > tol else "INACTIVE")''',
     f"{_GUARD}::test_a_control_that_BEATS_the_peeking_oracle_VIOLATES_the_floor"),

    ("the NF-W6d inactive-pair reading is dropped (a tie scores as ACTIVE)",
     _RUNNER,
     '"pair_active": state == "ACTIVE",',
     '"pair_active": state != "VIOLATED",',
     f"{_GUARD}::test_an_all_inactive_anchor_family_FAILS_the_informative_clause"),

    ("the floor stops reporting its NON-VACUOUS count beside the raw pass count",
     _RUNNER,
     '"n_holding_NON_VACUOUSLY": f"{len([a for a in active if a not in violated])}"',
     '"n_holding_NON_VACUOUSLY_dropped": f"{len([a for a in active if a not in violated])}"',
     f"{_GUARD}::test_the_floor_clause_reports_its_NON_VACUOUS_count_beside_the_raw_pass_count"),

    ("an unfittable anchor is scored as a PASS instead of a hard failure",
     _RUNNER,
     '''        if orc is None or ctl is None:
            out[a] = {"evaluable": False,''',
     '''        if orc is None or ctl is None:
            out[a] = {"evaluable": True,''',
     f"{_GUARD}::test_an_unfittable_anchor_is_a_hard_failure_never_a_pass"),

    ("the matched-resolution self-check stops refusing an UNMATCHED control",
     _RUNNER,
     '"matched": bool(min(f["n_test"], f["n_train"]) == int(f["n_test"]))}',
     '"matched": True}',
     f"{_GUARD}::test_a_control_fitted_at_FULL_resolution_is_refused_as_unmatched"),

    ("the matched-n control is drawn at FULL resolution in the scorer",
     _SCORER,
     'take = rng.choice(len(train), size=min(n_peek, len(train)), replace=False)',
     'take = rng.choice(len(train), size=len(train), replace=False)',
     f"{_GUARD}::test_the_matched_n_control_is_actually_drawn_at_the_peeks_row_count"),

    ("the naive oracle clause is put BACK into the gate table",
     _MODULE,
     '    ANCHOR_CLAUSE_FLOOR: "invariant",',
     '    ANCHOR_CLAUSE_FLOOR: "invariant",\n    "oracle_respected": "metric",',
     f"{_GUARD}::test_the_naive_oracle_clause_is_retired_from_the_gate_table"),

    ("only ONE anchor reading is registered (the two clauses are merged)",
     _MODULE,
     'ANCHOR_CLAUSE_FLOOR = "oracle_floor_matched_resolution"',
     'ANCHOR_CLAUSE_FLOOR = "anchor_pair_informative"',
     f"{_GUARD}::test_both_anchor_readings_are_registered_as_separately_named_clauses"),

    ("MIN_CELL_N is lowered to unlock the 29-row `doubtful` cell",
     _MODULE,
     'MIN_CELL_N = DD.MIN_CELL_N',
     'MIN_CELL_N = 29',
     f"{_GUARD}::test_the_field_and_folds_are_inherited_by_IMPORT_not_restated"),

    ("the forward injection-invariance declaration is dropped",
     _MODULE,
     'INVARIANT_GATES: tuple[str, ...] = (\n    "degenerates_lose", ANCHOR_CLAUSE_INFORMATIVE, ANCHOR_CLAUSE_FLOOR)',
     'INVARIANT_GATES: tuple[str, ...] = ("degenerates_lose",)',
     f"{_GUARD}::test_both_anchor_clauses_are_declared_injection_invariant_forward"),

    ("the positive control stops being driven by the EXPLICIT partition",
     _RUNNER,
     'gate_classes=B.GATE_CLASSES,',
     'deflation_gates=B.DEFLATION_GATES,',
     f"{_GUARD}::test_the_gate_partition_is_declared_explicitly_and_covers_every_gate"),

    ("the two availability channels are applied SEQUENTIALLY (they stack)",
     _SEASON,
     'new_games = np.minimum(formal_new, desig_new)',
     'new_games = desig_new',
     f"{_INJ4_GUARD}::test_the_designation_channel_is_wired_but_structurally_off_in_production"),

    ("the designation channel stops being default-off",
     _SEASON,
     '    designation_games=None,',
     '    designation_games=lambda d: d["proj_games"].to_numpy(dtype=float) * 0.5,',
     f"{_INJ4_GUARD}::test_passing_no_designation_channel_leaves_the_chain_byte_identical"),

    ("the designation cap stops stamping the disjointness flag",
     _SEASON,
     'df[FORMAL_APPLIED_COL] = new_games < old_games - 1e-9',
     'df[FORMAL_APPLIED_COL] = formal_new < old_games - 1e-9',
     f"{_INJ4_GUARD}::test_a_designation_cap_STAMPS_the_flag_that_keeps_the_news_channel_disjoint"),

    ("the counterfactual groups on config_name alone (two boards concatenated)",
     _CF,
     'for (cfg, n_teams), g in boards.groupby(["config_name", "n_teams"]):',
     'for cfg, g in boards.groupby("config_name"):\n        n_teams = int(g["n_teams"].iloc[0])',
     f"{_GUARD}::test_an_empty_designation_map_moves_exactly_zero_ranks_on_every_board"),

    ("an unmapped designation label silently prices at 1.0 again",
     _CF,
     'unmapped = sorted(set(g["cf_desig"].dropna()) - set(mult))',
     'unmapped = []',
     f"{_GUARD}::test_an_unmapped_designation_label_REFUSES_rather_than_pricing_at_one"),

    ("the counterfactual compares against the PUBLISHED rank, not a like-for-like baseline",
     _CF,
     'g["cf_move"] = g["cf_base_rank"] - g["cf_rank"]',
     'g["cf_move"] = g["overall_rank"].astype(int) - g["cf_rank"]',
     f"{_GUARD}::test_the_rank_move_is_like_for_like_and_an_ordering_difference_is_DISCLOSED_not_absorbed"),
]

#: The NOT-SELECTED control: a test that must stay GREEN under every mutation above, so a red
#: reading is never credited to a mutation that simply broke the module for everyone.
#: ⚠️ It must NOT import the module a mutation can break at IMPORT time — several breaks here trip
#: `nf_inj4b_designation_duration`'s own self-assertions, which fails EVERY test in a file that
#: imports it and would make the control read "not attributable" for a perfectly attributable red.
#: This one exercises the pure NF-INJ4 kernel only.
NOT_SELECTED = f"{_INJ4_GUARD}::test_no_channel_leaves_the_projection_untouched"


def _run(nodeid: str) -> bool:
    """True when the selected test PASSES."""
    r = subprocess.run([sys.executable, "-m", "pytest", nodeid, "-q", "--no-header", "-p",
                        "no:cacheprovider"], cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


def _sweep_stale_backups() -> list[str]:
    """⛔ FIRST, before any mutation: this harness's worst case is being killed mid-mutation, and a
    signal skips `finally`. A stale `.redproof.bak` means real source is still broken on disk."""
    restored = []
    for bak in _FAN.rglob("*.redproof.bak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        restored.append(str(target.relative_to(_REPO)))
    for bak in (_REPO / "betting_ml/tests").rglob("*.redproof.bak"):
        target = bak.with_suffix("")
        target.write_text(bak.read_text())
        bak.unlink()
        restored.append(str(target.relative_to(_REPO)))
    return restored


def main() -> int:
    stale = _sweep_stale_backups()
    if stale:
        print(f"⚠️  restored {len(stale)} stale backup(s) from an interrupted run: {stale}")

    print("── BASELINE: every guard must be GREEN on unbroken source "
          "(a 'red' means nothing otherwise)")
    if not _run(str(_GUARD)) or not _run(str(_INJ4_GUARD)):
        print("⛔ BASELINE FAILED — fix the suite before reading any RED below")
        return 1
    print("   ✅ baseline green\n")

    red = 0
    for label, path, old, new, nodeid in CASES:
        src = path.read_text()
        # ⛔ #815 + E11.24: the anchor must be UNIQUE, or the mutation can land on the wrong symbol.
        n = src.count(old)
        if n != 1:
            print(f"⛔ {label}: anchor occurs {n}× in {path.name} — NOT UNIQUE, refusing to mutate")
            continue
        bak = path.with_suffix(path.suffix + ".redproof.bak")
        bak.write_text(src)
        try:
            path.write_text(src.replace(old, new, 1))
            # ⛔ #682: the mutation LANDED.  ⛔ #815: it MOVED the asserted predicate.
            #    ⭐ "moved" has TWO forms and conflating them makes the check wrong in one of them:
            #    a REPLACEMENT must remove the old token, while an ADDITIVE break (putting a key
            #    back into a dict) necessarily PRESERVES it and moves the predicate by introducing
            #    something new. The form is derived from the mutation itself rather than declared,
            #    so a future case cannot pick the lenient one by accident.
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
            other_ok = _run(NOT_SELECTED) if nodeid != NOT_SELECTED else True
            mark = "✅ RED" if failed else "⛔ STILL GREEN (VACUOUS GUARD)"
            sel = "" if other_ok else "  ⚠️ NOT-SELECTED control also broke — not attributable"
            print(f"{mark:34s} {label}{sel}")
            red += bool(failed and other_ok)
        finally:
            path.write_text(bak.read_text())
            bak.unlink()

    print(f"\n{red}/{len(CASES)} mutations turned their named guard RED (attributably).")
    print("── restoring: verifying the tree is green again")
    ok = _run(str(_GUARD)) and _run(str(_INJ4_GUARD))
    print("   ✅ restored green" if ok else "   ⛔ TREE LEFT BROKEN — investigate")
    return 0 if (red == len(CASES) and ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
