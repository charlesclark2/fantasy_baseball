"""Guards for NCAAF-VAL3 — the cold-start μ_total correction.

Fast-gate: source inspection + pure-function checks over synthetic frames. ⛔ Nothing here imports
`pipeline` or touches IO (the E11.23 rule), and nothing reads the on-disk artifacts, so the suite
runs in a fresh worktree with no cache.

⭐ Every clause is written to be ISOLABLE (NF-D17): a fixture that trips two clauses at once proves
neither, so each test moves exactly one quantity and `ncaaf_val3_red_proof.py` RED-proves each by
deleting that clause's own source.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3_cold_start_mu as V3

_SRC_PATH = Path(V3.__file__)


def _src_no_comments() -> str:
    """The module's source with comments and docstrings STRIPPED.

    ⭐ Load-bearing: this module's comments quote the defects it defends against almost verbatim
    (`close_total`, `reset_index`, "market"), so a plain text scan would match the PROSE explaining
    the fix and pass on a file whose CODE had been gutted (the INC-38 prose-cannot-satisfy class).
    """
    return ast.unparse(ast.parse(_SRC_PATH.read_text()))


# ── the field is CLOSED, and its shape is the pre-registration's ───────────────────────────────

def test_the_field_is_closed_and_matches_the_preregistration():
    names = [a.name for a in V3.ARMS]
    assert names == ["none", "bucket_shift", "per_week_shift", "linear_decay", "shrunk_bucket",
                     "pooled_level", "week_blind", "over_scale", "oracle_bucket",
                     "matched_n_bucket"], "the pre-registered field was edited"
    assert V3.FOIL_ARM == "none"
    assert V3.CANDIDATES == ("bucket_shift", "per_week_shift", "linear_decay", "shrunk_bucket")
    assert V3.LOSERS == ("pooled_level", "week_blind", "over_scale")
    assert V3.DIAGNOSTICS == ("oracle_bucket", "matched_n_bucket")


def test_declared_field_size_counts_the_searched_arms_and_excludes_the_diagnostics():
    """MH2.1 (a) — a diagnostic ANCHOR is never a trial. It must not enter `n_trials`, or the
    instrument that exists to POLICE the metric sets the gate's own bar."""
    assert V3.DECLARED_FIELD_SIZE == 1 + len(V3.CANDIDATES) + len(V3.LOSERS) == 8
    assert V3.DECLARED_FIELD_SIZE == len(V3.ARMS) - len(V3.DIAGNOSTICS)


def test_every_registered_loser_is_ineligible_to_ship():
    """NF-D20 — a registered-to-lose arm is SCORED (so a refuted magnitude hypothesis is
    obtainable) but can never be selected. `_ships` gates on the ROLE, not on a name list."""
    body = inspect.getsource(V3.stage_decide)
    assert 'spec.role == "candidate"' in body
    assert "survivors = [a for a in CANDIDATES if _ships(a)]" in body


# ── C4: the estimator may not see the market ───────────────────────────────────────────────────

def test_the_estimator_frame_contract_excludes_every_market_column():
    assert V3.ESTIMATOR_COLUMNS == (V3.WEEK_COL, "season", "mu_total", "y_total", "model_err")
    assert "close_total" not in V3.ESTIMATOR_COLUMNS
    assert "close_home_spread" not in V3.ESTIMATOR_COLUMNS


def test_a_market_column_on_the_estimator_frame_HALTS():
    """VAL2 §9's ⛔: sizing off `μ − close` instead of `μ − y` under-corrects by ~46 % in wk1-3,
    and it would arrive silently as an extra column rather than as an error."""
    good = pd.DataFrame({V3.WEEK_COL: [1], "season": [2020], "mu_total": [50.0],
                         "y_total": [48.0], "model_err": [2.0]})
    V3.assert_estimator_is_market_blind(good)           # the two-sided half: a clean frame passes
    bad = good.assign(close_total=49.0)
    with pytest.raises(SystemExit, match="market"):
        V3.assert_estimator_is_market_blind(bad)


