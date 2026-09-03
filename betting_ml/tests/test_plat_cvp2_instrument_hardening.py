"""PLAT-CVP2 — the four measured defects in the shared null-classification / positive-control
instrument, each guarded by the incident that measured it.

Two of the four are **verdict INVERSIONS** — the instrument returning the opposite of the truth with
no warning — which outranks a merely wrong verdict, because a wrong verdict is argued with and an
inverted one is believed.

  1. **NF-INJ2b D2** (PR #1051) — arms blocked SOLELY by a gate the injection structurally cannot
     move were reported `BLIND` ("a null from this family is free"), the opposite of the truth. The
     record had to carry a render-time "⛔ DO NOT READ THAT BADGE AT FACE VALUE".
  2. **MLB-TV2-2 finding 7** (`mlb_tv2_2_mixture_head.md` §17) — a caller whose clause names share
     ZERO overlap with the default deflation vocabulary had its deflation gate filed as a metric
     gate and got `BLIND` when the truth was `DEFLATION_BLOCKED`. Found by hand.
  3. **MLB-TV2-2 finding 2 / E7.14** (prereg §14.1) — a fold-sign floor ABOVE its own BH cutoff
     makes a multiplicity clause structurally unpassable by an effect of any size, and nothing had
     to consult the helpers that would have said so.
  4. **NF-INJ2c §6.3** — a floor census and the kernel that applies the floor read different
     predicates, so a non-finite row the kernel floors was invisible to the census.

⭐ **EVERY FIXTURE IS LOADED FROM THE COMMITTED RECORD, NEVER RETYPED** (PLAT-CVP1's discipline): a
transcribed blocking table is a restatement of what the author believed the run produced, and the
whole point is to drive the instrument with what it actually did produce.

⛔ **AND EVERY RECORDED VERDICT STILL REPRODUCES.** The defect-1 and defect-2 cases are guarded
TWO-SIDED: the historical call (no declaration / the caller's own corrected declaration) returns the
recorded verdict byte-identically, and only the NEW declared input changes the reading. History is
not recomputed, restated, or upgraded by this story (E2.1-r).
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import cv_power
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2_rate_permutation as RP

REPO = Path(__file__).resolve().parents[2]
INJ2B = REPO / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/nf_inj2b_rate_ordering.json"
TV2_2 = REPO / "ablation_results/mlb_tv2_2_mixture_head.json"
TV2_2_PREREG = REPO / "ablation_results/mlb_tv2_2_prereg.md"


def _record(path: Path) -> dict:
    if not path.exists():                      # pragma: no cover - the record is committed
        pytest.skip(f"no committed record at {path}")
    return json.loads(path.read_text())


def _replay(blocking: dict[str, list[str]], gate_names):
    """Replay a RECORDED per-arm blocking table as an `(inject, run_gates)` pair.

    The recorded table IS the gate function's output on the injected payload, so replaying it drives
    the control with the study's own measured gates rather than a re-implementation of them (the
    NF-C0e "a test that reads a value back under the key the code wrote" class). The null leg blocks
    everything, which is the recorded `null_control_survivors == []` in both records."""
    names = tuple(gate_names)

    def inject(effect: float) -> float:
        return float(effect)

    def run_gates(payload: float) -> dict[str, dict[str, bool]]:
        if float(payload) == 0.0:
            return {a: {g: False for g in names} for a in blocking}
        return {a: {g: g not in set(b) for g in names} for a, b in blocking.items()}

    return inject, run_gates


def _inj2b():
    pc = _record(INJ2B)["positive_control"]
    gates = sorted(set(pc["metric_gates"]) | set(pc["deflation_gates"]))
    return pc, _replay({a: list(b) for a, b in pc["blocking_gates"].items()}, gates)


def _tv2_2():
    d = _record(TV2_2)["cvp1"]
    det = d["detail"]
    gates = sorted(set(det["metric_gates"]) | set(det["deflation_gates"]))
    return d, det, _replay({a: list(b) for a, b in det["blocking_gates"].items()}, gates)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 1 — NF-INJ2b D2: BLIND on a gate the injection cannot move
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_defect1_the_recorded_blind_verdict_still_reproduces_without_a_declaration():
    """⛔ HISTORY FIRST. NF-INJ2b declared no invariant set, so its call must return exactly what it
    recorded — the fix is opt-in, and a fix that silently re-labels a recorded verdict would be the
    E2.1-r inversion wearing a repair's badge."""
    pc, (inject, run_gates) = _inj2b()
    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=0.05)
    assert rep.verdict == pc["verdict"] == "BLIND"
    assert rep.constraint_blocked == () and rep.invariant_gates == ()
    assert set(rep.deflation_gates) == set(pc["deflation_gates"]) == {"dsr"}


