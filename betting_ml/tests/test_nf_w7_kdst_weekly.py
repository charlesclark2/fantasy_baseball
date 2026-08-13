"""Guards for NF-W7 (`kdst_weekly.py` + its runner) — weekly K/DST projections with exact tier
scoring as expected-bucket probabilities.

Discipline carried from the NF-W line:
  · every AND-composed gate clause has its own ISOLATING fixture (NF-D17 — a fixture that trips
    two clauses proves neither);
  · every source-inspection RED-proof asserts its mutation LANDED before asserting the guard
    fires (E11.24 #682 — a red-proof that can silently no-op reports a false catch);
  · iterating guards assert NON-VACUITY first (an empty match set passes on nothing — the
    DSR-CONV #690 lesson);
  · fast gate: imports `kdst_weekly` (pure) and the runner's CONSTANTS only — no lake IO, no
    `pipeline`, no network.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import kdst_weekly as KW
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP

_FANTASY = Path(KW.__file__).resolve().parent
_RUNNER = _FANTASY / "run_nf_w7_kdst_weekly.py"


# ── Pre-registration pins ───────────────────────────────────────────────────────────────────────
class TestPreregistrationPins:
    def test_fold_axis_is_the_nf_w1_axis_verbatim(self):
        assert KW.TEST_BLOCKS == WP.TEST_BLOCKS
        assert KW.PURGE_WEEKS == WP.PURGE_WEEKS

    def test_selection_is_the_dense_grid_never_the_39_level(self):
        assert KW.SELECTION_METRIC == "crps_q199"
        assert len(KW.EVAL_LEVELS) == 199

    def test_every_leg_declares_arms_a_foil_and_a_proper_metric(self):
        assert len(KW.ALL_LEGS) == 12  # non-vacuity for the loops below
        for leg in KW.ALL_LEGS:
            assert len(KW.REAL_ARMS[leg]) >= 2, leg
            assert len(KW.FOILS[leg]) >= 1, leg
            assert KW.LEG_METRIC[leg] in ("crps_q199", "log_loss", "log_loss_multiclass", "rps")
            assert leg in KW.PERMUTED_FAMILY

    def test_only_the_rare_legs_carry_the_thin_two_arm_family(self):
        for leg in KW.ALL_LEGS:
            if leg in KW.RARE_LEGS:
                assert len(KW.REAL_ARMS[leg]) == 2, leg  # the declared scope-note trade
            else:
                assert len(KW.REAL_ARMS[leg]) >= 3, leg  # the §0.5 minimum

    def test_bucket_legs_score_rps_never_a_point_metric(self):
        for leg in KW.BUCKET_LEGS:
            assert KW.LEG_METRIC[leg] == "rps"

    def test_layer_b_eligible_field_is_frozen(self):
        assert KW.LAYER_B_ELIGIBLE == ("assembled", "foil_climatology", "foil_board_eb",
                                       "foil_direct")
        assert set(KW.FDR_FAMILIES) == {"component", "downstream"}
        assert KW.FDR_FAMILIES["component"] == KW.ALL_LEGS
        assert KW.FDR_FAMILIES["downstream"] == KW.LAYER_B_TARGETS

    def test_tier_tables_are_nf1_6s_verbatim(self):
        from quant_sports_intel_models.football.nfl.fantasy import kdst_projection as KP
        assert KW.PA_EDGES == KP.PA_BUCKET_EDGES
        assert KW.YA_EDGES == KP.YA_BUCKET_EDGES
        assert KW.PA_TIER_POINTS == tuple(KP.DST_PA_TIER_POINTS[b] for b in KP.PA_BUCKET_LABELS)


# ── Provenance: one isolating fixture per clause (NF-D17) ───────────────────────────────────────
class TestProvenanceClauses:
    def test_clean_features_pass(self):
        KW.assert_feature_provenance_w7(KW.FEATURES_K)
        KW.assert_feature_provenance_w7(KW.FEATURES_D)

    def test_unknown_family_rejected_alone(self):
        # a name failing ONLY the family clause: no leaky/era/banned token in it
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            KW.assert_feature_provenance_w7(("made_up_family__points_l4",))

    def test_leaky_token_rejected_alone(self):
        tok = WF.LEAKY_COLUMNS[0]
        with pytest.raises(WF.LeakageError, match="leaky"):
            KW.assert_feature_provenance_w7((f"team_environment__{tok}",))

    def test_era_token_rejected_alone(self):
        tok = KW.ERA_FORBIDDEN_TOKENS[0]
        with pytest.raises(WF.LeakageError, match="participation-era"):
            KW.assert_feature_provenance_w7((f"team_environment__x_{tok}_l4",))

    def test_weather_token_rejected_alone(self):
        with pytest.raises(WF.LeakageError, match="deferred-contract"):
            KW.assert_feature_provenance_w7(("game_context__temp_l4",))

    def test_no_declared_feature_smuggles_weather_or_markets(self):
        all_feats = (KW.FEATURES_K + KW.FEATURES_D + KW.FEATURES_MAKE + KW.FEATURES_BAND)
        assert len(all_feats) > 30  # non-vacuity
        for c in all_feats:
            assert not any(tok in c for tok in KW.BANNED_SOURCE_TOKENS), c
            assert not any(tok in c for tok in KW.ERA_FORBIDDEN_TOKENS), c


# ── The SQL scan (identifier-boundary, comment-stripped) ────────────────────────────────────────
class TestSourceQueryScan:
    def test_attempt_is_not_temp(self):
        # the measured first-smoke failure: GE's substring scan dies on 'field_goal_attempt'
        KW.assert_source_query_is_clean("select field_goal_attempt, extra_point_attempt from x")

    def test_weather_read_rejected(self):
        with pytest.raises(WF.LeakageError, match="temp"):
            KW.assert_source_query_is_clean("select temp from x")

    def test_market_read_rejected(self):
        with pytest.raises(WF.LeakageError, match="spread_line"):
            KW.assert_source_query_is_clean("select spread_line from x")

    def test_a_comment_cannot_trip_it(self):
        KW.assert_source_query_is_clean("select a from x -- temp and wind discussed in prose")

    def test_a_comment_cannot_satisfy_it(self):
        with pytest.raises(WF.LeakageError):
            KW.assert_source_query_is_clean("select temp from x -- this query is clean, honest")

    def test_runner_sql_literals_are_scanned_and_clean(self):
        src = _RUNNER.read_text()
        names = re.findall(r"^([A-Z_]+_SQL) = ", src, flags=re.M)
        assert len(names) >= 6, "runner SQL constants vanished — the scan would be vacuous"
        import importlib
        runner_ns = {}
        tree = ast.parse(src)
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                    and node.targets[0].id.endswith("_SQL")):
                runner_ns[node.targets[0].id] = ast.literal_eval(node.value)
        assert set(runner_ns) == set(names)
        for name, sql in runner_ns.items():
            KW.assert_source_query_is_clean(sql)

    def test_red_proof_scan_fires_on_a_poisoned_runner_sql(self):
        """The scan must FAIL on broken source — and the break must be PROVEN to land."""
        src = _RUNNER.read_text()
        assert "from {pbp}" in src  # the mutation site exists
        marker = ", temp, wind from {pbp}"
        poisoned = src.replace("from {pbp}", marker, 1)
        assert poisoned != src and marker in poisoned, (
            "mutation did not land — the red-proof would be vacuous")
        blocks = re.findall(r'_SQL = """(.*?)"""', poisoned, flags=re.S)
        broken = [b for b in blocks if marker in b]
        assert len(broken) == 1, "the poisoned SQL block was not recovered — vacuous red-proof"
        broken = broken[0]
        assert re.search(r"(?<![a-z0-9_])temp(?![a-z0-9_])", broken)
        with pytest.raises(WF.LeakageError):
            KW.assert_source_query_is_clean(broken)


# ── Dense banks + tails (the NF-MARGIN1 inheritance) ────────────────────────────────────────────
class TestDenseBanks:
    def test_count_bank_matches_scipy_ppf_exactly(self):
        from scipy.stats import poisson
        mu = np.array([0.5, 2.0, 7.3])
        bank = KW.poisson_bank(mu)
        expect = poisson.ppf(KW.EVAL_LEVELS[None, :], mu[:, None])
        np.testing.assert_array_equal(bank, expect)

    def test_knot_bank_extends_beyond_the_end_knot_when_tail_is_fit(self):
        knots = np.tile(np.linspace(0.0, 10.0, 9), (3, 1))
        bank = KW.dense_bank_from_knots(knots, {"beta_hi": 2.0, "beta_lo": 1.0}, clip_lo=None)
        # ⛔ the flat-extension defect: q(0.995) must sit strictly ABOVE the 0.95 knot
        assert (bank[:, -1] > knots[:, -1] + 1e-9).all()
        assert (bank[:, 0] < knots[:, 0] - 1e-9).all()
        assert (np.diff(np.sort(bank, axis=1), axis=1) >= -1e-9).all()

    def test_zero_beta_degrades_to_the_flat_end_and_is_counted(self):
        knots = np.tile(np.linspace(0.0, 10.0, 9), (2, 1))
        bank = KW.dense_bank_from_knots(knots, {"beta_hi": 0.0, "beta_lo": 0.0}, clip_lo=None)
        assert (bank[:, -1] == knots[:, -1]).all()
        thin = KW.fit_knot_tail_betas(knots[:1], np.array([5.0]))
        assert thin["thin_hi"] and thin["beta_hi"] == 0.0  # counted, never silent (NF1.7 (a))

    def test_tail_betas_are_the_mean_excess(self):
        knots = np.tile(np.linspace(0.0, 10.0, 9), (30, 1))
        y = np.full(30, 5.0)
        y[:12] = 14.0  # 12 exceedances of 4.0 beyond the top knot
        tail = KW.fit_knot_tail_betas(knots, y)
        assert tail["n_hi"] == 12 and abs(tail["beta_hi"] - 4.0) < 1e-9

    def test_finite_predictive_refusal(self):
        bad = np.ones((2, 199))
        bad[0, 5] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            KW.assert_finite_predictive(bad, "x")


# ── Exact tier scoring (§4A.3 — the core discipline) ────────────────────────────────────────────
class TestExactTierScoring:
    def test_expected_points_is_linear_in_bucket_probabilities(self):
        n_b = len(KW.PA_TIER_POINTS)
        for b in range(n_b):
            p = np.full((1, n_b), 1e-12)
            p[0, b] = 1.0
            assert abs(KW.expected_tier_points(p)[0] - KW.PA_TIER_POINTS[b]) < 1e-6
        mix = np.zeros((1, n_b))
        mix[0, 0], mix[0, -1] = 0.25, 0.75
        expect = 0.25 * KW.PA_TIER_POINTS[0] + 0.75 * KW.PA_TIER_POINTS[-1]
        assert abs(KW.expected_tier_points(mix)[0] - expect) < 1e-6

    def test_assembly_draws_the_bucket_and_scores_it_exactly(self):
        """⛔ no point estimate crosses the tier table: a point-mass bucket probability must
        produce EXACTLY that bucket's tier points in every draw."""
        n = 2
        zero_counts = {leg: np.zeros((n, 199)) for leg in KW.DST_LINEAR_POINTS}
        for b, pts in ((0, KW.PA_TIER_POINTS[0]), (8, KW.PA_TIER_POINTS[8])):
            proba = np.full((n, 9), 1e-12)
            proba[:, b] = 1.0
            bank = KW.assemble_dst_bank(zero_counts, proba, draws=64)
            assert np.allclose(bank, pts), f"bucket {b} must score exactly {pts}"

    def test_bucket_index_edges_are_inclusive_lower_bounds(self):
        assert KW.bucket_index(np.array([0]), KW.PA_EDGES)[0] == 0      # shutout
        assert KW.bucket_index(np.array([1]), KW.PA_EDGES)[0] == 1
        assert KW.bucket_index(np.array([46]), KW.PA_EDGES)[0] == 8
        assert KW.bucket_index(np.array([99]), KW.YA_EDGES)[0] == 0
        assert KW.bucket_index(np.array([100]), KW.YA_EDGES)[0] == 1    # the disclosed boundary

    def test_k_assembly_scoring_map(self):
        """Deterministic chain: 2 attempts all in one band, always made, no XP → exactly
        2 × that band's points. Moving the band moves the points (the RED half)."""
        n = 1
        att = np.full((n, 199), 2.0)
        xp = np.zeros((n, 199))
        make = np.ones((n, 3))
        for b, per in enumerate(KW.BAND_POINTS):
            p_band = np.full((n, 3), 1e-12)
            p_band[:, b] = 1.0
            bank = KW.assemble_k_bank(att, xp, p_band, make, 0.0, draws=64)
            assert np.allclose(bank, 2 * per), f"band {b}"

    def test_band_split_conserves_attempts(self):
        rng = np.random.default_rng(0)
        att = rng.integers(0, 8, size=(50, 200)).astype(float)
        n0, n1, n2 = KW._split_bands(att, np.tile([0.5, 0.3, 0.2], (50, 1)), rng)
        np.testing.assert_array_equal(n0 + n1 + n2, att.astype(int))


