"""Guards for NF-W6d — distributional outputs for ALL optimizer-input metrics (the per-stat
distribution substrate: Phase A ceiling gate · Phase B bake-off · Phase C calibrated defaults ·
dispatch-only serving).

Fast-gate, no IO: everything exercises the PURE modules (`stat_distributions_d`,
`stat_distribution_serving_d`); runners are imported only INSIDE test methods (module scope is
IO-free; lake reads live in functions).

Discipline (NF-W6b / W6b-C / W6c suites, plus this story's own):
  · every gate clause has an ISOLATING fixture (NF-D17) and is RED-proved by deleting it
    in-process with the mutation ASSERTED TO LAND (E11.24 #682);
  · any RED proof wrapping a `pytest.raises` clause catches `BaseException` — pytest's `Failed`
    is NOT an `Exception` (NF-W6c);
  · iterating guards assert NON-VACUITY first (DSR-CONV #690); source scans run comment-stripped;
    structural checks use AST (INC-38 / NF-W3);
  · ⛔ no linear-residual / plain-quantile arm and no head+bank foil on the EVENT class;
  · `cv_power.classify_null` IS wired with `declared_field_size` (MH2.7) and the DSR MECHANISM
    is attached (NF-W6b-C);
  · the reproduction control is EXACT (byte-identical) and RED-proved against a tolerant mutant;
  · a Phase-C default is chosen by ORDER + calibration, NEVER by CRPS (RED-proved);
  · the served map is READ from records fail-closed, forms dispatch by IDENTITY, no learner import.
"""
from __future__ import annotations

import ast
import json
import re
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import stat_distribution_serving as SDS
from quant_sports_intel_models.football.nfl.fantasy import stat_distribution_serving_d as SDSD
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_c as SDC
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_d as SDD
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_MODULE = Path(SDD.__file__)
_SERVING = Path(SDSD.__file__)
_DIR = _MODULE.parent
_RUNNERS = {p: _DIR / f"run_nf_w6d_{p}.py" for p in
            ("ceiling_gate", "stat_bakeoff", "defaults", "serve_stat_distributions")}
_PREREG = _DIR / "ablation_results" / "nf_w6d_preregistration.md"
_W6B_JSON = _DIR / "ablation_results" / "nf_w6b_stat_distributions.json"
_W6BC_JSON = _DIR / "ablation_results" / "nf_w6b_c_rb_rush_tds.json"


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first
    (E11.24 #682: a RED proof that can silently no-op its own break reports a false catch)."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    assert src.count(old) == 1, (
        f"RED-proof target is ambiguous ({src.count(old)} occurrences) in {path.name}: {old!r}")
    mutated = src.replace(old, new, 1)
    assert mutated != src, "the mutation did not change the source — the RED-proof would no-op"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(mutated, str(path), "exec"), mod.__dict__)  # noqa: S102 — test harness
    return mod


