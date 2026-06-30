"""derivative_eval.py — Edge Program Story E13.13: derivative-market efficiency (pure math).

E13.13 evaluates whether MLB DERIVATIVE markets (first-5-inning totals/h2h, NRFI, team/alt
totals) are mispriced relative to the realized outcome we settle from our own pitch data.
The Miller-Davidow + E13.8 thesis: books price the FEATURED markets tight (main H2H dead ×5,
main total a coin-flip) but DERIVATIVES looser (lower limits / less line-setting effort) → the
lazier inning/team/alt markets are the one place a real edge might still live.

SCOPE = angles 1+2 (pure cached-data analysis, NO model). Angle 3 (model-vs-market gate) is
E2.6. This module is the PURE machinery; the orchestration
(`betting_ml/scripts/derivative_eval/eval_derivatives.py`) reads the cached S3 data, settles
outcomes, runs the angles, and writes the dossier.

HONEST BAR (baked into every output): a derivative being less efficient is the THESIS, not a
free lunch — derivatives carry higher vig + lower limits. Nothing here is an "edge"; outputs are
an efficiency ranking, a mechanical-derivation deviation map, and a CANDIDATE shortlist for E2.6.
The cashability verdict is forward CLV net of the derivative's own vig at PBO<0.2/DSR>0 (E2.6).

Reuses the program's odds primitives so the de-vig matches everywhere:
  - `american_to_implied` / `implied_no_vig_pair` (the A0.4.32 additive method),
  - `american_to_profit` (per-$1 win profit),
  - `settle_side` / `payoff_vec` (totals over/under settlement net of the offered vig).
"""

from __future__ import annotations

import numpy as np

from betting_ml.utils.market_features import implied_no_vig_pair
from betting_ml.utils.prop_edge import american_to_profit
from betting_ml.utils.prop_gate import payoff_vec, settle_side  # totals settlement (reused)
from betting_ml.utils.totals_probability import american_to_implied

# ── Book groups (mirror prop_gate.MAJOR_BOOKS / A0.4.32) ────────────────────────────────────
MAJOR_BOOKS = ("draftkings", "fanduel", "betmgm", "williamhill_us")
PINNACLE = "pinnacle"

# The derivative markets E13.13 settles — the corrected `*_1st_N_innings` Odds-API keys present in
# the E5.1 `mlb/props/` backfill (NOT the stale `totals_h1`/`h2h_h1` of the older derivative_odds
# pipeline). team/alt are included iff present (their backfill stalls 2025-08-11 — partial).
F5_TOTALS = "totals_1st_5_innings"
F5_H2H = "h2h_1st_5_innings"
NRFI = "totals_1st_1_innings"      # Over/Under 0.5 first-inning runs (under = NRFI)
TEAM_TOTALS = "team_totals"
ALT_TOTALS = "alternate_totals"

TOTALS_MARKETS = (F5_TOTALS, NRFI, TEAM_TOTALS, ALT_TOTALS)

_EPS = 1e-9
_CLAMP = 1e-6   # log-loss / logit probability clamp


# ── Settlement (realized outcome from pitch-settled runs) ────────────────────────────────────

def realized_over(actual_total: float, line: float) -> float:
    """Binary realized OVER for a totals line. 1 if total > line, 0 if total < line.

    NaN at an integer-line PUSH (total == line) — excluded from Brier/calibration, counted as a
    push elsewhere (E13.8 convention). NaN if either input is missing."""
    if actual_total is None or line is None:
        return float("nan")
    a, ln = float(actual_total), float(line)
    if not (np.isfinite(a) and np.isfinite(ln)):
        return float("nan")
    if a == ln:
        return float("nan")     # integer-line push → excluded from the binary
    return 1.0 if a > ln else 0.0


def realized_home_f5(home_runs: float, away_runs: float) -> float:
    """Binary realized HOME-wins-F5. 1 if home > away after 5, 0 if away > home.

    NaN on a tie (F5 h2h tie = push for a 2-way market / the `draw` outcome for a 3-way one);
    ties are excluded from the 2-way Brier and reported separately as the tie-rate."""
    if home_runs is None or away_runs is None:
        return float("nan")
    h, a = float(home_runs), float(away_runs)
    if not (np.isfinite(h) and np.isfinite(a)):
        return float("nan")
    if h == a:
        return float("nan")
    return 1.0 if h > a else 0.0


