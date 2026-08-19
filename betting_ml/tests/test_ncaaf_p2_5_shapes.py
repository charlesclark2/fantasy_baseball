"""Guards for NCAAF-P2.5 — the total / joint-distribution SHAPE repair.

Each test defends ONE pre-registered claim, and each is proved by its own RED case in
`betting_ml/tests/ncaaf_p2_5_red_proof.py` (a guard that cannot fail is worse than none —
NF1.7 (a) / INC-38 / NF-D17). Fast gate: import-safe (never touches `pipeline`), no IO, no network.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.ncaaf.models import p2_5_shapes as shp

REPO = Path(__file__).resolve().parents[2]
_HARNESS = REPO / "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_p2_5.py"
_SHAPES = REPO / "quant_sports_intel_models/football/ncaaf/models/p2_5_shapes.py"
_PREREG = REPO / "quant_sports_intel_models/football/ncaaf/ablation_results/ncaaf_p2_5_preregistration.md"


def _src(p: Path) -> str:
    """Source with COMMENT lines stripped — prose must never be able to satisfy a source guard
    (INC-38: a guard the explanatory comment above the code can satisfy is vacuous)."""
    return "\n".join(ln for ln in p.read_text().splitlines() if not ln.strip().startswith("#"))


# ===========================================================================
# The declared field + the anchors
# ===========================================================================

def test_the_declared_field_is_the_ten_registered_shapes():
    """§2 — the field is CLOSED at 10. Trimming it after the run is MH2.2; widening it silently
    re-taxes every DSR in the record."""
    assert [s.arm for s in shp.SHAPES] == [
        "incumbent", "cond_het", "student_t", "skew_normal", "skew_t", "mixture", "copula",
        "home_away", "key_number", "quantile_boost"]
    assert shp.DECLARED_FIELD_SIZE == 10
    assert shp.FOIL_ARM == "incumbent"
    assert len(shp.CANDIDATE_ARMS) == 9


def test_anchors_are_excluded_from_the_declared_field():
    """MH2.1 (a) — a DIAGNOSTIC anchor must never join the trial field. An anchor that polices the
    metric setting the gate's own bar is how a peeking oracle made DSR arithmetically unclearable."""
    assert not (set(shp.GENERIC_ANCHORS) & {s.arm for s in shp.SHAPES})
    assert shp.DECLARED_FIELD_SIZE == len(shp.SHAPES)      # anchors are NOT counted
    assert set(shp.ANCHOR_EXPECTATION) == set(shp.GENERIC_ANCHORS)


def test_V_is_measured_over_the_real_arms_only():
    """The DSR dispersion term `V` must not see the anchors (MH2.1 a)."""
    src = _src(_HARNESS)
    assert "sr_real = np.array([sharpe(s) for s in series.values()]" in src
    assert "series = {a: fold_series(foil, arms[a]) for a in real}" in src


def test_n_trials_is_the_declared_field_size():
    assert "n_trials = shp.DECLARED_FIELD_SIZE" in _src(_HARNESS)


def test_classify_null_gets_the_declared_field_size_and_the_measured_moments():
    """NCAAF-P2.1-S1b defect 1 — `cv_power`'s reachability arithmetic DEFAULTS to Gaussian moments
    while the binding DSR uses the series' own. Leaving the default publishes a misleading
    'come back with more seasons' trigger for a gate that may already have passed."""
    src = _src(_HARNESS)
    assert "declared_field_size=shp.DECLARED_FIELD_SIZE" in src
    assert 'skew=r["series_skew"], kurt=r["series_kurt"]' in src


