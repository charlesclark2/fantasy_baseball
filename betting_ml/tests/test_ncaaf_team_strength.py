"""NCAAF-P1.2 — team-strength mixed-effects model guards.

Fast-gate only: pure numpy/pandas over SYNTHETIC data, no DuckDB, no S3, no `pipeline`
import (the fast gate has no dbt manifest — CLAUDE.md's fast-gate rule).

What these tests are actually for:
  * the solver recovers a known truth (otherwise every downstream number is decoration);
  * partial pooling demonstrably SHRINKS a thin sample toward its conference (the whole
    reason this model exists rather than a per-team regression);
  * the leakage contract holds — including the specific way P1.1's postseason-week bug
    would manifest here, which is why one test builds a season whose raw `week` ordering
    disagrees with its date ordering;
  * a NULL covariate stays "unknown" instead of silently becoming zero.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from quant_sports_intel_models.football.ncaaf.models.hierarchical import (
    Block,
    DesignSpec,
    fit,
    marginal_loglik,
    solve_posterior,
)
from quant_sports_intel_models.football.ncaaf.models import team_strength as ts


def _schedule_only_next_season(sim: dict, next_season: int) -> pd.DataFrame:
    """The scheduled team universe for a season with NO completed games (the P0.7 roll-forward /
    upcoming-season shape): reuse the league membership, tag it `next_season`."""
    league = sim["team_games"][["team_id", "team", "conference"]].drop_duplicates()
    out = league.copy()
    out.insert(0, "season", next_season)
    return out.reset_index(drop=True)


def test_upcoming_season_emits_a_preseason_prior_from_schedule_only():
    """A season present ONLY in `schedule_teams` (no completed games) must emit its week-1
    pre-season prior — the NCAAF-P0.7 cold-start: covariate-only strengths so a 2026 futures
    board can render before a single game is played."""
    sim = _simulate(seasons=(2014, 2015, 2016, 2017))
    next_season = 2018
    sched = _schedule_only_next_season(sim, next_season)

    run = ts.run_strength(
        games=sim["games"], team_games=sim["team_games"], roster=sim["roster"],
        coaching=sim["coaching"], schedule_teams=sched,
    )
    wk = run.weekly
    up = wk[wk["season"] == next_season]
    # It emitted, exactly one (pre-season) as-of week, one row per team, all finite + bounded.
    assert not up.empty, "the upcoming (schedule-only) season produced no rows"
    assert sorted(up["as_of_week"].unique()) == [1], "should emit ONLY the week-1 pre-season prior"
    assert up["team_id"].nunique() == len(sched), "one pre-season row per scheduled team"
    assert (up["games_in_window"] == 0).all(), "the pre-season prior must condition on 0 games"
    assert np.isfinite(up["strength_margin"]).all()
    # sd is strictly positive and within the 50-pt plausibility ceiling (run_team_strength gate 7).
    assert (up["strength_margin_sd"] > 0).all() and (up["strength_margin_sd"] < 50.0).all()


def test_schedule_teams_is_backward_compatible_for_played_seasons():
    """Passing `schedule_teams` for ALREADY-PLAYED seasons must not change their output — the
    completed universe is canonical (dedup keeps the fact rows)."""
    sim = _simulate(seasons=(2014, 2015, 2016, 2017))
    league = sim["team_games"][["season", "team_id", "team", "conference"]].drop_duplicates()

    base = ts.run_strength(sim["games"], sim["team_games"], sim["roster"], sim["coaching"])
    withsched = ts.run_strength(sim["games"], sim["team_games"], sim["roster"], sim["coaching"],
                                schedule_teams=league)
    a = base.weekly.sort_values(["season", "team_id", "as_of_week"]).reset_index(drop=True)
    b = withsched.weekly.sort_values(["season", "team_id", "as_of_week"]).reset_index(drop=True)
    assert a.shape == b.shape
    pd.testing.assert_series_equal(a["strength_margin"], b["strength_margin"], check_exact=False,
                                   atol=1e-9, rtol=0)


# ══════════════════════════════════════════════════════════════════════════════════════
# Synthetic league
# ══════════════════════════════════════════════════════════════════════════════════════

_CONFS = ["Alpha", "Beta", "Gamma", "Delta"]
_TEAMS_PER_CONF = 8
_N_WEEKS = 10


def _league() -> pd.DataFrame:
    rows = []
    for ci, conf in enumerate(_CONFS):
        for t in range(_TEAMS_PER_CONF):
            tid = ci * 100 + t
            rows.append({"team_id": tid, "team": f"{conf}-{t}", "conference": conf})
    return pd.DataFrame(rows)


def _simulate(
    seasons=(2014, 2015, 2016, 2017),
    seed: int = 7,
    hfa: float = 3.0,
    scramble_postseason_week: bool = False,
) -> dict[str, pd.DataFrame]:
    """A league with real conference-level and team-level structure, plus a talent covariate.

    Conference means are genuinely different (Alpha strong, Delta weak) so shrinkage toward
    the conference is the right behaviour and can be measured. `team_talent` is correlated
    with true strength so the pre-season covariate has something to find.
    """
    rng = np.random.default_rng(seed)
    league = _league()
    conf_mean = {"Alpha": 9.0, "Beta": 3.0, "Gamma": -3.0, "Delta": -9.0}

    games, team_games, roster, coaching = [], [], [], []
    truth = {}
    for season in seasons:
        theta = {}
        for _, r in league.iterrows():
            theta[r["team_id"]] = conf_mean[r["conference"]] + rng.normal(0, 6.0)
        truth[season] = dict(theta)

        for _, r in league.iterrows():
            t = r["team_id"]
            roster.append(
                {
                    "season": season,
                    "team": r["team"],
                    "returning_ppa_pct": float(np.clip(rng.normal(0.6, 0.15), 0, 1)),
                    "roster_continuity_pct": float(np.clip(rng.normal(0.7, 0.1), 0, 1)),
                    "portal_net_stars": float(rng.normal(0, 5)),
                    "portal_data_covered": season >= 2016,
                    # Correlated with truth (r ~ 0.45) so the covariate is genuinely
                    # informative, but NOT so predictive that it explains theta outright —
                    # otherwise the team random effect has nothing left to do and the
                    # tests stop exercising partial pooling from game evidence at all.
                    "team_talent": float(theta[t] * 10 + rng.normal(0, 120)),
                }
            )
            coaching.append(
                {
                    "season": season,
                    "team": r["team"],
                    "hc_change_from_prev": bool(rng.random() < 0.15),
                    "is_first_year_at_school": bool(rng.random() < 0.2),
                    "hc_recent_sp_overall": float(rng.normal(0, 8)),
                }
            )

        base = pd.Timestamp(f"{season}-09-01")
        gid = season * 10_000
        for week in range(1, _N_WEEKS + 1):
            order = league.sample(frac=1.0, random_state=season * 100 + week)["team_id"].tolist()
            date = base + pd.Timedelta(days=7 * (week - 1))
            for i in range(0, len(order) - 1, 2):
                h, a = order[i], order[i + 1]
                neutral = bool(rng.random() < 0.05)
                margin = (
                    (0.0 if neutral else hfa)
                    + theta[h]
                    - theta[a]
                    + rng.normal(0, 14.0)
                )
                total = 52 + rng.normal(0, 9)
                hp, ap = (total + margin) / 2, (total - margin) / 2
                gid += 1
                # `week` (CFBD-native) vs `season_order_week` (the safe ordering). When
                # `scramble_postseason_week` is on, the last two weeks pretend to be a
                # postseason that restarts `week` at 1 — exactly the P1.1 bug shape.
                raw_week = (week - _N_WEEKS + 2) if (scramble_postseason_week and week > _N_WEEKS - 2) else week
                games.append(
                    {
                        "season": season,
                        "game_id": gid,
                        "week": raw_week,
                        "season_order_week": week,
                        "game_date": date.date(),
                        "home_team_id": h,
                        "home_conference": league.set_index("team_id").loc[h, "conference"],
                        "away_team_id": a,
                        "away_conference": league.set_index("team_id").loc[a, "conference"],
                        "is_neutral_site": neutral,
                        "home_margin": margin,
                    }
                )
                for tid, opp, is_home, pts in ((h, a, True, hp), (a, h, False, ap)):
                    row = league.set_index("team_id").loc[tid]
                    orow = league.set_index("team_id").loc[opp]
                    team_games.append(
                        {
                            "season": season,
                            "game_id": gid,
                            "week": raw_week,
                            "season_order_week": week,
                            "game_date": date.date(),
                            "team_id": tid,
                            "team": row["team"],
                            "conference": row["conference"],
                            "opponent_team_id": opp,
                            "opponent_conference": orow["conference"],
                            "is_home": is_home,
                            "is_neutral_site": neutral,
                            "points_for": pts,
                        }
                    )
    return {
        "games": pd.DataFrame(games),
        "team_games": pd.DataFrame(team_games),
        "roster": pd.DataFrame(roster),
        "coaching": pd.DataFrame(coaching),
        "truth": truth,
        "league": league,
    }


@pytest.fixture(scope="module")
def sim():
    return _simulate()


@pytest.fixture(scope="module")
def run(sim):
    return ts.run_strength(
        games=sim["games"],
        team_games=sim["team_games"],
        roster=sim["roster"],
        coaching=sim["coaching"],
        config=ts.StrengthConfig(hyper_lookback_seasons=2, fit_points_model=True),
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# 1. The solver
# ══════════════════════════════════════════════════════════════════════════════════════


def test_solver_recovers_known_coefficients():
    """A ridge with a near-flat prior must reproduce OLS on a well-identified design."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 4))
    beta = np.array([2.0, -1.0, 0.5, 3.0])
    y = X @ beta + rng.normal(0, 0.5, 500)
    spec = DesignSpec((Block("fixed", ("a", "b", "c", "d"), penalized=False),))
    mean, cov = solve_posterior(X, y, np.ones(500), spec, sigma2=0.25, variances={})
    assert np.allclose(mean, beta, atol=0.1)
    # posterior sd must be positive and small on 500 clean observations
    assert np.all(np.sqrt(np.diag(cov)) < 0.1)


