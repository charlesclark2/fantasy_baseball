"""E7.12 slice 5 — prospect aging curves (the age × minor-line interaction).

Pure numpy/pandas throughout, so the whole file runs in the fast gate. Nothing here touches S3,
Snowflake or the network.

The tests are organised around the three things that could make a slice-5 null WORTHLESS:
  * the age transforms leak or silently drop rows (`TestAgeContext`);
  * the design block does not actually enter the model, so every arm is the baseline in disguise
    (`TestProjectorBlocks`, `TestCloneCarriesEveryField`);
  * the block cannot recover a planted effect, or cannot tell the SLOPE channel from the INTERCEPT
    channel, in which case both the null AND the attribution are unearned (`TestRecovery`).
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.age_context import (
    AGE_BUCKET,
    AGE_LABELS,
    REL_BUCKET,
    REL_COL,
    REL_LABELS,
    attach_age_features,
    bucket_coverage,
    level_median_age,
    permute_bucket,
)
from betting_ml.scripts.milb_mle.milb_mle import (
    GBMProjector,
    PartialPoolProjector,
    _config_name,
    clone_projector,
)
from betting_ml.scripts.milb_mle.run_e7_12_slice5 import (
    S5_LADDER,
    SURVIVORSHIP_RETENTION_MIN,
    _S2_SENSITIVITY_ARM,
    by_label,
    s5_anchors,
    s5_verdict,
    survivorship_read,
    synthetic_recovery_check,
)

_LEVELS = ("Single-A", "High-A", "Double-A", "Triple-A")
_REF = {"Single-A": 21.0, "High-A": 22.0, "Double-A": 22.8, "Triple-A": 24.0}


def _panel(n: int = 500, seed: int = 0, mode: str = "none") -> pd.DataFrame:
    """A small labelled panel with a level-dependent age distribution, like the real substrate."""
    rng = np.random.default_rng(seed)
    level = rng.choice(_LEVELS, n)
    ref = pd.Series(level).map(_REF).to_numpy(float)
    age = ref + rng.normal(0.0, 1.8, n)
    feat = rng.normal(0.10, 0.030, n)
    young = ((age - ref) < -0.5).astype(float)
    slope = 0.60 + (0.55 * young if mode == "slope" else 0.0)
    shift = 0.020 * young if mode == "intercept" else 0.0
    return pd.DataFrame({
        "player_id": np.arange(n), "level": level, "league": rng.choice(["L1", "L2"], n),
        "age": age, "feat": feat, "minor_pa": rng.integers(150, 600, n),
        "target": 0.020 + slope * (feat - 0.10) + shift + rng.normal(0.0, 0.010, n),
        "has_target": True,
        "debut_cohort": rng.choice([2019, 2020, 2021, 2022], n)})


def _with_ages(df: pd.DataFrame) -> pd.DataFrame:
    return attach_age_features(df, level_median_age(df))


# ══════════════════════════════════════════════════════════════════════════════════════
class TestAgeContext:
    def test_missing_columns_raise_rather_than_returning_an_empty_reference(self):
        with pytest.raises(KeyError):
            level_median_age(pd.DataFrame({"age": [22.0]}))
        with pytest.raises(KeyError):
            attach_age_features(pd.DataFrame({"level": ["Triple-A"]}), pd.Series(dtype=float))

    def test_age_vs_level_is_measured_from_the_levels_own_median(self):
        df = _with_ages(_panel(400, seed=1))
        for lvl, g in df.groupby("level"):
            # the median of the centred values within a level is 0 by construction
            assert abs(float(g[REL_COL].median())) < 1e-9

    def test_the_reference_is_train_only_so_a_held_out_outlier_cannot_move_it(self):
        """⭐ The one genuine leakage seam in this slice. The level median is a population aggregate;
        computing it over the full frame would let a held-out cohort's own ages set the origin its
        feature is measured from."""
        df = _panel(400, seed=2)
        train = df[df["debut_cohort"] < 2022]
        med = level_median_age(train)
        # a wildly old held-out cohort must not shift the reference at all
        poisoned = df.copy()
        poisoned.loc[poisoned["debut_cohort"] == 2022, "age"] = 41.0
        assert level_median_age(poisoned[poisoned["debut_cohort"] < 2022]).equals(med)
        a = attach_age_features(df, med)[REL_COL]
        b = attach_age_features(df, level_median_age(df))[REL_COL]
        assert not np.allclose(a.to_numpy(), b.to_numpy())  # the choice of reference is load-bearing

    def test_an_unseen_level_falls_back_rather_than_becoming_nan(self):
        """A NaN would drop the row out of every bucket and shrink the mechanism's reach WITHOUT
        appearing anywhere in the leaderboard — the silent-degradation shape this repo keeps hitting."""
        med = level_median_age(_panel(300, seed=3))
        novel = pd.DataFrame({"level": ["Rookie-Ball"], "age": [21.0]})
        out = attach_age_features(novel, med)
        assert np.isfinite(out[REL_COL].iloc[0])
        assert out[REL_BUCKET].iloc[0] in REL_LABELS

    def test_a_missing_age_stays_bucketless_instead_of_being_imputed(self):
        med = level_median_age(_panel(300, seed=4))
        out = attach_age_features(pd.DataFrame({"level": ["Triple-A"], "age": [np.nan]}), med)
        assert out[AGE_BUCKET].isna().all() and out[REL_BUCKET].isna().all()

    def test_every_finite_age_lands_in_a_bucket(self):
        med = level_median_age(_panel(300, seed=5))
        extreme = pd.DataFrame({"level": ["Triple-A"] * 4, "age": [16.0, 23.0, 30.0, 47.0]})
        out = attach_age_features(extreme, med)
        assert out[AGE_BUCKET].notna().all() and out[REL_BUCKET].notna().all()

    def test_placebo_permutes_the_bucket_within_cells_and_never_touches_age(self):
        """⭐ Permuting `age` itself would corrupt the BASELINE (age is already a main effect), so a
        placebo loss would be evidence about the main effect rather than about the interaction."""
        df = _with_ages(_panel(600, seed=6))
        rng = np.random.default_rng(0)
        perm = permute_bucket(df, REL_BUCKET, rng)
        # `age` is untouched — the function returns a Series and mutates nothing
        assert df["age"].equals(_with_ages(_panel(600, seed=6))["age"])
        # the multiset is preserved within every (level, cohort) cell
        for key, g in df.groupby(["level", "debut_cohort"]):
            assert (sorted(g[REL_BUCKET].dropna().tolist())
                    == sorted(perm.loc[g.index].dropna().tolist())), key
        # and it is not the identity on a panel this size
        assert (perm.to_numpy() != df[REL_BUCKET].to_numpy()).any()

    def test_coverage_lists_every_label_even_when_a_bucket_is_empty(self):
        """An almost-empty bucket is not a bug, but a mechanism inert in the cell it was DESIGNED for
        (the youngest) has to be visible rather than inferred from a missing row."""
        df = _with_ages(_panel(200, seed=7))
        cov = bucket_coverage(df)
        assert set(cov[cov["bucketing"] == AGE_BUCKET]["bucket"]) == set(AGE_LABELS)
        assert set(cov[cov["bucketing"] == REL_BUCKET]["bucket"]) == set(REL_LABELS)


# ══════════════════════════════════════════════════════════════════════════════════════
class TestProjectorBlocks:
    def test_the_default_projector_is_byte_exact(self):
        df = _with_ages(_panel(400, seed=8))
        a, _ = PartialPoolProjector(prior_scale=2.0).fit(df).predict(df)
        b, _ = PartialPoolProjector(prior_scale=2.0, bucket_col=None).fit(df).predict(df)
        assert np.array_equal(a, b)

    def test_a_bucket_col_with_neither_switch_is_inert(self):
        """The feature must not activate on the column alone — otherwise merely naming a column in a
        future slice would silently change every incumbent projection."""
        df = _with_ages(_panel(400, seed=9))
        a, _ = PartialPoolProjector(prior_scale=2.0).fit(df).predict(df)
        m = PartialPoolProjector(prior_scale=2.0, bucket_col=REL_BUCKET).fit(df)
        assert m.buckets_ == []
        assert np.array_equal(a, m.predict(df)[0])

    @pytest.mark.parametrize("kw,expected", [
        (dict(bucket_slope=True), ["age_slope"]),
        (dict(bucket_intercept=True), ["age_intercept"]),
        (dict(bucket_slope=True, bucket_intercept=True), ["age_intercept", "age_slope"]),
    ])
    def test_the_requested_blocks_actually_enter_the_design(self, kw, expected):
        df = _with_ages(_panel(400, seed=10))
        m = PartialPoolProjector(prior_scale=2.0, bucket_col=REL_BUCKET, **kw).fit(df)
        names = [b.name for b in m.spec_.blocks]
        assert [n for n in names if n.startswith("age_")] == expected
        # penalized: a bucket block estimates DEPARTURES from the linear main effect and must be shrunk
        assert all(b.penalized for b in m.spec_.blocks if b.name.startswith("age_"))
        # the fixed block still carries the linear age main effect this slice is NOT re-adding
        fixed = next(b for b in m.spec_.blocks if b.name == "fixed")
        assert "age" in fixed.columns
        assert not np.array_equal(m.predict(df)[0],
                                  PartialPoolProjector(prior_scale=2.0).fit(df).predict(df)[0])

    def test_an_unseen_bucket_at_predict_falls_back_to_the_global_line(self):
        """Same correct partial-pooling behaviour as an unseen level — degrade, never raise, never
        emit NaN. Real early folds DO have an empty youngest bucket."""
        df = _with_ages(_panel(400, seed=11))
        train = df[df[REL_BUCKET] != REL_LABELS[0]]
        test = df[df[REL_BUCKET] == REL_LABELS[0]]
        assert len(test) > 0
        m = PartialPoolProjector(prior_scale=2.0, bucket_col=REL_BUCKET, bucket_slope=True).fit(train)
        assert REL_LABELS[0] not in m.buckets_
        pred, sd = m.predict(test)
        assert np.isfinite(pred).all() and np.isfinite(sd).all()

    def test_gbm_use_age_removes_the_column_and_changes_the_fit(self):
        df = _with_ages(_panel(400, seed=12))
        with_age = GBMProjector(40, 2, 0.1, use_statcast=False, use_age=True).fit(df)
        no_age = GBMProjector(40, 2, 0.1, use_statcast=False, use_age=False).fit(df)
        assert no_age._features(df).shape[1] == with_age._features(df).shape[1] - 1
        assert not np.array_equal(with_age.predict(df)[0], no_age.predict(df)[0])
        assert "noage" in _config_name(no_age) and "noage" not in _config_name(with_age)


class TestCloneCarriesEveryField:
    """🪤 `clone_projector` silently dropped `extra_cols` from the moment slice 2 added it.

    Nothing broke, because the slice-2/4 runners construct projectors directly — but `emit_projections`
    round-trips through the clone, so the deferred S2 emission would have refit the winner with its
    Heckman regressor removed and served the plain incumbent under the winning arm's name. The test is
    MECHANICAL (it walks the dataclass fields) precisely so a slice-6 parameter cannot repeat it.
    """

    _PROBE = {"prior_scale": 3.5, "name": "probe", "weight_col": "mlb_pa",
              "extra_cols": ("_probe_col",), "bucket_col": REL_BUCKET,
              "bucket_slope": True, "bucket_intercept": True}

    def test_every_dataclass_field_has_a_probe_value(self):
        """If a new field is added without extending `_PROBE`, this fails LOUDLY rather than letting
        the completeness test below quietly stop covering it."""
        fields = {f.name for f in dataclasses.fields(PartialPoolProjector)}
        assert fields == set(self._PROBE), f"update _PROBE for {fields ^ set(self._PROBE)}"

    @pytest.mark.parametrize("field_name", [f.name for f in
                                            dataclasses.fields(PartialPoolProjector)])
    def test_field_survives_a_clone(self, field_name):
        original = PartialPoolProjector(**self._PROBE)
        assert getattr(clone_projector(original), field_name) == self._PROBE[field_name]

    def test_gbm_use_age_survives_a_clone(self):
        assert clone_projector(GBMProjector(10, 2, 0.1, use_age=False)).use_age is False


# ══════════════════════════════════════════════════════════════════════════════════════
class TestRecovery:
    """NF1.7 lesson 1 — an anchor that cannot fail passes on nothing.

    A block that cannot recover a PLANTED effect turns every real-data null into "my code does not
    work", and a channel foil that cannot separate the two channels makes the attribution unearned.
    Both are proven here on synthetic data with a known answer, in BOTH directions.
    """

    @pytest.fixture(scope="class")
    def rec(self):
        return synthetic_recovery_check(n=2400, seed=5)

    def test_a_planted_slope_effect_is_recovered_by_the_slope_arm(self, rec):
        assert rec["slope"]["slope_arm_pct_lift"] > 5.0

    def test_a_planted_slope_effect_is_not_claimed_by_the_intercept_arm(self, rec):
        """The discriminating half: per-bucket LEVEL shifts cannot mimic a per-bucket SLOPE."""
        assert rec["slope"]["intercept_arm_pct_lift"] < 1.0
        assert rec["slope"]["slope_arm_pct_lift"] > 5 * max(
            rec["slope"]["intercept_arm_pct_lift"], 0.1)

    def test_a_planted_intercept_effect_goes_to_the_intercept_arm(self, rec):
        """⭐ THE ATTRIBUTION TEST. Without this the `intercept_only_vs_rel_slope` anchor is untested
        machinery and a real-data 'the level explains it' reading would be unearned."""
        assert rec["intercept"]["intercept_arm_pct_lift"] > 5.0
        assert rec["intercept"]["slope_arm_pct_lift"] < 1.0

    def test_neither_arm_invents_a_lift_on_a_null_panel(self, rec):
        assert abs(rec["none"]["slope_arm_pct_lift"]) < 1.0
        assert abs(rec["none"]["intercept_arm_pct_lift"]) < 1.0


# ══════════════════════════════════════════════════════════════════════════════════════
def _board(rows: list[dict]) -> pd.DataFrame:
    base = {"kind": "ladder", "selectable": True, "fold_win_rate": 0.8, "oos_mae": 1.0,
            "p_one_sided": 0.01}
    return pd.DataFrame([{**base, **r} for r in rows])


_CLEAN = {"placebo_vs_rel_slope": {"violated": False},
          "intercept_only_vs_rel_slope": {"violated": False}}
_SURV_OK = {"available": True, "retention": 0.9, "survives_reweighting": True}


class TestVerdict:
    def test_nothing_clearing_the_fold_gate_drops(self):
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y2_rel_slope", "oos_mae": 0.9, "fold_win_rate": 0.55}])
        v, w, _ = s5_verdict(board, _CLEAN, _SURV_OK, [])
        assert (v, w) == ("DROP", "Y0_shipped")

    def test_a_violated_placebo_drops_even_with_a_big_lift(self):
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y2_rel_slope", "oos_mae": 0.5}])
        anchors = {**_CLEAN, "placebo_vs_rel_slope": {"violated": True}}
        v, w, reasons = s5_verdict(board, anchors, _SURV_OK, [])
        assert (v, w) == ("DROP", "Y0_shipped")
        assert any("placebo" in r for r in reasons)

    def test_a_violated_channel_foil_changes_the_claim_rather_than_dropping(self):
        """⭐ NF-D15 g′. Something real won, so DROP would be wrong — but the mechanism claimed is
        refuted, and the verdict has to SAY the finding is a mis-specified main effect."""
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y2_rel_slope", "oos_mae": 0.9}])
        anchors = {**_CLEAN, "intercept_only_vs_rel_slope": {"violated": True}}
        v, w, reasons = s5_verdict(board, anchors, _SURV_OK, [])
        assert v == "ADD_LEVEL_ONLY" and w == "Y3b_rel_growth_prior"
        assert any("mis-specified as LINEAR" in r for r in reasons)

    def test_a_collapsed_lift_under_reweighting_becomes_an_upper_bound(self):
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y2_rel_slope", "oos_mae": 0.9}])
        surv = {"available": True, "retention": 0.10, "survives_reweighting": False}
        v, w, reasons = s5_verdict(board, _CLEAN, surv, [])
        assert v == "UPPER_BOUND_ONLY" and w == "Y2_rel_slope"
        assert any("SELECTION" in r for r in reasons)

    def test_a_clean_slope_win_adds(self):
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y2_rel_slope", "oos_mae": 0.9}])
        assert s5_verdict(board, _CLEAN, _SURV_OK, [])[:2] == ("ADD", "Y2_rel_slope")

    def test_an_intercept_win_is_not_gated_by_the_slope_channel_foil(self):
        """`Y3b` beating `Y2` is the foil FIRING, not a disqualification of `Y3b` itself."""
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "Y3b_rel_growth_prior", "oos_mae": 0.9}])
        anchors = {**_CLEAN, "intercept_only_vs_rel_slope": {"violated": True}}
        assert s5_verdict(board, anchors, _SURV_OK, [])[:2] == ("ADD", "Y3b_rel_growth_prior")

    def test_a_sensitivity_arm_can_never_be_the_winner(self):
        """The IPW pair is a diagnostic. Its emission path was DEFERRED by PM ruling, so shipping one
        would ship a configuration that has no build."""
        board = _board([{"arm": "Y0_shipped", "oos_mae": 1.0},
                        {"arm": "V_ipw_Y2", "kind": "sensitivity", "oos_mae": 0.1}])
        assert s5_verdict(board, _CLEAN, _SURV_OK, [])[:2] == ("DROP", "Y0_shipped")

    def test_reference_arms_are_never_selectable(self):
        assert not any(a.selectable for a in S5_LADDER if a.kind in ("reference", "anchor"))
        assert by_label()["R_gbm_age"].kind == "reference"


class TestSurvivorshipRead:
    def test_a_missing_pair_reports_unavailable_and_demands_an_upper_bound(self):
        out = survivorship_read(pd.DataFrame({"Y0_shipped": [1.0], "Y2_rel_slope": [0.9]}))
        assert out["available"] is False and "UPPER BOUND" in out["note"]

    def test_a_retained_lift_survives(self):
        mae = pd.DataFrame({"Y0_shipped": [1.00, 1.00, 1.00, 1.00],
                            "Y2_rel_slope": [0.90, 0.90, 0.90, 0.90],
                            "V_ipw_Y0": [1.00, 1.00, 1.00, 1.00],
                            "V_ipw_Y2": [0.91, 0.91, 0.91, 0.91]})
        out = survivorship_read(mae)
        assert out["survives_reweighting"] is True
        assert out["retention"] == pytest.approx(0.9, abs=1e-6)

    def test_a_collapsed_lift_is_flagged_as_selection(self):
        mae = pd.DataFrame({"Y0_shipped": [1.00] * 4, "Y2_rel_slope": [0.90] * 4,
                            "V_ipw_Y0": [1.00] * 4, "V_ipw_Y2": [0.99] * 4})
        out = survivorship_read(mae)
        assert out["survives_reweighting"] is False
        assert out["retention"] == pytest.approx(0.1, abs=1e-6)
        assert "UPPER BOUND" in out["reading"]

    def test_a_non_positive_unweighted_lift_makes_retention_undefined_not_zero(self):
        """Dividing two numbers that are both the wrong sign produces a ratio that LOOKS like a
        retention. There is nothing to retain, and the read has to say so."""
        mae = pd.DataFrame({"Y0_shipped": [1.00] * 4, "Y2_rel_slope": [1.10] * 4,
                            "V_ipw_Y0": [1.00] * 4, "V_ipw_Y2": [1.20] * 4})
        out = survivorship_read(mae)
        assert out["retention"] is None and out["survives_reweighting"] is False
        assert "does not arise" in out["reading"]

    def test_the_floor_is_pre_registered_at_a_sane_value(self):
        assert 0.0 < SURVIVORSHIP_RETENTION_MIN < 1.0


class TestLadderShape:
    def test_labels_are_unique(self):
        labels = [a.label for a in S5_LADDER]
        assert len(labels) == len(set(labels))

    def test_the_baseline_is_first_and_inert(self):
        y0 = by_label()["Y0_shipped"]
        assert S5_LADDER[0].label == "Y0_shipped"
        assert y0.bucket_col is None and not y0.bucket_slope and not y0.bucket_intercept
        assert not y0.ipw and not y0.gbm and not y0.linear_interaction

    def test_both_channels_are_registered_on_the_same_bucketing(self):
        """The matched foil is only matched if it uses the IDENTICAL bucketing."""
        slope = by_label()["Y2_rel_slope"]
        foil = by_label()["Y3b_rel_growth_prior"]
        assert slope.bucket_col == foil.bucket_col == REL_BUCKET
        assert slope.bucket_slope and not slope.bucket_intercept
        assert foil.bucket_intercept and not foil.bucket_slope

    def test_the_gbm_pair_differs_only_in_age(self):
        a, b = by_label()["R_gbm_age"], by_label()["R_gbm_noage"]
        assert a.gbm and b.gbm and a.gbm_use_age and not b.gbm_use_age
        assert not (a.selectable or b.selectable)

    def test_the_ipw_pair_is_a_matched_base_and_arm(self):
        base, arm = by_label()["V_ipw_Y0"], by_label()["V_ipw_Y2"]
        assert base.ipw and arm.ipw
        assert base.bucket_col is None            # the matched BASE carries no mechanism
        assert arm.bucket_col == REL_BUCKET and arm.bucket_slope

    def test_the_placebo_permutes_and_mirrors_the_real_arm(self):
        p = by_label()["A_bucket_placebo"]
        assert p.permute and p.bucket_slope and not p.selectable

    def test_the_borrowed_s2_arm_still_exists_on_the_s2_ladder(self):
        """If S2's winner is ever re-labelled, this raises instead of silently testing a DIFFERENT
        correction under the same name."""
        from betting_ml.scripts.milb_mle.run_e7_12_slice2 import S2_LADDER

        assert _S2_SENSITIVITY_ARM.label in {a.label for a in S2_LADDER}
        real = next(a for a in S2_LADDER if a.label == _S2_SENSITIVITY_ARM.label)
        assert real.ipw == _S2_SENSITIVITY_ARM.ipw


class TestAnchors:
    def test_the_free_learner_gap_is_reported_as_a_paired_read(self):
        mae = pd.DataFrame({"Y0_shipped": [1.0] * 4, "Y2_rel_slope": [1.0] * 4,
                            "A_bucket_placebo": [1.0] * 4, "Y3b_rel_growth_prior": [1.0] * 4,
                            "Y5_linear_interaction": [1.0] * 4,
                            "R_gbm_age": [0.90] * 4, "R_gbm_noage": [0.99] * 4})
        board = _board([{"arm": c, "oos_mae": float(mae[c].mean())} for c in mae.columns])
        out = s5_anchors(mae, board)["free_learner_age_value"]
        assert out["mean_mae_gap"] == pytest.approx(0.09, abs=1e-9)
        assert out["folds_age_helps"] == 4

    def test_a_missing_gbm_pair_omits_the_probe_rather_than_faking_it(self):
        mae = pd.DataFrame({"Y0_shipped": [1.0] * 4, "Y2_rel_slope": [1.0] * 4})
        board = _board([{"arm": c, "oos_mae": 1.0} for c in mae.columns])
        assert "free_learner_age_value" not in s5_anchors(mae, board)

    def test_a_missing_anchor_arm_is_reported_unavailable_not_passed(self):
        mae = pd.DataFrame({"Y0_shipped": [1.0] * 4, "Y2_rel_slope": [1.0] * 4})
        board = _board([{"arm": c, "oos_mae": 1.0} for c in mae.columns])
        a = s5_anchors(mae, board)["placebo_vs_rel_slope"]
        assert a["available"] is False and a["violated"] is False