def test_an_unexpected_non_market_column_also_HALTS():
    """The column list is a CONTRACT, not a denylist — a future edit that joins something in to
    'sanity check' the magnitude must fail here rather than silently re-size the correction."""
    frame = pd.DataFrame({V3.WEEK_COL: [1], "season": [2020], "mu_total": [50.0],
                          "y_total": [48.0], "model_err": [2.0], "surprise": [1.0]})
    with pytest.raises(SystemExit, match="unexpected columns"):
        V3.assert_estimator_is_market_blind(frame)


def test_the_peek_source_is_also_market_blind_checked():
    """The peeking anchor is the one place eval-fold information is legitimately handed in, so it
    is exactly where a market column would be least conspicuous."""
    body = inspect.getsource(V3._eval_source)
    assert "assert_estimator_is_market_blind" in body


# ── the CRPS instrument ────────────────────────────────────────────────────────────────────────

def test_the_closed_form_crps_matches_the_ensemble_identity():
    """One policy, two call sites is the E9.61 two-renderers hazard — so the guard asserts the two
    AGREE numerically rather than trusting either."""
    rng = np.random.default_rng(0)
    n = 400
    mu = rng.normal(50, 5, n)
    sig = rng.uniform(12, 20, n)
    y = mu + sig * rng.standard_normal(n)
    closed = float(np.mean(V3.gaussian_crps(y, mu, sig)))
    sampled = V3.crps_sampled_control(y, mu, sig, n_draws=20_000, seed=1)
    assert abs(closed - sampled) < 0.05 * closed / 5, (closed, sampled)


def test_gaussian_crps_is_minimised_at_the_true_mean():
    """The selection metric must be PROPER on this predictive: a shift AWAY from the conditional
    mean has to cost, in BOTH directions. A metric a pessimism arm could win cannot select a level
    correction (NF-D11)."""
    rng = np.random.default_rng(7)
    n = 20_000
    sig = np.full(n, 16.0)
    y = 50.0 + sig * rng.standard_normal(n)
    at_truth = float(np.mean(V3.gaussian_crps(y, np.full(n, 50.0), sig)))
    for shift in (-3.0, -1.0, 1.0, 3.0):
        assert float(np.mean(V3.gaussian_crps(y, np.full(n, 50.0 + shift), sig))) > at_truth


def test_a_non_positive_sigma_HALTS_rather_than_scoring():
    with pytest.raises(SystemExit, match="non-positive"):
        V3.gaussian_crps(np.array([1.0]), np.array([0.0]), np.array([0.0]))


def test_the_analytic_pit_of_a_correct_gaussian_is_flat():
    rng = np.random.default_rng(3)
    n = 60_000
    mu, sig = np.full(n, 50.0), np.full(n, 16.0)
    y = mu + sig * rng.standard_normal(n)
    assert V3.pit_dev(V3.analytic_pit(y, mu, sig))["max_decile_dev"] < 0.01


def test_calib_80_of_a_correct_gaussian_lands_on_nominal():
    rng = np.random.default_rng(4)
    n = 60_000
    mu, sig = np.full(n, 50.0), np.full(n, 16.0)
    y = mu + sig * rng.standard_normal(n)
    assert abs(V3.calib_80(y, mu, sig) - 0.80) < 0.01


# ── the estimator forms ────────────────────────────────────────────────────────────────────────

def _src(err_by_week: dict[int, float], n_per: int = 200, late_err: float = 0.0) -> pd.DataFrame:
    rows = []
    for w, e in err_by_week.items():
        rows.append(pd.DataFrame({V3.WEEK_COL: w, "season": 2020, "mu_total": 50.0,
                                  "y_total": 50.0 - e, "model_err": e, }, index=range(n_per)))
    rows.append(pd.DataFrame({V3.WEEK_COL: 9, "season": 2020, "mu_total": 50.0,
                              "y_total": 50.0 - late_err, "model_err": late_err},
                             index=range(n_per)))
    return pd.concat(rows, ignore_index=True)[list(V3.ESTIMATOR_COLUMNS)]


def test_the_bucket_form_subtracts_the_cold_start_mean_and_leaves_late_weeks_alone():
    src = _src({1: 3.0, 2: 3.0, 3: 3.0}, late_err=-9.0)
    wk = np.array([1, 2, 3, 4, 9])
    d, info = V3._estimate("bucket", src, wk)
    assert info["delta"] == pytest.approx(3.0)
    assert d[:3] == pytest.approx([3.0, 3.0, 3.0])
    assert d[3:] == pytest.approx([0.0, 0.0]), "a week-scoped form touched weeks 4+"