def test_marginal_likelihood_prefers_the_true_variance():
    """The marginal likelihood must peak near the tau that generated the effects."""
    rng = np.random.default_rng(1)
    n, p = 400, 20
    X = rng.normal(size=(n, p))
    true_tau2 = 4.0
    b = rng.normal(0, np.sqrt(true_tau2), p)
    y = X @ b + rng.normal(0, 1.0, n)
    spec = DesignSpec((Block("g", tuple(f"c{i}" for i in range(p))),))
    lls = {
        tau2: marginal_loglik(X, y, np.ones(n), spec, sigma2=1.0, variances={"g": tau2})
        for tau2 in (0.05, 0.5, 4.0, 40.0, 400.0)
    }
    assert max(lls, key=lls.get) == pytest.approx(true_tau2)


def test_fit_with_no_observations_returns_the_prior():
    """As-of week 1 has an empty window; the posterior must be the prior, not a crash."""
    spec = DesignSpec((Block("team", ("t1", "t2")),))
    post = fit(np.zeros((0, 2)), np.zeros(0), spec, init_tau2=9.0, init_sigma2=100.0)
    assert post.n_obs == 0
    assert np.allclose(post.mean, 0.0)
    # sd collapses to the prior sd
    assert np.allclose(np.sqrt(np.diag(post.cov)), 3.0, rtol=1e-3)


