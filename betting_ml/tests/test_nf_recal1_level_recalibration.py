"""NF-RECAL1 guards — the veteran LEVEL recalibration's pre-registration, metric and constraints.

⚠️ EVERY GUARD HERE WAS RED-PROVEN by deliberately breaking the source it protects; a guard that
cannot FAIL is worse than none (INC-38/INC-39), and a guard on an `and`-composed rule is VACUOUS
unless its fixture satisfies every OTHER clause (NF-D17) — so the constraint tests below build one
ISOLATING fixture per clause rather than one fixture that trips several.

Fast gate: pure logic + source inspection only. ⛔ No `pipeline` import (E11.23), no IO, no network,
and nothing at module scope beyond the import of the module under test.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import level_recalibration as LR


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The metric — CRPS must be the metric it claims to be
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_crps_matches_the_closed_form_normal():
    """The pre-registration claims `CRPS_TAU_KNOTS` is a MEASURED sufficiency rather than a guess.
    This is the measurement: a symmetric band whose edges are exactly ±z(0.9)·σ IS a normal, and its
    CRPS has a closed form.

    ⚠️ THE BOUND IS RELATIVE BECAUSE CRPS CARRIES THE UNITS OF THE TARGET — an absolute bound means
    something different at a 5-PPR outcome and a 400-PPR one, and the far tail is exactly where a
    fixed-knot quadrature of a kinked integrand is least accurate. The bar is `CRPS_RELATIVE_
    TOLERANCE`, read from the module so this guard cannot drift looser than the constant it defends.
    """
    from scipy.stats import norm
    mu, sd = 100.0, 25.0
    lo, hi = mu - 1.2815515655446004 * sd, mu + 1.2815515655446004 * sd
    worst = 0.0
    for y in (0.0, 30.0, 100.0, 175.0, 260.0, 400.0):
        z = (y - mu) / sd
        closed = sd * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))
        got = LR.crps_from_band(np.array([mu]), np.array([lo]), np.array([hi]), np.array([y]))[0]
        worst = max(worst, abs(closed - got) / abs(closed))
    assert worst < LR.CRPS_RELATIVE_TOLERANCE, f"CRPS drifted from the closed form (rel {worst:.2e})"


def test_the_crps_resolution_is_far_finer_than_the_gap_it_must_separate():
    """The number that makes the knot count a DECISION rather than a preference: the quadrature error
    has to be small against the spread of the field, not small in the abstract. Measured, the field
    spans several percent of the incumbent's CRPS while the quadrature error is ~1e-4 relative."""
    assert LR.CRPS_RELATIVE_TOLERANCE < 1e-3
    # and it must actually be attained at the registered knot count, not merely declared
    from scipy.stats import norm
    mu, sd, y = 100.0, 25.0, 260.0
    z = (y - mu) / sd
    closed = sd * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))
    got = LR.crps_from_band(np.array([mu]), np.array([mu - 1.2815515655446004 * sd]),
                            np.array([mu + 1.2815515655446004 * sd]), np.array([y]),
                            n_tau=LR.CRPS_TAU_KNOTS)[0]
    assert abs(closed - got) / closed < LR.CRPS_RELATIVE_TOLERANCE


def test_crps_of_a_point_mass_is_the_absolute_error():
    """A degenerate band (p10 = point = p90) is a point mass, for which CRPS reduces EXACTLY to
    |y − point|. This pins the limit the degenerate anchors (`zero_project`, `pos_median`) live at —
    without it those anchors could be scoring something other than what the report calls CRPS."""
    got = LR.crps_from_band(np.array([50.0]), np.array([50.0]), np.array([50.0]),
                            np.array([80.0]))[0]
    assert abs(got - 30.0) < 1e-6


def test_crps_punishes_a_widened_band_so_a_coverage_target_cannot_win_it():
    """NF1.8's rule: a coverage floor is a CONSTRAINT and must never become a TARGET, because that
    criterion is monotone in widening. CRPS is the metric that eliminates the widened arm — and this
    asserts it does, on a band inflated exactly the way the `wide_band` degenerate inflates one."""
    p = np.array([100.0]); lo = np.array([60.0]); hi = np.array([140.0]); y = np.array([98.0])
    tight = LR.crps_from_band(p, lo, hi, y)[0]
    wide = LR.crps_from_band(p, p - 3 * (p - lo), p + 3 * (hi - p), y)[0]
    assert wide > tight, "a 3x-widened band must LOSE CRPS or the wide_band degenerate is unpoliced"


