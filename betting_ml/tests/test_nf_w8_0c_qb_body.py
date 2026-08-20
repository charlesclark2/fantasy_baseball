"""NF-W8-0c — guards for the QB BODY-level comparison and the declared body re-level field.

Every guard here is RED-PROVEN by `red_proof_nf_w8_0c.py`: a clause that cannot FAIL on
deliberately-broken source is not a guard (NF1.7 (a) / INC-38 / NF-D17). The RED proof asserts
its own mutation LANDED, that the mutated token is GONE, and that its anchor is UNIQUE in the file
(the three ways a red proof lies: #682, #815, the prediction_log anchor collision).
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_body as QB
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP
from quant_sports_intel_models.football.nfl.fantasy import league_presets as LP
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as W7C

_ROOT = Path(__file__).resolve().parents[2]
_FANTASY = _ROOT / "quant_sports_intel_models" / "football" / "nfl" / "fantasy"
_MODULE = _FANTASY / "fp_qb_body.py"
_RUNNER = _FANTASY / "run_nf_w8_0c_qb_body.py"
_PREREG = _FANTASY / "ablation_results" / "nf_w8_0c_preregistration.md"
_RECORD = _FANTASY / "ablation_results" / "nf_w8_0c_qb_body.json"


def _strip_comments(src: str) -> str:
    """Comment-stripped source — prose must never be able to satisfy a source guard (INC-38)."""
    return "\n".join(re.sub(r"#.*$", "", line) for line in src.splitlines())


def _qb_weights() -> np.ndarray:
    return FA.leg_weights(LP.get_preset(W7C.GATE_LEAGUE), "QB")


def _synth_banks(n: int = 48, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    b = np.sort(rng.gamma(2.0, 4.0, size=(n, FA.N_LEGS, FA.N_LEVELS)), axis=2)
    b[:, :, : FA.N_LEVELS // 2] = 0.0          # a realistic zero mass per leg
    return b


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The registration — the field, the pins and the inherited gates
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRegistration:
    def test_the_preregistration_is_committed_and_names_the_declared_field(self):
        assert _PREREG.exists(), "the narrative pre-registration must be committed BEFORE any run"
        txt = _PREREG.read_text()
        for arm in QB.REAL_ARMS:
            assert f"`{arm}`" in txt, f"real arm `{arm}` is not in the registration"
        assert "direct_points" in txt

    def test_the_comparator_is_not_in_family_bs_trial_field(self):
        """MH2 (a): a family gets its OWN pre-registered field. `direct_points` is a DIFFERENT
        ARCHITECTURE — bundling it would over-tax a real finding through DSR's cross-trial
        dispersion (NF-W6b-C / NF-W7f)."""
        assert QB.COMPARATOR not in QB.REAL_ARMS
        assert QB.COMPARATOR not in QB.ELIGIBLE
        assert QB.COMPARATOR not in QB.ANCHOR_ARMS
        assert QB.DECLARED_FIELD_SIZE == len(QB.REAL_ARMS) == 4

    def test_every_gate_constant_is_inherited_by_reference_and_unrelaxed(self):
        """E2.1-r: a bar is never re-read after a result. Inheriting BY REFERENCE means a future
        edit to this module cannot quietly loosen a predecessor's bar."""
        assert QB.PIT_MAX_DECILE_DEV == FA.PIT_MAX_DECILE_DEV == 0.05
        assert QB.BH_Q == XP.BH_Q and QB.ALPHA == XP.ALPHA
        assert QB.DSR_MIN == XP.DSR_MIN and QB.PBO_MAX == XP.PBO_MAX
        assert QB.MIN_PRIOR_ROWS == XP.MIN_PRIOR_ROWS
        assert QB.REPRODUCTION_TOLERANCE == XP.REPRODUCTION_TOLERANCE == 1e-9

    def test_the_ranking_point_is_the_decided_0b_read_by_reference(self):
        assert QB.POINT_READER is TP.tail_completed_point

    def test_there_is_one_oracle_per_form(self):
        """NF-D16 (g‴): the forms NEST (`cond_scale` ⊂ `leg_scale`), so a single field-wide
        ceiling would veto a legitimately-better nested form as a false metric inversion."""
        assert set(QB.ORACLE_OF) == set(QB.REAL_ARMS)
        assert len(set(QB.ORACLE_ARMS)) == len(QB.REAL_ARMS)
        for arm in QB.REAL_ARMS:
            assert QB.ORACLE_OF[arm] in QB.ANCHOR_ARMS

    def test_both_degenerates_are_scored_every_run(self):
        """NF-D11 / NF1.8: score the degenerate, never reason about it — and the two-sided pair
        (a nihilist that must lose, a climatology that WINS the objective and must lose CRPS)."""
        assert set(QB.DEGENERATE_ARMS) == {"climatology_bank", "nihilist_zero"}
        for d in QB.DEGENERATE_ARMS:
            assert d in QB.ANCHOR_ARMS and d not in QB.ELIGIBLE

    def test_the_tail_lever_is_recorded_closed_and_not_reopened(self):
        src = _strip_comments(_MODULE.read_text()) + _strip_comments(_RUNNER.read_text())
        assert "fit_tail_betas" not in src and "fit_eq_tail" not in src, (
            "the tail lever is measured CLOSED (NF-W8-0b: ~19x short) — a successor must not "
            "re-fit it")
        assert QB.PRED_TAIL_MECHANISM_BOUND_PPR == 0.0193


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The assembly wrapper — ONE code path, byte-identical at shift 0
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestAssembly:
    def test_the_wrapper_is_byte_identical_to_the_certified_assembly_at_zero_shift(self):
        """The identity that makes `cond_shift` a MATCHED arm (same code path, shift off) rather
        than a differently-implemented one (NF-W7d)."""
        b, w = _synth_banks(), _qb_weights()
        rng = np.random.default_rng(5)
        pi = np.clip(rng.beta(6, 2, size=b.shape[0]), 0, 1)
        corr = np.eye(FA.N_LEGS)
        ref = MX.assemble_mixture_bank(b, w, pi=pi, corr=corr, draws=200)
        got, legs, tot = QB.assemble_qb(b, w, pi=pi, corr=corr, draws=200)
        assert np.array_equal(ref, got), "the wrapper diverged from the certified assembly"
        assert legs.shape == (b.shape[0], FA.N_LEGS) and tot.shape == (b.shape[0],)
        # ⭐ the INDEPENDENT anchor the §3.1 identity rests on: the assembled total is linear in
        # its own leg draws. Without it the read channel would be defined as the residual and the
        # identity clause would be vacuously true for ANY leg means (NF-C0e).
        assert abs(float((legs @ w).mean() - tot.mean())) <= QB.IDENTITY_TOLERANCE

    def test_a_played_shift_actually_acts_and_moves_the_point_by_pi_times_delta(self):
        """NF-D20: a mechanism that cannot ACT is a finding, not a pass — and the shift's size is
        exactly what `fit_arm_params` assumes when it divides by mean π."""
        b, w = _synth_banks(), _qb_weights()
        rng = np.random.default_rng(7)
        pi = np.clip(rng.beta(6, 2, size=b.shape[0]), 0, 1)
        corr = np.eye(FA.N_LEGS)
        base, _, _ = QB.assemble_qb(b, w, pi=pi, corr=corr, draws=400)
        moved, _, _ = QB.assemble_qb(b, w, pi=pi, corr=corr, draws=400, played_shift=2.0)
        delta = float(QB.POINT_READER(moved).mean() - QB.POINT_READER(base).mean())
        assert delta > 0
        assert abs(delta - 2.0 * float(pi.mean())) < 0.15 * abs(delta)

    def test_the_alive_mask_crosscheck_refuses_a_disagreeing_leg_draw(self, monkeypatch):
        """The one quantity the shared path does not return is re-derived — so it is VERIFIED
        against the scored draws, never trusted (NF-W7d)."""
        b, w = _synth_banks(), _qb_weights()
        pi = np.full(b.shape[0], 0.5)
        corr = np.eye(FA.N_LEGS)
        real = MX.mixture_leg_draws

        def _poisoned(*a, **k):
            out = real(*a, **k)
            out = out.copy()
            out[:, :, 0] = 1.0                 # every draw non-zero ⇒ some not-alive draw is too
            return out

        monkeypatch.setattr(MX, "mixture_leg_draws", _poisoned)
        with pytest.raises(ValueError, match="availability mask disagrees"):
            QB.assemble_qb(b, w, pi=pi, corr=corr, draws=64, played_shift=1.0)

    def test_scale_legs_refuses_a_nonpositive_kappa_and_preserves_zero_mass(self):
        """NF-D16 / NF-TR2b: a negative scale inverts a leg. And a κ > 0 leaves each bank's zero
        mass EXACTLY where it was, so `MX.pi_floor` — hence the clamp — is unchanged."""
        b = _synth_banks()
        k = np.full(FA.N_LEGS, -1.0)
        with pytest.raises(ValueError, match="non-positive"):
            QB.scale_legs(b, k)
        scaled = QB.scale_legs(b, np.full(FA.N_LEGS, 1.7))
        assert np.array_equal(MX.leg_zero_mass(b), MX.leg_zero_mass(scaled))
        assert np.array_equal(MX.pi_floor(b), MX.pi_floor(scaled))

    def test_the_climatology_anchor_refuses_to_be_formed_from_nothing(self):
        """NF1.7 (a): an anchor that could not be FORMED is a failed control, never a pass."""
        with pytest.raises(ValueError, match="at least 2 prior realized rows"):
            QB.climatology_bank(np.asarray([1.0]), 5)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Family A — the two decompositions, asserted as IDENTITIES against the artifact
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _decomp_case(seed: int = 21):
    rng = np.random.default_rng(seed)
    n, w = 60, _qb_weights()
    leg_means = np.abs(rng.normal(size=(n, FA.N_LEGS))) * 3.0
    realized = np.abs(rng.normal(size=(n, FA.N_LEGS))) * 3.0
    y = realized @ w
    total_draw_mean = leg_means @ w
    point = total_draw_mean + rng.normal(scale=0.05, size=n)
    pi = np.clip(rng.beta(6, 2, size=n), 0.01, 1)
    active = (np.abs(realized) > 0).any(axis=1).astype(float)
    return dict(point=point, y=y, leg_means=leg_means, realized=realized, weights=w,
                pi_used=pi, active=active, total_draw_mean=total_draw_mean)


