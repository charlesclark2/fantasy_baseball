"""Guards for NF-MARGIN3 — a better QB/WR tail-magnitude estimator vs `tail_ext` (1-arm family).

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.margin3_tail_estimator`); the runner is never
imported (it pulls the lake-reading story runners).

Discipline inherited from the NF-MARGIN1/NF-MARGIN2 suites:
  · every gate clause has an ISOLATING fixture — a base selection where every clause passes and
    a per-clause mutation that flips exactly that clause (NF-D17);
  · ⭐ the story card's arm-MOVABILITY requirement is PROVED, not asserted: the tail-mass gate
    statistic (beyond-EVAL-grid deviation) is shown to move between the arm and THE FOIL on a
    synthetic where the exceedance law is not exponential — a statistic the arm could not move
    would be décor, not a gate (NF-D20 (g⁗));
  · the estimator is proved to BE what the pre-registration says it is: the pooled pinball
    optimum at each beyond-grid eval level, i.e. the offsets calibrate the eval-end exceedance
    rates on the fitting sample;
  · ⭐ THE BAR is pinned: the foil is `tail_ext`, the incumbent is reference-only and NOT in the
    eligible field;
  · fail-closed clauses are RED-proved (NF1.7 (a)).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from quant_sports_intel_models.football.nfl.fantasy import game_environment as GE
from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import margin2_tail_extension as M2
from quant_sports_intel_models.football.nfl.fantasy import margin3_tail_estimator as M3
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_RNG = np.random.default_rng(20260815)


def _bank(n: int = 200, loc: float = 10.0, scale: float = 5.0,
          rng: np.random.Generator | None = None) -> np.ndarray:
    """A monotone synthetic 39-level quantile bank: N(loc, scale) quantiles + row jitter."""
    rng = rng or _RNG
    from scipy.stats import norm
    base = norm.ppf(WP.Q_LEVELS, loc=loc, scale=scale)
    shift = rng.normal(0, 1, size=(n, 1))
    return np.sort(base[None, :] + shift, axis=1)


def _eq_params(hi: float = 4.0, lo: float = 2.0) -> dict:
    """Simple valid eq params: linearly growing offsets toward the far levels."""
    t_hi = hi * np.array([0.25, 0.5, 0.75, 1.0])
    t_lo = lo * np.array([1.0, 0.75, 0.5, 0.25])   # LO levels ascend ⇒ offsets nonincreasing
    return {"t_hi": t_hi, "t_lo": t_lo, "n_hi": 99, "n_lo": 99, "m_hi": 0.05, "m_lo": 0.04,
            "thin_hi": False, "thin_lo": False, "clamped_hi": 0, "clamped_lo": 0}


_TAIL = {"beta_hi": 3.0, "beta_lo": 1.0, "n_hi": 99, "n_lo": 99,
         "thin_hi": False, "thin_lo": False}


# ── Field + pre-registration ────────────────────────────────────────────────────────────────────
class TestFieldAndPreregistration:
    def test_the_bar_is_tail_ext_not_the_incumbent(self):
        """⭐ The story card's headline constraint: the foil is the STANDING OBJECT; the
        incumbent is reference-only and must never enter the eligible field."""
        assert M3.REAL_ARMS == ("eq_tail",)
        assert M3.FOILS == ("tail_ext",)
        assert M3.REFERENCE == ("incumbent",)
        assert M3.eligible_labels() == ["eq_tail", "tail_ext"]
        assert "incumbent" not in M3.eligible_labels()

    def test_anchors_never_enter_the_eligible_field(self):
        eligible = set(M3.eligible_labels())
        assert eligible.isdisjoint(M3.anchors())
        assert set(M3.anchors()) == {"zero_width", "max_width", "over_ext_eq", "permuted_eq",
                                     "pooled_eq", "oracle__eq_tail", "matched_n__eq_tail"}

    def test_the_family_is_qb_wr_only_and_rb_te_are_report_only(self):
        """The two refused positions form the family; RB/TE are registered non-shippable —
        their p-values must never enter BH (NF-D20 decision-shape)."""
        assert M3.LIVE_POSITIONS == ("QB", "WR")
        assert set(M3.REPORT_ONLY_POSITIONS) == {"RB", "TE"}
        assert set(M3.LIVE_POSITIONS) | set(M3.REPORT_ONLY_POSITIONS) == set(M3.POSITIONS)
        assert M3.FDR_FAMILY == ("margin3_tail_QB", "margin3_tail_WR")
        assert not any(p in k for k in M3.FDR_FAMILY for p in ("RB", "TE"))

    def test_pbo_is_undefined_by_design_at_a_one_arm_family(self):
        assert not GE.pbo_is_evaluable(len(M3.REAL_ARMS))
        assert "pbo_ok" not in M3.M3_STATISTICAL_CHECKS

    def test_the_magnitude_degenerate_is_a_genuine_over_extension(self):
        assert M3.OVER_SCALE > 1.0

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        pre = Path(__file__).resolve().parents[2] / (
            "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
            "nf_margin3_preregistration.md")
        assert pre.exists(), "the narrative pre-registration must be committed before the run"
        text = pre.read_text()
        for token in ("eq_tail", "tail_ext", "crps_q199", "MH2.2", "UNDEFINED", "deploy-held",
                      "best_alpha = 0", "pinball", "GPD", "arm-MOVABLE", "over_ext_eq",
                      "randomized_pit_levels", "NON-SHIPPABLE", "20260815"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_coverage_is_a_floor_never_a_target(self):
        """⛔ E2.1-r: no objective may reference |coverage − floor|. Source-inspected with
        comments stripped so prose can neither satisfy nor trip it (INC-38)."""
        src = Path(M3.__file__).read_text()
        code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", code)

    def test_seed_is_fresh_and_distinct_from_both_predecessors(self):
        assert M3._SEED not in (MC._SEED, M2._SEED)


# ── The estimator: it IS what the pre-registration says it is ───────────────────────────────────
class TestEstimator:
    def test_offsets_calibrate_the_eval_end_exceedance_rates(self):
        """The defining property: on the fitting sample, P(y > q975 + t_hi(u)) ≈ 1 − u at every
        beyond-grid level (mirrored below) — 'calibrated on eval-end exceedances', literally."""
        rng = np.random.default_rng(7)
        n = 20000
        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        p = M3.fit_eq_tail(q39, y)
        assert not p["thin_hi"] and not p["thin_lo"]
        for u, t in zip(M3.HI_LEVELS, p["t_hi"]):
            rate = float(np.mean(y > q39[:, -1] + t))
            assert abs(rate - (1 - u)) < 3e-3, (u, t, rate)
        for u, t in zip(M3.LO_LEVELS, p["t_lo"]):
            rate = float(np.mean(y < q39[:, 0] - t))
            assert abs(rate - u) < 3e-3, (u, t, rate)

    def test_offsets_are_the_pooled_pinball_optimum(self):
        """The metric-optimality claim, brute-forced: at the far level the fitted offset must
        (approximately) minimize the pooled pinball loss over a fine grid of alternatives."""
        rng = np.random.default_rng(11)
        n = 12000
        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        p = M3.fit_eq_tail(q39, y)
        u = float(M3.HI_LEVELS[-1])                      # 0.995
        t_fit = float(p["t_hi"][-1])

        def pinball(t: float) -> float:
            q = q39[:, -1] + t
            return float(np.mean((u - (y < q)) * (y - q)))

        grid = np.linspace(max(0.0, t_fit - 6.0), t_fit + 6.0, 241)
        best = grid[int(np.argmin([pinball(t) for t in grid]))]
        assert abs(best - t_fit) < 0.3, (best, t_fit)

    def test_offsets_are_monotone_and_nonnegative(self):
        rng = np.random.default_rng(13)
        q39 = _bank(4000, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, 4000) * 5.0
        p = M3.fit_eq_tail(q39, y)
        assert (np.asarray(p["t_hi"]) >= 0).all() and (np.asarray(p["t_lo"]) >= 0).all()
        assert (np.diff(p["t_hi"]) >= 0).all(), "hi offsets must be nondecreasing in u"
        assert (np.diff(p["t_lo"]) <= 0).all(), "lo offsets must be nonincreasing in u"

    def test_a_thin_side_collapses_loudly_to_the_clamp(self):
        """< MIN_TAIL_N exceedances ⇒ offsets 0 + the thin flag — loud, never silent
        (NF1.7 (a); the NF-MARGIN2 convention verbatim)."""
        rng = np.random.default_rng(17)
        q39 = _bank(500, rng=rng)
        y = q39[:, 20]                                   # inside the grid: no exceedances
        p = M3.fit_eq_tail(q39, y)
        assert p["thin_hi"] and p["thin_lo"]
        assert (np.asarray(p["t_hi"]) == 0).all() and (np.asarray(p["t_lo"]) == 0).all()

    def test_an_already_calibrated_end_clamps_to_zero_and_is_counted(self):
        """When the empirical beyond-mass is thinner than 1 − u the raw quantile is ≤ 0 — the
        arm must degrade to the flat incumbent AT THAT LEVEL, counted in `clamped_*`."""
        rng = np.random.default_rng(19)
        n = 20000
        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        # exactly ~40 tiny hi exceedances (mass 0.002 < every 1−u in {0.02..0.005}) — not thin
        y = q39[:, 20].copy()
        idx = rng.choice(n, 40, replace=False)
        y[idx] = q39[idx, -1] + rng.exponential(1.0, 40)
        p = M3.fit_eq_tail(q39, y)
        assert not p["thin_hi"] and p["n_hi"] == 40
        assert (np.asarray(p["t_hi"]) == 0).all()
        assert p["clamped_hi"] == len(M3.HI_LEVELS)

    def test_scale_eq_scales_and_keeps_zeros_zero(self):
        p = _eq_params()
        p["t_lo"] = np.zeros(4)
        scaled = M3.scale_eq(p)
        assert np.allclose(scaled["t_hi"], np.asarray(p["t_hi"]) * M3.OVER_SCALE)
        assert (scaled["t_lo"] == 0).all(), "the degenerate cannot invent a tail the fit refused"


# ── ⭐ Arm-movability of the gate statistic (the story card's design-time check) ────────────────
class TestGateMovability:
    def test_the_tail_mass_gate_is_arm_movable_vs_the_foil(self):
        """THE pre-registration §4 proof: on a fat-tailed reality the arm and the foil place the
        beyond-grid eval columns at different x, so the beyond-EVAL-grid deviation MOVES between
        them — and the calibrated arm's is smaller (the estimator calibrates those ends by
        construction; the exponential is mis-specified for a t(3) excess). A statistic the arm
        could not move would be décor, not a gate (NF-D20 (g⁗))."""
        rng = np.random.default_rng(41)
        n = 8000
        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0          # fat-tailed reality
        y_cal = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0      # honest calibration draw
        eq = M3.fit_eq_tail(q39, y_cal)
        tail = M2.fit_tail_betas(q39, y_cal)
        arm = M3.build_bank_m3("eq_tail", eq, q39)
        foil = M3.build_bank_m3("tail_ext", tail, q39)
        inc = M3.build_bank_m3("incumbent", None, q39)
        s = {lab: M3.pit_stats_m2(M3.randomized_pit_levels(b, y, np.random.default_rng(1)))
             for lab, b in (("arm", arm), ("foil", foil), ("inc", inc))}
        # champion-grid mass: ARM-INVARIANT across all three (the NF-D20 trap, still true)
        assert s["arm"]["n_above_grid"] == s["foil"]["n_above_grid"] == s["inc"]["n_above_grid"]
        assert s["arm"]["n_below_grid"] == s["foil"]["n_below_grid"] == s["inc"]["n_below_grid"]
        p = {k: M3.pool_pit_stats_m2([v]) for k, v in s.items()}
        dev = {k: M3.tail_mass_deviation(v) for k, v in p.items()}
        assert dev["arm"] != dev["foil"], "the gate statistic must be MOVABLE arm-vs-foil"
        assert dev["arm"] < dev["foil"] < dev["inc"]

    def test_the_39_level_instrument_is_blind_to_the_contrast(self):
        """Arm and foil share every champion-grid column byte-for-byte, so the 39-level PIT of
        both is IDENTICAL — the gate must live on the 199-level bank (NF-MARGIN2 verbatim)."""
        q39 = _bank(300)
        y = q39.mean(axis=1) + _RNG.standard_t(3, 300) * 6
        arm = M3.build_bank_m3("eq_tail", _eq_params(), q39)
        foil = M3.build_bank_m3("tail_ext", _TAIL, q39)
        assert np.array_equal(arm[:, M3.IDX_Q39], foil[:, M3.IDX_Q39])
        u_a = M3.randomized_pit_levels(arm[:, M3.IDX_Q39], y,
                                       np.random.default_rng(7), WP.Q_LEVELS)
        u_f = M3.randomized_pit_levels(foil[:, M3.IDX_Q39], y,
                                       np.random.default_rng(7), WP.Q_LEVELS)
        assert np.array_equal(u_a, u_f)


# ── Constructions ───────────────────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_within_grid_byte_identity_holds_for_arm_foil_and_every_eq_label(self):
        q39 = _bank(80)
        inc = M3.build_bank_m3("incumbent", None, q39)
        for label, params in [("eq_tail", _eq_params()), ("permuted_eq", _eq_params()),
                              ("pooled_eq", _eq_params()), ("over_ext_eq", _eq_params()),
                              ("oracle__eq_tail", _eq_params()),
                              ("matched_n__eq_tail", _eq_params()),
                              ("tail_ext", _TAIL)]:
            bank = M3.build_bank_m3(label, params, q39)
            M3.assert_within_grid_identity(bank, inc, label)  # must not raise
            assert not np.array_equal(bank, inc), (
                f"{label} must actually differ beyond the grid, else the identity check "
                f"passes on nothing (non-vacuity)")

    def test_identity_assert_fires_on_a_within_grid_modification(self):
        q39 = _bank(30)
        inc = M3.build_bank_m3("incumbent", None, q39)
        bad = M3.build_bank_m3("eq_tail", _eq_params(), q39)
        mid = int(np.searchsorted(M3.EVAL_LEVELS, 0.5))
        bad[:, mid] += 0.01
        with pytest.raises(ValueError, match="tail-ONLY"):
            M3.assert_within_grid_identity(bad, inc, "eq_tail")

    def test_the_foil_is_byte_identical_to_the_nf_margin2_construction(self):
        """Reproduction BY CONSTRUCTION: `tail_ext` here must be the same object NF-MARGIN2
        scored — the builder delegates, and this pins it (the cross-story anchor's basis)."""
        q39 = _bank(60)
        ours = M3.build_bank_m3("tail_ext", _TAIL, q39)
        theirs = M2.build_bank_m2("tail_ext", _TAIL, q39)
        assert np.array_equal(ours, theirs)

    def test_apply_eq_tail_refuses_negative_or_non_monotone_offsets(self):
        q39 = _bank(10)
        bad = _eq_params()
        bad["t_hi"] = np.array([0.5, 0.4, 0.6, 0.7])     # non-monotone
        with pytest.raises(ValueError, match="not monotone"):
            M3.apply_eq_tail(q39, bad)
        bad2 = _eq_params()
        bad2["t_lo"] = np.array([1.0, 0.75, 0.5, -0.1])  # negative ⇒ would cross the grid
        with pytest.raises(ValueError, match="≥ 0"):
            M3.apply_eq_tail(q39, bad2)

    def test_declared_inactive_metrics_are_identically_zero_and_the_primary_moves(self):
        """Winkler-80 / coverage(50/80/95) identical for arm AND foil vs the incumbent;
        crps_q199 + coverage_99 move — the only active channels (NF-D20 (g⁗))."""
        rng = np.random.default_rng(42)
        n = 6000
        q39 = _bank(n, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        y_cal = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0
        s_inc = M3.score_bank(M3.build_bank_m3("incumbent", None, q39), y)
        s_arm = M3.score_bank(M3.build_bank_m3("eq_tail", M3.fit_eq_tail(q39, y_cal), q39), y)
        s_foil = M3.score_bank(M3.build_bank_m3("tail_ext", M2.fit_tail_betas(q39, y_cal),
                                                q39), y)
        for m in ("winkler_80", "coverage_50", "coverage_80", "coverage_95"):
            assert s_inc[m] == s_arm[m] == s_foil[m], f"{m} must be identical by construction"
        assert s_arm["crps_q199"] != s_foil["crps_q199"]
        assert s_arm["coverage_99"] > s_inc["coverage_99"]
        assert s_arm["crps_q199"] < s_inc["crps_q199"]

    def test_the_arm_beats_the_foil_where_the_exceedance_law_is_heavier_than_exponential(self):
        """The story's core hypothesis, demonstrable in vitro: on a reality whose exceedances
        are HEAVIER than exponential (the QB/WR diagnosis), the calibrated offsets beat the
        mean-excess exponential on crps_q199 — the channel the arm exists to win."""
        rng = np.random.default_rng(43)
        n = 16000

        def _draw(q39: np.ndarray) -> np.ndarray:
            u = rng.random(len(q39))
            y = np.array([np.interp(ui, WP.Q_LEVELS, row) for ui, row in zip(u, q39)])
            hi, lo = u > WP.Q_LEVELS[-1], u < WP.Q_LEVELS[0]
            # lognormal excess: heavier than any exponential fit by mean-matching
            y[hi] = q39[hi, -1] + rng.lognormal(0.0, 1.4, int(hi.sum()))
            y[lo] = q39[lo, 0] - rng.lognormal(0.0, 1.4, int(lo.sum()))
            return y

        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y, y_cal = _draw(q39), _draw(q39)
        arm = M3.build_bank_m3("eq_tail", M3.fit_eq_tail(q39, y_cal), q39)
        foil = M3.build_bank_m3("tail_ext", M2.fit_tail_betas(q39, y_cal), q39)
        assert (M3.score_bank(arm, y)["crps_q199"]
                < M3.score_bank(foil, y)["crps_q199"])

    def test_over_extension_loses_to_the_calibrated_fit_on_matched_reality(self):
        """The NF-D20 magnitude degenerate must be BEATABLE: when reality matches the
        calibration draw, offsets × OVER_SCALE overshoot the pinball optimum and score worse.
        (In NF-MARGIN2 `over_ext` WON at QB because the mean-excess base under-extended; a
        calibrated base removes that headroom — which is the whole story.)"""
        rng = np.random.default_rng(47)
        n = 16000

        def _draw(q39: np.ndarray) -> np.ndarray:
            u = rng.random(len(q39))
            y = np.array([np.interp(ui, WP.Q_LEVELS, row) for ui, row in zip(u, q39)])
            hi, lo = u > WP.Q_LEVELS[-1], u < WP.Q_LEVELS[0]
            y[hi] = q39[hi, -1] + rng.exponential(3.0, int(hi.sum()))
            y[lo] = q39[lo, 0] - rng.exponential(3.0, int(lo.sum()))
            return y

        q39 = _bank(n, loc=0.0, scale=2.0, rng=rng)
        y, y_cal = _draw(q39), _draw(q39)
        eq = M3.fit_eq_tail(q39, y_cal)
        s_arm = M3.score_bank(M3.build_bank_m3("eq_tail", eq, q39), y)["crps_q199"]
        s_over = M3.score_bank(M3.build_bank_m3("over_ext_eq", eq, q39), y)["crps_q199"]
        assert s_over > s_arm

    def test_over_ext_eq_extends_strictly_beyond_the_arm_where_offsets_engage(self):
        q39 = _bank(20)
        p = _eq_params()
        arm = M3.build_bank_m3("eq_tail", p, q39)
        over = M3.build_bank_m3("over_ext_eq", p, q39)
        above = M3.EVAL_LEVELS > WP.Q_LEVELS[-1]
        assert (over[:, above] > arm[:, above]).all()

    def test_unknown_label_raises(self):
        with pytest.raises(ValueError, match="unknown construction"):
            M3.build_bank_m3("mystery_arm", None, _bank(3))


# ── Gate clauses (isolating fixtures — NF-D17) ──────────────────────────────────────────────────
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"passes": True},
        "dsr": 0.99,
        "anchors": {"zero_width_loses": True, "max_width_loses": True,
                    "over_ext_eq_loses": True,
                    "permuted_not_significantly_better": True,
                    "oracle_floor_respected_at_matched_n": True},
        "coverage": {"blocking_shortfall": False},
        "calibration": {"tail_mass_delta_vs_foil": 0.005},
    }