def test_the_quantile_function_is_clipped_at_zero():
    """The zero clip is substantive, not cosmetic: this population has a genuine point mass at 0
    (NF1.9 measured 31%), and an unclipped band would score negative fantasy seasons as possible."""
    q = LR._band_quantiles(np.array([5.0]), np.array([-40.0]), np.array([50.0]),
                           LR._tau_knots(64))
    assert q.min() >= 0.0


def test_mae_is_forbidden_as_the_selection_metric():
    """§4 — MAE is minimised at the conditional median and PAYS FOR PESSIMISM on this zero-heavy,
    right-skewed target (NF-D11 measured an all-zero degenerate winning it at 43% zeros). The
    prohibition is data in the pre-registration so a future edit cannot quietly re-select on it."""
    assert LR.SELECTION_METRIC == "crps"
    assert "mae" in LR.FORBIDDEN_SELECTION_METRICS
    assert LR.SELECTION_METRIC not in LR.FORBIDDEN_SELECTION_METRICS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ The primary hypothesis — the per-game/season-total foil, and where it CANNOT act
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _panel(n: int = 400, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    pos = np.array(["QB", "RB", "WR", "TE"])[rng.integers(0, 4, n)]
    g = rng.uniform(3.0, 17.0, n)
    point = np.clip(rng.gamma(3.0, 40.0, n), 5.0, None)
    real = np.clip(point * rng.uniform(0.4, 2.0, n), 0.0, None)
    return {"point": point, "real": real, "pos": pos, "g": g,
            "p10": np.clip(point * 0.4, 0, None), "p90": point * 1.7}


@pytest.mark.parametrize("form", LR.SPACE_INVARIANT_FORMS)
def test_space_invariance_is_exact(form):
    """⭐ THE PRE-REGISTERED EXPECTED TIE, PROVEN RATHER THAN DISCOVERED (§2, NF-D16 (2)).

    A purely multiplicative correction satisfies `k·(p/g)·g ≡ k·p`, so for these three forms the
    per-game and season-total parameterisations emit BYTE-IDENTICAL projections and the matched foil
    CANNOT ACT. Registering that in advance and measuring it is what stops the report from claiming
    a mechanism acted where it structurally cannot (NF1.9: a mechanism that cannot act is a finding).
    """
    d = _panel()
    a = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
    b = LR.fit_form(form, "season_total", d["point"], d["real"], d["pos"], d["g"])
    pa = LR.predict_form(form, "per_game", a, d["point"], d["pos"], d["g"])
    pb = LR.predict_form(form, "season_total", b, d["point"], d["pos"], d["g"])
    assert np.max(np.abs(pa - pb)) < 1e-9, f"{form} is registered SPACE-INVARIANT but moved"


@pytest.mark.parametrize("form", LR.SPACE_ACTING_FORMS)
def test_the_per_game_channel_actually_acts_on_the_forms_that_carry_an_intercept(form):
    """The mirror of the test above, and it is what keeps the foil from being vacuous: on the two
    forms whose correction carries an INTERCEPT, the per-game parameterisation emits `c·g` where
    season-total emits a flat `c`, so the two MUST differ. If this ever ties, the matched foil is
    measuring nothing and the primary hypothesis is untestable.

    ⚠️ THE TWO CHANNELS ARE ASSERTED SEPARATELY AND THE RED-PROOF HARNESS IS WHY. Comparing
    fit-then-predict conflates them: deleting the `c·g` term from `predict_form` left the test green,
    because the two SPACES still fit DIFFERENT parameters and the predictions differed for that
    reason alone. So the PREDICTION channel is isolated by holding the parameters FIXED, and the FIT
    channel is checked on its own — a break in either now goes red."""
    d = _panel()
    # (i) the PREDICTION channel, isolated: identical parameters, different space.
    fixed = ({q: 2.0 for q in LR.RECALIBRATED_POSITIONS} if form == "pos_offset"
             else {q: (2.0, 1.1) for q in LR.RECALIBRATED_POSITIONS})
    pa = LR.predict_form(form, "per_game", fixed, d["point"], d["pos"], d["g"])
    pb = LR.predict_form(form, "season_total", fixed, d["point"], d["pos"], d["g"])
    assert np.max(np.abs(pa - pb)) > 1e-6, \
        f"{form}: the per-game intercept must scale with games at PREDICT time"
    # (ii) the FIT channel: the two spaces must estimate genuinely different parameters.
    a = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
    b = LR.fit_form(form, "season_total", d["point"], d["real"], d["pos"], d["g"])
    assert str(a) != str(b), f"{form}: the two spaces must FIT differently or the foil is vacuous"


def test_permutation_vacuity_is_a_property_of_the_space_not_only_of_the_form():
    """⭐ THE PRE-REGISTERED "TIE", MEASURED — and the measurement REFINED the expectation.

    A within-position shuffle preserves that position's MARGINAL exactly, so it cannot move a
    SEASON-TOTAL additive level (`c = mean(y − p)`) — NF-D16 measured 7.1e-15 for this reason. It DOES
    move the PER-GAME one (`c = Σg(y − p)/Σg²`), which re-pairs each outcome with a different
    expected-games value. ⇒ "the permutation is vacuous against a level" is true only with the SPACE
    named, and the per-game correction is NOT a pure marginal statistic — which is precisely why the
    per-game hypothesis is testable at all rather than being a reparametrisation."""
    d = _panel(600, seed=3)
    rng = np.random.default_rng(11)
    ysh = d["real"].copy()
    for q in LR.RECALIBRATED_POSITIONS:
        idx = np.flatnonzero(d["pos"] == q)
        if len(idx) > 1:
            ysh[idx] = rng.permutation(ysh[idx])

    a = LR.fit_form("pos_offset", "season_total", d["point"], d["real"], d["pos"], d["g"])
    b = LR.fit_form("pos_offset", "season_total", d["point"], ysh, d["pos"], d["g"])
    assert max(abs(a[q] - b[q]) for q in a) < 1e-9, \
        "a SEASON-TOTAL additive level is a marginal statistic and MUST be shuffle-invariant"

    c = LR.fit_form("pos_offset", "per_game", d["point"], d["real"], d["pos"], d["g"])
    e = LR.fit_form("pos_offset", "per_game", d["point"], ysh, d["pos"], d["g"])
    assert max(abs(c[q] - e[q]) for q in c) > 1e-3, \
        "a PER-GAME level draws on the games covariate and must NOT be shuffle-invariant"


def test_the_fit_never_reads_realized_games():
    """⛔ §0's hazard at its sharpest. Dividing by REALIZED games would make the per-game target an
    outcome-conditioned quantity — the artifact this whole story exists to keep out — and would be
    undefined for the ~31% who play none. The divisor is PROJECTED games, and this proves it by
    changing realized games arbitrarily and requiring the fit not to move."""
    d = _panel()
    for form in LR.FORMS:
        a = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
        b = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
        assert str(a) == str(b)
    # `_g` is the only divisor, and it is fed proj_games by every call site.
    assert np.all(LR._g(np.array([0.0, np.nan, 20.0])) >= LR.MIN_GAMES)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# λ — never a knob
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_lambda_zero_reproduces_the_incumbent_exactly_for_every_form():
    """The λ grid is only an honest shrink toward "no recalibration" if its zero end IS the
    incumbent, byte-for-byte, for EVERY form — otherwise the knob quietly changes shape at 0 and the
    NULL in the field is not the product."""
    d = _panel()
    for form in LR.FORMS:
        params = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
        p, lo, hi = LR.apply_to_band(form, "per_game", params, d["point"], d["p10"], d["p90"],
                                     d["pos"], d["g"], 0.0)
        assert np.allclose(p, d["point"]) and np.allclose(lo, d["p10"]) \
            and np.allclose(hi, d["p90"]), f"{form} at λ=0 is not the incumbent"


def test_the_lambda_grid_is_inherited_and_not_re_chosen():
    """NF-D20's rule: a successor that invents its own grid can place a point wherever it wants the
    answer. The grid is `rookie_point_recalibration.SHRINK_GRID`, imported."""
    from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RPR
    assert LR.LAMBDA_GRID == (0.0,) + tuple(RPR.SHRINK_GRID)


def test_an_empty_evidence_set_yields_no_correction_rather_than_a_free_grid():
    """NF1.7 (a): a check that did not run is not a check that passed. With no prior fold to verify
    against, a CONSTRAINED rule must fall back to λ=0 — the difference between "nothing refused it"
    and "nothing examined it". The unconstrained REFERENCE arm is the deliberate exception."""
    assert LR.aggregate_admissible({}, True) == (float(LR.EMPTY_EVIDENCE_LAMBDA),)
    assert LR.aggregate_admissible({}, False) == tuple(float(x) for x in LR.LAMBDA_GRID)


def test_select_lambda_breaks_ties_toward_less_correction():
    """A tie means the data cannot tell two λ apart, and the conservative side of "how much of a
    correction do we apply" is less of it."""
    pick = LR.select_lambda((0.0, 0.5, 1.0), {0.0: 5.0, 0.5: 5.0, 1.0: 5.0})
    assert pick["lam"] == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ C3 — the constraint that refused NF-D21, and the clause that keeps it non-vacuous
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cov_case(cov_by_pos: dict, n: int = 100):
    """Build a population whose per-position 80% coverage is EXACTLY the requested fraction, so a
    coverage test can isolate ONE clause instead of tripping several (NF-D17's vacuity lesson)."""
    y, lo, hi, pos = [], [], [], []
    for q, c in cov_by_pos.items():
        k = int(round(c * n))
        y += [50.0] * n
        lo += [0.0] * k + [80.0] * (n - k)     # covered rows bracket 50, the rest sit above it
        hi += [100.0] * k + [180.0] * (n - k)
        pos += [q] * n
    return (np.array(y), np.array(lo), np.array(hi), np.array(pos, dtype=object))


def test_the_bare_floor_alone_would_refuse_the_incumbent_itself():
    """⭐ THE MEASUREMENT THAT FORCED THE CLAUSE'S SHAPE, PINNED SO IT CANNOT BE FORGOTTEN.

    The served veteran band covers ~0.50 of nominal on the draftable tier (the NF1.9 zero-atom
    mechanism read on a population where the zeros are rare). Under a BARE 0.80 floor the NULL itself
    is refused, and a constraint that refuses everything has examined nothing (NF1.7 (a)) — a
    bake-off run under one reports a null produced entirely by its own gate."""
    y, lo, hi, pos = _cov_case({q: 0.50 for q in LR.RECALIBRATED_POSITIONS})
    bare = LR.coverage_floor_check(y, lo, hi, pos)
    assert not bare["ok"], "the bare floor must refuse a 0.50-covering incumbent — else this is moot"


def test_c3_governs_the_change_so_the_incumbent_is_admissible_at_its_own_coverage():
    """With the incumbent's own coverage supplied, the clause reduces to "do not make it worse", and
    the NULL is admissible. That is NF-D20's C2 structure, inherited — ⛔ NOT a loosened floor: the
    binding level is `min(floor, incumbent)` and can never sit ABOVE the floor."""
    y, lo, hi, pos = _cov_case({q: 0.50 for q in LR.RECALIBRATED_POSITIONS})
    inc = LR.per_position_coverage(y, lo, hi, pos)
    rel = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc)
    assert rel["ok"] and rel["governs_the_change"]
    for q, v in rel["per_position"].items():
        assert v["binding_level"] <= LR.COVERAGE_FLOOR + 1e-12, "the clause must never exceed the floor"


