"""parlay_calc.py — Edge Program Story E10.1 (Parlay decision-support CALCULATOR, honest MVP).

PURE-STDLIB math for the "tell the user the TRUTH about the parlay they built" calculator. This module
lives INSIDE the backend and depends only on the standard-library `math` module — NO numpy, NO scipy,
NO `betting_ml` import — because the FastAPI Lambda bundle installs neither numpy/scipy nor the
`betting_ml` package (only `betting_ml/utils/game_day.py` is copied in). Importing anything heavier
from a serving router crashes the whole app on boot (every endpoint then 500s → the browser reports a
CORS error on all routes). Keep this module stdlib-only.

What it computes:
  * per-leg odds conversions (American → decimal → book-implied probability),
  * the TRUE combined probability of a multi-leg parlay from our per-leg MODEL probabilities —
    independent (product) for legs in DIFFERENT games, correlation-ADJUSTED (Gaussian copula) for
    SAME-GAME legs (never the naive product — that overstates a same-game parlay's chance in the
    user's favour, the exact bias this tool exists to counter),
  * the book-implied probability + expected value from the parlay PRICE,
  * a plain-language, factual verdict.

🔒 HONEST FRAMING (non-negotiable). This is a CALCULATOR / education tool, NOT the +EV recommender
(that is E10.3, hard-gated behind a proven advantage we do NOT have; `best_alpha = 0` holds). It
exists to show that *most parlays are −EV after the vig*. So every result carries `best_alpha = 0` and
`is_bet_recommendation = False`, frames expected value factually (a negative number reported as plainly
as a positive one — never a "+EV play"/"value"/"edge" recommendation), and bakes in the "most parlays
are −EV after vig" disclaimer. The banned-language guard (test_parlay_serving.py) fails the build if
any promotional / bet-rec wording ever creeps into this module's prose or the shipped frontend.

── Same-game correlation (source-stamped, conservative) ─────────────────────────────────────────
The measured pairwise-correlation source (Epic 22.1 `mart_bet_correlation_matrix`) is SPECCED but not
built, and E10.1's parallel-safety rule forbids standing up a new correlation pipeline mid-migration.
So we do NOT silently assume independence for same-game legs — we apply a DOCUMENTED, deliberately
CONSERVATIVE prior via a Gaussian copula, stamped `source = "conservative_prior"` on every same-game
group. The latent correlation is NEGATIVE on purpose so the reported combined probability sits at or
BELOW the naive independent product — we err toward NEVER overstating a same-game parlay's chance (the
honest direction for a −EV-warning tool). It is a prior, NOT a measurement: when Epic 22.1 lands, swap
in the measured per-pair correlation and re-stamp `source = "historical_pairwise"`; the copula
machinery below is unchanged.

The Gaussian machinery (standard-normal CDF/quantile, bivariate-normal orthant) is implemented in pure
Python (Acklam's inverse-normal + the Drezner–Wesolowsky bivariate-normal), validated against SciPy in
the tests — so the module is fully unit-tested and safe in the dependency-light Lambda bundle.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

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
# Pure-Python Gaussian helpers (no numpy / scipy)
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via the error function (stdlib math.erf)."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_ppf(p: float) -> float:
    """Standard-normal quantile (inverse CDF) — Acklam's rational approximation (|err| < 1.15e-9)."""
    p = min(max(p, _EPS), 1.0 - _EPS)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1.0 - 0.02425
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)


# Gauss–Legendre nodes/weights for Genz's bivariate-normal integral (three node sets by |r|).
_GL = {
    1: (  # |r| < 0.3
        [0.1713244923791705, 0.3607615730481384, 0.4679139345726904],
        [0.9324695142031522, 0.6612093864662647, 0.2386191860831970],
    ),
    2: (  # 0.3 <= |r| < 0.75
        [0.04717533638651177, 0.1069393259953183, 0.1600783285433464,
         0.2031674267230659, 0.2334925365383547, 0.2491470458134029],
        [0.9815606342467191, 0.9041172563704750, 0.7699026741943050,
         0.5873179542866171, 0.3678314989981802, 0.1252334085114692],
    ),
    3: (  # |r| >= 0.75
        [0.01761400713915212, 0.04060142980038694, 0.06267204833410906,
         0.08327674157670475, 0.1019301198172404, 0.1181945319615184,
         0.1316886384491766, 0.1420961093183821, 0.1491729864726037,
         0.1527533871307259],
        [0.9931285991850949, 0.9639719272779138, 0.9122344282513259,
         0.8391169718222188, 0.7463319064601508, 0.6360536807265150,
         0.5108670019508271, 0.3737060887154196, 0.2277858511416451,
         0.07652652113349733],
    ),
}


