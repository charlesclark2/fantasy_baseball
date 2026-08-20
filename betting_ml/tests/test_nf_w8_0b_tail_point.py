"""NF-W8-0b guards — the tail-completed cross-position ranking point.

Everything here is SYNTHETIC (no lake, no S3, no W6d dispatch): the deterministic transform's
correctness anchors, the swap materiality floor, the verdict mapping, and the runner's derive
layer end-to-end on fabricated fold rows. Fast-gate safe: imports `quant_sports_intel_models` +
`betting_ml` only, mutates no global state at import, touches no network.

⭐ THE LOAD-BEARING GUARD CLASS HERE IS `TestPredecessorDefaultsUnchanged`. This story reaches
into NF-W8-0's DECIDED harness through three new optional hooks (`point_reader`, `bank_detail`,
`swap_floor_ppr`/`floor_ppr`). Each defaults to the predecessor's registered behaviour, and each
default is pinned here — because a successor that silently moved a decided story's numbers would
be indistinguishable from one that did not (E2.1-r).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sps

from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import fp_tail_point as TP
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_w8_0_cross_position as R,
)
from quant_sports_intel_models.football.nfl.fantasy import run_nf_w8_0b_tail_point as R0B

_ROOT = Path(__file__).resolve().parents[2]
_PREREG = _ROOT / TP.PREREGISTRATION_RELPATH
_MODULE = Path(TP.__file__)
_RUNNER = Path(R0B.__file__)

RNG_SEED = 20260819
L = TP.GRID_LEVELS


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Synthetic substrate
# ══════════════════════════════════════════════════════════════════════════════════════════════
_N_PER_POS = {"QB": 15, "RB": 30, "WR": 30, "TE": 15}
_POS_BASE_MEAN = {"QB": 16.0, "RB": 11.0, "WR": 11.5, "TE": 8.0}


def _bank_from(dist, n: int) -> np.ndarray:
    """(n, 199) bank whose every row is `dist`'s quantile function on the eval grid."""
    return np.tile(dist.ppf(L), (n, 1))


def _make_rows(bias: dict[str, float], swap_bias: dict[str, float], *, folds: int = 8,
               weeks: int = 4, seed: int = RNG_SEED) -> dict[str, pd.DataFrame]:
    """Fabricated OOF rows on the TAIL-COMPLETED point (`point_consumed`), with the incumbent
    grid-mean read carried beside it. Base ability varies per player so the points CARRY SIGNAL
    — without it `position_mean_point` would tie the arms and the degenerate clause would be
    decided by the fixture rather than the assertion (the fixture-inertness lesson)."""
    rng = np.random.default_rng(seed)
    base = {p: rng.normal(_POS_BASE_MEAN[p], 6.0, _N_PER_POS[p]) for p in XP.POSITIONS}
    out: dict[str, pd.DataFrame] = {}
    for f in range(1, folds + 1):
        frames = []
        for p in XP.POSITIONS:
            n = _N_PER_POS[p]
            for w in range(1, weeks + 1):
                y = base[p] + rng.normal(0.0, 3.0, n)
                pc = base[p] + bias[p] + rng.normal(0.0, 2.0, n)
                psw = base[p] + swap_bias[p] + rng.normal(0.0, 2.0, n)
                frames.append(pd.DataFrame({
                    "season": 2020 + f, "week": w, "gw": f * 100 + w,
                    "gsis_id": [f"{p}{i:03d}" for i in range(n)], "position": p,
                    "y": y, "point_consumed": pc, "point_swap": psw,
                    "point_consumed_gridmean": pc - 0.3, "point_swap_gridmean": psw - 0.3,
                    "p10": pc - 5.0, "p50": pc, "p90": pc + 5.0,
                }))
        out[f"F{f}"] = pd.concat(frames, ignore_index=True)
    return out


def _fold_results(rows_by_fold: dict[str, pd.DataFrame], tmp: Path) -> list[dict]:
    frs = []
    for label, df in sorted(rows_by_fold.items()):
        path = tmp / f"{label}.parquet"
        df.to_parquet(path, index=False)
        positions = {}
        for p in XP.POSITIONS:
            sel = df["position"] == p
            positions[p] = {
                "scores": {R.CONSUMED_BANK_LABEL[p]: 2.0 + 0.01 * len(label),
                           R.SWAP_BANK_LABEL[p]: 2.1},
                "consumed": R.CONSUMED_BANK_LABEL[p], "swap": R.SWAP_BANK_LABEL[p],
                "n_train": 1000, "n_test": int(sel.sum()),
                "point_reader": "tail_completed_point",
                "bias_identity": XP.bias_detail(df.loc[sel, "point_consumed"].to_numpy(),
                                                df.loc[sel, "y"].to_numpy()),
                "bias_gridmean": XP.bias_detail(
                    df.loc[sel, "point_consumed_gridmean"].to_numpy(),
                    df.loc[sel, "y"].to_numpy()),
                "bias_swap": XP.bias_detail(df.loc[sel, "point_swap"].to_numpy(),
                                            df.loc[sel, "y"].to_numpy()),
                "calibration_slope": XP.calibration_slope(
                    df.loc[sel, "point_consumed"].to_numpy(), df.loc[sel, "y"].to_numpy()),
                "bank_detail": {"consumed": {"mean_delta": 0.3, "mean_gridmean": 10.0,
                                             "mean_hi_tail": 0.04},
                                "swap": {"mean_delta": 0.1, "mean_gridmean": 10.0,
                                         "mean_hi_tail": 0.02}},
            }
        frs.append({"label": label, "n_test": int(len(df)), "positions": positions,
                    "bank_cache": "synthetic", "rows_path": str(path)})
    return frs


def _out_shell(frs: list[dict], tmp: Path) -> dict:
    return {"story": TP.STORY, "smoke": False, "generated_at": "synthetic",
            "gate_league": R.GATE_LEAGUE, "n_folds": len(frs),
            "fold_results": frs, "input_dir": str(tmp / "input")}


