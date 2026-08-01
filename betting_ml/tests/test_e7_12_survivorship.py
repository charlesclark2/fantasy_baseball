"""E7.12 SLICE 2 — the promotion-selection (survivorship) correction for the MiLB→MLB MLE.

This slice's failure mode is NOT "the correction does nothing". It is "the correction does something,
for the wrong reason, and the number goes up". Three specific ways, one test group each:

  1. **RIGHT-CENSORING masquerading as selection.** 37.3% of the never-MLB population is still active —
     "not promoted YET", not "not promoted". A hazard blind to that learns follow-up time, and IPW then
     up-weights the oldest cohorts. The guard must FIRE on a world where censoring is the only signal
     (an anchor that cannot fail is an anchor that passes on nothing — NF1.7 lesson 1).
  2. **IPW buying representativeness with sample size, silently.** Extreme weights collapse the
     effective n; MAE alone never shows it, so ESS is asserted as part of the output.
  3. **A pre-S2 pairs artifact.** It has no season for un-promoted players, so a leakage-safe or
     censoring-aware model is not even expressible — that must RAISE, not silently degrade.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.survivorship import (
    build_person_seasons,
    censoring_diagnostic,
    cumulative_promotion_probability,
    fit_hazard,
    fixed_horizon_propensity,
    ipw_weights,
    propensity_strata,
    resolve_rate_col,
)


HORIZON = 4          # the fixed promotion window the guard and the propensity both use
LAST_SEASON = 2026    # the calendar edge: nothing after this is observable
EXIT_HAZARD = 0.31    # per-season attrition, set from the live fitted exit intercept σ(-0.8) ≈ 0.31
MAX_CAREER = 8        # nobody hangs around forever


def _pairs(n=400, seed=0, *, censor_recent=False, promote_on_rate=True, entry_hi=None):
    """A synthetic prospect population whose promotion process is SIMULATED SEASON BY SEASON.

    ⚠️ **AN EARLIER VERSION OF THIS GENERATOR PRODUCED TWO BROKEN ANCHORS AND THEY CERTIFIED A GUARD
    THAT DOES NOT WORK.** Both defects are easy to make and neither is visible from a passing test:

      • the "censored" world forced recent entrants to `promoted=False` — o/e of exactly 0.000. That is
        TOTAL truncation; real censoring is PARTIAL (live cohorts run o/e 0.80 / 0.64 / 0.26). A guard
        proven on an unmissable positive is barely proven at all.
      • the "clean" world capped every window at the same calendar edge, so recent entrants were
        truncated there too — **the negative control was not negative**, and the threshold got loosened
        to keep it quiet until it could no longer fire on anything.

    So the generator now runs the actual process: each player draws a per-season promotion hazard and is
    promoted the first season it hits. Censoring then arises the way it does in reality — from the
    CALENDAR EDGE cutting a window short — rather than being stamped on by hand.

    ⚠️ **ATTRITION IS PART OF THE PROCESS, NOT A REFINEMENT.** Each season a player is promoted, LEAVES
    affiliated ball, or continues. On the live substrate the mean at-risk window is 2.05 seasons and 85%
    of the never-promoted are releases, so a generator in which everyone sticks around for the full
    horizon has no competing risk to model and would silently certify a propensity that over-predicts by
    ~2.2× on real data. `EXIT_HAZARD` is set from the fitted live exit intercept (≈ σ(-0.8)).

    `promote_on_rate`: the per-season hazard rises with the minor-league rate (the planted mechanism).
    `censor_recent`:   entrants run right up to the calendar edge, so the newest cohorts are partially
                       observed. When False, entry is bounded so EVERY player gets a full HORIZON window.
    """
    rng = np.random.default_rng(seed)
    hi = entry_hi if entry_hi is not None else (
        LAST_SEASON - 1 if censor_recent else LAST_SEASON - HORIZON + 1)
    first = rng.integers(2015, hi + 1, n)
    rate = np.clip(rng.normal(0.30, 0.06, n), 0.05, 0.60)
    lp = np.full(n, -1.9) + (5.0 * (rate - 0.30) if promote_on_rate else 0.0)
    h = 1.0 / (1.0 + np.exp(-lp))                      # per-season promotion hazard
    e = EXIT_HAZARD                                     # per-season attrition hazard

    debut, last = [], []
    for i in range(n):
        promo_season, exit_season = None, None
        for k in range(MAX_CAREER):
            if rng.random() < h[i]:
                promo_season = first[i] + k
                break
            if rng.random() < e:
                exit_season = first[i] + k
                break
        else:
            exit_season = first[i] + MAX_CAREER - 1
        # the calendar can only show us what happened on or before LAST_SEASON
        if promo_season is not None and promo_season <= LAST_SEASON:
            debut.append(int(promo_season))
            last.append(int(promo_season))
        else:
            debut.append(np.nan)
            end = exit_season if exit_season is not None else first[i] + MAX_CAREER - 1
            last.append(int(min(end, LAST_SEASON)))
    promoted = [not np.isnan(d) for d in debut]
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)],
        "level": rng.choice(["Double-A", "Triple-A"], n),
        "first_minor_season": first, "last_minor_season": last,
        "debut_cohort": debut,
        "_hazard_rate": rate, "age": rng.normal(23.0, 1.6, n),
        "minor_pa": rng.integers(150, 700, n).astype(float),
        "has_mlb_label": promoted,
    })


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The person-season panel — censoring is the whole point
# ══════════════════════════════════════════════════════════════════════════════════════


def test_a_never_promoted_player_is_CENSORED_at_his_last_season_not_marked_as_a_failure():
    """The distinction the slice lives or dies on. A player still active in MiLB has not FAILED to be
    promoted, he has not FINISHED — he must contribute at-risk seasons with `event=0` and then STOP,
    flagged censored, rather than being counted as a permanent negative."""
    pairs = _pairs(300, seed=3, censor_recent=True)
    ps = build_person_seasons(pairs)
    active = pairs[pairs["debut_cohort"].isna() & (pairs["last_minor_season"] == LAST_SEASON)]
    never = active["player_id"].iloc[0]
    rows = ps[ps["player_id"] == never].sort_values("season")
    assert len(rows) >= 1
    assert rows["event"].sum() == 0, "a never-promoted player must contribute NO promotion event"
    assert rows["censored"].iloc[-1] == 1, "…and must be CENSORED at his last observed season"
    assert rows["censored"].iloc[:-1].sum() == 0, "censoring marks the LAST season only"
    assert rows["exited"].sum() == 0, "still playing in the final observed season is NOT an exit"
    assert int(rows["season"].iloc[-1]) == int(pairs.set_index("player_id").loc[never,
                                                                               "last_minor_season"])


def test_leaving_affiliated_ball_is_an_EXIT_not_a_censor_and_the_two_are_never_conflated():
    """⭐ A never-promoted player's last season means one of two completely different things. If he was
    still playing in the final observed season he is CENSORED (unfinished). If he stopped before that, he
    LEFT — a real, observed, terminal event, and the one that happens to **85% of the never-promoted** on
    the live substrate. Collapsing them is what makes the promotion propensity over-predict by ~2.2×."""
    pairs = _pairs(300, seed=5, censor_recent=True)
    ps = build_person_seasons(pairs)
    gone = pairs[pairs["debut_cohort"].isna() & (pairs["last_minor_season"] < LAST_SEASON)]
    pid = gone["player_id"].iloc[0]
    rows = ps[ps["player_id"] == pid].sort_values("season")
    assert rows["exited"].iloc[-1] == 1, "a player who stopped before the calendar edge EXITED"
    assert rows["censored"].sum() == 0, "…and is therefore NOT censored"
    assert rows["event"].sum() == 0

    # and the two flags are mutually exclusive everywhere, not just for this player
    assert int((ps["exited"] & ps["censored"]).sum()) == 0
    assert int((ps["exited"] & ps["event"]).sum()) == 0


def test_a_promoted_player_contributes_at_risk_seasons_then_exactly_one_event():
    pairs = _pairs(60, seed=4)
    ps = build_person_seasons(pairs)
    grad = pairs.loc[pairs["debut_cohort"].notna(), "player_id"].iloc[0]
    rows = ps[ps["player_id"] == grad].sort_values("season")
    assert rows["event"].sum() == 1, "exactly one promotion event"
    assert rows["event"].iloc[-1] == 1, "…in the LAST at-risk season (he leaves the risk set)"
    assert rows["censored"].sum() == 0, "a promoted player is not censored"


def test_a_pre_S2_pairs_artifact_RAISES_rather_than_silently_degrading():
    """A pre-S2 parquet has `debut_cohort` (graduates only) and no MiLB season window, so there is no
    season to anchor a leakage-safe fold on and no way to tell censoring from failure. Silently falling
    back would produce a plausible propensity built on nothing — raise instead."""
    pairs = _pairs(30).drop(columns=["first_minor_season", "last_minor_season"])
    with pytest.raises(KeyError, match="first_minor_season|as-of MiLB window"):
        build_person_seasons(pairs)


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The hazard recovers a planted mechanism — and the censoring guard FIRES
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_hazard_recovers_a_PLANTED_promotion_mechanism():
    """If promotion really is driven by the minor-league rate, the fitted hazard must say so — and the
    resulting propensity must ORDER players by that rate. Without this the IPW arm is weighting by noise
    and no downstream anchor could tell."""
    pairs = _pairs(800, seed=11, promote_on_rate=True)
    ps = build_person_seasons(pairs)
    fit, mu = fit_hazard(ps)
    assert fit.converged and fit.n_events > 0
    i = fit.features.index("minor_rate_z")
    assert fit.coef[1 + i] > 0, ("a planted rate→promotion effect must come back POSITIVE", fit.coef)

    # ⚠️ ordered on the FIXED-HORIZON propensity, not the observed-window one — the latter is
    # outcome-dependent (a promoted player's window ends at his promotion, so his propensity is small),
    # which destroys the ordering it is supposed to express. See the dedicated test below.
    ef, emu = fit_hazard(ps, event_col="exited")
    prop = fixed_horizon_propensity(fit, ps, mu, exit_fit=ef, exit_mu=emu)
    merged = prop.merge(pairs[["player_id", "level", "_hazard_rate"]], on=["player_id", "level"])
    rho = merged["propensity"].corr(merged["_hazard_rate"], method="spearman")
    assert rho > 0.5, ("propensity must order players by the planted driver", rho)


def test_a_NULL_promotion_world_leaves_the_rate_coefficient_at_roughly_zero():
    """The other side of the instrument: with promotion independent of the line, the hazard must not
    manufacture a driver. A propensity model that always finds something makes every IPW arm a lottery."""
    pairs = _pairs(800, seed=13, promote_on_rate=False)
    ps = build_person_seasons(pairs)
    fit, _ = fit_hazard(ps)
    i = fit.features.index("minor_rate_z")
    assert abs(fit.coef[1 + i]) < 0.35, ("no planted effect ⇒ near-zero coefficient", fit.coef)


def _diag(pairs, *, with_exit=True):
    ps = build_person_seasons(pairs)
    fit, mu = fit_hazard(ps)
    ef, emu = fit_hazard(ps, event_col="exited") if with_exit else (None, None)
    return censoring_diagnostic(ps, fit, mu, exit_fit=ef, exit_mu=emu)


@pytest.mark.parametrize("seed", [17, 21, 27, 33])
def test_the_CENSORING_GUARD_FIRES_on_PARTIAL_calendar_censoring(seed, n=6000):
    """🚨 THE LOAD-BEARING ANCHOR — and it is deliberately a PARTIAL-censoring world, not a total one.

    An earlier version of this test forced recent entrants to `promoted=False`, giving an observed/expected
    of exactly 0.000. The guard passed that, and then **stayed silent on live data whose newest cohort
    promotes at a quarter of its expected rate.** Proving detection of an unmissable positive proves
    almost nothing; the regime that actually occurs is partial (live cohorts run o/e 0.47 / 0.29 / 0.08).

    Here recent entrants run up against the calendar edge and are simply observed for fewer seasons —
    exactly how censoring arises in the substrate.

    `n` is set to a cohort size comparable to the live one (~550/cohort vs 1,000–3,700 in the substrate)
    because the guard genuinely has NO POWER on a toy — see the power test below."""
    diag = _diag(_pairs(n, seed=seed, censor_recent=True))
    assert diag["recent_cohorts_are_censoring_contaminated"], (
        "the guard MUST fire on partial calendar censoring, or it is guarding nothing",
        diag["flagged_cohorts"], diag["by_entry_cohort"][-4:])
    assert "RIGHT-CENSORED" in diag["reading"]
    assert diag["pct_incomplete_followup"] > 5.0, diag["pct_incomplete_followup"]


@pytest.mark.parametrize("seed", [0, 3, 7, 11])
def test_the_censoring_guard_does_NOT_fire_on_a_GENUINELY_clean_world(seed):
    """…and it must be quiet otherwise, or it is an alarm nobody can act on.

    ⚠️ The control has to be genuinely clean, which the first version was not: it capped every player's
    window at the same calendar edge, so recent entrants were truncated in the 'clean' world too (92% of
    late entrants never promoted, mean window 3.3 vs 4.3). A threshold tuned to stay quiet on a
    contaminated control is a threshold tuned into uselessness — which is precisely what happened."""
    diag = _diag(_pairs(1200, seed=seed, censor_recent=False))
    assert diag["pct_incomplete_followup"] == 0.0, "the clean control must have FULL follow-up"
    assert not diag["recent_cohorts_are_censoring_contaminated"], (
        diag["flagged_cohorts"], diag["by_entry_cohort"][-4:])


def test_the_guard_NEVER_FALSE_FIRES_and_its_POWER_is_a_STATED_PROPERTY_not_an_assumption():
    """The old statistic was a ratio against a fixed constant, which cannot serve a 36-player synthetic
    cohort and a 1,400-player live cohort at once — the reason it ended up mis-calibrated. A
    Poisson-binomial z is scale-free, but scale-free is NOT the same as all-powerful, and the honest
    thing is to measure the power curve rather than assume it.

    Measured (20 seeds per cell, `censor_recent=True` vs `False`):

        per-cohort n │   36    72   136   272   545
        detected     │   0%   15%   25%   80%  100%
        false-fired  │   0%    0%    0%    0%    0%

    ⇒ **the false-fire rate is 0 at every size — the guard never cries wolf — but below ~150 players per
    cohort it has essentially no power.** The live cohorts are 1,000–3,700, comfortably in the
    fully-powered regime, which is the only reason the guard is worth gating on. If this ever gets
    applied to a thinner population (a single level, a single organisation), that limitation binds and
    the guard's silence must NOT be read as a clean bill of health."""
    small_detect = sum(_diag(_pairs(400, seed=s, censor_recent=True))[
        "recent_cohorts_are_censoring_contaminated"] for s in range(6))
    big_detect = sum(_diag(_pairs(6000, seed=s, censor_recent=True))[
        "recent_cohorts_are_censoring_contaminated"] for s in range(3))
    false_fires = sum(_diag(_pairs(n, seed=s, censor_recent=False))[
        "recent_cohorts_are_censoring_contaminated"] for n in (400, 6000) for s in range(3))

    assert false_fires == 0, "a guard that false-fires on a clean population gets muted and then ignored"
    assert big_detect == 3, ("at live cohort sizes detection must be reliable, not lucky", big_detect)
    assert small_detect == 0, (
        "documents the limitation: at ~36 players per cohort the guard cannot see partial censoring, so "
        "its silence on a thin population means nothing", small_detect)


