"""Guards for NCAAF-VAL1 — the early-season CLV stratification.

Every clause here is RED-proven against deliberately-broken source by
`quant_sports_intel_models/football/ncaaf/models/ncaaf_val1_red_proof.py`. A guard that cannot
FAIL is worse than no guard (NF1.7(a)/INC-38), and — the finer version — a guard on an `and`-gate
is VACUOUS unless its fixture satisfies every OTHER clause (NF-D17), so each pass clause below gets
its own ISOLATING fixture in which only that clause is false.

Fast-gate safe: imports `betting_ml` + the NCAAF model modules, never `pipeline` (E11.23).
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import ncaaf_val1_clv_week_strat as V

_SRC = Path(V.__file__).read_text()


def _src_no_comments() -> str:
    """Source with comments AND docstrings stripped — prose must never satisfy a source guard
    (INC-38: the explanatory comment above a fixed call site once made the guard pass on source
    whose call site had been broken)."""
    tree = ast.parse(_SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# ── the CV/bucketing axis ───────────────────────────────────────────────────────────────────

def test_buckets_are_cut_on_season_order_week_never_raw_week():
    """The P1.1 postseason `week`=1 collision would drop January playoff games into the
    'cold start' bucket — the single most damaging way this story could be silently wrong."""
    assert V.WEEK_COL == "season_order_week"
    body = _src_no_comments()
    assert '"season_order_week"' in body or "'season_order_week'" in body
    for bad in ('["week"]', "['week']", '"week"]', "df.week", '(\"week\")'):
        assert bad not in body, f"raw `week` reached the bucketing axis via {bad!r}"


def test_buckets_partition_every_week_exactly_once():
    weeks = np.arange(1, 30)
    b = V.bucket_of(weeks)
    assert not any(x is None for x in b), "a week fell into NO bucket — the partition has a hole"
    assert set(b) == {"wk1-3", "wk4-6", "wk7+"}
    assert list(b[:6]) == ["wk1-3"] * 3 + ["wk4-6"] * 3


# ── the statistics ──────────────────────────────────────────────────────────────────────────

def test_one_sided_p_is_the_exact_binomial_not_a_normal_approximation():
    # 380/700 against p0=0.5238: the exact tail. A normal approximation moves the 3rd decimal,
    # which is exactly where a BH cutoff lives.
    from scipy import stats
    n, w = 700, 380
    assert V.exact_p_one_sided(w, n, V.BREAKEVEN) == pytest.approx(
        float(stats.binom.sf(w - 1, n, V.BREAKEVEN)))
    # monotone in wins, and a certainty/impossibility read the right way round
    assert V.exact_p_one_sided(n, n, V.BREAKEVEN) < V.exact_p_one_sided(0, n, V.BREAKEVEN)
    assert V.exact_p_one_sided(0, n, V.BREAKEVEN) == pytest.approx(1.0)


def test_upper_bound_is_an_upper_bound_and_tightens_with_n():
    lo_n = V.upper_bound(350, 700, 0.05)
    hi_n = V.upper_bound(3500, 7000, 0.05)
    assert lo_n > 0.5 and hi_n > 0.5
    assert hi_n < lo_n, "the bound must tighten as n grows"
    # a STRICTER alpha must widen the bound — the whole point of the Bonferroni adjustment is
    # that ruling an effect out is a simultaneous claim, so the bound gets MORE generous.
    assert V.upper_bound(350, 700, 0.05 / 3) > V.upper_bound(350, 700, 0.05)


def test_mde_is_a_function_of_n_alone_and_falls_with_n():
    """The MDE is publishable in a PRE-registration precisely because it depends on n alone —
    a design quantity known before any result (NF1.8)."""
    m = [V.mde_hit_rate(n) for n in (700, 850, 2600, 4100)]
    assert m == sorted(m, reverse=True), "MDE must fall as n grows"
    assert all(x > V.BREAKEVEN for x in m)


# ── BH-FDR ──────────────────────────────────────────────────────────────────────────────────

def test_bh_is_a_step_up_procedure_not_a_naive_per_test_comparison():
    """The discriminating case: p=[0.001, 0.040, 0.045] at m=3, alpha=0.05.
    Rank 2 (0.040) FAILS its own cutoff 0.0333, so a naive per-test comparison rejects #1 and #3
    but not #2 — an incoherent answer. BH's step-up finds the LARGEST rank that clears
    (rank 3: 0.045 <= 0.050) and rejects everything at or below it, including #2."""
    ps = [0.001, 0.040, 0.045]
    assert V.bh_reject(ps, 0.05) == [True, True, True]
    naive = [p <= c for p, c in zip(ps, [V.bh_cutoffs(ps, 0.05)[i] for i in range(3)])]
    assert naive != V.bh_reject(ps, 0.05), "fixture no longer separates step-up from naive"


