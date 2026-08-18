"""NF-W7j RED proof — break the source, prove each guard goes RED.

    uv run python quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w7j.py

A guard that cannot FAIL is worse than none (NF1.7 (a) / INC-38 / NF-D17). This harness applies one
deliberate defect at a time and asserts the named guard turns RED. The four disciplines this repo has
paid for are enforced, exactly as in NF-W7i's harness:

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
_CONST = Path(__file__).with_name("fp_component_clause.py")
_RUNNER = Path(__file__).with_name("run_nf_w7j_component_clause.py")
_TESTS = _ROOT / "betting_ml/tests/test_nf_w7j_component_clause.py"
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
    # ── the decision's own semantics ───────────────────────────────────────────────────────────
    Break("fail_open_instead_of_fail_closed", _RUNNER,
          'refuses = bool(demonstrable and material_primary and effect_well_defined) if audit_ok \\\n'
          '        else bool(raw["refuses"])',
          "refuses = bool(audit_ok and demonstrable and material_primary and effect_well_defined)",
          ("test_condition_A_FAILS_CLOSED_to_the_raw_clause_never_fail_open",
           "test_fail_closed_still_tracks_the_raw_verdict_when_the_raw_clause_would_pass"),
          "the natural-looking `audit_ok and …` is fail-OPEN: an expired audit silently REMOVES "
          "the gate instead of reverting to the raw 0.0 tolerance"),
    Break("demonstrable_half_dropped", _RUNNER,
          "refuses = bool(demonstrable and material_primary and effect_well_defined) if audit_ok",
          "refuses = bool(material_primary and effect_well_defined) if audit_ok",
          ("test_condition_B_alone_decides_when_A_C_D_all_hold",),
          "the clause refuses on a magnitude whose SIGN is not established (NF-W7f's 5/8 folds)"),
    Break("material_half_dropped", _RUNNER,
          "refuses = bool(demonstrable and material_primary and effect_well_defined) if audit_ok",
          "refuses = bool(demonstrable and effect_well_defined) if audit_ok",
          ("test_condition_C_alone_decides_when_A_B_D_all_hold",),
          "any demonstrable degradation refuses, however far below the materiality band"),
    Break("effect_well_defined_dropped", _RUNNER,
          "refuses = bool(demonstrable and material_primary and effect_well_defined) if audit_ok",
          "refuses = bool(demonstrable and material_primary) if audit_ok",
          ("test_condition_D_alone_decides_when_A_B_C_all_hold",),
          "the materiality RATIO is taken against a non-positive claimed effect (meaningless)"),

    # ── thresholds must be DESIGN quantities (E2.1-r) ──────────────────────────────────────────
    Break("alpha_reverse_engineered_to_admit_the_observed_p", _CONST,
          "ALPHA_DEMONSTRABLE: float = 0.05",
          "ALPHA_DEMONSTRABLE: float = 0.20",
          ("test_the_materiality_fraction_is_nf_w7c_s_convention_not_nf_w7f_s_observed_value",),
          "α widened until NF-W7f's p=0.1611 clears it — the bar reverse-engineered to the answer"),
    Break("materiality_fraction_reverse_engineered", _CONST,
          "MATERIALITY_FRACTION: float = 0.10",
          "MATERIALITY_FRACTION: float = 6.0",
          ("test_the_materiality_fraction_is_nf_w7c_s_convention_not_nf_w7f_s_observed_value",),
          "the band inflated past the observed +0.3866% so the component reads immaterial"),
    Break("raw_clause_erased", _RUNNER,
          '"refuses": bool(pooled_rel > CC.RAW_TOLERANCE),',
          '"refuses": False,',
          ("test_the_raw_tolerance_is_retained_so_both_readings_are_always_reported",),
          "NF-W7f's FAILED pre-registered clause is silently re-labelled as passing (NF-D20)"),

    # ── the audit cannot pass vacuously ────────────────────────────────────────────────────────
    Break("positive_control_check_removed", _RUNNER,
          '        if not controls[seed]:\n'
          '            raise InvalidRun(\n'
          '                f"POSITIVE CONTROL EMPTY for {seed!r}',
          '        if False:\n'
          '            raise InvalidRun(\n'
          '                f"unused {seed!r}',
          ("test_the_audit_raises_when_a_positive_control_comes_back_empty",),
          "a closure walker that resolves NOTHING reports a clean PASS for every seed"),
    Break("unresolvable_seed_accepted", _RUNNER,
          "        if _module_path(seed, root) is None:\n            raise InvalidRun(",
          "        if False:\n            raise InvalidRun(",
          ("test_the_audit_raises_on_an_unresolvable_seed",),
          "a renamed/mistyped seed yields an empty closure, which has no hits — it reads as PASS"),
    Break("serving_plane_loses_its_producer", _CONST,
          '    "quant_sports_intel_models.football.nfl.fantasy.season_projection",',
          "",
          ("test_the_serving_plane_seed_set_covers_producer_exporter_api_and_scorer",),
          "the model that PRODUCES the stat line is dropped — the audit checks the wrong plane"),

    # ── the band read (NF-W7i) ─────────────────────────────────────────────────────────────────
    Break("band_state_says_power_limited", _RUNNER,
          '    # the interval straddles the band: the design does not resolve the magnitude\n'
          '    return "UNDECIDED_MAGNITUDE"',
          '    return "POWER_LIMITED"',
          ("test_the_band_state_is_three_way_and_never_says_power_limited",
           "test_a_ci_straddling_the_band_is_undecided_not_immaterial"),
          "a BAND decision is published as a POWER verdict — the NF-W7i hand-correction, undone"),
    Break("undecided_read_as_immaterial", _RUNNER,
          "    if hi < band:\n        return \"MEASURED_IMMATERIAL\"",
          "    if lo < band:\n        return \"MEASURED_IMMATERIAL\"",
          ("test_a_ci_straddling_the_band_is_undecided_not_immaterial",),
          "the dangerous direction: a WIDE interval is reported as 'we measured it small'"),
    Break("absolute_unit_sensitivity_dropped", _RUNNER,
          '            "sensitivity_absolute": {',
          '            "_dropped_sensitivity": {',
          ("test_both_units_are_reported_and_the_verdict_states_whether_they_agree",),
          "only the convenient unit is reported, so a unit-dependent verdict cannot be seen"),

    # ── the significance instrument ────────────────────────────────────────────────────────────
    Break("instrument_swapped_for_a_bespoke_test", _RUNNER,
          "    p_one_sided = M14.onesided_paired_pvalue(d)",
          "    p_one_sided = float(1.0 - (d > 0).mean())",
          ("test_the_demonstrable_half_uses_the_harness_s_own_paired_test_by_identity",),
          "a NEW test is substituted for the harness's own — chosen after seeing the answer"),

    # ── the reproduction pin (prereg §3) ───────────────────────────────────────────────────────
    Break("pin_tolerance_loosened", _CONST,
          "PIN_TOLERANCE: float = 1e-9",
          "PIN_TOLERANCE: float = 1.0",
          ("test_the_pin_raises_on_any_drift_from_the_object_nf_w7f_scored",),
          "the decision is measured against a different object than the one NF-W7f scored"),
    Break("series_pinned_to_the_pooled_ratio_of_sums", _RUNNER,
          '    by_fold_mean = CC.W7F_PINS["per_leg_relative_change_winner_by_fold_mean"]',
          '    by_fold_mean = CC.W7F_PINS["per_leg_relative_change"]',
          ("test_the_pin_distinguishes_the_pooled_ratio_from_the_mean_of_fold_ratios",),
          "a ratio of SUMS is conflated with a mean of per-fold ratios (NF1.8)"),

    # ── the certification bar (prereg §4) ──────────────────────────────────────────────────────
    Break("certification_drops_the_full_gate_requirement", _RUNNER,
          '"certified_for_nf_w8": bool(full_gate_green and CC.CERTIFICATION_REQUIRES_FULL_GATE),',
          '"certified_for_nf_w8": bool(CC.CERTIFICATION_REQUIRES_FULL_GATE),',
          ("test_certification_requires_the_FULL_gate_the_bar_wr_and_te_actually_cleared",),
          "QB is certified on a 'PIT + component + beats incumbent' bar that omits `dsr_ok` — the "
          "E2.1-r inversion, and a bar WR/TE were never held to"),
    Break("declared_field_size_pin_dropped", _CONST,
          "W7F_DECLARED_FIELD_SIZE = 4",
          "W7F_DECLARED_FIELD_SIZE = 2",
          ("test_the_purely_statistical_refusal_is_classified_at_the_declared_field_size",),
          "the field is silently trimmed below the pre-registered family (MH2.2)"),
    Break("unsafe_field_shrink_flag_removed", _RUNNER,
          "    verdict = GE.flag_unsafe_field_shrink(",
          "    verdict = dict(",
          ("test_the_purely_statistical_refusal_is_classified_at_the_declared_field_size",),
          "the instrument's 'use a SMALLER field' prose ships unflagged at the declared minimum"),
    Break("anchor_failure_gets_a_data_retest_trigger", _RUNNER,
          '"state": "CONSTRAINT_REFUSED", "binding_half": "anchor", "retest_trigger": None,',
          '"state": "CONSTRAINT_REFUSED", "binding_half": "anchor", "retest_trigger": "+4 folds",',
          ("test_a_remaining_anchor_failure_stays_constraint_refused_with_no_data_trigger",),
          "publishes the 'more data' trigger NF-D18 forbids for a non-rescuable anchor refusal"),
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
    print(f"\nNF-W7j RED proof — {len(BREAKS)} deliberate defects\n")
    for name, verdict, note in rows:
        print(f"  {name.ljust(w)}  {verdict:<6}  {note}")
    print(f"\n{len(rows) - failures}/{len(rows)} RED\n")
    if failures:
        print("⛔ a guard that does not go RED on a deliberate defect is VACUOUS", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
