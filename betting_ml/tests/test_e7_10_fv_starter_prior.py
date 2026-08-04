"""Guards for MLB Edge-E7.10 — FV as an incremental cold-start rate prior for debuting starters.

E7.10 shipped a NULL, and a null's guards have a specific job: make sure the null was reached by a
mechanism that COULD have found an effect. A study that structurally cannot detect anything produces a
null too, and it looks identical from the outside.

⭐ **EVERY GUARD HERE WAS RED-PROVEN** against deliberately broken source before being trusted, and each
one isolates ONE clause — the NF-D17 lesson: a guard on an `and`-composed rule is VACUOUS unless its
fixture satisfies every OTHER clause, because a second clause already refusing the fixture makes the
deletion of the named clause change nothing observable.

Pure numpy/pandas fixtures — no S3, no DuckDB, no `pipeline` import (the fast-gate rule).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.fv_translation import build_fv_starter_cohort as bc
from betting_ml.scripts.fv_translation import fv_starter_prior as fp


# ══════════════════════════════════════════════════════════════════════════════════════
# Fixtures — a synthetic cohort whose FV↔outcome link is CONTROLLABLE
# ══════════════════════════════════════════════════════════════════════════════════════


def _cohort(n_per_fold: int = 40, cohorts=(2019, 2020, 2021, 2022, 2023, 2024, 2025),
            fv_beta: float = 0.0, seed: int = 3) -> pd.DataFrame:
    """A study frame with a TUNABLE FV effect.

    `fv_beta = 0` ⇒ FV carries no information (the null world). `fv_beta` large ⇒ FV genuinely drives
    the realized rate, so a working harness MUST find it. Both directions are exercised, because a
    harness that cannot find a planted effect would emit exactly the null E7.10 reports.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for c in cohorts:
        for i in range(n_per_fold):
            fv = float(rng.choice([35, 40, 45, 50, 55, 60]))
            mle = float(np.clip(0.22 + rng.normal(0, 0.03), 0.02, 0.6))
            noise = float(rng.normal(0, 0.02))
            rows.append({
                "player_id": f"{c}_{i}", "level": "Triple-A", "debut_cohort": c,
                "fv": fv, "fv_board_season": c - 1, "risk": rng.choice(["High", "Medium"]),
                "eta": c, "milb_start_share": 0.9, "is_starter": True,
                "has_mlb_label": True, "mlb_pa": 400.0, "mlb_bip": 300.0,
                "mle_k_pct": mle, "mle_bb_pct": mle / 3, "mle_gb_pct": 0.44,
                "mlb_k_pct": float(np.clip(mle + fv_beta * (fv - 45.0) + noise, 0.01, 0.9)),
                "mlb_bb_pct": float(np.clip(mle / 3 + noise, 0.01, 0.5)),
                "mlb_gb_pct": float(np.clip(0.44 + noise, 0.05, 0.95)),
            })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The harness can find an effect that IS there  (⇒ the null is about the data)
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_planted_fv_effect_is_recovered_so_the_null_is_not_a_dead_harness():
    """⭐ THE MOST IMPORTANT GUARD IN THIS FILE. A study that cannot detect anything emits a null that
    is indistinguishable from a real one. Plant a strong FV→rate link and require the mechanism arm to
    beat the MATCHED foil on a clear majority of folds."""
    st = fp.run_metric(_cohort(fv_beta=0.004), "k_pct")
    assert fp.relative_gain_vs_foil(st) > 0.05, "a planted FV effect was NOT recovered"
    assert st.leaderboard.set_index("arm").loc[fp.MECHANISM_ARM, "fold_win_rate"] >= 0.8


def test_with_no_planted_effect_the_mechanism_does_not_manufacture_one():
    """The other side of the same coin: on FV-free data the FV arm must NOT systematically win, or the
    harness would invent lift wherever it looked."""
    st = fp.run_metric(_cohort(fv_beta=0.0), "k_pct")
    assert fp.relative_gain_vs_foil(st) < 0.03


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The matched foil — the one design decision the verdict turns on
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_primary_defender_is_the_matched_foil_not_the_served_prior():
    """`C0_mle_recal` (the same regression MINUS FV) must be the defender. Defending against the raw
    served MLE mean would let recalibration-alone lift be attributed to the scouting grade
    (NF-D10 (g) / NF-D15 (g′))."""
    assert fp.FOIL == "C0_mle_recal"
    assert fp.SERVED_REFERENCE == "L0_mle_served"
    assert fp.FOIL != fp.SERVED_REFERENCE