def test_defect1_the_declared_invariant_set_turns_that_same_table_into_CONSTRAINT_BLOCKED():
    """⭐ THE FIX, on the record that measured the defect.

    NF-INJ2b's annotation names the two arms and the gate: `stratified` and `feasibility_clamp` are
    "blocked under injection by it ALONE, with every metric gate AND `dsr` firing correctly". The
    instrument now says that itself, from the same table."""
    _, (inject, run_gates) = _inj2b()
    rep = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=0.05,
        invariant_gates=("coherence_restored",))
    assert rep.verdict == "CONSTRAINT_BLOCKED"
    assert set(rep.constraint_blocked) == {"stratified", "feasibility_clamp"}, (
        "the two arms NF-INJ2b's annotation names must be the two the instrument names")
    assert rep.invariant_gates == ("coherence_restored",)
    assert "coherence_restored" in rep.reason and "BLIND" in rep.reason, (
        "the verdict must NAME the invariant gate and say what it is not — a bare state swap "
        "leaves the next reader with the same question the annotation had to answer by hand")


def test_defect1_an_invariant_gate_is_neither_a_metric_detector_nor_a_deflation_statistic():
    """The three-class partition is the mechanism, and it is what makes `metric_survivors` mean
    "cleared every gate the injection could MOVE" rather than "cleared every gate not named in a
    deflation vocabulary"."""
    _, (inject, run_gates) = _inj2b()
    rep = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=0.05,
        invariant_gates=("coherence_restored",))
    assert "coherence_restored" not in rep.metric_gates
    assert "coherence_restored" not in rep.deflation_gates
    assert rep.gate_classes_resolved["coherence_restored"] == "invariant"
    assert rep.gate_classes_resolved["dsr"] == "deflation"
    assert rep.gate_classes_resolved["beats_incumbent"] == "metric"
    # `rate_refit` is blocked by {coherence_restored, dsr}: every MOVABLE metric gate fired, and a
    # deflation gate is among its blockers, so it is deflation-blocked and NOT constraint-blocked.
    assert "rate_refit" in rep.deflation_blocked and "rate_refit" not in rep.constraint_blocked


def test_defect1_BLIND_keeps_its_meaning_for_movable_gates_only():
    """Two-sided: with the SAME invariant declaration, a family whose movable metric gates genuinely
    fail is still BLIND — the new state must not swallow the one it was carved out of."""
    def run_gates(payload):
        fired = float(payload) != 0.0
        return {"arm": {"crps_lift": False, "dsr": fired, "coherence_restored": False}}

    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
        invariant_gates=("coherence_restored",))
    assert rep.verdict == "BLIND" and rep.constraint_blocked == ()
    assert "coherence_restored" in rep.reason, (
        "a BLIND verdict with invariant gates declared must say they were excluded from the "
        "reading, or the reader cannot tell WHICH half failed to fire")


def test_defect1_CONSTRAINT_BLOCKED_outranks_DEFLATION_BLOCKED_because_it_clears_strictly_more():
    """An arm stopped only by an invariant gate cleared its metric gates AND its deflation gates; an
    arm stopped by a deflation gate did not. The precedence is that containment, not a preference."""
    def run_gates(payload):
        fired = float(payload) != 0.0
        return {"constrained": {"m": fired, "dsr": fired, "coh": False},
                "deflated": {"m": fired, "dsr": False, "coh": True}}

    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
        invariant_gates=("coh",))
    assert rep.verdict == "CONSTRAINT_BLOCKED"
    assert rep.constraint_blocked == ("constrained",) and rep.deflation_blocked == ("deflated",)
    i = cv_power.POSITIVE_CONTROL_VERDICTS.index
    assert i("CONSTRAINT_BLOCKED") < i("DEFLATION_BLOCKED") < i("BLIND")


