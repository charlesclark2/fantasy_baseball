"""Guards for NF-W6b — the per-stat distributional successor (§0.5 bake-off).

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.stat_distributions`); the runner is imported
only INSIDE test methods (its module scope is IO-free; its lake reads live in functions).

Discipline inherited from the NF-W3/W4/W5/W6/MARGIN suites:
  · every gate clause has an ISOLATING fixture — a base selection where every other clause
    passes, so exactly one clause can flip the result (NF-D17) — and each clause is RED-proved
    by deleting it in-process with the mutation ASSERTED TO LAND (E11.24 #682);
  · iterating guards assert NON-VACUITY first (an empty match set passes on nothing — DSR-CONV);
  · source scans run comment-stripped and structural checks use AST, so prose can neither
    satisfy nor trip them (INC-38 / NF-W3);
  · ⛔ the 4 TD-NO cells are pinned CLOSED (the story card's re-open ban), and the fresh-
    registration rule (MH2.2) is pinned: no oracle/matched label may enter the trial field.
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
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(SD.__file__)
_RUNNER = _MODULE.parent / "run_nf_w6b_stat_distributions.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w6b_preregistration.md"
_RNG = np.random.default_rng(20260815)

LICENSED_CELLS = {
    "QB|passing_yards", "QB|passing_tds", "QB|rushing_yards",
    "RB|rushing_yards", "RB|rushing_tds", "RB|receiving_yards",
    "WR|receiving_yards", "TE|receiving_yards",
}
CLOSED = {"QB|rushing_tds", "RB|receiving_tds", "WR|receiving_tds", "TE|receiving_tds"}


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
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Field + pre-registration shape
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFieldAndPreregistration:
    def test_the_cell_map_is_exactly_the_licensed_scope(self):
        """7 NF-W6 YES cells + RB rushing_tds by PM ruling — nothing else."""
        assert set(SD.cells()) == LICENSED_CELLS
        assert len(SD.cells()) == 8

    def test_the_four_td_no_cells_stay_closed(self):
        """⛔ the story card's re-open ban: closed cells are declared, disjoint from the field,
        and licensed + closed together reconstruct NF-W6's full 12-cell map (so a cell can
        neither leak in nor silently vanish from the accounting)."""
        assert set(SD.CLOSED_CELLS) == CLOSED
        assert CLOSED.isdisjoint(SD.cells())
        assert LICENSED_CELLS | CLOSED == set(EM.cells())

    def test_anchors_never_enter_the_eligible_field(self):
        """MH2.1 (a): the PBO/DSR field is arms + foils only."""
        eligible = SD.eligible_labels()
        assert len(eligible) == 6                       # non-vacuity
        assert set(eligible) == set(SD.REAL_ARMS) | set(SD.FOILS)
        assert set(eligible).isdisjoint(SD.ANCHORS)

    def test_fresh_registration_no_oracle_label_is_a_trial(self):
        """MH2.2: nothing from NF-W6's oracle field is promoted — oracle/matched labels exist
        ONLY as diagnostic anchors."""
        for lab in SD.eligible_labels():
            assert "oracle" not in lab and "matched" not in lab, lab
        assert "oracle_marginal" in SD.ANCHORS and "matched_marginal" in SD.ANCHORS

    def test_the_field_is_a_full_sized_bakeoff(self):
        """§0.5: ≥3 learner classes + the direct-learned foil (`inc_head_bank` — the champion's
        own direct-learned mean in the minimal distributional costume)."""
        assert len(SD.REAL_ARMS) >= 3
        assert "inc_head_bank" in SD.FOILS and "inc_climatology" in SD.FOILS

    def test_fdr_families_are_disjoint_and_cover_every_cell(self):
        fams = SD.fdr_families()
        yards, tds = set(fams["yards"]), set(fams["tds"])
        assert yards.isdisjoint(tds)
        assert len(yards) == 6 and len(tds) == 2
        assert yards | tds == {f"w6b_arm_{c}" for c in SD.cells()}

    def test_shared_machinery_is_imported_not_retyped(self):
        assert SD.EVAL_LEVELS is MC.EVAL_LEVELS and len(SD.EVAL_LEVELS) == 199
        assert SD.fdr_two_families is EM.fdr_two_families_w6
        assert SD.score_bank is EM.score_bank
        assert SD.paired_ci95 is EM.paired_ci95
        assert (SD.PBO_MAX, SD.DSR_MIN, SD.FDR_Q) == (WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q)
        assert SD.TEST_BLOCKS is WP.TEST_BLOCKS

    def test_ppr_weights_are_the_ppr_map_for_the_open_stats_only(self):
        assert SD.PPR_WEIGHTS == {"passing_yards": 0.04, "passing_tds": 4.0,
                                  "rushing_yards": 0.1, "rushing_tds": 6.0,
                                  "receiving_yards": 0.1}
        assert set(SD.PPR_WEIGHTS) == set(SD.STATS)

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        assert _PREREG.exists(), "the narrative pre-registration must be committed before the run"
        text = _PREREG.read_text()
        for token in ("crps_q199", "FRESH REGISTRATION", "deploy-held", "BINDING",
                      "lgbm_hurdle_tail", "zero atom", "NF1.9 (e)", "REPORT-ONLY",
                      "CONSTRAINT_REFUSED", "MH2.2", "RB rushing_tds", "stay closed"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_no_mae_anywhere(self):
        """NF-D11/D14: MAE inverts at the conditional median on zero-heavy targets — never
        computed. AST scan (prose must neither satisfy nor trip)."""
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
        """NF-W3 (c): 4× hand-corrected — the null states are hand-derived. Call-site regex
        (DSR-CONV #690: never grep a bare name)."""
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            assert not re.search(r"classify_null\s*\(", src), f"classify_null call in {path.name}"

    def test_coverage_is_never_a_target(self):
        """⛔ E2.1-r: no fitting objective may reference |coverage − floor|; no fit_* function
        may read the floor."""
        src = _stripped_source(_MODULE)
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", src)
        for m in re.finditer(r"def (arm_\w+|fit_\w+)\(.*?(?=\ndef |\Z)", src, re.S):
            assert "COVERAGE_FLOOR" not in m.group(0), (
                f"{m.group(1)} references the coverage floor — a floor must never be fit toward")

    def test_the_hurdle_classifier_is_champion_faithful(self):
        """The hurdle's P(0) classifier must be the champion hurdle's construction, verbatim —
        the same literal parameter block in both sources."""
        lit = "n_estimators=250, learning_rate=0.06, num_leaves=63, min_child_samples=40"
        sd_src = _stripped_source(_MODULE)
        clf_block = sd_src.split("def _hurdle_clf", 1)[1].split("\ndef ", 1)[0]
        assert lit in clf_block
        wp_src = _stripped_source(Path(WP.__file__))
        hurdle_block = wp_src.split("def fit_lgbm_hurdle", 1)[1].split("\ndef ", 1)[0]
        assert lit in hurdle_block, "the champion hurdle changed — re-verify faithfulness"

    def test_deploy_held_no_serving_or_cloud_writes(self):
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            for token in ("boto3", "put_object", "upload_file", "write_serving_store",
                          "sub_model_registry"):
                assert token not in src, f"deploy-held violation: `{token}` in {path.name}"

    def test_the_runner_pins_the_fold_bank_set_to_the_declared_field(self):
        """The run_fold label-set assert is present (a drifted bank dict must fail loud)."""
        src = _stripped_source(_RUNNER)
        assert "set(banks) == set(SD.all_labels())" in src

    def test_the_runner_deflates_the_eligible_subset_and_trials_are_real_arms(self):
        src = _stripped_source(_RUNNER)
        assert "NF18.deflate(crps[eligible], subset=eligible)" in src
        assert "eligible = SD.eligible_labels()" in src
        assert "for arm in SD.REAL_ARMS:" in src        # the DSR trial field = real arms only


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The hurdle mixture (the atom priced exactly)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMixture:
    def test_p0_zero_reproduces_the_conditional(self):
        cond = np.linspace(1.0, 80.0, 199)
        out = SD.mixture_quantiles199(0.0, cond)
        assert np.allclose(out, cond)

    def test_p0_one_is_the_point_mass_at_zero(self):
        cond = np.linspace(1.0, 80.0, 199)
        assert np.allclose(SD.mixture_quantiles199(1.0, cond), 0.0)

    def test_the_atom_sits_at_its_fitted_mass(self):
        cond = np.linspace(1.0, 80.0, 199)             # strictly positive conditional
        p0 = 0.4
        out = SD.mixture_quantiles199(p0, cond)
        u = SD.EVAL_LEVELS
        assert np.allclose(out[u <= p0], 0.0)          # the atom occupies [0, p0]
        assert (out[u > p0 + 0.01] > 0.0).all()
        assert (np.diff(out) >= -1e-12).all()          # monotone

    def test_a_negative_conditional_tail_lands_below_the_atom(self):
        """Yards can be negative — the mixture must place negative conditional mass BELOW the
        zero atom, exactly the WP._mixture_quantiles convention."""
        cond = np.linspace(-10.0, 80.0, 199)
        p0 = 0.3
        out = SD.mixture_quantiles199(p0, cond)
        neg_mass = (1 - p0) * float((cond < 0).mean())
        u = SD.EVAL_LEVELS
        assert (out[u <= neg_mass - 0.01] < 0.0).all()
        band = (u > neg_mass + 0.005) & (u <= neg_mass + p0)
        assert np.allclose(out[band], 0.0)
        assert (np.diff(out) >= -1e-12).all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Permutation substrate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _perm_frame(n_per: int = 30) -> pd.DataFrame:
    rows = []
    for gw in (1, 2, 3):
        for p in SD.POSITIONS:
            for i in range(n_per):
                rows.append({"position": p, "gw": gw,
                             "rushing_yards": float(gw * 100 + i)})
    return pd.DataFrame(rows)


class TestPermutation:
    def test_multiset_preserved_within_pos_week_and_broken_rowwise(self):
        df = _perm_frame()
        y = SD.permute_stat_within_pos_week(df, "rushing_yards")
        orig = df["rushing_yards"].to_numpy(float)
        assert not np.array_equal(y, orig)              # the link is actually destroyed
        keys = df["position"].astype(str) + "|" + df["gw"].astype(str)
        for k in keys.unique():
            sel = (keys == k).to_numpy()
            assert sorted(y[sel]) == sorted(orig[sel]), k   # marginals intact per group

    def test_deterministic_per_stat_and_distinct_across_stats(self):
        df = _perm_frame()
        df["receiving_yards"] = df["rushing_yards"] * 1.0
        a = SD.permute_stat_within_pos_week(df, "rushing_yards")
        b = SD.permute_stat_within_pos_week(df, "rushing_yards")
        c = SD.permute_stat_within_pos_week(df, "receiving_yards")
        assert np.array_equal(a, b)
        assert not np.array_equal(a, c)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Gate composition — one ISOLATING fixture per clause + RED-proof per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"required": 6, "attainable": True, "passes": True},
        "pbo": 0.05, "dsr": 0.99,
        "coverage": {"blocking_shortfall": False},
        "anchors": {"nihilist_loses": True, "zero_width_loses": True, "max_width_loses": True,
                    "winner_beats_permuted": True, "permuted_lift_not_significant": True,
                    "winner_beats_oracle_marginal": True, "oracle_marginal_beats_matched": True},
    }