def test_the_COMPETING_RISK_of_leaving_affiliated_ball_is_what_makes_the_propensity_CALIBRATED():
    """⭐ THE MECHANISM TEST. `P(promoted within k seasons) = 1 - Π(1-h)` silently assumes the player is
    still around to be promoted in all k seasons. Most are not — they are released. Ignoring that makes
    the expectation far too high for EVERY cohort, including the fully-observed ones, so a calibration
    check built on it is measuring its own missing risk rather than censoring.

    Measured on the live substrate: mature-cohort o/e **0.46 without** the exit hazard, **0.94 with** it.
    This test pins the mechanism on synthetic data where the truth is known: adding the competing risk
    must move mature cohorts materially TOWARD 1.0."""
    pairs = _pairs(3000, seed=23, censor_recent=True)
    without = _diag(pairs, with_exit=False)["mature_oe_mean"]
    with_ = _diag(pairs, with_exit=True)["mature_oe_mean"]
    assert without < 0.85, ("without the competing risk the model must OVER-predict promotions", without)
    assert abs(with_ - 1.0) < abs(without - 1.0), (
        "adding the exit hazard must move mature-cohort calibration toward 1.0", without, with_)
    assert 0.80 < with_ < 1.25, ("…and land near it", with_)


def test_the_fixed_horizon_propensity_is_not_OUTCOME_DEPENDENT_unlike_the_observed_window_version():
    """Why `cumulative_promotion_probability` cannot be the calibration baseline: it multiplies over the
    seasons a player was ACTUALLY at risk, and a promoted player's window ENDS at his promotion. So the
    players who were promoted are exactly the ones given a small expected value, and the o/e of a mature
    cohort is inflated for a purely mechanical reason. The fixed-horizon version evaluates every player
    over the same k seasons regardless of what happened to him."""
    pairs = _pairs(1500, seed=29, censor_recent=False)
    ps = build_person_seasons(pairs)
    fit, mu = fit_hazard(ps)
    ef, emu = fit_hazard(ps, event_col="exited")

    obs_window = cumulative_promotion_probability(fit, ps, mu)
    fixed = fixed_horizon_propensity(fit, ps, mu, exit_fit=ef, exit_mu=emu)
    promoted = ps.groupby(["player_id", "level"])["event"].max().rename("promoted").reset_index()
    a = obs_window.merge(promoted, on=["player_id", "level"])
    b = fixed.merge(promoted, on=["player_id", "level"])

    gap_obs = a.loc[a.promoted == 1, "propensity"].mean() - a.loc[a.promoted == 0, "propensity"].mean()
    gap_fix = b.loc[b.promoted == 1, "propensity"].mean() - b.loc[b.promoted == 0, "propensity"].mean()
    assert gap_obs < 0, ("the observed-window propensity is LOWER for the players who were actually "
                         "promoted — the outcome-dependence this slice must not build a check on", gap_obs)
    assert gap_fix > 0, ("the fixed-horizon propensity must be HIGHER for players who were promoted, "
                         "which is what a propensity is supposed to mean", gap_fix)


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. IPW: the weights, and the sample size they silently spend
# ══════════════════════════════════════════════════════════════════════════════════════