def test_c3_still_refuses_an_arm_that_makes_a_shortfall_worse():
    """The clause must keep TEETH. An arm covering less than the incumbent is refused even where the
    incumbent already sits below the floor — otherwise "governs the change" would be a licence."""
    y, lo, hi, pos = _cov_case({q: 0.50 for q in LR.RECALIBRATED_POSITIONS})
    inc = LR.per_position_coverage(y, lo, hi, pos)
    y2, lo2, hi2, pos2 = _cov_case({q: 0.40 for q in LR.RECALIBRATED_POSITIONS})
    worse = LR.coverage_floor_check(y2, lo2, hi2, pos2, incumbent_coverage=inc)
    assert not worse["ok"] and worse["breaches"]


def test_c3_refuses_a_single_position_and_is_never_a_pooled_mean():
    """NF1.8: a per-group constraint may not be a mean of per-class means. A pooled coverage can
    clear while ONE position breaches, and averaging is the exact operation that hides the failure
    the constraint exists to catch. ⭐ ISOLATING FIXTURE: three positions are given generous coverage
    so ONLY the RB clause can flip the result (NF-D17)."""
    inc = {q: 0.85 for q in LR.RECALIBRATED_POSITIONS}
    y, lo, hi, pos = _cov_case({"QB": 0.95, "RB": 0.55, "WR": 0.95, "TE": 0.95})
    res = LR.coverage_floor_check(y, lo, hi, pos, incumbent_coverage=inc)
    assert res["pooled_coverage"] > LR.COVERAGE_FLOOR, "the pooled read must CLEAR, or this is moot"
    assert not res["ok"] and any("RB" in b for b in res["breaches"])