#: (check name, sel mutation) — each mutation flips EXACTLY its own clause on the passing base.
_CLAUSE_BREAKS: list[tuple[str, dict]] = [
    ("beats_foil", {"beats_foil": False}),
    ("fold_consistency", {"fold_clause": {"required": 6, "attainable": True, "passes": False}}),
    ("pbo_ok", {"pbo": 0.5}),
    ("dsr_ok", {"dsr": 0.5}),
    ("coverage_floor_ok", {"coverage": {"blocking_shortfall": True}}),
]


class TestGateComposition:
    def test_the_passing_base_ships(self):
        g = SD.compose_gate_w6b(_passing_sel(), fdr_pass=True)
        assert g["ship"] and all(g["checks"].values())

    @pytest.mark.parametrize("check,mut", _CLAUSE_BREAKS)
    def test_each_statistical_clause_isolates(self, check, mut):
        sel = {**_passing_sel(), **mut}
        g = SD.compose_gate_w6b(sel, fdr_pass=True)
        assert not g["ship"]
        failing = [k for k, v in g["checks"].items() if not v]
        assert failing == [check]                       # exactly one clause flipped (NF-D17)

    def test_fdr_clause_isolates(self):
        g = SD.compose_gate_w6b(_passing_sel(), fdr_pass=False)
        assert [k for k, v in g["checks"].items() if not v] == ["fdr_ok"]

    def test_none_pbo_and_none_dsr_fail_closed(self):
        for mut in ({"pbo": None}, {"dsr": None}):
            g = SD.compose_gate_w6b({**_passing_sel(), **mut}, fdr_pass=True)
            assert not g["ship"]

    @pytest.mark.parametrize("anchor", ["nihilist_loses", "zero_width_loses", "max_width_loses"])
    def test_each_degenerate_flips_the_degenerates_clause(self, anchor):
        sel = _passing_sel()
        sel["anchors"][anchor] = False
        g = SD.compose_gate_w6b(sel, fdr_pass=True)
        assert [k for k, v in g["checks"].items() if not v] == ["degenerates_lose"]

    @pytest.mark.parametrize("anchor", ["winner_beats_permuted", "permuted_lift_not_significant"])
    def test_each_permutation_leg_flips_the_permutation_clause(self, anchor):
        sel = _passing_sel()
        sel["anchors"][anchor] = False
        g = SD.compose_gate_w6b(sel, fdr_pass=True)
        assert [k for k, v in g["checks"].items() if not v] == ["permutation_behaves"]

    def test_report_only_oracle_anchors_never_gate(self):
        """The marginal-oracle pair is REPORTED, never a veto (the NF-W1 stance) — flipping it
        must not move the gate."""
        sel = _passing_sel()
        sel["anchors"]["winner_beats_oracle_marginal"] = False
        sel["anchors"]["oracle_marginal_beats_matched"] = False
        assert SD.compose_gate_w6b(sel, fdr_pass=True)["ship"]

    def test_red_proof_every_clause_is_load_bearing(self):
        """Delete each clause from the composed gate in-process and prove its isolating fixture
        now SHIPS — a clause whose deletion changes nothing observable is decoration (NF-D17;
        mutation asserted to land — E11.24 #682). Loops assert non-vacuity."""
        red_targets = [
            ("beats_foil", '"beats_foil": bool(sel["beats_foil"])',
             '"beats_foil": True', {"beats_foil": False}, True),
            ("fold_consistency", '"fold_consistency": bool(sel["fold_clause"]["passes"])',
             '"fold_consistency": True',
             {"fold_clause": {"required": 6, "attainable": True, "passes": False}}, True),
            ("pbo_ok", '"pbo_ok": sel["pbo"] is not None and sel["pbo"] < PBO_MAX',
             '"pbo_ok": True', {"pbo": 0.5}, True),
            ("dsr_ok", '"dsr_ok": sel["dsr"] is not None and sel["dsr"] >= DSR_MIN',
             '"dsr_ok": True', {"dsr": 0.5}, True),
            ("coverage_floor_ok",
             '"coverage_floor_ok": not sel["coverage"]["blocking_shortfall"]',
             '"coverage_floor_ok": True', {"coverage": {"blocking_shortfall": True}}, True),
            ("fdr_ok", '"fdr_ok": bool(fdr_pass)', '"fdr_ok": True', {}, False),
        ]
        assert len(red_targets) >= 6                    # non-vacuity of the loop itself
        for check, old, new, mut, fdr in red_targets:
            mod = _mutated(_MODULE, old, new, f"sd_mut_{check}")
            sel = {**_passing_sel(), **mut}
            g = mod.compose_gate_w6b(sel, fdr_pass=fdr)
            assert g["ship"], f"deleting `{check}` did not flip the verdict — vacuous clause"

    def test_red_proof_anchor_clauses_are_load_bearing(self):
        for check, old, new, anchor in [
            ("degenerates_lose", '"degenerates_lose": bool(sel["anchors"]["nihilist_loses"]',
             '"degenerates_lose": bool(True or sel["anchors"]["nihilist_loses"]',
             "nihilist_loses"),
            ("permutation_behaves",
             '"permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]',
             '"permutation_behaves": bool(True or sel["anchors"]["winner_beats_permuted"]',
             "winner_beats_permuted"),
        ]:
            mod = _mutated(_MODULE, old, new, f"sd_mut_{check}")
            sel = _passing_sel()
            sel["anchors"][anchor] = False
            assert mod.compose_gate_w6b(sel, fdr_pass=True)["ship"], (
                f"deleting `{check}` did not flip the verdict")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Null classification (hand states; the NF-W7 coverage rule)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _sel_for_classify(**over) -> dict:
    base = {**_passing_sel(),
            "binding_foil": "inc_head_bank", "mean_delta": 0.5, "fold_wins": 7,
            "ci95": [0.1, 0.9], "observed_sr": 1.2, "p_one_sided": 0.01}
    base.update(over)
    return base