def test_ipw_weights_are_normalised_trimmed_and_report_EFFECTIVE_SAMPLE_SIZE():
    """⭐ ESS is part of the RESULT, not a diagnostic. IPW buys population-representativeness by SPENDING
    sample size; an arm whose effective n collapses has traded bias for variance, and MAE alone hides it
    completely."""
    p = pd.Series(np.concatenate([np.full(90, 0.5), np.full(10, 0.001)]))   # 10 extreme rows
    w, audit = ipw_weights(p)
    assert audit["n_propensity_trimmed"] == 10, audit
    assert w.min() >= 0.2 - 1e-12 and w.max() <= 5.0 + 1e-12
    assert abs(float(np.mean(w)) - 1.0) < 0.5, "weights are centred, not rescaling the likelihood"
    assert 0.0 < audit["ess_fraction"] <= 1.0

    flat, flat_audit = ipw_weights(pd.Series(np.full(100, 0.5)))
    np.testing.assert_allclose(flat, 1.0)
    assert flat_audit["ess_fraction"] == pytest.approx(1.0, abs=1e-6), (
        "uniform propensity must cost NO effective sample size")
    assert audit["ess_fraction"] < flat_audit["ess_fraction"], (
        "dispersed weights MUST show up as a lower ESS — that is the whole point of reporting it")


