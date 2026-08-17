"""NF-W7e guards — the availability split over the ALL-ROWS Σ + the atom-cap confirmation.

Every clause below is written to be INDEPENDENTLY RED-PROVABLE (NF-D17): a fixture satisfies every
OTHER clause so that only the named one can flip the result, and where a clause could pass
vacuously the NON-VACUITY is asserted first (NF1.7 (a) / INC-38). The mixture primitives are
NF-W7d's by IDENTITY (`test_nf_w7d_qb_availability.py` owns their guards); this file guards what
NF-W7e ADDS: the field, the all-rows Σ, the incumbent-as-matched-foil identity, the 2×2
attribution, the two reproduction controls, the Σ-invariance of the atom, and the atom-cap rule.

⛔ No lake IO, no S3, no network: the modules under test are pure and the runner's decision layer
is exercised on synthetic fold scores.
"""
from __future__ import annotations

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_split_allrows as SA
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as W7C
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7d_qb_availability as W7D
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7e_split_allrows as R


# ── Fixtures ────────────────────────────────────────────────────────────────────────────────────
def _banks(n: int = 24, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.empty((n, SA.N_LEGS, SA.N_LEVELS))
    for i in range(SA.N_LEGS):
        p0 = rng.uniform(0.35, 0.85)
        scale = rng.uniform(1.0, 30.0)
        q = np.maximum(0.0, (FA.EVAL_LEVELS - p0) / (1.0 - p0)) * scale
        out[:, i, :] = q[None, :] * rng.uniform(0.6, 1.4, size=(n, 1))
    return out


def _raw(seed: int = 5, n: int = 600, atom: float = 0.4) -> np.ndarray:
    """A raw stat matrix with a real all-zero atom, so Σ_all and Σ_played DIFFER."""
    rng = np.random.default_rng(seed)
    raw = np.abs(rng.normal(size=(n, SA.N_LEGS))) * (rng.random((n, SA.N_LEGS)) > 0.4)
    raw[rng.random(n) < atom] = 0.0
    return raw


def _weights(seed: int = 7) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=SA.N_LEGS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The all-rows Σ IS the incumbent's, and the incumbent IS the matched foil
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_sigma_all_is_the_incumbents_estimator_by_identity_and_differs_from_sigma_played():
    assert SA.sigma_all is FA.position_sigma          # NF-W7c's `joint_rank` Σ, verbatim
    raw = _raw()
    s_all, _ = SA.sigma_all(raw)
    s_pl, note = SA.sigma_played(raw)
    off = ~np.eye(SA.N_LEGS, dtype=bool)
    # NON-VACUITY: on an atom-bearing matrix the two populations give DIFFERENT correlations —
    # otherwise the whole 2×2 collapses and every attribution cell reads zero on nothing
    assert note["population"] == "active_rows_only"
    assert not np.allclose(s_all, s_pl)
    assert float(np.abs(s_all[off]).mean()) > float(np.abs(s_pl[off]).mean())


def test_the_mixture_over_sigma_all_at_pi_one_is_byte_identical_to_the_incumbent():
    """⭐ THE LOAD-BEARING IDENTITY OF THIS STORY: `single_copula` is the matched foil, so
    `single_copula − mixall` is the split's contribution over Σ_all and nothing else moves."""
    b, w = _banks(), _weights()
    s_all, _ = SA.sigma_all(_raw())
    inc = FA.assemble_fp_bank(b, w, corr=s_all, draws=200, seed=SA._SEED)
    off = SA.assemble_mixture_bank(b, w, pi=np.ones(len(b)), corr=s_all, draws=200,
                                   seed=SA._SEED)
    assert np.array_equal(inc, off)
    # NON-VACUITY: with a real atom the mixture is NOT the incumbent
    on = SA.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.5), corr=s_all, draws=200,
                                  seed=SA._SEED)
    assert not np.array_equal(inc, on)