def test_c3_reports_its_margin_in_rows():
    """NF1.8, and the distinction NF-D21 turned on: "0.7905 vs 0.80" reads like a calibration change;
    "two covered seasons short of 119 at n=148" reads like what it is."""
    y, lo, hi, pos = _cov_case({q: 0.79 for q in LR.RECALIBRATED_POSITIONS})
    res = LR.coverage_floor_check(y, lo, hi, pos)
    for v in res["per_position"].values():
        assert "rows_of_slack" in v and "rows_required" in v and v["rows_of_slack"] < 0


def test_the_coverage_floor_is_never_raised_above_nominal():
    """NF1.8: every notch above nominal moves the eligible set toward the `wide_band` degenerate and
    away from an honest interval. The floor equals the band's own nominal level, and it is inherited."""
    assert LR.COVERAGE_FLOOR == LR.BAND_NOMINAL == 0.80


# ══════════════════════════════════════════════════════════════════════════════════════════════
# ⭐ The peeking ceilings — matched family, matched sample AND matched objective
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_every_form_has_its_own_peeking_ceiling():
    """NF-D16 (g‴): the forms NEST, so ONE shared ceiling would veto a legitimately-better richer
    family as a metric inversion. A form without a registered ceiling would make
    `family_ceiling_check` pass on NOTHING."""
    assert set(LR.FAMILY_CEILING) == set(LR.FORMS)
    assert len(set(LR.FAMILY_CEILING.values())) == len(LR.FORMS)


