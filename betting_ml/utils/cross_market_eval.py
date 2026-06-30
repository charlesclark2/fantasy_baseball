"""cross_market_eval.py — Edge Program Story E13.14: cross-market constellation coherence (pure math).

E13.14 tests a DIFFERENT question than every prior program null. E5.4 / E13.13 / E13.8 asked "is OUR
prediction better than ONE line?" (efficient, PBO≈0.5). This asks: **"are the BOOKS' OWN markets on a
game mutually COHERENT, and where two markets CONTRADICT each other, does the side the implied/sharp
market favors win NET OF the bet-market's vig?"** The play is RELATIVE (market-vs-market) → partly
market-NEUTRAL: we don't predict the game, we arbitrage the books' own disagreement; the rule only
picks WHICH side of an inconsistency to take.

SCOPE = pure cached-data analysis, NO predictive model. This module is the PURE machinery; the
orchestration (`betting_ml/scripts/cross_market_eval/eval_cross_market.py`) reads the cached S3 data,
assembles the per-relation frames, runs the credence-gated grid, and writes the dossier.

HONEST BAR (baked into every output — the E13.13 lesson):
  * GAME-LEVEL collapse FIRST — book quotes on one game are correlated, not independent bets; per-quote
    PnL is averaged to ONE return per game before any t-test / DSR / PBO (`score_game_level`).
  * IN-FOLD centering — the coherent-market "wedge" offset is estimated leave-one-season-out
    (`loso_offset`); no same-season / same-game leakage.
  * FORCED side — the bet side is the SIGN of the cross-market deviation, never the realized outcome.
  * The cashability proxy is realized-outcome ROI net of the bet-market's OWN vig (the offered American
    price embeds the overround — the E13.13 / E5.4 unit). True beat-the-close forward CLV is the
    forward leg, not here.

Reuses the program's odds + deflation primitives so the math matches everywhere:
  - `derivative_eval.devig_pair` (additive de-vig), `bh_fdr`, `book_mask`,
  - `prop_gate.payoff_vec` (totals over/under settlement net of the offered vig),
  - `overfitting.pbo_cscv` / `deflated_sharpe` (the program go-live deflation).
"""

from __future__ import annotations

from math import erf, log, sqrt

import numpy as np

# Re-exported odds + deflation primitives (single source of truth for the de-vig / FDR / book groups).
from betting_ml.utils.derivative_eval import (  # noqa: F401  (re-exported on purpose)
    MAJOR_BOOKS, PINNACLE, bh_fdr, book_mask, devig_pair,
)
from betting_ml.utils.overfitting import deflated_sharpe, pbo_cscv
from betting_ml.utils.prop_gate import payoff_vec

_EPS = 1e-9
_POISSON_CAP = 60   # max k summed in the Poisson SF (team/player run counts never approach this)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Normal CDF + the Bayesian credence (no scipy dependency)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def normal_cdf(z: float) -> float:
    """Standard-normal CDF Φ(z) via the error function (scipy-free)."""
    if not np.isfinite(z):
        return float("nan")
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def credence(deviation, joint_sd) -> np.ndarray:
    """Posterior credence that the cross-market deviation carries its OBSERVED sign.

    The deviation posterior is d ~ Normal(deviation, joint_sd) (the across-book line-setting noise on
    the implied/posted quantities). The credence the true deviation is non-zero in the observed
    direction = Φ(|deviation| / joint_sd) ∈ [0.5, 1]. joint_sd==0 ⇒ a degenerate point posterior:
    credence 1 if deviation≠0 else 0.5 (no information). NaN-safe (NaN in → NaN out)."""
    d = np.asarray(deviation, float)
    s = np.asarray(joint_sd, float)
    out = np.full(d.shape, np.nan, float)
    ok = np.isfinite(d) & np.isfinite(s)
    # sd > 0 → the normal credence
    pos = ok & (s > _EPS)
    if pos.any():
        z = np.abs(d[pos]) / s[pos]
        out[pos] = [0.5 * (1.0 + erf(zi / sqrt(2.0))) for zi in z]
    # sd == 0 → point posterior
    zero = ok & (s <= _EPS)
    out[zero] = np.where(np.abs(d[zero]) > _EPS, 1.0, 0.5)
    return out


