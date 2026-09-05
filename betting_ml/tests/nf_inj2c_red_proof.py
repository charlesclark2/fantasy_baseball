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
_N12 = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_nf1_2.py"
_N15 = _REPO / "quant_sports_intel_models/football/nfl/fantasy/run_nf1_5.py"
_RB = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/run_nf_inj2b_rate_ordering.py")
_GITIGNORE = _REPO / ".gitignore"
_DEC = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/run_nf_inj2c_decisive.py")
_REG2C = _REPO / ("quant_sports_intel_models/football/nfl/fantasy/nf_inj2c_assignment_rule.py")
_SUITE = "betting_ml/tests/test_nf_inj2c_coherence_diagnosis.py"
#: nodes 3a/3b/3c live in their own suite; the harness routes each break to the suite that owns it.
_SUITE_BY_NODE = {}

#: (label, file, anchor, replacement, token that must be GONE afterwards, the guard(s) it must break)
BREAKS: list[tuple[str, Path, str, str, str, str]] = [
    ("the kernel-floor count silently narrows to the recorded definition", _DIAG,
     'floored = np.where(np.isfinite(g), gsafe != g, True)',
     'floored = np.where(np.isfinite(g), gsafe != g, False)',
     # ⚠️ the `gone` token must be as SPECIFIC as the anchor (#815 / E11.24). RE-ANCHORED
     # 2026-09-03: PLAT-CVP2 (642ca608) renamed this binding `moved` -> `floored`, which retired
     # the old anchor and left this guard silently UN-RED-PROVEN — the harness caught it as
     # "ANCHOR NOT UNIQUE (0 occurrences)" rather than reporting a false vacuity. Re-anchored onto
     # the new implementation, never weakened or deleted (MH2.7).
     'floored = np.where(np.isfinite(g), gsafe != g, True)',
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
     '        elif str(mine) != str(served):\n            problems.append(',
     '        elif False:\n            problems.append(',
     'elif str(mine) != str(served):\n            problems.append(',
     # RE-ANCHORED at D3 (2026-09-03): the precondition widened and moved this call/expression.
     # Re-anchored onto the new implementation, never weakened (MH2.7).
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
     '    vintage = assert_vintages_match(con, season, schema)\n    doc = json.loads(_SERVED_JSON.read_text())',
     '    vintage = market_vintage()\n    doc = json.loads(_SERVED_JSON.read_text())',
     # ⚠️ the gone-token must not be a SUBSTRING of the sibling call: `now_vintage = assert_…`
     # in `assert_capture_intact` contains `vintage = assert_…` verbatim (the E11.24 wrong-symbol
     # class, caught by the harness rather than by review).
     '    vintage = assert_vintages_match(con, season, schema)\n    doc = json.loads',
     "test_capture_enforces_the_precondition_so_it_cannot_be_bypassed"),

    ("the run path stops re-checking that the caches held still", _BASE,
     '    now_vintage = assert_vintages_match(con, season, schema)\n    captured_vintage = stamp.get("market_vintage")',
     '    now_vintage = market_vintage()\n    captured_vintage = None',
     'now_vintage = assert_vintages_match(con, season, schema)',
     "test_the_run_path_rechecks_that_the_caches_did_not_move_after_the_capture"),

    ("the market-input registry is emptied, so the precondition checks nothing", _BASE,
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = (\n    ("adp", "adp_as_of",',
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = ()\n_UNUSED = (\n    ("adp", "adp_as_of",',
     '_MARKET_INPUTS: tuple[tuple[str, str, str], ...] = (\n    ("adp", "adp_as_of",',
     "test_every_declared_market_input_carries_a_real_refresh_command"),

    ("a MATCHED vintage starts being refused too, blocking the study outright", _BASE,
     '        elif str(mine) != str(served):\n            problems.append(',
     '        elif True:\n            problems.append(',
     'elif str(mine) != str(served):\n            problems.append(',
     # RE-ANCHORED at D3 (2026-09-03): the precondition widened and moved this call/expression.
     # Re-anchored onto the new implementation, never weakened (MH2.7).
     "test_a_matched_market_vintage_PASSES"),
    # ── the cache guard (NF-INJ2c, 2026-09-03) ────────────────────────────────────────────────
    # The guard checked 20 of the NF1.5 pool's 120 columns and was blind to the other 100, so a
    # Jul-31 cache missing 5 registered columns was served as "current" for a month. These breaks
    # prove the fix cannot silently revert to that state.
    ("the guard ignores the caller's family (the pre-fix behaviour)", _N12,
     "    return not missing_registered_cols(pool, required)",
     "    return not missing_registered_cols(pool, None)",
     "return not missing_registered_cols(pool, required)",
     "test_a_pool_missing_five_registered_columns_REFUSES"),

    ("missing_registered_cols always reports 'nothing missing'", _N12,
     "    return sorted(c for c in req if c not in pool.columns)",
     "    return []",
     "return sorted(c for c in req if c not in pool.columns)",
     "test_a_pool_missing_five_registered_columns_REFUSES"),

    ("POOL_REQUIRED_COLS is hand-listed instead of DERIVED", _N15,
     '''POOL_REQUIRED_COLS: frozenset[str] = frozenset(
    {c for feats in M13.POSITION_FEATURES.values() for c in feats}
    | set(M13.MARKET_FEATURES)
    | set(M12.REFINEMENT_COLS)
    | {"real_fp_ppr", "real_games"}
)''',
     'POOL_REQUIRED_COLS: frozenset[str] = frozenset({"wopr", "team_pace"})',
     "{c for feats in M13.POSITION_FEATURES.values() for c in feats}",
     "test_the_required_family_is_DERIVED_so_a_new_feature_joins_without_an_edit"),

    ("build_pool stops passing the family to the guard (wired != invoked)", _N15,
     "absent = missing_registered_cols(cached, POOL_REQUIRED_COLS)",
     "absent = missing_registered_cols(cached)",
     "missing_registered_cols(cached, POOL_REQUIRED_COLS)",
     "test_build_pool_actually_passes_the_family_to_the_guard"),

    ("an empty/absent pool is scored as current (NF1.7(a))", _N12,
     "        return sorted(required if required is not None else M12.REFINEMENT_COLS)",
     "        return []",
     "return sorted(required if required is not None else M12.REFINEMENT_COLS)",
     "test_an_absent_or_empty_pool_refuses"),
    # ── D3: the widened vintage precondition (PM ruling 2026-09-03) ──────────────────
    ('the ADP window table is emptied, so a same-day re-pull passes', _BASE,
     '("window_start", "start_date"), ("window_end", "end_date"), ("drafts", "total_drafts"),',
     '',
     '("window_start", "start_date")',
     'test_a_moved_adp_window_REFUSES_even_though_the_DAY_still_matches'),
    ('the ECR fingerprint table is emptied', _BASE,
     '_ECR_FINGERPRINT_FIELDS: tuple[tuple[str, str], ...] = (("experts", "total_experts"),)',
     '_ECR_FINGERPRINT_FIELDS: tuple[tuple[str, str], ...] = ()',
     '(("experts", "total_experts"),)',
     'test_a_changed_ecr_expert_count_REFUSES_even_though_the_DAY_still_matches'),
    ('a consensus published AFTER the board stops being refused', _BASE,
     '            if when > board:',
     '            if False:  # was: when later than board',
     'if when > board:',
     'test_an_ecr_consensus_published_AFTER_the_board_REFUSES'),
    ('the input-vintage leg iterates nothing', _BASE,
     '    for key, got in input_vintage(con, season, schema).items():',
     '    for key, got in dict().items():',
     'for key, got in input_vintage(con, season, schema).items():',
     'test_a_mismatched_input_vintage_REFUSES_and_names_the_mart_rebuild'),
    ('a missing marts connection is scored as a pass (NF1.7(a))', _BASE,
     '    if con is None:',
     '    if con is None and False:',
     '    if con is None:',
     'test_a_published_input_vintage_with_NO_marts_connection_REFUSES'),
    ("the input-vintage leg hardcodes its keys instead of reading the manifest's", _BASE,
     '    return {k: {"served": served.get(k), "local": local.get(k)} for k in served}',
     '    return {k: {"served": served.get(k), "local": local.get(k)}\n            for k in ("depth_chart_as_of", "sleeper_status_as_of")}',
     'for k in served}',
     'test_the_input_vintage_leg_is_TABLE_DRIVEN_over_the_manifests_own_keys'),

    # ── PM ruling, decision request #5: the pin is evaluated at the PUBLISHED artifact's own
    # resolution. Both directions are RED-proven — a correct reproduction must PASS, a genuinely
    # wrong row must still REFUSE — because a fix in either direction alone is the defect.
    ("the pin compares a DECIMAL bar with raw BINARY `<=` again (the defect)", _RB,
     'return bool(w <= PUBLISHED_ROUNDING_TOL + PUBLISHED_TOL_REPR_EPS)',
     'return bool(w <= PUBLISHED_ROUNDING_TOL)',
     'PUBLISHED_ROUNDING_TOL + PUBLISHED_TOL_REPR_EPS',
     "TestACorrectReproductionPasses::test_the_exact_measured_worst_passes"),

    ("the representation epsilon is widened into SLACK", _RB,
     'PUBLISHED_TOL_REPR_EPS = 1e-9',
     'PUBLISHED_TOL_REPR_EPS = 1e-3',
     'PUBLISHED_TOL_REPR_EPS = 1e-9',
     "TestAWrongRowStillRefuses::test_the_epsilon_is_not_slack_at_any_material_scale"),

    ("the epsilon shrinks until it no longer covers the error it exists for", _RB,
     'PUBLISHED_TOL_REPR_EPS = 1e-9',
     'PUBLISHED_TOL_REPR_EPS = 1e-15',
     'PUBLISHED_TOL_REPR_EPS = 1e-9',
     "TestTheRegisteredBarIsUnchanged::"
     "test_the_epsilon_brackets_the_representation_error_without_reaching_the_data"),

    # ⭐ the E2.1-r break: "fix" the pin by MOVING THE BAR instead of the comparison. This is the
    # thing the PM ruling explicitly did NOT authorise, so a guard must refuse it.
    ("the REGISTERED BAR is moved instead of the comparison being fixed", _RB,
     'PUBLISHED_ROUNDING_TOL = 0.05',
     'PUBLISHED_ROUNDING_TOL = 0.06',
     'PUBLISHED_ROUNDING_TOL = 0.05',
     "TestTheRegisteredBarIsUnchanged::test_the_tolerance_is_still_half_the_published_quantum"),

    ("the comparison stops failing closed on an unevaluable worst", _RB,
     '    if not math.isfinite(w):\n        return False\n',
     '    if math.isinf(w) and w > 0:\n        return False\n',
     'if not math.isfinite(w):',
     "TestAWrongRowStillRefuses::test_an_unevaluable_worst_refuses"),

    ("the pin stops routing through the helper (wired != invoked)", _RB,
     '"reproduces": reproduces_at_published_resolution(worst),',
     '"reproduces": bool(worst <= PUBLISHED_ROUNDING_TOL),',
     'reproduces_at_published_resolution(worst)',
     "TestThePinUsesIt::test_the_pin_calls_the_helper_rather_than_comparing_raw"),

    ("the pin folds the epsilon into the reported tolerance, hiding that the bar did not move", _RB,
     '            "representation_epsilon": PUBLISHED_TOL_REPR_EPS,\n',
     '',
     '"representation_epsilon": PUBLISHED_TOL_REPR_EPS',
     "TestThePinUsesIt::test_the_pin_reports_the_bar_and_the_epsilon_SEPARATELY"),

    ("the comparison site stops saying the epsilon is not slack", _RB,
     '⛔ `PUBLISHED_TOL_REPR_EPS` IS NOT slack',
     'The epsilon is applied here',
     'IS NOT slack',
     "TestTheRegisteredBarIsUnchanged::"
     "test_the_source_documents_the_epsilon_as_representation_not_slack"),

    # ── PM ruling, decision request #5 (second half): the D3 capture stamp is machine-local state
    # and must not ship in the `COPY . .` image. The TRACKING half is RED-proven by index mutation
    # in the suite's own docstring — this harness cannot express a `git add`.
    ("the capture stamp is un-ignored, so the image ships one machine's study state", _GITIGNORE,
     'quant_sports_intel_models/football/nfl/fantasy/artifacts/nf_inj2b_baseline/'
     'nf_inj2c_capture.json\n',
     '',
     'nf_inj2b_baseline/nf_inj2c_capture.json',
     "TestTheCaptureStampNeverShipsInTheImage::test_gitignore_names_the_capture_stamp"),

    ("the report stops embedding the stamp, so untracking WOULD lose the provenance", _BASE,
     '"capture": stamp,',
     '"capture_note": "see the stamp file",',
     '"capture": stamp',
     "TestTheCaptureStampNeverShipsInTheImage::"
     "test_the_reports_carry_the_stamp_so_untracking_loses_no_audit_trail"),

    ("the run stops asserting the capture is intact (the guard that made this a finding)", _BASE,
     '    stamp = assert_capture_intact(con, schema=args.schema)',
     '    stamp = json.loads(_CAPTURE_STAMP.read_text())',
     '= assert_capture_intact(',
     "TestTheCaptureStampNeverShipsInTheImage::"
     "test_the_validation_that_refused_the_stale_stamp_is_still_wired"),

    # ── node 4: the decisive run. Every clause below defends a route the registration FORBIDS.
    ("the primary arm is SELECTED from the scores instead of read from the registration", _DEC,
     "    arm = C.PRIMARY_ARM\n",
     "    cands = [a for a in C.ARMS if a not in C.DEGENERATE_ARMS]\n"
     "    arm = min(cands, key=lambda a: (scored[a]['crps'] or float('inf')))\n",
     "arm = C.PRIMARY_ARM",
     "TestThePrimaryArmIsNotSelected::"
     "test_the_runner_reads_the_registered_arm_and_never_argmins_crps"),

    ("an absent node-3b report is tolerated instead of refused", _DEC,
     '        raise SystemExit(\n            f"node 3b\'s report is not committed at {p}',
     '        return {"arms": {}, "served_incumbent_baseline": {}}  # noqa\n        _unused = (\n'
     '            f"node 3b\'s report is not committed at {p}',
     'raise SystemExit(\n            f"node 3b\'s report is not committed at {p}',
     "TestTheBoardMeasuresAreRead::test_an_absent_node_3b_report_REFUSES_and_names_the_command"),

    ("a FAILED reproduction pin is treated as a null instead of VOID", _DEC,
     '    if not pin.get("reproduces", False):',
     '    if False:',
     'if not pin.get("reproduces", False):',
     "TestTheBoardMeasuresAreRead::test_a_failed_reproduction_pin_is_VOID_not_a_null"),

    ("M2 drops its attribution control", _DEC,
     "    paired = (np.maximum(a - null, 0.0) - np.maximum(i - null, 0.0))[ok]",
     "    paired = (a - i)[ok]",
     "np.maximum(a - null, 0.0)",
     "TestM2::test_violations_the_control_also_produces_are_subtracted"),

    ("M6 averages per-fold RATES instead of pooling over ROWS", _DEC,
     "            covered += float(rate) * int(k)\n            n += int(k)",
     "            covered += float(rate)\n            n += 1",
     "covered += float(rate) * int(k)",
     "TestM6::test_coverage_is_pooled_over_ROWS_not_averaged_over_folds"),

    ("M6 uses a FLAT nominal point-floor instead of the power-derived one", _DEC,
     "        floor = round(float(CPF.power_floor(n, nominal=NOMINAL_COVERAGE)), 4)",
     "        floor = NOMINAL_COVERAGE",
     "CPF.power_floor(n, nominal=NOMINAL_COVERAGE)",
     "TestM6::test_the_floor_is_DERIVED_from_n_and_is_below_nominal"),

    ("an UNEVALUABLE measure is scored as a pass", _DEC,
     '    if unevaluable:\n        state = "UNEVALUABLE"\n    elif regressed:',
     '    if False:\n        state = "UNEVALUABLE"\n    elif regressed:',
     'if unevaluable:\n        state = "UNEVALUABLE"',
     "TestDominance::test_an_UNEVALUABLE_measure_is_NEVER_a_pass"),

    ("a REGRESSION is downgraded to a deflation refusal instead of a NULL", _DEC,
     '    elif dominance["state"] == "REGRESSES":\n        state = "NULL"',
     '    elif dominance["state"] == "REGRESSES":\n        state = "DEFLATION_REFUSED"',
     'dominance["state"] == "REGRESSES":\n        state = "NULL"',
     "TestTheVerdict::test_a_regression_is_a_NULL_even_when_every_gate_passes"),

    ("an UNCOMPUTABLE gate is scored as a FAILURE instead of UNDEFINED", _DEC,
     '        "dsr": (None if binding_dsr is None else bool(binding_dsr >= dsr_min)),',
     '        "dsr": bool(binding_dsr is not None and binding_dsr >= dsr_min),',
     '(None if binding_dsr is None else bool(binding_dsr >= dsr_min))',
     "TestTheVerdict::test_an_UNCOMPUTABLE_gate_is_UNDEFINED_never_FAILED"),

    ("the fold-consistency clause reverts to the LEGACY (looser) requirement", _DEC,
     "    required = (None if clause.wins_required is None else int(clause.wins_required))",
     "    required = (None if clause.legacy_wins_required is None\n"
     "                else int(clause.legacy_wins_required))",
     "int(clause.wins_required)",
     "TestTheVerdict::test_the_fold_consistency_clause_is_the_CALIBRATED_one"),

    ("a THIRD deflation field is constructed", _DEC,
     "DIAGNOSTIC_FIELD = RB.NF_INJ2B_FIELD",
     "DIAGNOSTIC_FIELD = RB.FieldSpec(arms=tuple(B.ARMS), degenerates=tuple(B.DEGENERATE_ARMS),\n"
     "                                reference=tuple(B.REFERENCE_ARMS), declared_field_size=10,\n"
     '                                label="a third field")',
     "DIAGNOSTIC_FIELD = RB.NF_INJ2B_FIELD",
     "TestTheFields::test_there_is_no_THIRD_field"),

    ("the calendar-bound fold trigger is published even when SR <= SR0", _DEC,
     '        "fold_trigger_publishable": reachable,\n        "why": ("a fold trigger only means',
     '        "fold_trigger_publishable": True,\n        "why": ("a fold trigger only means',
     '"fold_trigger_publishable": reachable',
     "TestTheLockstepLever::test_the_trigger_is_WITHHELD_when_SR_does_not_exceed_SR0"),

    ("the registration stops proving `V` has the two members it reasons about", _REG2C,
     "    if len(v_members) != 2:",
     "    if False:",
     "if len(v_members) != 2:",
     "TestTheRegistration::test_assert_coherent_REFUSES_a_field_whose_V_is_not_two_members"),

    ("the registration's coherence check stops running at import", _REG2C,
     "\n\nassert_coherent()\n",
     "\n\n_SKIPPED = assert_coherent\n",
     "\nassert_coherent()\n",
     "TestTheRegistration::test_assert_coherent_runs_at_import"),

    # ── PRE-REGISTRATION AMENDMENT 1 (PM ruling #6 D1) — the control's null leg ────────────────
    ("the control's binding verdict charges an INVARIANT-blocked arm to the family's sensitivity",
     _DEC,
     "    f1 = not metric_survivors",
     "    f1 = not injected_survivors",
     "f1 = not metric_survivors",
     "TestTheControlsBindingSubstanceIsTheInjectedLeg::test_f1_reads_metric_survivors_not_survivors"),

    ("an UNDETECTED planted effect stops failing the control (the re-scope loses its teeth)", _DEC,
     '    failures = (["F1"] if f1 else [])',
     '    failures = ([] if f1 else [])',
     '(["F1"] if f1 else [])',
     "TestTheControlsBindingSubstanceIsTheInjectedLeg::"
     "test_f1_an_undetected_planted_effect_fails_however_good_the_badge_is"),

    ("a DEGENERATE surviving the INJECTED leg stops failing the control", _DEC,
     "    f2 = sorted(a for a in injected_survivors if a in degen)",
     "    f2 = []",
     "f2 = sorted(a for a in injected_survivors if a in degen)",
     "TestTheControlsBindingSubstanceIsTheInjectedLeg::"
     "test_f2_a_degenerate_surviving_the_injected_leg_fails"),

    ("amendment 1 SS3's degenerate carve-out is dropped, making the declaration a blanket waiver",
     _DEC,
     "    f3 = sorted(a for a in null_survivors if a in degen)",
     "    f3 = []",
     "f3 = sorted(a for a in null_survivors if a in degen)",
     "TestTheControlsBindingSubstanceIsTheInjectedLeg::"
     "test_f3_a_degenerate_surviving_the_null_leg_is_carved_out_of_the_declaration"),

    ("a control that never ran is scored as a pass (NF1.7 (a))", _DEC,
     '    if not control.get("null_control_checked"):',
     "    if False:",
     'if not control.get("null_control_checked"):',
     "TestTheControlsBindingSubstanceIsTheInjectedLeg::"
     "test_f4_a_control_that_did_not_run_is_never_a_pass"),

    ("a FAILING control stops blocking the disposition (the badge becomes the whole control)",
     _DEC,
     '    control_failed = str(control_binding.get("state")) in ("FAILS", "UNEVALUABLE")',
     "    control_failed = False",
     'str(control_binding.get("state")) in ("FAILS", "UNEVALUABLE")',
     "TestAControlFailureBlocksTheDisposition::"
     "test_a_failing_control_refuses_an_otherwise_dominant_run"),

    ("a REGRESSION is reported as a control refusal instead of the NULL PM ruling 3 requires",
     _DEC,
     '    elif dominance["state"] == "REGRESSES":\n        state = "NULL"\n    elif control_failed:',
     '    elif control_failed:\n        state = "CONTROL_REFUSED"\n    elif dominance["state"] == "REGRESSES":',
     '"REGRESSES":\n        state = "NULL"\n    elif control_failed:',
     "TestAControlFailureBlocksTheDisposition::"
     "test_a_regression_still_reads_null_ahead_of_the_control"),

    ("the injector is handed NF-INJ2b's field again, so this story's degenerates may be treated",
     _DEC,
     "    inject = RB.make_injector(payload, field=BINDING_FIELD)",
     "    inject = RB.make_injector(payload)",
     "RB.make_injector(payload, field=BINDING_FIELD)",
     "TestTheInjectorCannotTreatThisStorysDegenerates::"
     "test_the_decisive_runner_hands_the_injector_its_own_field"),

    ("`make_injector` reverts to a HARDCODED field, so the caller's declaration is ignored", _RB,
     "    f = field or NF_INJ2B_FIELD\n    treated = [a for a in f.arms\n"
     "               if a not in f.degenerates and a not in f.reference]",
     "    treated = [a for a in B.ARMS\n"
     "               if a not in B.DEGENERATE_ARMS and a not in B.REFERENCE_ARMS]",
     # ⛔ NOT `f = field or NF_INJ2B_FIELD` — three SIBLING functions share that idiom, so it
     # survives this break and the harness correctly reports the break malformed (#815).
     "treated = [a for a in f.arms",
     "TestTheInjectorCannotTreatThisStorysDegenerates::"
     "test_a_field_with_different_degenerates_treats_different_arms"),

    ("the declaration is applied to a badge with a DEGENERATE among the survivors", _DEC,
     "    declaration_applies = (str(rep.get(\"verdict\")) == \"VACUOUS\"\n"
     "                           and not degenerate_null_survivors)",
     '    declaration_applies = str(rep.get("verdict")) == "VACUOUS"',
     "and not degenerate_null_survivors)",
     "TestTheDeclarationIsScopedAndRecordedRatherThanChosen::"
     "test_the_declaration_applies_only_when_no_degenerate_survived"),

    ("the record reverts to refusing to choose, after the PM has ruled", _DEC,
     "⚠️ BOTH READINGS STAY ON ",
     "⚠️ this record chooses NEITHER of ",
     "BOTH READINGS STAY ON",
     "TestAVacuousBadgeIsRecordedNotReinterpreted::"
     "test_a_VACUOUS_verdict_states_both_readings_and_names_the_survivors"),

    ("the reading stops citing the amendment that authorises it", _DEC,
     '"pre-registration AMENDMENT 1 (PM ruling #6 D1) declares (b) — the badge is "',
     '"this session declares (b) — the badge is "',
     "pre-registration AMENDMENT 1 (PM ruling #6 D1) declares",
     "TestAVacuousBadgeIsRecordedNotReinterpreted::"
     "test_which_reading_binds_is_traceable_to_the_amendment_not_to_this_call_site"),

    ("the pre-registration stops pointing at its own amendment", _PREREG,
     "> **AMENDMENT LOG", "> **Amendment history",
     "AMENDMENT LOG",
     "TestTheAmendmentDocumentSaysWhatTheCodeDoes::"
     "test_the_amendment_exists_and_the_prereg_points_at_it"),
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
    "betting_ml/tests/test_nf_inj2c_cache_guard.py",
    "betting_ml/tests/test_nf_inj2c_published_resolution_pin.py",
    "betting_ml/tests/test_nf_inj2c_decisive.py",
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
