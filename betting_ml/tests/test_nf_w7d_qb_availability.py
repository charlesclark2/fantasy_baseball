"""NF-W7d guards — the QB availability mixture for the assembled fantasy-point distribution.

Every clause below is written to be INDEPENDENTLY RED-PROVABLE (NF-D17): a fixture satisfies every
OTHER clause so that only the named one can flip the result. Where a clause could pass vacuously —
a check that did not run, a comparison with nothing to compare, a mechanism that cannot act — the
test asserts the NON-VACUITY explicitly, because a guard that cannot fail is worse than none
(NF1.7 (a) / INC-38 / NF-D17).

⛔ No lake IO, no S3, no network: the modules under test are pure and the runner's decision layer
is exercised on synthetic fold scores.
"""
from __future__ import annotations

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_assembly as FA
from quant_sports_intel_models.football.nfl.fantasy import fp_availability_mixture as MX
from quant_sports_intel_models.football.nfl.fantasy import joint_draw as JD
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7c_fp_assembly as W7C
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w7d_qb_availability as R


# ── Fixtures: a zero-heavy bank tensor of exactly the shape the assembly consumes ────────────────
def _banks(n: int = 24, seed: int = 11) -> np.ndarray:
    """(n, 13, 199) sorted quantile banks with a real per-leg zero atom, like a QB's."""
    rng = np.random.default_rng(seed)
    out = np.empty((n, MX.N_LEGS, MX.N_LEVELS))
    for i in range(MX.N_LEGS):
        p0 = rng.uniform(0.35, 0.85)
        scale = rng.uniform(1.0, 30.0)
        q = np.maximum(0.0, (FA.EVAL_LEVELS - p0) / (1.0 - p0)) * scale
        out[:, i, :] = q[None, :] * rng.uniform(0.6, 1.4, size=(n, 1))
    return out


def _corr(seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    raw = np.abs(rng.normal(size=(600, MX.N_LEGS))) * (rng.random((600, MX.N_LEGS)) > 0.4)
    return FA.position_sigma(raw)[0]


def _weights(seed: int = 7) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=MX.N_LEGS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The matched foil is matched BY IDENTITY, not by re-implementation
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_mixture_at_pi_one_is_byte_identical_to_the_incumbent_construction():
    """⭐ THE LOAD-BEARING IDENTITY. `mix_off` is "the mixture machinery with the availability term
    off", and that is only a MATCHED foil if turning the term off returns EXACTLY the incumbent's
    code path. Byte-identity — not "close" — is what makes the attribution
    `mixture − mix_off` a statement about the split rather than about two implementations."""
    b, c, w = _banks(), _corr(), _weights()
    a = FA.assemble_fp_bank(b, w, corr=c, draws=200, seed=MX._SEED)
    m = MX.assemble_mixture_bank(b, w, pi=np.ones(len(b)), corr=c, draws=200, seed=MX._SEED)
    assert np.array_equal(a, m)
    # NON-VACUITY: a mixture with a real atom must NOT be byte-identical, or the test above would
    # pass for a function that ignores pi entirely.
    m2 = MX.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.5), corr=c, draws=200, seed=MX._SEED)
    assert not np.array_equal(a, m2)


def test_the_availability_stream_leaves_the_copula_columns_untouched():
    """The Bernoulli must draw from a SEPARATE generator: if it consumed base normals, the 13
    copula columns would shift and `single_copula` could no longer reproduce NF-W7c exactly."""
    b, c, w = _banks(), _corr(), _weights()
    lo = MX.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.30), corr=c, draws=150,
                                  seed=MX._SEED)
    hi = MX.assemble_mixture_bank(b, w, pi=np.full(len(b), 0.90), corr=c, draws=150,
                                  seed=MX._SEED)
    # different pi ⇒ different banks (the term acts) …
    assert not np.array_equal(lo, hi)
    # … while pi ≡ 1 still lands exactly on the availability-off construction (the stream is clean)
    assert np.array_equal(
        MX.assemble_mixture_bank(b, w, pi=np.ones(len(b)), corr=c, draws=150, seed=MX._SEED),
        FA.assemble_fp_bank(b, w, corr=c, draws=150, seed=MX._SEED))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Marginal preservation — and the NAIVE mixture that would violate it
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_mixture_preserves_every_leg_marginal_within_the_declared_tolerance():
    b, c = _banks(), _corr()
    pi = np.random.default_rng(2).uniform(0.25, 0.95, len(b))
    used, note = MX.clamp_pi(pi, b)
    drift = MX.mixture_marginal_drift(b, pi=used, corr=c)
    # NON-VACUITY FIRST: a mixture that installed no atom could not violate anything, so the
    # clause would pass on nothing. Prove the mechanism actually acted on this fixture.
    assert note["mean_installed_atom"] > MX.MIN_MIXTURE_ATOM
    assert drift["preserved"], drift
    assert drift["max_probability_drift"] <= MX.MAX_MARGINAL_DRIFT


