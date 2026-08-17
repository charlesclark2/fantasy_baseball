"""NF-W7f guards — the QB MARGINAL-layer zero-mass recalibration.

WHAT THESE DEFEND. NF-W7e CONFIRMED that QB's PIT ceiling is set by the MARGINAL layer and named the
52-cell substrate as the only remaining route. This story takes that route, so the guards concentrate
on the three ways it could be wrong WITHOUT anything looking wrong:

  1. the TRANSFORM could reshape a marginal instead of re-weighting its atom (a refit wearing a
     recalibration's badge) — §1 of the pre-registration forbids exactly that;
  2. the MATCHED FOIL could stop being matched (if re-splicing to a bank's own atom were not a
     byte-identical no-op, `mixall_learned − zm_*` would be measuring the transform's arithmetic
     rather than the recalibration);
  3. a gate clause could be VACUOUS — the NF1.7 (a) / INC-38 / NF-D17 family this repo keeps
     re-learning. Every clause below gets an ISOLATING fixture that satisfies every OTHER clause, so
     a green result can only mean the clause under test passed (NF-D17: a fixture that trips several
     clauses of an `and`-gate proves none of them).

⭐ EVERY IDENTITY HERE WAS RED FIRST. The transform's four defects (zeroed sub-threshold knots
flipping an integer draw, an off-grid target misaligning the conditional levels, a target silently
LOWERING an atom, and a staircase inverted to measure the conditional law) were all found by these
identities failing on synthetic banks — not by inspection. The `RESHAPE`/`REFIT` cases below are the
RED proofs kept in the suite so a future edit cannot quietly re-introduce any of them.

Fast-gate safe: imports `betting_ml` / `quant_sports_intel_models` only, never `pipeline` (E11.23).
"""
from __future__ import annotations

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_split_allrows as SA
from quant_sports_intel_models.football.nfl.fantasy import fp_qb_marginal_calibration as QM


# ── Synthetic banks: the shapes the QB substrate actually serves ─────────────────────────────────
def _banks(seed: int = 7, n: int = 40) -> np.ndarray:
    """(n, 13, 199) served-shaped banks spanning the four cases that matter:
    an ATOM-FREE continuous leg at yardage scale (the NF-W6c-recorded `QB|passing_yards` defect),
    an atom-bearing count leg, a nearly-all-zero event leg, and a leg with a NEGATIVE tail."""
    rng = np.random.default_rng(seed)
    lv = QM.N_LEVELS
    b = np.empty((n, QM.N_LEGS, lv), dtype=float)
    for i in range(n):
        for j in range(QM.N_LEGS):
            if j % 4 == 0:
                q = np.sort(rng.gamma(2.0, 300.0, lv)) + 0.5            # atom-free, yardage scale
            elif j % 4 == 1:
                q = np.sort(np.concatenate([np.zeros(int(0.6 * lv)),
                                            rng.gamma(1.5, 2.0, lv - int(0.6 * lv))]))
            elif j % 4 == 2:
                q = np.sort(np.concatenate([np.zeros(lv - 4), rng.gamma(1.0, 1.0, 4)]))
            else:
                q = np.sort(np.concatenate([-rng.gamma(1.0, 3.0, 10), np.zeros(lv - 60),
                                            rng.gamma(2.0, 8.0, 50)]))
            b[i, j] = q
    return b


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The transform's three identities — each RED-proved against a deliberate defect
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("seed", [7, 11, 23, 101])
def test_resplicing_to_a_banks_own_atom_is_a_byte_identical_no_op(seed: int) -> None:
    """⭐ THE MATCHED-FOIL IDENTITY. `mixall_learned − zm_*` is only "the recalibration and nothing
    else" if a target equal to the bank's own atom changes NOTHING the draw path can see. Measured
    on the DRAW path (not the knots), because a sub-threshold knot legitimately differs while a draw
    cannot — `FA.draw_legs` already rounds and floors.

    RED HISTORY: the first cut overwrote the sub-threshold knots with 0.0, which looks harmless
    (0.41 already rounds to 0) but changes the INTERPOLATION RAMP into the first positive knot — a
    max draw gap of 1.0 on 7 of 13 legs. A second cut computed the identity level map through the
    affine formula, which drifts ~1e-13 in floats and at yardage scale survives into the draw."""
    b = _banks(seed, 30)
    got = QM.matched_foil_identity(b, draws=256, seed=seed)
    assert got["max_abs_draw_gap"] == 0.0, got
    assert got["holds"], got


@pytest.mark.parametrize("add", [0.005, 0.02, 0.10, 0.25, 0.45])
def test_the_installed_atom_is_exactly_what_the_raise_only_rule_asked_for(add: float) -> None:
    """The recalibrated bank, RE-READ through `MX.leg_zero_mass` — the very function `pi_floor` and
    the atom cap are built from — carries the requested atom. Not a restatement of the transform:
    it goes back through the public reader, so a wrong `p̂`, an off-by-one on the grid or an inverted
    direction is caught here rather than shipping a cap the mixture then silently clamps against."""
    b = _banks()
    t = np.clip(QM.leg_zero_mass(b) + add, 0.0, QM.MAX_ZERO_TARGET)
    got = QM.zero_mass_hits_target(b, t, QM.resplice_zero_mass(b, t))
    assert got["max_abs_gap"] <= QM.ZERO_MASS_TOLERANCE, got
    assert got["holds"], got


