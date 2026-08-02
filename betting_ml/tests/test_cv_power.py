"""test_cv_power.py — MH2 guards.

Two things are being pinned, and they are different in kind:

  1. **The instrument reproduces the RECORD.** A power diagnostic whose numbers disagree with
     results already on file is not evidence about anything, so E7.9's fold count, E7.12-S6's
     false-fire rate, E7.14's certifiability floor and E7.15-H3's DSR figures are all asserted
     against their stored values.
  2. **The H8 fix cannot manufacture an ADD.** MH2 is a DIAGNOSTIC story that nonetheless changes a
     live gate, so the safety property has to be mechanical rather than argued: the calibrated
     clause must be weakly STRICTER than the legacy clause at every fold count, and must re-decide
     none of the 8 ADDs on the record.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils.cv_power import (
    FOLD_CONSISTENCY_ALPHA,
    LEGACY_FOLD_WIN_RATE,
    MIN_FOLDS_FOR_PBO,
    achievable_folds,
    classify_null,
    decompose_field_size,
    dsr_benchmark_sr0,
    dsr_ceiling,
    dsr_from_sr,
    dsr_max_field_size,
    dsr_required_sr,
    fold_consistency_clause,
    fold_gate_false_fire,
    folds_for_sign_certifiability,
    folds_to_clear_dsr,
    pbo_evaluable,
    seasons_for_folds,
    sign_test_floor,
)
from betting_ml.utils.overfitting import deflated_sharpe

ABL = Path(__file__).resolve().parents[2] / \
    "quant_sports_intel_models/baseball/edge_program/ablation_results"


def _calibrated_only(n: int) -> int | None:
    """The sign-test count WITHOUT the legacy floor — used only to prove the crossover exists."""
    from betting_ml.utils.cv_power import _binom_sf

    return next((i for i in range(1, n + 1) if _binom_sf(i, n) <= FOLD_CONSISTENCY_ALPHA), None)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 1. Fold arithmetic
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestFoldArithmetic:
    def test_it_reproduces_E7_9s_recorded_fold_count(self):
        """E7.9's matrix spans 2021→2026 (6 seasons) and it reported 3 purged folds."""
        assert achievable_folds(6) == 3

    def test_the_serving_window_measured_on_the_store_would_yield_8_folds(self):
        """2016–2026 = 11 seasons. The single actionable finding of the story, pinned as a number
        so a later reader cannot soften it into a vague 'more folds'."""
        assert achievable_folds(11) == 8

    @pytest.mark.parametrize("n", range(0, 20))
    def test_seasons_for_folds_inverts_achievable_folds(self, n):
        assert achievable_folds(seasons_for_folds(n)) == max(n, 0)

    def test_pbo_is_undefined_not_failed_below_four_folds(self):
        assert not pbo_evaluable(3, 10)
        assert pbo_evaluable(MIN_FOLDS_FOR_PBO, 10)

    def test_purging_does_not_remove_folds(self):
        """`achievable_folds` claims to describe `PurgedWalkForwardSplit`; that is only true if
        purging trims TRAINING ROWS and never drops a fold. Verified against the real splitter
        rather than asserted from its docstring."""
        from betting_ml.utils.cv import PurgedWalkForwardSplit

        rng = np.random.default_rng(0)
        rows = []
        for yr in range(2021, 2027):
            for d in pd.date_range(f"{yr}-04-01", f"{yr}-09-30", freq="3D"):
                rows.append({"game_date": d, "game_year": yr, "x": rng.normal()})
        df = pd.DataFrame(rows).reset_index(drop=True)
        sp = PurgedWalkForwardSplit()
        folds = list(sp.split(df, feature_cols=["x_30d"]))
        assert len(folds) == achievable_folds(6) == 3
        assert all(len(tr) > 0 for tr, _ in folds)


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 2. H8 — the fold-consistency clause
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestH8Diagnosis:
    def test_it_reproduces_E7_12_S6s_simulated_false_fire_rate(self):
        """S6 SIMULATED 0.4968; the closed form is exactly 0.5 (P(Bin(3,½) ≥ 2))."""
        assert fold_gate_false_fire(3) == pytest.approx(0.5, abs=1e-12)
        assert abs(fold_gate_false_fire(3) - 0.4968) < 0.01

    def test_the_legacy_clauses_meaning_drifts_by_a_factor_of_two(self):
        """The finding itself: the clause is not one gate, it is a different gate at every n."""
        rates = [fold_gate_false_fire(n) for n in range(3, 12)]
        assert max(rates) / min(rates) > 1.8
        assert fold_gate_false_fire(11) == pytest.approx(0.2744, abs=1e-3)

    def test_the_placebo_clearing_nine_of_eleven_is_unremarkable(self):
        """E7.12-S5's placebo cleared the clause 9 times in 11. At a ~27% per-shot false-fire rate
        that is an ordinary outcome, not an anomaly — which is the point of the diagnosis."""
        p = fold_gate_false_fire(11)
        assert 0.25 < p < 0.30
        # P(≥9 of 11 independent shots clear) is not tiny under the null
        assert sum(math.comb(11, k) * p**k * (1 - p) ** (11 - k) for k in range(9, 12)) > 1e-6


