"""Fast-gate unit tests for NF1.5 — the capstone feature-combination bake-off (pure module only).

Imports ONLY `nf1_5_model` (numpy/pandas/sklearn — no `pipeline`, no IO), per the fast-gate
discipline. Covers the anti-mirage contracts the capstone gate rests on:
  • the BLIND bundle registry is BOUNDED + hypothesis-driven (⛔ no powerset), bundle feature
    sets respect the NF1.2 per-position family map + the NF1.1 xFP verdict, and duplicate
    bundles dedupe per position (no padded search);
  • `PosRefinedBlend` NESTS the NF1.3 incumbent (anchor=mvp1 + slope=0 ≡ the flat blend), the
    learned anchor routes through the in-fold NF1.1 winner, the dispersion slope leans on the
    market only where the experts agree, a market-uncovered player keeps the pure anchor, and
    thin data falls back to MVP-1;
  • `PosMLP` (the DL candidate) is deterministic, falls back on thin data, and is a regular
    registry citizen (no exemption from the shared interface);
  • `placebo_shuffle` permutes outcomes WITHIN (position, target_season) only — multiset
    preserved, features untouched, deterministic;
  • the serving-recommendation decision rule hits its four branches;
  • the search spaces expose exactly the pre-registered knobs.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

M15 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_5_model")
M12 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_2_model")
M13 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_3_model")


# ── synthetic pool-like frame ──────────────────────────────────────────────────────────────────
def _frame(pos="QB", n=200, seed=1, cover=1.0, seasons=(2022, 2023)):
    rng = np.random.default_rng(seed)
    mvp1 = np.clip(rng.normal(200, 60, n), 10, None)
    market_rank = np.argsort(np.argsort(-(mvp1 + rng.normal(0, 40, n)))) + 1
    real = np.clip(0.5 * mvp1 - 1.2 * market_rank + rng.normal(0, 20, n), 0, None)
    ecr = market_rank.astype(float)
    if cover < 1.0:
        ecr[rng.choice(n, int(n * (1 - cover)), replace=False)] = np.nan
    df = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "position": pos,
        "target_season": rng.choice(list(seasons), n),
        "mvp1_fp": mvp1, "real_fp_ppr": real,
        "real_games": rng.integers(6, 18, n).astype(float),
        "ecr_rank": ecr, "ecr_std": rng.uniform(1, 20, n),
        "adp": ecr + rng.normal(0, 2, n), "adp_stdev": rng.uniform(1, 10, n),
        "feat_a": 0.8 * real + rng.normal(0, 10, n),   # a feature an inner learner can use
        "feat_b": rng.normal(0, 1, n),
    })
    return M13.build_market_features(df)


_SPEC = lambda: M15.AnchorSpec(learner="pos_ridge", hp={"alpha": 1.0}, feats=("feat_a", "feat_b"))


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Bundle registry — bounded, hypothesis-driven, per-position correct, deduped
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_bundles_are_bounded_not_a_powerset():
    # 7 named hypotheses — nowhere near an open subset search over the family space
    assert len(M15.BLIND_BUNDLES) == 7
    known = set(M12.REFINEMENT_FAMILIES) | {"xfp"}
    for fams in M15.BLIND_BUNDLES.values():
        assert set(fams) <= known


def test_base_bundle_is_the_nf1_core_only():
    for pos in M15.POSITIONS:
        feats = M15.bundle_features("base", pos)
        assert not set(feats) & set(M15.XFP_FEATURES)
        assert not set(feats) & set(M12.REFINEMENT_COLS)


def test_kitchen_sink_is_a_superset_of_every_bundle():
    for pos in M15.POSITIONS:
        sink = set(M15.bundle_features("kitchen_sink", pos))
        for b in M15.BLIND_BUNDLES:
            assert set(M15.bundle_features(b, pos)) <= sink


def test_bundles_respect_the_position_family_map():
    # qbcorr is WR/TE-only; oline is QB/RB-only (NF1.2's pre-registration)
    assert "team_qb_quality" not in M15.bundle_features("kitchen_sink", "QB")
    assert "team_qb_quality" in M15.bundle_features("kitchen_sink", "WR")
    assert "team_ol_cap_pct" in M15.bundle_features("kitchen_sink", "RB")
    assert "team_ol_cap_pct" not in M15.bundle_features("kitchen_sink", "WR")


def test_wr_xfp_verdict_inherited_and_deduped():
    # NF1.1 nulled xFP at WR ⇒ WR's base_xfp collapses into base and is DEDUPED from the sweep
    assert M15.bundle_features("base_xfp", "WR") == M15.bundle_features("base", "WR")
    eff = M15.effective_bundles("WR")
    assert "base" in eff and "base_xfp" not in eff
    # QB keeps its distinct xFP legs
    assert "base_xfp" in M15.effective_bundles("QB")


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosRefinedBlend — nesting, learned anchor, dispersion adaptivity, coverage fallback
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_refined_blend_w0_is_anchor_ordering():
    m = _frame(n=200)
    pred = M15.PosRefinedBlend(blend_w=0.0).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    assert pd.Series(pred).corr(m["mvp1_fp"], method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_refined_blend_flat_nests_the_nf1_3_incumbent():
    """anchor=mvp1 + slope=0 must reproduce NF1.3's PosMarketBlend ORDERING exactly (the
    incumbent is a strict special case of the refinement family)."""
    m = _frame(n=250, seed=3)
    y = m["real_fp_ppr"].to_numpy()
    ours = M15.PosRefinedBlend(blend_w=0.6, disp_slope=0.0).fit(m, y).predict(m)
    theirs = M13.PosMarketBlend(blend_w=0.6).fit(m, y).predict(m)
    assert pd.Series(ours).corr(pd.Series(theirs), method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_refined_blend_learned_anchor_uses_the_inner_learner():
    m = _frame(n=250, seed=5)
    y = m["real_fp_ppr"].to_numpy()
    blend = M15.PosRefinedBlend(blend_w=0.0, anchor="learned", inner=_SPEC()).fit(m, y)
    pred = blend.predict(m)
    inner = blend._fit["inner"]
    assert inner is not None
    assert pd.Series(pred).corr(pd.Series(inner.predict(m)), method="spearman") == pytest.approx(
        1.0, abs=1e-9)
    # and it is NOT just the mvp1 ordering (feat_a carries independent signal)
    assert pd.Series(pred).corr(m["mvp1_fp"], method="spearman") < 0.999


def test_refined_blend_dispersion_slope_leans_on_agreement():
    """Two players with identical anchor + market values: the LOW-dispersion one (experts agree)
    must sit closer to the market opinion when slope > 0."""
    tr = _frame(n=200, seed=7)
    y = tr["real_fp_ppr"].to_numpy()
    blend = M15.PosRefinedBlend(blend_w=0.5, disp_slope=0.5).fit(tr, y)
    te = tr.head(2).copy()
    te["mvp1_fp"] = 100.0                      # low anchor
    te["market_score"] = -1.0                  # strong market opinion (top rank)
    te["market_dispersion"] = [1.0, 19.0]      # agree vs soft
    p = blend.predict(te)
    assert p[0] > p[1]                         # low dispersion ⇒ more market ⇒ higher score here
    flat = M15.PosRefinedBlend(blend_w=0.5, disp_slope=0.0).fit(tr, y).predict(te)
    assert flat[0] == pytest.approx(flat[1])   # slope=0 ⇒ dispersion is inert


def test_refined_blend_uncovered_player_keeps_the_pure_anchor():
    tr = _frame(n=200, seed=11)
    blend = M15.PosRefinedBlend(blend_w=0.9).fit(tr, tr["real_fp_ppr"].to_numpy())
    te = tr.head(3).copy()
    te.loc[te.index[0], ["market_score", "market_rank", "market_dispersion"]] = np.nan
    p = blend.predict(te)
    za = blend._fit["za"].transform(te["mvp1_fp"].to_numpy())
    assert p[0] == pytest.approx(za[0])        # w forced to 0 where the market is silent


def test_refined_blend_thin_data_falls_back_to_mvp1():
    m = _frame(n=5)
    learner = M15.PosRefinedBlend(blend_w=0.7, anchor="learned", inner=_SPEC())
    learner.fit(m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is None
    assert np.allclose(learner.predict(m), m["mvp1_fp"].to_numpy())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosMLP — the DL candidate is a regular, deterministic citizen
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_mlp_thin_data_falls_back_to_mvp1():
    m = _frame(n=5)
    learner = M15.PosMLP(feats=("feat_a", "feat_b"))
    learner.fit(m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is None
    assert np.allclose(learner.predict(m), m["mvp1_fp"].to_numpy())


def test_mlp_is_deterministic_and_finite():
    m = _frame(n=150, seed=13)
    y = m["real_fp_ppr"].to_numpy()
    p1 = M15.PosMLP(hidden="32-16", feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    p2 = M15.PosMLP(hidden="32-16", feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    assert np.allclose(p1, p2)
    assert np.isfinite(p1).all() and (p1 >= 0).all()


def test_blind_registry_has_all_candidates_plus_null():
    assert set(M15.BLIND_CANDIDATES) == {"pos_ridge", "pos_gbm", "pos_similarity", "pos_mlp",
                                         "pos_twopart", "pos_rank"}
    for name in M15.BLIND_CANDIDATES:
        assert name in M15.BLIND_REGISTRY
    learner = M15.make_blind_learner("pos_mlp", feats=("feat_a",), hidden="32-16")
    assert isinstance(learner, M15.PosMLP)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosTwoPart — the availability×rate structural candidate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_twopart_thin_or_gameless_falls_back_to_mvp1():
    m = _frame(n=5)
    learner = M15.PosTwoPart(feats=("feat_a", "feat_b"))
    learner.fit(m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is None
    assert np.allclose(learner.predict(m), m["mvp1_fp"].to_numpy())
    # a big frame WITHOUT real_games also refuses to fit (the decomposition needs it)
    m2 = _frame(n=100).drop(columns=["real_games"])
    learner2 = M15.PosTwoPart(feats=("feat_a", "feat_b"))
    learner2.fit(m2, m2["real_fp_ppr"].to_numpy())
    assert learner2._fit is None


def test_twopart_predicts_rate_times_games_deterministically():
    m = _frame(n=200, seed=21)
    y = m["real_fp_ppr"].to_numpy()
    p1 = M15.PosTwoPart(feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    p2 = M15.PosTwoPart(feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    assert np.allclose(p1, p2)
    assert np.isfinite(p1).all() and (p1 >= 0).all()
    # games leg is clipped to a season's physical bound → prediction ≤ max_rate × 18
    rate_cap = (y / m["real_games"].to_numpy()).max()
    assert p1.max() <= rate_cap * 18 + 1e-6
    # it learned something: correlates with the realized outcome (feat_a carries signal)
    assert pd.Series(p1).corr(pd.Series(y), method="spearman") > 0.3


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosRank — the rank-objective candidate
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_rank_thin_data_falls_back_to_mvp1():
    m = _frame(n=5)
    learner = M15.PosRank(feats=("feat_a", "feat_b"))
    learner.fit(m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is None
    assert np.allclose(learner.predict(m), m["mvp1_fp"].to_numpy())


def test_rank_grades_are_bounded_quantiles():
    g = M15.PosRank._grade(np.array([1.0, 5.0, 2.0, 9.0, 7.0]))
    assert g.min() >= 0 and g.max() <= 15
    # monotone: a bigger outcome never gets a smaller grade
    order = np.argsort([1.0, 5.0, 2.0, 9.0, 7.0])
    assert (np.diff(g[order]) >= 0).all()


def test_rank_is_deterministic_and_orders_signal():
    m = _frame(n=250, seed=23)
    y = m["real_fp_ppr"].to_numpy()
    p1 = M15.PosRank(n_estimators=100, feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    p2 = M15.PosRank(n_estimators=100, feats=("feat_a", "feat_b")).fit(m, y).predict(m)
    assert np.allclose(p1, p2)
    assert pd.Series(p1).corr(pd.Series(y), method="spearman") > 0.3


def test_rank_fits_without_target_season_column():
    m = _frame(n=100, seed=29).drop(columns=["target_season"])
    learner = M15.PosRank(n_estimators=50, feats=("feat_a", "feat_b")).fit(
        m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is not None
    assert np.isfinite(learner.predict(m)).all()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# placebo_shuffle — the mirage control
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_placebo_preserves_group_multisets_and_features():
    pool = pd.concat([_frame("QB", 120, seed=1), _frame("RB", 120, seed=2)], ignore_index=True)
    plc = M15.placebo_shuffle(pool, seed=42)
    assert plc.shape == pool.shape
    for (pos, y), grp in pool.groupby(["position", "target_season"]):
        pg = plc[(plc["position"] == pos) & (plc["target_season"] == y)]
        assert sorted(grp["real_fp_ppr"]) == pytest.approx(sorted(pg["real_fp_ppr"]))
    # features untouched, alignment destroyed
    pd.testing.assert_frame_equal(pool.drop(columns=["real_fp_ppr"]),
                                  plc.drop(columns=["real_fp_ppr"]))
    assert (pool["real_fp_ppr"] != plc["real_fp_ppr"]).mean() > 0.5


def test_placebo_is_deterministic():
    pool = _frame("WR", 100, seed=3)
    a = M15.placebo_shuffle(pool, seed=7)
    b = M15.placebo_shuffle(pool, seed=7)
    pd.testing.assert_frame_equal(a, b)
    c = M15.placebo_shuffle(pool, seed=8)
    assert (a["real_fp_ppr"] != c["real_fp_ppr"]).any()


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Incumbent extraction, stage-1 factory, search spaces
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_extract_winners_parses_a_bakeoff_dict():
    bake = {"positions": {
        "QB": {"winner": {"learner": "pos_market_blend", "hp": {"blend_w": 0.9}, "mean_top": 0.5}},
        "RB": {"note": "no scoreable candidate"},
    }}
    w = M15.extract_winners(bake)
    assert w == {"QB": {"learner": "pos_market_blend", "hp": {"blend_w": 0.9}, "mean_top": 0.5}}
    assert M15.extract_winners({}) == {}


def test_stage1_factory_routes_variants_and_foils():
    r = M15.make_stage1_learner("pos_learned_adaptive_blend", inner=_SPEC(),
                                blend_w=0.4, disp_slope=0.2)
    assert isinstance(r, M15.PosRefinedBlend) and r.anchor == "learned" and r.disp_slope == 0.2
    flat = M15.make_stage1_learner("pos_blend_flat", blend_w=0.4)
    assert isinstance(flat, M15.PosRefinedBlend) and flat.anchor == "mvp1"
    foil = M15.make_stage1_learner("pos_market_only")
    assert isinstance(foil, M13.PosMarketOnly)


class _StubTrial:
    def suggest_float(self, name, lo, hi, **kw):
        return (lo + hi) / 2
    def suggest_int(self, name, lo, hi, **kw):
        return int((lo + hi) // 2)
    def suggest_categorical(self, name, choices):
        return choices[0]


def test_search_spaces_expose_the_preregistered_knobs():
    t = _StubTrial()
    assert set(M15.suggest_hp(t, "pos_blend_flat")) == {"blend_w"}
    assert set(M15.suggest_hp(t, "pos_learned_blend")) == {"blend_w"}
    assert set(M15.suggest_hp(t, "pos_adaptive_blend")) == {"blend_w", "disp_slope"}
    assert set(M15.suggest_hp(t, "pos_learned_adaptive_blend")) == {"blend_w", "disp_slope"}
    assert set(M15.suggest_hp(t, "pos_mlp")) == {"hidden", "alpha", "learning_rate_init"}
    assert set(M15.suggest_hp(t, "pos_gbm")) == {"n_estimators", "num_leaves", "learning_rate",
                                                 "min_child_samples", "reg_lambda"}
    assert set(M15.suggest_hp(t, "pos_twopart")) == {"n_estimators", "num_leaves", "learning_rate",
                                                     "min_child_samples", "reg_lambda", "games_alpha"}
    assert set(M15.suggest_hp(t, "pos_rank")) == {"n_estimators", "num_leaves", "learning_rate",
                                                  "min_child_samples", "reg_lambda"}


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Serving recommendation — the four branches
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_serving_recommendation_refined_wins():
    r = M15.serving_recommendation({"QB": True}, {"QB": {"repoint": False}},
                                   product_delta_vs_nf1_3=0.01, calib_80=0.81)
    assert r["serve"] == "refined-dual-board"


def test_serving_recommendation_falls_back_to_nf1_3():
    r = M15.serving_recommendation({"QB": False}, {}, product_delta_vs_nf1_3=-0.01, calib_80=0.80)
    assert r["serve"] == "nf1_3-dual-board"


def test_serving_recommendation_pending_calibration():
    r = M15.serving_recommendation({}, {}, product_delta_vs_nf1_3=None, calib_80=None)
    assert r["serve"] == "nf1_3-dual-board-pending-calibration"


def test_serving_recommendation_mvp1_when_no_market_win():
    r = M15.serving_recommendation({}, {}, product_delta_vs_nf1_3=None, calib_80=0.85,
                                   nf1_3_product_beats_blind=False)
    assert r["serve"] == "mvp1-blind"


# ══════════════════════════════════════════════════════════════════════════════════════════════
# The reused metric surface (oracle guard through the NF1.5 import)
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_oracle_is_the_scoring_floor_through_nf1_5():
    m = _frame("QB", 120, seed=17)
    df = m.assign(_c=m["mvp1_fp"])
    assert M15.oracle_top_tier_is_ceiling(df, ["_c"]) is True
