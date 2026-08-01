"""E7.13 Phase 2 — the comp-projection validation harness (`prospect_board/comp_validation.py`).

Fast-gate: pure numpy/pandas, no IO.

A bug in ANY scoring function here silently invalidates the whole verdict, and the failure mode is
never a crash — it is a plausible-looking number. So each metric is pinned against a case whose
answer is known in closed form, and each anchor is pinned by CONSTRUCTING the failure it exists to
detect (an inverted metric, an unstable pick, a de-clustered CI) and proving the statistic fires.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.prospect_board.comp_validation import (
    ARM_FIELD,
    bh_fdr,
    cluster_bootstrap_pvalue,
    crps_sample,
    deflated_sharpe,
    fold_plan,
    interval_coverage,
    pbo_cscv,
    pit_max_decile_deviation,
    randomized_pit,
    score_arm,
)

_RNG = np.random.default_rng(713)


# ── 1. CRPS ──────────────────────────────────────────────────────────────────────────────────

class TestCRPS:
    def test_point_mass_reduces_to_absolute_error(self):
        """A degenerate predictive at m must score exactly |m − y| — the closed form."""
        for m, y in ((0.0, 0.0), (0.0, 250.0), (100.0, 40.0)):
            assert crps_sample(np.array([m]), np.array([1.0]), y) == pytest.approx(abs(m - y))

    def test_two_point_case_matches_the_closed_form(self):
        """Predictive = ½δ(0) + ½δ(100), observation 0.
        E|X−y| = 50 ; ½E|X−X'| = ½·(2·¼·100) = 25 ; CRPS = 25."""
        assert crps_sample(np.array([0.0, 100.0]), np.array([1.0, 1.0]), 0.0) == pytest.approx(25.0)

    def test_is_proper_the_true_distribution_wins(self):
        """The property the whole verdict rests on: neither a nihilist nor a hedger can win it."""
        truth = _RNG.normal(100, 30, 4000)
        obs = _RNG.normal(100, 30, 500)
        correct = np.mean([crps_sample(truth, np.ones_like(truth), y) for y in obs])
        too_tight = np.mean([crps_sample(_RNG.normal(100, 5, 4000), np.ones(4000), y) for y in obs])
        too_wide = np.mean([crps_sample(_RNG.normal(100, 120, 4000), np.ones(4000), y) for y in obs])
        biased = np.mean([crps_sample(truth + 60, np.ones_like(truth), y) for y in obs])
        assert correct < too_tight
        assert correct < too_wide
        assert correct < biased

    def test_the_nihilist_loses_which_is_why_this_is_not_mae(self):
        """⭐ THE INVERSION CHECK, in miniature. On a 50%-zero target MAE is minimised by an
        all-zero arm; CRPS must NOT be. If this test ever flips, the selection metric is inverted
        and every E7.13 verdict is void (NF-D11 / NF-D14 (g))."""
        y = np.where(_RNG.random(600) < 0.5, 0.0, _RNG.gamma(2.0, 150.0, 600))
        honest = np.where(_RNG.random(3000) < 0.5, 0.0, _RNG.gamma(2.0, 150.0, 3000))
        zeros, w = np.zeros(1), np.ones(1)
        mae_nihilist = np.mean(np.abs(y - 0.0))
        mae_honest = np.mean(np.abs(y - np.median(honest)))
        crps_nihilist = np.mean([crps_sample(zeros, w, v) for v in y])
        crps_honest = np.mean([crps_sample(honest, np.ones_like(honest), v) for v in y])
        assert mae_nihilist <= mae_honest          # MAE really is inverted on this cohort
        assert crps_honest < crps_nihilist         # CRPS is not

    def test_weights_shift_the_score(self):
        s, y = np.array([0.0, 100.0]), 0.0
        near_zero = crps_sample(s, np.array([9.0, 1.0]), y)
        near_hundred = crps_sample(s, np.array([1.0, 9.0]), y)
        assert near_zero < near_hundred

    def test_empty_or_nan_returns_nan_rather_than_a_number(self):
        assert np.isnan(crps_sample(np.array([]), np.array([]), 1.0))
        assert np.isnan(crps_sample(np.array([1.0]), np.array([1.0]), np.nan))


# ── 2. Randomized PIT ────────────────────────────────────────────────────────────────────────

