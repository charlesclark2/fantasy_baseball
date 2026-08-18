"""NF-W7i guards — the RB direct-points CEILING gate.

Every clause below has an ISOLATING fixture: the other clauses of its `and`-gate are SATISFIED so
only the clause under test can flip the result (NF-D17 — a fixture that trips a second clause
proves neither). The companion RED proof
(`quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w7i.py`) breaks the source for each
clause and asserts the guard goes RED, with the mutation asserted to LAND, the asserted token
asserted GONE, and the anchor asserted UNIQUE.

⛔ Fast gate: this module imports only `betting_ml` + the fantasy package, never `pipeline`
(E11.23 — `pipeline/__init__` reads the dbt manifest, absent in the fast gate).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import direct_points_ceiling as DC
from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW

_MODULE = Path(DC.__file__)
_RUNNER = _MODULE.with_name("run_nf_w7i_direct_ceiling.py")


def _src(path: Path) -> str:
    """Source with COMMENTS and DOCSTRINGS stripped — prose must never satisfy a source guard
    (INC-38: a comment naming the flag made the pre-fix source pass)."""
    text = path.read_text()
    tree = ast.parse(text)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                docs.add(d)
    out = re.sub(r"(?m)^\s*#.*$", "", text)
    for d in docs:
        out = out.replace(d, "")
    return out


# ── Fixtures: a synthetic fold field where every label is present and controllable ──────────────
def _fold(label: str, *, inc: float, oracle: dict[str, float], matched: dict[str, float],
          n: int = 1000) -> dict:
    scores = {DC.INCUMBENT: inc}
    for f in DC.ORACLE_FORMS:
        scores[f"oracle__{f}"] = oracle[f]
        scores[f"matched_n__{f}"] = matched[f]
    # degenerates + permutation always LOSE unless a test overrides them
    for d in DC.DEGENERATES:
        scores[d] = inc + 5.0
    scores[DC.PERMUTATION] = inc + 3.0
    return {"label": label, "n": n, "scores": scores}


def _field(ceiling_pct: float, *, n_folds: int = 8, active: bool = True,
           jitter: float = 0.0) -> list[dict]:
    """A field in which `direct_augmented` carries `ceiling_pct` and is ACTIVE (its peek beats its
    own matched-n control) — every OTHER clause satisfied, so one clause at a time can be tested."""
    inc = 2.5
    orc = inc * (1.0 - ceiling_pct / 100.0)
    folds = []
    for i in range(n_folds):
        j = jitter * (1 if i % 2 == 0 else -1)
        oracle = {f: inc + 1.0 for f in DC.ORACLE_FORMS}
        # every OTHER form: active by default (peek beats its own control) but with a negative
        # ceiling, so it can never win the headline max on magnitude
        matched = {f: inc + (2.0 if active else 0.5) for f in DC.ORACLE_FORMS}
        oracle["direct_augmented"] = orc + j
        # ACTIVE ⇒ the peek BEATS its own control; INACTIVE ⇒ it does not
        matched["direct_augmented"] = (orc + j + 0.10) if active else (orc + j - 0.10)
        folds.append(_fold(f"F{i}", inc=inc, oracle=oracle, matched=matched))
    return folds


def _decide(folds: list[dict]) -> tuple[dict, dict]:
    sel = DC.select_ceiling(folds, len(folds))
    fdr = DC.bh_binding(sel["per_form"])
    return sel, DC.decide(sel, fdr)


# ── 1. The cross-fit peek — the defect this whole story corrects ────────────────────────────────
def test_the_peek_is_cross_fit_so_no_row_can_see_its_own_label():
    """NF-W7h's `oracle__foil_direct_points` was `fit_direct_points(te_p, te_p)` — an in-sample
    memorisation degenerate. Every peek here must route through `EM.crossfit_ids`, which REFUSES
    K < 2 ('a 1-fold cross-fit is an in-sample fit')."""
    src = _src(_MODULE)
    assert "EM.crossfit_ids" in src, "the peek must delegate to the K-refusing cross-fit helper"
    with pytest.raises(ValueError, match="in-sample"):
        EM.crossfit_ids(100, 1, "F0", "tag")
    ids = DC._ids(90, "F0", "t")
    assert set(np.unique(ids)) == set(range(DC.CROSSFIT_K)) and DC.CROSSFIT_K >= 2


def test_no_declared_peek_is_an_in_sample_fit_on_the_block():
    """The block-only peek must never fit and predict the SAME rows."""
    calls: list[tuple[int, int]] = []
    test = pd.DataFrame({"gw": np.arange(300), "x": np.arange(300.0),
                         DC.__name__ and "league_fantasy_points": np.arange(300.0)})
    orig = DC.fit_direct
    try:
        DC.fit_direct = lambda tr, te, feats, **kw: (  # noqa: ARG005
            calls.append((len(tr), len(te))) or np.zeros((len(te), DC.N_LEVELS)))
        DC.oracle_blockonly(test, ["x"], "F0")
    finally:
        DC.fit_direct = orig
    assert calls, "the peek made no fit — a vacuous check (NF1.7 (a))"
    for n_tr, n_te in calls:
        assert n_tr + n_te == len(test), "cross-fit leaves must partition the block"
        assert n_te < len(test), "a leaf predicted the WHOLE block — that is an in-sample peek"


# ── 2. Matched-n sizing — same-family AND same-sample (NF1.7 (b) / NF-W6b-C) ────────────────────
def test_matched_window_is_sized_to_the_peeks_effective_n_not_the_full_block():
    train = pd.DataFrame({"gw": np.arange(5000), "v": np.arange(5000.0)})
    test = pd.DataFrame({"gw": np.arange(900), "v": np.arange(900.0)})
    got = len(DC.matched_window(train, test))
    assert got == 600, f"expected ceil(900·2/3)=600 effective rows, got {got}"
    assert got != len(GE.matched_n_train(train, test)), (
        "the control was sized like the FULL block — that hands the control ~1.5× the rows the "
        "cross-fit peek trains on (NF-W6b-C's false near-tie)")


def test_the_augmented_control_never_uses_a_single_test_row():
    """The honest control must replace the peeked block with TRAIN rows — if it reached into the
    test block it would be a second peek, and the attribution would be vacuous."""
    seen: list[pd.DataFrame] = []
    orig = DC._augmented
    try:
        DC._augmented = lambda tr, te, extra, feats, lam, hold: (  # noqa: ARG005
            seen.append(extra) or np.zeros((int(hold.sum()), DC.N_LEVELS)))
        train = pd.DataFrame({"gw": np.arange(4000), "tag": ["train"] * 4000})
        test = pd.DataFrame({"gw": np.arange(300), "tag": ["TEST"] * 300})
        DC.matched_augmented(train, test, ["gw"], "F0", 1.0, "direct_augmented")
    finally:
        DC._augmented = orig
    assert seen, "no augmented leaf ran — vacuous"
    for extra in seen:
        assert set(extra["tag"]) == {"train"}, "the matched control peeked at the TEST block"


# ── 3. Activity before magnitude (NF-W6d / NF-D20) ──────────────────────────────────────────────
def test_an_inactive_form_cannot_carry_the_headline_however_large_its_ceiling():
    """The isolating fixture gives the INACTIVE form a HUGE ceiling and satisfies every other
    clause — so only the activity rule can keep it out of the headline."""
    folds = _field(40.0, active=False)
    sel, dec = _decide(folds)
    assert sel["per_form"]["direct_augmented"]["activity"] == "INACTIVE"
    assert sel["best_form"] != "direct_augmented", (
        "a peek that loses to its own matched-n control was read as a 40% ceiling")


def test_no_active_form_is_UNEVALUABLE_and_is_never_reported_as_a_NO():
    folds = _field(40.0, active=False)
    sel, dec = _decide(folds)
    assert sel["active_forms"] == [] and sel["ceiling_pct"] is None
    assert dec["answer"] == "UNEVALUABLE", (
        "every anchor pair INACTIVE must be UNEVALUABLE — reporting it as a NO would claim RB has "
        "no headroom on the strength of a check that could not run (NF1.7 (a))")
    assert dec["licensed_for_bakeoff"] is False
    assert "NOT a finding that RB has no headroom" in dec["reason"]


def test_the_block_only_peek_being_negative_is_not_by_itself_a_verdict():
    """The measured shape: block-only is INACTIVE/negative while an augmented form is ACTIVE — the
    headline must come from the ACTIVE form, not from the starved one."""
    folds = _field(3.0, active=True)
    for fr in folds:                      # block-only: starved, worse than the arm AND its control
        fr["scores"]["oracle__direct_blockonly"] = 3.2
        fr["scores"]["matched_n__direct_blockonly"] = 3.1
    sel, _ = _decide(folds)
    assert sel["per_form"]["direct_blockonly"]["activity"] == "INACTIVE"
    assert sel["best_form"] == "direct_augmented"


# ── 4. The bands — one isolating fixture per band (every other clause satisfied) ────────────────
@pytest.mark.parametrize("pct,expected", [(0.5, "NO"), (1.9, "NO"), (3.0, "MARGINAL"),
                                          (7.0, "YES")])
def test_the_bands_decide_the_answer(pct, expected):
    sel, dec = _decide(_field(pct))
    assert dec["stat_ok"] is True, "the fixture must satisfy every OTHER clause (NF-D17)"
    assert dec["answer"] == expected, f"ceiling {sel['ceiling_pct']}% → {dec['answer']}"


def test_a_demonstrable_but_immaterial_ceiling_is_refused():
    """NF-W6's 'demonstrable ≠ material': a tiny ceiling that clears every statistical clause is
    still a NO — the four TD-NO cells at 0.07–0.38% were real and correctly refused."""
    sel, dec = _decide(_field(0.4))
    assert dec["stat_ok"] is True and dec["answer"] == "NO"
    assert dec["licensed_for_bakeoff"] is False
    assert "IMMATERIAL" in dec["reason"]


def test_bands_are_imported_from_the_nf_w6_gate_not_redeclared():
    assert DC.CEILING_BANDS is EM.CEILING_BANDS == (2.0, 5.0)


# ── 5. stat_ok — one isolating fixture per clause (NF-D17) ──────────────────────────────────────
def test_a_ceiling_whose_interval_spans_zero_is_a_NO_however_large():
    folds = _field(7.0, jitter=6.0)        # huge fold-to-fold swing ⇒ CI spans zero
    sel, dec = _decide(folds)
    assert sel["ci95"][0] is not None and sel["ci95"][0] <= 0
    assert dec["answer"] == "NO" and dec["stat_ok"] is False


def test_a_ceiling_failing_the_fold_consistency_clause_is_a_NO():
    folds = _field(7.0)
    for fr in folds[:5]:                   # flip most folds so the win count fails the clause
        fr["scores"]["oracle__direct_augmented"] = fr["scores"][DC.INCUMBENT] + 0.5
        fr["scores"]["matched_n__direct_augmented"] = fr["scores"][DC.INCUMBENT] + 0.6
    sel, dec = _decide(folds)
    assert sel["fold_clause"]["passes"] is False
    assert dec["answer"] == "NO" and dec["stat_ok"] is False


def test_bh_runs_over_the_declared_form_family_because_the_headline_is_a_max_over_it():
    sel, _ = _decide(_field(7.0))
    fdr = DC.bh_binding(sel["per_form"])
    assert fdr["family_size"] == len(DC.ORACLE_FORMS) == 5, (
        "BH must spend the multiplicity the MAX-over-forms selection actually costs (MH2 (a))")


# ── 6. Refusals — a check that could not run is never a pass (NF1.7 (a)) ────────────────────────
def test_a_thin_bank_refuses_rather_than_defaulting():
    with pytest.raises(ValueError, match="REFUSED"):
        DC._bank(np.arange(DC.MIN_BANK_ROWS - 1, dtype=float))
    assert DC._bank(np.arange(DC.MIN_BANK_ROWS, dtype=float)).shape == (DC.N_LEVELS,)


def test_an_incomplete_declared_field_refuses():
    folds = _field(3.0)
    del folds[0]["scores"][DC.PERMUTATION]
    with pytest.raises(ValueError, match="REFUSED"):
        DC.select_ceiling(folds, len(folds))


def test_select_refuses_a_field_with_no_scored_fold():
    with pytest.raises(ValueError, match="REFUSED"):
        DC.select_ceiling([{"label": "F0", "skipped": "thin"}], 0)


# ── 7. The pre-registered SCOPE guard: RB gets no season/fold re-test trigger ───────────────────
@pytest.mark.parametrize("pct,jitter,corrected", [(0.5, 0.0, True), (6.0, 0.5, False)])
def test_rb_is_never_given_a_season_or_fold_retest_trigger(pct, jitter, corrected):
    """NF-W7h measured RB's DSR as variance-bound and unreachable at any n. A 'come back with more
    seasons' trigger is the misleading direction NF-D18 / MH2 (g″) forbid.

    ⛔ BOTH branches are exercised — the hand-corrected one AND the raw `classify_null` one. The
    hand-correction sets its own `retest_trigger`, so a fixture that only ever reaches the
    corrected branch would leave the raw path's suppression untested (it went vacuous exactly this
    way when the correction was added, and the RED proof caught it).
    """
    sel, dec = _decide(_field(pct, jitter=jitter))
    ns = DC.null_state(sel, dec, n_folds=8)
    assert bool(ns.get("hand_corrected")) is corrected, "fixture did not reach the intended branch"
    assert ns["retest_trigger"] is None
    assert "NO season/fold re-test trigger" in ns["retest_trigger_note"]
    assert "field_remedy_admissible" in ns, "MH2.7: read the machine flag, never the prose"


def test_a_negative_ceiling_is_never_reported_as_beating_its_foil():
    """`bool(x or 0 > 0)` parses as `bool(x or (0 > 0))` — TRUE for a NEGATIVE delta. That would
    hand `classify_null` a beats_foil it did not earn and invert the null state."""
    folds = _field(3.0)
    for fr in folds:                       # every active form now scores WORSE than the incumbent
        for f in DC.ORACLE_FORMS:
            fr["scores"][f"oracle__{f}"] = fr["scores"][DC.INCUMBENT] + 0.4
            fr["scores"][f"matched_n__{f}"] = fr["scores"][DC.INCUMBENT] + 0.9
    sel, dec = _decide(folds)
    assert sel["mean_delta"] is not None and sel["mean_delta"] < 0
    ns = DC.null_state(sel, dec, n_folds=len(folds))
    assert ns["state"] == "GENUINE_ABSENCE", (
        f"a negative ceiling classified as {ns['state']} — a negative point estimate is not "
        "rescued by n (NF-D15 (g\u2033))")


def test_a_ceiling_whose_whole_interval_is_below_the_band_is_not_power_limited():
    """`classify_null` answers 'is the effect > 0?' and, with no detectability figure, FALLS
    THROUGH to POWER_LIMITED. This story asks 'is the ceiling ≥ the materiality band?' — and when
    the whole 95% interval lies BELOW that band the evidence is DECISIVE, not thin. Publishing
    POWER_LIMITED would read as 'buy more seasons' for a bar the data already exclude (NF-D18 /
    MH2 (g″)).

    The fixture puts a TIGHT interval far below the band, so only the band comparison can decide.
    """
    sel, dec = _decide(_field(0.2, jitter=0.005))
    hi = sel["ceiling_ci_pct"][1]
    assert hi is not None and hi < DC.CEILING_BANDS[0], "fixture must sit wholly below the band"
    ns = DC.null_state(sel, dec, n_folds=8)
    assert ns["state"] == "MEASURED_IMMATERIAL", (
        f"a ceiling whose whole interval is below the band classified as {ns['state']}")
    assert ns["retest_trigger"] is None
    assert "never more data" in ns["remedy"]


def test_the_hand_correction_retains_the_instruments_raw_verdict():
    """NF-D20: correcting an instrument's misclassification must never DESTROY what it said."""
    sel, dec = _decide(_field(0.2, jitter=0.005))
    ns = DC.null_state(sel, dec, n_folds=8)
    assert ns["hand_corrected"] is True and ns["corrected_from"]
    assert ns["classify_null_raw"]["state"] == ns["corrected_from"], (
        "the raw classify_null verdict must be retained verbatim, not overwritten")