def test_defect1_a_surviving_arm_still_outranks_a_constraint_blocked_one():
    """DETECTED is not weakened by the new state: an arm that clears EVERYTHING, invariant gates
    included, is the strongest reading available and must still win."""
    def run_gates(payload):
        fired = float(payload) != 0.0
        return {"clean": {"m": fired, "coh": True}, "constrained": {"m": fired, "coh": False}}

    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
        invariant_gates=("coh",))
    assert rep.verdict == "DETECTED" and rep.survivors == ("clean",)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 2 — MLB-TV2-2 §17: the zero-intersection partition inversion
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_defect2_the_clause_names_that_inverted_the_verdict_now_report_UNVERIFIED():
    """⭐ THE INVERSION, REFUSED. TV2-2's clause names share ZERO overlap with the default
    vocabulary, so `C7_deflation` was filed as a METRIC gate and the verdict came back `BLIND` for a
    family whose metric gates fired on every arm. The two states a zero-overlap partition cannot
    tell apart lead to OPPOSITE readings, so it must not pick one (MH2.7's self-safe move)."""
    _, det, (inject, run_gates) = _tv2_2()
    assert not (set(det["metric_gates"]) | set(det["deflation_gates"])) & set(
        cv_power.DEFLATION_CLASS_GATES), "the fixture no longer has the zero overlap it exists for"

    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=1.5)
    assert rep.verdict == "UNVERIFIED"
    assert rep.partition_verified is False
    assert rep.verdict != "BLIND", "the inverted verdict is back"


def test_defect2_the_refusal_tells_the_caller_how_to_declare_its_gate_classes():
    """A refusal that does not say what to do instead is a wall. MH2.7's refusal names the input; so
    must this one, and it must name the gates it could not classify."""
    _, det, (inject, run_gates) = _tv2_2()
    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=1.5)
    assert "gate_classes=" in rep.reason
    assert "C7_deflation" in rep.reason, "the reason must list the gates it could not classify"
    for word in ("metric", "deflation", "invariant"):
        assert word in rep.reason


def test_defect2_TV2_2s_own_corrected_call_still_returns_its_recorded_verdict():
    """⛔ HISTORY. TV2-2 corrected this by hand by passing `deflation_gates={"C7_deflation"}`, and
    that call must be byte-identical after the fix — the record is the fixture, not a thing to
    re-run into a new answer."""
    d, det, (inject, run_gates) = _tv2_2()
    rep = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=1.5,
        deflation_gates=frozenset({"C7_deflation"}))
    assert rep.verdict == d["verdict"] == "DEFLATION_BLOCKED"
    assert set(rep.deflation_blocked) == set(det["deflation_blocked"])
    assert set(rep.metric_survivors) == set(det["metric_survivors"])
    assert list(rep.deflation_gates) == det["deflation_gates"] == ["C7_deflation"]
    assert rep.partition_verified is True and rep.partition_source == "declared_vocabulary"


def test_defect2_a_full_gate_class_declaration_reaches_the_same_reading():
    """The DURABLE half of the fix. `gate_classes` is the only input that can affirm "there is no
    deflation gate here", so it must be able to express what the vocabulary form expresses."""
    d, det, (inject, run_gates) = _tv2_2()
    gates = sorted(set(det["metric_gates"]) | set(det["deflation_gates"]))
    rep = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=1.5,
        gate_classes={g: ("deflation" if g == "C7_deflation" else "metric") for g in gates})
    assert rep.verdict == d["verdict"] == "DEFLATION_BLOCKED"
    assert rep.partition_source == "gate_classes" and rep.partition_verified is True


