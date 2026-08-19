"""NF-W7k RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w7k.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17), and this story's
guards defend a governance-adjacent DSR re-read whose dangerous failure is a FALSE STOP — a
decomposition that closes the last remaining QB lever on arithmetic rather than on evidence.

The four disciplines this repo has paid for are enforced, exactly as in NF-W7i's and NF-W7j's
harnesses:

- **the mutation must LAND** (E11.24 #682) — a no-op break reports a FALSE "the guard is vacuous",
  which reads as a real finding and invites weakening a correct guard;
- **the anchor must be UNIQUE** (#885) — a single-occurrence replace can land on the WRONG symbol;
- **the asserted token must be GONE** (#815) — a break that writes without moving the asserted
  predicate is a false GREEN;
- **a stalled leg reports HUNG**, never silently green.

⛔ Not a pytest module: it MUTATES tracked source and restores it in a `finally`.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
_MV = Path(__file__).with_name("fp_mc_variance.py")
_RUNNER = Path(__file__).with_name("run_nf_w7k_mc_variance.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w7k_mc_variance.py"
_TIMEOUT_S = 600


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    tests: tuple[str, ...]
    defect: str


BREAKS: tuple[Break, ...] = (
    # ── the FALSE-STOP surface: the ceiling must not be manufacturable ─────────────────────────
    Break("het_var_clamped_at_zero", _MV,
          "    het_var = between_var - mc_var / n_seeds",
          "    het_var = max(between_var - mc_var / n_seeds, 0.0)",
          ("TestDecompositionCannotManufactureAFalseStop::"
           "test_het_var_is_returned_signed_and_never_clamped",),
          "⭐ THE DANGEROUS DIRECTION — a clamped heterogeneity variance makes the ceiling sd 0, "
          "the ceiling Sharpe infinite, and the story reports a FUND it never earned"),
    Break("mc_var_reads_the_across_fold_spread", _MV,
          "    mc_var = float(np.mean([per_fold_var[f] for f in folds]))",
          "    mc_var = float(np.var([float(np.mean(delta_by_fold[f])) for f in folds], ddof=1))",
          ("TestDecompositionCannotManufactureAFalseStop::"
           "test_mc_variance_is_the_within_fold_across_seed_spread",),
          "imports season-to-season SIGNAL into the term the ceiling removes, so the ceiling "
          "deletes real heterogeneity and overstates the lever"),
    Break("single_fold_decomposition_allowed", _MV,
          "    if len(folds) < 2:",
          "    if len(folds) < 1:",
          ("TestDecompositionCannotManufactureAFalseStop::"
           "test_a_decomposition_refuses_fewer_than_two_folds",),
          "a one-fold decomposition has no across-fold spread at all, so `het_var` is undefined "
          "and every downstream number is meaningless"),
    Break("unbalanced_seed_pool_allowed", _MV,
          "    if counts != {min(counts)} or min(counts) < 2:",
          "    if False:",
          ("TestDecompositionCannotManufactureAFalseStop::"
           "test_a_decomposition_refuses_unbalanced_or_single_seed_input",),
          "an unbalanced pool weights folds by how often they happened to be scored"),
    Break("seed_stride_can_alias_the_availability_stream", _MV,
          "SEED_STRIDE = 7_000_003",
          "SEED_STRIDE = 256",
          ("TestDecompositionCannotManufactureAFalseStop::"
           "test_the_seed_stride_cannot_alias_either_rng_stream",),
          "⭐ two seeds share an RNG stream ⇒ the across-seed spread reads ZERO ⇒ the lever is "
          "closed on a measurement that never happened (the FALSE STOP)"),

    Break("degenerate_ceiling_read_as_a_sharpe_of_zero", _MV,
          "    if winner in degenerate:",
          "    if False:",
          ("TestADegenerateCeilingIsUnboundedNotZero::"
           "test_a_zero_target_sd_reports_unbounded_rather_than_a_sharpe_of_zero",
           "TestADegenerateCeilingIsUnboundedNotZero::"
           "test_the_monotonicity_assertion_tolerates_an_unbounded_rung"),
          "⭐ THE FALSE STOP IN ITS MOST DAMAGING FORM — a zero-dispersion ceiling has an INFINITE "
          "Sharpe, and reading it as 0.0 inverts the most favourable case into the least"),
    Break("unbounded_ceiling_falls_through_to_a_refusal", _MV,
          "    if ceiling_unbounded:",
          "    if False:",
          ("TestADegenerateCeilingIsUnboundedNotZero::"
           "test_an_unbounded_ceiling_cannot_refuse_the_lever",),
          "an unbounded ceiling is evidence the lever is ALIVE; falling through to "
          "MC_LEVER_EXHAUSTED would close it on the opposite of what was measured"),
    Break("bootstrap_drops_unbounded_resamples", _MV,
          '        if g.get("unbounded"):\n            vals.append(1.0)\n        elif g["dsr"] is not None:',
          '        if g["dsr"] is not None:',
          ("TestADegenerateCeilingIsUnboundedNotZero::"
           "test_the_bootstrap_keeps_unbounded_resamples_at_the_supremum",),
          "discards exactly the resamples most favourable to the lever, biasing the CI's UPPER "
          "end — the end the decision reads — downward"),

    # ── the registered identities ─────────────────────────────────────────────────────────────
    Break("rescale_moves_the_mean", _MV,
          "    return mu + (d - mu) * (target_sd / sd)",
          "    return d * (target_sd / sd)",
          ("TestRegisteredIdentities::"
           "test_rescale_preserves_mean_and_every_standardized_shape_moment",
           "TestRegisteredIdentities::"
           "test_projection_at_the_observed_sds_reproduces_nf_w7f_exactly"),
          "scaling the LEVEL as well as the dispersion changes the effect being deflated, so the "
          "projection describes a different arm than the one under test"),
    Break("monotonicity_assertion_removed", _MV,
          "    if any(b < a - 1e-9 for a, b in zip(sharpes, sharpes[1:])):",
          "    if False:",
          ("TestRegisteredIdentities::"
           "test_a_non_monotone_projection_raises_rather_than_reporting_a_finding",),
          "a non-monotone projection is a CODING DEFECT; without the assertion it would be "
          "published as a finding about draws (prereg §3.3)"),
    Break("projection_covers_only_the_winner", _MV,
          "    if set(target_sd) != set(base_deltas):",
          "    if False:",
          ("TestProjectionCoversTheDeclaredField::test_a_partially_projected_field_is_refused",),
          "`SR0` would mix projected and unprojected trials, so the bar and the Sharpe would be "
          "measured on different objects"),

    # ── the decision rule (prereg §3) ─────────────────────────────────────────────────────────
    Break("ceiling_read_at_the_point_estimate_not_the_upper_end", _MV,
          '    hi = float(ceiling_ci["hi"])',
          '    hi = float(ceiling_ci["median"])',
          ("TestTheDecisionRule::test_the_decision_reads_the_UPPER_end_of_the_ceiling_ci",),
          "closes the lever whenever the POINT estimate misses, though the honest question is "
          "whether the lever COULD clear"),
    Break("broken_scaling_law_falls_through_to_a_verdict", _MV,
          '    if not scaling.get("evaluable") or not scaling.get("holds"):',
          "    if False:",
          ("TestTheDecisionRule::"
           "test_a_broken_scaling_law_withholds_a_verdict_rather_than_producing_one",),
          "⭐ a ceiling computed off a 1/D law the data does not obey would close the lever on "
          "arithmetic rather than on evidence — G2 must WITHHOLD, not decide"),
    Break("unevaluable_ceiling_ci_scored_as_a_refusal", _MV,
          '    if not ceiling_ci.get("evaluable"):',
          "    if False:",
          ("TestTheDecisionRule::test_an_unevaluable_ceiling_ci_withholds_a_verdict",),
          "a CI that could not be computed is neither a pass nor a refusal (NF1.7 (a))"),
    Break("exhausted_verdict_publishes_a_data_retest_trigger", _MV,
          '                      f"row-count or sharper-metric lever is UNTESTED here, not refuted.",\n'
          '            "publishes_retest_trigger": False,',
          '                      f"lever is dead. Re-test after +4 more seasons.",\n'
          '            "publishes_retest_trigger": True,',
          ("TestTheDecisionRule::"
           "test_a_ceiling_below_the_bar_closes_the_lever_and_publishes_no_retest_trigger",),
          "the ceiling is what NO draw count can beat, so a data trigger is the actively "
          "misleading direction NF-D18 names"),
    Break("d2_may_be_the_draw_count_that_already_failed", _MV,
          '                     if r.get("kind") == "ladder" and r["dsr"] is not None\n'
          '                     and r["dsr"] >= dsr_min), ladder[-1]))',
          '                     if r["dsr"] is not None\n'
          '                     and r["dsr"] >= dsr_min), ladder[-1]))',
          ("TestTheDecisionRule::test_d2_is_never_the_draw_count_that_already_failed",),
          "reading the identity/reconstruction rows as ladder rungs could 'fund' a re-run at "
          "exactly the 4,000 draws that already failed"),
    Break("scaling_check_scores_an_unevaluable_ratio_as_holding", _MV,
          "    if mc_var_primary <= 0.0:",
          "    if False:",
          ("TestScalingLawIsMeasuredNotAssumed::"
           "test_a_zero_primary_variance_is_unevaluable_and_never_scored_as_holding",),
          "a ratio that could not be computed must never be scored as a pass (NF1.7 (a))"),

    # ── the runner's own clauses ──────────────────────────────────────────────────────────────
    Break("reproduction_pin_tolerance_opened", _RUNNER,
          '        "reproduces": bool(flat) and max(flat) <= MV._REPRO_TOL,',
          '        "reproduces": True,',
          ("TestEndToEndVerdictLayer::test_a_drifted_base_seed_fails_the_reproduction_pin",),
          "without G0 the decomposition could describe a re-derivation rather than the object "
          "NF-W7f actually scored"),
    Break("dead_seed_check_removed", _RUNNER,
          "                if float(np.std(np.asarray(vals, dtype=float), ddof=1)) <= 0.0:",
          "                if False:",
          ("TestEndToEndVerdictLayer::"
           "test_a_dead_seed_is_caught_by_G1_rather_than_reported_as_zero_mc_error",),
          "⭐ a seed that never reaches the draws makes σ²_MC read 0 and the ceiling equal the "
          "observed gate — the lever gets closed on a measurement that never happened"),
    Break("smoke_exemption_inverted_so_a_REAL_run_skips_the_raise", _RUNNER,
          '    if not out.get("smoke"):',
          '    if out.get("smoke"):',
          ("TestEndToEndVerdictLayer::test_a_drifted_base_seed_fails_the_reproduction_pin",
           "TestEndToEndVerdictLayer::"
           "test_a_dead_seed_is_caught_by_G1_rather_than_reported_as_zero_mc_error"),
          "⭐ THE DANGEROUS HALF of the path-proof exemption — inverted, a REAL run records a "
          "failed G0/G1 and publishes a decision anyway, while only the smoke ever refuses"),
    Break("story_certifies_qb", _RUNNER,
          '        "certified_for_nf_w8": False,',
          '        "certified_for_nf_w8": True,',
          ("TestEndToEndVerdictLayer::test_the_verdict_layer_never_certifies_qb",),
          "no path through this story may certify QB — `FUND` funds a MEASUREMENT, and only a "
          "FULL-gate Phase B could certify (E2.1-r)"),
    Break("the_bar_is_lowered", _RUNNER,
          '        "dsr_min": QM.DSR_MIN,',
          '        "dsr_min": 0.5,',
          ("TestEndToEndVerdictLayer::test_the_verdict_layer_never_certifies_qb",),
          "⛔ relaxing the certification bar after seeing `dsr_ok` fail is the E2.1-r inversion "
          "and would certify QB on a bar WR/TE/RB were never held to"),
    Break("field_silently_trimmed", _RUNNER,
          "SCORED_LABELS: tuple[str, ...] = tuple(QM.ELIGIBLE)",
          'SCORED_LABELS: tuple[str, ...] = ("zm_floor", "mixall_learned")',
          ("TestProjectionCoversTheDeclaredField::"
           "test_the_field_is_nf_w7fs_declared_four_arms_with_no_trim",),
          "⛔ MH2.2 — a field you have already scored and then cut is the exact selection bias "
          "DSR exists to deflate"),
)


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
    rows, failures = [], 0
    for b in BREAKS:
        original = b.path.read_text()
        occurrences = original.count(b.old)
        if occurrences != 1:
            rows.append((b.name, "ANCHOR", f"anchor occurs {occurrences}× — must be exactly 1"))
            failures += 1
            continue
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
        rows.append((b.name, verdict, note))
        if verdict != "RED":
            failures += 1

    w = max(len(r[0]) for r in rows)
    print(f"\nNF-W7k RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        print(f"  {name.ljust(w)}  {verdict:<6}  {note}")
    print(f"\n{len(rows) - failures}/{len(rows)} RED\n")
    if failures:
        print("⛔ a guard that does not go RED on a deliberate defect is VACUOUS", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
