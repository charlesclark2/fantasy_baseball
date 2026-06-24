"""
totals_probability.py — Epic 10, Story 10.3

Turn the Layer 3 totals champion's NegBin(mu, r) predictive distribution into
betting quantities: P(over)/P(under)/P(push) via the NegBin CDF (replaces the
Normal-CDF approximation that caused over-confidence), an 80% credible interval
on P(over) propagated from the uncertainty about mu, the de-vigged Bovada
over-probability, and the resulting edge.

NB2 parameterization: mean = mu, dispersion = r; variance = mu + mu^2/r.
scipy.stats.nbinom uses (n=r, p=r/(r+mu)).
"""

from __future__ import annotations

from scipy.stats import nbinom


def compute_over_under_probs(mu: float, r: float, line: float) -> tuple[float, float, float]:
    """P(over), P(under), P(push) for a total `line` from NegBin(mu, r).

    Half-point lines (e.g. 8.5): no push — P(over)=P(X>=9)=1-P(X<=8).
    Integer lines (e.g. 9): push possible — P(under)=P(X<=8), P(push)=P(X=9),
    P(over)=P(X>9).
    """
    mu = max(float(mu), 1e-6)
    r = max(float(r), 1e-6)
    p = r / (r + mu)
    if line != int(line):                          # half-point → no push
        p_under = float(nbinom.cdf(int(line), n=r, p=p))
        return 1.0 - p_under, p_under, 0.0
    k = int(line)                                  # integer → push possible
    p_under = float(nbinom.cdf(k - 1, n=r, p=p))
    p_push = float(nbinom.pmf(k, n=r, p=p))
    p_over = 1.0 - p_under - p_push
    return p_over, p_under, p_push


def compute_over_prob_ci(mu: float, sigma: float, r: float, line: float,
                         n_sigma: float = 1.28) -> tuple[float, float]:
    """80% credible interval on P(over) via the delta method.

    `sigma` is the uncertainty about the conditional mean `mu` (epistemic). P(over)
    increases monotonically in mu, so the low/high CI endpoints come from
    mu ∓ n_sigma·sigma. n_sigma=1.28 → central 80%. With sigma=0 the interval
    collapses to the point estimate.
    """
    sigma = max(float(sigma), 0.0)
    lo_over, _, _ = compute_over_under_probs(mu - n_sigma * sigma, r, line)
    hi_over, _, _ = compute_over_under_probs(mu + n_sigma * sigma, r, line)
    return lo_over, hi_over


def american_to_implied(american: float) -> float:
    """Implied probability from American odds (vig included).

    Favorites (negative): |a|/(|a|+100). Underdogs (positive): 100/(a+100).
    (The spec text only gave the favorite case; both signs are handled here.)
    """
    a = float(american)
    if a < 0:
        return -a / (-a + 100.0)
    return 100.0 / (a + 100.0)


def devig_over_prob(over_american: float, under_american: float) -> float:
    """De-vigged P(over) via the additive (normalization) method:
    devig_over = implied_over / (implied_over + implied_under)."""
    io = american_to_implied(over_american)
    iu = american_to_implied(under_american)
    total = io + iu
    if total <= 0:
        return float("nan")
    return io / total


def compute_totals_edge(p_over: float, bovada_devig_over_prob: float) -> float:
    """Primary totals signal: model P(over) minus the de-vigged market P(over).
    Positive → over edge; negative → under edge."""
    return float(p_over) - float(bovada_devig_over_prob)


def prob_to_american(p: float) -> int:
    """Convert a win probability to its breakeven American-odds price (no-vig).

    Breakeven means EV = 0 exactly: decimal = 1/p.
    Returns an int rounded toward zero (standard sportsbook display convention).
    Clamps p to (0.001, 0.999) to avoid divide-by-zero at the extremes.
    """
    p = max(0.001, min(0.999, float(p)))
    decimal = 1.0 / p
    if decimal >= 2.0:                      # underdog
        return int(round((decimal - 1.0) * 100.0))
    else:                                   # favorite
        return int(round(-100.0 / (decimal - 1.0)))


def compute_conformal_total_runs_pi(mu: float, r: float, q_hat: float) -> tuple[int, int]:
    """Conformal-adjusted run-count PI with empirical ≥80% coverage (Story 10.9).

    Expands the NegBin 75% base PI (ppf(0.125)/ppf(0.875)) by q_hat runs on each
    side.  q_hat is loaded from conformal_totals.json (production value = 1 run).
    Returns (lo, hi) as non-negative integer run counts.
    """
    mu = max(float(mu), 1e-6)
    r_disp = max(float(r), 1e-6)
    p = r_disp / (r_disp + mu)
    lo = int(nbinom.ppf(0.125, n=r_disp, p=p)) - int(q_hat)
    hi = int(nbinom.ppf(0.875, n=r_disp, p=p)) + int(q_hat)
    return max(lo, 0), hi
