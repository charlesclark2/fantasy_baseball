"""E7.12 slice 6 — AAA-Statcast feasibility memo (the GATE, not a bake-off).

Pure numpy/pandas; fast-gate safe. The memo's whole job is to decide whether a bake-off may run at
all, so what has to be tested is the DECISION machinery: does it classify a fold that cannot carry the
mechanism as unusable, does its power simulation reflect the gate that will actually judge the arm,
and does it name which constraint binds rather than stopping on whichever trips first.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.s6_feasibility import (
    BH_ALPHA,
    FOLD_WIN_GATE,
    MIN_FOLD_TEST_ROWS,
    MIN_FOLDS_FOR_PBO,
    _MISS_SUFFIX,
    _with_missing_indicators,
    coverage_census,
    fold_viability,
    minimum_detectable,
    power_curve,
    reopen_trigger,
)

_SC = ("sc_a", "sc_b")


def _labelled(spec: dict[int, tuple[int, int]]) -> pd.DataFrame:
    """{cohort: (covered, labelled)} → a labelled frame with that exact coverage pattern."""
    rows = []
    for cohort, (cov, lab) in spec.items():
        for i in range(lab):
            covered = i < cov
            rows.append({"debut_cohort": cohort, "level": "Triple-A" if covered else "Double-A",
                         "sc_a": 90.0 if covered else np.nan,
                         "sc_b": 0.4 if covered else np.nan})
    return pd.DataFrame(rows)


class TestCoverageCensus:
    def test_a_row_counts_as_covered_when_any_block_column_is_present(self):
        """The block arrives as a unit from one source; requiring every column would understate
        coverage over a partial scrape and make the ceiling look worse than it is."""
        df = pd.DataFrame({"debut_cohort": [2022, 2022], "level": ["Triple-A"] * 2,
                           "sc_a": [90.0, np.nan], "sc_b": [np.nan, np.nan]})
        census, _ = coverage_census(df, _SC)
        assert int(census.loc[0, "covered"]) == 1

    def test_census_reports_both_cohort_and_level(self):
        census, by_level = coverage_census(_labelled({2022: (5, 10), 2023: (3, 10)}), _SC)
        assert list(census["covered"]) == [5, 3]
        assert set(by_level["level"]) == {"Triple-A", "Double-A"}


class TestFoldViability:
    def test_a_fold_with_no_covered_TRAINING_row_is_inert_even_when_its_test_rows_are_covered(self):
        """⭐ THE CASE THAT DECIDES THIS SLICE. Coverage begins in 2022, so fold 2022 trains entirely
        on uncovered cohorts: the arm is byte-identical to the baseline, scores `delta = 0`, and the
        `d > 0` fold test counts that as a LOSS. Counting it would both overstate the fold budget and
        cap the achievable win-rate — the S4 lesson."""
        census, _ = coverage_census(_labelled({2021: (0, 100), 2022: (69, 300), 2023: (59, 200)}), _SC)
        folds = fold_viability(census)
        f22 = folds[folds["fold"] == 2022].iloc[0]
        assert f22["covered_test"] == 69 and f22["covered_train"] == 0
        assert f22["status"].startswith("INERT")
        assert folds[folds["fold"] == 2023].iloc[0]["status"] == "USABLE"

    def test_a_cohort_below_the_row_floor_is_thin_not_usable(self):
        census, _ = coverage_census(
            _labelled({2022: (60, 200), 2023: (MIN_FOLD_TEST_ROWS - 1, 100)}), _SC)
        assert fold_viability(census)[lambda d: d["fold"] == 2023]["status"].iloc[0].startswith("THIN")

    def test_the_seed_cohort_is_excluded_because_it_has_no_prior_training_window(self):
        """The EARLIEST cohort can never be a fold — there is nothing strictly prior to train on. In
        the real data that is 2015, which is why 2022 still appears (as INERT) rather than vanishing.
        """
        census, _ = coverage_census(
            _labelled({2021: (0, 100), 2022: (60, 200), 2023: (60, 200)}), _SC)
        folds = fold_viability(census)
        assert set(folds["fold"]) == {2022, 2023}      # 2021 is the seed and is absent
        assert folds[folds["fold"] == 2022].iloc[0]["status"].startswith("INERT")

    def test_train_coverage_is_cumulative_over_strictly_prior_cohorts(self):
        census, _ = coverage_census(
            _labelled({2022: (69, 300), 2023: (59, 200), 2024: (52, 200)}), _SC)
        folds = fold_viability(census).set_index("fold")
        assert folds.loc[2023, "covered_train"] == 69
        assert folds.loc[2024, "covered_train"] == 69 + 59


class TestMissingIndicatorLandmine:
    def test_an_indicator_is_emitted_per_column_and_both_are_returned(self):
        """🚨 `PartialPoolProjector._design` discards `_Scaler`'s missing flag, so the raw block alone
        would assert the covered-subset MEAN about every uncovered row — a fabricated neutral on ~88%
        of the population, exactly what the story prompt forbids."""
        df = pd.DataFrame({"sc_a": [90.0, np.nan], "sc_b": [0.4, np.nan]})
        out, cols = _with_missing_indicators(df, _SC)
        assert cols == ("sc_a", "sc_a" + _MISS_SUFFIX, "sc_b", "sc_b" + _MISS_SUFFIX)
        assert list(out["sc_a" + _MISS_SUFFIX]) == [0.0, 1.0]

    def test_the_projector_really_receives_the_indicator_columns(self):
        """A guard that only checks the frame would pass while the model still never sees them."""
        from betting_ml.scripts.milb_mle.milb_mle import PartialPoolProjector

        rng = np.random.default_rng(0)
        n = 300
        df = pd.DataFrame({
            "player_id": np.arange(n), "level": rng.choice(["Double-A", "Triple-A"], n),
            "league": "L1", "age": rng.normal(23, 2, n), "feat": rng.normal(0.1, 0.03, n),
            "minor_pa": 300, "has_target": True})
        df["target"] = 0.02 + 0.6 * df["feat"] + rng.normal(0, 0.01, n)
        df["sc_a"] = np.where(df["level"] == "Triple-A", rng.normal(90, 2, n), np.nan)
        df["sc_b"] = np.where(df["level"] == "Triple-A", rng.normal(0.4, 0.05, n), np.nan)
        frame, cols = _with_missing_indicators(df, _SC)
        m = PartialPoolProjector(prior_scale=2.0, extra_cols=cols).fit(frame)
        fixed = next(b for b in m.spec_.blocks if b.name == "fixed")
        assert all(c in fixed.columns for c in cols)


class TestPowerSimulation:
    def test_the_full_rule_is_calibrated_at_a_true_lift_of_zero(self):
        """A power curve that fires often under the null would make every MDE meaningless."""
        p = power_curve(0.001, 0.03, n_folds=5, n_metrics=4,
                        lifts_pct=np.array([0.0]), n_sims=4000)
        assert p["power_full_rule"].iloc[0] <= BH_ALPHA

    def test_power_is_monotone_in_the_true_lift(self):
        p = power_curve(0.001, 0.03, n_folds=6, n_metrics=1,
                        lifts_pct=np.arange(0, 8.01, 1.0), n_sims=3000)
        v = p["power_full_rule"].to_numpy()
        assert np.all(np.diff(v) >= -0.03)      # monotone up to simulation noise
        assert v[-1] > v[0]

    def test_the_coarse_fold_clause_is_near_a_coin_flip_at_three_folds(self):
        """⭐ THE FINDING THE MEMO TURNS ON, pinned. With 3 folds \"≥60% of folds\" collapses to
        \"≥2 of 3\", which a NULL clears about half the time — so the fold clause contributes almost
        no discrimination and the whole burden falls on a t-test with 2 degrees of freedom. Sibling of
        the S5 result where a permuted placebo cleared the same clause 9/11."""
        p = power_curve(0.001, 0.03, n_folds=3, n_metrics=4,
                        lifts_pct=np.array([0.0]), n_sims=6000)
        assert 0.40 <= p["power_fold_gate"].iloc[0] <= 0.60
        assert p["power_full_rule"].iloc[0] < 0.10   # BH carries all of it

    def test_more_folds_detect_a_smaller_effect(self):
        args = dict(fold_delta_sd=0.001, base_mae=0.03, n_metrics=1,
                    lifts_pct=np.arange(0, 12.01, 0.5), n_sims=3000)
        small = minimum_detectable(power_curve(n_folds=3, **args), 1.0)
        large = minimum_detectable(power_curve(n_folds=8, **args), 1.0)
        assert large["mde_fold_level_pct"] < small["mde_fold_level_pct"]

    def test_the_gate_constants_mirror_the_runner(self):
        """If the real gate moves and this does not, the memo silently starts answering about a rule
        nobody applies."""
        from betting_ml.scripts.milb_mle.run_e7_12_slice5 import FOLD_WIN_GATE as RUNNER_GATE

        assert FOLD_WIN_GATE == RUNNER_GATE


class TestMinimumDetectable:
    def test_the_covered_fraction_converts_a_fold_lift_into_a_mechanism_lift(self):
        """⭐ The arm can only move covered rows, but the fold MAE averages over ALL of them — so the
        effect the MECHANISM must produce is larger than the effect the GATE sees, by 1/coverage.
        Quoting only one number misstates the requirement by ~4x on this substrate."""
        p = pd.DataFrame({"true_lift_pct": [0.0, 1.0, 2.0, 3.0],
                          "power_full_rule": [0.0, 0.3, 0.6, 0.9]})
        out = minimum_detectable(p, covered_frac=0.25)
        assert out["mde_fold_level_pct"] == 3.0
        assert out["mde_on_covered_rows_pct"] == pytest.approx(12.0)

    def test_an_undetectable_effect_is_reported_as_unreachable_not_as_a_number(self):
        p = pd.DataFrame({"true_lift_pct": [0.0, 5.0], "power_full_rule": [0.01, 0.2]})
        out = minimum_detectable(p, covered_frac=0.25)
        assert out["unreachable"] is True and out["mde_on_covered_rows_pct"] is None


class TestReopenTrigger:
    def test_it_counts_how_many_more_folds_are_needed_for_the_deflation_instrument(self):
        census, _ = coverage_census(
            _labelled({2022: (69, 300), 2023: (59, 200), 2024: (52, 200), 2025: (59, 200)}), _SC)
        folds = fold_viability(census)
        out = reopen_trigger(census, folds)
        assert out["usable_folds_now"] == len(folds[folds["status"] == "USABLE"])
        assert out["additional_usable_folds_required"] == max(
            MIN_FOLDS_FOR_PBO - out["usable_folds_now"], 0)

    def test_a_thin_in_progress_cohort_is_listed_as_one_season_from_usable(self):
        """The re-open condition has to be a DATA condition someone can check, not a date."""
        census, _ = coverage_census(
            _labelled({2022: (69, 300), 2023: (59, 200), 2026: (20, 80)}), _SC)
        out = reopen_trigger(census, fold_viability(census))
        assert 2026 in out["thin_folds_one_season_from_usable"]

    def test_it_never_demands_a_negative_number_of_folds(self):
        census, _ = coverage_census({y: (60, 200) for y in range(2022, 2030)} and
                                    _labelled({y: (60, 200) for y in range(2022, 2030)}), _SC)
        out = reopen_trigger(census, fold_viability(census))
        assert out["additional_usable_folds_required"] == 0