def test_the_naive_double_counting_mixture_FAILS_the_marginal_clause():
    """⭐ THE NEGATIVE CONTROL, and the reason the clause is not décor.

    The obvious way to write an availability mixture — draw the Bernoulli, then draw each leg from
    its UNCONDITIONAL bank — counts the zero atom twice and silently under-states every stat. It is
    the defect this clause exists to catch, so it is constructed here and must be REFUSED. Without
    it, `mixture_preserves_marginals` would be a clause nobody had ever seen fail."""
    b, c = _banks(), _corr()
    pi = np.full(len(b), 0.6)
    rng = np.random.default_rng(MX._SEED)
    base_z = rng.standard_normal((len(b), 1000, MX.N_LEGS))
    u = JD.gaussian_copula_uniforms(base_z, c)
    honest = FA.draw_legs(b, u)                                   # the availability-off reference
    naive = FA.draw_legs(b, u)                                    # ⛔ NO conditional uniform shift
    alive = np.random.default_rng(MX._SEED + MX.AVAIL_STREAM_OFFSET).random(
        (len(b), 1000)) < pi[:, None]
    naive = np.where(alive[:, :, None], naive, 0.0)

    worst = 0.0
    for i in range(MX.N_LEGS):
        xo, xm = honest[:, :, i].ravel(), naive[:, :, i].ravel()
        grid = np.unique(np.quantile(xo, FA.EVAL_LEVELS))
        worst = max(worst, float(np.max(np.abs(
            (xo[None, :] <= grid[:, None]).mean(axis=1)
            - (xm[None, :] <= grid[:, None]).mean(axis=1)))))
    assert worst > MX.MAX_MARGINAL_DRIFT * 5, (
        f"the double-counting mixture drifted only {worst} — the marginal clause cannot "
        f"distinguish it from the honest construction and is therefore vacuous")


def test_the_marginal_clause_validates_the_PATH_THAT_IS_SCORED_not_a_second_copy(monkeypatch):
    """⭐ THE GUARD A RED PROOF DEMANDED. The first cut implemented the conditional uniform shift
    twice — once in the assembly, once in the diagnostic — so deleting it from the assembly (i.e.
    shipping the double-counted-atom defect) left the entire suite GREEN: the clause was validating
    its own copy. Both must now route through the SAME callable, and this asserts it by INVOCATION
    rather than by reading the source (NF-C0e: wired ≠ invoked)."""
    seen: list[str] = []
    real = MX.mixture_leg_draws

    def spy(*a, **k):
        seen.append("called")
        return real(*a, **k)

    monkeypatch.setattr(MX, "mixture_leg_draws", spy)
    b, c, w = _banks(8), _corr(), _weights()
    pi, _ = MX.clamp_pi(np.full(8, 0.6), b)
    MX.assemble_mixture_bank(b, w, pi=pi, corr=c, draws=50)
    assert seen, "the assembly does not route through `mixture_leg_draws`"
    seen.clear()
    MX.mixture_marginal_drift(b, pi=pi, corr=c, draws=50, n_rows=8)
    assert seen, "the marginal diagnostic does not route through `mixture_leg_draws`"


def test_the_drift_metric_is_a_probability_not_a_value_ratio():
    """A first cut measured drift in inter-decile units and read 10.0 on an EXACT construction,
    because a mostly-zero integer leg has an inter-decile range of 0 or 1. A Kolmogorov distance
    is bounded by 1 by construction — assert the units, so the regression cannot return."""
    b, c = _banks(), _corr()
    pi, _ = MX.clamp_pi(np.full(len(b), 0.5), b)
    drift = MX.mixture_marginal_drift(b, pi=pi, corr=c)
    assert "probability" in drift["units"]
    assert all(0.0 <= v <= 1.0 for v in drift["per_leg"].values())


