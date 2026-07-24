"""NCAAF-P1.5 — unit guards for the pure season-simulation engine.

Fast-gate compatible: imports only `betting_ml` + the pure `season_simulation` module (no `pipeline`,
no lake/DuckDB IO). Every test builds a synthetic season in-memory and runs a small Monte-Carlo.

The properties pinned here are the ones a silent regression would break invisibly:
  * the futures-probability INVARIANTS (a champion market sums to 1; the field is exactly 12; 4 byes;
    2 finalists; each real conference crowns exactly one champion, an independent none);
  * the ONCE-PER-SEASON strength draw preserves `margin = offense + defense` exactly (the identity
    the totals leg relies on) and injects correlated season strength;
  * the DOUBLE-COUNT discipline — the sim uses σ₀ ONLY (fixed_strength), never the per-game k² term;
  * PLAYED games are fixed to their realized result (mid-season conditioning);
  * the bracket is correct (a dominant #1 seed wins; finalists are the two semifinal winners);
  * determinism under a fixed seed; and strength MONOTONICITY (stronger ⇒ higher title odds).
"""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from quant_sports_intel_models.football.ncaaf.models.ncaaf_game_distribution import (
    NcaafGameDistributionParams,
)
from quant_sports_intel_models.football.ncaaf.models import season_simulation as ss


# --------------------------------------------------------------------------- helpers

def _params(sigma0: float = 15.6) -> NcaafGameDistributionParams:
    """A strength_posterior served-params object; the sim reads ONLY σ₀ (fixed_strength)."""
    return NcaafGameDistributionParams(
        form="strength_posterior", sigma_margin=16.1, sigma_total=16.7, rho=0.05,
        sigma0_margin=sigma0, k_margin=0.57, sigma0_total=sigma0 + 0.8, k_total=0.50,
        learner="ridge", contract="strength_only",
    )


def _synthetic_league(n_confs: int = 2, per_conf: int = 8, n_ind: int = 4, seed: int = 0):
    """Two conferences (round-robin, conference games) + some independents + cross-conference games."""
    rng = np.random.default_rng(seed)
    conf_names = ["SEC", "Big Ten", "ACC", "Big 12"][:n_confs]
    posts: list[ss.TeamPosterior] = []
    tid = 0
    conf_ids: dict[str, list[int]] = {}
    for c in conf_names:
        ids = []
        for _ in range(per_conf):
            m = float(rng.normal(0, 12))
            posts.append(ss.TeamPosterior(tid, f"T{tid}", c, m, 5.0, m / 2, 6.0, m / 2, 6.0))
            ids.append(tid)
            tid += 1
        conf_ids[c] = ids
    for _ in range(n_ind):
        m = float(rng.normal(0, 10))
        posts.append(ss.TeamPosterior(tid, f"IND{tid}", "FBS Independents", m, 5, m / 2, 6, m / 2, 6))
        tid += 1

    sched: list[ss.ScheduledGame] = []
    for ids in conf_ids.values():
        for a, b in itertools.combinations(ids, 2):
            sched.append(ss.ScheduledGame(home_id=a, away_id=b, is_conference_game=True))
    all_ids = [p.team_id for p in posts]
    for _ in range(120):
        a, b = rng.choice(all_ids, 2, replace=False)
        sched.append(ss.ScheduledGame(home_id=int(a), away_id=int(b), is_conference_game=False))
    return posts, sched, conf_names


# --------------------------------------------------------------------------- invariants

