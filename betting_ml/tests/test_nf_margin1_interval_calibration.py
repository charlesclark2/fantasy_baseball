"""Guards for NF-MARGIN1 — per-player interval/tail calibration of the hurdle champion.

Fast-gate, no IO: everything here exercises the PURE module
(`quant_sports_intel_models.football.nfl.fantasy.margin_calibration`); the runner is never
imported (it pulls the lake-reading story runners).

Discipline inherited from the NF-W3/W4/W5 suites:
  · every gate clause has an ISOLATING fixture — a base selection where every clause passes and
    a per-clause mutation that flips exactly that clause (NF-D17);
  · RED-proofs assert the refusal actually fires on bad input (a guard that cannot fail is
    worse than none — INC-38/INC-39);
  · the widen-only knob's monotonicity (NF1.7 (d)) and the identity map's byte-level no-op
    reproduction (the delta-harness-must-reproduce-a-no-op rule) are proved, not asserted.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import margin_calibration as MC
from quant_sports_intel_models.football.nfl.fantasy import opportunity_allocation as OA
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_RNG = np.random.default_rng(20260812)


def _bank(n: int = 200, loc: float = 10.0, scale: float = 5.0,
          rng: np.random.Generator | None = None) -> np.ndarray:
    """A monotone synthetic 39-level quantile bank: N(loc, scale) quantiles + row jitter."""
    rng = rng or _RNG
    from scipy.stats import norm
    base = norm.ppf(WP.Q_LEVELS, loc=loc, scale=scale)
    shift = rng.normal(0, 1, size=(n, 1))
    return np.sort(base[None, :] + shift, axis=1)


# ── Field + pre-registration ────────────────────────────────────────────────────────────────────
class TestFieldAndPreregistration:
    def test_the_declared_field_is_the_sec05_minimum(self):
        assert len(MC.REAL_ARMS) >= 3, "§0.5 requires ≥3 candidate classes"
        assert len(MC.FOILS) >= 2 and "incumbent" in MC.FOILS
        assert set(MC.REAL_ARMS).isdisjoint(MC.FOILS)

    def test_anchors_never_enter_the_eligible_field(self):
        eligible = set(MC.eligible_labels())
        assert eligible == set(MC.REAL_ARMS) | set(MC.FOILS)
        assert eligible.isdisjoint(MC.anchors())

    def test_every_parametrized_form_has_an_oracle_and_every_arm_a_matched_n(self):
        anchors = set(MC.anchors())
        for f in MC.PARAMETRIZED_FORMS:
            assert MC.oracle_of(f) in anchors
        for a in MC.REAL_ARMS:
            assert MC.matched_n_of(a) in anchors
        assert MC.oracle_of("incumbent") not in anchors, (
            "the incumbent has no parameters — its peeking version is itself (declared)")

    def test_form_resolution_strips_anchor_prefixes(self):
        assert MC.form_of("oracle__pit_recal_tail") == "pit_recal_tail"
        assert MC.form_of("matched_n__level_widen") == "level_widen"
        assert MC.form_of("incumbent") == "incumbent"

    def test_fdr_families_are_disjoint_and_position_keyed(self):
        arm, tail = set(MC.FDR_FAMILIES["arm"]), set(MC.FDR_FAMILIES["tail_channel"])
        assert arm.isdisjoint(tail)
        assert len(arm) == len(tail) == len(MC.POSITIONS)

    def test_the_widen_grid_is_the_nf1_7d_clamp(self):
        """The widen-only knob's clamp IS the grid — nothing below 1.0 is expressible."""
        assert min(MC.WIDEN_GRID) == 1.0
        assert MC.WIDEN_GRID[0] == 1.0

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        pre = Path(__file__).resolve().parents[2] / (
            "quant_sports_intel_models/football/nfl/fantasy/ablation_results/"
            "nf_margin1_preregistration.md")
        assert pre.exists(), "the narrative pre-registration must be committed before the run"
        text = pre.read_text()
        for token in ("crps_q199", "pit_recal_tail", "level_widen", "zscore_affine",
                      "deploy-held", "best_alpha = 0", "0.706"):
            assert token in text, f"pre-registration is missing `{token}`"

    def test_coverage_is_a_floor_never_a_target(self):
        """⛔ E2.1-r: no fitting objective may reference |coverage − floor|. Source-inspected
        with comments stripped so prose can neither satisfy nor trip it (INC-38)."""
        src = Path(MC.__file__).read_text()
        code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
        assert not re.search(r"abs\([^)]*coverage[^)]*-\s*(0\.8|COVERAGE_FLOOR)", code)
        # the floor appears only in floor/report contexts — never inside a fit_ function
        for m in re.finditer(r"def (fit_\w+)\(.*?(?=\ndef |\Z)", code, re.S):
            assert "COVERAGE_FLOOR" not in m.group(0), (
                f"{m.group(1)} references the coverage floor — a floor must never be fit toward")