def test_the_drift_diagnostic_refuses_an_empty_slice_rather_than_passing_on_nothing():
    with pytest.raises(ValueError, match="did not run"):
        MX.mixture_marginal_drift(_banks()[:0], pi=np.array([]), corr=_corr())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The atom: what "plays" means, and that it is NOT the roster label
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_activity_indicator_is_the_all_zero_event_the_mechanism_names():
    raw = np.zeros((5, MX.N_LEGS))
    raw[1, 0] = 3.0
    raw[2, -1] = 1.0
    raw[3, :] = 0.0
    assert MX.activity_indicator(raw).tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]
    assert MX.atom_rate(raw) == pytest.approx(0.6)


def test_a_negative_leg_value_still_counts_as_activity():
    """Two priced legs carry negative WEIGHTS, and a leg VALUE is clipped at 0 in the draw — but
    the indicator reads the realized stat line, so it must not silently treat a sign as absence."""
    raw = np.zeros((2, MX.N_LEGS))
    raw[0, 3] = -1.0
    assert MX.activity_indicator(raw).tolist() == [1.0, 0.0]


def test_the_availability_label_never_reads_the_roster_status_or_the_frame_label():
    """⛔ NF-W4's target-leak tokens, applied to this story's source. NF-W7d derives availability
    from the realized STAT LINES the assembly is already scored against — it introduces no new
    source, no new feature family and no new provenance gate, and reading `label` / `status` /
    `offense_pct` here would quietly make that claim false."""
    import inspect
    src = "\n".join(line.split("#", 1)[0] for line in inspect.getsource(MX).splitlines())
    for token in ("offense_pct", '"label"', "'label'", '"status"', "'status'"):
        assert token not in src, f"NF-W7d source reads `{token}` — see the NF-W4 target-leak clause"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Σ on ACTIVE rows only — the conditional half
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_sigma_played_is_estimated_on_active_rows_and_differs_from_the_unconditional_sigma():
    """The whole hypothesis is that these two matrices differ (NF-W7c measured QB at 0.239 vs
    0.127). If the fixture could not tell them apart, every downstream comparison would be a
    comparison of an arm with itself."""
    rng = np.random.default_rng(4)
    active = np.abs(rng.normal(size=(400, MX.N_LEGS))) + 0.5
    raw = np.vstack([active, np.zeros((400, MX.N_LEGS))])
    sig_all, _ = FA.position_sigma(raw)
    sig_act, note = MX.sigma_played(raw)
    off = ~np.eye(MX.N_LEGS, dtype=bool)
    assert note["population"] == "active_rows_only"
    assert note["n_active"] == 400 and note["n_all"] == 800
    # the atom manufactures co-movement the conditional estimate does not see
    assert np.abs(sig_all[off]).mean() > np.abs(sig_act[off]).mean()


def test_sigma_played_refuses_below_the_row_floor_rather_than_falling_back():
    raw = np.zeros((300, MX.N_LEGS))
    raw[:10] = np.abs(np.random.default_rng(1).normal(size=(10, MX.N_LEGS))) + 1.0
    with pytest.raises(ValueError, match="ACTIVE rows"):
        MX.sigma_played(raw)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The clamp — the exactness condition, enforced and COUNTED
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_clamp_raises_pi_to_the_marginal_admissible_floor_and_records_the_binding():
    b = _banks()
    floor = MX.pi_floor(b)
    used, note = MX.clamp_pi(np.zeros(len(b)), b)
    assert np.allclose(used, floor)
    assert note["clamp_binding_share"] == 1.0
    assert note["mean_upward_move"] > 0


def test_the_clamp_never_lowers_an_admissible_pi():
    b = _banks()
    pi = np.clip(MX.pi_floor(b) + 0.05, 0, 1)
    used, note = MX.clamp_pi(pi, b)
    assert np.allclose(used, pi)
    assert note["clamp_binding_share"] == 0.0


def test_a_bank_with_no_zero_mass_pins_pi_to_one_so_the_mechanism_CANNOT_act():
    """⭐ NF1.9 / NF-D20: the failure mode this story must be able to SEE. If every leg's bank
    places no mass at zero, no admissible π installs an atom, the mixture IS its own matched foil,
    and the contest becomes an arm against itself. It must surface as an INACTIVE mechanism, never
    as a quiet pass."""
    b = np.tile(np.linspace(1.0, 50.0, MX.N_LEVELS), (6, MX.N_LEGS, 1))
    used, note = MX.clamp_pi(np.full(6, 0.4), b)
    assert np.allclose(used, 1.0)
    assert note["mean_installed_atom"] == 0.0
    assert note["mean_installed_atom"] < MX.MIN_MIXTURE_ATOM


