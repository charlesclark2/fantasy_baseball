"""Guards for NF-W7b (`joint_draw.py` + `kdst_weekly_joint.py` + its runner) — the DST
dependence successor: a Gaussian-copula joint draw over NF-W7's FROZEN component marginals.

Discipline carried from the NF-W line:
  · every AND-composed gate clause has its own ISOLATING fixture (NF-D17);
  · red-proofs assert the mutation LANDED (E11.24 #682);
  · iterating guards assert NON-VACUITY first (DSR-CONV #690);
  · fast gate: pure modules + the runner's SOURCE only — no lake IO, no `pipeline`, no network.

The load-bearing contracts:
  · ⛔ the marginals are NOT refit — mechanically: the copula at Σ=I is BYTE-IDENTICAL to the
    independent draw (common random numbers), so the layer can add ONLY dependence;
  · the dependence knob provably MOVES the gated statistic (NF-MARGIN2/NF-D20);
  · an unevaluable Σ̂ REFUSES, never silently becomes independence (NF1.7 (a));
  · a coverage-only refusal classifies CONSTRAINT_REFUSED with THIS story's mechanism prose,
    while NF-W7's default prose is byte-stable (backward compatibility).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly_joint as KWJ

_FANTASY = Path(KWJ.__file__).resolve().parent
_RUNNER = _FANTASY / "run_nf_w7b_dst_joint.py"
_W7_RECORD = _FANTASY / "ablation_results" / "nf_w7_kdst_weekly.json"

_RNG = np.random.default_rng(7)


# ── Pre-registration pins ───────────────────────────────────────────────────────────────────────
class TestPreregistrationPins:
    def test_family_is_at_least_the_section_0_5_minimum(self):
        assert len(KWJ.REAL_ARMS) >= 3
        assert len(set(KWJ.REAL_ARMS)) == len(KWJ.REAL_ARMS)

    def test_foils_and_floor_are_nf_w7s_verbatim(self):
        assert KWJ.FOILS == KW.LAYER_B_FOILS
        assert KWJ.COVERAGE_FLOOR == KW.COVERAGE_FLOOR == 0.80
        assert KWJ.COVERAGE_BLOCK_SE == KW.COVERAGE_BLOCK_SE
        assert (KWJ.PBO_MAX, KWJ.DSR_MIN, KWJ.FDR_Q) == (KW.PBO_MAX, KW.DSR_MIN, KW.FDR_Q)

    def test_frozen_marginals_match_the_committed_nf_w7_record(self):
        """⛔ the binding constraint: this story consumes NF-W7's Layer-A score-best DST arms
        VERBATIM — a drift here would silently re-select the marginals."""
        rec = json.loads(_W7_RECORD.read_text())
        assert len(KWJ.COMPONENT_LEGS) == 7  # non-vacuity
        for leg in KWJ.COMPONENT_LEGS:
            assert KWJ.FROZEN_DST_WINNERS[leg] == rec["winners"][leg], leg

    def test_component_legs_cover_exactly_the_dst_scoring_map_plus_pa(self):
        assert set(KWJ.COMPONENT_LEGS[:-1]) == set(KW.DST_LINEAR_POINTS)
        assert KWJ.COMPONENT_LEGS[-1] == "pa_bucket"

    def test_comonotone_flips_only_the_pa_leg(self):
        """Tier points DECREASE in the PA bucket, so the points-direction comonotone flips PA
        and nothing else."""
        assert len(KWJ.COMONOTONE_FLIP) == len(KWJ.COMPONENT_LEGS)
        flipped = [leg for leg, fl in zip(KWJ.COMPONENT_LEGS, KWJ.COMONOTONE_FLIP) if fl]
        assert flipped == ["pa_bucket"]

    def test_comonotone_sits_in_the_degenerate_set(self):
        assert "assembled_comonotone" in KWJ.DEGENERATES

    def test_eligible_field_is_arms_plus_foils_and_never_anchors(self):
        assert KWJ.ELIGIBLE == (*KWJ.REAL_ARMS, *KWJ.FOILS)
        assert not set(KWJ.ELIGIBLE) & set(KWJ.ANCHORS)

    def test_runner_reads_constants_and_asserts_the_frozen_record(self):
        src = _RUNNER.read_text()
        assert "assert_frozen_winners_match_the_record" in src
        assert "FROZEN_DST_WINNERS" in src
        assert "coverage_constraint_refusal" in src


# ── Correlation-matrix hygiene ──────────────────────────────────────────────────────────────────
class TestCorrHygiene:
    def test_psd_clamp_repairs_a_non_psd_matrix(self):
        bad = np.array([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]])
        assert np.linalg.eigvalsh(bad).min() < 0  # non-vacuity: it IS broken
        fixed = JD.psd_clamp(bad)
        assert np.linalg.eigvalsh(fixed).min() >= 0
        assert np.allclose(np.diag(fixed), 1.0)

    def test_psd_clamp_is_identity_on_a_valid_matrix(self):
        good = np.array([[1.0, 0.3], [0.3, 1.0]])
        assert np.allclose(JD.psd_clamp(good), good, atol=1e-9)

    def test_scale_offdiagonal_doubles_small_correlations_exactly(self):
        c = np.array([[1.0, 0.2], [0.2, 1.0]])
        out = JD.scale_offdiagonal(c, 2.0)
        assert np.isclose(out[0, 1], 0.4)
        assert np.allclose(np.diag(out), 1.0)

    def test_scale_offdiagonal_clips_before_repair(self):
        c = np.array([[1.0, 0.6], [0.6, 1.0]])
        out = JD.scale_offdiagonal(c, 2.0)
        assert out[0, 1] <= JD.MAX_ABS_OFFDIAG + 1e-9

    def test_one_factor_recovers_a_true_one_factor_structure(self):
        lam = np.array([0.8, -0.5, 0.3])
        true = np.outer(lam, lam)
        np.fill_diagonal(true, 1.0)
        est, lam_hat = JD.one_factor_corr(true)
        assert np.allclose(est, true, atol=1e-6)
        # loadings identified up to a global sign
        assert (np.allclose(lam_hat, lam, atol=1e-6)
                or np.allclose(lam_hat, -lam, atol=1e-6))


# ── Estimation layer ────────────────────────────────────────────────────────────────────────────
class TestEstimation:
    def test_z_corr_recovers_a_known_rho(self):
        chol = np.linalg.cholesky(np.array([[1.0, 0.6], [0.6, 1.0]]))
        z = _RNG.standard_normal((20000, 2)) @ chol.T
        est, n = JD.estimate_corr_from_z(z)
        assert n == 20000
        assert abs(est[0, 1] - 0.6) < 0.03

    def test_estimation_refuses_below_min_rows_instead_of_defaulting_to_identity(self):
        """NF1.7 (a): an unevaluable dependence estimate must not masquerade as independence."""
        z = _RNG.standard_normal((JD.MIN_ESTIMATION_ROWS - 1, 3))
        with pytest.raises(ValueError, match="refused"):
            JD.estimate_corr_from_z(z)
        with pytest.raises(ValueError, match="refused"):
            JD.spearman_gauss_corr(z)

    def test_estimation_drops_incomplete_rows_before_counting(self):
        z = _RNG.standard_normal((JD.MIN_ESTIMATION_ROWS + 10, 2))
        z[: 11, 0] = np.nan
        with pytest.raises(ValueError, match="refused"):
            JD.estimate_corr_from_z(z)

    def test_spearman_gauss_maps_through_two_sin(self):
        chol = np.linalg.cholesky(np.array([[1.0, 0.5], [0.5, 1.0]]))
        m = _RNG.standard_normal((20000, 2)) @ chol.T
        est, _ = JD.spearman_gauss_corr(m)
        assert abs(est[0, 1] - 0.5) < 0.03

    def test_categorical_pit_is_flat_when_calibrated(self):
        p = np.tile(np.array([0.2, 0.5, 0.3]), (30000, 1))
        y = _RNG.choice(3, size=30000, p=[0.2, 0.5, 0.3])
        u = JD.randomized_pit_categorical(p, y, seed=0)
        hist, _ = np.histogram(u, bins=10, range=(0, 1))
        assert np.max(np.abs(hist / len(u) - 0.1)) < 0.02

    def test_sigma_for_arm_rejects_an_unregistered_arm(self):
        with pytest.raises(KeyError, match="pre-registered"):
            KWJ.sigma_for_arm("joint_vine", {}, None)


# ── The draw layer: marginal preservation + dependence ──────────────────────────────────────────
def _toy_inputs(n=40, rho=0.0):
    """Tiny count banks + a PA proba for assembly tests."""
    rng = np.random.default_rng(11)
    count_banks = {}
    for leg in KWJ.COMPONENT_LEGS[:-1]:
        mu = rng.uniform(0.3, 3.0, size=n)
        count_banks[leg] = KW.poisson_bank(mu)
    pa = rng.dirichlet(np.ones(9) * 2.0, size=n)
    return count_banks, pa


class TestJointDrawContracts:
    def test_identity_copula_is_byte_identical_to_the_independent_draw(self):
        """⭐ THE frozen-marginals contract, mechanically: at Σ=I under common random numbers the
        copula path must reproduce the independent draw EXACTLY — the layer adds only
        dependence."""
        cb, pa = _toy_inputs()
        eye = np.eye(len(KWJ.COMPONENT_LEGS))
        a = KWJ.assembled_bank(cb, pa, corr=eye, draws=400, seed=5)
        b = KWJ.assembled_bank(cb, pa, mode="indep", draws=400, seed=5)
        assert np.array_equal(a, b)

    def test_copula_uniform_marginals_are_uniform(self):
        corr = JD.psd_clamp(np.full((3, 3), 0.7) + 0.3 * np.eye(3))
        base = _RNG.standard_normal((200, 300, 3))
        u = JD.gaussian_copula_uniforms(base, corr)
        for i in range(3):
            hist, _ = np.histogram(u[..., i].ravel(), bins=10, range=(0, 1))
            assert np.max(np.abs(hist / u[..., i].size - 0.1)) < 0.01

    def test_comonotone_shares_one_uniform_and_flips_the_flagged_leg(self):
        base = _RNG.standard_normal((10, 20, 3))
        u = JD.comonotone_uniforms(base, (False, False, True))
        assert np.array_equal(u[..., 0], u[..., 1])
        assert np.allclose(u[..., 2], 1.0 - u[..., 0])

    def test_positive_dependence_widens_the_assembled_bank(self):
        """The MEASURED half of arm-movability on a synthetic fixture: comonotone > copula(0.6)
        > indep in central-interval width — dispersion moves monotonically with the knob."""
        cb, pa = _toy_inputs()
        L = len(KWJ.COMPONENT_LEGS)
        rho = JD.psd_clamp(np.full((L, L), 0.6) + 0.4 * np.eye(L))

        def width(bank):
            li = int(np.argmin(np.abs(KW.EVAL_LEVELS - 0.10)))
            hi = int(np.argmin(np.abs(KW.EVAL_LEVELS - 0.90)))
            q = np.sort(bank, axis=1)
            return float(np.mean(q[:, hi] - q[:, li]))

        w_ind = width(KWJ.assembled_bank(cb, pa, mode="indep", draws=2000, seed=3))
        w_cop = width(KWJ.assembled_bank(cb, pa, corr=rho, draws=2000, seed=3))
        w_com = width(KWJ.assembled_bank(cb, pa, mode="comonotone", draws=2000, seed=3))
        assert w_ind < w_cop < w_com

    def test_weighted_sum_variance_is_monotone_in_the_offdiagonal(self):
        """The ANALYTIC half of arm-movability."""
        sds = np.array([1.0, 2.0, 0.5])
        w = np.array([1.0, 2.0, 2.0])
        prev = -np.inf
        for rho in (0.0, 0.3, 0.6, 0.9):
            c = JD.psd_clamp(np.full((3, 3), rho) + (1 - rho) * np.eye(3))
            v = JD.weighted_sum_variance(c, sds, w)
            assert v > prev
            prev = v

    def test_assembly_marginal_mean_is_unmoved_by_dependence(self):
        """Dependence changes the SUM's dispersion, never any component's marginal — the
        assembled bank's MEAN must agree between indep and comonotone within MC noise."""
        cb, pa = _toy_inputs()
        a = KWJ.assembled_bank(cb, pa, mode="indep", draws=4000, seed=9)
        b = KWJ.assembled_bank(cb, pa, mode="comonotone", draws=4000, seed=9)
        # means over the dense-level grid approximate the distribution mean; the tolerance is
        # MC noise at 4000 draws on a sum with sd ≈ 10 — dependence moves DISPERSION by far
        # more than this (see the width test), so the check still discriminates
        assert abs(float(np.mean(a)) - float(np.mean(b))) < 0.5

    def test_unknown_mode_and_missing_corr_raise(self):
        cb, pa = _toy_inputs(n=5)
        with pytest.raises(ValueError):
            KWJ.assembled_bank(cb, pa, mode="copula", draws=10)
        with pytest.raises(ValueError):
            KWJ.assembled_bank(cb, pa, mode="anticomonotone", draws=10)