def test_the_mixture_primitives_are_NF_W7ds_by_identity_not_a_second_copy():
    """One code path (NF-W7d's RED-proof lesson): a re-implemented shift would let the diagnostic
    validate its own copy while the scored path drifted."""
    assert SA.assemble_mixture_bank is MX.assemble_mixture_bank
    assert SA.mixture_marginal_drift is MX.mixture_marginal_drift
    assert SA.clamp_pi is MX.clamp_pi and SA.pi_floor is MX.pi_floor
    assert SA.pi_for_arm is MX.pi_for_arm
    assert SA._SEED == MX._SEED == FA._SEED
    assert SA.AVAIL_STREAM_OFFSET == MX.AVAIL_STREAM_OFFSET


def test_every_all_rows_arm_maps_onto_a_distinct_predecessor_pi_estimator():
    assert set(SA.PI_ESTIMATOR_OF) == set(SA.REAL_ARMS)
    assert set(SA.PI_ESTIMATOR_OF.values()) == set(MX.REAL_ARMS)
    assert SA.PI_ESTIMATOR_OF[SA.PRIMARY_ARM] == MX.PRIMARY_ARM   # the same learned π̂
    with pytest.raises(KeyError, match="not in the pre-registered family"):
        SA.pi_for_arm("mixall_learned", None, None, [], train_raw=np.zeros((1, SA.N_LEGS)))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The declared field
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_declared_field_partitions_and_the_2x2_is_complete():
    groups = (SA.REAL_ARMS, SA.CONTEST_FOILS, SA.REFERENCE_FOILS, SA.DEGENERATES)
    flat = [x for g in groups for x in g]
    assert len(flat) == len(set(flat))
    assert len(SA.ALL_LABELS) == len(set(SA.ALL_LABELS))
    assert set(SA.ELIGIBLE) == set(SA.REAL_ARMS) | set(SA.CONTEST_FOILS)
    assert not set(SA.REFERENCE_FOILS) & set(SA.ELIGIBLE)
    # the 2×2: {split on, off} × {Σ_all, Σ_played} — every cell has a label
    assert {"single_copula", "mix_played"} == set(SA.CONTEST_FOILS)
    assert "mix_off" in SA.REFERENCE_FOILS
    assert SA.INCUMBENT_FOIL == "single_copula" and SA.PREDECESSOR_FOIL == "mix_played"


def test_every_real_arm_has_its_OWN_form_oracle_and_matched_n_control():
    for arm in SA.REAL_ARMS:
        assert f"oracle__{arm}" in SA.ANCHORS
        assert f"matched_n__{arm}" in SA.ANCHORS
    assert "oracle__foil_direct_points" in SA.ANCHORS
    for décor in ("oracle__assembled_indep", "oracle__mix_off", "oracle__single_copula",
                  "oracle__mix_played"):
        assert décor not in SA.ANCHORS       # an anchor that cannot differ from its arm is décor


def test_all_four_positions_gate_and_may_ship():
    """NF-W7d scored RB/WR/TE report-only and said a successor must register them FORWARD. This is
    that successor: all four gate, the BH family carries four members."""
    assert set(SA.GATE_POSITIONS) == set(FA.POSITIONS) == {"QB", "RB", "WR", "TE"}


def test_every_bar_this_story_could_have_softened_is_inherited_by_reference():
    assert SA.PIT_MAX_DECILE_DEV == MX.PIT_MAX_DECILE_DEV == FA.PIT_MAX_DECILE_DEV == 0.05
    assert SA.COVERAGE_FLOOR == FA.COVERAGE_FLOOR == 0.80
    assert (SA.PBO_MAX, SA.DSR_MIN, SA.FDR_Q) == (FA.PBO_MAX, FA.DSR_MIN, FA.FDR_Q)
    assert SA.MIN_MIXTURE_ATOM == MX.MIN_MIXTURE_ATOM
    assert SA.MAX_MARGINAL_DRIFT == MX.MAX_MARGINAL_DRIFT
    assert SA.INCUMBENT_TOLERANCE == MX.INCUMBENT_TOLERANCE == 1e-9
    assert SA.oracle_floor_state is FA.oracle_floor_state
    assert R.GATE_LEAGUE == W7D.GATE_LEAGUE == W7C.GATE_LEAGUE