def _stripped_source(path: Path) -> str:
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The declared universe / classes / families
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPreregistration:
    def test_substrate_is_52_cells_once_each(self):
        SDD.assert_substrate_is_complete()
        cells = SDD.substrate_cells()
        assert len(cells) == 52 == len(set(cells))
        assert set(SDD.ALL_STATS) == set(WP.COMPONENTS) | set(SDD.EXTRA_STATS)
        assert len(SDD.ALL_STATS) == 13
        # the 7 served + 1 withheld + 22 gated + 22 minor
        assert len(SDD.cells()) == 22 and len(SDD.minor_cells()) == 22

    def test_served_prior_matches_the_serving_module(self):
        assert set(SDD.SERVED_CELLS_PRIOR) == set(SDS.SERVED_CELLS)
        assert set(SDD.WITHHELD_PRIOR) == set(SDS.WITHHELD_NULL_CELLS)

    def test_classes_partition_the_gated_stats(self):
        assert set(SDD.COUNT_STATS).isdisjoint(SDD.EVENT_STATS)
        assert set(SDD.COUNT_STATS) | set(SDD.EVENT_STATS) == set(SDD.GATED_STATS)
        with pytest.raises(KeyError):
            SDD.stat_class("passing_yards")            # a served stat is not gated here

    def test_families_and_foils_as_declared(self):
        assert SDD.FAMILY["count"] == ("lgbm_quantile_tail", "lgbm_hurdle_tail",
                                       "knn_quantile", "count_negbin")
        assert SDD.FAMILY["event"] == ("lgbm_hurdle_tail", "knn_quantile", "count_negbin")
        assert SDD.FOILS["event"] == ("inc_climatology",)
        assert SDD.DECLARED_FIELD_SIZE == {"count": 4, "event": 3}
        for cls, arms in SDD.FAMILY.items():
            for a in arms:
                assert SDD.ARM_FORM[a] in SDD.ORACLE_PAIRS      # every arm has its own pair

    def test_banned_classes_never_enter_an_event_field(self):
        for banned in SDD.BANNED_ON_EVENT:
            assert banned not in SDD.FAMILY["event"]
            assert banned not in SDD.FOILS["event"]
            assert banned not in SDD.bakeoff_labels("event")
        # ⛔ enet_residual is called NOWHERE in the module (call-site regex, comment-stripped)
        assert not re.search(r"arm_enet_residual\s*\(", _stripped_source(_MODULE))
        assert not re.search(r"arm_enet_residual\s*\(", _stripped_source(_RUNNERS["stat_bakeoff"]))

    def test_anchors_never_enter_the_eligible_field(self):
        for cls in ("count", "event"):
            elig = set(SDD.eligible_labels(cls))
            assert elig == set(SDD.FAMILY[cls]) | set(SDD.FOILS[cls])
            for lab in SDD.bakeoff_labels(cls):
                if lab not in elig:
                    assert lab.startswith(("oracle_", "matched_", "permuted_")) or lab in SDD.DEGENERATES

    def test_fresh_seed_differs_from_prior_registrations(self):
        assert SDD._SEED not in (SD._SEED, SDC._SEED, EM._SEED)

    def test_shared_machinery_is_imported_by_identity(self):
        assert SDD.arm_lgbm_hurdle_tail is SD.arm_lgbm_hurdle_tail
        assert SDD.arm_lgbm_quantile_tail is SD.arm_lgbm_quantile_tail
        assert SDD.arm_knn_quantile is SD.arm_knn_quantile
        assert SDD.arm_count_negbin is SDC.arm_count_negbin
        assert SDD.matched_window is SDC.matched_window        # the (K−1)/K refinement
        assert SDD.compose_gate_w6bc is SDC.compose_gate_w6bc  # the ten clauses, by identity
        assert SDD.score_bank is EM.score_bank

    def test_matched_controls_are_sized_to_the_peek(self):
        """The conditional forms' matched window is (K−1)/K of the block (W6b-C), the marginal
        keeps the full block (W6)."""
        gw = np.repeat(np.arange(300), 10)
        train = pd.DataFrame({"gw": gw, "position": "RB"})
        test = pd.DataFrame({"gw": [999] * 900, "position": "RB"})
        assert len(SDD.matched_window(train, test)) == round(900 * 2 / 3)
        assert len(EM.matched_n_train(train, test)) == 900

    def test_license_rule_is_marginal_or_yes(self):
        assert SDD.LICENSE_BANDS == ("YES", "MARGINAL")
        assert SDD.CEILING_BANDS == EM.CEILING_BANDS == (2.0, 5.0)

    def test_no_mae_anywhere(self):
        """⛔ MAE is AST-banned in the pure modules and the runners (NF-D11/D14)."""
        for path in (_MODULE, _SERVING, *_RUNNERS.values()):
            tree = ast.parse(path.read_text())
            names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            bad = {s for s in names | attrs if "mae" in s.lower() or "absolute_error" in s.lower()}
            assert not bad, f"{path.name}: {bad}"

    def test_classify_null_is_wired_with_declared_field_size(self):
        tree = ast.parse(_MODULE.read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == "classify_null"]
        assert calls, "classify_null is not called (non-vacuity)"
        for c in calls:
            kws = {k.arg for k in c.keywords}
            assert "declared_field_size" in kws and "degenerates_excluded_from_v" in kws

    def test_deploy_held_no_cloud_writes(self):
        """AST: no boto3/s3 import anywhere; no `--publish` argparse flag (a flag that cannot
        legally be used is a loaded gun); prose mentions in docstrings are not code."""
        for path in (_MODULE, _SERVING, *_RUNNERS.values()):
            tree = ast.parse(path.read_text())
            imported = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    imported |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module:
                    imported.add(n.module.split(".")[0])
            assert imported.isdisjoint({"boto3", "botocore", "s3fs"}), path.name
            flags = {a.value for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Attribute) and n.func.attr == "add_argument"
                     for a in n.args if isinstance(a, ast.Constant)}
            assert "--publish" not in flags, path.name

    def test_the_preregistration_declares_the_story_shape(self):
        txt = _PREREG.read_text()
        for needle in ("20260817", "MARGINAL", "(K−1)/K", "byte-identically", "PIT",
                       "count_negbin", "climatology", "52", "RE-SCORING ASSEMBLY", "MIN_COND_ROWS"):
            assert needle in txt, needle


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Label attach
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _feed(rows):
    cols = ["season", "week", "player_id", "passing_interceptions", "sack_fumbles_lost",
            "rushing_fumbles_lost", "receiving_fumbles_lost", "passing_2pt_conversions",
            "rushing_2pt_conversions", "receiving_2pt_conversions"]
    return pd.DataFrame(rows, columns=cols)