def test_the_per_week_form_recovers_each_week_separately():
    src = _src({1: 5.0, 2: 3.0, 3: 1.0})
    d, info = V3._estimate("per_week", src, np.array([1, 2, 3, 7]))
    assert [info["delta_by_week"][k] for k in ("1", "2", "3")] == pytest.approx([5.0, 3.0, 1.0])
    assert d == pytest.approx([5.0, 3.0, 1.0, 0.0])


def test_the_linear_form_recovers_an_exact_ramp():
    src = _src({1: 5.0, 2: 3.0, 3: 1.0})
    _, info = V3._estimate("linear", src, np.array([1, 2, 3]))
    assert info["slope"] == pytest.approx(-2.0)
    assert info["intercept"] == pytest.approx(7.0)


def test_the_shrunk_form_collapses_to_the_foil_when_the_sample_cannot_see_the_level():
    """The whole point of registering a shrunk arm: at fold 2018 the in-fold level is estimated
    from ~141 rows at σ≈16.6, so its SE is ≈1.4 pts against a ≈2.5 pt effect."""
    assert V3._js_shrink(2.0, 0.1) == pytest.approx(2.0 * (1 - 0.0025))
    assert V3._js_shrink(0.5, 5.0) == 0.0, "a level the sample cannot see must shrink to zero"
    assert V3._js_shrink(0.0, 1.0) == 0.0


def test_the_two_matched_foils_differ_only_in_the_channel_each_removes():
    """`pooled_all` and `pooled_cold` share a MAGNITUDE and differ in SCOPE — which is what makes
    the paired reading attributable (NF-D10 / NF-D15 g′) instead of a leaderboard rank."""
    src = _src({1: 3.0, 2: 3.0, 3: 3.0}, late_err=-1.0)
    wk = np.array([1, 2, 3, 9])
    d_all, i_all = V3._estimate("pooled_all", src, wk)
    d_cold, i_cold = V3._estimate("pooled_cold", src, wk)
    assert i_all["delta"] == pytest.approx(i_cold["delta"])          # same magnitude
    assert d_all[:3] == pytest.approx(d_cold[:3])                    # identical on the cold cell
    assert d_all[3] != 0.0 and d_cold[3] == 0.0                      # differ ONLY on weeks 4+


def test_the_over_scale_anchor_is_exactly_twice_the_bucket_constant():
    src = _src({1: 2.0, 2: 2.0, 3: 2.0})
    _, b = V3._estimate("bucket", src, np.array([1]))
    _, o = V3._estimate("over2", src, np.array([1]))
    assert o["delta"] == pytest.approx(2.0 * b["delta"])


def test_the_zero_form_is_the_do_nothing_degenerate():
    d, info = V3._estimate("zero", _src({1: 3.0, 2: 3.0, 3: 3.0}), np.array([1, 2, 9]))
    assert info["delta"] == 0.0 and np.all(d == 0.0)


def test_a_form_with_no_source_rows_HALTS_rather_than_returning_zero():
    """NF1.7 (a) — an unevaluable magnitude is never a pass. A silent 0.0 here would make the arm
    byte-identical to the foil and score as an honest tie."""
    empty = pd.DataFrame(columns=list(V3.ESTIMATOR_COLUMNS))
    for form in ("bucket", "per_week", "linear"):
        with pytest.raises(SystemExit):
            V3._estimate(form, empty, np.array([1, 2, 3]))


def test_the_linear_form_HALTS_on_a_single_source_week():
    with pytest.raises(SystemExit, match="distinct source weeks"):
        V3._estimate("linear", _src({1: 3.0}), np.array([1, 2, 3]))


# ── in-fold-ness: the whole admissibility argument ─────────────────────────────────────────────

def test_the_inner_walk_forward_can_only_see_seasons_strictly_before_the_eval_year():
    """VAL2 §9 constraint 2 / NF-D18 / NF-D20 — the magnitude must be selected IN-FOLD. If this
    filter widened, VAL3 would be fitting a constant with the answer in view, which is the
    inadmissible-λ shape the whole story exists to avoid."""
    body = ast.unparse(ast.parse(inspect.getsource(V3.infold_oos)))
    assert "df[df['game_year'] < eval_year]" in body.replace('"', "'")