def test_the_propensity_strata_are_non_empty_terciles_ordered_low_to_high():
    """The stratified score is this slice's directional falsification — a real correction must help the
    LOW-propensity graduates (the observable proxy for the un-promoted) and not the high ones. That test
    is impossible if the strata are degenerate."""
    p = pd.Series(np.concatenate([np.full(40, 0.10), np.full(40, 0.30), np.full(40, 0.80)]))
    s = propensity_strata(p)
    assert set(s.dropna().unique()) == {0, 1, 2}
    assert s.value_counts().min() >= 30, s.value_counts().to_dict()
    assert p[s == 0].mean() < p[s == 2].mean(), "stratum 0 must be the LOW-propensity end"


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. `extra_cols` — the Heckman arm's regressor must reach BOTH fit and predict, and must be
#    a byte-exact no-op when unused
# ══════════════════════════════════════════════════════════════════════════════════════


def _fit_frame(n=300, seed=7):
    rng = np.random.default_rng(seed)
    feat = rng.normal(0.32, 0.05, n)
    z = rng.normal(0.0, 1.0, n)
    return pd.DataFrame({
        "feat": feat, "age": rng.normal(23.0, 1.5, n),
        "level": rng.choice(["Double-A", "Triple-A"], n),
        "league": rng.choice(["IL", "PCL", "EL"], n),
        "target": 0.9 * feat + 0.02 * z + rng.normal(0, 0.005, n),
        "z": z, "has_target": True,
    })


