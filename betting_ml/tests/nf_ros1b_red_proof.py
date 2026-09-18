"""nf_ros1b_red_proof.py — prove every NF-ROS1b guard can actually FAIL (⛔ NOT a pytest module).

Reuses the parent's RED-proof machinery (`nf_ros1_red_proof.py`: baseline-pass, resolve-every-node,
NOT-SELECTED ⇒ only pytest exit 1 is a red, unique anchors, token-gone, stale-backup restore) by
pointing its module globals at this story's tests, sources and breaks — one owner of the harness.

    uv run python betting_ml/tests/nf_ros1b_red_proof.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nf_ros1_red_proof as P  # noqa: E402

ROOT = P.ROOT
FANT = ROOT / "quant_sports_intel_models/football/nfl/fantasy"
RI = FANT / "ros_interval.py"
RUN = FANT / "run_nf_ros1.py"
B = FANT / "run_nf_ros1b.py"
Break = P.Break

BREAKS: tuple[Break, ...] = (
    Break("the atom is ignored (every level reads the ratio)", RI,
          "    q = np.where((tau <= pi[:, None]) | (pred[:, None] <= 0), 0.0, q)",
          "    q = np.where(pred[:, None] <= 0, 0.0, q)",
          gone="(tau <= pi[:, None]) |",
          tests=("test_hurdle_positive_control_reads_flat",
                 "test_mixture_is_monotone_and_the_atom_levels_are_exactly_zero")),
    Break("the conditional level is not renormalized by (1 − π)", RI,
          "    u = (tau - pi[:, None]) / denom",
          "    u = tau + 0.0 * pi[:, None]",
          gone="(tau - pi[:, None]) / denom",
          tests=("test_hurdle_positive_control_reads_flat",)),
    Break("the spread is additive, not scaled by the projection", RI,
          "    q = pred[:, None] * eps", "    q = pred[:, None] + eps",
          gone="pred[:, None] * eps",
          tests=("test_scale_equivariance", "test_a_zero_point_is_a_point_mass_at_zero")),
    Break("the ratio table stores residuals, not ratios", RI,
          "    ratio = np.where(pos_rows, y / np.where(pred > 0, pred, 1.0), np.nan)",
          "    ratio = np.where(pos_rows, y - pred, np.nan)",
          gone="y / np.where(pred > 0, pred, 1.0)",
          tests=("test_hurdle_positive_control_reads_flat",)),
    Break("zero-point rows are counted as needing a ratio", RI,
          "        mp = np.where((pos == P) & (pred > 0))[0]",
          "        mp = np.where(pos == P)[0]",
          gone="mp = np.where((pos == P) & (pred > 0))[0]",
          tests=("test_ratio_fallback_is_counted_only_where_a_ratio_is_needed",)),
    Break("the foil's features read the REAL miss_streak", RI,
          '        "miss_streak": df[f"{prefix}miss_streak"].to_numpy(dtype=float),',
          '        "miss_streak": df["miss_streak"].to_numpy(dtype=float),',
          gone='df[f"{prefix}miss_streak"]',
          tests=("test_pi_features_are_the_registered_set_in_order",)),
    Break("the hurdle event becomes y < 0", RI,
          '            zt = (train[f"y_{preset}"].to_numpy(dtype=float) <= 0).astype(int)',
          '            zt = (train[f"y_{preset}"].to_numpy(dtype=float) < 0).astype(int)',
          gone="dtype=float) <= 0).astype(int)",
          tests=("test_the_hurdle_event_is_y_at_or_below_zero",)),
    Break("the logistic regularization drifts", RI,
          "LOGIT_C = 1.0\n", "LOGIT_C = 0.5\n", gone="LOGIT_C = 1.0\n",
          tests=("test_the_registered_constants",)),
    Break("miss_streak never resets when he plays", RI,
          "            if n[i] > pn[i]:\n                s = 0.0\n",
          "            if n[i] > pn[i]:\n                pass\n",
          gone="                s = 0.0\n            elif",
          tests=("test_miss_streak_counts_missed_team_games_and_skips_the_bye",)),
    Break("a bye counts as a missed game", RI,
          "            elif t[i] > pt[i]:", "            else:",
          gone="elif t[i] > pt[i]:",
          tests=("test_miss_streak_counts_missed_team_games_and_skips_the_bye",)),
    # the first cut (pn = the NEXT row's n) only stopped resets — it never made a row depend on a
    # later week, so the leak clause rightly stayed green. This break reads the season's last row.
    Break("miss_streak reads the season's last row (future leak)", RI,
          "            if n[i] > pn[i]:\n",
          "            if n[-1] > pn[i]:\n",
          gone="if n[i] > pn[i]:",
          tests=("test_miss_streak_reads_no_week_after_k",)),
    Break("ros_interval grows an IO import", RI,
          "import numpy as np\nimport pandas as pd\n\nfrom quant_sports_intel_models",
          "import numpy as np\nimport pandas as pd\nimport requests  # noqa: F401\n\n"
          "from quant_sports_intel_models",
          gone="import pandas as pd\n\nfrom quant_sports_intel_models",
          tests=("test_ros_interval_never_imports_pipeline_or_does_io",)),
    Break("the foil stops carrying the donor's miss_streak", RUN,
          '        if carry_streak:\n            f.loc[idx, "perm_miss_streak"]',
          '        if False:\n            f.loc[idx, "perm_miss_streak"]',
          gone='if carry_streak:\n            f.loc[idx',
          tests=("test_the_foil_carries_the_donors_streak",)),
    Break("the hook is not inert (a reference is built without an interval)", RUN,
          '    if interval is not None:\n        out["reference"] = {}',
          '    if True:\n        out["reference"] = {}',
          gone='if interval is not None:\n        out["reference"]',
          tests=("test_the_hook_is_inert_when_no_interval_is_passed",)),
    Break("hurdle mode silently keeps the parent residual table", RUN,
          "            if interval is None:\n                q, fb = V.apply_residual_table(table, test",
          "            if True:\n                q, fb = V.apply_residual_table(table, test",
          gone="if interval is None:\n                q, fb = V.apply_residual_table(table, test",
          tests=("test_the_hurdle_replaces_every_predictors_interval_but_not_its_point",)),
    Break("the reference is built with the hurdle table", RUN,
          "                ref_q, _ = V.apply_residual_table(_loso_residual_table(train, arm, preset),",
          "                ref_q, _ = V.apply_residual_table(_loso_residual_table(train, arm, preset,"
          " interval=interval),",
          gone="_loso_residual_table(train, arm, preset),",
          tests=("test_the_hurdle_replaces_every_predictors_interval_but_not_its_point",)),
    Break("the foil is handed the REAL π", RUN,
          'ptable,\n            prefix="perm_")', "ptable)",
          gone='ptable,\n            prefix="perm_")',
          tests=("test_every_predictor_reads_its_own_hurdle_probability",)),
    Break("the successor writes over the parent's record", B,
          'STEM = "nf_ros1b_walkforward"', 'STEM = "nf_ros1_walkforward"',
          gone='STEM = "nf_ros1b_walkforward"',
          tests=("test_the_successor_never_writes_the_parents_record",)),
    Break("the reference label is dropped from the report", B,
          "`{RI.REFERENCE_KEY}` — **{RI.REFERENCE_LABEL}**", "`{RI.REFERENCE_KEY}`",
          gone="**{RI.REFERENCE_LABEL}**",
          tests=("test_the_full_evaluate_runs_and_writes_a_labelled_report",)),
    Break("the interval leaks into the compared result", B,
          "            result[\"hurdle\"] = hurdle_extras(result, interval)\n    return result\n",
          "            result[\"hurdle\"] = hurdle_extras(result, interval)\n"
          "    result[\"interval\"] = interval_name\n    return result\n",
          gone="hurdle_extras(result, interval)\n    return result\n",
          tests=("test_the_full_evaluate_runs_and_writes_a_labelled_report",)),
    Break("the reproduction comparison ignores non-numeric mismatches", B,
          "    return (0.0, []) if a == b else (0.0, [f\"{path}: {a!r} != {b!r}\"])",
          "    return (0.0, [])",
          gone="if a == b else",
          tests=("test_max_abs_diff_sees_numbers_structure_and_ignores_meta",)),
    Break("the companion averages over the whole position, not the top tercile", RI,
          "        mp, rz = float(pi[top].mean()), float((y[top] <= 0).mean())",
          "        mp, rz = float(pi[m].mean()), float((y[m] <= 0).mean())",
          gone="float(pi[top].mean())",
          tests=("test_the_companion_diagnostic_reads_mean_pi_on_the_top_tercile",)),
    Break("the companion loses its label in the report", B,
          '    L += ["", f"### {comp[\'label\']}", "",',
          '    L += ["", "### companion", "",',
          gone="{comp[\'label\']}",
          tests=("test_the_full_evaluate_runs_and_writes_a_labelled_report",)),
    Break("the RB-rookie read loosens the bar", B,
          "    if dev <= V.PIT_MAX_DECILE_DEV:\n        return \"STRATUM_CHECK_PASSES\"",
          "    if dev <= 0.06:\n        return \"STRATUM_CHECK_PASSES\"",
          gone="if dev <= V.PIT_MAX_DECILE_DEV:",
          tests=("test_the_rb_rookie_decision_rule_has_both_branches",)),
    Break("the RB-rookie read includes veterans", B,
          '("rb_rookie", (pos == "RB") & rk, RB_ROOKIE_SEED)',
          '("rb_rookie", (pos == "RB"), RB_ROOKIE_SEED)',
          gone='("rb_rookie", (pos == "RB") & rk,',
          tests=("test_the_rb_rookie_read_uses_only_rb_rookies_and_the_registered_bar",)),
    # ── amendment 5: the descriptive spread the PM's disposition is read from ──
    Break("the two dependence readings are swapped, overstating the evidence", B,
          '        "decile_z_fully_clustered": z(n_ps),',
          '        "decile_z_fully_clustered": z(len(u)),',
          gone="z(n_ps),",
          tests=("test_the_clustered_reading_is_the_conservative_one",)),
    Break("a first run claims it reproduced a prior that does not exist", B,
          "    if not jp.exists():\n        return None",
          '    if not jp.exists():\n        return {"identical": True}',
          gone="    if not jp.exists():\n        return None",
          tests=("test_a_rerun_after_the_result_is_known_must_prove_it_moved_nothing",)),
    Break("an unreadable prior artifact reads as a clean reproduction", B,
          '        return {"prior_read_error": str(exc), "identical": None}',
          '        return {"prior_read_error": str(exc), "identical": True}',
          gone='"identical": None}',
          tests=("test_a_rerun_after_the_result_is_known_must_prove_it_moved_nothing",)),
    Break("the spread starts declaring its own verdict", B,
          '        "player_seasons_above_half": int((means > 0.5).sum()),',
          '        "verdict": "concentrated" if top_rows < 300 else "broad",',
          gone='"player_seasons_above_half"',
          tests=("test_the_spread_never_returns_a_verdict",)),
    Break("a WRONG join reads as CORRECT", B,
          '        return "CORRECT" if rid == auth else "WRONG"',
          '        return "CORRECT"',
          gone='if rid == auth else "WRONG"',
          tests=("test_a_wrong_join_is_never_correct",)),
    Break("the pick key is trusted without the position check", B,
          'bool(len(hit) == 1 and LS.normalize_position(\n'
          '                           hit["position"].iloc[0]) == LS.normalize_position(r["position"])),',
          "bool(len(hit) == 1),",
          gone='hit["position"].iloc[0]) == LS.normalize_position',
          tests=("test_the_pick_key_is_refused_when_a_position_disagrees",)),
)


def _batched_collects_one(nodes):
    """One collect-only call for every node (the parent checks one node per subprocess); the
    same rule — each named node resolves to exactly one collected test."""
    r = P._pytest(["--collect-only", *[f"{P.TESTS}::{n}" for n in nodes]])
    got = [ln.split("::", 1)[1] for ln in r.stdout.splitlines() if "::" in ln]
    return {n: got.count(n) == 1 for n in nodes} if r.returncode == 0 else {n: False for n in nodes}


PUB = FANT / "run_nf_ros1_publish.py"
CON = ROOT / "app/backend/models/nfl_ros.py"
FRESH = ROOT / "betting_ml/monitoring/nfl_ros_freshness.py"
JOB = ROOT / "pipeline/jobs/sports_nfl_weekly_serving_job.py"

#: node 4 — the served artifact's guards (`test_nf_ros1b_node4.py`).
NODE4_BREAKS: tuple[Break, ...] = (
    Break("an uncertified position is served numbers", PUB,
          '        elif r["pos"] not in certified_positions or not certified_week:',
          '        elif not certified_week:',
          gone='r["pos"] not in certified_positions or not certified_week',
          tests=("test_the_build_serves_certified_rows_and_states_every_absence",)),
    # ── PM disposition (ii), 2026-09-18: the rookie stratum is a stated absence ──
    Break("a rookie at a certified position is served a value again", PUB,
          '        elif bool(r.get("rookie")):',
          '        elif False:',
          gone='elif bool(r.get("rookie")):',
          tests=("test_a_rookie_at_a_certified_position_is_an_absence_carrying_no_value",
                 "test_the_manifest_states_the_stratum_carve_out")),
    Break("the rookie reason is keyed on the id shape instead of the flag", PUB,
          '        elif bool(r.get("rookie")):',
          '        elif not GSIS_RE.fullmatch(pid):',
          gone='elif bool(r.get("rookie")):',
          tests=("test_the_rookie_absence_is_keyed_on_the_flag_not_on_the_id_shape",)),
    Break("join_unresolved goes back to reading the served label, hiding a rookie's broken join",
          PUB,
          '        "join_unresolved_names": sorted(join_missing_names),',
          '        "join_unresolved_names": sorted(x["name"] for x in players\n'
          '                                        if x["absence"] == "join_unresolved"),',
          gone="sorted(join_missing_names)",
          tests=("test_the_build_serves_certified_rows_and_states_every_absence",)),
    Break("the manifest drops the stratum qualifier", PUB,
          '        "rookie_stratum_note": (C.ROOKIE_STRATUM_NOTE if certified_positions and certified_week',
          '        "rookie_stratum_note": (None if certified_positions and certified_week',
          gone="C.ROOKIE_STRATUM_NOTE if certified_positions",
          tests=("test_the_manifest_states_the_stratum_carve_out",)),
    Break("the stratum note falls back to a generic hedge", CON,
          '    "A position is certified here for its NON-ROOKIE players. Rookie rows carry the absence "',
          '    "A position is certified here for its NON-ROOKIE players. Rookies are uncertain, so "',
          gone="NON-ROOKIE players. Rookie rows carry the absence",
          tests=("test_the_rookie_stratum_note_says_what_was_measured",)),
    Break("an unevaluated board term is no longer stripped", RUN,
          "    if allowed_keys is not None:\n        # NF-ROS1b §4",
          "    if False:\n        # NF-ROS1b §4",
          gone="if allowed_keys is not None:\n        # NF-ROS1b §4",
          tests=("test_an_unevaluated_board_term_is_stripped_before_scoring",)),
    Break("a WRONG identity join no longer stops the build", PUB,
          '            if outcome == "WRONG":', '            if False:',
          gone='if outcome == "WRONG":',
          tests=("test_a_wrong_identity_join_stops_the_build",)),
    Break("a MISSED join is served as a number", PUB,
          '            if outcome == "MISSED":\n                unresolved.add(pid)',
          '            if outcome == "MISSED":\n                pass',
          gone="unresolved.add(pid)",
          tests=("test_the_build_serves_certified_rows_and_states_every_absence",)),
    Break("the stat-line coherence gate is off", PUB,
          "                if abs(got - point[p][i]) > COHERENCE_TOL * max(1.0, abs(point[p][i])):",
          "                if False:",
          gone="if abs(got - point[p][i]) > COHERENCE_TOL",
          tests=("test_an_incoherent_stat_line_refuses",)),
    Break("the write-gate is skipped on a dry run", PUB,
          "    assert_contract_shaped(built)            # before the dry-run return (NF-INJ3B reading)\n",
          "",
          gone="# before the dry-run return (NF-INJ3B reading)",
          tests=("test_the_write_gate_refuses_a_players_hash_mismatch",)),
    Break("the served-bytes check is off", PUB,
          "        if want != got:", "        if False:",
          gone="if want != got:",
          tests=("test_publish_reads_back_and_compares_the_served_bytes",)),
    Break("a partial week counts as final", PUB,
          '        if states[wk] != "final":\n            break',
          '        if False:\n            break',
          gone='if states[wk] != "final":',
          tests=("test_no_final_week_builds_nothing",
                 "test_final_week_needs_every_game_and_contiguity")),
    Break("the certified set is typed rather than derived", PUB,
          '        if d["ships"]:\n            certified.append(P)',
          '        if True:\n            certified.append(P)',
          gone='if d["ships"]:',
          tests=("test_the_committed_params_certify_what_the_decisive_record_certified",)),
    Break("a rank field joins the contract", CON,
          "    waiverValue: Optional[float] = None\n",
          "    waiverValue: Optional[float] = None\n    globalRank: Optional[int] = None\n",
          gone="    waiverValue: Optional[float] = None\n    waiverAbsence",
          tests=("test_no_field_invites_a_cross_position_comparison",)),
    Break("the deploy-held state pages CRITICAL", FRESH,
          '        return v("ARMED_NOT_FIRING", "WARN",',
          '        return v("ARMED_NOT_FIRING", "CRITICAL",',
          gone='"ARMED_NOT_FIRING", "WARN"',
          tests=("test_the_deploy_held_state_is_warn_not_critical_and_names_the_action",)),
    Break("a just-final week pages BEHIND immediately", FRESH,
          "BEHIND_GRACE_HOURS = 2.0", "BEHIND_GRACE_HOURS = 0.0",
          gone="BEHIND_GRACE_HOURS = 2.0",
          tests=("test_a_just_final_week_is_not_behind_yet",)),
    Break("the flag accepts any truthy value", FRESH,
          '    return (source.get(PUBLISH_ENABLED_FLAG) or "").strip() == "1"',
          '    return bool((source.get(PUBLISH_ENABLED_FLAG) or "").strip())',
          gone='.strip() == "1"',
          tests=("test_the_flag_reads_only_exactly_one",)),
    Break("the publish op no longer checks the flag", JOB,
          "    if not RF.publish_enabled():\n        context.log.warning(\n            \"[nfl ros]",
          "    if False:\n        context.log.warning(\n            \"[nfl ros]",
          gone="if not RF.publish_enabled():\n        context.log.warning(\n            \"[nfl ros]",
          tests=("test_the_publish_op_checks_the_flag_before_doing_anything",)),
    Break("the ROS publish hangs off the build instead of the ingest", JOB,
          "    nfl_ros_value_publish_op(start=landed)",
          "    nfl_ros_value_publish_op(start=nfl_weekly_serving_op(start=nfl_weekly_stats_freshness_op(start=landed)))",
          gone="    nfl_ros_value_publish_op(start=landed)",
          tests=("test_the_publish_is_an_independent_branch_off_the_ingest",)),
)


def _run(tests: str, breaks, paths) -> int:
    P.TESTS = tests
    nodes = sorted({t for b in breaks for t in b.tests})
    resolved = _batched_collects_one(nodes)
    P._collects_one = lambda node: resolved.get(node, False)
    P.PATHS = paths
    P.BREAKS = breaks
    return P.main()


def main() -> int:
    a = _run("betting_ml/tests/test_nf_ros1b_interval.py", BREAKS, (RI, RUN, B))
    print("\n── node 4 ──")
    b = _run("betting_ml/tests/test_nf_ros1b_node4.py", NODE4_BREAKS, (PUB, RUN, CON, FRESH, JOB))
    return a or b


if __name__ == "__main__":
    raise SystemExit(main())
