"""Guards for NCAAF-VAL3b — the cold-start μ correction as ONE pre-registered contrast.

Each clause is ISOLABLE (NF-D17): a fixture that trips two clauses proves neither, so every test
below reads exactly one quantity and its RED proof deletes exactly one thing. RED-proven by
`quant_sports_intel_models/football/ncaaf/models/ncaaf_val3b_red_proof.py`.

⭐ The thing these guards exist to defend is a SUCCESSOR shape whose declared field is SMALLER than
its parent's. That is legitimate only under a specific set of conditions, and every one of them is
a property of the CODE, not of a paragraph — so each gets a guard: the field really has one
selectable arm; PBO is INAPPLICABLE rather than a number that could read as a pass; `V` is the
asymptotic no-field default rather than the parent's measured dispersion; and the two materiality
bars follow from VAL2's constants rather than from an author who had already read the parent's
scores.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3_cold_start_mu as V3
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3b_single_contrast as M

_SRC = Path(M.__file__).read_text()
#: comment-stripped, so PROSE can never satisfy a source-inspection guard (INC-38).
_CODE = "\n".join(ln.split("#", 1)[0] for ln in _SRC.splitlines())


# ── the field ────────────────────────────────────────────────────────────────────────────────────

def test_the_field_has_exactly_one_selectable_arm():
    """The whole successor shape rests on this. If a second candidate appears, PBO stops being
    INAPPLICABLE and the pre-registration is no longer describing the code."""
    assert M.CANDIDATES == ("bucket_shift",)
    assert len([a for a in M.ARMS if a.role == "candidate"]) == 1
    assert M.DECLARED_FIELD_SIZE == 2


def test_no_delta_scaling_arm_is_registered():
    """⛔ `over_scale` topped VAL3's raw leaderboard but its PAIRED read is a TIE — a rank cannot
    tell a tie from a win (NF1.8), and a magnitude adopted after seeing it rank is the
    inadmissible-λ shape (NF-D18/NF-D20). No scaled variant may enter this field."""
    forms = {a.form for a in M.ARMS}
    assert "over2" not in forms
    assert not any("scale" in a.name for a in M.ARMS)


def test_the_matched_foils_are_out_of_the_field_and_the_attribution_is_cited():
    """VAL3's matched foils are honest, in-principle-shippable estimators; keeping one as a
    'diagnostic' to hold it out of the multiplicity count is the laundering MH2.2 forbids. They are
    OUT — and the channel attribution is therefore CITED, which the record must say."""
    names = {a.name for a in M.ARMS}
    assert "week_blind" not in names and "pooled_level" not in names
    assert "channel_attribution_cited_from_val3" in _CODE


def test_only_peeking_constructions_are_diagnostics():
    """A diagnostic is excluded from `n_trials` AND `V` (MH2.1 (a)). That is defensible only for a
    PEEKING construction, which was never a candidate for selection."""
    assert set(M.DIAGNOSTICS) == {"oracle_bucket", "matched_n_bucket"}
    for name in M.DIAGNOSTICS:
        assert "peek" in next(a.doc for a in M.ARMS if a.name == name).lower() \
            or "matched" in name


# ── PBO: INAPPLICABLE, never a number ────────────────────────────────────────────────────────────

def test_pbo_is_never_computed_and_never_recorded_as_passed():
    """⛔ §4.1. A two-arm CSCV number inside the successor's own gate block would read as 'the gate
    we failed now passes'. It must not be computed, and `pbo` must be None with an explicit state."""
    assert "pbo_cscv" not in _CODE, "VAL3b must not compute a PBO number, even as a diagnostic"
    assert '"pbo": None' in _CODE
    assert '"pbo_state": "INAPPLICABLE"' in _CODE
    assert not re.search(r'"pbo_pass"', _CODE), "a PBO pass/fail flag would invite the misreading"


def test_classify_null_is_told_one_arm_so_it_takes_the_pbo_inapplicable_branch():
    """`cv_power.classify_null`'s n_arms<2 branch (the MH2.7 co-fix) reports PBO INAPPLICABLE and
    emits NO fold trigger. Passing a padded `n_arms` would resurrect the fabricated fold shortage
    the fantasy vertical hand-corrected four times."""
    assert "n_arms=len(CANDIDATES)" in _CODE
    assert "declared_field_size=DECLARED_FIELD_SIZE" in _CODE


# ── V and the deflation bar ──────────────────────────────────────────────────────────────────────