class TestLabelAttach:
    def _feat(self):
        return pd.DataFrame({"season": [2024, 2024, 2024], "week": [1, 1, 2],
                             "gsis_id": ["a", "b", "a"], "position": ["QB", "RB", "QB"]})

    def test_sums_sources_and_fills_zero_for_missing(self):
        feed = _feed([[2024, 1, "a", 2, 1, 0, 0, 1, 0, 1], [2024, 1, "b", 0, 0, 1, 1, 0, 0, 0]])
        out, audit = SDD.attach_extra_labels(self._feat(), feed)
        assert list(out["passing_interceptions"]) == [2, 0, 0]
        assert list(out["fumbles_lost"]) == [1, 2, 0]
        assert list(out["two_pt"]) == [2, 0, 0]
        assert audit["two_pt_filled_zero_rows"] == 1

    def test_duplicate_grain_refuses(self):
        feed = _feed([[2024, 1, "a", 1, 0, 0, 0, 0, 0, 0], [2024, 1, "a", 1, 0, 0, 0, 0, 0, 0]])
        with pytest.raises(ValueError, match="duplicate"):
            SDD.attach_extra_labels(self._feat(), feed)

    def test_second_attach_refuses(self):
        feed = _feed([[2024, 1, "a", 1, 0, 0, 0, 0, 0, 0]])
        out, _ = SDD.attach_extra_labels(self._feat(), feed)
        with pytest.raises(ValueError, match="second attach"):
            SDD.attach_extra_labels(out, feed)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Phase A — selection + decision from synthetic fold scores
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _score(crps, cov=0.95, pred_p0=0.5, real_p0=0.5, n=1000):
    return {"crps_q199": crps, "coverage_80": cov, "pred_p0": pred_p0, "real_p0": real_p0, "n": n}


def _gate_folds(cell="RB|receptions", inc=1.000, best_orc=0.900, n_folds=8,
                inapplicable=(), lift_jitter=0.002):
    cls = SDD.stat_class(cell.split("|", 1)[1])
    frs = []
    for i in range(n_folds):
        jit = lift_jitter * ((-1) ** i)
        s = {"inc_climatology": _score(inc + 0.05 + jit),
             "nihilist_zero": _score(inc + 0.5), "zero_width": _score(inc + 0.3),
             "max_width": _score(inc + 0.4)}
        if "inc_head_bank" in SDD.FOILS[cls]:
            s["inc_head_bank"] = _score(inc + jit)
        for f in SDD.CEILING_FORMS[cls]:
            orc, mat = SDD.ORACLE_PAIRS[f]
            if f in inapplicable:
                s[orc] = None
                s[mat] = None
                continue
            orc_v = best_orc if f == "hurdle" else best_orc + 0.03
            s[orc] = _score(orc_v + jit * 0.5)
            s[mat] = _score(orc_v + 0.01)
        frs.append({"label": f"202{2 + i // 2}H{1 + i % 2}", "n_test": 1000,
                    "cells": {cell: {"scores": s, "stat_class": cls}}})
    return frs