@pytest.fixture()
def pins_pass(monkeypatch):
    """Reproduction pins that MATCH the fabricated fold scores — the pass path. The fail path is
    the default (the real records' fold labels never match the synthetic ones — fails closed)."""
    monkeypatch.setattr(R, "_generator_record_scores",
                        lambda position: {f"F{f}": 2.0 + 0.01 * 2 for f in range(1, 9)})


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — the transform's correctness anchors (an ORACLE FLOOR, not a plausibility argument)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestTailCompletedPointIsExactWhereItMustBe:
    """The transform claims to recover E[Y]. Three distributions have a KNOWN E[Y] the
    exponential form reproduces exactly or near-exactly; a transform that misses them is not
    computing the quantity it names. This is the story's oracle floor — nothing may beat it and
    the transform must MEET it."""

    def test_degenerate_bank_returns_its_own_value_exactly(self):
        # ⭐ the correctness anchor for the 199/200 RE-WEIGHTING: without it a degenerate bank at
        # c returns 1.005·c — a multiplicative bias that scales with a position's own LEVEL and
        # would MANUFACTURE a cross-position differential of exactly the kind family A measures.
        for c in (0.0, 7.25, 31.5):
            bank = np.full((4, TP.N_LEVELS), float(c))
            assert np.allclose(TP.tail_completed_point(bank), c, atol=1e-12)

    def test_uniform_quantile_function_is_exact(self):
        bank = np.tile(L, (2, 1))
        assert np.allclose(TP.tail_completed_point(bank), 0.5, atol=1e-12)

    def test_exponential_tail_is_recovered_and_beats_the_truncated_grid_mean(self):
        bank = np.tile(-np.log(1.0 - L), (2, 1))       # Exp(1), E[Y] = 1
        tc = float(TP.tail_completed_point(bank)[0])
        gm = float(XP.bank_point(bank)[0])
        assert abs(tc - 1.0) < abs(gm - 1.0) / 10.0, (tc, gm)

    @pytest.mark.parametrize("dist,true_mean", [
        (sps.gamma(2.0, scale=6.0), 12.0),
        (sps.lognorm(s=1.0), float(np.exp(0.5))),
        (sps.gamma(1.4, scale=8.0), 1.4 * 8.0),
    ])
    def test_right_skewed_shapes_move_strictly_toward_the_truth(self, dist, true_mean):
        bank = _bank_from(dist, 2)
        gm, tc = float(XP.bank_point(bank)[0]), float(TP.tail_completed_point(bank)[0])
        assert abs(tc - true_mean) < abs(gm - true_mean)
        assert gm < true_mean, "the truncated grid mean must UNDER-state a right-skewed mean"

    def test_the_mechanism_a_symmetric_shape_loses_nothing_and_a_skewed_one_loses_a_lot(self):
        """⭐ NF-W8-0 §12.3d's HYPOTHESIS, made mechanical: the truncation bias is a function of
        RIGHT-TAIL HEAVINESS. A symmetric bank loses ~nothing to the truncated grid mean; a
        right-skewed bank of the SAME mean loses an order of magnitude more. That differential
        IS the code-of-origin artifact family A measures — so a guard that could not tell the
        two apart would not be testing this story's claim at all."""
        sym = _bank_from(sps.norm(12.0, 8.0), 1)
        skew = _bank_from(sps.gamma(2.0, scale=6.0), 1)          # also mean 12
        loss_sym = 12.0 - float(XP.bank_point(sym)[0])
        loss_skew = 12.0 - float(XP.bank_point(skew)[0])
        assert abs(loss_sym) < 0.01
        assert loss_skew > 10.0 * max(abs(loss_sym), 1e-6)
        # and the completion removes the differential the truncation created
        assert abs(float(TP.tail_completed_point(skew)[0]) - 12.0) < 0.1 * loss_skew


class TestTransformIsDeterministic:
    """The whole reason this successor exists: NF-W8-0 §12.3a measured a non-stationarity floor
    (0.511 PPR of prior-vs-fold drift against a 0.4888 artifact) that defeats any FITTED
    per-position constant. A transform that reads outcomes re-imports that floor."""

    def test_repeated_calls_are_byte_identical(self):
        bank = _bank_from(sps.gamma(2.0, scale=6.0), 5)
        a, b = TP.tail_completed_point(bank), TP.tail_completed_point(bank)
        assert np.array_equal(a, b)

    def test_the_module_never_calls_a_tail_ESTIMATOR(self):
        """⛔ `MC.fit_tail_betas` (mean excess on realized `y`) and `M3.fit_eq_tail` (empirical
        exceedance quantiles) are FITTERS. Either would make the point outcome-dependent, and
        NF-MARGIN2 additionally measured the fitted exponential UNDER-extending at QB/WR — i.e.
        the estimator is known-biased-low at exactly the position under test."""
        src = _MODULE.read_text()
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        for fitter in ("fit_tail_betas", "fit_eq_tail", "fit_form", "fit_level_widen"):
            assert f"{fitter}(" not in code, f"{fitter} is an ESTIMATOR — the point must not fit"

    def test_the_transform_signature_takes_no_outcomes(self):
        import inspect
        for fn in (TP.tail_completed_point, TP.tail_scales, TP.tail_contributions):
            params = set(inspect.signature(fn).parameters)
            assert not params & {"y", "outcomes", "realized", "target"}, fn.__name__

    def test_a_partly_absent_bank_is_refused_never_nan_meaned(self):
        bank = _bank_from(sps.gamma(2.0, scale=6.0), 3)
        bank[1, 100] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            TP.tail_completed_point(bank)

    def test_an_off_grid_anchor_is_refused_never_snapped(self):
        bank = _bank_from(sps.gamma(2.0, scale=6.0), 2)
        with pytest.raises(ValueError, match="not an exact member"):
            TP.tail_completed_point(bank, inner_hi=0.9765)

    def test_scales_are_non_negative_so_the_extension_is_monotone(self):
        rng = np.random.default_rng(RNG_SEED)
        bank = np.sort(rng.normal(10, 5, (50, TP.N_LEVELS)), axis=1)
        sc = TP.tail_scales(bank)
        assert float(sc["beta_hi"].min()) >= 0.0 and float(sc["beta_lo"].min()) >= 0.0

    def test_an_unsorted_bank_is_sorted_defensively_not_mis_read(self):
        bank = _bank_from(sps.gamma(2.0, scale=6.0), 1)
        shuffled = bank[:, np.random.default_rng(1).permutation(TP.N_LEVELS)]
        assert np.allclose(TP.tail_completed_point(shuffled), TP.tail_completed_point(bank))


