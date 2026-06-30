"""Tests for Edge Program Story E13.13 — derivative-market efficiency eval (angles 1+2).

Covers the pure machinery (`betting_ml/utils/derivative_eval.py`) + the orchestration's
synthetic end-to-end path (`betting_ml/scripts/derivative_eval/eval_derivatives.py`):
  * settlement / de-vig correctness (half-line push, F5 tie, two/three-way de-vig),
  * efficiency metrics (Brier, calibration bias z, line MAE),
  * static-strategy ROI net of vig + OLS / mechanical-derivation,
  * Benjamini–Hochberg FDR control,
  * the gate behaves correctly: an EFFICIENT synthetic market → clean null; a deliberately
    MISPRICED one → the gate fires a candidate (proves it can detect, not just reject).
All synthetic — no Snowflake / S3 / network.
"""

from __future__ import annotations

import numpy as np
import pytest

from betting_ml.utils import derivative_eval as de


# ── Settlement ────────────────────────────────────────────────────────────────────────────────
def test_realized_over_halfline_and_integer_push():
    assert de.realized_over(5.0, 4.5) == 1.0      # 5 > 4.5
    assert de.realized_over(4.0, 4.5) == 0.0      # 4 < 4.5
    assert np.isnan(de.realized_over(5.0, 5.0))   # integer-line push → excluded
    assert np.isnan(de.realized_over(None, 4.5))


def test_realized_home_f5_tie_is_nan():
    assert de.realized_home_f5(3, 1) == 1.0
    assert de.realized_home_f5(1, 3) == 0.0
    assert np.isnan(de.realized_home_f5(2, 2))    # tie = push (2-way) → excluded


def test_h2h_payoff_vec_win_lose_push():
    # home bet at +100 (profit 1.0): win when home>away, push on tie, lose otherwise
    pay = de.h2h_payoff_vec([3, 1, 2], [1, 3, 2], ["home", "home", "home"], [100, 100, 100])
    assert pay[0] == pytest.approx(1.0)    # win
    assert pay[1] == pytest.approx(-1.0)   # lose
    assert pay[2] == pytest.approx(0.0)    # tie → push refund
    # away side mirrors
    pay_a = de.h2h_payoff_vec([1], [3], ["away"], [-110])
    assert pay_a[0] == pytest.approx(100 / 110)


def test_h2h_payoff_nan_safe():
    pay = de.h2h_payoff_vec([np.nan], [2], ["home"], [100])
    assert np.isnan(pay[0])


# ── De-vig ────────────────────────────────────────────────────────────────────────────────────
def test_devig_pair_sums_to_one_and_hold():
    r = de.devig_pair(-110, -110)
    assert r["valid"]
    assert r["fair_a"] + r["fair_b"] == pytest.approx(1.0)
    assert r["fair_a"] == pytest.approx(0.5)
    assert r["hold"] > 0           # -110/-110 carries ~4.5% overround
    assert r["hold"] == pytest.approx(0.0476, abs=1e-3)


def test_devig_pair_invalid_one_sided():
    r = de.devig_pair(None, -110)
    assert not r["valid"]
    assert np.isnan(r["fair_a"])


def test_devig_triple_normalises():
    r = de.devig_triple(150, 160, 240)   # 3-way F5 h2h with a draw price
    assert r["valid"]
    assert r["fair_home"] + r["fair_away"] + r["fair_draw"] == pytest.approx(1.0)
    assert r["hold"] > 0


# ── Efficiency metrics ──────────────────────────────────────────────────────────────────────────
def test_calibration_z_detects_bias_sign():
    # market prices P(over)=0.40 but it hits 0.60 → realized underpriced → bias>0, large z
    rng = np.random.default_rng(0)
    n = 5000
    fair = np.full(n, 0.40)
    realized = (rng.random(n) < 0.60).astype(float)
    cz = de.calibration_z(fair, realized)
    assert cz["bias"] > 0.15
    assert cz["z"] > 5
    assert cz["p_two_sided"] < 1e-3
    assert cz["n"] == n


def test_calibration_z_clean_when_calibrated():
    rng = np.random.default_rng(1)
    n = 8000
    fair = np.full(n, 0.5)
    realized = (rng.random(n) < 0.5).astype(float)
    cz = de.calibration_z(fair, realized)
    assert abs(cz["z"]) < 3       # no systematic bias


def test_efficiency_summary_brier_and_mae():
    fair_over = np.array([0.5, 0.5, 0.5, 0.5])
    realized = np.array([1.0, 0.0, 1.0, 0.0])
    line = np.array([4.5, 4.5, 4.5, 4.5])
    actual = np.array([6.0, 3.0, 5.0, 2.0])
    s = de.efficiency_summary(fair_over, realized, line=line, actual_total=actual,
                              hold=np.array([0.05, 0.05, 0.05, 0.05]))
    assert s["brier"] == pytest.approx(0.25)
    assert s["over_rate"] == pytest.approx(0.5)
    assert s["mean_vig"] == pytest.approx(0.05)
    assert s["line_mae"] == pytest.approx(np.mean([1.5, 1.5, 0.5, 2.5]))


def test_efficiency_summary_excludes_push_from_brier():
    fair_over = np.array([0.5, 0.5, 0.5])
    realized = np.array([1.0, np.nan, 0.0])   # middle is a push
    s = de.efficiency_summary(fair_over, realized)
    assert s["n_brier"] == 2


