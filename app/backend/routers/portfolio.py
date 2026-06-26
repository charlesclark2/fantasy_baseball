"""Portfolio preferences endpoints.

GET /portfolio/preferences  — fetch the authenticated user's portfolio settings
PUT /portfolio/preferences  — update the authenticated user's portfolio settings

Portfolio preferences drive server-side pick filtering on GET /picks/today?apply_portfolio=true.
Settings live in DynamoDB as a `portfolio` map on the users table (INC-16-P2;
migrated off the decommissioned Railway PostgreSQL user_portfolios table).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.backend.dependencies import get_user_id
from app.backend.services import dynamo

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class PortfolioPreferences(BaseModel):
    min_ev_threshold: float = Field(default=0.02, ge=0.0, le=1.0)
    markets: list[str] = Field(default=["h2h", "totals"])
    bankroll: Optional[float] = Field(default=None, ge=0.0)
    max_kelly_fraction: float = Field(default=0.05, ge=0.001, le=0.5)

    @field_validator("markets")
    @classmethod
    def _valid_markets(cls, v: list[str]) -> list[str]:
        allowed = {"h2h", "totals"}
        bad = [m for m in v if m not in allowed]
        if bad:
            raise ValueError(f"Unknown markets: {bad}. Allowed: {sorted(allowed)}")
        if not v:
            raise ValueError("markets must contain at least one entry")
        return v


class PortfolioPreferencesResponse(PortfolioPreferences):
    user_id: str


@router.get("/preferences", response_model=PortfolioPreferencesResponse)
def get_portfolio_preferences(user_id: str = Depends(get_user_id)) -> PortfolioPreferencesResponse:
    """Returns the authenticated user's portfolio preferences (defaults if not yet set)."""
    prefs = dynamo.get_user_portfolio(user_id)
    markets = prefs.get("markets") or ["h2h", "totals"]
    if isinstance(markets, str):
        import json
        markets = json.loads(markets)
    return PortfolioPreferencesResponse(
        user_id=user_id,
        min_ev_threshold=prefs.get("min_ev_threshold") or 0.02,
        markets=markets,
        bankroll=prefs.get("bankroll"),
        max_kelly_fraction=prefs.get("max_kelly_fraction") or 0.05,
    )


@router.put("/preferences", response_model=PortfolioPreferencesResponse)
def update_portfolio_preferences(
    prefs: PortfolioPreferences,
    user_id: str = Depends(get_user_id),
) -> PortfolioPreferencesResponse:
    """Saves the authenticated user's portfolio preferences."""
    saved = dynamo.upsert_user_portfolio(user_id, prefs.model_dump())
    markets = saved.get("markets") or prefs.markets
    if isinstance(markets, str):
        import json
        markets = json.loads(markets)
    return PortfolioPreferencesResponse(
        user_id=user_id,
        min_ev_threshold=saved.get("min_ev_threshold") or prefs.min_ev_threshold,
        markets=markets,
        bankroll=saved.get("bankroll"),
        max_kelly_fraction=saved.get("max_kelly_fraction") or prefs.max_kelly_fraction,
    )