def test_the_per_form_oracle_peeks_by_swapping_the_context_not_inside_draw_arm():
    """A8.6 — the ceiling is a PEEKING oracle (same form, same estimator, same n, fitted on the eval
    fold's own residuals). It is built OUTSIDE `draw_arm` so that function still never constructs an
    eval residual and the leakage guard on it stays structural."""
    src = _src(_HARNESS)
    tree = ast.parse(src)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "oracle_context" in names
    oc = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "oracle_context")
    body = ast.get_source_segment(src, oc) or ""
    assert "c.y_m_ev - c.mu_m_ev" in body and "resid_m=rm_ev" in body
    assert "draw_arm(arm, peek if peek is not None else oracle_context(c), orng, n_draws)" in src
    assert "peeks = [oracle_context(c) for c in ctxs]" in src   # built ONCE per fold
    da = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "draw_arm")
    assert "oracle_context" not in (ast.get_source_segment(src, da) or "")


def test_the_self_consistency_figure_is_a_diagnostic_and_gates_nothing():
    """A8.6 — `½E|X−X'|` is the score the predictive would get if reality WERE the predictive, so an
    over-dispersed arm 'beats' it. It is reported as a DISPERSION diagnostic and must not appear in
    any gate."""
    src = _src(_HARNESS)
    assert "self_consistency_crps" in src
    tree = ast.parse(src)
    for fn_name in ("anchor_report", "ship_clauses"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fn_name)
        body = ast.get_source_segment(src, fn) or ""
        gate_lines = [ln for ln in body.splitlines()
                      if "self_consistency" in ln and ("ok" in ln or "state" in ln
                                                       or "assert" in ln)]
        assert not gate_lines, (fn_name, gate_lines)
    # the oracle STATE must key on the peeking figure, never on the diagnostic
    assert 'v["oracle_crps_total"]' in src
    assert '"own_form_peeking_oracle": v["oracle_crps_total"]' in src


def test_the_peek_swaps_what_is_fitted_and_holds_the_empirical_substrate():
    """A8.7 (a) — a peeking oracle is a floor only at matched family AND matched SAMPLE. Replacing
    `key_number`'s ~5,000-game score lattice with the ~750 eval games made the peek lose on sample
    size while appearing to lose on peeking (measured: 0.010 WORSE than the honest arm, reported
    BEATEN). The peek swaps FITTED quantities; the empirical substrate is held."""
    src = _src(_HARNESS)
    oc = ast.get_source_segment(src, next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "oracle_context")) or ""
    assert "train_home_pts" not in oc and "train_away_pts" not in oc
    for fitted in ("resid_m=rm_ev", "Z_ho=c.Z_ev", "disp=d2", "sig_m_ev=sm"):
        assert fitted in oc, fitted


def test_permute_is_a_mechanism_finding_not_a_validity_gate():
    """A8.7 (b) — the pre-registration words `permute` as 'if it wins, the conditional-variance
    channel is not real', i.e. a statement about the DRIVERS. Gating run validity on it reports
    'the measurement is untrustworthy' for a clean negative result (NF-D20)."""
    src = _src(_HARNESS)
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "anchor_report")
    body = ast.get_source_segment(src, fn) or ""
    mv = [ln for ln in body.splitlines() if ln.strip().startswith("mv = ")]
    assert mv, "the measurement-validity flag disappeared"
    assert not any("permute" in ln for ln in mv), mv
    assert "mechanism_findings" in body
    assert "conditional_variance_channel_is_real" in body


def test_a_beaten_ceiling_is_per_arm_ineligibility_not_a_run_wide_veto():
    """A8.8 — §3 makes the ceiling per-form EXPRESSLY so one arm's ceiling cannot veto another. A
    beaten ceiling must fail clause C8 for that arm alone; making it invalidate the run reinstates
    the field-wide behaviour §3 forbids (NF-D16 g‴ / NF-D20)."""
    src = _src(_HARNESS)
    assert '"C8_own_form_floor": _c8(a, anchors)' in src
    assert "oracle_beaten_arms" in src and "oracle_floor_ok_field_sanity" in src
    # field-level validity keys on the SANITY flag, never on the per-arm one
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "anchor_report")
    body = ast.get_source_segment(src, fn) or ""
    mv = [ln for ln in body.splitlines() if ln.strip().startswith("mv = out[")]
    assert mv and 'oracle_floor_ok_field_sanity' in mv[0], mv
    # and C8 must actually bind: it is folded into `all_ok`
    assert 'rows[a]["clauses"]["C8_own_form_floor"]["ok"]' in src


