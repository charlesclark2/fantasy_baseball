"""NF-D6 — Forward defense-strength projection. Pure/offline unit tests for the strength math
(z-scoring, churn shrink, forward uncertainty, position-group split), the opponent-adjusted mixed-model
fit on SYNTHETIC plays (recovers a known-strong defense; no S3), and the leakage-safe forward-projection
wiring with injected frames. All IO-free (the S3 play/roster reads are exercised by the run harness), so
these land in the fast gate."""
import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.nfl.fantasy import defense_source as D


# ── pure helpers ────────────────────────────────────────────────────────────────────────────────
def test_zscore_mean_zero_unit_sd_and_degenerate_safe():
    z = D.zscore(np.array([1.0, 2.0, 3.0, 4.0]))
    assert z.mean() == pytest.approx(0.0, abs=1e-9)
    assert z.std() == pytest.approx(1.0, abs=1e-9)
    # a degenerate (all-equal) input → zeros, never NaN
    assert np.allclose(D.zscore(np.array([5.0, 5.0, 5.0])), 0.0)


def test_churn_shrink_pulls_toward_mean_with_churn():
    prior = np.array([2.0, -1.0, 0.5])
    # k=0 ⇒ no shrink (the pure opponent-adjusted arm)
    assert np.allclose(D.churn_shrink(prior, np.array([0.5, 0.5, 0.5]), 0.0), prior)
    # k=1, churn=1 ⇒ collapse to the mean (0 on the z-scale)
    assert np.allclose(D.churn_shrink(prior, np.array([1.0, 1.0, 1.0]), 1.0), 0.0)
    # partial churn shrinks proportionally; churn is clamped to [0,1]
    got = D.churn_shrink(np.array([2.0]), np.array([0.5]), 0.4)
    assert got[0] == pytest.approx(2.0 * (1 - 0.4 * 0.5))
    assert D.churn_shrink(np.array([2.0]), np.array([5.0]), 1.0)[0] == pytest.approx(0.0)  # clamp


def test_forward_sd_quadrature_and_monotone_in_all_terms():
    prior_sd = np.array([0.3, 0.3])
    churn = np.array([0.0, 1.0])
    # measurement-only (no floor, no churn term)
    base = D.forward_sd(prior_sd, churn, 0.0, 0.0)
    assert np.allclose(base, prior_sd)
    # a volatility floor widens both, in quadrature
    withfloor = D.forward_sd(prior_sd, churn, 0.5, 0.0)
    assert np.allclose(withfloor, np.sqrt(0.3 ** 2 + 0.5 ** 2))
    # a churn-specific term widens the high-churn one MORE
    withchurn = D.forward_sd(prior_sd, churn, 0.5, 0.75)
    assert withchurn[1] > withchurn[0]
    assert withchurn[1] == pytest.approx(np.sqrt(0.3 ** 2 + 0.5 ** 2 + 0.75 ** 2))


def test_classify_position_pass_rush_groups():
    assert D.classify_position("CB") == (True, False)     # secondary → pass only
    assert D.classify_position("DT") == (False, True)     # interior line → rush only
    assert D.classify_position("DE") == (True, True)      # edge → both fronts
    assert D.classify_position("LB") == (False, True)
    assert D.classify_position("QB") == (False, False)    # unknown/offense → neither
    assert D.classify_position("") == (False, False)