# ══════════════════════════════════════════════════════════════════════════════════════
# 2. Partial pooling — the reason the model exists
# ══════════════════════════════════════════════════════════════════════════════════════


def test_thin_sample_is_shrunk_toward_the_conference():
    """A team with ONE freak result must not be trusted at face value.

    PAIRED design: the same league fit twice, differing only in that one Delta (weak-
    conference) team's week-1 game is rewritten as a 50-point blowout. Comparing that team
    against ITSELF isolates the shrinkage — comparing it against other teams would just
    measure their different true strengths.

    The unshrunk answer is the whole residual: a single-game least-squares fit would move
    the estimate by ~the full surprise (tens of points). Partial pooling must absorb most
    of it, because one game against one opponent is not evidence of a 50-point team.
    """
    sim = _simulate(seasons=(2014, 2015), seed=3)
    target, season = 300, 2015

    boosted = sim["games"].copy()
    mask = (boosted["season"] == season) & (boosted["season_order_week"] == 1)
    home_idx = boosted[mask & (boosted["home_team_id"] == target)].index
    away_idx = boosted[mask & (boosted["away_team_id"] == target)].index
    if len(home_idx):
        original = float(boosted.loc[home_idx[0], "home_margin"])
        boosted.loc[home_idx, "home_margin"] = 50.0
        surprise = 50.0 - original
    else:
        original = float(boosted.loc[away_idx[0], "home_margin"])
        boosted.loc[away_idx, "home_margin"] = -50.0
        surprise = abs(-50.0 - original)

    cfg = ts.StrengthConfig(hyper_lookback_seasons=1, fit_points_model=False)
    kw = dict(
        team_games=sim["team_games"], roster=sim["roster"], coaching=sim["coaching"],
        config=cfg, seasons=[season],
    )
    base = ts.run_strength(games=sim["games"], **kw)
    boost = ts.run_strength(games=boosted, **kw)

    def _at(run, week):
        w = run.weekly[(run.weekly["season"] == season) & (run.weekly["as_of_week"] == week)]
        return float(w.loc[w["team_id"] == target, "strength_margin"].iloc[0])

    moved = _at(boost, 2) - _at(base, 2)
    assert moved > 0.5, f"a 50-point win moved the estimate by only {moved:.2f} pts"
    shrinkage = moved / surprise
    assert shrinkage < 0.5, (
        f"n=1 estimate absorbed {shrinkage:.0%} of a {surprise:.0f}-point surprise — "
        f"that is not partial pooling"
    )
    # Week 1 (before the game) must be untouched: the boost is in the future there.
    assert _at(boost, 1) == pytest.approx(_at(base, 1))