class TestAnchorChoiceIsDeclaredAndBounded:
    def test_registered_anchors_are_inherited_design_constants(self):
        from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
        assert TP.ANCHOR_INNER_HI == float(WP.Q_LEVELS[-1])      # the SERVED 39-grid end
        assert TP.ANCHOR_OUTER_HI == float(TP.GRID_LEVELS[-1])   # the eval grid end
        assert TP.ANCHOR_INNER_LO == float(WP.Q_LEVELS[0])
        assert TP.ANCHOR_OUTER_LO == float(TP.GRID_LEVELS[0])

    def test_sensitivity_is_reported_and_the_registered_anchor_is_named(self):
        bank = _bank_from(sps.gamma(2.0, scale=6.0), 3)
        sens = TP.anchor_sensitivity(bank)
        assert sens["registered"] == f"inner_hi={TP.ANCHOR_INNER_HI}"
        assert len(sens) == len(TP.ANCHOR_SENSITIVITY_INNER_HI) + 1

    def test_the_completion_reports_magnitudes_not_only_shares(self):
        """NF-W7f: a binding/active SHARE is invariant to the magnitude it binds at, so a share
        alone can report 'nothing changed' about a mechanism that stopped mattering."""
        d = TP.completion_detail(_bank_from(sps.gamma(2.0, scale=6.0), 4))
        for k in ("mean_delta", "mean_hi_tail", "mean_lo_tail", "mean_beta_hi"):
            assert isinstance(d[k], float)
        for k in ("flat_hi_share", "flat_lo_share"):
            assert 0.0 <= d[k] <= 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §2 — the swap materiality floor (NF-W8-0 §12.5(2), registered forward)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestMaterialityFloor:
    _FA = {"pairs": {"QB|RB": {"mde_ppr": 0.3277}, "QB|WR": {"mde_ppr": 0.202},
                     "QB|TE": {"mde_ppr": 0.1889}, "RB|WR": {"mde_ppr": 0.2538},
                     "RB|TE": {"mde_ppr": 0.1732}, "WR|TE": {"mde_ppr": 0.1839}}}

    def test_floor_is_the_registered_summary_of_family_a_own_mdes(self):
        fl = TP.materiality_floor(self._FA)
        assert fl["statistic"] == TP.SWAP_FLOOR_STATISTIC
        assert fl["floor_ppr"] == pytest.approx(0.1955, abs=1e-6)
        assert fl["sensitivity_band"] == {"min": 0.1732, "median": 0.1955, "max": 0.3277}

    def test_an_unregistered_summary_statistic_is_refused(self):
        with pytest.raises(ValueError, match="unregistered floor statistic"):
            TP.materiality_floor(self._FA, statistic="max")

    def test_an_unformable_floor_is_none_never_zero(self):
        """NF1.7 (a): a floor that could not be FORMED must not silently become floor-0, which
        would restore the predecessor's no-floor rule under this story's name."""
        fl = TP.materiality_floor({"pairs": {}})
        assert fl["floor_ppr"] is None and "UNEVALUABLE" in fl["note"]

    def test_a_precise_but_immaterial_shift_is_inactive(self):
        """NF-W8-0 §12.3c: WR/TE shifts of 0.037/0.095 PPR were PRECISELY estimated (2×SE) and
        an order of magnitude below family A's own detection floor — the clause refused the
        story's winner on them. Under the registered floor they are UNINFORMATIVE, not a fail."""
        shifts = np.array([0.037, 0.038, 0.036, 0.037, 0.039, 0.035, 0.037])
        assert XP.swap_activity(shifts)["active"] is True          # precise under W8-0's rule
        act = XP.swap_activity(shifts, floor_ppr=0.1955)
        assert act["active"] is False and act["precise"] is True and act["material"] is False

    def test_a_material_shift_stays_active(self):
        shifts = np.array([-0.37, -0.36, -0.38, -0.37, -0.39, -0.35, -0.37])
        assert XP.swap_activity(shifts, floor_ppr=0.1955)["active"] is True

    def test_a_material_but_IMPRECISE_shift_stays_inactive(self):
        """⭐ The floor is an AND, so it may never RESCUE a shift the precision rule rejects.
        This needs a fixture where the two rules DISAGREE — a large mean with a large SE. The
        low-noise fixtures below cannot produce it, so without this case the monotonicity guard
        passes on nothing (found by the RED proof, not by a green suite)."""
        shifts = np.array([2.0, -1.6, 1.9, -1.5, 2.1, -1.4, 0.9])       # mean 0.34, SE ~0.63
        assert XP.swap_activity(shifts)["active"] is False, "fixture must be IMPRECISE"
        act = XP.swap_activity(shifts, floor_ppr=0.1955)
        assert act["material"] is True, "fixture must be MATERIAL (|mean| above the floor)"
        assert act["active"] is False, "the floor must not rescue an imprecise shift"

    @pytest.mark.parametrize("mean_shift", [0.0, 0.02, 0.05, 0.1, 0.19, 0.2, 0.4, 1.0])
    def test_the_floor_can_only_REMOVE_activity_never_add_it(self, mean_shift):
        """The floor is an AND with the precision rule, so it is monotone: a position inactive
        under NF-W8-0 can never become active under NF-W8-0b. Anything else would be a NEW way
        to refuse, not a materiality filter."""
        rng = np.random.default_rng(7)
        shifts = mean_shift + rng.normal(0, 0.01, 7)
        old = XP.swap_activity(shifts)["active"]
        new = XP.swap_activity(shifts, floor_ppr=0.1955)["active"]
        assert not (new and not old)

    def test_the_floor_reaches_the_clause_not_only_the_activity_helper(self):
        before = {p: np.full(7, 0.05) + np.random.default_rng(3).normal(0, 0.005, 7)
                  for p in XP.POSITIONS}
        after = {p: v * 0.9 for p, v in before.items()}
        assert XP.swap_clause(before, after)["state"] != XP.SWAP_INACTIVE_EVERYWHERE
        floored = XP.swap_clause(before, after, floor_ppr=0.1955)
        assert floored["state"] == XP.SWAP_INACTIVE_EVERYWHERE
        assert floored["passes"] is None, "INACTIVE_EVERYWHERE neither passes nor refuses"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §3 — ⭐ the predecessor's DECIDED behaviour is untouched at every default
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestPredecessorDefaultsUnchanged:
    """Three hooks were added to NF-W8-0's decided harness. Each default must reproduce the
    predecessor's registered behaviour EXACTLY — a successor that silently moved a decided
    story's numbers would be indistinguishable from one that did not (E2.1-r)."""

    def test_swap_activity_default_is_the_no_floor_rule(self):
        shifts = np.array([0.037, 0.038, 0.036, 0.037, 0.039, 0.035, 0.037])
        d = XP.swap_activity(shifts)
        assert d["active"] is True
        assert "materiality_floor_ppr" not in d, "the default must not even mention a floor"
        assert XP.swap_activity(shifts, floor_ppr=None) == d

    def test_swap_clause_default_matches_the_explicit_none(self):
        before = {p: np.full(7, 0.4) + np.random.default_rng(5).normal(0, 0.01, 7)
                  for p in XP.POSITIONS}
        after = {p: v * 0.1 for p, v in before.items()}
        assert XP.swap_clause(before, after) == XP.swap_clause(before, after, floor_ppr=None)

    def test_run_position_default_reader_is_the_truncated_grid_mean(self):
        import inspect
        sig = inspect.signature(R.run_position).parameters
        assert sig["point_reader"].default is None
        assert sig["bank_detail"].default is None
        src = inspect.getsource(R.run_position)
        assert "read = XP.bank_point if point_reader is None else point_reader" in src

    def test_derive_verdict_layer_default_floor_is_none(self):
        import inspect
        assert inspect.signature(R.derive_verdict_layer).parameters[
            "swap_floor_ppr"].default is None

    def test_the_gridmean_columns_are_only_emitted_under_a_reader(self):
        """The disclosure columns must not appear in the predecessor's own rows schema."""
        import inspect
        src = inspect.getsource(R.run_position)
        assert 'if point_reader is not None:' in src
        i_guard = src.index("if point_reader is not None:")
        assert src.index('rows["point_consumed_gridmean"]') > i_guard


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §4 — the verdict rule + the two cross_rankable readings
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _pv(state, **kw):
    return {"state": state, "gap_detected": kw.get("gap", True),
            "max_mde_ppr": kw.get("mde", 0.2), "winner": kw.get("winner")}


