"""NF-W8-0d — guards for the DSR gate-design FRONTIER instrument.

The story's whole load-bearing claim is an ARITHMETIC one — that a proportional dispersion lever
cannot flip an `SR ≤ SR0` refusal — so the guards pin the arithmetic, not the prose. Every clause
here was RED-proven against deliberately broken source
(`quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0d.py`).

⛔ FAST-GATE SAFE: nothing here imports `pipeline` (the E11.23 rule), touches the network, or reads
a Snowflake/S3 handle. The known-case fixture is LITERAL — it is NOT read back out of the artifact
the instrument writes, which would be the "a fixture that is the post-transform artifact cannot
test the transform" tautology (E9.64b / NF-C0e).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_dsr_frontier as DF
from quant_sports_intel_models.football.nfl.fantasy import nf1_1_model as M14

# ── the KNOWN (effect, design) → DSR case, as LITERALS (prereg §3 G0) ─────────────────────────
# NF-W8-0c's published QB level bias by arm over its 7 evaluable folds
# (2022H2, 2023H1, 2023H2, 2024H1, 2024H2, 2025H1, 2025H2), gate league full_ppr.
KNOWN_BIAS: dict[str, list[float]] = {
    "identity":      [-0.376163794298, -0.319740404618, -0.717830820221, -0.130446729453,
                      -0.863867381462, -0.528530490036, -0.264291991318],
    "cond_shift":    [-0.187262711439, -0.035795844753, -0.416458582416, +0.284839618159,
                      -0.496943127731, -0.078783051961, +0.189159181374],
    "cond_scale":    [-0.258716868344, -0.127523258868, -0.535335707381, +0.166663630507,
                      -0.627529291755, -0.214543569410, +0.024128451360],
    "avail_relevel": [-0.376918215477, -0.321627608010, -0.718378107484, -0.131853369297,
                      -0.864280839386, -0.530135933197, -0.266224849330],
    "leg_scale":     [+0.009484430335, +0.107360091813, -0.306951599941, +0.382679579478,
                      -0.427779145448, -0.043557531544, +0.144979552028],
}
KNOWN_N = [685.0, 683.0, 710.0, 685.0, 676.0, 671.0, 701.0]
KNOWN_SD_ERR = [5.916420963, 5.790585024, 6.000987184, 5.710074583, 6.694417874, 6.429423980,
                6.348068154]
#: NF-W8-0c's recorded family-B DSR. ⚠️ The literals above are carried to 12 dp ON PURPOSE: at the
#: record's printed 4 dp the reconstruction lands at 0.1644, so a 4-dp fixture would have forced a
#: 2e-3 tolerance and quietly stopped pinning anything at the resolution that matters.
KNOWN_DSR = 0.1654


def _known() -> DF.Observed:
    return DF.Observed(
        folds=("2022H2", "2023H1", "2023H2", "2024H1", "2024H2", "2025H1", "2025H2"),
        bias={a: np.asarray(v, float) for a, v in KNOWN_BIAS.items()},
        n_rows=np.asarray(KNOWN_N, float), sd_err=np.asarray(KNOWN_SD_ERR, float))


def _deltas():
    return DF.delta_series(_known().bias)


# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTheKnownCaseIsPinned:
    def test_the_known_effect_and_design_reproduce_the_recorded_dsr(self):
        """G0 — the frontier's own DSR path, on LITERAL published inputs, is NF-W8-0c's number.

        This is the pin the whole story rests on: if the instrument's arithmetic drifts from the
        gate's, every projected point is a projection of something else."""
        d = _deltas()
        assert M14.deflated_sharpe(d[DF.WINNER], DF.sharpes(d)) == KNOWN_DSR

    def test_the_winner_sharpe_sits_below_the_deflation_benchmark(self):
        """The premise of the whole verdict: `SR < SR0` at the observed design."""
        srs = DF.sharpes(_deltas())
        assert srs[DF.REAL_ARMS.index(DF.WINNER)] < DF._sr0_from(srs, len(DF.REAL_ARMS))

    def test_the_delta_series_is_the_absolute_bias_improvement_the_gate_reads(self):
        """A statistic guard: `δ = |b_I| − |b_a|`, so an arm that OVERSHOOTS is penalised.

        Pinned because the whole §2 kink argument is a property of THIS statistic — a silent switch
        to a signed or squared delta would leave every number plausible and every claim wrong."""
        d = _deltas()
        # 2024H1: identity −0.1304, cond_shift +0.2848 ⇒ the corrected arm is FURTHER from zero
        assert d[DF.WINNER][3] == pytest.approx(
            abs(KNOWN_BIAS["identity"][3]) - abs(KNOWN_BIAS["cond_shift"][3]), abs=1e-12)
        assert d[DF.WINNER][3] < 0


