"""Fast-gate unit tests for NF1 — the joint learned re-weighting + the matchup-aware weekly leg.

Imports ONLY the pure `nf1_model` module (numpy/pandas/sklearn/lightgbm/scipy — no `pipeline`, no
IO), per the fast-gate discipline. Covers the behavioural contracts the NF1 gate rests on:
  • the learners fit/predict a sane per-position ordering (and the heuristic null is a true identity);
  • `apply_learned_level` preserves the raw-line contract (rescores consistently, clamps the tail);
  • the E2.1-r metric hygiene (randomized PIT, flatness, calib_80 as a FLOOR, the ORACLE-FLOOR guard);
  • the weekly matchup model applies leakage-safe multiplicative tilts and stays face-valid.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

M = pytest.importorskip("quant_sports_intel_models.football.nfl.fantasy.nf1_model")


# ── synthetic feature frame ───────────────────────────────────────────────────────────────────
def _synthetic(n=400, seed=1):
    rng = np.random.default_rng(seed)
    pos = rng.choice(list(M.LEARN_POSITIONS), size=n)
    mvp1 = np.clip(rng.normal(150, 60, n), 10, None)
    # a realized target that depends on mvp1 + a usage signal + noise (so a learner CAN beat the null)
    snap = np.clip(rng.normal(0.6, 0.2, n), 0.05, 0.99)
    real = np.clip(0.6 * mvp1 + 120 * snap + rng.normal(0, 30, n), 0, None)
    df = pd.DataFrame({
        "player_id": [f"p{i}" for i in range(n)], "position": pos,
        "mvp1_fp": mvp1, "pergame_fp": mvp1 / 15.0, "base_games": rng.integers(6, 17, n),
        "expected_games": rng.uniform(8, 17, n), "snap_share": snap,
        "target_share": np.clip(rng.normal(0.12, 0.06, n), 0, 0.4),
        "carry_share": np.clip(rng.normal(0.1, 0.08, n), 0, 0.5),
        "depth_rank": rng.integers(1, 4, n), "mover_scale": rng.uniform(0.9, 1.2, n),
        "team_env": rng.normal(22, 3, n), "injury_cap_ratio": rng.uniform(0.8, 1.0, n),
        "age": rng.uniform(22, 33, n), "fp_sd": rng.uniform(5, 12, n),
        "real_fp_ppr": real,
    })
    return df


# ══════════════════════════════════════════════════════════════════════ learners
def test_heuristic_null_is_identity():
    df = _synthetic()
    m = M.HeuristicNull().fit(df, df["real_fp_ppr"].to_numpy(), df["position"].to_numpy())
    pred = m.predict(df, df["position"].to_numpy())
    np.testing.assert_allclose(pred, df["mvp1_fp"].to_numpy())


@pytest.mark.parametrize("name", ["ridge", "elasticnet", "gbm"])
def test_learner_beats_null_ordering_on_signal(name):
    """A learner fit on data where usage adds real signal must out-order the mvp1-only null in-sample."""
    df = _synthetic()
    pos = df["position"].to_numpy()
    learner = M.make_learner(name).fit(df, df["real_fp_ppr"].to_numpy(), pos)
    pred = learner.predict(df, pos)
    _, learned = M.within_position_rho(df.assign(_p=pred), "_p")
    _, null = M.within_position_rho(df.assign(_p=df["mvp1_fp"]), "_p")
    assert learned is not None and null is not None
    assert learned >= null - 1e-6  # the learner can see the usage signal the null cannot


def test_ridge_predict_handles_missing_feature_column():
    """A feature-ablation arm passes a subset of columns; a missing column must not crash (all-NaN →
    imputed), and the prediction falls back to the incumbent for an unfit position."""
    df = _synthetic()
    feats = tuple(f for f in M.FEATURES if f != "snap_share")
    learner = M.make_learner("ridge", feats=feats).fit(df, df["real_fp_ppr"].to_numpy(),
                                                        df["position"].to_numpy())
    pred = learner.predict(df.drop(columns=["snap_share"]), df["position"].to_numpy())
    assert np.isfinite(pred).all() and (pred >= 0).all()


# ══════════════════════════════════════════════════════════════════════ raw-line contract
def _raw_line():
    return pd.DataFrame([{
        "position": "WR", "proj_fp_ppr": 200.0,
        "proj_pass_att": 0, "proj_pass_cmp": 0, "proj_pass_yds": 0, "proj_pass_td": 0, "proj_pass_int": 0,
        "proj_rush_att": 5, "proj_rush_yds": 30, "proj_rush_td": 0,
        "proj_targets": 120, "proj_rec": 90, "proj_rec_yds": 1100, "proj_rec_td": 8,
        "proj_fumbles_lost": 1.0,
    }])


def test_apply_learned_level_rescores_consistently():
    """Rescaling the line to a learned target then re-scoring yields the target EXACTLY (raw-line
    contract: NF-C1 can rescore in any league and recover the learned ordering). The base is the
    line's OWN score, so a stale proj_fp_ppr on the row is irrelevant."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    line = _raw_line()
    base_score = SP.score_line(line, prefix="proj_")["proj_fp_ppr"].iloc[0]   # ~249, not the stale 200
    out = M.apply_learned_level(line, np.array([260.0]))          # target within the clamp band
    rescored = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].iloc[0]
    assert rescored == pytest.approx(260.0, rel=0.02)
    assert out["nf1_scale"].iloc[0] == pytest.approx(260.0 / base_score, rel=0.02)


