"""test_derivative_model_gate.py — Edge Program E2.6 (model-vs-market derivative gate).

Proves the PURE machinery (`betting_ml/utils/derivative_model_gate.py`) + the orchestration's
honest math end-to-end: on EFFICIENT books the gate returns a CLEAN NULL (0 candidates, 0 FDR
survivors), and on a genuinely mispriced corner the DETECTION legs light up (FDR survivors + a
positive-ROI, positive-edge winning config). The deflation (PBO<0.2 tie-conservatism) is verified to
STAY conservative — a saturated tie of correlated winners is NOT certified, which is the whole point.

All synthetic (no S3). Fast gate: every test builds small frames + small draw counts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils import derivative_model_gate as dg
from betting_ml.utils.derivative_eval import devig_pair
from betting_ml.utils.totals_distribution import draw_independent_samples

R_HOME, R_AWAY = 4.0645, 3.3977


# ── pricing ──────────────────────────────────────────────────────────────────────────────────────
def test_price_game_samples_shapes_and_monotone_in_mu():
    rng = np.random.default_rng(0)
    mu_h = np.array([3.0, 5.0]); mu_a = np.array([3.0, 5.0])
    s = dg.price_game_samples(mu_h, mu_a, R_HOME, R_AWAY, rng, n_draws=2000)
    assert set(s) == {"total", "home_total", "away_total"}
    assert s["total"].shape == (2, 2000)
    # a higher-μ game has a higher mean total (the convolution respects the marginals)
    assert s["total"][1].mean() > s["total"][0].mean()
    # total = home_total + away_total, draw-for-draw
    assert np.allclose(s["total"], s["home_total"] + s["away_total"])


def test_prob_over_at_lines_matches_direct_and_handles_kinds():
    rng = np.random.default_rng(1)
    mu_h = np.array([4.5, 4.5]); mu_a = np.array([4.0, 4.0])
    s = dg.price_game_samples(mu_h, mu_a, R_HOME, R_AWAY, rng, n_draws=4000)
    gi = np.array([0, 1, 0]); kind = np.array(["total", "home_total", "away_total"], dtype=object)
    line = np.array([8.5, 4.5, 3.5])
    p = dg.prob_over_at_lines(s, gi, kind, line, chunk=2)
    assert np.isclose(p[0], (s["total"][0] > 8.5).mean())
    assert np.isclose(p[1], (s["home_total"][1] > 4.5).mean())
    assert np.isclose(p[2], (s["away_total"][0] > 3.5).mean())
    assert np.all((p >= 0) & (p <= 1))


# ── bet construction ──────────────────────────────────────────────────────────────────────────────
def _frame(model_p, fair_over, over=-110, under=-110, market=dg.ALT_TOTALS, line=8.5, actual=9):
    n = len(model_p)
    return pd.DataFrame({
        "game_pk": np.arange(n), "season": 2024, "bookmaker_key": "bovada",
        "market": market, "line": float(line), "over_price": over, "under_price": under,
        "model_p_over": model_p, "fair_over": fair_over, "devig_valid": True,
        "actual_total": actual, "game_date": "2024-06-01"})


def test_select_bets_side_and_threshold():
    df = _frame(model_p=[0.60, 0.40, 0.52], fair_over=[0.50, 0.50, 0.50])
    bets = dg.select_bets(df, dg.DerivConfig(dg.ALT_TOTALS, "all", "all", tau=0.05))
    # game 0 edge +0.10 → over; game 1 edge −0.10 → under; game 2 edge +0.02 < τ → skipped
    assert set(bets["game_pk"]) == {0, 1}
    assert bets.set_index("game_pk").loc[0, "bet_side"] == "over"
    assert bets.set_index("game_pk").loc[1, "bet_side"] == "under"


def test_select_bets_ignores_invalid_devig():
    df = _frame(model_p=[0.7], fair_over=[0.5])
    df.loc[0, "devig_valid"] = False
    assert dg.select_bets(df, dg.DerivConfig(dg.ALT_TOTALS, "all", "all", 0.05)).empty


def test_game_level_returns_collapse_correlated_quotes():
    # 3 book-quotes on ONE game → exactly ONE game-level return (mean payoff), not 3 bets.
    df = pd.DataFrame({
        "game_pk": [10, 10, 10], "season": [2024, 2024, 2024], "game_date": ["2024-06-01"] * 3,
        "line": [8.5, 8.5, 8.5], "bet_side": ["over"] * 3, "bet_price": [-110, 100, -105],
        "actual_total": [9, 9, 9], "edge": [0.06, 0.06, 0.06]})
    g = dg.game_level_returns(df)
    assert len(g) == 1 and g.loc[0, "game_pk"] == 10


# ── per-config scoring + oracle floor ──────────────────────────────────────────────────────────────
def test_score_config_positive_roi_when_model_beats_book():
    # over always wins (actual 12 > line 8.5) and model favors over → positive ROI net of vig.
    df = _frame(model_p=[0.7] * 80, fair_over=[0.5] * 80, actual=12, line=8.5)
    df["game_pk"] = np.arange(80)
    c = dg.score_config(df, dg.DerivConfig(dg.ALT_TOTALS, "all", "all", tau=0.05))
    assert c is not None and c["n"] == 80 and c["roi"] > 0 and c["mean_edge"] > 0


def _synth_totals_frame(n_games, seed, *, shade=0.0, shade_only_high=True, truth_draws=6000):
    """Small alt-totals frame: books priced at the TRUE convolved prob (shade=0 → efficient),
    optionally shading the HIGH line by `shade` (the concentrated-mispricing positive control)."""
    from scipy.stats import nbinom
    rng = np.random.default_rng(seed)
    mu_h = rng.uniform(3.6, 5.6, n_games); mu_a = rng.uniform(3.4, 5.2, n_games)
    fh = nbinom.rvs(R_HOME, R_HOME / (R_HOME + mu_h), random_state=rng)
    fa = nbinom.rvs(R_AWAY, R_AWAY / (R_AWAY + mu_a), random_state=rng)
    yh, ya = draw_independent_samples(mu_h, mu_a, R_HOME, rng, r_away=R_AWAY, n_draws=truth_draws)
    tot = yh + ya
    seas = rng.choice([2023, 2024, 2025, 2026], n_games); mon = rng.integers(4, 10, n_games)
    books = ["pinnacle", "draftkings", "fanduel", "betmgm", "bovada"]

    def _am(p, v):
        io = float(np.clip(p + v / 2, 1e-3, 1 - 1e-3))
        return int(round(-100 * io / (1 - io))) if io >= 0.5 else int(round(100 * (1 - io) / io))

    rows = []
    for g in range(n_games):
        gmu = mu_h[g] + mu_a[g]; ll, hl = float(np.floor(gmu) - 0.5), float(np.floor(gmu) + 1.5)
        at = {ll: float((tot[g] > ll).mean()), hl: float((tot[g] > hl).mean())}
        base = dict(game_pk=g, season=int(seas[g]), game_date=f"{int(seas[g])}-{int(mon[g]):02d}-15",
                    mu_home=float(mu_h[g]), mu_away=float(mu_a[g]), is_oos=True,
                    final_home=int(fh[g]), final_away=int(fa[g]))
        for bk in books:
            v = 0.04 if bk == "pinnacle" else float(rng.uniform(0.05, 0.09))
            for ln in (ll, hl):
                sh = shade if (ln == hl or not shade_only_high) else 0.0
                pb = float(np.clip(at[ln] - sh, 1e-3, 1 - 1e-3))
                rows.append({**base, "market": dg.ALT_TOTALS, "bookmaker_key": bk, "line": ln,
                             "over_price": _am(pb, v), "under_price": _am(1 - pb, v)})
    return pd.DataFrame(rows)


def _price(df, n_draws=1500):
    games = df.drop_duplicates("game_pk").reset_index(drop=True)
    gidx = {int(x): i for i, x in enumerate(games["game_pk"])}
    s = dg.price_game_samples(games["mu_home"].to_numpy(float), games["mu_away"].to_numpy(float),
                              R_HOME, R_AWAY, np.random.default_rng(2), n_draws=n_draws)
    df = df.copy()
    df["game_index"] = df["game_pk"].map(gidx)
    df["kind"] = "total"
    df["model_p_over"] = dg.prob_over_at_lines(s, df["game_index"].to_numpy(),
                                               df["kind"].to_numpy(object), df["line"].to_numpy(float))
    dv = df.apply(lambda r: devig_pair(r["over_price"], r["under_price"]), axis=1)
    df["fair_over"] = [x["fair_a"] for x in dv]
    df["devig_valid"] = [bool(x["valid"]) for x in dv]
    fh = games.set_index("game_pk")["final_home"]; fa = games.set_index("game_pk")["final_away"]
    df["actual_total"] = df["game_pk"].map(fh).to_numpy(float) + df["game_pk"].map(fa).to_numpy(float)
    return df


@pytest.mark.slow
def test_efficient_market_is_clean_null():
    """The load-bearing correctness check: a genuinely efficient book (priced at the model's own
    truth) yields NO candidate and NO FDR survivor — the gate does not manufacture an edge."""
    df = _price(_synth_totals_frame(260, seed=7, shade=0.0))
    res = dg.evaluate_market(df, dg.ALT_TOTALS, sorted(df["bookmaker_key"].unique()))
    assert res["candidates"] == []
    assert res["fdr"]["n_survive"] == 0
    assert res["verdict"].startswith("CLEAN NULL")


@pytest.mark.slow
def test_mispriced_corner_lights_up_detection_legs():
    """A concentrated real mispricing (the HIGH alt line shaded) must move the DETECTION legs off
    their efficient-market floor: FDR survivors appear and the best high-line config has +ROI/+edge.
    (The full candidate can still be held by PBO tie-conservatism — that is BY DESIGN and is the
    separate `test_deflation_stays_conservative_on_a_tie` below.)"""
    df = _price(_synth_totals_frame(320, seed=3, shade=0.12))
    res = dg.evaluate_market(df, dg.ALT_TOTALS, sorted(df["bookmaker_key"].unique()))
    assert res["fdr"]["n_survive"] > 0                     # detection fired (vs 0 on efficient)
    high = [c for c in res["configs"] if c["line_bucket"] == "high" and c["n"] >= dg.MIN_GAMES]
    assert high, "expected selectable high-bucket configs"
    best = max(high, key=lambda c: c["roi"])
    assert best["roi"] > 0 and best["mean_edge"] > 0


@pytest.mark.slow
def test_deflation_stays_conservative_on_a_tie():
    """When EVERY config shares the same uniform edge (a saturated tie), PBO must NOT certify it —
    the high-PBO-over-a-tie discipline (§0.5). A uniform shade across all lines/books → no candidate
    even though ROIs are positive, because 'which tied config wins' is noise."""
    df = _price(_synth_totals_frame(300, seed=9, shade=0.10, shade_only_high=False))
    res = dg.evaluate_market(df, dg.ALT_TOTALS, sorted(df["bookmaker_key"].unique()))
    assert res["candidates"] == []                         # deflation refuses the saturated tie


@pytest.mark.slow
def test_placebo_negative_control_stays_clean_on_mispriced_data():
    """The E13.16 durable lesson: even where a REAL mispricing exists, breaking the model↔outcome
    link (pricing each game with ANOTHER game's μ) must NOT produce a candidate — else the gate
    manufactures edge. We shade the high line (a real edge for the true model) but roll the μ→game
    map so the model is now outcome-independent → the placebo grid must return a clean null."""
    df = _synth_totals_frame(320, seed=4, shade=0.12)
    games = df.drop_duplicates("game_pk").reset_index(drop=True)
    games["mu_home"] = np.roll(games["mu_home"].to_numpy(), len(games) // 2)   # placebo roll
    games["mu_away"] = np.roll(games["mu_away"].to_numpy(), len(games) // 2)
    df = df.drop(columns=["mu_home", "mu_away"]).merge(
        games[["game_pk", "mu_home", "mu_away"]], on="game_pk")
    res = dg.evaluate_market(_price(df), dg.ALT_TOTALS, sorted(df["bookmaker_key"].unique()))
    assert res["candidates"] == []


def test_absent_market_reports_explicit_not_silent_pass():
    res = dg.evaluate_market(pd.DataFrame(), dg.TEAM_TOTALS, [])
    assert res["present"] is False and res["candidates"] == []
    assert res["verdict"].startswith("ABSENT")


def test_config_grid_is_deterministic_and_covers_the_registered_space():
    grid = dg.make_config_grid(dg.ALT_TOTALS, ["bovada", "pinnacle"])
    # groups = {all,pinnacle,soft,majors} + the non-group book (bovada); pinnacle already a group
    groups = {c.book_group for c in grid}
    assert groups == {"all", "pinnacle", "soft", "majors", "bovada"}
    assert len(grid) == len(groups) * len(dg.LINE_BUCKETS) * len(dg.TAU_GRID)
    assert grid == dg.make_config_grid(dg.ALT_TOTALS, ["pinnacle", "bovada"])  # order-independent


@pytest.mark.parametrize("side,actual,line,price,expect_sign", [
    ("over", 12, 8.5, -110, 1),      # over wins → +profit
    ("over", 5, 8.5, -110, -1),      # over loses → −1
    ("under", 5, 8.5, -110, 1),      # under wins → +profit
])
def test_game_level_payoff_signs(side, actual, line, price, expect_sign):
    df = pd.DataFrame({"game_pk": [1], "season": [2024], "game_date": ["2024-06-01"],
                       "line": [line], "bet_side": [side], "bet_price": [price],
                       "actual_total": [actual], "edge": [0.06]})
    g = dg.game_level_returns(df)
    assert np.sign(g.loc[0, "p"]) == expect_sign
