"""NF-INJ2c node 4 — guards for the decisive run.

⛔ These certify no verdict. They pin that the runner COMPUTES what `nf_inj2c_preregistration.md`
and `nf_inj2c_margin_construction_rule.md` (node 3a, BINDING) declare, and that it cannot reach a
dominance claim by a route those documents forbid:

  · the primary arm is FIXED by the registration and is ⛔ never selected as "the best CRPS";
  · M3, M4 and M2's BASELINE are READ from node 3b, ⛔ never recomputed, and a failed pin is VOID;
  · every band is one of node 3a's three rules, and ⛔ none is derived from an observed gap;
  · an UNEVALUABLE measure is ⛔ never a pass, and one regression is a NULL;
  · the BINDING deflation field is the declared five, the inherited ten is NON-BINDING, and there
    is ⛔ no third field;
  · the field-trim 2x2 is STRUCTURALLY UNAVAILABLE at two V members, stated a fortiori;
  · the calendar-bound fold trigger is WITHHELD when SR <= SR0.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from betting_ml.utils import coverage_power_floor as CPF
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2b_rate_ordering as B
from quant_sports_intel_models.football.nfl.fantasy import nf_inj2c_assignment_rule as C
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2b_rate_ordering as RB
from quant_sports_intel_models.football.nfl.fantasy import run_nf_inj2c_decisive as D

_RUNNER = Path(D.__file__)
_REG = Path(C.__file__)
_POS = ("QB", "RB", "WR", "TE")


def _strip_comments(src: str) -> str:
    """INC-38: a source-inspection guard that PROSE can satisfy is not a guard."""
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("#"))


def _flat(text: str) -> str:
    """Markdown wraps a sentence across lines, so a raw substring check on prose is a coin flip on
    where the author's editor broke the line — not on what the document says."""
    return " ".join(text.split())


def _stub(monkeypatch, **fields):
    """Stub `cv_power.injected_effect_positive_control` with a report carrying EVERY field the
    reader unpacks — so a field the instrument adds later fails loudly here rather than silently
    vanishing from the record."""
    base = {"verdict": "BLIND", "reason": "", "effect": 0.75, "survivors": [],
            "metric_survivors": [], "deflation_blocked": [], "deflation_gates": [],
            "metric_gates": [], "blocking_gates": {}, "field_level_gates_applied_per_arm": [],
            "null_control_checked": True, "null_control_survivors": []}
    base.update(fields)
    monkeypatch.setattr(RB, "build_payload", lambda *a, **k: {})
    monkeypatch.setattr(RB, "make_injector",
                        lambda p, field=None: (lambda e: {}))
    monkeypatch.setattr(D.cv_power, "injected_effect_positive_control",
                        lambda **k: type("R", (), base)())