def test_v_is_the_asymptotic_no_field_default_not_the_parents_measured_dispersion():
    """⛔ Importing VAL3's measured V (0.05878) would be a dispersion from a field this
    registration does not have. `None` selects `deflated_sharpe`'s documented 1/n_obs fallback."""
    assert M.VAR_TRIALS_SR is None
    assert "0.05878" not in _CODE.split("DSR_SENSITIVITY")[0], \
        "the parent's measured V must not reach the BINDING deflation call"
    assert "var_trials_sr=VAR_TRIALS_SR" in _CODE


def test_the_dsr_sensitivity_reports_the_parents_harsher_bar_and_never_binds():
    """The first question a sceptical reader asks: did the arm CLEAR the gate, or was the gate
    LOWERED? It must be COMPUTED, and it must not be able to change a verdict."""
    s = np.array([0.0085, 0.0311, 0.0899, 0.0651, 0.0274, 0.1020, 0.2113, 0.1433])
    sens = M.dsr_sensitivity(s)
    assert "val3_full_field" in sens
    assert sens["val3_full_field"]["var_trials_sr"] == pytest.approx(0.05878)
    assert all(v["binds"] is False for v in sens.values())
    # the sensitivity must be STRICTER than the binding reading, or it proves nothing
    from betting_ml.utils.overfitting import deflated_sharpe
    binding = deflated_sharpe(s, n_trials=M.DECLARED_FIELD_SIZE, var_trials_sr=M.VAR_TRIALS_SR)
    assert sens["val3_full_field"]["sr0"] > binding.sr0


# ── materiality: the bars VAL3 handed forward ────────────────────────────────────────────────────

def test_m2_is_derivable_from_val2s_constants_and_the_literal_has_not_drifted():
    """A bar written by an author who had already read the parent's scores is only credible if it
    RE-DERIVES from inputs that pre-date them. This is that re-derivation, run for real."""
    d = M.verify_m2_derivation()
    assert d["derived_rel_gain"] == pytest.approx(M.MATERIAL_REL_CRPS_GAIN, abs=5e-6)
    # and it must be a genuine fraction of the available headroom, not a rounding of zero
    assert 0.5 < d["derived_rel_gain"] / d["full_removal_rel_gain"] < 0.9


def test_m2_derivation_halts_when_the_literal_drifts(monkeypatch):
    """The check must be able to FAIL — a bar whose derivation cannot refuse it is decoration."""
    monkeypatch.setattr(M, "MATERIAL_REL_CRPS_GAIN", 0.001)
    with pytest.raises(SystemExit, match="drifted"):
        M.verify_m2_derivation()


def test_m1_is_val2s_inherited_band_and_is_not_re_derived():
    assert M.MATERIAL_BIAS_PTS == 1.00


def _mat_folds(bias, crps):
    return [{"cold": {"n": 100, "bias": bias, "crps": crps, "pit_max_decile_dev": 0.0,
                      "calib_80": 0.8}} for _ in range(8)]


def test_m1_and_m2_are_isolable_refusals():
    """NF-D17: a fixture that trips two clauses proves neither. Each bar must refuse ALONE, with the
    other satisfied — so a RED proof deleting one clause has something only that clause can catch."""
    foil = _mat_folds(2.0, 9.4642)
    # M1 fails ALONE: a huge CRPS gain but only a 0.5 pt bias move
    only_m1 = M.materiality(_mat_folds(1.5, 9.4642 * (1 - 0.05)), foil)
    assert only_m1["M1_bias_reduction_pts"]["ok"] is False
    assert only_m1["M2_relative_crps_gain"]["ok"] is True
    # M2 fails ALONE: a big bias move worth almost nothing on the proper score
    only_m2 = M.materiality(_mat_folds(0.5, 9.4642 * (1 - 0.0001)), foil)
    assert only_m2["M1_bias_reduction_pts"]["ok"] is True
    assert only_m2["M2_relative_crps_gain"]["ok"] is False


def test_m1_reads_the_ABSOLUTE_bias_move_so_an_over_correction_cannot_pass():
    """⭐ A SIGN FLIP is not a bias reduction. Reading the SIGNED move (`foil − arm`) rewards an arm
    that over-corrects straight past zero: +2.0 → −1.5 scores 3.5 signed and would sail through a
    1.0-pt band, while the model is now 1.5 pts WRONG THE OTHER WAY. The fixture is built so ONLY
    the abs/signed distinction can flip it — the CRPS side is held identical (E2.1-r's mirror: a
    bar that a degenerate direction wins is not a bar)."""
    foil = _mat_folds(2.0, 9.4642)
    over = M.materiality(_mat_folds(-1.5, 9.4642 * (1 - 0.05)), foil)   # signed 3.5, abs 0.5
    assert over["M1_bias_reduction_pts"]["value"] == pytest.approx(0.5)
    assert over["M1_bias_reduction_pts"]["ok"] is False, \
        "an over-correction past zero must NOT count as a materially reduced bias"