class TestMechanismDecomposition:
    def test_the_identity_is_exact(self):
        d = QB.mechanism_decomposition(**_decomp_case())
        assert d["identity_holds"] is True
        assert abs(d["identity_residual"]) <= QB.IDENTITY_TOLERANCE

    def test_the_identity_FAILS_when_the_leg_means_are_not_the_ones_the_point_came_from(self):
        """The two-sided half: an identity guard that cannot go RED is décor (NF-W8-0b §12.5(e) —
        assert the identity against the artifact, never restate the claim)."""
        case = _decomp_case()
        case["leg_means"] = case["leg_means"] + 1.0
        d = QB.mechanism_decomposition(**case)
        assert d["identity_holds"] is False
        assert abs(d["linearity_residual"]) > QB.IDENTITY_TOLERANCE

    def test_the_availability_split_is_None_not_zero_when_it_cannot_be_formed(self):
        """NF1.7 (a): an UNDEFINED split is reported as such, never zero-filled."""
        case = _decomp_case()
        case["active"] = np.zeros_like(case["active"])
        d = QB.mechanism_decomposition(**case)
        assert d["availability_channel_ppr"] is None
        assert d["conditional_channel_ppr"] is None
        assert all(v["conditional_part_ppr"] is None for v in d["legs"].values())

    def test_pooling_is_over_rows_and_the_fold_mean_convention_is_reported_beside_it(self):
        """NF1.8 — and NF-W8-0b's own headline was first written from the wrong convention, which
        made a published bound WRONG. Both are carried so a reader cannot confuse them."""
        big = QB.mechanism_decomposition(**_decomp_case(seed=3))
        small_case = {k: (v[:8] if isinstance(v, np.ndarray) and len(v) == 60 else v)
                      for k, v in _decomp_case(seed=4).items()}
        small = QB.mechanism_decomposition(**small_case)
        pooled = QB.pool_mechanism([big, small])
        assert pooled["n"] == big["n"] + small["n"] == 68
        row_pooled = (big["n"] * big["total_bias_ppr"] + small["n"] * small["total_bias_ppr"]) \
            / (big["n"] + small["n"])
        assert abs(pooled["pooled"]["total_bias_ppr"] - row_pooled) < 1e-12
        fold_mean = float(np.mean([big["total_bias_ppr"], small["total_bias_ppr"]]))
        assert abs(pooled["fold_mean"]["total_bias_ppr"] - fold_mean) < 1e-12
        assert abs(fold_mean - row_pooled) > 1e-9, (
            "the fixture must make the two conventions DIFFER, or this guard passes on nothing")

    def test_an_immaterial_channel_is_labelled_immaterial(self):
        """NF-W6: demonstrable ≠ material. The floor is a DESIGN quantity fixed before any score."""
        assert QB.CHANNEL_MATERIAL_PPR == 0.05
        d = QB.mechanism_decomposition(**_decomp_case())
        pooled = QB.pool_mechanism([d])
        for leg, v in pooled["legs"].items():
            if v["contribution_ppr"] is not None:
                assert v["material"] == (abs(v["contribution_ppr"]) >= QB.CHANNEL_MATERIAL_PPR)