def test_uncertainty_shrinks_as_games_accumulate():
    """More evidence must mean a tighter posterior. If not, the sd is decoration."""
    sim = _simulate(seasons=(2014, 2015), seed=11)
    r = ts.run_strength(
        games=sim["games"],
        team_games=sim["team_games"],
        roster=sim["roster"],
        coaching=sim["coaching"],
        config=ts.StrengthConfig(hyper_lookback_seasons=1, fit_points_model=False),
        seasons=[2015],
    )
    by_week = r.weekly.groupby("as_of_week")["strength_margin_sd"].mean()
    assert by_week.iloc[-1] < by_week.iloc[0], "posterior sd did not tighten over the season"


def test_estimates_correlate_with_the_truth_they_were_simulated_from(run, sim):
    """End-of-season strength must track the theta that generated the games.

    The bar depends on how much data the season's HYPERPARAMETERS were fit on, and that is
    a real property of the model, not a test convenience. The first emitted season has only
    ONE prior season to learn `tau_team` / `tau_conference` / the covariate coefficients
    from, so its shrinkage is calibrated on a thin base and its estimates are measurably
    weaker. That is why `hyper_n_prior_seasons` / `hyper_n_games` are emitted columns — a
    consumer (P1.3/P1.4) can see it and down-weight rather than discover it the hard way.

    ⚠️ This synthetic league is ~160 games/season; real FBS is ~800. The thin-base season
    is therefore substantially worse HERE than it will be on real data.
    """
    final = run.weekly.sort_values("as_of_week").groupby(["season", "team_id"]).tail(1)
    for season in sorted(final["season"].unique()):
        s = final[final["season"] == season]
        truth = pd.Series(sim["truth"][season])
        est = s.set_index("team_id")["strength_margin"]
        rho = float(np.corrcoef(est.values, truth.reindex(est.index).values)[0, 1])
        thin = int(s["hyper_n_prior_seasons"].iloc[0]) < 2
        floor = 0.60 if thin else 0.75
        assert rho > floor, (
            f"season {season}: strength/truth correlation only {rho:.2f} "
            f"(floor {floor}, hyper fit on {s['hyper_n_prior_seasons'].iloc[0]} prior season(s))"
        )