def test_m2_is_a_RELATIVE_gain_so_it_does_not_depend_on_the_metrics_scale():
    """⭐ M2's whole derivation is σ-free — it is a FRACTION of the foil's CRPS, which is what lets
    it be computed from VAL2's constants without knowing σ. An absolute-gain implementation would
    silently re-introduce the scale dependence. The fixture puts the two readings on OPPOSITE sides
    of the band (relative 5 % ✅ vs absolute 0.005 ❌ against a 0.0075 band), so only that
    distinction can flip it."""
    foil = _mat_folds(2.0, 0.10)                                  # a small-scale metric
    r = M.materiality(_mat_folds(0.5, 0.10 * (1 - 0.05)), foil)
    assert r["M2_relative_crps_gain"]["value"] == pytest.approx(0.05)
    assert r["M2_relative_crps_gain"]["ok"] is True, \
        "a 5 % relative gain must clear the band regardless of the metric's absolute scale"


# ── the clauses are the PARENT's, called ─────────────────────────────────────────────────────────

def test_ship_clauses_are_the_parents_function_not_a_copy():
    """One policy with two call sites is the E9.61 two-renderers hazard, and a restated clause is
    how a successor silently stops being judged by the bar its parent used."""
    assert "V3.ship_clauses(" in _CODE
    assert "def ship_clauses" not in _CODE


def test_the_estimator_and_metric_are_imported_from_the_parent():
    """Same reason: the population, folds, estimator and metric must be the PARENT's objects."""
    assert M.SERVED is V3.SERVED
    assert M.WEEK_COL == V3.WEEK_COL and M.COLD_START_MAX_WEEK == V3.COLD_START_MAX_WEEK
    for call in ("V3.infold_oos(", "V3._estimate(", "V3.cell_metrics(", "V3.fold_series("):
        assert call in _CODE, f"{call} must be the parent's"


def test_the_infold_estimator_is_called_on_the_folds_own_eval_year():
    """⭐ The name-match above is NOT enough, and the RED proof proved it: `V3.infold_oos(...,
    fold.eval_year + 1)` keeps the string and quietly lets the estimator see the eval season — the
    "it landed but did not move the asserted predicate" class (E11.24 #815). The in-fold-ness IS
    the admissibility argument of this whole study, so it is checked at the CALL SHAPE."""
    calls = [n for n in ast.walk(ast.parse(_SRC))
             if isinstance(n, ast.Call) and ast.unparse(n.func) == "V3.infold_oos"]
    assert len(calls) == 1, "exactly one in-fold estimator call is expected"
    args = [ast.unparse(a) for a in calls[0].args]
    assert args[-1] == "fold.eval_year", (
        f"the estimator must be anchored on the fold's OWN eval year, got {args[-1]!r} — anything "
        "else lets the nested walk-forward see rows it must not")


# ── the pin ──────────────────────────────────────────────────────────────────────────────────────

def test_the_population_legs_bind_and_only_the_date_leg_is_reported():
    """§7 declared this forward so it could not look like a loosening after a failure. The three
    legs that DEFINE the population must HALT; the clock-driven one must not silently join them."""
    assert M.PIN_REPORTED_ONLY == ("cache_assembled_at",)
    assert set(M.PIN) >= {"n_with_close", "n_oos_games", "fold_years"}
    assert "cache_assembled_at" not in M.PIN, \
        "the date must not be a pinned target — it moves with the clock"


def test_a_failing_population_leg_halts():
    import pandas as pd
    oos = pd.DataFrame({"x": range(M.PIN["n_oos_games"] - 1)})       # one row short
    r = M.check_pin({"n_with_close": M.PIN["n_with_close"], "assembled_at": "2026-08-23"},
                    oos, M.PIN["fold_years"])
    assert r["all_ok"] is False
    assert r["checks"]["n_oos_games"]["ok"] is False


def test_the_date_leg_cannot_fail_the_pin():
    import pandas as pd
    oos = pd.DataFrame({"x": range(M.PIN["n_oos_games"])})
    r = M.check_pin({"n_with_close": M.PIN["n_with_close"], "assembled_at": "1999-01-01"},
                    oos, M.PIN["fold_years"])
    assert r["all_ok"] is True
    assert r["checks"]["cache_assembled_at"]["binds"] is False