class TestRandomizedPIT:
    def test_uniform_under_a_correct_predictive(self):
        rng = np.random.default_rng(1)
        pred = _RNG.normal(0, 1, 2000)
        pits = [randomized_pit(pred, np.ones_like(pred), float(_RNG.normal()), rng)
                for _ in range(3000)]
        assert pit_max_decile_deviation(np.asarray(pits)) < 0.02

    def test_detects_an_under_dispersed_predictive(self):
        rng = np.random.default_rng(2)
        tight = _RNG.normal(0, 0.25, 2000)
        pits = [randomized_pit(tight, np.ones_like(tight), float(_RNG.normal()), rng)
                for _ in range(3000)]
        assert pit_max_decile_deviation(np.asarray(pits)) > 0.10

    def test_randomization_is_what_makes_the_zero_atom_well_posed(self):
        """Both the predictive and the observation put a large atom at exactly 0, so a plain PIT
        piles up on the jump. The randomized transform must spread across it."""
        rng = np.random.default_rng(3)
        pred = np.concatenate([np.zeros(500), _RNG.gamma(2, 100, 500)])
        pits = np.array([randomized_pit(pred, np.ones_like(pred), 0.0, rng) for _ in range(2000)])
        assert pits.min() < 0.05 and pits.max() > 0.45          # genuinely spread over the atom
        assert 0.20 < pits.mean() < 0.30                        # ≈ half the atom's mass

    def test_flatness_statistic_is_zero_on_a_perfectly_uniform_sample(self):
        assert pit_max_decile_deviation(np.linspace(0.0005, 0.9995, 10000)) < 1e-3


# ── 3. Coverage ──────────────────────────────────────────────────────────────────────────────

class TestCoverage:
    def test_counts_inclusive_membership(self):
        lo, hi = np.array([0.0, 10.0]), np.array([5.0, 20.0])
        assert interval_coverage(lo, hi, np.array([0.0, 25.0])) == pytest.approx(0.5)

    def test_a_max_width_degenerate_satisfies_any_coverage_floor(self):
        """NF1.8: the proof that coverage is a CONSTRAINT and not a criterion is that a degenerate
        satisfies it — which is fine, because the primary metric then eliminates it."""
        y = _RNG.normal(100, 30, 500)
        assert interval_coverage(np.full(500, -1e9), np.full(500, 1e9), y) == 1.0


# ── 4. PBO / CSCV ────────────────────────────────────────────────────────────────────────────

class TestPBO:
    def test_refuses_fewer_than_four_folds_rather_than_returning_a_number(self):
        """E7.12-S6: at <4 folds CSCV is UNDEFINED. Returning a plausible number here would let an
        unpowered test be reported as a deflated one."""
        out = pbo_cscv(np.array([[1.0, 2.0], [1.5, 2.5], [1.2, 2.2]]))
        assert out["computable"] is False and out["pbo"] is None

    def test_a_consistently_better_arm_gives_pbo_zero(self):
        s = np.array([[1.0, 2.0, 3.0], [1.1, 2.1, 3.1], [0.9, 1.9, 2.9], [1.0, 2.2, 3.2]])
        out = pbo_cscv(s)
        assert out["computable"] and out["pbo"] == pytest.approx(0.0)

    def test_an_overfit_pick_is_detected(self):
        """Every arm is excellent on exactly ONE fold and terrible on the rest — the textbook
        overfit field, where whichever arm wins in-sample is guaranteed to lose out of sample."""
        s = np.full((4, 4), 10.0)
        np.fill_diagonal(s, 0.1)
        assert pbo_cscv(s)["pbo"] == pytest.approx(1.0)

    def test_reports_the_two_statistics_pbo_alone_cannot_give(self):
        """NF1.8: a rank statistic cannot tell an unstable pick from a TIE — the flip distribution
        and the performance degradation are what distinguish them."""
        out = pbo_cscv(np.array([[1.0, 1.001, 3.0]] * 2 + [[1.001, 1.0, 3.0]] * 2))
        assert "flip_distribution" in out and "performance_degradation" in out
        assert sum(out["flip_distribution"].values()) == out["n_splits"]
        assert out["performance_degradation"] < 0.01          # a tie costs ~nothing to pick wrong


# ── 5. BH-FDR + clustered inference ──────────────────────────────────────────────────────────

class TestMultiplicity:
    def test_bh_matches_the_hand_computed_step_up(self):
        """m=8, alpha=0.05 → thresholds i·0.05/8. Sorted p clears its threshold at i=1 and i=2 and
        nowhere after (0.039 > 0.01875), so the step-up rejects exactly the two smallest."""
        out = bh_fdr([0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205], alpha=0.05)
        assert out["reject"] == [True, True, False, False, False, False, False, False]

    def test_nothing_survives_when_nothing_is_significant(self):
        assert not any(bh_fdr([0.4, 0.5, 0.9])["reject"])

    def test_bh_is_stricter_than_the_raw_alpha(self):
        """⚠️ BH is stricter WHEN THE FAMILY IS MOSTLY NULL, not always — with a family of nearly
        all significant p's the step-up rejects everything the raw alpha would. This is the case
        that separates them, and it is the case E7.13's channel family is in."""
        p = [0.04, 0.04, 0.9, 0.9, 0.9]
        assert sum(bh_fdr(p, alpha=0.05)["reject"]) == 0
        assert sum(x <= 0.05 for x in p) == 2


