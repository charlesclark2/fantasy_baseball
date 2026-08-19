"""NF-W8-0 guards — the cross-position comparability layer + the QB consumption registration.

Everything here is SYNTHETIC (no lake, no S3, no W6d dispatch): the pure module's estimators and
verdict rule, the runner's derive layer end-to-end on fabricated fold rows, and the registration
pins. Fast-gate safe: imports `quant_sports_intel_models` + `betting_ml` only, mutates no global
state at import, touches no network.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import fp_cross_position as XP
from quant_sports_intel_models.football.nfl.fantasy import (
    run_nf_w8_0_cross_position as R,
)

_ROOT = Path(__file__).resolve().parents[2]
_PREREG = _ROOT / XP.PREREGISTRATION_RELPATH

RNG_SEED = 20260819


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Synthetic substrate
# ══════════════════════════════════════════════════════════════════════════════════════════════
_N_PER_POS = {"QB": 15, "RB": 30, "WR": 30, "TE": 15}
_POS_BASE_MEAN = {"QB": 16.0, "RB": 11.0, "WR": 11.5, "TE": 8.0}


def _make_rows(bias: dict[str, float], swap_bias: dict[str, float], *, folds: int = 8,
               weeks: int = 4, seed: int = RNG_SEED,
               bias_only_in_last_fold: bool = False) -> dict[str, pd.DataFrame]:
    """Fabricated OOF rows: y = base + N(0,3); point_consumed = base + bias + N(0,2);
    point_swap = base + swap_bias + N(0,2). Base ability varies per player (sd 6) so the points
    CARRY SIGNAL — without it `position_mean_point` would tie the arms and the degenerate clause
    would be decided by the fixture, not the assertion (the fixture-inertness lesson)."""
    rng = np.random.default_rng(seed)
    base = {p: rng.normal(_POS_BASE_MEAN[p], 6.0, _N_PER_POS[p]) for p in XP.POSITIONS}
    out: dict[str, pd.DataFrame] = {}
    for f in range(1, folds + 1):
        frames = []
        b_on = (not bias_only_in_last_fold) or (f == folds)
        for p in XP.POSITIONS:
            n = _N_PER_POS[p]
            for w in range(1, weeks + 1):
                y = base[p] + rng.normal(0.0, 3.0, n)
                pc = base[p] + (bias[p] if b_on else 0.0) + rng.normal(0.0, 2.0, n)
                psw = base[p] + (swap_bias[p] if b_on else 0.0) + rng.normal(0.0, 2.0, n)
                frames.append(pd.DataFrame({
                    "season": 2020 + f, "week": w, "gw": f * 100 + w,
                    "gsis_id": [f"{p}{i:03d}" for i in range(n)], "position": p,
                    "y": y, "point_consumed": pc, "point_swap": psw,
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
                "bias_identity": XP.bias_detail(df.loc[sel, "point_consumed"].to_numpy(),
                                                df.loc[sel, "y"].to_numpy()),
                "bias_swap": XP.bias_detail(df.loc[sel, "point_swap"].to_numpy(),
                                            df.loc[sel, "y"].to_numpy()),
                "calibration_slope": XP.calibration_slope(
                    df.loc[sel, "point_consumed"].to_numpy(), df.loc[sel, "y"].to_numpy()),
            }
        frs.append({"label": label, "n_test": int(len(df)), "positions": positions,
                    "bank_cache": "synthetic", "rows_path": str(path)})
    return frs


def _out_shell(frs: list[dict], tmp: Path) -> dict:
    return {"story": XP.STORY, "smoke": False, "generated_at": "synthetic",
            "gate_league": R.GATE_LEAGUE, "n_folds": len(frs),
            "fold_results": frs, "input_dir": str(tmp / "input")}


@pytest.fixture()
def pins_pass(monkeypatch):
    """Reproduction pins that MATCH the fabricated fold scores — the pass path. The fail path is
    the default (the real records' fold labels never match the synthetic ones — fails closed)."""
    def fake(position):
        return {f"F{f}": 2.0 + 0.01 * 2 for f in range(1, 9)}
    # the fabricated per-fold score is 2.0 + 0.01*len(label) with label 'F1'.. (len 2) — constant
    monkeypatch.setattr(R, "_generator_record_scores", fake)
    return fake


# ══════════════════════════════════════════════════════════════════════════════════════════════
# §1 — the QB consumption registration
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestQBConsumptionRegistration:
    def test_option_b_constants_are_pinned(self):
        assert XP.QB_CONSUMPTION == "OPTION_B_RECALIBRATED"
        assert XP.CONSUMED_GENERATOR_OF["QB"] == "qb_zm_floor"
        relpath, story, arm = XP.GENERATOR_RECORD_PINS["QB"]
        assert story == "NF-W7f" and arm == "zm_floor"
        assert "nf_w7f_qb_marginal.json" in relpath

    def test_second_reader_flag_is_open(self):
        assert XP.SECOND_READER["requested"] is True
        assert "OPEN" in XP.SECOND_READER["status"]

    def test_caveat_travels_and_does_not_claim_certification(self):
        assert "not certification-equivalent" in XP.QB_CONSUMPTION_CAVEAT
        # the rationale must not say QB is certified — the bar stands (E2.1-r)
        assert "certified" not in XP.QB_CONSUMPTION_RATIONALE.lower()

    def test_preregistration_file_carries_the_registration(self):
        text = _PREREG.read_text()
        for phrase in ("OPTION B", "not certification-equivalent", "SECOND-READER",
                       "E2.1-r", "NOT a re-certification"):
            assert phrase in text, f"prereg is missing the registered phrase {phrase!r}"

    def test_generator_pins_cover_every_position(self):
        assert set(XP.GENERATOR_RECORD_PINS) == set(XP.POSITIONS)
        assert set(XP.CONSUMED_GENERATOR_OF) == set(XP.POSITIONS)
        assert set(XP.SWAP_GENERATOR_OF) == set(XP.POSITIONS)

    def test_clause_partition_is_exact(self):
        assert set(XP.STATISTICAL_CLAUSES) | set(XP.ANCHOR_CLAUSES) == set(XP.ARM_CLAUSES)
        assert not set(XP.STATISTICAL_CLAUSES) & set(XP.ANCHOR_CLAUSES)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The pure estimators
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestBankPoint:
    def test_grid_mean_of_a_linear_quantile_function(self):
        # Q(u) = 10u ⇒ E[Y] = 5; the grid mean over uniform levels 0.005..0.995 is exactly 5
        bank = (10.0 * XP.EVAL_LEVELS)[None, :] * np.ones((3, 1))
        np.testing.assert_allclose(XP.bank_point(bank), 5.0, atol=1e-12)

    def test_wrong_shape_refused(self):
        with pytest.raises(ValueError):
            XP.bank_point(np.zeros((4, 10)))


class TestLevelFits:
    def test_add_recovers_a_known_bias(self):
        rng = np.random.default_rng(0)
        y = rng.normal(10, 3, 500)
        prm = XP.fit_level_add(y + 2.5, y)
        assert prm["fitted"] and abs(prm["delta"] + 2.5) < 1e-9

    def test_below_floor_is_identity_and_flagged(self):
        prm = XP.fit_level_add(np.ones(XP.MIN_PRIOR_ROWS - 1), np.ones(XP.MIN_PRIOR_ROWS - 1))
        assert prm["fitted"] is False and prm["delta"] == 0.0 and "flagged" in prm["note"]

    def test_affine_recovers_slope_and_intercept(self):
        rng = np.random.default_rng(1)
        pt = rng.normal(10, 4, 2000)
        y = 1.5 + 0.8 * pt + rng.normal(0, 0.01, 2000)
        prm = XP.fit_level_affine(pt, y)
        assert prm["fitted"] and abs(prm["b"] - 0.8) < 0.01 and abs(prm["a"] - 1.5) < 0.15

    def test_affine_zero_variance_is_identity_flagged(self):
        prm = XP.fit_level_affine(np.full(100, 3.0), np.arange(100.0))
        assert prm["fitted"] is False and prm["b"] == 1.0

    def test_negative_slope_makes_the_arm_ineligible(self):
        rng = np.random.default_rng(2)
        pt = rng.normal(10, 4, 500)
        y = -0.5 * pt + rng.normal(0, 0.01, 500)
        prm = XP.fit_level_affine(pt, y)
        assert prm["b"] < 0
        tables = {"F2": {"point_consumed": {p: {"level_affine": prm} for p in XP.POSITIONS}}}
        elig = R._affine_eligibility(tables, ["F2"])
        assert elig["eligible"] is False and len(elig["violations"]) == len(XP.POSITIONS)


class TestPairwiseGapTests:
    def test_distinct_biases_are_detected(self):
        rng = np.random.default_rng(3)
        bias = {"QB": [2.0 + rng.normal(0, .1) for _ in range(8)],
                "RB": [-1.0 + rng.normal(0, .1) for _ in range(8)],
                "WR": [0.5 + rng.normal(0, .1) for _ in range(8)],
                "TE": [0.0 + rng.normal(0, .1) for _ in range(8)]}
        fa = XP.pairwise_gap_tests(bias)
        assert fa["gap_detected"] is True
        assert fa["pairs"]["QB|RB"]["bh_rejected"] is True
        assert fa["max_mde_ppr"] is not None and fa["max_mde_ppr"] > 0

    def test_equal_biases_are_a_bounded_null(self):
        rng = np.random.default_rng(4)
        bias = {p: list(rng.normal(0.0, 0.1, 8)) for p in XP.POSITIONS}
        fa = XP.pairwise_gap_tests(bias)
        assert fa["gap_detected"] is False
        assert fa["max_mde_ppr"] is not None            # the null is 'no artifact larger than X'

    def test_one_fold_is_undefined_never_false(self):
        fa = XP.pairwise_gap_tests({p: [0.0] for p in XP.POSITIONS})
        assert fa["gap_detected"] is None               # NF1.7 (a): did-not-run is never a pass

    def test_unpaired_vectors_refused(self):
        with pytest.raises(ValueError):
            XP.pairwise_gap_tests({"QB": [0.0, 1.0], "RB": [0.0]})


class TestPermutedParams:
    def test_cyclic_shift(self):
        base = {p: {"delta": i} for i, p in enumerate(XP.POSITIONS)}
        perm = XP.permuted_params(base)
        for p in XP.POSITIONS:
            assert perm[p] is base[XP.PERMUTATION_CYCLE[p]]

    def test_cycle_is_a_derangement(self):
        assert all(XP.PERMUTATION_CYCLE[p] != p for p in XP.POSITIONS)
        assert set(XP.PERMUTATION_CYCLE.values()) == set(XP.POSITIONS)


class TestSwapClause:
    def test_active_position_collapse_passes(self):
        before = {"QB": np.full(7, 2.0) + np.linspace(-.1, .1, 7),
                  "WR": np.random.default_rng(5).normal(0, 0.05, 7)}   # WR inactive
        after = {"QB": np.random.default_rng(6).normal(0, 0.05, 7),
                 "WR": np.random.default_rng(7).normal(0, 0.05, 7)}
        sc = XP.swap_clause(before, after)
        assert sc["detail"]["QB"]["activity"]["active"] is True
        assert sc["detail"]["WR"]["activity"]["active"] is False
        assert sc["state"] == "PASS" and sc["passes"] is True and sc["n_active_positions"] == 1

    def test_no_collapse_fails(self):
        shifts = np.full(7, 2.0) + np.linspace(-.1, .1, 7)
        sc = XP.swap_clause({"QB": shifts}, {"QB": shifts})
        assert sc["state"] == "FAIL" and sc["passes"] is False

    def test_inactive_everywhere_is_not_a_pass(self):
        # deterministically inactive: zero pooled shift with real spread at every position
        zero_mean = np.array([0.05, -0.05, 0.05, -0.05, 0.05, -0.05, 0.0])
        before = {p: zero_mean.copy() for p in XP.POSITIONS}
        sc = XP.swap_clause(before, before)
        assert sc["state"] == XP.SWAP_INACTIVE_EVERYWHERE and sc["passes"] is None


class TestSelectArm:
    def _d(self, vals, eligible=True):
        return {"range_by_fold": list(vals), "eligible": eligible}

    def test_ineligible_affine_leaves_add(self):
        assert XP.select_arm({"level_add": self._d([1, 1, 1]),
                              "level_affine": self._d([0.1, 0.1, 0.1], eligible=False)}) \
            == "level_add"

    def test_tie_goes_to_the_simpler_arm(self):
        assert XP.select_arm({"level_add": self._d([1.0, 1.01, 0.99]),
                              "level_affine": self._d([1.0, 1.0, 1.0])}) == "level_add"

    def test_clearly_smaller_affine_wins(self):
        assert XP.select_arm({"level_add": self._d([1.0, 1.1, 0.9, 1.0]),
                              "level_affine": self._d([0.2, 0.25, 0.15, 0.2])}) == "level_affine"


class TestComparabilityVerdict:
    """Isolating fixture per AND-clause (NF-D17): every other clause True, only the clause under
    test flips — so each assertion can only be satisfied by its own clause."""

    def _clauses(self, **over):
        base = {c: True for c in XP.ARM_CLAUSES}
        base.update(over)
        return base

    def test_harness_failure_is_undefined(self):
        v = XP.comparability_verdict(harness_ok=False, gap_detected=True, max_mde_ppr=1.0,
                                     winner="level_add", winner_clauses=self._clauses(),
                                     swap_state="PASS")
        assert v["state"] == XP.V_UNDEFINED

    def test_unevaluable_family_a_is_undefined(self):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=None, max_mde_ppr=None,
                                     winner=None, winner_clauses=None, swap_state=None)
        assert v["state"] == XP.V_UNDEFINED

    def test_no_gap_is_comparable_with_a_stated_mde(self):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=False, max_mde_ppr=0.42,
                                     winner=None, winner_clauses=None, swap_state=None)
        assert v["state"] == XP.V_COMPARABLE and "0.42" in v["reason"]

    def test_all_clauses_green_ships_the_arm(self):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=True, max_mde_ppr=0.4,
                                     winner="level_add", winner_clauses=self._clauses(),
                                     swap_state="PASS")
        assert v["state"] == XP.V_REMOVED

    @pytest.mark.parametrize("clause", XP.ARM_CLAUSES)
    def test_each_failing_clause_alone_refuses(self, clause):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=True, max_mde_ppr=0.4,
                                     winner="level_add",
                                     winner_clauses=self._clauses(**{clause: False}),
                                     swap_state="FAIL" if clause == "swap_clause" else "PASS")
        assert v["state"] == XP.V_UNREPAIRED and clause in v["reason"]

    def test_inactive_swap_does_not_refuse(self):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=True, max_mde_ppr=0.4,
                                     winner="level_add",
                                     winner_clauses=self._clauses(swap_clause=None),
                                     swap_state=XP.SWAP_INACTIVE_EVERYWHERE)
        assert v["state"] == XP.V_REMOVED

    @pytest.mark.parametrize("clause", [c for c in XP.ARM_CLAUSES if c != "swap_clause"])
    def test_any_other_unevaluable_clause_refuses(self, clause):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=True, max_mde_ppr=0.4,
                                     winner="level_add",
                                     winner_clauses=self._clauses(**{clause: None}),
                                     swap_state="PASS")
        assert v["state"] == XP.V_UNREPAIRED and clause in v["reason"]

    def test_second_reader_travels_on_every_verdict(self):
        v = XP.comparability_verdict(harness_ok=True, gap_detected=False, max_mde_ppr=0.4,
                                     winner=None, winner_clauses=None, swap_state=None)
        assert v["second_reader"]["requested"] is True
        assert v["qb_consumption"] == "OPTION_B_RECALIBRATED"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The derive layer, end-to-end on synthetic rows
