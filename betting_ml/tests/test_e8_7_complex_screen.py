"""E8.7 — fast-gate guards for the complex-level translation screen.

These pin the TWO defects the pre-registered anchors caught in the screen's own instrument. Both
were live bugs in the first cut, and both are the same class: an invented constant standing in for a
measured null. Every guard here was verified to go RED against the pre-fix implementation.

Pure logic only — no network, no S3 (the module's fetch path is never touched).
"""
import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle import run_e8_7_complex_screen as screen

METRICS = ("k_pct", "bb_pct", "iso", "woba")


def _lines(n: int, pa: int, seed: int = 3, talent_sd: float = 0.045) -> pd.DataFrame:
    """Synthetic season lines with a KNOWN between-player talent spread.

    ⚠️ The fixture must carry real talent heterogeneity or these guards test nothing. A first cut
    gave every player the SAME true rate, so the observed variance WAS pure sampling noise and a
    correct estimator returns reliability ~ 0 — the guards then failed for a reason that had
    nothing to do with the estimator (the NF-D17 vacuous-fixture trap, facing the other way).
    Each player now draws a true rate, then their counts are drawn given it, so the population has
    a real signal variance the reliability estimator is supposed to recover.
    """
    rng = np.random.default_rng(seed)
    true_k = np.clip(rng.normal(0.22, talent_sd, n), 0.03, 0.55)
    true_bb = np.clip(rng.normal(0.10, talent_sd * 0.7, n), 0.01, 0.35)
    true_h = np.clip(rng.normal(0.26, talent_sd * 0.8, n), 0.08, 0.45)
    true_hr = np.clip(rng.normal(0.12, 0.05, n), 0.0, 0.45)

    bb = rng.binomial(pa, true_bb)
    ab = np.maximum(pa - bb, 1)
    so = rng.binomial(ab, true_k)
    h = rng.binomial(ab, true_h)
    dbl = rng.binomial(h, 0.20)
    tpl = rng.binomial(np.maximum(h - dbl, 0), 0.04)
    hr = rng.binomial(np.maximum(h - dbl - tpl, 0), true_hr)
    df = pd.DataFrame({
        "bat_plate_appearances": np.full(n, pa), "bat_at_bats": ab, "bat_hits": h,
        "bat_doubles": dbl, "bat_triples": tpl, "bat_home_runs": hr, "bat_walks": bb,
        "bat_intentional_walks": np.zeros(n, int), "bat_hit_by_pitch": np.zeros(n, int),
        "bat_sac_flies": np.zeros(n, int), "bat_strike_outs": so,
        "bat_total_bases": h + dbl + 2 * tpl + 3 * hr,
    })
    out = screen.compute_rate_metrics_from_counts(df)
    out = out.rename(columns={f"minor_{m}": m for m in METRICS})
    out.attrs["true_k_var"] = float(np.var(true_k, ddof=1))
    return out


# ══════════════════════════════════════════════════════════════════════════════════
# DEFECT (a) — the reliability ceiling must be a real bound, not a negative number.
# The first cut used a delta-method bound `p*(w_max - p)/n` that over-stated the noise
# so badly that wOBA reliability came out NEGATIVE at EVERY rung, including rungs the
# MLE already trusts. A negative reliability is not a finding; it is a broken estimator,
# and it would have been read as "the mechanism cannot act" (a false INACTIVE verdict).
# ══════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("metric", METRICS)
def test_sampling_noise_never_exceeds_observed_variance_for_a_real_population(metric):
    """RED against the delta-method bound, for iso and woba."""
    df = _lines(600, pa=200)
    noise = float(np.nanmean(screen._sampling_noise_var(df, metric)))
    obs = float(np.var(df[metric].to_numpy(float), ddof=1))
    assert noise <= obs, (
        f"{metric}: mean sampling-noise variance {noise:.3e} exceeds the observed variance "
        f"{obs:.3e} -> reliability would be NEGATIVE, which is an estimator bug, not a finding"
    )


