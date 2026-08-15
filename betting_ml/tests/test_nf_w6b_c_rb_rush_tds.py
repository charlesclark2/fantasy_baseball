"""Guards for NF-W6b-C — RB rushing_tds fresh-family successor (§0.5 bake-off).

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.stat_distributions_c`); the runner is imported
only INSIDE test methods (its module scope is IO-free; its lake reads live in functions).

Discipline inherited from the NF-W6b suite plus this story's own requirements:
  · every gate clause has an ISOLATING fixture (NF-D17) and is RED-proved by deleting it
    in-process with the mutation ASSERTED TO LAND (E11.24 #682);
  · any RED proof wrapping a `pytest.raises` clause catches `BaseException` — pytest's
    `Failed` is NOT an `Exception` (the NF-W6c lesson);
  · iterating guards assert NON-VACUITY first (DSR-CONV #690); source scans run
    comment-stripped; structural checks use AST (INC-38/NF-W3);
  · ⛔ the linear-residual class is pinned OUT of the field (the whole point of the story);
  · `cv_power.classify_null` IS wired here — with `declared_field_size` stated, the record
    reading `field_remedy_admissible` (MH2.7) — the inverse of the W6b never-call guard;
  · the serving pin: RB|rushing_tds stays OUT of NF-W6c's dispatch regardless of verdict.
"""
from __future__ import annotations

import re
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions as SD
from quant_sports_intel_models.football.nfl.fantasy import stat_distributions_c as SDC