def test_the_inner_min_train_seasons_is_a_design_quantity_not_a_tuned_one():
    """It is fixed from the FOLD STRUCTURE (at 3, the earliest outer fold has zero inner folds and
    every arm is UNDEFINED there), never from a score."""
    assert V3.INNER_MIN_TRAIN_SEASONS == 2
    assert "min_train_seasons=min_train_seasons" in inspect.getsource(V3.infold_oos)


def _reachable_halt_guards(fn) -> list[str]:
    """Every `raise SystemExit` in `fn` whose enclosing `if` test is not a constant falsehood.

    ⭐ Read off the AST, NOT as a substring: `if False and len(x) == 0: raise SystemExit(...)`
    contains every string a text scan looks for while HALTing on nothing. That is the exact
    "a break that lands but does not move the asserted predicate" class NCAAF-CLV-repair's own
    RED proof caught, and this file's RED proof caught it here too.
    """
    tree = ast.parse(inspect.getsource(fn).lstrip())
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        if not any(isinstance(n, ast.Raise) and getattr(n.exc.func, "id", "") == "SystemExit"
                   for n in ast.walk(node) if isinstance(n, ast.Raise) and n.exc is not None
                   and isinstance(n.exc, ast.Call)):
            continue
        test = ast.unparse(node.test)
        if test in ("False", "0", "None"):          # a dead guard
            continue
        if isinstance(node.test, ast.BoolOp) and any(
                ast.unparse(v) == "False" for v in node.test.values):
            continue                                 # `if False and <real test>`
        out.append(test)
    return out


def test_an_outer_fold_with_no_inner_fold_HALTS_reachably():
    tests = _reachable_halt_guards(V3.infold_oos)
    assert any("splits" in t for t in tests), \
        f"the ZERO-inner-fold HALT is unreachable or gone; live guards: {tests}"
    assert "ZERO inner folds" in inspect.getsource(V3.infold_oos)


def test_only_the_diagnostic_anchors_are_ever_handed_the_eval_fold_residuals():
    """⭐ The single most important structural guard in the file: an honest arm that could reach
    `peek_src` would be peeking, and its score would look like skill."""
    body = ast.unparse(ast.parse(inspect.getsource(V3.stage_score)))
    assert "'oracle_bucket': peek_src" in body.replace('"', "'"), \
        "the peek source is no longer routed by arm NAME"
    assert body.count("peek_src") >= 2
    # an honest arm's source must be `infold`, via the .get(...) default
    assert ".get(a.name, infold)" in body


# ── the ship clauses ───────────────────────────────────────────────────────────────────────────

def test_every_preregistered_clause_is_present_and_each_reads_one_quantity():
    body = inspect.getsource(V3.ship_clauses)
    for c in ("C1_pooled_pit_not_degraded", "C2_pooled_calib_floor", "C3_cold_calib_floor",
              "C4_market_blind_estimator", "C5_week_scoped", "C6_margin_frozen",
              "C7_sigma_frozen", "C8_own_form_oracle_floor"):
        assert c in body, f"clause {c} is gone"


def _ships_body() -> str:
    """JUST the `_ships` closure. ⚠️ Scoping matters: every needle below ALSO appears elsewhere in
    `stage_decide` (`"pbo_pass": bool(pbo < PBO_GATE)`, `"bh_pass": bool(bh_pass[a])`, …), so a
    whole-function scan passes with the gate deleted from the ship rule — which is what this file's
    RED proof measured before the scope was tightened."""
    body = inspect.getsource(V3.stage_decide)
    return body.split("def _ships(")[1].split("\n    survivors =")[0]


def test_the_ship_rule_requires_every_gate_and_not_merely_the_clauses():
    body = _ships_body()
    for needle in ('r["clauses"]["all_ok"]', 'r["dsr"] >= DSR_GATE', 'r["bh_pass"]',
                   'r["fold_consistency_ok"]', "pbo < PBO_GATE",
                   'r["gain_vs_foil_cold"] > 0', 'not r["tie_with_foil"]'):
        assert needle in body, f"the ship rule no longer requires {needle}"


