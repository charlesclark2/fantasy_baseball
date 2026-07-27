"""Fast-gate unit tests for NF1.1 — per-position independent models + top-tier-weighted selection.

Imports ONLY the pure `nf1_1_model` module (numpy/pandas/sklearn/lightgbm/scipy — no `pipeline`,
no IO), per the fast-gate discipline. Covers the behavioural contracts the NF1.1 gate rests on:
  • the per-position learners (ridge / GBM / SIMILARITY-comparables) fit one position's rows and
    fall back to the MVP-1 incumbent when unfit (never garbage);
  • the TOP-TIER selection metric grades every candidate on the SAME incumbent-anchored tier and
    keeps the realized-outcome oracle a hard ceiling (E2.1-r);
  • the deflation harness (CSCV-PBO / config spread / deflated Sharpe / BH-FDR) behaves correctly
    on known-overfit vs known-dominant searches, and the repoint verdict enforces every gate;
  • the combined ordering score keeps MVP-1's order for unselected positions (the ordering-only
    discipline feeds `apply_learned_ordering` unchanged).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

M11 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_1_model")


# ── synthetic single-position frame ───────────────────────────────────────────────────────────
def _pos_frame(pos="WR", n=200, seed=1, signal=True):
    rng = np.random.default_rng(seed)
    mvp1 = np.clip(rng.normal(150, 60, n), 10, None)
    snap = np.clip(rng.normal(0.6, 0.2, n), 0.05, 0.99)
    xfp = np.clip(rng.normal(8, 3, n), 0, None)
    real = np.clip(0.5 * mvp1 + (120 * snap + 6 * xfp if signal else 0) + rng.normal(0, 25, n), 0, None)
    df = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "position": pos,
        "mvp1_fp": mvp1, "pergame_fp": mvp1 / 15.0, "base_games": rng.integers(6, 17, n),
        "expected_games": rng.uniform(8, 17, n), "snap_share": snap,
        "target_share": np.clip(rng.normal(0.15, 0.06, n), 0, 0.4),
        "carry_share": np.clip(rng.normal(0.05, 0.04, n), 0, 0.5),
        "depth_rank": rng.integers(1, 4, n), "mover_scale": rng.uniform(0.9, 1.2, n),
        "team_env": rng.normal(22, 3, n), "injury_cap_ratio": rng.uniform(0.8, 1.0, n),
        "age": rng.uniform(22, 33, n), "fp_sd": rng.uniform(5, 12, n),
        "xfp_pg": xfp, "td_luck_ratio": rng.normal(0, 0.1, n),
        "xrush_td_pg": np.clip(rng.normal(0.05, 0.05, n), 0, None),
        "xrec_td_pg": np.clip(rng.normal(0.25, 0.15, n), 0, None),
        "xrec_pg": np.clip(rng.normal(4, 2, n), 0, None),
        "xrec_yds_pg": np.clip(rng.normal(45, 20, n), 0, None),
        "real_fp_ppr": real,
    })
    return df


# ══════════════════════════════════════════════════════════════════════ feature contracts
def test_position_feature_sets_are_position_specific():
    """QB never a target; WR/TE never meaningful carriers; RB gets everything; every set includes
    the xFP candidates appropriate to the role (the NF-D7 delivery)."""
    assert "target_share" not in M11.POSITION_FEATURES["QB"]
    assert "carry_share" in M11.POSITION_FEATURES["QB"]          # rushing QBs are the separator
    assert "xrush_td_pg" in M11.POSITION_FEATURES["QB"]
    assert "xrec_pg" not in M11.POSITION_FEATURES["QB"]
    for p in ("WR", "TE"):
        assert "carry_share" not in M11.POSITION_FEATURES[p]
        assert "xrec_yds_pg" in M11.POSITION_FEATURES[p]
    assert set(M11.XFP_FEATURES) <= set(M11.POSITION_FEATURES["RB"])
    for p, feats in M11.POSITION_FEATURES.items():
        assert "mvp1_fp" in feats                                 # the incumbent prior always present
        assert len(feats) == len(set(feats))                      # no duplicated columns


# ══════════════════════════════════════════════════════════════════════ learners
def test_pos_null_is_the_incumbent_identity():
    df = _pos_frame()
    m = M11.PosNull().fit(df, df["real_fp_ppr"].to_numpy())
    np.testing.assert_allclose(m.predict(df), df["mvp1_fp"].to_numpy())


@pytest.mark.parametrize("name,hp", [
    ("pos_ridge", {"alpha": 5.0}),
    ("pos_gbm", {"n_estimators": 80, "num_leaves": 7, "min_child_samples": 10}),
    ("pos_similarity", {"k": 15, "weight_power": 1.0}),
])
def test_pos_learner_beats_null_in_sample_on_signal(name, hp):
    """Fit on data where usage/xFP add real signal beyond mvp1 → the learner must out-order the
    incumbent in-sample within the position."""
    df = _pos_frame(n=300)
    feats = M11.POSITION_FEATURES["WR"]
    learner = M11.make_pos_learner(name, feats=feats, **hp).fit(df, df["real_fp_ppr"].to_numpy())
    pred = learner.predict(df)
    assert np.isfinite(pred).all() and (pred >= 0).all()
    rho_l = pd.Series(pred).corr(df["real_fp_ppr"], method="spearman")
    rho_0 = df["mvp1_fp"].corr(df["real_fp_ppr"], method="spearman")
    assert rho_l >= rho_0 - 1e-6


@pytest.mark.parametrize("name", ["pos_ridge", "pos_gbm", "pos_similarity"])
def test_pos_learner_unfit_falls_back_to_incumbent(name):
    """A too-thin fit (below the row floor) must predict the MVP-1 incumbent, never garbage."""
    df = _pos_frame(n=5)
    learner = M11.make_pos_learner(name, feats=M11.POSITION_FEATURES["WR"])
    learner.fit(df, df["real_fp_ppr"].to_numpy())
    np.testing.assert_allclose(learner.predict(df), df["mvp1_fp"].to_numpy())


def test_similarity_predicts_from_comparables():
    """Two well-separated clusters: a test row in cluster A must be projected at cluster A's realized
    level (the comp average), not the global mean — the whole point of the analog paradigm."""
    n = 60
    a = _pos_frame(n=n, seed=3).assign(mvp1_fp=100.0, snap_share=0.2, real_fp_ppr=80.0)
    b = _pos_frame(n=n, seed=4).assign(mvp1_fp=300.0, snap_share=0.9, real_fp_ppr=280.0)
    train = pd.concat([a, b], ignore_index=True)
    sim = M11.PosSimilarity(k=10, weight_power=1.0, feats=("mvp1_fp", "snap_share"))
    sim.fit(train, train["real_fp_ppr"].to_numpy())
    test = a.head(3)
    pred = sim.predict(test)
    np.testing.assert_allclose(pred, 80.0, atol=1.0)


def test_similarity_is_deterministic_and_k_safe():
    df = _pos_frame(n=40)
    sim = M11.PosSimilarity(k=500, weight_power=0.0, feats=M11.POSITION_FEATURES["WR"])
    sim.fit(df, df["real_fp_ppr"].to_numpy())
    p1, p2 = sim.predict(df), sim.predict(df)
    np.testing.assert_allclose(p1, p2)                      # deterministic
    # k > n_train clamps to n_train; weight_power=0 → the unweighted mean of ALL train rows
    np.testing.assert_allclose(p1, np.full(len(df), df["real_fp_ppr"].mean()), rtol=1e-6)


def test_similarity_mvp1_emphasis_tightens_prior_neighbourhood():
    """With a huge mvp1 emphasis the comp neighbourhood is driven by the incumbent level alone —
    a low-mvp1 test row must comp to low-mvp1 (low-realized) train rows even when its other
    features match the high cluster."""
    n = 50
    lo = _pos_frame(n=n, seed=5).assign(mvp1_fp=80.0, snap_share=0.9, real_fp_ppr=60.0)
    hi = _pos_frame(n=n, seed=6).assign(mvp1_fp=320.0, snap_share=0.9, real_fp_ppr=300.0)
    train = pd.concat([lo, hi], ignore_index=True)
    probe = lo.head(2).assign(snap_share=0.9)
    sim = M11.PosSimilarity(k=8, weight_power=0.0, mvp1_emphasis=50.0,
                            feats=("mvp1_fp", "snap_share", "age"))
    sim.fit(train, train["real_fp_ppr"].to_numpy())
    np.testing.assert_allclose(sim.predict(probe), 60.0, atol=5.0)


# ══════════════════════════════════════════════════════════════════════ top-tier metric
def _two_pos_frame():
    rng = np.random.default_rng(7)
    frames = []
    for pos, n in (("QB", 60), ("WR", 90)):
        mvp1 = np.sort(rng.uniform(50, 350, n))[::-1]
        frames.append(pd.DataFrame({
            "position": pos, "mvp1_fp": mvp1,
            "real_fp_ppr": np.clip(mvp1 + rng.normal(0, 40, n), 0, None),
            "cand": mvp1 + rng.normal(0, 20, n),
        }))
    return pd.concat(frames, ignore_index=True)


def test_top_tier_rho_restricts_to_the_anchored_tier():
    """The metric must correlate ONLY inside the incumbent-anchored top-N — a candidate that orders
    the tier perfectly but scrambles the depth must score 1.0."""
    df = _two_pos_frame()
    # candidate: perfect inside the MVP-1 top-N, anti-ordered outside it
    cand = np.empty(len(df))
    for p, n in M11.TOP_N.items():
        d = df[df["position"] == p]
        if d.empty:
            continue
        tier_idx = d.nlargest(n, "mvp1_fp").index
        rest_idx = d.index.difference(tier_idx)
        cand[tier_idx] = df.loc[tier_idx, "real_fp_ppr"]
        cand[rest_idx] = -df.loc[rest_idx, "real_fp_ppr"]
    per, pooled = M11.top_tier_rho(df.assign(_c=cand), "_c", top_n={"QB": 24, "WR": 48})
    assert per["QB"] == pytest.approx(1.0) and per["WR"] == pytest.approx(1.0)
    assert pooled == pytest.approx(1.0)


def test_top_tier_is_fixed_across_candidates():
    """Two candidates are graded on the SAME (anchor-selected) subset: a candidate cannot change its
    own tier membership by inflating scores for easy players."""
    df = _two_pos_frame()
    d = df[df["position"] == "QB"]
    tier = set(d.nlargest(24, "mvp1_fp").index)
    # a candidate that puts absurd scores on non-tier players must not drag them into the grade:
    cheat = df["cand"].copy()
    outside = d.index.difference(list(tier))
    cheat.loc[outside] = 10_000.0
    per_a, _ = M11.top_tier_rho(df.assign(_c=df["cand"]), "_c", top_n={"QB": 24})
    per_b, _ = M11.top_tier_rho(df.assign(_c=cheat), "_c", top_n={"QB": 24})
    assert per_a["QB"] == per_b["QB"]        # identical inside the fixed tier → identical grade


def test_safe_spearman_handles_near_constant_float_noise():
    """The QB pos_gbm NaN bug: a degenerate LightGBM predicts a 'constant' carrying ~1e-14 float
    noise, so std>0 sneaks past a zero-variance check and scipy returns NaN. safe_spearman must
    return None (distinct-value guard), never NaN."""
    b = pd.Series(np.arange(20.0))
    exact = pd.Series(np.full(20, 187.3))
    noisy = pd.Series(np.full(20, 187.3) + np.random.default_rng(2).normal(0, 1e-14, 20))
    assert M11.safe_spearman(exact, b) is None
    v = M11.safe_spearman(noisy, b)
    assert v is None or np.isfinite(v)          # never NaN; the ~1e-14 case must not blow up
    assert M11.safe_spearman(b, b) == pytest.approx(1.0)


def test_top_tier_rho_degenerate_candidate_scores_zero_not_skip():
    """Under the SELECTION setting a constant candidate over a scoreable tier scores ρ=0.0 (zero
    ordering skill) so every config keeps the null's season coverage; the default setting skips."""
    df = _two_pos_frame().assign(_const=5.0)
    per_sel, _ = M11.top_tier_rho(df, "_const", top_n={"QB": 24}, degenerate_zero=True)
    assert per_sel["QB"] == 0.0
    per_def, _ = M11.top_tier_rho(df, "_const", top_n={"QB": 24})
    assert "QB" not in per_def


