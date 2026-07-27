"""totals_serving.py — Edge Program Story E2.7 (Distribution UX, serving layer).

WHAT THIS IS
------------
The DAILY-batch helper that turns the served per-side means (`totals_perside_mu_v1`, home/away)
plus the E2.3 held-out dispersion params (`totals_distribution_v1.json`) into the compact,
JSON-serialisable distribution payload the totals pick-detail page renders (E2.7). It is the
serving-side sibling of `totals_distribution.py` (the calibration machinery) and reuses the SAME
convolution — the app CONSUMES this payload, it never recomputes a distribution at request time.

§6 COST GUARD (non-negotiable): we draw at most `n_draws` (≤ 10k) samples PER GAME here, in the
daily batch, and persist **PARAMS + the P05…P95 QUANTILE GRID + p_over ladders ONLY** — never the
raw samples. The payload is a few hundred floats per game.

HONEST FRAMING (best_alpha=0, program-wide): this is a CALIBRATED DISTRIBUTION for transparency,
NOT an edge claim. E2.6's derivative gate closed as a CONFIRMED CLEAN NULL (0 FDR survivors across
team_totals + alt_totals, placebo-indistinguishable), so NO derivative is surfaced as "+EV" /
"value" / a win-rate — every line is context ("our calibrated view of this total"). This module
computes only descriptive quantities (a distribution + P(over) at lines); it emits no bet rec.

Pure NumPy/SciPy — no Snowflake, no request-path IO — so it is fully unit-tested.
"""

from __future__ import annotations

import numpy as np

from betting_ml.utils.totals_distribution import (
    TotalsDistributionParams,
    derive_distributions,
    draw_independent_samples,
)

# Half-line offsets for the alternate-GAME-total ladder, relative to the market total line.
_ALT_TOTAL_OFFSETS: tuple[float, ...] = (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0)
# Half-line offsets for each TEAM-total ladder, relative to that team's line.
_TEAM_TOTAL_OFFSETS: tuple[float, ...] = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5)
# Serving draw cap (§6). Default a touch below the fit-time 10k — plenty for stored quantiles.
DEFAULT_SERVE_DRAWS = 10_000


def _nearest_half(x: float) -> float:
    """Round to the nearest 0.5 — the natural home for a team-total line centred on its mean."""
    return round(float(x) * 2.0) / 2.0


def _quantile_dict(samples_1d: np.ndarray, levels: tuple[float, ...]) -> dict[str, float]:
    """P05…P95 grid of a single game's 1-D sample array → {"p05": .., "p10": .., ...} (rounded)."""
    qs = np.quantile(samples_1d, np.asarray(levels))
    return {f"p{int(round(lvl * 100)):02d}": round(float(q), 2) for lvl, q in zip(levels, qs)}


def _pmf(samples_1d: np.ndarray, *, tail: tuple[float, float] = (0.005, 0.995)) -> list[dict]:
    """Probability mass function of a DISCRETE (integer-valued) predictive: [{"x": k, "p": P(==k)}…].

    A game total / run margin is an integer count, so the honest distribution is a PMF over integers,
    not a smoothed continuous density. Reconstructing a density from the quantile grid via Δp/Δx
    oscillates on the integer lattice (a sawtooth) — the PMF is the exact, smooth bell instead. Support
    is trimmed to the [0.5%, 99.5%] range so the payload stays compact (~20-25 points) and drops the
    negligible tails. Counts, not raw samples, so the §6 cost guard holds."""
    lo = int(np.floor(np.quantile(samples_1d, tail[0])))
    hi = int(np.ceil(np.quantile(samples_1d, tail[1])))
    xs = np.arange(lo, hi + 1)
    counts = np.array([(samples_1d == k).mean() for k in xs], dtype=float)
    return [{"x": int(k), "p": round(float(p), 4)} for k, p in zip(xs, counts)]


def _ladder(samples_1d: np.ndarray, lines: list[float]) -> list[dict[str, float]]:
    """[{"line": L, "p_over": P(sample > L)} …] for a single game's sample array."""
    return [
        {"line": round(float(L), 1), "p_over": round(float((samples_1d > L).mean()), 4)}
        for L in lines
    ]