# ── Grid identity + the no-op reproduction rule ─────────────────────────────────────────────────
class TestGridIdentity:
    def test_eval_grid_contains_the_champion_grid_exactly(self):
        assert len(MC.EVAL_LEVELS) == 199
        assert np.array_equal(MC.EVAL_LEVELS[MC.IDX_Q39], WP.Q_LEVELS)

    def test_identity_map_reproduces_the_incumbent_bank(self):
        """The no-op reproduction rule: the harness applied with the identity map must return
        the champion bank itself at the 39 columns, and equal `OA.x_from_uniforms` everywhere."""
        q39 = _bank(60)
        inc = MC.build_eval_bank("incumbent", None, q39)
        assert np.allclose(inc[:, MC.IDX_Q39], q39, atol=1e-12)
        for i in (0, 17, 59):
            assert np.allclose(inc[i], OA.x_from_uniforms(q39[i], MC.EVAL_LEVELS), atol=1e-12)

    def test_apply_refuses_a_non_monotone_map(self):
        q39 = _bank(5)
        g = MC.EVAL_LEVELS.copy()
        g[50], g[51] = g[51], g[50]
        with pytest.raises(ValueError, match="not monotone"):
            MC.apply_level_map(q39, g)

    def test_every_construction_emits_monotone_rows(self):
        q39 = _bank(40)
        u = np.sort(_RNG.random(4000))
        cases = {
            "incumbent": None,
            "zero_width": None,
            "max_width": None,
            "pit_recal_pos": u,
            "pit_recal_tail": {"u_sorted": u,
                               "tail": {"beta_hi": 2.0, "beta_lo": 0.5, "n_hi": 50, "n_lo": 50}},
            "level_widen": 1.3,
            "zscore_affine": {"mu": 0.1, "sigma": 1.2},
        }
        for label, params in cases.items():
            bank = MC.build_eval_bank(label, params, q39)
            assert (np.diff(bank, axis=1) >= -1e-9).all(), label

    def test_case_list_is_exhaustive_over_the_field(self):
        forms = {MC.form_of(lab) for lab in MC.all_labels()}
        known = {"incumbent", "zero_width", "max_width", "permuted_recal", "pit_recal_pos",
                 "pit_recal_global", "pit_recal_tail", "level_widen", "zscore_affine"}
        assert forms == known

    def test_unknown_label_raises(self):
        with pytest.raises(ValueError, match="unknown construction"):
            MC.build_eval_bank("mystery_arm", None, _bank(3))