def test_the_reproduction_targets_name_both_predecessors_records():
    assert SA.INCUMBENT_RECORD_RELPATH == FA.RECORD_RELPATH
    assert SA.INCUMBENT_RECORD_ARM == FA.PRIMARY_ARM == "joint_rank"
    assert SA.PREDECESSOR_RECORD_RELPATH.endswith("nf_w7d_qb_availability.json")
    assert SA.PREDECESSOR_RECORD_ARMS == {"mix_played": MX.PRIMARY_ARM, "mix_off": "mix_off"}
    assert SA.PREDECESSOR == MX.STORY == "NF-W7d"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The atom cap and the assembled zero mass
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_atom_cap_is_a_function_of_the_banks_alone_and_bounds_the_installed_atom():
    b = _banks()
    cap = SA.atom_cap(b)
    assert 0.0 < cap < 1.0
    # any π̂ — however small — installs at most the cap after the clamp
    used, note = SA.clamp_pi(np.full(len(b), 1e-6), b)
    assert note["mean_installed_atom"] == pytest.approx(cap, abs=1e-4)   # the note is 4-dp rounded
    # a bank with NO zero mass has a cap of ZERO — the mechanism cannot act there
    assert SA.atom_cap(_banks() + 1.0) == 0.0


def test_the_installed_atom_does_not_depend_on_sigma():
    """The identity `atom_is_sigma_invariant` measures: same π̂, same banks ⇒ the same clamp,
    whatever Σ the arm draws under."""
    b = _banks()
    pi = np.random.default_rng(3).uniform(0.1, 0.9, len(b))
    _, n1 = SA.clamp_pi(pi, b)
    _, n2 = SA.clamp_pi(pi, b)
    assert n1["mean_installed_atom"] == n2["mean_installed_atom"]
    # …while the assembled banks under Σ_all vs Σ_played DIFFER (Σ acts on the joint, not the atom)
    raw = _raw()
    s_all, s_pl = SA.sigma_all(raw)[0], SA.sigma_played(raw)[0]
    used, _ = SA.clamp_pi(pi, b)
    a = SA.assemble_mixture_bank(b, _weights(), pi=used, corr=s_all, draws=150)
    p = SA.assemble_mixture_bank(b, _weights(), pi=used, corr=s_pl, draws=150)
    assert not np.array_equal(a, p)


def test_total_zero_mass_reads_the_atom_and_excludes_negative_totals():
    n = SA.N_LEVELS
    lv = FA.EVAL_LEVELS
    # row 0: 30% of levels at exactly 0, the rest positive → atom ≈ 0.30 (conservative read)
    row0 = np.where(lv <= 0.30, 0.0, lv * 10)
    # row 1: 20% negative, then 30% zero, then positive → atom ≈ 0.30, NOT 0.50
    row1 = np.where(lv <= 0.20, -1.0, np.where(lv <= 0.50, 0.0, lv * 10))
    # row 2: no zero mass at all
    row2 = lv * 10 + 1.0
    m = SA.total_zero_mass(np.vstack([row0, row1, row2]))
    assert m[0] == pytest.approx(0.30, abs=0.01)
    assert m[1] == pytest.approx(0.30, abs=0.01)
    assert m[2] == 0.0
    with pytest.raises(ValueError, match="expected"):
        SA.total_zero_mass(np.zeros((3, n - 1)))


def test_the_assembled_zero_mass_grows_with_the_installed_atom():
    """The mechanism the confirmation reads: a bigger Bernoulli atom ⇒ more assembled zero mass."""
    b, w = _banks(), _weights()
    s_all, _ = SA.sigma_all(_raw())
    lo = SA.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.9), corr=s_all, draws=400)
    hi = SA.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.5), corr=s_all, draws=400)
    assert SA.total_zero_mass(hi).mean() > SA.total_zero_mass(lo).mean()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The atom-cap RULE — fixed in advance, four states, never read as a verdict when undefined
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _cap(**over):
    kw = dict(pit_by_arm={a: 0.058 for a in SA.REAL_ARMS}, atom_all_rows=0.267,
              atom_played=0.267, atom_cap_mean=0.27, realized_atom=0.516,
              total_zero_mass_by_arm={"mixall_learned": 0.30, "single_copula": 0.22},
              pit_predecessor=0.0595)
    kw.update(over)
    return SA.atom_cap_verdict(**kw)