_MODULE = Path(SDC.__file__)
_RUNNER = _MODULE.parent / "run_nf_w6b_c_rb_rush_tds.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w6b_c_preregistration.md"


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first
    (E11.24 #682: a RED proof that can silently no-op its own break reports a false catch)."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    # ⚠️ an AMBIGUOUS target lands the break on the wrong occurrence (a docstring quoting the
    # code) — the break "lands" but not where the proof needs it. Refuse rather than guess.
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
# 1. The fresh field — coherent, atom-aware, and exactly what was declared
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFreshFieldPreregistration:
    def test_one_cell_only_and_the_td_no_cells_stay_closed(self):
        assert SDC.cells() == ("RB|rushing_tds",)
        assert SDC.CELL == "RB|rushing_tds"
        # ⛔ the four TD-NO cells cannot leak in: the module has no cell map beyond CELL
        assert set(SDC.cells()).isdisjoint(SD.CLOSED_CELLS)

    def test_the_family_is_exactly_the_declared_three_atom_aware_arms(self):
        assert SDC.REAL_ARMS == ("lgbm_hurdle_tail", "knn_quantile", "count_negbin")
        assert SDC.FOILS == ("inc_climatology",)
        assert SDC.DECLARED_FIELD_SIZE == len(SDC.REAL_ARMS) == 3

    def test_no_linear_residual_arm_anywhere(self):
        """⛔ The story's whole point: the field-inflating class is out. Field membership AND
        call-site scan on comment-stripped source (DSR-CONV #690: never grep a bare name)."""
        banned = {"enet_residual", "inc_head_bank"}
        assert banned.isdisjoint(SDC.all_labels())
        assert banned == set(SDC.BANNED_ARM_CLASSES)          # both exclusions are on record
        for reason in SDC.BANNED_ARM_CLASSES.values():
            assert len(reason) > 40                           # a reason, not a label
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            assert not re.search(r"arm_enet_residual\s*\(", src), path.name
            assert not re.search(r"inc_head_bank\s*\(", src), path.name
            assert not re.search(r"\bElasticNet\b", src), path.name

    def test_anchors_never_enter_the_eligible_field(self):
        eligible = SDC.eligible_labels()
        assert len(eligible) == 4                             # non-vacuity: 3 arms + 1 foil
        assert set(eligible) == set(SDC.REAL_ARMS) | set(SDC.FOILS)
        assert set(eligible).isdisjoint(SDC.ANCHORS)
        for lab in eligible:
            assert "oracle" not in lab and "matched" not in lab, lab

    def test_every_candidate_form_has_its_own_oracle_matched_pair(self):
        """NF-D16 (g‴): one ceiling PER form (candidates nest the marginal). Non-vacuous:
        every real arm's form is a key, plus the foil's own (marginal) pair."""
        assert set(SDC.ORACLE_PAIRS) == set(SDC.REAL_ARMS) | {"marginal"}
        flat = [lab for pair in SDC.ORACLE_PAIRS.values() for lab in pair]
        assert len(flat) == 8 and len(set(flat)) == 8
        assert set(flat) <= set(SDC.ANCHORS)

    def test_matched_controls_are_same_sample_as_the_crossfit_peek(self):
        """NF1.7 (b): the matched-n control must fit on about the rows the K-fold cross-fit
        oracle FITS ON — (K−1)/K of the block — not the whole block (the smoke amendment)."""
        n_train, n_test = 5000, 900
        train = pd.DataFrame({"gw": np.arange(n_train), "x": 0.0})
        test = pd.DataFrame({"gw": np.arange(n_test) + n_train, "x": 0.0})
        w = SDC.matched_window(train, test)
        assert len(w) == round(n_test * (EM.CROSSFIT_K - 1) / EM.CROSSFIT_K)
        assert w["gw"].min() == n_train - len(w)                    # the most RECENT slice
        src = _stripped_source(_MODULE)
        for fn in ("matched_knn", "matched_hurdle", "matched_negbin"):
            body = src.split(f"def {fn}(", 1)[1].split("\ndef ", 1)[0]
            assert "matched_window(train, test)" in body, fn
            assert "matched_n_train(" not in body, fn

    def test_fresh_registration_fresh_seed(self):
        assert SDC._SEED != SD._SEED                          # a fresh field re-seeds
        assert SDC.STORY == "NF-W6b-C"

    def test_shared_machinery_is_imported_not_retyped(self):
        """The two carried arms ARE the W6b pinned code paths, by identity — the MH2.1
        serve-what-was-validated rule applied to a form."""
        assert SDC.arm_lgbm_hurdle_tail is SD.arm_lgbm_hurdle_tail
        assert SDC.arm_knn_quantile is SD.arm_knn_quantile
        assert SDC.mixture_quantiles199 is SD.mixture_quantiles199
        assert SDC.score_bank is EM.score_bank
        assert SDC.EVAL_LEVELS is MC.EVAL_LEVELS and len(SDC.EVAL_LEVELS) == 199
        assert (SDC.PBO_MAX, SDC.DSR_MIN, SDC.FDR_Q) == (SD.PBO_MAX, SD.DSR_MIN, SD.FDR_Q)

    def test_tie_eps_sits_between_float_noise_and_the_real_effect(self):
        assert 1e-6 < SDC.TIE_EPS_CRPS < 0.0194 / 10          # W6b's real effect on this cell

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        assert _PREREG.exists(), "the narrative pre-registration must be committed before the run"
        text = _PREREG.read_text()
        for token in ("FRESH REGISTRATION", "crps_q199", "deploy-held", "MH2.2",
                      "declared_field_size", "field_remedy_admissible", "count_negbin",
                      "tie", "one-sided", "CONSTRAINT_REFUSED", "Runtime gate",
                      "WITHHELD_NULL_CELLS", "linear-residual", "20260816"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_no_mae_anywhere(self):
        """NF-D11/D14: MAE inverts at the conditional median on an 86%-zero target. AST scan."""
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
            assert not hits, f"MAE computation surface in {path.name}: {hits}"

    def test_classify_null_is_wired_with_declared_field_size(self):
        """The INVERSE of the W6b guard: MH2.7 landed, so THIS story invokes
        `cv_power.classify_null` — and must pass `declared_field_size` at the call site
        (call-site regex on comment-stripped source, DSR-CONV #690)."""
        src = _stripped_source(_MODULE)
        call = re.search(r"cv_power\.classify_null\(.*?\)\n", src, re.S)
        assert call, "classify_null is not invoked — the story requires it (MH2.7)"
        assert "declared_field_size=DECLARED_FIELD_SIZE" in call.group(0)
        assert "degenerates_excluded_from_v=True" in call.group(0)

    def test_coverage_is_never_a_target(self):
        src = _stripped_source(_MODULE)
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", src)
        for m in re.finditer(r"def (arm_\w+|fit_\w+)\(.*?(?=\ndef |\Z)", src, re.S):
            assert "COVERAGE_FLOOR" not in m.group(0), (
                f"{m.group(1)} references the coverage floor — a floor must never be fit toward")

    def test_deploy_held_no_serving_or_cloud_writes(self):
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            for token in ("boto3", "put_object", "upload_file", "write_serving_store",
                          "sub_model_registry"):
                assert token not in src, f"deploy-held violation: `{token}` in {path.name}"

    def test_the_runner_pins_the_fold_bank_set_and_the_eligible_deflation(self):
        src = _stripped_source(_RUNNER)
        assert "set(banks) == set(SDC.all_labels())" in src
        assert "NF18.deflate(crps[eligible], subset=eligible)" in src
        assert "eligible = SDC.eligible_labels()" in src
        assert "for arm in SDC.REAL_ARMS:" in src            # the DSR trial field = real arms


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The serving pin — a SHIP here does NOT join NF-W6c's dispatch
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestServingStaysPinnedOut:
    def test_rb_rushing_tds_is_withheld_from_serving(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            stat_distribution_serving as SRV,
        )
        assert SDC.CELL in SRV.WITHHELD_NULL_CELLS
        assert SDC.CELL not in SRV.SERVED_CELLS
        # and the module SAYS so — moving the pin is a future wiring story's change, not ours
        assert "WITHHELD_NULL_CELLS" in _MODULE.read_text()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The count arm (the new discrete-count class)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestCountNegbin:
    def test_dispersion_recovers_overdispersion_and_poisson_floors(self):
        """Two-sided instrument check: NB2 data must fit α well off the floor; Poisson data
        must floor (the declared nested collapse, visible in the recorded α)."""
        from scipy.stats import nbinom, poisson
        rng = np.random.default_rng(20260816)
        n, mu, alpha = 3000, 1.5, 1.0
        pos = np.array(["RB"] * n)
        r = 1.0 / alpha
        y_nb = nbinom.rvs(r, r / (r + mu), size=n, random_state=rng)
        fit_nb = SDC.fit_nb2_dispersion_by_pos(np.full(n, mu), y_nb.astype(float), pos)
        assert fit_nb["RB"] > 0.3, fit_nb                     # well off the floor
        y_po = poisson.rvs(mu, size=n, random_state=rng)
        fit_po = SDC.fit_nb2_dispersion_by_pos(np.full(n, mu), y_po.astype(float), pos)
        assert fit_po["RB"] < 0.05, fit_po                    # collapses toward Poisson

    def test_thin_pooled_sample_refuses(self):
        with pytest.raises(ValueError, match="refusing"):
            SDC.fit_nb2_dispersion_by_pos(np.full(10, 0.5), np.zeros(10), np.array(["RB"] * 10))

    def test_non_integer_labels_refuse(self):
        with pytest.raises(ValueError, match="integer"):
            SDC.fit_nb2_dispersion_by_pos(np.full(100, 0.5), np.full(100, 0.4),
                                          np.array(["RB"] * 100))

    def test_bank_is_monotone_and_prices_the_atom(self):
        mu = np.array([0.1, 0.5, 2.0])
        bank = SDC.nb2_bank199(mu, {p: 0.5 for p in SDC.POSITIONS},
                               np.array(["RB", "RB", "RB"]))
        assert bank.shape == (3, 199)
        assert (np.diff(bank, axis=1) >= 0).all()
        # μ=0.1: P(0) ≈ 0.91 ⇒ the leading ~90% of grid levels sit at 0 (the atom expressed)
        assert (bank[0] == 0.0).mean() > 0.8
        assert bank[2].max() >= 4.0                           # a real right tail at μ=2

    def test_red_proof_thin_refusal_wrapped_raises_catches_baseexception(self):
        """NF-W6c: pytest's `Failed` derives from BaseException — a RED proof wrapping a
        `pytest.raises` clause must catch BaseException or the break sails through. Break the
        refusal guard in-process (mutation asserted to land) and prove the clause goes RED."""
        mod = _mutated(_MODULE, "if len(yv) < EM.MIN_BANK_ROWS:", "if False:",
                       "sdc_mut_thin")
        tripped = False
        try:
            with pytest.raises(ValueError, match="refusing"):
                mod.fit_nb2_dispersion_by_pos(np.full(10, 0.5), np.zeros(10),
                                              np.array(["RB"] * 10))
        except BaseException:  # noqa: BLE001 — pytest.Failed is NOT an Exception
            tripped = True
        assert tripped, "the mutated module still raised — the RED proof did not bite"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Permutation substrate (fresh seed, marginals preserved)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPermutation:
    def _frame(self):
        rng = np.random.default_rng(3)
        n = 240
        return pd.DataFrame({
            "position": rng.choice(["RB", "QB"], n),
            "gw": rng.integers(1, 5, n),
            "rushing_tds": rng.choice([0.0, 0.0, 0.0, 1.0, 2.0], n),
        })

    def test_multiset_preserved_within_pos_week_and_deterministic(self):
        df = self._frame()
        a = SDC.permute_stat_within_pos_week(df)
        b = SDC.permute_stat_within_pos_week(df)
        assert np.array_equal(a, b)                           # seeded
        keys = df["position"].astype(str) + "|" + df["gw"].astype(str)
        for k in keys.unique():
            sel = (keys == k).to_numpy()
            assert sorted(a[sel]) == sorted(df["rushing_tds"].to_numpy()[sel])

    def test_fresh_seed_differs_from_the_w6b_draw(self):
        df = self._frame()
        ours = SDC.permute_stat_within_pos_week(df, "rushing_tds")
        w6b = SD.permute_stat_within_pos_week(df, "rushing_tds")
        assert not np.array_equal(ours, w6b)                  # a fresh field re-seeds


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. Gate composition — one ISOLATING fixture per clause + RED-proof per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "mean_delta": 0.019,
        "fold_clause": {"required": 6, "attainable": True, "passes": True},
        "pbo": 0.05, "dsr": 0.99,
        "coverage": {"blocking_shortfall": False},
        "anchors": {"nihilist_loses": True, "zero_width_loses": True, "max_width_loses": True,
                    "winner_beats_permuted": True, "permuted_lift_not_significant": True,
                    "winner_own_form_oracle_beats_matched": True,
                    "winner_beats_own_form_oracle": True},
    }


#: (check name, sel mutation) — each mutation flips EXACTLY its own clause on the passing base.
_CLAUSE_BREAKS: list[tuple[str, dict]] = [
    ("beats_foil", {"beats_foil": False}),
    ("fold_consistency", {"fold_clause": {"required": 6, "attainable": True, "passes": False}}),
    ("pbo_ok", {"pbo": 0.5}),
    ("dsr_ok", {"dsr": 0.5}),
    ("coverage_floor_ok", {"coverage": {"blocking_shortfall": True}}),
    ("not_a_foil_tie", {"mean_delta": 5e-5}),
]


class TestGateComposition:
    def test_the_passing_base_ships(self):
        g = SDC.compose_gate_w6bc(_passing_sel(), fdr_pass=True)
        assert g["ship"] and all(g["checks"].values())

    @pytest.mark.parametrize("check,mut", _CLAUSE_BREAKS)
    def test_each_statistical_clause_isolates(self, check, mut):
        sel = {**_passing_sel(), **mut}
        g = SDC.compose_gate_w6bc(sel, fdr_pass=True)
        assert not g["ship"]
        failing = [k for k, v in g["checks"].items() if not v]
        assert failing == [check]                             # exactly one clause flipped

    def test_fdr_clause_isolates(self):
        g = SDC.compose_gate_w6bc(_passing_sel(), fdr_pass=False)
        assert [k for k, v in g["checks"].items() if not v] == ["fdr_ok"]

    def test_none_pbo_dsr_delta_fail_closed(self):
        for mut in ({"pbo": None}, {"dsr": None}, {"mean_delta": None}):
            g = SDC.compose_gate_w6bc({**_passing_sel(), **mut}, fdr_pass=True)
            assert not g["ship"], mut

    @pytest.mark.parametrize("anchor", ["nihilist_loses", "zero_width_loses", "max_width_loses"])
    def test_each_degenerate_flips_the_degenerates_clause(self, anchor):
        sel = _passing_sel()
        sel["anchors"][anchor] = False
        g = SDC.compose_gate_w6bc(sel, fdr_pass=True)
        assert [k for k, v in g["checks"].items() if not v] == ["degenerates_lose"]

    @pytest.mark.parametrize("anchor", ["winner_beats_permuted", "permuted_lift_not_significant"])
    def test_each_permutation_leg_flips_the_permutation_clause(self, anchor):
        sel = _passing_sel()
        sel["anchors"][anchor] = False
        g = SDC.compose_gate_w6bc(sel, fdr_pass=True)
        assert [k for k, v in g["checks"].items() if not v] == ["permutation_behaves"]

    def test_own_form_floor_flips_and_absent_reading_fails_closed(self):
        sel = _passing_sel()
        sel["anchors"]["winner_own_form_oracle_beats_matched"] = False
        g = SDC.compose_gate_w6bc(sel, fdr_pass=True)
        assert [k for k, v in g["checks"].items() if not v] == ["winner_own_form_floor"]
        sel2 = _passing_sel()
        del sel2["anchors"]["winner_own_form_oracle_beats_matched"]   # NF1.7 (a): absent ≠ pass
        assert not SDC.compose_gate_w6bc(sel2, fdr_pass=True)["ship"]

    def test_capacity_reading_is_report_only(self):
        """Beating one's OWN block peek is legitimate capacity (NF1.9 (f)) — flipping the
        report-only reading must not move the gate."""
        sel = _passing_sel()
        sel["anchors"]["winner_beats_own_form_oracle"] = False
        assert SDC.compose_gate_w6bc(sel, fdr_pass=True)["ship"]

    def test_red_proof_every_clause_is_load_bearing(self):
        """Delete each clause in-process (mutation asserted to land — E11.24 #682) and prove
        its isolating fixture now SHIPS — a clause whose deletion changes nothing observable
        is decoration (NF-D17). The loop asserts non-vacuity."""
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
            ("not_a_foil_tie",
             '"not_a_foil_tie": bool(sel["mean_delta"] is not None',
             '"not_a_foil_tie": bool(True or sel["mean_delta"] is not None',
             {"mean_delta": 5e-5}, True),
            ("winner_own_form_floor",
             '"winner_own_form_floor": bool(sel["anchors"].get(',
             '"winner_own_form_floor": bool(True or sel["anchors"].get(',
             {}, True),
        ]
        assert len(red_targets) == 8                          # non-vacuity of the loop itself
        for check, old, new, mut, fdr in red_targets:
            mod = _mutated(_MODULE, old, new, f"sdc_mut_{check}")
            sel = {**_passing_sel(), **mut}
            if check == "winner_own_form_floor":
                sel["anchors"] = dict(sel["anchors"],
                                      winner_own_form_oracle_beats_matched=False)
            g = mod.compose_gate_w6bc(sel, fdr_pass=fdr)
            assert g["ship"], f"deleting `{check}` did not flip the verdict — vacuous clause"

    def test_red_proof_anchor_clauses_are_load_bearing(self):
        targets = [
            ("degenerates_lose", '"degenerates_lose": bool(sel["anchors"]["nihilist_loses"]',
             '"degenerates_lose": bool(True or sel["anchors"]["nihilist_loses"]',
             "nihilist_loses"),
            ("permutation_behaves",
             '"permutation_behaves": bool(sel["anchors"]["winner_beats_permuted"]',
             '"permutation_behaves": bool(True or sel["anchors"]["winner_beats_permuted"]',
             "winner_beats_permuted"),
        ]
        assert len(targets) == 2                              # non-vacuity
        for check, old, new, anchor in targets:
            mod = _mutated(_MODULE, old, new, f"sdc_mut_{check}")
            sel = _passing_sel()
            sel["anchors"][anchor] = False
            assert mod.compose_gate_w6bc(sel, fdr_pass=True)["ship"], (
                f"deleting `{check}` did not flip the verdict")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Null classification — cv_power wired with declared_field_size (MH2.7)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _sel_for_classify(**over) -> dict:
    base = {**_passing_sel(),
            "binding_foil": "inc_climatology", "fold_wins": 8,
            "ci95": [0.017, 0.022], "observed_sr": 6.5, "p_one_sided": 0.0001,
            "deltas_by_fold": [0.018, 0.02, 0.019, 0.021, 0.017, 0.02, 0.019, 0.018],
            "trial_srs": [6.5, 5.0, 2.5]}
    base.update(over)
    return base