def test_oracle_is_the_top_tier_ceiling():
    df = _two_pos_frame()
    df = df.assign(good=df["real_fp_ppr"], noisy=df["cand"])
    assert M11.oracle_top_tier_is_ceiling(df, ["good", "noisy"], top_n={"QB": 24, "WR": 48}) is True


# ══════════════════════════════════════════════════════════════════════ deflation
def test_cscv_pbo_high_for_pure_noise_and_low_for_dominance():
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, size=(50, 8))
    pbo_noise = M11.cscv_pbo(noise)
    assert pbo_noise is not None and pbo_noise > 0.3      # noise: IS winner ~random OOS
    dom = rng.normal(0, 0.05, size=(50, 8))
    dom[7] += 2.0                                          # one config dominates every season
    pbo_dom = M11.cscv_pbo(dom)
    assert pbo_dom == pytest.approx(0.0)


def test_cscv_pbo_thin_matrix_is_none():
    assert M11.cscv_pbo(np.zeros((1, 8))) is None          # <2 configs
    assert M11.cscv_pbo(np.zeros((5, 3))) is None          # <4 seasons


def test_cscv_pbo_nan_safe():
    rng = np.random.default_rng(13)
    S = rng.normal(0, 1, size=(20, 6))
    S[3, :2] = np.nan                                       # a config unscored in two seasons
    v = M11.cscv_pbo(S)
    assert v is not None and 0.0 <= v <= 1.0