# ── Proper scores ───────────────────────────────────────────────────────────────────────────────
class TestProperScores:
    def test_rps_orders_point_mass_truth_below_climatology_below_far_wrong(self):
        y = np.array([4])
        perfect = KW.anchor_point_mass((1, 9), 4)
        far = KW.anchor_point_mass((1, 9), 0)
        uniform = KW.anchor_uniform((1, 9))
        s = [KW.rps(p, y)[0] for p in (perfect, far, uniform)]
        assert s[0] < s[2] < s[1]

    def test_log_losses_are_proper_at_the_edge(self):
        assert KW.log_loss_binary(np.array([0.999]), np.array([1.0]))[0] < \
               KW.log_loss_binary(np.array([0.5]), np.array([1.0]))[0]
        p = np.array([[0.8, 0.1, 0.1]])
        assert KW.log_loss_multiclass(p, np.array([0]))[0] < \
               KW.log_loss_multiclass(p, np.array([2]))[0]

    def test_randomized_pit_is_flat_on_a_calibrated_bank(self):
        rng = np.random.default_rng(1)
        y = rng.normal(0, 1, 4000)
        from scipy.stats import norm
        bank = np.tile(norm.ppf(KW.EVAL_LEVELS), (4000, 1))
        flat = KW.pit_flatness(KW.randomized_pit_from_bank(bank, y))
        assert flat["max_decile_dev"] < 0.03
        # RED: a half-width (over-sharp) bank must NOT read flat
        broken = KW.pit_flatness(KW.randomized_pit_from_bank(bank * 0.5, y))
        assert broken["max_decile_dev"] > 0.05

    def test_coverage_floor_two_sided(self):
        rng = np.random.default_rng(2)
        y = rng.normal(0, 1, 3000)
        from scipy.stats import norm
        good = np.tile(norm.ppf(KW.EVAL_LEVELS), (3000, 1))
        assert not KW.coverage80_dense(good, y)["blocking_shortfall"]
        assert KW.coverage80_dense(good * 0.4, y)["blocking_shortfall"]