def test_the_matched_foil_differs_from_the_served_arm_by_exactly_the_fv_columns():
    """The foil must be a MATCHED foil: identical design matrix except the FV block. If it also dropped
    the intercept/slope, the 'match' would be a fiction and the contrast would measure two changes."""
    df = _cohort()
    train, test = df[df.debut_cohort < 2024], df[df.debut_cohort == 2024]
    rng = np.random.default_rng(0)
    x_foil = fp._design(fp.ARM_BY_LABEL[fp.FOIL], train, test, "k_pct", rng)
    x_mech = fp._design(fp.ARM_BY_LABEL[fp.MECHANISM_ARM], train, test, "k_pct", rng)
    assert x_mech.shape[1] == x_foil.shape[1] + 1, "A1 must be C0 plus exactly the FV column"
    assert np.allclose(x_mech[:, :x_foil.shape[1]], x_foil), "the shared columns must be identical"


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. Anchors — an anchor that cannot act is a pass on NOTHING (NF1.7 (a))
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_placebo_actually_moves_rows_so_its_loss_is_not_a_pass_on_nothing():
    """`Z_fv_permuted` must be demonstrably DIFFERENT from the arm it defends. An inert anchor is more
    dangerous than a missing one: the report looks healthy while the check tested nothing."""
    st = fp.run_metric(_cohort(fv_beta=0.002), "k_pct")
    assert st.anchor_moves["Z_fv_permuted"]["pct_rows_moved"] > 50.0


def test_the_placebo_loses_to_a_real_effect_when_one_exists():
    """A shuffled grade must be BEATEN when the real grade genuinely carries information — otherwise
    the placebo could never refute anything and the anchor is decorative."""
    st = fp.run_metric(_cohort(fv_beta=0.004), "k_pct")
    s = st.leaderboard.set_index("arm")["oos_mae"]
    assert s["Z_fv_permuted"] > s[fp.MECHANISM_ARM], "the placebo must lose to a REAL effect"


def test_both_sharpness_degenerates_lose_so_the_score_is_not_gameable_from_either_side():
    """NF1.7 (3): reporting ONE sharpness degenerate leaves the score gameable from the other side. A
    maximally SHARP arm and a maximally WIDE arm must BOTH lose the primary score."""
    st = fp.run_metric(_cohort(fv_beta=0.001), "k_pct")
    s = st.leaderboard.set_index("arm")["oos_mae"]
    assert s["Z_sigma_sharp"] > s[fp.MECHANISM_ARM], "the SHARP degenerate must lose"
    assert s["Z_sigma_wide"] > s[fp.MECHANISM_ARM], "the WIDE degenerate must lose"


def test_the_sharpness_degenerates_change_only_the_spread_never_the_mean():
    """They must be the mechanism arm's MEAN at a scaled σ. If they moved the mean too they would test
    two things at once and their loss would be uninterpretable."""
    st = fp.run_metric(_cohort(fv_beta=0.002), "k_pct")
    s = st.leaderboard.set_index("arm")["oos_pointscore_mae"]
    assert s["Z_sigma_sharp"] == pytest.approx(s[fp.MECHANISM_ARM])
    assert s["Z_sigma_wide"] == pytest.approx(s[fp.MECHANISM_ARM])


def test_the_degenerate_cohort_mean_loses_so_the_metric_is_not_inverted():
    """NF-D11: a criterion a know-nothing degenerate WINS cannot select anything. Keep it in the field
    every run and READ it — do not reason about whether the score inverts."""
    st = fp.run_metric(_cohort(fv_beta=0.0), "k_pct")
    s = st.leaderboard.set_index("arm")["oos_mae"]
    assert s["Z_cohort_mean"] > s[fp.FOIL]


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. Trial-field hygiene — a diagnostic is never a trial (MH2.1 (a))
# ══════════════════════════════════════════════════════════════════════════════════════


def test_diagnostic_and_anchor_arms_are_excluded_from_the_eligible_trial_field():
    """An arm that exists to POLICE the reading must never set the gate's own bar. `Z_*` anchors and
    the `D_*` diagnostic must be absent from `ELIGIBLE_ARMS` (⇒ from PBO and the DSR trial field)."""
    for label in [a.label for a in fp.ARMS if a.label.startswith(("Z_", "D_"))]:
        assert label not in fp.ELIGIBLE_ARMS, f"{label} must not be a trial"
    assert fp.FOIL not in fp.ELIGIBLE_ARMS and fp.SERVED_REFERENCE not in fp.ELIGIBLE_ARMS