# ── The widen-only knob (NF1.7 (d)) ─────────────────────────────────────────────────────────────
class TestWidenOnly:
    def test_widening_is_monotone_at_every_level(self):
        """|q(tau) − median| is nondecreasing in w for EVERY tau — widen-only BY CONSTRUCTION,
        the clause NF1.7 (d) says must be proved, not asserted."""
        q39 = _bank(30)
        prev = MC.apply_level_map(q39, MC.widen_levels(1.0))
        for w in (1.05, 1.2, 1.6, 2.5):
            cur = MC.apply_level_map(q39, MC.widen_levels(w))
            up, dn = MC.EVAL_LEVELS > 0.5, MC.EVAL_LEVELS < 0.5
            assert (cur[:, up] >= prev[:, up] - 1e-9).all(), w
            assert (cur[:, dn] <= prev[:, dn] + 1e-9).all(), w
            prev = cur

    def test_fit_cannot_sharpen_even_when_sharpening_would_win(self):
        """RED-proof of the clamp: outcomes far TIGHTER than the bank make sharpening optimal;
        the fit must still return exactly 1.0 (the grid is the clamp). The same fit offered an
        unclamped grid RETURNS a sharpening w — proving the clamp is load-bearing, not
        decorative (the mutation lands and changes the answer)."""
        rng = np.random.default_rng(7)
        q39 = _bank(400, scale=8.0, rng=rng)
        y = q39[:, MC.IDX_Q39.searchsorted(len(WP.Q_LEVELS) // 2)] * 0 + \
            q39.mean(axis=1) + rng.normal(0, 0.5, 400)  # far tighter than the bank
        assert MC.fit_level_widen(q39, y) == 1.0
        w_unclamped = MC.fit_level_widen(q39, y, grid=(0.4, 0.7, 1.0, 1.3))
        assert w_unclamped < 1.0, "the unclamped grid must sharpen here, else this proves nothing"

    def test_fit_widens_on_genuinely_underdispersed_banks(self):
        rng = np.random.default_rng(8)
        q39 = _bank(400, scale=3.0, rng=rng)
        y = q39.mean(axis=1) + rng.normal(0, 9.0, 400)  # reality much wider than the bank
        assert MC.fit_level_widen(q39, y) > 1.0


# ── The nonparametric recal map ─────────────────────────────────────────────────────────────────
class TestRecalMap:
    def test_recovers_calibration_on_an_underdispersed_predictive(self):
        """True X ~ N(0,2) scored by N(0,1) quantile banks: the map fit on a calibration sample
        must widen the predictive and repair coverage(80) toward nominal on held-out rows."""
        from scipy.stats import norm
        rng = np.random.default_rng(11)
        n_cal, n_te = 4000, 4000
        q39 = np.tile(norm.ppf(WP.Q_LEVELS)[None, :], (n_cal + n_te, 1))
        y = rng.normal(0, 2.0, n_cal + n_te)
        u_cal = MC.randomized_pit(q39[:n_cal], y[:n_cal], rng)
        params = MC.fit_recal_levels(u_cal)
        bank = MC.build_eval_bank("pit_recal_pos", params, q39[n_cal:])
        inc = MC.build_eval_bank("incumbent", None, q39[n_cal:])
        sc_arm = MC.score_bank(bank, y[n_cal:])
        sc_inc = MC.score_bank(inc, y[n_cal:])
        assert abs(sc_arm["coverage_80"] - 0.80) < abs(sc_inc["coverage_80"] - 0.80)
        assert sc_arm["crps_q199"] < sc_inc["crps_q199"]

    def test_refuses_a_thin_fit(self):
        with pytest.raises(ValueError, match="refusing"):
            MC.fit_recal_levels(np.array([0.5] * 10))

    def test_zscore_affine_recovers_the_analytic_var_z(self):
        from scipy.stats import norm
        rng = np.random.default_rng(12)
        u = norm.cdf(rng.normal(0.2, 1.5, 20000))  # z has mu .2, sigma 1.5
        prm = MC.fit_zscore_affine(u)
        assert abs(prm["mu"] - 0.2) < 0.05 and abs(prm["sigma"] - 1.5) < 0.05

    def test_the_permutation_substrate_preserves_group_multisets(self):
        rng = np.random.default_rng(13)
        cal = pd.DataFrame({
            "position": rng.choice(["QB", "RB"], 300),
            "gw": rng.integers(1, 5, 300),
            "fantasy_points": rng.normal(10, 5, 300),
        })
        y_perm = MC.permute_within_pos_week(cal, rng)
        moved = int((y_perm != cal["fantasy_points"].to_numpy()).sum())
        assert moved > 50, "the permutation must actually move outcomes"
        for (_, _), sub in cal.groupby(["position", "gw"]):
            a = np.sort(sub["fantasy_points"].to_numpy())
            b = np.sort(y_perm[sub.index.to_numpy()])
            assert np.allclose(a, b), "a group's multiset must be preserved"


# ── Tails ───────────────────────────────────────────────────────────────────────────────────────
class TestTails:
    def test_mean_excess_recovers_an_exponential_scale(self):
        rng = np.random.default_rng(21)
        n = 20000
        q39 = _bank(n, loc=0.0, scale=1.0, rng=rng)
        beta_true = 4.0
        y = q39[:, -1] + rng.exponential(beta_true, n)  # every row exceeds the top
        tail = MC.fit_tail_betas(q39, y)
        assert abs(tail["beta_hi"] - beta_true) < 0.15
        assert not tail["thin_hi"]

    def test_a_thin_side_collapses_loudly_to_zero(self):
        rng = np.random.default_rng(22)
        q39 = _bank(500, rng=rng)
        y = q39[:, 20]  # interior everywhere: zero exceedances both sides
        tail = MC.fit_tail_betas(q39, y)
        assert tail["beta_hi"] == 0.0 and tail["beta_lo"] == 0.0
        assert tail["thin_hi"] and tail["thin_lo"]

    def test_extension_is_continuous_at_the_grid_end_and_beyond_it(self):
        q39 = _bank(20)
        u = np.sort(np.concatenate([_RNG.random(3000), np.full(400, 0.999)]))
        g = MC.recal_levels_g(MC.fit_recal_levels(u))
        tail = {"beta_hi": 3.0, "beta_lo": 1.0, "n_hi": 99, "n_lo": 99}
        with_tail = MC.apply_level_map(q39, g, tail=tail)
        without = MC.apply_level_map(q39, g)
        above, below = g > WP.Q_LEVELS[-1], g < WP.Q_LEVELS[0]
        assert above.any(), "fixture must actually engage the upper tail"
        inside = ~(above | below)
        assert (with_tail[:, above] > without[:, above] - 1e-12).all()
        assert (with_tail[:, below] <= without[:, below] + 1e-12).all()
        assert np.allclose(with_tail[:, inside], without[:, inside], atol=1e-12)

    def test_tail_only_channel_is_visible_to_the_primary_metric(self):
        """The reason the eval grid is 199 levels: an arm that ONLY models beyond-grid tails
        must be distinguishable from the incumbent on the selection metric."""
        rng = np.random.default_rng(23)
        n = 6000
        q39 = _bank(n, scale=2.0, rng=rng)
        y = q39.mean(axis=1) + rng.standard_t(3, n) * 4.0  # fat-tailed reality
        g = MC.EVAL_LEVELS.copy()
        tail = {"beta_hi": 6.0, "beta_lo": 6.0, "n_hi": 99, "n_lo": 99}
        crps_tail = MC.score_bank(MC.apply_level_map(q39, g, tail=tail), y)["crps_q199"]
        crps_flat = MC.score_bank(MC.apply_level_map(q39, g), y)["crps_q199"]
        assert crps_tail < crps_flat, (
            "a correct tail extension must beat the flat clamp on crps_q199")


# ── Scoring ─────────────────────────────────────────────────────────────────────────────────────
class TestScoring:
    def test_crps_q199_matches_sample_crps_on_a_smooth_case(self):
        from scipy.stats import norm
        q39 = np.tile(norm.ppf(WP.Q_LEVELS, scale=3.0)[None, :], (1, 1))
        bank = MC.build_eval_bank("incumbent", None, q39)
        y = 1.7
        samples = np.interp(np.random.default_rng(31).random(200_000),
                            MC.EVAL_LEVELS, bank[0])
        approx = OA.crps_sample(samples, y)
        exact = float(WP.crps_from_quantiles(bank, np.array([y]), MC.EVAL_LEVELS)[0])
        assert abs(approx - exact) < 0.02

    def test_winkler_hand_case(self):
        q = np.linspace(0.0, 10.0, len(MC.EVAL_LEVELS))[None, :]
        lo, hi = q[0, MC._I10], q[0, MC._I90]
        inside = MC.winkler_80(q, np.array([(lo + hi) / 2]))[0]
        assert abs(inside - (hi - lo)) < 1e-9
        above = MC.winkler_80(q, np.array([hi + 2.0]))[0]
        assert abs(above - ((hi - lo) + 10.0 * 2.0)) < 1e-9

    def test_reducer_refuses_a_non_finite_bank(self):
        q39 = _bank(10)
        bank = MC.build_eval_bank("incumbent", None, q39)
        bank[3, 5] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            MC.score_bank(bank, np.zeros(10))

    def test_zero_width_and_max_width_bracket_sharpness(self):
        """NF1.7 (c) two-sided degenerates + the NF1.8 floor proof: max_width must SATISFY the
        coverage floor while LOSING both proper scores to the incumbent."""
        rng = np.random.default_rng(32)
        n = 4000
        q39 = _bank(n, scale=5.0, rng=rng)
        y = q39.mean(axis=1) + rng.normal(0, 5.0, n)
        sc = {lab: MC.score_bank(MC.build_eval_bank(lab, None, q39), y)
              for lab in ("incumbent", "zero_width", "max_width")}
        assert sc["zero_width"]["crps_q199"] > sc["incumbent"]["crps_q199"]
        assert sc["max_width"]["crps_q199"] > sc["incumbent"]["crps_q199"]
        assert sc["max_width"]["winkler_80"] > sc["incumbent"]["winkler_80"]
        assert sc["max_width"]["coverage_80"] >= MC.COVERAGE_FLOOR, (
            "the degenerate must SATISFY the floor — that is what proves the floor is a "
            "constraint, not a criterion (NF1.8)")


# ── PIT accounting ──────────────────────────────────────────────────────────────────────────────
class TestPitAccounting:
    def test_pooling_equals_stats_of_the_concatenation(self):
        rng = np.random.default_rng(41)
        parts = [rng.random(500), rng.random(700), rng.beta(2, 5, 300)]
        pooled = MC.pool_pit_stats([MC.pit_stats(p) for p in parts])
        direct = MC.pit_stats(np.concatenate(parts))
        n = pooled["n"]
        assert n == direct["n"]
        assert np.allclose(pooled["decile_freq"],  # report values round to 5 decimals
                           np.asarray(direct["decile_counts"]) / n, atol=1e-5)
        assert abs(pooled["var_z"]
                   - (direct["sum_z2"] / n - (direct["sum_z"] / n) ** 2)) < 1e-4

    def test_beyond_grid_mass_reads_the_truncation(self):
        u = np.concatenate([np.full(100, 0.99), np.full(100, 0.01), np.full(800, 0.5)])
        s = MC.pit_stats(u)
        assert s["n_above_grid"] == 100 and s["n_below_grid"] == 100

    def test_calibration_split_respects_the_purge_gap(self):
        train = pd.DataFrame({"gw": np.repeat(np.arange(1, 41), 300),
                              "fantasy_points": 0.0})
        core, cal, note = MC.calibration_split(train)
        assert core["gw"].max() <= cal["gw"].min() - 1 - MC.PURGE_WEEKS
        assert note["n_cal"] >= MC.CAL_MIN_ROWS
        with pytest.raises(ValueError, match="degenerate"):
            MC.calibration_split(train[train["gw"] <= 2])


# ── Gate clauses (isolating fixtures — NF-D17) ──────────────────────────────────────────────────
def _passing_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"passes": True},
        "pbo": 0.05, "dsr": 0.99,
        "anchors": {"zero_width_loses": True, "max_width_loses": True,
                    "winner_beats_permuted": True, "permuted_lift_not_significant": True,
                    "oracle_floors_respected_at_matched_n": True},
        "coverage": {"blocking_shortfall": False},
        "calibration": {"winkler_delta_vs_incumbent": 0.05,
                        "flatness_delta_vs_incumbent": 0.01},
    }