# ── EB + permutation mechanics ──────────────────────────────────────────────────────────────────
class TestMechanics:
    def _frame(self, prior, prior_g, s2d, wk):
        return pd.DataFrame({
            "p": [prior], "g": [prior_g], "s": [s2d], "game_context__week_index": [wk]})

    def test_entity_eb_shrinks_to_league_with_no_history(self):
        df = self._frame(np.nan, 0.0, np.nan, 1.0)
        r = KW.entity_eb_rate(df, "p", "g", "s", "game_context__week_index", 2.5)
        assert abs(r[0] - 2.5) < 1e-9

    def test_entity_eb_approaches_entity_rate_with_long_history(self):
        df = self._frame(5.0, 1000.0, np.nan, 1.0)
        r = KW.entity_eb_rate(df, "p", "g", "s", "game_context__week_index", 2.5)
        assert abs(r[0] - 5.0) < 0.05

    def test_permute_within_group_preserves_group_multisets(self):
        y = np.array([1, 2, 3, 10, 20, 30])
        g = np.array([0, 0, 0, 1, 1, 1])
        out = KW.permute_within_group(y, g, seed=7)
        assert sorted(out[:3]) == [1, 2, 3] and sorted(out[3:]) == [10, 20, 30]

    def test_expand_proba_restores_absent_classes(self):
        p = np.array([[0.7, 0.3]])
        out = KW._expand_proba(p, np.array([0, 2]), 4)
        assert out.shape == (1, 4) and abs(out.sum() - 1.0) < 1e-9
        assert out[0, 1] < 1e-4 and out[0, 3] < 1e-4