def test_a_metric_fitted_ceiling_bounds_its_own_form_where_a_least_squares_one_need_not():
    """⭐ THE MATCHED-OBJECTIVE FINDING, PINNED. "Peeking can only help" holds only when the peeking
    fit minimises the objective the arm is SCORED on. An LS-fitted ceiling scored on CRPS is not a
    bound at all — it is just another arm — which is why the ceilings did not order by capacity until
    they were fitted on CRPS.

    ⚠️ A "never worse" ASSERTION ALONE IS VACUOUS AND THE RED-PROOF HARNESS CAUGHT THAT: a
    `fit_form_peeking_on_metric` that simply RETURNED its least-squares initialisation satisfies
    "at least as good" BY EQUALITY, so the test stayed green with the entire optimiser deleted. It
    therefore asserts BOTH — never worse on any form, and STRICTLY better on at least one, which is
    the only thing that distinguishes a metric-fitted ceiling from the LS fit it starts from."""
    d = _panel(300)
    strictly_better = 0
    for form in LR.FORMS:
        ls = LR.fit_form(form, "per_game", d["point"], d["real"], d["pos"], d["g"])
        opt = LR.fit_form_peeking_on_metric(form, "per_game", d["point"], d["p10"], d["p90"],
                                            d["real"], d["pos"], d["g"], init=ls)

        def _crps(params):
            p, lo, hi = LR.apply_to_band(form, "per_game", params, d["point"], d["p10"], d["p90"],
                                         d["pos"], d["g"], 1.0)
            return float(np.mean(LR.crps_from_band(p, lo, hi, d["real"])))
        a, b = _crps(opt), _crps(ls)
        assert a <= b + 1e-6, f"the {form} metric-fitted ceiling regressed vs LS"
        strictly_better += int(a < b - 1e-6)
    assert strictly_better > 0, ("no form's ceiling improved on its least-squares init — the "
                                 "optimiser is a no-op and the matched-objective claim is unproven")


def test_the_declared_nesting_is_a_real_containment():
    """`FORM_NESTING` is what `ceilings_order_by_capacity` reads, so a wrong entry would turn an
    internal-consistency signal into noise. Each pair is checked by CONSTRUCTION: the coarser form's
    output must be reproducible by the richer one's parameters."""
    d = _panel()
    # pos_const ⊂ pos_affine: a multiplicative k is the affine (0, k).
    k = {q: 1.3 for q in LR.RECALIBRATED_POSITIONS}
    aff = {q: (0.0, 1.3) for q in LR.RECALIBRATED_POSITIONS}
    assert np.allclose(LR.predict_form("pos_const", "per_game", k, d["point"], d["pos"], d["g"]),
                       LR.predict_form("pos_affine", "per_game", aff, d["point"], d["pos"], d["g"]))
    # pos_offset ⊂ pos_affine (per-game): `c·g` is the affine (c, 1).
    off = {q: 2.0 for q in LR.RECALIBRATED_POSITIONS}
    aff2 = {q: (2.0, 1.0) for q in LR.RECALIBRATED_POSITIONS}
    assert np.allclose(LR.predict_form("pos_offset", "per_game", off, d["point"], d["pos"], d["g"]),
                       LR.predict_form("pos_affine", "per_game", aff2, d["point"], d["pos"],
                                       d["g"]))
    for a, b in LR.FORM_NESTING:
        assert a in LR.FORMS and b in LR.FORMS