def test_the_zero_mass_read_is_aligned_to_the_samplers_own_grid_and_rounding():
    """A leg whose bank sits entirely below 0.5 draws as zero after `FA.draw_legs`' rounding, so
    that mass is removable; a continuous yardage leg is measured at 0.0 instead."""
    b = np.zeros((1, MX.N_LEGS, MX.N_LEVELS))
    b[0, MX.LEGS.index("receptions"), :] = 0.4                    # integer leg, rounds to 0
    b[0, MX.LEGS.index("passing_yards"), :] = 0.4                 # continuous, is NOT zero
    zm = MX.leg_zero_mass(b)[0]
    assert zm[MX.LEGS.index("receptions")] == pytest.approx(FA.EVAL_LEVELS[-1])
    assert zm[MX.LEGS.index("passing_yards")] == 0.0


def test_the_mixture_refuses_a_pi_that_is_not_a_probability():
    b, c, w = _banks(6), _corr(), _weights()
    for bad, match in ((np.full(6, 1.5), "not a probability"),
                       (np.full(6, np.nan), "not a probability"),
                       (np.ones(3), "one availability probability per assembled row")):
        with pytest.raises(ValueError, match=match):
            MX.assemble_mixture_bank(b, w, pi=bad, corr=c, draws=20)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. The declared field partitions, and every arm carries its own anchors
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_declared_field_partitions_and_nothing_is_double_counted():
    groups = (MX.REAL_ARMS, MX.CONTEST_FOILS, MX.REFERENCE_FOILS, MX.DEGENERATES)
    flat = [x for g in groups for x in g]
    assert len(flat) == len(set(flat))
    assert set(MX.ELIGIBLE) == set(MX.REAL_ARMS) | set(MX.CONTEST_FOILS)
    # ⛔ the reference foils are diagnostics and must NOT enter the deflated field (MH2.1 (a))
    assert not set(MX.REFERENCE_FOILS) & set(MX.ELIGIBLE)
    assert not set(MX.DEGENERATES) & set(MX.ELIGIBLE)


def test_every_real_arm_has_its_OWN_form_oracle_and_matched_n_control():
    for arm in MX.REAL_ARMS:
        assert f"oracle__{arm}" in MX.ANCHORS      # NF-D16 (g‴): per FORM, never field-wide
        assert f"matched_n__{arm}" in MX.ANCHORS   # NF1.9 (f): the capacity control
    assert "oracle__foil_direct_points" in MX.ANCHORS, (
        "the activity POSITIVE CONTROL is missing — without an oracle that provably ACTS, an "
        "all-INACTIVE ceiling table cannot be distinguished from a broken detector")
    # ⛔ an arm that estimates nothing gets no oracle: an anchor that cannot differ from what it
    # anchors is décor, and scoring it 'respected' is a pass on nothing (NF1.7 (a))
    assert "oracle__assembled_indep" not in MX.ANCHORS
    assert "oracle__mix_off" not in MX.ANCHORS


def test_every_pre_registered_arm_has_a_distinct_estimator_and_an_unknown_one_is_refused():
    assert set(MX.PI_FITTERS) == set(MX.REAL_ARMS)
    assert len({MX.PI_FITTERS[a] for a in MX.REAL_ARMS}) == len(MX.REAL_ARMS)
    with pytest.raises(KeyError, match="not in the pre-registered family"):
        MX.pi_for_arm("mix_nonexistent", None, None, [], train_raw=np.zeros((1, MX.N_LEGS)))