class TestTheLockstepInvariant:
    """§1 — the story's load-bearing proposition, made arithmetic."""

    def test_sign_of_sr_minus_sr0_is_invariant_under_proportional_shrinkage(self):
        rows = DF.lockstep_ladder(_deltas())
        signs = {r["sr_minus_sr0"] > 0 for r in rows}
        assert len(signs) == 1, "a proportional dispersion change must not flip the DSR gap's sign"

    def test_a_sharper_design_does_not_raise_dsr_when_the_gap_is_negative(self):
        rows = DF.lockstep_ladder(_deltas())
        assert all(r["sr_minus_sr0"] < 0 for r in rows)
        for a, b in zip(rows, rows[1:]):
            assert b["dsr"] <= a["dsr"] + 1e-12, (
                "with `SR < SR0` a sharper design must make DSR worse, never better — this is the "
                "finding that voids the 'a lower-variance design' prescription")

    def test_the_ladder_is_live_so_it_cannot_pass_on_nothing(self):
        """NF1.7 (a) — a ladder that does not move the arithmetic pins nothing."""
        assert DF.lockstep_is_live(DF.lockstep_ladder(_deltas()))
        flat = DF.lockstep_ladder(_deltas(), factors=(1.0, 1.0, 1.0))
        assert not DF.lockstep_is_live(flat), "an unmoving ladder must be reported as NOT live"

    def test_scaling_dispersion_holds_the_mean_fixed(self):
        d = _deltas()[DF.WINNER]
        for c in (0.5, 2.0):
            s = DF.scale_dispersion(d, c)
            assert s.mean() == pytest.approx(d.mean(), abs=1e-12)
            assert s.std(ddof=1) == pytest.approx(d.std(ddof=1) * c, rel=1e-12)


class TestTheSplitFieldCarrier:
    """The DSR-CONV shape (`V` from one set, `n_trials` from another) expressed THROUGH the gate's
    own function — never a second copy of the arithmetic (NF-W7k / NF-C0e)."""

    def test_it_is_a_byte_identical_no_op_when_no_arm_is_excluded(self):
        d = _deltas()
        srs = DF.sharpes(d)
        assert DF.dsr_split_field(d[DF.WINNER], srs, len(DF.REAL_ARMS)) == \
            M14.deflated_sharpe(d[DF.WINNER], srs)

    def test_the_carrier_transports_exactly_the_dispersion_and_the_length(self):
        srs = DF.sharpes(_deltas())
        keep = np.asarray([s for a, s in zip(DF.REAL_ARMS, srs) if a != "avail_relevel"])
        synth = DF.synth_trials_for_split_field(keep, 4)
        assert len(synth) == 4
        assert float(synth.std(ddof=1)) == pytest.approx(float(keep.std(ddof=1)), rel=1e-12)

    def test_excluding_the_inactive_arm_lowers_the_bar_but_does_not_clear_it(self):
        """The forward recommendation's own figure, pinned so a later edit cannot inflate it."""
        d = _deltas()
        srs = DF.sharpes(d)
        keep = np.asarray([s for a, s in zip(DF.REAL_ARMS, srs) if a != "avail_relevel"])
        dsr = DF.dsr_split_field(d[DF.WINNER], keep, len(DF.REAL_ARMS))
        assert dsr > M14.deflated_sharpe(d[DF.WINNER], srs)
        assert dsr < DF.DSR_MIN, ("R1 alone must NOT clear the bar at the observed design — a "
                                  "recommendation that quietly ships the refused arm is the "
                                  "E2.1-r inversion")

    @pytest.mark.parametrize("v_set,n", [(np.asarray([1.0]), 4), (np.asarray([1.0, 2.0]), 1),
                                         (np.asarray([1.0, 2.0, 3.0]), 2)])
    def test_a_carrier_that_cannot_be_formed_raises_rather_than_deflating_by_zero(self, v_set, n):
        """NF1.7 (a) — with <2 retained Sharpes the benchmark silently collapses to 0, i.e. NO
        deflation at all. That must RAISE, never pass."""
        with pytest.raises(ValueError):
            DF.synth_trials_for_split_field(v_set, n)