def test_the_transform_is_raise_only_so_the_cap_can_never_move_backwards() -> None:
    """⭐ NF1.7 (d) (4) — "a widen-only knob must actually BE monotone". Lowering an atom would
    require inventing positive mass the source never expressed, and because the cap is a row-wise
    MIN over legs only RAISING can lift it. A target below a leg's own atom must be a NO-OP.

    RED HISTORY: the first cut let a target lower an atom; because the transform preserves the
    source's sub-threshold knots, the re-read atom stayed at `p̂` anyway and
    `zero_mass_hits_target` went RED with a 0.43 gap — the identity catching the transform's own
    undeclared direction."""
    b = _banks()
    p = QM.leg_zero_mass(b)
    low = QM.resplice_zero_mass(b, np.clip(p - 0.20, 0.0, None))
    assert np.allclose(QM.leg_zero_mass(low), p), "a lowering target moved the atom DOWN"
    assert QM.matched_foil_identity(low)["max_abs_draw_gap"] == 0.0
    # mixed raise/lower in ONE call: the raised legs raise, the lowered legs hold
    mixed = p.copy()
    mixed[:, ::2] = np.clip(p[:, ::2] + 0.15, 0.0, QM.MAX_ZERO_TARGET)
    mixed[:, 1::2] = np.clip(p[:, 1::2] - 0.15, 0.0, None)
    out = QM.resplice_zero_mass(b, mixed)
    assert np.all(QM.leg_zero_mass(out) >= p - 1e-12)
    assert QM.zero_mass_hits_target(b, mixed, out)["holds"]


def test_a_recalibrated_bank_stays_a_monotone_quantile_bank() -> None:
    b = _banks()
    p = QM.leg_zero_mass(b)
    for t in (np.clip(p + 0.30, 0.0, QM.MAX_ZERO_TARGET), np.full(p.shape, 0.999),
              np.zeros(p.shape)):
        out = QM.resplice_zero_mass(b, t)
        assert np.all(np.diff(out, axis=2) >= -1e-9), "the recalibrated bank is not sorted"


def test_an_honest_splice_preserves_the_conditional_on_positive_law() -> None:
    b = _banks()
    t = np.clip(QM.leg_zero_mass(b) + 0.10, 0.0, QM.MAX_ZERO_TARGET)
    got = QM.positive_law_drift(b, QM.resplice_zero_mass(b, t))
    assert got["evaluated"] and got["holds"], got
    assert got["max_drift_over_bound"] <= QM.MAX_POSITIVE_LAW_DRIFT_RATIO, got


@pytest.mark.parametrize(
    "name,lo,factor,offset",
    [("upper_tail_stretch", 120, 1.6, 0.0), ("mild_tail_stretch", 150, 1.08, 0.0),
     ("shift_above_the_atom", 150, 1.0, 2.0), ("squeeze", 120, 0.9, 0.0)])
def test_a_RESHAPED_splice_is_refused_by_the_positive_law_clause(
        name: str, lo: int, factor: float, offset: float) -> None:
    """⭐ THE RED PROOF THAT KEEPS THE CLAUSE FALSIFIABLE. A splice that RESHAPES a marginal instead
    of re-weighting its atom — a refit wearing a recalibration's badge, the one thing §1 forbids —
    must be REFUSED. A clause that could not fail would be the vacuous-guard class this repo keeps
    re-learning (NF1.7 (a) / INC-38 / NF-D17).

    The mutation is asserted to LAND and to MOVE the asserted quantity before the verdict is trusted
    (#682: a RED proof whose break silently no-ops reports a FALSE "the guard is vacuous"; #815: a
    break that lands without moving the predicate is a false green)."""
    b = _banks()
    t = np.clip(QM.leg_zero_mass(b) + 0.10, 0.0, QM.MAX_ZERO_TARGET)
    honest = QM.resplice_zero_mass(b, t)
    assert QM.positive_law_drift(b, honest)["holds"], "the honest baseline must pass first"
    bad = honest.copy()
    bad[:, :, lo:] = bad[:, :, lo:] * factor + offset
    bad = np.sort(bad, axis=2)
    assert not np.allclose(bad, honest), f"{name}: the deliberate reshape did NOT land"
    got = QM.positive_law_drift(b, bad)
    assert got["evaluated"], got
    assert not got["holds"], f"{name}: a RESHAPE passed the positive-law clause — it is VACUOUS"


def test_an_all_degenerate_comparison_is_unevaluable_and_never_a_pass() -> None:
    """NF1.7 (a): a check that could not run is not a pass. A leg whose atom is ~0.995 has ONE
    positive knot, its conditional law is a point mass, and comparing it to a 199-knot law is
    meaningless — so the clause must report NOT EVALUATED rather than quietly passing on it."""
    deg = np.zeros((3, QM.N_LEGS, QM.N_LEVELS))
    deg[:, :, -1] = 5.0
    got = QM.positive_law_drift(deg, QM.resplice_zero_mass(deg, np.full(deg.shape[:2], 0.99)))
    assert got["evaluated"] is False and got["holds"] is False, got


