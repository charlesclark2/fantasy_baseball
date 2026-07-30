from __future__ import annotations

from pydantic import BaseModel, field_validator, model_validator

# Game markets (h2h/totals) settle against the final score. The strikeouts prop
# markets (E9.42) settle against the starter's actual K total — see settle_user_bets.py.
_GAME_MARKETS = {"h2h home", "h2h away", "over", "under"}
_PROP_MARKETS = {"strikeouts over", "strikeouts under"}
_MARKETS = _GAME_MARKETS | _PROP_MARKETS


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
    # Player-prop fields (E9.42). Only set for _PROP_MARKETS bets logged from /props.
    # prop_line is the posted strikeout line the wager is against; projection is OUR
    # model's projected mean K at log time (bookkeeping context, never an edge claim).
    player_id: int | None = None
    player_name: str | None = None
    prop_line: float | None = None
    projection: float | None = None

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

    @model_validator(mode="after")
    def validate_settleable(self) -> "BetCreate":
        """A bet must carry everything settlement needs to GRADE it — or it can never close.

        E9.49: the audit found a totals bet logged with NO total_line back on 2026-07-02.
        settle_user_bets._outcome returns None without a line, so that bet showed "Pending"
        in the Bet Log for 27 days and would have done so forever — an unsettleable bet is
        indistinguishable from an unfinished one. The grading inputs are therefore REQUIRED
        at write time, per market, rather than left optional and discovered at settle time.
        """
        if self.market in ("over", "under") and self.total_line is None:
            raise ValueError("total_line is required for over/under bets (needed to settle)")
        if self.market in _PROP_MARKETS:
            if self.prop_line is None:
                raise ValueError("prop_line is required for strikeout prop bets (needed to settle)")
            if self.player_id is None:
                raise ValueError("player_id is required for strikeout prop bets (needed to settle)")
        return self


class BetUpdate(BaseModel):
    market: str | None = None
    bookmaker: str | None = None
    american_odds: int | None = None
    stake: float | None = None
    total_line: float | None = None
    prop_line: float | None = None
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
    # E9.49. ⚠️ A field the STORE carries but the response model does not declare is dropped
    # SILENTLY on serialize (the E9.41 class) — so these must stay declared here, not only
    # written by settle_user_bets.py / dynamo.update_bet.
    settled_at: str | None = None     # ISO-8601 UTC; None on a pending bet (or one settled
                                      # before E9.49, which is not backfilled — see the story)
    settle_source: str | None = None  # 'mart' | 'statsapi' — which K/score authority graded it


class BetsResponse(BaseModel):
    bets: list[Bet]
    total: int


class LoginSyncRequest(BaseModel):
    email: str | None = None