def test_defect2_a_declaration_of_no_deflation_gates_is_affirmative_and_is_honoured():
    """⭐ The state the heuristic CANNOT express, and the reason `gate_classes` is the durable half:
    a family with genuinely no deflation gate is a real design, and it must be able to say so and
    get BLIND rather than a refusal it can do nothing about."""
    def run_gates(payload):
        return {"arm": {"roi_positive": False, "coverage": False}}

    gc = {"roi_positive": "metric", "coverage": "metric"}
    rep = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
        gate_classes=gc)
    assert rep.verdict == "BLIND" and rep.partition_verified is True
    assert rep.deflation_gates == ()
    # …and WITHOUT the declaration the identical family is refused, because the instrument cannot
    # tell "no deflation gate" from "a deflation gate named something else".
    bare = cv_power.injected_effect_positive_control(
        inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False)
    assert bare.verdict == "UNVERIFIED"


def test_defect2_a_partially_declared_partition_is_refused_rather_than_completed():
    """A partial declaration reintroduces exactly the ambiguity it exists to remove — so it raises
    rather than filling the gap with the heuristic, which would be the defect wearing a
    declaration's badge."""
    def run_gates(payload):
        return {"arm": {"a": False, "b": False}}

    with pytest.raises(ValueError, match="PARTIALLY declared|does not classify"):
        cv_power.injected_effect_positive_control(
            inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
            gate_classes={"a": "metric"})
    with pytest.raises(ValueError, match="unknown class"):
        cv_power.injected_effect_positive_control(
            inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False,
            gate_classes={"a": "metric", "b": "deflation_class"})


def test_defect2_the_name_heuristic_survives_only_as_a_fallback_that_announces_itself():
    """It is still the default, because every existing caller relies on it — but a partition
    inferred from this repo's harness names is a fact about our naming, not about the caller's
    clauses, and a reader must be told which one they are looking at."""
    _, (inject, run_gates) = _inj2b()
    rep = cv_power.injected_effect_positive_control(inject=inject, run_gates=run_gates, effect=0.05)
    assert rep.partition_source == "name_heuristic"
    assert "PARTITION BY NAME HEURISTIC" in rep.reason
    assert "gate_classes=" in rep.reason

    declared = cv_power.injected_effect_positive_control(
        inject=inject, run_gates=run_gates, effect=0.05, deflation_gates=frozenset({"dsr"}))
    assert declared.partition_source == "declared_vocabulary"
    assert "PARTITION BY NAME HEURISTIC" not in declared.reason, (
        "a caller that declared its vocabulary must not be lectured about a heuristic it did not use")


def test_defect2_the_partition_free_verdicts_are_invariant_to_any_partition():
    """⭐ THE MEASURED EXEMPTION, and the reason it is safe.

    `VACUOUS` and `DETECTED` are returned even when the partition is UNVERIFIED. That is admissible
    only because both are computed from EMPTY blocking sets and cannot depend on the partition — so
    it is PROVEN here over every possible partition of the gate names rather than asserted in a
    docstring. Withholding "this family certifies noise" behind "I could not classify your gates"
    would suppress the control's most important finding to guard against an inversion that
    structurally cannot reach it."""
    import itertools

    for label, table in (
        ("vacuous", {"a": {"x": True, "y": True}}),          # survives the NULL leg too
        ("detected", None),
    ):
        if label == "vacuous":
            def run_gates(payload, t=table):
                return t
            rep_bare = cv_power.injected_effect_positive_control(
                inject=lambda e: e, run_gates=run_gates, effect=1.0)
            assert rep_bare.verdict == "VACUOUS"
        else:
            def run_gates(payload):
                fired = float(payload) != 0.0
                return {"a": {"x": fired, "y": fired}}
            rep_bare = cv_power.injected_effect_positive_control(
                inject=lambda e: e, run_gates=run_gates, effect=1.0)
            assert rep_bare.verdict == "DETECTED"

        # every assignment of the two gates to the three classes must give the SAME verdict
        for combo in itertools.product(cv_power.GATE_CLASSES, repeat=2):
            gc = dict(zip(("x", "y"), combo))
            rep = cv_power.injected_effect_positive_control(
                inject=lambda e: e, run_gates=run_gates, effect=1.0, gate_classes=gc)
            assert rep.verdict == rep_bare.verdict, (
                f"{label} moved under partition {gc} — it is NOT partition-free and the "
                f"UNVERIFIED exemption is unsafe")