def test_the_gate_clause_partition_covers_every_declared_check():
    """A clause that is composed but classified into neither bucket cannot be read by
    `classify` — it would silently stop distinguishing a CONSTRAINT refusal from a power one."""
    sel = _synthetic_selection()
    composed = set(R.compose_gate(sel, True)["checks"])
    declared = set(MX.STATISTICAL_CHECKS) | set(MX.ANCHOR_CHECKS)
    assert composed <= declared, sorted(composed - declared)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. Inherited constants are not softened in the successor to a refusal
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_every_bar_this_story_could_have_softened_is_inherited_by_reference():
    """⛔ E2.1-r in its most literal form: re-setting a bar a predecessor FAILED, inside the story
    written to clear it, would make the whole result unfalsifiable."""
    assert MX.PIT_MAX_DECILE_DEV == FA.PIT_MAX_DECILE_DEV == 0.05
    assert MX.COVERAGE_FLOOR == FA.COVERAGE_FLOOR == 0.80
    assert (MX.PBO_MAX, MX.DSR_MIN, MX.FDR_Q) == (FA.PBO_MAX, FA.DSR_MIN, FA.FDR_Q)
    assert R.GATE_LEAGUE == W7C.GATE_LEAGUE
    assert MX.ORACLE_VIOLATION_ALPHA == FA.ORACLE_VIOLATION_ALPHA
    assert MX.ORACLE_INVERSION_MATERIAL_FRACTION == FA.ORACLE_INVERSION_MATERIAL_FRACTION
    assert MX.oracle_floor_state is FA.oracle_floor_state


def test_the_draw_seed_is_inherited_so_the_incumbent_can_be_reproduced_exactly():
    assert MX._SEED == FA._SEED, (
        "a fresh seed would move the common-random-number blocks and make the "
        "incumbent-reproduction control approximate, which needs a tolerance knob")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. PIT gates; it must never RANK (a criterion a degenerate wins is fatal — NF1.8)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pit_block(dev: float) -> dict:
    counts = [100] * 10
    counts[0] = int(100 + dev * 1000)
    return {"max_decile_dev": dev, "n": sum(counts), "decile_counts": counts,
            "decile_freq": [c / sum(counts) for c in counts], "worst_decile": 0}


def _fold_result(label: str, scores: dict[str, float], *, pit: dict[str, float] | None = None,
                 cov: dict[str, float] | None = None, position: str = "QB",
                 atom: float = 0.30, drift: float = 0.001) -> dict:
    watched = (*MX.REAL_ARMS, *MX.FOILS, "assembled_comonotone", "pi_permuted")
    pit = pit or {}
    cov = cov or {}
    return {"label": label, "n_test": 690, "positions": {position: {
        "scores": {lab: scores[lab] for lab in MX.ALL_LABELS},
        "coverage": {lab: {"coverage": cov.get(lab, 0.85), "n": 690, "binomial_se": 0.015,
                           "blocking_shortfall": False} for lab in watched},
        "pit_flatness": {lab: _pit_block(pit.get(lab, 0.02)) for lab in watched},
        "n_train": 9000, "n_test": 690, "atom_rate_train": 0.54, "atom_rate_test": 0.53,
        "pi_summary": {a: {"mean": 0.5, "sd": 0.2, "p10": 0.2, "p90": 0.9}
                       for a in MX.REAL_ARMS},
        "clamp": {a: {"mean_installed_atom": atom, "clamp_binding_share": 0.1}
                  for a in MX.REAL_ARMS},
        "marginal_drift": {"max_probability_drift": drift},
        "sigma_note_played": {}, "sigma_all_note": {},
        "mean_abs_offdiag": {"all_rows": 0.239, "active_rows": 0.127},
    }}}


def _base_scores(**over: float) -> dict[str, float]:
    s = {lab: 3.0 for lab in MX.ALL_LABELS}
    s.update({a: 2.50 for a in MX.REAL_ARMS})
    s.update({"single_copula": 2.60, "mix_off": 2.58, "assembled_indep": 2.70,
              "foil_direct_points": 2.55, "assembled_comonotone": 2.80, "pi_permuted": 2.62,
              "permuted_direct": 4.80, "nihilist_zero": 6.6, "zero_width": 7.9,
              "max_width": 10.5})
    for a in MX.REAL_ARMS:
        s[f"oracle__{a}"] = s[a] - 0.01                 # a peek that ACTS ⇒ RESPECTED
        s[f"matched_n__{a}"] = s[a] + 0.01
    s["oracle__foil_direct_points"] = 1.70
    s.update(over)
    return s


def _folds(n: int = 8, **over: float) -> list[dict]:
    out = []
    for i in range(n):
        s = _base_scores(**over)
        jitter = 0.001 * ((-1) ** i)
        out.append(_fold_result(f"F{i}", {k: v + jitter * (k in MX.REAL_ARMS) for k, v in
                                          s.items()}))
    return out


def _synthetic_selection(**over: float) -> dict:
    sel = R.select_position(_folds(**over), "QB")
    assert sel is not None
    return sel


