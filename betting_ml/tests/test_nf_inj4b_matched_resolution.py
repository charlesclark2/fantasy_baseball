"""NF-INJ4b — guards for the MATCHED-RESOLUTION oracle anchor and the honesty clause.

⭐ WHAT THESE GUARD, AND WHY EACH ONE CAN FAIL. Every clause below has an ISOLATING fixture — one
that satisfies every OTHER clause of the same conjunction — because a guard on `A and B and C`
whose fixture also trips B proves nothing about A (NF-D17; NF-W7j's refinement: an isolating
fixture per clause is necessary but not sufficient when one clause re-tests another).

⛔ NF-INJ4's record stands unedited. Nothing here re-reads its refusal; these guard the SUCCESSOR's
registration going forward.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import (
    nf_inj4_designation_duration as DD,
    nf_inj4b_designation_duration as B,
    run_nf_inj4b_designation_duration as R,
)

_RUNNER = Path(R.__file__)
_MODULE = Path(B.__file__)
_REPORT_DIR = _MODULE.parent / "ablation_results"
_RESULT = _REPORT_DIR / "nf_inj4b_designation_duration.json"
_PREREG = _REPORT_DIR / "nf_inj4b_preregistration.md"


def _strip_comments(src: str) -> str:
    """⛔ INC-38: a source-inspection guard that a COMMENT can satisfy is vacuous. This story's own
    module and prereg discuss the retired clause in prose at length, so every scan below reads
    comment-stripped source."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


# ── the registration delta ─────────────────────────────────────────────────────────────────────
def test_both_anchor_readings_are_registered_as_separately_named_clauses():
    """⭐ THE ONE THING THIS STORY EXISTS FOR. The NF-W6d inactive-pair reading and the NF1.9 (f)
    capacity reading are DIFFERENT guards — registering one does not give you the other (the
    standing convention NF-INJ4 produced). Both must be NAMED, and neither may be implied."""
    assert B.ANCHOR_CLAUSE_INFORMATIVE in B.GATE_CLASSES
    assert B.ANCHOR_CLAUSE_FLOOR in B.GATE_CLASSES
    assert B.ANCHOR_CLAUSE_INFORMATIVE != B.ANCHOR_CLAUSE_FLOOR


def test_the_naive_oracle_clause_is_retired_from_the_gate_table():
    """⛔ The clause NF-INJ4 refused on measured the ORACLE'S SAMPLE SIZE, not an arm property. It
    must not be a gate here — and it must still be REPORTED, because retiring a clause is not a
    reason to stop showing its number."""
    assert "oracle_respected" not in B.GATE_CLASSES
    src = _strip_comments(_RUNNER.read_text())
    assert "retired_naive_clause_arm_ge_oracle" in src, (
        "the retired clause is no longer computed — its number must stay on the record")


def test_the_field_and_folds_are_inherited_by_IMPORT_not_restated():
    """⭐ The honesty clause's precondition is a fact about the imports. A second declaration of the
    field would be a second place for it to drift, and 'unchanged' would become a claim a reader has
    to check by eye."""
    assert B.ARMS is DD.ARMS and B.SHIPPABLE_ARMS is DD.SHIPPABLE_ARMS
    assert B.DECLARED_FIELD_SIZE == DD.DECLARED_FIELD_SIZE == 7
    assert (B.N_FOLDS, B.FOLD_SEED) == (DD.N_FOLDS, DD.FOLD_SEED)
    assert B.MIN_CELL_N == DD.MIN_CELL_N == 30, (
        "MIN_CELL_N moved. `doubtful` holds 29 rows, and lowering the threshold to 29 BECAUSE 29 is "
        "the number that would unlock it is reverse-engineering a design constant from the answer "
        "(MH2.2)")


def test_both_anchor_clauses_are_declared_injection_invariant_forward():
    """The declaration NF-INJ4 said belonged to its successor, made in the registration module (so
    it is committed BEFORE the run) rather than annotated onto a result."""
    assert B.ANCHOR_CLAUSE_INFORMATIVE in B.INVARIANT_GATES
    assert B.ANCHOR_CLAUSE_FLOOR in B.INVARIANT_GATES
    assert all(B.GATE_CLASSES[g] == "invariant" for g in B.INVARIANT_GATES)


def test_the_gate_partition_is_declared_explicitly_and_covers_every_gate():
    """PLAT-CVP2 defect 2: a PARTIALLY declared partition reintroduces the ambiguity it removes, and
    the name heuristic cannot affirm 'there is no deflation gate here'."""
    src = _strip_comments(_RUNNER.read_text())
    assert "gate_classes=B.GATE_CLASSES" in src, (
        "the positive control is no longer driven by the EXPLICIT partition")
    tbl = R.gate_table.__doc__ or ""
    assert tbl, "gate_table lost its docstring"
    assert set(B.GATE_CLASSES) >= {"dsr_ok", "degenerates_lose"}