def test_the_declared_family_is_exactly_the_three_fv_forms():
    """MH2 (a): you pre-register a family, you do not discover one. Trimming this set after seeing the
    answer would re-commit the very selection bias DSR exists to deflate (MH2.2)."""
    assert set(fp.ELIGIBLE_ARMS) == {"A1_mle_fv", "A2_mle_fv_bucket", "A3_mle_fv_eta_risk"}
    assert all(fp.ARM_BY_LABEL[a].uses_fv for a in fp.ELIGIBLE_ARMS)


def test_the_diagnostic_arm_drops_the_mle_column_or_it_answers_a_different_question():
    """`D_fv_over_generic` must carry NO `mle_<m>` column — it exists to ask whether FV is informative
    ON ITS OWN. With the MLE still in it would silently be a fourth FV arm."""
    df = _cohort()
    rng = np.random.default_rng(0)
    x = fp._design(fp.ARM_BY_LABEL["D_fv_over_generic"], df, df, "k_pct", rng)
    x_mech = fp._design(fp.ARM_BY_LABEL[fp.MECHANISM_ARM], df, df, "k_pct", rng)
    assert x.shape[1] == x_mech.shape[1] - 1
    mle = pd.to_numeric(df["mle_k_pct"], errors="coerce").to_numpy(float)
    assert not any(np.allclose(x[:, j], mle) for j in range(x.shape[1])), \
        "the diagnostic must not carry the MLE column"


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. Leakage + population — the as-of rule and the served row
# ══════════════════════════════════════════════════════════════════════════════════════


def _board(seasons=(2018, 2019, 2020), player="p1") -> pd.DataFrame:
    return pd.DataFrame([{"player_id": player, "fv_board_season": s, "fv_as_of_date": f"{s}-07-01",
                          "fv": 40.0 + s - 2018, "risk": "High", "eta": s + 1,
                          "overall_rank": 10.0, "org_rank": 1.0} for s in seasons])


def test_the_headline_asof_rule_admits_only_strictly_prior_board_seasons():
    """⭐ THE LEAKAGE GUARD. E7.7 serves the RETAINED board stamped `<season>-07-01`, so a DEBUT-season
    grade can embed a revision made after the pitcher debuted. The headline rule must exclude it."""
    pop = pd.DataFrame([{"player_id": "p1", "debut_cohort": 2020}])
    got = bc.attach_pre_debut_fv(pop, _board(), "strictly_prior_season")
    assert int(got["fv_board_season"].iloc[0]) == 2019, "must take the LATEST STRICTLY-PRIOR board"
    assert int(got["fv_board_season"].iloc[0]) < 2020, "a debut-season grade is hindsight-exposed"


def test_the_loose_asof_rule_is_a_separate_named_sensitivity_and_does_admit_the_debut_season():
    """The sensitivity must genuinely differ from the headline, or reporting it proves nothing."""
    pop = pd.DataFrame([{"player_id": "p1", "debut_cohort": 2020}])
    loose = bc.attach_pre_debut_fv(pop, _board(), "same_season_allowed")
    assert int(loose["fv_board_season"].iloc[0]) == 2020


def test_a_pitcher_with_no_admissible_grade_keeps_null_fv_and_is_never_dropped():
    """The coverage gate depends on ungraded pitchers SURVIVING into the frame as MLE-prior fallbacks.
    Dropping them would silently inflate coverage to 100%."""
    pop = pd.DataFrame([{"player_id": "p1", "debut_cohort": 2018},
                        {"player_id": "p2", "debut_cohort": 2020}])
    got = bc.attach_pre_debut_fv(pop, _board(seasons=(2019,), player="p2"), "strictly_prior_season")
    assert len(got) == 2, "an ungraded pitcher must NOT be dropped"
    assert pd.isna(got.set_index("player_id").loc["p1", "fv"])


def test_an_unknown_asof_rule_raises_rather_than_silently_defaulting():
    with pytest.raises(ValueError):
        bc.attach_pre_debut_fv(pd.DataFrame([{"player_id": "p", "debut_cohort": 2020}]),
                               _board(), "whatever_i_typed")