def h2h_payoff_vec(home_runs, away_runs, side, american) -> np.ndarray:
    """Per-$1 realized PnL of a 2-way F5 h2h bet at the offered American price.

    side ∈ {'home','away'} (per row). win → +american_to_profit; lose → −1; TIE → 0 (push /
    stake refund, the standard 2-way F5 rule). NaN-safe. Mirrors prop_gate.payoff_vec for totals.
    """
    h = np.asarray(home_runs, float)
    a = np.asarray(away_runs, float)
    am = np.asarray(american, float)
    sd = np.asarray(side, dtype=object)
    home_wins = h > a
    tie = h == a
    side_is_home = sd == "home"
    won = np.where(side_is_home, home_wins, ~home_wins) & ~tie
    profit = np.where(am > 0, am / 100.0, 100.0 / np.abs(np.where(am == 0, np.nan, am)))
    out = np.where(won, profit, -1.0)
    out = np.where(tie, 0.0, out)
    out = np.where(np.isnan(h) | np.isnan(a) | np.isnan(am), np.nan, out)
    return out.astype(float)


# ── De-vig (two-way + three-way additive normalisation) ──────────────────────────────────────

def devig_pair(price_a: float | None, price_b: float | None) -> dict:
    """De-vig a two-way American pair (over/under or home/away) → fair probs + hold.

    Returns {fair_a, fair_b, implied_a, implied_b, hold, valid}. `hold` = implied_a+implied_b−1
    (the book's overround). One-sided / bad input → valid=False with NaN fairs (never silently
    50/50). Thin wrapper over `implied_no_vig_pair` (the canonical additive method)."""
    if price_a is None or price_b is None:
        return {"fair_a": float("nan"), "fair_b": float("nan"),
                "implied_a": float("nan"), "implied_b": float("nan"),
                "hold": float("nan"), "valid": False}
    try:
        ia = american_to_implied(price_a)
        ib = american_to_implied(price_b)
    except (TypeError, ValueError):
        return {"fair_a": float("nan"), "fair_b": float("nan"),
                "implied_a": float("nan"), "implied_b": float("nan"),
                "hold": float("nan"), "valid": False}
    fa, fb = implied_no_vig_pair(price_a, price_b)
    return {"fair_a": float(fa), "fair_b": float(fb),
            "implied_a": float(ia), "implied_b": float(ib),
            "hold": float(ia + ib - 1.0), "valid": bool(np.isfinite(fa))}


def devig_triple(price_home, price_away, price_draw) -> dict:
    """De-vig a THREE-way F5 h2h (home/away/draw) → fair probs + hold, additive normalisation.

    Returns {fair_home, fair_away, fair_draw, hold, valid}. Used when a book offers an explicit
    F5 draw price (3-way market); for the 2-way Brier the caller renormalises home/away."""
    try:
        ih = american_to_implied(price_home)
        ia = american_to_implied(price_away)
        idr = american_to_implied(price_draw)
    except (TypeError, ValueError):
        return {"fair_home": float("nan"), "fair_away": float("nan"),
                "fair_draw": float("nan"), "hold": float("nan"), "valid": False}
    tot = ih + ia + idr
    if not np.isfinite(tot) or tot <= 0:
        return {"fair_home": float("nan"), "fair_away": float("nan"),
                "fair_draw": float("nan"), "hold": float("nan"), "valid": False}
    return {"fair_home": float(ih / tot), "fair_away": float(ia / tot),
            "fair_draw": float(idr / tot), "hold": float(tot - 1.0), "valid": True}


# ── Efficiency metrics (extend the E13.8 benchmark to derivatives) ────────────────────────────

def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _CLAMP, 1 - _CLAMP)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def calibration_z(fair_p: np.ndarray, realized: np.ndarray) -> dict:
    """Two-sided z-test that the de-vigged market probability is mis-calibrated.

    bias = mean(realized) − mean(fair_p): >0 ⇒ the event happens MORE than the book prices it
    (the priced side is over-priced → fade toward the event). Standard error from the realized
    Bernoulli variance over n games. Returns {bias, implied_rate, realized_rate, se, z,
    p_two_sided, n}. n excludes pushes/ties (NaN realized)."""
    p = np.asarray(fair_p, float)
    y = np.asarray(realized, float)
    ok = np.isfinite(p) & np.isfinite(y)
    p, y = p[ok], y[ok]
    n = len(y)
    if n == 0:
        return {"bias": float("nan"), "implied_rate": float("nan"),
                "realized_rate": float("nan"), "se": float("nan"),
                "z": float("nan"), "p_two_sided": float("nan"), "n": 0}
    implied_rate = float(p.mean())
    realized_rate = float(y.mean())
    bias = realized_rate - implied_rate
    var = realized_rate * (1 - realized_rate)
    se = float(np.sqrt(var / n)) if var > 0 else float("nan")
    z = float(bias / se) if (se and np.isfinite(se) and se > 0) else float("nan")
    # two-sided normal p-value via erfc (no scipy dependency)
    from math import erfc, sqrt
    p_two = float(erfc(abs(z) / sqrt(2.0))) if np.isfinite(z) else float("nan")
    return {"bias": bias, "implied_rate": implied_rate, "realized_rate": realized_rate,
            "se": se, "z": z, "p_two_sided": p_two, "n": n}