class TestBandDecomposition:
    def test_the_bands_sum_exactly_to_the_gridmean_gap(self):
        rng = np.random.default_rng(31)
        a = np.sort(rng.gamma(2.0, 3.0, size=(40, FA.N_LEVELS)), axis=1)
        b = np.sort(rng.gamma(2.0, 2.6, size=(40, FA.N_LEVELS)), axis=1)
        d = QB.band_decomposition(a, b)
        assert d["identity_holds"] is True
        assert abs(d["gridmean_gap_ppr"] - float((a.mean(axis=1) - b.mean(axis=1)).mean())) < 1e-10
        assert len(d["bands"]) == QB.N_BANDS
        assert abs(sum(x["contribution_ppr"] for x in d["bands"]) - d["gridmean_gap_ppr"]) < 1e-10

    def test_a_uniform_level_shift_lands_evenly_across_every_band(self):
        """The mechanistic reading the story turns on: a BODY-level offset is spread across the
        quantile function, whereas a tail-only mechanism concentrates in the outer bands."""
        rng = np.random.default_rng(33)
        a = np.sort(rng.gamma(2.0, 3.0, size=(40, FA.N_LEVELS)), axis=1)
        d = QB.band_decomposition(a + 1.0, a)
        shares = [x["share"] for x in d["bands"]]
        assert max(shares) - min(shares) < 0.02, "a uniform shift must not concentrate in a band"

    def test_band_pooling_is_over_rows(self):
        rng = np.random.default_rng(35)
        a1 = np.sort(rng.gamma(2.0, 3.0, size=(40, FA.N_LEVELS)), axis=1)
        a2 = np.sort(rng.gamma(2.0, 3.0, size=(10, FA.N_LEVELS)), axis=1)
        c1 = QB.band_decomposition(a1 + 1.0, a1)
        c2 = QB.band_decomposition(a2 + 3.0, a2)
        p = QB.pool_bands([c1, c2])
        assert p["n_rows"] == 50
        assert abs(p["gridmean_gap_ppr"] - (40 * 1.0 + 10 * 3.0) / 50) < 1e-9


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 the arm parameters — prior-fold OOF only, nothing silently defaulted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ledger(n=400, mean_point=7.0, mean_y=7.4, mean_pi=0.6, leg_scale=1.0):
    w = _qb_weights()
    leg = np.where(w != 0, 2.0, 0.0)
    return {"n": n, "sum_point": n * mean_point, "sum_y": n * mean_y, "sum_pi": n * mean_pi,
            "sum_leg_mean": list(n * leg), "sum_realized": list(n * leg * leg_scale),
            "weights": [float(v) for v in w]}