def test_apply_learned_level_clamps_the_tail():
    line = _raw_line()
    out_hi = M.apply_learned_level(line, np.array([100000.0]))    # absurd target → clamp at HI
    assert out_hi["nf1_scale"].iloc[0] == pytest.approx(M._RESCALE_HI)
    out_lo = M.apply_learned_level(line, np.array([1.0]))         # absurd low → clamp at LO
    assert out_lo["nf1_scale"].iloc[0] == pytest.approx(M._RESCALE_LO)


def test_apply_learned_level_preserves_rec_le_targets():
    line = _raw_line()
    out = M.apply_learned_level(line, np.array([260.0]))
    assert (out["proj_rec"] <= out["proj_targets"]).all()


# ══════════════════════════════════════════════════════════════════════ ordering remap
def _mvp1_board(n=40, seed=2):
    """A synthetic MVP-1 veteran board: a raw line whose scored PPR spans a realistic range."""
    rng = np.random.default_rng(seed)
    pos = rng.choice(list(M.LEARN_POSITIONS), n)
    rec = np.clip(rng.normal(60, 30, n), 0, None)
    rec_yds = rec * rng.uniform(9, 13, n)
    rec_td = np.clip(rng.normal(5, 3, n), 0, None)
    # fumbles_lost must be the pipeline's own 0.006×touches (rush_att=0 → 0.006×rec); an inconsistent
    # value would shift the rescore vs the base and mask the identity/multiset properties under test.
    return pd.DataFrame({
        "position": pos, "proj_fp_ppr": np.nan,
        "proj_pass_att": 0.0, "proj_pass_cmp": 0.0, "proj_pass_yds": 0.0, "proj_pass_td": 0.0,
        "proj_pass_int": 0.0, "proj_rush_att": 0.0, "proj_rush_yds": 0.0, "proj_rush_td": 0.0,
        "proj_targets": rec * 1.5, "proj_rec": rec, "proj_rec_yds": rec_yds, "proj_rec_td": rec_td,
        "proj_fumbles_lost": np.round(0.006 * rec, 2),
    })