def efficiency_summary(fair_over: np.ndarray, realized_bin: np.ndarray, *,
                       hold: np.ndarray | None = None,
                       line: np.ndarray | None = None,
                       actual_total: np.ndarray | None = None,
                       dist_to_sharp: np.ndarray | None = None) -> dict:
    """One efficiency row for a (market × book × season) cell — the E13.8 derivative analogue.

    fair_over     : de-vigged closing P(over) [totals] or P(home|not-tie) [h2h], per game.
    realized_bin  : realized 1/0 (NaN at push/tie → excluded from Brier/log-loss/calibration).
    hold          : per-game book overround (optional) → mean vig.
    line/actual_total : totals only → line MAE/RMSE + push-rate vs realized total.
    dist_to_sharp : |book fair − Pinnacle fair| per game (optional) → soft-vs-sharp spread.

    Returns brier, log_loss, n_brier, mean_vig, over_rate (realized), implied_over_rate,
    calib_bias (+ z/p), line_mae/rmse/push_rate, mean_dist_to_sharp. Brier floor for a centred
    coin-flip market = 0.25 (E13.8): brier ≈ 0.25 + over_rate≈implied_rate ⇒ efficient."""
    fp = np.asarray(fair_over, float)
    y = np.asarray(realized_bin, float)
    ok = np.isfinite(fp) & np.isfinite(y)
    fpb, yb = fp[ok], y[ok]
    n = len(yb)
    out: dict = {"n_brier": n}
    out["brier"] = float(np.mean((fpb - yb) ** 2)) if n else float("nan")
    out["log_loss"] = _logloss(fpb, yb) if n else float("nan")
    out["over_rate"] = float(yb.mean()) if n else float("nan")
    out["implied_over_rate"] = float(fpb.mean()) if n else float("nan")
    cz = calibration_z(fpb, yb)
    out["calib_bias"] = cz["bias"]
    out["calib_z"] = cz["z"]
    out["calib_p"] = cz["p_two_sided"]

    if hold is not None:
        h = np.asarray(hold, float)
        h = h[np.isfinite(h)]
        out["mean_vig"] = float(h.mean()) if len(h) else float("nan")
    if dist_to_sharp is not None:
        d = np.asarray(dist_to_sharp, float)
        d = d[np.isfinite(d)]
        out["mean_dist_to_sharp"] = float(d.mean()) if len(d) else float("nan")
    if line is not None and actual_total is not None:
        ln = np.asarray(line, float)
        at = np.asarray(actual_total, float)
        m = np.isfinite(ln) & np.isfinite(at)
        if m.any():
            err = at[m] - ln[m]
            out["line_mae"] = float(np.mean(np.abs(err)))
            out["line_rmse"] = float(np.sqrt(np.mean(err ** 2)))
            out["push_rate"] = float(np.mean(at[m] == ln[m]))
            out["n_line"] = int(m.sum())
        else:
            out["line_mae"] = out["line_rmse"] = out["push_rate"] = float("nan")
            out["n_line"] = 0
    return out


# ── Static directional strategies (the retail-bias probe — net of the offered vig) ────────────

def static_total_payoffs(actual_total, line, side: str, american) -> np.ndarray:
    """Per-$1 PnL of betting the SAME totals `side` ('over'|'under') every game at the offered
    price. Pure delegation to prop_gate.payoff_vec (handles the integer-line push)."""
    n = len(np.asarray(actual_total, float))
    return payoff_vec(actual_total, line, np.full(n, side, dtype=object), american)


def static_summary(payoffs: np.ndarray) -> dict:
    """ROI (mean per-$1 PnL net of vig) + Sharpe + n for a static strategy's bet series."""
    p = np.asarray(payoffs, float)
    p = p[np.isfinite(p)]
    n = len(p)
    if n == 0:
        return {"n": 0, "roi": float("nan"), "sharpe": float("nan")}
    sd = p.std(ddof=1) if n > 1 else 0.0
    return {"n": n, "roi": float(p.mean()),
            "sharpe": float(p.mean() / sd) if sd > 0 else 0.0}


# ── Mechanical-derivation check (angle 2) ─────────────────────────────────────────────────────