# ── Gate composition: one isolating break per clause (NF-D17) ───────────────────────────────────
_GREEN_SEL = {
    "beats_foil": True,
    "fold_clause": {"passes": True},
    "pbo": 0.0,
    "dsr": 1.0,
    "anchors": {"degenerates_lose": True, "winner_beats_permuted": True,
                "permuted_lift_not_significant": True,
                "oracle_floors_respected_at_matched_n": True},
    "coverage": {"blocking_shortfall": False},
}


def _broken(path: str, value):
    import copy
    sel = copy.deepcopy(_GREEN_SEL)
    node = sel
    parts = path.split(".")
    for k in parts[:-1]:
        node = node[k]
    node[parts[-1]] = value
    return sel


class TestGateClauses:
    def test_green_fixture_ships(self):
        gate = KW.compose_gate(_GREEN_SEL, True, coverage=True)
        assert gate["ship"] and all(gate["checks"].values())

    @pytest.mark.parametrize("path,value,check", [
        ("beats_foil", False, "beats_foil"),
        ("fold_clause.passes", False, "fold_consistency"),
        ("pbo", 0.5, "pbo_ok"),
        ("pbo", None, "pbo_ok"),
        ("dsr", 0.5, "dsr_ok"),
        ("dsr", None, "dsr_ok"),
        ("anchors.degenerates_lose", False, "degenerates_lose"),
        ("anchors.winner_beats_permuted", False, "permutation_behaves"),
        ("anchors.permuted_lift_not_significant", False, "permutation_behaves"),
        ("anchors.oracle_floors_respected_at_matched_n", False, "oracle_floors_respected"),
        ("coverage.blocking_shortfall", True, "coverage_floor_ok"),
    ])
    def test_each_clause_refuses_alone(self, path, value, check):
        gate = KW.compose_gate(_broken(path, value), True, coverage=True)
        assert not gate["ship"]
        assert not gate["checks"][check]
        others = {k: v for k, v in gate["checks"].items() if k != check}
        assert all(others.values()), f"fixture for `{check}` tripped {others} too (NF-D17)"

    def test_fdr_clause_refuses_alone(self):
        gate = KW.compose_gate(_GREEN_SEL, False, coverage=True)
        assert not gate["ship"] and not gate["checks"]["fdr_ok"]
        assert all(v for k, v in gate["checks"].items() if k != "fdr_ok")