class TestTheDecompositionAndTheStructuralBound:
    def test_the_level_decomposition_reproduces_nf_w8_0c(self):
        dec = DF.level_decomposition(_known())
        assert dec["observed_fold_sd"] == pytest.approx(0.2607, abs=5e-4)
        assert dec["mean_within_fold_se"] == pytest.approx(0.2338, abs=5e-4)
        assert dec["excess_sd"] == pytest.approx(0.1146, abs=5e-4)
        assert dec["sampling_share_of_fold_variance"] == pytest.approx(0.807, abs=5e-3)

    def test_the_paired_difference_carries_a_negligible_share_of_the_level_noise(self):
        """§2 — the structural reason the rows/fold lever is weaker than the level suggests."""
        b = DF.paired_noise_bound(_known())
        assert b["paired_share_of_level_variance_bound"] < 0.01
        assert b["level_row_sd_ppr"] > 5.0

    def test_a_non_positive_excess_is_reported_not_clamped_away(self):
        """NF-W7k's `het_var` discipline: a residual at or below zero is a real reading."""
        obs = DF.Observed(folds=("a", "b", "c"),
                          bias={"identity": np.asarray([-0.4, -0.4, -0.4])},
                          n_rows=np.asarray([100.0] * 3), sd_err=np.asarray([6.0] * 3))
        dec = DF.level_decomposition(obs)
        assert dec["excess_is_non_positive"] and dec["excess_sd"] is None
        # ⭐ the REPORTED residual must itself be the un-clamped value — asserting only the derived
        # flag left the clause vacuous against a `max(excess, ε)` clamp (its own RED proof caught it)
        assert dec["excess_var"] <= 0.0


class TestTheFrontierRefusesRatherThanGuessing:
    def _model(self):
        return DF.fit_design_model(_known())

    def test_fewer_than_three_folds_raises_because_dsr_is_undefined(self):
        with pytest.raises(ValueError, match="UNDEFINED"):
            DF.simulate_design(self._model(), 700, 2, "persistent", reps=5)

    def test_an_unknown_scaling_law_raises_instead_of_defaulting(self):
        with pytest.raises(ValueError, match="unknown scaling law"):
            DF.simulate_design(self._model(), 700, 5, "optimistic", reps=5)

    def test_excluding_an_unknown_arm_raises(self):
        with pytest.raises(KeyError):
            DF.simulate_design(self._model(), 700, 5, "persistent", reps=5,
                               v_exclude=("no_such_arm",))

    def test_excluding_down_to_one_arm_raises(self):
        with pytest.raises(ValueError):
            DF.simulate_design(self._model(), 700, 5, "persistent", reps=5,
                               v_exclude=("cond_scale", "avail_relevel", "leg_scale"))

    def test_the_averaging_law_is_the_lever_favouring_one(self):
        """A DECLARED-bias check: `averaging` must shrink the non-sampling spread at a bigger
        fold, `persistent` must leave it alone."""
        m = self._model()
        assert DF._law_factor(m, m.rows_per_fold_0 * 4, "averaging") == pytest.approx(0.5, rel=1e-9)
        assert DF._law_factor(m, m.rows_per_fold_0 * 4, "persistent") == 1.0

    def test_the_simulation_is_deterministic_under_its_seed(self):
        m = self._model()
        a = DF.simulate_design(m, 700, 7, "persistent", reps=80, seed=5)
        b = DF.simulate_design(m, 700, 7, "persistent", reps=80, seed=5)
        assert a["dsr_median"] == b["dsr_median"]