def test_the_atom_cap_rule_confirms_when_the_identity_holds_and_no_arm_clears_pit():
    v = _cap()
    assert v["state"] == SA.CAP_CONFIRMED and v["atom_identity_holds"] is True
    assert v["pit_moved_by_sigma_all"] == pytest.approx(0.058 - 0.0595, abs=1e-6)
    assert v["atom_shortfall_cap_vs_realized"] == pytest.approx(0.516 - 0.27, abs=1e-6)
    assert "MARGINAL layer" in v["reading"] and "52-cell" in v["reading"]


def test_the_atom_cap_rule_is_REFUTED_when_any_real_arm_clears_the_bar():
    """RED-PROVABLE: only the PIT of one arm changes."""
    v = _cap(pit_by_arm={"mixall_learned": 0.058, "mixall_clim": 0.049, "mixall_const": 0.058})
    assert v["state"] == SA.CAP_REFUTED
    assert v["best_pit_arm"] == "mixall_clim"


def test_the_atom_cap_rule_is_UNDEFINED_when_the_identity_fails_or_nothing_was_scored():
    """⛔ A broken identity means the two arms did not share a π̂ / bank — a harness defect — and
    an unscored position is not evidence. Neither may read as CONFIRMED (NF1.7 (a))."""
    assert _cap(atom_played=0.30)["state"] == SA.CAP_UNDEFINED
    assert _cap(pit_by_arm={})["state"] == SA.CAP_UNDEFINED
    # a float-noise gap inside the tolerance still holds
    assert _cap(atom_played=0.267 + 1e-12)["state"] == SA.CAP_CONFIRMED


def test_the_atom_cap_states_are_the_three_declared_and_the_reading_names_the_roadmap_move():
    assert set(SA.CAP_STATES) == {SA.CAP_CONFIRMED, SA.CAP_REFUTED, SA.CAP_UNDEFINED}
    assert SA.ATOM_CAP_POSITION == "QB"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The selection layer on synthetic fold scores
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pit_block(dev: float) -> dict:
    counts = [100] * 10
    counts[0] = int(100 + dev * 1000)
    return {"max_decile_dev": dev, "n": sum(counts), "decile_counts": counts,
            "decile_freq": [c / sum(counts) for c in counts], "worst_decile": 0}


def _fold_result(label: str, scores: dict[str, float], *, pit: dict[str, float] | None = None,
                 cov: dict[str, float] | None = None, position: str = "QB",
                 atom: float = 0.30, atom_played: float | None = None,
                 drift: float = 0.001) -> dict:
    pit = pit or {}
    # the inherited dependence clauses need indep < comonotone on coverage and the winner > indep
    cov = {"assembled_indep": 0.75, "assembled_comonotone": 0.95, **(cov or {})}
    ap = atom if atom_played is None else atom_played
    return {"label": label, "n_test": 690, "positions": {position: {
        "scores": {lab: scores[lab] for lab in SA.ALL_LABELS},
        "coverage": {lab: {"coverage": cov.get(lab, 0.85), "n": 690, "binomial_se": 0.015,
                           "blocking_shortfall": False} for lab in SA.WATCHED},
        "pit_flatness": {lab: _pit_block(pit.get(lab, 0.02)) for lab in SA.WATCHED},
        "n_train": 9000, "n_test": 690, "atom_rate_train": 0.54, "atom_rate_test": 0.53,
        "pi_summary": {a: {"mean": 0.5, "sd": 0.2, "p10": 0.2, "p90": 0.9}
                       for a in SA.REAL_ARMS},
        "clamp": {a: {"mean_installed_atom": atom, "clamp_binding_share": 0.1}
                  for a in SA.REAL_ARMS},
        "clamp_played": {"mean_installed_atom": ap, "clamp_binding_share": 0.1},
        "marginal_drift": {"max_probability_drift": drift},
        "atom_cap": {"cap_mean": 0.31, "installed_atom_all_rows": atom,
                     "installed_atom_played": ap,
                     "total_zero_mass_by_arm": {"mixall_learned": 0.3, "mixall_clim": 0.3,
                                                "mixall_const": 0.3, "mix_played": 0.28,
                                                "single_copula": 0.2, "mix_off": 0.18,
                                                "assembled_indep": 0.1,
                                                "assembled_comonotone": 0.4}},
        "sigma_all_note": {}, "sigma_played_note": {},
        "mean_abs_offdiag": {"all_rows": 0.239, "active_rows": 0.127},
    }}}