class TestCeilingGate:
    def test_yes_cell_is_licensed(self):
        sel = SDD.select_ceiling(_gate_folds(), "RB|receptions", 8)
        sel["fdr_binding"] = True
        assert sel["binding_incumbent"] == "inc_head_bank"
        assert sel["best_form"] == "hurdle" and sel["ceiling_pct"] > 5
        d = SDD.decide_ceiling(sel)
        assert d["answer"] == "YES" and d["licensed_for_bakeoff"]

    def test_marginal_cell_is_licensed_no_cell_is_not(self):
        sel = SDD.select_ceiling(_gate_folds(best_orc=0.965), "RB|receptions", 8)
        sel["fdr_binding"] = True
        d = SDD.decide_ceiling(sel)
        assert d["answer"] == "MARGINAL" and d["licensed_for_bakeoff"]
        sel = SDD.select_ceiling(_gate_folds(best_orc=0.99), "RB|receptions", 8)
        sel["fdr_binding"] = True
        d = SDD.decide_ceiling(sel)
        assert d["answer"] == "NO" and not d["licensed_for_bakeoff"]

    def test_not_stat_ok_is_no_regardless_of_magnitude(self):
        sel = SDD.select_ceiling(_gate_folds(), "RB|receptions", 8)
        sel["fdr_binding"] = False
        d = SDD.decide_ceiling(sel)
        assert d["answer"] == "NO" and not d["licensed_for_bakeoff"]

    def test_inapplicable_form_is_excluded_and_named(self):
        sel = SDD.select_ceiling(_gate_folds(inapplicable=("hurdle",)), "RB|receptions", 8)
        assert "hurdle" in sel["inapplicable_forms"]
        assert "hurdle" not in sel["per_form"] and sel["best_form"] != "hurdle"

    def test_all_forms_inapplicable_refuses(self):
        frs = _gate_folds(cell="QB|two_pt", inapplicable=tuple(SDD.CEILING_FORMS["event"]))
        with pytest.raises(ValueError, match="unevaluable"):
            SDD.select_ceiling(frs, "QB|two_pt", 8)

    def test_event_class_binding_incumbent_is_the_climatology(self):
        sel = SDD.select_ceiling(_gate_folds(cell="WR|receiving_tds"), "WR|receiving_tds", 8)
        assert sel["binding_incumbent"] == "inc_climatology"
        assert set(sel["per_form"]) == set(SDD.CEILING_FORMS["event"])

    def test_red_proof_license_rule_is_load_bearing(self):
        """Delete MARGINAL from LICENSE_BANDS → a MARGINAL cell is no longer licensed."""
        mod = _mutated(_MODULE, 'LICENSE_BANDS: tuple[str, ...] = ("YES", "MARGINAL")',
                       'LICENSE_BANDS: tuple[str, ...] = ("YES",)', "sdd_mut_license")
        sel = mod.select_ceiling(_gate_folds(best_orc=0.965), "RB|receptions", 8)
        sel["fdr_binding"] = True
        assert mod.decide_ceiling(sel)["licensed_for_bakeoff"] is False

    def test_fdr_two_families_binding_is_own_and_pooled(self):
        fdr = SDD.fdr_two_families({"a": 0.001, "b": 0.5}, {"c": 0.001})
        assert fdr["binding"]["a"] and fdr["binding"]["c"] and not fdr["binding"]["b"]

    def test_min_cond_rows_makes_the_hurdle_form_inapplicable(self):
        """A stat with too few non-zero rows RAISES InapplicableForm (never a silent constant)."""
        n = 300
        test = pd.DataFrame({"position": ["RB"] * n, "gw": [500] * n,
                             "two_pt": [0.0] * (n - 5) + [1.0] * 5})
        with pytest.raises(SDD.InapplicableForm):
            SDD.oracle_hurdle(test, ["x"], "two_pt", "fold")
        train = pd.DataFrame({"position": ["RB"] * n, "gw": np.arange(n),
                              "two_pt": [0.0] * n})
        with pytest.raises(SDD.InapplicableForm):
            SDD.matched_hurdle(train, test, ["x"], "two_pt")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Phase B — selection, gates, null reading, reproduction control
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _bake_folds(cell="WR|receiving_tds", winner="knn_quantile", n_folds=8, w=0.130,
                others=(0.134, 0.140), foil=0.150, permuted=0.151, tie=False):
    cls = SDD.stat_class(cell.split("|", 1)[1])
    frs = []
    arms = list(SDD.FAMILY[cls])
    for i in range(n_folds):
        jit = 0.0005 * i
        s = {}
        k = 0
        for a in arms:
            if a == winner:
                s[a] = _score((foil - 1e-5 if tie else w) + jit)
            else:
                s[a] = _score(others[k % len(others)] + jit)
                k += 1
        for f in SDD.FOILS[cls]:
            s[f] = _score(foil + jit + 0.001 * ((-1) ** i) + (0.02 if f == "inc_head_bank" else 0))
        s["nihilist_zero"] = _score(0.169)
        s["zero_width"] = _score(0.169)
        s["max_width"] = _score(0.230)
        s[f"permuted_{SDD.PERMUTED_FORM[cls]}"] = _score(permuted + jit + 0.002 * ((-1) ** i))
        s["oracle_marginal"] = _score(0.149)
        s["matched_marginal"] = _score(0.1495)
        for a in arms:
            orc, mat = SDD.ORACLE_PAIRS[SDD.ARM_FORM[a]]
            s[orc] = _score(0.125)
            s[mat] = _score(0.133)
        frs.append({"label": f"202{2 + i // 2}H{1 + i % 2}", "n_test": 1000,
                    "cells": {cell: {"scores": s, "stat_class": cls}}})
    return frs


def _deflate_stub(matrix, subset=None):
    return {"pbo": 0.0, "os_gap_pct": 0.0, "contender_spread_pct": 1.0, "flips": []}