class TestTheVerdictBindsOnTheMedian:
    def test_a_high_p_clear_with_a_sub_bar_median_is_still_answer_b(self):
        """prereg §3 — a design that only sometimes draws a lucky panel has NOT cleared; binding on
        `P(clear)` would re-admit the very selection bias DSR exists to deflate."""
        rows = [{"window": "w", "feasible": True, "dsr_median": 0.94, "p_clears": 0.49,
                 "n_folds": 8, "rows_per_fold": 700.0, "law": "persistent"}]
        v = DF.verdict(rows)
        assert v["answer"] == "b" and v["state"] == "NO_FEASIBLE_DESIGN_CLEARS"

    def test_a_median_at_the_bar_is_answer_a(self):
        rows = [{"window": "w", "feasible": True, "dsr_median": DF.DSR_MIN, "p_clears": 0.0,
                 "n_folds": 8, "rows_per_fold": 700.0, "law": "persistent"}]
        assert DF.verdict(rows)["answer"] == "a"

    def test_an_infeasible_point_can_never_carry_the_verdict(self):
        rows = [{"window": "unreachable", "feasible": False, "dsr_median": 0.99, "p_clears": 1.0,
                 "n_folds": 8, "rows_per_fold": 700.0, "law": "persistent"},
                {"window": "w", "feasible": True, "dsr_median": 0.10, "p_clears": 0.0,
                 "n_folds": 8, "rows_per_fold": 700.0, "law": "persistent"}]
        v = DF.verdict(rows)
        assert v["answer"] == "b"
        assert v["best_anywhere"]["dsr_median"] == 0.99  # reported a fortiori, never binding

    def test_an_empty_feasible_set_raises_rather_than_passing_on_nothing(self):
        with pytest.raises(ValueError, match="pass on nothing"):
            DF.verdict([{"window": "u", "feasible": False, "dsr_median": 0.99, "p_clears": 1.0,
                         "n_folds": 8, "rows_per_fold": 700.0, "law": "persistent"}])


class TestTheDeclaredConstantsAreInherited:
    def test_the_bar_is_inherited_and_not_restated(self):
        """E2.1-r — this story reads the bar, it does not set one."""
        from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
        assert DF.DSR_MIN == XP.DSR_MIN == 0.95

    def test_the_declared_field_stays_at_the_registered_minimum(self):
        assert DF.DECLARED_FIELD_SIZE == 4 == len(DF.REAL_ARMS)

    def test_the_granularity_floor_actually_excludes_points(self):
        """A non-vacuity check on a declared feasibility constraint: a floor that never binds is a
        constraint nobody can audit."""
        m = DF.fit_design_model(_known())
        grid = DF.frontier(m, windows=(("w", 4, True, "why"),), fold_counts=(8, 20),
                           laws=("persistent",), reps=20)
        flagged = [r for r in grid if not r["granularity_ok"]]
        assert flagged and all(r["block_weeks"] < DF.MIN_BLOCK_WEEKS for r in flagged)
        assert all(not r["feasible"] for r in flagged)

    def test_rows_per_season_matches_the_measured_folds(self):
        obs = _known()
        assert DF.QB_ROWS_PER_SEASON == pytest.approx(2 * float(obs.n_rows.mean()), rel=0.01)


class TestTheRecordReaderRefusesAnInconsistentRecord:
    def test_a_record_missing_an_evaluable_fold_raises(self):
        rec = {"family_b": {"evaluable_folds": ["a", "b", "c"]},
               "fold_results": [{"label": "a"}, {"label": "b"}]}
        # ⭐ `match=` is load-bearing: without it the clause passed on the INCIDENTAL KeyError the
        # downstream dict lookup raises anyway, i.e. it did not test the explicit refusal at all
        # (its own RED proof caught it — a guard passing for the wrong reason).
        with pytest.raises(KeyError, match="are absent from"):
            DF.load_observed(rec)

    def test_a_record_with_too_few_folds_raises(self):
        rec = {"family_b": {"evaluable_folds": ["a", "b"]}, "fold_results": []}
        with pytest.raises(ValueError, match="DSR needs"):
            DF.load_observed(rec)


def test_the_v_attribution_shares_sum_to_one_and_name_every_arm():
    """§4's mechanism table must cover the whole field — a share table that prints only the culprit
    cannot show the rest are unremarkable."""
    rows = DF.v_attribution(_deltas())
    assert [r["arm"] for r in rows] == list(DF.REAL_ARMS)
    assert math.isclose(sum(r["share_of_var_trial_sharpes"] for r in rows), 1.0, abs_tol=1e-9)
    top = max(rows, key=lambda r: r["share_of_var_trial_sharpes"])
    assert top["arm"] == "avail_relevel" and top["share_of_var_trial_sharpes"] > 0.5


def test_the_kink_free_alternative_is_recorded_as_losing():
    """An alternative that LOST is reported as losing, never quietly dropped (prereg §6)."""
    rows = {r["statistic"]: r for r in DF.alternative_statistic_field(_known().bias)}
    reg = next(v for k, v in rows.items() if "REGISTERED" in k)
    alt = next(v for k, v in rows.items() if "squared" in k)
    assert alt["dsr"] < reg["dsr"] < DF.DSR_MIN