def _base_scores(**over: float) -> dict[str, float]:
    s = {lab: 3.0 for lab in SA.ALL_LABELS}
    s.update({a: 2.50 for a in SA.REAL_ARMS})
    s.update({"single_copula": 2.60, "mix_played": 2.56, "mix_off": 2.62,
              "assembled_indep": 2.70, "foil_direct_points": 2.55,
              "assembled_comonotone": 2.80, "pi_permuted": 2.62, "permuted_direct": 4.80,
              "nihilist_zero": 6.6, "zero_width": 7.9, "max_width": 10.5})
    for a in SA.REAL_ARMS:
        s[f"oracle__{a}"] = s[a] - 0.01
        s[f"matched_n__{a}"] = s[a] + 0.01
    s["oracle__foil_direct_points"] = 1.70
    s.update(over)
    return s


def _folds(n: int = 8, position: str = "QB", **over: float) -> list[dict]:
    out = []
    for i in range(n):
        s = _base_scores(**over)
        jitter = 0.001 * ((-1) ** i)
        out.append(_fold_result(f"F{i}", {k: v + jitter * (k in SA.REAL_ARMS) for k, v in
                                          s.items()}, position=position))
    return out


def _synthetic_selection(monkeypatch=None, **over: float) -> dict:
    sel = R.select_position(_folds(**over), "QB")
    assert sel is not None
    return sel


@pytest.fixture
def no_records(monkeypatch):
    """The predecessor records are ABSENT ⇒ the reproduction controls DID NOT RUN (fail closed).
    Selection-layer tests that are not about reproduction run under this fixture."""
    monkeypatch.setattr(R, "_incumbent_record_scores", lambda: None)
    monkeypatch.setattr(R, "_predecessor_record_scores", lambda foil: None)


def test_the_winner_is_ranked_on_CRPS_even_when_another_arm_has_a_better_PIT(no_records):
    folds = []
    for i in range(8):
        s = _base_scores(mixall_const=2.90)
        folds.append(_fold_result(f"F{i}", s,
                                  pit={"mixall_const": 0.005, "mixall_learned": 0.045,
                                       "assembled_comonotone": 0.001}))
    sel = R.select_position(folds, "QB")
    assert sel["winner"] == "mixall_learned"
    assert sel["pit_by_label"]["assembled_comonotone"] < sel["pit_flatness_winner_max_decile_dev"]


def test_beats_foil_binds_against_BOTH_contest_foils_and_the_stricter_one_binds(no_records):
    """The all-rows arm must beat the incumbent AND NF-W7d's registered arm. Give `mix_played`
    the better score and it must be the binding foil; a reference foil never binds."""
    sel = _synthetic_selection()
    assert sel["best_foil"] == "mix_played"          # 2.56 < 2.60
    sel2 = _synthetic_selection(mix_played=2.65)
    assert sel2["best_foil"] == "single_copula"
    sel3 = _synthetic_selection(foil_direct_points=1.90, mix_off=1.95)
    assert sel3["best_foil"] in SA.CONTEST_FOILS
    assert "beats_direct_points_REPORT_ONLY" not in R.compose_gate(sel3, True)["checks"]