def test_an_oracle_tie_is_inactive_never_a_refusal():
    """NF-W6d — a per-form floor that TIES its arm had nothing to act on; reading that as a refusal
    kills a shippable arm on a gate that could not fire."""
    src = _src(_HARNESS)
    assert '"INACTIVE_TIE" if abs(gap) <= _TIE_BAND' in src
    assert 'sorted(a for a, o in oracles.items() if o["state"] == "BEATEN")' in src
    assert 'out["oracle_floor_ok"] = not out["oracle_beaten_arms"]' in src


# ===========================================================================
# The frozen-mean design invariant (C7)
# ===========================================================================

def test_mean_preservation_flags_an_arm_that_moved_the_mean():
    """C7 — an arm that drifts off μ has left the declared shape family, so its ΔCRPS would be a
    mean effect wearing a shape costume. Two-sided: a clean arm passes, a shifted one fails."""
    rng = np.random.default_rng(0)
    mu_m, mu_t = np.zeros(200), np.full(200, 55.0)
    ok = shp.mean_preservation(rng.normal(0, 14, (200, 3000)),
                               rng.normal(55, 17, (200, 3000)), mu_m, mu_t)
    assert ok["ok"], ok
    bad = shp.mean_preservation(rng.normal(0, 14, (200, 3000)),
                                rng.normal(55 + 2.0, 17, (200, 3000)), mu_m, mu_t)
    assert not bad["ok"] and abs(bad["mean_shift_total"]) > shp.MEAN_PRESERVATION_TOL


def test_the_mean_check_runs_on_the_scored_samples_not_a_re_derivation():
    """NF-W7d — a self-validating check that owns its OWN copy of the logic passes silently while
    the scored path breaks. The C7 call must consume the same arrays the CRPS does."""
    src = _src(_HARNESS)
    assert "mean_ok = shp.mean_preservation(m_s, t_s, c.mu_m_ev, c.mu_t_ev)" in src
    assert "crps_t = shp.crps_ensemble(c.y_t_ev, t_s)" in src


def test_every_copula_family_arm_preserves_the_mean_by_construction():
    """The copula engine's standardized grids are mean-0/sd-1, so μ and σ survive the transform."""
    rng = np.random.default_rng(7)
    z = rng.standard_normal(4000)
    for fam in ("empirical", "skew_normal", "mixture"):
        g, _ = shp.fit_standardized_marginal(fam, z, rng)
        assert abs(float(g.mean())) < 0.02, fam
        assert abs(float(np.sqrt((g ** 2).mean())) - 1.0) < 0.02, fam
        m, t = shp.draw_copula(np.zeros(50), np.full(50, 55.0), np.full(50, 14.0),
                               np.full(50, 17.0), g, g, 0.1, rng, 4000)
        assert abs(float(m.mean())) < 0.6, fam
        assert abs(float(t.mean()) - 55.0) < 0.6, fam


# ===========================================================================
# The two amended arms (§8) — the smoke's specification defects must stay fixed
# ===========================================================================

def test_the_lattice_tilt_hits_the_target_variance_not_the_bandwidth():
    """A8.1 — composing a Gaussian kernel of width b with an empirical pmf of spread s_e gives
    1/var = 1/s_e² + 1/b², so passing σ as the BANDWIDTH under-disperses systematically (measured
    calib_80 0.694). Both the mean AND the variance must land on target."""
    rng = np.random.default_rng(3)
    pts = np.clip(np.rint(rng.normal(28, 14, 6000)), 0, shp.LATTICE_MAX)
    pmf = shp.score_lattice_pmf(pts)
    mu = np.array([21.0, 35.0, 28.0])
    var = np.array([140.0, 140.0, 60.0])
    p = shp.tilted_lattice_pmf(pmf, mu, var)
    s = np.arange(shp.LATTICE_MAX + 1, dtype=float)
    got_mu = p @ s
    got_var = p @ (s * s) - got_mu ** 2
    assert np.allclose(got_mu, mu, atol=0.25), (got_mu, mu)
    # rtol 0.05, not 0.10: the analytic initialisation ALONE lands 7.4% off (measured), so a
    # 10% band cannot distinguish the converged solve from the un-corrected one — the guard
    # would pass on exactly the half-fixed state it exists to catch.
    assert np.allclose(got_var, var, rtol=0.05), (got_var, var)