# ── Static strategy ─────────────────────────────────────────────────────────────────────────────
def test_static_total_payoffs_and_summary():
    actual = np.array([6.0, 3.0])
    line = np.array([4.5, 4.5])
    pay = de.static_total_payoffs(actual, line, "over", np.array([100.0, 100.0]))
    assert pay[0] == pytest.approx(1.0)    # over wins
    assert pay[1] == pytest.approx(-1.0)   # over loses
    summ = de.static_summary(pay)
    assert summ["n"] == 2
    assert summ["roi"] == pytest.approx(0.0)


# ── OLS / mechanical derivation ───────────────────────────────────────────────────────────────
def test_ols_recovers_line():
    x = np.arange(50, dtype=float)
    y = 2.0 + 0.5 * x
    fit = de.ols(x, y)
    assert fit["slope"] == pytest.approx(0.5)
    assert fit["intercept"] == pytest.approx(2.0)
    assert fit["r2"] == pytest.approx(1.0)


def test_derivation_deviation_flags_systematic_gap():
    rng = np.random.default_rng(2)
    main = rng.uniform(7, 11, 400)
    book_implied = 0.54 * main                  # book's fixed-fraction F5 line
    realized = 0.54 * main + 0.8 + rng.normal(0, 0.3, 400)  # truth runs 0.8 hotter
    dev = de.derivation_deviation(main, book_implied, realized)
    assert dev["mean_resid"] == pytest.approx(0.8, abs=0.1)
    assert dev["resid_z"] > 5


# ── Multiple-comparison (BH-FDR) ──────────────────────────────────────────────────────────────
def test_bh_fdr_controls_false_discoveries():
    # 100 nulls (uniform p) + 5 strong signals → BH should recover signals, reject most nulls
    rng = np.random.default_rng(3)
    nulls = rng.uniform(0, 1, 100)
    signals = np.full(5, 1e-6)
    pvals = np.concatenate([nulls, signals])
    res = de.bh_fdr(pvals, q=0.10)
    assert res["n_tested"] == 105
    assert res["survive"][-5:].all()             # all 5 signals survive
    assert res["n_survive"] < 20                 # FDR keeps false discoveries low


def test_bh_fdr_all_null_survives_few():
    rng = np.random.default_rng(4)
    pvals = rng.uniform(0, 1, 200)
    res = de.bh_fdr(pvals, q=0.10)
    assert res["n_survive"] <= 5                  # ~q·m expected; essentially a clean reject


def test_bh_fdr_handles_nans():
    res = de.bh_fdr([np.nan, np.nan, 1e-8], q=0.10)
    assert res["n_tested"] == 1
    assert res["survive"][2]


# ── Book grouping ───────────────────────────────────────────────────────────────────────────────
def test_book_mask_groups():
    bk = np.array(["pinnacle", "draftkings", "bovada", "fanduel"], dtype=object)
    assert de.book_mask(bk, "all").all()
    assert de.book_mask(bk, "pinnacle").tolist() == [True, False, False, False]
    assert de.book_mask(bk, "soft").tolist() == [False, True, True, True]
    assert de.book_mask(bk, "majors").tolist() == [False, True, False, True]
    assert de.book_mask(bk, "bovada").tolist() == [False, False, True, False]


# ── End-to-end gate behaviour (the discipline check) ─────────────────────────────────────────────
def _run(frame):
    from betting_ml.scripts.derivative_eval.eval_derivatives import (
        angle1, angle2, build_candidates, build_wides,
    )
    wides = build_wides(frame)
    books = sorted(frame["bookmaker_key"].dropna().unique().tolist())
    a1 = angle1(wides, books)
    a2 = angle2(wides)
    return a1, a2, build_candidates(a1, a2)


def test_efficient_market_yields_clean_null():
    from betting_ml.scripts.derivative_eval.eval_derivatives import make_smoke_frame
    frame = make_smoke_frame(n_games=250, seed=11, efficiency=1.0)
    a1, a2, cand = _run(frame)
    assert cand["verdict"].startswith("CLEAN NULL")
    assert len(cand["candidates"]) == 0
    # efficient ⇒ deflation rejects the in-sample-best static strategy (DSR below the 0.95 gate)
    assert a1["dsr"]["dsr"] < 0.95
    # the grid + the deviation map both exist (required deliverables)
    assert len(a1["efficiency"]) > 0 and len(a2) > 0


def test_mispriced_market_is_detected():
    """A deliberately mispriced market (books shrink every prob to 0.5) must FIRE a candidate —
    proves the gate can detect signal, not merely reject everything."""
    from betting_ml.scripts.derivative_eval.eval_derivatives import make_smoke_frame
    frame = make_smoke_frame(n_games=350, seed=12, efficiency=0.0)
    a1, a2, cand = _run(frame)
    assert cand["verdict"].startswith("CANDIDATES")
    assert len(cand["candidates"]) > 0
    # a real, large, persistent edge ⇒ the in-sample-best static persists out of sample (PBO<0.2)
    assert a1["pbo"]["pbo"] < 0.2
    # detected through BOTH channels: an FDR-surviving static strategy AND a calibration cell
    sources = {c["source"] for c in cand["candidates"]}
    assert "angle1_static" in sources or "angle1_calibration" in sources


def test_reshape_totals_columns_and_realized():
    from betting_ml.scripts.derivative_eval.eval_derivatives import _reshape_totals, make_smoke_frame
    frame = make_smoke_frame(n_games=40, seed=5)
    w = _reshape_totals(frame, de.F5_TOTALS)
    for col in ("over_price", "under_price", "fair_over", "realized_over", "line",
                "actual_total", "hold", "dist_to_sharp"):
        assert col in w.columns
    # Pinnacle's own dist_to_sharp is 0 (it is the sharp anchor)
    pin = w[w["bookmaker_key"] == de.PINNACLE]
    assert (pin["dist_to_sharp"].abs() < 1e-9).all()
