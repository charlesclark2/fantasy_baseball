"""Guards for MH2.10 — the morning-tier (`pre_lineup_v6`) served-calibration audit.

⭐ WHAT THESE GUARDS ARE FOR
===================================================================================================
MH2.10's answer is a NON-firing verdict. The repo's standing lesson is that a study whose headline
is a null is exactly the study whose instrument must be proven able to produce the OTHER answer —
a check that cannot fail is not a check (NF1.7 (a)), and the MH2 lineage has now hit that class at
the level of a clause (INC-38), a whole inference harness (MH2.6) and a remedy string (MH2.7).

So the load-bearing guards here are REACHABILITY guards: every verdict the decision rule can emit
must be shown to be emittable, and every clause of the AND-composed firing rule must be shown to
bind ON ITS OWN.

⭐ CLAUSE ISOLATION (NF-D17). `SIGMA_SCALE_DEFECT` fires on `A and B and C and D`. A fixture that
trips two clauses at once proves NEITHER — the guard stays green when you delete the clause it
names, because a second clause is already refusing the fixture. Each clause below therefore gets a
fixture that SATISFIES every other clause, so only the named one can flip the result.

These are fast-gate tests: they import from `betting_ml`, never from `pipeline` (E11.23).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts import mh2_10_morning_audit as M

FAST_REPS = 600          # above the vacuity floor, fast enough for the gate


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The lean variance path may never drift from the imported one
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_variance_stats_agrees_exactly_with_the_imported_totals_stats():
    """`variance_stats` exists only so the shape-matched null has a lean, PIT-free surface. If it
    ever disagreed with `totals_stats`, the shape-matched null would be judging a different
    statistic from the one the Normal null judges, and the scale-vs-shape comparison would be
    meaningless."""
    rng = np.random.default_rng(0)
    fr = M.clean_frame(500, rng)
    y, mu, sg = fr["y_total"].values, fr["mu"].values, fr["sigma"].values
    k = M.n_strata(len(y))
    a = M.totals_stats(y, mu, sg, np.random.default_rng(1), k)
    b = M.variance_stats(y, mu, sg, k)
    for key in M.VARIANCE_STATS:
        assert a[key] == pytest.approx(b[key], abs=1e-12), key


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The ddof=0 lock — what makes the shape-matched null's hypothesis actually be "σ is right"
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_shape_pool_is_standardised_to_population_variance_exactly_one():
    """RED-PROVABLE: flipping `ddof=0` to `ddof=1` in `standardized_shape_pool` moves the pool's
    population variance to (n−1)/n, which shifts the whole shape-matched null's CENTRE below 1 and
    biases every σ-scale test toward finding a defect. This asserts the property that stops it."""
    rng = np.random.default_rng(3)
    fr = M.clean_frame(400, rng)
    pool = M.standardized_shape_pool(fr["y_total"].values, fr["mu"].values, fr["sigma"].values)
    assert float(np.mean(pool)) == pytest.approx(0.0, abs=1e-12)
    assert float(np.var(pool, ddof=0)) == pytest.approx(1.0, abs=1e-12)


def test_the_shape_matched_null_centres_on_var_z_of_one():
    """The consequence of the lock, measured rather than asserted: draws from the shape-matched
    null must have `Var(z)` centred on 1, or its null hypothesis is not 'the σ scale is correct'."""
    rng = np.random.default_rng(4)
    fr = M.clean_frame(600, rng)
    mu, sg = fr["mu"].values, fr["sigma"].values
    pool = M.standardized_shape_pool(fr["y_total"].values, mu, sg)
    draws = [float(np.var((M.draw_shape_matched(mu, sg, pool, rng) - mu) / sg, ddof=1))
             for _ in range(300)]
    assert float(np.median(draws)) == pytest.approx(1.0, abs=0.02)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. LOCK 4c — the shape-matched null may judge the VARIANCE statistics and nothing else
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_shape_matched_null_never_judges_a_pit_or_coverage_statistic():
    """Applying it to the PIT statistics would build the very shape defect being tested INTO the
    null, making the shape untestable by construction. The restriction is structural (the lean
    `variance_stats` surface) and this guard pins it."""
    forbidden = {"pit_mdd", "pit_ks", "cov80", "cov50", "cov80_integer_inclusive", "crps", "bias"}
    assert not (set(M.VARIANCE_STATS) & forbidden)
    rng = np.random.default_rng(5)
    fr = M.clean_frame(300, rng)
    out = M.shape_matched_verdict(fr["y_total"].values, fr["mu"].values, fr["sigma"].values,
                                  M.n_strata(300), FAST_REPS, 42)
    assert set(out["null"]) <= set(M.VARIANCE_STATS)
    assert not (set(M.variance_stats(fr["y_total"].values, fr["mu"].values,
                                     fr["sigma"].values, 3)) & forbidden)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ⭐ VERDICT REACHABILITY — a verdict machine with one reachable verdict is vacuous
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.parametrize("scale", [1.25, 0.80])
def test_sigma_scale_defect_is_reachable_in_both_directions(scale):
    """MH2.10's headline is a NON-firing verdict, so the firing one must be proven emittable —
    and in BOTH directions, because a machine that can only detect UNDER-dispersion would report a
    null for an over-dispersed model no matter how badly it was mis-scaled."""
    fr = M.clean_frame(655, np.random.default_rng(11), sigma_scale=scale)
    v = M.run(frame=fr, reps=FAST_REPS, with_power=False, with_games_needed=False,
              windows=("FULL",))["verdict"]
    assert v["verdict"] == "SIGMA_SCALE_DEFECT"
    assert v["phase_2_fires"] is True


@pytest.mark.slow
def test_a_clean_frame_does_not_fire_phase_2():
    fr = M.clean_frame(655, np.random.default_rng(12))
    v = M.run(frame=fr, reps=FAST_REPS, with_power=False, with_games_needed=False,
              windows=("FULL",))["verdict"]
    assert v["phase_2_fires"] is False


def test_the_shape_matched_null_is_unbiased_on_a_SKEWED_truth():
    """⭐ THE mechanism guard that licenses any scale-vs-shape attribution at all.

    The real target is right-skewed. If the shape-matched null were mis-CENTRED on a skewed truth,
    then "the σ scale is correct" would not be its null hypothesis, every σ verdict on real data
    would be biased, and the study's whole conclusion would be an artefact of its own instrument.

    This asserts the mechanism (the null sits at `Var(z) = 1`, and a correctly-scaled skewed world
    lands on either side of it with equal probability) rather than sampling a handful of verdicts
    and hoping none of them trips at the α level — a sampled-outcome assertion cannot distinguish
    "the discriminator is biased" from "this seed drew a 1-in-20", which is precisely the
    distinction that matters here.
    """
    med, obs = [], []
    for s in range(12):
        rng = np.random.default_rng(700 + s)
        fr = M.clean_frame(655, rng, shape_alpha=M.SKEW_CONTROL_ALPHA)
        y, mu, sg = fr["y_total"].values, fr["mu"].values, fr["sigma"].values
        pool = M.standardized_shape_pool(y, mu, sg)
        draws = [float(np.var((M.draw_shape_matched(mu, sg, pool, rng) - mu) / sg, ddof=1))
                 for _ in range(200)]
        med.append(float(np.median(draws)))
        obs.append(float(np.var((y - mu) / sg, ddof=1)))
    assert float(np.mean(med)) == pytest.approx(1.0, abs=0.01), "shape-matched null is mis-centred"
    assert 0.2 <= float(np.mean(np.asarray(obs) > np.asarray(med))) <= 0.8


@pytest.mark.slow
def test_the_discriminator_does_not_SYSTEMATICALLY_invent_a_sigma_defect_on_skewed_data():
    """The rate half of the same control, at the pre-registered bar rather than at zero.

    ⚠️ The pre-registered acceptance is a RATE (`SIGMA_DEFECT_FP_BAR = 0.05`), not "zero fires on a
    handful of draws" — a correctly-built test statistic MUST fire at its α level, so a
    zero-tolerance assertion over a few seeds would be a test the instrument is designed to fail.
    The bar here is chosen for its BINOMIAL behaviour, not to make these seeds pass: at a true rate
    of 0.05, `P(≥3 of 8) ≈ 0.006`, while a SYSTEMATICALLY broken discriminator (one that reads
    skew as scale) fires at a rate near 1 and lands at 8 of 8. The precise rate on 40 replicates at
    production reps is measured by `control_sweep` and published in the report.
    """
    fires = sum(
        M.run(frame=M.clean_frame(655, np.random.default_rng(20 + s),
                                  shape_alpha=M.SKEW_CONTROL_ALPHA),
              reps=FAST_REPS, with_power=False, with_games_needed=False,
              windows=("FULL",))["verdict"]["verdict"] == "SIGMA_SCALE_DEFECT"
        for s in range(8))
    assert fires <= 2, f"{fires}/8 skewed-but-correctly-scaled frames read as a σ-scale defect"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. ⭐ CLAUSE ISOLATION (NF-D17) — each clause of the AND-composed firing rule must bind ALONE
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _t(*, normal_p=0.0001, shape_outside=True, ci_lo=1.01, ci_hi=1.20, var_z=1.12,
       strat_valid=False):
    """A minimal decision-rule input in which EVERY clause of the firing rule is satisfied.

    Each clause test below flips exactly ONE argument, so the fixture cannot refuse for a second
    reason and the guard cannot pass for the wrong one (NF-D17).
    """
    def nv(p):
        return {"observed": 1.0, "p_two_sided": p, "evaluable": True, "outside_null": p < 0.05,
                "null_median": 1.0, "null_lo": 0.9, "null_hi": 1.1}
    quiet = {k: nv(0.9) for k in ("pit_mdd", "bias", "rms_var_z_sigma", "rms_var_z_mean",
                                  "pit_ks", "cov80", "cov50", "rmse", "crps")}
    return {
        "totals": {"FULL": {
            "stratifiers": {M.PRIMARY_STRATIFIER: {"valid": strat_valid, "spearman_rho": -0.04}},
            "null": {**quiet, "var_z_pooled": nv(normal_p)},
            "shape_matched": {"null": {"var_z_pooled": {"observed": var_z, "evaluable": True,
                                                        "outside_null": shape_outside,
                                                        "p_two_sided": 0.01 if shape_outside
                                                        else 0.30}}},
            "sigma_scale": {"c_hat": float(np.sqrt(var_z)), "ci_lo": ci_lo, "ci_hi": ci_hi,
                            "ci_excludes_one": bool(ci_lo > 1.0 or ci_hi < 1.0),
                            "var_z": var_z, "material": abs(var_z - 1.0) >= M.MATERIAL_VAR_Z_GAP,
                            "material_bar": M.MATERIAL_VAR_Z_GAP,
                            "pct_too_small": 100 * (float(np.sqrt(var_z)) - 1)},
        }},
        "h2h": {"FULL": {"null": {k: nv(0.9) for k in M.VERDICT_STATS_H2H}}},
    }


def test_clause_baseline_all_four_satisfied_fires():
    """The fixture itself must FIRE, or every clause test below is vacuous."""
    assert M._decide(_t())["verdict"] == "SIGMA_SCALE_DEFECT"


def test_clause_normal_null_binds_alone():
    """Only the Normal-null p is moved; shape, CI and materiality all still satisfied."""
    assert M._decide(_t(normal_p=0.60))["verdict"] != "SIGMA_SCALE_DEFECT"


def test_clause_shape_matched_null_binds_alone():
    """⭐ The clause this whole study exists to add. With the Normal null, the CI and the
    materiality bar ALL still satisfied, failing the shape-matched null alone must stop the fire —
    and must land on `SHAPE_ARTIFACT`, its own non-firing label, not on a caveat."""
    v = M._decide(_t(shape_outside=False))
    assert v["verdict"] == "SHAPE_ARTIFACT"
    assert v["phase_2_fires"] is False


def test_clause_bootstrap_ci_binds_alone():
    assert M._decide(_t(ci_lo=0.97, ci_hi=1.19))["verdict"] != "SIGMA_SCALE_DEFECT"


def test_clause_materiality_binds_alone():
    """MH2.5's bar: a σ gap smaller than one coverage point is not a pricing-relevant defect,
    however significant. Everything else here still fires."""
    v = M._decide(_t(var_z=1.02, ci_lo=1.001, ci_hi=1.04))
    assert v["verdict"] == "IMMATERIAL"
    assert v["phase_2_fires"] is False


def test_a_validated_stratifier_readmits_rms_var_z_sigma_to_the_family():
    """The conditional-membership lock, both ways: DISQUALIFIED drops it (and says why),
    VALIDATED keeps it."""
    assert "rms_var_z_sigma" not in M._decide(_t(strat_valid=False))["verdict_family"]["totals"]
    assert M._decide(_t(strat_valid=False))["notes"]
    assert "rms_var_z_sigma" in M._decide(_t(strat_valid=True))["verdict_family"]["totals"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. ⭐ POWER_LIMITED — the pre-registered verdict the first implementation left UNREACHABLE
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_power_limited_is_reachable_and_is_not_reported_as_a_clean_null():
    """RED-PROVABLE: delete the `underpowered` branch from `_decide` and this goes red.

    The pre-registration's decision table has always carried the POWER_LIMITED row; the first cut
    of `_decide` had no branch that could assign it, so every underpowered window would have been
    reported as a clean `WITHIN_NOISE`. A pre-registered verdict with no reachable branch is the
    NF1.7 (a) vacuous class inside the study written to guard against it.
    """
    quiet = _t(normal_p=0.90, shape_outside=False, var_z=1.0055, ci_lo=0.98, ci_hi=1.03)
    v = M._decide(quiet, sigma_mde=1.08)          # observed |ĉ−1| ≈ 0.003 < MDE−1 = 0.08
    assert v["verdict"] == "POWER_LIMITED"
    assert v["underpowered_for_observed_effect"] is True
    assert v["phase_2_fires"] is False


def test_an_effect_larger_than_the_mde_is_a_clean_null_not_power_limited():
    """The other side of the same branch: if the window COULD have found an effect of the observed
    size and did not, that is a genuine null and must not be dressed as under-power."""
    quiet = _t(normal_p=0.90, shape_outside=False, var_z=1.35, ci_lo=0.99, ci_hi=1.30)
    v = M._decide(quiet, sigma_mde=1.05)          # |ĉ−1| ≈ 0.16 > MDE−1 = 0.05
    assert v["verdict"] == "WITHIN_NOISE"
    assert v["underpowered_for_observed_effect"] is False


def test_power_limited_never_masks_a_firing_verdict():
    """Ordering guard: an under-powered-looking window that nonetheless clears every firing clause
    must still FIRE — POWER_LIMITED is a fallback, never a veto."""
    assert M._decide(_t(), sigma_mde=1.50)["verdict"] == "SIGMA_SCALE_DEFECT"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The controls must judge the SAME rule the real run judged (MH2.8)
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
def test_the_windows_knob_is_a_cost_knob_not_a_scope_knob():
    """The control sweep computes the PRIMARY window only, for speed. That is safe ONLY because
    `_decide` reads the primary window alone — if a future edit made the verdict depend on RECENT
    or EARLIER, the controls would silently start measuring a CHEAPER rule than the real run, which
    is exactly MH2.8's negative-control defect. This pins the equivalence."""
    fr = M.clean_frame(655, np.random.default_rng(31), sigma_scale=1.25)
    kw = dict(frame=fr, reps=FAST_REPS, with_power=False, with_games_needed=False, sigma_mde=1.08)
    assert (M.run(**kw, windows=("FULL",))["verdict"]["verdict"]
            == M.run(**kw)["verdict"]["verdict"])