# ── the opponent-adjusted mixed-model fit (SYNTHETIC plays; no IO) ────────────────────────────────
def _synthetic_plays(seed: int = 0) -> pd.DataFrame:
    """8 teams; team 'D0' is an ELITE defense (allows far less EPA), 'D7' a SIEVE. Offenses vary too,
    and the schedule is confounded (D0 happens to face strong offenses) so a RAW mean would understate
    D0 — the exact case opponent-adjustment must correct."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    off_skill = {t: v for t, v in zip(teams, np.linspace(0.15, -0.15, 8))}   # T0 best offense
    def_allow = {t: v for t, v in zip(teams, np.linspace(-0.20, 0.20, 8))}   # T0 best defense (allows less)
    rows = []
    for _ in range(6000):
        o, d = rng.choice(teams), rng.choice(teams)
        if o == d:
            continue
        # confound: the elite defense faces the elite offenses more often
        epa = off_skill[o] + def_allow[d] + rng.normal(0, 0.8)
        rows.append({"posteam": o, "defteam": d, "epa": epa,
                     "success": float(epa > 0), "yards_gained": 0.0})
    return pd.DataFrame(rows)


@pytest.mark.slow  # the mixed-model variance-component optimizer (multi-start Nelder-Mead) is variable
def test_fit_unit_strength_recovers_ordering_and_is_opponent_adjusted():
    plays = _synthetic_plays()
    out = D.fit_unit_strength(plays, metric="epa")
    assert set(out["team"]) == {f"T{i}" for i in range(8)}
    # higher strength_z ⇒ stronger D (allows less EPA). The best/worst land in the top/bottom two
    # (adjacent teams near the extremes can swap under noise — the ρ check below is the robust one).
    ordered = out.sort_values("strength_z", ascending=False)["team"].tolist()
    assert "T0" in ordered[:2] and "T7" in ordered[-2:]
    # opponent-adjusted effect recovers the TRUE def_allow ranking (the confound would break a RAW mean)
    from scipy.stats import spearmanr
    truth = {f"T{i}": v for i, v in enumerate(np.linspace(-0.20, 0.20, 8))}
    rho = spearmanr(out["def_effect"], out["team"].map(truth))[0]
    assert rho > 0.85
    # honest posterior sd present + finite
    assert (out["strength_z_sd"] > 0).all()


def test_fit_unit_strength_skips_thin_slice():
    assert D.fit_unit_strength(pd.DataFrame({"posteam": [], "defteam": [], "epa": []})).empty
    tiny = pd.DataFrame({"posteam": ["A"] * 10, "defteam": ["B"] * 10, "epa": [0.1] * 10,
                         "success": [1.0] * 10, "yards_gained": [0.0] * 10})
    assert D.fit_unit_strength(tiny).empty     # < MIN_PLAYS_PER_UNIT


# ── leakage-safe forward-projection wiring (injected frames, no IO) ───────────────────────────────
def _strength_frame(season: int) -> pd.DataFrame:
    rows = []
    for unit in D.UNITS:
        for i, t in enumerate([f"T{j}" for j in range(4)]):
            z = [1.5, 0.5, -0.5, -1.5][i]
            rows.append({"season": season, "unit": unit, "team": t, "def_effect": -z * 0.05,
                         "def_effect_sd": 0.3, "strength_z": z, "strength_z_sd": 0.3,
                         "raw_epa_allowed": -z * 0.05, "raw_success_allowed": 0.45, "plays": 500})
    return pd.DataFrame(rows)


def _continuity_frame() -> pd.DataFrame:
    rows = []
    churn = {"T0": 0.1, "T1": 0.8, "T2": 0.3, "T3": 0.5}
    for unit in D.UNITS:
        for t, c in churn.items():
            rows.append({"team": t, "unit": unit, "returning_share": 1 - c, "churn": c,
                         "incoming_veteran_share": 0.2, "prior_snaps": 1000.0,
                         "top_losses": "X", "top_adds": "Y"})
    return pd.DataFrame(rows)


def test_prior_strength_is_leakage_safe():
    # projecting 2024 must use ONLY ≤ 2023 rows, never the 2024 fit
    strengths = pd.concat([_strength_frame(2023), _strength_frame(2024)], ignore_index=True)
    prior = D._prior_strength(strengths, 2024, D.DefenseConfig(name="p", opp_adjust=True, window=1))
    assert not prior.empty and set(prior["unit"]) == set(D.UNITS)
    # single-season window ⇒ prior_z equals the 2023 z exactly (no 2024 leakage)
    t0 = prior[(prior.unit == "pass") & (prior.team == "T0")].iloc[0]
    assert t0["prior_z"] == pytest.approx(1.5)


def test_build_forward_defense_shape_and_churn_effects():
    strengths = _strength_frame(2023)
    cont = _continuity_frame()
    cfg = D.DefenseConfig(name="c", opp_adjust=True, window=1, churn_shrink_k=0.5,
                          forward_noise=0.5, churn_widen_k=0.5)
    fwd = D.build_forward_defense(None, 2024, config=cfg, strengths=strengths, continuity=cont)
    assert len(fwd) == 4
    for c in D.SERVING_COLUMNS:
        assert c in fwd.columns
    # churn shrinks the point toward the mean, MORE for the higher-churn team (T1 0.8 vs T0 0.1)
    t0 = fwd[fwd.team == "T0"].iloc[0]
    t1 = fwd[fwd.team == "T1"].iloc[0]
    ratio0 = t0["pass_def_strength"] / t0["pass_prior_strength"]   # retained fraction
    ratio1 = t1["pass_def_strength"] / t1["pass_prior_strength"]
    assert ratio0 == pytest.approx(1 - 0.5 * 0.1)   # low churn ⇒ retains most
    assert ratio1 == pytest.approx(1 - 0.5 * 0.8)   # high churn ⇒ shrunk hard
    assert ratio1 < ratio0
    # a churn-specific widen makes the high-churn team's sd larger
    assert t1["pass_def_strength_sd"] > t0["pass_def_strength_sd"]


def test_load_forward_defense_requires_lake_or_con():
    with pytest.raises(RuntimeError):
        D.load_forward_defense(2099, con=None, from_lake=False)
