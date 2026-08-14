"""Guards for NF-W6 — per-stat distributional targets: the ORACLE DECISION GATE.

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.efficiency_marginals`); the runner is imported
only INSIDE test methods (its module scope is IO-free; its lake reads live in functions).

Discipline inherited from the NF-W3/W4/W5/MARGIN suites:
  · every `stat_ok` clause has an ISOLATING fixture — a base selection where every other clause
    passes, so exactly one clause can flip the result (NF-D17);
  · RED-proofs apply their mutation in-process and ASSERT THE MUTATION LANDED (E11.24 #682);
  · iterating guards assert NON-VACUITY first (an empty match set passes on nothing — DSR-CONV);
  · source scans run comment-stripped so prose can neither satisfy nor trip them (INC-38).
"""
from __future__ import annotations

import json
import re
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(EM.__file__)
_RUNNER = _MODULE.parent / "run_nf_w6_efficiency_marginals.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w6_preregistration.md"
_RNG = np.random.default_rng(20260814)


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    mutated = src.replace(old, new, 1)
    assert mutated != src, "the mutation did not change the source — the RED-proof would no-op"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(mutated, str(path), "exec"), mod.__dict__)  # noqa: S102 — test harness
    return mod


def _stripped_source(path: Path) -> str:
    """Comment-stripped source, so a prose mention can neither satisfy nor trip a check."""
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Field + pre-registration shape
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFieldAndPreregistration:
    def test_the_cell_map_is_the_declared_scope(self):
        assert len(EM.cells()) == 12
        assert EM.POSITION_STATS["QB"] == ("passing_yards", "passing_tds",
                                           "rushing_yards", "rushing_tds")
        assert EM.POSITION_STATS["WR"] == ("receiving_yards", "receiving_tds")
        assert EM.POSITION_STATS["TE"] == ("receiving_yards", "receiving_tds")
        for p, stats in EM.POSITION_STATS.items():
            assert set(stats) <= set(EM.STATS), (p, stats)

    def test_anchors_and_incumbents_are_disjoint_and_complete(self):
        anchors = EM.anchors()
        assert len(anchors) > 0                       # non-vacuity (NF1.7 (a))
        assert set(anchors).isdisjoint(EM.INCUMBENT_FORMS)
        for f in EM.ORACLE_FORMS:
            assert EM.oracle_of(f) in anchors
            assert EM.matched_n_of(f) in anchors
        assert set(EM.all_labels()) == set(EM.INCUMBENT_FORMS) | set(anchors)

    def test_the_candidate_heteroscedastic_form_is_in_the_oracle_set(self):
        """The two incumbent-form oracles carry position-constant banks — blind to conditional
        heteroscedasticity. The candidate quantile form is the clause that prevents a FALSE NO."""
        assert "cand_lgbm_quantile" in EM.ORACLE_FORMS

    def test_fdr_families_are_disjoint_and_cover_every_cell(self):
        fams = EM.fdr_families()
        yards, tds = set(fams["yards"]), set(fams["tds"])
        assert yards.isdisjoint(tds)
        assert len(yards) == len(tds) == 6
        assert yards | tds == {f"w6_ceiling_{c}" for c in EM.cells()}

    def test_capture_era_folds_derive_from_the_fold_axis(self):
        assert EM.CAPTURE_ERA_FOLDS == tuple(
            f"{s}H{h}" for s, h in WP.TEST_BLOCKS if s >= 2025)
        assert EM.CAPTURE_ERA_FOLDS == ("2025H1", "2025H2")

    def test_the_dense_grid_is_the_margin1_grid_imported_not_retyped(self):
        assert EM.EVAL_LEVELS is MC.EVAL_LEVELS
        assert len(EM.EVAL_LEVELS) == 199

    def test_the_bands_are_the_nf_w5_precedent_bands(self):
        assert EM.CEILING_BANDS == (2.0, 5.0)

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        assert _PREREG.exists(), "the narrative pre-registration must be committed before the run"
        text = _PREREG.read_text()
        for token in ("crps_q199", "cand_lgbm_quantile", "deploy-held", "BINDING incumbent",
                      "ORACLE", "matched-n", "cross-fit", "NF-D11", "2%", "5%",
                      "classify_null` is NOT invoked"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_the_champion_head_construction_is_byte_identical(self):
        """The incumbent head must be the champion component head's learner, verbatim — the same
        `WP._lgbm` override dict in both sources (a drifted head is a different incumbent)."""
        lit = '{"objective": "regression", "n_estimators": 200}'
        assert lit in _stripped_source(_MODULE)
        wp_src = _stripped_source(Path(WP.__file__))
        head_src = wp_src.split("def fit_component_head", 1)[1]
        assert lit in head_src, "fit_component_head no longer uses the pinned construction — "\
                                "re-verify the incumbent head faithfulness"

    def test_no_mae_anywhere_td_cells_are_crps_only(self):
        """NF-D11/D14: MAE inverts at the conditional median on zero-heavy targets — this story
        must not COMPUTE it at all. ⭐ AST scan, not substring: the module docstring legitimately
        SAYS "CRPS, never MAE" (prose must neither satisfy nor trip a guard — NF-W3's AST
        lesson)."""
        import ast
        for path in (_MODULE, _RUNNER):
            tree = ast.parse(path.read_text())
            hits = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and "mae" in node.id.lower():
                    hits.append(node.id)
                if isinstance(node, ast.Attribute) and (
                        "mae" in node.attr.lower() or "mean_absolute" in node.attr.lower()):
                    hits.append(node.attr)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                        "mae" in node.name.lower():
                    hits.append(node.name)
            assert not hits, f"MAE computation surface in {path.name}: {hits}"

    def test_classify_null_is_never_called(self):
        """NF-W3 (c): the n_arms=1 mis-render — the decision object is bands, not a null state.
        Call-site regex (DSR-CONV #690: never grep a bare name)."""
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            assert not re.search(r"classify_null\s*\(", src), f"classify_null call in {path.name}"

    def test_coverage_is_never_a_target(self):
        """⛔ E2.1-r: no fitting objective may reference |coverage − floor|."""
        src = _stripped_source(_MODULE)
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", src)
        for m in re.finditer(r"def (fit_\w+)\(.*?(?=\ndef |\Z)", src, re.S):
            assert "COVERAGE_FLOOR" not in m.group(0), (
                f"{m.group(1)} references the coverage floor — a floor must never be fit toward")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. TD label attach (grain + conservation, both refusals RED-proved)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _feat(rows):
    return pd.DataFrame(rows)


def _feed(rows):
    return pd.DataFrame(rows)


class TestTdAttach:
    def _base(self):
        feat = _feat([
            {"season": 2024, "week": 1, "gsis_id": "A", "position": "QB"},
            {"season": 2024, "week": 1, "gsis_id": "B", "position": "WR"},
            {"season": 2024, "week": 2, "gsis_id": "A", "position": "QB"},
        ])
        feed = _feed([
            {"season": 2024, "week": 1, "player_id": "A",
             "passing_tds": 2, "rushing_tds": 1, "receiving_tds": 0},
            {"season": 2024, "week": 1, "player_id": "B",
             "passing_tds": 0, "rushing_tds": 0, "receiving_tds": 1},
        ])
        return feat, feed

    def test_happy_path_fills_label_zeros_and_audits(self):
        feat, feed = self._base()
        out, audit = EM.attach_td_labels(feat, feed)
        assert len(out) == 3
        assert out.loc[2, "passing_tds"] == 0.0        # rostered-no-stat week = REAL ZERO
        assert out.loc[0, "passing_tds"] == 2.0
        assert audit["passing_tds_total"] == 2.0
        assert audit["passing_tds_filled_zero_rows"] == 1

    def test_duplicate_feed_grain_refuses(self):
        feat, feed = self._base()
        feed = pd.concat([feed, feed.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="duplicate"):
            EM.attach_td_labels(feat, feed)

    def test_a_duplicated_matrix_key_fails_conservation(self):
        """A dup key on the MATRIX side double-counts the label — the conservation clause is what
        catches it (the NF-W3 row-conservation rule made operational)."""
        feat, feed = self._base()
        feat = pd.concat([feat, feat.iloc[[0]]], ignore_index=True)
        with pytest.raises(ValueError, match="conservation FAILED"):
            EM.attach_td_labels(feat, feed)

    def test_an_already_attached_column_refuses_a_second_merge(self):
        feat, feed = self._base()
        feat["receiving_tds"] = 0.0
        with pytest.raises(ValueError, match="second attach"):
            EM.attach_td_labels(feat, feed)

    def test_red_proof_the_conservation_clause_is_load_bearing(self):
        mod = _mutated(_MODULE, 'if abs(matrix_sum - feed_sum) > 1e-6:',
                       'if False and abs(matrix_sum - feed_sum) > 1e-6:', "em_mut_conserv")
        feat, feed = self._base()
        feat = pd.concat([feat, feat.iloc[[0]]], ignore_index=True)
        out, _ = mod.attach_td_labels(feat, feed)      # no raise ⇒ the clause was the guard
        assert len(out) == 4


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Banks + refusals (NF1.7 (a))
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pos_arr(n_per: int = 80):
    return np.repeat(list(EM.POSITIONS), n_per)


class TestBanks:
    def test_climatology_reproduces_empirical_quantiles(self):
        pos = _pos_arr(100)
        y = _RNG.normal(50, 10, len(pos))
        bank = EM.climatology_bank(y, pos)
        qb = y[pos == "QB"]
        assert np.allclose(bank["QB"], np.quantile(qb, EM.EVAL_LEVELS))

    def test_climatology_refuses_a_thin_position(self):
        pos = np.array(["QB"] * 10 + ["RB"] * 100 + ["WR"] * 100 + ["TE"] * 100)
        with pytest.raises(ValueError, match="refusing"):
            EM.climatology_bank(_RNG.normal(size=len(pos)), pos)

    def test_residual_bank_falls_back_pooled_for_a_thin_position(self):
        pos = np.array(["QB"] * 10 + ["RB"] * 200 + ["WR"] * 200 + ["TE"] * 200)
        r = _RNG.normal(size=len(pos))
        bank = EM.residual_bank199(r, pos)
        pooled = np.quantile(r, EM.EVAL_LEVELS)
        assert np.allclose(bank["QB"], pooled)          # thin → pooled (the WP convention)
        assert not np.allclose(bank["RB"], pooled)

    def test_residual_bank_refuses_a_thin_pooled_sample(self):
        with pytest.raises(ValueError, match="refusing"):
            EM.residual_bank199(np.ones(10), np.array(["QB"] * 10))

    def test_apply_bank_adds_the_point(self):
        pos = _pos_arr(60)
        bank = {p: np.linspace(-1, 1, 199) for p in EM.POSITIONS}
        out = EM.apply_bank199(np.full(len(pos), 7.0), pos, bank)
        assert out.shape == (len(pos), 199)
        assert np.allclose(out[0], 7.0 + np.linspace(-1, 1, 199))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Candidate knot form + the NF-MARGIN1 tail
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _knots(n: int = 40, lo: float = 0.0, hi: float = 90.0):
    base = np.linspace(lo, hi, len(EM.FIT_LEVELS))
    return np.sort(base[None, :] + _RNG.normal(0, 1, size=(n, 1)), axis=1)


def _tails(beta_hi: float, beta_lo: float = 0.0):
    return {p: {"beta_hi": beta_hi, "beta_lo": beta_lo, "n_hi": 30, "n_lo": 30,
                "thin_hi": False, "thin_lo": False} for p in EM.POSITIONS}


class TestCandTails:
    def test_rows_are_monotone_with_and_without_tails(self):
        pos = np.repeat("QB", 40)
        for beta in (0.0, 12.0):
            out = EM.knots_to_eval(_knots(), _tails(beta, beta), pos)
            assert (np.diff(out, axis=1) >= -1e-9).all()

    def test_beta_zero_is_the_as_served_flat_truncation(self):
        pos = np.repeat("QB", 5)
        k = _knots(5)
        out = EM.knots_to_eval(k, _tails(0.0), pos)
        above = EM.EVAL_LEVELS > EM.FIT_LEVELS[-1]
        assert np.allclose(out[:, above], k[:, -1][:, None])   # flat = no tail model

    def test_a_positive_beta_extends_beyond_the_end_knot_continuously(self):
        pos = np.repeat("QB", 5)
        k = _knots(5)
        out = EM.knots_to_eval(k, _tails(10.0), pos)
        above = EM.EVAL_LEVELS > EM.FIT_LEVELS[-1]
        assert (out[:, above] > k[:, -1][:, None] + 1e-9).all()
        at_end = out[:, int(np.searchsorted(EM.EVAL_LEVELS, EM.FIT_LEVELS[-1]))]
        assert np.allclose(at_end, k[:, -1])                    # continuous at the joint

    def test_tail_betas_are_mean_excess_and_thin_sides_are_counted(self):
        pos = np.repeat("QB", 200).astype(object)
        k = np.tile(np.linspace(0, 50, len(EM.FIT_LEVELS)), (200, 1))
        y = np.full(200, 25.0)
        y[:30] = 50.0 + 8.0                       # 30 exceedances of excess exactly 8
        t = EM.tail_betas_by_pos(k, y, pos)
        assert t["QB"]["beta_hi"] == pytest.approx(8.0)
        assert t["QB"]["n_hi"] == 30 and not t["QB"]["thin_hi"]
        assert t["QB"]["beta_lo"] == 0.0 and t["QB"]["thin_lo"]   # no low exceedances → counted

    def test_crossfit_partitions_and_is_deterministic(self):
        a = EM.crossfit_ids(100, 3, "2025H1", "passing_yards")
        b = EM.crossfit_ids(100, 3, "2025H1", "passing_yards")
        assert np.array_equal(a, b)
        assert set(np.unique(a)) == {0, 1, 2}
        c = EM.crossfit_ids(100, 3, "2025H2", "passing_yards")
        assert not np.array_equal(a, c)

    def test_crossfit_refuses_k_below_two(self):
        with pytest.raises(ValueError, match="in-sample"):
            EM.crossfit_ids(100, 1, "2025H1", "passing_yards")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The one reducer (refuses a broken construction — NF-W3 (b))
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestReducer:
    def test_point_mass_at_the_label_scores_zero(self):
        y = np.array([3.0, 7.0])
        bank = np.repeat(y[:, None], 199, axis=1)
        assert EM.score_bank(bank, y)["crps_q199"] == pytest.approx(0.0)

    def test_refuses_a_non_finite_predictive(self):
        bank = np.zeros((4, 199))
        bank[1, 5] = np.nan
        with pytest.raises(ValueError, match="non-finite predictive"):
            EM.score_bank(bank, np.zeros(4))

    def test_refuses_non_finite_labels(self):
        with pytest.raises(ValueError, match="labels"):
            EM.score_bank(np.zeros((2, 199)), np.array([1.0, np.nan]))

    def test_red_proof_the_finite_refusal_is_load_bearing(self):
        mod = _mutated(_MODULE, "if not np.isfinite(b).all():",
                       "if False and not np.isfinite(b).all():", "em_mut_finite")
        bank = np.zeros((2, 199))
        bank[0, 0] = np.nan
        out = mod.score_bank(bank, np.zeros(2))   # no raise ⇒ the clause was the ONLY guard
        assert np.isnan(out["crps_q199"]), (
            "with the refusal disabled the reducer should propagate the NaN — if it doesn't, "
            "something else guards this path and the RED-proof is not isolating (NF-D17)")

    def test_the_nihilist_loses_to_climatology_on_a_zero_heavy_td_cell(self):
        """The NF-D11 soundness proof, measured: with a 60% zero atom CRPS must still prefer the
        honest climatology to the all-zero degenerate (MAE would not)."""
        y = np.concatenate([np.zeros(600), np.ones(300), np.full(100, 2.0)])
        bank = np.repeat(np.quantile(y, EM.EVAL_LEVELS)[None, :], len(y), axis=0)
        clim = EM.score_bank(bank, y)["crps_q199"]
        nihil = EM.score_bank(EM.anchor_nihilist(len(y)), y)["crps_q199"]
        assert clim < nihil

    def test_zero_atom_diagnostics_are_sane(self):
        y = np.concatenate([np.zeros(500), np.ones(500)])
        bank = np.repeat(np.quantile(y, EM.EVAL_LEVELS)[None, :], len(y), axis=0)
        sc = EM.score_bank(bank, y)
        assert sc["real_p0"] == pytest.approx(0.5)
        assert 0.3 < sc["pred_p0"] < 0.7

    def test_sharpness_degenerates_bracket(self):
        y = _RNG.normal(20, 8, 800)
        bank = np.repeat(np.quantile(y, EM.EVAL_LEVELS)[None, :], len(y), axis=0)
        base = EM.score_bank(bank, y)["crps_q199"]
        zw = EM.score_bank(EM.anchor_zero_width(bank), y)["crps_q199"]
        mw = EM.score_bank(EM.anchor_max_width(bank), y)["crps_q199"]
        assert zw > base and mw > base                 # both must lose (NF1.7 (c) / NF1.8)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Ceiling selection + the decision (isolating fixture per clause — NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fold_result(label: str, cell: str, crps_by_label: dict[str, float]) -> dict:
    scores = {lab: {"crps_q199": v, "coverage_80": 0.8, "pred_p0": 0.1, "real_p0": 0.1,
                    "n": 500} for lab, v in crps_by_label.items()}
    return {"label": label, "cells": {cell: {"scores": scores}}}


def _fold_results(cell: str = "QB|passing_yards", n: int = 8, oracle_gap: float = 1.0,
                  jitter: float = 0.02) -> list[dict]:
    """8 folds where the best oracle beats the binding incumbent by `oracle_gap` (CRPS 10.0
    base), every degenerate loses, and matched-n sits between."""
    out = []
    rng = np.random.default_rng(7)
    labels = [f"{s}H{h}" for s, h in WP.TEST_BLOCKS][:n]
    for lbl in labels:
        e = rng.normal(0, jitter)
        crps = {
            "inc_head_bank": 10.0 + e,
            "inc_climatology": 10.4 + e,
            "nihilist_zero": 14.0, "zero_width": 12.0, "max_width": 13.0,
            "oracle__inc_climatology": 10.2 + e,
            "oracle__inc_head_bank": 10.0 - oracle_gap + e,
            "oracle__cand_lgbm_quantile": 10.1 + e,
            "matched_n__inc_climatology": 10.1 + e,   # BEATS its own oracle (capacity reading)
            "matched_n__inc_head_bank": 10.2 + e,
            "matched_n__cand_lgbm_quantile": 10.3 + e,
        }
        out.append(_fold_result(lbl, cell, crps))
    return out


class TestSelectCell:
    def test_binding_incumbent_and_best_form(self):
        sel = EM.select_cell(_fold_results(), "QB|passing_yards", 8)
        assert sel["binding_incumbent"] == "inc_head_bank"
        assert sel["best_form"] == "inc_head_bank"
        assert sel["fold_wins"] == 8
        assert sel["ceiling_pct"] == pytest.approx(10.0, abs=0.5)
        assert sel["anchors"]["nihilist_loses"] and sel["anchors"]["zero_width_loses"]
        assert sel["anchors"]["max_width_loses"]

    def test_oracle_vs_matched_n_reading_is_reported_per_form(self):
        sel = EM.select_cell(_fold_results(), "QB|passing_yards", 8)
        for f in EM.ORACLE_FORMS:
            assert "oracle_beats_matched_n" in sel["per_form"][f]
        assert sel["per_form"]["inc_head_bank"]["oracle_beats_matched_n"]
        assert not sel["per_form"]["inc_climatology"]["oracle_beats_matched_n"]

    def test_era_note_splits_capture_and_legacy(self):
        sel = EM.select_cell(_fold_results(), "QB|passing_yards", 8)
        assert sel["era_note"]["capture_folds"] == ["2025H1", "2025H2"]
        assert sel["era_note"]["capture_mean_delta"] is not None

    def test_pbo_is_undefined_by_declaration(self):
        sel = EM.select_cell(_fold_results(), "QB|passing_yards", 8)
        assert sel["pbo"] is None and "UNDEFINED" in sel["pbo_state"]


def _sel(pct: float = 6.0, lo: float = 0.5, passes: bool = True, fdr: bool = True) -> dict:
    """A selection where every stat_ok clause passes unless the caller flips exactly one —
    the NF-D17 isolating-fixture builder."""
    return {"ceiling_pct": pct, "ci95": [lo, lo + 1.0],
            "fold_clause": {"required": 6, "attainable": True, "passes": passes},
            "fdr_binding": fdr}


class TestDecisionRule:
    def test_yes_at_and_above_five(self):
        assert EM.decide_cell(_sel(5.0))["answer"] == "YES"
        assert EM.decide_cell(_sel(9.3))["answer"] == "YES"

    def test_marginal_between_bands(self):
        assert EM.decide_cell(_sel(2.0))["answer"] == "MARGINAL"
        assert EM.decide_cell(_sel(4.9))["answer"] == "MARGINAL"

    def test_no_below_two(self):
        d = EM.decide_cell(_sel(1.9))
        assert d["answer"] == "NO" and "near its ceiling" in d["reason"]

    def test_isolating_ci_spanning_zero_is_no(self):
        d = EM.decide_cell(_sel(10.0, lo=-0.01))
        assert d["answer"] == "NO" and not d["stat_ok"]

    def test_isolating_fold_clause_failure_is_no(self):
        assert EM.decide_cell(_sel(10.0, passes=False))["answer"] == "NO"

    def test_isolating_fdr_failure_is_no(self):
        assert EM.decide_cell(_sel(10.0, fdr=False))["answer"] == "NO"

    def test_unset_fdr_fails_closed(self):
        s = _sel(10.0)
        s["fdr_binding"] = None
        assert EM.decide_cell(s)["answer"] == "NO"

    def test_unevaluable_pct_or_ci_fails_closed(self):
        s = _sel(3.0)
        s["ceiling_pct"] = None
        assert EM.decide_cell(s)["answer"] == "NO"
        s2 = _sel(3.0)
        s2["ci95"] = [None, None]
        assert EM.decide_cell(s2)["answer"] == "NO"

    def test_red_proof_the_ci_clause_is_load_bearing(self):
        mod = _mutated(_MODULE, "and lo is not None and lo > 0", "and True", "em_mut_ci")
        assert mod.decide_cell(_sel(10.0, lo=-0.01))["stat_ok"]

    def test_red_proof_the_bands_are_load_bearing(self):
        mod = _mutated(_MODULE, "CEILING_BANDS: tuple[float, float] = (2.0, 5.0)",
                       "CEILING_BANDS: tuple[float, float] = (0.1, 0.2)", "em_mut_bands")
        assert mod.decide_cell(_sel(1.9))["answer"] == "YES"

    def test_story_builds_iff_any_yes(self):
        d_yes, d_no, d_m = _sel(6.0), _sel(1.0), _sel(3.0)
        story = EM.decide_story({"a": EM.decide_cell(d_yes), "b": EM.decide_cell(d_no)})
        assert story["answer"] == "BUILD" and story["yes_cells"] == ["a"]
        story2 = EM.decide_story({"a": EM.decide_cell(d_no), "b": EM.decide_cell(d_m)})
        assert story2["answer"] == "NULL" and story2["marginal_cells"] == ["b"]
        assert "MARGINAL cells for the PM" in story2["reason"]

    def test_json_round_trip_preserves_the_decision(self):
        s = _sel(3.3)
        assert EM.decide_cell(json.loads(json.dumps(s)))["answer"] == EM.decide_cell(s)["answer"]


class TestFdrFamilies:
    def test_binding_requires_both_own_and_pooled(self):
        yards = {f"w6_ceiling_y{i}": 0.5 for i in range(6)}
        yards["w6_ceiling_y0"] = 0.011     # would pass alone in a 6-test family (0.1/6 ≈ 0.0167)
        tds = {f"w6_ceiling_t{i}": 0.001 for i in range(6)}
        out = EM.fdr_two_families_w6(yards, tds)
        assert len(out["binding"]) == 12   # non-vacuity
        assert all(out["binding"][k] for k in tds)
        # y0 passes its own family but must ALSO survive the pooled 12-test correction
        assert out["own_family"]["w6_ceiling_y0"]
        assert out["binding"]["w6_ceiling_y0"] == out["pooled"]["w6_ceiling_y0"]

    def test_a_none_p_never_passes(self):
        out = EM.fdr_two_families_w6({"w6_ceiling_a": None}, {"w6_ceiling_b": 0.001})
        assert out["binding"]["w6_ceiling_a"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Positive control (MH2.1 (d): the instrument must SEE a known regime shift)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPositiveControl:
    def _test_frame(self, n: int = 400):
        return pd.DataFrame({
            "position": ["QB"] * n,
            "passing_yards": _RNG.normal(220, 60, n).clip(0),
        })

    def test_the_instrument_sees_a_regime_shift(self):
        test = self._test_frame()
        train_bank = {"QB": np.quantile(_RNG.normal(220, 60, 4000).clip(0), EM.EVAL_LEVELS)}
        pc = EM.positive_control_shift(test, "passing_yards", "QB", train_bank)
        assert pc["instrument_sees_the_shift"]
        assert pc["ceiling_shifted"] > pc["ceiling_unshifted"]

    def test_refuses_a_thin_position(self):
        test = self._test_frame(10)
        with pytest.raises(ValueError, match="refusing"):
            EM.positive_control_shift(test, "passing_yards", "QB",
                                      {"QB": np.zeros(199)})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. The verdict layer is DERIVED, not stored (NF-W2e one level up)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _full_out(oracle_gap: float = 1.0) -> dict:
    frs_by_cell: list[dict] = []
    labels = [f"{s}H{h}" for s, h in WP.TEST_BLOCKS]
    for i, lbl in enumerate(labels):
        cells = {}
        for c in EM.cells():
            fr = _fold_results(c, 8, oracle_gap)[i]
            cells[c] = fr["cells"][c]
        frs_by_cell.append({"label": lbl, "cells": cells})
    return {"n_folds": 8, "fold_results": frs_by_cell}


class TestVerdictLayerIsDerivedNotStored:
    def _runner(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6_efficiency_marginals as R,
        )
        return R

    def test_a_large_demonstrable_ceiling_derives_build(self):
        derived = self._runner().derive_verdict_layer(_full_out(oracle_gap=1.0))
        assert derived["verdict"]["story"] == "BUILD"
        assert len(derived["selections"]) == 12
        assert derived["story_decision"]["yes_cells"]

    def test_a_tiny_ceiling_derives_null(self):
        derived = self._runner().derive_verdict_layer(_full_out(oracle_gap=0.05))
        assert derived["verdict"]["story"] == "NULL"

    def test_re_deriving_is_idempotent_and_overwrites_stale_verdicts(self):
        R = self._runner()
        out = _full_out()
        first = R.derive_verdict_layer(out)
        out.update(first)
        out["verdict"] = {"story": "STALE"}
        second = R.derive_verdict_layer(out)
        assert second["verdict"]["story"] == first["verdict"]["story"] == "BUILD"

    def test_the_rewrite_path_shares_the_same_derivation(self):
        src = _stripped_source(_RUNNER)
        assert src.count("out.update(derive_verdict_layer(out))") == 2, (
            "the live run and --rewrite-report must share ONE derivation — a second "
            "implementation is a verdict that can disagree with itself")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. Runner wiring (source inspection, comment-stripped — INC-38)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRunnerWiring:
    def test_the_pit_gate_runs_on_every_build_including_cache_hits(self):
        src = _stripped_source(_RUNNER)
        assert "WP.run_pit_gate(feat)" in src, "the cache-hit path must re-prove PIT (NF-C0e)"
        assert "W1R.build_matrix(" in src

    def test_the_td_attach_is_invoked_not_just_imported(self):
        src = _stripped_source(_RUNNER)
        assert re.search(r"EM\.attach_td_labels\s*\(", src), "wired ≠ invoked (NF-C0e)"

    def test_the_ceiling_is_logged_oracle_first_inside_the_fold(self):
        src = _RUNNER.read_text()
        fold_section = src.split("def derive_verdict_layer")[0]
        assert "peeking CEILING" in fold_section

    def test_the_smoke_positive_control_is_a_hard_assert(self):
        src = _stripped_source(_RUNNER)
        assert "POSITIVE CONTROL FAILED" in src
        assert re.search(r"raise SystemExit\(f?\"POSITIVE CONTROL FAILED", src)

    def test_the_features_are_the_champion_features_never_a_new_set(self):
        src = _stripped_source(_RUNNER)
        assert "FEATURES = list(WP.FEATURES)" in src
        assert not re.search(r"FEATURES\s*=\s*\[\s*['\"]", src), (
            "a hand-typed feature list can drift from the certified contract")

    def test_no_fillna_zero_on_snap_or_feature_columns(self):
        """The only fillna(0) surfaces in this story are LABEL-side stat columns (declared)."""
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            for m in re.finditer(r"(\w+)?\[[^\]]*snap[^\]]*\][^\n]*fillna\(0", src):
                raise AssertionError(f"snap-column fillna(0) in {path.name}: {m.group(0)}")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. Deploy-held (best_alpha N/A; promotes nothing, publishes nothing)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDeployHeld:
    _FORBIDDEN = ("write_serving_store", "write_api_cache", "deploy.sh", "boto3.client",
                  "put_object", "upload_file", "credence-prod", "s3.put", "registry.stage",
                  "to_delta", "write_deltalake")

    def test_neither_file_touches_a_serving_surface(self):
        assert len(self._FORBIDDEN) > 0
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            hits = [tok for tok in self._FORBIDDEN if tok in src]
            assert not hits, f"{path.name} touches serving surfaces: {hits}"

    def test_red_proof_the_scan_would_catch_a_real_write(self):
        src = _stripped_source(_MODULE) + "\nboto3.client('s3').put_object()"
        hits = [tok for tok in self._FORBIDDEN if tok in src]
        assert hits, "the deploy-held scan cannot fire — it guards nothing"