def build_totals_distribution_payload(
    mu_home: float,
    mu_away: float,
    params: TotalsDistributionParams,
    *,
    market_total_line: float | None = None,
    home_team_line: float | None = None,
    away_team_line: float | None = None,
    rng: np.random.Generator | None = None,
    n_draws: int | None = None,
) -> dict:
    """Build the E2.7 per-game distribution payload from the served per-side means + E2.3 params.

    Convolves the two per-side NegBin marginals INDEPENDENTLY (E2.2 ρ≈0) using the E2.3 held-out
    dispersions (`params.r_home`/`params.r_away` — NOT the artifact train-fit r), then reads off:

      * total     — μ, the P05…P95 quantile grid, the market line, P(over) at that line, and the
                    80% predictive interval [Q10, Q90].
      * run_diff  — the home-minus-away margin grid + P(home > away) (the distributional H2H view).
      * team_totals — each side's line (the book's, else the nearest-half of its mean) with P(over)
                    and a small ladder of P(over) at neighbouring lines.
      * alt_totals — a ladder of P(over) at lines stepped around the market total (the alt-line grid).

    `market_total_line` is the book's game total (drawn on the chart, shaded to the favourable side);
    when absent we anchor the alt ladder on the nearest-half of μ_total. All quantities are
    DESCRIPTIVE (a calibrated distribution) — no EV / value / win-rate is produced (best_alpha=0).
    """
    if rng is None:
        rng = np.random.default_rng(0)  # deterministic per-game (no request-time randomness leak)
    n = int(n_draws if n_draws is not None else min(params.n_draws, DEFAULT_SERVE_DRAWS))

    mu_h = max(float(mu_home), 0.0)
    mu_a = max(float(mu_away), 0.0)
    y_home, y_away = draw_independent_samples(
        np.array([mu_h]), np.array([mu_a]), params.r_home, rng,
        r_away=params.r_away, n_draws=n,
    )
    dist = derive_distributions(y_home, y_away)
    total = dist["total"][0]
    run_diff = dist["run_diff"][0]
    home_total = dist["home_total"][0]
    away_total = dist["away_total"][0]

    levels = tuple(params.quantile_levels)
    mu_total = round(mu_h + mu_a, 3)

    # ── total ────────────────────────────────────────────────────────────────────────────────────
    ci80 = [round(float(np.quantile(total, 0.10)), 2), round(float(np.quantile(total, 0.90)), 2)]
    total_block: dict = {
        "mu": mu_total,
        "quantiles": _quantile_dict(total, levels),
        "pmf": _pmf(total),          # P(total == k) over the integer support — the render shape
        "ci80": ci80,
    }
    if market_total_line is not None:
        ml = round(float(market_total_line), 1)
        total_block["market_line"] = ml
        total_block["p_over"] = round(float((total > ml).mean()), 4)
    else:
        total_block["market_line"] = None
        total_block["p_over"] = None

    # ── run_diff (distributional H2H: >0 ⇔ home) ───────────────────────────────────────────────────
    run_diff_block = {
        "mu": round(mu_h - mu_a, 3),
        "quantiles": _quantile_dict(run_diff, levels),
        "pmf": _pmf(run_diff),       # P(home − away == k); >0 ⇔ home wins on the scoreboard
        "p_home": round(float((run_diff > 0.0).mean()), 4),
    }

    # ── team totals (line = book's if known, else nearest-half of the mean) ─────────────────────────
    def _team_block(samples_1d: np.ndarray, mean: float, line: float | None) -> dict:
        L = round(float(line), 1) if line is not None else _nearest_half(mean)
        ladder_lines = [round(L + off, 1) for off in _TEAM_TOTAL_OFFSETS]
        return {
            "line": L,
            "p_over": round(float((samples_1d > L).mean()), 4),
            "mu": round(float(mean), 3),
            "ladder": _ladder(samples_1d, ladder_lines),
        }

    team_totals = {
        "home": _team_block(home_total, mu_h, home_team_line),
        "away": _team_block(away_total, mu_a, away_team_line),
    }

    # ── alternate game totals (ladder around the market line, else nearest-half of μ_total) ─────────
    anchor = round(float(market_total_line), 1) if market_total_line is not None else _nearest_half(mu_total)
    alt_lines = [round(anchor + off, 1) for off in _ALT_TOTAL_OFFSETS]
    alt_totals = _ladder(total, alt_lines)

    return {
        "version": params.version,
        "total": total_block,
        "run_diff": run_diff_block,
        "team_totals": team_totals,
        "alt_totals": alt_totals,
    }