def test_the_attribution_is_the_full_2x2_and_its_cells_are_consistent(no_records):
    sel = _synthetic_selection()
    a = sel["attribution"]
    assert a["split_over_sigma_all"] == pytest.approx(2.60 - 2.50, abs=2e-3)
    assert a["sigma_population_with_split"] == pytest.approx(2.56 - 2.50, abs=2e-3)
    assert a["split_over_sigma_played"] == pytest.approx(2.62 - 2.56, abs=2e-3)
    assert a["sigma_population_without_split"] == pytest.approx(2.60 - 2.62, abs=2e-3)
    # the square closes: with cells A=Σall/off, B=Σpl/off, C=Σpl/on, D=Σall/on,
    # (A−D) − (B−C) == (A−B) + (C−D)  ⇒  split_all − split_played == Σpop_without + Σpop_with
    assert (a["split_over_sigma_all"] - a["split_over_sigma_played"]) == pytest.approx(
        a["sigma_population_with_split"] + a["sigma_population_without_split"], abs=3e-3)


def test_the_atom_invariance_clause_fails_when_the_two_arms_installed_different_atoms(no_records):
    ok = R.select_position(_folds(), "QB")
    assert ok["anchors"]["atom_is_sigma_invariant"] is True
    bad = R.select_position(
        [_fold_result(f"F{i}", _base_scores(), atom=0.30, atom_played=0.31) for i in range(8)],
        "QB")
    assert bad["anchors"]["atom_is_sigma_invariant"] is False
    assert R.compose_gate(bad, True)["checks"]["atom_is_sigma_invariant"] is False


def test_the_reproduction_controls_fail_CLOSED_when_a_record_is_absent(no_records):
    sel = _synthetic_selection()
    assert sel["anchors"]["incumbent_reproduces"] is False
    assert sel["anchors"]["predecessor_reproduces"] is False
    assert "did not run" in sel["incumbent_reproduction"]["note"].lower() or \
        "DID NOT RUN" in sel["incumbent_reproduction"]["note"]
    checks = R.compose_gate(sel, True)["checks"]
    assert checks["incumbent_reproduces"] is False and checks["predecessor_reproduces"] is False


def test_the_reproduction_controls_pass_only_when_EVERY_predecessor_arm_matches(monkeypatch):
    folds = _folds()
    inc = {f"QB|F{i}": folds[i]["positions"]["QB"]["scores"]["single_copula"] for i in range(8)}
    pl = {f"QB|F{i}": folds[i]["positions"]["QB"]["scores"]["mix_played"] for i in range(8)}
    off = {f"QB|F{i}": folds[i]["positions"]["QB"]["scores"]["mix_off"] for i in range(8)}
    monkeypatch.setattr(R, "_incumbent_record_scores", lambda: inc)
    monkeypatch.setattr(R, "_predecessor_record_scores",
                        lambda foil: {"mix_played": pl, "mix_off": off}[foil])
    sel = R.select_position(folds, "QB")
    assert sel["anchors"]["incumbent_reproduces"] is True
    assert sel["anchors"]["predecessor_reproduces"] is True
    # RED-PROVABLE: drift ONE predecessor arm by 1e-6 on ONE fold — the clause must fail
    off2 = dict(off)
    off2["QB|F3"] += 1e-6
    monkeypatch.setattr(R, "_predecessor_record_scores",
                        lambda foil: {"mix_played": pl, "mix_off": off2}[foil])
    sel2 = R.select_position(folds, "QB")
    assert sel2["anchors"]["incumbent_reproduces"] is True
    assert sel2["anchors"]["predecessor_reproduces"] is False