def test_games_needed_is_measured_against_the_bh_threshold_not_an_uncorrected_alpha():
    """The premise MH2.10 tests rests on UNCORRECTED α = 0.05 marks. A `games_needed` computed
    against that same uncorrected bar would reproduce the premise's error inside the remedy."""
    rng = np.random.default_rng(41)
    fr = M.clean_frame(300, rng)
    out = M.games_needed_for_sigma(fr["mu"].values, fr["sigma"].values, 1.10,
                                   reps=60, seed=1, grid=(300,), family_size=5)
    assert out["bh_threshold"] == pytest.approx(M.FDR_Q / 5)
    assert out["bh_threshold"] < M.ALPHA


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Refusals — the harness must refuse rather than report a verdict it could not have contradicted
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_run_refuses_below_the_vacuity_floor():
    """Below the floor a Monte-Carlo p cannot resolve past BH's strictest threshold, so NO input
    could ever be flagged and the verdict would be non-firing BY CONSTRUCTION."""
    fr = M.clean_frame(300, np.random.default_rng(51))
    with pytest.raises(RuntimeError, match="vacuity floor"):
        M.run(frame=fr, reps=M.min_null_reps() - 1, with_power=False, with_games_needed=False)


def test_run_refuses_an_empty_morning_population():
    fr = M.clean_frame(300, np.random.default_rng(52))
    fr["tier"] = M.CONTRAST_TIER
    with pytest.raises(RuntimeError, match="ZERO morning rows"):
        M.run(frame=fr, reps=FAST_REPS, with_power=False, with_games_needed=False)