# ── the three-state anchor reading ─────────────────────────────────────────────────────────────
def _fold(arm_c: float, orc_c: float, ctl_c: float, n_test: int = 131, n_train: int = 1178):
    """One synthetic fold carrying ONLY the anchor quantities the audit reads."""
    def sc(c):
        return {"crps": float(c), "mae": float(c), "mean_expected_games_missed": 0.0, "n": n_test}
    arms = {a: sc(arm_c) for a in DD.ARMS}
    return {"n_test": n_test, "n_train": n_train,
            "arms": arms,
            "oracles": {a: sc(orc_c) for a in DD.ARMS},
            "matched_n": {a: sc(ctl_c) for a in DD.ARMS},
            "permutation": {a: sc(arm_c + 1.0) for a in DD.SHIPPABLE_ARMS}}


def test_an_oracle_that_beats_its_matched_n_control_is_ACTIVE_and_the_floor_holds():
    a = R.anchor_audit([_fold(0.50, 0.60, 0.64)] * 3, DD.PRIMARY_ARM)
    assert a[DD.PRIMARY_ARM]["state"] == "ACTIVE"
    assert a[DD.PRIMARY_ARM]["pair_active"] and a[DD.PRIMARY_ARM]["floor_holds"]
    assert not a[DD.PRIMARY_ARM]["floor_reading_is_vacuous_here"]


def test_an_oracle_that_TIES_its_control_is_INACTIVE_and_is_neither_a_refusal_nor_a_pass():
    """NF-W6d lost three shippable arms to reading a tie as 'this form has no headroom'; NF1.7 (a)
    forbids reading it as a pass. It must be UNINFORMATIVE, and the floor's reading on it VACUOUS."""
    a = R.anchor_audit([_fold(0.50, 0.64, 0.64)] * 3, DD.PRIMARY_ARM)
    v = a[DD.PRIMARY_ARM]
    assert v["state"] == "INACTIVE"
    assert not v["pair_active"]
    assert v["floor_holds"] and v["floor_reading_is_vacuous_here"], (
        "an inactive pair satisfies the floor VACUOUSLY — that must be recorded, or its pass is "
        "counted as evidence (NF-D20)")


def test_a_control_that_BEATS_the_peeking_oracle_VIOLATES_the_floor():
    """⭐ THE CLAUSE THAT MAKES B NON-VACUOUS. If an HONEST matched-n fit beats the peek, the
    'oracle' is not a floor at all. Without this state, B would be implied by ACTIVE and could
    never fail."""
    a = R.anchor_audit([_fold(0.50, 0.64, 0.60)] * 3, DD.PRIMARY_ARM)
    v = a[DD.PRIMARY_ARM]
    assert v["state"] == "VIOLATED"
    assert not v["floor_holds"]
    assert not a["_clauses"][B.ANCHOR_CLAUSE_FLOOR]["passes"]


def test_the_floor_clause_reports_its_NON_VACUOUS_count_beside_the_raw_pass_count():
    """NF-D20: count what the mechanism could ACT on before crediting 'the constraint held N of M'."""
    a = R.anchor_audit([_fold(0.50, 0.64, 0.64)] * 3, DD.PRIMARY_ARM)
    cf = a["_clauses"][B.ANCHOR_CLAUSE_FLOOR]
    assert "n_holding_NON_VACUOUSLY" in cf and "active pairs" in cf["n_holding_NON_VACUOUSLY"]
    assert cf["n_holding_NON_VACUOUSLY"].startswith("0/0"), (
        "with every pair tied, the floor holds on paper and on NOTHING in substance")


def test_an_all_inactive_anchor_family_FAILS_the_informative_clause():
    """⭐ Clause A's isolating case, and it is what stops A being decorative: an anchor family in
    which nothing could act certified nothing. ⚠️ Note the floor clause PASSES on this same fixture
    — which is exactly why the two readings must be separate clauses."""
    a = R.anchor_audit([_fold(0.50, 0.64, 0.64)] * 3, DD.PRIMARY_ARM)
    assert not a["_clauses"][B.ANCHOR_CLAUSE_INFORMATIVE]["passes"]
    assert a["_clauses"][B.ANCHOR_CLAUSE_FLOOR]["passes"], (
        "the floor passes here VACUOUSLY — if a single merged clause were registered instead of "
        "two, this field would score as a passed anchor check")


def test_an_unfittable_anchor_is_a_hard_failure_never_a_pass():
    """NF1.7 (a): an anchor that fails to fit makes its check vacuously true."""
    folds = [_fold(0.50, 0.60, 0.64)] * 3
    for f in folds:
        f["oracles"][DD.PRIMARY_ARM]["crps"] = float("nan")
    a = R.anchor_audit(folds, DD.PRIMARY_ARM)
    assert a[DD.PRIMARY_ARM]["evaluable"] is False
    assert not a["_clauses"]["all_anchors_evaluable"]


