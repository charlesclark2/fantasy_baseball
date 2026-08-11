"""NF-W4 guards — the availability & playing-time mixture.

Discipline carried from the NF-W family, applied here:
  · every RED-proof mutates the source IN-PROCESS and ASSERTS THE MUTATION LANDED before running
    the guard (E11.24 #682);
  · every guard that ITERATES over matches asserts NON-VACUITY (NF1.7 (a) / INC-38);
  · every clause of an AND-composed rule gets its OWN ISOLATING fixture, satisfying every other
    clause, so only the clause under test can flip the result (NF-D17);
  · source-inspection guards strip comments first so PROSE can neither satisfy nor trip them
    (INC-38).
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import availability_mixture as AV
from quant_sports_intel_models.football.nfl.fantasy import weekly_frame as WF
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection as WP
from quant_sports_intel_models.football.nfl.fantasy import weekly_projection_w2b as W2B

_MODULE = Path(AV.__file__)
_RUNNER = _MODULE.parent / "run_nf_w4_availability_bakeoff.py"
_PREREG = _MODULE.parent / "ablation_results" / "nf_w4_preregistration.md"
_W2D_ARTIFACT = _MODULE.parent / "ablation_results" / "nf_w2d_2025_regate.json"


def _mutated(path: Path, old: str, new: str, name: str):
    """Load `path` with one deliberate break applied — asserting the break LANDED first."""
    src = path.read_text()
    assert old in src, f"RED-proof target not found in {path.name}: {old!r}"
    mutated = src.replace(old, new, 1)
    assert mutated != src, "the mutation did not change the source — the RED-proof would no-op"
    mod = types.ModuleType(name)
    mod.__file__ = str(path)
    exec(compile(mutated, str(path), "exec"), mod.__dict__)  # noqa: S102 — test harness
    return mod


def _stripped_source(path: Path) -> str:
    """Comment-stripped source, so a prose mention can neither satisfy nor trip a check."""
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text().splitlines())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 1. Provenance — five clauses, five ISOLATING fixtures (NF-D17)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestProvenanceClausesAreIndependentlyRedProvable:
    def test_the_real_feature_lists_pass_and_are_not_empty(self):
        assert len(AV.AVAIL_FEATURES) > 0 and len(AV.AVAIL_PROJ_FEATURES) > 0
        AV.assert_feature_provenance_w4(AV.AVAIL_FEATURES)
        AV.assert_feature_provenance_w4(AV.AVAIL_PROJ_FEATURES)

    def test_target_leak_by_exact_name_is_rejected_before_the_prefix_clause(self):
        """ISOLATING for the ordering itself: `status` has no family separator, so if the prefix
        clause ran first this would raise 'unknown provenance' — the target-leak clause would be
        DEAD for exact names (the NF-D17 vacuity shape)."""
        with pytest.raises(WF.LeakageError, match="target-leak"):
            AV.assert_feature_provenance_w4(["status"])
        with pytest.raises(WF.LeakageError, match="target-leak"):
            AV.assert_feature_provenance_w4(["label"])

    def test_target_leak_by_token_is_rejected(self):
        """ISOLATING: certified family, not leaky, no era/banned token — only the target-leak
        clause can fire."""
        col = "snap_share__offense_pct_now"
        assert col.split("__", 1)[0] in AV.USED_FAMILIES_W4
        assert not any(tok == col or col.endswith(f"_{tok}") or col.startswith(f"{tok}_")
                       for tok in WF.LEAKY_COLUMNS)
        assert not any(tok in col for tok in WP.ERA_FORBIDDEN_TOKENS)
        assert not any(tok in col for tok in AV.BANNED_FEATURE_TOKENS)
        with pytest.raises(WF.LeakageError, match="target-leak"):
            AV.assert_feature_provenance_w4([col])

    def test_unknown_family_is_rejected(self):
        col = "mystery_family__usage"
        assert not any(tok in col for tok in AV.BANNED_FEATURE_TOKENS)
        assert not any(tok in col for tok in AV.TARGET_LEAK_TOKENS)
        with pytest.raises(WF.LeakageError, match="unknown provenance"):
            AV.assert_feature_provenance_w4([col])

    def test_a_leaky_token_is_rejected_under_a_certified_family(self):
        col = "prior_week_box__home_score"
        assert col.split("__", 1)[0] in AV.USED_FAMILIES_W4
        assert not any(tok in col for tok in AV.BANNED_FEATURE_TOKENS)
        assert not any(tok in col for tok in AV.TARGET_LEAK_TOKENS)
        with pytest.raises(WF.LeakageError, match="leaky"):
            AV.assert_feature_provenance_w4([col])

    def test_a_participation_era_token_is_rejected(self):
        col = "opponent_matchup__pressure_rate_l4"
        assert col.split("__", 1)[0] in AV.USED_FAMILIES_W4
        assert not any(tok == col or col.endswith(f"_{tok}") or col.startswith(f"{tok}_")
                       for tok in WF.LEAKY_COLUMNS)
        assert not any(tok in col for tok in AV.BANNED_FEATURE_TOKENS)
        with pytest.raises(WF.LeakageError, match="participation-era"):
            AV.assert_feature_provenance_w4([col])

    def test_a_deferred_contract_source_is_rejected(self):
        """ISOLATING for clause 5 — incl. the story-specific game-day inactive ban."""
        for col in ("game_context__depth_chart_rank", "game_context__gameday_inactive_flag"):
            assert col.split("__", 1)[0] in AV.USED_FAMILIES_W4
            assert not any(tok == col or col.endswith(f"_{tok}") or col.startswith(f"{tok}_")
                           for tok in WF.LEAKY_COLUMNS)
            assert not any(tok in col for tok in WP.ERA_FORBIDDEN_TOKENS)
            assert not any(tok in col for tok in AV.TARGET_LEAK_TOKENS)
            with pytest.raises(WF.LeakageError, match="deferred-contract"):
                AV.assert_feature_provenance_w4([col])

    def test_red_proof_deleting_the_target_leak_clause_lets_the_snap_target_through(self):
        mod = _mutated(
            _MODULE,
            "target_leak = [c for c in cols\n"
            "                   if c in TARGET_LEAK_EXACT or any(tok in c for tok in "
            "TARGET_LEAK_TOKENS)]",
            "target_leak = []",
            "av_no_target_leak")
        mod.assert_feature_provenance_w4(["snap_share__offense_pct_now"])  # no raise
        with pytest.raises(WF.LeakageError):
            AV.assert_feature_provenance_w4(["snap_share__offense_pct_now"])

    def test_the_availability_projection_family_is_in_the_certified_contract(self):
        names = {s.name for s in WF.ALLOWED_FEATURE_CONTRACT}
        assert "availability_projection" in names


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 2. Targets: NULL-bearing share, counted exclusions, no byes
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _target_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "label": [WF.LABEL_PLAYED, WF.LABEL_PLAYED, WF.LABEL_INACTIVE, WF.LABEL_DRESSED_NO_STAT],
        "offense_pct": [0.8, np.nan, np.nan, np.nan],
        "position": ["RB", "WR", "QB", "TE"],
    })


class TestAvailabilityTargets:
    def test_played_collapses_the_label_and_share_stays_null_bearing(self):
        f = AV.attach_availability_targets(_target_frame())
        assert list(f["_t_played"]) == [1.0, 1.0, 0.0, 0.0]
        assert np.isnan(f["_t_share"].iloc[1]), "an unmeasured share must stay NaN — never 0"

    def test_a_played_but_unmeasured_row_is_excluded_and_counted(self):
        f = AV.attach_availability_targets(_target_frame())
        mask = AV.t2_mask(f)
        assert mask.tolist() == [True, False, False, False]
        counts = AV.t2_exclusion_counts(f)
        assert counts["n_played"] == 2 and counts["n_scored"] == 1
        assert counts["n_played_unmeasured_excluded"] == 1

    def test_a_bye_row_raises_instead_of_becoming_an_availability_outcome(self):
        f = _target_frame()
        f.loc[0, "label"] = WF.LABEL_BYE
        with pytest.raises(ValueError, match="bye"):
            AV.attach_availability_targets(f)

    def test_red_proof_a_fillna0_on_the_share_would_fabricate_a_scored_zero(self):
        mod = _mutated(
            _MODULE,
            'f["_t_share"] = pd.to_numeric(f["offense_pct"], errors="coerce").clip(0.0, 1.0)',
            'f["_t_share"] = pd.to_numeric(f["offense_pct"], errors="coerce")'
            '.fillna(0.0).clip(0.0, 1.0)',
            "av_fillna_share")
        f_bad = mod.attach_availability_targets(_target_frame())
        assert mod.t2_mask(f_bad).tolist() == [True, True, False, False], (
            "the mutation should fabricate a scored zero — otherwise this proves nothing")
        f_good = AV.attach_availability_targets(_target_frame())
        assert AV.t2_mask(f_good).tolist() == [True, False, False, False]


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 3. T1 scoring: exact CRPS closed forms; the reducer refuses a non-finite predictive
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestT1Scoring:
    def test_crps_bernoulli_is_the_exact_closed_form(self):
        p = np.array([0.2, 0.9, 0.5])
        y = np.array([0.0, 1.0, 1.0])
        assert np.allclose(AV.crps_bernoulli(p, y), [(0.2) ** 2, (0.1) ** 2, (0.5) ** 2])

    def test_crps_point_and_uniform_forms(self):
        assert np.allclose(AV.crps_point(np.array([0.3]), np.array([1.0])), [0.7])
        assert AV.CRPS_UNIFORM01 == pytest.approx(1.0 / 3.0)

    def test_the_reducer_refuses_a_non_finite_p(self):
        with pytest.raises(ValueError, match="non-finite"):
            AV.assert_finite_p(np.array([0.4, np.nan]), "some_arm")

    def test_the_t2_reducer_refuses_a_non_finite_predictive(self):
        q = np.full((2, len(AV.Q_LEVELS)), 0.5)
        q[1, 3] = np.nan
        with pytest.raises(ValueError, match="non-finite"):
            AV.assert_finite_predictive(q, "some_arm")

    def test_t1_coverage_declares_itself_structurally_inactive(self):
        cov = AV.t1_interval_coverage(np.array([0.5, 0.6]), np.array([1.0, 0.0]))
        assert cov["structurally_inactive"] is True
        assert cov["coverage"] == 1.0  # the two-point band spans {0,1} at interior p

    def test_two_stage_refuses_a_y_train_override(self):
        """The permutation anchor is pre-registered on the plain boosting class; two_stage
        decomposes the label column itself, so an override must refuse loudly."""
        with pytest.raises(ValueError, match="two_stage"):
            AV.fit_t1_two_stage(pd.DataFrame(), pd.DataFrame(), [], y_train=np.array([1.0]))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 4. Foils: climatology never 0-fills; thin lookup cells fall back LOUDLY (counted)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _foil_frame(n: int = 800, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    listed = rng.random(n) < 0.5
    out_ = listed & (rng.random(n) < 0.5)
    return pd.DataFrame({
        "position": np.tile(["QB", "RB", "WR", "TE"], n // 4),
        "prior_week_box__played_share_l4": np.where(rng.random(n) < 0.1, np.nan, rng.random(n)),
        "snap_share__l4_mean": np.where(rng.random(n) < 0.1, np.nan, rng.random(n)),
        "_t_played": np.where(out_, (rng.random(n) < 0.02).astype(float),
                              (rng.random(n) < 0.7).astype(float)),
        "_t_share": rng.random(n),
        "injury_report__observed": 1.0,
        "injury_report__listed": listed.astype(float),
        "injury_report__status_out": out_.astype(float),
        "injury_report__status_doubtful": 0.0,
        "injury_report__status_questionable": 0.0,
    })


class TestFoils:
    def test_a_missing_lagged_window_falls_to_the_position_rate_never_zero(self):
        f = _foil_frame()
        pos_rate = AV.train_pos_played_rate(f)
        p = AV.foil_point_t1(f, pos_rate)
        missing = f["prior_week_box__played_share_l4"].isna().to_numpy()
        assert missing.any(), "fixture must contain missing windows — else this tests nothing"
        expected = f.loc[missing, "position"].map(pos_rate).to_numpy(dtype=float)
        assert np.allclose(p[missing], np.clip(expected, 1e-6, 1 - 1e-6))
        assert (p[missing] > 0.0).all()

    def test_an_out_designation_gets_the_train_empirical_rate(self):
        f = _foil_frame()
        class_p, fallbacks = AV.fit_class_p_t1(f)
        assert "out" in class_p, f"the out cell must be fat in this fixture (fallbacks={fallbacks})"
        p = AV.foil_point_t1_inj(f, AV.train_pos_played_rate(f), class_p)
        sel = (AV.inj_class(f) == "out").to_numpy()
        assert sel.any()
        assert np.allclose(p[sel], np.clip(class_p["out"], 1e-6, 1 - 1e-6))

    def test_a_thin_lookup_cell_falls_back_and_is_COUNTED_never_silent(self):
        f = _foil_frame(n=80)  # every cell thin
        class_p, fallbacks = AV.fit_class_p_t1(f)
        assert not class_p
        assert fallbacks, "a thin cell must be REPORTED — a silent no-op is the NF1.7 (a) class"

    def test_an_unobserved_row_classifies_to_None_never_healthy(self):
        f = _foil_frame(n=8)
        f["injury_report__observed"] = 0.0
        for c in ("injury_report__listed", "injury_report__status_out",
                  "injury_report__status_doubtful", "injury_report__status_questionable"):
            f[c] = np.nan  # observed=0 ⇒ the whole family is NaN (W2d contract)
        assert AV.inj_class(f).isna().all()

    def test_the_t2_multiplier_is_clipped_and_out_doubtful_are_excluded_by_design(self):
        assert set(AV.INJ_MULT_CLASSES_T2) == {"questionable", "listed_no_designation"}
        lo, hi = AV.SHARE_MULT_CLIP
        f = _foil_frame()
        f["injury_report__status_questionable"] = f["injury_report__status_out"]
        f["injury_report__status_out"] = 0.0
        f["_t_share"] = np.where(
            f["injury_report__status_questionable"] == 1.0, 0.001, f["_t_share"])
        mult, _ = AV.fit_class_mult_t2(f)
        assert "questionable" in mult
        assert lo <= mult["questionable"] <= hi


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 5. The oracle + shuffle semantics of the Layer-B block
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _block_frame(n: int = 40, seed: int = 9) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    feat = pd.DataFrame({
        "position": np.tile(["QB", "RB", "WR", "TE"], n // 4),
        "gw": np.repeat(np.arange(n // 8), 8),
        "_t_played": (rng.random(n) < 0.7).astype(float),
        "_t_share": np.where(rng.random(n) < 0.3, np.nan, rng.random(n)),
    })
    proj = pd.DataFrame({
        "p_played": rng.uniform(0.2, 0.9, n),
        "snap_share": rng.uniform(0.1, 0.9, n),
        "share_sd": rng.uniform(0.05, 0.2, n),
    }, index=feat.index)
    return feat, proj


class TestOracleAndShuffleSemantics:
    def test_the_oracle_substitutes_realized_played_always(self):
        feat, proj = _block_frame()
        out = AV.attach_avail_features(feat, proj, realized=True)
        assert np.allclose(out["availability_projection__p_played"], feat["_t_played"])

    def test_the_oracle_keeps_the_projection_where_the_share_is_unmeasured(self):
        feat, proj = _block_frame()
        out = AV.attach_avail_features(feat, proj, realized=True)
        un = feat["_t_share"].isna()
        assert un.any(), "fixture must contain unmeasured shares — else this tests nothing"
        assert np.allclose(out.loc[un, "availability_projection__snap_share"],
                           proj.loc[un, "snap_share"])
        assert np.allclose(out.loc[~un, "availability_projection__snap_share"],
                           feat.loc[~un, "_t_share"])

    def test_the_oracle_does_not_substitute_the_sd(self):
        feat, proj = _block_frame()
        out = AV.attach_avail_features(feat, proj, realized=True)
        assert np.allclose(out["availability_projection__share_sd"], proj["share_sd"])

    def test_the_product_is_recomputed_from_the_substituted_parents(self):
        feat, proj = _block_frame()
        for kwargs in ({"realized": True}, {"shuffle_seed": 7}, {}):
            out = AV.attach_avail_features(feat, proj, **kwargs)
            prod = (out["availability_projection__p_played"]
                    * out["availability_projection__snap_share"])
            assert np.allclose(out["availability_projection__expected_avail"], prod)

    def test_the_shuffle_permutes_within_position_week_preserving_the_multiset(self):
        feat, proj = _block_frame()
        out = AV.attach_avail_features(feat, proj, shuffle_seed=11)
        moved = 0
        groups = 0
        for (_, _), grp in out.groupby(["position", "gw"]):
            groups += 1
            orig = proj.loc[grp.index, "p_played"].to_numpy()
            got = grp["availability_projection__p_played"].to_numpy()
            assert np.allclose(np.sort(orig), np.sort(got))
            moved += int((~np.isclose(orig, got)).sum())
        assert groups > 0, "no groups — the shuffle check ran on nothing"
        assert moved > 0, "the shuffle moved nothing — the anchor would equal the real arm"

    def test_red_proof_an_unmeasured_oracle_share_zeroed_is_caught(self):
        mod = _mutated(
            _MODULE,
            'share = np.where(np.isfinite(realized_share), realized_share, share)',
            'share = np.nan_to_num(realized_share)',
            "av_oracle_zero_fill")
        feat, proj = _block_frame()
        out_bad = mod.attach_avail_features(feat, proj, realized=True)
        un = feat["_t_share"].isna()
        assert (out_bad.loc[un, "availability_projection__snap_share"] == 0.0).all(), (
            "the mutation should fabricate zeros — otherwise this proves nothing")
        out_good = AV.attach_avail_features(feat, proj, realized=True)
        assert np.allclose(out_good.loc[un, "availability_projection__snap_share"],
                           proj.loc[un, "snap_share"])


class TestBlockNonVacuity:
    def test_an_unattached_block_raises_instead_of_comparing_the_champion_to_itself(self):
        feat, proj = _block_frame()
        attached = AV.attach_avail_features(feat, proj)
        empty = feat.copy()
        for c in AV.AVAIL_PROJ_FEATURES:
            empty[c] = np.nan
        with pytest.raises(ValueError, match="did not attach"):
            AV.assert_avail_block_attached({"avail": attached, "avail_oracle": empty},
                                           feat.index.to_numpy(), "t")
        cov = AV.assert_avail_block_attached({"avail": attached}, feat.index.to_numpy(), "t")
        assert cov["avail"] == 1.0

    def test_red_proof_loosening_the_threshold_lets_an_empty_block_pass(self):
        mod = _mutated(_MODULE, "if min(coverage.values()) < 0.99:",
                       "if min(coverage.values()) < -1.0:", "av_loose_block")
        feat, proj = _block_frame()
        empty = feat.copy()
        for c in AV.AVAIL_PROJ_FEATURES:
            empty[c] = np.nan
        mod.assert_avail_block_attached({"avail_oracle": empty},
                                        feat.index.to_numpy(), "t")  # no raise = the defect
        with pytest.raises(ValueError):
            AV.assert_avail_block_attached({"avail_oracle": empty},
                                           feat.index.to_numpy(), "t")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 6. Layer-B gate: every clause independently decisive; ⭐ NO PBO clause by design
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _passing_layer_b_sel() -> dict:
    return {
        "beats_foil": True,
        "fold_clause": {"passes": True, "required": 6, "attainable": True},
        "dsr": 0.99,
        "anchors": {"winner_beats_shuffled": True, "shuffled_lift_not_significant": True,
                    "respects_realized_oracle": True},
        "coverage": {"blocking_shortfall": False},
    }


class TestLayerBGate:
    def test_the_all_pass_baseline_ships(self):
        gate = AV.layer_b_gate_w4(_passing_layer_b_sel(), True)
        assert gate["ship"] is True
        assert all(gate["checks"].values())

    def test_pbo_is_absent_from_the_gate_by_design(self):
        """NF-W3 registered `pbo_ok` on a one-contrast field and had to disclaim it; NF-W4
        declares PBO undefined BEFORE the run instead — the gate must not contain it."""
        gate = AV.layer_b_gate_w4(_passing_layer_b_sel(), True)
        assert "pbo_ok" not in gate["checks"]

    @pytest.mark.parametrize("mutate, expect_false", [
        (lambda s: s.update(beats_foil=False), "beats_champion"),
        (lambda s: s["fold_clause"].update(passes=False), "fold_consistency"),
        (lambda s: s.update(dsr=0.5), "dsr_ok"),
        (lambda s: s.update(dsr=None), "dsr_ok"),
        (lambda s: s["anchors"].update(winner_beats_shuffled=False), "permutation_behaves"),
        (lambda s: s["anchors"].update(shuffled_lift_not_significant=False),
         "permutation_behaves"),
        (lambda s: s["anchors"].update(respects_realized_oracle=False),
         "oracle_floor_respected"),
        (lambda s: s["coverage"].update(blocking_shortfall=True), "coverage_floor_ok"),
    ])
    def test_flipping_exactly_one_input_fails_exactly_that_check(self, mutate, expect_false):
        sel = _passing_layer_b_sel()
        mutate(sel)
        gate = AV.layer_b_gate_w4(sel, True)
        assert gate["ship"] is False
        failed = [k for k, v in gate["checks"].items() if not v]
        assert failed == [expect_false]

    def test_fdr_is_its_own_decisive_clause(self):
        gate = AV.layer_b_gate_w4(_passing_layer_b_sel(), False)
        assert [k for k, v in gate["checks"].items() if not v] == ["fdr_ok"]

    def test_the_permutation_clause_fails_closed_in_both_selectors(self):
        """The exact fail-closed shape must be in BOTH selection functions' real source —
        comment-stripped, so prose cannot satisfy it (INC-38)."""
        src = _stripped_source(_RUNNER)
        assert src.count("is not None and p_perm >= 0.05") == 1
        assert src.count("is not None and p_shuf >= 0.05") == 1

    def test_hand_layer_b_refusal_is_constraint_refused_with_no_trigger(self):
        checks = {c: True for c in AV.LAYER_B_STATISTICAL_CHECKS}
        checks.update({c: True for c in AV.LAYER_B_ANCHOR_CHECKS})
        checks["oracle_floor_respected"] = False
        out = AV.hand_classify_layer_b_refusal(checks)
        assert out["state"] == "CONSTRAINT_REFUSED"
        assert out["retest_trigger"] is None

    def test_a_statistical_failure_hands_back_to_classify_null(self):
        checks = {c: True for c in AV.LAYER_B_STATISTICAL_CHECKS}
        checks.update({c: True for c in AV.LAYER_B_ANCHOR_CHECKS})
        checks["dsr_ok"] = False
        checks["oracle_floor_respected"] = False
        assert AV.hand_classify_layer_b_refusal(checks) is None

    def test_an_all_pass_check_set_is_not_a_refusal(self):
        checks = {c: True for c in AV.LAYER_B_STATISTICAL_CHECKS + AV.LAYER_B_ANCHOR_CHECKS}
        assert AV.hand_classify_layer_b_refusal(checks) is None


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 7. The Layer-B foil is the VALIDATED object (pinned to the committed W2d artifact)
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestIncumbentPin:
    def test_the_incumbent_spec_is_imported_from_w2b_not_retyped(self):
        assert AV.INCUMBENT_OF_POSITION == W2B.POST_FLIP_SPEC

    def test_the_incumbent_spec_matches_the_committed_w2d_artifact(self):
        assert _W2D_ARTIFACT.exists(), "the W2d artifact must be committed for the pin to hold"
        art = json.loads(_W2D_ARTIFACT.read_text())
        winners = {pos: art["positions"][pos]["winner"] for pos in WP.POSITIONS}
        assert winners == AV.INCUMBENT_OF_POSITION
        assert all(art["gates"][pos]["ship"] for pos in WP.POSITIONS), (
            "the pinned incumbents must be the CERTIFIED winners, not merely the recorded ones")

    def test_the_runner_refuses_an_unpinned_foil(self, monkeypatch):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w4_availability_bakeoff as R,
        )
        monkeypatch.setattr(AV, "INCUMBENT_OF_POSITION", {p: "inj_both" for p in WP.POSITIONS})
        with pytest.raises(ValueError, match="does not match the W2d-certified"):
            R.assert_incumbents_match_the_w2d_artifact()

    def test_the_runner_refuses_a_missing_artifact(self, monkeypatch):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w4_availability_bakeoff as R,
        )
        monkeypatch.setattr(R, "_W2D_ARTIFACT", Path("/nonexistent/nf_w2d.json"))
        with pytest.raises(FileNotFoundError):
            R.assert_incumbents_match_the_w2d_artifact()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 8. Field declaration, fold axis, power
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestFieldAndPower:
    def test_the_fold_axis_is_the_nf_w1_axis_verbatim(self):
        assert AV.TEST_BLOCKS is WP.TEST_BLOCKS
        assert AV.PURGE_WEEKS == WP.PURGE_WEEKS

    def test_each_target_fields_four_arms_and_two_foils(self):
        for t in AV.TARGETS:
            assert len(AV.REAL_ARMS[t]) == 4
        assert len(AV.FOILS) == 2

    def test_anchors_are_excluded_from_the_eligible_field(self):
        for t in AV.TARGETS:
            eligible = set(AV.eligible_labels(t))
            assert eligible == set(AV.REAL_ARMS[t]) | set(AV.FOILS)
            assert not (eligible & set(AV.anchors_for(t))), (
                "an anchor in the eligible field makes the deflation measure the anchors (NF1.8)")

    def test_the_layer_b_field_is_exactly_two_arms(self):
        assert AV.LAYER_B_ELIGIBLE == ("champion_inj", "champion_avail")
        assert AV.LAYER_B_REAL_ARMS == ("champion_avail",)

    def test_fdr_families_are_declared_in_the_module_not_discovered(self):
        assert AV.FDR_FAMILIES == {"component": ("played", "snap_share"),
                                   "downstream": tuple(WP.POSITIONS)}

    def test_no_gate_is_structurally_unattainable_at_eight_folds(self):
        from betting_ml.utils import cv_power
        clause = cv_power.fold_consistency_clause(8)
        assert clause.attainable and clause.wins_required <= 8
        assert 2 ** -8 < AV.FDR_Q
        ceiling = cv_power.dsr_ceiling(8)
        assert ceiling > AV.DSR_MIN, (
            f"dsr_ceiling(8)={ceiling} would make the DSR gate structurally unattainable")

    def test_the_oracle_substitution_set_excludes_the_sd(self):
        assert "availability_projection__share_sd" not in AV.ORACLE_SUBSTITUTED
        assert set(AV.ORACLE_SUBSTITUTED) < set(AV.AVAIL_PROJ_FEATURES)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 9. Deploy-held: no serving surface is imported or written
# ══════════════════════════════════════════════════════════════════════════════════════════════
class TestDeployHeld:
    _FORBIDDEN = ("write_serving_store", "write_api_cache", "deploy.sh", "boto3.client",
                  "put_object", "upload_file", "credence-prod", "s3.put", "registry.stage")

    def test_neither_file_touches_a_serving_surface(self):
        for path in (_MODULE, _RUNNER):
            src = _stripped_source(path)
            hits = [tok for tok in self._FORBIDDEN if tok in src]
            assert not hits, f"{path.name} touches serving surfaces: {hits}"
        assert len(self._FORBIDDEN) > 0

    def test_red_proof_the_scan_would_catch_a_real_write(self):
        src = _stripped_source(_MODULE) + "\nboto3.client('s3').put_object()"
        hits = [tok for tok in self._FORBIDDEN if tok in src]
        assert hits, "the deploy-held scan cannot fire — it guards nothing"

    def test_the_preregistration_exists_and_declares_the_story_shape(self):
        assert _PREREG.exists()
        text = _PREREG.read_text()
        for needle in ("Layer A", "Layer B", "oracle", "injury-aware",
                       "best_alpha = 0", "deploy-held", "UNDEFINED"):
            assert needle in text, f"pre-registration must declare {needle!r}"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# 10. The verdict layer is DERIVED, not stored (NF-W2e one level up)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def _fake_sel_a(beats: bool) -> dict:
    return {
        "beats_foil": beats, "mean_delta": 0.01 if beats else -0.01,
        "ci95": [-0.001, 0.02] if beats else [-0.02, 0.001],
        "fold_wins": 6 if beats else 2,
        "fold_clause": {"required": 6, "attainable": True, "passes": beats},
        "pbo": 0.1, "dsr": 0.99 if beats else 0.2, "p_one_sided": 0.01 if beats else 0.6,
        "observed_sr": 1.2 if beats else -0.3, "var_trials_sr": 0.01,
        "anchors": {"nihilist_loses": True, "marginal_loses": True, "zero_width_loses": True,
                    "max_width_loses": True, "winner_beats_permuted": True,
                    "permuted_lift_not_significant": True,
                    "oracle_floors_respected_at_matched_n": True,
                    "no_arm_beats_own_oracle": True, "foils_respect_own_oracle": True},
        "coverage": {"blocking_shortfall": False},
    }


def _fake_sel_b(beats: bool) -> dict:
    s = _fake_sel_a(beats)
    s["anchors"] = {"winner_beats_shuffled": True, "shuffled_lift_not_significant": True,
                    "respects_realized_oracle": True}
    return s


class TestVerdictLayerIsDerivedNotStored:
    def _out(self) -> dict:
        return {
            "n_folds": 8, "targets": ["played", "snap_share"],
            "layer_a": {"played": _fake_sel_a(True), "snap_share": _fake_sel_a(False)},
            "layer_b": {p: _fake_sel_b(False) for p in WP.POSITIONS},
        }

    def test_every_non_shipping_cell_gets_a_state(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w4_availability_bakeoff as R,
        )
        out = self._out()
        derived = R.derive_verdict_layer(out)
        assert set(derived["verdict"]["layer_a"]) == {"played", "snap_share"}
        assert set(derived["verdict"]["layer_b"]) == set(WP.POSITIONS)
        for key, v in {**derived["verdict"]["layer_a"], **derived["verdict"]["layer_b"]}.items():
            assert v != "NULL", f"{key} carries the fallback verdict — no state was derived"
        for p in WP.POSITIONS:
            assert f"layer_b::{p}" in derived["null_states"]

    def test_re_deriving_is_idempotent(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w4_availability_bakeoff as R,
        )
        out = self._out()
        first = R.derive_verdict_layer(out)
        out.update(first)
        second = R.derive_verdict_layer(out)
        assert first["verdict"] == second["verdict"]

    def test_a_losing_layer_b_arm_is_genuine_absence_with_no_trigger(self):
        from quant_sports_intel_models.football.nfl.fantasy import (
            run_nf_w4_availability_bakeoff as R,
        )
        out = self._out()
        derived = R.derive_verdict_layer(out)
        for p in WP.POSITIONS:
            ns = derived["null_states"][f"layer_b::{p}"]
            assert ns["state"] == "GENUINE_ABSENCE"
            assert ns["retest_trigger"] is None

    def test_the_rewrite_path_shares_the_same_derivation(self):
        src = _stripped_source(_RUNNER)
        assert src.count("out.update(derive_verdict_layer(out))") == 2, (
            "the live run and --rewrite-report must share ONE derivation — a second "
            "implementation is a verdict that can disagree with itself")