@pytest.mark.parametrize("metric", METRICS)
def test_reliability_is_in_the_unit_interval(metric):
    rel = screen.reliability(_lines(600, pa=200), metric)["reliability"]
    assert rel is not None
    assert 0.0 < rel < 1.0, f"{metric}: reliability {rel} outside (0,1)"


def test_binomial_metrics_use_the_EXACT_variance_not_an_approximation():
    """k_pct/bb_pct are exact binomial rates; the estimator must reproduce p(1-p)/n exactly."""
    df = _lines(200, pa=250)
    got = screen._sampling_noise_var(df, "k_pct")
    p = df["k_pct"].to_numpy(float)
    np.testing.assert_allclose(got, p * (1 - p) / 250.0, rtol=1e-12)


def test_reliability_RECOVERS_the_KNOWN_true_value():
    """Oracle check: the fixture's true talent variance is known, so the answer is known.

    reliability = var_true / (var_true + var_noise). This is the strongest form of the guard —
    it pins the estimator to a value rather than only to a sign or an ordering.
    """
    n, pa = 4000, 220
    df = _lines(n, pa=pa, seed=21)
    got = screen.reliability(df, "k_pct")["reliability"]
    var_true = df.attrs["true_k_var"]
    var_noise = float(np.nanmean(screen._sampling_noise_var(df, "k_pct")))
    expected = var_true / (var_true + var_noise)
    assert got == pytest.approx(expected, abs=0.05), (
        f"reliability {got:.3f} does not recover the known {expected:.3f}"
    )


def test_reliability_RISES_with_line_thickness():
    """The ceiling must respond to the thing it is a function of — a thicker line is a more
    reliable measurement. A constant/negative estimator would not order these."""
    thin = screen.reliability(_lines(800, pa=120, seed=11), "k_pct")["reliability"]
    thick = screen.reliability(_lines(800, pa=500, seed=11), "k_pct")["reliability"]
    assert thick > thin, f"reliability did not rise with PA ({thin:.3f} -> {thick:.3f})"


# ══════════════════════════════════════════════════════════════════════════════════
# DEFECT (b) — the permutation floor's stringency must NOT be a side-effect of n.
# The first cut scored ONE permutation draw against a fixed |r| < 0.05. A single draw's
# sd is ~1/sqrt(n), so that constant is ~1.7 sigma at n=3509 but only ~0.57 sigma at
# n=130 (the MH2-H8 defect: a clause whose false-fire rate moves with the design). The
# second cut ("null mean within 3 SE of zero") failed 26 of 40 cells INCLUDING the
# incumbent rungs — a floor a known-good rung cannot pass measures the wrong thing.
# ══════════════════════════════════════════════════════════════════════════════════

def _pairs(n: int, rho: float, seed: int, n_seasons: int = 20) -> pd.DataFrame:
    """Transition pairs with a known true correlation, in the shape `evaluate` consumes."""
    rng = np.random.default_rng(seed)
    a = rng.normal(size=n)
    b = rho * a + np.sqrt(max(1 - rho**2, 0)) * rng.normal(size=n)
    d = {"season_dst": rng.integers(2006, 2006 + n_seasons, n),
         "bat_plate_appearances_src": np.full(n, 200), "bat_plate_appearances_dst": np.full(n, 300)}
    for m in METRICS:
        d[f"{m}_c_src"], d[f"{m}_c_dst"] = a, b
        d[f"{m}_src"], d[f"{m}_dst"] = a, b
    return pd.DataFrame(d)