class TestClusterBootstrap:
    def test_detects_a_real_shift(self):
        d = _RNG.normal(-3.0, 5.0, 400)
        out = cluster_bootstrap_pvalue(d, np.arange(400), n_boot=800, seed=1)
        assert out["p_value"] < 0.05 and out["ci_hi"] < 0

    def test_no_shift_is_not_significant(self):
        d = _RNG.normal(0.0, 5.0, 400)
        out = cluster_bootstrap_pvalue(d, np.arange(400), n_boot=800, seed=1)
        assert out["p_value"] > 0.05

    def test_clustering_widens_the_ci_versus_treating_rows_as_independent(self):
        """A player sits on several boards, so his rows are not independent draws. Ignoring that
        would narrow every CI and manufacture significance."""
        base = _RNG.normal(-1.0, 4.0, 100)
        d = np.repeat(base, 8)                              # 8 near-identical rows per person
        clustered = cluster_bootstrap_pvalue(d, np.repeat(np.arange(100), 8), n_boot=800, seed=2)
        naive = cluster_bootstrap_pvalue(d, np.arange(800), n_boot=800, seed=2)
        assert (clustered["ci_hi"] - clustered["ci_lo"]) > (naive["ci_hi"] - naive["ci_lo"])
        assert clustered["n_clusters"] == 100


class TestDSR:
    def test_rises_with_skill_and_falls_with_the_trial_count(self):
        skill = _RNG.normal(0.15, 1.0, 600)
        assert deflated_sharpe(skill, 2, 600) > deflated_sharpe(skill, 500, 600)
        weak = _RNG.normal(0.0, 1.0, 600)
        assert deflated_sharpe(weak, 10, 600) < deflated_sharpe(skill, 10, 600)


# ── 6. Folds + arms ──────────────────────────────────────────────────────────────────────────

def _pool(seasons=(2018, 2019, 2020, 2021, 2022), horizon=3, n_per=40) -> pd.DataFrame:
    rows = []
    for s in seasons:
        for i in range(n_per):
            rows.append({"board_season": s, "horizon_seasons": horizon,
                         "fantasy_points": float(max(0.0, _RNG.normal(120, 160))),
                         "fv": float(_RNG.choice([40, 45, 50])),
                         "position_group": _RNG.choice(["IF_MID", "OF"]),
                         "comp_key": f"p{s}_{i}", "debuted": bool(_RNG.random() < 0.4)})
    df = pd.DataFrame(rows)
    df["board_season"] = df["board_season"].astype("Int64")
    return df


class TestFoldPlan:
    def test_strict_maturity_admits_exactly_one_fold_at_this_archive_depth(self):
        """The documented FOLD CEILING, pinned. If this ever returns more, the archive deepened and
        the strictly-matured re-validation has become possible — which is the re-open trigger."""
        plan = fold_plan(_pool(), strict=True)
        assert [f["query_season"] for f in plan] == [2022]
        assert plan[0]["train_seasons"] == [2018]

    def test_relaxed_rule_gives_the_four_folds_the_primary_run_uses(self):
        plan = fold_plan(_pool(), strict=False)
        assert [f["query_season"] for f in plan] == [2019, 2020, 2021, 2022]
        assert plan[-1]["train_seasons"] == [2018, 2019, 2020, 2021]

    def test_folds_are_forward_chained_never_using_the_future(self):
        for f in fold_plan(_pool(), strict=False):
            assert max(f["train_seasons"]) < f["query_season"]


class TestArmField:
    def test_anchors_and_degenerates_are_not_selectable(self):
        by = {a.name: a for a in ARM_FIELD}
        assert by["oracle_k15"].selectable is False
        assert by["marginal"].selectable is False
        assert by["all_zero"].selectable is False
        assert by["random_k15"].selectable is False
        assert by["fv_bucket"].selectable is True

    def test_the_field_carries_all_four_required_anchor_kinds(self):
        kinds = {a.kind for a in ARM_FIELD}
        assert {"anchor", "degenerate", "placebo", "bucket", "comp", "blend"} <= kinds

    def test_all_zero_is_a_point_mass_at_zero(self):
        by = {a.name: a for a in ARM_FIELD}
        pool = _pool()
        s, w = score_arm(by["all_zero"], pool, pool.head(5), player_type="batter")
        assert all(np.array_equal(x, np.zeros(1)) for x in s)

    def test_marginal_is_the_unconditional_pool_outcome(self):
        by = {a.name: a for a in ARM_FIELD}
        pool = _pool()
        s, _ = score_arm(by["marginal"], pool, pool.head(3), player_type="batter")
        assert all(len(x) == len(pool) for x in s)

    def test_fv_bucket_conditions_on_grade_and_position(self):
        by = {a.name: a for a in ARM_FIELD}
        pool = _pool(n_per=200)
        q = pool.head(20)
        s, _ = score_arm(by["fv_bucket"], pool, q, player_type="batter")
        assert all(0 < len(x) <= len(pool) for x in s)
        assert any(len(x) < len(pool) for x in s)        # at least one row got a real bucket