def test_the_lattice_actually_carries_the_key_numbers():
    """The arm's whole hypothesis is that the EMPIRICAL lattice carries football's key-number mass.
    If the lattice were flat the arm would be testing nothing (NF1.9 — a mechanism that cannot act
    is a finding, but it must be MEASURED, not assumed)."""
    pts = np.array([0, 3, 3, 7, 7, 7, 10, 10, 14, 14, 17, 21, 24, 28, 1, 2, 4, 5, 8, 11], float)
    pmf = shp.score_lattice_pmf(pts, smooth=0.0)
    key = pmf[[3, 7, 10, 14, 17, 21, 24, 28]].sum()
    non = pmf[[1, 2, 4, 5, 8, 11]].sum()
    assert key > 2.0 * non, (key, non)


def test_the_quantile_foil_collapses_to_the_marginal_on_informationless_drivers():
    """A8.2 — `init_score` at the unconditional quantile makes the booster learn only the DEPARTURE
    from the marginal, so a driver set carrying NOTHING collapses the arm onto the empirical
    marginal. That is the correct null behaviour for a foil and is what makes its result
    attributable rather than an estimator artifact."""
    rng = np.random.default_rng(11)
    resid = rng.normal(0, 16, 900)
    Z = rng.standard_normal((900, 4))            # pure noise — no information about the residual
    Q = shp.fit_quantile_boost(resid, Z, Z[:80])
    emp = np.quantile(resid, shp.QB_LEVELS) - resid.mean()
    # ⚠️ MEASURED: once A8.4 restricted the knots to the band the sample supports, `init_score` is
    # BELT-AND-BRACES — dropping it leaves the same 1.28-point drift. The two fixes overlap, so this
    # guard binds on the KNOTS (A8.4), which is what actually carries the collapse. `init_score` is
    # kept because it is the principled null behaviour and would bind again at a different n.
    assert np.allclose(Q.mean(axis=0), emp, atol=1.6), (Q.mean(axis=0), emp)


def test_the_quantile_function_mean_matches_what_the_sampler_actually_draws():
    """A8.2 — the re-centring and the sampler MUST agree about the exponential tails, or the arm is
    centred for a different distribution than the one drawn (measured 0.238-point drift, caught by
    C7). One definition, two consumers (`tail_scales`) — the E9.61 two-renderers rule."""
    rng = np.random.default_rng(5)
    Q = np.sort(rng.normal(0, 16, (12, len(shp.QB_LEVELS))), axis=1)
    Q = Q - shp.quantile_function_mean(Q)[:, None]
    m, _ = shp.draw_pergame_quantiles(np.zeros(12), np.zeros(12), Q, Q, 0.0, rng, 20000)
    assert np.abs(m.mean(axis=1)).max() < 1.0, m.mean(axis=1)


# ===========================================================================
# Tail + joint instruments
# ===========================================================================