def _pf(*, arm_crps, inc_crps, arm_viol, inc_viol, null_viol=0, arm_rho=0.55, inc_rho=0.50,
        cov=0.81, n_group=60, folds=(2019, 2020, 2021, 2022, 2023, 2024, 2025)):
    """A per-fold frame carrying only what the measures read. Every arm is scored by the SAME
    shape, so an anchor and a candidate cannot answer different questions."""
    out: dict = {}
    spec = {"stratified": (arm_crps, arm_viol, arm_rho), C.INCUMBENT_ARM: (inc_crps, inc_viol,
                                                                           inc_rho),
            "mvp1_null": (inc_crps, null_viol, inc_rho)}
    for a, (crps, viol, rho) in spec.items():
        out[a] = {}
        for j, y in enumerate(folds):
            out[a][y] = {
                "crps": (crps[j] if isinstance(crps, (list, tuple)) else crps),
                "coherence_violating_players": (viol[j] if isinstance(viol, (list, tuple)) else viol),
                "tier_rho_by_position": {p: (rho[j] if isinstance(rho, (list, tuple)) else rho)
                                         for p in _POS},
                "coverage80_by_position": {p: cov for p in _POS},
                "coverage_n_by_position": {p: n_group for p in _POS},
                "n": 400,
            }
    return out, folds


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registration transcribes the documents
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheRegistration:

    def test_the_binding_field_is_the_declared_five(self):
        assert C.ARMS == ("incumbent", "stratified", "feasibility_clamp", "mvp1_null",
                          "random_order")
        assert C.DECLARED_FIELD_SIZE == 5

    def test_V_has_exactly_two_members_as_section_2_3a_declares(self):
        """⭐ §2.3(a) reasons about a 1-df variance estimate. If `V` ever stops being two members,
        the declared fragility no longer describes the design being run.

        ⚠️ This asserts the DATA. It does NOT test that `assert_coherent` enforces it — the two are
        different claims, and an earlier cut had only this one, so deleting the enforcing clause
        left the guard green (the RED proof caught it). The enforcement is tested below."""
        v = [a for a in C.ARMS if a not in set(C.DEGENERATE_ARMS) | set(C.REFERENCE_ARMS)]
        assert v == ["stratified", "feasibility_clamp"]

    def test_assert_coherent_REFUSES_a_field_whose_V_is_not_two_members(self, monkeypatch):
        """The ENFORCEMENT half. A field with three contenders would make §2.3(a)'s reasoning — and
        §2.3(b)'s structural-unavailability argument — describe a design nobody is running."""
        monkeypatch.setattr(C, "ARMS", ("incumbent", "stratified", "feasibility_clamp",
                                        "points_rate_permute", "mvp1_null", "random_order"))
        monkeypatch.setattr(C, "DECLARED_FIELD_SIZE", 6)
        monkeypatch.setattr(C, "EXCLUDED_RATE_SPACE_ARMS",
                            ("rate_refit", "points_rate_stratified", "rate_refit_stratified",
                             "rate_refit_reselect"))
        with pytest.raises(RuntimeError, match="declares exactly two"):
            C.assert_coherent()

    def test_the_exclusions_account_for_every_inherited_arm_exactly_once(self):
        """Nothing quietly dropped, nothing invented — the exclusion is auditable against the
        inherited field rather than asserted."""
        assert set(C.ARMS) | set(C.EXCLUDED_RATE_SPACE_ARMS) == set(B.ARMS)
        assert not set(C.ARMS) & set(C.EXCLUDED_RATE_SPACE_ARMS)

    def test_the_primary_arm_is_stratified_and_is_not_a_degenerate(self):
        assert C.PRIMARY_ARM == "stratified"
        assert C.PRIMARY_ARM not in C.DEGENERATE_ARMS and C.PRIMARY_ARM not in C.REFERENCE_ARMS

    def test_the_registration_declares_no_served_arm(self):
        """⛔ A third owner for one logical thing is the INC-30 / INC-36 / INC-38 class."""
        assert not hasattr(C, "SERVED_ARM")
        assert C.resolve_served_arm() == B.resolve_served_arm()

    def test_assert_coherent_runs_at_import(self):
        src = _strip_comments(_REG.read_text())
        assert re.search(r"^assert_coherent\(\)\s*$", src, re.M), (
            "the registration's own consistency check is no longer invoked at import, so a state "
            "the documents do not support would ship rather than failing the process (NF-C0e)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The primary arm is FIXED — ⛔ never selected
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePrimaryArmIsNotSelected:

    def test_the_runner_reads_the_registered_arm_and_never_argmins_crps(self):
        """⭐ Choosing the arm after seeing the scores is the E2.1-r inversion in the one place a
        DOMINANCE claim is most exposed to it. NF-INJ2b legitimately picks a CRPS winner; this story
        may not, because its disposition names the arm in advance."""
        src = _strip_comments(_RUNNER.read_text())
        assert "arm = C.PRIMARY_ARM" in src, "the run no longer takes its arm from the registration"
        for forbidden in ("min(cands", "min(candidates", "key=lambda a: (scored[a]"):
            assert forbidden not in src, (
                f"{forbidden!r} selects an arm from the scores — this story's arm is REGISTERED")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M3 / M4 / M2's baseline are READ from node 3b, and a failed pin is VOID
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheBoardMeasuresAreRead:

    def test_an_absent_node_3b_report_REFUSES_and_names_the_command(self, tmp_path):
        with pytest.raises(SystemExit) as e:
            D.board_measures(tmp_path / "nope.json")
        msg = str(e.value)
        assert "never recomputed" in msg and "run_nf_inj2c_dominance_baseline" in msg, (
            "a refusal that does not name its own remedy is why the precondition exists at all")

    def test_a_failed_reproduction_pin_is_VOID_not_a_null(self, tmp_path):
        """node 3a §5 branch 3: a dominance claim against a board nobody is served is not a
        measurement — and VOID and NULL are different findings."""
        p = tmp_path / "b.json"
        p.write_text(json.dumps({"application_2026": {"reproduction_pin": {
            "reproduces": False, "worst_abs_diff": 1.82, "n": 797, "tolerance": 0.05}},
            "dominance": {"arms": {"stratified": {}}}}))
        with pytest.raises(SystemExit) as e:
            D.board_measures(p)
        assert "VOID, not a null" in str(e.value)

    def test_a_report_with_no_dominance_table_REFUSES(self, tmp_path):
        p = tmp_path / "b.json"
        p.write_text(json.dumps({"application_2026": {"reproduction_pin": {"reproduces": True}},
                                 "dominance": {}}))
        with pytest.raises(SystemExit) as e:
            D.board_measures(p)
        assert "never computed" in str(e.value)

    def test_M3_and_M4_are_read_from_the_report_not_recomputed(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def _board_measure(", 1)[1].split("\ndef ", 1)[0]
        # ⛔ the RAW SOURCES a recomputation would need. The DERIVED key names ("M3_worst_times_over")
        # legitimately appear — they are what is READ — so forbidding those would fail on the
        # correct implementation. This forbids the INPUTS, which is the thing that distinguishes
        # reading a committed baseline from computing a second one.
        for forbidden in ("worst_violations", "injury_giveback", "implied_per_game",
                          "max_ever_per_game", "mvp1_total", "arm_total"):
            assert forbidden not in body, (
                f"{forbidden!r} — a RAW board input — appears in the board-measure reader. M3/M4 are "
                "READ from node 3b; a second computation of a committed baseline is a second answer "
                "to one question, and the two would drift (E9.61)")

    def test_a_missing_board_figure_is_UNEVALUABLE_never_a_pass(self):
        board = {"arms": {"stratified": {}}, "served_incumbent_baseline": {}}
        for k in ("M3", "M4"):
            r = D._board_measure(board, "stratified", k)
            assert r["evaluable"] is False and r["verdict"] != "IMPROVES" if "verdict" in r else True


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The bands are node 3a's, and none is derived from an observed gap
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheBands:

    def test_M1s_band_is_the_per_fold_SE_of_its_own_lift_series(self):
        pf, folds = _pf(arm_crps=[9.0, 9.4, 9.1, 9.5, 9.2, 9.3, 9.6],
                        inc_crps=10.0, arm_viol=2, inc_viol=4)
        r = D.m1_crps_lift(pf, folds, "stratified")
        lifts = np.asarray([10.0 - c for c in [9.0, 9.4, 9.1, 9.5, 9.2, 9.3, 9.6]])
        assert r["tie_band"] == pytest.approx(lifts.std(ddof=1) / np.sqrt(len(lifts)), abs=1e-4)
        assert r["band_rule"] == "R1"

    def test_M3_and_M4_bands_are_the_RECORDED_PRECISION_and_nothing_else(self):
        board = D.board_measures()
        assert D._board_measure(board, "stratified", "M3")["tie_band"] == C.M3_RECORDED_PRECISION
        assert D._board_measure(board, "stratified", "M4")["tie_band"] == C.M4_RECORDED_PRECISION

    def test_a_single_fold_cannot_form_an_R1_band_and_is_UNEVALUABLE(self):
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, folds=(2019,))
        assert D.m1_crps_lift(pf, folds, "stratified")["evaluable"] is False

    def test_no_band_is_derived_from_an_observed_gap(self):
        """node 3a §1: ⛔ no band may be derived from an observed arm-vs-incumbent gap. The R1 band
        must read the DISPERSION of the series, never its mean."""
        src = _strip_comments(_RUNNER.read_text())
        for fn in ("def m1_crps_lift(", "def m2_coherence("):
            body = src.split(fn, 1)[1].split("\ndef ", 1)[0]
            band_line = [ln for ln in body.splitlines() if "band = " in ln]
            assert band_line, f"{fn} no longer computes a band"
            assert all("std(ddof=1)" in ln for ln in band_line), (
                f"{fn}'s band is not a standard error of its own series")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M2 — attribution-controlled, with a FOLD band
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestM2:

    def test_violations_the_control_also_produces_are_subtracted(self):
        """3a §3(b): a defect present with the ordering step OFF is not caused by it.

        ⭐ THE FIXTURE MUST MAKE THE CLAUSE OBSERVABLE (NF-D17). An earlier cut used
        arm = incumbent = control = 5, where the controlled reading (0) and the UNCONTROLLED one
        (5 − 5 = 0) are IDENTICAL — so the guard stayed green with the control deleted, and the RED
        proof caught it. Here arm=8, incumbent=6, control=7 ⇒ controlled +1, uncontrolled +2, so
        only the control's presence can produce the asserted number."""
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=8, inc_viol=6, null_viol=7)
        r = D.m2_coherence(pf, folds, "stratified", board)
        assert r["mean_paired_diff_vs_incumbent"] == pytest.approx(1.0), (
            "the attributable difference is max(8−7,0) − max(6−7,0) = 1; an UNCONTROLLED reading "
            "would be 8 − 6 = 2")
        assert r["control_inert"] is False

    def test_the_inert_control_is_STATED_not_discovered(self):
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, null_viol=0)
        assert D.m2_coherence(pf, folds, "stratified", board)["control_inert"] is True

    def test_the_board_reading_is_carried_as_the_BASELINE_not_the_verdict(self):
        board = D.board_measures()
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4)
        r = D.m2_coherence(pf, folds, "stratified", board)
        blk = r["board_baseline_from_node_3b"]
        assert blk["incumbent_attributable"] == 10 and blk["arm_attributable"] == 6
        assert "authoritative M2 verdict is this run's" in blk["note"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# M6 — pooled over ROWS, against a POWER floor
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestM6:

    def test_coverage_is_pooled_over_ROWS_not_averaged_over_folds(self):
        """NF1.8: a mean of per-fold rates re-weights a thin fold equal to a fat one."""
        folds = (2019, 2020)
        pf = {"stratified": {
            2019: {"coverage80_by_position": {"QB": 1.0}, "coverage_n_by_position": {"QB": 10}},
            2020: {"coverage80_by_position": {"QB": 0.5}, "coverage_n_by_position": {"QB": 190}}}}
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        assert g["n_rows"] == 200
        assert g["coverage"] == pytest.approx((10 * 1.0 + 190 * 0.5) / 200, abs=1e-6)
        assert g["coverage"] != pytest.approx(0.75, abs=1e-6), "that would be the mean-of-means"

    def test_the_floor_is_DERIVED_from_n_and_is_below_nominal(self):
        """⛔ NF-D22: a flat point-floor at nominal is a ~50% coin flip on a perfectly calibrated
        band at ANY n, and does not improve with n."""
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, n_group=60)
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        # rendered and compared at the SAME precision, so the table and the gate cannot disagree
        # about one number (E9.61) — the guard reads it the way the verdict does.
        assert g["power_floor"] == pytest.approx(
            round(CPF.power_floor(g["n_rows"], nominal=D.NOMINAL_COVERAGE), 4), abs=1e-12)
        assert g["power_floor"] < D.NOMINAL_COVERAGE

    def test_a_materially_short_band_still_FAILS(self):
        """The two-sided half: a floor that nothing can fail is not a floor (NF-D22)."""
        pf, folds = _pf(arm_crps=9.0, inc_crps=10.0, arm_viol=2, inc_viol=4, cov=0.55)
        r = D.m6_interval_floor(pf, folds, "stratified")
        assert r["verdict"] == "REGRESSES" and set(r["groups_below_floor"]) == set(_POS)

    def test_a_group_with_no_scored_interval_is_UNEVALUABLE_never_clearing(self):
        folds = (2019,)
        pf = {"stratified": {2019: {"coverage80_by_position": {},
                                    "coverage_n_by_position": {}}}}
        g = D.m6_interval_floor(pf, folds, "stratified")["groups"]["QB"]
        assert g["evaluable"] is False and "clears" not in g


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The dominance rule
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDominance:

    def _m(self, **over):
        base = {"M1": {"verdict": "IMPROVES"}, "M2": {"verdict": "TIES"},
                "M3": {"verdict": "IMPROVES"}, "M4": {"verdict": "IMPROVES"},
                "M5": {"verdict": "TIES_OR_BETTER"}, "M6": {"verdict": "CLEARS"}}
        base.update({k: {"verdict": v} for k, v in over.items()})
        return base

    def test_improve_or_tie_everywhere_DOMINATES(self):
        assert D.dominance_verdict(self._m())["state"] == "DOMINATES"

    @pytest.mark.parametrize("m", ["M1", "M2", "M3", "M4"])
    def test_one_regression_beyond_its_band_is_a_REGRESSION(self, m):
        v = D.dominance_verdict(self._m(**{m: "REGRESSES"}))
        assert v["state"] == "REGRESSES" and v["regressed_measures"] == [m]

    def test_an_ordering_regression_is_a_REGRESSION(self):
        assert D.dominance_verdict(self._m(M5="REGRESSES"))["state"] == "REGRESSES"

    def test_a_group_below_its_interval_floor_is_a_REGRESSION(self):
        assert D.dominance_verdict(self._m(M6="REGRESSES"))["state"] == "REGRESSES"

    @pytest.mark.parametrize("m", ["M1", "M2", "M3", "M4", "M5", "M6"])
    def test_an_UNEVALUABLE_measure_is_NEVER_a_pass(self, m):
        """⭐ NF1.7 (a). A dominance claim missing a measure is not a dominance claim."""
        v = D.dominance_verdict(self._m(**{m: "UNEVALUABLE"}))
        assert v["state"] == "UNEVALUABLE" and m in v["unevaluable_measures"]

    def test_a_missing_measure_is_NEVER_a_pass(self):
        m = self._m()
        del m["M6"]
        assert D.dominance_verdict(m)["state"] == "UNEVALUABLE"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The verdict's pre-committed branches
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheVerdict:

    def _defl(self, dsr=0.99, pbo=0.05):
        return {"binding": {"dsr_binding": dsr, "dsr_min": 0.95, "pbo": pbo, "pbo_max": 0.2,
                            "trial_sharpes": {}, "v_members": []},
                "lockstep_variance_lever": {"field_trim_status": D._FIELD_TRIM_STATUS}}

    def test_dominance_plus_clear_gates_is_DOMINATES(self):
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(),
                      control_binding={"state": "PASSES"},
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "DOMINATES" and v["deploy_held"] is True and v["best_alpha"] == 0

    def test_a_regression_is_a_NULL_even_when_every_gate_passes(self):
        """PM ruling 3, verbatim: 'that is a NULL, not a margin to adjust.'"""
        v = D.verdict(dominance={"state": "REGRESSES"}, defl=self._defl(),
                      control_binding={"state": "PASSES"},
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "NULL"

    def test_dominance_with_a_failing_DSR_is_DEFLATION_REFUSED(self):
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(dsr=0.40),
                      control_binding={"state": "PASSES"},
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "DEFLATION_REFUSED" and v["gates_failed"] == ["dsr"]

    def test_an_UNCOMPUTABLE_gate_is_UNDEFINED_never_FAILED(self):
        """MH2: a statistic that could not be computed is UNDEFINED, ⛔ never a failure."""
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(dsr=None),
                      control_binding={"state": "PASSES"},
                      control={}, fold_wins=7, folds=7)
        assert v["state"] == "UNEVALUABLE" and v["gates_undefined"] == ["dsr"]

    def test_the_fold_consistency_clause_is_the_CALIBRATED_one(self):
        """⛔ Never the raw 0.60 rate (MH2 H8) — at seven folds the calibrated clause needs 6."""
        v = D.verdict(dominance={"state": "DOMINATES"}, defl=self._defl(),
                      control_binding={"state": "PASSES"},
                      control={}, fold_wins=5, folds=7)
        assert v["fold_consistency_required_wins"] == 6
        assert v["state"] == "DEFLATION_REFUSED" and "fold_consistency" in v["gates_failed"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The deflation fields
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheFields:

    def test_the_binding_field_is_the_five_and_the_diagnostic_is_the_inherited_ten(self):
        assert D.BINDING_FIELD.arms == tuple(C.ARMS)
        assert D.BINDING_FIELD.declared_field_size == 5
        assert D.DIAGNOSTIC_FIELD.arms == tuple(B.ARMS)
        assert D.DIAGNOSTIC_FIELD is RB.NF_INJ2B_FIELD

    def test_there_is_no_THIRD_field(self):
        """The PM's ruling permits exactly two and forbids a third."""
        src = _strip_comments(_RUNNER.read_text())
        assert len(re.findall(r"RB\.FieldSpec\(", src)) == 1, (
            "more than one FieldSpec is constructed here — the ruling permits the BINDING field and "
            "the inherited DIAGNOSTIC one, and forbids a third")

    def test_the_field_trim_2x2_is_STRUCTURALLY_UNAVAILABLE_at_two_V_members(self):
        """§2.3(b): with two contributors the only drops are the arm under test (inadmissible,
        NF-W7h) or the sole other contributor (leaving `V` undefined)."""
        srs = {"stratified": 1.2, "feasibility_clamp": 0.4,
               "incumbent": 0.0, "mvp1_null": -2.0, "random_order": -3.0}
        out = RB._dsr_2x2(np.asarray([0.1] * 7), srs, "stratified", D.BINDING_FIELD)
        assert out["evaluable"] is False and out["structurally_unavailable"] is True
        assert out["v_member_count"] == 2 and "a fortiori" in out["why"]

    def test_the_declared_v_exclusion_drops_the_degenerates_AND_the_reference(self):
        srs = {a: float(i) for i, a in enumerate(C.ARMS)}
        members = RB._v_members(srs, D.BINDING_FIELD)
        assert set(members) == {"stratified", "feasibility_clamp"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The lockstep lever and the calendar-bound trigger
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheLockstepLever:

    def test_the_trigger_is_WITHHELD_when_SR_does_not_exceed_SR0(self):
        """⭐ NF-W8-0d: `n` enters through √(n−1), which scales a positive gap but cannot CREATE
        one. Publishing a fold trigger there is the NF-D18 misleading direction."""
        binding = {"trial_sharpes": {"stratified": 0.05, "feasibility_clamp": -3.0},
                   "v_members": ["stratified", "feasibility_clamp"]}
        out = D._lockstep(np.asarray([0.01, -0.02, 0.005, 0.0, 0.01, -0.01, 0.002]), binding)
        assert out["evaluable"] is True
        assert out["sr_gt_sr0"] is False and out["fold_trigger_publishable"] is False
        assert "never published" in out["why"]

    def test_an_unevaluable_lever_is_not_a_pass_and_still_names_the_trim_status(self):
        out = D._lockstep(np.asarray([0.1]), {"trial_sharpes": {}, "v_members": []})
        assert out["evaluable"] is False and "STRUCTURALLY UNAVAILABLE" in out["field_trim_status"]

    def test_the_lever_runs_BEFORE_any_remedy_is_named(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def deflation_blocks(", 1)[1].split("\ndef ", 1)[0]
        assert "_lockstep(" in body, "the lever is no longer computed with the deflation block"
        for prescribed in ("more seasons", "more rows", "more draws", "lower-variance design"):
            assert prescribed not in body.lower(), (
                f"a remedy ({prescribed!r}) is named in the deflation block — the lever is what "
                "decides whether any such remedy exists (NF-W8-0d)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The positive control's declared partition
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestThePositiveControlPartition:

    def test_the_two_halves_are_disjoint_and_the_sensitive_half_is_non_empty(self):
        assert not set(C.INJECTION_SENSITIVE_GATES) & set(C.INJECTION_INVARIANT_GATES)
        assert C.INJECTION_SENSITIVE_GATES, "a control evaluated over nothing is a vacuous pass"

    def test_the_board_measures_are_declared_INJECTION_INVARIANT(self):
        """An injected CRPS effect cannot reach a property of a board."""
        for g in ("m2_coherence", "m3_worst_times_over", "m4_giveback", "m6_interval_floor"):
            assert g in C.INJECTION_INVARIANT_GATES


class TestASmokeCannotClobberTheDecisiveRecord:
    """NF-INJ3b-M D4 / NF-W2c-CBS: a runner with a fixed output path overwrites a DECIDED story's
    artifact on any partial re-run. The decided stem must be reachable ONLY by the registered folds."""

    def test_a_non_registered_fold_set_writes_its_own_stem(self):
        src = _strip_comments(_RUNNER.read_text())
        body = src.split("def main(", 1)[1]
        assert "smoke = tuple(folds) != tuple(C.FOLDS)" in body
        assert 'stem = f"{_STEM}_smoke" if smoke else _STEM' in body
        assert f'{{stem}}.json' in body and f'{{stem}}.md' in body, (
            "the report is still written to a FIXED stem — a smoke would clobber the decisive record")

    def test_the_smoke_stem_is_gitignored(self):
        ignored = [ln.strip() for ln in (Path(__file__).resolve().parents[2] / ".gitignore"
                                         ).read_text().splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#")]
        for suffix in ("json", "md"):
            assert ("quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
                    f"nf_inj2c_decisive_smoke.{suffix}") in ignored


class TestAnUndefinedFoldClauseIsNotAPass:
    """MH2 H8 (2): at n ≤ 2 the sign test's smallest attainable false-fire rate `2⁻ⁿ` already
    exceeds α, so the clause DECLARES ITSELF UNDEFINED and `wins_required` is None. An UNDEFINED
    clause is ⛔ never a pass and ⛔ never a failure — the distinction MH2's seven-state taxonomy
    exists to preserve. Found by the 2-fold code-path smoke, which is what a smoke is for."""

    def test_two_folds_make_the_clause_UNDEFINED_and_the_verdict_UNEVALUABLE(self):
        from betting_ml.utils import cv_power
        assert cv_power.fold_consistency_clause(2).wins_required is None
        v = D.verdict(dominance={"state": "DOMINATES"}, control_binding={"state": "PASSES"},
                      defl={"binding": {"dsr_binding": 0.99, "dsr_min": 0.95, "pbo": 0.05,
                                        "pbo_max": 0.2, "trial_sharpes": {}, "v_members": []},
                            "lockstep_variance_lever": {}},
                      control={}, fold_wins=2, folds=2)
        assert v["gates"]["fold_consistency"] is None
        assert "fold_consistency" in v["gates_undefined"] and v["gates_failed"] == []
        assert v["state"] == "UNEVALUABLE"

    def test_the_registered_seven_folds_require_six(self):
        from betting_ml.utils import cv_power
        assert cv_power.fold_consistency_clause(len(C.FOLDS)).wins_required == 6


class TestTheControlReadsGateNamesNotArmNames:
    """`cv_power`'s `blocking_gates` is a {arm -> [gate names]} MAPPING. Reading it as a flat list
    collects ARM names, which then all land in `blockers_unclassified` — making a CORRECT partition
    look broken. Found by the 2-fold code-path smoke; a fixture-only suite would not have seen it."""

    def test_a_mapping_is_flattened_to_its_GATE_names(self, monkeypatch):
        # RE-ANCHORED: the control now drives `cv_power` directly with THIS story's own gate table
        # (NF-INJ2b's emits `coherence_restored`, the gate PM ruling 2 removed), so the stub moves
        # to the instrument. The asserted property is unchanged (MH2.7).
        _stub(monkeypatch, verdict="BLIND",
              blocking_gates={"incumbent": ["m1_crps_lift", "m2_coherence"],
                              "stratified": ["m2_coherence"]})
        out = D.positive_control({}, (2019,), {}, {}, board={})
        assert out["blockers_on_sensitive_side"] == ["m1_crps_lift"]
        assert out["blockers_on_invariant_side"] == ["m2_coherence"]
        assert out["blockers_unclassified"] == [], (
            "arm names leaked into the blocker set — the mapping was read as a flat list")

    def test_an_unclassified_blocker_is_reported_as_UNREADABLE_never_as_a_pass(self, monkeypatch):
        _stub(monkeypatch, verdict="BLIND",
              blocking_gates={"stratified": ["a_gate_nobody_declared"]})
        out = D.positive_control({}, (2019,), {}, {}, board={})
        assert out["blockers_unclassified"] == ["a_gate_nobody_declared"]
        assert "cannot be read against it" in (out["reading"] or "")


class TestAVacuousBadgeIsRecordedNotReinterpreted:
    """⚠️ `inject(0.0)` returns the REAL payload, so "an arm survives the no-effect payload" is
    measured on real data — where H1 asserts exactly that. The instrument reads it as "the family
    certifies noise"; on a DOMINANCE disposition it is also what a TRUE hypothesis looks like.

    ⚠️ **RE-ANCHORED 2026-09-05 BY PRE-REGISTRATION AMENDMENT 1 (PM ruling #6 D1).** The original
    form required the record to choose NEITHER reading, which was correct while the question was
    open and is FALSE now that the PM has ruled: a record still saying nobody chose would misstate
    its own authority. ⛔ The clause is re-anchored onto what survives and is still falsifiable —
    BOTH readings stay recorded, the survivors are named, and which one BINDS must be traceable to
    the AMENDMENT rather than picked at the point of reading (MH2.7: re-anchor a guard onto the new
    implementation, never weaken or delete it).

    ⛔ The ban the original carried is untouched: the control is never re-run with the null check
    disabled to obtain a nicer badge (§7 forbids it by name; E2.1-r)."""

    def test_a_VACUOUS_verdict_states_both_readings_and_names_the_survivors(self, monkeypatch):
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified"])
        out = D.positive_control({}, (2019,), {}, {}, board={})
        r = out["reading"] or ""
        assert "stratified" in r, "the surviving arm is not named"
        assert "BOTH READINGS STAY ON THE RECORD" in r and "(a)" in r and "(b)" in r, (
            "a VACUOUS badge must carry BOTH readings; deleting one is the E2.1-r inversion")

    def test_which_reading_binds_is_traceable_to_the_amendment_not_to_this_call_site(
            self, monkeypatch):
        """⭐ The distinction the PM's ruling turns on: a FORWARD DECLARATION, not an annotation
        applied after the fact. The reading must cite the amendment that authorises it."""
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified"])
        r = D.positive_control({}, (2019,), {}, {}, board={})["reading"] or ""
        assert "AMENDMENT 1" in r and "DECLARED" in r

    def test_the_null_control_is_never_disabled(self):
        src = _strip_comments(_RUNNER.read_text())
        assert "check_null_control=True" in src
        assert "check_null_control=False" not in src, (
            "the null check is disabled — that is re-running the control to obtain a nicer badge, "
            "which the pre-registration §7 forbids by name (E2.1-r)")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PRE-REGISTRATION AMENDMENT 1 (PM ruling #6 D1) — the control's null leg
#
# ⛔ These certify no verdict. They pin that the amendment is EXECUTED rather than described: the
# badge is recorded and does not bind, the INJECTED leg does, the declaration is SCOPED to a
# survivor set free of degenerates, and a control failure BLOCKS the disposition.
# ══════════════════════════════════════════════════════════════════════════════════════════════
_AMENDMENT = (Path(RB.__file__).parent / "ablation_results"
              / "nf_inj2c_preregistration_amendment_1.md")
_PREREG_DOC = (Path(RB.__file__).parent / "ablation_results" / "nf_inj2c_preregistration.md")


def _control(**over) -> dict:
    """A control record carrying every key the binding verdict reads."""
    base = {"verdict": "VACUOUS", "effect_injected_crps": 0.75,
            "survivors": ["stratified"], "metric_survivors": ["stratified"],
            "null_control_checked": True, "null_control_survivors": ["stratified"]}
    base.update(over)
    return base


class TestTheControlsBindingSubstanceIsTheInjectedLeg:
    """Amendment 1 §4 (b) — 'the declaration re-scopes the control, it never waives it'."""

    def test_a_detected_effect_with_no_degenerate_survivor_passes(self) -> None:
        got = D.control_binding_verdict(_control())
        assert got["state"] == "PASSES"
        assert got["checks"]["F1_effect_detected"] is True

    def test_f1_an_undetected_planted_effect_fails_however_good_the_badge_is(self) -> None:
        """The half of the re-scope that CUTS AGAINST the study: no metric survivor is a FAIL even
        when the instrument's own badge is the one the amendment declares inapplicable."""
        got = D.control_binding_verdict(_control(metric_survivors=[], survivors=[]))
        assert got["state"] == "FAILS" and got["failures"] == ["F1"]
        assert "did not detect" in got["why"]

    def test_f2_a_degenerate_surviving_the_injected_leg_fails(self) -> None:
        got = D.control_binding_verdict(
            _control(survivors=["stratified", "random_order"],
                     metric_survivors=["stratified", "random_order"]))
        assert got["state"] == "FAILS" and "F2" in got["failures"]
        assert got["checks"]["degenerate_injected_survivors"] == ["random_order"]

    def test_f3_a_degenerate_surviving_the_null_leg_is_carved_out_of_the_declaration(self) -> None:
        """⭐ Amendment 1 §3. The entailment (ship => VACUOUS) covers arms H1 predicts will clear.
        A DEGENERATE clearing every gate on the real payload is not entailed by H1, so the
        declaration must not reach it — this is what keeps the amendment from being a waiver."""
        got = D.control_binding_verdict(_control(null_control_survivors=["stratified",
                                                                        "mvp1_null"]))
        assert got["state"] == "FAILS" and "F3" in got["failures"]
        assert "not entailed by" in got["why"] or "genuine alarm" in got["why"]

    def test_f4_a_control_that_did_not_run_is_never_a_pass(self) -> None:
        assert D.control_binding_verdict({})["state"] == "UNEVALUABLE"
        assert D.control_binding_verdict(
            _control(null_control_checked=False))["state"] == "UNEVALUABLE"

    def test_f1_reads_metric_survivors_not_survivors(self) -> None:
        """⭐ PLAT-CVP2 defect 1: an arm stopped ONLY by an INJECTION-INVARIANT gate has still
        demonstrated the family detected the effect. Charging that to the family's SENSITIVITY is
        the defect NF-INJ2b's BLIND badge was earned by."""
        got = D.control_binding_verdict(_control(survivors=[],
                                                 metric_survivors=["stratified"]))
        assert got["state"] == "PASSES", (
            "an arm blocked only by a gate the injection cannot MOVE was charged to the family's "
            "sensitivity — the reading amendment 1 §4 names explicitly")


class TestTheDeclarationIsScopedAndRecordedRatherThanChosen:

    def test_the_declaration_applies_only_when_no_degenerate_survived(self, monkeypatch) -> None:
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified"])
        ok = D.positive_control({}, (2019,), {}, {})
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified", "mvp1_null"])
        carved = D.positive_control({}, (2019,), {}, {})
        assert ok["null_leg_declaration_applies"] is True
        assert carved["null_leg_declaration_applies"] is False
        assert carved["degenerate_null_survivors"] == ["mvp1_null"]

    def test_a_non_vacuous_badge_is_not_declared_inapplicable(self, monkeypatch) -> None:
        """The declaration names ONE badge. A BLIND or DEFLATION_BLOCKED reading is untouched by
        it — declaring a badge inapplicable that the amendment never mentions would be the waiver
        the PM ruled against."""
        _stub(monkeypatch, verdict="BLIND", null_control_survivors=[])
        assert D.positive_control({}, (2019,), {}, {})["null_leg_declaration_applies"] is False

    def test_both_readings_stay_on_the_record_and_the_binding_one_is_named(self, monkeypatch):
        """Amendment 1 §5 (c): the badge is recorded VERBATIM, both readings survive, and which
        one BINDS is DECLARED rather than chosen at the point of reading."""
        _stub(monkeypatch, verdict="VACUOUS", null_control_survivors=["stratified"])
        reading = D.positive_control({}, (2019,), {}, {})["reading"]
        assert "BOTH READINGS STAY ON THE RECORD" in reading
        assert "AMENDMENT 1" in reading and "INAPPLICABLE" in reading
        assert "chooses NEITHER" not in reading, (
            "the pre-amendment wording refused to choose; the PM has now ruled, and a record that "
            "still says nobody chose is false")

    def test_the_null_leg_still_runs_every_time(self) -> None:
        """§5 (2): disabling the null check to obtain a nicer badge stays forbidden — and it is
        what makes §3's degenerate carve-out enforceable rather than decorative."""
        src = _strip_comments(_RUNNER.read_text())
        assert "check_null_control=True" in src
        assert "check_null_control=False" not in src


class TestAControlFailureBlocksTheDisposition:

    def _v(self, control_binding, dominance_state="DOMINATES"):
        dom = {"state": dominance_state, "by_measure": {}, "regressed_measures": [],
               "unevaluable_measures": []}
        defl = {"binding": {"dsr_binding": 0.99, "dsr_min": 0.95, "pbo": 0.01, "pbo_max": 0.2}}
        return D.verdict(dominance=dom, defl=defl, control={"verdict": "VACUOUS"},
                         control_binding=control_binding, fold_wins=7, folds=7)

    def test_a_failing_control_refuses_an_otherwise_dominant_run(self) -> None:
        assert self._v({"state": "PASSES"})["state"] == "DOMINATES"
        assert self._v({"state": "FAILS", "failures": ["F1"]})["state"] == "CONTROL_REFUSED"
        assert self._v({"state": "UNEVALUABLE"})["state"] == "CONTROL_REFUSED"

    def test_a_regression_still_reads_null_ahead_of_the_control(self) -> None:
        """A measured regression against the incumbent is a direct comparison the control's
        sensitivity cannot manufacture, so NULL stays prior."""
        assert self._v({"state": "FAILS", "failures": ["F1"]}, "REGRESSES")["state"] == "NULL"

    def test_the_badge_alone_can_never_refuse_or_rescue(self) -> None:
        """⭐ The amendment's admissibility rests on this: it can only REFUSE. A VACUOUS badge with
        a PASSING injected leg reaches DOMINATES, and a PASSING badge with a FAILING injected leg
        does not — so the badge is inert in BOTH directions and the injected leg is what binds."""
        dom = {"state": "DOMINATES", "by_measure": {}, "regressed_measures": [],
               "unevaluable_measures": []}
        defl = {"binding": {"dsr_binding": 0.99, "dsr_min": 0.95, "pbo": 0.01, "pbo_max": 0.2}}
        for badge in ("VACUOUS", "DETECTED", "BLIND", "CONSTRAINT_BLOCKED"):
            passes = D.verdict(dominance=dom, defl=defl, control={"verdict": badge},
                               control_binding={"state": "PASSES"}, fold_wins=7, folds=7)
            fails = D.verdict(dominance=dom, defl=defl, control={"verdict": badge},
                              control_binding={"state": "FAILS", "failures": ["F1"]},
                              fold_wins=7, folds=7)
            assert passes["state"] == "DOMINATES" and fails["state"] == "CONTROL_REFUSED", badge

    def test_the_badge_is_still_recorded_verbatim_beside_the_binding_verdict(self) -> None:
        got = self._v({"state": "PASSES"})
        assert got["positive_control"] == "VACUOUS"
        assert got["control_binding"]["state"] == "PASSES"


class TestTheInjectorCannotTreatThisStorysDegenerates:
    """⭐ F2/F3 charge a degenerate that survives. That reading is only sound if the injection never
    IMPROVED it — otherwise the control manufactures the failure it then reports."""

    def test_the_decisive_runner_hands_the_injector_its_own_field(self) -> None:
        src = _strip_comments(_RUNNER.read_text())
        assert "RB.make_injector(payload, field=BINDING_FIELD)" in src, (
            "the injector is taking NF-INJ2b's field; this story's degenerates would be treated "
            "only by the coincidence that the two registrations declare the same ones")

    def test_no_declared_degenerate_or_reference_is_ever_injected(self) -> None:
        base = {"folds": [2019], "coherence": {},
                "per_fold": {a: {2019: {"crps": 1.0}} for a in C.ARMS},
                "tier_rho": {a: {2019: dict.fromkeys(_POS, 0.5)} for a in C.ARMS},
                "scored": {a: {"crps": 1.0} for a in C.ARMS}}
        inject = RB.make_injector(base, field=D.BINDING_FIELD)
        out = inject(0.75)
        for arm in tuple(C.DEGENERATE_ARMS) + tuple(C.REFERENCE_ARMS):
            assert out["per_fold"][arm][2019]["crps"] == 1.0, f"{arm} was injected"
        assert out["per_fold"]["stratified"][2019]["crps"] == pytest.approx(0.25), (
            "the PRIMARY arm was NOT injected — the control would then be probing nothing")

    def test_a_field_with_different_degenerates_treats_different_arms(self) -> None:
        """Non-vacuity: the parameter must CHANGE the treated set, or passing it proves nothing."""
        base = {"folds": [2019], "coherence": {},
                "per_fold": {a: {2019: {"crps": 1.0}} for a in C.ARMS},
                "tier_rho": {a: {2019: dict.fromkeys(_POS, 0.5)} for a in C.ARMS},
                "scored": {a: {"crps": 1.0} for a in C.ARMS}}
        other = RB.FieldSpec(arms=tuple(C.ARMS), degenerates=("stratified",),
                             reference=(C.INCUMBENT_ARM,), declared_field_size=len(C.ARMS),
                             label="a field that declares the primary a degenerate")
        out = RB.make_injector(base, field=other)(0.75)
        assert out["per_fold"]["stratified"][2019]["crps"] == 1.0
        assert out["per_fold"]["mvp1_null"][2019]["crps"] == pytest.approx(0.25)


class TestTheAmendmentDocumentSaysWhatTheCodeDoes:

    def test_the_amendment_exists_and_the_prereg_points_at_it(self) -> None:
        assert _AMENDMENT.exists()
        prereg = _PREREG_DOC.read_text()
        assert "AMENDMENT LOG" in prereg and "nf_inj2c_preregistration_amendment_1.md" in prereg, (
            "a reader can reach §7 without learning the amendment exists")

    def test_section_7_is_left_verbatim_including_its_measured_false_premise(self) -> None:
        """NF-W7f: a premise a measurement refutes is part of the record, ⛔ not tidied away."""
        assert "**has not landed**" in _PREREG_DOC.read_text()

    def test_the_amendment_declares_itself_refuse_only(self) -> None:
        txt = _AMENDMENT.read_text()
        assert "can only REFUSE, never RESCUE" in txt
        assert "REFUSE-ONLY" in _PREREG_DOC.read_text()

    def test_the_amendment_states_the_entailment_it_rests_on(self) -> None:
        txt = _AMENDMENT.read_text()
        assert "SHIPS" in txt and "VACUOUS" in txt and "entailed" in txt

    def test_the_amendment_does_not_claim_the_blindness_it_cannot_have(self) -> None:
        """⭐ It was written AFTER node 3b ran. It must say so — a provenance claim it cannot
        support is worse than none."""
        flat = _flat(_AMENDMENT.read_text())
        assert _flat("cannot claim that, and does not") in flat
        assert _flat("Node 3b has run") in flat

    def test_the_amendment_quotes_no_figure_from_the_node_3b_remeasure(self) -> None:
        """The same provenance property the base prereg carries, applied to the amendment: it may
        be written after the board numbers exist, but it must not be SHAPED by them."""
        report = _AMENDMENT.parent / "nf_inj2c_dominance_baseline.json"
        if not report.exists():
            pytest.skip("node 3b's report is absent in this checkout")
        rep = json.loads(report.read_text())
        figures: set[str] = set()

        def _collect(node) -> None:
            if isinstance(node, dict):
                for v in node.values():
                    _collect(v)
            elif isinstance(node, list):
                for v in node:
                    _collect(v)
            elif isinstance(node, float) and abs(node) >= 0.01:
                for text in (f"{node:.2f}", f"{node:.3f}", f"{node:.4f}", repr(node)):
                    if len(text.split(".")[-1]) >= 2:
                        figures.add(text)
            elif isinstance(node, int) and abs(node) >= 1000:
                figures.add(str(node))

        dominance = dict(rep.get("dominance") or {})
        dominance.pop("bands", None)
        _collect(dominance)
        assert figures, "no distinctive figure could be extracted — the guard would pass on nothing"
        txt = _AMENDMENT.read_text()
        assert not sorted(f for f in figures if f in txt)

    def test_the_decisive_run_has_not_happened_at_this_commit(self) -> None:
        """The blindness that MATTERS here: this document fixes how a control verdict is read, and
        that verdict has not been computed."""
        assert not (_AMENDMENT.parent / "nf_inj2c_decisive.json").exists()
        assert not (_AMENDMENT.parent / "nf_inj2c_decisive.md").exists()

    def test_the_rejected_option_is_recorded_with_its_reason(self) -> None:
        """'The stricter option' is the one a later reader assumes was safe."""
        txt = _AMENDMENT.read_text()
        assert "vacuity pointed in the punishing direction" in txt
        assert "gates that cannot FAIL" in txt and "gates that cannot PASS" in txt

    def test_plat_cvp3_is_named_as_the_true_fix(self) -> None:
        assert "PLAT-CVP3" in _AMENDMENT.read_text()


class TestTheControlGlueOverTheREALInstrument:
    """⭐ ONE test drives the REAL `cv_power.injected_effect_positive_control` — no stub — through
    the real `gate_table`, the real injector and the real binding verdict.

    Every other test in this file stubs the instrument, which means they assert against a report
    shape a TEST AUTHOR wrote. That is the INC-39 unexercised-middle: the reader and the instrument
    could drift apart and the suite would stay green. The 3-fold code-path smoke found exactly three
    such bugs (the fold clause returns a report; `blocking_gates` is a MAPPING; the control returns
    a DATACLASS), and a fresh worktree cannot run that smoke because `sports.duckdb` is gitignored
    (NF-INFRA1). This closes the gap the smoke cannot reach from here.

    ⛔ Certifies no verdict — the numbers are synthetic and no arm ordering here means anything.
    """

    def _payload(self, *, primary_better: bool):
        folds = (2019, 2020, 2021)
        per_fold: dict = {}
        for arm in C.ARMS:
            better = primary_better and arm in ("stratified", "feasibility_clamp")
            for i, y in enumerate(folds):
                per_fold.setdefault(arm, {})[y] = {
                    "crps": 10.0 - (0.5 if better else 0.0) + 0.01 * i,
                    "tier_rho_by_position": dict.fromkeys(
                        _POS, 0.60 if better else 0.50),
                    "coverage80_by_position": dict.fromkeys(_POS, 0.82),
                    "coverage_n_by_position": dict.fromkeys(_POS, 80),
                    "n": 400,
                }
        scored = {a: {"crps": 10.0} for a in C.ARMS}
        return per_fold, folds, scored, {a: 5 for a in C.ARMS}

    def test_the_reader_and_the_instrument_agree_on_every_key_the_verdict_reads(self) -> None:
        per_fold, folds, scored, coh = self._payload(primary_better=True)
        out = D.positive_control(per_fold, folds, scored, coh, board={})
        # the keys `control_binding_verdict` and the report reach for, produced by the REAL library
        for key in ("verdict", "survivors", "metric_survivors", "null_control_checked",
                    "null_control_survivors", "blocking_gates", "deflation_gates",
                    "metric_gates", "field_level_gates_applied_per_arm"):
            assert key in out, f"the instrument no longer returns {key!r}"
        assert isinstance(out["blocking_gates"], dict), (
            "`blocking_gates` stopped being a {arm -> [gate]} MAPPING — iterating it would yield "
            "ARM names and make the declared partition look broken (found by the smoke)")
        binding = D.control_binding_verdict(out)
        assert binding["state"] in ("PASSES", "FAILS", "UNEVALUABLE")
        assert binding["state"] != "UNEVALUABLE", (
            "the real instrument's report is missing a key the binding verdict needs — F4 fired "
            "on a control that actually ran, which is the reader/instrument drift this test exists "
            f"to catch: {binding.get('why')}")

    def test_the_declared_partition_covers_every_gate_the_real_table_emits(self) -> None:
        """⛔ An unclassified blocker means the §7 partition no longer covers the gate set, and the
        control could not be read against it at all (NF1.7 (a))."""
        per_fold, folds, scored, coh = self._payload(primary_better=False)
        out = D.positive_control(per_fold, folds, scored, coh, board={})
        assert out["blockers_unclassified"] == [], (
            f"gate(s) {out['blockers_unclassified']} are in NEITHER declared half")
        table = D.gate_table(RB.build_payload(per_fold, folds, scored, coh))
        emitted = set(table["stratified"])
        declared = set(C.INJECTION_SENSITIVE_GATES) | set(C.INJECTION_INVARIANT_GATES)
        assert emitted <= declared, f"undeclared gates: {sorted(emitted - declared)}"

    def test_the_real_injector_leaves_this_storys_degenerates_untouched(self) -> None:
        """The premise F2/F3 rest on, proven against the REAL injector rather than a stub."""
        per_fold, folds, scored, coh = self._payload(primary_better=True)
        payload = RB.build_payload(per_fold, folds, scored, coh)
        out = RB.make_injector(payload, field=D.BINDING_FIELD)(RB.INJECTED_EFFECT)
        for arm in tuple(C.DEGENERATE_ARMS) + tuple(C.REFERENCE_ARMS):
            assert out["per_fold"][arm][2019]["crps"] == per_fold[arm][2019]["crps"], (
                f"{arm} was injected — F2/F3 would charge it for a survival the control MANUFACTURED")


class TestTheRunRecordsTheVintageItWasScoredOn:
    """⭐ NF-INFRA1's class, on the READ side: an artifact a build reads but never writes is
    invisible until someone looks. Two of node 4's inputs are gitignored and fail in OPPOSITE
    ways — the panels RAISE when absent (safe), the pool cache silently REBUILDS from a live
    upstream (not safe). ⛔ RECORDED, ⛔ never gated: a run is internally consistent whatever the
    vintage; what this makes checkable is a comparison ACROSS runs."""

    def test_the_vintage_names_both_gitignored_inputs(self) -> None:
        fv = D.feature_vintage()
        assert set(fv) >= {"nf1_5_pool_cache", "nf1_9_veteran_band_panel"}
        for key in ("nf1_5_pool_cache", "nf1_9_veteran_band_panel"):
            assert "present" in fv[key] and "newest_mtime" in fv[key]

    def test_an_absent_input_is_reported_absent_rather_than_omitted(self, monkeypatch,
                                                                    tmp_path) -> None:
        """An input that is not there must SAY so — a missing key reads as 'not checked'."""
        monkeypatch.setattr(D.N15, "_FEATURE_CACHE", tmp_path / "nope")
        fv = D.feature_vintage()
        assert fv["nf1_5_pool_cache"]["present"] is False
        assert fv["nf1_5_pool_cache"]["files"] == 0

    def test_the_vintage_is_a_CONTENT_fingerprint_not_an_mtime(self, tmp_path) -> None:
        """⭐ INC-41 on a local file: a COPY refreshes an mtime while the data is unchanged, and the
        difference that actually moved the scored arms between two checkouts on 2026-09-05 was a
        5-COLUMN delta at IDENTICAL row counts. An mtime cannot see that; a column fingerprint can.
        """
        import pandas as pd

        d = tmp_path / "cache"
        d.mkdir()
        import types

        pd.DataFrame({"a": [1], "b": [2]}).to_parquet(d / "pool_base2024.parquet")
        orig = D.N15
        try:
            D.N15 = types.SimpleNamespace(_FEATURE_CACHE=d)
            a = D.feature_vintage()["nf1_5_pool_cache"]["fingerprint"]
            # same rows, one MORE column — the exact shape of the real difference
            pd.DataFrame({"a": [1], "b": [2], "injury_games_served": [3]}).to_parquet(
                d / "pool_base2024.parquet")
            b = D.feature_vintage()["nf1_5_pool_cache"]["fingerprint"]
        finally:
            D.N15 = orig
        assert a and b and a != b, (
            "a 5-column difference at identical row counts did not move the fingerprint — the "
            "record cannot distinguish the two vintages it exists to distinguish")

    def test_an_unreadable_cache_file_is_named_rather_than_skipped(self, tmp_path) -> None:
        """NF1.7 (a): a cache we cannot read is not a cache we verified."""
        import types

        d = tmp_path / "cache"
        d.mkdir()
        (d / "pool_base2024.parquet").write_text("not a parquet file")
        orig = D.N15
        try:
            D.N15 = types.SimpleNamespace(_FEATURE_CACHE=d)
            got = D.feature_vintage()["nf1_5_pool_cache"]
        finally:
            D.N15 = orig
        assert got["unreadable"] == ["pool_base2024.parquet"]

    def test_the_record_says_it_is_not_a_gate(self) -> None:
        """⛔ Recording a vintage must not become a bar. It has no admissible band (node 3a §1),
        so folding it into the verdict would be a criterion invented after the registration."""
        fv = D.feature_vintage()
        assert "NOT GATED" in fv["note"]
        src = _strip_comments(_RUNNER.read_text())
        # ⛔ NOT `"feature_vintage()" in src` — the DEFINITION line satisfies that, so the clause
        # stayed GREEN with the call deleted from the payload (the NF-C0e wired-but-never-invoked
        # shape; caught by the RED proof, not by review). Match the CALL SITE.
        assert '"feature_vintage": feature_vintage()' in src, (
            "the run no longer records the vintage it was scored on")
        assert "feature_vintage" not in src.split("def verdict(")[1].split("\ndef ")[0], (
            "the vintage reached the verdict — it is an audit trail, not a measure, and node 3a "
            "§1 admits no band for it")


class TestF1IsInactiveNotFailedWhenAGateCannotBeFormed:
    """⭐ NF-D20 / NF1.9 — count whether the mechanism could ACT before condemning it.

    At n <= 2 the calibrated fold-consistency clause is UNDEFINED (MH2 H8), so it is False for
    EVERY arm and `metric_survivors` empties STRUCTURALLY. Reporting that as "the family did not
    detect a planted effect" is untrue. Found by the 2-fold code-path smoke.

    ⛔ The distinction changes the REASON, never the OUTCOME — both still block."""

    def test_at_two_folds_an_empty_metric_survivor_set_is_INACTIVE(self) -> None:
        got = D.control_binding_verdict(_control(metric_survivors=[], survivors=[]), folds=2)
        assert got["state"] == "UNEVALUABLE" and got["failures"] == ["F1_INACTIVE"]
        assert "INACTIVE" in got["why"] and "UNDEFINED" in got["why"]

    def test_at_the_registered_seven_folds_the_same_input_is_a_real_FAILURE(self) -> None:
        """Non-vacuity: the clause must DISCRIMINATE, or the carve-out excuses every F1."""
        got = D.control_binding_verdict(_control(metric_survivors=[], survivors=[]), folds=7)
        assert got["state"] == "FAILS" and got["failures"] == ["F1"]

    def test_an_inactive_F1_still_blocks_the_disposition(self) -> None:
        dom = {"state": "DOMINATES", "by_measure": {}, "regressed_measures": [],
               "unevaluable_measures": []}
        defl = {"binding": {"dsr_binding": 0.99, "dsr_min": 0.95, "pbo": 0.01, "pbo_max": 0.2}}
        v = D.verdict(dominance=dom, defl=defl, control={"verdict": "BLIND"},
                      control_binding=D.control_binding_verdict(
                          _control(metric_survivors=[], survivors=[]), folds=2),
                      fold_wins=2, folds=2)
        assert v["state"] == "CONTROL_REFUSED", (
            "an INACTIVE control was scored as a pass — the carve-out must change the REASON, "
            "never the outcome (it stays refuse-only)")

    def test_the_carve_out_never_excuses_a_degenerate_survivor(self) -> None:
        """⛔ F2/F3 are NOT fold-count artifacts: a degenerate clearing every gate is an alarm at
        any n, so the inactivity carve-out must not swallow it."""
        got = D.control_binding_verdict(
            _control(metric_survivors=[], survivors=[],
                     null_control_survivors=["mvp1_null"]), folds=2)
        assert "F3" in got["failures"] and got["state"] == "FAILS"

    def test_the_runner_passes_the_fold_count(self) -> None:
        src = _strip_comments(_RUNNER.read_text())
        assert "control_binding_verdict(control, folds=len(folds))" in src


def test_the_amendment_records_the_F1_inactivity_carve_out() -> None:
    """The document must say what the code does — a carve-out present only in code is a rule a
    later reader cannot audit against the registration."""
    flat = _flat(_AMENDMENT.read_text())
    assert _flat("F1 IS *INACTIVE*, ⛔ NOT FAILED") in flat
    assert _flat("never reaches") in flat and "F2/F3" in flat
    assert _flat("changes the **REASON**, ⛔ never the **OUTCOME**") in flat
