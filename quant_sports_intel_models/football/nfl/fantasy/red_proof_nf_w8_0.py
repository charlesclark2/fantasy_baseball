"""NF-W8-0 RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness applies
one deliberate defect at a time and asserts the named guard turns RED. The four disciplines this
repo has paid for are enforced, exactly as in NF-W7i/W7j's harnesses:

- **the mutation must LAND** (E11.24 #682) — a no-op break reports a FALSE "the guard is
  vacuous", which reads as a real finding and invites weakening a correct guard;
- **the anchor must be UNIQUE** (#885) — a replace can otherwise land on the WRONG symbol;
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
_CONST = Path(__file__).with_name("fp_cross_position.py")
_RUNNER = Path(__file__).with_name("run_nf_w8_0_cross_position.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w8_0_cross_position.py"
_TIMEOUT_S = 300


@dataclass(frozen=True)
class Break:
    name: str
    path: Path
    old: str
    new: str
    tests: tuple[str, ...]
    defect: str


BREAKS: tuple[Break, ...] = (
    # ── §1 the QB consumption registration ─────────────────────────────────────────────────────
    Break("qb_consumption_repointed_off_option_b", _CONST,
          '    "QB": "qb_zm_floor",        # NF-W7f `zm_floor`, by identity (Option B, §1)',
          '    "QB": "qb_mixall",          # silently repointed',
          ("TestQBConsumptionRegistration::test_option_b_constants_are_pinned",),
          "the consumed QB generator drifts off the registered Option-B object"),
    Break("second_reader_silently_signed", _CONST,
          '    "requested": True,',
          '    "requested": False,',
          ("TestQBConsumptionRegistration::test_second_reader_flag_is_open",),
          "the open governance flag is closed without a reader"),
    Break("weaker_footing_caveat_dropped", _CONST,
          "'calibrated + best-on-record, consumed under Option B; not certification-equivalent'",
          "'calibrated + best-on-record, consumed under Option B'",
          ("TestQBConsumptionRegistration::test_caveat_travels_and_does_not_claim_certification",),
          "the caveat quietly stops saying QB is not certification-equivalent"),
    Break("qb_pin_repointed_to_the_unrecalibrated_arm", _CONST,
          '    "QB": (_AR + "nf_w7f_qb_marginal.json", "NF-W7f", "zm_floor"),',
          '    "QB": (_AR + "nf_w7f_qb_marginal.json", "NF-W7f", "mixall_learned"),',
          ("TestQBConsumptionRegistration::test_option_b_constants_are_pinned",
           "TestReproductionPlumbing::test_qb_pin_matches_the_w7f_headline"),
          "the reproduction pin measures a DIFFERENT object than the one Option B registered"),

    # ── the verdict rule ────────────────────────────────────────────────────────────────────────
    Break("unevaluable_clause_becomes_a_pass", _CONST,
          "                if v is None:\n                    missing.append(c)\n"
          "                elif not v:",
          "                if v is None:\n                    pass\n"
          "                elif not v:",
          ("TestComparabilityVerdict::test_any_other_unevaluable_clause_refuses",),
          "a clause that DID NOT RUN is silently scored as green (NF1.7 (a))"),
    Break("verdict_ships_on_gap_alone", _CONST,
          "        if winner is not None and not failing and not missing:",
          "        if winner is not None:",
          ("TestComparabilityVerdict::test_each_failing_clause_alone_refuses",),
          "a detected gap ships the arm regardless of its admissibility clauses"),
    Break("undefined_family_a_becomes_no_gap", _CONST,
          '        "gap_detected": (None if not evaluable else bool(any(rejected[n] for n in evaluable))),',
          '        "gap_detected": (False if not evaluable else bool(any(rejected[n] for n in evaluable))),',
          ("TestPairwiseGapTests::test_one_fold_is_undefined_never_false",),
          "a family that could not evaluate is read as a clean 'no gap' (NF1.7 (a))"),
    Break("mde_multiplier_zeroed", _CONST,
          "MDE_MULT = float(sps.norm.ppf(0.975) + sps.norm.ppf(0.80))",
          "MDE_MULT = 0.0",
          ("TestPairwiseGapTests::test_distinct_biases_are_detected",),
          "the bounded-null statement collapses to 'no artifact larger than 0' — a free pass"),
    Break("permutation_cycle_becomes_identity", _CONST,
          'PERMUTATION_CYCLE: dict[str, str] = {"QB": "RB", "RB": "WR", "WR": "TE", "TE": "QB"}',
          'PERMUTATION_CYCLE: dict[str, str] = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE"}',
          ("TestPermutedParams::test_cyclic_shift",
           "TestPermutedParams::test_cycle_is_a_derangement"),
          "the permutation anchor becomes the real arm — beats_permuted turns vacuous"),

    # ── the estimators / chronology ─────────────────────────────────────────────────────────────
    Break("recal_peeks_at_the_eval_fold", _RUNNER,
          "        prior = [rows_by_fold[l] for l in labels[:k]]",
          "        prior = [rows_by_fold[l] for l in labels[:k + 1]]",
          ("TestDeriveEndToEnd::test_recal_is_fit_on_prior_folds_only",),
          "the level fit includes the eval fold's own rows — the in-sample recal NF-MARGIN1 bans"),
    Break("negative_affine_slope_admitted", _RUNNER,
          '            if prm["fitted"] and prm["b"] <= XP.AFFINE_MIN_SLOPE:',
          "            if False:",
          ("TestLevelFits::test_negative_slope_makes_the_arm_ineligible",),
          "a board-inverting slope ships (NF-D16: an affine is only conditionally monotone)"),
    Break("absent_record_reproduces", _RUNNER,
          '        return {"reproduces": False, "n_folds_compared": 0, "max_abs_gap": None,',
          '        return {"reproduces": True, "n_folds_compared": 0, "max_abs_gap": None,',
          ("TestReproductionPlumbing::test_absent_record_is_did_not_run",),
          "a reproduction control that DID NOT RUN is scored as a pass (NF1.7 (a))"),

    # ── the gates must be COMPUTED, never asserted ──────────────────────────────────────────────
    Break("pbo_gate_asserted_true", _RUNNER,
          '        clauses["pbo_ok"] = bool(\n'
          "            (pbo is not None and pbo < XP.PBO_MAX)\n"
          "            or (os_gap is not None and os_gap <= XP.OS_GAP_TIE_PCT))",
          '        clauses["pbo_ok"] = True',
          ("TestGateComputationSourceInspection::test_pbo_clause_reads_both_registered_constants",),
          "the deflation gate is a literal True — every field passes it"),
    Break("dsr_gate_asserted_true", _RUNNER,
          '        clauses["dsr_ok"] = bool(dsr is not None and dsr >= XP.DSR_MIN)',
          '        clauses["dsr_ok"] = True',
          ("TestGateComputationSourceInspection::test_dsr_clause_is_computed_not_asserted",),
          "the DSR gate is a literal True — the house §0.5 bar silently removed"),

    Break("pin_scores_rounded_below_the_tolerance", _RUNNER,
          '        "scores": {k: float(v) for k, v in scores.items()},',
          '        "scores": {k: round(v, 6) for k, v in scores.items()},',
          ("TestGateComputationSourceInspection::test_pin_scores_are_stored_at_full_precision",),
          "the smoke's real catch, re-armed: rounding the stored scores caps every reproduction "
          "pin at ~5e-7 against 1e-9 — the decisive run returns UNDEFINED at every position"),

    # ── the PIT-preservation identity at the artifact ───────────────────────────────────────────
    Break("writer_shifts_the_band_with_the_point", _RUNNER,
          '        w["point_vs_bank_offset"] = w["point_recal"] - w["point_raw"]',
          '        w["point_vs_bank_offset"] = (w["point_recal"] - w["point_raw"]); '
          'w["p50"] = w["p50"] + 0.25',
          ("TestDeriveEndToEnd::test_real_gap_is_removed",),
          "the NF-TR2 apply_to_band mistake: the certified band moves with the point — the "
          "banks_untouched identity must catch it at the written artifact and demote the ship"),
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
    print(f"\nNF-W8-0 RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        print(f"  {name.ljust(w)}  {verdict:<6}  {note}")
    print(f"\n{len(rows) - failures}/{len(rows)} RED\n")
    if failures:
        print("⛔ a guard that does not go RED on a deliberate defect is VACUOUS", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
