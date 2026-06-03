"""
h2h_probability.py — Epic 11 (H2H), Stories 11.1 / 11.5

Moneyline betting quantities for the H2H model. De-vig Bovada's moneyline into a
home-win probability via the additive (normalization) method — consistent with
the totals de-vig in Story 10.3 (`totals_probability.devig_over_prob`) — and the
resulting H2H edge (model P(home) minus de-vigged market P(home)).
"""

from __future__ import annotations

from betting_ml.utils.totals_probability import american_to_implied


def devig_home_prob(home_american: float, away_american: float) -> float:
    """De-vigged P(home win) via the additive method:
    devig_home = implied_home / (implied_home + implied_away).

    Returns NaN if either price is missing/invalid so callers can fall back to a
    consensus source rather than emit a bogus 0/1.
    """
    try:
        ih = american_to_implied(home_american)
        ia = american_to_implied(away_american)
    except (TypeError, ValueError):
        return float("nan")
    total = ih + ia
    if total <= 0:
        return float("nan")
    return ih / total


def compute_h2h_edge(p_home_win: float, bovada_devig_home_prob: float) -> float:
    """Primary H2H signal: model P(home win) minus de-vigged market P(home win).
    Positive → home edge; negative → away edge."""
    return float(p_home_win) - float(bovada_devig_home_prob)