def test_defect2_every_partition_dependent_verdict_is_withheld_when_unverified():
    """The other half of the exemption: nothing that READS the partition may be returned from an
    unverifiable one."""
    partition_dependent = {"CONSTRAINT_BLOCKED", "DEFLATION_BLOCKED", "BLIND"}
    assert partition_dependent < set(cv_power.POSITIVE_CONTROL_VERDICTS)
    for table in ({"a": {"C7_deflation": False, "C1": True}},
                  {"a": {"C7_deflation": False, "C1": False}},
                  {"a": {"C7_deflation": True, "C1": False}}):
        def run_gates(payload, t=table):
            return t
        rep = cv_power.injected_effect_positive_control(
            inject=lambda e: e, run_gates=run_gates, effect=1.0, check_null_control=False)
        assert rep.verdict not in partition_dependent, (
            f"{rep.verdict} was returned from an UNVERIFIED partition on {table}")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 3 — MLB-TV2-2 §14.1 / E7.14: the structurally unpassable multiplicity clause
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_defect3_TV2_2s_registered_five_fold_design_is_refused_with_the_arithmetic():
    """⭐ The design TV2-2 registered and had to amend. `N_BLOCKS = 5` against a 4-arm rank-1 BH
    cutoff of 0.0125 puts the sign floor at 0.03125 — 2.5x the cutoff — so C8 was unpassable by an
    effect of any size. It was caught by a vacuity control, by hand, AFTER registration."""
    with pytest.raises(ValueError) as e:
        cv_power.validate_sign_certifiability(n_folds=5, n_arms=4, alpha=0.05)
    msg = str(e.value)
    for token in ("0.03125", "0.01250", "2.50", "5 folds", "E7.14"):
        assert token in msg, f"the refusal must carry its arithmetic — {token!r} missing from {msg}"
    assert "7" in msg, "the refusal must name the smallest certifiable design"


def test_defect3_the_refusal_reproduces_the_preregs_own_recorded_numbers():
    """⛔ Not retyped: the prereg's §14.1 numbers are read out of the committed document and the
    instrument is required to agree with them."""
    if not TV2_2_PREREG.exists():                      # pragma: no cover - committed
        pytest.skip("no committed prereg")
    text = TV2_2_PREREG.read_text()
    assert "0.03125" in text and "0.0125" in text, "the prereg no longer carries §14.1's arithmetic"
    rep = cv_power.validate_sign_certifiability(n_folds=5, n_arms=4, alpha=0.05, strict=False)
    assert rep.sign_floor == pytest.approx(0.03125, abs=1e-9)
    assert rep.bh_cutoff == pytest.approx(0.0125, abs=1e-9)
    assert rep.certifiable is False
    assert rep.folds_needed == cv_power.folds_for_sign_certifiability(0.0125) == 7
    # the amended design, and the forward-stated margin rule that produced it
    ok = cv_power.validate_sign_certifiability(n_folds=8, n_arms=4, alpha=0.05)
    assert ok.certifiable is True
    assert ok.sign_floor == pytest.approx(0.00390625, abs=1e-9)
    assert f"{ok.sign_floor:.4f}" in text, (
        "the prereg quotes the amended design's floor and the instrument must agree with it")
    seven = cv_power.validate_sign_certifiability(n_folds=7, n_arms=4, alpha=0.05)
    assert seven.certifiable is True and seven.headroom == pytest.approx(0.625, abs=1e-9), (
        "the prereg records n=7 as clearing with NO margin (0.62 of the cutoff)")
    assert "NO MARGIN" in seven.reason


def test_defect3_it_refuses_to_invent_the_bar_it_is_checking_against():
    """MH2.7's shape: an instrument that defaulted the cutoff would be choosing a caller's
    registration for it, and the resulting pass would mean nothing."""
    with pytest.raises(ValueError, match="needs the bar"):
        cv_power.validate_sign_certifiability(n_folds=5)


def test_defect3_strict_false_reports_instead_of_raising_for_a_caller_choosing_a_design():
    """The inspection path — used to CHOOSE `n_folds`, never to score with one."""
    rep = cv_power.validate_sign_certifiability(n_folds=5, bh_cutoff=0.0125, strict=False)
    assert rep.certifiable is False and "REFUSED" in rep.reason
    assert isinstance(rep, cv_power.SignCertifiability)


