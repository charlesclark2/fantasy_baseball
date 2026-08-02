"""Guards for MH2.1 — the WIDE-WINDOW re-run of E7.9's retrain bake-off.

Fast-gate safe: imports only `betting_ml`, inspects source, and fits nothing. No Snowflake, no S3,
no `pipeline`. The real 8-fold run is the operator's, and the runtime-gate rule (CI-green is not
sufficient) applies here like anywhere else.

WHAT THIS FILE IS ACTUALLY PROTECTING
-------------------------------------
MH2.1's entire value is that its DESIGN was fixed before its RESULT was seen. Every guard below
pins one leg of that: the window, the field, the DSR convention, the report's disclosures, and the
two defects the build-out's own harness check surfaced (a reference arm inflating the trial
dispersion, and the E2.1-r oracle leaking into the trial field). A story whose pre-registration can
drift silently after the fact has no pre-registration.
"""
from __future__ import annotations

import inspect
import re

import numpy as np
import pytest

from betting_ml.scripts import e7_9_train_serve_consistency as e79
from betting_ml.utils import cv_power


def _source_without_comments(fn) -> str:
    """Source with comment-only lines stripped.

    ⚠️ INC-38: a source-inspection guard that matches ANYWHERE in the file is VACUOUS — the
    explanatory comment written above a fixed call satisfies it even after the call itself is
    broken. Every source assertion below runs through here so prose cannot pass the test.
    """
    return "\n".join(ln for ln in inspect.getsource(fn).splitlines()
                     if not ln.strip().startswith("#"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 1 — the window and the 2020 decision, registered rather than discovered
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_window_and_the_2020_decision_are_pinned_constants():
    """The PRIMARY window is 2016 and the DECLARED sensitivity is dropping 2020. Both are the
    story's pre-registration; if either drifts, the run is window-shopping rather than a re-test."""
    assert e79.MH21_MIN_YEAR == 2016
    assert e79.MH21_SENSITIVITY_EXCLUDE == (2020,)


def test_the_registered_window_yields_the_eight_folds_the_story_claims():
    """MH2's headline: 2016–2026 is 11 seasons ⇒ 8 folds, available today. The fold count is a
    deterministic function of the window (`n_seasons − min_train_seasons`), so this is checkable
    without any data — and it is the arithmetic the whole story rests on."""
    n_seasons = 2026 - e79.MH21_MIN_YEAR + 1
    assert n_seasons == 11
    assert cv_power.achievable_folds(n_seasons) == 8
    # the declared sensitivity drops one season ⇒ one fewer fold
    assert cv_power.achievable_folds(n_seasons - 1) == 7
    # and what E7.9 actually ran, for contrast
    assert cv_power.achievable_folds(2026 - 2021 + 1) == 3


def test_the_sensitivity_arm_is_labelled_in_the_result_so_the_two_are_never_confused():
    for excl, expect in [((), "PRIMARY"), ((2020,), "SENSITIVITY")]:
        stem = e79._report_stem({
            "target": "total_runs", "tier": "post_lineup", "smoke": False,
            "window": {"is_mh2_1": True, "min_year": 2016, "excluded_seasons": list(excl)},
        })
        assert ("no2020" in stem) == bool(excl), f"{expect} arm must be distinguishable in the stem"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 1b — the field is DECLARED, and cannot be silently narrowed
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_pre_registered_family_is_exactly_four_arms():
    """MH2 §2b: DSR's bar rises with the FIELD SIZE (required per-fold Sharpe 1.69 at 28 arms vs
    1.18 at 4). The family is `{incumbent, plus_eb} × {incumbent learner, one direct-learned foil}`
    — E7.9's own follow-up #2, not a grid."""
    assert e79.MH21_VARIANTS == ("incumbent", "plus_eb")
    assert e79.MH21_LEARNERS == ("ngboost_normal", "glm_elasticnet")
    assert len(e79.MH21_VARIANTS) * len(e79.MH21_LEARNERS) == 4
    # the incumbent LEARNER for total_runs must be in the family, or there is no bar to beat
    assert e79.INCUMBENT_CLASS["total_runs"] in e79.MH21_LEARNERS


def test_family_filter_restricts_variants_and_leaves_the_full_grid_untouched():
    cols = set(e79._read_contract(e79.SERVED_CONTRACTS[("total_runs", "post_lineup")]))
    cols |= set(e79.MLE_AFFECTED_COLS) | set(e79.E79_GB_COLS)

    full = e79.build_arm_contracts("total_runs", "post_lineup", cols, family="full")
    mh21 = e79.build_arm_contracts("total_runs", "post_lineup", cols, family="mh2_1")

    assert set(mh21) == set(e79.MH21_VARIANTS)
    # E7.9's own field is unchanged by MH2.1 existing — the baseline must stay the baseline
    assert set(full) == {"incumbent", "plus_gb", "plus_eb", "plus_both"}
    assert mh21["incumbent"] == full["incumbent"]
    assert mh21["plus_eb"] == full["plus_eb"]


def test_a_missing_pre_registered_learner_halts_rather_than_shrinking_the_field():
    """Trimming a field after registration UNDER-taxes DSR and is a second layer of the very
    selection bias DSR exists to deflate (MH2 §a). So an unbuildable pre-registered arm must be a
    HALT, never a quiet 3-arm run."""
    src = _source_without_comments(e79.run_retrain_bakeoff)
    assert "MH2.1 pre-registered learner(s)" in src
    assert "raise SystemExit" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 3 — the DSR convention, and the two defects the build-out caught
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _fold_scores(n=8, seed=0):
    """A synthetic (arm → per-fold metric) map: incumbent plus three challengers."""
    rng = np.random.default_rng(seed)
    inc = 2.50 + rng.normal(0, 0.03, n)
    return {
        "incumbent::ngboost_normal": list(inc),
        "plus_eb::ngboost_normal": list(inc - rng.normal(0.01, 0.02, n)),
        "incumbent::glm_elasticnet": list(inc - rng.normal(0.005, 0.02, n)),
        "plus_eb::glm_elasticnet": list(inc - rng.normal(0.012, 0.02, n)),
    }


def test_dsr_observations_are_FOLDS_not_month_buckets():
    """MH2 defect 2, half one. The statistic scales with `√(n_obs−1)`, and E7.9 counted ~19
    non-independent month buckets where its design yielded 3 folds."""
    fs = _fold_scores(n=8)
    out = e79.dsr_gate(fs, "incumbent::ngboost_normal", "plus_eb::glm_elasticnet", n_trials=4)
    assert out["available"]
    assert out["n_obs"] == 8, "observations must be the purged folds"


def test_trial_sharpes_are_MEASURED_not_the_asymptotic_fallback():
    """MH2 defect 2, half two. Omitting `trial_sharpes` makes `deflated_sharpe` fall back to
    `V = 1/n_obs`, silently substituting an easier benchmark for the measured field dispersion."""
    fs = _fold_scores(n=8)
    out = e79.dsr_gate(fs, "incumbent::ngboost_normal", "plus_eb::glm_elasticnet", n_trials=4)
    assert out["trial_sharpes"], "the measured per-arm Sharpes must be recorded"
    assert np.isfinite(out["var_trials_sr"])
    # the measured benchmark must genuinely differ from the asymptotic one it replaces
    assert out["sr0"] != pytest.approx(out["sr0_asymptotic_V"])
    # and the asymptotic figure is reported beside it, never instead of it
    assert np.isfinite(out["dsr_asymptotic_V"])


def test_the_reference_arm_is_excluded_from_the_trial_dispersion():
    """REGRESSION — defect 1 of 2 found by this harness's own build-out.

    The incumbent's skill-vs-itself series is identically ZERO by construction. Feeding that forced
    0 into a variance estimated from a handful of arms inflates `V`, hence `SR0`, for a purely
    structural reason. `h_harness.dsr_report` excludes its foil for exactly this reason.
    """
    fs = _fold_scores(n=8)
    inc = "incumbent::ngboost_normal"
    out = e79.dsr_gate(fs, inc, "plus_eb::glm_elasticnet", n_trials=4)
    assert inc not in out["trial_arms"], "the reference is not one of the trials"
    assert len(out["trial_arms"]) == len(fs) - 1

    # prove the excluded value would have MOVED the answer — a guard that cannot fail is no guard
    skill = {a: np.asarray(fs[inc], float) - np.asarray(v, float) for a, v in fs.items()}
    with_ref = float(np.var([e79._sharpe(skill[a]) for a in fs], ddof=1))
    assert with_ref != pytest.approx(out["var_trials_sr"]), (
        "including the zero reference must change V, or this exclusion is untested"
    )


def test_the_oracle_anchor_never_enters_the_trial_field():
    """REGRESSION — defect 2 of 2, and the more dangerous one.

    The E2.1-r `oracle_floor` SEES the realized target. Left in the trial field it posted a per-fold
    skill Sharpe near 30 and drove the measured dispersion to V≈220 / SR0≈15.6 — i.e. an anchor that
    exists to POLICE the metric was silently setting the gate's bar, making DSR unclearable for an
    arithmetic reason rather than an evidential one. Caught on smoke data before any real arm was
    scored.
    """
    src = _source_without_comments(e79.run_retrain_bakeoff)
    assert re.search(r"dsr_gate\(\s*\{n:\s*fold_scores\[n\]\s*for n in arm_names\}", src), (
        "dsr_gate must be handed CANDIDATE arms only — `arm_names` excludes the oracle"
    )

    # and demonstrate the failure the exclusion prevents
    fs = _fold_scores(n=8)
    inc = "incumbent::ngboost_normal"
    clean = e79.dsr_gate(fs, inc, "plus_eb::glm_elasticnet", n_trials=4)
    poisoned = e79.dsr_gate({**fs, "oracle_floor": [0.0002] * 8}, inc,
                            "plus_eb::glm_elasticnet", n_trials=5)
    assert poisoned["sr0"] > clean["sr0"] * 5, (
        "an oracle in the trial field must visibly blow up SR0 — otherwise this regression is "
        "not actually being tested"
    )
    assert poisoned["degenerate_trial_arms"], "and it must be FLAGGED, not absorbed silently"


def test_a_degenerate_leader_series_is_UNDEFINED_rather_than_a_silent_pass_or_fail():
    """NF1.7 (a): a check that could not be evaluated must say so. When the leader IS the incumbent
    the skill series is identically zero, and DSR is undefined — not failed, not passed."""
    fs = _fold_scores(n=8)
    out = e79.dsr_gate(fs, "incumbent::ngboost_normal", "incumbent::ngboost_normal", n_trials=4)
    assert out["available"] is False
    assert "UNDEFINED" in out["note"]


def test_the_legacy_convention_is_reported_but_never_binds():
    """The size of MH2 defect 2 has to be visible on the record. Both figures are emitted; only the
    fixed one is allowed to gate."""
    src = _source_without_comments(e79.run_retrain_bakeoff)
    assert 'dsr_p = float(dsr_fixed["dsr"])' in src, "the FIXED convention must feed the gate"
    assert '"binding": False' in src, "the legacy figure must be marked non-binding"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 5 — the bar is stated before the run, and the null names its state
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_design_bar_reproduces_the_numbers_MH2_published():
    """MH2 §7's design table is what commissioned this story. If these drift, either the table or
    the harness is wrong, and the story's premise is unverified."""
    assert e79.design_bar(3, 28)["dsr_required_per_fold_sr_asymptotic_V"] == pytest.approx(7.28, abs=0.01)
    assert e79.design_bar(8, 28)["dsr_required_per_fold_sr_asymptotic_V"] == pytest.approx(1.69, abs=0.01)
    assert e79.design_bar(8, 4)["dsr_required_per_fold_sr_asymptotic_V"] == pytest.approx(1.18, abs=0.01)


def test_the_bar_is_computed_before_any_arm_is_scored():
    """Not decorative: a bar computed after the scores is not a pre-registration. `design_bar` must
    be called before the fitting loop."""
    src = _source_without_comments(e79.run_retrain_bakeoff)
    assert src.index("design_bar(") < src.index("fit_predict("), (
        "the bar must be stated before the first arm is fitted"
    )


def test_pbo_is_UNDEFINED_at_three_folds_and_evaluable_at_eight():
    """The single sharpest statement of why the window mattered: E7.9's PBO was not FAILED, it was
    not COMPUTABLE. MH2.1's window makes it computable."""
    assert cv_power.pbo_evaluable(3, 28) is False
    assert cv_power.pbo_evaluable(8, 4) is True


def test_a_null_names_which_of_the_seven_states_it_is_in():
    fs = _fold_scores(n=8)
    good = e79.dsr_gate(fs, "incumbent::ngboost_normal", "plus_eb::glm_elasticnet", n_trials=4)

    # a negative point estimate is never rescued by n or by field size (NF-D15 g")
    absent = e79.classify_the_null(metric="crps", n_folds=8, n_arms=4, margin=-0.01,
                                   dsr_fixed=good)
    assert absent["state"] == "GENUINE_ABSENCE"
    assert absent["retest_trigger"] is None, "a genuine absence must NOT carry a re-test trigger"

    # and at 3 folds the deflation requirement was never evaluated at all
    undef = e79.classify_the_null(metric="crps", n_folds=3, n_arms=28, margin=0.01,
                                  dsr_fixed=good)
    assert undef["state"] == "UNDEFINED"

    live = e79.classify_the_null(metric="crps", n_folds=8, n_arms=4, margin=0.01, dsr_fixed=good)
    assert live["state"] in cv_power.NULL_STATES


def test_the_meaningful_effect_is_a_pre_existing_design_constant():
    """NF1.8: a threshold reverse-engineered from the answer is not a threshold. The
    practically-meaningful lift is the program's own `NOISE_FLOOR['crps']`, fixed long before this
    story existed."""
    from betting_ml.utils.promotion_gate import NOISE_FLOOR

    assert e79.MH21_MEANINGFUL_CRPS_LIFT == NOISE_FLOOR["crps"]


def test_the_mde_is_derived_from_the_gate_this_harness_actually_runs():
    """`cv_power.mde_in_sd_units` simulates a fold-consistency + BH composite. E7.9's rule carries
    NEITHER, so using it would report on a rule the harness does not run — this repo's most-repeated
    defect shape."""
    src = _source_without_comments(e79.classify_the_null)
    assert "dsr_required_sr(" in src
    # ⚠️ match the CALL, not the mention: the docstring legitimately NAMES the rejected helper to
    # explain why it is rejected, and a bare-substring assertion would fire on that explanation.
    # Same vacuity trap as INC-38's, facing the other way — here prose would FAIL a true guard.
    assert "mde_in_sd_units(" not in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# LOCK 2 + LOCK 4 — the reporting obligations
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_per_season_contract_coverage_is_measured_on_the_real_matrix():
    import pandas as pd

    df = pd.DataFrame({
        "game_year": [2016] * 4 + [2025] * 4,
        "a": [1.0, None, 1.0, None, 1.0, 1.0, 1.0, 1.0],
        "b": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
    })
    cov = e79.contract_coverage_by_season(df, ["a", "b"])
    assert cov[2016]["coverage"] == pytest.approx(0.75)
    assert cov[2025]["coverage"] == pytest.approx(1.0)
    assert cov[2016]["rows"] == 4


def test_a_structurally_absent_contract_column_is_named_not_averaged_away():
    """⚠️ A PER-SEASON MEAN HIDES THE THING THAT MATTERS.

    The served 13-column contract carries `away_lineup_bat_speed_vs_starter_velo`, a Statcast
    BAT-TRACKING feature that did not exist before 2023 (measured: 0.000 non-null in 2021 and 2022,
    0.483 in 2023, 1.000 from 2024). Pooled, that reads as "0.83 coverage" — uniformly noisier data.
    In truth a SPECIFIC feature is entirely missing for the older half of the window, so those folds
    evaluate a structurally SMALLER contract, imputed to a constant in that slot. A lift read across
    those folds is not comparable to one read across the late folds, and only per-column resolution
    can say so.
    """
    import pandas as pd

    df = pd.DataFrame({
        "game_year": [2019] * 5 + [2025] * 5,
        "bat_speed": [None] * 5 + [1.0] * 5,          # did not exist yet
        "sporadic": [1.0, None, 1.0, 1.0, 1.0] * 2,   # merely patchy — NOT structurally absent
        "always": [1.0] * 10,
    })
    cov = e79.contract_coverage_by_season(df, ["bat_speed", "sporadic", "always"])

    assert cov[2019]["structurally_absent"] == ["bat_speed"]
    assert cov[2025]["structurally_absent"] == []
    # a merely-patchy column must NOT be swept into the same bucket as a nonexistent one
    assert "sporadic" not in cov[2019]["structurally_absent"]
    assert cov[2019]["per_column"]["bat_speed"] == pytest.approx(0.0)
    assert cov[2019]["per_column"]["sporadic"] == pytest.approx(0.8)


def test_the_report_flags_structural_absence_loudly():
    src = _source_without_comments(e79._append_mh21_sections)
    assert "STRUCTURALLY ABSENT" in src
    assert "structurally_absent" in src


def test_the_per_fold_table_pairs_score_with_coverage():
    """LOCK 2's whole purpose: a lift living only in the thin early folds is an imputation
    artifact. That is unreadable unless the two sit in the same row."""
    src = _source_without_comments(e79.run_retrain_bakeoff)
    for key in ("contract_coverage", "eval_season", "leader_minus_incumbent"):
        assert key in src, f"the per-fold table must carry {key}"


def test_the_point_in_time_ceiling_caveat_is_unconditional():
    """LOCK 4. A disclosure that only appears when it flatters the run is not a disclosure — and
    widening the window WIDENS the non-point-in-time exposure rather than shrinking it."""
    assert "CEILING" in e79.MH21_POINT_IN_TIME_CAVEAT
    assert "NOT POINT-IN-TIME" in e79.MH21_POINT_IN_TIME_CAVEAT
    src = _source_without_comments(e79._write_bakeoff_report)
    assert "point_in_time_caveat" in src


def test_an_mh2_1_run_can_never_overwrite_a_recorded_e7_9_verdict():
    """E7.9's three recorded verdicts are the baseline MH2.1 is measured against. Clobbering one
    would destroy the comparison the story exists to make."""
    e79_stem = e79._report_stem({"target": "total_runs", "tier": "post_lineup", "smoke": False,
                                 "window": {"is_mh2_1": False}})
    mh21_stem = e79._report_stem({
        "target": "total_runs", "tier": "post_lineup", "smoke": False,
        "window": {"is_mh2_1": True, "min_year": 2016, "excluded_seasons": []}})
    assert e79_stem == "e7_9_retrain_total_runs_post_lineup"
    assert mh21_stem.startswith("mh2_1_retrain_")
    assert e79_stem != mh21_stem


def test_a_wider_window_gets_its_own_training_matrix_cache_key():
    """⚠️ The silent failure this prevents: `get_cached_df` keys only on the string it is given, so
    serving a 2016-window request out of the 2021 parquet would report a fold count the run did not
    have. Same shape as every other 'reports on a quantity it is not measuring' defect."""
    from betting_ml.scripts import model_bakeoff

    src = _source_without_comments(model_bakeoff.load_clean_matrix)
    assert 'edge_e1_training_from{int(min_year)}' in src
    assert "load_features(min_year=int(min_year))" in src


def test_the_honest_frame_survives_in_the_report():
    """`best_alpha = 0`. A CRPS improvement on total_runs is a PRICING improvement, never an edge,
    a win rate, or an ROI — and that has to be in the artifact, not just in a session's prose."""
    assert e79.BEST_ALPHA == 0
    src = _source_without_comments(e79._write_bakeoff_report)
    assert "PRICING/CALIBRATION improvement" in src
    assert "never an edge" in src