def test_the_hand_correction_never_swallows_a_decisive_state():
    """A NEGATIVE point estimate is GENUINE_ABSENCE, which MH2 ranks ABOVE the power states because
    no n rescues it. That is strictly more informative than 'immaterial' and must survive."""
    folds = _field(3.0)
    for fr in folds:                       # drive every active form BELOW the incumbent
        for f in DC.ORACLE_FORMS:
            fr["scores"][f"oracle__{f}"] = fr["scores"][DC.INCUMBENT] + 0.4
            fr["scores"][f"matched_n__{f}"] = fr["scores"][DC.INCUMBENT] + 0.9
    sel, dec = _decide(folds)
    assert sel["ceiling_ci_pct"][1] < DC.CEILING_BANDS[0], "fixture is below the band"
    ns = DC.null_state(sel, dec, n_folds=len(folds))
    assert ns["state"] == "GENUINE_ABSENCE" and ns.get("hand_corrected") is not True, (
        f"the correction swallowed a decisive state → {ns['state']}")


def test_a_ceiling_reaching_the_band_is_left_to_the_instrument():
    """The correction must be NARROW: it fires only when the interval excludes the band. A ceiling
    that could still be material keeps whatever classify_null said."""
    sel, dec = _decide(_field(6.0, jitter=0.5))
    hi = sel["ceiling_ci_pct"][1]
    assert hi is not None and hi >= DC.CEILING_BANDS[0], "fixture must reach the band"
    ns = DC.null_state(sel, dec, n_folds=8)
    assert ns.get("hand_corrected") is not True, (
        "the hand-correction fired on a ceiling that could still be material")