class TestH8Fix:
    @pytest.mark.parametrize("n", range(2, 81))
    def test_the_calibrated_clause_is_weakly_stricter_at_every_fold_count(self, n):
        """⭐ THE SAFETY PROPERTY THAT MAKES THIS SAFE TO SHIP INSIDE A DIAGNOSTIC STORY. If the
        required win count is never BELOW the legacy one, adopting the clause can only prevent a
        false ADD and can never manufacture one."""
        cl = fold_consistency_clause(n)
        assert cl.is_stricter_than_legacy
        if cl.attainable:
            assert cl.wins_required >= cl.legacy_wins_required

    @pytest.mark.parametrize("n", range(3, 41))
    def test_the_false_fire_rate_is_bounded_by_alpha_at_every_fold_count(self, n):
        cl = fold_consistency_clause(n)
        if cl.attainable:
            assert cl.attained_false_fire <= FOLD_CONSISTENCY_ALPHA + 1e-12

    def test_it_declares_itself_UNDEFINED_rather_than_passing_when_unattainable(self):
        """At 2 folds the smallest attainable false-fire rate is 0.25 > α, so no win count makes
        the clause meaningful. NF1.7 (a): a clause that cannot run has not passed."""
        assert not fold_consistency_clause(2).attainable
        assert fold_consistency_clause(3).attainable

    def test_it_would_have_stopped_the_three_fold_coin_flip(self):
        """The concrete E7.12-S6 case: at 3 folds the legacy clause is a coin flip and the
        calibrated one demands unanimity."""
        cl = fold_consistency_clause(3)
        assert cl.legacy_wins_required == 2 and cl.legacy_false_fire == pytest.approx(0.5)
        assert cl.wins_required == 3 and cl.attained_false_fire == pytest.approx(0.125)

    def test_it_re_decides_none_of_the_recorded_ADDs(self):
        """⭐ VERDICT-NEUTRALITY, VERIFIED AGAINST THE STORED RECORD RATHER THAN ASSERTED. Every
        recorded ADD is re-checked against the calibrated clause; any flip would mean MH2 had
        quietly un-shipped part of the served configuration."""
        clause = fold_consistency_clause(11)
        checked = 0
        for f in sorted(ABL.glob("*/*_summary.json")):
            d = json.loads(f.read_text())
            for pm in (d.get("per_metric") or {}).values():
                if not isinstance(pm, dict) or str(pm.get("verdict", "")).upper() != "ADD":
                    continue
                lb = pd.DataFrame(pm["leaderboard"])
                if "fold_win_rate" not in lb.columns or "selectable" not in lb.columns:
                    continue
                sel = lb[lb["selectable"].astype(bool) & lb.get("active", True).astype(bool)]
                if sel.empty:
                    continue
                n_folds = len(pd.DataFrame(pm.get("mae_by_fold") or {}).index) or 11
                wins = int(round(float(sel.iloc[0]["fold_win_rate"]) * n_folds))
                cl = fold_consistency_clause(n_folds) if n_folds != 11 else clause
                assert cl.passes(wins), (
                    f"{f.name}: a recorded ADD ({sel.iloc[0]['arm']}, {wins}/{n_folds}) would be "
                    f"re-decided by the calibrated clause — MH2 is diagnostic and must not "
                    f"un-ship anything")
                checked += 1
        assert checked >= 6, f"expected the recorded ADDs to be found and checked, saw {checked}"

    def test_the_sign_test_alone_would_become_LOOSER_past_about_thirty_folds(self):
        """The reason `fold_consistency_clause` takes `max(legacy, calibrated)`. A fixed-alpha sign
        test asymptotically demands a rate tending to 0.50, so past the crossover the calibrated
        count ALONE would admit arms the legacy 60% bar rejects — the one thing a diagnostic story
        must not do. Pinned so the max can never be 'simplified' away."""
        crossings = [n for n in range(3, 81)
                     if _calibrated_only(n) is not None
                     and _calibrated_only(n) < math.ceil(LEGACY_FOLD_WIN_RATE * n)]
        assert crossings, "the crossover is the premise of the max(); it must exist"
        assert min(crossings) > 11, (
            "the crossover must sit ABOVE every fold count the program runs today, or the two "
            "clauses would already be in conflict on live tiers")
        for n in crossings:
            assert fold_consistency_clause(n).wins_required == math.ceil(LEGACY_FOLD_WIN_RATE * n)

    def test_the_alpha_sensitivity_that_the_report_discloses_is_real(self):
        """The report states that α=0.10 WOULD re-decide the 8/11 ADDs. If that ever stopped being
        true the disclosure would be stale, which is worse than no disclosure."""
        strict = fold_consistency_clause(11, alpha=0.10)
        assert strict.wins_required == 9
        assert not strict.passes(8)          # the four 0.73 (=8/11) ADDs
        assert fold_consistency_clause(11).passes(8)


