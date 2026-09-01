"""NF-INJ2c node 3 — guards on the PRE-REGISTRATION and the PM ruling of 2026-09-01.

Every clause here is RED-proven in `betting_ml/tests/nf_inj2c_red_proof.py`: a deliberate break of
the source it reads must turn it red. A guard that cannot fail is the NF1.7 (a) vacuous anchor.

⭐ Prose is matched over WHITESPACE-NORMALISED text (`_flat`), because a guard that fires when a
sentence is re-wrapped teaches people to weaken it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FANTASY = _ROOT / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"
_REPORTS = _FANTASY / "ablation_results"
_PREREG = _REPORTS / "nf_inj2c_preregistration.md"
_MARGIN_RULE = _REPORTS / "nf_inj2c_margin_construction_rule.md"
_SPEC = _ROOT / "plan_specs" / "nfl_fantasy" / "nf-inj2c.yaml"


def _flat(text: str) -> str:
    """Whitespace-normalised, so a line re-wrap cannot fire a prose guard."""
    return re.sub(r"\s+", " ", text)


def _default_deflation_gates(cv_power) -> frozenset:
    """The SHIPPED deflation-class default, read off the instrument rather than transcribed."""
    import inspect

    return inspect.signature(
        cv_power.injected_effect_positive_control).parameters["deflation_gates"].default


@pytest.fixture(scope="module")
def prereg() -> str:
    assert _PREREG.exists(), "the pre-registration is missing"
    return _PREREG.read_text()


@pytest.fixture(scope="module")
def spec() -> str:
    return _SPEC.read_text()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The PM ruling — transcribed, and the record's SHAPE preserved
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_pm_field_declaration_is_transcribed_verbatim(spec: str) -> None:
    """The declaration is the PM's words, not a session's paraphrase."""
    flat = _flat(spec)
    for clause in (
        "the deflation gates' BINDING field is NF-INJ2c's own coherent family, declared on "
        "mechanism before any deflation statistic is computed",
        "point-space assignment rules only — incumbent (reference), stratified, "
        "feasibility_clamp, and the two registered degenerates",
        "the incumbent reference arm ∉ V (MH2.1(a)); degenerates ∈ n_trials, ∉ V",
        "both numbers publish regardless of which looks better, and no third field is ever computed",
        "If the binding family's DSR refuses, that is DEFLATION_REFUSED and the thread closes at "
        "that specification; the diagnostic does not rescue it",
    ):
        assert _flat(clause) in flat, f"the PM's declaration lost a clause: {clause[:60]!r}"


def test_ruling_4_stays_standing_unedited_with_the_correction_beside_it(spec: str) -> None:
    """⭐ The PM's ruling on the RECORD's shape: a refuted premise is part of the record.

    Two things must BOTH hold — the original wording is still present (not tidied away), and an
    annotation names its premise measured false. Either alone is the failure mode.
    """
    flat = _flat(spec)
    # ⭐ The survival anchor must be text the ANNOTATION does not itself quote. The annotation
    # cites "DSR at 8 folds is then a real gate…" to say the premise is false, so asserting on
    # THAT phrase would stay green with ruling 4 deleted — the annotation would satisfy the check
    # written to prove the annotation did not replace it (NF-D17 / INC-38, found by the RED proof).
    for survives in ("4. THE +1 FOLD is registered forward on the data-fidelity ruling already "
                     "given",
                     "0.9325 at 7 does not guarantee 0.95 at 8"):
        assert _flat(survives) in flat, (
            "ruling 4's own wording was edited or removed — the correction goes BESIDE it, never "
            f"in place of it (E2.1-r); missing: {survives[:50]!r}")
    assert _flat("MARKED ANNOTATION ON RULING 4") in flat, "the correction annotation is missing"
    assert _flat("is MEASURED FALSE") in flat, (
        "the annotation must say the premise is measured false")


def test_the_calendar_bound_eighth_fold_is_recorded_as_the_only_remaining_one(spec: str) -> None:
    flat = _flat(spec)
    assert _flat("the realized 2026 season") in flat
    assert _flat("it is not an NF-D18 violation; the trigger names a date, not a purchase no "
                 "design can make") in flat, "the PM's reason for allowing the trigger was dropped"
    # ⭐ the clause above also appears in the closeout SUMMARY, so on its own it would stay green
    # with the VERBATIM ruling gutted. This span exists only in the transcription.
    assert _flat("that is a genuinely reachable trigger and may be published as one") in flat, (
        "the PM's ruling on the trigger is no longer transcribed verbatim — the closeout summary "
        "is not a substitute for the transcription")


def test_the_spec_no_longer_records_the_field_as_held(spec: str) -> None:
    """The hold is resolved; a stale HELD marker would misreport the story's state."""
    assert "HELD FOR A PM RULING — THE DSR FIELD DECLARATION" not in spec
    assert _flat("RESOLVED BY PM RULING 2026-09-01") in _flat(spec)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registration's field — enumerated, and its consequences declared FORWARD
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_binding_field_is_the_five_point_space_arms_and_only_those(prereg: str) -> None:
    flat = _flat(prereg)
    assert _flat("`declared_field_size = 5`") in flat, "the binding field size is not declared"
    for arm in ("`incumbent`", "`stratified`", "`feasibility_clamp`", "`mvp1_null`",
                "`random_order`"):
        assert arm in prereg, f"the binding field omits {arm}"
    for excluded in ("points_rate_permute", "rate_refit", "rate_refit_reselect"):
        assert excluded in prereg, f"the excluded rate-space arm {excluded} must be NAMED"
    assert _flat("not because of anything they scored") in flat, (
        "the exclusion must be on MECHANISM, and must SAY it is not on the arms' scores (MH2.2)")