def ols(x: np.ndarray, y: np.ndarray) -> dict:
    """Simple least-squares y = a + b·x. Returns {slope, intercept, r2, n, resid_std}. NaN-safe.

    Used to (1) fit the BOOK's implied derivative mapping (book F5/NRFI implied ~ main close) and
    (2) the TRUE mapping (realized outcome ~ main close); a systematic gap between them, larger
    than half the cell's hold, is the angle-2 candidate exploit."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 3 or x.std() < _EPS:
        return {"slope": float("nan"), "intercept": float("nan"),
                "r2": float("nan"), "n": n, "resid_std": float("nan")}
    b, a = np.polyfit(x, y, 1)
    yhat = a + b * x
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > _EPS else float("nan")
    resid_std = float(np.sqrt(ss_res / max(n - 2, 1)))
    return {"slope": float(b), "intercept": float(a), "r2": r2,
            "n": n, "resid_std": resid_std}


def derivation_deviation(main_close: np.ndarray, book_implied: np.ndarray,
                         realized: np.ndarray) -> dict:
    """Compare the book's implied derivative mapping to the TRUE mapping off the main close.

    main_close   : the consensus main full-game number (total line, or de-vig P(home)).
    book_implied : the book's derivative implied (F5/NRFI line, or de-vig prob) per game.
    realized     : the realized derivative outcome (F5/NRFI total, or home-won-F5) per game.

    Returns the two OLS fits + the mean signed residual (realized − book_implied) and its z —
    a systematic, sign-consistent residual larger than half the hold is the angle-2 candidate;
    a residual ≈ 0 / inside noise ⇒ the book's mechanical derivation is correct (efficient)."""
    book_fit = ols(main_close, book_implied)
    true_fit = ols(main_close, realized)
    bi = np.asarray(book_implied, float)
    rz = np.asarray(realized, float)
    ok = np.isfinite(bi) & np.isfinite(rz)
    resid = rz[ok] - bi[ok]
    n = len(resid)
    if n == 0:
        mean_resid = se = z = float("nan")
    else:
        mean_resid = float(resid.mean())
        sd = resid.std(ddof=1) if n > 1 else 0.0
        se = float(sd / np.sqrt(n)) if sd > 0 else float("nan")
        z = float(mean_resid / se) if (se and se > 0) else float("nan")
    return {"book_fit": book_fit, "true_fit": true_fit,
            "mean_resid": mean_resid, "resid_se": se, "resid_z": z, "n": n}


# ── Multiple-comparison control ───────────────────────────────────────────────────────────────

def bh_fdr(pvalues, q: float = 0.10) -> dict:
    """Benjamini–Hochberg FDR control. Returns {threshold, n_survive, survive (bool mask aligned
    to the input order), n_tested}. NaN p-values never survive and don't count in the test count.

    The deflation analogue for the angle-1 calibration cells: a cell's bias is "real" only if its
    z-test survives FDR at q across EVERY cell tested — so an apparent mis-pricing among hundreds
    of cells isn't just the tail of the multiple-comparison surface (the E5.4 discipline)."""
    p = np.asarray(pvalues, float)
    finite = np.isfinite(p)
    pv = p[finite]
    m = len(pv)
    survive_full = np.zeros(len(p), bool)
    if m == 0:
        return {"threshold": float("nan"), "n_survive": 0, "survive": survive_full, "n_tested": 0}
    order = np.argsort(pv)
    ranked = pv[order]
    crit = (np.arange(1, m + 1) / m) * q
    passed = ranked <= crit
    if passed.any():
        kmax = np.max(np.where(passed)[0])
        thresh = float(ranked[kmax])
        finite_survive = pv <= thresh
    else:
        thresh = float("nan")
        finite_survive = np.zeros(m, bool)
    survive_full[np.where(finite)[0]] = finite_survive
    return {"threshold": thresh, "n_survive": int(finite_survive.sum()),
            "survive": survive_full, "n_tested": m}


# ── Book grouping (for the static-strategy grid) ──────────────────────────────────────────────

def book_mask(book_keys, group: str) -> np.ndarray:
    """Boolean mask selecting `group` ∈ {all, pinnacle, soft, majors, <single book>}."""
    bk = np.asarray(book_keys, dtype=object)
    if group == "all":
        return np.ones(len(bk), bool)
    if group == "pinnacle":
        return bk == PINNACLE
    if group == "soft":
        return bk != PINNACLE
    if group == "majors":
        return np.isin(bk, MAJOR_BOOKS)
    return bk == group


__all__ = [
    "F5_TOTALS", "F5_H2H", "NRFI", "TEAM_TOTALS", "ALT_TOTALS", "TOTALS_MARKETS",
    "MAJOR_BOOKS", "PINNACLE",
    "realized_over", "realized_home_f5", "h2h_payoff_vec",
    "devig_pair", "devig_triple",
    "calibration_z", "efficiency_summary",
    "static_total_payoffs", "static_summary",
    "ols", "derivation_deviation", "bh_fdr", "book_mask",
]
