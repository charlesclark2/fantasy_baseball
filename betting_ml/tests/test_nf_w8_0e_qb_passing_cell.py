"""NF-W8-0e guards — the QB | `passing_yards` cell, zero-mass × conditional-level (the 2×2).

⭐ EVERY clause here is RED-PROVEN against deliberately broken source by
`quant_sports_intel_models/football/nfl/fantasy/red_proof_nf_w8_0e.py`. A guard that cannot fail is
worse than none (NF1.7 (a) / INC-38 / NF-D17), and a guard on an `and`-composed rule is vacuous
unless its fixture satisfies every OTHER clause (NF-D17) — so each clause below drives an ISOLATING
fixture rather than one fixture that trips several at once.

Fast-gate safe: imports only `betting_ml` + the pure fantasy modules; ⛔ never `pipeline`
(E11.23), no lake IO, no S3.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import efficiency_marginals as EM
from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_body as QB
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_passing_cell as PC
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_FANTASY = Path(PC.__file__).resolve().parent
_MODULE_SRC = Path(PC.__file__).read_text()
_RUNNER = _FANTASY / "run_nf_w8_0e_qb_passing_cell.py"
_RUNNER_SRC = _RUNNER.read_text()
_PREREG = _FANTASY / "ablation_results" / "nf_w8_0e_preregistration.md"

_LEVELS = FA.EVAL_LEVELS
_N = FA.N_LEVELS


def _strip_comments(src: str) -> str:
    """⛔ Comments and docstrings must never satisfy a source-inspection guard (INC-38): a comment
    naming a rule is not the rule, and a docstring naming a call is not the call.

    ⚠️ Docstrings are blanked by their AST **line span**, never by replacing `ast.get_docstring`'s
    value: that returns the PARSED string, so a docstring containing a backslash line-continuation
    (every `RUN (OPERATOR …)` block here) never matches the raw source and the strip silently
    no-ops — which is a guard that cannot fail, in the guard written to prevent exactly that."""
    tree = ast.parse(src)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        # ⚠️ only the four node types whose `.body` is a STATEMENT LIST — an `IfExp`'s `.body` is
        # an expression and a bare `getattr(node, "body")` sweep raises on it
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in node.body:
            if (isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)):
                doc_lines.update(range(child.lineno, (child.end_lineno or child.lineno) + 1))
    kept = [("" if i + 1 in doc_lines else ln)
            for i, ln in enumerate(src.splitlines())]
    out = "\n".join(kept)
    out = re.sub(r"(?m)^\s*#.*$", "", out)
    return re.sub(r"(?m)#(?![^\n]*[\"']).*$", "", out)


def _bank(n: int, atom: float, scale: float = 60.0, seed: int = 11, *,
          negative_floor: float = 0.0) -> np.ndarray:
    """One leg's (n, 199) bank with a known atom and a positive gamma body.

    ⭐ `negative_floor < 0` makes the SUB-THRESHOLD knots genuinely NEGATIVE rather than exactly
    0.0 — which a real `lgbm_quantile_tail` bank routinely produces, and without which a break that
    OVERWRITES those knots with 0.0 changes nothing and the guard on them is VACUOUS (found by this
    story's own RED proof)."""
    rng = np.random.default_rng(seed)
    below = float(negative_floor) * rng.random((n, 20000))
    draws = np.where(rng.random((n, 20000)) < atom, below, rng.gamma(3.0, scale, (n, 20000)))
    return np.sort(np.quantile(draws, _LEVELS, axis=1).T, axis=1)


def _tensor(n: int, *, atom: float = 0.30, seed: int = 11, other_atom: float = 0.20,
            negative_floor: float = -4.0) -> np.ndarray:
    """A full (n, 13, 199) tensor: the target leg at `atom`, every other leg at `other_atom`.

    ⚠️ `other_atom` is deliberately BELOW the zero-mass targets these tests install (0.55): with the
    other legs already ABOVE the target, a break that stops scoping Z would be a no-op on them and
    the scoping guard would pass on nothing (found by this story's own RED proof)."""
    t = np.empty((n, FA.N_LEGS, _N), dtype=float)
    for j, leg in enumerate(FA.LEGS):
        t[:, j, :] = (_bank(n, atom, 60.0, seed, negative_floor=negative_floor)
                      if j == PC.LEG_INDEX else _bank(n, other_atom, 1.4, seed + j))
    return t


def _targets(tensor: np.ndarray, q: float) -> np.ndarray:
    """The leg-scoped `zm_floor`-shaped target at inactivity probability `q`."""
    full = np.maximum(PC.leg_zero_mass(tensor), q)
    return PC.leg_scoped_targets(tensor, full)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2/§3 — the story is what it says it is
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_declared_field_is_the_two_by_three_grid_and_its_size_is_stated():
    """MH2.7: `declared_field_size` must be a fact about the registration, not a discovered one."""
    assert PC.DECLARED_FIELD_SIZE == len(PC.REAL_ARMS) == 5
    assert set(PC.ARM_GRID) == set(PC.REAL_ARMS)
    # every (Z, C) combination except the incumbent cell, exactly once
    assert set(PC.ARM_GRID.values()) == {
        (True, None), (False, "shift"), (True, "shift"), (False, "scale"), (True, "scale")}
    assert len(PC.ARM_GRID) == 5, "a duplicated grid cell would silently shrink the field"
    # the primary square is the (Z, shift) sub-square of that grid
    assert PC.PRIMARY_SQUARE == {"z": "zm_only", "c": "cond_shift", "joint": "joint_shift"}
    assert PC.ALT_SQUARE == {"z": "zm_only", "c": "cond_scale", "joint": "joint_scale"}
    assert "5" in _PREREG.read_text() and "declared_field_size" in _PREREG.read_text()


def test_no_anchor_or_degenerate_is_ever_a_trial():
    """MH2.1 (a): a diagnostic anchor that leaks into the TRIAL field sets the gate's own bar."""
    assert set(PC.ELIGIBLE) == {PC.INCUMBENT, *PC.REAL_ARMS}
    for label in (*PC.ANCHOR_ARMS, PC.PERMUTED_ANCHOR, *PC.DEGENERATE_ARMS):
        assert label not in PC.ELIGIBLE
        assert label not in PC.REAL_ARMS


def test_the_certified_transform_is_a_pointer_not_a_copy():
    """NF-C0e: a second implementation of a certified transform is the wrong-key class. The
    re-splice, the target rule, the conditional reader and the atom reader must be the SAME
    objects NF-W7f certified — asserted by IDENTITY, and the source must not redefine them."""
    assert PC.resplice_zero_mass is QM.resplice_zero_mass
    assert PC.zero_targets is QM.zero_targets
    assert PC.conditional_quantiles is QM.conditional_quantiles
    assert PC.leg_zero_mass is QM.leg_zero_mass
    assert PC.score_bank is EM.score_bank
    assert PC.pairwise_gap_tests is XP.pairwise_gap_tests
    assert PC.POINT_READER is TP.tail_completed_point
    body = _strip_comments(_MODULE_SRC)
    for banned in ("def resplice_zero_mass", "def zero_targets", "def conditional_quantiles",
                   "def leg_zero_mass", "def score_bank", "def pairwise_gap_tests"):
        assert banned not in body, f"{banned} is REDEFINED in fp_qb_passing_cell — must be a pointer"


def test_every_gate_constant_is_inherited_by_reference_and_un_relaxed():
    """E2.1-r: a bar re-typed here could drift below the one the lineage was held to."""
    assert PC.ASSEMBLED_PIT_MAX_DECILE_DEV == FA.PIT_MAX_DECILE_DEV == 0.05
    assert (PC.PBO_MAX, PC.DSR_MIN, PC.FDR_Q) == (WP.PBO_MAX, WP.DSR_MIN, WP.FDR_Q)
    assert (PC.COVERAGE_FLOOR, PC.COVERAGE_BLOCK_SE) == (WP.COVERAGE_FLOOR, WP.COVERAGE_BLOCK_SE)
    assert (PC.BH_Q, PC.ALPHA, PC.MIN_PRIOR_ROWS) == (XP.BH_Q, XP.ALPHA, XP.MIN_PRIOR_ROWS)
    assert (PC.MIN_SCALE, PC.MAX_SCALE, PC.OVER_SCALE) == (QB.MIN_SCALE, QB.MAX_SCALE,
                                                           QB.OVER_SCALE)
    assert PC.REPRODUCTION_TOLERANCE == XP.REPRODUCTION_TOLERANCE == 1e-9


def test_the_w6d_default_pit_bar_is_disclosure_and_never_a_gate():
    """E2.1-r: NF-W6d's 0.03 was registered for Phase-C DEFAULTS. Importing it as a bar this
    certified W6b cell was never held to would be inventing a threshold after the fact."""
    assert PC.W6D_DEFAULT_PIT_BAR == 0.03
    body = _strip_comments(_MODULE_SRC)
    # the constant must not appear in any comparison inside the gate composition
    gate = body[body.index("def compose_gate("):body.index("def lockstep_reading(")]
    assert "W6D_DEFAULT_PIT_BAR" not in gate
    assert "cell_pit_not_degraded" in gate


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the two mechanisms
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_z_is_leg_scoped_and_the_other_twelve_legs_are_byte_identical():
    """The scoped target must reproduce the full target on ONE leg and be a byte-exact no-op on the
    other twelve — the property the whole story rests on, MEASURED not assumed."""
    t = _tensor(24)
    scoped = _targets(t, 0.55)
    # ⭐ NON-VACUITY: the UN-scoped target must actually move the other twelve legs, or "scoped"
    # and "not scoped" are the same transform here and the guard passes on nothing
    unscoped = np.maximum(PC.leg_zero_mass(t), 0.55)
    assert not PC.other_legs_untouched(t, PC.resplice_zero_mass(t, unscoped))["holds"]
    recal = PC.resplice_zero_mass(t, scoped)
    other = PC.other_legs_untouched(t, recal)
    assert other["holds"] and other["max_abs_gap"] == 0.0 and other["n_other_legs"] == 12
    moved = float(np.max(np.abs(recal[:, PC.LEG_INDEX, :] - t[:, PC.LEG_INDEX, :])))
    assert moved > 0.0, "Z did not act on its own leg — an inactive mechanism proves nothing"
    hits = PC.zero_mass_hits_target(t, scoped, recal)
    assert hits["holds"]


def test_z_raises_the_atom_to_the_target_on_the_scoped_leg():
    t = _tensor(24, atom=0.30)
    before = float(PC.leg_zero_mass(t)[:, PC.LEG_INDEX].mean())
    recal = PC.resplice_zero_mass(t, _targets(t, 0.55))
    after = float(PC.leg_zero_mass(recal)[:, PC.LEG_INDEX].mean())
    assert before == pytest.approx(0.30, abs=0.03)
    assert after == pytest.approx(0.55, abs=0.006)      # snapped DOWN onto the 199-level grid
    assert after > before


def test_c_moves_the_conditional_level_and_cannot_move_the_atom():
    """A continuous leg's atom must survive C exactly — the property that makes Z and C commute
    and the one a wrong implementation would break silently."""
    t = _tensor(24)
    for form, value in (("shift", 25.0), ("scale", 1.3)):
        out = PC.apply_conditional_correction(t, form, value)
        assert PC.atom_unmoved(t, out)["holds"], form
        assert PC.other_legs_untouched(t, out)["holds"], form
        before = float(PC.conditional_point_mean(t).mean())
        after = float(PC.conditional_point_mean(out).mean())
        assert after > before, form
        assert np.all(np.diff(out[:, PC.LEG_INDEX, :], axis=1) >= -1e-9), f"{form} broke monotonicity"


def test_c_leaves_the_sub_threshold_knots_untouched():
    """The identical rule `resplice_zero_mass` documents: `sample_from_bank` INTERPOLATES, so
    overwriting the last sub-threshold knot changes the ramp into the first positive knot and flips
    a draw just above the atom from 1 to 0."""
    t = _tensor(24)
    leg = t[:, PC.LEG_INDEX, :]
    p_hat = PC.leg_zero_mass(t)[:, PC.LEG_INDEX]
    at_or_below = _LEVELS[None, :] <= p_hat[:, None]
    # ⭐ NON-VACUITY: the knots being preserved must be genuinely NON-ZERO, or "preserved" and
    # "blanked to 0.0" are the same bytes and this assertion tests nothing
    assert float(np.min(leg[at_or_below])) < -1e-6
    out = PC.apply_conditional_correction(t, "shift", 25.0)[:, PC.LEG_INDEX, :]
    assert np.max(np.abs(out[at_or_below] - leg[at_or_below])) == 0.0


def test_a_negative_shift_is_clipped_at_zero_and_the_clip_share_is_reported():
    """The `reverse_joint_shift` anchor needs a NEGATIVE shift to be admissible; the `max(·, 0)`
    floor is what makes it so, and its cost is REPORTED, never absorbed."""
    t = _tensor(24)
    out = PC.apply_conditional_correction(t, "shift", -40.0)
    p_hat = PC.leg_zero_mass(t)[:, PC.LEG_INDEX]
    above = _LEVELS[None, :] > p_hat[:, None]
    # the CORRECTED (above-atom) region is floored at 0; the preserved sub-threshold knots keep
    # their original (here negative) values by design — see the sub-threshold guard
    assert float(out[:, PC.LEG_INDEX, :][above].min()) >= 0.0
    edges = PC.correction_edges(t, "shift", -40.0)
    assert edges["share_clipped_at_zero"] > 0.0
    assert edges["n_positive_cells"] > 0


def test_a_non_positive_kappa_is_refused_outright():
    """NF-D16: a negative scale INVERTS the leg — INELIGIBLE outright, never applied."""
    t = _tensor(8)
    for bad in (0.0, -1.0):
        with pytest.raises(ValueError, match="inverts the leg"):
            PC.apply_conditional_correction(t, "scale", bad)
    with pytest.raises(KeyError, match="unknown conditional-correction form"):
        PC.apply_conditional_correction(t, "affine", 1.0)


def test_z_and_c_commute_on_the_bank_within_the_registered_tolerance():
    """prereg §4 — registered FORWARD as an EXPECTED TIE and PROVEN, so the ordering choice is a
    recorded fact rather than an assumption (NF-D16 sibling (1))."""
    t = _tensor(24)
    scoped = _targets(t, 0.55)
    r = PC.commutation_gap(t, scoped, "shift", 25.0)
    assert r["commutes"] and r["max_abs_gap"] <= PC.COMMUTATION_TOLERANCE
    assert PC.commutation_gap(t, scoped, "scale", 1.25)["commutes"]


def test_build_arm_refuses_a_named_form_with_no_fitted_value():
    """NF1.7 (a): an arm built on a missing parameter is not the declared arm."""
    t = _tensor(8)
    with pytest.raises(ValueError, match="no fitted value"):
        PC.build_arm(t, _targets(t, 0.55), z_on=True, form="shift", value=None)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4.1 — the OOF fits
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _ledger(n: int = 400, atom: float = 0.30, q: float = 0.55, seed: int = 3) -> dict:
    rng = np.random.default_rng(seed)
    t = _tensor(n, atom=atom, seed=seed)
    zon = PC.resplice_zero_mass(t, _targets(t, q))
    y = np.where(rng.random(n) < 0.556, 0.0, rng.gamma(3.0, 90.0, n))
    return PC.cell_ledger(banks_by_column={"z_off": t, "z_on": zon}, realized_leg=y)


def test_the_estimator_is_the_tail_completed_conditional_mean_not_the_grid_mean():
    """prereg §12A A4: NF-W8-0b decided a grid mean is not `E[Y]`; the −0.3878 PPR channel this
    story corrects is stated on the TAIL-COMPLETED point, so the model side must be read the same
    way. BOTH readings are carried so the choice is auditable."""
    t = _tensor(64)
    grid = PC.conditional_grid_mean(t)
    point = PC.conditional_point_mean(t)
    assert point.shape == grid.shape == (64,)
    assert float(point.mean()) > float(grid.mean()), \
        "the tail-completed read must exceed the truncated grid mean on a right-skewed law"
    led = _ledger()
    for col in ("z_off", "z_on"):
        assert "sum_cond_mean" in led["columns"][col]
        assert "sum_cond_gridmean" in led["columns"][col]
    p = PC.fit_cell_params("cond_shift", [led, led])
    assert p["reader"].startswith("fp_tail_point.tail_completed_point")
    assert p["mean_cond_model_prior"] != p["mean_cond_model_prior_gridmean"]


def test_delta_is_fitted_per_z_column():
    """prereg §4.1: δ and κ are refitted separately in the Z-on and Z-off columns, each against the
    bank that column actually produces — a single δ carried across the columns would measure the
    ORDERING, not the mechanisms."""
    led = _ledger()
    assert PC.fit_cell_params("cond_shift", [led, led])["column"] == "z_off"
    assert PC.fit_cell_params("joint_shift", [led, led])["column"] == "z_on"
    assert PC.fit_cell_params("cond_scale", [led, led])["column"] == "z_off"
    assert PC.fit_cell_params("joint_scale", [led, led])["column"] == "z_on"
    body = _strip_comments(_MODULE_SRC)
    fit = body[body.index("def fit_cell_params("):body.index("def permuted_ledgers(")]
    assert '"z_on" if z_on else "z_off"' in fit


def test_a_thin_prior_is_ineligible_and_recorded_never_defaulted():
    """NF1.7 (a): an arm that could not be FORMED keeps identity and says so — never a silent 1.0."""
    p = PC.fit_cell_params("cond_shift", [])
    assert p["eligible"] is False and "prior OOF rows" in p["reason"]
    assert "value" not in p
    thin = _ledger(n=10)
    assert PC.fit_cell_params("cond_shift", [thin])["eligible"] is False


def test_kappa_outside_the_registered_band_is_ineligible():
    """The band is [0.5, 2.0], inherited from NF-W8-0c — an out-of-band κ is REFUSED, not clipped."""
    led = _ledger()
    huge = dict(led)
    huge["sum_y_positive"] = led["sum_y_positive"] * 50.0
    p = PC.fit_cell_params("cond_scale", [huge, huge])
    assert p["eligible"] is False and "outside the registered band" in p["reason"]
    assert p["kappa"] > PC.MAX_SCALE


def test_zm_only_needs_no_fitted_scalar():
    """Its target is NF-W7f's certified `zm_floor` rule, so it is eligible with no prior rows."""
    p = PC.fit_cell_params("zm_only", [])
    assert p["eligible"] is True and p["form"] is None


def test_an_unknown_arm_is_refused():
    with pytest.raises(KeyError, match="not in the declared field"):
        PC.fit_cell_params("leg_scale", [_ledger()])


def test_the_permutation_anchor_is_registered_inactive_and_gates_nothing():
    """prereg §5.2 / NF-D16 sibling (1): δ is a POOLED SCALAR, so a within-fold permutation cannot
    act. It is scored and its TIE asserted; presenting the near-tie as a passed test is the defect."""
    led = _ledger()
    rng = np.random.default_rng(0)
    same = PC.fit_cell_params("joint_shift", PC.permuted_ledgers([led, led], rng))
    real = PC.fit_cell_params("joint_shift", [led, led])
    assert same["value"] == real["value"]
    assert PC.PERMUTED_ANCHOR not in PC.ELIGIBLE
    body = _strip_comments(_MODULE_SRC)
    gate = body[body.index("def compose_gate("):body.index("def lockstep_reading(")]
    assert "permut" not in gate.lower(), \
        "the inactive permutation anchor must enter NO gate clause (NF-D20)"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 — the 2×2 read
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _square(inc, z, c, joint):
    return {PC.INCUMBENT: np.asarray(inc, float), "zm_only": np.asarray(z, float),
            "cond_shift": np.asarray(c, float), "joint_shift": np.asarray(joint, float)}


def test_the_interaction_is_delta_joint_minus_the_sum_of_the_halves():
    """The arithmetic itself, pinned — not the agreement of two readers (E9.61)."""
    inc = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    z = [9.0] * 6                     # Δ_Z = 1
    c = [8.0] * 6                     # Δ_C = 2
    joint = [7.5] * 6                 # Δ_joint = 2.5 ⇒ interaction = 2.5 − 3 = −0.5
    r = PC.interaction_read(_square(inc, z, c, joint), PC.PRIMARY_SQUARE)
    assert r["delta_z"]["mean"] == pytest.approx(1.0)
    assert r["delta_c"]["mean"] == pytest.approx(2.0)
    assert r["delta_joint"]["mean"] == pytest.approx(2.5)
    assert r["interaction"]["mean"] == pytest.approx(-0.5)
    assert r["sum_of_halves"] == pytest.approx(3.0)
    assert r["joint_over_sum_ratio"] == pytest.approx(2.5 / 3.0)


def test_the_interaction_states_are_read_off_the_ci_and_a_tie_is_additive():
    rng = np.random.default_rng(5)
    inc = np.full(8, 10.0)
    # SUB_ADDITIVE: joint delivers materially less than the halves' sum, with tight spread
    r = PC.interaction_read(_square(inc, np.full(8, 9.0), np.full(8, 8.0),
                                    np.full(8, 7.5) + rng.normal(0, 1e-3, 8)),
                            PC.PRIMARY_SQUARE)
    assert r["state"] == PC.I_SUB
    # SUPER_ADDITIVE
    r = PC.interaction_read(_square(inc, np.full(8, 9.0), np.full(8, 8.0),
                                    np.full(8, 6.5) + rng.normal(0, 1e-3, 8)),
                            PC.PRIMARY_SQUARE)
    assert r["state"] == PC.I_SUPER
    # ADDITIVE: exactly the sum, plus noise
    r = PC.interaction_read(_square(inc, np.full(8, 9.0), np.full(8, 8.0),
                                    np.full(8, 7.0) + rng.normal(0, 0.05, 8)),
                            PC.PRIMARY_SQUARE)
    assert r["state"] == PC.I_ADDITIVE


def test_an_incomplete_or_thin_square_is_undefined_never_a_clean_reading():
    """NF1.7 (a): 'they add' must never be reachable from a square that could not be measured."""
    sq = _square([10.0] * 6, [9.0] * 6, [8.0] * 6, [7.0] * 6)
    del sq["joint_shift"]
    assert PC.interaction_read(sq, PC.PRIMARY_SQUARE)["state"] == PC.I_UNDEFINED
    thin = _square([10.0], [9.0], [8.0], [7.0])
    assert PC.interaction_read(thin, PC.PRIMARY_SQUARE)["state"] == PC.I_UNDEFINED


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §7 — the clause battery, one ISOLATING fixture per clause (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_kwargs() -> dict:
    """A kwargs set on which EVERY clause passes — so flipping ONE input can only flip ITS clause."""
    return dict(
        beats_foil=True, mean_delta=0.05, fold_clause_passes=True,
        pbo=0.0, dsr=0.99, fdr_pass=True,
        coverage={"blocking_shortfall": False},
        assembled_pit={"passes": True}, assembled_crps_delta=0.01,
        cell_pit_winner=0.02, cell_pit_incumbent=0.06,
        degenerate_losses={d: True for d in PC.DEGENERATE_ARMS},
        magnitude_losses={a: True for a in PC.MAGNITUDE_ANCHORS},
        own_form_pair={"passes": True}, identities={"transform": True},
        incumbent_reproduces=True)


def test_the_passing_fixture_ships_so_every_other_clause_is_satisfied():
    """NF-D17: an isolating fixture is only isolating if every OTHER clause is already satisfied."""
    g = PC.compose_gate(**_passing_kwargs())
    assert g["ship"] and all(g["checks"].values())
    assert set(g["checks"]) == set(PC.ALL_CLAUSES)


@pytest.mark.parametrize("override,clause", [
    ({"beats_foil": False}, "beats_foil"),
    ({"mean_delta": PC.TIE_EPS_CRPS / 2.0}, "not_a_foil_tie"),
    ({"fold_clause_passes": False}, "fold_consistency"),
    ({"pbo": PC.PBO_MAX}, "pbo_ok"),
    ({"pbo": None}, "pbo_ok"),
    ({"dsr": PC.DSR_MIN - 1e-6}, "dsr_ok"),
    ({"dsr": None}, "dsr_ok"),
    ({"fdr_pass": False}, "fdr_ok"),
    ({"coverage": {"blocking_shortfall": True}}, "coverage_floor_ok"),
    ({"coverage": {}}, "coverage_floor_ok"),
    ({"assembled_pit": {"passes": False}}, "assembled_pit_preserved"),
    ({"assembled_crps_delta": -1e-9}, "assembled_crps_no_harm"),
    ({"assembled_crps_delta": None}, "assembled_crps_no_harm"),
    ({"cell_pit_winner": 0.07}, "cell_pit_not_degraded"),
    ({"cell_pit_winner": None}, "cell_pit_not_degraded"),
    ({"own_form_pair": {"passes": False}}, "winner_own_form_floor"),
    ({"identities": {"transform": False}}, "transform_identities_hold"),
    ({"identities": {}}, "transform_identities_hold"),
    ({"incumbent_reproduces": False}, "incumbent_reproduces"),
])
def test_each_clause_has_an_isolating_fixture_that_flips_only_it(override, clause):
    kw = _passing_kwargs() | override
    g = PC.compose_gate(**kw)
    failing = [c for c, ok in g["checks"].items() if not ok]
    assert failing == [clause], f"{override} flipped {failing}, expected only [{clause}]"


@pytest.mark.parametrize("anchor", PC.DEGENERATE_ARMS)
def test_every_degenerate_must_lose_on_its_own(anchor):
    kw = _passing_kwargs()
    kw["degenerate_losses"] = kw["degenerate_losses"] | {anchor: False}
    assert [c for c, ok in PC.compose_gate(**kw)["checks"].items() if not ok] == \
        ["degenerates_lose"]


@pytest.mark.parametrize("anchor", PC.MAGNITUDE_ANCHORS)
def test_the_magnitude_bracket_is_two_sided_and_each_side_binds(anchor):
    """NF1.7 (d) (3) one axis over: `over` (×2) and `reverse` (×−1) bracket the magnitude from BOTH
    sides, so the metric is shown to respond to DIRECTION and not only to size."""
    kw = _passing_kwargs()
    kw["magnitude_losses"] = kw["magnitude_losses"] | {anchor: False}
    assert [c for c, ok in PC.compose_gate(**kw)["checks"].items() if not ok] == \
        ["magnitude_anchors_lose"]


def test_an_empty_anchor_dict_fails_closed():
    """A check that did not run is not a pass (NF1.7 (a)) — an empty dict must NOT pass by `all([])`."""
    for key in ("degenerate_losses", "magnitude_losses"):
        kw = _passing_kwargs() | {key: {}}
        assert not PC.compose_gate(**kw)["ship"]


def test_the_clause_battery_cannot_silently_lose_a_registered_clause():
    src = _strip_comments(_MODULE_SRC)
    fn = src[src.index("def compose_gate("):src.index("def lockstep_reading(")]
    for clause in PC.ALL_CLAUSES:
        assert f'"{clause}"' in fn, f"{clause} is registered but not composed"
    assert "the clause battery is incomplete" in _MODULE_SRC


# ── the constraint readers ──────────────────────────────────────────────────────────────────────
def test_the_assembled_pit_bar_is_every_evaluable_fold_and_an_unreadable_fold_fails_closed():
    """The assembly is the ONLY PIT-clearing QB distribution on record — a cell fix that breaks its
    calibration is DISQUALIFIED, and an unreadable fold is never a pass (NF1.7 (a))."""
    assert PC.assembled_pit_verdict([0.02] * 8)["passes"]
    assert not PC.assembled_pit_verdict([0.02] * 7 + [0.051])["passes"]
    assert PC.assembled_pit_verdict([0.05] * 8)["passes"]            # the bar is inclusive
    v = PC.assembled_pit_verdict([0.02] * 7 + [None])
    assert not v["passes"] and v["n_unreadable"] == 1
    assert not PC.assembled_pit_verdict([])["passes"]


def test_the_coverage_floor_is_a_constraint_and_an_unevaluable_read_blocks():
    """NF1.8: a FLOOR, never a target — and a coverage read that did not happen is not a pass."""
    assert not PC.coverage_verdict(0.80, 5000)["blocking_shortfall"]
    assert not PC.coverage_verdict(0.79, 5000)["blocking_shortfall"]   # inside 3 binomial SE
    assert PC.coverage_verdict(0.60, 5000)["blocking_shortfall"]
    assert PC.coverage_verdict(None, 5000)["blocking_shortfall"]
    assert PC.coverage_verdict(0.90, 0)["blocking_shortfall"]


def test_an_oracle_pair_that_ties_is_inactive_and_does_not_refuse():
    """prereg §12A A7 / NF-W6d / NF-D20: a per-form peeking oracle that TIES its matched-n control
    had nothing to act on — UNINFORMATIVE, so it must NOT refuse (NF-W6d recorded three shippable
    arms killed by exactly that reading). It is not a clean pass either: `inactive` is flagged so
    the verdict can NAME it, and only a genuinely VIOLATED or an ABSENT read fails closed."""
    tie = PC.oracle_pair_state(2.5, 2.5 + PC.TIE_EPS_CRPS / 2.0)
    assert tie["state"] == "INACTIVE" and tie["inactive"] and tie["passes"]
    ok = PC.oracle_pair_state(2.4, 2.5)
    assert ok["state"] == "ACTIVE_AND_RESPECTED" and ok["passes"]
    bad = PC.oracle_pair_state(2.6, 2.5)
    assert bad["state"] == "ACTIVE_AND_VIOLATED" and not bad["passes"]
    absent = PC.oracle_pair_state(None, 2.5)
    assert absent["state"] == "UNDEFINED" and not absent["passes"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §7 — the null classifier and the NF-W8-0d lockstep reading
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_constraint_only_null_publishes_no_data_trigger():
    """NF-D18: a directional refusal is not rescuable by data — a fold/season trigger there is the
    actively-misleading direction."""
    from betting_ml.utils import cv_power
    checks = {c: True for c in PC.ALL_CLAUSES}
    checks["assembled_pit_preserved"] = False
    out = PC.classify_null(checks, sel={}, n_folds=8, cv_power=cv_power)
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert out["retest_trigger"] is None and out["binding_half"] == "anchor"


def test_a_statistical_null_states_the_declared_field_size():
    """MH2.7: the instrument must be told the field was DECLARED, and the machine flag read."""
    from betting_ml.utils import cv_power
    checks = {c: True for c in PC.ALL_CLAUSES}
    checks["dsr_ok"] = False
    sel = {"deltas_by_fold": [0.01, 0.02, -0.01, 0.03, 0.01, 0.0, 0.02, 0.01],
           "trial_srs": [0.4, 0.3, 0.5, -2.0, 0.2], "beats_foil": True, "observed_sr": 0.4,
           "fold_wins": 6, "p_one_sided": 0.06}
    out = PC.classify_null(checks, sel=sel, n_folds=8, cv_power=cv_power)
    assert out["detail"]["declared_field_size"] == PC.DECLARED_FIELD_SIZE
    assert "lockstep" in out


def test_a_dsr_failure_with_sr_below_sr0_withholds_the_variance_lever_trigger():
    """⭐ NF-W8-0d §1 / R2: a SHARED proportional variance lever maps `SR − SR0 ↦ (SR − SR0)/c` with
    its SIGN invariant, so when `SR ≤ SR0` a 'lower-variance design' trigger is VOID. Three
    consecutive records were sent at that wall."""
    from betting_ml.utils import cv_power
    checks = {c: True for c in PC.ALL_CLAUSES}
    checks["dsr_ok"] = False
    sel = {"deltas_by_fold": [0.001] * 8, "trial_srs": [3.0, -3.0, 2.0, -2.0, 0.1],
           "beats_foil": True, "observed_sr": 0.1, "fold_wins": 6, "p_one_sided": 0.2}
    out = PC.classify_null(checks, sel=sel, n_folds=8, cv_power=cv_power)
    assert out["lockstep"]["variance_lever_closed"] is True
    assert out["retest_trigger"] is None
    assert "VOID" in out["mechanism_reading"]


def test_the_lockstep_reading_is_sign_invariant_under_proportional_shrinkage():
    """The invariant itself, measured: scaling every trial Sharpe by 1/c scales `SR − SR0` by 1/c."""
    srs = [1.0, -2.0, 0.5, 0.2, 0.3]
    base = PC.lockstep_reading(1.0, srs)
    for c in (0.5, 0.25, 0.1):
        sharp = PC.lockstep_reading(1.0 / c, [s / c for s in srs])
        assert np.sign(sharp["sr_minus_sr0"]) == np.sign(base["sr_minus_sr0"])
        assert sharp["sr_minus_sr0"] == pytest.approx(base["sr_minus_sr0"] / c, rel=1e-9)
    assert not PC.lockstep_reading(None, srs)["evaluable"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §8 — the downstream verification and its measured structural fact
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_gap_closed_reads_both_bh_and_the_mde_and_refuses_an_unevaluable_pair():
    gt = {"pairs": {"QB|WR": {"gap": -0.05, "mde_ppr": 0.20, "bh_rejected": False},
                    "QB|TE": {"gap": 0.01, "mde_ppr": 0.19, "bh_rejected": False}},
          "gap_detected": False, "max_mde_ppr": 0.20}
    c = PC.gap_closed(gt)
    assert c["all_below_mde"] and c["none_bh_rejected"]
    gt["pairs"]["QB|WR"]["gap"] = -0.36
    gt["pairs"]["QB|WR"]["bh_rejected"] = True
    c = PC.gap_closed(gt)
    assert c["all_below_mde"] is False and c["none_bh_rejected"] is False
    c = PC.gap_closed({"pairs": {"QB|WR": {"gap": None, "mde_ppr": None}}})
    assert c["all_below_mde"] is None      # UNDEFINED, never a clean close


def test_the_assembled_z_column_activity_is_measured_never_assumed():
    """prereg §8.1 — the Z column is PREDICTED inactive at the assembled layer (the consumed
    `zm_floor` generator already re-splices all thirteen legs, idempotently). NF-D20: the
    active-fold count is reported so an inactive arm is never credited as a pass."""
    r = PC.assembly_activity([0.0] * 8)
    assert r["inactive"] and r["n_active_folds"] == 0 and r["n_folds"] == 8
    r = PC.assembly_activity([0.0, 0.0, 0.004, 0.0])
    assert not r["inactive"] and r["n_active_folds"] == 1
    # ⭐ nothing MEASURED is not 'inactive' — an empty read must not be reported as a measured
    # no-op, which is the NF-D20 direction that would credit a mechanism that never ran
    empty = PC.assembly_activity([])
    assert empty["inactive"] is False and empty["n_folds"] == 0 and empty["max_abs_gap"] is None
    none_only = PC.assembly_activity([None, None])
    assert none_only["inactive"] is False and none_only["n_folds"] == 0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §8 — the verdict rule
# ══════════════════════════════════════════════════════════════════════════════════════════════
_PASS = {c: True for c in PC.ALL_CLAUSES}
_CLOSED = {"all_below_mde": True, "none_bh_rejected": True}


def test_the_four_verdict_states_are_reachable_and_only_by_their_own_route():
    v = PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS, closure=_CLOSED)
    assert v["state"] == PC.V_CLOSED and v["cross_rankable"] is True
    v = PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS,
                        closure={"all_below_mde": False, "none_bh_rejected": False})
    assert v["state"] == PC.V_PERSISTS and v["cross_rankable"] is False
    v = PC.cell_verdict(harness_ok=True, winner="joint_shift",
                        checks=_PASS | {"dsr_ok": False}, closure=_CLOSED)
    assert v["state"] == PC.V_NOT_CORRECTED and v["failing_clauses"] == ["dsr_ok"]
    for bad in ({"harness_ok": False}, {"winner": None}, {"checks": None}):
        kw = dict(harness_ok=True, winner="joint_shift", checks=_PASS, closure=_CLOSED) | bad
        assert PC.cell_verdict(**kw)["state"] == PC.V_UNDEFINED
    assert PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS,
                           closure=None)["state"] == PC.V_UNDEFINED


def test_cross_rankable_is_only_reachable_through_the_closed_state():
    """⛔ The consumption flag must never be reachable from a persisting gap or a failed battery."""
    for closure in (None, {"all_below_mde": None}, {"all_below_mde": False,
                                                    "none_bh_rejected": True},
                    {"all_below_mde": True, "none_bh_rejected": False}):
        v = PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS, closure=closure)
        assert v["cross_rankable"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The runner's structural refusals
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_runner_refuses_to_write_any_decided_predecessor_path():
    """The NCAAF-P2.1 S1-serve lesson: a successor that writes a decided story's paths destroys its
    audit trail with no error and no test failure. Enforced at IMPORT, not by review."""
    body = _strip_comments(_RUNNER_SRC)
    assert "_DECIDED_PATHS" in body and "would write a DECIDED predecessor artifact path" in body
    for decided in ("nf_w8_0_cross_position", "nf_w8_0b_tail_point", "nf_w8_0c_qb_body",
                    "nf_w7f_qb_marginal", "nf_w6d_stat_bakeoff"):
        assert f'"{decided}"' in body, f"{decided} is not in the refusal list"
    assert "nf_w8_0e_qb_passing_cell.json" in body


def test_the_runner_publishes_nothing_and_touches_no_serving_surface():
    """⚖️ DEPLOY-HELD: local artifacts only (prereg §11)."""
    body = _strip_comments(_RUNNER_SRC) + _strip_comments(_MODULE_SRC)
    for banned in ("boto3", "--publish", "s3://", "dagster", "dbt", "put_object",
                   "SERVED_CELLS", "serve_frame", "registry"):
        assert banned not in body, f"NF-W8-0e must not reference `{banned}`"


def test_the_runner_never_rounds_a_pinned_score():
    """⛔ the NF-W8-0 smoke's catch: a `round(…, 6)` caps every 1e-9 pin at ~5e-7 and the decisive
    run returns UNDEFINED while reproducing perfectly."""
    body = _strip_comments(_RUNNER_SRC)
    for fn in ("_cell_scores", "_assembled_scores"):
        block = body[body.index(f"def {fn}("):]
        block = block[:block.index("\ndef ", 5)]
        assert "round(" not in block, f"{fn} rounds a score that a 1e-9 pin compares"


def test_the_qb_assembly_is_one_code_path_with_the_certified_generator():
    """NF-W7d: the four calls must be the QB branch of `build_position_banks`, not a second copy —
    and the runner must REFUSE (never tolerate) a re-derived incumbent that is not the certified
    generator."""
    body = _strip_comments(_RUNNER_SRC)
    fn = body[body.index("def assemble_qb_from_tensor("):body.index("def _cell_scores(")]
    for call in ('QM.zero_targets("zm_floor"', "QM.resplice_zero_mass(", "QM.clamp_pi(",
                 "QB.assemble_qb("):
        assert call in fn, f"the assembly is missing `{call}`"
    assert 'check["crps_gap"] == 0.0 and check["point_gap"] == 0.0' in body
    assert "is NOT the certified `zm_floor`" in _RUNNER_SRC


def test_the_preregistration_exists_and_declares_the_field_before_the_run():
    txt = _PREREG.read_text()
    assert "BEFORE any scoring run" in txt
    for arm in PC.REAL_ARMS:
        assert f"`{arm}`" in txt, f"{arm} is not declared in the pre-registration"
    for section in ("§5 The declared field", "§6 The 2×2 read", "§8 Family D",
                    "§12A BUILD-TIME AMENDMENTS", "§13 POST-RUN FINDINGS"):
        assert section in txt
    assert PC.PREREGISTRATION_RELPATH.endswith("nf_w8_0e_preregistration.md")


def test_assemble_qb_at_zero_shift_is_byte_identical_to_the_certified_mixture():
    """⭐ The load-bearing claim behind using `QB.assemble_qb` instead of `QM.assemble_mixture_bank`
    (which the certified `build_position_banks` calls): at `played_shift = 0` the two are the SAME
    construction — same block loop, same seeds, legs from `MX.mixture_leg_draws` — and this story
    needs the leg means + total mean that only the former returns. ⛔ MEASURED, not trusted: if the
    two ever diverge, every reproduction pin in this story is comparing the wrong object."""
    t = _tensor(48)
    from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
    pi = np.clip(np.linspace(0.15, 0.95, 48), 0.0, 1.0)
    corr = np.eye(FA.N_LEGS)
    a, _lm, _tm = QB.assemble_qb(t, np.asarray([0.0, 0.04, 4.0, -2.0, 0.0, 0.1, 6.0, 0.0, 1.0,
                                                0.1, 6.0, -2.0, 2.0]),
                                 pi=pi, corr=corr, draws=128)
    b = MX.assemble_mixture_bank(t, np.asarray([0.0, 0.04, 4.0, -2.0, 0.0, 0.1, 6.0, 0.0, 1.0,
                                                0.1, 6.0, -2.0, 2.0]),
                                 pi=pi, corr=corr, draws=128)
    assert float(np.max(np.abs(a - b))) == 0.0


def test_the_model_side_of_the_fit_is_probability_weighted():
    """prereg §12A A6 — the realized side averages over the rows that WERE positive
    (disproportionately starters); an UNWEIGHTED mean of per-row model conditional means carries
    every backup's much lower conditional law at full weight, so the two are different populations
    and δ absorbs a SELECTION effect. The model's own `E[Y | Y>0]` is `Σ P̂(Y>0)·m / Σ P̂(Y>0)`.

    The fixture makes the two estimators DISAGREE by construction: half the rows are
    starter-shaped (a small atom and a high conditional level) and half are backup-shaped."""
    hi = _tensor(60, atom=0.10, seed=21)                    # starters: mostly play, throw a lot
    lo = _tensor(60, atom=0.90, seed=22)
    lo[:, PC.LEG_INDEX, :] *= 0.25                          # backups: rarely play, throw little
    t = np.concatenate([hi, lo], axis=0)
    y = np.concatenate([np.full(60, 250.0), np.zeros(60)])  # only the starters realize positive
    led = PC.cell_ledger(banks_by_column={"z_off": t}, realized_leg=y)
    col = led["columns"]["z_off"]
    for key in ("sum_weighted_cond", "sum_positive_weight", "sum_cond_mean"):
        assert key in col
    weighted = col["sum_weighted_cond"] / col["sum_positive_weight"]
    unweighted = col["sum_cond_mean"] / led["n"]
    assert weighted > unweighted * 1.2, \
        "the fixture must make the two estimators disagree, or this guard tests nothing"
    p = PC.fit_cell_params("cond_shift", [led, led])
    # ⚠️ the REPORTED diagnostics are rounded for legibility; the applied `value` is full precision
    assert p["mean_cond_model_prior"] == pytest.approx(weighted, abs=1e-6)
    assert p["mean_cond_model_prior_unweighted"] == pytest.approx(unweighted, abs=1e-6)
    assert p["value"] == pytest.approx(p["mean_y_positive_prior"] - weighted, abs=1e-6)
    # the unweighted estimator would have produced a MATERIALLY larger δ — the path proof's defect
    assert p["value"] < (p["mean_y_positive_prior"] - unweighted)


def test_a_zero_positive_weight_is_ineligible_never_a_division_by_zero():
    """NF1.7 (a): a MODEL that is a point mass at 0 on every row carries no conditional law to
    match, so `Σ P̂(Y>0)` is 0 and the fit must be INELIGIBLE — never a division by zero.

    ⭐ The realized side deliberately HAS positive rows and the row count clears the floor, so the
    earlier `n < MIN_PRIOR_ROWS or n_positive < 1` guard cannot short-circuit this one: without
    that, the fixture never reaches the clause under test (found by this story's own RED proof)."""
    t = np.zeros((80, FA.N_LEGS, _N))
    y = np.where(np.arange(80) < 40, 250.0, 0.0)
    led = PC.cell_ledger(banks_by_column={"z_off": t}, realized_leg=y)
    assert led["n_positive"] == 40                        # the row-count guards cannot fire
    # ⚠️ `MX.leg_zero_mass` reads the atom as the LEVEL of the last sub-threshold knot, capped at
    # `EVAL_LEVELS[-1]` = 0.995, so a real bank always leaves ≥ 0.005 of positive weight per row.
    # This clause is therefore a DEFENSIVE branch against a malformed/degenerate ledger, and it is
    # pinned by constructing exactly that ledger — stated plainly rather than dressed as a
    # reachable-from-data case.
    assert led["columns"]["z_off"]["sum_positive_weight"] == pytest.approx(0.4, abs=1e-9)
    degenerate = {**led, "columns": {"z_off": {**led["columns"]["z_off"],
                                               "sum_positive_weight": 0.0}}}
    assert PC.fit_cell_params("cond_shift", [degenerate, degenerate])["eligible"] is False


def test_an_inactive_own_form_floor_is_named_in_the_verdict():
    """prereg §12A A7: an INACTIVE pair does not refuse AND does not certify — the record must say
    which happened rather than letting one `passes` stand for both."""
    v = PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS, closure=_CLOSED,
                        own_form_pair={"passes": True, "inactive": True})
    assert v["state"] == PC.V_CLOSED and v["own_form_floor_inactive"] is True
    assert "INACTIVE" in v["reason"]
    v = PC.cell_verdict(harness_ok=True, winner="joint_shift", checks=_PASS, closure=_CLOSED,
                        own_form_pair={"passes": True, "inactive": False})
    assert v["own_form_floor_inactive"] is False and "INACTIVE" not in v["reason"]


def test_the_downstream_read_is_report_only_and_never_a_second_selection():
    """prereg §12A A8: family D is computed under every real arm so a null still records the
    downstream answer — ⛔ but the verdict must read the closure of the §7 WINNER and nothing else.
    Promoting an arm that lost the registered contest because its downstream row looks better is
    the E2.1-r inversion in its most literal form."""
    body = _strip_comments(_RUNNER_SRC)
    d = body[body.index("    family_d: dict[str, dict] = {}"):body.index('out["family_d"] = family_d')]
    assert "for arm in (PC.INCUMBENT, *PC.REAL_ARMS):" in d
    # the verdict's closure comes from the winner's row, never from a scan of family_d
    v = body[body.index('closure = ('):body.index('out["cross_rankable"]')]
    assert 'family_d.get(sel["winner"]' in v
    for banned in ("min(", "max(", "sorted(", "idxmin", "argmin"):
        assert banned not in v, f"the verdict layer must not RANK family_d rows (`{banned}`)"