class TestNullClassification:
    def test_an_all_green_gate_classifies_none(self):
        sel = _sel_for_classify()
        checks = SDC.compose_gate_w6bc(sel, fdr_pass=True)["checks"]
        assert SDC.classify_w6bc_null(sel, checks, 8) is None

    def test_constraint_or_anchor_only_refusal_is_constraint_refused_no_trigger(self):
        """The NF-W7/NF-D18 rule: no sample-size trigger for a directional refusal — incl.
        the tie guard (a nested collapse is a TIE, and more data cannot un-nest a form)."""
        for mut in ({"coverage": {"blocking_shortfall": True}}, {"mean_delta": 5e-5}):
            sel = _sel_for_classify(**mut)
            checks = SDC.compose_gate_w6bc(sel, fdr_pass=True)["checks"]
            out = SDC.classify_w6bc_null(sel, checks, 8)
            assert out["state"] == "CONSTRAINT_REFUSED", mut
            assert out["retest_trigger"] is None

    def test_losing_on_average_is_genuine_absence_with_no_trigger(self):
        sel = _sel_for_classify(beats_foil=False, mean_delta=-0.01,
                                deltas_by_fold=[-0.01] * 8)
        checks = SDC.compose_gate_w6bc(sel, fdr_pass=True)["checks"]
        out = SDC.classify_w6bc_null(sel, checks, 8)
        assert out["state"] == "GENUINE_ABSENCE"
        assert out["retest_trigger"] is None
        assert "classify_null" in out["classifier"]

    #: deltas whose sample moments are DETERMINISTIC (two copies of 4 evenly-spaced values ⇒
    #: skew exactly 0, kurtosis exactly 1.64) so the classifier's DSR arithmetic is stable,
    #: and a trial field whose dispersion puts the arithmetic max-field at 2 < declared 3.
    _BELOW_DECLARED = dict(dsr=0.5, observed_sr=2.0, trial_srs=[2.0, -1.0, 3.0],
                           deltas_by_fold=[0.009, 0.009, 0.010, 0.010,
                                           0.011, 0.011, 0.012, 0.012])

    def test_statistical_null_reads_the_machine_flag_not_the_prose(self):
        """MH2.7 end-to-end: a statistical null whose arithmetic field sits BELOW the
        declared family must carry `field_remedy_admissible=False`, the arithmetic-only
        refusal in the trigger text, and a `stated` declared-size provenance."""
        sel = _sel_for_classify(**self._BELOW_DECLARED)
        checks = SDC.compose_gate_w6bc(sel, fdr_pass=True)["checks"]
        assert not checks["dsr_ok"] and checks["beats_foil"]
        out = SDC.classify_w6bc_null(sel, checks, 8)
        assert out["state"] in ("POWER_LIMITED", "DSR_UNREACHABLE")
        assert out["field_remedy_admissible"] is False
        assert "NOT A REMEDY" in (out["retest_trigger"] or "")
        assert out["detail"]["declared_field_size"] == 3
        assert out["detail"]["declared_field_size_source"] == "stated"
        assert out["detail"]["degenerates_excluded_from_v"] is True
        assert "dsr_ok" in out["failing_checks"]

    def test_red_proof_declared_field_size_is_load_bearing(self):
        """Delete `declared_field_size=` from the call (mutation asserted to land) and the
        same verdict must fall back to the refused/unstated provenance — proving the stated
        provenance is what earns the `stated` badge."""
        # ⚠️ the CALL-SITE form (indented + trailing comma) — the module docstring quotes the
        # same phrase, and a bare-phrase replace would land on the prose (a no-op break)
        mod = _mutated(_MODULE, "        declared_field_size=DECLARED_FIELD_SIZE,\n",
                       "        declared_field_size=None,\n", "sdc_mut_dfs")
        sel = _sel_for_classify(**self._BELOW_DECLARED)
        checks = SDC.compose_gate_w6bc(sel, fdr_pass=True)["checks"]
        out = mod.classify_w6bc_null(sel, checks, 8)
        assert out["detail"]["declared_field_size_source"] != "stated"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Single-cell FDR + report-only layers
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestSmallLayers:
    def test_fdr_single_cell_is_bh_at_m_equals_one(self):
        assert SDC.fdr_single_cell(0.05)["pass"] is True
        assert SDC.fdr_single_cell(0.10)["pass"] is True      # cutoff = q exactly
        assert SDC.fdr_single_cell(0.11)["pass"] is False
        assert SDC.fdr_single_cell(None)["pass"] is False     # unevaluable fails closed
        assert SDC.fdr_single_cell(0.05)["m"] == 1

    def test_benchmark_sr0_matches_the_dsr_instrument_shape(self):
        from betting_ml.utils import cv_power
        srs = [6.5, 5.0, 2.5]
        expect = cv_power.dsr_benchmark_sr0(3, float(np.var(srs, ddof=1)))
        assert SDC.benchmark_sr0(srs) == pytest.approx(expect, abs=1e-4)
        assert SDC.benchmark_sr0([1.0]) is None               # too thin → None, never 0

    def test_ppr_note_is_report_only_and_scales_by_six(self):
        out = SDC.ppr_points_note(0.02)
        assert out["points_units"] == pytest.approx(0.12)
        assert "REPORT-ONLY" in out["note"]
        assert SDC.ppr_points_note(None)["points_units"] is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Selection end-to-end WITHOUT fits (synthetic fold scores through the real runner layer)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _score(crps: float, cov: float = 0.95, pred_p0: float = 0.86, real_p0: float = 0.86,
           n: int = 1000) -> dict:
    return {"crps_q199": crps, "coverage_80": cov, "pred_p0": pred_p0,
            "real_p0": real_p0, "n": n}