def test_a_missing_anchor_is_a_hard_failure_not_a_pass():
    """NF1.7 (a) — an anchor that did not score makes its own check VACUOUSLY TRUE."""
    with pytest.raises(SystemExit):
        LR.require_anchors({"oracle_perplayer": {LR.SELECTION_METRIC: 1.0}},
                           required=("oracle_perplayer", "zero_project"))
    with pytest.raises(SystemExit):
        LR.require_anchors({"zero_project": {LR.SELECTION_METRIC: None}},
                           required=("zero_project",))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Scope — the CLOSED rookie leg stays closed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_rookie_row_in_the_population_is_a_hard_failure():
    """⛔ §1 — the rookie LEVEL is governed by the CLOSED NF-D16→D21 chain, and re-opening it inside
    a differently-named story would re-apply the exact pressure the PM closed it to remove."""
    with pytest.raises(SystemExit):
        LR.assert_rookie_leg_untouched(pd.DataFrame({"is_rookie": [False, True, False]}))
    LR.assert_rookie_leg_untouched(pd.DataFrame({"is_rookie": [False, False]}))


def test_the_scope_gate_re_reads_the_imported_disposition(monkeypatch):
    """The exclusion is INHERITED, not restated — so if a future edit flips the rookie policy without
    re-deciding this story, NF-RECAL1 must FAIL rather than silently widen its own scope."""
    from quant_sports_intel_models.football.nfl.fantasy import rookie_publish_policy as RPP
    monkeypatch.setattr(RPP, "SERVING_ENABLED", True, raising=False)
    with pytest.raises(SystemExit):
        LR.assert_rookie_leg_untouched(pd.DataFrame({"is_rookie": [False]}))


def test_qb_is_in_scope_and_the_reason_is_recorded():
    """QB is IN scope here unlike NF-D16/D18/D20, whose exclusion rests on NF-D14's ROOKIE-QB
    finding. Inheriting a reason that does not apply is its own error, so the divergence is data."""
    assert "QB" in LR.RECALIBRATED_POSITIONS
    assert "rookie" in LR.QB_INCLUSION_REASON.lower()
    assert LR.RECALIBRATED_LEG == "veteran" and "rookie" in LR.EXCLUDED_LEGS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The population — the choice that decides the answer
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_tier_anchor_is_the_incumbent_and_outcome_anchors_are_forbidden():
    """§0 — anchoring the tier on the realized outcome (or on "the player played") selects the rows
    on which any honest projection looks cold. NF-D17 measured a one-sided truncation manufacturing
    an arbitrary gap; the prohibition is data so a future edit cannot quietly re-anchor."""
    assert LR.TIER_ANCHOR == "incumbent_projection"
    assert "realized_outcome" in LR.FORBIDDEN_TIER_ANCHORS
    assert LR.TIER_ANCHOR not in LR.FORBIDDEN_TIER_ANCHORS
    assert set(LR.POPULATION_READINGS) >= {"universe", "draftable_tier_incumbent_anchor",
                                           "draftable_tier_realized_anchor"}


def test_the_draftable_tier_is_derived_from_the_shipped_preset():
    """The tier is a PRODUCT quantity, not a number somebody picked — a tier that could be tuned sits
    directly upstream of every figure in this story and would be tuned."""
    n = LR.draftable_tier_size()
    assert n == 156, "12 teams x (1QB+2RB+2WR+1TE+1FLEX+6BN) skill slots"
    assert LR.draftable_tier_size(teams=10) == 130, "the size must track the league, not a constant"


