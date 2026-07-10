"""Pydantic models for the E10.1 parlay decision-support calculator (honest MVP).

Request/response shapes for the stateless `/parlay` calc endpoints. The heavy lifting (combined
probability, correlation copula, EV, verdict) lives in `app.backend.services.parlay_calc`; these models
just type the HTTP surface. The calculator reads per-leg model probabilities from the SERVING CACHE
(DynamoDB → S3) only — never a direct mart / lakehouse query (E9.40 discipline).
"""

from __future__ import annotations

from pydantic import BaseModel


class ParlayLegInput(BaseModel):
    """One user-selected parlay leg. The backend re-resolves `hit_prob` from the serving cache — a
    client-supplied model probability is never trusted."""
    game_pk: int | None = None
    market_type: str  # 'h2h' | 'totals' | 'strikeouts'
    side: str         # 'home' | 'away' | 'over' | 'under'
    book_odds_american: float | None = None
    pitcher_id: int | None = None  # strikeouts legs
    line: float | None = None      # totals / strikeouts posted line (display + K resolve)
    label: str | None = None


class ParlayEvaluateRequest(BaseModel):
    legs: list[ParlayLegInput]
    parlay_odds_american: float | None = None
    date: str | None = None  # YYYY-MM-DD slate the legs belong to (defaults to ET today)