def test_the_calibration_constraints_are_floors_and_tolerances_not_targets():
    """NF1.8/E2.1-r — a coverage figure is a CONSTRAINT and must never become a criterion; and the
    PIT clause is a NOT-WORSE tolerance, not a 'must improve' target that a widening arm wins."""
    assert V3.CALIB_FLOOR == 0.78 and V3.PIT_DEGRADE_TOL == 0.0020
    body = inspect.getsource(V3.ship_clauses)
    assert "pooled_pit <= foil_pit + PIT_DEGRADE_TOL" in body
    assert "pooled_cal >= CALIB_FLOOR" in body and "cold_cal >= CALIB_FLOOR" in body


def test_the_week_scoping_clause_exempts_only_the_declared_all_row_foil():
    body = inspect.getsource(V3.ship_clauses)
    assert 'scope == "all" or late_gap <= FROZEN_TOL' in body


# ── the anchors ────────────────────────────────────────────────────────────────────────────────

def _folds(arm_crps, peek_crps, mn_crps, n=4):
    return {"folds": [{"cold": {"crps": arm_crps, "n": 10}, "pooled": {"crps": arm_crps, "n": 10},
                       "own_form_peek": {"crps_cold": peek_crps},
                       "own_form_matched_n": {"crps_cold": mn_crps}} for _ in range(n)]}


def _anchor_input(arm_crps, peek, mn):
    arms = {a.name: _folds(arm_crps, peek, mn) for a in V3.ARMS}
    arms["oracle_bucket"] = _folds(peek, peek, mn)
    arms["matched_n_bucket"] = _folds(mn, peek, mn)
    return arms


def test_a_peek_that_cannot_beat_its_own_matched_n_control_is_INACTIVE_not_a_pass():
    """NF-W6d / NF-D20 — an anchor pair that could not ACT is uninformative. Recording it as a
    PASS is how a vacuous gate ends up certifying an arm it never examined."""
    arms = _anchor_input(arm_crps=9.0, peek=9.5, mn=9.5)       # peek buys nothing
    rep = V3.anchor_report(arms, arms["none"]["folds"])
    assert rep["per_form_oracle"]["bucket_shift"]["state"] == "INACTIVE"
    assert rep["per_form_oracle"]["bucket_shift"]["anchor_pair_active"] is False


def test_an_active_peek_that_the_arm_beats_is_BEATEN():
    arms = _anchor_input(arm_crps=9.0, peek=9.4, mn=9.6)       # peek is active AND the arm beats it
    rep = V3.anchor_report(arms, arms["none"]["folds"])
    assert rep["per_form_oracle"]["bucket_shift"]["state"] == "BEATEN"


def test_an_active_peek_the_arm_does_not_beat_is_FLOORED():
    arms = _anchor_input(arm_crps=9.5, peek=9.3, mn=9.6)
    rep = V3.anchor_report(arms, arms["none"]["folds"])
    assert rep["per_form_oracle"]["bucket_shift"]["state"] == "FLOORED"


def test_the_oracle_is_computed_PER_FORM_and_not_once_for_the_whole_field():
    """NF-D16 (g‴) — `per_week_shift` and `linear_decay` CONTAIN the bucket constant as a special
    case, so a single bucket ceiling would veto a legitimately-better nested form as a metric
    inversion. Each arm is floored by the peeking version of its OWN estimator."""
    body = ast.unparse(ast.parse(inspect.getsource(V3.stage_score)))
    assert "_estimate(a.form, peek_src, wk)" in body
    assert "_estimate(a.form, matched_src, wk)" in body
    forms = {a.name: a.form for a in V3.ARMS}
    assert len({forms[c] for c in V3.CANDIDATES}) == len(V3.CANDIDATES), \
        "two candidates share a form; their per-form floors would be the same ceiling"


def test_the_matched_n_source_is_sized_to_the_eval_folds_own_cold_cell():
    """NF1.9 (f) — a peeking oracle is a floor only at MATCHED family AND MATCHED sample. Without
    the size match an honest arm beating the peek is a capacity effect read as a violation."""
    body = ast.unparse(ast.parse(inspect.getsource(V3.stage_score)))
    assert "n_match = min(int(cold_mask.sum()), len(infold_cold))" in body


# ── deflation bookkeeping ──────────────────────────────────────────────────────────────────────