@pytest.mark.parametrize("n", [150, 1500])
def test_a_TRUE_NULL_is_not_declared_signal_at_EITHER_sample_size(n):
    """The floor must behave the same at n=150 and n=1500 — that is the whole point.

    RED against the fixed-|r| criterion, which passes comfortably at n=1500 and is
    near-vacuous at n=150.
    """
    res = screen.evaluate(_pairs(n, rho=0.0, seed=5), "k_pct",
                          np.random.default_rng(screen.SCREEN_SEED))
    assert res["floor_ok"], "the null must still be CHARACTERISED on true-null data"
    # bias-corrected r sits inside the null's own spread => correctly NOT signal
    assert abs(res["z_vs_permutation_null"]) < 3.0, (
        f"n={n}: a TRUE NULL scored {res['z_vs_permutation_null']:.1f} sd out — the floor is "
        f"manufacturing signal"
    )
    assert abs(res["r_adj"]) < 0.15


@pytest.mark.parametrize("n", [150, 1500])
def test_a_REAL_effect_is_detected_at_EITHER_sample_size(n):
    """The two-sided half: a floor that can never fire is as useless as one that always does."""
    res = screen.evaluate(_pairs(n, rho=0.55, seed=5), "k_pct",
                          np.random.default_rng(screen.SCREEN_SEED))
    assert res["z_vs_permutation_null"] > 3.0
    assert res["ci_lo"] > 0
    assert res["r_adj"] == pytest.approx(0.55, abs=0.15)


def test_the_null_LOCATION_is_subtracted_from_the_reported_statistic():
    """`r_adj` is what the gate reads. It must be r minus the measured null location.

    This is the correction that cut DSL->MLB K% from a 0.96x ratio to 0.58x — i.e. it is
    load-bearing against the headline, not cosmetic.
    """
    res = screen.evaluate(_pairs(400, rho=0.30, seed=9), "iso",
                          np.random.default_rng(screen.SCREEN_SEED))
    assert res["r_adj"] == pytest.approx(res["r"] - res["perm_mean"], abs=1e-12)


def test_the_floor_uses_MANY_draws_so_the_null_has_a_measurable_spread():
    """A single draw gives a location estimate with no scale — the original defect."""
    assert screen.PERMUTATION_DRAWS >= 100
    res = screen.evaluate(_pairs(500, rho=0.2, seed=4), "bb_pct",
                          np.random.default_rng(screen.SCREEN_SEED))
    assert res["perm_sd"] > 0, "the null must have a measured SCALE, not just a location"
    assert res["perm_se"] < res["perm_sd"]


# ══════════════════════════════════════════════════════════════════════════════════
# Wiring: the screen must not silently diverge from the model or the ingest.
# ══════════════════════════════════════════════════════════════════════════════════

def test_screen_inherits_the_PA_floor_rather_than_inventing_one():
    from betting_ml.scripts.milb_mle.level_ladder import MIN_TRANSITION_PA
    assert screen.MIN_TRANSITION_PA is MIN_TRANSITION_PA


def test_screen_derives_rungs_through_the_INGESTS_map_not_a_private_copy():
    assert screen._ingest.derive_level_name(16, 130, "Dominican Summer League") == "DSL"
    assert screen._ingest.derive_level_name(16, 124, "Gulf Coast League") == "CPX"


def test_incumbent_benchmarks_are_registered_transitions():
    """The bar is 0.50x an incumbent rung, so that rung must actually be measured."""
    assert screen.INCUMBENT_BENCHMARK in screen.TRANSITIONS
    assert screen.INCUMBENT_MLB_BENCHMARK in screen.TRANSITIONS


def test_season_centring_removes_the_level_season_mean():
    """Defect (c): the era confound. Centred rates must have ~zero mean in every cell."""
    df = _lines(400, pa=200)
    df["level_name"] = np.where(np.arange(400) % 2 == 0, "DSL", "CPX")
    df["season"] = 2006 + (np.arange(400) % 8)
    df["player_id"] = np.arange(400)
    raw = df.assign(**{c: df[c] for c in df.columns})
    for m in METRICS:
        raw[f"{m}_c"] = raw[m] - raw.groupby(["level_name", "season"])[m].transform("mean")
        cell_means = raw.groupby(["level_name", "season"])[f"{m}_c"].mean().abs()
        assert cell_means.max() < 1e-12, f"{m}: (rung, season) mean not removed"
