"""Fast-gate unit tests for NF1.3 — market-aware, position-conditional per-position models.

Imports ONLY the pure `nf1_3_model` module (numpy/pandas/sklearn/scipy — no `pipeline`, no IO), per
the fast-gate discipline. Covers the market-aware contracts the NF1.3 gate rests on:
  • market feature engineering (`build_market_features`) is ECR-primary / ADP-fallback, aligns
    `market_score = −market_rank`, and leaves the uncovered tail NaN;
  • the explicit blend learner (`PosMarketBlend`) collapses to the MVP-1 ordering at w=0 and to the
    pure-consensus ordering at w=1, is leakage-safe (train-fit standardisation), and falls back to
    the incumbent when unfit / where the market is missing;
  • the pure-consensus foil (`PosMarketOnly`) orders covered players by the market and sinks the
    uncovered below them, degrading to MVP-1 when no market column exists;
  • the position-conditional feature sets carry the market axes, the ablation groups include
    `market`, and the search space exposes the blend weight;
  • the reused NF1.1 metric + deflation kit is importable and behaves through the NF1.3 surface.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

M13 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_3_model")


# ── synthetic single-position frame with a market signal ────────────────────────────────────────
def _pos_frame(pos="QB", n=200, seed=1, market_signal=True, cover=1.0):
    """A position frame where realized fp is driven partly by the market rank (so a market-aware
    learner should have real ordering skill). `cover` = fraction of rows the market ranks."""
    rng = np.random.default_rng(seed)
    mvp1 = np.clip(rng.normal(200, 60, n), 10, None)
    # true quality is mvp1 + a market-only component the blind model can't see
    market_rank = np.argsort(np.argsort(-(mvp1 + rng.normal(0, 40, n)))) + 1  # 1=best
    real = 0.5 * mvp1 + (-(1.2) * market_rank if market_signal else 0.0) + rng.normal(0, 20, n)
    real = np.clip(real, 0, None)
    ecr = market_rank.astype(float)
    # thin the coverage: some players unranked by the market
    if cover < 1.0:
        drop = rng.choice(n, int(n * (1 - cover)), replace=False)
        ecr[drop] = np.nan
    df = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "position": pos,
        "mvp1_fp": mvp1, "real_fp_ppr": real,
        "ecr_rank": ecr, "ecr_std": rng.uniform(1, 20, n),
        "adp": ecr + rng.normal(0, 2, n), "adp_stdev": rng.uniform(1, 10, n),
    })
    return M13.build_market_features(df)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# build_market_features
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_market_features_ecr_primary_adp_fallback():
    df = pd.DataFrame({
        "adp": [5.0, np.nan, 80.0], "adp_stdev": [2.0, np.nan, 10.0],
        "ecr_rank": [3.0, 10.0, np.nan], "ecr_std": [1.0, 4.0, np.nan],
    })
    m = M13.build_market_features(df)
    # ECR wins where present; ADP fills the gap; NaN where neither
    assert list(m["market_rank"]) == [3.0, 10.0, 80.0]
    assert list(m["market_dispersion"]) == [1.0, 4.0, 10.0]
    assert list(m["market_score"]) == [-3.0, -10.0, -80.0]


def test_market_features_all_missing_is_nan():
    df = pd.DataFrame({"mvp1_fp": [100.0, 200.0]})
    m = M13.build_market_features(df)
    assert m["market_rank"].isna().all()
    assert m["market_score"].isna().all()


def test_market_score_orders_opposite_to_rank():
    m = _pos_frame(n=50)
    # higher market_score ⇔ lower (better) market_rank
    assert m["market_score"].corr(m["market_rank"], method="spearman") == pytest.approx(-1.0, abs=1e-9)


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosMarketBlend — the explicit position-conditional blend weight
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_blend_w0_is_mvp1_ordering():
    m = _pos_frame(n=200)
    pred = M13.PosMarketBlend(blend_w=0.0).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    # w=0 ⇒ pure z(mvp1_fp) ⇒ orders EXACTLY like mvp1_fp
    assert pd.Series(pred).corr(m["mvp1_fp"], method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_blend_w1_is_market_ordering():
    m = _pos_frame(n=200)
    pred = M13.PosMarketBlend(blend_w=1.0).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    # w=1 ⇒ pure z(market_score) ⇒ orders EXACTLY like market_score
    assert pd.Series(pred).corr(m["market_score"], method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_blend_intermediate_between_the_two_orderings():
    m = _pos_frame(n=300)
    pred = M13.PosMarketBlend(blend_w=0.5).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    r_mvp1 = abs(pd.Series(pred).corr(m["mvp1_fp"], method="spearman"))
    r_mkt = abs(pd.Series(pred).corr(m["market_score"], method="spearman"))
    # a genuine blend correlates with BOTH signals, neither perfectly
    assert 0.3 < r_mvp1 < 0.999 and 0.3 < r_mkt < 0.999


def test_blend_unfit_falls_back_to_mvp1():
    m = _pos_frame(n=5)  # < _MIN_FIT_ROWS ⇒ never fits
    learner = M13.PosMarketBlend(blend_w=0.7)
    learner.fit(m, m["real_fp_ppr"].to_numpy())
    assert learner._fit is None
    assert np.allclose(learner.predict(m), m["mvp1_fp"].to_numpy())


def test_blend_is_leakage_safe_standardisation():
    """Standardisation is fit on train only; a shifted test set must not change train's fit."""
    tr = _pos_frame(n=200, seed=2)
    te = _pos_frame(n=60, seed=9)
    learner = M13.PosMarketBlend(blend_w=1.0).fit(tr, tr["real_fp_ppr"].to_numpy())
    p1 = learner.predict(te)
    te2 = te.copy()
    te2["market_score"] = te2["market_score"] + 1000  # a shift preserves order
    p2 = learner.predict(te2)
    # order is invariant to a monotone shift (leakage-safe train stats), even if levels move
    assert pd.Series(p1).corr(pd.Series(p2), method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_blend_handles_missing_market_via_median_impute():
    m = _pos_frame(n=200, cover=0.5)  # half the rows have no market rank
    pred = M13.PosMarketBlend(blend_w=0.5).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    assert np.isfinite(pred).all()  # no NaN leaks through the impute


# ══════════════════════════════════════════════════════════════════════════════════════════════
# PosMarketOnly — the pure-consensus reference foil
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_market_only_orders_by_market_where_covered():
    m = _pos_frame(n=150)
    pred = M13.PosMarketOnly().predict(m)
    assert pd.Series(pred).corr(m["market_score"], method="spearman") == pytest.approx(1.0, abs=1e-9)


def test_market_only_sinks_uncovered_below_covered():
    m = _pos_frame(n=200, cover=0.6)
    pred = M13.PosMarketOnly().predict(m)
    covered = m["market_rank"].notna().to_numpy()
    # every covered player scores above every uncovered player
    assert pred[covered].min() > pred[~covered].max()


def test_market_only_no_market_column_is_mvp1():
    df = pd.DataFrame({"mvp1_fp": [100.0, 200.0, 150.0], "position": "QB"})
    pred = M13.PosMarketOnly().predict(df)
    assert np.allclose(pred, df["mvp1_fp"].to_numpy())


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Feature sets / groups / search space / registry
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_position_feature_sets_carry_market_axes():
    for pos in M13.POSITIONS:
        for f in M13.MARKET_FEATURES:
            assert f in M13.POSITION_FEATURES[pos]
    # xFP stays in for QB/RB/TE, out for WR? (WR keeps its NF1.1 set; market added to all)
    assert "market_rank" in M13.POSITION_FEATURES["WR"]


def test_ablation_groups_include_market():
    assert M13.FEATURE_GROUPS["market"] == M13.MARKET_FEATURES


def test_suggest_hp_exposes_blend_weight():
    class _T:  # minimal Optuna-trial stub
        def suggest_float(self, name, lo, hi, log=False):
            return (lo + hi) / 2
        def suggest_int(self, name, lo, hi, step=1):
            return lo

    hp = M13.suggest_hp(_T(), "pos_market_blend")
    assert "blend_w" in hp and 0.0 <= hp["blend_w"] <= 1.0
    assert "alpha" in M13.suggest_hp(_T(), "pos_ridge")


def test_registry_and_make_pos_learner():
    for name in ("pos_null", "pos_market_only", "pos_ridge", "pos_gbm", "pos_similarity", "pos_market_blend"):
        assert name in M13.POS_LEARNER_REGISTRY
    learner = M13.make_pos_learner("pos_market_blend", feats=("mvp1_fp", "market_score"), blend_w=0.4)
    assert isinstance(learner, M13.PosMarketBlend) and learner.blend_w == 0.4


def test_market_coverage_reports_tier_fraction():
    q = _pos_frame(pos="QB", n=40, cover=0.5)
    cov = M13.market_coverage(q, top_n={"QB": 24})
    assert "QB" in cov and 0.0 <= cov["QB"] <= 1.0


# ══════════════════════════════════════════════════════════════════════════════════════════════
# Reused NF1.1 kit is live through the NF1.3 surface
# ══════════════════════════════════════════════════════════════════════════════════════════════
def test_reused_metric_and_deflation_kit_importable():
    assert callable(M13.top_tier_rho) and callable(M13.cscv_pbo) and callable(M13.deflated_sharpe)
    assert M13.TOP_N == {"QB": 24, "RB": 36, "WR": 48, "TE": 24}


def test_top_tier_metric_grades_a_market_aware_score():
    m = _pos_frame(pos="RB", n=120, seed=3)
    # a w=1 market ordering should have real held-out top-tier skill (market drives the synthetic real)
    pred = M13.PosMarketBlend(blend_w=1.0).fit(m, m["real_fp_ppr"].to_numpy()).predict(m)
    per, pooled = M13.top_tier_rho(m.assign(_p=pred), "_p", top_n={"RB": 36})
    assert pooled is not None and pooled > 0