def _bvn_upper(dh: float, dk: float, r: float) -> float:
    """Standard bivariate-normal upper orthant P(X ≥ dh, Y ≥ dk), corr r.

    Faithful pure-Python port of Alan Genz's `bvnu` (the reference routine behind SciPy's/MATLAB's
    bivariate-normal CDF) — accurate to ~1e-14. Returns exactly what the copula joint needs, so no
    lower-CDF conversion is required.
    """
    if abs(r) < 1e-15:
        return _norm_cdf(-dh) * _norm_cdf(-dk)
    tp = 2.0 * math.pi
    h, k = dh, dk
    hk = h * k
    bvn = 0.0
    ng = 1 if abs(r) < 0.3 else (2 if abs(r) < 0.75 else 3)
    w, x = _GL[ng]
    if abs(r) < 0.925:
        hs = (h * h + k * k) / 2.0
        asr = math.asin(r) / 2.0
        for i in range(len(w)):
            for sign in (-1.0, 1.0):
                sn = math.sin(asr * (1.0 + sign * x[i]))
                bvn += w[i] * math.exp((sn * hk - hs) / (1.0 - sn * sn))
        bvn = bvn * asr / tp + _norm_cdf(-h) * _norm_cdf(-k)
    else:
        if r < 0.0:
            k = -k
            hk = -hk
        if abs(r) < 1.0:
            as_ = (1.0 - r) * (1.0 + r)
            a = math.sqrt(as_)
            bs = (h - k) ** 2
            c = (4.0 - hk) / 8.0
            d = (12.0 - hk) / 16.0
            asr = -(bs / as_ + hk) / 2.0
            if asr > -100.0:
                bvn = a * math.exp(asr) * (1.0 - c * (bs - as_) * (1.0 - d * bs / 5.0) / 3.0
                                           + c * d * as_ * as_ / 5.0)
            if hk > -100.0:
                b = math.sqrt(bs)
                sp = math.sqrt(tp) * _norm_cdf(-b / a)
                bvn = bvn - math.exp(-hk / 2.0) * sp * b * (1.0 - c * bs * (1.0 - d * bs / 5.0) / 3.0)
            a = a / 2.0
            for i in range(len(w)):
                for sign in (-1.0, 1.0):
                    xs = (a * (1.0 + sign * x[i])) ** 2
                    rs = math.sqrt(1.0 - xs)
                    asr1 = -(bs / xs + hk) / 2.0
                    if asr1 > -100.0:
                        sp = 1.0 + c * xs * (1.0 + d * xs)
                        ep = math.exp(-hk * xs / (2.0 * (1.0 + rs) ** 2)) / rs
                        bvn += a * w[i] * math.exp(asr1) * (ep - sp)
            bvn = -bvn / tp
        if r > 0.0:
            bvn += _norm_cdf(-max(h, k))
        elif h >= k:
            bvn = -bvn
        else:
            if h < 0.0:
                lhk = _norm_cdf(k) - _norm_cdf(h)
            else:
                lhk = _norm_cdf(-h) - _norm_cdf(-k)
            bvn = lhk - bvn
    return min(max(bvn, 0.0), 1.0)


def _bvn_joint_hit(p_a: float, p_b: float, r: float) -> float:
    """P(both legs hit) for two Bernoulli legs coupled by a Gaussian copula with latent corr r.

    thresholds t = Φ⁻¹(1−p) → P(Z>t)=p; joint upper-orthant P(Z_a>t_a, Z_b>t_b) = bvnu(t_a, t_b, r)."""
    return _bvn_upper(_norm_ppf(1.0 - p_a), _norm_ppf(1.0 - p_b), r)


# ---------------------------------------------------------------------------
# Per-leg odds conversions
# ---------------------------------------------------------------------------

def american_to_decimal(american: float | int | None) -> float | None:
    """American odds → decimal odds (total return per $1 staked, incl. stake). +150 → 2.5, −120 → 1.833."""
    if american is None:
        return None
    try:
        a = float(american)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    dec = (a / 100.0 if a > 0 else 100.0 / abs(a)) + 1.0
    return round(dec, 6)


def decimal_to_implied(decimal_odds: float | None) -> float | None:
    """Decimal odds → book-implied probability (with vig): 1 / decimal."""
    if decimal_odds is None or decimal_odds <= 0:
        return None
    return round(1.0 / float(decimal_odds), 6)


def american_to_implied_prob(american: float | int | None) -> float | None:
    """American odds → book-implied probability (with vig)."""
    return decimal_to_implied(american_to_decimal(american))