def test_V_is_measured_over_the_real_arms_only():
    """MH2.1 (a) — an anchor that exists to POLICE the metric must never SET the gate's own bar."""
    body = inspect.getsource(V3.stage_decide)
    assert "sr_all = np.array([sharpe(series[a]) for a in real], float)" in body
    assert "real = [a for a in (CANDIDATES + LOSERS)]" in body
    assert "DIAGNOSTICS" not in body.split("sr_all")[0].split("real = ")[-1]


def test_the_binding_V_is_the_full_field_and_the_convention_variant_is_only_reported():
    """DSR-CONV is FORWARD-ONLY. Declaring the generous reading NON-binding is the conservative
    direction and forecloses the NF-W7h failure where re-reading `V` deletes the arm under test."""
    body = inspect.getsource(V3.stage_decide)
    # ⚠️ The EXACT binding line, not a loose substring: `V_convention` is legitimately passed to the
    # reported variant two lines below, so `"var_trials_sr=V_binding" in body` stays true after the
    # two are swapped (the RED proof caught precisely that).
    assert ("        d = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, "
            "var_trials_sr=V_binding)") in body, "the BINDING DSR is no longer the full-field V"
    assert ("        d_conv = (deflated_sharpe(s, n_trials=DECLARED_FIELD_SIZE, "
            "var_trials_sr=V_convention)") in body
    assert 'var_trials_sr=V_binding, fold_wins=r["fold_wins"]' in body, \
        "classify_null is no longer handed the BINDING V"
    assert '"var_trials_sr_binding": V_binding' in body
    assert '"var_trials_sr_convention_variant": V_convention' in body
    # the classifier must be told which provenance it was handed
    assert "degenerates_excluded_from_v=False" in body


def test_the_null_classifier_is_given_the_declared_field_size_and_measured_moments():
    """MH2.7 — `declared_field_size` is what stops the field-size remedy prescribing the retired
    post-hoc field; the moments must be MEASURED or the classifier answers about a different world."""
    body = inspect.getsource(V3.stage_decide)
    assert "declared_field_size=DECLARED_FIELD_SIZE" in body
    assert 'skew=r["series_skew"], kurt=r["series_kurt"]' in body
    assert 'v.detail.get("field_remedy_admissible")' in body


def test_a_deflation_refusal_publishes_no_fold_or_season_retest_trigger():
    """NF-D18 — no fold count moves a pre-registered gate CHOICE, so a `POWER_LIMITED`-style
    'more seasons' trigger for a PBO refusal is the actively-misleading direction."""
    body = inspect.getsource(V3.stage_decide)
    assert '"binding_half": ("constraint" if failed else' in body
    assert '"deflation" if deflation_failed else "statistical"' in body
    assert "never more seasons" in body


def test_the_pbo_sensitivity_marks_exactly_one_population_as_binding():
    """NF-D15 (g″) — prove the null does not rest on the gate choice, without ADOPTING a different
    gate after the fact (MH2.2)."""
    body = inspect.getsource(V3.stage_decide)
    assert '"binding_preregistered"' in body and '"binds": True' in body
    assert body.count('"binds": False') == 2


def test_the_fold_consistency_clause_is_the_calibrated_one():
    """H8 — `fold_win_rate >= 0.60` is a different gate at every fold count."""
    assert "cv_power.fold_consistency_clause(n_folds)" in inspect.getsource(V3.stage_decide)
    c = V3.cv_power.fold_consistency_clause(8)
    assert c.attainable and c.wins_required == 6


# ── the reproduction pin ───────────────────────────────────────────────────────────────────────

def test_the_pin_is_anchored_on_the_parent_never_on_val3s_own_output():
    assert V3.PIN["source"].startswith("ncaaf_val3_s1_serve_reanchor.json")
    assert "S1-serve" in V3.PIN["source"]
    assert V3.PIN["cache_assembled_at"] == "2026-08-22" and V3.PIN["n_with_close"] == 4187
    assert V3.PIN["n_oos_games"] == 6024
    assert V3.PIN["fold_years"] == list(range(2018, 2026))