class TestTailPointVerdict:
    def test_no_gap_closes_and_is_cross_rankable_with_no_layer(self):
        v = TP.tail_point_verdict(predecessor_verdict=_pv(XP.V_COMPARABLE, gap=False),
                                  swap_state=None, winner_clauses=None)
        assert v["state"] == TP.V_CLOSES
        assert v["cross_rankable"] is True and v["cross_rankable_with_layer"] is True
        # ⛔ assert the VALUE, not the word: "MDE" also appears in the sentence that follows,
        # so a reason that dropped the number entirely still contained the token (RED-proof find)
        assert "0.2" in v["reason"], "a null must state its MDE in PPR, not merely name one"

    def test_a_layer_repaired_gap_is_NOT_the_deterministic_claim(self):
        """⭐ the AC's single definition: `cross_rankable` is the DETERMINISTIC reading. A gap
        closed only by a fitted layer re-imports NF-W8-0 §12.3a's non-stationarity floor, which
        is precisely what this story exists to step around."""
        v = TP.tail_point_verdict(predecessor_verdict=_pv(XP.V_REMOVED, winner="level_add"),
                                  swap_state="PASS", winner_clauses={"reduces_gap": True})
        assert v["state"] == TP.V_REMOVED
        assert v["cross_rankable"] is False
        assert v["cross_rankable_with_layer"] is True

    def test_a_persisting_gap_is_not_cross_rankable_either_way(self):
        v = TP.tail_point_verdict(predecessor_verdict=_pv(XP.V_UNREPAIRED, winner="level_affine"),
                                  swap_state="FAIL", winner_clauses={"reduces_gap": False})
        assert v["state"] == TP.V_PERSISTS
        assert v["cross_rankable"] is False and v["cross_rankable_with_layer"] is False

    @pytest.mark.parametrize("base,gap", [(XP.V_UNDEFINED, True), (XP.V_COMPARABLE, None)])
    def test_an_unevaluable_harness_is_undefined_never_cross_rankable(self, base, gap):
        v = TP.tail_point_verdict(predecessor_verdict=_pv(base, gap=gap), swap_state=None,
                                  winner_clauses=None)
        assert v["state"] == TP.V_UNDEFINED and v["cross_rankable"] is False

    def test_the_qb_option_b_caveat_and_second_reader_travel_on_every_verdict(self):
        for base in (XP.V_COMPARABLE, XP.V_REMOVED, XP.V_UNREPAIRED, XP.V_UNDEFINED):
            v = TP.tail_point_verdict(predecessor_verdict=_pv(base, gap=base != XP.V_COMPARABLE),
                                      swap_state=None, winner_clauses=None)
            assert v["qb_consumption"] == XP.QB_CONSUMPTION
            assert v["second_reader"]["status"].startswith("OPEN")

    def test_promote_blockers_inherit_the_predecessors_in_full(self):
        for b in XP.PROMOTE_BLOCKERS:
            assert b in TP.PROMOTE_BLOCKERS
        assert len(TP.PROMOTE_BLOCKERS) > len(XP.PROMOTE_BLOCKERS)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §5 — the derive layer end-to-end on the tail-completed point
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDerive0bEndToEnd:
    def test_a_closed_gap_ships_identity_and_emits_cross_rankable(self, tmp_path, pins_pass):
        flat = {p: 0.05 for p in XP.POSITIONS}
        rows = _make_rows(flat, {p: 0.05 for p in XP.POSITIONS})
        out = R0B.derive_0b(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert out["verdict_0b"]["state"] == TP.V_CLOSES
        assert out["cross_rankable"] is True
        assert out["input"]["shipped_arm"] == XP.INCUMBENT
        assert out["input"]["cross_rankable"] is True
        assert out["input"]["banks_untouched"] is True

    def test_a_surviving_gap_is_not_cross_rankable(self, tmp_path, pins_pass):
        bias = {"QB": -1.2, "RB": -0.2, "WR": 0.0, "TE": 0.0}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(bias, bias), tmp_path), tmp_path))
        assert out["family_a"]["gap_detected"] is True
        assert out["cross_rankable"] is False
        assert out["verdict_0b"]["state"] in (TP.V_REMOVED, TP.V_PERSISTS)

    def test_a_failed_reproduction_is_undefined_never_a_pass(self, tmp_path):
        # no `pins_pass` ⇒ the real records' fold labels never match the synthetic ones
        flat = {p: 0.05 for p in XP.POSITIONS}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(flat, flat), tmp_path), tmp_path))
        assert out["verdict_0b"]["state"] == TP.V_UNDEFINED
        assert out["cross_rankable"] is False

    def test_the_materiality_floor_is_recorded_with_its_sensitivity_band(self, tmp_path,
                                                                        pins_pass):
        flat = {p: 0.05 for p in XP.POSITIONS}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(flat, flat), tmp_path), tmp_path))
        fl = out["materiality_floor"]
        assert fl["floor_ppr"] is not None and fl["statistic"] == TP.SWAP_FLOOR_STATISTIC
        assert set(fl["sensitivity_band"]) == {"min", "median", "max"}
        assert out["swap_verification"]["materiality_floor_ppr"] == fl["floor_ppr"]
        # ⭐ REPORTED ≠ APPLIED: the key above is stamped on the record independently of whether
        # the floor reached `XP.swap_activity`. The floor's OWN keys (`material`/
        # `materiality_floor_ppr` inside `activity`) exist ONLY when it was actually passed in,
        # so they are what proves application (E11.24 'writing the caveat is not applying it').
        acts = [d["activity"] for d in out["swap_verification"]["detail"].values()
                if d["activity"].get("active") is not None]
        assert acts, "no evaluable position — the clause guard would pass on nothing"
        for act in acts:
            assert "materiality_floor_ppr" in act and "material" in act, \
                "the floor never reached swap_activity — reported but not applied"

    def test_both_reads_of_the_same_banks_are_recorded(self, tmp_path, pins_pass):
        """The record must carry the incumbent grid-mean bias BESIDE the tail-completed one —
        a successor that reported only its own read would make the comparison unauditable."""
        flat = {p: 0.05 for p in XP.POSITIONS}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(flat, flat), tmp_path), tmp_path))
        assert set(out["gridmean_bias_by_position"]) == set(XP.POSITIONS)
        assert set(out["tail_completion_by_position"]) == set(XP.POSITIONS)
        for pos in XP.POSITIONS:
            assert out["tail_completion_by_position"][pos]["mean_completion_delta_ppr"] is not None

    def test_an_unformable_floor_raises_rather_than_silently_dropping_the_rule(self, tmp_path,
                                                                              monkeypatch):
        monkeypatch.setattr(TP, "materiality_floor",
                            lambda fa, **k: {"floor_ppr": None, "note": "synthetic: no pairs"})
        flat = {p: 0.05 for p in XP.POSITIONS}
        with pytest.raises(ValueError, match="could not be formed"):
            R0B.derive_0b(_out_shell(_fold_results(_make_rows(flat, flat), tmp_path), tmp_path))

    def test_family_a_disagreement_between_the_floor_read_and_the_record_is_refused(self):
        pre = {"pairs": {"QB|WR": {"gap": -0.3, "se": 0.07, "mde_ppr": 0.2}}}
        bad = {"pairs": {"QB|WR": {"gap": -0.1, "se": 0.07, "mde_ppr": 0.2}}}
        R0B._assert_family_a_agrees(pre, pre)                      # non-vacuity: agreement passes
        with pytest.raises(ValueError, match="one field, one rule set"):
            R0B._assert_family_a_agrees(pre, bad)

    def test_the_smoke_path_proof_makes_the_clause_UNEVALUABLE_not_the_predecessors_rule(
            self, tmp_path, monkeypatch):
        """⭐ The `--smoke` path proof runs ONE fold, so every family-A pair has a single
        observation, every MDE is None, and the floor cannot be FORMED. The run is UNDEFINED by
        construction and reaches no verdict, so it must not RAISE (that would defeat the path
        proof) — but it must also NOT fall back to floor-0 / None, either of which restores the
        predecessor's no-floor rule under this story's name. The registered resolution is an
        INFINITE floor ⇒ INACTIVE_EVERYWHERE ⇒ the clause neither passes nor refuses."""
        monkeypatch.setattr(R, "_generator_record_scores", lambda position: {"F1": 2.02})
        flat = {p: 0.05 for p in XP.POSITIONS}
        rows = _make_rows(flat, flat, folds=1)          # ⭐ ONE fold — the real `--smoke` shape
        out = R0B.derive_0b(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert out["family_a"]["gap_detected"] is None, "1 fold ⇒ family A cannot evaluate"
        assert out["verdict_0b"]["state"] == TP.V_UNDEFINED
        assert out["cross_rankable"] is False
        fl = out["materiality_floor"]
        assert fl["unformable_on_a_path_proof"] is True
        assert fl["floor_ppr"] == float("inf"), \
            "⛔ never 0 and never None — either IS the predecessor's no-floor rule"

    def test_an_infinite_floor_deactivates_every_position(self):
        """The property the path-proof fallback relies on: an infinite floor cannot let any
        position be ACTIVE, so the clause is UNEVALUABLE rather than silently permissive."""
        before = {p: np.full(7, 5.0) + np.random.default_rng(11).normal(0, 0.01, 7)
                  for p in XP.POSITIONS}
        after = {p: v * 0.1 for p, v in before.items()}
        assert XP.swap_clause(before, after)["state"] == "PASS"      # non-vacuity: it CAN pass
        inf_floored = XP.swap_clause(before, after, floor_ppr=float("inf"))
        assert inf_floored["state"] == XP.SWAP_INACTIVE_EVERYWHERE
        assert inf_floored["passes"] is None

    def test_an_unformable_floor_on_a_run_that_WOULD_reach_a_verdict_still_raises(
            self, tmp_path, pins_pass, monkeypatch):
        """The path-proof relaxation above must not reach a run that can actually decide."""
        monkeypatch.setattr(TP, "materiality_floor",
                            lambda fa, **k: {"floor_ppr": None, "note": "synthetic: no pairs"})
        flat = {p: 0.05 for p in XP.POSITIONS}
        with pytest.raises(ValueError, match="could not be formed"):
            R0B.derive_0b(_out_shell(_fold_results(_make_rows(flat, flat), tmp_path), tmp_path))

    def test_the_family_a_agreement_check_is_actually_INVOKED_by_the_derivation(
            self, tmp_path, pins_pass, monkeypatch):
        """NF-C0e (wired ≠ invoked): testing `_assert_family_a_agrees` directly proves the
        function works, NOT that the derivation calls it. Deleting the call site left the
        direct test green (RED-proof find), so the wiring needs its own guard."""
        real = R0B.family_a_on_stored_rows

        def divergent(rows_by_fold):
            fa = real(rows_by_fold)
            for d in fa["pairs"].values():
                if d.get("gap") is not None:
                    d["gap"] = float(d["gap"]) + 99.0
                    break
            return fa

        monkeypatch.setattr(R0B, "family_a_on_stored_rows", divergent)
        flat = {p: 0.05 for p in XP.POSITIONS}
        with pytest.raises(ValueError, match="one field, one rule set"):
            R0B.derive_0b(_out_shell(_fold_results(_make_rows(flat, flat), tmp_path), tmp_path))

    @pytest.mark.parametrize("bias,label", [
        ({"QB": 0.05, "RB": 0.05, "WR": 0.05, "TE": 0.05}, "closed"),
        ({"QB": -1.2, "RB": -0.2, "WR": 0.0, "TE": 0.0}, "persisting"),
    ])
    def test_the_report_renders_on_every_verdict_it_can_reach(self, tmp_path, pins_pass,
                                                             bias, label):
        """⛔ A report renderer that raises would waste the operator's ~50-minute decisive run
        AFTER every fold had been scored — the record is written last. So the renderer is
        exercised on each verdict shape, not just the happy one."""
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(bias, bias), tmp_path), tmp_path))
        path = tmp_path / f"report_{label}.md"
        R0B.write_report(out, path)
        txt = path.read_text()
        assert out["verdict_0b"]["state"] in txt
        assert "cross_rankable" in txt and "Reproduction pins" in txt
        assert str(out["materiality_floor"]["floor_ppr"]) in txt
        for pos in XP.POSITIONS:                     # both reads of the same banks, per position
            assert f"| {pos} |" in txt

    def test_a_rendered_retest_trigger_is_always_scoped_to_the_family_it_describes(
            self, tmp_path, pins_pass):
        """⛔ NF-D18: `classify_null`'s trigger describes FAMILY B (the fitted contest). Family A's
        null is arithmetically bounded, not underpowered. A record that prints `+2 folds` with no
        scoping invites a reader to apply it to family A — so the renderer must carry the warning
        wherever it carries the number."""
        bias = {"QB": -1.2, "RB": -0.2, "WR": 0.0, "TE": 0.0}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(bias, bias), tmp_path), tmp_path))
        # ⛔ INJECT the trigger rather than hoping a synthetic field reaches one — a guard that
        # SKIPS when the branch is unreached proves nothing (it is the vacuous-guard class in a
        # skip's clothing, and this test skipped on first write).
        out["classification"] = dict(out.get("classification") or {}) | {
            "state": "POWER_LIMITED", "retest_trigger": "+2 folds for the DSR gate"}
        path = tmp_path / "scoped.md"
        R0B.write_report(out, path)
        txt = path.read_text()
        assert "+2 folds for the DSR gate" in txt, "non-vacuity: the trigger must be rendered"
        assert "FAMILY B ONLY" in txt, "a trigger was rendered with no family scoping"
        assert "ARITHMETICALLY BOUNDED" in txt

        # and the negative half: no trigger ⇒ no warning (the note must not be unconditional
        # boilerplate, or it would read as scoping a trigger that isn't there)
        out["classification"] = {"state": "CONSTRAINT_REFUSED", "retest_trigger": None}
        path2 = tmp_path / "unscoped.md"
        R0B.write_report(out, path2)
        assert "FAMILY B ONLY" not in path2.read_text()

    def test_the_report_carries_the_bound_in_the_row_pooled_convention(self, tmp_path, pins_pass):
        flat = {p: 0.05 for p in XP.POSITIONS}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(flat, flat), tmp_path), tmp_path))
        path = tmp_path / "bound.md"
        R0B.write_report(out, path)
        txt = path.read_text()
        assert "ROW-POOLED completion deltas" in txt and "MEAN OF FOLD MEANS" in txt
        assert str(out["completion_delta_pooled_spread"]) in txt

    def test_the_report_renders_on_an_UNDEFINED_path_proof(self, tmp_path, monkeypatch):
        monkeypatch.setattr(R, "_generator_record_scores", lambda position: {"F1": 2.02})
        flat = {p: 0.05 for p in XP.POSITIONS}
        out = R0B.derive_0b(_out_shell(
            _fold_results(_make_rows(flat, flat, folds=1), tmp_path), tmp_path))
        path = tmp_path / "report_undefined.md"
        R0B.write_report(out, path)
        assert TP.V_UNDEFINED in path.read_text()

    def test_the_written_input_carries_the_certified_quantiles_byte_identically(self, tmp_path,
                                                                                pins_pass):
        """`banks_untouched`: this story changes only how a POINT is READ. A writer that shifted
        a quantile (the NF-TR2 `apply_to_band` mistake) must demote the ship."""
        flat = {p: 0.05 for p in XP.POSITIONS}
        rows = _make_rows(flat, flat)
        out = R0B.derive_0b(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert out["input"]["max_quantile_drift"] == 0.0
        written = pd.read_parquet(Path(out["input"]["dir"]) / "F1.parquet")
        src = rows["F1"]
        m = written.merge(src[["gsis_id", "gw", "p10", "p50", "p90"]],
                          on=["gsis_id", "gw"], suffixes=("_w", "_s"))
        assert len(m) == len(src)
        for q in ("p10", "p50", "p90"):
            assert np.array_equal(m[f"{q}_w"].to_numpy(), m[f"{q}_s"].to_numpy())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §6 — registration + artifact hygiene
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestRegistrationAndArtifactHygiene:
    def test_the_preregistration_file_exists_and_carries_the_registration(self):
        assert _PREREG.exists(), f"the forward registration is missing at {_PREREG}"
        txt = _PREREG.read_text()
        for token in ("NF-W8-0b", TP.SWAP_FLOOR_STATISTIC, TP.TAIL_FORM,
                      "cross_rankable", "best_alpha", "DEPLOY-HELD"):
            assert token in txt, f"the prereg does not register {token!r}"

    def test_the_runner_refuses_to_write_the_predecessors_decided_paths(self):
        """The NCAAF-P2.1 S1-serve lesson: a successor writing a DECIDED story's output paths
        destroys its audit trail with no error and no test failure."""
        src = _RUNNER.read_text()
        assert "_PREDECESSOR_PATHS" in src and "raise RuntimeError" in src
        for dec in R0B._PREDECESSOR_PATHS:
            assert not R0B._ARTIFACT_REL.endswith(f"{dec}.json")
            assert Path(R0B._ROWS_DIR).name != dec and Path(R0B._INPUT_DIR).name != dec

    def test_pin_scores_are_stored_at_full_precision(self):
        """⛔ the NF-W8-0 smoke bug, re-armed: a `round(…, 6)` on a stored per-fold score CAPS
        every reproduction pin at ~5e-7 against a 1e-9 tolerance, so the decisive run returns
        UNDEFINED at all four positions while reproducing perfectly."""
        import inspect
        src = inspect.getsource(R.run_position)
        block = src[src.index('"scores"'):src.index('"consumed"')]
        assert "round(" not in block, "a rounded score CAPS the 1e-9 reproduction pin"
        assert XP.REPRODUCTION_TOLERANCE <= 1e-9

    def test_the_0b_runner_stores_no_rounded_point(self):
        src = _RUNNER.read_text()
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        assert "round(TP.tail_completed_point" not in code
        assert "point_reader=TP.tail_completed_point" in code

    def test_the_runner_drives_the_shared_harness_rather_than_forking_it(self):
        """One code path for the generators (NF-W7d) and one rule set for the statistics
        (E9.61): the 0b runner must REUSE W80's fold + derive layer, not re-implement them."""
        src = _RUNNER.read_text()
        assert "W80.run_fold(" in src and "W80.derive_verdict_layer(" in src
        for forked in ("def run_fold(", "def run_position(", "def build_position_banks("):
            assert forked not in src, f"{forked} is forked — the generators must have ONE path"

    def test_the_story_is_deploy_held_and_edge_independent(self):
        """⚠️ The banned tokens are matched as real IMPORT/ARGUMENT FORMS, not bare words: a
        substring scan for `boto3` is satisfied by this runner's own docstring promising 'no
        boto3', so the guard would fail on the honest prose and the cheapest way to pass it
        would be to DELETE the promise (the INC-38 prose-cannot-satisfy class, inverted)."""
        for p in (_MODULE, _RUNNER):
            txt = p.read_text()
            assert "best_alpha" in txt and "DEPLOY-HELD" in txt
        src = _RUNNER.read_text()
        for banned in ("import boto3", "boto3.client(", "import dagster", '"--publish"',
                       "'--publish'"):
            assert banned not in src, f"{banned} in a deploy-held research runner"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §7 — the COMMITTED decisive record (NF-W8-0 §12.4's record-accuracy defect class)
# ══════════════════════════════════════════════════════════════════════════════════════════════
_RECORD = (_ROOT / "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
           "nf_w8_0b_tail_point.json")


@pytest.mark.skipif(not _RECORD.exists(), reason="the decisive record is not committed here")
class TestCommittedRecordConsistency:
    """Assertions on the RECORD as committed. NF-W8-0 §12.4 shipped a record whose classification
    listed a clause as failing while its final value was True — a record-accuracy defect that no
    code test could see, because the defect lived in the artifact."""

    @pytest.fixture(scope="class")
    def rec(self):
        import json
        return json.loads(_RECORD.read_text())

    def test_it_is_the_decisive_run_not_a_path_proof(self, rec):
        assert rec["smoke"] is False and rec["n_folds"] >= 4
        assert rec["story"] == TP.STORY

    def test_cross_rankable_has_exactly_one_definition(self, rec):
        assert rec["cross_rankable"] is (rec["verdict_0b"]["state"] == TP.V_CLOSES)
        assert rec["input"]["cross_rankable"] == rec["cross_rankable"]
        assert rec["verdict_0b"]["state"] in TP.VERDICT_STATES

    def test_a_verdict_was_only_reached_because_every_pin_reproduced(self, rec):
        """A verdict other than UNDEFINED asserts the generators ARE their certified records."""
        if rec["verdict_0b"]["state"] != TP.V_UNDEFINED:
            for pos, r in rec["reproduction"].items():
                assert r["reproduces"] is True, f"{pos} did not reproduce yet a verdict was read"
                assert r["max_abs_gap"] <= XP.REPRODUCTION_TOLERANCE

    def test_the_certified_banks_passed_through_untouched(self, rec):
        assert rec["input"]["banks_untouched"] is True
        assert rec["input"]["max_quantile_drift"] == 0.0

    def test_the_materiality_floor_reached_the_clause(self, rec):
        fl = rec["materiality_floor"]
        assert fl["statistic"] == TP.SWAP_FLOOR_STATISTIC
        acts = [d["activity"] for d in (rec.get("swap_verification") or {}).get("detail", {}).values()
                if d["activity"].get("active") is not None]
        assert acts, "no evaluable position — this guard would pass on nothing"
        for a in acts:
            assert "material" in a and "materiality_floor_ppr" in a

    def test_no_clause_listed_as_failing_is_finally_true(self, rec):
        """NF-W8-0 §12.4 verbatim: the failing lists must describe the FINAL clause values."""
        c = rec.get("classification") or {}
        clauses = rec["recal"]["winner_clauses"]
        for key in ("failing_anchor_checks", "failing_statistical_checks"):
            for name in c.get(key) or []:
                assert clauses.get(name) is not True, f"{name} listed failing but is finally True"

    def test_a_published_retest_trigger_rests_only_on_statistical_clauses(self, rec):
        """⭐ NF-D18: a trigger beside an ANCHOR/constraint refusal is actively misleading — more
        data makes such a refusal MORE certain, never less."""
        c = rec.get("classification") or {}
        if c.get("retest_trigger"):
            clauses = rec["recal"]["winner_clauses"]
            failing_anchors = [n for n in XP.ANCHOR_CLAUSES if clauses.get(n) is False]
            assert not failing_anchors, (
                f"a retest trigger is published while anchor clauses {failing_anchors} fail")

    def test_the_committed_report_scopes_its_published_trigger(self, rec):
        """The .md is the human-facing artifact; the scoping must be IN it, not only in the
        preregistration a reader may never open."""
        md = _RECORD.with_suffix(".md")
        assert md.exists()
        txt = md.read_text()
        trig = (rec.get("classification") or {}).get("retest_trigger")
        if trig:
            assert "FAMILY B ONLY" in txt and "ARITHMETICALLY BOUNDED" in txt
        assert "ROW-POOLED completion deltas" in txt, "the bound must be stated in the record"

    def test_the_family_a_family_is_the_six_declared_pairs(self, rec):
        assert len(rec["family_a"]["pairs"]) == 6
        assert rec["family_a"]["bh_q"] == XP.BH_Q
        for d in rec["family_a"]["pairs"].values():
            assert d["mde_ppr"] is not None, "a null must state its MDE (MH2.6)"

    def test_the_record_carries_BOTH_reads_of_the_same_banks(self, rec):
        assert set(rec["gridmean_bias_by_position"]) == set(XP.POSITIONS)
        assert set(rec["tail_completion_by_position"]) == set(XP.POSITIONS)

    def test_the_deterministic_bound_the_headline_rests_on(self, rec):
        """⭐ §12.1's identity: a pair's movement is EXACTLY the difference of its two positions'
        ROW-POOLED completion deltas, so the whole mechanism is bounded by their spread.

        ⚠️ The convention is load-bearing and is why this guard exists. Stated from
        `tail_completion_by_position` — a MEAN OF FOLD MEANS — the identity is only approximate
        and the implied bound (0.0167) is WRONG: RB|WR moves 0.0193. Pooled over rows it is exact
        to 1e-17 (NF1.8: pool over rows, never a mean of fold means)."""
        assert set(rec["completion_delta_pooled"]) == set(XP.POSITIONS)
        gm = rec["gridmean_bias_by_position"]
        tc = {p: rec["identity_bias"]["pooled"][p]["bias_pooled"] for p in XP.POSITIONS}
        # the deltas at FULL precision — the record stores them rounded to 6dp, which is coarser
        # than the identity itself (the residual is ~1e-17, the rounding ~4e-7)
        exact = {p: tc[p] - gm[p] for p in XP.POSITIONS}
        spread = max(exact.values()) - min(exact.values())
        for p in XP.POSITIONS:                      # the STORED value must be that, rounded
            assert rec["completion_delta_pooled"][p] == pytest.approx(exact[p], abs=1e-6)
        assert rec["completion_delta_pooled_spread"] == pytest.approx(spread, abs=1e-6)
        worst = 0.0
        for a in XP.POSITIONS:
            for b in XP.POSITIONS:
                if a >= b:
                    continue
                moved = (tc[a] - tc[b]) - (gm[a] - gm[b])
                # ⭐ the identity, exact — not an approximation with slack
                assert moved == pytest.approx(exact[a] - exact[b], abs=1e-12), f"{a}|{b}"
                worst = max(worst, abs(moved))
        assert worst <= spread + 1e-12, "no pair may move more than the spread — that IS the bound"

    def test_the_two_pooling_conventions_are_reported_and_differ(self, rec):
        """Both conventions are in the record BECAUSE they differ enough to change a headline —
        a reader must not pick up the fold-mean figure and state the bound from it."""
        pooled = rec["completion_delta_pooled"]
        fold_mean = {p: rec["tail_completion_by_position"][p]["mean_completion_delta_ppr"]
                     for p in XP.POSITIONS}
        assert pooled != fold_mean
        sp_p = max(pooled.values()) - min(pooled.values())
        sp_f = max(fold_mean.values()) - min(fold_mean.values())
        assert abs(sp_p - sp_f) > 1e-4, "if the conventions agreed this guard would be vacuous"