def test_the_winner_is_ranked_on_CRPS_even_when_another_arm_has_a_better_PIT():
    """⭐ RED-PROVABLE, and it is the story's most dangerous available mistake. `mix_const` is
    given the WORST CRPS and the BEST PIT; ranking on PIT would select it. NF-W7c measured the
    over-correlated degenerate posting the best PIT in the whole QB field, so a PIT-ranked contest
    hands itself to a construction registered to lose."""
    folds = []
    for i in range(8):
        s = _base_scores(mix_const=2.90)
        folds.append(_fold_result(f"F{i}", s,
                                  pit={"mix_const": 0.005, "mix_learned": 0.045,
                                       "assembled_comonotone": 0.001}))
    sel = R.select_position(folds, "QB")
    assert sel["winner"] != "mix_const"
    assert sel["winner"] == "mix_learned"
    # …and the degenerate's PIT is RECORDED, which is what proves the bar was never a criterion
    assert sel["pit_by_label"]["assembled_comonotone"] < sel[
        "pit_flatness_winner_max_decile_dev"]


def test_beats_foil_binds_against_the_CONTEST_foils_only():
    """`foil_direct_points` is given the best score in the field. It must not become the binding
    foil: NF-W7c §11.4 records that a null against it is an ARCHITECTURE verdict, not this
    story's hypothesis. It is still SCORED and REPORTED."""
    sel = _synthetic_selection(foil_direct_points=1.90)
    assert sel["best_foil"] in MX.CONTEST_FOILS
    assert sel["attribution"]["beats_direct_points_REPORT_ONLY"] is False
    assert sel["attribution"]["delta_vs_direct_points_REPORT_ONLY"] < 0
    # ⛔ and the report-only reading may never reach the gate
    assert "beats_direct_points_REPORT_ONLY" not in R.compose_gate(sel, True)["checks"]


def test_the_pit_clause_reads_the_selected_arm_against_the_inherited_bar():
    assert _synthetic_selection()["pit_flat_ok"] is True
    rough = R.select_position(
        [_fold_result(f"F{i}", _base_scores(), pit={a: 0.09 for a in MX.REAL_ARMS})
         for i in range(8)], "QB")
    assert rough["pit_flat_ok"] is False
    assert rough["pit_flatness_winner_max_decile_dev"] > MX.PIT_MAX_DECILE_DEV


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. PIT instrumentation — NF-W7c §11.2's carded gap, closed
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_pit_record_carries_its_direction_not_only_its_magnitude():
    u = np.concatenate([np.random.default_rng(3).random(900), np.full(100, 0.05)])
    d = MX.pit_detail(u)
    assert len(d["decile_counts"]) == 10 and sum(d["decile_counts"]) == len(u)
    assert d["worst_decile"] == 0            # the excess mass was placed in the first decile
    assert d["max_decile_dev"] == pytest.approx(
        abs(d["decile_freq"][0] - 0.1), abs=1e-3)


def test_the_pooled_pit_pools_over_ROWS_and_is_reported_beside_the_binding_convention():
    counts = [[200, 100, 100, 100, 100, 100, 100, 100, 50, 50],
              [50, 50, 100, 100, 100, 100, 100, 100, 100, 200]]
    pooled = MX.pooled_pit(counts)
    assert pooled["n"] == 2000
    assert pooled["decile_freq"][0] == pytest.approx(0.125)
    assert pooled["max_decile_dev"] == pytest.approx(0.025)


def test_the_calibrated_pit_null_reproduces_the_figure_NF_W7c_reported_independently():
    """NF-W7c §11.1 states a perfectly calibrated model at n ≈ 690 posts a median max-decile
    deviation of 0.0201 and exceeds 0.05 essentially never. An independent re-derivation landing
    on the same number is a cross-check on the whole PIT instrument."""
    ref = MX.pit_null_reference(690, draws=1500)
    assert ref["median"] == pytest.approx(0.0201, abs=0.003)
    assert ref["p_exceeds_bar_under_perfect_calibration"] < 0.01
    assert ref["bar"] == MX.PIT_MAX_DECILE_DEV