def _fold_results(n_folds: int = 8, winner_crps: float = 0.130,
                  hurdle_crps: float = 0.134, negbin_crps: float = 0.140) -> list[dict]:
    """8 synthetic folds: `knn_quantile` beats everything, degenerates lose, each form's
    oracle beats its matched control, the permuted arm sits at the foil's level."""
    frs = []
    for i in range(n_folds):
        jit = 0.0005 * i
        scores = {
            "knn_quantile": _score(winner_crps + jit),
            "lgbm_hurdle_tail": _score(hurdle_crps + jit),
            "count_negbin": _score(negbin_crps + jit),
            "inc_climatology": _score(0.150 + jit + 0.001 * ((-1) ** i)),
            "nihilist_zero": _score(0.169),
            "zero_width": _score(0.169),
            "max_width": _score(0.230),
            "permuted_knn": _score(0.151 + jit + 0.002 * ((-1) ** i)),
            "oracle_marginal": _score(0.149), "matched_marginal": _score(0.1495),
            "oracle_knn": _score(0.125), "matched_knn": _score(0.133),
            "oracle_hurdle": _score(0.128), "matched_hurdle": _score(0.136),
            "oracle_negbin": _score(0.138), "matched_negbin": _score(0.143),
        }
        frs.append({"label": f"202{2 + i // 2}H{1 + i % 2}", "n_test": 1000,
                    "cells": {"RB|rushing_tds": {"scores": scores, "nb_note": {}}}})
    return frs


