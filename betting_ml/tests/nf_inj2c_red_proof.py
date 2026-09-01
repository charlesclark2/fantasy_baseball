"""nf_inj2c_red_proof.py — prove NF-INJ2c's node-1 guards actually FAIL on deliberately broken source.

    uv run python betting_ml/tests/nf_inj2c_red_proof.py

⛔ NOT a pytest module (no `test_` name) — it MUTATES source on disk. It restores every file in a
`finally`, and — the E11.26 lesson — it also restores any stale backup left by a previous run AT
STARTUP, because its own worst case is being killed mid-mutation.

THREE WAYS A RED PROOF LIES, all closed here:
  * #682 — the mutation NEVER LANDED (a quoting bug) and the pass was read as "the guard is
    vacuous". Every break asserts the file CHANGED on disk before pytest is invoked.
  * #815 — the mutation landed but did not move the ASSERTED predicate. Every break asserts its
    `gone` token is ABSENT afterwards, not merely that the file differs.
  * E11.24 `prediction_log` — `replace(old, new, 1)` landed on the WRONG symbol because two
    functions had byte-identical tails, and the harness reported a FALSE vacuity, which is the
    dangerous direction (it invites weakening a correct guard). Every anchor is asserted UNIQUE in
    its file before it is applied.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DIAG = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_nf_inj2c_coherence_diagnosis.py"
_INJ2_MD = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                    "nf_inj2_rate_permutation.md")
_CLAUDE = _REPO / "CLAUDE.md"
_BASE = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/"
                 "run_nf_inj2c_dominance_baseline.py")
_RULE = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_inj2c_margin_construction_rule.md")
_FOLD = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                 "nf_inj2c_fold_fidelity_finding.md")
_PREREG = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                   "nf_inj2c_preregistration.md")
_SPEC = _REPO / "plan_specs/nfl_fantasy/nf-inj2c.yaml"
_SUITE = "betting_ml/tests/test_nf_inj2c_coherence_diagnosis.py"
#: nodes 3a/3b/3c live in their own suite; the harness routes each break to the suite that owns it.
_SUITE_BY_NODE = {}

#: (label, file, anchor, replacement, token that must be GONE afterwards, the guard(s) it must break)
BREAKS: list[tuple[str, Path, str, str, str, str]] = [
    ("the kernel-floor count silently narrows to the recorded definition", _DIAG,
     'moved = np.where(np.isfinite(g), gsafe != g, True)',
     'moved = np.where(np.isfinite(g), gsafe != g, False)',
     # ⚠️ the `gone` token must be as SPECIFIC as the anchor: `attribute()` carries the identical
     # expression under the name `floored`, so a loose token survives the mutation and the harness
     # (correctly) refuses the break rather than reporting a false vacuity (#815 / E11.24).
     'moved = np.where(np.isfinite(g), gsafe != g, True)',
     "test_the_recorded_binding_count_misses_a_non_finite_row_the_kernel_does_floor"),

    ("an inactive floor stops refuting the hypothesis", _DIAG,
     '    if not can_act:\n        state = "REFUTED"',
     '    if not can_act:\n        state = "ESTABLISHED"',
     'if not can_act:\n        state = "REFUTED"',
     "test_a_floor_that_cannot_act_refutes_the_hypothesis"),

    ("a floor-attributed violation stops ESTABLISHING it", _DIAG,
     '        state = "ESTABLISHED"\n        why = (f"{m1} of {total}',
     '        state = "REFUTED"\n        why = (f"{m1} of {total}',
     '        state = "ESTABLISHED"\n        why = (f"{m1} of {total}',
     "test_one_floor_attributed_violation_establishes_it"),

    ("the pre-existing CONTROL stops outranking the floor in attribution", _DIAG,
     '    if pre_existing:\n        return "M4_PRE_EXISTING"\n    if floored:',
     '    if floored:\n        return "M1_GAMES_FLOOR"\n    if pre_existing:',
     '    if pre_existing:\n        return "M4_PRE_EXISTING"',
     "test_attribution_by_control_outranks_the_floor_when_both_clauses_are_true"),

    ("the unexplained residual defaults to the hypothesis under test", _DIAG,
     '    return "M3_STAT_MIX_OR_PROMOTION"',
     '    return "M1_GAMES_FLOOR"',
     '    return "M3_STAT_MIX_OR_PROMOTION"',
     "test_a_row_no_clause_explains_falls_to_stat_mix_rather_than_to_the_hypothesis"),

    ("the under-2-games share is computed over the board instead of the violating rows", _DIAG,
     'acc["share_rows_under_2_games"] = round(sum(1 for x in g if x < 2.0) / len(g), 4) if g else None',
     'acc["share_rows_under_2_games"] = round(sum(1 for x in g if x < 2.0) / (len(g) + 100), 4) if g else None',
     '/ len(g), 4) if g else None',
     "test_the_under_two_games_share_is_over_the_violating_rows_not_the_board"),

    ("an arm with no violation reports a clean 0.0 worst breach instead of None", _DIAG,
     'acc["max_times_over"] = round(max(t), 3) if t else None',
     'acc["max_times_over"] = round(max(t), 3) if t else 0.0',
     'round(max(t), 3) if t else None',
     "test_an_arm_with_no_violation_profiles_as_empty_rather_than_as_clean_numbers"),

    ("the D4 annotation loses its POST-HOC marker", _INJ2_MD,
     "> This block is a POST-HOC ANNOTATION",
     "> This block is a note",
     "POST-HOC ANNOTATION",
     "test_the_d4_annotation_is_on_nf_inj2s_record_and_is_marked_as_an_annotation"),

    ("the D4 annotation drops the measurement and keeps only the suspicion", _INJ2_MD,
     "`served_giveback_pct` is **33.96 on all seven arms**",
     "`served_giveback_pct` may be the arm's own number",
     "33.96 on all seven arms",
     "test_the_d4_annotation_records_the_measurement_that_settles_the_baseline_question"),

    ("the D3 landmine loses its dated CORRECTION marker, so a reader cannot tell it was re-measured",
     _CLAUDE,
     "⚠️ MECHANISM CORRECTED IN PLACE 2026-09-01 from a misattribution",
     "(mechanism as originally recorded)",
     "MECHANISM CORRECTED IN PLACE 2026-09-01",
     "test_the_d3_pin_against_capture_landmine_is_in_claude_md"),

    ("the D3 landmine reverts to prescribing a same-day rebuild as sufficient", _CLAUDE,
     "A SAME-DAY REBUILD IS NECESSARY BUT **NOT SUFFICIENT**",
     "A SAME-DAY REBUILD IS WHAT IT NEEDS",
     "SAME-DAY REBUILD IS NECESSARY BUT **NOT SUFFICIENT**",
     "test_the_d3_pin_against_capture_landmine_is_in_claude_md"),

    # RE-AIMED 2026-09-01 with the entry's correction: the measurement now lives in the
    # corrected mechanism sentence, and the guard pins BOTH failures (40.58 and 84.72).
    ("the D3 landmine loses the measurement that makes it actionable", _CLAUDE,
     "pin failed at **40.58** with its rebuild on the **SAME UTC DAY**",
     "pin failed with its rebuild on the **SAME UTC DAY**",
     "40.58",
     "test_the_d3_pin_against_capture_landmine_is_in_claude_md"),

    # ── nodes 3a / 3b / 3c ────────────────────────────────────────────────────────────────────
    ("the runner invents a tie band the committed rule does not name", _BASE,
     "M4_TIE_BAND = 0.01",
     "M4_TIE_BAND = 5.0",
     "M4_TIE_BAND = 0.01",
     "test_every_band_the_runner_applies_is_named_in_the_rule"),

    ("the capture-pin stops refusing a RE-PULLED board", _BASE,
     "    if now != stamp.get(\"sha256\"):",
     "    if False:",
     "if now != stamp.get(\"sha256\"):",
     "test_a_REPULLED_board_is_refused_which_is_the_whole_point_of_D3"),

    ("a mid-study recapture stops being refused", _BASE,
     "    if _CAPTURE_STAMP.exists() and not force:",
     "    if False:",
     "if _CAPTURE_STAMP.exists() and not force:",
     "test_recapturing_mid_study_is_refused_without_an_explicit_flag"),

    ("an unevaluable measure is scored as a pass", _BASE,
     '                row[f"{key}_verdict"] = "UNEVALUABLE"   # ⛔ never scored as a pass (NF1.7 (a))',
     '                row[f"{key}_verdict"] = "IMPROVES"',
     'row[f"{key}_verdict"] = "UNEVALUABLE"',
     "test_a_measure_with_no_value_is_UNEVALUABLE_and_never_a_pass"),

    ("the give-back measure reverts to the SIGNED value and rewards over-discounting", _BASE,
     "    return None if pct is None else max(float(pct), 0.0)",
     "    return None if pct is None else float(pct)",
     "max(float(pct), 0.0)",
     "test_the_giveback_measure_does_not_reward_over_discounting"),

    ("the attribution CONTROL arm becomes droppable", _BASE,
     '    if "incumbent" not in arms or "mvp1_null" not in arms:',
     "    if False:",
     '"mvp1_null" not in arms:',
     "test_the_attribution_control_arm_cannot_be_dropped_from_a_run"),

    ("the margin rule drops its ban on a band derived from an observed gap", _RULE,
     "no\nband may be derived from an observed arm-vs-incumbent gap",
     "a band may be derived however is convenient",
     "band may be derived from an observed arm-vs-incumbent gap",
     "test_the_rule_forbids_a_band_derived_from_an_observed_gap"),

    ("the margin rule loses the PM's NULL branch", _RULE,
     "that is a NULL, not a margin to adjust",
     "that is a margin to revisit",
     "that is a NULL, not a margin to adjust",
     "test_the_rule_carries_the_pms_null_branch_verbatim"),

    ("the fold finding stops refusing to pick the declared field", _FOLD,
     "no per-candidate-family DSR has been computed",
     "the narrowest clearing family was selected",
     "no per-candidate-family DSR has been computed",
     "test_the_finding_refuses_to_pick_the_declared_field"),

    # ⚠️ `1.6418` appears TWICE (the table and the precision caveat), so a single-occurrence break
    # on it does not move the guard's predicate — the harness caught that and refused (#815). The
    # Sharpe DELTA is unique AND is the statistic the finding turns on.
    ("the fold finding drops the measurement showing the 8th fold hurts", _FOLD,
     "**−0.3682**",
     "**(not computed)**",
     "−0.3682",
     "test_the_finding_records_that_the_eighth_fold_moves_the_gate_the_WRONG_way"),

    ("the fresh-worktree cache landmine is removed", _CLAUDE,
     "SILENTLY REBUILDS THE GITIGNORED FEATURE CACHES FROM A LIVE UPSTREAM",
     "rebuilds caches",
     "SILENTLY REBUILDS THE GITIGNORED FEATURE CACHES FROM A LIVE UPSTREAM",
     "test_the_fresh_worktree_cache_rebuild_landmine_is_in_claude_md"),
    # ── node 3 — the PRE-REGISTRATION and the PM ruling of 2026-09-01 ─────────────────────────
    ("the PM's field declaration loses its no-third-field clause", _SPEC,
     "        no third field is ever computed. If the binding family's DSR refuses, that is\n",
     "        a third field may be computed if needed. If the binding family's DSR refuses, that is\n",
     "no third field is ever computed. If the binding family's DSR refuses",
     "test_the_pm_field_declaration_is_transcribed_verbatim"),

    # ⭐ this break is aimed at ruling 4's OPENING clause, not at the sentence the correction
    # annotation quotes — the first cut used the quoted sentence and the harness refused it,
    # exposing a VACUOUS guard (the annotation satisfied the check written to police it).
    ("ruling 4 is TIDIED AWAY in place instead of annotated beside", _SPEC,
     "        4. THE +1 FOLD is registered forward on the data-fidelity ruling already given\n",
     "        4. THE +1 FOLD is WITHDRAWN; the registration runs at seven folds\n",
     "4. THE +1 FOLD is registered forward on the data-fidelity ruling already given",
     "test_ruling_4_stays_standing_unedited_with_the_correction_beside_it"),

    ("the correction annotation stops saying the premise is false", _SPEC,
     "        fold would settle the gate, so \"DSR at 8 folds is then a real gate, not a\n        formality\" — is MEASURED FALSE",
     "        fold would settle the gate — is NOTED",
     "is MEASURED FALSE",
     "test_ruling_4_stays_standing_unedited_with_the_correction_beside_it"),

    ("the calendar-bound trigger loses the PM's reason for allowing it", _SPEC,
     "        8th fold as calendar-bound: the realized 2026 season — that is a genuinely\n        reachable trigger and may be published as one",
     "        8th fold as calendar-bound",
     "that is a genuinely\n        reachable trigger and may be published as one",
     "test_the_calendar_bound_eighth_fold_is_recorded_as_the_only_remaining_one"),

    ("the resolved hold reverts to a stale HELD marker", _SPEC,
     "      ✅ RESOLVED BY PM RULING 2026-09-01 — THE FOLD AND THE FIELD",
     "      ⛔ HELD FOR A PM RULING — THE DSR FIELD DECLARATION — THE FOLD AND THE FIELD",
     "RESOLVED BY PM RULING 2026-09-01",
     "test_the_spec_no_longer_records_the_field_as_held"),

    ("the binding field silently widens back to ten arms", _PREREG,
     "`declared_field_size = 5`, passed to `cv_power.classify_null(declared_field_size=5)`",
     "`declared_field_size = 10`, passed to `cv_power.classify_null(declared_field_size=10)`",
     "`declared_field_size = 5`",
     "test_the_binding_field_is_the_five_point_space_arms_and_only_those"),

    ("the exclusion stops saying it is not on the arms' scores", _PREREG,
     "different mechanism, ⛔ not because of anything they scored.",
     "different mechanism.",
     "not because of anything they scored",
     "test_the_binding_field_is_the_five_point_space_arms_and_only_those"),

    ("the two-member V is declared but left as an escape hatch", _PREREG,
     "an explanation after a number arrives. ⛔ It is not a licence to change the field afterwards.",
     "an explanation after a number arrives.",
     "It is not a licence to change the field afterwards",
     "test_the_two_member_V_is_declared_forward_as_a_fragility"),

    ("the field-trim reading stops being declared structurally unavailable", _PREREG,
     "if DSR refuses, the 2×2 is reported as **STRUCTURALLY UNAVAILABLE**, ⛔ never as a trimmed number.",
     "if DSR refuses, the 2×2 is reported with its largest contributor dropped.",
     "the 2×2 is reported as **STRUCTURALLY UNAVAILABLE**",
     "test_the_field_trim_reading_is_declared_structurally_unavailable"),

    ("DSR-CONV's non-monotonicity is dropped, so exclusion reads as a lever", _PREREG,
     "**(c) DSR-CONV'S EXCLUSION IS NON-MONOTONE, SO IT IS NOT A LEVER.**",
     "**(c) DSR-CONV'S EXCLUSION LOWERS THE BAR.**",
     "NON-MONOTONE",
     "test_dsr_conv_non_monotonicity_is_declared_so_it_is_not_read_as_a_lever"),

    ("the diagnostic field is left able to rescue a binding refusal", _PREREG,
     "where it is more favourable than the binding number. It ⛔ **cannot rescue a binding refusal** and no\ndisposition reads it.",
     "where it is more favourable than the binding number.",
     "cannot rescue a binding refusal",
     "test_the_diagnostic_field_is_declared_non_binding_in_advance"),

    ("the registration quietly runs at eight folds", _PREREG,
     "* **Folds: SEVEN — 2019–2025**, inherited from NF1.5's own `score_from`",
     "* **Folds: EIGHT — 2018–2025**, inherited from NF1.5's own `score_from`",
     "**Folds: SEVEN — 2019–2025**",
     "test_the_registration_runs_at_seven_folds"),

    ("the 2026 trigger loses its reachability condition", _PREREG,
     "  **WITHHELD with that reason stated** rather than published",
     "  published anyway",
     "WITHHELD with that reason stated",
     "test_the_2026_trigger_carries_its_reachability_condition"),

    ("a design quantity is transcribed wrong rather than computed", _PREREG,
     "`cv_power.dsr_ceiling(7) = 0.99973` against a 0.95 bar",
     "`cv_power.dsr_ceiling(7) = 0.94210` against a 0.95 bar",
     "0.99973",
     "test_the_design_quantities_are_the_ones_cv_power_actually_computes"),

    ("coherence drifts back toward being read as a distance from zero", _PREREG,
     "incumbent**, ⛔ never as a distance from zero.",
     "incumbent**.",
     "never as a distance from zero",
     "test_coherence_is_measured_and_reported_never_gated_at_zero"),

    ("the prereg starts RESTATING the bands instead of pointing at them", _PREREG,
     "was committed before the re-measure; this is a pointer, not a restatement with room to drift.",
     "was committed before the re-measure.",
     "this is a pointer, not a restatement",
     "test_the_prereg_points_at_the_margin_rule_rather_than_restating_it"),

    ("a declared dominance measure is dropped between 3a and the registration", _PREREG,
     "| M6 | per-group interval coverage |",
     "| M6-REMOVED | per-group interval coverage |",
     "| M6 | per-group interval coverage |",
     "test_every_margin_rule_measure_survives_into_the_registration"),

    ("a regression stops being a NULL and becomes a band to widen", _PREREG,
     "regression, and by PM ruling 3 that is a NULL** — ⛔ never a band to widen, a measure to drop, or a\ndimension to re-classify as disclosed-only.",
     "regression** — the band is widened to the observed gap.",
     "never a band to widen",
     "test_a_single_regression_is_a_null_and_not_a_band_to_widen"),

    ("the injection-invariant partition is dropped from the control", _PREREG,
     "| **INJECTION-INVARIANT** | M2, M3, M4 (board coherence + give-back), M6 floors |",
     "| **ALSO CHECKED** | M2, M3, M4 (board coherence + give-back), M6 floors |",
     "INJECTION-INVARIANT",
     "test_the_injection_invariant_partition_is_declared_forward"),

    ("the control is left re-runnable with the blocker removed", _PREREG,
     "⛔ **The control is never re-run\nwith a constraint removed to obtain a nicer badge** (E2.1-r).",
     "The control may be re-run without the blocker.",
     "never re-run\nwith a constraint removed",
     "test_the_injection_invariant_partition_is_declared_forward"),

    ("the PLAT-CVP2 status claim is removed rather than checked", _PREREG,
     "(the `CONSTRAINT_BLOCKED` instrument fix) **has not landed**: verified at this",
     "(the `CONSTRAINT_BLOCKED` instrument fix) is not discussed here: verified at this",
     "**has not landed**",
     "test_the_plat_cvp2_claim_is_true_of_the_installed_instrument"),

    ("the deflation-gate partition stops taking the shipped defaults", _PREREG,
     "The shipped `cv_power` defaults are taken **unchanged** — ⛔ no `deflation_gates=`\noverride is registered, so none may be passed.",
     "A `deflation_gates=` override is registered for this study.",
     "override is registered, so none may be passed",
     "test_the_deflation_gate_partition_takes_the_shipped_defaults"),

    ("the provenance claim about node 3b is removed", _PREREG,
     "**Committed BEFORE any arm is scored, and BEFORE the node-3b re-measure has been run**",
     "**Committed at some point in the story**",
     "BEFORE the node-3b re-measure has been run",
     "test_the_prereg_was_written_before_the_remeasure_and_says_so_checkably"),

    ("the prereg opens an edit path for the incumbent baseline", _PREREG,
     "⛔ never copied into this one. That is deliberate",
     "copied into this one once node 3b runs. That is deliberate",
     "⛔ never copied into this one",
     "test_the_prereg_does_not_quote_the_incumbent_baseline"),

    ("the NF-INJ3b-M no-menu-of-DSRs claim is dropped", _PREREG,
     "  any candidate family** — ⛔ no per-candidate-family DSR was computed, per the NF-INJ3b-M rule.",
     "  any candidate family**.",
     "no per-candidate-family DSR was computed",
     "test_no_per_candidate_family_dsr_was_computed_before_the_declaration"),

    ("3a's superseded branch is REWRITTEN in place instead of marked", _RULE,
     "5. **DSR at 8 folds does not clear 0.95**",
     "5. **DSR at 7 folds does not clear 0.95**",
     "DSR at 8 folds does not clear 0.95",
     "test_the_superseded_margin_rule_branch_is_marked_not_edited"),
    # ── node 3b (PM ruling 2026-09-01 (a)) — the MARKET-VINTAGE precondition ──────────────────
    ("a mismatched market vintage stops being refused", _BASE,
     '        elif str(mine) != str(served):',
     '        elif False:',
     'elif str(mine) != str(served):',
     "test_the_run_1_mismatch_REFUSES_and_names_input_both_vintages_and_the_fix"),

    ("an UNREADABLE local vintage is scored as a pass", _BASE,
     '        elif mine is None:\n            problems.append(',
     '        elif mine is None:\n            _ignored = (',
     'elif mine is None:\n            problems.append(',
     "test_an_unreadable_local_vintage_REFUSES_rather_than_passing"),

    ("a manifest with no vintage is scored as a pass", _BASE,
     '        if served is None:\n            problems.append(',
     '        if served is None:\n            _skipped = (',
     'if served is None:\n            problems.append(',
     "test_a_manifest_without_the_vintage_REFUSES_rather_than_passing"),

    ("the refusal drops the remedy the operator needs", _BASE,
     '                f" — MISMATCHED. Refresh it, then re-capture:\\n      {cmd}")',
     '                f" — MISMATCHED.")',
     'MISMATCHED. Refresh it, then re-capture',
     "test_the_run_1_mismatch_REFUSES_and_names_input_both_vintages_and_the_fix"),

    ("capture stops enforcing the precondition, so it can be bypassed", _BASE,
     '    vintage = assert_market_vintage_matches()\n    doc = json.loads(_SERVED_JSON.read_text())',
     '    vintage = market_vintage()\n    doc = json.loads(_SERVED_JSON.read_text())',
     # ⚠️ the gone-token must not be a SUBSTRING of the sibling call: `now_vintage = assert_…`
     # in `assert_capture_intact` contains `vintage = assert_…` verbatim (the E11.24 wrong-symbol
     # class, caught by the harness rather than by review).
     '    vintage = assert_market_vintage_matches()\n    doc = json.loads',
     "test_capture_enforces_the_precondition_so_it_cannot_be_bypassed"),

    ("the run path stops re-checking that the caches held still", _BASE,
     '    now_vintage = assert_market_vintage_matches()\n    captured_vintage = stamp.get("market_vintage")',
     '    now_vintage = market_vintage()\n    captured_vintage = None',
     'now_vintage = assert_market_vintage_matches()',
     "test_the_run_path_rechecks_that_the_caches_did_not_move_after_the_capture"),

    ("the market-input registry is emptied, so the precondition checks nothing", _BASE,
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = (\n    ("adp", "adp_as_of",',
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = ()\n_UNUSED = (\n    ("adp", "adp_as_of",',
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = (\n    ("adp", "adp_as_of",',
     "test_every_declared_market_input_carries_a_real_refresh_command"),

    ("a MATCHED vintage starts being refused too, blocking the study outright", _BASE,
     '        elif str(mine) != str(served):',
     '        elif True:',
     'elif str(mine) != str(served):',
     "test_a_matched_market_vintage_PASSES"),
]


def _bak(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".redproof.bak")


def _restore_stale() -> None:
    """A previous run killed mid-mutation would leave a .bak beside a BROKEN file. Restore first —
    a red proof whose own failure mode is leaving deliberately broken source on disk is worse than
    no red proof (E11.26)."""
    for path in {b[1] for b in BREAKS}:
        b = _bak(path)
        if b.exists():
            print(f"  ⚠️  restoring a STALE backup left by an earlier run: {path.name}")
            path.write_text(b.read_text())
            b.unlink()


def _run(node_id: str) -> bool:
    suite = _SUITE_BY_NODE.get(node_id, _SUITE)
    r = subprocess.run([sys.executable, "-m", "pytest", f"{suite}::{node_id}", "-q",
                        "--no-header", "-p", "no:cacheprovider"],
                       cwd=_REPO, capture_output=True, text=True)
    return r.returncode == 0


#: every suite a break may belong to. The harness routes each break to the suite that OWNS its
#: guard, so a shared guard is never run from the wrong shard (CLAUDE.md's owning-shard rule).
_OTHER_SUITES = (
    "betting_ml/tests/test_nf_inj2c_dominance_baseline.py",
    "betting_ml/tests/test_nf_inj2c_preregistration.py",
)


def main() -> int:
    import subprocess as _sp
    for _suite in _OTHER_SUITES:
        names = _sp.run([sys.executable, "-m", "pytest", _suite, "--collect-only", "-q",
                         "-p", "no:cacheprovider"], cwd=_REPO,
                        capture_output=True, text=True).stdout
        for _label, _p, _a, _r, _g, _node in BREAKS:
            if f"::{_node}" in names:
                _SUITE_BY_NODE[_node] = _suite
    _restore_stale()
    reds, greens = 0, []
    for label, path, anchor, repl, gone, node in BREAKS:
        src = path.read_text()
        # ⭐ the E11.24 lesson: a non-unique anchor makes `replace(..., 1)` land on the wrong symbol
        # and the harness reports a FALSE vacuity.
        n = src.count(anchor)
        if n != 1:
            print(f"  ✗ ANCHOR NOT UNIQUE ({n} occurrences) for {label!r} — the break cannot be "
                  f"trusted to land where it is aimed")
            greens.append(label)
            continue
        _bak(path).write_text(src)
        try:
            path.write_text(src.replace(anchor, repl, 1))
            after = path.read_text()
            if after == src:
                print(f"  ✗ MALFORMED BREAK — the mutation for {label!r} did not LAND (#682)")
                greens.append(label)
                continue
            if gone in after:
                print(f"  ✗ MALFORMED BREAK — {label!r} landed but {gone!r} SURVIVED, so it cannot "
                      f"move the predicate the guard reads (#815)")
                greens.append(label)
                continue
            if _run(node):
                print(f"  ✗ GREEN on broken source — {label}  →  {node}")
                greens.append(label)
            else:
                print(f"  ✓ RED — {label}")
                reds += 1
        finally:
            path.write_text(_bak(path).read_text())
            _bak(path).unlink()
    print(f"\n{reds}/{len(BREAKS)} deliberate breaks were caught.")
    if greens:
        print("VACUOUS GUARDS:")
        for g in greens:
            print(f"  - {g}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