def forced_side(deviation) -> np.ndarray:
    """The bet side on the bet-market, FORCED by the deviation sign (zero outcome DOF):
    deviation>0 (market A implies higher than the posted line) ⇒ 'over', else 'under'."""
    d = np.asarray(deviation, float)
    return np.where(d > 0, "over", "under").astype(object)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Implied mean from a de-vigged O/U prop line (the prop → run-value posterior basis)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def poisson_sf(threshold: float, lam: float) -> float:
    """P(X > threshold) for X ~ Poisson(lam). threshold half-integer (no push) or integer.

    P(X > t) = P(X ≥ floor(t) + 1) = 1 − Σ_{k≤floor(t)} e^{-λ} λ^k / k!. scipy-free; bounded sum."""
    if not (np.isfinite(threshold) and np.isfinite(lam)) or lam < 0:
        return float("nan")
    k_le = int(np.floor(threshold))
    if k_le < 0:
        return 1.0
    # cumulative Poisson pmf up to k_le (stable incremental term)
    term = np.exp(-lam)
    cdf = term
    for k in range(1, min(k_le, _POISSON_CAP) + 1):
        term *= lam / k
        cdf += term
    return float(np.clip(1.0 - cdf, 0.0, 1.0))


def poisson_mean_from_p_over(p_over: float, line: float) -> float:
    """Invert a de-vigged P(stat > line) into the implied Poisson mean λ (E[stat]).

    The canonical batter `runs_scored` / `rbis` line is 0.5 → closed form λ = −ln(1 − P(≥1)). For a
    general half-integer line, λ is found by bisection on the monotone Poisson SF. Returns NaN for an
    out-of-range probability. This is the per-player implied run-value used to SUM a team's offense."""
    p = float(p_over)
    if not (np.isfinite(p) and np.isfinite(line)) or not (0.0 < p < 1.0):
        return float("nan")
    # closed form for the dominant 0.5 line: P(X≥1) = 1 − e^{−λ}
    if abs(line - 0.5) < 1e-9:
        return float(-log(1.0 - p))
    lo, hi = 0.0, 40.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if poisson_sf(line, mid) < p:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Leave-one-season-out centering (the coherent-market "wedge" offset — in-fold, no leakage)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def loso_offset(residual, season) -> np.ndarray:
    """Per-row leave-one-season-out median of `residual` (= implied_A − posted_B).

    Two coherent markets differ by a near-constant structural wedge (each leg carries vig, half-run
    rounding, etc.). We center each game's residual on the median residual of the OTHER seasons, so the
    DEVIATION (residual − offset) is the genuine inconsistency, and the wedge itself never leaks from
    the same season. A single-season frame falls back to the global median (logged as degenerate)."""
    r = np.asarray(residual, float)
    s = np.asarray(season, object)
    out = np.full(r.shape, np.nan, float)
    seasons = [v for v in set(s.tolist()) if v is not None]
    finite = np.isfinite(r)
    if len(seasons) < 2:
        med = float(np.median(r[finite])) if finite.any() else float("nan")
        out[:] = med
        return out
    for v in seasons:
        other = (s != v) & finite
        med = float(np.median(r[other])) if other.any() else (
            float(np.median(r[finite])) if finite.any() else float("nan"))
        out[s == v] = med
    return out


def loso_affine(implied_raw, posted_b, season):
    """Leave-one-season-out AFFINE calibration of market A's native quantity into market B's units.

    Two coherent markets are linked by the book's "mechanical derivation" — an affine map
    posted_B ≈ α + β·implied_raw (β rescales units: an incomplete prop-sum, the F5≈0.54 fraction;
    α absorbs the vig wedge). We fit (α,β) by OLS of posted_B on implied_raw over the OTHER seasons
    (LINES only — NO outcome) and apply it to the held-out season. The result `implied_A` is market
    A's implied quantity expressed in B's units; the **deviation** implied_A − posted_B is then the
    genuine cross-market inconsistency with the systematic scale+wedge removed (so a fixed-fraction
    derivative like F5 leaves only noise — the control returns consistent). A multiplicative scale,
    NOT a constant offset, is required: a constant offset would leave an F5 residual that scales with
    the total and manufacture a spurious inconsistency. Returns (implied_A, beta) per row; a
    single-season frame falls back to the global fit (logged as degenerate)."""
    x = np.asarray(implied_raw, float)
    y = np.asarray(posted_b, float)
    s = np.asarray(season, object)
    out = np.full(x.shape, np.nan, float)
    beta = np.full(x.shape, np.nan, float)

    def _fit(mask):
        ok = mask & np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 3 or x[ok].std() < _EPS:
            return None
        b, a = np.polyfit(x[ok], y[ok], 1)
        return float(a), float(b)

    glob = _fit(np.ones(x.shape, bool))
    seasons = [v for v in set(s.tolist()) if v is not None]
    if len(seasons) < 2 or glob is None:
        if glob is not None:
            a, b = glob
            out[:] = a + b * x
            beta[:] = b
        return out, beta
    for v in seasons:
        f = _fit(s != v) or glob
        a, b = f
        m = s == v
        out[m] = a + b * x[m]
        beta[m] = b
    return out, beta