class TestSignFloor:
    def test_it_reproduces_E7_14s_recorded_certifiability_requirement(self):
        """E7.14 recorded a two-sided floor of 0.0625 at 5 folds and `folds_required_to_certify=8`
        against a rank-1 BH cutoff of 0.010."""
        assert sign_test_floor(5, two_sided=True) == pytest.approx(0.0625)
        assert folds_for_sign_certifiability(0.010, two_sided=True) == 8

    def test_the_floor_makes_a_null_a_statement_about_the_design(self):
        assert sign_test_floor(3) == pytest.approx(0.125)
        assert sign_test_floor(11) < 0.001


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 3. DSR — agreement with the shipped implementation, and the field-size axis
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestDSRAgreesWithTheShippedImplementation:
    def test_the_closed_form_matches_deflated_sharpe_on_a_real_series(self):
        """`dsr_from_sr` re-derives what `overfitting.deflated_sharpe` computes. If these ever
        diverge the power table is describing a gate the program does not run."""
        rng = np.random.default_rng(7)
        for seed_shift in range(5):
            s = rng.normal(0.3, 1.0, 11) + seed_shift * 0.05
            trials = list(rng.normal(0.0, 0.5, 7))
            res = deflated_sharpe(s, n_trials=7, trial_sharpes=trials)
            rc, sd0 = s - s.mean(), s.std(ddof=0)
            sk = float((rc**3).mean() / sd0**3)
            ku = float((rc**4).mean() / sd0**4)
            mine = dsr_from_sr(res.observed_sr, n_obs=len(s), n_trials=7,
                               var_trials_sr=float(np.var(trials, ddof=1)), skew=sk, kurt=ku)
            assert mine == pytest.approx(res.dsr, abs=1e-9)

    def test_required_sr_inverts_dsr_from_sr(self):
        for n_obs, n_trials in ((3, 28), (5, 9), (11, 7), (8, 4)):
            need = dsr_required_sr(n_obs=n_obs, n_trials=n_trials, var_trials_sr=1.0 / n_obs)
            assert dsr_from_sr(need, n_obs=n_obs, n_trials=n_trials,
                               var_trials_sr=1.0 / n_obs) == pytest.approx(0.95, abs=1e-4)


class TestDSRCeiling:
    def test_three_folds_leaves_almost_no_headroom_above_the_gate(self):
        """The structural bound that reframes E7.9: at 3 observations the LARGEST attainable DSR is
        0.977 at an infinite Sharpe, against a 0.95 gate."""
        assert dsr_ceiling(3) == pytest.approx(0.9772, abs=1e-3)
        assert dsr_ceiling(3) > 0.95            # passable in principle…
        assert dsr_ceiling(3) - 0.95 < 0.03     # …but with essentially no headroom

    def test_the_ceiling_rises_with_observations(self):
        vals = [dsr_ceiling(n) for n in (3, 4, 6, 11)]
        assert vals == sorted(vals)

    def test_no_attainable_sharpe_exceeds_the_ceiling(self):
        """The ceiling is a bound, so nothing may beat it — the oracle-floor discipline pointed at
        this module's own arithmetic (E2.1-r)."""
        for sr in (1.0, 5.0, 50.0, 1e4):
            assert dsr_from_sr(sr, n_obs=3, n_trials=2, var_trials_sr=0.0) <= dsr_ceiling(3) + 1e-9


