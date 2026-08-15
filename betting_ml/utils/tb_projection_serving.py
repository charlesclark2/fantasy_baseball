"""tb_projection_serving.py — Edge Program Story E5.9 (batter TOTAL-BASES projection payload).

E5.9 ships the MLB Batter Props Phase-2 total_bases SHIP_CANDIDATE (`batter_tb_glm_nb_v1` —
Poisson-GLM mean + fitted NB2 dispersion) as a calibration/transparency surface on the /props
page: the per-batter-game TB distribution (P(TB ≥ k), quantile grid) beside the sportsbooks'
posted total-bases line. The batter-side analog of E5.5's pitcher K projection; this module is
the pure payload machinery (mirrors `k_projection_serving`).

🔒 HONEST FRAMING (non-negotiable — the E5.9 boundary, best_alpha = 0):
  * This is a PROJECTION + transparency comparison, NEVER a "+EV" / "value" / "bet this"
    recommendation. No edge / EV / win-rate field is emitted anywhere.
  * The strongest allowed claim is CALIBRATION: in the registered Phase-2 evaluation the
    market-blind model priced better-calibrated than the de-vigged closing consensus on Brier
    in 6/6 half-season folds. That is a per-row calibration statement — NOT "the market is
    systematically off" (the NF-D15 level-only foil was refuted; the per-fold market bias
    flips sign) and NOT a claim any price can be beaten.
  * Market-blind: book prices are never model inputs; the posted line is a reference only.
  * REGULAR SEASON ONLY: the model is fit on regular-season games (the substrate's upstream
    boundary); a postseason game is an extrapolation and is not served.

pmf conventions (mirrors the Phase-2 harness `batter_props_phase2_bakeoff`): the predictive is
an exact pmf on integer support 0..K (K = 24, the registered TB grid cap) with the tail mass
folded into the cap bin. All probabilities here are computed from that pmf's CDF — exact, no
Monte-Carlo. Integer book lines get an EXPLICIT three-way push convention (the Phase-2 research
grading excluded integer lines, ~1.5% of rows; serving must price them):
  * half-line   L.5 : P(over) = 1 − F(⌊L⌋);  P(under) = F(⌊L⌋);  P(push) = 0.
  * integer line L  : P(over) = 1 − F(L);  P(push) = p(L);  P(under) = F(L−1).

Pure NumPy — no model, no network — fully unit-tested (test_tb_projection_serving.py).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from betting_ml.utils.prop_edge import devig_two_way

# ---------------------------------------------------------------------------
# Honest-framing constants — baked into every payload, asserted by the guard test.
# The forbidden-language guard (test_tb_projection_serving.py) fails the build if any
# "+EV"/"edge"/"value play"/win-rate wording creeps in here or into the frontend surface.
# ---------------------------------------------------------------------------

MODEL_VERSION = "batter_tb_glm_nb_v1"

# The registered TB support cap (Phase-2 harness GRID_CAP["batter_total_bases"]).
GRID_CAP_TB = 24

CAPTION = (
    "Our model's total-bases projection for this batter's game, shown next to the "
    "sportsbooks' posted total-bases line. A projection and transparency comparison only."
)

DISCLAIMER = (
    "Projections reflect our model; they are not betting advice and we make no profitability "
    "claim. Single-game total-bases outcomes are high-variance — treat this as informational "
    "context, not a play. The model is fit on regular-season games only."
)

# The strongest allowed claim (per-row calibration; see module docstring). Shown as the
# surface's methodology note.
CALIBRATION_NOTE = (
    "In historical evaluation (2023–2026), this model's probabilities were better-calibrated "
    "against realized outcomes than the sportsbooks' de-vigged consensus closing price in "
    "every evaluated half-season. That is a statement about probability calibration, not "
    "betting advice."
)

# P(TB ≥ k) thresholds the surface displays as chips.
P_GE_THRESHOLDS = (1, 2, 3, 4)


# ---------------------------------------------------------------------------
# pmf helpers — exact reads off the discrete predictive (support 0..K, rows sum to 1)
# ---------------------------------------------------------------------------

def _as_pmf(pmf: Sequence[float]) -> np.ndarray:
    p = np.asarray(pmf, float).ravel()
    if p.ndim != 1 or p.size < 2:
        raise ValueError("pmf must be a 1-D array over integer support 0..K")
    if not np.isclose(p.sum(), 1.0, atol=1e-6):
        raise ValueError("pmf must sum to 1 — a non-normalized predictive is refused, "
                         "never silently renormalized (NF-W3)")
    return p


def pmf_mean_std(pmf: Sequence[float]) -> tuple[float, float]:
    p = _as_pmf(pmf)
    ks = np.arange(p.size, dtype=float)
    mean = float(np.sum(ks * p))
    var = float(np.sum((ks - mean) ** 2 * p))
    return mean, float(np.sqrt(max(var, 0.0)))


def pmf_quantile_grid(pmf: Sequence[float], levels: Sequence[float]) -> list[int]:
    """Smallest k with F(k) ≥ q, per level — the integer quantile grid the surface plots."""
    p = _as_pmf(pmf)
    cdf = np.cumsum(p)
    out = []
    for q in levels:
        out.append(int(np.argmax(cdf >= float(q) - 1e-12)))
    return out


def pmf_p_ge(pmf: Sequence[float], k: int) -> float:
    """P(y ≥ k) = 1 − F(k−1). k=0 → 1.0 by construction."""
    p = _as_pmf(pmf)
    if k <= 0:
        return 1.0
    if k >= p.size:
        return 0.0
    cdf = np.cumsum(p)
    return float(np.clip(1.0 - cdf[k - 1], 0.0, 1.0))


def pmf_line_probabilities(pmf: Sequence[float], line: float) -> dict[str, float]:
    """Model P(over)/P(under)/P(push) at a book's TB line, exact off the pmf CDF.

    EXPLICIT half-vs-integer push convention (the E5.9 AC — the Phase-2 research grading
    excluded integer lines; serving prices them three-way):
      * half-line (e.g. 1.5): over = P(y ≥ 2) = 1 − F(1); under = F(1); push = 0.
      * integer line (e.g. 2): over = P(y > 2) = 1 − F(2); push = p(2); under = F(1).
    Probabilities sum to 1. Lines at/above the grid cap clamp to the cap bin (the tail mass
    is folded there by the pmf builders, so the clamp is exact for the capped support).
    """
    p = _as_pmf(pmf)
    K = p.size - 1
    cdf = np.cumsum(p)
    ln = float(line)
    if ln < 0:
        return {"p_over": 1.0, "p_under": 0.0, "p_push": 0.0}
    is_integer = bool(ln == np.floor(ln))
    if not is_integer:
        k = int(min(np.floor(ln), K))
        p_over = float(np.clip(1.0 - cdf[k], 0.0, 1.0))
        return {"p_over": p_over, "p_under": float(np.clip(cdf[k], 0.0, 1.0)), "p_push": 0.0}
    L = int(min(ln, K))
    p_push = float(p[L])
    p_over = float(np.clip(1.0 - cdf[L], 0.0, 1.0))
    p_under = float(np.clip(cdf[L - 1], 0.0, 1.0)) if L > 0 else 0.0
    return {"p_over": p_over, "p_under": p_under, "p_push": p_push}


# ---------------------------------------------------------------------------
# Distribution summary
# ---------------------------------------------------------------------------

def summarize_distribution(
    quantile_levels: Sequence[float],
    pmf: Sequence[float],
) -> dict[str, Any]:
    """Package the TB predictive for the surface: quantile grid + moments + P(TB ≥ k) chips."""
    levels = [round(float(q), 4) for q in quantile_levels]
    grid = pmf_quantile_grid(pmf, levels)
    mean, std = pmf_mean_std(pmf)
    median: float | None = None
    for q, g in zip(levels, grid):
        if abs(q - 0.50) < 1e-6:
            median = float(g)
            break
    return {
        "quantile_levels": levels,
        "tb_quantile_grid": grid,
        "mean": round(mean, 2),
        "median": median,
        "std": round(std, 2),
        "p05": grid[0] if grid else None,
        "p95": grid[-1] if grid else None,
        "p_ge": {str(k): round(pmf_p_ge(pmf, k), 4) for k in P_GE_THRESHOLDS},
    }


# ---------------------------------------------------------------------------
# Per-book model-vs-market COMPARISON row (NO edge / EV — honest framing)
# ---------------------------------------------------------------------------

def book_comparison_row(
    book: str,
    line: float,
    over_american: float | None,
    under_american: float | None,
    pmf: Sequence[float],
    model_mean: float | None,
) -> dict[str, Any]:
    """One transparent model-vs-book row for a posted TB line. NO edge/EV field (E5.9 crux)."""
    mp = pmf_line_probabilities(pmf, line)
    dv = devig_two_way(over_american, under_american)
    book_implied = dv["devig_over"] if dv["valid"] else float("nan")
    delta = (mp["p_over"] - book_implied) if np.isfinite(book_implied) else float("nan")
    return {
        "book": book,
        "line": float(line),
        "is_integer_line": bool(float(line) == np.floor(float(line))),
        "over_odds": _int_or_none(over_american),
        "under_odds": _int_or_none(under_american),
        "book_implied_p_over": _round_or_none(book_implied),
        "book_hold": _round_or_none(dv["hold"]),
        "model_p_over": _round_or_none(mp["p_over"]),
        "model_p_under": _round_or_none(mp["p_under"]),
        "model_p_push": _round_or_none(mp["p_push"]),
        # Transparency deltas — NOT edge/EV. Positive = our model is higher than the book's price.
        "model_vs_book_p_over": _round_or_none(delta),
        "model_mean_minus_line": (round(float(model_mean) - float(line), 2)
                                  if model_mean is not None and np.isfinite(model_mean) else None),
    }


def comparisons_from_pmf(
    pmf: Sequence[float],
    book_lines: Sequence[dict[str, Any]],
    model_mean: float | None,
) -> list[dict[str, Any]]:
    """Per-book comparison rows straight from the pmf; `book_lines` items carry
    {book, line, over_odds, under_odds} (the live TB props feed for this batter×date)."""
    rows: list[dict[str, Any]] = []
    for bl in book_lines:
        rows.append(book_comparison_row(
            book=str(bl.get("book", "")), line=float(bl["line"]),
            over_american=bl.get("over_odds"), under_american=bl.get("under_odds"),
            pmf=pmf, model_mean=model_mean,
        ))
    return rows


# ---------------------------------------------------------------------------
# Full serving payload
# ---------------------------------------------------------------------------

def build_tb_projection_payload(
    *,
    batter_id: int,
    full_name: str | None,
    team: str | None,
    opponent: str | None,
    game_pk: int | None,
    game_date: str | None,
    quantile_levels: Sequence[float],
    pmf: Sequence[float],
    book_comparisons: Sequence[dict[str, Any]],
    batting_slot: int | None = None,
    game_datetime: str | None = None,
    last3_tb: Sequence[int] | None = None,
    model_fit_date: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the batter TB-projection serving payload.

    The model version + fit date are STAMPED into every payload (PROD-STATE-1 Class A — the
    K-projections registry gap is not repeated). best_alpha=0 / is_bet_recommendation=False /
    regular_season_only=True travel WITH the data so the posture reaches every consumer."""
    dist = summarize_distribution(quantile_levels, pmf)
    mean, _ = pmf_mean_std(pmf)
    comparisons = list(book_comparisons)
    return {
        "batter_id": int(batter_id),
        "full_name": full_name,
        "team": team,
        "opponent": opponent,
        "game_pk": int(game_pk) if game_pk is not None else None,
        "game_date": game_date,
        "game_datetime": game_datetime,
        "batting_slot": int(batting_slot) if batting_slot is not None else None,
        "last3_tb": [int(t) for t in last3_tb] if last3_tb else None,
        "model_version": MODEL_VERSION,
        "model_fit_date": model_fit_date,
        "distribution": dist,
        "book_comparisons": comparisons,
        "primary_line": _primary_line(comparisons),
        "caption": CAPTION,
        "disclaimer": DISCLAIMER,
        "calibration_note": CALIBRATION_NOTE,
        # The no-edge posture travels with the data (honest framing — module docstring).
        "best_alpha": 0,
        "is_bet_recommendation": False,
        "regular_season_only": True,
        "generated_at": generated_at,
    }