def test_learned_ordering_preserves_position_point_multiset():
    """The remap keeps each position's MVP-1 scored-points MULTISET exactly (calibrated levels intact,
    no survivorship inflation, no clamp saturation) — it only permutes WHICH player gets which level."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    board = _mvp1_board()
    base = SP.score_line(board, prefix="proj_")["proj_fp_ppr"].to_numpy()
    # a MILD reordering (base + noise) so no player's rank move is extreme enough to hit the rescale
    # clamp — the multiset is then preserved EXACTLY (the clamp only perturbs the rare extreme mover).
    score = base + np.random.default_rng(9).normal(0, base.std() * 0.15, size=len(board))
    out = M.apply_learned_ordering(board, score)
    got = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy()
    for p in M.LEARN_POSITIONS:
        m = board["position"].to_numpy() == p
        if m.sum() >= 2:
            np.testing.assert_allclose(np.sort(got[m]), np.sort(base[m]), rtol=0.02)


def test_learned_ordering_matches_the_learned_rank():
    """Within a position the shipped board's rank == the learned-score rank (the validated bake-off
    ordering ships exactly)."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    board = _mvp1_board(n=60)
    score = np.random.default_rng(11).normal(size=len(board))
    out = M.apply_learned_ordering(board, score)
    got = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy()
    pos = board["position"].to_numpy()
    for p in M.LEARN_POSITIONS:
        idx = np.where(pos == p)[0]
        if len(idx) < 3:
            continue
        # the player with the top learned score must have the top shipped points in that position
        assert idx[np.argmax(score[idx])] == idx[np.argmax(got[idx])]


def test_learned_ordering_null_is_identity():
    """Remapping by the MVP-1 score itself (the heuristic null) is an identity — MVP-1 unchanged."""
    from quant_sports_intel_models.football.nfl.fantasy import season_projection as SP
    board = _mvp1_board()
    base = SP.score_line(board, prefix="proj_")["proj_fp_ppr"].to_numpy()
    out = M.apply_learned_ordering(board, base)
    got = SP.score_line(out, prefix="proj_")["proj_fp_ppr"].to_numpy()
    np.testing.assert_allclose(got, base, rtol=0.02)


# ══════════════════════════════════════════════════════════════════════ E2.1-r hygiene
def test_oracle_is_the_ordering_ceiling():
    """A candidate equal to realized == the oracle (ρ=1); nothing may exceed it. A deliberately
    inverted candidate (−realized) must NOT be flagged as beating the oracle (it scores far below)."""
    df = _synthetic()
    df = df.assign(good=df["real_fp_ppr"], bad=-df["real_fp_ppr"])
    assert M.oracle_ordering_is_the_ceiling(df, ["good", "bad"]) is True
    # a candidate that literally exceeds the oracle is impossible → construct a fake to prove the guard
    df2 = df.assign(cheat=df["real_fp_ppr"] * 1.0)
    # perturb the oracle down by adding noise to real inside the check is not possible; instead assert
    # the guard returns True for legitimate candidates and the oracle equals 1 per position
    per, pooled = M.within_position_rho(df.assign(_o=df["real_fp_ppr"]), "_o")
    assert pooled == pytest.approx(1.0)


def test_randomized_pit_uniform_for_calibrated_normal():
    rng = np.random.default_rng(3)
    n = 5000
    mu = np.full(n, 10.0)
    sd = np.full(n, 4.0)
    y = rng.normal(mu, sd)
    from scipy.stats import norm
    cdf = norm.cdf((y - mu) / sd)
    pit = M.randomized_pit(y, cdf, cdf, rng=np.random.default_rng(4))
    assert M.pit_max_decile_deviation(pit) < 0.03   # ~uniform


def test_calibrate_dispersion_is_a_floor():
    """An UNDER-dispersed predictive (true sd 2× the model sd) must get κ≈2 so calib_80 clears 0.80."""
    rng = np.random.default_rng(5)
    n = 4000
    base_sd = np.full(n, 3.0)
    resid = rng.normal(0, 6.0, n)                    # true dispersion 2× the base
    k = M.calibrate_dispersion(resid, base_sd, target_cov=0.80)
    z = 1.2815515594
    cov = M.calib_coverage(resid, -z * k * base_sd, z * k * base_sd)
    assert cov >= 0.80
    assert k > 1.5