def test_the_pin_names_the_parent_it_came_from():
    """⛔ Never anchored on VAL3b's own output, which would make the pin restate what it checks."""
    assert "s1_serve_reanchor" in M.PIN["source"]


# ── the runner does not clobber its parent's record ──────────────────────────────────────────────

def test_val3b_writes_only_its_own_paths():
    """A runner that writes to a fixed path its parent owns clobbers a DECIDED story's record on
    every re-run (NF-W2c-CBS; NF-W7f)."""
    for p in (M._SCORES_JSON, M._OUT_JSON, M._OUT_MD):
        assert p.name.startswith("ncaaf_val3b_"), f"{p.name} is not a VAL3b-owned path"


# ── the descriptive market read ──────────────────────────────────────────────────────────────────

def test_the_over_tilt_uses_the_clv_leg_immune_implementation_and_names_it():
    """The row-misaligned `_clv_eval` (a reset_index positional bug) is a recorded INC. Any vs-close
    figure must come from the `game_id`-join implementation, and the record must NAME it."""
    assert "V3.over_tilt_report(" in _CODE
    # ⭐ the key must be WRITTEN by the scorer, not merely mentioned by the reader: the RED proof
    # renamed the writer's key and this guard stayed green off `stage_decide`'s own read of it
    # (the NF-C0e wired-vs-invoked shape). Checked at the writer's dict literal, by AST.
    written = {
        ast.unparse(k) for fn in ast.walk(ast.parse(_SRC))
        if isinstance(fn, ast.FunctionDef) and fn.name == "stage_score"
        for d in ast.walk(fn) if isinstance(d, ast.Dict) for k in d.keys if k is not None}
    assert "'over_tilt_implementation'" in written, \
        "the scorer must WRITE the implementation name into its own artifact"
    # ⚠️ a CALL, not a mention: the pin's provenance string legitimately NAMES `_clv_eval` (it
    # records that the parent ran the REPAIRED one), and a bare substring check fails on that —
    # which would push a future author to delete the provenance to get green.
    calls = {ast.unparse(n.func) for n in ast.walk(ast.parse(_SRC)) if isinstance(n, ast.Call)}
    assert not any("_clv_eval" in c for c in calls)


def test_no_market_column_can_reach_the_estimator():
    """C4, exercised rather than asserted."""
    import pandas as pd
    frame = pd.DataFrame({M.WEEK_COL: [1], "season": [2020], "mu_total": [50.0],
                          "y_total": [48.0], "model_err": [2.0], "close_total": [51.0]})
    with pytest.raises(SystemExit):
        V3.assert_estimator_is_market_blind(frame)


# ── the parity check ─────────────────────────────────────────────────────────────────────────────

def test_the_parity_leg_iii_reads_the_ast_not_a_substring():
    """⚠️ This leg's FIRST implementation was `col in source` and it returned a FALSE PASS —
    satisfied by `df["season_order_week"] = df["week"]`, an ALIAS of exactly the column the study
    forbids. A name-match cannot tell a column from an alias of the column it forbids."""
    from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3b_serve_parity as P
    leg = P.leg_iii_week_column()
    assert leg["ok"] is False
    assert leg["n_raw_week_aliases"] >= 1
    # and the substring check the AST version replaced would have PASSED — that is the point
    assert P.STUDY_WEEK_COL in P._SNAPSHOT_PY.read_text()


def test_the_parity_check_writes_nothing_served():
    from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3b_serve_parity as P
    src = Path(P.__file__).read_text()
    code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    for banned in (".save(", "put_object", "write_parquet", "to_parquet"):
        assert banned not in code


def test_every_parity_leg_must_pass_for_a_pre_opener_ship():
    """AC (a): any leg failing ⇒ DEPLOY-HELD. An `any()` here would ship on one green leg."""
    from quant_sports_intel_models.football.ncaaf.models import ncaaf_val3b_serve_parity as P
    code = "\n".join(ln.split("#", 1)[0] for ln in Path(P.__file__).read_text().splitlines())
    assert 'ok = all(l["ok"] for l in legs)' in code


# ── nothing serves ───────────────────────────────────────────────────────────────────────────────

def test_the_module_writes_no_served_artifact():
    tree = ast.parse(_SRC)
    calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for banned in ("mean.save", "params.save", "boto3.client"):
        assert banned not in calls
    assert "artifacts" not in _CODE, "VAL3b must not touch the served artifact directory"


def test_best_alpha_is_zero_and_the_study_declares_itself_market_blind():
    assert '"best_alpha": 0' in _CODE
    assert '"market_blind": True' in _CODE