def test_defect3_the_two_sided_floor_reproduces_E7_14s_own_recorded_design():
    """E7.14: cutoff 0.010 two-sided => 8 seasons, which is what it reported. The helper already
    said so; nothing had to ask it, which is the defect this closes."""
    assert cv_power.folds_for_sign_certifiability(0.010, two_sided=True) == 8
    with pytest.raises(ValueError, match="REFUSED"):
        cv_power.validate_sign_certifiability(n_folds=5, bh_cutoff=0.010, two_sided=True)
    ok = cv_power.validate_sign_certifiability(n_folds=8, bh_cutoff=0.010, two_sided=True)
    assert ok.certifiable is True


def test_defect3_a_certifiable_design_passes_two_sided():
    """The guard must not simply refuse everything: a design with real margin passes and says so."""
    rep = cv_power.validate_sign_certifiability(n_folds=11, n_arms=4, alpha=0.05)
    assert rep.certifiable is True and "CERTIFIABLE" in rep.reason
    assert "NO MARGIN" not in rep.reason and rep.headroom < 0.5


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# DEFECT 4 — NF-INJ2c §6.3: one floor predicate, one owner, both readers
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_defect4_the_census_now_sees_the_non_finite_row_the_kernel_floors():
    """The census used to require `isfinite(g)` while the kernel floored a non-finite row anyway, so
    "the floor is inert" could be read off a count blind to one of the two ways the floor acts."""
    assert RP.games_floor_binding([5.0, float("nan"), 12.0]) == 1
    assert RP.games_floor_binding([float("inf"), 3.0]) == 1
    assert RP.games_floor_binding([0.1, 5.0]) == 1            # the pre-existing recorded case
    assert RP.games_floor_binding([0.81, 3.0, 17.0]) == 0     # a healthy column is still inert


def test_defect4_the_census_and_the_kernel_read_the_same_predicate_on_every_row_shape():
    """⭐ The property, not the instance: driven over the shapes that separated the two definitions
    (non-finite, the exact boundary, negative, zero) rather than over one hand-picked row."""
    F = RP.GAMES_FLOOR
    g = np.array([5.0, np.nan, np.inf, -np.inf, F, F - 1e-12, F + 1e-12, 0.1, 12.0, -3.0, 0.0])
    mask = RP.games_floored_mask(g)
    moved = np.where(np.isfinite(g), np.where(mask, F, g) != g, True)
    assert np.array_equal(mask, moved), (
        "the mask and 'the divisor actually moved' disagree — they are two predicates again")
    assert RP.games_floor_binding(g) == int(mask.sum()) == int(moved.sum())


def test_defect4_repointing_the_kernel_left_every_divisor_bit_identical():
    """The fix's SAFETY claim, MEASURED. `np.where(mask, FLOOR, g)` and the retired
    `np.where(isfinite(g) & (g > FLOOR), g, FLOOR)` agree on every input — at `g == FLOOR` the
    retired form took its substitution branch and substituted `FLOOR`, which the row already held."""
    F = RP.GAMES_FLOOR
    g = np.array([5.0, np.nan, np.inf, -np.inf, F, F - 1e-12, F + 1e-12, 0.1, 12.0, -3.0, 0.0])
    retired = np.where(np.isfinite(g) & (g > F), g, F)
    shipped = np.where(RP.games_floored_mask(g), F, g)
    assert np.array_equal(retired, shipped, equal_nan=True)


def test_defect4_the_boundary_row_is_still_a_no_op_by_value_which_is_NF_INJ2cs_choice():
    """⛔ NOT re-decided by this story. NF-INJ2c chose to count by VALUE ("did the divisor change?")
    rather than by BRANCH ("was the substitution taken?"), with its reason recorded: a row at
    exactly the floor takes the branch and is substituted with the value it already had, so it
    cannot make the assignment and the check disagree. The shared predicate keeps that choice."""
    assert RP.games_floor_binding([RP.GAMES_FLOOR, 9.0]) == 0
    assert not RP.games_floored_mask([RP.GAMES_FLOOR])[0]