# ── Gate clauses: one isolating fixture per clause (NF-D17) ─────────────────────────────────────
def _sel(**over):
    sel = {
        "beats_foil": True, "mean_delta": 0.03, "ci95": (0.01, 0.05), "fold_wins": 7,
        "fold_clause": {"passes": True, "required": 6}, "pbo": 0.0, "dsr": 0.99,
        "p_one_sided": 0.005, "observed_sr": 1.2, "var_trials_sr": 0.001,
        "anchors": {"degenerates_lose": True, "winner_beats_permuted": True,
                    "permuted_lift_not_significant": True,
                    "oracle_floors_respected_at_matched_n": True},
        "coverage": {"winner_coverage_80": 0.815, "n_rows": 2174, "binomial_se": 0.0086,
                     "blocking_shortfall": False},
        "dependence_checks": {"incumbent_refusal_reproduces": True,
                              "dependence_moves_coverage": True,
                              "beats_indep_on_coverage": True},
    }
    deep = {k: v for k, v in over.items() if k in ("anchors", "coverage", "dependence_checks")}
    for k, v in deep.items():
        sel[k] = {**sel[k], **v}
    sel.update({k: v for k, v in over.items() if k not in deep})
    return sel


@pytest.fixture(scope="module")
def runner():
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7b_dst_joint as mod
    return mod


