"""E7.12 SLICE 2 runner — the harness logic that decides what gets shipped.

`test_e7_12_survivorship.py` covers the hazard/propensity mechanism. This file covers the RUNNER's
judgement, which is where a survivorship slice actually goes wrong: not by computing a bad number, but by
computing a good number and then not consuming it.

Three defects were found by running the smoke and are pinned here so they cannot come back:

  1. **A statistic computed and never consumed.** The propensity-stratified read is the slice's whole
     directional falsification, and the first version PRINTED it while the verdict logic ignored it — so
     the ISO smoke selected an arm whose entire benefit sat in the HIGH-propensity tercile while it HURT
     the low-propensity one. Exactly the E7.12 slice-1p BH-FDR shape, one story later.
  2. **Two arms that were secretly one arm.** "Stabilized" IPW normalises to mean 1, so a constant
     numerator cancels and the arm is byte-identical to raw IPW — three leaderboard rows agreeing to six
     decimals, padding the field the deflation is computed over.
  3. **A baseline that re-reports an earlier win.** The S2 baseline must be the SHIPPED slice-1 config
     per metric; falling back to `ContextSpec()` would re-book the slice-1 lift as an S2 lift.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.scripts.milb_mle.run_e7_12_slice1 import SIDES
from betting_ml.scripts.milb_mle.run_e7_12_slice2 import (
    synthetic_recovery_check,
    S2_LADDER,
    SHIPPED_RUNG,
    attach_arm_columns,
    by_label,
    concentration_read,
    s2_verdict,
    shipped_spec,
)


def _strat(arm: str, lo: float, mid: float, hi: float) -> pd.DataFrame:
    return pd.DataFrame([
        {"arm": arm, "stratum": 0, "n": 100, "mae": 0.04, "pct_lift_vs_ref": lo},
        {"arm": arm, "stratum": 1, "n": 100, "mae": 0.04, "pct_lift_vs_ref": mid},
        {"arm": arm, "stratum": 2, "n": 100, "mae": 0.04, "pct_lift_vs_ref": hi},
    ])


def _board(arm: str, *, fold_win_rate: float = 0.8) -> pd.DataFrame:
    return pd.DataFrame([
        {"arm": "T0_shipped", "kind": "ladder", "selectable": True, "oos_mae": 0.040,
         "fold_win_rate": 0.0},
        {"arm": arm, "kind": "ladder", "selectable": True, "oos_mae": 0.039,
         "fold_win_rate": fold_win_rate},
    ])


_CLEAN_ANCHORS = {"uniform_weight_is_a_noop": True,
                  "propensity_placebo_vs_ipw": {"violated": False},
                  "mills_placebo_vs_heckman": {"violated": False}}


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The directional falsification is ENFORCED, not merely reported
# ══════════════════════════════════════════════════════════════════════════════════════


def test_an_ANTI_CONCENTRATED_winner_is_DROPPED_however_good_its_overall_mae():
    """🚨 THE LOAD-BEARING TEST. An arm whose benefit GROWS with propensity is the OPPOSITE of a
    selection correction — the served population (prospects who have not debuted) is low-propensity by
    construction. This shape was produced by the very first real smoke (`T2_heckman` on ISO: +0.46% high,
    -1.25% low) and the verdict logic sailed straight past it.

    An overall MAE win cannot rehabilitate it: the win means the fit reallocated attention toward the
    players it already handled best."""
    v, w, reasons = s2_verdict(_board("T2_heckman"), _CLEAN_ANCHORS,
                               _strat("T2_heckman", lo=-1.25, mid=-0.15, hi=0.46), [])
    assert v == "DROP" and w == "T0_shipped"
    assert any("anti-concentrated" in r for r in reasons), reasons


def test_a_BOTH_POSITIVE_but_HIGH_END_LOADED_arm_is_also_ineligible():
    """🪤 THE REAL CASE THE FIRST CLASSIFIER MISSED. On the live k_pct run `T3_joint` lifts +0.15% at the
    low-propensity end and +1.19% at the high end. Both are positive, so a SIGN-based rule graded it
    "flat" and shipped it as the winner — while it is the clearest example in the whole run of a benefit
    accruing to the players the fit already handled best. The pre-registered claim is about the GRADIENT,
    not the signs."""
    v, w, reasons = s2_verdict(_board("T3_joint"), _CLEAN_ANCHORS,
                               _strat("T3_joint", lo=0.151, mid=0.646, hi=1.195), [])
    assert v == "DROP" and w == "T0_shipped", (v, w, reasons)
    assert any("anti-concentrated" in r for r in reasons), reasons


def test_an_ineligible_TOP_arm_does_not_take_a_LEGITIMATE_lower_arm_down_with_it():
    """Concentration is an ELIGIBILITY criterion, not a veto applied to the winner after the fact. If the
    best-MAE arm is anti-concentrated but a lower-MAE-lift arm has the pre-registered signature, that arm
    is the pick — removing ineligible arms BEFORE the selection is what makes this a rule rather than a
    rescue."""
    board = pd.DataFrame([
        {"arm": "T0_shipped", "kind": "ladder", "selectable": True, "oos_mae": 0.0400,
         "fold_win_rate": 0.0},
        {"arm": "T3_joint", "kind": "ladder", "selectable": True, "oos_mae": 0.0381,
         "fold_win_rate": 0.82},          # best MAE, but anti-concentrated
        {"arm": "T1_ipw", "kind": "ladder", "selectable": True, "oos_mae": 0.0384,
         "fold_win_rate": 0.73},          # worse MAE, correct signature
    ])
    strat = pd.concat([_strat("T3_joint", 0.151, 0.646, 1.195),
                       _strat("T1_ipw", 0.410, 0.135, 0.042)], ignore_index=True)
    v, w, reasons = s2_verdict(board, _CLEAN_ANCHORS, strat, [])
    assert v == "ADD" and w == "T1_ipw", (v, w, reasons)
    assert any("anti-concentrated" in r for r in reasons), "the exclusion must still be REPORTED"


def test_a_CONCENTRATED_winner_is_ADDED():
    """…and the guard must not simply reject everything: the pre-registered signature — helps the
    low-propensity tercile most — passes."""
    v, w, reasons = s2_verdict(_board("T1_ipw"), _CLEAN_ANCHORS,
                               _strat("T1_ipw", lo=1.4, mid=0.6, hi=0.1), [])
    assert v == "ADD" and w == "T1_ipw", reasons


def test_a_FLAT_winner_is_ADDED_but_LABELLED_generic_reweighting():
    """A benefit that is uniform across propensity is a variance effect, not a selection correction. It
    is not a defect and is not blocked — but it must not be DESCRIBED as survivorship, so the reason
    string is the deliverable."""
    v, w, reasons = s2_verdict(_board("T1_ipw"), _CLEAN_ANCHORS,
                               _strat("T1_ipw", lo=0.40, mid=0.42, hi=0.44), [])
    assert v == "ADD" and w == "T1_ipw"
    assert any("FLAT across propensity terciles" in r for r in reasons), reasons


@pytest.mark.parametrize("lo,hi,expected", [
    (-1.2, 0.5, "anti"),            # hurts the low end, helps the high end
    (0.151, 1.195, "anti"),         # both positive but 8× loaded to the high end (the live k_pct case)
    (-0.3, -0.9, "concentrated"),   # hurts everywhere, but LESS at the low end — right direction
    (2.0, 0.1, "concentrated"),
    (0.40, 0.44, "flat"),           # within tolerance: genuine re-weighting, no gradient
])
def test_the_concentration_read_classifies_each_shape(lo, hi, expected):
    assert concentration_read(_strat("x", lo, (lo + hi) / 2, hi), "x")["verdict"] == expected


def test_a_missing_stratified_read_does_not_silently_pass_as_concentrated():
    """🪤 NF1.7 lesson 1 — an anchor that cannot fail passes on nothing. If the stratified frame is empty
    the read must say `unavailable`, never quietly grade the arm as fine."""
    assert concentration_read(pd.DataFrame(), "x")["verdict"] == "unavailable"
    assert concentration_read(_strat("x", 1.0, 1.0, 1.0), "OTHER")["verdict"] == "unavailable"


def test_a_broken_weighting_seam_BLOCKS_the_metric_outright():
    """The plumbing anchor: a uniform weight column must reproduce the unweighted fit exactly. If it does
    not, the weighted code path is moving the answer by itself and NO weighted arm on that metric can be
    attributed to its propensity — that is a BLOCK, not a DROP."""
    anchors = {**_CLEAN_ANCHORS, "uniform_weight_is_a_noop": False,
               "uniform_weight_max_abs_gap": 1e-4}
    v, w, reasons = s2_verdict(_board("T1_ipw"), anchors, _strat("T1_ipw", 2.0, 1.0, 0.1), [])
    assert v == "BLOCKED" and w == "T0_shipped"
    assert any("weighting seam" in r for r in reasons), reasons


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. The arms are genuinely distinct, and the IPW weight COMPOSES with the shipped one
# ══════════════════════════════════════════════════════════════════════════════════════


def _arm_frame(n=200, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "level": "Double-A",
        "debut_cohort": rng.integers(2018, 2024, n).astype(float),
        "mlb_pa": rng.integers(150, 900, n).astype(float),
    })


def _prop_frame(frame, seed=4):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "player_id": frame["player_id"], "level": frame["level"],
        "propensity": np.clip(rng.beta(2, 5, len(frame)), 0.02, 0.95),
    })


def test_the_IPW_weight_MULTIPLIES_the_shipped_label_weight_it_does_not_replace_it():
    """⭐ NF-D10's matched foil, in weight space. Pitcher BB% and HR-rate SHIP with `weight_col="mlb_pa"`.
    An IPW arm that swapped that out would be testing 'IPW instead of label weighting', and a loss would
    read as 'IPW does not help' when it actually means 'IPW is worse than the thing it displaced'. The
    honest pair is shipped-weights vs shipped-weights × IPW."""
    f = _arm_frame()
    prop = _prop_frame(f)
    arm = by_label(S2_LADDER)["T1_ipw"]
    out, wcol, _ = attach_arm_columns(f, arm, prop, 0.25, "mlb_pa", np.random.default_rng(0))
    assert wcol is not None and wcol != "mlb_pa"
    w = out[wcol].to_numpy(float)
    # the composed weight must track BOTH inputs: correlated with mlb_pa AND with 1/propensity
    assert np.corrcoef(w, out["mlb_pa"].to_numpy(float))[0, 1] > 0.3
    assert np.corrcoef(w, 1.0 / out["propensity"].to_numpy(float))[0, 1] > 0.3


def test_an_arm_with_no_ipw_INHERITS_the_shipped_weight_column_rather_than_dropping_it():
    """The Heckman arm adds a regressor; it must not silently also remove the shipped label weighting,
    or its comparison against T0 would be confounded by two changes at once."""
    f = _arm_frame()
    arm = by_label(S2_LADDER)["T2_heckman"]
    out, wcol, _ = attach_arm_columns(f, arm, _prop_frame(f), 0.25, "mlb_pa",
                                      np.random.default_rng(0))
    assert wcol == "mlb_pa"
    assert "_s2_mills" in out.columns and np.isfinite(out["_s2_mills"]).all()


def test_the_uniform_anchor_produces_EXACTLY_ones_times_the_shipped_weight():
    f = _arm_frame()
    arm = by_label(S2_LADDER)["A_uniform_weight"]
    out, wcol, _ = attach_arm_columns(f, arm, _prop_frame(f), 0.25, None,
                                      np.random.default_rng(0))
    np.testing.assert_allclose(out[wcol].to_numpy(float), 1.0)


def test_no_two_ladder_arms_produce_the_SAME_weight_vector():
    """🪤 THE DEFECT THIS PINS: 'stabilized' IPW multiplies by a CONSTANT and the weights are then
    normalised to mean 1, so the constant cancels EXACTLY — the arm was byte-identical to raw IPW, and
    the leaderboard carried three rows agreeing to six decimals. A duplicated arm is not harmless: it
    pads the eligible field that PBO and the contender spread are computed over, and it reads as
    independent corroboration."""
    f = _arm_frame()
    prop = _prop_frame(f)
    # compared within a `mills` setting: T3_joint legitimately reuses T1_ipw's weight vector and differs
    # by the Mills regressor, so weights alone would flag a real pair as a duplicate
    vectors: dict[tuple[str | None, str], np.ndarray] = {}
    for arm in S2_LADDER:
        if arm.ipw is None:
            continue
        out, wcol, _ = attach_arm_columns(f, arm, prop, 0.25, None, np.random.default_rng(0))
        vectors[(arm.mills, arm.label)] = out[wcol].to_numpy(float)
    keys = sorted(vectors, key=lambda k: (str(k[0]), k[1]))
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if a[0] != b[0]:
                continue
            assert not np.allclose(vectors[a], vectors[b]), (
                f"{a[1]} and {b[1]} produce the same weight vector at the same Mills setting — they "
                f"are ONE arm wearing two names")


def test_the_placebo_permutes_WITHIN_debut_cohort_so_only_the_pairing_is_destroyed():
    """The placebo must keep the weight DISTRIBUTION (and its per-cohort composition) and destroy only
    the player↔weight pairing — otherwise a loss could be blamed on a different weight distribution
    rather than on the propensity carrying no information. Same shape as the slice-1 park placebo."""
    f = _arm_frame()
    prop = _prop_frame(f)
    arm = by_label(S2_LADDER)["A_propensity_placebo"]
    out, wcol, _ = attach_arm_columns(f, arm, prop, 0.25, None, np.random.default_rng(1))
    real, _rc, _ = attach_arm_columns(f, by_label(S2_LADDER)["T1_ipw"], prop, 0.25, None,
                                      np.random.default_rng(1))
    for cohort, d in out.groupby("debut_cohort"):
        r = real.loc[real["debut_cohort"] == cohort, "_s2w_T1_ipw"].to_numpy(float)
        assert np.allclose(np.sort(d[wcol].to_numpy(float)), np.sort(r)), (
            "the placebo must be a PERMUTATION of the real weights within the cohort")


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The baseline is the SHIPPED config, and a stale label raises
# ══════════════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════════════
# 2b. The oracle floor, and the predict-time step the live gate cannot see
# ══════════════════════════════════════════════════════════════════════════════════════


def test_the_synthetic_check_RECOVERS_a_planted_selection_bias():
    """⭐ THE ORACLE FLOOR. The live gate can only score promoted players, so a live null is ambiguous
    between 'no bias' and 'this correction cannot be validated here'. If the machinery cannot recover a
    KNOWN planted bias, every live null in the report is uninformative and must be labelled so."""
    r = synthetic_recovery_check()
    assert r["recovers_planted_bias"], r
    assert r["pct_bias_removed"] > 10.0, ("a correction that removes only a sliver of a large planted "
                                          "bias is not a working instrument", r)
    assert r["best_correction"] == "heckman", (
        "selection on UNOBSERVABLES is the Heckman case by construction — if IPW were winning this, the "
        "planted process is not the one the slice claims to be testing", r)


def test_carrying_the_MILLS_RATIO_into_PREDICT_applies_NO_correction_at_all():
    """🚨 THE FINDING THIS SLICE MUST NOT SHIP WITHOUT. A Heckman model fitted with λ and predicted WITH
    each player's own λ reproduces `E[Y|X, S=1]` — the SELECTED conditional mean, i.e. precisely the
    biased quantity. The correction is entirely in setting λ→0 at prediction.

    Why it matters operationally: the live gate scores held-out GRADUATES, for whom carrying λ is the
    correct prediction, so a Heckman arm can clear the gate while correcting nothing for the prospects
    the board actually serves. If one ever ships, emission must zero λ — and only this check validates
    that step."""
    r = synthetic_recovery_check()
    assert r["heckman_mills_carried_into_predict"] > r["uncorrected"], (
        "carrying λ into predict should be no better than doing nothing", r)
    assert r["heckman"] < 0.7 * r["heckman_mills_carried_into_predict"], (
        "zeroing λ at predict is the entire correction and must show a large gap", r)


@pytest.mark.parametrize("side_name", sorted(SIDES))
def test_every_metric_has_a_shipped_baseline_that_resolves_to_a_REAL_rung(side_name):
    """A silent fallback to `ContextSpec()` here would re-report the slice-1 park/run-env win as an S2
    survivorship win — the most flattering way this slice could lie."""
    side = SIDES[side_name]
    for m in side.metrics:
        assert m in SHIPPED_RUNG[side_name], f"{side_name}/{m} has no recorded shipped rung"
        shipped_spec(side, m)          # raises if the label is not on the live ladder


def test_a_stale_shipped_label_RAISES_rather_than_falling_back_to_the_bare_incumbent():
    side = SIDES["batter"]
    SHIPPED_RUNG["batter"]["__probe__"] = "S99_does_not_exist"
    try:
        with pytest.raises(KeyError, match="not a rung on the current ladder"):
            shipped_spec(side, "__probe__")
    finally:
        SHIPPED_RUNG["batter"].pop("__probe__")


def test_the_shipped_baselines_match_the_PUBLISHED_slice1_verdicts():
    """Transcription guard — these came off the published slice-1/1p reports by hand, and a typo would
    quietly change what S2 is measured against."""
    assert SHIPPED_RUNG["batter"] == {
        "woba": "S2_level_env", "k_pct": "S4_park_env_rel0.5",
        "bb_pct": "S4_park_env_rel2.0", "iso": "S4_park_env_rel2.0"}
    assert SHIPPED_RUNG["pitcher"]["bb_pct"] == "S5_full_labelweight"
    assert SHIPPED_RUNG["pitcher"]["hr_rate"] == "S5_full_labelweight"
    # the three pitcher DROPs ship the byte-exact E7.3 incumbent
    for m in ("k_pct", "gb_pct", "xwoba_against"):
        assert SHIPPED_RUNG["pitcher"][m] == "S0_baseline"
        assert shipped_spec(SIDES["pitcher"], m).is_noop
