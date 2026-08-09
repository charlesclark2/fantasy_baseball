"""Guards for MH2.5's per-game σ recalibration harness.

Every test here targets ONE clause and is RED-provable on its own. That discipline is the NF-D17
lesson: a guard on an `and`-composed rule is VACUOUS unless its fixture satisfies every OTHER
clause, because a second clause will refuse the fixture and the guard stays green when the clause it
names is deleted. So the ship-rule tests below build a fixture in which only the clause under test
can flip the answer.

Fast-gate safe: imports `betting_ml` only, never `pipeline` (the E11.23 rule), and fits nothing that
needs the training matrix.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

import numpy as np
import pytest

from betting_ml.scripts import mh2_5_sigma_recalibration as M


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. THE METHOD LOCK — the stratifier validation must be able to FAIL, and must fail correctly
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _resid_with_dispersion(strat, rng, *, slope):
    """Residuals whose SD rises with `strat` at the given slope (slope=0 ⇒ homoscedastic)."""
    sd = 4.0 + slope * (np.asarray(strat, float) - np.mean(strat))
    return rng.normal(0.0, np.maximum(sd, 0.5))


def test_a_partition_that_separates_dispersion_is_admitted():
    rng = np.random.default_rng(0)
    strat = rng.uniform(3.0, 6.0, 20_000)
    v = M.realized_dispersion_table(strat, _resid_with_dispersion(strat, rng, slope=1.0))
    assert v["valid"] is True
    assert v["spearman_rho"] >= M.STRATIFIER_MIN_RHO
    assert v["endpoint_separation_se"] >= M.STRATIFIER_MIN_ENDPOINT_SE


def test_a_partition_that_does_NOT_separate_dispersion_is_DISQUALIFIED():
    """The load-bearing half. MH2.1 was rolled back for reading Var(z) off exactly this case."""
    rng = np.random.default_rng(1)
    strat = rng.uniform(3.0, 6.0, 20_000)
    v = M.realized_dispersion_table(strat, _resid_with_dispersion(strat, rng, slope=0.0))
    assert v["valid"] is False
    assert "DISQUALIFIED" in v["reason"]


def test_the_validation_publishes_the_per_bin_table_and_its_SE_even_when_it_fails():
    """A validation that fails silently is no better than none — the table is the deliverable."""
    rng = np.random.default_rng(2)
    strat = rng.uniform(3.0, 6.0, 5_000)
    v = M.realized_dispersion_table(strat, _resid_with_dispersion(strat, rng, slope=0.0))
    assert v["valid"] is False
    assert len(v["bins"]) == M.N_STRATA
    for b in v["bins"]:
        assert b["realized_sd_se"] > 0 and b["n"] > 0
        assert pytest.approx(b["realized_sd"] / np.sqrt(2 * b["n"]), rel=1e-9) == b["realized_sd_se"]


def test_a_rank_valued_stratifier_reports_no_range_ratio():
    """A rank partition runs 0→1 by construction, so its range ratio would read ×19 — nonsense."""
    rng = np.random.default_rng(3)
    ranks = (np.arange(10_000) + 0.5) / 10_000
    v = M.realized_dispersion_table(ranks, _resid_with_dispersion(ranks, rng, slope=3.0))
    assert v["stratifier_is_rank_valued"] is True
    assert not np.isfinite(v["stratifier_range_ratio"])


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. THE METRIC — anchored on the ANALYTIC truth, two-sided, and with a known noise floor
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_metric_is_anchored_on_var_z_equals_one_not_on_any_arm():
    """A well-calibrated z scores ~0; a UNIFORMLY mis-scaled one scores its true deviation.

    An incumbent-relative rule would score the second case 0 whenever the incumbent were equally
    wrong — which is the inversion MH2.1 (b) names.
    """
    rng = np.random.default_rng(4)
    z = rng.normal(size=40_000)
    lab = M._bin_labels(rng.uniform(size=40_000))
    good, _ = M.rms_var_z(z, lab)
    bad, _ = M.rms_var_z(z * np.sqrt(1.5), lab)
    assert good < 0.05
    assert bad == pytest.approx(0.5, abs=0.05)


@pytest.mark.parametrize("k", [M.DEGENERATE_K, 1.0 / M.DEGENERATE_K])
def test_both_degenerates_LOSE_the_primary_metric(k):
    """Two-sided: a criterion a degenerate WINS is fatal (NF1.8 (3)), so both must lose."""
    rng = np.random.default_rng(5)
    sigma = rng.uniform(3.5, 5.5, 40_000)
    y = rng.normal(0.0, sigma)
    lab = M._bin_labels(sigma)
    honest, _ = M.rms_var_z(y / sigma, lab)
    degenerate, _ = M.rms_var_z(y / (sigma * k), lab)
    assert degenerate > honest


def test_the_max_width_degenerate_also_loses_the_SECONDARY_interval_score():
    """A coverage TARGET is monotone in widening and `max_width` wins it; Winkler must not be."""
    rng = np.random.default_rng(6)
    sigma = rng.uniform(3.5, 5.5, 40_000)
    y = rng.normal(0.0, sigma)
    zq = 1.2815515655446004
    honest = M.winkler_score(y, -zq * sigma, zq * sigma).mean()
    wide = M.winkler_score(y, -zq * sigma * 3.0, zq * sigma * 3.0).mean()
    assert wide > honest


def test_the_noise_floor_matches_the_analytic_expectation():
    """RMS |Var(z)−1| is positive even for a PERFECT model; the floor says how positive."""
    rng = np.random.default_rng(7)
    m = 200
    assert M.metric_noise_floor([m] * 10) == pytest.approx(np.sqrt(2.0 / (m - 1)), rel=1e-12)
    z = rng.normal(size=m * 10)
    lab = np.repeat(np.arange(10), m).astype(float)
    observed, _ = M.rms_var_z(z, lab)
    assert observed == pytest.approx(M.metric_noise_floor([m] * 10), rel=0.6)


def test_the_construction_floor_is_calibrated_by_construction():
    """`oracle_bin` must give Var(z)≈1 in every bin — that is why it can gate an inversion."""
    rng = np.random.default_rng(8)
    strat = rng.uniform(3.0, 6.0, 30_000)
    resid = _resid_with_dispersion(strat, rng, slope=1.0)
    sigma = M.oracle_bin_sigma(strat, resid)
    rms, bins = M.rms_var_z(resid / sigma, M._bin_labels(strat))
    assert rms < 0.05
    assert all(abs(b["var_z"] - 1.0) < 0.12 for b in bins)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. THE PREMISE TEST — the widener must be ABLE to widen, or "γ̂ < 1 in 8/8" proves nothing
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_widener_recovers_a_TRUE_widening_when_one_exists():
    """⭐ The guard that makes MH2.5's headline a finding rather than a broken optimizer.

    The study's decisive number is that the fitted γ̂ landed BELOW 1 in every fold — i.e. the
    widener chose to NARROW. That is only evidence if the same code returns γ > 1 when the data
    genuinely want widening. Here the true σ is `σ̄·(s/σ̄)^2`, so the fit must recover γ ≈ 2.
    """
    rng = np.random.default_rng(9)
    s = rng.uniform(3.0, 6.0, 60_000)
    sbar = float(np.mean(s))
    true_sigma = sbar * (s / sbar) ** 2.0
    resid = rng.normal(0.0, true_sigma)
    p = M.fit_power(s, resid)
    assert p["gamma"] == pytest.approx(2.0, abs=0.2)
    assert p["gamma"] > 1.0


def test_the_widener_recovers_a_TRUE_narrowing_too():
    """The mirror — the family is genuinely two-sided over its registered bounds."""
    rng = np.random.default_rng(10)
    s = rng.uniform(3.0, 6.0, 60_000)
    sbar = float(np.mean(s))
    resid = rng.normal(0.0, np.full(len(s), sbar))          # truly homoscedastic ⇒ γ = 0
    p = M.fit_power(s, resid)
    assert p["gamma"] < 0.25


def test_gamma_one_reproduces_the_incumbent_sigma_so_the_family_really_nests_it():
    s = np.linspace(3.0, 6.0, 500)
    out = M.apply_power(s, {"gamma": 1.0, "a": 1.0, "sigma_bar": float(np.mean(s))})
    assert np.allclose(out, s)


def test_gamma_zero_reproduces_the_flat_null_so_the_family_nests_that_too():
    s = np.linspace(3.0, 6.0, 500)
    sbar = float(np.mean(s))
    out = M.apply_power(s, {"gamma": 0.0, "a": 1.0, "sigma_bar": sbar})
    assert np.allclose(out, sbar)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. ATTRIBUTION — the level fix, and the matched foil that separates LEVEL from SHAPE
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_level_fix_sets_mean_squared_z_to_one_on_its_fit_rows():
    rng = np.random.default_rng(11)
    sigma = rng.uniform(3.0, 6.0, 20_000)
    resid = rng.normal(0.0, sigma * 1.3)                    # σ is 30% too small
    fixed = M._level_fix(sigma, resid, sigma)
    assert float(np.mean((resid / fixed) ** 2)) == pytest.approx(1.0, abs=1e-9)
    assert float(np.mean(fixed / sigma)) == pytest.approx(1.3, abs=0.05)


def test_the_matched_foil_is_in_the_field_and_the_ship_rule_names_it():
    """Without `level_only`, a candidate could win purely by fixing the LEVEL (NF-D15 g′)."""
    assert M.MH25_MATCHED_FOIL in M.MH25_FIELD
    src = inspect.getsource(M._decide)
    assert "beats_matched_foil_materially" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. THE FIELD — declared, and diagnostic anchors are never trials
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_diagnostic_anchors_are_excluded_from_the_trial_field():
    """MH2.1 (a): an anchor left in the DSR field SETS the bar of the gate it exists to police."""
    assert set(M.MH25_FIELD).isdisjoint(M.MH25_DIAGNOSTICS)
    assert len(M.MH25_FIELD) == len(set(M.MH25_FIELD))


def test_the_field_is_the_declared_union_of_anchors_and_candidates():
    assert set(M.MH25_FIELD) == set(M.MH25_ANCHORS) | set(M.MH25_CANDIDATES)
    for name in (M.MH25_INCUMBENT_ARM, M.MH25_MATCHED_FOIL, M.MH25_FLAT_NULL, *M.MH25_DEGENERATES):
        assert name in M.MH25_ANCHORS


def test_every_candidate_has_its_OWN_form_peeking_arm():
    """NF-D16 (g‴): the forms NEST, so a single ceiling would veto a better nested form."""
    assert set(M.MH25_PER_FORM_CEILING) == set(M.MH25_CANDIDATES)
    assert set(M.MH25_PER_FORM_CEILING.values()) <= set(M.MH25_DIAGNOSTICS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. THE SHIP RULE — one isolating fixture per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════

def _passing_run(**over):
    """A synthetic run in which EVERY ship clause passes. Each test breaks exactly one.

    Built so that a clause's guard cannot pass because some OTHER clause already refused the
    fixture — the NF-D17 vacuity trap.
    """
    folds = 8
    rng = np.random.default_rng(12)
    # POOLED means — these drive every ship clause that reads a leaderboard.
    base = {"incumbent": 0.40, "level_only": 0.35, "flat_sigma": 0.38,
            "over_disperse": 0.90, "under_disperse": 1.10, "power_widen": 0.30,
            "iso_widen": 0.31, "var_glm": 0.05, "var_glm_plus_sigma": 0.29}
    # ⭐ The PER-FOLD series is deliberately DECOUPLED from those means, and the reason is this
    # study's own finding: `SR0 = √V·z(N)` scales with the cross-trial Sharpe DISPERSION, so a
    # fixture in which the degenerates lose by a large and CONSISTENT amount makes DSR unclearable
    # for a purely ARITHMETIC reason — which is exactly what happened on the real run. A control
    # fixture that could not clear DSR would make every clause test below vacuous, so here each arm
    # carries the same modest, similar per-fold skill and the leaderboard is pinned separately.
    fold_base = {a: (0.40 if a == "incumbent" else 0.30) for a in M.MH25_FIELD}
    fs = {a: list(v + rng.normal(0, 0.02, folds)) for a, v in fold_base.items()}
    for a in M.MH25_DIAGNOSTICS:                      # diagnostics are scored but never trials
        fs.setdefault(a, [0.02] * folds)
    pooled_arm = {a: {"rms_abs_var_z_minus_1": float(base.get(a, 0.02)),
                      "bins": [{"n": 1400}] * 10,
                      "pooled_var_z": 1.0, "coverage": 0.80, "winkler": 15.0, "crps": 2.5,
                      "pit_ks": 0.03, "mean_sigma": 4.5, "sigma_cv": 0.1,
                      "sigma_p90_over_p10": 1.2}
                  for a in list(M.MH25_FIELD) + list(M.MH25_DIAGNOSTICS)}
    pooled_arm["oracle_bin"]["rms_abs_var_z_minus_1"] = 0.01     # the construction floor
    for c in M.MH25_CANDIDATES:
        pooled_arm[M.MH25_PER_FORM_CEILING[c]]["rms_abs_var_z_minus_1"] = 0.02
    pooled_arm["_noise_floor"] = 0.03
    R = dict(
        seasons=list(range(2016, 2027)), exclude_seasons=(), folds=folds, n_rows=20000,
        n_eval_rows=14000, contract_cols=["a"], fold_meta=[], design_bar={},
        stratifiers={"incumbent_sigma": {"valid": True, "reason": "ok"}},
        primary_ok=True, pooled={"incumbent_sigma": pooled_arm}, own_sigma={},
        per_fold_validation=[], premise={}, divergence={}, repro={},
        fold_scores_by_strat={"incumbent_sigma": fs},
        fold_winkler_by_strat={"incumbent_sigma": {a: [15.0] * folds for a in fs}},
        gen_gap={}, seed=42, smoke=False, n_arms=len(M.MH25_FIELD), contract_coverage={},
    )
    R.update(over)
    return R


def _decide(R):
    from betting_ml.scripts.e7_9_train_serve_consistency import dsr_gate
    return M._decide(R, dsr_gate)


def test_the_control_fixture_actually_ships():
    """If this fails, every clause test below is vacuous — they would pass for the wrong reason."""
    r = _decide(_passing_run())
    assert r["verdict"] == "SHIP_RECALIBRATION", r.get("gates")


def test_a_DISQUALIFIED_primary_partition_blocks_a_ship_that_would_otherwise_pass():
    """⭐ The method lock as a HARD gate. Only `primary_ok` differs from the shipping fixture."""
    r = _decide(_passing_run(
        primary_ok=False,
        stratifiers={"incumbent_sigma": {"valid": False, "reason": "DISQUALIFIED for the test"}}))
    assert r["binding"] is False
    assert r["verdict"] != "SHIP_RECALIBRATION"


def test_an_arm_beating_the_CONSTRUCTION_floor_HALTs_as_a_metric_inversion():
    R = _passing_run()
    R["pooled"]["incumbent_sigma"]["oracle_bin"]["rms_abs_var_z_minus_1"] = 0.9
    r = _decide(R)
    assert r["verdict"] == "METRIC_INVERTED_HALT"
    assert r["anchors"]["arms_beating_the_construction_floor"]


def test_a_leader_that_only_beats_the_LEVEL_and_not_the_SHAPE_does_not_ship():
    """The matched-foil clause, isolated: the leader still clears the incumbent by a mile."""
    R = _passing_run()
    R["pooled"]["incumbent_sigma"]["level_only"]["rms_abs_var_z_minus_1"] = 0.055
    r = _decide(R)
    assert r["gates"]["beats_incumbent_materially"] is True      # the OTHER clause still passes
    assert r["gates"]["beats_matched_foil_materially"] is False
    assert r["verdict"] == "INCUMBENT_STANDS"


def test_a_leader_that_loses_to_the_FLAT_NULL_does_not_ship():
    R = _passing_run()
    R["pooled"]["incumbent_sigma"][M.MH25_FLAT_NULL]["rms_abs_var_z_minus_1"] = 0.03
    r = _decide(R)
    assert r["gates"]["beats_flat_null"] is False
    assert r["verdict"] == "INCUMBENT_STANDS"


@pytest.mark.parametrize("degenerate", M.MH25_DEGENERATES)
def test_a_leader_that_loses_to_EITHER_degenerate_does_not_ship(degenerate):
    R = _passing_run()
    # 0.03 sits BELOW the leader (0.05) and ABOVE the construction floor (0.01): if it were below
    # the floor the inversion HALT would fire first and this clause would never be reached — the
    # NF-D17 vacuity trap, seen here in its "a different clause answers first" form.
    R["pooled"]["incumbent_sigma"][degenerate]["rms_abs_var_z_minus_1"] = 0.03
    r = _decide(R)
    assert r["gates"]["beats_both_degenerates"] is False
    assert r["verdict"] == "INCUMBENT_STANDS"


def test_a_sub_meaningful_gain_over_the_incumbent_does_not_ship():
    """The E2.1-r/NF1.8 materiality clause, isolated — significance is not materiality."""
    R = _passing_run()
    P = R["pooled"]["incumbent_sigma"]
    P["incumbent"]["rms_abs_var_z_minus_1"] = (P["var_glm"]["rms_abs_var_z_minus_1"]
                                               + 0.5 * M.MH25_MEANINGFUL_RMS_GAIN)
    r = _decide(R)
    assert r["gates"]["beats_incumbent_materially"] is False
    assert r["verdict"] == "INCUMBENT_STANDS"


def test_a_degraded_coverage_FLOOR_blocks_a_ship():
    R = _passing_run()
    R["pooled"]["incumbent_sigma"]["var_glm"]["coverage"] = 0.60
    r = _decide(R)
    assert r["gates"]["coverage_floor_respected"] is False
    assert r["verdict"] == "INCUMBENT_STANDS"


def test_a_null_reports_the_deflation_sensitivity_but_never_applies_it():
    """MH2.2: the sensitivity exists to EXPLAIN a failure, never to launder one."""
    R = _passing_run()
    R["pooled"]["incumbent_sigma"][M.MH25_FLAT_NULL]["rms_abs_var_z_minus_1"] = 0.03
    r = _decide(R)
    assert r["verdict"] == "INCUMBENT_STANDS"
    sens = r["gates"]["deflation_sensitivity"]
    assert sens["binding"] is False
    assert "dsr_excluding_designed_losers" in sens


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. REPRODUCIBILITY — NGBoost's base learner is unseeded; the harness must seed the global RNG
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_the_global_rng_is_seeded_before_every_ngboost_fit():
    """`NGBRegressor(random_state=...)` does NOT seed its base `DecisionTreeRegressor`.

    Source-inspected via the AST rather than a text match, so an explanatory COMMENT naming
    `np.random.seed` cannot satisfy the guard (the INC-38 prose-cannot-satisfy lesson).
    """
    tree = ast.parse(pathlib.Path(inspect.getfile(M)).read_text())
    fits, seeds = [], []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", getattr(node.func, "id", ""))
        if name == "NGBoostSpec":
            fits.append(node.lineno)
        if name == "seed" and getattr(getattr(node.func, "value", None), "attr", "") == "random":
            seeds.append(node.lineno)
    assert fits, "no NGBoost construction found — the guard would be vacuous"
    assert seeds, "np.random.seed is never called; NGBoost's base learner is left unseeded"
    for f in fits:
        assert any(0 < f - s <= 6 for s in seeds), (
            f"the NGBoost construction at line {f} is not immediately preceded by np.random.seed")


def test_the_base_learner_is_the_only_unseeded_rng_consumer_in_the_fit_path():
    """Pins the ENABLING CONDITION rather than a re-derived mechanism.

    ⚠️ Deliberately NOT an end-to-end repro. The instability is real and was measured on the REAL
    training matrix (two identical-spec fits, per-game σ differing by up to 0.30 on 1,440 games;
    identical once the global RNG is seeded — see `mh2_5_sigma_recalibration.md` §0b). But it does
    NOT reproduce on synthetic data: fits on Gaussian, on tie-rich integer, and on
    constant-indicator fixtures all came back byte-identical. So a synthetic CI repro would be a
    test that passes for the wrong reason, and asserting a mechanism we cannot demonstrate would be
    worse than asserting none.

    What IS checkable, and what this pins: within `ngboost` 0.5.x's fit path every other RNG use
    goes through `check_random_state(self.random_state)`, so the default base learner's
    `random_state=None` is the one consumer left on numpy's global RNG. If that changes upstream,
    this test fails and the global-seed guard should be re-justified rather than silently kept.
    """
    from ngboost import NGBRegressor

    assert getattr(NGBRegressor(random_state=42).Base, "random_state", "missing") is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. POSTURE
# ══════════════════════════════════════════════════════════════════════════════════════════════

def test_best_alpha_is_zero_and_the_harness_refuses_to_pull():
    assert M.BEST_ALPHA == 0
    src = inspect.getsource(M.run)
    assert "refresh_cache=False" in src, "the harness must never refresh the cache (Snowflake-free)"
    assert "raise SystemExit" in src, "an absent cache must HALT, never trigger a pull"


def test_the_window_and_control_match_MH2_1_so_the_studies_are_comparable():
    from betting_ml.scripts.e7_9_train_serve_consistency import (
        MH21_MIN_YEAR, MH21_SENSITIVITY_EXCLUDE,
    )
    assert M.MH25_MIN_YEAR == MH21_MIN_YEAR
    assert M.MH25_SENSITIVITY_EXCLUDE == MH21_SENSITIVITY_EXCLUDE