def combined_decimal_odds(leg_americans: Sequence[float | int | None]) -> float | None:
    """Cross-game parlay PRICE = product of per-leg decimal odds. None if any leg price is missing.

    Only valid for legs in DIFFERENT games — a same-game parlay (SGP) is priced by the book with its
    own correlation model, so its price cannot be inferred from the leg prices (E10.2's gap).
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
    """Joint P(all legs hit) for correlated legs via a Gaussian copula with latent corr `rho`.

    * n == 1 → the leg's own probability.
    * n == 2 → the exact bivariate-normal orthant (Drezner–Wesolowsky).
    * n >= 3 → a documented CONSERVATIVE fallback: the naive product scaled by the SMALLEST pairwise
      copula ratio across all leg pairs. With the negative prior every pairwise ratio ≤ 1, so the
      result is ≤ the naive product (never overstated) and needs no multivariate-normal routine.
    """
    ps = [_clip_prob(p) for p in hit_probs]
    n = len(ps)
    if n == 0:
        return 1.0
    if n == 1:
        return round(ps[0], 6)
    if n == 2:
        j = _bvn_joint_hit(ps[0], ps[1], rho)
        return round(min(max(j, 0.0), min(ps)), 6)
    naive = 1.0
    for p in ps:
        naive *= p
    min_ratio = 1.0
    for i in range(n):
        for j in range(i + 1, n):
            pair = _bvn_joint_hit(ps[i], ps[j], rho)
            ratio = pair / (ps[i] * ps[j]) if ps[i] * ps[j] > 0 else 1.0
            min_ratio = min(min_ratio, ratio)
    joint = naive * min_ratio
    return round(min(max(joint, 0.0), min(ps)), 6)


def combined_true_probability(legs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """TRUE combined probability of a parlay from per-leg MODEL probabilities.

    `legs` — each a dict with at least `game_pk` (same-game grouping key; None → its own independent
    group), `hit_prob` (the model's probability the leg HITS, side-oriented), plus display fields.

    Legs in DIFFERENT games multiply (independence); SAME-GAME legs are correlation-adjusted with the
    conservative copula prior (never the naive product). Returns the combined probability, the naive
    independent product (for contrast), and a per-group breakdown with source stamps.
    """
    resolved = [l for l in legs if l.get("hit_prob") is not None]
    naive_product = 1.0
    for l in resolved:
        naive_product *= _clip_prob(float(l["hit_prob"]))

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
        g_naive = 1.0
        for p in probs:
            g_naive *= p
        same_game = len(gl) > 1 and not str(key).startswith("__solo_")
        if same_game:
            joint = copula_joint_probability(probs, RHO_SAME_GAME_CONSERVATIVE)
            source = "conservative_prior"
            note = (
                "Same-game legs — correlation-adjusted with a conservative prior (a measured "
                "same-game correlation is not yet available), so the combined probability is not "
                "overstated in your favour."
            )
            if len({l.get("market_type") for l in gl}) < len(gl):
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
            "is_correlation_estimated": same_game,
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

    A user-entered price always wins (the only honest way to price a same-game parlay — the book uses
    its own correlation model, so an SGP price can't be inferred from the leg prices; that gap is
    E10.2's feasibility spike). Otherwise a purely CROSS-game parlay price = product of leg decimals; a
    same-game parlay with no user price has no computable price.
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
    """A factual, plain-language verdict. A negative expected value is stated as plainly as a positive
    one; NEVER a "+EV play" / recommendation. Always closes with the honest reminder that most parlays
    are −EV after vig."""
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
        sign_txt = (
            f"Expected value is about +{ev_pct:.1f}% per $1 staked — the model's estimate is higher "
            f"than the book's implied price here. This is a factual calculation, not a recommendation."
        )
    else:
        sign_txt = "Expected value is about break-even per $1 staked at these odds."
    return f"The book's price implies {imp}; the model estimates {tp}. {sign_txt} " + tail


# ---------------------------------------------------------------------------
# Full evaluation — assemble the calculator result payload
# ---------------------------------------------------------------------------

def evaluate_parlay(
    legs: Sequence[dict[str, Any]],
    user_parlay_american: float | int | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the full parlay-calculator result from resolved legs.

    `legs` — each a dict with (at least) game_pk, market_type, side, hit_prob (model P the leg hits,
    already side-oriented; None if unresolvable), book_odds_american (may be None), + display fields.
    The no-edge posture (`best_alpha = 0`, `is_bet_recommendation = False`) + the honest disclaimer
    travel WITH the payload."""
    legs = list(legs)
    resolved = [l for l in legs if l.get("hit_prob") is not None]
    unresolved = [l for l in legs if l.get("hit_prob") is None]

    prob = combined_true_probability(resolved)
    true_prob = prob["combined_prob"]

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
        "best_alpha": 0,
        "is_bet_recommendation": False,
        "generated_at": generated_at,
    }


def oriented_hit_prob(market_type: str, side: str, model_prob: float | None) -> float | None:
    """Orient a served model probability to the chosen side (= P the leg HITS).

    * h2h:    model_prob = P(home win)     → 'home' → p, 'away' → 1−p
    * totals: model_prob = P(over)         → 'over' → p, 'under' → 1−p
    * strikeouts: model_prob = P(over line)→ 'over' → p, 'under' → 1−p
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
