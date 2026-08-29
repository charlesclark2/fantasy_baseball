"""MLB-TV2-0 — the RED proof: every guard is shown to FAIL on deliberately broken source.

A guard that cannot fail is not a guard (NF1.7 (a) / INC-38). This harness applies each break
IN-PROCESS, and before running anything it asserts THREE things the recorded RED-proof failures
each taught the repo:

  #682  the mutation LANDED ON DISK   — a break that silently no-ops reports a false "vacuous".
  #815  the asserted token is GONE    — a break that writes but does not move the predicate is a
                                        false GREEN, and an `x in src` clause is blind to a rename.
  E11.24 the anchor is UNIQUE         — two byte-identical tails make `replace(old, new, 1)` mutate
                                        the WRONG symbol, and a FALSE vacuity report is the
                                        dangerous direction: it invites weakening a correct guard.

Run:  uv run python betting_ml/tests/mlb_tv2_0_red_proof.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "module": ROOT / "betting_ml" / "scripts" / "mlb_tv2_0_ceiling_diagnosis.py",
    "prereg": ROOT / "ablation_results" / "mlb_tv2_0_prereg.md",
    "fixture": ROOT / "betting_ml" / "tests" / "fixtures" / "mlb_tv2_0_fixture.json",
}
SUITE = ROOT / "betting_ml" / "tests" / "test_mlb_tv2_0_ceiling_diagnosis.py"

#: (label, target, find, replace, the test that MUST go red, the token that must be GONE)
BREAKS = [
    ("market-blind: a real odds read reaches the harness", "module",
     '        "over": (y > arm.mu).astype(float),',
     '        "over": (y > arm.mu).astype(float),\n        "mkt": arm.bovada_devig_over_prob,',
     "test_the_harness_reads_no_market_column_anywhere", None),

    ("market-blind: an odds column enters the pull SQL", "module",
     "s.mu, s.sigma,\n    (r.home_final_score",
     "s.mu, s.sigma, s.total_line_consensus,\n    (r.home_final_score",
     "test_the_sql_reads_only_the_two_market_blind_tables", None),

    ("the scale-mixture oracle stops being inert on a constant true scale", "module",
     "        if K > 1 and min(sides) < 2:",
     "        if False and min(sides) < 2:",
     "test_the_symmetry_gate_closes_on_skew_and_opens_on_a_real_scale_mixture",
     "if K > 1 and min(sides) < 2:"),

    ("the oracle loses its BIC model selection (always K=1)", "module",
     "        K, w, s2 = self._bic_k(z, k_max)\n",
     "        K, w, s2 = self._bic_k(z, 1)\n",
     "test_the_scale_mixture_oracle_recovers_a_real_per_game_scale_signal", None),

    ("an arm is allowed to move mu", "module",
     '    arms["A1_sigma_level"] = Arm("A1_sigma_level", mu, sigma * c, norm_laws, block)',
     '    arms["A1_sigma_level"] = Arm("A1_sigma_level", mu + 0.1, sigma * c, norm_laws, block)',
     "test_every_arm_holds_mu_exactly_at_the_served_value", None),

    ("the PIT randomisation stops being shared across arms (pairing broken)", "module",
     "        stats[a] = arm_stats(y, arms[a], None, u=u_shared)",
     "        stats[a] = arm_stats(y, arms[a], np.random.default_rng(1))",
     "test_the_pit_uniforms_are_shared_across_arms_so_the_comparison_is_paired",
     "arm_stats(y, arms[a], None, u=u_shared)"),

    ("the CRPS grid reverts to the left-Riemann levels", "module",
     "    return (np.arange(CRPS_LEVELS) + 0.5) / CRPS_LEVELS",
     "    return (np.arange(1, CRPS_LEVELS + 1)) / (CRPS_LEVELS + 1.0)",
     "test_the_crps_grid_reproduces_the_normal_closed_form", None),

    ("the continuity correction is dropped from the PIT", "module",
     "    lo, hi = arm.cdf_at(y - 0.5), arm.cdf_at(y + 0.5)",
     "    lo, hi = arm.cdf_at(y), arm.cdf_at(y + 1.0)",
     "test_the_randomized_pit_is_exactly_uniform_under_a_correct_predictive", None),

    ("the empirical law loses its Gaussian tail extension", "module",
     "        if lo.any():\n            out[lo] = self.q_lo + (norm.ppf(p[lo]) - self._n_lo) * self.t_lo",
     "        if lo.any():\n            out[lo] = self.q_lo",
     "test_the_empirical_law_is_a_monotone_invertible_quantile_function", None),

    ("a date is allowed to straddle two blocks", "module",
     "    for day in np.unique(d):\n        m = d == day",
     "    for day in np.unique(d)[:0]:\n        m = d == day",
     "test_date_blocks_never_split_a_slate_across_two_blocks", None),

    ("the feature lever becomes admissible on the asymmetry statistic", "module",
     'LEVER_STATS = {"shape": (CRPS_STAT, ASYM_STAT), "feature": (CRPS_STAT,),',
     'LEVER_STATS = {"shape": (CRPS_STAT, ASYM_STAT), "feature": (CRPS_STAT, ASYM_STAT),',
     "test_the_feature_lever_is_inadmissible_on_the_asymmetry_statistic", None),

    ("the fidelity statistic is promoted to a lever statistic", "module",
     'LEVER_STATS = {"shape": (CRPS_STAT, ASYM_STAT), "feature": (CRPS_STAT,),',
     'LEVER_STATS = {"shape": (CRPS_STAT, ASYM_STAT, FIDELITY_STAT), "feature": (CRPS_STAT,),',
     "test_the_fidelity_statistic_is_not_a_lever_statistic", None),

    ("the asymmetry channel loses its gap-materiality precondition", "module",
     '    in_play = bool(gap_material and mv["material"] and toward_zero)',
     '    in_play = bool(mv["material"] and toward_zero)',
     "test_the_asymmetry_channel_requires_the_incumbent_gap_to_be_materially_non_zero",
     'bool(gap_material and mv["material"] and toward_zero)'),

    ("the decomposition stops being hierarchical (feature scored vs A1, not B2)", "module",
     '             "feature": ("C1_combined", "B2_shape_empirical"),',
     '             "feature": ("C1_combined", "A1_sigma_level"),',
     "test_the_decomposition_is_hierarchical_and_conservative_toward_the_expensive_lever",
     '"feature": ("C1_combined", "B2_shape_empirical"),'),

    ("a lever counts without a paired CI that excludes zero", "module",
     '        r["in_play"] = bool(r["material"] and r["point"] > 0)',
     '        r["in_play"] = bool(r["point"] > 0)',
     "test_a_lever_counts_only_on_a_paired_ci_that_excludes_zero",
     'bool(r["material"] and r["point"] > 0)'),

    ("the non-defect precondition is removed", "module",
     '    if not joint_material and not any_failure:\n        outcome = "NO_MEASURABLE_DEFECT"',
     '    if False:\n        outcome = "NO_DEFECT_AT_ALL"',
     "test_the_rule_refuses_to_run_on_a_non_defect", 'outcome = "NO_MEASURABLE_DEFECT"'),

    ("INDETERMINATE is routed to a lever the outcomes did not license", "module",
     '    "INDETERMINATE": "routes as IRREDUCIBLE — no lever demonstrated majority closure",',
     '    "INDETERMINATE": "TV2-1 funded first anyway",',
     "test_every_route_is_registered_and_the_irreducible_route_unholds_the_calibrator", None),

    ("std_pred enters the decision rule", "module",
     "    s_share, f_share = levers[\"shape\"][\"share\"], levers[\"feature\"][\"share\"]",
     "    std_pred_hack = 1.0\n    s_share, f_share = levers[\"shape\"][\"share\"], levers[\"feature\"][\"share\"]",
     "test_std_pred_is_reported_under_both_readings_and_never_enters_the_rule", None),

    ("an INACTIVE lever null publishes a fold/season re-test trigger", "module",
     '        inert = name == "feature" and notes.get("A3_all_blocks_single_component")',
     '        inert = False',
     "test_an_inactive_lever_null_publishes_no_retest_trigger", None),

    ("the row-blind matched control stops being row-blind", "module",
     "    z_perm = z[rng.permutation(len(y))]",
     "    z_perm = z.copy()",
     "test_the_row_blind_control_shares_the_oracle_machinery", "rng.permutation"),

    ("the reproduction pin drifts", "fixture",
     '"closed_shape": 0.993008128624567',
     '"closed_shape": 0.993108624567',
     "test_the_whole_battery_reproduces_to_1e_9_on_the_committed_fixture", None),

    ("the prereg loses an arm the code scores", "prereg",
     "`A3_sigma_clairvoyant` → `A3_sigma_scalemix`",
     "`A3_sigma_clairvoyant` → `A3_REMOVED_FROM_THE_PREREG`",
     "test_prereg_document_matches_the_registered_battery", None),

    ("a control bar is changed in code without the prereg", "module",
     "CONTROL_ROUTE_BAR = 0.80",
     "CONTROL_ROUTE_BAR = 0.55",
     "test_the_control_bars_are_design_quantities_fixed_in_the_prereg", None),
]


def _restore():
    for name, path in TARGETS.items():
        bak = path.with_suffix(path.suffix + ".redbak")
        if bak.exists():
            shutil.copy2(bak, path)
            bak.unlink()


def main() -> int:
    # ⚠️ A source-mutating harness's own worst case is being killed MID-MUTATION, so stale backups
    # are restored BEFORE anything else runs (E11.26).
    _restore()
    originals = {n: p.read_text() for n, p in TARGETS.items()}
    red, failures = 0, []
    for label, target, find, repl, test, gone in BREAKS:
        path, src = TARGETS[target], originals[target]
        if src.count(find) != 1:
            failures.append(f"⛔ ANCHOR NOT UNIQUE ({src.count(find)}×) — {label}")
            continue
        try:
            shutil.copy2(path, path.with_suffix(path.suffix + ".redbak"))
            path.write_text(src.replace(find, repl, 1))
            on_disk = path.read_text()
            if on_disk == src:
                failures.append(f"⛔ MUTATION DID NOT LAND — {label}")
                continue
            if gone is not None and gone in on_disk:
                failures.append(f"⛔ ASSERTED TOKEN STILL PRESENT — {label}")
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", f"{SUITE}::{test}", "-q", "--no-header", "-p",
                 "no:cacheprovider"],
                cwd=ROOT, capture_output=True, text=True)
            if proc.returncode != 0:
                red += 1
                print(f"  RED  {test}\n       ← {label}")
            else:
                failures.append(f"⛔ STAYED GREEN — {test} ← {label}")
        finally:
            _restore()

    print(f"\n{red}/{len(BREAKS)} breaks went RED")
    for f in failures:
        print(" ", f)
    for n, p in TARGETS.items():
        assert p.read_text() == originals[n], f"{n} was not restored!"
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
