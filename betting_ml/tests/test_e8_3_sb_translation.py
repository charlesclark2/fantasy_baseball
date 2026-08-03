"""E8.3 — guards for the stolen-base translation.

Every gate here was verified to go RED on deliberately-broken source before being trusted (the
repo's standing rule: a guard that cannot fail is not a guard). The four things worth guarding are
the four that would silently produce a WRONG SHIP rather than a crash:

  1. the SELECTOR is proper (CRPS), and the degenerate ceilings genuinely lose on it;
  2. the anchors RAISE when they cannot fit, rather than passing vacuously (NF1.7 (a));
  3. the DSR field excludes diagnostic anchors from V but pays multiplicity in full (MH2.1 (a));
  4. the emitted line is leakage-safe and a FAILED gate cannot emit at all.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import sb_translation as sbt


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────

def _cohort(n: int = 400, seed: int = 0, zero_share: float = 0.35) -> pd.DataFrame:
    """A synthetic cohort with a REAL minor→major SB relation and a genuine zero atom."""
    rng = np.random.default_rng(seed)
    minor = np.clip(rng.gamma(2.0, 0.05, n), 0, 0.8)
    minor[rng.random(n) < zero_share] = 0.0
    target = np.clip(0.55 * minor + rng.normal(0, 0.02, n), 0, None)
    levels = rng.choice(["Single-A", "High-A", "Double-A", "Triple-A"], n)
    cohorts = rng.choice([2016, 2017, 2018, 2019, 2020], n)
    sbo = rng.integers(60, 400, n)
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "player_name": [f"P {i}" for i in range(n)],
        "level": levels, "league": "L", "age": rng.normal(22, 1.5, n),
        "debut_cohort": cohorts, "is_prospect": False,
        "minor_pa": rng.integers(200, 600, n), "minor_sbo": sbo,
        "minor_sb": (minor * sbo).round(), "minor_cs": rng.integers(0, 10, n),
        "minor_sb_rate": minor, "mlb_sb_rate": target,
        "minor_env_sb_rate": rng.uniform(0.05, 0.11, n),
        "minor_env_att_rate": rng.uniform(0.07, 0.14, n),
        "minor_att_rate": minor * 1.3, "mlb_att_rate": target * 1.3,
        "minor_succ_rate": rng.uniform(0.5, 0.9, n), "mlb_succ_rate": rng.uniform(0.5, 0.9, n),
        "minor_sb_per_pa": minor * 0.3, "mlb_sb_per_pa": target * 0.3,
        "has_target": True, "has_minor_line": True,
    })


@pytest.fixture
def data():
    return sbt.build_target(_cohort())


# ── 1. the selector ──────────────────────────────────────────────────────────────────────────

class TestTheSelectorIsProper:
    def test_crps_is_minimised_by_the_truth_and_punishes_both_over_and_under_dispersion(self):
        """CRPS must grade the POINT and the SPREAD jointly — that is the whole reason it replaces
        MAE on a zero-heavy target. A score that a too-tight or too-wide predictive can win is not
        proper, and every deflation statistic computed on top of it would be meaningless."""
        rng = np.random.default_rng(0)
        y = rng.normal(0.06, 0.03, 4000)
        honest = sbt.crps_gaussian(np.full_like(y, 0.06), np.full_like(y, 0.03), y).mean()
        too_tight = sbt.crps_gaussian(np.full_like(y, 0.06), np.full_like(y, 0.003), y).mean()
        too_wide = sbt.crps_gaussian(np.full_like(y, 0.06), np.full_like(y, 0.30), y).mean()
        biased = sbt.crps_gaussian(np.full_like(y, 0.20), np.full_like(y, 0.03), y).mean()
        assert honest < too_tight and honest < too_wide and honest < biased

    def test_the_all_zero_nihilist_loses_on_crps(self, data):
        """⭐ NF-D11/NF-D14: the degenerate is scored EVERY run and READ, never reasoned about.
        On a cohort whose conditional MEDIAN is off the floor it must lose decisively."""
        train, test = data.iloc[:300], data.iloc[300:]
        y = test["target"].to_numpy(float)
        zero = sbt.DegenerateZeroProjector().fit(train)
        real = sbt.LevelFactorProjector().fit(train)
        z = sbt.score_predictions(*zero.predict(test), y)
        r = sbt.score_predictions(*real.predict(test), y)
        assert r["crps"] < z["crps"]

    def test_the_conditional_median_is_what_predicts_the_mae_inversion_not_the_zero_share(self):
        """NF-D14's refinement, as an executable statement: MAE inverts on the conditional MEDIAN
        being at the floor, NOT on the cohort merely 'looking' zero-heavy. Built two ways round.

        This is the test that says WHY the real E8.3 cohort (13% zeros, median 0.0435) was safe
        while a 60%-zero cohort would not have been — and why the rule is to SCORE the degenerate
        rather than eyeball the histogram."""
        rng = np.random.default_rng(7)

        def mae(y, pred):
            return float(np.mean(np.abs(y - pred)))

        # (a) 35% zeros but the conditional MEDIAN is off the floor — the real E8.3 shape
        #     (measured: 13% exact zeros, median 0.0435). The nihilist LOSES MAE outright.
        y1 = np.concatenate([np.zeros(350), rng.uniform(0.02, 0.20, 650)])
        assert np.median(y1) > 0
        assert mae(y1, 0.0) > mae(y1, float(np.median(y1)))

        # (b) 65% zeros ⇒ the conditional median IS the floor. Now the SAME metric is minimised at
        #     zero and the nihilist wins — the NF-D11 inversion. Same statistic, opposite verdict,
        #     and the ONLY thing that changed is where the median sits.
        y2 = np.concatenate([np.zeros(650), rng.uniform(0.02, 0.20, 350)])
        assert np.median(y2) == 0
        assert mae(y2, 0.0) < mae(y2, float(np.mean(y2)))

        # ⭐ and the reason CRPS is the selector: it is NOT fooled in case (b). A degenerate spike
        #     at zero is punished for its spread, so the honest predictive still wins.
        honest = sbt.crps_gaussian(np.full_like(y2, y2.mean()),
                                   np.full_like(y2, y2.std()), y2).mean()
        nihilist = sbt.crps_gaussian(np.zeros_like(y2), np.full_like(y2, 1e-6), y2).mean()
        assert honest < nihilist


# ── 2. the anchors ───────────────────────────────────────────────────────────────────────────

class TestAnchorsRaiseRatherThanPassVacuously:
    """⭐ NF1.7 (a): an anchor that FAILS TO FIT makes its check vacuously true. NF1.7's oracle
    silently returned None under 40 rows and `oracle_respected` passed on NOTHING."""

    def test_the_oracle_raises_on_a_fold_too_thin_to_fit(self, data):
        with pytest.raises(sbt.AnchorFitError, match="vacuously true|cannot fit"):
            sbt.fit_oracle(lambda: sbt.LevelFactorProjector(), data.iloc[:100], data.iloc[:2])

    def test_the_matched_n_candidate_raises_rather_than_returning_none(self, data):
        with pytest.raises(sbt.AnchorFitError):
            sbt.fit_matched_n_candidate(lambda: sbt.LevelFactorProjector(), data.iloc[:1],
                                        data.iloc[:2])

    def test_the_permutation_raises_on_an_empty_train(self, data):
        with pytest.raises(sbt.AnchorFitError):
            sbt.fit_permutation(lambda: sbt.LevelFactorProjector(), data.iloc[:1], data.iloc[:50])

    def test_a_fit_failure_inside_an_anchor_surfaces_as_an_anchor_error(self, data):
        """A broken arm must not be swallowed into a silent pass."""
        class _Broken(sbt.SbProjector):
            name = "broken"

            def fit(self, train):
                raise RuntimeError("boom")

        with pytest.raises(sbt.AnchorFitError, match="boom"):
            sbt.fit_oracle(lambda: _Broken(), data.iloc[:200], data.iloc[200:])

    def test_the_permutation_destroys_the_signal_it_is_meant_to_destroy(self, data):
        """The anchor's MECHANISM must actually act (NF1.7 inert-anchor lesson): an arm fit on
        shuffled labels must be materially worse than the same arm fit on real ones."""
        train, test = data.iloc[:300], data.iloc[300:]
        y = test["target"].to_numpy(float)
        real = sbt.score_predictions(*sbt.LevelFactorProjector().fit(train).predict(test), y)
        perm = sbt.score_predictions(
            *sbt.fit_permutation(lambda: sbt.LevelFactorProjector(), train, test), y)
        assert perm["crps"] > real["crps"]


# ── 3. the DSR field ─────────────────────────────────────────────────────────────────────────

class TestTheDsrFieldExcludesDiagnosticsFromDispersion:
    def test_the_degenerates_are_declared_non_selectable_before_any_run(self):
        """⚠️ MH2 (a): you get to PRE-REGISTER a family, you do not get to DISCOVER one. The
        partition that `dsr_panel` relies on must live in `build_field`, i.e. be fixed before a
        single fold is scored — not derived after seeing who lost."""
        field = {a.label: a.selectable for a in sbt.build_field()}
        assert field["degenerate_zero"] is False
        assert field["degenerate_mean"] is False
        assert field["L0_foil"] is False
        assert field["identity_no_translation"] is False
        assert sum(field.values()) >= 4, "need ≥4 real learner arms for a §0.5 field"

    def test_the_field_carries_at_least_three_distinct_learner_classes(self):
        """§0.5: a bake-off, not a single architecture — and a direct-learned foil beside any
        prescribed structure."""
        classes = {type(a.factory()).__name__ for a in sbt.build_field() if a.selectable}
        assert len(classes) >= 3
        assert "RidgeProjector" in classes, "the direct-learned foil must be in the field"

    def test_every_era_arm_has_a_matched_foil(self):
        """NF-D10: a feature family earns an ATTRIBUTABLE verdict only as a matched pair. An era arm
        without its byte-identical era-blind twin could only ever be read off a leaderboard rank,
        which cannot tell 'inert' from 'in a tie'."""
        field = sbt.build_field()
        labels = {a.label for a in field}
        era = [a for a in field if getattr(a.factory(), "uses_era", False)]
        assert era, "the era covariate must actually be represented in the field"
        for a in era:
            assert a.pair_with, f"{a.label} has no matched foil"
            assert a.pair_with in labels

    def test_a_matched_pair_differs_ONLY_in_the_era_term(self):
        """The foil must be byte-identical apart from the claimed channel, or the paired delta
        measures something else."""
        field = {a.label: a for a in sbt.build_field()}
        era, base = field["gbm_era"].factory(), field["gbm"].factory()
        assert era.uses_era and not base.uses_era
        for attr in ("n_estimators", "max_depth", "learning_rate"):
            assert getattr(era, attr) == getattr(base, attr)


# ── 4. emission ──────────────────────────────────────────────────────────────────────────────

class TestEmissionIsLeakageSafe:
    def test_a_cohort_is_never_scored_by_a_model_that_saw_it(self):
        """The expanding-window contract: cohort Y's line is fit on strictly-PRIOR cohorts only.
        Sharing this discipline with E7.3 is what makes an SB weight blendable with k_pct's."""
        d = sbt.build_target(_cohort(n=500, seed=3))
        seen: list[set] = []

        class _Spy(sbt.LevelFactorProjector):
            def fit(self, train):
                seen.append(set(train["debut_cohort"].unique()))
                return super().fit(train)

        proj = sbt.emit_projections(d, lambda: _Spy(), "sb_rate")
        assert not proj.empty
        emitted = sorted(proj["debut_cohort"].unique())
        for train_cohorts, year in zip(seen, emitted):
            assert all(c < year for c in train_cohorts), \
                f"cohort {year} was fit on {train_cohorts} — a non-prior cohort leaked in"

    def test_the_earliest_cohort_is_a_seed_and_is_not_emitted(self):
        d = sbt.build_target(_cohort(n=500, seed=4))
        proj = sbt.emit_projections(d, lambda: sbt.LevelFactorProjector(), "sb_rate")
        assert int(proj["debut_cohort"].min()) > int(d["debut_cohort"].min())

    def test_the_emitted_line_is_clipped_to_a_physically_plausible_range(self):
        d = sbt.build_target(_cohort(n=400, seed=5))
        proj = sbt.emit_projections(d, lambda: sbt.LevelFactorProjector(), "sb_rate")
        lo, hi = sbt.PLAUSIBLE_RANGE["sb_rate"]
        assert proj["mle_sb_rate"].between(lo, hi).all()

    def test_emission_refuses_a_frame_without_eligibility_flags(self):
        with pytest.raises(ValueError, match="eligibility"):
            sbt.emit_projections(pd.DataFrame({"x": [1]}), lambda: sbt.LevelFactorProjector())


