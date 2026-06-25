"""prop_edge.py — Edge Program Story E5.3 (market-AWARE de-vig + per-book prop comparison).

Pure, fully-unit-tested machinery for the FIRST market-aware prop step: take the E5.2 market-blind
K predictive distribution (samples), the book's two-way K over/under price, and emit the
model-vs-market comparison — de-vigged book implied, model P at the EXACT line (integer-line PUSH
handled), per-$1 EV, and the edge (model − de-vigged book). Pinnacle is carried as the sharp
fair-value anchor in the orchestration (`edge_devig_props.py`); this module is the math.

🔒 HONEST FRAMING (non-negotiable, see §0.1): every quantity here is a TRANSPARENCY / model-vs-market
comparison, NOT a bet recommendation. The prop vig is LARGE, so net-of-vig is the only honest read;
"edge" is model-RELATIVE and UNPROVEN until the E5.4 hard gate (PBO<0.2/DSR>0 per market,
multiple-comparison-corrected, + forward CLV). best_alpha = 0.

The market math reuses the existing two-way de-vig (`betting_ml/utils`): `american_to_implied` +
`implied_no_vig_pair` (the additive/normalisation method the A0.4.32 game-market pattern uses) —
extended here to props with the integer-line push convention the K market occasionally uses.

NAME→ID BRIDGE (the E5.2-flagged blocker): `normalize_name` folds accents, punctuation, case and the
Jr./Sr./III generational suffixes so the S3 K-prop lines (keyed on `player_name`, "First Last") join
to the E5.2 predictions (keyed on `pitcher_id`) via the `ref_players` name dimension ("Last, First").
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import numpy as np

# Reuse the canonical two-way de-vig already used for the game markets (A0.4.32 pattern).
from betting_ml.utils.market_features import implied_no_vig_pair
from betting_ml.utils.totals_probability import american_to_implied

# Generational / ordinal suffixes stripped during name normalisation (the Jr./Sr. ambiguity).
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


# ---------------------------------------------------------------------------
# NAME→ID bridge: normalisation (handles accents, punctuation, Jr./Sr., nicknames-by-spelling)
# ---------------------------------------------------------------------------

def normalize_name(name: str | None) -> str:
    """Fold a player name to a join key: strip accents, lowercase, drop punctuation + generational
    suffixes, collapse whitespace.

    Handles BOTH the S3 line format ("First Last", "Nestor Cortes Jr.") and the ref_players format
    ("Last, First" → caller reassembles as "First Last" first). Accent-folds (José → jose) via NFKD,
    drops periods/commas/apostrophes/hyphens→space, removes Jr/Sr/II/III/IV tokens, squeezes spaces.
    Returns "" for empty/None. This is the bridge's join key on BOTH sides.
    """
    if name is None:
        return ""
    s = str(name).strip()
    if not s:
        return ""
    # Drop parenthetical team disambiguators ("Logan Allen (CLE)" → "Logan Allen"); the
    # date-window + modelled-set bridge resolves the duplicate instead.
    s = re.sub(r"\([^)]*\)", " ", s)
    # Accent-fold (José → Jose, Peña → Pena).
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    # Punctuation → space (handles "Smith-Shawver", "O'Brien", "Cortes Jr.", "Ohtani, Shohei").
    s = re.sub(r"[.,'`\-]", " ", s)
    tokens = [t for t in s.split() if t and t not in _SUFFIXES]
    return " ".join(tokens)


def last_initial_key(norm_name: str) -> tuple[str, str] | None:
    """(last token, first initial) fallback key for the name bridge — folds nickname/legal-name and
    middle-name mismatches ("Matthew Boyd"↔"Matt Boyd", "Bryan Joseph Woo"↔"Bryan Woo", "JP Sears"↔
    "John Patrick Sears" all key to (woo/boyd/sears, b/m/j)). Resolved against the date window so
    last-name + initial collisions stay rare; genuine same-key starts on a date are flagged ambiguous.
    Returns None when the name has <2 tokens (can't form a last+first key)."""
    toks = (norm_name or "").split()
    if len(toks) < 2:
        return None
    return toks[-1], toks[0][0]


def ref_display_name(first_name: str | None, last_name: str | None) -> str:
    """Assemble a "First Last" display name from the ref_players first/last columns (its
    `player_name` is stored "Last, First"). Used before `normalize_name` so both sides key the same."""
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    return f"{fn} {ln}".strip()


# ---------------------------------------------------------------------------
# Two-way de-vig of a book's prop price (over/under), with the integer-line push convention
# ---------------------------------------------------------------------------

def devig_two_way(over_american: float | None, under_american: float | None) -> dict[str, float]:
    """De-vig a book's two-way K over/under price → fair (no-vig) implied probabilities + the hold.

    Returns {devig_over, devig_under, implied_over, implied_under, hold, valid}. The de-vig is the
    additive/normalisation method (`implied_no_vig_pair`); the two-way fair pair is push-EXCLUDED by
    construction (it sums to 1), which is the correct comparison target for an integer line where the
    push is refunded. `hold` = implied_over + implied_under − 1 (the book's overround / vig). When
    either side is missing/NaN the pair cannot be de-vigged → valid=False and the fair probs are NaN
    (a one-sided quote is reported, never silently treated as 50/50).
    """
    o = _as_float(over_american)
    u = _as_float(under_american)
    if o is None or u is None:
        io = american_to_implied(o) if o is not None else float("nan")
        iu = american_to_implied(u) if u is not None else float("nan")
        return {"devig_over": float("nan"), "devig_under": float("nan"),
                "implied_over": io, "implied_under": iu,
                "hold": float("nan"), "valid": False}
    io = american_to_implied(o)
    iu = american_to_implied(u)
    fair_over, fair_under = implied_no_vig_pair(o, u)
    return {"devig_over": float(fair_over), "devig_under": float(fair_under),
            "implied_over": float(io), "implied_under": float(iu),
            "hold": float(io + iu - 1.0), "valid": bool(np.isfinite(fair_over))}


def american_to_profit(american: float) -> float:
    """Profit per $1 staked at American odds (the `b` in EV = p·b − (1−p)). +150 → 1.5, −120 → 0.833."""
    a = float(american)
    return a / 100.0 if a > 0 else 100.0 / abs(a)


# ---------------------------------------------------------------------------
# Model P at the EXACT book line (half-line vs integer-line PUSH) — from predictive samples
# ---------------------------------------------------------------------------

def line_probabilities(samples: np.ndarray, line: float) -> dict[str, float]:
    """Model P(over)/P(under)/P(push) at a book's K line, from the predictive K-count samples.

    HANDLES THE HALF vs INTEGER convention explicitly (the AC):
      * half-line (e.g. 5.5): over = P(K > 5.5) = P(K ≥ 6); under = P(K ≤ 5); push = 0.
      * integer line (e.g. 6): over = P(K > 6) = P(K ≥ 7); push = P(K = 6); under = P(K ≤ 5).
    Computed directly off the sample array (which already carries the served `scale_spread` λ
    recalibration), so it is exact for whatever line the book posts — no half-vs-integer fudge.
    `samples` is a 1-D integer K-count array for ONE pitcher×date. Returns probs that sum to 1.
    """
    s = np.asarray(samples)
    n = s.size
    if n == 0:
        return {"p_over": float("nan"), "p_under": float("nan"), "p_push": float("nan")}
    p_over = float(np.count_nonzero(s > line) / n)
    p_push = float(np.count_nonzero(s == line) / n)   # non-zero only at integer lines
    p_under = float(np.count_nonzero(s < line) / n)
    return {"p_over": p_over, "p_under": p_under, "p_push": p_push}


def conditional_no_push(p_over: float, p_under: float) -> tuple[float, float]:
    """Push-excluded model probabilities P(over | not push), P(under | not push).

    The apples-to-apples comparison target for the two-way de-vigged book pair (which is itself
    push-excluded). For a half-line (p_push=0) this is the identity. Returns (nan, nan) if both
    sides are ~0 (degenerate)."""
    denom = p_over + p_under
    if denom <= 0:
        return float("nan"), float("nan")
    return p_over / denom, p_under / denom


def ev_per_dollar(p_win: float, p_lose: float, american: float) -> float:
    """EV per $1 staked on one side: p_win·profit − p_lose·1 (push mass is a stake refund → 0 PnL).

    For a half-line p_win + p_lose = 1 ⇒ EV = p_win·(b+1) − 1. For an integer line the push mass is
    excluded from BOTH terms (refunded), so EV uses the raw over/under masses, not the conditional."""
    b = american_to_profit(american)
    return float(p_win) * b - float(p_lose)


def compute_edge_row(
    samples: np.ndarray, line: float,
    over_american: float | None, under_american: float | None,
) -> dict[str, Any]:
    """One model-vs-market comparison row: model P at the line (push-aware), the book's de-vigged
    implied, the edge (model − book, push-excluded), and per-$1 EV for each side.

    EDGE = model P(side | not push) − book de-vigged P(side). EV uses the raw (push-inclusive)
    masses so an integer-line push is correctly a refund. `best_side`/`best_edge`/`best_ev` pick the
    larger-edge side for display convenience (NOT a bet rec — best_alpha=0). All NaN-safe."""
    mp = line_probabilities(samples, line)
    dv = devig_two_way(over_american, under_american)
    over_cond, under_cond = conditional_no_push(mp["p_over"], mp["p_under"])

    edge_over = over_cond - dv["devig_over"] if dv["valid"] else float("nan")
    edge_under = under_cond - dv["devig_under"] if dv["valid"] else float("nan")
    ev_over = (ev_per_dollar(mp["p_over"], mp["p_under"], over_american)
               if _as_float(over_american) is not None else float("nan"))
    ev_under = (ev_per_dollar(mp["p_under"], mp["p_over"], under_american)
                if _as_float(under_american) is not None else float("nan"))

    # Display pick: the side with the larger model-vs-market edge (ties / NaN → over).
    if _finite(edge_over) or _finite(edge_under):
        if not _finite(edge_under) or (_finite(edge_over) and edge_over >= edge_under):
            best_side, best_edge, best_ev = "over", edge_over, ev_over
        else:
            best_side, best_edge, best_ev = "under", edge_under, ev_under
    else:
        best_side, best_edge, best_ev = "", float("nan"), float("nan")

    return {
        "line": float(line),
        "is_integer_line": bool(float(line) == np.floor(float(line))),
        "model_p_over": mp["p_over"], "model_p_under": mp["p_under"], "model_p_push": mp["p_push"],
        "model_p_over_cond": over_cond, "model_p_under_cond": under_cond,
        "book_devig_over": dv["devig_over"], "book_devig_under": dv["devig_under"],
        "book_hold": dv["hold"], "devig_valid": dv["valid"],
        "edge_over": edge_over, "edge_under": edge_under,
        "ev_over": ev_over, "ev_under": ev_under,
        "best_side": best_side, "best_edge": best_edge, "best_ev": best_ev,
    }


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _as_float(x: Any) -> float | None:
    """Coerce to float, returning None for None/NaN/blank (so a missing price never reads as 0)."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else f


def _finite(x: float) -> bool:
    return bool(np.isfinite(x))