class TestSelectCellEndToEnd:
    def _select(self, **kw):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6b_c_rb_rush_tds as R,
        )
        return R.select_cell(_fold_results(**kw), 8)

    def test_selection_and_gates_on_a_clean_winner(self):
        sel = self._select()
        assert sel["winner"] == "knn_quantile"
        assert sel["binding_foil"] == "inc_climatology"
        assert sel["beats_foil"] and sel["fold_wins"] == 8
        assert sel["winner_form"] == "knn_quantile"
        assert sel["anchors"]["winner_own_form_oracle_beats_matched"] is True
        assert len(sel["trial_srs"]) == len(SDC.REAL_ARMS)
        assert sel["sr0_this_field"] is not None
        g = SDC.compose_gate_w6bc(sel, fdr_pass=True)
        assert g["ship"], g["checks"]
        layer_ok = SDC.classify_w6bc_null(sel, g["checks"], 8)
        assert layer_ok is None

    def test_per_form_pairs_are_read_per_form_not_field_wide(self):
        sel = self._select()
        pairs = sel["anchors"]["oracle_pairs"]
        assert set(pairs) == set(SDC.ORACLE_PAIRS)            # non-vacuity: all four read
        for form, read in pairs.items():
            assert read["oracle_beats_matched"] is True, form

    def test_derive_verdict_layer_composes_everything(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6b_c_rb_rush_tds as R,
        )
        out = {"n_folds": 8, "fold_results": _fold_results()}
        layer = R.derive_verdict_layer(out)
        assert layer["verdict"] == {"RB|rushing_tds": "SHIP"}
        assert layer["headline"] == "RB-RUSHTD-FRESH SHIP"
        assert layer["null_state"] is None
        assert layer["fdr"]["m"] == 1
        assert layer["ppr_note"]["points_units"] is not None

    def test_a_tie_scale_winner_cannot_ship(self):
        """A winner whose lead is inside TIE_EPS must not ship — the tie clause reads False
        and a null state is recorded (Batter-Props Ph2: a nested collapse is a TIE)."""
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w6b_c_rb_rush_tds as R,
        )
        # all three arms collapse to ~5e-5 ahead of the foil's fold mean
        frs = _fold_results(winner_crps=0.14995, hurdle_crps=0.14995, negbin_crps=0.14995)
        out = {"n_folds": 8, "fold_results": frs}
        layer = R.derive_verdict_layer(out)
        assert not layer["gate"]["ship"]
        assert layer["gate"]["checks"]["not_a_foil_tie"] is False
        assert layer["null_state"] is not None
        assert layer["verdict"]["RB|rushing_tds"] != "SHIP"