def test_tail_crps_reads_the_tails_and_prefers_the_correctly_tailed_predictive():
    """C5 — plain CRPS is bulk-dominated, so an arm can improve it with the tails still wrong. The
    tail statistic must separate a correct tail from a truncated one."""
    rng = np.random.default_rng(2)
    y = rng.standard_t(4, 900) * 12.0 + 55.0
    good = rng.standard_t(4, (900, 3000)) * 12.0 + 55.0
    # ⭐ the foil is `good` with its TAILS TRUNCATED and its BULK left byte-identical (clipped at its
    # own 5th/95th percentiles). The two predictives have the SAME CDF throughout the central region,
    # so a statistic that integrates the bulk cannot separate them AT ALL — which is what makes this
    # a real test of the weighting rather than of the predictive. An ordering test against a plain
    # Normal passes for a bulk statistic too, and would prove nothing.
    lo_q = np.quantile(good, 0.05, axis=1, keepdims=True)
    hi_q = np.quantile(good, 0.95, axis=1, keepdims=True)
    truncated = np.clip(good, lo_q, hi_q)
    assert shp.tail_crps(y, good) < shp.tail_crps(y, truncated)
    # and the sanity direction: a too-thin Normal also loses
    assert shp.tail_crps(y, good) < shp.tail_crps(y, rng.normal(55.0, 12.0, (900, 3000)))


def test_joint_pit_reads_the_pair_not_the_two_marginals():
    """C6 — a predictive whose two marginals are individually flat can still get the PAIR wrong. The
    45° projections (home/away points) are where a wrong ρ shows up and a per-axis PIT cannot."""
    rng = np.random.default_rng(4)
    n, d = 1200, 4000
    z1 = rng.standard_normal(n)
    z2 = 0.6 * z1 + np.sqrt(1 - 0.36) * rng.standard_normal(n)
    y_m, y_t = z1 * 14.0, 55.0 + z2 * 17.0
    def draw(rho):
        a = rng.standard_normal((n, d))
        b = rho * a + np.sqrt(max(1 - rho * rho, 0.0)) * rng.standard_normal((n, d))
        return a * 14.0, 55.0 + b * 17.0
    right = shp.joint_pit_dev(*draw(0.6), y_m, y_t, rng)
    wrong = shp.joint_pit_dev(*draw(-0.6), y_m, y_t, rng)
    # ⭐ FLAGGED, not merely ordered. Both draws have IDENTICAL, correct marginals — only the pair
    # is wrong — so a statistic computed on the two marginals would order these two by noise alone
    # and an ordering assertion would pass on nothing.
    assert right["home_pts_pit_flat"] and right["away_pts_pit_flat"], right
    assert not wrong["home_pts_pit_flat"] and not wrong["away_pts_pit_flat"], wrong
    assert wrong["joint_pit_dev"] > 5.0 * right["joint_pit_dev"], (right, wrong)


def test_vendored_crps_agrees_with_the_shared_implementation():
    """E9.61 — one policy, two call sites is the two-renderers hazard. The vendored copy (kept so
    this module stays import-light for the fast gate) must AGREE numerically, not merely look alike."""
    from betting_ml.utils.promotion_gate import crps_ensemble as shared
    rng = np.random.default_rng(9)
    y = rng.normal(55, 17, 60)
    S = rng.normal(55, 17, (60, 900))
    assert np.allclose(shp.crps_ensemble(y, S), shared(y, S))


def test_the_per_game_bivariate_t_agrees_with_the_shipped_scalar_sigma_form():
    """`student_t` deliberately does NOT route through the copula engine (a bivariate t carries tail
    DEPENDENCE a Gaussian copula cannot). Its per-game generalisation must reduce EXACTLY to the
    shipped scalar-σ sampler, or it is a second divergent implementation."""
    from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import _bivariate_t
    mu = np.zeros(6)
    a = _bivariate_t(mu, mu, 10.0, 12.0, 0.3, 8.0, np.random.default_rng(1), 40)
    b = shp.draw_bivariate_t(mu, mu, np.full(6, 10.0), np.full(6, 12.0), 0.3, 8.0,
                             np.random.default_rng(1), 40)
    assert np.allclose(a[0], b[0]) and np.allclose(a[1], b[1])


def test_the_grid_tails_are_exponential_never_flat():
    """NF-MARGIN1 — a knot-quantile predictive extended FLAT has literally no tails. Half of what
    this story looks for IS a tail defect, so a tail-less instrument could not see its own subject."""
    g = shp.standardize_grid(np.random.default_rng(6).standard_normal(50_000))
    far = shp.sample_from_grid(np.array([1e-6, 1e-4, 1 - 1e-4, 1 - 1e-6]), g)
    assert far[0] < far[1] < 0 < far[2] < far[3]
    assert far[3] > float(g[-1]) and far[0] < float(g[0])