def test_the_two_member_V_is_declared_forward_as_a_fragility(prereg: str) -> None:
    """⭐ V has exactly two members. That is arithmetic from the field, knowable before scoring.

    Declaring it here is what stops it being produced later as an explanation for a number.
    """
    flat = _flat(prereg)
    assert _flat("`V` has exactly TWO members") in flat, (
        "the two-member V must be declared forward, not discovered after a DSR figure")
    assert "1-df" in flat, "the estimate's degrees of freedom must be stated"
    assert _flat("It is not a licence to change the field afterwards") in flat


def test_the_field_trim_reading_is_declared_structurally_unavailable(prereg: str) -> None:
    """NF-W7h: a trim that deletes the winner is inadmissible. Here it is the ONLY trim available."""
    flat = _flat(prereg)
    assert _flat("INADMISSIBLE BY CONSTRUCTION") in flat
    # ⭐ the phrase appears twice — once DECLARED forward (§2.3(b)), once USED in the gate section
    # (§6). A bare presence check is satisfied by either, so both spans are pinned.
    assert _flat("the 2×2 is reported as **STRUCTURALLY UNAVAILABLE**, ⛔ never as a trimmed "
                 "number") in flat, (
        "the forward declaration that a refused DSR reports the 2x2 as unavailable is gone")
    assert _flat("diagnostic is **STRUCTURALLY UNAVAILABLE** here (§2.3(b))") in flat, (
        "the gate section no longer applies the declaration it was given")


def test_dsr_conv_non_monotonicity_is_declared_so_it_is_not_read_as_a_lever(prereg: str) -> None:
    flat = _flat(prereg)
    assert _flat("NON-MONOTONE") in flat
    assert _flat("both figures are computed and published") in flat
    assert _flat("not** a third field") in flat, (
        "publishing both V conventions must be distinguished from computing a third FIELD")


def test_the_diagnostic_field_is_declared_non_binding_in_advance(prereg: str) -> None:
    """NF-D14's two-sided rule: it publishes whichever way it comes out."""
    flat = _flat(prereg)
    assert _flat("NON-BINDING DIAGNOSTIC") in flat
    assert _flat("published **whichever way it comes out**") in flat
    assert _flat("cannot rescue a binding refusal") in flat


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Folds, and the trigger's standing-rule condition
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_registration_runs_at_seven_folds(prereg: str) -> None:
    flat = _flat(prereg)
    assert _flat("**Folds: SEVEN — 2019–2025**") in flat
    assert _flat("inherited, not chosen") in flat