def test_config_spread_discriminates_tied_vs_wide_fields():
    tied = np.full((30, 6), 0.5) + np.random.default_rng(1).normal(0, 0.001, (30, 6))
    wide = np.vstack([np.full(6, 0.1), np.full(6, 0.9)])
    assert M11.config_spread(tied) < 0.01
    assert M11.config_spread(wide) == pytest.approx(0.8)


def test_deflated_sharpe_rewards_consistent_lift_and_deflates_many_trials():
    deltas = np.array([0.05, 0.06, 0.04, 0.055, 0.05, 0.045, 0.052])   # strong, consistent lift
    few = M11.deflated_sharpe(deltas, np.array([0.2]))
    assert few is not None and few > 0.95
    # the same winner surrounded by a huge population of high-variance unskilled trials deflates
    rng = np.random.default_rng(3)
    many_srs = rng.normal(0, 2.0, 5000)
    many = M11.deflated_sharpe(deltas, many_srs)
    assert many is not None and many < few


def test_deflated_sharpe_thin_or_flat_is_none():
    assert M11.deflated_sharpe(np.array([0.1, 0.2]), np.array([1.0])) is None      # T<3
    assert M11.deflated_sharpe(np.full(6, 0.1), np.array([1.0])) is None           # zero variance


def test_onesided_pvalue_direction():
    up = M11.onesided_paired_pvalue(np.array([0.05, 0.04, 0.06, 0.05, 0.045]))
    down = M11.onesided_paired_pvalue(np.array([-0.05, -0.04, -0.06, -0.05, -0.045]))
    assert up < 0.01 and down > 0.99


