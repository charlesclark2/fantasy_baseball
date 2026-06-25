"""prop_pricing.py — Edge Program Story E5.2 (Per-prop distributional pricing).

⭐ LEAD MARKET = PITCHER STRIKEOUTS. This module is the market-blind, fully-unit-tested
machinery that prices a player prop from the player's PREDICTIVE DISTRIBUTION (never the
book line — that enters only at E5.3/E5.4). It mirrors the E2.3 totals machinery
(`totals_distribution.py`): a pure-NumPy/SciPy compound sampler + a leakage-safe dispersion
calibration lever + PIT / calib_80 diagnostics (reused verbatim from `totals_distribution`).

THE PITCHER-STRIKEOUT MODEL — K = K-RATE × BATTERS-FACED (the prompt's two explicit
components, convolved):

  K-RATE (per-PA strikeout probability `p_k`)
  -------------------------------------------
  `effective_k_rate` composes three honest levers (and DELIBERATELY NOT a platoon/matchup
  conditioning term — E13.2 showed PA-outcome matchup signal is ≈all batter×pitcher IDENTITY,
  which log5 already captures by construction; conditioning on platoon added ≈0):
    1. EB CAREER + LEAGUE shrinkage of the pitcher's raw K-rate (`eb_shrink_rate`) — the
       small-sample edge: early-season / post-return, shrink the noisy rate toward
       career→league and let data take over as the batters-faced count grows.
    2. log5 (`log5`) combination with the opposing lineup's EB-shrunk K-propensity, relative
       to the league baseline — the standard odds-multiplication matchup combiner (identity-
       driven, the part log5 captures cleanly).
    3. CATCHER FRAMING (`framing_logit_adjust`) — the genuinely-underweighted factor (borderline
       strike → K; we have the data, books rarely price it). A SMALL logit shift (tempered).
  The bet thesis is market laziness (books price K off recent-avg + reputation) + the EB
  small-sample edge + framing — NOT a better matchup model. If the K market is as efficient
  as the game-level ones, E5.4 returns a clean null and that's fine.

  BATTERS-FACED (`draw_batters_faced`) — the K-opportunity DENOMINATOR
  -------------------------------------------------------------------
  Reuses `starter_ip_v1`'s NegBin over OUTS (the workload model is already a survival/hazard
  over outs on pitch-count/velocity/manager-pull inputs). Converts outs → batters faced via
  the pitcher's on-base-against rate: each PA is an out (prob 1−reach) or a reach (prob reach)
  and the starter is pulled around an outs target, so the reaches before `outs` outs are
  NegBin(n=outs, p=1−reach) → BF = outs + reaches. (Baserunning/DP outs are a small ignored
  correction, documented.)

  CONVOLUTION (`draw_strikeouts` / `price_strikeouts`)
  ----------------------------------------------------
  K | BF ~ Beta-Binomial(BF, mean=p_k, concentration=s). The Beta-Binomial concentration `s`
  is the leakage-safe calibration lever (the K analogue of E2.3's NegBin `r`): s→∞ is plain
  Binomial, smaller s adds the intra-start overdispersion real K counts show. `s` is fit by
  MLE on HELD-OUT residuals (`fit_betabinom_concentration`) and calibrated leakage-safe with an
  expanding window (`calibrate_concentration_expanding`) — season T sees only seasons < T.
  Marginalising BF's own uncertainty in the MC gives the honest K-count predictive
  distribution → quantile grid + p_over/p_under at the book's K line.

OTHER PHASE-1 PROPS (lighter; the K prop is the lead):
  * `pitcher_outs` → priced DIRECTLY off the `starter_ip_v1` NegBin over outs (`prob_over_negbin`).
  * `batter_total_bases` / `batter_hits` → per-batter PA-level outcome multinomial over an
    expected-PA count (`draw_batter_bases_hits`) from the EB wOBA/ISO component rates.

Pure NumPy/SciPy — no Snowflake, no model, no market data — so it is fully unit-tested. The
orchestration (loading actuals + the leak-clean EB rates + starter_ip_v1 μ, the purged-CV
PIT/calib gate, the S3 line join, the served artifact) lives in
scripts/prop_pricing/fit_prop_pricing.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import gammaln

# Reuse the E2.3 quantile-grid / p_over / calibration diagnostics verbatim — same contract, so
# prop pricing and totals pricing report calibration the identical way (one source of truth).
from betting_ml.utils.totals_distribution import (  # noqa: F401  (re-exported for callers)
    CALIB_80_GATE,
    DEFAULT_QUANTILES,
    interval_coverage,
    pit_flatness,
    prob_over,
    prob_push,
    quantile_grid,
    randomized_pit,
)

# Probabilities are clipped off the {0,1} boundary so log5 / logit transforms stay finite.
_EPS = 1e-6
# Concentration search bounds: s≈2 is heavy overdispersion, s≈500 ≈ Binomial.
_S_LO, _S_HI = 2.0, 500.0


# ---------------------------------------------------------------------------
# K-RATE component: EB shrinkage + log5 matchup + catcher-framing adjustment
# ---------------------------------------------------------------------------

def eb_shrink_rate(
    successes: np.ndarray | float,
    trials: np.ndarray | float,
    prior_rate: np.ndarray | float,
    prior_strength: float,
) -> np.ndarray:
    """Empirical-Bayes shrunk rate: (successes + prior_strength·prior_rate) / (trials + prior_strength).

    The small-sample shrinkage lever (the E5.2 edge): with few trials the estimate sits near
    `prior_rate` (career→league); as `trials` grows it converges to the raw rate. `prior_strength`
    is the pseudo-count (≈ the trials at which the raw and prior get equal weight). Vectorised;
    result clipped into (0,1). A pitcher with a career prior would call this twice — once with the
    career rate shrunk to the league, then the season rate shrunk to that career posterior — or
    pass a blended `prior_rate`; the orchestration composes the chain leak-cleanly.
    """
    successes = np.asarray(successes, dtype=float)
    trials = np.asarray(trials, dtype=float)
    prior_rate = np.asarray(prior_rate, dtype=float)
    k = float(prior_strength)
    out = (successes + k * prior_rate) / np.clip(trials + k, _EPS, None)
    return np.clip(out, _EPS, 1.0 - _EPS)


def log5(rate_a: np.ndarray | float, rate_b: np.ndarray | float,
         league: np.ndarray | float) -> np.ndarray:
    """log5 matchup combination of two rates relative to a league baseline (Bill James).

    For a batter-vs-pitcher event the matchup rate is the odds-multiplication
        p = (a·b/L) / (a·b/L + (1−a)(1−b)/(1−L)),
    where `a` = pitcher's rate, `b` = batter's rate, `L` = league rate. Reduces to `a` when
    `b==L` (a league-average opponent) and to `b` when `a==L` — the identity-preserving property
    that makes it the right combiner for the K-rate (E13.2: matchup signal ≈ identity, which
    log5 captures by construction). Vectorised; inputs clipped off {0,1}; result in (0,1).
    """
    a = np.clip(np.asarray(rate_a, dtype=float), _EPS, 1.0 - _EPS)
    b = np.clip(np.asarray(rate_b, dtype=float), _EPS, 1.0 - _EPS)
    lg = np.clip(np.asarray(league, dtype=float), _EPS, 1.0 - _EPS)
    num = (a * b) / lg
    den = num + ((1.0 - a) * (1.0 - b)) / (1.0 - lg)
    return np.clip(num / np.clip(den, _EPS, None), _EPS, 1.0 - _EPS)


def framing_logit_adjust(
    p: np.ndarray | float, framing_z: np.ndarray | float, gamma: float,
) -> np.ndarray:
    """Nudge a per-PA K probability by the catcher's framing, on the logit scale.

    logit(p') = logit(p) + gamma · framing_z, where `framing_z` is the catcher's framing-runs
    z-score (positive = a better framer → more borderline strikes → more strikeouts). `gamma` is
    SMALL and TEMPERED — framing is a genuinely-underweighted factor, not a dominant one — and is
    a fixed, pre-registered coefficient (NOT fit to the K line; market-blind). gamma=0 is the
    no-framing baseline. Vectorised; result in (0,1).
    """
    p = np.clip(np.asarray(p, dtype=float), _EPS, 1.0 - _EPS)
    z = np.asarray(framing_z, dtype=float)
    logit = np.log(p / (1.0 - p)) + float(gamma) * z
    return np.clip(1.0 / (1.0 + np.exp(-logit)), _EPS, 1.0 - _EPS)


def effective_k_rate(
    pitcher_k_rate: np.ndarray | float,
    lineup_k_rate: np.ndarray | float,
    league_k_rate: np.ndarray | float,
    *,
    framing_z: np.ndarray | float | None = None,
    framing_gamma: float = 0.0,
) -> np.ndarray:
    """Compose the per-PA strikeout probability `p_k` from the three honest levers.

    `pitcher_k_rate` / `lineup_k_rate` are expected to ALREADY be EB-shrunk (caller applies
    `eb_shrink_rate` leak-cleanly). Combines them via `log5` against `league_k_rate`, then applies
    the optional catcher-framing logit nudge. Returns the per-game per-PA K probability used by
    `draw_strikeouts`. NO platoon/TTO conditioning term — see the module docstring (E13.2 temper).
    """
    p = log5(pitcher_k_rate, lineup_k_rate, league_k_rate)
    if framing_z is not None and framing_gamma:
        p = framing_logit_adjust(p, framing_z, framing_gamma)
    return p


# ---------------------------------------------------------------------------
# BATTERS-FACED component: outs (starter_ip_v1 NegBin) → BF via on-base-against
# ---------------------------------------------------------------------------

def draw_batters_faced(
    mu_outs: np.ndarray,
    r_outs: np.ndarray | float,
    reach_rate: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    max_outs: int = 27,
) -> np.ndarray:
    """Draw `n_draws` batters-faced counts/game from the outs NegBin + an on-base-against reach.

    Step 1: outs ~ NegBin(r_outs, mu_outs) — `starter_ip_v1`'s served workload distribution
    (numpy parameterisation: `negative_binomial(r, p)` with p = r/(r+mu) ⇒ mean = mu), capped at
    `max_outs` (a 9-inning start).
    Step 2: each PA is an out (prob 1−reach) or a reach (prob reach); a starter pulled around an
    outs target faces NegBin(n=outs, p=1−reach) reaches before `outs` outs → BF = outs + reaches.
    (Mean BF = outs/(1−reach); baserunning/DP outs are a small ignored correction.)
    Returns an (n_games, n_draws) integer array.
    """
    mu = np.clip(np.asarray(mu_outs, dtype=float), 0.5, float(max_outs))
    r = np.broadcast_to(np.asarray(r_outs, dtype=float), mu.shape)
    reach = np.clip(np.broadcast_to(np.asarray(reach_rate, dtype=float), mu.shape), _EPS, 0.6)

    p_outs = (r / (r + mu))[:, None]                          # (n_games, 1)
    r_col = r[:, None]
    outs = rng.negative_binomial(r_col, p_outs, size=(mu.shape[0], n_draws))
    outs = np.clip(outs, 0, max_outs)

    q_success = (1.0 - reach)[:, None]                        # P(out) per PA
    # negative_binomial needs n ≥ 1; outs==0 starts (pulled before an out) face only reaches we
    # treat as 0 BF contribution beyond the (rare) event — clip n to ≥1, then zero those rows out.
    n_succ = np.clip(outs, 1, None)
    reaches = rng.negative_binomial(n_succ, np.broadcast_to(q_success, n_succ.shape))
    reaches = np.where(outs == 0, 0, reaches)
    return outs + reaches


# ---------------------------------------------------------------------------
# CONVOLUTION: K | BF ~ Beta-Binomial(BF, p_k, concentration s)
# ---------------------------------------------------------------------------

def draw_strikeouts(
    bf_samples: np.ndarray,
    p_k: np.ndarray | float,
    concentration: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Strikeout counts: K | BF ~ Beta-Binomial(BF, mean=p_k, concentration=s) per draw.

    `bf_samples` is the (n_games, n_draws) batters-faced array from `draw_batters_faced`; `p_k`
    is the per-game per-PA K probability (n_games,). Beta-Binomial draws p ~ Beta(α,β) per cell
    (α=p_k·s, β=(1−p_k)·s) then K ~ Binomial(BF, p) — the intra-start overdispersion lever `s`
    (concentration); s→∞ ⇒ plain Binomial. Returns an (n_games, n_draws) integer array.
    K ≤ BF by construction. (Strikeouts consume outs, so K and the balls-in-play outs are weakly
    coupled in the true joint; for the K MARGINAL this BF-then-K factorisation is exact given
    p_k = the per-PA K rate over all batters faced.)
    """
    p_k = np.clip(np.asarray(p_k, dtype=float), _EPS, 1.0 - _EPS)[:, None]
    s = float(concentration)
    alpha = p_k * s
    beta = (1.0 - p_k) * s
    p_draw = rng.beta(np.broadcast_to(alpha, bf_samples.shape),
                      np.broadcast_to(beta, bf_samples.shape))
    return rng.binomial(bf_samples.astype(np.int64), p_draw)


def scale_spread(samples: np.ndarray, lam: float) -> np.ndarray:
    """Variance-tightening recalibration of a count predictive: K' = round(mean + λ·(K − mean)).

    The marginal calibration lever (the K analogue of E2.3's served `r` / E13.6's temperature T):
    the compound K predictive inherits `starter_ip_v1`'s slightly over-wide outs intervals (its own
    calib_80 ≈ 0.90, not 0.80) plus the batters-faced uncertainty, so the raw K distribution
    over-covers (calib_80 > 0.80, PIT not flat). λ<1 shrinks each game's draws toward that game's
    predictive mean to hit PIT-flatness; λ=1 is the identity. Mean-preserving (so p_over centring is
    untouched), variance scales ≈ λ². Rounded back to non-negative integer counts. `samples` is
    (n_games, n_draws). `lam` is calibrated leakage-safe in the orchestration to minimise the pooled
    PIT decile deviation.
    """
    m = samples.mean(axis=1, keepdims=True)
    scaled = m + float(lam) * (samples - m)
    return np.clip(np.rint(scaled), 0, None)


def price_strikeouts(
    mu_outs: np.ndarray,
    r_outs: np.ndarray | float,
    reach_rate: np.ndarray | float,
    p_k: np.ndarray | float,
    concentration: float,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    max_outs: int = 27,
) -> np.ndarray:
    """End-to-end strikeout-count predictive samples: BF compound × per-PA K rate.

    Convenience wrapper: `draw_batters_faced` → `draw_strikeouts`. Returns (n_games, n_draws). Feed
    to `quantile_grid` / `prob_over` (over the book's K line) / the calibration diagnostics.
    """
    bf = draw_batters_faced(mu_outs, r_outs, reach_rate, rng, n_draws=n_draws, max_outs=max_outs)
    return draw_strikeouts(bf, p_k, concentration, rng)


# ---------------------------------------------------------------------------
# Beta-Binomial concentration — the leakage-safe K calibration lever (∼ E2.3 `r`)
# ---------------------------------------------------------------------------

def _betabinom_nll(k: np.ndarray, n: np.ndarray, mu: np.ndarray, s: float) -> float:
    """Mean Beta-Binomial NLL with mean `mu` and concentration `s` (α=μs, β=(1−μ)s).

    log P(k;n,α,β) = logC(n,k) + [logB(k+α, n−k+β) − logB(α,β)], logB = Σgammaln. Used to MLE the
    concentration on held-out (k, n=batters_faced, μ=p_k) residuals.
    """
    mu = np.clip(mu, _EPS, 1.0 - _EPS)
    a = mu * s
    b = (1.0 - mu) * s
    log_c = gammaln(n + 1.0) - gammaln(k + 1.0) - gammaln(n - k + 1.0)
    log_b_num = gammaln(k + a) + gammaln(n - k + b) - gammaln(n + a + b)
    log_b_den = gammaln(a) + gammaln(b) - gammaln(a + b)
    ll = log_c + log_b_num - log_b_den
    return float(-np.mean(ll))


def fit_betabinom_concentration(
    k_obs: np.ndarray, bf_obs: np.ndarray, p_k: np.ndarray,
) -> float:
    """MLE of the Beta-Binomial concentration `s` given observed strikeouts, the ACTUAL batters
    faced, and the predicted per-PA K rate.

    Identical role to `totals_distribution.fit_negbin_dispersion`: on HELD-OUT (eval-fold)
    residuals this recovers the intra-start overdispersion the predictive K distribution needs to
    be calibrated; on TRAIN-fit residuals it is optimistic. Bounded 1-D search on log(s).
    """
    k = np.asarray(k_obs, dtype=float)
    n = np.asarray(bf_obs, dtype=float)
    mu = np.clip(np.asarray(p_k, dtype=float), _EPS, 1.0 - _EPS)
    res = minimize_scalar(
        lambda log_s: _betabinom_nll(k, n, mu, float(np.exp(log_s))),
        bounds=(np.log(_S_LO), np.log(_S_HI)), method="bounded",
    )
    return float(np.exp(res.x))


def calibrate_concentration_expanding(
    seasons: np.ndarray, k_obs: np.ndarray, bf_obs: np.ndarray, p_k: np.ndarray,
) -> dict[int, float]:
    """Leakage-safe per-season concentration: for season T fit `s` on the strictly-prior seasons'
    held-out residuals (expanding walk-forward window — the deployed estimate for season T sees
    only seasons < T). Mirrors `totals_distribution.calibrate_dispersion_expanding`. Returns
    {season: s_used}; the earliest season (no prior residuals) is omitted (the un-gated seed).
    """
    seasons = np.asarray(seasons)
    k = np.asarray(k_obs, dtype=float)
    n = np.asarray(bf_obs, dtype=float)
    mu = np.asarray(p_k, dtype=float)
    out: dict[int, float] = {}
    for t in sorted(set(int(s) for s in seasons)):
        prior = seasons < t
        if prior.sum() < 50:
            continue
        out[t] = round(fit_betabinom_concentration(k[prior], n[prior], mu[prior]), 3)
    return out


# ---------------------------------------------------------------------------
# pitcher_outs — priced directly off the starter_ip_v1 NegBin over outs
# ---------------------------------------------------------------------------

def prob_over_negbin(
    mu: np.ndarray, r: np.ndarray | float, lines: np.ndarray | list[float],
) -> dict[float, np.ndarray]:
    """P(count > line) per game under a NegBin(mu, r) — the analytic price for `pitcher_outs`
    (line in OUTS) straight off `starter_ip_v1`. For a half-line the strict inequality is
    unambiguous; an integer line's equal-mass is a push (use `nbinom.pmf` separately if needed).
    Returns {line: (n_games,) array}. Uses the survival function (no sampling needed).
    """
    from scipy.stats import nbinom
    mu = np.clip(np.asarray(mu, dtype=float), 0.5, None)
    r = np.broadcast_to(np.asarray(r, dtype=float), mu.shape)
    p = r / (r + mu)
    out: dict[float, np.ndarray] = {}
    for ln in lines:
        # P(X > line) = P(X >= floor(line)+1) = sf(ceil(line)-1) for half-lines; use floor for ints.
        thresh = np.floor(ln)
        out[float(ln)] = nbinom.sf(thresh, r, p)
    return out


# ---------------------------------------------------------------------------
# batter_total_bases / batter_hits — per-batter PA-outcome multinomial
# ---------------------------------------------------------------------------

def draw_batter_bases_hits(
    expected_pa: np.ndarray | float,
    p_single: np.ndarray | float,
    p_double: np.ndarray | float,
    p_triple: np.ndarray | float,
    p_hr: np.ndarray | float,
    rng: np.random.Generator,
    *,
    n_draws: int = 10_000,
    pa_dispersion: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Total-bases and hit-count predictive samples for a batter from the per-PA outcome rates.

    Draws a PA count per game (Poisson around `expected_pa`; `pa_dispersion`>0 mixes a Gamma for
    lineup-turnover overdispersion), then a Multinomial over {single, double, triple, HR, other}
    per draw. total_bases = 1·1B + 2·2B + 3·3B + 4·HR; hits = 1B+2B+3B+HR. The four hit-type
    probabilities come from the batter's EB wOBA/ISO component posteriors (leak-clean, caller-
    supplied). Returns (total_bases_samples, hits_samples), each (n_games, n_draws).
    """
    epa = np.clip(np.asarray(expected_pa, dtype=float), 0.1, None)[:, None]
    if pa_dispersion > 0:
        shape = 1.0 / float(pa_dispersion)
        lam = rng.gamma(shape, epa / shape, size=(epa.shape[0], n_draws))
    else:
        lam = np.broadcast_to(epa, (epa.shape[0], n_draws))
    pa = rng.poisson(lam)

    n_games = epa.shape[0]
    bcast = lambda x: np.clip(np.broadcast_to(np.asarray(x, dtype=float), (n_games,)), 0.0, 1.0)
    ps, pd, pt, ph = bcast(p_single), bcast(p_double), bcast(p_triple), bcast(p_hr)
    p_out = np.clip(1.0 - (ps + pd + pt + ph), _EPS, 1.0)
    probs = np.stack([ps, pd, pt, ph, p_out], axis=1)        # (n_games, 5)
    probs = probs / probs.sum(axis=1, keepdims=True)

    tb = np.zeros(pa.shape, dtype=np.int64)
    hits = np.zeros(pa.shape, dtype=np.int64)
    for gi in range(pa.shape[0]):
        counts = rng.multinomial(pa[gi], probs[gi])          # (n_draws, 5)
        s, d, t, h = counts[:, 0], counts[:, 1], counts[:, 2], counts[:, 3]
        tb[gi] = s + 2 * d + 3 * t + 4 * h
        hits[gi] = s + d + t + h
    return tb, hits


# ---------------------------------------------------------------------------
# Served / calibration params (consumed by E5.3 edge + E5.4 gate + E5.5 UX)
# ---------------------------------------------------------------------------

@dataclass
class StrikeoutPricingParams:
    """The fitted E5.2 pitcher-strikeout calibration layer + served-contract spec.

    `concentration` is the pooled stable Beta-Binomial concentration `s` (the K analogue of E2.3's
    NegBin `r`) calibrated leakage-safe on held-out residuals. `league_k_rate` is the per-PA K
    baseline used by log5. `pitcher_prior_strength` / `lineup_prior_strength` are the EB pseudo-
    counts. `framing_gamma` is the (tempered, pre-registered) framing logit coefficient. `reach_rate
    _default` is the league on-base-against fallback for the BF conversion. JSON-roundtrippable (no
    model state — the μ_outs come from `starter_ip_v1` and the EB rates from the feature mart at
    score time). best_alpha = 0: calibration is product value, NOT an edge claim (E5.4 is the gate).
    """
    concentration: float
    league_k_rate: float
    spread_scale: float = 1.0
    pitcher_prior_strength: float = 200.0
    lineup_prior_strength: float = 150.0
    framing_gamma: float = 0.0
    reach_rate_default: float = 0.31
    n_draws: int = 10_000
    quantile_levels: tuple[float, ...] = DEFAULT_QUANTILES
    s_calibration: str = "expanding-window held-out residuals (leakage-safe Beta-Binomial MLE)"
    notes: str = ""
    version: str = "prop_pricing_strikeouts_v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "concentration": self.concentration,
            "league_k_rate": self.league_k_rate,
            "spread_scale": self.spread_scale,
            "pitcher_prior_strength": self.pitcher_prior_strength,
            "lineup_prior_strength": self.lineup_prior_strength,
            "framing_gamma": self.framing_gamma,
            "reach_rate_default": self.reach_rate_default,
            "n_draws": self.n_draws,
            "quantile_levels": list(self.quantile_levels),
            "s_calibration": self.s_calibration,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StrikeoutPricingParams":
        return cls(
            concentration=float(d["concentration"]),
            league_k_rate=float(d["league_k_rate"]),
            spread_scale=float(d.get("spread_scale", 1.0)),
            pitcher_prior_strength=float(d.get("pitcher_prior_strength", 200.0)),
            lineup_prior_strength=float(d.get("lineup_prior_strength", 150.0)),
            framing_gamma=float(d.get("framing_gamma", 0.0)),
            reach_rate_default=float(d.get("reach_rate_default", 0.31)),
            n_draws=int(d.get("n_draws", 10_000)),
            quantile_levels=tuple(d.get("quantile_levels", DEFAULT_QUANTILES)),
            s_calibration=d.get("s_calibration", ""),
            notes=d.get("notes", ""),
            version=d.get("version", "prop_pricing_strikeouts_v1"),
        )
