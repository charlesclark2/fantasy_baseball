"""k_projection_serving.py — Edge Program Story E5.5 (K-PROJECTION transparency serving payload).

REFRAME (post-E5.4): the pitcher-strikeout PROP EDGE is NULL, but the E5.2 K predictive distribution
is genuinely well-calibrated (calib_80 ≈ 0.81) → real PRODUCT value as a *projection*. E5.5 ships that
projection on the pitcher player page as an honest PROJECTION + a transparent model-vs-market
COMPARISON. This module is the pure machinery that assembles the user-facing serving payload (the
distribution grid + the book's posted strikeout line(s) + a neutral model-vs-book delta).

🔒 HONEST FRAMING (non-negotiable — the crux of E5.5): this is a PROJECTION + a transparency
comparison, NEVER a "+EV" / "value" / "bet this" recommendation. E5.4 PROVED there is no cashable
edge here (best_alpha = 0), so any profitability / win-rate framing would be dishonest and a trust
violation. This module therefore DELIBERATELY emits NO edge / EV / win-rate field and bakes the
disclaimer into every payload. The numeric `model_vs_book_p_over` delta is a transparency comparison
("we project P(over) = 0.61; the book's no-vig line implies 0.52") — it is NOT an edge claim.

Reuses the E5.3 `prop_edge` math (`devig_two_way`, `line_probabilities`) so the de-vig and the
half-vs-integer-line push convention match everywhere in the program. Pure NumPy — no model, no
Snowflake, no network — so it is fully unit-tested.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from betting_ml.utils.prop_edge import devig_two_way, line_probabilities

# ---------------------------------------------------------------------------
# Honest-framing constants — baked into every payload, asserted by the guard test.
# These are the ONLY user-facing prose this surface ships. The forbidden-language guard
# (test_k_projection_serving.py) fails the build if any "+EV"/"edge"/"value play"/win-rate
# wording ever creeps in here or into the frontend component.
# ---------------------------------------------------------------------------

MODEL_VERSION = "strikeout_glm_v1"

CAPTION = (
    "Our model's strikeout projection for this start, shown next to the sportsbooks' "
    "posted strikeout line. A projection and transparency comparison only."
)

DISCLAIMER = (
    "Projections reflect our model; they are not betting advice and we make no profitability "
    "claim. Single-game strikeout totals are high-variance — treat this as informational "
    "context, not a play."
)


# ---------------------------------------------------------------------------
# Distribution summary
# ---------------------------------------------------------------------------

def summarize_distribution(
    quantile_levels: Sequence[float],
    k_quantile_grid: Sequence[float],
    mean: float | None,
    std: float | None,
) -> dict[str, Any]:
    """Package the calibrated K predictive distribution for the player-page chart.

    Stores the quantile grid (the served representation — never the raw samples) plus the mean, the
    median (the grid value at the 0.50 level when present), and the std. All values are plain floats /
    ints (JSON-safe). The grid is rounded to integer K counts (the surface plots counts)."""
    levels = [round(float(q), 4) for q in quantile_levels]
    grid = [int(round(float(x))) for x in k_quantile_grid]
    median: float | None = None
    for q, g in zip(levels, grid):
        if abs(q - 0.50) < 1e-6:
            median = float(g)
            break
    return {
        "quantile_levels": levels,
        "k_quantile_grid": grid,
        "mean": round(float(mean), 2) if mean is not None and np.isfinite(mean) else None,
        "median": median,
        "std": round(float(std), 2) if std is not None and np.isfinite(std) else None,
        "p05": grid[0] if grid else None,
        "p95": grid[-1] if grid else None,
    }


# ---------------------------------------------------------------------------
# Per-book model-vs-market COMPARISON row (NO edge / EV — honest framing)
# ---------------------------------------------------------------------------

def book_comparison_row(
    book: str,
    line: float,
    over_american: float | None,
    under_american: float | None,
    model_p_over: float,
    model_p_under: float,
    model_p_push: float,
    model_mean: float | None,
) -> dict[str, Any]:
    """One transparent model-vs-book comparison row for the posted strikeout line.

    Emits ONLY transparency quantities — the posted line, the book's two-way price, the book's
    DE-VIGGED (no-vig, push-excluded) implied P(over), the model's P(over) at the same line, and two
    neutral deltas: `model_vs_book_p_over` (model P(over) − book no-vig P(over)) and
    `model_mean_minus_line` (our projected mean K − the posted line). NO edge / EV / win-rate field is
    emitted — E5.4 proved no cashable edge, so this is a comparison, not a recommendation."""
    dv = devig_two_way(over_american, under_american)
    book_implied = dv["devig_over"] if dv["valid"] else float("nan")
    delta = (model_p_over - book_implied) if np.isfinite(book_implied) else float("nan")
    return {
        "book": book,
        "line": float(line),
        "is_integer_line": bool(float(line) == np.floor(float(line))),
        "over_odds": _int_or_none(over_american),
        "under_odds": _int_or_none(under_american),
        "book_implied_p_over": _round_or_none(book_implied),
        "book_hold": _round_or_none(dv["hold"]),
        "model_p_over": _round_or_none(model_p_over),
        "model_p_under": _round_or_none(model_p_under),
        "model_p_push": _round_or_none(model_p_push),
        # Transparency deltas — NOT edge/EV. Positive = our model is higher than the book's line.
        "model_vs_book_p_over": _round_or_none(delta),
        "model_mean_minus_line": (round(float(model_mean) - float(line), 2)
                                  if model_mean is not None and np.isfinite(model_mean) else None),
    }


def comparison_from_samples(
    samples: np.ndarray,
    book_lines: Sequence[dict[str, Any]],
    model_mean: float | None,
) -> list[dict[str, Any]]:
    """Build the per-book comparison rows directly from the served K-count samples.

    `book_lines` is a list of `{book, line, over_odds, under_odds}` (the live K-prop feed for this
    pitcher×date). For each, computes the model probabilities at the exact line (half-vs-integer push
    aware, via `prop_edge.line_probabilities`) and the transparent de-vigged book comparison. Convenience
    wrapper so the writer never re-implements the sample→prob step."""
    rows: list[dict[str, Any]] = []
    for bl in book_lines:
        line = float(bl["line"])
        mp = line_probabilities(samples, line)
        rows.append(book_comparison_row(
            book=str(bl.get("book", "")), line=line,
            over_american=bl.get("over_odds"), under_american=bl.get("under_odds"),
            model_p_over=mp["p_over"], model_p_under=mp["p_under"], model_p_push=mp["p_push"],
            model_mean=model_mean,
        ))
    return rows


# ---------------------------------------------------------------------------
# Full serving payload
# ---------------------------------------------------------------------------

def build_k_projection_payload(
    *,
    pitcher_id: int,
    full_name: str | None,
    team: str | None,
    game_pk: int | None,
    game_date: str | None,
    opponent: str | None,
    quantile_levels: Sequence[float],
    k_quantile_grid: Sequence[float],
    mean: float | None,
    std: float | None,
    calib_80: float | None,
    book_comparisons: Sequence[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the full pitcher-page K-projection serving payload.

    Bundles the distribution summary + the per-book comparison rows + the honest-framing caption and
    disclaimer. `primary_line` is the most common posted line across books (the headline the surface
    leads with). `best_alpha = 0` and `is_bet_recommendation = False` are stamped into the payload so
    the no-edge posture travels WITH the data (the frontend asserts these before rendering)."""
    dist = summarize_distribution(quantile_levels, k_quantile_grid, mean, std)
    comparisons = list(book_comparisons)
    return {
        "pitcher_id": int(pitcher_id),
        "full_name": full_name,
        "team": team,
        "game_pk": int(game_pk) if game_pk is not None else None,
        "game_date": game_date,
        "opponent": opponent,
        "model_version": MODEL_VERSION,
        "calib_80": round(float(calib_80), 3) if calib_80 is not None and np.isfinite(calib_80) else None,
        "distribution": dist,
        "book_comparisons": comparisons,
        "primary_line": _primary_line(comparisons),
        "caption": CAPTION,
        "disclaimer": DISCLAIMER,
        # The no-edge posture travels with the data (honest framing — see module docstring).
        "best_alpha": 0,
        "is_bet_recommendation": False,
        "generated_at": generated_at,
    }


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _primary_line(comparisons: Sequence[dict[str, Any]]) -> float | None:
    """The most-common posted line across books (ties → the lowest line). None if no books."""
    lines = [c["line"] for c in comparisons if c.get("line") is not None]
    if not lines:
        return None
    counts: dict[float, int] = {}
    for ln in lines:
        counts[ln] = counts.get(ln, 0) + 1
    best = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return float(best[0])


def _int_or_none(x: Any) -> int | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return int(round(f)) if np.isfinite(f) else None


def _round_or_none(x: Any, ndigits: int = 4) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, ndigits) if np.isfinite(f) else None
