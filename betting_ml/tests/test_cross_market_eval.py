"""Tests for Edge Program Story E13.14 — cross-market constellation coherence.

Covers the pure machinery (`betting_ml/utils/cross_market_eval.py`) + the orchestration's synthetic
end-to-end path (`betting_ml/scripts/cross_market_eval/eval_cross_market.py`):
  * the Bayesian credence + the normal CDF,
  * the Poisson-mean inversion (the prop → implied-runs basis),
  * the leave-one-season-out AFFINE calibration (recovers a known scale, in-fold),
  * the game-level collapse (correlated book-quotes → one return per game — the E13.13 honest bar),
  * the coherence info-gain diagnostic,
  * the gate behaves correctly end-to-end: a COHERENT constellation → clean null; an injected
    inconsistency → a candidate fires; and — non-negotiable — the F5↔main NEGATIVE CONTROL stays
    "consistent" in BOTH regimes (a control candidate would mean the harness is broken).
All synthetic — no Snowflake / S3 / network.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from betting_ml.utils import cross_market_eval as cm


# ── Credence / normal CDF ───────────────────────────────────────────────────────────────────────
def test_normal_cdf_known_points():
    assert cm.normal_cdf(0.0) == pytest.approx(0.5)
    assert cm.normal_cdf(1.0) == pytest.approx(0.8413, abs=1e-3)
    assert cm.normal_cdf(-1.0) == pytest.approx(0.1587, abs=1e-3)


def test_credence_monotone_and_bounds():
    # larger deviation / smaller sd ⇒ higher credence; range [0.5, 1]
    c = cm.credence([0.0, 0.5, 2.0], [1.0, 1.0, 1.0])
    assert c[0] == pytest.approx(0.5)
    assert 0.5 < c[1] < c[2] <= 1.0
    # sd == 0 → degenerate point posterior
    cz = cm.credence([0.0, 0.3], [0.0, 0.0])
    assert cz[0] == pytest.approx(0.5)
    assert cz[1] == pytest.approx(1.0)
    assert np.isnan(cm.credence([np.nan], [1.0])[0])


def test_forced_side_from_deviation_sign():
    s = cm.forced_side([0.4, -0.2, 0.0])
    assert s.tolist() == ["over", "under", "under"]   # 0 → under (deviation not > 0)


# ── Poisson-mean inversion (prop → implied runs) ─────────────────────────────────────────────────
def test_poisson_mean_from_p_over_half_line_closed_form():
    # P(score ≥ 1) = 1 − e^{−λ}; at p=0.5 → λ = ln 2
    assert cm.poisson_mean_from_p_over(0.5, 0.5) == pytest.approx(math.log(2.0), abs=1e-6)
    # round-trip a known mean through the SF and back
    lam = 0.9
    p = cm.poisson_sf(0.5, lam)            # P(X > 0.5) = P(X ≥ 1)
    assert cm.poisson_mean_from_p_over(p, 0.5) == pytest.approx(lam, abs=1e-6)


def test_poisson_mean_general_line_bisection_roundtrip():
    lam = 2.3
    for line in (1.5, 2.5):
        p = cm.poisson_sf(line, lam)
        assert cm.poisson_mean_from_p_over(p, line) == pytest.approx(lam, abs=1e-2)


def test_poisson_mean_out_of_range_is_nan():
    assert np.isnan(cm.poisson_mean_from_p_over(0.0, 0.5))
    assert np.isnan(cm.poisson_mean_from_p_over(1.0, 0.5))


# ── LOSO affine calibration ──────────────────────────────────────────────────────────────────────
def test_loso_affine_recovers_scale_in_fold():
    # posted_B ≈ 1.85 · implied_raw + 0.1 (an F5-fraction-like map); fit must recover it OOF
    rng = np.random.default_rng(0)
    n = 800
    season = rng.choice([2023, 2024, 2025], n).astype(object)
    implied_raw = rng.uniform(2.0, 3.5, n)            # F5-ish line
    posted = 0.1 + 1.85 * implied_raw + rng.normal(0, 0.05, n)
    fitted, beta = cm.loso_affine(implied_raw, posted, season)
    # the fitted posted-equivalent matches the true posted (the deviation is just noise)
    assert np.nanmean(np.abs(fitted - posted)) < 0.1
    assert np.nanmedian(beta) == pytest.approx(1.85, abs=0.05)


def test_loso_affine_single_season_falls_back_global():
    x = np.arange(20, dtype=float)
    y = 2.0 + 0.5 * x
    fitted, beta = cm.loso_affine(x, y, np.array(["2024"] * 20, object))
    assert np.allclose(fitted, y, atol=1e-6)
    assert beta[0] == pytest.approx(0.5)


# ── Game-level collapse (the E13.13 honest bar) ──────────────────────────────────────────────────
def test_score_game_level_collapses_correlated_quotes():
    # one game, 5 book-quotes all winning +0.9 → ONE game return, n == 1 (not 5)
    pay = np.array([0.9, 0.9, 0.9, 0.9, 0.9])
    gp = np.array([100, 100, 100, 100, 100])
    season = np.array(["2024"] * 5, object)
    ym = np.array(["2024-05"] * 5, object)
    s = cm.score_game_level(pay, gp, season, ym)
    assert s["n"] == 1                 # unique GAMES, not quotes
    assert s["n_quotes"] == 5
    assert s["roi"] == pytest.approx(0.9)


def test_score_game_level_season_sign_consistency():
    # +0.2 in 2023 and +0.1 in 2024 → sign-consistent; flip one and it is not
    pay = np.array([0.2, 0.2, 0.1, 0.1])
    gp = np.array([1, 2, 3, 4])
    season = np.array(["2023", "2023", "2024", "2024"], object)
    ym = np.array(["2023-05", "2023-06", "2024-05", "2024-06"], object)
    assert cm.score_game_level(pay, gp, season, ym)["season_sign_consistent"]
    pay2 = np.array([0.2, 0.2, -0.1, -0.1])
    assert not cm.score_game_level(pay2, gp, season, ym)["season_sign_consistent"]


# ── Coherence diagnostic ─────────────────────────────────────────────────────────────────────────
def test_coherence_info_gain_positive_when_implied_more_informative():
    rng = np.random.default_rng(1)
    n = 1500
    truth = rng.normal(4.5, 1.0, n)
    implied = truth + rng.normal(0, 0.2, n)        # implied_A ≈ truth (informative)
    posted = truth + rng.normal(0, 0.9, n)         # posted line is noisier
    realized = truth + rng.normal(0, 1.0, n)
    c = cm.coherence_summary(implied, posted, realized)
    assert c["info_gain"] > 0                       # implied tracks the outcome better than the line
    assert c["corr_markets"] > 0


# ── End-to-end gate behaviour (the discipline check) ─────────────────────────────────────────────
# Use the SAME params as the committed `--smoke` run (n_games=600, seed=7) so the deflation (CSCV/DSR
# is deterministic and the assertions match the shipped smoke dossier exactly.
def _run(efficiency, *, seed=7, n_games=600):
    from betting_ml.scripts.cross_market_eval.eval_cross_market import evaluate, make_smoke_frame
    frame = make_smoke_frame(n_games=n_games, seed=seed, efficiency=efficiency)
    return evaluate(frame)


def _surviving_configs(res, relation):
    cfgs = res["relations"][relation]["configs"]
    return [c for c in cfgs if c["n"] >= 50 and c["roi"] > 0
            and c["season_sign_consistent"] and c.get("roi_fdr_survive")]


def test_coherent_constellation_yields_clean_null():
    res = _run(efficiency=1.0)
    assert res["candidates"]["verdict"].startswith("CLEAN NULL")
    assert len(res["candidates"]["candidates"]) == 0
    # the F5 control is reported consistent (the method is not manufacturing inconsistencies)
    assert res["candidates"]["control_consistent"]
    assert len(res["candidates"]["control_breaks"]) == 0
    # a coherent constellation leaves NO surviving +ROI config anywhere (incl. the laziest pair)
    assert _surviving_configs(res, "props_to_team_total") == []


def test_injected_inconsistency_is_detected_and_control_holds():
    """A deliberately shaded team-total line vs informative props (efficiency=0) MUST be detected on
    the props↔team-total relation — AND the F5↔main control MUST still come back consistent (proves
    the gate detects signal without breaking the control)."""
    res = _run(efficiency=0.0)
    cand = res["candidates"]
    # the edge is DETECTED through the robust channel: an FDR-surviving, season-consistent, +ROI
    # props↔team-total config exists; the control produces NONE (it stays consistent)
    assert _surviving_configs(res, "props_to_team_total"), "the injected inconsistency was not detected"
    assert _surviving_configs(res, "f5_to_full_control") == [], "the NEGATIVE CONTROL fired — method broken"
    assert res["relations"]["props_to_team_total"]["coherence"]["info_gain"] > 0
    # the full deflated gate also clears at the canonical smoke params (deterministic PBO)
    assert "CANDIDATE" in cand["verdict"] or "FRAGILE" in cand["verdict"]
    assert len(cand["candidates"]) > 0
    assert all(c["relation"] == "props_to_team_total" for c in cand["candidates"])
    assert all(not c["is_control"] for c in cand["candidates"])
    assert cand["control_consistent"]
    assert len(cand["control_breaks"]) == 0
    # a real, large, persistent edge ⇒ the in-sample-best persists OOS (PBO < 0.2)
    assert res["deflation"]["pbo"]["pbo"] < 0.2


def test_control_relation_is_flagged_as_control():
    from betting_ml.scripts.cross_market_eval.eval_cross_market import RELATIONS, R3
    assert RELATIONS[R3]["is_control"] is True


def test_assemble_team_to_game_handles_single_book_games():
    """A (game, side) quoted by only ONE book has an undefined cross-book std → pivot_table drops it
    from the std frame, so its index becomes a subset of the median frame. The assembler must reindex
    (not .loc) so it can't KeyError, and a single-book game's sd_a must be 0 (no dispersion)."""
    import pandas as pd
    from betting_ml.scripts.cross_market_eval.eval_cross_market import (
        CACHE_COLS, _assemble_team_to_game)
    gp = np.arange(20)
    gd = pd.to_datetime(["2024-05-10"] * 10 + ["2025-06-11"] * 10)
    settled = pd.DataFrame({"game_pk": gp, "game_date": gd,
                            "final_home": np.full(20, 4), "final_away": np.full(20, 3),
                            "f5_home": 0, "f5_away": 0})
    gt = pd.concat([pd.DataFrame({"game_pk": gp, "bookmaker_key": bk, "over_price": -110,
                                  "under_price": -110, "line_B": 7.5, "game_date": gd,
                                  "season": gd.year}) for bk in ("pinnacle", "draftkings")],
                   ignore_index=True)
    rows = []
    for i in gp:
        books = ["pinnacle"] if i < 5 else ["pinnacle", "draftkings"]   # games 0-4 single-book
        for bk in books:
            for side, base in (("home", 4.5), ("away", 3.5)):
                rows.append({"game_pk": i, "side_label": side, "bookmaker_key": bk,
                             "over_price": -110, "under_price": -110, "line_B": base})
    out = _assemble_team_to_game(pd.DataFrame(rows), gt, settled)
    assert list(out.columns) == CACHE_COLS
    assert out["game_pk"].nunique() == 20                       # no game dropped, no KeyError
    one_book = out[out["game_pk"] == 2]
    assert float(one_book["sd_a"].iloc[0]) == 0.0               # single-book → zero dispersion