def test_bh_fdr_monotone_and_none_safe():
    res = M11.bh_fdr({"QB": 0.001, "RB": 0.02, "WR": 0.8, "TE": None}, q=0.10)
    assert res["QB"] is True and res["RB"] is True
    assert res["WR"] is False and res["TE"] is False
    assert M11.bh_fdr({"a": None}) == {"a": False}


def test_position_verdict_requires_every_gate():
    ok = M11.position_verdict(True, pbo=0.1, dsr=0.97, fdr_pass=True)
    assert ok["repoint"] is True
    assert M11.position_verdict(False, 0.1, 0.97, True)["repoint"] is False    # loses to null
    assert M11.position_verdict(True, 0.3, 0.97, True)["repoint"] is False     # PBO gate
    assert M11.position_verdict(True, 0.1, 0.5, True)["repoint"] is False      # DSR gate
    assert M11.position_verdict(True, 0.1, 0.97, False)["repoint"] is False    # FDR gate
    assert M11.position_verdict(True, None, None, True)["repoint"] is False    # unscorable ≠ pass


# ══════════════════════════════════════════════════════════════════════ ordering assembly
def test_combined_ordering_score_keeps_mvp1_for_unselected_positions():
    df = pd.concat([_pos_frame("QB", 30, seed=8), _pos_frame("WR", 40, seed=9)], ignore_index=True)
    wr_scores = np.arange(40, dtype=float)
    out = M11.combined_ordering_score(df, {"WR": wr_scores})
    m = df["position"].to_numpy() == "WR"
    np.testing.assert_allclose(out[m], wr_scores)
    np.testing.assert_allclose(out[~m], df.loc[~m, "mvp1_fp"].to_numpy())   # QB untouched = MVP-1


def test_combined_ordering_score_rejects_misaligned_rows():
    df = _pos_frame("QB", 10)
    with pytest.raises(ValueError):
        M11.combined_ordering_score(df, {"QB": np.zeros(7)})


def test_combined_score_feeds_apply_learned_ordering_identity_for_null():
    """End-to-end discipline: with NO selected positions the combined score is mvp1 everywhere →
    `apply_learned_ordering` is an identity remap (MVP-1's board unchanged) — the shipped null."""
    M1 = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_model")
    SP = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.season_projection")
    rng = np.random.default_rng(10)
    n = 30
    rec = np.clip(rng.normal(60, 25, n), 5, None)
    board = pd.DataFrame({
        "position": rng.choice(["WR", "TE"], n), "mvp1_fp": np.nan,
        "proj_pass_att": 0.0, "proj_pass_cmp": 0.0, "proj_pass_yds": 0.0, "proj_pass_td": 0.0,
        "proj_pass_int": 0.0, "proj_rush_att": 0.0, "proj_rush_yds": 0.0, "proj_rush_td": 0.0,
        "proj_targets": rec * 1.5, "proj_rec": rec, "proj_rec_yds": rec * 11.0,
        "proj_rec_td": np.clip(rng.normal(5, 2, n), 0, None),
        "proj_fumbles_lost": np.round(0.006 * rec, 2),
    })
    base = SP.score_line(board, prefix="proj_")["proj_fp_ppr"].to_numpy()
    board["mvp1_fp"] = base
    score = M11.combined_ordering_score(board, {})
    out = M1.apply_learned_ordering(board, score)
    got = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy()
    np.testing.assert_allclose(got, base, rtol=0.02)
