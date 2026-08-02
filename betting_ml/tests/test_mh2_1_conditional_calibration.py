"""Guards for MH2.1's conditional-calibration check.

Fast-gate safe: pure numpy/scipy, no fitting, no Snowflake, no S3, no `pipeline`.

WHAT THIS PROTECTS
------------------
The diagnostic exists because CRPS and PIT-KS are both blind to a homoscedastic model's loss of
per-game variance. That makes it a check whose OWN sensitivity has to be proven — and its first cut
was NOT sensitive (a max−min range statistic, swamped by sampling noise, made it read blind). These
guards pin the corrected design and the two cost/vacuity protections.
"""
from __future__ import annotations

import inspect

import numpy as np
import pytest

from betting_ml.scripts import mh2_1_conditional_calibration as cal
from betting_ml.utils.promotion_gate import PredictiveOutput


# ── 💸 cost protection ────────────────────────────────────────────────────────────────────────

def test_it_refuses_to_pull_rather_than_waking_snowflake(tmp_path, monkeypatch):
    """The whole point of this diagnostic is that it is FREE. A missing cache must HALT with
    instructions, never silently trigger a pull — ~80% of the Snowflake bill is warehouse
    wake/idle (E11.20-COST), so an accidental pull is a real cost, not a rounding error."""
    monkeypatch.setattr(cal, "_CACHE", tmp_path / "does_not_exist.parquet")
    with pytest.raises(SystemExit) as e:
        cal.run()
    msg = str(e.value)
    assert "REFUSES to pull" in msg and "Snowflake" in msg


def test_the_matrix_is_never_refreshed_from_source():
    """`refresh_cache` must be hard-wired False — a True here would pull the whole feature matrix."""
    src = inspect.getsource(cal.run)
    assert "refresh_cache=False" in src
    assert "refresh_cache=True" not in src


# ── ⚠️ the POSITIVE CONTROL must isolate exactly one mechanism ────────────────────────────────

def test_the_positive_control_changes_only_whether_sigma_VARIES():
    """It keeps the parent's means AND its average variance, so the only difference is per-game
    variation in sigma. Matching average sharpness is what makes a detected gap attributable to the
    VARIATION rather than to the control merely being wider or narrower (NF-D15 g′)."""
    rng = np.random.default_rng(0)
    loc = rng.normal(9, 1, 500)
    scale = rng.uniform(2.0, 6.0, 500)
    parent = PredictiveOutput.normal(loc, scale)
    flat = cal._flatten(parent)

    assert np.allclose(flat.loc, parent.loc), "means must be untouched"
    assert len(np.unique(flat.scale)) == 1, "the control must be genuinely homoscedastic"
    # same AVERAGE variance — the matched-foil property
    assert float(np.mean(flat.scale ** 2)) == pytest.approx(float(np.mean(parent.scale ** 2)))


# ── the statistic: a SLOPE, because a RANGE cannot work ───────────────────────────────────────

def test_var_z_slope_is_flat_for_a_correctly_specified_model():
    rng = np.random.default_rng(1)
    n, k = 6000, 10
    sigma = rng.uniform(2, 6, n)
    z = rng.normal(0, 1, n)                      # correctly specified ⇒ Var(z)=1 everywhere
    lab = np.argsort(np.argsort(sigma)) * k // n
    assert abs(cal._var_z_slope(z, lab, k)) < 0.01


def test_var_z_slope_DETECTS_a_homoscedastic_model():
    """The signature: dividing by a constant when the truth is heteroscedastic makes Var(z) rise
    with the true sigma. If this failed, the diagnostic could not see its own target."""
    rng = np.random.default_rng(2)
    n, k = 6000, 10
    sigma = rng.uniform(2, 6, n)
    y = rng.normal(0, sigma)                      # truth IS heteroscedastic
    z_homo = y / np.sqrt(np.mean(sigma ** 2))     # the homoscedastic model's standardisation
    lab = np.argsort(np.argsort(sigma)) * k // n
    assert cal._var_z_slope(z_homo, lab, k) > 0.05, "must rise across sigma strata"
    # and the correctly-specified standardisation of the SAME data must stay flat
    assert abs(cal._var_z_slope(y / sigma, lab, k)) < 0.02


def test_a_max_minus_min_RANGE_would_have_been_noise_dominated():
    """⚠️ REGRESSION on the defect that made the first cut read blind.

    A range over k noisy per-stratum estimates measures k and n, not miscalibration: at ~320 rows
    per decile a PERFECTLY calibrated model posts an expected max−min coverage near 0.07. The
    observed spreads were 0.084–0.122, i.e. entirely inside that null band — which is why the
    statistic had to become a permutation-tested SLOPE.
    """
    rng = np.random.default_rng(3)
    ranges = [np.ptp([(rng.random(320) < 0.8).mean() for _ in range(10)]) for _ in range(600)]
    assert np.mean(ranges) > 0.05, (
        "if this ever became small the range statistic would be usable — re-derive before trusting "
        "any spread-based reading"
    )
    # the slope, by contrast, has a null centred on zero
    assert abs(cal._var_z_slope(rng.normal(0, 1, 3200),
                                np.repeat(np.arange(10), 320), 10)) < 0.02


def test_pit_is_uniform_for_a_correctly_specified_normal():
    from scipy.stats import kstest

    rng = np.random.default_rng(4)
    loc, scale = rng.normal(9, 1, 4000), rng.uniform(2, 6, 4000)
    y = rng.normal(loc, scale)
    pit = cal._pit(y, PredictiveOutput.normal(loc, scale))
    assert kstest(pit, "uniform").pvalue > 0.01


