"""red_proof_nf_w8_0e.py — prove NF-W8-0e's guards actually FAIL on deliberately broken source.

A guard that cannot fail is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness breaks one
thing at a time in `fp_qb_passing_cell.py` / `run_nf_w8_0e_qb_passing_cell.py`, runs the named
guard(s), and requires RED.

⭐ THE THREE WAYS A RED PROOF LIES, all closed here:
  1. **the mutation never LANDS** (#682) — every break is applied IN-PROCESS and the file is
     re-read and diffed; a mutation that did not change the bytes ABORTS rather than reporting a
     (false) "the guard is vacuous";
  2. **the mutation lands on the WRONG symbol** (E11.24 prediction_log) — each break asserts its
     anchor occurs EXACTLY ONCE in the file before replacing it;
  3. **the mutation lands but does not move the ASSERTED predicate** (#815) — each break declares
     an `absent_after` token and the harness asserts it is GONE once the break is applied, so a
     suffix-rename-style no-op break cannot come back green.

⚠️ It also restores stale backups AT START-UP: a source-mutating proof whose own worst case is
being killed mid-mutation must not leave a broken tree behind (the E11.26 lesson).

⛔ It runs pytest through the PROJECT interpreter (`sys.executable -m pytest`) — a bare `python3`
with no pytest turns "pytest is missing" into a non-zero exit that reads as a caught break (the
NF-INFRA1 false-RED).

RUN (LAPTOP, ~1-2 min):

    uv run python -m quant_sports_intel_models.football.nfl.fantasy.red_proof_nf_w8_0e
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[3]
MODULE = _HERE / "fp_qb_passing_cell.py"
RUNNER = _HERE / "run_nf_w8_0e_qb_passing_cell.py"
TESTS = _ROOT / "betting_ml" / "tests" / "test_nf_w8_0e_qb_passing_cell.py"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    #: a token that must be GONE from the file once the break is applied (#815: a mutation that
    #: lands but does not move the asserted predicate is a FALSE GREEN)
    absent_after: str
    tests: tuple[str, ...]


BREAKS: tuple[Break, ...] = (
    Break(
        "Z stops being leg-scoped (it touches every leg)",
        MODULE,
        "    out = leg_zero_mass(b)\n    out[:, int(leg_index)] = t[:, int(leg_index)]\n    return out",
        "    return np.asarray(t, dtype=float)",
        "out[:, int(leg_index)] = t[:, int(leg_index)]",
        ("test_z_is_leg_scoped_and_the_other_twelve_legs_are_byte_identical",),
    ),
    Break(
        "C overwrites the sub-threshold knots (the interpolation-ramp defect)",
        MODULE,
        "    out[:, j, :] = np.where(above, np.maximum(moved, 0.0), leg)",
        "    out[:, j, :] = np.where(above, np.maximum(moved, 0.0), 0.0)",
        "np.where(above, np.maximum(moved, 0.0), leg)",
        ("test_c_leaves_the_sub_threshold_knots_untouched",
         "test_c_moves_the_conditional_level_and_cannot_move_the_atom"),
    ),
    Break(
        "C drops the zero floor, so a negative shift emits negative yardage",
        MODULE,
        "    moved = (leg + v) if form == \"shift\" else (leg * v)\n"
        "    out[:, j, :] = np.where(above, np.maximum(moved, 0.0), leg)",
        "    moved = (leg + v) if form == \"shift\" else (leg * v)\n"
        "    out[:, j, :] = np.where(above, moved, leg)",
        "np.where(above, np.maximum(moved, 0.0), leg)",
        ("test_a_negative_shift_is_clipped_at_zero_and_the_clip_share_is_reported",),
    ),
    Break(
        "a non-positive κ is silently clipped instead of refused (NF-D16)",
        MODULE,
        "    if form == \"scale\" and v <= 0.0:\n"
        "        raise ValueError(f\"κ {v} ≤ 0 inverts the leg — INELIGIBLE outright (NF-D16), never applied\")",
        "    v = max(v, 1e-6) if form == \"scale\" else v",
        "INELIGIBLE outright (NF-D16), never applied",
        ("test_a_non_positive_kappa_is_refused_outright",),
    ),
    Break(
        "the estimator falls back to the TRUNCATED grid mean (the A4 defect)",
        MODULE,
        "    return POINT_READER(conditional_bank(banks, leg_index))",
        "    return conditional_bank(banks, leg_index).mean(axis=1)",
        "POINT_READER(conditional_bank(banks, leg_index))",
        ("test_the_estimator_is_the_tail_completed_conditional_mean_not_the_grid_mean",),
    ),
    Break(
        "δ stops being refitted per Z column (one δ carried across the square)",
        MODULE,
        '    column = "z_on" if z_on else "z_off"',
        '    column = "z_off"',
        '"z_on" if z_on else "z_off"',
        ("test_delta_is_fitted_per_z_column",),
    ),
    Break(
        "a thin prior silently DEFAULTS instead of being recorded ineligible (NF1.7 (a))",
        MODULE,
        '        return {"eligible": False, "form": form, "column": column,\n'
        '                "reason": (f"fewer than {MIN_PRIOR_ROWS} prior OOF rows (or no positive row) in "\n'
        '                           f"column `{column}` — identity by construction (prereg §4.1)")}',
        '        return {"eligible": True, "form": form, "column": column, "value": 0.0}',
        "identity by construction (prereg §4.1)",
        ("test_a_thin_prior_is_ineligible_and_recorded_never_defaulted",),
    ),
    Break(
        "an out-of-band κ is clipped into the band instead of refused",
        MODULE,
        "    if not (MIN_SCALE <= kappa <= MAX_SCALE):",
        "    if False:",
        "if not (MIN_SCALE <= kappa <= MAX_SCALE):",
        ("test_kappa_outside_the_registered_band_is_ineligible",),
    ),
    Break(
        "the interaction is read as Δ_joint alone (the halves are never subtracted)",
        MODULE,
        "    inter = d_j - (d_z + d_c)",
        "    inter = d_j",
        "inter = d_j - (d_z + d_c)",
        ("test_the_interaction_is_delta_joint_minus_the_sum_of_the_halves",
         "test_the_interaction_states_are_read_off_the_ci_and_a_tie_is_additive"),
    ),
    Break(
        "an incomplete 2×2 square reports ADDITIVE instead of UNDEFINED",
        MODULE,
        '        return {"state": I_UNDEFINED, "reason": f"square incomplete: missing {missing} — "\n'
        '                                                f"UNDEFINED, never a clean reading (NF1.7 (a))"}',
        '        return {"state": I_ADDITIVE, "reason": "missing cells ignored"}',
        "UNDEFINED, never a clean reading (NF1.7 (a))",
        ("test_an_incomplete_or_thin_square_is_undefined_never_a_clean_reading",),
    ),
    Break(
        "the assembled-PIT clause tolerates an unreadable fold (fails OPEN)",
        MODULE,
        '            "passes": bool(evaluable and n_missing == 0 and len(clears) == len(evaluable))}',
        '            "passes": bool(len(clears) == len(evaluable))}',
        "n_missing == 0 and len(clears)",
        ("test_the_assembled_pit_bar_is_every_evaluable_fold_and_an_unreadable_fold_fails_closed",),
    ),
    Break(
        "the assembled-PIT clause is dropped from the battery entirely",
        MODULE,
        '        "assembled_pit_preserved": bool(assembled_pit.get("passes", False)),',
        '        "assembled_pit_preserved": True,',
        'bool(assembled_pit.get("passes", False))',
        ("test_each_clause_has_an_isolating_fixture_that_flips_only_it",),
    ),
    Break(
        "an unevaluable coverage read PASSES the floor (NF1.7 (a))",
        MODULE,
        '                "blocking_shortfall": True,\n'
        '                "note": "unevaluable — a coverage read that did not happen is not a pass "\n'
        '                        "(NF1.7 (a))"}',
        '                "blocking_shortfall": False, "note": "unevaluable"}',
        "a coverage read that did not happen is not a pass",
        ("test_the_coverage_floor_is_a_constraint_and_an_unevaluable_read_blocks",),
    ),
    Break(
        "an empty degenerate dict passes by `all([])`",
        MODULE,
        '        "degenerates_lose": bool(degenerate_losses\n'
        '                                 and all(bool(v) for v in degenerate_losses.values())),',
        '        "degenerates_lose": all(bool(v) for v in degenerate_losses.values()),',
        "bool(degenerate_losses\n                                 and all(",
        ("test_an_empty_anchor_dict_fails_closed",),
    ),
    Break(
        "a CONSTRAINT-only null publishes a data trigger anyway (NF-D18)",
        MODULE,
        '            "retest_trigger": None, "failing_checks": other_fail, "binding_half": "anchor",',
        '            "retest_trigger": "re-run with more folds", "failing_checks": other_fail,\n'
        '            "binding_half": "anchor",',
        '"retest_trigger": None, "failing_checks": other_fail',
        ("test_a_constraint_only_null_publishes_no_data_trigger",),
    ),
    Break(
        "a DSR failure with SR ≤ SR0 keeps the VOID 'lower-variance design' trigger (NF-W8-0d R2)",
        MODULE,
        '        if ls.get("variance_lever_closed"):\n            out["retest_trigger"] = None',
        '        if False:\n            out["retest_trigger"] = None',
        'if ls.get("variance_lever_closed"):',
        ("test_a_dsr_failure_with_sr_below_sr0_withholds_the_variance_lever_trigger",),
    ),
    Break(
        "the lockstep reading loses its benchmark (SR0 is dropped)",
        MODULE,
        "    gap = float(observed_sr) - float(sr0)",
        "    gap = float(observed_sr)",
        "float(observed_sr) - float(sr0)",
        ("test_the_lockstep_reading_is_sign_invariant_under_proportional_shrinkage",
         "test_a_dsr_failure_with_sr_below_sr0_withholds_the_variance_lever_trigger"),
    ),
    Break(
        "`cross_rankable` becomes reachable from a PERSISTING gap",
        MODULE,
        '    return {\n        "state": V_PERSISTS, "winner": winner, "cross_rankable": False,',
        '    return {\n        "state": V_PERSISTS, "winner": winner, "cross_rankable": True,',
        '"state": V_PERSISTS, "winner": winner, "cross_rankable": False',
        ("test_cross_rankable_is_only_reachable_through_the_closed_state",
         "test_the_four_verdict_states_are_reachable_and_only_by_their_own_route"),
    ),
    Break(
        "an unevaluable downstream read is treated as a clean close",
        MODULE,
        '    if closure is None or closure.get("all_below_mde") is None:',
        "    if False:",
        'if closure is None or closure.get("all_below_mde") is None:',
        ("test_the_four_verdict_states_are_reachable_and_only_by_their_own_route",),
    ),
    Break(
        "an unevaluable gap pair reports a clean close",
        MODULE,
        '            out[name] = {"evaluable": False, "below_mde": None, "bh_rejected": None,',
        '            out[name] = {"evaluable": True, "below_mde": True, "bh_rejected": False,',
        '"evaluable": False, "below_mde": None',
        ("test_gap_closed_reads_both_bh_and_the_mde_and_refuses_an_unevaluable_pair",),
    ),
    Break(
        "an empty assembled-Z activity read is scored INACTIVE (NF-D20)",
        MODULE,
        '"inactive": bool(g and not active),',
        '"inactive": bool(not active),',
        '"inactive": bool(g and not active)',
        ("test_the_assembled_z_column_activity_is_measured_never_assumed",),
    ),
    Break(
        "the permutation anchor is promoted into a gate clause (the NF-D16 sibling defect)",
        MODULE,
        '        "incumbent_reproduces": bool(incumbent_reproduces),',
        '        "incumbent_reproduces": bool(incumbent_reproduces),\n'
        '        "permutation_behaves": True,',
        "MARKER_NOT_PRESENT_permutation_behaves",
        ("test_the_permutation_anchor_is_registered_inactive_and_gates_nothing",
         "test_the_clause_battery_cannot_silently_lose_a_registered_clause"),
    ),
    Break(
        "the model side of δ reverts to the UNWEIGHTED mean (the A6 selection defect)",
        MODULE,
        '"mean_cond_model": sum(l["columns"][column]["sum_weighted_cond"]',
        '"mean_cond_model": sum(l["columns"][column]["sum_cond_mean"]',
        '["sum_weighted_cond"]',
        ("test_the_model_side_of_the_fit_is_probability_weighted",),
    ),
    Break(
        "a zero positive weight divides by zero instead of being ineligible",
        MODULE,
        "    if wsum <= 0.0:",
        "    if False:",
        "if wsum <= 0.0:",
        ("test_a_zero_positive_weight_is_ineligible_never_a_division_by_zero",),
    ),
    Break(
        "an INACTIVE own-form floor REFUSES again (the NF-W6d defect A7 corrects)",
        MODULE,
        'return {"state": "INACTIVE", "passes": True, "inactive": True, "gap": gap,',
        'return {"state": "INACTIVE", "passes": False, "inactive": True, "gap": gap,',
        '"state": "INACTIVE", "passes": True',
        ("test_an_oracle_pair_that_ties_is_inactive_and_does_not_refuse",),
    ),
    Break(
        "an INACTIVE own-form floor stops being NAMED in the verdict",
        MODULE,
        '    inactive = bool((own_form_pair or {}).get("inactive"))',
        "    inactive = False",
        '(own_form_pair or {}).get("inactive")',
        ("test_an_inactive_own_form_floor_is_named_in_the_verdict",),
    ),
    Break(
        "the module keeps its OWN copy of the certified re-splice",
        MODULE,
        "resplice_zero_mass = QM.resplice_zero_mass",
        "def resplice_zero_mass(banks, targets):\n"
        "    return QM.resplice_zero_mass(banks, targets)",
        "resplice_zero_mass = QM.resplice_zero_mass",
        ("test_the_certified_transform_is_a_pointer_not_a_copy",),
    ),
    Break(
        "the verdict RANKS the report-only downstream table (the E2.1-r inversion)",
        RUNNER,
        '    closure = (family_d.get(sel["winner"], {}).get("closure")',
        '    closure = (max(family_d.values(), key=lambda r: 1).get("closure")',
        'family_d.get(sel["winner"]',
        ("test_the_downstream_read_is_report_only_and_never_a_second_selection",),
    ),
    Break(
        "the runner drops its refusal to write a DECIDED predecessor path",
        RUNNER,
        '    "nf_w8_0c_qb_body", "nf_w8_0c_rows", "nf_w8_0d_dsr_frontier",',
        '    "nf_w8_0d_dsr_frontier",',
        '"nf_w8_0c_qb_body"',
        ("test_the_runner_refuses_to_write_any_decided_predecessor_path",),
    ),
    Break(
        "the runner ROUNDS a score a 1e-9 pin compares (the NF-W8-0 smoke's catch)",
        RUNNER,
        '        "crps_q199": float(s["crps_q199"]), "coverage_80": float(s["coverage_80"]),',
        '        "crps_q199": round(float(s["crps_q199"]), 6), "coverage_80": float(s["coverage_80"]),',
        '"crps_q199": float(s["crps_q199"]),',
        ("test_the_runner_never_rounds_a_pinned_score",),
    ),
    Break(
        "the runner TOLERATES an incumbent that is not the certified generator",
        RUNNER,
        '    check["matches"] = bool(check["crps_gap"] == 0.0 and check["point_gap"] == 0.0)',
        '    check["matches"] = bool(check["crps_gap"] < 1e-3 and check["point_gap"] < 1e-3)',
        'check["crps_gap"] == 0.0 and check["point_gap"] == 0.0',
        ("test_the_qb_assembly_is_one_code_path_with_the_certified_generator",),
    ),
)


def _restore_stale() -> None:
    """⚠️ A source-mutating proof's own worst case is being killed mid-mutation. Restore first."""
    for path in (MODULE, RUNNER):
        bak = path.with_suffix(path.suffix + ".redbak")
        if bak.exists():
            print(f"  ⚠️ restoring a STALE backup: {path.name}")
            shutil.move(str(bak), str(path))