def test_check_pin_is_strict_on_every_leg_and_its_fixture_derives_from_PIN():
    """The fixture is DERIVED from `PIN`, never restated — a restated constant silently rots (the
    defect NCAAF-CLV-repair found in VAL1's own pin test)."""
    meta = {"assembled_at": V3.PIN["cache_assembled_at"], "n_with_close": V3.PIN["n_with_close"]}
    oos = pd.DataFrame(index=range(V3.PIN["n_oos_games"]))
    years = list(V3.PIN["fold_years"])
    assert V3.check_pin(meta, oos, years)["all_ok"] is True
    assert V3.check_pin({**meta, "n_with_close": V3.PIN["n_with_close"] - 1}, oos,
                        years)["all_ok"] is False
    assert V3.check_pin(meta, pd.DataFrame(index=range(V3.PIN["n_oos_games"] - 1)),
                        years)["all_ok"] is False
    assert V3.check_pin(meta, oos, years[:-1])["all_ok"] is False
    assert V3.check_pin({**meta, "assembled_at": "1999-01-01"}, oos, years)["all_ok"] is False


def test_a_failing_pin_HALTS_the_decide_stage_unless_explicitly_overridden():
    body = inspect.getsource(V3.stage_decide)
    assert 'if not pin["all_ok"] and not args.allow_pin_fail' in body
    assert "raise SystemExit" in body.split('if not pin["all_ok"]')[1][:400]


# ── the over-tilt report is DESCRIPTIVE, never a clause ────────────────────────────────────────

def test_the_over_tilt_report_never_reaches_the_verdict():
    """It is the only market-touching number in the study. If it entered a clause the study would
    be selecting on the market, which is the one thing a market-blind model may not do."""
    assert "over_tilt" not in _ships_body()
    assert "over_tilt" not in inspect.getsource(V3.ship_clauses)


def test_the_over_tilt_report_joins_on_game_id_and_takes_no_positional_draw_index():
    """The NCAAF-VAL2 §2 / CLV-repair misalignment class: `df[mask].reset_index(drop=True)` then
    indexing a parallel array with the reset index reads the WRONG rows, silently."""
    body = ast.unparse(ast.parse(inspect.getsource(V3.over_tilt_report)))
    assert "merge(close, on='game_id', how='left')" in body.replace('"', "'")
    assert "len(merged) != len(oos)" in body
    assert ".index.to_numpy()" not in body


def test_an_unevaluable_over_tilt_is_reported_as_such_and_never_as_a_number():
    """NF1.7 (a) — a NaN that renders like a measurement is worse than an honest refusal."""
    body = inspect.getsource(V3.over_tilt_report)
    assert '"state": "UNEVALUABLE"' in body and '"over_actually_hit": None' in body


def test_an_undefined_statistic_renders_as_na_and_not_as_a_number():
    assert V3._f(None) == "n/a"
    assert V3._f(0.5) == "0.500"


# ── whole-module invariants ────────────────────────────────────────────────────────────────────

def test_the_module_never_reads_a_market_column_outside_the_descriptive_tilt_report():
    """Comment-stripped, because this module's own prose names `close_total` repeatedly."""
    src = _src_no_comments()
    tilt = ast.unparse(ast.parse(inspect.getsource(V3.over_tilt_report)))
    outside = src.replace(tilt, "")
    for col in ("close_total", "close_home_spread"):
        assert col not in outside, f"{col} is read outside the descriptive over-tilt report"


def test_the_module_does_not_write_any_served_artifact():
    src = _src_no_comments()
    for forbidden in ("ncaaf_game_distribution_v", "ncaaf_game_mean_v", "sub_model_registry",
                      "fit_served_mean", "--publish"):
        assert forbidden not in src, f"VAL3 must not touch {forbidden}"


def test_the_runner_never_writes_to_the_narrative_writeup_path():
    """NF-W2c-CBS — a runner that writes to a hand-written narrative's FIXED path silently clobbers
    it on every re-run, and `git status` is the only thing that would catch it."""
    src = _src_no_comments()
    assert "ncaaf_val3_cold_start_readout.md" in src
    assert "ncaaf_val3_cold_start_mu.md" not in src, \
        "the harness writes to the NARRATIVE path; it would clobber the writeup on every run"


def test_the_study_declares_itself_market_blind_and_best_alpha_zero():
    src = _src_no_comments()
    assert "'market_blind': True" in src.replace('"', "'")
    assert "'best_alpha': 0" in src.replace('"', "'")