def test_probability_invariants():
    posts, sched, confs = _synthetic_league()
    board = ss.simulate_season(posts, sched, _params(), hfa=2.3, league_base=27.0,
                               fmt=ss.CfpFormat(), cfg=ss.SeasonSimConfig(n_sims=3000, seed=1))
    teams = board.teams
    assert board.meta["n_teams"] == len(posts)
    # a national champion market sums to 1 (someone always wins); field=12, byes=4, finalists=2 every
    # sim. Tolerance absorbs the board's 5-dp rounding accumulated over ~130 teams.
    assert sum(t["p_natty"] for t in teams) == pytest.approx(1.0, abs=5e-3)
    assert sum(t["p_playoff"] for t in teams) == pytest.approx(12.0, abs=5e-3)
    assert sum(t["p_top_seed"] for t in teams) == pytest.approx(4.0, abs=5e-3)
    assert sum(t["p_reach_final"] for t in teams) == pytest.approx(2.0, abs=5e-3)
    # each real conference crowns exactly one champion; an independent none
    by_conf: dict[str, float] = {}
    for t in teams:
        by_conf[t["conference"]] = by_conf.get(t["conference"], 0.0) + t["p_conf_title"]
    for c in confs:
        assert by_conf[c] == pytest.approx(1.0, abs=5e-3)
    assert by_conf.get("FBS Independents", 0.0) == pytest.approx(0.0, abs=1e-9)
    # an independent can still make the field at-large but never wins a conference title
    for t in teams:
        if t["conference"] in ss.NO_CONFERENCE:
            assert t["p_conf_title"] == 0.0
            assert not t["conf_title_available"]


def test_determinism_under_seed():
    posts, sched, _ = _synthetic_league()
    kw = dict(hfa=2.0, league_base=27.0, fmt=ss.CfpFormat())
    a = ss.simulate_season(posts, sched, _params(), cfg=ss.SeasonSimConfig(n_sims=1500, seed=7), **kw)
    b = ss.simulate_season(posts, sched, _params(), cfg=ss.SeasonSimConfig(n_sims=1500, seed=7), **kw)
    assert [t["p_natty"] for t in a.teams] == [t["p_natty"] for t in b.teams]
    c = ss.simulate_season(posts, sched, _params(), cfg=ss.SeasonSimConfig(n_sims=1500, seed=8), **kw)
    # a different seed must actually change the draw (not a frozen result)
    assert [t["p_natty"] for t in a.teams] != [t["p_natty"] for t in c.teams]


# --------------------------------------------------------------------------- the strength draw

def test_strength_draw_preserves_margin_identity():
    posts, _, _ = _synthetic_league()
    idx = ss.build_team_index(posts)
    rng = np.random.default_rng(3)
    s = ss.draw_season_strengths(idx, 500, rng, sd_scale=1.0)
    # margin = offense + defense EXACTLY, per draw (the identity the totals leg needs)
    np.testing.assert_allclose(s["margin"], s["offense"] + s["defense"], atol=1e-9)
    # the draw is once-per-season: the per-team spread ≈ the posterior sd (correlated across games)
    emp_sd = s["margin"].std(axis=0)
    np.testing.assert_allclose(emp_sd, idx.margin_sd, rtol=0.2)


def test_sd_scale_widens_the_draw():
    posts, sched, _ = _synthetic_league()
    kw = dict(hfa=2.0, league_base=27.0, fmt=ss.CfpFormat())
    tight = ss.simulate_season(posts, sched, _params(),
                               cfg=ss.SeasonSimConfig(n_sims=4000, seed=2, strength_sd_scale=0.1), **kw)
    wide = ss.simulate_season(posts, sched, _params(),
                              cfg=ss.SeasonSimConfig(n_sims=4000, seed=2, strength_sd_scale=2.0), **kw)
    # widening the season-strength draw pushes the favourite's title odds DOWN (more upset room)
    fav_tight = max(tight.teams, key=lambda t: t["strength_margin"])["team"]
    p_tight = next(t["p_natty"] for t in tight.teams if t["team"] == fav_tight)
    p_wide = next(t["p_natty"] for t in wide.teams if t["team"] == fav_tight)
    assert p_wide < p_tight


# --------------------------------------------------------------------------- double-count discipline

def test_sim_uses_sigma0_only_not_the_per_game_strength_term():
    """The season sim must use σ₀ ALONE (fixed_strength) — the strength uncertainty is already in the
    once-per-season draw. `_sigma0` returns σ₀ for the strength_posterior form (NOT the full σ)."""
    p = _params(sigma0=15.6)
    s0_m, s0_t = ss._sigma0(p)
    assert s0_m == pytest.approx(p.sigma0_margin) and s0_m != pytest.approx(p.sigma_margin)
    assert s0_t == pytest.approx(p.sigma0_total)
    # a homoscedastic served form has no separable strength term → σ₀ IS the served σ
    homo = NcaafGameDistributionParams(form="gaussian", sigma_margin=16.0, sigma_total=17.0)
    assert ss._sigma0(homo) == (16.0, 17.0)