def _run(tests: tuple[str, ...]) -> tuple[bool, str]:
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly"]
    for t in tests:
        args += [f"{TESTS}::{t}"]
    r = subprocess.run(args, cwd=_ROOT, capture_output=True, text=True, timeout=900)
    return r.returncode == 0, (r.stdout + r.stderr)[-600:]


def main() -> int:
    _restore_stale()
    ok, tail = _run(tuple(sorted({t for b in BREAKS for t in b.tests})))
    if not ok:
        print("⛔ the guards are NOT green on unbroken source — fix that before proving RED\n", tail)
        return 2
    print(f"✅ baseline GREEN · proving {len(BREAKS)} breaks\n")

    failures: list[str] = []
    for b in BREAKS:
        src = b.path.read_text()
        n = src.count(b.old)
        if n != 1:
            failures.append(f"{b.name}: anchor occurs {n}× (must be exactly 1) — the break could "
                            f"land on the WRONG symbol")
            print(f"  ⛔ {b.name}: ANCHOR NOT UNIQUE ({n}×)")
            continue
        bak = b.path.with_suffix(b.path.suffix + ".redbak")
        shutil.copy2(b.path, bak)
        try:
            b.path.write_text(src.replace(b.old, b.new, 1))
            after = b.path.read_text()
            if after == src:
                failures.append(f"{b.name}: the mutation did NOT land")
                print(f"  ⛔ {b.name}: MUTATION DID NOT LAND")
                continue
            if b.absent_after in after:
                failures.append(f"{b.name}: the mutation landed but `{b.absent_after[:40]}…` "
                                f"survives — it cannot have moved the asserted predicate")
                print(f"  ⛔ {b.name}: MUTATION DID NOT MOVE THE PREDICATE")
                continue
            green, tail = _run(b.tests)
            if green:
                failures.append(f"{b.name}: the guard stayed GREEN on broken source")
                print(f"  ⛔ {b.name}\n{tail}")
            else:
                print(f"  ✅ RED — {b.name}")
        finally:
            shutil.move(str(bak), str(b.path))

    print()
    if failures:
        print(f"⛔ {len(failures)} of {len(BREAKS)} breaks did NOT go red:")
        for f in failures:
            print(f"   · {f}")
        return 1
    print(f"✅ all {len(BREAKS)} breaks went RED — every guard can fail")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