def test_classify_null_is_given_the_declared_field_size():
    src = _src(_MODULE)
    assert "declared_field_size=len(ORACLE_FORMS)" in src.replace(" ", ""), (
        "MH2.7: classify_null must be told the DECLARED field or its remedy can prescribe a field "
        "below the declared minimum")


# ── 8. Same-family: the weighted fit differs from the incumbent ONLY by the weight ──────────────
def test_the_unweighted_path_delegates_to_the_predecessors_object_by_identity():
    src = _src(_MODULE)
    assert "KW.fit_direct_points(train, test, features" in src, (
        "the incumbent must BE NF-W7h's object, not a re-implementation that could drift")


def test_the_weighted_fit_keeps_the_incumbents_hyperparameters_byte_identical():
    inc = re.search(r"def fit_count_lgbm.*?tail = ", KW.__loader__.get_source(KW.__name__),
                    re.S).group(0)
    mine = re.search(r"def fit_direct\(.*?tail = ", _MODULE.read_text(), re.S).group(0)
    for token in ('"objective": "quantile"', '"n_estimators": 200', '"num_leaves": 31',
                  '"min_child_samples": 30'):
        assert token in inc and token in mine, f"{token} drifted between the arm and its peek"


def test_the_weighted_fit_refuses_a_mismatched_weight_vector():
    df = pd.DataFrame({"gw": np.arange(60), "x": np.arange(60.0),
                       "league_fantasy_points": np.arange(60.0)})
    with pytest.raises(ValueError, match="REFUSED"):
        DC.fit_direct(df, df, ["x"], sample_weight=np.ones(5))