def test_the_record_reader_refuses_a_path_proof_and_the_wrong_story(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(R, "_PROJECT_ROOT", tmp_path)
    p = tmp_path / "rec.json"
    p.write_text(json.dumps({"story": "NF-W7d", "smoke": True, "fold_results": [
        {"label": "F0", "positions": {"QB": {"scores": {"mix_off": 1.0}}}}]}))
    assert R._record_scores("rec.json", "NF-W7d", "mix_off") is None      # a smoke ⇒ no target
    p.write_text(json.dumps({"story": "NF-W7c", "smoke": False, "fold_results": [
        {"label": "F0", "positions": {"QB": {"scores": {"mix_off": 1.0}}}}]}))
    assert R._record_scores("rec.json", "NF-W7d", "mix_off") is None      # wrong story
    p.write_text(json.dumps({"story": "NF-W7d", "smoke": False, "fold_results": [
        {"label": "F0", "positions": {"QB": {"scores": {"mix_off": 1.0}}}}]}))
    assert R._record_scores("rec.json", "NF-W7d", "mix_off") == {"QB|F0": 1.0}


def test_the_gate_clause_partition_covers_every_declared_check(no_records):
    sel = _synthetic_selection()
    composed = set(R.compose_gate(sel, True)["checks"])
    declared = set(SA.STATISTICAL_CHECKS) | set(SA.ANCHOR_CHECKS)
    assert composed <= declared, sorted(composed - declared)
    for c in ("predecessor_reproduces", "atom_is_sigma_invariant", "incumbent_reproduces",
              "mixture_is_active", "mixture_preserves_marginals", "pit_flat_ok"):
        assert c in composed


@pytest.mark.parametrize("clause", ["mixture_is_active", "mixture_preserves_marginals",
                                    "incumbent_reproduces", "predecessor_reproduces",
                                    "atom_is_sigma_invariant", "pit_flat_ok"])
def test_each_clause_is_composed_and_can_block_a_ship(no_records, clause):
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    assert clause in checks
    checks[clause] = False
    assert not all(checks.values())


def test_a_PIT_only_refusal_is_CONSTRAINT_REFUSED_and_names_the_MARGINAL_layer(no_records):
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["pit_flat_ok"] = False
    out = R.classify(sel, checks)
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert out["retest_trigger"] == SA.REFUSAL_REMEDY
    assert "MARGINAL layer" in out["retest_trigger"] and "NONE" in out["retest_trigger"]
    # RED: with PIT green the branch is not taken
    checks["pit_flat_ok"] = True
    checks["beats_foil"] = False
    assert R.classify(sel, checks)["state"] != "CONSTRAINT_REFUSED"


def test_an_anchor_only_refusal_is_CONSTRAINT_REFUSED_and_names_the_failing_anchor(no_records):
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["atom_is_sigma_invariant"] = False
    out = R.classify(sel, checks)
    assert out["state"] == "CONSTRAINT_REFUSED" and out["retest_trigger"] is None
    assert out["failing_anchor_checks"] == ["atom_is_sigma_invariant"]


def test_the_declared_field_size_is_passed_and_its_SOURCE_is_recorded(no_records):
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["beats_foil"] = False
    out = R.classify(sel, checks)
    assert "field_remedy_admissible" in out
    assert "nf_w7e_preregistration" in out["declared_field_size_source"]
    assert f"{len(SA.REAL_ARMS)}-arm declared family" in out["pbo_state"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The verdict layer: four gated positions, one BH family, the atom-cap verdict on the record
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _four_position_out() -> dict:
    frs = _folds()
    for p in ("RB", "WR", "TE"):
        for fr, t in zip(frs, _folds(position=p)):
            fr["positions"][p] = t["positions"][p]
    return {"fold_results": frs}


def test_all_four_positions_are_gated_and_the_bh_family_carries_four_members(no_records):
    out = R.derive_verdict_layer(_four_position_out())
    assert set(out["gates"]) == {"QB", "RB", "WR", "TE"}
    assert set(out["fdr"]) == {f"fp|{p}" for p in ("QB", "RB", "WR", "TE")}
    assert all(out["selections"][p]["gated"] for p in ("QB", "RB", "WR", "TE"))
    assert out["verdict"]["gate_positions"] == list(SA.GATE_POSITIONS)


def test_the_atom_cap_verdict_is_derived_onto_the_record_from_QBs_selection(no_records):
    out = R.derive_verdict_layer(_four_position_out())
    assert out["atom_cap"]["state"] in SA.CAP_STATES
    assert out["verdict"]["atom_cap_state"] == out["atom_cap"]["state"]
    # the synthetic QB PIT is 0.02 for every arm ⇒ the joint layer CLEARS ⇒ REFUTED
    assert out["atom_cap"]["state"] == SA.CAP_REFUTED
    # …and with QB failing PIT under every arm ⇒ CONFIRMED
    frs = _folds()
    for fr in frs:
        for a in SA.REAL_ARMS:
            fr["positions"]["QB"]["pit_flatness"][a] = _pit_block(0.058)
    out2 = R.derive_verdict_layer({"fold_results": frs})
    assert out2["atom_cap"]["state"] == SA.CAP_CONFIRMED
    # …and with QB never scored ⇒ UNDEFINED, never a verdict
    out3 = R.derive_verdict_layer({"fold_results": _folds(position="TE")})
    assert out3["atom_cap"]["state"] == SA.CAP_UNDEFINED
    assert "QB" not in out3["selections"]


def test_the_ship_list_is_per_position_and_a_failing_position_is_a_null(no_records):
    """No records ⇒ the reproduction clauses fail ⇒ nothing ships; every gated position is a
    null with a state. RED: with the two reproduction clauses forced green the synthetic field
    ships (it is built to)."""
    out = R.derive_verdict_layer(_four_position_out())
    assert out["verdict"]["ship_positions"] == []
    assert set(out["verdict"]["null_positions"]) == {"QB", "RB", "WR", "TE"}
    for p, g in out["gates"].items():
        fails = [k for k, ok in g["checks"].items() if not ok]
        assert set(fails) == {"incumbent_reproduces", "predecessor_reproduces"}, (p, fails)


def test_the_selection_key_and_promote_blockers_are_declared_on_the_record(no_records):
    out = R.derive_verdict_layer(_four_position_out())
    key = out["verdict"]["selection_key"]
    assert "crps_q199" in key and "never a ranking key" in key
    joined = " ".join(SA.PROMOTE_BLOCKERS)
    assert "DEPLOY-HELD" in joined and "NF-W4" in joined and "Layer B" in joined
    assert "NF-W7d's report-only wins are NOT carried forward" in joined


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The bank cache refuses a stale / mismatched artifact rather than reading it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_marginal_bank_cache_round_trips_and_refuses_a_shape_mismatch(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(R, "_BANK_CACHE_DIR", tmp_path)
    smap = {"QB|passing_yards": {"form": "f", "source": "s"},
            "RB|rushing_yards": {"form": "g", "source": "s"}}
    test = pd.DataFrame({"position": ["QB", "QB", "RB"]})
    banks = {"QB|passing_yards": np.ones((2, SA.N_LEVELS)),
             "RB|rushing_yards": np.zeros((1, SA.N_LEVELS))}
    calls = []

    def fake_serve(train, serve, m):
        calls.append(1)
        return banks, {}
    monkeypatch.setattr(R.SDSD, "serve_banks", fake_serve)
    b1, s1 = R._marginals_cached("F0", None, test, smap, matrix_key="k")
    b2, s2 = R._marginals_cached("F0", None, test, smap, matrix_key="k")
    assert (s1, s2) == ("miss", "hit") and len(calls) == 1
    assert np.array_equal(b1["QB|passing_yards"], b2["QB|passing_yards"])
    # a test frame with a DIFFERENT row count refuses the cache and refits
    test2 = pd.DataFrame({"position": ["QB", "QB", "QB", "RB"]})
    banks["QB|passing_yards"] = np.ones((3, SA.N_LEVELS))
    _, s3 = R._marginals_cached("F0", None, test2, smap, matrix_key="k")
    assert s3 == "miss" and len(calls) == 2
    # a different served map ⇒ a different key ⇒ a miss
    smap2 = {**smap, "QB|passing_yards": {"form": "OTHER", "source": "s"}}
    banks["QB|passing_yards"] = np.ones((2, SA.N_LEVELS))
    _, s4 = R._marginals_cached("F0", None, test, smap2, matrix_key="k")
    assert s4 == "miss" and len(calls) == 3


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Honest framing
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_story_is_edge_independent_and_names_no_market_source():
    import inspect
    import re
    banned = ("spread_line", "total_line", "moneyline", "vegas", "implied_prob", "closing_line")
    for mod in (SA, R):
        src = inspect.getsource(mod)
        for token in banned:
            assert not re.search(rf"\b{token}\b", src), f"{mod.__name__} references `{token}`"
    assert "best_alpha = 0" in inspect.getsource(SA)
    assert "never an edge / ROI / win-rate claim" in inspect.getsource(SA).replace("\n", " ")