class TestFieldSizeAxis:
    def test_dsr_is_monotone_decreasing_in_the_arm_count(self):
        prev = 1.0
        for n in (2, 3, 5, 7, 12, 28, 60):
            d = dsr_from_sr(1.0, n_obs=11, n_trials=n, var_trials_sr=0.3)
            assert d <= prev + 1e-12
            prev = d

    def test_max_field_size_is_the_threshold_it_claims_to_be(self):
        """Chosen so the threshold falls INSIDE the search range: a saturating case returns the
        `max_trials` cap, at which point `k+1` was never evaluated and asserting on it would be
        testing the cap rather than the threshold."""
        sr, v = 1.1, 0.25
        k = dsr_max_field_size(observed_sr=sr, n_obs=11, var_trials_sr=v, max_trials=500)
        assert 2 <= k < 500, f"fixture saturated the search cap (k={k}) — pick a harder case"
        assert dsr_from_sr(sr, n_obs=11, n_trials=k, var_trials_sr=v) >= 0.95
        assert dsr_from_sr(sr, n_obs=11, n_trials=k + 1, var_trials_sr=v) < 0.95

    def test_it_reproduces_the_E7_15_H3_field_size_flip(self):
        """⭐ THE VALIDATION CASE. Same winner, same folds, same effect — only the field changed."""
        p = ABL / "e7_15_artifacts/e7_15_h3_summary.json"
        if not p.exists():                                     # pragma: no cover - corpus optional
            pytest.skip("E7.15-H3 artifact not present")
        d = json.loads(p.read_text())

        def _sr(x):
            x = np.asarray(x, float)
            x = x[np.isfinite(x)]
            sd = float(np.std(x, ddof=1))
            return float(np.mean(x) / sd) if sd > 0 else 0.0

        for metric, wide_recorded in (("bb_pct", 0.6065), ("iso", 0.6573)):
            pm = d["per_metric"][metric]
            mae = pd.DataFrame(pm["mae_by_fold"])
            lb = pd.DataFrame(pm["leaderboard"])
            elig = [a for a in lb.loc[lb["selectable"], "arm"]
                    if a in mae.columns and a != "L0_foil"]
            traj = [a for a in elig if a.startswith(("T1_", "T2_"))]
            skill = pd.DataFrame(mae[["L0_foil"]].to_numpy(float) - mae.to_numpy(float),
                                 index=mae.index, columns=mae.columns)
            win = pm["dsr"]["eligible"]["arm"]
            s = skill[win].dropna().to_numpy(float)
            rc, sd0 = s - s.mean(), s.std(ddof=0)
            sk, ku = float((rc**3).mean() / sd0**3), float((rc**4).mean() / sd0**4)
            v_wide = float(np.var([_sr(skill[c]) for c in elig], ddof=1))
            v_narrow = float(np.var([_sr(skill[c]) for c in traj], ddof=1))
            wide = dsr_from_sr(_sr(s), n_obs=len(s), n_trials=len(elig),
                               var_trials_sr=v_wide, skew=sk, kurt=ku)
            narrow = dsr_from_sr(_sr(s), n_obs=len(s), n_trials=len(traj),
                                 var_trials_sr=v_narrow, skew=sk, kurt=ku)
            assert wide == pytest.approx(wide_recorded, abs=2e-3)
            assert wide < 0.95 <= narrow, (
                f"{metric}: the recorded field-size flip did not reproduce ({wide} → {narrow})")

    def test_a_post_hoc_trimmed_family_is_NOT_evidence(self):
        """⭐ THE TWO-SIDED HALF OF THE FIELD-SIZE RULE. E7.15-H3's recorded "clears at 0.998 over
        the 2-arm trajectory family" drops `T3_tenure`, a NAMED member of that family in H3's own
        pre-registration. Scored against the family as DECLARED, nothing clears. Pinned because the
        0.998 figure is quoted in the story record and would otherwise be carried forward as
        "basically there"."""
        p = ABL / "e7_15_artifacts/e7_15_h3_summary.json"
        if not p.exists():                                     # pragma: no cover - corpus optional
            pytest.skip("E7.15-H3 artifact not present")
        d = json.loads(p.read_text())

        def _sr(x):
            x = np.asarray(x, float)
            x = x[np.isfinite(x)]
            sd = float(np.std(x, ddof=1))
            return float(np.mean(x) / sd) if sd > 0 else 0.0

        pm = d["per_metric"]["bb_pct"]
        mae = pd.DataFrame(pm["mae_by_fold"])
        skill = pd.DataFrame(mae[["L0_foil"]].to_numpy(float) - mae.to_numpy(float),
                             index=mae.index, columns=mae.columns)
        declared = ["T1_traj_ladder", "T2_traj_raw", "T3_tenure"]
        assert all(a in mae.columns for a in declared), "the declared family must be in the run"
        best = max(declared, key=lambda c: skill[c].mean())
        s = skill[best].dropna().to_numpy(float)
        rc, sd0 = s - s.mean(), s.std(ddof=0)
        sk, ku = float((rc**3).mean() / sd0**3), float((rc**4).mean() / sd0**4)
        full = dsr_from_sr(_sr(s), n_obs=len(s), n_trials=len(declared),
                           var_trials_sr=float(np.var([_sr(skill[c]) for c in declared], ddof=1)),
                           skew=sk, kurt=ku)
        trimmed = dsr_from_sr(_sr(s), n_obs=len(s), n_trials=2,
                              var_trials_sr=float(np.var([_sr(skill[c]) for c in declared[:2]],
                                                         ddof=1)), skew=sk, kurt=ku)
        assert trimmed >= 0.95 > full, (
            "the point of this guard is that the POST-HOC field clears and the DECLARED one does "
            f"not (declared={full:.3f}, trimmed={trimmed:.3f})")
        assert full == pytest.approx(0.849, abs=0.01)

    def test_the_decomposition_separates_the_two_channels(self):
        """Shrinking a field moves BOTH the trial count and the trial dispersion; reporting only
        the count under-explains the change and invites 'just run fewer arms'."""
        dec = decompose_field_size(observed_sr=1.0, n_obs=11, n_trials_wide=7, var_wide=0.40,
                                   n_trials_narrow=2, var_narrow=0.001)
        assert dec["dsr_narrow_field"] > dec["dsr_wide_field"]
        assert dec["sr0_narrow"] < dec["sr0_wide"]
        assert dec["dsr_if_only_dispersion_shrank"] > dec["dsr_wide_field"]
        assert dec["dsr_if_only_trial_count_shrank"] > dec["dsr_wide_field"]

    def test_a_bigger_field_never_helps(self):
        """The sign of the axis, asserted so a future refactor cannot silently invert it."""
        assert dsr_benchmark_sr0(28, 0.3) > dsr_benchmark_sr0(4, 0.3) > dsr_benchmark_sr0(2, 0.3)