def joint_sd(sd_a, sd_b, floor: float) -> np.ndarray:
    """Per-game posterior SD of the deviation = sqrt(var_A + var_B + floor²).

    sd_a / sd_b are the across-book dispersions of implied_A / posted_B (the line-setting noise; the
    Bayesian posterior width). `floor` is a relation-level minimum so a single-book game (dispersion
    undefined → 0) still carries a non-degenerate posterior. NaN dispersions are treated as 0."""
    a = np.nan_to_num(np.asarray(sd_a, float), nan=0.0)
    b = np.nan_to_num(np.asarray(sd_b, float), nan=0.0)
    return np.sqrt(a ** 2 + b ** 2 + float(floor) ** 2)


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Coherence diagnostics (per relation — does the constellation hang together?)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def _corr(x: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3 or x[ok].std() < _EPS or y[ok].std() < _EPS:
        return float("nan")
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def coherence_summary(implied_a, posted_b, realized_b) -> dict:
    """Per-relation coherence diagnostics (one row per game in).

    Returns n, corr(implied_A, posted_B) (how tightly the two markets agree), the OLS of posted_B on
    implied_A (slope≈1, intercept≈wedge ⇒ coherent mechanical derivation), the mean signed residual
    (the wedge), and the INFORMATION test: corr(realized, implied_A) vs corr(realized, posted_B). If
    implied_A tracks the realized outcome BETTER than the posted line does, the bet-market is leaving
    information on the table — the precondition for a relative-value edge."""
    ia = np.asarray(implied_a, float)
    pb = np.asarray(posted_b, float)
    rb = np.asarray(realized_b, float)
    ok = np.isfinite(ia) & np.isfinite(pb)
    n = int(ok.sum())
    resid = ia[ok] - pb[ok]
    # OLS posted_B ~ implied_A
    slope = intercept = float("nan")
    if n >= 3 and ia[ok].std() > _EPS:
        slope, intercept = np.polyfit(ia[ok], pb[ok], 1)
    ci = _corr(ia, rb)
    cp = _corr(pb, rb)
    return {
        "n": n,
        "corr_markets": _corr(ia, pb),
        "ols_slope": float(slope), "ols_intercept": float(intercept),
        "mean_resid": float(resid.mean()) if n else float("nan"),
        "resid_sd": float(resid.std(ddof=1)) if n > 1 else float("nan"),
        "corr_realized_implied": ci,
        "corr_realized_posted": cp,
        "info_gain": float(ci ** 2 - cp ** 2) if (np.isfinite(ci) and np.isfinite(cp)) else float("nan"),
    }


# ════════════════════════════════════════════════════════════════════════════════════════════════
# Game-level scoring (the honest-bar core — collapse correlated book-quotes to ONE return per game)
# ════════════════════════════════════════════════════════════════════════════════════════════════
def score_game_level(payoffs, game_pk, season, ym) -> dict | None:
    """Collapse per-(game × book) PnL to ONE return per game, then summarise the game-level series.

    payoffs : per-quote per-$1 PnL net of the offered vig (NaN-dropped).
    game_pk / season / ym : aligned arrays (ym = 'YYYY-MM' slice for PBO).

    Returns n (= unique GAMES), roi (mean game return), sharpe, roi_t/roi_p (one-sided t that ROI>0),
    per_season / per_ym means, season_sign_consistent, and `_payoffs` (the game-level series for DSR).
    None if no finite bet. THIS is where the E13.13 correlated-quote inflation is removed."""
    import pandas as pd
    p = np.asarray(payoffs, float)
    finite = np.isfinite(p)
    if not finite.any():
        return None
    q = pd.DataFrame({"game_pk": np.asarray(game_pk)[finite],
                      "season": np.asarray(season, object)[finite],
                      "ym": np.asarray(ym, object)[finite],
                      "p": p[finite]})
    games = q.groupby("game_pk").agg(p=("p", "mean"), season=("season", "first"),
                                     ym=("ym", "first")).reset_index()
    g = games["p"].to_numpy(float)
    n = len(games)
    sd = g.std(ddof=1) if n > 1 else 0.0
    per_season = {str(s): float(gg["p"].mean()) for s, gg in games.groupby("season")}
    per_ym = {str(y): float(gg["p"].mean()) for y, gg in games.groupby("ym")}
    signs = [np.sign(v) for v in per_season.values()]
    season_sign_consistent = bool(len(signs) >= 2 and len(set(signs)) == 1 and signs[0] != 0)
    if sd > 0 and n > 1:
        from math import erfc
        t = float(g.mean() / (sd / np.sqrt(n)))
        roi_p = float(0.5 * erfc(t / sqrt(2.0)))   # one-sided upper tail (ROI > 0)
    else:
        t, roi_p = float("nan"), float("nan")
    return {"n": n, "n_quotes": int(finite.sum()), "roi": float(g.mean()),
            "sharpe": float(g.mean() / sd) if sd > 0 else 0.0, "roi_t": t, "roi_p": roi_p,
            "per_season": per_season, "per_ym": per_ym,
            "season_sign_consistent": season_sign_consistent, "_payoffs": g}


def deflate_configs(configs: list[dict], *, min_games: int, fdr_q: float = 0.10) -> dict:
    """The full multiple-comparison deflation over the credence-gated config grid.

    Each config dict must carry: n (unique games), roi, sharpe, roi_p, per_ym, _payoffs. Returns the
    PBO (CSCV over year-month slices × selectable configs), the DSR on the in-sample-best (deflated by
    the selectable-config count), and the BH-FDR survival mask over every selectable config's ROI test.
    Selectable = n ≥ min_games. Mirrors the E13.13 `_deflate_static` discipline exactly."""
    sel = [c for c in configs if c.get("n", 0) >= min_games]
    static_fdr = bh_fdr([c.get("roi_p", float("nan")) for c in sel], q=fdr_q)
    for c, surv in zip(sel, static_fdr["survive"]):
        c["roi_fdr_survive"] = bool(surv)

    if len(sel) < 2:
        pbo = {"pbo": float("nan"), "note": f"only {len(sel)} selectable configs (need ≥2)"}
        dsr = {"dsr": float("nan"), "note": "no selectable config"}
        return {"pbo": pbo, "dsr": dsr, "fdr": _fdr_public(static_fdr, fdr_q),
                "n_selectable": len(sel)}

    yms = sorted({ym for c in sel for ym in c["per_ym"]})
    if len(yms) < 4:
        pbo = {"pbo": float("nan"), "note": f"only {len(yms)} ym slices (need ≥4 for CSCV)"}
    else:
        mat = np.array([[c["per_ym"].get(ym, np.nan) for c in sel] for ym in yms], float)
        dense = ~np.isnan(mat).any(axis=0)
        if dense.sum() >= 2:
            res = pbo_cscv(mat[:, dense], higher_is_better=True,
                           n_splits=min(16, len(yms)), max_combos=2000)
            pbo = {"pbo": res.pbo, "n_combos": res.n_combos, "n_configs": int(dense.sum()),
                   "n_splits": res.n_splits, "clears_live_pbo": res.clears_live_pbo}
        else:
            pbo = {"pbo": float("nan"), "note": "no config dense across all ym slices"}

    best = max(sel, key=lambda c: c["roi"])
    trial_sharpes = [c["sharpe"] for c in sel]
    if len(best["_payoffs"]) >= 3:
        d = deflated_sharpe(best["_payoffs"], n_trials=len(sel), trial_sharpes=trial_sharpes)
        dsr = {"dsr": d.dsr, "observed_sr": d.observed_sr, "sr0": d.sr0, "n_trials": d.n_trials,
               "n_obs": d.n_obs, "passes_live": d.passes_live,
               "best_config": best["name"], "best_roi": best["roi"]}
    else:
        dsr = {"dsr": float("nan"), "note": "best config <3 games"}
    return {"pbo": pbo, "dsr": dsr, "fdr": _fdr_public(static_fdr, fdr_q), "n_selectable": len(sel)}


def _fdr_public(fdr: dict, q: float) -> dict:
    return {"threshold": fdr["threshold"], "n_survive": fdr["n_survive"],
            "n_tested": fdr["n_tested"], "q": q}


__all__ = [
    "MAJOR_BOOKS", "PINNACLE", "bh_fdr", "book_mask", "devig_pair", "payoff_vec",
    "normal_cdf", "credence", "forced_side",
    "poisson_sf", "poisson_mean_from_p_over",
    "loso_offset", "loso_affine", "joint_sd",
    "coherence_summary", "score_game_level", "deflate_configs",
]