class TestGateClauses:
    def test_the_passing_fixture_ships(self):
        gate = MC.compose_gate_margin(_passing_sel(), True)
        assert gate["ship"], gate["checks"]

    @pytest.mark.parametrize("mutate,expect_check", [
        (lambda s: s.update(beats_foil=False), "beats_foil"),
        (lambda s: s["fold_clause"].update(passes=False), "fold_consistency"),
        (lambda s: s.update(pbo=0.5), "pbo_ok"),
        (lambda s: s.update(pbo=None), "pbo_ok"),
        (lambda s: s.update(dsr=0.5), "dsr_ok"),
        (lambda s: s.update(dsr=None), "dsr_ok"),
        (lambda s: s["anchors"].update(zero_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(max_width_loses=False), "degenerates_lose"),
        (lambda s: s["anchors"].update(winner_beats_permuted=False), "permutation_behaves"),
        (lambda s: s["anchors"].update(permuted_lift_not_significant=False),
         "permutation_behaves"),
        (lambda s: s["anchors"].update(oracle_floors_respected_at_matched_n=False),
         "oracle_floors_respected"),
        (lambda s: s["coverage"].update(blocking_shortfall=True), "coverage_floor_ok"),
        (lambda s: s["calibration"].update(winkler_delta_vs_incumbent=-0.01),
         "interval_score_improves"),
        (lambda s: s["calibration"].update(flatness_delta_vs_incumbent=-0.01),
         "pit_flatness_improves"),
    ])
    def test_each_clause_flips_only_itself(self, mutate, expect_check):
        sel = _passing_sel()
        mutate(sel)
        gate = MC.compose_gate_margin(sel, True)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == [expect_check], (
            f"mutation must flip exactly `{expect_check}`, flipped {failed} — a fixture that "
            f"trips several clauses proves none of them (NF-D17)")
        assert not gate["ship"]

    def test_fdr_clause_flips_only_fdr(self):
        gate = MC.compose_gate_margin(_passing_sel(), False)
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == ["fdr_ok"]

    def test_anchor_only_refusal_is_constraint_refused(self):
        sel = _passing_sel()
        sel["anchors"]["oracle_floors_respected_at_matched_n"] = False
        checks = MC.compose_gate_margin(sel, True)["checks"]
        verdict = MC.hand_classify_refusal_margin(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert verdict["retest_trigger"] is None

    def test_calibration_only_refusal_is_constraint_refused_and_named(self):
        sel = _passing_sel()
        sel["calibration"]["winkler_delta_vs_incumbent"] = -0.02
        checks = MC.compose_gate_margin(sel, True)["checks"]
        verdict = MC.hand_classify_refusal_margin(checks)
        assert verdict is not None and verdict["state"] == "CONSTRAINT_REFUSED"
        assert "interval_score_improves" in verdict["failing_anchor_checks"]

    def test_statistical_refusal_delegates_to_the_instrument(self):
        sel = _passing_sel()
        sel["beats_foil"] = False
        checks = MC.compose_gate_margin(sel, True)["checks"]
        assert MC.hand_classify_refusal_margin(checks) is None