class TestFoldsToClearDSR:
    def test_unreachable_is_returned_for_the_right_reason(self):
        """`SR ≤ SR0` ⇒ no fold count ever clears. The closed-form reason the old search could only
        discover by exhausting a 4,000-fold horizon."""
        v = 0.5
        sr0 = dsr_benchmark_sr0(7, v)
        assert folds_to_clear_dsr(observed_sr=sr0 * 0.9, n_trials=7, var_trials_sr=v) is None
        assert folds_to_clear_dsr(observed_sr=sr0 * 1.5, n_trials=7, var_trials_sr=v) is not None

    def test_the_returned_fold_count_actually_clears_and_one_fewer_does_not(self):
        v = 0.05
        k = folds_to_clear_dsr(observed_sr=1.2, n_trials=7, var_trials_sr=v)
        assert k is not None
        assert dsr_from_sr(1.2, n_obs=k, n_trials=7, var_trials_sr=v) >= 0.95
        assert dsr_from_sr(1.2, n_obs=k - 1, n_trials=7, var_trials_sr=v) < 0.95

    def test_the_asymptotic_fallback_branch_shrinks_V_as_the_gate_does(self):
        """When fewer than two trial Sharpes exist `deflated_sharpe` uses `V = 1/n_obs`, which is a
        function of n. The extrapolation must follow that branch or it extrapolates a bar the gate
        does not use."""
        k = folds_to_clear_dsr(observed_sr=0.09, n_trials=2, var_trials_sr=1.0 / 11,
                               n_obs_now=11, var_is_asymptotic_fallback=True)
        assert k is not None and k > 11
        assert dsr_from_sr(0.09, n_obs=k, n_trials=2,
                           var_trials_sr=(1.0 / 11) * (11.0 / k)) >= 0.95

    def test_a_non_positive_sharpe_is_never_rescued_by_folds(self):
        assert folds_to_clear_dsr(observed_sr=-0.4, n_trials=5, var_trials_sr=0.1) is None
        assert folds_to_clear_dsr(observed_sr=-0.4, n_trials=2, var_trials_sr=0.09,
                                  n_obs_now=11, var_is_asymptotic_fallback=True) is None

    def test_it_does_not_inherit_the_np_resize_sharpe_inflation(self):
        """The DEFECT-1 regression. Tiling a series with `np.resize` inflates its ddof=1 Sharpe by
        ≈√(n/(n−1)); the closed form must hold the Sharpe genuinely fixed."""
        rng = np.random.default_rng(3)
        s = rng.normal(1.2, 1.0, 11)          # a Sharpe comfortably above SR0, so both are finite
        sr_true = float(np.mean(s) / np.std(s, ddof=1))
        sr_tiled = float(np.mean(np.resize(s, 400)) / np.std(np.resize(s, 400), ddof=1))
        assert sr_tiled > sr_true * 1.02, "fixture no longer demonstrates the inflation"
        v = 0.05
        honest = folds_to_clear_dsr(observed_sr=sr_true, n_trials=7, var_trials_sr=v)
        optimistic = folds_to_clear_dsr(observed_sr=sr_tiled, n_trials=7, var_trials_sr=v)
        assert honest is not None and optimistic is not None
        assert honest > optimistic, "the inflated Sharpe must look EASIER — that was the defect"