class TestBakeoffSelection:
    def test_clean_winner_ships_and_classifies_none(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(), "WR|receiving_tds", 8, _deflate_stub)
        assert sel["winner"] == "knn_quantile" and sel["binding_foil"] == "inc_climatology"
        assert sel["stat_class"] == "event" and len(sel["trial_srs"]) == 3
        assert sel["dsr_mechanism"]["sr0_this_field"] is not None
        g = SDD.compose_gate(sel, fdr_pass=True)
        assert g["ship"], g["checks"]
        assert SDD.classify_null(sel, g["checks"], 8) is None
        assert sel["ppr_points_units"] == pytest.approx(sel["mean_delta"] * 6.0, rel=1e-3)

    def test_count_class_reads_head_bank_as_binding_foil(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(cell="RB|receptions", winner="lgbm_hurdle_tail",
                                                  others=(0.134, 0.140, 0.145)),
                                      "RB|receptions", 8, _deflate_stub)
        assert sel["binding_foil"] == "inc_climatology"      # head_bank +0.02 worse in the fixture
        assert len(sel["trial_srs"]) == 4 and sel["winner_form"] == "hurdle"

    def test_tie_scale_winner_cannot_ship(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(tie=True, others=(0.160, 0.165)),
                                      "WR|receiving_tds", 8, _deflate_stub)
        assert sel["winner"] == "knn_quantile"                # non-vacuity: the tie arm won
        g = SDD.compose_gate(sel, fdr_pass=True)
        assert not g["ship"] and g["checks"]["not_a_foil_tie"] is False

    def test_constraint_only_refusal_is_constraint_refused(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(), "WR|receiving_tds", 8, _deflate_stub)
        sel["coverage"]["blocking_shortfall"] = True
        g = SDD.compose_gate(sel, fdr_pass=True)
        ns = SDD.classify_null(sel, g["checks"], 8)
        assert ns["state"] == "CONSTRAINT_REFUSED" and ns["retest_trigger"] is None

    def test_statistical_null_reads_the_machine_flag_and_the_mechanism(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(), "WR|receiving_tds", 8, _deflate_stub)
        sel["dsr"] = 0.5
        g = SDD.compose_gate(sel, fdr_pass=True)
        ns = SDD.classify_null(sel, g["checks"], 8)
        assert "field_remedy_admissible" in ns and "dsr_mechanism" in ns
        assert ns["classifier"].startswith("cv_power.classify_null")

    def test_dsr_mechanism_flags_unreachable_when_winner_sr_below_sr0(self):
        m = SDD.dsr_mechanism(observed_sr=1.0, trial_srs=[1.0, -9.0, 8.0],
                              arms=("a", "b", "c"))
        assert m["unreachable_in_field"] is True and m["most_dispersing_arm"] == "b"
        m2 = SDD.dsr_mechanism(observed_sr=6.0, trial_srs=[6.0, 5.5, 5.8], arms=("a", "b", "c"))
        assert m2["unreachable_in_field"] is False

    def test_dsr_unreachable_null_carries_the_mechanism_reading(self):
        sel = SDD.select_bakeoff_cell(_bake_folds(), "WR|receiving_tds", 8, _deflate_stub)
        sel["dsr"] = 0.2
        sel["dsr_mechanism"]["unreachable_in_field"] = True
        g = SDD.compose_gate(sel, fdr_pass=True)
        ns = SDD.classify_null(sel, g["checks"], 8)
        assert "DSR-UNREACHABLE IN THIS FIELD" in ns["mechanism_reading"]

    def test_red_proof_declared_field_size_is_load_bearing(self):
        mod = _mutated(_MODULE, "declared_field_size=DECLARED_FIELD_SIZE[cls],",
                       "declared_field_size=None,", "sdd_mut_dfs")
        sel = mod.select_bakeoff_cell(_bake_folds(), "WR|receiving_tds", 8, _deflate_stub)
        sel["dsr"] = 0.5
        g = mod.compose_gate(sel, fdr_pass=True)
        ns_mut = mod.classify_null(sel, g["checks"], 8)
        ns = SDD.classify_null(sel, g["checks"], 8)
        assert ns_mut["detail"].get("declared_field_size_source") != ns["detail"].get(
            "declared_field_size_source")

    def test_derive_verdict_layer_composes(self):
        from quant_sports_intel_models.football.nfl.fantasy import run_nf_w6d_stat_bakeoff as R
        out = {"n_folds": 8, "fold_results": _bake_folds()}
        layer = R.derive_verdict_layer(out)
        assert layer["verdict"]["cells"] == {"WR|receiving_tds": "SHIP"}
        assert layer["verdict"]["winners"] == {"WR|receiving_tds": "knn_quantile"}