# ══════════════════════════════════════════════════════════════════════════════════════════════
BIAS = {"QB": 2.0, "RB": -1.0, "WR": 0.5, "TE": 0.0}
SWAP_BIAS = {"QB": 0.0, "RB": 1.5, "WR": 0.5, "TE": -2.0}   # WR agrees ⇒ swap-inactive there


class TestDeriveEndToEnd:
    def test_real_gap_is_removed(self, tmp_path, pins_pass):
        rows = _make_rows(BIAS, SWAP_BIAS)
        out = R.derive_verdict_layer(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert out["family_a"]["gap_detected"] is True
        assert out["verdict"]["state"] == XP.V_REMOVED
        w = out["recal"]["winner"]
        assert w in XP.REAL_ARMS
        # the measured identity biases recover the planted ones
        for p, b in BIAS.items():
            assert abs(out["identity_bias"]["pooled"][p]["bias_pooled"] - b) < 0.35, p
        # fold 1 is never evaluable (no prior OOF)
        assert "F1" not in out["recal"]["evaluable_folds"]
        assert out["recal"]["n_evaluable"] == 7
        # the arm's range collapses vs identity
        assert (out["recal"]["range_by_arm"][w]["pooled"]
                < out["recal"]["range_by_arm"]["identity"]["pooled"] / 2)
        # anchors: both degenerates lose RMSE at every position
        assert out["recal"]["winner_clauses"]["degenerates_lose"] is True
        # the swap clause genuinely exercised: ≥2 active positions (fixture-inertness guard)
        assert out["swap_verification"]["n_active_positions"] >= 2
        assert out["recal"]["winner_clauses"]["swap_clause"] is True
        # PIT preservation identity
        assert out["input"]["banks_untouched"] is True
        # the input parquets exist with the schema and the disclosures
        files = sorted(Path(out["input"]["dir"]).glob("*.parquet"))
        assert len(files) == 8
        df = pd.read_parquet(files[0])
        assert set(XP.INPUT_SCHEMA) <= set(df.columns)
        assert df.loc[df["position"] == "QB", "qb_option_b"].all()
        assert not df.loc[df["position"] != "QB", "qb_option_b"].any()
        assert not df.loc[df["position"] == "RB", "calibration_warning"].any()
        assert df.loc[df["position"] == "TE", "calibration_warning"].all()
        # VOR sanity: every week ranks, replacement is position-specific and finite
        assert df["overall_rank"].min() == 1
        assert df["vor"].notna().all()

    def test_no_gap_is_comparable_and_identity_ships(self, tmp_path, pins_pass):
        rows = _make_rows({p: 0.0 for p in XP.POSITIONS}, {p: 0.0 for p in XP.POSITIONS},
                          seed=RNG_SEED + 1)
        out = R.derive_verdict_layer(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert out["family_a"]["gap_detected"] is False
        assert out["verdict"]["state"] == XP.V_COMPARABLE
        assert out["input"]["shipped_arm"] == XP.INCUMBENT
        assert out["verdict"]["max_mde_ppr"] is not None

    def test_failed_reproduction_is_undefined_never_a_pass(self, tmp_path):
        # no pins_pass fixture: the real records' fold labels never match 'F1'.. ⇒ fails closed
        rows = _make_rows(BIAS, SWAP_BIAS, seed=RNG_SEED + 2)
        out = R.derive_verdict_layer(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        assert all(not r["reproduces"] for r in out["reproduction"].values())
        assert out["verdict"]["state"] == XP.V_UNDEFINED

    def test_recal_is_fit_on_prior_folds_only(self, tmp_path):
        # the bias exists ONLY in the last fold: a prior-only fit must see δ≈0 there while the
        # peeking oracle sees the planted bias — proves no eval-fold peek (chronology guard)
        rows = _make_rows({"QB": 3.0, "RB": 0.0, "WR": 0.0, "TE": 0.0},
                          {p: 0.0 for p in XP.POSITIONS}, bias_only_in_last_fold=True,
                          seed=RNG_SEED + 3)
        tables = R._fit_recal_tables(rows)
        last = sorted(rows)[-1]
        qb = tables[last]["point_consumed"]["QB"]
        assert abs(qb["level_add"]["delta"]) < 0.5              # no peek
        assert abs(qb["level_add_oracle"]["delta"] + 3.0) < 0.7  # the peek sees it
        assert tables[sorted(rows)[0]]["has_prior"] is False

    def test_permuted_anchor_does_not_repair_the_gap(self, tmp_path, pins_pass):
        rows = _make_rows(BIAS, SWAP_BIAS, seed=RNG_SEED + 4)
        out = R.derive_verdict_layer(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        w = out["recal"]["winner"]
        assert (out["recal"]["range_by_arm"]["level_add_permuted"]["pooled"]
                > out["recal"]["range_by_arm"][w]["pooled"])

    def test_position_mean_degenerate_satisfies_the_constraint_but_loses_the_metric(
            self, tmp_path, pins_pass):
        # NF1.8: a constraint a degenerate SATISFIES is fine — the metric eliminates it. The
        # per-position climatology constant trivially zeroes the cross-position bias range while
        # destroying all within-position skill: it must lose RMSE at every position. Scoring it
        # proves the comparability constraint was never promoted into a selection criterion.
        rows = _make_rows(BIAS, SWAP_BIAS, seed=RNG_SEED + 5)
        out = R.derive_verdict_layer(_out_shell(_fold_results(rows, tmp_path), tmp_path))
        w = out["recal"]["winner"]
        pm_range = out["recal"]["range_by_arm"]["position_mean_point"]["pooled"]
        assert pm_range is not None
        assert pm_range < out["recal"]["range_by_arm"]["identity"]["pooled"] / 2
        for p in XP.POSITIONS:
            assert (out["recal"]["rmse_pooled"]["position_mean_point"][p]
                    > out["recal"]["rmse_pooled"][w][p])


class TestBoardLevelChannel:
    def test_a_pure_level_shift_moves_other_positions_through_the_board(self):
        """The §3 flex channel, mechanically: shifting ONE position's level moves OTHER
        positions' overall ranks (interleaving + flex allocation), while the mean-matched board
        (level removed, ordering kept) moves nothing — the decomposition is exact for a pure
        constant shift."""
        rng = np.random.default_rng(9)
        frames = []
        for p in XP.POSITIONS:
            n = _N_PER_POS[p]
            pts = np.sort(rng.normal(_POS_BASE_MEAN[p], 6.0, n))[::-1]
            frames.append(pd.DataFrame({
                "gw": 1, "gsis_id": [f"{p}{i:03d}" for i in range(n)], "position": p,
                "point": pts}))
        df = pd.concat(frames, ignore_index=True)
        pts_a = df["point"].to_numpy(float)
        pts_b = pts_a.copy()
        te = (df["position"] == "TE").to_numpy()
        pts_b[te] = pts_b[te] - 5.0                     # a pure level artifact at TE
        cfg = R.LP.get_preset(R.GATE_LEAGUE)
        disp = R._weekly_displacement(df, pts_a, pts_b, "TE", cfg, R.LP.NFL_PROFILE)
        assert disp["own_mean_abs_rank_move"] > 0
        assert disp["other_mean_abs_rank_move"] > 0     # the cross-position channel is real
        pts_matched = pts_b.copy()
        pts_matched[te] = pts_matched[te] + 5.0         # mean-matched ⇒ identical points
        disp_m = R._weekly_displacement(df, pts_a, pts_matched, "TE", cfg, R.LP.NFL_PROFILE)
        assert disp_m["own_mean_abs_rank_move"] == 0.0
        assert disp_m["other_mean_abs_rank_move"] == 0.0


class TestReproductionPlumbing:
    def test_absent_record_is_did_not_run(self, monkeypatch):
        monkeypatch.setattr(R, "_generator_record_scores", lambda pos: None)
        rep = R._reproduction([{"label": "F1", "positions": {
            p: {"scores": {R.CONSUMED_BANK_LABEL[p]: 1.0}} for p in XP.POSITIONS}}], "QB")
        assert rep["reproduces"] is False and "DID NOT RUN" in rep["note"]

    def test_real_records_resolve_for_every_position(self):
        # the pins point at committed records that exist and carry the pinned arm's fold scores
        for pos in XP.POSITIONS:
            rec = R._generator_record_scores(pos)
            assert rec is not None and len(rec) == 8, pos
            assert all(np.isfinite(v) for v in rec.values())

    def test_qb_pin_matches_the_w7f_headline(self):
        # NF-W7f's recorded zm_floor QB fold scores — the exact values the decisive run must hit
        rec = R._generator_record_scores("QB")
        assert abs(rec["2025H2"] - 2.609) < 5e-4


class TestGateComputationSourceInspection:
    """INC-38: prose cannot satisfy these — comments are stripped before matching, and the
    match is anchored on the actual assignment, so a clause replaced by a literal True (or
    deleted) goes RED here even though every behavioral fixture in this file happens to pass."""

    @staticmethod
    def _code() -> str:
        src = Path(R.__file__.replace(".pyc", ".py")).read_text()
        return "\n".join(line.split("#")[0] for line in src.splitlines())

    def test_pbo_clause_reads_both_registered_constants(self):
        code = self._code()
        start = code.index('clauses["pbo_ok"]')          # raises (RED) if the clause is deleted
        stmt = code[start:code.index('clauses["dsr_ok"]')]
        assert "XP.PBO_MAX" in stmt and "XP.OS_GAP_TIE_PCT" in stmt, (
            "pbo_ok must be COMPUTED from the two registered constants (the NF1.8 tie "
            "discipline), never asserted")

    def test_dsr_clause_is_computed_not_asserted(self):
        code = self._code()
        start = code.index('clauses["dsr_ok"]')
        stmt = code[start:start + 200]
        assert "XP.DSR_MIN" in stmt and "bool(" in stmt


class TestFoldRangeAndHelpers:
    def test_fold_range(self):
        assert XP.fold_range({"QB": 2.0, "RB": -1.0, "WR": 0.5, "TE": 0.0}) == 3.0

    def test_fold_range_refuses_a_single_position(self):
        with pytest.raises(ValueError):
            XP.fold_range({"QB": 2.0})

    def test_bh_fails_closed_on_none(self):
        out = XP.bh_reject({"a": None, "b": 0.001}, q=0.10)
        assert out["a"] is False and out["b"] is True

    def test_bias_detail_refuses_non_finite(self):
        with pytest.raises(ValueError):
            XP.bias_detail(np.array([1.0, np.nan]), np.array([1.0, 2.0]))