# ══════════════════════════════════════════════════════════════════════════════════════════════════
# 4. The null classifier
# ══════════════════════════════════════════════════════════════════════════════════════════════════


class TestClassifyNull:
    def _base(self, **kw):
        d = dict(metric="iso", n_folds=11, n_arms=7, beats_foil=True,
                 observed_sr=2.0, var_trials_sr=0.02)
        d.update(kw)
        return classify_null(**d)

    def test_inactive_outranks_every_power_state(self):
        """E7.15's `xwoba_against`: zero within-player transitions. Neither underpowered nor a bug —
        and mislabelling it sent a session hunting a defect that did not exist."""
        v = self._base(active=False)
        assert v.state == "INACTIVE"
        assert v.folds_needed is None

    def test_an_unrecorded_fold_count_is_UNKNOWN_not_UNDEFINED(self):
        """'not read' and 'too few' have different remedies; conflating them lets the inventory
        emit a fabricated re-test trigger for a study whose design it never read."""
        assert self._base(n_folds=0).state == "UNKNOWN"
        assert self._base(n_folds=3).state == "UNDEFINED"

    def test_a_negative_point_estimate_is_a_GENUINE_ABSENCE_with_no_trigger(self):
        v = self._base(beats_foil=False)
        assert v.state == "GENUINE_ABSENCE"
        assert v.retest_trigger is None, \
            "no sample size rescues a negative point estimate — quoting one would be a lie"

    def test_DSR_UNREACHABLE_outranks_POWER_LIMITED_and_names_the_right_remedy(self):
        """Its remedy is a SMALLER FIELD, not more seasons. Reporting 'needs N more seasons' — which
        a naive search does — is an actively misleading trigger."""
        v = self._base(observed_sr=0.05, var_trials_sr=0.5)
        assert v.state == "DSR_UNREACHABLE"
        assert "field" in (v.retest_trigger or "").lower()
        assert v.folds_needed is None

    def test_power_limited_states_its_trigger_in_FOLDS_not_seasons(self):
        """The fold RULE differs per tier, so this function — which does not know the tier — must
        not do the calendar arithmetic (an earlier cut produced a '36-season window' for a
        cohort-based study)."""
        v = self._base(observed_sr=0.9, var_trials_sr=0.06)
        if v.state == "POWER_LIMITED":
            assert "fold" in (v.retest_trigger or "")
            assert "season window" not in (v.retest_trigger or "")

    def test_trustworthy_dead_requires_the_design_to_reach_the_meaningful_effect(self):
        dead = self._base(observed_sr=None, var_trials_sr=None,
                          mde_sd_units=0.5, meaningful_sd_units=1.0)
        limited = self._base(observed_sr=None, var_trials_sr=None,
                             mde_sd_units=3.0, meaningful_sd_units=1.0)
        assert dead.state == "TRUSTWORTHY_DEAD"
        assert limited.state == "POWER_LIMITED"

    def test_the_default_with_no_statistics_is_POWER_LIMITED_not_dead(self):
        """A null is trustworthy only when something was COMPUTED to make it so; the safe default
        must be the one that does not retire a live mechanism on no evidence."""
        v = classify_null(metric="x", n_folds=11, n_arms=5, beats_foil=True)
        assert v.state == "POWER_LIMITED"