# ── Deploy-held (AST — a docstring mention cannot trip or satisfy a substring scan) ─────────────
class TestDeployHeld:
    @pytest.mark.parametrize("path", [Path(KW.__file__), _RUNNER])
    def test_no_serving_or_upload_imports(self, path):
        tree = ast.parse(path.read_text())
        imports = [n.names[0].name.split(".")[0] for n in ast.walk(tree)
                   if isinstance(n, ast.Import)]
        imports += [n.module.split(".")[0] for n in ast.walk(tree)
                    if isinstance(n, ast.ImportFrom) and n.module]
        assert len(imports) > 3  # non-vacuity
        for banned in ("boto3", "requests", "snowflake"):
            assert banned not in imports, f"{path.name} imports {banned} — deploy-held story"

    def test_no_write_outside_research_artifacts(self):
        src = _RUNNER.read_text()
        writes = re.findall(r"\.to_parquet\(|write_text\(", src)
        assert len(writes) >= 3  # non-vacuity: the runner does write its artifacts
        assert "write_serving_store" not in src
        assert "deploy" not in Path(KW.__file__).read_text().replace("deploy-held", "")


# ── The known-instrument wrapper ────────────────────────────────────────────────────────────────
class TestClassifierWrapper:
    def test_layer_b_pbo_state_is_declared_evaluable_here(self):
        """NF-W7's Layer B fields a 4-config eligible set, unlike NF-W3's — the wrapper must not
        inherit GE's 'PBO UNDEFINED' prose."""
        src = _RUNNER.read_text()
        m = re.search(r'out\["pbo_state"\] = \(\s*"([^"]+)', src)
        assert m and m.group(1).startswith("EVALUABLE"), (
            "the Layer-B classifier wrapper must override GE's single-arm PBO prose — this "
            "story's eligible field has 4 configs")
