from __future__ import annotations

from pydantic import BaseModel, field_validator

_MARKETS = {"h2h home", "h2h away", "over", "under"}


class BetCreate(BaseModel):
    game_pk: int
    score_date: str  # YYYY-MM-DD
    matchup: str | None = None
    market: str
    bookmaker: str | None = None
    american_odds: int
    stake: float
    total_line: float | None = None
    model_prob: float | None = None
    market_prob: float | None = None
    ev: float | None = None
    kelly_capped: float | None = None
    notes: str | None = None

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        if v not in _MARKETS:
            raise ValueError(f"market must be one of {sorted(_MARKETS)}")
        return v

    @field_validator("stake")
    @classmethod
    def validate_stake(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("stake must be > 0")
        return v


class BetUpdate(BaseModel):
    market: str | None = None
    bookmaker: str | None = None
    american_odds: int | None = None
    stake: float | None = None
    total_line: float | None = None
    model_prob: float | None = None
    market_prob: float | None = None
    ev: float | None = None
    notes: str | None = None
    outcome: str | None = None
    profit_loss: float | None = None

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str | None) -> str | None:
        if v is not None and v not in _MARKETS:
            raise ValueError(f"market must be one of {sorted(_MARKETS)}")
        return v

    @field_validator("outcome")
    @classmethod
    def validate_outcome(cls, v: str | None) -> str | None:
        if v is not None and v not in {"win", "loss", "push", "void"}:
            raise ValueError("outcome must be win, loss, push, or void")
        return v


class Bet(BetCreate):
    bet_id: str
    user_id: str
    placed_at: str
    outcome: str | None = None        # 'win' | 'loss' | 'push' | 'void' | None (pending)
    profit_loss: float | None = None


class BetsResponse(BaseModel):
    bets: list[Bet]
    total: int


class LoginSyncRequest(BaseModel):
    email: str | None = None