def test_the_pit_null_refuses_an_empty_sample_rather_than_returning_a_reference():
    with pytest.raises(ValueError, match="pass on nothing"):
        MX.pit_null_reference(0)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The incumbent-reproduction identity proof
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_incumbent_reproduction_is_exact_and_a_tiny_drift_still_fails_it():
    rec = {"F0": 2.4628540673, "F1": 2.5013}
    assert MX.incumbent_reproduction(dict(rec), rec)["reproduces"] is True
    drifted = {"F0": rec["F0"] + 1e-6, "F1": rec["F1"]}
    out = MX.incumbent_reproduction(drifted, rec)
    assert out["reproduces"] is False and out["max_abs_gap"] == pytest.approx(1e-6)


def test_a_reproduction_that_COULD_NOT_RUN_is_never_scored_as_a_pass():
    """NF1.7 (a): no overlapping fold labels means the comparison did not happen. A control that
    did not run must fail closed, or an absent predecessor record would silently license the run."""
    out = MX.incumbent_reproduction({"F0": 1.0}, {"OTHER": 1.0})
    assert out["reproduces"] is False and out["n_folds_compared"] == 0
    assert "did not run" in out["note"]


def test_the_reproduction_target_names_NF_W7cs_own_record_and_primary_arm():
    assert MX.INCUMBENT_RECORD_RELPATH == FA.RECORD_RELPATH
    assert MX.INCUMBENT_ARM == FA.PRIMARY_ARM
    assert MX.INCUMBENT_FOIL in MX.CONTEST_FOILS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 11. Classification — the NF-D18 shape, and no misleading trigger
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_a_PIT_only_refusal_is_CONSTRAINT_REFUSED_with_NO_sample_size_trigger(monkeypatch):
    """⭐ A max-decile deviation against a FIXED bar accumulates no sampling error that more folds
    can remove, so publishing "+N folds" here would be the misleading direction NF-D18 forbids.
    RED-PROVABLE: the same selection with a passing PIT does not take this branch."""
    monkeypatch.setattr(R, "_incumbent_record_scores", lambda: None)
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["pit_flat_ok"] = False
    out = R.classify(sel, checks)
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert out["retest_trigger"] == MX.REFUSAL_REMEDY
    assert "never more seasons" not in (out["retest_trigger"] or "")  # the remedy names a mechanism
    assert "NONE" in out["retest_trigger"]


def test_an_anchor_only_refusal_is_also_CONSTRAINT_REFUSED_and_names_the_failing_anchors():
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["mixture_is_active"] = False
    out = R.classify(sel, checks)
    assert out["state"] == "CONSTRAINT_REFUSED"
    assert out["retest_trigger"] is None
    assert out["failing_anchor_checks"] == ["mixture_is_active"]


def test_the_declared_field_size_is_passed_and_its_SOURCE_is_recorded(monkeypatch):
    """MH2.7: the instrument refuses to prescribe a field smaller than the declared one, but it
    cannot adjudicate the claim — so the claim must land somewhere a reviewer can check it."""
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    checks["beats_foil"] = False
    out = R.classify(sel, checks)
    assert "field_remedy_admissible" in out
    assert "preregistration" in out["declared_field_size_source"]
    assert f"{len(MX.REAL_ARMS)}-arm declared family" in out["pbo_state"]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 12. The gate composes every clause this story added, and they can each fail
# ══════════════════════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("clause", ["mixture_is_active", "mixture_preserves_marginals",
                                    "incumbent_reproduces", "pit_flat_ok"])
def test_each_clause_this_story_adds_is_composed_and_can_block_a_ship(clause):
    sel = _synthetic_selection()
    checks = dict.fromkeys(R.compose_gate(sel, True)["checks"], True)
    assert clause in checks
    checks[clause] = False
    assert not all(checks.values())


def test_an_inactive_mixture_fails_its_clause_rather_than_passing_quietly():
    """RED-PROVABLE by fixture: the ONLY thing changed is the installed atom."""
    active = R.select_position(_folds(), "QB")
    assert active["anchors"]["mixture_is_active"] is True
    inert = R.select_position(
        [_fold_result(f"F{i}", _base_scores(), atom=0.0) for i in range(8)], "QB")
    assert inert["anchors"]["mixture_is_active"] is False


def test_a_drifting_marginal_fails_its_clause_rather_than_passing_quietly():
    ok = R.select_position(_folds(), "QB")
    assert ok["anchors"]["mixture_preserves_marginals"] is True
    bad = R.select_position(
        [_fold_result(f"F{i}", _base_scores(), drift=MX.MAX_MARGINAL_DRIFT * 3)
         for i in range(8)], "QB")
    assert bad["anchors"]["mixture_preserves_marginals"] is False