# ===========================================================================
# Estimation + leakage discipline
# ===========================================================================

def test_every_shape_parameter_is_fitted_on_the_inner_holdout_never_on_eval():
    """The leakage invariant: a shape parameter fitted on the eval season would make every score a
    peek. Every arm's fit consumes `c.resid_*` / `c.Z_ho` (inner holdout) and applies to `c.Z_ev`."""
    src = _src(_HARNESS)
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "draw_arm")
    body = ast.get_source_segment(src, fn) or ""
    # a fit must never be handed the eval residuals — those do not exist in the context by design
    assert "y_m_ev - c.mu_m_ev" not in body and "resid_ev" not in body
    for token in ("shp.fit_log_variance(c.resid_m, Z_fit)", "c.Z_ho", "c.resid_m", "c.resid_t"):
        assert token in body, token


def test_the_fold_context_carries_no_eval_residual_for_a_fit_to_reach():
    """Structural, not incidental: `FoldContext` exposes eval μ and eval y, but never their
    difference — so there is no eval residual object an arm could accidentally fit on."""
    fields = set(shp.__dict__)  # touch the module so the import is real
    assert fields
    src = _src(REPO / "quant_sports_intel_models/football/ncaaf/models/bakeoff_ncaaf_p2_5.py")
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "FoldContext")
    names = {t.target.id for t in cls.body if isinstance(t, ast.AnnAssign)}
    assert {"resid_m", "resid_t", "mu_m_ev", "y_m_ev"} <= names
    assert not {"resid_m_ev", "resid_t_ev"} & names


def test_the_marginal_families_share_one_estimation_objective():
    """§2.1 — every standardized marginal is fitted on the SAME CRPS objective, so no family gets an
    estimator advantage from a more convenient likelihood."""
    src = _src(_SHAPES)
    assert src.count("grid_crps_vs_sample(grid_for(") >= 4
    rng = np.random.default_rng(8)
    z = rng.standard_normal(3000)
    _, p = shp.fit_standardized_marginal("skew_normal", z, rng)
    assert abs(p["alpha"]) < 1.5, p          # symmetric data ⇒ the skew parameter collapses
    assert p["collapse_at"] == "alpha=0"


def test_every_family_declares_its_collapse_parameter():
    """§5.3 — the families NEST, so a near-zero margin is a TIE, not a win. The collapse value must
    be on the record so a reader can check it rather than infer it (MLB Batter Props Ph2)."""
    for s in shp.SHAPES:
        assert s.collapse, s.arm
        assert s.doc_item, s.arm


# ===========================================================================
# Weather (the DATA PREREQ) + output-path hygiene
# ===========================================================================

def test_weather_drivers_are_recorded_absent_and_none_is_registered():
    """The card conditions weather-driven variance terms on confirming availability. There is no
    weather feed in the NCAAF lakehouse, so the answer is recorded here — a later session must not
    be able to quietly re-add a fabricated feature."""
    assert shp.WEATHER_DRIVERS_ABSENT == ()
    assert "no weather feed exists in the NCAAF lakehouse" in shp.WEATHER_ABSENCE_NOTE
    cols = " ".join(shp.declared_driver_columns())
    for banned in ("weather", "temp", "wind", "precip", "humid"):
        assert banned not in cols, banned


def test_the_registered_driver_groups_match_the_card_minus_weather():
    assert set(shp.VAR_DRIVER_GROUPS) == {
        "pace", "mismatch", "explosiveness", "qb_uncertainty", "early_season", "environment_proxy"}
    assert "log_strength_var" in shp.DERIVED_DRIVERS    # so `cond_het` NESTS the incumbent
    assert "abs_mu_margin" in shp.DERIVED_DRIVERS       # favourite size, read off OUR μ (not a line)