def test_coverage_is_reported_over_cohorts_the_board_could_have_graded():
    """NF1.8: a coverage figure over a quietly different population than the one it names. Cohorts at
    or before the board's first season are 0% BY CONSTRUCTION and must not dilute the headline."""
    proj = pd.DataFrame([
        {"player_id": "old", "level": "Triple-A", "debut_cohort": 2017, "is_prospect": False,
         **{f"mle_{m}": 0.2 for m in fp.PRIOR_METRICS}, **{f"mlb_{m}": 0.2 for m in fp.PRIOR_METRICS}},
        {"player_id": "new", "level": "Triple-A", "debut_cohort": 2020, "is_prospect": False,
         **{f"mle_{m}": 0.2 for m in fp.PRIOR_METRICS}, **{f"mlb_{m}": 0.2 for m in fp.PRIOR_METRICS}},
    ])
    pairs = pd.DataFrame([{"player_id": p, "level": "Triple-A", "mlb_pa": 400.0, "mlb_bip": 300.0,
                           "has_mlb_label": True, "pit_games_started": 20, "pit_games_played": 20}
                          for p in ("old", "new")])
    _df, rep = bc.build_frame(proj, pairs, _board(seasons=(2018, 2019), player="new"),
                              season_ceiling=2025)
    # "new" is graded, "old" cannot be — pooled says 50%, the honest figure says 100%
    assert rep["fv_coverage_pooled_incl_pre_board_cohorts"] == pytest.approx(0.5)
    assert rep["fv_coverage_of_gradable_labelled_starters"] == pytest.approx(1.0)
    assert rep["first_gradable_debut_cohort"] == 2019


def test_the_scored_row_is_the_highest_reached_level_the_served_prior_uses():
    """`eb_starter_posteriors` reads ONE row per pitcher at his highest level. Scoring a lower-level
    translation would calibrate on a population serving never sees."""
    proj = pd.DataFrame([
        {"player_id": "p", "level": lv, "debut_cohort": 2020, "is_prospect": False,
         **{f"mle_{m}": 0.2 for m in fp.PRIOR_METRICS}, **{f"mlb_{m}": 0.2 for m in fp.PRIOR_METRICS}}
        for lv in ("Single-A", "Double-A", "Triple-A")])
    pairs = pd.DataFrame([{"player_id": "p", "level": lv, "mlb_pa": 400.0, "mlb_bip": 300.0,
                           "has_mlb_label": True, "pit_games_started": 20, "pit_games_played": 20}
                          for lv in ("Single-A", "Double-A", "Triple-A")])
    df, _rep = bc.build_frame(proj, pairs, _board(player="p"), season_ceiling=2025)
    assert len(df) == 1 and df["level"].iloc[0] == "Triple-A"


# ══════════════════════════════════════════════════════════════════════════════════════
# 6. Thin-sample floors — inherited from E7.5/E7.5p VERBATIM, not re-derived
# ══════════════════════════════════════════════════════════════════════════════════════


def test_thin_mlb_cameos_are_excluded_the_e7_5_landmine():
    """A handful of TBF makes a realized rate almost pure noise and blows up the residual spread
    (the E7.5 cameo landmine). `has_mlb_label` must gate the scored population."""
    df = _cohort()
    df.loc[df.index[:10], "has_mlb_label"] = False
    assert len(fp.eligible_rows(df, "k_pct")) == len(df) - 10


def test_gb_pct_carries_its_own_second_order_bip_floor():
    """E7.5p: a pitcher can clear 150 TBF while putting few balls in play, and a ~20-BIP realized GB%
    is nearly pure sampling noise. GB% needs the SECOND floor; K%/BB% must not."""
    df = _cohort()
    df.loc[df.index[:10], "mlb_bip"] = 5.0
    assert len(fp.eligible_rows(df, "gb_pct")) == len(df) - 10
    assert len(fp.eligible_rows(df, "k_pct")) == len(df), "the BIP floor must not touch a BF metric"


def test_the_primary_population_is_the_leakage_safe_pre_debut_start_share():
    """The starter filter must be knowable AT CALL-UP. Anything conditioned on post-debut usage would
    select on the outcome's neighbourhood."""
    df = _cohort()
    df.loc[df.index[:10], "milb_start_share"] = 0.1
    assert len(fp.eligible_rows(df, "k_pct", "starter")) == len(df) - 10
    assert len(fp.eligible_rows(df, "k_pct", "all_pitchers")) == len(df)