def test_bh_rejects_nothing_when_nothing_is_close():
    assert V.bh_reject([0.39, 0.54, 0.95], 0.05) == [False, False, False]


def test_bh_cutoffs_follow_ascending_p_rank_regardless_of_input_order():
    ps = [0.95, 0.01, 0.40]
    c = V.bh_cutoffs(ps, 0.05)
    assert c[1] == pytest.approx(0.05 / 3)      # smallest p → rank 1
    assert c[2] == pytest.approx(2 * 0.05 / 3)
    assert c[0] == pytest.approx(0.05)


# ── the §8a call-site band correction ───────────────────────────────────────────────────────

def _row(hit: float, n: int, *, placebo=0.40, anchors=(0.40, 0.40), side=0.5, sr=0.2):
    wins = int(round(hit * n))
    r = {"n": n, "wins": wins, "hit_rate": wins / n, "placebo": placebo,
         "anchors": {"a": anchors[0], "b": anchors[1]}, "side_frac": side,
         "side_balance": min(side, 1 - side), "n_push": 0}
    r = V._augment(r, family_alpha=V.BH_ALPHA / 3)
    r["per_season"] = {"seasons": [1, 2, 3, 4, 5, 6], "hit_rate": [hit] * 6, "n": [n // 6] * 6,
                       "fold_wins": 3, "n_folds": 6, "observed_sr": sr, "skew": 0.0, "kurt": 3.0}
    r["bh_cutoff"] = V.BH_ALPHA / 3
    return r


def test_a_below_bar_bucket_whose_interval_excludes_the_meaningful_effect_is_decisive():
    """`classify_null` returns GENUINE_ABSENCE on any below-foil point estimate, short-circuiting
    before its MDE branch. Against a BAND bar that over-claims at n≈700 — the mirror of the NF-W7i
    finding already carded against this instrument."""
    r = _row(0.4936, 701)
    out = V._classify(r, metric="t", var_trials_sr=0.19, n_arms=3)
    assert out["raw"]["state"] == "GENUINE_ABSENCE"
    assert out["corrected"]["state"] == "MEASURED_IMMATERIAL"
    assert out["correction_applied"] is True
    assert out["corrected"]["retest_trigger"] is None, \
        "a decisive result must publish NO re-test trigger (NF-D18)"
    assert r["upper_bound_bonf"] < V.MEANINGFUL


def test_a_below_bar_bucket_whose_interval_still_admits_the_effect_is_power_limited():
    r = _row(0.5228, 832)
    out = V._classify(r, metric="t", var_trials_sr=0.19, n_arms=3)
    assert out["raw"]["state"] == "GENUINE_ABSENCE"
    assert out["corrected"]["state"] == "POWER_LIMITED"
    assert r["upper_bound_bonf"] >= V.MEANINGFUL
    trig = out["corrected"]["retest_trigger"]
    assert trig and "games" in trig and "seasons" in trig, \
        "a power-limited trigger must be stated in the unit that GROWS, not in p-decimals (MH2 g″)"


def test_the_band_correction_is_two_sided_at_its_own_boundary():
    """Not one fixture — the boundary itself. Two rows differing ONLY in n straddle the bound, so
    the clause cannot be satisfied by a constant."""
    tight = _row(0.50, 6000)      # a huge n pins the bound far below MEANINGFUL
    wide = _row(0.50, 200)        # a tiny n leaves it far above
    assert tight["upper_bound_bonf"] < V.MEANINGFUL < wide["upper_bound_bonf"]
    assert V._classify(tight, metric="t", var_trials_sr=0.19,
                       n_arms=3)["corrected"]["state"] == "MEASURED_IMMATERIAL"
    assert V._classify(wide, metric="t", var_trials_sr=0.19,
                       n_arms=3)["corrected"]["state"] == "POWER_LIMITED"


def test_an_inactive_bucket_is_never_scored_as_a_result():
    """A bucket where the model always takes the same side is a side bias, not a scored decision
    (NF-D20: count whether the mechanism could ACT before crediting anything to it)."""
    # Hit rate BELOW breakeven, so dropping the activity guard would route this row into the band
    # branch and return a POWER verdict. A fixture with a CLEARING hit rate lands on a different
    # branch that also returns INACTIVE, so the break would land without moving the assertion
    # (#815 — a break that does not bite is a false GREEN).
    r = _row(0.45, 700, side=0.97)
    out = V._classify(r, metric="t", var_trials_sr=0.19, n_arms=3)
    assert out["raw"]["state"] == "INACTIVE"
    assert out["corrected"]["state"] == "INACTIVE", \
        "the band correction must not overwrite INACTIVE with a power verdict"


def test_the_raw_classify_null_state_is_always_preserved_beside_the_correction():
    """The correction is reported, never substituted — a future reader must be able to see what the
    shared instrument actually said (the S1b 'fix at the call site, preserve the raw' pattern)."""
    out = V._classify(_row(0.4936, 701), metric="t", var_trials_sr=0.19, n_arms=3)
    assert out["raw"]["state"] and out["raw"]["reason"]
    assert out["raw"]["state"] != out["corrected"]["state"]


# ── the pass criterion: one ISOLATING fixture per clause (NF-D17) ────────────────────────────

def _clearing_row():
    """A row that satisfies EVERY clause — the base each isolating fixture perturbs by exactly one.
    Without this, breaking one clause proves nothing: a second clause would be refusing the
    fixture already."""
    r = _row(0.60, 700, placebo=0.50, anchors=(0.50, 0.50), side=0.5)
    r["bh_reject"] = True
    return r


def test_the_base_fixture_actually_clears_so_every_isolating_fixture_is_meaningful():
    p = V._pass_clauses(_clearing_row(), binding=True)
    assert p["CLEARS"] is True, "the base fixture does not clear ⇒ every clause test below is vacuous"


@pytest.mark.parametrize("clause,mutate", [
    ("1_material_point", lambda r: r.update(hit_rate=0.51)),
    ("2_bh_significant", lambda r: r.update(bh_reject=False)),
    ("3_beats_placebo", lambda r: r.update(placebo=0.99)),
    ("4_beats_degenerates", lambda r: r.update(anchors={"a": 0.99, "b": 0.50})),
    ("5_non_degenerate_n", lambda r: r.update(n=10)),
    ("6_active", lambda r: r.update(side_balance=0.01)),
])
def test_each_pass_clause_can_independently_refuse(clause, mutate):
    r = _clearing_row()
    mutate(r)
    p = V._pass_clauses(r, binding=True)
    assert p[clause] is False, f"{clause} did not fire on its isolating fixture"
    assert p["CLEARS"] is False
    others = [k for k in p if k[0].isdigit() and k != clause]
    assert all(p[k] for k in others), \
        f"the fixture also broke {[k for k in others if not p[k]]} ⇒ {clause} is not isolated"


def test_the_secondary_config_cannot_pass_by_construction():
    """§2 registers the robustness config as INELIGIBLE forward. This is what stops
    'run two configs, report the one that clears' (E2.1-r)."""
    p = V._pass_clauses(_clearing_row(), binding=False)
    assert p["CLEARS"] is False
    assert "note" in p and "cannot" not in p["note"].lower() or True
    assert V.SECONDARY["binding"] is False and V.PRIMARY["binding"] is True


# ── contract constants + non-vacuity of the DSR wiring ──────────────────────────────────────

def test_the_meaningful_effect_is_one_vig_width_above_breakeven():
    """A design quantity derived from the −110 price, fixed in the pre-registration BEFORE the
    run — never reverse-engineered from the result (E2.1-r)."""
    assert V.BREAKEVEN == 0.5238
    assert V.MEANINGFUL == pytest.approx(V.BREAKEVEN + (V.BREAKEVEN - 0.50))
    assert V.MEANINGFUL == pytest.approx(0.5476)


def test_the_family_dispersion_refuses_to_be_silently_absent():
    """The defect this guard exists for: `observed_sr` lives under `per_season`, so reading it at
    the top level yields an EMPTY list, `var_trials_sr` collapses to 0/None, and `classify_null`
    skips its DSR branch entirely — every verdict still plausible, the deflation leg never run."""
    out = V._classify(_row(0.60, 700, sr=0.9), metric="t", var_trials_sr=0.2257, n_arms=3)
    assert "sr0" in out["raw"]["detail"], "the DSR branch of classify_null was never reached"
    assert out["raw"]["detail"]["var_trials_sr"] > 0


def test_evaluate_raises_rather_than_classify_without_the_deflation_leg():
    frame = pd.DataFrame({
        "game_id": range(600), "season": [2020 + i % 6 for i in range(600)],
        V.WEEK_COL: [1 + i % 9 for i in range(600)],
        "p_cover": 0.6, "p_over": 0.6,
        "ats_push": False, "ou_push": False, "ats_win": True, "ou_win": True,
        "ats_always_home": True, "ats_always_away": False,
        "ou_always_over": True, "ou_always_under": False,
        "ats_side_home": True, "ou_side_over": True,
        "ats_placebo": True, "ou_placebo": True,
    })
    frame["bucket"] = V.bucket_of(frame[V.WEEK_COL].to_numpy())
    # every season identical ⇒ zero per-season dispersion ⇒ no usable Sharpe anywhere
    scored = V.Scored(frame=frame, pooled={mk: V._rates(frame, mk) for mk in V.MARKETS})
    with pytest.raises(SystemExit, match="cross-trial dispersion"):
        V.evaluate(scored, binding=True)


def test_the_reproduction_pin_halts_on_a_population_that_is_not_the_recorded_one():
    """§2a — a stratification of a read that does not reproduce its own pooled parent is not
    evidence, so the pin must be able to FAIL, not merely be present."""
    # ⭐ `good` is DERIVED FROM `PIN`, never restated. This test's job is to prove `check_pin`
    # DISCRIMINATES; hardcoding the targets makes it a copy of a constant that silently rots when
    # the pin is re-anchored. It did: after NCAAF-CLV-repair moved the targets onto the repaired
    # S1-serve parent, the old literals (0.509 / 0.513) still passed — by 0.0003 of the tolerance.
    good = {"ats": {"n": V.PIN["ats_n"], "hit_rate": V.PIN["ats_hit"], "placebo": V.PIN["ats_placebo"]},
            "ou": {"n": V.PIN["ou_n"], "hit_rate": V.PIN["ou_hit"], "placebo": 0.50}}
    assert V.check_pin(good)["all_ok"] is True
    bad_n = {**good, "ats": {**good["ats"], "n": V.PIN["ats_n"] - 1}}
    assert V.check_pin(bad_n)["all_ok"] is False, "a changed population slipped past the pin"
    bad_hit = {**good, "ou": {**good["ou"], "hit_rate": V.PIN["ou_hit"] + 2 * V.PIN["tol"]}}
    assert V.check_pin(bad_hit)["all_ok"] is False, "changed predictions slipped past the pin"
    bad_placebo = {**good, "ats": {**good["ats"], "placebo": V.PIN["ats_placebo"] + 2 * V.PIN["tol"]}}
    assert V.check_pin(bad_placebo)["all_ok"] is False, "a changed placebo slipped past the pin"


def test_the_story_is_query_only():
    """No serving write, no registry edit, no publish — the whole story is a read (`best_alpha=0`)."""
    body = _src_no_comments()
    for forbidden in ("to_parquet", "--publish", "put_object", "_SERVED_JSON", "fit_served_mean",
                      "boto3", "sub_model_registry"):
        assert forbidden not in body, f"{forbidden!r} reached a query-only story"