# ── 5. the target definition ─────────────────────────────────────────────────────────────────

class TestTheTargetIsAnAbilityRateNotACount:
    def test_a_rate_is_null_not_zero_when_its_denominator_is_zero(self):
        """⚠️ SB/0 is UNKNOWN ('we never saw him reach first'), and coercing it to 0.0 would inject
        a fabricated 'cannot run' into a zero-heavy target — the exact direction that flatters the
        all-zero degenerate and would bias the whole selection."""
        from betting_ml.scripts.milb_mle.build_sb_pairs import compute_sb_rates

        out = compute_sb_rates(pd.DataFrame({
            "minor_sb": [0, 5], "minor_cs": [0, 1], "minor_sbo": [0, 100], "minor_pa": [0, 300],
            "minor_env_sb_rate": [0.08, 0.08], "minor_env_att_rate": [0.1, 0.1],
            "mlb_sb": [0, 3], "mlb_cs": [0, 1], "mlb_sbo": [0, 90], "mlb_pa": [0, 250],
            "mlb_env_sb_rate": [0.07, 0.07], "mlb_env_att_rate": [0.09, 0.09],
        }))
        assert pd.isna(out["minor_sb_rate"].iloc[0])
        assert out["minor_sb_rate"].iloc[1] == pytest.approx(0.05)

    def test_the_opportunity_denominator_is_times_reached_first_not_plate_appearances(self):
        """SBO = singles + walks + HBP. Using PA would confound ability with ON-BASE skill, and
        using hits would count a double as a chance to steal second."""
        from betting_ml.scripts.milb_mle import build_sb_pairs as bsp

        for expr in (bsp._MINOR_SBO, bsp._MLB_SBO):
            assert "doubles" in expr and "triples" in expr and "home_runs" in expr
            assert "walks" in expr and "hit_by_pitch" in expr

    def test_the_left_censoring_flag_only_fires_inside_the_mart_floor_cohort(self):
        """A LATER cohort with a long gap is a real slow-developer, not a censoring artifact —
        sweeping those in would quietly redefine the population the robustness arm tests."""
        from betting_ml.scripts.milb_mle.build_sb_pairs import (
            DEBUT_MART_FLOOR_SEASON, apply_eligibility,
        )

        df = pd.DataFrame({
            "debut_cohort": [DEBUT_MART_FLOOR_SEASON, DEBUT_MART_FLOOR_SEASON, 2021],
            "last_minor_season": [2009, DEBUT_MART_FLOOR_SEASON, 2014],
            "minor_pa": [400, 400, 400], "minor_sbo": [100, 100, 100],
            "minor_sb_rate": [0.1, 0.1, 0.1], "mlb_sb_rate": [0.05, 0.05, 0.05],
            "mlb_pa": [400, 400, 400], "mlb_sbo": [100, 100, 100],
        })
        out = apply_eligibility(df)
        assert list(out["debut_censored"]) == [True, False, False]