# ══════════════════════════════════════════════════════════════════════════════════════
# 7. Folds, scoring and reproducibility
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_fold_is_purged_by_debut_cohort_so_no_pitcher_straddles_the_boundary():
    """Every eval cohort must be strictly newer than everything it trained on."""
    st = fp.run_metric(_cohort(), "k_pct")
    assert st.fold_cohorts == sorted(st.fold_cohorts)
    assert min(st.fold_cohorts) > 2019, "the earliest cohort can only ever TRAIN"


def test_the_earliest_cohort_is_never_evaluated_because_it_has_no_prior_to_train_on():
    st = fp.run_metric(_cohort(cohorts=(2020, 2021, 2022, 2023)), "k_pct")
    assert 2020 not in st.fold_cohorts


def test_crps_punishes_both_over_sharpness_and_over_width():
    """The property the two-sided sharpness anchors rely on. If CRPS were monotone in σ, one of those
    anchors could never fire and would be decorative."""
    y, mu = np.array([0.25]), np.array([0.22])
    at = {s: float(fp.normal_crps(y, mu, np.array([s]))[0]) for s in (0.001, 0.03, 1.0)}
    assert at[0.03] < at[0.001] and at[0.03] < at[1.0]


def test_a_zero_variance_delta_is_decided_on_sign_not_treated_as_untestable():
    """NF1.7 (a) facing the other way: a CONSTANT advantage is the most systematic case there is, and a
    t-test that bails on zero variance would let it pass unexamined."""
    assert fp.one_sided_paired_p(np.array([0.5, 0.5, 0.5, 0.5])) == 0.0
    assert fp.one_sided_paired_p(np.array([-0.5, -0.5, -0.5, -0.5])) == 1.0
    assert fp.one_sided_paired_p(np.array([1.0, 2.0])) is None, "too few folds ⇒ no p, never a pass"


def test_fv_buckets_are_fixed_not_fitted_in_fold():
    """An in-fold bucket-edge search would be a hidden extra trial that PBO and DSR never see."""
    assert fp.FV_BUCKET_EDGES == (40.0, 45.0, 50.0)
    got = fp.fv_bucket_labels(pd.Series([30.0, 42.0, 47.0, 60.0, np.nan]))
    assert got.tolist() == ["lt40", "40_45", "45_50", "ge50", "missing"]


def test_a_category_unseen_in_train_maps_to_the_baseline_not_a_new_column():
    """Train and test design matrices must be column-aligned, or the fold silently scores a different
    model than it fitted."""
    tr, te = pd.Series(["High", "Medium"]), pd.Series(["High", "Extreme"])
    assert fp._one_hot(tr, te).shape == (2, 1)
    assert fp._one_hot(tr, te)[1, 0] == 0.0, "an unseen category must fall to the baseline"


def test_the_study_is_reproducible_given_its_seed():
    """The placebo is randomised; a run whose verdict moves between invocations is not a record."""
    a = fp.run_metric(_cohort(), "k_pct").leaderboard.set_index("arm")["oos_mae"]
    b = fp.run_metric(_cohort(), "k_pct").leaderboard.set_index("arm")["oos_mae"]
    pd.testing.assert_series_equal(a, b)


def test_every_arm_is_floored_by_the_peeking_version_of_its_own_form():
    """NF-D16 (g‴): `A1` NESTS `C0`, so a single shared ceiling would veto a legitimately-better nested
    form as a false metric inversion. Each arm must be floored by ITS OWN peeking version."""
    st = fp.run_metric(_cohort(fv_beta=0.002), "k_pct")
    assert set(st.oracle_floor) == {a.label for a in fp.ARMS}
    for arm in (fp.MECHANISM_ARM, fp.FOIL, fp.SERVED_REFERENCE):
        assert fp.oracle_floor_holds(st, arm), f"{arm} beat its OWN oracle ⇒ the score is inverted"


def test_the_meaningful_effect_threshold_is_pinned_so_a_null_cannot_be_rescored_against_a_softer_bar():
    """The practically-meaningful effect is set from E7.5p's RECORDED gains, before this run. Moving it
    afterwards would be reverse-engineering the verdict from the answer (E2.1-r)."""
    assert fp.MEANINGFUL_REL_CRPS_GAIN == 0.03
    assert fp.MIN_START_SHARE == 0.50