def test_the_permutation_clause_reads_the_availability_signal_as_well_as_the_labels():
    """`pi_permuted` shuffles π across players: same marginal, wrong rows. A mixture that beat
    nothing but its own shuffled availability would have learned nothing about availability."""
    sel = _synthetic_selection()
    assert sel["anchors"]["winner_beats_pi_permuted"] is True
    beaten = R.select_position(
        [_fold_result(f"F{i}", _base_scores(pi_permuted=2.30)) for i in range(8)], "QB")
    assert beaten["anchors"]["winner_beats_pi_permuted"] is False
    assert R.compose_gate(beaten, True)["checks"]["permutation_behaves"] is False


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 13. Attribution — the two-step decomposition the card asks for
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_the_attribution_separates_the_split_from_the_sigma_population():
    """A single Δ against the incumbent bundles two changes (the availability split AND estimating
    Σ on active rows). NF-D15 (g′): a win must be attributable to its CLAIMED channel."""
    sel = _synthetic_selection()
    a = sel["attribution"]
    assert a["delta_vs_mix_off_the_split"] == pytest.approx(2.58 - 2.50, abs=2e-3)
    assert a["delta_mix_off_vs_single_copula_sigma_population"] == pytest.approx(0.02, abs=2e-3)
    # the two steps must sum to the total against the incumbent
    assert (a["delta_vs_mix_off_the_split"]
            + a["delta_mix_off_vs_single_copula_sigma_population"]) == pytest.approx(
        a["delta_vs_single_copula_total"], abs=2e-3)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 14. Scope, verdicts and the deploy hold
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_only_the_gate_position_is_gated_and_report_only_wins_cannot_ship():
    out = {"fold_results": _folds()
           + [{"label": f"R{i}", "n_test": 690,
               "positions": _fold_result(f"R{i}", _base_scores(), position="TE")["positions"]}
              for i in range(8)]}
    # merge the TE rows into the QB folds so both positions are usable on the same fold labels
    frs = _folds()
    te = [_fold_result(f"F{i}", _base_scores(), position="TE") for i in range(8)]
    for fr, t in zip(frs, te):
        fr["positions"]["TE"] = t["positions"]["TE"]
    out = {"fold_results": frs}
    R.derive_verdict_layer(out)
    assert set(out["gates"]) == {MX.GATE_POSITION}
    assert "TE" in out["selections"] and out["selections"]["TE"]["gated"] is False
    assert out["verdict"]["report_only_positions"] == ["TE"]
    assert set(out["verdict"]["ship_positions"]) <= {MX.GATE_POSITION}
    assert "E2.1-r" in out["verdict"]["report_only_note"]


def test_the_selection_key_is_declared_on_the_verdict_itself():
    out = {"fold_results": _folds()}
    R.derive_verdict_layer(out)
    key = out["verdict"]["selection_key"]
    assert "crps_q199" in key and "never a ranking key" in key


def test_the_promote_blockers_name_the_deploy_hold_the_report_only_scope_and_NF_W4():
    joined = " ".join(MX.PROMOTE_BLOCKERS)
    assert "DEPLOY-HELD" in joined
    assert "REPORT-ONLY" in joined and "never a ship" in joined
    assert "NF-W4" in joined and "Layer B" in joined


def test_the_story_is_edge_independent_and_names_no_market_source():
    """⚠️ IDENTIFIER-BOUNDARY, NOT SUBSTRING — and NOT negation-blind (NF-W7 / NF-C6P3).

    A raw substring scan for edge language fires on this repo's OWN honest hedge ("never an edge /
    ROI / win-rate claim"), which makes the cheapest way to pass the guard DELETING the sentence
    that keeps the surface honest. So the scan looks for market SOURCE identifiers at token
    boundaries, and the hedge is asserted POSITIVELY instead."""
    import inspect
    import re
    banned = ("spread_line", "total_line", "moneyline", "vegas", "implied_prob", "closing_line")
    for mod in (MX, R):
        src = inspect.getsource(mod)
        for token in banned:
            assert not re.search(rf"\b{token}\b", src), f"{mod.__name__} references `{token}`"
    assert "best_alpha = 0" in inspect.getsource(MX)
    assert "never an edge / ROI / win-rate claim" in inspect.getsource(MX).replace("\n", " ")