class TestNullClassification:
    def test_an_all_green_gate_classifies_none(self):
        sel = _sel_for_classify()
        checks = SD.compose_gate_w6b(sel, fdr_pass=True)["checks"]
        assert SD.classify_cell_null(sel, checks, 8) is None

    def test_losing_on_average_is_genuine_absence_with_no_trigger(self):
        sel = _sel_for_classify(beats_foil=False, mean_delta=-0.2)
        checks = SD.compose_gate_w6b(sel, fdr_pass=True)["checks"]
        out = SD.classify_cell_null(sel, checks, 8)
        assert out["state"] == "GENUINE_ABSENCE" and out["retest_trigger"] is None

    def test_a_positive_underpowered_cell_is_power_limited_in_folds(self):
        sel = _sel_for_classify(dsr=0.5, observed_sr=0.6)
        checks = SD.compose_gate_w6b(sel, fdr_pass=True)["checks"]
        out = SD.classify_cell_null(sel, checks, 8)
        assert out["state"] == "POWER_LIMITED"
        assert "folds" in out["retest_trigger"]

    def test_coverage_only_refusal_is_constraint_refused_never_power_limited(self):
        """The NF-W7 classifier rule: a coverage-floor-only refusal must classify
        CONSTRAINT_REFUSED — no fold count can move a constraint."""
        sel = _sel_for_classify(coverage={"blocking_shortfall": True})
        checks = SD.compose_gate_w6b(sel, fdr_pass=True)["checks"]
        out = SD.classify_cell_null(sel, checks, 8)
        assert out["state"] == "CONSTRAINT_REFUSED" and out["retest_trigger"] is None

    def test_anchor_only_refusal_is_constraint_refused(self):
        sel = _sel_for_classify()
        sel["anchors"]["zero_width_loses"] = False
        checks = SD.compose_gate_w6b(sel, fdr_pass=True)["checks"]
        out = SD.classify_cell_null(sel, checks, 8)
        assert out["state"] == "CONSTRAINT_REFUSED" and out["retest_trigger"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Report-only layers + structural coverage note
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestReportOnlyLayers:
    def test_ppr_report_scales_by_weight_and_sums_per_position(self):
        sels = {"QB|passing_yards": {"mean_delta": 1.0},
                "QB|passing_tds": {"mean_delta": 0.01},
                "RB|rushing_tds": {"mean_delta": None}}
        out = SD.ppr_report(sels)
        assert out["per_cell_points_units"]["QB|passing_yards"] == pytest.approx(0.04)
        assert out["per_cell_points_units"]["QB|passing_tds"] == pytest.approx(0.04)
        assert out["per_cell_points_units"]["RB|rushing_tds"] is None
        assert out["per_position_sum_points_units"]["QB"] == pytest.approx(0.08)
        assert "RB" not in out["per_position_sum_points_units"]
        assert "REPORT-ONLY" in out["note"]

    def test_structural_coverage_note_is_atom_plus_ninety_pct_of_the_rest(self):
        assert SD.structural_coverage_note(0.0) == pytest.approx(0.9)
        assert SD.structural_coverage_note(0.5) == pytest.approx(0.95)
        assert SD.structural_coverage_note(1.0) == pytest.approx(1.0)

    def test_decide_story_counts_and_names_cells(self):
        gates = {"A|x": {"ship": True}, "B|y": {"ship": False}, "C|z": {"ship": True}}
        out = SD.decide_story(gates)
        assert out["ship_cells"] == ["A|x", "C|z"] and out["null_cells"] == ["B|y"]
        assert "ship=2 null=1 of 3" in out["headline"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. select_cell end-to-end WITHOUT fits (synthetic fold scores through the real runner layer)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _score(crps: float, cov: float = 0.85, pred_p0: float = 0.5, real_p0: float = 0.5,
           n: int = 500) -> dict:
    return {"crps_q199": crps, "coverage_80": cov, "pred_p0": pred_p0,
            "real_p0": real_p0, "n": n}


def _fold_results(n_folds: int = 8, winner_cov: float = 0.85) -> list[dict]:
    """8 synthetic folds for one cell: `lgbm_hurdle_tail` beats everything, degenerates lose,
    the permuted arm sits at the foil's level (no significant lift)."""
    frs = []
    for i in range(n_folds):
        jit = 0.001 * i
        scores = {
            "lgbm_hurdle_tail": _score(4.0 + jit, cov=winner_cov),
            "lgbm_quantile_tail": _score(4.3 + jit),
            "enet_residual": _score(4.6 + jit),
            "knn_quantile": _score(4.5 + jit),
            "inc_head_bank": _score(5.0 + jit + 0.02 * ((-1) ** i)),
            "inc_climatology": _score(5.4 + jit),
            "nihilist_zero": _score(9.0),
            "zero_width": _score(7.0),
            "max_width": _score(6.5),
            "permuted_quantile": _score(5.01 + jit + 0.03 * ((-1) ** i)),
            "oracle_marginal": _score(5.2),
            "matched_marginal": _score(5.3),
        }
        frs.append({"label": f"202{2 + i // 2}H{1 + i % 2}", "n_test": 500,
                    "cells": {"RB|rushing_yards": {"scores": scores, "cal_split": {}}}})
    return frs


class TestSelectCellEndToEnd:
    def _select(self, **kw):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6b_stat_distributions as R,
        )
        return R.select_cell(_fold_results(**kw), "RB|rushing_yards", 8)

    def test_selection_and_gates_on_a_clean_winner(self):
        sel = self._select()
        assert sel["winner"] == "lgbm_hurdle_tail"
        assert sel["binding_foil"] == "inc_head_bank"   # the better foil binds
        assert sel["beats_foil"] and sel["fold_wins"] == 8
        assert sel["pbo"] is not None and sel["dsr"] is not None
        assert all(sel["anchors"][k] for k in
                   ("nihilist_loses", "zero_width_loses", "max_width_loses",
                    "winner_beats_permuted", "permuted_lift_not_significant"))
        g = SD.compose_gate_w6b(sel, fdr_pass=True)
        assert g["ship"], g["checks"]

    def test_the_coverage_floor_is_one_sided_high_coverage_never_blocks(self):
        """The prereg §2 clause operationalized: 0.97 pooled coverage (the structural atom
        excess) must NOT block; 0.70 with n=4000 must."""
        sel_hi = self._select(winner_cov=0.97)
        assert not sel_hi["coverage"]["blocking_shortfall"]
        sel_lo = self._select(winner_cov=0.70)
        assert sel_lo["coverage"]["blocking_shortfall"]
        assert sel_lo["coverage"]["structural_expectation"] == SD.structural_coverage_note(0.5)

    def test_trial_srs_field_is_exactly_the_real_arms(self):
        sel = self._select()
        assert len(sel["trial_srs"]) == len(SD.REAL_ARMS)

    def test_era_note_is_report_only_and_splits_on_capture_folds(self):
        sel = self._select()
        assert set(sel["era_note"]["capture_folds"]) <= set(SD.CAPTURE_ERA_FOLDS)
        assert "REPORT-ONLY" in sel["era_note"]["note"]

    def test_derive_verdict_layer_composes_fdr_gates_and_ppr(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6b_stat_distributions as R,
        )
        out = {"n_folds": 8, "fold_results": _fold_results()}
        layer = R.derive_verdict_layer(out)
        assert set(layer["selections"]) == {"RB|rushing_yards"}
        assert "RB|rushing_yards" in layer["verdict"]["cells"]
        assert layer["ppr_report"]["per_cell_points_units"]["RB|rushing_yards"] is not None
        assert layer["headline"].startswith("PERSTAT-BAKEOFF")
        # partial-field runs (only-stat path proofs) must not KeyError on absent cells
        assert layer["fdr"]["binding"].get("w6b_arm_RB|rushing_yards") in (True, False)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Arms on synthetic data (the cheap real-fit path proof; kNN/enet + mixture shape)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _synth_frame(n_per_pos_gw: int = 12, gws: int = 10, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for gw in range(1, gws + 1):
        for p in SD.POSITIONS:
            for _ in range(n_per_pos_gw):
                f1 = rng.normal()
                zero = rng.random() < (0.6 if p in ("QB", "TE") else 0.35)
                y = 0.0 if zero else float(np.exp(rng.normal(3.0 + 0.5 * f1, 0.6)))
                rows.append({"position": p, "gw": gw, "f1": f1, "f2": rng.normal(),
                             "f3": rng.normal(), "rushing_yards": y})
    return pd.DataFrame(rows)


class TestArmsOnSyntheticData:
    # real LGBM/kNN fits (>5s) — slow tier by the marker rule; still on the merge bar
    pytestmark = [pytest.mark.slow]
    FEATS = ["f1", "f2", "f3"]

    @pytest.fixture()
    def frames(self, monkeypatch):
        monkeypatch.setattr(MC, "CAL_MIN_ROWS", 100)
        df = _synth_frame()
        train = df[df["gw"] <= 8].reset_index(drop=True)
        test = df[df["gw"] > 8].reset_index(drop=True)
        return train, test

    def test_knn_prices_the_atom_and_is_monotone(self, frames):
        train, test = frames
        out = SD.arm_knn_quantile(train, test, self.FEATS, "rushing_yards", k=40)
        assert out.shape == (len(test), 199)
        assert (np.diff(np.sort(out, axis=1), axis=1) >= -1e-9).all()
        qb = (test["position"] == "QB").to_numpy()
        assert (out[qb][:, :40] == 0.0).mean() > 0.5    # ~60% atom → low quantiles at 0

    def test_enet_residual_shapes_and_finiteness(self, frames):
        train, test = frames
        out, note = SD.arm_enet_residual(train, test, self.FEATS, "rushing_yards")
        assert out.shape == (len(test), 199)
        assert np.isfinite(out).all()
        assert note["n_cal"] >= 100

    def test_quantile_tail_arm_runs_and_is_monotone(self, frames):
        train, test = frames
        out, _ = SD.arm_lgbm_quantile_tail(train, test, self.FEATS, "rushing_yards")
        assert out.shape == (len(test), 199)
        assert (np.diff(out, axis=1) >= -1e-9).all()
        assert np.isfinite(out).all()

    def test_hurdle_arm_places_an_atom(self, frames):
        train, test = frames
        out, _ = SD.arm_lgbm_hurdle_tail(train, test, self.FEATS, "rushing_yards")
        assert out.shape == (len(test), 199)
        assert (np.diff(out, axis=1) >= -1e-9).all()
        qb = (test["position"] == "QB").to_numpy()
        share_zero = (np.abs(out[qb]) < 1e-9).mean(axis=1)
        assert share_zero.mean() > 0.2                  # the atom is expressed on the grid

    def test_the_reducer_refuses_a_non_finite_bank(self):
        bad = np.full((3, 199), 1.0)
        bad[1, 5] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            SD.score_bank(bad, np.array([1.0, 2.0, 3.0]))
