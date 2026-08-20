"""NF-W8-0c RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0c.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness applies
one deliberate defect at a time and asserts the named guard turns RED. Every discipline this repo
has paid for is enforced:

- **the mutation must LAND** (E11.24 #682) — a no-op break reports a FALSE "the guard is vacuous",
  which reads as a real finding and invites weakening a correct guard;
- **the anchor must be UNIQUE** (#885) — a replace can otherwise land on the WRONG symbol and the
  run comes back GREEN reporting a false vacuity;
- **the asserted token must be GONE** (#815) — a break that writes without moving the asserted
  predicate is a false GREEN;
- **a stale backup is restored AT START-UP** (E11.26) — this harness's own worst case is being
  killed mid-mutation, which would leave broken source on disk;
- **a stalled leg reports HUNG**, never silently green.

⛔ Not a pytest module: it MUTATES tracked source and restores it in a `finally`.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_QB = Path(__file__).with_name("fp_qb_body.py")
_RUN = Path(__file__).with_name("run_nf_w8_0c_qb_body.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w8_0c_qb_body.py"
_TIMEOUT_S = 300
_BACKUP_SUFFIX = ".red_proof_backup"


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    tests: tuple[str, ...]
    defect: str


_A = "TestAssembly"
_M = "TestMechanismDecomposition"
_B = "TestBandDecomposition"
_P = "TestArmParameters"
_S = "TestSelection"
_C = "TestArchitectureState"
_V = "TestVerdict"
_R = "TestRunnerDiscipline"
_G = "TestRegistration"
_E2E = "test_the_full_runner_path_runs_end_to_end_on_synthetic_banks"

BREAKS: tuple[Break, ...] = (
    # ── the assembly wrapper: ONE code path, and the identity's INDEPENDENT anchor ─────────────
    Break("wrapper_forks_the_certified_leg_draw_stream", _QB,
          "        legs = MX.mixture_leg_draws(b[start:stop], base_z, pi=p[start:stop], "
          "corr=corr, seed=seed,",
          "        legs = MX.mixture_leg_draws(b[start:stop], base_z, pi=p[start:stop], "
          "corr=corr, seed=seed + 1,",
          (f"{_A}::test_the_wrapper_is_byte_identical_to_the_certified_assembly_at_zero_shift",),
          "⭐ the arm harness forks the generator stream — every arm is then scored against an "
          "incumbent that is NOT the certified `zm_floor` (NF-W7d)"),
    Break("read_channel_defined_as_the_residual_making_the_identity_vacuous", _QB,
          "    draw_total = float(tdm.mean())",
          "    draw_total = float(leg_sum)",
          (f"{_M}::test_the_identity_FAILS_when_the_leg_means_are_not_the_ones_the_point_came_"
           f"from",),
          "⭐⭐ THE DEFECT THIS STORY SHIPPED IN ITS FIRST CUT: defining READ as the residual "
          "makes the §3.1 identity TAUTOLOGICAL — it then holds for ANY leg means, so the whole "
          "decomposition guard passes on nothing (NF-C0e: a test that reads a value back under "
          "the key the code writes)"),
    Break("leg_means_drift_from_the_draws_the_total_came_from", _QB,
          "        leg_means[start:stop] = legs.mean(axis=1)",
          "        leg_means[start:stop] = 1.01 * legs.mean(axis=1)",
          (f"{_E2E}",),
          "⭐ the leg means stop being the draws the assembled total came from — the §3.1 "
          "LINEARITY identity breaks, and only asserting it on the REAL runner path (not in a "
          "unit fixture) can see it"),
    Break("alive_mask_crosscheck_removed", _QB,
          "            if np.any(legs[~alive]):",
          "            if False:",
          (f"{_A}::test_the_alive_mask_crosscheck_refuses_a_disagreeing_leg_draw",),
          "the re-derived availability mask is TRUSTED rather than verified against the scored "
          "draws — `cond_shift` would then shift the wrong draws silently (NF-W7d)"),
    Break("negative_scale_accepted_by_scale_legs", _QB,
          "    if not np.all(np.isfinite(k)) or float(k.min()) <= 0.0:",
          "    if not np.all(np.isfinite(k)):",
          (f"{_A}::test_scale_legs_refuses_a_nonpositive_kappa_and_preserves_zero_mass",),
          "a negative κ INVERTS a leg's whole distribution (NF-D16/NF-TR2b)"),
    Break("climatology_anchor_formed_from_a_single_row", _QB,
          "    if len(y) < 2:",
          "    if False:",
          (f"{_A}::test_the_climatology_anchor_refuses_to_be_formed_from_nothing",),
          "the two-sided anchor is formed from nothing — an anchor that could not be FORMED is a "
          "failed control, never a pass (NF1.7 (a))"),

    # ── the decompositions ─────────────────────────────────────────────────────────────────────
    Break("availability_split_zero_filled_instead_of_UNDEFINED", _QB,
          "        c_bar = float(rz[:, i].mean() / a_bar) if a_bar > 0 else None",
          "        c_bar = float(rz[:, i].mean() / a_bar) if a_bar > 0 else 0.0",
          (f"{_M}::test_the_availability_split_is_None_not_zero_when_it_cannot_be_formed",),
          "an UNDEFINED split is zero-filled — 'we could not measure it' becomes 'it is zero' "
          "(NF1.7 (a))"),
    Break("pooling_reverts_to_a_mean_of_fold_means", _QB,
          "        return float(sum(c[\"n\"] * v for c, v in zip(usable, vals)) / n_tot)",
          "        return float(np.mean(vals))",
          (f"{_M}::test_pooling_is_over_rows_and_the_fold_mean_convention_is_reported_beside_it",),
          "⭐ NF1.8, and NF-W8-0b's OWN headline was first written this way: a bound stated from "
          "a mean of fold means is a different number wearing the same name"),
    Break("band_contributions_no_longer_sum_to_the_gap", _QB,
          "        contrib = float(diff[lo:hi].sum() * GRID_STEP)",
          "        contrib = float(diff[lo:hi].sum() * GRID_STEP * 0.9)",
          (f"{_B}::test_the_bands_sum_exactly_to_the_gridmean_gap",),
          "the band localisation stops being an identity, so the published shares no longer "
          "account for the gap they claim to decompose"),

    # ── the arm parameters: nothing silently defaulted ─────────────────────────────────────────
    Break("negative_kappa_clipped_instead_of_refused", _QB,
          "        if k <= 0.0:",
          "        if False:",
          (f"{_P}::test_a_negative_kappa_makes_leg_scale_INELIGIBLE_OUTRIGHT_never_clipped",),
          "a leg whose implied κ is negative is silently kept — a board-inverting parameter "
          "shipped as an ordinary fit (NF-D16)"),
    Break("out_of_band_kappa_silently_accepted", _QB,
          "    if arm == \"cond_scale\":\n        if not (MIN_SCALE <= ratio <= MAX_SCALE):",
          "    if arm == \"cond_scale\":\n        if False:",
          (f"{_P}::test_a_kappa_outside_the_registered_band_makes_the_scale_arm_ineligible",),
          "the registered admissibility band stops binding — an arbitrary scale ships under a "
          "pre-registered arm's name (E2.1-r)"),
    Break("immaterial_leg_floor_removed", _QB,
          "        if contrib < MIN_LEG_CONTRIB_PPR:",
          "        if False:",
          (f"{_P}::test_an_immaterial_leg_keeps_kappa_one_and_is_listed",),
          "a leg that cannot materially move the level contributes its NOISE ratio as a fitted "
          "parameter (the NF-W6 demonstrable-≠-material lesson, at the parameter level)"),
    Break("out_of_band_share_gate_removed", _QB,
          "    if priced and len(out_of_band) / len(priced) > MAX_OUT_OF_BAND_SHARE:",
          "    if False:",
          (f"{_P}::test_too_many_out_of_band_legs_makes_leg_scale_ineligible_for_the_fold",),
          "a fold where most legs are un-fittable still ships a `leg_scale` arm"),
    Break("permutation_anchor_becomes_the_identity", _QB,
          "    rolled = vals[-1:] + vals[:-1]",
          "    rolled = list(vals)",
          (f"{_P}::test_permute_kappa_preserves_the_population_and_destroys_the_assignment",),
          "⭐ the matched foil becomes the REAL ARM, so `beats_permuted` can never refuse "
          "anything (NF-D10)"),

    # ── selection: the constraints are FLOORS ──────────────────────────────────────────────────
    Break("selection_ignores_the_pit_constraint", _QB,
          "                  and clauses_by_arm.get(a, {}).get(\"pit_preserved\") is True",
          "                  and True",
          (f"{_S}::test_an_arm_failing_a_hard_constraint_is_not_selectable_even_with_the_"
           f"smallest_bias",),
          "an arm that BREAKS the certified PIT bar becomes selectable purely for having the "
          "smallest level bias — the objective eats the constraint (E2.1-r/NF1.8)"),
    Break("selection_starts_ranking_on_pit_headroom", _QB,
          "    best = min(admissible, key=lambda a: bias_by_arm[a][\"abs_pooled\"])",
          "    best = min(admissible, key=lambda a: (bias_by_arm[a][\"abs_pooled\"],\n"
          "                                          bias_by_arm[a].get(\"max_decile_dev\", 0.0)))",
          (f"{_S}::test_the_pit_bar_is_a_floor_and_buys_no_credit_for_exceeding_it",),
          "⭐ the FLOOR becomes a TARGET — a criterion monotone in over-widening, which the "
          "`max_width` degenerate wins outright (NF1.8)"),
    Break("tie_break_abandons_the_registered_simplicity_order", _QB,
          "            return min(tied, key=REAL_ARMS.index)     # the registered simplicity "
          "order",
          "            return max(tied, key=REAL_ARMS.index)",
          (f"{_S}::test_a_tie_breaks_to_the_registered_simplicity_order",),
          "a 0.001 PPR edge buys the 13-parameter arm that re-levels a CERTIFIED per-stat "
          "marginal — a tie decided against the registration (E2.1-r)"),

    # ── family C + the verdict ─────────────────────────────────────────────────────────────────
    Break("a_tie_on_every_axis_counts_as_assembly_dominance", _QB,
          "    a_dominates = any(wins_a.values()) and not any(wins_d.values())",
          "    a_dominates = not any(wins_d.values())",
          (f"{_C}::test_a_tie_on_every_axis_is_unresolved_because_a_tie_is_not_a_win",),
          "⭐ a TIE is reported as a WIN for the incumbent architecture — the NF1.8 lesson that "
          "a rank statistic cannot tell a tie from a win, on the consumption decision"),
    Break("an_unevaluable_architecture_comparison_reads_as_a_result", _QB,
          "    if n_folds < 2 or len(cd) < 2 or len(bd) < 2:",
          "    if False:",
          (f"{_C}::test_below_two_folds_it_DID_NOT_RUN_and_is_never_read_as_a_result",),
          "a comparison that DID NOT RUN is rendered as a state (NF1.7 (a))"),
    Break("cross_rankable_licensed_without_the_gap_closing", _QB,
          "    if admissible and gap_closed:",
          "    if admissible:",
          (f"{_V}::test_cross_rankable_is_true_ONLY_when_the_gap_actually_closes",),
          "⭐ `cross_rankable: true` — which UNBLOCKS raw-point cross-position surfaces and "
          "superflex — ships on an admissible arm that never closed the measured gap"),
    Break("a_failing_clause_no_longer_refuses_the_arm", _QB,
          "                      and all(winner_clauses.get(c) is True for c in ARM_CLAUSES))",
          "                      and any(winner_clauses.get(c) is True for c in ARM_CLAUSES))",
          (f"{_V}::test_a_single_failing_clause_refuses_the_arm",),
          "one passing clause is enough to ship — the whole registered battery becomes advisory"),
    Break("hybrid_state_no_longer_requires_a_closed_gap", _QB,
          "    if not admissible and arch == A_DIRECT and hybrid_closes_gap:",
          "    if not admissible and arch == A_DIRECT:",
          (f"{_V}::test_the_hybrid_state_needs_BOTH_dominance_and_a_closed_gap",),
          "a PM consumption decision is indicated on dominance alone, without the swap actually "
          "closing the cross-position gap it is being recommended for"),
    Break("undefined_licenses_cross_rankability", _QB,
          "        return {\"state\": V_UNDEFINED, \"cross_rankable\": False,",
          "        return {\"state\": V_UNDEFINED, \"cross_rankable\": True,",
          (f"{_V}::test_undefined_never_licenses_cross_rankability",),
          "⭐ a harness that DID NOT RUN licenses the consumption it was built to gate — the "
          "worst shape of NF1.7 (a)"),

    # ── the registration + the runner's posture ────────────────────────────────────────────────
    Break("the_comparator_joins_family_bs_trial_field", _QB,
          "ELIGIBLE: tuple[str, ...] = (INCUMBENT, *REAL_ARMS)",
          "ELIGIBLE: tuple[str, ...] = (INCUMBENT, *REAL_ARMS, COMPARATOR)",
          (f"{_G}::test_the_comparator_is_not_in_family_bs_trial_field",),
          "⭐ a DIFFERENT ARCHITECTURE is bundled into the repair family's PBO/DSR field, "
          "over-taxing a real finding through cross-trial dispersion (MH2 (a)/NF-W6b-C)"),
    Break("the_pit_bar_is_relaxed", _QB,
          "PIT_MAX_DECILE_DEV = FA.PIT_MAX_DECILE_DEV              # 0.05",
          "PIT_MAX_DECILE_DEV = 0.08",
          (f"{_G}::test_every_gate_constant_is_inherited_by_reference_and_unrelaxed",),
          "⛔ a bar is re-read after the result it was written to gate (E2.1-r) — and inheriting "
          "BY REFERENCE is what makes that impossible to do quietly"),
    Break("one_field_wide_ceiling_replaces_the_per_form_oracles", _QB,
          "ORACLE_OF: dict[str, str] = {a: f\"oracle_{a}\" for a in REAL_ARMS}",
          "ORACLE_OF: dict[str, str] = {a: \"oracle_cond_shift\" for a in REAL_ARMS}",
          (f"{_G}::test_there_is_one_oracle_per_form",),
          "the forms NEST, so a single ceiling vetoes a legitimately-better nested form as a "
          "false metric inversion (NF-D16 (g‴))"),
    Break("stored_scores_rounded_capping_every_reproduction_pin", _RUN,
          "        \"crps\": float(np.mean(KW.crps_dense(bank, y))),",
          "        \"crps\": round(float(np.mean(KW.crps_dense(bank, y))), 6),",
          (f"{_R}::test_no_stored_score_is_rounded_away_from_the_pin_tolerance",),
          "⛔ the NF-W8-0 smoke bug re-armed: rounding caps every pin at ~5e-7 against 1e-9, so "
          "the decisive run returns UNDEFINED while reproducing perfectly"),
    Break("a_decided_predecessors_path_drops_out_of_the_refusal", _RUN,
          "                                   \"nf_w8_0b_tail_point\", \"nf_w8_0b_rows\", "
          "\"nf_w8_0b_input\")",
          "                                   \"nf_w8_0b_tail_point\", \"nf_w8_0b_input\")",
          (f"{_R}::test_the_runner_refuses_to_write_a_decided_predecessors_path",),
          "⭐ the NCAAF-P2.1 S1-serve lesson: a successor overwrites a DECIDED story's artifacts "
          "with no error and no test failure"),
    Break("classify_null_loses_its_declared_field_size", _RUN,
          "            declared_field_size=QB.DECLARED_FIELD_SIZE)",
          "            )",
          (f"{_R}::test_classify_null_is_called_with_the_declared_field_size",),
          "MH2.7: without the DECLARED field the instrument prescribes a smaller one — "
          "re-committing the exact selection bias it exists to deflate"),
    Break("an_unformable_oracle_is_skipped_rather_than_refused", _RUN,
          "        if not p.get(\"eligible\"):\n            raise ValueError(\n"
          "                f\"the peeking oracle `{QB.ORACLE_OF[arm]}` could not be FORMED on "
          "its own test \"\n                f\"fold ({p.get('reason')}) — a ceiling that failed "
          "to fit is a failed control, \"\n                f\"never a pass (NF1.7 (a))\")\n"
          "        _build(QB.ORACLE_OF[arm], arm, p)",
          "        if not p.get(\"eligible\"):\n            continue\n"
          "        _build(QB.ORACLE_OF[arm], arm, p)",
          (f"{_R}::test_an_unformable_oracle_raises_rather_than_being_skipped",),
          "a per-form CEILING that failed to fit is silently absent, so its captured-fraction "
          "reading is computed against nothing (NF1.7 (a))"),
    Break("an_arm_silently_drops_out_of_the_declared_field", _RUN,
          "    for arm in QB.REAL_ARMS:\n        _build(arm, arm, QB.fit_arm_params(arm, "
          "prior_ledgers))",
          "    for arm in QB.REAL_ARMS[:2]:\n        _build(arm, arm, QB.fit_arm_params(arm, "
          "prior_ledgers))",
          (f"{_E2E}",),
          "⭐ half the DECLARED field never reaches the scoring layer — a field scored with arms "
          "silently absent is not the declared field (MH2/NF1.7 (a)), and only a NON-VACUITY "
          "assertion in the path proof can see it"),
    Break("the_smoke_shrinks_to_a_single_fold_where_every_arm_is_identity", _RUN,
          "        folds = folds[-2:]",
          "        folds = folds[-1:]",
          (f"{_R}::test_the_smoke_keeps_enough_folds_for_an_arm_to_be_fitted_at_all",),
          "the path proof shrinks to ONE fold, where every arm is identity BY CONSTRUCTION — it "
          "would then exercise none of the declared field (NF1.7 (a), on the smoke itself)"),
    Break("the_runner_starts_writing_an_optimizer_input", _RUN,
          "_ROWS_DIR = Path(__file__).resolve().parent / \"artifacts\" / \"nf_w8_0c_rows\"",
          "_ROWS_DIR = _INPUT_DIR = Path(__file__).resolve().parent / \"artifacts\" / "
          "\"nf_w8_0c_rows\"",
          (f"{_R}::test_the_runner_writes_no_optimizer_input",),
          "prereg §9 is silently widened — a research story starts shipping a consumable "
          "artifact its verdict never licensed"),
)


def _restore_stale_backups() -> list[str]:
    """E11.26: this harness's own worst case is being killed mid-mutation, which leaves BROKEN
    SOURCE on disk. Restore any backup a previous run left behind BEFORE doing anything else."""
    restored = []
    for p in sorted(Path(__file__).parent.glob(f"*{_BACKUP_SUFFIX}")):
        target = p.with_suffix("")
        target = target.with_name(target.name.replace(_BACKUP_SUFFIX, ""))
        target.write_text(p.read_text())
        p.unlink()
        restored.append(target.name)
    return restored


def _run(tests: tuple[str, ...]) -> tuple[str, str]:
    args = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    for t in tests:
        args += [f"{_TESTS}::{t}"]
    try:
        p = subprocess.run(args, cwd=_ROOT, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "HUNG", f"no verdict within {_TIMEOUT_S}s"
    tail = (p.stdout or p.stderr).strip().splitlines()
    return ("RED" if p.returncode != 0 else "GREEN"), (tail[-1] if tail else "")


def main() -> int:
    stale = _restore_stale_backups()
    if stale:
        print(f"⚠️  restored stale backups from an interrupted run: {stale}")
    rows, failures = [], 0
    for b in BREAKS:
        original = b.path.read_text()
        occurrences = original.count(b.old)
        if occurrences != 1:
            rows.append((b.name, "ANCHOR", f"anchor occurs {occurrences}× — must be exactly 1"))
            failures += 1
            continue
        backup = b.path.with_name(b.path.name + _BACKUP_SUFFIX)
        backup.write_text(original)
        try:
            b.path.write_text(original.replace(b.old, b.new, 1))
            on_disk = b.path.read_text()
            if on_disk == original:
                rows.append((b.name, "NO-OP", "mutation did not LAND (E11.24 #682)"))
                failures += 1
                continue
            if b.old in on_disk:
                rows.append((b.name, "TOKEN", "asserted token still present (#815)"))
                failures += 1
                continue
            verdict, note = _run(b.tests)
        finally:
            b.path.write_text(original)
            backup.unlink(missing_ok=True)
        rows.append((b.name, verdict, note))
        if verdict != "RED":
            failures += 1

    w = max(len(r[0]) for r in rows)
    print(f"\nNF-W8-0c RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        print(f"  {name.ljust(w)}  {verdict:<6}  {note}")
    print(f"\n{len(rows) - failures}/{len(rows)} RED\n")
    if failures:
        print("⛔ a guard that does not go RED on a deliberate defect is VACUOUS", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