def test_defect4_the_kernel_has_no_second_floor_predicate_left_in_it():
    """The one-owner half. A re-implementation is how the two drifted apart in the first place, so
    the source must not carry another copy of the predicate (MH2.7: a defect corrected N times
    downstream is a defect in the instrument)."""
    src = inspect.getsource(RP)
    # ⚠️ COMMENT-STRIPPED, and only comment-stripped. The kernel's own comment quotes the retired
    # predicate verbatim to record what it replaced, so an unstripped scan reports a false positive
    # (INC-38: prose must not be able to satisfy — or here, to TRIP — a source guard). An earlier
    # cut of this clause dropped every line containing `GAMES_FLOOR)`, which is the token being
    # searched for, so it could never fire at all — the NF1.7 (a) vacuity, inside its own guard.
    body = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert "isfinite(g) & (g > GAMES_FLOOR)" not in body, (
        "a second copy of the floor predicate is back in the owner module — the census and the "
        "kernel can drift apart again, which is PLAT-CVP2 defect 4")
    assert src.count("def games_floored_mask") == 1
    # and the guard is not vacuous: the retired predicate IS still present in the comment that
    # records it, so a scan that failed to strip comments would fire here.
    assert "isfinite(g) & (g > GAMES_FLOOR)" in src, (
        "the kernel no longer records what predicate it replaced — this clause is now unfalsifiable")


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# The instrument's standing contract
# ══════════════════════════════════════════════════════════════════════════════════════════════════
def test_the_new_states_are_declared_and_exported():
    assert "CONSTRAINT_BLOCKED" in cv_power.POSITIVE_CONTROL_VERDICTS
    assert "UNVERIFIED" in cv_power.POSITIVE_CONTROL_VERDICTS
    assert cv_power.GATE_CLASSES == ("metric", "deflation", "invariant")
    # ⭐ ORDER-PINNED, because the module UNPACKS this tuple positionally: a reorder would silently
    # relabel every report's `partition_source` (E11.29's dead-constant guard forced the reference;
    # this is the other half — a referenced constant that can still be reordered underneath it).
    assert cv_power.GATE_PARTITION_SOURCES == (
        "gate_classes", "declared_vocabulary", "name_heuristic")
    for name in ("GATE_CLASSES", "GATE_PARTITION_SOURCES", "SignCertifiability",
                 "validate_sign_certifiability"):
        assert name in cv_power.__all__, f"{name} is not exported"


def test_the_control_docstring_cites_all_four_incident_records():
    """The retirement note. The annotate-around rule retires for FUTURE callers, and a reader who
    meets the new states needs the four incidents that produced them (MH2.7's convention)."""
    doc = cv_power.injected_effect_positive_control.__doc__ or ""
    for citation in ("NF-INJ2b D2", "MLB-TV2-2 finding 7", "MLB-TV2-2 finding 2", "NF-INJ2c"):
        assert citation in doc, f"the docstring no longer cites {citation}"
    assert "E7.14" in doc and "PR #1051" in doc
    assert "ANNOTATE-AROUND RULE RETIRES" in doc.upper()
    assert "are NOT edited" in doc, (
        "the note must say the records are the fixtures and are not edited (E2.1-r)")


def test_every_pre_existing_caller_keeps_its_behaviour_without_the_new_inputs():
    """⭐ BACK-COMPAT BY CONSTRUCTION, measured. Every new input defaults to None/absent, so a call
    written before this story returns what it returned before — which is why the cross-vertical
    sweep moved only the pins where the defects lived."""
    sig = inspect.signature(cv_power.injected_effect_positive_control).parameters
    for new in ("gate_classes", "invariant_gates"):
        assert sig[new].default is None, f"{new} must default to None or it is not opt-in"
    assert sig["deflation_gates"].default is None, (
        "the vocabulary default is None so the instrument can tell a DECLARED vocabulary from the "
        "shipped one; the shipped set itself is `DEFLATION_CLASS_GATES` and has not moved")
    assert set(cv_power.DEFLATION_CLASS_GATES) == {"pbo", "cscv", "dsr", "deflated_sharpe"}
