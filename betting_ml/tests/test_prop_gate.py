"""test_prop_gate.py — Edge Program E5.4 pure gate machinery.

Covers the AC-critical pieces: settlement net of vig (half-line vs integer-line PUSH, win/lose
payoff at the real offered price), the PRE-REGISTERED config grid (deterministic, every book
counted, no degenerate Pinnacle-vs-Pinnacle duplicate), config bet selection (book/line/tau
masks, the two anchor policies, de-vig filter — selection NEVER touches the outcome), and the
at-the-line reliability / ECE.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from betting_ml.utils.prop_edge import american_to_profit
from betting_ml.utils.prop_gate import (
    ANCHOR_POLICIES,
    LINE_BUCKETS,
    MAJOR_BOOKS,
    PINNACLE,
    TAU_GRID,
    PropConfig,
    bet_payoff,
    central_interval_coverage,
    make_config_grid,
    payoff_vec,
    reliability_table,
    select_config_bets,
    settle_side,
)


# ── settlement ──────────────────────────────────────────────────────────────

def test_settle_halfline_over_under():
    assert settle_side(7, 5.5, "over") == "win"
    assert settle_side(4, 5.5, "over") == "lose"
    assert settle_side(4, 5.5, "under") == "win"
    assert settle_side(7, 5.5, "under") == "lose"


def test_settle_integer_line_push():
    # integer line, K exactly on the line → push for BOTH sides
    assert settle_side(5, 5.0, "over") == "push"
    assert settle_side(5, 5.0, "under") == "push"
    assert settle_side(6, 5.0, "over") == "win"
    assert settle_side(4, 5.0, "under") == "win"


def test_settle_nan_is_void():
    assert settle_side(float("nan"), 5.5, "over") == "void"


def test_settle_bad_side_raises():
    with pytest.raises(ValueError):
        settle_side(5, 5.5, "sideways")


def test_payoff_win_lose_push():
    # win at +120 → profit 1.2; lose → −1; push → 0
    assert bet_payoff(7, 5.5, "over", 120) == pytest.approx(1.2)
    assert bet_payoff(3, 5.5, "over", 120) == pytest.approx(-1.0)
    assert bet_payoff(5, 5.0, "over", 120) == pytest.approx(0.0)
    # win at −150 → profit 100/150
    assert bet_payoff(7, 5.5, "over", -150) == pytest.approx(100.0 / 150.0)


def test_payoff_nan_price_is_nan():
    assert np.isnan(bet_payoff(7, 5.5, "over", float("nan")))


def test_payoff_vec_matches_scalar():
    rng = np.random.default_rng(0)
    k = rng.integers(0, 12, 200).astype(float)
    line = rng.choice([3.5, 4.5, 5.0, 5.5, 6.5], 200).astype(float)
    side = rng.choice(["over", "under"], 200).astype(object)
    price = rng.choice([-150, -120, 100, 120, 145], 200).astype(float)
    vec = payoff_vec(k, line, side, price)
    scal = np.array([bet_payoff(k[i], line[i], side[i], price[i]) for i in range(len(k))])
    np.testing.assert_allclose(vec, scal, equal_nan=True)


def test_payoff_is_roi_net_of_vig():
    """A −110/−110 two-way book at a half-line: blindly betting over at a coin-flip outcome
    returns the negative-of-hold ROI (you pay the vig). This is why mean(payoff) IS ROI net of
    the vig the offered price embeds."""
    profit = american_to_profit(-110)            # ≈ 0.909
    # 50% win 0.909, 50% lose 1 → mean ≈ −0.045 (the per-side hold)
    payoffs = [bet_payoff(7, 5.5, "over", -110), bet_payoff(3, 5.5, "over", -110)]
    assert np.mean(payoffs) == pytest.approx((profit - 1.0) / 2.0)


# ── pre-registered grid ───────────────────────────────────────────────────────

def test_grid_is_deterministic_and_sized():
    books = ["draftkings", "fanduel", "bovada"]                    # no pinnacle → no de-dup here
    g1 = make_config_grid(books)
    g2 = make_config_grid(books)
    assert [c.name for c in g1] == [c.name for c in g2]            # deterministic
    groups = 4 + len(books)                                         # {all,pinnacle,soft,majors}+books
    # every (group × bucket × tau × anchor) MINUS the pinnacle/pinnacle degenerate (one per bucket×tau)
    expected = groups * len(LINE_BUCKETS) * len(TAU_GRID) * len(ANCHOR_POLICIES) \
        - len(LINE_BUCKETS) * len(TAU_GRID)
    assert len(g1) == expected


def test_grid_dedupes_pinnacle_book():
    # pinnacle is both a named group AND a real book — must not be counted twice
    with_pin = make_config_grid(["pinnacle", "draftkings"])
    without = make_config_grid(["draftkings"])
    assert len(with_pin) == len(without)
    assert sum(c.book_group == PINNACLE for c in with_pin) == \
        sum(c.book_group == PINNACLE for c in without)


def test_grid_skips_pinnacle_vs_pinnacle():
    g = make_config_grid(["pinnacle", "draftkings"])
    assert not any(c.book_group == PINNACLE and c.anchor == "pinnacle" for c in g)
    # but pinnacle-vs-book IS present
    assert any(c.book_group == PINNACLE and c.anchor == "book" for c in g)


# ── config bet selection (pure; never sees the outcome) ────────────────────────

def _edge_frame() -> pd.DataFrame:
    """A tiny hand-built edge table covering both anchors / books / lines."""
    return pd.DataFrame([
        # book, line, best_side, best_edge, over_price, under_price, model_p_over_cond, edge_vs_pinnacle, devig_valid
        dict(bookmaker_key="draftkings", line=5.5, best_side="under", best_edge=0.08,
             over_price=120, under_price=-150, model_p_over_cond=0.40, edge_vs_pinnacle=-0.07, devig_valid=True),
        dict(bookmaker_key="fanduel", line=4.5, best_side="over", best_edge=0.03,
             over_price=-110, under_price=-110, model_p_over_cond=0.55, edge_vs_pinnacle=0.05, devig_valid=True),
        dict(bookmaker_key="pinnacle", line=6.5, best_side="over", best_edge=0.10,
             over_price=-105, under_price=-115, model_p_over_cond=0.60, edge_vs_pinnacle=float("nan"), devig_valid=True),
        dict(bookmaker_key="bovada", line=3.5, best_side="over", best_edge=0.09,
             over_price=130, under_price=-160, model_p_over_cond=0.58, edge_vs_pinnacle=0.01, devig_valid=False),  # one-sided → excluded
    ])


def test_select_book_anchor_applies_tau_and_devig():
    df = _edge_frame()
    cfg = PropConfig(book_group="all", line_bucket="all", tau=0.05, anchor="book")
    bets = select_config_bets(df, cfg)
    # DK (edge 0.08) + Pinnacle (0.10) clear tau 0.05; FD (0.03) doesn't; Bovada is devig-invalid
    assert set(bets["bookmaker_key"]) == {"draftkings", "pinnacle"}
    # bet_side follows best_side; price is the chosen side's offered price
    dk = bets[bets["bookmaker_key"] == "draftkings"].iloc[0]
    assert dk["bet_side"] == "under" and dk["bet_price"] == -150


def test_select_book_group_majors_and_soft():
    df = _edge_frame()
    maj = select_config_bets(df, PropConfig("majors", "all", 0.02, "book"))
    assert set(maj["bookmaker_key"]) <= set(MAJOR_BOOKS)
    soft = select_config_bets(df, PropConfig("soft", "all", 0.02, "book"))
    assert PINNACLE not in set(soft["bookmaker_key"])


def test_select_line_bucket():
    df = _edge_frame()
    hi = select_config_bets(df, PropConfig("all", "high_ge6p5", 0.02, "book"))
    assert (hi["line"] >= 6.5).all() and len(hi) == 1  # only the pinnacle 6.5 row


def test_select_pinnacle_anchor_uses_sign_of_edge_vs_pinnacle():
    df = _edge_frame()
    cfg = PropConfig("soft", "all", 0.04, "pinnacle")
    bets = select_config_bets(df, cfg)
    # DK edge_vs_pinnacle −0.07 → bet UNDER; FD +0.05 → bet OVER. Pinnacle row has NaN evp → excluded.
    dk = bets[bets["bookmaker_key"] == "draftkings"].iloc[0]
    fd = bets[bets["bookmaker_key"] == "fanduel"].iloc[0]
    assert dk["bet_side"] == "under"
    assert fd["bet_side"] == "over"
    assert PINNACLE not in set(bets["bookmaker_key"])


def test_select_empty_returns_typed_columns():
    df = _edge_frame()
    bets = select_config_bets(df, PropConfig("all", "all", 0.99, "book"))  # impossible tau
    assert bets.empty and "bet_side" in bets.columns and "bet_price" in bets.columns


# ── reliability / ECE ───────────────────────────────────────────────────────

def test_reliability_perfect_is_low_ece():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 20000)
    y = (rng.uniform(0, 1, 20000) < p).astype(float)   # perfectly calibrated by construction
    rel = reliability_table(p, y, n_bins=10)
    assert rel["n"] == 20000
    assert rel["ece"] < 0.02


def test_reliability_miscalibrated_has_gap():
    p = np.full(1000, 0.9)
    y = np.zeros(1000)                                  # always says 0.9, never happens
    rel = reliability_table(p, y, n_bins=5)
    assert rel["ece"] > 0.8


def test_reliability_empty():
    rel = reliability_table(np.array([]), np.array([]))
    assert rel["n"] == 0 and np.isnan(rel["ece"])


def test_central_interval_coverage():
    p = np.array([0.7, 0.2, 0.6, 0.4])
    over = np.array([1, 0, 0, 0])     # bets 1,2,4 land on the model's side; 3 wrong → 3/4
    assert central_interval_coverage(p, over) == pytest.approx(0.75)
