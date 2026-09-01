"""RED proof for the MLB-TV2-2 guards — a guard that cannot FAIL is not a guard.

Each case applies ONE deliberate mutation and asserts the named guard goes RED. Three disciplines
this repo has already paid for, all enforced here:

  * the anchor must be UNIQUE in the file — two functions with byte-identical tails make a
    single-occurrence replace land on the WRONG symbol and report a FALSE "the guard is vacuous",
    which is the dangerous direction because it invites weakening a correct guard (E11.24 #815).
  * the mutation must be proven to have LANDED on disk (#682) — a break that silently no-ops
    reports SUCCESS.
  * the retired token must be proven GONE, not merely the file changed (#815) — a mutation that
    writes but does not move the asserted predicate comes back green.

Run:  uv run python betting_ml/tests/mlb_tv2_2_red_proof.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "betting_ml" / "scripts" / "mlb_tv2_2_mixture_head.py"
TEST = ROOT / "betting_ml" / "tests" / "test_mlb_tv2_2_mixture_head.py"
BACKUP = SRC.with_suffix(".py.redproof.bak")

#: (case, target, old, new, guard, gone) — `gone` is a token that must NOT survive the mutation.
CASES = [
    ("C7 silently re-adds PBO as a per-arm veto", SRC,
     'v["C7_deflation"] = bool(defl["dsr_pass"]) if defl else False',
     'v["C7_deflation"] = bool(defl["pbo_pass"] and defl["dsr_pass"]) if defl else False',
     "test_c7_carries_dsr_only_and_never_pbo_as_a_per_arm_veto", None),

    ("the per-fold series reverts to the Brier score", SRC,
     '    cf = np.asarray(rows_foil["crps"], float)\n    ca = np.asarray(rows_arm["crps"], float)',
     '    cf = brier_rows(rows_foil)\n    ca = brier_rows(rows_arm)',
     "test_the_per_fold_series_is_crps_and_the_deflation_reads_it", None),

    ("C8 reverts to the low-resolution per-fold signed-rank", SRC,
     '        d = boot[FOIL_ARM]["p_over_stated"] - boot[a]["p_over_stated"]   # the MOVEMENT, paired\n'
     '        pvals.append(float((np.sum(d <= 0) + 1) / (len(d) + 1)))         # one-sided, +1 correction',
     '        pvals.append(float(wilcoxon(fold_series(rows[FOIL_ARM], rows[a], block),\n'
     '                                    alternative="greater").pvalue))',
     "test_c8_corrects_the_statistic_that_carries_the_claim", None),

    ("the C10 tie band goes back to a hardcoded constant", SRC,
     "        tie_band = float(np.sqrt(0.25 / max(len(y), 1)))",
     "        tie_band = 1e-6",
     "test_c10_tie_band_is_derived_from_n_and_not_a_hardcoded_constant", None),

    ("V quietly admits the degenerates", SRC,
     "V_ARMS = TRIAL_ARMS                                          # §5.3",
     "V_ARMS = TRIAL_ARMS + DEGENERATE_ARMS                        # §5.3",
     "test_v_excludes_the_reference_the_foil_and_the_degenerates", None),

    ("the served-ness lag check is removed", SRC,
     "    if lag > MAX_SERVED_MEDIAN_LAG_DAYS:",
     "    if False:",
     "test_pull_refuses_a_population_whose_insertion_lag_says_backtest", None),

    ("the collapse detector's min-weight condition is deleted", SRC,
     '        if float(self.w.min()) < COLLAPSE_MIN_WEIGHT:\n'
     '            why.append(f"weight {self.w.min():.4f} < {COLLAPSE_MIN_WEIGHT}")',
     '        if False:\n            why.append("never")',
     "test_the_collapse_detector_fires_on_each_of_its_three_registered_conditions", None),

    ("the initialization collapses onto a common point", SRC,
     "    m = np.quantile(z, 1.0 - qs if mirror else qs)",
     "    m = np.full(K, float(np.median(z)))",
     "test_initialization_is_staggered_so_no_component_starts_at_a_common_point", None),

    ("the shape-matched null is replaced by a Normal-drawn one", SRC,
     "        yy = mu + sigma * z0[rng.integers(0, n, size=n)]",
     "        yy = mu + sigma * rng.standard_normal(n)",
     "test_the_variance_statistic_uses_a_shape_matched_null_and_pit_does_not", None),

    ("classify_null loses the declared field size", SRC,
     "        declared_field_size=DECLARED_FIELD_SIZE)",
     "        declared_field_size=None)",
     "test_classify_null_is_passed_the_declared_field_size_and_the_v_convention", None),

    ("a hard-constraint refusal starts publishing a data re-test trigger", SRC,
     '        out["retest_trigger"] = None',
     '        out["retest_trigger"] = "collect more served games"',
     "test_a_hard_constraint_binds_and_publishes_no_data_retest_trigger", None),

    ("the FRESH slice is allowed to trigger STOP", SRC,
     '    out["fresh_can_trigger_stop"] = False',
     '    out["fresh_can_trigger_stop"] = True',
     "test_the_replication_leg_is_the_stop_gate_and_fresh_cannot_trigger_it", None),

    ("an arm is allowed to move mu off the served value", SRC,
     "    arms = {n: Arm(n, mu, sigma, L, block) for n, L in {**laws, **oracle_laws}.items()}",
     "    arms = {n: Arm(n, mu * 1.01, sigma, L, block) for n, L in {**laws, **oracle_laws}.items()}",
     "test_mu_is_held_at_the_served_value_for_every_arm", None),

    ("the serializer stops recursing into dataclasses", SRC,
     "    if dataclasses.is_dataclass(o) and not isinstance(o, type):\n"
     "        return _strip(dataclasses.asdict(o))",
     "    if False:\n        pass",
     "test_the_serializer_survives_a_nested_dataclass", None),

    ("the pull SQL starts reading a market column", SRC,
     "    s.mu, s.sigma, s.insert_lag_days,",
     "    s.mu, s.sigma, s.insert_lag_days, s.total_line_consensus,",
     "test_the_study_is_market_blind_and_reads_no_odds_column", False),  # ADDITIVE
]


def _restore():
    if BACKUP.exists():
        SRC.write_text(BACKUP.read_text())
        BACKUP.unlink()


def main() -> int:
    # a source-mutating proof's own worst case is being killed mid-mutation (E11.26) —
    # restore any stale backup BEFORE doing anything else.
    _restore()
    original = SRC.read_text()
    BACKUP.write_text(original)
    reds, fails = 0, []
    try:
        for name, target, old, new, guard, gone in CASES:
            text = target.read_text()
            n = text.count(old)
            if n != 1:
                fails.append(f"{name}: ANCHOR NOT UNIQUE ({n} occurrences) — a non-unique anchor "
                             f"lands on the wrong symbol and reports a FALSE vacuity")
                continue
            mutated = text.replace(old, new, 1)
            target.write_text(mutated)
            on_disk = target.read_text()
            if on_disk == original:                       # #682 — the mutation must LAND
                fails.append(f"{name}: mutation did NOT land on disk")
                target.write_text(original)
                continue
            # #815 — the RETIRED code must be GONE, not merely the file changed. Defaulting the
            # token to `old` itself is the correct discipline: a `gone` token that also occurs
            # ELSEWHERE in the file reports a false "the predicate did not move".
            # `gone=False` marks a purely ADDITIVE mutation: it retires nothing, so there is no
            # token that must disappear and the #815 check does not apply. Saying so explicitly is
            # the honest form — silently skipping it would be the vacuity this proof exists to catch.
            retired = old if gone is None else gone
            if retired is not False and retired in on_disk:
                fails.append(f"{name}: mutation landed but {retired!r} SURVIVES — the asserted "
                             f"predicate did not move")
                target.write_text(original)
                continue
            r = subprocess.run([sys.executable, "-m", "pytest", str(TEST), "-k", guard, "-q",
                                "--no-header", "-p", "no:cacheprovider"],
                               capture_output=True, text=True, cwd=ROOT)
            target.write_text(original)
            if r.returncode != 0:
                reds += 1
                print(f"  ✅ RED   {name}\n           -> {guard}")
            else:
                fails.append(f"{name}: guard {guard} stayed GREEN on broken source (VACUOUS)")
                print(f"  ⛔ GREEN {name}\n           -> {guard} IS VACUOUS")
    finally:
        _restore()

    print(f"\nRED proof: {reds}/{len(CASES)} guards went RED on a deliberate break.")
    for f in fails:
        print(f"  ⛔ {f}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
