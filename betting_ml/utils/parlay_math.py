"""parlay_math.py — Edge Program Story E10.1 (Parlay decision-support CALCULATOR, honest MVP).

Pure math for the "tell the user the TRUTH about the parlay they built" calculator:

  * per-leg odds conversions (American → decimal → book-implied probability),
  * the TRUE combined probability of a multi-leg parlay from our per-leg MODEL probabilities —
    independent (product) for legs in DIFFERENT games, correlation-ADJUSTED (Gaussian copula) for
    SAME-GAME legs (never the naive product — that overstates a same-game parlay's chance in the
    user's favour, the exact bias this tool exists to counter),
  * the book-implied probability + expected value from the parlay PRICE,
  * a plain-language, factual verdict.

🔒 HONEST FRAMING (non-negotiable — the crux of E10.1). This is a CALCULATOR / education tool, NOT
the +EV recommender (that is E10.3, hard-gated behind a proven edge we do NOT have; `best_alpha = 0`
holds). It exists to show that *most parlays are −EV after the vig*. So this module DELIBERATELY:
  * emits `best_alpha = 0` and `is_bet_recommendation = False` with every result,
  * frames expected value factually (a negative number is reported as plainly as a positive one) and
    NEVER as a "+EV play" / "value" / "edge" recommendation,
  * bakes the "most parlays are −EV after vig" disclaimer into every payload.
The banned-language guard (test_parlay_serving.py) fails the build if any promotional / bet-rec
wording ("+EV" as a sell, "value play/bet", "edge", "lock", "smash", "hammer", win-rate, "profitable")
ever creeps into this module or the shipped frontend. "Expected value" / "−EV" are the neutral,
factual vocabulary of the computation and are allowed.

── Same-game correlation (source-stamped, conservative) ─────────────────────────────────────────
The measured pairwise-correlation source (Epic 22.1 `mart_bet_correlation_matrix`) is SPECCED but not
built, and E10.1's parallel-safety rule forbids standing up a new correlation pipeline over the
lakehouse mid-migration. So we do NOT silently assume independence for same-game legs — we apply a
DOCUMENTED, deliberately CONSERVATIVE prior via a Gaussian copula, and stamp the source on every
same-game group so the UI can flag it:

  * `source = "conservative_prior"` — a documented negative latent-correlation prior
    (RHO_SAME_GAME_CONSERVATIVE) applied to same-game leg pairs. It is chosen NEGATIVE on purpose so
    the reported combined probability sits at or BELOW the naive independent product — i.e. we err
    toward NEVER overstating a same-game parlay's true chance (the honest, cautious direction for a
    −EV-warning tool). It is a prior, NOT a measurement: when Epic 22.1 lands, swap in the measured
    per-pair correlation matrix and re-stamp `source = "historical_pairwise"`; the copula machinery
    below is unchanged.

The math is pure NumPy + SciPy (multivariate-normal orthant probability) — no model, no Snowflake,
no network — so it is fully unit-testable and safe to import in the fast test gate.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from scipy.stats import multivariate_normal, norm

from betting_ml.utils.prop_edge import american_to_profit
from betting_ml.utils.totals_probability import american_to_implied

# ---------------------------------------------------------------------------
# Honest-framing constants — baked into every payload, asserted by the guard test.
# ---------------------------------------------------------------------------

MODEL_VERSION = "parlay_calculator_v1"

CAPTION = (
    "Build a parlay and see the truth about it: our model's estimate of its true combined "
    "probability next to the price the sportsbook is charging you, and the resulting expected "
    "value. A transparency calculator — not a bet recommendation."
)

DISCLAIMER = (
    "This is a decision-support calculator, not betting advice, and we make no profitability "
    "claim. Most parlays are negative expected value once the sportsbook's vig is priced in — "
    "combining legs multiplies the hold against you. Same-game legs are correlation-adjusted with "
    "a deliberately conservative prior (a measured same-game correlation is not yet available), so "
    "a same-game parlay's true probability is never overstated in your favour."
)

# Documented conservative same-game latent-correlation prior (see module docstring). Negative so the
# copula joint stays at/below the naive independent product — never overstating in the user's favour.
RHO_SAME_GAME_CONSERVATIVE = -0.20

_EPS = 1e-9


# ---------------------------------------------------------------------------
# Per-leg odds conversions
# ---------------------------------------------------------------------------

def american_to_decimal(american: float | int | None) -> float | None:
    """American odds → decimal odds (total return per $1 staked, incl. stake). +150 → 2.5, −120 → 1.833."""
    if american is None:
        return None
    try:
        return round(american_to_profit(float(american)) + 1.0, 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def decimal_to_implied(decimal_odds: float | None) -> float | None:
    """Decimal odds → book-implied probability (with vig): 1 / decimal."""
    if decimal_odds is None or decimal_odds <= 0:
        return None
    return round(1.0 / float(decimal_odds), 6)


def american_to_implied_prob(american: float | int | None) -> float | None:
    """American odds → book-implied probability (with vig)."""
    if american is None:
        return None
    try:
        return round(float(american_to_implied(float(american))), 6)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def combined_decimal_odds(leg_americans: Sequence[float | int | None]) -> float | None:
    """Cross-game parlay PRICE = product of per-leg decimal odds. None if any leg price is missing.

    Only valid for legs in DIFFERENT games — a same-game parlay (SGP) is priced by the book with its
    own correlation model, so its price cannot be inferred from the leg prices (E10.2's gap). The
    caller must fall back to a user-entered parlay price for any same-game parlay.
    """
    dec = 1.0
    for a in leg_americans:
        d = american_to_decimal(a)
        if d is None:
            return None
        dec *= d
    return round(dec, 6)


# ---------------------------------------------------------------------------
# True combined probability (independent product + same-game Gaussian copula)
# ---------------------------------------------------------------------------

def _clip_prob(p: float) -> float:
    return float(min(max(p, _EPS), 1.0 - _EPS))


def copula_joint_probability(
    hit_probs: Sequence[float],
    rho: float = RHO_SAME_GAME_CONSERVATIVE,
) -> float:
    """Joint P(all legs hit) for correlated legs, via a Gaussian copula with common latent corr `rho`.

    Each leg i has marginal P(hit) = p_i. Introduce standard-normal latents Z_i with an exchangeable
    correlation matrix (rho off-diagonal) and thresholds t_i = Φ⁻¹(1 − p_i) so P(Z_i > t_i) = p_i.
    The joint upper-orthant probability P(Z_1 > t_1, …, Z_n > t_n) is, by symmetry (W = −Z ~ N(0, R)),
    the lower-orthant CDF of N(0, R) at (−t_1, …, −t_n). `rho` is clamped to keep R positive-definite
    for any leg count (rho > −1/(n−1)).
    """
    ps = [_clip_prob(p) for p in hit_probs]
    n = len(ps)
    if n == 0:
        return 1.0
    if n == 1:
        return round(ps[0], 6)
    # Keep the exchangeable correlation matrix positive-definite: rho ∈ (−1/(n−1), 1).
    lo = -1.0 / (n - 1) + 1e-6
    r = float(min(max(rho, lo), 1.0 - 1e-6))
    thresholds = np.array([norm.ppf(1.0 - p) for p in ps])  # t_i
    cov = np.full((n, n), r)
    np.fill_diagonal(cov, 1.0)
    joint = multivariate_normal(mean=np.zeros(n), cov=cov, allow_singular=True).cdf(-thresholds)
    # Numerical guard: the joint can never exceed min(p_i) nor drop below 0.
    joint = float(min(max(joint, 0.0), min(ps)))
    return round(joint, 6)


def combined_true_probability(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """TRUE combined probability of a parlay from per-leg MODEL probabilities.

    `legs` — each a dict with at least:
        game_pk    : int|None   — same-game grouping key (None → treated as its own independent group)
        hit_prob   : float      — the model's probability the leg HITS (already oriented to the side)
        market_type, side, label … (carried through untouched for the UI)

    Legs in DIFFERENT games are independent → their group probabilities multiply. Legs in the SAME
    game are correlation-adjusted with the conservative copula prior (never the naive product).

    Returns:
        combined_prob        : float — Π over groups of each group's (copula or single) joint
        naive_product        : float — Π of every leg's hit_prob (independence — shown for contrast)
        groups               : list  — per game_pk: legs, joint, naive_product, correlation_source,
                                        is_same_game, is_correlation_estimated, note
    """
    resolved = [l for l in legs if l.get("hit_prob") is not None]
    naive_product = 1.0
    for l in resolved:
        naive_product *= _clip_prob(float(l["hit_prob"]))

    # Group by game_pk; legs without a game_pk are each their own independent group.
    groups_by_key: dict[Any, list[dict[str, Any]]] = {}
    for i, l in enumerate(resolved):
        key = l.get("game_pk")
        if key is None:
            key = f"__solo_{i}"
        groups_by_key.setdefault(key, []).append(l)

    combined = 1.0
    group_summaries: list[dict[str, Any]] = []
    for key, gl in groups_by_key.items():
        probs = [_clip_prob(float(l["hit_prob"])) for l in gl]
        g_naive = float(np.prod(probs))
        same_game = len(gl) > 1 and not str(key).startswith("__solo_")
        if same_game:
            joint = copula_joint_probability(probs, RHO_SAME_GAME_CONSERVATIVE)
            source = "conservative_prior"
            note = (
                "Same-game legs — correlation-adjusted with a conservative prior (a measured "
                "same-game correlation is not yet available), so the combined probability is not "
                "overstated in your favour."
            )
            same_market = len({l.get("market_type") for l in gl}) < len(gl)
            if same_market:
                note += (
                    " Heads up: two legs share the same game and market — an unusual same-game "
                    "combination; double-check they are not mutually exclusive."
                )
        else:
            joint = round(g_naive, 6)
            source = "independent"
            note = None
        combined *= joint
        group_summaries.append({
            "game_pk": None if str(key).startswith("__solo_") else key,
            "leg_count": len(gl),
            "is_same_game": same_game,
            "joint": round(joint, 6),
            "naive_product": round(g_naive, 6),
            "correlation_source": source,
            "is_correlation_estimated": same_game,  # a prior, not a measurement
            "note": note,
        })

    return {
        "combined_prob": round(combined, 6) if resolved else None,
        "naive_product": round(naive_product, 6) if resolved else None,
        "groups": group_summaries,
        "has_same_game": any(g["is_same_game"] for g in group_summaries),
    }


# ---------------------------------------------------------------------------
# Book-implied probability + expected value from the parlay PRICE
# ---------------------------------------------------------------------------

def expected_value_per_dollar(true_prob: float | None, decimal_parlay_odds: float | None) -> float | None:
    """Expected value per $1 staked = true_prob × decimal_parlay_odds − 1. Factual sign (may be < 0)."""
    if true_prob is None or decimal_parlay_odds is None or decimal_parlay_odds <= 0:
        return None
    return round(float(true_prob) * float(decimal_parlay_odds) - 1.0, 6)


def resolve_parlay_price(
    leg_americans: Sequence[float | int | None],
    has_same_game: bool,
    user_parlay_american: float | int | None,
) -> dict[str, Any]:
    """Determine the parlay PRICE (decimal odds) + where it came from.

    * A user-entered parlay price always wins (the only honest way to price a same-game parlay — the
      book uses its own correlation model, so an SGP price cannot be inferred from the leg prices;
      that gap is E10.2's feasibility spike).
    * Otherwise, for a purely CROSS-game parlay we compute the price = product of leg decimal odds.
    * A same-game parlay with no user-entered price has NO computable price → decimal None + a note.
    """
    user_dec = american_to_decimal(user_parlay_american)
    if user_dec is not None:
        return {"decimal": user_dec, "source": "user_entered", "note": None}
    if has_same_game:
        return {
            "decimal": None,
            "source": "unavailable_same_game",
            "note": (
                "This parlay has same-game legs. Sportsbooks price a same-game parlay with their own "
                "correlation model, so its price can't be computed from the individual leg odds — "
                "enter the book's posted parlay odds to see the implied probability and expected value."
            ),
        }
    computed = combined_decimal_odds(leg_americans)
    if computed is None:
        return {
            "decimal": None,
            "source": "unavailable_missing_leg_odds",
            "note": "Enter the odds for every leg (or the book's posted parlay odds) to price the parlay.",
        }
    return {"decimal": computed, "source": "computed_cross_game", "note": None}


# ---------------------------------------------------------------------------
# Plain-language, factual verdict (honest framing)
# ---------------------------------------------------------------------------

def build_verdict(
    true_prob: float | None,
    book_implied_prob: float | None,
    ev_per_dollar: float | None,
) -> str:
    """A factual, plain-language verdict. A negative expected value is stated as plainly as a
    positive one; NEVER a "+EV play" / "value" / recommendation. Always closes with the honest
    reminder that most parlays are −EV after vig."""
    tail = "Most parlays are negative expected value once the vig is priced in."
    if true_prob is None:
        return "Add at least one leg with a model probability to evaluate this parlay. " + tail
    tp = f"{true_prob * 100:.1f}%"
    if book_implied_prob is None or ev_per_dollar is None:
        return (
            f"The model estimates this parlay's true combined probability at {tp}. Enter the book's "
            f"parlay odds to see the implied probability and expected value. " + tail
        )
    imp = f"{book_implied_prob * 100:.1f}%"
    ev_pct = ev_per_dollar * 100
    if ev_per_dollar < 0:
        sign_txt = (
            f"Expected value is about {ev_pct:.1f}% per $1 staked — this parlay is negative "
            f"expected value (−EV)."
        )
    elif ev_per_dollar > 0:
        # Reported factually — NOT as a recommendation. E10.3 (a recommender) is hard-gated behind a
        # proven edge we do not have; this remains a calculator.
        sign_txt = (
            f"Expected value is about +{ev_pct:.1f}% per $1 staked — the model's estimate is higher "
            f"than the book's implied price here. This is a factual calculation, not a recommendation."
        )
    else:
        sign_txt = "Expected value is about break-even per $1 staked at these odds."
    return (
        f"The book's price implies {imp}; the model estimates {tp}. {sign_txt} " + tail
    )


# ---------------------------------------------------------------------------
# Full evaluation — assemble the calculator result payload
# ---------------------------------------------------------------------------

def evaluate_parlay(
    legs: Sequence[dict[str, Any]],
    user_parlay_american: float | int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the full parlay-calculator result from resolved legs.

    `legs` — each a dict with (at least): game_pk, market_type, side, hit_prob (model P the leg hits,
    already side-oriented; None if unresolvable), book_odds_american (the price the user is taking;
    may be None), plus any display fields (label, home_team, away_team, line, …) carried through.

    The no-edge posture (`best_alpha = 0`, `is_bet_recommendation = False`) and the honest disclaimer
    travel WITH the payload."""
    legs = list(legs)
    resolved = [l for l in legs if l.get("hit_prob") is not None]
    unresolved = [l for l in legs if l.get("hit_prob") is None]

    prob = combined_true_probability(resolved)
    true_prob = prob["combined_prob"]

    # Only legs that actually count toward the combined probability contribute their price.
    leg_americans = [l.get("book_odds_american") for l in resolved]
    price = resolve_parlay_price(leg_americans, prob["has_same_game"], user_parlay_american)
    decimal = price["decimal"]
    book_implied = decimal_to_implied(decimal)
    ev = expected_value_per_dollar(true_prob, decimal)
    verdict = build_verdict(true_prob, book_implied, ev)

    leg_rows: list[dict[str, Any]] = []
    for l in legs:
        hp = l.get("hit_prob")
        oa = l.get("book_odds_american")
        leg_rows.append({
            **l,
            "hit_prob": round(float(hp), 6) if hp is not None else None,
            "book_implied_prob": american_to_implied_prob(oa),
            "decimal_odds": american_to_decimal(oa),
            "resolved": hp is not None,
        })

    flags: list[str] = []
    if unresolved:
        flags.append(
            f"{len(unresolved)} leg(s) have no served model probability and are excluded from the "
            f"combined probability."
        )
    if price["note"]:
        flags.append(price["note"])
    if prob["has_same_game"]:
        flags.append(
            "Same-game legs are correlation-adjusted with a conservative prior (not a measured "
            "correlation), so the combined probability is never overstated in your favour."
        )

    return {
        "model_version": MODEL_VERSION,
        "leg_count": len(legs),
        "resolved_leg_count": len(resolved),
        "legs": leg_rows,
        "combined_true_prob": true_prob,
        "naive_independent_prob": prob["naive_product"],
        "correlation_groups": prob["groups"],
        "has_same_game": prob["has_same_game"],
        "parlay_decimal_odds": decimal,
        "parlay_price_source": price["source"],
        "book_implied_prob": book_implied,
        "expected_value_per_dollar": ev,
        "verdict": verdict,
        "flags": flags,
        "caption": CAPTION,
        "disclaimer": DISCLAIMER,
        # The no-edge posture travels with the data (honest framing — see module docstring).
        "best_alpha": 0,
        "is_bet_recommendation": False,
        "generated_at": generated_at,
    }


def oriented_hit_prob(market_type: str, side: str, model_prob: float | None) -> float | None:
    """Orient a served model probability to the chosen side (= P the leg HITS).

    * h2h:   model_prob = P(home win)   → 'home' → p, 'away' → 1−p
    * totals:model_prob = P(over)       → 'over' → p, 'under' → 1−p
    * strikeouts: model_prob = P(over the line) → 'over' → p, 'under' → 1−p
    Returns None if the probability is missing or the side is unrecognised.
    """
    if model_prob is None:
        return None
    p = float(model_prob)
    s = (side or "").lower()
    if market_type == "h2h":
        if s == "home":
            return p
        if s == "away":
            return 1.0 - p
    elif market_type in ("totals", "strikeouts"):
        if s == "over":
            return p
        if s == "under":
            return 1.0 - p
    return None