def test_a_control_fitted_at_FULL_resolution_is_refused_as_unmatched():
    """⭐ The self-check on the anchor CONSTRUCTION. A control that silently fitted at full
    resolution would make BOTH clauses vacuous while still returning a number."""
    folds = [_fold(0.50, 0.60, 0.64, n_test=1178, n_train=131)] * 3
    a = R.anchor_audit(folds, DD.PRIMARY_ARM)
    assert not a["_resolution"]["matched_on_every_fold"]
    assert not a["_clauses"]["all_anchors_evaluable"]


def test_the_matched_n_control_is_actually_drawn_at_the_peeks_row_count():
    """⛔ The runtime check above computes the control size as `min(n_test, n_train)`. That is only
    true if the SCORING code really draws that many rows — otherwise the check restates an
    assumption instead of testing it (NF-C0e)."""
    from quant_sports_intel_models.football.nfl.fantasy import (
        run_nf_inj4_designation_duration as R4)
    body = _strip_comments(Path(R4.__file__).read_text())
    body = body.split("def score_fold(", 1)[1].split("\ndef ", 1)[0]
    assert re.search(r"size\s*=\s*min\(\s*n_peek\s*,\s*len\(train\)\s*\)", body), (
        "the matched-n control is no longer drawn at the peek's row count — the matched-resolution "
        "reading has become unmatched, and both clauses would be vacuous")


# ── the honesty clause ─────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(not _RESULT.exists(), reason="decisive run artifact absent")
def test_the_record_reproduces_nf_inj4_and_says_that_is_a_PIPELINE_check():
    """⭐ The honesty clause's proof AND its limit. A pass certifies the pipeline; it certifies
    nothing about the mechanism."""
    d = json.loads(_RESULT.read_text())
    pin = d["reproduction_pin"]
    assert pin["evaluable"] and pin["all_reproduce"], pin.get("failures")
    assert pin["figures_checked"] >= 30
    assert "PIPELINE" in pin["what_a_pass_certifies"]
    assert "certifies NOTHING about the mechanism" in pin["what_a_pass_certifies"]
    assert "never" in d["honesty_clause"].lower() and "confirmation" in d["honesty_clause"]


@pytest.mark.skipif(not _RESULT.exists(), reason="decisive run artifact absent")
def test_the_positive_control_verdict_is_recorded_verbatim_and_decomposed_not_relabelled():
    """⛔ E2.1-r: an instrument's badge is ANNOTATED, never re-labelled. `VACUOUS` must survive in
    the record, and the claim behind it must be MEASURED rather than argued."""
    d = json.loads(_RESULT.read_text())
    ctl = d["positive_control"]
    assert ctl["verdict"] == "VACUOUS", "the recorded badge changed — it must stand as returned"
    spec = ctl["null_control_leg_specification"]
    assert spec["verdict_stands"] is True
    absent = d["diagnostics"]["mechanism_absent_control"]
    assert absent["n_shuffles"] >= 3, "one shuffle cannot decide whether a family discriminates"
    assert absent["family_discriminates"] is True
    assert absent["survivors_on_any_shuffle"] == [], (
        "arms survive where the mechanism is ABSENT — the VACUOUS badge would then be "
        "SUBSTANTIVELY right and the ship verdict is not trustworthy")


@pytest.mark.skipif(not _RESULT.exists(), reason="decisive run artifact absent")
def test_the_invariance_declaration_is_reported_as_consistency_never_as_a_passed_check():
    """⚠️ A clause that PASSES at every rung has nowhere to move upward, so the ladder can only
    REFUTE the forward declaration, never confirm it (NF1.7 (a))."""
    lad = json.loads(_RESULT.read_text())["diagnostics"]["invariance_ladder"]
    assert lad["pre_registered"] is True and lad["gate"] is False
    assert lad["declaration_holds"] and not lad["declaration_refuted_for"]
    assert "not PROOF" in lad["reading"] and "only REFUTE" in lad["reading"]


@pytest.mark.skipif(not _PREREG.exists(), reason="prereg absent")
def test_the_preregistration_states_the_expected_result_forward():
    """⭐ Where a registration cannot protect against foreknowledge — every number was already
    public in NF-INJ4's record — the honest substitute is writing the expectation down where it can
    be checked against what happened."""
    # ⛔ the pre-registration is COMMITTED and must not be edited to satisfy a guard (E2.1-r).
    #    ⚠️ The document is HARD-WRAPPED, so a multi-word phrase straddles a newline and a naive
    #    substring scan misses it silently. Whitespace is normalised and case folded, so this pins
    #    the CLAIM rather than the document's line breaks or emphasis.
    txt = re.sub(r"\s+", " ", _PREREG.read_text()).lower()
    assert "already known" in txt and "only the gate flips" in txt
    assert "never to be presented as fresh confirmation" in txt
    assert "zero rows for 2026" in txt, (
        "the NF-W0a capture dependency must be stated with its MEASURED value at registration time")