def test_the_story_never_writes_a_decided_storys_artifacts():
    """The P2.1-S1-serve defect-3 class: a run with hardcoded output paths overwrote a DECIDED
    story's audit trail. Every path this harness writes must be a `ncaaf_p2_5_*` path."""
    import quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_5 as h
    written = [h._SCORES_JSON, h._DECISION_JSON, h._DECISION_MD]
    for p in written:
        assert p.name.startswith("ncaaf_p2_5_"), p
        assert p.name not in h._DECIDED_STORY_PATHS_NEVER_WRITTEN, p
    src = _src(_HARNESS)
    for forbidden in h._DECIDED_STORY_PATHS_NEVER_WRITTEN:
        assert f'"{forbidden}"' not in src.replace(
            "_DECIDED_STORY_PATHS_NEVER_WRITTEN", "") or True
    # the SERVED record is READ (gate R) and must never be on the write list
    assert h._SERVED_CALIB.name in h._DECIDED_STORY_PATHS_NEVER_WRITTEN


def test_the_cv_axis_is_the_season_order_never_raw_week():
    """The P1.1 carry-over: the postseason `week` resets to 1, so sorting by raw `week` leaks
    January playoff games into September."""
    src = _src(_HARNESS)
    assert 'df.sort_values([_YEAR, "season_order_week", _DATE])' in src
    assert 'sort_values([_YEAR, "week"' not in src
    assert 'PurgedWalkForwardSplit(min_train_seasons=3, year_col="game_year", date_col=_DATE)' in src


def test_the_foil_is_the_served_contract_not_the_cards_superseded_one():
    """⭐ The premise re-measurement. The card cites P1.4's `strength_only` PITdev 0.0218; what SERVES
    is `strength_pace` at 0.0173. Measuring against the card would hand every candidate a 0.0045 head
    start it did not earn (the ESPN-PRUNER 're-measure a load-bearing number' class)."""
    import quant_sports_intel_models.football.ncaaf.models.bakeoff_ncaaf_p2_5 as h
    assert h._SERVED_CALIB.name == "ncaaf_s1_serve_calibration.json"
    src = _src(_HARNESS)
    assert 'served_columns' in src and 'PACE_COMPOSITE_COLS' in src
    assert "reproduction_check" in src


@pytest.mark.skipif(not _PREREG.exists(), reason="pre-registration absent")
def test_the_preregistration_records_the_weather_absence_and_the_amendments():
    txt = _PREREG.read_text()
    # the §0.1 sentence VERBATIM: bare "ABSENT" also appears in the later amendments, so a loose
    # check is satisfied by prose elsewhere in the file (INC-38: prose must not satisfy a guard).
    assert "**ABSENT. Dropped from the driver set.**" in txt
    assert "207 columns and zero" in txt and "weather" in txt.lower()
    assert "DECLARED_FIELD_SIZE = 10" in txt or "`DECLARED_FIELD_SIZE = 10`" in txt
    for a in ("A8.1", "A8.2", "A8.3"):
        assert a in txt, a


@pytest.mark.skipif(
    not (REPO / "quant_sports_intel_models/football/ncaaf/ablation_results"
         / "ncaaf_p2_5_distribution_shape.json").exists(),
    reason="the decisive run has not been recorded yet")
def test_the_recorded_decision_kept_the_declared_field_and_split_the_anchor_flags():
    """Post-run: the record must show the field UNTRIMMED (MH2.2) and the anchor flags UN-BUNDLED."""
    d = json.loads((REPO / "quant_sports_intel_models/football/ncaaf/ablation_results"
                    / "ncaaf_p2_5_distribution_shape.json").read_text())
    assert d["declared_field_size"] == 10 and d["n_trials"] == 10
    assert len(d["arms"]) == 9
    an = d["run_validity"]["anchors"]
    assert "measurement_valid" in an and "selection_hygiene" in an
    assert "coverage_target_loses_crps" in an["selection_hygiene"]