class TestReproductionControl:
    def test_reference_reads_both_records_for_the_seven_served_cells(self):
        ref = SDD.reproduction_reference(_W6B_JSON, _W6BC_JSON, dict(SDS.SERVED_CELLS_FROM_W6B),
                                         dict(SDS.SERVED_CELLS_FROM_W6BC))
        assert set(ref) == set(SDS.SERVED_CELLS)
        assert ref["RB|rushing_tds"]["record"] == "NF-W6b-C"
        assert ref["QB|passing_tds"]["record"] == "NF-W6b"
        assert len(ref["QB|passing_tds"]["fold_crps"]) == 8

    def test_check_is_exact_and_flags_any_difference(self):
        ref = SDD.reproduction_reference(_W6B_JSON, _W6BC_JSON, dict(SDS.SERVED_CELLS_FROM_W6B),
                                         dict(SDS.SERVED_CELLS_FROM_W6BC))
        obs = {c: ref[c]["fold_crps"]["2025H2"] for c in ref}
        assert SDD.check_reproduction(ref, "2025H2", obs)["all_reproduce"] is True
        obs["QB|passing_tds"] += 1e-12
        audit = SDD.check_reproduction(ref, "2025H2", obs)
        assert audit["all_reproduce"] is False
        assert audit["cells"]["QB|passing_tds"]["byte_identical"] is False

    def test_unrecorded_fold_refuses(self):
        ref = SDD.reproduction_reference(_W6B_JSON, _W6BC_JSON, dict(SDS.SERVED_CELLS_FROM_W6B),
                                         dict(SDS.SERVED_CELLS_FROM_W6BC))
        with pytest.raises(ValueError, match="not in the"):
            SDD.check_reproduction(ref, "2099H1", {c: 0.0 for c in ref})

    def test_red_proof_a_tolerant_check_is_caught(self):
        mod = _mutated(_MODULE, "same = bool(want == got)",
                       "same = bool(abs(want - got) < 1e-6)", "sdd_mut_repro")
        ref = mod.reproduction_reference(_W6B_JSON, _W6BC_JSON, dict(SDS.SERVED_CELLS_FROM_W6B),
                                         dict(SDS.SERVED_CELLS_FROM_W6BC))
        obs = {c: ref[c]["fold_crps"]["2025H2"] + 1e-12 for c in ref}
        assert mod.check_reproduction(ref, "2025H2", obs)["all_reproduce"] is True   # the mutant
        assert SDD.check_reproduction(ref, "2025H2", obs)["all_reproduce"] is False  # ours

    def test_runner_marks_the_run_invalid_on_mismatch(self):
        """Source-level: the runner exits 2 and writes `invalid: True` on a mismatch."""
        src = _stripped_source(_RUNNERS["stat_bakeoff"])
        assert '"invalid": True' in src and "return 2" in src
        assert "reproduce_served_cells(f, feat, reference)" in src


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Phase C — calibration validation + the ORDER-not-CRPS decision
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pit(dev: float, n: int = 1000) -> dict:
    """A poolable PIT accounting whose pooled max-decile-deviation is `dev`."""
    counts = [n // 10] * 10
    counts[0] += int(dev * n)
    counts[1] -= int(dev * n)
    return {"decile_counts": counts, "n": n, "n_below_grid": 0, "n_above_grid": 0,
            "sum_z": 0.0, "sum_z2": float(n)}


def _default_folds(cell="RB|carries", nb_cov=0.95, nb_dev=0.01, nb_crps=1.0,
                   clim_cov=0.95, clim_dev=0.01, clim_crps=1.2, n_folds=8):
    frs = []
    for i in range(n_folds):
        s = {"nihilist_zero": _score(3.0),
             "count_negbin": {**_score(nb_crps, cov=nb_cov), "pit": _pit(nb_dev)},
             "climatology": {**_score(clim_crps, cov=clim_cov), "pit": _pit(clim_dev)}}
        frs.append({"label": f"f{i}", "n_test": 1000,
                    "cells": {cell: {"scores": s, "kind": "modeled"}}})
    return frs


class TestDefaults:
    def test_first_calibrated_in_order_is_chosen(self):
        d = SDD.decide_default(_default_folds(), "RB|carries")
        assert d["chosen"] == "count_negbin" and d["calibration_warning"] is None
        assert d["order"] == ["count_negbin", "climatology"]

    def test_uncalibrated_first_falls_through_to_next(self):
        d = SDD.decide_default(_default_folds(nb_dev=0.08), "RB|carries")
        assert d["chosen"] == "climatology"
        assert d["reads"]["count_negbin"]["pit_flat_ok"] is False

    def test_coverage_shortfall_also_falls_through(self):
        d = SDD.decide_default(_default_folds(nb_cov=0.70), "RB|carries")
        assert d["chosen"] == "climatology"
        assert d["reads"]["count_negbin"]["coverage_floor_ok"] is False

    def test_none_calibrated_emits_last_with_a_loud_warning(self):
        d = SDD.decide_default(_default_folds(nb_dev=0.08, clim_dev=0.09), "RB|carries")
        assert d["chosen"] == "climatology" and "UNCALIBRATED" in d["calibration_warning"]

    def test_crps_never_decides_a_default(self):
        """A LATER form with far better CRPS is NOT chosen over an earlier calibrated one."""
        d = SDD.decide_default(_default_folds(nb_crps=5.0, clim_crps=0.1), "RB|carries")
        assert d["chosen"] == "count_negbin"

    def test_red_proof_order_is_load_bearing(self):
        mod = _mutated(_MODULE, "chosen = next((f for f in order if reads[f][\"calibrated\"]), None)",
                       "chosen = min(order, key=lambda f: reads[f][\"crps_q199\"])",
                       "sdd_mut_order")
        d = mod.decide_default(_default_folds(nb_crps=5.0, clim_crps=0.1), "RB|carries")
        assert d["chosen"] == "climatology"                   # the mutant picks by CRPS
        assert SDD.decide_default(_default_folds(nb_crps=5.0, clim_crps=0.1),
                                  "RB|carries")["chosen"] == "count_negbin"

    def test_minor_channels_use_the_climatology_only(self):
        assert SDD.default_order_for("QB|receptions") == ("climatology",)
        assert SDD.default_order_for("RB|carries") == ("count_negbin", "climatology")
        # a yards cell (negative values possible) never takes the count default
        assert SDD.default_order_for("RB|receiving_yards") == ("climatology",)

    def test_calibration_scores_see_a_miscalibrated_bank(self):
        """Positive control: a Poisson bank scored on Poisson draws is PIT-flat; the same bank on
        3× draws is not (the instrument must SEE the defect — MH2.1 (d))."""
        from scipy.stats import poisson
        rng = np.random.default_rng(0)
        mu = np.full(4000, 3.0)
        bank = poisson.ppf(SDD.EVAL_LEVELS[None, :], mu[:, None])
        y_ok = rng.poisson(mu)
        y_bad = rng.poisson(mu * 3)
        ok = SDD.calibration_scores(bank, y_ok, np.random.default_rng(1))
        bad = SDD.calibration_scores(bank, y_bad, np.random.default_rng(1))
        assert SDD.pool_pit_stats([ok["pit"]])["max_decile_dev"] <= SDD.PIT_MAX_DECILE_DEV
        assert SDD.pool_pit_stats([bad["pit"]])["max_decile_dev"] > SDD.PIT_MAX_DECILE_DEV

    def test_default_dispatch_is_by_identity(self):
        assert SDD.DEFAULT_DISPATCH["count_negbin"] is SDD.default_count_negbin
        assert SDD.DEFAULT_DISPATCH["climatology"] is SDD.default_climatology
        assert set(SDD.DEFAULT_DISPATCH) == set(SDD.DEFAULT_FORMS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Serving — the record-derived map, dispatch identity, no learner import
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _write_records(tmp: Path, *, licensed=("RB|receptions",), ships=None, smoke=False,
                   invalid=False, defaults_for=None):
    ships = {} if ships is None else ships
    gate = {"story": "NF-W6d", "phase": "A", "smoke": smoke,
            "verdict": {"licensed_cells": list(licensed)}}
    bake = {"story": "NF-W6d", "phase": "B", "smoke": smoke, "invalid": invalid,
            "cell_source": "Phase-A record", "verdict": {"ship_cells": list(ships),
                                                          "winners": dict(ships)}}
    cells = defaults_for or [c for c in SDD.substrate_cells() if c not in SDS.SERVED_CELLS]
    defs = {"story": "NF-W6d", "phase": "C", "smoke": smoke,
            "verdict": {"defaults": {c: "climatology" for c in cells}},
            "decisions": {c: {"chosen": "climatology", "calibration_warning": None}
                          for c in cells}}
    paths = []
    for name, rec in (("gate", gate), ("bake", bake), ("defs", defs)):
        p = tmp / f"{name}.json"
        p.write_text(json.dumps(rec))
        paths.append(p)
    return tuple(paths)


class TestServingMap:
    def test_complete_map_with_precedence(self, tmp_path):
        g, b, d = _write_records(tmp_path, licensed=("RB|receptions", "WR|receiving_tds"),
                                 ships={"RB|receptions": "lgbm_hurdle_tail"})
        smap = SDSD.served_map(g, b, d)
        assert set(smap) == set(SDD.substrate_cells()) and len(smap) == 52
        assert smap["QB|passing_tds"] == {"form": "knn_quantile", "source": "nf_w6b",
                                          "calibration_warning": None}
        assert smap["RB|rushing_tds"]["source"] == "nf_w6b_c"
        assert smap["RB|receptions"] == {"form": "lgbm_hurdle_tail", "source": "nf_w6d_b_ship",
                                         "calibration_warning": None}
        assert smap["WR|receiving_tds"]["source"] == "nf_w6d_c_default"    # a null → default
        assert smap["RB|receiving_yards"]["source"] == "nf_w6d_c_default"  # the withheld prior

    def test_smoke_records_are_refused_by_default_and_allowed_only_for_the_path_proof(self, tmp_path):
        g, b, d = _write_records(tmp_path, smoke=True)
        with pytest.raises(ValueError, match="path proof"):
            SDSD.served_map(g, b, d)
        assert len(SDSD.served_map(g, b, d, allow_path_proof=True)) == 52

    def test_invalid_bakeoff_record_is_refused(self, tmp_path):
        g, b, d = _write_records(tmp_path, invalid=True)
        with pytest.raises(ValueError, match="INVALID"):
            SDSD.served_map(g, b, d)

    def test_missing_bakeoff_record_is_refused_when_cells_were_licensed(self, tmp_path):
        g, b, d = _write_records(tmp_path)
        b.unlink()
        with pytest.raises(FileNotFoundError):
            SDSD.served_map(g, b, d)

    def test_missing_bakeoff_record_is_fine_when_nothing_was_licensed(self, tmp_path):
        g, b, d = _write_records(tmp_path, licensed=())
        b.unlink()
        assert len(SDSD.served_map(g, b, d)) == 52

    def test_a_ship_outside_the_license_is_refused(self, tmp_path):
        g, b, d = _write_records(tmp_path, licensed=("RB|receptions",),
                                 ships={"WR|receptions": "knn_quantile"})
        with pytest.raises(ValueError, match="did not license"):
            SDSD.served_map(g, b, d)

    def test_wrong_phase_is_refused(self, tmp_path):
        g, b, d = _write_records(tmp_path)
        with pytest.raises(ValueError, match="story/phase"):
            SDSD.served_map(d, b, g)

    def test_incomplete_defaults_refuse(self, tmp_path):
        g, b, d = _write_records(tmp_path, defaults_for=["RB|carries"])
        with pytest.raises(ValueError, match="incomplete"):
            SDSD.served_map(g, b, d)

    def test_dispatch_targets_are_certified_functions_by_identity(self):
        assert SDSD.ARM_DISPATCH_D["lgbm_hurdle_tail"] is SD.arm_lgbm_hurdle_tail
        assert SDSD.ARM_DISPATCH_D["lgbm_quantile_tail"] is SD.arm_lgbm_quantile_tail
        assert SDSD.ARM_DISPATCH_D["knn_quantile"] is SDS.ARM_DISPATCH["knn_quantile"]
        assert SDSD.ARM_DISPATCH_D["count_negbin"] is SDC.arm_count_negbin
        assert SDSD.ARM_DISPATCH_D["climatology"] is SDD.default_climatology
        assert set(SDSD.ARM_DISPATCH_D) == {"lgbm_quantile_tail", "lgbm_hurdle_tail",
                                            "knn_quantile", "count_negbin", "climatology"}

    def test_serving_module_imports_no_learner_and_never_fits(self):
        tree = ast.parse(_SERVING.read_text())
        imported = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                imported |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module.split(".")[0])
        assert imported.isdisjoint({"lightgbm", "sklearn", "scipy", "xgboost", "ngboost"})
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert attrs.isdisjoint({"fit", "predict", "predict_proba", "kneighbors"})

    def test_served_rows_carry_source_and_the_w6c_contract(self):
        serve = pd.DataFrame({"gsis_id": ["a", "b"], "position": ["RB", "RB"], "team": ["X", "Y"],
                              "season": [2025, 2025], "week": [1, 1], "gw": [170, 170]})
        bank = np.tile(np.linspace(0, 10, SDSD.N_LEVELS), (2, 1))
        rows = SDSD.served_rows(serve, bank, "RB|carries", "climatology", "nf_w6d_c_default", None)
        assert list(rows.columns[:5]) == ["cell", "stat", "form", "source", "calibration_warning"]
        for c in SDS.SUMMARY_COLUMNS:
            assert c in rows.columns
        assert rows["q50"].iloc[0] == pytest.approx(bank[0, SDS.IDX_Q50])
        with pytest.raises(ValueError):
            SDSD.served_rows(serve, bank[:1], "RB|carries", "climatology", "x", None)

    def test_manifest_strings_pass_the_denylist_and_name_the_follow_on(self, tmp_path):
        g, b, d = _write_records(tmp_path, licensed=())
        b.unlink()
        m = SDSD.representation_manifest(SDSD.served_map(g, b, d))
        assert m["n_cells"] == 52 and "parity tax" in m["follow_on"]
        SDD.screen_copy("t", m["uncertainty_framing"])
        with pytest.raises(ValueError, match="banned"):
            SDD.screen_copy("t", "this distribution beats the market")

    def test_same_registry_target_new_version(self):
        assert SDSD.REGISTRY_TARGET == SDS.REGISTRY_TARGET == "weekly_stat_distribution"
        assert SDSD.SERVED_VERSION != SDS.SERVED_VERSION
        assert len(SDSD.PROMOTE_BLOCKERS) == len(SDS.PROMOTE_BLOCKERS) + 1


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. RED-proof of a pytest.raises clause (catches BaseException — NF-W6c)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRedProofHygiene:
    def test_red_proof_min_cond_rows_refusal_is_load_bearing(self):
        """Delete the floor (set it to 0) → the InapplicableForm clause no longer raises; the
        proof wraps a `pytest.raises` so it MUST catch BaseException."""
        mod = _mutated(_MODULE, "MIN_COND_ROWS = 40", "MIN_COND_ROWS = 0", "sdd_mut_cond")
        n = 300
        test = pd.DataFrame({"position": ["RB"] * n, "gw": [500] * n,
                             "two_pt": [0.0] * (n - 5) + [1.0] * 5})
        caught = None
        try:
            with pytest.raises(mod.InapplicableForm):
                mod._assert_cond_rows(3, "x", "two_pt")
        except BaseException as e:  # noqa: BLE001 — pytest.Failed derives from BaseException
            caught = e
        assert caught is not None, "the mutation did not disarm the floor — RED proof vacuous"
        with pytest.raises(SDD.InapplicableForm):
            SDD._assert_cond_rows(3, "x", "two_pt")
        del test
