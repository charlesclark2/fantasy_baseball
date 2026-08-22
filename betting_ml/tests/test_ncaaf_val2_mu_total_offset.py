"""Guards for NCAAF-VAL2 — the μ_total − close_total offset decomposition.

Every clause is RED-proven against deliberately-broken source by
`quant_sports_intel_models/football/ncaaf/models/ncaaf_val2_red_proof.py`. A guard that cannot FAIL
is worse than no guard (NF1.7(a)/INC-38), and a guard on an `and`-gate is VACUOUS unless its fixture
satisfies every OTHER clause (NF-D17) — so each verdict clause below gets its own ISOLATING fixture
in which only that clause is false, and the base fixture is asserted to CLEAR first so the isolating
fixtures are known to be meaningful.

Fast-gate safe: imports `betting_ml` + the NCAAF model modules, never `pipeline` (E11.23), and does
no IO at import (the P1.4 cache is never touched here).
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models import ncaaf_val1_clv_week_strat as V1
from quant_sports_intel_models.football.ncaaf.models import ncaaf_val2_mu_total_offset as V2

_SRC = Path(V2.__file__).read_text()


def _src_no_comments() -> str:
    """Source with comments AND docstrings stripped — prose must never satisfy a source guard
    (INC-38: an explanatory comment once made a guard pass on a broken call site)."""
    tree = ast.parse(_SRC)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


def _frame(seasons=(2020, 2021, 2022, 2023, 2024, 2025), per=40, early_bias=0.0, level=0.0,
           week_early=2, week_late=9, seed=0) -> pd.DataFrame:
    """A synthetic offset frame with the columns `summarise`/`cold_start_contrast` consume.

    `level` shifts EVERY row (a season-wide bias); `early_bias` shifts only the wk1-3 rows (a genuine
    cold-start effect). Keeping the two knobs separate is what lets a fixture put a level in
    disguise up against the matched contrast."""
    rng = np.random.default_rng(seed)
    rows = []
    for s in seasons:
        for wk, n in ((week_early, per), (week_late, per)):
            err = rng.normal(0.0, 1.0, n) + level + (early_bias if wk <= 3 else 0.0)
            rows.append(pd.DataFrame({
                "season": s, V2.WEEK_COL: wk, "mu_total": 50.0 + err, "y_total": 50.0,
                "close_total": 49.0, "model_err": err, "close_err": 1.0,
                "offset": err + 1.0, "is_push": False,
            }))
    f = pd.concat(rows, ignore_index=True)
    f["bucket"] = V1.bucket_of(f[V2.WEEK_COL].to_numpy())
    return f


# ── the axis and the population ─────────────────────────────────────────────────────────────

def test_the_week_axis_is_season_order_week_never_raw_week():
    """The P1.1 postseason `week`=1 restart would drop January playoff games into the cold-start
    bucket — which is the exact cell this story hands to VAL3, so a raw-`week` cut would corrupt
    the one conclusion the study produces."""
    assert V2.WEEK_COL == "season_order_week"
    body = _src_no_comments()
    for bad in ('["week"]', "['week']", '.week', '"week")'):
        assert bad not in body, f"raw `week` reached the week axis via {bad!r}"


def test_the_served_config_is_imported_from_val1_not_restated():
    """A second literal of the served config here could drift from the one VAL1/S1-serve scored
    and nothing would fail — the study would silently be about a different model."""
    assert V2.SERVED is V1.PRIMARY
    body = _src_no_comments()
    assert "V.PRIMARY" in body or "V1.PRIMARY" in body
    assert "strength_pace" not in body, "the served contract is restated as a literal; import it"


# ── the decomposition ───────────────────────────────────────────────────────────────────────

def test_the_decomposition_terms_are_the_two_attributable_halves():
    names = [n for n, _d in V2.TERMS]
    assert names == ["offset", "model_err", "close_err"]


def test_build_offset_frame_raises_if_the_identity_does_not_hold():
    """(μ−close) = (μ−y) + (y−close) is arithmetic; if it ever fails, a column has been redefined
    and every mean below is measuring something other than what its name says."""
    body = _src_no_comments()
    assert "model_err" in body and "close_err" in body
    assert "SystemExit" in body
    assert "identity" in _SRC.lower()
    # the guard must live in the builder, not merely be described somewhere
    tree = ast.parse(_SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "build_offset_frame")
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert len(raises) >= 3, "the builder must refuse a bad join, a NULL close AND a broken identity"


def test_the_offset_read_never_indexes_a_draw_array_positionally():
    """⭐ THE defect this story uncovers: `_clv_eval`/`score_config` index the (n_games, n_draws)
    predictive array with a RESET index, reading a different game's distribution. This module is
    immune ONLY because it joins on `game_id` and reads each row's own `mu_total` — so a positional
    read into `dists` anywhere outside the alignment control would re-import the very bug."""
    tree = ast.parse(_SRC)
    control = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "alignment_control")
    # nested helpers of the control are part of the control (its `agree` closure does the two reads)
    exempt = {id(n) for n in ast.walk(control)}
    offenders = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or id(fn) in exempt:
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Subscript) \
                    and isinstance(node.value.value, ast.Name) and node.value.value.id == "dists":
                offenders.append(fn.name)
    assert not offenders, f"a positional read into `dists` outside the control, in {offenders}"


# ── the alignment control ───────────────────────────────────────────────────────────────────

def test_the_upstream_clv_misalignment_is_repaired():
    """The deliberate `..._is_still_present_TRIPWIRE` guard that stood here has been DISCHARGED.

    It pinned the known defect NCAAF-VAL2 §2 measured — `bakeoff_ncaaf_game._clv_eval` and
    `ncaaf_val1_clv_week_strat.score_config` indexing the `(n_games, n_draws)` draw array with a
    `reset_index(drop=True)` index — and went RED the moment someone fixed it, because the fix was
    not free: it changes every recorded model-vs-close hit rate in P1.4, S1-serve and VAL1.

    Its four discharge conditions were met by NCAAF-CLV-repair: the fix is
    `idx = np.flatnonzero(mask)` taken BEFORE the reset at both sites; P1.4, S1-serve and VAL1 were
    re-run on the repaired path; and VAL1's verdict was re-read against the repaired figures
    (`ALL_BUCKETS_NULL` survives — now EARNED rather than guaranteed — while its `side_tilt`
    ordering reverses). See `ablation_results/ncaaf_clv_row_alignment_repair.md`.

    ⛔ This assertion is deliberately weak: it only refuses a REGRESSION to the exact original
    shape, so that VAL2's suite stays coherent about its own §2. The substantive guards — including
    the numerical one that drives the real `_clv_eval` — live in
    `betting_ml/tests/test_ncaaf_clv_row_alignment.py`, RED-proven 6/6.
    """
    from quant_sports_intel_models.football.ncaaf.models import bakeoff_ncaaf_game as _B
    regressed = []
    for mod in (_B, V1):
        tree = ast.parse(Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = "\n".join(ast.unparse(st) for st in node.body)   # comments dropped
                if "m.index.to_numpy()" in body and "reset_index(drop=True)" in body:
                    regressed.append(f"{Path(mod.__file__).name}::{node.name}")
    assert regressed == [], (
        f"the NCAAF-VAL2 §2 row misalignment has come BACK at {regressed}. The repaired form is "
        "`idx = np.flatnonzero(mask)` taken BEFORE the reset; see test_ncaaf_clv_row_alignment.py.")


def test_the_alignment_control_is_two_sided():
    """A one-sided control that only checks the repaired path cannot tell the broken code from the
    fixed code, and would keep passing after someone 'simplifies' the index away."""
    assert V2.SIGN_AGREEMENT_FLOOR > V2.MISALIGNED_CEILING
    tree = ast.parse(_SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "alignment_control")
    body = ast.unparse(fn)
    assert "positive_control_ok" in body and "negative_control_ok" in body
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert len(raises) >= 3, "each control leg, and an unrecoverable index, must HALT separately"
    # ⭐ It is not enough that a HALT exists — it must be REACHABLE. Rewiring the guarding `if` to
    # a constant leaves the raise (and its explanatory message) in the source, so a guard that only
    # asserts the raise's TEXT passes on a control that can never fire. Read the CONDITION.
    conditions = [ast.unparse(n.test) for n in ast.walk(fn)
                  if isinstance(n, ast.If)
                  and any(isinstance(c, ast.Raise) for c in ast.walk(n))]
    assert any("positive_control_ok" in c for c in conditions), \
        "no reachable HALT is conditioned on the positive control"
    assert any("negative_control_ok" in c for c in conditions), \
        "no reachable HALT is conditioned on the negative control"


def test_the_mc_flip_band_shrinks_as_draws_grow():
    """The band inside which Monte-Carlo noise can flip a side is the reason the positive control's
    floor is 0.97 and not 1.0; if it did not shrink with draws it would be a fudge factor."""
    tree = ast.parse(_SRC)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "alignment_control")
    src = ast.unparse(fn)
    assert "mc_flip_band_pts" in src and "n_draws" in src
    assert "sqrt" in src, "the band must scale with the draw count, not be a constant"


# ── the statistics ──────────────────────────────────────────────────────────────────────────

def test_the_clustered_se_is_reported_beside_the_naive_one_and_is_larger_when_seasons_differ():
    """Games inside a season share one fitted strength surface and one scoring environment, so the
    naive sd/√n understates a LEVEL's uncertainty (NF1.8's per-group rule). Both are reported so
    the gap is visible rather than inferable."""
    rng = np.random.default_rng(1)
    season = np.repeat([2020, 2021, 2022, 2023, 2024, 2025], 200)
    v = np.concatenate([rng.normal(mu, 1.0, 200) for mu in (-2, -1, 0, 1, 2, 3)])
    s = V2.term_stats(v, season)
    assert s["n_clusters"] == 6
    assert s["cluster_se"] > s["naive_se"] * 3, "the clustered SE collapsed to the naive one"
    assert np.isclose(s["ci_hi"] - s["ci_lo"], 2 * s["cluster_t_crit"] * s["cluster_se"])


def test_demonstrated_and_resolvable_answer_different_questions_and_can_disagree():
    """`resolvable` is a PRE-data design question (80 % power); `demonstrated` is a POST-data one
    (does the interval exclude zero?). An effect can be demonstrated while below the 80 %-power
    MDE — collapsing them into one clause is the NF-W7i defect this study avoids."""
    season = np.repeat(np.arange(2020, 2026), 100)
    # per-season means chosen so the clustered t lands INSIDE the window where the two readings
    # differ: t_crit(.05, df=5) = 2.571 < |t| < 2.571 + t(.80, df=5) = 3.491.
    per = np.array([0.2, 2.2, 0.1, 2.0, 0.8, 1.7])
    s = V2.term_stats(np.repeat(per, 100), season)
    assert 2.571 < abs(s["cluster_t"]) < 3.491, "fixture drifted out of the disagreement window"
    assert s["demonstrated"] is True
    assert s["mde_clustered_pts"] > abs(s["cluster_mean"]), \
        "fixture no longer isolates the disagreement — pick a tighter/looser series"
    assert s["resolvable"] is False


def test_a_centred_series_is_neither_demonstrated_nor_resolvable():
    """The two-sided floor: an instrument that only ever says 'yes' certifies nothing."""
    season = np.repeat(np.arange(2020, 2026), 100)
    rng = np.random.default_rng(5)
    v = rng.normal(0.0, 1.0, 600)
    s = V2.term_stats(v - v.mean(), season)
    assert s["demonstrated"] is False and s["resolvable"] is False


def test_the_band_reading_is_two_sided_at_its_own_boundary():
    season = np.repeat(np.arange(2020, 2026), 50)
    hi = V2.term_stats(np.repeat([5.0, 5.1, 4.9, 5.0, 5.2, 4.8], 50), season)
    lo = V2.term_stats(np.repeat([0.10, 0.11, 0.09, 0.10, 0.12, 0.08], 50), season)
    assert hi["band_decisive_above"] and not hi["band_decisive_below"]
    assert lo["band_decisive_below"] and not lo["band_decisive_above"]


# ── the matched cold-start contrast ─────────────────────────────────────────────────────────

def test_the_matched_contrast_cancels_a_season_wide_level():
    """A level bias is positive in wk1-3 too, so the per-bucket read alone cannot separate 'the
    early weeks are special' from 'everything is shifted' (NF-D10). Pairing within season must make
    a pure level vanish."""
    k = V2.cold_start_contrast(_frame(level=3.0, early_bias=0.0))
    assert abs(k["mean_delta_pts"]) < 0.5
    assert k["demonstrated"] is False


def test_the_matched_contrast_finds_a_genuine_cold_start_effect():
    """The positive half — the contrast must be able to say yes, or the guard above is satisfied by
    an instrument that always says no."""
    k = V2.cold_start_contrast(_frame(level=3.0, early_bias=2.5))
    assert k["mean_delta_pts"] > 2.0 and k["demonstrated"] is True and k["material"] is True


def test_the_injection_controls_discriminate_in_both_directions():
    """A control set that only ever says 'nothing here' cannot certify a null, and one that always
    says 'found it' cannot certify a finding — so an injection ABOVE the design's MDE must be
    detected, one BELOW it must not, and a genuinely centred series must not."""
    c = V2.sign_stability_controls(_frame(early_bias=0.0, level=0.0), seed=0, n_perm=50)
    assert c["injection_above_mde_detected"] is True
    assert c["injection_below_mde_detected"] is False
    assert c["centred_null_detected"] is False
    assert c["discriminates"] is True


def test_the_matched_contrast_refuses_rather_than_score_one_season():
    f = _frame(seasons=(2023,))
    with pytest.raises(SystemExit, match="cannot be formed"):
        V2.cold_start_contrast(f)


# ── the verdict ─────────────────────────────────────────────────────────────────────────────

def _cells(demonstrated=True, material=True):
    """A cell dict shaped like `term_stats` output, clearing every clause unless told otherwise."""
    mean = 2.5 if material else 0.2
    half = 0.5 if demonstrated else 5.0
    return {"mean": mean, "cluster_mean": mean, "ci_lo": mean - half, "ci_hi": mean + half,
            "demonstrated": bool(demonstrated), "band_decisive_above": False,
            "band_decisive_below": False, "resolvable": True, "mde_clustered_pts": 1.0,
            "seasons_positive": 6, "n_clusters": 6, "sign_test_p": 0.03, "cluster_t": 5.0}


def _verdict(bucket_cell=None, pooled_cell=None, contrast=None):
    pooled = {"model_err": pooled_cell or _cells(demonstrated=False, material=False),
              "shares": {"model_share": 0.6, "close_share": 0.4}}
    by_bucket = {n: {"model_err": (bucket_cell or _cells()) if n == "wk1-3"
                     else _cells(demonstrated=False, material=False)} for n, _l, _h in V2.BUCKETS}
    unit = {"mean_minus_median_pts": 1.1}
    ctrl = {"discriminates": True}
    con = contrast or {"demonstrated": True, "material": True, "mean_delta_pts": 2.1,
                       "resolvable": True, "ci_lo": 0.4, "ci_hi": 3.8}
    return V2.verdict(pooled, by_bucket, unit, ctrl, con)


def test_the_base_fixture_actually_hands_off_so_every_isolating_fixture_is_meaningful():
    """NF-D17: an isolating fixture proves nothing unless the un-mutated fixture CLEARS."""
    v = _verdict()
    assert v["state"] == "HAND_TO_VAL3_SCOPED" and v["target_cells"] == ["wk1-3"]


def test_an_undemonstrated_bucket_cell_alone_refuses():
    v = _verdict(bucket_cell=_cells(demonstrated=False, material=True))
    assert v["state"] == "NOT_WORTH_A_REPAIR" and v["target_cells"] == []


def test_an_immaterial_bucket_cell_alone_refuses():
    v = _verdict(bucket_cell=_cells(demonstrated=True, material=False))
    assert v["state"] == "NOT_WORTH_A_REPAIR"


def test_a_level_in_disguise_is_refused_by_the_contrast_clause_alone():
    """⭐ The isolating fixture for the clause that matters most: the bucket cell is demonstrated
    AND material (so neither of the other clauses can be doing the refusing) and ONLY the matched
    contrast fails. Without this clause a season-wide level bias would be handed to VAL3 wearing a
    cold-start costume."""
    base = _verdict()
    assert base["state"] == "HAND_TO_VAL3_SCOPED"          # the fixture clears without the mutation
    v = _verdict(contrast={"demonstrated": False, "material": True, "mean_delta_pts": 0.3,
                           "resolvable": False, "ci_lo": -1.0, "ci_hi": 1.6})
    assert v["state"] == "NOT_WORTH_A_REPAIR" and v["target_cells"] == []


def test_the_pooled_cell_is_exempt_from_the_contrast_clause():
    """For a POOLED hand-off the level IS the hypothesis, so requiring it to also beat a
    within-season contrast would be requiring it to differ from itself."""
    v = _verdict(pooled_cell=_cells(), contrast={"demonstrated": False, "material": False,
                                                 "mean_delta_pts": 0.0, "resolvable": False,
                                                 "ci_lo": -1.0, "ci_hi": 1.0})
    assert v["state"] == "HAND_TO_VAL3" and "pooled" in v["target_cells"]


def test_the_sign_test_is_reported_but_is_not_a_verdict_clause():
    """The season permutation measures this statistic to be confounded with the LEVEL, so using it
    as a clause would double-count the level it is derived from (NF1.8). Flipping it must not move
    the verdict — and it must still be REPORTED, or the reader loses the caveat."""
    cell = _cells()
    cell["seasons_positive"] = 3                      # sign stability destroyed
    v = _verdict(bucket_cell=cell)
    assert v["state"] == "HAND_TO_VAL3_SCOPED", "the sign test is acting as a hidden clause"
    assert "seasons_positive" in v["cells"]["wk1-3"] and "sign_test_p" in v["cells"]["wk1-3"]


def test_both_readings_are_disclosed_so_a_reader_can_apply_either_rule():
    v = _verdict()
    d = v["reading_disagreement"]
    assert set(d) >= {"cells_where_mde_and_ci_disagree", "contrast_mde_says", "contrast_ci_says",
                      "verdict_under_mde_rule"}


def test_the_materiality_band_is_stated_forward_as_a_constant():
    """⛔ A band re-derived from an observed value is the E2.1-r inversion. It must be a module
    constant, not a function of any measured cell."""
    assert V2.MATERIAL_PTS == 1.0
    tree = ast.parse(_SRC)
    assign = [n for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, "id", "") == "MATERIAL_PTS" for t in n.targets)]
    assert len(assign) == 1 and isinstance(assign[0].value, ast.Constant)


# ── provenance and scope ────────────────────────────────────────────────────────────────────

def test_a_cache_that_is_not_val1s_population_is_flagged_not_silently_used():
    df = pd.DataFrame({"has_close": [True] * 10})
    p = V2.cache_provenance(df, {"assembled_at": "2026-01-01"})
    assert p["matches_val1_population"] is False and "⚠️" in p["note"]
    df2 = pd.DataFrame({"has_close": [True] * V2.VAL1_RECORDED["n_with_close"]})
    assert V2.cache_provenance(df2, {})["matches_val1_population"] is True


def test_a_missing_pace_source_raises_rather_than_producing_a_pace_free_frame():
    """NF1.7(a): a silently pace-free frame would resolve the served contract to something else."""
    with pytest.raises(KeyError, match="pace"):
        V2.ensure_pace_composites(pd.DataFrame({"game_id": [1]}), [])


def test_a_cache_that_already_carries_the_composites_is_left_alone():
    df = pd.DataFrame({"game_id": [1], "pace_sum": [1.0], "pace_diff": [0.0]})
    out, feat, prov = V2.ensure_pace_composites(df, ["a"])
    assert out is df and feat == ["a"] and prov["pace_derived_in_session"] is False


def test_the_close_unit_reading_uses_non_push_rows_for_the_side_statistic():
    """A push is neither over nor under; counting it as an under would bias the median reading that
    decides how much of the offset a μ-recalibration is even allowed to remove."""
    f = pd.DataFrame({"close_err": [1.0, -1.0, 0.0, 0.0], "is_push": [False, False, True, True],
                      "y_total": [50.0, 48.0, 49.0, 49.0]})
    u = V2.close_unit_reading(f)
    assert u["n_nonpush"] == 2 and u["p_realised_over_close_nonpush"] == 0.5


def test_the_study_is_query_only():
    """No refit of a served artifact, no serving write, no registry edit, no bet."""
    body = _src_no_comments()
    for bad in ("--publish", "to_parquet(", "boto3", "deploy.sh", "registry", "best_alpha =",
                "sub_model_registry"):
        assert bad not in body, f"a query-only study reached for {bad!r}"
    assert "'best_alpha': 0" in body or '"best_alpha": 0' in body