def test_the_2026_trigger_carries_its_reachability_condition(prereg: str) -> None:
    """⭐ A fold trigger is meaningless when SR <= SR0 — n scales a positive gap, never creates one.

    The PM's ruling is permissive ("may be published"), so conditioning it is a standing-rule
    application; publishing it unconditionally would be the NF-D18 misleading direction.
    """
    flat = _flat(prereg)
    assert _flat("DSR_UNREACHABLE") in flat
    assert _flat("WITHHELD with that reason stated") in flat, (
        "an unreachable trigger must be withheld WITH its reason, not silently dropped")
    assert _flat("√(n−1)") in flat, "the mechanism (n enters only through sqrt(n-1)) must be named"


def test_the_design_quantities_are_the_ones_cv_power_actually_computes() -> None:
    """⭐ Not a restatement of the document: recompute them and compare.

    These depend only on the fold count, so they are knowable before any scoring — which is why
    they belong in a pre-registration at all.
    """
    from betting_ml.utils import cv_power

    text = _flat(_PREREG.read_text())
    ceiling = cv_power.dsr_ceiling(7)
    assert ceiling > 0.95, "the ceiling would bind — the document's claim would be wrong"
    assert f"{ceiling:.5f}" in text, (
        f"the document must quote the computed dsr_ceiling(7)={ceiling:.5f}")

    clause = cv_power.fold_consistency_clause(n_folds=7)
    assert _flat(f"**{clause.wins_required} of 7 wins required**") in text, (
        f"the document must quote the calibrated clause ({clause.wins_required} of 7)")
    assert f"{clause.attained_false_fire:.4f}" in text
    assert clause.wins_required >= clause.legacy_wins_required, (
        "MH2 H8: the calibrated clause is weakly STRICTER at every n")

    assert cv_power.pbo_evaluable(n_folds=7, n_configs=5), (
        "PBO would be UNDEFINED at this design — the document's claim would be wrong")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Coherence measured, never gated; and the margin rule is pointed at, not restated
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_coherence_is_measured_and_reported_never_gated_at_zero(prereg: str) -> None:
    flat = _flat(prereg)
    assert _flat("MEASURED AND REPORTED, ⛔ NEVER GATED AT ZERO") in flat
    assert _flat("with **no bar**") in flat
    assert _flat("never as a distance from zero") in flat


def test_the_prereg_points_at_the_margin_rule_rather_than_restating_it(prereg: str) -> None:
    """Two documents that both DEFINE the bands are two rule sets that can drift (E9.61)."""
    flat = _flat(prereg)
    assert _flat("is BINDING and") in flat and _flat("this is a pointer, not a restatement") in flat


def test_every_margin_rule_measure_survives_into_the_registration(prereg: str) -> None:
    """The six measures are the verdict. A measure silently dropped between 3a and the prereg is
    exactly the "drop a dimension" move PM ruling 3 forbids."""
    rule = _MARGIN_RULE.read_text()
    declared = set(re.findall(r"\|\s*(M[1-6])\s*\|", rule))
    assert len(declared) == 6, f"the margin rule no longer declares six measures: {sorted(declared)}"
    for m in sorted(declared):
        # ⭐ a bare `m in prereg` is satisfied by the range "M1–M6" elsewhere in the prose, so a
        # dropped row would stay green. Require the measure's own TABLE ROW.
        assert re.search(rf"\|\s*{m}\s*\|", prereg), (
            f"{m} was declared in the margin rule and has no row in the prereg's verdict table")


def test_a_single_regression_is_a_null_and_not_a_band_to_widen(prereg: str) -> None:
    flat = _flat(prereg)
    assert _flat("that is a NULL, not a margin to adjust") in flat
    assert _flat("never a band to widen, a measure to drop, or a dimension to re-classify") in flat


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The positive control's partition — declared BEFORE the control runs
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_injection_invariant_partition_is_declared_forward(prereg: str) -> None:
    """⭐ NF-INJ2b's BLIND badge was a wrong READING: its blockers were injection-invariant.

    Declaring which gates an injected effect can move, before the control runs, is what makes the
    verdict readable instead of a badge to argue with.
    """
    flat = _flat(prereg)
    assert _flat("INJECTION-SENSITIVE") in flat and _flat("INJECTION-INVARIANT") in flat
    assert _flat("never re-run with a constraint removed") in flat, (
        "re-running the control without the blocker to get a nicer badge is the E2.1-r inversion")