def test_the_interval_is_the_nominal_central_band():
    loc = np.zeros(5)
    lo, hi = cal._interval(PredictiveOutput.normal(loc, np.ones(5)), nominal=0.80)
    assert lo[0] == pytest.approx(-1.2816, abs=1e-3)
    assert hi[0] == pytest.approx(+1.2816, abs=1e-3)


# ── the verdict states must be reachable and honest ───────────────────────────────────────────

def test_the_statistic_is_distance_from_truth_not_distance_from_the_incumbent():
    """⚠️ REGRESSION on the defect that INVERTED this study's own first verdict.

    The original rule asked "does the leader's slope differ from the matched foil's?", which assumes
    the foil is the calibrated reference. On the real 8-fold run the foil was the WORST arm in the
    field, so the rule labelled the BETTER-calibrated arm as the damaged one. For ANY conditionally
    calibrated predictive `Var(z) = 1` in every stratum — an analytic truth needing no oracle — so
    that, not the incumbent, is the anchor.
    """
    perfect = [{"var_z": 1.0} for _ in range(10)]
    assert cal._calibration_rms(perfect) == pytest.approx(0.0)

    bad = [{"var_z": v} for v in (1.4, 1.3, 1.1, 1.1, 1.1, 1.0, 1.1, 1.0, 1.0, 0.9)]
    good = [{"var_z": v} for v in (0.97, 1.0, 0.9, 0.99, 0.99, 0.95, 1.04, 1.01, 1.0, 1.1)]
    assert cal._calibration_rms(good) < cal._calibration_rms(bad)

    # and the verdict must FOLLOW the truth-anchored score, not the foil comparison
    rms = {"incumbent::ngboost_normal": 0.158, "plus_eb::ngboost_normal": 0.180,
           "plus_eb::glm_elasticnet": 0.050, "plus_eb::ngboost_FLATTENED": 0.107}
    v, prose, extra = cal._verdict(
        rms, 0.08, {"z_score": 51.7}, {"z_score": 39.0},
        incumbent="incumbent::ngboost_normal", foil="plus_eb::ngboost_normal",
        leader="plus_eb::glm_elasticnet", control="plus_eb::ngboost_FLATTENED")
    assert v == "INCUMBENT_VARIANCE_UNINFORMATIVE", (
        "when flattening the incumbent's sigma IMPROVES its calibration, the per-game sigma was "
        "never informative and the swap cannot be blocked on variance grounds"
    )
    assert extra["leader_better_than_incumbent"] is True


def test_a_genuinely_worse_leader_still_trips_the_material_verdict():
    """The corrected rule must not have become unfalsifiable — an informative incumbent sigma PLUS a
    worse leader must still block."""
    rms = {"incumbent::ngboost_normal": 0.05, "plus_eb::ngboost_normal": 0.05,
           "plus_eb::glm_elasticnet": 0.20, "plus_eb::ngboost_FLATTENED": 0.18}
    v, _, extra = cal._verdict(
        rms, 0.08, {"z_score": 30.0}, {"z_score": 30.0},
        incumbent="incumbent::ngboost_normal", foil="plus_eb::ngboost_normal",
        leader="plus_eb::glm_elasticnet", control="plus_eb::ngboost_FLATTENED")
    assert v == "VARIANCE_LOSS_MATERIAL"
    assert extra["flattening_the_incumbent_sigma_hurts"] is True


def test_rescoring_a_stored_run_refits_nothing():
    """The corrected verdict must be recoverable from stored per-stratum Var(z) — the operator
    should never pay for another fit (or another Snowflake wake) to fix a scoring rule."""
    src = inspect.getsource(cal.rescore)
    assert "_calibration_rms" in src and "_verdict(" in src
    for forbidden in ("load_clean_matrix", "fit_predict", "make_gate_splitter"):
        assert forbidden not in src, f"rescore must not {forbidden}"


def test_it_can_declare_itself_blind_or_inactive_rather_than_passing():
    """Two ways this check must decline to answer instead of returning a clean bill of health:
    INSTRUMENT_BLIND (the positive control did not separate — NF1.7 (a)) and MECHANISM_INACTIVE
    (sigma is effectively constant, so there is no per-game variance to lose — NF1.9)."""
    src = inspect.getsource(cal.run)
    src = inspect.getsource(cal._verdict)
    assert '"MECHANISM_INACTIVE"' in src
    assert '"INCUMBENT_VARIANCE_UNINFORMATIVE"' in src
    assert "MIN_SIGMA_CV" in src
    # the inactive branch gates everything else — it must be checked FIRST
    assert src.index('"MECHANISM_INACTIVE"') < src.index('"VARIANCE_LOSS_MATERIAL"')


def test_the_shared_stratifier_is_the_matched_foil_not_the_leader():
    """All arms must sit on IDENTICAL row groupings (the homoscedastic arm has no sigma variation to
    stratify by), and the grouping must come from the arm the positive control is derived from, or
    the control is blunted and the instrument understates its own power."""
    src = inspect.getsource(cal.run)
    assert 'strat_sigma.append(np.asarray(outs["plus_eb::ngboost_normal"].scale, float))' in src


def test_best_alpha_is_zero_and_the_report_says_so():
    assert cal.BEST_ALPHA == 0
    src = inspect.getsource(cal._write)
    assert "Not an edge claim" in src
    assert "Snowflake-free" in src