def test_thin_hyperparameter_base_is_disclosed_not_hidden(run):
    """A consumer must be able to SEE that the first emitted season is thinly calibrated."""
    w = run.weekly
    assert {"hyper_n_prior_seasons", "hyper_n_games"} <= set(w.columns)
    first = w["season"].min()
    assert int(w.loc[w["season"] == first, "hyper_n_prior_seasons"].iloc[0]) == 1
    later = w[w["season"] > first]
    assert (later["hyper_n_prior_seasons"] >= 2).all()


def test_boundary_avoiding_prior_keeps_the_team_level_alive():
    """Without it, ML collapses tau_team to ~0 and every team equals its conference.

    This is a regression guard on a bug that was live during development: on a single
    season the raw marginal likelihood genuinely PEAKS at tau_team = 0, which silently
    deletes the team level of a team-strength model.
    """
    sim = _simulate(seasons=(2014, 2015), seed=7)
    cov = ts.standardize_covariates(
        ts.prepare_covariates(
            sim["roster"],
            sim["coaching"],
            sim["team_games"][["season", "team_id", "team", "conference"]].drop_duplicates(),
        ).assign(prior_strength=np.nan)
    )
    cfg = ts.StrengthConfig(fit_points_model=False)
    h = ts.fit_hyperparameters(sim["games"], sim["team_games"], cov, [2014], cfg, kind="margin")
    tau_team = math.sqrt(h.variances["team"])
    assert tau_team > 0.5, f"tau_team collapsed to {tau_team:.4f} — the team level is dead"


# ══════════════════════════════════════════════════════════════════════════════════════
# 3. The leakage contract
# ══════════════════════════════════════════════════════════════════════════════════════


def test_week_one_window_is_empty_and_is_a_pure_preseason_prior(run):
    wk1 = run.weekly[run.weekly["as_of_week"] == 1]
    assert len(wk1) > 0
    assert (wk1["games_in_window"] == 0).all()
    # with no games, strength is entirely the covariate-driven prior mean
    assert np.allclose(wk1["strength_team_component"], 0.0, atol=1e-6)
    assert np.allclose(
        wk1["strength_margin"],
        wk1["strength_covariate_component"] + wk1["strength_conference_component"],
        atol=1e-6,
    )


def test_seed_season_is_never_emitted(run):
    assert run.weekly["season"].min() > ts.SEED_SEASON
    assert not run.weekly["hyper_in_sample"].any()


def test_window_uses_season_order_week_not_raw_week():
    """The P1.1 bug, reproduced: raw `week` restarts, `season_order_week` does not.

    Fitting the same league twice — once with a sane raw `week`, once with a scrambled
    postseason-style `week` — must give IDENTICAL strengths, because the model must never
    touch `week`. If it did, the scrambled run would fold late-season games into week 1.
    """
    clean = _simulate(seasons=(2014, 2015), seed=5, scramble_postseason_week=False)
    scrambled = _simulate(seasons=(2014, 2015), seed=5, scramble_postseason_week=True)
    cfg = ts.StrengthConfig(hyper_lookback_seasons=1, fit_points_model=False)
    kw = dict(config=cfg, seasons=[2015])
    a = ts.run_strength(clean["games"], clean["team_games"], clean["roster"], clean["coaching"], **kw)
    b = ts.run_strength(
        scrambled["games"], scrambled["team_games"], scrambled["roster"], scrambled["coaching"], **kw
    )
    merged = a.weekly.merge(
        b.weekly, on=["season", "team_id", "as_of_week"], suffixes=("_clean", "_scrambled")
    )
    assert len(merged) == len(a.weekly)
    assert np.allclose(merged["strength_margin_clean"], merged["strength_margin_scrambled"])