# --------------------------------------------------------------------------- played-game conditioning

def test_played_game_is_fixed_not_simulated():
    posts, _, _ = _synthetic_league(n_confs=2, per_conf=4, n_ind=0)
    idx = ss.build_team_index(posts)
    # one game, marked played with a known result → the winner must be deterministic across sims
    sched = [ss.ScheduledGame(home_id=0, away_id=1, is_conference_game=True, played=True, home_win=True)]
    rng = np.random.default_rng(0)
    strengths = ss.draw_season_strengths(idx, 200, rng)
    st = ss.simulate_regular_season(idx, sched, strengths, 2.0, 27.0, _params(), rng)
    assert (st.wins[:, 0] == 1).all()   # team 0 won every sim (the realized result)
    assert (st.wins[:, 1] == 0).all()
    assert (st.losses[:, 1] == 1).all()


# --------------------------------------------------------------------------- bracket correctness

def test_dominant_top_seed_wins_and_bracket_is_consistent():
    """With near-zero game noise and monotone strengths, the #1 committee team wins the natty and the
    field/byes are exactly right."""
    posts: list[ss.TeamPosterior] = []
    # 16 teams across 2 conferences with widely separated strengths → deterministic games
    for t in range(16):
        c = "SEC" if t < 8 else "Big Ten"
        m = float(40 - 3 * t)   # strictly decreasing
        posts.append(ss.TeamPosterior(t, f"T{t}", c, m, 0.001, m / 2, 0.001, m / 2, 0.001))
    sched = [ss.ScheduledGame(home_id=a, away_id=b, is_conference_game=(a // 8 == b // 8))
             for a, b in itertools.combinations(range(16), 2)]
    board = ss.simulate_season(posts, sched, _params(sigma0=0.01), hfa=0.0, league_base=27.0,
                               fmt=ss.CfpFormat(), cfg=ss.SeasonSimConfig(n_sims=800, seed=5))
    top = board.teams[0]
    assert top["team"] == "T0"                      # the strongest team
    assert top["p_natty"] > 0.95                    # near-deterministic dominance
    assert top["p_playoff"] == pytest.approx(1.0, abs=1e-9)
    assert top["p_top_seed"] == pytest.approx(1.0, abs=1e-9)


def test_strength_monotonicity():
    posts, sched, _ = _synthetic_league(seed=11)
    board = ss.simulate_season(posts, sched, _params(), hfa=2.0, league_base=27.0,
                               fmt=ss.CfpFormat(), cfg=ss.SeasonSimConfig(n_sims=4000, seed=1))
    ranked = sorted(board.teams, key=lambda t: t["strength_margin"], reverse=True)
    # the strongest team's natty odds strictly exceed the median team's (a monotone signal)
    strongest = ranked[0]["p_natty"]
    median = ranked[len(ranked) // 2]["p_natty"]
    assert strongest > median


# --------------------------------------------------------------------------- tiebreak key

def test_rank_key_orders_conf_then_overall_then_strength():
    # conference win-pct dominates
    assert ss._rank_key(1.0, 0.0, -300) > ss._rank_key(0.9, 1.0, 300)
    # overall win-pct breaks a conf-pct tie
    assert ss._rank_key(0.8, 0.9, -50) > ss._rank_key(0.8, 0.5, 50)
    # strength breaks an overall tie
    assert ss._rank_key(0.8, 0.8, 10) > ss._rank_key(0.8, 0.8, 5)


def test_no_playoff_mode_gives_conference_board_only():
    posts, sched, confs = _synthetic_league()
    board = ss.simulate_season(posts, sched, _params(), hfa=2.0, league_base=27.0,
                               fmt=ss.CfpFormat(run_playoff=False),
                               cfg=ss.SeasonSimConfig(n_sims=1500, seed=1))
    # conference titles still resolve; the playoff columns are all zero
    assert sum(t["p_conf_title"] for t in board.teams) == pytest.approx(len(confs), abs=5e-3)
    assert all(t["p_natty"] == 0.0 and t["p_playoff"] == 0.0 for t in board.teams)