# ── 9. Metric hygiene + deploy-held ────────────────────────────────────────────────────────────
def test_no_mae_anywhere_on_a_zero_heavy_target():
    """NF-D11/D14: RB's realised all-zero rate is 0.3359 — MAE is minimised at the conditional
    median, exactly where it pays for pessimism."""
    for path in (_MODULE, _RUNNER):
        src = _src(path).lower()
        assert not re.search(r"\bmean_absolute_error\b|\bmae\b", src), f"MAE reached {path.name}"


def test_the_story_is_deploy_held_and_writes_no_serving_surface():
    for path in (_MODULE, _RUNNER):
        src = _src(path)
        for token in ("--publish", "boto3", "put_object", "s3://", "sub_model_registry",
                      "deploy.sh", "write_serving_store"):
            assert token not in src, f"{path.name} reaches a serving surface via {token!r}"


def test_the_positive_control_is_wired_and_fails_the_smoke_when_blind():
    src = _src(_RUNNER)
    assert "POSITIVE_CONTROL_MIN_ABS_GROWTH" in src
    assert "raise AssertionError" in src, (
        "a blind instrument must REFUSE the smoke, not report a ceiling it cannot see")
    assert "positive_control=True" in src


def test_the_failed_original_control_clause_is_retained_and_still_scored():
    """NF-D20: a pre-registered anchor that FAILS is left failing and DECOMPOSED, never deleted or
    re-labelled. The amendment changed which STATISTIC gates; it must not erase the original."""
    src = _src(_RUNNER)
    assert "POSITIVE_CONTROL_MIN_MOVE_PCT" in src, "the original clause was deleted, not retained"
    # ⛔ the KEY the payload is written under — not a loose substring, which the report writer's
    # own `pc['legacy_clause']` reference would satisfy even with the payload key renamed away
    assert '"legacy_clause": {' in src, (
        "the original clause must still be SCORED into the artifact, not merely referenced")
    assert '"measured_move_pct": move' in src