class TestGateClauses:
    def test_green_fixture_ships(self, runner):
        gate = runner.compose_gate_joint(_sel(), True)
        assert gate["ship"], gate["checks"]

    @pytest.mark.parametrize("over,check", [
        ({"beats_foil": False}, "beats_foil"),
        ({"fold_clause": {"passes": False, "required": 6}}, "fold_consistency"),
        ({"pbo": 0.5}, "pbo_ok"),
        ({"dsr": 0.5}, "dsr_ok"),
        ({"anchors": {"degenerates_lose": False}}, "degenerates_lose"),
        ({"anchors": {"winner_beats_permuted": False}}, "permutation_behaves"),
        ({"anchors": {"oracle_floors_respected_at_matched_n": False}},
         "oracle_floors_respected"),
        ({"coverage": {"blocking_shortfall": True}}, "coverage_floor_ok"),
        ({"dependence_checks": {"incumbent_refusal_reproduces": False}},
         "incumbent_refusal_reproduces"),
        ({"dependence_checks": {"dependence_moves_coverage": False}},
         "dependence_moves_coverage"),
        ({"dependence_checks": {"beats_indep_on_coverage": False}},
         "beats_indep_on_coverage"),
    ])
    def test_each_clause_refuses_alone(self, runner, over, check):
        gate = runner.compose_gate_joint(_sel(**over), True)
        assert not gate["ship"]
        reds = [k for k, v in gate["checks"].items() if not v]
        assert reds == [check], f"expected only {check} red, got {reds}"

    def test_fdr_clause_refuses_alone(self, runner):
        gate = runner.compose_gate_joint(_sel(), False)
        reds = [k for k, v in gate["checks"].items() if not v]
        assert reds == ["fdr_ok"]

    def test_clause_partition_matches_the_declared_sets(self, runner):
        gate = runner.compose_gate_joint(_sel(), True)
        assert set(gate["checks"]) == set(KWJ.STATISTICAL_CHECKS) | set(KWJ.ANCHOR_CHECKS)