# ---------------------------------------------------------------------------
# Daily index — one compact row per batter for the /props list page
# ---------------------------------------------------------------------------

def index_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Compact card summary of a full TB payload (the list endpoint ships one small blob)."""
    dist = payload.get("distribution", {}) or {}
    levels = dist.get("quantile_levels", []) or []
    grid = dist.get("tb_quantile_grid", []) or []

    def _at(level: float) -> float | None:
        for q, g in zip(levels, grid):
            if abs(float(q) - level) < 1e-6:
                return float(g)
        return None

    primary = payload.get("primary_line")
    at_primary = None
    if primary is not None:
        for c in payload.get("book_comparisons", []) or []:
            if c.get("line") == primary:
                at_primary = c
                break
    return {
        "batter_id": payload.get("batter_id"),
        "full_name": payload.get("full_name"),
        "team": payload.get("team"),
        "opponent": payload.get("opponent"),
        "game_pk": payload.get("game_pk"),
        "game_date": payload.get("game_date"),
        "game_datetime": payload.get("game_datetime"),
        "batting_slot": payload.get("batting_slot"),
        "last3_tb": payload.get("last3_tb"),
        "mean": dist.get("mean"),
        "median": dist.get("median"),
        "p10": _at(0.10),
        "p90": _at(0.90),
        "p05": dist.get("p05"),
        "p95": dist.get("p95"),
        "p_ge_2": (dist.get("p_ge") or {}).get("2"),
        "primary_line": primary,
        "book_count": len(payload.get("book_comparisons", []) or []),
        "model_p_over": (at_primary or {}).get("model_p_over"),
        "model_vs_book_p_over": (at_primary or {}).get("model_vs_book_p_over"),
        "model_mean_minus_line": (at_primary or {}).get("model_mean_minus_line"),
    }


def build_index_payload(rows: Sequence[dict[str, Any]], game_date: str | None,
                        generated_at: str | None = None,
                        model_fit_date: str | None = None) -> dict[str, Any]:
    """The daily TB list blob. Rows sort by projected mean desc; the honest-framing posture
    travels with the list (best_alpha=0, is_bet_recommendation=False, regular_season_only)."""
    ordered = sorted(rows, key=lambda r: (r.get("mean") is not None, r.get("mean") or 0.0),
                     reverse=True)
    return {
        "game_date": game_date,
        "count": len(ordered),
        "batters": ordered,
        "model_version": MODEL_VERSION,
        "model_fit_date": model_fit_date,
        "caption": CAPTION,
        "disclaimer": DISCLAIMER,
        "calibration_note": CALIBRATION_NOTE,
        "best_alpha": 0,
        "is_bet_recommendation": False,
        "regular_season_only": True,
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