class TestGateClauses:
    def test_the_passing_fixture_ships(self):
        gate = M3.compose_gate_margin3(_passing_sel(), True)
        assert gate["ship"], gate["checks"]

    def test_pbo_is_absent_from_the_gate(self):
        checks = M3.compose_gate_margin3(_passing_sel(), True)["checks"]
        assert "pbo_ok" not in checks, "PBO is UNDEFINED by design at a 1-arm family (§6)"

    @pytest.mark.parametrize("mutate,expect_check", [
        (lambda s: s.update(beats_foil=False), "beats_tail_ext"),
        (lambda s: s["fold_clause"].update(passes=False), "fold_consistency"),
        (lambda s: s.update(dsr=0.5), "dsr_ok"),
        (lambda s: s.update(dsr=None), "dsr_ok"),
        (lambda s: s["coverage"].update(blocking_shortfall=True), "coverage_floor_ok"),
        (lambda s: s["anchors"].update(zero_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(max_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(over_ext_eq_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(permuted_not_significantly_better=False),
         "permutation_not_better"),
        (lambda s: s["anchors"].update(oracle_floor_respected_at_matched_n=False),
         "oracle_floor_respected"),
        (lambda s: s["calibration"].update(tail_mass_delta_vs_foil=-0.001),
         "tail_mass_toward_nominal"),
    ])
    def test_each_clause_flips_only_itself(self, mutate, expect_check):
        sel = _passing_sel()
        mutate(sel)
        gate = M3.compose_gate_margin3(sel, True)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == [expect_check], (
            f"mutation must flip exactly `{expect_check}`, flipped {failed} — a fixture that "
            f"trips several clauses proves none of them (NF-D17)")
        assert not gate["ship"]

    def test_fdr_clause_flips_only_fdr(self):
        gate = M3.compose_gate_margin3(_passing_sel(), False)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == ["fdr_ok"]

    def test_the_tail_mass_clause_reads_the_foil_key_not_the_incumbent_key(self):
        """⭐ The bar is `tail_ext`: a selection carrying only an incumbent-keyed delta must
        KeyError, not silently pass — the NF-MARGIN2 clause may not be reused verbatim here."""
        sel = _passing_sel()
        sel["calibration"] = {"tail_mass_delta_vs_incumbent": 0.05}
        with pytest.raises(KeyError):
            M3.compose_gate_margin3(sel, True)

    def test_permutation_clause_fails_closed_on_an_unevaluable_p(self):
        """NF1.7 (a): a positive permuted advantage with no evaluable p is NOT a pass."""
        assert not M3.permuted_not_significantly_better(0.01, None)
        assert M3.permuted_not_significantly_better(-0.01, None)
        assert M3.permuted_not_significantly_better(0.01, 0.20)
        assert not M3.permuted_not_significantly_better(0.01, 0.01)

    def test_anchor_only_refusal_is_constraint_refused(self):
        sel = _passing_sel()
        sel["anchors"]["over_ext_eq_loses"] = False
        checks = M3.compose_gate_margin3(sel, True)["checks"]
        verdict = M3.hand_classify_refusal_margin3(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert verdict["retest_trigger"] is None

    def test_calibration_only_refusal_is_constraint_refused_and_named(self):
        sel = _passing_sel()
        sel["calibration"]["tail_mass_delta_vs_foil"] = -0.02
        checks = M3.compose_gate_margin3(sel, True)["checks"]
        verdict = M3.hand_classify_refusal_margin3(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert "tail_mass_toward_nominal" in verdict["failing_anchor_checks"]

    def test_statistical_refusal_delegates_to_the_layer_b_classifier(self):
        sel = _passing_sel()
        sel["beats_foil"] = False
        checks = M3.compose_gate_margin3(sel, True)["checks"]
        assert M3.hand_classify_refusal_margin3(checks) is None


# ── Null classification (the 1-arm hand path — carried, re-pinned) ──────────────────────────────
def _sel_for_classifier(beats: bool) -> dict:
    return {
        "beats_foil": beats, "mean_delta": 0.0004 if beats else -0.0004,
        "ci95": [-0.0001, 0.0009] if beats else [-0.0009, 0.0001],
        "fold_wins": 6 if beats else 3,
        "fold_clause": {"required": 6},
        "p_one_sided": 0.08 if beats else 0.7,
        "observed_sr": 0.45 if beats else -0.2,
    }


class TestNullClassification:
    def test_a_losing_arm_is_genuine_absence_with_no_trigger(self):
        out = M3.classify_layer_b(_sel_for_classifier(False), n_folds=8)
        assert out["state"] == "GENUINE_ABSENCE"
        assert out["retest_trigger"] is None

    def test_the_instrument_verdict_is_recorded_never_discarded(self):
        iv = {"state": "UNDEFINED", "reason": "8 fold(s) < 4", "retest_trigger": "-4 folds"}
        out = M3.classify_layer_b(_sel_for_classifier(True), n_folds=8, instrument_verdict=iv)
        assert out["instrument_verdict"] == iv
        assert out["hand_corrected"] is True