def test_the_control_gates_on_the_absolute_advantage_not_the_ratio():
    """A multiplicative shift inflates the incumbent CRPS that is the relative ceiling's
    DENOMINATOR, so reading sensitivity on that ratio understates it by construction.

    ⛔ Asserts the GATING EXPRESSION itself, not that the words appear somewhere in the file — the
    reported payload carries `abs_growth`/`ceiling_widened` regardless of what actually gates.
    """
    src = _src(_RUNNER)
    gate = re.search(r"^\s*passes = .*$", src, re.M)
    assert gate, "no `passes = …` gating assignment found"
    expr = gate.group(0)
    assert "growth" in expr and "MIN_ABS_GROWTH" in expr, (
        f"the control gates on {expr.strip()!r} — sensitivity must be read on the ABSOLUTE peek "
        "advantage, not the ratio the shift itself inflates")
    assert "widened" in expr, (
        "the amended clause must be TWO-SIDED — a regime difference must WIDEN a ceiling")


def test_the_control_writes_its_evidence_before_it_raises():
    """INC-43 salvage: a refusal that destroys its own evidence forces the next session to re-run a
    14-minute job to learn why.

    ⛔ Scoped to the SMOKE block. A file-wide index comparison is vacuous — `--rewrite-report`
    writes a report near the top of `main`, so the naive check passes with the smoke block's write
    deleted outright.
    """
    src = _src(_RUNNER)
    block = src[src.index("if args.smoke:", src.index("def main(")):]
    raise_at = block.index("if not passes:")
    assert "write_report(" in block[:raise_at], (
        "the smoke block raises WITHOUT writing its evidence first — the next session would have "
        "to re-run the whole job to learn why the control failed")


def test_the_runner_records_the_premise_correction_it_is_built_on():
    """The 1.4933 figure must be recorded AS an in-sample degenerate, so a later reader cannot
    re-import it as a ceiling."""
    src = _RUNNER.read_text()
    assert "1.4933" in src and "premise_correction" in _src(_RUNNER)
    assert "fit_direct_points(te_p, te_p" in src