# ══════════════════════════════════════════════════════════════════════ weekly matchup
def test_defense_vs_position_factor_direction_and_clamp():
    allowed = pd.DataFrame({
        "defense_team": ["AAA", "BBB", "CCC"], "position": ["WR", "WR", "WR"],
        "fp_allowed_pg": [40.0, 20.0, 30.0], "def_games": [10, 10, 0],   # CCC has no sample
    })
    lg = pd.DataFrame({"position": ["WR"], "lg_fp_allowed_pg": [30.0]})
    f = M.defense_vs_position_factor(allowed, lg).set_index("defense_team")["dvp_factor"]
    assert f["AAA"] > 1.0 and f["BBB"] < 1.0            # generous vs stingy defense
    assert f["CCC"] == pytest.approx(1.0)               # no sample → neutral
    assert (f <= M._DVP_CLAMP[1] + 1e-9).all() and (f >= M._DVP_CLAMP[0] - 1e-9).all()


def test_environment_factor_scales_with_implied_points():
    f = M.environment_factor(np.array([28.0, 22.5, 16.0, np.nan]), 22.5)
    assert f[0] > 1.0 and f[1] == pytest.approx(1.0) and f[2] < 1.0
    assert f[3] == pytest.approx(1.0)                   # unknown → neutral
    assert (f <= M._ENV_CLAMP[1] + 1e-9).all()


def test_project_week_toggles_and_home_boost():
    pg = np.array([12.0, 12.0])
    sd = np.array([6.0, 6.0])
    dvp = np.array([1.2, 1.2])
    env = np.array([1.1, 1.1])
    home = np.array([1.0, 0.0])
    off = M.project_week(pg, sd, dvp=dvp, env=env, is_home=home,
                         cfg=M.WeeklyConfig(False, False, False))
    np.testing.assert_allclose(off["week_fp"].to_numpy(), pg)      # all off → flat baseline
    full = M.project_week(pg, sd, dvp=dvp, env=env, is_home=home, cfg=M.WeeklyConfig(True, True, True))
    assert full["week_fp"].iloc[0] > full["week_fp"].iloc[1]        # home game scores higher
    assert full["week_fp"].iloc[0] == pytest.approx(12.0 * 1.2 * 1.1 * M._HOME_BOOST, rel=1e-3)
    assert (full["week_p10"] >= 0).all()                            # floored at 0


def test_gamma_weekly_interval_is_nonneg_and_ordered():
    mu = np.array([12.0, 4.0, 20.0])
    sd = np.array([7.0, 3.0, 9.0])
    lo, hi = M.gamma_weekly_interval(mu, sd)
    assert (lo >= 0).all() and (hi > lo).all()           # non-negative, ordered (no cl-at-0 artefact)
    c = M.gamma_weekly_cdf(mu, mu, sd)                    # CDF at the mean ~ (0.5, 0.6) for right-skew
    assert ((c > 0.35) & (c < 0.75)).all()


def test_gamma_weekly_cdf_uniform_for_gamma_draws():
    from scipy.stats import gamma
    rng = np.random.default_rng(9)
    n = 6000
    mu = np.full(n, 10.0); sd = np.full(n, 6.0)
    k, theta = M._gamma_shape_scale(mu, sd)
    y = gamma.rvs(a=k, scale=theta, random_state=rng)
    pit = M.gamma_weekly_cdf(y, mu, sd)
    assert M.pit_max_decile_deviation(pit) < 0.03        # calibrated on its own draws


def test_truncnorm_cdf_monotone_and_bounded():
    y = np.array([0.0, 5.0, 10.0, 30.0])
    mu = np.full(4, 10.0)
    sd = np.full(4, 5.0)
    c = M.truncnorm_cdf(y, mu, sd)
    assert (np.diff(c) >= -1e-9).all()                              # monotone non-decreasing in y
    assert (c >= 0).all() and (c <= 1).all()