def test_extra_cols_is_a_BYTE_EXACT_no_op_when_unused():
    """The discipline every optional knob in this program ships under: OFF must be indistinguishable from
    the code before the knob existed, to the bit — otherwise every downstream slice-1 result silently
    moves and no one can tell an improvement from a refactor."""
    from betting_ml.scripts.milb_mle.milb_mle import PartialPoolProjector

    df = _fit_frame()
    a = PartialPoolProjector(prior_scale=2.0).fit(df)
    b = PartialPoolProjector(prior_scale=2.0, extra_cols=()).fit(df)
    ma, sa = a.predict(df)
    mb, sb = b.predict(df)
    np.testing.assert_array_equal(ma, mb)
    np.testing.assert_array_equal(sa, sb)
    assert a._design(df)[0].shape == b._design(df)[0].shape
    assert "z" not in a.spec_.blocks[0].columns, a.spec_.blocks[0].columns


def test_an_extra_col_reaches_BOTH_fit_AND_predict():
    """🪤 THE FAILURE THIS TEST EXISTS FOR: a new fixed block wired into `fit` but omitted from `predict`
    does not raise — the arm simply serves the incumbent projection under a new name, and the bake-off
    reports a clean null for a mechanism that was never actually applied. (`predict` was a hand-copied
    duplicate of `_design`; it now calls it, and this pins that.)

    Changing ONLY the extra column at predict time must change the prediction."""
    from betting_ml.scripts.milb_mle.milb_mle import PartialPoolProjector

    df = _fit_frame()
    m = PartialPoolProjector(prior_scale=2.0, extra_cols=("z",)).fit(df)
    assert "z" in m.spec_.blocks[0].columns
    assert not m.spec_.blocks[0].penalized, (
        "the selection correction must live in the UNPENALIZED block — shrinking it toward 0 IS the null "
        "the Heckman arm is being tested against")

    base, _ = m.predict(df)
    moved, _ = m.predict(df.assign(z=df["z"] + 1.0))
    assert not np.allclose(base, moved), "predict() ignored the extra column — the arm would be inert"

    # …and it must be USED, not merely present: with a planted z-effect the fit recovers a real coefficient
    plain = PartialPoolProjector(prior_scale=2.0).fit(df)
    mae_plain = float(np.mean(np.abs(plain.predict(df)[0] - df["target"])))
    mae_extra = float(np.mean(np.abs(base - df["target"])))
    assert mae_extra < mae_plain, (mae_plain, mae_extra)