def test_the_zero_threshold_is_not_a_second_copy_of_the_atom_rule() -> None:
    """`ZERO_THRESHOLD` is derived from `FA.INTEGER_LEGS` — the same source `MX.leg_zero_mass`
    derives its own from. A second copy of a rule is the NF-C0e wrong-key class, so the two are
    asserted to AGREE by construction rather than by reading the code: a bank whose knots sit just
    below / just above each leg's threshold must be read the same way by both."""
    lv = QM.N_LEVELS
    for eps, expect_atom in ((-1e-6, True), (+1e-6, False)):
        b = np.empty((1, QM.N_LEGS, lv))
        for j in range(QM.N_LEGS):
            thr = QM.ZERO_THRESHOLD[j]
            b[0, j] = np.concatenate([np.full(lv // 2, thr + eps),
                                      np.full(lv - lv // 2, thr + 100.0)])
        read = MX.leg_zero_mass(b)[0]
        if expect_atom:
            assert np.all(read > 0.0), "MX reads no atom where ZERO_THRESHOLD says there is one"
        else:
            assert np.all(read == 0.0), "MX reads an atom where ZERO_THRESHOLD says there is none"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The declared field, the scope, and the held-fixed joint construction
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_story_gates_QB_only_and_says_so_on_the_record() -> None:
    """⛔ The card gates QB and names an RB certificate as a SEPARATE prerequisite for NF-W8. A
    position this story does not run may not be read as evidence in either direction (NF1.7 (a))."""
    assert QM.GATE_POSITIONS == ("QB",)
    assert QM.POSITIONS == ("QB",)
    assert QM.CAP_POSITION == "QB"
    blockers = " ".join(QM.PROMOTE_BLOCKERS)
    assert "QB ONLY" in blockers
    assert "RB certificate" in blockers


def test_the_declared_family_varies_the_zero_mass_target_and_nothing_else() -> None:
    """⭐ The coherence claim, made mechanical: the joint construction is FIXED at NF-W7e's
    registered arm for every real arm, and the π̂ estimator is NF-W7d's, imported by identity. If a
    future edit gave one arm its own copula or its own availability estimator the family would stop
    being coherent and DSR would be deflating over a heterogeneous field (the MH2.5 / NF-W6b-C
    `V`-inflation mechanism)."""
    assert QM.JOINT_CONSTRUCTION == SA.PRIMARY_ARM == "mixall_learned"
    assert QM.MATCHED_FOIL == QM.JOINT_CONSTRUCTION
    assert QM.PI_ESTIMATOR is SA.PI_ESTIMATOR_OF[SA.PRIMARY_ARM]
    assert QM.PI_ESTIMATOR == "mix_learned"


def test_every_real_arm_names_a_DISTINCT_zero_mass_target() -> None:
    """A coherent family is still a family of DISTINCT arms. Two arms computing the same target
    would make the field smaller than declared — and DSR/PBO would be deflating over a field with a
    duplicate in it."""
    b = _banks()
    pi = np.full(len(b), 0.55)
    cond = np.linspace(0.05, 0.9, QM.N_LEGS)
    marg = np.linspace(0.4, 0.99, QM.N_LEGS)
    seen: dict[str, np.ndarray] = {}
    for arm in QM.REAL_ARMS:
        seen[arm] = QM.zero_targets(arm, banks=b, pi_hat=pi, cond_rate=cond, marg_rate=marg)
    names = list(seen)
    for i, a in enumerate(names):
        for bname in names[i + 1:]:
            assert not np.allclose(seen[a], seen[bname]), f"{a} and {bname} name the same target"


def test_the_magnitude_probe_is_a_REAL_arm_not_an_anchor() -> None:
    """⭐ NF-D20 / NF-W7b: an over-correction registered as an ANCHOR that then BEATS the field
    produces a null while the answer sits in an ineligible cell. `zm_over` must therefore be a real,
    shippable arm — inside `REAL_ARMS`, inside `ELIGIBLE`, and NOT among the anchors."""
    assert "zm_over" in QM.REAL_ARMS
    assert "zm_over" in QM.ELIGIBLE
    assert "zm_over" not in QM.ANCHORS
    assert "zm_over" not in QM.DEGENERATES
    assert QM.OVER_SCALE > 1.0
    # …and it must actually over-correct relative to the primary
    b = _banks()
    pi = np.full(len(b), 0.55)
    cond, marg = np.full(QM.N_LEGS, 0.2), np.full(QM.N_LEGS, 0.5)
    prim = QM.zero_targets(QM.PRIMARY_ARM, banks=b, pi_hat=pi, cond_rate=cond, marg_rate=marg)
    over = QM.zero_targets("zm_over", banks=b, pi_hat=pi, cond_rate=cond, marg_rate=marg)
    assert over.mean() > prim.mean(), "the magnitude probe does not over-correct"


def test_the_blind_arm_is_row_blind_and_registered_shippable() -> None:
    """NF-D20: a BLIND rule that wins is a finding about the signal, not an anchor to disqualify
    after the fact — so it must be registered shippable, and it must actually be blind."""
    b = _banks()
    marg = np.linspace(0.4, 0.99, QM.N_LEGS)
    t = QM.zero_targets("zm_climatology", banks=b, pi_hat=np.random.default_rng(0).random(len(b)),
                        cond_rate=np.full(QM.N_LEGS, 0.3), marg_rate=marg)
    assert np.allclose(t.std(axis=0), 0.0), "the blind arm's target varies by ROW"
    assert np.allclose(t[0], marg)
    assert "zm_climatology" in QM.REAL_ARMS


def test_the_reference_foils_do_not_bind_beats_foil_and_stay_out_of_the_trial_field() -> None:
    """MH2.1 (a): a diagnostic/reference arm that joins the PBO/DSR trial field sets the gate's own
    bar. `zm_cond_copula` completes the 2×2 and must be reported, never binding."""
    for f in QM.REFERENCE_FOILS:
        assert f not in QM.CONTEST_FOILS
        assert f not in QM.ELIGIBLE
    assert "zm_cond_copula" in QM.REFERENCE_FOILS
    assert set(QM.ELIGIBLE) == set(QM.REAL_ARMS) | set(QM.CONTEST_FOILS)


def test_every_declared_label_is_unique_and_the_watched_set_covers_the_degenerates() -> None:
    assert len(QM.ALL_LABELS) == len(set(QM.ALL_LABELS)), "a label is declared twice"
    # NF1.8: every degenerate's PIT is printed every run, which is what proves the bar was never
    # promoted into a selection criterion
    for d in QM.DEGENERATES:
        assert d in QM.WATCHED
    for a in QM.REAL_ARMS:
        assert a in QM.WATCHED
        assert f"oracle__{a}" in QM.ANCHORS and f"matched_n__{a}" in QM.ANCHORS


def test_the_zero_mass_permutation_anchor_is_declared() -> None:
    """NF-D15 (g′): without a per-row permutation a row-blind LEVEL shift is indistinguishable from a
    per-player signal."""
    assert "zm_permuted" in QM.ANCHORS
    assert "zm_permuted" in QM.WATCHED
    assert "permuted_direct" in QM.ANCHORS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. Every gate constant is INHERITED BY IDENTITY, not re-typed (E2.1-r / NF1.8 / NF-D18)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_bar_the_floor_and_the_deflation_gates_are_inherited_by_reference() -> None:
    """⛔ A story that re-types a bar can move it. Pinning by IDENTITY means a bar change upstream is
    visible here and a bar change HERE is impossible without editing the predecessor."""
    assert QM.PIT_MAX_DECILE_DEV is SA.PIT_MAX_DECILE_DEV is FA.PIT_MAX_DECILE_DEV
    assert QM.COVERAGE_FLOOR is SA.COVERAGE_FLOOR
    assert (QM.PBO_MAX, QM.DSR_MIN, QM.FDR_Q) == (SA.PBO_MAX, SA.DSR_MIN, SA.FDR_Q)
    assert QM.MIN_MIXTURE_ATOM is SA.MIN_MIXTURE_ATOM
    assert QM.MAX_MARGINAL_DRIFT is SA.MAX_MARGINAL_DRIFT
    assert QM.SELECTION_METRIC is FA.SELECTION_METRIC
    assert QM.GATE_STATISTIC is SA.GATE_STATISTIC


def test_the_seed_and_the_mixture_primitives_are_the_predecessors_own_objects() -> None:
    """⭐ The reproduction claim rests on this: `single_copula` reproduces NF-W7c and
    `mixall_learned` reproduces NF-W7e only if the seed, the availability stream offset and the
    mixture code path are the SAME objects, not equal values."""
    assert QM._SEED is SA._SEED is MX._SEED is FA._SEED
    assert QM.AVAIL_STREAM_OFFSET is SA.AVAIL_STREAM_OFFSET is MX.AVAIL_STREAM_OFFSET
    assert QM.assemble_mixture_bank is MX.assemble_mixture_bank
    assert QM.clamp_pi is MX.clamp_pi
    assert QM.pi_floor is MX.pi_floor
    assert QM.leg_zero_mass is MX.leg_zero_mass
    assert QM.mixture_marginal_drift is MX.mixture_marginal_drift
    assert QM.sigma_all is FA.position_sigma, "Σ must be the INCUMBENT's estimator, verbatim"
    assert QM.oracle_floor_state is FA.oracle_floor_state


def test_pit_ranks_nothing_and_the_selection_key_says_so() -> None:
    assert QM.SELECTION_IS_CRPS_NOT_PIT is SA.SELECTION_IS_CRPS_NOT_PIT
    assert "crps_q199" in QM.SELECTION_IS_CRPS_NOT_PIT
    assert "never a ranking key" in QM.SELECTION_IS_CRPS_NOT_PIT


def test_the_three_oracle_states_are_carried_so_a_TIE_is_never_read_as_a_refusal() -> None:
    """NF-W6d lost three cells to a per-form oracle floor that TIED its matched control being read
    as a REFUSAL. The three-state evaluator is imported, not re-derived."""
    assert (QM.ORACLE_RESPECTED, QM.ORACLE_VIOLATED, QM.ORACLE_INACTIVE) == (
        FA.ORACLE_RESPECTED, FA.ORACLE_VIOLATED, FA.ORACLE_INACTIVE)
    assert QM.ORACLE_INACTIVE not in (QM.ORACLE_RESPECTED, QM.ORACLE_VIOLATED)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. The MARGINAL-CAP verdict — four states, each independently reachable
# ══════════════════════════════════════════════════════════════════════════════════════════════
_CAP_KW = dict(cap_mean=0.52, predecessor_cap_mean=0.2687, realized_atom=0.5162,
               installed_atom=0.51, clamp_binding_share=0.02,
               binding_legs={"passing_yards": 1.0}, pit_matched_foil=0.0648)


def test_the_cap_verdict_CLEARS_only_when_the_cap_moved_AND_an_arm_clears_the_bar() -> None:
    got = QM.marginal_cap_verdict(pit_by_arm={"zm_conditional": 0.041}, **_CAP_KW)
    assert got["state"] == QM.CAP_CLEARS, got
    assert got["cap_was_lifted"] is True
    assert "MARGINAL layer was QB's binding constraint" in got["reading"]


def test_the_cap_verdict_reports_RESIDUAL_when_the_cap_moved_and_no_arm_clears() -> None:
    """⭐ The state that says "the atom cap was real but not the whole ceiling" — and it must be a
    CONSTRAINT shape, never a power shortfall: no fold count moves a fixed bar (NF-D18)."""
    got = QM.marginal_cap_verdict(pit_by_arm={"zm_conditional": 0.058}, **_CAP_KW)
    assert got["state"] == QM.CAP_RESIDUAL, got
    assert "not the whole ceiling" in got["reading"]
    assert "NF-D18" in got["reading"]


def test_the_cap_verdict_reports_CAP_NOT_LIFTED_when_the_mechanism_could_not_act() -> None:
    """⭐ NF1.7 (a) / NF-D20 — "count whether the mechanism could act before crediting or condemning
    it". If the recalibration did not move the cap, every arm is its own matched foil and the contest
    passed on nothing: the thesis is UNTESTED, not refuted. ⛔ This must NOT read as a null about QB,
    even when the PIT happens to clear."""
    kw = dict(_CAP_KW, cap_mean=0.2700)                  # a lift of 0.0013, below MIN_CAP_LIFT
    for pit in (0.041, 0.058):                           # reachable regardless of the PIT
        got = QM.marginal_cap_verdict(pit_by_arm={"zm_conditional": pit}, **kw)
        assert got["state"] == QM.CAP_INACTIVE, got
        assert got["cap_was_lifted"] is False
        assert "UNTESTED, not refuted" in got["reading"]


def test_the_cap_verdict_is_UNDEFINED_when_the_position_was_not_scored() -> None:
    got = QM.marginal_cap_verdict(pit_by_arm={}, **_CAP_KW)
    assert got["state"] == QM.CAP_UNDEFINED, got
    got2 = QM.marginal_cap_verdict(pit_by_arm={"zm_conditional": 0.04},
                                   **dict(_CAP_KW, cap_mean=float("nan")))
    assert got2["state"] == QM.CAP_UNDEFINED, got2


def test_an_unavailable_predecessor_baseline_can_never_satisfy_the_cap_lift() -> None:
    """⛔ NF1.7 (a) again, on the input side: if the predecessor's record cannot be read, the lift is
    UNEVALUABLE. It must not fall through to a pass — which is exactly what a `nan` comparison would
    do if the rule used `not (lift < min)` instead of `lift >= min`."""
    got = QM.marginal_cap_verdict(pit_by_arm={"zm_conditional": 0.04},
                                  **dict(_CAP_KW, predecessor_cap_mean=float("nan")))
    assert got["cap_was_lifted"] is False
    assert got["state"] != QM.CAP_CLEARS


def test_the_min_cap_lift_is_derived_from_the_bar_and_the_recorded_decile() -> None:
    """The activity floor is a DESIGN quantity, not a tuned one: the bar is a 0.05 max-decile
    deviation and NF-W7e RECORDED the QB first decile at 0.162, so ≥ 0.012 of mass must move out of
    the bottom decile for any arm to clear. A floor below that would let an arm that cannot possibly
    clear the bar count as having turned the knob."""
    assert QM.MIN_CAP_LIFT == pytest.approx(0.162 - (0.10 + QM.PIT_MAX_DECILE_DEV), abs=1e-9)


def test_the_cap_verdict_states_are_distinct_and_enumerated() -> None:
    assert len(set(QM.CAP_STATES)) == 4
    assert set(QM.CAP_STATES) == {QM.CAP_CLEARS, QM.CAP_RESIDUAL, QM.CAP_INACTIVE,
                                 QM.CAP_UNDEFINED}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The refusal text must not promise data can fix a constraint (NF-D18)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_refusal_remedy_names_a_mechanism_and_never_more_seasons() -> None:
    assert "NONE" in QM.REFUSAL_REMEDY
    assert "NF-D18" in QM.REFUSAL_REMEDY
    assert "FRESH registration" in QM.REFUSAL_REMEDY
    low = QM.REFUSAL_REMEDY.lower()
    assert "more seasons" not in low.replace("never more seasons", "")
    # ⭐ and the mechanism text must NOT still blame the marginal layer — that is the answer this
    # story spends, so a refusal here has to name the NEXT residual, not repeat the last one
    assert "no longer the atom the marginals forbid" in QM.REFUSAL_MECHANISM


def test_the_anchor_and_statistical_check_sets_partition_the_new_clauses() -> None:
    """Every clause this story ADDS must be classified, or `classify` would silently treat a failing
    new clause as neither statistical nor anchor and mis-state the null (the E11.30 "a tier enforced
    only by a table row is not enforced" shape, applied to a gate partition)."""
    added = {"zero_mass_hits_target", "positive_law_preserved", "matched_foil_identity",
             "cap_was_lifted", "per_leg_calibration_not_degraded", "predecessor_reproduces"}
    assert added <= set(QM.ANCHOR_CHECKS), sorted(added - set(QM.ANCHOR_CHECKS))
    assert not (set(QM.ANCHOR_CHECKS) & set(QM.STATISTICAL_CHECKS)), "a clause is in BOTH sets"
    assert "pit_flat_ok" in QM.STATISTICAL_CHECKS


def test_the_per_leg_clause_forbids_buying_the_atom_by_wrecking_the_parts() -> None:
    """Recalibrating a marginal CHANGES a NF-W6d certified cell. The tolerance is zero degradation
    of the summed PRICED-leg CRPS, which makes the clause two-sided: if the diagnosis is right the
    legs IMPROVE, and if it is wrong this is where it shows."""
    assert QM.MAX_PER_LEG_CRPS_DEGRADATION == 0.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The mechanism ACTS — the thesis, demonstrated rather than asserted
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_recalibration_lifts_the_atom_cap_and_un_clamps_the_availability_split() -> None:
    """⭐ THE WHOLE THESIS, on banks whose defect is the one NF-W7e measured: an atom-free continuous
    leg caps `min_j P̂_j(0)` at ~0, the clamp then binds on every row and the mixture installs NO
    atom. Recalibrating lifts the cap above what π̂ asks, the clamp stops binding, and the installed
    atom lands on the true inactivity rate."""
    b = _banks()
    q = 0.45
    pi = np.full(len(b), 1.0 - q)
    cond, marg = np.full(QM.N_LEGS, 0.2), np.full(QM.N_LEGS, 0.5)
    _, served = QM.clamp_pi(pi, b)
    t = QM.zero_targets(QM.PRIMARY_ARM, banks=b, pi_hat=pi, cond_rate=cond, marg_rate=marg)
    recal = QM.resplice_zero_mass(b, t)
    _, after = QM.clamp_pi(pi, recal)

    assert QM.atom_cap(b) < QM.MIN_CAP_LIFT, "the fixture does not carry the defect under repair"
    assert QM.atom_cap(recal) - QM.atom_cap(b) >= QM.MIN_CAP_LIFT, "the cap did not move"
    assert served["clamp_binding_share"] == 1.0, "the fixture's clamp should bind everywhere"
    assert after["mean_installed_atom"] > served["mean_installed_atom"]
    assert after["mean_installed_atom"] == pytest.approx(q, abs=2 * QM.GRID_STEP)


def test_the_binding_leg_diagnostic_names_the_cell_that_caps_the_atom() -> None:
    """The premise must be AUDITABLE, not assumed: the diagnostic has to point at the leg with the
    least zero mass. NF-W7e named `QB|passing_yards` off an 89-row serving proof; this story reports
    what actually bound the cap on every fold."""
    # ⛔ the fixture must make ONE leg UNIQUELY lowest, or `argmin` ties and the assertion passes on
    # whichever leg happens to come first — which is how the first cut of this test read `attempts`
    # (also atom-free in `_banks`) as the binding leg and proved nothing about the diagnostic.
    n, target = 40, 2
    b = np.empty((n, QM.N_LEGS, QM.N_LEVELS))
    for j in range(QM.N_LEGS):
        atom = 0.0 if j == target else 0.60           # every other leg carries a real atom
        k = int(round(atom * QM.N_LEVELS))
        b[:, j, :] = np.sort(np.concatenate([np.zeros(k),
                                             np.linspace(1.0, 50.0, QM.N_LEVELS - k)]))
    zm = QM.leg_zero_mass(b)
    assert zm[:, target].max() < zm[:, [j for j in range(QM.N_LEGS) if j != target]].min(), \
        "the fixture does not make the target leg uniquely lowest"
    share = QM.binding_leg_share(b)
    assert share == {QM.LEGS[target]: 1.0}, share
    tbl = QM.leg_zero_mass_table(b, np.zeros((n, QM.N_LEGS)))
    assert tbl[QM.LEGS[target]]["predicted_zero_mass"] == 0.0
    # realized all-zero against a no-atom marginal is the story's premise, and the table shows it
    assert tbl[QM.LEGS[target]]["gap_realized_minus_predicted"] == pytest.approx(1.0)
    # …and the recalibrated binding share must MOVE off that leg once its atom is installed
    recal = QM.resplice_zero_mass(b, np.full(b.shape[:2], 0.70))
    assert QM.LEGS[target] not in QM.binding_leg_share(recal)


def test_the_conditional_zero_rate_refuses_a_population_below_the_estimation_floor() -> None:
    """NF1.7 (a): a rate estimated on a handful of rows is a made-up number wearing an estimate's
    badge. It must RAISE, not default."""
    tiny = np.zeros((QM.MIN_ESTIMATION_ROWS - 1, QM.N_LEGS))
    with pytest.raises(ValueError, match="estimation floor"):
        QM.conditional_zero_rate(tiny)
    with pytest.raises(ValueError, match="estimation floor"):
        QM.marginal_zero_rate(tiny)


def test_realized_zero_uses_the_same_threshold_the_draw_path_uses() -> None:
    """A marginal's atom and the realized event it is compared against must be the SAME event. A
    negative rushing yardage and a zero are the same assembled outcome, because `FA.draw_legs`
    floors at 0 and rounds integer legs."""
    raw = np.zeros((3, QM.N_LEGS))
    for j, leg in enumerate(QM.LEGS):
        raw[0, j] = -3.0                                   # negative → a zero outcome
        raw[1, j] = 0.4 if leg in QM.INTEGER_LEGS else 0.4  # rounds to 0 only for integer legs
        raw[2, j] = 100.0
    z = QM.realized_zero(raw)
    assert np.all(z[0]), "a negative realization is not read as a zero outcome"
    assert np.all(~z[2])
    for j, leg in enumerate(QM.LEGS):
        assert bool(z[1, j]) is (leg in QM.INTEGER_LEGS)


def test_the_predecessor_baseline_is_read_from_the_record_and_still_matches_the_prereg() -> None:
    """⭐ NF1.9-R: never trust a NAME for a measurement. The cap-lift baseline is READ from NF-W7e's
    committed record at run time; the constants exist only so the pre-registration is legible. This
    asserts the record still carries them — if NF-W7e's record were ever regenerated with different
    figures, the pre-registration's §0 table would be stale and this goes RED."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7f_qb_marginal as R
    base = R.predecessor_cap_baseline()
    assert base["available"], base
    assert base["matches_preregistered_constants"], base
    assert base["atom_cap_mean"] == pytest.approx(QM.PREDECESSOR_CAP_MEAN, abs=1e-4)
    assert base["realized_all_zero_rate"] == pytest.approx(QM.PREDECESSOR_REALIZED_ATOM, abs=1e-4)
    assert base["best_qb_pit"] == pytest.approx(QM.PREDECESSOR_BEST_QB_PIT, abs=1e-4)
    # ⭐ and the predecessor must actually have CONFIRMED the marginal-layer block — this story's
    # whole premise is that verdict, so a different predecessor state means a different story
    assert base["state"] == "QB_BLOCKED_AT_THE_MARGINAL_LAYER", base


def test_the_preregistration_is_committed_and_names_the_declared_field() -> None:
    """NF-D16: the runner reads constants, and the narrative pre-registration is committed BEFORE the
    decisive run. A field named in code but not in the committed document is not pre-registered."""
    import pathlib
    doc = (pathlib.Path(QM.__file__).resolve().parent / "ablation_results"
           / "nf_w7f_preregistration.md")
    assert doc.exists(), f"the pre-registration is not committed at {doc}"
    text = doc.read_text()
    for arm in QM.REAL_ARMS:
        assert f"`{arm}`" in text, f"{arm} is in REAL_ARMS but not in the committed prereg"
    for foil in (*QM.CONTEST_FOILS, *QM.REFERENCE_FOILS):
        assert f"`{foil}`" in text, f"{foil} is a declared foil but not in the committed prereg"
    assert str(QM.MIN_CAP_LIFT) in text
    assert "QB ONLY" in text


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The arm-attribution defect the SMOKE found — the clause must read the WINNER, not the primary
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fold_block(*, scores: dict, per_leg_rel: dict, identity_gap: dict) -> dict:
    """A minimal-but-REAL `run_position` output for one (fold, QB) — enough for `select_position` to
    run its actual code path (INC-39: one test must exercise the real leg, not a monkeypatched one).
    Only the three arm-keyed structures under test carry per-arm variation; everything else is
    plausible and identical across arms so the assertions can only turn on the arm attribution."""
    labels = list(scores)
    pit = {lab: {"max_decile_dev": 0.02, "decile_counts": [10] * 10,
                 "decile_freq": [0.1] * 10} for lab in QM.WATCHED}
    # ⚠️ `n`, not `n_rows` — the real `_pooled_coverage` reads `KW.coverage80_dense`'s own key. The
    # first cut of this fixture used `n_rows` and the REAL selection leg raised `KeyError: 'n'`,
    # which is the point of not monkeypatching it away (INC-39).
    cov = {lab: {"coverage": 0.86, "n": 700} for lab in QM.WATCHED}
    # the comonotone degenerate must out-cover the independent foil, or the inherited dependence
    # clauses fail for a reason unrelated to what these tests assert (NF-D17: isolate the clause)
    cov["assembled_comonotone"] = {"coverage": 0.94, "n": 700}
    cov["assembled_indep"] = {"coverage": 0.74, "n": 700}
    return {
        "scores": scores, "coverage": cov, "pit_flatness": pit,
        "n_train": 12000, "n_test": 700, "atom_rate_train": 0.51, "atom_rate_test": 0.51,
        "clamp": {a: {"mean_installed_atom": 0.51, "clamp_binding_share": 0.07,
                      "mean_pi_hat": 0.49, "mean_pi_used": 0.49} for a in QM.REAL_ARMS},
        "clamp_served": {"clamp_binding_share": 0.92, "mean_installed_atom": 0.26},
        "marginal_drift": {"max_probability_drift": 0.001},
        "targets": {a: {"mean": 0.8} for a in QM.REAL_ARMS},
        "resplice_edges": {a: {"share_target_clipped": 0.0} for a in QM.REAL_ARMS},
        "identities": {a: {
            "zero_mass_hits_target": {"max_abs_gap": identity_gap[a], "holds": True},
            "positive_law": {"max_drift_over_bound": 0.5, "evaluated": True, "holds": True},
        } for a in QM.REAL_ARMS},
        "matched_foil_no_op": {"max_abs_draw_gap": 0.0, "holds": True},
        "per_leg_crps": {a: {
            "by_leg": {leg: {"served_crps": 1.0, "recalibrated_crps": 1.0 + per_leg_rel[a],
                             "delta": -per_leg_rel[a],
                             "delta_by_pi_quartile": [0.1, 0.0, -0.1, -0.2], "priced": True}
                       for leg in QM.LEGS},
            "priced_legs": list(QM.LEGS),
            "served_crps_sum_priced": float(QM.N_LEGS),
            "recalibrated_crps_sum_priced": float(QM.N_LEGS) * (1.0 + per_leg_rel[a]),
            "relative_change": per_leg_rel[a]} for a in QM.REAL_ARMS},
        "leg_zero_mass_table": {leg: {"predicted_zero_mass": 0.3, "realized_zero_rate": 0.55,
                                      "gap_realized_minus_predicted": 0.25} for leg in QM.LEGS},
        "binding_leg_share_served": {"passing_yards": 1.0},
        "binding_leg_share_recalibrated": {"attempts": 1.0},
        "atom_cap": {"cap_served": 0.2658, "cap_recalibrated": 0.5431,
                     "installed_atom_recalibrated": 0.51, "installed_atom_served": 0.26,
                     "clamp_binding_share_recalibrated": 0.07,
                     "clamp_binding_share_served": 0.92,
                     "total_zero_mass_by_arm": {lab: 0.5 for lab in labels}},
        "sigma_all_note": {},
    }


def _two_folds(*, winner_arm: str, per_leg_rel: dict, identity_gap: dict) -> list[dict]:
    """Two folds whose CRPS makes `winner_arm` the unambiguous winner of the real-arm field."""
    base = {lab: 3.0 for lab in QM.ALL_LABELS}
    base.update({a: 2.9 for a in QM.REAL_ARMS})
    base[winner_arm] = 2.5                       # the winner
    base[QM.MATCHED_FOIL] = 2.8                  # the best contest foil, beaten
    base[QM.INCUMBENT_FOIL] = 2.85
    for d in QM.DEGENERATES:
        base[d] = 6.0
    out = []
    for i in range(2):
        s = {k: v + 0.001 * i for k, v in base.items()}
        out.append({"label": f"f{i}", "n_test": 700, "bank_cache": "test",
                    "positions": {"QB": _fold_block(scores=s, per_leg_rel=per_leg_rel,
                                                    identity_gap=identity_gap)}})
    return out


@pytest.mark.parametrize("winner_arm", ["zm_conditional", "zm_floor", "zm_climatology", "zm_over"])
def test_the_per_leg_clause_reads_the_SELECTED_arms_table_not_the_primarys(
        winner_arm: str) -> None:
    """⭐ THE DEFECT THE SMOKE FOUND. The first cut computed the per-leg table (and the two
    target-dependent identities) for the PRIMARY arm only, while the gate reads them for the WINNER —
    so a clause could report the primary's marginals while anchoring a different arm's. That is the
    "an anchor that describes something other than what it anchors" defect (NF1.7 (a)), and it is
    decisive here: the smoke measured the four arms moving the per-leg CRPS by +0.60% to +48.6%.

    ISOLATING FIXTURE (NF-D17): only the WINNER's table degrades; every other arm's passes. So the
    clause can only be False if it read the winner's — and only True if it read someone else's."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7f_qb_marginal as R
    rel = {a: (0.05 if a == winner_arm else -0.05) for a in QM.REAL_ARMS}
    gaps = {a: 0.0 for a in QM.REAL_ARMS}
    sel = R.select_position(_two_folds(winner_arm=winner_arm, per_leg_rel=rel,
                                      identity_gap=gaps), "QB")
    assert sel is not None and sel["winner"] == winner_arm, sel
    assert sel["per_leg_detail"]["arm_read"] == winner_arm
    assert sel["per_leg_detail"]["relative_change"] == pytest.approx(0.05)
    assert sel["anchors"]["per_leg_calibration_not_degraded"] is False, \
        "the clause passed on a DEGRADING winner — it read another arm's table"
    # …and the inverse: only the winner passing must make the clause pass
    rel_ok = {a: (-0.05 if a == winner_arm else 0.05) for a in QM.REAL_ARMS}
    sel_ok = R.select_position(_two_folds(winner_arm=winner_arm, per_leg_rel=rel_ok,
                                         identity_gap=gaps), "QB")
    assert sel_ok["anchors"]["per_leg_calibration_not_degraded"] is True, \
        "the clause failed on a non-degrading winner — it read another arm's table"


@pytest.mark.parametrize("winner_arm", ["zm_floor", "zm_over"])
def test_the_zero_mass_identity_is_also_read_for_the_selected_arm(winner_arm: str) -> None:
    """The same attribution property for a TARGET-DEPENDENT identity: only the winner's splice
    misses its target, so the clause can only fire if it read the winner's."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7f_qb_marginal as R
    rel = {a: -0.05 for a in QM.REAL_ARMS}
    gaps = {a: (1.0 if a == winner_arm else 0.0) for a in QM.REAL_ARMS}
    sel = R.select_position(_two_folds(winner_arm=winner_arm, per_leg_rel=rel,
                                      identity_gap=gaps), "QB")
    assert sel["transform_detail"]["identity_arm_read"] == winner_arm
    assert sel["anchors"]["zero_mass_hits_target"] is False, \
        "the identity passed on a winner whose splice missed its target — wrong arm read"


def test_the_availability_decomposition_is_reported_for_every_arm() -> None:
    """⭐ REPORTED, never gated. The smoke measured that the SIGN of the per-leg effect FLIPS with
    availability (it helps where the player probably did not play, hurts where he probably did), so a
    refusal that did not carry this would say "the parts got worse" without saying WHERE — the
    difference between a null that names where the answer lives and one that just closes a door."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7f_qb_marginal as R
    rel = {a: -0.01 * (i + 1) for i, a in enumerate(QM.REAL_ARMS)}
    sel = R.select_position(_two_folds(winner_arm=QM.PRIMARY_ARM, per_leg_rel=rel,
                                      identity_gap={a: 0.0 for a in QM.REAL_ARMS}), "QB")
    d = sel["per_leg_detail"]
    assert set(d["relative_change_by_arm"]) == set(QM.REAL_ARMS), d["relative_change_by_arm"]
    assert len(d["delta_by_pi_quartile_priced"]) == 4, d["delta_by_pi_quartile_priced"]
    # the decomposition must be a REPORT, not part of the gate
    assert "delta_by_pi_quartile" not in " ".join(QM.ANCHOR_CHECKS + QM.STATISTICAL_CHECKS)


def test_the_per_leg_table_helper_decomposes_by_availability() -> None:
    """The helper itself: the priced sum is what the clause reads, and the quartile decomposition
    must actually separate rows by π̂ (a decomposition that returned the same number in every bucket
    would be reporting nothing)."""
    from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7f_qb_marginal as R
    b = _banks(n=60)
    # a target that raises the atom a lot → it should HELP rows whose realized value is 0 and HURT
    # rows whose realized value is large, so a π̂ ordered with the realized value must separate them
    y = np.zeros((60, QM.N_LEGS))
    y[30:, :] = 50.0
    pi = np.concatenate([np.full(30, 0.05), np.full(30, 0.95)])   # low π̂ ⇒ the zero rows
    recal = QM.resplice_zero_mass(b, np.full(b.shape[:2], 0.90))
    w = np.ones(QM.N_LEGS)
    t = R._per_leg_table(b, recal, y, w, pi)
    assert t["priced_legs"] == list(QM.LEGS)
    q = t["by_leg"]["passing_yards"]["delta_by_pi_quartile"]
    assert len(q) == 4 and all(v is not None for v in q), q
    assert q[0] > 0 > q[-1], f"the decomposition does not separate by availability: {q}"
    assert t["relative_change"] == pytest.approx(
        (t["recalibrated_crps_sum_priced"] - t["served_crps_sum_priced"])
        / t["served_crps_sum_priced"], rel=1e-6)


def test_an_unknown_arm_is_refused_rather_than_silently_defaulted() -> None:
    b = _banks(n=4)
    with pytest.raises(KeyError, match="not in the pre-registered family"):
        QM.zero_targets("zm_not_registered", banks=b, pi_hat=np.full(4, 0.5),
                        cond_rate=np.zeros(QM.N_LEGS), marg_rate=np.zeros(QM.N_LEGS))


def test_a_non_probability_target_is_a_coding_defect_not_an_arm() -> None:
    b = _banks(n=4)
    with pytest.raises(ValueError, match="non-finite"):
        QM.resplice_zero_mass(b, np.full((4, QM.N_LEGS), np.nan))
    with pytest.raises(ValueError, match="one zero mass per"):
        QM.resplice_zero_mass(b, np.full((4, QM.N_LEGS + 1), 0.5))