def test_a_later_result_cannot_change_an_earlier_weeks_estimate(sim):
    """Rewrite the LAST week's results; every earlier as-of week must be untouched."""
    cfg = ts.StrengthConfig(hyper_lookback_seasons=2, fit_points_model=False)
    base = ts.run_strength(
        sim["games"], sim["team_games"], sim["roster"], sim["coaching"], config=cfg, seasons=[2017]
    )
    tampered_games = sim["games"].copy()
    last = tampered_games["season_order_week"].max()
    mask = (tampered_games["season"] == 2017) & (tampered_games["season_order_week"] == last)
    tampered_games.loc[mask, "home_margin"] = 70.0
    tampered = ts.run_strength(
        tampered_games, sim["team_games"], sim["roster"], sim["coaching"], config=cfg, seasons=[2017]
    )
    early_a = base.weekly[base.weekly["as_of_week"] <= last]
    early_b = tampered.weekly[tampered.weekly["as_of_week"] <= last]
    merged = early_a.merge(early_b, on=["season", "team_id", "as_of_week"], suffixes=("_a", "_b"))
    assert np.allclose(merged["strength_margin_a"], merged["strength_margin_b"]), (
        "a future result changed a past as-of week — the fit window is leaking"
    )


# ══════════════════════════════════════════════════════════════════════════════════════
# 4. NULL handling — unknown must not become zero
# ══════════════════════════════════════════════════════════════════════════════════════


def test_missing_covariate_becomes_season_mean_plus_an_explicit_indicator():
    league = _league()
    team_seasons = league.assign(season=2020)[["season", "team_id", "team", "conference"]]
    roster = pd.DataFrame(
        {
            "season": 2020,
            "team": league["team"],
            "returning_ppa_pct": [np.nan] * 4 + [0.5] * (len(league) - 4),
            "roster_continuity_pct": 0.7,
            "portal_net_stars": 1.0,
            "portal_data_covered": True,
            "team_talent": 500.0,
        }
    )
    coaching = pd.DataFrame(
        {
            "season": 2020,
            "team": league["team"],
            "hc_change_from_prev": False,
            "is_first_year_at_school": False,
            "hc_recent_sp_overall": 0.0,
        }
    )
    cov = ts.prepare_covariates(roster, coaching, team_seasons)
    assert cov["returning_ppa_pct"].isna().sum() == 4, "a NULL covariate must stay NULL on input"

    std = ts.standardize_covariates(cov)
    assert (std["returning_ppa_pct_missing"].sum()) == 4
    # the four unknown teams sit at the season mean (0 in z-space), NOT at a fabricated value
    assert np.allclose(std.loc[std["returning_ppa_pct_missing"] == 1, "returning_ppa_pct_z"], 0.0)


def test_pre_2021_portal_data_is_unknown_not_zero():
    """`portal_data_covered = false` means "no data", and the mart coalesces counts to 0.

    Reading that 0 at face value would tell the model every pre-portal-era roster was
    perfectly stable. It must be turned back into a NULL.
    """
    league = _league().head(4)
    team_seasons = league.assign(season=2019)[["season", "team_id", "team", "conference"]]
    roster = pd.DataFrame(
        {
            "season": 2019,
            "team": league["team"],
            "returning_ppa_pct": 0.6,
            "roster_continuity_pct": 0.7,
            "portal_net_stars": 0.0,          # the mart's coalesce-to-0
            "portal_data_covered": False,     # ... which means UNKNOWN
            "team_talent": 500.0,
        }
    )
    coaching = pd.DataFrame(
        {
            "season": 2019,
            "team": league["team"],
            "hc_change_from_prev": False,
            "is_first_year_at_school": False,
            "hc_recent_sp_overall": 0.0,
        }
    )
    cov = ts.prepare_covariates(roster, coaching, team_seasons)
    assert cov["portal_net_stars"].isna().all()