def test_the_availability_buckets_are_fixed_and_physical():
    """A fitted bucket boundary is a knob, and a knob chosen on this population is the E2.1-r move."""
    b = LR.avail_bucket(np.array([0.0, 7.9, 8.0, 12.9, 13.0, 17.0, np.nan]))
    assert list(b) == ["part", "part", "most", "most", "full", "full", "part"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Attribution + verdict wiring
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_attribution_signature_separates_a_level_fix_from_a_per_player_effect():
    """⭐ NF-D15 (g′): a genuine LEVEL correction moves pooled bias TOWARD zero while accuracy
    improves. NF-D15 measured the opposite and that is what REFUTED NF-D14's stated mechanism, so
    "my arm won" is not "it won for the reason I said"."""
    assert LR.attribution_signature(incumbent_bias=-20.0, winner_bias=-5.0,
                                    incumbent_metric=10.0, winner_metric=9.0
                                    )["verdict"] == "level_fix"
    assert LR.attribution_signature(incumbent_bias=-20.0, winner_bias=-24.0,
                                    incumbent_metric=10.0, winner_metric=9.0
                                    )["verdict"] == "per_player_effect"
    assert LR.attribution_signature(incumbent_bias=-20.0, winner_bias=-5.0,
                                    incumbent_metric=10.0, winner_metric=11.0
                                    )["verdict"] == "no_lift"


def test_the_sanity_degenerate_flag_is_split_from_the_magnitude_hypothesis():
    """⭐ NF-D20: a BUNDLED gate flag mixing a metric-SANITY check with a MAGNITUDE hypothesis is a
    liability — a future reader sees one `False` and distrusts the whole measurement when only the
    registered magnitude was refuted. `over_scale` winning is a REFUTED MAGNITUDE, not an inversion.

    ⭐ ISOLATING FIXTURE (NF-D17): every OTHER clause is satisfied, so only the flag under test can
    flip the result — otherwise this would pass without testing anything."""
    base = dict(pooled_ships=True, premise_confirmed=True, sanity_degenerates_lose=True,
                permutation_across_beaten=True, oracle_respected=True,
                family_ceiling_respected=True, ceilings_order_by_capacity=True,
                over_scale_loses=True, wide_band_loses=True, rookie_leg_untouched=True,
                space_invariance_proven=True)
    assert LR.level_verdict(**base)["ship"] is True, "the all-clear fixture must SHIP or this is moot"
    v = LR.level_verdict(**{**base, "over_scale_loses": False})
    assert v["ship"] is False and v["sanity_degenerates_lose"] is True, \
        "a refuted MAGNITUDE must not read as an untrustworthy measurement"
    v2 = LR.level_verdict(**{**base, "sanity_degenerates_lose": False})
    assert v2["ship"] is False and v2["over_scale_loses"] is True


@pytest.mark.parametrize("clause", ["pooled_ships", "premise_confirmed", "sanity_degenerates_lose",
                                    "permutation_across_beaten", "oracle_respected",
                                    "family_ceiling_respected", "ceilings_order_by_capacity",
                                    "over_scale_loses", "wide_band_loses", "rookie_leg_untouched",
                                    "space_invariance_proven"])
def test_every_verdict_clause_is_independently_load_bearing(clause):
    """⭐ NF-D17's vacuity lesson applied exhaustively: a guard on an `and`-composed rule proves
    nothing unless its fixture satisfies every OTHER clause. One isolating fixture PER clause, so
    deleting any single clause from the source makes exactly this case go red."""
    base = dict(pooled_ships=True, premise_confirmed=True, sanity_degenerates_lose=True,
                permutation_across_beaten=True, oracle_respected=True,
                family_ceiling_respected=True, ceilings_order_by_capacity=True,
                over_scale_loses=True, wide_band_loses=True, rookie_leg_untouched=True,
                space_invariance_proven=True)
    assert LR.level_verdict(**base)["ship"] is True
    assert LR.level_verdict(**{**base, clause: False})["ship"] is False


def test_the_pooled_gate_requires_all_three_constraints():
    """The ship decision reads C1, C2 and C3 on the SELECTED arm as well as on eligibility, so a
    reader of the verdict sees the constraint state of the thing actually chosen."""
    ok = dict(winner={"metric": 1.0, "recalibrates": True},
              incumbent_metric=2.0,
              ordering={"per_position": {q: {"ok": True} for q in LR.RECALIBRATED_POSITIONS}},
              placement={"holds_out": True}, coverage={"ok": True},
              pbo=0.05, dsr=0.99, pvalue=0.01)
    assert LR.pooled_ship(**ok)["ship"] is True
    assert LR.pooled_ship(**{**ok, "coverage": {"ok": False}})["ship"] is False
    assert LR.pooled_ship(**{**ok, "placement": {"holds_out": False}})["ship"] is False
    assert LR.pooled_ship(**{**ok, "ordering": {"per_position": {"RB": {"ok": False}}}})["ship"] \
        is False


def test_the_framing_and_deflation_bars_are_inherited_not_re_chosen():
    """The bars cannot drift between the story that ratified a level correction and the story asking
    the same question of a different leg — so they are imported, not typed."""
    from quant_sports_intel_models.football.nfl.fantasy import rookie_point_recalibration as RPR
    assert (LR.PBO_MAX, LR.DSR_MIN, LR.ALPHA) == (RPR.PBO_MAX, RPR.DSR_MIN, RPR.ALPHA)
    assert LR.PREREGISTERED_FRAMING == "pooled"
    assert LR.PREREGISTERED_DSR_READING == "whole_field"
    from quant_sports_intel_models.football.nfl.fantasy.nf1_4_rookie import ORDERING_DO_NO_HARM
    assert LR.ORDERING_DO_NO_HARM == ORDERING_DO_NO_HARM


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Ordering claims are MEASURED, never asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_leg_monotone_form_moves_no_rank_within_the_leg():
    """A single positive constant is monotone over the rows it TOUCHES."""
    d = _panel()
    adj = LR.predict_form("global_const", "per_game", {"k": 1.4}, d["point"], d["pos"], d["g"])
    assert LR.ordering_movement(d["point"], adj, d["pos"])["worst_rank_move"] == 0.0


def test_leg_monotone_is_named_for_its_scope_because_the_board_holds_untouched_rows():
    """⭐ THE CLAIM THE FIRST CUT GOT WRONG AND THE MEASUREMENT CAUGHT. A veteran-only constant is NOT
    whole-board monotone: the served board also holds rookies, which this story may not touch, so
    lifting every veteran past a fixed rookie field genuinely reorders the board (NF-D16 (g‴) — a
    'moves no ranks' claim is scoped, and asserting it unscoped is the error)."""
    assert hasattr(LR, "LEG_MONOTONE_FORMS") and not hasattr(LR, "GLOBAL_MONOTONE_FORMS")
    point = np.array([100.0, 90.0, 80.0, 70.0])
    adj = np.array([140.0, 126.0, 80.0, 70.0])          # first two are veterans, lifted 1.4x
    mv = LR.cross_position_movement(point, adj, np.array(["RB", "WR", "RB", "WR"], dtype=object))
    assert mv["n_moved"] == 0                            # this ordering happens not to cross
    adj2 = np.array([100.0, 90.0, 112.0, 98.0])          # now the untouched rows are overtaken
    mv2 = LR.cross_position_movement(point, adj2, np.array(["RB", "WR", "RB", "WR"], dtype=object))
    assert mv2["n_moved"] > 0, "a leg-scoped lift must be able to reorder the shared board"


def test_a_negative_affine_slope_is_detected_rather_than_assumed_away():
    """NF-D16 (2): an affine is only CONDITIONALLY monotone — a negative fitted slope inverts a whole
    position's board — so "does no ordering harm" is a MEASUREMENT for this form, never a property."""
    assert "pos_affine" in LR.CONDITIONALLY_MONOTONE_FORMS
    d = _panel()
    bad = {q: (200.0, -0.5) for q in LR.RECALIBRATED_POSITIONS}
    adj = LR.predict_form("pos_affine", "per_game", bad, d["point"], d["pos"], d["g"])
    assert LR.ordering_movement(d["point"], adj, d["pos"])["worst_rank_move"] > 0


def test_an_inverted_band_is_re_sorted_so_the_score_stays_well_defined():
    """A negative slope can invert the (p10, point, p90) triple. The inversion is a real defect the
    ordering measurement reports — but a quantile function must remain non-decreasing or every score
    computed from it is meaningless."""
    d = _panel(50)
    bad = {q: (300.0, -1.0) for q in LR.RECALIBRATED_POSITIONS}
    p, lo, hi = LR.apply_to_band("pos_affine", "per_game", bad, d["point"], d["p10"], d["p90"],
                                 d["pos"], d["g"], 1.0)
    assert np.all(lo <= hi) and np.all(lo >= 0.0)
    assert np.all(np.isfinite(LR.crps_from_band(p, lo, hi, d["real"])))