def test_cumulative_promotion_probability_is_one_minus_the_survival_product():
    """`P(promoted) = 1 - prod_s (1 - h_s)` — asserted against a hand-computed value so a refactor that
    quietly switches to a mean-of-hazards (which is NOT the same number) fails here."""
    ps = pd.DataFrame({
        "player_id": ["a", "a", "a", "b"], "level": ["AAA"] * 4,
        "season": [2018, 2019, 2020, 2018], "season_index": [0, 1, 2, 0],
        "event": [0, 0, 1, 0], "censored": [0, 0, 0, 1],
        "minor_rate": [0.3, 0.3, 0.3, 0.2], "age": [22.0, 23.0, 24.0, 25.0],
        "minor_pa": [400.0, 400.0, 400.0, 300.0],
    })
    fit, mu = fit_hazard(ps, l2=10.0)
    out = cumulative_promotion_probability(fit, ps, mu).set_index("player_id")["propensity"]
    from betting_ml.scripts.milb_mle.survivorship import _design

    X, _ = _design(ps, mu)
    h = fit.hazard(X)
    expected_a = 1.0 - np.prod(1.0 - h[:3])
    assert out.loc["a"] == pytest.approx(expected_a, abs=1e-9)
    assert out.loc["b"] == pytest.approx(1.0 - (1.0 - h[3]), abs=1e-9)
    assert out.loc["a"] > out.loc["b"], "three seasons at risk must exceed one, all else equal"
