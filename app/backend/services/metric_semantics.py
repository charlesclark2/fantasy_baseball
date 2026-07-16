"""E9.26 — the ONE canonical performance-metric semantics, shared by every surface.

Single source of truth for how the model's record / win-rate is defined so the
Performance page, EV Tracker, dashboard, the E9.40 scorecard and the "yesterday"
badge all mean the SAME thing by "correct". The E9.40 doubled-tally bug (a
moneyline + total-runs tally summed into a single ``Model 10/22``) is the failure
class this module exists to prevent: records are ALWAYS computed **per market**,
NEVER combined across markets.

Canonical definitions
---------------------
* **Model pick**   — the side the model's probability favors: ``model_prob >= 0.5``
  → home (h2h) / over (totals), else away / under. Deliberately off ``model_prob``
  (not the Layer-4 served ``pick_side``), so the call is defined even when the
  served pick abstains — the E9.40 convention.
* **Market pick**  — the side the de-vigged market probability favors
  (``bovada_devig_prob >= 0.5``): h2h = the closing favorite; totals = the
  ~50/50 over/under lean (near-neutral by construction).
* **Correct**      — the picked side matched the outcome. Push on an exact tie.
* **Record**       — ``wins / (wins + losses)``; **pushes are excluded** from the
  denominator. Reported per ``market_type`` only.
* **Small sample** — below :data:`SMALL_SAMPLE_N` decisive calls a rate is flagged
  ``low_sample`` so no surface shows a bare percentage off a handful of games.

Honest framing (``best_alpha = 0``): this module scores who *called* the outcome.
It makes no advantage / beat-the-line / return-over-market claim. ROI, where a
surface shows it, is realized settlement net of vig — a factual record, never a
market-advantage claim.

Pure and dependency-light: operates on already-graded ``GameScorecard`` objects
(built by ``scorecard.build_scorecard_from_detail`` from serving-cache blobs), so
the aggregation never touches Snowflake / the lakehouse / a mart (E11.20-safe).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

# Below this many decisive (win+loss, pushes excluded) calls, a rate is not
# trustworthy — surfaces flag it and suppress a bare percentage. Chosen to be
# conservative: a full ~15-game MLB slate settles ~15 calls per market, so a
# single day never clears the bar on its own.
SMALL_SAMPLE_N = 30


# ── the pick rule (identical for model and market) ───────────────────────────

def pick_side(market_type: str, prob: float | None) -> str | None:
    """The side a probability favors: ``>= 0.5`` → home/over, else away/under.

    The SAME rule grades the model (off ``model_prob``) and the market (off the
    de-vigged ``bovada_devig_prob``). Returns ``None`` when the probability is
    missing so an abstain / missing value never silently counts as a pick.
    """
    if prob is None:
        return None
    if market_type == "h2h":
        return "home" if prob >= 0.5 else "away"
    if market_type == "totals":
        return "over" if prob >= 0.5 else "under"
    return None


def oriented_prob(prob: float | None, side: str | None) -> float | None:
    """Probability oriented to the chosen side (confidence in the pick)."""
    if prob is None or side is None:
        return None
    return prob if side in ("home", "over") else 1.0 - prob


# ── grading a single call against the outcome ────────────────────────────────

def grade_h2h(side: str | None, home_score: int, away_score: int) -> str | None:
    if side is None:
        return None
    if home_score == away_score:  # MLB has no ties; guard defensively
        return "push"
    winner = "home" if home_score > away_score else "away"
    return "win" if side == winner else "loss"


def totals_landed(final_total: int, line: float | None) -> str | None:
    if line is None:
        return None
    if final_total == line:
        return "push"
    return "over" if final_total > line else "under"


def grade_totals(side: str | None, landed: str | None) -> str | None:
    if side is None or landed is None:
        return None
    if landed == "push":
        return "push"
    return "win" if side == landed else "loss"


# ── per-market aggregation (the canonical record) ────────────────────────────

def _blank_tally() -> dict[str, int]:
    return {"wins": 0, "losses": 0, "pushes": 0}


def _apply_result(tally: dict[str, int], result: str | None) -> None:
    if result == "win":
        tally["wins"] += 1
    elif result == "loss":
        tally["losses"] += 1
    elif result == "push":
        tally["pushes"] += 1
    # None (undefined pick / ungradable) contributes nothing.


def record_from_tally(tally: dict[str, int]) -> dict:
    """Finalize a {wins,losses,pushes} tally into the canonical record shape.

    ``decisive`` = wins + losses (the rate denominator; pushes excluded).
    ``win_rate`` is ``None`` when there are no decisive calls, and ``low_sample``
    is True whenever ``decisive < SMALL_SAMPLE_N`` so a surface can caveat it.
    """
    wins = tally["wins"]
    losses = tally["losses"]
    pushes = tally["pushes"]
    decisive = wins + losses
    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "decisive": decisive,
        "win_rate": (wins / decisive) if decisive > 0 else None,
        "low_sample": decisive < SMALL_SAMPLE_N,
    }


def aggregate_scorecard_records(scorecards: Iterable) -> dict[str, dict]:
    """Aggregate graded ``GameScorecard`` objects into per-market model & market records.

    Returns ``{market_type: {"n_games": int, "model": <record>, "market": <record>}}``.
    One call per (game, market); pushes excluded from the rate; markets never combined.
    This is the server-side twin of the frontend ``ScorecardResults`` tally — the two
    MUST agree, which the tests pin.
    """
    model_tallies: dict[str, dict[str, int]] = defaultdict(_blank_tally)
    market_tallies: dict[str, dict[str, int]] = defaultdict(_blank_tally)
    game_counts: dict[str, int] = defaultdict(int)

    for sc in scorecards:
        markets = getattr(sc, "markets", None) or []
        for m in markets:
            mt = getattr(m, "market_type", None)
            if not mt:
                continue
            game_counts[mt] += 1
            _apply_result(model_tallies[mt], getattr(m, "model_result", None))
            _apply_result(market_tallies[mt], getattr(m, "market_result", None))

    out: dict[str, dict] = {}
    for mt in sorted(model_tallies.keys() | market_tallies.keys(),
                     key=lambda k: 0 if k == "h2h" else 1):
        out[mt] = {
            "n_games": game_counts[mt],
            "model": record_from_tally(model_tallies[mt]),
            "market": record_from_tally(market_tallies[mt]),
        }
    return out