def test_null_boolean_coaching_flag_does_not_become_false():
    """`hc_change_from_prev` is NULL at the 2014 floor — unknown, not "no change"."""
    league = _league().head(3)
    team_seasons = league.assign(season=2014)[["season", "team_id", "team", "conference"]]
    roster = pd.DataFrame(
        {
            "season": 2014,
            "team": league["team"],
            "returning_ppa_pct": 0.6,
            "roster_continuity_pct": np.nan,
            "portal_net_stars": 0.0,
            "portal_data_covered": False,
            "team_talent": np.nan,
        }
    )
    coaching = pd.DataFrame(
        {
            "season": 2014,
            "team": league["team"],
            "hc_change_from_prev": [None, None, None],
            "is_first_year_at_school": [True, False, None],
            "hc_recent_sp_overall": [1.0, np.nan, 2.0],
        }
    )
    cov = ts.prepare_covariates(roster, coaching, team_seasons)
    assert cov["hc_change_from_prev"].isna().all()
    assert cov["is_first_year_at_school"].isna().sum() == 1


# ══════════════════════════════════════════════════════════════════════════════════════
# 5. Output contract
# ══════════════════════════════════════════════════════════════════════════════════════


def test_output_grain_and_columns(run):
    w = run.weekly
    assert not w.duplicated(subset=["season", "team_id", "as_of_week"]).any()
    for col in (
        "sport", "season", "team_id", "team", "conference", "as_of_week",
        "games_in_window", "has_sufficient_sample",
        "strength_margin", "strength_margin_sd",
        "strength_conference_component", "strength_covariate_component", "strength_team_component",
        "strength_offense", "strength_offense_sd", "strength_defense", "strength_defense_sd",
        "home_field_advantage", "residual_sigma", "tau_team", "tau_conference",
        "model_version",
    ):
        assert col in w.columns, f"missing output column {col}"
    assert (w["sport"] == "ncaaf").all()
    assert np.isfinite(w["strength_margin"]).all()
    assert (w["strength_margin_sd"] > 0).all()


def test_strength_decomposes_into_its_three_reported_components(run):
    w = run.weekly
    total = (
        w["strength_conference_component"]
        + w["strength_covariate_component"]
        + w["strength_team_component"]
    )
    assert np.allclose(total, w["strength_margin"], atol=1e-6)


def test_home_field_advantage_is_recovered(run):
    """The simulation used +3 points of home field; the fit must find roughly that."""
    hfa = run.weekly["home_field_advantage"].unique()
    assert np.all((hfa > 1.0) & (hfa < 6.0)), f"implausible home-field estimate {hfa}"


def test_offense_plus_defense_tracks_margin_strength(run):
    """The two models are INDEPENDENT fits; they must still agree on who is good.

    ⚠️ It is `offense + defense`, not minus — see the sign convention in
    `build_points_design`. With `points_for = base + hfa + O_team - D_opponent` and D
    emitted as points PREVENTED, a team's margin is
        (O_t - D_o) - (O_o - D_t) = (O_t + D_t) - (O_o + D_o)
    so the team's margin contribution is the SUM. Subtracting them is the natural-looking
    mistake and it silently produces a number near zero for every team.
    """
    final = run.weekly.sort_values("as_of_week").groupby(["season", "team_id"]).tail(1)
    net = final["strength_offense"] + final["strength_defense"]
    rho = float(np.corrcoef(net.values, final["strength_margin"].values)[0, 1])
    assert rho > 0.85, f"offense+defense net and margin strength disagree (rho={rho:.2f})"


def test_seasons_argument_still_fits_predecessors(sim):
    """Emitting only 2017 must NOT silently skip the seasons its covariates depend on."""
    r = ts.run_strength(
        sim["games"], sim["team_games"], sim["roster"], sim["coaching"],
        config=ts.StrengthConfig(hyper_lookback_seasons=2, fit_points_model=False),
        seasons=[2017],
    )
    assert set(r.weekly["season"].unique()) == {2017}
    # 2017's hyperparameters must come from real prior seasons, not from itself
    assert not r.weekly["hyper_in_sample"].any()
    assert "2017" not in str(r.weekly["hyper_seasons"].iloc[0]).split(",")