def test_the_plat_cvp2_claim_is_true_of_the_installed_instrument(prereg: str) -> None:
    """⭐ The document asserts PLAT-CVP2 has not landed. Check the instrument, not the prose.

    If the fix DOES land later this turns red, which is the correct outcome: the annotation-around
    would then be stale and the registration should consume the real verdict instead.
    """
    import inspect

    from betting_ml.utils import cv_power

    claims_absent = _flat("**has not landed**") in _flat(prereg)
    assert claims_absent, "the prereg no longer states PLAT-CVP2's status — it must state one"
    src = inspect.getsource(cv_power)
    assert "CONSTRAINT_BLOCKED" not in src, (
        "PLAT-CVP2 appears to have LANDED — the prereg's annotation-around is now stale and the "
        "registration must consume the real CONSTRAINT_BLOCKED verdict")
    params = inspect.signature(cv_power.injected_effect_positive_control).parameters
    assert "injection_invariant_gates" not in params


def test_the_deflation_gate_partition_takes_the_shipped_defaults(prereg: str) -> None:
    """The program convention is a DEFAULT; an override needs a registered reason."""
    from betting_ml.utils import cv_power

    flat = _flat(prereg)
    assert _flat("no `deflation_gates=` override is registered") in flat
    default = set(_default_deflation_gates(cv_power))
    assert default == {"deflated_sharpe", "pbo", "dsr", "cscv"}, (
        f"the shipped deflation-class default moved to {sorted(default)} — the prereg quotes the "
        "old set and must be re-read against the instrument")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Provenance — the claim that makes the document trustworthy
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_prereg_was_written_before_the_remeasure_and_says_so_checkably(prereg: str) -> None:
    """⭐ The strongest provenance available: it cannot have been shaped by numbers nobody has seen.

    A prose claim is worth nothing on its own, so the guard checks the world: the node-3b report
    must not exist alongside a document asserting it did not.
    """
    flat = _flat(prereg)
    assert _flat("BEFORE the node-3b re-measure has been run") in flat
    assert not (_REPORTS / "nf_inj2c_dominance_baseline.json").exists(), (
        "the node-3b report EXISTS — the prereg's provenance claim is no longer true and must be "
        "corrected rather than left standing")
    assert not (_REPORTS / "nf_inj2c_dominance_baseline.md").exists()


def test_the_prereg_does_not_quote_the_incumbent_baseline(prereg: str) -> None:
    """The baseline lives in node 3b's report. A prereg with an edit path is not a prereg."""
    flat = _flat(prereg)
    assert _flat("it is ⛔ never copied into this one") in flat
    assert _flat("reads the baseline THROUGH 3a's already-committed bands") in flat


def test_no_per_candidate_family_dsr_was_computed_before_the_declaration(prereg: str) -> None:
    """NF-INJ3b-M: publishing a menu of per-family DSRs hands the successor a field chosen on it."""
    flat = _flat(prereg)
    assert _flat("no per-candidate-family DSR was computed") in flat
    assert _flat("NF-INJ3b-M") in flat


def test_the_superseded_margin_rule_branch_is_marked_not_edited(prereg: str) -> None:
    """3a §5 branch 5 says "DSR at 8 folds". It is superseded by measurement and left verbatim."""
    rule = _flat(_MARGIN_RULE.read_text())
    assert _flat("DSR at 8 folds does not clear 0.95") in rule, (
        "the margin rule's branch 5 was EDITED — a superseded branch is marked in the successor "
        "document, never rewritten in place (E2.1-r / NF-W7f)")
    flat = _flat(prereg)
    assert _flat("SUPERSEDED by measurement") in flat
    assert _flat("left **VERBATIM and UNEDITED**") in flat