class TestClassification:
    def test_coverage_only_refusal_uses_this_storys_mechanism_prose(self, runner):
        sel = _sel(coverage={"winner_coverage_80": 0.778, "blocking_shortfall": True})
        gate = runner.compose_gate_joint(sel, True)
        out = runner.classify_joint(sel, gate["checks"], 8)
        assert out["state"] == "CONSTRAINT_REFUSED"
        assert "UNDER-CORRECT" in out["reason"]
        assert "independence-simplification" not in out["reason"], (
            "NF-W7's mechanism prose is FALSE of a joint arm — the successor must state its own")
        assert out["retest_trigger"].startswith("NONE")

    def test_nf_w7_default_prose_is_byte_stable_without_the_new_kwargs(self):
        """Backward compatibility: the shared branch called the NF-W7 way must still emit the
        independence prose (the committed W7 record depends on it)."""
        sel = {"beats_foil": True, "mean_delta": 0.0338, "ci95": (0.0094, 0.0582),
               "fold_wins": 7, "fold_clause": {"passes": True, "required": 6},
               "p_one_sided": 0.0067,
               "coverage": {"winner_coverage_80": 0.7603, "n_rows": 2174,
                            "binomial_se": 0.0086, "blocking_shortfall": True}}
        checks = {"beats_foil": True, "fold_consistency": True, "pbo_ok": True, "dsr_ok": True,
                  "fdr_ok": True, "degenerates_lose": True, "permutation_behaves": True,
                  "oracle_floors_respected": True, "coverage_floor_ok": False}
        out = KW.coverage_constraint_refusal(sel, checks, {"state": "X"})
        assert "independence-simplification" in out["reason"]

    def test_anchor_only_refusal_is_constraint_refused_with_the_clause_named(self, runner):
        sel = _sel(dependence_checks={"incumbent_refusal_reproduces": False})
        gate = runner.compose_gate_joint(sel, True)
        out = runner.classify_joint(sel, gate["checks"], 8)
        assert out["state"] == "CONSTRAINT_REFUSED"
        assert out["failing_anchor_checks"] == ["incumbent_refusal_reproduces"]
        assert out["retest_trigger"] is None

    def test_a_statistical_refusal_falls_through_to_the_instrument(self, runner):
        sel = _sel(beats_foil=False, mean_delta=-0.01, observed_sr=-0.4)
        gate = runner.compose_gate_joint(sel, True)
        out = runner.classify_joint(sel, gate["checks"], 8)
        assert out["state"] not in ("CONSTRAINT_REFUSED",)
        assert "instrument_verdict" in out


# ── Deploy-held (research substrate only) ───────────────────────────────────────────────────────
class TestDeployHeld:
    @pytest.mark.parametrize("path", ["joint_draw.py", "kdst_weekly_joint.py",
                                      "run_nf_w7b_dst_joint.py"])
    def test_no_serving_or_upload_imports(self, path):
        src = (_FANTASY / path).read_text()
        body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        for tok in ("boto3", "put_object", "upload_file", "write_serving_store",
                    "requests.post"):
            assert tok not in body, f"{path} must not touch serving/upload surfaces ({tok})"

    def test_runner_writes_only_research_artifacts(self):
        src = _RUNNER.read_text()
        for m in re.finditer(r"write_text|to_parquet", src):
            line = src[:m.start()].rsplit("\n", 1)[-1] + src[m.start():].split("\n", 1)[0]
            assert ("_REPORT_DIR" in line or "json_path" in line or "path" in line), line