class TestArmParameters:
    def test_fold_one_has_no_prior_and_is_identity_by_construction(self):
        for arm in QB.REAL_ARMS:
            p = QB.fit_arm_params(arm, [])
            assert p["eligible"] is False
            assert "prior OOF rows" in p["reason"]

    def test_below_the_minimum_prior_rows_the_arm_is_ineligible_not_defaulted(self):
        assert QB.MIN_PRIOR_ROWS == 50
        p = QB.fit_arm_params("cond_shift", [_ledger(n=QB.MIN_PRIOR_ROWS - 1)])
        assert p["eligible"] is False

    def test_cond_shift_delta_is_the_point_gap_divided_by_mean_pi(self):
        p = QB.fit_arm_params("cond_shift", [_ledger(mean_point=7.0, mean_y=7.4, mean_pi=0.5)])
        assert p["eligible"] is True
        assert abs(p["delta"] - (7.4 - 7.0) / 0.5) < 1e-12

    def test_a_kappa_outside_the_registered_band_makes_the_scale_arm_ineligible(self):
        p = QB.fit_arm_params("cond_scale", [_ledger(mean_point=1.0, mean_y=9.0)])
        assert p["eligible"] is False and "outside the registered band" in p["reason"]
        assert QB.MIN_SCALE == 0.5 and QB.MAX_SCALE == 2.0

    def test_a_negative_kappa_makes_leg_scale_INELIGIBLE_OUTRIGHT_never_clipped(self):
        """NF-D16: a negative scale inverts a leg — refused, not clipped into the band."""
        led = _ledger()
        led["sum_realized"] = [-abs(v) for v in led["sum_realized"]]
        p = QB.fit_arm_params("leg_scale", [led])
        assert p["eligible"] is False and "INELIGIBLE outright" in p["reason"]

    def test_an_immaterial_leg_keeps_kappa_one_and_is_listed(self):
        """The NF-W6 materiality lesson at the PARAMETER level: a leg that cannot move the level
        contributes only noise through its ratio."""
        led = _ledger()
        w = _qb_weights()
        i = list(FA.LEGS).index("two_pt")
        led["sum_leg_mean"][i] = led["n"] * (QB.MIN_LEG_CONTRIB_PPR / abs(w[i]) / 10.0)
        led["sum_realized"][i] = led["n"] * 5.0
        p = QB.fit_arm_params("leg_scale", [led])
        assert p["eligible"] is True
        assert "two_pt" in p["immaterial_legs"]
        assert p["kappa"][i] == 1.0

    def test_too_many_out_of_band_legs_makes_leg_scale_ineligible_for_the_fold(self):
        led = _ledger()
        w = _qb_weights()
        priced = [i for i in range(FA.N_LEGS) if w[i] != 0.0]
        for i in priced[:len(priced) // 2 + 1]:
            led["sum_realized"][i] = led["sum_leg_mean"][i] * 9.0     # κ = 9, out of band
        p = QB.fit_arm_params("leg_scale", [led])
        assert p["eligible"] is False and "out of band" in p["reason"]

    def test_permute_kappa_preserves_the_population_and_destroys_the_assignment(self):
        """NF-D10's matched-foil discipline: the anchor must keep the corrections and lose their
        per-leg meaning."""
        w = _qb_weights()
        priced = [i for i in range(FA.N_LEGS) if w[i] != 0.0]
        k = np.ones(FA.N_LEGS)
        for j, i in enumerate(priced):
            k[i] = 1.0 + 0.1 * j
        perm = QB.permute_kappa(k, priced)
        assert sorted(perm[priced]) == sorted(k[priced])
        assert not np.array_equal(perm[priced], k[priced])
        assert np.array_equal(perm[[i for i in range(FA.N_LEGS) if i not in priced]],
                              k[[i for i in range(FA.N_LEGS) if i not in priced]])

    def test_an_unknown_arm_is_refused(self):
        with pytest.raises(KeyError):
            QB.fit_arm_params("not_registered", [_ledger()])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Selection — the constraints are FLOORS, never targets
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _bias(**kw):
    return {a: {"abs_pooled": v, "se": 0.001} for a, v in kw.items()}


def _ok(*arms, failing=None):
    failing = failing or {}
    return {a: {"pit_preserved": failing.get(a, ("pit" not in failing.get(a, ""))) is not False
                and failing.get(a) != "pit",
                "no_crps_harm": failing.get(a) != "crps"} for a in arms}


class TestSelection:
    def test_an_arm_failing_a_hard_constraint_is_not_selectable_even_with_the_smallest_bias(self):
        bias = _bias(cond_shift=0.01, cond_scale=0.20, avail_relevel=0.30, leg_scale=0.40)
        clauses = _ok(*QB.REAL_ARMS, failing={"cond_shift": "pit"})
        assert QB.select_arm(bias, clauses) == "cond_scale"

    def test_a_crps_harm_also_disqualifies(self):
        bias = _bias(cond_shift=0.01, cond_scale=0.02, avail_relevel=0.30, leg_scale=0.40)
        clauses = _ok(*QB.REAL_ARMS, failing={"cond_shift": "crps", "cond_scale": "crps"})
        assert QB.select_arm(bias, clauses) == "avail_relevel"

    def test_nothing_admissible_returns_None_rather_than_a_least_bad_arm(self):
        bias = _bias(**{a: 0.1 for a in QB.REAL_ARMS})
        clauses = {a: {"pit_preserved": False, "no_crps_harm": True} for a in QB.REAL_ARMS}
        assert QB.select_arm(bias, clauses) is None

    def test_a_tie_breaks_to_the_registered_simplicity_order(self):
        bias = {a: {"abs_pooled": 0.20, "se": 0.05} for a in QB.REAL_ARMS}
        bias["leg_scale"]["abs_pooled"] = 0.199
        clauses = _ok(*QB.REAL_ARMS)
        assert QB.select_arm(bias, clauses) == "cond_shift", (
            "within 1 SE the registered SIMPLICITY order decides — a 0.001 PPR edge must not buy "
            "a 13-parameter arm that re-levels a certified per-stat marginal")

    def test_the_pit_bar_is_a_floor_and_buys_no_credit_for_exceeding_it(self):
        """E2.1-r / NF1.8: a constraint a degenerate satisfies is fine because the objective
        eliminates it; a CRITERION a degenerate wins is fatal. Selection reads |bias| only."""
        src = _strip_comments(_MODULE.read_text())
        fn = src[src.index("def select_arm("):src.index("def body_verdict(")]
        assert "pit_preserved" in fn and "no_crps_harm" in fn
        assert "pit_pooled" not in fn and "max_decile_dev" not in fn, (
            "selection must not rank on PIT headroom — that criterion is monotone in widening")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Family C + the verdict
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestBanksMoveDeliberately:
    def test_an_arm_that_cannot_act_is_refused_not_passed(self):
        """NF-D20: a mechanism with nothing to act on is a FINDING, never a pass."""
        assert QB.banks_move_deliberately(arm_acts_by_fold=[True, False, True],
                                          non_qb_identical=True) is False

    def test_a_moved_non_qb_bank_refuses_the_arm(self):
        """This story re-levels QB and NOTHING else — a WR or TE bank that moved means the
        harness changed something it never registered."""
        assert QB.banks_move_deliberately(arm_acts_by_fold=[True, True],
                                          non_qb_identical=False) is False

    def test_a_genuine_qb_only_move_passes(self):
        assert QB.banks_move_deliberately(arm_acts_by_fold=[True, True],
                                          non_qb_identical=True) is True

    def test_no_fold_is_UNDEFINED_never_a_verdict(self):
        assert QB.banks_move_deliberately(arm_acts_by_fold=[], non_qb_identical=True) is None


class TestArchitectureState:
    def test_the_assembly_dominates_when_it_alone_clears_the_pit_bar_and_ties_elsewhere(self):
        s = QB.architecture_state(pit_folds_assembly=7, pit_folds_direct=0, n_folds=7,
                                  crps_delta=np.zeros(7), bias_delta=np.zeros(7))
        assert s["state"] == QB.A_ASSEMBLY

    def test_direct_points_dominates_when_it_wins_level_and_nothing_is_lost(self):
        s = QB.architecture_state(pit_folds_assembly=7, pit_folds_direct=7, n_folds=7,
                                  crps_delta=np.zeros(7),
                                  bias_delta=np.full(7, 0.3) + np.linspace(0, 0.01, 7))
        assert s["state"] == QB.A_DIRECT

    def test_a_split_decision_is_the_CLASSIFIED_NULL_neither_side_can_claim(self):
        """⭐ The story card's classified-null arm: the assembly holds PIT and CRPS, the
        comparator holds the level — a genuine disagreement, disclosed rather than resolved."""
        s = QB.architecture_state(pit_folds_assembly=7, pit_folds_direct=0, n_folds=7,
                                  crps_delta=np.full(7, 0.02) + np.linspace(0, 1e-3, 7),
                                  bias_delta=np.full(7, 0.30) + np.linspace(0, 1e-3, 7))
        assert s["state"] == QB.A_UNRESOLVED
        assert s["assembly_wins"]["pit"] and s["direct_points_wins"]["bias"]

    def test_a_tie_on_every_axis_is_unresolved_because_a_tie_is_not_a_win(self):
        s = QB.architecture_state(pit_folds_assembly=7, pit_folds_direct=7, n_folds=7,
                                  crps_delta=np.zeros(7), bias_delta=np.zeros(7))
        assert s["state"] == QB.A_UNRESOLVED

    def test_below_two_folds_it_DID_NOT_RUN_and_is_never_read_as_a_result(self):
        s = QB.architecture_state(pit_folds_assembly=1, pit_folds_direct=0, n_folds=1,
                                  crps_delta=np.zeros(1), bias_delta=np.zeros(1))
        assert s["state"] == QB.A_UNRESOLVED and s["evaluable"] is False


def _all_pass():
    return {c: True for c in QB.ARM_CLAUSES}


class TestVerdict:
    def test_every_registered_state_is_reachable(self):
        seen = {
            QB.body_verdict(harness_ok=False, winner=None, winner_clauses=None, gap_closed=None,
                            architecture=None, hybrid_closes_gap=None, max_mde_ppr=None)["state"],
            QB.body_verdict(harness_ok=True, winner="cond_shift", winner_clauses=_all_pass(),
                            gap_closed=True, architecture=None, hybrid_closes_gap=None,
                            max_mde_ppr=0.2)["state"],
            QB.body_verdict(harness_ok=True, winner=None, winner_clauses=None, gap_closed=None,
                            architecture={"state": QB.A_DIRECT}, hybrid_closes_gap=True,
                            max_mde_ppr=0.2)["state"],
            QB.body_verdict(harness_ok=True, winner="cond_shift", winner_clauses=_all_pass(),
                            gap_closed=False, architecture={"state": QB.A_UNRESOLVED},
                            hybrid_closes_gap=False, max_mde_ppr=0.2)["state"],
        }
        assert seen == set(QB.VERDICT_STATES)

    def test_cross_rankable_is_true_ONLY_when_the_gap_actually_closes(self):
        for gap_closed, clauses in ((False, _all_pass()), (True, {**_all_pass(),
                                                                 "dsr_ok": False}),
                                    (None, _all_pass())):
            v = QB.body_verdict(harness_ok=True, winner="cond_shift", winner_clauses=clauses,
                                gap_closed=gap_closed, architecture=None, hybrid_closes_gap=None,
                                max_mde_ppr=0.2)
            assert v["cross_rankable"] is False
        v = QB.body_verdict(harness_ok=True, winner="cond_shift", winner_clauses=_all_pass(),
                            gap_closed=True, architecture=None, hybrid_closes_gap=None,
                            max_mde_ppr=0.2)
        assert v["state"] == QB.V_CLOSED and v["cross_rankable"] is True

    def test_a_single_failing_clause_refuses_the_arm(self):
        for clause in QB.ARM_CLAUSES:
            c = _all_pass()
            c[clause] = False
            v = QB.body_verdict(harness_ok=True, winner="cond_shift", winner_clauses=c,
                                gap_closed=True, architecture=None, hybrid_closes_gap=None,
                                max_mde_ppr=0.2)
            assert v["state"] == QB.V_PERSISTS, f"`{clause}` did not refuse the arm"

    def test_the_hybrid_state_needs_BOTH_dominance_and_a_closed_gap(self):
        base = dict(harness_ok=True, winner=None, winner_clauses=None, gap_closed=None,
                    max_mde_ppr=0.2)
        assert QB.body_verdict(**base, architecture={"state": QB.A_DIRECT},
                               hybrid_closes_gap=False)["state"] == QB.V_PERSISTS
        assert QB.body_verdict(**base, architecture={"state": QB.A_UNRESOLVED},
                               hybrid_closes_gap=True)["state"] == QB.V_PERSISTS
        assert QB.body_verdict(**base, architecture={"state": QB.A_DIRECT},
                               hybrid_closes_gap=True)["state"] == QB.V_HYBRID

    def test_undefined_never_licenses_cross_rankability(self):
        v = QB.body_verdict(harness_ok=False, winner="cond_shift", winner_clauses=_all_pass(),
                            gap_closed=True, architecture=None, hybrid_closes_gap=None,
                            max_mde_ppr=0.2)
        assert v["state"] == QB.V_UNDEFINED and v["cross_rankable"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The runner — paths, precision, and the deploy-held posture
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRunnerDiscipline:
    def test_the_runner_refuses_to_write_a_decided_predecessors_path(self):
        src = _strip_comments(_RUNNER.read_text())
        for dec in ("nf_w8_0_cross_position", "nf_w8_0_rows", "nf_w8_0_input",
                    "nf_w8_0b_tail_point", "nf_w8_0b_rows", "nf_w8_0b_input"):
            assert f'"{dec}"' in src, f"`{dec}` is missing from the import-time path refusal"
        assert "raise RuntimeError" in src

    def test_no_stored_score_is_rounded_away_from_the_pin_tolerance(self):
        """⛔ FULL PRECISION IS LOAD-BEARING: a `round(…, 6)` caps every reproduction pin at
        ~5e-7 against a 1e-9 tolerance and the decisive run returns UNDEFINED (NF-W8-0's smoke)."""
        src = _strip_comments(_RUNNER.read_text())
        fn = src[src.index("def _score_arm("):src.index("def run_qb_arms(")]
        assert "round(" not in fn, "a rounded score cannot satisfy a 1e-9 reproduction pin"

    def test_the_runner_is_deploy_held_and_touches_no_serving_surface(self):
        """Checked on the IMPORT GRAPH and on real string literals — never on prose, which a
        docstring saying "no boto3" would satisfy (INC-38: prose must not satisfy a guard)."""
        for path in (_RUNNER, _MODULE):
            tree = ast.parse(path.read_text())
            mods: set[str] = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    mods |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module:
                    mods.add(n.module.split(".")[0])
            assert not (mods & {"boto3", "botocore", "dagster", "snowflake"}), (
                f"{path.name} imports a serving/infra module — this story is deploy-held")
            lits = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                    and isinstance(n.value, str)}
            assert not any("--publish" == v.strip() for v in lits)

    def test_the_runner_writes_no_optimizer_input(self):
        """Prereg §9: NF-W8-0b's shipped input stands untouched — regenerating it is a
        SUCCESSOR's step, never a side effect of this run."""
        src = _strip_comments(_RUNNER.read_text())
        assert "_write_input" not in src and "_INPUT_DIR" not in src
        assert any("writes NO optimizer input" in b for b in QB.PROMOTE_BLOCKERS)

    def test_the_reproduction_pins_fail_closed_on_an_absent_record(self, monkeypatch):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0c_qb_body as R
        monkeypatch.setattr(R, "_W7F_REL", "does/not/exist.json")
        out = R._w7f_qb_pins([{"label": "x", "qb": {"arms": {}}}])
        assert out["reproduces"] is False and "DID NOT RUN" in out["note"]

    def test_a_path_proof_record_is_never_read_as_a_pin(self, monkeypatch, tmp_path):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0c_qb_body as R
        p = tmp_path / "smoke.json"
        p.write_text(json.dumps({"story": "NF-W7f", "smoke": True, "fold_results": []}))
        monkeypatch.setattr(R, "_PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(R, "_W7F_REL", "smoke.json")
        assert R._w7f_qb_pins([])["reproduces"] is False

    def test_an_unformable_oracle_raises_rather_than_being_skipped(self):
        """NF1.7 (a): a CEILING that failed to fit is a failed control, never a pass — and the
        per-form ceilings are what the captured-fraction reading rests on (NF-D16 (g‴))."""
        tree = ast.parse(_RUNNER.read_text())
        fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
               and n.name == "run_qb_arms"]
        assert len(fns) == 1, "run_qb_arms must exist exactly once for this guard to bind"
        loops = [n for n in ast.walk(fns[0]) if isinstance(n, ast.For)
                 and any(isinstance(x, ast.Attribute) and x.attr == "ORACLE_OF"
                         for x in ast.walk(n))]
        assert loops, "no oracle-BUILDING loop found — the guard would pass on nothing"
        for loop in loops:
            assert any(isinstance(x, ast.Raise) for x in ast.walk(loop)), (
                "the oracle loop must RAISE on a ceiling that could not be formed")

    def test_the_smoke_keeps_enough_folds_for_an_arm_to_be_fitted_at_all(self):
        """Prereg §4 makes fold 1 identity BY CONSTRUCTION, so a one-fold path proof exercises
        NONE of the declared field — a smoke that cannot see the arms is the NF1.7 (a) shape
        applied to the proof itself."""
        src = _strip_comments(_RUNNER.read_text())
        m = re.search(r"folds = folds\[-(\d+):\]", src)
        assert m, "the smoke's fold slice was not found — the guard would pass on nothing"
        assert int(m.group(1)) >= 2, (
            "a single-fold smoke leaves every arm at identity by construction")

    def test_the_classification_scope_note_names_family_b_only(self):
        src = _strip_comments(_RUNNER.read_text())
        assert "FAMILY B ONLY" in src and "misleading-trigger" in src, (
            "a published fold trigger must be scoped to the FITTED contest (NF-D18)")

    def test_classify_null_is_called_with_the_declared_field_size(self):
        """MH2.7: `classify_null` must be told the DECLARED field or its remedy re-commits the
        selection bias it exists to deflate."""
        tree = ast.parse(_RUNNER.read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "classify_null"]
        assert calls, "no classify_null call found — the guard would pass on nothing"
        for c in calls:
            kw = {k.arg for k in c.keywords}
            assert "declared_field_size" in kw and "degenerates_excluded_from_v" in kw


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The end-to-end path proof on SYNTHETIC banks (no lake, no W6d dispatch)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _synthetic_feat(seed: int = 101) -> pd.DataFrame:
    """A frame shaped like the W6d matrix: `WP.TEST_BLOCKS`' seasons × 18 weeks × enough players
    per position that the dependence estimator's own row floor is met on every fold's train slice
    (an under-rowed fixture would exercise a REFUSAL path, not the runner path)."""
    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WPm
    rng = np.random.default_rng(seed)
    seasons = sorted({s for s, _ in WPm.TEST_BLOCKS})
    seasons = [seasons[0] - 1, *seasons]           # one prior season so fold 1 has a train slice
    players = 14
    rows = []
    gw = 0
    for season in seasons:
        for week in range(1, 19):
            gw += 1
            for pos in XP.POSITIONS:
                for k in range(players):
                    rows.append({"position": pos, "season": season, "week": week, "gw": gw,
                                 "gsis_id": f"{pos}-{k:03d}"})
    df = pd.DataFrame(rows)
    for f in WPm.FEATURES:
        if f not in df.columns:
            df[f] = rng.normal(size=len(df))
    # ⭐ a LEARNABLE availability signal: ~40% of player-weeks are all-zero (the atom the mixture
    # exists to price) and the event is driven by the first feature, so π̂ is a real estimate
    # rather than a degenerate constant — a fixture whose π̂ collapses would exercise a REFUSAL
    # path and prove nothing about the runner (NF1.7 (a), on the fixture side)
    drive = df[WPm.FEATURES[0]].to_numpy(float)
    active = (drive + rng.normal(scale=0.5, size=len(df))) > -0.25
    for leg in FA.LEGS:
        df[leg] = np.round(np.abs(rng.normal(size=len(df))) * 3.0, 1) * active
    return df


def test_the_full_runner_path_runs_end_to_end_on_synthetic_banks(monkeypatch, tmp_path):
    """⭐ THE IN-SESSION PATH PROOF. The real `--smoke` needs the W6d marginal dispatch
    (~370–600 s/fold cold, no cache on this machine) and is therefore an OPERATOR command; this
    exercises the SAME runner functions — `run_fold` → `derive_0c` → `write_report` — with only
    the marginal banks and the direct-points learner stubbed. Every reproduction pin necessarily
    FAILS on synthetic banks, so the verdict must be UNDEFINED: that is the correct answer and it
    proves the fail-closed path (NF1.7 (a))."""
    from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KWm
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0_cross_position as W80m
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0c_qb_body as R

    feat = _synthetic_feat()
    smap = {f"{p}|{leg}": {"source": "synthetic"} for p in XP.POSITIONS for leg in FA.LEGS}

    def _banks(fold_label, train, test, smap_, *, matrix_key, rebuild=False):
        rng = np.random.default_rng(abs(hash(fold_label)) % 2**31)
        out = {}
        pos = test["position"].astype(str).to_numpy()
        for cell in smap_:
            n = int((pos == cell.split("|", 1)[0]).sum())
            b = np.sort(rng.gamma(2.0, 2.0, size=(n, FA.N_LEVELS)), axis=1)
            b[:, : FA.N_LEVELS // 2] = 0.0
            out[cell] = b
        return out, "synthetic"

    def _direct(train, test, features, target, *, y_train=None):
        rng = np.random.default_rng(7)
        return np.sort(rng.gamma(2.0, 3.0, size=(len(test), FA.N_LEVELS)), axis=1)

    monkeypatch.setattr(W80m, "_marginals_cached", _banks)
    monkeypatch.setattr(R, "_marginals_cached", _banks, raising=False)
    monkeypatch.setattr(KWm, "fit_direct_points", _direct)
    monkeypatch.setattr(FA, "MIN_ESTIMATION_ROWS", 5, raising=False)

    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WPm
    folds = WPm.build_folds(feat)
    assert folds, "the synthetic frame produced no folds — the path proof would test nothing"

    ledgers: list[dict] = []
    fold_results = []
    for f in folds[:3]:
        fr, led = R.run_fold(f, feat, smap, draws=48, matrix_key="synthetic",
                             rows_dir=tmp_path / "rows", prior_ledgers=list(ledgers))
        fold_results.append(fr)
        if led:
            ledgers.append(led)
    out = R.derive_0c({"story": QB.STORY, "generated_at": "synthetic", "gate_league": "full_ppr",
                       "n_folds": len(fold_results), "fold_results": fold_results})
    assert out["verdict"]["state"] == QB.V_UNDEFINED, (
        "synthetic banks cannot reproduce any certified record — the harness MUST report "
        "UNDEFINED rather than a verdict (NF1.7 (a))")
    assert out["cross_rankable"] is False
    assert out["family_a"]["mechanism"]["identity_holds"] is True, (
        "the §3.1 identity must hold on the REAL runner path, not only in a unit fixture")
    assert out["family_a"]["bands"]["n_folds"] >= 1
    assert out["family_a"]["mechanism"]["max_abs_linearity_residual"] <= QB.IDENTITY_TOLERANCE

    # ⭐ NON-VACUITY: "it ran" is not a path proof. Every declared arm must have been FITTED,
    # ASSEMBLED and have ACTED on at least one fold, and every per-form oracle must have been
    # formed — otherwise this test would pass with the whole field silently absent (NF1.7 (a)).
    last = fold_results[-1]["qb"]["arms"]
    for arm in QB.REAL_ARMS:
        assert arm in last, f"`{arm}` never reached the scoring layer"
        assert last[arm]["params"].get("eligible") is True, f"`{arm}` was never fitted"
        assert last[arm]["acts"] is True, f"`{arm}` produced the incumbent's own bank"
    for anchor in QB.ANCHOR_ARMS:
        assert anchor in last, f"anchor `{anchor}` was never scored"
    assert QB.COMPARATOR in last, "family C's comparator was never scored"
    assert set(out["family_b"]["oracle_ceilings"]) == set(QB.REAL_ARMS), (
        "one ceiling PER FORM is the registered design (NF-D16 (g‴))")
    assert out["family_b"]["over_anchor"]["abs_pooled"] is not None
    assert out["family_c"]["state"] in QB.ARCHITECTURE_STATES

    R.write_report(out, tmp_path / "report.md")
    md = (tmp_path / "report.md").read_text()
    assert QB.V_UNDEFINED in md and "Family A" in md and "Promote blockers" in md


@pytest.mark.slow          # 7.7s — the repo's >5s marker rule; it lands in the slow gate,
                          # never in the fast one (CLAUDE.md marker discipline)
def test_the_winner_present_branch_executes_and_renders(monkeypatch, tmp_path):
    """⭐ The `winner is None` path proof above CANNOT reach the deflation, the classification or
    the winner half of the report — on synthetic banks no arm clears the PIT floor, which is the
    floor working as designed. So this drives the SAME derivation with the PIT bar patched HIGH
    **purely to reach the code path**.

    ⛔ This is NOT a re-read of a gate (E2.1-r) and it asserts NOTHING about any verdict: it
    asserts only that PBO/DSR compute, that `classify_null` is reached with the declared field,
    and that `write_report` renders the winner half — because a crash there lands AFTER an
    ~80-minute decisive run."""
    from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KWm
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0_cross_position as W80m
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0c_qb_body as R
    from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WPm

    feat = _synthetic_feat()
    smap = {f"{p}|{leg}": {"source": "synthetic"} for p in XP.POSITIONS for leg in FA.LEGS}

    def _banks(fold_label, train, test, smap_, *, matrix_key, rebuild=False):
        rng = np.random.default_rng(abs(hash(fold_label)) % 2**31)
        pos = test["position"].astype(str).to_numpy()
        out = {}
        for cell in smap_:
            n = int((pos == cell.split("|", 1)[0]).sum())
            b = np.sort(rng.gamma(2.0, 2.0, size=(n, FA.N_LEVELS)), axis=1)
            b[:, : FA.N_LEVELS // 2] = 0.0
            out[cell] = b
        return out, "synthetic"

    def _direct(train, test, features, target, *, y_train=None):
        rng = np.random.default_rng(7)
        return np.sort(rng.gamma(2.0, 3.0, size=(len(test), FA.N_LEVELS)), axis=1)

    monkeypatch.setattr(W80m, "_marginals_cached", _banks)
    monkeypatch.setattr(R, "_marginals_cached", _banks, raising=False)
    monkeypatch.setattr(KWm, "fit_direct_points", _direct)
    monkeypatch.setattr(FA, "MIN_ESTIMATION_ROWS", 5, raising=False)
    monkeypatch.setattr(QB, "PIT_MAX_DECILE_DEV", 1.0)      # reach the path, judge nothing

    folds = WPm.build_folds(feat)
    ledgers: list[dict] = []
    fold_results = []
    for f in folds[:6]:
        fr, led = R.run_fold(f, feat, smap, draws=32, matrix_key="synthetic",
                             rows_dir=tmp_path / "rows", prior_ledgers=list(ledgers))
        fold_results.append(fr)
        if led:
            ledgers.append(led)
    out = R.derive_0c({"story": QB.STORY, "generated_at": "synthetic",
                       "gate_league": "full_ppr", "n_folds": len(fold_results),
                       "fold_results": fold_results})
    fb = out["family_b"]
    assert fb["winner"] in QB.REAL_ARMS, "the winner-present branch was not reached"
    assert set(QB.ARM_CLAUSES) <= set(fb["winner_clauses"]), "a registered clause was not computed"
    assert fb["pbo"] is not None and fb["dsr"] is not None
    assert out["family_a_prime"].get(fb["winner"]) is not None, (
        "family A′ must be re-tested UNDER the winner, not only under identity")
    assert out["gap_closed_under_winner"] in (True, False)
    # the pins still fail on synthetic banks, so the verdict stays UNDEFINED — the winner-present
    # machinery must run to completion WITHOUT that turning into a verdict (NF1.7 (a))
    assert out["verdict"]["state"] == QB.V_UNDEFINED and out["cross_rankable"] is False
    R.write_report(out, tmp_path / "report.md")
    md = (tmp_path / "report.md").read_text()
    assert f"`{fb['winner']}`" in md and "oracle ceilings" in md and "Family C" in md


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The committed record, once the decisive run lands
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.skipif(not _RECORD.exists(), reason="the decisive record has not landed yet")
class TestCommittedRecord:
    def _rec(self):
        return json.loads(_RECORD.read_text())

    def test_the_record_is_not_a_path_proof_and_reaches_a_registered_state(self):
        r = self._rec()
        assert r.get("smoke") is not True
        assert r["verdict"]["state"] in QB.VERDICT_STATES

    def test_every_identity_the_headline_rests_on_holds_in_the_artifact(self):
        """NF-W8-0b §12.5(e): when a conclusion rests on an arithmetic identity, ASSERT the
        identity against the artifact — a bound quoted from a differently-pooled summary of the
        same quantity is a different number wearing the same name."""
        r = self._rec()
        assert r["family_a"]["mechanism"]["identity_holds"] is True
        bands = r["family_a"]["bands"]
        assert abs(bands["band_sum_residual"]) <= QB.IDENTITY_TOLERANCE

    def test_no_clause_listed_as_failing_is_finally_true(self):
        """NF-W8-0 §12.4: the classification must describe the FINAL clause values."""
        r = self._rec()
        cl = (r.get("classification") or {})
        final = r["family_b"]["winner_clauses"]
        for c in (cl.get("failing_anchor_checks", []) + cl.get("failing_statistical_checks", [])):
            assert final.get(c) is not True, f"`{c}` is listed failing but is finally True"

    def test_cross_rankable_matches_the_verdict_state(self):
        r = self._rec()
        assert r["cross_rankable"] == (r["verdict"]["state"] == QB.V_CLOSED)

    def test_a_published_trigger_is_scoped_to_the_fitted_contest(self):
        r = self._rec()
        if (r.get("classification") or {}).get("retest_trigger"):
            assert "FAMILY B ONLY" in r["classification_scope"]