def test_run_refuses_a_population_whose_declared_deviation_has_grown():
    """MH2.10 narrows MH2.6's population rule to the morning champion, having PROBED that this
    changes nothing. If a foreign stamp ever appears the deviation is no longer a no-op, and the
    harness must say so rather than quietly audit a mixed population."""
    fr = M.clean_frame(300, np.random.default_rng(53))
    fr.loc[fr.index[:3], "model_version"] = "v6"
    with pytest.raises(RuntimeError, match="pre-registered expectation"):
        M.run(frame=fr, reps=FAST_REPS, with_power=False, with_games_needed=False)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. The verdict-inert descriptive block must stay verdict-inert
# ══════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
def test_the_contrast_block_cannot_influence_the_verdict():
    """§6 compares morning against post_lineup. MH2.1 (b) forbids an incumbent-relative anchor, so
    the contrast must be reportable without being readable by the decision rule. Corrupting the
    contrast tier beyond recognition must leave the verdict byte-identical."""
    rng = np.random.default_rng(61)
    m = M.clean_frame(655, rng)
    p = m.copy()
    p["tier"] = M.CONTRAST_TIER
    p["model_version"] = M.CONTRAST_CHAMPION
    base = M.run(frame=pd.concat([m, p], ignore_index=True), reps=FAST_REPS, with_power=False,
                 with_games_needed=False, windows=("FULL",))
    p2 = p.copy()
    p2["sigma"] = p2["sigma"] * 5.0          # an absurd contrast tier
    wrecked = M.run(frame=pd.concat([m, p2], ignore_index=True), reps=FAST_REPS, with_power=False,
                    with_games_needed=False, windows=("FULL",))
    assert base["verdict"] == wrecked["verdict"]
    assert base["contrast"]["sigma_mean_post"] != wrecked["contrast"]["sigma_mean_post"]
    assert wrecked["contrast"]["contracts_nest"] is False
